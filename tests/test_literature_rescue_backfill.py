from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_rescue_backfill import backfill_literature_rescue_plans, render_literature_rescue_backfill_markdown
from research_agent.literature_rescue_plan import LITERATURE_RESCUE_PLAN_JSON, LITERATURE_RESCUE_PLAN_MD


class LiteratureRescueBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_rescue_plans(runs_dir, dry_run=True)
            rendered = render_literature_rescue_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write"], 1)
            self.assertEqual(report["fallback_research_plan"], 1)
            self.assertEqual(report["fallback_quality"], 1)
            self.assertEqual(report["fallback_coverage"], 1)
            self.assertEqual(report["fallback_snowball"], 1)
            self.assertEqual(report["generated_curated"], 1)
            self.assertFalse((run_dir / LITERATURE_RESCUE_PLAN_JSON).exists())
            self.assertFalse((run_dir / LITERATURE_RESCUE_PLAN_MD).exists())
            self.assertIn("Literature Rescue Backfill", rendered)
            self.assertIn("不会批准 review gate", rendered)

    def test_write_creates_rescue_plan_without_research_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_rescue_plans(runs_dir)
            saved = json.loads((run_dir / LITERATURE_RESCUE_PLAN_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written"], 1)
            self.assertTrue((run_dir / LITERATURE_RESCUE_PLAN_MD).exists())
            self.assertEqual(saved["domain"], "robotics_motion_planning")
            self.assertIn(saved["status"], {"needs_rescue_search", "needs_manual_seed", "needs_source_repair", "block"})
            self.assertGreater(len(saved["rescue_queries"]), 0)
            self.assertTrue(any("survey" in item["query"] or "OMPL" in item["query"] for item in saved["rescue_queries"]))

    def test_existing_plan_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_legacy_literature_run(run_dir)
            write_json(run_dir / LITERATURE_RESCUE_PLAN_JSON, {"status": "sentinel"})
            (run_dir / LITERATURE_RESCUE_PLAN_MD).write_text("# sentinel\n", encoding="utf-8")

            skipped = backfill_literature_rescue_plans(runs_dir)
            forced = backfill_literature_rescue_plans(runs_dir, force=True)
            saved = json.loads((run_dir / LITERATURE_RESCUE_PLAN_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(skipped["written"], 0)
            self.assertEqual(forced["written"], 1)
            self.assertEqual(forced["items"][0]["action"], "overwrite")
            self.assertNotEqual(saved["status"], "sentinel")

    def test_missing_literature_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "missing-lit"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = backfill_literature_rescue_plans(runs_dir)

            self.assertEqual(report["skipped_no_literature"], 1)
            self.assertEqual(report["written"], 0)
            self.assertFalse((run_dir / LITERATURE_RESCUE_PLAN_JSON).exists())


def _write_legacy_literature_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(
        run_dir / "01-literature.json",
        {
            "topic": "机械臂路径规划",
            "papers": [
                {
                    "title": "A generic neural planner",
                    "authors": ["Author A"],
                    "year": 2024,
                    "venue": "ArXiv",
                    "url": "https://example.test/generic",
                    "abstract": "A neural planner for path planning with limited benchmark grounding.",
                    "relevance": 0.86,
                    "source": "openalex",
                    "sources": ["openalex"],
                    "doi": "10.1000/generic",
                },
                {
                    "title": "Recent robot path planning applications",
                    "authors": ["Author B"],
                    "year": 2025,
                    "venue": "IEEE Access",
                    "url": "https://example.test/recent",
                    "abstract": "Recent path planning applications in robotics with general discussion but limited baseline coverage.",
                    "relevance": 0.82,
                    "source": "crossref",
                    "sources": ["crossref"],
                    "doi": "10.1000/recent",
                },
            ],
            "themes": ["path planning"],
            "gaps": ["benchmark coverage"],
            "summary": "legacy literature review",
            "source_diagnostics": ["crossref: 返回 20 条，用时 1.4s"],
        },
    )


if __name__ == "__main__":
    unittest.main()
