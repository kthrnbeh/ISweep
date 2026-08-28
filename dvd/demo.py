"""
ISweep DVD - Interactive Shared-Preferences Demo

This demo proves the first connection between the existing ISweep
website/backend and ISweep DVD.

Flow:

    ISweep Filters webpage
            ↓
       /preferences
            ↓
       ISweep database
            ↓
       ISweep DVD
            ↓
      Decision Engine
            ↓
     Simulated Remote

The user no longer types filter words into this program.

Instead, ISweep DVD signs into the existing ISweep backend and loads
the same saved preferences already used by the website/extension.

No media is edited or modified.
"""

from getpass import getpass

from dvd.control.simulated import SimulatedRemote
from dvd.decision_engine import DecisionEngine, Detection
from dvd.preferences import (
    ISweepPreferencesClient,
    PreferencesError,
    preferences_to_decision_preferences,
)


def show_header() -> None:
    """Display the ISweep DVD startup header."""

    print()
    print("=" * 60)
    print("ISWEEP DVD")
    print("SHARED PREFERENCES DEMO")
    print("=" * 60)
    print()


def show_category(name: str, config: dict) -> None:
    """
    Display one saved ISweep category.
    """

    if not isinstance(config, dict):
        return

    enabled = config.get("enabled", True)
    action = str(config.get("action") or "none").upper()
    duration = config.get("duration", 0)
    sensitivity = config.get("sensitivity")

    status = "ON" if enabled else "OFF"

    print(f"{name}:")
    print(f"  Status:      {status}")
    print(f"  Action:      {action}")
    print(f"  Duration:    {duration} sec")

    if sensitivity is not None:
        print(f"  Sensitivity: {sensitivity}")

    print()


def show_preferences(raw_preferences: dict, mute_words: list[str]) -> None:
    """
    Display the actual preferences loaded from the ISweep backend.

    Decision Engine v1 currently acts only on language words, but
    the entire preference object is loaded so later versions can
    consume visual categories without changing the connection.
    """

    print()
    print("-" * 60)
    print("ISWEEP PREFERENCES LOADED")
    print("-" * 60)
    print()

    categories = raw_preferences.get("categories", {})

    if not isinstance(categories, dict):
        categories = {}

    display_names = {
        "language": "Language",
        "intimacy": "Intimacy",
        "violence": "Violence",
        "substances": "Substances",
        "horror": "Horror & Fears",
    }

    for key, label in display_names.items():
        category = categories.get(key)

        if isinstance(category, dict):
            show_category(label, category)

    print("Language words currently available to DVD Decision Engine:")

    if mute_words:
        print(f"  {len(mute_words)} selected word(s) / phrase(s)")

        for word in mute_words:
            print(f"  MUTE: {word}")
    else:
        print("  No language words are currently selected.")

    print()
    print("-" * 60)


def load_shared_preferences():
    """
    Connect to the existing ISweep backend and load the user's
    real saved preferences.
    """

    client = ISweepPreferencesClient()

    print("Checking ISweep backend...")

    if not client.health_check():
        print()
        print("ERROR: ISweep backend is not responding.")
        print()
        print("Expected backend:")
        print("  http://127.0.0.1:5000")
        print()
        print("Make sure the existing ISweep backend is running.")
        return None

    print("Backend connected.")
    print()

    email = input("ISweep email: ").strip()

    if not email:
        print("An ISweep account email is required.")
        return None

    # getpass hides the password while the user types.
    password = getpass("ISweep password (typing is hidden — press Enter when done): ")

    if not password:
        print("An ISweep password is required.")
        return None

    print()
    print("Signing into ISweep...")

    try:
        session = client.login(
            email=email,
            password=password,
        )

        print("Signed in.")
        print("Loading saved preferences...")

        raw_preferences = client.get_preferences(session)

    except PreferencesError as exc:
        print()
        print("Could not load ISweep preferences.")
        print(f"Reason: {exc}")
        return None

    print("Preferences loaded.")

    decision_preferences = preferences_to_decision_preferences(
        raw_preferences
    )

    return raw_preferences, decision_preferences


def run_demo() -> None:
    """
    Start the shared-preferences ISweep DVD demo.
    """

    show_header()

    loaded = load_shared_preferences()

    if loaded is None:
        print()
        print("ISweep DVD demo stopped.")
        print()
        return

    raw_preferences, decision_preferences = loaded

    show_preferences(
        raw_preferences,
        decision_preferences.custom_mute_words,
    )

    engine = DecisionEngine()
    remote = SimulatedRemote()

    print()
    print("ISweep DVD Decision Engine is ready.")
    print()
    print("For now, type dialogue to simulate text detected from a DVD.")
    print("The preferences above come from your real ISweep account.")
    print()
    print("Type 'reload' to reload preferences from the website.")
    print("Type 'quit' to stop the demo.")
    print()

    timestamp = 0.0

    while True:
        detected_text = input("Detected dialogue > ").strip()

        command = detected_text.lower()

        if command in {"quit", "exit", "q"}:
            print()
            print("ISweep DVD demo stopped.")
            print()
            break

        if command == "reload":
            print()
            print("Reloading preferences from ISweep...")
            print()

            loaded = load_shared_preferences()

            if loaded is None:
                print()
                print("Previous preferences remain active.")
                print()
                continue

            raw_preferences, decision_preferences = loaded

            show_preferences(
                raw_preferences,
                decision_preferences.custom_mute_words,
            )

            print()
            print("Preferences reloaded.")
            print()

            continue

        if not detected_text:
            continue

        detection = Detection(
            text=detected_text,
            timestamp=timestamp,
            confidence=1.0,
            source="manual_dvd_demo",
        )

        decision = engine.decide(
            detection=detection,
            preferences=decision_preferences,
        )

        remote.execute_decision(decision)

        # Temporary artificial timeline for testing.
        # Real DVD synchronization will replace this later.
        timestamp += 1.0


if __name__ == "__main__":
    run_demo()