from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from runner.logger import get_recent_logs, get_logs_by_tool, log_execution

try:
    import tkinter as tk
    from tkinter import filedialog

    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False


app = FastAPI()

CONFIG_DIR = Path(__file__).parent / "configs"
CONFIG_DIR.mkdir(exist_ok=True)

executor = ThreadPoolExecutor(max_workers=2)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEPARTMENT_SCRIPTS = {
    "CONSULT": {
        "test_hello": Path(__file__).parent / "scripts" / "consult" / "test_hello.py",
        "invoice_recognizer": Path(__file__).parent / "scripts" / "consult" / "invoice_recognizer.py",
    }
}


class ConfigRequest(BaseModel):
    folderPath: str
    excelPath: str


class FileSelectRequest(BaseModel):
    fileType: Optional[str] = "excel"


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


def _shorten_path(path_value: Optional[str], limit: int = 56) -> str:
    if not path_value:
        return "未设置"

    if len(path_value) <= limit:
        return path_value

    return f"...{path_value[-(limit - 3):]}"


def _build_preview_payload(department: str, tool: str, config: Optional[dict]) -> dict:
    if department.upper() == "CONSULT" and tool == "invoice_recognizer":
        folder_path = (config or {}).get("folderPath", "")
        excel_path = (config or {}).get("excelPath", "")
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

    return {"success": False, "error": f"Preview not available for {department}/{tool}"}


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/api/health")
def read_health():
    return {"message": "Hello World"}


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


@app.post("/api/departments/{department}/tools/{tool}/run")
def run_tool(department: str, tool: str):
    dept_scripts = DEPARTMENT_SCRIPTS.get(department.upper())
    if not dept_scripts:
        return {"success": False, "error": f"Department {department} not found"}

    script_path = dept_scripts.get(tool)
    if not script_path or not script_path.exists():
        return {"success": False, "error": f"Tool {tool} not found for department {department}"}

    # 读取配置用于记录
    config = _read_tool_config(department, tool)
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        duration = time.time() - start_time
        success = result.returncode == 0
        
        # 记录执行日志
        log_execution(
            department=department.upper(),
            tool=tool,
            config=config,
            status="success" if success else "failed",
            output=result.stdout if success else result.stderr,
            error=None if success else (result.stderr or "Unknown error"),
            duration=duration,
        )
        
        return {
            "success": success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        error_msg = "Script execution timeout"
        
        log_execution(
            department=department.upper(),
            tool=tool,
            config=config,
            status="failed",
            output="",
            error=error_msg,
            duration=duration,
        )
        
        return {"success": False, "error": error_msg}
    except Exception as error:
        duration = time.time() - start_time
        error_msg = str(error)
        
        log_execution(
            department=department.upper(),
            tool=tool,
            config=config,
            status="failed",
            output="",
            error=error_msg,
            duration=duration,
        )
        
        return {"success": False, "error": error_msg}


@app.post("/api/departments/{department}/tools/{tool}/config")
def save_tool_config(department: str, tool: str, config: ConfigRequest):
    config_file = _config_file(department, tool)

    try:
        with open(config_file, "w", encoding="utf-8") as file:
            json.dump(_config_payload(config), file, ensure_ascii=False, indent=2)
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


def _open_folder_dialog():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    folder_path = filedialog.askdirectory(title="选择源单据文件夹")

    root.destroy()
    return folder_path


@app.post("/api/select-folder")
async def select_folder():
    if not TKINTER_AVAILABLE:
        return {"success": False, "error": "Tkinter not available"}

    try:
        loop = asyncio.get_event_loop()
        folder_path = await loop.run_in_executor(executor, _open_folder_dialog)
        if folder_path:
            return {"success": True, "path": folder_path}
        return {"success": False, "path": None, "message": "未选择文件夹"}
    except Exception as error:
        return {"success": False, "error": str(error)}


def _open_file_dialog(file_type: str):
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
    if not TKINTER_AVAILABLE:
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
