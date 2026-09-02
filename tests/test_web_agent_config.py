from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from research_agent.config import AgentConfig, AgentRoleConfig, LLMConfig, MultiAgentConfig
import research_agent.web_server as web_server
from research_agent.web_server import _multi_agent_config_from_payload
from research_agent.workflow_state import append_node_event


class AgentCatalogEndpointTest(unittest.TestCase):
    """WEB-01: the frontend renders its agent config view from the catalog."""

    def setUp(self) -> None:
        self._originals = (web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline)
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        web_server.ROOT = root
        web_server.RUNS_DIR = root / "runs"
        web_server.STORE = web_server.RunStore()
        web_server.run_pipeline = lambda topic, out_dir, config: Path(out_dir)

    def tearDown(self) -> None:
        web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline = self._originals
        self._tmp.cleanup()

    def test_catalog_lists_agents_skills_and_model_precedence(self) -> None:
        for skill_id in ["evidence-grounding", "skeptical-review"]:
            skills_root = web_server.ROOT / "skills" / skill_id
            skills_root.mkdir(parents=True, exist_ok=True)
            (skills_root / "SKILL.md").write_text(f"# {skill_id}\n", encoding="utf-8")
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/agent-catalog", timeout=5) as response:
                catalog = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        agent_ids = {agent["agent_id"] for agent in catalog["agents"]}
        self.assertIn("skeptical_reviewer", agent_ids)
        self.assertIn("statistician", agent_ids)
        self.assertIn("model_precedence", catalog)
        skill_ids = {skill["skill_id"] for skill in catalog["skills"]}
        self.assertIn("evidence-grounding", skill_ids)
        self.assertIn("skeptical-review", skill_ids)


class ConditionalGetTest(unittest.TestCase):
    """WEB-03: pollers get 304 Not Modified instead of the full body."""

    def setUp(self) -> None:
        self._originals = (web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline)
        self._tmp = TemporaryDirectory()
        root = Path(self._tmp.name)
        web_server.ROOT = root
        web_server.RUNS_DIR = root / "runs"
        web_server.STORE = web_server.RunStore()
        web_server.run_pipeline = lambda topic, out_dir, config: Path(out_dir)

    def tearDown(self) -> None:
        web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline = self._originals
        self._tmp.cleanup()

    def test_run_detail_supports_if_none_match(self) -> None:
        record = web_server.STORE.create(
            "ETag 测试",
            AgentConfig(llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="placeholder")),
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import time as _time

            deadline = _time.monotonic() + 5
            while _time.monotonic() < deadline:
                if web_server.STORE.get(record["id"]).get("worker_active") is False:
                    break
                _time.sleep(0.05)
            detail_url = f"http://127.0.0.1:{server.server_port}/api/runs/{urllib.parse.quote(record['id'])}"
            with urllib.request.urlopen(detail_url, timeout=5) as first:
                etag = first.headers.get("ETag")
                self.assertTrue(etag)
            request = urllib.request.Request(detail_url, headers={"If-None-Match": etag})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 304)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class ActivityStreamTest(unittest.TestCase):
    """WEB-03: the activity stream exposes node events with ids and revisions."""

    def test_activity_stream_frames_node_events(self) -> None:
        originals = (web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline)
        root = Path(TemporaryDirectory().name)
        root.mkdir(parents=True, exist_ok=True)
        web_server.ROOT = root
        web_server.RUNS_DIR = root / "runs"
        web_server.STORE = web_server.RunStore()
        web_server.run_pipeline = lambda topic, out_dir, config: Path(out_dir)
        server = None
        thread = None
        try:
            run_dir = root / "runs" / "activity-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text(json.dumps({"topic": "活动流", "stage": "running"}), encoding="utf-8")
            append_node_event(run_dir, node_id="research_planning", event_type="started", revision=0)
            append_node_event(run_dir, node_id="research_planning", event_type="completed", revision=0)

            web_server.STORE._runs["activity-run"] = {
                "id": "activity-run",
                "topic": "活动流",
                "out_dir": "runs/activity-run",
                "status": "running",
                "stage": "started",
                "worker_active": False,
                "artifacts": [],
                "created_at": "",
                "updated_at": "",
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/api/runs/activity-run/activity?cursor=1"
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertTrue(response.headers.get("Content-Type", "").startswith("text/event-stream"))
                body = response.read().decode("utf-8")
            self.assertIn("id: 2", body)
            self.assertIn("event: node", body)
            self.assertIn('"type": "completed"', body)
            self.assertIn("event: done", body)
            self.assertNotIn("id: 1\n", body)
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=2)
            web_server.ROOT, web_server.RUNS_DIR, web_server.STORE, web_server.run_pipeline = originals


class MultiAgentPayloadMergeTest(unittest.TestCase):
    """WEB-01: flat agent maps plus nested MCP servers merge with the current config."""

    def test_flat_maps_and_nested_servers_merge(self) -> None:
        current = MultiAgentConfig(
            enabled=False,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    model="m0",
                    base_url="http://127.0.0.1:10/v1",
                    base_url_env="ROLE_BASE_URL",
                    api_key_env="ROLE_API_KEY",
                )
            ],
        )
        patched = _multi_agent_config_from_payload(
            {
                "multi_agent_enabled": True,
                "agent_models": {"gap_analyst": "m1"},
                "agent_skills": {"gap_analyst": ["evidence-grounding"]},
                "agent_mcp_servers": {"gap_analyst": ["local-docs"]},
                "agent_enabled": {"gap_analyst": True},
                "multi_agent": {
                    "mcp_servers": [
                        {
                            "server_id": "local-docs",
                            "url": "http://127.0.0.1:8000/mcp",
                            "allowed_tools": ["search_docs"],
                            "auth_env": "RESEARCH_AGENT_MCP_LOCAL_DOCS_TOKEN",
                        }
                    ]
                },
            },
            current,
        )
        self.assertTrue(patched.enabled)
        self.assertEqual(patched.mcp_servers[0].server_id, "local-docs")
        role = patched.roles[0]
        self.assertEqual(role.model, "m1")
        self.assertEqual(role.skills, ["evidence-grounding"])
        self.assertEqual(role.mcp_servers, ["local-docs"])
        self.assertEqual(role.base_url, "http://127.0.0.1:10/v1")
        self.assertEqual(role.api_key_env, "ROLE_API_KEY")


if __name__ == "__main__":
    unittest.main()
