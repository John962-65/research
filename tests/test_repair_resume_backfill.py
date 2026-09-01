from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.repair_resume_backfill import backfill_repair_resume_plans, render_repair_resume_backfill_markdown


class RepairResumeBackfillTest(unittest.TestCase):
    def test_dry_run_reports_active_queue_without_writing_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "blocked-run"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_active_queue(run_dir, rerun_from="experiments")

            report = backfill_repair_resume_plans(runs_dir, dry_run=True)
            rendered = render_repair_resume_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write"], 1)
            self.assertEqual(report["written"], 0)
            self.assertFalse((run_dir / "12-repair-resume-plan.json").exists())
            self.assertFalse((run_dir / "12-repair-resume-plan.md").exists())
            self.assertIn("Repair Resume Backfill", rendered)
            self.assertIn("blocked-run", rendered)
            self.assertIn("不会删除产物、不会恢复 pipeline、不会批准 gate 或执行实验", rendered)

    def test_write_creates_unapplied_plan_without_deleting_downstream_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-needed"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_active_queue(run_dir, rerun_from="experiments")
            write_json(run_dir / "03-execution-approval.json", {"approved": True})
            write_json(run_dir / "04-results.json", [{"status": "stale"}])
            write_text(run_dir / "06-paper.md", "# stale paper")

            report = backfill_repair_resume_plans(runs_dir)
            plan = json.loads((run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))

            self.assertEqual(report["written"], 1)
            self.assertEqual(report["items"][0]["action"], "write")
            self.assertEqual(plan["status"], "ready_to_resume_repair")
            self.assertFalse(plan["applied"])
            self.assertTrue(plan["execution_reapproval_required"])
            self.assertTrue((run_dir / "03-execution-approval.json").exists())
            self.assertTrue((run_dir / "04-results.json").exists())
            self.assertTrue((run_dir / "06-paper.md").exists())
            self.assertTrue((run_dir / "12-repair-resume-plan.md").exists())

    def test_existing_plan_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-plan"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_active_queue(run_dir, rerun_from="checkpoint")
            write_json(run_dir / "12-repair-resume-plan.json", {"status": "sentinel", "applied": False})
            write_text(run_dir / "12-repair-resume-plan.md", "# sentinel")

            skipped = backfill_repair_resume_plans(runs_dir)
            force = backfill_repair_resume_plans(runs_dir, force=True)
            plan = json.loads((run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(skipped["written"], 0)
            self.assertEqual(force["written"], 1)
            self.assertEqual(force["items"][0]["action"], "overwrite")
            self.assertEqual(plan["status"], "ready_to_resume_repair")

    def test_existing_stale_literature_plan_is_refreshed_when_rebuild_adds_queries(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "stale-literature-plan"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_active_queue(run_dir, rerun_from="literature_review")
            write_json(
                run_dir / "01-seed-paper-intake.json",
                {
                    "status": "pass",
                    "role_coverage_status": "review_required",
                    "total_seed_entries": 2,
                    "curated_seed_papers": 2,
                    "missing_curated_seed_roles": ["review"],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "can_resume": True,
                    "applied": False,
                    "rerun_from": "literature_review",
                    "repair_items": [{"task_id": "RQ-001", "category": "repair"}],
                    "retrieval_repair_tasks": [],
                    "recommended_config": {},
                    "review_reapproval_required": True,
                    "execution_reapproval_required": True,
                },
            )
            write_text(run_dir / "12-repair-resume-plan.md", "# stale")

            dry = backfill_repair_resume_plans(runs_dir, dry_run=True)
            report = backfill_repair_resume_plans(runs_dir)
            plan = json.loads((run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))

        self.assertEqual(dry["would_write"], 1)
        self.assertEqual(dry["stale_existing"], 1)
        self.assertEqual(dry["items"][0]["action"], "would_refresh_stale")
        self.assertEqual(report["refreshed_stale"], 1)
        self.assertEqual(report["items"][0]["action"], "refresh_stale")
        self.assertTrue(plan["retrieval_repair_tasks"])
        self.assertEqual(plan["recommended_config"]["literature_provider"], "online")

    def test_existing_literature_plan_without_feedback_is_refreshed_with_fallback_queries(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "fallback-refresh"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            _write_active_queue(run_dir, rerun_from="literature_review")
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "can_resume": True,
                    "applied": False,
                    "rerun_from": "literature_review",
                    "repair_items": [{"task_id": "RQ-001", "category": "repair"}],
                    "retrieval_repair_tasks": [],
                    "recommended_config": {},
                    "review_reapproval_required": True,
                    "execution_reapproval_required": True,
                },
            )
            write_text(run_dir / "12-repair-resume-plan.md", "# stale")

            report = backfill_repair_resume_plans(runs_dir)
            plan = json.loads((run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))

        self.assertEqual(report["written"], 1)
        self.assertEqual(report["refreshed_stale"], 1)
        self.assertEqual(report["items"][0]["action"], "refresh_stale")
        self.assertEqual(report["items"][0]["resume_readiness"], "ready_to_apply")
        self.assertEqual(plan["recommended_config"]["literature_provider"], "online")
        self.assertTrue(any(item.get("category") == "bounded_rescue_query" for item in plan["retrieval_repair_tasks"]))

    def test_existing_benchmark_plan_still_missing_manifest_is_not_overwritten(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "still-missing-benchmark"
            run_dir.mkdir(parents=True)
            _write_state(run_dir)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-BENCH-001",
                            "severity": "block",
                            "category": "benchmark_result_schema",
                            "source_artifact": "04-benchmark-result-schema-audit.json",
                            "action": "补齐 benchmark manifest 后重跑实验。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "can_resume": True,
                    "applied": False,
                    "rerun_from": "experiments",
                    "repair_items": [{"task_id": "RQ-BENCH-001", "category": "benchmark_result_schema"}],
                    "recommended_execution_config": {},
                    "review_reapproval_required": False,
                    "execution_reapproval_required": True,
                },
            )
            write_text(run_dir / "12-repair-resume-plan.md", "# stale")

            report = backfill_repair_resume_plans(runs_dir)
            plan = json.loads((run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))

        self.assertEqual(report["written"], 0)
        self.assertEqual(report["still_needs_preconditions"], 1)
        self.assertEqual(report["skipped_existing"], 1)
        self.assertEqual(report["items"][0]["action"], "skipped_needs_preconditions")
        self.assertIn("missing_benchmark_manifest_recommendation", report["items"][0]["precondition_codes"])
        self.assertEqual(plan["recommended_execution_config"], {})

    def test_clean_or_missing_queue_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-run"
            missing = runs_dir / "missing-queue"
            non_run = runs_dir / "scratch"
            clean.mkdir(parents=True)
            missing.mkdir()
            non_run.mkdir()
            _write_state(clean)
            _write_state(missing)
            write_json(clean / "12-repair-queue.json", {"topic": "机械臂路径规划", "status": "pass", "items": []})

            report = backfill_repair_resume_plans(runs_dir)

            self.assertEqual(report["scanned_runs"], 2)
            self.assertEqual(report["skipped_no_state"], 1)
            self.assertEqual(report["skipped_no_active_queue"], 2)
            self.assertEqual(report["written"], 0)
            self.assertFalse((clean / "12-repair-resume-plan.json").exists())
            self.assertFalse((missing / "12-repair-resume-plan.json").exists())


def _write_state(run_dir: Path) -> None:
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})


def _write_active_queue(run_dir: Path, *, rerun_from: str) -> None:
    write_json(
        run_dir / "12-repair-queue.json",
        {
            "topic": "机械臂路径规划",
            "status": "blocked_repair_required",
            "items": [
                {
                    "task_id": "RQ-001",
                    "severity": "block",
                    "category": "repair",
                    "source_artifact": "04-result-validation.json",
                    "action": "重跑修复项",
                    "rerun_from": rerun_from,
                    "status": "open",
                }
            ],
        },
    )


if __name__ == "__main__":
    unittest.main()
