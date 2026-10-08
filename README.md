# ISweep

ISweep is a content-filtering system designed to let users control what they hear and see while watching online video.

The long-term goal is to make ISweep work across the web — YouTube, other video websites, and eventually any video playing inside a supported browser.

ISweep does not edit or permanently alter the original video.

---

## Current Goal

We are proving the system on YouTube first.

The immediate goal is:

1. YouTube plays normally.
2. ISweep receives the video's captions/transcript.
3. ISweep checks the caption against the user's selected filter words.
4. If a selected word is detected:
   - the word is hidden/masked in the ISweep caption display
   - the video is temporarily muted
5. When the selected word passes:
   - the video returns to its previous audio state.

Example:

    YouTube caption:
    "What the hell are you doing?"

    ISweep:
    "What the ___ are you doing?"

    Audio:
    normal → MUTED → normal

---

## Core Design

The important idea behind ISweep is event-driven filtering.

Conceptually:

    caption arrives
          ↓
    onCaption(caption)
          ↓
    filterCaption(caption.text)
          ↓
    selected words found?
       /          \
     no            yes
     ↓              ↓
    continue     mask words
                    ↓
              requestMute()
                    ↓
              word passes
                    ↓
              restore audio

The filtering system should respond to the caption event rather than constantly guessing when a word might be spoken.

---

## Main Components

### Chrome Extension

The extension runs inside the browser and controls the user experience.

Important files include:

- `ISweep_extention/popup.html`
- `ISweep_extention/popup.js`
- `ISweep_extention/popup.css`
- `ISweep_extention/youtube_captions.js`
- `ISweep_extention/background.js`
- `ISweep_extention/offscreen.js`
- `ISweep_extention/audio_chunk_processor.js`
- `ISweep_extention/plumbing.js`
- `ISweep_extention/site_token_bridge.js`

### Backend

The Flask backend handles processing that should not happen entirely inside the browser.

Important files:

- `ISweep_backend/app.py`
- `ISweep_backend/content_analyzer.py`
- `ISweep_backend/database.py`

The backend provides APIs for caption/transcript processing and persistent application data.

### Repository structure

- `docs/` — hosted/static Filter, account, settings, and help pages.
- `ISweep_backend/` — Flask API, preference persistence, caption/STT processing, and tests.
- `ISweep_extention/` — Chrome extension source, popup, background/offscreen audio plumbing, and tests.
- `dvd/` — separate DVD playback/control system; it is intentionally outside the browser-extension work.

The repository does not contain an `ISweep_frontend/` directory. Local website links
use `http://127.0.0.1:5500/docs/` or `http://localhost:5500/docs/`.

---

## Filtering

ISweep has a user-selected list of words that should be filtered.

The filter system should support:

- predefined words
- custom words
- selected/unselected words
- different categories
- caption masking
- audio muting

The user's preferences are intended to be the single source of truth.

The normalized selected-word contract is:

```json
{
  "categories": {
    "language": { "items": [] },
    "intimacy": { "items": [] },
    "violence": { "items": [] },
    "substances": { "items": [] },
    "horror": { "items": [] }
  },
  "blocklist": { "items": [] }
}
```

`blocklist.items` is the authoritative selected-word list. The site uses the
canonical `isweep_auth_token` for new bridge traffic while migrating compatible
legacy keys (`isweep-token` and `auth-state`) when present. Tokens must not be
printed in diagnostics; sync diagnostics should report only account identity,
preference source/schema, word count/preview, result, and failure reason.

---

## Captions

ISweep can display its own caption overlay instead of relying entirely on YouTube's visual captions.

The current caption controls include:

- captions on/off
- caption style
- text size
- caption behavior
- caption position

Current caption styles include:

- dark/transparent background with white text
- white background with black text

The caption overlay should eventually become the primary visual filtering layer.

Caption recognition is not guaranteed to be exact. Music, noise, accents,
overlapping speakers, recognition delay, missing word timestamps, and caption
source differences can affect masking and mute alignment. Visible YouTube
captions currently use a configurable caption-window fallback when exact word
timing is unavailable; timed STT data uses its source-video timeline.

---

## Selected Word Muting

The desired behavior is temporary remote-control-style muting.

ISweep should NOT:

- edit the video
- permanently modify audio
- create a new video
- clip the audio file

Instead:

    Detect selected word
          ↓
    Mute YouTube
          ↓
    Wait for word to pass
          ↓
    Restore previous audio state

The previous audio state is important.

If the user already muted YouTube before ISweep detected the word, ISweep must not automatically unmute the video afterward.

---

## Caption Processing

The ideal filtering function is conceptually:

```javascript
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
