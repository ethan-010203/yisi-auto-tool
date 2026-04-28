from __future__ import annotations

import asyncio
import binascii
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from runner.runtime import prepare_runtime_bundle
    from runner.runtime_limits import load_runtime_limits
    from runner.sqlite_store import (
        build_department_snapshot,
        build_global_snapshot,
        clear_department_logs as clear_department_logs_sqlite,
        enqueue_execution,
        healthcheck,
        init_db,
        list_executions,
        request_cancel,
        retry_execution as retry_execution_sqlite,
    )
except ModuleNotFoundError:
    from .runner.runtime import prepare_runtime_bundle
    from .runner.runtime_limits import load_runtime_limits
    from .runner.sqlite_store import (
        build_department_snapshot,
        build_global_snapshot,
        clear_department_logs as clear_department_logs_sqlite,
        enqueue_execution,
        healthcheck,
        init_db,
        list_executions,
        request_cancel,
        retry_execution as retry_execution_sqlite,
    )

try:
    import tkinter as tk
    from tkinter import filedialog

    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False


app = FastAPI()

SERVICE_ENV = os.environ.get("YISI_SERVICE_ENV", "production").strip() or "production"
CONFIG_DIR = Path(os.environ.get("YISI_CONFIG_DIR") or Path(__file__).parent / "configs")
CONFIG_DIR.mkdir(exist_ok=True)
FRONT_DIST_DIR = Path(os.environ.get("YISI_FRONT_DIST_DIR") or Path(__file__).parent.parent / "front" / "dist")
FRONT_ASSETS_DIR = FRONT_DIST_DIR / "assets"

SCRIPT_DIR = Path(__file__).parent / "scripts"

DEPARTMENT_CATALOG: list[dict[str, Any]] = [
    {
        "code": "BUE1",
        "name": "BUE1",
        "tone": "regulatory",
        "summary": "BUE1 申报与法规自动化工具集合。",
        "networkPath": r"\\192.168.76.93\厦门部门\BUE1",
        "tools": [
            {
                "id": "ear_declaration_data_fetcher",
                "name": "EAR官网申报数据抓取",
                "tag": "EAR",
                "description": "读取申报数据 Excel 文件夹，结合 EAR 网页账号密码，为后续抓取官网申报结果提供运行骨架。",
                "action": "run_script",
                "configurable": True,
                "script": SCRIPT_DIR / "bue1" / "ear_declaration_data_fetcher.py",
            },
        ],
    },
    {
        "code": "BUE2",
        "name": "BUE2",
        "tone": "operations",
        "summary": "BUE2 自动化执行工具集合。",
        "networkPath": r"\\192.168.76.93\厦门部门\BUE2",
        "tools": [
            {
                "id": "test",
                "name": "测试脚本",
                "tag": "Test",
                "description": "用于验证脚本运行链路与日志输出。",
                "action": "run_script",
                "script": SCRIPT_DIR / "bue2" / "test.py",
            },
            {
                "id": "queue_runtime_probe",
                "name": "队列运行探针",
                "tag": "Queue",
                "description": "用于验证任务排队、运行时目录和实时日志能力。",
                "action": "run_script",
                "script": SCRIPT_DIR / "bue2" / "testing" / "queue_runtime_probe.py",
            },
            {
                "id": "citeo_email_extractor",
                "name": "FR-Citeo 邮件编号提取",
                "tag": "Email",
                "description": "从 163 邮箱指定文件夹提取 Citeo 邮件里的客户编号并导出结果。",
                "action": "run_script",
                "configurable": True,
                "script": SCRIPT_DIR / "bue2" / "citeo_email_extractor.py",
            },
        ],
    },
    {
        "code": "BUV1",
        "name": "BUV1",
        "tone": "growth",
        "summary": "BUV1 工具位预留。",
        "networkPath": r"\\192.168.76.93\厦门部门\BUV1",
        "tools": [
            {"id": "campaign_plan", "name": "活动规划", "tag": "Plan", "description": "预留工具位。"},
            {"id": "media_pack", "name": "素材包管理", "tag": "Media", "description": "预留工具位。"},
            {"id": "publish_hub", "name": "发布中心", "tag": "Publish", "description": "预留工具位。"},
        ],
    },
    {
        "code": "BUV2",
        "name": "BUV2",
        "tone": "delivery",
        "summary": "BUV2 工具位预留。",
        "networkPath": r"\\192.168.76.93\厦门部门\BUV2",
        "tools": [
            {"id": "roster_board", "name": "排期面板", "tag": "Roster", "description": "预留工具位。"},
            {"id": "ad_studio", "name": "广告工作台", "tag": "Ads", "description": "预留工具位。"},
            {"id": "report_center", "name": "报告中心", "tag": "Report", "description": "预留工具位。"},
        ],
    },
    {
        "code": "BUV3",
        "name": "BUV3",
        "tone": "brand",
        "summary": "BUV3 工具位预留。",
        "networkPath": r"\\192.168.76.93\厦门部门\BUV3",
        "tools": [
            {"id": "campaign_board", "name": "品牌项目板", "tag": "Brand", "description": "预留工具位。"},
            {"id": "idea_pool", "name": "灵感池", "tag": "Idea", "description": "预留工具位。"},
            {"id": "brand_guide", "name": "品牌指南", "tag": "Guide", "description": "预留工具位。"},
        ],
    },
    {
        "code": "CONSULT",
        "name": "顾问部",
        "tone": "consulting",
        "summary": "顾问部自动化工具集合。",
        "networkPath": r"\\192.168.76.93\厦门部门\顾问部",
        "tools": [
            {
                "id": "test_hello",
                "name": "测试脚本",
                "tag": "Test",
                "description": "用于验证顾问部脚本运行链路。",
                "action": "run_script",
                "script": SCRIPT_DIR / "consult" / "test_hello.py",
            },
            {
                "id": "queue_runtime_probe",
                "name": "队列运行探针",
                "tag": "Queue",
                "description": "用于验证任务排队、运行时目录和实时日志能力。",
                "action": "run_script",
                "script": SCRIPT_DIR / "consult" / "testing" / "queue_runtime_probe.py",
            },
            {
                "id": "invoice_recognizer",
                "name": "英德单据识别",
                "tag": "RPA",
                "description": "识别共享目录中的单据并处理 Excel 清单。",
                "action": "run_script",
                "configurable": True,
                "requiresNetworkPath": True,
                "script": SCRIPT_DIR / "consult" / "invoice_recognizer.py",
            },
        ],
    },
]

