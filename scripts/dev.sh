#!/bin/bash
set -Eeuo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR" && git rev-parse --show-toplevel )"

cd "$REPO_DIR"

# Run the FastAPI dev server with auto-reload.
# --reload restarts on Python changes; --reload-include '*.html' also picks up
# template edits. HOST/PORT are overridable via env vars; extra args are
# forwarded straight to uvicorn.
exec uv run uvicorn app.main:app \
    --reload \
    --reload-include '*.html' \
    --host "${HOST:-127.0.0.1}" \
    --port "${PORT:-5555}" \
    "$@"
