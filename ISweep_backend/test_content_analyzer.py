import pytest  # Testing framework
from content_analyzer import ContentAnalyzer  # Class under test


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
