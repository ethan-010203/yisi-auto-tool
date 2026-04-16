#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
mkdir -p "$RUN_DIR"
BACKEND_PORT="${YISI_BACKEND_PORT:-8000}"
FRONTEND_PORT="${YISI_FRONTEND_PORT:-5173}"

has_uvicorn() {
  local python_bin="$1"
  "$python_bin" -c "import uvicorn" >/dev/null 2>&1
}

pid_listening_on_port() {
  local port="$1"
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1
}

get_lan_ip() {
  local ip=""

  if command -v ipconfig >/dev/null 2>&1; then
    ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
    if [[ -z "$ip" ]]; then
      ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
    fi
  fi

  if [[ -z "$ip" ]] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi

  if [[ -z "$ip" ]] && command -v ifconfig >/dev/null 2>&1; then
    ip="$(ifconfig | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}')"
  fi

  echo "${ip:-localhost}"
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

BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
BACKEND_PID="$RUN_DIR/backend.pid"
FRONTEND_PID="$RUN_DIR/frontend.pid"
BACKEND_RELOAD_FLAG="${YISI_BACKEND_RELOAD_FLAG:-}"
LAN_HOST="$(get_lan_ip)"

echo "Using Python: $PYTHON_BIN"

if [[ -f "$BACKEND_PID" ]] && kill -0 "$(cat "$BACKEND_PID")" 2>/dev/null; then
  echo "Backend already running: PID $(cat "$BACKEND_PID")"
elif [[ -n "$(pid_listening_on_port "$BACKEND_PORT")" ]]; then
  echo "Backend already running on port $BACKEND_PORT: PID $(pid_listening_on_port "$BACKEND_PORT")"
else
  (
    cd "$ROOT_DIR/black"
    nohup "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" $BACKEND_RELOAD_FLAG >"$BACKEND_LOG" 2>&1 &
    echo $! >"$BACKEND_PID"
  )
  sleep 2
  if [[ -f "$BACKEND_PID" ]] && kill -0 "$(cat "$BACKEND_PID")" 2>/dev/null; then
    echo "Backend started. Log: $BACKEND_LOG"
  else
    echo "Backend failed to start. Log: $BACKEND_LOG"
    sed -n '1,120p' "$BACKEND_LOG" 2>/dev/null || true
    rm -f "$BACKEND_PID"
  fi
fi

if [[ -f "$FRONTEND_PID" ]] && kill -0 "$(cat "$FRONTEND_PID")" 2>/dev/null; then
  echo "Frontend already running: PID $(cat "$FRONTEND_PID")"
elif [[ -n "$(pid_listening_on_port "$FRONTEND_PORT")" ]]; then
  echo "Frontend already running on port $FRONTEND_PORT: PID $(pid_listening_on_port "$FRONTEND_PORT")"
else
  (
    cd "$ROOT_DIR/front"
    nohup npm run dev >"$FRONTEND_LOG" 2>&1 &
    echo $! >"$FRONTEND_PID"
  )
  sleep 2
  if [[ -f "$FRONTEND_PID" ]] && kill -0 "$(cat "$FRONTEND_PID")" 2>/dev/null; then
    echo "Frontend started. Log: $FRONTEND_LOG"
  else
    echo "Frontend failed to start. Log: $FRONTEND_LOG"
    sed -n '1,120p' "$FRONTEND_LOG" 2>/dev/null || true
    rm -f "$FRONTEND_PID"
  fi
fi

echo "Backend LAN:  http://$LAN_HOST:$BACKEND_PORT"
echo "Frontend LAN: http://$LAN_HOST:$FRONTEND_PORT"
