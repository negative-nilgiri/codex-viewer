import json

import pytest

from session_viewer_backend.adapters import get_adapter
from session_viewer_backend.archive import export_archive
from session_viewer_backend.discovery import discover_sessions
from session_viewer_backend.repository import get_messages, get_session
from session_viewer_backend.rollout import RolloutError
from session_viewer_backend.sources import SourceDefinition
from session_viewer_backend.sync import sync_session


SESSION_ID = "019fdbaf-c2ea-7e50-ae8f-8fa79e733904"


def write_codex_session(path):
    path.parent.mkdir(parents=True)
    events = [
        {
            "timestamp": "2026-08-30T08:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": SESSION_ID,
                "timestamp": "2026-08-30T08:00:00Z",
                "cwd": "/workspace/archive-test",
            },
        },
        {
            "timestamp": "2026-08-30T08:00:01Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "Hello **archive**"},
        },
        {
            "timestamp": "2026-08-30T08:00:02Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "not_exported"},
        },
        {
            "timestamp": "2026-08-30T08:00:03Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Stored forever."},
        },
    ]
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def test_archive_round_trip_preserves_indexed_conversation_and_detects_damage(tmp_path):
    database = tmp_path / "viewer.sqlite3"
    transcript = tmp_path / "codex" / f"rollout-{SESSION_ID}.jsonl"
    archives = tmp_path / "archives"
    write_codex_session(transcript)
    codex_source = SourceDefinition("personal", "codex", transcript.parent)

    sync_session(database, (codex_source,), "personal", SESSION_ID)
    result = export_archive(database, archives, "personal", SESSION_ID, "codex")

    assert result.message_count == 2
    archive_path = archives / f"{SESSION_ID}.jsonl"
    records = [json.loads(line) for line in archive_path.read_text().splitlines()]
    assert records[0]["origin"] == {"source": "personal", "adapter": "codex"}
    assert [record["type"] for record in records] == [
        "session",
        "message",
        "message",
        "end",
    ]
    assert "not_exported" not in archive_path.read_text()

    archive_source = SourceDefinition("archive", "archive", archives)
    discovered = discover_sessions(database, (archive_source,))
    assert (discovered.found, discovered.added) == (1, 1)
    sync_session(database, (archive_source,), "archive", SESSION_ID)

    imported = get_messages(database, "archive", SESSION_ID, 0, 10)["items"]
    assert [(item["role"], item["markdown"]) for item in imported] == [
        ("user", "Hello **archive**"),
        ("assistant", "Stored forever."),
    ]
    assert get_session(database, "archive", SESSION_ID)["workspace"] == "archive-test"

    raw = archive_path.read_bytes()
    archive_path.write_bytes(raw.replace(b"Stored forever.", b"Stored for-now."))
    with pytest.raises(RolloutError, match="checksum does not match"):
        get_adapter("archive").validate(archive_path)
