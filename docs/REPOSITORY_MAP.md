# Repository map

Start here. This file tells you where things live, how data moves, and which
files to touch for common tasks. It describes structure, not behavior in depth:
for setup and user-facing behavior read the root `README.md`.

If you change the structure (add, move, or delete a module, endpoint, table, or
storage location), update this file in the same change.

## What this project is

A local, single-user web app that reads Codex and Claude Code JSONL session
transcripts (and standalone Markdown files) and renders them as Markdown.

```text
transcripts (read-only JSONL) ──► FastAPI ──► SQLite index ──► React (virtualized)
                                     ▲                              │
Markdown documents (read-only) ──────┘                   Caddy serves the build
                                                         and proxies /api/*
```

- Backend: Python 3.14, FastAPI, standard-library `sqlite3`, managed with `uv`.
- Frontend: React 19 + TypeScript + Vite (React Compiler enabled), `react-virtuoso`.
- Runtime: Docker Compose (`api` = backend, `web` = Caddy + built frontend).

## Vocabulary (the code is inconsistent, so read this)

| Term | Meaning |
| --- | --- |
| **source** | One entry in `config/sources.toml`: `id`, `adapter`, container `path`. |
| **profile** | The code's name for a source id. In the DB, API paths, and `api.ts`, `profile` == source id. |
| **session** | One conversation, identified by `(profile, session_id)`. Session IDs are lowercased UUIDs. |
| **adapter** | Parser for one JSONL format: `codex`, `claude`, or `archive`. |
| **discover** | Cheap catalog pass. Reads only a 256 KB prefix per file; imports no messages. |
| **sync / index** | Import visible messages into SQLite, incrementally by byte offset. |
| **archive** | Explicit export of indexed messages to a checksummed JSONL in `archives/`. |
| **document** | A `.md` file read straight from disk. Never stored in SQLite. |
| **annotation** | A note attached to a quoted passage of a message or document. Stored in SQLite. |
| **bookmark** | A starred message. Lives in browser `localStorage`; optional JSON backup on disk. |
| **"codex"** | Legacy project name. Still appears in the compose project name, `localStorage` keys (`codex-sessions-viewer:*`), the API title, and the page title. Not a feature flag. |

## Top-level layout

```text
.
├── README.md                 User docs: setup, mounts, features, HTTP API list
├── compose.yaml              Services: api, web; profile "test": backend-tests, frontend-check
├── justfile                  Command shortcuts (just setup / up / test / sync / archive / ...)
├── .env.example              VIEWER_* host settings (copy to .env, gitignored)
├── config/
│   ├── sources.example.toml  Copy to config/sources.toml (gitignored)
│   └── session_metadata.example.json
├── backend/                  FastAPI app, CLI, tests   (see "Backend")
├── frontend/                 React SPA                 (see "Frontend")
├── server/                   Caddyfile + Dockerfile that bakes the frontend build into Caddy
├── scripts/                  Host-side helpers: session_title.py, count_session_messages.py
├── docs/                     This map
├── metadata/                 Writable: session_metadata.json (titles, hidden)   (contents gitignored)
├── bookmarks/                Writable: bookmark backups                          (gitignored)
├── archives/                 Writable: archive JSONL exports                     (gitignored)
├── documents/                Read-only Markdown documents                        (contents gitignored)
└── lessons/                  Untracked generated lesson material; not part of the app
```

Local runtime data directories (`metadata/`, `bookmarks/`, `archives/`,
`documents/`) are bind-mounted into the `api` container; see `compose.yaml`.

## Backend

Package: `backend/src/session_viewer_backend/`. Entry points: `api.py` (`app`,
served by uvicorn) and `cli.py` (`viewer` command, also `python -m session_viewer_backend`).

