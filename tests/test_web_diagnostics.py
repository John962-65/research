from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import time
import unittest

from research_agent.config import AgentConfig, LLMConfig
import research_agent.web_server as web_server


class WebDiagnosticsTest(unittest.TestCase):
    def test_create_blocks_failed_preflight_without_starting_worker(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_run_pipeline = web_server.run_pipeline
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            called = False
            try:
                def fake_run_pipeline(topic, out_dir, config):
                    nonlocal called
                    called = True

                web_server.run_pipeline = fake_run_pipeline
                store = web_server.RunStore()

                with self.assertRaises(web_server.PreflightGateError) as caught:
                    store.create("诊断测试", AgentConfig())

                self.assertFalse(called)
                self.assertEqual(caught.exception.report.status, "fail")
                self.assertEqual(store.list(), [])
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.run_pipeline = original_run_pipeline

    def test_failed_worker_writes_public_diagnostic_and_artifacts(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_run_pipeline = web_server.run_pipeline
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            try:
                def fake_run_pipeline(topic, out_dir, config):
                    raise RuntimeError("Missing model. Set llm.model or env var: OPENAI_MODEL")

                web_server.run_pipeline = fake_run_pipeline
                store = web_server.RunStore()
                record = store.create(
                    "诊断测试",
                    AgentConfig(llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="placeholder")),
                )
                failed = _wait_for_failed(store, record["id"])
                run_dir = root / failed["out_dir"]

                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["diagnostic"]["category"], "llm_configuration")
                self.assertIn("模型名", failed["error"])
                self.assertTrue((run_dir / "00-preflight.md").exists())
                self.assertTrue((run_dir / "00-preflight.json").exists())
                self.assertTrue((run_dir / "run-diagnostics.md").exists())
                self.assertTrue((run_dir / "run-diagnostics.json").exists())
                self.assertTrue((run_dir / "run-recovery-plan.md").exists())
                self.assertTrue((run_dir / "run-recovery-plan.json").exists())
                data = json.loads((run_dir / "run-diagnostics.json").read_text(encoding="utf-8"))
                self.assertEqual(data["category"], "llm_configuration")
                self.assertIn("Traceback", (run_dir / "run-diagnostics.md").read_text(encoding="utf-8"))
                recovery = json.loads((run_dir / "run-recovery-plan.json").read_text(encoding="utf-8"))
                self.assertEqual(recovery["category"], "failed")
                self.assertTrue(any("resume" in item for item in recovery["commands"]))
                preflight = json.loads((run_dir / "00-preflight.json").read_text(encoding="utf-8"))
                self.assertIn(preflight["status"], {"pass", "warn", "fail"})
                self.assertIn("00-preflight.md", failed["artifacts"])
                self.assertIn("run-diagnostics.md", failed["artifacts"])
                self.assertIn("run-recovery-plan.md", failed["artifacts"])
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.run_pipeline = original_run_pipeline

    def test_create_reserves_fresh_output_directory_when_default_exists(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_run_pipeline = web_server.run_pipeline
        original_default_out_dir = web_server.default_out_dir
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "runs" / "collision-run"
            existing.mkdir(parents=True)
            (existing / "old-artifact.txt").write_text("do not overwrite", encoding="utf-8")
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"

            def fake_run_pipeline(topic, out_dir, config):
                return out_dir

            try:
                web_server.run_pipeline = fake_run_pipeline
                web_server.default_out_dir = lambda topic: Path("runs/collision-run")
                store = web_server.RunStore()
                record = store.create(
                    "collision run",
                    AgentConfig(llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="placeholder")),
                )
                _wait_for_terminal(store, record["id"])

                self.assertEqual(record["out_dir"], "runs/collision-run-2")
                self.assertTrue((root / "runs" / "collision-run-2" / "run-config.json").exists())
                self.assertEqual((existing / "old-artifact.txt").read_text(encoding="utf-8"), "do not overwrite")
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.run_pipeline = original_run_pipeline
                web_server.default_out_dir = original_default_out_dir


def _wait_for_failed(store: web_server.RunStore, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = store.get(run_id) or {}
        if last.get("status") == "failed" and last.get("worker_active") is False:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for failed run; last={last}")


def _wait_for_terminal(store: web_server.RunStore, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = store.get(run_id) or {}
        if last.get("status") in {"completed", "failed", "cancelled"} and last.get("worker_active") is False:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for terminal run; last={last}")


if __name__ == "__main__":
    unittest.main()
