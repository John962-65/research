from __future__ import annotations

from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import json
import os
import unittest
from urllib.parse import quote
import urllib.error
import urllib.request

from research_agent.artifacts import write_json
from research_agent.config import load_config
from research_agent.models import Paper
import research_agent.web_server as web_server


ROOT = Path(__file__).resolve().parents[1]


class WebBenchmarkPreviewTest(unittest.TestCase):
    def test_literature_preview_returns_safe_read_only_candidates(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_client = web_server.OnlineLiteratureClient

        class FakeLiteratureClient:
            def __init__(self, config) -> None:
                self.config = config
                self.source_health = []

            def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
                self.source_health = [
                    {
                        "source": "openalex",
                        "status": "ok",
                        "queries": len(queries),
                        "returned": 1,
                        "errors": 0,
                        "rate_limited": False,
                        "elapsed_seconds": 0.01,
                        "cache_hits": 0,
                        "cache_misses": 1,
                        "cache_writes": 1,
                        "stale_cache_uses": 0,
                        "query_results": [
                            {
                                "source": "openalex",
                                "query": queries[0] if queries else topic,
                                "status": "ok",
                                "returned": 1,
                                "error": "api_key=oa-secret x-api-key: s2-secret mailto=lab@university.edu email=lab@university.edu",
                                "rate_limited": False,
                                "elapsed_seconds": 0.01,
                            }
                        ],
                    }
                ]
                return [
                    Paper(
                        title="Robot manipulator motion planning benchmark",
                        authors=["A. Researcher"],
                        year=2024,
                        venue="OpenAlex",
                        url="https://doi.org/10.1234/robot.preview",
                        abstract="A benchmark study for robot manipulator motion planning, RRT, CHOMP, and OMPL.",
                        relevance=0.91,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.1234/robot.preview",
                        citation_count=42,
                    ),
                    Paper(
                        title="Review on robot manipulator motion planning in dynamic environments",
                        authors=["B. Surveyor"],
                        year=2024,
                        venue="Robotics Review",
                        url="https://doi.org/10.1234/robot.review",
                        abstract="A review and survey of robot manipulator motion planning in dynamic environments.",
                        relevance=0.88,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.1234/robot.review",
                        citation_count=15,
                    ),
                    Paper(
                        title="CHOMP and TrajOpt baseline methods for robot arm planning",
                        authors=["C. Baseline"],
                        year=2013,
                        venue="Robotics Methods",
                        url="https://doi.org/10.1234/robot.baseline",
                        abstract="A baseline method comparison for CHOMP and TrajOpt in robot arm planning.",
                        relevance=0.86,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.1234/robot.baseline",
                        citation_count=130,
                    )
                ], ["openalex diagnostic api_key=oa-secret mailto=lab@university.edu email=lab@university.edu"]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            web_server.OnlineLiteratureClient = FakeLiteratureClient
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "topic": "机械臂路径规划",
                    "literature_provider": "online",
                    "literature_sources": "openalex",
                    "max_papers": 5,
                    "max_search_queries": 4,
                    "semantic_scholar_api_key": "s2-secret",
                    "openalex_api_key": "oa-secret",
                    "literature_contact_email": "lab@university.edu",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/literature-preview",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.OnlineLiteratureClient = original_client
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        encoded = json.dumps(data, ensure_ascii=False)
        self.assertIn(data["report"]["status"], {"ready", "needs_review"})
        self.assertTrue(data["report"]["read_only"])
        self.assertEqual(len(data["report"]["papers"]), 3)
        self.assertLessEqual(len(data["report"]["papers"]), payload["max_papers"])
        self.assertIn("Robot manipulator", data["report"]["papers"][0]["title"])
        self.assertEqual(data["report"]["recommended_seed_entries"][0], "10.1234/robot.review Review on robot manipulator motion planning in dynamic environments (2024)")
        self.assertIn("10.1234/robot.preview Robot manipulator motion planning benchmark (2024)", data["report"]["recommended_seed_entries"])
        self.assertEqual(data["report"]["seed_role_coverage"]["status"], "pass")
        self.assertGreaterEqual(data["report"]["seed_role_coverage"]["role_counts"]["review"], 1)
        self.assertGreaterEqual(data["report"]["seed_role_coverage"]["role_counts"]["benchmark_dataset"], 1)
        self.assertGreaterEqual(data["report"]["seed_role_coverage"]["role_counts"]["baseline_method"], 1)
        self.assertGreaterEqual(data["report"]["seed_role_coverage"]["role_counts"]["recent"], 1)
        self.assertTrue(any(item["primary_role"] == "review" for item in data["report"]["recommended_seed_items"]))
        self.assertIn("只读预览", data["markdown"])
        self.assertIn("推荐人工 Seed", data["markdown"])
        self.assertIn("角色覆盖：pass", data["markdown"])
        self.assertNotIn("s2-secret", encoded)
        self.assertNotIn("oa-secret", encoded)
        self.assertNotIn("lab@university.edu", encoded)
        self.assertIn("mailto=***", encoded)
        self.assertIn("email=***", encoded)
        self.assertEqual(before, after)

    def test_literature_preview_blocks_offline_provider_without_searching(self) -> None:
        original_client = web_server.OnlineLiteratureClient

        class FailingClient:
            def __init__(self, config) -> None:
                raise AssertionError("offline literature preview must not create online client")

        web_server.OnlineLiteratureClient = FailingClient
        try:
            report = web_server._literature_preview_report(
                "机械臂路径规划",
                web_server.LiteratureConfig(provider="offline", sources=["openalex"]),
            )
        finally:
            web_server.OnlineLiteratureClient = original_client

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("literature_provider must be online or auto" in issue for issue in report["blocking_issues"]))
        self.assertFalse(report["papers"])
        self.assertFalse(report["recommended_seed_entries"])

    def test_paper_grade_probe_api_is_safe_and_read_only(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_client = web_server.OnlineLiteratureClient

        class FakeProbeClient:
            def __init__(self, config) -> None:
                self.config = config
                self.source_health = []

            def resolve_doi_metadata(self, value: str) -> Paper | None:
                doi = value.split()[0]
                return Paper(
                    title=f"Resolved {doi}",
                    authors=["Seed Author"],
                    year=2024,
                    venue="Crossref",
                    url=f"https://doi.org/{doi}",
                    abstract="Resolved seed metadata.",
                    relevance=1.0,
                    source="crossref",
                    sources=["crossref"],
                    doi=doi,
                )

            def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
                self.source_health = [
                    {
                        "source": "openalex",
                        "status": "ok",
                        "queries": len(queries),
                        "returned": 2,
                        "errors": 0,
                        "rate_limited": False,
                        "query_results": [{"source": "openalex", "query": queries[0], "status": "ok", "returned": 2, "error": "api_key=oa-secret email=lab@university.edu"}],
                    },
                    {
                        "source": "arxiv",
                        "status": "ok",
                        "queries": len(queries),
                        "returned": 1,
                        "errors": 0,
                        "rate_limited": False,
                        "query_results": [{"source": "arxiv", "query": queries[0], "status": "ok", "returned": 1, "error": ""}],
                    },
                    {
                        "source": "crossref",
                        "status": "ok",
                        "queries": len(queries),
                        "returned": 1,
                        "errors": 0,
                        "rate_limited": False,
                        "query_results": [{"source": "crossref", "query": queries[0], "status": "ok", "returned": 1, "error": "mailto=lab@university.edu x-api-key: s2-secret"}],
                    },
                ]
                return [
                    Paper(
                        title="Robot manipulator motion planning benchmark",
                        authors=["A. Researcher"],
                        year=2024,
                        venue="OpenAlex",
                        url="https://doi.org/10.1234/robot.preview",
                        abstract="A benchmark study for robot manipulator motion planning.",
                        relevance=0.91,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.1234/robot.preview",
                    )
                ], ["probe diagnostic api_key=oa-secret mailto=lab@university.edu email=lab@university.edu"]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            web_server.OnlineLiteratureClient = FakeProbeClient
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "topic": "机械臂路径规划",
                    "literature_provider": "online",
                    "literature_sources": "openalex, arxiv, crossref",
                    "max_papers": 5,
                    "max_search_queries": 4,
                    "seed_papers": "10.1234/robot.review\n10.1234/robot.benchmark\n10.1234/robot.baseline",
                    "semantic_scholar_api_key": "s2-secret",
                    "openalex_api_key": "oa-secret",
                    "literature_contact_email": "lab@university.edu",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/paper-grade-probe",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.OnlineLiteratureClient = original_client
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        encoded = json.dumps(data, ensure_ascii=False)
        self.assertEqual(data["report"]["status"], "pass")
        self.assertTrue(data["report"]["read_only"])
        self.assertEqual(data["report"]["source_summary"]["successful_sources"], 3)
        self.assertEqual(data["report"]["seed_summary"]["metadata_resolved_seed_papers"], 3)
        self.assertIn("Paper-grade Online Probe", data["markdown"])
        self.assertNotIn("s2-secret", encoded)
        self.assertNotIn("oa-secret", encoded)
        self.assertNotIn("lab@university.edu", encoded)
        self.assertEqual(before, after)

    def test_gold_launch_bundle_aggregates_prelaunch_checks_safely(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_client = web_server.OnlineLiteratureClient
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        short_gateway_token = "sk-" + "LOCAL12345"

        class FakeBundleClient:
            def __init__(self, config) -> None:
                self.config = config
                self.source_health = []

            def resolve_doi_metadata(self, value: str) -> Paper | None:
                doi = value.split()[0]
                return Paper(
                    title=f"Resolved {doi}",
                    authors=["Seed Author"],
                    year=2024,
                    venue="Crossref",
                    url=f"https://doi.org/{doi}",
                    abstract="Resolved seed metadata.",
                    relevance=1.0,
                    source="crossref",
                    sources=["crossref"],
                    doi=doi,
                )

            def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
                self.source_health = [
                    {"source": "openalex", "status": "ok", "queries": len(queries), "returned": 2, "errors": 0, "rate_limited": False},
                    {"source": "arxiv", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                    {"source": "crossref", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                ]
                return [
                    Paper(
                        title="Robot manipulator motion planning benchmark",
                        authors=["A. Researcher"],
                        year=2024,
                        venue="OpenAlex",
                        url="https://doi.org/10.1234/robot.preview",
                        abstract="A benchmark study for robot manipulator motion planning.",
                        relevance=0.91,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.1234/robot.preview",
                    )
                ], [f"bundle diagnostic api_key=oa-secret token={short_gateway_token} mailto=lab@university.edu email=lab@university.edu"]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            web_server.OnlineLiteratureClient = FakeBundleClient
            os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8317"
            os.environ["OPENAI_MODEL"] = "gpt-5.5"
            os.environ["OPENAI_API_KEY"] = "env-secret-token"
            os.environ["RESEARCH_AGENT_CONTACT_EMAIL"] = "researcher@university.edu"
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "topic": "机械臂路径规划",
                    "paper_grade_enabled": True,
                    "llm_base_url": "http://127.0.0.1:8317",
                    "llm_model": "gpt-5.5",
                    "literature_provider": "online",
                    "literature_sources": "openalex, arxiv, crossref",
                    "max_papers": 5,
                    "max_search_queries": 4,
                    "seed_papers": "10.1234/robot.review\n10.1234/robot.benchmark\n10.1234/robot.baseline",
                    "execution_mode": "benchmark",
                    "execution_repeats": 5,
                    "benchmark_manifests": "benchmarks/missing/manifest-candidate.json",
                    "release_code_repository_url": "https://github.com/research-lab/iris-study",
                    "release_code_archive_doi": "10.5281/zenodo.7654321",
                    "release_code_license": "MIT",
                    "release_code_version": "v1.0.0",
                    "release_data_access_statement": "No restricted external data are used; benchmark data are available from the cited public source.",
                    "release_environment_url": "https://zenodo.org/records/7654321",
                    "llm_api_key": "payload-secret-token",
                    "semantic_scholar_api_key": "s2-secret",
                    "openalex_api_key": "oa-secret",
                    "literature_contact_email": "lab@university.edu",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/gold-launch-bundle",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.OnlineLiteratureClient = original_client
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        report = data["report"]
        components = {item["item"]: item for item in report["components"]}
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["read_only"])
        self.assertEqual(components["gold_env"]["status"], "pass")
        self.assertEqual(components["paper_grade_literature_probe"]["status"], "pass")
        self.assertIn("provider=online", components["paper_grade_literature_probe"]["evidence"])
        self.assertIn("configured_sources=3/3", components["paper_grade_literature_probe"]["evidence"])
        self.assertIn("successful_sources=3/2", components["paper_grade_literature_probe"]["evidence"])
        self.assertIn("doi_url_seeds=3/3", components["paper_grade_literature_probe"]["evidence"])
        self.assertEqual(components["benchmark_preview"]["status"], "block")
        self.assertEqual(report["prelaunch_focus"]["category"], "benchmark_manifest")
        self.assertFalse(report["prelaunch_focus"]["ready_except_server_environment"])
        self.assertIn("benchmark_preview", report["prelaunch_focus"]["blocking_components"])
        self.assertIn("benchmark_manifests", report["prelaunch_focus"]["form_fields"])
        self.assertIn("benchmark_manifests", components["benchmark_preview"]["form_fields"])
        self.assertEqual(components["release_metadata"]["status"], "pass")
        self.assertEqual(report["repair_plan_items"], 2)
        repair_plan = {item["component"]: item for item in report["repair_plan"]}
        self.assertIn("benchmark_preview", repair_plan)
        self.assertIn("gold_doctor", repair_plan)
        self.assertEqual(repair_plan["benchmark_preview"]["button"], "校验 Benchmark")
        self.assertIn("benchmark_manifests", repair_plan["benchmark_preview"]["form_fields"])
        self.assertIn("gold-launch-bundle", repair_plan["benchmark_preview"]["cli_hint"])
        self.assertIn("Repair Plan", data["markdown"])
        self.assertEqual(report["launch_plan"]["status"], "blocked")
        self.assertFalse(report["launch_plan"]["ready_to_execute_commands"])
        self.assertEqual(report["launch_plan"]["secret_policy"], "env_only")
        self.assertIn("llm_api_key", report["launch_plan"]["required_environment"])
        self.assertEqual(report["launch_plan"]["target_environment"]["status"], "matched")
        self.assertEqual(report["reports"]["gold_env"]["target_environment"]["status"], "matched")
        self.assertEqual(report["reports"]["gold_env"]["expected_mismatch_fields"], [])
        self.assertTrue(report["launch_plan"]["safe_commands"])
        self.assertTrue(any(" research_agent run " in command for command in report["launch_plan"]["safe_commands"]))
        self.assertTrue(any(" research_agent status " in command for command in report["launch_plan"]["safe_commands"]))
        self.assertTrue(any(" research_agent approve-execution " in command for command in report["launch_plan"]["safe_commands"]))
        self.assertFalse(any(command.startswith("export ") for command in report["launch_plan"]["safe_commands"]))
        self.assertIn("Gold Launch Bundle", data["markdown"])
        self.assertIn("Safe Launch Plan", data["markdown"])
        self.assertIn("benchmark_preview=block", "\n".join(report["next_steps"]))
        self.assertEqual(report["ignored_payload_secret_fields"], ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"])
        for needle in [
            "payload-secret-token",
            "s2-secret",
            "oa-secret",
            "env-secret-token",
            short_gateway_token,
            "researcher@university.edu",
            "lab@university.edu",
            "OPENAI_API_KEY",
        ]:
            self.assertNotIn(needle, encoded)
        self.assertIn("sk-***", encoded)
        self.assertEqual(before, after)

    def test_gold_bundle_prelaunch_focus_detects_environment_only_blocker_safely(self) -> None:
        components = [
            web_server._gold_bundle_component("gold_env", "block", "Gold Env", "missing=4", "Set server environment."),
            web_server._gold_bundle_component("paper_grade_literature_probe", "pass", "Gold 文献 Probe", "status=pass", "Ready."),
            web_server._gold_bundle_component("benchmark_preview", "pass", "校验 Benchmark", "status=ready", "Ready."),
            web_server._gold_bundle_component("release_metadata", "pass", "校验 Release", "status=ready", "Ready."),
            web_server._gold_bundle_component("gold_doctor", "block", "Gold Doctor", "status=blocked", "Rerun Gold Doctor."),
        ]

        focus = web_server._gold_bundle_prelaunch_focus(components)
        encoded = json.dumps(focus, ensure_ascii=False)

        self.assertEqual(focus["category"], "server_environment")
        self.assertTrue(focus["ready_except_server_environment"])
        self.assertTrue(focus["server_environment_refresh_required"])
        self.assertEqual(focus["blocking_components"], ["gold_env", "gold_doctor"])
        self.assertIn("llm_api_key", focus["form_fields"])
        self.assertNotIn("OPENAI_API_KEY", encoded)
        self.assertNotIn("sk-", encoded)

    def test_gold_bundle_paper_probe_component_blocks_when_probe_passes_but_thresholds_are_not_met(self) -> None:
        config = load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
        paper_probe = {
            "status": "pass",
            "source_summary": {
                "provider": "online",
                "configured_sources": 3,
                "successful_sources": 1,
            },
            "seed_summary": {
                "strong_seed_papers": 3,
                "metadata_resolved_seed_papers": 2,
            },
            "candidate_count": 1,
        }

        component = web_server._gold_bundle_paper_probe_component(paper_probe, config)

        self.assertEqual(component["status"], "block")
        self.assertIn("configured_sources=3/3", component["evidence"])
        self.assertIn("successful_sources=1/2", component["evidence"])
        self.assertIn("doi_url_seeds=2/3", component["evidence"])

    def test_gold_env_launch_kit_returns_placeholder_only_commands(self) -> None:
        original_root = web_server.ROOT
        env_keys = [
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_API_KEY",
            "RESEARCH_AGENT_CONTACT_EMAIL",
            "SEMANTIC_SCHOLAR_API_KEY",
            "OPENALEX_API_KEY",
        ]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for key in env_keys:
                    os.environ.pop(key, None)
                short_gateway_token = "sk-" + "LOCAL12345"
                payload = {
                    "llm_base_url": "http://127.0.0.1:8317",
                    "llm_model": "gpt-5.5",
                    "llm_api_key": short_gateway_token,
                    "literature_contact_email": "lab@university.edu",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/gold-env-launch-kit",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        encoded = json.dumps(data, ensure_ascii=False)
        report = data["report"]
        server_env = report["server_environment"]
        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["read_only"])
        self.assertEqual(report["secret_policy"], "env_only")
        self.assertEqual(report["ignored_payload_secret_fields"], ["llm_api_key"])
        self.assertEqual(server_env["status"], "needs_server_environment")
        self.assertEqual(server_env["required_present"], 0)
        self.assertEqual(server_env["required_total"], 4)
        self.assertEqual(
            server_env["missing_required"],
            ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"],
        )
        self.assertIn(server_env["gateway_socket"]["status"], {"reachable", "unreachable"})
        self.assertEqual(server_env["gateway_socket"]["target"], "http://127.0.0.1:8317")
        self.assertIn("http://127.0.0.1:8317", encoded)
        self.assertIn("gpt-5.5", encoded)
        self.assertIn("read -rsp", encoded)
        self.assertLess(
            report["shell_steps"].index("export RESEARCH_AGENT_CONTACT_EMAIL='<your-real-contact-email>'"),
            report["shell_steps"].index("read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY; export OPENAI_API_KEY; echo"),
        )
        self.assertEqual(report["gold_run_output"]["path"], "runs/iris-classification-benchmark-smoke-gold-run")
        self.assertEqual(report["gold_run_output"]["launch_path"], "runs/iris-classification-benchmark-smoke-gold-run")
        checklist = report["environment_setup_checklist"]
        checklist_by_field = {item["field"]: item for item in checklist}
        self.assertEqual(
            [item["field"] for item in checklist],
            [
                "llm_base_url",
                "llm_model",
                "literature_contact_email",
                "llm_api_key",
                "semantic_scholar_api_key",
                "openalex_api_key",
            ],
        )
        self.assertEqual(checklist_by_field["llm_api_key"]["status"], "missing")
        self.assertTrue(checklist_by_field["llm_api_key"]["required"])
        self.assertTrue(checklist_by_field["llm_api_key"]["secret"])
        self.assertIn("hidden prompt", checklist_by_field["llm_api_key"]["safe_action"])
        self.assertEqual(checklist_by_field["literature_contact_email"]["safe_action"], "export RESEARCH_AGENT_CONTACT_EMAIL='<your-real-contact-email>'")
        self.assertFalse(checklist_by_field["semantic_scholar_api_key"]["required"])
        self.assertTrue(checklist_by_field["semantic_scholar_api_key"]["secret"])
        self.assertIn("<optional-api-key>", checklist_by_field["semantic_scholar_api_key"]["safe_action"])
        self.assertIn("post_launch_gate_commands", report)
        self.assertTrue(any(" research_agent status " in command for command in report["post_launch_gate_commands"]))
        self.assertTrue(any(" research_agent approve " in command for command in report["post_launch_gate_commands"]))
        self.assertTrue(any(" research_agent approve-execution " in command for command in report["post_launch_gate_commands"]))
        self.assertIn("Environment Setup Checklist", data["markdown"])
        self.assertIn("Post-Launch Human Gates", data["markdown"])
        self.assertIn("Final Verification", data["markdown"])
        self.assertTrue(any(" gold-run-verify " in command for command in report["post_launch_verification_commands"]))
        self.assertEqual(report["helper_script"], "scripts/start_gold_web_env.sh")
        self.assertEqual(report["web_restart_command"], "scripts/start_gold_web_env.sh")
        self.assertEqual(report["startup_verification_policy"], "post_key_doctor_ping_and_bundle_gate")
        self.assertEqual(report["helper_script_post_key_checks"], ["gold-run-doctor --ping-llm --no-write", "gold-launch-bundle --no-write"])
        self.assertEqual(report["port_conflict_policy"], "prompt_before_secret")
        self.assertEqual(report["web_replace_environment"], "RESEARCH_AGENT_WEB_REPLACE=1")
        self.assertIn("web_restart_fallback_command", report)
        self.assertIn("release_code_repository_url", report["release_overrides"])
        self.assertIn("--release-code-repository-url", encoded)
        self.assertIn("--release-code-archive-doi", encoded)
        self.assertIn("research-agent-lab/research-agent", encoded)
        self.assertNotIn("paper-grade-scaffold", encoded)
        self.assertIn("<your-real-contact-email>", encoded)
        self.assertIn("RESEARCH_AGENT_WEB_REPLACE=1", encoded)
        self.assertIn("Gold Env Launch Kit", data["markdown"])
        self.assertIn("服务端环境", data["markdown"])
        self.assertIn("Startup verification", data["markdown"])
        self.assertIn("Helper post-key checks", data["markdown"])
        self.assertIn("gold-run-doctor --ping-llm --no-write", data["markdown"])
        self.assertIn("gold-launch-bundle --no-write", data["markdown"])
        self.assertNotIn(short_gateway_token, encoded)
        self.assertNotIn("lab@university.edu", encoded)
        self.assertEqual(before, after)

    def test_gold_env_launch_kit_rejects_placeholder_contact_email_without_echoing_it(self) -> None:
        env_keys = [
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_API_KEY",
            "RESEARCH_AGENT_CONTACT_EMAIL",
            "SEMANTIC_SCHOLAR_API_KEY",
            "OPENALEX_API_KEY",
        ]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8317"
            os.environ["OPENAI_MODEL"] = "gpt-5.5"
            os.environ["OPENAI_API_KEY"] = "unit-test-api-token"
            os.environ["RESEARCH_AGENT_CONTACT_EMAIL"] = "agent@example.org"
            os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            os.environ.pop("OPENALEX_API_KEY", None)

            report = web_server.build_gold_env_launch_kit(load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml"))
            rendered = web_server.render_gold_env_launch_kit_markdown(report)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        server_env = report["server_environment"]
        checklist_by_field = {item["field"]: item for item in report["environment_setup_checklist"]}
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertEqual(server_env["status"], "needs_server_environment")
        self.assertEqual(server_env["required_present"], 3)
        self.assertEqual(server_env["required_total"], 4)
        self.assertEqual(server_env["missing_required"], [])
        self.assertEqual(server_env["invalid_required"], ["RESEARCH_AGENT_CONTACT_EMAIL"])
        self.assertEqual(checklist_by_field["literature_contact_email"]["status"], "invalid")
        self.assertNotIn("agent@example.org", encoded)
        self.assertNotIn("agent@example.org", rendered)

    def test_gold_env_launch_kit_uses_fresh_launch_path_when_default_output_exists(self) -> None:
        original_root = web_server.ROOT
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                web_server.ROOT = root
                default_output = root / "runs" / "iris-classification-benchmark-smoke-gold-run"
                default_output.mkdir(parents=True)

                report = web_server.build_gold_env_launch_kit(load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml"))
                markdown = web_server.render_gold_env_launch_kit_markdown(report)

            launch_path = "runs/iris-classification-benchmark-smoke-gold-run-2"
            self.assertEqual(report["gold_run_output"]["status"], "exists")
            self.assertEqual(report["gold_run_output"]["launch_path"], launch_path)
            self.assertIn(f"RESEARCH_AGENT_GOLD_OUT={launch_path}", report["cli_launcher_command"])
            self.assertIn(f"RESEARCH_AGENT_GOLD_OUT={launch_path}", report["cli_launcher_dry_run_command"])
            self.assertTrue(any(launch_path in command for command in report["post_launch_gate_commands"]))
            self.assertTrue(any(launch_path in command for command in report["post_launch_verification_commands"]))
            self.assertIn(f"Suggested launch output：`{launch_path}`", markdown)
            self.assertNotIn("sk-", json.dumps(report, ensure_ascii=False))
        finally:
            web_server.ROOT = original_root

    def test_gold_env_launch_kit_bundle_verification_focuses_only_on_server_env(self) -> None:
        original_client = web_server.OnlineLiteratureClient
        env_keys = [
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_API_KEY",
            "RESEARCH_AGENT_CONTACT_EMAIL",
            "SEMANTIC_SCHOLAR_API_KEY",
            "OPENALEX_API_KEY",
        ]
        previous_env = {key: os.environ.get(key) for key in env_keys}

        class FakeBundleClient:
            def __init__(self, config) -> None:
                self.config = config
                self.source_health = []

            def resolve_doi_metadata(self, value: str) -> Paper | None:
                return Paper(
                    title=f"Resolved {value}",
                    authors=["Seed Author"],
                    year=2024,
                    venue="Crossref",
                    url=f"https://doi.org/{value}",
                    abstract="Resolved seed metadata.",
                    relevance=1.0,
                    source="crossref",
                    sources=["crossref"],
                    doi=value,
                )

            def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
                self.source_health = [
                    {"source": "semantic_scholar", "status": "ok", "queries": len(queries), "returned": 2, "errors": 0, "rate_limited": False},
                    {"source": "openalex", "status": "ok", "queries": len(queries), "returned": 2, "errors": 0, "rate_limited": False},
                    {"source": "crossref", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                ]
                return [
                    Paper(
                        title="UCI Iris classification benchmark",
                        authors=["Benchmark Author"],
                        year=2024,
                        venue="OpenAlex",
                        url="https://doi.org/10.24432/C56C76",
                        abstract="Iris benchmark candidate.",
                        relevance=0.95,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.24432/C56C76",
                    )
                ], []

        try:
            for key in env_keys:
                os.environ.pop(key, None)
            web_server.OnlineLiteratureClient = FakeBundleClient
            config = load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
            kit = web_server.build_gold_env_launch_kit(config)
            release_field_map = {
                "release_code_repository_url": "code_repository_url",
                "release_code_archive_doi": "code_archive_doi",
                "release_code_license": "code_license",
                "release_code_version": "code_version",
                "release_data_access_statement": "data_access_statement",
                "release_environment_url": "environment_url",
                "release_notes": "release_notes",
            }
            release_overrides = {release_field_map[key]: value for key, value in kit["release_overrides"].items()}
            config = replace(config, release=replace(config.release, **release_overrides))
            report = web_server.build_gold_launch_bundle_report(
                "Iris classification benchmark smoke",
                config,
                benchmark_pack_run_dir=ROOT / "runs" / "uci-iris-expanded-baseline-pack-run",
                fulltext_grounding_run_dir=ROOT / "runs" / "uci-iris-fulltext-grounding",
                candidate_run_dir=None,
                base_dir=ROOT,
            )
        finally:
            web_server.OnlineLiteratureClient = original_client
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        components = {item["item"]: item for item in report["components"]}
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(components["gold_env"]["status"], "block")
        self.assertEqual(components["paper_grade_literature_probe"]["status"], "pass")
        self.assertEqual(components["benchmark_preview"]["status"], "pass")
        self.assertEqual(components["release_metadata"]["status"], "pass")
        self.assertEqual(report["reports"]["release_metadata"]["blocking_fields"], [])
        self.assertEqual(report["prelaunch_focus"]["category"], "server_environment")
        self.assertTrue(report["prelaunch_focus"]["ready_except_server_environment"])
        self.assertEqual(report["prelaunch_focus"]["blocking_components"], ["gold_env", "gold_doctor"])
        server_env = report["reports"]["gold_env"]["server_environment"]
        self.assertEqual(server_env["status"], "needs_server_environment")
        self.assertEqual(server_env["required_present"], 0)
        self.assertEqual(server_env["required_total"], 4)
        self.assertIn(server_env["gateway_socket"]["status"], {"reachable", "unreachable"})
        self.assertIn("server_env=0/4", components["gold_env"]["evidence"])
        self.assertIn("服务端环境", web_server.render_gold_launch_bundle_markdown(report))
        self.assertIn("--release-notes", "\n".join(kit["verification_steps"]))
        self.assertNotIn("paper-grade-scaffold", encoded)
        self.assertNotIn("OPENAI_API_KEY", encoded)
        self.assertNotIn("sk-", encoded)

    def test_gold_launch_bundle_allows_missing_optional_literature_api_keys_when_required_env_ready(self) -> None:
        original_client = web_server.OnlineLiteratureClient
        env_keys = [
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_API_KEY",
            "RESEARCH_AGENT_CONTACT_EMAIL",
            "SEMANTIC_SCHOLAR_API_KEY",
            "OPENALEX_API_KEY",
        ]
        previous_env = {key: os.environ.get(key) for key in env_keys}

        class FakeBundleClient:
            def __init__(self, config) -> None:
                self.config = config
                self.source_health = []

            def resolve_doi_metadata(self, value: str) -> Paper | None:
                return Paper(
                    title=f"Resolved {value}",
                    authors=["Seed Author"],
                    year=2024,
                    venue="Crossref",
                    url=f"https://doi.org/{value}",
                    abstract="Resolved seed metadata.",
                    relevance=0.95,
                    source="crossref",
                    sources=["crossref"],
                    doi=value,
                )

            def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
                self.source_health = [
                    {"source": "openalex", "status": "ok", "queries": len(queries), "returned": 2, "errors": 0, "rate_limited": False},
                    {"source": "arxiv", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                    {"source": "crossref", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                ]
                return [
                    Paper(
                        title="UCI Iris classification benchmark",
                        authors=["Benchmark Author"],
                        year=2024,
                        venue="OpenAlex",
                        url="https://doi.org/10.24432/C56C76",
                        abstract="Iris benchmark candidate.",
                        relevance=0.95,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.24432/C56C76",
                    )
                ], []

        try:
            os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8317"
            os.environ["OPENAI_MODEL"] = "gpt-5.5"
            os.environ["OPENAI_API_KEY"] = "unit-test-api-token"
            os.environ["RESEARCH_AGENT_CONTACT_EMAIL"] = "researcher@university.edu"
            os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            os.environ.pop("OPENALEX_API_KEY", None)
            web_server.OnlineLiteratureClient = FakeBundleClient
            config = load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
            kit = web_server.build_gold_env_launch_kit(config)
            release_field_map = {
                "release_code_repository_url": "code_repository_url",
                "release_code_archive_doi": "code_archive_doi",
                "release_code_license": "code_license",
                "release_code_version": "code_version",
                "release_data_access_statement": "data_access_statement",
                "release_environment_url": "environment_url",
                "release_notes": "release_notes",
            }
            release_overrides = {release_field_map[key]: value for key, value in kit["release_overrides"].items()}
            config = replace(config, release=replace(config.release, **release_overrides))
            report = web_server.build_gold_launch_bundle_report(
                "Iris classification benchmark smoke",
                config,
                benchmark_pack_run_dir=ROOT / "runs" / "uci-iris-expanded-baseline-pack-run",
                fulltext_grounding_run_dir=ROOT / "runs" / "uci-iris-fulltext-grounding",
                candidate_run_dir=None,
                base_dir=ROOT,
            )
        finally:
            web_server.OnlineLiteratureClient = original_client
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        components = {item["item"]: item for item in report["components"]}
        doctor = report["reports"]["gold_doctor"]
        self.assertEqual(report["status"], "ready_to_start")
        self.assertTrue(report["can_start_gold_run"])
        self.assertEqual(components["gold_env"]["status"], "pass")
        self.assertEqual(components["gold_doctor"]["status"], "pass")
        self.assertEqual(doctor["launch_status"], "ready_to_start")
        self.assertTrue(doctor["can_start_gold_run"])
        self.assertEqual(doctor["launch_readiness"]["status"], "ready_to_start")
        self.assertIn("semantic_scholar_key", doctor["warn_checks"])
        self.assertIn("openalex_key", doctor["warn_checks"])
        self.assertNotIn("doctor_ready", doctor["launch_readiness"]["review_items"])
        self.assertNotIn("unit-test-api-token", json.dumps(report, ensure_ascii=False))

    def test_benchmark_manifest_lint_accepts_template_without_writing_files(self) -> None:
        original_root = web_server.ROOT
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                manifest = {
                    "name": "robot-motion-planning",
                    "role": "candidate",
                    "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
                    "metrics_path": "metrics.json",
                    "expected_artifacts": ["metrics.json"],
                    "expected_metrics": ["success_rate"],
                    "metric_schema": {
                        "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."}
                    },
                    "grader": "run_benchmark.py",
                    "grader_version": "web-lint-grader-v1",
                    "grader_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
                    "submission_path": "submission.csv",
                    "source_files": ["run_benchmark.py"],
                    "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                    "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                    "dataset_version": "ompl-1.6.0",
                    "split_name": "web lint split",
                    "split_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
                    "license": "BSD-3-Clause",
                    "baseline": "RRT*",
                    "baseline_version": "ompl-1.6.0",
                    "citation": "10.1109/MRA.2012.2205651",
                    "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat_index.",
                    "min_repeats": 1,
                }
                payload = {
                    "path": "benchmarks/robot-motion-planning/manifest.json",
                    "manifest": json.dumps(manifest),
                    "allowed_commands": "python3",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/benchmark-manifest-lint",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        self.assertEqual(data["report"]["status"], "ready")
        self.assertEqual(data["report"]["paper_grade_status"], "review_required")
        self.assertTrue(any("min_repeats" in issue for issue in data["report"]["paper_grade_issues"]))
        self.assertTrue(any("min_repeats=1" in warning for warning in data["report"]["warnings"]))
        self.assertIn("草稿校验和保存不会创建 run 或执行命令", data["markdown"])
        self.assertIn("Paper-grade", data["markdown"])
        self.assertEqual(before, after)

    def test_benchmark_manifest_lint_uses_payload_paper_grade_threshold(self) -> None:
        payload = {
            "path": "benchmarks/robot-motion-planning/manifest.json",
            "manifest": json.dumps(_web_lint_manifest(min_repeats=3)),
            "allowed_commands": "python3",
            "paper_grade_min_execution_repeats": 5,
        }
        report = web_server._lint_benchmark_manifest_payload(payload, web_server._paper_grade_config_from_payload(payload))

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["paper_grade_status"], "review_required")
        self.assertEqual(report["min_execution_repeats"], 5)
        self.assertTrue(any("min_repeats >= 5" in issue for issue in report["paper_grade_issues"]))
        self.assertTrue(any("阈值 5" in warning for warning in report["warnings"]))

    def test_benchmark_manifest_save_writes_only_safe_benchmarks_manifest(self) -> None:
        original_root = web_server.ROOT
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "path": "benchmarks/robot-motion-planning/manifest.json",
                    "manifest": json.dumps(
                        {
                            "name": "robot-motion-planning",
                            "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
                            "metrics_path": "metrics.json",
                            "expected_artifacts": ["metrics.json"],
                            "expected_metrics": ["success_rate"],
                            "metric_schema": {
                                "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."}
                            },
                            "grader": "run_benchmark.py",
                            "grader_version": "web-save-grader-v1",
                            "grader_sha256": "7777777777777777777777777777777777777777777777777777777777777777",
                            "submission_path": "submission.csv",
                            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_version": "ompl-1.6.0",
                            "split_name": "web save split",
                            "split_sha256": "7777777777777777777777777777777777777777777777777777777777777777",
                            "license": "BSD-3-Clause",
                            "baseline_version": "ompl-1.6.0",
                            "citation": "10.1109/MRA.2012.2205651",
                            "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat_index.",
                            "min_repeats": 1,
                        }
                    ),
                    "allowed_commands": "python3",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/benchmark-manifest-save",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root

            saved = root / "benchmarks" / "robot-motion-planning" / "manifest.json"
            saved_data = json.loads(saved.read_text(encoding="utf-8"))

        self.assertEqual(data["path"], "benchmarks/robot-motion-planning/manifest.json")
        self.assertEqual(saved_data["command"][0], "python3")
        self.assertIn(saved_data["metrics_path"], saved_data["expected_artifacts"])

    def test_benchmark_manifest_save_rejects_unsafe_path_and_invalid_json(self) -> None:
        original_root = web_server.ROOT
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {"path": "../manifest.json", "manifest": "{", "allowed_commands": "python3"}
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/benchmark-manifest-save",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(request, timeout=2)
                body = json.loads(ctx.exception.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root

        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("manifest lint blocked save", body["error"])
        self.assertFalse((root / "manifest.json").exists())

    def test_benchmark_manifest_save_path_rejects_symlink_components(self) -> None:
        original_root = web_server.ROOT
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "README.md"
            target.write_text("keep me", encoding="utf-8")
            manifest_dir = root / "benchmarks" / "linked"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").symlink_to(target)
            web_server.ROOT = root
            try:
                destination = web_server._benchmark_manifest_save_path(
                    "benchmarks/linked/manifest.json"
                )
            finally:
                web_server.ROOT = original_root

            self.assertIsNone(destination)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep me")

    def test_benchmark_template_endpoint_returns_read_only_manifest_template(self) -> None:
        original_root = web_server.ROOT
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                topic = quote("机械臂路径规划")
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/benchmark-template?topic={topic}", timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
            after = sorted(path.relative_to(root) for path in root.rglob("*"))

        template = data["template"]
        for field in data["required_fields"]:
            self.assertIn(field, template)
        self.assertEqual(template["command"][0], "python3")
        self.assertEqual(template["role"], "candidate")
        self.assertIn(template["metrics_path"], template["expected_artifacts"])
        self.assertTrue(template["baseline"])
        self.assertIn("does not create files", data["markdown"])
        self.assertIn("create runs", data["markdown"])
        self.assertIn("execute commands", data["markdown"])
        self.assertEqual(before, after)

    def test_benchmark_examples_endpoint_lists_repo_example(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/benchmark-examples", timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        paths = [item.get("path") for item in data.get("examples", []) if isinstance(item, dict)]
        self.assertIn("examples/benchmark-adapter/manifest.json", paths)
        example = next(item for item in data["examples"] if item.get("path") == "examples/benchmark-adapter/manifest.json")
        self.assertEqual(example["command"][0], "python3")
        self.assertEqual(example["metrics_path"], "metrics.json")
        self.assertIn("ompl", example["dataset_url"].lower())
        self.assertTrue(example["license"])
        self.assertTrue(example["baseline_version"])
        self.assertIn("10.1109", example["citation"])

    def test_gold_defaults_endpoint_prefers_formal_external_benchmark_pack(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/gold-defaults", timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        defaults = data["defaults"]
        self.assertTrue(defaults["paper_grade_enabled"])
        self.assertEqual(defaults["literature"]["provider"], "online")
        self.assertGreaterEqual(len(defaults["literature"]["sources"]), 2)
        self.assertEqual(defaults["literature"]["min_doi_url_seed_papers"], 3)
        self.assertGreaterEqual(len(defaults["literature"]["seed_papers"]), 3)
        self.assertGreaterEqual(len(defaults["literature"]["extra_search_queries"]), 3)
        self.assertIn("benchmarks/uci-iris-classification/fulltext/iris.names.txt", defaults["literature"]["fulltext_paths"])
        self.assertTrue(any("10.24432/C56C76" in item for item in defaults["literature"]["seed_papers"]))
        self.assertEqual(defaults["execution"]["mode"], "benchmark")
        self.assertGreaterEqual(defaults["execution"]["repeats"], 5)
        paths = defaults["execution"]["benchmark_manifest_paths"]
        self.assertEqual(
            paths,
            [
                "benchmarks/uci-iris-classification/manifest-candidate.json",
                "benchmarks/uci-iris-classification/manifest-baseline.json",
                "benchmarks/uci-iris-classification/manifest-ablation.json",
            ],
        )
        self.assertFalse(any(path.startswith("examples/") for path in paths))
        self.assertEqual(defaults["support_runs"]["status"], "ready")
        self.assertEqual(defaults["support_runs"]["benchmark_pack_run_dir"], "runs/uci-iris-expanded-baseline-pack-run")
        self.assertEqual(defaults["support_runs"]["fulltext_grounding_run_dir"], "runs/uci-iris-fulltext-grounding")
        release_fields = defaults["release"]["config_fields"]
        self.assertIn("research-agent-lab/research-agent", release_fields["code_repository_url"])
        self.assertEqual(release_fields["code_license"], "MIT")
        self.assertEqual(release_fields["data_archive_doi"], "10.24432/C56C76")
        self.assertIn("Support runs", data["markdown"])
        self.assertIn("Release 必填", data["markdown"])
        self.assertTrue(any("Gold Defaults 已回填 UCI Iris DOI/URL seed papers" in item for item in defaults["manual_todos"]))
        self.assertFalse(any("release metadata" in item and "填写真实" in item for item in defaults["manual_todos"]))

    def test_gold_defaults_smoke_endpoint_reports_ready_except_server_environment(self) -> None:
        original_client = web_server.OnlineLiteratureClient
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}

        class FakeGoldDefaultsSmokeClient:
            def __init__(self, config) -> None:
                self.config = config
                self.source_health = []

            def resolve_doi_metadata(self, value: str) -> Paper | None:
                identifier = value.split()[0]
                return Paper(
                    title=f"Resolved {identifier}",
                    authors=["Seed Author"],
                    year=2024,
                    venue="Crossref",
                    url=identifier if identifier.startswith("http") else f"https://doi.org/{identifier}",
                    abstract="Resolved seed metadata.",
                    relevance=1.0,
                    source="crossref",
                    sources=["crossref"],
                    doi=identifier if not identifier.startswith("http") else "",
                )

            def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
                self.source_health = [
                    {"source": "openalex", "status": "ok", "queries": len(queries), "returned": 2, "errors": 0, "rate_limited": False},
                    {"source": "arxiv", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                    {"source": "crossref", "status": "ok", "queries": len(queries), "returned": 1, "errors": 0, "rate_limited": False},
                ]
                return [
                    Paper(
                        title="UCI Iris classification benchmark",
                        authors=["A. Researcher"],
                        year=2024,
                        venue="OpenAlex",
                        url="https://doi.org/10.24432/C56C76",
                        abstract="A reproducible Iris classification benchmark.",
                        relevance=0.95,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.24432/C56C76",
                    )
                ], []

        try:
            for key in env_keys:
                os.environ.pop(key, None)
            web_server.OnlineLiteratureClient = FakeGoldDefaultsSmokeClient
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {"topic": "Iris classification benchmark smoke"}
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/gold-defaults-smoke",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
        finally:
            web_server.OnlineLiteratureClient = original_client
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        report = data["report"]
        components = {item["item"]: item for item in report["components"]}
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertEqual(report["status"], "ready_except_server_environment")
        self.assertTrue(report["read_only"])
        self.assertTrue(report["input_ready"])
        self.assertTrue(report["ready_except_server_environment"])
        self.assertEqual(report["prelaunch_focus"]["category"], "server_environment")
        server_env = report["server_environment"]
        self.assertEqual(server_env["status"], "needs_server_environment")
        self.assertEqual(server_env["required_present"], 0)
        self.assertEqual(server_env["required_total"], 4)
        self.assertIn(server_env["gateway_socket"]["status"], {"reachable", "unreachable"})
        self.assertIn("缺失必填环境：OPENAI_BASE_URL, OPENAI_MODEL, RESEARCH_AGENT_CONTACT_EMAIL, <secret-env>", data["markdown"])
        checklist = report["environment_setup_checklist"]
        checklist_by_field = {item["field"]: item for item in checklist}
        self.assertEqual(
            [item["field"] for item in checklist],
            [
                "llm_base_url",
                "llm_model",
                "literature_contact_email",
                "llm_api_key",
                "semantic_scholar_api_key",
                "openalex_api_key",
            ],
        )
        self.assertEqual(checklist_by_field["llm_base_url"]["environment"], "OPENAI_BASE_URL")
        self.assertEqual(checklist_by_field["llm_api_key"]["environment"], "<secret-env>")
        self.assertEqual(checklist_by_field["llm_api_key"]["status"], "missing")
        self.assertTrue(checklist_by_field["llm_api_key"]["secret"])
        self.assertIn("hidden prompt", checklist_by_field["llm_api_key"]["safe_action"])
        self.assertEqual(checklist_by_field["semantic_scholar_api_key"]["environment"], "<secret-env>")
        self.assertIn("服务端环境", data["markdown"])
        self.assertIn("Environment Setup Checklist", data["markdown"])
        self.assertIn("<secret-env>", data["markdown"])
        self.assertEqual(components["gold_env"]["status"], "block")
        self.assertEqual(components["paper_grade_literature_probe"]["status"], "pass")
        self.assertEqual(components["benchmark_preview"]["status"], "pass")
        self.assertEqual(components["release_metadata"]["status"], "pass")
        self.assertEqual(report["gold_defaults"]["support_runs_status"], "ready")
        self.assertIn("manifest-candidate.json", "\n".join(report["gold_defaults"]["benchmark_manifest_paths"]))
        self.assertEqual(report["gold_run_output"]["path"], "runs/iris-classification-benchmark-smoke-gold-run")
        self.assertIn(report["gold_run_output"]["status"], {"available", "exists"})
        launch_path = report["gold_run_output"]["launch_path"]
        self.assertTrue(launch_path.startswith(report["gold_run_output"]["path"]))
        self.assertIn("scripts/run_gold_cli_env.sh", report["safe_commands"]["cli_launcher"])
        self.assertIn("RESEARCH_AGENT_GOLD_DRY_RUN=1", report["safe_commands"]["cli_launcher_dry_run"])
        self.assertIn(f"--out {launch_path}", report["safe_commands"]["gold_launch"])
        self.assertTrue(report["gold_run_output"]["safe_to_render"])
        self.assertIn("Gold run output", data["markdown"])
        self.assertIn("RESEARCH_AGENT_WEB_REPLACE=1 scripts/start_gold_web_env.sh", data["markdown"])
        self.assertIn("scripts/run_gold_cli_env.sh", data["markdown"])
        self.assertTrue(any(launch_path in command for command in report["post_launch_gate_commands"]))
        self.assertTrue(any(" research_agent status " in command for command in report["post_launch_gate_commands"]))
        self.assertTrue(any(" research_agent approve-execution " in command for command in report["post_launch_gate_commands"]))
        self.assertTrue(any(launch_path in command for command in report["post_launch_verification_commands"]))
        self.assertTrue(any(" gold-run-verify " in command for command in report["post_launch_verification_commands"]))
        self.assertTrue(any(" perfect-readiness " in command for command in report["post_launch_verification_commands"]))
        self.assertIn("Post-Launch Human Gates", data["markdown"])
        self.assertIn("Final Verification", data["markdown"])
        self.assertIn("gold-launch-bundle", encoded)
        self.assertNotIn("paper-grade-scaffold", encoded)
        self.assertNotIn("OPENAI_API_KEY", encoded)
        self.assertNotIn("sk-", encoded)

    def test_gold_defaults_output_summary_suggests_fresh_launch_path_when_default_output_exists(self) -> None:
        original_root = web_server.ROOT
        try:
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                web_server.ROOT = root
                default_output = root / "runs" / "iris-classification-benchmark-smoke-gold-run"
                default_output.mkdir(parents=True)

                summary = web_server._gold_defaults_output_summary("runs/iris-classification-benchmark-smoke-gold-run")

            self.assertEqual(summary["status"], "exists")
            self.assertTrue(summary["exists"])
            self.assertEqual(summary["path"], "runs/iris-classification-benchmark-smoke-gold-run")
            self.assertEqual(summary["launch_path"], "runs/iris-classification-benchmark-smoke-gold-run-2")
            self.assertEqual(summary["suggested_path"], "runs/iris-classification-benchmark-smoke-gold-run-2")
            self.assertIn("fresh --out", summary["next_action"])
            self.assertNotIn("sk-", json.dumps(summary))
        finally:
            web_server.ROOT = original_root

    def test_gold_defaults_cli_launcher_command_uses_fresh_out_when_default_output_exists(self) -> None:
        command = web_server._gold_defaults_cli_launcher_command(
            "RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh",
            out_dir="runs/iris-classification-benchmark-smoke-gold-run-2",
            default_out_dir="runs/iris-classification-benchmark-smoke-gold-run",
        )

        self.assertEqual(
            command,
            "RESEARCH_AGENT_GOLD_OUT=runs/iris-classification-benchmark-smoke-gold-run-2 "
            "RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh",
        )
        self.assertNotIn("sk-", command)

    def test_platform_audit_endpoint_is_read_only_without_starting_runs(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "weak-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-10T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 1, "total_papers": 2, "confidence_status": "warn"})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": []})
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/platform-audit", timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            written_json = (runs_dir / "runs-platform-audit.json").exists()
            written_md = (runs_dir / "runs-platform-audit.md").exists()
            run_dirs = sorted(path.name for path in runs_dir.iterdir() if path.is_dir())

        self.assertEqual(data["audit"]["status"], "blocked")
        self.assertIn("平台能力审计", data["markdown"])
        self.assertEqual(before, after)
        self.assertFalse(written_json)
        self.assertFalse(written_md)
        self.assertEqual(run_dirs, ["weak-run"])

    def test_open_source_backfill_endpoint_previews_then_writes_artifacts(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/open-source-compliance-backfill", timeout=5) as response:
                    preview = json.loads(response.read().decode("utf-8"))
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/open-source-compliance-backfill",
                    data=json.dumps({"dry_run": False, "force": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    written = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

            lessons_exists = (run_dir / "00-open-source-lessons.json").exists()
            compliance_exists = (run_dir / "13-open-source-compliance.json").exists()

        self.assertEqual(preview["report"]["would_write_lessons"], 1)
        self.assertEqual(preview["report"]["would_write_compliance"], 1)
        self.assertEqual(written["report"]["lessons_written"], 1)
        self.assertEqual(written["report"]["compliance_written"], 1)
        self.assertTrue(lessons_exists)
        self.assertTrue(compliance_exists)
        self.assertIn("Open-Source Compliance Backfill", written["markdown"])

    def test_llm_observability_backfill_endpoint_previews_then_writes_audits(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/llm-observability-backfill", timeout=5) as response:
                    preview = json.loads(response.read().decode("utf-8"))
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/llm-observability-backfill",
                    data=json.dumps({"dry_run": False, "force": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    written = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

            trace_exists = (run_dir / "13-llm-trace-audit.json").exists()
            economics_exists = (run_dir / "13-run-economics-audit.json").exists()
            observability_exists = (run_dir / "13-agent-observability-audit.json").exists()

        self.assertEqual(preview["report"]["would_write_trace"], 1)
        self.assertEqual(preview["report"]["would_write_economics"], 1)
        self.assertEqual(preview["report"]["would_write_observability"], 1)
        self.assertEqual(written["report"]["trace_written"], 1)
        self.assertEqual(written["report"]["economics_written"], 1)
        self.assertEqual(written["report"]["observability_written"], 1)
        self.assertTrue(trace_exists)
        self.assertTrue(economics_exists)
        self.assertTrue(observability_exists)
        self.assertFalse((run_dir / "run-llm-ledger.json").exists())
        self.assertIn("LLM Observability Backfill", written["markdown"])

    def test_llm_observability_backfill_endpoint_returns_public_report(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_backfill = web_server.backfill_llm_observability

        def fake_backfill(runs_dir, *, dry_run=False, force=False, limit=0):
            return {
                "schema_version": 1,
                "generated_at": "test",
                "runs_dir": str(runs_dir),
                "dry_run": dry_run,
                "force": force,
                "limit": limit,
                "scanned_runs": 1,
                "trace_written": 0,
                "economics_written": 0,
                "observability_written": 0,
                "would_write_trace": 1,
                "would_write_economics": 1,
                "would_write_observability": 1,
                "skipped_existing": 0,
                "skipped_no_state": 0,
                "errors": [{"run_id": "private run", "error": "private traceback must not leak"}],
                "items": [
                    {
                        "run_id": "legacy-run",
                        "action": "error",
                        "trace": True,
                        "economics": True,
                        "observability": True,
                        "error": "private item error must not leak",
                    }
                ],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            runs_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            web_server.backfill_llm_observability = fake_backfill
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/llm-observability-backfill", timeout=5) as response:
                    payload = response.read().decode("utf-8")
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.backfill_llm_observability = original_backfill

        data = json.loads(payload)
        self.assertEqual(data["report"]["error_count"], 1)
        self.assertEqual(data["report"]["errors"], [])
        self.assertNotIn("private traceback", payload)
        self.assertNotIn("private item error", payload)

    def test_repair_resume_backfill_endpoint_previews_then_writes_plans(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "重跑修复项",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(run_dir / "04-results.json", [{"status": "stale"}])
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/repair-resume-backfill", timeout=5) as response:
                    preview_payload = response.read().decode("utf-8")
                    preview = json.loads(preview_payload)
                preview_plan_exists = (run_dir / "12-repair-resume-plan.json").exists()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/repair-resume-backfill",
                    data=json.dumps({"dry_run": False, "force": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    written_payload = response.read().decode("utf-8")
                    written = json.loads(written_payload)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

            plan_exists = (run_dir / "12-repair-resume-plan.json").exists()
            plan_md_exists = (run_dir / "12-repair-resume-plan.md").exists()
            stale_results_exist = (run_dir / "04-results.json").exists()

        self.assertEqual(preview["report"]["would_write"], 1)
        self.assertFalse(preview_plan_exists)
        self.assertEqual(written["report"]["written"], 1)
        self.assertTrue(plan_exists)
        self.assertTrue(plan_md_exists)
        self.assertTrue(stale_results_exist)
        self.assertIn("Repair Resume Backfill", written["markdown"])
        for payload in [preview_payload, written_payload]:
            self.assertNotIn("repair_context", payload)
            self.assertNotIn("prompt_text", payload)
            self.assertNotIn("experiment_manager_resume_actions", payload)
            self.assertNotIn("commands", payload)
            self.assertNotIn("manager_queue", payload)

    def test_repair_resume_backfill_endpoint_returns_public_report(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_backfill = web_server.backfill_repair_resume_plans

        def fake_backfill(runs_dir, *, dry_run=False, force=False, limit=0):
            return {
                "schema_version": 1,
                "generated_at": "test",
                "runs_dir": str(runs_dir),
                "dry_run": dry_run,
                "force": force,
                "limit": limit,
                "scanned_runs": 1,
                "written": 0,
                "would_write": 1,
                "skipped_existing": 0,
                "skipped_no_state": 0,
                "skipped_no_active_queue": 0,
                "errors": [{"run_id": "private run", "error": "private traceback must not leak"}],
                "items": [
                    {
                        "run_id": "legacy-run",
                        "action": "error",
                        "queue_status": "blocked_repair_required",
                        "queue_items": 1,
                        "queue_block": 1,
                        "queue_high": 0,
                        "queue_medium": 0,
                        "plan_status": "ready_to_resume_repair",
                        "can_resume": True,
                        "rerun_from": "experiments",
                        "repair_items": 1,
                        "retrieval_repair_tasks": 0,
                        "artifacts_to_remove": 2,
                        "directories_to_remove": 0,
                        "review_reapproval_required": False,
                        "execution_reapproval_required": True,
                        "applied": False,
                        "repair_context": {"prompt_text": "private prompt must not leak"},
                        "experiment_manager_resume_actions": [{"manager_queue": "private manager queue"}],
                        "commands": ["private command must not leak"],
                        "error": "private item error must not leak",
                    }
                ],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            runs_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            web_server.backfill_repair_resume_plans = fake_backfill
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/repair-resume-backfill", timeout=5) as response:
                    payload = response.read().decode("utf-8")
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.backfill_repair_resume_plans = original_backfill

        data = json.loads(payload)
        self.assertEqual(data["report"]["error_count"], 1)
        self.assertEqual(data["report"]["errors"], [])
        self.assertEqual(data["report"]["items"][0]["artifacts_to_remove"], 2)
        self.assertNotIn("private traceback", payload)
        self.assertNotIn("private item error", payload)
        self.assertNotIn("private prompt", payload)
        self.assertNotIn("private manager queue", payload)
        self.assertNotIn("private command", payload)
        self.assertNotIn("repair_context", payload)
        self.assertNotIn("experiment_manager_resume_actions", payload)
        self.assertNotIn("commands", payload)

    def test_repair_resume_backlog_endpoint_reports_pending_runs_without_private_text(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "private repair action must not leak",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "can_resume": True,
                    "applied": False,
                    "rerun_from": "experiments",
                    "repair_items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "action": "private plan action must not leak",
                        }
                    ],
                    "retrieval_repair_tasks": [],
                    "artifacts_to_remove": [str(run_dir / "04-results.json")],
                    "directories_to_remove": [str(run_dir / "experiments")],
                    "repair_context": {"prompt_text": "private repair context must not leak"},
                    "experiment_manager_resume_actions": [{"manager_queue": "private manager queue must not leak"}],
                    "review_reapproval_required": False,
                    "execution_reapproval_required": True,
                    "commands": [f"PYTHONPATH=src python3 -m research_agent repair-resume {run_dir}"],
                },
            )
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/repair-resume-backlog", timeout=5) as response:
                    payload = response.read().decode("utf-8")
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

        data = json.loads(payload)
        self.assertEqual(data["report"]["status"], "blocked")
        self.assertEqual(data["report"]["summary"]["total"], 1)
        self.assertEqual(data["report"]["summary"]["ready_to_apply"], 1)
        self.assertEqual(data["report"]["summary"]["needs_preconditions"], 0)
        self.assertEqual(data["report"]["items"][0]["run_id"], "legacy-run")
        self.assertEqual(data["report"]["items"][0]["resume_readiness"], "ready_to_apply")
        self.assertEqual(data["report"]["items"][0]["blocking_preconditions"], 0)
        self.assertEqual(data["report"]["items"][0]["artifacts_to_remove"], 1)
        self.assertEqual(data["report"]["items"][0]["directories_to_remove"], 1)
        self.assertEqual(data["report"]["items"][0]["command"], "PYTHONPATH=src python3 -m research_agent repair-resume runs/legacy-run --apply")
        self.assertIn("Repair Resume Backlog", data["markdown"])
        self.assertIn("不删除产物、不批准 gate、不恢复 pipeline、不执行实验", data["markdown"])
        self.assertNotIn(str(root), payload)
        self.assertNotIn("private repair action", payload)
        self.assertNotIn("private plan action", payload)
        self.assertNotIn("private repair context", payload)
        self.assertNotIn("private manager queue", payload)
        self.assertNotIn("repair_context", payload)
        self.assertNotIn("experiment_manager_resume_actions", payload)
        self.assertNotIn("commands", payload)

    def test_benchmark_preview_audits_manifest_without_creating_run_artifacts(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter_dir = root / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "run_benchmark.py").write_text("print('ok')\n", encoding="utf-8")
            manifest = adapter_dir / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "Preview Benchmark",
                        "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "execution_mode": "benchmark",
                    "allowed_commands": "python3",
                    "benchmark_manifests": "adapter/manifest.json",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/benchmark-preview",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

        self.assertEqual(data["report"]["status"], "ready")
        self.assertIn("Benchmark Adapter 审计", data["markdown"])
        self.assertFalse((root / "experiments" / "benchmark-adapters" / "preview-benchmark").exists())

    def test_benchmark_preview_reports_whitelist_blocker(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter_dir = root / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "run_benchmark.py").write_text("print('ok')\n", encoding="utf-8")
            (adapter_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "name": "Blocked Preview",
                        "command": ["python3", "run_benchmark.py"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "execution_mode": "benchmark",
                    "allowed_commands": "pytest",
                    "benchmark_manifests": "adapter/manifest.json",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/benchmark-preview",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

        self.assertEqual(data["report"]["status"], "blocked")
        self.assertTrue(any("allowed_commands" in issue for issue in data["report"]["blocking_issues"]))

    def test_repo_example_manifest_matches_documented_schema_fields(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "examples" / "benchmark-adapter" / "manifest.json").read_text(encoding="utf-8"))
        schema = json.loads((root / "examples" / "benchmark-adapter" / "manifest.schema.json").read_text(encoding="utf-8"))

        for field in schema["required"]:
            self.assertIn(field, manifest)
        self.assertIsInstance(manifest["command"], list)
        self.assertIsInstance(manifest["expected_artifacts"], list)
        self.assertIn(manifest["metrics_path"], manifest["expected_artifacts"])


def _web_lint_manifest(*, min_repeats: int) -> dict[str, object]:
    return {
        "name": "robot-motion-planning",
        "role": "candidate",
        "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
        "metrics_path": "metrics.json",
        "expected_artifacts": ["metrics.json"],
        "expected_metrics": ["success_rate"],
        "metric_schema": {
            "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."}
        },
        "grader": "run_benchmark.py",
        "grader_version": "web-lint-grader-v1",
        "grader_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
        "submission_path": "submission.csv",
        "source_files": ["run_benchmark.py"],
        "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
        "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
        "dataset_version": "ompl-1.6.0",
        "split_name": "web lint split",
        "split_sha256": "8888888888888888888888888888888888888888888888888888888888888888",
        "license": "BSD-3-Clause",
        "baseline": "RRT*",
        "baseline_version": "ompl-1.6.0",
        "citation": "10.1109/MRA.2012.2205651",
        "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat_index.",
        "min_repeats": min_repeats,
    }


if __name__ == "__main__":
    unittest.main()
