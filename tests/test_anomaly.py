"""异常检测测试：长尾定位、无异常不强造、混合状态、方向未声明。"""
from __future__ import annotations

from research_copilot.analysis.anomaly_detection import detect_anomalies, tail_report
from tests.conftest import latency_rows


def test_tail_detected_and_located():
    rows = latency_rows("paco", n_queries=120, tail_ratio=0.05, tail_multiplier=25.0)
    report = tail_report(rows, "planning_time_s")
    assert report["percentiles"]["p95"] is not None
    assert report["tail_share"] is not None and report["tail_share"] > 0.02
    assert report["outliers"], "必须定位到离群查询"
    assert report["outliers"][0]["locator"].endswith("q119")  # 尾部在 q114-q119
    candidates = detect_anomalies(rows, "planning_time_s")
    kinds = {c["kind"] for c in candidates}
    assert "tail_latency" in kinds


def test_no_anomaly_no_forced_findings():
    rows = latency_rows("paco", n_queries=120, tail_ratio=0.0)
    candidates = detect_anomalies(rows, "planning_time_s", {"planning_time_s": "lower_is_better"})
    assert candidates == [], "数据无异常时不得强行生成问题"


def test_mixed_status_reported():
    rows = latency_rows("paco", n_queries=50, timeout_ids={1, 2, 3, 4, 5})
    candidates = detect_anomalies(rows, "planning_time_s")
    kinds = [c["kind"] for c in candidates]
    assert "mixed_status" in kinds
    mixed = next(c for c in candidates if c["kind"] == "mixed_status")
    assert "timeout" in mixed["statement"]


def test_direction_unresolved_flagged():
    rows = latency_rows("paco", n_queries=120, tail_ratio=0.0)
    candidates = detect_anomalies(rows, "obscure_metric_abc", {})
    assert any(c["kind"] == "metric_direction_unresolved" for c in candidates)


def test_p99_not_reported_for_small_samples():
    rows = latency_rows("paco", n_queries=50, tail_ratio=0.06, tail_multiplier=40.0)
    report = tail_report(rows, "planning_time_s")
    assert report["percentiles"]["p99"] is None
    assert any("p99" in w for w in report["warnings"])
