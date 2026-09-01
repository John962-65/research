from __future__ import annotations

import unittest

from research_agent.experiment_audit import build_experiment_audit_report, render_experiment_audit_markdown
from research_agent.models import ExperimentCommand, ExperimentPlan
from research_agent.research_plan import build_research_plan


class ExperimentAuditTest(unittest.TestCase):
    def test_experiment_audit_passes_aligned_plan(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        plan = _plan()

        report = build_experiment_audit_report(
            research_plan,
            plan,
            literature_coverage={"status": "pass", "coverage_ratio": 1.0},
            ablation_plan={"status": "pass"},
            preregistration={"status": "locked"},
            constraint_compliance={"status": "pass", "checked_constraints": 1, "blocked": 0, "review_required": 0},
        )
        rendered = render_experiment_audit_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["blocking_issues"])
        self.assertIn("实验计划审计", rendered)

    def test_experiment_audit_blocks_generic_baseline_and_missing_ablation(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        plan = ExperimentPlan(
            idea_title="weak plan",
            objective="弱实验计划。",
            variables=["method"],
            metrics=["success_rate"],
            protocol=["run candidate"],
            commands=[ExperimentCommand(name="candidate", command=["python3", "simulate.py"])],
            baseline="最相关 baseline",
        )

        report = build_experiment_audit_report(
            research_plan,
            plan,
            literature_coverage={"status": "pass", "coverage_ratio": 1.0},
            ablation_plan={"status": "needs_ablation"},
            preregistration={"status": "locked"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("baseline" in item for item in report["blocking_issues"]))
        self.assertTrue(any("实验命令缺少" in item for item in report["blocking_issues"]))

    def test_experiment_audit_blocks_duplicate_selected_idea(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        plan = _plan()

        report = build_experiment_audit_report(
            research_plan,
            plan,
            literature_coverage={"status": "pass", "coverage_ratio": 1.0},
            novelty_audit={
                "items": [
                    {
                        "idea_title": plan.idea_title,
                        "decision": "likely_duplicate",
                        "duplicate_risk": 0.72,
                        "closest_paper": {"title": "Sampling-based Algorithms for Optimal Motion Planning"},
                    }
                ]
            },
            ablation_plan={"status": "pass"},
            preregistration={"status": "locked"},
        )
        rendered = render_experiment_audit_markdown(report)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("高重复风险" in item for item in report["blocking_issues"]))
        self.assertIn("selected_idea_novelty", rendered)


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="aligned plan",
        objective="在 OMPL benchmark 上比较候选方法和 RRT baseline。",
        variables=["method", "scene_complexity"],
        metrics=["planning_success_rate", "planning_time", "path_length"],
        protocol=["run candidate", "run baseline", "run ablation"],
        commands=[
            ExperimentCommand(name="robotics_candidate_planner", command=["python3", "simulate.py"]),
            ExperimentCommand(name="robotics_baseline_planner", command=["python3", "simulate.py"]),
            ExperimentCommand(name="robotics_ablation_planner", command=["python3", "simulate.py"]),
        ],
        baseline="RRT / RRT* / PRM",
        evidence_keys=["paper2011"],
        template_profile="robotics_motion_planning",
    )


if __name__ == "__main__":
    unittest.main()
