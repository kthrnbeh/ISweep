# ISweep Backend

ISweep Backend is a real-time decision engine that receives caption or transcript text from client apps and returns playback control actions (mute, skip, fast_forward, or none). It stores per-user filtering preferences for language, sexual content, and violence. Media is never modified. The backend enhances intelligence while clients remain functional if it is unavailable. Designed for browser, mobile, and TV platforms.

## Quick Test (curl)

Run the server (`python app.py`), then from another terminal:

```bash
# 1) Health
curl -s http://127.0.0.1:5000/health

# 2) Save preferences (prototype auth: token == user_id)
USER_ID="demo-user"
curl -s -X PUT http://127.0.0.1:5000/preferences \
  -H "Authorization: Bearer ${USER_ID}" \
  -H "Content-Type: application/json" \
  -d '{
    "language_filter": true,
    "sexual_content_filter": true,
    "violence_filter": true,
    "language_sensitivity": "medium",
    "sexual_content_sensitivity": "medium",
    "violence_sensitivity": "medium",
    "actions": {"language": {"action": "mute", "duration_seconds": 4}}
  }'

# 3) Read preferences
curl -s "http://127.0.0.1:5000/preferences?user_id=${USER_ID}"

# 4) Decision
curl -s -X POST http://127.0.0.1:5000/event \
  -H "Authorization: Bearer ${USER_ID}" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "'"${USER_ID}"'", "text": "this is explicit violence", "confidence": 0.9}'
```

## Features

- **Real-time Content Analysis**: Analyzes caption/transcript text in real-time
- **Playback Control Actions**: Returns one of four actions:
  - `mute`: Temporarily mute audio
  - `fast_forward`: Fast forward through a scene
  - `skip`: Skip ahead
  - `none`: No action needed, content is acceptable
- **Per-User Preferences**: Each user can configure their own filtering preferences
- **Three Content Categories**: Language/profanity, sexual content, and violence
- **Adjustable Sensitivity**: Low, medium, or high sensitivity for each category
- **Client Resilience**: Health check endpoint allows clients to remain functional if backend is unavailable
- **Cross-Platform**: Designed for browser, mobile, and TV platforms with CORS support

## Installation

1. Clone the repository:
```bash
git clone https://github.com/kthrnbeh/ISweep_backend.git
cd ISweep_backend
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create environment file:
```bash
cp .env.example .env
```

4. Run the application:
```bash
python app.py
```

The server will start on `http://localhost:5000` by default.

## API Documentation

### Health Check

Check if the backend is available.

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "status": "healthy",
  "service": "ISweep Backend",
  "version": "1.0.0"
}
```

### Create User

Create a new user with default filtering preferences.

**Endpoint:** `POST /api/users`

**Request Body:**
```json
{
  "username": "user123"
}
```

**Response:**
```json
{
  "user_id": 1,
  "username": "user123",
  "preferences": {
    "user_id": 1,
    "language_filter": true,
    "sexual_content_filter": true,
    "violence_filter": true,
    "language_sensitivity": "medium",
    "sexual_content_sensitivity": "medium",
    "violence_sensitivity": "medium"
  }
}
```

### Get User Preferences

Retrieve user's filtering preferences.

**Endpoint:** `GET /api/users/{user_id}/preferences`

**Response:**
```json
{
  "user_id": 1,
  "language_filter": true,
  "sexual_content_filter": true,
  "violence_filter": true,
  "language_sensitivity": "medium",
  "sexual_content_sensitivity": "medium",
  "violence_sensitivity": "medium"
}
```

### Update User Preferences

Update user's filtering preferences.

**Endpoint:** `PUT /api/users/{user_id}/preferences`

**Request Body:**
```json
{
  "language_filter": true,
  "sexual_content_filter": false,
  "violence_filter": true,
  "language_sensitivity": "high",
  "sexual_content_sensitivity": "low",
  "violence_sensitivity": "medium"
}
```

**Response:**
```json
{
  "message": "Preferences updated successfully",
  "preferences": {
    "user_id": 1,
    "language_filter": true,
    "sexual_content_filter": false,
    "violence_filter": true,
    "language_sensitivity": "high",
    "sexual_content_sensitivity": "low",
    "violence_sensitivity": "medium"
  }
}
```

**Sensitivity Levels:**
- `low`: Very lenient, requires multiple matches before triggering action
- `medium`: Moderate sensitivity (default)
- `high`: Very strict, single match triggers action

### Analyze Content (Real-time Decision Engine)

Analyze caption or transcript text and receive playback control action.

**Endpoint:** `POST /api/analyze`

**Request Body:**
```json
{
  "user_id": 1,
  "text": "This is the caption or transcript text to analyze"
}
```

**Response:**
```json
{
  "action": "none",
  "text": "This is the caption or transcript text to analyze",
  "user_id": 1
}
```

**Possible Actions:**
- `mute`: Mute audio temporarily
- `fast_forward`: Fast forward through a scene
- `skip`: Skip ahead
- `none`: No action needed

**Note:** For structured decisions (/event), the matched category is chosen deterministically
(sexual > violence > language). The returned action and duration are determined by that
category’s sensitivity setting (low/medium/high).

### Event Decision (Structured Action)

Use the decision engine with structured output and category details.

**Endpoint:** `POST /event`

**Request Body:**
```json
{
  "user_id": "1",
  "text": "Full caption or transcript text",
  "confidence": 0.92
}
```

**Response:**
```json
{
  "action": "mute|skip|fast_forward|none",
  "duration_seconds": 10,
  "matched_category": "language|sexual|violence|null",
  "reason": "sexual content detected; sensitivity=medium; severity=1"
}
```

Rules:
- Priority order: sexual > violence > language
- Action and duration are determined by the matched category’s sensitivity (low/medium/high).
- Most restrictive action wins: skip > fast_forward > mute > none
- If nothing matches: `action` is `none`, `duration_seconds` is `0`, `matched_category` is `null`, `reason` is `"No match"`
- Invalid payloads or unknown users also return the same schema with HTTP 200 and `action` as `none` and `reason` explaining the issue.

## Usage Example

```python
import requests

