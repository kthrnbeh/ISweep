# ISweep DVD IR Prototype

## First hardware target: BroadLink RM4 Mini

For the first physical ISweep DVD prototype, the recommended IR transmitter is the **BroadLink RM4 Mini**.

Why this device:

- It is an IR transmitter designed to control televisions, DVD players, receivers, and similar equipment.
- It can learn buttons from the user's existing physical remotes.
- It communicates with the ISweep computer over the local 2.4 GHz Wi-Fi network.
- The open-source `broadlink` Python package supports RM4 Mini discovery, authentication, IR learning, and sending learned packets.
- It does not require changing the DVD, movie, television, or extension code.

The RM4 Mini is IR-only. This is intentional for Prototype 1.

---

# What to obtain

1. BroadLink RM4 Mini
2. USB power source for the RM4 Mini
3. The original TV remote
4. The original DVD/Blu-ray player remote
5. ISweep computer on the same local network

The television and DVD player must actually accept infrared commands for the buttons ISweep needs. Some newer devices use Bluetooth/RF for some functions.

---

# Before running ISweep

Use the BroadLink mobile app to put the RM4 Mini on the same 2.4 GHz Wi-Fi network as the ISweep computer.

Place the RM4 Mini where its IR signal can reach the TV and DVD player. IR requires line-of-sight or a useful reflection path; it does not pass through cabinet doors or walls.

---

# Install the optional hardware dependency

From the ISweep repository with the virtual environment active:

```powershell
pip install -r dvd/requirements-hardware.txt
```

This installs BroadLink support only for the DVD hardware prototype. The normal website, extension, backend, tests, and simulated remote do not depend on it.

---

# Learn the TV MUTE button

Run:

```powershell
python -m dvd.ir_remote_setup learn tv MUTE
```

When the BroadLink enters learning mode, point the original TV remote at it and press **Mute** once.

The learned packet is saved locally in:

```text
dvd/config/ir_codes.json
```

That file is ignored by Git and stays on the local computer.

Most TVs have one MUTE toggle rather than separate MUTE and UNMUTE buttons. ISweep tracks the mute state it entered and can reuse the same learned toggle to unmute during the prototype.

---

# First physical milestone: MUTE -> UNMUTE

After learning MUTE, run:

```powershell
python -m dvd.ir_remote_setup mute-test
```

Expected physical behavior:

```text
Computer
   |
   v
BroadLink RM4 Mini
   |
   v
TV mutes
   |
   | wait 2 seconds
   v
TV unmutes
```

If this works, ISweep has performed its first real remote-control action on physical equipment.

---

# Learn DVD player controls

Learn the buttons that exist on the actual DVD player's remote:

```powershell
python -m dvd.ir_remote_setup learn dvd PLAY
python -m dvd.ir_remote_setup learn dvd PAUSE
python -m dvd.ir_remote_setup learn dvd FAST_FORWARD
python -m dvd.ir_remote_setup learn dvd SKIP
```

Then test individual commands:

```powershell
python -m dvd.ir_remote_setup send dvd PLAY
python -m dvd.ir_remote_setup send dvd PAUSE
```

Or run the short sequence:

```powershell
python -m dvd.ir_remote_setup dvd-test
```

Do not use `dvd-test` with anything important playing until each learned button has been verified individually.

---

# Optional fixed IP address

Automatic local discovery should be tried first.

If discovery is unreliable, find the RM4 Mini's local IP address and use:

```powershell
python -m dvd.ir_remote_setup --host 192.168.x.x mute-test
```

or set it for the current terminal:

```powershell
$env:ISWEEP_IR_HOST="192.168.x.x"
```

Then normal setup commands can omit `--host`.

---

# What this prototype DOES NOT do yet

The IR controller solves the **hands** part of ISweep. It does not yet solve the **ears/eyes** part.

After MUTE/UNMUTE and DVD playback buttons work physically, the next system is:

```text
DVD audio
   |
   v
Computer audio input
   |
   v
Detection / synchronization
   |
   v
Decision Engine
   |
   v
BroadLink infrared controller
```

That is when the simulated detected-dialogue prompt can begin being replaced by real DVD input.
