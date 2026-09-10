# Agent Sessions Viewer

A local web interface for reading Codex and Claude Code session transcripts.
It renders user and assistant messages as Markdown, remains responsive with very
long conversations, and can follow an active session as new messages arrive.

The application has four small pieces:

- FastAPI discovers transcripts and incrementally indexes visible messages.
- SQLite stores the rebuildable message index.
- React renders only the part of a conversation currently being viewed.
- Caddy serves the frontend and proxies API requests.

Transcript files are mounted read-only and remain the source of truth. The
viewer never modifies them.

## Requirements

- Docker with Docker Compose
- A directory containing Codex and/or Claude Code JSONL session files
- A modern web browser
- Optional: Python 3.10 or newer for the host-side title and counting scripts

Python, Node.js, and Caddy do not need to be installed on the host for normal
viewer use. Docker builds everything the application requires.

## Quick start with the default layout

The checked-in configuration expects this repository to be inside a common
session-data directory with the following layout:

```text
.codex_homes/
├── sessions_viewer/       # this repository
├── codex_1/
│   └── sessions/
├── codex_2/
│   └── sessions/
└── projects/              # Claude Code project sessions
```

From the repository root, start the application:

```bash
docker compose up --build -d
```

Then open <http://localhost:8080>.

The first page load discovers available sessions. Select a session in the
sidebar and press **Index session** to import its visible user and assistant
messages. Turn on **Watch** when you want the open session to follow new
messages automatically.

## Configure transcript locations

Compose makes one host directory available inside the API container at
`/sources`. By default, the mounted host directory is the parent of this
repository. To mount a different directory, create `.env`:

```bash
cp .env.example .env
```

Set its absolute or repository-relative path:

```dotenv
VIEWER_SOURCES_ROOT=/Users/me/agent-session-data
VIEWER_PORT=8080
```

Next, edit `config/sources.toml`. Each entry gives a source a stable name,
selects its transcript format, and points to a directory inside `/sources`:

```toml
[[sources]]
id = "work_codex"
adapter = "codex"
path = "/sources/work-codex/sessions"

[[sources]]
id = "claude"
adapter = "claude"
path = "/sources/projects"
```

The example above corresponds to these host directories:

```text
/Users/me/agent-session-data/work-codex/sessions
/Users/me/agent-session-data/projects
```

Source IDs are labels chosen by you. Keep them stable because SQLite records
and browser preferences use them to distinguish sessions. Discovery searches
recursively below each configured path, so date folders, project folders, and
JSONL filenames do not need a particular shape.

After changing the mounted root, recreate the containers:

```bash
docker compose up --build -d
```

To confirm the resolved host mount before debugging discovery:

```bash
docker compose config
```

## Discover and read sessions

Opening the viewer runs discovery automatically. Discovery catalogs session
metadata but does not import every conversation, which keeps startup fast even
when the source root contains many sessions.

The main workflow is:

1. Use **Rescan** in the sidebar when a new session does not appear.
2. Select a session.
3. Press **Index session** the first time it is opened.
4. Use **Sync now** for a one-time update or enable **Watch** for the active
   conversation.

The sidebar is ordered by latest activity and grouped by day. Its collapse
state is remembered by the browser.

The same operations are available from the command line. A source ID and a
complete session UUID or unique UUID prefix identify a session:

```bash
docker compose exec api viewer discover
docker compose exec api viewer discover codex_2
docker compose exec api viewer sync codex_2 019fdbaf
docker compose exec api viewer sync claude 087e7ac1
```

## Give sessions custom titles

The viewer normally derives a title from the transcript. To assign a persistent
title, copy the complete session ID from the session header and run:

```bash
./scripts/session_title.py set \
  019fdbaf-c2ea-7e50-ae8f-8fa79e733904 \
  "Codex frontend UI"
```

Click **Rescan** in the viewer to display the new title.

List all custom titles:

```bash
./scripts/session_title.py list
```

Remove a custom title and return to the transcript-derived title:

```bash
./scripts/session_title.py remove \
  019fdbaf-c2ea-7e50-ae8f-8fa79e733904
```

The script updates `config/session_metadata.json` atomically. A different
metadata file can be selected by placing `--file PATH` before the command.

The underlying format is intentionally simple:

```json
{
  "019fdbaf-c2ea-7e50-ae8f-8fa79e733904": {
    "title": "Codex frontend UI"
  }
}
```

Session titles are deployment configuration. Message bookmarks and bookmark
labels are different: they are stored only in the current browser's local
storage.

## Reading controls

- **Beginning** and **Latest** move to either end of the session.
- Enter the displayed message number in the **# / Go** control to jump directly
  to that message.
- The star in a message header adds or removes a bookmark.
- **Bookmarks** opens the saved-message list. Bookmark labels are generated
  from message text and can be edited in place.
- **Fold**, **Collapse all**, and **Expand all** control long message bodies.
- Messages with at least two headings have an **Outline** button. The outline is
  closed by default and provides quick jumps within that message.
- Rendered messages substantially taller than the viewport have a compact
  **Top of message** action at their bottom.
