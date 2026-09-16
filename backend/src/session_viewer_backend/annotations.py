import hashlib
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .database import connect, initialize


class AnnotationError(ValueError):
    pass


def content_hash(markdown: str):
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def validate_lines(markdown: str, start_line: int, end_line: int):
    line_count = max(1, len(markdown.splitlines()))
    if end_line > line_count:
        raise AnnotationError(
            f"Annotation ends on line {end_line}, but the content has {line_count} lines"
        )


def _row_dict(row):
    return None if row is None else dict(row)


def list_session_annotations(database_path: Path, profile: str, session_id: str):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT * FROM annotations
            WHERE target_type = 'message' AND profile = ? AND session_id = ?
            ORDER BY message_index, start_line, id
            """,
            (profile, session_id),
        ).fetchall()
    return [_row_dict(row) for row in rows]


def list_document_annotations(database_path: Path, document_id: str):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT * FROM annotations
            WHERE target_type = 'document' AND document_id = ?
            ORDER BY start_line, id
            """,
            (document_id,),
        ).fetchall()
    return [_row_dict(row) for row in rows]


def get_message_markdown(
    database_path: Path, profile: str, session_id: str, message_index: int
):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT markdown FROM messages
            WHERE profile = ? AND session_id = ? AND message_index = ?
            """,
            (profile, session_id, message_index),
        ).fetchone()
    return None if row is None else row["markdown"]


def create_message_annotation(
    database_path: Path,
    profile: str,
    session_id: str,
    message_index: int,
    start_line: int,
    end_line: int,
    selected_text: str,
    prefix: str,
    suffix: str,
    note: str,
):
    markdown = get_message_markdown(database_path, profile, session_id, message_index)
    if markdown is None:
        raise AnnotationError("Message does not exist")
    validate_lines(markdown, start_line, end_line)
    return _insert_annotation(
        database_path,
        target_type="message",
        profile=profile,
        session_id=session_id,
        message_index=message_index,
        document_id=None,
        document_path=None,
        start_line=start_line,
        end_line=end_line,
        selected_text=selected_text,
        prefix=prefix,
        suffix=suffix,
        source_hash=content_hash(markdown),
        note=note,
    )


def create_document_annotation(
    database_path: Path,
    document_id: str,
    document_path: str,
    markdown: str,
    start_line: int,
    end_line: int,
    selected_text: str,
    prefix: str,
    suffix: str,
    note: str,
):
    validate_lines(markdown, start_line, end_line)
    return _insert_annotation(
        database_path,
        target_type="document",
        profile=None,
        session_id=None,
        message_index=None,
        document_id=document_id,
        document_path=document_path,
        start_line=start_line,
        end_line=end_line,
        selected_text=selected_text,
        prefix=prefix,
        suffix=suffix,
        source_hash=content_hash(markdown),
        note=note,
    )


def _insert_annotation(
    database_path: Path,
    *,
    target_type: str,
    profile: str | None,
    session_id: str | None,
    message_index: int | None,
    document_id: str | None,
    document_path: str | None,
    start_line: int,
    end_line: int,
    selected_text: str,
    prefix: str,
    suffix: str,
    source_hash: str,
    note: str,
):
    initialize(database_path)
    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(database_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO annotations(
                    target_type, profile, session_id, message_index,
                    document_id, document_path, start_line, end_line,
                    selected_text, prefix, suffix, content_hash, note,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_type,
                    profile,
                    session_id,
                    message_index,
                    document_id,
                    document_path,
                    start_line,
                    end_line,
                    selected_text,
                    prefix,
                    suffix,
                    source_hash,
                    note,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM annotations WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
    return _row_dict(row)


def update_annotation_note(database_path: Path, annotation_id: int, note: str):
    initialize(database_path)
    now = datetime.now(timezone.utc).isoformat()
    with closing(connect(database_path)) as connection:
        with connection:
            cursor = connection.execute(
                "UPDATE annotations SET note = ?, updated_at = ? WHERE id = ?",
                (note, now, annotation_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM annotations WHERE id = ?", (annotation_id,)
            ).fetchone()
    return _row_dict(row)


def delete_annotation(database_path: Path, annotation_id: int):
    initialize(database_path)
    with closing(connect(database_path)) as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM annotations WHERE id = ?", (annotation_id,)
            )
    return cursor.rowcount > 0
