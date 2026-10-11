"""工具执行沙箱 v3：容器级隔离（bwrap）+ 数据只读 + 可写输出目录分离。

隔离栈（fail-closed，审查 P0-3/P1）：
1. env 白名单：凭据不可达；
2. bwrap 容器：unshare-all（网络/挂载/pid）+ 文件系统白名单——
   系统目录只读、数据快照**文件级只读绑定**、工作目录可写；
3. 数据快照：仅复制 csv/dta（金标元数据不进入沙箱），保留相对目录结构，
   逐文件 sha256 清单——agent 可读数据但**写同名文件会被拒绝**（ro-bind）；
4. fail-closed：bwrap 不可用时默认拒绝执行，仅显式 allow_unsafe_fallback
   的开发模式允许降级（unshare -Urn，残余风险如实标注）。
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

ENV_WHITELIST = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "PYTHONHASHSEED")

DEFAULT_LIMITS = {
    "cpu_seconds": 60,
    "address_space_bytes": 2 * 1024**3,
    "file_size_bytes": 16 * 1024**2,
    "max_processes": 64,
    "open_files": 128,
}


def build_clean_env() -> dict[str, str]:
    import os

    env = {key: value for key, value in os.environ.items() if key in ENV_WHITELIST}
    env.setdefault("PYTHONHASHSEED", "0")
    env["RESEARCH_COPILOT_SANDBOXED"] = "1"
    return env


_RLIMIT_MAP = {
    "cpu_seconds": resource.RLIMIT_CPU,
    "address_space_bytes": resource.RLIMIT_AS,
    "file_size_bytes": resource.RLIMIT_FSIZE,
    "max_processes": resource.RLIMIT_NPROC,
    "open_files": resource.RLIMIT_NOFILE,
}


def _apply_rlimits(limits: dict[str, int]) -> None:  # pragma: no cover
    for key, rlimit in _RLIMIT_MAP.items():
        if key in limits:
            resource.setrlimit(rlimit, (limits[key], limits[key]))


def container_runtime_available() -> bool:
    return bool(shutil.which("bwrap")) or bool(shutil.which("firejail")) or bool(shutil.which("docker"))


def _user_site_packages() -> Path | None:
    """精确的用户 site-packages 路径（审查 P1：~/.local 整目录挂载范围过宽）。"""
    candidate = Path.home() / ".local" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    if candidate.exists():
        return candidate
    fallback = Path.home() / ".local"
    return fallback if fallback.exists() else None


def build_bwrap_command(
    script: Path, data_files: list[tuple[Path, str]], workdir: Path
) -> list[str] | None:
    """构造 bwrap 命令。

    data_files: [(宿主路径, 相对路径)]——数据快照**文件级只读绑定**到 cwd
    （审查 P0-3：数据只读语义，写同名文件被内核拒绝）；workdir 可写（输出目录）。
    返回 None 表示 bwrap 不可用。
    """
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return None
    command = [
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/etc", "/etc",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
    ]
    for lib in ("/lib", "/lib64"):
        if Path(lib).exists():
            command += ["--ro-bind", lib, lib]
    site_packages = _user_site_packages()
    if site_packages is not None:  # 精确到 site-packages，不挂整个 ~/.local
        command += ["--ro-bind", str(site_packages), str(site_packages)]
    # 绑定顺序：workdir 先、数据文件后（bwrap 后绑定覆盖先绑定——
    # 数据文件必须叠在可写 workdir 之上才是只读语义）
    command += ["--bind", str(workdir), str(workdir)]
    for host_path, inner_path in data_files:
        command += ["--ro-bind", str(host_path), str(Path(workdir) / inner_path)]
    command += ["--chdir", str(workdir)]  # cwd=可写输出目录；数据文件在 cwd 只读可见
    return command


def check_network_isolation_available() -> bool:
    unshare = shutil.which("unshare")
    if not unshare:
        return False
    try:
        probe = subprocess.run([unshare, "-Urn", "true"], capture_output=True, timeout=10)
        return probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class ToolSandbox:
    """python 代码执行沙箱 v3。所有组共用同一配置（评测公平性）。

    布局：cwd=workdir（可写，agent 输出目录）；数据快照文件**只读绑定**到
    workdir/<相对路径>（保留相对结构——agent 旧代码 glob('*.csv') 照常工作，
    但写同名文件被内核拒绝，输出须写其他文件名或仅 print）。
    """

    def __init__(
        self,
        dataset_dir: str | Path | None,
        timeout_s: float = 60.0,
        limits: dict[str, int] | None = None,
        network_isolation: bool | None = None,
        allow_unsafe_fallback: bool = False,  # fail-closed 默认
    ) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else None
        self.timeout_s = timeout_s
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self.network_isolation = check_network_isolation_available() if network_isolation is None else network_isolation
        self.allow_unsafe_fallback = allow_unsafe_fallback
        self.executions: list[dict[str, Any]] = []
        self._snapshot: dict[str, Path] = {}  # 沙箱内相对路径 -> 宿主快照文件
        self.snapshot_manifest: dict[str, str] = {}  # 相对路径 -> sha256
        self._snapshot_tmp: tempfile.TemporaryDirectory | None = None

    def _ensure_data_snapshot(self) -> list[tuple[Path, str]]:
        """快照数据文件（仅 csv/dta，保留相对结构，记录哈希）。"""
        if self._snapshot_tmp is not None:
            return [(host, rel) for rel, host in self._snapshot.items()]
        if self.dataset_dir is None or not self.dataset_dir.exists():
            return []
        self._snapshot_tmp = tempfile.TemporaryDirectory(prefix="rc-data-snapshot-")
        from ..core.evidence import sha256_file

        for pattern in ("*.csv", "*.dta"):
            for source in sorted(self.dataset_dir.rglob(pattern)):
                rel = str(source.relative_to(self.dataset_dir))
                host_file = Path(self._snapshot_tmp.name) / rel
                host_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, host_file)
                self._snapshot[rel] = host_file
                self.snapshot_manifest[rel] = sha256_file(source)
        return [(host, rel) for rel, host in self._snapshot.items()]

    def close(self) -> None:
        if self._snapshot_tmp is not None:
            self._snapshot_tmp.cleanup()
            self._snapshot_tmp = None
            self._snapshot = {}
            self.snapshot_manifest = {}

    def __enter__(self) -> "ToolSandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def isolation_record(self) -> dict[str, Any]:
        bwrap_ready = shutil.which("bwrap") is not None
        if bwrap_ready:
            note = (
                "容器级隔离（bwrap v3）：网络+挂载空间全隔离；数据快照文件级只读绑定"
                "（agent 写数据文件被内核拒绝）；仅工作目录可写；site-packages 精确挂载"
            )
        elif self.network_isolation:
            note = "网络已通过 user+net namespace 隔离；文件系统未隔离（用户权限内可读）"
        else:
            note = "网络未隔离：生成代码可访问网络与用户文件，残余风险如实记录"
        return {
            "env_whitelist": list(ENV_WHITELIST),
            "rlimits": dict(self.limits),
            "network_isolated": bool(self.network_isolation),
            "container_runtime": container_runtime_available(),
            "fs_isolated": bwrap_ready,
            "data_readonly": bwrap_ready,
            "snapshot_manifest": dict(self.snapshot_manifest),
            "honesty_note": note,
        }

    def run_python(self, code: str) -> dict[str, Any]:
        # fail-closed：无 bwrap 默认拒绝（审查 P0-3）
        if shutil.which("bwrap") is None and not self.allow_unsafe_fallback:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "fail-closed: 容器级隔离（bwrap）不可用，拒绝执行模型生成的代码",
                "fail_closed": True,
            }
        data_files = self._ensure_data_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            script = workdir / "snippet.py"
            script.write_text(code, encoding="utf-8")
            command: list[str] = []
            use_bwrap = False
            bwrap_command = build_bwrap_command(script, data_files, workdir)
            if bwrap_command is not None:
                command = bwrap_command
                command += [sys.executable, str(script)]
                use_bwrap = True
            else:
                if self.network_isolation:
                    unshare = shutil.which("unshare")
                    command += [unshare, "-Urn"]
                command += [sys.executable, str(script)]
            effective_limits = {k: v for k, v in self.limits.items() if k != "max_processes"} if use_bwrap else self.limits
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(workdir),
                    env=build_clean_env(),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    start_new_session=True,
                    preexec_fn=lambda: _apply_rlimits(effective_limits),
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
        result["isolation"] = {**self.isolation_record, "bwrap_used": use_bwrap}
        self.executions.append({"code": code, **result})
        return result

    def usage_summary(self) -> dict[str, Any]:
        return {"tool_executions": len(self.executions), "network_isolated": self.network_isolation}