DEPARTMENT_NETWORK_PATHS = {
    department["code"]: department["networkPath"]
    for department in DEPARTMENT_CATALOG
}

TOOL_STORAGE_POLICIES = {
    ("CONSULT", "invoice_recognizer"): {
        "requires_network_path": True,
        "inputs_must_live_in_network_path": True,
    },
}

DEPARTMENT_SCRIPTS = {
    department["code"]: {
        tool["id"]: tool["script"]
        for tool in department["tools"]
        if tool.get("action") == "run_script" and tool.get("script")
    }
    for department in DEPARTMENT_CATALOG
}

executor = ThreadPoolExecutor(max_workers=2)
init_db()


def _load_cors_origins() -> list[str]:
    configured_origins = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("YISI_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if configured_origins:
        return configured_origins

    return [
        "https://auto.ethan010203.online",
        "https://auto-test.ethan010203.online",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_load_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONT_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONT_ASSETS_DIR), name="front-assets")


class ConfigRequest(BaseModel):
    folderPath: Optional[str] = None
    folderDisplay: Optional[str] = None
    excelPath: Optional[str] = None
    listExcelPath: Optional[str] = None
    listExcelDisplay: Optional[str] = None
    excelFilePath: Optional[str] = None
    excelFileDisplay: Optional[str] = None
    excelFolderPath: Optional[str] = None
    excelFolderDisplay: Optional[str] = None
    reportYear: Optional[str] = None
    reportMonthGerman: Optional[str] = None
    maxWorkers: Optional[int] = None
    email: Optional[str] = None
    authCode: Optional[str] = None
    maxEmails: Optional[int] = None
    subjectKeyword: Optional[str] = None
    selectedFolder: Optional[str] = None


class FileSelectRequest(BaseModel):
    fileType: Optional[str] = "excel"


class RunToolRequest(BaseModel):
    configOverride: Optional[ConfigRequest] = None


class DepartmentConfig(BaseModel):
    networkPath: Optional[str] = None


class NetworkPathTestRequest(BaseModel):
    path: str


class ImapTestRequest(BaseModel):
    email: str
    authCode: str


def _config_payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _config_file(department: str, tool: str) -> Path:
    return CONFIG_DIR / f"{department}_{tool}.json"


def _department_config_file(department: str) -> Path:
    return CONFIG_DIR / f"{department}_config.json"


def _read_tool_config(department: str, tool: str) -> Optional[dict[str, Any]]:
    config_file = _config_file(department.upper(), tool)
    if not config_file.exists():
        return None

    with open(config_file, "r", encoding="utf-8") as file:
        return json.load(file)


def _read_department_config(department: str) -> Optional[dict[str, Any]]:
    normalized_department = department.upper()
    fixed_network_path = DEPARTMENT_NETWORK_PATHS.get(normalized_department)
    if fixed_network_path:
        return {"networkPath": fixed_network_path}

    config_file = _department_config_file(department.upper())
    if not config_file.exists():
        return None

    with open(config_file, "r", encoding="utf-8") as file:
        return json.load(file)


def _merge_tool_config(base_config: Optional[dict[str, Any]], override_model: Optional[ConfigRequest]) -> dict[str, Any]:
    merged = dict(base_config or {})
    if not override_model:
        return merged

    for key, value in _config_payload(override_model).items():
        if value is not None:
            merged[key] = value
    return merged


