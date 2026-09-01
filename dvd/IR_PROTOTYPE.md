# ISweep DVD IR Prototype — Optional Legacy Compatibility

## Important

Infrared is **not** the primary ISweep DVD architecture.

The main product direction is software-first:

```text
ISweep Companion (phone/computer)
        |
        +--> Wi-Fi / local network APIs
        +--> Bluetooth where supported
        +--> HDMI-CEC where supported
        |
        v
TV / receiver / DVD player
```

This IR prototype is retained only as an **optional compatibility adapter** for older equipment that accepts infrared commands but exposes no usable Wi-Fi, Bluetooth, HDMI-CEC, USB, or other software-control interface.

A user should not be required to purchase a universal remote or IR bridge in order to use the normal ISweep system.

---

# Why the IR code remains in the repository

The project uses a shared command vocabulary:

```text
MUTE
UNMUTE
PLAY
PAUSE
FAST_FORWARD
REWIND
SKIP
```

Different device adapters can implement those same commands.

```text
Decision Engine
      |
      +--> Wi-Fi adapter       PRIMARY
      +--> Bluetooth adapter   WHEN SUPPORTED
      +--> HDMI-CEC adapter    WHEN SUPPORTED
      +--> IR adapter          OPTIONAL LEGACY FALLBACK
```

Keeping the IR adapter does not make IR a product requirement and does not change the extension or webpage preference architecture.

---

# When this prototype is useful

Use the IR adapter only when all of the following are true:

1. The television/player is controlled by IR.
2. The device has no usable local-network/Bluetooth/CEC control path.
3. The user already has compatible IR hardware or chooses to add it.

If the user's existing phone already has an IR emitter, a future ISweep phone implementation could potentially use that emitter directly rather than requiring a separate device.

---

# Current reference implementation

The current optional implementation targets a BroadLink-compatible IR transmitter because it provides a practical development reference for learning and replaying remote codes.

It is **not a required purchase recommendation** for the ISweep product.

The code lives in:

```text
dvd/control/infrared.py
```

and its optional setup utility is:

```text
dvd/ir_remote_setup.py
```

BroadLink support is isolated in:

```text
dvd/requirements-hardware.txt
```

so installing or using it is unnecessary for the website, extension, backend, Decision Engine, or software-first DVD controller.

---

# Future priority

Development priority now belongs to:

1. shared website/backend/DVD preferences,
2. local network device discovery,
3. smart-TV Wi-Fi control,
4. player Wi-Fi/Bluetooth/CEC control,
5. phone/computer sensing,
6. synchronization and AI,
7. IR only as optional legacy compatibility.
