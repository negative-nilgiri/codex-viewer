import json

from fastapi.testclient import TestClient

from session_viewer_backend.api import create_app
from session_viewer_backend.config import Settings
from session_viewer_backend.sources import load_sources
from session_viewer_backend.sync import sync_session


SESSION_ID = "019fdbaf-c2ea-7e50-ae8f-8fa79e733904"


def make_client(tmp_path, message_count=4):
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
            "timestamp": "2026-08-30T07:59:59Z",
            "type": "session_meta",
            "payload": {"id": SESSION_ID, "cwd": "/workspace/api-test"},
        },
        *[
            {
                "timestamp": f"2026-08-30T08:00:{index:02d}Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": f"Message {index}",
                },
            }
            for index in range(message_count)
        ],
    ]
    rollout.write_text("".join(json.dumps(item) + "\n" for item in events))
    sources_path = tmp_path / "sources.toml"
    sources_path.write_text(
        '[[sources]]\nid = "codex_2"\nadapter = "codex"\n'
        f"path = {json.dumps(str(sessions_root / 'codex_2'))}\n"
    )
    metadata_path = tmp_path / "session_metadata.json"
    metadata_path.write_text("{}")
    documents_path = tmp_path / "documents"
    documents_path.mkdir()
    settings = Settings(
        tmp_path / "viewer.sqlite3",
        sources_path,
        metadata_path,
        tmp_path / "bookmarks",
        tmp_path / "archives",
        documents_path,
    )
    sync_session(
        settings.database_path,
        load_sources(settings.sources_path),
        "codex_2",
        SESSION_ID,
        metadata_path,
    )
    return TestClient(create_app(settings))