def _shorten_path(path_value: str, limit: int = 60) -> str:
    path_value = (path_value or "").strip()
    if len(path_value) <= limit:
        return path_value or "未设置"
    return f"...{path_value[-(limit - 3):]}"


def _normalize_absolute_path_or_raise(path_value: str, label: str) -> Path:
    path = (path_value or "").strip()
    if len(path) >= 2 and path[0] == path[-1] and path[0] in ('"', "'"):
        path = path[1:-1].strip()
    if not path:
        raise ValueError(f"{label}不能为空，请填写可访问的绝对路径。")

    expanded_path = str(Path(path).expanduser()) if path.startswith("~") else path
    is_unc_path = expanded_path.startswith(r"\\")
    is_posix_path = expanded_path.startswith("/")
    is_windows_drive = len(expanded_path) > 2 and expanded_path[1] == ":" and expanded_path[2] in ["\\", "/"]

    if not (is_unc_path or is_posix_path or is_windows_drive):
        raise ValueError(f"{label}必须是绝对路径，例如 `\\\\server\\share\\folder` 或 `D:\\folder`。")

    if is_unc_path and os.name != "nt":
        raise ValueError("当前服务端不是 Windows，无法校验 UNC 网络路径。")

    return Path(expanded_path)


def _ensure_readable_directory(path: Path, label: str) -> None:
    try:
        next(path.iterdir(), None)
    except PermissionError as exc:
        raise PermissionError(f"{label}没有读取权限: {path}") from exc
    except OSError as exc:
        raise OSError(f"{label}无法读取: {path}; {exc}") from exc


def _ensure_writable_directory(path: Path, label: str) -> None:
    probe_file = path / f".yisi_write_test_{uuid4().hex[:8]}"
    try:
        probe_file.write_text("test", encoding="utf-8")
        probe_file.unlink()
    except PermissionError as exc:
        raise PermissionError(f"{label}没有写入权限: {path}") from exc
    except OSError as exc:
        raise OSError(f"{label}无法写入: {path}; {exc}") from exc


def _ensure_readable_file(path: Path, label: str) -> None:
    try:
        with open(path, "rb") as file:
            file.read(1)
    except PermissionError as exc:
        raise PermissionError(f"{label}没有读取权限: {path}") from exc
    except OSError as exc:
        raise OSError(f"{label}无法读取: {path}; {exc}") from exc


def _validate_network_path_or_raise(path_value: str) -> Path:
    target_path = _normalize_absolute_path_or_raise(path_value, "网络路径")
    if not target_path.exists():
        raise FileNotFoundError(f"网络路径不存在: {target_path}")
    if not target_path.is_dir():
        raise NotADirectoryError(f"网络路径不是文件夹: {target_path}")

    _ensure_readable_directory(target_path, "网络路径")
    _ensure_writable_directory(target_path, "网络路径")
    return target_path


