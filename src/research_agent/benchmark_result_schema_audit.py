from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text, cell as _cell
from .benchmark_adapter import formal_benchmark_metric_contract_issues, formal_benchmark_provenance_issues
from .models import ExperimentPlan, ExperimentResult, StatisticsReport


BENCHMARK_RESULT_SCHEMA_AUDIT_JSON = "04-benchmark-result-schema-audit.json"
BENCHMARK_RESULT_SCHEMA_AUDIT_MD = "04-benchmark-result-schema-audit.md"


def write_benchmark_result_schema_audit_artifacts(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    runbook: dict[str, Any],
    run_dir: Path,
    *,
    benchmark_plan: dict[str, Any] | None = None,
    adapter_report: dict[str, Any] | None = None,
    result_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_benchmark_result_schema_audit_report(
        plan,
        results,
        statistics,
        runbook,
        benchmark_plan=benchmark_plan,
        adapter_report=adapter_report,
        result_validation=result_validation,
    )
    write_json(run_dir / BENCHMARK_RESULT_SCHEMA_AUDIT_JSON, report)
    write_text(run_dir / BENCHMARK_RESULT_SCHEMA_AUDIT_MD, render_benchmark_result_schema_audit_markdown(report))
    return report


def build_benchmark_result_schema_audit_report(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    runbook: dict[str, Any],
    *,
    benchmark_plan: dict[str, Any] | None = None,
    adapter_report: dict[str, Any] | None = None,
    result_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runbook = runbook if isinstance(runbook, dict) else {}
    benchmark_plan = benchmark_plan if isinstance(benchmark_plan, dict) else {}
    adapter_report = adapter_report if isinstance(adapter_report, dict) else {}
    result_validation = result_validation if isinstance(result_validation, dict) else {}
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    execution_mode = str(execution.get("mode") or "")
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []
    manual: list[str] = []
    warnings: list[str] = []
    inventory = _schema_inventory(plan, results, statistics, runbook, benchmark_plan, adapter_report)

    _check_runbook_schema(plan, results, runbook, checks, blocking, manual)
    _check_role_matrix(plan, results, execution_mode, adapter_report, checks, blocking, manual)
    _check_metric_schema(plan, results, checks, blocking, manual)
    _check_repeat_schema(results, checks, manual)
    _check_statistics_coverage(plan, results, statistics, execution_mode, adapter_report, checks, blocking, manual)
    _check_benchmark_metric_alignment(plan, results, benchmark_plan, checks, manual)
    _check_artifact_trace(runbook, checks, blocking, manual, warnings)
    _check_adapter_artifact_contract(runbook, adapter_report, execution_mode, checks, blocking, manual)
    _check_adapter_provenance_contract(adapter_report, execution_mode, checks, blocking, manual)
    _check_benchmark_execution_contract(adapter_report, execution_mode, runbook, checks, blocking, manual)
    _check_adapter_role_command_contract(adapter_report, execution_mode, checks, blocking, manual)
    _check_result_validation_status(result_validation, checks, blocking, manual)

    blocking = _unique(blocking)
    manual = _unique(manual)
    warnings = _unique(warnings)
    status = "block" if blocking else "review_required" if manual or warnings else "pass"
    return {
        "schema_version": 1,
        "idea_title": plan.idea_title,
        "status": status,
        "execution_mode": execution_mode or "unknown",
        "planned_metrics": [str(item) for item in plan.metrics],
        "actual_metrics": inventory["actual_metrics"],
        "benchmark_expected_metrics": inventory["benchmark_expected_metrics"],
        "adapter_expected_artifacts": inventory["adapter_expected_artifacts"],
        "adapter_expected_metrics": inventory["adapter_expected_metrics"],
        "adapter_execution_contract": inventory["adapter_execution_contract"],
        "adapter_provenance": inventory["adapter_provenance"],
        "role_summary": inventory["role_summary"],
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "warnings": warnings,
        "checks": checks,
        "required_actions": _required_actions(status, blocking, manual, warnings),
    }


def render_benchmark_result_schema_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Benchmark Result Schema Audit：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 执行模式：{report.get('execution_mode') or '-'}",
        f"- 计划指标：{', '.join(str(item) for item in _as_list(report.get('planned_metrics'))) or '-'}",
        f"- 实际指标：{', '.join(str(item) for item in _as_list(report.get('actual_metrics'))) or '-'}",
        f"- Benchmark 期望指标：{', '.join(str(item) for item in _as_list(report.get('benchmark_expected_metrics'))) or '-'}",
        f"- Adapter 期望产物：{', '.join(str(item) for item in _as_list(report.get('adapter_expected_artifacts'))) or '-'}",
        f"- Adapter 期望指标：{', '.join(str(item) for item in _as_list(report.get('adapter_expected_metrics'))) or '-'}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("warnings", "警告"), ("required_actions", "必要动作")]:
        values = _as_list(report.get(key))
        if values:
            lines.extend([f"## {title}"])
            prefix = "- [ ] " if key in {"manual_tasks", "required_actions"} else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(["## Role Matrix", "| 角色 | 命令数 | 结果数 | 重复 | 指标 |", "| --- | ---: | ---: | --- | --- |"])
    role_summary = report.get("role_summary") if isinstance(report.get("role_summary"), dict) else {}
    for role in ["candidate", "baseline", "ablation", "other"]:
        item = role_summary.get(role) if isinstance(role_summary.get(role), dict) else {}
        lines.append(
            "| "
            + " | ".join(
                [
                    role,
                    str(item.get("commands", 0)),
                    str(item.get("results", 0)),
                    _cell(", ".join(str(value) for value in _as_list(item.get("repeats"))) or "-"),
                    _cell(", ".join(str(value) for value in _as_list(item.get("metrics"))) or "-"),
                ]
            )
            + " |"
        )
    provenance = report.get("adapter_provenance") if isinstance(report.get("adapter_provenance"), dict) else {}
    if provenance:
        lines.extend(["", "## Adapter Provenance", "| Adapter | dataset/benchmark | license | baseline | baseline_version | citation |", "| --- | --- | --- | --- | --- | --- |"])
        for name, item in provenance.items():
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(name)),
                        _cell(str(item.get("dataset_url") or item.get("benchmark_url") or "-")),
                        _cell(str(item.get("license") or "-")),
                        _cell(str(item.get("baseline") or "-")),
                        _cell(str(item.get("baseline_version") or "-")),
                        _cell(str(item.get("citation") or "-")),
                    ]
                )
                + " |"
            )
    execution_contract = report.get("adapter_execution_contract") if isinstance(report.get("adapter_execution_contract"), dict) else {}
    if execution_contract:
        lines.extend(["", "## Benchmark Execution Contract", "| Adapter | expected_metrics | grader | submission_path | seed_policy | min_repeats |", "| --- | --- | --- | --- | --- | ---: |"])
        for name, item in execution_contract.items():
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(name)),
                        _cell(", ".join(str(value) for value in _as_list(item.get("expected_metrics"))) or "-"),
                        _cell(str(item.get("grader") or "-")),
                        _cell(str(item.get("submission_path") or "-")),
                        _cell(str(item.get("seed_policy") or "-")),
                        str(item.get("min_repeats") or 0),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## 检查项", "| 检查 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
    for item in _as_list(report.get("checks")):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("name") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("evidence") or "")),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- `block` 表示结果 schema、角色、统计比较或 benchmark artifact contract 断链，不能支撑后续实验结论。",
            "- `review_required` 表示 schema 可追溯但仍需人工核对 benchmark 指标对齐、repeat 一致性或 artifact trace。",
            "- `pass` 表示 04-results、04-statistics、04-experiment-runbook 和 benchmark adapter contract 已形成可审计闭环。",
        ]
    )
    return "\n".join(lines)


