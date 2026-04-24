from datetime import datetime, timedelta
from database import Database  # Database class under test


def create_test_user(db: Database, username: str = 'testuser', email: str | None = None):
    # Use a placeholder password hash; create_user does not enforce hashing.
    return db.create_user(email or f"{username}@dev.local", 'hashedpw', username=username)  # Helper to insert a user


class TestDatabase:
    """Test database operations."""

    def test_create_user(self, database):
        user_id = create_test_user(database, 'testuser1')  # Create user
        assert user_id is not None  # Should return an id
        assert user_id > 0  # Id should be positive

    def test_create_duplicate_user(self, database):
        create_test_user(database, 'dupe')  # First insert
        user_id = create_test_user(database, 'dupe')  # Duplicate insert
        assert user_id is None  # Expect None due to unique constraint

    def test_get_user_by_id(self, database):
        user_id = create_test_user(database, 'byid')  # Create user
        user = database.get_user_by_id(user_id)  # Fetch by id
        assert user is not None  # Should return user
        assert user['username'] == 'byid'  # Username matches

    def test_get_user_by_username(self, database):
        create_test_user(database, 'byname')  # Create user
        user = database.get_user_by_username('byname')  # Fetch by username
        assert user is not None  # Should return user
        assert user['username'] == 'byname'  # Username matches

    def test_get_nonexistent_user(self, database):
        user = database.get_user_by_id(9999)  # Nonexistent id
        assert user is None  # Expect None

    def test_default_preferences(self, database):
        user_id = create_test_user(database, 'prefs')  # Create user
        prefs = database.get_user_preferences(user_id)  # Fetch default prefs

        assert prefs is not None  # Prefs should exist
        assert prefs['enabled'] is True  # Global enabled default
        assert prefs['categories']['language']['enabled'] is True  # Language enabled
        assert prefs['categories']['sexual']['enabled'] is True  # Sexual enabled
        assert prefs['categories']['violence']['enabled'] is True  # Violence enabled

    def test_update_preferences(self, database):
        user_id = create_test_user(database, 'update')  # Create user

        payload = {
            'enabled': True,
            'categories': {
                'language': {'enabled': False, 'action': 'mute', 'duration': 4},
                'violence': {'enabled': True, 'action': 'skip', 'duration': 10},
            },
            'sensitivity': 0.9,
        }  # Preference updates
        success = database.update_user_preferences(user_id, payload)  # Update prefs
        assert success is True  # Update should succeed

        prefs = database.get_user_preferences(user_id)  # Fetch updated prefs
        assert prefs['categories']['language']['enabled'] is False  # Language disabled
        assert prefs['categories']['violence']['duration'] == 10  # Violence duration updated

    def test_update_all_preferences(self, database):
        user_id = create_test_user(database, 'updateall')  # Create user

        new_prefs = {
            'enabled': True,
            'categories': {
                'language': {'enabled': False, 'action': 'mute', 'duration': 3},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': True, 'action': 'fast_forward', 'duration': 9},
            },
            'sensitivity': 0.5,
        }  # Comprehensive preference update

        success = database.update_user_preferences(user_id, new_prefs)  # Apply updates
        assert success is True  # Should succeed

        prefs = database.get_user_preferences(user_id)  # Fetch updated prefs
        assert prefs['categories']['language']['enabled'] is False  # Language disabled
        assert prefs['categories']['sexual']['enabled'] is False  # Sexual disabled
        assert prefs['categories']['violence']['enabled'] is True  # Violence enabled

    def test_store_and_validate_token_lifecycle(self, database):
        user_id = create_test_user(database, 'tokenlife')
        token = 'token-life-123'
        database.store_user_token(user_id, token, datetime.utcnow() + timedelta(minutes=30))

        validated_user_id = database.validate_token(token)
        assert validated_user_id == user_id

    def test_validate_token_unknown_returns_none(self, database):
        assert database.validate_token('missing-token') is None

    def test_expired_token_returns_none_and_is_removed(self, database):
        user_id = create_test_user(database, 'expiredtoken')
        token = 'expired-token-123'
        database.store_user_token(user_id, token, datetime.utcnow() - timedelta(minutes=1))

        assert database.validate_token(token) is None
        assert database.get_user_by_token(token) is None

    def test_preferences_roundtrip_json_consistency(self, database):
        user_id = create_test_user(database, 'prefroundtrip')
        payload = {
            'enabled': True,
            'categories': {
                'language': {'enabled': True, 'action': 'mute', 'duration': 4},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': False, 'action': 'fast_forward', 'duration': 8},
            },
            'sensitivity': 0.9,
        }

        assert database.update_user_preferences(user_id, payload) is True
        loaded = database.get_user_preferences(user_id)
        assert loaded == payload

    def test_video_analysis_cache_roundtrip(self, database):
        payload = {
            'status': 'ready',
            'source': 'transcript',
            'events': [{'id': 'm1', 'start_seconds': 1.0, 'end_seconds': 2.0, 'action': 'mute'}],
            'cleaned_captions': [{'start_seconds': 1.0, 'end_seconds': 2.0, 'text': 'a', 'clean_text': 'a'}],
            'clean_captions': [{'start_seconds': 1.0, 'end_seconds': 2.0, 'text': 'a', 'clean_text': 'a'}],
            'failure_reason': None,
        }

        database.save_video_analysis_cache('vid-1', 'prefs-1', payload)
        cached = database.get_video_analysis_cache('vid-1', 'prefs-1')

        assert cached is not None
        assert cached['status'] == 'ready'
        assert cached['source'] == 'transcript'
        assert cached['events'][0]['id'] == 'm1'
        assert cached['cleaned_captions'][0]['clean_text'] == 'a'
        assert cached['clean_captions'] == cached['cleaned_captions']
        assert cached['failure_reason'] is None
        assert isinstance(cached['created_at'], str)
        assert isinstance(cached['updated_at'], str)

    def test_video_analysis_cache_upsert_updates_payload(self, database):
        first_payload = {
            'status': 'unavailable',
            'source': None,
            'events': [],
            'cleaned_captions': [],
            'clean_captions': [],
            'failure_reason': 'transcript_unavailable',
        }
        second_payload = {
            'status': 'ready',
            'source': 'transcript',
            'events': [{'id': 'm2', 'start_seconds': 3.0, 'end_seconds': 4.0, 'action': 'skip'}],
            'cleaned_captions': [{'start_seconds': 3.0, 'end_seconds': 4.0, 'text': 'b', 'clean_text': 'b'}],
            'clean_captions': [{'start_seconds': 3.0, 'end_seconds': 4.0, 'text': 'b', 'clean_text': 'b'}],
            'failure_reason': None,
        }

        database.save_video_analysis_cache('vid-2', 'prefs-2', first_payload)
        database.save_video_analysis_cache('vid-2', 'prefs-2', second_payload)
        cached = database.get_video_analysis_cache('vid-2', 'prefs-2')

        assert cached is not None
        assert cached['status'] == 'ready'
        assert cached['events'][0]['id'] == 'm2'
        assert cached['failure_reason'] is None
