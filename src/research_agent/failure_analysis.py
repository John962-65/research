from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExperimentPlan, ExperimentResult, MetricComparison, StatisticsReport


FAILURE_ANALYSIS_JSON = "04-failure-analysis.json"
FAILURE_ANALYSIS_MD = "04-failure-analysis.md"
_BAD_STATUSES = {"failed", "blocked", "timeout"}


def write_failure_analysis_artifacts(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    report = build_failure_analysis_report(plan, results, statistics, result_validation)
    write_json(run_dir / FAILURE_ANALYSIS_JSON, report)
    write_text(run_dir / FAILURE_ANALYSIS_MD, render_failure_analysis_markdown(report))
    return report


def build_failure_analysis_report(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    result_validation: dict[str, Any],
) -> dict[str, Any]:
    failed_runs = [_failed_run_row(result) for result in results if result.status in _BAD_STATUSES]
    negative_metrics = [_comparison_row(item) for item in statistics.comparisons if item.direction == "baseline_better_or_equal"]
    uncertain_metrics = [_comparison_row(item) for item in statistics.comparisons if item.ci_low <= 0 <= item.ci_high]
    validation_status = str(result_validation.get("status") or "")
    validation_blocking = _as_list(result_validation.get("blocking_issues"))
    validation_warnings = _as_list(result_validation.get("warnings"))
    simulated_runs = [result for result in results if result.status == "simulated"]
    missing_comparisons = not statistics.comparisons
    status = _status(
        failed_runs=failed_runs,
        validation_status=validation_status,
        validation_blocking=validation_blocking,
        negative_metrics=negative_metrics,
        uncertain_metrics=uncertain_metrics,
        validation_warnings=validation_warnings,
        missing_comparisons=missing_comparisons,
        simulated_runs=simulated_runs,
    )
    required_actions = _required_actions(
        failed_runs=failed_runs,
        validation_status=validation_status,
        validation_blocking=validation_blocking,
        validation_warnings=validation_warnings,
        negative_metrics=negative_metrics,
        uncertain_metrics=uncertain_metrics,
        missing_comparisons=missing_comparisons,
        simulated_runs=simulated_runs,
    )
    claim_boundaries = _claim_boundaries(
        status=status,
        failed_runs=failed_runs,
        negative_metrics=negative_metrics,
        uncertain_metrics=uncertain_metrics,
        missing_comparisons=missing_comparisons,
        simulated_runs=simulated_runs,
    )
    return {
        "schema_version": 1,
        "idea_title": plan.idea_title,
        "status": status,
        "summary": {
            "total_results": len(results),
            "failed_runs": len(failed_runs),
            "negative_metrics": len(negative_metrics),
            "uncertain_metrics": len(uncertain_metrics),
            "missing_comparisons": missing_comparisons,
            "simulated_runs": len(simulated_runs),
        },
        "failed_runs": failed_runs,
        "negative_metrics": negative_metrics,
        "uncertain_metrics": uncertain_metrics,
        "validation_status": validation_status,
        "validation_blocking_issues": [str(item) for item in validation_blocking],
        "validation_warnings": [str(item) for item in validation_warnings],
        "failure_modes": _failure_modes(results),
        "required_actions": required_actions,
        "claim_boundaries": claim_boundaries,
    }


def render_failure_analysis_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# 失败/负结果分析：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 结果数：{summary.get('total_results', 0)}",
        f"- 失败/阻断/超时运行：{summary.get('failed_runs', 0)}",
        f"- 候选不优于基线指标：{summary.get('negative_metrics', 0)}",
        f"- CI 跨 0 指标：{summary.get('uncertain_metrics', 0)}",
        f"- 结果验证：{report.get('validation_status') or '-'}",
        "",
    ]
    required_actions = _as_list(report.get("required_actions"))
    if required_actions:
        lines.extend(["## 必须处理"])
        lines.extend(f"- {item}" for item in required_actions)
        lines.append("")
    lines.extend(
        [
            "## 失败/阻断/超时运行",
            "| 名称 | 状态 | repeat | seed | returncode | stderr 摘要 |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    failed_runs = _as_list(report.get("failed_runs"))
    if not failed_runs:
        lines.append("| 无 |  |  |  |  |  |")
    for item in failed_runs:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("name") or "")),
                        _cell(str(item.get("status") or "")),
                        str(item.get("repeat_index", "")),
                        _cell(str(item.get("seed") or "")),
                        _cell(str(item.get("returncode")) if item.get("returncode") is not None else "-"),
                        _cell(str(item.get("stderr_summary") or "")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## 负向指标", "| 指标 | Candidate | Baseline | Δ | 95% CI | 解释 |", "| --- | ---: | ---: | ---: | --- | --- |"])
    negative_metrics = _as_list(report.get("negative_metrics"))
    if not negative_metrics:
        lines.append("| 无 |  |  |  |  |  |")
    for item in negative_metrics:
        if isinstance(item, dict):
            lines.append(_metric_markdown_row(item))
    lines.extend(["", "## 不确定指标", "| 指标 | Candidate | Baseline | Δ | 95% CI | 解释 |", "| --- | ---: | ---: | ---: | --- | --- |"])
    uncertain_metrics = _as_list(report.get("uncertain_metrics"))
    if not uncertain_metrics:
        lines.append("| 无 |  |  |  |  |  |")
    for item in uncertain_metrics:
        if isinstance(item, dict):
            lines.append(_metric_markdown_row(item))
    lines.extend(["", "## 结论边界"])
    claim_boundaries = _as_list(report.get("claim_boundaries"))
    lines.extend(f"- {item}" for item in claim_boundaries) if claim_boundaries else lines.append("- 暂无额外限制。")
    return "\n".join(lines)


def _status(
    failed_runs: list[dict[str, Any]],
    validation_status: str,
    validation_blocking: list[Any],
    negative_metrics: list[dict[str, Any]],
    uncertain_metrics: list[dict[str, Any]],
    validation_warnings: list[Any],
    missing_comparisons: bool,
    simulated_runs: list[ExperimentResult],
) -> str:
    if failed_runs or validation_status == "block" or validation_blocking:
        return "block"
    if negative_metrics or uncertain_metrics or validation_status == "warn" or validation_warnings or missing_comparisons or simulated_runs:
        return "warn"
    return "pass"


def _required_actions(
    failed_runs: list[dict[str, Any]],
    validation_status: str,
    validation_blocking: list[Any],
    validation_warnings: list[Any],
    negative_metrics: list[dict[str, Any]],
    uncertain_metrics: list[dict[str, Any]],
    missing_comparisons: bool,
    simulated_runs: list[ExperimentResult],
) -> list[str]:
    actions: list[str] = []
    if failed_runs:
        failed_names = ", ".join(_dedupe([str(item.get("name") or "") for item in failed_runs])[:6])
        actions.append(f"重跑或修复失败/阻断/超时命令：{failed_names}。")
    if validation_status == "block" or validation_blocking:
        actions.append("先修复 04-result-validation 的阻断问题，再进入论文分析或实验扩展。")
    if missing_comparisons:
        actions.append("补齐 candidate 与 baseline 的共同指标，否则不能比较主效果。")
    if negative_metrics:
        names = ", ".join(str(item.get("metric") or "") for item in negative_metrics[:6])
        actions.append(f"检查候选不优于基线的指标并定位原因：{names}；论文中不得写成整体优于 baseline。")
    if uncertain_metrics:
        names = ", ".join(str(item.get("metric") or "") for item in uncertain_metrics[:6])
        actions.append(f"增加重复次数或扩大任务集以收窄 CI：{names}。")
    if validation_status == "warn" or validation_warnings:
        actions.append("把 04-result-validation 的 warning 写入局限性，并人工复核统计解释。")
    if simulated_runs:
        actions.append("将模拟实验替换为 local 或 benchmark 真实任务后，再支持论文主张。")
    return _dedupe(actions)


def _claim_boundaries(
    status: str,
    failed_runs: list[dict[str, Any]],
    negative_metrics: list[dict[str, Any]],
    uncertain_metrics: list[dict[str, Any]],
    missing_comparisons: bool,
    simulated_runs: list[ExperimentResult],
) -> list[str]:
    boundaries: list[str] = []
    if status == "block":
        boundaries.append("当前结果不得用于主张候选方法有效；只能描述为实验执行或数据产物仍需修复。")
    if missing_comparisons:
        boundaries.append("没有共同统计指标时，不得比较 candidate 与 baseline 的优劣。")
    if failed_runs:
        boundaries.append("含失败/超时/阻断运行的设置不得选择性排除，除非提供预注册排除规则和重跑记录。")
    if negative_metrics:
        boundaries.append("候选不优于基线的指标必须作为负结果报告，不能只展示正向指标。")
    if uncertain_metrics:
        boundaries.append("CI 跨 0 的指标只能表述为趋势或不确定结果，不能写成显著改进。")
    if simulated_runs:
        boundaries.append("模拟结果只能作为工程烟测；论文主结论需要 local 或 benchmark 真实实验支撑。")
    if not boundaries:
        boundaries.append("可在当前计划和指标范围内表述候选方案相对 baseline 的观察结果，但仍需保留样本量和任务范围限制。")
    return boundaries


def _failed_run_row(result: ExperimentResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "status": result.status,
        "repeat_index": result.repeat_index,
        "seed": result.seed,
        "returncode": result.returncode,
        "duration_seconds": result.duration_seconds,
        "command": result.command,
        "stderr_summary": _short_text(result.stderr or "；".join(result.validation_issues), 240),
        "validation_issues": result.validation_issues,
    }


def _comparison_row(item: MetricComparison) -> dict[str, Any]:
    return {
        "metric": item.metric,
        "candidate_mean": item.candidate_mean,
        "baseline_mean": item.baseline_mean,
        "delta": item.delta,
        "ci_low": item.ci_low,
        "ci_high": item.ci_high,
        "effect_size": item.effect_size,
        "direction": item.direction,
        "ci_crosses_zero": item.ci_low <= 0 <= item.ci_high,
        "interpretation": item.interpretation,
    }


def _failure_modes(results: list[ExperimentResult]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    bad_by_family: dict[str, int] = {}
    for result in results:
        by_status[result.status] = by_status.get(result.status, 0) + 1
        if result.status in _BAD_STATUSES:
            family = _command_family(result.name)
            bad_by_family[family] = bad_by_family.get(family, 0) + 1
    return {"by_status": by_status, "bad_by_command_family": bad_by_family}


def _command_family(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("artifact", "candidate", "proposed")):
        return "candidate"
    if any(token in lowered for token in ("baseline", "control")):
        return "baseline"
    if any(token in lowered for token in ("ablation", "without", "ablated")):
        return "ablation"
    return "other"


def _metric_markdown_row(item: dict[str, Any]) -> str:
    return (
        "| "
        + " | ".join(
            [
                _cell(str(item.get("metric") or "")),
                _fmt(item.get("candidate_mean")),
                _fmt(item.get("baseline_mean")),
                _fmt(item.get("delta")),
                _cell(f"[{_fmt(item.get('ci_low'))}, {_fmt(item.get('ci_high'))}]"),
                _cell(str(item.get("interpretation") or "")),
            ]
        )
        + " |"
    )


def _fmt(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "NA"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _short_text(value: str, max_chars: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
