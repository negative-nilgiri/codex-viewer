from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from .annotations import (
    AnnotationError,
    create_document_annotation,
    create_message_annotation,
    delete_annotation,
    list_document_annotations,
    list_session_annotations,
    update_annotation_note,
)
from .archive import ArchiveError, export_archive
from .bookmarks import BookmarkBackupError, load_backup, save_backup
from .config import Settings
from .database import initialize
from .discovery import discover_sessions
from .documents import DocumentError, list_documents, load_document
from .repository import (
    get_messages,
    get_session,
    list_sessions,
    search_messages,
    update_session_title,
)
from .rollout import RolloutError
from .session_metadata import (
    SessionMetadataError,
    load_hidden_session_ids,
    save_session_hidden,
    save_session_title,
)
from .sources import SourceConfigurationError, load_sources, select_sources
from .sync import sync_session


class BookmarkItem(BaseModel):
    message_index: int = Field(ge=1)
    title: str = Field(max_length=500)


class BookmarkBackupInput(BaseModel):
    bookmarks: list[BookmarkItem] = Field(max_length=10_000)


class BookmarkBackup(BookmarkBackupInput):
    schema_version: Literal[1]
    profile: str
    session_id: str
    session_title: str
    exported_at: str


class SessionTitleInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SessionVisibilityInput(BaseModel):
    hidden: bool


