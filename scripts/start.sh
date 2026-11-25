#!/usr/bin/env bash
# KrishiVaani - production-style local start (Linux/macOS)
# Serves the built React app and the API from one FastAPI process.
# Usage:  ./scripts/start.sh [--port 8000] [--host 127.0.0.1] [--reload]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
RELOAD=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --reload) RELOAD=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Virtual environment not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "Warning: frontend/dist is missing. Run ./scripts/setup.sh or 'npm run build' in frontend/." >&2
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example."
fi

ARGS=(-m uvicorn app.main:app --app-dir backend --host "$HOST" --port "$PORT")
if [ "$RELOAD" -eq 1 ]; then
  ARGS+=(--reload)
fi

echo "Starting KrishiVaani on http://${HOST}:${PORT}"
echo "API docs: http://${HOST}:${PORT}/docs"
exec "$ROOT/.venv/bin/python" "${ARGS[@]}"
