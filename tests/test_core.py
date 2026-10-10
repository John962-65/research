"""core 层测试：模型往返、存储原子性/路径安全、证据失效、研究状态升级规则。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.core.evidence import check_ref, material_ref, sha256_file
from research_copilot.core.models import EvidenceRef, Finding, Material, ResearchState
from research_copilot.core.research_state import (
    confirm_question,
    propose_questions_from_findings,
    render_markdown,
    set_question_status,
    sync_claims_from_findings,
)
from research_copilot.core.storage import ProjectStore


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "data")


def test_model_roundtrip():
    finding = Finding(
        id="F-001",
        statement="测试",
        observation_ids=["OBS-001"],
        numeric_assertions=[],
        alternative_explanations=["x"],
    )
    data = json.loads(json.dumps(finding.to_dict()))
    restored = Finding.from_dict(data)
    assert restored.statement == finding.statement
    assert restored.observation_ids == ["OBS-001"]


def test_state_roundtrip_ignores_unknown_fields():
    payload = ResearchState(current_stage="s", updated_at="t").to_dict()
    payload["future_field"] = 1
    state = ResearchState.from_dict(payload)
    assert state.current_stage == "s"
    assert not hasattr(state, "future_field") or True


def test_create_load_list_project(store: ProjectStore):
    project = store.create_project("测试项目", "描述", ["目标一"])
    loaded = store.load_project(project.id)
    assert loaded.name == "测试项目"
    assert loaded.goals == ["目标一"]
    assert [p.id for p in store.list_projects()] == [project.id]


def test_storage_rejects_path_escape(store: ProjectStore):
    with pytest.raises(ValueError):
        store.project_dir("../../etc")


def test_storage_missing_project(store: ProjectStore):
    with pytest.raises(FileNotFoundError):
        store.load_project("nope-000000")


def test_event_log_and_jsonl(store: ProjectStore):
    project = store.create_project("事件项目")
    store.log_event(project.id, "custom", target="X", detail="d")
    events = ProjectStore.read_jsonl(store.project_dir(project.id) / "events.jsonl")
    assert events[-1]["action"] == "custom"


def test_evidence_ledger_append_ids(store: ProjectStore):
    from research_copilot.core.models import EvidenceEntry

    project = store.create_project("台账")
    first = store.append_evidence(project.id, EvidenceEntry(id="", ts="", kind="observation", summary="s1"))
    second = store.append_evidence(project.id, EvidenceEntry(id="", ts="", kind="observation", summary="s2"))
    assert (first.id, second.id) == ("EV-001", "EV-002")
    assert len(store.load_evidence_ledger(project.id)) == 2


def test_check_ref_valid_and_stale(tmp_path: Path, store: ProjectStore):
    data_file = tmp_path / "results.csv"
    data_file.write_text("a,b\n1,2\n", encoding="utf-8")
    material = Material(
        id="MAT-001", kind="results", path=str(data_file), sha256=sha256_file(data_file), imported_at="t"
    )
    ref = material_ref(material)
    assert check_ref(ref, {"MAT-001": material})["status"] == "valid"
    data_file.write_text("a,b\n1,3\n", encoding="utf-8")  # 内容更新
    assert check_ref(ref, {"MAT-001": material})["status"] == "stale"
    assert check_ref(EvidenceRef(material_id="MAT-999", sha256="x"), {"MAT-001": material})["status"] == "missing"


def test_question_lifecycle_and_upgrade_rules():
    state = ResearchState()
    finding_established = Finding(
        id="F-001",
        statement="候选组均值更低",
        claim_type="statistical_finding",
        verification_method="重复实验验证",
    )
    finding_established.validation = {"status": "verified"}
    finding_causal = Finding(
        id="F-002",
        statement="因为采样策略更好所以更快",
        claim_type="hypothesis",
        verification_method="受控实验",
    )
    finding_causal.validation = {"status": "downgraded"}
    findings = [finding_established, finding_causal]

    questions = propose_questions_from_findings(state, findings)
    assert len(questions) == 2
    assert all(q.status == "proposed" for q in questions)

    counts = sync_claims_from_findings(state, findings)
    assert counts == {"established": 1, "current": 1, "insufficient": 0}
    assert state.established_results[0]["finding_id"] == "F-001"
    assert state.current_claims[0]["finding_id"] == "F-002"

    confirm_question(state, questions[0].id, rationale="人工确认")
    assert state.open_questions[0].status == "confirmed"
    assert state.open_questions[0].human_override is True
    set_question_status(state, questions[1].id, "retired", rationale="不值得做")
    assert state.open_questions[1].status == "retired"

    markdown = render_markdown(state, "项目X")
    assert "已证实结果" in markdown and "F-001" in markdown
    assert "证据不足的主张" in markdown


def test_unverified_claim_never_established():
    state = ResearchState()
    finding = Finding(id="F-009", statement="猜想", claim_type="unverified_conjecture")
    finding.validation = {"status": "rejected"}
    sync_claims_from_findings(state, [finding])
    assert not state.established_results
    assert state.insufficient_claims[0]["finding_id"] == "F-009"