def _check_runbook_schema(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    runbook: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    commands = _dicts(runbook.get("commands"))
    runs = _dicts(runbook.get("runs"))
    if not runbook:
        detail = "缺少 04-experiment-runbook，无法把结果追溯到命令和产物。"
        checks.append(_check("runbook_schema", "block", detail, "重新生成实验 runbook。"))
        blocking.append(detail)
        return
    if not runs:
        detail = "runbook 没有 runs 记录。"
        checks.append(_check("runbook_schema", "block", detail, "重新执行或重建 04-experiment-runbook。"))
        blocking.append(detail)
        return
    missing_commands = sorted({command.name for command in plan.commands} - {str(item.get("name") or "") for item in commands})
    if missing_commands:
        detail = "runbook commands 缺少实验计划命令：" + ", ".join(missing_commands[:6])
        checks.append(_check("runbook_schema", "block", detail, "用当前 03-experiment-plan 重新生成 runbook。"))
        blocking.append(detail)
        return
    if len(runs) != len(results):
        detail = f"runbook runs 与 04-results 数量不一致：runbook={len(runs)} results={len(results)}。"
        checks.append(_check("runbook_schema", "review_required", detail, "人工核对 runbook 是否过期。"))
        manual.append(detail)
        return
    checks.append(_check("runbook_schema", "pass", f"commands={len(commands)} runs={len(runs)} results={len(results)}", "无需处理。"))


def _check_role_matrix(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    execution_mode: str,
    adapter_report: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    role_by_name = _role_lookup(plan)
    command_roles = _role_counts(_command_role(command) for command in plan.commands)
    result_roles = _role_counts(_result_role(result, role_by_name) for result in _successful(results))
    missing: list[str] = []
    for role in ["candidate", "baseline", "ablation"]:
        if command_roles.get(role, 0) == 0:
            missing.append(f"{role} command")
        if result_roles.get(role, 0) == 0:
            missing.append(f"{role} result")
    if missing:
        detail = "实验角色矩阵不完整：" + ", ".join(missing)
        if _benchmark_adapter_contract_ready(execution_mode, adapter_report):
            detail += "；当前 benchmark adapter 未声明完整比较角色，结果只能作为 adapter 执行闭环或非比较 benchmark 证据。"
            checks.append(_check("role_matrix", "review_required", detail, "正式比较结论需补齐 candidate/baseline/ablation adapter 或在论文中降级。"))
            manual.append(detail)
        else:
            checks.append(_check("role_matrix", "block", detail, "补齐 candidate/baseline/ablation 命令和结果。"))
            blocking.append(detail)
        return
    checks.append(
        _check(
            "role_matrix",
            "pass",
            f"candidate={result_roles.get('candidate', 0)} baseline={result_roles.get('baseline', 0)} ablation={result_roles.get('ablation', 0)}",
            "无需处理。",
        )
    )


def _check_metric_schema(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    expected = {str(metric) for metric in plan.metrics if str(metric).strip()}
    successful = _successful(results)
    if not expected:
        detail = "03-experiment-plan 没有声明 metrics。"
        checks.append(_check("metric_schema", "review_required", detail, "补齐计划指标后重跑实验。"))
        manual.append(detail)
        return
    missing: list[str] = []
    for result in successful:
        keys = {str(key) for key in result.metrics}
        if not keys:
            missing.append(f"{result.name}#{result.repeat_index}: no metrics")
            continue
        missing_metrics = sorted(expected - keys)
        if missing_metrics:
            missing.append(f"{result.name}#{result.repeat_index}: missing {', '.join(missing_metrics[:4])}")
    if missing:
        detail = "实际结果缺少计划指标：" + "；".join(missing[:8])
        checks.append(_check("metric_schema", "block", detail, "修复 metrics JSON 或实验计划 schema 后重跑。"))
        blocking.append(detail)
        return
    checks.append(_check("metric_schema", "pass", f"{len(expected)} planned metrics present in {len(successful)} successful results", "无需处理。"))


def _check_repeat_schema(results: list[ExperimentResult], checks: list[dict[str, Any]], manual: list[str]) -> None:
    inconsistent: list[str] = []
    by_name: dict[str, list[set[str]]] = {}
    for result in _successful(results):
        by_name.setdefault(result.name, []).append({str(key) for key in result.metrics})
    for name, metric_sets in by_name.items():
        if len({tuple(sorted(values)) for values in metric_sets}) > 1:
            inconsistent.append(name)
    if inconsistent:
        detail = "同一命令不同 repeat 的 metric keys 不一致：" + ", ".join(inconsistent[:8])
        checks.append(_check("repeat_metric_schema", "review_required", detail, "确认失败 repeat、额外指标或 metrics converter 是否一致。"))
        manual.append(detail)
        return
    checks.append(_check("repeat_metric_schema", "pass", f"{len(by_name)} command schemas stable", "无需处理。"))


def _check_statistics_coverage(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    execution_mode: str,
    adapter_report: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    role_by_name = _role_lookup(plan)
    candidate = [result for result in _successful(results) if _result_role(result, role_by_name) == "candidate"]
    baseline = [result for result in _successful(results) if _result_role(result, role_by_name) == "baseline"]
    shared = sorted(_metric_union(candidate) & _metric_union(baseline))
    comparisons = {str(item.metric) for item in statistics.comparisons}
    if not shared:
        detail = "candidate 与 baseline 没有共同 metric schema。"
        if _benchmark_adapter_contract_ready(execution_mode, adapter_report):
            detail += " 当前 benchmark adapter 未暴露比较角色，统计比较需由多 adapter 或显式角色映射补齐。"
            checks.append(_check("statistics_metric_coverage", "review_required", detail, "补齐 candidate/baseline adapter 后再写比较性结论。"))
            manual.append(detail)
        else:
            checks.append(_check("statistics_metric_coverage", "block", detail, "统一 candidate/baseline metrics 后重跑统计。"))
            blocking.append(detail)
        return
    required = _statistics_required_metrics(plan, shared)
    missing = sorted(set(required) - comparisons)
    if comparisons and not missing:
        descriptive = sorted(set(shared) - set(required))
        detail = f"statistics cover {len(comparisons)} planned/shared comparison metrics"
        if descriptive:
            detail += f"; {len(descriptive)} descriptive metrics kept out of inferential comparison"
        checks.append(_check("statistics_metric_coverage", "pass", detail, "无需处理。"))
        return
    if not comparisons:
        detail = "04-statistics 没有覆盖 candidate/baseline 共同指标。"
        checks.append(_check("statistics_metric_coverage", "block", detail, "重新生成统计比较。"))
        blocking.append(detail)
        return
    detail = "部分共同指标未进入统计比较：" + ", ".join(missing[:8])
    checks.append(_check("statistics_metric_coverage", "review_required", detail, "人工确认这些指标是否应作为补充统计。"))
    manual.append(detail)


def _statistics_required_metrics(plan: ExperimentPlan, shared: list[str]) -> list[str]:
    planned = {str(metric) for metric in plan.metrics if str(metric).strip()}
    exact = sorted(set(shared) & planned)
    if exact:
        return exact
    return sorted(metric for metric in shared if _default_statistical_metric(metric))


def _default_statistical_metric(metric: str) -> bool:
    lowered = metric.lower()
    if lowered.startswith("cm_"):
        return False
    if "_class_count_" in lowered:
        return False
    if lowered in {"train_cases", "test_cases"}:
        return False
    return True


def _check_benchmark_metric_alignment(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    benchmark_plan: dict[str, Any],
    checks: list[dict[str, Any]],
    manual: list[str],
) -> None:
    expected = _selected_benchmark_metrics(benchmark_plan)
    if not expected:
        checks.append(_check("benchmark_metric_alignment", "pass", "no selected benchmark expected_metrics to enforce", "无需处理。"))
        return
    plan_terms = _terms(plan.metrics)
    actual_terms = _terms(sorted({str(key) for result in _successful(results) for key in result.metrics}))
    benchmark_terms = _terms(expected)
    overlap = sorted((plan_terms | actual_terms) & benchmark_terms)
    if overlap:
        checks.append(_check("benchmark_metric_alignment", "pass", f"overlap={', '.join(overlap[:8])}", "无需处理。"))
        return
    detail = "计划/实际 metrics 与选中 benchmark expected_metrics 没有可解释重合。"
    checks.append(_check("benchmark_metric_alignment", "review_required", detail, "人工确认指标映射，或修改 metrics converter 输出标准字段。"))
    manual.append(detail)


def _check_artifact_trace(
    runbook: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
    warnings: list[str],
) -> None:
    runs = _dicts(runbook.get("runs"))
    produced = [artifact for run in runs for artifact in _dicts(run.get("produced_artifacts"))]
    if not produced:
        detail = "runbook 没有 produced_artifacts 记录。"
        checks.append(_check("artifact_hash_trace", "block", detail, "重新生成 runbook artifact trace。"))
        blocking.append(detail)
        return
    missing_hash = [str(item.get("path") or "") for item in produced if not str(item.get("path") or "").strip() or not str(item.get("sha256") or "").strip()]
    if missing_hash:
        detail = "部分产物缺少 path 或 sha256：" + ", ".join(missing_hash[:6])
        checks.append(_check("artifact_hash_trace", "review_required", detail, "补齐产物 hash 记录。"))
        manual.append(detail)
        warnings.append(detail)
        return
    checks.append(_check("artifact_hash_trace", "pass", f"{len(produced)} produced artifacts with hashes", "无需处理。"))


def _check_adapter_artifact_contract(
    runbook: dict[str, Any],
    adapter_report: dict[str, Any],
    execution_mode: str,
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    if execution_mode != "benchmark":
        checks.append(_check("adapter_artifact_contract", "pass", f"mode={execution_mode or 'unknown'}; benchmark adapter contract not required", "无需处理。"))
        return
    if str(adapter_report.get("status") or "") != "ready":
        detail = f"benchmark 模式 adapter 不是 ready：{adapter_report.get('status') or 'missing'}。"
        checks.append(_check("adapter_artifact_contract", "block", detail, "先修复 03-benchmark-adapters。"))
        blocking.append(detail)
        return
    adapter_contract = _adapter_contract(adapter_report)
    if not adapter_contract:
        detail = "03-benchmark-adapters 缺少可审计的 adapter command/metrics_path/expected_artifacts。"
        checks.append(_check("adapter_artifact_contract", "block", detail, "补齐 benchmark manifest schema。"))
        blocking.append(detail)
        return
    run_commands = {str(item.get("name") or ""): set(_normalize_artifact_path(value) for value in _as_list(item.get("expected_artifacts"))) for item in _dicts(runbook.get("commands"))}
    run_records = _dicts(runbook.get("runs"))
    missing: list[str] = []
    for name, contract in adapter_contract.items():
        expected = set(contract["expected_artifacts"])
        metrics_path = str(contract["metrics_path"] or "")
        if metrics_path and metrics_path not in expected:
            missing.append(f"{name}: metrics_path {metrics_path} not in expected_artifacts")
        if not expected:
            missing.append(f"{name}: no expected_artifacts")
        if expected - run_commands.get(name, set()):
            missing.append(f"{name}: runbook command missing {', '.join(sorted(expected - run_commands.get(name, set()))[:4])}")
        for run in [item for item in run_records if str(item.get("name") or "") == name]:
            produced = _produced_artifact_contract_paths(run)
            missing_paths = sorted(expected - produced)
            if missing_paths:
                missing.append(f"{name}#{run.get('repeat_index', '-')}: missing produced {', '.join(missing_paths[:4])}")
    if missing:
        detail = "benchmark adapter artifact contract 未闭环：" + "；".join(missing[:8])
        checks.append(_check("adapter_artifact_contract", "block", detail, "修复 adapter 输出路径或 runbook artifact trace 后重跑。"))
        blocking.append(detail)
        return
    commands_without_runs = sorted(set(adapter_contract) - {str(item.get("name") or "") for item in run_records})
    if commands_without_runs:
        detail = "adapter command 没有对应 run 记录：" + ", ".join(commands_without_runs[:6])
        checks.append(_check("adapter_artifact_contract", "review_required", detail, "确认 benchmark adapter 是否全部执行。"))
        manual.append(detail)
        return
    checks.append(_check("adapter_artifact_contract", "pass", f"{len(adapter_contract)} adapter commands traced", "无需处理。"))


def _check_adapter_provenance_contract(
    adapter_report: dict[str, Any],
    execution_mode: str,
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    if execution_mode != "benchmark":
        checks.append(_check("adapter_provenance_contract", "pass", f"mode={execution_mode or 'unknown'}; benchmark provenance not required", "无需处理。"))
        return
    provenance = _adapter_provenance(adapter_report)
    if not provenance:
        detail = "benchmark 模式缺少 adapter provenance，无法把结果追溯到数据来源、许可证、baseline 版本和引用。"
        checks.append(_check("adapter_provenance_contract", "block", detail, "补齐 03-benchmark-adapters provenance 后重跑。"))
        blocking.append(detail)
        return
    missing: list[str] = []
    for name, item in provenance.items():
        provenance_issues = item.get("provenance_issues")
        if isinstance(provenance_issues, list) and provenance_issues:
            missing.extend(str(issue) for issue in provenance_issues if str(issue).strip())
            continue
        missing.extend(
            formal_benchmark_provenance_issues(
                name=name,
                benchmark_kind=str(item.get("benchmark_kind") or ""),
                benchmark_url=str(item.get("benchmark_url") or ""),
                dataset_url=str(item.get("dataset_url") or ""),
                dataset_version=str(item.get("dataset_version") or ""),
                split_name=str(item.get("split_name") or ""),
                split_sha256=str(item.get("split_sha256") or ""),
                split_sha256_actual=str(item.get("split_sha256_actual") or ""),
                license_value=str(item.get("license") or ""),
                baseline_version=str(item.get("baseline_version") or ""),
                citation=str(item.get("citation") or ""),
            )
        )
    if missing:
        detail = "benchmark result provenance 不完整：" + "；".join(missing[:8])
        checks.append(_check("adapter_provenance_contract", "block", detail, "补齐 manifest provenance；结果不能作为正式 benchmark 证据。"))
        blocking.append(detail)
        return
    if any(not str(item.get("baseline") or "").strip() for item in provenance.values()):
        detail = "部分 adapter 未声明 baseline 名称，需人工确认 baseline 与论文/统计一致。"
        checks.append(_check("adapter_provenance_contract", "review_required", detail, "在 manifest 或论文局限性中说明 baseline 映射。"))
        manual.append(detail)
        return
    checks.append(_check("adapter_provenance_contract", "pass", f"{len(provenance)} adapter provenance records traced", "无需处理。"))


def _check_benchmark_execution_contract(
    adapter_report: dict[str, Any],
    execution_mode: str,
    runbook: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    if execution_mode != "benchmark":
        checks.append(_check("benchmark_execution_contract", "pass", f"mode={execution_mode or 'unknown'}; benchmark execution contract not required", "无需处理。"))
        return
    contract = _adapter_execution_contract(adapter_report)
    if not contract:
        detail = "benchmark 模式缺少 expected_metrics、grader/submission、seed policy 和 repeat policy 契约。"
        checks.append(_check("benchmark_execution_contract", "block", detail, "补齐 benchmark manifest 的 execution contract。"))
        blocking.append(detail)
        return
    missing: list[str] = []
    configured_repeats = _safe_int(_dict(runbook.get("execution")).get("repeats"))
    for name, item in contract.items():
        expected_metrics = [str(value) for value in _as_list(item.get("expected_metrics")) if str(value).strip()]
        missing.extend(
            formal_benchmark_metric_contract_issues(
                name=name,
                expected_metrics=expected_metrics,
                metric_schema=_metric_schema(item.get("metric_schema")),
                grader_version=str(item.get("grader_version") or ""),
                grader_sha256=str(item.get("grader_sha256") or ""),
                grader_sha256_actual=str(item.get("grader_sha256_actual") or ""),
            )
        )
        if not str(item.get("grader") or "").strip() and not str(item.get("submission_path") or "").strip():
            missing.append(f"{name}: grader_or_submission_path")
        if not str(item.get("seed_policy") or "").strip():
            missing.append(f"{name}: seed_policy")
        min_repeats = _safe_int(item.get("min_repeats"))
        if min_repeats <= 0:
            missing.append(f"{name}: min_repeats")
        elif configured_repeats and configured_repeats < min_repeats:
            missing.append(f"{name}: repeats {configured_repeats} < min_repeats {min_repeats}")
    if missing:
        detail = "benchmark execution contract 不完整：" + "；".join(missing[:8])
        checks.append(_check("benchmark_execution_contract", "block", detail, "补齐 grader/submission、expected_metrics、seed_policy 或提高 repeats 后重跑。"))
        blocking.append(detail)
        return
    checks.append(_check("benchmark_execution_contract", "pass", f"{len(contract)} adapter execution contracts traced", "无需处理。"))


def _check_adapter_role_command_contract(
    adapter_report: dict[str, Any],
    execution_mode: str,
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    if execution_mode != "benchmark":
        checks.append(_check("adapter_role_command_contract", "pass", f"mode={execution_mode or 'unknown'}; benchmark role command contract not required", "无需处理。"))
        return
    role_records = _adapter_role_command_contract(adapter_report)
    if not role_records:
        detail = "benchmark 模式缺少 candidate/baseline/ablation role command signature。"
        if str(adapter_report.get("paper_grade_status") or "") == "ready":
            checks.append(_check("adapter_role_command_contract", "review_required", detail, "确认旧 adapter 报告或 manifest 是否显式区分 role 命令。"))
            manual.append(detail)
        else:
            checks.append(_check("adapter_role_command_contract", "pass", "no paper-grade role command contract declared", "无需处理。"))
        return
    by_signature: dict[str, list[str]] = {}
    missing: list[str] = []
    for name, item in role_records.items():
        signature = str(item.get("role_command_signature") or "")
        role = str(item.get("role") or "")
        if not signature:
            missing.append(f"{name}: role_command_signature")
            continue
        by_signature.setdefault(signature, []).append(role)
    for roles in by_signature.values():
        unique_roles = sorted(set(roles))
        if len(unique_roles) > 1:
            missing.append("重复 role command：" + ", ".join(unique_roles))
    if missing:
        detail = "benchmark role command contract 不完整：" + "；".join(missing[:6])
        checks.append(_check("adapter_role_command_contract", "block", detail, "让 candidate/baseline/ablation 命令显式包含不同 method/variant/config 参数后重跑。"))
        blocking.append(detail)
        return
    checks.append(_check("adapter_role_command_contract", "pass", f"{len(role_records)} role command signatures traced", "无需处理。"))


def _check_result_validation_status(
    result_validation: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
) -> None:
    status = str(result_validation.get("status") or "")
    if not status:
        checks.append(_check("result_validation_link", "review_required", "未读取到 04-result-validation 状态。", "确认结果有效性验证已生成。"))
        manual.append("未读取到 04-result-validation 状态。")
    elif status == "block":
        detail = "04-result-validation 仍为 block，schema 审计不能覆盖有效性阻断。"
        checks.append(_check("result_validation_link", "block", detail, "先修复 04-result-validation。"))
        blocking.append(detail)
    elif status == "warn":
        non_schema_warnings = _non_schema_result_validation_warnings(result_validation)
        warning_count = len(_as_list(result_validation.get("warnings")))
        if non_schema_warnings and len(non_schema_warnings) == warning_count:
            detail = "04-result-validation 仅包含非 schema 统计解释警告：" + ", ".join(non_schema_warnings[:4])
            checks.append(_check("result_validation_link", "pass", detail, "在 result validation / benchmark evidence 层保留结论边界。"))
            return
        detail = "04-result-validation 存在 warn。"
        checks.append(_check("result_validation_link", "review_required", detail, "人工核对结果验证警告。"))
        manual.append(detail)
    else:
        checks.append(_check("result_validation_link", "pass", f"04-result-validation={status}", "无需处理。"))


def _schema_inventory(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    runbook: dict[str, Any],
    benchmark_plan: dict[str, Any],
    adapter_report: dict[str, Any],
) -> dict[str, Any]:
    del statistics, runbook
    role_summary: dict[str, dict[str, Any]] = {}
    role_by_name = _role_lookup(plan)
    for role in ["candidate", "baseline", "ablation", "other"]:
        role_commands = [command.name for command in plan.commands if _command_role(command) == role]
        role_results = [result for result in _successful(results) if _result_role(result, role_by_name) == role]
        role_summary[role] = {
            "commands": len(role_commands),
            "results": len(role_results),
            "repeats": sorted({result.repeat_index for result in role_results}),
            "metrics": sorted(_metric_union(role_results)),
        }
    return {
        "actual_metrics": sorted({str(key) for result in _successful(results) for key in result.metrics}),
        "benchmark_expected_metrics": _selected_benchmark_metrics(benchmark_plan),
        "adapter_expected_artifacts": sorted({path for item in _adapter_contract(adapter_report).values() for path in item["expected_artifacts"]}),
        "adapter_expected_metrics": sorted({metric for item in _adapter_execution_contract(adapter_report).values() for metric in _as_list(item.get("expected_metrics"))}),
        "adapter_execution_contract": _adapter_execution_contract(adapter_report),
        "adapter_provenance": _adapter_provenance(adapter_report),
        "role_summary": role_summary,
    }


def _non_schema_result_validation_warnings(result_validation: dict[str, Any]) -> list[str]:
    warnings = [str(item) for item in _as_list(result_validation.get("warnings")) if str(item).strip()]
    if not warnings:
        return []
    allowed_items = {"statistical_comparability"}
    warning_item_names = {
        str(item.get("name") or "")
        for item in _dicts(result_validation.get("items"))
        if str(item.get("status") or "") == "warn"
    }
    if warning_item_names and warning_item_names <= allowed_items:
        return warnings
    return []


def _adapter_contract(adapter_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in _dicts(adapter_report.get("adapters")):
        name = str(item.get("name") or "").strip()
        if not name or str(item.get("status") or "") != "ready":
            continue
        expected = [_normalize_artifact_path(value) for value in _as_list(item.get("expected_artifacts")) if str(value).strip()]
        metrics_path = _normalize_artifact_path(item.get("metrics_path"))
        records[name] = {"expected_artifacts": expected, "metrics_path": metrics_path}
    for item in _dicts(adapter_report.get("commands")):
        name = str(item.get("name") or "").strip()
        if not name or name in records:
            continue
        expected = [_normalize_artifact_path(value) for value in _as_list(item.get("expected_artifacts")) if str(value).strip()]
        records[name] = {"expected_artifacts": expected, "metrics_path": expected[0] if expected else ""}
    return records


def _adapter_provenance(adapter_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in [*_dicts(adapter_report.get("adapters")), *_dicts(adapter_report.get("commands"))]:
        name = str(item.get("name") or "").strip()
        if not name or name in records:
            continue
        if "status" in item and str(item.get("status") or "") != "ready":
            continue
        record = {
            "benchmark_url": str(item.get("benchmark_url") or ""),
            "dataset_url": str(item.get("dataset_url") or ""),
            "dataset_version": str(item.get("dataset_version") or ""),
            "split_name": str(item.get("split_name") or ""),
            "split_path": str(item.get("split_path") or ""),
            "split_sha256": str(item.get("split_sha256") or ""),
            "split_sha256_actual": str(item.get("split_sha256_actual") or ""),
            "license": str(item.get("license") or ""),
            "baseline": str(item.get("baseline") or ""),
            "baseline_version": str(item.get("baseline_version") or ""),
            "citation": str(item.get("citation") or ""),
        }
        if item.get("benchmark_kind"):
            record["benchmark_kind"] = str(item.get("benchmark_kind") or "")
        if item.get("provenance_status"):
            record["provenance_status"] = str(item.get("provenance_status") or "")
        if "provenance_issues" in item:
            record["provenance_issues"] = _as_list(item.get("provenance_issues"))
        records[name] = record
    return records


def _adapter_execution_contract(adapter_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in [*_dicts(adapter_report.get("adapters")), *_dicts(adapter_report.get("commands"))]:
        name = str(item.get("name") or "").strip()
        if not name or name in records:
            continue
        if "status" in item and str(item.get("status") or "") != "ready":
            continue
        records[name] = {
            "expected_metrics": [str(value) for value in _as_list(item.get("expected_metrics")) if str(value).strip()],
            "metric_schema": _metric_schema(item.get("metric_schema")),
            "grader": str(item.get("grader") or ""),
            "grader_path": str(item.get("grader_path") or ""),
            "submission_path": str(item.get("submission_path") or ""),
            "grader_version": str(item.get("grader_version") or ""),
            "grader_sha256": str(item.get("grader_sha256") or ""),
            "grader_sha256_actual": str(item.get("grader_sha256_actual") or ""),
            "seed_policy": str(item.get("seed_policy") or ""),
            "min_repeats": _safe_int(item.get("min_repeats")),
        }
    return records


def _adapter_role_command_contract(adapter_report: dict[str, Any]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for item in [*_dicts(adapter_report.get("adapters")), *_dicts(adapter_report.get("commands"))]:
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        if not name or name in records or role not in {"candidate", "baseline", "ablation"}:
            continue
        if "status" in item and str(item.get("status") or "") != "ready":
            continue
        records[name] = {
            "role": role,
            "role_command_signature": str(item.get("role_command_signature") or ""),
        }
    return records


def _benchmark_adapter_contract_ready(execution_mode: str, adapter_report: dict[str, Any]) -> bool:
    return execution_mode == "benchmark" and str(adapter_report.get("status") or "") == "ready" and bool(_adapter_execution_contract(adapter_report))


def _selected_benchmark_metrics(benchmark_plan: dict[str, Any]) -> list[str]:
    selected = {str(item) for item in _as_list(benchmark_plan.get("selected_names")) if str(item).strip()}
    candidates = _dicts(benchmark_plan.get("candidates"))
    if selected:
        candidates = [item for item in candidates if str(item.get("name") or "") in selected]
    metrics = [str(metric) for item in candidates for metric in _as_list(item.get("expected_metrics")) if str(metric).strip()]
    return _unique(metrics)


def _check(name: str, status: str, evidence: str, action: str) -> dict[str, str]:
    return {"name": name, "status": status, "evidence": evidence, "action": action}


def _required_actions(status: str, blocking: list[str], manual: list[str], warnings: list[str]) -> list[str]:
    if status == "block":
        return ["先修复 benchmark result schema 阻断项，再使用这些结果写实验结论。", *blocking[:4]]
    if status == "review_required":
        return ["人工确认 result schema、benchmark metric 映射和 artifact trace 后再进入强结论。", *(manual or warnings)[:4]]
    return ["可继续使用结果，但仍需人工核对 benchmark 许可证、任务代表性和领域指标解释。"]


def _successful(results: list[ExperimentResult]) -> list[ExperimentResult]:
    return [result for result in results if result.status not in {"failed", "blocked", "timeout"}]


def _metric_union(results: list[ExperimentResult]) -> set[str]:
    return {str(key) for result in results for key in result.metrics}


def _role_lookup(plan: ExperimentPlan) -> dict[str, str]:
    return {command.name: _command_role(command) for command in plan.commands}


def _command_role(command: Any) -> str:
    role = str(getattr(command, "role", "") or "").strip()
    return role if role in {"candidate", "baseline", "ablation", "other"} else _role(str(getattr(command, "name", "")))


def _result_role(result: ExperimentResult, role_by_name: dict[str, str]) -> str:
    return role_by_name.get(result.name) or _role(result.name)


def _role_counts(names: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in names:
        role = str(name)
        if role not in {"candidate", "baseline", "ablation", "other"}:
            role = _role(role)
        counts[role] = counts.get(role, 0) + 1
    return counts


def _role(name: str) -> str:
    lowered = name.lower()
    if "ablation" in lowered or "ablated" in lowered or "without" in lowered:
        return "ablation"
    if "candidate" in lowered or "artifact" in lowered or "proposed" in lowered:
        return "candidate"
    if "baseline" in lowered or "control" in lowered:
        return "baseline"
    return "other"


def _terms(values: list[str]) -> set[str]:
    aliases = {"runtime": "time", "planning_time": "time", "planning_success_rate": "success_rate", "success": "success_rate"}
    terms: set[str] = set()
    for value in values:
        raw = str(value).lower().replace("-", "_").replace(".", "_")
        for match in re.findall(r"[a-z][a-z0-9_*_]{1,}|[\u4e00-\u9fff]{2,}", raw):
            terms.add(aliases.get(match, match))
            parts = [part for part in match.split("_") if part]
            terms.update(aliases.get(part, part) for part in parts)
    return terms


def _normalize_artifact_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("experiments/"):
        text = text[len("experiments/") :]
    return text


def _produced_artifact_contract_paths(run: dict[str, Any]) -> set[str]:
    paths = {
        _normalize_artifact_path(item.get("path"))
        for item in _dicts(run.get("produced_artifacts"))
        if str(item.get("path") or "").strip()
    }
    name = str(run.get("name") or "").strip()
    repeat_index = run.get("repeat_index")
    if not name or not isinstance(repeat_index, int) or isinstance(repeat_index, bool) or repeat_index < 0:
        return paths
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-.") or "command"
    snapshot_prefix = f"repeat-artifacts/{safe_name}/repeat-{repeat_index + 1:03d}/"
    for path in list(paths):
        if path.startswith(snapshot_prefix):
            logical_path = path[len(snapshot_prefix) :]
            if logical_path:
                paths.add(logical_path)
    return paths


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


