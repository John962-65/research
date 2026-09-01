from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import contextlib
import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from research_agent.config import AgentConfig, LLMConfig
import research_agent.web_server as web_server


def _fake_pipeline_writing_ideas(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    from research_agent.workflow_graph import update_workflow_stage

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "02-ideas.json").write_text(json.dumps([{"title": "idea"}]), encoding="utf-8")
    (out_dir / "02-ideas.md").write_text("# Ideas\n", encoding="utf-8")
    update_workflow_stage(out_dir, topic, "ideation_completed")
    return out_dir


class WebRollbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self._originals = (web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline, web_server.resume_pipeline_from_checkpoint)
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        web_server.ROOT = root
        web_server.RUNS_DIR = root / "runs"
        web_server.STORE = web_server.RunStore()
        web_server.run_pipeline = _fake_pipeline_writing_ideas

    def tearDown(self) -> None:
        web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline, web_server.resume_pipeline_from_checkpoint = self._originals
        self._tmp.cleanup()

    def _create_run(self) -> dict:
        return web_server.STORE.create(
            "回退测试",
            AgentConfig(llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="placeholder")),
        )

    def _wait_for_node(self, run_id: str, node_id: str, timeout: float = 5.0) -> dict:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            detail = web_server.STORE.get(run_id) or {}
            if ((detail.get("workflow") or {}).get("current_node")) == node_id:
                return detail
            time.sleep(0.05)
        raise AssertionError(f"run did not reach workflow node {node_id}")

    def test_store_preview_rejects_active_worker(self) -> None:
        record = self._create_run()
        run_id = record["id"]
        self._wait_for_node(run_id, "ideation")
        web_server.STORE._update(run_id, worker_active=True, status="running")
        with self.assertRaises(RuntimeError):
            web_server.STORE.preview_rollback(run_id, "ideation")

    def test_store_rollback_archives_and_starts_resume_worker(self) -> None:
        record = self._create_run()
        run_id = record["id"]
        self._wait_for_node(run_id, "ideation")
        run_dir = web_server.ROOT / record["out_dir"]
        self.assertTrue((run_dir / "02-ideas.json").exists())

        resumed = threading.Event()
        captured = {}

        def fake_resume(topic: str, out_dir: Path, config: AgentConfig) -> Path:
            captured["topic"] = topic
            captured["out_dir"] = Path(out_dir)
            resumed.set()
            return Path(out_dir)

        web_server.resume_pipeline_from_checkpoint = fake_resume
        preview = web_server.STORE.preview_rollback(run_id, "ideation")
        self.assertIn("02-ideas.json", preview["preview"]["artifacts_to_archive"])
        result = web_server.STORE.rollback_with_config(
            run_id,
            {
                "target": "ideation",
                "preview_id": preview["preview"]["preview_id"],
                "preview_token": preview["preview"]["preview_token"],
                "reason": "web rollback smoke test",
            },
        )
        self.assertTrue(resumed.wait(timeout=5), "checkpoint resume worker did not start")
        self.assertEqual(captured["topic"], "回退测试")
        self.assertFalse((run_dir / "02-ideas.json").exists())
        self.assertEqual(result["rollback"]["status"], "applied")
        self.assertEqual(result["run"]["stage"], "rollback_applied")

    def test_http_rollback_flow_end_to_end(self) -> None:
        record = self._create_run()
        run_id = record["id"]
        self._wait_for_node(run_id, "ideation")
        web_server.resume_pipeline_from_checkpoint = lambda topic, out_dir, config: Path(out_dir)
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/api/runs/{urllib.parse.quote(run_id)}"
            with urllib.request.urlopen(f"{base}/rollback-options", timeout=5) as response:
                options = json.loads(response.read().decode("utf-8"))
            targets = [item["target"] for item in options["options"]]
            self.assertIn("ideation", targets)

            preview_request = urllib.request.Request(
                f"{base}/rollback-preview",
                data=json.dumps({"target": "ideation"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(preview_request, timeout=5) as response:
                preview = json.loads(response.read().decode("utf-8"))["preview"]

            def _post(path_payload: dict) -> tuple[int, dict]:
                request = urllib.request.Request(
                    f"{base}/rollback-apply",
                    data=json.dumps(path_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return response.status, json.loads(response.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    return exc.code, json.loads(exc.read().decode("utf-8"))

            status, short_reason = _post({
                "target": "ideation",
                "preview_id": preview["preview_id"],
                "preview_token": preview["preview_token"],
                "reason": "短",
            })
            self.assertEqual(status, 409)
            self.assertIn("reason", short_reason.get("error", ""))

            status, applied_body = _post({
                "target": "ideation",
                "preview_id": preview["preview_id"],
                "preview_token": preview["preview_token"],
                "reason": "rollback via http",
            })
            self.assertEqual(status, 200)
            self.assertEqual(applied_body["rollback"]["status"], "applied")
        finally:
            server.shutdown()
            server.server_close()
            with contextlib.suppress(RuntimeError):
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
