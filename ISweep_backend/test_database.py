import pytest  # Testing framework
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
