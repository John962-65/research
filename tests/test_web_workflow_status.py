from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import time
import unittest

from research_agent.config import AgentConfig, LLMConfig
import research_agent.web_server as web_server
from research_agent.workflow_graph import begin_workflow_node, read_workflow_status


class BeginWorkflowNodeTest(unittest.TestCase):
    def test_marks_node_running_and_updates_state(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            begin_workflow_node(out_dir, "测试主题", "literature_review")
            status = read_workflow_status(out_dir)
            state = json.loads((out_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(status["current_node"], "literature_review")
            self.assertEqual(status["activity_status"], "running")
            self.assertEqual(state["current_stage"], "literature_review")
            self.assertEqual(state["stage_status"], "running")
            node = next(item for item in status["nodes"] if item["node_id"] == "literature_review")
            self.assertEqual(node["status"], "running")
            self.assertTrue(any(event["detail"].startswith("阶段开始") for event in status["events"]))

    def test_unknown_node_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                begin_workflow_node(Path(tmp), "测试主题", "not_a_node")


class RunDetailWorkflowFieldTest(unittest.TestCase):
    def test_store_refresh_attaches_workflow_status(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_run_pipeline = web_server.run_pipeline
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            try:
                def fake_run_pipeline(topic, out_dir, config):
                    from research_agent.workflow_graph import update_workflow_stage

                    update_workflow_stage(Path(out_dir), topic, "awaiting_review_approval")

                web_server.run_pipeline = fake_run_pipeline
                store = web_server.RunStore()
                record = store.create(
                    "工作流状态测试",
                    AgentConfig(llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="placeholder")),
                )
                detail = _wait_for_node(store, record["id"], "review_gate")
                workflow = detail.get("workflow") or {}
                self.assertEqual(workflow.get("current_node"), "review_gate")
                self.assertEqual(workflow.get("activity_status"), "waiting")
                nodes = {node["node_id"]: node["status"] for node in workflow.get("nodes", [])}
                self.assertEqual(nodes.get("research_planning"), "completed")
                self.assertEqual(nodes.get("literature_review"), "completed")
                self.assertEqual(nodes.get("literature_context"), "completed")
                self.assertEqual(nodes.get("review_gate"), "waiting")
                self.assertTrue(any(event.get("kind") == "stage" for event in workflow.get("events", [])))
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.run_pipeline = original_run_pipeline


def _wait_for_node(store: web_server.RunStore, run_id: str, node_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        detail = store.get(run_id)
        workflow = (detail or {}).get("workflow") or {}
        if workflow.get("current_node") == node_id:
            return detail
        time.sleep(0.05)
    raise AssertionError(f"run did not reach workflow node {node_id}")


if __name__ == "__main__":
    unittest.main()
