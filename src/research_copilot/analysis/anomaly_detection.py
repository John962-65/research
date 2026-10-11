"""异常与长尾检测（确定性规则，产出候选观测；无异常时返回空，不强造问题）。"""
from __future__ import annotations

import math
from typing import Any

from .statistics import (
    PERCENTILE_MIN_N,
    aggregate_per_query,
    percentile,
    split_by_status,
)


def _row_locator(row: dict[str, Any], index: int, query_field: str) -> str:
    if query_field in row and row.get(query_field) not in (None, ""):
        return f"{query_field}={row.get(query_field)}"
    return f"row#{index}"


def tail_report(
    rows: list[dict[str, Any]],
    metric: str,
    query_field: str = "query_id",
    status_field: str = "status",
) -> dict[str, Any]:
    """长尾报告：分位数、尾部占比、IQR 离群与极端倍数行（带定位）。

    仅统计成功行；非成功行计数单列。分位数样本不足时置 None 并告警。
    """
    success_rows, status_counts = split_by_status(rows, status_field)
    values, n_queries, n_repeats, agg_warnings = aggregate_per_query(success_rows, metric, query_field)
    report: dict[str, Any] = {
        "metric": metric,
        "n_independent": n_queries,
        "n_repeats": n_repeats,
        "status_counts": status_counts,
        "percentiles": {},
        "tail_share": None,
        "outliers": [],
        "warnings": list(agg_warnings),
    }
    if not values:
        report["warnings"].append("无可用成功样本")
        return report

    for q in (90, 95, 99):
        min_n = PERCENTILE_MIN_N[q]
        if n_queries >= min_n:
            report["percentiles"][f"p{q}"] = percentile(values, q)
        else:
            report["percentiles"][f"p{q}"] = None
            report["warnings"].append(f"p{q} 样本不足（独立样本 n={n_queries} < {min_n}）：不报告精确值")

    p50 = percentile(values, 50)
    p95 = report["percentiles"]["p95"]
    if p95 is not None:
        tail_rows = [v for v in values if v > p95]
        report["tail_share"] = len(tail_rows) / len(values)

    # IQR 离群（聚合后）
    q1, q3 = percentile(values, 25), percentile(values, 75)
    iqr = q3 - q1
    upper_fence = q3 + 1.5 * iqr if iqr > 0 else None
    # 定位离群行：用成功行原始数据（按查询键或行号）
    locator_values: list[tuple[str, float]] = []
    for index, row in enumerate(success_rows):
        try:
            locator_values.append((_row_locator(row, index, query_field), float(row.get(metric))))
        except (TypeError, ValueError):
            continue
    if upper_fence is not None:
        report["outliers"] = [
            {"locator": loc, "value": val, "rule": "iqr_upper_fence", "fence": upper_fence}
            for loc, val in sorted(locator_values, key=lambda item: -item[1])
            if val > upper_fence
        ][:20]
    # 极端倍数行（>10 倍中位数）
    if p50 > 0:
        report["extreme_ratio_rows"] = [
            {"locator": loc, "value": val, "ratio_vs_median": val / p50}
            for loc, val in sorted(locator_values, key=lambda item: -item[1])
            if val > 10 * p50
        ][:20]
    else:
        report["extreme_ratio_rows"] = []
    return report


def detect_anomalies(
    rows: list[dict[str, Any]],
    metric: str,
    metric_directions: dict[str, str] | None = None,
    query_field: str = "query_id",
    status_field: str = "status",
) -> list[dict[str, Any]]:
    """从单表数据检测候选异常。无异常返回空列表——调用方不得强行生成问题。

    检测项：
    1. tail_latency：p95 可用且尾部占比 >2%，且存在离群行；
    2. mixed_status：存在失败/超时行，提示不得只分析成功样本；
    3. metric_direction_unresolved：指标方向既未声明也无法由名称推断。
    """
    findings: list[dict[str, Any]] = []
    report = tail_report(rows, metric, query_field, status_field)

    if (
        report["percentiles"].get("p95") is not None
        and report["tail_share"] is not None
        and report["tail_share"] > 0.02
        and (report["outliers"] or report["extreme_ratio_rows"])
    ):
        worst = (report["outliers"] or report["extreme_ratio_rows"])[0]
        findings.append(
            {
                "kind": "tail_latency",
                "statement": (
                    f"指标 {metric} 存在长尾：尾部占比 {report['tail_share']:.1%}（>P95），"
                    f"最重样本 {worst['locator']} 值 {worst['value']:.4g}"
                ),
                "value": {
                    "p95": report["percentiles"]["p95"],
                    "p50": percentile([v for v in _success_values(rows, metric, query_field)], 50),
                    "tail_share": report["tail_share"],
                    "top_outliers": (report["outliers"] or report["extreme_ratio_rows"])[:5],
                },
                "computed_by": "anomaly_detection.detect_anomalies",
            }
        )

    failed = {k: v for k, v in report["status_counts"].items() if k not in ("success", "passed", "ok", "done", "true", "1")}
    if failed:
        findings.append(
            {
                "kind": "mixed_status",
                "statement": (
                    f"数据混合了非成功状态 {failed}：以下统计仅基于成功样本，"
                    "结论必须同时报告失败/超时情况，不得只引用成功部分"
                ),
                "value": {"status_counts": report["status_counts"]},
                "computed_by": "anomaly_detection.detect_anomalies",
            }
        )

    from .statistics import resolve_direction

    _, declared = resolve_direction(metric, metric_directions)
    lowered = metric.lower()
    heuristic_hit = any(t in lowered for t in ("time", "cost", "latency", "success", "rate", "score"))
    if not declared and not heuristic_hit:
        findings.append(
            {
                "kind": "metric_direction_unresolved",
                "statement": f"指标 {metric} 的优劣方向未声明且无法由名称推断：解释前必须先声明方向",
                "value": {"metric": metric},
                "computed_by": "anomaly_detection.detect_anomalies",
            }
        )
    return findings


def compact_direction_noise(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把逐指标的 metric_direction_unresolved 噪声合并为一条摘要观测。

    修复 2026-10 评测发现：宽表任务中方向未声明提示逐条出现，把关系图/组间比较
    挤出上下文截断窗口。合并后噪声只占一条，且排在最后。
    """
    unresolved = [f for f in findings if f.get("kind") == "metric_direction_unresolved"]
    rest = [f for f in findings if f.get("kind") != "metric_direction_unresolved"]
    if len(unresolved) <= 1:
        return findings
    metrics = [str(f.get("value", {}).get("metric")) for f in unresolved]
    merged = {
        "kind": "metric_direction_unresolved",
        "statement": f"{len(metrics)} 个指标的优劣方向未声明且无法由名称推断：{', '.join(metrics[:12])}"
        + ("…" if len(metrics) > 12 else "")
        + "；解释这些指标前请先声明方向",
        "value": {"metrics": metrics},
        "computed_by": "anomaly_detection.compact_direction_noise",
    }
    return rest + [merged]


def detect_anomalies_compact(
    rows: list[dict[str, Any]],
    metric: str,
    metric_directions: dict[str, str] | None = None,
    query_field: str = "query_id",
    status_field: str = "status",
) -> list[dict[str, Any]]:
    """detect_anomalies 的紧凑变体：方向未声明噪声合并为单条。"""
    return compact_direction_noise(
        detect_anomalies(rows, metric, metric_directions, query_field, status_field)
    )


def _success_values(rows: list[dict[str, Any]], metric: str, query_field: str) -> list[float]:
    success_rows, _ = split_by_status(rows)
    values, _, _, _ = aggregate_per_query(success_rows, metric, query_field)
    return values