def _validate_invoice_recognizer_config_or_raise(config: dict[str, Any]) -> dict[str, Any]:
    folder_path_text = (config.get("folderPath") or "").strip()
    excel_path_text = (config.get("excelPath") or config.get("listExcelPath") or "").strip()

    folder_path = _normalize_absolute_path_or_raise(folder_path_text, "单据文件夹")
    excel_path = _normalize_absolute_path_or_raise(excel_path_text, "Excel 清单")

    if not folder_path.exists():
        raise FileNotFoundError(f"单据文件夹不存在: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"单据路径不是文件夹: {folder_path}")
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel 清单不存在: {excel_path}")
    if not excel_path.is_file():
        raise FileNotFoundError(f"Excel 清单不是文件: {excel_path}")
    if excel_path.suffix.lower() != ".xlsx":
        raise ValueError("Excel 清单必须是 .xlsx 文件。")

    _ensure_readable_directory(folder_path, "单据文件夹")
    _ensure_writable_directory(folder_path, "单据文件夹")
    _ensure_readable_file(excel_path, "Excel 清单")

    normalized_folder_path = str(folder_path)
    normalized_excel_path = str(excel_path)
    normalized_config = dict(config)
    normalized_config["folderPath"] = normalized_folder_path
    normalized_config["folderDisplay"] = normalized_folder_path
    normalized_config["excelPath"] = normalized_excel_path
    normalized_config["listExcelPath"] = normalized_excel_path
    normalized_config["listExcelDisplay"] = normalized_excel_path
    return normalized_config


def _validate_ear_declaration_data_fetcher_config_or_raise(config: dict[str, Any]) -> dict[str, Any]:
    excel_file_path_text = (config.get("excelFilePath") or config.get("excelFolderPath") or "").strip()
    report_year = str(config.get("reportYear") or "").strip()
    report_month_german = str(config.get("reportMonthGerman") or "").strip()
    raw_max_workers = config.get("maxWorkers", 1)
    excel_file_path = _normalize_absolute_path_or_raise(excel_file_path_text, "EAR Excel")

    if not excel_file_path.exists():
        raise FileNotFoundError(f"EAR Excel 不存在: {excel_file_path}")
    if not excel_file_path.is_file():
        raise FileNotFoundError(f"EAR Excel 不是文件: {excel_file_path}")
    if excel_file_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("EAR Excel 必须是 .xlsx 或 .xlsm 文件。")
    if not report_year:
        raise ValueError("请填写检测年份。")
    if not report_month_german:
        raise ValueError("请填写德语月份。")

    try:
        max_workers = int(raw_max_workers)
    except (TypeError, ValueError):
        raise ValueError("EAR 并发线程数必须是 1 到 4 之间的整数。") from None
    if max_workers < 1 or max_workers > 4:
        raise ValueError("EAR 并发线程数必须是 1 到 4 之间的整数。")

    _ensure_readable_file(excel_file_path, "EAR Excel")

    normalized_excel_path = str(excel_file_path)
    normalized_config = dict(config)
    normalized_config["excelFilePath"] = normalized_excel_path
    normalized_config["excelFileDisplay"] = normalized_excel_path
    normalized_config["excelFolderPath"] = normalized_excel_path
    normalized_config["excelFolderDisplay"] = normalized_excel_path
    normalized_config["reportYear"] = report_year
    normalized_config["reportMonthGerman"] = report_month_german
    normalized_config["maxWorkers"] = max_workers
    return normalized_config


def _validate_tool_config_or_raise(department: str, tool: str, config: dict[str, Any]) -> dict[str, Any]:
    normalized_config = dict(config or {})

    if department.upper() == "BUE1" and tool == "ear_declaration_data_fetcher":
        return _validate_ear_declaration_data_fetcher_config_or_raise(normalized_config)

    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        return _validate_invoice_recognizer_config_or_raise(normalized_config)

    return normalized_config


def _get_tool_storage_policy(department: str, tool: str) -> dict[str, Any]:
    return TOOL_STORAGE_POLICIES.get((department.upper(), tool), {})


def _ensure_tool_network_root(department: str, tool: str) -> tuple[dict[str, Any], Path]:
    dept_config = _read_department_config(department.upper()) or {}
    network_root = _validate_network_path_or_raise(dept_config.get("networkPath", ""))
    return dept_config, network_root


def _is_path_within_root(path_value: str, root_path: Path) -> bool:
    try:
        normalized_path = os.path.normcase(os.path.normpath(str(Path(path_value))))
        normalized_root = os.path.normcase(os.path.normpath(str(root_path)))
        return os.path.commonpath([normalized_path, normalized_root]) == normalized_root
    except Exception:
        return False


def _validate_network_bound_config(department: str, tool: str, config: dict[str, Any], network_root: Path) -> None:
    policy = _get_tool_storage_policy(department, tool)
    if not policy.get("inputs_must_live_in_network_path"):
        return

    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        required_paths = [
            ("单据文件夹", (config.get("folderPath") or "").strip()),
            ("Excel 清单", (config.get("excelPath") or config.get("listExcelPath") or "").strip()),
        ]

        for label, path_value in required_paths:
            if not path_value:
                raise ValueError(f"{label}不能为空。")
            if not _is_path_within_root(path_value, network_root):
                raise ValueError(f"{label}必须位于部门共享根目录下: {network_root}")


def _build_preview_payload(department: str, tool: str, config: Optional[dict[str, Any]]) -> dict[str, Any]:
    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        folder_path = (config or {}).get("folderPath", "")
        excel_path = (config or {}).get("excelPath", "") or (config or {}).get("listExcelPath", "")
        configured = bool(folder_path and excel_path)
        return {
            "success": True,
            "preview": {
                "eyebrow": "Consult Automation",
                "title": "Invoice Recognizer",
                "summary": "从共享盘读取单据目录和 Excel 清单，调用脚本生成识别结果与运行产物。",
                "configured": configured,
                "metrics": [
                    {"label": "运行方式", "value": "Worker 队列", "detail": "API 只负责入队和查询，执行由独立 worker 完成。"},
                    {"label": "输入来源", "value": "共享盘目录", "detail": "目录与清单都要求位于当前部门共享根目录下。"},
                    {"label": "实时状态", "value": "SSE 推送", "detail": "执行日志、排队位置和失败状态会实时刷新。"},
                ],
                "stages": [
                    {"name": "Step 1", "description": "校验共享盘路径与 Excel 配置。"},
                    {"name": "Step 2", "description": "任务进入 SQLite 队列，等待 worker 认领。"},
                    {"name": "Step 3", "description": "worker 执行脚本并持续回写实时输出。"},
                ],
                "checklist": [
                    "单据文件夹已配置为服务器可访问的绝对路径。",
                    "Excel 清单为 .xlsx 且可读。",
                    "两条路径都位于部门共享盘根目录下。",
                ],
                "inputs": [
                    {"label": "单据文件夹", "value": _shorten_path(folder_path)},
                    {"label": "Excel 清单", "value": _shorten_path(excel_path)},
                    {"label": "配置状态", "value": "已完成" if configured else "未完成"},
                ],
            },
        }

    if department.upper() == "BUE2" and tool == "citeo_email_extractor":
        email = (config or {}).get("email", "")
        auth_code = (config or {}).get("authCode", "")
        configured = bool(email and auth_code)
        return {
            "success": True,
            "preview": {
                "eyebrow": "BUE2 Automation",
                "title": "Citeo Email Extractor",
                "summary": "通过 163 邮箱的 IMAP 连接提取指定文件夹中的 Citeo 邮件。",
                "configured": configured,
                "metrics": [
                    {"label": "连接方式", "value": "IMAP SSL", "detail": "使用 163 邮箱授权码登录。"},
                    {"label": "运行方式", "value": "Worker 队列", "detail": "任务与日志都写入 SQLite。"},
                    {"label": "实时状态", "value": "SSE 推送", "detail": "排队和运行状态自动刷新。"},
                ],
                "stages": [
                    {"name": "Step 1", "description": "读取邮箱配置并获取目标文件夹。"},
                    {"name": "Step 2", "description": "任务进入队列等待 worker 执行。"},
                    {"name": "Step 3", "description": "按配置抓取邮件并输出结果。"},
                ],
                "checklist": [
                    "邮箱地址与授权码已配置。",
                    "目标文件夹已选择。",
                    "邮件数量上限符合当前业务场景。",
                ],
                "inputs": [
                    {"label": "邮箱账号", "value": email or "未设置"},
                    {"label": "授权码", "value": "已设置" if auth_code else "未设置"},
                    {"label": "配置状态", "value": "已完成" if configured else "未完成"},
                ],
            },
        }

    return {"success": False, "error": f"Preview not available for {department}/{tool}"}


def _build_bue1_ear_template_workbook_bytes() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "EAR Template"
    sheet.append(
        [
            "授权代表\nbevollmächtigter Vertreter",
            "WEEE号\nWEEE-Nummer",
            "中文名\nFirmenname auf Chinesisch",
            "英文名\nFirmenname auf Englisch",
            "类别\nKategorie",
            "德语类目",
            "账号",
            "密码",
            "*月申报数据",
            "官网上抓取的数据（*月）",
        ]
    )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def decode_imap_utf7(value: str) -> str:
    def decode_chunk(chunk: str) -> str:
        b64 = chunk.replace(",", "/").encode("ascii")
        pad_len = (4 - len(b64) % 4) % 4
        b64 += b"=" * pad_len
        try:
            decoded_bytes = binascii.a2b_base64(b64)
            return decoded_bytes.decode("utf-16-be", errors="ignore")
        except Exception:
            return chunk

    result: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "&" and index + 1 < len(value):
            end = value.find("-", index + 1)
            if end == -1:
                result.append(value[index])
                index += 1
                continue

            encoded = value[index + 1:end]
            result.append("&" if encoded == "" else decode_chunk(encoded))
            index = end + 1
            continue

        result.append(value[index])
        index += 1

    return "".join(result)


def _open_folder_dialog_native() -> str:
    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
                        '$dialog.Title = "Select current folder"; '
                        '$dialog.Filter = "Folder selection|*.folder"; '
                        "$dialog.CheckFileExists = $false; "
                        "$dialog.CheckPathExists = $true; "
                        "$dialog.ValidateNames = $false; "
                        '$dialog.FileName = "Select current folder"; '
                        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                        "$selectedPath = Split-Path -Parent $dialog.FileName; "
                        'if ([string]::IsNullOrWhiteSpace($selectedPath)) { $selectedPath = $dialog.FileName }; '
                        "Write-Output $selectedPath "
                        "}"
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["osascript", "-e", 'POSIX path of (choose folder with prompt "Select folder")'],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    if not TKINTER_AVAILABLE:
        return ""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder_path = filedialog.askdirectory(title="Select folder")
    root.destroy()
    return folder_path


def _open_file_dialog(file_type: str) -> str:
    if sys.platform.startswith("win"):
        prompt = "Select Excel file" if file_type == "excel" else "Select file"
        filter_value = "Excel files (*.xlsx;*.xls)|*.xlsx;*.xls" if file_type == "excel" else "All files (*.*)|*.*"
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
                        f'$dialog.Title = "{prompt}"; '
                        f'$dialog.Filter = "{filter_value}"; '
                        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                        "Write-Output $dialog.FileName "
                        "}"
                    ),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["osascript", "-e", 'POSIX path of (choose file with prompt "Select file")'],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    if not TKINTER_AVAILABLE:
        return ""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_types = [("Excel files", "*.xlsx *.xls"), ("All files", "*.*")] if file_type == "excel" else [("All files", "*.*")]
    file_path = filedialog.askopenfilename(title="Select file", filetypes=file_types)
    root.destroy()
    return file_path