def test_health_list_detail_and_bounded_pagination(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        sessions = client.get("/api/sessions").json()["items"]
        assert len(sessions) == 1
        assert sessions[0]["message_count"] == 4

        detail = client.get(f"/api/sessions/codex_2/{SESSION_ID}")
        assert detail.status_code == 200
        page = client.get(
            f"/api/sessions/codex_2/{SESSION_ID}/messages",
            params={"start": 1, "limit": 2},
        )
        assert page.status_code == 200
        assert page.json()["total"] == 4
        assert [item["message_index"] for item in page.json()["items"]] == [2, 3]


def test_api_rejects_page_larger_than_limit(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get(
            f"/api/sessions/codex_2/{SESSION_ID}/messages",
            params={"limit": 101},
        )
        assert response.status_code == 422


def test_search_finds_message_indexes_case_insensitively(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get(
            f"/api/sessions/codex_2/{SESSION_ID}/search",
            params={"q": "mESSAGE 2"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "query": "mESSAGE 2",
            "total": 1,
            "message_indexes": [3],
        }


def test_session_title_can_be_edited_and_reset_without_rescanning(tmp_path):
    with make_client(tmp_path) as client:
        path = f"/api/sessions/codex_2/{SESSION_ID}/title"
        updated = client.put(path, json={"title": "  A clearer   session title  "})

        assert updated.status_code == 200
        assert updated.json()["title"] == "A clearer session title"
        assert updated.json()["title_overridden"] is True
        assert client.get("/api/sessions").json()["items"][0]["title"] == (
            "A clearer session title"
        )
        metadata = json.loads((tmp_path / "session_metadata.json").read_text())
        assert metadata[SESSION_ID]["title"] == "A clearer session title"

        blank = client.put(path, json={"title": "   "})
        assert blank.status_code == 422

        reset = client.delete(path)
        assert reset.status_code == 200
        assert reset.json()["title"] == "Message 0"
        assert reset.json()["title_overridden"] is False
        assert json.loads((tmp_path / "session_metadata.json").read_text()) == {}


def test_bookmark_backup_export_overwrites_and_restore_reads_snapshot(tmp_path):
    with make_client(tmp_path) as client:
        path = f"/api/sessions/codex_2/{SESSION_ID}/bookmarks"
        first = client.put(
            path,
            json={
                "bookmarks": [
                    {"message_index": 4, "title": "Fourth"},
                    {"message_index": 2, "title": "Second"},
                ]
            },
        )
        assert first.status_code == 200
        assert [item["message_index"] for item in first.json()["bookmarks"]] == [2, 4]

        replacement = client.put(
            path,
            json={"bookmarks": [{"message_index": 3, "title": "Only bookmark"}]},
        )
        assert replacement.status_code == 200

        restored = client.get(path)
        assert restored.status_code == 200
        assert restored.json()["bookmarks"] == [
            {"message_index": 3, "title": "Only bookmark"}
        ]
        backup = json.loads((tmp_path / "bookmarks" / f"{SESSION_ID}.json").read_text())
        assert backup["bookmarks"] == restored.json()["bookmarks"]


def test_archive_endpoint_exports_current_index_without_syncing(tmp_path):
    with make_client(tmp_path, message_count=3) as client:
        response = client.post(f"/api/sessions/codex_2/{SESSION_ID}/archive")

        assert response.status_code == 200
        assert response.json()["message_count"] == 3
        archive = tmp_path / "archives" / f"{SESSION_ID}.jsonl"
        assert archive.is_file()
        assert json.loads(archive.read_text().splitlines()[-1])["message_count"] == 3


def test_documents_are_listed_recursively_and_read_directly(tmp_path):
    client = make_client(tmp_path)
    documents = tmp_path / "documents"
    (documents / "notes").mkdir()
    (documents / "notes" / "diagram.md").write_text(
        "```markdown\n# Not the title\n```\n\n# Actual title\n\n```mermaid\nA --> B\n```\n"
    )
    (documents / "other.md").write_text("Fallback content")

    with client:
        response = client.get("/api/documents")
        assert response.status_code == 200
        items = response.json()["items"]
        assert [(item["path"], item["title"]) for item in items] == [
            ("notes/diagram.md", "Actual title"),
            ("other.md", "other"),
        ]

        document = client.get(f"/api/documents/{items[0]['id']}")
        assert document.status_code == 200
        assert document.headers["content-type"].startswith("text/markdown")
        assert "```mermaid" in document.text
        assert document.headers["etag"]

        unchanged = client.get(
            f"/api/documents/{items[0]['id']}",
            headers={"If-None-Match": document.headers["etag"]},
        )
        assert unchanged.status_code == 304

        assert client.get("/api/documents/not-valid!").status_code == 404


def test_message_annotations_are_persistent_editable_and_deletable(tmp_path):
    with make_client(tmp_path) as client:
        path = f"/api/sessions/codex_2/{SESSION_ID}/annotations"
        created = client.post(
            path,
            json={
                "message_index": 2,
                "start_line": 1,
                "end_line": 1,
                "selected_text": "Message 1",
                "prefix": "",
                "suffix": "",
                "note": "  Ask why this matters.  ",
            },
        )

        assert created.status_code == 201
        annotation = created.json()
        assert annotation["target_type"] == "message"
        assert annotation["message_index"] == 2
        assert annotation["note"] == "Ask why this matters."
        assert len(annotation["content_hash"]) == 64
        assert client.get(path).json()["items"] == [annotation]

        edited = client.patch(
            f"/api/annotations/{annotation['id']}",
            json={"note": "A better reminder"},
        )
        assert edited.status_code == 200
        assert edited.json()["note"] == "A better reminder"

        removed = client.delete(f"/api/annotations/{annotation['id']}")
        assert removed.status_code == 204
        assert client.get(path).json()["items"] == []

        invalid_range = client.post(
            path,
            json={
                "message_index": 2,
                "start_line": 2,
                "end_line": 1,
                "selected_text": "Message 1",
                "note": "Invalid range",
            },
        )
        assert invalid_range.status_code == 422


def test_document_annotations_keep_document_identity_and_validate_lines(tmp_path):
    client = make_client(tmp_path)
    document_path = tmp_path / "documents" / "notes.md"
    document_path.write_text("# Notes\n\nA useful sentence.\n")

    with client:
        document = client.get("/api/documents").json()["items"][0]
        path = f"/api/documents/{document['id']}/annotations"
        created = client.post(
            path,
            json={
                "start_line": 3,
                "end_line": 3,
                "selected_text": "useful sentence",
                "prefix": "A ",
                "suffix": ".",
                "note": "Reuse this later",
            },
        )

        assert created.status_code == 201
        assert created.json()["document_path"] == "notes.md"
        assert client.get(path).json()["items"][0]["note"] == "Reuse this later"

        invalid = client.post(
            path,
            json={
                "start_line": 30,
                "end_line": 30,
                "selected_text": "missing",
                "note": "Impossible line",
            },
        )
        assert invalid.status_code == 400
