"""P1 修复验证：关系主张校验（方向错误不升级）+ 多轮诊断 ID/历史引用稳定。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.agents.diagnosis_agent import run_diagnosis
from research_copilot.analysis.evidence_validator import apply_validation, validate_finding
from research_copilot.analysis.statistics import relation_sign, relation_signs
from research_copilot.core.models import (
    EvidenceRef,
    Finding,
    Material,
    Observation,
    RelationClaim,
)
from research_copilot.core.evidence import sha256_file
from research_copilot.core.research_state import sync_claims_from_findings
from research_copilot.core.storage import ProjectStore
from research_copilot.integrations.material_importer import import_material

from tests.conftest import latency_rows, write_csv


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "data")


def test_relation_sign_computation():
    assert relation_sign(0.5) == "positive"
    assert relation_sign(-0.3) == "negative"
    assert relation_sign(0.01) == "none"
    assert relation_sign(None) == "unverifiable"
    rows = [{"x": float(i), "y": 2.0 * i + 1.0} for i in range(30)]
    relations = relation_signs(rows, ["x", "y"])
    assert relations[0]["sign"] == "positive"


def _obs_with_relations(obs_id: str, sign: str, material: Material) -> Observation:
    return Observation(
        id=obs_id,
        statement="关系图观测",
        value={"relations": [{"a": "x", "b": "y", "pearson_r": 0.8 if sign == "positive" else -0.8, "sign": sign, "n": 50}]},
        evidence_refs=[EvidenceRef(material_id=material.id, sha256=material.sha256)],
    )


@pytest.fixture()
def material(tmp_path: Path) -> Material:
    data_file = tmp_path / "r.csv"
    data_file.write_text("x,y\n1,2\n", encoding="utf-8")
    return Material(id="MAT-001", kind="results", path=str(data_file), sha256=sha256_file(data_file), imported_at="t")


def _finding(material: Material, relation: str, obs: Observation) -> Finding:
    return Finding(
        id="F-001",
        statement=f"x 与 y 呈{relation}相关",
        claim_type="statistical_finding",
        observation_ids=[obs.id],
        claims=[RelationClaim(variable_a="x", variable_b="y", relation=relation, basis_observation=obs.id)],
    )


def test_wrong_relation_direction_downgraded(material: Material):
    obs = _obs_with_relations("OBS-001", "positive", material)
    finding = _finding(material, "negative", obs)  # 数据为正，声称负
    validation = validate_finding(finding, {"OBS-001": obs}, {material.id: material})
    assert validation["l2"]["relation_failed"] is True
    assert validation["final_claim_type"] == "unverified_conjecture"
    assert validation["status"] == "downgraded"


def test_correct_relation_direction_verified(material: Material):
    obs = _obs_with_relations("OBS-001", "positive", material)
    finding = _finding(material, "positive", obs)
    validation = validate_finding(finding, {"OBS-001": obs}, {material.id: material})
    assert validation["status"] == "verified"


def test_unverifiable_relation_needs_human_review_not_established(material: Material):
    # 观测里没有该变量对的相关计算 → 不能自动升级为已证实结果
    obs = Observation(
        id="OBS-001",
        statement="无关观测",
        value={"mean": 1.0},
        evidence_refs=[EvidenceRef(material_id=material.id, sha256=material.sha256)],
    )
    finding = _finding(material, "positive", obs)
    validation = validate_finding(finding, {"OBS-001": obs}, {material.id: material})
    assert validation["status"] == "needs_human_review"
    assert any("人工复核" in d for d in validation["downgrades"])
    # 同步进研究状态：不得进入已证实桶
    from research_copilot.core.models import ResearchState
    from research_copilot.core.research_state import sync_claims_from_findings

    state = ResearchState()
    counts = sync_claims_from_findings(state, [finding])
    assert counts["established"] == 0
    assert counts["insufficient"] == 1


def test_controlled_experiment_requires_variable_overlap(material: Material):
    material.meta["experiment_kind"] = "controlled"
    material.meta["intervention_variables"] = ["temperature"]
    obs = _obs_with_relations("OBS-001", "positive", material)
    finding = _finding(material, "positive", obs)
    finding.statement = "因为温度机制导致 x 与 y 正相关"
    validation = validate_finding(finding, {"OBS-001": obs}, {material.id: material})
    # 受控实验存在，但干预变量 temperature 与主张变量 x/y 无交集 → 仍然降级
    assert validation["final_claim_type"] == "hypothesis"
    # 干预变量覆盖主张变量时才放行
    material.meta["intervention_variables"] = ["x"]
    validation2 = validate_finding(finding, {"OBS-001": obs}, {material.id: material})
    assert validation2["final_claim_type"] == "statistical_finding"
    apply_validation(finding, validation2)
    assert finding.validation["status"] == "verified"


def test_three_consecutive_diagnoses_keep_history_refs(store: ProjectStore, tmp_path: Path):
    """P1-2 核心验收：三轮诊断（数据演变）后，第一轮确认的问题仍指向原始发现与材料。"""
    project_id = store.create_project("历史引用").id

    # 第一轮：candidate 快 20%
    rows1 = latency_rows("baseline", n_queries=120, tail_ratio=0.0) + latency_rows("paco", n_queries=120, scale=0.8, tail_ratio=0.0)
    data_file = write_csv(tmp_path / "results.csv", rows1)
    material = import_material(store, project_id, "results", data_file, meta={"metric_directions": {"planning_time_s": "lower_is_better"}})
    report1 = run_diagnosis(store, project_id, llm=None)
    assert report1["diag_id"] == "DIAG-0001"
    original_finding = report1["findings"][0]
    original_finding_id = original_finding["id"]
    assert original_finding_id.startswith("DIAG-0001/")

    state = store.load_state(project_id)
    question_id = state.open_questions[0].id
    question_finding_ref = state.open_questions[0].finding_ids[0]
    from research_copilot.core.research_state import confirm_question

    confirm_question(state, question_id, rationale="第一轮确认")
    store.save_state(project_id, state)

    # 第二轮：数据被替换（candidate 变慢）→ 新发现
    rows2 = latency_rows("baseline", n_queries=120, tail_ratio=0.0) + latency_rows("paco", n_queries=120, scale=1.5, tail_ratio=0.0)
    write_csv(Path(material.path), rows2)
    # 材料内容变了 → 旧哈希失效，需重新登记新版本材料（真实流程：导入新材料）
    material2 = import_material(store, project_id, "results", data_file, meta={"metric_directions": {"planning_time_s": "lower_is_better"}})
    report2 = run_diagnosis(store, project_id, llm=None, material_ids=[material2.id])
    assert report2["diag_id"] == "DIAG-0002"
    # 旧观测/旧发现不被覆盖：两轮 ID 前缀不同
    all_findings = store.load_findings(project_id)
    prefixes = {f.id.split("/")[0] for f in all_findings}
    assert prefixes == {"DIAG-0001", "DIAG-0002"}

    # 第三轮：再次诊断，确认无 ID 冲突
    report3 = run_diagnosis(store, project_id, llm=None, material_ids=[material2.id])
    assert report3["diag_id"] == "DIAG-0003"
    assert len(store.load_observations(project_id)) == report1["n_observations"] + report2["n_observations"] + report3["n_observations"]

    # 第一轮确认的研究问题仍指向第一轮的原始发现（ID 与内容都不变）
    state_final = store.load_state(project_id)
    target = next(q for q in state_final.open_questions if q.id == question_id)
    assert target.finding_ids == [question_finding_ref]
    assert target.finding_ids[0] == original_finding_id
    original_still = next(f for f in all_findings if f.id == original_finding_id)
    assert original_still.statement == original_finding["statement"]
