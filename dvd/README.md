# ISweep DVD

## Project Status

**Early Development / Research Stage**

ISweep DVD is currently at the beginning of development. The hardware, software architecture, supported DVD players, AI models, and control methods are still being researched and tested.

This README will evolve as the project develops.

---

# What Is ISweep DVD?

ISweep DVD is a content-preference playback assistant designed to work with DVDs, Blu-rays, televisions, media players, and similar playback systems.

The goal of ISweep DVD is **not to edit, alter, copy, or permanently change the movie, television show, DVD, Blu-ray, or other media being played.**

Instead, ISweep DVD acts like an intelligent remote control.

Based on preferences selected by the user, the system can recognize content the user does not want to hear or see and temporarily control playback using actions that already exist on the playback device.

Examples include:

* Pressing **Mute**
* Pressing **Unmute**
* Pressing **Skip**
* Pressing **Fast Forward**
* Pressing **Play**
* Potentially jumping forward using controls already supported by the DVD player or television

The original media continues to play normally and remains unchanged.

---

# Core Principle

## Control Playback — Do Not Edit Media

ISweep DVD should never require creating an altered version of a movie.

For example, if a user does not want to hear a particular word:

1. ISweep identifies when the unwanted word is about to occur.
2. ISweep sends the equivalent of a **Mute** command.
3. The television, receiver, or playback device mutes the audio.
4. After the unwanted content passes, ISweep sends an **Unmute** command.
5. Playback continues normally.

The movie itself has not been edited.

The same principle can be applied to visual content.

If the user has selected a type of scene they do not want to see, ISweep could use the playback controls available to the device to move past that portion of the program.

The goal is similar to having a person sitting beside you with a remote control who already knows your preferences and presses the appropriate buttons at the appropriate time.

ISweep attempts to automate that process.

---

# Project Vision

The long-term goal is to create a system where users can define what they personally do or do not want to hear or see.

ISweep then helps control their playback experience automatically.

Possible filtering categories could eventually include:

### Audio

* Specific words
* Profanity
* User-created custom word lists
* Sexual language
* Drug references
* Religious language
* Other user-defined categories

### Visual Content

Potential future categories could include:

* Sexual content
* Nudity
* Graphic violence
* Gore
* Drug use
* Other user-selected visual categories

Users should ultimately control their own preferences rather than ISweep deciding what is appropriate for them.

---

# User Preference System

A major goal of ISweep is to make filtering customizable.

The user may eventually be able to select preferences through an ISweep webpage or application.

For example:

```text
Audio Preferences

[x] Mute selected profanity
[x] Mute custom words
[ ] Mute religious references
[ ] Mute drug references
```

Visual preferences could work similarly.

```text
Visual Preferences

[ ] Skip sexual scenes
[x] Skip graphic gore
[ ] Skip drug use
```

These are examples only.

The final preference system has not yet been designed.

---

# Two Possible Ways ISweep May Know When to Act

ISweep DVD may eventually use more than one method.

## 1. Pre-Identified Content

ISweep could have information associated with a particular movie, episode, or disc.

For example:

```text
00:14:32 - unwanted word
00:37:11 - unwanted word
01:02:18 - graphic scene begins
01:03:07 - graphic scene ends
```

ISweep could compare these events with the user's preferences and automatically send the required remote-control commands.

This could allow extremely accurate timing.

---

## 2. AI Content Recognition

A future version of ISweep may use AI to recognize what is happening while the media is playing.

Possible technologies could include:

* Speech recognition
* Subtitle recognition
* Closed-caption analysis
* Audio analysis
* Computer vision
* Scene recognition
* Content classification

For example, speech recognition might detect an unwanted word and trigger a mute command.

Computer vision could potentially recognize a category of visual content and trigger a playback command.

AI recognition is still an area that requires significant research and testing.

---

# Remote Control Concept

One of the central technical challenges of ISweep DVD is determining how the system will control playback devices.

Possible control technologies may include:

* Infrared (IR)
* HDMI-CEC
* Bluetooth
* Network-controlled televisions
* Smart TV APIs
* USB-connected infrared transmitters
* Raspberry Pi or similar hardware
* Microcontrollers
* Custom ISweep hardware
* Other remote-control technologies

