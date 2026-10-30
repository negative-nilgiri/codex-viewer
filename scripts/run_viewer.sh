#!/usr/bin/env bash
# Run the API and the web server until either one exits, then stop both.
# `just serve` runs this in the foreground and `just up` in the background;
# both export VIEWER_PORT, VIEWER_API_PORT and the VIEWER_* paths and build
# the frontend first.
set -eu
api=
web=
trap 'kill $api $web 2>/dev/null; wait' EXIT
trap 'exit' INT TERM HUP
uv run --project backend --frozen uvicorn session_viewer_backend.api:app \
    --host 127.0.0.1 --port "$VIEWER_API_PORT" &
api=$!
(cd frontend && exec node_modules/.bin/vite preview \
    --host 127.0.0.1 --port "$VIEWER_PORT" --strictPort) &
web=$!
# macOS bash 3.2 has no `wait -n`.
while kill -0 "$api" 2>/dev/null && kill -0 "$web" 2>/dev/null; do sleep 1; done
