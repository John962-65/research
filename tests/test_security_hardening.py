from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from research_agent.agent_runtime import AgentRoutedLLM
from research_agent.config import AgentConfig, AgentRoleConfig, LLMConfig, MCPServerConfig, MultiAgentConfig, load_config
from research_agent.llm import resolve_role_llm_config
from research_agent.preflight import run_preflight
from research_agent.workflow_graph import apply_rollback, build_rollback_preview, issue_rollback_preview, update_workflow_stage

PROJECT_ROOT = Path(__file__).resolve().parents[1]

GLOBAL_BASE_URL = "http://127.0.0.1:9/v1"  # port 9: nothing listens there for non-capture paths
GLOBAL_CAPTURE_PORT = None  # assigned at runtime
ROLE_CAPTURE_PORT = None


class _CaptureHandler(BaseHTTPRequestHandler):
    server_version = "CaptureServer/1"

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.server.captured.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization") or "",
            }
        )
        body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_capture_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    server.captured = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class CredentialOriginCaptureTest(unittest.TestCase):
    """SEC-01: the global literal API key must never reach a different origin."""

    def setUp(self) -> None:
        self.global_server = _start_capture_server()
        self.role_server = _start_capture_server()
        self.global_base = f"http://127.0.0.1:{self.global_server.server_port}/v1"
        self.role_base = f"http://127.0.0.1:{self.role_server.server_port}/v1"

    def tearDown(self) -> None:
        self.global_server.shutdown()
        self.global_server.server_close()
        self.role_server.shutdown()
        self.role_server.server_close()

    def _config(self, **multi_agent_kwargs: object) -> AgentConfig:
        return AgentConfig(
            llm=LLMConfig(base_url=self.global_base, api_key="global-literal-key", model="default-model"),
            multi_agent=MultiAgentConfig(**multi_agent_kwargs),
        )

    def _complete(self, config: AgentConfig, stage: str) -> None:
        with TemporaryDirectory() as tmp:
            routed = AgentRoutedLLM(config, Path(tmp), Path(tmp) / "run")
            client = routed._client_for(routed.router.resolve(stage=stage))
            client.complete("system", "user")

    def test_cross_origin_role_never_receives_global_literal_key(self) -> None:
        config = self._config(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    base_url=self.role_base,
                    base_url_env="ROLE_TEST_BASE_URL",
                    api_key_env="ROLE_TEST_API_KEY",
                )
            ],
        )
        with mock.patch.dict(os.environ, {"ROLE_TEST_BASE_URL": self.role_base, "ROLE_TEST_API_KEY": "role-scoped-key"}):
            self._complete(config, "research_planning")
        self.assertEqual(len(self.role_server.captured), 1)
        self.assertEqual(self.role_server.captured[0]["authorization"], "Bearer role-scoped-key")
        # The global endpoint must not have been contacted at all for this call.
        self.assertEqual(self.global_server.captured, [])

    def test_cross_origin_role_without_env_pair_is_rejected(self) -> None:
        config = self._config(
            enabled=True,
            roles=[AgentRoleConfig(agent_id="gap_analyst", base_url=self.role_base)],
        )
        with self.assertRaises(ValueError) as caught:
            self._complete(config, "research_planning")
        self.assertIn("credential binding rejected", str(caught.exception))
        self.assertEqual(self.role_server.captured, [])

    def test_cross_origin_role_with_mismatched_env_origin_is_rejected(self) -> None:
        config = self._config(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    base_url=self.role_base,
                    base_url_env="ROLE_TEST_BASE_URL",
                    api_key_env="ROLE_TEST_API_KEY",
                )
            ],
        )
        # The env endpoint points at the global origin instead of the role's.
        with mock.patch.dict(os.environ, {"ROLE_TEST_BASE_URL": self.global_base, "ROLE_TEST_API_KEY": "k"}):
            with self.assertRaises(ValueError) as caught:
                self._complete(config, "research_planning")
        self.assertIn("does not match", str(caught.exception))
        self.assertEqual(self.role_server.captured, [])

    def test_global_literal_key_missing_env_still_cleared_cross_origin(self) -> None:
        # Even with no role env vars at all, the literal key must not be reused.
        config = self._config(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    base_url=self.role_base,
                    base_url_env="ROLE_TEST_BASE_URL",
                    api_key_env="ROLE_TEST_API_KEY",
                )
            ],
        )
        env = {k: v for k, v in os.environ.items() if k not in {"ROLE_TEST_BASE_URL", "ROLE_TEST_API_KEY"}}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                self._complete(config, "research_planning")
        self.assertEqual(self.role_server.captured, [])

    def test_same_origin_role_still_uses_global_key(self) -> None:
        # Role endpoint that only changes the path (same origin) stays compatible.
        config = self._config(
            enabled=True,
            roles=[AgentRoleConfig(agent_id="gap_analyst", base_url=self.global_base)],
        )
        self._complete(config, "research_planning")
        self.assertEqual(len(self.global_server.captured), 1)
        self.assertEqual(self.global_server.captured[0]["authorization"], "Bearer global-literal-key")
        self.assertEqual(self.role_server.captured, [])

    def test_model_only_override_keeps_global_credential(self) -> None:
        config = self._config(enabled=True, roles=[AgentRoleConfig(agent_id="gap_analyst", model="other-model")])
        self._complete(config, "research_planning")
        self.assertEqual(len(self.global_server.captured), 1)
        self.assertEqual(self.global_server.captured[0]["authorization"], "Bearer global-literal-key")

    def test_resolve_role_llm_config_clears_literal_key_cross_origin(self) -> None:
        global_config = LLMConfig(base_url=self.global_base, api_key="global-literal-key", model="m")
        with mock.patch.dict(
            os.environ,
            {"ROLE_TEST_BASE_URL": self.role_base, "ROLE_TEST_API_KEY": "role-scoped-key"},
        ):
            bound = resolve_role_llm_config(
                global_config,
                base_url=self.role_base,
                base_url_env="ROLE_TEST_BASE_URL",
                api_key_env="ROLE_TEST_API_KEY",
            )
        self.assertEqual(bound.api_key, "")
        self.assertEqual(bound.base_url_env, "ROLE_TEST_BASE_URL")
        self.assertEqual(bound.api_key_env, "ROLE_TEST_API_KEY")
        self.assertEqual(bound.base_url, self.role_base)


