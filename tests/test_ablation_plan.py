from __future__ import annotations

import unittest

from research_agent.ablation_plan import build_ablation_plan, render_ablation_plan_markdown
from research_agent.models import ExperimentCommand, ExperimentPlan, ResearchIdea


class AblationPlanTest(unittest.TestCase):
    def test_ablation_plan_passes_when_commands_cover_candidate_baseline_ablation(self) -> None:
        report = build_ablation_plan(_idea(), _plan(include_ablation=True))
        rendered = render_ablation_plan_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["has_ablation"])
        self.assertIn("消融计划", rendered)
        self.assertIn("without_core_mechanism", rendered)

    def test_ablation_plan_marks_missing_ablation_as_needing_action(self) -> None:
        report = build_ablation_plan(_idea(), _plan(include_ablation=False))

        self.assertEqual(report["status"], "needs_ablation")
        self.assertFalse(report["has_ablation"])
        self.assertTrue(report["warnings"])


def _plan(include_ablation: bool) -> ExperimentPlan:
    commands = [
        ExperimentCommand(name="candidate", command=["python3", "simulate.py"]),
        ExperimentCommand(name="baseline", command=["python3", "simulate.py"]),
    ]
    if include_ablation:
        commands.append(ExperimentCommand(name="without_core_mechanism", command=["python3", "simulate.py"]))
    return ExperimentPlan(
        idea_title="ablation test",
        objective="验证核心机制贡献。",
        variables=["method"],
        metrics=["success_rate"],
        protocol=["run candidate", "run baseline", "run ablation"],
        commands=commands,
    )


def _idea() -> ResearchIdea:
    return ResearchIdea(
        title="ablation test",
        hypothesis="核心机制应提升成功率。",
        mechanism="比较完整方案与去除核心机制的变体。",
        expected_contribution="让实验结论可被消融验证。",
        novelty=5,
        feasibility=5,
        risk=2,
        evaluation=["success_rate"],
        baseline="baseline",
    )


if __name__ == "__main__":
    unittest.main()
