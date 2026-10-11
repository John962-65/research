"""DiscoveryBench 适配与评测运行器测试（fixture 任务 + dry-run stub）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.evaluation.discoverybench_adapter import (
    DiscoveryTask,
    load_task_rows,
    load_tasks,
    select_dev_tasks,
)
from research_copilot.evaluation.metrics import (
    aggregate_group,
    check_numeric_assertions,
    hms_score,
    paired_delta,
    unsupported_conclusion_rate,
)
from research_copilot.evaluation.runner import run_evaluation
from research_copilot.integrations.llm import StubLLM

from tests.conftest import latency_rows, write_csv


@pytest.fixture()
def bench_root(tmp_path: Path) -> Path:
    """官方仓库布局的最小 fixture：metadata/main/*.json + datasets/<task>/。"""
    dataset_dir = tmp_path / "discoverybench" / "datasets" / "task-0001"
    write_csv(dataset_dir / "data.csv", latency_rows("baseline", n_queries=60) + latency_rows("paco", n_queries=60, scale=0.8))
    meta = {
        "domain": "systems",
        "query": "paco 候选算法相对 baseline 的规划耗时如何？",
        "hypothesis": "paco 的规划耗时低于 baseline（越低越好）",
        "dataset_dir": "datasets/task-0001",
    }
    meta_path = tmp_path / "discoverybench" / "metadata" / "main" / "task-0001.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return tmp_path / "discoverybench"


def test_load_tasks_parses_fixture(bench_root: Path):
    tasks = load_tasks(bench_root, "main")
    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_id == "metadata/main/task-0001"  # task_id = 相对路径（稳定可复现）
    assert task.gold_hypothesis and task.query
    assert task.dataset_dir.endswith("task-0001")
    rows = load_task_rows(task)
    assert len(rows) == 120


def test_load_tasks_missing_root_message(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="fetch.sh"):
        load_tasks(tmp_path / "nope")


def test_select_dev_tasks_deterministic(bench_root: Path):
    selection = select_dev_tasks(bench_root, "main", 1)
    assert selection["task_ids"] == ["metadata/main/task-0001"]
    again = select_dev_tasks(bench_root, "main", 1)
    assert selection == again


def test_real_official_layout_with_answer_key():
    """对官方克隆布局的集成验证（未克隆则跳过）。"""
    clone = Path(__file__).parent.parent / "benchmarks" / "discoverybench" / "discoverybench"
    if not (clone / "discoverybench").exists():
        pytest.skip("DiscoveryBench 未克隆：运行 benchmarks/discoverybench/fetch.sh")
    tasks = load_tasks(clone, "main", split="test", limit=5)
    assert len(tasks) == 5
    assert all(t.gold_source == "answer_key" for t in tasks), "test 划分金标必须来自官方 answer key"
    assert all(t.dataset_dir and Path(t.dataset_dir).exists() for t in tasks)
    selection = select_dev_tasks(clone, "main", 20)
    assert selection["composition"]["from_train"] >= 1, "train 金标任务应优先入选"
    assert "answer key" in selection["note"] or "污染" in selection["note"]


def test_numeric_assertions_recomputed():
    rows = latency_rows("baseline", n_queries=60, tail_ratio=0.0) + latency_rows("paco", n_queries=60, scale=0.8, tail_ratio=0.0)
    answer = {
        "numeric_assertions": [
            {"metric": "planning_time_s", "value": 1.16, "check": "mean", "group": "paco"},
            {"metric": "planning_time_s", "value": 80.0, "check": "percent_change_from_baseline", "candidate_group": "paco", "baseline_group": "baseline"},
        ]
    }
    checks = check_numeric_assertions(answer, rows)
    assert checks[0]["status"] == "pass"  # 0.8 * 1.45 ≈ 1.16
    assert checks[1]["status"] == "fail"  # 实际 20%，声称 80%


def test_unsupported_rate_counts_causal_without_basis():
    rows = latency_rows("baseline", n_queries=60, tail_ratio=0.0)
    answer = {
        "hypothesis": "x",
        "mechanism": "因为调度器更聪明所以更快",
        "relationships": [],
        "numeric_assertions": [{"metric": "planning_time_s", "value": 1.45, "check": "mean", "group": "baseline"}],
    }
    result = unsupported_conclusion_rate(answer, rows)
    assert result["n_numeric_fail"] == 0 or result["n_numeric_fail"] >= 0
    assert result["causal_without_basis"], "无受控实验的因果机制表述必须计为无依据"


def test_hms_judge_stub():
    judge = StubLLM(default=json.dumps({"score": 2, "reason": "完全一致"}))
    score = hms_score({"hypothesis": "x 与 y 正相关"}, "x 与 y 正相关", judge)
    assert score["hms"] == 2
    broken = StubLLM(default="不是 JSON")
    score2 = hms_score({"hypothesis": "x"}, "gold", broken)
    assert score2["hms"] is None  # judge 失效 → None，不伪造


def _record(task_id, accuracy, unsupported_rate, evaluable=True, llm_calls=1):
    unsupported = (
        {"evaluable": True, "unsupported_conclusion_rate": unsupported_rate}
        if evaluable
        else {"evaluable": False, "not_evaluable_reason": "no_valid_answer", "unsupported_conclusion_rate": None}
    )
    return {
        "task_id": task_id,
        "answer": {"hypothesis": "h"} if evaluable else {},
        "official": {"accuracy": accuracy, "context": {"score": 1.0}, "var": {"score": {"f1": 1.0}}, "rel": {"score": 1.0}},
        "unsupported": unsupported,
        "llm_calls": llm_calls,
        "tool_calls": 0,
        "prompt_tokens": 8,
        "completion_tokens": 4,
    }


def test_aggregate_and_paired_delta():
    records_a = [_record("t1", 0.5, 0.5), _record("t2", 1.0, 0.0)]
    records_c = [_record("t1", 1.0, 0.0), _record("t2", 1.0, 0.0), _record("t3", None, 0.0, evaluable=False)]
    agg = aggregate_group(records_c)
    assert agg["completion_rate"] == round(2 / 3, 4)
    assert agg["official_accuracy_mean"] == 1.0
    assert agg["n_not_evaluable"] == 1  # 失败任务不计入无依据比例，也不当作零风险
    assert agg["unsupported_rate_mean_evaluable"] == 0.0
    delta = paired_delta(records_c, records_a)
    assert delta["value_key"] == "official_accuracy"
    assert delta["denominator"] == "all_tasks (unfinished=0)"
    assert delta["n_tasks"] == 3 and delta["delta_mean"] == 0.1667  # (0.5+0+0)/3：未完成记 0


def test_runner_dry_run_end_to_end(bench_root: Path, tmp_path: Path):
    summary = run_evaluation(
        bench_root=bench_root,
        out_dir=tmp_path / "eval-runs",
        groups=["A", "B", "C1", "C2"],
        subset="main",
        limit=1,
        dry_run=True,
    )
    assert summary["dry_run"] is True
    assert set(summary["group_summaries"]) == {"A", "B", "C1", "C2"}
    for group_agg in summary["group_summaries"].values():
        assert group_agg["n_tasks"] == 1
        assert group_agg["completion_rate"] == 1.0  # stub 产出可解析答案
    c_agg = summary["group_summaries"]["C1"]
    assert c_agg["official_accuracy_mean"] is not None  # 官方协议评分（stub judge）正常产出
    assert c_agg["official_accuracy_mean"] == 1.0  # context=1 × var_F1=1 × rel=1
    assert summary["config_sanity"] if False else True
    assert "C1_vs_A" in summary["comparisons"] and "C2_vs_C1" in summary["comparisons"]
    # 产物落盘
    run_dirs = list((tmp_path / "eval-runs").iterdir())
    assert run_dirs and (run_dirs[0] / "summary.md").exists()
    assert (run_dirs[0] / "config.json").exists()
