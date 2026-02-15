ISweep (Monorepo)

ISweep is an AI-driven media content filtering system that helps users watch content with their own boundaries — without editing the original media.

ISweep observes captions/transcripts in real time and sends playback-control decisions to the client (extension/app), such as:

mute (temporarily mute audio)

skip (jump forward past a scene)

fast_forward (speed through a segment)

none (do nothing)

The original video/audio file is never modified. Playback control only.

What’s in this repo
ISweep/
├─ ISweep_backend/     # API + preferences + decision engine (Flask/FastAPI-style backend)
├─ ISweep_frontend/    # Website UI prototype (static HTML/Tailwind/JS)
└─ ISweep_extension/   # Chrome extension (controls playback, reads settings, applies filters)


Frontend = website UX: create account, choose plan, set filters, parental PIN, etc. (currently a static prototype using LocalStorage) 

README

Extension = runs in the browser and actually controls playback (mute/skip/ff) based on settings and backend decisions 

README

Backend = stores user preferences + makes deterministic decisions from caption/transcript events 

README

End-to-end user flow (the goal)

User visits the ISweep website

Creates an account (email + profile)

Picks a plan (Free / Flexible / Ownership)

Gets an “Enable Code” (or signs into the extension)

Installs the ISweep extension

When the user plays anything:

the extension observes captions/transcript text

sends events to the backend

receives a decision: mute | skip | fast_forward | none

applies the action seamlessly in the player without editing the content

Future: same idea across mobile, TV, streaming devices, etc. (client app changes, backend stays the brain).

How “working together” should be wired
Source of truth (event → decision)

The backend is the decision engine. Clients (extension/apps) send text and receive an action.

Request (client → backend)
POST /event

{
  "user_id": "string",
  "text": "caption or transcript text",
  "confidence": 0.0
}


Response (backend → client)

{
  "action": "mute | skip | fast_forward | none",
  "duration_seconds": 4,
  "matched_category": "language | sexual | violence | null",
  "reason": "short explanation"
}

Preferences (website → backend → clients)

Website saves user preferences (filters, actions, sensitivity, blocked words, parental lock)

Backend stores them per user

Extension fetches/syncs them and uses them in real time

Important: if backend is down, the extension should still have a “local fallback” ruleset so filtering still works.

Local dev: run all 3 parts
1) Frontend (website prototype)

This is static HTML/JS/Tailwind.

Recommended: VS Code → Live Server

Right-click ISweep_frontend/index.html → Open with Live Server

You’ll get something like:

http://127.0.0.1:5500/...

(Your screenshots show 127.0.0.1:5500/docs/Settings.html which means you’re close — the path just needs to match your actual folder structure.)

Frontend details live here: ISweep_frontend/README.md 

README

2) Backend API

From inside ISweep_backend/:

Create/activate a virtual environment

Install dependencies

pip install -r requirements.txt
pip install -r requirements-dev.txt


Backend dependency notes here: ISweep_backend/README.md 

README

Run the server (example patterns)

If your entrypoint is app.py:

python app.py


Or if it’s Flask:

flask run


Expected: backend running at something like:

http://127.0.0.1:8000 or http://127.0.0.1:5000

3) Chrome Extension

Open Chrome → chrome://extensions/

Enable Developer mode

Click Load unpacked

Select the ISweep_extension/ folder

Extension details live here: ISweep_extension/README.md 

README

The 3 key “connection settings” you need

To make everything actually talk to each other, you need these to be consistent:

FRONTEND URL (where the website is running)

Example: http://127.0.0.1:5500

BACKEND URL (where the API is running)

Example: http://127.0.0.1:8000

User identity

A real user_id or token that the extension can send to the backend on every /event

If any one of these is wrong, you’ll see things like:

settings page works but extension does nothing

extension loads but can’t reach backend

backend works but has no preferences for that user

Why your Account page shows “connection refused” sometimes

In your screenshot you have:

127.0.0.1:5500/docs/Settings.html working

127.0.0.1:5500/docs/Account.html failing with ERR_CONNECTION_REFUSED

That typically means Live Server stopped or the page path doesn’t exist where you think it does.

Quick checks:

In VS Code, confirm Live Server is running (bottom bar should show it)

Confirm the file is really located at: .../docs/Account.html (or adjust the link to match the real folder)

Try opening index.html first via Live Server, then navigate using your site’s nav links

Production direction (how this becomes “real”)

Right now:

Frontend stores settings in LocalStorage (prototype)

Extension stores auth state in chrome.storage.local (good foundation) 

README

Backend exists to become the central preference + decision source

Next wiring steps (the “make it real” checklist):

Backend:

Add endpoints for login/signup (or token exchange)

Add endpoints for get/update preferences

Implement /event decision logic using stored preferences + word packs

Frontend:

Replace LocalStorage-only settings with API calls to backend

Extension:

On sign-in, store token/user_id

Fetch preferences from backend

On captions/transcripts, call /event and apply action immediately
