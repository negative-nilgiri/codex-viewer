import json
from pathlib import Path

import pytest

from session_viewer_backend.repository import get_messages, list_sessions
from session_viewer_backend.rollout import RolloutError
from session_viewer_backend.sync import sync_session


SESSION_ID = "019fdbaf-c2ea-7e50-ae8f-8fa79e733904"


def event(timestamp, kind, **payload):
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {"type": kind, **payload},
    }


def write_lines(path: Path, events, partial=b""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"".join(json.dumps(item).encode() + b"\n" for item in events) + partial
    )


@pytest.fixture
def archive(tmp_path):
    sessions_root = tmp_path / "sessions"
    rollout = (
        sessions_root
        / "codex_2"
        / "2026"
        / "08"
        / "30"
        / f"rollout-test-{SESSION_ID}.jsonl"
    )
    events = [
        {
            "timestamp": "2026-08-30T08:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": SESSION_ID,
                "timestamp": "2026-08-30T08:00:00Z",
                "cwd": "/workspace/project",
            },
        },
        event("2026-08-30T08:00:01Z", "user_message", message="Hello **Markdown**"),
        {
            "timestamp": "2026-08-30T08:00:02Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "exec_command"},
        },
        event("2026-08-30T08:00:03Z", "agent_message", message="Hello back"),
    ]
    write_lines(rollout, events)
    return tmp_path / "viewer.sqlite3", sessions_root, rollout


def test_first_sync_is_incremental_idempotent_and_ignores_tools(archive):
    database, sessions_root, rollout = archive
    original = rollout.read_bytes()

    first = sync_session(database, sessions_root, "codex_2", SESSION_ID[:8])
    second = sync_session(database, sessions_root, "codex_2", SESSION_ID)

    assert first.added_messages == 2
    assert first.message_count == 2
    assert second.added_messages == 0
    assert second.up_to_date is True
    assert rollout.read_bytes() == original
    messages = get_messages(database, "codex_2", SESSION_ID, 0, 30)
    assert [item["role"] for item in messages["items"]] == ["user", "assistant"]
    assert "exec_command" not in repr(messages)


def test_append_imports_only_new_complete_lines(archive):
    database, sessions_root, rollout = archive
    first = sync_session(database, sessions_root, "codex_2", SESSION_ID)
    old_offset = first.last_complete_offset
    appended = event("2026-08-30T08:01:00Z", "user_message", message="New message")
    encoded = json.dumps(appended).encode()

    with rollout.open("ab") as destination:
        destination.write(encoded[:20])
    partial = sync_session(database, sessions_root, "codex_2", SESSION_ID)
    assert partial.added_messages == 0
    assert partial.last_complete_offset == old_offset

    with rollout.open("ab") as destination:
        destination.write(encoded[20:] + b"\n")
    completed = sync_session(database, sessions_root, "codex_2", SESSION_ID)
    assert completed.added_messages == 1
    assert completed.message_count == 3
    assert completed.last_complete_offset == rollout.stat().st_size


def test_truncated_rollout_is_rebuilt(archive):
    database, sessions_root, rollout = archive
    sync_session(database, sessions_root, "codex_2", SESSION_ID)
    replacement = [
        event("2026-08-30T09:00:00Z", "user_message", message="Replacement")
    ]
    write_lines(rollout, replacement)

    result = sync_session(database, sessions_root, "codex_2", SESSION_ID)

    assert result.rebuilt is True
    assert result.message_count == 1
    messages = get_messages(database, "codex_2", SESSION_ID, 0, 30)
    assert messages["items"][0]["markdown"] == "Replacement"


def test_same_uuid_in_two_profiles_does_not_collide(archive):
    database, sessions_root, source = archive
    second = (
        sessions_root
        / "codex_1"
        / "2026"
        / "08"
        / "30"
        / source.name
    )
    write_lines(
        second,
        [event("2026-08-30T10:00:00Z", "user_message", message="Other profile")],
    )

    sync_session(database, sessions_root, "codex_2", SESSION_ID)
    sync_session(database, sessions_root, "codex_1", SESSION_ID)

    rows = list_sessions(database)
    assert {(row["profile"], row["session_id"]) for row in rows} == {
        ("codex_1", SESSION_ID),
        ("codex_2", SESSION_ID),
    }


def test_ambiguous_prefix_is_rejected(archive):
    database, sessions_root, source = archive
    other_id = "019fdbaf-1111-2222-3333-444444444444"
    other = source.with_name(f"rollout-test-{other_id}.jsonl")
    write_lines(other, [event("2026-08-30T10:00:00Z", "user_message", message="Other")])

    with pytest.raises(RolloutError, match="ambiguous"):
        sync_session(database, sessions_root, "codex_2", "019fdbaf")
