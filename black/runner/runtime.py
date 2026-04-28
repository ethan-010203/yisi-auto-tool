from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict

RUNTIME_ROOT = Path(os.environ.get("YISI_RUNTIME_ROOT") or Path(__file__).parent.parent / "runtime")
RUNTIME_RETENTION_DAYS = 3
SECONDS_PER_DAY = 24 * 60 * 60


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def cleanup_old_runtime_dirs(retention_days: int = RUNTIME_RETENTION_DAYS) -> int:
    """Remove per-run runtime directories older than the retention window."""
    if retention_days < 1:
        raise ValueError("runtime retention days must be at least 1")

    if not RUNTIME_ROOT.exists():
        return 0

    runtime_root = RUNTIME_ROOT.resolve()
    cutoff_timestamp = time.time() - retention_days * SECONDS_PER_DAY
    deleted_count = 0

    for department_dir in RUNTIME_ROOT.iterdir():
        if not department_dir.is_dir() or department_dir.is_symlink():
            continue
        for tool_dir in department_dir.iterdir():
            if not tool_dir.is_dir() or tool_dir.is_symlink():
                continue
            for run_dir in tool_dir.iterdir():
                if not run_dir.is_dir() or run_dir.is_symlink():
                    continue
                try:
                    resolved_run_dir = run_dir.resolve()
                    if not _is_relative_to(resolved_run_dir, runtime_root):
                        continue
                    if run_dir.stat().st_mtime >= cutoff_timestamp:
                        continue
                    shutil.rmtree(resolved_run_dir)
                    deleted_count += 1
                except OSError:
                    continue

    return deleted_count


def prepare_runtime_bundle(department: str, tool: str, run_id: str, config: Dict[str, Any] | None) -> Dict[str, Path]:
    """为单次运行创建隔离目录和配置快照。"""
    cleanup_old_runtime_dirs()

    runtime_dir = RUNTIME_ROOT / department.lower() / tool / run_id
    downloads_dir = runtime_dir / "downloads"
    artifacts_dir = runtime_dir / "artifacts"
    screenshots_dir = runtime_dir / "screenshots"
    browser_profile_dir = runtime_dir / "browser-profile"
    stdout_log_path = runtime_dir / "stdout.log"
    stderr_log_path = runtime_dir / "stderr.log"
    config_path = runtime_dir / "config.json"

    for path in [
        runtime_dir,
        downloads_dir,
        artifacts_dir,
        screenshots_dir,
        browser_profile_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(config or {}, file, ensure_ascii=False, indent=2)

    return {
        "runtime_dir": runtime_dir,
        "downloads_dir": downloads_dir,
        "artifacts_dir": artifacts_dir,
        "screenshots_dir": screenshots_dir,
        "browser_profile_dir": browser_profile_dir,
        "stdout_log_path": stdout_log_path,
        "stderr_log_path": stderr_log_path,
        "config_path": config_path,
    }
