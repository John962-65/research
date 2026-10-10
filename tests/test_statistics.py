"""统计分析测试：方向声明优先、配对（按查询）、分位数告警、重复测量、状态感知、混杂画像。"""
from __future__ import annotations

import pytest

from research_copilot.analysis.statistics import (
    aggregate_per_query,
    compare_metric,
    describe,
    group_profile,
    group_report,
    percentile,
    resolve_direction,
    split_by_status,
    two_mean_ci,
)
from tests.conftest import latency_rows


def test_direction_declared_overrides_heuristic():
    # 声明方向必须覆盖名称启发式/缺省（旧仓库 robot 案例的教训）
    lower, declared = resolve_direction("mean_iterations", {"mean_iterations": "lower_is_better"})
    assert lower is True and declared is True
    # 无 token 命中时缺省为 lower，但声明 higher_is_better 必须反转
    default_lower, default_declared = resolve_direction("obscure_metric_x")
    assert default_declared is False and default_lower is True
    override_lower, override_declared = resolve_direction("obscure_metric_x", {"obscure_metric_x": "higher_is_better"})
    assert override_declared is True and override_lower is False


def test_percentile_small_sample_warning():
    values = [float(i) for i in range(15)]
    report = describe(values, "x")
    assert report["percentiles"]["p90"] is not None
    assert report["percentiles"]["p95"] is None
    assert any("p95" in w for w in report["warnings"])


def test_percentile_exact_values():
    values = [float(i) for i in range(1, 101)]  # 1..100
    assert percentile(values, 50) == 50.5
    assert percentile(values, 95) == 95.05
    assert percentile(values, 99) == 99.01


def test_repeats_are_aggregated_not_treated_independent():
    rows = latency_rows("paco", n_queries=10, repeats=3)
    values, n_queries, n_repeats, warnings = aggregate_per_query(rows, "planning_time_s")
    assert n_queries == 10 and n_repeats == 30 and len(values) == 10
    assert any("重复测量" in w for w in warnings)


def test_split_status_counts_non_success():
    rows = latency_rows("paco", n_queries=20, timeout_ids={1, 2, 3})
    success_rows, counts = split_by_status(rows)
    assert counts == {"success": 17, "timeout": 3}
    assert len(success_rows) == 17


def test_paired_comparison_by_query_with_declared_direction():
    baseline = latency_rows("baseline", n_queries=100, scale=1.0, tail_ratio=0.0)
    candidate = latency_rows("paco", n_queries=100, scale=0.8, tail_ratio=0.0)
    rows = baseline + candidate
    comparison = compare_metric(
        rows, "planning_time_s", "paco", "baseline", {"planning_time_s": "lower_is_better"}
    )
    assert comparison["paired"] is True
    assert comparison["n_pairs"] == 100
    assert comparison["direction_declared"] is True
    # candidate 快 20%：delta = 候选-基线 = -0.2*base 均值，CI 不跨 0 → candidate_better
    assert comparison["interpretation"] == "candidate_better"
    assert abs(comparison["delta_mean"] + 0.2 * comparison["baseline"]["mean"]) < 1e-6


def test_direction_not_reversed_when_declared_lower_is_better():
    # 旧 robot 案例场景：迭代次数 candidate 107 vs baseline 267（越低越好）
    rows = []
    for q in range(100):
        rows.append({"query_id": f"q{q}", "comparison_group": "baseline", "status": "success", "mean_iterations": 267.0, "seed": 1, "repeat_index": 0})
        rows.append({"query_id": f"q{q}", "comparison_group": "paco", "status": "success", "mean_iterations": 107.65, "seed": 1, "repeat_index": 0})
    comparison = compare_metric(rows, "mean_iterations", "paco", "baseline", {"mean_iterations": "lower_is_better"})
    assert comparison["interpretation"] == "candidate_better"  # 修复前会误判 baseline_better_or_equal


def test_small_sample_group_difference_reports_uncertainty():
    baseline = latency_rows("baseline", n_queries=6, scale=1.0, tail_ratio=0.0)
    candidate = latency_rows("paco", n_queries=6, scale=0.95, tail_ratio=0.0)  # 差异 5%
    comparison = compare_metric(baseline + candidate, "planning_time_s", "paco", "baseline")
    # 配对设计下一致的小差异可判 candidate_better，但必须携带小样本告警（不确定性不丢失）
    assert comparison["n_pairs"] == 6
    assert any("样本少" in w for w in comparison["warnings"])


def test_heuristic_direction_warns_when_undeclared():
    baseline = latency_rows("baseline", n_queries=50, tail_ratio=0.0)
    candidate = latency_rows("paco", n_queries=50, scale=0.8, tail_ratio=0.0)
    comparison = compare_metric(baseline + candidate, "planning_time_s", "paco", "baseline", None)
    assert comparison["direction_declared"] is False
    assert any("未声明" in w or "启发式" in w for w in comparison.get("warnings", []))


def test_excluded_rows_reported_not_hidden():
    baseline = latency_rows("baseline", n_queries=50, timeout_ids={0, 1})
    candidate = latency_rows("paco", n_queries=50, timeout_ids={5})
    comparison = compare_metric(baseline + candidate, "planning_time_s", "paco", "baseline")
    assert comparison["excluded_rows"]["baseline"]["excluded"] == {"timeout": 2}
    assert comparison["excluded_rows"]["paco"]["excluded"] == {"timeout": 1}
    assert comparison["excluded_rows"]["baseline"]["n_queries"] == 48


def test_group_report_and_confounder_profile():
    # 混杂：candidate 组的 arm_count 系统性更大
    def scenario(q):
        return "hard" if q % 3 == 0 else "easy"

    baseline = latency_rows("baseline", n_queries=60, tail_ratio=0.0, scenario_fn=scenario)
    candidate = latency_rows("paco", n_queries=60, tail_ratio=0.0, scenario_fn=scenario)
    for row in candidate:
        row["arm_count"] = row["arm_count"] + 3  # 混杂因素（均值 4 vs 7，差异 >30%）
    rows = baseline + candidate
    report = group_report(rows, "planning_time_s", group_field="scenario")
    assert set(report["groups"]) == {"easy", "hard"}
    profile = group_profile(rows, ["arm_count"], "comparison_group")
    assert profile["imbalance_warnings"], "协变量不均衡必须产生混杂警告"


def test_two_mean_ci_contains_delta():
    cand = [1.0 + 0.01 * i for i in range(40)]
    base = [2.0 + 0.01 * i for i in range(40)]
    lo, hi = two_mean_ci(cand, base)
    assert lo < 0 and hi < 0
