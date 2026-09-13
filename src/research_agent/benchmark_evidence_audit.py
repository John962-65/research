from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text, cell as _cell
from .config import PaperGradeConfig
from .models import ExperimentPlan, ExperimentResult, MetricComparison, StatisticsReport


BENCHMARK_EVIDENCE_AUDIT_JSON = "04-benchmark-evidence-audit.json"
BENCHMARK_EVIDENCE_AUDIT_MD = "04-benchmark-evidence-audit.md"


def write_benchmark_evidence_audit_artifacts(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    runbook: dict[str, Any],
    run_dir: Path,
    *,
    execution_mode: str,
    benchmark_plan: dict[str, Any] | None = None,
    adapter_report: dict[str, Any] | None = None,
    paper_grade: PaperGradeConfig | None = None,
) -> dict[str, Any]:
    report = build_benchmark_evidence_audit_report(
        plan,
        results,
        statistics,
        result_validation,
        runbook,
        execution_mode=execution_mode,
        benchmark_plan=benchmark_plan,
        adapter_report=adapter_report,
        paper_grade=paper_grade,
    )
    write_json(run_dir / BENCHMARK_EVIDENCE_AUDIT_JSON, report)
    write_text(run_dir / BENCHMARK_EVIDENCE_AUDIT_MD, render_benchmark_evidence_audit_markdown(report))
    return report


def build_benchmark_evidence_audit_report(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    runbook: dict[str, Any],
    *,
    execution_mode: str,
    benchmark_plan: dict[str, Any] | None = None,
    adapter_report: dict[str, Any] | None = None,
    paper_grade: PaperGradeConfig | None = None,
) -> dict[str, Any]:
    benchmark_plan = benchmark_plan if isinstance(benchmark_plan, dict) else {}
    adapter_report = adapter_report if isinstance(adapter_report, dict) else {}
    runbook = runbook if isinstance(runbook, dict) else {}
    paper_grade_config = paper_grade or PaperGradeConfig()
    min_execution_repeats = max(1, int(paper_grade_config.min_execution_repeats or 0))
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []
    manual: list[str] = []
    warnings: list[str] = []
    _check_execution_mode(execution_mode, adapter_report, checks, blocking, manual, warnings)
    _check_adapter_paper_grade(execution_mode, adapter_report, checks, manual, warnings)
    _check_benchmark_plan(benchmark_plan, checks, manual, warnings)
    _check_result_validation(result_validation, checks, blocking, warnings)
    _check_comparisons(statistics, checks, manual, warnings, min_execution_repeats)
    _check_runbook(runbook, results, checks, blocking, manual, warnings)
    _check_artifact_trace(plan, runbook, checks, manual, warnings)
    evidence_grade = _evidence_grade(execution_mode, adapter_report, result_validation, checks, blocking)
    statistical_outcome = _statistical_outcome(statistics)
    claim_boundary_warnings = _claim_boundary_warnings(result_validation, statistics)
    claim_boundary_severity = _claim_boundary_severity(evidence_grade, blocking, statistical_outcome, claim_boundary_warnings)
    publishable_negative_or_neutral = _publishable_negative_or_neutral_result(
        evidence_grade,
        result_validation,
        statistical_outcome,
        blocking,
        manual,
    )
    status = _status(evidence_grade, blocking, manual, warnings)
    return {
        "schema_version": 2,
        "idea_title": plan.idea_title,
        "status": status,
        "evidence_grade": evidence_grade,
        "statistical_outcome": statistical_outcome,
        "claim_boundary_severity": claim_boundary_severity,
        "claim_boundary_warnings": claim_boundary_warnings,
        "publishable_negative_or_neutral_result": publishable_negative_or_neutral,
        "execution_mode": execution_mode,
        "benchmark_plan_selected": _as_list(benchmark_plan.get("selected_names")),
        "adapter_status": str(adapter_report.get("status") or ""),
        "adapter_paper_grade_status": str(adapter_report.get("paper_grade_status") or ""),
        "adapter_paper_grade_issues": _as_list(adapter_report.get("paper_grade_issues")),
        "adapter_paper_grade_repair_suggestions": _as_dict_list(adapter_report.get("paper_grade_repair_suggestions")),
        "results": len(results),
        "comparisons": len(statistics.comparisons),
        "repeats": statistics.repeats,
        "min_execution_repeats": min_execution_repeats,
        "blocking_issues": blocking,
        "manual_tasks": _dedupe(manual),
        "warnings": _dedupe(warnings),
        "checks": checks,
        "claim_policy": _claim_policy(evidence_grade, status, statistical_outcome),
        "required_actions": _required_actions(status, evidence_grade, blocking, manual, warnings, publishable_negative_or_neutral),
    }


