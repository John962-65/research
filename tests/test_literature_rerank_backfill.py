from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_rerank import LITERATURE_RERANK_JSON, LITERATURE_RERANK_MD
from research_agent.literature_rerank_backfill import backfill_literature_rerank_artifacts, render_literature_rerank_backfill_markdown


class LiteratureRerankBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_rerank_artifacts(runs_dir, dry_run=True)
            rendered = render_literature_rerank_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write"], 1)
            self.assertEqual(report["fallback_research_plan"], 1)
            self.assertFalse((run_dir / LITERATURE_RERANK_JSON).exists())
            self.assertIn("Literature Rerank Backfill", rendered)

    def test_write_creates_rerank_report(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_rerank_artifacts(runs_dir)
            saved = json.loads((run_dir / LITERATURE_RERANK_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written"], 1)
            self.assertTrue((run_dir / LITERATURE_RERANK_MD).exists())
            self.assertIn(saved["status"], {"pass", "review_required"})
            self.assertEqual(saved["total_candidates"], 2)
            self.assertTrue(saved["items"])

    def test_existing_report_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_legacy_literature_run(run_dir)
            write_json(run_dir / LITERATURE_RERANK_JSON, {"status": "sentinel"})
            (run_dir / LITERATURE_RERANK_MD).write_text("# sentinel\n", encoding="utf-8")

            skipped = backfill_literature_rerank_artifacts(runs_dir)
            forced = backfill_literature_rerank_artifacts(runs_dir, force=True)
            saved = json.loads((run_dir / LITERATURE_RERANK_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written"], 1)
            self.assertNotEqual(saved["status"], "sentinel")


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
        },
    )


if __name__ == "__main__":
    unittest.main()
