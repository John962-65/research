from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import hashlib
import ipaddress
import json
import re
import shutil
import tomllib

from .artifacts import write_json, write_text, cell as _cell, sha256_file as _sha256_file
from .command_safety import interpreter_execution_issues
from .config import ExecutionConfig, PaperGradeConfig
from .models import ExperimentCommand, ExperimentPlan


BENCHMARK_ADAPTER_JSON = "03-benchmark-adapters.json"
BENCHMARK_ADAPTER_MD = "03-benchmark-adapters.md"
_SHELL_META_PATTERN = re.compile(r"[;&|<>`$]|\r|\n")
_EXTERNAL_BENCHMARK_KINDS = {"external", "official", "public", "formal"}
_METRIC_DIRECTIONS = {"higher_is_better", "lower_is_better", "target", "descriptive"}
_PLACEHOLDER_MARKERS = [
    "todo",
    "tbd",
    "placeholder",
    "replace me",
    "replace with",
    "verify-before-run",
    "example.org",
    "example.com",
    "example.net",
    "path/to",
]


@dataclass(frozen=True)
class BenchmarkAdapterRecord:
    name: str
    role: str
    status: str
    manifest_path: str
    adapter_dir: str
    command: list[str]
    role_command_signature: str
    expected_artifacts: list[str]
    metrics_path: str
    benchmark_url: str
    dataset_url: str
    dataset_version: str
    split_name: str
    split_path: str
    split_sha256: str
    split_sha256_actual: str
    license: str
    baseline: str
    baseline_version: str
    citation: str
    expected_metrics: list[str]
    metric_schema: dict[str, dict[str, str]]
    grader: str
    grader_path: str
    submission_path: str
    grader_version: str
    grader_sha256: str
    grader_sha256_actual: str
    seed_policy: str
    min_repeats: int
    benchmark_kind: str
    provenance_status: str
    provenance_issues: list[str]
    metric_contract_status: str
    metric_contract_issues: list[str]
    source_files: list[str]
    copied_files: list[str]
    issues: list[str]
    notes: list[str]


@dataclass(frozen=True)
class BenchmarkAdapterReport:
    status: str
    mode: str
    manifest_paths: list[str]
    adapters: list[BenchmarkAdapterRecord]
    commands: list[dict[str, Any]]
    blocking_issues: list[str]
    manual_tasks: list[str]
    paper_grade_status: str = ""
    paper_grade_issues: list[str] = field(default_factory=list)
    paper_grade_repair_suggestions: list[dict[str, Any]] = field(default_factory=list)


def prepare_benchmark_adapter_plan(
    plan: ExperimentPlan,
    config: ExecutionConfig,
    run_dir: Path,
    base_dir: Path | None = None,
    paper_grade: PaperGradeConfig | None = None,
) -> tuple[ExperimentPlan, BenchmarkAdapterReport]:
    base = base_dir or Path.cwd()
    manifest_paths = [str(item).strip() for item in config.benchmark_manifest_paths if str(item).strip()]
    experiment_dir = run_dir / "experiments"
    adapter_root = experiment_dir / "benchmark-adapters"
    adapter_root.mkdir(parents=True, exist_ok=True)
    records = [_with_execution_issues(_load_adapter(path, base, adapter_root), config) for path in manifest_paths]
    usable = [record for record in records if record.status == "ready"]
    blocking = _blocking_issues(manifest_paths, records, usable)
    manual = _manual_tasks(records)
    paper_grade_status = _paper_grade_status(usable, config.repeats, paper_grade)
    commands = [
        ExperimentCommand(
            name=record.name,
            command=record.command,
            expected_artifacts=record.expected_artifacts,
            role=record.role,
            comparison_group=_comparison_group(record),
            adapter_id=record.name,
        )
        for record in usable
    ]
    adapter_plan = ExperimentPlan(
        idea_title=plan.idea_title,
        objective=plan.objective,
        variables=plan.variables,
        metrics=plan.metrics,
        protocol=[*plan.protocol, "使用 benchmark manifest 接入的本地适配器执行真实/外部任务。"],
        commands=commands,
        rationale=(plan.rationale + " " if plan.rationale else "") + "实验命令来自人工配置的 benchmark manifest，并通过本地白名单安全校验。",
        baseline=plan.baseline,
        evidence_keys=plan.evidence_keys,
        template_profile=plan.template_profile,
    )
    report = BenchmarkAdapterReport(
        status="ready" if usable and not blocking else "blocked",
        mode="benchmark",
        manifest_paths=manifest_paths,
        adapters=records,
        commands=[_command_payload(record) for record in usable],
        blocking_issues=blocking,
        manual_tasks=manual,
        paper_grade_status=paper_grade_status["status"],
        paper_grade_issues=paper_grade_status["issues"],
        paper_grade_repair_suggestions=paper_grade_status["repair_suggestions"],
    )
    write_benchmark_adapter_artifacts(run_dir, report)
    return adapter_plan, report


def audit_benchmark_adapter_config(
    config: ExecutionConfig,
    base_dir: Path | None = None,
    paper_grade: PaperGradeConfig | None = None,
) -> BenchmarkAdapterReport:
    base = base_dir or Path.cwd()
    manifest_paths = [str(item).strip() for item in config.benchmark_manifest_paths if str(item).strip()]
    adapter_root = Path("experiments") / "benchmark-adapters"
    records = [_load_adapter(path, base, adapter_root, copy_files=False) for path in manifest_paths]
    records = [_with_execution_issues(record, config) for record in records]
    usable = [record for record in records if record.status == "ready"]
    blocking = _blocking_issues(manifest_paths, records, usable)
    paper_grade_status = _paper_grade_status(usable, config.repeats, paper_grade)
    return BenchmarkAdapterReport(
        status="ready" if usable and not blocking else "blocked",
        mode="benchmark",
        manifest_paths=manifest_paths,
        adapters=records,
        commands=[_command_payload(record) for record in usable],
        blocking_issues=blocking,
        manual_tasks=_manual_tasks(records) if records else [],
        paper_grade_status=paper_grade_status["status"],
        paper_grade_issues=paper_grade_status["issues"],
        paper_grade_repair_suggestions=paper_grade_status["repair_suggestions"],
    )


