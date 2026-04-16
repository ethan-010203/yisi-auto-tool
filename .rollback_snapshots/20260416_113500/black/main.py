from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


class ConfigRequest(BaseModel):
    folderPath: Optional[str] = None
    excelPath: Optional[str] = None
    listExcelPath: Optional[str] = None
    # BUE2 email extractor fields
    email: Optional[str] = None
    authCode: Optional[str] = None
    maxEmails: Optional[int] = None
    subjectKeyword: Optional[str] = None
    selectedFolder: Optional[str] = None


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


def _read_department_config(department: str) -> Optional[dict]:
    """读取部门配置"""
    config_file = _department_config_file(department)
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
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
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

        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-u", str(script_path)],
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
def run_tool(department: str, tool: str):
    normalized_department = department.upper()
    dept_scripts = DEPARTMENT_SCRIPTS.get(normalized_department)
    if not dept_scripts:
        return {"success": False, "error": f"Department {department} not found"}

    script_path = dept_scripts.get(tool)
    if not script_path or not script_path.exists():
        return {"success": False, "error": f"Tool {tool} not found for department {department}"}

    # 读取工具配置和部门配置
    config = _read_tool_config(normalized_department, tool) or {}
    dept_config = _read_department_config(normalized_department)
    network_path = dept_config.get("networkPath", "") if dept_config else ""

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
        config_file = _department_config_file(department)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(_config_payload(config), f, ensure_ascii=False, indent=2)
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
        path = request.path.strip()
        if not path:
            return {"success": False, "error": "路径不能为空"}

        # 验证UNC路径格式 (\\server\share)
        if not path.startswith(r"\\"):
            return {"success": False, "error": "路径格式错误：请使用有效的局域网路径格式，如 \\\\\\服务器\\\\共享文件夹"}

        # 将路径转换为 Path 对象
        test_path = Path(path)

        # 检查路径是否存在（不自动创建）
        if not test_path.exists():
            return {"success": False, "error": "路径不存在，请检查路径是否正确"}

        # 检查是否是目录
        if not test_path.is_dir():
            return {"success": False, "error": "路径不是有效的文件夹"}

        # 尝试创建一个临时文件来测试写入权限
        test_file = test_path / ".write_test"
        try:
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()  # 删除测试文件
        except Exception as e:
            return {"success": False, "error": f"没有写入权限：{str(e)}"}

        return {"success": True, "message": "网络路径连接成功，可正常读写，记得保存配置"}

    except Exception as error:
        return {"success": False, "error": f"测试失败：{str(error)}"}
