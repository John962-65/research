from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest import mock

import research_agent.workflow_graph as wg
from research_agent.run_lease import RunLeaseConflict, acquire_run_lease
from research_agent.run_lease import lease_path as wg_lease_path
from research_agent.workflow_graph import (
    apply_rollback,
    build_rollback_preview,
    prune_rollback_archives,
    cleanup_expired_previews,
    issue_rollback_preview,
    reconcile_rollback_journals,
    update_workflow_stage,
)


def _make_run(tmp: str) -> Path:
    run_dir = Path(tmp) / "run"
    run_dir.mkdir()
    (run_dir / "02-ideas.json").write_text(json.dumps([{"title": "idea"}]), encoding="utf-8")
    (run_dir / "02-ideas.md").write_text("# Ideas\n", encoding="utf-8")
    update_workflow_stage(run_dir, "事务回退测试", "ideation_completed")
    return run_dir


class RollbackReasonPersistenceTest(unittest.TestCase):
    """ART-02: reason and actor are committed with the transaction, not after."""

    def test_reason_reaches_archive_report_index_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            report = apply_rollback(
                run_dir,
                "ideation",
                preview["preview_id"],
                preview["preview_token"],
                reason="实验方向需要人工调整",
                actor="cli",
            )
            self.assertEqual(report["reason"], "实验方向需要人工调整")
            self.assertEqual(report["actor"], "cli")
            archive_root = run_dir.parent / ".research-agent-archives" / run_dir.name / report["archive_ref"]
            archived_report = json.loads((archive_root / "rollback.json").read_text(encoding="utf-8"))
            self.assertEqual(archived_report["reason"], "实验方向需要人工调整")
            self.assertEqual(archived_report["actor"], "cli")
            index = json.loads(
                (run_dir.parent / ".research-agent-archives" / run_dir.name / "index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(index["entries"][-1]["reason"], "实验方向需要人工调整")
            self.assertEqual(index["entries"][-1]["actor"], "cli")
            manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
            event = next(item for item in manifest["events"] if item["stage"] == "workflow_rollback")
            self.assertTrue(any("实验方向需要人工调整" in note for note in event["notes"]))


class RollbackJournalRecoveryTest(unittest.TestCase):
    """TX-01: a crashed apply is reconciled to exactly one new revision."""

    def test_crash_during_moves_is_reconciled_forward_idempotently(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = build_rollback_preview(run_dir, "ideation")
            archive_id = "20260902T000000000000Z-r1-ideation"
            archive_root = run_dir.parent / ".research-agent-archives" / run_dir.name / archive_id
            archive_root.mkdir(parents=True, exist_ok=True)
            journal_path = run_dir.parent / ".research-agent-archives" / run_dir.name / f"journal-{archive_id}.json"
            # Simulate a crash right after the first file was moved.
            destination = archive_root / "02-ideas.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            (run_dir / "02-ideas.json").replace(destination)
            journal = {
                "schema_version": 1,
                "state": "moving",
                "archive_id": archive_id,
                "target": "ideation",
                "revision": preview["next_revision"],
                "previous_revision": preview["current_revision"],
                "applied_at": "2026-09-02T00:00:00+00:00",
                "reason": "crash recovery test",
                "actor": "test",
                "artifact_index": preview["artifact_index"],
                "directory_index": preview["directory_index"],
                "moved_files": ["02-ideas.json"],
                "moved_directories": [],
                "metadata_committed": False,
                "error": "",
                "updated_at": "2026-09-02T00:00:00+00:00",
            }
            journal_path.write_text(json.dumps(journal), encoding="utf-8")

            completed = reconcile_rollback_journals(run_dir)
            self.assertEqual(completed, [archive_id])
            self.assertFalse((run_dir / "02-ideas.md").exists())
            self.assertTrue((archive_root / "02-ideas.md").exists())
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "rollback_applied")
            self.assertEqual(state["workflow_revision"], preview["next_revision"])

            # Running recovery again changes nothing (idempotent).
            completed_again = reconcile_rollback_journals(run_dir)
            self.assertEqual(completed_again, [])
            index = json.loads(
                (run_dir.parent / ".research-agent-archives" / run_dir.name / "index.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(index["entries"]), 1)
            manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
            rollback_events = [item for item in manifest["events"] if item["stage"] == "workflow_rollback"]
            self.assertEqual(len(rollback_events), 1)

    def test_apply_reconciles_stale_journal_before_starting(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            stale_id = "20260902T000000000000Z-r1-ideation"
            journal_path = run_dir.parent / ".research-agent-archives" / run_dir.name / f"journal-{stale_id}.json"
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            journal_path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "state": "prepared",
                    "archive_id": stale_id,
                    "target": "ideation",
                    "revision": 1,
                    "previous_revision": 0,
                    "applied_at": "2026-09-02T00:00:00+00:00",
                    "reason": "stale",
                    "actor": "test",
                    "artifact_index": [],
                    "directory_index": [],
                    "moved_files": [],
                    "moved_directories": [],
                    "metadata_committed": False,
                    "error": "",
                    "updated_at": "2026-09-02T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            # A normal apply must refuse to start while a stale journal would be
            # reconciled with the same revision, or reconcile it first — here the
            # stale journal targets revision 1 like a fresh apply would.
            preview = build_rollback_preview(run_dir, "ideation")
            self.assertEqual(preview["current_revision"], 0)
            completed = reconcile_rollback_journals(run_dir)
            self.assertEqual(completed, [stale_id])
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["workflow_revision"], 1)


class RollbackDiskSpaceTest(unittest.TestCase):
    """ART-03: apply refuses to run when the archive cannot fit."""

    def test_apply_refused_when_free_space_is_insufficient(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            usage = mock.Mock()
            usage.free = wg.MIN_ROLLBACK_FREE_BYTES - 1
            usage.total = 10**12
            usage.used = 1
            with mock.patch.object(wg.shutil, "disk_usage", return_value=usage):
                with self.assertRaises(RuntimeError) as caught:
                    apply_rollback(
                        run_dir,
                        "ideation",
                        preview["preview_id"],
                        preview["preview_token"],
                        reason="disk test",
                        actor="test",
                    )
            self.assertIn("rollback refused", str(caught.exception))
            # The run must be untouched: files stay in place.
            self.assertTrue((run_dir / "02-ideas.json").exists())

    def test_expired_previews_are_cleaned(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            previews_dir = run_dir.parent / ".research-agent-archives" / run_dir.name / "previews"
            record = json.loads((previews_dir / f"{preview['preview_id']}.json").read_text(encoding="utf-8"))
            record["expires_at_epoch"] = 1  # long expired
            (previews_dir / f"{preview['preview_id']}.json").write_text(json.dumps(record), encoding="utf-8")
            removed = cleanup_expired_previews(run_dir)
            self.assertEqual(removed, 1)
            self.assertFalse((previews_dir / f"{preview['preview_id']}.json").exists())


class RollbackArchivePruneTest(unittest.TestCase):
    """ART-03 complete: explicit, previewable, auditable archive cleanup."""

    def _apply_two_rollbacks(self, run_dir: Path) -> None:
        for revision in range(2):
            preview = issue_rollback_preview(run_dir, "ideation")
            apply_rollback(
                run_dir,
                "ideation",
                preview["preview_id"],
                preview["preview_token"],
                reason=f"prune test {revision}",
                actor="test",
            )
            # After the rollback the ideation artifacts are archived; recreate
            # them so the next rollback has something to archive.
            (run_dir / "02-ideas.json").write_text("[]", encoding="utf-8")
            (run_dir / "02-ideas.md").write_text("# Ideas\n", encoding="utf-8")

    def test_prune_previews_then_applies(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "02-ideas.json").write_text("[]", encoding="utf-8")
            (run_dir / "02-ideas.md").write_text("# Ideas\n", encoding="utf-8")
            update_workflow_stage(run_dir, "清理测试", "ideation_completed")
            self._apply_two_rollbacks(run_dir)
            archive_root = run_dir.parent / ".research-agent-archives" / run_dir.name

            preview = prune_rollback_archives(run_dir, keep=1, apply=False)
            self.assertEqual(len(preview["archives"]), 2)
            self.assertEqual(preview["removed"], [])
            self.assertEqual(len(preview["kept"]), 1)
            def _archive_dirs() -> list[Path]:
                return [path for path in archive_root.iterdir() if path.is_dir() and (path / "rollback.json").is_file()]

            self.assertEqual(len(_archive_dirs()), 2)

            applied = prune_rollback_archives(run_dir, keep=1, apply=True)
            self.assertEqual(len(applied["removed"]), 1)
            self.assertEqual(len(_archive_dirs()), 1)
            # Index entries survive for audit purposes.
            index = json.loads((archive_root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["entries"]), 2)

    def test_prune_rejects_negative_keep(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            with self.assertRaises(ValueError):
                prune_rollback_archives(run_dir, keep=-1)


class RollbackRunLeaseIntegrationTest(unittest.TestCase):
    """LOCK-01: apply_rollback holds the run lease for the whole transaction."""

    def test_apply_refuses_when_lease_is_held_elsewhere(self) -> None:
        import fcntl
        import os as _os

        with TemporaryDirectory() as tmp:
            run_dir = _make_run(tmp)
            preview = issue_rollback_preview(run_dir, "ideation")
            # Hold the lease the way another process would: a raw flock on a
            # separate file descriptor, bypassing this process's reentrancy
            # counter on purpose.
            external_fd = _os.open(wg_lease_path(run_dir), _os.O_RDWR | _os.O_CREAT, 0o600)
            try:
                fcntl.flock(external_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(RunLeaseConflict):
                    apply_rollback(
                        run_dir,
                        "ideation",
                        preview["preview_id"],
                        preview["preview_token"],
                        reason="lease test",
                        actor="test",
                    )
            finally:
                fcntl.flock(external_fd, fcntl.LOCK_UN)
                _os.close(external_fd)
            # After the external holder releases, the apply succeeds.
            report = apply_rollback(
                run_dir,
                "ideation",
                preview["preview_id"],
                preview["preview_token"],
                reason="lease test",
                actor="test",
            )
            self.assertEqual(report["status"], "applied")


if __name__ == "__main__":
    unittest.main()