def write_benchmark_adapter_artifacts(run_dir: Path, report: BenchmarkAdapterReport) -> None:
    write_json(run_dir / BENCHMARK_ADAPTER_JSON, report)
    write_text(run_dir / BENCHMARK_ADAPTER_MD, render_benchmark_adapter_markdown(report))


def render_benchmark_adapter_markdown(report: BenchmarkAdapterReport) -> str:
    lines = [
        "# Benchmark Adapter 审计",
        "",
        f"- 状态：{report.status}",
        f"- 模式：{report.mode}",
        f"- Manifest 数：{len(report.manifest_paths)}",
        f"- 可执行命令：{len(report.commands)}",
        f"- Paper-grade：{report.paper_grade_status or '-'}",
        "",
        "## Adapter",
        "| 名称 | 角色 | 状态 | manifest | adapter_dir | 命令 | 预期产物 | 问题 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if report.adapters:
        for record in report.adapters:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(record.name),
                        _cell(record.role or "-"),
                        record.status,
                        _cell(record.manifest_path),
                        _cell(record.adapter_dir),
                        _cell(" ".join(record.command) or "-"),
                        _cell(", ".join(record.expected_artifacts) or "-"),
                        _cell("；".join(record.issues) or "-"),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | missing | - | - | - | - | 未配置 benchmark_manifest_paths |")
    lines.extend(["", "## 阻断问题"])
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    if report.paper_grade_issues:
        lines.extend(["", "## Paper-grade 缺口"])
        lines.extend(f"- {item}" for item in report.paper_grade_issues)
    if report.paper_grade_repair_suggestions:
        lines.extend(["", "## Paper-grade 修复建议", "| 类型 | 目标 | 动作 |", "| --- | --- | --- |"])
        for item in report.paper_grade_repair_suggestions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("kind") or "")),
                        _cell(str(item.get("target") or item.get("role") or item.get("manifest_path") or "-")),
                        _cell(str(item.get("action") or "")),
                    ]
                )
                + " |"
            )
        template_rows = [item for item in report.paper_grade_repair_suggestions if isinstance(item.get("manifest_template"), dict)]
        if template_rows:
            lines.extend(["", "### 缺失 manifest 模板"])
            for item in template_rows:
                lines.extend(
                    [
                        f"- `{item.get('target_path_hint') or item.get('role') or 'manifest'}`",
                        "```json",
                        json.dumps(item.get("manifest_template"), ensure_ascii=False, indent=2),
                        "```",
                    ]
                )
    if report.adapters:
        lines.extend(["", "## Benchmark Provenance", "| 名称 | 角色 | kind | status | benchmark_url | dataset_url | dataset_version | split_name | split_path | split_sha256 | split_sha256_actual | license | baseline | baseline_version | citation | metrics | grader | grader_path | grader_sha256_actual | submission | seed_policy | min_repeats |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: |"])
        for record in report.adapters:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(record.name),
                        _cell(record.role or "-"),
                        _cell(record.benchmark_kind or "-"),
                        _cell(record.provenance_status or "-"),
                        _cell(record.benchmark_url or "-"),
                        _cell(record.dataset_url or "-"),
                        _cell(record.dataset_version or "-"),
                        _cell(record.split_name or "-"),
                        _cell(record.split_path or "-"),
                        _cell(record.split_sha256 or "-"),
                        _cell(record.split_sha256_actual or "-"),
                        _cell(record.license or "-"),
                        _cell(record.baseline or "-"),
                        _cell(record.baseline_version or "-"),
                        _cell(record.citation or "-"),
                        _cell(", ".join(record.expected_metrics) or "-"),
                        _cell(record.grader or "-"),
                        _cell(record.grader_path or "-"),
                        _cell(record.grader_sha256_actual or "-"),
                        _cell(record.submission_path or "-"),
                        _cell(record.seed_policy or "-"),
                        str(record.min_repeats or 0),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Manifest Schema",
            "```json",
            json.dumps(
                {
                    "name": "toy benchmark",
                    "role": "candidate",
                    "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
                    "metrics_path": "metrics.json",
                    "source_files": ["run_benchmark.py"],
                    "expected_artifacts": ["metrics.json"],
                    "benchmark_kind": "external",
                    "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                    "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                    "dataset_version": "ompl-1.6.0",
                    "split_name": "official-ompl-benchmark-suite",
                    "split_path": "split-manifest.json",
                    "split_sha256": "0" * 64,
                    "license": "BSD-3-Clause",
                    "baseline": "RRT*",
                    "baseline_version": "ompl-1.6.0",
                    "citation": "10.1109/MRA.2012.2205651",
                    "expected_metrics": ["success_rate", "planning_time"],
                    "metric_schema": {
                        "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction of tasks solved."},
                        "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Wall-clock planning time."},
                    },
                    "grader": "grade.py",
                    "grader_path": "grade.py",
                    "grader_version": "ompl-1.6.0",
                    "grader_sha256": "0" * 64,
                    "submission_path": "submission.csv",
                    "seed_policy": "RESEARCH_AGENT_SEED controls deterministic split/task sampling",
                    "min_repeats": 5,
                    "notes": ["optional human notes"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
        ]
    )
    return "\n".join(lines)


