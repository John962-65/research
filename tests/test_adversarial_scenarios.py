"""对抗性合成场景（用户指定的 8 个期望行为，逐一验收）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.agents.diagnosis_agent import run_diagnosis
from research_copilot.analysis.evidence_validator import validate_finding
from research_copilot.analysis.statistics import compare_metric, describe
from research_copilot.core.models import EvidenceRef, Finding, Material, NumericAssertion, Observation
from research_copilot.core.evidence import sha256_file
from research_copilot.core.storage import ProjectStore
from research_copilot.integrations.material_importer import import_material

from tests.conftest import latency_rows, write_csv


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "data")


def _import(store, project_id, tmp_path, name, rows, directions=None):
    data_file = write_csv(tmp_path / name, rows)
    return import_material(store, project_id, "results", data_file, meta={"metric_directions": directions or {}})


def test_scenario_1_no_anomaly_no_forced_findings(store, tmp_path):
    project_id = store.create_project("S1 无异常").id
    _import(store, project_id, tmp_path, "clean.csv", latency_rows("only", n_queries=120, tail_ratio=0.0))
    report = run_diagnosis(store, project_id, llm=None)
    assert report["n_findings"] == 0
    assert report["n_questions_proposed"] == 0


def test_scenario_2_small_sample_reports_uncertainty(store, tmp_path):
    baseline = latency_rows("baseline", n_queries=6, tail_ratio=0.0)
    candidate = latency_rows("paco", n_queries=6, scale=0.93, tail_ratio=0.0)
    comparison = compare_metric(baseline + candidate, "planning_time_s", "paco", "baseline")
    assert comparison["n_pairs"] == 6
    assert any("样本少" in w for w in comparison["warnings"]), "小样本必须给出不确定性告警"
    # 离线诊断不应把小样本差异升级为发现（不确定性不被写成结论）
    project_id = store.create_project("S2 小样本").id
    _import(store, project_id, tmp_path, "small.csv", baseline + candidate, {"planning_time_s": "lower_is_better"})
    report = run_diagnosis(store, project_id, llm=None)
    assert report["n_findings"] == 0


def test_scenario_3_extreme_tail_locates_samples(store, tmp_path):
    rows = latency_rows("paco", n_queries=120, tail_ratio=0.05, tail_multiplier=40.0)
    project_id = store.create_project("S3 极端长尾").id
    _import(store, project_id, tmp_path, "tail.csv", rows, {"planning_time_s": "lower_is_better"})
    report = run_diagnosis(store, project_id, llm=None)
    tail_observations = [o for o in report["observations"] if o["computed_by"].startswith("anomaly_detection") and "长尾" in o["statement"]]
    assert tail_observations
    assert tail_observations[0]["value"]["top_outliers"]
    assert tail_observations[0]["value"]["top_outliers"][0]["locator"].endswith("q119")


def test_scenario_4_confounder_blocks_attribution(store, tmp_path):
    def scenario(q):
        return "hard" if q % 2 == 0 else "easy"

    baseline = latency_rows("baseline", n_queries=80, tail_ratio=0.0, scenario_fn=scenario)
    candidate = latency_rows("paco", n_queries=80, tail_ratio=0.0, scenario_fn=scenario)
    for row in candidate:
        row["arm_count"] = row["arm_count"] + 3  # candidate 组混杂更多机械臂
    project_id = store.create_project("S4 混杂").id
    _import(store, project_id, tmp_path, "confounded.csv", baseline + candidate, {"planning_time_s": "lower_is_better"})
    report = run_diagnosis(store, project_id, llm=None)
    covariate_observations = [o for o in report["observations"] if o["computed_by"] == "statistics.group_profile"]
    assert covariate_observations, "必须暴露协变量不均衡"
    assert any("混杂" in o["statement"] for o in covariate_observations)
    # 同时：LLM 式因果归因陈述必须被降级（校验器层面）
    material = store.load_materials(project_id)[0]
    observation = Observation(
        id="OBS-900",
        statement="候选更快",
        value={"baseline_mean": 10.0, "candidate_mean": 8.0},
        evidence_refs=[EvidenceRef(material_id=material.id, sha256=material.sha256)],
    )
    finding = Finding(
        id="F-900",
        statement="算法在更多机械臂场景下带来提升是因为其采样策略更好",
        observation_ids=["OBS-900"],
        numeric_assertions=[],
    )
    validation = validate_finding(finding, {"OBS-900": observation}, {material.id: material})
    assert validation["final_claim_type"] == "hypothesis"


def test_scenario_5_mean_improves_but_worst_case_reported(store, tmp_path):
    # 候选均值更低，但最差情况（max）反而更差 → 描述统计必须同时呈现两者
    baseline = latency_rows("baseline", n_queries=120, scale=1.0, tail_ratio=0.0)
    candidate = latency_rows("paco", n_queries=120, scale=0.85, tail_ratio=0.05, tail_multiplier=3.0)
    rows = baseline + candidate
    comparison = compare_metric(rows, "planning_time_s", "paco", "baseline")
    assert comparison["candidate"]["mean"] < comparison["baseline"]["mean"]
    assert comparison["candidate"]["max"] > comparison["baseline"]["max"], "最差情况变差必须可见"
    assert comparison["direction_declared"] is False or comparison["interpretation"] in ("candidate_better", "no_clear_difference")
    project_id = store.create_project("S5 均值与最差").id
    _import(store, project_id, tmp_path, "mixed.csv", rows, {"planning_time_s": "lower_is_better"})
    report = run_diagnosis(store, project_id, llm=None)
    tail_observations = [o for o in report["observations"] if "长尾" in o["statement"]]
    assert tail_observations, "均值改善但存在长尾时必须报告尾部风险"


def test_scenario_6_direction_lower_is_better_not_reversed(store, tmp_path):
    # 复现旧仓库 robot 案例的教训：迭代数 candidate 107.65 vs baseline 267.55
    rows = []
    for q in range(100):
        rows.append({"query_id": f"q{q:03d}", "comparison_group": "baseline", "status": "success", "mean_iterations": 267.55, "seed": 1000 + q, "repeat_index": 0})
        rows.append({"query_id": f"q{q:03d}", "comparison_group": "paco", "status": "success", "mean_iterations": 107.65, "seed": 1000 + q, "repeat_index": 0})
    comparison = compare_metric(rows, "mean_iterations", "paco", "baseline", {"mean_iterations": "lower_is_better"})
    assert comparison["interpretation"] == "candidate_better"
    project_id = store.create_project("S6 方向").id
    _import(store, project_id, tmp_path, "iter.csv", rows, {"mean_iterations": "lower_is_better"})
    report = run_diagnosis(store, project_id, llm=None)
    findings = [f for f in report["findings"] if "mean_iterations" in json.dumps(f)]
    assert findings, "方向已声明且差异显著时应产生发现"
    assert any("candidate_better" in f["statement"] for f in findings)


def test_scenario_7_success_and_timeout_both_reported(store, tmp_path):
    baseline = latency_rows("baseline", n_queries=60, timeout_ids={1, 2})
    candidate = latency_rows("paco", n_queries=60, timeout_ids={3, 4, 5})
    project_id = store.create_project("S7 混合状态").id
    _import(store, project_id, tmp_path, "mixed.csv", baseline + candidate, {"planning_time_s": "lower_is_better"})
    report = run_diagnosis(store, project_id, llm=None)
    mixed = [o for o in report["observations"] if "timeout" in o["statement"]]
    assert mixed, "超时情况必须出现在观测中"
    comparison = [o for o in report["observations"] if o["computed_by"] == "statistics.compare_metric"]
    assert comparison
    excluded = comparison[0]["value"]["excluded_rows"]
    assert excluded["baseline"]["excluded"] == {"timeout": 2}
    assert excluded["paco"]["excluded"] == {"timeout": 3}


def test_scenario_8_tampered_evidence_blocks_upgrade(store, tmp_path):
    project_id = store.create_project("S8 篡改").id
    material = _import(store, project_id, tmp_path, "r.csv", latency_rows("paco", n_queries=120, tail_ratio=0.0))
    # 导入后篡改内容
    original = Path(material.path)
    rows = latency_rows("paco", n_queries=120, scale=0.1, tail_ratio=0.0)
    write_csv(original, rows)
    # 基于旧哈希的发现必须被拒绝
    observation = Observation(
        id="OBS-001",
        statement="x",
        value={"mean": 1.0},
        evidence_refs=[EvidenceRef(material_id=material.id, sha256=material.sha256)],
    )
    finding = Finding(id="F-001", statement="均值 1.0", observation_ids=["OBS-001"], numeric_assertions=[NumericAssertion(metric="m", value=1.0, check="mean")])
    validation = validate_finding(finding, {"OBS-001": observation}, {material.id: material})
    assert validation["status"] == "rejected"
    assert validation["final_claim_type"] == "unverified_conjecture"
    # 诊断同样跳过过期材料
    report = run_diagnosis(store, project_id, llm=None)
    assert report["skipped_materials"]
