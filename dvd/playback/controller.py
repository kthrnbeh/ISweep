"""Common playback-control interface for ISweep Host Playback."""

from typing import Protocol

from .models import MediaSource, PlaybackState


class PlaybackController(Protocol):
    """Contract implemented by real and simulated media-player adapters."""

    def load(self, source: MediaSource) -> None:
        ...

    def play(self) -> None:
        ...

    def pause(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def mute(self) -> None:
        ...

    def unmute(self) -> None:
        ...

    def seek_relative(self, seconds: float) -> None:
        ...

    def get_state(self) -> PlaybackState:
        ...
