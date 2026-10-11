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


_RLIMIT_MAP = {
    "cpu_seconds": resource.RLIMIT_CPU,
    "address_space_bytes": resource.RLIMIT_AS,
    "file_size_bytes": resource.RLIMIT_FSIZE,
    "max_processes": resource.RLIMIT_NPROC,
    "open_files": resource.RLIMIT_NOFILE,
}


def _apply_rlimits(limits: dict[str, int]) -> None:  # pragma: no cover - 在子进程 preexec 中执行
    for key, rlimit in _RLIMIT_MAP.items():
        if key in limits:  # bwrap 模式排除 NPROC（与 namespace 创建冲突）
            resource.setrlimit(rlimit, (limits[key], limits[key]))


def container_runtime_available() -> bool:
    """探测容器级隔离运行时（bwrap 优先——轻量无需镜像）。"""
    return bool(shutil.which("bwrap")) or bool(shutil.which("firejail")) or bool(shutil.which("docker"))


def build_bwrap_command(script: Path, dataset_dir: Path | None, workdir: Path) -> list[str] | None:
    """构造 bwrap 命令：unshare-all + 文件系统白名单绑定（系统只读，仅数据/工作目录可写）。

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
    user_local = Path.home() / ".local"
    if user_local.exists():  # 用户 site-packages（pandas 等可选依赖）
        command += ["--ro-bind", str(user_local), str(user_local)]
    chdir_target = None
    if dataset_dir:
        dataset_abs = dataset_dir.resolve()
        if dataset_abs.exists():
            command += ["--bind", str(dataset_abs), str(dataset_abs)]  # 数据目录可写（分析产物）
            chdir_target = dataset_abs  # cwd 与宿主一致：相对路径读数据照旧
    command += ["--bind", str(workdir), str(workdir)]  # 脚本工作目录
    if chdir_target is not None:
        command += ["--chdir", str(chdir_target)]
    return command


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
        allow_unsafe_fallback: bool = False,  # 默认 fail-closed：隔离不满足则拒绝执行
    ) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else None
        self.timeout_s = timeout_s
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        if network_isolation is None:
            self.network_isolation = check_network_isolation_available()
        else:
            self.network_isolation = network_isolation
        self.allow_unsafe_fallback = allow_unsafe_fallback
        self.executions: list[dict[str, Any]] = []
        self._snapshot_dir: Path | None = None
        self._snapshot_tmp: tempfile.TemporaryDirectory | None = None

    def _ensure_data_snapshot(self) -> Path | None:
        """把数据文件（仅 csv/dta——绝不复制金标元数据）快照到可写工作区。

        修复审查 P0-3：原始 Benchmark 数据不再以可写方式挂载——agent 代码只能
        修改快照副本，保证原始数据完整性与后续实验可复现性。
        """
        if self._snapshot_dir is not None or self.dataset_dir is None:
            return self._snapshot_dir
        self._snapshot_tmp = tempfile.TemporaryDirectory(prefix="rc-data-snapshot-")
        self._snapshot_dir = Path(self._snapshot_tmp.name)
        if self.dataset_dir.exists():
            for pattern in ("*.csv", "*.dta"):
                for source in self.dataset_dir.rglob(pattern):
                    shutil.copy2(source, self._snapshot_dir / source.name)
        return self._snapshot_dir

    def close(self) -> None:
        if self._snapshot_tmp is not None:
            self._snapshot_tmp.cleanup()
            self._snapshot_tmp = None
            self._snapshot_dir = None

    @property
    def isolation_record(self) -> dict[str, Any]:
        bwrap_ready = build_bwrap_command(Path("x"), self.dataset_dir, Path("/tmp")) is not None
        if bwrap_ready:
            note = (
                "容器级隔离（bwrap）：网络+挂载空间全隔离，系统目录只读，"
                "仅数据目录与工作目录可写——生成代码无法读取绑定集之外的宿主文件"
            )
        elif self.network_isolation:
            note = "网络已通过 user+net namespace 隔离；文件系统未隔离（用户权限内可读）"
        else:
            note = "网络未隔离（系统不支持非特权 namespace）：生成代码可访问网络与用户文件，残余风险如实记录"
        return {
            "env_whitelist": list(ENV_WHITELIST),
            "rlimits": dict(self.limits),
            "network_isolated": bool(self.network_isolation),
            "container_runtime": container_runtime_available(),
            "fs_isolated": bwrap_ready,
            "honesty_note": note,
        }

    def run_python(self, code: str) -> dict[str, Any]:
        # fail-closed（审查 P0-3）：无容器级隔离时默认拒绝执行不可信代码，
        # 仅显式 allow_unsafe_fallback=True 的开发模式允许降级。
        probe = build_bwrap_command(Path("snippet.py"), self.dataset_dir, Path("/tmp/rc-probe"))
        if probe is None and not self.allow_unsafe_fallback:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "fail-closed: 容器级隔离（bwrap）不可用，拒绝执行模型生成的代码",
                "fail_closed": True,
            }
        # 数据快照（只读语义）：cwd/绑定都指向快照副本，原数据永不修改
        data_for_binding = self._ensure_data_snapshot() or self.dataset_dir
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            script = workdir / "snippet.py"
            script.write_text(code, encoding="utf-8")
            command: list[str] = []
            use_bwrap = False
            bwrap_command = build_bwrap_command(script, data_for_binding, workdir)
            if bwrap_command is not None:
                command = bwrap_command
                command += [sys.executable, str(script)]
                use_bwrap = True
            else:
                if self.network_isolation:
                    unshare = shutil.which("unshare")
                    command += [unshare, "-Urn"]
                # 不用 -I：env 已白名单清洗，保留默认 site-packages（pandas 等与宿主公平一致）
                command += [sys.executable, str(script)]
            # bwrap 模式排除 RLIMIT_NPROC（与 namespace 创建冲突）；其余限额保留
            effective_limits = {k: v for k, v in self.limits.items() if k != "max_processes"} if use_bwrap else self.limits
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(data_for_binding) if data_for_binding else str(workdir),
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

    def usage_summary(self) -> dict[str, Any]:  # 与 LLM 接口一致性占位（无 LLM 调用）
        return {"tool_executions": len(self.executions), "network_isolated": self.network_isolation}


def sandbox_note_json(sandbox: ToolSandbox) -> str:
    return json.dumps(sandbox.isolation_record, ensure_ascii=False)
