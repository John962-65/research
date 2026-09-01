from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import tomllib

from .artifacts import write_json, write_text, cell as _cell
from .benchmark_adapter import audit_benchmark_adapter_config
from .config import ExecutionConfig, PaperGradeConfig
from .experiments import MAX_EXECUTION_REPEATS, MAX_EXECUTION_TIMEOUT_SECONDS, MAX_OUTPUT_BYTES, validate_experiment_command
from .models import ExperimentPlan


EXECUTION_SAFETY_AUDIT_JSON = "03-execution-safety-audit.json"
EXECUTION_SAFETY_AUDIT_MD = "03-execution-safety-audit.md"


def write_execution_safety_audit_artifacts(
    plan: ExperimentPlan,
    config: ExecutionConfig,
    run_dir: Path,
    paper_grade: PaperGradeConfig | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    report = build_execution_safety_audit_report(plan, config, run_dir, paper_grade=paper_grade, base_dir=base_dir)
    write_json(run_dir / EXECUTION_SAFETY_AUDIT_JSON, report)
    write_text(run_dir / EXECUTION_SAFETY_AUDIT_MD, render_execution_safety_audit_markdown(report))
    return report


def build_execution_safety_audit_report(
    plan: ExperimentPlan,
    config: ExecutionConfig,
    run_dir: Path,
    paper_grade: PaperGradeConfig | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    experiment_dir = run_dir / "experiments"
    commands = _command_records(plan, config, experiment_dir)
    blocking: list[str] = []
    warnings: list[str] = []
    _check_execution_config(config, blocking, warnings)
    _check_commands(config, commands, blocking, warnings)
    benchmark_report: dict[str, Any] = {}
    source_artifacts: list[dict[str, Any]] = []
    if config.mode == "benchmark":
        benchmark_base = base_dir or Path.cwd()
        benchmark = audit_benchmark_adapter_config(config, base_dir=benchmark_base)
        benchmark_report = {
            "status": benchmark.status,
            "manifest_paths": benchmark.manifest_paths,
            "commands": benchmark.commands,
            "blocking_issues": benchmark.blocking_issues,
            "manual_tasks": benchmark.manual_tasks,
        }
        source_artifacts = _benchmark_source_artifacts(benchmark.adapters)
        blocking.extend(f"benchmark adapter: {item}" for item in benchmark.blocking_issues)
    isolation = {
        "sandboxed": False,
        "network_isolated": False,
        "process_group_isolated": True,
        "output_capture": "bounded_pipe_tail",
        "external_runner_controlled": config.external_runner_controlled,
        "notice": "Local execution is not a sandbox and does not provide network isolation.",
    }
    if paper_grade is not None and paper_grade.enabled and config.mode == "benchmark" and not config.external_runner_controlled:
        blocking.append("paper-grade benchmark 必须显式配置 external_runner_controlled=true，并由外部受控 runner 提供系统/网络隔离。")
    approved_commands = benchmark_report.get("commands") if config.mode == "benchmark" else commands
    binding = _execution_binding(config, approved_commands if isinstance(approved_commands, list) else [], source_artifacts)
    status = "block" if blocking else "warn" if warnings else "pass"
    return {
        "schema_version": 1,
        "idea_title": plan.idea_title,
        "status": status,
        "execution_mode": config.mode,
        "timeout_seconds": config.timeout_seconds,
        "repeats": config.repeats,
        "max_output_bytes": config.max_output_bytes,
        "allowed_commands": config.allowed_commands,
        "commands": commands,
        "approved_commands": approved_commands,
        "benchmark_adapter_audit": benchmark_report,
        "source_artifacts": source_artifacts,
        "execution_binding": binding,
        "execution_binding_sha256": _digest(binding),
        "isolation": isolation,
        "blocking_issues": _dedupe(blocking),
        "warnings": _dedupe(warnings),
        "required_actions": _required_actions(blocking, warnings),
    }


def render_execution_safety_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 实验执行安全审计：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 执行模式：{report.get('execution_mode') or '-'}",
        f"- 超时限制：{report.get('timeout_seconds') or '-'}s",
        f"- 重复次数：{report.get('repeats') or '-'}",
        f"- 输出读取上限：{report.get('max_output_bytes') or '-'} bytes/stream",
        f"- 命令白名单：{', '.join(report.get('allowed_commands') or []) or '-'}",
        f"- Sandbox：否；网络隔离：否；独立进程组：是",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("warnings", "警告"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(["## 命令审计", "| 名称 | 命令 | 预期产物 | 状态 | 问题 |", "| --- | --- | --- | --- | --- |"])
    commands = report.get("commands") if isinstance(report.get("commands"), list) else []
    if not commands:
        lines.append("| 无 | - | - | block | 没有实验命令 |")
    for command in commands:
        if isinstance(command, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(command.get("name") or "")),
                        _cell(" ".join(command.get("command") or [])),
                        _cell(", ".join(command.get("expected_artifacts") or []) or "-"),
                        _cell(str(command.get("status") or "")),
                        _cell("；".join(command.get("validation_issues") or []) or "-"),
                    ]
                )
                + " |"
            )
    benchmark = report.get("benchmark_adapter_audit") if isinstance(report.get("benchmark_adapter_audit"), dict) else {}
    if benchmark:
        lines.extend(
            [
                "",
                "## Benchmark Adapter",
                f"- 状态：{benchmark.get('status') or '-'}",
                f"- Manifest：{', '.join(benchmark.get('manifest_paths') or []) or '-'}",
                f"- 可执行命令：{len(benchmark.get('commands') or [])}",
            ]
        )
        blockers = benchmark.get("blocking_issues") if isinstance(benchmark.get("blocking_issues"), list) else []
        if blockers:
            lines.extend(["", "### Adapter 阻断"])
            lines.extend(f"- {item}" for item in blockers)
    return "\n".join(lines)


