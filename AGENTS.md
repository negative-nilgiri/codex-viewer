# Agent guide

Read [docs/REPOSITORY_MAP.md](docs/REPOSITORY_MAP.md) first. It maps every
module, route, table, and storage location, and has a "task → where to look"
table. Keep it updated when you change the structure.

## What this is

A local, single-user viewer for Codex and Claude Code JSONL session transcripts
and Markdown files. FastAPI + SQLite backend (`backend/`), React + Vite
frontend (`frontend/`), run natively with `just` (uvicorn plus `vite preview`).

## Rules that are easy to break

- Never write to transcript or Markdown source files. The app only reads them; they are the source of truth.
- Annotations in SQLite cannot be rebuilt from transcripts. Do not drop or recreate the `annotations` table, and do not delete `data/viewer.sqlite3` as a cleanup step.
- Only newline-terminated JSONL lines are processed. Keep sync offsets advancing only past complete lines.
- In the code, `profile` means source id. `message_index` is 1-based; Virtuoso indexes are 0-based.
- Changing an API response shape means updating `backend/src/session_viewer_backend/api.py`, `frontend/src/api.ts`, and the tests together.
- Schema changes need a `SCHEMA_VERSION` bump and a migration branch in `database.py`.
- Raw HTML in Markdown is intentionally unsanitized because the app is for trusted local use. Do not expose it publicly or "fix" this without asking.
- New Markdown element components in `MarkdownRenderer.tsx` must stamp `data-source-*-line` attributes (`sourcePosition(node)`), or annotations inside them lose line information.

## Commands

```bash
# Backend tests (Python 3.14, uv)
cd backend && uv run --group dev pytest

# Frontend checks
cd frontend && npm ci && npm run lint && npm run build

# Both
just test

# Run the app in the background at http://127.0.0.1:41730 (ports: VIEWER_PORT, VIEWER_API_PORT)
just setup && just up      # stop with just down; logs in data/viewer.log

# Or in this terminal until Ctrl-C
just serve
```

`vite.config.ts` proxies `/api` to `127.0.0.1:$VIEWER_API_PORT` in both `vite` and `vite preview`; the justfile exports it.
There are no frontend unit tests, so lint and the build are the frontend check.
After changing frontend code, verify the UI in the running app, not only the build.

## Conventions

- Match the surrounding code. Backend: plain functions and dataclasses, standard-library `sqlite3`, no ORM. Frontend: TypeScript, single quotes, no semicolons, plain CSS in `App.css`.
- Add or update a backend test for backend behavior changes. Existing tests build tiny JSONL transcripts in `tmp_path`; copy that pattern.
- Update `README.md` when user-visible behavior, configuration, or the HTTP API list changes.
- Do not commit `.env`, `config/sources.toml`, or anything under `data/`, `metadata/`, `bookmarks/`, `archives/`, or `documents/` (they are gitignored runtime data).
- Naming still says "codex" in places (`localStorage` keys, page title). That is legacy, not a design. Do not rename `localStorage` keys casually: it would orphan users' saved bookmarks and fold state.
