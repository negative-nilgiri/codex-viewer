import json
import re
from dataclasses import dataclass
from pathlib import Path


SESSION_ID_RE = re.compile(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$", re.I)
PROFILE_RE = re.compile(r"codex_[A-Za-z0-9._-]+$")


class RolloutError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedLine:
    start: int
    end: int
    event: dict | None


def session_id_from_path(path: Path):
    match = SESSION_ID_RE.search(path.stem)
    return match.group(1).lower() if match else None


def profile_directory(sessions_root: Path, profile: str):
    if not PROFILE_RE.fullmatch(profile):
        raise RolloutError(f"Invalid Codex profile {profile!r}")
    root = sessions_root.resolve()
    directory = (root / profile).resolve()
    try:
        directory.relative_to(root)
    except ValueError as error:
        raise RolloutError(f"Profile escapes the sessions root: {profile}") from error
    if not directory.is_dir():
        raise RolloutError(f"Session bind mount does not exist: {directory}")
    return directory


def find_rollout(sessions_root: Path, profile: str, requested_id: str):
    directory = profile_directory(sessions_root, profile)
    requested = requested_id.lower()
    matches = []
    for path in directory.rglob("*.jsonl"):
        session_id = session_id_from_path(path)
        if session_id and session_id.startswith(requested):
            matches.append((session_id, path))
    matches.sort(key=lambda item: (item[0], str(item[1])))
    if not matches:
        raise RolloutError(
            f"No rollout in {profile} has a session ID starting with {requested_id!r}"
        )
    if len(matches) > 1:
        descriptions = ", ".join(
            f"{session_id} ({path.name})" for session_id, path in matches[:8]
        )
        raise RolloutError(f"Session prefix {requested_id!r} is ambiguous: {descriptions}")
    return matches[0]


def iter_complete_lines(path: Path, offset: int):
    """Yield decoded complete JSONL records, leaving a partial final line unread."""
    with path.open("rb") as source:
        source.seek(offset)
        while True:
            start = source.tell()
            raw = source.readline()
            if not raw:
                return
            if not raw.endswith(b"\n"):
                return
            end = source.tell()
            if not raw.strip():
                yield ParsedLine(start=start, end=end, event=None)
                continue
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RolloutError(
                    f"Malformed complete JSONL line at byte {start} in {path}: {error}"
                ) from error
            if not isinstance(event, dict):
                raise RolloutError(
                    f"JSONL value at byte {start} in {path} is not an object"
                )
            yield ParsedLine(start=start, end=end, event=event)


def visible_message(event):
    if event.get("type") != "event_msg":
        return None
    payload = event.get("payload") or {}
    kind = payload.get("type")
    if kind == "user_message":
        role = "user"
    elif kind == "agent_message":
        role = "assistant"
    else:
        return None
    markdown = payload.get("message")
    if not isinstance(markdown, str) or not markdown:
        return None
    return role, markdown, event.get("timestamp")


def session_metadata(event):
    if event.get("type") != "session_meta":
        return None
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}
