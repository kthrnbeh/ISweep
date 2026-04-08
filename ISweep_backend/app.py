"""
ISWEEP COMPONENT: Backend API + Decision Gateway

This module hosts the Flask server that the Chrome extension and frontend call
for authentication, preferences, health checks, and real-time caption decisions.

System flow:
    Extension/frontend -> /auth, /preferences, /event -> Decision engine -> JSON response

Key responsibilities:
    - Expose REST endpoints for auth, preferences, and analysis
    - Guard endpoints with bearer-token auth
    - Forward caption text to ContentAnalyzer and return structured decisions
    - Keep CORS permissive for local extension calls
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import math
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

from database import Database
from content_analyzer import ContentAnalyzer

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "chrome-extension://*",
]

# Allow wide CORS for local dev (TODO: tighten for prod)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS + ["*"]}})


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
    return response


@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        resp = app.make_response(('', 204))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
        return resp

# Initialize database and content analyzer
# These will be created once and reused for the lifetime of the app
def get_db():
    """Get or create the shared Database instance for user data and tokens."""
    if not hasattr(app, 'database'):
        db_path = os.getenv('DATABASE_PATH', 'isweep.db')
        app.database = Database(db_path)
    return app.database

def get_analyzer():
    """Get or create the shared ContentAnalyzer that scores caption text."""
    if not hasattr(app, 'analyzer'):
        app.analyzer = ContentAnalyzer()
    return app.analyzer


def issue_token(user_id: int) -> str:
    """Create a bearer token valid for 7 days and persist it for auth checks."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    db = get_db()
    db.store_user_token(user_id, token, expires_at)
    return token


def require_auth(fn):
    """Decorator that enforces bearer auth and attaches user_id to request."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized'}), 401
        token = auth_header.split(' ', 1)[1].strip()
        user_id = get_db().validate_token(token)
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        request.user_id = user_id
        request.token = token
        return fn(*args, **kwargs)

    return wrapper


@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for client resilience.
    Clients can check if backend is available and remain functional if not.
    """
    return jsonify({
        'status': 'healthy',
        'service': 'ISweep Backend',
        'version': '1.0.0'
    }), 200


@app.route('/health', methods=['GET'])
def health_check_root():
    return jsonify({'status': 'ok'}), 200


