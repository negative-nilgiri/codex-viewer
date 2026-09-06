import json
import sqlite3
from pathlib import Path

import pytest

from session_viewer_backend.database import connect, initialize
from session_viewer_backend.discovery import discover_sessions, load_session_metadata
from session_viewer_backend.repository import get_messages, list_sessions
from session_viewer_backend.sources import SourceDefinition
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
            "timestamp": "2026-08-01T08:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "019fc854-95e2-7901-a1be-b6d229cc92ff",
                "cwd": "/workspace/historical-parent",
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
    metadata = tmp_path / "session_metadata.json"
    metadata.write_text(json.dumps({SESSION_ID: {"title": "Persistent custom title"}}))
    sources = (
        SourceDefinition("codex_2", "codex", sessions_root / "codex_2"),
    )

    first = discover_sessions(database, sources, session_metadata_path=metadata)
    second = discover_sessions(database, sources, session_metadata_path=metadata)

    assert (first.found, first.added) == (1, 1)
    assert (second.found, second.added, second.refreshed) == (1, 0, 1)
    session = list_sessions(database)[0]
    assert session["title"] == "Persistent custom title"
    assert session["title_overridden"] is True
    assert session["workspace"] == "discovery-test"
    assert session["indexed"] is False
    assert session["source_present"] is True
    assert get_messages(database, "codex_2", SESSION_ID, 0, 30)["items"] == []

    sync_session(database, sources, "codex_2", SESSION_ID, metadata)
    rollout.unlink()
    metadata.write_text("{}")
    missing = discover_sessions(database, sources, session_metadata_path=metadata)
    session = list_sessions(database)[0]

    assert missing.unavailable == 1
    assert session["indexed"] is True
    assert session["source_present"] is False
    assert session["message_count"] == 1
    assert session["title"] == "Discovered **title**"
    assert session["title_overridden"] is False


def test_session_metadata_rejects_legacy_title_values(tmp_path):
    metadata = tmp_path / "session_metadata.json"
    metadata.write_text(json.dumps({SESSION_ID: "Legacy title"}))

    with pytest.raises(ValueError, match="metadata object"):
        load_session_metadata(metadata)


def test_discovery_repairs_a_path_assigned_to_historical_session_id(tmp_path):
    database = tmp_path / "viewer.sqlite3"
    sessions_root, rollout = make_rollout(tmp_path)
    sources = (
        SourceDefinition("codex_2", "codex", sessions_root / "codex_2"),
    )
    historical_id = "019fc854-95e2-7901-a1be-b6d229cc92ff"
    initialize(database)
    with connect(database) as connection:
        connection.execute(
            """
            INSERT INTO sessions(profile, session_id, rollout_path, message_count)
            VALUES (?, ?, ?, 7)
            """,
            ("codex_2", historical_id, str(rollout),),
        )
        connection.execute(
            """
            INSERT INTO sessions(profile, session_id, rollout_path, message_count)
            VALUES (?, ?, ?, 3)
            """,
            ("codex_2", SESSION_ID, "/old/location.jsonl"),
        )
        connection.execute(
            """
            INSERT INTO sessions(profile, session_id, rollout_path)
            VALUES (?, ?, ?)
            """,
            (
                "codex_2",
                "00000000-0000-0000-0000-000000000000",
                "stale://codex_2/empty-artifact/previous-pass",
            ),
        )
        connection.commit()

    result = discover_sessions(database, sources)

    assert (result.found, result.added, result.refreshed) == (1, 0, 1)
    with connect(database) as connection:
        rows = {
            row["session_id"]: row
            for row in connection.execute(
                """
                SELECT session_id, rollout_path, message_count, source_present
                FROM sessions WHERE profile = 'codex_2'
                """
            )
        }
    assert rows[SESSION_ID]["rollout_path"] == str(rollout)
    assert rows[SESSION_ID]["message_count"] == 3
    assert rows[SESSION_ID]["source_present"] == 1
    assert rows[historical_id]["rollout_path"].startswith("stale://codex_2/")
    assert rows[historical_id]["message_count"] == 7
    assert rows[historical_id]["source_present"] == 0
    assert "00000000-0000-0000-0000-000000000000" not in rows


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
    assert version == 3
    assert {"source_present", "last_discovered_at", "title_override"} <= columns
