set dotenv-load := true
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# List the available commands.
default:
    @just --list

# Create missing local configuration without overwriting existing files.
setup:
    #!/usr/bin/env bash
    set -eu
    if [[ ! -f .env ]]; then
        cp .env.example .env
        echo "Created .env; set VIEWER_SOURCES_ROOT before starting the viewer."
    fi
    if [[ ! -f config/sources.toml ]]; then
        cp config/sources.example.toml config/sources.toml
        echo "Created config/sources.toml; configure its source paths before starting."
    fi
    mkdir -p bookmarks "${VIEWER_ARCHIVES_ROOT:-./archives}" "${VIEWER_DOCUMENTS_ROOT:-./documents}"

# Build images and start the viewer in the background.
up: setup
    docker compose up --build -d

# Start existing images without rebuilding them.
start: setup
    docker compose up -d

# Build the application images without starting them.
build:
    docker compose build api web

# Restart the running containers without rebuilding them.
restart:
    docker compose restart api web

# Stop containers while preserving the SQLite volume and bookmark files.
down:
    docker compose down

# Show container status.
status:
    docker compose ps

# Check the HTTP health endpoint.
health:
    curl --fail --silent --show-error "http://localhost:${VIEWER_PORT:-8080}/api/health"
    @echo

# Follow API and web logs.
logs:
    docker compose logs --tail=100 -f api web

# Follow only API logs.
logs-api:
    docker compose logs --tail=100 -f api

# Follow only Caddy/web logs.
logs-web:
    docker compose logs --tail=100 -f web

# Print the fully resolved Compose configuration and mounts.
config:
    docker compose config

# List configured source labels, adapters, paths, and mount availability.
sources:
    docker compose exec api viewer sources

# Discover sessions from every configured source.
discover:
    docker compose exec api viewer discover

# Discover sessions from one configured source.
discover-source source:
    docker compose exec api viewer discover {{quote(source)}}

# Incrementally index one session (full UUID or unique prefix).
sync source session:
    docker compose exec api viewer sync {{quote(source)}} {{quote(session)}}

# Export the currently indexed messages from one session to durable archive JSONL.
archive source session:
    docker compose exec api viewer archive {{quote(source)}} {{quote(session)}}

# Run all focused backend and frontend checks.
test: test-backend test-frontend

# Run backend tests in the uv-based test container.
test-backend:
    docker compose --profile test run --rm --build backend-tests

# Run frontend lint and the production build in its test container.
test-frontend:
    docker compose --profile test run --rm --build frontend-check

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
