import pytest  # Testing framework
from content_analyzer import AUDIO_MUTE_PREROLL_SEC, ContentAnalyzer, DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT  # Class under test


class TestContentAnalyzer:
    """Test the content analysis engine."""

    @pytest.fixture
    def analyzer(self):
        """Create a content analyzer instance."""
        return ContentAnalyzer()  # Instantiate analyzer for each test

    @pytest.fixture
    def default_preferences(self):
        """Default user preferences for testing."""
        return {
            'language_filter': True,
            'sexual_content_filter': True,
            'violence_filter': True,
            'language_sensitivity': 'medium',
            'sexual_content_sensitivity': 'medium',
            'violence_sensitivity': 'medium'
        }  # Default settings mimicking normal use

    @pytest.fixture
    def audio_language_preferences(self):
        """Audio-ahead preferences enabling only language mute."""
        return {
            'enabled': True,
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
            'sensitivity': 0.9,
        }

    def test_clean_content_returns_none(self, analyzer, default_preferences):
        """Test that clean content returns 'none' action."""
        text = "Hello, this is a nice day and everything is wonderful."  # Benign text
        action = analyzer.analyze(text, default_preferences)  # Analyze with defaults
        assert action == 'none'  # Expect no action

    def test_profanity_returns_mute(self, analyzer, default_preferences):
        """Test that profanity triggers mute action."""
        text = "This is damn stupid"  # Contains profanity
        action = analyzer.analyze(text, default_preferences)  # Analyze
        assert action == 'mute'  # Expect mute action

    def test_violence_returns_fast_forward(self, analyzer, default_preferences):
        """Test that violent content triggers fast_forward action."""
        text = "He was shot and killed in the fight"  # Violent content
        action = analyzer.analyze(text, default_preferences)  # Analyze
        assert action == 'fast_forward'  # Expect fast forward

    def test_sexual_content_returns_skip(self, analyzer, default_preferences):
        """Test that sexual content triggers skip action."""
        text = "The sexual scene was explicit"  # Sexual content
        action = analyzer.analyze(text, default_preferences)  # Analyze
        assert action == 'skip'  # Expect skip

    def test_disabled_filter_returns_none(self, analyzer):
        """Test that disabled filters don't trigger actions."""
        preferences = {
            'language_filter': False,
            'sexual_content_filter': False,
            'violence_filter': False,
            'language_sensitivity': 'medium',
            'sexual_content_sensitivity': 'medium',
            'violence_sensitivity': 'medium'
        }  # Disable all filters
        text = "This damn violent sexual content"  # Text that would normally trigger
        action = analyzer.analyze(text, preferences)  # Analyze with filters off
        assert action == 'none'  # Expect no action

    def test_high_sensitivity_triggers_easily(self, analyzer):
        """Test that high sensitivity triggers on single match."""
        preferences = {
            'language_filter': False,  # Disable language filter to test violence
            'sexual_content_filter': False,
            'violence_filter': True,
            'language_sensitivity': 'high',
            'sexual_content_sensitivity': 'high',
            'violence_sensitivity': 'high'
        }  # High sensitivity thresholds
        text = "There was one violent attack"  # Single violent term
        action = analyzer.analyze(text, preferences)  # Analyze
        assert action == 'fast_forward'  # High sensitivity triggers fast forward

    def test_low_sensitivity_requires_multiple_matches(self, analyzer):
        """Test that low sensitivity needs multiple matches."""
        preferences = {
            'language_filter': False,
            'sexual_content_filter': False,
            'violence_filter': True,
            'language_sensitivity': 'low',
            'sexual_content_sensitivity': 'low',
            'violence_sensitivity': 'low'
        }  # Low sensitivity thresholds
        # Single mention shouldn't trigger with low sensitivity
        text = "There was violence"  # Only one match
        action = analyzer.analyze(text, preferences)  # Analyze
        # Low sensitivity threshold is 5, so this should return 'none'
        assert action == 'none'  # Expect no action

        # Multiple mentions should trigger
        text = "Violence and murder and kill and shot and fight and blood"  # Many violent terms
        action = analyzer.analyze(text, preferences)  # Analyze again
        assert action == 'fast_forward'  # Now should trigger fast forward

    def test_empty_text_returns_none(self, analyzer, default_preferences):
        """Test that empty text returns 'none'."""
        action = analyzer.analyze('', default_preferences)  # Analyze empty string
        assert action == 'none'  # Expect no action

    def test_priority_language_over_others(self, analyzer, default_preferences):
        """Test that language filter takes priority (returns mute first)."""
        # When multiple categories match, language (mute) should be checked first
        text = "This damn violent sexual scene"  # Contains profanity, violence, sexual
        action = analyzer.analyze(text, default_preferences)  # Analyze
        # Language filter is checked first, so should return mute
        assert action == 'mute'  # Expect mute due to profanity priority

    def test_blocklist_word_triggers_mute(self, analyzer):
        """Blocklist single word triggers mute with blocklist category."""
        prefs = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['forbidden'],
                'duration': 6,
            },
        }  # Blocklist configuration for single word
        decision = analyzer.analyze_decision('This FORBIDDEN topic appears', prefs)  # Analyze with blocklist word
        assert decision['action'] == 'mute'  # Expect mute action
        assert decision['matched_category'] == 'blocklist'  # Category blocklist
        assert decision['duration_seconds'] == 6  # Duration from prefs
        assert 'blocklist match' in decision['reason']  # Reason mentions blocklist

    def test_blocklist_phrase_triggers_mute(self, analyzer):
        """Blocklist phrase triggers mute on substring match."""
        prefs = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['make out'],
                'duration': 5,
            },
        }  # Blocklist configuration for phrase
        decision = analyzer.analyze_decision('They start to Make out in the scene', prefs)  # Analyze with blocklist phrase
        assert decision['action'] == 'mute'  # Expect mute action
        assert decision['matched_category'] == 'blocklist'  # Category blocklist
        assert decision['duration_seconds'] == 5  # Duration from prefs
        assert 'blocklist match' in decision['reason']  # Reason mentions blocklist

    def test_transcript_generates_mute_marker(self, analyzer):
        """Transcript segment with blocklist phrase should generate mute marker."""
        prefs = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['strip club'],
                'duration': 6,
            },
        }

        analyzer._fetch_transcript_segments = lambda _: [
            {'text': 'He walked into a strip club downtown', 'start': 12.3, 'duration': 1.3}
        ]

        result = analyzer.analyze_video_markers('abc123', prefs)
        assert result['status'] == 'ready'
        assert result['source'] == 'transcript'
        assert len(result['events']) == 1
        marker = result['events'][0]
        assert marker['action'] == 'mute'
        assert marker['matched_category'] == 'blocklist'
        assert marker['start_seconds'] == pytest.approx(12.3)
        assert marker['duration_seconds'] == pytest.approx(6.0)
        assert marker['end_seconds'] == pytest.approx(18.3)
        assert isinstance(marker['id'], str) and marker['id']

    def test_build_cleaned_captions_masks_blocked_words(self, analyzer):
        """Cleaned captions mask configured blocklist/profanity terms for overlay display."""
        prefs = {
            'enabled': True,
            'blocklist': {'enabled': True, 'items': ['heck']},
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
        }

        cleaned = analyzer.build_cleaned_captions([
            {'text': 'What the heck and shit is going on?', 'start': 12.3, 'duration': 1.8}
        ], prefs)

        assert len(cleaned) == 1
        assert 'heck' not in cleaned[0]['clean_text'].lower()
        assert 'shit' not in cleaned[0]['clean_text'].lower()
        assert cleaned[0]['clean_text'].count('____') >= 2
        assert len(cleaned[0]['words']) == 8
        assert cleaned[0]['words'][0]['word'] == 'What'
        assert cleaned[0]['words'][0]['start'] == pytest.approx(12.3)
        assert cleaned[0]['words'][-1]['end'] == pytest.approx(14.1)
        assert cleaned[0]['clean_resume_time'] == pytest.approx(cleaned[0]['words'][3]['start'])

    def test_build_cleaned_captions_preserves_original_text_and_timing(self, analyzer):
        """Cleaned captions preserve transcript text while exposing rounded start/end timing."""
        prefs = {
            'enabled': True,
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
        }

        cleaned = analyzer.build_cleaned_captions([
            {'text': 'Original transcript line', 'start': 5.25, 'duration': 1.55}
        ], prefs)

        assert len(cleaned) == 1
        assert cleaned[0]['start_seconds'] == pytest.approx(5.25)
        assert cleaned[0]['end_seconds'] == pytest.approx(6.8)
        assert cleaned[0]['text'] == 'Original transcript line'
        assert cleaned[0]['clean_text'] == 'Original transcript line'
        assert len(cleaned[0]['words']) == 3
        assert cleaned[0]['words'][0]['start'] == pytest.approx(5.25)
        assert cleaned[0]['words'][-1]['end'] == pytest.approx(6.8)
        assert 'clean_resume_time' not in cleaned[0]

    def test_transcript_generates_skip_marker(self, analyzer):
        """Transcript segment with sexual content should generate skip marker."""
        prefs = {
            'enabled': True,
            'categories': {
                'sexual': {'enabled': True, 'action': 'skip', 'duration': 10},
                'language': {'enabled': False, 'action': 'mute', 'duration': 4},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
            'sensitivity': 0.7,
        }

        analyzer._fetch_transcript_segments = lambda _: [
            {'text': 'The sexual scene was explicit', 'start': 30.0, 'duration': 1.8}
        ]

        result = analyzer.analyze_video_markers('video456', prefs)
        assert result['status'] == 'ready'
        assert len(result['events']) == 1
        marker = result['events'][0]
        assert marker['action'] == 'skip'
        assert marker['matched_category'] == 'sexual'
        assert marker['start_seconds'] == pytest.approx(30.0)
        assert marker['duration_seconds'] == pytest.approx(10.0)
        assert marker['end_seconds'] == pytest.approx(40.0)

    def test_analyze_video_markers_returns_cleaned_captions_with_events(self, analyzer):
        """Video marker analysis returns cleaned captions separately from action markers."""
        prefs = {
            'enabled': True,
            'blocklist': {'enabled': True, 'items': ['heck']},
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
        }

        analyzer._fetch_transcript_segments = lambda _: [
            {'text': 'What the heck', 'start': 7.5, 'duration': 1.0}
        ]

        result = analyzer.analyze_video_markers('clean-cc-video', prefs)

        assert result['status'] == 'ready'
        assert result['failure_reason'] is None
        assert len(result['events']) == 1
        assert result['cleaned_captions'] == result['clean_captions']
        assert result['cleaned_captions'][0]['text'] == 'What the heck'
        assert result['cleaned_captions'][0]['clean_text'] == 'What the ____'
        assert len(result['cleaned_captions'][0]['words']) == 3
        assert 'clean_resume_time' not in result['cleaned_captions'][0]
        assert result['events'][0]['start_seconds'] == pytest.approx(7.5)
        assert result['events'][0]['blocked_word_start'] == pytest.approx(8.167, abs=0.001)

    def test_mute_marker_ends_at_clean_resume_time_when_clean_word_exists(self, analyzer):
        """Mute marker exposes clean_resume_time metadata without changing base duration."""
        prefs = {
            'enabled': True,
            'blocklist': {'enabled': True, 'items': ['heck']},
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
        }

        analyzer._fetch_transcript_segments = lambda _: [
            {'text': 'croc of heck man', 'start': 10.0, 'duration': 2.0}
        ]

        result = analyzer.analyze_video_markers('clean-anchor-video', prefs)
        assert result['status'] == 'ready'
        assert len(result['events']) == 1
        assert result['cleaned_captions'][0]['clean_resume_time'] == pytest.approx(11.5, abs=0.001)
        assert result['events'][0]['start_seconds'] == pytest.approx(10.0)
        assert result['events'][0]['blocked_word_start'] == pytest.approx(11.0, abs=0.001)
        assert result['events'][0]['end_seconds'] == pytest.approx(14.0, abs=0.001)
        assert result['events'][0]['clean_resume_time'] == pytest.approx(11.5, abs=0.001)

    def test_clean_resume_time_anchors_to_first_clean_word_after_filtered_run(self, analyzer):
        """clean_resume_time points to the first clean word after blocked words."""
        prefs = {
            'enabled': True,
            'blocklist': {'enabled': True, 'items': ['heck']},
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
        }

        cleaned = analyzer.build_cleaned_captions([
            {'text': 'croc of heck man', 'start': 10.0, 'duration': 2.0}
        ], prefs)

        assert len(cleaned) == 1
        assert cleaned[0]['words'][0]['word'] == 'croc'
        assert cleaned[0]['words'][2]['word'] == 'heck'
        assert cleaned[0]['words'][3]['word'] == 'man'
        assert cleaned[0]['clean_resume_time'] == pytest.approx(cleaned[0]['words'][3]['start'])

    def test_cleaned_captions_fallback_when_word_timing_unavailable(self, analyzer):
        """Segments with no lexical words still return safe cleaned caption entries."""
        prefs = {'enabled': True, 'categories': {'language': {'enabled': True}}}
        cleaned = analyzer.build_cleaned_captions([
            {'text': '...', 'start': 4.0, 'duration': 1.2}
        ], prefs)

        assert len(cleaned) == 1
        assert cleaned[0]['text'] == '...'
        assert cleaned[0]['clean_text'] == '...'
        assert cleaned[0]['words'] == []
        assert 'clean_resume_time' not in cleaned[0]

    def test_transcript_markers_are_non_overlapping(self, analyzer):
        """Overlapping events should be merged/trimmed to deterministic non-overlapping output."""
        events = [
            {
                'id': 'a',
                'start_seconds': 10.0,
                'end_seconds': 14.0,
                'action': 'mute',
                'duration_seconds': 4.0,
                'matched_category': 'language',
                'reason': 'first',
            },
            {
                'id': 'b',
                'start_seconds': 12.0,
                'end_seconds': 15.0,
                'action': 'skip',
                'duration_seconds': 3.0,
                'matched_category': 'sexual',
                'reason': 'second',
            },
        ]

        merged = analyzer._merge_marker_events(events)
        assert len(merged) == 2
        assert merged[0]['end_seconds'] <= merged[1]['start_seconds']

    def test_audio_chunk_uses_default_dev_fallback_text(self, analyzer, monkeypatch):
        """Audio-ahead uses a deterministic fallback transcript when no stub text is configured."""
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_STUB_TEXT', raising=False)
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_PROVIDER', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'development')

        segments = analyzer.audio_transcription_adapter.transcribe(
            audio_chunk='ZmFrZQ==',
            mime_type='audio/wav',
            start_seconds=12.0,
            end_seconds=13.0,
        )

        assert len(segments) == 1
        assert segments[0]['text'] == DEFAULT_AUDIO_AHEAD_FALLBACK_TEXT
        assert segments[0]['start'] == pytest.approx(0.0)
        assert segments[0]['duration'] == pytest.approx(1.0)

    def test_audio_mute_marker_applies_preroll(self, analyzer, monkeypatch, audio_language_preferences):
        """Audio-ahead mute markers are shifted earlier by the configured preroll."""
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_STUB_TEXT', raising=False)
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_PROVIDER', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'development')

        result = analyzer.analyze_audio_chunk(
            audio_chunk='ZmFrZQ==',
            mime_type='audio/wav',
            start_seconds=20.0,
            end_seconds=21.0,
            preferences=audio_language_preferences,
            video_id='dev-audio',
        )

        assert result['status'] == 'ready'
        assert result['failure_reason'] is None
        assert len(result['events']) == 1
        marker = result['events'][0]
        assert marker['action'] == 'mute'
        assert marker['matched_category'] == 'language'
        assert marker['start_seconds'] == pytest.approx(20.0 - AUDIO_MUTE_PREROLL_SEC)
        assert marker['end_seconds'] == pytest.approx(24.0)

    def test_audio_marker_start_never_below_zero(self, analyzer, monkeypatch, audio_language_preferences):
        """Audio mute marker preroll clamps at zero for near-start chunks."""
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_STUB_TEXT', raising=False)
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_PROVIDER', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'development')

        result = analyzer.analyze_audio_chunk(
            audio_chunk='ZmFrZQ==',
            mime_type='audio/wav',
            start_seconds=0.05,
            end_seconds=1.05,
            preferences=audio_language_preferences,
            video_id='dev-audio-start',
        )

        assert result['status'] == 'ready'
        assert len(result['events']) == 1
        assert result['events'][0]['start_seconds'] == pytest.approx(0.0)

    def test_audio_marker_ids_are_deterministic(self, analyzer, monkeypatch, audio_language_preferences):
        """Repeated audio chunk analysis with the same inputs yields the same marker id."""
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_STUB_TEXT', raising=False)
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_PROVIDER', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'development')

        first = analyzer.analyze_audio_chunk(
            audio_chunk='ZmFrZQ==',
            mime_type='audio/wav',
            start_seconds=20.0,
            end_seconds=21.0,
            preferences=audio_language_preferences,
            video_id='stable-audio',
        )
        second = analyzer.analyze_audio_chunk(
            audio_chunk='ZmFrZQ==',
            mime_type='audio/wav',
            start_seconds=20.0,
            end_seconds=21.0,
            preferences=audio_language_preferences,
            video_id='stable-audio',
        )

        assert first['status'] == 'ready'
        assert second['status'] == 'ready'
        assert first['events'][0]['id'] == second['events'][0]['id']

    def test_audio_overlapping_mute_markers_merge_cleanly(self, analyzer):
        """Overlapping audio mute markers merge into one stable mute window."""
        events = [
            {
                'id': 'audio-a',
                'start_seconds': 10.0,
                'end_seconds': 12.0,
                'action': 'mute',
                'duration_seconds': 2.0,
                'matched_category': 'language',
                'reason': 'audio first',
            },
            {
                'id': 'audio-b',
                'start_seconds': 11.25,
                'end_seconds': 14.0,
                'action': 'mute',
                'duration_seconds': 2.75,
                'matched_category': 'language',
                'reason': 'audio second',
            },
        ]

        merged = analyzer._merge_marker_events(events)

        assert len(merged) == 1
        assert merged[0]['start_seconds'] == pytest.approx(10.0)
        assert merged[0]['end_seconds'] == pytest.approx(14.0)
        assert merged[0]['duration_seconds'] == pytest.approx(4.0)

    def test_audio_chunk_without_match_returns_ready_with_empty_events_in_dev_mode(self, analyzer, monkeypatch, audio_language_preferences):
        """Development audio fallback still returns ready when the transcript has no match."""
        monkeypatch.setenv('ISWEEP_AUDIO_AHEAD_STUB_TEXT', 'hello there friend')
        monkeypatch.delenv('ISWEEP_AUDIO_AHEAD_PROVIDER', raising=False)
        monkeypatch.setenv('FLASK_ENV', 'development')

        result = analyzer.analyze_audio_chunk(
            audio_chunk='ZmFrZQ==',
            mime_type='audio/wav',
            start_seconds=20.0,
            end_seconds=21.0,
            preferences=audio_language_preferences,
            video_id='clean-audio',
        )

        assert result['status'] == 'ready'
        assert result['events'] == []
        assert result['failure_reason'] is None
