#!/usr/bin/env bash
# KrishiVaani - run the backend test suite (Linux/macOS)
# Usage:  ./scripts/test.sh [--eval]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_EVAL=0
for arg in "$@"; do
  case "$arg" in
    --eval) RUN_EVAL=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Virtual environment not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

echo "== Backend tests =="
(cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -m pytest)

if [ "$RUN_EVAL" -eq 1 ]; then
  echo
  echo "== Evaluation (writes docs/EVALUATION_REPORT.md) =="
  (cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -X utf8 -m app.evaluation)
fi

echo
echo "All backend tests passed."
