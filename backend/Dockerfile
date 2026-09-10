FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS source

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

FROM source AS test

COPY tests ./tests
RUN uv sync --frozen
CMD ["uv", "run", "pytest", "-q"]

FROM source AS runtime

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    VIEWER_DATABASE=/data/viewer.sqlite3 \
    VIEWER_SOURCES_FILE=/config/sources.toml \
    VIEWER_SESSION_METADATA_FILE=/config/session_metadata.json \
    VIEWER_BOOKMARKS_DIRECTORY=/data/bookmarks

RUN mkdir -p /config /data /sources /data/bookmarks

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]

CMD ["uvicorn", "session_viewer_backend.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