The goal is to communicate with the playback device using commands the device already understands.

For example:

```text
ISweep
   |
   | Detect unwanted content
   v
Control System
   |
   | Send MUTE command
   v
TV / DVD Player / Receiver
```

ISweep would behave like an automated remote.

---

# Example: Audio Filtering

Imagine a movie containing a word the user has selected to mute.

Normal playback:

```text
Character: "What the hell are you doing?"
```

ISweep could perform:

```text
Character: "What the [MUTED] are you doing?"
```

Behind the scenes:

```text
Movie playing
      |
      v
ISweep detects upcoming selected word
      |
      v
Send MUTE command
      |
      v
Selected word plays while device is muted
      |
      v
Send UNMUTE command
      |
      v
Movie continues
```

The audio file on the DVD has not been changed.

---

# Example: Visual Filtering

Suppose a user has selected a category of scene they do not want to watch.

ISweep could know:

```text
Scene starts: 00:42:18
Scene ends:   00:43:07
```

ISweep could potentially:

```text
Scene approaches
      |
      v
Send playback control
      |
      v
Move past selected scene
      |
      v
Resume normal playback
```

Exactly how this will work depends heavily on the controls supported by the DVD player, Blu-ray player, television, or media device.

This still needs to be researched.

---

# What ISweep DVD Is NOT

ISweep DVD is not intended to:

* Rewrite movies
* Replace movie dialogue
* Modify DVD files
* Modify Blu-ray files
* Permanently remove scenes
* Create an edited copy of a movie
* Redistribute modified movies
* Change the original media

The ISweep philosophy is:

> **Leave the original content alone and control how the user's own playback device presents it.**

---

# Relationship to ISweep

ISweep DVD builds on the ideas being developed in the original ISweep project.

The original ISweep project is being developed around internet video playback, including YouTube.

ISweep DVD explores how the same basic concept could be expanded to physical media and home entertainment systems.

Both projects share an important principle:

**ISweep controls playback rather than modifying the original media.**

---

# Possible System Architecture

The architecture is not finalized, but an early concept could look like this:

```text
                    ISWEEP DVD
                         |
         +---------------+---------------+
         |                               |
         v                               v
 User Preferences                 Content Detection
         |                               |
         |                    +----------+----------+
         |                    |                     |
         |                    v                     v
         |              Audio Detection       Visual Detection
         |                    |                     |
         +--------------------+----------+----------+
                                         |
                                         v
                                  Decision Engine
                                         |
                                         v
                                  Remote Controller
                                         |
                       +-----------------+----------------+
                       |                                  |
                       v                                  v
                  Television                       DVD / Blu-ray
                  / Receiver                          Player
```

This architecture will likely change significantly as prototypes are built.

---

# Major Development Questions

Before ISweep DVD can become a working product, several important problems need to be solved.

## Playback Identification

How does ISweep determine:

* Which movie is playing?
* Which version of the movie is playing?
* Which disc is being used?
* Which episode is playing?
* The current playback position?

Different releases of the same movie may have different timing.

---

## Synchronization

ISweep must know exactly where playback currently is.

Even a timing error of one or two seconds could cause a mute or skip to occur at the wrong moment.

Possible synchronization methods need to be researched.

---

## Audio Recognition

Can ISweep reliably recognize speech quickly enough to mute a word before the viewer hears it?

Possible approaches include:

* Closed captions
* Subtitles
* Speech-to-text
* Pre-analyzed dialogue
* Hybrid systems

---

## Visual Recognition

Can AI reliably recognize selected visual categories?

How much processing power would be required?

Would recognition occur:

* On the ISweep device?
* On a computer?
* Through a local AI model?
* Through another system?

These questions are currently unanswered.

---

## Device Control

Different televisions and DVD players use different control methods.

ISweep may need to support multiple methods such as:

```text
IR
HDMI-CEC
Bluetooth
Wi-Fi
Device APIs
```

IR may be especially useful because it can mimic the physical remote control supplied with many devices.

---

## Timing

