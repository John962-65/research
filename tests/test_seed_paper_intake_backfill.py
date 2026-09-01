from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.seed_paper_intake import SEED_PAPER_INTAKE_JSON, SEED_PAPER_INTAKE_MD
from research_agent.seed_paper_intake_backfill import (
    backfill_seed_paper_intake_artifacts,
    render_seed_paper_intake_backfill_markdown,
)


class SeedPaperIntakeBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_quality_run(run_dir)

            report = backfill_seed_paper_intake_artifacts(runs_dir, dry_run=True)
            rendered = render_seed_paper_intake_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write_runs"], 1)
            self.assertEqual(report["suggested_runs"], 1)
            self.assertFalse((run_dir / SEED_PAPER_INTAKE_JSON).exists())
            self.assertIn("Seed Paper Intake Backfill", rendered)
            self.assertIn("不会伪造 seed 配置", rendered)

    def test_write_creates_not_configured_seed_intake_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_quality_run(run_dir)

            report = backfill_seed_paper_intake_artifacts(runs_dir)
            saved = json.loads((run_dir / SEED_PAPER_INTAKE_JSON).read_text(encoding="utf-8"))
            markdown = (run_dir / SEED_PAPER_INTAKE_MD).read_text(encoding="utf-8")

            self.assertEqual(report["written_runs"], 1)
            self.assertEqual(report["written_seed_intake"], 1)
            self.assertEqual(saved["status"], "not_configured")
            self.assertEqual(saved["role_coverage_status"], "review_required")
            self.assertEqual(saved["total_seed_entries"], 0)
            self.assertEqual(saved["suggested_seed_count"], 1)
            self.assertIn("The Open Motion Planning Library", markdown)
            self.assertIn("候选建议", markdown)

    def test_existing_bundle_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_quality_run(run_dir)
            write_json(run_dir / SEED_PAPER_INTAKE_JSON, {"status": "sentinel"})
            (run_dir / SEED_PAPER_INTAKE_MD).write_text("# sentinel\n", encoding="utf-8")

            skipped = backfill_seed_paper_intake_artifacts(runs_dir)
            forced = backfill_seed_paper_intake_artifacts(runs_dir, force=True)
            saved = json.loads((run_dir / SEED_PAPER_INTAKE_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written_runs"], 1)
            self.assertEqual(forced["items"][0]["action"], "overwrite")
            self.assertNotEqual(saved["status"], "sentinel")

    def test_missing_literature_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "missing-lit"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = backfill_seed_paper_intake_artifacts(runs_dir)

            self.assertEqual(report["skipped_no_literature"], 1)
            self.assertEqual(report["written_runs"], 0)


def _write_quality_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
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
                }
            ]
        },
    )


if __name__ == "__main__":
    unittest.main()
