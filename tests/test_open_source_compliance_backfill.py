from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.open_source_compliance_backfill import backfill_open_source_compliance, render_open_source_compliance_backfill_markdown


class OpenSourceComplianceBackfillTest(unittest.TestCase):
    def test_backfill_writes_missing_lessons_and_compliance(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            dry = backfill_open_source_compliance(runs_dir, dry_run=True)
            report = backfill_open_source_compliance(runs_dir)
            rendered = render_open_source_compliance_backfill_markdown(report)

            lessons = json.loads((run_dir / "00-open-source-lessons.json").read_text(encoding="utf-8"))
            compliance = json.loads((run_dir / "13-open-source-compliance.json").read_text(encoding="utf-8"))

        self.assertEqual(dry["would_write_lessons"], 1)
        self.assertEqual(dry["would_write_compliance"], 1)
        self.assertEqual(report["lessons_written"], 1)
        self.assertEqual(report["compliance_written"], 1)
        self.assertGreater(len(lessons["lessons"]), 0)
        self.assertGreater(compliance["checked_lessons"], 0)
        self.assertIn("Open-Source Compliance Backfill", rendered)
        self.assertIn("legacy-run", rendered)

    def test_backfill_refreshes_repair_queue_when_compliance_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "blocked-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / "00-open-source-lessons.json", {"lessons": []})
            (run_dir / "00-open-source-lessons.md").write_text("# existing\n", encoding="utf-8")
            write_json(run_dir / "13-open-source-compliance.json", {"status": "block", "score": 0.2, "checked_lessons": 4, "blocking_issues": ["外部项目约束未闭环"], "manual_tasks": []})
            (run_dir / "13-open-source-compliance.md").write_text("# existing\n", encoding="utf-8")
            write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0}, "items": []})
            (run_dir / "12-repair-queue.md").write_text("# stale\n", encoding="utf-8")

            dry = backfill_open_source_compliance(runs_dir, dry_run=True)
            report = backfill_open_source_compliance(runs_dir)
            queue = json.loads((run_dir / "12-repair-queue.json").read_text(encoding="utf-8"))

        self.assertEqual(dry["would_write_repair_queue"], 1)
        self.assertEqual(report["repair_queue_written"], 1)
        self.assertEqual(queue["status"], "blocked_repair_required")
        self.assertTrue(any(item["category"] == "open_source_compliance" for item in queue["items"]))

    def test_backfill_skips_existing_without_force(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "已有产物", "stage": "completed"})
            backfill_open_source_compliance(runs_dir)

            skipped = backfill_open_source_compliance(runs_dir)

        self.assertEqual(skipped["skipped_existing"], 1)
        self.assertEqual(skipped["lessons_written"], 0)
        self.assertEqual(skipped["compliance_written"], 0)

    def test_backfill_refreshes_legacy_contract_schema_without_force(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-contract-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "00-open-source-lessons.json",
                {
                    "status": "constraints_ready",
                    "profiles": [{"name": "PaperQA2", "url": "https://github.com/Future-House/paper-qa"}],
                    "project_evidence": [{"project_name": "PaperQA2", "repository_url": "https://github.com/Future-House/paper-qa", "evidence_targets": ["README.md"]}],
                    "lessons": [{"lesson_id": "citation_grounded_fulltext", "source_projects": ["PaperQA2"], "pipeline_targets": ["literature_context"]}],
                },
            )
            (run_dir / "00-open-source-lessons.md").write_text("# old lessons\n", encoding="utf-8")
            write_json(run_dir / "13-open-source-compliance.json", {"schema_version": 2, "status": "pass", "score": 1.0, "checked_lessons": 1})
            (run_dir / "13-open-source-compliance.md").write_text("# old compliance\n", encoding="utf-8")

            dry = backfill_open_source_compliance(runs_dir, dry_run=True)
            report = backfill_open_source_compliance(runs_dir)
            lessons = json.loads((run_dir / "00-open-source-lessons.json").read_text(encoding="utf-8"))
            compliance = json.loads((run_dir / "13-open-source-compliance.json").read_text(encoding="utf-8"))

        self.assertEqual(dry["would_write_lessons"], 1)
        self.assertEqual(dry["would_write_compliance"], 1)
        self.assertEqual(report["lessons_written"], 1)
        self.assertEqual(report["compliance_written"], 1)
        self.assertIn("contract_summary", lessons)
        self.assertEqual(compliance["schema_version"], 3)
        self.assertIn("contract_summary", compliance)


if __name__ == "__main__":
    unittest.main()
