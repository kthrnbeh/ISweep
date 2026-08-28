"""
ISweep DVD - Remote Control Commands

Defines the common commands that the ISweep Decision Engine
can eventually send to different playback-control systems.

The actual device-control implementation may later use:
- Simulated output
- Infrared
- HDMI-CEC
- Smart TV APIs
- Other playback-control technologies
"""

from enum import Enum


class RemoteCommand(str, Enum):
    ALLOW = "ALLOW"
    MUTE = "MUTE"
    UNMUTE = "UNMUTE"
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    FAST_FORWARD = "FAST_FORWARD"
    REWIND = "REWIND"
    SKIP = "SKIP"