"""任务级持久工作区 + bwrap 隔离 + 文件级只读数据快照。

默认 fail-closed。程序存在与实际运行成功分别记录；显式开发降级
allow_unsafe_fallback 不构成正式评测的隔离保证。工作区在 close 时清理。
"""
from __future__ import annotations

import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from functools import lru_cache
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
_RLIMIT_MAP = {
    "cpu_seconds": resource.RLIMIT_CPU,
    "address_space_bytes": resource.RLIMIT_AS,
    "file_size_bytes": resource.RLIMIT_FSIZE,
    "max_processes": resource.RLIMIT_NPROC,
    "open_files": resource.RLIMIT_NOFILE,
}


def build_clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in ENV_WHITELIST}
    env["TMPDIR"] = "/tmp"
    env.setdefault("PYTHONHASHSEED", "0")
    env["RESEARCH_COPILOT_SANDBOXED"] = "1"
    return env


def _apply_rlimits(limits: dict[str, int]) -> None:  # pragma: no cover
    for key, rlimit in _RLIMIT_MAP.items():
        if key in limits:
            resource.setrlimit(rlimit, (limits[key], limits[key]))


def _run_process(command: list[str], timeout: float, cwd: Path | None = None,
                 limits: dict[str, int] | None = None) -> dict[str, Any]:
    """有界等待并终止整个进程组；输出写临时文件，避免后台子进程持有管道。"""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                command, cwd=str(cwd) if cwd else None, env=build_clean_env(),
                stdout=stdout, stderr=stderr, start_new_session=True,
                preexec_fn=(lambda: _apply_rlimits(limits)) if limits else None,
            )
        except OSError as exc:
            return {"ok": False, "stdout": "", "stderr": f"launch failed: {exc}"}
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

        def tail(handle, n):
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - n))
            return handle.read().decode("utf-8", errors="replace")

        err = tail(stderr, 2000)
        if timed_out:
            err = f"timeout after {timeout}s\n{err}"
        return {"ok": not timed_out and process.returncode == 0,
                "stdout": tail(stdout, 4000), "stderr": err,
                "returncode": process.returncode, "timed_out": timed_out}


def _user_site_packages() -> Path | None:
    candidate = Path.home() / ".local" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    return candidate if candidate.is_dir() else None


