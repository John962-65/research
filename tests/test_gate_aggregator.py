from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest import mock
from types import SimpleNamespace

from research_agent.agent_runtime import AgentRoutedLLM, DEFAULT_ROLE_SKILLS
from research_agent.agent_verdict import (
    ROLE_EVIDENCE_VIEWS,
    _parse_verdict,
    run_independent_deliberation,
)
from research_agent.config import AgentConfig, AgentRoleConfig, LLMConfig, MultiAgentConfig
from research_agent.final_readiness import apply_gate_to_final_readiness
from research_agent.gate_aggregator import aggregate_final_decision
from research_agent.llm import enumerate_llm_routes
from research_agent.llm_trace import _read_entries, trace_llm

LOCAL_BASE_URL = "http://127.0.0.1:9/v1"

VALID_VERDICT_JSON = json.dumps({
    "verdict": "pass",
    "confidence": 0.8,
    "evidence_refs": ["01-context.json"],
    "counter_evidence": [],
    "required_actions": [],
    "summary": "证据边界一致",
})


class _VerdictLLM:
    model = "fake-model"
    base_url = LOCAL_BASE_URL

    def complete(self, system: str, user: str) -> str:
        return VALID_VERDICT_JSON


class ParseVerdictTest(unittest.TestCase):
    def test_valid_verdict_parsed(self) -> None:
        parsed, error = _parse_verdict(VALID_VERDICT_JSON)
        self.assertEqual(error, "")
        self.assertEqual(parsed["verdict"], "pass")

    def test_fenced_json_accepted(self) -> None:
        parsed, error = _parse_verdict(f"```\n{VALID_VERDICT_JSON}\n```")
        self.assertEqual(error, "")
        self.assertEqual(parsed["verdict"], "pass")

    def test_unknown_verdict_rejected(self) -> None:
        parsed, error = _parse_verdict('{"verdict": "excellent", "confidence": 0.5}')
        self.assertEqual(parsed, {})
        self.assertIn("verdict must be one of", error)

    def test_non_json_rejected(self) -> None:
        parsed, error = _parse_verdict("我觉得没问题")
        self.assertEqual(parsed, {})
        self.assertIn("not valid JSON", error)

    def test_confidence_out_of_range_rejected(self) -> None:
        parsed, error = _parse_verdict('{"verdict": "pass", "confidence": 1.5}')
        self.assertEqual(parsed, {})
        self.assertIn("confidence", error)


