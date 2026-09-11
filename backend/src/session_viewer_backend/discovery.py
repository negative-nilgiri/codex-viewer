import json
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .adapters import get_adapter
from .database import connect, initialize
from .formatting import normalized_title
from .rollout import RolloutError, read_prefix_events
from .sources import SourceDefinition, select_sources


DISCOVERY_PREFIX_LIMIT = 256 * 1024


@dataclass(frozen=True)
class DiscoveredSession:
    source_id: str
    session_id: str
    transcript_path: Path
    title: str
    workspace: str | None
    created_at: str | None
    approximate_activity_at: str


@dataclass(frozen=True)
class DiscoveryResult:
    sources: tuple[str, ...]
    found: int
    added: int
    refreshed: int
    unavailable: int

    def as_dict(self):
        result = asdict(self)
        result["sources"] = list(self.sources)
        return result


def load_session_metadata(path: Path):
    try:
        with path.open() as source:
            parsed = json.load(source)
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ValueError(f"Cannot read session metadata {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid session metadata {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain an object keyed by session ID")

    titles = {}
    for session_id, metadata in parsed.items():
        if not isinstance(session_id, str) or not isinstance(metadata, dict):
            raise ValueError(
                f"{path} must map every session ID to a metadata object"
            )
        title = metadata.get("title")
        if title is not None and not isinstance(title, str):
            raise ValueError(f"Session {session_id!r} has a non-string title")
        if isinstance(title, str):
            titles[session_id.lower()] = normalized_title(title, width=200)
    return titles


def inspect_transcript(source: SourceDefinition, path: Path):
    adapter = get_adapter(source.adapter)
    if not adapter.accepts_path(path):
        return None
    events = read_prefix_events(path, DISCOVERY_PREFIX_LIMIT)
    if not events:
        return None
    inspected = adapter.inspect(path, events)
    if inspected is None:
        return None
    stat = path.stat()
    return DiscoveredSession(
        source_id=source.id,
        session_id=inspected.session_id,
        transcript_path=path,
        title=normalized_title(inspected.title),
        workspace=inspected.workspace,
        created_at=inspected.created_at,
        approximate_activity_at=datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    )


def scan_source(source: SourceDefinition):
    if not source.path.is_dir():
        raise RolloutError(f"Session source does not exist: {source.path}")
    discovered: dict[str, DiscoveredSession] = {}
    for path in sorted(source.path.rglob("*.jsonl")):
        inspected = inspect_transcript(source, path)
        if inspected is None:
            continue
        current = discovered.get(inspected.session_id)
        if (
            current is None
            or current.transcript_path.stat().st_mtime_ns < path.stat().st_mtime_ns
        ):
            discovered[inspected.session_id] = inspected
    return tuple(discovered.values())


def find_transcript(source: SourceDefinition, requested_id: str):
    requested = requested_id.lower()
    matches = [
        item for item in scan_source(source) if item.session_id.startswith(requested)
    ]
    matches.sort(key=lambda item: (item.session_id, str(item.transcript_path)))
    if not matches:
        raise RolloutError(
            f"No session in {source.id} has an ID starting with {requested_id!r}"
        )
    if len(matches) > 1:
        descriptions = ", ".join(
            f"{item.session_id} ({item.transcript_path.name})" for item in matches[:8]
        )
        raise RolloutError(
            f"Session prefix {requested_id!r} is ambiguous: {descriptions}"
        )
    return matches[0]


