import json
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .database import connect, initialize
from .rollout import (
    PROFILE_RE,
    RolloutError,
    profile_directory,
    session_id_from_path,
    session_metadata,
    visible_message,
)
from .sync import normalized_title


DISCOVERY_PREFIX_LIMIT = 256 * 1024


@dataclass(frozen=True)
class DiscoveredRollout:
    profile: str
    session_id: str
    rollout_path: Path
    title: str
    workspace: str | None
    created_at: str | None
    approximate_activity_at: str


@dataclass(frozen=True)
class DiscoveryResult:
    profiles: tuple[str, ...]
    found: int
    added: int
    refreshed: int
    unavailable: int

    def as_dict(self):
        result = asdict(self)
        result["profiles"] = list(self.profiles)
        return result


def profile_names(sessions_root: Path, requested_profile: str | None):
    if requested_profile is not None:
        profile_directory(sessions_root, requested_profile)
        return [requested_profile]
    if not sessions_root.is_dir():
        raise RolloutError(f"Sessions root does not exist: {sessions_root}")
    return sorted(
        path.name
        for path in sessions_root.iterdir()
        if path.is_dir() and PROFILE_RE.fullmatch(path.name)
    )


def load_title_overrides(path: Path | None):
    if path is None or not path.exists():
        return {}
    with path.open() as source:
        parsed = json.load(source)
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in parsed.items()
    ):
        raise ValueError(
            f"{path} must contain a JSON object mapping session IDs to titles"
        )
    return {
        session_id.lower(): normalized_title(title, width=200)
        for session_id, title in parsed.items()
    }


def inspect_prefix(path: Path, expected_id: str):
    title = f"Session {expected_id[:8]}"
    workspace = None
    created_at = None
    consumed = 0
    with path.open("rb") as source:
        while consumed < DISCOVERY_PREFIX_LIMIT:
            remaining = DISCOVERY_PREFIX_LIMIT - consumed
            raw = source.readline(remaining + 1)
            if not raw or len(raw) > remaining or not raw.endswith(b"\n"):
                break
            consumed += len(raw)
            try:
                event = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            metadata = session_metadata(event)
            if metadata is not None:
                recorded_id = metadata.get("id") or metadata.get("session_id")
                if recorded_id and str(recorded_id).lower() != expected_id:
                    continue
                created_at = str(metadata.get("timestamp") or created_at or "") or None
                cwd = metadata.get("cwd")
                if cwd:
                    workspace = Path(str(cwd)).name
            message = visible_message(event)
            if message is not None and message[0] == "user":
                title = normalized_title(message[1])
                break
    return title, workspace, created_at


def discover_sessions(
    database_path: Path,
    sessions_root: Path,
    requested_profile: str | None = None,
    titles_path: Path | None = None,
):
    initialize(database_path)
    profiles = profile_names(sessions_root, requested_profile)
    title_overrides = load_title_overrides(titles_path)
    with closing(connect(database_path)) as connection:
        existing_rows = connection.execute(
            "SELECT profile, session_id, last_synced_at FROM sessions"
        ).fetchall()
    existing = {
        (row["profile"], row["session_id"]): row["last_synced_at"]
        for row in existing_rows
    }

    discovered: dict[tuple[str, str], DiscoveredRollout] = {}
    for profile in profiles:
        directory = profile_directory(sessions_root, profile)
        for path in directory.rglob("*.jsonl"):
            session_id = session_id_from_path(path)
            if session_id is None:
                continue
            stat = path.stat()
            key = (profile, session_id)
            current = discovered.get(key)
            if current is not None and current.rollout_path.stat().st_mtime_ns >= stat.st_mtime_ns:
                continue
            if existing.get(key) is None:
                title, workspace, created_at = inspect_prefix(path, session_id)
            else:
                title = f"Session {session_id[:8]}"
                workspace = None
                created_at = None
            discovered[key] = DiscoveredRollout(
                profile=profile,
                session_id=session_id,
                rollout_path=path,
                title=title,
                workspace=workspace,
                created_at=created_at,
                approximate_activity_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            )

    discovered_at = datetime.now(timezone.utc).isoformat()
    added = 0
    refreshed = 0
    with closing(connect(database_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for profile in profiles:
                connection.execute(
                    "UPDATE sessions SET source_present = 0 WHERE profile = ?",
                    (profile,),
                )
            for item in discovered.values():
                key = (item.profile, item.session_id)
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
                            str(item.rollout_path),
                            discovered_at,
                            title_overrides.get(item.session_id),
                            item.title,
                            item.workspace,
                            item.created_at,
                            item.approximate_activity_at,
                            item.profile,
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
                            item.profile,
                            item.session_id,
                            str(item.rollout_path),
                            item.title,
                            item.workspace,
                            item.created_at,
                            item.approximate_activity_at,
                            title_overrides.get(item.session_id),
                            discovered_at,
                        ),
                    )
            for profile in profiles:
                rows = connection.execute(
                    "SELECT session_id FROM sessions WHERE profile = ?",
                    (profile,),
                ).fetchall()
                for row in rows:
                    connection.execute(
                        "UPDATE sessions SET title_override = ? "
                        "WHERE profile = ? AND session_id = ?",
                        (
                            title_overrides.get(row["session_id"]),
                            profile,
                            row["session_id"],
                        ),
                    )
            placeholders = ",".join("?" for _ in profiles)
            unavailable = connection.execute(
                f"SELECT COUNT(*) AS count FROM sessions "
                f"WHERE profile IN ({placeholders}) AND source_present = 0",
                profiles,
            ).fetchone()["count"]
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return DiscoveryResult(
        profiles=tuple(profiles),
        found=len(discovered),
        added=added,
        refreshed=refreshed,
        unavailable=unavailable,
    )
