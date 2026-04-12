"""执行日志记录模块 - 按部门独立存储"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

MAX_LOG_ENTRIES = 100  # 每个部门保留最近100条记录


def _get_log_file(department: str) -> Path:
    """获取部门的日志文件路径"""
    return LOGS_DIR / f"{department.lower()}.json"


def log_execution(
    department: str,
    tool: str,
    config: Optional[Dict],
    status: str,
    output: str,
    error: Optional[str] = None,
    duration: float = 0.0,
) -> Dict[str, Any]:
    """记录一次脚本执行到对应部门的日志文件"""
    timestamp = datetime.now().isoformat()
    
    log_entry = {
        "id": f"{timestamp}_{tool}",
        "timestamp": timestamp,
        "department": department,
        "tool": tool,
        "config": config or {},
        "status": status,  # "success" | "failed"
        "output": output[:2000] if output else "",  # 限制长度
        "error": error[:1000] if error else None,
        "duration": round(duration, 2),
    }
    
    # 读取该部门的现有日志
    logs = _read_department_logs(department)
    
    # 添加新记录到开头
    logs.insert(0, log_entry)
    
    # 限制数量
    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[:MAX_LOG_ENTRIES]
    
    # 保存到部门文件
    _write_department_logs(department, logs)
    
    return log_entry


def get_recent_logs(limit: int = 20, department: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取最近的执行记录
    
    Args:
        limit: 返回记录数量限制
        department: 指定部门，为None则返回所有部门
    """
    if department:
        return _read_department_logs(department)[:limit]
    
    # 获取所有部门的日志并合并
    all_logs = []
    for log_file in LOGS_DIR.glob("*.json"):
        dept = log_file.stem.upper()
        dept_logs = _read_department_logs(dept)
        all_logs.extend(dept_logs)
    
    # 按时间排序
    all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_logs[:limit]


def get_logs_by_tool(department: str, tool: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取指定工具的最近记录"""
    logs = _read_department_logs(department)
    filtered = [log for log in logs if log["tool"] == tool]
    return filtered[:limit]


def clear_old_logs(days: int = 30) -> Dict[str, int]:
    """清理N天前的日志，返回各部门清理数量"""
    cutoff = datetime.now().timestamp() - (days * 86400)
    total_removed = 0
    dept_removed = {}
    
    for log_file in LOGS_DIR.glob("*.json"):
        dept = log_file.stem.upper()
        logs = _read_department_logs(dept)
        
        filtered = [
            log for log in logs
            if datetime.fromisoformat(log["timestamp"]).timestamp() > cutoff
        ]
        
        removed = len(logs) - len(filtered)
        if removed > 0:
            _write_department_logs(dept, filtered)
            dept_removed[dept] = removed
            total_removed += removed
    
    dept_removed["_total"] = total_removed
    return dept_removed


def _read_department_logs(department: str) -> List[Dict[str, Any]]:
    """读取指定部门的日志文件"""
    log_file = _get_log_file(department)
    if not log_file.exists():
        return []
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_department_logs(department: str, logs: List[Dict[str, Any]]):
    """写入指定部门的日志文件"""
    log_file = _get_log_file(department)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def clear_department_logs(department: str) -> bool:
    """清空指定部门的所有日志
    
    Args:
        department: 部门代码
        
    Returns:
        是否成功清空
    """
    try:
        log_file = _get_log_file(department)
        if log_file.exists():
            _write_department_logs(department, [])
        return True
    except Exception:
        return False