class AnnotationSelectionInput(BaseModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    selected_text: str = Field(min_length=1, max_length=100_000)
    prefix: str = Field(default="", max_length=500)
    suffix: str = Field(default="", max_length=500)
    note: str = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def valid_line_range(self):
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if not self.selected_text.strip():
            raise ValueError("selected_text cannot be blank")
        return self


class MessageAnnotationInput(AnnotationSelectionInput):
    message_index: int = Field(ge=1)


class AnnotationNoteInput(BaseModel):
    note: str = Field(min_length=1, max_length=20_000)


def create_app(settings: Settings | None = None):
    configured = settings or Settings.from_environment()

    def add_session_visibility(items):
        try:
            hidden_ids = load_hidden_session_ids(configured.session_metadata_path)
        except SessionMetadataError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        for item in items:
            item["hidden"] = item["session_id"].lower() in hidden_ids
        return items

    def session_response(profile: str, session_id: str):
        result = get_session(configured.database_path, profile, session_id)
        if result is None:
            return None
        return add_session_visibility([result])[0]

    @asynccontextmanager
    async def lifespan(_application):
        initialize(configured.database_path)
        yield

    application = FastAPI(
        title="Codex Sessions Viewer API", version="0.1.0", lifespan=lifespan
    )

    @application.get("/api/health")
    def health():
        initialize(configured.database_path)
        return {"status": "ok"}

    @application.get("/api/sessions")
    def sessions(limit: int = Query(default=100, ge=1, le=500)):
        return {
            "items": add_session_visibility(
                list_sessions(configured.database_path, limit)
            )
        }

    @application.get("/api/documents")
    def documents():
        try:
            return {
                "items": [
                    document.as_dict()
                    for document in list_documents(configured.documents_path)
                ]
            }
        except DocumentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.get("/api/documents/{document_id}")
    def document(document_id: str, request: Request):
        try:
            loaded = load_document(configured.documents_path, document_id)
        except DocumentError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        headers = {
            "ETag": loaded.etag,
            "Cache-Control": "no-cache",
            "X-Document-Modified-At": loaded.summary.modified_at,
        }
        if request.headers.get("if-none-match") == loaded.etag:
            return Response(status_code=304, headers=headers)
        return PlainTextResponse(
            loaded.markdown,
            media_type="text/markdown",
            headers=headers,
        )

    @application.get("/api/documents/{document_id}/annotations")
    def document_annotations(document_id: str):
        try:
            load_document(configured.documents_path, document_id)
        except DocumentError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {
            "items": list_document_annotations(configured.database_path, document_id)
        }

    @application.post("/api/documents/{document_id}/annotations", status_code=201)
    def add_document_annotation(document_id: str, payload: AnnotationSelectionInput):
        note = payload.note.strip()
        if not note:
            raise HTTPException(status_code=422, detail="Annotation note cannot be blank")
        try:
            document = load_document(configured.documents_path, document_id)
            return create_document_annotation(
                configured.database_path,
                document_id,
                document.summary.path,
                document.markdown,
                payload.start_line,
                payload.end_line,
                payload.selected_text,
                payload.prefix,
                payload.suffix,
                note,
            )
        except DocumentError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except AnnotationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.post("/api/sessions/discover")
    def discover(profile: str | None = Query(default=None)):
        try:
            result = discover_sessions(
                configured.database_path,
                load_sources(configured.sources_path),
                profile,
                configured.session_metadata_path,
            )
        except (OSError, RolloutError, SourceConfigurationError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result.as_dict()

    @application.get("/api/sessions/{profile}/{session_id}")
    def session(profile: str, session_id: str):
        result = session_response(profile, session_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        return result

    @application.get("/api/sessions/{profile}/{session_id}/messages")
    def messages(
        profile: str,
        session_id: str,
        start: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
    ):
        result = get_messages(
            configured.database_path, profile, session_id, start, limit
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        return result

    @application.get("/api/sessions/{profile}/{session_id}/search")
    def search(
        profile: str,
        session_id: str,
        q: str = Query(min_length=1, max_length=500),
    ):
        result = search_messages(configured.database_path, profile, session_id, q)
        if result is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        return result

    @application.get("/api/sessions/{profile}/{session_id}/annotations")
    def session_annotations(profile: str, session_id: str):
        if get_session(configured.database_path, profile, session_id) is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        return {
            "items": list_session_annotations(
                configured.database_path, profile, session_id
            )
        }

    @application.post(
        "/api/sessions/{profile}/{session_id}/annotations", status_code=201
    )
    def add_session_annotation(
        profile: str, session_id: str, payload: MessageAnnotationInput
    ):
        if get_session(configured.database_path, profile, session_id) is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        note = payload.note.strip()
        if not note:
            raise HTTPException(status_code=422, detail="Annotation note cannot be blank")
        try:
            return create_message_annotation(
                configured.database_path,
                profile,
                session_id,
                payload.message_index,
                payload.start_line,
                payload.end_line,
                payload.selected_text,
                payload.prefix,
                payload.suffix,
                note,
            )
        except AnnotationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.patch("/api/annotations/{annotation_id}")
    def edit_annotation(annotation_id: int, payload: AnnotationNoteInput):
        note = payload.note.strip()
        if not note:
            raise HTTPException(status_code=422, detail="Annotation note cannot be blank")
        result = update_annotation_note(configured.database_path, annotation_id, note)
        if result is None:
            raise HTTPException(status_code=404, detail="Annotation does not exist")
        return result

    @application.delete("/api/annotations/{annotation_id}", status_code=204)
    def remove_annotation(annotation_id: int):
        if not delete_annotation(configured.database_path, annotation_id):
            raise HTTPException(status_code=404, detail="Annotation does not exist")

    @application.put("/api/sessions/{profile}/{session_id}/title")
    def set_title(profile: str, session_id: str, payload: SessionTitleInput):
        if get_session(configured.database_path, profile, session_id) is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        title = " ".join(payload.title.split())
        if not title:
            raise HTTPException(status_code=422, detail="Session title cannot be blank")
        try:
            save_session_title(configured.session_metadata_path, session_id, title)
            update_session_title(configured.database_path, session_id, title)
        except SessionMetadataError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return session_response(profile, session_id)

    @application.delete("/api/sessions/{profile}/{session_id}/title")
    def reset_title(profile: str, session_id: str):
        if get_session(configured.database_path, profile, session_id) is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        try:
            save_session_title(configured.session_metadata_path, session_id, None)
            update_session_title(configured.database_path, session_id, None)
        except SessionMetadataError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return session_response(profile, session_id)

    @application.put("/api/sessions/{profile}/{session_id}/visibility")
    def set_visibility(
        profile: str, session_id: str, payload: SessionVisibilityInput
    ):
        if get_session(configured.database_path, profile, session_id) is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        try:
            save_session_hidden(
                configured.session_metadata_path, session_id, payload.hidden
            )
        except SessionMetadataError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return session_response(profile, session_id)

    @application.put(
        "/api/sessions/{profile}/{session_id}/bookmarks",
        response_model=BookmarkBackup,
    )
    def export_bookmarks(
        profile: str,
        session_id: str,
        payload: BookmarkBackupInput,
    ):
        indexed_session = get_session(configured.database_path, profile, session_id)
        if indexed_session is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        try:
            return save_backup(
                configured.bookmarks_path,
                profile,
                session_id,
                indexed_session["title"],
                [bookmark.model_dump() for bookmark in payload.bookmarks],
            )
        except (BookmarkBackupError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.get(
        "/api/sessions/{profile}/{session_id}/bookmarks",
        response_model=BookmarkBackup,
    )
    def restore_bookmarks(profile: str, session_id: str):
        if get_session(configured.database_path, profile, session_id) is None:
            raise HTTPException(status_code=404, detail="Session is not indexed")
        try:
            snapshot = load_backup(configured.bookmarks_path, profile, session_id)
            if snapshot is None:
                raise HTTPException(
                    status_code=404,
                    detail="No bookmark backup exists for this session",
                )
            return BookmarkBackup.model_validate(snapshot)
        except BookmarkBackupError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ValidationError as error:
            raise HTTPException(
                status_code=400,
                detail="Bookmark backup contains invalid data",
            ) from error

    @application.post("/api/sessions/{profile}/{session_id}/sync")
    def sync(profile: str, session_id: str):
        try:
            result = sync_session(
                configured.database_path,
                load_sources(configured.sources_path),
                profile,
                session_id,
                configured.session_metadata_path,
            )
        except (OSError, RolloutError, SourceConfigurationError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result.__dict__

    @application.post("/api/sessions/{profile}/{session_id}/archive")
    def archive(profile: str, session_id: str):
        try:
            sources = load_sources(configured.sources_path)
            source = select_sources(sources, profile)[0]
            result = export_archive(
                configured.database_path,
                configured.archives_path,
                profile,
                session_id,
                source.adapter,
            )
        except (ArchiveError, OSError, SourceConfigurationError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result.as_dict()

    return application


app = create_app()
