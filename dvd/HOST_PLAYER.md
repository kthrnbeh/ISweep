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

`dvd/playback/disc.py` now contains the first Windows optical-drive/DVD-Video detection foundation for this flow.

---

# Playback adapter boundary

The Decision Engine should never depend directly on one media framework.

Instead, every media engine should implement the same `PlaybackController` contract:

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

This allows us to begin with a simulated player and later plug in a real Windows-capable media engine without rewriting filters, preferences, AI, or synchronization.

`ISweepHostPlayback` already converts Decision Engine MUTE/ALLOW results into deterministic player mute/unmute calls.

---

# Roku and smart-TV control

Roku-style network discovery is still useful, but it becomes **Mode B**, not the core DVD path.

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

# What still must be selected

The new playback layer is deliberately independent of the final decoding engine.

A real DVD player app still needs a media engine capable of presenting DVD content on the user's operating system. We should not write video/audio codecs from scratch; ISweep should own the product/UI/filtering logic while using a supported media-decoding layer underneath it.

For commercial encrypted DVDs, playback also depends on what licensed or legally available DVD support exists on the user's system. ISweep should not implement copy-protection circumvention. The first playable prototype can begin with media the operating system/media engine can lawfully open, including unencrypted/home-authored DVD-Video.

---

# Next implementation milestones

1. **Disc detection** — detect insertion/removal and standard `VIDEO_TS` structure. (foundation added)
2. **Playback abstraction** — one controller API for play/pause/mute/seek/state. (added)
3. **Simulated host player tests** — prove decisions control playback state. (added)
4. **Real media-engine adapter** — load/play a supported DVD or test media through the same controller interface.
5. **Auto-session service** — when a DVD appears, create an ISweep playback session and load account preferences automatically.
6. **Timeline synchronization** — use the player's actual clock instead of artificial timestamps.
7. **Caption/audio detection** — feed detected text/events into the existing Decision Engine.
8. **Visual AI** — classify frames/scenes against the same saved visual preferences.
9. **Phone companion** — remote UI and optional microphone/camera helper over the local network.

This architecture keeps the website, browser extension, DVD player, and future phone companion connected through shared preferences while allowing each playback environment to use the control method best suited to it.
