from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.provenance import (
    ACTIVE_BRANCH_ID,
    LEGACY_BRANCH_ID,
    RunManifestRecorder,
    active_revision,
    event_in_active_branch,
    filter_active_events,
)
from research_agent.run_integrity_audit import _human_gate_checks
from research_agent.workflow_graph import build_rollback_preview, issue_rollback_preview, apply_rollback, update_workflow_stage


def _event(stage: str, *, revision: int | None = None, branch: str | None = None) -> dict:
    event = {"stage": stage, "status": "completed"}
    if revision is not None:
        event["revision"] = revision
    if branch is not None:
        event["branch_id"] = branch
    return event


class ActiveRevisionFilterTest(unittest.TestCase):
    def test_stamped_events_filter_by_active_revision(self) -> None:
        events = [
            _event("review_approval", revision=0, branch=ACTIVE_BRANCH_ID),
            _event("ideation", revision=0, branch=ACTIVE_BRANCH_ID),
            _event("ideation", revision=1, branch=ACTIVE_BRANCH_ID),
        ]
        active = filter_active_events(events, active_rev=1)
        self.assertEqual([event["stage"] for event in active], ["ideation"])

    def test_legacy_events_count_only_before_first_rollback(self) -> None:
        legacy_events = [_event("review_approval"), _event("ideation")]
        self.assertEqual(len(filter_active_events(legacy_events, active_rev=0)), 2)
        self.assertEqual(filter_active_events(legacy_events, active_rev=1), [])

    def test_event_in_active_branch_rejects_other_branch(self) -> None:
        event = _event("review_approval", revision=1, branch="side-branch")
        self.assertFalse(event_in_active_branch(event, active_rev=1))


class ManifestSchemaV2Test(unittest.TestCase):
    def test_recorder_stamps_revision_node_and_event_id(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            update_workflow_stage(out_dir, "主题", "literature_review_completed")  # revision 0
            recorder = RunManifestRecorder(out_dir, "主题")
            recorder.record("literature_synthesis", inputs=["x"], outputs=["01-context.json"])
            data = json.loads((out_dir / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 2)
            event = data["events"][0]
            self.assertEqual(event["revision"], 0)
            self.assertEqual(event["branch_id"], ACTIVE_BRANCH_ID)
            self.assertEqual(event["node_id"], "literature_context")
            self.assertEqual(event["attempt_id"], "literature_context-r0")
            self.assertTrue(event["event_id"])
            artifact = data["artifacts"][0]
            self.assertEqual(artifact["revision"], 0)
            self.assertEqual(artifact["branch_id"], ACTIVE_BRANCH_ID)

    def test_v1_manifest_round_trips_as_legacy(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            v1 = {
                "topic": "旧 run",
                "status": "completed",
                "started_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:01+00:00",
                "events": [{"stage": "ideation", "status": "completed"}],
                "artifacts": [{"path": "02-ideas.json", "bytes": 3, "sha256": "a" * 64}],
            }
            (out_dir / "run-manifest.json").write_text(json.dumps(v1), encoding="utf-8")
            recorder = RunManifestRecorder(out_dir, "旧 run")
            self.assertEqual(recorder.events[0].revision, 0)
            self.assertEqual(recorder.events[0].branch_id, LEGACY_BRANCH_ID)
            recorder.record("literature_synthesis")
            data = json.loads((out_dir / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["events"][0]["branch_id"], LEGACY_BRANCH_ID)
            self.assertEqual(data["events"][1]["branch_id"], ACTIVE_BRANCH_ID)


class ActiveRevisionEvidenceTest(unittest.TestCase):
    """REV-01 acceptance: revision 0 success must not back revision 1 gates."""

    def test_rolled_back_run_cannot_borrow_old_revision_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            # Revision 0: literature approved, ideas generated, experiments done.
            update_workflow_stage(run_dir, "回退借用测试", "ideation_completed")
            recorder = RunManifestRecorder(run_dir, "回退借用测试")
            recorder.record("review_approval")
            recorder.record("ideation")
            # Roll back to ideation: revision becomes 1, revision-0 events stay
            # in the accumulated manifest but no longer own the gate.
            preview = issue_rollback_preview(run_dir, "ideation")
            apply_rollback(
                run_dir,
                "ideation",
                preview["preview_id"],
                preview["preview_token"],
                reason="revision borrowing test",
                actor="test",
            )
            self.assertEqual(active_revision(run_dir), 1)
            # Revision 1: downstream artifacts and events exist but the gate was
            # not re-approved yet.
            (run_dir / "02-ideas.json").write_text("[]", encoding="utf-8")
            recorder2 = RunManifestRecorder(run_dir, "回退借用测试")
            recorder2.record("ideation")
            manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
            stages = [event["stage"] for event in manifest["events"]]
            self.assertEqual(
                stages,
                ["review_approval", "ideation", "workflow_rollback", "ideation"],
            )

            checks = _human_gate_checks(run_dir, {}, manifest)
            order = next(item for item in checks if item["name"] == "manifest_order")
            # With active-revision filtering the revision-0 approval is not
            # visible, so the missing approval must block instead of passing
            # on the strength of revision-0 events.
            self.assertEqual(order["status"], "block")

    def test_unstamped_v1_events_still_pass_before_any_rollback(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "02-ideas.json").write_text("[]", encoding="utf-8")
            manifest = {
                "events": [
                    {"stage": "review_approval", "status": "completed"},
                    {"stage": "ideation", "status": "completed"},
                ]
            }
            checks = _human_gate_checks(run_dir, {"approved": True}, manifest)
            order = next(item for item in checks if item["name"] == "manifest_order")
            self.assertEqual(order["status"], "pass")


if __name__ == "__main__":
    unittest.main()
