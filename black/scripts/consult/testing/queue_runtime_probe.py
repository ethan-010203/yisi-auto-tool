from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

LOG_PREFIX = "[CONSULT-QUEUE-PROBE]"
DEFAULT_WAIT_SECONDS = 12
MAX_WAIT_SECONDS = 3600


def log(message: str) -> None:
    print(f"{LOG_PREFIX} {message}", flush=True)


def get_required_path(env_name: str) -> Path:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise ValueError(f"Missing required env: {env_name}")
    return Path(value)


def resolve_wait_seconds(config: dict) -> int:
    raw_value = config.get("waitSeconds", DEFAULT_WAIT_SECONDS)
    try:
        wait_seconds = int(raw_value)
    except (TypeError, ValueError):
        raise ValueError("waitSeconds must be an integer from 1 to 3600.") from None

    if wait_seconds < 1 or wait_seconds > MAX_WAIT_SECONDS:
        raise ValueError("waitSeconds must be an integer from 1 to 3600.")

    return wait_seconds


def main() -> int:
    started_at = datetime.now()
    runtime_dir = get_required_path("YISI_RUNTIME_DIR")
    artifact_dir = get_required_path("YISI_ARTIFACT_DIR")
    download_dir = get_required_path("YISI_DOWNLOAD_DIR")
    screenshot_dir = get_required_path("YISI_SCREENSHOT_DIR")
    browser_profile_dir = get_required_path("YISI_BROWSER_PROFILE_DIR")
    config_path = get_required_path("YISI_CONFIG_PATH")
    stdout_log_path = get_required_path("YISI_STDOUT_LOG_PATH")
    stderr_log_path = get_required_path("YISI_STDERR_LOG_PATH")

    run_id = os.environ.get("YISI_RUN_ID", "")
    department = os.environ.get("YISI_DEPARTMENT", "")
    tool_id = os.environ.get("YISI_TOOL_ID", "")

    log("queue/runtime probe started")
    log(f"department={department} tool={tool_id} run_id={run_id}")
    log(f"runtime_dir={runtime_dir}")
    log(f"artifact_dir={artifact_dir}")
    log(f"download_dir={download_dir}")
    log(f"screenshot_dir={screenshot_dir}")
    log(f"browser_profile_dir={browser_profile_dir}")
    log(f"config_path={config_path}")
    log(f"stdout_log_path={stdout_log_path}")
    log(f"stderr_log_path={stderr_log_path}")

    config_snapshot = {}
    if config_path.exists():
        config_snapshot = json.loads(config_path.read_text(encoding="utf-8"))
    wait_seconds = resolve_wait_seconds(config_snapshot)
    log(f"configured wait_seconds={wait_seconds}")

    metadata = {
        "department": department,
        "tool": tool_id,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "wait_seconds": wait_seconds,
        "config_snapshot": config_snapshot,
        "paths": {
            "runtime_dir": str(runtime_dir),
            "artifact_dir": str(artifact_dir),
            "download_dir": str(download_dir),
            "screenshot_dir": str(screenshot_dir),
            "browser_profile_dir": str(browser_profile_dir),
            "config_path": str(config_path),
            "stdout_log_path": str(stdout_log_path),
            "stderr_log_path": str(stderr_log_path),
        },
    }
    (artifact_dir / "probe_meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    heartbeat_path = artifact_dir / "heartbeat.log"
    for remaining_seconds in range(wait_seconds, 0, -1):
        elapsed_seconds = wait_seconds - remaining_seconds + 1
        log(f"waiting {elapsed_seconds}/{wait_seconds}s")
        with heartbeat_path.open("a", encoding="utf-8") as heartbeat_file:
            heartbeat_file.write(
                f"{datetime.now().isoformat()} | run_id={run_id} | elapsed={elapsed_seconds}/{wait_seconds}s\n"
            )
        time.sleep(1)

    (artifact_dir / "probe_done.txt").write_text(
        f"done at {datetime.now().isoformat()}\n",
        encoding="utf-8",
    )

    elapsed = (datetime.now() - started_at).total_seconds()
    log(f"probe finished in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
