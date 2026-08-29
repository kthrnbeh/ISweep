# ISweep DVD Hardware Bridge

## Purpose

ISweep DVD is intended to control playback without modifying the DVD, Blu-ray, movie file, or television program itself.

The software therefore needs three separate abilities:

1. **Sense** what is being played.
2. **Decide** whether the current or upcoming content matches the user's saved ISweep preferences.
3. **Control** the existing television / receiver / DVD player using commands that the device already supports.

The current repository has a working Decision Engine and a simulated remote. It does **not yet control real DVD/TV hardware**.

---

## Current Status

### Working now

- ISweep DVD Decision Engine
- Language whole-word matching
- Shared-preference bridge for the ISweep website/backend
- Simulated remote commands
- Automated tests

### Not implemented yet

- Real DVD audio/video input
- Real subtitle/caption input from a DVD player
- Real-time playback synchronization
- Infrared transmitter control
- HDMI-CEC control
- Smart-TV control
- Real mute/unmute timing
- Real skip / fast-forward timing

The empty controller modules in `dvd/control/` are placeholders for these future hardware implementations.

---

# Target Physical Architecture

A standalone DVD player version of ISweep can be thought of as four pieces:

```text
                       ISWEEP WEBSITE
                         Preferences
                              |
                              v
                     ISweep DVD Computer
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
     MEDIA SENSOR       DECISION ENGINE      REMOTE CONTROL
   (ears + eyes)             (brain)             (hands)
          |                   |                   |
          +-------------------+-------------------+
                              |
                              v
                    TV / Receiver / DVD Player
```

The DVD itself remains unchanged.

---

# 1. Media Sensor — How ISweep Knows What Is Playing

For a normal standalone DVD player, ISweep needs a way to observe the movie while it is playing.

Possible inputs include:

## Audio capture

Preferred early prototype options:

- DVD player's analog/RCA audio output into a USB audio capture interface
- Optical audio output through a compatible capture interface
- HDMI audio capture where the equipment permits it
- PC system-audio loopback when the DVD is played on the computer

The captured audio can be sent to speech recognition and language detection.

## Video capture

Possible later options:

- HDMI capture where supported
- Analog/composite/component capture from compatible players
- PC playback capture when the disc is played on the computer

Video capture would feed future scene and visual-category AI.

### Important HDMI limitation

Commercial DVD/Blu-ray players may use HDCP on HDMI output. Ordinary capture cards may refuse to capture protected HDMI video. ISweep must not rely on an HDMI-capture design until the exact player/capture hardware has been tested.

For the first physical prototype, audio capture and remote control can be tested independently of protected HDMI video.

---

# 2. Decision Engine — The Brain

This part already exists in the project.

```text
Detected dialogue / event
          |
          v
Saved ISweep preferences
          |
          v
Decision Engine
          |
          +--> ALLOW
          +--> MUTE
          +--> future SKIP
          +--> future FAST_FORWARD
```

The existing webpage should remain the single source of truth for the user's preferences. The extension and DVD system should consume the same account settings rather than maintaining separate filter lists.

---

# 3. Remote Control — How ISweep Presses the Buttons

The current `SimulatedRemote` only prints commands. A physical controller must replace that simulation.

## Recommended first physical controller: Infrared (IR)

IR is the most practical first target because it mimics the normal remote control and works with many televisions, receivers, and DVD players.

A future IR controller would learn or store the same remote codes as the user's existing remotes.

Example:

```text
ISweep decides MUTE
        |
        v
USB / network IR transmitter
        |
        v
TV receives normal MUTE remote code
```

For skipping a scene:

```text
ISweep decides SKIP
        |
        v
IR transmitter sends FAST FORWARD / SKIP / PLAY
        |
        v
DVD player performs the same action as if the user pressed the remote
```

## Other controller options

Later adapters may include:

- HDMI-CEC
- Smart-TV APIs
- Network-controlled receivers
- Bluetooth controls

All adapters should ultimately implement the same ISweep command vocabulary already defined in `dvd/control/commands.py`.

---

# 4. Synchronization — Knowing WHEN to Act

This is a separate problem from recognizing content.

ISweep must know when to send MUTE and when to send UNMUTE, or when a scene begins and ends.

Possible synchronization sources include:

- Known timestamps for a specific movie/disc version
- Subtitle timing
- Closed-caption timing
- Audio fingerprint synchronization
- Live speech recognition
- Hybrid synchronization using more than one source

## Profanity timing challenge

If speech-to-text recognizes a word only after the viewer has already heard it, a mute command will be late.

For accurate language filtering, the long-term design should prefer information that gives ISweep some look-ahead, such as:

1. known event timestamps,
2. subtitle/caption timing,
3. pre-analysis of a title,
4. or another synchronized prediction source.

Live speech recognition is still useful as a fallback and for learning, but by itself it may not always react before the first sound of a word.

---

# Recommended Prototype Path

## Prototype A — Real remote control, simulated detection

Goal: prove the computer can physically control the user's equipment.

```text
Computer
   |
   | manual test command
   v
IR transmitter
   |
   +--> TV MUTE / UNMUTE
   +--> DVD PLAY / PAUSE / FAST FORWARD
```

This is the first real hardware milestone.

## Prototype B — Real audio input + real remote

```text
DVD Player
   |
   | audio output
   v
USB audio capture
   |
   v
Speech / content detector
   |
   v
Decision Engine
   |
   v
IR remote controller
```

## Prototype C — Synchronization and look-ahead

Add movie identification, subtitle/timestamp information, or audio fingerprint synchronization so commands can occur before unwanted content reaches the viewer.

## Prototype D — Visual AI

Add video input and scene recognition for the visual categories already represented on the ISweep Filters page.

---

# What We Should Build Next

Before adding more AI, the next physical-development task should be a **real control adapter** that can replace `SimulatedRemote`.

The recommended first adapter is IR because it most closely matches the project's core principle: ISweep acts like an automated person pressing the user's existing remote buttons.

Once a real IR MUTE / UNMUTE command works on one television, we can add DVD-player PLAY / PAUSE / FAST FORWARD commands and then connect detection to those same commands.

This keeps the extension, website, Decision Engine, and physical-DVD work separated enough that one component can be improved without breaking the others.
