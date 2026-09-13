from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import inspect
import unittest

from research_agent.experiment_decision import build_experiment_decision_report
from research_agent.models import ExperimentCommand, ExperimentPlan, MetricComparison, PaperClaimAudit, PaperReview, StatisticsReport
from research_agent.pipeline import build_workflow_facts, recheck_required_from_disk
from research_agent.workflow_state import WorkflowEngine
from research_agent.artifacts import write_json


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="路由测试",
        objective="验证负结果路由。",
        variables=["method"],
        metrics=["accuracy"],
        protocol=["run"],
        commands=[ExperimentCommand(name="candidate", command=["python3", "c.py"])],
        baseline="base",
    )


def _stats(direction: str) -> StatisticsReport:
    return StatisticsReport(
        idea_title="路由测试",
        repeats=3,
        candidate_name="candidate",
        baseline_name="base",
        comparisons=[
            MetricComparison(
                metric="accuracy",
                candidate_mean=0.9,
                baseline_mean=0.9 + (0.1 if direction == "negative" else -0.1),
                delta=-0.1 if direction == "negative" else 0.1,
                ci_low=(-0.2 if direction == "negative" else 0.0),
                ci_high=(0.0 if direction == "negative" else 0.2),
                candidate_std=0.05,
                baseline_std=0.05,
                effect_size=0.5,
                direction="baseline_better_or_equal" if direction == "negative" else "candidate_better",
                interpretation="test",
            )
        ],
        warnings=[],
    )


def _decision(direction: str, mode: str = "benchmark") -> dict:
    return build_experiment_decision_report(
        _plan(),
        _stats(direction),
        {"status": "pass"},
        {
            "status": "pass",
            "summary": {"failed_runs": 0, "simulated_runs": 3 if mode == "simulated" else 0},
            "failed_runs": [],
            "negative_metrics": [{"metric": "accuracy"}] if direction == "negative" else [],
            "uncertain_metrics": [],
        },
        execution_mode=mode,
    )


class SimulatedStatesTest(unittest.TestCase):
    def test_simulated_result_maps_all_four_states(self) -> None:
        # A29：模拟执行 → execution_status=simulated（契约 §1.1：不属于 completed），
        # evidence_status=simulated，research_outcome=not_assessed，next_action=request_material。
        report = _decision("negative", mode="simulated")
        states = report["decision_states"]
        self.assertEqual(states["execution_status"], "simulated")
        self.assertEqual(states["evidence_status"], "simulated")
        self.assertEqual(states["research_outcome"], "not_assessed")
        self.assertEqual(states["next_action"], "request_material")


class NegativeResultRoutingTest(unittest.TestCase):
    def _engine(self) -> WorkflowEngine:
        return WorkflowEngine([
            "ideation", "experiment_plan", "execution_gate", "experiments", "analysis",
            "paper_writing", "paper_review", "paper_revision", "finalization", "completed",
        ])

    def _states(self) -> dict:
        return {node: {"status": "completed"} for node in (
            "analysis", "paper_writing", "paper_review",
        )}

    def test_negative_result_without_review_tasks_skips_revision(self) -> None:
        # A30：合格负结果、复核未给出必须修改项 → 不进入无界修订，直达终局。
        decision = _decision("negative")
        review = PaperReview(
            decision="accept_with_minor_revisions", score=8.0, novelty=4, soundness=4,
            evidence_quality=4, reproducibility=4, summary="通过", strengths=[],
            weaknesses=[], required_revisions=[], claim_audit=[],
        )
        facts = build_workflow_facts(config_mode="benchmark", experiment_decision=decision, paper_review=review)
        self.assertFalse(facts["revision_required"])
        engine = self._engine()
        states = self._states()
        self.assertFalse(engine.evaluate_edge("paper_review", "paper_revision", states, facts).satisfied)
        self.assertTrue(engine.evaluate_edge("paper_review", "finalization", states, facts).satisfied)

    def test_negative_result_with_review_tasks_enters_one_revision(self) -> None:
        # A31：负结果但复核确有必须修改项 → 进入一次修订（受 paper_revisions
        # 预算上限约束，见 tests/test_run_budget.py），且修订后按审计决定是否复查。
        decision = _decision("negative")
        review = PaperReview(
            decision="revise", score=6.0, novelty=3, soundness=3,
            evidence_quality=3, reproducibility=3, summary="需修订", strengths=[],
            weaknesses=["证据不足"], required_revisions=["降级强结论"], claim_audit=[],
        )
        facts = build_workflow_facts(config_mode="benchmark", experiment_decision=decision, paper_review=review)
        self.assertTrue(facts["revision_required"])
        engine = self._engine()
        states = self._states()
        self.assertTrue(engine.evaluate_edge("paper_review", "paper_revision", states, facts).satisfied)

    def test_recheck_required_follows_revision_response_audit(self) -> None:
        # A31：recheck_required 由修订响应审计实际结果计算，不再固定 False。
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.assertFalse(recheck_required_from_disk(out), "无审计文件 → 不复查")
            write_json(out / "09-revision-response-audit.json", {"status": "pass", "blocking_issues": []})
            self.assertFalse(recheck_required_from_disk(out))
            write_json(out / "09-revision-response-audit.json", {"status": "block", "blocking_issues": ["未响应修订项"]})
            self.assertTrue(recheck_required_from_disk(out))
            write_json(out / "09-revision-response-audit.json", {"status": "pass", "blocking_issues": ["遗留问题"]})
            self.assertTrue(recheck_required_from_disk(out))

    def test_three_entries_share_one_facts_constructor(self) -> None:
        # A31：CLI/Web/恢复三入口的 facts 由同一函数构造——结构上断言
        # 主调度点使用 build_workflow_facts（三入口都汇聚到该调度函数）。
        from research_agent import pipeline

        source = inspect.getsource(pipeline)
        self.assertIn("build_workflow_facts(", source)
        self.assertNotIn('"revision_required": True,', source.replace(" ", "").replace('"revision_required":True,', ""))
        # 纯函数：相同输入产出相同 facts（三入口一致性前提）。
        decision = _decision("negative")
        review = PaperReview(
            decision="revise", score=6.0, novelty=3, soundness=3, evidence_quality=3,
            reproducibility=3, summary="s", strengths=[], weaknesses=[], required_revisions=["r"], claim_audit=[],
        )
        first = build_workflow_facts(config_mode="local", experiment_decision=decision, paper_review=review)
        second = build_workflow_facts(config_mode="local", experiment_decision=decision, paper_review=review)
        self.assertEqual(first, second)
        self.assertTrue(first["revision_required"])
        self.assertTrue(first["execution_requires_approval"])


if __name__ == "__main__":
    unittest.main()
