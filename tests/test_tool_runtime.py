from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from research_agent.config import AgentRoleConfig, MCPServerConfig, MultiAgentConfig
from research_agent.tool_runtime import (
    MAX_SKILL_FILE_BYTES,
    ToolRuntime,
    list_project_skills,
    load_skill_context,
    validate_mcp_server,
    validate_multi_agent_tools,
)


def _mcp_server(**overrides: object) -> MCPServerConfig:
    values: dict[str, object] = {
        "server_id": "local-docs",
        "transport": "streamable-http",
        "url": "http://127.0.0.1:8000/mcp",
        "allowed_tools": ["search_docs"],
        "enabled": True,
    }
    values.update(overrides)
    return MCPServerConfig(**values)


def _runtime(project_root: Path, **config_overrides: object) -> ToolRuntime:
    values: dict[str, object] = {
        "enabled": True,
        "mcp_servers": [_mcp_server()],
        "roles": [AgentRoleConfig(agent_id="gap_analyst", mcp_servers=["local-docs"])],
    }
    values.update(config_overrides)
    return ToolRuntime(project_root, project_root / "run", MultiAgentConfig(**values))


class SkillLoadingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        (self.project_root / "run").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_skill(self, skill_id: str, content: str = "# Skill\n\n- Rule.\n") -> None:
        directory = self.project_root / "skills" / skill_id
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(content, encoding="utf-8")

    def test_list_and_load_project_skills(self) -> None:
        self._write_skill("evidence-grounding", "# Evidence Grounding\n\n- Rule one.\n")
        self._write_skill("not-a-skill-id!", "# Invalid\n")
        skills = list_project_skills(self.project_root)
        self.assertEqual([item["skill_id"] for item in skills], ["evidence-grounding"])
        self.assertEqual(skills[0]["title"], "Evidence Grounding")
        context, records = load_skill_context(self.project_root, ["evidence-grounding"])
        self.assertIn("## Skill: evidence-grounding", context)
        self.assertEqual(records[0]["skill_id"], "evidence-grounding")

    def test_unknown_skill_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_skill_context(self.project_root, ["missing-skill"])

    def test_oversized_skill_rejected(self) -> None:
        self._write_skill("big-skill", "# Big\n" + "x" * (MAX_SKILL_FILE_BYTES + 1))
        with self.assertRaises(ValueError):
            load_skill_context(self.project_root, ["big-skill"])

    def test_symlinked_skill_rejected(self) -> None:
        outside = self.project_root / "outside.md"
        outside.write_text("# Outside\n", encoding="utf-8")
        directory = self.project_root / "skills" / "evil-skill"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").symlink_to(outside)
        with self.assertRaises(ValueError):
            load_skill_context(self.project_root, ["evil-skill"])


class ValidateMcpServerTest(unittest.TestCase):
    def test_valid_local_server_passes(self) -> None:
        validate_mcp_server(_mcp_server())

    def test_non_streamable_http_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_mcp_server(_mcp_server(transport="stdio"))

    def test_missing_url_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_mcp_server(_mcp_server(url=""))

    def test_remote_host_rejected_unless_enabled(self) -> None:
        with self.assertRaises(ValueError):
            validate_mcp_server(_mcp_server(url="http://example.com/mcp"))
        validate_mcp_server(_mcp_server(url="http://example.com/mcp", allow_remote=True))

    def test_writable_server_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_mcp_server(_mcp_server(read_only=False))

    def test_empty_allowlist_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_mcp_server(_mcp_server(allowed_tools=[]))

    def test_auth_env_namespace_enforced(self) -> None:
        with self.assertRaises(ValueError):
            validate_mcp_server(_mcp_server(auth_env="OPENAI_API_KEY"))
        validate_mcp_server(_mcp_server(auth_env="RESEARCH_AGENT_MCP_LOCAL_DOCS_TOKEN"))


class ValidateMultiAgentToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unknown_mcp_reference_reported(self) -> None:
        issues = validate_multi_agent_tools(
            MultiAgentConfig(roles=[AgentRoleConfig(agent_id="gap_analyst", mcp_servers=["ghost"])]),
            self.project_root,
        )
        self.assertTrue(any("ghost" in issue for issue in issues))

    def test_duplicate_role_and_server_ids_reported(self) -> None:
        issues = validate_multi_agent_tools(
            MultiAgentConfig(
                roles=[
                    AgentRoleConfig(agent_id="gap_analyst"),
                    AgentRoleConfig(agent_id="gap_analyst"),
                ],
                mcp_servers=[_mcp_server(), _mcp_server(server_id="local-docs")],
            ),
            self.project_root,
        )
        joined = "; ".join(issues)
        self.assertIn("duplicate agent_id", joined)
        self.assertIn("duplicate MCP server_id", joined)


class ToolRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        (self.project_root / "run").mkdir()
        skill_dir = self.project_root / "skills" / "evidence-grounding"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Evidence Grounding\n\n- Only supported claims.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_invalid_config_rejected_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            _runtime(self.project_root, mcp_servers=[_mcp_server(transport="stdio")])

    def test_disabled_server_not_callable(self) -> None:
        runtime = _runtime(self.project_root, mcp_servers=[_mcp_server(enabled=False)])
        with self.assertRaises(RuntimeError):
            runtime.call(
                {"server_id": "local-docs", "name": "search_docs", "arguments": {}},
                stage="research_planning",
                agent_id="gap_analyst",
            )

    def test_role_context_includes_skill_and_tool_protocol(self) -> None:
        runtime = _runtime(self.project_root)
        role = AgentRoleConfig(agent_id="gap_analyst", skills=["evidence-grounding"], mcp_servers=["local-docs"])
        context, records = runtime.role_context(role)
        self.assertIn("## Skill: evidence-grounding", context)
        self.assertIn("## MCP tools", context)
        self.assertIn("search_docs", context)
        self.assertEqual(records[0]["skill_id"], "evidence-grounding")

    def test_tool_receipts_recorded_on_failure(self) -> None:
        runtime = _runtime(self.project_root)
        with self.assertRaises(RuntimeError):
            runtime.call(
                {"server_id": "local-docs", "name": "not_allowlisted", "arguments": {}},
                stage="research_planning",
                agent_id="gap_analyst",
            )


class ParseCallTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        (self.project_root / "run").mkdir()
        self.runtime = ToolRuntime(self.project_root, self.project_root / "run", MultiAgentConfig(enabled=True))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_valid_call_parsed(self) -> None:
        request = self.runtime.parse_call(
            '{"__mcp_call__":{"server_id":"local-docs","name":"search_docs","arguments":{"q":"iris"}}}'
        )
        assert request is not None
        self.assertEqual(request["server_id"], "local-docs")
        self.assertEqual(request["name"], "search_docs")
        self.assertEqual(request["arguments"], {"q": "iris"})

    def test_plain_response_returns_none(self) -> None:
        self.assertIsNone(self.runtime.parse_call("The final answer is 42."))
        self.assertIsNone(self.runtime.parse_call('{"other": 1}'))
        self.assertIsNone(self.runtime.parse_call(""))

    def test_non_object_arguments_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            self.runtime.parse_call('{"__mcp_call__":{"server_id":"s","name":"n","arguments":[1]}}')

    def test_fenced_json_accepted(self) -> None:
        request = self.runtime.parse_call(
            '```\n{"__mcp_call__":{"server_id":"s","name":"n","arguments":{}}}\n```'
        )
        assert request is not None
        self.assertEqual(request["arguments"], {})


if __name__ == "__main__":
    unittest.main()
