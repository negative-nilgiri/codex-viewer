import sqlite3
from contextlib import closing
from pathlib import Path


SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    profile TEXT NOT NULL,
    session_id TEXT NOT NULL,
    rollout_path TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'Untitled session',
    workspace TEXT,
    created_at TEXT,
    last_activity_at TEXT,
    last_complete_offset INTEGER NOT NULL DEFAULT 0,
    source_size INTEGER NOT NULL DEFAULT 0,
    source_mtime_ns INTEGER,
    source_device INTEGER,
    source_inode INTEGER,
    message_count INTEGER NOT NULL DEFAULT 0,
    last_synced_at TEXT,
    sync_error TEXT,
    PRIMARY KEY (profile, session_id),
    UNIQUE (profile, rollout_path)
);

CREATE INDEX IF NOT EXISTS sessions_by_activity
    ON sessions(last_activity_at DESC);
CREATE INDEX IF NOT EXISTS sessions_by_creation
    ON sessions(created_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    profile TEXT NOT NULL,
    session_id TEXT NOT NULL,
    message_index INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    timestamp TEXT,
    markdown TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    PRIMARY KEY (profile, session_id, message_index),
    UNIQUE (profile, session_id, source_offset),
    FOREIGN KEY (profile, session_id)
        REFERENCES sessions(profile, session_id) ON DELETE CASCADE
);
"""


def connect(database_path: Path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(database_path: Path):
    with closing(connect(database_path)) as connection:
        with connection:
            connection.executescript(SCHEMA)
            row = connection.execute("SELECT version FROM schema_info").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,)
                )
            elif row["version"] != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported database schema {row['version']}; expected {SCHEMA_VERSION}"
                )
