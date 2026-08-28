"""
ISweep DVD - Decision Engine

This is the central decision-making component for ISweep DVD.

The engine receives:

    Detection
        +
    User Preferences

and returns:

    Decision

Version 1 supports:

    ALLOW
    MUTE

The Decision Engine does NOT:
- Control the television
- Control the DVD player
- Listen to audio
- Read subtitles
- Modify media
- Skip scenes
- Perform AI recognition

Those responsibilities belong to other ISweep components.

The Decision Engine's only responsibility is deciding what SHOULD
happen based on detected content and the user's preferences.
"""

from .models import Action, Decision, Detection, UserPreferences
from .rules import find_custom_mute_match


class DecisionEngine:
    """
    ISweep's central decision engine.

    Future versions can add:
    - Language categories
    - Sensitivity levels
    - Violence
    - Intimacy
    - Substances
    - Horror / fears
    - Visual detections
    - Confidence thresholds
    - Skip decisions
    - Device-specific overrides

    Version 1 deliberately starts with custom mute words only.
    """

    def decide(
        self,
        detection: Detection,
        preferences: UserPreferences,
    ) -> Decision:
        """
        Decide whether detected content should be allowed or muted.

        Args:
            detection:
                Content detected by another ISweep component.

            preferences:
                Current user filtering preferences.

        Returns:
            A Decision describing what ISweep should do.
        """

        matched_term = find_custom_mute_match(
            detected_text=detection.text,
            custom_mute_words=preferences.custom_mute_words,
        )

        if matched_term is not None:
            return Decision(
                action=Action.MUTE,
                reason="Detected text matched a custom mute word.",
                matched_term=matched_term,
                timestamp=detection.timestamp,
                detected_text=detection.text,
            )

        return Decision(
            action=Action.ALLOW,
            reason="No enabled custom mute rule matched the detected text.",
            matched_term=None,
            timestamp=detection.timestamp,
            detected_text=detection.text,
        )