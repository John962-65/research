from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.ideation import generate_ideas
from research_agent.config import IdeationConfig
from research_agent.literature_context import build_literature_context
from research_agent.models import LiteratureReview, Paper, ResearchPlan
from research_agent.research_gap_map import build_research_gap_map, render_research_gap_map_markdown, write_research_gap_map_artifacts


class EmptyLLM:
    def complete(self, system: str, user: str) -> str:
        return "{}"


class ResearchGapMapTest(unittest.TestCase):
    def test_gap_map_builds_ready_gap_from_literature_and_plan(self) -> None:
        plan = _plan()
        review = _review()
        context = build_literature_context(review)
        coverage = {"status": "pass", "missing_required": []}

        report = build_research_gap_map("机械臂路径规划", plan, review, context, coverage)
        rendered = render_research_gap_map_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["ready_gap_count"], 1)
        self.assertEqual(report["gaps"][0]["testability"], "ready")
        self.assertEqual(report["gaps"][0]["baseline"], "RRT*")
        self.assertIn("planning_success_rate", report["gaps"][0]["metrics"])
        self.assertTrue(report["gaps"][0]["evidence_keys"])
        self.assertIn("研究空白矩阵", rendered)

    def test_gap_map_turns_missing_coverage_into_rescue_gap(self) -> None:
        plan = _plan()
        review = _review()
        context = build_literature_context(review)
        coverage = {
            "status": "needs_coverage",
            "missing_required": [
                {
                    "category": "baseline_family",
                    "name": "trajectory optimization",
                    "suggested_queries": ["robot manipulator TrajOpt benchmark baseline"],
                }
            ],
        }

        report = build_research_gap_map("机械臂路径规划", plan, review, context, coverage)

        coverage_gaps = [item for item in report["gaps"] if item["source"] == "coverage_gap"]
        self.assertTrue(coverage_gaps)
        self.assertEqual(coverage_gaps[0]["baseline"], "trajectory optimization")
        self.assertIn("TrajOpt", coverage_gaps[0]["suggested_queries"][0])

    def test_ideation_fallback_uses_gap_map_before_generic_review_gaps(self) -> None:
        plan = _plan()
        review = _review()
        context = build_literature_context(review)
        gap_map = build_research_gap_map("机械臂路径规划", plan, review, context, {"status": "pass", "missing_required": []})

        ideas = generate_ideas(review, IdeationConfig(max_ideas=1), EmptyLLM(), context, research_gap_map=gap_map)

        self.assertEqual(len(ideas), 1)
        self.assertIn("窄通道失败模式", ideas[0].gap_alignment)
        self.assertEqual(ideas[0].baseline, "RRT*")
        self.assertTrue(ideas[0].evidence_keys)
        self.assertGreaterEqual(len(ideas[0].experiment_sketch), 3)

    def test_write_gap_map_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            report = write_research_gap_map_artifacts(
                "机械臂路径规划",
                _plan(),
                _review(),
                build_literature_context(_review()),
                {"status": "pass", "missing_required": []},
                Path(tmp),
            )
            saved = json.loads((Path(tmp) / "02-research-gap-map.json").read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertTrue((Path(tmp) / "02-research-gap-map.md").exists())
            self.assertEqual(saved["gaps"][0]["gap_id"], "G1")


def _plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="评估机械臂路径规划方法。",
        search_queries=["robot manipulator motion planning benchmark"],
        benchmarks=["OMPL manipulation benchmark"],
        baselines=["RRT*", "TrajOpt"],
        metrics=["planning_success_rate", "planning_time", "collision_rate"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _review() -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="RRT star for narrow passage robot manipulator planning",
                authors=["A. Author"],
                year=2024,
                venue="Robotics",
                url="https://example.org/rrt",
                abstract="RRT* and OMPL manipulation benchmark studies report planning_success_rate, planning_time, and collision_rate for narrow passage robot manipulator motion planning.",
                relevance=0.95,
                source="offline",
                sources=["offline"],
                doi="10.1234/rrt",
            )
        ],
        themes=["机械臂路径规划需要公平 baseline。"],
        gaps=["窄通道失败模式缺少与 RRT* 的可复现比较。"],
        summary="测试综述。",
    )


if __name__ == "__main__":
    unittest.main()
