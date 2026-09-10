import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = 1
SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


class BookmarkBackupError(ValueError):
    pass


def backup_path(directory: Path, session_id: str) -> Path:
    if not SAFE_SESSION_ID.fullmatch(session_id) or session_id in {".", ".."}:
        raise BookmarkBackupError("Session ID cannot be used as a backup filename")
    return directory / f"{session_id}.json"


def save_backup(
    directory: Path,
    profile: str,
    session_id: str,
    session_title: str,
    bookmarks: list[dict],
):
    target = backup_path(directory, session_id)
    directory.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "session_id": session_id,
        "session_title": session_title,
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "bookmarks": sorted(bookmarks, key=lambda item: item["message_index"]),
    }
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot


def load_backup(directory: Path, profile: str, session_id: str):
    target = backup_path(directory, session_id)
    if not target.exists():
        return None
    try:
        snapshot = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BookmarkBackupError(
            f"Bookmark backup is unreadable: {target.name}"
        ) from error

    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise BookmarkBackupError("Bookmark backup has an unsupported schema")
    if snapshot.get("profile") != profile or snapshot.get("session_id") != session_id:
        raise BookmarkBackupError("Bookmark backup belongs to another session")
    return snapshot
