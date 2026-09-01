from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_quality_backfill import (
    LITERATURE_CURATED_JSON,
    LITERATURE_CURATED_MD,
    LITERATURE_QUALITY_JSON,
    LITERATURE_QUALITY_MD,
    backfill_literature_quality_artifacts,
    render_literature_quality_backfill_markdown,
)


class LiteratureQualityBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_quality_artifacts(runs_dir, dry_run=True)
            rendered = render_literature_quality_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write_runs"], 1)
            self.assertEqual(report["reconstructed_source_health"], 1)
            self.assertFalse((run_dir / LITERATURE_QUALITY_JSON).exists())
            self.assertFalse((run_dir / LITERATURE_CURATED_JSON).exists())
            self.assertIn("Literature Quality Backfill", rendered)
            self.assertIn("不会批准 gate", rendered)

    def test_write_creates_quality_and_curated_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_quality_artifacts(runs_dir)
            quality = json.loads((run_dir / LITERATURE_QUALITY_JSON).read_text(encoding="utf-8"))
            curated = json.loads((run_dir / LITERATURE_CURATED_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written_runs"], 1)
            self.assertEqual(report["written_quality"], 1)
            self.assertEqual(report["written_curated"], 1)
            self.assertTrue((run_dir / LITERATURE_QUALITY_MD).exists())
            self.assertTrue((run_dir / LITERATURE_CURATED_MD).exists())
            self.assertEqual(quality["selected_papers"], 1)
            self.assertEqual(quality["confidence_factors"]["rate_limited_sources"], 1)
            self.assertEqual(len(curated["papers"]), 1)
            self.assertEqual(curated["papers"][0]["title"], "Robot manipulator motion planning with RRT star and OMPL benchmarks")
            self.assertTrue(any("质量筛选" in item for item in curated["source_diagnostics"]))

    def test_existing_bundle_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_legacy_literature_run(run_dir)
            write_json(run_dir / LITERATURE_QUALITY_JSON, {"confidence_status": "sentinel"})
            (run_dir / LITERATURE_QUALITY_MD).write_text("# sentinel\n", encoding="utf-8")
            write_json(run_dir / LITERATURE_CURATED_JSON, {"topic": "机械臂路径规划", "papers": [], "themes": [], "gaps": [], "summary": "sentinel"})
            (run_dir / LITERATURE_CURATED_MD).write_text("# sentinel\n", encoding="utf-8")

            skipped = backfill_literature_quality_artifacts(runs_dir)
            forced = backfill_literature_quality_artifacts(runs_dir, force=True)
            quality = json.loads((run_dir / LITERATURE_QUALITY_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written_runs"], 1)
            self.assertEqual(forced["items"][0]["action"], "overwrite")
            self.assertNotEqual(quality["confidence_status"], "sentinel")

    def test_missing_literature_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "missing-lit"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = backfill_literature_quality_artifacts(runs_dir)

            self.assertEqual(report["skipped_no_literature"], 1)
            self.assertEqual(report["written_runs"], 0)


def _write_legacy_literature_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(
        run_dir / "01-literature.json",
        {
            "topic": "机械臂路径规划",
            "papers": [
                {
                    "title": "A generic education survey",
                    "authors": [],
                    "year": 2025,
                    "venue": "Crossref",
                    "url": "",
                    "abstract": "Short note.",
                    "relevance": 0.95,
                    "source": "crossref",
                    "sources": ["crossref"],
                },
                {
                    "title": "Robot manipulator motion planning with RRT star and OMPL benchmarks",
                    "authors": ["Ada Lovelace"],
                    "year": 2024,
                    "venue": "Robotics Journal",
                    "url": "https://example.test/robot",
                    "abstract": "Robot manipulator motion planning with obstacle avoidance, RRT star, CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, collision rate, and reproducible baseline evaluation.",
                    "relevance": 0.35,
                    "source": "openalex",
                    "sources": ["openalex", "semantic_scholar"],
                    "doi": "10.1234/robot.motion",
                    "citation_count": 120,
                },
            ],
            "themes": [],
            "gaps": [],
            "summary": "legacy literature review",
            "source_diagnostics": [
                "检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",
                "semantic_scholar: 检索失败：HTTP 429: Too Many Requests",
                "crossref: 2 个检索式返回 20 条，用时 1.4s",
            ],
        },
    )


if __name__ == "__main__":
    unittest.main()
