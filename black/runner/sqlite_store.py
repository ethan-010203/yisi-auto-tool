from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

DB_DIR = Path(os.environ.get("YISI_DATA_DIR") or Path(__file__).parent.parent / "data")
DB_PATH = Path(os.environ.get("YISI_DB_PATH") or DB_DIR / "automation.sqlite3")

MAX_OUTPUT_CHARS = 12000
MAX_ERROR_CHARS = 4000

ACTIVE_STATUSES = {"queued", "running", "cancelling"}
RUNNING_STATUSES = {"running", "cancelling"}

_init_lock = threading.Lock()
_initialized = False


def _utcnow() -> str:
    return datetime.now().isoformat()


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def _parse_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _serialize_json(value: dict | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def _db_cursor(immediate: bool = False) -> Iterator[tuple[sqlite3.Connection, sqlite3.Cursor]]:
    connection = _connect()
    cursor = connection.cursor()
    try:
        if immediate:
            cursor.execute("BEGIN IMMEDIATE")
        yield connection, cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def init_db() -> None:
    global _initialized

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        with _db_cursor() as (_, cursor):
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    department TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    env_json TEXT NOT NULL DEFAULT '{}',
                    script_path TEXT NOT NULL,
                    output TEXT NOT NULL DEFAULT '',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    duration REAL NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    source_execution_id TEXT,
                    worker_id TEXT,
                    process_id INTEGER,
                    exit_code INTEGER
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_department_created "
                "ON executions(department, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_department_tool_created "
                "ON executions(department, tool, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_status_created "
                "ON executions(status, created_at ASC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_executions_updated "
                "ON executions(updated_at DESC)"
            )

        _initialized = True


def _execution_sort_timestamp(row: sqlite3.Row | dict) -> str:
    return row["started_at"] or row["created_at"]


def _execution_duration(row: sqlite3.Row | dict) -> float:
    status = row["status"]
    if status not in ACTIVE_STATUSES:
        return round(float(row["duration"] or 0), 2)

    reference = row["started_at"] if status in RUNNING_STATUSES else row["created_at"]
    try:
        reference_dt = datetime.fromisoformat(reference)
    except Exception:
        return round(float(row["duration"] or 0), 2)
    return round(max(0.0, time.time() - reference_dt.timestamp()), 1)


def _row_to_log(row: sqlite3.Row | dict, queue_positions: dict[str, int]) -> dict[str, Any]:
    log = {
        "id": row["id"],
        "timestamp": _execution_sort_timestamp(row),
        "department": row["department"],
        "tool": row["tool"],
        "config": _parse_json(row["config_json"]),
        "status": row["status"],
        "output": row["output"] or "",
        "error": row["error"],
        "duration": _execution_duration(row),
        "attempt": int(row["attempt"] or 1),
        "updatedAt": row["updated_at"],
    }
    if row["status"] == "queued" and row["id"] in queue_positions:
        log["queuePosition"] = queue_positions[row["id"]]
    return log


def _fetch_queue_positions(
    cursor: sqlite3.Cursor,
    *,
    department: str | None = None,
    tool: str | None = None,
) -> dict[str, int]:
    conditions = ["status = 'queued'"]
    params: list[Any] = []
    if department:
        conditions.append("department = ?")
        params.append(department)
    if tool:
        conditions.append("tool = ?")
        params.append(tool)

    query = (
        "SELECT id FROM executions WHERE " + " AND ".join(conditions) + " "
        "ORDER BY created_at ASC"
    )
    rows = cursor.execute(query, params).fetchall()
    return {row["id"]: index for index, row in enumerate(rows, start=1)}


