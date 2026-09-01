from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.repair_resume_backlog import build_repair_resume_backlog, render_repair_resume_backlog_markdown


class RepairResumeBacklogTest(unittest.TestCase):
    def test_reports_active_repair_resume_queue_without_writing_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            scratch = runs_dir / "scratch"
            run_dir.mkdir(parents=True)
            scratch.mkdir()
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "private repair action must not be rendered",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(run_dir / "04-results.json", [{"status": "stale"}])

            report = build_repair_resume_backlog(runs_dir)
            rendered = render_repair_resume_backlog_markdown(report)

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["skipped_no_state"], 1)
            self.assertEqual(report["summary"]["total"], 1)
            self.assertEqual(report["summary"]["ready_to_apply"], 1)
            self.assertEqual(report["summary"]["needs_preconditions"], 0)
            self.assertEqual(report["summary"]["applied"], 0)
            item = report["items"][0]
            self.assertEqual(item["run_id"], "legacy-run")
            self.assertEqual(item["queue_block"], 1)
            self.assertTrue(item["can_resume"])
            self.assertFalse(item["applied"])
            self.assertEqual(item["resume_readiness"], "ready_to_apply")
            self.assertEqual(item["blocking_preconditions"], 0)
            self.assertEqual(item["rerun_from"], "experiments")
            self.assertEqual(item["repair_items"], 1)
            self.assertGreater(item["priority_score"], 0)
            self.assertTrue(item["execution_reapproval_required"])
            self.assertFalse((run_dir / "12-repair-resume-plan.json").exists())
            self.assertIn("Repair Resume Backlog", rendered)
            self.assertIn("前置条件摘要", rendered)
            self.assertIn("legacy-run", rendered)
            self.assertIn("不删除产物、不批准 gate、不恢复 pipeline、不执行实验", rendered)
            self.assertNotIn("private repair action", rendered)

    def test_existing_plan_counts_pending_gate_requirements(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "review-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "needs_repair",
                    "summary": {"total": 2, "block": 1, "high": 1, "medium": 0},
                    "items": [],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "can_resume": True,
                    "applied": False,
                    "rerun_from": "literature_review",
                    "repair_items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}],
                    "retrieval_repair_tasks": [{"task_id": "LIT-001"}],
                    "artifacts_to_remove": ["01-context.json"],
                    "directories_to_remove": [],
                    "review_reapproval_required": True,
                    "execution_reapproval_required": True,
                },
            )

            report = build_repair_resume_backlog(runs_dir)

            self.assertEqual(report["summary"]["review_reapproval_required"], 1)
            self.assertEqual(report["summary"]["execution_reapproval_required"], 1)
            self.assertEqual(report["summary"]["ready_to_apply"], 0)
            self.assertEqual(report["summary"]["needs_preconditions"], 1)
            self.assertEqual(report["items"][0]["repair_items"], 2)
            self.assertEqual(report["items"][0]["retrieval_repair_tasks"], 1)
            self.assertEqual(report["items"][0]["artifacts_to_remove"], 1)
            self.assertEqual(report["items"][0]["resume_readiness"], "needs_preconditions")
            self.assertIn("missing_literature_repair_config", report["items"][0]["precondition_codes"])

    def test_benchmark_backlog_requires_manifest_recommendation_before_apply(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "benchmark-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 1, "block": 1},
                    "items": [
                        {
                            "task_id": "RQ-BENCH",
                            "severity": "block",
                            "category": "benchmark_result_schema",
                            "source_artifact": "04-benchmark-result-schema-audit.json",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )

            report = build_repair_resume_backlog(runs_dir)
            item = report["items"][0]

        self.assertEqual(report["summary"]["ready_to_apply"], 0)
        self.assertEqual(report["summary"]["needs_preconditions"], 1)
        self.assertEqual(item["resume_readiness"], "needs_preconditions")
        self.assertIn("missing_benchmark_manifest_recommendation", item["precondition_codes"])
        self.assertIn("benchmark_manifest", item["required_config"])

    def test_benchmark_backlog_requires_paper_grade_manifest_set_before_apply(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "paper-grade-benchmark-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 1, "high": 1},
                    "items": [
                        {
                            "task_id": "RQ-BENCH-PAPER",
                            "severity": "high",
                            "category": "benchmark_evidence",
                            "source_artifact": "04-benchmark-evidence-audit.json",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "03-benchmark-adapters.json",
                {
                    "status": "ready",
                    "manifest_paths": ["benchmarks/candidate.json"],
                    "paper_grade_status": "review_required",
                    "paper_grade_issues": ["缺少 baseline/ablation role。"],
                    "paper_grade_repair_suggestions": [{"kind": "missing_manifest_role", "role": "baseline", "target": "role:baseline"}],
                },
            )

            report = build_repair_resume_backlog(runs_dir)
            item = report["items"][0]

        self.assertEqual(report["summary"]["ready_to_apply"], 0)
        self.assertEqual(report["summary"]["needs_preconditions"], 1)
        self.assertEqual(item["resume_readiness"], "needs_preconditions")
        self.assertNotIn("missing_benchmark_manifest_recommendation", item["precondition_codes"])
        self.assertIn("missing_paper_grade_benchmark_manifest_set", item["precondition_codes"])
        self.assertIn("paper_grade_benchmark_manifest", item["required_config"])
        self.assertIn("benchmark_manifest_scaffold_available", item["triage_notes"])

    def test_release_backlog_requires_real_release_values_before_apply(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "release-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Iris", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 1, "high": 1},
                    "items": [
                        {
                            "task_id": "RQ-REL",
                            "severity": "high",
                            "category": "release_metadata",
                            "source_artifact": "10-release-metadata.json",
                            "rerun_from": "final_readiness",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "10-release-metadata.json",
                {
                    "status": "needs_release_metadata",
                    "recommended_config": {
                        "status": "needs_input",
                        "required_fields": ["release_code_repository_url", "release_code_archive_doi"],
                        "recommended_fields": [],
                        "cli_args": ["--release-code-repository-url", "--release-code-archive-doi"],
                        "config_fields": {"code_repository_url": "", "code_archive_doi": ""},
                    },
                },
            )

            report = build_repair_resume_backlog(runs_dir)
            item = report["items"][0]

        self.assertEqual(report["summary"]["ready_to_apply"], 0)
        self.assertEqual(report["summary"]["needs_preconditions"], 1)
        self.assertEqual(item["resume_readiness"], "needs_preconditions")
        self.assertIn("release_metadata", item["required_config"])
        self.assertIn("release_metadata_values_required", item["precondition_codes"])
        self.assertIn("release_metadata_cli_args_available", item["triage_notes"])

    def test_includes_gold_doctor_plan_without_active_repair_queue(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "doctor-candidate-run"
            doctor_report = runs_dir / "gold-doctor" / "00-gold-run-doctor.json"
            run_dir.mkdir(parents=True)
            doctor_report.parent.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Iris", "stage": "completed"})
            write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0}})
            write_json(doctor_report, {"status": "blocked"})
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "can_resume": True,
                    "applied": False,
                    "rerun_from": "submission_package",
                    "repair_plan_sources": ["gold-run-doctor"],
                    "doctor_report_path": str(doctor_report),
                    "repair_items": [
                        {
                            "task_id": "gold-doctor:submission_package",
                            "category": "submission_package",
                            "severity": "block",
                        }
                    ],
                    "commands": [
                        f"PYTHONPATH=src python3 -m research_agent repair-resume {run_dir} --gold-run-doctor-report {doctor_report}"
                    ],
                },
            )

            report = build_repair_resume_backlog(runs_dir)
            rendered = render_repair_resume_backlog_markdown(report)

            self.assertEqual(report["summary"]["total"], 1)
            self.assertEqual(report["summary"]["ready_to_apply"], 1)
            item = report["items"][0]
            self.assertEqual(item["run_id"], "doctor-candidate-run")
            self.assertEqual(item["queue_status"], "pass")
            self.assertEqual(item["repair_plan_sources"], ["gold-run-doctor"])
            self.assertTrue(item["doctor_report"])
            self.assertEqual(item["doctor_report_path"], str(doctor_report))
            self.assertEqual(item["resume_readiness"], "ready_to_apply")
            self.assertIn("--apply", item["command"])
            self.assertIn("--gold-run-doctor-report", item["command"])
            self.assertIn("gold-run-doctor", rendered)
            self.assertIn("--gold-run-doctor-report", rendered)


if __name__ == "__main__":
    unittest.main()
