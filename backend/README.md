# Viewer backend

FastAPI and standard-library SQLite backend for the agent Sessions Viewer.

```bash
uv sync
uv run pytest
uv run viewer --help
uv run uvicorn session_viewer_backend.api:app --reload
```

Configuration:

- `VIEWER_DATABASE`, default `/data/viewer.sqlite3`
- `VIEWER_SOURCES_FILE`, default `/config/sources.toml`
- `VIEWER_SESSION_METADATA_FILE`, default `/config/session_metadata.json`
- `VIEWER_BOOKMARKS_DIRECTORY`, default `/data/bookmarks`
- `VIEWER_ARCHIVES_DIRECTORY`, default `/data/archives`

Export the currently indexed user/assistant conversation without synchronizing
the source first:

```bash
uv run viewer archive SOURCE FULL_SESSION_ID
```
