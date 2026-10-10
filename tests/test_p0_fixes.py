"""P0-1/P0-3/多表修复验证：A/B/C 公平性、C 自检闭环、每任务成本差值、多表结构保留。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.evaluation.baselines import (
    GROUP_RUNNERS,
    GroupBudget,
    _data_profile,
    _dataset_brief,
    _react_loop,
    compute_task_observations,
)
from research_copilot.evaluation.discoverybench_adapter import load_task_tables
from research_copilot.evaluation.metrics import aggregate_group
from research_copilot.evaluation.runner import run_evaluation
from research_copilot.evaluation.sandbox import ToolSandbox
from research_copilot.integrations.llm import StubLLM

from tests.conftest import latency_rows, write_csv


@pytest.fixture()
def bench_root(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "discoverybench" / "datasets" / "task-0001"
    write_csv(dataset_dir / "data.csv", latency_rows("baseline", n_queries=60, tail_ratio=0.0) + latency_rows("paco", n_queries=60, scale=0.8, tail_ratio=0.0))
    meta_path = tmp_path / "discoverybench" / "metadata" / "main" / "task-0001.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({"domain": "systems", "query": "paco 相对 baseline 耗时如何？", "hypothesis": "paco 更快（越低越好）", "dataset_dir": "datasets/task-0001"}),
        encoding="utf-8",
    )
    return tmp_path / "discoverybench"


def test_load_task_tables_preserves_structure(tmp_path: Path):
    """多表任务不得盲目合并：每张表独立保留 schema。"""
    task_dir = tmp_path / "task"
    write_csv(task_dir / "runs.csv", latency_rows("baseline", n_queries=20, tail_ratio=0.0))
    write_csv(task_dir / "meta.csv", [{"dataset": "runs", "license": "CC0", "version": 1}])
    task = type("T", (), {"task_id": "t", "dataset_dir": str(task_dir)})()
    tables = load_task_tables(task)
    assert [t["name"] for t in tables] == ["meta", "runs"]  # 排序后 meta 在前
    schemas = [set(_columns := list(t["rows"][0].keys()) if t["rows"] else []) for t in tables]
    assert schemas[0] != schemas[1], "两张 schema 不同的表必须保持独立"


def test_abc_share_same_loop_and_budget(bench_root: Path):
    """公平性：三组走同一 ReAct 循环、同一预算字段，差异仅在上下文。"""
    from research_copilot.evaluation.discoverybench_adapter import load_tasks

    task = load_tasks(bench_root, "main")[0]
    budget = GroupBudget(max_steps=4, max_tool_calls=3, timeout_s=30)
    captured = []

    class RecordingStub(StubLLM):
        def complete(self, system, user, purpose="", temperature=None):
            captured.append((purpose.split("_")[1] if "_" in purpose else purpose, user))
            return super().complete(system, user, purpose)

    answer = json.dumps({"hypothesis": "paco 更快", "variables": ["t"], "relationships": [], "mechanism": "数据不足以支持机制解释", "numeric_assertions": []}, ensure_ascii=False)
    llm = RecordingStub(responses={f"react_{g}_step_0": answer for g in "ABC"})
    for group in "ABC":
        captured.clear()
        GROUP_RUNNERS[group](llm, task, budget=budget, sandbox=ToolSandbox(task.dataset_dir, timeout_s=30))
        purpose, user = captured[0]
        assert purpose == group.lower()
    # A 只看到数据概要，看不到统计画像/诊断观测；B 看到画像；C 看到画像 + 观测
    captured.clear()
    GROUP_RUNNERS["A"](llm, task, budget=budget, sandbox=ToolSandbox(task.dataset_dir, timeout_s=30))
    a_context = captured[0][1]
    assert "数据集概要" in a_context and "column_stats" not in a_context and "诊断观测" not in a_context
    captured.clear()
    GROUP_RUNNERS["B"](llm, task, budget=budget, sandbox=ToolSandbox(task.dataset_dir, timeout_s=30))
    b_context = captured[0][1]
    assert "column_stats" in b_context and "诊断观测" not in b_context
    captured.clear()
    GROUP_RUNNERS["C"](llm, task, budget=budget, sandbox=ToolSandbox(task.dataset_dir, timeout_s=30))
    c_context = captured[0][1]
    assert "column_stats" in c_context and "诊断观测" in c_context


def test_group_c_self_check_corrective_round(bench_root: Path):
    """C 组证据闭环：数值断言复核失败 → 预算内带错误重答 → 自检记录在案。"""
    from research_copilot.evaluation.discoverybench_adapter import load_tasks

    task = load_tasks(bench_root, "main")[0]
    budget = GroupBudget(max_steps=6)
    bad_answer = json.dumps(
        {"hypothesis": "paco 快 80%", "variables": ["t"], "relationships": [], "mechanism": "数据不足以支持机制解释",
         "numeric_assertions": [{"metric": "planning_time_s", "value": 80.0, "check": "percent_change_from_baseline", "candidate_group": "paco", "baseline_group": "baseline"}]},
        ensure_ascii=False,
    )
    good_answer = json.dumps(
        {"hypothesis": "paco 快 20%", "variables": ["t"], "relationships": [], "mechanism": "数据不足以支持机制解释",
         "numeric_assertions": [{"metric": "planning_time_s", "value": 20.0, "check": "percent_change_from_baseline", "candidate_group": "paco", "baseline_group": "baseline"}]},
        ensure_ascii=False,
    )
    llm = StubLLM(responses={"react_c_step_0": bad_answer, "react_c_selfcheck": good_answer})
    result = GROUP_RUNNERS["C"](llm, task, budget=budget, sandbox=ToolSandbox(task.dataset_dir, timeout_s=30))
    assert result.ok
    assert result.self_check["corrective_round"] is True
    assert result.self_check["n_fail"] == 0, "修正后自检应通过"
    assert "20" in result.answer["hypothesis"]
    assert result.llm_calls == 2  # 初答 + 自检重答


def test_cost_delta_per_task_not_cumulative(bench_root: Path, tmp_path: Path):
    """每任务成本必须为差值：累计计数会被求和重复计算（审查发现）。"""
    from research_copilot.evaluation.discoverybench_adapter import load_tasks

    class CountingLLM(StubLLM):
        def __init__(self):
            super().__init__()
            self._tokens = 0

        def complete(self, system, user, purpose="", temperature=None):
            self._tokens += 100
            return super().complete(system, user, purpose)

        def usage_summary(self):
            return {"model": "stub", "total_calls": len(self.calls), "prompt_tokens": self._tokens, "completion_tokens": 0, "failed_calls": 0}

    task = load_tasks(bench_root, "main")[0]
    budget = GroupBudget(max_steps=3)
    llm = CountingLLM()
    llm.responses.update({f"react_{g.lower()}_step_0": json.dumps({"hypothesis": "h", "numeric_assertions": []}, ensure_ascii=False) for g in "ABC"})
    llm.responses.update(
        {
            "official_judge_context": "A) same",
            "official_judge_var": json.dumps({"sizeA": 1, "sizeB": 1, "intersection": 1, "explanation": "x"}),
            "official_judge_rel": json.dumps({"answer": "A) very similar", "explanation": "x"}),
        }
    )
    summary = run_evaluation(
        bench_root=bench_root, out_dir=tmp_path / "eval-runs", groups=["A", "B", "C"], limit=1,
        llm=llm, judge_llm=llm, budget=budget,
    )
    for group, agg in summary["group_summaries"].items():
        # 每任务 1 次调用、100 tokens（差值）；若误用累计值，三组相加会变成 (1+2+3)*100
        assert agg["total_llm_calls"] == 1, f"{group} 组的任务级调用数应为 1（差值计量）"
        assert agg["total_prompt_tokens"] == 100, f"{group} 组的任务级 token 应为 100（差值计量）"


def test_observations_include_relation_map(bench_root: Path):
    from research_copilot.evaluation.discoverybench_adapter import load_task_tables

    task = type("T", (), {"task_id": "t", "dataset_dir": str(bench_root / "datasets" / "task-0001"), "query": "q", "gold_hypothesis": "h", "domain": "", "source_path": "", "meta": {}})()
    tables = load_task_tables(task)
    observations = compute_task_observations(tables)
    kinds = {o["kind"] for o in observations}
    assert "group_comparison" in kinds
    assert "relation_map" in kinds  # 关系方向图（供 C 组/校验使用）


def test_data_profile_multi_table():
    tables = [
        {"name": "a", "rows": [{"x": 1.0}, {"x": 2.0}]},
        {"name": "b", "rows": [{"y": "s"}]},
    ]
    profile = json.loads(_data_profile(tables))
    assert [t["table"] for t in profile["tables"]] == ["a", "b"]
    brief = json.loads(_dataset_brief(tables))
    assert [t["table"] for t in brief["tables"]] == ["a", "b"]
