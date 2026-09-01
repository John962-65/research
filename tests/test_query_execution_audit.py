from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.models import LiteratureReview, Paper, ResearchPlan
from research_agent.query_execution_audit import (
    QUERY_EXECUTION_AUDIT_JSON,
    QUERY_EXECUTION_AUDIT_MD,
    build_query_execution_audit,
    render_query_execution_audit_markdown,
    write_query_execution_audit_artifacts,
)


class QueryExecutionAuditTest(unittest.TestCase):
    def test_query_execution_audit_passes_when_sources_intents_and_top_hits_are_covered(self) -> None:
        review = _review()
        report = build_query_execution_audit(_plan(), review, _rerank(), _source_health())
        rendered = render_query_execution_audit_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["selected_query_count"], 3)
        self.assertFalse(report["intent_coverage"]["missing_required_intents"])
        self.assertTrue(all(item["high_quality_hits"] for item in report["queries"]))
        self.assertIn("Query Execution Audit", rendered)
        self.assertIn("Query 覆盖表", rendered)

    def test_query_execution_audit_requires_source_repair_when_all_sources_fail(self) -> None:
        review = _review(papers=[])
        source_health = {
            "sources": [{"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True}],
            "query_results": [
                {
                    "source": "semantic_scholar",
                    "query": "robot manipulator motion planning",
                    "status": "rate_limited",
                    "returned": 0,
                    "rate_limited": True,
                }
            ],
        }

        report = build_query_execution_audit(_plan(), review, {"items": []}, source_health)

        self.assertEqual(report["status"], "needs_source_repair")
        self.assertTrue(report["required_actions"])
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in report["manual_tasks"]))

    def test_query_execution_audit_detects_missing_required_intent_and_no_candidate_hits(self) -> None:
        review = _review(
            search_strategy={
                "selected_queries": ["robot manipulator motion planning"],
                "sources": ["openalex"],
                "candidates": [{"query": "robot manipulator motion planning", "intent": "method", "selected": True}],
            }
        )
        source_health = {
            "sources": [{"source": "openalex", "status": "ok", "returned": 5}],
            "query_results": [{"source": "openalex", "query": "robot manipulator motion planning", "status": "ok", "returned": 5}],
        }

        report = build_query_execution_audit(_plan(), review, {"items": []}, source_health)

        self.assertEqual(report["status"], "needs_query_repair")
        self.assertIn("baseline", report["intent_coverage"]["missing_required_intents"])
        self.assertIn("benchmark", report["intent_coverage"]["missing_required_intents"])

    def test_write_query_execution_audit_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_query_execution_audit_artifacts(_plan(), _review(), _rerank(), _source_health(), run_dir)
            saved = json.loads((run_dir / QUERY_EXECUTION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(saved["status"], "pass")
            self.assertTrue((run_dir / QUERY_EXECUTION_AUDIT_MD).exists())


def _plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="Evaluate robot manipulator motion planning.",
        search_queries=[
            "robot manipulator motion planning",
            "RRT* CHOMP robot arm trajectory optimization",
            "OMPL benchmark robot manipulator",
        ],
        benchmarks=["OMPL benchmark"],
        baselines=["RRT*", "CHOMP"],
        metrics=["planning time", "path length"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _review(papers: list[Paper] | None = None, search_strategy: dict[str, object] | None = None) -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=papers
        if papers is not None
        else [
            Paper(
                title="Robot manipulator motion planning with RRT star and OMPL benchmarks",
                authors=["Ada"],
                year=2024,
                venue="IEEE ICRA",
                url="https://example.test/robot",
                abstract=(
                    "Robot manipulator motion planning with RRT star, CHOMP trajectory optimization, "
                    "OMPL benchmark evaluation, planning time, path length, and collision avoidance."
                ),
                relevance=0.86,
                source="openalex",
                sources=["openalex", "semantic_scholar"],
                doi="10.1234/robot",
            )
        ],
        themes=[],
        gaps=[],
        summary="",
        search_strategy=search_strategy
        or {
            "selected_queries": [
                "robot manipulator motion planning",
                "RRT* CHOMP robot arm trajectory optimization",
                "OMPL benchmark robot manipulator",
            ],
            "sources": ["openalex", "semantic_scholar"],
            "candidates": [
                {"query": "robot manipulator motion planning", "intent": "method", "selected": True},
                {"query": "RRT* CHOMP robot arm trajectory optimization", "intent": "baseline", "selected": True},
                {"query": "OMPL benchmark robot manipulator", "intent": "benchmark", "selected": True},
            ],
        },
    )


def _source_health() -> dict[str, object]:
    queries = [
        "robot manipulator motion planning",
        "RRT* CHOMP robot arm trajectory optimization",
        "OMPL benchmark robot manipulator",
    ]
    return {
        "sources": [{"source": "openalex", "status": "ok", "returned": 9}],
        "query_results": [{"source": "openalex", "query": query, "status": "ok", "returned": 3} for query in queries],
    }


def _rerank() -> dict[str, object]:
    return {
        "status": "pass",
        "items": [
            {
                "title": "Robot manipulator motion planning with RRT star and OMPL benchmarks",
                "query_coverage": 1.0,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
