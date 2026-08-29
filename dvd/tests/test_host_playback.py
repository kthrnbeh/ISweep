from dvd.decision_engine import Action, Decision
from dvd.playback import ISweepHostPlayback, SimulatedPlaybackController


def _decision(action: Action) -> Decision:
    return Decision(
        action=action,
        reason="test",
        timestamp=1.0,
        detected_text="test dialogue",
    )


def test_mute_decision_mutes_host_player_once():
    controller = SimulatedPlaybackController()
    host = ISweepHostPlayback(controller)

    host.apply_decision(_decision(Action.MUTE))
    host.apply_decision(_decision(Action.MUTE))

    assert controller.get_state().muted is True
    assert controller.events == ["MUTE"]
    assert host.muted_by_isweep is True


def test_allow_restores_sound_after_isweep_mute():
    controller = SimulatedPlaybackController()
    host = ISweepHostPlayback(controller)

    host.apply_decision(_decision(Action.MUTE))
    host.apply_decision(_decision(Action.ALLOW))

    assert controller.get_state().muted is False
    assert controller.events == ["MUTE", "UNMUTE"]
    assert host.muted_by_isweep is False


def test_allow_does_not_unmute_audio_isweep_did_not_mute():
    controller = SimulatedPlaybackController()
    controller.mute()
    controller.events.clear()
    host = ISweepHostPlayback(controller)

    host.apply_decision(_decision(Action.ALLOW))

    assert controller.get_state().muted is True
    assert controller.events == []


def test_skip_moves_player_forward():
    controller = SimulatedPlaybackController()
    host = ISweepHostPlayback(controller)

    host.skip_seconds(15)

    assert controller.get_state().position_seconds == 15.0
    assert controller.events == ["SEEK:15"]
