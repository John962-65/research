from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.config import LiteratureConfig
from research_agent.literature_context import apply_literature_audits_to_context, build_literature_context
from research_agent.models import LiteratureReview, Paper
from research_agent.seed_paper_intake import (
    build_seed_paper_intake_report,
    build_seed_paper_suggestion_report,
    build_unconfigured_seed_paper_intake_report,
    render_seed_paper_intake_markdown,
    write_seed_paper_intake_artifacts,
)


class SeedPaperIntakeTest(unittest.TestCase):
    def test_seed_suggestions_report_extracts_role_gaps_from_quality_candidates(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-quality.json",
                {
                    "items": [
                        {
                            "title": "The Open Motion Planning Library",
                            "doi": "10.1109/MRA.2012.2205651",
                            "url": "https://doi.org/10.1109/MRA.2012.2205651",
                            "selected": True,
                            "quality_score": 0.94,
                            "evidence_roles": ["benchmark_dataset", "baseline_method"],
                        },
                        {
                            "title": "Recent robot manipulator motion planning advances",
                            "doi": "10.1234/recent",
                            "url": "https://doi.org/10.1234/recent",
                            "selected": True,
                            "quality_score": 0.86,
                            "evidence_roles": ["recent_work"],
                        },
                    ]
                },
            )

            report = build_seed_paper_suggestion_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "available")
        self.assertEqual(report["suggested_seed_count"], 2)
        self.assertEqual(report["suggested_seed_role_counts"]["benchmark_dataset"], 1)
        self.assertEqual(report["suggested_seed_role_counts"]["baseline_method"], 1)
        self.assertEqual(report["suggested_seed_role_counts"]["recent"], 1)
        self.assertEqual(report["missing_roles"], ["review"])
        self.assertEqual(report["role_repair_queries"], ["机械臂路径规划 survey review state of the art"])

    def test_seed_intake_passes_when_doi_seed_is_curated(self) -> None:
        raw = _review([_paper("Sampling-based Algorithms for Optimal Motion Planning", doi="10.1177/0278364911406761")])
        curated = _review(raw.papers)
        quality = {"items": [{"title": raw.papers[0].title, "doi": raw.papers[0].doi, "url": raw.papers[0].url, "selected": True}]}

        report = build_seed_paper_intake_report(
            "机械臂路径规划",
            LiteratureConfig(seed_papers=["10.1177/0278364911406761 Sampling-based Algorithms for Optimal Motion Planning"]),
            raw,
            curated,
            quality,
        )
        rendered = render_seed_paper_intake_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["curated_seed_papers"], 1)
        self.assertEqual(report["metadata_resolved_seed_papers"], 0)
        self.assertEqual(report["metadata_unresolved_doi_url_seed_papers"], 1)
        self.assertIn("Seed Paper Intake", rendered)
        self.assertIn("Seed 元数据解析", rendered)

    def test_seed_intake_records_resolved_metadata_sources(self) -> None:
        raw = _review([_paper("Resolved RRT Benchmark", doi="10.1234/rrt", sources=["crossref", "manual_seed"])])
        report = build_seed_paper_intake_report(
            "机械臂路径规划",
            LiteratureConfig(seed_papers=["10.1234/rrt Resolved RRT Benchmark"]),
            raw,
            raw,
            {"items": [{"title": raw.papers[0].title, "doi": raw.papers[0].doi, "selected": True}]},
        )

        self.assertEqual(report["metadata_resolved_seed_papers"], 1)
        self.assertEqual(report["metadata_unresolved_doi_url_seed_papers"], 0)
        self.assertEqual(report["items"][0]["metadata_sources"], ["crossref"])

    def test_unconfigured_seed_intake_report_preserves_missing_configuration_and_suggestions(self) -> None:
        report = build_unconfigured_seed_paper_intake_report(
            "机械臂路径规划",
            {
                "suggested_seed_entries": ["10.1234/ompl The Open Motion Planning Library"],
                "suggested_seed_role_counts": {"review": 0, "benchmark_dataset": 1, "baseline_method": 1, "recent": 0},
                "combined_seed_role_counts": {"review": 0, "benchmark_dataset": 1, "baseline_method": 1, "recent": 0},
                "missing_roles": ["review", "recent"],
                "role_repair_queries": ["机械臂路径规划 survey review state of the art", "机械臂路径规划 2024 2025 latest recent advances"],
            },
        )
        rendered = render_seed_paper_intake_markdown(report)

        self.assertEqual(report["status"], "not_configured")
        self.assertEqual(report["role_coverage_status"], "review_required")
        self.assertEqual(report["total_seed_entries"], 0)
        self.assertEqual(report["metadata_resolved_seed_papers"], 0)
        self.assertEqual(report["suggested_seed_count"], 1)
        self.assertIn("历史", "；".join(report["warnings"]))
        self.assertIn("survey review state of the art", "；".join(report["required_actions"]))
        self.assertIn("候选建议", rendered)
        self.assertIn("The Open Motion Planning Library", rendered)

    def test_seed_intake_blocks_when_seed_never_reaches_raw_pool(self) -> None:
        raw = _review([_paper("Unrelated robot paper", doi="10.1000/other")])
        curated = _review(raw.papers)

        report = build_seed_paper_intake_report(
            "机械臂路径规划",
            LiteratureConfig(seed_papers=["10.9999/missing Important benchmark paper"]),
            raw,
            curated,
            {"items": []},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("未进入原始文献池" in item for item in report["warnings"]))

    def test_seed_intake_reviews_title_only_seed_and_updates_gate(self) -> None:
        seed = _paper("Robot manipulator motion planning benchmark", doi="", sources=["manual_seed"])
        raw = _review([seed])
        curated = _review([seed])
        report = build_seed_paper_intake_report(
            "机械臂路径规划",
            LiteratureConfig(seed_papers=["Robot manipulator motion planning benchmark 2024"]),
            raw,
            curated,
            {"items": [{"title": seed.title, "selected": True}]},
        )
        context = apply_literature_audits_to_context(build_literature_context(curated), seed_intake_report=report)

        self.assertEqual(report["status"], "review_required")
        self.assertIn("seed intake", " ".join(context.review_gate.warnings).lower())
        self.assertTrue(any("01-seed-paper-intake" in item for item in context.review_gate.required_actions))

    def test_seed_role_coverage_requires_review_even_when_all_seeds_are_curated(self) -> None:
        papers = [
            _paper(
                "RRT star robot manipulator motion planning algorithm",
                doi="10.1234/rrtstar",
                abstract="Robot manipulator motion planning algorithm for cluttered workcells.",
            ),
            _paper(
                "PRM robot manipulator motion planning method",
                doi="10.1234/prm",
                abstract="Robot manipulator motion planning method with roadmap construction.",
            ),
            _paper(
                "CHOMP robot manipulator trajectory planning approach",
                doi="10.1234/chomp",
                abstract="Robot manipulator motion planning approach for trajectory optimization.",
            ),
        ]
        review = _review(papers)
        seed_entries = [f"{paper.doi} {paper.title}" for paper in papers]

        report = build_seed_paper_intake_report(
            "机械臂路径规划",
            LiteratureConfig(seed_papers=seed_entries),
            review,
            review,
            {"items": [{"title": paper.title, "doi": paper.doi, "selected": True} for paper in papers]},
        )
        context = apply_literature_audits_to_context(build_literature_context(review), seed_intake_report=report)
        rendered = render_seed_paper_intake_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["role_coverage_status"], "review_required")
        self.assertEqual(report["curated_seed_role_counts"]["baseline_method"], 3)
        self.assertEqual(report["curated_seed_role_counts"]["recent"], 3)
        self.assertIn("review", report["missing_curated_seed_roles"])
        self.assertIn("benchmark_dataset", report["missing_curated_seed_roles"])
        self.assertIn("角色覆盖", rendered)
        self.assertTrue(any("角色覆盖不足" in item for item in context.review_gate.warnings))
        self.assertTrue(any("至少 3 类 seed" in item for item in context.review_gate.required_actions))

    def test_seed_role_coverage_passes_with_review_benchmark_baseline_and_recent(self) -> None:
        papers = [
            _paper(
                "Survey of robot manipulator motion planning methods",
                doi="10.1234/survey",
                year=2020,
                abstract="Review of robot manipulator motion planning methods.",
            ),
            _paper(
                "OMPL benchmark suite for robot manipulator motion planning",
                doi="10.1234/ompl",
                year=2019,
                abstract="Benchmark suite and evaluation protocol for robot manipulator motion planning.",
            ),
            _paper(
                "Recent RRT planner for robot manipulator motion planning",
                doi="10.1234/recent",
                year=2024,
                abstract="Robot manipulator motion planning algorithm with recent baseline comparisons.",
            ),
        ]
        review = _review(papers)

        report = build_seed_paper_intake_report(
            "机械臂路径规划",
            LiteratureConfig(seed_papers=[f"{paper.doi} {paper.title}" for paper in papers]),
            review,
            review,
            {"items": [{"title": paper.title, "doi": paper.doi, "selected": True} for paper in papers]},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["role_coverage_status"], "pass")
        self.assertFalse(report["missing_curated_seed_roles"])

    def test_write_seed_paper_intake_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            raw = _review([_paper("Robot manipulator motion planning benchmark", doi="10.1234/robot")])
            report = write_seed_paper_intake_artifacts(
                "机械臂路径规划",
                LiteratureConfig(seed_papers=["10.1234/robot Robot manipulator motion planning benchmark"]),
                raw,
                raw,
                {"items": [{"title": raw.papers[0].title, "doi": raw.papers[0].doi, "selected": True}]},
                run_dir,
            )
            saved = (run_dir / "01-seed-paper-intake.json")
            self.assertTrue(saved.exists())
            self.assertEqual(report["status"], "pass")


def _review(papers: list[Paper]) -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=papers,
        themes=["robot manipulator motion planning"],
        gaps=[],
        summary="summary",
    )


def _paper(
    title: str,
    doi: str = "10.1234/robot",
    sources: list[str] | None = None,
    year: int = 2024,
    abstract: str = "Robot manipulator motion planning benchmark and baseline evidence for 机械臂 路径规划.",
) -> Paper:
    source_values = sources or ["manual_seed"]
    return Paper(
        title=title,
        authors=["Ada"],
        year=year,
        venue="Robotics",
        url=f"https://doi.org/{doi}" if doi else "https://example.test/manual-seed",
        abstract=abstract,
        relevance=0.9,
        source=source_values[0],
        sources=source_values,
        doi=doi,
    )


if __name__ == "__main__":
    unittest.main()
