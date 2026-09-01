from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import Analysis, ExperimentPlan, StatisticsReport


CLAIM_BOUNDARY_PREFLIGHT_JSON = "04-claim-boundary-preflight.json"
CLAIM_BOUNDARY_PREFLIGHT_MD = "04-claim-boundary-preflight.md"


def write_claim_boundary_preflight_artifacts(
    topic: str,
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    analysis: Analysis,
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    benchmark_evidence: dict[str, Any],
    experiment_decision: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    run_dir: Path,
    execution_mode: str = "",
) -> dict[str, Any]:
    report = build_claim_boundary_preflight_report(
        topic,
        plan,
        statistics,
        analysis,
        result_validation,
        failure_analysis,
        benchmark_evidence,
        experiment_decision,
        hypothesis_outcome,
        execution_mode=execution_mode,
    )
    write_json(run_dir / CLAIM_BOUNDARY_PREFLIGHT_JSON, report)
    write_text(run_dir / CLAIM_BOUNDARY_PREFLIGHT_MD, render_claim_boundary_preflight_markdown(report))
    return report


def build_claim_boundary_preflight_report(
    topic: str,
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    analysis: Analysis,
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    benchmark_evidence: dict[str, Any],
    experiment_decision: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    execution_mode: str = "",
) -> dict[str, Any]:
    validation_status = str(result_validation.get("status") or "")
    failure_status = str(failure_analysis.get("status") or "")
    decision = str(experiment_decision.get("decision") or "")
    decision_status = str(experiment_decision.get("status") or "")
    paper_policy = str(experiment_decision.get("paper_policy") or "")
    downstream_allowed = experiment_decision.get("downstream_writing_allowed")
    benchmark_status = str(benchmark_evidence.get("status") or "")
    benchmark_grade = str(benchmark_evidence.get("evidence_grade") or "")
    benchmark_policy = str(benchmark_evidence.get("claim_policy") or "")
    outcome = str(hypothesis_outcome.get("outcome") or "")
    outcome_status = str(hypothesis_outcome.get("status") or "")
    support_score = _safe_float(hypothesis_outcome.get("support_score"))
    comparisons = list(getattr(statistics, "comparisons", []) or [])
    negative_metrics = [item for item in comparisons if _direction(item) == "baseline_better_or_equal"]
    uncertain_metrics = [item for item in comparisons if _ci_crosses_zero(item)]
    stable_positive = [item for item in comparisons if _direction(item) == "candidate_better" and not _ci_crosses_zero(item)]

    blocking: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []
    if validation_status == "block":
        blocking.extend(_as_strings(result_validation.get("blocking_issues")) or ["04-result-validation 阻断，当前结果不能支撑论文效果主张。"])
    if failure_status == "block":
        blocking.extend(_as_strings(failure_analysis.get("blocking_issues")) or ["04-failure-analysis 阻断，当前结果不能支撑论文效果主张。"])
    if benchmark_status == "block" or benchmark_grade == "blocked":
        blocking.extend(_as_strings(benchmark_evidence.get("blocking_issues")) or ["Benchmark 证据审计被阻断。"])
    if decision == "repair_before_writing" or decision_status == "block" or downstream_allowed is False:
        blocking.append("实验后决策不允许正常写作；必须先修复实验或把草稿限制为诊断/修复报告。")
    if outcome_status == "block" or outcome in {"blocked_unverified", "untested"}:
        blocking.append("假设结果未验证或被阻断；不得写成方法有效性结论。")

    if not blocking:
        if execution_mode == "simulated" or decision == "benchmark_upgrade" or benchmark_grade == "smoke_only" or benchmark_status == "smoke_only" or outcome == "smoke_only":
            warnings.append("当前主要是 simulated/smoke 证据，只能写流程可运行或初步趋势。")
            actions.append("补真实 local/benchmark 实验后再写强效果结论。")
        if benchmark_grade == "local_experiment":
            warnings.append("Benchmark 证据仍是 local_experiment，不能外推到公开 benchmark 或广泛任务族。")
            actions.append("补公开 benchmark 来源、split、许可和任务代表性说明。")
        if decision in {"pivot_or_refine", "refine_experiment"}:
            warnings.append(f"实验后决策为 {decision}，论文必须收窄结论并规划下一轮实验。")
            actions.extend(_as_strings(experiment_decision.get("next_actions"))[:3])
        if outcome in {"partially_supported", "refuted_or_negative", "inconclusive"} or outcome_status == "review_required":
            warnings.append(f"假设结果为 {outcome or outcome_status}，写作必须区分支持、负向、不确定和未检验指标。")
            actions.extend(_as_strings(hypothesis_outcome.get("next_actions"))[:3])
        if negative_metrics:
            names = ", ".join(_metric_name(item) for item in negative_metrics[:6] if _metric_name(item))
            warnings.append(f"存在负向指标：{names or len(negative_metrics)}。")
            actions.append("负向指标必须进入结果和局限性，不能只保留正向结果。")
        if uncertain_metrics:
            names = ", ".join(_metric_name(item) for item in uncertain_metrics[:6] if _metric_name(item))
            warnings.append(f"存在 CI 跨 0 或不确定指标：{names or len(uncertain_metrics)}。")
            actions.append("不确定指标不得表述为显著提升。")

    status = "block" if blocking else "review_required" if warnings or actions else "pass"
    writing_mode = _writing_mode(status, decision, outcome, execution_mode, benchmark_grade)
    boundaries = _boundaries(
        status,
        writing_mode,
        failure_analysis,
        benchmark_evidence,
        experiment_decision,
        hypothesis_outcome,
        negative_metrics,
        uncertain_metrics,
    )
    allowed = _allowed_claims(status, writing_mode, outcome, execution_mode, benchmark_grade)
    prohibited = _prohibited_claims(status, writing_mode, outcome, benchmark_grade)
    return {
        "schema_version": 1,
        "topic": topic,
        "idea_title": plan.idea_title,
        "status": status,
        "writing_mode": writing_mode,
        "risk_score": _risk_score(status, warnings, blocking, support_score),
        "evidence_summary": {
            "execution_mode": execution_mode,
            "validation_status": validation_status,
            "failure_status": failure_status,
            "benchmark_status": benchmark_status,
            "benchmark_grade": benchmark_grade,
            "benchmark_claim_policy": benchmark_policy,
            "experiment_decision": decision,
            "experiment_decision_status": decision_status,
            "paper_policy": paper_policy,
            "downstream_writing_allowed": downstream_allowed is not False,
            "hypothesis_outcome": outcome,
            "hypothesis_status": outcome_status,
            "support_score": support_score,
            "comparisons": len(comparisons),
            "stable_positive_metrics": len(stable_positive),
            "negative_metrics": len(negative_metrics),
            "uncertain_metrics": len(uncertain_metrics),
            "analysis_findings": len(analysis.findings),
            "analysis_limitations": len(analysis.limitations),
        },
        "allowed_claims": allowed,
        "prohibited_claims": prohibited,
        "prohibited_patterns": _prohibited_patterns(status, writing_mode, outcome),
        "required_boundary_statements": boundaries,
        "prompt_constraints": _prompt_constraints(status, writing_mode, allowed, prohibited, boundaries),
        "blocking_issues": _dedupe(blocking),
        "warnings": _dedupe(warnings),
        "required_actions": _dedupe(actions),
    }


