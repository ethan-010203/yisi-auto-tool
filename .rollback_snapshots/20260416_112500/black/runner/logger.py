"""执行日志记录模块 - 按部门独立存储。"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

MAX_LOG_ENTRIES = 100
MAX_OUTPUT_CHARS = 12000
MAX_ERROR_CHARS = 4000

# 活跃任务跟踪 {log_id: {...}}
_active_processes: Dict[str, Dict[str, Any]] = {}
_processes_lock = threading.Lock()


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def _isoformat(value: datetime) -> str:
    return value.isoformat()


def _get_log_file(department: str) -> Path:
    """获取部门的日志文件路径。"""
    return LOGS_DIR / f"{department.lower()}.json"


def _read_department_logs(department: str) -> List[Dict[str, Any]]:
    """读取指定部门的日志文件。"""
    log_file = _get_log_file(department)
    if not log_file.exists():
        return []

    try:
        with open(log_file, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, IOError):
        return []


def _write_department_logs(department: str, logs: List[Dict[str, Any]]) -> None:
    """写入指定部门的日志文件。"""
    log_file = _get_log_file(department)
    with open(log_file, "w", encoding="utf-8") as file:
        json.dump(logs, file, ensure_ascii=False, indent=2)


def _build_log_entry(
    *,
    log_id: str,
    timestamp: str,
    department: str,
    tool: str,
    config: Optional[Dict[str, Any]],
    status: str,
    output: str = "",
    error: Optional[str] = None,
    duration: float = 0.0,
    queue_position: Optional[int] = None,
) -> Dict[str, Any]:
    entry = {
        "id": log_id,
        "timestamp": timestamp,
        "department": department,
        "tool": tool,
        "config": config or {},
        "status": status,
        "output": _trim_text(output, MAX_OUTPUT_CHARS) if output else "",
        "error": _trim_text(error, MAX_ERROR_CHARS) if error else None,
        "duration": round(duration, 2),
    }

    if queue_position is not None:
        entry["queuePosition"] = queue_position

    return entry


def _upsert_log_entry(department: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    logs = _read_department_logs(department)
    for index, existing in enumerate(logs):
        if existing.get("id") == entry["id"]:
            logs[index] = entry
            break
    else:
        logs.insert(0, entry)

    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[:MAX_LOG_ENTRIES]

    _write_department_logs(department, logs)
    return entry


def register_queued_job(
    log_id: str,
    department: str,
    tool: str,
    config: Optional[Dict[str, Any]],
    queue_position: Optional[int] = None,
    created_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """注册排队中的任务。"""
    created_at = created_time or datetime.now()

    with _processes_lock:
        _active_processes[log_id] = {
            "process": None,
            "created_time": created_at,
            "start_time": None,
            "department": department,
            "tool": tool,
            "config": config or {},
            "manual_terminated": False,
            "output": "",
            "error": "",
            "status": "queued",
            "queue_position": queue_position,
        }

    entry = _build_log_entry(
        log_id=log_id,
        timestamp=_isoformat(created_at),
        department=department,
        tool=tool,
        config=config,
        status="queued",
        queue_position=queue_position,
    )
    return _upsert_log_entry(department, entry)


def update_queue_positions(positions: Dict[str, int]) -> None:
    """批量更新排队任务的队列位置。"""
    if not positions:
        return

    touched_departments: set[str] = set()

    with _processes_lock:
        for log_id, position in positions.items():
            info = _active_processes.get(log_id)
            if not info or info.get("status") != "queued":
                continue
            info["queue_position"] = position
            touched_departments.add(info["department"])

    for department in touched_departments:
        logs = _read_department_logs(department)
        changed = False
        for log in logs:
            log_id = log.get("id")
            if log_id in positions and log.get("status") == "queued":
                log["queuePosition"] = positions[log_id]
                changed = True
        if changed:
            _write_department_logs(department, logs)


def register_active_process(
    log_id: str,
    process: Any,
    department: str,
    tool: str,
    start_time: Optional[datetime] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """注册正在运行的进程。"""
    started_at = start_time or datetime.now()

    with _processes_lock:
        existing = _active_processes.get(log_id, {})
        created_at = existing.get("created_time") or started_at
        _active_processes[log_id] = {
            "process": process,
            "created_time": created_at,
            "start_time": started_at,
            "department": department,
            "tool": tool,
            "config": config or existing.get("config") or {},
            "manual_terminated": existing.get("manual_terminated", False),
            "output": existing.get("output", ""),
            "error": existing.get("error", ""),
            "status": "running",
            "queue_position": None,
        }

    entry = _build_log_entry(
        log_id=log_id,
        timestamp=_isoformat(started_at),
        department=department,
        tool=tool,
        config=config or existing.get("config"),
        status="running",
    )
    _upsert_log_entry(department, entry)


def terminate_process(log_id: str) -> bool:
    """终止正在运行的任务。"""
    with _processes_lock:
        if log_id not in _active_processes:
            return False

        proc_info = _active_processes[log_id]
        process = proc_info.get("process")
        proc_info["manual_terminated"] = True

        if process is None:
            return False

        try:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
                process.wait()
            return True
        except Exception:
            return False


def append_process_output(log_id: str, chunk: str, stream: str = "stdout") -> None:
    """向运行中任务追加实时输出。"""
    if not chunk:
        return

    with _processes_lock:
        proc_info = _active_processes.get(log_id)
        if not proc_info:
            return

        key = "error" if stream == "stderr" else "output"
        limit = MAX_ERROR_CHARS if key == "error" else MAX_OUTPUT_CHARS
        proc_info[key] = _trim_text(f"{proc_info.get(key, '')}{chunk}", limit)


def get_active_processes(department: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取活跃任务列表。"""
    with _processes_lock:
        processes = []
        for log_id, info in _active_processes.items():
            if department is not None and info["department"] != department:
                continue

            status = info.get("status", "running")
            reference_time = info.get("start_time") if status == "running" else info.get("created_time")
            if reference_time is None:
                reference_time = datetime.now()

            duration = max(0.0, time.time() - reference_time.timestamp())
            entry = {
                "id": log_id,
                "department": info["department"],
                "tool": info["tool"],
                "duration": round(duration, 1),
                "status": status,
                "timestamp": _isoformat(reference_time),
                "manual_terminated": info.get("manual_terminated", False),
                "output": info.get("output", ""),
                "error": info.get("error", ""),
                "config": info.get("config", {}),
            }

            if info.get("queue_position") is not None:
                entry["queuePosition"] = info["queue_position"]

            processes.append(entry)

        return processes


