"""三层证据校验测试：L1 引用/失效、L2 数值重算、L3 因果降级、最终状态。"""
from __future__ import annotations

from pathlib import Path

import pytest

from research_copilot.analysis.evidence_validator import apply_validation, validate_finding
from research_copilot.core.evidence import sha256_file
from research_copilot.core.models import EvidenceRef, Finding, Material, NumericAssertion, Observation


@pytest.fixture()
def env(tmp_path: Path):
    data_file = tmp_path / "results.csv"
    data_file.write_text("query_id,time\n", encoding="utf-8")
    material = Material(
        id="MAT-001", kind="results", path=str(data_file), sha256=sha256_file(data_file), imported_at="t"
    )
    observation = Observation(
        id="OBS-001",
        statement="基线均值 10.0，候选 8.0",
        value={
            "baseline_mean": 10.0,
            "candidate_mean": 8.0,
            "lower_is_better": True,
            "interpretation": "candidate_better",
            "mean": 8.0,
            "median": 7.5,
            "percentiles": {"p95": 9.9},
        },
        evidence_refs=[EvidenceRef(material_id="MAT-001", sha256=material.sha256)],
    )
    return {
        "material": material,
        "materials_by_id": {"MAT-001": material},
        "observations_by_id": {"OBS-001": observation},
        "path": data_file,
    }


def _finding(env, statement: str, assertions: list[NumericAssertion] | None = None, hint: str = "statistical_finding") -> Finding:
    return Finding(
        id="F-001",
        statement=statement,
        claim_type=hint,
        claim_type_hint=hint,
        observation_ids=["OBS-001"],
        numeric_assertions=assertions or [],
    )


def test_l1_valid_refs_pass(env):
    finding = _finding(env, "候选均值低于基线", [NumericAssertion(metric="time", value="candidate_better", check="direction")])
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["l1"]["status"] == "pass"
    assert validation["status"] == "verified"
    assert validation["final_claim_type"] == "statistical_finding"


def test_l1_missing_observation_rejects(env):
    finding = _finding(env, "陈述")
    finding.observation_ids = ["OBS-404"]
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["status"] == "rejected"
    assert validation["final_claim_type"] == "unverified_conjecture"


def test_l1_stale_hash_blocks(env):
    finding = _finding(env, "陈述")
    env["path"].write_text("query_id,time\n1,2\n", encoding="utf-8")  # 数据被更新
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["status"] == "rejected"
    assert any("stale" in str(i) or "旧哈希" in str(i) for i in validation["l1"]["issues"])


def test_no_observation_citation_rejects(env):
    finding = _finding(env, "无引用的陈述")
    finding.observation_ids = []
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["status"] == "rejected"


def test_l2_percent_change_claiming_80_when_20_fails(env):
    # 用户给出的核心反例：基线 10.0 → 候选 8.0 是快 20%，声称快 80% 必须被拒
    finding = _finding(
        env,
        "Candidate 比 Baseline 快了 80%",
        [NumericAssertion(metric="time", value=80.0, unit="percent_improvement", check="percent_change_from_baseline", basis_observation="OBS-001")],
    )
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["l2"]["status"] == "fail"
    assert validation["final_claim_type"] == "unverified_conjecture"
    assert any("20" in str(issue) for issue in validation["l2"]["issues"])


def test_l2_correct_20_percent_passes(env):
    finding = _finding(
        env,
        "Candidate 比 Baseline 耗时降低 20%",
        [NumericAssertion(metric="time", value=20.0, unit="percent_change", check="percent_change_from_baseline", basis_observation="OBS-001")],
    )
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["l2"]["status"] == "pass"
    assert validation["status"] == "verified"


def test_l2_unverified_number_in_text(env):
    finding = _finding(env, "候选耗时降至 8.0 秒，P99 为 42.7 秒")  # 42.7 无依据
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["l2"]["status"] == "fail"
    assert any("42.7" in issue for issue in validation["l2"]["issues"])


def test_l3_causal_statement_downgraded_to_hypothesis(env):
    finding = _finding(env, "候选更快是因为采用了更好的采样策略")
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["final_claim_type"] == "hypothesis"
    assert validation["status"] == "downgraded"
    assert any("L3" in d for d in validation["downgrades"])


def test_l3_controlled_metadata_without_variables_is_insufficient(env):
    env["material"].meta["experiment_kind"] = "controlled"
    finding = _finding(env, "受控实验显示更好的采样策略导致更快")
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    assert validation["final_claim_type"] == "hypothesis"
    assert validation["status"] == "downgraded"


def test_apply_validation_mutates(env):
    finding = _finding(env, "因为机制 X 导致更快")
    validation = validate_finding(finding, env["observations_by_id"], env["materials_by_id"])
    apply_validation(finding, validation)
    assert finding.claim_type == "hypothesis"
    assert finding.validation["status"] == "downgraded"
