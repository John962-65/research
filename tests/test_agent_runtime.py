from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.agent_runtime import (
    DEFAULT_ROLE_SKILLS,
    AgentRoutedLLM,
    RoleModelRouter,
    agent_for_stage,
)
from research_agent.config import AgentConfig, AgentRoleConfig, LLMConfig, MultiAgentConfig

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

    def test_clients_cached_per_endpoint_and_model(self) -> None:
        config = _config(
            enabled=True,
            roles=[
                AgentRoleConfig(agent_id="gap_analyst", base_url=ALT_BASE_URL),
                AgentRoleConfig(agent_id="skeptical_reviewer"),
            ],
            task_models={"research_planning": "planner-model", "paper_review_loop": "reviewer-model"},
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
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
                    api_key_env="ROLE_API_KEY",
                )
            ],
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        client = routed._client_for(routed.router.resolve(stage="research_planning"))
        self.assertEqual(client.base_url, ALT_BASE_URL)
        # The credential itself stays empty: the env var is resolved by
        # resolve_llm_api_key and this test environment does not set it.
        self.assertEqual(client.api_key, "")

    def test_sampling_parameters_reach_client(self) -> None:
        config = replace(
            _config(),
            llm=LLMConfig(base_url=LOCAL_BASE_URL, model="m", temperature=0.3, max_tokens=512),
        )
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        client = routed._client_for(routed.router.resolve(stage="research_planning"))
        self.assertEqual(client.temperature, 0.3)
        self.assertEqual(client.max_tokens, 512)


if __name__ == "__main__":
    unittest.main()
