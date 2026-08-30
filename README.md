# Codex Sessions Viewer

A local, read-only viewer for Codex rollout JSONL files. The viewer
incrementally stores visible user and assistant messages in SQLite, exposes
bounded ranges through FastAPI, and displays them in a virtualized React
transcript served by Caddy. Visible messages are rendered as GitHub-flavored
Markdown with syntax highlighting and Mermaid diagrams.

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

Open <http://localhost:8080>. The browser loads 30-message blocks around the
visible viewport and keeps at most seven blocks (roughly 210 messages) in its
in-memory cache. Use **Beginning** and **Latest** to move through a long session
without downloading the entire transcript.

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
session. Repeating a sync is idempotent. If new messages are imported, the
current reading position remains stable and a button offers to jump to the new
tail. Tool calls, tool outputs, reasoning, and injected context are not stored.

The current milestone intentionally supports modern `event_msg` user and agent
messages only. Legacy message formats, manager coordination events, Markdown
folding, and client-side transcript editing are later milestones.

## Message rendering

User and agent messages use the same Markdown pipeline. It supports headings,
lists, tables, task lists, blockquotes, links, inline code, fenced code, and raw
HTML. Fenced code is syntax-highlighted when its language is recognized. Every
code block has a copy button, and the button in a message header copies that
message's original Markdown.

A fenced block marked `mermaid` is rendered as a diagram. Mermaid is downloaded
by the browser only when a visible message needs it. Invalid diagrams show the
rendering error and retain their source text instead of disappearing.

Raw HTML is intentionally not sanitized because this viewer is designed for a
single user's trusted local rollouts. Keep the Caddy port bound to localhost,
as it is in the supplied Compose configuration, and do not use this deployment
to display untrusted session files.

## Tests

Run backend tests in Docker:

```bash
docker compose run --build --rm backend-tests
```

Run the frontend lint and production build in Docker:

```bash
docker compose run --build --rm frontend-check
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
