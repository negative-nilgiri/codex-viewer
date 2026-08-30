import re
import sqlite3
import textwrap
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .database import connect, initialize
from .rollout import find_rollout, iter_complete_lines, session_metadata, visible_message


@dataclass(frozen=True)
class SyncResult:
    profile: str
    session_id: str
    added_messages: int
    message_count: int
    last_complete_offset: int
    up_to_date: bool
    rebuilt: bool


def normalized_title(markdown: str, width=100):
    value = " ".join(markdown.split())
    value = re.sub(r"^#+\s*", "", value)
    return textwrap.shorten(value, width=width, placeholder="…") or "Untitled session"


def parsed_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def later_timestamp(current, candidate):
    current_parsed = parsed_timestamp(current)
    candidate_parsed = parsed_timestamp(candidate)
    if candidate_parsed is None:
        return current
    if current_parsed is None or candidate_parsed > current_parsed:
        return candidate
    return current


def sync_session(
    database_path: Path,
    sessions_root: Path,
    profile: str,
    requested_id: str,
):
    initialize(database_path)
    session_id, rollout_path = find_rollout(sessions_root, profile, requested_id)
    initial_stat = rollout_path.stat()

    with closing(connect(database_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                "SELECT * FROM sessions WHERE profile = ? AND session_id = ?",
                (profile, session_id),
            ).fetchone()
            rebuilt = False
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO sessions(profile, session_id, rollout_path)
                    VALUES (?, ?, ?)
                    """,
                    (profile, session_id, str(rollout_path)),
                )
                offset = 0
                message_count = 0
                title = "Untitled session"
                workspace = None
                created_at = None
                last_activity_at = None
            else:
                replaced = (
                    existing["rollout_path"] != str(rollout_path)
                    or initial_stat.st_size < existing["last_complete_offset"]
                    or (
                        existing["source_inode"] is not None
                        and (
                            existing["source_inode"] != initial_stat.st_ino
                            or existing["source_device"] != initial_stat.st_dev
                        )
                    )
                )
                if replaced:
                    connection.execute(
                        "DELETE FROM messages WHERE profile = ? AND session_id = ?",
                        (profile, session_id),
                    )
                    offset = 0
                    message_count = 0
                    title = "Untitled session"
                    workspace = None
                    created_at = None
                    last_activity_at = None
                    rebuilt = True
                else:
                    offset = existing["last_complete_offset"]
                    message_count = existing["message_count"]
                    title = existing["title"]
                    workspace = existing["workspace"]
                    created_at = existing["created_at"]
                    last_activity_at = existing["last_activity_at"]

            complete_offset = offset
            added_messages = 0
            for parsed_line in iter_complete_lines(rollout_path, offset):
                complete_offset = parsed_line.end
                event = parsed_line.event
                if event is None:
                    continue
                last_activity_at = later_timestamp(
                    last_activity_at, event.get("timestamp")
                )
                metadata = session_metadata(event)
                if metadata is not None:
                    recorded_id = metadata.get("id") or metadata.get("session_id")
                    if recorded_id and str(recorded_id).lower() != session_id:
                        raise ValueError(
                            f"Rollout metadata ID {recorded_id} does not match {session_id}"
                        )
                    created_at = str(metadata.get("timestamp") or created_at or "") or None
                    cwd = metadata.get("cwd")
                    if cwd:
                        workspace = Path(str(cwd)).name
                message = visible_message(event)
                if message is None:
                    continue
                role, markdown, timestamp = message
                message_count += 1
                added_messages += 1
                if title == "Untitled session" and role == "user":
                    title = normalized_title(markdown)
                connection.execute(
                    """
                    INSERT INTO messages(
                        profile, session_id, message_index, role, timestamp,
                        markdown, source_offset
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile,
                        session_id,
                        message_count,
                        role,
                        timestamp,
                        markdown,
                        parsed_line.start,
                    ),
                )

            final_stat = rollout_path.stat()
            synced_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE sessions
                SET rollout_path = ?, title = ?, workspace = ?, created_at = ?,
                    last_activity_at = ?, last_complete_offset = ?, source_size = ?,
                    source_mtime_ns = ?, source_device = ?, source_inode = ?,
                    message_count = ?, last_synced_at = ?, sync_error = NULL,
                    source_present = 1, last_discovered_at = ?
                WHERE profile = ? AND session_id = ?
                """,
                (
                    str(rollout_path),
                    title,
                    workspace,
                    created_at,
                    last_activity_at,
                    complete_offset,
                    final_stat.st_size,
                    final_stat.st_mtime_ns,
                    final_stat.st_dev,
                    final_stat.st_ino,
                    message_count,
                    synced_at,
                    synced_at,
                    profile,
                    session_id,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return SyncResult(
        profile=profile,
        session_id=session_id,
        added_messages=added_messages,
        message_count=message_count,
        last_complete_offset=complete_offset,
        up_to_date=added_messages == 0 and not rebuilt,
        rebuilt=rebuilt,
    )
