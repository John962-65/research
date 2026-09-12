from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import hashlib
import json
import unittest
from unittest import mock

from research_agent.llm_trace import _read_entries, complete_with_purpose_detail, trace_llm
from research_agent.agent_runtime import (
    DEFAULT_ROLE_SKILLS,
    AgentRoutedLLM,
    RoleModelRouter,
    agent_for_stage,
)
from research_agent.config import AgentConfig, AgentRoleConfig, LLMConfig, MCPServerConfig, MultiAgentConfig

LOCAL_BASE_URL = "http://127.0.0.1:9/v1"
ALT_BASE_URL = "http://127.0.0.1:10/v1"


def _config(**multi_agent_kwargs: object) -> AgentConfig:
    return AgentConfig(
        llm=LLMConfig(base_url=LOCAL_BASE_URL, model="default-model"),
        multi_agent=MultiAgentConfig(**multi_agent_kwargs),
    )


def _skills_root(project_root: Path, skill_ids: list[str]) -> None:
    skills = project_root / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    for skill_id in skill_ids:
        directory = skills / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"# {skill_id}\n\n- Follow the {skill_id} contract.\n", encoding="utf-8"
        )


class _FakeLLM:
    model = "fake-model"
    base_url = LOCAL_BASE_URL

    def complete(self, system: str, user: str) -> str:
        return "输出"


class RoleModelRouterTest(unittest.TestCase):
    def test_model_precedence_task_over_role_over_default(self) -> None:
        config = _config(
            enabled=True,
            roles=[AgentRoleConfig(agent_id="manuscript_editor", model="role-model")],
            task_models={"research_planning": "task-model"},
        )
        router = RoleModelRouter(config)
        self.assertEqual(router.resolve(stage="research_planning").model, "task-model")
        self.assertEqual(router.resolve(stage="paper_writing").model, "role-model")
        self.assertEqual(router.resolve(stage="literature_synthesis").model, "default-model")

    def test_unknown_role_and_task_raise(self) -> None:
        with self.assertRaises(ValueError):
            RoleModelRouter(_config(roles=[AgentRoleConfig(agent_id="not_a_role")]))
        with self.assertRaises(ValueError):
            RoleModelRouter(_config(task_models={"not_a_stage": "model-a"}))

    def test_resolve_rejects_unknown_agent(self) -> None:
        router = RoleModelRouter(_config())
        with self.assertRaises(ValueError):
            router.resolve(stage="research_planning", agent_id="not_a_role")

    def test_agent_for_stage_matches_task_table(self) -> None:
        self.assertEqual(agent_for_stage("research_planning"), "gap_analyst")
        self.assertEqual(agent_for_stage("Paper Review Loop"), "skeptical_reviewer")
        self.assertEqual(agent_for_stage("unknown_stage"), "gap_analyst")

    def test_default_skills_applied_when_role_has_none(self) -> None:
        config = _config(enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")])
        router = RoleModelRouter(config)
        decision = router.resolve(stage="paper_review_loop")
        self.assertEqual(decision.skills, DEFAULT_ROLE_SKILLS["skeptical_reviewer"])

    def test_default_skills_applied_to_implicit_roles(self) -> None:
        router = RoleModelRouter(_config(enabled=True))
        for agent_id, skills in DEFAULT_ROLE_SKILLS.items():
            with self.subTest(agent_id=agent_id):
                decision = router.resolve(stage="paper_deliberation", agent_id=agent_id)
                self.assertEqual(decision.skills, skills)

    def test_disabled_role_does_not_load_default_skills(self) -> None:
        router = RoleModelRouter(_config(
            enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer", enabled=False)]
        ))
        self.assertEqual(router.resolve(stage="paper_review_loop").skills, [])

    def test_explicit_skills_override_defaults(self) -> None:
        config = _config(
            enabled=True,
            roles=[AgentRoleConfig(agent_id="skeptical_reviewer", skills=["evidence-grounding"])],
        )
        router = RoleModelRouter(config)
        self.assertEqual(router.resolve(stage="paper_review_loop").skills, ["evidence-grounding"])

    def test_skills_empty_when_multi_agent_disabled(self) -> None:
        config = _config(enabled=False, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")])
        router = RoleModelRouter(config)
        decision = router.resolve(stage="paper_review_loop")
        self.assertFalse(decision.multi_agent_enabled)
        self.assertEqual(decision.skills, [])

    def test_role_endpoint_fields_carried_on_decision(self) -> None:
        config = _config(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    base_url=ALT_BASE_URL,
                    base_url_env="ROLE_BASE_URL",
                    api_key_env="ROLE_API_KEY",
                )
            ],
        )
        router = RoleModelRouter(config)
        decision = router.resolve(stage="research_planning")
        self.assertEqual(decision.base_url, ALT_BASE_URL)
        self.assertEqual(decision.base_url_env, "ROLE_BASE_URL")
        self.assertEqual(decision.api_key_env, "ROLE_API_KEY")

    def test_endpoint_resolution_falls_back_to_global_config(self) -> None:
        router = RoleModelRouter(_config(enabled=True, roles=[AgentRoleConfig(agent_id="gap_analyst")]))
        decision = router.resolve(stage="research_planning")
        self.assertEqual(decision.base_url, LOCAL_BASE_URL)


class AgentRoutedLLMTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.run_dir = self.project_root / "run"
        self.run_dir.mkdir()
        _skills_root(self.project_root, ["evidence-grounding", "skeptical-review"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_role_prompt_injected_when_enabled(self) -> None:
        config = _config(enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")])
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        prepared = routed.prepare_request(
            "Original system prompt.", "user task", stage="paper_review_loop", purpose="review"
        )
        self.assertIn("You are Skeptical Reviewer (skeptical_reviewer)", prepared.system)
        self.assertIn("Assigned task T07", prepared.system)
        self.assertIn("Original system prompt.", prepared.system)
        self.assertEqual(prepared.user, "user task")

    def test_role_prompt_not_injected_when_disabled(self) -> None:
        config = _config(enabled=False, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")])
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        prepared = routed.prepare_request(
            "Original system prompt.", "user task", stage="paper_review_loop", purpose="review"
        )
        self.assertEqual(prepared.system, "Original system prompt.")

    def test_default_skill_context_loaded(self) -> None:
        config = _config(enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")])
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        prepared = routed.prepare_request(
            "Original system prompt.", "user task", stage="paper_review_loop", purpose="review"
        )
        self.assertIn("## Skill: skeptical-review", prepared.system)

    def test_implicit_role_loads_and_records_default_skill(self) -> None:
        config = _config(enabled=True)
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        prepared = routed.prepare_request("System", "Task", stage="paper_review_loop", purpose="review")
        self.assertIn("## Skill: skeptical-review", prepared.system)
        self.assertEqual(prepared.skill_records[0]["skill_id"], "skeptical-review")
        with mock.patch.object(routed, "_client_for", return_value=_FakeLLM()):
            traced = trace_llm(routed, self.run_dir, config.llm)
            complete_with_purpose_detail(traced, "System", "Task", stage="paper_review_loop", purpose="review")
        entry = _read_entries(self.run_dir / "run-llm-ledger.json")[0]
        self.assertEqual(entry.skills, ["skeptical-review"])
        self.assertTrue(entry.skill_hashes[0].startswith("skeptical-review:"))

    def test_clients_cached_per_endpoint_and_model(self) -> None:
        config = _config(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    base_url=ALT_BASE_URL,
                    base_url_env="ROLE_A_BASE_URL",
                    api_key_env="ROLE_A_API_KEY",
                ),
                AgentRoleConfig(agent_id="skeptical_reviewer"),
            ],
            task_models={"research_planning": "planner-model", "paper_review_loop": "reviewer-model"},
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        env = {"ROLE_A_BASE_URL": ALT_BASE_URL, "ROLE_A_API_KEY": "role-key"}
        with mock.patch.dict(os.environ, env):
            planner = routed._client_for(routed.router.resolve(stage="research_planning"))
            reviewer = routed._client_for(routed.router.resolve(stage="paper_review_loop"))
            again = routed._client_for(routed.router.resolve(stage="research_planning"))
        self.assertIs(planner, again)
        self.assertIsNot(planner, reviewer)
        self.assertEqual(planner.base_url, ALT_BASE_URL)
        self.assertEqual(planner.model, "planner-model")
        self.assertEqual(reviewer.base_url, LOCAL_BASE_URL)
        self.assertEqual(reviewer.model, "reviewer-model")

    def test_role_api_key_env_passed_to_client_config(self) -> None:
        config = _config(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    base_url=ALT_BASE_URL,
                    base_url_env="ROLE_BASE_URL",
                    api_key_env="ROLE_API_KEY",
                )
            ],
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        env = {"ROLE_BASE_URL": ALT_BASE_URL}
        with mock.patch.dict(os.environ, env, clear=False):
            client = routed._client_for(routed.router.resolve(stage="research_planning"))
        self.assertEqual(client.base_url, ALT_BASE_URL)
        # The credential itself stays empty: ROLE_API_KEY is not set in this
        # test environment, and resolve_llm_api_key refuses to invent one.
        self.assertEqual(client.api_key, "")

    def test_cross_origin_role_without_env_pair_rejected_at_client_build(self) -> None:
        config = _config(
            enabled=True,
            roles=[AgentRoleConfig(agent_id="gap_analyst", base_url=ALT_BASE_URL)],
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        with self.assertRaises(ValueError) as caught:
            routed._client_for(routed.router.resolve(stage="research_planning"))
        self.assertIn("credential binding rejected", str(caught.exception))

    def test_sampling_parameters_reach_client(self) -> None:
        config = replace(
            _config(),
            llm=LLMConfig(base_url=LOCAL_BASE_URL, model="m", temperature=0.3, max_tokens=512),
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        client = routed._client_for(routed.router.resolve(stage="research_planning"))
        self.assertEqual(client.temperature, 0.3)
        self.assertEqual(client.max_tokens, 512)


class MCPBudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_dir = self.root / "run"
        _skills_root(self.root, ["evidence-grounding"])
        self.config = _config(
            enabled=True,
            roles=[AgentRoleConfig(agent_id="gap_analyst", mcp_servers=["local-docs"])],
            mcp_servers=[MCPServerConfig(
                server_id="local-docs", url="http://127.0.0.1:9/mcp",
                enabled=True, allowed_tools=["search_docs"],
            )],
        )
        self.tool_response = json.dumps({"__mcp_call__": {
            "server_id": "local-docs", "name": "search_docs", "arguments": {"q": "iris"},
        }})

    def runtime(self, responses, **budget):
        config = replace(self.config, llm=replace(self.config.llm, **budget))
        routed = AgentRoutedLLM(config, self.root, self.run_dir)
        client = mock.Mock()
        prompts = []
        responses = iter(responses)

        def complete(system, user):
            prompts.append((system, user))
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            client.last_usage = {"input_tokens": 100 * len(prompts), "output_tokens": 10 * len(prompts)}
            return response

        client.complete.side_effect = complete
        self.enterContext(mock.patch.object(routed, "_client_for", return_value=client))
        return trace_llm(routed, self.run_dir, config.llm), routed, prompts

    def invoke(self, traced):
        return complete_with_purpose_detail(
            traced, "Private system", "Private task", stage="research_planning",
            purpose="plan", requires_validation=True,
        )

    def entries(self):
        return _read_entries(self.run_dir / "run-llm-ledger.json")

    def test_tool_continuation_obeys_call_budget(self) -> None:
        traced, routed, prompts = self.runtime([self.tool_response, "Finished"], max_calls=1)
        with mock.patch.object(routed.tool_runtime, "call", return_value="Private tool data"):
            with self.assertRaisesRegex(RuntimeError, "max_calls=1"):
                self.invoke(traced)
        self.assertEqual(len(prompts), 1)
        self.assertEqual([entry.status for entry in self.entries()], ["success", "budget_exceeded"])
        self.assertEqual([entry.usage_input_tokens for entry in self.entries()], [100, 0])

    def test_tool_continuation_obeys_cumulative_prompt_budget(self) -> None:
        traced, routed, prompts = self.runtime([self.tool_response, "Finished"])
        prepared = routed.prepare_request("Private system", "Private task", stage="research_planning", purpose="plan")
        traced.config = replace(traced.config, max_prompt_chars=len(prepared.system) + len(prepared.user) + 1)
        with mock.patch.object(routed.tool_runtime, "call", return_value="Private tool data"):
            with self.assertRaisesRegex(RuntimeError, "max_prompt_chars="):
                self.invoke(traced)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(self.entries()[-1].status, "budget_exceeded")

    def test_each_round_records_usage_and_final_call_owns_validation(self) -> None:
        traced, routed, prompts = self.runtime([self.tool_response, self.tool_response, "Finished"], max_calls=3)
        with mock.patch.object(routed.tool_runtime, "call", return_value="Private tool data") as tool:
            response, call_id = self.invoke(traced)
        entries = self.entries()
        self.assertEqual((response, call_id, tool.call_count), ("Finished", 3, 2))
        self.assertEqual([entry.status for entry in entries], ["success", "success", "validation_pending"])
        self.assertEqual([entry.usage_input_tokens for entry in entries], [100, 200, 300])
        self.assertEqual([entry.usage_output_tokens for entry in entries], [10, 20, 30])
        for entry, (system, user) in zip(entries, prompts):
            self.assertEqual(entry.user_sha256, hashlib.sha256(user.encode()).hexdigest())
            self.assertEqual(entry.system_chars + entry.user_chars, len(system) + len(user))
            self.assertEqual(entry.agent_id, "gap_analyst")
            self.assertTrue(entry.skill_hashes)
        self.assertNotIn("Private tool data", (self.run_dir / "run-llm-ledger.json").read_text())
        traced.record_validation_result(stage="research_planning", valid=False, error="Invalid final answer", call_id=call_id)
        self.assertEqual([entry.status for entry in self.entries()], ["success", "success", "invalid_response"])

    def test_failed_continuation_does_not_reuse_previous_usage(self) -> None:
        traced, routed, prompts = self.runtime([self.tool_response, RuntimeError("Provider unavailable")])
        with mock.patch.object(routed.tool_runtime, "call", return_value="Private tool data"):
            with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
                self.invoke(traced)
        self.assertEqual(len(prompts), 2)
        self.assertEqual([entry.status for entry in self.entries()], ["success", "failed"])
        self.assertEqual([entry.usage_input_tokens for entry in self.entries()], [100, 0])
        self.assertIsNone(routed.last_usage)

    def test_denied_tool_records_receipt_without_extra_model_call(self) -> None:
        other_tool = self.tool_response.replace("local-docs", "unassigned")
        traced, routed, prompts = self.runtime([other_tool])
        with self.assertRaises(RuntimeError):
            self.invoke(traced)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(len(self.entries()), 1)
        receipts = json.loads((self.run_dir / "run-tool-receipts.json").read_text())
        self.assertIn('"denied"', json.dumps(receipts))

    def test_round_limit_keeps_all_actual_calls_in_ledger(self) -> None:
        traced, routed, prompts = self.runtime([self.tool_response] * 3)
        with mock.patch.object(routed.tool_runtime, "call", return_value="Private tool data") as tool:
            with self.assertRaisesRegex(RuntimeError, "round limit"):
                self.invoke(traced)
        self.assertEqual((len(prompts), tool.call_count, len(self.entries())), (3, 2, 3))


class SkillFingerprintTest(unittest.TestCase):
    """SKILL-02: effective skill content is hashed into the checkpoint and the
    per-call ledger, so changing skill content invalidates old checkpoints."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.run_dir = self.project_root / "run"
        self.run_dir.mkdir()
        _skills_root(self.project_root, ["evidence-grounding", "skeptical-review"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_checkpoint_includes_effective_default_skills_when_enabled(self) -> None:
        import research_agent.pipeline as pipeline_module

        config = AgentConfig(
            llm=LLMConfig(base_url=LOCAL_BASE_URL, model="m"),
            multi_agent=MultiAgentConfig(enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")]),
        )
        contract = pipeline_module._checkpoint_contract("主题", config)
        skill_records = [
            item
            for item in contract["configured_inputs"]
            if str(item.get("configured_path", "")).startswith("skill:")
        ]
        self.assertTrue(skill_records)
        self.assertTrue(all(item.get("skill_source") == "default" for item in skill_records))
        self.assertTrue(all(item.get("sha256") for item in skill_records))

        # Changing which default skills bind to a role changes the fingerprint.
        with mock.patch.dict(
            "research_agent.agent_runtime.DEFAULT_ROLE_SKILLS",
            {"skeptical_reviewer": ["evidence-grounding"]},
        ):
            changed = pipeline_module._checkpoint_contract("主题", config)
        self.assertNotEqual(changed["fingerprint"], contract["fingerprint"])

    def test_checkpoint_has_no_skill_records_when_multi_agent_disabled(self) -> None:
        import research_agent.pipeline as pipeline_module

        config = AgentConfig(llm=LLMConfig(base_url=LOCAL_BASE_URL, model="m"))
        contract = pipeline_module._checkpoint_contract("主题", config)
        skill_records = [
            item
            for item in contract["configured_inputs"]
            if str(item.get("configured_path", "")).startswith("skill:")
        ]
        self.assertEqual(skill_records, [])

    def test_ledger_records_skill_content_hashes(self) -> None:
        config = AgentConfig(
            llm=LLMConfig(base_url=LOCAL_BASE_URL, model="m"),
            multi_agent=MultiAgentConfig(enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")]),
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        # Stub the client build: the ledger must record the skill content that
        # prepare_request bound, regardless of what the endpoint returns.
        with mock.patch.object(routed, "_client_for", return_value=_FakeLLM()):
            traced = trace_llm(routed, self.run_dir, config.llm)
            complete_with_purpose_detail(traced, "sys", "user", stage="paper_review_loop", purpose="review")
        entries = _read_entries(self.run_dir / "run-llm-ledger.json")
        self.assertTrue(entries)
        hashes = entries[-1].skill_hashes
        self.assertTrue(hashes)
        self.assertTrue(all(item.startswith("skeptical-review:") for item in hashes))
        self.assertTrue(all(len(item.split(":")[1]) == 16 for item in hashes))


if __name__ == "__main__":
    unittest.main()
