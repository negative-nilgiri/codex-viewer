from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adapters import get_adapter
from .database import connect, initialize
from .discovery import find_transcript, load_session_metadata
from .formatting import normalized_title
from .rollout import RolloutError, iter_complete_lines
from .sources import SourceDefinition, select_sources


@dataclass(frozen=True)
class SyncResult:
    profile: str
    session_id: str
    added_messages: int
    message_count: int
    last_complete_offset: int
    up_to_date: bool
    rebuilt: bool


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


def earlier_timestamp(current, candidate):
    current_parsed = parsed_timestamp(current)
    candidate_parsed = parsed_timestamp(candidate)
    if candidate_parsed is None:
        return current
    if current_parsed is None or candidate_parsed < current_parsed:
        return candidate
    return current


def resolve_transcript(
    database_path: Path,
    source: SourceDefinition,
    requested_id: str,
):
    requested = requested_id.lower()
    with closing(connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT session_id, rollout_path FROM sessions WHERE profile = ?",
            (source.id,),
        ).fetchall()
    matches = [row for row in rows if row["session_id"].startswith(requested)]
    if len(matches) > 1:
        descriptions = ", ".join(row["session_id"] for row in matches[:8])
        raise RolloutError(
            f"Session prefix {requested_id!r} is ambiguous: {descriptions}"
        )
    if len(matches) == 1:
        path = Path(matches[0]["rollout_path"])
        if path.is_file():
            return matches[0]["session_id"], path

    discovered = find_transcript(source, requested_id)
    return discovered.session_id, discovered.transcript_path


def sync_session(
    database_path: Path,
    sources: tuple[SourceDefinition, ...],
    source_id: str,
    requested_id: str,
    session_metadata_path: Path | None = None,
):
    initialize(database_path)
    source = select_sources(sources, source_id)[0]
    adapter = get_adapter(source.adapter)
    session_id, transcript_path = resolve_transcript(
        database_path, source, requested_id
    )
    initial_stat = transcript_path.stat()
    title_overrides = (
        load_session_metadata(session_metadata_path)
        if session_metadata_path is not None
        else {}
    )

    with closing(connect(database_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                "SELECT * FROM sessions WHERE profile = ? AND session_id = ?",
                (source.id, session_id),
            ).fetchone()
            rebuilt = False
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO sessions(
                        profile, session_id, rollout_path, title_override
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        source.id,
                        session_id,
                        str(transcript_path),
                        title_overrides.get(session_id),
                    ),
                )
                offset = 0
                message_count = 0
                title = "Untitled session"
                workspace = None
                created_at = None
                last_activity_at = None
            else:
                replaced = (
                    existing["rollout_path"] != str(transcript_path)
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
                        (source.id, session_id),
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
            for parsed_line in iter_complete_lines(transcript_path, offset):
                complete_offset = parsed_line.end
                event = parsed_line.event
                if event is None:
                    continue
                last_activity_at = later_timestamp(
                    last_activity_at, adapter.event_timestamp(event)
                )
                metadata = adapter.event_metadata(event)
                if metadata.session_id and metadata.session_id != session_id:
                    if adapter.name != "codex":
                        raise ValueError(
                            f"Transcript record ID {metadata.session_id} does not match "
                            f"{session_id}"
                        )
                else:
                    if metadata.workspace:
                        workspace = metadata.workspace
                    if metadata.created_at:
                        created_at = earlier_timestamp(created_at, metadata.created_at)
                    if metadata.title:
                        title = normalized_title(metadata.title)

                message = adapter.visible_message(event)
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
                        source.id,
                        session_id,
                        message_count,
                        role,
                        timestamp,
                        markdown,
                        parsed_line.start,
                    ),
                )

            final_stat = transcript_path.stat()
            synced_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE sessions
                SET rollout_path = ?, title = ?, workspace = ?, created_at = ?,
                    last_activity_at = ?, last_complete_offset = ?, source_size = ?,
                    source_mtime_ns = ?, source_device = ?, source_inode = ?,
                    message_count = ?, last_synced_at = ?, sync_error = NULL,
                    title_override = ?, source_present = 1, last_discovered_at = ?
                WHERE profile = ? AND session_id = ?
                """,
                (
                    str(transcript_path),
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
                    title_overrides.get(session_id),
                    synced_at,
                    source.id,
                    session_id,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return SyncResult(
        profile=source.id,
        session_id=session_id,
        added_messages=added_messages,
        message_count=message_count,
        last_complete_offset=complete_offset,
        up_to_date=added_messages == 0 and not rebuilt,
        rebuilt=rebuilt,
    )