@app.get("/")
def read_root():
    index_file = FRONT_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse(
        "<html><body><h1>Yisi Automation API</h1><p>Frontend build not found. Run the frontend build first.</p></body></html>"
    )


@app.get("/api/health")
def read_health():
    return {
        "message": "Automation API is online",
        "storage": healthcheck(),
        "limits": load_runtime_limits(CONFIG_DIR),
        "frontend": {
            "distExists": FRONT_DIST_DIR.exists(),
            "indexExists": (FRONT_DIST_DIR / "index.html").exists(),
            "distPath": str(FRONT_DIST_DIR),
        },
        "mode": {
            "environment": SERVICE_ENV,
            "queue": "sqlite",
            "worker": "separate-process",
            "configDir": str(CONFIG_DIR),
        },
    }


def _serialize_tool_metadata(tool: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in tool.items()
        if key != "script"
    }
    script_path = tool.get("script")
    if isinstance(script_path, Path):
        payload["path"] = str(script_path)
        payload["available"] = script_path.exists()
    elif tool.get("action") == "run_script":
        payload["available"] = False
    return payload


def _serialize_department_metadata(department: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": department["code"],
        "name": department["name"],
        "tone": department.get("tone", ""),
        "summary": department.get("summary", ""),
        "networkPath": department.get("networkPath", ""),
        "tools": [_serialize_tool_metadata(tool) for tool in department.get("tools", [])],
    }


