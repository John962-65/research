from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.human_gate_audit import (
    HUMAN_GATE_AUDIT_JSON,
    HUMAN_GATE_AUDIT_MD,
    build_human_gate_audit_report,
    render_human_gate_audit_markdown,
    write_human_gate_audit_artifacts,
)


class HumanGateAuditTest(unittest.TestCase):
    def test_blocks_downstream_without_review_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": []})
            write_json(run_dir / "02-ideas.json", [{"title": "idea"}])

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertEqual(report["summary"]["downstream_artifacts"], 1)
            self.assertTrue(any("未批准" in item for item in report["blocking_issues"]))

    def test_waiting_review_requires_human_but_does_not_block_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertEqual(report["blocking_issues"], [])
            self.assertTrue(any("等待 review gate" in item for item in report["manual_tasks"]))

    def test_blocks_execution_without_execution_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "experiments_completed"})
            write_json(run_dir / "approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(run_dir / "03-execution-approval.json", {"approved": False, "execution_mode": "benchmark"})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "benchmark"}, "runs": [{"id": "r1"}]})
            write_json(run_dir / "04-results.json", {"metrics": []})

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertEqual(report["summary"]["execution_artifacts"], 1)
            self.assertTrue(any("03-execution-approval" in item for item in report["blocking_issues"]))

    def test_repair_resume_blocks_stale_review_reapproval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})
            write_json(
                run_dir / "approval.json",
                {
                    "approved": True,
                    "approved_at": "2026-06-11T09:00:00+00:00",
                    "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    "history": [{"action": "approved", "at": "2026-06-11T09:00:00+00:00"}],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": True,
                    "applied_at": "2026-06-11T10:00:00+00:00",
                    "review_reapproval_required": True,
                    "execution_reapproval_required": False,
                },
            )

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(report["summary"]["repair_resume_applied"])
            self.assertTrue(report["summary"]["review_reapproval_required"])
            self.assertTrue(any("批准发生在修复之后" in item for item in report["blocking_issues"]))

    def test_repair_resume_waits_when_review_approval_was_reset(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": True,
                    "applied_at": "2026-06-11T10:00:00+00:00",
                    "review_reapproval_required": True,
                    "execution_reapproval_required": False,
                },
            )

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertEqual(report["blocking_issues"], [])
            self.assertTrue(any("重新批准" in item for item in report["manual_tasks"]))

    def test_repair_resume_passes_when_reapproved_after_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})
            write_json(
                run_dir / "approval.json",
                {
                    "approved": True,
                    "approved_at": "2026-06-11T11:00:00+00:00",
                    "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    "history": [{"action": "approved", "at": "2026-06-11T11:00:00+00:00"}],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": True,
                    "applied_at": "2026-06-11T10:00:00+00:00",
                    "review_reapproval_required": True,
                    "execution_reapproval_required": False,
                },
            )

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "pass")
            repair_check = next(item for item in report["checks"] if item["gate"] == "repair_resume_reapproval")
            self.assertIn("review_reapproved_after_repair=True", repair_check["evidence"])

    def test_repair_resume_blocks_stale_execution_reapproval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_execution_approval"})
            write_json(run_dir / "approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(
                run_dir / "03-execution-approval.json",
                {
                    "approved": True,
                    "approved_at": "2026-06-11T09:00:00+00:00",
                    "execution_mode": "benchmark",
                    "history": [{"action": "execution_approved", "at": "2026-06-11T09:00:00+00:00"}],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": True,
                    "applied_at": "2026-06-11T10:00:00+00:00",
                    "review_reapproval_required": False,
                    "execution_reapproval_required": True,
                },
            )

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(report["summary"]["execution_reapproval_required"])
            self.assertTrue(any("03-execution-approval.json 未证明批准发生在修复之后" in item for item in report["blocking_issues"]))

    def test_repair_resume_preview_does_not_require_reapproval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})
            write_json(run_dir / "approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": False,
                    "review_reapproval_required": True,
                    "execution_reapproval_required": True,
                },
            )

            report = build_human_gate_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["summary"]["repair_resume_applied"])

    def test_passes_when_gates_are_approved(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "experiments_completed"})
            write_json(run_dir / "approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]})
            write_json(run_dir / "03-execution-approval.json", {"approved": True, "execution_mode": "benchmark"})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "benchmark"}, "runs": [{"id": "r1"}]})
            write_text(run_dir / "04-results.csv", "metric,value\nsuccess,1\n")

            report = write_human_gate_audit_artifacts("机械臂路径规划", run_dir)
            rendered = render_human_gate_audit_markdown(report)

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / HUMAN_GATE_AUDIT_JSON).exists())
            self.assertTrue((run_dir / HUMAN_GATE_AUDIT_MD).exists())
            self.assertIn("Human Gate Audit", rendered)


if __name__ == "__main__":
    unittest.main()
