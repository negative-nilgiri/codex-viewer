import json
import sqlite3
from pathlib import Path

from session_viewer_backend.database import connect, initialize
from session_viewer_backend.discovery import discover_sessions
from session_viewer_backend.repository import get_messages, list_sessions
from session_viewer_backend.sync import sync_session


SESSION_ID = "019fdbaf-c2ea-7e50-ae8f-8fa79e733904"


def make_rollout(tmp_path: Path):
    sessions_root = tmp_path / "sessions"
    rollout = (
        sessions_root
        / "codex_2"
        / "2026"
        / "08"
        / "30"
        / f"rollout-test-{SESSION_ID}.jsonl"
    )
    rollout.parent.mkdir(parents=True)
    events = [
        {
            "timestamp": "2026-08-30T08:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": SESSION_ID,
                "timestamp": "2026-08-30T08:00:00Z",
                "cwd": "/workspace/discovery-test",
            },
        },
        {
            "timestamp": "2026-08-30T08:00:01Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Discovered **title**",
            },
        },
    ]
    rollout.write_text("".join(json.dumps(event) + "\n" for event in events))
    return sessions_root, rollout


def test_discovery_is_shallow_idempotent_and_preserves_missing_session(tmp_path):
    database = tmp_path / "viewer.sqlite3"
    sessions_root, rollout = make_rollout(tmp_path)

    first = discover_sessions(database, sessions_root)
    second = discover_sessions(database, sessions_root)

    assert (first.found, first.added) == (1, 1)
    assert (second.found, second.added, second.refreshed) == (1, 0, 1)
    session = list_sessions(database)[0]
    assert session["title"] == "Discovered **title**"
    assert session["workspace"] == "discovery-test"
    assert session["indexed"] is False
    assert session["source_present"] is True
    assert get_messages(database, "codex_2", SESSION_ID, 0, 30)["items"] == []

    sync_session(database, sessions_root, "codex_2", SESSION_ID)
    rollout.unlink()
    missing = discover_sessions(database, sessions_root)
    session = list_sessions(database)[0]

    assert missing.unavailable == 1
    assert session["indexed"] is True
    assert session["source_present"] is False
    assert session["message_count"] == 1


def test_initialize_migrates_a_version_one_catalog(tmp_path):
    database = tmp_path / "viewer.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_info (version INTEGER NOT NULL);
            INSERT INTO schema_info(version) VALUES (1);
            CREATE TABLE sessions (
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
            """
        )

    initialize(database)

    with connect(database) as connection:
        version = connection.execute("SELECT version FROM schema_info").fetchone()[0]
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(sessions)")
        }
    assert version == 2
    assert {"source_present", "last_discovered_at"} <= columns
