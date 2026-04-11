from __future__ import annotations

import json
import sys
from pathlib import Path


CONFIG_FILE = Path(__file__).resolve().parents[2] / "configs" / "CONSULT_invoice_recognizer.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("配置文件不存在，请先在前端完成配置保存。")

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def validate_config(config: dict) -> tuple[str, str]:
    folder_path = (config.get("folderPath") or "").strip()
    excel_path = (config.get("excelPath") or "").strip()

    if not folder_path:
        raise ValueError("缺少源单据文件夹配置。")

    if not excel_path:
        raise ValueError("缺少 Excel 输出文件配置。")

    return folder_path, excel_path


def main() -> int:
    print("[CONSULT] 英德单据识别任务启动中...")

    try:
        config = load_config()
        folder_path, excel_path = validate_config(config)
    except Exception as error:
        print(f"[CONSULT] 配置检查失败: {error}")
        return 1

    print(f"[CONSULT] 源文件夹: {folder_path}")
    print(f"[CONSULT] Excel 输出: {excel_path}")
    print("[CONSULT] 当前脚本为企业级接入占位实现，可在此接入真实 OCR / RPA 流程。")
    print("[CONSULT] 任务校验完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