def enqueue_execution(
    *,
    execution_id: str,
    department: str,
    tool: str,
    config: dict[str, Any] | None,
    env: dict[str, str] | None,
    script_path: str,
    source_execution_id: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    init_db()
    now = _utcnow()
    with _db_cursor() as (_, cursor):
        cursor.execute(
            """
            INSERT INTO executions (
                id,
                department,
                tool,
                status,
                config_json,
                env_json,
                script_path,
                created_at,
                updated_at,
                attempt,
                source_execution_id
            ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                department,
                tool,
                _serialize_json(config),
                _serialize_json(env),
                script_path,
                now,
                now,
                attempt,
                source_execution_id,
            ),
        )
        queue_positions = _fetch_queue_positions(cursor)
        return {
            "status": "queued",
            "queuePosition": queue_positions.get(execution_id),
        }


def get_execution(execution_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with _db_cursor() as (_, cursor):
        row = cursor.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        queue_positions = _fetch_queue_positions(cursor)
        return _row_to_log(row, queue_positions)


def _list_execution_rows(
    cursor: sqlite3.Cursor,
    *,
    limit: int,
    department: str | None = None,
    tool: str | None = None,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list[Any] = []
    if department:
        conditions.append("department = ?")
        params.append(department)
    if tool:
        conditions.append("tool = ?")
        params.append(tool)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT *
        FROM executions
        {where_clause}
        ORDER BY
            CASE WHEN status IN ('queued', 'running', 'cancelling') THEN 0 ELSE 1 END,
            COALESCE(started_at, created_at) DESC,
            created_at DESC
        LIMIT ?
    """
    return cursor.execute(query, (*params, limit)).fetchall()


def list_executions(
    *,
    limit: int = 20,
    department: str | None = None,
    tool: str | None = None,
) -> list[dict[str, Any]]:
    init_db()
    with _db_cursor() as (_, cursor):
        rows = _list_execution_rows(cursor, limit=limit, department=department, tool=tool)
        queue_positions = _fetch_queue_positions(cursor)
        return [_row_to_log(row, queue_positions) for row in rows]


def clear_department_logs(department: str) -> int:
    init_db()
    with _db_cursor() as (_, cursor):
        cursor.execute(
            "DELETE FROM executions WHERE department = ? AND status NOT IN ('queued', 'running', 'cancelling')",
            (department,),
        )
        return cursor.rowcount


def get_department_summary(department: str) -> dict[str, int]:
    return get_execution_summary(department=department)


def get_execution_summary(
    *,
    department: str | None = None,
    tool: str | None = None,
) -> dict[str, int]:
    init_db()
    with _db_cursor() as (_, cursor):
        conditions: list[str] = []
        params: list[Any] = []
        if department:
            conditions.append("department = ?")
            params.append(department)
        if tool:
            conditions.append("tool = ?")
            params.append(tool)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = cursor.execute(
            f"""
            SELECT status, COUNT(*) AS total
            FROM executions
            {where_clause}
            GROUP BY status
            """,
            params,
        ).fetchall()

    summary = {
        "queued": 0,
        "running": 0,
        "failed": 0,
        "success": 0,
        "terminated": 0,
        "cancelling": 0,
    }
    for row in rows:
        summary[row["status"]] = int(row["total"])
    return summary


def get_department_active_tools(department: str) -> list[str]:
    init_db()
    with _db_cursor() as (_, cursor):
        rows = cursor.execute(
            """
            SELECT DISTINCT tool
            FROM executions
            WHERE department = ? AND status IN ('queued', 'running', 'cancelling')
            ORDER BY tool ASC
            """,
            (department,),
        ).fetchall()
    return [row["tool"] for row in rows]


def get_latest_change_cursor(department: str | None = None) -> str:
    init_db()
    with _db_cursor() as (_, cursor):
        if department:
            row = cursor.execute(
                "SELECT COALESCE(MAX(updated_at), '') AS updated_at FROM executions WHERE department = ?",
                (department,),
            ).fetchone()
        else:
            row = cursor.execute(
                "SELECT COALESCE(MAX(updated_at), '') AS updated_at FROM executions"
            ).fetchone()
    return row["updated_at"] if row else ""


def request_cancel(execution_id: str) -> tuple[bool, Optional[str]]:
    init_db()
    now = _utcnow()
    with _db_cursor(immediate=True) as (_, cursor):
        row = cursor.execute("SELECT status FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return False, None

        status = row["status"]
        if status == "queued":
            cursor.execute(
                """
                UPDATE executions
                SET status = 'terminated',
                    cancel_requested = 1,
                    finished_at = ?,
                    updated_at = ?,
                    error = COALESCE(error, '任务已取消')
                WHERE id = ?
                """,
                (now, now, execution_id),
            )
            return True, "terminated"

        if status in RUNNING_STATUSES:
            next_status = "cancelling" if status == "running" else status
            cursor.execute(
                """
                UPDATE executions
                SET cancel_requested = 1,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (next_status, now, execution_id),
            )
            return True, next_status

        return False, status


def retry_execution(execution_id: str, new_execution_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with _db_cursor(immediate=True) as (_, cursor):
        row = cursor.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None

        now = _utcnow()
        attempt = int(row["attempt"] or 1) + 1
        cursor.execute(
            """
            INSERT INTO executions (
                id,
                department,
                tool,
                status,
                config_json,
                env_json,
                script_path,
                created_at,
                updated_at,
                attempt,
                source_execution_id
            ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_execution_id,
                row["department"],
                row["tool"],
                row["config_json"],
                row["env_json"],
                row["script_path"],
                now,
                now,
                attempt,
                execution_id,
            ),
        )
        queue_positions = _fetch_queue_positions(cursor)
        return {
            "status": "queued",
            "queuePosition": queue_positions.get(new_execution_id),
            "department": row["department"],
            "tool": row["tool"],
        }


def claim_next_execution(
    *,
    worker_id: str,
    global_limit: int,
    department_limit: int,
    tool_limit: int,
) -> Optional[dict[str, Any]]:
    init_db()
    now = _utcnow()
    with _db_cursor(immediate=True) as (_, cursor):
        running_rows = cursor.execute(
            "SELECT department, tool FROM executions WHERE status IN ('running', 'cancelling')"
        ).fetchall()
        if len(running_rows) >= global_limit:
            return None

        candidates = cursor.execute(
            "SELECT * FROM executions WHERE status = 'queued' ORDER BY created_at ASC"
        ).fetchall()

        for row in candidates:
            department_running = sum(1 for item in running_rows if item["department"] == row["department"])
            if department_running >= department_limit:
                continue

            tool_running = sum(
                1
                for item in running_rows
                if item["department"] == row["department"] and item["tool"] == row["tool"]
            )
            if tool_running >= tool_limit:
                continue

            cursor.execute(
                """
                UPDATE executions
                SET status = 'running',
                    started_at = ?,
                    updated_at = ?,
                    worker_id = ?,
                    cancel_requested = 0
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, worker_id, row["id"]),
            )
            if cursor.rowcount != 1:
                return None

            claimed = cursor.execute("SELECT * FROM executions WHERE id = ?", (row["id"],)).fetchone()
            return {
                "id": claimed["id"],
                "department": claimed["department"],
                "tool": claimed["tool"],
                "config": _parse_json(claimed["config_json"]),
                "env": _parse_json(claimed["env_json"]),
                "script_path": claimed["script_path"],
                "attempt": int(claimed["attempt"] or 1),
            }

    return None


def set_execution_process_info(execution_id: str, *, process_id: int | None) -> None:
    init_db()
    with _db_cursor() as (_, cursor):
        cursor.execute(
            "UPDATE executions SET process_id = ?, updated_at = ? WHERE id = ?",
            (process_id, _utcnow(), execution_id),
        )


def is_cancel_requested(execution_id: str) -> bool:
    init_db()
    with _db_cursor() as (_, cursor):
        row = cursor.execute(
            "SELECT cancel_requested FROM executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
    return bool(row and row["cancel_requested"])


def append_execution_output(execution_id: str, chunk: str, *, stream: str = "stdout") -> None:
    if not chunk:
        return

    init_db()
    with _db_cursor(immediate=True) as (_, cursor):
        row = cursor.execute(
            "SELECT output, error FROM executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
        if not row:
            return

        if stream == "stderr":
            new_error = _trim_text(f"{row['error'] or ''}{chunk}", MAX_ERROR_CHARS)
            cursor.execute(
                "UPDATE executions SET error = ?, updated_at = ? WHERE id = ?",
                (new_error, _utcnow(), execution_id),
            )
            return

        new_output = _trim_text(f"{row['output'] or ''}{chunk}", MAX_OUTPUT_CHARS)
        cursor.execute(
            "UPDATE executions SET output = ?, updated_at = ? WHERE id = ?",
            (new_output, _utcnow(), execution_id),
        )


def finalize_execution(
    execution_id: str,
    *,
    status: str,
    output: str,
    error: str | None,
    duration: float,
    exit_code: int | None = None,
) -> None:
    init_db()
    now = _utcnow()
    with _db_cursor() as (_, cursor):
        cursor.execute(
            """
            UPDATE executions
            SET status = ?,
                output = ?,
                error = ?,
                duration = ?,
                finished_at = ?,
                updated_at = ?,
                exit_code = ?,
                process_id = NULL
            WHERE id = ?
            """,
            (
                status,
                _trim_text(output or "", MAX_OUTPUT_CHARS),
                _trim_text(error, MAX_ERROR_CHARS) if error else None,
                round(duration, 2),
                now,
                now,
                exit_code,
                execution_id,
            ),
        )


def build_department_snapshot(department: str, *, limit: int = 20) -> dict[str, Any]:
    logs = list_executions(limit=limit, department=department)
    summary = get_department_summary(department)
    active_tools = get_department_active_tools(department)
    cursor = get_latest_change_cursor(department)
    return {
        "department": department,
        "logs": logs,
        "summary": summary,
        "activeToolIds": active_tools,
        "cursor": cursor,
    }


def build_global_snapshot(*, limit: int = 50) -> dict[str, Any]:
    logs = list_executions(limit=limit)
    summary = get_execution_summary()
    active_departments = sorted({log["department"] for log in logs if log["status"] in ACTIVE_STATUSES})
    cursor = get_latest_change_cursor()
    return {
        "logs": logs,
        "summary": summary,
        "activeDepartments": active_departments,
        "cursor": cursor,
    }


def get_execution_payload(execution_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with _db_cursor() as (_, cursor):
        row = cursor.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "department": row["department"],
            "tool": row["tool"],
            "config": _parse_json(row["config_json"]),
            "env": _parse_json(row["env_json"]),
            "script_path": row["script_path"],
            "status": row["status"],
            "attempt": int(row["attempt"] or 1),
        }


def healthcheck() -> dict[str, Any]:
    init_db()
    size_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {
        "dbPath": str(DB_PATH),
        "dbSizeBytes": size_bytes,
        "exists": os.path.exists(DB_PATH),
    }
