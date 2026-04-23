from __future__ import annotations

import json
from pathlib import Path


def load_runtime_limits(config_dir: Path) -> dict:
    default_limits = {
        "global": 2,
        "perDepartment": 1,
        "perTool": 1,
    }

    limits_file = config_dir / "runtime_limits.json"
    if not limits_file.exists():
        return default_limits

    try:
        with open(limits_file, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return default_limits

    return {
        "global": max(1, int(payload.get("global", default_limits["global"]))),
        "perDepartment": max(1, int(payload.get("perDepartment", default_limits["perDepartment"]))),
        "perTool": max(1, int(payload.get("perTool", default_limits["perTool"]))),
    }