def render_claim_boundary_preflight_markdown(report: dict[str, Any]) -> str:
    summary = report.get("evidence_summary") if isinstance(report.get("evidence_summary"), dict) else {}
    lines = [
        f"# Claim Boundary Preflight：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 写作模式：{report.get('writing_mode') or '-'}",
        f"- 风险分数：{_safe_float(report.get('risk_score')):.3f}",
        f"- Idea：{report.get('idea_title') or '-'}",
        "",
        "## 证据摘要",
        f"- 执行模式：{summary.get('execution_mode') or '-'}",
        f"- 结果验证：{summary.get('validation_status') or '-'}",
        f"- 失败分析：{summary.get('failure_status') or '-'}",
        f"- Benchmark 证据：{summary.get('benchmark_status') or '-'} / {summary.get('benchmark_grade') or '-'}",
        f"- 实验后决策：{summary.get('experiment_decision') or '-'} / {summary.get('paper_policy') or '-'}",
        f"- 允许正常写作：{'是' if summary.get('downstream_writing_allowed') is True else '否'}",
        f"- 假设结果：{summary.get('hypothesis_outcome') or '-'} / {summary.get('hypothesis_status') or '-'} / support={_safe_float(summary.get('support_score')):.3f}",
        f"- 比较数/稳定正向/负向/不确定：{summary.get('comparisons', 0)}/{summary.get('stable_positive_metrics', 0)}/{summary.get('negative_metrics', 0)}/{summary.get('uncertain_metrics', 0)}",
        "",
        "## 阻断问题",
    ]
    blocking = _as_strings(report.get("blocking_issues"))
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 警告"])
    warnings = _as_strings(report.get("warnings"))
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- 无")
    lines.extend(["", "## 必须写入的边界"])
    boundaries = _as_strings(report.get("required_boundary_statements"))
    lines.extend(f"- {item}" for item in boundaries) if boundaries else lines.append("- 无")
    lines.extend(["", "## 允许表述"])
    allowed = _as_strings(report.get("allowed_claims"))
    lines.extend(f"- {item}" for item in allowed) if allowed else lines.append("- 无")
    lines.extend(["", "## 禁止表述"])
    prohibited = _as_strings(report.get("prohibited_claims"))
    lines.extend(f"- {item}" for item in prohibited) if prohibited else lines.append("- 无")
    lines.extend(["", "## 下一步动作"])
    actions = _as_strings(report.get("required_actions"))
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    return "\n".join(lines)


