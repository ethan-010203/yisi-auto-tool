#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  exec "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/black/worker.py"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$PROJECT_ROOT/black/worker.py"
fi

exec python "$PROJECT_ROOT/black/worker.py"
