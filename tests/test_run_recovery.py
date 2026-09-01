from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.run_recovery import build_run_recovery_plan, render_run_recovery_plan_markdown, write_run_recovery_plan_artifacts


class RunRecoveryTest(unittest.TestCase):
    def test_failed_run_recovery_uses_diagnostic_actions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "failed"})
            write_json(
                run_dir / "run-diagnostics.json",
                {
                    "category": "llm_configuration",
                    "summary": "模型名未配置",
                    "recommended_actions": ["填写模型名", "重新预检"],
                },
            )

            report = write_run_recovery_plan_artifacts(run_dir, status="failed")
            rendered = render_run_recovery_plan_markdown(report)

            self.assertEqual(report["category"], "failed")
            self.assertIn("填写模型名", report["recommended_actions"])
            self.assertTrue(any("resume" in item for item in report["commands"]))
            self.assertFalse(any("--llm-api-key" in item for item in report["commands"]))
            self.assertTrue((run_dir / "run-recovery-plan.json").exists())
            self.assertTrue((run_dir / "run-recovery-plan.md").exists())
            self.assertIn("Run 恢复计划", rendered)

    def test_review_revision_recovery_points_to_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "review_revision_requested"})
            write_json(run_dir / "approval.json", {"topic": "机械臂路径规划", "revision_requested": True, "notes": "补 DOI"})

            report = build_run_recovery_plan(run_dir, status="revision_requested")

            self.assertEqual(report["category"], "review_revision_requested")
            self.assertEqual(report["approval_state"], "revision_requested")
            self.assertTrue(any("approve" in item for item in report["commands"]))
            self.assertTrue(any("补 DOI" in item for item in report["recommended_actions"]))

    def test_cancelled_run_recovery_does_not_suggest_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "cancelled"})
            write_json(run_dir / "cancel.json", {"cancelled": True, "reason": "unit_test"})

            report = build_run_recovery_plan(run_dir, status="cancelled")

            self.assertEqual(report["category"], "cancelled")
            self.assertFalse(any(" resume " in f" {item} " for item in report["commands"]))
            self.assertTrue(any("新 run" in item for item in report["recommended_actions"]))

    def test_execution_approval_recovery_points_to_execution_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_execution_approval"})
            write_json(run_dir / "approval.json", {"approved": True})
            write_json(run_dir / "03-execution-approval.json", {"approved": False, "execution_mode": "local", "stage": "awaiting_execution_approval"})

            report = build_run_recovery_plan(run_dir)

            self.assertEqual(report["category"], "awaiting_execution_approval")
            self.assertEqual(report["execution_approval_state"], "pending")
            self.assertTrue(any("approve-execution" in item for item in report["commands"]))
            self.assertTrue(any("local" in item for item in report["recommended_actions"]))


if __name__ == "__main__":
    unittest.main()