class GateAggregatorTest(unittest.TestCase):
    def test_pipeline_rechecks_override_file_against_current_evidence(self) -> None:
        from research_agent.pipeline import _finalize_gate_decision
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            kwargs = dict(agent_deliberation={"status": "pass"},
                          claim_consistency={"status": "block", "reason": "unmatched split"},
                          citation_grounding=SimpleNamespace(status="pass"),
                          revised_review=SimpleNamespace(decision="accept"), resume=True)
            def finalize():
                return _finalize_gate_decision("test", out, AgentConfig(), None, **kwargs)[0]
            initial = finalize()
            override = dict(reviewer="reviewer", reason="Accepted limitation", approved=False,
                            revision=0, verdict_sha256=initial["inputs"]["verdict_sha256"])
            path = out / "10-gate-override.json"
            path.write_text(json.dumps(override))
            self.assertEqual(finalize()["status"], "blocked")
            path.write_text(json.dumps(override | {"approved": True}))
            self.assertEqual(finalize()["status"], "publishable")
            kwargs["claim_consistency"]["reason"] = "different evidence"
            self.assertEqual(finalize()["status"], "blocked")

    def test_all_pass_is_publishable(self) -> None:
        decision = aggregate_final_decision(
            deterministic_audits={"agent_deliberation": {"status": "pass"}},
            independent_deliberation={"verdicts": [
                {"agent_id": "skeptical_reviewer", "verdict": "pass"},
                {"agent_id": "statistician", "verdict": "pass"},
            ]},
            expected_roles=["skeptical_reviewer", "statistician"],
        )
        self.assertEqual(decision.status, "publishable")

    def test_deterministic_block_blocks(self) -> None:
        decision = aggregate_final_decision(
            deterministic_audits={"claim_consistency": {"status": "block"}},
            independent_deliberation=None,
        )
        self.assertEqual(decision.status, "blocked")
        self.assertIn("deterministic:claim_consistency", decision.blocking_sources)

    def test_independent_block_blocks(self) -> None:
        decision = aggregate_final_decision(
            deterministic_audits={},
            independent_deliberation={"verdicts": [{"agent_id": "statistician", "verdict": "block"}]},
            expected_roles=["statistician"],
        )
        self.assertEqual(decision.status, "blocked")
        self.assertIn("verdict:statistician", decision.blocking_sources)

    def test_invalid_verdict_blocks(self) -> None:
        decision = aggregate_final_decision(
            deterministic_audits={},
            independent_deliberation={"verdicts": [{"agent_id": "gap_analyst", "verdict": "invalid"}]},
        )
        self.assertEqual(decision.status, "blocked")

    def test_missing_expected_role_blocks(self) -> None:
        decision = aggregate_final_decision(
            deterministic_audits={},
            independent_deliberation={"verdicts": [{"agent_id": "skeptical_reviewer", "verdict": "pass"}]},
            expected_roles=["skeptical_reviewer", "statistician"],
        )
        self.assertEqual(decision.status, "blocked")
        self.assertIn("statistician", decision.missing_verdict_roles)

    def test_warnings_become_repair_required(self) -> None:
        decision = aggregate_final_decision(
            deterministic_audits={"agent_deliberation": {"status": "warn"}},
            independent_deliberation={"verdicts": [{"agent_id": "skeptical_reviewer", "verdict": "warn"}]},
            expected_roles=["skeptical_reviewer"],
        )
        self.assertEqual(decision.status, "repair_required")

    def test_human_override_requires_full_provenance(self) -> None:
        blocked_inputs = dict(
            deterministic_audits={"claim_consistency": {"status": "block"}},
            independent_deliberation=None,
        )
        partial = aggregate_final_decision(**blocked_inputs, human_override={"reviewer": "amy", "reason": "ok"})
        self.assertEqual(partial.status, "blocked")
        self.assertTrue(any("override_rejected" in item for item in partial.warning_sources))

        full = aggregate_final_decision(
            **blocked_inputs,
            human_override={
                "reviewer": "amy",
                "reason": "已知限制，人工接受",
                "revision": 0,
                "verdict_sha256": partial.inputs["verdict_sha256"],
                "approved": True,
            },
        )
        self.assertEqual(full.status, "publishable")
        self.assertTrue(full.overridden)
        self.assertEqual(full.override["reviewer"], "amy")

    def test_override_rejects_invalid_semantics_and_changed_evidence(self) -> None:
        inputs = dict(deterministic_audits={"audit": {"status": "block", "evidence": "original"}},
                      independent_deliberation=None, revision=3)
        digest = aggregate_final_decision(**inputs).inputs["verdict_sha256"]
        valid = dict(reviewer="reviewer", reason="Accepted limitation", revision=3,
                     verdict_sha256=digest, approved=True)
        for change in ({"approved": False}, {"approved": "true"}, {"approved": 1},
                       {"revision": 2}, {"revision": "3"}, {"revision": True},
                       {"verdict_sha256": "a" * 64}, {"verdict_sha256": "哈希"},
                       {"reviewer": " "}, {"reason": "\n"}):
            with self.subTest(change=change):
                decision = aggregate_final_decision(**inputs, human_override=valid | change)
                self.assertEqual(decision.status, "blocked")
                self.assertFalse(decision.overridden)
        inputs["deterministic_audits"]["audit"]["evidence"] = "changed"
        self.assertEqual(aggregate_final_decision(**inputs, human_override=valid).status, "blocked")

    def test_missing_independent_report_cannot_satisfy_required_roles(self) -> None:
        decision = aggregate_final_decision(deterministic_audits={},
            independent_deliberation=None, expected_roles=["statistician"])
        self.assertEqual(decision.status, "blocked")
        self.assertEqual(decision.missing_verdict_roles, ["statistician"])

    def test_blocked_final_readiness_cannot_be_publishable(self) -> None:
        from research_agent.models import FinalReadinessReport

        report = FinalReadinessReport(
            topic="t",
            status="ready_for_human_polish",
            score_before=8.0,
            score_after=8.0,
            unsupported_before=0,
            unsupported_after=0,
            weak_before=0,
            weak_after=0,
            deferred_tasks=[],
            blocking_issues=[],
            recommendation="ready",
            next_actions=[],
        )
        gated = apply_gate_to_final_readiness(
            report,
            {"status": "blocked", "blocking_sources": ["verdict:statistician"], "overridden": False},
        )
        self.assertEqual(gated.status, "blocked")
        self.assertIn("gate:verdict:statistician", gated.blocking_issues)
        untouched = apply_gate_to_final_readiness(report, {"status": "publishable", "blocking_sources": []})
        self.assertEqual(untouched.status, "ready_for_human_polish")


class IndependentDeliberationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.run_dir = self.project_root / "run"
        self.run_dir.mkdir()
        for skill_id in {skill for skills in DEFAULT_ROLE_SKILLS.values() for skill in skills}:
            skills = self.project_root / "skills" / skill_id
            skills.mkdir(parents=True)
            (skills / "SKILL.md").write_text(f"# {skill_id}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _config(self) -> AgentConfig:
        return AgentConfig(
            llm=LLMConfig(base_url=LOCAL_BASE_URL, model="default-model"),
            multi_agent=MultiAgentConfig(enabled=True, roles=[AgentRoleConfig(agent_id="skeptical_reviewer")]),
        )

    def test_independent_verdicts_are_bound_to_real_calls(self) -> None:
        config = self._config()
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        with mock.patch.object(routed, "_client_for", return_value=_VerdictLLM()):
            traced = trace_llm(routed, self.run_dir, config.llm)
            report = run_independent_deliberation("独立审查测试", self.run_dir, config, traced)
        self.assertTrue(report["independent_agent_execution"])
        self.assertEqual(report["status"], "pass")
        verdicts = {item["agent_id"]: item for item in report["verdicts"]}
        self.assertIn("statistician", verdicts)
        self.assertIn("skeptical_reviewer", verdicts)
        for item in verdicts.values():
            self.assertTrue(item["independent"])
            self.assertGreater(item["call_id"], 0)
            self.assertTrue(item["response_sha256"])
        # The ledger holds one real call per role.
        entries = _read_entries(self.run_dir / "run-llm-ledger.json")
        self.assertEqual(len(entries), len(ROLE_EVIDENCE_VIEWS))
        self.assertEqual({entry.agent_id for entry in entries}, set(ROLE_EVIDENCE_VIEWS))
        for entry in entries:
            self.assertEqual(entry.skills, DEFAULT_ROLE_SKILLS[entry.agent_id])
            self.assertTrue(entry.skill_hashes)

    def test_role_failure_becomes_block(self) -> None:
        class _BrokenLLM:
            model = "fake-model"
            base_url = LOCAL_BASE_URL

            def complete(self, system: str, user: str) -> str:
                raise RuntimeError("gateway down")

        config = self._config()
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        with mock.patch.object(routed, "_client_for", return_value=_BrokenLLM()):
            traced = trace_llm(routed, self.run_dir, config.llm)
            report = run_independent_deliberation("独立审查测试", self.run_dir, config, traced)
        self.assertEqual(report["status"], "block")
        self.assertTrue(any(item["verdict"] == "invalid" for item in report["verdicts"]))


class RouteEnumerationTest(unittest.TestCase):
    """ROUTE-01: every (provider, endpoint, model, credential) route is listed."""

    def test_routes_include_global_tasks_and_roles(self) -> None:
        config = AgentConfig(
            llm=LLMConfig(base_url=LOCAL_BASE_URL, model="default-model"),
            multi_agent=MultiAgentConfig(
                enabled=True,
                roles=[AgentRoleConfig(agent_id="skeptical_reviewer", model="reviewer-model")],
                task_models={"research_planning": "planner-model"},
            ),
        )
        routes = {route["route_id"]: route for route in enumerate_llm_routes(config)}
        self.assertIn("global", routes)
        self.assertIn("task:research_planning", routes)
        self.assertIn("role:skeptical_reviewer", routes)
        self.assertEqual(routes["role:skeptical_reviewer"]["model"], "reviewer-model")
        self.assertEqual(routes["task:research_planning"]["model"], "planner-model")

    def test_preflight_reports_route_check(self) -> None:
        from research_agent.preflight import run_preflight

        good = AgentConfig(llm=LLMConfig(base_url=LOCAL_BASE_URL, model="default-model"))
        report = run_preflight("路由测试", good, ping_llm=False)
        route_checks = [check for check in report.checks if check.name == "llm_routes"]
        self.assertTrue(any(check.status == "pass" for check in route_checks))

        broken = AgentConfig(
            llm=LLMConfig(base_url=LOCAL_BASE_URL),
            multi_agent=MultiAgentConfig(
                enabled=True,
                roles=[AgentRoleConfig(agent_id="gap_analyst", base_url="http://127.0.0.1:10/v1")],
                task_models={"idea_generation": "m"},
            ),
        )
        report = run_preflight("路由测试", broken, ping_llm=False)
        route_checks = [check for check in report.checks if check.name == "llm_routes"]
        self.assertTrue(any(check.status == "fail" for check in route_checks))


class ProviderUsageTest(unittest.TestCase):
    """COST-01: provider-reported usage reaches the ledger and economics."""

    def test_usage_captured_from_response_and_recorded_in_ledger(self) -> None:
        from research_agent.llm import _provider_usage

        usage = _provider_usage({"usage": {"prompt_tokens": 11, "completion_tokens": 7}})
        self.assertEqual(usage, {"input_tokens": 11, "output_tokens": 7})
        self.assertIsNone(_provider_usage({"usage": None}))

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            config = self._config()
            routed = AgentRoutedLLM(config, self.project_root, self.run_dir)

            class _UsageLLM:
                model = "fake-model"
                base_url = LOCAL_BASE_URL
                last_usage = {"input_tokens": 11, "output_tokens": 7}

                def complete(self, system: str, user: str) -> str:
                    return "ok"

            with mock.patch.object(routed, "_client_for", return_value=_UsageLLM()):
                traced = trace_llm(routed, run_dir, config.llm)
                traced.complete("sys", "user")
            entries = _read_entries(run_dir / "run-llm-ledger.json")
            self.assertEqual(entries[-1].usage_input_tokens, 11)
            self.assertEqual(entries[-1].usage_output_tokens, 7)
            self.assertEqual(entries[-1].usage_source, "provider")

    def _config(self) -> AgentConfig:
        return AgentConfig(llm=LLMConfig(base_url=LOCAL_BASE_URL, model="m"))

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.project_root = Path(self._tmp.name)
        self.run_dir = self.project_root / "run"
        self.run_dir.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