def discover_sessions(
    database_path: Path,
    sources: tuple[SourceDefinition, ...],
    requested_source: str | None = None,
    session_metadata_path: Path | None = None,
):
    initialize(database_path)
    selected_sources = select_sources(sources, requested_source)
    title_overrides = (
        load_session_metadata(session_metadata_path)
        if session_metadata_path is not None
        else {}
    )
    with closing(connect(database_path)) as connection:
        existing_rows = connection.execute(
            "SELECT profile, session_id, last_synced_at FROM sessions"
        ).fetchall()
    existing = {
        (row["profile"], row["session_id"]): row["last_synced_at"]
        for row in existing_rows
    }

    discovered: dict[tuple[str, str], DiscoveredSession] = {}
    for source in selected_sources:
        for item in scan_source(source):
            discovered[(item.source_id, item.session_id)] = item

    discovered_at = datetime.now(timezone.utc).isoformat()
    added = 0
    refreshed = 0
    with closing(connect(database_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for source in selected_sources:
                connection.execute(
                    "UPDATE sessions SET source_present = 0 WHERE profile = ?",
                    (source.id,),
                )
            # A transcript path may already belong to the wrong session after an
            # older/broken discovery pass. Move that stale association aside before
            # restoring every path to the identity found inside the transcript.
            # The row (and any indexed messages attached to it) is deliberately
            # preserved: its own transcript may be rediscovered later in this pass.
            for item in discovered.values():
                path_owner = connection.execute(
                    """
                    SELECT session_id FROM sessions
                    WHERE profile = ? AND rollout_path = ?
                    """,
                    (item.source_id, str(item.transcript_path)),
                ).fetchone()
                if (
                    path_owner is not None
                    and path_owner["session_id"] != item.session_id
                ):
                    stale_path = (
                        f"stale://{item.source_id}/"
                        f"{path_owner['session_id']}/{discovered_at}"
                    )
                    connection.execute(
                        """
                        UPDATE sessions SET rollout_path = ?
                        WHERE profile = ? AND session_id = ?
                        """,
                        (stale_path, item.source_id, path_owner["session_id"]),
                    )
            for item in discovered.values():
                key = (item.source_id, item.session_id)
                override = title_overrides.get(item.session_id)
                if key in existing:
                    refreshed += 1
                    connection.execute(
                        """
                        UPDATE sessions
                        SET rollout_path = ?, source_present = 1,
                            last_discovered_at = ?, title_override = ?,
                            title = CASE WHEN last_synced_at IS NULL THEN ? ELSE title END,
                            workspace = CASE WHEN last_synced_at IS NULL THEN ? ELSE workspace END,
                            created_at = CASE WHEN last_synced_at IS NULL THEN ? ELSE created_at END,
                            last_activity_at = CASE
                                WHEN last_synced_at IS NULL THEN ? ELSE last_activity_at END
                        WHERE profile = ? AND session_id = ?
                        """,
                        (
                            str(item.transcript_path),
                            discovered_at,
                            override,
                            item.title,
                            item.workspace,
                            item.created_at,
                            item.approximate_activity_at,
                            item.source_id,
                            item.session_id,
                        ),
                    )
                else:
                    added += 1
                    connection.execute(
                        """
                        INSERT INTO sessions(
                            profile, session_id, rollout_path, title, workspace,
                            created_at, last_activity_at, title_override, source_present,
                            last_discovered_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                        """,
                        (
                            item.source_id,
                            item.session_id,
                            str(item.transcript_path),
                            item.title,
                            item.workspace,
                            item.created_at,
                            item.approximate_activity_at,
                            override,
                            discovered_at,
                        ),
                    )
            for source in selected_sources:
                rows = connection.execute(
                    "SELECT session_id FROM sessions WHERE profile = ?",
                    (source.id,),
                ).fetchall()
                for row in rows:
                    connection.execute(
                        "UPDATE sessions SET title_override = ? "
                        "WHERE profile = ? AND session_id = ?",
                        (
                            title_overrides.get(row["session_id"]),
                            source.id,
                            row["session_id"],
                        ),
                    )
                connection.execute(
                    """
                    DELETE FROM sessions
                    WHERE profile = ? AND rollout_path LIKE 'stale://%'
                      AND message_count = 0 AND last_synced_at IS NULL
                      AND source_present = 0
                    """,
                    (source.id,),
                )
            source_ids = [source.id for source in selected_sources]
            placeholders = ",".join("?" for _ in source_ids)
            unavailable = connection.execute(
                f"SELECT COUNT(*) AS count FROM sessions "
                f"WHERE profile IN ({placeholders}) AND source_present = 0",
                source_ids,
            ).fetchone()["count"]
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return DiscoveryResult(
        sources=tuple(source.id for source in selected_sources),
        found=len(discovered),
        added=added,
        refreshed=refreshed,
        unavailable=unavailable,
    )