def render_benchmark_evidence_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Benchmark 证据审计：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 证据等级：{report.get('evidence_grade') or '-'}",
        f"- 执行模式：{report.get('execution_mode') or '-'}",
        f"- Adapter 状态：{report.get('adapter_status') or '-'}",
        f"- Adapter paper-grade：{report.get('adapter_paper_grade_status') or '-'}",
        f"- 结果/比较/重复：{report.get('results', 0)}/{report.get('comparisons', 0)}/{report.get('repeats', 0)}",
        f"- 统计结果：{report.get('statistical_outcome') or '-'}",
        f"- Claim 边界严重性：{report.get('claim_boundary_severity') or '-'}",
        f"- 可发表负/中性结果：{'是' if report.get('publishable_negative_or_neutral_result') else '否'}",
        f"- Claim 策略：{report.get('claim_policy') or '-'}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("warnings", "警告"), ("manual_tasks", "人工待办"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            prefix = "- [ ] " if key in {"manual_tasks", "required_actions"} else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(["## 检查项", "| 检查 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
    for item in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if isinstance(item, dict):
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
            "- `real_benchmark` 可以支撑保守正式实验结论。",
            "- `local_experiment` 需要人工说明 benchmark 来源和任务代表性。",
            "- `smoke_only` 只能写成流程验证或初步趋势，不能写成正式科学主结论。",
            "- `blocked` 需要先修复 adapter、runbook、结果验证或 artifact trace。",
        ]
    )
    return "\n".join(lines)


def _check_execution_mode(
    execution_mode: str,
    adapter_report: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
    warnings: list[str],
) -> None:
    adapter_status = str(adapter_report.get("status") or "")
    if execution_mode == "benchmark":
        if adapter_status == "ready":
            checks.append(_check("execution_mode", "pass", "benchmark mode with ready adapter", "无需处理。"))
        else:
            detail = f"benchmark 模式缺少 ready adapter，adapter_status={adapter_status or 'missing'}。"
            checks.append(_check("execution_mode", "block", detail, "修复 03-benchmark-adapters.md 或 benchmark_manifest_paths。"))
            blocking.append(detail)
        return
    if execution_mode == "local":
        detail = "local 模式有本地真实执行潜力，但未通过 benchmark manifest 绑定公开任务。"
        checks.append(_check("execution_mode", "review_required", detail, "人工确认任务来源、split、baseline 和许可。"))
        manual.append("为 local 实验补 benchmark manifest 或在论文中明确说明任务代表性限制。")
        return
    detail = "simulated 模式只能作为 smoke run。"
    checks.append(_check("execution_mode", "smoke_only", detail, "升级到 local 或 benchmark manifest 后再写正式结论。"))
    warnings.append(detail)


def _check_benchmark_plan(
    benchmark_plan: dict[str, Any],
    checks: list[dict[str, Any]],
    manual: list[str],
    warnings: list[str],
) -> None:
    selected = _as_list(benchmark_plan.get("selected_names"))
    actions = _as_list(benchmark_plan.get("required_actions"))
    if selected:
        checks.append(_check("benchmark_plan", "pass", f"selected={', '.join(str(item) for item in selected[:3])}", "按计划接入至少一个真实 benchmark。"))
    else:
        detail = "03-benchmark-plan 未选择任何候选 benchmark。"
        checks.append(_check("benchmark_plan", "review_required", detail, "补充 benchmark plan 或人工选择候选。"))
        manual.append(detail)
    if actions:
        warnings.append(f"benchmark plan 仍有 {len(actions)} 条接入动作未落实。")


