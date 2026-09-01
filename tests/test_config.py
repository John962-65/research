from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.config import (
    AgentRoleConfig,
    ExecutionConfig,
    LLMConfig,
    MCPServerConfig,
    config_from_dict,
    load_config,
)
from research_agent.experiments import _simulated_metrics


CONFIG_TOML = """
[llm]
provider = "openai-compatible"
base_url = "http://127.0.0.1:9/v1"
model = "default-model"
temperature = 0.2
max_tokens = 512

[execution]
mode = "simulated"

[execution.simulated_offsets]
candidate = 0.05
baseline = -0.02

[multi_agent]
enabled = true
task_models = { research_planning = "planner-model", " " = "ignored", paper_review_loop = "" }
max_tool_rounds = 3

[[multi_agent.roles]]
agent_id = "gap_analyst"
model = "role-model"
base_url = "http://127.0.0.1:10/v1"
api_key_env = "ROLE_API_KEY"
skills = ["evidence-grounding"]

[[multi_agent.mcp_servers]]
server_id = "local-docs"
url = "http://127.0.0.1:8000/mcp"
allowed_tools = ["search_docs"]
auth_env = "RESEARCH_AGENT_MCP_LOCAL_DOCS_TOKEN"
"""


class LoadConfigTest(unittest.TestCase):
    def test_multi_agent_section_parsed(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(CONFIG_TOML, encoding="utf-8")
            config = load_config(path)
        self.assertTrue(config.multi_agent.enabled)
        self.assertEqual(config.multi_agent.task_models, {"research_planning": "planner-model"})
        self.assertEqual(config.multi_agent.max_tool_rounds, 3)
        role = config.multi_agent.roles[0]
        self.assertEqual(role, AgentRoleConfig(
            agent_id="gap_analyst",
            model="role-model",
            skills=["evidence-grounding"],
            base_url="http://127.0.0.1:10/v1",
            api_key_env="ROLE_API_KEY",
        ))
        server = config.multi_agent.mcp_servers[0]
        self.assertEqual(server, MCPServerConfig(
            server_id="local-docs",
            url="http://127.0.0.1:8000/mcp",
            allowed_tools=["search_docs"],
            auth_env="RESEARCH_AGENT_MCP_LOCAL_DOCS_TOKEN",
        ))

    def test_llm_sampling_parameters_parsed(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(CONFIG_TOML, encoding="utf-8")
            config = load_config(path)
        self.assertEqual(config.llm.temperature, 0.2)
        self.assertEqual(config.llm.max_tokens, 512)

    def test_simulated_offsets_parsed(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(CONFIG_TOML, encoding="utf-8")
            config = load_config(path)
        self.assertEqual(config.execution.simulated_offsets, {"candidate": 0.05, "baseline": -0.02})
        self.assertEqual(ExecutionConfig().simulated_offsets, {})

    def test_simulated_metrics_neutral_without_offsets(self) -> None:
        names = ["success_rate", "planning_time"]
        neutral_candidate = _simulated_metrics(names, 0.5, "candidate", "generic")
        neutral_baseline = _simulated_metrics(names, 0.5, "baseline", "generic")
        self.assertEqual(neutral_candidate, neutral_baseline)

    def test_simulated_metrics_apply_offset_in_favorable_direction(self) -> None:
        names = ["success_rate", "planning_time"]
        offsets = {"candidate": 0.05}
        with_offset = _simulated_metrics(names, 0.5, "candidate", "generic", offsets)
        neutral = _simulated_metrics(names, 0.5, "candidate", "generic")
        self.assertAlmostEqual(with_offset["success_rate"], neutral["success_rate"] + 0.05, places=6)
        # planning_time is lower-is-better: the advantage lowers the value.
        self.assertAlmostEqual(with_offset["planning_time"], neutral["planning_time"] - 0.05, places=6)

    def test_defaults_when_sections_missing(self) -> None:
        config = config_from_dict({})
        self.assertEqual(config.llm, LLMConfig())
        self.assertFalse(config.multi_agent.enabled)
        self.assertEqual(config.multi_agent.roles, [])

    def test_snapshot_roundtrip_preserves_multi_agent(self) -> None:
        config = config_from_dict({
            "llm": {"model": "m", "temperature": 0.1},
            "multi_agent": {
                "enabled": True,
                "task_models": {"idea_generation": "idea-model"},
                "roles": [{"agent_id": "gap_analyst", "model": "role-m"}],
            },
        })
        from dataclasses import asdict
        import json

        payload = json.loads(json.dumps(asdict(config)))
        restored = config_from_dict(payload)
        self.assertEqual(restored, config)


if __name__ == "__main__":
    unittest.main()
