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
# of ~220 ms total lead when combined with the content-script mute fire lead.
AUDIO_MUTE_PREROLL_SEC: float = 0.10
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

    def _collect_clean_caption_terms(self, preferences: Dict) -> List[str]:
        """Collect user-configured terms that should be masked in clean captions."""
        if not isinstance(preferences, dict):
            return []

        categories = preferences.get('categories') if isinstance(preferences.get('categories'), dict) else {}
        language = categories.get('language') if isinstance(categories.get('language'), dict) else {}
        candidates: List[str] = []

        blocklist = preferences.get('blocklist') if isinstance(preferences.get('blocklist'), dict) else {}
        if blocklist.get('enabled', True) and isinstance(blocklist.get('items'), list):
            candidates.extend(blocklist.get('items') or [])

        if language.get('enabled', True):
            for key in ['items', 'words', 'customWords']:
                values = language.get(key)
                if isinstance(values, list):
                    candidates.extend(values)
            if isinstance(preferences.get('customWords'), list):
                candidates.extend(preferences.get('customWords') or [])

        normalized: List[str] = []
        seen = set()
        for candidate in candidates:
            term = str(candidate or '').strip()
            if not term:
                continue
            lowered = term.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(term)
        return sorted(normalized, key=lambda value: (-len(value), value.lower()))

    def _mask_clean_caption_text(self, text: str, preferences: Dict) -> str:
        """Return overlay-safe text without mutating the original transcript segment."""
        if not text:
            return ''

        masked = str(text)
        for term in self._collect_clean_caption_terms(preferences):
            escaped = re.escape(term)
            if re.search(r'\s', term):
                pattern = re.compile(escaped, re.IGNORECASE)
            else:
                pattern = re.compile(rf'\b{escaped}\b', re.IGNORECASE)
            masked = pattern.sub('____', masked)

        def replace_profane_word(match: re.Match) -> str:
            word = match.group(0)
            return '____' if profanity.contains_profanity(word) else word

        masked = re.sub(r"[A-Za-z']+", replace_profane_word, masked)
        return masked

    def _is_clean_caption_word_filtered(self, word: str, preferences: Dict) -> bool:
        """Return true when a single word should be hidden in clean captions."""
        normalized = re.sub(r"[^A-Za-z0-9']", '', str(word or '')).strip().lower()
        if not normalized:
            return False
        if profanity.contains_profanity(normalized):
            return True

        terms = self._collect_clean_caption_terms(preferences)
        return any(
            ' ' not in term and normalized == re.sub(r"[^A-Za-z0-9']", '', term).strip().lower()
            for term in terms
        )

    def _build_cleaned_caption_entry(self, segment: Dict, preferences: Dict) -> Dict | None:
        """Build one cleaned caption entry with approximate word timing when needed."""
        text = str(segment.get('text') or '').strip()
        if not text:
            return None

        try:
            start_seconds = float(segment.get('start', 0) or 0)
            duration = float(segment.get('duration', 0) or 0)
        except (TypeError, ValueError):
            return None

        if start_seconds < 0:
            start_seconds = 0.0
        if duration < 0:
            duration = 0.0

        end_seconds = start_seconds + duration
        tokens = [match.group(0) for match in re.finditer(r"[A-Za-z0-9']+", text)]

        words: List[Dict] = []
        filtered_flags: List[bool] = []
        if tokens:
            step = duration / len(tokens) if duration > 0 else 0.0
            for index, token in enumerate(tokens):
                word_start = start_seconds + (step * index)
                word_end = start_seconds + (step * (index + 1)) if step > 0 else start_seconds
                if step > 0 and index == len(tokens) - 1:
                    word_end = end_seconds
                words.append({
                    'word': token,
                    'start': round(word_start, 3),
                    'end': round(max(word_end, word_start), 3),
                })
                filtered_flags.append(self._is_clean_caption_word_filtered(token, preferences))

        clean_resume_time = None
        first_blocked_word_start = None
        blocked_seen = False
        for index, is_filtered in enumerate(filtered_flags):
            if is_filtered:
                blocked_seen = True
                if first_blocked_word_start is None:
                    first_blocked_word_start = words[index]['start']
                continue
            if blocked_seen:
                clean_resume_time = words[index]['start']
                break

        entry: Dict = {
            'start_seconds': round(start_seconds, 3),
            'end_seconds': round(end_seconds, 3),
            'text': text,
            'clean_text': self._mask_clean_caption_text(text, preferences),
            'words': words,
        }
        if clean_resume_time is not None:
            entry['clean_resume_time'] = round(clean_resume_time, 3)
        if first_blocked_word_start is not None:
            entry['_first_blocked_word_start'] = round(first_blocked_word_start, 3)
        return entry

    def build_cleaned_captions(self, transcript_segments: List[Dict], preferences: Dict) -> List[Dict]:
        """Build timed display captions for the extension clean-caption overlay."""
        cleaned_captions: List[Dict] = []
        for segment in transcript_segments or []:
            entry = self._build_cleaned_caption_entry(segment, preferences)
            if not entry:
                continue
            entry.pop('_first_blocked_word_start', None)
            cleaned_captions.append(entry)

        return cleaned_captions

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
                'cleaned_captions': [],
                'clean_captions': [],
                'failure_reason': 'transcript_fetch_failed',
            }

        if not segments:
            return {
                'status': 'unavailable',
                'source': None,
                'events': [],
                'cleaned_captions': [],
                'clean_captions': [],
                'failure_reason': 'transcript_unavailable',
            }

        cleaned_entries = [self._build_cleaned_caption_entry(segment, preferences) for segment in segments]
        cleaned_captions = []
        for entry in cleaned_entries:
            if not entry:
                continue
            clean_entry = dict(entry)
            clean_entry.pop('_first_blocked_word_start', None)
            cleaned_captions.append(clean_entry)
        print(f'[ISWEEP][CLEAN_CC] cleaned captions generated video_id={video_id!r}')
        print(f'[ISWEEP][CLEAN_CC] cleaned caption count={len(cleaned_captions)} video_id={video_id!r}')

        events: List[Dict] = []
        for index, segment in enumerate(segments):
            text = segment.get('text') or ''
            start_seconds = float(segment.get('start', 0) or 0)
            transcript_duration = float(segment.get('duration', 0) or 0)
            cleaned_entry = cleaned_entries[index] if index < len(cleaned_entries) else None

            decision = self.analyze_decision(text, preferences)
            action = decision.get('action')
            if action not in {'mute', 'skip', 'fast_forward'}:
                continue

            decision_duration = float(decision.get('duration_seconds') or 0)
            effective_duration = decision_duration if decision_duration > 0 else transcript_duration
            if effective_duration <= 0:
                continue

            if action == 'mute' and cleaned_entry and cleaned_entry.get('_first_blocked_word_start') is not None:
                start_seconds = float(cleaned_entry.get('_first_blocked_word_start'))

            end_seconds = start_seconds + effective_duration
            if action == 'mute' and cleaned_entry and cleaned_entry.get('clean_resume_time') is not None:
                end_seconds = min(end_seconds, float(cleaned_entry.get('clean_resume_time')))
                effective_duration = end_seconds - start_seconds
                if effective_duration <= 0:
                    continue

            category = decision.get('matched_category') or 'language'

            event = {
                'id': self._stable_marker_id(video_id, start_seconds, end_seconds, action, category),
                'start_seconds': round(start_seconds, 3),
                'end_seconds': round(end_seconds, 3),
                'action': action,
                'duration_seconds': round(effective_duration, 3),
                'matched_category': category,
                'reason': decision.get('reason') or 'transcript match',
            }
            if action == 'mute' and cleaned_entry and cleaned_entry.get('clean_resume_time') is not None:
                event['clean_resume_time'] = round(float(cleaned_entry.get('clean_resume_time')), 3)
            events.append(event)

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
            'cleaned_captions': cleaned_captions,
            'clean_captions': cleaned_captions,
            'failure_reason': None,
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
                    f'chunk_start={start_seconds} chunk_end={end_seconds} '
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
