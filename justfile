set dotenv-load := true
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Browser port and API port; override either in .env.
export VIEWER_PORT := env_var_or_default("VIEWER_PORT", "41730")
export VIEWER_API_PORT := env_var_or_default("VIEWER_API_PORT", "41731")

# Backend settings. Recipes run from this directory, so relative paths start here.
export VIEWER_DATABASE := "data/viewer.sqlite3"
export VIEWER_SOURCES_FILE := "config/sources.toml"
export VIEWER_SESSION_METADATA_FILE := env_var_or_default("VIEWER_METADATA_ROOT", "metadata") / "session_metadata.json"
export VIEWER_BOOKMARKS_DIRECTORY := "bookmarks"
export VIEWER_ARCHIVES_DIRECTORY := env_var_or_default("VIEWER_ARCHIVES_ROOT", "archives")
export VIEWER_DOCUMENTS_DIRECTORY := env_var_or_default("VIEWER_DOCUMENTS_ROOT", "documents")

# The process started by serve and up. [r] keeps pgrep from matching a command line that contains this pattern.
viewer_process := "bash .*scripts/[r]un_viewer.sh"

# List the available commands.
default:
    @just --list

# Create missing local configuration and install frontend dependencies, without overwriting anything.
setup:
    #!/usr/bin/env bash
    set -eu
    if [[ ! -f .env ]]; then
        cp .env.example .env
        echo "Created .env."
    fi
    if [[ ! -f config/sources.toml ]]; then
        cp config/sources.example.toml config/sources.toml
        echo "Created config/sources.toml; set its source paths before starting."
    fi
    metadata_root="${VIEWER_METADATA_ROOT:-./metadata}"
    mkdir -p data bookmarks "$metadata_root" "${VIEWER_ARCHIVES_ROOT:-./archives}" "${VIEWER_DOCUMENTS_ROOT:-./documents}"
    if [[ ! -f "$metadata_root/session_metadata.json" ]]; then
        if [[ -f config/session_metadata.json ]]; then
            mv config/session_metadata.json "$metadata_root/session_metadata.json"
            echo "Migrated session titles to $metadata_root/session_metadata.json."
        else
            cp config/session_metadata.example.json "$metadata_root/session_metadata.json"
            echo "Created $metadata_root/session_metadata.json."
        fi
    fi
    if [[ ! -d frontend/node_modules ]]; then
        echo "Installing frontend dependencies..."
        npm --prefix frontend ci --silent
    fi

# Build the frontend into frontend/dist.
build:
    @npm --prefix frontend run build

# Build the frontend, then run the viewer in this terminal until Ctrl-C.
[no-exit-message]
serve: setup build
    @scripts/run_viewer.sh

# Build the frontend, then start the viewer in the background (log: data/viewer.log).
[no-exit-message]
up: setup
    #!/usr/bin/env bash
    set -eu
    if pgrep -f '{{viewer_process}}' >/dev/null; then
        echo "The viewer is already running. Use just restart to rebuild and restart it."
        exit 0
    fi
    echo "Building the frontend..."
    if ! npm --prefix frontend run build > data/viewer.log 2>&1; then
        tail -n 20 data/viewer.log >&2
        echo "The frontend build failed. The full output is in data/viewer.log." >&2
        exit 1
    fi
    nohup scripts/run_viewer.sh >> data/viewer.log 2>&1 &
    pid=$!
    healthy() { curl --fail --silent --output /dev/null "http://127.0.0.1:$VIEWER_PORT/api/health"; }
    # Wait up to a minute, but stop waiting as soon as the script exits (for example, a port is taken).
    for _ in $(seq 120); do
        if ! kill -0 "$pid" 2>/dev/null || healthy; then break; fi
        sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null && healthy; then
        echo "The viewer is up on http://127.0.0.1:$VIEWER_PORT"
        exit 0
    fi
    kill "$pid" 2>/dev/null || true
    tail -n 20 data/viewer.log >&2
    echo "The viewer didn't start. The full log is in data/viewer.log." >&2
    exit 1

# Stop the viewer, whether it was started by up or serve.
[no-exit-message]
down:
    #!/usr/bin/env bash
    set -eu
    if ! pkill -f '{{viewer_process}}'; then
        echo "The viewer isn't running."
        exit 0
    fi
    for _ in $(seq 50); do
        if ! pgrep -f '{{viewer_process}}' >/dev/null; then
            echo "The viewer is stopped."
            exit 0
        fi
        sleep 0.2
    done
    echo "The viewer didn't stop within 10 seconds. Still listening:" >&2
    lsof -nP -iTCP:"$VIEWER_PORT" -iTCP:"$VIEWER_API_PORT" -sTCP:LISTEN >&2 || true
    exit 1

# Rebuild the frontend and restart the viewer in the background.
restart: down up

# Follow the log of the viewer started by up.
logs:
    @tail -n 100 -f data/viewer.log

# Open the viewer in the default browser.
open:
    open "http://127.0.0.1:$VIEWER_PORT"

# Serve the running viewer to the tailnet over plain HTTP (the tailnet has no HTTPS certificates).
tailscale-serve: health
    @tailscale serve --bg --http=80 "$VIEWER_PORT"

# Check the HTTP health endpoint.
[no-exit-message]
health:
    @curl --fail --silent --output /dev/null "http://127.0.0.1:$VIEWER_PORT/api/health" || { echo "The viewer isn't answering on port $VIEWER_PORT. Start it with: just up" >&2; exit 1; }
    @echo "The viewer is up on http://127.0.0.1:$VIEWER_PORT"

alias status := health

# List configured source labels, adapters, paths, and whether each path exists.
sources:
    @uv run --project backend --frozen viewer sources

# Discover sessions from every configured source.
discover:
    @uv run --project backend --frozen viewer discover

# Discover sessions from one configured source.
discover-source source:
    @uv run --project backend --frozen viewer discover {{quote(source)}}

# Incrementally index one session (full UUID or unique prefix).
sync source session:
    @uv run --project backend --frozen viewer sync {{quote(source)}} {{quote(session)}}

# Export the currently indexed messages from one session to durable archive JSONL.
archive source session:
    @uv run --project backend --frozen viewer archive {{quote(source)}} {{quote(session)}}

# Run all focused backend and frontend checks.
test: test-backend test-frontend

# Run the backend tests.
test-backend:
    @cd backend && uv run --frozen --group dev pytest -q

# Run frontend lint and the production build.
test-frontend:
    @npm --prefix frontend run lint
    @npm --prefix frontend run build

# List custom session titles.
title-list:
    ./scripts/session_title.py list

# Set a custom title: just title-set SESSION_ID "Readable title"
title-set session title:
    ./scripts/session_title.py set {{quote(session)}} {{quote(title)}}

# Remove a custom title.
title-remove session:
    ./scripts/session_title.py remove {{quote(session)}}

# Count visible messages in a JSONL transcript using automatic format detection.
count transcript:
    ./scripts/count_session_messages.py {{quote(transcript)}}

# Count visible messages using an explicit archive, codex, or claude adapter.
count-as adapter transcript:
    ./scripts/count_session_messages.py --adapter {{quote(adapter)}} {{quote(transcript)}}
