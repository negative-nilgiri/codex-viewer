import json

from fastapi.testclient import TestClient

from session_viewer_backend.api import create_app
from session_viewer_backend.config import Settings
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
            "timestamp": f"2026-08-30T08:00:{index:02d}Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": f"Message {index}"},
        }
        for index in range(message_count)
    ]
    rollout.write_text("".join(json.dumps(item) + "\n" for item in events))
    settings = Settings(tmp_path / "viewer.sqlite3", sessions_root)
    sync_session(settings.database_path, settings.sessions_root, "codex_2", SESSION_ID)
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
