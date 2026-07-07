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
import hashlib
import json
import math
import os
import secrets
import re
import base64
import time
import wave
from io import BytesIO
import numpy as np
from typing import cast
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

from database import Database
from content_analyzer import ContentAnalyzer

AUDIO_SAMPLE_RATE = 16000

# Load environment variables
load_dotenv(Path(__file__).resolve().parent / ".env")

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
        configured_path = os.getenv('DATABASE_PATH', 'isweep.db')
        if os.path.isabs(configured_path):
            db_path = configured_path
        else:
            # Keep DB location stable regardless of the shell working directory.
            db_path = os.path.join(os.path.dirname(__file__), configured_path)
        app.database = Database(db_path)
    return app.database

def get_analyzer():
    """Get or create the shared ContentAnalyzer that scores caption text."""
    if not hasattr(app, 'analyzer'):
        app.analyzer = ContentAnalyzer()
    return app.analyzer


# In-memory diagnostic counters for the /captions/transcribe pipeline.
# Never persisted; reset on server restart. Exposed via GET /captions/debug.
captions_debug: dict = {
    'transcribe_requests': 0,
    'last_audio_bytes': 0,
    'last_sample_rate': None,
    'last_duration_seconds': 0.0,
    'last_source': None,
    'last_text_length': 0,
    'last_text_preview': '',
    'last_error': None,
    'chunkStartedAt': None,
    'chunkFlushedAt': None,
    'transcribeStartedAt': None,
    'transcribeFinishedAt': None,
    'relaySentAt': None,
    'overlayRenderedAt': None,
    'totalLatencyMs': None,
}

# Rolling per-session caption state used by /captions/transcribe live pipeline.
# Keyed by user+tab+video+session so each active tab/session keeps an independent buffer.
rolling_caption_state: dict = {}
ROLLING_CAPTION_WINDOW_SEC = 4.0
ROLLING_TRANSCRIBE_INTERVAL_MS = 750
MIN_INITIAL_STT_CONTEXT_MS = 1500


