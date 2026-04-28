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
import base64
import tempfile
from io import BytesIO

# Seconds to shift audio-derived mute markers earlier so the audio is
# already silent when the speaker reaches the flagged word.
# Layered with the scheduler's MARKER_FIRE_EARLY_SEC for a total lead time
# of ~220 ms total lead when combined with the content-script mute fire lead.
AUDIO_MUTE_PREROLL_SEC: float = 0.10
DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT = 'test profanity fuck'
CHUNK_DURATION_SEC: float = float(os.getenv('ISWEEP_AUDIO_CHUNK_SEC', '2') or '2')
CHUNK_OVERLAP_SEC: float = 0.5
from typing import Dict, List  # Imports type annotations for dictionaries and lists
from better_profanity import profanity  # Imports third-party profanity checker


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, '')).strip().lower() in {'1', 'true', 'yes', 'on'}


class SpeechToTextAdapter:
    """Interface for optional word-level speech-to-text timing providers."""

    def transcribe_with_word_timestamps(
        self,
        audio_path_or_bytes,
        text_hint: str = '',
        start_seconds: float = 0.0,
        duration_seconds: float = 0.0,
    ) -> Dict:
        raise NotImplementedError()


class FasterWhisperSpeechToTextAdapter(SpeechToTextAdapter):
    """Optional faster-whisper adapter loaded only when STT is enabled."""

    def __init__(self, model_size: str = 'base', device: str = 'cpu', compute_type: str = 'int8'):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            fw_module = importlib.import_module('faster_whisper')
            WhisperModel = getattr(fw_module, 'WhisperModel')
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            return self._model
        except Exception as exc:  # pragma: no cover - environment dependent import/runtime
            raise RuntimeError('stt_unavailable') from exc

    def transcribe_with_word_timestamps(
        self,
        audio_path_or_bytes,
        text_hint: str = '',
        start_seconds: float = 0.0,
        duration_seconds: float = 0.0,
    ) -> Dict:
        if audio_path_or_bytes is None:
            raise RuntimeError('stt_unavailable')

        model = self._ensure_model()
        audio_input = BytesIO(audio_path_or_bytes) if isinstance(audio_path_or_bytes, (bytes, bytearray)) else audio_path_or_bytes

        segments, _ = model.transcribe(
            audio_input,
            word_timestamps=True,
            vad_filter=True,
            language='en',
        )

        words: List[Dict] = []
        for segment in segments:
            for word in (getattr(segment, 'words', None) or []):
                word_text = str(getattr(word, 'word', '') or '').strip()
                word_start = getattr(word, 'start', None)
                word_end = getattr(word, 'end', None)
                if not word_text:
                    continue
                if word_start is None or word_end is None:
                    continue
                words.append({
                    'word': word_text,
                    'start': round(max(start_seconds + float(word_start), 0.0), 3),
                    'end': round(max(start_seconds + float(word_end), start_seconds + float(word_start)), 3),
                    'source': 'whisper',
                })

        return {'words': words}


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
        mime = (mime_type or '').lower()
        if not any(kind in mime for kind in ('wav', 'webm', 'ogg', 'mp4', 'mpeg', 'mp3')):
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

    def __init__(self, speech_to_text_adapter: SpeechToTextAdapter | None = None):
        """Initialize the content analyzer."""
        profanity.load_censor_words()  # Load the profanity word list into memory
        self.audio_transcription_adapter = Phase1AudioTranscriptionAdapter()
        self.stt_enabled = _env_flag('ISWEEP_STT_ENABLED')
        self.stt_model_size = str(os.getenv('ISWEEP_STT_MODEL_SIZE', 'base') or 'base').strip() or 'base'
        self.stt_device = str(os.getenv('ISWEEP_STT_DEVICE', 'cpu') or 'cpu').strip() or 'cpu'
        self.stt_compute_type = str(os.getenv('ISWEEP_STT_COMPUTE_TYPE', 'int8') or 'int8').strip() or 'int8'
        self.speech_to_text_adapter = speech_to_text_adapter
        if self.stt_enabled:
            print('[ISWEEP][STT] whisper enabled', {
                'model': self.stt_model_size,
                'device': self.stt_device,
                'compute_type': self.stt_compute_type,
            })
        else:
            print('[ISWEEP][STT] disabled fallback estimated')

    def get_stt_cache_mode(self) -> Dict:
        """Expose STT mode so cache keys can include timing source behavior."""
        if not self.stt_enabled:
            return {'enabled': False, 'model': None}
        return {'enabled': True, 'model': self.stt_model_size}

    def _get_or_create_stt_adapter(self) -> SpeechToTextAdapter | None:
        if self.speech_to_text_adapter is not None:
            return self.speech_to_text_adapter
        if not self.stt_enabled:
            return None
        self.speech_to_text_adapter = FasterWhisperSpeechToTextAdapter(
            model_size=self.stt_model_size,
            device=self.stt_device,
            compute_type=self.stt_compute_type,
        )
        return self.speech_to_text_adapter

    def _estimate_word_timings(self, text: str, start_seconds: float, duration: float) -> List[Dict]:
        tokens = [match.group(0) for match in re.finditer(r"[A-Za-z0-9']+", text)]
        if not tokens:
            return []

        words: List[Dict] = []
        step = duration / len(tokens) if duration > 0 else 0.0
        end_seconds = start_seconds + duration
        for index, token in enumerate(tokens):
            word_start = start_seconds + (step * index)
            word_end = start_seconds + (step * (index + 1)) if step > 0 else start_seconds
            if step > 0 and index == len(tokens) - 1:
                word_end = end_seconds
            words.append({
                'word': token,
                'start': round(word_start, 3),
                'end': round(max(word_end, word_start), 3),
                'source': 'estimated',
            })
        return words

    def _build_segment_word_timings(self, segment: Dict, text: str, start_seconds: float, duration: float) -> List[Dict]:
        provided_word_timings = segment.get('word_timings') if isinstance(segment.get('word_timings'), list) else None
        if provided_word_timings:
            normalized_provided: List[Dict] = []
            for word in provided_word_timings:
                if not isinstance(word, dict):
                    continue
                w = str(word.get('word') or '').strip()
                if not w:
                    continue
                try:
                    ws = float(word.get('start'))
                    we = float(word.get('end'))
                except (TypeError, ValueError):
                    continue
                if we < ws:
                    continue
                normalized_provided.append({
                    'word': w,
                    'start': round(ws, 3),
                    'end': round(we, 3),
                    'source': str(word.get('source') or 'whisper'),
                })
            if normalized_provided:
                print('[ISWEEP][STT] word timestamps generated', {'count': len(normalized_provided)})
                return normalized_provided

        estimated_words = self._estimate_word_timings(text, start_seconds, duration)

        if not self.stt_enabled:
            print('[ISWEEP][STT] disabled fallback estimated')
            return estimated_words

        adapter = self._get_or_create_stt_adapter()
        if adapter is None:
            print('[ISWEEP][STT] unavailable fallback estimated', {'reason': 'adapter_missing'})
            return estimated_words

        audio_payload = segment.get('audio_path_or_bytes')
        if audio_payload is None:
            print('[ISWEEP][STT] unavailable fallback estimated', {'reason': 'missing_audio'})
            return estimated_words

        try:
            result = adapter.transcribe_with_word_timestamps(
                audio_payload,
                text_hint=text,
                start_seconds=start_seconds,
                duration_seconds=duration,
            )
        except RuntimeError:
            print('[ISWEEP][STT] unavailable fallback estimated', {'reason': 'runtime_unavailable'})
            return estimated_words
        except Exception:
            print('[ISWEEP][STT] unavailable fallback estimated', {'reason': 'unexpected_error'})
            return estimated_words

        words = result.get('words') if isinstance(result, dict) else None
        if not isinstance(words, list) or not words:
            print('[ISWEEP][STT] unavailable fallback estimated', {'reason': 'no_words'})
            return estimated_words

        normalized_words = []
        for word in words:
            if not isinstance(word, dict):
                continue
            w = str(word.get('word') or '').strip()
            start = word.get('start')
            end = word.get('end')
            if not w:
                continue
            if start is None or end is None:
                continue
            try:
                ws = float(start)
                we = float(end)
            except (TypeError, ValueError):
                continue
            if we < ws:
                continue
            normalized_words.append({
                'word': w,
                'start': round(ws, 3),
                'end': round(we, 3),
                'source': str(word.get('source') or 'whisper'),
            })

        if not normalized_words:
            print('[ISWEEP][STT] unavailable fallback estimated', {'reason': 'normalized_empty'})
            return estimated_words

        print('[ISWEEP][STT] word timestamps generated', {'count': len(normalized_words)})
        return normalized_words

    def _decode_audio_chunk(self, audio_chunk: str) -> bytes:
        if not isinstance(audio_chunk, str):
            raise RuntimeError('audio_decode_failed')
        payload = audio_chunk.strip()
        if not payload:
            raise RuntimeError('audio_decode_failed')
        if payload.startswith('data:') and ',' in payload:
            payload = payload.split(',', 1)[1]
        try:
            decoded = base64.b64decode(payload, validate=False)
        except Exception as exc:
            raise RuntimeError('audio_decode_failed') from exc
        if not decoded:
            raise RuntimeError('audio_decode_failed')
        return decoded

    def _infer_audio_extension(self, mime_type: str) -> str:
        mime = (mime_type or '').lower()
        if 'webm' in mime:
            return '.webm'
        if 'ogg' in mime:
            return '.ogg'
        if 'mp4' in mime or 'aac' in mime:
            return '.m4a'
        if 'mpeg' in mime or 'mp3' in mime:
            return '.mp3'
        return '.wav'

    def _persist_audio_for_stt(self, decoded_audio: bytes, mime_type: str) -> str:
        suffix = self._infer_audio_extension(mime_type)
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            temp.write(decoded_audio)
            temp.flush()
            return temp.name
        finally:
            temp.close()

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
        """Build one cleaned caption entry with STT-derived or estimated word timing."""
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
        words = self._build_segment_word_timings(segment, text, start_seconds, duration)
        filtered_flags: List[bool] = []
        for word in words:
            filtered_flags.append(self._is_clean_caption_word_filtered(word.get('word', ''), preferences))

        clean_resume_time = None
        first_blocked_word_start = None
        first_blocked_word_source = None
        blocked_seen = False
        for index, is_filtered in enumerate(filtered_flags):
            if is_filtered:
                blocked_seen = True
                if first_blocked_word_start is None:
                    first_blocked_word_start = words[index]['start']
                    first_blocked_word_source = str(words[index].get('source') or '')
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
            if first_blocked_word_source:
                entry['_first_blocked_word_source'] = first_blocked_word_source
        return entry

    def build_cleaned_captions(self, transcript_segments: List[Dict], preferences: Dict) -> List[Dict]:
        """Build timed display captions for the extension clean-caption overlay."""
        cleaned_captions: List[Dict] = []
        for segment in transcript_segments or []:
            entry = self._build_cleaned_caption_entry(segment, preferences)
            if not entry:
                continue
            entry.pop('_first_blocked_word_start', None)
            entry.pop('_first_blocked_word_source', None)
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
            clean_entry.pop('_first_blocked_word_source', None)
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

            end_seconds = start_seconds + effective_duration

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
            if action == 'mute' and cleaned_entry and cleaned_entry.get('_first_blocked_word_start') is not None:
                event['blocked_word_start'] = round(float(cleaned_entry.get('_first_blocked_word_start')), 3)
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
                'cleaned_captions': [],
                'failure_reason': 'analyze_exception',
            }

        print('[ISWEEP][AUDIO_STT] chunk received', {
            'video_id': video_id,
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'mime_type': mime_type,
        })

        duration_seconds = max(float(end_seconds) - float(start_seconds), 0.0)
        try:
            decoded_audio = self._decode_audio_chunk(audio_chunk)
            print("[ISWEEP][AUDIO_DEBUG] Received audio bytes:", len(decoded_audio))
        except RuntimeError as err:
            print("[ISWEEP][AUDIO_DEBUG] Audio decode failed:", str(err))
            return {
                'status': 'error',
                'source': 'audio_chunk',
                'events': [],
                'cleaned_captions': [],
                'failure_reason': str(err) or 'audio_decode_failed',
            }

        whisper_words: List[Dict] = []
        stt_failure_reason: str | None = None
        stt_audio_path: str | None = None
        if self.stt_enabled:
            adapter = self._get_or_create_stt_adapter()
            if adapter is not None and decoded_audio:
                try:
                    print('[ISWEEP][AUDIO_STT] whisper started', {
                        'video_id': video_id,
                        'model': self.stt_model_size,
                    })
                    stt_audio_path = self._persist_audio_for_stt(decoded_audio, mime_type)
                    stt_result = adapter.transcribe_with_word_timestamps(
                        stt_audio_path,
                        text_hint='',
                        start_seconds=float(start_seconds),
                        duration_seconds=duration_seconds,
                    )
                    candidate_words = stt_result.get('words') if isinstance(stt_result, dict) else []
                    if isinstance(candidate_words, list):
                        whisper_words = [w for w in candidate_words if isinstance(w, dict)]
                    if whisper_words:
                        print('[ISWEEP][AUDIO_STT] word timestamps generated', {
                            'video_id': video_id,
                            'count': len(whisper_words),
                        })
                except RuntimeError:
                    stt_failure_reason = 'stt_unavailable'
                    print('[ISWEEP][AUDIO_STT] fallback used', {
                        'video_id': video_id,
                        'reason': stt_failure_reason,
                    })
                except Exception:
                    stt_failure_reason = 'transcription_failed'
                    print('[ISWEEP][AUDIO_STT] fallback used', {
                        'video_id': video_id,
                        'reason': stt_failure_reason,
                    })
                finally:
                    if stt_audio_path:
                        try:
                            os.unlink(stt_audio_path)
                        except OSError:
                            pass

        if whisper_words:
            transcript_text = ' '.join(str(word.get('word') or '').strip() for word in whisper_words).strip()
            segments = [{
                'text': transcript_text,
                'start': 0.0,
                'duration': duration_seconds,
                'word_timings': whisper_words,
            }]
            source_name = 'audio_stt'
        else:
            try:
                segments = self.audio_transcription_adapter.transcribe(
                    audio_chunk=audio_chunk,
                    mime_type=mime_type,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                )
                source_name = 'audio_chunk'
            except RuntimeError as exc:
                reason = str(exc)
                normalized_reason = reason if reason in {
                    'transcription_unavailable',
                    'analyze_exception',
                    'audio_decode_failed',
                } else 'analyze_exception'
                status = 'unavailable' if normalized_reason == 'transcription_unavailable' else 'error'
                print('[ISWEEP][AUDIO_STT] fallback used', {
                    'video_id': video_id,
                    'reason': normalized_reason,
                })
                if stt_failure_reason in {'stt_unavailable', 'transcription_failed'}:
                    normalized_reason = stt_failure_reason
                    status = 'error'
                return {
                    'status': status,
                    'source': 'audio_chunk',
                    'events': [],
                    'cleaned_captions': [],
                    'failure_reason': normalized_reason,
                }

        transcription_text = ' '.join(
            str(segment.get('text') or '').strip()
            for segment in segments
            if str(segment.get('text') or '').strip()
        )
        print(f'[ISWEEP][AUDIO_AHEAD] transcription used: {transcription_text}')

        if not segments:
            return {'status': 'unavailable', 'source': source_name, 'events': [],
                    'cleaned_captions': [], 'failure_reason': 'transcription_unavailable'}

        absolute_segments: List[Dict] = []
        for segment in segments:
            rel_start = float(segment.get('start', 0) or 0)
            rel_duration = float(segment.get('duration', 0) or 0)
            abs_start = float(start_seconds) + rel_start
            abs_segment = {
                'text': segment.get('text') or '',
                'start': abs_start,
                'duration': rel_duration,
            }
            if isinstance(segment.get('word_timings'), list):
                abs_segment['word_timings'] = segment.get('word_timings')
            absolute_segments.append(abs_segment)

        cleaned_entries = [self._build_cleaned_caption_entry(segment, preferences) for segment in absolute_segments]
        cleaned_captions: List[Dict] = []
        for entry in cleaned_entries:
            if not entry:
                continue
            clean_entry = dict(entry)
            clean_entry.pop('_first_blocked_word_start', None)
            cleaned_captions.append(clean_entry)

        events: List[Dict] = []
        for index, segment in enumerate(absolute_segments):
            text = segment.get('text') or ''
            rel_duration = float(segment.get('duration', 0) or 0)
            abs_start = round(float(segment.get('start', 0) or 0), 3)
            cleaned_entry = cleaned_entries[index] if index < len(cleaned_entries) else None

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

            if action == 'mute':
                if (
                    cleaned_entry
                    and cleaned_entry.get('_first_blocked_word_start') is not None
                    and str(cleaned_entry.get('_first_blocked_word_source') or '') == 'whisper'
                ):
                    adj_start = round(float(cleaned_entry.get('_first_blocked_word_start')), 3)
                else:
                    adj_start = max(round(abs_start - AUDIO_MUTE_PREROLL_SEC, 3), 0.0)

                if cleaned_entry and cleaned_entry.get('clean_resume_time') is not None:
                    resume = round(float(cleaned_entry.get('clean_resume_time')), 3)
                    if resume > adj_start:
                        abs_end = min(abs_end, resume)
                        effective_duration = max(abs_end - adj_start, 0.0)

                if effective_duration <= 0:
                    continue

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
                'source': source_name,
            })
            if action == 'mute' and cleaned_entry and cleaned_entry.get('_first_blocked_word_start') is not None:
                events[-1]['blocked_word_start'] = round(float(cleaned_entry.get('_first_blocked_word_start')), 3)
            if action == 'mute' and cleaned_entry and cleaned_entry.get('clean_resume_time') is not None:
                events[-1]['clean_resume_time'] = round(float(cleaned_entry.get('clean_resume_time')), 3)

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
            'source': source_name,
            'start_seconds': start_seconds,
            'end_seconds': end_seconds,
            'events': merged,
            'cleaned_captions': cleaned_captions,
            'text': transcription_text,
            'clean_text': cleaned_captions[0].get('clean_text') if cleaned_captions else '',
            'failure_reason': None,
        }

    def analyze_audio_chunk_bytes(
        self,
        audio_bytes: bytes,
        start_time: float,
        preferences: Dict,
        video_id: str = '',
        chunk_duration_sec: float | None = None,
    ) -> Dict:
        """Analyze raw audio bytes and emit live marker events for rolling chunks."""
        print('[ISWEEP][AUDIO] chunk received', {
            'video_id': video_id,
            'start_time': start_time,
            'bytes': len(audio_bytes or b''),
        })

        if not _env_flag('ISWEEP_AUDIO_ENABLED'):
            return {
                'events': [],
                'cleaned_text': '',
                'words': [],
                'source': 'audio',
                'failure_reason': 'audio_pipeline_disabled',
            }

        if not self.stt_enabled:
            return {
                'events': [],
                'cleaned_text': '',
                'words': [],
                'source': 'audio',
                'failure_reason': 'stt_disabled',
            }

        if not audio_bytes:
            return {
                'events': [],
                'cleaned_text': '',
                'words': [],
                'source': 'audio',
                'failure_reason': 'audio_decode_failed',
            }

        adapter = self._get_or_create_stt_adapter()
        if adapter is None:
            return {
                'events': [],
                'cleaned_text': '',
                'words': [],
                'source': 'audio',
                'failure_reason': 'stt_unavailable',
            }

        duration = float(chunk_duration_sec if chunk_duration_sec is not None else CHUNK_DURATION_SEC)
        duration = max(duration, 0.0)
        try:
            stt_result = adapter.transcribe_with_word_timestamps(
                audio_bytes,
                text_hint='',
                start_seconds=float(start_time),
                duration_seconds=duration,
            )
            words = stt_result.get('words') if isinstance(stt_result, dict) else []
            words = [w for w in words if isinstance(w, dict)] if isinstance(words, list) else []
        except Exception:
            return {
                'events': [],
                'cleaned_text': '',
                'words': [],
                'source': 'audio',
                'failure_reason': 'transcription_failed',
            }

        print('[ISWEEP][AUDIO] transcription complete', {
            'video_id': video_id,
            'start_time': start_time,
            'words': len(words),
        })

        text = ' '.join(str(word.get('word') or '').strip() for word in words).strip()
        events = self.analyze_transcribed_words(words, preferences or {}, video_id=video_id or 'audio')
        for event in events:
            event['source'] = 'audio'

        cleaned_text = ''
        if text:
            clean_entry = self._build_cleaned_caption_entry({
                'text': text,
                'start': float(start_time),
                'duration': duration,
                'word_timings': words,
            }, preferences or {})
            cleaned_text = (clean_entry or {}).get('clean_text') or ''

        print('[ISWEEP][AUDIO] events generated', {
            'video_id': video_id,
            'count': len(events),
        })
        return {
            'events': events,
            'cleaned_text': cleaned_text,
            'words': words,
            'source': 'audio',
            'failure_reason': None,
        }

    def analyze_transcribed_words(self, words: List[Dict], preferences: Dict, video_id: str = 'audio') -> List[Dict]:
        """Return mute/skip/fast_forward markers from a pre-transcribed word list.

        Parameters
        ----------
        words :
            Absolute-timed word list: [{word, start, end}, ...].
        preferences :
            User filter preferences (same shape as analyze_audio_chunk).
        video_id :
            Used for stable marker ID generation.

        Returns
        -------
        List of marker dicts with ``start_seconds``, ``end_seconds``,
        ``action``, ``matched_category``, ``reason``, and optionally
        ``blocked_word_start`` / ``clean_resume_time``.
        """
        if not isinstance(words, list) or not words:
            return []

        valid_words = [
            w for w in words
            if isinstance(w, dict)
            and str(w.get('word') or '').strip()
            and isinstance(w.get('start'), (int, float))
            and isinstance(w.get('end'), (int, float))
        ]
        if not valid_words:
            return []

        abs_start = float(valid_words[0]['start'])
        abs_end = float(valid_words[-1]['end'])
        duration = max(abs_end - abs_start, 0.0)
        transcript_text = ' '.join(str(w['word']).strip() for w in valid_words)

        segment = {
            'text': transcript_text,
            'start': abs_start,
            'duration': duration,
            'word_timings': valid_words,
        }

        cleaned_entry = self._build_cleaned_caption_entry(segment, preferences)
        decision = self.analyze_decision(transcript_text, preferences)
        action = decision.get('action')
        if action not in {'mute', 'skip', 'fast_forward'}:
            return []

        decision_duration = float(decision.get('duration_seconds') or 0)
        effective_duration = decision_duration if decision_duration > 0 else duration
        if effective_duration <= 0:
            return []

        adj_start = abs_start
        marker_end = round(abs_start + effective_duration, 3)
        category = decision.get('matched_category') or 'language'

        if action == 'mute':
            if (
                cleaned_entry
                and cleaned_entry.get('_first_blocked_word_start') is not None
                and str(cleaned_entry.get('_first_blocked_word_source') or '') == 'whisper'
            ):
                adj_start = round(float(cleaned_entry['_first_blocked_word_start']), 3)
            else:
                adj_start = max(round(abs_start - AUDIO_MUTE_PREROLL_SEC, 3), 0.0)

            if cleaned_entry and cleaned_entry.get('clean_resume_time') is not None:
                resume = round(float(cleaned_entry['clean_resume_time']), 3)
                if resume > adj_start:
                    marker_end = min(marker_end, resume)
                    effective_duration = max(marker_end - adj_start, 0.0)

            if effective_duration <= 0:
                return []

        marker: Dict = {
            'id': self._stable_marker_id(video_id, adj_start, marker_end, action, category),
            'start_seconds': adj_start,
            'end_seconds': marker_end,
            'action': action,
            'duration_seconds': round(effective_duration, 3),
            'matched_category': category,
            'reason': decision.get('reason') or 'word match',
            'source': 'audio_stt',
        }
        if action == 'mute' and cleaned_entry:
            if cleaned_entry.get('_first_blocked_word_start') is not None:
                marker['blocked_word_start'] = round(float(cleaned_entry['_first_blocked_word_start']), 3)
            if cleaned_entry.get('clean_resume_time') is not None:
                marker['clean_resume_time'] = round(float(cleaned_entry['clean_resume_time']), 3)

        return self._merge_marker_events([marker])
