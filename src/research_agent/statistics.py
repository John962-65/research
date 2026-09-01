from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExperimentPlan, ExperimentResult, MetricComparison, StatisticsReport
import math


STATISTICS_FIGURE_JSON = "04-statistics-figure.json"
STATISTICS_FIGURE_SVG = "04-statistics-figure.svg"


def build_statistics_report(plan: ExperimentPlan, results: list[ExperimentResult]) -> StatisticsReport:
    role_lookup = {command.name: command.role for command in plan.commands if command.role}
    group_lookup = {command.name: command.comparison_group or "default" for command in plan.commands}
    warnings: list[str] = []
    valid_results = [result for result in results if result.status in {"passed", "simulated"}]
    excluded_statuses = sorted({result.status for result in results if result.status not in {"passed", "simulated"}})
    if excluded_statuses:
        warnings.append("已排除未成功完成的结果状态：" + ", ".join(excluded_statuses))
    candidate = _find_group(valid_results, ["artifact", "candidate", "proposed"], role_lookup=role_lookup, role="candidate")
    baseline = _find_group(valid_results, ["baseline", "control"], role_lookup=role_lookup, role="baseline")
    if not candidate:
        warnings.append("未找到 candidate/proposed/artifact 结果组，无法计算候选方案统计量。")
    if not baseline:
        warnings.append("未找到 baseline/control 结果组，无法计算对照统计量。")
    if not candidate or not baseline:
        return StatisticsReport(
            idea_title=plan.idea_title,
            repeats=0,
            candidate_name=candidate[0].name if candidate else "",
            baseline_name=baseline[0].name if baseline else "",
            comparisons=[],
            warnings=warnings,
            multiplicity=_multiplicity_plan(plan, []),
            power_analysis=_power_analysis(0, []),
        )

    candidate, baseline, compatibility_warnings = _compatible_groups(candidate, baseline, group_lookup)
    warnings.extend(compatibility_warnings)
    if not candidate or not baseline:
        return StatisticsReport(
            idea_title=plan.idea_title,
            repeats=0,
            candidate_name="",
            baseline_name="",
            comparisons=[],
            warnings=warnings,
            multiplicity=_multiplicity_plan(plan, []),
            power_analysis=_power_analysis(0, []),
        )

    pairs, pairing_warnings = _paired_results(candidate, baseline)
    warnings.extend(pairing_warnings)
    planned_metrics = {metric for metric in plan.metrics if metric}
    metric_pairs = [pair for pair in pairs if _pair_has_comparable_metric(pair, planned_metrics)]
    if len(metric_pairs) != len(pairs):
        warnings.append("已排除没有共同有限数值指标的配对结果。")
    pairs = metric_pairs
    if not pairs:
        warnings.append("candidate 与 baseline 没有同 repeat 且同 seed 的可配对结果，拒绝计算统计比较。")
        return StatisticsReport(
            idea_title=plan.idea_title,
            repeats=0,
            candidate_name=candidate[0].name,
            baseline_name=baseline[0].name,
            comparisons=[],
            warnings=warnings,
            multiplicity=_multiplicity_plan(plan, []),
            power_analysis=_power_analysis(0, []),
        )

    candidate_metrics, baseline_metrics = _paired_metric_values(pairs)
    comparisons: list[MetricComparison] = []
    shared_metrics = set(candidate_metrics) & set(baseline_metrics)
    comparable_metrics = shared_metrics & planned_metrics if planned_metrics else shared_metrics
    for metric in sorted(comparable_metrics):
        left = candidate_metrics[metric]
        right = baseline_metrics[metric]
        if not left or not right:
            continue
        comparison = _compare_paired_metric(metric, left, right)
        comparisons.append(comparison)
    if len(pairs) < 3:
        warnings.append("重复次数少于 3，置信区间和效应量仅作烟测参考。")
    missing_planned = sorted(planned_metrics - shared_metrics)
    if missing_planned:
        warnings.append("计划指标未在 candidate/baseline 共同结果中出现：" + ", ".join(missing_planned[:6]))
    if not comparisons:
        warnings.append("candidate 与 baseline 没有共同指标。")
    return StatisticsReport(
        idea_title=plan.idea_title,
        repeats=len(pairs),
        candidate_name=candidate[0].name,
        baseline_name=baseline[0].name,
        comparisons=comparisons,
        warnings=warnings,
        multiplicity=_multiplicity_plan(plan, comparisons),
        power_analysis=_power_analysis(len(pairs), comparisons),
    )