def build_preferences_fingerprint(preferences: dict, stt_mode: dict | None = None) -> str:
    """Build stable hash for preference payloads used by /videos/analyze cache."""
    canonical = json.dumps({
        'preferences': preferences or {},
        'stt_mode': stt_mode or {'enabled': False, 'model': None},
    }, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    
def _extract_transcribe_text(result: dict) -> str:
    """Choose the cleanest caption text available for the owned caption overlay."""
    if not isinstance(result, dict):
        return ''
    for key in ('clean_text', 'cleaned_text', 'caption_text', 'text'):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    cleaned_captions = result.get('cleaned_captions') if isinstance(result.get('cleaned_captions'), list) else []
    for entry in cleaned_captions:
        if not isinstance(entry, dict):
            continue
        for key in ('clean_text', 'cleaned_text', 'caption_text', 'text'):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ''


def _rolling_state_key(user_id: int | None, tab_id: int | None, video_id: str, session_id: str | None) -> str:
    clean_video_id = str(video_id or '').strip() or 'unknown_video'
    clean_session_id = str(session_id or '').strip() or 'unknown_session'
    clean_tab_id = int(tab_id or 0)
    return f"{int(user_id or 0)}::{clean_tab_id}::{clean_video_id}::{clean_session_id}"


def _reset_rolling_state(state: dict, sample_rate: int = AUDIO_SAMPLE_RATE) -> None:
    state['sample_rate'] = int(sample_rate or AUDIO_SAMPLE_RATE)
    state['samples'] = np.array([], dtype=np.float32)
    state['last_transcribe_at'] = 0
    state['last_text'] = ''
    state['last_stable_text'] = ''
    state['last_words'] = []
    state['last_word_tokens'] = []
    state['last_sequence_number'] = None


def _get_or_create_rolling_state(user_id: int | None, tab_id: int | None, video_id: str, session_id: str | None) -> tuple[str, dict, bool]:
    key = _rolling_state_key(user_id, tab_id, video_id, session_id)
    if key not in rolling_caption_state:
        rolling_caption_state[key] = {}
        _reset_rolling_state(rolling_caption_state[key], AUDIO_SAMPLE_RATE)
        rolling_caption_state[key]['created_at'] = int(time.time() * 1000)
        rolling_caption_state[key]['key'] = key
        return key, rolling_caption_state[key], True
    return key, rolling_caption_state[key], False


def _log_stt_session(event: str, payload: dict) -> None:
    print(f"[ISWEEP][STT_SESSION] {event}", payload)


def _extract_filter_word_hints(preferences: dict) -> list[str]:
    if not isinstance(preferences, dict):
        return []
    out: list[str] = []
    categories = preferences.get('categories') if isinstance(preferences.get('categories'), dict) else {}
    language = categories.get('language') if isinstance(categories.get('language'), dict) else {}
    blocklist = preferences.get('blocklist') if isinstance(preferences.get('blocklist'), dict) else {}
    for key in ('items', 'words', 'customWords'):
        values = language.get(key)
        if isinstance(values, list):
            out.extend(values)
        values = blocklist.get(key)
        if isinstance(values, list):
            out.extend(values)
    custom_words = preferences.get('customWords')
    if isinstance(custom_words, list):
        out.extend(custom_words)

    normalized = []
    for entry in out:
        word = str(entry or '').strip().lower()
        if not word:
            continue
        if word not in normalized:
            normalized.append(word)
    return normalized[:32]


def _decode_wav_to_mono_float(decoded_audio: bytes) -> tuple[np.ndarray, int]:
    if not decoded_audio:
        return np.array([], dtype=np.float32), AUDIO_SAMPLE_RATE
    with wave.open(BytesIO(decoded_audio), 'rb') as wav_reader:
        channels = int(wav_reader.getnchannels() or 1)
        sample_width = int(wav_reader.getsampwidth() or 0)
        sample_rate = int(wav_reader.getframerate() or 0) or AUDIO_SAMPLE_RATE
        frame_count = int(wav_reader.getnframes() or 0)
        raw_frames = wav_reader.readframes(frame_count)

    if not raw_frames or sample_width <= 0:
        return np.array([], dtype=np.float32), sample_rate

    if sample_width == 1:
        mono = (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        mono = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        mono = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        return np.array([], dtype=np.float32), sample_rate

    if channels > 1 and mono.size >= channels:
        frame_total = mono.size // channels
        mono = mono[: frame_total * channels].reshape(frame_total, channels).mean(axis=1)
    return mono.astype(np.float32, copy=False), sample_rate


def _float_to_base64_wav(samples: np.ndarray, sample_rate: int) -> str:
    if samples is None or int(samples.size) == 0:
        return ''
    pcm = np.clip(samples.astype(np.float32, copy=False), -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with BytesIO() as wav_buffer:
        with cast(wave.Wave_write, wave.open(wav_buffer, 'wb')) as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(sample_rate) if int(sample_rate) > 0 else AUDIO_SAMPLE_RATE)
            wav_file.writeframes(pcm16.tobytes())
        return base64.b64encode(wav_buffer.getvalue()).decode('ascii')


def _normalized_word_tokens(words: list[dict]) -> list[str]:
    return [str(entry.get('word') or '').strip().lower() for entry in (words or []) if str(entry.get('word') or '').strip()]


def _suffix_prefix_overlap(prev_tokens: list[str], new_tokens: list[str], max_overlap: int = 20) -> int:
    if not prev_tokens or not new_tokens:
        return 0
    limit = min(len(prev_tokens), len(new_tokens), max_overlap)
    for size in range(limit, 0, -1):
        if prev_tokens[-size:] == new_tokens[:size]:
            return size
    return 0


def _longest_common_prefix_words(first_text: str, second_text: str) -> str:
    first = [token for token in str(first_text or '').split(' ') if token]
    second = [token for token in str(second_text or '').split(' ') if token]
    out = []
    for idx, token in enumerate(first):
        if idx >= len(second):
            break
        if token != second[idx]:
            break
        out.append(token)
    return ' '.join(out).strip()


def as_bool(value) -> bool:
    """Parse booleans from JSON values and common string forms."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return False


def _float_audio_payload_to_base64_wav(sample_rate: int, channels: int, samples) -> str:
    """Convert Float32 sample arrays into base64 WAV so existing analyzer path can reuse decode/transcribe logic."""
    if not isinstance(samples, list) or not samples:
        raise ValueError('audio sample array is required')

    rate = int(sample_rate) if isinstance(sample_rate, (int, float)) else 16000
    if rate <= 0:
        rate = 16000

    ch = int(channels) if isinstance(channels, (int, float)) else 1
    if ch <= 0:
        ch = 1

    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim != 1:
        audio = audio.reshape(-1)
    if audio.size == 0:
        raise ValueError('audio sample array is empty')

    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)

    with BytesIO() as wav_buffer:
        with cast(wave.Wave_write, wave.open(wav_buffer, 'wb')) as wav_file:
            wav_file.setnchannels(ch)
            wav_file.setsampwidth(2)
            wav_file.setframerate(rate)
            wav_file.writeframes(pcm16.tobytes())
        return base64.b64encode(wav_buffer.getvalue()).decode('ascii')


def _decode_base64_audio_payload(audio_chunk: str) -> bytes:
    """Decode base64 audio payload with optional data URI prefix."""
    payload = str(audio_chunk or '').strip()
    if not payload:
        return b''
    if payload.startswith('data:') and ',' in payload:
        payload = payload.split(',', 1)[1]
    try:
        return base64.b64decode(payload, validate=False)
    except Exception:
        return b''


def _measure_wav_audio(decoded_audio: bytes) -> dict:
    """Return WAV diagnostics used for transcribe troubleshooting logs."""
    diagnostics = {
        'sample_rate': None,
        'channels': None,
        'duration_seconds': 0.0,
        'rms': None,
        'peak': None,
        'wav_parse_ok': False,
    }
    if not decoded_audio:
        return diagnostics

    try:
        with wave.open(BytesIO(decoded_audio), 'rb') as wav_reader:
            channels = int(wav_reader.getnchannels() or 1)
            sample_width = int(wav_reader.getsampwidth() or 0)
            sample_rate = int(wav_reader.getframerate() or 0)
            frame_count = int(wav_reader.getnframes() or 0)
            raw_frames = wav_reader.readframes(frame_count)

        diagnostics['sample_rate'] = sample_rate if sample_rate > 0 else None
        diagnostics['channels'] = channels if channels > 0 else None
        diagnostics['duration_seconds'] = round((frame_count / sample_rate), 3) if sample_rate > 0 else 0.0

        if not raw_frames or sample_width <= 0:
            diagnostics['wav_parse_ok'] = True
            diagnostics['rms'] = 0.0
            diagnostics['peak'] = 0.0
            return diagnostics

        if sample_width == 1:
            # 8-bit PCM is unsigned.
            mono = (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sample_width == 2:
            mono = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            mono = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            diagnostics['wav_parse_ok'] = True
            diagnostics['rms'] = None
            diagnostics['peak'] = None
            return diagnostics

        if channels > 1 and mono.size >= channels:
            frame_total = mono.size // channels
            mono = mono[: frame_total * channels].reshape(frame_total, channels).mean(axis=1)

        if mono.size == 0:
            rms = 0.0
            peak = 0.0
        else:
            rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float32), dtype=np.float32)))
            peak = float(np.max(np.abs(mono)))

        diagnostics['wav_parse_ok'] = True
        diagnostics['rms'] = round(rms, 6)
        diagnostics['peak'] = round(peak, 6)
        return diagnostics
    except Exception:
        return diagnostics


def issue_token(user_id: int) -> str:
    """Create a bearer token valid for 7 days and persist it for auth checks."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)
    db = get_db()
    db.store_user_token(user_id, token, expires_at)
    return token


@app.route('/', methods=['GET'])
def root():
    """Root endpoint - returns basic service info."""
    return jsonify({
        'service': 'ISweep Backend',
        'version': '1.0.0',
        'status': 'running',
        'endpoints': {
            'health': '/health',
            'captions_debug': '/captions/debug',
            'captions_transcribe': '/captions/transcribe',
            'videos_analyze': '/videos/analyze',
        }
    }), 200


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
    analyzer = get_analyzer()
    return jsonify({
        'status': 'ok',
        'stt_enabled': getattr(analyzer, 'stt_enabled', False) is True,
    }), 200


@app.route('/auth/signup', methods=['POST'])
@app.route('/auth/register', methods=['POST'])
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
    stt_mode = analyzer.get_stt_cache_mode() if hasattr(analyzer, 'get_stt_cache_mode') else {'enabled': False, 'model': None}
    preferences_fingerprint = build_preferences_fingerprint(preferences, stt_mode)
    force_refresh = as_bool(data.get('force_refresh'))

    if force_refresh:
        print('[ISWEEP][CACHE] bypass force_refresh', {
            'video_id': video_id,
            'preferences_fingerprint': preferences_fingerprint,
        })
    else:
        cached = db.get_video_analysis_cache(video_id, preferences_fingerprint)
        if cached:
            print('[ISWEEP][CACHE] hit', {
                'video_id': video_id,
                'preferences_fingerprint': preferences_fingerprint,
            })
            return jsonify({
                'status': cached.get('status', 'error'),
                'source': cached.get('source'),
                'events': cached.get('events', []),
                'cleaned_captions': cached.get('cleaned_captions', []),
                'clean_captions': cached.get('clean_captions', cached.get('cleaned_captions', [])),
                'failure_reason': cached.get('failure_reason'),
                'cached': True,
            }), 200

        print('[ISWEEP][CACHE] miss', {
            'video_id': video_id,
            'preferences_fingerprint': preferences_fingerprint,
        })

    result = analyzer.analyze_video_markers(video_id, preferences)

    if result.get('status') != 'error':
        db.save_video_analysis_cache(video_id, preferences_fingerprint, {
            'status': result.get('status', 'error'),
            'source': result.get('source'),
            'events': result.get('events', []),
            'cleaned_captions': result.get('cleaned_captions', []),
            'clean_captions': result.get('clean_captions', result.get('cleaned_captions', [])),
            'failure_reason': result.get('failure_reason'),
        })
        print('[ISWEEP][CACHE] saved', {
            'video_id': video_id,
            'preferences_fingerprint': preferences_fingerprint,
            'status': result.get('status', 'error'),
        })

    return jsonify({
        'status': result.get('status', 'error'),
        'source': result.get('source'),
        'events': result.get('events', []),
        'cleaned_captions': result.get('cleaned_captions', []),
        'clean_captions': result.get('clean_captions', result.get('cleaned_captions', [])),
        'failure_reason': result.get('failure_reason'),
        'cached': False,
    }), 200


@app.route('/audio/analyze', methods=['POST'])
@require_auth
def analyze_audio_chunk():
    """Audio watch-ahead endpoint: transcribe chunk audio and emit marker events."""
    data = request.get_json() or {}
    audio_chunk = str(data.get('audio_chunk') or data.get('audio_b64') or '').strip()
    mime_type = str(data.get('mime_type') or 'audio/wav').strip()
    video_id = str(data.get('video_id') or '').strip()
    force_refresh = as_bool(data.get('force_refresh'))

    try:
        start_seconds = float(
            data.get('chunk_start_seconds')
            or data.get('start_seconds')
            or data.get('chunk_offset_seconds')
            or 0
        )
    except (TypeError, ValueError):
        start_seconds = 0.0

    try:
        end_seconds = float(data.get('chunk_end_seconds') or data.get('end_seconds') or start_seconds)
    except (TypeError, ValueError):
        end_seconds = start_seconds

    if end_seconds < start_seconds:
        end_seconds = start_seconds

    if not audio_chunk:
        return jsonify({'error': 'audio_chunk is required'}), 400

    db = get_db()
    preferences = db.get_user_preferences(request.user_id) or {}
    analyzer = get_analyzer()
    stt_mode = analyzer.get_stt_cache_mode() if hasattr(analyzer, 'get_stt_cache_mode') else {'enabled': False, 'model': None}
    preferences_fingerprint = build_preferences_fingerprint(preferences, stt_mode)
    stt_model = stt_mode.get('model') if stt_mode.get('enabled') else None

    if force_refresh:
        print('[ISWEEP][AUDIO_STT] bypass force_refresh', {
            'video_id': video_id,
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
        })
    else:
        cached = db.get_audio_stt_chunk_cache(
            video_id=video_id,
            preferences_fingerprint=preferences_fingerprint,
            stt_model=stt_model,
            chunk_start_seconds=start_seconds,
            chunk_end_seconds=end_seconds,
        )
        if cached:
            print('[ISWEEP][AUDIO_STT] cached hit', {
                'video_id': video_id,
                'start_seconds': start_seconds,
                'end_seconds': end_seconds,
            })
            cached_cleaned = cached.get('cleaned_captions', [])
            fallback_text = cached_cleaned[0].get('text') if cached_cleaned else None
            fallback_clean_text = cached_cleaned[0].get('clean_text') if cached_cleaned else None
            return jsonify({
                'status': cached.get('status', 'error'),
                'source': cached.get('source'),
                'start_seconds': start_seconds,
                'end_seconds': end_seconds,
                'events': cached.get('events', []),
                'cleaned_captions': cached_cleaned,
                'clean_captions': cached.get('clean_captions', cached_cleaned),
                'text': cached.get('text', fallback_text),
                'clean_text': cached.get('clean_text', fallback_clean_text),
                'failure_reason': cached.get('failure_reason'),
                'cached': True,
            }), 200

    try:
        audio_chunk_debug = audio_chunk.split(',', 1)[1] if ',' in audio_chunk else audio_chunk
        audio_bytes = base64.b64decode(audio_chunk_debug, validate=False)
        print("[ISWEEP][AUDIO_DEBUG] received audio bytes:", len(audio_bytes))
    except Exception as err:
        print("[ISWEEP][AUDIO_DEBUG] Audio decode failed:", str(err))

    result = analyzer.analyze_audio_chunk(
        audio_chunk, mime_type, start_seconds, end_seconds, preferences, video_id
    )

    if result.get('status') != 'error':
        db.save_audio_stt_chunk_cache(
            video_id=video_id,
            preferences_fingerprint=preferences_fingerprint,
            stt_model=stt_model,
            chunk_start_seconds=start_seconds,
            chunk_end_seconds=end_seconds,
            payload={
                'status': result.get('status', 'error'),
                'source': result.get('source'),
                'events': result.get('events', []),
                'cleaned_captions': result.get('cleaned_captions', []),
                'clean_captions': result.get('cleaned_captions', []),
                'text': result.get('text'),
                'clean_text': result.get('clean_text'),
                'failure_reason': result.get('failure_reason'),
            },
        )
        print('[ISWEEP][AUDIO_STT] cached saved', {
            'video_id': video_id,
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'status': result.get('status', 'error'),
        })

    return jsonify({
        'status': result.get('status', 'error'),
        'source': result.get('source'),
        'start_seconds': start_seconds,
        'end_seconds': end_seconds,
        'events': result.get('events', []),
        'cleaned_captions': result.get('cleaned_captions', []),
        'clean_captions': result.get('cleaned_captions', []),
        'text': result.get('text'),
        'clean_text': result.get('clean_text'),
        'failure_reason': result.get('failure_reason'),
        'cached': False,
    }), 200


@app.route('/audio/analyze_chunk', methods=['POST'])
@require_auth
def analyze_audio_chunk_live():
    """Live rolling-audio endpoint that emits marker events for scheduler injection."""
    data = request.get_json() or {}
    audio_base64 = str(data.get('audio_base64') or data.get('audio_chunk') or '').strip()
    video_id = str(data.get('video_id') or '').strip()
    try:
        start_time = float(data.get('start_time') or data.get('start_seconds') or 0)
    except (TypeError, ValueError):
        start_time = 0.0

    if not audio_base64:
        return jsonify({'error': 'audio_base64 is required'}), 400

    try:
        raw = audio_base64.split(',', 1)[1] if ',' in audio_base64 else audio_base64
        audio_bytes = base64.b64decode(raw + '==')
    except Exception:
        return jsonify({
            'events': [],
            'cleaned_text': '',
            'words': [],
            'source': 'audio',
            'failure_reason': 'audio_decode_failed',
        }), 200

    db = get_db()
    stored_preferences = db.get_user_preferences(request.user_id) or {}
    request_preferences = data.get('preferences') if isinstance(data.get('preferences'), dict) else None
    preferences = request_preferences or stored_preferences

    analyzer = get_analyzer()
    result = analyzer.analyze_audio_chunk_bytes(
        audio_bytes=audio_bytes,
        start_time=start_time,
        preferences=preferences,
        video_id=video_id,
    )

    return jsonify({
        'events': result.get('events', []),
        'cleaned_text': result.get('cleaned_text', ''),
        'words': result.get('words', []),
        'source': result.get('source', 'audio'),
        'failure_reason': result.get('failure_reason'),
    }), 200


@app.route('/captions/transcribe', methods=['POST'])
@require_auth
def transcribe_caption_audio():
    """Owned caption STT endpoint for the extension overlay.

    This route stays safe when STT is disabled: it returns a disabled/unavailable
    response instead of requiring faster-whisper to be installed.
    """
    data = request.get_json() or {}
    transcribe_started_at = int(time.time() * 1000)
    audio_chunk = str(data.get('audio_chunk') or data.get('audio_base64') or data.get('audio_b64') or '').strip()
    sample_rate = data.get('sampleRate') if data.get('sampleRate') is not None else data.get('sample_rate')
    channels = data.get('channels')
    float_samples = data.get('audio')
    mime_type = str(data.get('mime_type') or 'audio/wav').strip()
    video_id = str(data.get('video_id') or '').strip()
    tab_id = int(data.get('tab_id')) if str(data.get('tab_id') or '').isdigit() else None
    session_id = str(data.get('session_id') or '').strip() or None
    chunk_id = str(data.get('chunk_id') or '').strip() or None
    sequence_number = int(data.get('sequence_number')) if str(data.get('sequence_number') or '').isdigit() else None
    audio_window_start_ms = int(data.get('audio_window_start_ms')) if str(data.get('audio_window_start_ms') or '').isdigit() else None
    audio_window_end_ms = int(data.get('audio_window_end_ms')) if str(data.get('audio_window_end_ms') or '').isdigit() else None
    vad_state = str(data.get('vad_state') or '').strip().lower() or None

    try:
        start_seconds = float(
            data.get('chunk_start_seconds')
            or data.get('start_seconds')
            or data.get('start_time')
            or data.get('chunk_offset_seconds')
            or 0
        )
    except (TypeError, ValueError):
        start_seconds = 0.0

    try:
        end_seconds = float(data.get('chunk_end_seconds') or data.get('end_seconds') or start_seconds)
    except (TypeError, ValueError):
        end_seconds = start_seconds

    if end_seconds < start_seconds:
        end_seconds = start_seconds

    capture_started_at = int(data.get('capture_started_at')) if str(data.get('capture_started_at') or '').isdigit() else None
    chunk_started_at = int(data.get('chunk_started_at')) if str(data.get('chunk_started_at') or '').isdigit() else None
    chunk_flushed_at = int(data.get('chunk_flushed_at')) if str(data.get('chunk_flushed_at') or '').isdigit() else None
    chunk_emitted_at = int(data.get('chunk_emitted_at')) if str(data.get('chunk_emitted_at') or '').isdigit() else chunk_flushed_at
    backend_received_at = int(data.get('backend_received_at')) if str(data.get('backend_received_at') or '').isdigit() else int(time.time() * 1000)

    captions_debug['transcribe_requests'] += 1
    captions_debug['last_duration_seconds'] = round(max(end_seconds - start_seconds, 0.0), 3)
    captions_debug['last_sample_rate'] = sample_rate
    captions_debug['last_error'] = None
    captions_debug['chunkStartedAt'] = chunk_started_at
    captions_debug['chunkFlushedAt'] = chunk_flushed_at
    captions_debug['captureStartedAt'] = capture_started_at
    captions_debug['chunkEmittedAt'] = chunk_emitted_at
    captions_debug['backendReceivedAt'] = backend_received_at
    captions_debug['transcribeStartedAt'] = transcribe_started_at
    print('[ISWEEP][CAPTIONS_TRANSCRIBE] request received', {
        'video_id': video_id,
        'start_seconds': start_seconds,
        'end_seconds': end_seconds,
        'mime_type': mime_type,
    })

    if not audio_chunk and isinstance(float_samples, list):
        try:
            audio_chunk = _float_audio_payload_to_base64_wav(sample_rate or 16000, channels or 1, float_samples)
            mime_type = 'audio/wav'
        except Exception:
            return jsonify({'error': 'invalid audio sample payload'}), 400

    if not audio_chunk:
        return jsonify({'error': 'audio_chunk is required'}), 400

    db = get_db()
    preferences = db.get_user_preferences(request.user_id) or {}
    analyzer = get_analyzer()

    decoded_audio = _decode_base64_audio_payload(audio_chunk)
    wav_metrics = _measure_wav_audio(decoded_audio)
    captions_debug['last_audio_bytes'] = len(decoded_audio)

    stt_enabled = bool(getattr(analyzer, 'stt_enabled', False) is True)
    stt_model_name = str(getattr(analyzer, 'stt_model_size', '') or '') or None
    stt_model_initialized = False
    stt_model_init_error = None

    if stt_enabled:
        try:
            adapter = analyzer._get_or_create_stt_adapter() if hasattr(analyzer, '_get_or_create_stt_adapter') else None
            if adapter is not None:
                if hasattr(adapter, '_ensure_model') and callable(getattr(adapter, '_ensure_model')):
                    adapter._ensure_model()
                stt_model_initialized = True
            else:
                stt_model_init_error = 'stt_adapter_missing'
        except Exception as exc:
            stt_model_init_error = str(exc) or 'model_initialization_failed'

    print('[ISWEEP][CAPTIONS_TRANSCRIBE] stt state', {
        'video_id': video_id,
        'stt_enabled': stt_enabled,
        'model_name': stt_model_name,
        'model_initialized': stt_model_initialized,
        'model_init_error': stt_model_init_error,
    })
    print('[ISWEEP][CAPTIONS_TRANSCRIBE] audio diagnostics', {
        'video_id': video_id,
        'wav_bytes': len(decoded_audio),
        'sample_rate': wav_metrics.get('sample_rate'),
        'duration_seconds': wav_metrics.get('duration_seconds'),
        'rms': wav_metrics.get('rms'),
        'peak': wav_metrics.get('peak'),
        'wav_parse_ok': wav_metrics.get('wav_parse_ok'),
    })

    rolling_key, rolling_state, created_new_state = _get_or_create_rolling_state(
        request.user_id,
        tab_id,
        video_id,
        session_id,
    )
    if created_new_state:
        _log_stt_session('buffer reset', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'audio_window_start_ms': audio_window_start_ms,
            'audio_window_end_ms': audio_window_end_ms,
            'vad_state': vad_state,
            'reason': 'new_identity_key',
            'rolling_key': rolling_key,
        })
    mono_samples = np.array([], dtype=np.float32)
    decoded_sample_rate = wav_metrics.get('sample_rate') if isinstance(wav_metrics.get('sample_rate'), (int, float)) else None
    try:
        mono_samples, sample_rate_from_wav = _decode_wav_to_mono_float(decoded_audio)
        if sample_rate_from_wav:
            decoded_sample_rate = sample_rate_from_wav
    except Exception:
        mono_samples = np.array([], dtype=np.float32)

    if decoded_sample_rate and int(decoded_sample_rate) > 0:
        rolling_sample_rate = int(decoded_sample_rate)
    else:
        rolling_sample_rate = int(rolling_state.get('sample_rate') or AUDIO_SAMPLE_RATE)

    previous_sequence_number = rolling_state.get('last_sequence_number')
    if sequence_number is not None and isinstance(previous_sequence_number, int) and sequence_number <= previous_sequence_number:
        _log_stt_session('stale transcript rejected', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'sequence_number': sequence_number,
            'previous_sequence_number': previous_sequence_number,
            'audio_window_start_ms': audio_window_start_ms,
            'audio_window_end_ms': audio_window_end_ms,
            'vad_state': vad_state,
            'stt_status': 'transcription_error',
            'text_length': 0,
            'word_count': 0,
        })
        stale_response = {
            'text': '',
            'source': 'silence',
            'confidence': 0.0,
            'status': 'error',
            'reason': 'stale transcript rejected',
            'failure_reason': 'stale_chunk_rejected',
            'events': [],
            'cleaned_captions': [],
            'clean_captions': [],
            'clean_text': '',
            'cleaned_text': '',
            'words': [],
            'word_timestamps': [],
            'is_partial': False,
            'stable_text': '',
            'stt_status': 'transcription_error',
            'stt_error': 'stale_chunk_rejected',
            'latency': {
                'capture_started_at': capture_started_at,
                'chunk_started_at': chunk_started_at,
                'chunk_flushed_at': chunk_flushed_at,
                'chunk_emitted_at': chunk_emitted_at,
                'backend_received_at': backend_received_at,
                'transcribe_started_at': transcribe_started_at,
                'transcribe_finished_at': int(time.time() * 1000),
                'content_script_received_at': None,
                'overlay_rendered_at': None,
                'total_latency_ms': (
                    max(int(time.time() * 1000) - int(capture_started_at), 0)
                    if capture_started_at is not None else None
                ),
            },
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'cached': False,
        }
        return jsonify(stale_response), 200

    if sequence_number is not None:
        rolling_state['last_sequence_number'] = sequence_number

    existing_rate = int(rolling_state.get('sample_rate') or rolling_sample_rate)
    if existing_rate != rolling_sample_rate:
        rolling_state['samples'] = np.array([], dtype=np.float32)
        rolling_state['last_words'] = []
        rolling_state['last_word_tokens'] = []
        rolling_state['last_text'] = ''
        rolling_state['last_stable_text'] = ''
    rolling_state['sample_rate'] = rolling_sample_rate

    if mono_samples.size:
        existing_samples = rolling_state.get('samples')
        if isinstance(existing_samples, np.ndarray) and existing_samples.size:
            combined = np.concatenate([existing_samples.astype(np.float32, copy=False), mono_samples.astype(np.float32, copy=False)])
        else:
            combined = mono_samples.astype(np.float32, copy=False)
        max_samples = int(ROLLING_CAPTION_WINDOW_SEC * rolling_sample_rate)
        if combined.size > max_samples:
            combined = combined[-max_samples:]
        rolling_state['samples'] = combined
    rolling_samples_for_context = rolling_state.get('samples')
    if not isinstance(rolling_samples_for_context, np.ndarray):
        rolling_samples_for_context = np.array([], dtype=np.float32)

    rolling_duration_ms = (
        int(round((rolling_samples_for_context.size / rolling_sample_rate) * 1000))
        if rolling_sample_rate > 0 else 0
    )

    # Do not ask Whisper to guess from a fraction of a second of audio.
    if wav_metrics.get('wav_parse_ok') and rolling_duration_ms < MIN_INITIAL_STT_CONTEXT_MS:
        now_ms = int(time.time() * 1000)
        waiting_response = {
            'text': '',
            'source': 'waiting_audio_context',
            'confidence': 0.0,
            'status': 'waiting',
            'reason': '',
            'failure_reason': None,
            'events': [],
            'cleaned_captions': [],
            'clean_captions': [],
            'clean_text': '',
            'cleaned_text': '',
            'words': [],
            'word_timestamps': [],
            'is_partial': False,
            'stable_text': '',
            'stt_status': 'waiting_for_context',
            'stt_error': None,
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'cached': False,
        }

        captions_debug['last_source'] = waiting_response['source']
        captions_debug['last_text_length'] = 0
        captions_debug['last_text_preview'] = ''
        captions_debug['last_error'] = None
        captions_debug['transcribeFinishedAt'] = now_ms

        _log_stt_session('waiting for context', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'sequence_number': sequence_number,
            'audio_window_end_ms': audio_window_end_ms,
            'rolling_audio_duration_ms': rolling_duration_ms,
            'minimum_audio_context_ms': MIN_INITIAL_STT_CONTEXT_MS,
        })

        return jsonify(waiting_response), 200
    def build_caption_latency(finished_at: int) -> dict:
        return {
            'capture_started_at': capture_started_at,
            'chunk_started_at': chunk_started_at,
            'chunk_flushed_at': chunk_flushed_at,
            'chunk_emitted_at': chunk_emitted_at,
            'backend_received_at': backend_received_at,
            'transcribe_started_at': transcribe_started_at,
            'transcribe_finished_at': finished_at,
            'content_script_received_at': None,
            'overlay_rendered_at': None,
            'total_latency_ms': (
                max(finished_at - int(capture_started_at), 0)
                if capture_started_at is not None else None
            ),
        }

    transcribe_finished_at = int(time.time() * 1000)
    can_transcribe_now = (
        transcribe_finished_at
        - int(rolling_state.get('last_transcribe_at') or 0)
    ) >= ROLLING_TRANSCRIBE_INTERVAL_MS

    # When we are inside the 750 ms cadence, do not reuse the last transcript
    # as if it were new speech. Tell the extension that there is no new text.
    use_cached_only = (
        not can_transcribe_now
        and bool(rolling_state.get('last_text'))
    )

    if use_cached_only:
        no_change_response = {
            'text': '',
            'source': 'audio_stt_cached',
            'confidence': 0.0,
            'status': 'ready',
            'reason': '',
            'failure_reason': None,
            'events': [],
            'cleaned_captions': [],
            'clean_captions': [],
            'clean_text': '',
            'cleaned_text': '',
            'words': [],
            'word_timestamps': [],
            'is_partial': False,
            'stable_text': '',
            'no_change': True,
            'stt_status': 'ok',
            'stt_error': None,
            'latency': build_caption_latency(transcribe_finished_at),
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'cached': True,
        }
        captions_debug['last_source'] = no_change_response['source']
        captions_debug['last_text_length'] = 0
        captions_debug['last_text_preview'] = ''
        captions_debug['last_error'] = None
        captions_debug['transcribeFinishedAt'] = transcribe_finished_at
        _log_stt_session('no transcript change', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'sequence_number': sequence_number,
            'audio_window_end_ms': audio_window_end_ms,
            'reason': 'transcribe_cadence',
        })
        return jsonify(no_change_response), 200

    caught_transcription_exception = None
    rolling_samples = (
        rolling_state.get('samples')
        if isinstance(rolling_state.get('samples'), np.ndarray)
        else np.array([], dtype=np.float32)
    )
    rolling_duration_sec = (
        rolling_samples.size / rolling_sample_rate
        if rolling_sample_rate > 0 else 0.0
    )
    rolling_start_seconds = max(end_seconds - rolling_duration_sec, 0.0)
    rolling_audio_chunk = _float_to_base64_wav(rolling_samples, rolling_sample_rate)
    hint_words = _extract_filter_word_hints(preferences)

    print('[ISWEEP][CAPTIONS_TRANSCRIBE] hotword hints', {
        'video_id': video_id,
        'count': len(hint_words),
        'preview': hint_words[:8],
    })

    try:
        result = analyzer.analyze_audio_chunk(
            rolling_audio_chunk or audio_chunk,
            'audio/wav',
            rolling_start_seconds,
            end_seconds,
            preferences,
            video_id,
            caption_only=True,
        )
        rolling_state['last_transcribe_at'] = int(time.time() * 1000)
    except Exception as exc:
        caught_transcription_exception = str(exc) or exc.__class__.__name__
        print('[ISWEEP][CAPTIONS_TRANSCRIBE] transcription exception', {
            'video_id': video_id,
            'error': caught_transcription_exception,
        })
        result = {
            'status': 'error',
            'source': 'audio_stt_live',
            'events': [],
            'cleaned_captions': [],
            'failure_reason': 'transcription_failed',
            'text': '',
            'words': [],
        }

    if not isinstance(result, dict):
        result = {
            'status': 'error',
            'source': 'audio_stt_live',
            'events': [],
            'cleaned_captions': [],
            'failure_reason': 'invalid_transcription_result',
            'text': '',
            'words': [],
        }

    raw_transcription_text = str(result.get('text') or '').strip()
    full_text = _extract_transcribe_text(result)
    failure_reason = result.get('failure_reason')
    words = result.get('words') if isinstance(result.get('words'), list) else []
    word_timestamps_full = (
        result.get('word_timestamps')
        if isinstance(result.get('word_timestamps'), list)
        else words
    )

    previous_text = str(rolling_state.get('last_text') or '')
    previous_tokens = (
        rolling_state.get('last_word_tokens')
        if isinstance(rolling_state.get('last_word_tokens'), list)
        else []
    )
    new_tokens = _normalized_word_tokens(word_timestamps_full)
    if not new_tokens and full_text:
        new_tokens = [
            token.strip().lower()
            for token in full_text.split(' ')
            if token.strip()
        ]

    # The same rolling-window transcription is not new speech. Do not label it
    # as silence and do not send it to the overlay again.
    transcript_unchanged = (
        bool(full_text)
        and full_text == previous_text
        and not failure_reason
    )
    if transcript_unchanged:
        no_change_response = {
            'text': '',
            'source': 'audio_stt_cached',
            'confidence': float(result.get('confidence') or 0.0),
            'status': 'ready',
            'reason': '',
            'failure_reason': None,
            'events': [],
            'cleaned_captions': [],
            'clean_captions': [],
            'clean_text': '',
            'cleaned_text': '',
            'words': [],
            'word_timestamps': [],
            'is_partial': False,
            'stable_text': '',
            'no_change': True,
            'stt_status': 'ok',
            'stt_error': None,
            'latency': build_caption_latency(int(time.time() * 1000)),
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'cached': True,
        }
        captions_debug['last_source'] = no_change_response['source']
        captions_debug['last_text_length'] = 0
        captions_debug['last_text_preview'] = ''
        captions_debug['last_error'] = None
        captions_debug['transcribeFinishedAt'] = no_change_response['latency']['transcribe_finished_at']
        _log_stt_session('no transcript change', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'sequence_number': sequence_number,
            'audio_window_end_ms': audio_window_end_ms,
            'reason': 'same_transcript',
        })
        return jsonify(no_change_response), 200

    overlap_size = _suffix_prefix_overlap(previous_tokens, new_tokens)
    dedup_tokens = new_tokens[overlap_size:] if overlap_size > 0 else new_tokens
    dedup_words = (
        word_timestamps_full[overlap_size:]
        if overlap_size > 0 else word_timestamps_full
    )

    text = ' '.join(dedup_tokens).strip()
    if not text and full_text and full_text != previous_text:
        # Correction-only update: publish a corrected rolling transcript.
        text = full_text
        dedup_words = word_timestamps_full

    stable_text = _longest_common_prefix_words(previous_text, full_text)
    if not stable_text:
        stable_text = str(rolling_state.get('last_stable_text') or '')

    is_partial = bool(full_text) and not bool(
        re.search(r"[.!?]['\")\]]?\s*$", full_text)
    )
    if failure_reason:
        is_partial = False

    if full_text:
        rolling_state['last_text'] = full_text
        rolling_state['last_words'] = word_timestamps_full
        rolling_state['last_word_tokens'] = new_tokens
        if not is_partial:
            rolling_state['last_stable_text'] = full_text
            stable_text = full_text
        elif stable_text and len(stable_text) >= len(
            str(rolling_state.get('last_stable_text') or '')
        ):
            rolling_state['last_stable_text'] = stable_text
    elif failure_reason:
        rolling_state['last_text'] = ''
        rolling_state['last_words'] = []
        rolling_state['last_word_tokens'] = []

    word_timestamps = dedup_words if isinstance(dedup_words, list) else []
    words = word_timestamps
    transcribe_finished_at = int(time.time() * 1000)

    print('[ISWEEP][CAPTIONS_TRANSCRIBE] transcription output', {
        'video_id': video_id,
        'raw_text_preview': raw_transcription_text[:120],
        'clean_text_preview': str(text or '')[:120],
        'word_timestamp_count': len(word_timestamps_full),
        'dedup_word_timestamp_count': len(word_timestamps),
        'is_partial': is_partial,
        'stable_text_preview': str(stable_text or '')[:120],
        'failure_reason': failure_reason,
    })

    is_quiet_audio = (
        isinstance(wav_metrics.get('rms'), (int, float))
        and isinstance(wav_metrics.get('peak'), (int, float))
        and float(wav_metrics.get('rms')) <= 0.003
        and float(wav_metrics.get('peak')) <= 0.02
    )

    stt_status = 'ok'
    stt_error = None
    if not stt_enabled:
        stt_status = 'disabled'
        stt_error = 'stt_disabled'
    elif stt_model_init_error:
        stt_status = 'model_unavailable'
        stt_error = stt_model_init_error
    elif caught_transcription_exception:
        stt_status = 'transcription_error'
        stt_error = caught_transcription_exception
    elif failure_reason in {'stt_unavailable', 'transcription_unavailable'}:
        stt_status = 'model_unavailable'
        stt_error = failure_reason
    elif failure_reason in {
        'transcription_failed',
        'analyze_exception',
        'audio_decode_failed',
        'transcription_error',
        'invalid_transcription_result',
    }:
        stt_status = 'transcription_error'
        stt_error = failure_reason
    elif not text and not word_timestamps:
        if is_quiet_audio:
            stt_status = 'silent_audio'
        else:
            stt_status = 'transcription_error'
            stt_error = failure_reason or 'empty_transcription_non_silent'

    if stt_status == 'disabled':
        source = 'audio_stt_disabled'
    elif stt_status == 'model_unavailable':
        source = 'audio_stt_unavailable'
    elif stt_status == 'silent_audio':
        source = 'silence'
    elif stt_status == 'transcription_error':
        source = 'audio_stt'
    elif text:
        source = 'audio_stt_live'
    else:
        source = 'silence'

    # VAD is useful diagnostic information, but it is not trusted to erase the
    # rolling audio buffer. Music and noisy audio can make VAD report a false
    # speech end. Only a genuinely quiet decoded audio chunk clears the state.
    force_silence_payload = stt_status == 'silent_audio'

    if force_silence_payload:
        _reset_rolling_state(rolling_state, rolling_sample_rate)
        if sequence_number is not None:
            rolling_state['last_sequence_number'] = sequence_number
        source = 'silence'
        text = ''
        words = []
        word_timestamps = []
        stable_text = ''

    response = {
        'text': text,
        'source': source,
        'confidence': float(result.get('confidence') or 0.0),
        'status': result.get('status') or ('ready' if text else 'error'),
        'reason': (
            'Speech-to-text is not enabled'
            if source == 'audio_stt_disabled'
            else (
                'Speech-to-text is unavailable'
                if source == 'audio_stt_unavailable'
                else (failure_reason or '')
            )
        ),
        'failure_reason': failure_reason,
        'events': [],
        'cleaned_captions': result.get('cleaned_captions', []),
        'clean_captions': result.get('cleaned_captions', []),
        'clean_text': (
            result.get('clean_text') or text
            if text else ''
        ),
        'cleaned_text': (
            result.get('cleaned_text') or result.get('clean_text') or text
            if text else ''
        ),
        'words': words,
        'word_timestamps': word_timestamps,
        'is_partial': is_partial,
        'stable_text': stable_text,
        'no_change': False,
        'stt_status': stt_status,
        'stt_error': stt_error,
        'latency': build_caption_latency(transcribe_finished_at),
        'start_seconds': start_seconds,
        'end_seconds': end_seconds,
        'cached': False,
    }

    if force_silence_payload:
        _log_stt_session('silence response emitted', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'sequence_number': sequence_number,
            'audio_window_start_ms': audio_window_start_ms,
            'audio_window_end_ms': audio_window_end_ms,
            'vad_state': vad_state,
            'stt_status': response['stt_status'],
            'text_length': 0,
            'word_count': 0,
        })
    elif (
        response['stt_status'] == 'ok'
        and response['source'] == 'audio_stt_live'
        and response['text']
    ):
        _log_stt_session('transcript accepted', {
            'tab_id': tab_id,
            'video_id': video_id,
            'session_id': session_id,
            'chunk_id': chunk_id,
            'sequence_number': sequence_number,
            'audio_window_start_ms': audio_window_start_ms,
            'audio_window_end_ms': audio_window_end_ms,
            'vad_state': vad_state,
            'stt_status': response['stt_status'],
            'text_length': len(response['text'] or ''),
            'word_count': len(response.get('word_timestamps') or []),
        })

    captions_debug['last_source'] = response['source']
    captions_debug['last_text_length'] = len(response['text'] or '')
    captions_debug['last_text_preview'] = (response['text'] or '')[:60]
    captions_debug['last_error'] = stt_error
    captions_debug['transcribeFinishedAt'] = transcribe_finished_at
    if captions_debug['captureStartedAt'] is not None:
        try:
            captions_debug['totalLatencyMs'] = max(
                int(captions_debug['transcribeFinishedAt'])
                - int(captions_debug['captureStartedAt']),
                0,
            )
        except (TypeError, ValueError):
            captions_debug['totalLatencyMs'] = None

    print('[ISWEEP][CAPTIONS_TRANSCRIBE] text returned', {
        'video_id': video_id,
        'source': response['source'],
        'text': response['text'],
        'confidence': response['confidence'],
    })
    return jsonify(response), 200

@app.route('/captions/debug', methods=['GET'])
def get_captions_debug():
    """Return in-memory diagnostic counters for the /captions/transcribe pipeline.

    No auth required — local-dev diagnostic only. Does not expose user data.
    """
    return jsonify(dict(captions_debug)), 200


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Keep local runs stable by default; opt into debug/reload explicitly.
    debug_mode = os.getenv('ISWEEP_DEBUG', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
    app.run(host='127.0.0.1', port=5000, debug=debug_mode, use_reloader=debug_mode)
