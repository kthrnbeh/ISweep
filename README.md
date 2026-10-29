ISweep (Monorepo)

ISweep is an AI-driven media content filtering system that helps users watch content with their own boundaries — without editing the original media.

ISweep observes captions/transcripts in real time and sends playback-control decisions to the client (extension/app), limited to:

mute (temporarily mute audio)

unmute (restore the viewer's previous audio state)

none (do nothing)

The original video/audio file is never modified. Playback control only.

What’s in this repo
ISweep/
├─ ISweep_backend/     # API + preferences + decision engine (Flask/FastAPI-style backend)
├─ ISweep_frontend/    # Website UI prototype (static HTML/Tailwind/JS)
└─ ISweep_extention/   # Chrome extension (controls playback, reads settings, applies filters)


Frontend = website UX: create account, choose plan, set filters, parental PIN, etc. (currently a static prototype using LocalStorage) 

README

Extension = runs in the browser and controls the current player's audio state (mute/unmute) based on settings and backend decisions

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
  "action": "mute | unmute | none",
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

Use one canonical development website origin for extension integration:

http://127.0.0.1:5500/docs/

Open Filter.html, Account.html, and Settings.html from that same origin. Do not switch between port 5501, localhost, and GitHub Pages while testing one session; each origin has separate browser storage. The extension manifest includes the canonical 127.0.0.1:5500 origin and its /docs/* pages.

This is static HTML/JS/Tailwind.

Recommended: VS Code → Live Server

Right-click `docs/index.html` → Open with Live Server

You’ll get something like:

http://127.0.0.1:5500/docs/

Frontend details live here: `docs/`

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


Expected backend URL:

http://127.0.0.1:5000

Quick HOW TO RUN LOCALLY
- Backend: in ISweep_backend/ `python app.py` (uses SQLite file isweep.db and .env SECRET_KEY/DATABASE_PATH if set)
- Frontend: open `docs/index.html` with Live Server → http://127.0.0.1:5500/docs/
- Extension: chrome://extensions → Load unpacked → `ISweep_extention/`; set backend URL to http://127.0.0.1:5000 in Options; login via popup with the same development account as the website.
- For testing, set `DATABASE_PATH` to a new temporary SQLite path before starting Flask. Never use the production database for experiments.

End-to-end smoke test checklist
- Backend up at http://127.0.0.1:5000 and /health returns healthy.
- Frontend signup/login works; preferences save via PUT /preferences and reload via GET /preferences.
- Extension configured with backend URL; popup login succeeds and stores token/user id.
- Open YouTube with captions on; console shows [ISWEEP][YT] caption captured → [ISWEEP][BG] calling /event → [ISWEEP][BG] decision received → [ISWEEP][YT] applying action.
- Observe mute/unmute applied for matching captions; no console errors.

3) Chrome Extension

Open Chrome → chrome://extensions/

Enable Developer mode

Click Load unpacked

Select the ISweep_extention/ folder

Extension details live here: ISweep_extention/README.md 

README

The 3 key “connection settings” you need

To make everything actually talk to each other, you need these to be consistent:

FRONTEND URL (where the website is running)

Example: http://127.0.0.1:5500/ISweep_frontend/docs/

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


ISweep Master Development Roadmap
=================================

Mission
-------

ISweep is a universal video-filtering system that identifies user-selected
words and automatically mutes and unmutes playback at precisely the correct
moments.

Golden Rule
-----------

ISweep must never modify, edit, cut, trim, skip, shorten, replace, or remove
original video or audio content. Filtering must operate like a precision
remote control using mute/unmute only.

Development Roadmap
-------------------

1. **Learning History Cleanup** — Archive, exclude, restore, and manage
   learning records.
2. **Whisper/STT Readiness** — Validate speech recognition, audio capture, and
   word-level timestamps.
3. **Unified Detection Engine** — Combine captions, speech recognition, and
   verified corrections.
4. **AI Preview Engine** — Analyze accessible captions and audio before
   playback or ahead of the viewer, using full preview, rolling preview, or
   live fallback.
5. **Precision Remote Controller** — Improve mute/unmute timing, playback
   synchronization, and manual mute protection.
6. **Universal Video Compatibility** — Expand to supported video players and
   streaming platforms.
7. **Adaptive AI Learning** — Improve accuracy across unfamiliar videos using
   validated feedback.

AI Preview Rules
----------------

- Full-video analysis is preferred when technically and legally accessible.
- Rolling look-ahead is the next option.
- Live detection is the fallback.
- Optional initial buffering is acceptable if it preserves all content.
- Never assume that browser buffering provides access to future audio.
- Never claim that live STT can mute words before recognition without
  sufficient look-ahead.

Development Standards
---------------------

- Preserve working features.
- Use the existing Flask backend and Chrome extension architecture.
- Test changes with pytest, JavaScript tests, and real Chrome playback.
- Protect authentication, preferences, and database integrity.
- Keep inaccurate learning data out of correction reuse.
- Obtain approval before new database schema changes, permanent data deletion,
  or major playback architecture changes.

Current Project Status
----------------------

- **Learning Engine phases A–D:** Implemented in development.
- **Correction editing/removal improvements:** Implemented; live Chrome
  verification pending.
- **Learning History Cleanup:** Approved, implementation pending for the
  remaining cleanup workflow; reversible review API and popup controls are
  implemented in development.
- **Whisper/STT audit:** Complete; STT not yet operational.
- **Unified Detection Engine:** Planned.
- **AI Preview Engine:** Planned.

Keep this status list easy to update as milestones progress. Automated tests
do not replace real Chrome playback verification.
