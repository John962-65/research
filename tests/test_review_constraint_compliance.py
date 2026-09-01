from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.experiment_audit import build_experiment_audit_report
from research_agent.models import ExperimentCommand, ExperimentPlan, ResearchIdea, ResearchPlan
from research_agent.review_constraint_compliance import (
    REVIEW_CONSTRAINT_COMPLIANCE_JSON,
    REVIEW_CONSTRAINT_COMPLIANCE_MD,
    build_review_constraint_compliance_report,
    render_review_constraint_compliance_markdown,
    write_review_constraint_compliance_artifacts,
)


class ReviewConstraintComplianceTest(unittest.TestCase):
    def test_blocks_high_priority_constraint_missing_from_selected_idea_and_plan(self) -> None:
        idea = _idea(baseline="PRM", evaluation=["success_rate", "runtime", "path_length"])
        plan = _plan(baseline="PRM", metrics=["success_rate", "runtime"])
        report = build_review_constraint_compliance_report(
            "机械臂路径规划",
            {
                "constraints": [
                    {
                        "id": "RC01",
                        "priority": "high",
                        "category": "baseline",
                        "text": "必须比较 RRT*",
                        "applies_to": ["ideation", "experiment_plan"],
                    }
                ]
            },
            idea,
            plan,
        )
        rendered = render_review_constraint_compliance_markdown(report)

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["blocked"], 1)
        self.assertIn("selected_idea", report["items"][0]["missing_surfaces"])
        self.assertIn("experiment_plan", report["items"][0]["missing_surfaces"])
        self.assertIn("人工审核约束落实审计", rendered)

    def test_passes_when_constraint_is_covered_on_required_surfaces(self) -> None:
        idea = _idea(baseline="RRT*", evaluation=["success_rate", "碰撞率", "runtime"])
        plan = _plan(baseline="RRT*", metrics=["success_rate", "碰撞率", "runtime"])
        report = build_review_constraint_compliance_report(
            "机械臂路径规划",
            {
                "constraints": [
                    {
                        "id": "RC01",
                        "priority": "high",
                        "category": "baseline",
                        "text": "必须比较 RRT*",
                        "applies_to": ["ideation", "experiment_plan"],
                    },
                    {
                        "id": "RC02",
                        "priority": "medium",
                        "category": "metric",
                        "text": "建议报告碰撞率指标",
                        "applies_to": ["experiment_plan", "analysis"],
                    },
                ]
            },
            idea,
            plan,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["passed"], 2)
        self.assertIn("rrt*", report["items"][0]["matched_terms"])

    def test_human_brief_constraints_are_audited(self) -> None:
        idea = _idea(baseline="PRM", evaluation=["success_rate", "runtime"])
        plan = _plan(baseline="PRM", metrics=["success_rate", "runtime"])
        report = build_review_constraint_compliance_report(
            "机械臂路径规划",
            {"constraints": []},
            idea,
            plan,
            human_brief={
                "status": "provided",
                "constraints": ["必须比较 RRT*"],
                "success_criteria": ["成功率提升"],
            },
        )
        rendered = render_review_constraint_compliance_markdown(report)

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["review_constraints"], 0)
        self.assertEqual(report["human_brief_constraints"], 2)
        self.assertTrue(any(item["id"] == "HB-C01" and item["source"] == "human_brief" for item in report["items"]))
        self.assertIn("Review/Human brief：0/2", rendered)

    def test_human_brief_resource_limit_passes_when_plan_mentions_it(self) -> None:
        idea = _idea(experiment_sketch=["先做 smoke-first 运行", "固定随机种子"])
        plan = _plan(protocol=["先做 smoke-first 运行", "固定随机种子", "再比较 candidate 与 baseline"])
        report = build_review_constraint_compliance_report(
            "机械臂路径规划",
            {"constraints": []},
            idea,
            plan,
            human_brief={
                "status": "provided",
                "resource_limits": ["只允许运行 smoke-first"],
            },
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["human_brief_constraints"], 1)
        self.assertEqual(report["items"][0]["decision"], "pass")

    def test_review_gate_audit_summary_uses_experiment_plan_only(self) -> None:
        idea = _idea(baseline="RRT*", evaluation=["accuracy"])
        plan = _plan(
            baseline="RRT*",
            protocol=["记录 coverage passed (11/11 required external benchmark/baseline facets)"],
        )
        report = build_review_constraint_compliance_report(
            "Iris classification benchmark smoke",
            {
                "constraints": [
                    {
                        "id": "RC08",
                        "source": "review_gate",
                        "priority": "high",
                        "category": "baseline",
                        "text": "coverage passed (11/11 required external benchmark/baseline facets)",
                        "applies_to": ["ideation", "experiment_plan"],
                    }
                ]
            },
            idea,
            plan,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["blocked"], 0)
        self.assertEqual(report["items"][0]["required_surfaces"], ["experiment_plan"])

    def test_claim_boundary_human_brief_can_be_satisfied_by_plan_scope(self) -> None:
        idea = _idea(experiment_sketch=["运行 Iris smoke benchmark"])
        plan = _plan(
            protocol=[
                "Use Iris to validate benchmark provenance, manifest contracts, repeated execution, statistics, and release flow.",
                "Do not claim broad scientific novelty from Iris alone.",
            ],
        )
        report = build_review_constraint_compliance_report(
            "Iris classification benchmark smoke",
            {"constraints": []},
            idea,
            plan,
            human_brief={
                "status": "provided",
                "constraints": [
                    "Do not claim broad scientific novelty from Iris alone; use it to validate benchmark provenance, manifest contracts, repeated execution, statistics, and release flow."
                ],
            },
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["blocked"], 0)
        self.assertEqual(report["items"][0]["required_surfaces"], ["experiment_plan"])

    def test_experiment_audit_blocks_unmet_human_constraints(self) -> None:
        plan = _plan(baseline="PRM", metrics=["success_rate", "runtime"])
        audit = build_experiment_audit_report(
            _research_plan(),
            plan,
            literature_coverage={"status": "pass"},
            novelty_audit={"items": [{"idea_title": plan.idea_title, "decision": "likely_novel", "duplicate_risk": 0.1}]},
            ablation_plan={"status": "pass", "has_ablation": True},
            preregistration={"status": "locked"},
            constraint_compliance={"status": "block", "blocked": 1, "blocking_issues": ["RC01 未落实：必须比较 RRT*"]},
        )

        self.assertEqual(audit["status"], "block")
        self.assertTrue(any("RC01" in item for item in audit["blocking_issues"]))

    def test_writes_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = write_review_constraint_compliance_artifacts(
                "机械臂路径规划",
                {"constraints": []},
                _idea(),
                _plan(),
                out,
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue((out / REVIEW_CONSTRAINT_COMPLIANCE_JSON).exists())
            self.assertTrue((out / REVIEW_CONSTRAINT_COMPLIANCE_MD).exists())


def _idea(baseline: str = "RRT*", evaluation: list[str] | None = None, experiment_sketch: list[str] | None = None) -> ResearchIdea:
    return ResearchIdea(
        title="约束感知机械臂路径规划",
        hypothesis="加入约束审计可以提升路径规划实验可信度。",
        mechanism="把人工反馈转为实验前检查项。",
        expected_contribution="减少忽略人工约束的自动实验。",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=evaluation or ["success_rate", "collision_rate", "runtime"],
        evidence_keys=["smith2024"],
        evidence_chunks=["chunk-1"],
        gap_alignment="公开 benchmark 和 baseline 对齐不足。",
        baseline=baseline,
        experiment_sketch=experiment_sketch or ["固定随机种子", "比较 candidate 与 baseline", "报告均值方差"],
    )


def _plan(baseline: str = "RRT*", metrics: list[str] | None = None, protocol: list[str] | None = None) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="约束感知机械臂路径规划",
        objective="在公开任务上比较 candidate 与 baseline。",
        variables=["candidate vs baseline", "场景复杂度"],
        metrics=metrics or ["success_rate", "collision_rate", "runtime"],
        protocol=protocol or ["固定随机种子", "运行 candidate、baseline 和 ablation", "报告均值方差"],
        commands=[
            ExperimentCommand("candidate", ["python3", "simulate.py", "--mode", "candidate"]),
            ExperimentCommand("baseline", ["python3", "simulate.py", "--mode", "baseline"]),
            ExperimentCommand("ablation", ["python3", "simulate.py", "--mode", "ablation"]),
        ],
        rationale="实验计划落实人工审核意见。",
        baseline=baseline,
        evidence_keys=["smith2024"],
        template_profile="robotics_path_planning",
    )


def _research_plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics",
        objective="评估路径规划方法。",
        search_queries=["robot arm path planning"],
        benchmarks=["OMPL"],
        baselines=["RRT*", "PRM"],
        metrics=["success_rate", "collision_rate", "runtime"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


if __name__ == "__main__":
    unittest.main()
