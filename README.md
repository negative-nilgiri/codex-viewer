# Agent Sessions Viewer

A local web interface for reading Codex and Claude Code session transcripts and
ordinary Markdown documents. It renders user and assistant messages as
Markdown, remains responsive with very long conversations, and can follow an
active session as new messages arrive.

The application has four small pieces:

- FastAPI discovers transcripts and incrementally indexes visible messages.
- SQLite stores the rebuildable message index and durable annotations.
- React renders only the part of a conversation currently being viewed.
- Caddy serves the frontend and proxies API requests.

Markdown documents are read directly from a separate directory. They are not
copied into SQLite or converted into fake conversations.

Transcript files are mounted read-only and remain the source of truth. The
viewer never modifies them. Conversation archives created explicitly from the
UI or CLI use a separate writable directory.

## Requirements

- Docker with Docker Compose
- A directory containing Codex and/or Claude Code JSONL session files
- A modern web browser
- Optional: [`just`](https://just.systems/) for concise project commands
- Optional: Python 3.10 or newer for the host-side title and counting scripts

Python, Node.js, and Caddy do not need to be installed on the host for normal
viewer use. Docker builds everything the application requires.

## Common session locations

The tools normally store their JSONL session files beneath these directories:

| Tool | Common default directory |
| --- | --- |
| Codex | `$HOME/.codex/sessions` |
| Claude Code | `$HOME/.claude/projects` |

These are conventional defaults, not paths hard-coded by the viewer. Use the
actual locations on your machine if either tool has been configured with a
different home directory.

`$HOME` above is shell notation for your user home. In `.env`, use the expanded
absolute path—for example `/Users/me/.codex/sessions`—rather than writing the
literal `$HOME` expression. Docker Compose mounts `VIEWER_SOURCES_ROOT` directly
and shell-style expansion inside `.env` should not be relied upon.

## Quick start

`VIEWER_SOURCES_ROOT` is the deepest common host directory containing every
session directory you want the viewer to access. Docker mounts this one
directory read-only at `/sources`; the source configuration selects directories
inside that mount. Do not choose a broader parent than necessary.

Start by creating local configuration files from the documented examples:

```bash
cp .env.example .env
cp config/sources.example.toml config/sources.toml
```

Both resulting files are gitignored, so machine-specific paths and source names
will not be committed.

### Example: one Codex sessions directory

Suppose the only sessions you want to track are beneath:

```text
/Users/me/.codex/sessions/
├── 2026/
│   └── 09/...
└── ...
```

The deepest directory containing everything you want is the `sessions`
directory itself, so configure `.env` with its absolute path:

```dotenv
VIEWER_SOURCES_ROOT=/Users/me/.codex/sessions
VIEWER_ARCHIVES_ROOT=./archives
VIEWER_METADATA_ROOT=./metadata
VIEWER_DOCUMENTS_ROOT=./documents
VIEWER_PORT=8080
```

That exact directory becomes `/sources` inside the container:

```text
Host:      /Users/me/.codex/sessions
Container: /sources
```

Therefore `config/sources.toml` uses `/sources`, not the host path:

```toml
[[sources]]
id = "personal"
adapter = "codex"
path = "/sources"
```

### Example: several session directories

Suppose you want all three of these directories:

```text
/Users/me/agent-sessions/          # deepest common parent
├── personal/sessions/             # Codex
├── work/sessions/                 # Codex
└── claude-projects/               # Claude Code
```

Set the common parent as the mount:

```dotenv
VIEWER_SOURCES_ROOT=/Users/me/agent-sessions
VIEWER_ARCHIVES_ROOT=./archives
VIEWER_METADATA_ROOT=./metadata
VIEWER_DOCUMENTS_ROOT=./documents
VIEWER_PORT=8080
```

The paths beneath that parent retain the same relative layout beneath
`/sources`, so configure all three explicitly:

```toml
[[sources]]
id = "personal"
adapter = "codex"
path = "/sources/personal/sessions"

[[sources]]
id = "work"
adapter = "codex"
path = "/sources/work/sessions"

[[sources]]
id = "claude"
adapter = "claude"
path = "/sources/claude-projects"
```

Here:

- A **source** is one configured directory tree containing session JSONL files.
  It has a stable label, one transcript-format adapter, and one path inside the
  container. A source can contain any number of sessions recursively; it does
  not mean one session and does not have to mean one account.
- `id` is a label chosen by you. It is displayed in the viewer and is not an
  account name. Keep it stable because it becomes part of the indexed session
  identity and browser preferences.
- `adapter` selects the transcript format: `codex`, `claude`, or the viewer's
  own `archive` format.
- `path` is always a path inside the container and must be reachable beneath
  `/sources` for external transcript sources. The built-in archive source uses
  the separate `/archives` writable mount. Discovery searches either path
  recursively for supported JSONL files.

Start the application from the repository root:

```bash
docker compose up --build -d
```

Then open <http://localhost:8080>. The first page load discovers available
sessions. Select one and press **Index session** to import its visible messages.
Enable **Watch** only when you want the open session to follow new messages.

The comments in `config/sources.example.toml` repeat these mapping rules. All
external transcript source paths must resolve beneath the one host directory
selected by `VIEWER_SOURCES_ROOT`; the archive source is the one documented
exception because it uses `/archives`.

After changing `.env` or its mounted root, recreate the containers. To inspect
the exact resolved mount before debugging discovery, run:

```bash
docker compose up --build -d
docker compose config
```

## Command shortcuts with `just`

The checked-in `justfile` provides short names for routine commands. Running
`just` without arguments prints the complete command list with descriptions.
It is only a convenience layer; the equivalent Docker commands remain valid.

First-time setup and startup:

```bash
just setup       # Create missing config and local data directories
# Edit .env and config/sources.toml now.
just up          # Build and start
```

Daily operation:

```bash
just start
just status
just health
just logs
just logs-api
just down
```

Discovery and indexing:

```bash
just discover
just sources
just discover-source personal
just sync personal 019fdbaf
just archive personal 019fdbaf-c2ea-7e50-ae8f-8fa79e733904
```

Validation and utilities:

```bash
just test
just test-backend
just test-frontend
just title-list
just title-set 019fdbaf-c2ea-7e50-ae8f-8fa79e733904 "Codex frontend UI"
just title-remove 019fdbaf-c2ea-7e50-ae8f-8fa79e733904
just count /absolute/path/to/session.jsonl
just count-as claude /absolute/path/to/session.jsonl
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
docker compose exec api viewer sources
docker compose exec api viewer discover
docker compose exec api viewer discover personal
docker compose exec api viewer sync personal 019fdbaf
docker compose exec api viewer sync claude 087e7ac1
```

## Read Markdown documents

Compose mounts the host directory selected by `VIEWER_DOCUMENTS_ROOT` read-only
at `/documents`. The default is the gitignored `documents/` directory beside
this README:

```dotenv
VIEWER_DOCUMENTS_ROOT=./documents
```

Copy any number of UTF-8 `.md` files into it. Nested directories are supported:

```text
documents/
├── architecture.md
├── notes/
│   └── ollama.md
└── reviews/
    ├── backend.md
    └── frontend.md
```

Open **Documents** in the sidebar and press the refresh icon after adding,
renaming, or removing files. Each file is a separate document. Its first H1 is
used as its display title, with the filename as the fallback.

Opening a document reads that file directly from disk and renders the complete
document as one continuous page. The browser caches the loaded Markdown for the
current SPA session; **Reload** explicitly reads the file again. Documents use
the same headings, outline, Mermaid diagrams, syntax highlighting, raw HTML,
and copy buttons as conversation messages.

Documents are never written to SQLite and require no discovery, indexing, or
synchronization command. The API only lists filesystem metadata and returns the
selected file. To use a different directory, set an absolute host path in
`.env`, then recreate the API container:

```dotenv
VIEWER_DOCUMENTS_ROOT=/Users/me/Documents/markdown-library
```

## Archive a conversation

**Archive** writes the selected conversation to the viewer's stable JSONL
format. It exports only messages already present in SQLite, so press **Sync
now** first when the source may have newer messages. Export is explicit: Watch
and normal synchronization never write archives.

By default Compose enables a writable bind mount:

```text
Host:      ./archives
Container: /archives
```

The directory is gitignored. To store archives in a backed-up location, put an
absolute host path in `.env`:

```dotenv
VIEWER_ARCHIVES_ROOT=/Users/me/Documents/agent-conversation-archives
```

Keep this source in `config/sources.toml` so exported files can be discovered
and viewed like any other session:

```toml
[[sources]]
id = "archive"
adapter = "archive"
path = "/archives"
```

From the UI, open an indexed session and press **Archive**. The confirmation
shows how many currently indexed messages will be written. From the command
line, use the full session ID:

```bash
just archive personal 019fdbaf-c2ea-7e50-ae8f-8fa79e733904
# Equivalent:
docker compose exec api viewer archive \
  personal 019fdbaf-c2ea-7e50-ae8f-8fa79e733904
```

The result atomically overwrites `archives/<session-id>.jsonl`. A file contains
one versioned session header, ordered user/assistant Markdown messages, and a
final message count plus SHA-256 checksum. The archive adapter verifies that
footer before importing; a truncated or edited file fails loudly. Tool calls,
tool results, hidden reasoning, and injected context are intentionally absent,
because archives preserve the readable conversation rather than the vendor's
complete execution log.

After the first export, press **Rescan** (or run `just discover-source archive`),
then open and index the copy under the `archive` source. The original and the
archived copy remain separate because source ID is part of session identity.

## Give sessions custom titles

The viewer normally derives a title from the transcript. Click the pencil next
to the open session title to replace it directly. **Save** applies the title
immediately to the header and sidebar, Escape or **Cancel** discards the edit,
and **Reset** restores the title derived from the transcript.

Titles are stored atomically in the host file
`metadata/session_metadata.json`. Compose mounts only that metadata directory
writable at `/metadata`; `config/sources.toml` remains inside the separate
read-only `/config` mount. Consequently titles survive browser changes,
container recreation, and rebuilding the SQLite index.

The command-line helper edits the same file. Copy the complete session ID from
the session header and run:

```bash
./scripts/session_title.py set \
  019fdbaf-c2ea-7e50-ae8f-8fa79e733904 \
  "Codex frontend UI"
```

Click **Rescan** in the viewer after a command-line change. Browser edits update
the current catalog immediately and do not require a rescan.

List all custom titles:

```bash
./scripts/session_title.py list
```

Remove a custom title and return to the transcript-derived title:

```bash
./scripts/session_title.py remove \
  019fdbaf-c2ea-7e50-ae8f-8fa79e733904
```

The script updates `metadata/session_metadata.json` atomically. A different
metadata file can be selected by placing `--file PATH` before the command.

The underlying format is intentionally simple:

```json
{
  "019fdbaf-c2ea-7e50-ae8f-8fa79e733904": {
    "title": "Codex frontend UI",
    "hidden": true
  }
}
```

The JSON format remains deliberately simple. A title is scoped by session UUID,
so an original and archived copy with the same UUID receive the same custom
title. The eye action beside a session hides it from the normal sidebar without
deleting its transcript or index; the crossed-eye button in the sidebar opens
the hidden-session window and allows it to be restored. This preference is also
stored in the same metadata object as `"hidden": true` and therefore applies to
every source copy with that session UUID. Live message bookmarks and their
labels are stored in the current browser's local storage. They can also be
exported as durable snapshots from the viewer.

## Reading controls

- **Beginning** and **Latest** move to either end of the session.
- Enter the displayed message number in the **# / Go** control to jump directly
  to that message.
- The star in a message header adds or removes a bookmark.
- **Bookmarks** opens the saved-message list. Bookmark labels are generated
  from message text and can be edited in place.
- Select rendered text in a message or document to reveal a small **Annotate**
  action, then click it to open the note editor. Casual selections are harmless:
  the action disappears on outside click, Escape, or scrolling. The saved
  annotation records the exact quotation, surrounding text, and its Markdown
  source lines without changing the JSONL or `.md` file.
- **Annotations** lists notes for the current session or document. Selecting a
  note loads and expands its message when necessary, then jumps to and briefly
  emphasizes the annotated passage. Notes can be edited or deleted in place.
- **Export backup** atomically overwrites `bookmarks/<session-id>.json` with the
  current list. **Restore backup** confirms and then replaces the browser list
  directly; it does not scan or synchronize the transcript.
- **Fold**, **Collapse all**, and **Expand all** control long message bodies.
- **Archive** atomically exports the currently indexed conversation; it does
  not synchronize the source first.
- Messages with at least two headings have an **Outline** button. The outline is
  closed by default and provides quick jumps within that message.
- Rendered messages substantially taller than the viewport have a compact
  **Top of message** action at their bottom.
- The session ID, complete message Markdown, and every fenced code block have
dedicated copy buttons.

In document mode, **Beginning**, **End**, **Outline**, **Copy**, and **Reload**
operate on the complete Markdown file. **Top of document** is available at the
bottom of the page.

Press **Ctrl+F** or **Cmd+F** to search the complete indexed conversation—not
just the messages currently rendered on screen. Enter and Shift+Enter move
between matches, and Escape closes search.

Fold state, live bookmarks, bookmark labels, sidebar state, and Watch
preferences are stored in browser local storage. Bookmark backups are readable,
versioned JSON files in the gitignored `bookmarks/` directory. Annotations are
stored in SQLite so they are shared across browsers and survive session resyncs.
None of these mechanisms modifies transcript or Markdown source files.

## Markdown rendering

User messages, assistant messages, and standalone documents share the same
GitHub-flavored Markdown pipeline. The viewer supports headings, lists, tables,
task lists, blockquotes, links, inline code, fenced code, and raw HTML.
Recognized fenced-code languages receive syntax highlighting.

Headings receive message-scoped anchors, with a small `#` link visible only on
hover. Ordinary same-document Markdown links are resolved inside their own
message without conflicting with identically named headings elsewhere in the
conversation. This lets Codex refer naturally to another section of a long
answer:

```markdown
Implementation details are under [Architecture](#architecture).

## Architecture
...
```

The viewer's **Outline** control already provides a table of contents. These
anchors navigate the currently rendered message; durable links that reopen a
session at a specific heading are not yet part of the URL scheme.

The renderer also preserves Markdown AST line positions for annotations. For
ordinary prose it narrows a selection to the exact source lines when the
rendered quotation can be found in the Markdown; complex formatted selections
fall back to their containing Markdown blocks. The exact quotation and nearby
text are retained as additional anchors. If a standalone document changes, the
viewer first searches for that quotation and falls back to the recorded source
line when it can no longer be found.

A fenced block tagged `mermaid` is rendered as a Mermaid diagram:

````markdown
```mermaid
flowchart LR
    JSONL --> SQLite --> Browser
```
````

Use **Raw** in a diagram toolbar to switch between the rendered diagram and its
original Mermaid source. Invalid diagrams display their error and source instead
of disappearing. Generated SVG labels are not annotatable, but text selected in
the diagram's **Raw** source is.

When a diagram declares styled classes with `classDef`, the viewer adds a
compact legend beneath the rendered SVG. The class name is used as its label and
the badge reflects its `fill`, `stroke`, and `color` properties:

```mermaid
flowchart LR
    inside[Inside the system]:::boundary
classDef boundary fill:#fff2cc,stroke:#b38f00,color:#111;
```

The legend is derived without changing the Mermaid source or graph layout. It
is shown only in diagram mode and only when styled classes are present.

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
The session catalog and messages inside it are rebuildable indexes, but saved
annotations are user data and cannot be reconstructed from the JSONL
transcripts. Normal container rebuilds preserve the volume. Back it up before
deliberately deleting Docker volumes if annotations matter to you.

Conversation archives live in the writable directory selected by
`VIEWER_ARCHIVES_ROOT` (`./archives` by default). Unlike SQLite, these are
intended as durable, vendor-neutral conversation copies. Back that directory up
if the exports matter to you.

Standalone Markdown files remain solely in the read-only directory selected by
`VIEWER_DOCUMENTS_ROOT`. Only their contents currently displayed by the SPA are
kept in browser memory; neither their metadata nor content is stored in SQLite.

Session title metadata lives in the writable host directory selected by
`VIEWER_METADATA_ROOT` (`./metadata` by default). `just setup` moves an existing
`config/session_metadata.json` into this directory once, preserving titles from
older installations, and creates an empty metadata file for new installations.

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

Delete and rebuild all SQLite data only when intentionally starting over. This
also permanently deletes saved annotations:

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
every external path in `config/sources.toml` exists beneath `/sources` in the
container. The archive adapter should instead point to `/archives`.

### A session exists but has no messages

Select it and press **Index session**. The catalog and message index are
separate on purpose. Also remember that tool-only and metadata records are not
displayed as messages.

### Markdown documents do not appear

Switch to **Documents** and press its refresh icon. Check the resolved read-only
mount with `docker compose config`; `.md` files must be beneath the host path in
`VIEWER_DOCUMENTS_ROOT`. Files must be UTF-8 to open successfully.

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
./scripts/count_session_messages.py --adapter archive /path/to/archive.jsonl
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
GET  /api/documents
GET  /api/documents/{document_id}
GET  /api/documents/{document_id}/annotations
POST /api/documents/{document_id}/annotations
GET  /api/sessions
POST /api/sessions/discover
GET  /api/sessions/{source_id}/{session_id}
GET  /api/sessions/{source_id}/{session_id}/messages?start=0&limit=30
GET  /api/sessions/{source_id}/{session_id}/search?q=substring
GET  /api/sessions/{source_id}/{session_id}/annotations
POST /api/sessions/{source_id}/{session_id}/annotations
POST /api/sessions/{source_id}/{session_id}/sync
POST /api/sessions/{source_id}/{session_id}/archive
PUT  /api/sessions/{source_id}/{session_id}/title
DELETE /api/sessions/{source_id}/{session_id}/title
PUT  /api/sessions/{source_id}/{session_id}/visibility
PATCH /api/annotations/{annotation_id}
DELETE /api/annotations/{annotation_id}
```