def _load_adapter(manifest_value: str, base_dir: Path, adapter_root: Path, copy_files: bool = True) -> BenchmarkAdapterRecord:
    manifest_path = _resolve_manifest_path(manifest_value, base_dir)
    if manifest_path is None:
        return _record(
            name=_slug(Path(manifest_value).stem or "benchmark"),
            status="blocked",
            manifest_path=manifest_value,
            adapter_dir="",
            issues=[f"manifest 不存在或路径不安全：{manifest_value}"],
        )
    data, parse_issues = _read_manifest(manifest_path)
    name = str(data.get("name") or manifest_path.stem).strip()
    role = str(data.get("role") or "").strip().lower()
    base_slug = _slug(name)
    slug = _role_slug(role, base_slug)
    adapter_dir = adapter_root / slug
    command = _as_str_list(data.get("command"))
    source_files = _as_str_list(data.get("source_files"))
    metrics_path = str(data.get("metrics_path") or "benchmark_metrics.json").strip()
    expected_artifacts = _as_str_list(data.get("expected_artifacts")) or [metrics_path]
    submission_path = str(data.get("submission_path") or "").strip()
    role_command_signature = _role_command_signature(command, metrics_path, expected_artifacts, submission_path)
    benchmark_url = str(data.get("benchmark_url") or "").strip()
    dataset_url = str(data.get("dataset_url") or "").strip()
    dataset_version = str(data.get("dataset_version") or "").strip()
    split_name = str(data.get("split_name") or "").strip()
    split_path = str(data.get("split_path") or "").strip()
    split_sha256 = str(data.get("split_sha256") or "").strip().lower()
    license_value = str(data.get("license") or "").strip()
    baseline = str(data.get("baseline") or "").strip()
    baseline_version = str(data.get("baseline_version") or "").strip()
    citation = str(data.get("citation") or "").strip()
    expected_metrics = _as_str_list(data.get("expected_metrics"))
    metric_schema = _metric_schema(data.get("metric_schema"))
    grader = str(data.get("grader") or "").strip()
    grader_path = str(data.get("grader_path") or "").strip()
    grader_version = str(data.get("grader_version") or "").strip()
    grader_sha256 = str(data.get("grader_sha256") or "").strip().lower()
    seed_policy = str(data.get("seed_policy") or "").strip()
    min_repeats = _safe_int(data.get("min_repeats"))
    benchmark_kind = _benchmark_kind(str(data.get("benchmark_kind") or "").strip().lower(), benchmark_url, dataset_url)
    issues = [*parse_issues]
    notes = _as_str_list(data.get("notes"))
    issues.extend(_validate_manifest(name, role, command, metrics_path, source_files, expected_artifacts, grader, submission_path, split_path, grader_path))
    split_sha256_actual, split_hash_issues = _optional_manifest_file_sha256(manifest_path.parent, split_path, "split_path")
    grader_sha256_actual, grader_hash_issues = _optional_manifest_file_sha256(manifest_path.parent, grader_path, "grader_path")
    provenance_issues = formal_benchmark_provenance_issues(
        name=_role_slug(role, base_slug),
        benchmark_kind=benchmark_kind,
        benchmark_url=benchmark_url,
        dataset_url=dataset_url,
        dataset_version=dataset_version,
        split_name=split_name,
        split_sha256=split_sha256,
        split_sha256_actual=split_sha256_actual,
        license_value=license_value,
        baseline_version=baseline_version,
        citation=citation,
    )
    provenance_issues.extend(split_hash_issues)
    provenance_status = "external" if not provenance_issues else "review_required"
    metric_contract_issues = formal_benchmark_metric_contract_issues(
        name=_role_slug(role, base_slug),
        expected_metrics=expected_metrics,
        metric_schema=metric_schema,
        grader_version=grader_version,
        grader_sha256=grader_sha256,
        grader_sha256_actual=grader_sha256_actual,
    )
    metric_contract_issues.extend(grader_hash_issues)
    metric_contract_status = "ready" if not metric_contract_issues else "review_required"
    copied: list[str] = []
    if not issues and copy_files:
        adapter_dir.mkdir(parents=True, exist_ok=True)
        copied, copy_issues = _copy_adapter_files(
            manifest_path.parent,
            adapter_dir,
            command,
            source_files,
            extra_files=_existing_manifest_files(manifest_path.parent, [split_path, grader_path]),
        )
        issues.extend(copy_issues)
    elif not issues:
        issues.extend(_source_file_issues(manifest_path.parent, command, source_files))
    rewritten_command = _rewrite_command(command, slug) if command else []
    rewritten_expected = [_rewrite_path_token(path, slug) for path in expected_artifacts]
    rewritten_metrics = _rewrite_path_token(metrics_path, slug)
    status = "ready" if not issues else "blocked"
    return BenchmarkAdapterRecord(
        name=slug,
        role=role,
        status=status,
        manifest_path=str(manifest_path),
        adapter_dir=str(Path("experiments") / "benchmark-adapters" / slug),
        command=rewritten_command,
        role_command_signature=role_command_signature,
        expected_artifacts=rewritten_expected,
        metrics_path=rewritten_metrics,
        benchmark_url=benchmark_url,
        dataset_url=dataset_url,
        dataset_version=dataset_version,
        split_name=split_name,
        split_path=_rewrite_path_token(split_path, slug) if split_path else "",
        split_sha256=split_sha256,
        split_sha256_actual=split_sha256_actual,
        license=license_value,
        baseline=baseline,
        baseline_version=baseline_version,
        citation=citation,
        expected_metrics=expected_metrics,
        metric_schema=metric_schema,
        grader=_rewrite_path_token(grader, slug) if grader else "",
        grader_path=_rewrite_path_token(grader_path, slug) if grader_path else "",
        submission_path=_rewrite_path_token(submission_path, slug) if submission_path else "",
        grader_version=grader_version,
        grader_sha256=grader_sha256,
        grader_sha256_actual=grader_sha256_actual,
        seed_policy=seed_policy,
        min_repeats=min_repeats,
        benchmark_kind=benchmark_kind,
        provenance_status=provenance_status,
        provenance_issues=provenance_issues,
        metric_contract_status=metric_contract_status,
        metric_contract_issues=metric_contract_issues,
        source_files=source_files,
        copied_files=copied,
        issues=issues,
        notes=notes,
    )


