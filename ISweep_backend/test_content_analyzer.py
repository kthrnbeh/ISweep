import pytest
from content_analyzer import ContentAnalyzer

class TestContentAnalyzer:
    """Test the content analysis engine."""
    
    @pytest.fixture
    def analyzer(self):
        """Create a content analyzer instance."""
        return ContentAnalyzer()
    
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
        }
    
    def test_clean_content_returns_none(self, analyzer, default_preferences):
        """Test that clean content returns 'none' action."""
        text = "Hello, this is a nice day and everything is wonderful."
        action = analyzer.analyze(text, default_preferences)
        assert action == 'none'
    
    def test_profanity_returns_mute(self, analyzer, default_preferences):
        """Test that profanity triggers mute action."""
        text = "This is damn stupid"
        action = analyzer.analyze(text, default_preferences)
        assert action == 'mute'
    
    def test_violence_returns_fast_forward(self, analyzer, default_preferences):
        """Test that violent content triggers fast_forward action."""
        text = "He was shot and killed in the fight"
        action = analyzer.analyze(text, default_preferences)
        assert action == 'fast_forward'
    
    def test_sexual_content_returns_skip(self, analyzer, default_preferences):
        """Test that sexual content triggers skip action."""
        text = "The sexual scene was explicit"
        action = analyzer.analyze(text, default_preferences)
        assert action == 'skip'
    
    def test_disabled_filter_returns_none(self, analyzer):
        """Test that disabled filters don't trigger actions."""
        preferences = {
            'language_filter': False,
            'sexual_content_filter': False,
            'violence_filter': False,
            'language_sensitivity': 'medium',
            'sexual_content_sensitivity': 'medium',
            'violence_sensitivity': 'medium'
        }
        text = "This damn violent sexual content"
        action = analyzer.analyze(text, preferences)
        assert action == 'none'
    
    def test_high_sensitivity_triggers_easily(self, analyzer):
        """Test that high sensitivity triggers on single match."""
        preferences = {
            'language_filter': False,  # Disable language filter to test violence
            'sexual_content_filter': False,
            'violence_filter': True,
            'language_sensitivity': 'high',
            'sexual_content_sensitivity': 'high',
            'violence_sensitivity': 'high'
        }
        text = "There was one violent attack"
        action = analyzer.analyze(text, preferences)
        assert action == 'fast_forward'
    
    def test_low_sensitivity_requires_multiple_matches(self, analyzer):
        """Test that low sensitivity needs multiple matches."""
        preferences = {
            'language_filter': False,
            'sexual_content_filter': False,
            'violence_filter': True,
            'language_sensitivity': 'low',
            'sexual_content_sensitivity': 'low',
            'violence_sensitivity': 'low'
        }
        # Single mention shouldn't trigger with low sensitivity
        text = "There was violence"
        action = analyzer.analyze(text, preferences)
        # Low sensitivity threshold is 5, so this should return 'none'
        assert action == 'none'
        
        # Multiple mentions should trigger
        text = "Violence and murder and kill and shot and fight and blood"
        action = analyzer.analyze(text, preferences)
        assert action == 'fast_forward'
    
    def test_empty_text_returns_none(self, analyzer, default_preferences):
        """Test that empty text returns 'none'."""
        action = analyzer.analyze('', default_preferences)
        assert action == 'none'
    
    def test_priority_language_over_others(self, analyzer, default_preferences):
        """Test that language filter takes priority (returns mute first)."""
        # When multiple categories match, language (mute) should be checked first
        text = "This damn violent sexual scene"
        action = analyzer.analyze(text, default_preferences)
        # Language filter is checked first, so should return mute
        assert action == 'mute'

    def test_blocklist_word_triggers_mute(self, analyzer):
        """Blocklist single word triggers mute with blocklist category."""
        prefs = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['forbidden'],
                'duration': 6,
            },
        }
        decision = analyzer.analyze_decision('This FORBIDDEN topic appears', prefs)
        assert decision['action'] == 'mute'
        assert decision['matched_category'] == 'blocklist'
        assert decision['duration_seconds'] == 6
        assert 'blocklist match' in decision['reason']

    def test_blocklist_phrase_triggers_mute(self, analyzer):
        """Blocklist phrase triggers mute on substring match."""
        prefs = {
            'enabled': True,
            'blocklist': {
                'enabled': True,
                'items': ['make out'],
                'duration': 5,
            },
        }
        decision = analyzer.analyze_decision('They start to Make out in the scene', prefs)
        assert decision['action'] == 'mute'
        assert decision['matched_category'] == 'blocklist'
        assert decision['duration_seconds'] == 5
        assert 'blocklist match' in decision['reason']
