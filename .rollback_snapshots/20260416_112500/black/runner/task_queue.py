from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Optional

from runner.logger import log_execution, register_queued_job, unregister_process, update_queue_positions

JobRunner = Callable[[Dict[str, Any]], None]

DEFAULT_LIMITS = {
    "global": 2,
    "per_department": 1,
    "per_tool": 1,
}


class TaskQueue:
    """本机内存任务队列，负责排队和并发控制。"""

    def __init__(
        self,
        *,
        global_limit: int = DEFAULT_LIMITS["global"],
        department_limit: int = DEFAULT_LIMITS["per_department"],
        tool_limit: int = DEFAULT_LIMITS["per_tool"],
    ) -> None:
        self.global_limit = global_limit
        self.department_limit = department_limit
        self.tool_limit = tool_limit
        self._queued_jobs: Deque[Dict[str, Any]] = deque()
        self._running_jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def enqueue(self, job: Dict[str, Any], runner: JobRunner) -> Dict[str, Any]:
        with self._lock:
            self._queued_jobs.append(job)
            self._refresh_queue_positions_locked()
            queue_position = self._find_queue_position_locked(job["log_id"])
            register_queued_job(
                log_id=job["log_id"],
                department=job["department"],
                tool=job["tool"],
                config=job.get("config"),
                queue_position=queue_position,
                created_time=job.get("created_at"),
            )
            self._dispatch_locked(runner)

            status = "running" if job["log_id"] in self._running_jobs else "queued"
            result = {"status": status}
            if status == "queued":
                result["queuePosition"] = self._find_queue_position_locked(job["log_id"])
            return result

    def cancel(self, log_id: str) -> bool:
        with self._lock:
            for job in list(self._queued_jobs):
                if job["log_id"] != log_id:
                    continue

                self._queued_jobs.remove(job)
                self._refresh_queue_positions_locked()
                created_at = job.get("created_at") or datetime.now()
                duration = max(0.0, (datetime.now() - created_at).total_seconds())
                log_execution(
                    department=job["department"],
                    tool=job["tool"],
                    config=job.get("config"),
                    status="terminated",
                    output=job.get("queued_message", "任务在队列中被终止"),
                    error="用户手动终止流程",
                    duration=duration,
                    log_id=job["log_id"],
                )
                unregister_process(job["log_id"])
                return True

            return False

    def get_limits(self) -> Dict[str, int]:
        return {
            "global": self.global_limit,
            "per_department": self.department_limit,
            "per_tool": self.tool_limit,
        }

    def _find_queue_position_locked(self, log_id: str) -> Optional[int]:
        for index, job in enumerate(self._queued_jobs, start=1):
            if job["log_id"] == log_id:
                return index
        return None

    def _refresh_queue_positions_locked(self) -> None:
        positions = {}
        for index, queued_job in enumerate(self._queued_jobs, start=1):
            positions[queued_job["log_id"]] = index
        update_queue_positions(positions)

    def _can_start_locked(self, job: Dict[str, Any]) -> bool:
        if len(self._running_jobs) >= self.global_limit:
            return False

        department_running = sum(
            1 for running_job in self._running_jobs.values()
            if running_job["department"] == job["department"]
        )
        if department_running >= self.department_limit:
            return False

        tool_running = sum(
            1 for running_job in self._running_jobs.values()
            if running_job["department"] == job["department"] and running_job["tool"] == job["tool"]
        )
        if tool_running >= self.tool_limit:
            return False

        return True

    def _dispatch_locked(self, runner: JobRunner) -> None:
        started = True
        while started:
            started = False
            for job in list(self._queued_jobs):
                if not self._can_start_locked(job):
                    continue

                self._queued_jobs.remove(job)
                self._running_jobs[job["log_id"]] = job
                self._refresh_queue_positions_locked()

                thread = threading.Thread(
                    target=self._run_job,
                    args=(job, runner),
                    daemon=True,
                )
                thread.start()
                started = True
                break

    def _run_job(self, job: Dict[str, Any], runner: JobRunner) -> None:
        try:
            runner(job)
        finally:
            with self._lock:
                self._running_jobs.pop(job["log_id"], None)
                self._dispatch_locked(runner)


def build_job(
    *,
    log_id: str,
    department: str,
    tool: str,
    script_path: Path,
    env: Dict[str, str],
    config: Dict[str, Any] | None,
    created_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    return {
        "log_id": log_id,
        "department": department,
        "tool": tool,
        "script_path": script_path,
        "env": env,
        "config": config or {},
        "created_at": created_at or datetime.now(),
        "queued_message": "任务正在排队，等待可用执行槽位",
    }
