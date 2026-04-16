from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

RUNTIME_ROOT = Path(__file__).parent.parent / "runtime"


def prepare_runtime_bundle(department: str, tool: str, run_id: str, config: Dict[str, Any] | None) -> Dict[str, Path]:
    """为单次运行创建隔离目录和配置快照。"""
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
