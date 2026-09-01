from __future__ import annotations

import unittest

from research_agent.literature_coverage import build_literature_coverage_report, render_literature_coverage_markdown
from research_agent.models import LiteratureReview, Paper, ResearchPlan
from research_agent.research_plan import build_research_plan


class LiteratureCoverageTest(unittest.TestCase):
    def test_robotics_coverage_passes_when_baselines_and_benchmarks_are_present(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[
                _paper("Sampling-based Algorithms for Optimal Motion Planning", "RRT star and PRM sampling based motion planning for robot manipulators."),
                _paper("The Open Motion Planning Library", "OMPL benchmark and MoveIt benchmarking for cluttered manipulation scenes and narrow passage motion planning tasks."),
                _paper("CHOMP STOMP and TrajOpt for Robot Arm Trajectory Optimization", "Trajectory optimization baselines include CHOMP, STOMP, and TrajOpt."),
            ],
            themes=[],
            gaps=[],
            summary="",
        )

        report = build_literature_coverage_report(plan, review)
        rendered = render_literature_coverage_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertGreaterEqual(report["coverage_ratio"], 0.9)
        self.assertIn("文献覆盖审计", rendered)
        self.assertFalse(report["missing_required"])

    def test_coverage_flags_missing_required_facets(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[_paper("A generic neural planner", "A neural method for path planning without standard baselines.")],
            themes=[],
            gaps=[],
            summary="",
        )

        report = build_literature_coverage_report(plan, review)

        self.assertIn(report["status"], {"needs_literature", "needs_coverage"})
        self.assertTrue(report["missing_required"])
        missing = report["missing_required"][0]
        self.assertTrue(missing["terms"])
        self.assertTrue(missing["suggested_queries"])
        self.assertIn("robot manipulator", missing["suggested_queries"][0])
        self.assertTrue(any("baseline" in item for item in report["required_actions"]))

    def test_internal_process_benchmark_facets_are_not_required_literature_coverage(self) -> None:
        plan = ResearchPlan(
            topic="Iris classification benchmark smoke",
            domain="iris_classification_benchmark_smoke",
            objective="Validate benchmark flow.",
            search_queries=["UCI Iris classification benchmark"],
            benchmarks=[
                "UCI Machine Learning Repository Iris dataset",
                "paper-grade-benchmark-probe smoke benchmark",
                "内部 paper-grade preflight benchmark scaffold",
            ],
            baselines=[],
            metrics=[],
            constraints=[],
            risks=[],
            success_criteria=[],
        )
        review = LiteratureReview(
            topic=plan.topic,
            papers=[_paper("UCI Iris dataset", "UCI Machine Learning Repository Iris classification dataset benchmark provenance.")],
            themes=[],
            gaps=[],
            summary="",
        )

        report = build_literature_coverage_report(plan, review)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["missing_required"])
        internal_rows = [row for row in report["facets"] if "paper-grade" in str(row["name"]).lower()]
        self.assertTrue(internal_rows)
        self.assertTrue(all(row["required"] is False for row in internal_rows))


def _paper(title: str, abstract: str) -> Paper:
    return Paper(
        title=title,
        authors=["Author"],
        year=2024,
        venue="Test Venue",
        url="https://example.test",
        abstract=abstract,
        relevance=0.9,
        source="offline",
        sources=["offline"],
        doi="10.1000/test",
    )


if __name__ == "__main__":
    unittest.main()
