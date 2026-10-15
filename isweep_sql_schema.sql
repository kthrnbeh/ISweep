-- ISweep relational filter schema
--
-- This is an additive SQLite schema for ISweep. It does not delete, replace,
-- or rewrite the existing users, user_preferences, auth_tokens, or cache tables.
-- The current JSON preference path can continue working while the backend is
-- migrated gradually to these tables.

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- Predefined filter categories.
CREATE TABLE IF NOT EXISTS isweep_filter_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Predefined words belonging to a category.
CREATE TABLE IF NOT EXISTS isweep_filter_words (
    word_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    normalized_word TEXT NOT NULL,
    display_word TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id)
        REFERENCES isweep_filter_categories(category_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    UNIQUE (category_id, normalized_word)
);

-- One row records whether a user selected a predefined word.
-- The same user cannot have the same word more than once.
CREATE TABLE IF NOT EXISTS isweep_user_filter_words (
    user_id INTEGER NOT NULL,
    word_id INTEGER NOT NULL,
    selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
    action TEXT NOT NULL DEFAULT 'mute'
        CHECK (action IN ('mute', 'mask', 'skip', 'fast_forward')),
    duration_seconds REAL NOT NULL DEFAULT 4 CHECK (duration_seconds >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, word_id),
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    FOREIGN KEY (word_id)
        REFERENCES isweep_filter_words(word_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

-- Words or phrases created by a specific user.
CREATE TABLE IF NOT EXISTS isweep_custom_words (
    custom_word_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    normalized_word TEXT NOT NULL,
    display_word TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 1 CHECK (selected IN (0, 1)),
    action TEXT NOT NULL DEFAULT 'mute'
        CHECK (action IN ('mute', 'mask', 'skip', 'fast_forward')),
    duration_seconds REAL NOT NULL DEFAULT 4 CHECK (duration_seconds >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    UNIQUE (user_id, normalized_word)
);

-- Safe, token-free diagnostics for preference synchronization.
-- Do not store access tokens, raw audio, or complete transcripts here.
CREATE TABLE IF NOT EXISTS isweep_preference_sync_events (
    sync_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    preference_source TEXT NOT NULL,
    preference_schema TEXT NOT NULL,
    selected_word_count INTEGER NOT NULL DEFAULT 0 CHECK (selected_word_count >= 0),
    word_preview_json TEXT NOT NULL DEFAULT '[]',
    result TEXT NOT NULL CHECK (result IN ('success', 'failure')),
    failure_reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_isweep_words_category
    ON isweep_filter_words(category_id);

CREATE INDEX IF NOT EXISTS idx_isweep_user_words_selected
    ON isweep_user_filter_words(user_id, selected);

CREATE INDEX IF NOT EXISTS idx_isweep_custom_words_selected
    ON isweep_custom_words(user_id, selected);

CREATE INDEX IF NOT EXISTS idx_isweep_sync_events_user_time
    ON isweep_preference_sync_events(user_id, created_at);

-- Seed the categories without overwriting existing rows.
INSERT OR IGNORE INTO isweep_filter_categories (category_key, display_name)
VALUES
    ('language', 'Language'),
    ('intimacy', 'Intimacy'),
    ('violence', 'Violence'),
    ('substances', 'Substances'),
    ('horror', 'Horror & Fears');

-- Canonical selected-word view used when the backend builds blocklist.items.
-- Predefined and custom words are combined and deduplicated.
CREATE VIEW IF NOT EXISTS isweep_selected_words AS
SELECT
    ufw.user_id AS user_id,
    fw.normalized_word AS normalized_word,
    fw.display_word AS display_word,
    fc.category_key AS category_key,
    ufw.action AS action,
    ufw.duration_seconds AS duration_seconds
FROM isweep_user_filter_words AS ufw
JOIN isweep_filter_words AS fw ON fw.word_id = ufw.word_id
JOIN isweep_filter_categories AS fc ON fc.category_id = fw.category_id
WHERE ufw.selected = 1
  AND fw.is_active = 1

UNION

SELECT
    cw.user_id AS user_id,
    cw.normalized_word AS normalized_word,
    cw.display_word AS display_word,
    'custom' AS category_key,
    cw.action AS action,
    cw.duration_seconds AS duration_seconds
FROM isweep_custom_words AS cw
WHERE cw.selected = 1;

COMMIT;

-- Example verification query after the backend has created a user with id 1:
-- SELECT normalized_word, category_key
-- FROM isweep_selected_words
-- WHERE user_id = 1
-- ORDER BY normalized_word;
