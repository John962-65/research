from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.workflow_graph import (
    ROLLBACK_TARGETS,
    WORKFLOW_NODES,
    apply_rollback,
    begin_workflow_node,
    build_rollback_preview,
    issue_rollback_preview,
    read_workflow_status,
    rollback_options,
    update_workflow_stage,
)


def _make_run(tmp: str, stage: str = "ideation_completed") -> Path:
    run_dir = Path(tmp) / "run"
    run_dir.mkdir()
    (run_dir / "02-ideas.json").write_text(json.dumps([{"title": "idea"}]), encoding="utf-8")
    (run_dir / "02-ideas.md").write_text("# Ideas\n", encoding="utf-8")
    update_workflow_stage(run_dir, "测试主题", stage)
    return run_dir


class RollbackOptionsTest(unittest.TestCase):
    def test_gates_and_completed_never_rollback_targets(self) -> None:
        self.assertNotIn("review_gate", ROLLBACK_TARGETS)
        self.assertNotIn("execution_gate", ROLLBACK_TARGETS)
        self.assertNotIn("completed", ROLLBACK_TARGETS)

    def test_options_limited_to_reached_nodes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            targets = [item["target"] for item in rollback_options(run_dir)]
            self.assertIn("research_planning", targets)
            self.assertIn("ideation", targets)
            self.assertNotIn("experiment_plan", targets)
            self.assertNotIn("paper_writing", targets)


class RollbackPreviewTest(unittest.TestCase):
    def test_preview_lists_target_node_artifacts_and_reapproval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = build_rollback_preview(run_dir, "ideation")
            self.assertIn("02-ideas.json", preview["artifacts_to_archive"])
            self.assertIn("02-ideas.md", preview["artifacts_to_archive"])
            # The review gate sits before ideation, so rolling back to ideation
            # does not re-enter the literature approval; it does re-enter the
            # execution approval.
            self.assertFalse(preview["review_reapproval_required"])
            self.assertTrue(preview["execution_reapproval_required"])
            self.assertEqual(preview["blockers"], [])
            self.assertTrue(preview["plan_digest"])

    def test_preview_into_literature_requires_review_reapproval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = build_rollback_preview(run_dir, "literature_review")
            self.assertTrue(preview["review_reapproval_required"])
            self.assertTrue(preview["execution_reapproval_required"])

    def test_preview_rejects_unreached_target(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            with self.assertRaises(ValueError):
                build_rollback_preview(run_dir, "not_a_node")
            # Reachability is enforced when the preview is issued.
            with self.assertRaises(ValueError):
                issue_rollback_preview(run_dir, "finalization")


class RollbackApplyTest(unittest.TestCase):
    def test_issue_and_apply_archives_and_marks_state(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            self.assertEqual(preview["target"], "ideation")
            self.assertTrue(preview["preview_token"])
            self.assertGreater(preview["expires_at_epoch"], preview["issued_at_epoch"])

            report = apply_rollback(
                run_dir,
                "ideation",
                preview["preview_id"],
                preview["preview_token"],
            )
            self.assertEqual(report["status"], "applied")
            self.assertFalse((run_dir / "02-ideas.json").exists())
            self.assertFalse((run_dir / "02-ideas.md").exists())
            self.assertTrue((run_dir.parent / ".research-agent-archives" / run_dir.name / report["archive_ref"] / "02-ideas.json").exists())
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "rollback_applied")
            self.assertEqual(state["rollback_target"], "ideation")
            status = read_workflow_status(run_dir)
            self.assertEqual(status["current_node"], "ideation")
            self.assertTrue(any(event["kind"] == "rollback" for event in status["events"]))

            with self.assertRaises(RuntimeError):
                apply_rollback(run_dir, "ideation", preview["preview_id"], preview["preview_token"])

    def test_apply_rejects_wrong_token(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            with self.assertRaises(RuntimeError):
                apply_rollback(run_dir, "ideation", preview["preview_id"], "wrong-token")
            self.assertTrue((run_dir / "02-ideas.json").exists())

    def test_apply_rejects_stale_digest(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            (run_dir / "02-ideas.json").write_text(json.dumps([{"title": "changed"}]), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                apply_rollback(run_dir, "ideation", preview["preview_id"], preview["preview_token"])


class WorkflowStatusTest(unittest.TestCase):
    def test_completed_stage_maps_to_next_node_running(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            update_workflow_stage(run_dir, "测试主题", "literature_review_completed")
            status = read_workflow_status(run_dir)
            self.assertEqual(status["current_node"], "literature_context")
            self.assertEqual(status["activity_status"], "running")

    def test_begin_after_completion_refreshes_running_event(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            begin_workflow_node(run_dir, "测试主题", "ideation")
            status = read_workflow_status(run_dir)
            self.assertEqual(status["current_node"], "ideation")
            self.assertEqual(status["activity_status"], "running")
            stages = [event["stage"] for event in status["events"] if event["kind"] == "stage"]
            self.assertIn("ideation", stages)
            nodes = {node["node_id"]: node["status"] for node in status["nodes"]}
            self.assertEqual(nodes["research_planning"], "completed")
            self.assertEqual(nodes["literature_review"], "completed")
            self.assertEqual(nodes["ideation"], "running")
            self.assertEqual(nodes["experiment_plan"], "pending")
            self.assertEqual(len(WORKFLOW_NODES), len(nodes))


if __name__ == "__main__":
    unittest.main()
