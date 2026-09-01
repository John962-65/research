from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.repair_resolution_audit import (
    REPAIR_RESOLUTION_AUDIT_JSON,
    REPAIR_RESOLUTION_AUDIT_MD,
    build_repair_resolution_audit,
    render_repair_resolution_audit_markdown,
    write_repair_resolution_audit_artifacts,
)


class RepairResolutionAuditTest(unittest.TestCase):
    def test_not_applicable_without_applied_repair_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "12-repair-queue.json", {"status": "pass", "items": []})

            report = build_repair_resolution_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "not_applicable")
            self.assertFalse(report["blocking_issues"])

    def test_passes_when_original_repair_items_are_gone(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_resume_plan(run_dir)
            write_json(run_dir / "12-repair-queue.json", {"status": "pass", "items": []})

            report = write_repair_resolution_audit_artifacts("机械臂路径规划", run_dir)
            rendered = render_repair_resolution_audit_markdown(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(len(report["resolved_items"]), 1)
            self.assertFalse(report["remaining_items"])
            self.assertIn("修复闭环审计", rendered)
            self.assertTrue((run_dir / REPAIR_RESOLUTION_AUDIT_JSON).exists())
            self.assertTrue((run_dir / REPAIR_RESOLUTION_AUDIT_MD).exists())

    def test_blocks_when_original_source_category_still_open(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_resume_plan(run_dir)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-002",
                            "severity": "block",
                            "category": "idea_experiment_contract",
                            "source_artifact": "03-idea-experiment-contract.json",
                            "action": "选中 idea 没有 evidence_keys。",
                            "status": "open",
                        }
                    ],
                },
            )

            report = build_repair_resolution_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(report["remaining_items"])
            self.assertTrue(any("evidence_keys" in issue for issue in report["blocking_issues"]))


def _write_resume_plan(run_dir: Path) -> None:
    write_json(
        run_dir / "12-repair-resume-plan.json",
        {
            "applied": True,
            "rerun_from": "experiment_plan",
            "repair_items": [
                {
                    "task_id": "RQ-001",
                    "severity": "block",
                    "category": "idea_experiment_contract",
                    "source_artifact": "03-idea-experiment-contract.json",
                    "action": "修复 idea 到实验计划契约。",
                }
            ],
        },
    )


if __name__ == "__main__":
    unittest.main()
