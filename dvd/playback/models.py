"""Data models for the ISweep host-playback layer."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MediaKind(str, Enum):
    DVD = "DVD"
    FILE = "FILE"
    STREAM = "STREAM"


class PlaybackStatus(str, Enum):
    STOPPED = "STOPPED"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class MediaSource:
    """A source that an ISweep playback adapter can load."""

    kind: MediaKind
    location: str
    title: str = ""


@dataclass
class PlaybackState:
    """Player state exposed to synchronization, AI, and companion controls."""

    source: Optional[MediaSource] = None
    status: PlaybackStatus = PlaybackStatus.STOPPED
    position_seconds: float = 0.0
    duration_seconds: Optional[float] = None
    muted: bool = False
    volume: float = 1.0
