"""
ISWEEP COMPONENT: Content Analyzer

This module inspects caption text and assigns playback actions (mute/skip/fast_forward/none)
based on user preferences. It is invoked by /event so the extension can react in real time.

System connection:
    Extension sends caption -> Backend /event -> ContentAnalyzer.analyze_decision -> decision JSON
"""

import re
from typing import Dict, List
from better_profanity import profanity

class ContentAnalyzer:
    """Analyzes caption/transcript text and determines playback control actions."""
    
    # Define content patterns for different categories
    VIOLENCE_PATTERNS = [
        r'\b(kill|killed|murder|shot|shoot|stab|blood|violence|violent|attack|fight|gun|weapon)\b',
        r'\b(death|die|dying|dead)\b',
        r'\b(assault|beat|beating|punch|hit)\b'
    ]
    
    SEXUAL_PATTERNS = [
        r'\b(sex|sexual|naked|nude|explicit)\b',
        r'\b(rape|assault|abuse)\b',
        r'\b(intercourse|seduce|seduction)\b'
    ]
    
    # Sensitivity thresholds (number of matches before triggering action)
    SENSITIVITY_THRESHOLDS = {
        'low': 5,      # Very lenient, needs many matches
        'medium': 2,   # Moderate sensitivity
        'high': 1      # Very strict, one match triggers action
    }
    SENSITIVITY_ACTIONS = {
        'low': ('mute', 5),          # least restrictive
        'medium': ('fast_forward', 10),
        'high': ('skip', 15)         # most restrictive
    }
    DEFAULT_DURATIONS = {
        'mute': 4,
        'skip': 12,
        'fast_forward': 8,
        'none': 0
    }
    SEXUAL_KEYWORDS = ['sex', 'sexual', 'naked', 'nude', 'explicit', 'rape', 'intercourse', 'seduce', 'seduction']
    VIOLENCE_KEYWORDS = ['kill', 'killed', 'murder', 'shot', 'shoot', 'stab', 'blood', 'violence', 'violent', 'attack', 'fight', 'gun', 'weapon', 'death', 'die', 'dying', 'dead', 'assault', 'beat', 'beating', 'punch', 'hit']
    LANGUAGE_KEYWORDS = ['hell']
    
    def __init__(self):
        """Initialize the content analyzer."""
        profanity.load_censor_words()
    
    def analyze(self, text: str, user_preferences: Dict) -> str:
        """
        Analyze text and return playback action based on user preferences.
        
        Args:
            text: Caption or transcript text to analyze
            user_preferences: User's filtering preferences
            
        Returns:
            One of: 'mute', 'skip', 'fast_forward', 'none'
        """
        if not text:
            return 'none'
        """Shallow analysis that maps severities to a single action string for legacy APIs."""
        text_lower = text.lower()
        
        # Check language (profanity) filter
        if user_preferences.get('language_filter', True):
            language_severity = self._check_language(text_lower)
            threshold = self.SENSITIVITY_THRESHOLDS.get(
                user_preferences.get('language_sensitivity', 'medium'), 2
            )
            if language_severity >= threshold:
                return 'mute'  # Mute for brief profanity
        
        # Check sexual content filter
        if user_preferences.get('sexual_content_filter', True):
            sexual_severity = self._check_sexual_content(text_lower)
            threshold = self.SENSITIVITY_THRESHOLDS.get(
                user_preferences.get('sexual_content_sensitivity', 'medium'), 2
            )
            if sexual_severity >= threshold:
                return 'skip'  # Skip sexual content scenes
        
        # Check violence filter
        if user_preferences.get('violence_filter', True):
            violence_severity = self._check_violence(text_lower)
            threshold = self.SENSITIVITY_THRESHOLDS.get(
                user_preferences.get('violence_sensitivity', 'medium'), 2
            )
            if violence_severity >= threshold:
                return 'fast_forward'  # Fast forward through violence
        
        return 'none'
    
    def _check_language(self, text: str) -> int:
        """Count profane words using the library plus manual mild keywords (e.g., 'hell')."""
        score = 0
        if profanity.contains_profanity(text):
            words = text.split()
            score += sum(1 for word in words if profanity.contains_profanity(word))

        # Manual lightweight keyword list for missed mild profanities
        score += self._count_whole_words(text, self.LANGUAGE_KEYWORDS)
        return score
    
    def _check_sexual_content(self, text: str) -> int:
        """Count sexual-pattern matches to drive skip decisions for explicit scenes."""
        severity = self._count_whole_words(text, self.SEXUAL_KEYWORDS)
        for pattern in self.SEXUAL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            severity += len(matches)
        return severity
    
    def _check_violence(self, text: str) -> int:
        """Count violence-pattern matches to fast-forward through fights/blood."""
        severity = self._count_whole_words(text, self.VIOLENCE_KEYWORDS)
        for pattern in self.VIOLENCE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            severity += len(matches)
        return severity

    def _count_whole_words(self, text: str, words: List[str]) -> int:
        """Utility to count whole-word hits so partial matches don't inflate severity."""
        count = 0
        for word in words:
            count += len(re.findall(rf'\b{re.escape(word)}\b', text, re.IGNORECASE))
        return count

    def analyze_decision(self, text: str, preferences: Dict, confidence: float | None = None) -> Dict:
        """Return structured decision with priority: sexual > violence > language."""

        def base_decision(reason: str) -> Dict:
            return {
                "action": "none",
                "duration_seconds": 0,
                "matched_category": None,
                "reason": reason
            }

        if not text:
            return base_decision("No match")

        if not preferences.get('enabled', True):
            return base_decision("Filtering disabled")

        blocklist = preferences.get('blocklist') if isinstance(preferences.get('blocklist'), dict) else {}
        items = blocklist.get('items') if isinstance(blocklist.get('items'), list) else []
        if blocklist.get('enabled') and items:
            duration = blocklist.get('duration') or self.DEFAULT_DURATIONS.get('mute', 4)
            for raw_item in items:
                item = str(raw_item).strip()
                if not item:
                    continue
                if ' ' in item:
                    if item.lower() in text.lower():
                        return {
                            "action": "mute",
                            "duration_seconds": duration,
                            "matched_category": "blocklist",
                            "reason": f"blocklist match: {item}"
                        }
                else:
                    pattern = rf'\b{re.escape(item)}\b'
                    if re.search(pattern, text, re.IGNORECASE):
                        return {
                            "action": "mute",
                            "duration_seconds": duration,
                            "matched_category": "blocklist",
                            "reason": f"blocklist match: {item}"
                        }

        text_lower = text.lower()
        severities = {
            'language': self._check_language(text_lower),
            'sexual': self._check_sexual_content(text_lower),
            'violence': self._check_violence(text_lower)
        }

        def threshold_for(category: str) -> int:
            categories = preferences.get('categories', {}) if isinstance(preferences.get('categories'), dict) else {}
            cat_config = categories.get(category, {}) if isinstance(categories, dict) else {}
            sensitivity_value = cat_config.get('sensitivity') or preferences.get('sensitivity', 0.7)
            if isinstance(sensitivity_value, str):
                return self.SENSITIVITY_THRESHOLDS.get(sensitivity_value, 2)
            numeric = float(sensitivity_value)
            if numeric < 0.34:
                return self.SENSITIVITY_THRESHOLDS['low']
            if numeric < 0.67:
                return self.SENSITIVITY_THRESHOLDS['medium']
            return self.SENSITIVITY_THRESHOLDS['high']

        def category_config(category: str) -> Dict:
            categories = preferences.get('categories', {}) if isinstance(preferences.get('categories'), dict) else {}
            config = categories.get(category, {}) if isinstance(categories, dict) else {}
            action = config.get('action') or ('mute' if category == 'language' else 'skip')
            duration = config.get('duration') or self.DEFAULT_DURATIONS.get(action, 4)
            enabled = config.get('enabled', True)
            return {
                'action': action,
                'duration': duration,
                'enabled': enabled,
            }

        for category in ['sexual', 'violence', 'language']:
            config = category_config(category)
            if not config['enabled']:
                continue

            threshold = threshold_for(category)
            if severities[category] < threshold:
                continue

            action = config['action']
            duration = config.get('duration') or self.DEFAULT_DURATIONS.get(action, 4)
            reason_parts = [
                f"{category} content detected",
                f"severity={severities[category]}",
                f"threshold={threshold}",
                f"action={action}",
                f"duration={duration}",
            ]
            if confidence is not None:
                reason_parts.append(f"confidence={confidence}")

            return {
                "action": action,
                "duration_seconds": duration,
                "matched_category": category,
                "reason": "; ".join(reason_parts)
            }

        return base_decision("No match")
