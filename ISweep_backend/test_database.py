import pytest
from database import Database


def create_test_user(db: Database, username: str = 'testuser', email: str | None = None):
    # Use a placeholder password hash; create_user does not enforce hashing.
    return db.create_user(email or f"{username}@dev.local", 'hashedpw', username=username)


class TestDatabase:
    """Test database operations."""

    def test_create_user(self, database):
        user_id = create_test_user(database, 'testuser1')
        assert user_id is not None
        assert user_id > 0

    def test_create_duplicate_user(self, database):
        create_test_user(database, 'dupe')
        user_id = create_test_user(database, 'dupe')
        assert user_id is None

    def test_get_user_by_id(self, database):
        user_id = create_test_user(database, 'byid')
        user = database.get_user_by_id(user_id)
        assert user is not None
        assert user['username'] == 'byid'

    def test_get_user_by_username(self, database):
        create_test_user(database, 'byname')
        user = database.get_user_by_username('byname')
        assert user is not None
        assert user['username'] == 'byname'

    def test_get_nonexistent_user(self, database):
        user = database.get_user_by_id(9999)
        assert user is None

    def test_default_preferences(self, database):
        user_id = create_test_user(database, 'prefs')
        prefs = database.get_user_preferences(user_id)

        assert prefs is not None
        assert prefs['enabled'] is True
        assert prefs['categories']['language']['enabled'] is True
        assert prefs['categories']['sexual']['enabled'] is True
        assert prefs['categories']['violence']['enabled'] is True

    def test_update_preferences(self, database):
        user_id = create_test_user(database, 'update')

        payload = {
            'enabled': True,
            'categories': {
                'language': {'enabled': False, 'action': 'mute', 'duration': 4},
                'violence': {'enabled': True, 'action': 'skip', 'duration': 10},
            },
            'sensitivity': 0.9,
        }
        success = database.update_user_preferences(user_id, payload)
        assert success is True

        prefs = database.get_user_preferences(user_id)
        assert prefs['categories']['language']['enabled'] is False
        assert prefs['categories']['violence']['duration'] == 10

    def test_update_all_preferences(self, database):
        user_id = create_test_user(database, 'updateall')

        new_prefs = {
            'enabled': True,
            'categories': {
                'language': {'enabled': False, 'action': 'mute', 'duration': 3},
                'sexual': {'enabled': False, 'action': 'skip', 'duration': 12},
                'violence': {'enabled': True, 'action': 'fast_forward', 'duration': 9},
            },
            'sensitivity': 0.5,
        }

        success = database.update_user_preferences(user_id, new_prefs)
        assert success is True

        prefs = database.get_user_preferences(user_id)
        assert prefs['categories']['language']['enabled'] is False
        assert prefs['categories']['sexual']['enabled'] is False
        assert prefs['categories']['violence']['enabled'] is True
