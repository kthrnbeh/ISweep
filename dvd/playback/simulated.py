"""Simulated media player used while the real DVD engine is being integrated."""

from copy import deepcopy

from .models import MediaSource, PlaybackState, PlaybackStatus


class SimulatedPlaybackController:
    """In-memory player that implements the same contract as a real player."""

    def __init__(self) -> None:
        self._state = PlaybackState()
        self.events: list[str] = []

    def load(self, source: MediaSource) -> None:
        self._state = PlaybackState(source=source)
        self.events.append(f"LOAD:{source.kind.value}:{source.location}")

    def play(self) -> None:
        self._state.status = PlaybackStatus.PLAYING
        self.events.append("PLAY")

    def pause(self) -> None:
        self._state.status = PlaybackStatus.PAUSED
        self.events.append("PAUSE")

    def stop(self) -> None:
        self._state.status = PlaybackStatus.STOPPED
        self._state.position_seconds = 0.0
        self.events.append("STOP")

    def mute(self) -> None:
        if not self._state.muted:
            self._state.muted = True
            self.events.append("MUTE")

    def unmute(self) -> None:
        if self._state.muted:
            self._state.muted = False
            self.events.append("UNMUTE")

    def seek_relative(self, seconds: float) -> None:
        self._state.position_seconds = max(
            0.0,
            self._state.position_seconds + float(seconds),
        )
        self.events.append(f"SEEK:{float(seconds):g}")

    def get_state(self) -> PlaybackState:
        return deepcopy(self._state)
