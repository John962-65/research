from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text, cell as _cell
from .models import ExperimentPlan, MetricComparison, ResearchIdea, StatisticsReport


HYPOTHESIS_OUTCOME_JSON = "04-hypothesis-outcome.json"
HYPOTHESIS_OUTCOME_MD = "04-hypothesis-outcome.md"


def write_hypothesis_outcome_artifacts(
    idea: ResearchIdea,
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    experiment_decision: dict[str, Any],
    run_dir: Path,
    execution_mode: str = "",
) -> dict[str, Any]:
    report = build_hypothesis_outcome_report(
        idea,
        plan,
        statistics,
        result_validation,
        failure_analysis,
        experiment_decision,
        execution_mode=execution_mode,
    )
    write_json(run_dir / HYPOTHESIS_OUTCOME_JSON, report)
    write_text(run_dir / HYPOTHESIS_OUTCOME_MD, render_hypothesis_outcome_markdown(report))
    return report


def build_hypothesis_outcome_report(
    idea: ResearchIdea,
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    experiment_decision: dict[str, Any],
    execution_mode: str = "",
) -> dict[str, Any]:
    comparisons = statistics.comparisons
    stable_positive = [item for item in comparisons if item.direction == "candidate_better" and not _ci_crosses_zero(item)]
    uncertain = [item for item in comparisons if _ci_crosses_zero(item)]
    negative = [item for item in comparisons if item.direction == "baseline_better_or_equal"]
    compared_metrics = {item.metric for item in comparisons}
    planned_metrics = [metric for metric in plan.metrics if metric]
    missing_metrics = [metric for metric in planned_metrics if metric not in compared_metrics]
    validation_status = str(result_validation.get("status") or "")
    failure_status = str(failure_analysis.get("status") or "")
    decision = str(experiment_decision.get("decision") or "")
    outcome, status = _outcome(
        comparisons=comparisons,
        stable_positive=stable_positive,
        uncertain=uncertain,
        negative=negative,
        missing_metrics=missing_metrics,
        validation_status=validation_status,
        failure_status=failure_status,
        decision=decision,
        execution_mode=execution_mode,
    )
    support_score = _support_score(comparisons, stable_positive, uncertain, negative, missing_metrics, validation_status, failure_status, decision, execution_mode)
    boundaries = _claim_boundaries(outcome, missing_metrics, stable_positive, uncertain, negative, validation_status, failure_status, decision, execution_mode)
    return {
        "schema_version": 1,
        "idea_title": idea.title,
        "hypothesis": idea.hypothesis,
        "experiment_objective": plan.objective,
        "baseline": plan.baseline or idea.baseline,
        "status": status,
        "outcome": outcome,
        "support_score": support_score,
        "paper_statement": _paper_statement(outcome),
        "evidence_summary": {
            "execution_mode": execution_mode,
            "validation_status": validation_status,
            "failure_status": failure_status,
            "experiment_decision": decision,
            "planned_metrics": len(planned_metrics),
            "compared_metrics": len(comparisons),
            "stable_positive_metrics": len(stable_positive),
            "negative_metrics": len(negative),
            "uncertain_metrics": len(uncertain),
            "missing_planned_metrics": len(missing_metrics),
        },
        "stable_positive_metrics": [_comparison_row(item) for item in stable_positive],
        "negative_metrics": [_comparison_row(item) for item in negative],
        "uncertain_metrics": [_comparison_row(item) for item in uncertain],
        "missing_planned_metrics": missing_metrics,
        "claim_boundaries": boundaries,
        "next_actions": _next_actions(outcome, missing_metrics, uncertain, negative, decision, execution_mode),
    }