def _check_adapter_paper_grade(
    execution_mode: str,
    adapter_report: dict[str, Any],
    checks: list[dict[str, Any]],
    manual: list[str],
    warnings: list[str],
) -> None:
    if execution_mode != "benchmark" or str(adapter_report.get("status") or "") != "ready":
        return
    paper_grade_status = str(adapter_report.get("paper_grade_status") or "")
    issues = _as_list(adapter_report.get("paper_grade_issues"))
    repair_suggestions = _as_dict_list(adapter_report.get("paper_grade_repair_suggestions"))
    if paper_grade_status == "ready":
        checks.append(_check("adapter_paper_grade", "pass", "candidate/baseline/ablation manifests, shared metrics, and repeat policy are ready", "无需处理。"))
        return
    detail = "benchmark adapter 尚未达到 paper-grade：" + ("；".join(str(item) for item in issues[:4]) if issues else "缺少 paper_grade_status。")
    action = "补齐 candidate/baseline/ablation manifest、共同指标和 repeats/min_repeats 后重跑。"
    if repair_suggestions:
        action = f"按 {len(repair_suggestions)} 条 paper-grade repair suggestions 修复 manifest/repeats 后重跑。"
    checks.append(_check("adapter_paper_grade", "review_required", detail, action))
    manual.append(detail)
    warnings.append(detail)


