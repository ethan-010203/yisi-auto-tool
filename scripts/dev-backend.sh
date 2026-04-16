#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR/black"

has_uvicorn() {
  local python_bin="$1"
  "$python_bin" -c "import uvicorn" >/dev/null 2>&1
}

if [[ -n "${YISI_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$YISI_PYTHON_BIN"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]] && has_uvicorn "$ROOT_DIR/.venv/bin/python"; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3.11 >/dev/null 2>&1 && has_uvicorn python3.11; then
  PYTHON_BIN="python3.11"
elif command -v python3 >/dev/null 2>&1 && has_uvicorn python3; then
  PYTHON_BIN="python3"
else
  echo "No usable Python with uvicorn found."
  echo "Install dependencies with: python3.11 -m pip install fastapi uvicorn pydantic pymupdf openai python-multipart"
  exit 1
fi

echo "Using Python: $PYTHON_BIN"
"$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port "${YISI_BACKEND_PORT:-8000}" --reload
