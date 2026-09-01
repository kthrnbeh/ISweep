"""Connect ISweep decisions to a player that ISweep directly controls."""

from dvd.decision_engine import Action, Decision

from .controller import PlaybackController


class ISweepHostPlayback:
    """Apply Decision Engine results directly to the media player.

    The host owns playback, so MUTE/UNMUTE can be deterministic instead of
    depending on a TV remote toggle. The original media remains unchanged.
    """

    def __init__(self, controller: PlaybackController) -> None:
        self.controller = controller
        self._muted_by_isweep = False

    @property
    def muted_by_isweep(self) -> bool:
        return self._muted_by_isweep

    def apply_decision(self, decision: Decision) -> None:
        if decision.action == Action.MUTE:
            if not self._muted_by_isweep:
                self.controller.mute()
                self._muted_by_isweep = True
            return

        # Decision Engine v1 uses ALLOW as the clean-content state. Only
        # restore sound if ISweep itself muted the player.
        if decision.action == Action.ALLOW and self._muted_by_isweep:
            self.controller.unmute()
            self._muted_by_isweep = False

    def skip_seconds(self, seconds: float) -> None:
        """Move playback forward without altering the underlying media."""

        if seconds <= 0:
            return
        self.controller.seek_relative(seconds)
