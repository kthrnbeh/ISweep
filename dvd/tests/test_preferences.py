"""
Tests for the ISweep DVD preference bridge.

These tests verify that ISweep DVD understands the same preference
schema currently produced by the ISweep Filters webpage.
"""

from dvd.preferences import (
    extract_language_blocklist,
    preferences_to_decision_preferences,
)


def test_reads_current_web_blocklist():
    preferences = {
        "enabled": True,
        "categories": {
            "language": {
                "enabled": True,
                "action": "mute",
                "duration": 6,
                "sensitivity": 0.9,
                "items": ["hell", "damn"],
            }
        },
        "blocklist": {
            "enabled": True,
            "mode": "whole_word",
            "action": "mute",
            "duration": 6,
            "items": ["hell", "damn"],
        },
    }

    words = extract_language_blocklist(preferences)

    assert words == ["hell", "damn"]


def test_falls_back_to_language_items():
    preferences = {
        "enabled": True,
        "categories": {
            "language": {
                "enabled": True,
                "items": ["hell"],
            }
        },
    }

    words = extract_language_blocklist(preferences)

    assert words == ["hell"]


def test_disabled_global_preferences_returns_no_words():
    preferences = {
        "enabled": False,
        "blocklist": {
            "enabled": True,
            "items": ["hell"],
        },
    }

    words = extract_language_blocklist(preferences)

    assert words == []


def test_disabled_blocklist_can_use_language_fallback():
    preferences = {
        "enabled": True,
        "categories": {
            "language": {
                "items": ["fallback"],
            }
        },
        "blocklist": {
            "enabled": False,
            "items": ["hell"],
        },
    }

    words = extract_language_blocklist(preferences)

    assert words == ["fallback"]


def test_duplicate_words_are_removed_case_insensitively():
    preferences = {
        "enabled": True,
        "blocklist": {
            "enabled": True,
            "items": [
                "hell",
                "Hell",
                " damn ",
                "damn",
            ],
        },
    }

    words = extract_language_blocklist(preferences)

    assert words == ["hell", "damn"]


def test_web_preferences_convert_to_decision_engine_preferences():
    preferences = {
        "enabled": True,
        "blocklist": {
            "enabled": True,
            "items": ["hell", "damn"],
        },
    }

    decision_preferences = preferences_to_decision_preferences(
        preferences
    )

    assert decision_preferences.custom_mute_words == [
        "hell",
        "damn",
    ]
    