class CredentialOriginPreflightTest(unittest.TestCase):
    def test_cross_origin_role_without_pair_fails_preflight(self) -> None:
        config = AgentConfig(
            llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="m"),
            multi_agent=MultiAgentConfig(
                enabled=True,
                roles=[AgentRoleConfig(agent_id="gap_analyst", base_url="http://127.0.0.1:10/v1")],
            ),
        )
        report = run_preflight("测试", config, ping_llm=False)
        failing = [check for check in report.checks if check.name == "multi_agent_credential_origin"]
        self.assertTrue(any(check.status == "fail" for check in failing))
        self.assertEqual(report.status, "fail")

    def test_paired_env_role_passes_preflight(self) -> None:
        config = AgentConfig(
            llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="m"),
            multi_agent=MultiAgentConfig(
                enabled=True,
                roles=[
                    AgentRoleConfig(
                        agent_id="gap_analyst",
                        base_url="http://127.0.0.1:10/v1",
                        base_url_env="ROLE_TEST_BASE_URL",
                        api_key_env="ROLE_TEST_API_KEY",
                    )
                ],
            ),
        )
        env = {"ROLE_TEST_BASE_URL": "http://127.0.0.1:10/v1", "ROLE_TEST_API_KEY": "k"}
        with mock.patch.dict(os.environ, env):
            report = run_preflight("测试", config, ping_llm=False)
        origin_checks = [check for check in report.checks if check.name == "multi_agent_credential_origin"]
        self.assertTrue(origin_checks)
        self.assertTrue(all(check.status == "pass" for check in origin_checks))

    def test_same_origin_role_passes_preflight(self) -> None:
        config = AgentConfig(
            llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="m"),
            multi_agent=MultiAgentConfig(
                enabled=True,
                roles=[AgentRoleConfig(agent_id="gap_analyst", base_url="http://127.0.0.1:9/v1")],
            ),
        )
        report = run_preflight("测试", config, ping_llm=False)
        origin_checks = [check for check in report.checks if check.name == "multi_agent_credential_origin"]
        self.assertTrue(all(check.status == "pass" for check in origin_checks))


class RollbackApprovalInvalidationTest(unittest.TestCase):
    """GATE-01: a promised reapproval must invalidate the approval file."""

    def _make_run(self, tmp: str) -> Path:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        (run_dir / "03-experiment-plan.json").write_text("{}", encoding="utf-8")
        (run_dir / "03-execution-approval.json").write_text(
            json.dumps({"approved": True, "plan_sha256": "old"}), encoding="utf-8"
        )
        (run_dir / "04-results.json").write_text("[]", encoding="utf-8")
        update_workflow_stage(run_dir, "回退审批测试", "experiments_completed")
        return run_dir

    def test_rollback_to_experiments_archives_execution_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = self._make_run(tmp)
            preview = build_rollback_preview(run_dir, "experiments")
            self.assertTrue(preview["execution_reapproval_required"])
            self.assertIn("03-execution-approval.json", preview["artifacts_to_archive"])
            self.assertEqual(preview["blockers"], [])

            issued = issue_rollback_preview(run_dir, "experiments")
            report = apply_rollback(run_dir, "experiments", issued["preview_id"], issued["preview_token"])
            self.assertEqual(report["status"], "applied")
            self.assertFalse((run_dir / "03-execution-approval.json").exists())
            archived = (
                run_dir.parent / ".research-agent-archives" / run_dir.name / report["archive_ref"] / "03-execution-approval.json"
            )
            self.assertTrue(archived.exists())

    def test_rollback_to_literature_context_archives_review_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "01-context.json").write_text("{}", encoding="utf-8")
            (run_dir / "approval.json").write_text(json.dumps({"approved": True}), encoding="utf-8")
            update_workflow_stage(run_dir, "回退审批测试", "awaiting_review_approval")
            preview = build_rollback_preview(run_dir, "literature_context")
            self.assertTrue(preview["review_reapproval_required"])
            self.assertIn("approval.json", preview["artifacts_to_archive"])
            self.assertEqual(preview["blockers"], [])

    def test_invariant_blocks_when_approval_not_in_archive_plan(self) -> None:
        import research_agent.workflow_graph as wg

        with TemporaryDirectory() as tmp:
            run_dir = self._make_run(tmp)
            original = wg._rollback_patterns_and_directories

            def broken_patterns(target: str) -> tuple[list[str], list[str]]:
                patterns, directories = original(target)
                return [p for p in patterns if not p.startswith("03-execution-approval")], directories

            with mock.patch.object(wg, "_rollback_patterns_and_directories", broken_patterns):
                preview = build_rollback_preview(run_dir, "experiments")
            self.assertTrue(
                any("03-execution-approval.json" in blocker for blocker in preview["blockers"]),
                preview["blockers"],
            )


