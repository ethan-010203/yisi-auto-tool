#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PORT="${YISI_BACKEND_PORT:-8000}"
FRONTEND_PORT="${YISI_FRONTEND_PORT:-5173}"

stop_pid_file() {
  local label="$1"
  local pid_file="$2"

  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "$label stopped: PID $pid"
    fi
    rm -f "$pid_file"
  fi
}

stop_port_listener() {
  local label="$1"
  local port="$2"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"

  if [[ -n "$pids" ]]; then
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      echo "$label port listener stopped: PID $pid (port $port)"
    done <<< "$pids"
  fi
}

stop_pid_file "Backend" "$RUN_DIR/backend.pid"
stop_pid_file "Frontend" "$RUN_DIR/frontend.pid"
stop_port_listener "Backend" "$BACKEND_PORT"
stop_port_listener "Frontend" "$FRONTEND_PORT"
