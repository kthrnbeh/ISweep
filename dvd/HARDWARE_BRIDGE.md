# ISweep DVD Device Bridge

## Core Product Rule

ISweep itself should be the control system.

The preferred design is **software-first**: use devices the user already owns (computer, phone, smart TV, Wi-Fi/Bluetooth-enabled player) and communicate through interfaces those devices already expose.

ISweep should **not require a purchased universal remote or IR bridge** as part of the normal product.

Infrared support may remain as an optional compatibility path for older equipment, but it is not the primary architecture.

---

# What ISweep DVD Must Do

ISweep DVD needs three abilities:

1. **Sense** what is playing.
2. **Decide** whether content matches the user's saved ISweep preferences.
3. **Control** playback using software/network commands already supported by the user's equipment.

The DVD, Blu-ray, movie, or show remains unchanged.

---

# Current Status

## Working now

- Shared ISweep website/backend preference design
- DVD preference bridge
- Decision Engine
- Language whole-word matching
- Simulated remote commands
- Automated tests

## In progress

- Website/backend preference synchronization

## Not implemented yet

- Automatic discovery of TVs/players on the local network
- Wi-Fi smart-TV command adapters
- Bluetooth device-control adapters
- HDMI-CEC adapter
- Phone/PC companion controller
- Real DVD audio/video sensing
- Playback synchronization
- Real-time MUTE / UNMUTE / SKIP / FAST_FORWARD control

---

# Primary Architecture — ISweep Companion

The preferred design is an ISweep Companion running on a computer or phone already owned by the user.

```text
                    ISWEEP WEBSITE
                 shared user preferences
                          |
                          v
                 ISWEEP BACKEND / ACCOUNT
                          |
                          v
                    ISWEEP COMPANION
                 phone and/or computer
                          |
            +-------------+-------------+
            |             |             |
            v             v             v
         Wi-Fi        Bluetooth      HDMI-CEC
            |             |             |
            +-------------+-------------+
                          |
                          v
                TV / Receiver / Player
```

The companion is the "universal remote" logic. ISweep does not need a third-party universal remote application.

---

# Important Physical Limitation

A phone or computer can only send commands through communication methods that both sides support.

For example:

```text
Phone has Wi-Fi
TV exposes Wi-Fi remote API
        -> ISweep can control TV over Wi-Fi
```

But:

```text
Phone has Wi-Fi/Bluetooth
Old DVD player accepts ONLY infrared
        -> software alone cannot make the DVD player receive Wi-Fi/Bluetooth
```

That is not a software limitation we can code around; the receiving device must understand at least one protocol the phone/computer can transmit.

For ISweep's no-extra-hardware mode, equipment with no usable Wi-Fi, Bluetooth, HDMI-CEC, USB, or other software-control interface would simply be unsupported unless the user's phone already contains an IR emitter.

Optional IR support can remain for people who want compatibility with legacy devices, but it should not be a requirement for ISweep.

---

# Software Control Priority

ISweep should try control methods in this order:

## 1. Direct local-network control

Preferred when the TV/player exposes a local API.

Examples of transport we may support through adapters:

- local HTTP
- WebSocket
- TCP/UDP device protocols
- SSDP / UPnP discovery
- mDNS discovery

The ISweep code should perform discovery, pairing, and command transmission itself.

## 2. Smart-TV control

The TV is often the best target for:

- MUTE
- UNMUTE
- volume
- input selection

If the TV can also forward transport commands to an HDMI-connected player through HDMI-CEC, ISweep may be able to control the DVD/Blu-ray player indirectly without another device.

## 3. Direct network control of the DVD/Blu-ray/media player

When a player exposes its own network protocol, ISweep can send:

- PLAY
- PAUSE
- FAST_FORWARD
- SKIP
- REWIND

Support will be adapter-based because manufacturers/models expose different capabilities.

## 4. Bluetooth control

Use Bluetooth when the playback device actually accepts remote/media-control commands over Bluetooth.

Having Bluetooth hardware alone does not guarantee a DVD player accepts Bluetooth remote commands; ISweep must discover and pair with a compatible service/profile.

## 5. HDMI-CEC

If the computer/TV/player chain exposes CEC control, ISweep can potentially send playback commands through HDMI.

CEC support varies by computer hardware, TV, player, and operating-system access.

## 6. Infrared — optional legacy fallback

IR remains an adapter for equipment that has no usable software interface.

It is **not required** for the main ISweep product vision.

---