def _check_result_validation(
    result_validation: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    status = str(result_validation.get("status") or "")
    if status == "pass":
        checks.append(_check("result_validation", "pass", "04-result-validation pass", "无需处理。"))
    elif status == "block":
        detail = "04-result-validation 仍为 block。"
        checks.append(_check("result_validation", "block", detail, "先修复结果验证阻断项。"))
        blocking.append(detail)
    else:
        warning_details = _result_validation_warning_details(result_validation)
        suffix = "：" + "；".join(warning_details[:3]) if warning_details else "。"
        detail = f"04-result-validation 状态为 {status or 'missing'}{suffix}"
        checks.append(_check("result_validation", "warn", detail, "人工核对结果验证警告。"))
        warnings.append(detail)


def _check_comparisons(
    statistics: StatisticsReport,
    checks: list[dict[str, Any]],
    manual: list[str],
    warnings: list[str],
    min_execution_repeats: int,
) -> None:
    if len(statistics.comparisons) >= 2:
        checks.append(_check("statistical_comparisons", "pass", f"{len(statistics.comparisons)} comparisons", "无需处理。"))
    elif statistics.comparisons:
        detail = "只有 1 个统计比较，benchmark 证据范围偏窄。"
        checks.append(_check("statistical_comparisons", "review_required", detail, "增加核心指标或任务。"))
        manual.append(detail)
    else:
        detail = "没有 candidate-baseline 统计比较。"
        checks.append(_check("statistical_comparisons", "review_required", detail, "补齐 baseline 共同指标。"))
        manual.append(detail)
    if statistics.repeats < min_execution_repeats:
        warnings.append(f"重复次数偏低：repeats={statistics.repeats} < {min_execution_repeats}，不适合强结论。")


def _check_runbook(
    runbook: dict[str, Any],
    results: list[ExperimentResult],
    checks: list[dict[str, Any]],
    blocking: list[str],
    manual: list[str],
    warnings: list[str],
) -> None:
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    runs = runbook.get("runs") if isinstance(runbook.get("runs"), list) else []
    environment = runbook.get("environment") if isinstance(runbook.get("environment"), dict) else {}
    if not runbook:
        detail = "缺少 04-experiment-runbook。"
        checks.append(_check("runbook", "block", detail, "重新生成 runbook 后再使用结果。"))
        blocking.append(detail)
        return
    if len(runs) == len(results) and runs:
        checks.append(_check("runbook", "pass", f"{len(runs)} runs recorded, mode={execution.get('mode') or '-'}", "无需处理。"))
    else:
        detail = f"runbook runs 与结果数不一致：runbook={len(runs)} results={len(results)}。"
        checks.append(_check("runbook", "review_required", detail, "核对 runbook 是否过期。"))
        manual.append(detail)
    source_tree = environment.get("source_tree") if isinstance(environment.get("source_tree"), dict) else {}
    if not source_tree.get("aggregate_sha256"):
        warnings.append("环境快照缺少源码 aggregate hash。")


def _check_artifact_trace(
    plan: ExperimentPlan,
    runbook: dict[str, Any],
    checks: list[dict[str, Any]],
    manual: list[str],
    warnings: list[str],
) -> None:
    runs = runbook.get("runs") if isinstance(runbook.get("runs"), list) else []
    produced = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        artifacts = run.get("produced_artifacts") if isinstance(run.get("produced_artifacts"), list) else []
        produced += len(artifacts)
    expected_commands = len(plan.commands)
    if produced >= expected_commands and expected_commands:
        checks.append(_check("artifact_trace", "pass", f"{produced} artifact records for {expected_commands} commands", "无需处理。"))
    else:
        detail = f"实验 artifact trace 偏弱：{produced} records for {expected_commands} commands。"
        checks.append(_check("artifact_trace", "review_required", detail, "确认 metrics 文件、日志和产物 hash 已记录。"))
        manual.append(detail)
    if produced == 0:
        warnings.append("runbook 没有记录 produced_artifacts，结果可追溯性不足。")


def _evidence_grade(
    execution_mode: str,
    adapter_report: dict[str, Any],
    result_validation: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking: list[str],
) -> str:
    if blocking or str(result_validation.get("status") or "") == "block":
        return "blocked"
    if execution_mode == "benchmark" and str(adapter_report.get("status") or "") == "ready":
        if str(adapter_report.get("paper_grade_status") or "") != "ready":
            return "local_experiment"
        return "real_benchmark"
    if execution_mode == "local":
        return "local_experiment"
    return "smoke_only"


def _status(evidence_grade: str, blocking: list[str], manual: list[str], warnings: list[str]) -> str:
    if blocking or evidence_grade == "blocked":
        return "block"
    if evidence_grade == "smoke_only":
        return "smoke_only"
    if manual:
        return "review_required"
    if warnings:
        return "warn"
    return "pass"


def _claim_policy(evidence_grade: str, status: str, statistical_outcome: str = "") -> str:
    if status == "block" or evidence_grade == "blocked":
        return "no_effectiveness_claims_until_repaired"
    if evidence_grade == "smoke_only":
        return "smoke_test_only_no_scientific_main_claim"
    if evidence_grade == "local_experiment":
        return "preliminary_local_evidence_requires_manual_benchmark_context"
    if statistical_outcome in {"negative", "neutral_no_observed_difference"}:
        return "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims"
    if statistical_outcome in {"mixed", "inconclusive"}:
        return "mixed_or_uncertain_benchmark_claims_allowed_with_metric_level_boundaries"
    return "conservative_benchmark_claims_allowed"


def _required_actions(
    status: str,
    evidence_grade: str,
    blocking: list[str],
    manual: list[str],
    warnings: list[str],
    publishable_negative_or_neutral: bool = False,
) -> list[str]:
    actions: list[str] = []
    if blocking:
        actions.append("先修复 benchmark evidence 阻断项，再进入论文写作或强结论。")
    if evidence_grade == "smoke_only":
        actions.append("把 simulated smoke run 升级为 local 或 benchmark manifest 真实任务。")
    if evidence_grade == "local_experiment":
        actions.append("补齐 paper-grade benchmark manifest set，或在论文中明确声明任务来源、角色覆盖和重复次数限制。")
    if publishable_negative_or_neutral:
        actions.append("将负/中性 benchmark 结果作为可发表结果报告：明确 candidate 未显示优于 baseline，并禁止 superiority/stability claim。")
    actions.extend(str(item) for item in manual[:4])
    if warnings and not actions:
        actions.append("保留 benchmark evidence warning，并在论文结果边界中说明。")
    if not actions:
        actions.append("可进入保守实验结论，但仍需人工核对 benchmark 许可、引用和任务代表性。")
    return _dedupe(actions)


def _check(name: str, status: str, evidence: str, action: str) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence, "action": action}


