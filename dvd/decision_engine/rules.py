"""
ISweep DVD - Decision Engine Rules

Contains matching rules used by the Decision Engine.

Version 1 implements custom-word matching.

Important behavior:

    Selected word: "hell"

    "hell"       -> MATCH
    "Hell!"      -> MATCH
    "what the hell?" -> MATCH

    "shell"      -> NO MATCH
    "hello"      -> NO MATCH

This gives ISweep whole-word matching rather than simply checking
whether one group of letters appears inside another word.
"""

import re
from typing import Optional


def normalize_term(term: str) -> str:
    """
    Normalize a user preference term.

    Leading/trailing whitespace is removed and matching is
    case-insensitive.
    """

    return term.strip().lower()


def find_custom_mute_match(
    detected_text: str,
    custom_mute_words: list[str],
) -> Optional[str]:
    """
    Search detected text for one of the user's custom mute words.

    Matching is:
    - Case-insensitive
    - Whole-word / whole-phrase based
    - Safe around punctuation

    Returns:
        The matching preference term when found.

        None when no custom mute word matched.
    """

    if not detected_text:
        return None

    for raw_term in custom_mute_words:
        term = normalize_term(raw_term)

        if not term:
            continue

        # Escape the user's term so characters such as ".", "?", "+"
        # and others are treated literally instead of as regex syntax.
        escaped_term = re.escape(term)

        # Replace escaped spaces with flexible whitespace so a phrase
        # such as "bad word" can still work reliably if spacing varies.
        escaped_term = escaped_term.replace(r"\ ", r"\s+")

        # (?<!\w) and (?!\w) prevent terms from matching inside
        # larger words.
        #
        # Example:
        #   "hell" will match "hell!"
        #   "hell" will NOT match "shell"
        pattern = rf"(?<!\w){escaped_term}(?!\w)"

        if re.search(pattern, detected_text, flags=re.IGNORECASE):
            return raw_term.strip()

    return None