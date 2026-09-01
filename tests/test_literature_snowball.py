from __future__ import annotations

import unittest

from research_agent.literature_quality import assess_literature_quality
from research_agent.literature_snowball import build_literature_snowball_report, render_literature_snowball_markdown
from research_agent.models import LiteratureReview, Paper


class LiteratureSnowballTest(unittest.TestCase):
    def test_snowball_generates_seed_queries_from_quality_papers(self) -> None:
        review = _review()
        quality = assess_literature_quality(review, min_keep=3)

        report = build_literature_snowball_report(review, quality)
        rendered = render_literature_snowball_markdown(report)

        self.assertIn(report["status"], {"ready_for_review", "needs_snowball"})
        self.assertGreaterEqual(report["seed_count"], 3)
        self.assertTrue(any("10.1000/rrt" in item["query"] for item in report["expansion_queries"]))
        self.assertTrue(any(item["purpose"] == "exact_title" for item in report["expansion_queries"]))
        self.assertIn("文献滚雪球计划", rendered)

    def test_snowball_flags_semantic_scholar_rate_limit_repair(self) -> None:
        review = _review(
            source_health=[
                {"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True},
            ]
        )
        quality = assess_literature_quality(review, min_keep=3)

        report = build_literature_snowball_report(review, quality)

        self.assertEqual(report["status"], "needs_source_repair")
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in report["source_actions"]))


def _review(source_health: list[dict[str, object]] | None = None) -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="Sampling-based Algorithms for Optimal Motion Planning",
                authors=["Karaman", "Frazzoli"],
                year=2011,
                venue="IJRR",
                url="https://doi.org/10.1000/rrt",
                abstract="Sampling based motion planning with RRT star and PRM baselines for robot motion planning benchmark comparisons.",
                relevance=0.92,
                source="semantic_scholar",
                sources=["semantic_scholar", "openalex"],
                doi="10.1000/rrt",
                citation_count=3000,
            ),
            Paper(
                title="The Open Motion Planning Library",
                authors=["Sucan", "Moll", "Kavraki"],
                year=2012,
                venue="RAM",
                url="https://doi.org/10.1000/ompl",
                abstract="OMPL provides benchmark infrastructure for robot arm motion planning, collision avoidance, PRM, RRT, and trajectory evaluation.",
                relevance=0.89,
                source="openalex",
                sources=["openalex", "crossref"],
                doi="10.1000/ompl",
                citation_count=2000,
            ),
            Paper(
                title="CHOMP Gradient Optimization Techniques for Efficient Motion Planning",
                authors=["Ratliff"],
                year=2009,
                venue="ICRA",
                url="https://doi.org/10.1000/chomp",
                abstract="Trajectory optimization for manipulator motion planning and collision avoidance with smoothness metrics.",
                relevance=0.86,
                source="crossref",
                sources=["crossref"],
                doi="10.1000/chomp",
                citation_count=1200,
            ),
        ],
        themes=["motion planning"],
        gaps=["benchmark coverage"],
        summary="motion planning literature",
        source_health=source_health or [],
    )


if __name__ == "__main__":
    unittest.main()
