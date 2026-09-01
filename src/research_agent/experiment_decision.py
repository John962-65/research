from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExperimentPlan, StatisticsReport


EXPERIMENT_DECISION_JSON = "04-experiment-decision.json"
EXPERIMENT_DECISION_MD = "04-experiment-decision.md"


def write_experiment_decision_artifacts(
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    run_dir: Path,
    execution_mode: str = "",
    benchmark_plan: dict[str, Any] | None = None,
    benchmark_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_experiment_decision_report(
        plan,
        statistics,
        result_validation,
        failure_analysis,
        execution_mode=execution_mode,
        benchmark_plan=benchmark_plan,
        benchmark_evidence=benchmark_evidence,
    )
    write_json(run_dir / EXPERIMENT_DECISION_JSON, report)
    write_text(run_dir / EXPERIMENT_DECISION_MD, render_experiment_decision_markdown(report))
    return report


def build_experiment_decision_report(
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    execution_mode: str = "",
    benchmark_plan: dict[str, Any] | None = None,
    benchmark_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_status = str(result_validation.get("status") or "")
    failure_status = str(failure_analysis.get("status") or "")
    summary = failure_analysis.get("summary") if isinstance(failure_analysis.get("summary"), dict) else {}
    benchmark_plan = benchmark_plan if isinstance(benchmark_plan, dict) else {}
    benchmark_evidence = benchmark_evidence if isinstance(benchmark_evidence, dict) else {}
    benchmark_actions = _as_list(benchmark_plan.get("required_actions"))
    benchmark_evidence_status = str(benchmark_evidence.get("status") or "")
    benchmark_evidence_grade = str(benchmark_evidence.get("evidence_grade") or "")
    benchmark_evidence_actions = _as_list(benchmark_evidence.get("required_actions"))
    negative_metrics = _as_list(failure_analysis.get("negative_metrics"))
    uncertain_metrics = _as_list(failure_analysis.get("uncertain_metrics"))
    failed_runs = _as_list(failure_analysis.get("failed_runs"))
    simulated_runs = _safe_int(summary.get("simulated_runs"))
    decision, status = _decision(
        validation_status=validation_status,
        failure_status=failure_status,
        execution_mode=execution_mode,
        failed_runs=failed_runs,
        negative_metrics=negative_metrics,
        uncertain_metrics=uncertain_metrics,
        simulated_runs=simulated_runs,
        benchmark_actions=benchmark_actions,
        benchmark_evidence_status=benchmark_evidence_status,
        benchmark_evidence_grade=benchmark_evidence_grade,
    )
    next_actions = _next_actions(
        decision=decision,
        validation_status=validation_status,
        failure_status=failure_status,
        failed_runs=failed_runs,
        negative_metrics=negative_metrics,
        uncertain_metrics=uncertain_metrics,
        simulated_runs=simulated_runs,
        benchmark_actions=benchmark_actions,
        benchmark_evidence_status=benchmark_evidence_status,
        benchmark_evidence_grade=benchmark_evidence_grade,
        benchmark_evidence_actions=benchmark_evidence_actions,
    )
    claim_boundaries = _claim_boundaries(decision, failure_analysis, execution_mode, negative_metrics, uncertain_metrics, simulated_runs, benchmark_evidence)
    return {
        "schema_version": 1,
        "idea_title": plan.idea_title,
        "status": status,
        "decision": decision,
        "paper_policy": _paper_policy(decision),
        "downstream_writing_allowed": decision not in {"repair_before_writing"},
        "evidence_summary": {
            "validation_status": validation_status,
            "failure_status": failure_status,
            "execution_mode": execution_mode,
            "comparisons": len(statistics.comparisons),
            "failed_runs": len(failed_runs),
            "negative_metrics": len(negative_metrics),
            "uncertain_metrics": len(uncertain_metrics),
            "simulated_runs": simulated_runs,
            "benchmark_actions": len(benchmark_actions),
            "benchmark_evidence_status": benchmark_evidence_status,
            "benchmark_evidence_grade": benchmark_evidence_grade,
        },
        "next_actions": next_actions,
        "claim_boundaries": claim_boundaries,
        "rationale": _rationale(decision),
    }


def render_experiment_decision_markdown(report: dict[str, Any]) -> str:
    summary = report.get("evidence_summary") if isinstance(report.get("evidence_summary"), dict) else {}
    lines = [
        f"# 实验后决策：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 决策：{report.get('decision') or '-'}",
        f"- 论文策略：{report.get('paper_policy') or '-'}",
        f"- 允许继续写作：{'是' if report.get('downstream_writing_allowed') is True else '否'}",
        f"- 理由：{report.get('rationale') or '-'}",
        "",
        "## 证据摘要",
        f"- 结果验证：{summary.get('validation_status') or '-'}",
        f"- 失败分析：{summary.get('failure_status') or '-'}",
        f"- 执行模式：{summary.get('execution_mode') or '-'}",
        f"- 统计比较数：{summary.get('comparisons', 0)}",
        f"- 失败/阻断运行：{summary.get('failed_runs', 0)}",
        f"- 负向指标：{summary.get('negative_metrics', 0)}",
        f"- 不确定指标：{summary.get('uncertain_metrics', 0)}",
        f"- 模拟结果数：{summary.get('simulated_runs', 0)}",
        f"- Benchmark 待办：{summary.get('benchmark_actions', 0)}",
        f"- Benchmark 证据：{summary.get('benchmark_evidence_status') or '-'} / {summary.get('benchmark_evidence_grade') or '-'}",
        "",
        "## 下一步动作",
    ]
    actions = report.get("next_actions") if isinstance(report.get("next_actions"), list) else []
    lines.extend(f"- {item}" for item in actions) if actions else lines.append("- 暂无")
    lines.extend(["", "## 结论边界"])
    boundaries = report.get("claim_boundaries") if isinstance(report.get("claim_boundaries"), list) else []
    lines.extend(f"- {item}" for item in boundaries) if boundaries else lines.append("- 暂无")
    lines.extend(
        [
            "",
            "## 使用方式",
            "- `repair_before_writing` 表示当前实验产物不能支撑论文结果，应先修复验证或失败项。",
            "- `refine_experiment` 表示结果可进入保守草稿，但下一轮应补重复、补指标或扩大任务集。",
            "- `pivot_or_refine` 表示负结果需要作为发现报告，或推动 idea/方法 pivot。",
            "- `benchmark_upgrade` 表示当前主要是 smoke 证据，应优先接真实 benchmark。",
        ]
    )
    return "\n".join(lines)


def _decision(
    validation_status: str,
    failure_status: str,
    execution_mode: str,
    failed_runs: list[Any],
    negative_metrics: list[Any],
    uncertain_metrics: list[Any],
    simulated_runs: int,
    benchmark_actions: list[Any],
    benchmark_evidence_status: str,
    benchmark_evidence_grade: str,
) -> tuple[str, str]:
    if benchmark_evidence_status == "block" or benchmark_evidence_grade == "blocked":
        return "repair_before_writing", "block"
    if validation_status == "block" or failure_status == "block" or failed_runs:
        return "repair_before_writing", "block"
    if negative_metrics:
        return "pivot_or_refine", "warn"
    if uncertain_metrics or validation_status == "warn" or failure_status == "warn":
        return "refine_experiment", "warn"
    if execution_mode == "simulated" or simulated_runs:
        return "benchmark_upgrade", "warn"
    if benchmark_evidence_status in {"smoke_only", "review_required"} or benchmark_evidence_grade in {"smoke_only", "local_experiment"}:
        return "benchmark_upgrade", "warn"
    if benchmark_actions:
        return "benchmark_upgrade", "warn"
    return "proceed_to_paper", "pass"


def _next_actions(
    decision: str,
    validation_status: str,
    failure_status: str,
    failed_runs: list[Any],
    negative_metrics: list[Any],
    uncertain_metrics: list[Any],
    simulated_runs: int,
    benchmark_actions: list[Any],
    benchmark_evidence_status: str,
    benchmark_evidence_grade: str,
    benchmark_evidence_actions: list[Any],
) -> list[str]:
    actions: list[str] = []
    if decision == "repair_before_writing":
        actions.append("先修复 04-result-validation 或 04-failure-analysis 的阻断项，再重新分析和写作。")
    if failed_runs:
        actions.append("重跑或修复失败/阻断/超时命令，保留 runbook 中的重跑记录。")
    if validation_status == "block":
        actions.append("补齐命令覆盖、ablation 覆盖、共同指标或预注册一致性。")
    if failure_status == "block":
        actions.append("处理失败运行，避免把无效结果写成方法有效性证据。")
    if negative_metrics:
        names = ", ".join(_metric_name(item) for item in negative_metrics[:6] if _metric_name(item))
        actions.append(f"把负向指标作为结果报告，并判断是否需要 pivot：{names}。")
    if uncertain_metrics:
        names = ", ".join(_metric_name(item) for item in uncertain_metrics[:6] if _metric_name(item))
        actions.append(f"增加重复次数或任务规模，优先收窄这些指标的 CI：{names}。")
    if simulated_runs:
        actions.append("把 simulated smoke test 替换为 local 或 benchmark 真实任务后，再支持强结论。")
    if benchmark_evidence_status in {"block", "smoke_only", "review_required"} or benchmark_evidence_grade in {"blocked", "smoke_only", "local_experiment"}:
        actions.extend(str(item) for item in benchmark_evidence_actions[:4])
    if benchmark_actions:
        actions.extend(str(item) for item in benchmark_actions[:3])
    if not actions:
        actions.append("可以进入保守论文草稿，并继续保留样本量、任务范围和 benchmark 限制。")
    return _dedupe(actions)


def _claim_boundaries(
    decision: str,
    failure_analysis: dict[str, Any],
    execution_mode: str,
    negative_metrics: list[Any],
    uncertain_metrics: list[Any],
    simulated_runs: int,
    benchmark_evidence: dict[str, Any],
) -> list[str]:
    values = _as_list(failure_analysis.get("claim_boundaries"))
    if decision == "repair_before_writing":
        values.append("实验后决策为 repair_before_writing；当前结果不得用于主张候选方法有效。")
    if decision == "pivot_or_refine":
        values.append("实验后决策为 pivot_or_refine；负结果必须作为发现报告，不能只展示正向指标。")
    if decision == "refine_experiment":
        values.append("实验后决策为 refine_experiment；当前结论只能表述为初步趋势或待扩展验证。")
    if decision == "benchmark_upgrade" or execution_mode == "simulated" or simulated_runs:
        values.append("实验后决策要求 benchmark_upgrade；模拟或 smoke 结果不能支撑正式科学主结论。")
    evidence_grade = str(benchmark_evidence.get("evidence_grade") or "")
    if evidence_grade == "smoke_only":
        values.append("Benchmark 证据审计为 smoke_only；只能声称流程可运行或初步趋势。")
    elif evidence_grade == "local_experiment":
        values.append("Benchmark 证据审计为 local_experiment；强结论需要补公开 benchmark 来源、split、许可和任务代表性说明。")
    elif evidence_grade == "blocked":
        values.append("Benchmark 证据审计为 blocked；当前结果不得支撑有效性主张。")
    if negative_metrics:
        values.append("存在候选不优于 baseline 的指标，论文结论必须逐项降级。")
    if uncertain_metrics:
        values.append("存在 CI 跨 0 的指标，论文不得表述为显著改进。")
    return _dedupe([str(item).strip() for item in values if str(item).strip()])[:10]


def _paper_policy(decision: str) -> str:
    mapping = {
        "repair_before_writing": "repair_only_no_effectiveness_claims",
        "pivot_or_refine": "report_negative_results_and_consider_pivot",
        "refine_experiment": "preliminary_trends_only",
        "benchmark_upgrade": "smoke_test_only_until_real_benchmark",
        "proceed_to_paper": "conservative_claims_allowed",
    }
    return mapping.get(decision, "conservative_claims_only")


def _rationale(decision: str) -> str:
    mapping = {
        "repair_before_writing": "结果验证或失败分析存在阻断项，继续写作会把无效实验包装成结论。",
        "pivot_or_refine": "候选方案在至少一个指标上不优于 baseline，应报告负结果并考虑 pivot。",
        "refine_experiment": "结果存在 warning 或不确定指标，适合补重复、补任务或收窄结论。",
        "benchmark_upgrade": "当前证据仍偏 smoke 或缺真实 benchmark，强结论需要升级实验环境。",
        "proceed_to_paper": "结果验证、失败分析和 benchmark 条件未发现硬阻断，可进入保守草稿。",
    }
    return mapping.get(decision, "需要人工复核实验后决策。")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _metric_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("metric") or "").strip()
    return ""


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
