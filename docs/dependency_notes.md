# ISweep Dependency and License Notes

## Core product boundary
ISweep must never edit or redistribute video/audio.
ISweep only:
- captures local playback audio for analysis
- generates temporary clean captions
- controls playback (mute/skip/fast-forward)
- stores local analysis cache needed for playback

## Current libraries in use

### Backend required
- Flask (BSD-3-Clause): API server.
- Flask-CORS (MIT): local extension/frontend access.
- better-profanity (MIT): profanity matching for text decisions.
- python-dotenv (BSD-3-Clause): environment loading.

### Backend optional
- faster-whisper (MIT, optional): local speech-to-text plus word timestamps for audio chunks.
  - Optional dependency only; backend must run without it.
  - Commercial distribution impact: generally permissive (MIT), but model files and runtime packaging should still be reviewed separately.

### Browser/extension built-ins
- MediaStream/captureStream, AudioContext, AudioWorkletNode, fetch, chrome.runtime messaging.
- These are platform APIs, not third-party packages.

## Recommended library path (minimal risk)

### Phase 1 (current preferred path)
- Keep browser built-ins for capture and streaming.
- Keep backend STT optional via faster-whisper when ISWEEP_STT_ENABLED=1.
- Keep deterministic fallback transcript path when STT is unavailable.

### Phase 2 (only if timing precision gap is observed)
- Add one alignment-focused optional dependency:
  - whisper-timestamped (AGPL-3.0): stronger timestamps, but AGPL obligations are likely incompatible with closed/commercial distribution.
  - WhisperX (BSD-2-Clause project, but typically pulls PyTorch and may rely on optional models/tools with separate licenses): use only after full dependency tree review.
- Cache only local timing artifacts required for playback decisions.

## Optional tools not enabled by default
- ffmpeg for conversion/resampling:
  - Risk: binaries/builds can be LGPL or GPL depending on how compiled.
  - Policy: do not bundle GPL ffmpeg in distributed builds without legal review.
- VAD libraries (silero-vad, webrtcvad): only add if chunk quality or latency requires it.

## Copyright and data safety rules
- Do not copy YouTube captions or third-party captions into a reusable database.
- Do not redistribute full copyrighted transcripts.
- Cache only local analysis data needed for playback control.
- Keep user preferences separate from third-party source material.

## What remains custom by design
- Extension-side chunking, WAV encoding, and playback marker scheduler remain custom to preserve strict control over mute/skip behavior and to avoid over-coupling to heavy media frameworks.
- Backend marker shaping and cache fingerprint logic remain custom because they encode product-specific policy and timing behavior.
