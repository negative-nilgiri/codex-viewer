from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from .archive import ArchiveError, export_archive
from .bookmarks import BookmarkBackupError, load_backup, save_backup
from .config import Settings
from .database import initialize
from .discovery import discover_sessions
from .documents import DocumentError, list_documents, load_document
from .repository import get_messages, get_session, list_sessions, search_messages
from .rollout import RolloutError
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


def create_app(settings: Settings | None = None):
    configured = settings or Settings.from_environment()

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
        return {"items": list_sessions(configured.database_path, limit)}

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
        result = get_session(configured.database_path, profile, session_id)
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
