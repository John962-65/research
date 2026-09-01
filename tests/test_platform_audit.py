from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.platform_audit import build_platform_audit, render_platform_audit_markdown, write_platform_audit


class PlatformAuditTest(unittest.TestCase):
    def test_platform_audit_prioritizes_cross_run_capability_gaps(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "weak-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-10T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 1, "total_papers": 2, "confidence_status": "warn"})
            write_json(run_dir / "01-context.json", {"citations": [{"key": "thin"}]})
            write_json(run_dir / "01-literature-rescue-plan.json", {"status": "needs_source_repair", "rescue_queries": [{"query": "robot arm planning"}]})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "simulated"}})
            write_json(run_dir / "04-result-validation.json", {"status": "block", "blocking_issues": ["缺少共同指标"], "warnings": []})
            write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "block", "blocking_issues": ["缺少 adapter provenance"], "manual_tasks": []})
            write_json(run_dir / "12-repair-queue.json", {"status": "blocked_repair_required", "summary": {"total": 1, "block": 1}, "items": [{"task_id": "RQ-1"}]})
            write_json(run_dir / "13-run-economics-audit.json", {"status": "block", "summary": {"total_calls": 0, "failed_calls": 0}, "blocking_issues": ["LLM ledger 缺失"]})
            write_json(run_dir / "13-agent-observability-audit.json", {"status": "block", "summary": {"llm_failed_calls": 0}, "blocking_issues": ["approval trace 缺失"]})
            write_json(run_dir / "13-open-source-compliance.json", {"status": "block", "score": 0.4, "checked_lessons": 10})
            write_json(run_dir / "14-run-integrity-audit.json", {"status": "block", "summary": {"block": 1}, "blocking_issues": ["gate 缺失"]})
            write_json(run_dir / "14-final-handoff.json", {"status": "blocked", "blocking_issues": ["ZIP 缺失"], "manual_tasks": []})

            report = build_platform_audit(runs_dir)
            rendered = render_platform_audit_markdown(report)

        gap_ids = {gap.gap_id for gap in report.gaps}
        self.assertEqual(report.status, "blocked")
        self.assertIn("literature_rag_quality", gap_ids)
        self.assertIn("human_review_and_execution_gate", gap_ids)
        self.assertIn("real_benchmark_execution", gap_ids)
        self.assertIn("llm_trace_and_budget_observability", gap_ids)
        self.assertIn("repair_resume_backlog", gap_ids)
        self.assertIn("submission_release_readiness", gap_ids)
        self.assertIn("open_source_lesson_contract", gap_ids)
        open_source_gap = next(gap for gap in report.gaps if gap.gap_id == "open_source_lesson_contract")
        self.assertTrue(any("repair_queue_open_source_item=missing" in item for item in open_source_gap.evidence))
        self.assertLess(report.capability_scores["literature"], 1.0)
        self.assertIn("平台能力审计", rendered)
        self.assertIn("PaperQA2", rendered)
        self.assertIn("AgentLaboratory", rendered)

    def test_platform_audit_can_report_stable_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "stable-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "稳定 run", "stage": "completed", "updated_at": "2026-06-10T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 8, "total_papers": 10, "confidence_status": "pass"})
            write_json(run_dir / "01-context.json", {"citations": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}, {"key": "e"}]})
            write_json(run_dir / "approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "benchmark"}})
            write_json(run_dir / "03-execution-approval.json", {"approved": True, "execution_mode": "benchmark", "notes": "已检查 benchmark manifest 和安全审计", "blocks": ["experiment_execution"]})
            write_json(run_dir / "04-statistics.json", {"comparisons": [{"metric": "success", "direction": "candidate_better"}]})
            write_json(run_dir / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
            write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
            write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "summary": {"total_calls": 3, "failed_calls": 0}, "blocking_issues": []})
            write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "summary": {"llm_failed_calls": 0}, "blocking_issues": []})
            write_json(run_dir / "13-open-source-compliance.json", {"status": "pass", "score": 1.0, "checked_lessons": 10})
            write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"block": 0}, "blocking_issues": []})
            write_json(run_dir / "14-final-handoff.json", {"status": "ready_for_human_handoff", "blocking_issues": [], "manual_tasks": []})

            report = build_platform_audit(runs_dir)
            json_path, md_path = write_platform_audit(report, Path(tmp))

            data = json.loads(json_path.read_text(encoding="utf-8"))
            md_exists = md_path.exists()

        self.assertEqual(report.status, "stable")
        self.assertEqual(report.gaps, [])
        self.assertEqual(data["status"], "stable")
        self.assertTrue(md_exists)

    def test_platform_audit_blocks_invalid_final_handoff_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "invalid-zip-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "坏 ZIP", "stage": "completed", "updated_at": "2026-06-10T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 8, "total_papers": 10, "confidence_status": "pass"})
            write_json(run_dir / "01-context.json", {"citations": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}, {"key": "e"}]})
            write_json(run_dir / "approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "benchmark"}})
            write_json(run_dir / "03-execution-approval.json", {"approved": True, "execution_mode": "benchmark", "blocks": ["experiment_execution"]})
            write_json(run_dir / "04-statistics.json", {"comparisons": [{"metric": "success", "direction": "candidate_better"}]})
            write_json(run_dir / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
            write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "blocking_issues": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "blocking_issues": [], "manual_tasks": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "blocking_issues": [], "manual_tasks": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "blocking_issues": [], "manual_tasks": []})
            write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "summary": {"total_calls": 3, "failed_calls": 0}, "blocking_issues": []})
            write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "summary": {"llm_failed_calls": 0}, "blocking_issues": []})
            write_json(run_dir / "13-open-source-compliance.json", {"status": "pass", "score": 1.0, "checked_lessons": 10})
            write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"block": 0}, "blocking_issues": []})
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "package_zip_exists": True,
                    "package_zip_valid": False,
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            report = build_platform_audit(runs_dir)
            rendered = render_platform_audit_markdown(report)

        gap = next(gap for gap in report.gaps if gap.gap_id == "submission_release_readiness")
        self.assertEqual(report.status, "blocked")
        self.assertEqual(gap.severity, "block")
        self.assertTrue(any("zip_valid=N" in item for item in gap.evidence))
        self.assertIn("submission_release_readiness", rendered)


if __name__ == "__main__":
    unittest.main()