| File | Responsibility |
| --- | --- |
| `api.py` | All HTTP routes and request models, built in `create_app(settings)`. Thin: validates input, calls the modules below, maps errors to `HTTPException`. |
| `config.py` | `Settings` dataclass loaded from `VIEWER_*` environment variables. |
| `sources.py` | Parses and validates `sources.toml` into `SourceDefinition`s. Defines the supported adapter names. |
| `discovery.py` | Scans a source tree, asks the adapter to inspect each file, upserts the `sessions` catalog. Handles missing files (`source_present`) and stale path repair. |
| `sync.py` | Incremental indexing of one session into `messages`. Detects truncation or replacement and rebuilds that session. |
| `rollout.py` | Low-level JSONL reader (`iter_complete_lines`, `read_prefix_events`). Skips a trailing partial line. |
| `adapters/` | Per-format parsing. `base.py` is the protocol; `codex.py`, `claude.py`, `archive.py` implement it; `__init__.py` is the registry. |
| `database.py` | SQLite schema (`SCHEMA`), `connect`, `initialize`, schema-version migration. |
| `repository.py` | Read queries for sessions, message pages, search; title override update. |
| `annotations.py` | Create, list, edit, delete annotations (message and document). |
| `markdown_source.py` | Pure helpers: line splitting that matches Markdown parsers, the heading chain and open code fence at a line (`scan_context`; ATX and setext headings), and `source_snapshot` (annotated source lines, headings, fence language). No database access. |
| `archive.py` | Export indexed messages to the archive JSONL format (header, messages, SHA-256 footer). |
| `bookmarks.py` | Read and write bookmark backup JSON files. |
| `documents.py` | Lists and loads Markdown documents; base64url document IDs; path-escape protection. |
| `session_metadata.py` | Atomic read/write of `session_metadata.json` (custom titles, hidden flag). |
| `formatting.py` | `normalized_title` (whitespace, `#` prefix, shortening). |

### Request flow for the core path

1. `POST /api/sessions/discover` → `discovery.discover_sessions` → `sessions` rows (no messages).
2. `POST /api/sessions/{profile}/{session_id}/sync` → `sync.sync_session` → `messages` rows.
3. `GET .../messages?start=&limit=` → `repository.get_messages` (`message_index > start`, so `start` is a count, not a zero-based offset).
4. `GET .../search?q=` → `repository.search_messages` (case-insensitive substring, returns message indexes).

### HTTP routes (all in `api.py`)

| Area | Routes |
| --- | --- |
| Health | `GET /api/health` |
| Sessions | `GET /api/sessions`, `POST /api/sessions/discover`, `GET /api/sessions/{profile}/{id}` |
| Messages | `GET .../messages`, `GET .../search` |
| Sync / archive | `POST .../sync`, `POST .../archive` |
| Title / visibility | `PUT`/`DELETE .../title`, `PUT .../visibility` |
| Bookmark backup | `PUT`/`GET .../bookmarks` |
| Annotations | `GET`/`POST .../annotations` (sessions and documents), `PATCH`/`DELETE /api/annotations/{id}` |
| Documents | `GET /api/documents`, `GET /api/documents/{document_id}` (ETag, `text/markdown`) |

The frontend's matching client functions are all in `frontend/src/api.ts`.

### SQLite schema (`database.py`, `SCHEMA_VERSION = 6`)

- `sessions` — PK `(profile, session_id)`; offsets and file identity for incremental sync; `title`, `title_override`, `source_present`.
- `messages` — PK `(profile, session_id, message_index)`; `message_index` is 1-based; FK to `sessions` with cascade delete.
- `annotations` — `target_type` is `'message'` or `'document'` (a CHECK enforces which columns are set). **No foreign key to `messages`**, so annotations survive resyncs and rebuilds.
  - `source_text` / `source_context` / `source_fence` snapshot the annotated Markdown lines, the heading lines above them, and the fenced-code language when the passage starts inside a fence, all taken when the annotation is created (NULL = saved before that column existed). The list endpoints fill legacy rows in memory, without storing, only while `content_hash` still matches the current Markdown.
- Migrations live inline in `database.initialize`. Adding a column means updating `SCHEMA`, bumping `SCHEMA_VERSION`, and adding an upgrade branch there.

