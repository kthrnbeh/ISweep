# ISweep

## What Is ISweep?

ISweep is a personal content-filtering system.

The goal is simple:

> **Let people choose what they do not want to hear or see, while leaving the original media completely unchanged.**

ISweep controls playback instead of editing the movie, video, audio, or DVD.

For example:

```text
Video says: "What the hell are you doing?"

ISweep detects "hell"

Caption becomes:

"What the ___ are you doing?"

Audio:

MUTE
   ↓
"hell" passes
   ↓
UNMUTE

The Big Goal

ISweep should eventually work with:

YouTube
Streaming websites
HTML5 video
Other websites
Local media
DVDs
Blu-rays
TVs
Other playback devices

YouTube is our first testing environment because it lets us prove the system before expanding it to the rest of the web and physical media.

The Core Idea

The most important idea in ISweep is:

MEDIA EVENT
     ↓
ISWEEP HEARS THE EVENT
     ↓
FILTER THE CONTENT
     ↓
MATCH USER PREFERENCES?
     ↓
YES
     ↓
TAKE ACTION

The action could eventually be:

MUTE
SKIP
FAST FORWARD
NONE

The original media remains untouched.

The Event-Driven Architecture

ISweep should work like a simple JavaScript event listener:

Something happens
      ↓
ISweep detects it
      ↓
A function handles it
      ↓
The function decides what to do
      ↓
An action is performed

The desired caption flow is:

Caption appears
      ↓
onCaption(caption)
      ↓
filterCaption(caption.text)
      ↓
No match?
      ↓
Do nothing

OR

Match found
      ↓
Mask the selected word
      ↓
Request mute
      ↓
Mute during the unwanted word
      ↓
Restore the previous audio state

Conceptually:

function onCaption(caption) {
    const matches = filterCaption(caption.text);

    if (!matches.length) {
        return;
    }

    renderMaskedCaption(caption, matches);

    for (const match of matches) {
        requestMute({
            start: match.start,
            end: match.end
        });
    }
}

This is the architecture we are moving toward.

Important Separation of Responsibilities

ISweep should eventually have clear responsibilities.

1. Content Source

Finds captions, subtitles, speech, or other content.

Examples:

YouTube captions
HTML5 captions
WebVTT
Speech-to-text
Future website adapters

The source should NOT decide what is inappropriate.

It simply reports:

"What the hell"
2. Filter Engine

The filter engine receives text and compares it with the user's selected words/preferences.

Example:

Input:

"What the hell"

Selected words:

["hell", "damn"]

Result:

"hell" matched

The filter engine should not know anything about YouTube.

3. Caption Renderer

The renderer displays the cleaned caption.

Example:

Original:

What the hell are you doing?

ISweep:

What the ___ are you doing?

The renderer should not decide whether a word is inappropriate.

The filter engine makes that decision.

4. Mute Controller

The mute controller handles audio.

Example:

Selected word detected
        ↓
requestMute()
        ↓
YouTube audio muted
        ↓
word passes
        ↓
audio restored

There should be ONE authoritative mute controller.

We should not have several different systems fighting over mute/unmute.

Timing

The first proof-of-concept uses approximately:

0.85 seconds

as a temporary fallback mute duration.

This is NOT the final solution.

The long-term goal is:

Selected word begins
        ↓
MUTE

Selected word ends
        ↓
UNMUTE

If exact word-level timing is available from speech recognition, ISweep should use it.

If exact timing is unavailable, ISweep can temporarily use caption timing as a fallback.

The timing system must remain easy to tune.

Caption Sources

ISweep should eventually support multiple sources.

The architecture should be:

                 YouTube captions
                       │
                 HTML5 captions
                       │
                    WebVTT
                       │
                      STT
                       │
                       ▼
              NORMALIZED EVENT
                       │
                       ▼
                FILTER ENGINE
                       │
              ┌────────┴────────┐
              ▼                 ▼
       Caption Renderer    Mute Controller

This allows us to use YouTube now without permanently designing ISweep around YouTube.

YouTube Is the First Proof of Concept

YouTube is currently our testing environment.

The immediate goal is:

YouTube video playing
       ↓
YouTube caption appears
       ↓
ISweep receives caption
       ↓
Selected word detected
       ↓
Caption displays ___
       ↓
Audio mutes
       ↓
Selected word passes
       ↓
Audio unmutes

Once this works reliably, the same filtering engine can be reused elsewhere.

Universal Web Goal

The long-term browser goal is:

If video is playing in a browser, ISweep should eventually be able to recognize and filter it regardless of the website.

The architecture should therefore separate:

WHERE THE CONTENT COMES FROM

from:

WHAT ISWEEP DOES WITH THE CONTENT

For example:

YouTube
   ↓
YouTube Adapter
   ↓
             ┌────────────────────┐
             │                    │
             │   ISweep Engine    │
             │                    │
             │ Filter             │
             │ Mask               │
             │ Mute               │
             │ Skip               │
             │ Fast Forward       │
             │                    │
             └────────────────────┘
                      ↑
              HTML5 Adapter
                      ↑
               Other Adapter

This is one of the most important long-term design goals.

Current Extension

The Chrome extension lives in:

ISweep_extention/

The spelling extention is intentional because that is the current repository directory name.

Important extension components include:

popup.html
popup.js
popup.css

background.js
plumbing.js

youtube_captions.js

offscreen.js
audio_chunk_processor.js

site_token_bridge.js

options.html
options.js

manifest.json

The extension is responsible for:

User controls
Authentication
Preference synchronization
Caption observation
Audio/STT coordination
Playback control
YouTube integration
Future browser-wide media integration
Current Caption Controls

The popup contains controls for:

Captions
Caption style
Text size
Caption behavior
Caption position

Caption behavior currently includes:

Captions Only

Captions + Selected Word Mute

The selected-word mode is intended to:

Find selected word
       ↓
Display ___
       ↓
Mute audio
       ↓
Restore audio
Current Backend

The backend lives in:

ISweep_backend/

It uses Python and provides the server-side foundation for ISweep.

Major responsibilities include:

User authentication
Preferences
Database access
Content analysis
Caption/transcript processing
Speech-to-text support
API endpoints
Decision logic
Testing

Important files include:

app.py
content_analyzer.py
database.py

The backend also contains the speech-lab work used to evaluate speech recognition and word timing.

Backend Principle

The backend should be the central intelligence when server processing is needed.

The extension should still have enough local information to function when the backend is temporarily unavailable.

The goal is:

Website
   ↓
User Preferences
   ↓
Backend
   ↓
Extension
   ↓
Playback

But also:

Backend unavailable
       ↓
Local cached preferences
       ↓
Extension continues filtering where possible
Preferences

User preferences are extremely important.

The user's selected words/categories should ultimately be the source used by every playback system.

Examples:

Profanity
Custom words
Language
Other user-selected categories

A selected word should not have one definition for YouTube and another definition for another media source.

The filtering rules should be consistent.

Playback Actions

ISweep is intended to control playback rather than modify media.

Possible actions include:

NONE
MUTE
SKIP
FAST_FORWARD

Eventually:

Selected content
      ↓
Decision
      ↓
Playback command
Protecting Manual User Controls

This is extremely important.

If the user manually mutes the video:

User muted video
       ↓
ISweep detects selected word
       ↓
ISweep may already be muted
       ↓
ISweep must NOT unmute the user afterward

ISweep should restore the state that existed before ISweep temporarily changed it.

Example:

Before ISweep:

UNMUTED

ISweep:
MUTE
UNMUTE

Final:

UNMUTED

But:

Before ISweep:

MUTED

ISweep:
MUTE/maintain muted state

Final:

MUTED
STT / Audio Pipeline

The extension has an audio-processing architecture intended to support speech recognition.

Conceptually:

Browser video
      ↓
Tab audio
      ↓
offscreen.js
      ↓
audio_chunk_processor.js
      ↓
background.js
      ↓
Backend STT
      ↓
Word timing
      ↓
ISweep filter engine
      ↓
Mute decision

The important goal is that STT should eventually become another content source feeding the same filtering system.

It should NOT become a completely separate filtering system.

Caption Priority

When synchronized visible captions are available:

Use captions first

because they can provide a fast signal aligned with playback.

STT can act as a backup when captions are unavailable.

Eventually:

Captions ──┐
           ├──> Same Filter Engine
STT ───────┘

Both sources should use the same selected-word rules and mute controller.

Deduplication

Caption systems often report the same caption repeatedly.

ISweep must NOT do this:

caption detected
MUTE

caption detected again
UNMUTE

caption detected again
MUTE

caption detected again
UNMUTE

Instead:

caption detected
      ↓
new event?
      ↓
YES
      ↓
process

same event again?
      ↓
ignore

Deduplication is required for reliable real-time filtering.

Testing

Testing is a major part of the project.

The project contains backend tests and extension tests.

Important things to test include:

Word matching
Preferences
Authentication
Caption processing
STT timing
Mute timing
API behavior
Database behavior

The selected-word system should have tests for:

"hell" matches "hell"

"hell" matches "Hell"

"hello" does not incorrectly match "hell"

No selected words → no mute

Repeated caption → one event

User already muted → remain muted

User not muted → mute then restore

"What the hell"
        ↓
"What the ___"
Current Main Development Problem

The extension has many pieces of the desired system already.

The current challenge is making those pieces work as ONE clean pipeline.

We do not want to keep adding another detector, another timer, or another mute function every time something fails.

Instead:

ONE EVENT
     ↓
ONE FILTER ENGINE
     ↓
ONE MATCH RESULT
     ↓
ONE CAPTION RENDERER
     ↓
ONE MUTE CONTROLLER

The goal is to simplify the existing implementation while preserving working functionality.

Refactoring Rule

Before deleting existing code:

Find out what it does.
Find out who calls it.
Determine whether another component depends on it.
Replace its responsibility with the new architecture.
Run tests.
Only then remove obsolete code.

Do not delete working code simply because it looks old.

Current Development Priority

The immediate priority is:

1. Reliable selected-word detection
2. Reliable caption masking
3. Reliable mute
4. Correct mute timing
5. Correct preference synchronization
6. Deduplication
7. STT integration
8. Universal web architecture

Do not jump ahead to complicated visual AI until the basic audio filtering concept is reliable.

Universal Architecture

The long-term architecture should look approximately like this:

                 CONTENT SOURCES

       YouTube
          │
       HTML5
          │
       WebVTT
          │
        STT
          │
       Local Media
          │
        Future
          │
          ▼
   NORMALIZED MEDIA EVENT
          │
          ▼
   ┌──────────────────────┐
   │   ISWEEP FILTER      │
   │                      │
   │ Selected words       │
   │ Categories           │
   │ User preferences     │
   └──────────┬───────────┘
              │
              ▼
        MATCHED CONTENT
              │
       ┌──────┼───────┐
       ▼      ▼       ▼
      MUTE   SKIP   FAST FORWARD
       │
       ▼
   PLAYBACK CONTROLLER

This is the architecture we should build toward.

Physical Media / DVD

The dvd/ portion of the repository is a separate development area.

It shares the same overall philosophy:

Control playback. Do not modify the original media.

DVD/physical-media development may eventually support:

DVD
Blu-ray
Television
Receiver
Media players
Remote controls
IR
HDMI-CEC
Bluetooth
Network control

The DVD system should not destroy or replace the browser extension.

Likewise, browser-extension development should not unnecessarily modify the DVD system.

They can share compatible concepts such as:

User preferences
Content detection
Decision engine
Playback actions

but each system can have its own implementation where necessary.

Physical Media Vision

The long-term physical-media concept is:

User's own movie
      ↓
ISweep recognizes playback
      ↓
ISweep knows user's preferences
      ↓
Selected content approaches
      ↓
ISweep acts like a remote control
      ↓
Mute / Skip / Fast Forward
      ↓
Original movie remains unchanged

This allows ISweep to eventually support both:

ONLINE MEDIA

and:

USER-OWNED PHYSICAL MEDIA

without requiring ISweep to create altered copies of the media.

What ISweep Should Never Become

ISweep should not require:

Editing the original video
Editing the original audio
Creating modified movie files
Replacing the original media
Permanently altering a user's media

The fundamental principle is:

ISweep controls playback, not the source media.

Development Philosophy
Keep working systems working

Do not rewrite something just because it could be written differently.

Build one layer at a time
Detection
   ↓
Filtering
   ↓
Decision
   ↓
Action
   ↓
Timing
   ↓
Optimization
Prefer simple systems

If a simple function can solve a problem, use the simple function.

One source of truth

User preferences should not be duplicated into separate incompatible systems.

One filtering engine

Different media sources should feed the same filtering logic.

One mute controller

Different detection methods should not create competing mute systems.

Test before expanding

Prove YouTube first.

Then expand to the rest of the web.

Then expand to physical media.

Development Workflow

GitHub main is the source of truth.

When changes are made directly to GitHub:

GitHub
   ↓
VS Code
   ↓
Pull / Sync
   ↓
Local project

If VS Code has local changes that have not been committed, Git may refuse to pull or push.

Before syncing, check:

VS Code
→ Source Control
→ Changes

If there are changes you need to keep, commit or stash them before pulling.

The basic command for getting the latest information is:

git fetch origin

Then the local branch can be synchronized with:

git pull origin main

For the normal workflow:

1. GitHub change is made
2. Open VS Code
3. Pull/Sync
4. Reload Chrome extension
5. Test
6. Commit local changes only when appropriate
Running the Extension

Open:

chrome://extensions

Enable:

Developer mode

Then:

Load unpacked

and select:

ISweep_extention/

After code changes:

chrome://extensions
      ↓
ISweep
      ↓
Reload

Then open a fresh YouTube tab when testing content-script changes.

Running the Backend

The backend lives in:

ISweep_backend/

The project uses Python and a local virtual environment.

The backend should eventually start automatically without requiring VS Code to remain open.

Startup files include:

start_backend.bat
run_backend.bat
run_backend_hidden.ps1
install_startup.bat

The intended architecture is:

Windows startup
      ↓
ISweep backend starts
      ↓
Flask API runs
      ↓
Extension connects

VS Code should not be required for the production-like local experience.

Current Proof-of-Concept Test

The simplest important test is:

Selected word:
hell

Play a video containing:

"What the hell..."

Expected:

Caption:

"What the ___..."

and:

Audio:

NORMAL
  ↓
MUTE
  ↓
"hell" passes
  ↓
UNMUTE

If this works reliably, we have proven the core concept.

Future Roadmap
Phase 1 — Prove YouTube
[ ] Reliable caption event
[ ] Reliable selected-word matching
[ ] Caption masking
[ ] Reliable mute
[ ] Correct mute restoration
[ ] Exact/near-exact word timing
[ ] STT fallback
Phase 2 — Clean Architecture
[ ] Central filter engine
[ ] Central mute controller
[ ] Normalized caption events
[ ] Deduplication
[ ] Remove obsolete duplicate logic
[ ] Strong unit tests
Phase 3 — Universal Web
[ ] HTML5 video detection
[ ] WebVTT support
[ ] Additional website adapters
[ ] Browser-wide media event architecture
[ ] Common filtering engine
Phase 4 — More Actions
[ ] Mute
[ ] Skip
[ ] Fast Forward
[ ] Future playback actions
Phase 5 — Better Intelligence
[ ] Better STT
[ ] Better word timing
[ ] Scene recognition
[ ] Visual filtering
[ ] Content classification
Phase 6 — Physical Media
[ ] DVD playback control
[ ] Remote-control integration
[ ] TV control
[ ] Playback synchronization
[ ] Physical-media content detection
Final Vision

The ultimate ISweep system should look like this:

                 USER
                  │
                  ▼
          ISWEEP PREFERENCES
                  │
                  ▼
          ┌───────────────┐
          │ ISWEEP ENGINE │
          └───────┬───────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
      ONLINE    LOCAL      DVD
      MEDIA     MEDIA     MEDIA
        │         │         │
        └─────────┼─────────┘
                  ▼
            CONTENT EVENT
                  │
                  ▼
             FILTER MATCH
                  │
                  ▼
              DECISION
                  │
          ┌───────┼────────┐
          ▼       ▼        ▼
        MUTE     SKIP    FAST-FORWARD
          │       │        │
          └───────┼────────┘
                  ▼
             PLAYBACK

The user chooses their boundaries.

ISweep detects the content.

ISweep makes the decision.

ISweep controls playback.

The original media stays untouched.

The Most Important Rule

When adding new functionality, always ask:

Can this become another input to the same ISweep filtering and decision system instead of becoming another separate system?

If yes, integrate it.

If no, keep it isolated.

The goal is not to keep adding code.

The goal is to build one reliable ISweep engine that can eventually control many different kinds of media.


### One thing I would change from the old README

The old README describes an older architecture where the extension sends everything through `/event` and waits for a backend decision. Our newer direction is more powerful:

```text
CONTENT SOURCE
      ↓
NORMALIZED EVENT
      ↓
FILTER ENGINE
      ↓
ACTION

That lets us eventually use local filtering, backend filtering, captions, and STT without making each one a separate system.
And I would keep the DVD section in the repository, but not make it the thing driving the browser architecture. It can grow alongside ISweep without fighting the extension.