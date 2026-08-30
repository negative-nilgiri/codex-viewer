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

Opening the application automatically catalogs the mounted rollouts. Discovery
does not import complete message histories. To run the same scan explicitly:

```bash
docker compose exec api viewer discover
```

Index one session using a complete UUID or unique prefix:

```bash
docker compose exec api viewer sync codex_2 019fdbaf
```

Open <http://localhost:8080>. The browser loads 30-message blocks around the
visible viewport and keeps at most seven blocks (roughly 210 messages) in its
in-memory cache. Use **Beginning** and **Latest** to move through a long session
without downloading the entire transcript.

## Session discovery

Discovery scans every mounted `codex_*` profile and adds its rollout files to
the catalog. For a new or still-unindexed rollout, it reads at most the first
256 KiB to find a useful title, workspace, and creation timestamp. It never
imports messages or advances an incremental sync cursor. Already-indexed
rollouts are refreshed from filesystem metadata without reopening their
contents.

The sidebar runs discovery when the viewer opens and provides **Rescan** for
sessions created later. A discovered session is marked **Not indexed** until
its **Index session** button is used. If a previously cataloged rollout is no
longer mounted, it is marked **Source unavailable**; existing indexed messages
are retained.

Limit discovery to one profile when using the CLI:

```bash
docker compose exec api viewer discover codex_2
```

Periodic background discovery and synchronization are intentionally deferred.

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
tail. Successful synchronization notices disappear after five seconds. Tool
calls, tool outputs, reasoning, and injected context are not stored.

The current milestone intentionally supports modern `event_msg` user and agent
messages only. Legacy message formats, manager coordination events, Markdown
and client-side transcript editing are later milestones.

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

## Transcript controls

Each message can be folded independently from its header. **Collapse all** and
**Expand all** apply the same choice across the session, including messages
that are not currently mounted by the virtual list. The fold state is stored in
the browser for each profile and session; it does not modify SQLite or the
rollout. Collapsed messages skip Markdown and Mermaid rendering entirely.

The session header also provides a copy button for the complete session ID.

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
UUID isolation, API pagination limits, shallow discovery, missing sources, and
migration of an existing schema-v1 catalog.

## API in milestone 1

```text
GET  /api/health
GET  /api/sessions
POST /api/sessions/discover
GET  /api/sessions/{profile}/{session_id}
GET  /api/sessions/{profile}/{session_id}/messages?start=0&limit=30
POST /api/sessions/{profile}/{session_id}/sync
```

The list contains discovered catalog entries, including rollouts whose messages
have not yet been indexed. Background synchronization is intentionally
deferred.
