from __future__ import annotations

import contextlib
import json
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from research_agent import web_server
from research_agent.existing_results import import_existing_results


RESULTS = [
    {
        "name": "candidate",
        "status": "passed",
        "metrics": {"accuracy": 0.9},
        "command": ["python3", "run.py"],
        "returncode": 0,
        "seed": "s",
        "repeat_index": 0,
    }
]


def _create_run(store, runs_dir: Path, topic: str) -> str:
    """绕过 preflight，直接登记一个测试 run（与 test_web_resume 的做法一致）。"""
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = topic
    out_dir = runs_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "state.json").write_text(json.dumps({"topic": topic, "stage": "awaiting_review_approval", "status": "waiting"}), encoding="utf-8")
    (out_dir / "00-question.md").write_text(f"# {topic}\n", encoding="utf-8")
    store._runs[run_id] = {
        "id": run_id,
        "topic": topic,
        "stage": "awaiting_review_approval",
        "status": "waiting",
        "worker_active": False,
        "out_dir": str(out_dir.relative_to(runs_dir.parent)),
        "error": None,
    }
    return run_id


class DecisionStateEndpointTest(unittest.TestCase):
    def test_decision_state_endpoint_returns_structured_payload(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            server = None
            thread = None
            try:
                store = web_server.RunStore()
                web_server.STORE = store
                run_id = _create_run(store, root / "runs", "决策状态测试")
                out_dir = root / "runs" / run_id
                (out_dir / "04-experiment-decision.json").write_text(json.dumps({
                    "decision": "pivot_or_refine",
                    "decision_states": {
                        "execution_status": "completed",
                        "evidence_status": "verified",
                        "research_outcome": "not_supported",
                        "next_action": "proceed",
                        "stop_after_report": True,
                    },
                    "next_actions": ["把负向指标作为结果报告。"],
                }), encoding="utf-8")
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{server.server_port}/api/runs/{urllib.parse.quote(run_id)}/decision-state", timeout=5
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                with contextlib.suppress(RuntimeError):
                    if thread is not None:
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store
        states = payload["states"]
        self.assertEqual(states["execution_status"], "completed")
        self.assertEqual(states["evidence_status"], "verified")
        self.assertEqual(states["research_outcome"], "not_supported")
        self.assertEqual(states["next_action"], "proceed")
        self.assertTrue(states["stop_after_report"])
        self.assertIn("本机操作者", payload["reviewer_identity_note"])
        self.assertIn("budget", payload)

    def test_import_results_endpoint_writes_report(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            server = None
            thread = None
            try:
                store = web_server.RunStore()
                web_server.STORE = store
                run_id = _create_run(store, root / "runs", "导入测试")
                out_dir = root / "runs" / run_id
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/runs/{urllib.parse.quote(run_id)}/import-results",
                    data=json.dumps({"results_json": json.dumps(RESULTS), "notes": "web import"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                report = payload["import_report"]
                self.assertTrue((out_dir / "04-results.json").exists())
                self.assertTrue((out_dir / "00-import-report.json").exists())
                self.assertEqual(report["result_summary"]["total"], 1)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                with contextlib.suppress(RuntimeError):
                    if thread is not None:
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store


class StaleApprovalRejectionTest(unittest.TestCase):
    def test_stale_binding_approval_is_rejected_with_material_change_message(self) -> None:
        # A19：页面提交旧版本批准 → 后端拒绝并提示材料变化。
        from research_agent.pipeline import _review_approval_binding, _digest_payload, APPROVAL_FILENAME
        from research_agent.artifacts import write_json

        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "run"
            out_dir.mkdir(parents=True)
            binding = _review_approval_binding(out_dir, "材料变化测试")
            approval = {
                "topic": "材料变化测试",
                "stage": "awaiting_review_approval",
                "approved": False,
                "approved_at": None,
                "reviewer": "",
                "notes": "",
                "approval_binding": binding,
                "approval_binding_sha256": _digest_payload(binding),
                "gate_status": "pass",
                "warnings": [],
                "blocks": [],
                "history": [],
            }
            write_json(out_dir / APPROVAL_FILENAME, approval)
            # 审批请求生成后 run-config 变化 → 绑定失效。
            (out_dir / "run-config.json").write_text(json.dumps({"topic": "材料变化测试", "changed": True}), encoding="utf-8")
            from research_agent import pipeline as pipeline_module
            from research_agent.artifacts import read_json

            # 后端：旧绑定批准直接拒绝（RuntimeError），审批请求被刷新并落盘。
            with self.assertRaises(RuntimeError) as pipeline_error:
                pipeline_module.approve_review_gate(out_dir, reviewer="tester", notes="核对后批准")
            self.assertIn("changed after approval", str(pipeline_error.exception))
            persisted = read_json(out_dir / APPROVAL_FILENAME)
            self.assertFalse(persisted.get("approved"))
            self.assertTrue(persisted.get("stale_previous_approval"))
            # web 层守卫：刷新后的 stale 审批不能被静默放行。
            with self.assertRaises(RuntimeError) as ctx:
                web_server.ensure_approval_not_stale(persisted)
            self.assertIn("材料", str(ctx.exception))

    def test_fresh_approval_passes_stale_guard(self) -> None:
        web_server.ensure_approval_not_stale({"approved": True})
        web_server.ensure_approval_not_stale({"approved": False, "stale_previous_approval": False})


if __name__ == "__main__":
    unittest.main()
