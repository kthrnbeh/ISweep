"""
Tests for the ISweep DVD simulated remote.

These tests verify that Decision Engine results are correctly
translated into remote-control commands.
"""

from dvd.control.commands import RemoteCommand
from dvd.control.simulated import SimulatedRemote
from dvd.decision_engine import (
    DecisionEngine,
    Detection,
    UserPreferences,
)


def test_mute_decision_sends_mute_command():
    engine = DecisionEngine()
    remote = SimulatedRemote()

    preferences = UserPreferences(
        custom_mute_words=["hell"]
    )

    detection = Detection(
        text="What the hell are you doing?",
        timestamp=12.5,
        source="test",
    )

    decision = engine.decide(detection, preferences)
    command = remote.execute_decision(decision)

    assert command == RemoteCommand.MUTE


def test_allowed_content_sends_allow_command():
    engine = DecisionEngine()
    remote = SimulatedRemote()

    preferences = UserPreferences(
        custom_mute_words=["hell"]
    )

    detection = Detection(
        text="What are you doing?",
        timestamp=25.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)
    command = remote.execute_decision(decision)

    assert command == RemoteCommand.ALLOW