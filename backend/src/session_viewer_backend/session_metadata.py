import json
import os
from pathlib import Path
from uuid import uuid4

from .formatting import normalized_title


class SessionMetadataError(ValueError):
    pass


def load_metadata_document(path: Path):
    try:
        with path.open(encoding="utf-8") as source:
            parsed = json.load(source)
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise SessionMetadataError(f"Cannot read session metadata {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SessionMetadataError(f"Invalid session metadata {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise SessionMetadataError(f"{path} must contain an object keyed by session ID")
    for session_id, metadata in parsed.items():
        if not isinstance(session_id, str) or not isinstance(metadata, dict):
            raise SessionMetadataError(
                f"{path} must map every session ID to a metadata object"
            )
        title = metadata.get("title")
        if title is not None and not isinstance(title, str):
            raise SessionMetadataError(f"Session {session_id!r} has a non-string title")
        hidden = metadata.get("hidden")
        if hidden is not None and not isinstance(hidden, bool):
            raise SessionMetadataError(
                f"Session {session_id!r} has a non-boolean hidden flag"
            )
    return parsed


def load_session_metadata(path: Path):
    return {
        session_id.lower(): normalized_title(metadata["title"], width=200)
        for session_id, metadata in load_metadata_document(path).items()
        if isinstance(metadata.get("title"), str)
    }


def load_hidden_session_ids(path: Path):
    return {
        session_id.lower()
        for session_id, metadata in load_metadata_document(path).items()
        if metadata.get("hidden") is True
    }


def save_session_metadata_value(
    path: Path, session_id: str, key: str, value: str | bool | None
):
    metadata = load_metadata_document(path)
    normalized_id = session_id.lower()
    if value is None:
        values = metadata.get(normalized_id)
        if values is not None:
            values.pop(key, None)
            if not values:
                metadata.pop(normalized_id)
    else:
        metadata.setdefault(normalized_id, {})[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as error:
        raise SessionMetadataError(f"Cannot write session metadata {path}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


def save_session_title(path: Path, session_id: str, title: str | None):
    save_session_metadata_value(path, session_id, "title", title)


def save_session_hidden(path: Path, session_id: str, hidden: bool):
    save_session_metadata_value(path, session_id, "hidden", True if hidden else None)
