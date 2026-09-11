import hashlib
import json
from pathlib import Path

from ..archive import ARCHIVE_SCHEMA, ARCHIVE_SCHEMA_VERSION
from ..rollout import RolloutError
from .base import EventMetadata, SessionInspection


class ArchiveAdapter:
    name = "archive"

    def accepts_path(self, path: Path):
        return path.name.endswith(".jsonl")

    def inspect(self, path: Path, events: list[dict]):
        if not self.accepts_path(path) or not events:
            return None
        header = events[0]
        if not self._is_header(header):
            return None
        session_id = header.get("session_id")
        title = header.get("title")
        if not isinstance(session_id, str) or not session_id:
            return None
        return SessionInspection(
            session_id=session_id.lower(),
            title=title if isinstance(title, str) and title else f"Session {session_id[:8]}",
            workspace=(
                header.get("workspace")
                if isinstance(header.get("workspace"), str)
                else None
            ),
            created_at=(
                header.get("created_at")
                if isinstance(header.get("created_at"), str)
                else None
            ),
        )

    def validate(self, path: Path):
        """Verify structure, ordering, completeness, and the integrity footer."""
        checksum = hashlib.sha256()
        header_seen = False
        footer_seen = False
        message_count = 0
        with path.open("rb") as source:
            for line_number, raw in enumerate(source, start=1):
                if not raw.endswith(b"\n"):
                    raise RolloutError(
                        f"Archive {path} has an incomplete line {line_number}"
                    )
                try:
                    record = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise RolloutError(
                        f"Archive {path} has invalid JSON on line {line_number}: {error}"
                    ) from error
                if not isinstance(record, dict):
                    raise RolloutError(
                        f"Archive {path} line {line_number} is not an object"
                    )

                kind = record.get("type")
                if kind == "session" and line_number == 1 and self._is_header(record):
                    header_seen = True
                    checksum.update(raw)
                elif kind == "message" and header_seen and not footer_seen:
                    message_count += 1
                    if record.get("message_index") != message_count:
                        raise RolloutError(
                            f"Archive {path} has an invalid message index on line {line_number}"
                        )
                    if record.get("role") not in {"user", "assistant"}:
                        raise RolloutError(
                            f"Archive {path} has an invalid role on line {line_number}"
                        )
                    if not isinstance(record.get("markdown"), str):
                        raise RolloutError(
                            f"Archive {path} has non-text Markdown on line {line_number}"
                        )
                    checksum.update(raw)
                elif kind == "end" and header_seen and not footer_seen:
                    footer_seen = True
                    if record.get("message_count") != message_count:
                        raise RolloutError(f"Archive {path} message count does not match")
                    if record.get("sha256") != checksum.hexdigest():
                        raise RolloutError(f"Archive {path} checksum does not match")
                else:
                    raise RolloutError(
                        f"Archive {path} has an unexpected record on line {line_number}"
                    )
        if not header_seen or not footer_seen:
            raise RolloutError(f"Archive {path} is incomplete")

    def event_metadata(self, event: dict):
        if not self._is_header(event):
            return EventMetadata()
        session_id = event.get("session_id")
        return EventMetadata(
            session_id=session_id.lower() if isinstance(session_id, str) else None,
            title=event.get("title") if isinstance(event.get("title"), str) else None,
            workspace=(
                event.get("workspace") if isinstance(event.get("workspace"), str) else None
            ),
            created_at=(
                event.get("created_at") if isinstance(event.get("created_at"), str) else None
            ),
        )

    def event_timestamp(self, event: dict):
        if event.get("type") == "message" and isinstance(event.get("timestamp"), str):
            return event["timestamp"]
        if self._is_header(event) and isinstance(event.get("created_at"), str):
            return event["created_at"]
        return None

    def visible_message(self, event: dict):
        if event.get("type") != "message" or event.get("role") not in {
            "user",
            "assistant",
        }:
            return None
        markdown = event.get("markdown")
        if not isinstance(markdown, str):
            return None
        timestamp = event.get("timestamp")
        return (
            event["role"],
            markdown,
            timestamp if isinstance(timestamp, str) else None,
        )

    @staticmethod
    def _is_header(event: dict):
        return (
            event.get("type") == "session"
            and event.get("schema") == ARCHIVE_SCHEMA
            and event.get("schema_version") == ARCHIVE_SCHEMA_VERSION
        )