@app.route('/auth/signup', methods=['POST'])
def signup():
    """Handle user registration and return an auth token for immediate use."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'email and password are required'}), 400

    db = get_db()
    if db.get_user_by_email(email):
        return jsonify({'error': 'Email already exists'}), 409

    password_hash = generate_password_hash(password)
    user_id = db.create_user(email=email, password_hash=password_hash)
    if not user_id:
        return jsonify({'error': 'Failed to create user'}), 500

    token = issue_token(user_id)
    return jsonify({'token': token, 'user_id': user_id}), 201


@app.route('/auth/login', methods=['POST'])
def login():
    """Verify credentials and return a bearer token used by the extension."""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'email and password are required'}), 400

    db = get_db()
    user = db.get_user_by_email(email)
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401

    token = issue_token(user['id'])
    return jsonify({'token': token, 'user_id': user['id']}), 200


@app.route('/api/users', methods=['POST'])
def create_user():
    """
    Create a new user with default filtering preferences.
    
    Request body:
        {
            "username": "user123"
        }
    
    Response:
        {
            "user_id": 1,
            "username": "user123",
            "preferences": {...}
        }
    """
    data = request.get_json()
    
    if not data or 'username' not in data:
        return jsonify({'error': 'Username is required'}), 400

    username = data['username']
    db = get_db()
    # Legacy endpoint: synthesize email + password for compatibility
    email = f"{username}@dev.local"
    password_hash = generate_password_hash('changeme')
    user_id = db.create_user(email=email, password_hash=password_hash, username=username)
    
    if user_id is None:
        return jsonify({'error': 'Username already exists'}), 409
    
    preferences = db.get_user_preferences(user_id)
    
    return jsonify({
        'user_id': user_id,
        'username': username,
        'preferences': preferences
    }), 201


@app.route('/preferences', methods=['GET'])
@require_auth
def get_preferences_self():
    db = get_db()
    prefs = db.get_user_preferences(request.user_id)
    if not prefs:
        return jsonify({'error': 'Preferences not found'}), 404
    return jsonify(prefs), 200


@app.route('/preferences', methods=['PUT'])
@require_auth
def update_preferences_self():
    data = request.get_json() or {}
    db = get_db()

    # Accept any JSON blob; clients own schema for now
    success = db.update_user_preferences(request.user_id, data)
    if not success:
        return jsonify({'error': 'Failed to update preferences'}), 500

    prefs = db.get_user_preferences(request.user_id)
    return jsonify(prefs), 200


@app.route('/api/users/<int:user_id>/preferences', methods=['GET'])
def get_preferences(user_id):
    """
    Get user filtering preferences.
    
    Response:
        {
            "user_id": 1,
            "language_filter": true,
            "sexual_content_filter": true,
            "violence_filter": true,
            "language_sensitivity": "medium",
            "sexual_content_sensitivity": "medium",
            "violence_sensitivity": "medium"
        }
    """
    db = get_db()
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    preferences = db.get_user_preferences(user_id)
    return jsonify(preferences), 200


@app.route('/api/users/<int:user_id>/preferences', methods=['PUT'])
def update_preferences(user_id):
    """
    Update user filtering preferences.
    
    Request body:
        {
            "language_filter": true,
            "sexual_content_filter": false,
            "violence_filter": true,
            "language_sensitivity": "high",
            "sexual_content_sensitivity": "low",
            "violence_sensitivity": "medium"
        }
    
    Response:
        {
            "message": "Preferences updated successfully",
            "preferences": {...}
        }
    """
    db = get_db()
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    # Validate sensitivity values
    valid_sensitivities = ['low', 'medium', 'high']
    for field in ['language_sensitivity', 'sexual_content_sensitivity', 'violence_sensitivity']:
        if field in data and data[field] not in valid_sensitivities:
            return jsonify({'error': f'Invalid {field}. Must be one of: {", ".join(valid_sensitivities)}'}), 400
    
    success = db.update_user_preferences(user_id, data)
    
    if not success:
        return jsonify({'error': 'Failed to update preferences'}), 500
    
    preferences = db.get_user_preferences(user_id)
    return jsonify({
        'message': 'Preferences updated successfully',
        'preferences': preferences
    }), 200


@app.route('/api/analyze', methods=['POST'])
def analyze_content():
    """Legacy analysis endpoint that returns a simple action without durations."""
    """
    Real-time decision engine: analyze caption/transcript text and return playback action.
    
    Request body:
        {
            "user_id": 1,
            "text": "This is the caption or transcript text to analyze"
        }
    
    Response:
        {
            "action": "mute" | "skip" | "fast_forward" | "none",
            "text": "original text",
            "user_id": 1
        }
    
    Actions:
        - mute: Temporarily mute audio (for language/profanity)
        - skip: Skip ahead (for sexual content scenes)
        - fast_forward: Fast forward (for violence scenes)
        - none: No action needed, content is acceptable
    """
    data = request.get_json()
    
    if not data or 'user_id' not in data or 'text' not in data:
        return jsonify({'error': 'user_id and text are required'}), 400
    
    user_id = data['user_id']
    text = data['text']
    
    db = get_db()
    # Verify user exists
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get user preferences
    preferences = db.get_user_preferences(user_id)
    
    # Analyze content and determine action
    analyzer = get_analyzer()
    action = analyzer.analyze(text, preferences)
    
    return jsonify({
        'action': action,
        'text': text,
        'user_id': user_id
    }), 200


@app.route('/event', methods=['POST'])
@require_auth
def analyze_event():
    """Structured decision endpoint used by the extension for live captions."""
    data = request.get_json() or {}
    text = data.get('text')
    caption_duration_seconds = data.get('caption_duration_seconds')
    confidence = data.get('confidence')

    analyzer = get_analyzer()

    if not text:
        return jsonify({
            "action": "none",
            "duration_seconds": 0,
            "matched_category": None,
            "reason": "No text provided"
        }), 200

    db = get_db()
    preferences = db.get_user_preferences(request.user_id) or {}
    decision = analyzer.analyze_decision(text, preferences, confidence)

    def coerce_caption_duration(raw_value):
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        if value < 0 or value > 60:
            return None
        return value

    if decision.get('action') == 'mute' and decision.get('matched_category') != 'blocklist':
        # Prefer the caption's timing so the mute aligns with the spoken word duration.
        coerced = coerce_caption_duration(caption_duration_seconds)
        if coerced is not None:
            # Add a small buffer so the mute fully covers the word without lingering too long.
            buffered = coerced + 0.15
            # Clamp to prevent under-muting very short clips and to avoid over-muting longer phrases.
            decision['duration_seconds'] = min(max(buffered, 0.3), 2.5)
        else:
            # Fallback: if no caption duration is provided, estimate timing from word count.
            word_count = len((text or '').split())
            estimated = word_count * 0.45
            # Clamp the estimate for the same reasons as above—accuracy without excessive silence.
            decision['duration_seconds'] = min(max(estimated, 0.3), 2.5)

    response_payload = {
        "action": decision.get('action', 'none'),
        "duration_seconds": decision.get('duration_seconds', 0),
        "matched_category": decision.get('matched_category'),
        "reason": decision.get('reason', ''),
    }
    return jsonify(response_payload), 200


@app.route('/videos/analyze', methods=['POST'])
@require_auth
def analyze_video_markers():
    """Watch-ahead endpoint: returns transcript-derived marker events for a video."""
    data = request.get_json() or {}
    video_id = str(data.get('video_id') or '').strip()
    if not video_id:
        return jsonify({'error': 'video_id is required'}), 400

    db = get_db()
    preferences = db.get_user_preferences(request.user_id) or {}
    analyzer = get_analyzer()
    result = analyzer.analyze_video_markers(video_id, preferences)
    return jsonify({
        'status': result.get('status', 'error'),
        'source': result.get('source'),
        'events': result.get('events', []),
    }), 200


@app.route('/audio/analyze', methods=['POST'])
@require_auth
def analyze_audio_chunk():
    """Audio watch-ahead endpoint: transcribes a real-time audio chunk and returns marker events.

    Request body:
        {
            "video_id": "dQw4w9WgXcQ",         # YouTube video ID (for stable marker IDs)
            "audio_b64": "<base64 WAV bytes>",  # 16 kHz 16-bit mono WAV encoded in base64
            "mime_type": "audio/wav",            # always audio/wav from the extension
            "chunk_offset_seconds": 120.5        # absolute video time when chunk started
        }
    Response:
        {
            "status": "ready" | "unavailable" | "error",
            "source": "audio_chunk",
            "chunk_offset_seconds": 120.5,
            "events": [ /* marker objects */ ],
            "failure_reason": null | "transcription_unavailable" | "marker_list_empty" | ...
        }
    Install notes:
        pip install SpeechRecognition    — for Google Web Speech API (requires internet)
        pip install openai-whisper        — future upgrade for offline transcription
    """
    data = request.get_json() or {}
    audio_b64 = str(data.get('audio_b64') or '').strip()
    mime_type = str(data.get('mime_type') or 'audio/wav').strip()
    video_id = str(data.get('video_id') or '').strip()

    try:
        chunk_offset_seconds = float(data.get('chunk_offset_seconds') or 0)
    except (TypeError, ValueError):
        chunk_offset_seconds = 0.0

    if not audio_b64:
        return jsonify({'error': 'audio_b64 is required'}), 400

    db = get_db()
    preferences = db.get_user_preferences(request.user_id) or {}
    analyzer = get_analyzer()
    result = analyzer.analyze_audio_chunk(
        audio_b64, mime_type, chunk_offset_seconds, preferences, video_id
    )

    return jsonify({
        'status': result.get('status', 'error'),
        'source': result.get('source'),
        'chunk_offset_seconds': chunk_offset_seconds,
        'events': result.get('events', []),
        'failure_reason': result.get('failure_reason'),
    }), 200


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
