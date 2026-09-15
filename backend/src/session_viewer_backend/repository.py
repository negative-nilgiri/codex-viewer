from contextlib import closing
from pathlib import Path

from .database import connect, initialize


def row_dict(row):
    if row is None:
        return None
    result = dict(row)
    if "source_present" in result:
        result["source_present"] = bool(result["source_present"])
    if "last_synced_at" in result:
        result["indexed"] = result["last_synced_at"] is not None
    if "title_overridden" in result:
        result["title_overridden"] = bool(result["title_overridden"])
    return result


def list_sessions(database_path: Path, limit=100):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT profile, session_id, COALESCE(title_override, title) AS title,
                   title_override IS NOT NULL AS title_overridden,
                   workspace, created_at,
                   last_activity_at, message_count, last_synced_at,
                   source_present, last_discovered_at
            FROM sessions
            ORDER BY COALESCE(last_activity_at, created_at, '') DESC,
                     profile, session_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_dict(row) for row in rows]


def get_session(database_path: Path, profile: str, session_id: str):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT profile, session_id, COALESCE(title_override, title) AS title,
                   title_override IS NOT NULL AS title_overridden,
                   workspace, created_at,
                   last_activity_at, message_count, last_synced_at, sync_error,
                   source_present, last_discovered_at
            FROM sessions WHERE profile = ? AND session_id = ?
            """,
            (profile, session_id),
        ).fetchone()
    return row_dict(row)


def update_session_title(database_path: Path, session_id: str, title: str | None):
    """Apply the UUID-scoped title override to every indexed source copy."""
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        with connection:
            connection.execute(
                "UPDATE sessions SET title_override = ? WHERE session_id = ?",
                (title, session_id),
            )


def get_messages(database_path: Path, profile: str, session_id: str, start: int, limit: int):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        session = connection.execute(
            "SELECT message_count FROM sessions WHERE profile = ? AND session_id = ?",
            (profile, session_id),
        ).fetchone()
        if session is None:
            return None
        rows = connection.execute(
            """
            SELECT message_index, role, timestamp, markdown
            FROM messages
            WHERE profile = ? AND session_id = ? AND message_index > ?
            ORDER BY message_index
            LIMIT ?
            """,
            (profile, session_id, start, limit),
        ).fetchall()
    return {
        "start": start,
        "limit": limit,
        "total": session["message_count"],
        "items": [dict(row) for row in rows],
    }


def search_messages(database_path: Path, profile: str, session_id: str, query: str):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        session = connection.execute(
            "SELECT 1 FROM sessions WHERE profile = ? AND session_id = ?",
            (profile, session_id),
        ).fetchone()
        if session is None:
            return None
        rows = connection.execute(
            """
            SELECT message_index
            FROM messages
            WHERE profile = ? AND session_id = ?
              AND instr(lower(markdown), lower(?)) > 0
            ORDER BY message_index
            """,
            (profile, session_id, query),
        ).fetchall()
    indexes = [row["message_index"] for row in rows]
    return {"query": query, "total": len(indexes), "message_indexes": indexes}