def _writing_mode(status: str, decision: str, outcome: str, execution_mode: str, benchmark_grade: str) -> str:
    if status == "block":
        return "repair_report_only"
    if execution_mode == "simulated" or decision == "benchmark_upgrade" or outcome == "smoke_only" or benchmark_grade == "smoke_only":
        return "smoke_limited_paper"
    if decision in {"pivot_or_refine"} or outcome == "refuted_or_negative":
        return "negative_or_pivot_report"
    if decision == "refine_experiment" or outcome in {"partially_supported", "inconclusive"} or benchmark_grade == "local_experiment":
        return "limited_claim_paper"
    return "conservative_paper"


def _boundaries(
    status: str,
    writing_mode: str,
    failure_analysis: dict[str, Any],
    benchmark_evidence: dict[str, Any],
    experiment_decision: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    negative_metrics: list[Any],
    uncertain_metrics: list[Any],
) -> list[str]:
    values: list[str] = []
    values.extend(_as_strings(failure_analysis.get("claim_boundaries")))
    values.extend(_as_strings(experiment_decision.get("claim_boundaries")))
    values.extend(_as_strings(hypothesis_outcome.get("claim_boundaries")))
    claim_policy = str(benchmark_evidence.get("claim_policy") or "")
    if claim_policy:
        values.append(f"Benchmark claim policy：{claim_policy}。")
    if status == "block":
        values.append("Claim boundary preflight 为 block；论文不得写成方法有效性论文，只能作为修复/诊断记录。")
    elif writing_mode == "smoke_limited_paper":
        values.append("当前证据只能支撑 smoke/local 范围内的初步观察，不能支撑正式科学主结论。")
    elif writing_mode == "negative_or_pivot_report":
        values.append("论文必须报告负结果或 pivot 依据，不能只保留正向叙事。")
    elif writing_mode == "limited_claim_paper":
        values.append("论文结论必须限定在已比较指标、baseline、任务范围和当前运行环境内。")
    if negative_metrics:
        values.append("存在负向指标；结论必须逐项说明候选方法不优于 baseline 的情形。")
    if uncertain_metrics:
        values.append("存在不确定指标；不得使用显著提升、稳定优于或证明类表述。")
    return _dedupe(values)[:12]