def unregister_process(log_id: str) -> None:
    """注销任务。"""
    with _processes_lock:
        _active_processes.pop(log_id, None)


def is_manual_terminated(log_id: str) -> bool:
    """检查进程是否被用户手动终止。"""
    with _processes_lock:
        if log_id in _active_processes:
            return _active_processes[log_id].get("manual_terminated", False)
        return False


def log_execution(
    department: str,
    tool: str,
    config: Optional[Dict[str, Any]],
    status: str,
    output: str,
    error: Optional[str] = None,
    duration: float = 0.0,
    log_id: Optional[str] = None,
) -> Dict[str, Any]:
    """记录一次脚本执行到对应部门的日志文件。"""
    if not log_id:
        log_id = f"{datetime.now().isoformat()}_{tool}"

    existing_logs = _read_department_logs(department)
    existing_entry = next((log for log in existing_logs if log.get("id") == log_id), None)
    timestamp = existing_entry.get("timestamp") if existing_entry else datetime.now().isoformat()

    log_entry = _build_log_entry(
        log_id=log_id,
        timestamp=timestamp,
        department=department,
        tool=tool,
        config=config,
        status=status,
        output=output,
        error=error,
        duration=duration,
    )
    return _upsert_log_entry(department, log_entry)


def _merge_logs_with_active(
    persisted_logs: List[Dict[str, Any]],
    active_logs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for log in persisted_logs:
        merged[log["id"]] = log

    for log in active_logs:
        merged[log["id"]] = log

    return sorted(
        merged.values(),
        key=lambda log: log.get("timestamp") or datetime.now().isoformat(),
        reverse=True,
    )


def get_recent_logs(limit: int = 20, department: Optional[str] = None, include_running: bool = True) -> List[Dict[str, Any]]:
    """获取最近的执行记录，包括运行中的任务。"""
    persisted_logs: List[Dict[str, Any]] = []

    if department:
        persisted_logs.extend(_read_department_logs(department))
    else:
        for log_file in LOGS_DIR.glob("*.json"):
            dept = log_file.stem.upper()
            persisted_logs.extend(_read_department_logs(dept))

    active_logs = get_active_processes(department) if include_running else []
    merged = _merge_logs_with_active(persisted_logs, active_logs)
    return merged[:limit]


def get_logs_by_tool(department: str, tool: str, limit: int = 10, include_running: bool = True) -> List[Dict[str, Any]]:
    """获取指定工具的最近记录。"""
    persisted_logs = [log for log in _read_department_logs(department) if log["tool"] == tool]
    active_logs = []
    if include_running:
        active_logs = [log for log in get_active_processes(department) if log["tool"] == tool]

    merged = _merge_logs_with_active(persisted_logs, active_logs)
    return merged[:limit]


def clear_old_logs(days: int = 30) -> Dict[str, int]:
    """清理 N 天前的日志，并返回各部门清理数量。"""
    cutoff = datetime.now().timestamp() - (days * 86400)
    total_removed = 0
    dept_removed: Dict[str, int] = {}

    for log_file in LOGS_DIR.glob("*.json"):
        dept = log_file.stem.upper()
        logs = _read_department_logs(dept)
        filtered = [
            log for log in logs
            if datetime.fromisoformat(log["timestamp"]).timestamp() > cutoff
        ]

        removed = len(logs) - len(filtered)
        if removed > 0:
            _write_department_logs(dept, filtered)
            dept_removed[dept] = removed
            total_removed += removed

    dept_removed["_total"] = total_removed
    return dept_removed


def clear_department_logs(department: str) -> bool:
    """清空指定部门的所有日志。"""
    try:
        if _get_log_file(department).exists():
            _write_department_logs(department, [])
        return True
    except Exception:
        return False
