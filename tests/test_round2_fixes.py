"""第二轮修复验证：观测打包 / .dta 支持 / 金标-数据分歧诊断。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.analysis.anomaly_detection import compact_direction_noise, detect_anomalies
from research_copilot.analysis.statistics import relation_signs
from research_copilot.evaluation.baselines import OBSERVATION_PRIORITY, pack_observations
from research_copilot.evaluation.official_scoring import OfficialProtocolScorer
from research_copilot.integrations.llm import StubLLM
from research_copilot.integrations.material_importer import read_rows

from tests.conftest import latency_rows, write_csv


def test_direction_noise_merged_into_one():
    rows = latency_rows("paco", n_queries=60, tail_ratio=0.0)
    findings: list[dict] = []
    for metric in ("mystery_a", "mystery_b", "mystery_c"):
        findings.extend(detect_anomalies(rows, metric))
    assert len([f for f in findings if f["kind"] == "metric_direction_unresolved"]) == 3
    merged = compact_direction_noise(findings)
    unresolved = [f for f in merged if f["kind"] == "metric_direction_unresolved"]
    assert len(unresolved) == 1
    assert len(unresolved[0]["value"]["metrics"]) == 3
    assert merged[-1]["kind"] == "metric_direction_unresolved"  # 噪声排在最后


def test_pack_observations_priority_and_truncation():
    observations = [
        {"kind": "metric_direction_unresolved", "statement": "noise1", "value": {}},
        {"kind": "relation_map", "statement": "relations", "value": {"relations": []}},
        {"kind": "tail_latency", "statement": "tail", "value": {}},
        {"kind": "group_comparison", "statement": "comp", "value": {}},
        {"kind": "metric_direction_unresolved", "statement": "noise2", "value": {}},
    ]
    packed = pack_observations(observations, budget_chars=100000)
    order = [o["statement"] for o in json.loads(packed)]
    assert order == ["comp", "relations", "tail", "noise1", "noise2"]  # 优先级排序
    tiny = pack_observations(observations, budget_chars=250)
    parsed = json.loads(tiny.rsplit("（", 1)[0])
    kinds = [o["kind"] for o in parsed]
    assert "group_comparison" in kinds and "relation_map" in kinds, "超预算时高优先级观测必须保留"
    assert "metric_direction_unresolved" not in kinds, "超预算时噪声必须先被丢弃"
    assert "截断" in tiny


def test_relation_signs_sorted_by_abs_r():
    rows = [{"a": float(i), "b": 0.5 * i, "c": float(30 - i), "d": 0.01 * (i % 3)} for i in range(40)]
    relations = relation_signs(rows, ["d", "a", "b", "c"])
    r_values = [abs(rel["pearson_r"]) for rel in relations]
    assert r_values == sorted(r_values, reverse=True), "必须按 |r| 降序（信息量优先）"
    assert relations[0]["sign"] in ("positive", "negative")


def test_dta_support(tmp_path: Path):
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": ["a", "b", "c"]})
    dta_path = tmp_path / "data.dta"
    frame.to_stata(str(dta_path), write_index=False)
    rows = read_rows(dta_path)
    assert len(rows) == 3
    assert rows[0]["x"] == 1.0 and rows[0]["y"] == "a"
    # 数值列探测/摘要正常
    from research_copilot.integrations.material_importer import summarize_rows

    summary = summarize_rows(rows)
    assert "x" in summary["numeric_columns"]


def test_divergence_check_diagnostic_only():
    judge = StubLLM(default=json.dumps({"divergence": True, "reason": "gold says none, data shows r=0.42"}, ensure_ascii=False))
    scorer = OfficialProtocolScorer(judge)
    result = scorer.divergence_check("q?", "no association", json.dumps([{"a": "x", "b": "y", "sign": "positive", "pearson_r": 0.42}]))
    assert result["divergence"] is True
    assert result["diagnostic_only"]
    broken = StubLLM(default="无法解析")
    result2 = OfficialProtocolScorer(broken).divergence_check("q?", "g", "[]")
    assert result2["divergence"] is None  # 解析失败如实置 None


@pytest.fixture()
def bench_root(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "discoverybench" / "datasets" / "task-0001"
    write_csv(dataset_dir / "data.csv", latency_rows("baseline", n_queries=60, tail_ratio=0.0) + latency_rows("paco", n_queries=60, scale=0.8, tail_ratio=0.0))
    meta_path = tmp_path / "discoverybench" / "metadata" / "main" / "task-0001.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps({"domain": "systems", "query": "q?", "hypothesis": "gold", "dataset_dir": "datasets/task-0001"}),
        encoding="utf-8",
    )
    return tmp_path / "discoverybench"


def test_runner_records_divergence(bench_root: Path, tmp_path: Path):
    """runner 在正式模式记录每任务分歧诊断（stub judge：divergence=false）。"""
    summary = run_evaluation_with_stub(bench_root, tmp_path)
    # summary 即 config 的超集（**config 展开）
    assert summary["divergence_checks"], "必须记录分歧诊断"
    for check in summary["divergence_checks"].values():
        assert check.get("divergence") in (True, False, None)


def run_evaluation_with_stub(bench_root: Path, tmp_path: Path):
    from research_copilot.evaluation.runner import run_evaluation

    answer = json.dumps({"hypothesis": "h（stub）", "numeric_assertions": []}, ensure_ascii=False)
    llm = StubLLM(responses={f"react_{g}_step_0": answer for g in "abc"})
    llm.responses.update(
        {
            "official_judge_context": "A) same",
            "official_judge_var": json.dumps({"sizeA": 1, "sizeB": 1, "intersection": 1, "explanation": "x"}),
            "official_judge_rel": json.dumps({"answer": "A) very similar", "explanation": "x"}),
            "divergence_check": json.dumps({"divergence": False, "reason": "stub"}, ensure_ascii=False),
        }
    )
    return run_evaluation(
        bench_root=bench_root, out_dir=tmp_path / "eval-runs", groups=["A", "B", "C"], limit=1,
        llm=llm, judge_llm=llm,
    )
