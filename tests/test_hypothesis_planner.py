"""P1-B 测试：假设管理（证据门槛）+ 实验规划（形式检查/六维评分/批准门槛）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.agents.experiment_planner import SCORE_WEIGHTS, ExperimentPlanner, form_check, priority_score, score_candidate
from research_copilot.agents.hypothesis_agent import HypothesisManager
from research_copilot.core.models import ExperimentCandidate, ScoreDimension
from research_copilot.core.storage import ProjectStore
from research_copilot.integrations.llm import StubLLM

from tests.conftest import latency_rows, write_csv


@pytest.fixture()
def env(tmp_path: Path):
    store = ProjectStore(tmp_path / "data")
    project_id = store.create_project("假设与规划").id
    rows = latency_rows("baseline", n_queries=60) + latency_rows("paco", n_queries=60, scale=0.8)
    data_file = write_csv(tmp_path / "results.csv", rows)
    from research_copilot.integrations.material_importer import import_material

    import_material(store, project_id, "results", data_file, meta={"metric_directions": {"planning_time_s": "lower_is_better"}})
    from research_copilot.agents.diagnosis_agent import run_diagnosis

    run_diagnosis(store, project_id, llm=None)
    state = store.load_state(project_id)
    # 人工确认第一个 proposed 问题
    from research_copilot.core.research_state import confirm_question

    confirm_question(state, state.open_questions[0].id, rationale="值得研究")
    store.save_state(project_id, state)
    return store, project_id


def test_no_confirmed_question_blocks_generation(env):
    store, project_id = env
    # 全部退回 proposed
    state = store.load_state(project_id)
    for question in state.open_questions:
        question.status = "proposed"
    store.save_state(project_id, state)
    result = HypothesisManager(store, project_id).generate(llm=None)
    assert result["generated"] == []
    assert "confirmed" in result["note"]


def test_offline_hypotheses_from_alternative_explanations(env):
    store, project_id = env
    result = HypothesisManager(store, project_id).generate(llm=None)
    generated = result["generated"]
    assert generated, "离线发现带有竞争性解释，应能生成假设草稿"
    ids = [item["id"] for item in generated]
    hypotheses = store.load_hypotheses(project_id)
    by_id = {h.id: h for h in hypotheses}
    # 竞争假设互链
    first = by_id[ids[0]]
    assert first.competing_with
    assert all(cid in by_id for cid in first.competing_with)


def test_status_transition_requires_evidence(env):
    store, project_id = env
    manager = HypothesisManager(store, project_id)
    result = manager.generate(llm=None)
    hypothesis_id = result["generated"][0]["id"]
    with pytest.raises(ValueError, match="证据台账"):
        manager.set_status(hypothesis_id, "supported", rationale="感觉不错")
    manager.record_evidence(hypothesis_id, "supports", rationale="复现实验支持", ref_id="F-001")
    hypothesis = manager.set_status(hypothesis_id, "supported", rationale="复现实验支持")
    assert hypothesis.status == "supported"
    assert hypothesis.evidence_links


def test_human_override_flagged(env):
    store, project_id = env
    manager = HypothesisManager(store, project_id)
    result = manager.generate(llm=None)
    hypothesis_id = result["generated"][0]["id"]
    manager.record_evidence(hypothesis_id, "contradicts", rationale="对照实验矛盾")
    hypothesis = manager.set_status(hypothesis_id, "refuted", rationale="证据否定")
    assert hypothesis.human_override is True


def test_manual_hypothesis_add(env):
    store, project_id = env
    manager = HypothesisManager(store, project_id)
    hypothesis = manager.add_manual("Q-001", "人工假设：协调器是长尾来源", falsification_criteria="分模块计时显示协调器占比 <30%")
    assert hypothesis.origin == "human"
    assert hypothesis.human_override is True


def _candidate(**overrides) -> ExperimentCandidate:
    base = dict(
        id="EXP-001",
        question_id="Q-001",
        hypothesis_ids=["H-001", "H-002"],
        research_question="长尾来源是什么？",
        scientific_hypothesis="协调器是主要来源",
        competing_explanations=["单臂规划是主要来源"],
        design="相同查询与种子下分模块计时",
        controls=["相同场景", "相同随机种子", "相同硬件"],
        metrics=[{"name": "planning_time_s", "direction": "lower_is_better"}, {"name": "coordinator_share", "direction": "higher_is_better"}],
        expected_outcome="得到分模块耗时占比",
        falsification_condition="若单臂规划耗时占比 >70% 则否定协调器假设",
        cost_estimate="low",
    )
    base.update(overrides)
    return ExperimentCandidate(**base)


def test_form_check_four_required_fields():
    complete = _candidate()
    assert form_check(complete)["form_complete"] is True
    missing_falsification = _candidate(falsification_condition="")
    assert form_check(missing_falsification)["form_complete"] is False
    missing_direction = _candidate(metrics=[{"name": "x"}])
    assert form_check(missing_direction)["metrics_with_direction"] is False


def test_six_dimension_scoring_transparent():
    candidate = _candidate()
    scores = score_candidate(candidate, question_status="confirmed")
    names = [s.name for s in scores]
    assert set(names) == set(SCORE_WEIGHTS)
    for dimension in scores:
        assert 0 <= dimension.score <= 5
        assert dimension.rationale, "每维评分必须有依据"
    total = priority_score(scores)
    expected = sum(SCORE_WEIGHTS[d.name] * d.score for d in scores)
    assert abs(total - expected) < 1e-6
    # 高区分度方案应显著高于低区分度方案
    weak = score_candidate(_candidate(falsification_condition="", controls=[], metrics=[]), "proposed")
    assert priority_score(scores) > priority_score(weak)


def test_planner_offline_draft_needs_revision(env):
    store, project_id = env
    manager = HypothesisManager(store, project_id)
    manager.generate(llm=None)
    planner = ExperimentPlanner(store, project_id)
    result = planner.plan(llm=None)
    drafts = result["created"]
    assert drafts
    assert all(item["status"] == "needs_revision" for item in drafts)
    assert any(not item["form_check"]["form_complete"] for item in drafts)


def test_planner_llm_proposed_and_ranked(env):
    store, project_id = env
    manager = HypothesisManager(store, project_id)
    manager.generate(llm=None)
    answer = json.dumps(
        {
            "experiments": [
                {
                    "research_question": "长尾来源是什么？",
                    "scientific_hypothesis": "协调器是主要来源",
                    "competing_explanations": ["单臂规划是主要来源"],
                    "hypothesis_ids": ["H-001", "H-002"],
                    "design": "固定场景与随机种子，分模块计时（seed 固定）",
                    "controls": ["相同场景", "相同种子", "相同硬件"],
                    "metrics": [{"name": "coordinator_time_share", "direction": "higher_is_better"}],
                    "expected_outcome": "各模块耗时占比",
                    "falsification_condition": "单臂规划占比 >70% 时否定协调器假设",
                    "cost_estimate": "low",
                }
            ]
        },
        ensure_ascii=False,
    )
    planner = ExperimentPlanner(store, project_id)
    result = planner.plan(llm=StubLLM(responses={"planner": answer}))
    created = result["created"]
    assert created and created[0]["status"] == "proposed"
    assert created[0]["priority_score"] > 0


def test_approval_gate(env):
    store, project_id = env
    manager = HypothesisManager(store, project_id)
    manager.generate(llm=None)
    planner = ExperimentPlanner(store, project_id)
    result = planner.plan(llm=None)
    draft_id = result["created"][0]["id"]
    with pytest.raises(ValueError, match="形式检查"):
        planner.set_status(draft_id, "approved", actor="human")
