# Agent Sessions Viewer

A local, read-only viewer for Codex and Claude Code JSONL transcripts. The viewer
incrementally stores visible user and assistant messages in SQLite, exposes
bounded ranges through FastAPI, and displays them in a virtualized React
transcript served by Caddy. Visible messages are rendered as GitHub-flavored
Markdown with syntax highlighting and Mermaid diagrams.

The transcript files remain the source of truth. They are mounted read-only and
are never modified by the viewer.

## Requirements

- Docker with Docker Compose
- Existing Codex and/or Claude Code session directories

By default, Compose mounts the repository's parent `.codex_homes` directory
once at `/sources`, read-only. This covers sibling Codex homes and the Claude
`projects` directory without adding a Docker mount for every account. For
another layout:

```bash
cp .env.example .env
```

Then set `VIEWER_SOURCES_ROOT` in `.env` to their common host directory. The
entire root is exposed to the API container beneath `/sources` with
`read_only: true`; only directories listed in `config/sources.toml` are
scanned. The project-owned `config/` directory is mounted at `/config`, also
read-only. The rebuildable SQLite index is kept in the `viewer-data` Docker
volume.

`config/sources.toml` assigns a source label, adapter, and container path to
each session directory below `/sources`. Adding another source changes only
that file, not `compose.yaml`. Discovery is recursive below those explicit
roots; it does not depend on Codex's date directories, Claude's project
directories, or JSONL filenames.

For example:

```toml
[[sources]]
id = "another_codex_home"
adapter = "codex"
path = "/sources/another_codex_home/sessions"
```

## Start the viewer

Build and start FastAPI and Caddy:

```bash
docker compose up --build -d
```

Opening the application automatically catalogs the mounted transcripts. Discovery
does not import complete message histories. To run the same scan explicitly:

```bash
docker compose exec api viewer discover
```

Index one session using a complete UUID or unique prefix:

```bash
docker compose exec api viewer sync codex_2 019fdbaf
```

Claude sessions use the same command:

```bash
docker compose exec api viewer sync claude 087e7ac1
```

Open <http://localhost:8080>. The browser loads 30-message blocks around the
visible viewport and keeps at most seven blocks (roughly 210 messages) in its
in-memory cache. Use **Beginning** and **Latest** to move through a long session
without downloading the entire transcript.

## Session discovery

Discovery recursively scans every configured source for JSONL candidates. Its
configured adapter reads at most the first 256 KiB to recognize a main session
and find its content-derived UUID, title, workspace, and creation timestamp.
Unrelated JSONL and Claude subagent sidecars are ignored. Discovery never
imports messages or advances an incremental sync cursor.

The sidebar runs discovery when the viewer opens and provides **Rescan** for
sessions created later. A discovered session is marked **Not indexed** until
its **Index session** button is used. If a previously cataloged transcript is no
longer mounted, it is marked **Source unavailable**; existing indexed messages
are retained.

Sessions are sorted only by latest recorded activity and separated into local
calendar-day groups. The sidebar can be collapsed to a narrow rail; that choice
is remembered in browser storage.

Discovery applies persistent titles from `config/session_metadata.json`.
Metadata is keyed only by content-derived session UUID, independently of the
source, provider, or directory:

```json
{
  "019fdbaf-c2ea-7e50-ae8f-8fa79e733904": {
    "title": "Codex frontend UI"
  }
}
```

Only this object-valued format is accepted; the legacy `{id: "title"}` format
is deliberately rejected. Automatic and custom titles are stored separately,
so removing an override restores the transcript-derived title on the next
rescan.

Limit discovery to one source when using the CLI:

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

The first sync reads one complete transcript. Later syncs seek directly to the
last completely processed byte and inspect only appended JSONL lines. A partial
final line is left for the next sync. If the transcript is replaced or truncated,
only that session is rebuilt.

The UI's **Sync now** button invokes the same importer for the currently open
session. Repeating a sync is idempotent. If new messages are imported, the
current reading position remains stable and an indicator appears beside
**Latest**. Successful synchronization notices disappear after five seconds. Tool
calls, tool outputs, reasoning, and injected context are not stored.

The compact **Watch** toggle polls only the currently open, indexed session
every two seconds. Polls use the same byte-offset importer, so a no-op reads
only from the last complete JSONL offset and produces no notification. New
messages automatically keep the view at the live tail when it was already at
the bottom. If you have scrolled upward to read, the current position is kept
and a small indicator appears beside **Latest**. The indicator disappears as
soon as the newest message enters the visible range. Switching sessions,
closing the page, or disabling the toggle stops that watcher; no other session
is synchronized in the background. The preference is remembered per session
in browser storage.

The Codex adapter renders modern `event_msg` user and agent messages. The Claude
adapter renders genuine user text and assistant text blocks while excluding
local-command wrappers, metadata, thinking, tool calls, tool results,
attachments, snapshots, and subagent transcripts. Manager/subagent views and
client-side transcript editing remain later milestones.

## Message rendering

User and agent messages use the same Markdown pipeline. It supports headings,
lists, tables, task lists, blockquotes, links, inline code, fenced code, and raw
HTML. Fenced code is syntax-highlighted when its language is recognized. Every
code block has a copy button, and the button in a message header copies that
message's original Markdown.

A fenced block marked `mermaid` is rendered as a diagram. Mermaid is downloaded
by the browser only when a visible message needs it. Invalid diagrams show the
rendering error and retain their source text instead of disappearing.

Press **Ctrl+F** (or **Cmd+F** on macOS) to search the complete indexed session,
including messages that are not mounted by the virtual list. The temporary
search bar replaces the header actions while it is open. Enter and Shift+Enter
move between matches, and Escape closes it. Search results scroll to and outline
the matching message; the backend performs a literal, case-insensitive SQLite
substring search rather than relying on the browser DOM.

Raw HTML is intentionally not sanitized because this viewer is designed for a
single user's trusted local transcripts. Keep the Caddy port bound to localhost,
as it is in the supplied Compose configuration, and do not use this deployment
to display untrusted session files.

## Transcript controls

Each message can be folded independently from its header. **Collapse all** and
**Expand all** apply the same choice across the session, including messages
that are not currently mounted by the virtual list. The fold state is stored in
the browser for each source and session; it does not modify SQLite or the
transcript. Collapsed messages skip Markdown and Mermaid rendering entirely.

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
partial final lines, transcript truncation, ignored tool events, cross-source
UUID isolation, API pagination and search, recursive discovery, unrelated JSONL,
Claude filtering, strict metadata migration, missing sources, schema migration,
and persistent title overrides.

## API

```text
GET  /api/health
GET  /api/sessions
POST /api/sessions/discover
GET  /api/sessions/{profile}/{session_id}
GET  /api/sessions/{profile}/{session_id}/messages?start=0&limit=30
GET  /api/sessions/{profile}/{session_id}/search?q=substring
POST /api/sessions/{profile}/{session_id}/sync
```

The list contains discovered catalog entries, including transcripts whose messages
have not yet been indexed. Background synchronization is intentionally
deferred.
