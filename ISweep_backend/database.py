"""
ISWEEP COMPONENT: Persistence Layer
# Notes that this file is the persistence component

This module wraps SQLite access for users, preferences, and auth tokens. The Flask
# Explains it manages SQLite for users/preferences/tokens
app imports Database to store user accounts, bearer tokens, and filtering settings
# States that the Flask app uses this class to store auth and filtering data
that drive ContentAnalyzer decisions.
# Clarifies data supports ContentAnalyzer

System connection:
    Backend endpoints -> Database -> persist/fetch users, preferences, tokens -> /event
# Shows how API endpoints flow through the DB layer to event processing
"""

import sqlite3  # Standard library SQLite interface
import json  # JSON serialization for preferences
from datetime import datetime  # Timestamp handling
from typing import Dict, Optional, Tuple  # Type annotations for clarity


class Database:
    """Simple SQLite database handler for user preferences."""
    # Class docstring describing database handler purpose

    def __init__(self, db_path: str = 'isweep.db'):
        self.db_path = db_path  # Store DB file path
        self.init_db()  # Ensure schema exists on creation

    def get_connection(self):
        """Open a connection with row_factory set so rows can be dict-converted easily."""
        conn = sqlite3.connect(self.db_path)  # Open SQLite connection
        conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
        return conn  # Provide connection to caller

    def init_db(self):
        """Initialize database schema for users, preferences, and auth tokens."""
        conn = self.get_connection()  # Open connection for schema creation
        cursor = conn.cursor()  # Get cursor for executing SQL

        # Create users table with email/password support
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')  # Create users table if missing

        # Best-effort migrations for existing databases
        for alter in [
            "ALTER TABLE users ADD COLUMN email TEXT",  # Add email column if absent
            "ALTER TABLE users ADD COLUMN password_hash TEXT",  # Add password_hash column if absent
        ]:
            try:
                cursor.execute(alter)  # Attempt schema alteration
            except sqlite3.OperationalError:
                pass  # Ignore if column already exists

        # Create user_preferences table (legacy columns retained) plus JSON blob for flexible prefs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                language_filter BOOLEAN DEFAULT 1,
                sexual_content_filter BOOLEAN DEFAULT 1,
                violence_filter BOOLEAN DEFAULT 1,
                language_sensitivity TEXT DEFAULT 'medium',
                sexual_content_sensitivity TEXT DEFAULT 'medium',
                violence_sensitivity TEXT DEFAULT 'medium',
                preferences_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')  # Create preferences table with legacy and JSON fields

        try:
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN preferences_json TEXT")  # Add JSON column if missing
        except sqlite3.OperationalError:
            pass  # Ignore if column already exists

        # Simple token store for dev
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')  # Create auth token table for bearer tokens

        conn.commit()  # Persist schema changes
        conn.close()  # Close connection

    def create_user(self, email: str, password_hash: str, username: Optional[str] = None) -> Optional[int]:
        """Create a new user and seed default preferences used by the decision engine."""
        conn = self.get_connection()  # Open connection for insert
        cursor = conn.cursor()  # Get cursor

        try:
            # Default username fallback to email local-part when not provided
            username_to_store = username or email.split('@')[0]  # Derive username fallback

            cursor.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                (username_to_store, email, password_hash)
            )  # Insert new user row
            user_id = cursor.lastrowid  # Capture generated user id

            # Default preferences aligned with requested structure
            default_preferences = {
                "enabled": True,
                "categories": {
                    "language": {"enabled": True, "action": "mute", "duration": 4},
                    "sexual": {"enabled": True, "action": "skip", "duration": 12},
                    "violence": {"enabled": True, "action": "fast_forward", "duration": 8},
                },
                "sensitivity": 0.7,
            }  # Seed preferences JSON with defaults

            cursor.execute(
                'INSERT INTO user_preferences (user_id, preferences_json) VALUES (?, ?)',
                (user_id, json.dumps(default_preferences))
            )  # Store default preferences record

            conn.commit()  # Persist changes
            return user_id  # Return new user id
        except sqlite3.IntegrityError:
            return None  # Return None when email uniqueness fails
        finally:
            conn.close()  # Always close connection

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Fetch a user row by id for auth and preference lookups."""
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor

        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))  # Query user by id
        user = cursor.fetchone()  # Fetch single row
        conn.close()  # Close connection

        if user:
            return dict(user)  # Convert row to dict if found
        return None  # Return None if missing

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Fetch a user by email during login/signup flows."""
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor

        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))  # Query by email
        user = cursor.fetchone()  # Fetch row
        conn.close()  # Close connection

        if user:
            return dict(user)  # Return dict if found
        return None  # Otherwise None

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Fetch a user by username (legacy helper)."""
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor

        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))  # Query by username
        user = cursor.fetchone()  # Fetch row
        conn.close()  # Close connection

        if user:
            return dict(user)  # Return dict if found
        return None  # Otherwise None

    def get_user_preferences(self, user_id: int) -> Optional[Dict]:
        """Return user preferences as JSON (or legacy shape) for analysis decisions."""
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor

        cursor.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,))  # Query prefs by user id
        prefs = cursor.fetchone()  # Fetch row
        conn.close()  # Close connection

        if not prefs:
            return None  # No preferences stored

        prefs_dict = dict(prefs)  # Convert row to dict

        if prefs_dict.get('preferences_json'):
            try:
                return json.loads(prefs_dict['preferences_json'])  # Return parsed JSON prefs when present
            except json.JSONDecodeError:
                pass  # Fallback to legacy fields below on parse error

        # Legacy shape fallback
        return {
            "enabled": True,
            "categories": {
                "language": {
                    "enabled": bool(prefs_dict.get('language_filter', True)),
                    "action": "mute",
                    "duration": 4,
                },
                "sexual": {
                    "enabled": bool(prefs_dict.get('sexual_content_filter', True)),
                    "action": "skip",
                    "duration": 12,
                },
                "violence": {
                    "enabled": bool(prefs_dict.get('violence_filter', True)),
                    "action": "fast_forward",
                    "duration": 8,
                },
            },
            "sensitivity": 0.7,
        }  # Return legacy-structured preferences if JSON missing

    def verify_user(self, email: str) -> Optional[Dict]:
        """Helper used by auth flows to look up the user."""
        return self.get_user_by_email(email)  # Reuse email lookup

    def update_user_preferences(self, user_id: int, preferences: Dict) -> bool:
        """Persist updated preferences and backfill legacy columns for compatibility."""
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor

        # Persist the full JSON shape
        preferences_json = json.dumps(preferences)  # Serialize preferences
        cursor.execute(
            'UPDATE user_preferences SET preferences_json = ? WHERE user_id = ?',
            (preferences_json, user_id)
        )  # Update JSON blob

        # Also backfill legacy columns for compatibility with old code paths/tests
        legacy_updates = {
            'language_filter': preferences.get('categories', {}).get('language', {}).get('enabled', True),
            'sexual_content_filter': preferences.get('categories', {}).get('sexual', {}).get('enabled', True),
            'violence_filter': preferences.get('categories', {}).get('violence', {}).get('enabled', True),
            'language_sensitivity': 'medium',
            'sexual_content_sensitivity': 'medium',
            'violence_sensitivity': 'medium',
        }  # Derive legacy columns from new structure
        cursor.execute(
            '''UPDATE user_preferences
               SET language_filter = :language_filter,
                   sexual_content_filter = :sexual_content_filter,
                   violence_filter = :violence_filter,
                   language_sensitivity = :language_sensitivity,
                   sexual_content_sensitivity = :sexual_content_sensitivity,
                   violence_sensitivity = :violence_sensitivity
               WHERE user_id = :user_id''',
            {**legacy_updates, 'user_id': user_id}
        )  # Update legacy columns for compatibility

        conn.commit()  # Save updates
        success = cursor.rowcount > 0  # True if any row updated
        conn.close()  # Close connection

        return success  # Return update status

    def store_user_token(self, user_id: int, token: str, expires_at: datetime) -> None:
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor
        cursor.execute(
            'INSERT OR REPLACE INTO auth_tokens (token, user_id, expires_at) VALUES (?, ?, ?)',
            (token, user_id, expires_at.isoformat())
        )  # Insert or update token record
        conn.commit()  # Save token
        conn.close()  # Close connection

    def get_user_by_token(self, token: str) -> Optional[int]:
        conn = self.get_connection()  # Open connection
        cursor = conn.cursor()  # Get cursor
        cursor.execute('SELECT * FROM auth_tokens WHERE token = ?', (token,))  # Lookup token row
        token_row = cursor.fetchone()  # Fetch token row
        if not token_row:
            conn.close()  # Close connection if not found
            return None  # No token found

        # Validate expiry
        expires_at = datetime.fromisoformat(token_row['expires_at'])  # Parse expiry timestamp
        if expires_at < datetime.utcnow():
            cursor.execute('DELETE FROM auth_tokens WHERE token = ?', (token,))  # Remove expired token
            conn.commit()  # Persist deletion
            conn.close()  # Close connection
            return None  # Token expired

        user = self.get_user_by_id(token_row['user_id'])  # Fetch user for token
        conn.close()  # Close connection
        return user['id'] if user else None  # Return user id if found else None

    def validate_token(self, token: str) -> Optional[int]:
        """Return user_id for a valid (non-expired) token, else None (used by require_auth)."""
        return self.get_user_by_token(token)  # Delegate validation to token lookup
