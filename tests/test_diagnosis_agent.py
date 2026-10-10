"""诊断 Agent 端到端测试（离线 + stub LLM + 证据失效跳过）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.agents.diagnosis_agent import run_diagnosis
from research_copilot.core.storage import ProjectStore
from research_copilot.integrations.llm import StubLLM
from research_copilot.integrations.material_importer import import_material

from tests.conftest import latency_rows, manifest, write_csv


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "data")


def _import_results(store: ProjectStore, project_id: str, tmp_path: Path, name: str = "results.csv", **kwargs):
    rows = latency_rows(**kwargs)
    data_file = write_csv(tmp_path / name, rows)
    manifest(tmp_path / "manifest.json", {"planning_time_s": "lower_is_better", "success_rate": "higher_is_better"})
    return import_material(store, project_id, "results", data_file)


def test_offline_diagnosis_finds_tail_and_comparison(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("长尾诊断").id
    baseline = latency_rows("baseline", n_queries=120, scale=1.0, tail_ratio=0.0)
    candidate = latency_rows("paco", n_queries=120, scale=0.8, tail_ratio=0.05, tail_multiplier=25.0)
    data_file = write_csv(tmp_path / "results.csv", baseline + candidate)
    manifest(tmp_path / "manifest.json", {"planning_time_s": "lower_is_better"})
    import_material(store, project_id, "results", data_file)

    report = run_diagnosis(store, project_id, llm=None)
    assert report["llm_mode"] == "offline"
    assert report["n_observations"] > 0
    kinds = {f["claim_type"] for f in report["findings"]}
    # 离线模式：方向已声明、样本充足且 CI 明确 → statistical_finding
    assert "statistical_finding" in kinds
    findings_text = json.dumps(report["findings"], ensure_ascii=False)
    # 候选组带极端长尾 → 均值比较如实判为 baseline_better_or_equal（不被长尾掩盖，也不反向粉饰）
    assert "baseline_better_or_equal" in findings_text
    # 长尾被单独检出并定位（尾部在候选组）
    tail_observations = [o for o in report["observations"] if "长尾" in o["statement"] and "paco" in o["statement"]]
    assert tail_observations
    # 提出了待研究问题且全部 proposed
    state = store.load_state(project_id)
    assert state.open_questions
    assert all(q.status == "proposed" for q in state.open_questions)


def test_offline_clean_data_no_forced_findings(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("干净数据").id
    rows = latency_rows("only", n_queries=120, tail_ratio=0.0)
    data_file = write_csv(tmp_path / "clean.csv", rows)
    import_material(store, project_id, "results", data_file)
    report = run_diagnosis(store, project_id, llm=None)
    # 无组间比较、无异常 → 不产生发现与问题（观测可以有，如方向未声明的提示）
    assert report["n_findings"] == 0
    assert report["n_questions_proposed"] == 0


def _minimal_rows(scale_base=1.0, scale_cand=0.8):
    rows = []
    for q in range(120):
        base = (1.0 + 0.1 * (q % 10)) * scale_base
        rows.append({"query_id": f"q{q:03d}", "comparison_group": "baseline", "seed": 1000 + q, "repeat_index": 0, "status": "success", "planning_time_s": round(base, 4)})
        rows.append({"query_id": f"q{q:03d}", "comparison_group": "paco", "seed": 1000 + q, "repeat_index": 0, "status": "success", "planning_time_s": round(base * scale_cand / scale_base, 4)})
    return rows


def test_stub_llm_finding_with_wrong_number_gets_downgraded(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("幻觉数字").id
    data_file = write_csv(tmp_path / "results.csv", _minimal_rows())
    manifest(tmp_path / "manifest.json", {"planning_time_s": "lower_is_better"})
    import_material(store, project_id, "results", data_file)

    llm = StubLLM(
        responses={
            "diagnosis": json.dumps(
                {
                    "findings": [
                        {
                            "statement": "Candidate 比 Baseline 快了 80%，因为调度策略更好",
                            "claim_type_hint": "statistical_finding",
                            "observation_ids": ["DIAG-0001/OBS-003"],
                            "numeric_assertions": [
                                {
                                    "metric": "planning_time_s",
                                    "value": 80.0,
                                    "check": "percent_change_from_baseline",
                                    "basis_observation": "DIAG-0001/OBS-003",
                                }
                            ],
                            "alternative_explanations": ["调度策略更好"],
                            "verification_method": "受控计时实验",
                            "confidence": "high",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        }
    )
    report = run_diagnosis(store, project_id, llm=llm)
    finding = report["findings"][0]
    assert finding["claim_type"] == "unverified_conjecture"  # 80% vs 实际 20%：L2 拒绝
    assert any("L2" in d for d in finding["validation"]["downgrades"])


def test_stub_llm_honest_finding_passes_and_question_proposed(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("诚实LLM").id
    data_file = write_csv(tmp_path / "results.csv", _minimal_rows())
    manifest(tmp_path / "manifest.json", {"planning_time_s": "lower_is_better"})
    import_material(store, project_id, "results", data_file)

    llm = StubLLM(
        responses={
            "diagnosis": json.dumps(
                {
                    "findings": [
                        {
                            "statement": "Candidate 在全部查询上耗时比 Baseline 低 20%（置信区间不包含零）",
                            "claim_type_hint": "statistical_finding",
                            "observation_ids": ["DIAG-0001/OBS-003"],
                            "numeric_assertions": [
                                {
                                    "metric": "planning_time_s",
                                    "value": 20.0,
                                    "check": "percent_change_from_baseline",
                                    "basis_observation": "DIAG-0001/OBS-003",
                                }
                            ],
                            "alternative_explanations": ["场景分布不均（已由协变量画像排除/提示）"],
                            "verification_method": "在固定场景与种子下重复对照",
                            "confidence": "high",
                            "confidence_rationale": "方向已声明、配对 CI 明确",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        }
    )
    report = run_diagnosis(store, project_id, llm=llm)
    finding = report["findings"][0]
    assert finding["claim_type"] == "statistical_finding"
    assert finding["validation"]["status"] == "verified"
    assert report["n_questions_proposed"] >= 1


def test_stale_material_skipped_not_used(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("过期材料").id
    material = _import_results(store, project_id, tmp_path, group="paco", n_queries=60)
    # 材料导入后被篡改（模拟数据更新）
    write_csv(Path(material.path), latency_rows("tampered", n_queries=60, scale=9.9))
    report = run_diagnosis(store, project_id, llm=None)
    assert report["skipped_materials"]
    assert report["skipped_materials"][0]["status"] == "stale"
    assert report["n_observations"] == 0


def test_diagnosis_report_files_written(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("报告落盘").id
    _import_results(store, project_id, tmp_path, group="only", n_queries=60)
    report = run_diagnosis(store, project_id, llm=None)
    assert len(report["report_files"]) == 2
    for path in report["report_files"]:
        assert Path(path).exists()
    # 第二次诊断产生 diag-002
    report2 = run_diagnosis(store, project_id, llm=None)
    assert "diag-002" in report2["report_files"][0]
