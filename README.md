# Codex Sessions Viewer

A local, read-only viewer for Codex rollout JSONL files. The first milestone
incrementally stores visible user and assistant messages in SQLite, exposes
bounded pages through FastAPI, and displays them with a small React application
served by Caddy.

The rollout files remain the source of truth. They are mounted read-only and
are never modified by the viewer.

## Requirements

- Docker with Docker Compose
- Existing Codex session directories

The default Compose paths expect this repository to live beside `codex_1` and
`codex_2`, as it does when checked out as the `.codex_homes/sessions_viewer`
submodule. For another layout:

```bash
cp .env.example .env
```

Then edit the two host paths in `.env`. They are mounted inside the API
container as `/sessions/codex_1` and `/sessions/codex_2` with `read_only: true`.
The rebuildable SQLite index is kept in the `viewer-data` Docker volume.

## Start the viewer

Build and start FastAPI and Caddy:

```bash
docker compose up --build -d
```

Import one session using a complete UUID or unique prefix:

```bash
docker compose exec api viewer sync codex_2 019fdbaf
```

Open <http://localhost:8080> and reload the session list. The browser only
requests 30 messages at a time.

Useful checks:

```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/sessions
docker compose logs -f api web
```

Stop the containers without deleting the SQLite volume:

```bash
docker compose down
```

Delete the rebuildable index only when deliberately starting over:

```bash
docker compose down --volumes
```

## Synchronization behavior

The first sync reads one complete rollout. Later syncs seek directly to the
last completely processed byte and inspect only appended JSONL lines. A partial
final line is left for the next sync. If the rollout is replaced or truncated,
only that session is rebuilt.

The UI's **Sync now** button invokes the same importer for the currently open
session. Repeating a sync is idempotent. Tool calls, tool outputs, reasoning,
and injected context are not stored.

The current milestone intentionally supports modern `event_msg` user and agent
messages only. Legacy message formats, manager coordination events, Markdown
HTML rendering, Mermaid, syntax highlighting, folding, and virtual scrolling
are later milestones.

## Tests

Run backend tests in Docker:

```bash
docker compose run --rm backend-tests
```

Run the frontend lint and production build in Docker:

```bash
docker compose run --rm frontend-check
```

For faster local development, the equivalent uv and npm commands are:

```bash
cd backend
uv run --group dev pytest

cd ../frontend
npm run lint
npm run build
```

Backend tests cover first import, no-op resynchronization, append-only import,
partial final lines, rollout truncation, ignored tool events, cross-profile
UUID isolation, and API pagination limits.

## API in milestone 1

```text
GET  /api/health
GET  /api/sessions
GET  /api/sessions/{profile}/{session_id}
GET  /api/sessions/{profile}/{session_id}/messages?start=0&limit=30
POST /api/sessions/{profile}/{session_id}/sync
```

The list contains sessions already imported into SQLite. Automatic discovery
and background synchronization are intentionally deferred.
