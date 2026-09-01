from __future__ import annotations

import unittest

from research_agent.models import ExperimentCommand, ExperimentPlan, ResearchIdea
from research_agent.preregistration import build_preregistration_report, plan_fingerprint, render_preregistration_markdown


class PreregistrationTest(unittest.TestCase):
    def test_preregistration_locks_plan_before_results(self) -> None:
        plan = _plan()
        report = build_preregistration_report("机械臂路径规划", _idea(), plan)
        rendered = render_preregistration_markdown(report)

        self.assertEqual(report["status"], "locked")
        self.assertEqual(report["timing"], "before_results")
        self.assertEqual(report["plan_fingerprint"], plan_fingerprint(plan))
        self.assertIn("实验预注册", rendered)
        self.assertIn("candidate_vs_ablation", rendered)

    def test_preregistration_marks_checkpoint_after_results_as_posthoc(self) -> None:
        report = build_preregistration_report("机械臂路径规划", _idea(), _plan(), results_exist=True)

        self.assertEqual(report["status"], "posthoc")
        self.assertEqual(report["timing"], "posthoc_checkpoint")
        self.assertTrue(any("事后审计" in item for item in report["warnings"]))


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="prereg test",
        objective="锁定实验计划。",
        variables=["method"],
        metrics=["success_rate", "runtime_cost", "failure_cases"],
        protocol=["run candidate", "run baseline", "run ablation"],
        commands=[
            ExperimentCommand(name="candidate", command=["python3", "simulate.py"]),
            ExperimentCommand(name="baseline", command=["python3", "simulate.py"]),
            ExperimentCommand(name="ablation", command=["python3", "simulate.py"]),
        ],
    )


def _idea() -> ResearchIdea:
    return ResearchIdea(
        title="prereg test",
        hypothesis="预先锁定指标可以降低事后改结论风险。",
        mechanism="在实验前保存指标、比较和计划指纹。",
        expected_contribution="提高自动科研流程的审计性。",
        novelty=6,
        feasibility=7,
        risk=2,
        evaluation=["success_rate", "runtime_cost"],
        evidence_keys=["paper2024"],
        baseline="baseline",
    )


if __name__ == "__main__":
    unittest.main()