@app.get("/api/departments")
def list_departments():
    departments = [_serialize_department_metadata(department) for department in DEPARTMENT_CATALOG]
    return {
        "success": True,
        "departments": departments,
        "departmentNetworkPaths": {
            department["code"]: department.get("networkPath", "")
            for department in departments
        },
    }


@app.get("/api/departments/{department}/tools")
def list_tools(department: str):
    department_metadata = next(
        (item for item in DEPARTMENT_CATALOG if item["code"] == department.upper()),
        None,
    )
    if not department_metadata:
        return {"department": department, "tools": []}

    return {
        "department": department,
        "tools": [_serialize_tool_metadata(tool) for tool in department_metadata.get("tools", [])],
    }


@app.post("/api/departments/{department}/tools/{tool}/run")
def run_tool(department: str, tool: str, payload: Optional[RunToolRequest] = None):
    normalized_department = department.upper()
    dept_scripts = DEPARTMENT_SCRIPTS.get(normalized_department)
    if not dept_scripts:
        return {"success": False, "error": f"Department {department} not found"}

    script_path = dept_scripts.get(tool)
    if not script_path or not script_path.exists():
        return {"success": False, "error": f"Tool {tool} not found for department {department}"}

    config = _merge_tool_config(
        _read_tool_config(normalized_department, tool) or {},
        payload.configOverride if payload else None,
    )

    try:
        config = _validate_tool_config_or_raise(normalized_department, tool, config)
        dept_config = _read_department_config(normalized_department)
        network_path = dept_config.get("networkPath", "") if dept_config else ""
        policy = _get_tool_storage_policy(normalized_department, tool)
        if policy.get("requires_network_path"):
            _, validated_network_root = _ensure_tool_network_root(normalized_department, tool)
            network_path = str(validated_network_root)
            _validate_network_bound_config(normalized_department, tool, config, validated_network_root)
    except Exception as error:
        return {"success": False, "error": str(error)}

    log_id = f"{int(time.time() * 1000)}_{tool}_{uuid4().hex[:8]}"
    runtime_bundle = prepare_runtime_bundle(normalized_department, tool, log_id, config)
    env = {
        "YISI_DEPT_NETWORK_PATH": network_path,
        "YISI_TOOL_ID": tool,
        "YISI_DEPARTMENT": normalized_department,
        "YISI_RUN_ID": log_id,
        "YISI_RUNTIME_DIR": str(runtime_bundle["runtime_dir"]),
        "YISI_CONFIG_PATH": str(runtime_bundle["config_path"]),
        "YISI_DOWNLOAD_DIR": str(runtime_bundle["downloads_dir"]),
        "YISI_ARTIFACT_DIR": str(runtime_bundle["artifacts_dir"]),
        "YISI_SCREENSHOT_DIR": str(runtime_bundle["screenshots_dir"]),
        "YISI_BROWSER_PROFILE_DIR": str(runtime_bundle["browser_profile_dir"]),
        "YISI_STDOUT_LOG_PATH": str(runtime_bundle["stdout_log_path"]),
        "YISI_STDERR_LOG_PATH": str(runtime_bundle["stderr_log_path"]),
    }

    queue_result = enqueue_execution(
        execution_id=log_id,
        department=normalized_department,
        tool=tool,
        config=config,
        env=env,
        script_path=str(script_path),
    )

    return {
        "success": True,
        "logId": log_id,
        "message": "任务已进入队列，等待 worker 执行",
        "status": "queued",
        "queuePosition": queue_result.get("queuePosition"),
    }


