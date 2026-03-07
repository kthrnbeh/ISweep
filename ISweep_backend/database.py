"""
ISWEEP COMPONENT: Persistence Layer

This module wraps SQLite access for users, preferences, and auth tokens. The Flask
app imports Database to store user accounts, bearer tokens, and filtering settings
that drive ContentAnalyzer decisions.

System connection:
    Backend endpoints -> Database -> persist/fetch users, preferences, tokens -> /event
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, Optional, Tuple

class Database:
    """Simple SQLite database handler for user preferences."""
    
    def __init__(self, db_path: str = 'isweep.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Open a connection with row_factory set so rows can be dict-converted easily."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize database schema for users, preferences, and auth tokens."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Create users table with email/password support
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Best-effort migrations for existing databases
        for alter in [
            "ALTER TABLE users ADD COLUMN email TEXT",
            "ALTER TABLE users ADD COLUMN password_hash TEXT",
        ]:
            try:
                cursor.execute(alter)
            except sqlite3.OperationalError:
                pass

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
        ''')

        try:
            cursor.execute("ALTER TABLE user_preferences ADD COLUMN preferences_json TEXT")
        except sqlite3.OperationalError:
            pass

        # Simple token store for dev
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_user(self, email: str, password_hash: str, username: Optional[str] = None) -> Optional[int]:
        """Create a new user and seed default preferences used by the decision engine."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Default username fallback to email local-part when not provided
            username_to_store = username or email.split('@')[0]

            cursor.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                (username_to_store, email, password_hash)
            )
            user_id = cursor.lastrowid

            # Default preferences aligned with requested structure
            default_preferences = {
                "enabled": True,
                "categories": {
                    "language": {"enabled": True, "action": "mute", "duration": 4},
                    "sexual": {"enabled": True, "action": "skip", "duration": 12},
                    "violence": {"enabled": True, "action": "fast_forward", "duration": 8},
                },
                "sensitivity": 0.7,
            }

            cursor.execute(
                'INSERT INTO user_preferences (user_id, preferences_json) VALUES (?, ?)',
                (user_id, json.dumps(default_preferences))
            )

            conn.commit()
            return user_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Fetch a user row by id for auth and preference lookups."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return dict(user)
        return None

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Fetch a user by email during login/signup flows."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            return dict(user)
        return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Fetch a user by username (legacy helper)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return dict(user)
        return None
    
    def get_user_preferences(self, user_id: int) -> Optional[Dict]:
        """Return user preferences as JSON (or legacy shape) for analysis decisions."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,))
        prefs = cursor.fetchone()
        conn.close()
        
        if not prefs:
            return None

        prefs_dict = dict(prefs)

        if prefs_dict.get('preferences_json'):
            try:
                return json.loads(prefs_dict['preferences_json'])
            except json.JSONDecodeError:
                pass  # Fallback to legacy fields below

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
        }

    def verify_user(self, email: str) -> Optional[Dict]:
        """Helper used by auth flows to look up the user."""
        return self.get_user_by_email(email)
    
    def update_user_preferences(self, user_id: int, preferences: Dict) -> bool:
        """Persist updated preferences and backfill legacy columns for compatibility."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Persist the full JSON shape
        preferences_json = json.dumps(preferences)
        cursor.execute(
            'UPDATE user_preferences SET preferences_json = ? WHERE user_id = ?',
            (preferences_json, user_id)
        )

        # Also backfill legacy columns for compatibility with old code paths/tests
        legacy_updates = {
            'language_filter': preferences.get('categories', {}).get('language', {}).get('enabled', True),
            'sexual_content_filter': preferences.get('categories', {}).get('sexual', {}).get('enabled', True),
            'violence_filter': preferences.get('categories', {}).get('violence', {}).get('enabled', True),
            'language_sensitivity': 'medium',
            'sexual_content_sensitivity': 'medium',
            'violence_sensitivity': 'medium',
        }
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
        )

        conn.commit()
        success = cursor.rowcount > 0
        conn.close()

        return success

    def store_user_token(self, user_id: int, token: str, expires_at: datetime) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO auth_tokens (token, user_id, expires_at) VALUES (?, ?, ?)',
            (token, user_id, expires_at.isoformat())
        )
        conn.commit()
        conn.close()

    def get_user_by_token(self, token: str) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM auth_tokens WHERE token = ?', (token,))
        token_row = cursor.fetchone()
        if not token_row:
            conn.close()
            return None

        # Validate expiry
        expires_at = datetime.fromisoformat(token_row['expires_at'])
        if expires_at < datetime.utcnow():
            cursor.execute('DELETE FROM auth_tokens WHERE token = ?', (token,))
            conn.commit()
            conn.close()
            return None

        user = self.get_user_by_id(token_row['user_id'])
        conn.close()
        return user['id'] if user else None

    def validate_token(self, token: str) -> Optional[int]:
        """Return user_id for a valid (non-expired) token, else None (used by require_auth)."""
        return self.get_user_by_token(token)