Audio muting may require extremely precise timing.

ISweep needs to determine:

* How early the mute command should be sent
* How quickly the television responds
* When unmute should occur
* Whether different televisions have different delays

This will require testing.

---

# First Prototype Goals

The first version does not need to solve everything.

A useful first prototype could focus on proving the basic remote-control concept.

### Phase 1 — Remote Control

Build a system capable of sending commands such as:

```text
MUTE
UNMUTE
PLAY
PAUSE
FAST FORWARD
```

to a real television or DVD player.

---

### Phase 2 — Timed Commands

Create a simple test where ISweep is given predetermined timestamps.

Example:

```text
00:00:10 -> MUTE
00:00:11 -> UNMUTE
00:00:30 -> MUTE
00:00:31 -> UNMUTE
```

Verify that the commands occur accurately during DVD playback.

---

### Phase 3 — User Preferences

Allow the user to select which content should trigger actions.

---

### Phase 4 — Content Database

Experiment with storing known content events for individual movies or episodes.

---

### Phase 5 — AI Recognition

Begin testing AI systems for:

* Speech recognition
* Word detection
* Visual recognition
* Scene classification

---

### Phase 6 — Hybrid Detection

Eventually combine multiple sources of information.

For example:

```text
Movie identification
        +
Known timestamps
        +
Subtitles
        +
Speech recognition
        +
AI vision
        =
More reliable ISweep decisions
```

---

# Development Philosophy

During development we will follow several principles.

### 1. Preserve Working Code

When a component works, avoid unnecessarily rewriting it.

### 2. Build One Capability at a Time

For example:

```text
Remote control
      ↓
Reliable timing
      ↓
Mute
      ↓
User preferences
      ↓
Movie synchronization
      ↓
Skip
      ↓
AI detection
```

### 3. Test With Real Hardware

Many problems such as remote-control delay and playback synchronization cannot be solved through software theory alone.

### 4. Keep the Original Media Untouched

The system should control playback rather than modify the source media.

### 5. User Choice Comes First

ISweep should allow the user to determine what categories they personally want filtered.

---

# Initial Research Areas

The project currently needs research into:

* Infrared transmitters and receivers
* Raspberry Pi remote-control projects
* HDMI-CEC
* Universal remote-control protocols
* DVD playback timing
* Blu-ray playback timing
* Subtitle extraction or recognition
* Speech-to-text
* Real-time audio recognition
* Computer vision
* Movie identification
* Content timestamp databases
* Smart TV control
* Local AI models
* Synchronization methods

---

# Current Development Stage

ISweep DVD is currently at:

```text
[✓] Define the concept
[✓] Establish the non-editing playback philosophy
[ ] Determine first prototype hardware
[ ] Send first remote command
[ ] Control a television
[ ] Control a DVD player
[ ] Synchronize with playback
[ ] Create timed mute prototype
[ ] Create preference interface
[ ] Identify DVD/movie automatically
[ ] Create audio recognition
[ ] Create visual recognition
[ ] Create automatic scene skipping
```

---

# Immediate Next Goal

The first major technical goal for ISweep DVD is simple:

> **Prove that software can reliably act as a remote control for the television/DVD playback system.**

Before attempting advanced AI recognition, ISweep should first demonstrate that it can reliably send commands such as:

```text
Mute
Unmute
Play
Pause
Skip / Fast Forward
```

Once that foundation works, detection and AI systems can be built on top of it.

---

# Long-Term Goal

The long-term vision is a small ISweep system that sits alongside a user's entertainment setup.

The user chooses their preferences.

They start their movie.

ISweep recognizes the movie and follows the playback.

When selected content occurs, ISweep automatically operates the playback controls.

```text
User starts movie
       ↓
ISweep identifies movie
       ↓
ISweep synchronizes playback
       ↓
ISweep reads user preferences
       ↓
Movie plays normally
       ↓
Selected content approaches
       ↓
ISweep presses the appropriate virtual remote button
       ↓
Playback continues
```

The viewer gets a customized viewing experience while the original movie remains completely unchanged.

---

# ISweep DVD

**Your media. Your preferences. Your remote.**
