from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from research_agent.config import LiteratureConfig
from research_agent.literature_rescue_execution import execute_literature_rescue, render_literature_rescue_execution_markdown, write_literature_rescue_execution_artifacts
from research_agent.models import LiteratureReview, Paper


class SynthesisLLM:
    def complete(self, system: str, user: str) -> str:
        return '{"summary":"补检索后更新的综述。","themes":["补强主题"],"gaps":["补强空白"]}'


class FakeClient:
    def __init__(self, config: LiteratureConfig) -> None:
        self.config = config
        self.source_health = [
            {
                "source": "openalex",
                "status": "ok",
                "queries": config.max_search_queries,
                "returned": 1,
                "errors": 0,
                "rate_limited": False,
                "elapsed_seconds": 0.1,
                "cache_hits": 0,
                "cache_misses": 1,
                "cache_writes": 1,
                "stale_cache_uses": 0,
            }
        ]

    def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
        return [
            Paper(
                title="CHOMP: Gradient Optimization Techniques for Efficient Motion Planning",
                authors=["Ratliff"],
                year=2009,
                venue="ICRA",
                url="https://doi.org/10.1109/ICRA.2009.5152817",
                abstract="CHOMP trajectory optimization for robot manipulator motion planning and obstacle avoidance benchmark.",
                relevance=0.92,
                source="openalex",
                sources=["openalex"],
                doi="10.1109/ICRA.2009.5152817",
                citation_count=500,
            )
        ], ["openalex: fake rescue search"]


class LiteratureRescueExecutionTest(unittest.TestCase):
    def test_offline_mode_writes_not_applicable_artifacts(self) -> None:
        review = _review()
        with TemporaryDirectory() as tmp:
            final_review, report = write_literature_rescue_execution_artifacts(
                "机械臂路径规划",
                LiteratureConfig(provider="offline"),
                SynthesisLLM(),
                review,
                _rescue_report(),
                Path(tmp),
            )

            self.assertIs(final_review, review)
            self.assertEqual(report["status"], "not_applicable")
            self.assertTrue((Path(tmp) / "01-literature-rescue-execution.json").exists())
            self.assertTrue((Path(tmp) / "01-literature-rescue-execution.md").exists())

    def test_online_rescue_executes_high_priority_queries_and_updates_review(self) -> None:
        final_review, report = execute_literature_rescue(
            "机械臂路径规划",
            LiteratureConfig(provider="online", sources=["openalex"], max_papers=3, max_search_queries=2),
            SynthesisLLM(),
            _review(),
            _rescue_report(),
            client_factory=FakeClient,
        )

        self.assertEqual(report["status"], "executed")
        self.assertTrue(report["updated_review"])
        self.assertEqual(report["new_unique_papers"], 1)
        self.assertEqual(report["selected_queries"], ["机械臂路径规划 CHOMP benchmark baseline"])
        self.assertIn("补检索后更新的综述", final_review.summary)
        self.assertTrue(any("CHOMP" in paper.title for paper in final_review.papers))
        self.assertTrue(any(item.get("source") == "openalex" for item in final_review.source_health))

    def test_online_rescue_preserves_manual_seed_papers_when_truncating(self) -> None:
        final_review, report = execute_literature_rescue(
            "机械臂路径规划",
            LiteratureConfig(provider="online", sources=["openalex"], max_papers=2, max_search_queries=2),
            SynthesisLLM(),
            _manual_seed_review(),
            _rescue_report(),
            client_factory=FakeClient,
        )

        self.assertEqual(report["status"], "executed")
        self.assertEqual(len(final_review.papers), 2)
        self.assertTrue(any("manual_seed" in set(paper.sources or [paper.source]) for paper in final_review.papers))

    def test_confirmed_agent_repair_task_executes_even_when_rescue_plan_passes(self) -> None:
        final_review, report = execute_literature_rescue(
            "机械臂路径规划",
            LiteratureConfig(provider="online", sources=["openalex"], max_papers=3, max_search_queries=2),
            SynthesisLLM(),
            _review(),
            {"status": "pass", "rescue_queries": []},
            client_factory=FakeClient,
            repair_tasks=[
                {
                    "task_id": "retrieval-repair-001",
                    "owner": "agent",
                    "priority": 92,
                    "query": "机械臂路径规划 CHOMP benchmark baseline",
                }
            ],
        )

        self.assertEqual(report["status"], "executed")
        self.assertEqual(report["trigger_status"], "pass")
        self.assertEqual(report["selected_queries"], ["机械臂路径规划 CHOMP benchmark baseline"])
        self.assertEqual(report["repair_task_ids"], ["retrieval-repair-001"])
        self.assertEqual(report["query_outcomes"][0]["status"], "closed")
        self.assertEqual(report["query_outcomes"][0]["repair_task_ids"], ["retrieval-repair-001"])
        self.assertEqual(report["query_outcomes"][0]["new_unique_candidates"], 1)
        self.assertEqual(report["query_outcomes"][0]["final_new_papers"], 1)
        self.assertEqual(report["closed_query_outcomes"], 1)
        self.assertEqual(report["unresolved_query_outcomes"], 0)
        self.assertEqual(report["required_actions"], [])
        self.assertTrue(any("CHOMP" in paper.title for paper in final_review.papers))
        self.assertIn("Query 闭环", render_literature_rescue_execution_markdown(report))


def _review() -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="The Open Motion Planning Library",
                authors=["Sucan"],
                year=2012,
                venue="IEEE Robotics & Automation Magazine",
                url="https://doi.org/10.1109/MRA.2012.2205651",
                abstract="OMPL provides sampling based motion planning benchmark infrastructure for robots.",
                relevance=0.86,
                source="offline",
                sources=["offline"],
                doi="10.1109/MRA.2012.2205651",
            )
        ],
        themes=["采样规划"],
        gaps=["缺少轨迹优化 baseline"],
        summary="初始综述",
        source_diagnostics=["offline: seed"],
        source_health=[],
    )


def _manual_seed_review() -> LiteratureReview:
    review = _review()
    return LiteratureReview(
        topic=review.topic,
        papers=[
            Paper(
                title="Manual seed CHOMP baseline survey",
                authors=["Manual seed"],
                year=2024,
                venue="Manual seed",
                url="https://example.org/manual-seed",
                abstract="Manual seed for CHOMP baseline benchmark provenance.",
                relevance=0.2,
                source="manual_seed",
                sources=["manual_seed"],
            ),
            *review.papers,
        ],
        themes=review.themes,
        gaps=review.gaps,
        summary=review.summary,
        source_diagnostics=review.source_diagnostics,
        source_health=review.source_health,
    )


def _rescue_report() -> dict:
    return {
        "status": "needs_rescue_search",
        "rescue_queries": [
            {"query": "机械臂路径规划 CHOMP benchmark baseline", "priority": 98},
            {"query": "low priority query", "priority": 80},
        ],
    }


if __name__ == "__main__":
    unittest.main()