- The session ID, complete message Markdown, and every fenced code block have
  dedicated copy buttons.

Press **Ctrl+F** or **Cmd+F** to search the complete indexed conversation—not
just the messages currently rendered on screen. Enter and Shift+Enter move
between matches, and Escape closes search.

Fold state, bookmarks, bookmark labels, sidebar state, and Watch preferences
are stored in browser local storage. They do not modify SQLite or transcript
files.

## Markdown rendering

User and assistant messages share the same GitHub-flavored Markdown pipeline.
The viewer supports headings, lists, tables, task lists, blockquotes, links,
inline code, fenced code, and raw HTML. Recognized fenced-code languages receive
syntax highlighting.

Headings receive message-scoped anchors, with a small `#` link visible only on
hover. Ordinary same-document Markdown links are resolved inside their own
message, so Codex can produce a compact table of contents without conflicting
with identically named headings elsewhere in the conversation:

```markdown
- [Architecture](#architecture)
- [Trade-offs](#trade-offs)

## Architecture
...

## Trade-offs
...
```

For long answers, ask Codex to start with a short Markdown table of contents
using this standard link format. These anchors navigate the currently rendered
message; durable links that reopen a session at a specific heading are not yet
part of the URL scheme.

A fenced block tagged `mermaid` is rendered as a Mermaid diagram:

````markdown
```mermaid
flowchart LR
    JSONL --> SQLite --> Browser
```
````

Use **Raw** in a diagram toolbar to switch between the rendered diagram and its
original Mermaid source. Invalid diagrams display their error and source instead
of disappearing.

Raw HTML is not sanitized because this is a single-user viewer for trusted
local transcripts. Caddy binds to `127.0.0.1` by default. Do not expose this
application publicly or use it for untrusted transcript files.

## Synchronization and stored data

The first sync reads the selected transcript. Later syncs start at the last
completely processed byte and inspect only appended JSONL records. Repeating a
sync is safe, and truncating or replacing a transcript rebuilds only that
session.

**Watch** polls the open session every two seconds. It does not scan or import
other sessions in the background. When the viewer is already at the end, new
messages remain in view. When reading earlier messages, an indicator appears
beside **Latest** instead.

Only visible user and assistant text is indexed. Metadata, injected context,
reasoning, tool calls, tool results, attachments, and other non-conversation
records are excluded.

SQLite lives in the Docker volume named `codex-sessions-viewer_viewer-data`.
It is an index, not the source of truth, and can be rebuilt from the JSONL
transcripts.

## Useful operational commands

Check service status and health:

```bash
docker compose ps
curl http://localhost:8080/api/health
```

Follow backend and web-server logs:

```bash
docker compose logs -f api web
```

Rebuild after changing application code:

```bash
docker compose up --build -d
```

Stop the application without deleting the SQLite index:

```bash
docker compose down
```

Delete and rebuild the index only when intentionally starting over:

```bash
docker compose down --volumes
```

## Troubleshooting

### No sessions appear

Run discovery directly and inspect its error:

```bash
docker compose exec api viewer discover
docker compose logs --tail=100 api
```

Then use `docker compose config` to verify `VIEWER_SOURCES_ROOT` and make sure
every path in `config/sources.toml` exists beneath `/sources` in the container.

### A session exists but has no messages

Select it and press **Index session**. The catalog and message index are
separate on purpose. Also remember that tool-only and metadata records are not
displayed as messages.

### Compare a JSONL transcript with SQLite

The diagnostic script counts messages using the same adapter rules as the
backend:

```bash
./scripts/count_session_messages.py /absolute/path/to/session.jsonl
```

Select an adapter explicitly only when automatic detection is insufficient:

```bash
./scripts/count_session_messages.py --adapter codex /path/to/session.jsonl
./scripts/count_session_messages.py --adapter claude /path/to/session.jsonl
```

Its `visible messages` value is the count expected in SQLite after a successful
sync. `jsonl lines` is larger because one transcript contains many kinds of
records.

### The browser still shows an older frontend

After rebuilding the web container, reload the page so the browser fetches the
new hashed JavaScript and CSS assets.

## Development and tests

Run the backend suite in Docker:

```bash
docker compose --profile test run --rm --build backend-tests
```

Run frontend lint and the production TypeScript/Vite build in Docker:

```bash
docker compose --profile test run --rm --build frontend-check
```

For local development, the backend requires Python 3.14 and
[uv](https://docs.astral.sh/uv/), while the frontend uses Node.js and npm:

```bash
cd backend
uv run --group dev pytest

cd ../frontend
npm ci
npm run lint
npm run build
```

## HTTP API

The React frontend uses these endpoints:

```text
GET  /api/health
GET  /api/sessions
POST /api/sessions/discover
GET  /api/sessions/{source_id}/{session_id}
GET  /api/sessions/{source_id}/{session_id}/messages?start=0&limit=30
GET  /api/sessions/{source_id}/{session_id}/search?q=substring
POST /api/sessions/{source_id}/{session_id}/sync
```
