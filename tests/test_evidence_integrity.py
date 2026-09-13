from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research_agent.config import PaperConfig
from research_agent.evidence_integrity import (
    EvidenceIntegrity,
    assess_evidence_integrity,
    evidence_integrity_banner,
    evidence_integrity_prompt_constraint,
    write_evidence_integrity_artifacts,
)
from research_agent.final_readiness import build_final_readiness_report
from research_agent.models import (
    Analysis,
    ClaimTraceabilityItem,
    ClaimTraceabilityReport,
    ExperimentCommand,
    ExperimentPlan,
    LiteratureReview,
    PaperClaimAudit,
    Paper,
    PaperReview,
    PaperRewriteReport,
    ResearchIdea,
)
from research_agent.writing import write_paper_markdown


def _write_results(run_dir: Path, statuses: list[str]) -> None:
    rows = [
        {
            "name": f"exp{index}",
            "status": status,
            "metrics": {"planning_success_rate": 0.8},
            "artifacts": [],
            "stdout": "",
            "stderr": "",
            "repeat_index": 0,
            "seed": "deadbeef",
            "command": ["python3", "exp.py"],
            "returncode": 0 if status in {"passed", "completed", "local"} else 1,
        }
        for index, status in enumerate(statuses)
    ]
    (run_dir / "04-results.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _write_ledger(run_dir: Path, total_calls: int, successful_calls: int | None = None) -> None:
    """写入带逐条 entries 的账本（llm_trace 真实结构）；缺省全部成功。"""
    successful = total_calls if successful_calls is None else successful_calls
    entries = []
    for call_id in range(1, total_calls + 1):
        status = "success" if call_id <= successful else "failed"
        entries.append({"call_id": call_id, "stage": "research_planning", "purpose": "test", "status": status})
    payload = {
        "total_calls": total_calls,
        "successful_calls": successful,
        "failed_calls": total_calls - successful,
        "entries": entries,
    }
    (run_dir / "run-llm-ledger.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_summary_only_ledger(run_dir: Path, total_calls: int, successful_calls: int) -> None:
    payload = {"total_calls": total_calls, "successful_calls": successful_calls}
    (run_dir / "run-llm-ledger.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _simulated() -> EvidenceIntegrity:
    return EvidenceIntegrity(real_llm=False, real_experiment=False, llm_calls=0, real_result_count=0, simulated_result_count=4)


def _real() -> EvidenceIntegrity:
    return EvidenceIntegrity(real_llm=True, real_experiment=True, llm_calls=9, real_result_count=6, simulated_result_count=0)


class AssessEvidenceIntegrityTest(unittest.TestCase):
    def test_simulated_only_without_ledger_is_not_publishable(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["simulated", "simulated"])
            integrity = assess_evidence_integrity(run_dir)
            self.assertFalse(integrity.real_llm)
            self.assertFalse(integrity.real_experiment)
            self.assertFalse(integrity.publishable_evidence)
            self.assertTrue(integrity.simulated_only)
            self.assertEqual(integrity.status, "no_real_evidence")

    def test_real_llm_and_real_experiment_is_publishable(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["passed", "passed"])
            _write_ledger(run_dir, 12)
            integrity = assess_evidence_integrity(run_dir)
            self.assertTrue(integrity.real_llm)
            self.assertTrue(integrity.real_experiment)
            self.assertTrue(integrity.publishable_evidence)
            self.assertEqual(integrity.status, "real_evidence")

    def test_all_failed_llm_calls_are_not_real_evidence(self) -> None:
        # A01：总调用 3、成功 0、失败 3 → 不能显示已有成功模型产物。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["passed"])
            _write_ledger(run_dir, 3, 0)
            integrity = assess_evidence_integrity(run_dir)
            self.assertFalse(integrity.real_llm)
            self.assertEqual(integrity.llm_attempted_calls, 3)
            self.assertEqual(integrity.llm_successful_calls, 0)
            self.assertEqual(integrity.llm_evidence_status, "incomplete")
            self.assertTrue(any("成功 0 次" in note for note in integrity.notes))
            self.assertFalse(integrity.publishable_evidence)

    def test_summary_only_ledger_is_incomplete(self) -> None:
        # 仅有汇总、无逐条调用记录的账本 → incomplete，不能用总数冒充成功数。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["passed"])
            _write_summary_only_ledger(run_dir, 9, 9)
            integrity = assess_evidence_integrity(run_dir)
            self.assertFalse(integrity.real_llm)
            self.assertEqual(integrity.llm_evidence_status, "incomplete")

    def test_failed_only_results_are_attempts_not_verified_results(self) -> None:
        # A02：只有 failed/timeout/cancelled 记录 → 无可用于主张的已验证结果。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["failed", "timeout", "cancelled"])
            integrity = assess_evidence_integrity(run_dir)
            self.assertFalse(integrity.real_experiment)
            self.assertEqual(integrity.experiment_evidence_status, "incomplete")
            self.assertEqual(integrity.real_attempt_count, 3)
            self.assertEqual(integrity.real_result_count, 0)
            self.assertTrue(any("真实执行尝试" in note for note in integrity.notes))

    def test_result_without_finite_metrics_is_not_verified(self) -> None:
        # A03：完成状态但 NaN 指标 / 无指标 / 无来源绑定 → 不得判 verified。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            rows = [
                {"name": "nan_row", "status": "passed", "metrics": {"accuracy": float("nan")},
                 "command": ["python3", "exp.py"], "returncode": 0},
                {"name": "empty_row", "status": "passed", "metrics": {},
                 "command": ["python3", "exp.py"], "returncode": 0},
                {"name": "no_provenance", "status": "passed", "metrics": {"accuracy": 0.9}},
            ]
            (run_dir / "04-results.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            integrity = assess_evidence_integrity(run_dir)
            self.assertNotEqual(integrity.experiment_evidence_status, "verified")
            self.assertFalse(integrity.real_experiment)
            self.assertEqual(len(integrity.unusable_result_reasons), 3)
            self.assertTrue(any("非有限数值" in reason for reason in integrity.unusable_result_reasons))
            self.assertTrue(any("无任何指标" in reason for reason in integrity.unusable_result_reasons))
            self.assertTrue(any("来源绑定" in reason for reason in integrity.unusable_result_reasons))

    def test_manual_report_with_real_experiment_is_not_simulated(self) -> None:
        # A04：真实实验 + 无模型调用 → 实验证据 verified，不因无 LLM 判成模拟。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["passed", "passed"])
            integrity = assess_evidence_integrity(run_dir)
            self.assertTrue(integrity.real_experiment)
            self.assertEqual(integrity.experiment_evidence_status, "verified")
            self.assertEqual(integrity.llm_evidence_status, "unknown")
            self.assertFalse(integrity.real_llm)
            banner = evidence_integrity_banner(integrity)
            self.assertIn("真实 LLM", banner)
            self.assertNotIn("实验结果缺少可用真实数据", banner)
            readiness = build_final_readiness_report(
                "机械臂路径规划", _paper_review(), _paper_review(), _rewrite_report(), evidence_integrity=integrity
            )
            self.assertNotEqual(readiness.status, "requires_real_experiment")
            self.assertFalse(any("模拟/占位" in issue for issue in readiness.blocking_issues))

    def test_real_llm_but_simulated_experiment_is_partial(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["simulated"])
            _write_ledger(run_dir, 5)
            integrity = assess_evidence_integrity(run_dir)
            self.assertTrue(integrity.real_llm)
            self.assertFalse(integrity.real_experiment)
            self.assertFalse(integrity.publishable_evidence)
            self.assertEqual(integrity.status, "partial_real_evidence")

    def test_zero_total_calls_ledger_counts_as_no_real_llm(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["passed"])
            _write_ledger(run_dir, 0, 0)
            integrity = assess_evidence_integrity(run_dir)
            self.assertFalse(integrity.real_llm)
            self.assertEqual(integrity.llm_evidence_status, "unknown")
            self.assertTrue(integrity.real_experiment)
            self.assertFalse(integrity.publishable_evidence)

    def test_empty_run_dir_is_not_publishable(self) -> None:
        with TemporaryDirectory() as tmp:
            integrity = assess_evidence_integrity(Path(tmp))
            self.assertFalse(integrity.publishable_evidence)
            self.assertEqual(integrity.status, "no_real_evidence")

    def test_write_artifacts_emits_json_and_md(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_results(run_dir, ["simulated"])
            integrity = write_evidence_integrity_artifacts("机械臂路径规划", run_dir)
            self.assertFalse(integrity.publishable_evidence)
            self.assertTrue((run_dir / "04-evidence-integrity.json").exists())
            self.assertTrue((run_dir / "04-evidence-integrity.md").exists())
            data = json.loads((run_dir / "04-evidence-integrity.json").read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "no_real_evidence")
            self.assertFalse(data["publishable_evidence"])


class BannerAndConstraintTest(unittest.TestCase):
    def test_simulated_produces_banner_and_constraint(self) -> None:
        banner = evidence_integrity_banner(_simulated())
        self.assertIn("诚实性声明", banner)
        self.assertIn("不能作为科学结论", banner)
        constraint = evidence_integrity_prompt_constraint(_simulated())
        self.assertIn("禁止", constraint)
        self.assertIn("模拟原型", constraint)

    def test_real_evidence_suppresses_banner_and_constraint(self) -> None:
        self.assertEqual(evidence_integrity_banner(_real()), "")
        self.assertEqual(evidence_integrity_prompt_constraint(_real()), "")

    def test_none_is_safe(self) -> None:
        self.assertEqual(evidence_integrity_banner(None), "")
        self.assertEqual(evidence_integrity_prompt_constraint(None), "")


class FinalReadinessGateTest(unittest.TestCase):
    def test_simulated_evidence_forces_requires_real_experiment(self) -> None:
        readiness = build_final_readiness_report(
            "机械臂路径规划", _paper_review(), _paper_review(), _rewrite_report(), evidence_integrity=_simulated()
        )
        self.assertEqual(readiness.status, "requires_real_experiment")
        self.assertTrue(any("模拟" in issue for issue in readiness.blocking_issues))
        self.assertTrue(any("真实 LLM" in action or "真实 benchmark" in action for action in readiness.next_actions))

    def test_real_evidence_is_not_downgraded(self) -> None:
        readiness = build_final_readiness_report(
            "机械臂路径规划", _paper_review(), _paper_review(), _rewrite_report(), evidence_integrity=_real()
        )
        self.assertEqual(readiness.status, "ready_for_submission_check")

    def test_clean_traceability_can_close_reviewer_weak_claims_for_real_evidence(self) -> None:
        revised = PaperReview(
            decision="major_revision",
            score=4.0,
            novelty=2,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="审稿人认为贡献较窄。",
            strengths=[],
            weaknesses=["内部产物仍需人工解释。"],
            required_revisions=[],
            claim_audit=[
                PaperClaimAudit(
                    claim="runbook、results 和 statistics 已支撑本次内部 benchmark adapter 执行记录。",
                    support_level="weak",
                    evidence_keys=[],
                    result_refs=["04-results.json", "04-statistics.json"],
                    risk="medium",
                )
            ],
        )
        trace = ClaimTraceabilityReport(
            topic="机械臂路径规划",
            status="pass",
            traceability_score=1.0,
            total_claims=1,
            passed_claims=1,
            review_claims=0,
            blocked_claims=0,
            items=[
                ClaimTraceabilityItem(
                    claim="runbook、results 和 statistics 已支撑本次内部 benchmark adapter 执行记录。",
                    support_level="weak",
                    decision="pass",
                    citation_status="not_required",
                    result_status="pass",
                    runbook_status="pass",
                    evidence_keys=[],
                    missing_evidence_keys=[],
                    result_refs=["04-results.json", "04-statistics.json"],
                    matched_result_refs=["04-results.json", "04-statistics.json"],
                    issues=[],
                )
            ],
            blocking_issues=[],
            manual_tasks=[],
            evidence_inventory={"has_results": True, "has_statistics": True, "has_runbook": True},
        )

        readiness = build_final_readiness_report("机械臂路径规划", _paper_review(), revised, _rewrite_report(), traceability_report=trace, evidence_integrity=_real())

        self.assertEqual(readiness.status, "ready_for_human_polish")
        self.assertEqual(readiness.weak_after, 0)
        self.assertFalse(readiness.blocking_issues)

    def test_missing_evidence_integrity_is_backward_compatible(self) -> None:
        readiness = build_final_readiness_report(
            "机械臂路径规划", _paper_review(), _paper_review(), _rewrite_report()
        )
        self.assertEqual(readiness.status, "ready_for_submission_check")


class PaperBannerIntegrationTest(unittest.TestCase):
    def test_fallback_paper_gets_banner_under_simulated_evidence(self) -> None:
        review, idea, plan, analysis = _paper_fixtures()
        paper = write_paper_markdown(
            "机械臂路径规划", review, [idea], plan, analysis, PaperConfig(), evidence_integrity=_simulated()
        )
        self.assertTrue(paper.startswith("# "))
        self.assertIn("诚实性声明", paper)

    def test_fallback_paper_has_no_banner_under_real_evidence(self) -> None:
        review, idea, plan, analysis = _paper_fixtures()
        paper = write_paper_markdown(
            "机械臂路径规划", review, [idea], plan, analysis, PaperConfig(), evidence_integrity=_real()
        )
        self.assertNotIn("诚实性声明", paper)


def _paper_review() -> PaperReview:
    return PaperReview(
        decision="accept_with_minor_revisions",
        score=8.0,
        novelty=4,
        soundness=4,
        evidence_quality=4,
        reproducibility=4,
        summary="通过。",
        strengths=[],
        weaknesses=[],
        required_revisions=[],
        claim_audit=[],
    )


def _rewrite_report() -> PaperRewriteReport:
    return PaperRewriteReport(
        topic="机械臂路径规划",
        source_paper="06-paper.md",
        revised_paper="09-revised-paper.md",
        revision_plan="08-revision-plan.json",
        summary="已修订。",
        task_results=[],
        deferred_tasks=[],
        next_checks=[],
    )


def _paper_fixtures() -> tuple[LiteratureReview, ResearchIdea, ExperimentPlan, Analysis]:
    paper = Paper(
        title="Robot manipulator motion planning with obstacle avoidance",
        authors=["Ada Lovelace"],
        year=2024,
        venue="arXiv",
        url="https://arxiv.org/abs/0000.00001",
        abstract="Robot manipulator motion planning and obstacle avoidance benchmark.",
        relevance=0.9,
        source="arxiv",
        sources=["arxiv"],
        doi="10.1234/example",
    )
    review = LiteratureReview(
        topic="机械臂路径规划",
        papers=[paper],
        themes=["机械臂路径规划需要避障和轨迹连续性。"],
        gaps=["需要可复现 benchmark。"],
        summary="测试综述",
    )
    idea = ResearchIdea(
        title="避障路径规划验证",
        hypothesis="候选规划器可以在复杂障碍场景中提高规划成功率。",
        mechanism="结合采样式规划和轨迹平滑约束。",
        expected_contribution="提供机械臂路径规划的可复现实验起点。",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=["planning_success_rate", "planning_time"],
        evidence_keys=["manual2024robot"],
        evidence_chunks=["chunk-001"],
        baseline="RRT*",
    )
    plan = ExperimentPlan(
        idea_title=idea.title,
        objective="比较候选规划器与 RRT* 的规划成功率。",
        variables=["方法", "障碍密度"],
        metrics=["planning_success_rate", "planning_time"],
        protocol=["固定起终位姿", "运行候选方案和 baseline", "统计重复试验结果"],
        commands=[ExperimentCommand(name="simulate", command=["python3", "simulate.py"])],
        baseline="RRT*",
        evidence_keys=["manual2024robot"],
    )
    analysis = Analysis(
        headline="候选方案在模拟实验中取得更高成功率。",
        metric_table=[{"name": "planning_success_rate", "candidate": 0.82, "baseline": 0.74}],
        findings=["成功率高于 baseline。"],
        limitations=["当前仍是模拟实验。"],
        next_steps=["接入真实 benchmark。"],
    )
    return review, idea, plan, analysis


if __name__ == "__main__":
    unittest.main()
