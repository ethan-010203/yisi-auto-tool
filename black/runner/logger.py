"""执行日志记录模块 - 按部门独立存储。"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

MAX_LOG_ENTRIES = 100
MAX_OUTPUT_CHARS = 12000
MAX_ERROR_CHARS = 4000

# 活跃进程跟踪 {log_id: {...}}
_active_processes: Dict[str, Dict[str, Any]] = {}
_processes_lock = threading.Lock()


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def register_active_process(
    log_id: str,
    process: Any,
    department: str,
    tool: str,
    start_time: Optional[datetime] = None,
) -> None:
    """注册正在运行的进程。"""
    with _processes_lock:
        _active_processes[log_id] = {
            "process": process,
            "start_time": start_time or datetime.now(),
            "department": department,
            "tool": tool,
            "manual_terminated": False,
            "output": "",
            "error": "",
        }


def terminate_process(log_id: str) -> bool:
    """终止正在运行的进程。"""
    with _processes_lock:
        if log_id not in _active_processes:
            return False

        proc_info = _active_processes[log_id]
        process = proc_info["process"]
        proc_info["manual_terminated"] = True

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
    """获取活跃进程列表。"""
    with _processes_lock:
        processes = []
        for log_id, info in _active_processes.items():
            if department is None or info["department"] == department:
                duration = (datetime.now() - info["start_time"]).total_seconds()
                processes.append(
                    {
                        "id": log_id,
                        "department": info["department"],
                        "tool": info["tool"],
                        "duration": round(duration, 1),
                        "status": "running",
                        "timestamp": info["start_time"].isoformat(),
                        "manual_terminated": info.get("manual_terminated", False),
                        "output": info.get("output", ""),
                        "error": info.get("error", ""),
                    }
                )
        return processes


def unregister_process(log_id: str) -> None:
    """注销进程。"""
    with _processes_lock:
        _active_processes.pop(log_id, None)


def is_manual_terminated(log_id: str) -> bool:
    """检查进程是否被用户手动终止。"""
    with _processes_lock:
        if log_id in _active_processes:
            return _active_processes[log_id].get("manual_terminated", False)
        return False


def _get_log_file(department: str) -> Path:
    """获取部门的日志文件路径。"""
    return LOGS_DIR / f"{department.lower()}.json"


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
    timestamp = datetime.now().isoformat()

    log_entry = {
        "id": log_id or f"{timestamp}_{tool}",
        "timestamp": timestamp,
        "department": department,
        "tool": tool,
        "config": config or {},
        "status": status,
        "output": _trim_text(output, MAX_OUTPUT_CHARS) if output else "",
        "error": _trim_text(error, MAX_ERROR_CHARS) if error else None,
        "duration": round(duration, 2),
    }

    logs = _read_department_logs(department)
    logs.insert(0, log_entry)

    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[:MAX_LOG_ENTRIES]

    _write_department_logs(department, logs)
    return log_entry


def get_recent_logs(limit: int = 20, department: Optional[str] = None, include_running: bool = True) -> List[Dict[str, Any]]:
    """获取最近的执行记录，包括运行中的任务。"""
    logs: List[Dict[str, Any]] = []

    if include_running:
        logs.extend(get_active_processes(department))

    if department:
        logs.extend(_read_department_logs(department))
    else:
        for log_file in LOGS_DIR.glob("*.json"):
            dept = log_file.stem.upper()
            logs.extend(_read_department_logs(dept))

    def get_time(log: Dict[str, Any]) -> str:
        return log.get("timestamp") or datetime.now().isoformat()

    logs.sort(key=get_time, reverse=True)
    return logs[:limit]


def get_logs_by_tool(department: str, tool: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取指定工具的最近记录。"""
    logs = _read_department_logs(department)
    filtered = [log for log in logs if log["tool"] == tool]
    return filtered[:limit]


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


def clear_department_logs(department: str) -> bool:
    """清空指定部门的所有日志。"""
    try:
        log_file = _get_log_file(department)
        if log_file.exists():
            _write_department_logs(department, [])
        return True
    except Exception:
        return False
