# ISweep Backend

Flask API that stores users + preferences and returns deterministic playback decisions (mute/skip/fast_forward/none) based on incoming caption text.

## How to run locally
1) Install deps (inside `ISweep_backend/`):
```
python -m venv .venv
./.venv/Scripts/activate
pip install -r requirements.txt
```
2) Configure env (copy and edit):
```
cp .env.example .env
```
Key vars:
- `SECRET_KEY`: signing/CSRF secret (dev default is fine)
- `DATABASE_PATH`: sqlite file path (defaults to `isweep.db`)
3) Start the server:
```
python app.py
```
Default: http://127.0.0.1:5000 (CORS open for http://127.0.0.1:5500, http://localhost:5500, and the extension during dev).

## Auth & tokens (dev)
- Passwords hashed with Werkzeug.
- Tokens are random strings stored in sqlite (`auth_tokens`) with a 7‑day TTL. This is **not** production-grade—rotate/expire aggressively or replace with JWT in real deployments.

## Endpoints
- `GET /health` (alias `/api/health`): service status.
- `POST /auth/signup` `{email, password}` → `{token, user_id}`
- `POST /auth/login` `{email, password}` → `{token, user_id}`
- `GET /preferences` (Bearer token) → preferences JSON
- `PUT /preferences` (Bearer token, JSON body) → saved preferences JSON
- `POST /event` (Bearer token, `{text}`) → `{action, duration_seconds, matched_category, reason}`

## Preferences shape
```
{
  "enabled": true,
  "categories": {
    "language": {"enabled": true, "action": "mute", "duration": 4},
    "sexual":   {"enabled": true, "action": "skip", "duration": 12},
    "violence": {"enabled": true, "action": "fast_forward", "duration": 8}
  },
  "sensitivity": 0.7
}
```
- Action defaults: mute=4s, skip=12s, fast_forward=8s.
- Priority order: sexual > violence > language.
- If `enabled` is false or category is disabled, the response is `none`.

## Decision logic (POST /event)
1) If filtering disabled → `none`.
2) Compute severities using profanity + keyword regexes.
3) Threshold uses sensitivity (numeric 0-1 or low/medium/high mapping).
4) First matching category (sexual > violence > language) drives the action/duration.

## Notes
- Legacy `/api/users` remains but synthesizes email+password for compatibility.
- Database auto-adds missing columns on start (best-effort `ALTER TABLE`).
- CORS is wide open for local dev; tighten before production.