def _with_execution_issues(record: BenchmarkAdapterRecord, config: ExecutionConfig) -> BenchmarkAdapterRecord:
    issues = [*record.issues]
    if record.command:
        executable = str(record.command[0]).strip()
        if executable not in config.allowed_commands:
            issues.append(f"命令 '{executable}' 不在 allowed_commands 白名单中")
        for index, token in enumerate(record.command):
            value = str(token)
            if not value.strip():
                issues.append(f"命令参数 #{index} 为空")
            elif _SHELL_META_PATTERN.search(value):
                issues.append(f"命令参数 #{index} 含 shell 元字符：{value}")
        issues.extend(interpreter_execution_issues(record.command))
    status = "ready" if not issues else "blocked"
    return BenchmarkAdapterRecord(
        name=record.name,
        role=record.role,
        status=status,
        manifest_path=record.manifest_path,
        adapter_dir=record.adapter_dir,
        command=record.command,
        role_command_signature=record.role_command_signature,
        expected_artifacts=record.expected_artifacts,
        metrics_path=record.metrics_path,
        benchmark_url=record.benchmark_url,
        dataset_url=record.dataset_url,
        dataset_version=record.dataset_version,
        split_name=record.split_name,
        split_path=record.split_path,
        split_sha256=record.split_sha256,
        split_sha256_actual=record.split_sha256_actual,
        license=record.license,
        baseline=record.baseline,
        baseline_version=record.baseline_version,
        citation=record.citation,
        expected_metrics=record.expected_metrics,
        metric_schema=record.metric_schema,
        grader=record.grader,
        grader_path=record.grader_path,
        submission_path=record.submission_path,
        grader_version=record.grader_version,
        grader_sha256=record.grader_sha256,
        grader_sha256_actual=record.grader_sha256_actual,
        seed_policy=record.seed_policy,
        min_repeats=record.min_repeats,
        benchmark_kind=record.benchmark_kind,
        provenance_status=record.provenance_status,
        provenance_issues=record.provenance_issues,
        metric_contract_status=record.metric_contract_status,
        metric_contract_issues=record.metric_contract_issues,
        source_files=record.source_files,
        copied_files=record.copied_files,
        issues=_unique(issues),
        notes=record.notes,
    )


def _resolve_manifest_path(value: str, base_dir: Path) -> Path | None:
    raw = Path(value)
    if any(part == ".." for part in raw.parts):
        return None
    try:
        root = base_dir.resolve(strict=True)
    except OSError:
        return None
    path = raw if raw.is_absolute() else root / raw
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if _has_symlink_component(path, root):
        return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _read_manifest(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() in {".toml", ".tml"}:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            return {}, ["manifest 仅支持 .json 或 .toml"]
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"manifest 解析失败：{exc}"]
    if not isinstance(data, dict):
        return {}, ["manifest 顶层必须是对象"]
    return data, []


def _validate_manifest(
    name: str,
    role: str,
    command: list[str],
    metrics_path: str,
    source_files: list[str],
    expected_artifacts: list[str],
    grader: str = "",
    submission_path: str = "",
    split_path: str = "",
    grader_path: str = "",
) -> list[str]:
    issues: list[str] = []
    if not name:
        issues.append("name 不能为空")
    if role and role not in {"candidate", "baseline", "ablation", "other"}:
        issues.append(f"role 必须是 candidate、baseline、ablation 或 other：{role}")
    if not command:
        issues.append("command 不能为空")
    for value, label in [
        (metrics_path, "metrics_path"),
        *[(item, "source_files") for item in source_files],
        *[(item, "expected_artifacts") for item in expected_artifacts],
        *([(grader, "grader")] if grader else []),
        *([(submission_path, "submission_path")] if submission_path else []),
        *([(split_path, "split_path")] if split_path else []),
        *([(grader_path, "grader_path")] if grader_path else []),
    ]:
        if not value or Path(value).is_absolute() or any(part == ".." for part in Path(value).parts):
            issues.append(f"{label} 必须是 manifest 目录内的相对路径：{value}")
    return issues