### Adapters

An adapter implements `accepts_path`, `inspect`, `event_metadata`,
`event_timestamp`, and `visible_message` (see `adapters/base.py`). `visible_message`
is where "what counts as a message" is decided. `archive` additionally has
`validate`, which `sync.py` calls before importing.

To add a new transcript format:
1. Add `adapters/<name>.py` implementing the protocol.
2. Register it in `adapters/__init__.py`.
3. Add the name to `SUPPORTED_ADAPTERS` in `sources.py`.
4. Add it to `detect_adapter` in `scripts/count_session_messages.py`.
5. Add a test modeled on `tests/test_claude.py`.

## Frontend

All source is in `frontend/src/`. There is no router and no state library;
state is React `useState` plus `localStorage`.

| File | Responsibility |
| --- | --- |
| `main.tsx` | Mounts `<App />`. |
| `App.tsx` | Largest file. Contains `Transcript` (header controls, virtualized message list, block loading and cache, search, bookmarks, folding, Watch polling, title editing) and `App` (sidebar, Sessions/Documents mode, hidden-sessions dialog). |
| `MessageCard.tsx` | One message: header actions, outline, fold, back-to-top. |
| `DocumentViewer.tsx` | A whole Markdown document as one page, with outline, annotations, reload. |
| `api.ts` | Types for every API payload plus `fetch` wrappers. Keep in sync with `api.py` response shapes. |
| `markdown.ts` | Heading extraction, slugs, scoped heading IDs, scroll helpers. |
| `rehypeDisplayMathPosition.ts` | Rehype plugin (between `rehype-raw` and `rehype-katex`) that wraps display math in a `data-source-*-line` element, because rehype-katex drops the source position and the equation could not be annotated. |
| `components/MarkdownRenderer.tsx` | The shared Markdown pipeline (remark-gfm, remark-math, rehype-raw, rehype-katex, rehype-highlight), custom element components that stamp `data-source-start-line` / `data-source-end-line`, and `MarkdownOutline`. |
| `components/AnnotationSurface.tsx` | Text selection capture, line refinement, annotation anchoring and highlighting (CSS Custom Highlight API), floating Annotate button and editor. |
| `components/AnnotationsPanel.tsx` | The Annotations toggle button and side panel: grouped list, selection (per item, per message group, or all), jump, edit, delete (single, or Delete selected with one confirmation), and the copy buttons. |
| `annotationCopy.ts` | Pure functions that turn an annotation into the Markdown that is copied (label, headings, quote, note). The panel renders the same parts, so what you see is what is copied. |
| `components/MermaidDiagram.tsx` | Lazy-loaded Mermaid rendering, Raw toggle, legend built from `classDef`. |
| `components/CopyButton.tsx` | Clipboard copy with fallback. |
| `App.css`, `index.css` | All styling (plain CSS, no framework). |

Notes that matter when editing:
- Virtuoso indexes are 0-based; `message_index` from the API is 1-based. Conversions happen throughout `Transcript` (`index + 1`, `messageIndex - 1`).
- Messages are fetched in blocks of 30 (`BLOCK_SIZE`); at most 7 blocks stay cached (`MAX_CACHED_BLOCKS`).
- Annotation anchoring depends on the `data-source-*-line` attributes added in `MarkdownRenderer.tsx`. A new Markdown element component should call `sourcePosition(node)` or annotations inside it will lose line information.
- `vite.config.ts` has no dev-server proxy, so `npm run dev` does not reach `/api` by itself. The supported full-stack path is Docker Compose.

## Where state lives

| State | Location | Rebuildable from transcripts? |
| --- | --- | --- |
| Catalog and messages | SQLite (Docker volume `viewer-data`, `/data/viewer.sqlite3`) | Yes |
| **Annotations** | SQLite, same file | **No. Back up before deleting the volume.** |
| Custom titles, hidden flag | `metadata/session_metadata.json`, keyed by session UUID | n/a |
| Bookmarks, folds, watch, sidebar, view mode | Browser `localStorage` | n/a |
| Bookmark backups | `bookmarks/<session-id>.json` | n/a |
| Archives | `archives/<session-id>.jsonl` | n/a |
| Transcripts, Markdown documents | Host directories, mounted read-only | Source of truth; never written |

