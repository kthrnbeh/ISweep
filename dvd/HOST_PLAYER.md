# ISweep Host Player

## Primary DVD Mode

The preferred software-first architecture is for **ISweep itself to own playback**.

Instead of trying to remote-control every possible standalone DVD player, ISweep can run on a computer connected to the television and act as the playback application.

```text
DVD disc
   |
   v
Computer optical drive
   |
   v
ISweep Host Player
   |
   +--> shared account preferences
   +--> captions/audio/AI detection
   +--> exact playback clock
   +--> mute / unmute
   +--> pause / play
   +--> seek / skip
   |
   v
HDMI / display output
   |
   v
TV
```

The disc and movie are not modified. ISweep changes only the live playback state.

---

# Why this is the primary architecture

When ISweep owns playback, it has direct access to the things filtering needs most:

- current playback position
- mute state
- play/pause state
- seek position
- subtitle/caption tracks when exposed by the media engine
- audio/video frames when exposed by the media engine

That makes accurate synchronization much easier than watching an unrelated DVD player from the outside.

It also eliminates the need for a purchased universal remote for the normal supported setup.

---

# First real player implementation

The first real Windows playback adapter is now in:

```text
dvd/playback/vlc.py
```

and the first ISweep desktop player window is:

```text
dvd/player_app.py
```

ISweep owns the UI and filtering architecture. For this prototype, **libVLC is the underlying media-decoding engine**. This is the same kind of separation used by many applications: ISweep supplies the product behavior while a media engine handles codecs, timing, audio output, and video rendering.

The VLC dependency is intentionally optional. The website, Chrome extension, Flask backend, Decision Engine, and normal tests do not import or require VLC.

## Prototype setup on Windows

Install the 64-bit VLC desktop runtime on the ISweep computer, then in the active ISweep virtual environment run:

```powershell
pip install -r dvd/requirements-player.txt
```

Pull the current branch and run all tests:

```powershell
git pull --ff-only origin dvd-shared-preferences-sync
python -m pytest dvd/tests -v
```

Launch the first real ISweep Player:

```powershell
python -m dvd.player_app
```

The window contains:

- Open Video
- Load DVD
- Play
- Pause
- Stop
- -15 seconds
- +15 seconds
- Mute
- Unmute
- live playback position / duration

A normal video file is the easiest first physical test. Once that works, insert a supported DVD-Video disc and press **Load DVD**.

For a direct startup source, the prototype also accepts:

```powershell
python -m dvd.player_app --file "C:\path\to\video.mp4"
python -m dvd.player_app --dvd D:\
```

---

# Automatic disc flow

The intended user experience is:

```text
User inserts DVD
      |
      v
ISweep detects optical media
      |
      v
Recognizes DVD-Video structure
      |
      v
Creates playback session
      |
      +--> loads saved ISweep preferences
      +--> identifies title/disc where possible
      +--> starts synchronization/detection
      |
      v
User presses Play
      |
      v
ISweep filters live playback according to that account
```

`dvd/playback/disc.py` contains the first Windows optical-drive/DVD-Video detection foundation for this flow.

---

# Playback adapter boundary

The Decision Engine does not depend directly on VLC.

Every media engine implements the same `PlaybackController` contract:

```text
load(source)
play()
pause()
stop()
mute()
unmute()
seek_relative(seconds)
get_state()
```

The real `VLCPlaybackController` and the test-only `SimulatedPlaybackController` both sit behind this contract.

That means a later packaged/native media engine can replace libVLC without rewriting the ISweep filters, user preferences, AI, or synchronization system.

`ISweepHostPlayback` converts Decision Engine MUTE/ALLOW results into deterministic player mute/unmute calls. Because ISweep owns the player, it can distinguish sound that ISweep muted from sound the user muted manually.

---

# Important DVD limitation

ISweep does not decrypt, rip, copy, or modify discs.

Commercial DVD playback depends on the capabilities legally available through the installed playback/media engine and operating system. ISweep should not implement copy-protection circumvention.

The first playable prototype can be validated using:

- ordinary video files,
- home-authored DVD-Video,
- unencrypted DVD-Video,
- or other media that the installed engine can lawfully open.

---

# Roku and smart-TV control

Roku-style network discovery is still useful, but it is **Mode B**, not the core DVD path.

## Mode A — Host Player (preferred)

```text
DVD -> ISweep computer -> TV
```

ISweep directly controls the movie.

## Mode B — Companion / existing equipment

```text
Standalone player -> TV

ISweep phone/computer
       |
       +--> Wi-Fi API
       +--> Bluetooth capability
       +--> HDMI-CEC
       +--> optional legacy IR
```

Mode B extends compatibility when users want to keep an existing standalone player.

---

# Next implementation milestones

1. **Disc detection** — detect insertion/removal and standard `VIDEO_TS` structure. (foundation added)
2. **Playback abstraction** — one controller API for play/pause/mute/seek/state. (added)
3. **Simulated host player tests** — prove decisions control playback state. (added)
4. **Real media-engine adapter** — libVLC adapter added.
5. **Real ISweep Player window** — Windows desktop player with video surface and controls added.
6. **Auto-session service** — when a DVD appears, create an ISweep playback session and load account preferences automatically.
7. **Timeline synchronization** — feed the player's real clock into filtering instead of artificial timestamps.
8. **Caption/audio detection** — feed detected text/events into the existing Decision Engine before output where possible.
9. **Filtering integration** — make `ISweepHostPlayback` automatically mute/unmute the real player from shared `/preferences` decisions.
10. **Visual AI** — classify frames/scenes against the same saved visual preferences.
11. **Phone companion** — remote UI and optional microphone/camera helper over the local network.

This architecture keeps the website, browser extension, DVD player, and future phone companion connected through shared preferences while allowing each playback environment to use the control method best suited to it.
