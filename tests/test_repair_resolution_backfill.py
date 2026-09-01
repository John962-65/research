from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.repair_resolution_audit import REPAIR_RESOLUTION_AUDIT_JSON, REPAIR_RESOLUTION_AUDIT_MD
from research_agent.repair_resolution_backfill import backfill_repair_resolution_audits, render_repair_resolution_backfill_markdown


class RepairResolutionBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-run"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_queue(run_dir, status="blocked_repair_required")
            write_json(run_dir / "12-repair-resume-plan.json", {"applied": False, "rerun_from": "literature_review"})

            report = backfill_repair_resolution_audits(runs_dir, dry_run=True)
            rendered = render_repair_resolution_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write"], 1)
            self.assertFalse((run_dir / REPAIR_RESOLUTION_AUDIT_JSON).exists())
            self.assertIn("不会应用 repair-resume", rendered)

    def test_write_creates_not_applicable_for_unapplied_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-run"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_queue(run_dir, status="blocked_repair_required")
            write_json(run_dir / "12-repair-resume-plan.json", {"applied": False, "rerun_from": "literature_review"})

            report = backfill_repair_resolution_audits(runs_dir)
            saved = json.loads((run_dir / REPAIR_RESOLUTION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written"], 1)
            self.assertEqual(saved["status"], "not_applicable")
            self.assertFalse(saved["applied"])
            self.assertTrue((run_dir / REPAIR_RESOLUTION_AUDIT_MD).exists())

    def test_write_blocks_applied_resume_with_remaining_original_item(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-run"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_queue(run_dir, status="blocked_repair_required")
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "applied": True,
                    "rerun_from": "experiment_plan",
                    "repair_items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "repair",
                            "source_artifact": "04-result-validation.json",
                            "action": "重跑修复项",
                        }
                    ],
                },
            )

            report = backfill_repair_resolution_audits(runs_dir)
            saved = json.loads((run_dir / REPAIR_RESOLUTION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written"], 1)
            self.assertEqual(saved["status"], "block")
            self.assertTrue(saved["applied"])
            self.assertEqual(len(saved["remaining_items"]), 1)
            self.assertEqual(report["items"][0]["blocking_issues"], 1)

    def test_existing_skips_unless_forced(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-run"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_queue(run_dir, status="pass")
            write_json(run_dir / "12-repair-resolution-audit.json", {"status": "sentinel"})
            write_text(run_dir / "12-repair-resolution-audit.md", "# sentinel")

            skipped = backfill_repair_resolution_audits(runs_dir)
            forced = backfill_repair_resolution_audits(runs_dir, force=True)
            saved = json.loads((run_dir / REPAIR_RESOLUTION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written"], 1)
            self.assertEqual(saved["status"], "not_applicable")


def _write_state(run_dir: Path) -> None:
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})


def _write_queue(run_dir: Path, *, status: str) -> None:
    items = []
    if status == "blocked_repair_required":
        items.append(
            {
                "task_id": "RQ-001",
                "severity": "block",
                "category": "repair",
                "source_artifact": "04-result-validation.json",
                "action": "重跑修复项",
                "status": "open",
            }
        )
    write_json(run_dir / "12-repair-queue.json", {"topic": "机械臂路径规划", "status": status, "items": items})


if __name__ == "__main__":
    unittest.main()