def render_statistics_markdown(report: StatisticsReport) -> str:
    lines = [
        f"# 统计审计：{report.idea_title}",
        "",
        f"- Candidate：{report.candidate_name or '未找到'}",
        f"- Baseline：{report.baseline_name or '未找到'}",
        f"- 重复次数：{report.repeats}",
        "",
    ]
    if report.warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in report.warnings)
        lines.append("")
    multiplicity = report.multiplicity or {}
    power = report.power_analysis or {}
    if multiplicity or power:
        lines.extend(
            [
                "## 统计设计",
                f"- 多重比较策略：{multiplicity.get('strategy') or '-'}",
                f"- 指标族大小：{multiplicity.get('family_size') if multiplicity else 0}",
                f"- 功效分析：{power.get('status') or '-'}；每组重复：{power.get('per_group_repeats') if power else 0}；近似 MDE：{power.get('minimum_detectable_standardized_effect') or '-'}",
                f"- 解释边界：{power.get('interpretation') or '-'}",
                "",
            ]
        )
    lines.extend(
        [
            "## 指标比较",
            "| 指标 | Candidate 均值 | Baseline 均值 | 差值 | 95% CI | 标准化效应量 | 方向 | 解释 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not report.comparisons:
        lines.append("| 无共同指标 |  |  |  |  |  |  |  |")
    for item in report.comparisons:
        effect = "NA" if item.effect_size is None else f"{item.effect_size:.3f}"
        lines.append(
            "| "
            + " | ".join(
                [
                    item.metric,
                    f"{item.candidate_mean:.3f}",
                    f"{item.baseline_mean:.3f}",
                    f"{item.delta:.3f}",
                    f"[{item.ci_low:.3f}, {item.ci_high:.3f}]",
                    effect,
                    item.direction,
                    item.interpretation,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_statistics_figure_artifacts(out_dir: Path, report: StatisticsReport) -> dict[str, Any]:
    data = build_statistics_figure_data(report)
    write_json(out_dir / STATISTICS_FIGURE_JSON, data)
    write_text(out_dir / STATISTICS_FIGURE_SVG, render_statistics_figure_svg(report, data))
    return data


def build_statistics_figure_data(report: StatisticsReport) -> dict[str, Any]:
    comparisons = [_comparison_row(item) for item in report.comparisons[:8]]
    values = [abs(float(row[key])) for row in comparisons for key in ("delta", "ci_low", "ci_high")]
    axis_limit = max(values) if values else 1.0
    axis_limit = 1.0 if axis_limit <= 0 else axis_limit * 1.15
    candidate_better = sum(1 for row in comparisons if row["direction"] == "candidate_better")
    uncertain = sum(1 for row in comparisons if row["ci_crosses_zero"])
    return {
        "schema_version": 1,
        "title": f"统计可视化：{report.idea_title}",
        "status": "ok" if comparisons else "no_comparisons",
        "candidate": report.candidate_name,
        "baseline": report.baseline_name,
        "repeats": report.repeats,
        "axis": {"label": "candidate - baseline", "min": round(-axis_limit, 6), "max": round(axis_limit, 6)},
        "summary": {
            "metrics": len(comparisons),
            "candidate_better": candidate_better,
            "baseline_better_or_equal": len(comparisons) - candidate_better,
            "ci_crosses_zero": uncertain,
        },
        "comparisons": comparisons,
        "warnings": report.warnings,
    }


def render_statistics_figure_svg(report: StatisticsReport, data: dict[str, Any] | None = None) -> str:
    data = data or build_statistics_figure_data(report)
    comparisons = data.get("comparisons", []) if isinstance(data.get("comparisons"), list) else []
    rows = max(1, len(comparisons))
    width = 960
    top = 118
    row_height = 54
    height = top + rows * row_height + 72
    left = 260
    plot_width = 600
    axis_min = float((data.get("axis") or {}).get("min") or -1.0)
    axis_max = float((data.get("axis") or {}).get("max") or 1.0)

    def x(value: float) -> float:
        span = axis_max - axis_min
        if span <= 0:
            return left + plot_width / 2
        return left + ((value - axis_min) / span) * plot_width

    zero_x = x(0.0)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">" + _svg_text(str(data.get("title") or "统计可视化")) + "</title>",
        "<desc id=\"desc\">Candidate 与 baseline 的均值差值和 95% CI，可用于快速识别仍需更多重复实验确认的指标。</desc>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="28" y="38" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#172033">{_svg_text(report.idea_title)}</text>',
        f'<text x="28" y="66" font-family="Arial, sans-serif" font-size="13" fill="#4c5a6a">Candidate: {_svg_text(report.candidate_name or "-")} | Baseline: {_svg_text(report.baseline_name or "-")} | repeats: {report.repeats}</text>',
        f'<line x1="{left}" y1="{top - 26}" x2="{left + plot_width}" y2="{top - 26}" stroke="#9aa7b7" stroke-width="1"/>',
        f'<line x1="{zero_x:.1f}" y1="{top - 42}" x2="{zero_x:.1f}" y2="{height - 58}" stroke="#2f3b4a" stroke-width="1.5"/>',
        f'<text x="{zero_x + 5:.1f}" y="{top - 32}" font-family="Arial, sans-serif" font-size="12" fill="#2f3b4a">0</text>',
        f'<text x="{left}" y="{height - 26}" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a" text-anchor="start">{axis_min:.2f}</text>',
        f'<text x="{left + plot_width}" y="{height - 26}" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a" text-anchor="end">{axis_max:.2f}</text>',
        f'<text x="{left + plot_width / 2}" y="{height - 26}" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a" text-anchor="middle">candidate - baseline</text>',
    ]
    if not comparisons:
        lines.append('<text x="28" y="132" font-family="Arial, sans-serif" font-size="16" fill="#7a2430">没有可比较的共同指标。</text>')
    for index, item in enumerate(comparisons):
        y = top + index * row_height
        metric = str(item.get("metric") or "")
        delta = float(item.get("delta") or 0.0)
        ci_low = float(item.get("ci_low") or delta)
        ci_high = float(item.get("ci_high") or delta)
        uncertain = bool(item.get("ci_crosses_zero"))
        color = "#2f7d4f" if item.get("direction") == "candidate_better" else "#b14b4b"
        if uncertain:
            color = "#6f7785"
        ci_x1 = x(ci_low)
        ci_x2 = x(ci_high)
        delta_x = x(delta)
        lines.extend(
            [
                f'<line x1="28" y1="{y + 17}" x2="{width - 34}" y2="{y + 17}" stroke="#edf1f5" stroke-width="1"/>',
                f'<text x="28" y="{y + 23}" font-family="Arial, sans-serif" font-size="13" fill="#172033">{_svg_text(_short_metric(metric))}</text>',
                f'<line x1="{ci_x1:.1f}" y1="{y + 18}" x2="{ci_x2:.1f}" y2="{y + 18}" stroke="{color}" stroke-width="5" stroke-linecap="round"/>',
                f'<circle cx="{delta_x:.1f}" cy="{y + 18}" r="7" fill="{color}" stroke="#ffffff" stroke-width="2"/>',
                f'<text x="{left + plot_width + 18}" y="{y + 23}" font-family="Arial, sans-serif" font-size="12" fill="#172033">Δ={delta:.3f}</text>',
                f'<text x="{left + plot_width + 100}" y="{y + 23}" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a">CI [{ci_low:.3f}, {ci_high:.3f}]</text>',
            ]
        )
    lines.extend(
        [
            '<circle cx="32" cy="' + str(height - 48) + '" r="6" fill="#2f7d4f"/><text x="44" y="' + str(height - 44) + '" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a">candidate better</text>',
            '<circle cx="178" cy="' + str(height - 48) + '" r="6" fill="#b14b4b"/><text x="190" y="' + str(height - 44) + '" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a">baseline better/equal</text>',
            '<circle cx="348" cy="' + str(height - 48) + '" r="6" fill="#6f7785"/><text x="360" y="' + str(height - 44) + '" font-family="Arial, sans-serif" font-size="12" fill="#4c5a6a">CI crosses zero</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines)


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


def _multiplicity_plan(plan: ExperimentPlan, comparisons: list[MetricComparison]) -> dict[str, Any]:
    metrics = [item.metric for item in comparisons]
    planned = [metric for metric in plan.metrics if metric in set(metrics)]
    ci_crosses_zero = sum(1 for item in comparisons if item.ci_low <= 0 <= item.ci_high)
    stable_candidate_better = sum(1 for item in comparisons if item.direction == "candidate_better" and not (item.ci_low <= 0 <= item.ci_high))
    return {
        "schema_version": 1,
        "status": "pass" if comparisons else "no_comparisons",
        "family_size": len(comparisons),
        "primary_metrics": planned or metrics,
        "strategy": "Report all planned comparable metrics with 95% CI and effect sizes; do not cherry-pick a single favorable metric.",
        "adjustment_method": "CI-first estimation; no p-value multiplicity correction is applied because this report does not compute p-values.",
        "claim_boundary": "Broad superiority claims require preregistered direction and all primary CIs to avoid crossing zero; otherwise write metric-specific or negative/neutral claims.",
        "ci_crosses_zero": ci_crosses_zero,
        "stable_candidate_better": stable_candidate_better,
    }


def _power_analysis(repeats: int, comparisons: list[MetricComparison]) -> dict[str, Any]:
    mde = _minimum_detectable_standardized_effect(repeats)
    if not comparisons:
        status = "no_comparisons"
        interpretation = "No candidate/baseline comparisons were available, so no sensitivity profile can be computed."
    elif repeats < 3:
        status = "smoke_only"
        interpretation = "Fewer than three repeats per group supports only smoke-test interpretation."
    else:
        status = "profile_ready"
        interpretation = (
            "This is a sensitivity profile, not proof of adequate power; effects smaller than the approximate MDE "
            "should be treated as inconclusive unless supported by additional repeats or external evidence."
        )
    return {
        "schema_version": 1,
        "status": status,
        "per_group_repeats": repeats,
        "alpha": 0.05,
        "target_power": 0.80,
        "minimum_detectable_standardized_effect": mde,
        "method": "normal_approximation_two_group_difference",
        "interpretation": interpretation,
    }


def _minimum_detectable_standardized_effect(repeats: int) -> float | None:
    if repeats <= 0:
        return None
    # Approximate two-sided alpha=.05, 80% power threshold: (1.96 + 0.84) * sqrt(2 / n).
    return round(2.8 * math.sqrt(2 / repeats), 3)


def _short_metric(metric: str, max_chars: int = 30) -> str:
    if len(metric) <= max_chars:
        return metric
    return metric[: max_chars - 1].rstrip() + "…"


def _svg_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _find_group(results: list[ExperimentResult], tokens: list[str], role_lookup: dict[str, str] | None = None, role: str = "") -> list[ExperimentResult]:
    if role_lookup and role:
        group = [result for result in results if role_lookup.get(result.name) == role]
        if group:
            return group
    for token in tokens:
        group = [result for result in results if token in result.name.lower()]
        if group:
            return group
    return []


def _metric_values(results: list[ExperimentResult]) -> dict[str, list[float]]:
    metrics: dict[str, list[float]] = {}
    for result in results:
        for key, value in result.metrics.items():
            metrics.setdefault(key, []).append(float(value))
    return metrics


def _compatible_groups(
    candidate: list[ExperimentResult],
    baseline: list[ExperimentResult],
    group_lookup: dict[str, str],
) -> tuple[list[ExperimentResult], list[ExperimentResult], list[str]]:
    candidate_groups = {_result_group(result, group_lookup) for result in candidate}
    baseline_groups = {_result_group(result, group_lookup) for result in baseline}
    if len(candidate_groups) != 1 or len(baseline_groups) != 1 or candidate_groups != baseline_groups:
        return [], [], [
            "检测到不兼容的 adapter/dataset/split/task comparison_group，拒绝跨任务池化："
            f"candidate={sorted(candidate_groups)}; baseline={sorted(baseline_groups)}"
        ]
    candidate_adapters = {result.adapter_id or result.name for result in candidate}
    baseline_adapters = {result.adapter_id or result.name for result in baseline}
    if len(candidate_adapters) != 1 or len(baseline_adapters) != 1:
        return [], [], [
            "同一角色包含多个 adapter，当前报告不做跨 adapter 池化："
            f"candidate={sorted(candidate_adapters)}; baseline={sorted(baseline_adapters)}"
        ]
    return candidate, baseline, []


def _result_group(result: ExperimentResult, group_lookup: dict[str, str]) -> str:
    return result.comparison_group or group_lookup.get(result.name) or "default"


def _paired_results(
    candidate: list[ExperimentResult],
    baseline: list[ExperimentResult],
) -> tuple[list[tuple[ExperimentResult, ExperimentResult]], list[str]]:
    warnings: list[str] = []
    left = {result.repeat_index: result for result in candidate}
    right = {result.repeat_index: result for result in baseline}
    if len(left) != len(candidate) or len(right) != len(baseline):
        return [], ["同一角色存在重复 repeat_index，无法建立一对一配对。"]
    pairs: list[tuple[ExperimentResult, ExperimentResult]] = []
    for repeat_index in sorted(set(left) & set(right)):
        candidate_result = left[repeat_index]
        baseline_result = right[repeat_index]
        if not candidate_result.seed or not baseline_result.seed:
            warnings.append(f"repeat {repeat_index} 缺少 candidate/baseline seed，已排除。")
            continue
        if candidate_result.seed != baseline_result.seed:
            warnings.append(
                f"repeat {repeat_index} 的 candidate/baseline seed 不一致，已排除："
                f"{candidate_result.seed} != {baseline_result.seed}"
            )
            continue
        pairs.append((candidate_result, baseline_result))
    missing = sorted(set(left) ^ set(right))
    if missing:
        warnings.append("candidate/baseline 缺少配对 repeat_index：" + ", ".join(str(item) for item in missing[:10]))
    return pairs, warnings


def _pair_has_comparable_metric(
    pair: tuple[ExperimentResult, ExperimentResult],
    planned_metrics: set[str],
) -> bool:
    left, right = pair
    shared = set(left.metrics) & set(right.metrics)
    if planned_metrics:
        shared &= planned_metrics
    for metric in shared:
        try:
            if math.isfinite(float(left.metrics[metric])) and math.isfinite(float(right.metrics[metric])):
                return True
        except (TypeError, ValueError):
            continue
    return False


def _paired_metric_values(
    pairs: list[tuple[ExperimentResult, ExperimentResult]],
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    candidate: dict[str, list[float]] = {}
    baseline: dict[str, list[float]] = {}
    for left, right in pairs:
        for metric in sorted(set(left.metrics) & set(right.metrics)):
            try:
                left_value = float(left.metrics[metric])
                right_value = float(right.metrics[metric])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(left_value) or not math.isfinite(right_value):
                continue
            candidate.setdefault(metric, []).append(left_value)
            baseline.setdefault(metric, []).append(right_value)
    return candidate, baseline


def _compare_paired_metric(metric: str, candidate: list[float], baseline: list[float]) -> MetricComparison:
    deltas = [left - right for left, right in zip(candidate, baseline)]
    candidate_mean = _mean(candidate)
    baseline_mean = _mean(baseline)
    candidate_std = _sample_std(candidate)
    baseline_std = _sample_std(baseline)
    delta = _mean(deltas)
    delta_std = _sample_std(deltas)
    se = delta_std / math.sqrt(len(deltas)) if deltas else 0.0
    ci_low = delta - 1.96 * se
    ci_high = delta + 1.96 * se
    effect = None if delta_std == 0 else delta / delta_std
    lower_is_better = _lower_is_better(metric)
    better = delta < 0 if lower_is_better else delta > 0
    direction = "candidate_better" if better else "baseline_better_or_equal"
    if abs(delta) < 1e-12 and abs(ci_low) < 1e-12 and abs(ci_high) < 1e-12:
        interpretation = "candidate 与 baseline 在当前配对 repeat 下数值相同；零宽区间不支持显著性或稳定性结论。"
    elif ci_low <= 0 <= ci_high:
        interpretation = "配对差异区间跨过 0，需要更多重复实验确认。"
    elif better:
        interpretation = "candidate 在该指标的配对比较中优于 baseline。"
    else:
        interpretation = "candidate 在该指标的配对比较中未优于 baseline。"
    return MetricComparison(
        metric=metric,
        candidate_mean=round(candidate_mean, 6),
        baseline_mean=round(baseline_mean, 6),
        delta=round(delta, 6),
        ci_low=round(ci_low, 6),
        ci_high=round(ci_high, 6),
        candidate_std=round(candidate_std, 6),
        baseline_std=round(baseline_std, 6),
        effect_size=None if effect is None else round(effect, 6),
        direction=direction,
        interpretation=interpretation,
    )


def _compare_metric(metric: str, candidate: list[float], baseline: list[float]) -> MetricComparison:
    candidate_mean = _mean(candidate)
    baseline_mean = _mean(baseline)
    candidate_std = _sample_std(candidate)
    baseline_std = _sample_std(baseline)
    delta = candidate_mean - baseline_mean
    se = math.sqrt((candidate_std**2 / len(candidate)) + (baseline_std**2 / len(baseline))) if candidate and baseline else 0.0
    ci_low = delta - 1.96 * se
    ci_high = delta + 1.96 * se
    pooled = _pooled_std(candidate, baseline, candidate_std, baseline_std)
    effect = None if pooled == 0 else delta / pooled
    lower_is_better = _lower_is_better(metric)
    better = delta < 0 if lower_is_better else delta > 0
    direction = "candidate_better" if better else "baseline_better_or_equal"
    if abs(delta) < 1e-12 and abs(ci_low) < 1e-12 and abs(ci_high) < 1e-12:
        interpretation = "candidate 与 baseline 在当前重复下数值相同；零宽区间只表示这些 repeat 没有观测到差异，不支持显著性或稳定性结论。"
    elif ci_low <= 0 <= ci_high:
        interpretation = "差异跨过 0，需要更多重复实验确认。"
    elif better:
        interpretation = "candidate 在该指标上优于 baseline。"
    else:
        interpretation = "candidate 在该指标上未优于 baseline。"
    return MetricComparison(
        metric=metric,
        candidate_mean=round(candidate_mean, 6),
        baseline_mean=round(baseline_mean, 6),
        delta=round(delta, 6),
        ci_low=round(ci_low, 6),
        ci_high=round(ci_high, 6),
        candidate_std=round(candidate_std, 6),
        baseline_std=round(baseline_std, 6),
        effect_size=None if effect is None else round(effect, 6),
        direction=direction,
        interpretation=interpretation,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _pooled_std(candidate: list[float], baseline: list[float], candidate_std: float, baseline_std: float) -> float:
    degrees = len(candidate) + len(baseline) - 2
    if degrees <= 0:
        return 0.0
    pooled_variance = ((len(candidate) - 1) * candidate_std**2 + (len(baseline) - 1) * baseline_std**2) / degrees
    return math.sqrt(max(0.0, pooled_variance))


def _lower_is_better(metric: str) -> bool:
    lowered = metric.lower()
    tokens = ["time", "cost", "latency", "collision", "failure", "error", "risk", "耗时", "成本", "碰撞", "失败", "误差", "风险"]
    return any(token in lowered for token in tokens)