def _copy_adapter_files(manifest_dir: Path, adapter_dir: Path, command: list[str], source_files: list[str], extra_files: list[str] | None = None) -> tuple[list[str], list[str]]:
    candidates = list(source_files)
    for token in command:
        if _is_copy_candidate(token) and token not in candidates:
            candidates.append(token)
    for token in extra_files or []:
        if token and token not in candidates:
            candidates.append(token)
    copied: list[str] = []
    issues: list[str] = []
    adapter_root = adapter_dir.parent
    if _has_symlink_component(adapter_dir, adapter_root):
        return [], [f"adapter 目标路径含符号链接：{adapter_dir}"]
    for rel_value in candidates:
        source = _manifest_relative_file(manifest_dir, rel_value)
        if source is None:
            issues.append(f"source file 缺失或路径不安全：{rel_value}")
            continue
        rel = Path(rel_value)
        dest = adapter_dir / rel
        if _has_symlink_component(dest, adapter_root):
            issues.append(f"adapter 目标路径含符号链接：{rel_value}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if _has_symlink_component(dest, adapter_root):
            issues.append(f"adapter 目标路径含符号链接：{rel_value}")
            continue
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            issues.append(f"复制 source file 失败 {rel_value}: {exc}")
            continue
        copied.append(str(Path("benchmark-adapters") / adapter_dir.name / rel))
    return copied, issues


def _existing_manifest_files(manifest_dir: Path, values: list[str]) -> list[str]:
    existing: list[str] = []
    for value in values:
        if _manifest_relative_file(manifest_dir, value) is not None:
            existing.append(value)
    return existing


def _optional_manifest_file_sha256(manifest_dir: Path, value: str, label: str) -> tuple[str, list[str]]:
    if not str(value or "").strip():
        return "", []
    path = _manifest_relative_file(manifest_dir, value)
    if path is None:
        return "", [f"{label} 无法读取 manifest 目录内文件：{value}"]
    return _sha256_file(path), []


def _manifest_relative_file(manifest_dir: Path, value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    rel = Path(text)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        return None
    path = manifest_dir / rel
    if _has_symlink_component(path, manifest_dir):
        return None
    try:
        resolved = path.resolve(strict=True)
        root = manifest_dir.resolve(strict=True)
    except OSError:
        return None
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _source_file_issues(manifest_dir: Path, command: list[str], source_files: list[str]) -> list[str]:
    candidates = list(source_files)
    for token in command:
        if _is_copy_candidate(token) and token not in candidates:
            candidates.append(token)
    issues: list[str] = []
    for rel_value in candidates:
        if _manifest_relative_file(manifest_dir, rel_value) is None:
            issues.append(f"source file 缺失或路径不安全：{rel_value}")
    return issues


def _has_symlink_component(path: Path, trusted_root: Path) -> bool:
    try:
        root = trusted_root.resolve(strict=True)
        lexical = path if path.is_absolute() else root / path
        lexical.relative_to(root)
    except (OSError, ValueError):
        return True
    current = root
    for part in lexical.relative_to(root).parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
        if not current.exists():
            break
    return False


def _rewrite_command(command: list[str], slug: str) -> list[str]:
    rewritten: list[str] = []
    for index, token in enumerate(command):
        if index == 0 or token.startswith("-") or not _is_rewritable_path(token):
            rewritten.append(token)
        else:
            rewritten.append(_rewrite_path_token(token, slug))
    return rewritten


def _rewrite_path_token(token: str, slug: str) -> str:
    path = Path(token)
    if path.parts and path.parts[0] == "benchmark-adapters":
        return str(path)
    return str(Path("benchmark-adapters") / slug / path)


def _is_copy_candidate(token: str) -> bool:
    if token.startswith("-"):
        return False
    return _is_rewritable_path(token) and Path(token).suffix == ".py"


def _is_rewritable_path(token: str) -> bool:
    path = Path(token)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        return False
    return "/" in token or "\\" in token or bool(path.suffix)


def _role_command_signature(command: list[str], metrics_path: str, expected_artifacts: list[str], submission_path: str) -> str:
    outputs = {str(metrics_path or "").strip(), str(submission_path or "").strip(), *[str(item).strip() for item in expected_artifacts]}
    outputs.discard("")
    normalized = ["<output>" if str(token).strip() in outputs else str(token).strip() for token in command]
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _blocking_issues(manifest_paths: list[str], records: list[BenchmarkAdapterRecord], usable: list[BenchmarkAdapterRecord]) -> list[str]:
    issues: list[str] = []
    if not manifest_paths:
        issues.append("execution.mode=benchmark 需要至少一个 benchmark manifest。")
    for record in records:
        issues.extend(f"{record.name}: {issue}" for issue in record.issues)
    if manifest_paths and not usable:
        issues.append("没有可执行的 benchmark adapter。")
    return _unique(issues)


def _paper_grade_status(records: list[BenchmarkAdapterRecord], repeats: int, paper_grade: PaperGradeConfig | None = None) -> dict[str, Any]:
    config = paper_grade or PaperGradeConfig()
    min_ready_adapters = max(3, int(config.min_benchmark_roles or 0))
    min_execution_repeats = max(1, int(config.min_execution_repeats or 0))
    issues: list[str] = []
    ready = [record for record in records if record.status == "ready"]
    roles = {record.role for record in ready if record.role}
    missing_roles = [role for role in ["candidate", "baseline", "ablation"] if role not in roles]
    if missing_roles:
        issues.append("paper-grade benchmark 需要 candidate/baseline/ablation 三类 role：" + ", ".join(missing_roles))
    if len(ready) < min_ready_adapters:
        issues.append(f"paper-grade benchmark 至少需要 {min_ready_adapters} 个 ready adapter，当前 {len(ready)} 个。")
    metric_sets = [{metric for metric in record.expected_metrics if metric} for record in ready if record.role in {"candidate", "baseline", "ablation"}]
    common_metrics = set.intersection(*metric_sets) if len(metric_sets) >= 2 else set()
    if len(metric_sets) >= 2 and not common_metrics:
        issues.append("candidate/baseline/ablation 的 expected_metrics 没有共同指标。")
    issues.extend(_paper_grade_role_command_issues(ready))
    configured_repeats = max(1, int(repeats))
    if configured_repeats < min_execution_repeats:
        issues.append(f"paper-grade benchmark 至少需要 repeats >= {min_execution_repeats}，当前 {configured_repeats}。")
    for record in ready:
        if record.min_repeats < min_execution_repeats:
            issues.append(f"{record.name}: paper-grade min_repeats 至少需要 {min_execution_repeats}，当前 {record.min_repeats}")
        if record.min_repeats > configured_repeats:
            issues.append(f"{record.name}: repeats {configured_repeats} < min_repeats {record.min_repeats}")
        if record.provenance_status != "external":
            issues.extend(record.provenance_issues or [f"{record.name}: paper-grade formal benchmark 需要公开外部 provenance"])
        if record.metric_contract_status != "ready":
            issues.extend(record.metric_contract_issues or [f"{record.name}: paper-grade benchmark 需要 metric/grader contract"])
    repair_suggestions = _paper_grade_repair_suggestions(
        ready,
        configured_repeats,
        missing_roles,
        common_metrics,
        min_ready_adapters=min_ready_adapters,
        min_execution_repeats=min_execution_repeats,
    )
    return {"status": "ready" if ready and not issues else "review_required", "issues": _unique(issues), "repair_suggestions": repair_suggestions}


def _paper_grade_role_command_issues(records: list[BenchmarkAdapterRecord]) -> list[str]:
    issues: list[str] = []
    for roles in _duplicate_role_command_groups(records):
        issues.append(
            "candidate/baseline/ablation 的 command 需要显式区分 method/variant/config；重复 role command："
            + ", ".join(roles)
        )
    return issues


def _duplicate_role_command_groups(records: list[BenchmarkAdapterRecord]) -> list[list[str]]:
    role_records = [record for record in records if record.role in {"candidate", "baseline", "ablation"} and record.role_command_signature]
    by_signature: dict[str, list[str]] = {}
    for record in role_records:
        by_signature.setdefault(record.role_command_signature, []).append(record.role)
    return [sorted(set(roles)) for roles in by_signature.values() if len(set(roles)) > 1]


def _paper_grade_repair_suggestions(
    ready: list[BenchmarkAdapterRecord],
    configured_repeats: int,
    missing_roles: list[str],
    common_metrics: set[str],
    *,
    min_ready_adapters: int,
    min_execution_repeats: int,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for role in missing_roles:
        suggestions.append(
            {
                "kind": "missing_manifest_role",
                "role": role,
                "target": f"role:{role}",
                "target_path_hint": f"benchmarks/{role}-manifest.json",
                "action": "新增真实 benchmark manifest，并把 role 设为 candidate/baseline/ablation 中缺失的一类。",
                "manifest_template": _manifest_template(role, ready, common_metrics, max(configured_repeats, min_execution_repeats)),
            }
        )
    if ready and len(ready) < min_ready_adapters and not missing_roles:
        suggestions.append(
            {
                "kind": "insufficient_ready_adapters",
                "target": "benchmark_manifest_paths",
                "action": f"补充至少 {min_ready_adapters} 个 ready adapter，覆盖候选方法、直接 baseline 和关键 ablation。",
                "minimum_ready_adapters": min_ready_adapters,
                "current_ready_adapters": len(ready),
            }
        )
    metric_by_role = {
        record.role: record.expected_metrics
        for record in ready
        if record.role in {"candidate", "baseline", "ablation"} and record.expected_metrics
    }
    if len(metric_by_role) >= 2 and not common_metrics:
        suggestions.append(
            {
                "kind": "align_expected_metrics",
                "target": "expected_metrics",
                "action": "让 candidate/baseline/ablation manifest 的 expected_metrics 至少共享一个论文核心指标。",
                "current_expected_metrics": metric_by_role,
            }
        )
    for roles in _duplicate_role_command_groups(ready):
        suggestions.append(
            {
                "kind": "differentiate_role_commands",
                "target": "command",
                "roles": roles,
                "action": "让这些 role 的 command 显式包含不同 method/variant/config 参数；只改变 metrics 输出路径不能支撑真实对照。",
            }
        )
    if configured_repeats < min_execution_repeats:
        suggestions.append(
            {
                "kind": "increase_execution_repeats",
                "target": "execution.repeats",
                "action": f"把执行配置 repeats 提高到至少 {min_execution_repeats} 后重跑。",
                "recommended_execution_config": {"execution_repeats": min_execution_repeats},
            }
        )
    required_repeats = configured_repeats
    for record in ready:
        if record.provenance_status != "external":
            suggestions.append(
                {
                    "kind": "external_benchmark_provenance",
                    "target": "dataset_url",
                    "manifest_path": record.manifest_path,
                    "role": record.role,
                    "action": "将结构 fixture/本地任务替换为公开外部 benchmark/data 来源，并填写官方 http(s) dataset_url、license、baseline_version 和 citation。",
                    "current_provenance_status": record.provenance_status,
                    "current_benchmark_kind": record.benchmark_kind,
                    "issues": record.provenance_issues[:4],
                    "field_patch": {
                        "benchmark_kind": "external",
                        "dataset_url": "TODO official dataset/task URL",
                        "dataset_version": "TODO dataset/benchmark version",
                        "split_name": "TODO official split/task set",
                        "split_path": "TODO frozen split/task manifest path",
                        "split_sha256": "TODO 64-hex SHA256 of frozen split/task manifest",
                    },
                }
            )
        if record.metric_contract_status != "ready":
            suggestions.append(
                {
                    "kind": "metric_grader_contract",
                    "target": "metric_schema",
                    "manifest_path": record.manifest_path,
                    "role": record.role,
                    "action": "补齐 expected_metrics 对应的 metric_schema，并固定 grader_version 与 grader_sha256。",
                    "current_metric_contract_status": record.metric_contract_status,
                    "issues": record.metric_contract_issues[:4],
                    "field_patch": {
                        "metric_schema": _metric_schema_template(record.expected_metrics),
                        "grader_path": "TODO local grader/evaluation wrapper path",
                        "grader_version": "TODO grader/evaluator version",
                        "grader_sha256": "TODO 64-hex SHA256 of grader or official evaluation wrapper",
                    },
                }
            )
        if record.min_repeats < min_execution_repeats:
            suggestions.append(
                {
                    "kind": "manifest_field_patch",
                    "target": "min_repeats",
                    "manifest_path": record.manifest_path,
                    "role": record.role,
                    "action": f"把 manifest 的 min_repeats 提高到至少 {min_execution_repeats}，并确认 benchmark 协议允许这些重复。",
                    "field_patch": {"min_repeats": min_execution_repeats},
                }
            )
        required_repeats = max(required_repeats, record.min_repeats)
    if required_repeats > configured_repeats:
        suggestions.append(
            {
                "kind": "increase_execution_repeats",
                "target": "execution.repeats",
                "action": "执行配置 repeats 需要覆盖所有 manifest 的 min_repeats。",
                "recommended_execution_config": {"execution_repeats": required_repeats},
            }
        )
    return _unique_suggestions(suggestions)


def _manifest_template(
    role: str,
    ready: list[BenchmarkAdapterRecord],
    common_metrics: set[str],
    configured_repeats: int,
) -> dict[str, Any]:
    exemplar = ready[0] if ready else None
    metrics = sorted(common_metrics) or (exemplar.expected_metrics if exemplar and exemplar.expected_metrics else ["TODO_metric"])
    provenance_exemplar = exemplar if exemplar and exemplar.provenance_status == "external" else None
    return {
        "name": f"TODO {role} benchmark adapter",
        "role": role,
        "command": ["python3", f"run_{role}_benchmark.py", "--metrics", f"{role}_metrics.json"],
        "metrics_path": f"{role}_metrics.json",
        "source_files": [f"run_{role}_benchmark.py"],
        "expected_artifacts": [f"{role}_metrics.json"],
        "benchmark_kind": "external",
        "benchmark_url": provenance_exemplar.benchmark_url if provenance_exemplar and provenance_exemplar.benchmark_url else "TODO official benchmark URL",
        "dataset_url": provenance_exemplar.dataset_url if provenance_exemplar and provenance_exemplar.dataset_url else "TODO official dataset/task URL",
        "dataset_version": provenance_exemplar.dataset_version if provenance_exemplar and provenance_exemplar.dataset_version else "TODO dataset/benchmark version",
        "split_name": provenance_exemplar.split_name if provenance_exemplar and provenance_exemplar.split_name else "TODO official split/task set",
        "split_path": provenance_exemplar.split_path if provenance_exemplar and provenance_exemplar.split_path else "TODO frozen split/task manifest path",
        "split_sha256": provenance_exemplar.split_sha256 if provenance_exemplar and provenance_exemplar.split_sha256 else "TODO 64-hex SHA256 of frozen split/task manifest",
        "license": provenance_exemplar.license if provenance_exemplar and provenance_exemplar.license else "TODO benchmark/data license",
        "baseline": exemplar.baseline if exemplar and exemplar.baseline else "TODO matched baseline/control",
        "baseline_version": provenance_exemplar.baseline_version if provenance_exemplar and provenance_exemplar.baseline_version else "TODO implementation version/commit",
        "citation": provenance_exemplar.citation if provenance_exemplar and provenance_exemplar.citation else "TODO DOI/BibTeX key",
        "expected_metrics": metrics,
        "metric_schema": _metric_schema_template(metrics),
        "grader": f"run_{role}_benchmark.py",
        "grader_path": f"run_{role}_benchmark.py",
        "grader_version": "TODO grader/evaluator version",
        "grader_sha256": "TODO 64-hex SHA256 of grader or official evaluation wrapper",
        "submission_path": f"{role}_submission.csv",
        "seed_policy": exemplar.seed_policy if exemplar and exemplar.seed_policy else "RESEARCH_AGENT_SEED fixes split/task sampling and stochastic state",
        "min_repeats": max(3, configured_repeats),
        "notes": ["TODO replace every TODO field with a verified benchmark source before execution approval."],
    }


def _manual_tasks(records: list[BenchmarkAdapterRecord]) -> list[str]:
    tasks = [
        "确认 manifest 中的命令对应真实公开 benchmark、固定数据划分和可复现实验入口。",
        "确认 benchmark 数据许可、下载方式、baseline 版本和评价指标定义。",
    ]
    for record in records:
        tasks.extend(record.notes)
    return _unique(tasks)


def _record(
    name: str,
    status: str,
    manifest_path: str,
    adapter_dir: str,
    issues: list[str] | None = None,
) -> BenchmarkAdapterRecord:
    return BenchmarkAdapterRecord(
        name=name,
        role="",
        status=status,
        manifest_path=manifest_path,
        adapter_dir=adapter_dir,
        command=[],
        role_command_signature="",
        expected_artifacts=[],
        metrics_path="",
        benchmark_url="",
        dataset_url="",
        dataset_version="",
        split_name="",
        split_path="",
        split_sha256="",
        split_sha256_actual="",
        license="",
        baseline="",
        baseline_version="",
        citation="",
        expected_metrics=[],
        metric_schema={},
        grader="",
        grader_path="",
        submission_path="",
        grader_version="",
        grader_sha256="",
        grader_sha256_actual="",
        seed_policy="",
        min_repeats=0,
        benchmark_kind="",
        provenance_status="review_required",
        provenance_issues=[],
        metric_contract_status="review_required",
        metric_contract_issues=[],
        source_files=[],
        copied_files=[],
        issues=issues or [],
        notes=[],
    )


def _command_payload(record: BenchmarkAdapterRecord) -> dict[str, Any]:
    return {
        "name": record.name,
        "role": record.role,
        "adapter_id": record.name,
        "comparison_group": _comparison_group(record),
        "command": record.command,
        "role_command_signature": record.role_command_signature,
        "expected_artifacts": record.expected_artifacts,
        "metrics_path": record.metrics_path,
        "benchmark_url": record.benchmark_url,
        "dataset_url": record.dataset_url,
        "dataset_version": record.dataset_version,
        "split_name": record.split_name,
        "split_path": record.split_path,
        "split_sha256": record.split_sha256,
        "split_sha256_actual": record.split_sha256_actual,
        "license": record.license,
        "baseline": record.baseline,
        "baseline_version": record.baseline_version,
        "citation": record.citation,
        "expected_metrics": record.expected_metrics,
        "metric_schema": record.metric_schema,
        "grader": record.grader,
        "grader_path": record.grader_path,
        "submission_path": record.submission_path,
        "grader_version": record.grader_version,
        "grader_sha256": record.grader_sha256,
        "grader_sha256_actual": record.grader_sha256_actual,
        "seed_policy": record.seed_policy,
        "min_repeats": record.min_repeats,
        "benchmark_kind": record.benchmark_kind,
        "provenance_status": record.provenance_status,
        "provenance_issues": record.provenance_issues,
        "metric_contract_status": record.metric_contract_status,
        "metric_contract_issues": record.metric_contract_issues,
    }


def _comparison_group(record: BenchmarkAdapterRecord) -> str:
    """Fingerprint the dataset/task/split contract shared by comparable roles."""
    payload = {
        "benchmark_url": record.benchmark_url,
        "dataset_url": record.dataset_url,
        "dataset_version": record.dataset_version,
        "split_name": record.split_name,
        "split_sha256": record.split_sha256_actual or record.split_sha256,
        "expected_metrics": sorted(record.expected_metrics),
        "grader_version": record.grader_version,
        "grader_sha256": record.grader_sha256_actual or record.grader_sha256,
    }
    if not any(value for key, value in payload.items() if key != "expected_metrics"):
        return "default"
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def formal_benchmark_metric_contract_issues(
    *,
    name: str,
    expected_metrics: list[str],
    metric_schema: dict[str, dict[str, str]],
    grader_version: str = "",
    grader_sha256: str = "",
    grader_sha256_actual: str = "",
) -> list[str]:
    record_name = str(name or "benchmark").strip()
    issues: list[str] = []
    if not expected_metrics:
        issues.append(f"{record_name}: expected_metrics 不能为空")
    if not metric_schema:
        issues.append(f"{record_name}: metric_schema 不能为空")
    for metric in expected_metrics:
        spec = metric_schema.get(metric)
        if not isinstance(spec, dict):
            issues.append(f"{record_name}: metric_schema 缺少 expected metric：{metric}")
            continue
        direction = str(spec.get("direction") or "").strip()
        unit = str(spec.get("unit") or "").strip()
        description = str(spec.get("description") or "").strip()
        if direction not in _METRIC_DIRECTIONS:
            issues.append(f"{record_name}: metric_schema[{metric}].direction 必须是 {', '.join(sorted(_METRIC_DIRECTIONS))}")
        if _placeholder_value(unit):
            issues.append(f"{record_name}: metric_schema[{metric}].unit 缺少真实单位")
        if _placeholder_value(description):
            issues.append(f"{record_name}: metric_schema[{metric}].description 缺少指标定义")
    if _placeholder_value(grader_version):
        issues.append(f"{record_name}: grader_version 缺少真实版本")
    if not _valid_sha256(grader_sha256):
        issues.append(f"{record_name}: grader_sha256 必须是 grader/official evaluation wrapper 的 64 位 SHA256")
    elif grader_sha256_actual and grader_sha256.lower() != grader_sha256_actual.lower():
        issues.append(f"{record_name}: grader_sha256 与 grader_path 实际 SHA256 不一致")
    return _unique(issues)


def formal_benchmark_provenance_issues(
    *,
    name: str,
    benchmark_kind: str = "",
    benchmark_url: str = "",
    dataset_url: str = "",
    dataset_version: str = "",
    split_name: str = "",
    split_sha256: str = "",
    split_sha256_actual: str = "",
    license_value: str = "",
    baseline_version: str = "",
    citation: str = "",
) -> list[str]:
    record_name = str(name or "benchmark").strip()
    kind = _benchmark_kind(benchmark_kind, benchmark_url, dataset_url)
    issues: list[str] = []
    if kind and kind not in _EXTERNAL_BENCHMARK_KINDS:
        issues.append(f"{record_name}: benchmark_kind={kind} 不是公开外部 benchmark")
    if not _is_external_http_url(dataset_url):
        issues.append(f"{record_name}: paper-grade formal benchmark 需要公开 http(s) dataset_url，当前 {dataset_url or 'missing'}")
    if benchmark_url and not _is_external_http_url(benchmark_url):
        issues.append(f"{record_name}: benchmark_url 必须是公开 http(s) URL，当前 {benchmark_url}")
    required = {
        "license": license_value,
        "baseline_version": baseline_version,
        "citation": citation,
        "dataset_version": dataset_version,
        "split_name": split_name,
    }
    for field, value in required.items():
        if _placeholder_value(value):
            issues.append(f"{record_name}: paper-grade manifest provenance 缺少真实 {field}")
    if not _valid_sha256(split_sha256):
        issues.append(f"{record_name}: split_sha256 必须是固定 split/task manifest 的 64 位 SHA256")
    elif split_sha256_actual and split_sha256.lower() != split_sha256_actual.lower():
        issues.append(f"{record_name}: split_sha256 与 split_path 实际 SHA256 不一致")
    return _unique(issues)


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _metric_schema(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, raw in value.items():
        metric = str(key).strip()
        if not metric or not isinstance(raw, dict):
            continue
        result[metric] = {
            "direction": str(raw.get("direction") or "").strip(),
            "unit": str(raw.get("unit") or "").strip(),
            "description": str(raw.get("description") or "").strip(),
        }
    return result


def _metric_schema_template(metrics: list[str]) -> dict[str, dict[str, str]]:
    values = [str(metric).strip() for metric in metrics if str(metric).strip()] or ["TODO_metric"]
    return {
        metric: {
            "direction": "TODO higher_is_better|lower_is_better|target|descriptive",
            "unit": "TODO unit",
            "description": "TODO metric definition",
        }
        for metric in values
    }


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _benchmark_kind(value: str, benchmark_url: str, dataset_url: str) -> str:
    explicit = str(value or "").strip().lower()
    if explicit:
        return explicit
    data = str(dataset_url or "").strip().lower()
    benchmark = str(benchmark_url or "").strip().lower()
    if _is_external_http_url(dataset_url) and (not benchmark_url or _is_external_http_url(benchmark_url)):
        return "external"
    if data.startswith("procedural://") or benchmark.startswith("procedural://"):
        return "procedural"
    if data.startswith("file://") or benchmark.startswith("file://"):
        return "local"
    if data.startswith("/") or data.startswith("./") or benchmark.startswith("/") or benchmark.startswith("./"):
        return "local"
    if not data and not benchmark:
        return "incomplete"
    return "non_external"


def _is_external_http_url(value: str) -> bool:
    text = str(value or "").strip()
    if _placeholder_value(text):
        return False
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not any([address.is_private, address.is_loopback, address.is_link_local, address.is_multicast, address.is_unspecified])


def _placeholder_value(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lower = text.lower()
    return any(marker in lower for marker in _PLACEHOLDER_MARKERS)


def _valid_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value or "").strip()))


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return slug[:48].strip("-") or f"benchmark-{digest}"


def _role_slug(role: str, slug: str) -> str:
    if role in {"candidate", "baseline", "ablation"} and not slug.startswith(f"{role}-"):
        return f"{role}-{slug}"
    return slug


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _unique_suggestions(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


