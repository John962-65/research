from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .benchmark_adapter import audit_benchmark_adapter_config, formal_benchmark_metric_contract_issues, formal_benchmark_provenance_issues
from .config import ExecutionConfig
from .models import BenchmarkPlan, ExperimentPlan, ResearchPlan


BENCHMARK_READINESS_JSON = "03-benchmark-readiness.json"
BENCHMARK_READINESS_MD = "03-benchmark-readiness.md"


def write_benchmark_readiness_artifacts(
    research_plan: ResearchPlan,
    experiment_plan: ExperimentPlan,
    benchmark_plan: BenchmarkPlan,
    execution_config: ExecutionConfig,
    out_dir: Path,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    report = build_benchmark_readiness_report(research_plan, experiment_plan, benchmark_plan, execution_config, base_dir=base_dir)
    write_json(out_dir / BENCHMARK_READINESS_JSON, report)
    write_text(out_dir / BENCHMARK_READINESS_MD, render_benchmark_readiness_markdown(report))
    return report


def build_benchmark_readiness_report(
    research_plan: ResearchPlan,
    experiment_plan: ExperimentPlan,
    benchmark_plan: BenchmarkPlan,
    execution_config: ExecutionConfig,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    selected = [candidate for candidate in benchmark_plan.candidates if candidate.name in set(benchmark_plan.selected_names)]
    if not selected:
        selected = benchmark_plan.candidates[:3]
    adapter_report = audit_benchmark_adapter_config(execution_config, base_dir=base_dir) if execution_config.mode == "benchmark" else None
    checks = [
        _mode_check(execution_config, adapter_report),
        _candidate_check(selected, benchmark_plan),
        _manifest_metadata_check(execution_config, adapter_report),
        _manifest_metric_contract_check(execution_config, adapter_report),
        _manifest_role_command_check(execution_config, adapter_report),
        _metric_check(research_plan, experiment_plan, selected),
        _baseline_check(research_plan, experiment_plan, selected),
        _artifact_check(execution_config, adapter_report),
    ]
    blocking = [action for check in checks if check["status"] == "block" for action in check["required_actions"]]
    manual = [action for check in checks if check["status"] == "warn" for action in check["required_actions"]]
    status = "block" if blocking else "ready_for_benchmark" if execution_config.mode == "benchmark" else "needs_benchmark_upgrade"
    confidence = sum(_check_weight(check["status"]) for check in checks) / max(1, len(checks))
    return {
        "topic": research_plan.topic,
        "status": status,
        "execution_mode": execution_config.mode,
        "confidence_score": round(confidence, 3),
        "selected_benchmarks": [candidate.name for candidate in selected],
        "checks": checks,
        "adapter_report": asdict(adapter_report) if adapter_report is not None and is_dataclass(adapter_report) else {},
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "recommended_actions": _recommended_actions(status, blocking, manual, execution_config.mode),
    }


def render_benchmark_readiness_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Benchmark Readiness Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 执行模式：{report.get('execution_mode') or '-'}",
        f"- 置信度：{float(report.get('confidence_score') or 0.0):.3f}",
        f"- 选中 benchmark：{', '.join(str(item) for item in report.get('selected_benchmarks', []) if str(item).strip()) or '-'}",
        "",
        "## Readiness Checks",
        "| 检查项 | 状态 | 证据 | 动作 |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if not isinstance(check, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(check.get("name") or "")),
                    _cell(str(check.get("status") or "")),
                    _cell("；".join(str(item) for item in check.get("evidence", []) if str(item).strip()) or "-"),
                    _cell("；".join(str(item) for item in check.get("required_actions", []) if str(item).strip()) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    blocking = report.get("blocking_issues", []) if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    manual = report.get("manual_tasks", []) if isinstance(report.get("manual_tasks"), list) else []
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    actions = report.get("recommended_actions", []) if isinstance(report.get("recommended_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    adapter = report.get("adapter_report") if isinstance(report.get("adapter_report"), dict) else {}
    if adapter:
        suggestions = adapter.get("paper_grade_repair_suggestions") if isinstance(adapter.get("paper_grade_repair_suggestions"), list) else []
        lines.extend(
            [
                "",
                "## Adapter Dry Run",
                f"- 状态：{adapter.get('status') or '-'}",
                f"- Manifest 数：{len(adapter.get('manifest_paths', []) if isinstance(adapter.get('manifest_paths'), list) else [])}",
                f"- 可执行命令：{len(adapter.get('commands', []) if isinstance(adapter.get('commands'), list) else [])}",
                f"- Paper-grade：{adapter.get('paper_grade_status') or '-'}，repair_suggestions={len(suggestions)}",
            ]
        )
        if suggestions:
            lines.extend(["", "### Paper-grade 修复建议", "| 类型 | 目标 | 动作 |", "| --- | --- | --- |"])
            for item in suggestions:
                if not isinstance(item, dict):
                    continue
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
    return "\n".join(lines)


def _mode_check(execution_config: ExecutionConfig, adapter_report: Any) -> dict[str, Any]:
    if execution_config.mode == "benchmark":
        blocking: list[str] = []
        if adapter_report is None or getattr(adapter_report, "status", "") != "ready":
            blocking.append("benchmark 模式必须配置至少一个 ready benchmark manifest adapter。")
        return _check(
            "execution_mode",
            "block" if blocking else "pass",
            [f"mode={execution_config.mode}", f"manifests={len(execution_config.benchmark_manifest_paths)}"],
            blocking,
        )
    if execution_config.mode == "local":
        return _check(
            "execution_mode",
            "warn",
            [f"mode={execution_config.mode}", "local evidence can be useful but is not a standardized benchmark"],
            ["如论文要声称 benchmark 结果，请切换 execution.mode=benchmark 并配置 benchmark_manifest_paths。"],
        )
    return _check(
        "execution_mode",
        "warn",
        [f"mode={execution_config.mode}", "simulated evidence cannot support benchmark claims"],
        ["当前为 simulated，只能用于 smoke；如要真实 benchmark，请切换 benchmark 模式并配置 adapter manifest。"],
    )


def _candidate_check(selected: list[Any], benchmark_plan: BenchmarkPlan) -> dict[str, Any]:
    actions: list[str] = []
    if not selected:
        actions.append("补齐 03-benchmark-plan 中的候选 benchmark。")
    manual_required = sum(1 for candidate in selected if str(getattr(candidate, "status", "") or "") == "manual_required")
    missing_url = sum(1 for candidate in selected if not str(getattr(candidate, "url", "") or "").strip())
    if manual_required:
        actions.append("人工确认选中 benchmark 的访问方式、许可证、下载入口和引用要求。")
    if missing_url:
        actions.append("为没有 URL 的 benchmark/scenario suite 补正式来源或说明自建任务集。")
    status = "block" if not selected else "warn" if actions else "pass"
    return _check(
        "benchmark_candidates",
        status,
        [
            f"selected={len(selected)}",
            f"required_actions={len(benchmark_plan.required_actions)}",
            f"warnings={len(benchmark_plan.warnings)}",
            f"missing_url={missing_url}",
        ],
        actions,
    )


def _manifest_metadata_check(execution_config: ExecutionConfig, adapter_report: Any) -> dict[str, Any]:
    if execution_config.mode != "benchmark":
        return _check(
        "manifest_provenance",
        "warn",
        ["no benchmark manifest provenance in non-benchmark mode"],
        ["真实 benchmark run 需要 manifest 声明公开 http(s) benchmark_url/dataset_url、license、baseline_version 和 citation。"],
        )
    adapters = getattr(adapter_report, "adapters", []) if adapter_report is not None else []
    missing: list[str] = []
    evidence: list[str] = [f"adapters={len(adapters)}"]
    for adapter in adapters:
        name = str(getattr(adapter, "name", "") or "benchmark")
        provenance_status = str(getattr(adapter, "provenance_status", "") or "")
        record_issues = getattr(adapter, "provenance_issues", None)
        if isinstance(record_issues, list):
            provenance_issues = [str(item) for item in record_issues if str(item).strip()]
        else:
            provenance_issues = formal_benchmark_provenance_issues(
                name=name,
                benchmark_kind=str(getattr(adapter, "benchmark_kind", "") or ""),
                benchmark_url=str(getattr(adapter, "benchmark_url", "") or ""),
                dataset_url=str(getattr(adapter, "dataset_url", "") or ""),
                dataset_version=str(getattr(adapter, "dataset_version", "") or ""),
                split_name=str(getattr(adapter, "split_name", "") or ""),
                split_sha256=str(getattr(adapter, "split_sha256", "") or ""),
                split_sha256_actual=str(getattr(adapter, "split_sha256_actual", "") or ""),
                license_value=str(getattr(adapter, "license", "") or ""),
                baseline_version=str(getattr(adapter, "baseline_version", "") or ""),
                citation=str(getattr(adapter, "citation", "") or ""),
            )
        if provenance_issues:
            evidence.append(f"{name}: provenance={provenance_status or 'review_required'}")
            missing.extend(provenance_issues)
            continue
        data_url = str(getattr(adapter, "dataset_url", "") or getattr(adapter, "benchmark_url", "") or "").strip()
        license_value = str(getattr(adapter, "license", "") or "").strip()
        baseline_version = str(getattr(adapter, "baseline_version", "") or "").strip()
        citation = str(getattr(adapter, "citation", "") or "").strip()
        fields = {
            "dataset_url_or_benchmark_url": data_url,
            "dataset_version": str(getattr(adapter, "dataset_version", "") or "").strip(),
            "split_name": str(getattr(adapter, "split_name", "") or "").strip(),
            "split_sha256": str(getattr(adapter, "split_sha256", "") or "").strip(),
            "license": license_value,
            "baseline_version": baseline_version,
            "citation": citation,
        }
        missing_fields = [field for field, value in fields.items() if not value]
        evidence.append(f"{name}: missing={','.join(missing_fields) or '-'}")
        if missing_fields:
            missing.append(f"{name}: manifest 缺少 {', '.join(missing_fields)}。")
    if not adapters:
        missing.append("benchmark 模式缺少可审计的 manifest provenance。")
    return _check(
        "manifest_provenance",
        "block" if missing else "pass",
        evidence,
        [*missing, "补齐公开外部 benchmark/data 来源 URL、dataset_version、split_name、split_sha256、许可证、baseline 版本和 citation 后再批准执行。"] if missing else [],
    )


def _metric_check(research_plan: ResearchPlan, experiment_plan: ExperimentPlan, selected: list[Any]) -> dict[str, Any]:
    plan_terms = _terms([*research_plan.metrics, *experiment_plan.metrics])
    benchmark_terms = _terms([item for candidate in selected for item in getattr(candidate, "expected_metrics", [])])
    overlap = sorted(plan_terms & benchmark_terms)
    status = "pass" if overlap else "warn"
    actions = [] if overlap else ["让 03-experiment-plan metrics 与选中 benchmark expected_metrics 至少共享一个核心指标。"]
    return _check(
        "metric_alignment",
        status,
        [f"plan_metrics={len(plan_terms)}", f"benchmark_metrics={len(benchmark_terms)}", f"overlap={', '.join(overlap) or '-'}"],
        actions,
    )


def _manifest_metric_contract_check(execution_config: ExecutionConfig, adapter_report: Any) -> dict[str, Any]:
    if execution_config.mode != "benchmark":
        return _check(
            "manifest_metric_contract",
            "warn",
            ["no benchmark metric/grader contract in non-benchmark mode"],
            ["真实 benchmark run 需要 manifest 声明 metric_schema、grader_version 和 grader_sha256。"],
        )
    adapters = getattr(adapter_report, "adapters", []) if adapter_report is not None else []
    missing: list[str] = []
    evidence: list[str] = [f"adapters={len(adapters)}"]
    for adapter in adapters:
        name = str(getattr(adapter, "name", "") or "benchmark")
        record_issues = getattr(adapter, "metric_contract_issues", None)
        if isinstance(record_issues, list):
            issues = [str(item) for item in record_issues if str(item).strip()]
        else:
            issues = formal_benchmark_metric_contract_issues(
                name=name,
                expected_metrics=[str(item) for item in getattr(adapter, "expected_metrics", []) if str(item).strip()],
                metric_schema=_metric_schema(getattr(adapter, "metric_schema", {})),
                grader_version=str(getattr(adapter, "grader_version", "") or ""),
                grader_sha256=str(getattr(adapter, "grader_sha256", "") or ""),
                grader_sha256_actual=str(getattr(adapter, "grader_sha256_actual", "") or ""),
            )
        evidence.append(f"{name}: metric_contract={'review_required' if issues else 'ready'}")
        missing.extend(issues)
    if not adapters:
        missing.append("benchmark 模式缺少可审计的 metric/grader contract。")
    return _check(
        "manifest_metric_contract",
        "block" if missing else "pass",
        evidence,
        [*missing, "补齐 metric_schema、grader_version 和 grader_sha256 后再批准执行。"] if missing else [],
    )


def _manifest_role_command_check(execution_config: ExecutionConfig, adapter_report: Any) -> dict[str, Any]:
    if execution_config.mode != "benchmark":
        return _check(
            "manifest_role_commands",
            "warn",
            ["no benchmark role command contract in non-benchmark mode"],
            ["真实 benchmark run 需要 candidate/baseline/ablation 命令显式区分 method/variant/config。"],
        )
    adapters = getattr(adapter_report, "adapters", []) if adapter_report is not None else []
    role_records = [
        adapter
        for adapter in adapters
        if str(getattr(adapter, "status", "") or "") == "ready" and str(getattr(adapter, "role", "") or "") in {"candidate", "baseline", "ablation"}
    ]
    evidence: list[str] = [f"role_adapters={len(role_records)}"]
    missing: list[str] = []
    by_signature: dict[str, list[str]] = {}
    for adapter in role_records:
        role = str(getattr(adapter, "role", "") or "")
        signature = str(getattr(adapter, "role_command_signature", "") or "")
        if not signature:
            missing.append(f"{getattr(adapter, 'name', role)}: 缺少 role_command_signature")
            continue
        by_signature.setdefault(signature, []).append(role)
    for roles in by_signature.values():
        unique_roles = sorted(set(roles))
        if len(unique_roles) > 1:
            missing.append("重复 role command：" + ", ".join(unique_roles))
    evidence.append(f"unique_role_commands={len(by_signature)}")
    return _check(
        "manifest_role_commands",
        "block" if missing else "pass",
        evidence,
        [*missing, "让每个 role 的 command 显式包含不同 method/variant/config 参数；只改变 metrics 输出路径不能支撑真实对照。"] if missing else [],
    )


def _baseline_check(research_plan: ResearchPlan, experiment_plan: ExperimentPlan, selected: list[Any]) -> dict[str, Any]:
    plan_terms = _terms([*research_plan.baselines, experiment_plan.baseline])
    benchmark_terms = _terms([item for candidate in selected for item in getattr(candidate, "baselines", [])])
    overlap = sorted(plan_terms & benchmark_terms)
    status = "pass" if overlap else "warn"
    actions = [] if overlap else ["让实验 baseline 与 benchmark 推荐 baseline 对齐，或在 03-experiment-plan.md 写明等价映射。"]
    return _check(
        "baseline_alignment",
        status,
        [f"plan_baselines={len(plan_terms)}", f"benchmark_baselines={len(benchmark_terms)}", f"overlap={', '.join(overlap) or '-'}"],
        actions,
    )


def _artifact_check(execution_config: ExecutionConfig, adapter_report: Any) -> dict[str, Any]:
    if execution_config.mode != "benchmark":
        return _check(
            "artifact_contract",
            "warn",
            ["no benchmark adapter artifact contract in non-benchmark mode"],
            ["配置 benchmark manifest 的 metrics_path 和 expected_artifacts，保证结果能被 04-results/readiness/runbook 审计。"],
        )
    commands = getattr(adapter_report, "commands", []) if adapter_report is not None else []
    missing = []
    for command in commands:
        expected = command.get("expected_artifacts", []) if isinstance(command, dict) else []
        if not expected:
            missing.append(str(command.get("name") or "benchmark") if isinstance(command, dict) else "benchmark")
    return _check(
        "artifact_contract",
        "block" if missing else "pass",
        [f"adapter_commands={len(commands)}", f"missing_expected_artifacts={len(missing)}"],
        [f"为 adapter 命令补 expected_artifacts：{', '.join(missing)}。"] if missing else [],
    )


def _check(name: str, status: str, evidence: list[str], actions: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "evidence": evidence,
        "required_actions": _unique(actions),
    }


def _recommended_actions(status: str, blocking: list[str], manual: list[str], mode: str) -> list[str]:
    if status == "ready_for_benchmark":
        return ["人工确认 benchmark 许可证、数据下载和引用要求后再批准执行。", *manual[:3]]
    if blocking:
        return ["先修复 benchmark manifest/adapter 阻断项，再请求执行批准。", *blocking[:4]]
    if mode == "simulated":
        return ["当前只适合 smoke；要生成可发表 benchmark 证据，请切换 benchmark 模式并配置 manifest。", *manual[:3]]
    return ["按 readiness 待办补齐 benchmark 来源、metric/baseline 对齐和 artifact contract。", *manual[:3]]


def _check_weight(status: str) -> float:
    return {"pass": 1.0, "warn": 0.45, "block": 0.0}.get(status, 0.0)


def _terms(values: list[str]) -> set[str]:
    terms: set[str] = set()
    aliases = {"rrt*": "rrt", "rrt_star": "rrt", "runtime": "planning_time", "time": "planning_time"}
    for value in values:
        for match in re.findall(r"[A-Za-z][A-Za-z0-9_*.-]{1,}|[\u4e00-\u9fff]{2,}", str(value).lower()):
            normalized = match.replace("-", "_").replace(".", "_")
            terms.add(aliases.get(normalized, normalized))
    return terms


def _metric_schema(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, raw in value.items():
        if not isinstance(raw, dict):
            continue
        metric = str(key).strip()
        if not metric:
            continue
        result[metric] = {
            "direction": str(raw.get("direction") or "").strip(),
            "unit": str(raw.get("unit") or "").strip(),
            "description": str(raw.get("description") or "").strip(),
        }
    return result


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
