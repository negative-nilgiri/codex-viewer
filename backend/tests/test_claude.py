import json
from pathlib import Path

from session_viewer_backend.discovery import discover_sessions
from session_viewer_backend.repository import get_messages, list_sessions
from session_viewer_backend.sources import SourceDefinition
from session_viewer_backend.sync import sync_session


SESSION_ID = "087e7ac1-be3c-4f0c-b92a-4ee7a1837026"


def write_lines(path: Path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def claude_event(kind, content, timestamp, **extra):
    return {
        "type": kind,
        "sessionId": SESSION_ID,
        "timestamp": timestamp,
        "cwd": "/workspace/claude-project",
        "isSidechain": False,
        "message": {"role": kind, "content": content},
        **extra,
    }


def test_claude_recursion_filters_non_conversation_records_and_syncs_incrementally(
    tmp_path,
):
    database = tmp_path / "viewer.sqlite3"
    root = tmp_path / "mounted-claude"
    transcript = root / "arbitrary" / "depth" / "conversation.jsonl"
    events = [
        {"type": "ai-title", "sessionId": SESSION_ID, "aiTitle": "Claude title"},
        claude_event(
            "user",
            "<command-name>/model</command-name>",
            "2026-09-06T14:50:00Z",
        ),
        claude_event("user", "A genuine question", "2026-09-06T14:50:01Z"),
        claude_event(
            "assistant",
            [{"type": "thinking", "thinking": "Private reasoning"}],
            "2026-09-06T14:50:02Z",
        ),
        claude_event(
            "assistant",
            [{"type": "tool_use", "name": "Read", "input": {"path": "x"}}],
            "2026-09-06T14:50:03Z",
        ),
        claude_event(
            "user",
            [{"type": "tool_result", "content": "tool output"}],
            "2026-09-06T14:50:04Z",
            toolUseResult={"stdout": "tool output"},
        ),
        claude_event(
            "assistant",
            [
                {"type": "text", "text": "First paragraph."},
                {"type": "text", "text": "Second **Markdown** paragraph."},
            ],
            "2026-09-06T14:50:05Z",
        ),
        {"type": "file-history-snapshot", "snapshot": {}},
    ]
    write_lines(transcript, events)
    write_lines(root / "unrelated" / "events.jsonl", [{"kind": "not-a-session"}])
    sources = (SourceDefinition("claude", "claude", root),)
    metadata = tmp_path / "session_metadata.json"
    metadata.write_text("{}")

    discovered = discover_sessions(database, sources, session_metadata_path=metadata)
    assert discovered.found == 1
    assert list_sessions(database)[0]["title"] == "Claude title"

    first = sync_session(database, sources, "claude", SESSION_ID, metadata)
    messages = get_messages(database, "claude", SESSION_ID, 0, 30)["items"]
    assert first.added_messages == 2
    assert [(message["role"], message["markdown"]) for message in messages] == [
        ("user", "A genuine question"),
        ("assistant", "First paragraph.\n\nSecond **Markdown** paragraph."),
    ]
    assert "Private reasoning" not in repr(messages)
    assert "tool output" not in repr(messages)

    with transcript.open("a") as destination:
        destination.write(
            json.dumps(
                claude_event("user", "An appended prompt", "2026-09-06T14:51:00Z")
            )
            + "\n"
        )
    second = sync_session(database, sources, "claude", SESSION_ID, metadata)
    assert second.added_messages == 1
    assert second.message_count == 3
