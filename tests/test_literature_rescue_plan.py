from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.literature_rescue_plan import (
    LITERATURE_RESCUE_PLAN_JSON,
    LITERATURE_RESCUE_PLAN_MD,
    build_literature_rescue_plan,
    render_literature_rescue_plan_markdown,
    write_literature_rescue_plan_artifacts,
)
from research_agent.models import LiteratureReview, Paper, ResearchPlan


class LiteratureRescuePlanTest(unittest.TestCase):
    def test_rescue_plan_passes_when_quality_and_coverage_are_sufficient(self) -> None:
        review = _review(_papers(8))
        report = build_literature_rescue_plan(
            _plan(),
            review,
            review,
            {"selected_papers": 8, "warnings": []},
            {"status": "ready_for_review", "expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
        )
        rendered = render_literature_rescue_plan_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["weak_reasons"])
        self.assertIn("文献补检索计划", rendered)

    def test_rescue_plan_generates_queries_for_missing_coverage(self) -> None:
        review = _review(_papers(2))
        coverage = {
            "status": "needs_coverage",
            "coverage_ratio": 0.5,
            "missing_required": [{"category": "baseline", "name": "CHOMP"}, {"category": "benchmark", "name": "OMPL"}],
        }
        report = build_literature_rescue_plan(
            _plan(),
            review,
            review,
            {"selected_papers": 2, "warnings": ["质量筛选后可用文献偏少"]},
            {"status": "needs_snowball", "expansion_queries": [{"query": '"10.1000/rrt"', "priority": 96, "purpose": "doi_lookup"}]},
            coverage,
        )

        self.assertEqual(report["status"], "needs_rescue_search")
        self.assertTrue(any("CHOMP" in item["query"] for item in report["rescue_queries"]))
        self.assertTrue(any("OMPL" in item["query"] for item in report["rescue_queries"]))
        self.assertTrue(any("priority >= 94" in item for item in report["required_actions"]))

    def test_rescue_plan_generates_queries_for_missing_evidence_roles(self) -> None:
        review = _review(_papers(5))
        report = build_literature_rescue_plan(
            _plan(),
            review,
            review,
            {
                "selected_papers": 5,
                "warnings": ["证据角色覆盖不足"],
                "missing_evidence_roles": ["review_survey", "benchmark_dataset", "baseline_method"],
                "role_coverage": {"recent_work": 5},
            },
            {"status": "ready_for_review", "expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
        )
        rendered = render_literature_rescue_plan_markdown(report)
        queries = report["rescue_queries"]

        self.assertEqual(report["status"], "needs_rescue_search")
        self.assertEqual(report["missing_evidence_roles"], ["review_survey", "benchmark_dataset", "baseline_method"])
        self.assertTrue(any(item["kind"] == "missing_evidence_role" and item["priority"] == 99 for item in queries))
        self.assertTrue(any("survey review" in item["query"] for item in queries))
        self.assertTrue(any("benchmark dataset" in item["query"] for item in queries))
        self.assertTrue(any("baseline method" in item["query"] for item in queries))
        self.assertIn("证据角色覆盖不足", rendered)

    def test_rescue_plan_flags_source_repair_and_writes_artifacts(self) -> None:
        raw = _review(
            _papers(3),
            source_health=[{"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True}],
            diagnostics=['semantic_scholar: query="robot" 检索失败：HTTP 429'],
        )
        curated = _review(_papers(3))
        with TemporaryDirectory() as tmp:
            report = write_literature_rescue_plan_artifacts(
                _plan(),
                raw,
                curated,
                {"selected_papers": 3, "warnings": []},
                {"status": "needs_source_repair", "expansion_queries": []},
                {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
                Path(tmp),
            )
            saved = json.loads((Path(tmp) / LITERATURE_RESCUE_PLAN_JSON).read_text(encoding="utf-8"))
            rendered = (Path(tmp) / LITERATURE_RESCUE_PLAN_MD).read_text(encoding="utf-8")

        self.assertEqual(report["status"], "needs_source_repair")
        self.assertEqual(saved["status"], "needs_source_repair")
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in report["source_repairs"]))
        self.assertIn("文献源修复", rendered)

    def test_rate_limited_optional_source_does_not_block_with_successful_fallbacks(self) -> None:
        raw = _review(
            _papers(8),
            source_health=[
                {"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True},
                {"source": "openalex", "status": "ok", "returned": 8, "rate_limited": False},
                {"source": "crossref", "status": "ok", "returned": 8, "rate_limited": False},
            ],
            diagnostics=['semantic_scholar: query="robot" 检索失败：HTTP 429'],
        )
        curated = _review(_papers(8))

        report = build_literature_rescue_plan(
            _plan(),
            raw,
            curated,
            {"selected_papers": 8, "warnings": []},
            {"status": "ready_for_review", "expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["source_repair_severity"], "review")
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in report["source_repairs"]))


def _plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="评估机械臂路径规划方法",
        search_queries=["robot manipulator motion planning"],
        benchmarks=["OMPL"],
        baselines=["RRT*", "CHOMP"],
        metrics=["success_rate", "planning_time"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _review(
    papers: list[Paper],
    source_health: list[dict[str, object]] | None = None,
    diagnostics: list[str] | None = None,
) -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=papers,
        themes=["motion planning"],
        gaps=[],
        summary="summary",
        source_health=source_health or [],
        source_diagnostics=diagnostics or [],
    )


def _papers(count: int) -> list[Paper]:
    return [
        Paper(
            title=f"Robot manipulator motion planning benchmark {index}",
            authors=["A"],
            year=2020 + index,
            venue="ICRA",
            url=f"https://example.org/{index}",
            abstract="RRT* CHOMP OMPL benchmark baseline trajectory optimization collision avoidance.",
            relevance=0.8,
            source="openalex",
            sources=["openalex", "crossref"],
            doi=f"10.1000/{index}",
        )
        for index in range(count)
    ]


if __name__ == "__main__":
    unittest.main()