@app.post("/api/executions/{log_id}/terminate")
def terminate_execution(log_id: str):
    success, status = request_cancel(log_id)
    if not success and status is None:
        return {"success": False, "error": "Task not found"}

    if success and status == "terminated":
        return {"success": True, "message": "任务已从队列中移除"}

    if success and status in {"running", "cancelling"}:
        return {"success": True, "message": "已向 worker 发送取消请求"}

    return {"success": False, "error": f"Task cannot be cancelled in status: {status}"}


@app.post("/api/executions/{log_id}/retry")
def retry_execution(log_id: str):
    new_log_id = f"{int(time.time() * 1000)}_retry_{uuid4().hex[:8]}"
    result = retry_execution_sqlite(log_id, new_log_id)
    if not result:
        return {"success": False, "error": "Task not found"}

    return {
        "success": True,
        "logId": new_log_id,
        "status": result["status"],
        "queuePosition": result.get("queuePosition"),
        "message": "失败任务已重新入队",
    }


@app.post("/api/departments/{department}/tools/{tool}/config")
def save_tool_config(department: str, tool: str, config: ConfigRequest):
    normalized_department = department.upper()
    config_file = _config_file(normalized_department, tool)

    try:
        config_payload = _validate_tool_config_or_raise(normalized_department, tool, _config_payload(config))
        policy = _get_tool_storage_policy(normalized_department, tool)
        if policy.get("requires_network_path"):
            _, validated_network_root = _ensure_tool_network_root(normalized_department, tool)
            _validate_network_bound_config(normalized_department, tool, config_payload, validated_network_root)

        with open(config_file, "w", encoding="utf-8") as file:
            json.dump(config_payload, file, ensure_ascii=False, indent=2)
        return {"success": True, "message": "工具配置已保存", "path": str(config_file)}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/tools/{tool}/config")
def get_tool_config(department: str, tool: str):
    try:
        return {"success": True, "config": _read_tool_config(department, tool) or {}}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/tools/{tool}/preview")