class WebRolePatchRoundTripTest(unittest.TestCase):
    """WEB-02: a partial web patch must keep the role's endpoint binding."""

    def test_partial_patch_preserves_endpoint_fields(self) -> None:
        import research_agent.web_server as web_server

        current = MultiAgentConfig(
            enabled=True,
            roles=[
                AgentRoleConfig(
                    agent_id="gap_analyst",
                    model="model-a",
                    base_url="http://127.0.0.1:10/v1",
                    base_url_env="ROLE_BASE_URL",
                    api_key_env="ROLE_API_KEY",
                    skills=["evidence-grounding"],
                )
            ],
        )
        patched = web_server._multi_agent_config_from_payload({"agent_models": {"gap_analyst": "model-a2"}}, current)
        role = patched.roles[0]
        self.assertEqual(role.model, "model-a2")
        self.assertEqual(role.base_url, "http://127.0.0.1:10/v1")
        self.assertEqual(role.base_url_env, "ROLE_BASE_URL")
        self.assertEqual(role.api_key_env, "ROLE_API_KEY")
        self.assertEqual(role.skills, ["evidence-grounding"])
        self.assertTrue(role.enabled)


class DocTomlFixtureTest(unittest.TestCase):
    """DOC-01: every TOML snippet in the docs must parse as a real config."""

    @staticmethod
    def _toml_blocks(text: str) -> list[str]:
        blocks = re.findall(r"```toml\n(.*?)```", text, re.DOTALL)
        return [block for block in blocks if "multi_agent" in block]

    def test_readme_multi_agent_toml_parses(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        blocks = self._toml_blocks(readme)
        self.assertTrue(blocks, "README must contain a multi_agent TOML example")
        for index, block in enumerate(blocks):
            with TemporaryDirectory() as tmp:
                path = Path(tmp) / f"readme-block-{index}.toml"
                path.write_text(block, encoding="utf-8")
                config = load_config(path)
            self.assertTrue(config.multi_agent.enabled)
            self.assertTrue(config.multi_agent.roles)
            for role in config.multi_agent.roles:
                self.assertTrue(role.agent_id)

    def test_examples_config_parses(self) -> None:
        config = load_config(PROJECT_ROOT / "examples" / "config.toml")
        self.assertFalse(config.multi_agent.enabled)

    def test_examples_multi_agent_section_parses_when_enabled(self) -> None:
        text = (PROJECT_ROOT / "examples" / "config.toml").read_text(encoding="utf-8")
        lines = text.splitlines()
        start = lines.index("[multi_agent]")
        toml_shape = re.compile(r"^# (\[\[?[^\]]+\]\]?|\w[\w_]*\s*=.*)$")
        activated_lines: list[str] = []
        for line in lines[start:]:
            stripped = line.strip()
            if stripped.startswith("#"):
                match = toml_shape.match(stripped)
                if match:
                    activated_lines.append(match.group(1))
            else:
                activated_lines.append(line)
        # The shipped example keeps multi_agent disabled; flip it on to prove
        # the documented role/server syntax is valid for the real parser.
        activated = "\n".join(activated_lines).replace("enabled = false", "enabled = true", 1)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "activated.toml"
            path.write_text(activated, encoding="utf-8")
            config = load_config(path)
        self.assertTrue(config.multi_agent.enabled)
        role_ids = {role.agent_id for role in config.multi_agent.roles}
        self.assertIn("gap_analyst", role_ids)
        self.assertIn("skeptical_reviewer", role_ids)
        self.assertTrue(config.multi_agent.mcp_servers)


if __name__ == "__main__":
    unittest.main()
