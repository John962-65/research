"""Experiment attempt records and safe resume (T06).

持久化每次真实执行尝试的任务标识、尝试编号、进程身份（PID + 命令行）、
起止时间、退出码、预算与日志路径，使恢复执行能够：
- 核对任务实际存活（/proc/<pid>/cmdline 前缀匹配，防 PID 复用误判），
  活任务不重复启动（A13）；
- 把无终端状态的旧尝试标记为 interrupted，保留全部失败尝试记录；
- 日志落盘（experiments/logs/），04-results 只保留摘要。

仅记录 local/benchmark 真实执行；simulated 不产生进程，不登记。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import time

from .artifacts import read_json, safe_int as _safe_int, utc_now as _utc_now, write_json


EXPERIMENT_ATTEMPTS_JSON = "04-experiment-attempts.json"
TERMINAL_ATTEMPT_STATUSES = frozenset({"passed", "failed", "timeout", "blocked", "cancelled", "interrupted"})


def _attempts_path(run_dir: Path) -> Path:
    return Path(run_dir) / EXPERIMENT_ATTEMPTS_JSON


def _load_attempts(run_dir: Path) -> list[dict[str, Any]]:
    try:
        data = read_json(_attempts_path(run_dir))
    except (OSError, ValueError):
        return []
    entries = data.get("attempts") if isinstance(data, dict) else None
    return [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []


def _save_attempts(run_dir: Path, attempts: list[dict[str, Any]]) -> None:
    write_json(_attempts_path(run_dir), {"schema_version": 1, "attempts": attempts})


def process_matches(pid: int, command: list[str] | str) -> bool:
    """进程存在且命令行前缀匹配才认为身份一致；仅 PID 存在不算（防 PID 复用）。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return False
    cmdline = raw.decode("utf-8", errors="replace").split("\x00")
    cmdline = [part for part in cmdline if part]
    wanted = [str(part) for part in (command if isinstance(command, list) else [command]) if str(part)]
    if not wanted or not cmdline:
        return False
    if len(cmdline) != len(wanted):
        return False
    # 复审第 8 项：完整比较命令身份——解释器按基名匹配（python3 与
    # /usr/bin/python3 等价），其余参数必须逐项精确一致且长度相同；
    # 中间脚本不同或末尾多参数都视为不同任务。
    first = cmdline[0]
    wanted_first = wanted[0]
    first_ok = (
        first == wanted_first
        or first.endswith("/" + wanted_first)
        or os.path.basename(first) == os.path.basename(wanted_first)
    )
    if not first_ok:
        return False
    return cmdline[1:] == wanted[1:]


def find_live_attempt(run_dir: Path) -> dict[str, Any] | None:
    """返回仍存活的执行尝试（进程存在且命令行匹配）；无则 None。"""
    for attempt in _load_attempts(run_dir):
        if str(attempt.get("status") or "") in TERMINAL_ATTEMPT_STATUSES:
            continue
        pid = _safe_int(attempt.get("pid"))
        if process_matches(pid, attempt.get("command") or []):
            return attempt
    return None


def mark_interrupted_attempts(run_dir: Path) -> list[dict[str, Any]]:
    """把进程已不存在的非终态尝试标记为 interrupted；返回被标记的尝试。"""
    attempts = _load_attempts(run_dir)
    marked: list[dict[str, Any]] = []
    changed = False
    for attempt in attempts:
        if str(attempt.get("status") or "") in TERMINAL_ATTEMPT_STATUSES:
            continue
        pid = _safe_int(attempt.get("pid"))
        if not process_matches(pid, attempt.get("command") or []):
            attempt["status"] = "interrupted"
            attempt["ended_at"] = attempt.get("ended_at") or _utc_now()
            attempt["interrupted_reason"] = "process_no_longer_alive_at_resume"
            marked.append(dict(attempt))
            changed = True
    if changed:
        _save_attempts(run_dir, attempts)
    return marked


def record_attempt_start(
    run_dir: Path,
    *,
    task_id: str,
    attempt_number: int,
    pid: int,
    command: list[str] | str,
    timeout_seconds: int,
    stdout_log: str = "",
    stderr_log: str = "",
) -> dict[str, Any]:
    attempts = _load_attempts(run_dir)
    entry = {
        "task_id": str(task_id),
        "attempt_number": int(attempt_number),
        "pid": int(pid),
        "command": list(command) if isinstance(command, list) else [str(command)],
        "status": "running",
        "started_at": _utc_now(),
        "started_monotonic": time.monotonic(),
        "timeout_seconds": int(timeout_seconds),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    attempts.append(entry)
    _save_attempts(run_dir, attempts)
    return entry


def record_attempt_end(
    run_dir: Path,
    *,
    task_id: str,
    attempt_number: int,
    pid: int,
    status: str,
    exit_code: int | None,
    duration_seconds: float,
) -> None:
    attempts = _load_attempts(run_dir)
    for attempt in reversed(attempts):
        if (
            str(attempt.get("task_id")) == str(task_id)
            and _safe_int(attempt.get("attempt_number")) == int(attempt_number)
            and _safe_int(attempt.get("pid")) == int(pid)
        ):
            if str(attempt.get("status") or "") in TERMINAL_ATTEMPT_STATUSES:
                # 已有终态（如 interrupted）：保留既有记录，不产生重复。
                return
            attempt["status"] = str(status)
            attempt["ended_at"] = _utc_now()
            attempt["exit_code"] = exit_code
            attempt["duration_seconds"] = round(float(duration_seconds), 3)
            attempt.pop("started_monotonic", None)
            _save_attempts(run_dir, attempts)
            return
    # 没有匹配的 running 记录（例如旧结构 run）：补一条终态记录，保留审计痕迹。
    attempts.append(
        {
            "task_id": str(task_id),
            "attempt_number": int(attempt_number),
            "pid": int(pid),
            "command": [],
            "status": str(status),
            "ended_at": _utc_now(),
            "exit_code": exit_code,
            "duration_seconds": round(float(duration_seconds), 3),
        }
    )
    _save_attempts(run_dir, attempts)


def attempts_summary(run_dir: Path) -> dict[str, Any]:
    attempts = _load_attempts(run_dir)
    counts: dict[str, int] = {}
    for attempt in attempts:
        status = str(attempt.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {"total_attempts": len(attempts), "status_counts": counts, "attempts": attempts}


def load_attempt_history(run_dir: Path) -> list[dict[str, Any]]:
    return _load_attempts(run_dir)


def dump_attempts_debug(run_dir: Path) -> str:
    return json.dumps(_load_attempts(run_dir), ensure_ascii=False, indent=1)