def render_hypothesis_outcome_markdown(report: dict[str, Any]) -> str:
    summary = report.get("evidence_summary") if isinstance(report.get("evidence_summary"), dict) else {}
    lines = [
        f"# 假设结果审计：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 结果判定：{report.get('outcome') or '-'}",
        f"- 支撑分数：{_safe_float(report.get('support_score')):.3f}",
        f"- 论文表述：{report.get('paper_statement') or '-'}",
        f"- 假设：{report.get('hypothesis') or '-'}",
        f"- 实验目标：{report.get('experiment_objective') or '-'}",
        f"- Baseline：{report.get('baseline') or '-'}",
        "",
        "## 证据摘要",
        f"- 执行模式：{summary.get('execution_mode') or '-'}",
        f"- 结果验证：{summary.get('validation_status') or '-'}",
        f"- 失败分析：{summary.get('failure_status') or '-'}",
        f"- 实验后决策：{summary.get('experiment_decision') or '-'}",
        f"- 计划指标/已比较：{summary.get('planned_metrics', 0)}/{summary.get('compared_metrics', 0)}",
        f"- 稳定正向/负向/不确定：{summary.get('stable_positive_metrics', 0)}/{summary.get('negative_metrics', 0)}/{summary.get('uncertain_metrics', 0)}",
        f"- 未检验计划指标：{summary.get('missing_planned_metrics', 0)}",
        "",
        "## 稳定正向指标",
        "| 指标 | Candidate | Baseline | Δ | 95% CI | 解释 |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    _extend_metric_rows(lines, report.get("stable_positive_metrics"))
    lines.extend(["", "## 负向指标", "| 指标 | Candidate | Baseline | Δ | 95% CI | 解释 |", "| --- | ---: | ---: | ---: | --- | --- |"])
    _extend_metric_rows(lines, report.get("negative_metrics"))
    lines.extend(["", "## 不确定指标", "| 指标 | Candidate | Baseline | Δ | 95% CI | 解释 |", "| --- | ---: | ---: | ---: | --- | --- |"])
    _extend_metric_rows(lines, report.get("uncertain_metrics"))
    lines.extend(["", "## 未检验计划指标"])
    missing = report.get("missing_planned_metrics") if isinstance(report.get("missing_planned_metrics"), list) else []
    lines.extend(f"- {item}" for item in missing) if missing else lines.append("- 无")
    lines.extend(["", "## 结论边界"])
    boundaries = report.get("claim_boundaries") if isinstance(report.get("claim_boundaries"), list) else []
    lines.extend(f"- {item}" for item in boundaries) if boundaries else lines.append("- 无")
    lines.extend(["", "## 下一步动作"])
    actions = report.get("next_actions") if isinstance(report.get("next_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    return "\n".join(lines)


def _outcome(
    comparisons: list[MetricComparison],
    stable_positive: list[MetricComparison],
    uncertain: list[MetricComparison],
    negative: list[MetricComparison],
    missing_metrics: list[str],
    validation_status: str,
    failure_status: str,
    decision: str,
    execution_mode: str,
) -> tuple[str, str]:
    if validation_status == "block" or failure_status == "block" or decision == "repair_before_writing":
        return "blocked_unverified", "block"
    if not comparisons:
        return "untested", "block"
    if execution_mode == "simulated" or decision == "benchmark_upgrade":
        return "smoke_only", "review_required"
    if negative and not stable_positive:
        return "refuted_or_negative", "review_required"
    if stable_positive and not negative and not uncertain and not missing_metrics and validation_status == "pass" and failure_status == "pass":
        return "supported", "pass"
    if stable_positive:
        return "partially_supported", "review_required"
    return "inconclusive", "review_required"


def _support_score(
    comparisons: list[MetricComparison],
    stable_positive: list[MetricComparison],
    uncertain: list[MetricComparison],
    negative: list[MetricComparison],
    missing_metrics: list[str],
    validation_status: str,
    failure_status: str,
    decision: str,
    execution_mode: str,
) -> float:
    if validation_status == "block" or failure_status == "block" or decision == "repair_before_writing":
        return 0.0
    if not comparisons:
        return 0.0
    score = (len(stable_positive) + 0.35 * len(uncertain)) / max(1, len(comparisons) + len(missing_metrics))
    score -= min(0.6, 0.3 * len(negative))
    if execution_mode == "simulated" or decision == "benchmark_upgrade":
        score = min(score, 0.45)
    return round(max(0.0, min(1.0, score)), 3)


def _claim_boundaries(
    outcome: str,
    missing_metrics: list[str],
    stable_positive: list[MetricComparison],
    uncertain: list[MetricComparison],
    negative: list[MetricComparison],
    validation_status: str,
    failure_status: str,
    decision: str,
    execution_mode: str,
) -> list[str]:
    boundaries: list[str] = []
    if outcome == "supported":
        boundaries.append("假设结果审计支持当前假设，但结论仍限于本次 benchmark、baseline、任务和随机种子范围。")
    elif outcome == "partially_supported":
        boundaries.append("假设只得到部分支持；论文必须区分稳定正向、不确定和未检验指标。")
    elif outcome == "refuted_or_negative":
        boundaries.append("假设当前被负向结果反驳或未显示优势；论文必须报告负结果并考虑方法 pivot。")
    elif outcome == "smoke_only":
        boundaries.append("当前仅为 simulated/smoke 证据；不得写成正式 benchmark 支持的科学结论。")
    elif outcome == "untested":
        boundaries.append("计划假设尚未被统计比较检验；不得写成效果结论。")
    else:
        boundaries.append("假设结果不确定；论文只能写成初步观察或待验证趋势。")
    if validation_status == "block" or failure_status == "block" or decision == "repair_before_writing":
        boundaries.append("结果验证、失败分析或实验后决策存在阻断项；当前结果不得支撑方法有效性主张。")
    if missing_metrics:
        boundaries.append("仍有计划指标未被统计比较检验：" + ", ".join(missing_metrics[:6]) + "。")
    if uncertain:
        boundaries.append("CI 跨 0 指标只能表述为不确定趋势。")
    if negative:
        boundaries.append("候选不优于 baseline 的指标必须作为负结果报告。")
    if execution_mode == "simulated":
        boundaries.append("模拟执行模式不能替代真实 local/benchmark 证据。")
    if stable_positive and negative:
        boundaries.append("不得把混合结果概括为整体优于 baseline。")
    return _dedupe(boundaries)


def _next_actions(
    outcome: str,
    missing_metrics: list[str],
    uncertain: list[MetricComparison],
    negative: list[MetricComparison],
    decision: str,
    execution_mode: str,
) -> list[str]:
    actions: list[str] = []
    if outcome in {"blocked_unverified", "untested"}:
        actions.append("先修复实验执行和统计比较，再重新生成 hypothesis outcome。")
    if outcome == "smoke_only" or execution_mode == "simulated" or decision == "benchmark_upgrade":
        actions.append("把 simulated/smoke 实验升级为 local 或公开 benchmark。")
    if missing_metrics:
        actions.append("补齐未检验计划指标的 candidate/baseline 统计比较：" + ", ".join(missing_metrics[:6]) + "。")
    if uncertain:
        actions.append("增加重复次数或任务规模以收窄 CI：" + ", ".join(item.metric for item in uncertain[:6]) + "。")
    if negative:
        actions.append("分析负向指标，决定报告负结果、方法 pivot 或重设 hypothesis：" + ", ".join(item.metric for item in negative[:6]) + "。")
    if not actions:
        actions.append("保留当前证据边界，并在论文中逐项报告支持假设的指标。")
    return _dedupe(actions)


def _paper_statement(outcome: str) -> str:
    return {
        "supported": "当前实验支持该假设，可在限定范围内保守表述。",
        "partially_supported": "当前实验部分支持该假设，必须逐项说明不确定和未检验指标。",
        "refuted_or_negative": "当前实验不支持该假设或出现负结果，应报告负结果并考虑 pivot。",
        "smoke_only": "当前仅有 smoke/simulated 证据，不能作为正式科学结论。",
        "untested": "假设尚未被统计比较检验。",
        "blocked_unverified": "实验结果存在阻断项，不能用于验证假设。",
        "inconclusive": "当前证据不足以判断假设。",
    }.get(outcome, "需要人工复核假设结果。")


def _ci_crosses_zero(item: MetricComparison) -> bool:
    return item.ci_low <= 0 <= item.ci_high


def _comparison_row(item: MetricComparison) -> dict[str, Any]:
    return {
        "metric": item.metric,
        "candidate_mean": item.candidate_mean,
        "baseline_mean": item.baseline_mean,
        "delta": item.delta,
        "ci_low": item.ci_low,
        "ci_high": item.ci_high,
        "direction": item.direction,
        "ci_crosses_zero": _ci_crosses_zero(item),
        "interpretation": item.interpretation,
    }


def _extend_metric_rows(lines: list[str], value: Any) -> None:
    rows = value if isinstance(value, list) else []
    if not rows:
        lines.append("| 无 |  |  |  |  |  |")
        return
    for item in rows:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("metric") or "")),
                    f"{_safe_float(item.get('candidate_mean')):.3f}",
                    f"{_safe_float(item.get('baseline_mean')):.3f}",
                    f"{_safe_float(item.get('delta')):.3f}",
                    f"[{_safe_float(item.get('ci_low')):.3f}, {_safe_float(item.get('ci_high')):.3f}]",
                    _cell(str(item.get("interpretation") or "")),
                ]
            )
            + " |"
        )


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


