"""
Tests for ISweep DVD Decision Engine v1.

These tests verify the first core behavior of ISweep:

    detected content
            +
    user preferences
            ↓
    ALLOW or MUTE

Run from the main ISweep folder with:

    python -m pytest dvd/tests/test_decision_engine.py -v
"""

from dvd.decision_engine import (
    Action,
    DecisionEngine,
    Detection,
    UserPreferences,
)


def test_selected_word_is_muted():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=["hell", "damn"]
    )

    detection = Detection(
        text="hell",
        timestamp=10.5,
        confidence=0.99,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.MUTE
    assert decision.matched_term == "hell"
    assert decision.timestamp == 10.5


def test_unselected_word_is_allowed():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=["hell", "damn"]
    )

    detection = Detection(
        text="hello",
        timestamp=20.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.ALLOW
    assert decision.matched_term is None


def test_word_does_not_match_inside_larger_word():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=["hell"]
    )

    detection = Detection(
        text="She picked up a seashell.",
        timestamp=30.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.ALLOW
    assert decision.matched_term is None


def test_matching_is_case_insensitive():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=["hell"]
    )

    detection = Detection(
        text="What the HELL are you doing?",
        timestamp=40.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.MUTE
    assert decision.matched_term == "hell"


def test_punctuation_does_not_prevent_match():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=["damn"]
    )

    detection = Detection(
        text="Damn! I forgot my keys.",
        timestamp=50.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.MUTE
    assert decision.matched_term == "damn"


def test_empty_preferences_allow_content():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=[]
    )

    detection = Detection(
        text="hell",
        timestamp=60.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.ALLOW
    assert decision.matched_term is None


def test_phrase_can_be_matched():
    engine = DecisionEngine()

    preferences = UserPreferences(
        custom_mute_words=["bad word"]
    )

    detection = Detection(
        text="Someone said the bad word during the movie.",
        timestamp=70.0,
        source="test",
    )

    decision = engine.decide(detection, preferences)

    assert decision.action == Action.MUTE
    assert decision.matched_term == "bad word"