def _command_records(plan: ExperimentPlan, config: ExecutionConfig, experiment_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for command in plan.commands:
        issues = validate_experiment_command(command, config, experiment_dir) if config.mode in {"local", "benchmark"} else []
        records.append(
            {
                "name": command.name,
                "command": command.command,
                "expected_artifacts": command.expected_artifacts,
                "status": "block" if issues else "pass",
                "validation_issues": issues,
            }
        )
    return records


def _check_execution_config(config: ExecutionConfig, blocking: list[str], warnings: list[str]) -> None:
    if config.mode not in {"simulated", "local", "benchmark"}:
        blocking.append(f"Unsupported execution mode: {config.mode}")
    if config.timeout_seconds <= 0:
        blocking.append("timeout_seconds 必须大于 0。")
    elif config.timeout_seconds > MAX_EXECUTION_TIMEOUT_SECONDS:
        blocking.append(f"timeout_seconds 不得超过 {MAX_EXECUTION_TIMEOUT_SECONDS}。")
    if config.repeats < 1:
        blocking.append("repeats 必须大于 0。")
    elif config.repeats > MAX_EXECUTION_REPEATS:
        blocking.append(f"repeats 不得超过 {MAX_EXECUTION_REPEATS}。")
    if config.max_output_bytes < 1:
        blocking.append("max_output_bytes 必须大于 0。")
    elif config.max_output_bytes > MAX_OUTPUT_BYTES:
        blocking.append(f"max_output_bytes 不得超过 {MAX_OUTPUT_BYTES}。")
    if config.mode in {"local", "benchmark"} and not config.allowed_commands:
        blocking.append("local/benchmark 模式必须配置 allowed_commands。")
    if config.mode == "simulated":
        warnings.append("当前为 simulated，只能作为烟测；论文主结论需要 local 或 benchmark 真实实验支撑。")


def _check_commands(config: ExecutionConfig, commands: list[dict[str, Any]], blocking: list[str], warnings: list[str]) -> None:
    if not commands and config.mode != "benchmark":
        blocking.append("实验计划没有可执行命令。")
        return
    for command in commands:
        issues = command.get("validation_issues") if isinstance(command.get("validation_issues"), list) else []
        blocking.extend(f"{command.get('name')}: {item}" for item in issues)
        if config.mode in {"local", "benchmark"} and not command.get("expected_artifacts"):
            warnings.append(f"{command.get('name')}: 未声明 expected_artifacts，结果读取和复现审计会变弱。")


def _required_actions(blocking: list[str], warnings: list[str]) -> list[str]:
    if blocking:
        return ["修复命令白名单、路径、manifest 或执行参数后再运行实验。"]
    if warnings:
        return ["可以继续执行 smoke，但不得把模拟或弱产物审计当作正式实验结论。"]
    return ["执行配置和命令安全审计已通过，可以进入实验执行。"]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def execution_source_binding_matches(binding: dict[str, Any]) -> bool:
    artifacts = binding.get("source_artifacts") if isinstance(binding.get("source_artifacts"), list) else []
    for item in artifacts:
        if not isinstance(item, dict):
            return False
        path_value = str(item.get("path") or "")
        expected = str(item.get("sha256") or "")
        if not path_value:
            return False
        path = Path(path_value)
        expected_exists = item.get("exists") is not False
        if not expected_exists:
            if path.is_file():
                return False
            continue
        if not expected or not path.is_file() or _file_sha256(path) != expected:
            return False
    return True


def benchmark_source_artifacts(config: ExecutionConfig, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return the complete local input set referenced by benchmark manifests."""
    return _benchmark_source_artifacts_from_manifests(config.benchmark_manifest_paths, base_dir or Path.cwd())


def _execution_binding(config: ExecutionConfig, commands: list[Any], source_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": config.mode,
        "timeout_seconds": config.timeout_seconds,
        "repeats": config.repeats,
        "max_output_bytes": config.max_output_bytes,
        "allowed_commands": list(config.allowed_commands),
        "external_runner_controlled": config.external_runner_controlled,
        "commands": commands,
        "source_artifacts": source_artifacts,
    }


def _benchmark_source_artifacts(adapters: list[Any]) -> list[dict[str, Any]]:
    manifests = [str(getattr(adapter, "manifest_path", "")) for adapter in adapters]
    return _benchmark_source_artifacts_from_manifests(manifests, Path.cwd())


def _benchmark_source_artifacts_from_manifests(manifest_values: list[str], base_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for manifest_value in manifest_values:
        manifest_text = str(manifest_value or "").strip()
        if not manifest_text:
            continue
        raw_manifest = Path(manifest_text)
        manifest = raw_manifest if raw_manifest.is_absolute() else base_dir / raw_manifest
        manifest = _resolved_path(manifest)
        if manifest is None:
            continue
        _append_file_record(records, seen, manifest)
        if not manifest.is_file():
            continue
        data = _read_manifest(manifest)
        candidates = [
            *(data.get("source_files") if isinstance(data.get("source_files"), list) else []),
            data.get("split_path"),
            data.get("grader_path"),
        ]
        command = data.get("command") if isinstance(data.get("command"), list) else []
        outputs = {
            str(data.get("metrics_path") or ""),
            str(data.get("submission_path") or ""),
        }
        if isinstance(data.get("expected_artifacts"), list):
            outputs.update(str(item) for item in data["expected_artifacts"] if str(item))
        for token in command[1:]:
            value = str(token)
            if value and not value.startswith("-") and value not in outputs and ("/" in value or Path(value).suffix):
                candidates.append(value)
        for value in candidates:
            rel = Path(str(value or ""))
            if not str(value or "") or rel.is_absolute() or ".." in rel.parts:
                continue
            dependency = _resolved_manifest_dependency(manifest.parent, rel)
            if dependency is not None:
                _append_file_record(records, seen, dependency)
    return records


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _append_file_record(records: list[dict[str, Any]], seen: set[str], path: Path) -> None:
    resolved = _resolved_path(path)
    if resolved is None:
        return
    key = str(resolved)
    if key in seen:
        return
    seen.add(key)
    exists = resolved.is_file()
    records.append(
        {
            "path": key,
            "exists": exists,
            "bytes": resolved.stat().st_size if exists else 0,
            "sha256": _file_sha256(resolved) if exists else "",
        }
    )


def _resolved_path(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def _resolved_manifest_dependency(manifest_dir: Path, relative_path: Path) -> Path | None:
    resolved = _resolved_path(manifest_dir / relative_path)
    root = _resolved_path(manifest_dir)
    if resolved is None or root is None:
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
