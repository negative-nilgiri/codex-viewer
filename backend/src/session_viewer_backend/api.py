from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from .config import Settings
from .database import initialize
from .repository import get_messages, get_session, list_sessions
from .rollout import RolloutError
from .sync import sync_session


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

    @application.post("/api/sessions/{profile}/{session_id}/sync")
    def sync(profile: str, session_id: str):
        try:
            result = sync_session(
                configured.database_path,
                configured.sessions_root,
                profile,
                session_id,
            )
        except (OSError, RolloutError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result.__dict__

    return application


app = create_app()