# Using a Phone as the ISweep Device

A phone can potentially provide both sensing and control without additional purchased hardware.

```text
                    PHONE
              +------+------+
              |             |
              v             v
          Microphone       Camera
              |             |
              v             v
          Audio AI       Visual AI
              \             /
               \           /
                v         v
               Decision Engine
                      |
                      v
                Wi-Fi / Bluetooth
                      |
                      v
                 TV / Player
```

Possible phone roles:

- microphone for live dialogue recognition
- camera for future visual recognition
- account/preferences UI
- local network device discovery
- device pairing
- remote commands
- synchronization assistant

A phone camera/microphone is useful for a no-extra-hardware prototype, although live recognition latency must still be solved for accurate profanity muting.

---

# Using a Computer as the ISweep Device

The existing Python project can become the first ISweep Companion.

```text
ISweep backend/preferences
          |
          v
Python DVD service
          |
          +--> network device discovery
          +--> smart-TV adapter
          +--> player adapter
          +--> Bluetooth adapter
          +--> CEC adapter
          |
          v
TV / DVD player
```

This is the easiest place to build and test the protocol layer before packaging it into a phone application.

---

# Sensing — Giving ISweep Ears and Eyes Without Required Capture Hardware

The software-first design should prefer existing sensors and available data sources.

## Audio options

1. Phone microphone listening near the TV
2. Computer microphone listening near the TV
3. System-audio capture when playback occurs on the computer
4. Subtitle/caption data when available
5. Known transcript/timestamp data
6. Direct audio input only when the user already has compatible equipment

## Video options

1. Phone camera pointed at the display
2. Computer camera where practical
3. Computer playback frames when media is played locally
4. Network-accessible media/metadata where supported
5. Direct video capture only when already available and legally/technically supported

The product should not depend on purchasing an HDMI capture card.

---

# Synchronization — The Hard Part

Recognizing a word after it was spoken is too late for perfect muting.

ISweep therefore needs look-ahead or synchronization.

Preferred sources include:

- subtitle/caption timing
- known movie timestamps
- pre-analysis of a title
- transcript alignment
- audio fingerprint synchronization
- live speech recognition as a fallback
- hybrid detection using several sources

Long term:

```text
Movie identified
      +
playback synchronized
      +
known/subtitle event ahead
      |
      v
Decision Engine
      |
      v
MUTE before unwanted word
      |
      v
UNMUTE after event
```

---

# Adapter Architecture

All control technologies should implement the same command vocabulary already defined in:

```text
dvd/control/commands.py
```

Commands include:

```text
ALLOW
MUTE
UNMUTE
PLAY
PAUSE
FAST_FORWARD
REWIND
SKIP
```

That allows ISweep to select a controller based on the user's existing equipment without changing the Decision Engine.

Example:

```text
Decision Engine -> MUTE
                    |
                    +--> Samsung/LG/etc. Wi-Fi adapter
                    +--> Bluetooth adapter
                    +--> CEC adapter
                    +--> optional IR adapter
```

---

# Recommended Development Path

## Phase A — Shared preferences

Finish proving that the website, extension, and DVD controller read the same successfully saved backend preference object.

## Phase B — Software device discovery

Build a local ISweep device-discovery service that can identify controllable TVs/players on the user's LAN and report what protocols they expose.

## Phase C — First real Wi-Fi control adapter

Choose one real TV/device already owned by the user and implement:

```text
MUTE
UNMUTE
```

without a purchased universal remote.

## Phase D — Player transport control

For the user's actual DVD/Blu-ray player, determine whether it can be controlled by:

```text
Wi-Fi API
Bluetooth
HDMI-CEC through TV
other existing software protocol
```

Then implement PLAY / PAUSE / FAST_FORWARD / SKIP.

## Phase E — Phone/PC sensing

Use existing microphone/camera/system audio to feed detection.

## Phase F — Synchronization / look-ahead

Make mute/skip commands occur at the correct playback time.

## Phase G — Visual AI

Connect Intimacy, Violence, Substances, and Horror preferences to visual classification and playback actions.

---

# Product Principle

ISweep should be the intelligence, preference system, controller, and user experience.

We can implement support for standard device protocols ourselves, but we cannot make a physical player receive a protocol it was never designed to receive.

Therefore the main ISweep product should be:

**AI + shared preferences + phone/computer companion + Wi-Fi/Bluetooth/CEC/device APIs, with IR only as an optional legacy compatibility adapter.**