def build_bwrap_command(script: Path, data_files: list[tuple[Path, str]], workdir: Path) -> list[str] | None:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return None
    command = [bwrap, "--unshare-all", "--die-with-parent", "--new-session",
               "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    for lib in ("/lib", "/lib64"):
        if Path(lib).exists():
            command += ["--ro-bind", lib, lib]
    # 支持 /opt 的解释器和 virtualenv；不挂整个 home 或 ~/.local。
    bound = {Path("/usr"), Path("/etc"), Path("/lib"), Path("/lib64")}
    for prefix in (Path(sys.base_prefix), Path(sys.prefix), _user_site_packages()):
        if prefix is not None and prefix.exists() and not any(prefix.is_relative_to(p) for p in bound):
            if prefix == Path("/"):
                continue
            command += ["--ro-bind", str(prefix), str(prefix)]
            bound.add(prefix)
    command += ["--bind", str(workdir), str(workdir)]
    for host_path, relative_path in data_files:
        destination = workdir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        command += ["--ro-bind", str(host_path), str(destination)]
    return command + ["--chdir", str(workdir)]


@lru_cache(maxsize=4)
def _probe_bwrap(path: str) -> tuple[bool, str]:
    command = [path, "--unshare-all", "--die-with-parent", "--new-session", "--ro-bind", "/usr", "/usr"]
    for lib in ("/lib", "/lib64"):
        if Path(lib).exists():
            command += ["--ro-bind", lib, lib]
    result = _run_process(command + ["/usr/bin/true"], 3)
    return result["ok"], result["stderr"]


def check_bwrap_available() -> bool:
    path = shutil.which("bwrap")
    return bool(path and _probe_bwrap(path)[0])


def container_runtime_available() -> bool:
    return check_bwrap_available()


@lru_cache(maxsize=4)
def _probe_unshare(path: str) -> bool:
    return _run_process([path, "-Urn", "/usr/bin/true"], 3)["ok"]


def check_network_isolation_available() -> bool:
    path = shutil.which("unshare")
    return bool(path and _probe_unshare(path))


class ToolSandbox:
    def __init__(self, dataset_dir: str | Path | None, timeout_s: float = 60.0,
                 limits: dict[str, int] | None = None, network_isolation: bool | None = None,
                 allow_unsafe_fallback: bool = False) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else None
        self.timeout_s = timeout_s
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self.network_isolation = check_network_isolation_available() if network_isolation is None else network_isolation
        self.allow_unsafe_fallback = allow_unsafe_fallback
        self.executions: list[dict[str, Any]] = []
        self._snapshot: dict[str, Path] = {}
        self.snapshot_manifest: dict[str, str] = {}
        self._snapshot_tmp: tempfile.TemporaryDirectory | None = None
        self._work_tmp: tempfile.TemporaryDirectory | None = None
        self._last_isolation: dict[str, Any] = {}

    def _ensure_data_snapshot(self) -> list[tuple[Path, str]]:
        if self._snapshot_tmp is not None:
            return [(host, rel) for rel, host in self._snapshot.items()]
        if self.dataset_dir is None or not self.dataset_dir.exists():
            return []
        self._snapshot_tmp = tempfile.TemporaryDirectory(prefix="rc-data-snapshot-")
        from ..core.evidence import sha256_file
        for pattern in ("*.csv", "*.dta"):
            for source in sorted(self.dataset_dir.rglob(pattern)):
                if not source.resolve().is_relative_to(self.dataset_dir.resolve()):
                    raise ValueError("数据集符号链接指向工作区之外")
                relative = str(source.relative_to(self.dataset_dir))
                host = Path(self._snapshot_tmp.name) / relative
                host.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, host)
                self._snapshot[relative] = host
                self.snapshot_manifest[relative] = sha256_file(host)
        return [(host, rel) for rel, host in self._snapshot.items()]

    def close(self) -> None:
        for temporary in (self._work_tmp, self._snapshot_tmp):
            if temporary is not None:
                temporary.cleanup()
        self._work_tmp = self._snapshot_tmp = None
        self._snapshot = {}
        # 保留审计记录和 manifest，runner 清理后仍能归档。

    def __enter__(self) -> "ToolSandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def isolation_record(self) -> dict[str, Any]:
        ready = check_bwrap_available()
        effective = self._last_isolation
        fs_isolated = bool(effective.get("bwrap_used", False))
        network_isolated = bool(effective.get("network_isolated", False))
        return {"env_whitelist": list(ENV_WHITELIST), "rlimits": dict(self.limits),
                "container_runtime": ready, "bwrap_available": ready,
                "network_isolated": network_isolated, "fs_isolated": fs_isolated,
                "data_readonly": fs_isolated, "execution_verified": bool(effective),
                "snapshot_manifest": dict(self.snapshot_manifest),
                "honesty_note": (
                    "已执行 bwrap：命名空间隔离、文件级只读快照、任务级持久工作区。"
                    if fs_isolated else
                    "尚未验证实际执行隔离；默认 fail-closed。显式开发降级存在网络/文件访问残余风险。"
                ), **effective}

    def run_python(self, code: str) -> dict[str, Any]:
        ready = check_bwrap_available()
        if not ready and not self.allow_unsafe_fallback:
            result = {"ok": False, "stdout": "", "stderr": "fail-closed: 容器级隔离（bwrap）不可用，拒绝执行模型生成的代码", "fail_closed": True}
            result["isolation"] = self.isolation_record
            self.executions.append({"code": code, **result})
            return result
        data_files = self._ensure_data_snapshot()
        if self._work_tmp is None:
            self._work_tmp = tempfile.TemporaryDirectory(prefix="rc-work-")
            if not ready:
                for host, relative in data_files:
                    destination = Path(self._work_tmp.name) / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(host, destination)
        workdir = Path(self._work_tmp.name)
        script = workdir / "snippet.py"
        script.write_text(code, encoding="utf-8")
        command = build_bwrap_command(script, data_files, workdir) if ready else None
        use_bwrap = command is not None
        if command is None:
            command = [shutil.which("unshare"), "-Urn"] if self.network_isolation else []
        command += [sys.executable, str(script)]
        effective_limits = {k: v for k, v in self.limits.items() if k != "max_processes"} if use_bwrap else self.limits
        result = _run_process(command, self.timeout_s, cwd=workdir, limits=effective_limits)
        launched = not result["stderr"].startswith(("bwrap:", "launch failed:")) and not result.get("timed_out")
        self._last_isolation = {"bwrap_used": use_bwrap and launched,
                                "network_isolated": launched and (use_bwrap or bool(self.network_isolation)),
                                "execution_verified": launched,
                                "effective_limits": effective_limits}
        result["isolation"] = self.isolation_record
        self.executions.append({"code": code, **result})
        return result

    def usage_summary(self) -> dict[str, Any]:
        return {"tool_executions": len(self.executions), "network_isolated": self.isolation_record["network_isolated"]}
