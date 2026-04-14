"""
ISWEEP COMPONENT: Content Analyzer
# Explains this file belongs to the ISWEEP content analyzer module

This module inspects caption text and assigns playback actions (mute/skip/fast_forward/none)
# States the main purpose: map captions to playback controls
based on user preferences. It is invoked by /event so the extension can react in real time.
# Notes when this analyzer is called (via /event)

System connection:
    Extension sends caption -> Backend /event -> ContentAnalyzer.analyze_decision -> decision JSON
# Shows end-to-end data flow from extension to backend decision
"""

import re  # Imports regex utilities for pattern matching
import hashlib  # Stable marker ids for deterministic scheduling
import importlib
import os

# Seconds to shift audio-derived mute markers earlier so the audio is
# already silent when the speaker reaches the flagged word.
# Layered with the scheduler's MARKER_FIRE_EARLY_SEC for a total lead time
# of ~400 ms (200 ms pre-roll + 200 ms early-fire).
AUDIO_MUTE_PREROLL_SEC: float = 0.20
DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT = 'test profanity fuck'
from typing import Dict, List  # Imports type annotations for dictionaries and lists
from better_profanity import profanity  # Imports third-party profanity checker


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, '')).strip().lower() in {'1', 'true', 'yes', 'on'}


class Phase1AudioTranscriptionAdapter:
    """Phase 1 local transcription adapter.

    This adapter is intentionally small and swappable. It lets us validate the
    end-to-end audio-ahead control flow (capture -> backend -> markers -> scheduler)
    without coupling Phase 1 to a heavy STT engine.

    Behavior:
      - Reads optional env var ISWEEP_AUDIO_AHEAD_STUB_TEXT.
      - If set, returns one transcript segment spanning the chunk window.
      - If unset in dev or while no STT provider is configured, returns a
        deterministic fallback transcript so audio-ahead timing can be validated.
    """

    def _use_dev_fallback(self) -> bool:
        if _env_flag('ISWEEP_DEV_MODE'):
            return True
        if str(os.getenv('FLASK_ENV', '')).strip().lower() == 'development':
            return True
        if _env_flag('FLASK_DEBUG'):
            return True
        return not str(os.getenv('ISWEEP_AUDIO_AHEAD_PROVIDER', '')).strip()

    def transcribe(
        self,
        audio_chunk: str,
        mime_type: str,
        start_seconds: float,
        end_seconds: float,
    ) -> List[Dict]:
        if 'wav' not in (mime_type or '').lower():
            raise RuntimeError('transcription_unavailable')

        if not audio_chunk:
            raise RuntimeError('analyze_exception')

        stub_text = os.getenv('ISWEEP_AUDIO_AHEAD_STUB_TEXT', '').strip()
        if stub_text:
            transcript_text = stub_text
        elif self._use_dev_fallback():
            transcript_text = DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT
        else:
            raise RuntimeError('transcription_unavailable')

        duration = max(float(end_seconds) - float(start_seconds), 0.0)
        return [{'text': transcript_text, 'start': 0.0, 'duration': duration}]


