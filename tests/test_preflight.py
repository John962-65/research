from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from threading import Thread
from unittest.mock import patch
import json
import os
import subprocess
import sys
import unittest
import urllib.error

from pathlib import Path
from tempfile import TemporaryDirectory

from research_agent.artifacts import write_json
from research_agent.config import AgentConfig, ExecutionConfig, HumanConfig, LiteratureConfig, LLMConfig, PaperGradeConfig, ReleaseConfig, load_config
from research_agent.preflight import _llm_ping_check, render_preflight_markdown, run_preflight, write_preflight_artifacts
from research_agent.run_memory import build_run_memory
from research_agent.web_server import _config_from_payload


ROOT = Path(__file__).resolve().parents[1]


class PreflightTest(unittest.TestCase):
    def test_missing_model_fails_static_preflight(self) -> None:
        report = run_preflight("机械臂路径规划", AgentConfig(), ping_llm=False)

        self.assertEqual(report.status, "fail")
        self.assertTrue(any(check.name == "llm_model" and check.status == "fail" for check in report.checks))
        self.assertIn("模型名缺失", render_preflight_markdown(report))

    def test_write_preflight_artifacts_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = run_preflight("机械臂路径规划", AgentConfig(), ping_llm=False)

            json_path, md_path = write_preflight_artifacts(report, run_dir)

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "fail")
            self.assertIn("预检报告", md_path.read_text(encoding="utf-8"))

    def test_local_openai_compatible_ping_passes(self) -> None:
        _FakeOpenAIHandler.last_payload = None
        server = HTTPServer(("127.0.0.1", 0), _FakeOpenAIHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = AgentConfig(
                llm=LLMConfig(
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="fake-model",
                    api_key="test-key",
                ),
                release=_complete_release_config(),
            )
            report = run_preflight("自动科研 agent", config, ping_llm=True, llm_timeout_seconds=2)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        self.assertNotEqual(report.status, "fail")
        self.assertTrue(any(check.name == "llm_ping" and check.status == "pass" for check in report.checks))
        self.assertEqual(set(_FakeOpenAIHandler.last_payload or {}), {"model", "messages"})
        self.assertEqual((_FakeOpenAIHandler.last_payload or {})["messages"][0]["role"], "user")

    def test_llm_ping_retries_temporary_429(self) -> None:
        rate_limit_error = urllib.error.HTTPError(
            "http://local.test/v1/chat/completions",
            429,
            "Too Many Requests",
            hdrs={"Retry-After": "0"},
            fp=BytesIO(b'{"error":{"message":"Concurrency limit exceeded"}}'),
        )
        response = _FakeResponse(b'{"choices":[{"message":{"content":"OK"}}]}')
        config = AgentConfig(llm=LLMConfig(base_url="http://local.test/v1", model="model", api_key="secret"))

        with patch.dict(os.environ, {"OPENAI_PING_MAX_ATTEMPTS": "2"}), patch(
            "research_agent.llm._open_url", side_effect=[rate_limit_error, response]
        ), patch("research_agent.llm.random.uniform", return_value=0.1), patch(
            "research_agent.preflight.time.sleep"
        ) as sleep:
            check = _llm_ping_check(config, timeout_seconds=2)

        self.assertEqual(check.status, "pass")
        sleep.assert_called_once_with(0.1)

    def test_llm_ping_explains_persistent_concurrency_429(self) -> None:
        rate_limit_error = urllib.error.HTTPError(
            "http://local.test/v1/chat/completions",
            429,
            "Too Many Requests",
            hdrs={},
            fp=BytesIO(b'{"error":{"message":"Concurrency limit exceeded for user"}}'),
        )
        config = AgentConfig(llm=LLMConfig(base_url="http://local.test/v1", model="model", api_key="secret"))

        with patch.dict(os.environ, {"OPENAI_PING_MAX_ATTEMPTS": "1"}), patch(
            "research_agent.llm._open_url", side_effect=rate_limit_error
        ):
            check = _llm_ping_check(config, timeout_seconds=2)

        self.assertEqual(check.status, "fail")
        self.assertIn("并发槽", check.action)
        self.assertNotIn("secret", f"{check.detail} {check.action}")

    def test_cli_module_preflight_runs_main(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "preflight", "--topic", "机械臂路径规划", "--no-llm-ping"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("预检报告", completed.stdout)
        self.assertIn("模型名缺失", completed.stdout)

    def test_cli_preflight_accepts_paper_grade_flag(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "preflight", "--topic", "机械臂路径规划", "--no-llm-ping", "--paper-grade"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("paper-grade", completed.stdout)
        self.assertIn("paper_grade_literature_provider", completed.stdout)

    def test_non_paper_grade_local_gateway_missing_api_key_is_warn(self) -> None:
        report = run_preflight(
            "本地网关烟测",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5"),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        checks = {check.name: check for check in report.checks}

        self.assertEqual(report.status, "warn")
        self.assertEqual(checks["llm_api_key"].status, "warn")
        self.assertIn("API key 未配置", checks["llm_api_key"].summary)

    def test_paper_grade_local_gateway_missing_api_key_fails_before_ping(self) -> None:
        report = run_preflight(
            "本地网关正式 run",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5"),
                paper_grade=PaperGradeConfig(enabled=True),
                release=_complete_release_config(),
            ),
            ping_llm=True,
        )
        checks = {check.name: check for check in report.checks}
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["llm_api_key"].status, "fail")
        self.assertIn("paper-grade run 缺少 API key", checks["llm_api_key"].summary)
        self.assertIn("OPENAI_API_KEY", checks["llm_api_key"].action)
        self.assertEqual(checks["llm_ping"].status, "skipped")
        self.assertIn("缺少 API key", checks["llm_ping"].summary)
        self.assertNotIn("sk-", rendered)

    def test_paper_grade_requires_explicit_base_url_before_ping(self) -> None:
        report = run_preflight(
            "本地网关正式 run",
            AgentConfig(
                llm=LLMConfig(model="gpt-5.5", api_key="test-key"),
                paper_grade=PaperGradeConfig(enabled=True),
                release=_complete_release_config(),
            ),
            ping_llm=True,
        )
        checks = {check.name: check for check in report.checks}
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["llm_base_url"].status, "fail")
        self.assertIn("paper-grade run 缺少显式 Base URL", checks["llm_base_url"].summary)
        self.assertIn("OPENAI_BASE_URL", checks["llm_base_url"].action)
        self.assertEqual(checks["llm_ping"].status, "skipped")
        self.assertIn("缺少显式 Base URL", checks["llm_ping"].summary)
        self.assertNotIn("test-key", rendered)

    def test_paper_grade_rejects_placeholder_api_key(self) -> None:
        report = run_preflight(
            "本地网关正式 run",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="replace-for-real-run"),
                paper_grade=PaperGradeConfig(enabled=True),
                release=_complete_release_config(),
            ),
            ping_llm=True,
        )
        checks = {check.name: check for check in report.checks}
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["llm_api_key"].status, "fail")
        self.assertIn("占位值", checks["llm_api_key"].summary)
        self.assertEqual(checks["llm_ping"].status, "skipped")
        self.assertIn("占位值", checks["llm_ping"].summary)
        self.assertNotIn("replace-for-real-run", rendered)

    def test_paper_grade_rejects_placeholder_literature_api_keys(self) -> None:
        report = run_preflight(
            "本地网关正式 run",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="test-key"),
                literature=LiteratureConfig(
                    provider="online",
                    sources=["semantic_scholar", "openalex", "arxiv"],
                    semantic_scholar_api_key="replace-me",
                    openalex_api_key="<api-key>",
                    contact_email="researcher@university.edu",
                ),
                paper_grade=PaperGradeConfig(enabled=True),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        checks = {check.name: check for check in report.checks}
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["semantic_scholar_key"].status, "fail")
        self.assertEqual(checks["openalex_key"].status, "fail")
        self.assertIn("占位值", checks["semantic_scholar_key"].summary)
        self.assertIn("占位值", checks["openalex_key"].summary)
        self.assertNotIn("replace-me", rendered)
        self.assertNotIn("<api-key>", rendered)

    def test_paper_grade_rejects_placeholder_contact_email_without_printing_value(self) -> None:
        report = run_preflight(
            "本地网关正式 run",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="test-key"),
                literature=LiteratureConfig(provider="online", sources=["openalex", "crossref", "arxiv"], contact_email="agent@example.org"),
                paper_grade=PaperGradeConfig(enabled=True),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        checks = {check.name: check for check in report.checks}
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["contact_email"].status, "fail")
        self.assertIn("联系邮箱", checks["contact_email"].summary)
        self.assertIn("RESEARCH_AGENT_CONTACT_EMAIL", checks["contact_email"].action)
        self.assertNotIn("agent@example.org", rendered)

    def test_paper_grade_requires_contact_email_for_email_based_sources(self) -> None:
        report = run_preflight(
            "本地网关正式 run",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="test-key"),
                literature=LiteratureConfig(provider="online", sources=["openalex", "crossref", "arxiv"]),
                paper_grade=PaperGradeConfig(enabled=True),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        checks = {check.name: check for check in report.checks}

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["contact_email"].status, "fail")
        self.assertIn("缺少文献源联系邮箱", checks["contact_email"].summary)
        self.assertIn("RESEARCH_AGENT_CONTACT_EMAIL", checks["contact_email"].action)

    def test_non_paper_grade_warns_on_placeholder_literature_credentials(self) -> None:
        report = run_preflight(
            "本地网关试跑",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="test-key"),
                literature=LiteratureConfig(
                    provider="online",
                    sources=["semantic_scholar", "openalex", "crossref"],
                    semantic_scholar_api_key="<api-key>",
                    openalex_api_key="replace-me",
                    contact_email="agent@example.org",
                ),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        checks = {check.name: check for check in report.checks}
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "warn")
        self.assertEqual(checks["semantic_scholar_key"].status, "warn")
        self.assertEqual(checks["openalex_key"].status, "warn")
        self.assertEqual(checks["contact_email"].status, "warn")
        self.assertIn("将不会发送给文献源", checks["semantic_scholar_key"].summary)
        self.assertIn("将不会发送给文献源", checks["openalex_key"].summary)
        self.assertIn("将不会发送给文献源", checks["contact_email"].summary)
        self.assertNotIn("<api-key>", rendered)
        self.assertNotIn("replace-me", rendered)
        self.assertNotIn("agent@example.org", rendered)

    def test_web_payload_config_can_preflight_without_ping(self) -> None:
        config = _config_from_payload(
            {
                "topic": "机械臂路径规划",
                "llm_provider": "openai-compatible",
                "llm_model": "fake-model",
                "llm_base_url": "http://127.0.0.1:9/v1",
                "llm_max_calls": 12,
                "llm_max_prompt_chars": 50000,
                "llm_input_cost_per_million_tokens": 2.0,
                "llm_output_cost_per_million_tokens": 10.0,
                "literature_provider": "online",
                "literature_sources": "semantic_scholar, openalex, crossref",
                "semantic_scholar_api_key": "s2-secret",
                "openalex_api_key": "oa-secret",
                "literature_contact_email": "lab@university.edu",
                "fulltext_paths": "benchmarks/uci-iris-classification/fulltext/iris.names.txt",
            }
        )
        self.assertEqual(config.llm.max_calls, 12)
        self.assertEqual(config.llm.max_prompt_chars, 50000)
        self.assertEqual(config.llm.input_cost_per_million_tokens, 2.0)
        self.assertEqual(config.llm.output_cost_per_million_tokens, 10.0)
        self.assertEqual(config.literature.semantic_scholar_api_key, "s2-secret")
        self.assertEqual(config.literature.openalex_api_key, "oa-secret")
        self.assertEqual(config.literature.contact_email, "lab@university.edu")
        self.assertEqual(config.literature.fulltext_paths, ["benchmarks/uci-iris-classification/fulltext/iris.names.txt"])
        report = run_preflight("机械臂路径规划", config, ping_llm=False)
        encoded = json.dumps({"report": _report_dict(report), "markdown": render_preflight_markdown(report)}, ensure_ascii=False)

        self.assertIn("机械臂路径规划", encoded)
        self.assertIn("llm_ping", encoded)
        self.assertTrue(any(check.name == "semantic_scholar_key" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "openalex_key" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "contact_email" and check.status == "pass" for check in report.checks))
        self.assertNotIn("s2-secret", encoded)
        self.assertNotIn("oa-secret", encoded)

    def test_llm_budget_fields_are_validated(self) -> None:
        bad = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(
                    base_url="http://127.0.0.1:9/v1",
                    model="fake-model",
                    api_key="test-key",
                    max_calls=-1,
                    max_prompt_chars=-5,
                    input_cost_per_million_tokens=-1,
                ),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        self.assertEqual(bad.status, "fail")
        self.assertTrue(any(check.name == "llm_max_calls" and check.status == "fail" for check in bad.checks))
        self.assertTrue(any(check.name == "llm_max_prompt_chars" and check.status == "fail" for check in bad.checks))
        self.assertTrue(any(check.name == "llm_token_cost" and check.status == "fail" for check in bad.checks))

        good = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(
                    base_url="http://127.0.0.1:9/v1",
                    model="fake-model",
                    api_key="test-key",
                    max_calls=10,
                    max_prompt_chars=100000,
                    input_cost_per_million_tokens=2.0,
                    output_cost_per_million_tokens=10.0,
                ),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        self.assertEqual(good.status, "pass")
        self.assertTrue(any(check.name == "llm_max_calls" and check.status == "pass" for check in good.checks))
        self.assertTrue(any(check.name == "llm_max_prompt_chars" and check.status == "pass" for check in good.checks))
        self.assertTrue(any(check.name == "llm_token_cost" and check.status == "pass" for check in good.checks))

    def test_fulltext_paths_are_validated(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.txt"
            path.write_text("Local fulltext.", encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_AGENT_FULLTEXT_ROOTS": tmp}):
                report = run_preflight(
                    "机械臂路径规划",
                    AgentConfig(literature=LiteratureConfig(fulltext_paths=[str(path)])),
                    ping_llm=False,
                )

            self.assertTrue(any(check.name == "fulltext_paths" and check.status == "pass" for check in report.checks))

        missing = run_preflight(
            "机械臂路径规划",
            AgentConfig(literature=LiteratureConfig(fulltext_paths=["/missing/paper.txt"])),
            ping_llm=False,
        )
        self.assertTrue(any(check.name == "fulltext_paths" and check.status == "fail" for check in missing.checks))

    def test_seed_paper_quality_prefers_doi_or_url_entries(self) -> None:
        report = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                literature=LiteratureConfig(
                    provider="online",
                    seed_papers=[
                        "RRT star manipulator benchmark",
                        "10.1109/MRA.2012.2205651",
                        "https://doi.org/10.1177/0278364911406761",
                    ],
                ),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )

        self.assertTrue(any(check.name == "seed_metadata" and check.status == "pass" for check in report.checks))
        quality = next(check for check in report.checks if check.name == "seed_papers_quality")
        self.assertEqual(quality.status, "warn")
        self.assertIn("2/3", quality.detail)
        role = next(check for check in report.checks if check.name == "seed_role_coverage")
        self.assertEqual(role.status, "warn")
        self.assertIn("benchmark_dataset=1", role.detail)

    def test_seed_role_coverage_passes_with_balanced_seed_roles(self) -> None:
        report = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                literature=LiteratureConfig(
                    provider="online",
                    seed_papers=[
                        "10.1000/review survey review robot manipulator planning 2024",
                        "10.1001/benchmark benchmark dataset OMPL motion planning 2023",
                        "https://doi.org/10.1002/baseline RRT baseline method planner 2022",
                    ],
                ),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )

        role = next(check for check in report.checks if check.name == "seed_role_coverage")
        self.assertEqual(role.status, "pass")
        self.assertIn("review=1", role.detail)
        self.assertIn("benchmark_dataset=1", role.detail)
        self.assertIn("baseline_method=3", role.detail)
        self.assertIn("recent=3", role.detail)

    def test_max_search_queries_is_validated(self) -> None:
        bad = run_preflight(
            "机械臂路径规划",
            AgentConfig(literature=LiteratureConfig(max_search_queries=0)),
            ping_llm=False,
        )
        self.assertTrue(any(check.name == "max_search_queries" and check.status == "fail" for check in bad.checks))

        good = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                literature=LiteratureConfig(max_search_queries=6),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        self.assertEqual(good.status, "pass")
        self.assertTrue(any(check.name == "max_search_queries" and check.status == "pass" for check in good.checks))

    def test_benchmark_manifest_paths_are_validated(self) -> None:
        missing = run_preflight(
            "机械臂路径规划",
            AgentConfig(execution=ExecutionConfig(mode="benchmark", allowed_commands=["python3"])),
            ping_llm=False,
        )
        self.assertTrue(any(check.name == "benchmark_manifests" and check.status == "fail" for check in missing.checks))

        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            script = Path(tmp) / "run.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text('{"name": "toy", "command": ["python3", "run.py"]}', encoding="utf-8")
            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(execution=ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)])),
                ping_llm=False,
            )

            self.assertTrue(any(check.name == "benchmark_manifests" and check.status == "pass" for check in report.checks))
            self.assertTrue(any(check.name == "benchmark_adapter_audit" and check.status == "pass" for check in report.checks))

    def test_benchmark_manifest_content_is_audited_in_preflight(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "Unsafe Benchmark",
                        "command": ["bash", "run.sh"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
            )

        self.assertEqual(report.status, "fail")
        self.assertTrue(any(check.name == "benchmark_adapter_audit" and check.status == "fail" for check in report.checks))
        self.assertIn("benchmark manifest 内容审计未通过", render_preflight_markdown(report))

    def test_paper_grade_preflight_blocks_incomplete_startup_config(self) -> None:
        report = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                literature=LiteratureConfig(provider="offline", sources=["crossref"], seed_papers=["Robot manipulator benchmark"]),
                execution=ExecutionConfig(mode="simulated", repeats=1),
                release=_complete_release_config(),
                paper_grade=PaperGradeConfig(enabled=True),
            ),
            ping_llm=False,
        )
        rendered = render_preflight_markdown(report)

        self.assertEqual(report.status, "fail")
        self.assertTrue(any(check.name == "paper_grade_mode" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "paper_grade_literature_provider" and check.status == "fail" for check in report.checks))
        self.assertTrue(any(check.name == "paper_grade_seed_papers" and check.status == "fail" for check in report.checks))
        self.assertTrue(any(check.name == "paper_grade_execution_mode" and check.status == "fail" for check in report.checks))
        self.assertTrue(any(check.name == "paper_grade_benchmark_manifests" and check.status == "fail" for check in report.checks))
        self.assertIn("paper-grade", rendered)

    def test_paper_grade_config_file_enables_startup_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                """
[llm]
model = "fake-model"
api_key = "test-key"

[release]
code_repository_url = "https://github.com/example/repo"
code_license = "MIT"
data_access_statement = "No external dataset."

[paper_grade]
enabled = true
""",
                encoding="utf-8",
            )
            config = load_config(path)

        report = run_preflight("机械臂路径规划", config, ping_llm=False)

        self.assertTrue(config.paper_grade.enabled)
        self.assertEqual(report.status, "fail")
        self.assertTrue(any(check.name == "paper_grade_literature_provider" and check.status == "fail" for check in report.checks))

    def test_paper_grade_preflight_reports_configured_thresholds(self) -> None:
        report = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                literature=LiteratureConfig(
                    provider="online",
                    sources=["semantic_scholar", "openalex", "crossref"],
                    seed_papers=[
                        "10.1000/review survey review robot planning",
                        "10.1001/benchmark dataset benchmark robot planning",
                        "10.1002/baseline method baseline robot planning",
                    ],
                ),
                execution=ExecutionConfig(mode="benchmark", repeats=3),
                paper_grade=PaperGradeConfig(
                    enabled=True,
                    min_literature_sources=4,
                    min_seed_papers=4,
                    min_doi_url_seed_papers=4,
                    min_curated_seed_roles=4,
                    min_execution_repeats=5,
                ),
            ),
            ping_llm=False,
        )
        checks = {item.name: item for item in report.checks}

        self.assertEqual(checks["paper_grade_literature_sources"].status, "fail")
        self.assertIn("4 个", checks["paper_grade_literature_sources"].summary)
        self.assertIn("3/4", checks["paper_grade_literature_sources"].detail)
        self.assertEqual(checks["paper_grade_seed_papers"].status, "fail")
        self.assertIn("4 条", checks["paper_grade_seed_papers"].summary)
        self.assertIn("strong=3/4; total=3/4", checks["paper_grade_seed_papers"].detail)
        self.assertEqual(checks["paper_grade_seed_roles"].status, "fail")
        self.assertIn("4 类", checks["paper_grade_seed_roles"].summary)
        self.assertEqual(checks["paper_grade_execution_repeats"].status, "fail")
        self.assertIn("repeats >= 5", checks["paper_grade_execution_repeats"].summary)

    def test_paper_grade_preflight_passes_with_online_seed_and_manifest_set(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            manifests: list[str] = []
            for role in ["candidate", "baseline", "ablation"]:
                script = root / f"run_{role}.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                manifest = root / f"{role}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": f"{role} adapter",
                            "role": role,
                            "command": ["python3", script.name],
                            "source_files": [script.name],
                            "metrics_path": f"{role}_metrics.json",
                            "expected_artifacts": [f"{role}_metrics.json"],
                            "expected_metrics": ["success_rate", "runtime"],
                            "metric_schema": {
                                "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                                "runtime": {"direction": "lower_is_better", "unit": "seconds", "description": "Runtime."},
                            },
                            "benchmark_kind": "external",
                            "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_version": "ompl-1.6.0",
                            "split_name": f"official-{role}-split",
                            "split_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                            "license": "BSD-3-Clause",
                            "baseline": "control",
                            "baseline_version": f"test-{role}-v1",
                            "citation": "10.1109/MRA.2012.2205651",
                            "grader_version": f"grader-{role}-v1",
                            "grader_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
                            "min_repeats": 3,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))
            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        sources=["semantic_scholar", "openalex", "crossref"],
                        max_papers=12,
                        max_search_queries=6,
                        semantic_scholar_api_key="s2-key",
                        contact_email="lab@university.edu",
                        seed_papers=[
                            "10.1000/review survey review robot manipulator planning 2024",
                            "10.1001/benchmark benchmark dataset OMPL motion planning 2023",
                            "https://doi.org/10.1002/baseline RRT baseline method planner 2022",
                        ],
                    ),
                    execution=ExecutionConfig(mode="benchmark", repeats=3, allowed_commands=["python3"], benchmark_manifest_paths=manifests),
                    release=_complete_release_config(),
                    paper_grade=PaperGradeConfig(enabled=True),
                ),
                ping_llm=False,
            )

        self.assertNotEqual(report.status, "fail")
        self.assertTrue(any(check.name == "paper_grade_literature_provider" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "paper_grade_seed_papers" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "paper_grade_benchmark_manifests" and check.status == "pass" for check in report.checks))

    def test_paper_grade_preflight_rejects_procedural_fixture_manifest_set(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            manifests: list[str] = []
            for role in ["candidate", "baseline", "ablation"]:
                script = root / f"run_{role}.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                manifest = root / f"{role}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": f"{role} adapter",
                            "role": role,
                            "command": ["python3", script.name],
                            "source_files": [script.name],
                            "metrics_path": f"{role}_metrics.json",
                            "expected_artifacts": [f"{role}_metrics.json"],
                            "expected_metrics": ["success_rate", "runtime"],
                            "benchmark_kind": "fixture",
                            "benchmark_url": "https://lavalle.pl/rrtpubs.html",
                            "dataset_url": f"procedural://test-paper-grade/{role}",
                            "license": "MIT for generated test fixture",
                            "baseline": "control",
                            "baseline_version": f"test-{role}-v1",
                            "citation": "LaValle, S.M. (1998). Rapidly-exploring random trees: a new tool for path planning. TR 98-11. https://lavalle.pl/rrtpubs.html",
                            "min_repeats": 3,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))

            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        sources=["semantic_scholar", "openalex", "crossref"],
                        max_papers=12,
                        max_search_queries=6,
                        seed_papers=[
                            "10.1000/review survey review robot manipulator planning 2024",
                            "10.1001/benchmark benchmark dataset OMPL motion planning 2023",
                            "https://doi.org/10.1002/baseline RRT baseline method planner 2022",
                        ],
                    ),
                    execution=ExecutionConfig(mode="benchmark", repeats=3, allowed_commands=["python3"], benchmark_manifest_paths=manifests),
                    paper_grade=PaperGradeConfig(enabled=True),
                ),
                ping_llm=False,
            )

        check = next(item for item in report.checks if item.name == "paper_grade_benchmark_manifests")
        self.assertEqual(report.status, "fail")
        self.assertEqual(check.status, "fail")
        self.assertIn("benchmark_kind=fixture", check.detail)
        self.assertIn("procedural://", check.detail)

    def test_paper_grade_preflight_requires_manifest_provenance(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            manifests: list[str] = []
            for role in ["candidate", "baseline", "ablation"]:
                script = root / f"run_{role}.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                manifest = root / f"{role}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": f"{role} adapter",
                            "role": role,
                            "command": ["python3", script.name],
                            "source_files": [script.name],
                            "metrics_path": f"{role}_metrics.json",
                            "expected_artifacts": [f"{role}_metrics.json"],
                            "expected_metrics": ["success_rate", "runtime"],
                            "min_repeats": 3,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))

            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        sources=["semantic_scholar", "openalex", "crossref"],
                        max_papers=12,
                        max_search_queries=6,
                        seed_papers=[
                            "10.1000/review survey review robot manipulator planning 2024",
                            "10.1001/benchmark benchmark dataset OMPL motion planning 2023",
                            "https://doi.org/10.1002/baseline RRT baseline method planner 2022",
                        ],
                    ),
                    execution=ExecutionConfig(mode="benchmark", repeats=3, allowed_commands=["python3"], benchmark_manifest_paths=manifests),
                    paper_grade=PaperGradeConfig(enabled=True),
                ),
                ping_llm=False,
            )

        check = next(item for item in report.checks if item.name == "paper_grade_benchmark_manifests")
        self.assertEqual(report.status, "fail")
        self.assertEqual(check.status, "fail")
        self.assertIn("provenance", check.detail)

    def test_paper_grade_example_config_is_structural_fixture_not_formal_preflight(self) -> None:
        config = load_config(ROOT / "examples" / "paper-grade-config.toml")

        report = run_preflight("机械臂路径规划", config, ping_llm=False)
        checks = {check.name: check for check in report.checks}

        self.assertEqual(report.status, "fail")
        self.assertEqual(checks["paper_grade_mode"].status, "pass")
        self.assertEqual(checks["paper_grade_literature_provider"].status, "pass")
        self.assertEqual(checks["paper_grade_literature_sources"].status, "pass")
        self.assertEqual(checks["paper_grade_seed_papers"].status, "pass")
        self.assertEqual(checks["paper_grade_seed_roles"].status, "pass")
        self.assertEqual(checks["paper_grade_execution_mode"].status, "pass")
        self.assertEqual(checks["paper_grade_execution_repeats"].status, "pass")
        self.assertEqual(checks["paper_grade_benchmark_manifests"].status, "fail")
        self.assertIn("fixture", checks["paper_grade_benchmark_manifests"].detail)

    def test_uci_iris_paper_grade_config_uses_formal_external_manifest_set(self) -> None:
        config = load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")

        report = run_preflight("Iris classification benchmark smoke", config, ping_llm=False)
        checks = {check.name: check for check in report.checks}

        self.assertEqual(config.llm.base_url, "")
        self.assertEqual(config.llm.model, "")
        self.assertEqual(config.llm.api_key, "")
        self.assertEqual(config.llm.base_url_env, "OPENAI_BASE_URL")
        self.assertEqual(config.llm.model_env, "OPENAI_MODEL")
        self.assertEqual(config.llm.api_key_env, "OPENAI_API_KEY")
        self.assertEqual(checks["paper_grade_mode"].status, "pass")
        self.assertEqual(checks["paper_grade_seed_roles"].status, "pass")
        self.assertEqual(checks["paper_grade_execution_mode"].status, "pass")
        self.assertEqual(checks["paper_grade_execution_repeats"].status, "pass")
        self.assertEqual(checks["paper_grade_benchmark_manifests"].status, "pass")
        self.assertIn("roles=ablation,baseline,candidate", checks["paper_grade_benchmark_manifests"].detail)

    def test_release_metadata_fields_are_validated(self) -> None:
        bad = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                release=ReleaseConfig(
                    code_repository_url="github.com/example/repo",
                    code_archive_doi="not-a-doi",
                    data_repository_url="zenodo.org/records/1",
                    environment_url="docker-image",
                ),
            ),
            ping_llm=False,
        )
        self.assertEqual(bad.status, "fail")
        self.assertTrue(any(check.name == "release_code_repository_url" and check.status == "fail" for check in bad.checks))
        self.assertTrue(any(check.name == "release_code_archive_doi" and check.status == "fail" for check in bad.checks))
        self.assertTrue(any(check.name == "release_environment_url" and check.status == "fail" for check in bad.checks))

        good = run_preflight(
            "机械臂路径规划",
            AgentConfig(
                llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                release=_complete_release_config(),
            ),
            ping_llm=False,
        )
        self.assertEqual(good.status, "pass")
        self.assertTrue(any(check.name == "release_metadata" and check.status == "pass" for check in good.checks))

    def test_run_memory_warnings_are_added_to_preflight(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            thin = runs_dir / "thin-run"
            simulated = runs_dir / "simulated-run"
            thin.mkdir(parents=True)
            simulated.mkdir(parents=True)
            write_json(thin / "state.json", {"topic": "薄文献", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(thin / "01-literature-quality.json", {"selected_papers": 1, "total_papers": 2})
            write_json(
                thin / "01-literature-rescue-plan.json",
                {"status": "needs_rescue_search", "rescue_queries": [{"query": "robot arm benchmark"}]},
            )
            write_json(simulated / "state.json", {"topic": "模拟实验", "stage": "completed", "updated_at": "2026-06-08T11:00:00+00:00"})
            write_json(simulated / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(simulated / "04-experiment-runbook.json", {"execution": {"mode": "simulated"}})
            memory = build_run_memory(runs_dir)

            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="offline", max_papers=8),
                    execution=ExecutionConfig(mode="simulated", repeats=3),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertEqual(report.status, "warn")
        self.assertTrue(any(check.name == "run_memory_status" and check.status == "warn" for check in report.checks))
        self.assertTrue(any(check.name == "memory_literature_provider" and check.status == "warn" for check in report.checks))
        self.assertTrue(any(check.name == "memory_seed_papers" and check.status == "warn" for check in report.checks))
        self.assertTrue(any(check.name == "memory_execution_mode" and check.status == "warn" for check in report.checks))
        self.assertIn("历史 run 存在可继承风险", render_preflight_markdown(report))

    def test_run_memory_checks_can_pass_when_current_config_addresses_history(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "thin-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "薄文献", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 1, "total_papers": 2})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "simulated"}})
            memory = build_run_memory(runs_dir)

            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        seed_papers=[
                            "10.1000/example review survey robot planning 2024",
                            "10.1001/example benchmark dataset motion planning 2023",
                            "https://doi.org/10.1002/example RRT baseline method planner 2022",
                        ],
                    ),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_literature_provider" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "memory_seed_papers" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "memory_seed_role_coverage" and check.status == "pass" for check in report.checks))
        self.assertTrue(any(check.name == "memory_execution_mode" and check.status == "pass" for check in report.checks))

    def test_run_memory_requires_seed_role_coverage_for_thin_evidence_history(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "thin-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "薄文献", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 1, "total_papers": 2})
            memory = build_run_memory(runs_dir)

            report = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        seed_papers=["10.1000/a", "10.1001/b", "https://doi.org/10.1002/c"],
                    ),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        role = next(check for check in report.checks if check.name == "memory_seed_role_coverage")
        self.assertEqual(role.status, "warn")
        self.assertIn("review=0", role.detail)

    def test_literature_source_health_memory_adds_preflight_repair_checks(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "source-health-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-source-health.json",
                {
                    "topic": "机械臂路径规划",
                    "total_sources": 3,
                    "rate_limited_sources": 1,
                    "failed_sources": 1,
                    "query_attempts": 6,
                    "query_successes": 0,
                    "query_failures": 2,
                    "query_rate_limits": 2,
                    "sources": [
                        {"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True},
                        {"source": "openalex", "status": "failed", "returned": 0, "errors": 2},
                        {"source": "crossref", "status": "ok", "returned": 0},
                    ],
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="online", max_papers=8, max_search_queries=4, sources=["semantic_scholar"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        max_search_queries=6,
                        sources=["semantic_scholar", "openalex", "arxiv", "crossref"],
                        semantic_scholar_api_key="ss-test-key",
                        contact_email="robot@university.edu",
                    ),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            placeholder = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        max_search_queries=6,
                        sources=["semantic_scholar", "openalex", "arxiv", "crossref"],
                        semantic_scholar_api_key="replace-me",
                        contact_email="robot@example.org",
                    ),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_source_health_sources" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_source_health_capacity" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_source_health_semantic_scholar_key" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_source_health_provider" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_source_health_sources" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_source_health_capacity" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_source_health_semantic_scholar_key" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_source_health_contact_email" and check.status == "pass" for check in ready.checks))
        rendered = render_preflight_markdown(ready)
        self.assertNotIn("ss-test-key", rendered)
        self.assertNotIn("robot@university.edu", rendered)
        placeholder_checks = {check.name: check for check in placeholder.checks}
        self.assertEqual(placeholder_checks["memory_source_health_semantic_scholar_key"].status, "warn")
        self.assertEqual(placeholder_checks["memory_source_health_contact_email"].status, "warn")
        rendered_placeholder = render_preflight_markdown(placeholder)
        self.assertNotIn("replace-me", rendered_placeholder)
        self.assertNotIn("robot@example.org", rendered_placeholder)

    def test_experiment_manager_memory_warnings_are_added_to_preflight(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            blocked = runs_dir / "manager-blocked"
            smoke = runs_dir / "manager-smoke"
            blocked.mkdir(parents=True)
            smoke.mkdir(parents=True)
            write_json(blocked / "state.json", {"topic": "分支阻断", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(blocked / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                blocked / "02-experiment-manager.json",
                {
                    "status": "block",
                    "manager_decision": "needs_human_reselection",
                    "execution_policy": "blocked",
                    "selected_idea_title": "证据不可核对分支",
                    "required_actions": ["选中分支的 idea audit 为 block；修正不可核对 citation/chunk 或人工改选。"],
                },
            )
            write_json(smoke / "state.json", {"topic": "高风险分支", "stage": "completed", "updated_at": "2026-06-08T11:00:00+00:00"})
            write_json(smoke / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                smoke / "02-experiment-manager.json",
                {
                    "status": "review_required",
                    "manager_decision": "proceed_with_cautions",
                    "execution_policy": "smoke_first",
                    "selected_idea_title": "高风险分支",
                    "planning_constraints": ["先规划低成本 smoke-first 实验；不要把 smoke 结果写成最终科学结论。"],
                    "next_expansion_candidates": [{"branch_id": "b3", "title": "替代分支"}],
                },
            )
            memory = build_run_memory(runs_dir)

            simulated = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="simulated", repeats=5),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            local = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertEqual(simulated.status, "warn")
        self.assertTrue(any(check.name == "memory_experiment_manager" and check.status == "warn" for check in simulated.checks))
        self.assertTrue(any(check.name == "memory_experiment_manager_smoke_first" and check.status == "warn" for check in simulated.checks))
        self.assertTrue(any(check.name == "memory_experiment_branch_backlog" and check.status == "skipped" for check in simulated.checks))
        self.assertTrue(any(check.name == "memory_experiment_manager_smoke_first" and check.status == "pass" for check in local.checks))
        self.assertIn("历史 run 存在实验管理阻断", render_preflight_markdown(simulated))

    def test_benchmark_schema_memory_guides_preflight_manifest_setup(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "schema-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Benchmark schema", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "04-benchmark-result-schema-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["benchmark result provenance 不完整：candidate: license, baseline_version, citation"],
                },
            )
            manifest = root / "manifest.json"
            manifest.write_text('{"name":"x","command":["python3","run.py"],"metrics_path":"metrics.json","expected_artifacts":["metrics.json"]}', encoding="utf-8")
            memory = build_run_memory(runs_dir)

            simulated = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="simulated", repeats=5),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            benchmark = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="benchmark", repeats=5, allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_benchmark_result_schema" and check.status == "warn" for check in simulated.checks))
        self.assertTrue(any(check.name == "memory_benchmark_result_schema" and check.status == "pass" for check in benchmark.checks))
        self.assertIn("benchmark result schema/provenance", render_preflight_markdown(simulated))

    def test_llm_trace_memory_guides_preflight_model_and_budget_setup(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "llm-trace-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "LLM trace", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-llm-trace-audit.json",
                {
                    "status": "block",
                    "coverage": {"required_stages": 7, "passed_required": 4},
                    "ledger_summary": {"total_calls": 5, "successful_calls": 4, "failed_calls": 1, "budget_exceeded_calls": 0},
                    "blocking_issues": ["paper_writing: 06-paper.md 已生成，但匹配到的成功 LLM 调用为 0/1。"],
                    "warnings": [],
                },
            )
            memory = build_run_memory(runs_dir)

            low_budget = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key", max_calls=3, max_prompt_chars=12000),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key", max_calls=12, max_prompt_chars=50000),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_llm_trace_config" and check.status == "pass" for check in low_budget.checks))
        self.assertTrue(any(check.name == "memory_llm_trace_budget" and check.status == "warn" for check in low_budget.checks))
        self.assertTrue(any(check.name == "memory_llm_trace_prompt_budget" and check.status == "warn" for check in low_budget.checks))
        self.assertTrue(any(check.name == "memory_llm_trace_budget" and check.status == "pass" for check in ready.checks))
        self.assertIn("LLM trace", render_preflight_markdown(low_budget))

    def test_run_economics_memory_guides_preflight_budget_and_cost_setup(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "economics-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Run economics", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-run-economics-audit.json",
                {
                    "status": "review_required",
                    "summary": {
                        "total_calls": 3,
                        "failed_calls": 0,
                        "budget_exceeded_calls": 0,
                        "input_tokens_estimated": 4500,
                        "output_tokens_estimated": 900,
                        "call_utilization": 1.0,
                        "prompt_utilization": 0.92,
                        "estimated_cost_usd": None,
                    },
                    "budget": {"call_utilization": 1.0, "prompt_utilization": 0.92},
                    "pricing": {"cost_estimation_enabled": False},
                    "blocking_issues": [],
                    "manual_tasks": ["只配置了部分 token 单价，美元成本不完整。"],
                    "warnings": ["LLM 使用接近配置预算上限：calls=1.00"],
                },
            )
            memory = build_run_memory(runs_dir)

            low_budget = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(
                        base_url="http://127.0.0.1:9/v1",
                        model="fake-model",
                        api_key="test-key",
                        max_calls=3,
                        max_prompt_chars=12000,
                        input_cost_per_million_tokens=2.0,
                    ),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(
                        base_url="http://127.0.0.1:9/v1",
                        model="fake-model",
                        api_key="test-key",
                        max_calls=12,
                        max_prompt_chars=50000,
                        input_cost_per_million_tokens=2.0,
                        output_cost_per_million_tokens=10.0,
                    ),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_run_economics_call_budget" and check.status == "warn" for check in low_budget.checks))
        self.assertTrue(any(check.name == "memory_run_economics_prompt_budget" and check.status == "warn" for check in low_budget.checks))
        self.assertTrue(any(check.name == "memory_run_economics_token_cost" and check.status == "warn" for check in low_budget.checks))
        self.assertTrue(any(check.name == "memory_run_economics_call_budget" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_run_economics_prompt_budget" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_run_economics_token_cost" and check.status == "pass" for check in ready.checks))
        self.assertIn("economics", render_preflight_markdown(low_budget))

    def test_agent_observability_memory_guides_preflight_trace_setup(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "observability-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Observability", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {
                    "status": "review_required",
                    "summary": {"manifest_events": 12, "manifest_artifacts": 4, "llm_failed_calls": 0, "repair_queue_status": "needs_repair"},
                    "blocking_issues": [],
                    "manual_tasks": ["LLM 预算压力接近上限：calls=0.90"],
                    "warnings": [],
                },
            )
            memory = build_run_memory(runs_dir)

            missing_release = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            configured = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_observability_llm" and check.status == "pass" for check in missing_release.checks))
        self.assertTrue(any(check.name == "memory_observability_execution_trace" and check.status == "pass" for check in missing_release.checks))
        self.assertTrue(any(check.name == "memory_observability_release_trace" and check.status == "warn" for check in missing_release.checks))
        self.assertTrue(any(check.name == "memory_observability_release_trace" and check.status == "pass" for check in configured.checks))
        self.assertIn("可观测性", render_preflight_markdown(missing_release))

    def test_agent_stage_contract_memory_guides_preflight_startup_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "stage-contract-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Stage contract", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-agent-stage-contract.json",
                {
                    "status": "needs_human_review",
                    "score": 0.78,
                    "checks": [
                        {"stage": "release_reproducibility", "status": "warn", "required_actions": ["补 release 元数据。"]},
                        {"stage": "experiment_design", "status": "warn", "required_actions": ["补 benchmark manifest。"]},
                    ],
                    "blocking_issues": [],
                    "manual_tasks": ["完成 code/data、投稿格式和 ZIP 上传前的人工待办。"],
                    "recommended_actions": ["完成人工待办后重新生成 13-agent-stage-contract。"],
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="offline", max_papers=8),
                    execution=ExecutionConfig(mode="simulated", repeats=5),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="online", max_papers=12, seed_papers=["10.1000/example"]),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                    human=HumanConfig(constraints=["必须人工确认后才进入 idea/实验。"], success_criteria=["保留 stage contract 审计。"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_stage_contract_literature" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_human_brief" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_execution" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_release" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_literature" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_human_brief" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_execution" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_stage_contract_release" and check.status == "pass" for check in ready.checks))
        self.assertIn("stage contract", render_preflight_markdown(weak))

    def test_research_scorecard_memory_guides_preflight_targeted_iteration_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "scorecard-needs-iteration"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Scorecard", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-research-scorecard.json",
                {
                    "status": "needs_iteration",
                    "overall_score": 61.0,
                    "dimensions": [
                        {"category": "experiment_benchmark", "score": 30.0, "status": "manual_required"},
                        {"category": "reproducibility_release", "score": 45.0, "status": "manual_required"},
                    ],
                    "blocking_issues": [],
                    "manual_tasks": ["experiment_benchmark: 把模拟实验替换为 local 或 benchmark manifest 真实任务。"],
                    "next_actions": ["补 benchmark manifest。"],
                    "recommendation": "建议进入下一轮实验/修订。",
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="offline", max_papers=8),
                    execution=ExecutionConfig(mode="simulated", repeats=2),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="online", max_papers=12, seed_papers=["10.1000/example"]),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                    human=HumanConfig(constraints=["针对 scorecard 最低分维度做下一轮 targeted iteration。"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_scorecard_evidence" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_scorecard_experiment" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_scorecard_release" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_scorecard_human_work" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_scorecard_evidence" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_scorecard_experiment" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_scorecard_release" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_scorecard_human_work" and check.status == "pass" for check in ready.checks))
        self.assertIn("scorecard", render_preflight_markdown(weak))

    def test_run_integrity_memory_guides_preflight_auditability_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "integrity-warn"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Integrity", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "14-run-integrity-audit.json",
                {
                    "status": "warn",
                    "summary": {"checks": 7, "pass": 5, "warn": 2, "block": 0, "required_artifacts": 150},
                    "items": [
                        {"category": "manifest", "name": "events", "status": "warn", "evidence": "manifest events 偏少"},
                        {"category": "package", "name": "package_status", "status": "warn", "evidence": "submission package needs review"},
                    ],
                    "blocking_issues": [],
                    "warnings": ["manifest/events: manifest events 偏少"],
                    "recommended_actions": ["补齐 manifest events 和 submission package review。"],
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    literature=LiteratureConfig(provider="offline", max_papers=8),
                    execution=ExecutionConfig(mode="simulated", repeats=2, allowed_commands=[]),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="online", max_papers=12, seed_papers=["10.1000/example"]),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                    human=HumanConfig(constraints=["保留完整 run integrity audit 轨迹。"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_integrity_llm_trace" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_integrity_human_gate" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_integrity_execution_trace" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_integrity_release_package" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_integrity_literature_inputs" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_integrity_llm_trace" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_integrity_human_gate" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_integrity_execution_trace" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_integrity_release_package" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_integrity_literature_inputs" and check.status == "pass" for check in ready.checks))
        self.assertIn("integrity", render_preflight_markdown(weak))

    def test_repair_resolution_memory_guides_preflight_repair_resume_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-resolution-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Repair resolution", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "12-repair-resolution-audit.json",
                {
                    "status": "review_required",
                    "resolution_score": 0.75,
                    "applied": True,
                    "rerun_from": "paper_rewrite",
                    "queue_status": "needs_repair",
                    "remaining_items": [{"task_id": "R1", "severity": "high", "category": "submission"}],
                    "resolved_items": [{"task_id": "R2", "severity": "block", "category": "citation"}],
                    "new_items": [],
                    "blocking_issues": [],
                    "manual_tasks": ["11-submission-package.json/submission_packaging: 人工确认上传清单。"],
                    "required_actions": ["人工确认后再归档。"],
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="simulated", repeats=2, allowed_commands=[]),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3"]),
                    release=_complete_release_config(),
                    human=HumanConfig(success_criteria=["repair resolution 所有 high/block 项必须闭环。"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_repair_resolution_resume_mode" and check.status == "skipped" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_repair_resolution_human_brief" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_repair_resolution_execution" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_repair_resolution_release" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_repair_resolution_human_brief" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_repair_resolution_execution" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_repair_resolution_release" and check.status == "pass" for check in ready.checks))
        self.assertIn("repair-resume", render_preflight_markdown(weak))

    def test_literature_search_feedback_memory_guides_preflight_query_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "search-feedback-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-search-feedback.json",
                {
                    "status": "needs_search_revision",
                    "recommended_queries": [
                        {"query": "robot manipulator OMPL benchmark RRT* CHOMP", "priority": 96, "source": "coverage"}
                    ],
                    "seed_paper_targets": [{"category": "benchmark", "name": "OMPL", "hint": "补 DOI seed"}],
                    "retrieval_repair_tasks": [
                        {
                            "category": "query_repair",
                            "priority": 96,
                            "owner": "agent",
                            "action": "执行补检索式并合并去重候选。",
                            "query": "robot manipulator OMPL benchmark RRT* CHOMP",
                            "rationale": "补齐 benchmark/method 覆盖。",
                        }
                    ],
                    "next_run_config": {
                        "literature_provider": "online",
                        "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
                        "max_papers": 12,
                        "max_search_queries": 6,
                        "seed_papers_min": 3,
                    },
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="offline", max_papers=8, max_search_queries=2, sources=["crossref"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        max_search_queries=6,
                        sources=["semantic_scholar", "openalex", "arxiv", "crossref"],
                        extra_search_queries=["robot manipulator OMPL benchmark RRT* CHOMP"],
                        seed_papers=["10.1109/MRA.2012.2205651", "10.1177/0278364911406761", "10.1109/ICRA.2009.5152817"],
                    ),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_search_feedback_provider" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_queries" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_capacity" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_sources" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_seed_targets" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_provider" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_queries" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_capacity" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_sources" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_search_feedback_seed_targets" and check.status == "pass" for check in ready.checks))
        self.assertIn("search feedback", render_preflight_markdown(weak))

    def test_literature_rescue_execution_memory_guides_preflight_repair_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "rescue-execution-open"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-rescue-execution.json",
                {
                    "status": "no_new_papers",
                    "new_unique_papers": 0,
                    "closed_query_outcomes": 0,
                    "unresolved_query_outcomes": 1,
                    "selected_queries": ["robot manipulator OMPL benchmark"],
                    "repair_task_ids": ["retrieval-repair-001"],
                    "required_actions": ["检索修复任务 retrieval-repair-001 未闭环。"],
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(provider="offline", max_papers=8, max_search_queries=2, sources=["crossref"]),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        max_search_queries=6,
                        sources=["openalex", "arxiv", "crossref"],
                        extra_search_queries=["robot manipulator motion planning TrajOpt benchmark baseline"],
                        seed_papers=["10.1109/MRA.2012.2205651", "10.1177/0278364911406761", "10.1109/ICRA.2009.5152817"],
                    ),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_rescue_execution_provider" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_queries" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_sources" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_capacity" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_seed_papers" and check.status == "warn" for check in weak.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_provider" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_queries" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_sources" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_capacity" and check.status == "pass" for check in ready.checks))
        self.assertTrue(any(check.name == "memory_rescue_execution_seed_papers" and check.status == "pass" for check in ready.checks))
        self.assertIn("补检索", render_preflight_markdown(weak))

    def test_environment_snapshot_memory_guides_preflight_execution_and_release_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "env-partial"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "环境快照", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "04-environment-snapshot.json",
                {
                    "status": "partial",
                    "warnings": ["部分白名单命令当前不可定位：pytest"],
                    "package_versions": [{"name": "pip", "version": "25.0"}],
                    "tool_versions": [{"command": "pytest", "available": False, "path": ""}],
                    "source_tree": {"file_count": 3, "aggregate_sha256": "abc"},
                },
            )
            memory = build_run_memory(runs_dir)

            simulated = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="simulated", repeats=5),
                    release=_release_config_without_environment_archive(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            local = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    execution=ExecutionConfig(mode="local", repeats=5, allowed_commands=["python3", "pytest"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_environment_execution" and check.status == "warn" for check in simulated.checks))
        self.assertTrue(any(check.name == "memory_environment_archive" and check.status == "warn" for check in simulated.checks))
        self.assertTrue(any(check.name == "memory_environment_execution" and check.status == "pass" for check in local.checks))
        self.assertTrue(any(check.name == "memory_environment_archive" and check.status == "pass" for check in local.checks))
        self.assertIn("历史 run 环境快照不完整", render_preflight_markdown(simulated))

    def test_human_constraint_memory_guides_preflight_human_brief(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "human-constraint-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "03-review-constraint-compliance.json",
                {
                    "status": "block",
                    "human_brief_constraints": 1,
                    "blocked": 1,
                    "blocking_issues": ["HB-C01 未落实：必须比较 RRT*"],
                    "manual_tasks": [],
                },
            )
            memory = build_run_memory(runs_dir)

            missing = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            configured = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key"),
                    human=HumanConfig(constraints=["必须比较 RRT*"], resource_limits=["只允许运行 smoke-first"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        self.assertTrue(any(check.name == "memory_human_constraints" and check.status == "warn" for check in missing.checks))
        self.assertTrue(any(check.name == "memory_human_constraints" and check.status == "pass" for check in configured.checks))
        self.assertIn("human brief", render_preflight_markdown(missing))

    def test_open_source_compliance_memory_guides_preflight_config(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "open-source-compliance-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-open-source-compliance.json",
                {
                    "status": "block",
                    "score": 0.42,
                    "checked_lessons": 12,
                    "lesson_results": [
                        {"lesson_id": "query_execution_coverage_audit", "status": "block"},
                        {"lesson_id": "retrieval_rerank_before_synthesis", "status": "block"},
                        {"lesson_id": "human_feedback_compliance", "status": "block"},
                        {"lesson_id": "benchmark_result_schema_contract", "status": "block"},
                        {"lesson_id": "runtime_cost_observability", "status": "warn"},
                    ],
                    "blocking_issues": ["Semantic Scholar 429 导致 selected query 没有 source 返回。"],
                    "manual_tasks": ["补齐 run-manifest 和 LLM ledger。"],
                },
            )
            memory = build_run_memory(runs_dir)

            weak = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(base_url="http://127.0.0.1:9/v1", model="fake-model", api_key="test-key", max_calls=4),
                    literature=LiteratureConfig(provider="offline", max_papers=8, max_search_queries=4, sources=["semantic_scholar"]),
                    execution=ExecutionConfig(mode="simulated", repeats=3),
                    release=ReleaseConfig(),
                ),
                ping_llm=False,
                run_memory=memory,
            )
            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(
                        base_url="http://127.0.0.1:9/v1",
                        model="fake-model",
                        api_key="test-key",
                        max_calls=0,
                        max_prompt_chars=50000,
                        input_cost_per_million_tokens=2.0,
                        output_cost_per_million_tokens=10.0,
                    ),
                    literature=LiteratureConfig(provider="online", max_papers=12, max_search_queries=6, sources=["semantic_scholar", "openalex", "arxiv", "crossref"]),
                    human=HumanConfig(constraints=["必须比较 RRT*"], success_criteria=["保留 query/source 审计"]),
                    execution=ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=["examples/benchmark-adapter/manifest.json"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        for name in [
            "memory_open_source_compliance_llm",
            "memory_open_source_compliance_literature",
            "memory_open_source_compliance_human",
            "memory_open_source_compliance_execution",
            "memory_open_source_compliance_release",
            "memory_open_source_contract_literature_grounding",
            "memory_open_source_contract_runtime_trace",
            "memory_open_source_contract_human_gate",
            "memory_open_source_contract_execution_evidence",
        ]:
            self.assertTrue(any(check.name == name and check.status == "warn" for check in weak.checks), name)
            if name == "memory_open_source_contract_literature_grounding":
                continue
            self.assertTrue(any(check.name == name and check.status == "pass" for check in ready.checks), name)
        self.assertTrue(any(check.name == "memory_open_source_contract_lessons" and check.status == "pass" for check in weak.checks))

    def test_open_source_compliance_contract_preflight_passes_with_seed_roles(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "open-source-contract-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-open-source-compliance.json",
                {
                    "status": "block",
                    "score": 0.42,
                    "checked_lessons": 12,
                    "lesson_results": [
                        {"lesson_id": "query_execution_coverage_audit", "status": "block"},
                        {"lesson_id": "retrieval_rerank_before_synthesis", "status": "block"},
                        {"lesson_id": "runtime_cost_observability", "status": "block"},
                        {"lesson_id": "human_feedback_compliance", "status": "block"},
                        {"lesson_id": "benchmark_result_schema_contract", "status": "block"},
                    ],
                    "blocking_issues": ["外部项目约束未闭环。"],
                    "manual_tasks": [],
                },
            )
            memory = build_run_memory(runs_dir)

            ready = run_preflight(
                "机械臂路径规划",
                AgentConfig(
                    llm=LLMConfig(
                        base_url="http://127.0.0.1:9/v1",
                        model="fake-model",
                        api_key="test-key",
                        max_calls=0,
                        max_prompt_chars=50000,
                        input_cost_per_million_tokens=2.0,
                        output_cost_per_million_tokens=10.0,
                    ),
                    literature=LiteratureConfig(
                        provider="online",
                        max_papers=12,
                        max_search_queries=6,
                        sources=["semantic_scholar", "openalex", "arxiv", "crossref"],
                        seed_papers=[
                            "10.1000/review survey robot manipulator planning 2024",
                            "10.1001/benchmark benchmark dataset OMPL motion planning 2023",
                            "https://doi.org/10.1002/baseline RRT baseline method planner 2022",
                        ],
                    ),
                    human=HumanConfig(constraints=["必须比较 RRT*"], success_criteria=["保留 query/source 审计"]),
                    execution=ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=["examples/benchmark-adapter/manifest.json"]),
                    release=_complete_release_config(),
                ),
                ping_llm=False,
                run_memory=memory,
            )

        for name in [
            "memory_open_source_contract_literature_grounding",
            "memory_open_source_contract_runtime_trace",
            "memory_open_source_contract_human_gate",
            "memory_open_source_contract_execution_evidence",
        ]:
            self.assertTrue(any(check.name == name and check.status == "pass" for check in ready.checks), name)
        rendered = render_preflight_markdown(ready)
        self.assertIn("open-source lessons 已前置", rendered)


class _FakeOpenAIHandler(BaseHTTPRequestHandler):
    last_payload: dict | None = None

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).last_payload = payload
        body = json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": payload.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def _report_dict(report):
    return {
        "topic": report.topic,
        "status": report.status,
        "checks": [check.__dict__ for check in report.checks],
    }


def _complete_release_config() -> ReleaseConfig:
    return ReleaseConfig(
        code_repository_url="https://github.com/example/research-agent",
        code_archive_doi="10.5281/zenodo.1234567",
        code_license="Apache-2.0",
        code_version="v0.1.0",
        data_repository_url="https://zenodo.org/records/7654321",
        data_archive_doi="10.5281/zenodo.7654321",
        data_access_statement="All benchmark data are available from the archived public record.",
        environment_url="https://github.com/example/research-agent/releases/tag/v0.1.0",
        release_notes="First reproducibility release for audit testing.",
    )


def _release_config_without_environment_archive() -> ReleaseConfig:
    return ReleaseConfig(
        code_repository_url="https://github.com/example/research-agent",
        code_archive_doi="10.5281/zenodo.1234567",
        code_license="Apache-2.0",
        code_version="v0.1.0",
        data_repository_url="https://zenodo.org/records/7654321",
        data_archive_doi="10.5281/zenodo.7654321",
        data_access_statement="All benchmark data are available from the archived public record.",
        release_notes="First reproducibility release for audit testing.",
    )


if __name__ == "__main__":
    unittest.main()
