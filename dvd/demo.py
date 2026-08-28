"""
ISweep DVD - Interactive Decision Engine Demo

This is the first end-to-end ISweep DVD prototype.

It allows us to manually enter:
- Words/phrases the user wants muted
- Dialogue that ISweep has supposedly detected

The system then sends that information through:

    Detection
        ↓
    Decision Engine
        ↓
    Simulated Remote

No media is edited or modified.

This demo exists so we can prove the complete ISweep decision flow
before connecting real subtitles, speech recognition, AI vision,
or physical remote-control hardware.
"""

from dvd.control.simulated import SimulatedRemote
from dvd.decision_engine import (
    DecisionEngine,
    Detection,
    UserPreferences,
)


def get_custom_words() -> list[str]:
    """
    Ask the user which words or phrases should be muted.

    Multiple entries should be separated with commas.

    Example:

        hell, damn, bad word
    """

    print()
    print("=" * 60)
    print("ISWEEP DVD")
    print("DECISION ENGINE DEMO")
    print("=" * 60)

    raw_words = input(
        "\nEnter words or phrases to MUTE, separated by commas:\n> "
    )

    words = [
        word.strip()
        for word in raw_words.split(",")
        if word.strip()
    ]

    return words


def show_preferences(preferences: UserPreferences) -> None:
    """
    Display the preferences currently being used.
    """

    print()
    print("-" * 60)
    print("CURRENT ISWEEP PREFERENCES")
    print("-" * 60)

    if preferences.custom_mute_words:
        for word in preferences.custom_mute_words:
            print(f"  MUTE: {word}")
    else:
        print("  No custom mute words selected.")

    print("-" * 60)


def run_demo() -> None:
    """
    Start the interactive ISweep DVD demo.
    """

    engine = DecisionEngine()
    remote = SimulatedRemote()

    custom_words = get_custom_words()

    preferences = UserPreferences(
        custom_mute_words=custom_words
    )

    show_preferences(preferences)

    print()
    print("Type dialogue that ISweep has detected.")
    print("Type 'quit' to stop the demo.")
    print()

    timestamp = 0.0

    while True:
        detected_text = input("Detected dialogue > ").strip()

        if detected_text.lower() in {"quit", "exit", "q"}:
            print()
            print("ISweep DVD demo stopped.")
            print()
            break

        if not detected_text:
            continue

        detection = Detection(
            text=detected_text,
            timestamp=timestamp,
            confidence=1.0,
            source="manual_demo",
        )

        decision = engine.decide(
            detection=detection,
            preferences=preferences,
        )

        remote.execute_decision(decision)

        # Artificially advance the timestamp for demo purposes.
        # Real playback synchronization will replace this later.
        timestamp += 1.0


if __name__ == "__main__":
    run_demo()