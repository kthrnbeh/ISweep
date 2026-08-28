"""
ISweep DVD - Decision Engine Models

Defines the basic data structures used by the ISweep Decision Engine.

Version 1 focuses on:
- Detected spoken text
- User-selected custom mute words
- ALLOW / MUTE decisions

The models are intentionally independent from DVD hardware,
speech recognition, subtitles, and AI vision.

Those systems will eventually feed information INTO this engine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    """
    Actions that the ISweep Decision Engine can request.

    Version 1 only uses ALLOW and MUTE.

    Additional actions such as SKIP and FAST_FORWARD can be added
    later without changing the basic Decision Engine architecture.
    """

    ALLOW = "ALLOW"
    MUTE = "MUTE"


@dataclass
class Detection:
    """
    Represents content detected by another part of ISweep.

    The Decision Engine does not care how the text was detected.

    It could eventually come from:
    - DVD subtitles
    - Closed captions
    - Speech-to-text
    - Whisper
    - A known movie transcript
    - Another AI system

    Attributes:
        text:
            The detected word, phrase, sentence, or caption.

        timestamp:
            Approximate playback position in seconds.

        confidence:
            Detection confidence from 0.0 to 1.0.

        source:
            Name of the system that produced the detection.
    """

    text: str
    timestamp: float = 0.0
    confidence: float = 1.0
    source: str = "unknown"


@dataclass
class UserPreferences:
    """
    Preferences supplied by the ISweep user.

    Version 1 only contains custom mute words.

    Example:

        UserPreferences(
            custom_mute_words=["hell", "damn"]
        )
    """

    custom_mute_words: list[str] = field(default_factory=list)


@dataclass
class Decision:
    """
    Final result returned by the ISweep Decision Engine.

    Attributes:
        action:
            What ISweep should do.

        reason:
            Human-readable explanation for the decision.

        matched_term:
            The custom word or phrase that caused the decision.

        timestamp:
            Playback position associated with the detection.

        detected_text:
            Original text received by the Decision Engine.
    """

    action: Action
    reason: str
    matched_term: Optional[str] = None
    timestamp: float = 0.0
    detected_text: str = ""