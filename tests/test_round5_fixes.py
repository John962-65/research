"""第五轮修复验证：C1 标签 / 失败五分类 / 结构化分析声明 / bootstrap CI / 快照只读 / fail-closed。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.evaluation.baselines import GROUP_RUNNERS, classify_failure
from research_copilot.evaluation.metrics import (
    _bootstrap_cluster_ci,
    aggregate_group,
    check_numeric_assertions,
)
from research_copilot.evaluation.sandbox import ToolSandbox
from tests.conftest import latency_rows, write_csv


def test_c1_group_label_consistent():
    """审查 P1-1：结果对象内 group 标签必须与执行组一致。"""
    result = _run_minimal("C1")
    assert result.group == "C1"
    for group in ("A", "B", "C1", "C2"):
        assert _run_minimal(group).group == group


def _run_minimal(group: str):
    import tempfile

    from research_copilot.evaluation.baselines import GroupBudget
    from research_copilot.evaluation.discoverybench_adapter import DiscoveryTask
    from research_copilot.evaluation.sandbox import ToolSandbox
    from research_copilot.integrations.llm import StubLLM

    tmp = Path(tempfile.mkdtemp())
    write_csv(tmp / "data.csv", latency_rows("baseline", n_queries=30, tail_ratio=0.0))
    task = DiscoveryTask(task_id="t/x/data/m0", query="q?", gold_hypothesis="g", dataset_dir=str(tmp))
    answer = json.dumps({"hypothesis": "h", "numeric_assertions": []}, ensure_ascii=False)
    llm = StubLLM(responses={f"react_{group.lower()}_step_0": answer})
    runner = GROUP_RUNNERS[group]
    return runner(llm, task, budget=GroupBudget(max_steps=3), sandbox=ToolSandbox(tmp, timeout_s=30))


def test_classify_failure_five_classes():
    assert classify_failure("", {}, [{"kind": "tool"}], 6, 6) == "tool_loop_exhausted"
    assert classify_failure("", {}, [{"kind": "unparseable"}], 2, 6) == "output_parse_failure"
    assert classify_failure("LLM 调用失败: HTTP 500", {}, [], 1, 6) == "transport_failure"
    assert classify_failure("", {"variables": ["x"]}, [], 1, 6) == "invalid_final_answer"
    assert classify_failure("", {"hypothesis": "h"}, [], 1, 6) == ""
    assert classify_failure("SSL: EOF", {}, [{"kind": "tool"}], 2, 6) == "transport_failure"


def test_structured_analysis_regression(tmp_path: Path):
    rows = [{"SES": float(i) / 10, "BMI": 20 + float(i) / 10} for i in range(100)]
    answer = {"numeric_assertions": [
        {"metric": "beta_SES", "value": 1.0, "check": "ols_beta",
         "analysis": {"analysis_type": "regression", "dependent_variable": "BMI",
                      "independent_variables": ["SES"], "controls": [], "filters": {}, "reported_variable": "SES"},
         "basis": "声明式回归"},
    ]}
    checks = check_numeric_assertions(answer, rows)
    assert checks[0]["status"] == "pass" and abs(checks[0]["expected"] - 1.0) < 1e-6


def test_structured_analysis_group_diff_and_correlation(tmp_path: Path):
    rows = latency_rows("baseline", n_queries=60, tail_ratio=0.0) + latency_rows("paco", n_queries=60, scale=0.8, tail_ratio=0.0)
    answer = {"numeric_assertions": [
        {"metric": "diff", "value": -0.29, "check": "group_diff",
         "analysis": {"analysis_type": "group_diff", "column": "planning_time_s",
                      "group_field": "comparison_group", "candidate_group": "paco", "baseline_group": "baseline"}},
        {"metric": "corr", "value": 1.0, "check": "correlation",
         "analysis": {"analysis_type": "correlation", "x": "planning_time_s", "y": "planning_time_s"}},
    ]}
    checks = check_numeric_assertions(answer, rows)
    assert checks[0]["status"] == "pass", checks[0]
    assert checks[1]["status"] == "pass" and abs(checks[1]["expected"] - 1.0) < 1e-9  # 自相关=1


def test_structured_analysis_group_mean(tmp_path: Path):
    rows = latency_rows("baseline", n_queries=60, tail_ratio=0.0)
    answer = {"numeric_assertions": [
        {"metric": "mean_b", "value": rows[0]["planning_time_s"] + 0.1, "check": "group_mean",
         "analysis": {"analysis_type": "group_mean", "column": "planning_time_s",
                      "group_field": "comparison_group", "group": "baseline"}},
    ]}
    checks = check_numeric_assertions(answer, rows)
    assert checks[0]["status"] in ("pass", "fail") and "expected" in checks[0]


def test_bootstrap_cluster_ci_clamped():
    by_dataset = {"d1": [1.0] * 5, "d2": [1.0] * 5, "d3": [1.0] * 5}
    ci = _bootstrap_cluster_ci(by_dataset)
    assert ci == (1.0, 1.0)  # 全 1.0 → 钳位后仍 [1,1]，不越界
    by_mixed = {"d1": [0.0] * 3, "d2": [1.0] * 3}
    ci2 = _bootstrap_cluster_ci(by_mixed)
    assert 0.0 <= ci2[0] and ci2[1] <= 1.0


def test_aggregate_full_task_score_and_failures():
    records = [
        {"task_id": "t/x/d1/m0", "answer": {"hypothesis": "h"}, "official": {"accuracy": 1.0},
         "unsupported": {"evaluable": True, "unsupported_conclusion_rate": 0.0}, "llm_calls": 1},
        {"task_id": "t/x/d2/m0", "answer": {}, "error": "未在步数预算内", "failure_class": "tool_loop_exhausted",
         "official": {}, "unsupported": {"evaluable": False}, "llm_calls": 6},
    ]
    agg = aggregate_group(records)
    assert agg["full_task_score_mean"] == 0.5, "未完成任务记 0：全任务分母口径"
    assert agg["failure_breakdown"] == {"tool_loop_exhausted": 1}


def test_sandbox_snapshot_protects_original(tmp_path: Path):
    """审查 P0-3：agent 代码只能改快照，原数据完整性保持。"""
    data = tmp_path / "data"
    data.mkdir()
    write_csv(data / "data.csv", latency_rows("g", n_queries=10))
    original = (data / "data.csv").read_text(encoding="utf-8")
    sandbox = ToolSandbox(data, timeout_s=60)
    outcome = sandbox.run_python("open('data.csv','w').write('TAMPERED')")
    assert outcome["ok"]
    assert (data / "data.csv").read_text(encoding="utf-8") == original, "原始数据必须不可被 agent 修改"
    sandbox.close()


def test_sandbox_fail_closed_without_bwrap(monkeypatch):
    """审查 P0-3：隔离不可用时默认拒绝执行（fail-closed）。"""
    import research_copilot.evaluation.sandbox as sb

    monkeypatch.setattr(sb, "build_bwrap_command", lambda *a, **k: None)
    sandbox = sb.ToolSandbox(None, network_isolation=False)  # 默认 allow_unsafe_fallback=False
    outcome = sandbox.run_python("print(1)")
    assert outcome["ok"] is False and outcome.get("fail_closed") is True