def _allowed_claims(status: str, writing_mode: str, outcome: str, execution_mode: str, benchmark_grade: str) -> list[str]:
    if status == "block":
        return ["描述实验失败、验证缺口、需要修复的 benchmark/统计问题。", "把当前草稿定位为内部诊断或下一轮实验计划。"]
    if writing_mode == "smoke_limited_paper":
        return ["描述流程可运行、smoke test 现象或初步趋势。", "明确证据来自 simulated/local 范围。"]
    if writing_mode == "negative_or_pivot_report":
        return ["报告负结果、混合结果和 pivot 依据。", "说明哪些指标不优于 baseline。"]
    if writing_mode == "limited_claim_paper":
        return ["描述已比较指标内的保守趋势。", "把结论限定在当前 baseline、任务、seed 和环境。"]
    if outcome == "supported" and benchmark_grade in {"real_benchmark", ""} and execution_mode != "simulated":
        return ["在当前 benchmark、baseline 和统计审计范围内使用保守支持性结论。"]
    return ["使用保守结论，并保留结果边界、局限性和下一轮验证计划。"]


def _prohibited_claims(status: str, writing_mode: str, outcome: str, benchmark_grade: str) -> list[str]:
    values = [
        "不得编造未运行的实验、未统计的指标或未纳入的 benchmark。",
        "不得把文献综述或模拟结果写成真实实验结果。",
    ]
    if status == "block":
        values.append("不得声称候选方法有效、证明假设或优于 baseline。")
    if writing_mode in {"smoke_limited_paper", "repair_report_only"}:
        values.append("不得声称正式 benchmark 支持、显著提升或可泛化科学主结论。")
    if writing_mode == "negative_or_pivot_report":
        values.append("不得隐藏负向指标或把负结果改写成单向正结论。")
    if writing_mode == "limited_claim_paper" or outcome in {"partially_supported", "inconclusive"}:
        values.append("不得使用证明、证实、稳定提升、全面优于等强结论。")
    if benchmark_grade == "local_experiment":
        values.append("不得外推到公开 benchmark 或未覆盖任务族。")
    return _dedupe(values)


def _prohibited_patterns(status: str, writing_mode: str, outcome: str) -> list[str]:
    patterns = ["编造实验", "未运行实验"]
    if status == "block" or writing_mode in {"smoke_limited_paper", "repair_report_only", "limited_claim_paper"} or outcome != "supported":
        patterns.extend(["证明", "证实", "显著优于", "显著提升", "稳定提升", "全面提升", "方法有效", "支持假设"])
    return _dedupe(patterns)


def _prompt_constraints(status: str, writing_mode: str, allowed: list[str], prohibited: list[str], boundaries: list[str]) -> list[str]:
    constraints = [
        f"Claim boundary preflight status={status}; writing_mode={writing_mode}.",
        "必须新增或保留“结果边界”小节，并逐条响应 required_boundary_statements。",
        "只能使用 allowed_claims 中的结论强度，不得使用 prohibited_claims 中的表述。",
    ]
    constraints.extend(f"允许：{item}" for item in allowed[:3])
    constraints.extend(f"禁止：{item}" for item in prohibited[:3])
    constraints.extend(f"边界：{item}" for item in boundaries[:4])
    return constraints


def _risk_score(status: str, warnings: list[str], blocking: list[str], support_score: float) -> float:
    if status == "block":
        return 1.0
    risk = 0.25 + min(0.5, len(warnings) * 0.1) + max(0.0, 0.3 - support_score * 0.3)
    if blocking:
        risk += 0.3
    if status == "pass":
        risk = min(risk, 0.2)
    return round(max(0.0, min(1.0, risk)), 3)


def _ci_crosses_zero(item: Any) -> bool:
    low = _value(item, "ci_low")
    high = _value(item, "ci_high")
    if low is None or high is None:
        return False
    return low <= 0 <= high


def _direction(item: Any) -> str:
    return str(_raw_value(item, "direction") or "")


def _metric_name(item: Any) -> str:
    return str(_raw_value(item, "metric") or "").strip()


def _value(item: Any, field: str) -> float | None:
    raw = _raw_value(item, field)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _raw_value(item: Any, field: str) -> Any:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
