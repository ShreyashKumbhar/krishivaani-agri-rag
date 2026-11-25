#!/usr/bin/env bash
# KrishiVaani - development mode (Linux/macOS)
# Starts the FastAPI backend with reload and the Vite dev server.
# Usage:  ./scripts/start-dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Virtual environment not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
fi

echo "Starting API on http://127.0.0.1:${API_PORT} (reload) ..."
"$ROOT/.venv/bin/python" -m uvicorn app.main:app \
  --app-dir backend --reload --host 127.0.0.1 --port "$API_PORT" &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT

echo "Starting Vite on http://127.0.0.1:${WEB_PORT} ..."
cd "$ROOT/frontend"
npm run dev -- --port "$WEB_PORT"