class ContentAnalyzer:
    """Analyzes caption/transcript text and determines playback control actions."""
    # Class docstring describes purpose of the analyzer

    # Define content patterns for different categories
    VIOLENCE_PATTERNS = [
        r'\b(kill|killed|murder|shot|shoot|stab|blood|violence|violent|attack|fight|gun|weapon)\b',  # Regex for common violence terms
        r'\b(death|die|dying|dead)\b',  # Regex for death-related words
        r'\b(assault|beat|beating|punch|hit)\b'  # Regex for assault/fighting words
    ]

    SEXUAL_PATTERNS = [
        r'\b(sex|sexual|naked|nude|explicit)\b',  # Regex for explicit/sexual terms
        r'\b(rape|assault|abuse)\b',  # Regex for severe sexual violence terms
        r'\b(intercourse|seduce|seduction)\b'  # Regex for intercourse/innuendo terms
    ]

    # Sensitivity thresholds (number of matches before triggering action)
    SENSITIVITY_THRESHOLDS = {
        'low': 5,      # Very lenient: needs many matches
        'medium': 2,   # Moderate sensitivity
        'high': 1      # Very strict: one match triggers action
    }
    SENSITIVITY_ACTIONS = {
        'low': ('mute', 5),          # Low sensitivity maps to mute for 5 seconds
        'medium': ('fast_forward', 10),  # Medium sensitivity maps to fast-forward for 10 seconds
        'high': ('skip', 15)         # High sensitivity maps to skip for 15 seconds
    }
    DEFAULT_DURATIONS = {
        'mute': 4,           # Default mute duration in seconds
        'skip': 12,          # Default skip duration in seconds
        'fast_forward': 8,   # Default fast-forward duration in seconds
        'none': 0            # Default duration when no action is taken
    }
    SEXUAL_KEYWORDS = ['sex', 'sexual', 'naked', 'nude', 'explicit', 'rape', 'intercourse', 'seduce', 'seduction']  # Simple keyword list for sexual content
    VIOLENCE_KEYWORDS = ['kill', 'killed', 'murder', 'shot', 'shoot', 'stab', 'blood', 'violence', 'violent', 'attack', 'fight', 'gun', 'weapon', 'death', 'die', 'dying', 'dead', 'assault', 'beat', 'beating', 'punch', 'hit']  # Simple keyword list for violence
    LANGUAGE_KEYWORDS = ['hell']  # Mild language keyword not always caught by the library
    PROFANITY_KEYWORDS = [
        'fuck', 'fucking', 'fucked', 'bitch', 'shit', 'asshole', 'bastard', 'damn', 'crap'
    ]  # Explicit language the library occasionally misses with punctuation variants

    def __init__(self):
        """Initialize the content analyzer."""
        profanity.load_censor_words()  # Load the profanity word list into memory
        self.audio_transcription_adapter = Phase1AudioTranscriptionAdapter()

    def analyze(self, text: str, user_preferences: Dict) -> str:
        """
        Analyze text and return playback action based on user preferences.
        # Explains this is a legacy simple API returning just an action string

        Args:
            text: Caption or transcript text to analyze  # Describes incoming caption
            user_preferences: User's filtering preferences  # Describes user config

        Returns:
            One of: 'mute', 'skip', 'fast_forward', 'none'  # Lists possible outputs
        """
        if not text:
            return 'none'  # If no text provided, do nothing
        """Shallow analysis that maps severities to a single action string for legacy APIs."""
        text_lower = text.lower()  # Normalize text for case-insensitive checks

        # Check language (profanity) filter
        if user_preferences.get('language_filter', True):
            language_severity = self._check_language(text_lower)  # Count profanity severity
            threshold = self.SENSITIVITY_THRESHOLDS.get(
                user_preferences.get('language_sensitivity', 'medium'), 2
            )  # Pick threshold based on preferences with default medium
            if language_severity >= threshold:
                return 'mute'  # Mute when profanity meets threshold

        # Check sexual content filter
        if user_preferences.get('sexual_content_filter', True):
            sexual_severity = self._check_sexual_content(text_lower)  # Count sexual content severity
            threshold = self.SENSITIVITY_THRESHOLDS.get(
                user_preferences.get('sexual_content_sensitivity', 'medium'), 2
            )  # Threshold from preferences with default medium
            if sexual_severity >= threshold:
                return 'skip'  # Skip scenes with sexual content

        # Check violence filter
        if user_preferences.get('violence_filter', True):
            violence_severity = self._check_violence(text_lower)  # Count violence severity
            threshold = self.SENSITIVITY_THRESHOLDS.get(
                user_preferences.get('violence_sensitivity', 'medium'), 2
            )  # Threshold from preferences with default medium
            if violence_severity >= threshold:
                return 'fast_forward'  # Fast-forward through violent segments

        return 'none'  # Default action when nothing triggers

    def _check_language(self, text: str) -> int:
        """Count profane words using the library plus manual mild keywords (e.g., 'hell')."""
        normalized = text.lower()
        words = re.findall(r"[A-Za-z']+", normalized)

        # Count per-word profanity so punctuation-adjacent terms still register
        score = sum(1 for word in words if profanity.contains_profanity(word))

        # Manual lists backstop the library for explicit and mild terms
        score += self._count_whole_words(normalized, self.PROFANITY_KEYWORDS)
        score += self._count_whole_words(normalized, self.LANGUAGE_KEYWORDS)
        return score  # Return total language severity

    def _check_sexual_content(self, text: str) -> int:
        """Count sexual-pattern matches to drive skip decisions for explicit scenes."""
        severity = self._count_whole_words(text, self.SEXUAL_KEYWORDS)  # Count exact keyword hits
        for pattern in self.SEXUAL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)  # Find regex matches for sexual patterns
            severity += len(matches)  # Add number of regex matches to severity
        return severity  # Return sexual content severity

    def _check_violence(self, text: str) -> int:
        """Count violence-pattern matches to fast-forward through fights/blood."""
        severity = self._count_whole_words(text, self.VIOLENCE_KEYWORDS)  # Count exact violence keyword hits
        for pattern in self.VIOLENCE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)  # Find regex matches for violence patterns
            severity += len(matches)  # Add number of regex matches to severity
        return severity  # Return violence severity

    def _count_whole_words(self, text: str, words: List[str]) -> int:
        """Utility to count whole-word hits so partial matches don't inflate severity."""
        count = 0  # Initialize counter
        for word in words:
            count += len(re.findall(rf'\b{re.escape(word)}\b', text, re.IGNORECASE))  # Count whole-word matches for each keyword
        return count  # Return total matches for provided keywords

    def analyze_decision(self, text: str, preferences: Dict, confidence: float | None = None) -> Dict:
        """Return structured decision with priority: sexual > violence > language."""

        def base_decision(reason: str) -> Dict:
            return {
                "action": "none",             # Default action is none
                "duration_seconds": 0,        # Default duration when no action
                "matched_category": None,     # No category matched yet
                "reason": reason              # Explanation for the decision
            }

        if not text:
            return base_decision("No match")  # If empty text, return default decision

        if not preferences.get('enabled', True):
            return base_decision("Filtering disabled")  # If filtering disabled, return default

        blocklist = preferences.get('blocklist') if isinstance(preferences.get('blocklist'), dict) else {}  # Safely read blocklist config
        items = blocklist.get('items') if isinstance(blocklist.get('items'), list) else []  # Extract blocklist items if list
        if blocklist.get('enabled') and items:
            duration = blocklist.get('duration') or self.DEFAULT_DURATIONS.get('mute', 4)  # Duration for blocklist action
            for raw_item in items:
                item = str(raw_item).strip()  # Normalize each blocklist entry to string
                if not item:
                    continue  # Skip empty strings
                if ' ' in item:
                    if item.lower() in text.lower():  # Substring match for multi-word phrases
                        return {
                            "action": "mute",
                            "duration_seconds": duration,
                            "matched_category": "blocklist",
                            "reason": f"blocklist match: {item}"
                        }
                else:
                    pattern = rf'\b{re.escape(item)}\b'  # Whole-word regex for single words
                    if re.search(pattern, text, re.IGNORECASE):  # Match single-word blocklist item
                        return {
                            "action": "mute",
                            "duration_seconds": duration,
                            "matched_category": "blocklist",
                            "reason": f"blocklist match: {item}"
                        }

        text_lower = text.lower()  # Normalize text for severity checks
        severities = {
            'language': self._check_language(text_lower),       # Profanity severity count
            'sexual': self._check_sexual_content(text_lower),   # Sexual content severity count
            'violence': self._check_violence(text_lower)        # Violence severity count
        }

        def threshold_for(category: str) -> int:
            categories = preferences.get('categories', {}) if isinstance(preferences.get('categories'), dict) else {}  # Pull category-level config map
            cat_config = categories.get(category, {}) if isinstance(categories, dict) else {}  # Config for specific category
            sensitivity_value = cat_config.get('sensitivity') or preferences.get('sensitivity', 0.7)  # Sensitivity override or global default
            if isinstance(sensitivity_value, str):
                return self.SENSITIVITY_THRESHOLDS.get(sensitivity_value, 2)  # Map string sensitivity to threshold
            numeric = float(sensitivity_value)  # Cast numeric sensitivity
            if numeric < 0.34:
                return self.SENSITIVITY_THRESHOLDS['low']  # Low threshold if numeric below 0.34
            if numeric < 0.67:
                return self.SENSITIVITY_THRESHOLDS['medium']  # Medium threshold if numeric below 0.67
            return self.SENSITIVITY_THRESHOLDS['high']  # Otherwise high threshold

        def category_config(category: str) -> Dict:
            categories = preferences.get('categories', {}) if isinstance(preferences.get('categories'), dict) else {}  # Pull category configuration map
            config = categories.get(category, {}) if isinstance(categories, dict) else {}  # Specific category settings
            action = config.get('action') or ('mute' if category == 'language' else 'skip')  # Default action fallback per category
            duration = config.get('duration') or self.DEFAULT_DURATIONS.get(action, 4)  # Duration fallback using defaults
            enabled = config.get('enabled', True)  # Whether this category is enabled
            return {
                'action': action,
                'duration': duration,
                'enabled': enabled,
            }

        for category in ['sexual', 'violence', 'language']:
            config = category_config(category)  # Get configuration for this category
            if not config['enabled']:
                continue  # Skip disabled categories

            threshold = threshold_for(category)  # Get threshold for this category
            if severities[category] < threshold:
                continue  # If severity is below threshold, move on

            action = config['action']  # Action chosen for this category
            duration = config.get('duration') or self.DEFAULT_DURATIONS.get(action, 4)  # Duration chosen with default fallback
            reason_parts = [
                f"{category} content detected",           # Note which category matched
                f"severity={severities[category]}",       # Include measured severity
                f"threshold={threshold}",                 # Include threshold used
                f"action={action}",                       # Include action selected
                f"duration={duration}",                   # Include duration selected
            ]
            if confidence is not None:
                reason_parts.append(f"confidence={confidence}")  # Add optional confidence if provided

            return {
                "action": action,
                "duration_seconds": duration,
                "matched_category": category,
                "reason": "; ".join(reason_parts)
            }

        return base_decision("No match")  # Fallback when nothing triggers

    def _fetch_transcript_segments(self, video_id: str) -> List[Dict]:
        """Fetch transcript segments from YouTube when available."""
        try:
            yta_module = importlib.import_module('youtube_transcript_api')
            errors_module = importlib.import_module('youtube_transcript_api._errors')
        except Exception as exc:
            raise RuntimeError("transcript dependency unavailable") from exc

        YouTubeTranscriptApi = getattr(yta_module, 'YouTubeTranscriptApi')
        NoTranscriptFound = getattr(errors_module, 'NoTranscriptFound', Exception)
        TranscriptsDisabled = getattr(errors_module, 'TranscriptsDisabled', Exception)
        VideoUnavailable = getattr(errors_module, 'VideoUnavailable', Exception)
        CouldNotRetrieveTranscript = getattr(errors_module, 'CouldNotRetrieveTranscript', Exception)

        try:
            raw_segments = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        except TypeError:
            # Some versions do not support the languages keyword.
            raw_segments = YouTubeTranscriptApi.get_transcript(video_id)
        except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable, CouldNotRetrieveTranscript):
            return []

        segments: List[Dict] = []
        for row in raw_segments or []:
            try:
                text = str(row.get('text') or '').strip()
                start = float(row.get('start', 0))
                duration = float(row.get('duration', 0))
            except (TypeError, ValueError):
                continue
            if not text:
                continue
            if start < 0:
                start = 0.0
            if duration < 0:
                duration = 0.0
            segments.append({
                'text': text,
                'start': start,
                'duration': duration,
            })
        return segments

    def _stable_marker_id(self, video_id: str, start_seconds: float, end_seconds: float, action: str, category: str) -> str:
        """Create deterministic marker id from video + timing + action tuple."""
        raw = f"{video_id}|{start_seconds:.3f}|{end_seconds:.3f}|{action}|{category}"
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]

    def _merge_marker_events(self, events: List[Dict]) -> List[Dict]:
        """Merge same-kind overlaps; trim conflicting overlaps for deterministic non-overlapping output."""
        if not events:
            return []

        sorted_events = sorted(events, key=lambda event: (event['start_seconds'], event['end_seconds'], event['action']))
        merged: List[Dict] = []

        for event in sorted_events:
            current = dict(event)
            if current['end_seconds'] <= current['start_seconds']:
                continue

            if not merged:
                merged.append(current)
                continue

            previous = merged[-1]

            # Same behavior/category + overlap/touching: merge windows.
            if (
                current['start_seconds'] <= previous['end_seconds']
                and current['action'] == previous['action']
                and current['matched_category'] == previous['matched_category']
            ):
                previous['end_seconds'] = max(previous['end_seconds'], current['end_seconds'])
                previous['duration_seconds'] = round(previous['end_seconds'] - previous['start_seconds'], 3)
                continue

            # Conflicting overlap: trim current start to keep non-overlapping markers.
            if current['start_seconds'] < previous['end_seconds']:
                current['start_seconds'] = previous['end_seconds']
                current['duration_seconds'] = round(current['end_seconds'] - current['start_seconds'], 3)
                if current['duration_seconds'] <= 0:
                    continue

            merged.append(current)

        return merged

    def analyze_video_markers(self, video_id: str, preferences: Dict) -> Dict:
        """Build watch-ahead markers for a YouTube video transcript."""
        try:
            segments = self._fetch_transcript_segments(video_id)
        except RuntimeError:
            return {
                'status': 'error',
                'source': None,
                'events': [],
            }

        if not segments:
            return {
                'status': 'unavailable',
                'source': None,
                'events': [],
            }

        events: List[Dict] = []
        for segment in segments:
            text = segment.get('text') or ''
            start_seconds = float(segment.get('start', 0) or 0)
            transcript_duration = float(segment.get('duration', 0) or 0)

            decision = self.analyze_decision(text, preferences)
            action = decision.get('action')
            if action not in {'mute', 'skip', 'fast_forward'}:
                continue

            decision_duration = float(decision.get('duration_seconds') or 0)
            effective_duration = decision_duration if decision_duration > 0 else transcript_duration
            if effective_duration <= 0:
                continue

            end_seconds = start_seconds + effective_duration
            category = decision.get('matched_category') or 'language'

            events.append({
                'id': self._stable_marker_id(video_id, start_seconds, end_seconds, action, category),
                'start_seconds': round(start_seconds, 3),
                'end_seconds': round(end_seconds, 3),
                'action': action,
                'duration_seconds': round(effective_duration, 3),
                'matched_category': category,
                'reason': decision.get('reason') or 'transcript match',
            })

        merged_events = self._merge_marker_events(events)
        for event in merged_events:
            event['id'] = self._stable_marker_id(
                video_id,
                event['start_seconds'],
                event['end_seconds'],
                event['action'],
                event['matched_category'],
            )

        return {
            'status': 'ready',
            'source': 'transcript',
            'events': merged_events,
        }

    def analyze_audio_chunk(
        self,
        audio_chunk: str,
        mime_type: str,
        start_seconds: float,
        end_seconds: float,
        preferences: Dict,
        video_id: str = '',
    ) -> Dict:
        """Transcribe an audio chunk and return time-offset marker events.

        Parameters
        ----------
        audio_chunk : encoded WAV audio from the extension
        mime_type : MIME type hint (e.g. 'audio/wav')
        start_seconds : absolute video time when this chunk started
        end_seconds : absolute video time when this chunk ended
        preferences : user filter preferences
        video_id : YouTube video ID used for stable marker IDs
        """
        if not audio_chunk:
            return {
                'status': 'error',
                'source': 'audio_chunk',
                'events': [],
                'failure_reason': 'analyze_exception',
            }

        try:
            segments = self.audio_transcription_adapter.transcribe(
                audio_chunk=audio_chunk,
                mime_type=mime_type,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        except RuntimeError as exc:
            reason = str(exc)
            normalized_reason = reason if reason in {
                'transcription_unavailable',
                'analyze_exception',
            } else 'analyze_exception'
            status = 'unavailable' if normalized_reason == 'transcription_unavailable' else 'error'
            return {
                'status': status,
                'source': 'audio_chunk',
                'events': [],
                'failure_reason': normalized_reason,
            }

        transcription_text = ' '.join(
            str(segment.get('text') or '').strip()
            for segment in segments
            if str(segment.get('text') or '').strip()
        )
        print(f'[ISWEEP][AUDIO_AHEAD] transcription used: {transcription_text}')

        if not segments:
            return {'status': 'unavailable', 'source': 'audio_chunk', 'events': [],
                    'failure_reason': 'transcription_unavailable'}

        events: List[Dict] = []
        for segment in segments:
            text = segment.get('text') or ''
            rel_start = float(segment.get('start', 0) or 0)
            rel_duration = float(segment.get('duration', 0) or 0)
            abs_start = round(start_seconds + rel_start, 3)

            decision = self.analyze_decision(text, preferences)
            action = decision.get('action')
            if action not in {'mute', 'skip', 'fast_forward'}:
                continue

            decision_duration = float(decision.get('duration_seconds') or 0)
            source_duration = rel_duration if rel_duration > 0 else max(end_seconds - start_seconds, 0)
            effective_duration = decision_duration if decision_duration > 0 else source_duration
            if effective_duration <= 0:
                continue

            abs_end = round(abs_start + effective_duration, 3)
            category = decision.get('matched_category') or 'language'

            # Apply pre-roll to mute markers so the mute starts before the
            # speaker reaches the flagged word.  Skip/fast_forward are not
            # shifted because their seek/rate logic depends on exact timing.
            if action == 'mute':
                adj_start = max(round(abs_start - AUDIO_MUTE_PREROLL_SEC, 3), 0.0)
                print(
                    f'[ISWEEP][AUDIO_AHEAD] audio marker created '
                    f'video_id={video_id!r} action={action!r} '
                    f'original_start={abs_start} adj_start={adj_start} '
                    f'end={abs_end} preroll={AUDIO_MUTE_PREROLL_SEC}s'
                )
            else:
                adj_start = abs_start
                print(
                    f'[ISWEEP][AUDIO_AHEAD] audio marker created '
                    f'video_id={video_id!r} action={action!r} '
                    f'start={abs_start} end={abs_end}'
                )

            events.append({
                'id': self._stable_marker_id(
                    video_id or 'audio', adj_start, abs_end, action, category),
                'start_seconds': adj_start,
                'end_seconds': abs_end,
                'action': action,
                'duration_seconds': round(effective_duration, 3),
                'matched_category': category,
                'reason': decision.get('reason') or 'audio chunk match',
            })

        merged = self._merge_marker_events(events)
        # Re-stamp IDs after merge since boundaries may have changed.
        for ev in merged:
            ev['id'] = self._stable_marker_id(
                video_id or 'audio',
                ev['start_seconds'], ev['end_seconds'],
                ev['action'], ev['matched_category'],
            )

        print(f'[ISWEEP][AUDIO_AHEAD] markers generated: {len(merged)}')

        return {
            'status': 'ready',
            'source': 'audio_chunk',
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'events': merged,
            'failure_reason': None,
        }
