from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from typing import Any, Callable
from unittest.mock import patch
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.config import AgentConfig
import research_agent.web_server as web_server


class _DormantWorkerThread:
    starts: list["_DormantWorkerThread"] = []

    def __init__(self, *, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self) -> None:
        self.starts.append(self)


class RunStoreConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir()
        self._original_root = web_server.ROOT
        self._original_runs = web_server.RUNS_DIR
        web_server.ROOT = self.root
        web_server.RUNS_DIR = self.runs_dir
        _DormantWorkerThread.starts = []

    def tearDown(self) -> None:
        web_server.ROOT = self._original_root
        web_server.RUNS_DIR = self._original_runs
        self._tmp.cleanup()

    def test_concurrent_checkpoint_resume_starts_one_worker_and_keeps_winner_config(self) -> None:
        run_dir = self._write_run("checkpoint-race", "ideation_completed")
        store = web_server.RunStore()
        entered, release, preflight_models = self._blocking_preflight("winner-model")

        with (
            patch.object(web_server, "Thread", _DormantWorkerThread),
            patch.object(web_server, "_write_resume_preflight_or_raise", side_effect=self._preflight_side_effect(entered, release, preflight_models)),
        ):
            first_result, first_error = self._race_requests(
                lambda: store.resume_with_config("checkpoint-race", self._payload("winner-model")),
                lambda: store.resume_with_config("checkpoint-race", self._payload("loser-model")),
                entered,
                release,
            )

        self.assertIsNotNone(first_result)
        self.assertIsNone(first_error)
        self.assertEqual(preflight_models, ["winner-model"])
        self.assertEqual(len(_DormantWorkerThread.starts), 1)
        self.assertEqual(_DormantWorkerThread.starts[0].args[3].llm.model, "winner-model")
        marker = json.loads((run_dir / "preflight-config.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["model"], "winner-model")

    def test_concurrent_repair_resume_starts_one_worker_and_keeps_winner_config(self) -> None:
        run_dir = self._write_run("repair-race", "completed", repair_queue=True)
        store = web_server.RunStore()
        entered, release, preflight_models = self._blocking_preflight("winner-model")

        with (
            patch.object(web_server, "Thread", _DormantWorkerThread),
            patch.object(web_server, "_write_resume_preflight_or_raise", side_effect=self._preflight_side_effect(entered, release, preflight_models)),
        ):
            first_result, first_error = self._race_requests(
                lambda: store.repair_resume_with_config("repair-race", self._payload("winner-model")),
                lambda: store.repair_resume_with_config("repair-race", self._payload("loser-model")),
                entered,
                release,
            )

        self.assertIsNotNone(first_result)
        self.assertIsNone(first_error)
        self.assertEqual(preflight_models, ["winner-model"])
        self.assertEqual(len(_DormantWorkerThread.starts), 1)
        self.assertEqual(_DormantWorkerThread.starts[0].args[3].llm.model, "winner-model")
        marker = json.loads((run_dir / "preflight-config.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["model"], "winner-model")

    def test_concurrent_inactive_approve_does_not_overwrite_winning_approval_or_config(self) -> None:
        run_dir = self._write_run("approval-race", "awaiting_review_approval", review_approval=True)
        store = web_server.RunStore()
        entered, release, preflight_models = self._blocking_preflight("winner-model")
        approval_calls: list[str] = []

        def approve(out_dir: Path, reviewer: str = "manual", notes: str = "") -> dict[str, Any]:
            approval_calls.append(reviewer)
            approval = {
                "topic": "concurrency test",
                "approved": True,
                "reviewer": reviewer,
                "notes": notes,
                "stage": "review_approved",
                "blocks": ["idea_generation"],
            }
            write_json(out_dir / web_server.APPROVAL_FILENAME, approval)
            return approval

        with (
            patch.object(web_server, "Thread", _DormantWorkerThread),
            patch.object(web_server, "_write_resume_preflight_or_raise", side_effect=self._preflight_side_effect(entered, release, preflight_models)),
            patch.object(web_server, "approve_review_gate", side_effect=approve),
        ):
            first_result, first_error = self._race_requests(
                lambda: store.approve_with_config(
                    "approval-race",
                    reviewer="winner",
                    payload={**self._payload("winner-model"), "review_notes": "winner notes"},
                ),
                lambda: store.approve("approval-race", reviewer="loser"),
                entered,
                release,
            )
            with self.assertRaisesRegex(RuntimeError, "already been granted"):
                store.approve("approval-race", reviewer="late-loser")

        self.assertIsNotNone(first_result)
        self.assertIsNone(first_error)
        self.assertEqual(preflight_models, ["winner-model"])
        self.assertEqual(approval_calls, ["winner"])
        self.assertEqual(len(_DormantWorkerThread.starts), 1)
        self.assertEqual(_DormantWorkerThread.starts[0].args[3].llm.model, "winner-model")
        approval = json.loads((run_dir / web_server.APPROVAL_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(approval["reviewer"], "winner")
        self.assertEqual(approval["notes"], "winner notes")

    def _write_run(self, run_id: str, stage: str, *, repair_queue: bool = False, review_approval: bool = False) -> Path:
        run_dir = self.runs_dir / run_id
        run_dir.mkdir()
        write_json(run_dir / "state.json", {"topic": "concurrency test", "stage": stage, "updated_at": "test"})
        web_server._write_run_config(run_dir, AgentConfig())
        if repair_queue:
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 1, "block": 1},
                    "items": [{"task_id": "RQ-001", "severity": "block", "rerun_from": "paper_rewrite", "status": "open"}],
                },
            )
        if review_approval:
            write_json(
                run_dir / web_server.APPROVAL_FILENAME,
                {
                    "topic": "concurrency test",
                    "approved": False,
                    "stage": "awaiting_review_approval",
                    "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                },
            )
        return run_dir

    def _blocking_preflight(self, winner_model: str) -> tuple[Event, Event, list[str]]:
        del winner_model
        return Event(), Event(), []

    def _preflight_side_effect(self, entered: Event, release: Event, models: list[str]) -> Callable[[str, AgentConfig, Path], None]:
        def run(_topic: str, config: AgentConfig, out_dir: Path) -> None:
            models.append(config.llm.model)
            write_json(out_dir / "preflight-config.json", {"model": config.llm.model})
            if config.llm.model == "winner-model":
                entered.set()
                if not release.wait(timeout=3):
                    raise RuntimeError("test preflight release timed out")

        return run

    def _race_requests(
        self,
        first: Callable[[], Any],
        second: Callable[[], Any],
        entered: Event,
        release: Event,
    ) -> tuple[Any, BaseException | None]:
        outcome: dict[str, Any] = {}

        def invoke_first() -> None:
            try:
                outcome["result"] = first()
            except BaseException as exc:  # pragma: no cover - asserted by the caller
                outcome["error"] = exc

        thread = Thread(target=invoke_first, daemon=True)
        thread.start()
        self.assertTrue(entered.wait(timeout=3), "first request did not reach preflight")
        try:
            with self.assertRaisesRegex(RuntimeError, "active operation"):
                second()
        finally:
            release.set()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "first request did not finish")
        return outcome.get("result"), outcome.get("error")

    @staticmethod
    def _payload(model: str) -> dict[str, str]:
        return {"llm_model": model, "llm_base_url": "http://127.0.0.1:9/v1"}


if __name__ == "__main__":
    unittest.main()
