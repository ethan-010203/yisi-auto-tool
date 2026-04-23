from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from runner.runtime_limits import load_runtime_limits
    from runner.sqlite_store import (
        append_execution_output,
        claim_next_execution,
        finalize_execution,
        init_db,
        is_cancel_requested,
        set_execution_process_info,
    )
except ModuleNotFoundError:
    from .runner.runtime_limits import load_runtime_limits
    from .runner.sqlite_store import (
        append_execution_output,
        claim_next_execution,
        finalize_execution,
        init_db,
        is_cancel_requested,
        set_execution_process_info,
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = Path(__file__).parent / "requirements.txt"
CONFIG_DIR = Path(__file__).parent / "configs"

TOOL_REQUIRED_PYTHON_MODULES = {
    ("BUE1", "ear_declaration_data_fetcher"): ("playwright", "openpyxl"),
    ("CONSULT", "invoice_recognizer"): ("fitz", "openai"),
}


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
        "No compatible Python interpreter was found for this tool.\n"
        f"Tool: {department}/{tool}\n"
        f"Required modules: {', '.join(required_modules)}\n"
        f"Tried: {attempted_text}\n"
        f"Suggested install command: {install_command}"
    )


def _extract_error_message(stdout: str, stderr: str) -> str:
    if stderr and stderr.strip():
        return stderr.strip().splitlines()[-1]
    if stdout and stdout.strip():
        return stdout.strip().splitlines()[-1]
    return "Unknown error"


def _run_execution(job: dict[str, object], worker_id: str) -> None:
    execution_id = str(job["id"])
    department = str(job["department"])
    tool = str(job["tool"])
    script_path = str(job["script_path"])
    env_overrides = dict(job.get("env") or {})
    start_time = time.time()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    process: subprocess.Popen[str] | None = None
    manual_terminated = False

    stdout_log_path = Path(env_overrides["YISI_STDOUT_LOG_PATH"]) if env_overrides.get("YISI_STDOUT_LOG_PATH") else None
    stderr_log_path = Path(env_overrides["YISI_STDERR_LOG_PATH"]) if env_overrides.get("YISI_STDERR_LOG_PATH") else None

    def forward_stream(stream, chunks: list[str], stream_name: str, target_path: Path | None) -> None:
        file_handle = None
        try:
            if target_path:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                file_handle = open(target_path, "a", encoding="utf-8")

            for line in iter(stream.readline, ""):
                chunks.append(line)
                append_execution_output(execution_id, line, stream=stream_name)
                if file_handle:
                    file_handle.write(line)
                    file_handle.flush()
        finally:
            if file_handle:
                file_handle.close()
            stream.close()

    try:
        python_command, python_label = _resolve_tool_python_command(department, tool)
        run_env = os.environ.copy()
        run_env.update(env_overrides)
        run_env["PYTHONUNBUFFERED"] = "1"
        run_env["PYTHONIOENCODING"] = "utf-8"
        run_env["PYTHONUTF8"] = "1"
        run_env["YISI_TOOL_PYTHON_BIN_RESOLVED"] = python_label
        run_env["YISI_WORKER_ID"] = worker_id

        process = subprocess.Popen(
            [*python_command, "-X", "utf8", "-u", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=run_env,
        )
        set_execution_process_info(execution_id, process_id=process.pid)

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

        while process.poll() is None:
            if is_cancel_requested(execution_id):
                manual_terminated = True
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            time.sleep(0.5)

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        duration = time.time() - start_time
        exit_code = process.returncode if process else None
        success = exit_code == 0

        if manual_terminated:
            final_status = "terminated"
            error_message = "任务已取消"
        elif success:
            final_status = "success"
            error_message = None
        else:
            final_status = "failed"
            error_message = _extract_error_message(stdout, stderr)

        finalize_execution(
            execution_id,
            status=final_status,
            output=stdout,
            error=error_message,
            duration=duration,
            exit_code=exit_code,
        )
    except Exception as error:
        finalize_execution(
            execution_id,
            status="failed",
            output="".join(stdout_chunks),
            error=str(error),
            duration=time.time() - start_time,
            exit_code=process.returncode if process else None,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued Yisi automation tasks.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between queue polls when idle.")
    args = parser.parse_args()

    init_db()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    print(f"[worker] started: {worker_id}", flush=True)

    while True:
        limits = load_runtime_limits(CONFIG_DIR)
        job = claim_next_execution(
            worker_id=worker_id,
            global_limit=limits["global"],
            department_limit=limits["perDepartment"],
            tool_limit=limits["perTool"],
        )
        if not job:
            time.sleep(max(0.2, args.poll_interval))
            continue

        print(
            f"[worker] executing {job['department']}/{job['tool']} ({job['id']})",
            flush=True,
        )
        _run_execution(job, worker_id)


if __name__ == "__main__":
    main()