Titles and the hidden flag are scoped by session UUID, not by source, so every
source copy of a session (original and archive) shares them.

## Invariants to preserve

- The app never writes to transcript or Markdown source files.
- Only complete (newline-terminated) JSONL lines are processed; the sync offset only advances past complete lines.
- Only user and assistant text is indexed. Tool calls, tool results, reasoning, and injected context are excluded by adapters.
- File writes for metadata, bookmarks, and archives are atomic (temp file + `os.replace`).
- Document IDs are validated and resolved under the configured root; escaping it must keep failing.
- Raw HTML in Markdown is intentionally unsanitized (trusted local use, Caddy bound to `127.0.0.1`). Do not expose the app publicly.

## Task → where to look

| I want to... | Start in |
| --- | --- |
| Change which records become messages | `backend/src/session_viewer_backend/adapters/<format>.py` → `visible_message` |
| Change how sessions are found or titled | `discovery.py`, adapter `inspect`, `formatting.py` |
| Change incremental sync or rebuild behavior | `sync.py`, `rollout.py` |
| Add or change an API endpoint | `api.py`, then `frontend/src/api.ts`, then a test in `backend/tests/test_api.py` |
| Change the database schema | `database.py` (schema, version, migration) |
| Change annotation storage or validation | `annotations.py`, `api.py` models, `database.py` |
| Change what an annotation copies as | `annotationCopy.ts` (and the snapshot columns in `markdown_source.py`) |
| Change annotation anchoring or UI | `components/AnnotationSurface.tsx`, `components/AnnotationsPanel.tsx` |
| Change Markdown rendering (math, code, tables, links) | `components/MarkdownRenderer.tsx`, `markdown.ts` |
| Change Mermaid behavior | `components/MermaidDiagram.tsx` |
| Change the transcript view, search, bookmarks, Watch | `Transcript` in `App.tsx` |
| Change the sidebar, session grouping, hidden sessions | `App` in `App.tsx` |
| Change document listing or loading | `documents.py`, `DocumentViewer.tsx` |
| Change archive format | `archive.py` and `adapters/archive.py` together (header, footer, checksum must agree) |
| Change mounts, ports, or environment | `compose.yaml`, `.env.example`, `backend/Dockerfile`, `config.py` |
| Change reverse proxy or static serving | `server/Caddyfile`, `server/Dockerfile` |
| Add a CLI command | `cli.py` (and a `justfile` recipe) |
| Style something | `frontend/src/App.css` |

## Tests and commands

Backend tests are in `backend/tests/` (pytest, `httpx` test client, temp-dir
fixtures that build tiny JSONL transcripts):

| File | Covers |
| --- | --- |
| `test_api.py` | Routes: pagination, search, titles, hide/restore, bookmark backup, archive, documents, annotations |
| `test_sync.py` | Incremental sync, partial lines, truncation rebuild, same UUID in two sources, ambiguous prefix |
| `test_discovery.py` | Shallow idempotent discovery, stale path repair, metadata parsing, schema migration |
| `test_claude.py` | Claude adapter filtering and incremental sync |
| `test_archive.py` | Archive round trip and tamper detection |

The frontend has no unit tests. Its check is lint plus the TypeScript/Vite build.

```bash
# Backend (needs Python 3.14 and uv)
cd backend && uv run --group dev pytest

# Frontend
cd frontend && npm ci && npm run lint && npm run build

# Everything in Docker (no host toolchain needed)
just test          # or: docker compose --profile test run --rm --build backend-tests / frontend-check

# Run the app
just setup && just up      # then open http://localhost:8080
```

Useful diagnostics: `just count /path/to/session.jsonl` prints the message
count the adapter would produce, to compare against SQLite after a sync.
