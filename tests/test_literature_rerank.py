from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.literature_rerank import (
    LITERATURE_RERANK_JSON,
    LITERATURE_RERANK_MD,
    render_literature_rerank_markdown,
    rerank_literature_review,
    write_literature_rerank_artifacts,
)
from research_agent.models import LiteratureReview, Paper, ResearchPlan


class LiteratureRerankTest(unittest.TestCase):
    def test_rerank_demotes_thin_crossref_candidate_below_grounded_baseline_paper(self) -> None:
        weak = Paper(
            title="A generic education survey",
            authors=[],
            year=2025,
            venue="Crossref",
            url="",
            abstract="Short note.",
            relevance=0.95,
            source="crossref",
            sources=["crossref"],
        )
        strong = Paper(
            title="Robot manipulator motion planning with RRT star and OMPL benchmarks",
            authors=["Ada Lovelace"],
            year=2024,
            venue="Robotics Journal",
            url="https://example.test/robot",
            abstract=(
                "Robot manipulator motion planning with obstacle avoidance, RRT star, "
                "CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, "
                "collision rate, and reproducible baseline evaluation."
            ),
            relevance=0.35,
            source="openalex",
            sources=["openalex", "semantic_scholar"],
            doi="10.1234/robot.motion",
            citation_count=120,
        )
        review = _review([weak, strong])

        reranked, report = rerank_literature_review(review, _plan())
        rendered = render_literature_rerank_markdown(report)

        self.assertEqual(reranked.papers[0].title, strong.title)
        self.assertLess(reranked.papers[1].relevance, reranked.papers[0].relevance)
        weak_item = next(item for item in report["items"] if item["title"] == weak.title)
        self.assertIn("single Crossref source with thin abstract", weak_item["penalties"])
        self.assertIn("no DOI/URL locator", weak_item["penalties"])
        self.assertIn("文献候选重排", rendered)
        self.assertIn("降权", rendered)

    def test_manual_seed_and_benchmark_hits_are_prioritized(self) -> None:
        seed = Paper(
            title="STOMP stochastic trajectory optimization for robot arm motion planning",
            authors=["Grace Hopper"],
            year=2011,
            venue="ICRA",
            url="https://doi.org/10.1109/ICRA.2011.5980280",
            abstract="STOMP trajectory optimization baseline for robot arm motion planning with obstacle costs and benchmark comparison.",
            relevance=0.45,
            source="manual_seed",
            sources=["manual_seed", "crossref"],
            doi="10.1109/ICRA.2011.5980280",
            citation_count=800,
        )
        generic = Paper(
            title="Path planning applications overview",
            authors=["Reviewer"],
            year=2026,
            venue="Crossref",
            url="https://example.test/generic",
            abstract="A broad path planning applications overview with limited robot manipulator benchmark details.",
            relevance=0.7,
            source="crossref",
            sources=["crossref"],
        )
        reranked, report = rerank_literature_review(_review([generic, seed]), _plan())

        self.assertEqual(reranked.papers[0].title, seed.title)
        top_item = report["items"][0]
        self.assertIn("manual seed", top_item["reasons"])
        self.assertIn("stomp", top_item["baseline_hits"])

    def test_generic_title_and_weak_venue_are_penalized(self) -> None:
        generic = Paper(
            title="Path planning applications overview",
            authors=["Reviewer"],
            year=2026,
            venue="Crossref",
            url="https://example.test/generic",
            abstract=(
                "A broad path planning applications overview mentions robot manipulator "
                "motion planning, RRT star, OMPL, CHOMP, STOMP, and benchmark evaluation."
            ),
            relevance=0.82,
            source="crossref",
            sources=["crossref"],
        )
        specific = Paper(
            title="Robot manipulator motion planning with RRT star on OMPL benchmarks",
            authors=["Grace Hopper"],
            year=2024,
            venue="IEEE International Conference on Robotics and Automation",
            url="https://example.test/icra-robot",
            abstract=(
                "Robot manipulator motion planning with RRT star, OMPL benchmarks, "
                "collision-free path quality, planning time, and reproducible baseline evaluation."
            ),
            relevance=0.55,
            source="openalex",
            sources=["openalex", "semantic_scholar"],
            doi="10.1234/icra.robot",
            citation_count=90,
        )

        reranked, report = rerank_literature_review(_review([generic, specific]), _plan())

        self.assertEqual(reranked.papers[0].title, specific.title)
        generic_item = next(item for item in report["items"] if item["title"] == generic.title)
        specific_item = next(item for item in report["items"] if item["title"] == specific.title)
        self.assertIn("generic title/object mismatch", generic_item["penalties"])
        self.assertIn("weak venue/source signal", generic_item["penalties"])
        self.assertGreater(specific_item["title_specificity"], generic_item["title_specificity"])
        self.assertGreater(specific_item["venue_score"], generic_item["venue_score"])

    def test_write_rerank_artifacts_outputs_markdown_and_json(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            reranked, report = write_literature_rerank_artifacts(_review([]), _plan(), run_dir)

            self.assertEqual(reranked.papers, [])
            self.assertEqual(report["status"], "review_required")
            self.assertTrue((run_dir / LITERATURE_RERANK_JSON).exists())
            self.assertTrue((run_dir / LITERATURE_RERANK_MD).exists())
            self.assertIn("没有候选文献可重排", (run_dir / LITERATURE_RERANK_MD).read_text(encoding="utf-8"))


def _plan() -> ResearchPlan:
    return ResearchPlan(
        topic="robot manipulator motion planning",
        domain="robotics",
        objective="Improve robot manipulator path planning with obstacle avoidance and reproducible benchmarks.",
        search_queries=["robot manipulator motion planning RRT* OMPL", "CHOMP STOMP TrajOpt robot arm benchmark"],
        benchmarks=["OMPL benchmark"],
        baselines=["RRT*", "CHOMP", "STOMP", "TrajOpt"],
        metrics=["planning time", "path length", "collision rate"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _review(papers: list[Paper]) -> LiteratureReview:
    return LiteratureReview(
        topic="robot manipulator motion planning",
        papers=papers,
        themes=[],
        gaps=[],
        summary="test",
        search_strategy={"selected_queries": ["robot manipulator motion planning RRT* OMPL", "CHOMP STOMP TrajOpt robot arm benchmark"]},
    )


if __name__ == "__main__":
    unittest.main()