def _statistical_outcome(statistics: StatisticsReport) -> str:
    comparisons = list(statistics.comparisons or [])
    if not comparisons:
        return "not_compared"
    stable_positive = [item for item in comparisons if item.direction == "candidate_better" and not _ci_crosses_zero(item)]
    baseline_better_or_equal = [item for item in comparisons if item.direction == "baseline_better_or_equal"]
    neutral = [item for item in baseline_better_or_equal if _is_neutral_delta(item)]
    uncertain = [item for item in comparisons if _ci_crosses_zero(item)]
    if stable_positive and len(stable_positive) == len(comparisons):
        return "positive"
    if stable_positive:
        return "mixed"
    if len(neutral) == len(comparisons):
        return "neutral_no_observed_difference"
    if baseline_better_or_equal and len(baseline_better_or_equal) == len(comparisons):
        return "negative"
    if uncertain:
        return "inconclusive"
    return "mixed"


def _claim_boundary_warnings(result_validation: dict[str, Any], statistics: StatisticsReport) -> list[str]:
    warnings: list[str] = []
    warnings.extend(_result_validation_warning_details(result_validation))
    for item in statistics.comparisons:
        if item.direction == "baseline_better_or_equal":
            if _is_neutral_delta(item):
                warnings.append(f"{item.metric}: candidate 与 baseline 未观察到差异。")
            else:
                warnings.append(f"{item.metric}: candidate 不优于 baseline。")
        elif _ci_crosses_zero(item):
            warnings.append(f"{item.metric}: 95% CI 跨 0，不能声明显著或稳定优势。")
    return _dedupe(warnings)


def _claim_boundary_severity(
    evidence_grade: str,
    blocking: list[str],
    statistical_outcome: str,
    claim_boundary_warnings: list[str],
) -> str:
    if blocking or evidence_grade == "blocked":
        return "blocked"
    if evidence_grade in {"smoke_only", "local_experiment"}:
        return "smoke_or_local_limit"
    if statistical_outcome in {"negative", "neutral_no_observed_difference"}:
        return "negative_or_neutral_no_superiority"
    if statistical_outcome in {"mixed", "inconclusive", "not_compared"}:
        return "mixed_or_uncertain_limited_claims"
    if claim_boundary_warnings:
        return "warning_requires_boundary"
    return "none"


def _publishable_negative_or_neutral_result(
    evidence_grade: str,
    result_validation: dict[str, Any],
    statistical_outcome: str,
    blocking: list[str],
    manual: list[str],
) -> bool:
    if evidence_grade != "real_benchmark" or blocking or manual:
        return False
    if statistical_outcome not in {"negative", "neutral_no_observed_difference"}:
        return False
    status = str(result_validation.get("status") or "")
    return status in {"pass", "warn"} and _result_validation_is_claim_boundary_only(result_validation)


def _result_validation_is_claim_boundary_only(result_validation: dict[str, Any]) -> bool:
    status = str(result_validation.get("status") or "")
    if status == "pass":
        return True
    if status != "warn":
        return False
    items = _as_dict_list(result_validation.get("items"))
    warning_items = [item for item in items if str(item.get("status") or "") == "warn"]
    if not warning_items:
        return True
    # contract_binding 的 warn 只表示缺少契约的迁移提示（绑定失配会直接 block），
    # 不改变负/中性结果的可发表性判定。
    return all(str(item.get("name") or "") in {"statistical_comparability", "contract_binding"} for item in warning_items)


def _result_validation_warning_details(result_validation: dict[str, Any]) -> list[str]:
    details: list[str] = []
    for item in _as_dict_list(result_validation.get("items")):
        if str(item.get("status") or "") == "warn":
            detail = str(item.get("detail") or "").strip()
            if detail:
                details.append(detail)
    details.extend(str(item) for item in _as_list(result_validation.get("warnings")))
    return _dedupe(details)


def _ci_crosses_zero(item: MetricComparison) -> bool:
    return item.ci_low <= 0 <= item.ci_high


def _is_neutral_delta(item: MetricComparison) -> bool:
    return abs(item.delta) < 1e-12 and abs(item.ci_low) < 1e-12 and abs(item.ci_high) < 1e-12


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result


