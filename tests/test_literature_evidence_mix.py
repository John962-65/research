from __future__ import annotations

import unittest

from research_agent.literature_evidence_mix import build_literature_evidence_mix_report, render_literature_evidence_mix_markdown
from research_agent.models import LiteratureReview, Paper
from research_agent.research_plan import build_research_plan


class LiteratureEvidenceMixTest(unittest.TestCase):
    def test_evidence_mix_passes_for_balanced_robotics_pack(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        papers = [
            _paper("Robot Manipulator Motion Planning Survey", "A review of robot manipulator motion planning, RRT star, PRM, CHOMP, STOMP, TrajOpt, OMPL benchmark and evaluation dataset.", 2024, 300, ["openalex", "semantic_scholar"]),
            _paper("The Open Motion Planning Library", "OMPL benchmarking dataset for motion planning evaluation with robot arm manipulation tasks and baseline planners.", 2023, 500, ["openalex"]),
            _paper("Sampling-based Optimal Motion Planning", "RRT star and PRM baseline methods for collision-free robot manipulator path planning.", 2022, 220, ["semantic_scholar"]),
            _paper("Trajectory Optimization for Robot Arms", "CHOMP STOMP TrajOpt baseline method family for trajectory optimization and collision avoidance.", 2021, 140, ["arxiv"]),
            _paper("Recent Benchmarking of Robot Arm Planning", "Recent benchmark evaluation dataset with planning time, path length, collision rate, and robust manipulation tasks.", 2025, 50, ["openalex", "crossref"]),
        ]
        review = LiteratureReview("机械臂路径规划", papers, [], [], "")

        report = build_literature_evidence_mix_report(plan, review, review, {"confidence_score": 0.85, "confidence_status": "pass"}, {"coverage_ratio": 1.0, "status": "pass"})
        rendered = render_literature_evidence_mix_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertGreaterEqual(report["mix_score"], 0.72)
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(all(item["status"] == "pass" for item in report["anchor_checks"]))
        self.assertIn("文献证据组合审计", rendered)

    def test_evidence_mix_flags_bad_curated_pack(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        raw = LiteratureReview(
            "机械臂路径规划",
            [
                Paper(
                    title="Generic path planning note",
                    authors=[],
                    year=2012,
                    venue="Crossref",
                    url="",
                    abstract="Short note.",
                    relevance=0.3,
                    source="crossref",
                    sources=["crossref"],
                )
            ],
            [],
            [],
            "",
        )

        report = build_literature_evidence_mix_report(plan, raw, raw, {"confidence_score": 0.3, "confidence_status": "weak"}, {"coverage_ratio": 0.2, "status": "needs_coverage"})

        self.assertEqual(report["status"], "block")
        self.assertTrue(report["blocking_issues"])
        self.assertTrue(any("anchor" in item.lower() for item in report["warnings"]))
        self.assertTrue(any("不要批准进入 idea/实验" in item for item in report["required_actions"]))

    def test_evidence_mix_treats_open_motion_planning_library_as_benchmark_anchor(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        paper = _paper(
            "The Open Motion Planning Library",
            (
                "A software library for sampling based motion planning that implements "
                "RRT, PRM, and robot manipulation planners."
            ),
            2012,
            900,
            ["openalex", "crossref"],
        )
        review = LiteratureReview("机械臂路径规划", [paper], [], [], "")

        report = build_literature_evidence_mix_report(
            plan,
            review,
            review,
            {"confidence_score": 0.8, "confidence_status": "pass"},
            {"coverage_ratio": 0.8, "status": "pass"},
        )

        benchmark = next(item for item in report["anchor_checks"] if item["name"] == "benchmark_or_dataset_anchor")
        self.assertEqual(benchmark["status"], "pass")
        self.assertIn("The Open Motion Planning Library", benchmark["evidence_titles"])

    def test_evidence_mix_does_not_count_generic_motion_planning_as_benchmark_anchor(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        paper = _paper(
            "Generic motion planning for robot manipulators",
            "A method paper for robot manipulator motion planning with RRT and PRM comparisons.",
            2023,
            80,
            ["openalex"],
        )
        review = LiteratureReview("机械臂路径规划", [paper], [], [], "")

        report = build_literature_evidence_mix_report(
            plan,
            review,
            review,
            {"confidence_score": 0.7, "confidence_status": "review_required"},
            {"coverage_ratio": 0.5, "status": "needs_coverage"},
        )

        benchmark = next(item for item in report["anchor_checks"] if item["name"] == "benchmark_or_dataset_anchor")
        self.assertEqual(benchmark["status"], "missing")
        self.assertNotIn("Generic motion planning for robot manipulators", benchmark["evidence_titles"])


def _paper(title: str, abstract: str, year: int, citations: int, sources: list[str]) -> Paper:
    return Paper(
        title=title,
        authors=["Ada Lovelace"],
        year=year,
        venue="Robotics Journal",
        url=f"https://example.test/{abs(hash(title))}",
        abstract=abstract,
        relevance=0.9,
        source=sources[0],
        sources=sources,
        doi=f"10.1234/{abs(hash(title))}",
        citation_count=citations,
    )


if __name__ == "__main__":
    unittest.main()