def get_tool_preview(department: str, tool: str):
    try:
        config = _read_tool_config(department, tool)
        return _build_preview_payload(department, tool, config)
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/tools/{tool}/template")
def download_tool_template(department: str, tool: str):
    normalized_department = department.upper()
    if normalized_department == "BUE1" and tool == "ear_declaration_data_fetcher":
        file_bytes = _build_bue1_ear_template_workbook_bytes()
        filename = "EAR申报配置模板.xlsx"
        fallback_filename = "BUE1_EAR_template.xlsx"
        content_disposition = (
            f'attachment; filename="{fallback_filename}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
        return StreamingResponse(
            BytesIO(file_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": content_disposition},
        )

    raise HTTPException(status_code=404, detail=f"Template not available for {normalized_department}/{tool}")


@app.post("/api/select-folder")
async def select_folder():
    if not sys.platform.startswith("win") and sys.platform != "darwin" and not TKINTER_AVAILABLE:
        return {"success": False, "error": "Tkinter not available"}

    try:
        loop = asyncio.get_running_loop()
        folder_path = await loop.run_in_executor(executor, _open_folder_dialog_native)
        if folder_path:
            return {"success": True, "path": folder_path}
        return {"success": False, "path": None, "message": "未选择文件夹"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.post("/api/select-file")
async def select_file(request: FileSelectRequest):
    if not sys.platform.startswith("win") and sys.platform != "darwin" and not TKINTER_AVAILABLE:
        return {"success": False, "error": "Tkinter not available"}

    try:
        loop = asyncio.get_running_loop()
        file_path = await loop.run_in_executor(executor, _open_file_dialog, request.fileType)
        if file_path:
            return {"success": True, "path": file_path}
        return {"success": False, "path": None, "message": "未选择文件"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/logs")
def get_execution_logs(limit: int = 20, department: Optional[str] = None):
    try:
        logs = list_executions(limit=limit, department=department.upper() if department else None)
        return {"success": True, "logs": logs}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/logs")
def get_department_logs(department: str, limit: int = 20):
    try:
        logs = list_executions(limit=limit, department=department.upper())
        return {"success": True, "logs": logs}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/tools/{tool}/logs")
def get_tool_execution_logs(department: str, tool: str, limit: int = 10):
    try:
        logs = list_executions(limit=limit, department=department.upper(), tool=tool)
        return {"success": True, "logs": logs}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/events")
async def stream_department_events(department: str, request: Request, limit: int = 20):
    normalized_department = department.upper()

    async def event_stream():
        last_cursor: Optional[str] = None
        ping_counter = 0
        while True:
            if await request.is_disconnected():
                break

            snapshot = build_department_snapshot(normalized_department, limit=limit)
            cursor = json.dumps(
                {
                    "cursor": snapshot["cursor"],
                    "summary": snapshot["summary"],
                    "activeToolIds": snapshot["activeToolIds"],
                    "count": len(snapshot["logs"]),
                },
                ensure_ascii=False,
                sort_keys=True,
            )

            if cursor != last_cursor:
                last_cursor = cursor
                payload = json.dumps(snapshot, ensure_ascii=False)
                yield f"event: snapshot\ndata: {payload}\n\n"
                ping_counter = 0
            else:
                ping_counter += 1
                if ping_counter >= 10:
                    yield "event: ping\ndata: {}\n\n"
                    ping_counter = 0

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/events")
async def stream_global_events(request: Request, limit: int = 50):
    async def event_stream():
        last_cursor: Optional[str] = None
        ping_counter = 0
        while True:
            if await request.is_disconnected():
                break

            snapshot = build_global_snapshot(limit=limit)
            cursor = json.dumps(
                {
                    "cursor": snapshot["cursor"],
                    "summary": snapshot["summary"],
                    "activeDepartments": snapshot["activeDepartments"],
                    "count": len(snapshot["logs"]),
                },
                ensure_ascii=False,
                sort_keys=True,
            )

            if cursor != last_cursor:
                last_cursor = cursor
                payload = json.dumps(snapshot, ensure_ascii=False)
                yield f"event: snapshot\ndata: {payload}\n\n"
                ping_counter = 0
            else:
                ping_counter += 1
                if ping_counter >= 10:
                    yield "event: ping\ndata: {}\n\n"
                    ping_counter = 0

            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/departments/{department}/logs")
def clear_department_execution_logs(department: str):
    try:
        deleted = clear_department_logs_sqlite(department.upper())
        return {"success": True, "message": f"已清理 {deleted} 条历史记录"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.post("/api/list-mail-folders")
def list_mail_folders_endpoint(request: ImapTestRequest):
    try:
        import imaplib

        if not re.match(r"^[\w.-]+@163\.com$", request.email):
            return {"success": False, "error": "只支持 163 邮箱地址。"}
        if not request.authCode:
            return {"success": False, "error": "请输入邮箱授权码。"}

        mail = imaplib.IMAP4_SSL("imap.163.com", 993)
        mail.login(request.email, request.authCode)
        status, folders = mail.list()
        if status != "OK":
            mail.logout()
            return {"success": False, "error": "无法获取邮箱文件夹列表。"}

        folder_list = []
        for folder in folders:
            try:
                folder_str = folder.decode()
                parts = folder_str.split('"')
                if len(parts) < 2:
                    continue
                encoded_name = parts[-2]
                decoded_name = decode_imap_utf7(encoded_name)
                folder_type = "other"
                if decoded_name in ["INBOX", "收件箱"]:
                    folder_type = "inbox"
                elif decoded_name in ["Sent", "已发送", "&XfJT0ZAB-"]:
                    folder_type = "sent"
                elif decoded_name in ["Drafts", "草稿箱", "&g0l6P3ux-"]:
                    folder_type = "drafts"
                elif decoded_name in ["Trash", "垃圾箱", "Deleted"]:
                    folder_type = "trash"

                folder_list.append(
                    {
                        "encoded": encoded_name,
                        "display": decoded_name,
                        "type": folder_type,
                    }
                )
            except Exception:
                continue

        mail.logout()
        folder_list.sort(key=lambda item: (0 if item["type"] == "inbox" else 1, item["display"]))
        return {"success": True, "folders": folder_list}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.post("/api/departments/{department}/config")
def save_department_config(department: str, config: DepartmentConfig):
    try:
        normalized_department = department.upper()
        config_file = _department_config_file(normalized_department)
        payload = _config_payload(config)
        network_path = (payload.get("networkPath") or "").strip()
        payload["networkPath"] = str(_validate_network_path_or_raise(network_path)) if network_path else ""
        with open(config_file, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        return {"success": True, "message": "部门配置已保存"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/config")
def get_department_config(department: str):
    try:
        fixed_config = _read_department_config(department.upper())
        if fixed_config:
            return {"success": True, "config": fixed_config}

        config_file = _department_config_file(department.upper())
        if not config_file.exists():
            return {"success": True, "config": {}}
        with open(config_file, "r", encoding="utf-8") as file:
            return {"success": True, "config": json.load(file)}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.post("/api/test-network-path")
def test_network_path(request: NetworkPathTestRequest):
    try:
        _validate_network_path_or_raise(request.path)
        return {"success": True, "message": "网络路径读写正常"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/{full_path:path}")
def serve_frontend_app(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    candidate = FRONT_DIST_DIR / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    index_file = FRONT_DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    raise HTTPException(status_code=404, detail="Frontend build not found")
