import hashlib
import json
import os
import re
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .database import connect, initialize


ARCHIVE_SCHEMA = "session-viewer-archive"
ARCHIVE_SCHEMA_VERSION = 1
SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*$")


class ArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveResult:
    profile: str
    session_id: str
    path: str
    message_count: int
    exported_at: str
    sha256: str

    def as_dict(self):
        return asdict(self)


def encoded_line(record: dict):
    return (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def archive_path(root: Path, session_id: str):
    if not SAFE_SESSION_ID.fullmatch(session_id):
        raise ArchiveError(f"Session ID {session_id!r} cannot be used as an archive name")
    return root / f"{session_id}.jsonl"


def export_archive(
    database_path: Path,
    archives_path: Path,
    profile: str,
    session_id: str,
    origin_adapter: str,
):
    """Atomically export the currently indexed conversation into stable JSONL."""
    initialize(database_path)
    exported_at = datetime.now(timezone.utc).isoformat()
    destination = archive_path(archives_path, session_id)
    archives_path.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with closing(connect(database_path)) as connection:
            connection.execute("BEGIN")
            session = connection.execute(
                """
                SELECT COALESCE(title_override, title) AS title, workspace,
                       created_at, message_count
                FROM sessions
                WHERE profile = ? AND session_id = ? AND last_synced_at IS NOT NULL
                """,
                (profile, session_id),
            ).fetchone()
            if session is None:
                raise ArchiveError("Session is not indexed; synchronize it before archiving")

            messages = connection.execute(
                """
                SELECT message_index, role, timestamp, markdown
                FROM messages
                WHERE profile = ? AND session_id = ?
                ORDER BY message_index
                """,
                (profile, session_id),
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".tmp", dir=archives_path
            )
            temporary = Path(temporary_name)
            checksum = hashlib.sha256()
            written_messages = 0
            with os.fdopen(descriptor, "wb") as output:
                header = {
                    "type": "session",
                    "schema": ARCHIVE_SCHEMA,
                    "schema_version": ARCHIVE_SCHEMA_VERSION,
                    "session_id": session_id,
                    "title": session["title"],
                    "workspace": session["workspace"],
                    "created_at": session["created_at"],
                    "origin": {"source": profile, "adapter": origin_adapter},
                }
                raw = encoded_line(header)
                output.write(raw)
                checksum.update(raw)

                for message in messages:
                    written_messages += 1
                    record = {
                        "type": "message",
                        "message_index": message["message_index"],
                        "role": message["role"],
                        "timestamp": message["timestamp"],
                        "markdown": message["markdown"],
                    }
                    raw = encoded_line(record)
                    output.write(raw)
                    checksum.update(raw)

                if written_messages != session["message_count"]:
                    raise ArchiveError(
                        "Session changed while it was being archived; retry the export"
                    )
                digest = checksum.hexdigest()
                output.write(
                    encoded_line(
                        {
                            "type": "end",
                            "message_count": written_messages,
                            "exported_at": exported_at,
                            "sha256": digest,
                        }
                    )
                )
                output.flush()
                os.fsync(output.fileno())
            connection.rollback()

        os.replace(temporary, destination)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise

    return ArchiveResult(
        profile=profile,
        session_id=session_id,
        path=str(destination),
        message_count=written_messages,
        exported_at=exported_at,
        sha256=digest,
    )
