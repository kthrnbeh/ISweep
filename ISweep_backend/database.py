"""
ISWEEP COMPONENT: Persistence Layer

This module wraps SQLite access for users, preferences, auth tokens, and
account-owned learning records. The Flask app uses this class so ownership
checks, foreign-key enforcement, and transaction boundaries are consistent
across every endpoint.

System connection:
    Backend endpoints -> Database -> users/preferences/tokens/learning records
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, Optional


class Database:
    """SQLite gateway that keeps account ownership close to every query."""

    def __init__(self, db_path: str = 'isweep.db'):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        """Open a dict-friendly connection with foreign keys enabled per connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # SQLite does not persist this pragma in the file; set it on every
        # connection so deleting an account cannot leave orphaned learning data.
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    def init_db(self):
        """Create missing tables and additive compatibility structures."""
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS video_analysis_cache (
                video_id TEXT NOT NULL,
                preferences_fingerprint TEXT NOT NULL,
                status TEXT,
                source TEXT,
                events_json TEXT NOT NULL,
                cleaned_captions_json TEXT NOT NULL,
                clean_captions_json TEXT NOT NULL,
                failure_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (video_id, preferences_fingerprint)
            )
        ''')  # Cache table for /videos/analyze responses keyed by video + preferences

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audio_stt_chunk_cache (
                video_id TEXT NOT NULL,
                preferences_fingerprint TEXT NOT NULL,
                stt_model TEXT,
                chunk_start_seconds REAL NOT NULL,
                chunk_end_seconds REAL NOT NULL,
                status TEXT,
                source TEXT,
                events_json TEXT NOT NULL,
                cleaned_captions_json TEXT NOT NULL,
                failure_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (
                    video_id,
                    preferences_fingerprint,
                    stt_model,
                    chunk_start_seconds,
                    chunk_end_seconds
                )
            )
        ''')  # Cache table for /audio/analyze chunk-level STT outputs

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mute_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NULL,
                video_id TEXT NOT NULL,
                matched_word TEXT NOT NULL,
                caption_source TEXT NOT NULL,
                timing_method TEXT NOT NULL CHECK (
                    timing_method IN ('verified', 'estimated')
                ),
                predicted_start_seconds REAL NOT NULL,
                predicted_end_seconds REAL NOT NULL,
                actual_mute_start_seconds REAL NULL,
                actual_mute_end_seconds REAL NULL,
                playback_speed REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'predicted' CHECK (
                    status IN ('predicted', 'muted', 'restored', 'skipped', 'canceled', 'failed')
                ),
                playback_context_json TEXT NOT NULL DEFAULT '{}',
                dedupe_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')  # Store opt-in playback timing metadata without raw audio

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mute_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL UNIQUE,
                result TEXT NOT NULL CHECK (
                    result IN ('correct', 'early', 'late', 'missed')
                ),
                corrected_start_seconds REAL NULL,
                corrected_end_seconds REAL NULL,
                feedback_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES mute_events(event_id) ON DELETE CASCADE
            )
        ''')  # One replaceable feedback correction per mute event

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learning_event_reviews (
                event_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (
                    state IN ('active', 'archived', 'excluded')
                ),
                reason TEXT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES mute_events(event_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')  # Reversible per-account review state; historical events remain intact

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_learning_event_reviews_user_state
            ON learning_event_reviews (user_id, state, updated_at)
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS trg_learning_event_reviews_owner_insert
            BEFORE INSERT ON learning_event_reviews
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM mute_events
                WHERE event_id = NEW.event_id AND user_id = NEW.user_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'learning event review owner mismatch');
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS trg_learning_event_reviews_owner_update
            BEFORE UPDATE OF event_id, user_id ON learning_event_reviews
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM mute_events
                WHERE event_id = NEW.event_id AND user_id = NEW.user_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'learning event review owner mismatch');
            END
        ''')

        # Review state is separate from the event so archive/exclude remains
        # reversible and the original playback history is never deleted.

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mute_events_lookup
            ON mute_events (user_id, video_id, matched_word, predicted_start_seconds)
        ''')  # Support future same-video/word correction lookup

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

    @staticmethod
    def _mute_event_dict(row):
        if not row:
            return None
        data = dict(row)
        try:
            data['playback_context'] = json.loads(data.pop('playback_context_json') or '{}')
        except json.JSONDecodeError:
            data['playback_context'] = {}
            data.pop('playback_context_json', None)
        feedback_id = data.pop('feedback_id', None)
        feedback_result = data.pop('feedback_result', None)
        feedback_start = data.pop('feedback_corrected_start_seconds', None)
        feedback_end = data.pop('feedback_corrected_end_seconds', None)
        feedback_at = data.pop('feedback_at', None)
        if feedback_id is not None:
            data['feedback'] = {
                'feedback_id': feedback_id,
                'result': feedback_result,
                'corrected_start_seconds': feedback_start,
                'corrected_end_seconds': feedback_end,
                'feedback_at': feedback_at,
            }
        return data

    @staticmethod
    def _mute_feedback_dict(row):
        return dict(row) if row else None

    def create_mute_event(self, user_id: int, event: Dict) -> tuple[Dict, bool]:
        """Create an account-owned learning event, or return its existing dedupe record."""
        conn = self.get_connection()
        try:
            try:
                conn.execute(
                    '''INSERT INTO mute_events (
                           user_id, video_id, matched_word, caption_source, timing_method,
                           predicted_start_seconds, predicted_end_seconds,
                           actual_mute_start_seconds, actual_mute_end_seconds,
                           playback_speed, status, playback_context_json, dedupe_key
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        user_id,
                        event['video_id'],
                        event['matched_word'],
                        event['caption_source'],
                        event['timing_method'],
                        event['predicted_start_seconds'],
                        event['predicted_end_seconds'],
                        event.get('actual_mute_start_seconds'),
                        event.get('actual_mute_end_seconds'),
                        event['playback_speed'],
                        event['status'],
                        json.dumps(event.get('playback_context', {}), separators=(',', ':'), sort_keys=True),
                        event['dedupe_key'],
                    ),
                )
                conn.commit()
                created = True
            except sqlite3.IntegrityError as error:
                if 'dedupe_key' not in str(error).lower():
                    raise
                existing = conn.execute(
                    'SELECT * FROM mute_events WHERE dedupe_key = ?',
                    (event['dedupe_key'],),
                ).fetchone()
                if existing and existing['user_id'] != user_id:
                    raise PermissionError('event dedupe key belongs to another account')
                created = False

            row = conn.execute(
                'SELECT * FROM mute_events WHERE user_id = ? AND dedupe_key = ?',
                (user_id, event['dedupe_key']),
            ).fetchone()
            if not row:
                raise sqlite3.IntegrityError('event dedupe record is not owned by the authenticated user')
            return self._mute_event_dict(row), created
        finally:
            conn.close()

    def list_mute_events(self, user_id: int, limit: int, offset: int) -> tuple[list[Dict], int]:
        conn = self.get_connection()
        try:
            total = conn.execute(
                'SELECT COUNT(*) FROM mute_events WHERE user_id = ?',
                (user_id,),
            ).fetchone()[0]
            rows = conn.execute(
                '''SELECT e.*, COALESCE(r.state, 'active') AS review_state,
                          r.reason AS review_reason,
                          r.updated_at AS review_updated_at,
                          f.feedback_id AS feedback_id,
                          f.result AS feedback_result,
                          f.corrected_start_seconds AS feedback_corrected_start_seconds,
                          f.corrected_end_seconds AS feedback_corrected_end_seconds,
                          f.feedback_at AS feedback_at
                   FROM mute_events e
                   LEFT JOIN mute_feedback f ON f.event_id = e.event_id
                   LEFT JOIN learning_event_reviews r ON r.event_id = e.event_id
                   WHERE e.user_id = ?
                   ORDER BY e.event_id DESC
                   LIMIT ? OFFSET ?''',
                (user_id, limit, offset),
            ).fetchall()
            return [self._mute_event_dict(row) for row in rows], total
        finally:
            conn.close()

    def update_mute_event_reviews(
        self,
        user_id: int,
        event_ids: list[int],
        state: str,
        reason: Optional[str] = None,
    ) -> list[Dict]:
        """Atomically set review state for account-owned learning events.

        The ownership query runs inside the same write transaction as the
        upsert. If even one requested event belongs to another account, the
        transaction rolls back instead of partially changing the batch.
        """
        if not event_ids:
            raise ValueError('event_ids must not be empty')
        conn = self.get_connection()
        try:
            conn.execute('BEGIN IMMEDIATE')
            placeholders = ','.join('?' for _ in event_ids)
            rows = conn.execute(
                f'''SELECT event_id FROM mute_events
                    WHERE user_id = ? AND event_id IN ({placeholders})''',
                [user_id, *event_ids],
            ).fetchall()
            owned_ids = {int(row['event_id']) for row in rows}
            if owned_ids != set(event_ids):
                raise PermissionError('one or more learning events are not owned by this account')

            conn.executemany(
                '''INSERT INTO learning_event_reviews (event_id, user_id, state, reason)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(event_id) DO UPDATE SET
                       user_id = excluded.user_id,
                       state = excluded.state,
                       reason = excluded.reason,
                       updated_at = CURRENT_TIMESTAMP''',
                [(event_id, user_id, state, reason) for event_id in event_ids],
            )
            updated = conn.execute(
                f'''SELECT event_id, user_id, state, reason, updated_at
                    FROM learning_event_reviews
                    WHERE user_id = ? AND event_id IN ({placeholders})
                    ORDER BY event_id''',
                [user_id, *event_ids],
            ).fetchall()
            conn.commit()
            return [dict(row) for row in updated]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_mute_event_for_user(self, user_id: int, event_id: int) -> Optional[Dict]:
        conn = self.get_connection()
        try:
            row = conn.execute(
                'SELECT * FROM mute_events WHERE event_id = ? AND user_id = ?',
                (event_id, user_id),
            ).fetchone()
            return self._mute_event_dict(row)
        finally:
            conn.close()

    def upsert_mute_feedback(self, user_id: int, event_id: int, feedback: Dict) -> Optional[Dict]:
        conn = self.get_connection()
        try:
            owned = conn.execute(
                'SELECT event_id FROM mute_events WHERE event_id = ? AND user_id = ?',
                (event_id, user_id),
            ).fetchone()
            if not owned:
                return None
            conn.execute(
                '''INSERT INTO mute_feedback (
                       event_id, result, corrected_start_seconds, corrected_end_seconds
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(event_id) DO UPDATE SET
                       result = excluded.result,
                       corrected_start_seconds = excluded.corrected_start_seconds,
                       corrected_end_seconds = excluded.corrected_end_seconds,
                       feedback_at = CURRENT_TIMESTAMP''',
                (
                    event_id,
                    feedback['result'],
                    feedback.get('corrected_start_seconds'),
                    feedback.get('corrected_end_seconds'),
                ),
            )
            conn.commit()
            row = conn.execute(
                'SELECT * FROM mute_feedback WHERE event_id = ?',
                (event_id,),
            ).fetchone()
            return self._mute_feedback_dict(row)
        finally:
            conn.close()

    def delete_mute_feedback(self, user_id: int, event_id: int) -> bool:
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                '''DELETE FROM mute_feedback
                   WHERE event_id = ?
                     AND EXISTS (
                         SELECT 1 FROM mute_events
                         WHERE mute_events.event_id = mute_feedback.event_id
                           AND mute_events.user_id = ?
                     )''',
                (event_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_verified_corrections(
        self,
        user_id: int,
        video_id: str,
        matched_word: str,
        start_seconds: Optional[float],
        proximity_seconds: float,
        limit: int,
    ) -> list[Dict]:
        # Only validated feedback attached to a trusted event can affect a
        # future mute. User-reported missed words are the one intentional
        # exception: they carry their own corrected interval and are marked
        # separately from successful mute examples below.
        conn = self.get_connection()
        try:
            rows = conn.execute(
                '''SELECT
                       e.event_id,
                       e.video_id,
                       e.matched_word,
                       e.caption_source,
                       e.timing_method,
                       e.predicted_start_seconds,
                       e.predicted_end_seconds,
                       e.status,
                       f.feedback_id,
                       f.result,
                       f.corrected_start_seconds,
                       f.corrected_end_seconds,
                       f.feedback_at,
                       COALESCE(r.state, 'active') AS review_state,
                       r.reason AS review_reason
                   FROM mute_events e
                   JOIN mute_feedback f ON f.event_id = e.event_id
                   LEFT JOIN learning_event_reviews r ON r.event_id = e.event_id
                   WHERE e.user_id = ?
                     AND e.video_id = ?
                     AND e.matched_word = ?
                     AND (
                         (
                             e.status IN ('muted', 'restored')
                             AND f.result IN ('correct', 'early', 'late')
                         )
                         OR (
                             e.status = 'skipped'
                             AND e.caption_source = 'user_report'
                             AND f.result = 'missed'
                         )
                     )
                     AND COALESCE(r.state, 'active') != 'excluded'
                     AND f.corrected_start_seconds IS NOT NULL
                     AND f.corrected_end_seconds IS NOT NULL
                     AND f.corrected_start_seconds >= 0
                     AND f.corrected_end_seconds > f.corrected_start_seconds
                     AND (? IS NULL OR ABS(e.predicted_start_seconds - ?) <= ?)
                   ORDER BY e.predicted_start_seconds ASC, f.feedback_at DESC
                   LIMIT ?''',
                (user_id, video_id, matched_word, start_seconds, start_seconds, proximity_seconds, limit),
            ).fetchall()
            corrections = []
            for row in rows:
                correction = dict(row)
                correction['successful_mute_example'] = (
                    correction['status'] in ('muted', 'restored')
                    and correction['result'] in ('correct', 'early', 'late')
                )
                if start_seconds is not None:
                    correction['distance_seconds'] = abs(
                        correction['predicted_start_seconds'] - start_seconds
                    )
                    correction['applicable'] = correction['distance_seconds'] <= proximity_seconds
                else:
                    correction['distance_seconds'] = None
                    correction['applicable'] = False
                corrections.append(correction)
            return corrections
        finally:
            conn.close()

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

    def get_video_analysis_cache(self, video_id: str, preferences_fingerprint: str) -> Optional[Dict]:
        """Return cached /videos/analyze payload for a video + preferences fingerprint."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT *
               FROM video_analysis_cache
               WHERE video_id = ? AND preferences_fingerprint = ?''',
            (video_id, preferences_fingerprint)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        data = dict(row)
        return {
            'status': data.get('status'),
            'source': data.get('source'),
            'events': json.loads(data.get('events_json') or '[]'),
            'cleaned_captions': json.loads(data.get('cleaned_captions_json') or '[]'),
            'clean_captions': json.loads(data.get('clean_captions_json') or '[]'),
            'failure_reason': data.get('failure_reason'),
            'created_at': data.get('created_at'),
            'updated_at': data.get('updated_at'),
        }

    def save_video_analysis_cache(self, video_id: str, preferences_fingerprint: str, payload: Dict) -> None:
        """Upsert cached /videos/analyze payload for a video + preferences fingerprint."""
        events_json = json.dumps(payload.get('events', []), separators=(',', ':'), sort_keys=True)
        cleaned_captions_json = json.dumps(payload.get('cleaned_captions', []), separators=(',', ':'), sort_keys=True)
        clean_captions_json = json.dumps(
            payload.get('clean_captions', payload.get('cleaned_captions', [])),
            separators=(',', ':'),
            sort_keys=True,
        )

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO video_analysis_cache (
                   video_id,
                   preferences_fingerprint,
                   status,
                   source,
                   events_json,
                   cleaned_captions_json,
                   clean_captions_json,
                   failure_reason
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(video_id, preferences_fingerprint)
               DO UPDATE SET
                   status = excluded.status,
                   source = excluded.source,
                   events_json = excluded.events_json,
                   cleaned_captions_json = excluded.cleaned_captions_json,
                   clean_captions_json = excluded.clean_captions_json,
                   failure_reason = excluded.failure_reason,
                   updated_at = CURRENT_TIMESTAMP''',
            (
                video_id,
                preferences_fingerprint,
                payload.get('status'),
                payload.get('source'),
                events_json,
                cleaned_captions_json,
                clean_captions_json,
                payload.get('failure_reason'),
            ),
        )
        conn.commit()
        conn.close()

    def get_audio_stt_chunk_cache(
        self,
        video_id: str,
        preferences_fingerprint: str,
        stt_model: Optional[str],
        chunk_start_seconds: float,
        chunk_end_seconds: float,
    ) -> Optional[Dict]:
        """Return cached /audio/analyze payload for a video/preferences/chunk tuple."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT *
               FROM audio_stt_chunk_cache
               WHERE video_id = ?
                 AND preferences_fingerprint = ?
                 AND COALESCE(stt_model, '') = COALESCE(?, '')
                 AND chunk_start_seconds = ?
                 AND chunk_end_seconds = ?''',
            (video_id, preferences_fingerprint, stt_model, chunk_start_seconds, chunk_end_seconds),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        data = dict(row)
        return {
            'status': data.get('status'),
            'source': data.get('source'),
            'events': json.loads(data.get('events_json') or '[]'),
            'cleaned_captions': json.loads(data.get('cleaned_captions_json') or '[]'),
            'failure_reason': data.get('failure_reason'),
            'created_at': data.get('created_at'),
            'updated_at': data.get('updated_at'),
        }

    def save_audio_stt_chunk_cache(
        self,
        video_id: str,
        preferences_fingerprint: str,
        stt_model: Optional[str],
        chunk_start_seconds: float,
        chunk_end_seconds: float,
        payload: Dict,
    ) -> None:
        """Upsert /audio/analyze chunk-level cached payload."""
        events_json = json.dumps(payload.get('events', []), separators=(',', ':'), sort_keys=True)
        cleaned_captions_json = json.dumps(payload.get('cleaned_captions', []), separators=(',', ':'), sort_keys=True)

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO audio_stt_chunk_cache (
                   video_id,
                   preferences_fingerprint,
                   stt_model,
                   chunk_start_seconds,
                   chunk_end_seconds,
                   status,
                   source,
                   events_json,
                   cleaned_captions_json,
                   failure_reason
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(
                   video_id,
                   preferences_fingerprint,
                   stt_model,
                   chunk_start_seconds,
                   chunk_end_seconds
               )
               DO UPDATE SET
                   status = excluded.status,
                   source = excluded.source,
                   events_json = excluded.events_json,
                   cleaned_captions_json = excluded.cleaned_captions_json,
                   failure_reason = excluded.failure_reason,
                   updated_at = CURRENT_TIMESTAMP''',
            (
                video_id,
                preferences_fingerprint,
                stt_model,
                chunk_start_seconds,
                chunk_end_seconds,
                payload.get('status'),
                payload.get('source'),
                events_json,
                cleaned_captions_json,
                payload.get('failure_reason'),
            ),
        )
        conn.commit()
        conn.close()
