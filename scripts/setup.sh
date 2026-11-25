#!/usr/bin/env bash
# KrishiVaani - one-time local setup (Linux/macOS)
# Usage:  ./scripts/setup.sh [--skip-frontend]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --skip-frontend) SKIP_FRONTEND=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

echo "== KrishiVaani setup =="
echo "Project root: $ROOT"

PYTHON="${PYTHON:-python3}"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Creating virtual environment at .venv ..."
  "$PYTHON" -m venv .venv
fi

echo "Installing backend requirements ..."
"$ROOT/.venv/bin/python" -m pip install --upgrade pip --quiet
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"

if [ "$SKIP_FRONTEND" -eq 0 ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js/npm is required for the frontend build. Install Node.js 20+ or rerun with --skip-frontend." >&2
    exit 1
  fi
  echo "Installing frontend dependencies ..."
  (cd "$ROOT/frontend" && npm ci && echo "Building frontend ..." && npm run build)
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example (defaults need no API keys)."
else
  echo ".env already exists; leaving it unchanged."
fi

echo
echo "Setup complete."
echo "Start the app with:  ./scripts/start.sh"
echo "Open:                http://127.0.0.1:8000"
