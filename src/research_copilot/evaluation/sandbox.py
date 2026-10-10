"""工具执行沙箱：环境变量白名单 + 资源限额 + 尽力网络隔离（诚实标注隔离级别）。

隔离层级（按可用性降级，执行记录中如实标注）：
1. 环境变量白名单：子进程只拿到最小 env——API Key 等凭据不可能被生成代码读取；
2. 资源限额（RLIMIT_CPU / AS / FSIZE / NPROC / NOFILE）；
3. 网络隔离：若系统支持非特权 `unshare -Urn`（user+net namespace）则启用；
   不支持时如实标注 network_isolated=False（残余风险：生成代码可访问网络）。

残余风险（不假装解决）：未启用网络隔离时，模型生成的代码仍在宿主机内核内运行，
拥有当前用户的文件系统权限。正式评测/执行不可信模型代码时应使用容器级隔离
（docs/roadmap.md P2 工作区安全路径）。
"""
from __future__ import annotations

import json
import resource
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# 子进程环境白名单：只给运行 python 所必需的变量
ENV_WHITELIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "PYTHONHASHSEED")

DEFAULT_LIMITS = {
    "cpu_seconds": 60,
    "address_space_bytes": 2 * 1024**3,  # 2 GB
    "file_size_bytes": 16 * 1024**2,  # 16 MB 写盘上限
    "max_processes": 64,
    "open_files": 128,
}


def build_clean_env() -> dict[str, str]:
    env = {key: value for key, value in (__import__("os").environ.items()) if key in ENV_WHITELIST}
    env.setdefault("PYTHONHASHSEED", "0")
    env["RESEARCH_COPILOT_SANDBOXED"] = "1"
    return env


def _apply_rlimits(limits: dict[str, int]) -> None:  # pragma: no cover - 在子进程 preexec 中执行
    resource.setrlimit(resource.RLIMIT_CPU, (limits["cpu_seconds"], limits["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_AS, (limits["address_space_bytes"], limits["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits["file_size_bytes"], limits["file_size_bytes"]))
    resource.setrlimit(resource.RLIMIT_NPROC, (limits["max_processes"], limits["max_processes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits["open_files"], limits["open_files"]))


def check_network_isolation_available() -> bool:
    """探测非特权 user+net namespace 是否可用（结果缓存调用方决定）。"""
    unshare = shutil.which("unshare")
    if not unshare:
        return False
    try:
        probe = subprocess.run(
            [unshare, "-Urn", "true"],
            capture_output=True,
            timeout=10,
        )
        return probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class ToolSandbox:
    """python 代码执行沙箱。所有组共用同一沙箱配置（评测公平性）。"""

    def __init__(
        self,
        dataset_dir: str | Path | None,
        timeout_s: float = 60.0,
        limits: dict[str, int] | None = None,
        network_isolation: bool | None = None,  # None = 自动探测
    ) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else None
        self.timeout_s = timeout_s
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        if network_isolation is None:
            self.network_isolation = check_network_isolation_available()
        else:
            self.network_isolation = network_isolation
        self.executions: list[dict[str, Any]] = []

    @property
    def isolation_record(self) -> dict[str, Any]:
        return {
            "env_whitelist": list(ENV_WHITELIST),
            "rlimits": dict(self.limits),
            "network_isolated": bool(self.network_isolation),
            "honesty_note": (
                "网络已通过 user+net namespace 隔离"
                if self.network_isolation
                else "网络未隔离（系统不支持非特权 namespace）：生成代码可访问网络与用户文件，残余风险如实记录"
            ),
        }

    def run_python(self, code: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "snippet.py"
            script.write_text(code, encoding="utf-8")
            command: list[str] = []
            if self.network_isolation:
                unshare = shutil.which("unshare")
                command += [unshare, "-Urn"]
            command += [sys.executable, "-I", str(script)]
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(self.dataset_dir) if self.dataset_dir else tmp,
                    env=build_clean_env(),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    start_new_session=True,
                    preexec_fn=lambda: _apply_rlimits(self.limits),
                )
                result = {
                    "ok": completed.returncode == 0,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-2000:],
                }
            except subprocess.TimeoutExpired:
                result = {"ok": False, "stdout": "", "stderr": f"timeout after {self.timeout_s}s"}
            except OSError as exc:
                result = {"ok": False, "stdout": "", "stderr": f"launch failed: {exc}"}
        result["isolation"] = self.isolation_record
        self.executions.append({"code": code, **result})
        return result

    def usage_summary(self) -> dict[str, Any]:  # 与 LLM 接口一致性占位（无 LLM 调用）
        return {"tool_executions": len(self.executions), "network_isolated": self.network_isolation}


def sandbox_note_json(sandbox: ToolSandbox) -> str:
    return json.dumps(sandbox.isolation_record, ensure_ascii=False)
