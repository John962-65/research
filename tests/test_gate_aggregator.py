from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
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
        # 引用实际收到材料里的第一个文件名，模拟合规的证据引用。
        names = re.findall(r'"([0-9A-Za-z_\-]+\.(?:json|md))":\s*\{', user)
        refs = names[:1] or ["none.json"]
        return json.dumps({
            "verdict": "pass",
            "confidence": 0.8,
            "evidence_refs": refs,
            "counter_evidence": [],
            "required_actions": [],
            "summary": "证据边界一致",
        })


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

    def test_minimal_verdict_without_refs_or_summary_rejected(self) -> None:
        # A09 前置：最小 {verdict, confidence} 响应不再被接受。
        parsed, error = _parse_verdict('{"verdict": "pass", "confidence": 0.9}')
        self.assertEqual(parsed, {})
        self.assertIn("summary", error)
        parsed, error = _parse_verdict(json.dumps({"verdict": "pass", "confidence": 0.9, "summary": "ok", "evidence_refs": []}))
        self.assertEqual(parsed, {})
        self.assertIn("evidence_refs", error)


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
                            revision=0, verdict_sha256=initial["inputs"]["verdict_sha256"],
                            reason_code="documented_exception",
                            approval_object="deterministic:claim_consistency",
                            scope="仅接受 claim_consistency 的本次阻断，不影响其他审计")
            path = out / "10-gate-override.json"
            path.write_text(json.dumps(override))
            self.assertEqual(finalize()["status"], "blocked")
            path.write_text(json.dumps(override | {"approved": True}))
            decided = finalize()
            self.assertEqual(decided["status"], "publishable")
            # 覆盖后保留原机器决定与原始阻断记录。
            self.assertEqual(decided["override"]["original_status"], "blocked")
            self.assertIn("deterministic:claim_consistency", decided["blocking_sources"])
            self.assertTrue((out / "10-review-input-snapshot.json").exists())
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

        valid_override = {
            "reviewer": "amy",
            "reason": "已知限制，人工接受",
            "reason_code": "documented_exception",
            "approval_object": "deterministic:claim_consistency",
            "scope": "仅本次 claim_consistency 阻断",
            "revision": 0,
            "verdict_sha256": partial.inputs["verdict_sha256"],
            "approved": True,
        }
        full = aggregate_final_decision(**blocked_inputs, human_override=valid_override)
        self.assertEqual(full.status, "publishable")
        self.assertTrue(full.overridden)
        self.assertEqual(full.override["reviewer"], "amy")
        self.assertEqual(full.override["original_status"], "blocked")
        # 缺 reason_code 的旧格式覆盖不再生效。
        legacy = {k: v for k, v in valid_override.items() if k != "reason_code"}
        rejected = aggregate_final_decision(**blocked_inputs, human_override=legacy)
        self.assertEqual(rejected.status, "blocked")
        self.assertTrue(any("reason_code" in item for item in rejected.warning_sources))

    def test_partial_override_only_dissolves_approved_blockers(self) -> None:
        # 复审场景 1：三条阻断同时存在（普通建议性 / 来源不可核验 / 缺统计角色），
        # 人工批准明确只接受第一条 → 其余阻断（含缺失角色）继续阻止放行。
        inputs = dict(
            deterministic_audits={
                "advisory_check": {"status": "block", "reason": "边界措辞需收紧"},
                "provenance_check": {"status": "block", "overridable": False, "block_reason_code": "unverifiable_source"},
            },
            independent_deliberation={"verdicts": [{"agent_id": "statistician", "verdict": "pass"}]},
            expected_roles=["statistician", "evidence_curator"],
        )
        decision = aggregate_final_decision(**inputs)
        self.assertEqual(decision.status, "blocked")
        blockers = decision.blocking_sources
        self.assertIn("deterministic:advisory_check", blockers)
        self.assertIn("deterministic:provenance_check", blockers)
        self.assertIn("missing_verdict:evidence_curator", blockers)
        digest = decision.inputs["verdict_sha256"]
        override = {
            "reviewer": "amy",
            "reason": "只接受边界措辞问题",
            "reason_code": "scope_limitation",
            "approval_object": "deterministic:advisory_check",
            "approved_blockers": ["deterministic:advisory_check"],
            "scope": "仅收紧措辞问题",
            "revision": 0,
            "verdict_sha256": digest,
            "approved": True,
        }
        partial = aggregate_final_decision(**inputs, human_override=override)
        self.assertEqual(partial.status, "blocked", "未被覆盖的阻断必须继续阻止放行")
        self.assertTrue(partial.overridden)
        self.assertEqual(partial.override["dissolved_blockers"], ["deterministic:advisory_check"])
        self.assertIn("deterministic:provenance_check", partial.override["remaining_blockers"])
        self.assertIn("missing_verdict:evidence_curator", partial.override["remaining_blockers"])
        # 来源不可核验与缺失角色即使被列入批准清单也不生效（系统推导不可覆盖）。
        greedy = aggregate_final_decision(
            **inputs,
            human_override=override | {
                "approved_blockers": [
                    "deterministic:advisory_check",
                    "deterministic:provenance_check",
                    "missing_verdict:evidence_curator",
                ]
            },
        )
        self.assertEqual(greedy.status, "blocked")
        self.assertTrue(any("non_overridable:deterministic:provenance_check" in w for w in greedy.warning_sources))
        self.assertTrue(any("non_overridable:missing_verdict:evidence_curator" in w for w in greedy.warning_sources))
        # 只批准第一条（唯一可覆盖项）→ 全部消解后才可放行。
        inputs_single = dict(
            deterministic_audits={"advisory_check": {"status": "block", "reason": "边界措辞需收紧"}},
            independent_deliberation=None,
        )
        single_digest = aggregate_final_decision(**inputs_single).inputs["verdict_sha256"]
        ok = aggregate_final_decision(**inputs_single, human_override=override | {"verdict_sha256": single_digest})
        self.assertEqual(ok.status, "publishable")
        self.assertEqual(ok.override["remaining_blockers"], [])
        # 批准清单包含不存在的阻断 → 拒绝。
        bad = aggregate_final_decision(
            **inputs_single,
            human_override=override | {"verdict_sha256": single_digest, "approved_blockers": ["deterministic:advisory_check", "ghost:missing"]},
        )
        self.assertEqual(bad.status, "blocked")
        self.assertTrue(any("unknown ghost:missing" in w for w in bad.warning_sources))

    def test_non_overridable_reasons_reject_override(self) -> None:
        # decision-contract §3.2：不可覆盖原因码出现时覆盖一律不生效。
        inputs = dict(deterministic_audits={"claim_consistency": {"status": "block"}}, independent_deliberation=None)
        digest = aggregate_final_decision(**inputs).inputs["verdict_sha256"]
        valid_override = {
            "reviewer": "amy",
            "reason": "试图覆盖数据损坏",
            "reason_code": "scope_limitation",
            "approval_object": "deterministic:claim_consistency",
            "scope": "全部阻断",
            "revision": 0,
            "verdict_sha256": digest,
            "approved": True,
        }
        decision = aggregate_final_decision(
            **inputs, human_override=valid_override, non_overridable_reasons=["corrupted_input:04-results.json"]
        )
        self.assertEqual(decision.status, "blocked")
        self.assertFalse(decision.overridden)
        self.assertTrue(any("non_overridable:corrupted_input" in item for item in decision.warning_sources))
        # 原因码本身落在不可覆盖词表 → 拒绝。
        decision2 = aggregate_final_decision(**inputs, human_override=valid_override | {"reason_code": "invalid_approval"})
        self.assertEqual(decision2.status, "blocked")

    def test_override_rejects_invalid_semantics_and_changed_evidence(self) -> None:
        inputs = dict(deterministic_audits={"audit": {"status": "block", "evidence": "original"}},
                      independent_deliberation=None, revision=3)
        digest = aggregate_final_decision(**inputs).inputs["verdict_sha256"]
        valid = dict(reviewer="reviewer", reason="Accepted limitation", revision=3,
                     verdict_sha256=digest, approved=True,
                     reason_code="scope_limitation", approval_object="deterministic:audit", scope="仅本次阻断")
        for change in ({"approved": False}, {"approved": "true"}, {"approved": 1},
                       {"revision": 2}, {"revision": "3"}, {"revision": True},
                       {"verdict_sha256": "a" * 64}, {"verdict_sha256": "哈希"},
                       {"reviewer": " "}, {"reason": "\n"}, {"approval_object": "deterministic:other"}):
            with self.subTest(change=change):
                decision = aggregate_final_decision(**inputs, human_override=valid | change)
                self.assertEqual(decision.status, "blocked")
                self.assertFalse(decision.overridden)
        # A05：审计状态不变、证据正文变 → 摘要变化，旧批准失效。
        inputs["deterministic_audits"]["audit"]["evidence"] = "changed"
        self.assertEqual(aggregate_final_decision(**inputs, human_override=valid).status, "blocked")

    def test_verdict_must_match_ledger_records(self) -> None:
        # A09：伪造/失败/错角色的 call_id 或无引用 pass → 不计作有效独立评审票。
        verdict = {"agent_id": "statistician", "verdict": "pass", "call_id": 7, "response_sha256": "abcd1234"}
        good_entry = {
            "call_id": 7,
            "status": "success",
            "agent_id": "statistician",
            "stage": "paper_deliberation",
            "response_sha256": "abcd1234" + "0" * 48,
        }
        base = dict(deterministic_audits={}, independent_deliberation={"verdicts": [verdict]})
        ok = aggregate_final_decision(**base, llm_ledger=[good_entry])
        self.assertEqual(ok.status, "publishable")
        for ledger, problem in (
            ([], "not found"),
            ([good_entry | {"call_id": 8}], "not found"),
            ([good_entry | {"status": "failed"}], "is not success"),
            ([good_entry | {"agent_id": "evidence_curator"}], "does not match"),
            ([good_entry | {"stage": "paper_writing"}], "is not paper_deliberation"),
            ([good_entry | {"response_sha256": "f" * 64}], "does not match"),
        ):
            with self.subTest(problem=problem):
                decision = aggregate_final_decision(**base, llm_ledger=ledger)
                self.assertEqual(decision.status, "blocked")
                self.assertTrue(any("unverified_call" in item for item in decision.blocking_sources))

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
        # 各角色的证据视图文件真实存在，verdict 的 evidence_refs 才可定位。
        for name in sorted({path for paths in ROLE_EVIDENCE_VIEWS.values() for path in paths}):
            if name.endswith(".md"):
                (self.run_dir / name).write_text("# 修订稿内容\n", encoding="utf-8")
            else:
                (self.run_dir / name).write_text("{}", encoding="utf-8")

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

    def test_stale_deliberation_is_rerun_on_resume(self) -> None:
        # A06（前半）：恢复时旧 deliberation 的输入快照不一致 → 不复用，重新执行。
        from research_agent.pipeline import _finalize_gate_decision

        config = self._config()
        (self.run_dir / "09-revised-paper.md").write_text("# 修订稿 v1", encoding="utf-8")
        routed = AgentRoutedLLM(config, self.project_root, self.run_dir)
        with mock.patch.object(routed, "_client_for", return_value=_VerdictLLM()):
            traced = trace_llm(routed, self.run_dir, config.llm)
            stale = run_independent_deliberation(
                "独立审查测试", self.run_dir, config, traced, review_input_sha256="old-digest"
            )
        self.assertEqual(stale["review_input_sha256"], "old-digest")
        # 稿件变化后恢复：快照 digest 与旧戳不一致，必须重跑 deliberation。
        (self.run_dir / "09-revised-paper.md").write_text("# 修订稿 v2（已改动）", encoding="utf-8")
        with mock.patch.object(routed, "_client_for", return_value=_VerdictLLM()):
            traced2 = trace_llm(routed, self.run_dir, config.llm)
            decision, outputs = _finalize_gate_decision(
                "独立审查测试",
                self.run_dir,
                config,
                traced2,
                agent_deliberation={"status": "pass"},
                claim_consistency={"status": "pass"},
                citation_grounding=SimpleNamespace(status="pass"),
                revised_review=SimpleNamespace(decision="accept"),
                resume=True,
            )
        fresh = json.loads((self.run_dir / "10-independent-deliberation.json").read_text(encoding="utf-8"))
        self.assertNotEqual(fresh["review_input_sha256"], "old-digest")
        self.assertIn("10-independent-deliberation.json", outputs)
        self.assertEqual(decision["status"], "publishable")


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
