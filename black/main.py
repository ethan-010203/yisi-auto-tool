from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from runner.logger import (
    get_recent_logs, get_logs_by_tool, log_execution, clear_department_logs,
    register_active_process, terminate_process, get_active_processes, unregister_process,
    is_manual_terminated, append_process_output
)
from runner.runtime import prepare_runtime_bundle
from runner.task_queue import TaskQueue, build_job

try:
    import tkinter as tk
    from tkinter import filedialog

    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False


app = FastAPI()

CONFIG_DIR = Path(__file__).parent / "configs"
CONFIG_DIR.mkdir(exist_ok=True)
RUNTIME_LIMITS_FILE = CONFIG_DIR / "runtime_limits.json"
TOOL_STORAGE_POLICIES = {
    ("CONSULT", "invoice_recognizer"): {
        "requires_network_path": True,
        "inputs_must_live_in_network_path": True,
    },
}

executor = ThreadPoolExecutor(max_workers=2)
TASK_QUEUE = TaskQueue()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEPARTMENT_SCRIPTS = {
    "BUE1": {
        "ear_declaration_data_fetcher": Path(__file__).parent / "scripts" / "bue1" / "ear_declaration_data_fetcher.py",
    },
    "CONSULT": {
        "test_hello": Path(__file__).parent / "scripts" / "consult" / "test_hello.py",
        "queue_runtime_probe": Path(__file__).parent / "scripts" / "consult" / "testing" / "queue_runtime_probe.py",
        "invoice_recognizer": Path(__file__).parent / "scripts" / "consult" / "invoice_recognizer.py",
        "pdf_classifier": Path(__file__).parent / "scripts" / "consult" / "pdf_classifier.py",
    },
    "BUE2": {
        "test": Path(__file__).parent / "scripts" / "bue2" / "test.py",
        "queue_runtime_probe": Path(__file__).parent / "scripts" / "bue2" / "testing" / "queue_runtime_probe.py",
        "citeo_email_extractor": Path(__file__).parent / "scripts" / "bue2" / "citeo_email_extractor.py",
    }
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = Path(__file__).parent / "requirements.txt"
TOOL_REQUIRED_PYTHON_MODULES = {
    ("BUE1", "ear_declaration_data_fetcher"): ("playwright", "openpyxl"),
    ("CONSULT", "invoice_recognizer"): ("fitz", "openai"),
}


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
    # BUE2 email extractor fields
    email: Optional[str] = None
    authCode: Optional[str] = None
    maxEmails: Optional[int] = None
    subjectKeyword: Optional[str] = None
    selectedFolder: Optional[str] = None


class FileSelectRequest(BaseModel):
    fileType: Optional[str] = "excel"


class RunToolRequest(BaseModel):
    configOverride: Optional[ConfigRequest] = None


def _iter_python_candidates() -> list[tuple[list[str], str]]:
    candidates: list[tuple[list[str], str]] = []
    seen: set[tuple[str, ...]] = set()

    def add_candidate(command: list[str], label: str) -> None:
        key = tuple(command)
        if not command or key in seen:
            return
        seen.add(key)
        candidates.append((command, label))

    for env_name in ("YISI_TOOL_PYTHON_BIN", "YISI_PYTHON_BIN"):
        candidate = (os.environ.get(env_name) or "").strip()
        if candidate:
            add_candidate([candidate], candidate)

    venv_windows = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    venv_posix = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_windows.exists():
        add_candidate([str(venv_windows)], str(venv_windows))
    if venv_posix.exists():
        add_candidate([str(venv_posix)], str(venv_posix))

    add_candidate([sys.executable], sys.executable)

    if shutil.which("python"):
        add_candidate(["python"], "python")
    if shutil.which("py"):
        add_candidate(["py", "-3"], "py -3")

    return candidates


def _python_candidate_supports_modules(command: list[str], modules: tuple[str, ...]) -> bool:
    if not modules:
        return True

    probe_code = (
        "import importlib.util, sys;"
        "missing=[name for name in sys.argv[1:] if importlib.util.find_spec(name) is None];"
        "raise SystemExit(0 if not missing else 1)"
    )

    try:
        result = subprocess.run(
            [*command, "-c", probe_code, *modules],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return result.returncode == 0


def _resolve_tool_python_command(department: str, tool: str) -> tuple[list[str], str]:
    required_modules = TOOL_REQUIRED_PYTHON_MODULES.get((department.upper(), tool), ())
    if not required_modules:
        return [sys.executable], sys.executable

    candidates = _iter_python_candidates()
    attempted_labels: list[str] = []
    install_target = candidates[0][1] if candidates else sys.executable

    for command, label in candidates:
        attempted_labels.append(label)
        if _python_candidate_supports_modules(command, required_modules):
            return command, label

    requirements_path = REQUIREMENTS_FILE
    install_command = (
        f'{install_target} -m pip install --upgrade --force-reinstall -r "{requirements_path}"'
        if requirements_path.exists()
        else f"{install_target} -m pip install --upgrade --force-reinstall {' '.join(required_modules)}"
    )
    attempted_text = ", ".join(attempted_labels) if attempted_labels else sys.executable
    raise RuntimeError(
        "未找到可执行该工具的 Python 环境。\n"
        f"工具: {department}/{tool}\n"
        f"缺少模块: {', '.join(required_modules)}\n"
        f"已尝试解释器: {attempted_text}\n"
        f"建议修复命令: {install_command}"
    )


def _config_file(department: str, tool: str) -> Path:
    return CONFIG_DIR / f"{department}_{tool}.json"


def _config_payload(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _read_tool_config(department: str, tool: str) -> Optional[dict]:
    config_file = _config_file(department, tool)
    if not config_file.exists():
        return None

    with open(config_file, "r", encoding="utf-8") as file:
        return json.load(file)


def _read_department_config(department: str) -> Optional[dict]:
    """读取部门配置"""
    config_file = _department_config_file(department)
    if not config_file.exists():
        return None

    with open(config_file, "r", encoding="utf-8") as file:
        return json.load(file)


def _load_runtime_limits() -> dict:
    default_limits = {
        "global": 2,
        "perDepartment": 1,
        "perTool": 1,
    }

    if not RUNTIME_LIMITS_FILE.exists():
        return default_limits

    try:
        with open(RUNTIME_LIMITS_FILE, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return default_limits

    return {
        "global": max(1, int(payload.get("global", default_limits["global"]))),
        "perDepartment": max(1, int(payload.get("perDepartment", default_limits["perDepartment"]))),
        "perTool": max(1, int(payload.get("perTool", default_limits["perTool"]))),
    }


def _merge_tool_config(base_config: Optional[dict], override_model: Optional[ConfigRequest]) -> dict:
    merged = dict(base_config or {})
    if not override_model:
        return merged

    override_payload = _config_payload(override_model)
    for key, value in override_payload.items():
        if value is not None:
            merged[key] = value
    return merged


def _get_tool_storage_policy(department: str, tool: str) -> dict:
    return TOOL_STORAGE_POLICIES.get((department.upper(), tool), {})


def _validate_network_path_or_raise(path_value: str) -> Path:
    target_path = _normalize_absolute_path_or_raise(path_value, "部门局域网路径")
    if not target_path.exists():
        raise FileNotFoundError("路径不存在，请检查路径是否正确")

    if not target_path.is_dir():
        raise NotADirectoryError("路径不是有效的文件夹")

    _ensure_readable_directory(target_path, "部门局域网路径")
    _ensure_writable_directory(target_path, "部门局域网路径")

    return target_path


def _normalize_absolute_path_or_raise(path_value: str, label: str) -> Path:
    path = (path_value or "").strip()
    if len(path) >= 2 and path[0] == path[-1] and path[0] in ('"', "'"):
        path = path[1:-1].strip()
    if not path:
        raise ValueError(f"{label}未配置，请填写部署电脑可访问的真实绝对路径。")

    expanded_path = str(Path(path).expanduser()) if path.startswith("~") else path
    is_unc_path = expanded_path.startswith(r"\\")
    is_posix_path = expanded_path.startswith("/")
    is_windows_drive = len(expanded_path) > 2 and expanded_path[1] == ":" and expanded_path[2] in ["\\", "/"]

    if not (is_unc_path or is_posix_path or is_windows_drive):
        raise ValueError(
            f"{label}格式错误：请填写部署电脑可访问的真实绝对路径。"
            "推荐使用 Windows 路径，例如 \\\\服务器\\共享文件夹\\顾问部 或 D:\\工作目录\\顾问部。"
        )

    if is_unc_path and os.name != "nt":
        raise ValueError(
            "当前后端不是运行在 Windows 上，因此无法在本机校验 UNC 路径。"
            "请改用当前机器可访问的挂载路径，或在 Windows 部署机上再测试该共享路径。"
        )

    return Path(expanded_path)


def _ensure_readable_directory(path: Path, label: str) -> None:
    try:
        entries = path.iterdir()
        next(entries, None)
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


def _validate_invoice_recognizer_config_or_raise(config: dict) -> dict:
    folder_path_text = (config.get("folderPath") or "").strip()
    excel_path_text = (config.get("excelPath") or config.get("listExcelPath") or "").strip()

    folder_path = _normalize_absolute_path_or_raise(folder_path_text, "递延税单据总文件夹")
    excel_path = _normalize_absolute_path_or_raise(excel_path_text, "Excel 清单文件")

    if not folder_path.exists():
        raise FileNotFoundError(f"递延税单据总文件夹不存在: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"递延税单据总文件夹不是有效目录: {folder_path}")

    if not excel_path.exists():
        raise FileNotFoundError(f"Excel 清单文件不存在: {excel_path}")
    if not excel_path.is_file():
        raise FileNotFoundError(f"Excel 清单路径不是有效文件: {excel_path}")
    if excel_path.suffix.lower() != ".xlsx":
        raise ValueError("当前仅支持读取 .xlsx 格式的 Excel 清单文件。")

    _ensure_readable_directory(folder_path, "递延税单据总文件夹")
    _ensure_writable_directory(folder_path, "递延税单据总文件夹")
    _ensure_readable_file(excel_path, "Excel 清单文件")

    normalized_config = dict(config)
    normalized_folder_path = str(folder_path)
    normalized_excel_path = str(excel_path)
    normalized_config["folderPath"] = normalized_folder_path
    normalized_config["folderDisplay"] = normalized_folder_path
    normalized_config["excelPath"] = normalized_excel_path
    normalized_config["listExcelPath"] = normalized_excel_path
    normalized_config["listExcelDisplay"] = normalized_excel_path
    return normalized_config


def _validate_ear_declaration_data_fetcher_config_or_raise(config: dict) -> dict:
    excel_file_path_text = (config.get("excelFilePath") or config.get("excelFolderPath") or "").strip()
    report_year = str(config.get("reportYear") or "").strip()
    report_month_german = str(config.get("reportMonthGerman") or "").strip()
    excel_file_path = _normalize_absolute_path_or_raise(excel_file_path_text, "EAR 申报数据 Excel 文件")
    if not excel_file_path.exists():
        raise FileNotFoundError(f"EAR 申报数据 Excel 文件不存在: {excel_file_path}")
    if not excel_file_path.is_file():
        raise FileNotFoundError(f"EAR 申报数据 Excel 路径不是有效文件: {excel_file_path}")
    if excel_file_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("EAR 申报数据 Excel 文件必须是 .xlsx 或 .xlsm 文件。")
    if not report_year:
        raise ValueError("EAR 抓取配置中的年份不能为空。")
    if not report_month_german:
        raise ValueError("EAR 抓取配置中的德语月份不能为空。")

    _ensure_readable_file(excel_file_path, "EAR 申报数据 Excel 文件")

    normalized_config = dict(config)
    normalized_excel_file_path = str(excel_file_path)
    normalized_config["excelFilePath"] = normalized_excel_file_path
    normalized_config["excelFileDisplay"] = normalized_excel_file_path
    normalized_config["excelFolderPath"] = normalized_excel_file_path
    normalized_config["excelFolderDisplay"] = normalized_excel_file_path
    normalized_config["reportYear"] = report_year
    normalized_config["reportMonthGerman"] = report_month_german
    return normalized_config


def _validate_tool_config_or_raise(department: str, tool: str, config: dict) -> dict:
    normalized_config = dict(config or {})

    if department.upper() == "BUE1" and tool == "ear_declaration_data_fetcher":
        return _validate_ear_declaration_data_fetcher_config_or_raise(normalized_config)

    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        return _validate_invoice_recognizer_config_or_raise(normalized_config)

    return normalized_config


def _ensure_tool_network_root(department: str, tool: str) -> tuple[dict, Path]:
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


def _validate_network_bound_config(department: str, tool: str, config: dict, network_root: Path) -> None:
    policy = _get_tool_storage_policy(department, tool)
    if not policy.get("inputs_must_live_in_network_path"):
        return

    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        required_paths = [
            ("递延税单据总文件夹", (config.get("folderPath") or "").strip()),
            ("Excel 清单文件", (config.get("excelPath") or config.get("listExcelPath") or "").strip()),
        ]

        for label, path_value in required_paths:
            if not path_value:
                raise ValueError(f"{label}未配置，请先填写部门共享盘中的真实路径。")
            if not _is_path_within_root(path_value, network_root):
                raise ValueError(
                    f"{label}不在部门共享盘目录下，请改为填写部门共享盘中的真实路径后再运行。\n当前路径: {path_value}\n"
                    f"共享盘根目录: {network_root}"
                )


def _shorten_path(path_value: Optional[str], limit: int = 56) -> str:
    if not path_value:
        return "未设置"

    if len(path_value) <= limit:
        return path_value

    return f"...{path_value[-(limit - 3):]}"


def _build_preview_payload(department: str, tool: str, config: Optional[dict]) -> dict:
    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        folder_path = (config or {}).get("folderPath", "")
        excel_path = (config or {}).get("excelPath", "") or (config or {}).get("listExcelPath", "")
        configured = bool(folder_path and excel_path)

        return {
            "success": True,
            "preview": {
                "eyebrow": "Consult Automation",
                "title": "英德单据识别预览",
                "summary": "预览层先即时打开，再异步补齐配置与执行说明，避免点击后出现明显顿挫。",
                "configured": configured,
                "metrics": [
                    {
                        "label": "打开策略",
                        "value": "先开壳后补数",
                        "detail": "把首次可感知反馈放在最前面",
                    },
                    {
                        "label": "执行方式",
                        "value": "异步触发脚本",
                        "detail": "预览和运行解耦，减少阻塞链路",
                    },
                    {
                        "label": "缓存状态",
                        "value": "支持预热",
                        "detail": "页签激活后即可提前准备预览摘要",
                    },
                ],
                "stages": [
                    {
                        "name": "Step 1 · 秒开预览容器",
                        "description": "点击后先打开预览壳体和骨架屏，让用户立即感知到响应。",
                    },
                    {
                        "name": "Step 2 · 读取配置摘要",
                        "description": "异步检查源文件夹和 Excel 输出路径是否齐备。",
                    },
                    {
                        "name": "Step 3 · 正式执行识别",
                        "description": "确认无误后再触发识别脚本，运行反馈改走非阻塞提示。",
                    },
                ],
                "checklist": [
                    "源单据文件夹已选择，且当前环境可以访问",
                    "Excel 输出位置已配置，避免执行时再补参数",
                    "运行反馈使用页面内提示，不再依赖阻塞式弹窗",
                ],
                "inputs": [
                    {"label": "源文件夹", "value": _shorten_path(folder_path)},
                    {"label": "Excel 输出", "value": _shorten_path(excel_path)},
                    {"label": "配置完整度", "value": "已齐备" if configured else "仍需补全"},
                ],
            },
        }

    if department.upper() == "BUE2" and tool == "citeo_email_extractor":
        email = (config or {}).get("email", "")
        auth_code = (config or {}).get("authCode", "")
        max_emails = (config or {}).get("maxEmails", 50)
        subject_keyword = (config or {}).get("subjectKeyword", "")
        configured = bool(email and auth_code)

        # 隐藏授权码显示
        masked_auth = "已设置" if auth_code else "未设置"

        return {
            "success": True,
            "preview": {
                "eyebrow": "BUE2 Automation",
                "title": "FR-Citeo-注销成功名单邮件提取",
                "summary": "通过IMAP协议连接163邮箱，自动提取主题包含指定关键词的邮件，解析注销成功名单信息。",
                "configured": configured,
                "metrics": [
                    {
                        "label": "连接方式",
                        "value": "IMAP SSL",
                        "detail": "使用163邮箱IMAP服务，端口993",
                    },
                    {
                        "label": "认证方式",
                        "value": "授权码登录",
                        "detail": "使用邮箱授权码而非密码，更安全",
                    },
                    {
                        "label": "邮件筛选",
                        "value": "主题关键词匹配",
                        "detail": "只处理主题包含指定关键词的邮件",
                    },
                ],
                "stages": [
                    {
                        "name": "Step 1 · 测试IMAP连接",
                        "description": "验证邮箱账号和授权码是否正确，确保可以正常连接163邮箱服务器。",
                    },
                    {
                        "name": "Step 2 · 搜索邮件",
                        "description": "获取收件箱邮件列表，按日期倒序处理最新的N封邮件。",
                    },
                    {
                        "name": "Step 3 · 提取注销名单",
                        "description": "解析邮件正文，提取包含'注销成功'相关的名单信息。",
                    },
                ],
                "checklist": [
                    "已配置163邮箱账号（格式：xxx@163.com）",
                    "已获取并配置邮箱授权码（非登录密码）",
                    "邮件数量限制合理（建议50-200封）",
                    "主题关键词配置正确（如：注销成功）",
                ],
                "inputs": [
                    {"label": "邮箱账号", "value": email or "未设置"},
                    {"label": "授权码", "value": masked_auth},
                    {"label": "邮件数量", "value": str(max_emails)},
                    {"label": "主题关键词", "value": subject_keyword or "无"},
                    {"label": "配置完整度", "value": "已齐备" if configured else "仍需补全"},
                ],
            },
        }

    return {"success": False, "error": f"Preview not available for {department}/{tool}"}


def _build_bue1_ear_template_workbook_bytes() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "EAR模板"

    headers = [
        "授权代表\nbevollmächtigter Vertreter",
        "WEEE号\nWEEE-Nummer",
        "中文名\nFirmenname auf Chinesisch",
        "英文名\nFirmenname auf Englisch",
        "月份",
        "类别\nKategorie",
        "德语类目",
        "账号",
        "密码",
        "*月申报数据",
        "官网上抓取的数据（*月）",
    ]

    worksheet.append(headers)

    for cell in worksheet[1]:
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    column_widths = {
        "A": 24,
        "B": 20,
        "C": 28,
        "D": 28,
        "E": 12,
        "F": 20,
        "G": 36,
        "H": 16,
        "I": 16,
        "J": 18,
        "K": 24,
    }
    for column, width in column_widths.items():
        worksheet.column_dimensions[column].width = width

    worksheet.row_dimensions[1].height = 36

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    buffer.seek(0)
    return buffer.getvalue()


@app.get("/")
def read_root():
    return {"message": ""}


@app.get("/api/health")
def read_health():
    return {"message": ""}


@app.get("/api/departments/{department}/tools")
def list_tools(department: str):
    scripts = DEPARTMENT_SCRIPTS.get(department.upper(), {})
    tools = []

    for tool_id, script_path in scripts.items():
        tools.append(
            {
                "id": tool_id,
                "name": tool_id.replace("_", " ").title(),
                "path": str(script_path),
                "available": script_path.exists(),
            }
        )

    return {"department": department, "tools": tools}


def _run_script_async(log_id: str, department: str, tool: str, script_path: Path, env: dict, config: dict):
    """在后台线程中运行脚本"""
    start_time = time.time()
    process = None
    dt_start = datetime.now()

    def extract_error_message(stdout: str, stderr: str) -> str:
        if stderr and stderr.strip():
            return stderr.strip()

        if stdout and stdout.strip():
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            if lines:
                return lines[-1]

        return "Unknown error"

    try:
        # 启动进程
        python_command, python_label = _resolve_tool_python_command(department, tool)
        run_env = env.copy()
        run_env["YISI_TOOL_PYTHON_BIN_RESOLVED"] = python_label

        process = subprocess.Popen(
            [*python_command, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=run_env,
        )

        # 注册活跃进程（传入开始时间）
        register_active_process(log_id, process, department, tool, dt_start, config=config)
        
        # 等待进程完成
        stdout, stderr = process.communicate()

        duration = time.time() - start_time
        success = process.returncode == 0

        # 检查是否被用户手动终止
        manual_terminated = is_manual_terminated(log_id)
        if not success and manual_terminated:
            final_status = "terminated"
            error_msg = "用户手动终止流程"
        elif not success:
            final_status = "failed"
            error_msg = extract_error_message(stdout, stderr)
        else:
            final_status = "success"
            error_msg = None

        # 记录执行结果
        log_execution(
            department=department,
            tool=tool,
            config=config,
            status=final_status,
            output=stdout or "",
            error=error_msg,
            duration=duration,
            log_id=log_id,
        )
        
    except subprocess.TimeoutExpired:
        if process:
            process.terminate()
            try:
                process.wait(timeout=3)
            except:
                process.kill()
                process.wait()
        
        duration = time.time() - start_time
        log_execution(
            department=department,
            tool=tool,
            config=config,
            status="failed",
            output="",
            error="Script execution timeout",
            duration=duration,
            log_id=log_id,
        )
    except Exception as error:
        duration = time.time() - start_time
        log_execution(
            department=department,
            tool=tool,
            config=config,
            status="failed",
            output="",
            error=str(error),
            duration=duration,
            log_id=log_id,
        )
    finally:
        unregister_process(log_id)


def _run_script_async_live(log_id: str, department: str, tool: str, script_path: Path, env: dict, config: dict):
    """在后台线程中运行脚本，并持续收集实时输出。"""
    start_time = time.time()
    process = None
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    dt_start = datetime.now()
    stdout_log_path = Path(env["YISI_STDOUT_LOG_PATH"]) if env.get("YISI_STDOUT_LOG_PATH") else None
    stderr_log_path = Path(env["YISI_STDERR_LOG_PATH"]) if env.get("YISI_STDERR_LOG_PATH") else None

    def extract_error_message(stdout: str, stderr: str) -> str:
        if stderr and stderr.strip():
            return stderr.strip()

        if stdout and stdout.strip():
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            if lines:
                return lines[-1]

        return "Unknown error"

    def forward_stream(stream, chunks: list[str], stream_name: str, target_path: Optional[Path]) -> None:
        file_handle = None
        try:
            if target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                file_handle = open(target_path, "a", encoding="utf-8")

            for line in iter(stream.readline, ""):
                chunks.append(line)
                append_process_output(log_id, line, stream=stream_name)
                if file_handle:
                    file_handle.write(line)
                    file_handle.flush()
        finally:
            if file_handle:
                file_handle.close()
            stream.close()

    try:
        run_env = env.copy()
        run_env["PYTHONUNBUFFERED"] = "1"
        run_env["PYTHONIOENCODING"] = "utf-8"
        run_env["PYTHONUTF8"] = "1"

        python_command, python_label = _resolve_tool_python_command(department, tool)
        run_env["YISI_TOOL_PYTHON_BIN_RESOLVED"] = python_label

        process = subprocess.Popen(
            [*python_command, "-X", "utf8", "-u", str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=run_env,
        )

        register_active_process(log_id, process, department, tool, dt_start, config=config)

        stdout_thread = threading.Thread(
            target=forward_stream,
            args=(process.stdout, stdout_chunks, "stdout", stdout_log_path),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=forward_stream,
            args=(process.stderr, stderr_chunks, "stderr", stderr_log_path),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        process.wait()
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        duration = time.time() - start_time
        success = process.returncode == 0

        manual_terminated = is_manual_terminated(log_id)
        if not success and manual_terminated:
            final_status = "terminated"
            error_msg = "用户手动终止流程"
        elif not success:
            final_status = "failed"
            error_msg = extract_error_message(stdout, stderr)
        else:
            final_status = "success"
            error_msg = None

        log_execution(
            department=department,
            tool=tool,
            config=config,
            status=final_status,
            output=stdout or "",
            error=error_msg,
            duration=duration,
            log_id=log_id,
        )
    except Exception as error:
        duration = time.time() - start_time
        log_execution(
            department=department,
            tool=tool,
            config=config,
            status="failed",
            output="".join(stdout_chunks),
            error=str(error),
            duration=duration,
            log_id=log_id,
        )
    finally:
        unregister_process(log_id)


def _run_queued_job(job: dict) -> None:
    _run_script_async_live(
        job["log_id"],
        job["department"],
        job["tool"],
        job["script_path"],
        job["env"],
        job["config"],
    )


@app.post("/api/departments/{department}/tools/{tool}/run")
def run_tool(department: str, tool: str, payload: Optional[RunToolRequest] = None):
    normalized_department = department.upper()
    dept_scripts = DEPARTMENT_SCRIPTS.get(normalized_department)
    if not dept_scripts:
        return {"success": False, "error": f"Department {department} not found"}

    script_path = dept_scripts.get(tool)
    if not script_path or not script_path.exists():
        return {"success": False, "error": f"Tool {tool} not found for department {department}"}

    # 读取工具配置和部门配置
    config = _merge_tool_config(
        _read_tool_config(normalized_department, tool) or {},
        payload.configOverride if payload else None,
    )
    try:
        config = _validate_tool_config_or_raise(normalized_department, tool, config)
        dept_config = _read_department_config(normalized_department)
        network_path = dept_config.get("networkPath", "") if dept_config else ""
        policy = _get_tool_storage_policy(normalized_department, tool)
        validated_network_root = None
        if policy.get("requires_network_path"):
            dept_config, validated_network_root = _ensure_tool_network_root(normalized_department, tool)
            network_path = str(validated_network_root)
            _validate_network_bound_config(normalized_department, tool, config, validated_network_root)
    except Exception as error:
        return {"success": False, "error": str(error)}
    runtime_limits = _load_runtime_limits()
    TASK_QUEUE.update_limits(
        global_limit=runtime_limits["global"],
        department_limit=runtime_limits["perDepartment"],
        tool_limit=runtime_limits["perTool"],
    )

    # 为单次运行准备隔离目录和配置快照
    log_id = f"{time.time()}_{tool}"
    runtime_bundle = prepare_runtime_bundle(normalized_department, tool, log_id, config)

    # 准备环境变量
    env = os.environ.copy()
    env["YISI_DEPT_NETWORK_PATH"] = network_path
    env["YISI_TOOL_ID"] = tool
    env["YISI_DEPARTMENT"] = normalized_department
    env["YISI_RUN_ID"] = log_id
    env["YISI_RUNTIME_DIR"] = str(runtime_bundle["runtime_dir"])
    env["YISI_CONFIG_PATH"] = str(runtime_bundle["config_path"])
    env["YISI_DOWNLOAD_DIR"] = str(runtime_bundle["downloads_dir"])
    env["YISI_ARTIFACT_DIR"] = str(runtime_bundle["artifacts_dir"])
    env["YISI_SCREENSHOT_DIR"] = str(runtime_bundle["screenshots_dir"])
    env["YISI_BROWSER_PROFILE_DIR"] = str(runtime_bundle["browser_profile_dir"])
    env["YISI_STDOUT_LOG_PATH"] = str(runtime_bundle["stdout_log_path"])
    env["YISI_STDERR_LOG_PATH"] = str(runtime_bundle["stderr_log_path"])

    job = build_job(
        log_id=log_id,
        department=normalized_department,
        tool=tool,
        script_path=script_path,
        env=env,
        config=config,
    )
    queue_result = TASK_QUEUE.enqueue(job, _run_queued_job)

    return {
        "success": True,
        "logId": log_id,
        "message": "任务已启动" if queue_result["status"] == "running" else "任务已进入队列",
        "status": queue_result["status"],
        "queuePosition": queue_result.get("queuePosition"),
    }


@app.post("/api/executions/{log_id}/terminate")
def terminate_execution(log_id: str):
    """终止正在运行的任务"""
    if TASK_QUEUE.cancel(log_id):
        return {"success": True, "message": "排队中的任务已终止"}

    success = terminate_process(log_id)
    if success:
        return {"success": True, "message": "任务已终止"}
    return {"success": False, "error": "任务不存在或已结束"}


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
        return {
            "success": True,
            "message": "配置已保存",
            "path": str(config_file),
        }
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/tools/{tool}/config")
def get_tool_config(department: str, tool: str):
    try:
        return {"success": True, "config": _read_tool_config(department, tool)}
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
        filename = "EAR抓取配置-模板表.xlsx"
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


def _open_folder_dialog():
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
                        '$dialog.Title = "Select invoice folder (open target folder and click Open)"; '
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

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
                        '$dialog.Title = "选择递延税单据总文件夹（进入目标文件夹后直接点打开）"; '
                        '$dialog.Filter = "文件夹选择|*.folder"; '
                        "$dialog.CheckFileExists = $false; "
                        "$dialog.CheckPathExists = $true; "
                        "$dialog.ValidateNames = $false; "
                        '$dialog.FileName = "选择当前文件夹"; '
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

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
                        '$dialog.Description = "选择递延税单据总文件夹"; '
                        "$dialog.ShowNewFolderButton = $false; "
                        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
                        "Write-Output $dialog.SelectedPath "
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
                [
                    "osascript",
                    "-e",
                    'POSIX path of (choose folder with prompt "选择递延税单据总文件夹")',
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    folder_path = filedialog.askdirectory(title="选择源单据文件夹")

    root.destroy()
    return folder_path


def _open_folder_dialog_native():
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
                        '$dialog.Title = "Select invoice folder (open target folder and click Open)"; '
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
                [
                    "osascript",
                    "-e",
                    'POSIX path of (choose folder with prompt "Select invoice folder")',
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder_path = filedialog.askdirectory(title="Select invoice folder")
    root.destroy()
    return folder_path


@app.post("/api/select-folder")
async def select_folder():
    if not sys.platform.startswith("win") and sys.platform != "darwin" and not TKINTER_AVAILABLE:
        return {"success": False, "error": "Tkinter not available"}

    try:
        loop = asyncio.get_event_loop()
        folder_path = await loop.run_in_executor(executor, _open_folder_dialog_native)
        if folder_path:
            return {"success": True, "path": folder_path}
        return {"success": False, "path": None, "message": "未选择文件夹"}
    except Exception as error:
        return {"success": False, "error": str(error)}


def _open_file_dialog(file_type: str):
    if sys.platform.startswith("win"):
        prompt = "选择 Excel 输出文件" if file_type == "excel" else "选择文件"
        filter_value = "Excel 文件 (*.xlsx;*.xls)|*.xlsx;*.xls" if file_type == "excel" else "所有文件 (*.*)|*.*"
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
        prompt = "选择 Excel 输出文件" if file_type == "excel" else "选择文件"
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'POSIX path of (choose file with prompt "{prompt}")',
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    file_types = [("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
    if file_type != "excel":
        file_types = [("All files", "*.*")]

    file_path = filedialog.askopenfilename(
        title="选择 Excel 输出文件",
        filetypes=file_types,
    )

    root.destroy()
    return file_path


@app.post("/api/select-file")
async def select_file(request: FileSelectRequest):
    if not sys.platform.startswith("win") and sys.platform != "darwin" and not TKINTER_AVAILABLE:
        return {"success": False, "error": "Tkinter not available"}

    try:
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(executor, _open_file_dialog, request.fileType)
        if file_path:
            return {"success": True, "path": file_path}
        return {"success": False, "path": None, "message": "未选择文件"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/logs")
def get_execution_logs(limit: int = 20, department: Optional[str] = None):
    """获取最近的执行记录，支持按部门筛选"""
    try:
        logs = get_recent_logs(limit=limit, department=department.upper() if department else None)
        return {"success": True, "logs": logs}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/logs")
def get_department_logs(department: str, limit: int = 20):
    """获取指定部门的所有执行记录"""
    try:
        logs = get_recent_logs(limit=limit, department=department.upper())
        return {"success": True, "logs": logs}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/tools/{tool}/logs")
def get_tool_execution_logs(department: str, tool: str, limit: int = 10):
    """获取指定工具的执行记录"""
    try:
        logs = get_logs_by_tool(department.upper(), tool, limit=limit)
        return {"success": True, "logs": logs}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.delete("/api/departments/{department}/logs")
def clear_department_execution_logs(department: str):
    """清空指定部门的所有执行记录"""
    try:
        success = clear_department_logs(department.upper())
        if success:
            return {"success": True, "message": "日志已清空"}
        return {"success": False, "error": "清空日志失败"}
    except Exception as error:
        return {"success": False, "error": str(error)}


class ImapTestRequest(BaseModel):
    email: str
    authCode: str


def decode_imap_utf7(s: str) -> str:
    """解码IMAP RFC 2060 UTF-7编码的字符串"""
    import binascii

    def decode_chunk(chunk):
        # 将IMAP Base64编码转换为标准Base64
        # IMAP使用,代替/
        b64 = chunk.replace(',', '/').encode('ascii')
        # 添加填充
        pad_len = (4 - len(b64) % 4) % 4
        b64 += b'=' * pad_len
        try:
            decoded_bytes = binascii.a2b_base64(b64)
            # 将UTF-16BE转换为字符串
            return decoded_bytes.decode('utf-16-be', errors='ignore')
        except:
            return chunk

    result = []
    i = 0
    while i < len(s):
        if s[i] == '&' and i + 1 < len(s):
            # 找到编码块
            end = s.find('-', i + 1)
            if end == -1:
                result.append(s[i])
                i += 1
                continue

            encoded = s[i + 1:end]
            if encoded == '':
                # &-
                result.append('&')
            else:
                result.append(decode_chunk(encoded))
            i = end + 1
        else:
            result.append(s[i])
            i += 1

    return ''.join(result)


@app.post("/api/list-mail-folders")
def list_mail_folders_endpoint(request: ImapTestRequest):
    """获取163邮箱所有文件夹列表"""
    try:
        import imaplib
        import re

        # 验证邮箱格式
        if not re.match(r"^[\w.-]+@163\.com$", request.email):
            return {"success": False, "error": "请输入有效的163邮箱地址"}

        if not request.authCode:
            return {"success": False, "error": "授权码不能为空"}

        # 连接IMAP服务器
        mail = imaplib.IMAP4_SSL("imap.163.com", 993)
        mail.login(request.email, request.authCode)

        # 获取文件夹列表
        status, folders = mail.list()
        if status != "OK":
            mail.logout()
            return {"success": False, "error": "无法获取文件夹列表"}

        folder_list = []
        for folder in folders:
            try:
                folder_str = folder.decode()
                # 解析文件夹名称（通常在最后一个引号中）
                parts = folder_str.split('"')
                if len(parts) >= 2:
                    encoded_name = parts[-2]
                    decoded_name = decode_imap_utf7(encoded_name)
                    # 标记常用文件夹
                    folder_type = "other"
                    if decoded_name in ["INBOX", "收件箱"]:
                        folder_type = "inbox"
                    elif decoded_name in ["Sent", "已发送", "&XfJT0ZAB-"]:
                        folder_type = "sent"
                    elif decoded_name in ["Drafts", "草稿箱", "&g0l6P3ux-"]:
                        folder_type = "drafts"
                    elif decoded_name in ["Trash", "已删除", "Deleted"]:
                        folder_type = "trash"

                    folder_list.append({
                        "encoded": encoded_name,
                        "display": decoded_name,
                        "type": folder_type
                    })
            except:
                continue

        mail.logout()

        # 排序：inbox优先，其他按名称排序
        folder_list.sort(key=lambda x: (0 if x["type"] == "inbox" else 1, x["display"]))

        return {"success": True, "folders": folder_list}

    except imaplib.IMAP4.error as e:
        error_msg = str(e)
        if "authentication failed" in error_msg.lower() or "login error" in error_msg.lower() or "password error" in error_msg.lower():
            friendly_error = "登录失败：邮箱账号或授权码错误，请检查后重试"
        elif "not enabled" in error_msg.lower():
            friendly_error = "登录失败：IMAP服务未开启，请前往163邮箱设置中开启"
        else:
            friendly_error = f"登录失败：{error_msg}"
        return {"success": False, "error": friendly_error}
    except Exception as error:
        return {"success": False, "error": f"获取文件夹列表失败：{str(error)}"}


class DepartmentConfig(BaseModel):
    """部门配置模型"""
    networkPath: Optional[str] = None


class NetworkPathTestRequest(BaseModel):
    """测试网络路径请求"""
    path: str


def _department_config_file(department: str) -> Path:
    """获取部门配置文件路径"""
    return CONFIG_DIR / f"{department}_config.json"


@app.post("/api/departments/{department}/config")
def save_department_config(department: str, config: DepartmentConfig):
    """保存部门配置"""
    try:
        normalized_department = department.upper()
        config_file = _department_config_file(normalized_department)
        payload = _config_payload(config)
        network_path = (payload.get("networkPath") or "").strip()
        if network_path:
            payload["networkPath"] = str(_validate_network_path_or_raise(network_path))
        else:
            payload["networkPath"] = ""
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"success": True, "message": "部门配置已保存"}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.get("/api/departments/{department}/config")
def get_department_config(department: str):
    """获取部门配置"""
    try:
        config_file = _department_config_file(department)
        if not config_file.exists():
            return {"success": True, "config": {}}
        with open(config_file, "r", encoding="utf-8") as f:
            return {"success": True, "config": json.load(f)}
    except Exception as error:
        return {"success": False, "error": str(error)}


@app.post("/api/test-network-path")
def test_network_path(request: NetworkPathTestRequest):
    """测试网络路径是否可访问"""
    try:
        _validate_network_path_or_raise(request.path)
        return {"success": True, "message": "网络路径连接成功，可正常读写，记得保存配置"}
    except Exception as error:
        return {"success": False, "error": f"测试失败：{str(error)}"}