# Create a user
response = requests.post('http://localhost:5000/api/users', 
                        json={'username': 'john_doe'})
user_id = response.json()['user_id']

# Update preferences to high sensitivity for violence
requests.put(f'http://localhost:5000/api/users/{user_id}/preferences',
            json={'violence_sensitivity': 'high'})

# Analyze content in real-time
response = requests.post('http://localhost:5000/api/analyze',
                        json={
                            'user_id': user_id,
                            'text': 'The character was shot in the scene'
                        })
action = response.json()['action']  # Returns 'fast_forward'

# Client implements the action (fast forward, mute, skip, or do nothing)
```

## Client Integration

### Checking Backend Availability

Clients should check if the backend is available:

```javascript
async function checkBackendHealth() {
  try {
    const response = await fetch('http://localhost:5000/api/health');
    return response.ok;
  } catch (error) {
    return false;
  }
}
```

### Real-time Analysis Flow

1. Client receives caption/transcript text
2. Client sends text to `/api/analyze` endpoint with user_id
3. Backend analyzes text based on user preferences
4. Backend returns action (mute, skip, fast_forward, or none)
5. Client implements the action on the media player
6. If backend is unavailable, client continues normal playback

### Cross-Platform Support

The backend supports CORS and is designed to work with:
- **Browser**: Web applications using fetch/axios
- **Mobile**: iOS and Android apps
- **TV Platforms**: Smart TV applications

## Testing

Run the test suite:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run specific test file
pytest test_api.py

# Run with coverage
pytest --cov=. --cov-report=html
```

## Architecture

```
┌─────────────────┐
│  Client Apps    │
│ (Browser/Mobile)│
└────────┬────────┘
         │ POST /api/analyze
         │ {user_id, text}
         ▼
┌─────────────────────┐
│   Flask REST API    │
│  - CORS enabled     │
│  - Health check     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     ┌──────────────────┐
│ Content Analyzer    │────▶│ User Preferences │
│ - Language filter   │     │  (SQLite DB)     │
│ - Sexual content    │     └──────────────────┘
│ - Violence filter   │
└─────────────────────┘
          │
          ▼
  Action: mute, skip,
  fast_forward, or none
```

## Design Principles

1. **Media Never Modified**: The backend only provides recommendations; clients control playback
2. **Client Resilience**: Clients check backend health and remain functional if unavailable
3. **Real-time Processing**: Low-latency analysis for live captions/transcripts
4. **User Privacy**: Each user controls their own filtering preferences
5. **Platform Agnostic**: RESTful API works across all platforms

## License

MIT
