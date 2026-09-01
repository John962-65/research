from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import os
import json
import unittest
import zipfile

from research_agent.artifacts import read_json, write_json
from research_agent.config import load_config
from research_agent.gold_run_doctor import (
    GOLD_LAUNCH_MANIFEST_JSON,
    GOLD_LAUNCH_MANIFEST_MD,
    GOLD_RUN_VERIFICATION_JSON,
    GOLD_RUN_VERIFICATION_MD,
    _gold_required_artifact_hash_ready,
    build_gold_environment_lint,
    build_gold_run_doctor,
    build_gold_run_verification_report,
    render_gold_environment_lint_markdown,
    render_gold_launch_manifest_markdown,
    render_gold_run_doctor_markdown,
    render_gold_run_verification_markdown,
    write_gold_run_doctor_artifacts,
    write_gold_run_verification_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class GoldRunDoctorTest(unittest.TestCase):
    def test_gold_environment_lint_reports_missing_server_env_without_values(self) -> None:
        with _env_override(
            OPENAI_BASE_URL=None,
            OPENAI_MODEL=None,
            OPENAI_API_KEY=None,
            RESEARCH_AGENT_CONTACT_EMAIL=None,
            SEMANTIC_SCHOLAR_API_KEY=None,
            OPENALEX_API_KEY=None,
        ):
            report = build_gold_environment_lint(_gold_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml"))
            rendered = render_gold_environment_lint_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["required_ready"])
        self.assertEqual(
            report["missing_required_fields"],
            ["llm_base_url", "llm_model", "llm_api_key", "literature_contact_email"],
        )
        self.assertEqual(report["secret_policy"], "env_only")
        self.assertIn("Gold Environment Lint", rendered)
        self.assertIn("llm_api_key", rendered)
        self.assertNotIn("OPENAI_API_KEY", rendered)

    def test_gold_environment_lint_passes_with_valid_server_env_without_printing_values(self) -> None:
        with _env_override(
            OPENAI_BASE_URL="http://127.0.0.1:8317",
            OPENAI_MODEL="gpt-5.5",
            OPENAI_API_KEY="unit-test-api-token",
            RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
            SEMANTIC_SCHOLAR_API_KEY=None,
            OPENALEX_API_KEY=None,
        ):
            report = build_gold_environment_lint(_gold_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml"))
            rendered = render_gold_environment_lint_markdown(report)

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["required_ready"])
        self.assertEqual(report["missing_required_fields"], [])
        self.assertEqual(report["invalid_required_fields"], [])
        self.assertEqual(report["missing_optional_fields"], ["semantic_scholar_api_key", "openalex_api_key"])
        self.assertEqual(report["required_fields"]["llm_api_key"]["status"], "pass")
        self.assertNotIn("unit-test-api-token", rendered)
        self.assertNotIn("researcher@university.edu", rendered)
        self.assertNotIn("http://127.0.0.1:8317", rendered)

    def test_gold_environment_lint_blocks_target_gateway_mismatch_without_printing_values(self) -> None:
        config = _gold_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
        config = replace(config, llm=replace(config.llm, base_url="http://127.0.0.1:8317", model="gpt-5.5"))
        with _env_override(
            OPENAI_BASE_URL="http://127.0.0.1:9999",
            OPENAI_MODEL="wrong-model",
            OPENAI_API_KEY="unit-test-api-token",
            RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
            SEMANTIC_SCHOLAR_API_KEY=None,
            OPENALEX_API_KEY=None,
        ):
            report = build_gold_environment_lint(config)
            rendered = render_gold_environment_lint_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["required_ready"])
        self.assertEqual(report["expected_mismatch_fields"], ["llm_base_url", "llm_model"])
        self.assertEqual(report["target_environment"]["status"], "mismatch")
        self.assertEqual(report["required_fields"]["llm_base_url"]["status"], "mismatch")
        self.assertEqual(report["required_fields"]["llm_model"]["status"], "mismatch")
        self.assertIn("不匹配", rendered)
        for needle in ["http://127.0.0.1:8317", "http://127.0.0.1:9999", "gpt-5.5", "wrong-model", "unit-test-api-token"]:
            self.assertNotIn(needle, rendered)

    def test_blocks_when_required_gold_run_environment_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL=None,
                OPENAI_MODEL=None,
                OPENAI_API_KEY=None,
                RESEARCH_AGENT_CONTACT_EMAIL=None,
                SEMANTIC_SCHOLAR_API_KEY=None,
                OPENALEX_API_KEY=None,
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        statuses = {item["name"]: item["status"] for item in report["checks"]}
        readiness = report["launch_manifest"]["launch_readiness"]
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(readiness["status"], "blocked")
        self.assertFalse(readiness["can_start_gold_run"])
        self.assertIn("doctor_ready", readiness["blocking_items"])
        self.assertIn("preflight_pass", readiness["blocking_items"])
        self.assertEqual(statuses["llm_model"], "fail")
        self.assertEqual(statuses["llm_api_key"], "fail")
        self.assertEqual(statuses["literature_contact_email"], "fail")
        self.assertEqual(statuses["credential_transport"], "pass")
        self.assertEqual(statuses["benchmark_pack_run"], "pass")
        self.assertEqual(statuses["fulltext_grounding_run"], "pass")
        self.assertEqual({item["id"] for item in report["checks"]}, set(statuses))
        self.assertIn('export OPENAI_BASE_URL="http://127.0.0.1:8317"', rendered)
        self.assertIn('export OPENAI_MODEL="gpt-5.5"', rendered)
        self.assertIn('export OPENAI_API_KEY="<real-key>"', rendered)

    def test_reports_ready_commands_without_printing_secret_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        self.assertEqual(report["status"], "ready")
        launch = report["launch_manifest"]
        self.assertEqual(launch["status"], "ready_to_start")
        self.assertTrue(launch["can_start_gold_run"])
        self.assertEqual(launch["credential_sources"]["llm_api_key"]["source"], "env")
        self.assertEqual(launch["secret_handling"]["direct_secret_fields"], [])
        self.assertEqual(launch["launch_readiness"]["status"], "ready_to_start")
        self.assertTrue(launch["launch_readiness"]["can_start_gold_run"])
        self.assertEqual(launch["launch_readiness"]["blocking_items"], [])
        self.assertEqual(launch["launch_readiness"]["secret_policy"], "env_only")
        self.assertIn("candidate_run_optional", launch["launch_readiness"]["review_items"])
        self.assertEqual(launch["launch_readiness"]["paper_grade_contract"]["literature"], True)
        self.assertEqual(launch["launch_readiness"]["paper_grade_contract"]["benchmark"], True)
        self.assertEqual(launch["launch_readiness"]["paper_grade_contract"]["release_metadata"], True)
        self.assertTrue(launch["literature"]["paper_grade_ready"])
        self.assertTrue(launch["benchmark"]["benchmark_ready"])
        self.assertTrue(launch["release_metadata"]["required_ready"])
        checklist = {item["item"]: item for item in launch["launch_checklist"]}
        self.assertEqual(checklist["paper_grade_literature"]["form_fields"][0], "literature_provider")
        self.assertIn("sources=4/3", checklist["paper_grade_literature"]["evidence"])
        self.assertIn("seeds=11/3", checklist["paper_grade_literature"]["evidence"])
        self.assertIn("doi_url=8/3", checklist["paper_grade_literature"]["evidence"])
        self.assertIn("Literature Preview", checklist["paper_grade_literature"]["next_step"])
        self.assertIn("candidate/baseline/ablation", checklist["benchmark_manifest"]["next_step"])
        self.assertIn("Next step", render_gold_launch_manifest_markdown(launch))
        self.assertEqual({item["name"]: item["status"] for item in report["checks"]}["credential_transport"], "pass")
        self.assertIn('export OPENAI_BASE_URL="http://127.0.0.1:8317"', rendered)
        self.assertIn('export OPENAI_MODEL="gpt-5.5"', rendered)
        self.assertTrue(any(" research_agent status " in command for command in launch["safe_commands"]))
        self.assertTrue(any(" research_agent approve-execution " in command for command in launch["safe_commands"]))
        self.assertIn("--release-code-archive-doi", rendered)
        self.assertIn(f"--config \"{ROOT / 'examples' / 'uci-iris-paper-grade-config.toml'}\"", rendered)
        self.assertIn("Gold Launch Manifest", rendered)
        self.assertIn("Launch Readiness", rendered)
        launch_payload = json.dumps(launch, ensure_ascii=False)
        self.assertNotIn("unit-test-api-token", rendered)
        self.assertNotIn("semantic-secret", rendered)
        self.assertNotIn("openalex-secret", rendered)
        self.assertNotIn("researcher@university.edu", rendered)
        self.assertNotIn("unit-test-api-token", launch_payload)
        self.assertNotIn("semantic-secret", launch_payload)
        self.assertNotIn("openalex-secret", launch_payload)
        self.assertNotIn("researcher@university.edu", launch_payload)

    def test_optional_literature_api_key_warnings_do_not_block_startup_launch(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY=None,
                OPENALEX_API_KEY=None,
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )

        statuses = {item["name"]: item["status"] for item in report["checks"]}
        launch = report["launch_manifest"]
        readiness = launch["launch_readiness"]

        self.assertEqual(report["status"], "warn")
        self.assertEqual(statuses["semantic_scholar_key"], "warn")
        self.assertEqual(statuses["openalex_key"], "warn")
        self.assertEqual(statuses["preflight:overall"], "warn")
        self.assertEqual(launch["status"], "ready_to_start")
        self.assertTrue(launch["can_start_gold_run"])
        self.assertEqual(launch["launch_review_checks"], [])
        self.assertEqual(
            launch["nonblocking_warn_checks"],
            ["semantic_scholar_key", "openalex_key", "preflight:overall"],
        )
        self.assertEqual(readiness["status"], "ready_to_start")
        self.assertTrue(readiness["can_start_gold_run"])
        self.assertEqual(readiness["blocking_items"], [])
        self.assertNotIn("doctor_ready", readiness["review_items"])
        self.assertNotIn("preflight_pass", readiness["blocking_items"])

    def test_configless_launch_command_carries_paper_grade_inputs_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config = _gold_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=config,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        self.assertEqual(report["status"], "ready")
        launch_payload = json.dumps(report["launch_manifest"], ensure_ascii=False)
        run_command = next(item for item in report["commands"] if " research_agent run " in item)
        self.assertNotIn("--config examples/uci-iris-paper-grade-config.toml", run_command)
        self.assertIn("--paper-grade", run_command)
        self.assertIn('--literature-provider "online"', run_command)
        self.assertIn('--literature-sources "semantic_scholar,openalex,arxiv,crossref"', run_command)
        self.assertIn("--seed-paper", run_command)
        self.assertIn("--extra-search-query", run_command)
        self.assertIn("--fulltext-path", run_command)
        self.assertIn('--execution-mode "benchmark"', run_command)
        self.assertIn('--execution-repeats "3"', run_command)
        self.assertIn("--benchmark-manifest", run_command)
        self.assertIn("--release-code-archive-doi", run_command)
        self.assertIn('--out "runs/iris-classification-benchmark-smoke-gold-run"', run_command)
        self.assertNotIn("unit-test-api-token", rendered)
        self.assertNotIn("semantic-secret", rendered)
        self.assertNotIn("openalex-secret", rendered)
        self.assertNotIn("researcher@university.edu", rendered)
        self.assertNotIn("unit-test-api-token", launch_payload)
        self.assertNotIn("semantic-secret", launch_payload)
        self.assertNotIn("openalex-secret", launch_payload)
        self.assertNotIn("researcher@university.edu", launch_payload)

    def test_launch_literature_uses_configured_paper_grade_thresholds(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                config = _gold_config(config_path)
                config = replace(config, literature=replace(config.literature, sources=["openalex", "arxiv"]))
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=config,
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )

        launch = report["launch_manifest"]
        checklist = {item["item"]: item for item in launch["launch_checklist"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(launch["status"], "blocked")
        self.assertFalse(launch["literature"]["paper_grade_ready"])
        self.assertEqual(launch["literature"]["source_count"], 2)
        self.assertEqual(launch["literature"]["min_literature_sources"], 3)
        self.assertIn("paper_grade_literature", launch["launch_readiness"]["blocking_items"])
        self.assertEqual(checklist["paper_grade_literature"]["status"], "block")
        self.assertIn("sources=2/3", checklist["paper_grade_literature"]["evidence"])
        self.assertIn("doi_url=8/3", checklist["paper_grade_literature"]["evidence"])

    def test_launch_benchmark_uses_configured_paper_grade_thresholds(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                config = _gold_config(config_path)
                config = replace(
                    config,
                    paper_grade=replace(config.paper_grade, min_benchmark_roles=9, min_execution_repeats=5),
                )
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=config,
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )

        launch = report["launch_manifest"]
        checklist = {item["item"]: item for item in launch["launch_checklist"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(launch["status"], "blocked")
        self.assertFalse(launch["benchmark"]["benchmark_ready"])
        self.assertEqual(launch["benchmark"]["benchmark_manifest_paths"], 8)
        self.assertEqual(launch["benchmark"]["min_benchmark_roles"], 9)
        self.assertEqual(launch["benchmark"]["execution_repeats"], 3)
        self.assertEqual(launch["benchmark"]["min_execution_repeats"], 5)
        self.assertIn("benchmark_manifest", launch["launch_readiness"]["blocking_items"])
        self.assertEqual(checklist["benchmark_manifest"]["status"], "block")
        self.assertIn("manifests=8/9", checklist["benchmark_manifest"]["evidence"])
        self.assertIn("repeats=3/5", checklist["benchmark_manifest"]["evidence"])
        self.assertIn("repeats >= 5", checklist["benchmark_manifest"]["next_step"])
        self.assertIn("at least 9", checklist["benchmark_manifest"]["next_step"])

    def test_writes_standalone_launch_manifest_artifacts_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            doctor_dir = root / "doctor"
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = write_gold_run_doctor_artifacts(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    out_dir=doctor_dir,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
            launch = read_json(doctor_dir / GOLD_LAUNCH_MANIFEST_JSON)
            launch_markdown = (doctor_dir / GOLD_LAUNCH_MANIFEST_MD).read_text(encoding="utf-8")
            rendered = render_gold_launch_manifest_markdown(report["launch_manifest"])

        self.assertEqual(launch["status"], "ready_to_start")
        self.assertTrue(launch["can_start_gold_run"])
        self.assertEqual(launch["secret_handling"]["direct_secret_fields"], [])
        self.assertIn("# Gold Launch Manifest", launch_markdown)
        self.assertIn("ready_to_start", rendered)
        self.assertTrue(any(" research_agent status " in command for command in launch["safe_commands"]))
        self.assertTrue(any(" research_agent approve-execution " in command for command in launch["safe_commands"]))
        launch_payload = json.dumps(launch, ensure_ascii=False) + launch_markdown
        self.assertNotIn("unit-test-api-token", launch_payload)
        self.assertNotIn("semantic-secret", launch_payload)
        self.assertNotIn("openalex-secret", launch_payload)
        self.assertNotIn("researcher@university.edu", launch_payload)

    def test_blocks_scaffold_release_metadata_for_gold_run(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=load_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["gold_release_metadata"]["status"], "fail")
        self.assertIn("release_code_archive_doi", checks["gold_release_metadata"]["detail"])
        self.assertIn("placeholder", checks["gold_release_metadata"]["detail"])
        self.assertNotIn("unit-test-api-token", rendered)

    def test_candidate_run_dir_can_confirm_gold_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate")
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "ready")
        self.assertEqual(checks["candidate_gold_run"]["status"], "pass")
        self.assertIn("traceability=pass:0/0", checks["candidate_gold_run"]["detail"])
        self.assertIn("package=ready_for_human_submission_upload", checks["candidate_gold_run"]["detail"])
        self.assertIn("economics=pass:0", checks["candidate_gold_run"]["detail"])
        self.assertIn("scorecard=ready_for_human_submission_upload", checks["candidate_gold_run"]["detail"])
        self.assertIn("integrity=pass", checks["candidate_gold_run"]["detail"])
        self.assertIn("final=ready_for_submission_upload:0", checks["candidate_gold_run"]["detail"])

    def test_candidate_run_dir_blocks_stale_final_handoff_when_package_source_is_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate")
            write_json(candidate_dir / "11-submission-package.json", {"status": "blocked", "blocking_issues": ["missing required file"]})
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["candidate_gold_run"]["status"], "fail")
        self.assertIn("package=blocked", checks["candidate_gold_run"]["detail"])
        self.assertIn("submission package", checks["candidate_gold_run"]["action"])

    def test_candidate_run_dir_blocks_upload_ready_handoff_when_package_still_needs_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate", package_status="needs_human_submission_review")
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["candidate_gold_run"]["status"], "fail")
        self.assertIn("package=needs_human_submission_review:0", checks["candidate_gold_run"]["detail"])
        self.assertIn("final=ready_for_submission_upload:0", checks["candidate_gold_run"]["detail"])

    def test_candidate_run_dir_action_points_to_blocked_scorecard_source(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate", scorecard_status="blocked", scorecard_blockers=["score below threshold"])
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["candidate_gold_run"]["status"], "fail")
        self.assertIn("scorecard=blocked:1", checks["candidate_gold_run"]["detail"])
        self.assertIn("13-research-scorecard.json", checks["candidate_gold_run"]["action"])

    def test_candidate_run_dir_blocks_incomplete_release_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate")
            write_json(
                candidate_dir / "10-release-metadata.json",
                {"status": "needs_release_metadata", "blocking_issues": [], "manual_tasks": ["补代码归档 DOI"]},
            )
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        check = {item["name"]: item for item in report["checks"]}["candidate_gold_run"]
        repair_plan = check["repair_plan"]

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(check["status"], "fail")
        self.assertIn("release=needs_release_metadata:0/1", check["detail"])
        self.assertIn("10-release-metadata.json", check["action"])
        self.assertTrue(any(item["id"] == "release_metadata" for item in repair_plan))

    def test_candidate_run_dir_blocks_failed_claim_traceability(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate")
            write_json(
                candidate_dir / "10-claim-traceability.json",
                {
                    "status": "block",
                    "traceability_score": 0.4,
                    "blocked_claims": 1,
                    "review_claims": 0,
                    "blocking_issues": ["one empirical claim lacks a matched result reference"],
                    "manual_tasks": [],
                },
            )
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        check = {item["name"]: item for item in report["checks"]}["candidate_gold_run"]
        repair_plan = check["repair_plan"]

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(check["status"], "fail")
        self.assertIn("traceability=block:1/1", check["detail"])
        self.assertIn("10-claim-traceability.json", check["action"])
        self.assertTrue(any(item["id"] == "claim_traceability" for item in repair_plan))

    def test_candidate_run_dir_reports_structured_repair_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(
                root / "candidate",
                package_status="blocked",
                scorecard_status="blocked",
                scorecard_blockers=["score below threshold"],
                final_handoff_status="blocked",
            )
            write_json(candidate_dir / "12-repair-queue.json", {"status": "blocked_repair_required", "summary": {"total": 2, "block": 2}})
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        check = {item["name"]: item for item in report["checks"]}["candidate_gold_run"]
        repair_plan = check["repair_plan"]
        ids = {item["id"] for item in repair_plan}

        self.assertEqual(check["status"], "fail")
        self.assertIn("submission_package", ids)
        self.assertIn("research_scorecard", ids)
        self.assertIn("final_handoff", ids)
        self.assertIn("repair_queue_blockers", ids)
        self.assertTrue(all("target_artifacts" in item for item in repair_plan))
        self.assertIn("Candidate Repair Plan", rendered)
        self.assertIn("13-research-scorecard.json", rendered)
        self.assertNotIn("unit-test-api-token", rendered)
        self.assertNotIn("researcher@university.edu", rendered)

    def test_doctor_can_write_candidate_repair_resume_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate", package_status="blocked")
            doctor_dir = root / "doctor"
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = write_gold_run_doctor_artifacts(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    out_dir=doctor_dir,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                    write_candidate_repair_resume_plan=True,
                )
                rendered = render_gold_run_doctor_markdown(report)
            plan = read_json(candidate_dir / "12-repair-resume-plan.json")
            plan_md_exists = (candidate_dir / "12-repair-resume-plan.md").exists()

        summary = report["candidate_repair_resume_plan"]

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(summary["status"], "written")
        self.assertTrue(summary["can_resume"])
        self.assertEqual(plan["repair_plan_sources"], ["12-repair-queue", "gold-run-doctor"])
        self.assertEqual(plan["doctor_report_path"], str(doctor_dir / "00-gold-run-doctor.json"))
        self.assertTrue(any(item["task_id"] == "gold-doctor:submission_package" for item in plan["repair_items"]))
        self.assertIn("--gold-run-doctor-report", plan["commands"][0])
        self.assertTrue(plan_md_exists)
        self.assertIn("Candidate Repair Resume Plan", rendered)

    def test_gold_run_verification_reports_ready_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["gold_contract_ready"])
        self.assertEqual(report["missing_artifacts"], [])
        self.assertIn("10-claim-traceability.json", report["required_artifacts"])
        self.assertIn("10-final-readiness.json", report["required_artifacts"])
        self.assertIn("11-submission-package.zip", report["required_artifacts"])
        self.assertEqual(len(report["artifact_hashes"]), len(report["required_artifacts"]))
        self.assertRegex(report["artifact_hashes"]["10-claim-consistency.json"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(all(item["size_bytes"] > 0 for item in report["artifact_hashes"].values()))
        self.assertGreater(report["artifact_hashes"]["11-submission-package.zip"]["size_bytes"], 0)
        self.assertEqual(report["manifest_inventory"]["status"], "pass")
        self.assertEqual(report["secret_scan"]["status"], "pass")
        self.assertEqual(report["secret_scan"]["finding_count"], 0)
        self.assertEqual(report["check"]["status"], "pass")
        self.assertEqual(report["contract_evidence"]["final_zip_state"], "valid")
        self.assertTrue(report["contract_evidence"]["final_handoff_package_zip_exists"])
        self.assertTrue(report["contract_evidence"]["final_handoff_package_zip_valid"])
        self.assertTrue(report["contract_evidence"]["audit_contracts_ready"])
        self.assertEqual(report["contract_evidence"]["audit_contract_ready_count"], 7)
        self.assertEqual(report["contract_evidence"]["audit_contract_total"], 7)
        self.assertEqual(report["contract_evidence"]["audit_contract_blocking_issues"], 0)
        self.assertEqual(report["contract_evidence"]["audit_contract_manual_tasks"], 0)
        self.assertEqual(report["contract_evidence"]["audit_contracts"]["llm_trace"]["status"], "pass")
        self.assertIn("final_zip=valid", report["check"]["detail"])
        self.assertEqual(report["repair_plan"], [])
        self.assertIn("Gold Run Verification", rendered)
        self.assertIn("Gold contract ready：是", rendered)
        self.assertIn("final_zip：valid", rendered)
        self.assertIn("audit_contracts：7/7 ready", rendered)
        self.assertIn("Artifact Hashes", rendered)
        self.assertIn("记录：23/23", rendered)
        self.assertIn("Manifest Inventory", rendered)
        self.assertIn("Secret Scan", rendered)

    def test_gold_run_verification_rejects_boolean_audit_contract_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass", "blocking_issues": False, "manual_tasks": []})
            _write_test_run_manifest(run_dir)

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertFalse(report["contract_evidence"]["audit_contracts_ready"])
        self.assertEqual(report["contract_evidence"]["audit_contract_ready_count"], 6)
        self.assertEqual(report["contract_evidence"]["audit_contract_blocking_issues"], 1)
        self.assertFalse(report["contract_evidence"]["audit_contracts"]["llm_trace"]["ready"])

    def test_gold_required_artifact_hash_ready_rejects_boolean_size(self) -> None:
        self.assertFalse(_gold_required_artifact_hash_ready({"sha256": "0" * 64, "size_bytes": True}))
        self.assertTrue(_gold_required_artifact_hash_ready({"sha256": "0" * 64, "size_bytes": 1}))

    def test_gold_run_verification_requires_manifest_inventory_records_required_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            manifest["artifacts"] = [item for item in manifest["artifacts"] if item.get("path") != "10-claim-consistency.json"]
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["missing_artifacts"], [])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertIn("10-claim-consistency.json", report["manifest_inventory"]["missing_required_artifacts"])
        self.assertTrue(any(item["id"] == "manifest_inventory" for item in report["repair_plan"]))
        self.assertIn("Manifest Inventory", rendered)

    def test_gold_run_verification_rejects_manifest_inventory_hash_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            for item in manifest["artifacts"]:
                if item.get("path") == "10-claim-consistency.json":
                    item["sha256"] = "0" * 64
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertIn("10-claim-consistency.json", report["manifest_inventory"]["hash_mismatches"])
        self.assertTrue(any(item["id"] == "manifest_inventory" and "10-claim-consistency.json" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_manifest_inventory_size_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            for item in manifest["artifacts"]:
                if item.get("path") == "10-claim-consistency.json":
                    item["bytes"] = int(item.get("bytes") or 0) + 1
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertIn("10-claim-consistency.json", report["manifest_inventory"]["size_mismatches"])
        self.assertTrue(any(item["id"] == "manifest_inventory" and "10-claim-consistency.json" in item["target_artifacts"] for item in report["repair_plan"]))
        self.assertIn("Size 不一致：1", rendered)

    def test_gold_run_verification_requires_manifest_inventory_integer_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            for item in manifest["artifacts"]:
                if item.get("path") == "10-claim-consistency.json":
                    item["bytes"] = str(item.get("bytes"))
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertIn("10-claim-consistency.json", report["manifest_inventory"]["size_mismatches"])
        self.assertTrue(any(item["id"] == "manifest_inventory" and "10-claim-consistency.json" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_requires_manifest_inventory_bytes_field(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            for item in manifest["artifacts"]:
                if item.get("path") == "10-claim-consistency.json":
                    item["size_bytes"] = item.pop("bytes")
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertIn("10-claim-consistency.json", report["manifest_inventory"]["size_mismatches"])
        self.assertTrue(any(item["id"] == "manifest_inventory" and "10-claim-consistency.json" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_duplicate_manifest_inventory_records(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            original = next(item for item in manifest["artifacts"] if item.get("path") == "10-claim-consistency.json")
            manifest["artifacts"].append(dict(original))
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertIn("10-claim-consistency.json", report["manifest_inventory"]["duplicate_required_artifacts"])
        self.assertTrue(any(item["id"] == "manifest_inventory" and "10-claim-consistency.json" in item["target_artifacts"] for item in report["repair_plan"]))
        self.assertIn("重复记录：1", rendered)

    def test_gold_run_verification_rejects_unsafe_manifest_inventory_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            manifest_path = run_dir / "run-manifest.json"
            manifest = read_json(manifest_path)
            manifest["artifacts"].append({"path": "../outside/private-result.json", "bytes": 1, "sha256": "0" * 64})
            write_json(manifest_path, manifest)

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["manifest_inventory"]["status"], "blocked")
        self.assertEqual(report["manifest_inventory"]["unsafe_artifact_paths"], [{"path": "outside/private-result.json", "issue": "parent_reference"}])
        self.assertTrue(any(item["id"] == "manifest_inventory" and "outside/private-result.json" in item["target_artifacts"] for item in report["repair_plan"]))
        self.assertIn("Unsafe path：1", rendered)
        self.assertNotIn("../outside/private-result.json", rendered)

    def test_gold_run_verification_rejects_required_artifact_symlink(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_candidate_run(root / "candidate")
            artifact = run_dir / "10-claim-consistency.json"
            external = root / "outside-claim-consistency.json"
            external.write_bytes(artifact.read_bytes())
            artifact.unlink()
            artifact.symlink_to(external)

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["missing_artifacts"], [])
        self.assertEqual(report["artifact_safety"]["status"], "blocked")
        self.assertEqual(report["unsafe_artifacts"], [{"path": "10-claim-consistency.json", "issue": "symlink"}])
        self.assertNotIn("10-claim-consistency.json", report["artifact_hashes"])
        self.assertTrue(any(item["id"] == "required_artifact_safety" and "10-claim-consistency.json" in item["target_artifacts"] for item in report["repair_plan"]))
        self.assertIn("Required Artifact Safety", rendered)
        self.assertIn("symlink", rendered)
        self.assertNotIn(str(external), rendered)

    def test_gold_run_verification_blocks_secret_like_run_artifacts_without_echoing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            key_name = "OPENAI" + "_API_KEY"
            token = "sk" + "-unit-test-secret\n"
            (run_dir / "leaky-log.txt").write_text(f"{key_name}={token}", encoding="utf-8")

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["check"]["status"], "pass")
        self.assertEqual(report["secret_scan"]["status"], "blocked")
        self.assertGreaterEqual(report["secret_scan"]["finding_count"], 1)
        self.assertTrue(any(item["path"] == "leaky-log.txt" for item in report["secret_scan"]["findings"]))
        self.assertIn("leaky-log.txt", rendered)
        self.assertIn("env_api_key_assignment", rendered)
        self.assertNotIn("sk-unit-test-secret", rendered)

    def test_gold_run_secret_scan_blocks_symlink_without_reading_external_target(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _write_candidate_run(root / "candidate")
            key_name = "OPENAI" + "_API_KEY"
            token = "sk" + "-external-symlink-secret\n"
            external = root / "external-secret.log"
            external.write_text(f"{key_name}={token}", encoding="utf-8")
            (run_dir / "linked-secret.log").symlink_to(external)

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["secret_scan"]["status"], "blocked")
        self.assertTrue(any(item["path"] == "linked-secret.log" and item["rule"] == "unsafe_file_reference" for item in report["secret_scan"]["findings"]))
        self.assertFalse(any(item["rule"] == "env_api_key_assignment" and item["path"] == "linked-secret.log" for item in report["secret_scan"]["findings"]))
        self.assertIn("linked-secret.log", rendered)
        self.assertIn("unsafe_file_reference", rendered)
        self.assertNotIn(str(external), rendered)
        self.assertNotIn("sk" + "-external-symlink-secret", rendered)

    def test_gold_run_verification_scans_submission_zip_text_entries_for_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            key_name = "OPENAI" + "_API_KEY"
            token = "sk" + "-zip-test-secret\n"
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "a") as archive:
                archive.writestr("submission-package/private/leaky-log.txt", f"{key_name}={token}")

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["check"]["status"], "pass")
        self.assertEqual(report["missing_artifacts"], [])
        self.assertEqual(report["secret_scan"]["status"], "blocked")
        self.assertGreaterEqual(report["secret_scan"]["finding_count"], 1)
        self.assertTrue(any(item["path"] == "11-submission-package.zip!submission-package/private/leaky-log.txt" for item in report["secret_scan"]["findings"]))
        self.assertIn("11-submission-package.zip!submission-package/private/leaky-log.txt", rendered)
        self.assertIn("env_api_key_assignment", rendered)
        self.assertNotIn("sk-zip-test-secret", rendered)

    def test_gold_run_verification_scans_dotenv_artifacts_for_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            key_name = "OPENAI" + "_API_KEY"
            token = "sk" + "-dotenv-test-secret\n"
            (run_dir / ".env").write_text(f"{key_name}={token}", encoding="utf-8")

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["secret_scan"]["status"], "blocked")
        self.assertTrue(any(item["path"] == ".env" for item in report["secret_scan"]["findings"]))
        self.assertIn(".env", rendered)
        self.assertNotIn("sk-dotenv-test-secret", rendered)

    def test_gold_run_verification_scans_submission_zip_dotenv_entries_for_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            token = "sk" + "-zip-dotenv-test-secret\n"
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "a") as archive:
                archive.writestr("submission-package/.env.local", f"Authorization: Bearer {token}")

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["secret_scan"]["status"], "blocked")
        self.assertTrue(any(item["path"] == "11-submission-package.zip!submission-package/.env.local" for item in report["secret_scan"]["findings"]))
        self.assertIn("auth_header_token", rendered)
        self.assertNotIn("sk" + "-zip-dotenv-test-secret", rendered)

    def test_gold_run_verification_requires_provenance_artifacts(self) -> None:
        for artifact in ["run-manifest.json", "run-llm-ledger.json", "13-llm-runtime-contract.json", "13-agent-observability-audit.json"]:
            with self.subTest(artifact=artifact), TemporaryDirectory() as tmp:
                run_dir = _write_candidate_run(Path(tmp) / "candidate")
                (run_dir / artifact).unlink()

                report = build_gold_run_verification_report(run_dir)

            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["gold_contract_ready"])
            self.assertIn(artifact, report["required_artifacts"])
            self.assertIn(artifact, report["missing_artifacts"])
            self.assertEqual(report["check"]["status"], "fail")
            self.assertTrue(any(item["id"] == "missing_candidate_artifacts" and artifact in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_requires_claim_traceability_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            (run_dir / "10-claim-traceability.json").unlink()

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("10-claim-traceability.json", report["missing_artifacts"])
        self.assertTrue(any(item["id"] == "missing_candidate_artifacts" for item in report["repair_plan"]))
        self.assertIn("10-claim-traceability.json", rendered)

    def test_gold_run_verification_requires_run_economics_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            (run_dir / "13-run-economics-audit.json").unlink()

            report = build_gold_run_verification_report(run_dir)
            rendered = render_gold_run_verification_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("13-run-economics-audit.json", report["required_artifacts"])
        self.assertIn("13-run-economics-audit.json", report["missing_artifacts"])
        self.assertTrue(any(item["id"] == "missing_candidate_artifacts" for item in report["repair_plan"]))
        self.assertIn("13-run-economics-audit.json", rendered)

    def test_gold_run_verification_requires_final_readiness_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            (run_dir / "10-final-readiness.json").unlink()

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("10-final-readiness.json", report["required_artifacts"])
        self.assertIn("10-final-readiness.json", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any(item["id"] == "missing_candidate_artifacts" for item in report["repair_plan"]))

    def test_gold_run_verification_requires_submission_package_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            (run_dir / "11-submission-package.zip").unlink()

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["required_artifacts"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_invalid_submission_package_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            (run_dir / "11-submission-package.zip").write_text("not a zip archive", encoding="utf-8")

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_final_handoff_invalid_zip_marker(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "package_zip_exists": True,
                    "package_zip_valid": False,
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["missing_artifacts"], [])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertIn("final_zip=invalid", report["check"]["detail"])
        self.assertTrue(any(item["id"] == "final_handoff_zip" for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_final_handoff_unknown_zip_marker(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["missing_artifacts"], [])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertIn("final_zip=unknown", report["check"]["detail"])
        self.assertTrue(any(item["id"] == "final_handoff_zip" for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_unsafe_submission_package_zip_entry_names(self) -> None:
        unsafe_names = [
            "submission-package/../private.txt",
            "/submission-package/private.txt",
            "C:/submission-package/private.txt",
            "submission-package\\private.txt",
        ]
        for unsafe_name in unsafe_names:
            with self.subTest(unsafe_name=unsafe_name), TemporaryDirectory() as tmp:
                run_dir = _write_candidate_run(Path(tmp) / "candidate")
                with zipfile.ZipFile(run_dir / "11-submission-package.zip", "a") as archive:
                    archive.writestr(unsafe_name, "unsafe package entry")

                report = build_gold_run_verification_report(run_dir)

            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["gold_contract_ready"])
            self.assertIn("11-submission-package.zip", report["missing_artifacts"])
            self.assertEqual(report["check"]["status"], "fail")
            self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_requires_submission_package_zip_manifest_and_checklist(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
                archive.writestr("README.txt", "not the generated submission package structure")

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_requires_structured_submission_package_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
                archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
                archive.writestr("submission-package/package-manifest.json", "{}")

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_requires_manifest_listed_files_in_submission_package_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
                archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
                archive.writestr(
                    "submission-package/package-manifest.json",
                    json.dumps(
                        {
                            "status": "ready_for_human_submission_upload",
                            "files": [{"package_path": "submission-package/paper/revised-paper.md"}],
                        }
                    ),
                )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_unsafe_manifest_listed_package_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
                archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
                archive.writestr(
                    "submission-package/package-manifest.json",
                    json.dumps(
                        {
                            "status": "ready_for_human_submission_upload",
                            "files": [{"package_path": "../outside.txt", "status": "pass"}],
                        }
                    ),
                )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_duplicate_manifest_listed_package_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
                archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
                archive.writestr(
                    "submission-package/package-manifest.json",
                    json.dumps(
                        {
                            "status": "ready_for_human_submission_upload",
                            "files": [
                                {"package_path": "submission-package/CHECKLIST.md", "status": "pass"},
                                {"package_path": "submission-package/CHECKLIST.md", "status": "optional_missing"},
                            ],
                        }
                    ),
                )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_rejects_malformed_manifest_file_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
                archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
                archive.writestr(
                    "submission-package/package-manifest.json",
                    json.dumps(
                        {
                            "status": "ready_for_human_submission_upload",
                            "files": [{"package_path": "submission-package/CHECKLIST.md", "status": "pass", "required": "true"}],
                        }
                    ),
                )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertIn("11-submission-package.zip", report["missing_artifacts"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertTrue(any("11-submission-package.zip" in item["target_artifacts"] for item in report["repair_plan"]))

    def test_gold_run_verification_blocks_upload_ready_without_submission_check_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_human_polish", "unsupported_after": 0, "blocking_issues": []})

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertIn("final_readiness=ready_for_human_polish:0/0", report["check"]["detail"])
        self.assertTrue(any(item["id"] == "final_readiness" for item in report["repair_plan"]))

    def test_gold_run_verification_blocks_failed_run_economics(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate")
            write_json(
                run_dir / "13-run-economics-audit.json",
                {"status": "block", "summary": {"input_tokens_estimated": 100}, "blocking_issues": ["ledger missing"], "manual_tasks": [], "warnings": []},
            )

            report = build_gold_run_verification_report(run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["gold_contract_ready"])
        self.assertEqual(report["check"]["status"], "fail")
        self.assertIn("economics=block:1", report["check"]["detail"])
        self.assertTrue(any(item["id"] == "run_economics" for item in report["repair_plan"]))

    def test_gold_run_verification_requires_provenance_audits_to_pass(self) -> None:
        cases = [
            (
                "13-llm-trace-audit.json",
                {"status": "warn", "blocking_issues": [], "manual_tasks": ["核对 missing optional stage"]},
                "llm_trace=warn:0/1",
                "llm_trace_audit",
            ),
            (
                "13-llm-runtime-contract.json",
                {"status": "review_required", "blocking_issues": [], "manual_tasks": ["配置 token 单价"]},
                "llm_runtime=review_required:0/1",
                "llm_runtime_contract",
            ),
            (
                "13-run-economics-audit.json",
                {"status": "pass", "blocking_issues": [], "manual_tasks": ["人工确认恢复链路"], "warnings": []},
                "economics=pass:0/1",
                "run_economics",
            ),
            (
                "13-agent-observability-audit.json",
                {"status": "review_required", "blocking_issues": [], "manual_tasks": ["补 manifest timestamps"]},
                "agent_observability=review_required:0/1",
                "agent_observability",
            ),
            (
                "13-llm-observability-summary.json",
                {"status": "review_required", "blocking_issues": [], "manual_tasks": ["核对预算压力"]},
                "llm_observability=review_required:0/1",
                "llm_observability_summary",
            ),
            (
                "13-agent-stage-contract.json",
                {"status": "needs_human_review", "blocking_issues": [], "manual_tasks": ["人工关闭 release contract"]},
                "stage_contract=needs_human_review:0/1",
                "agent_stage_contract",
            ),
            (
                "13-agent-trajectory.json",
                {"status": "warn", "blocking_issues": [], "manual_tasks": ["补 trajectory event"]},
                "trajectory=warn:0/1",
                "agent_trajectory",
            ),
        ]
        for artifact, payload, detail_marker, repair_id in cases:
            with self.subTest(artifact=artifact), TemporaryDirectory() as tmp:
                run_dir = _write_candidate_run(Path(tmp) / "candidate")
                write_json(run_dir / artifact, payload)
                _write_test_run_manifest(run_dir)

                report = build_gold_run_verification_report(run_dir)

            self.assertEqual(report["status"], "blocked")
            self.assertFalse(report["gold_contract_ready"])
            self.assertEqual(report["manifest_inventory"]["status"], "pass")
            self.assertEqual(report["check"]["status"], "fail")
            self.assertIn(detail_marker, report["check"]["detail"])
            self.assertTrue(any(item["id"] == repair_id for item in report["repair_plan"]))

    def test_gold_run_verification_writes_artifacts_and_repair_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _write_candidate_run(Path(tmp) / "candidate", package_status="blocked")

            report = write_gold_run_verification_artifacts(run_dir)
            rendered = (run_dir / GOLD_RUN_VERIFICATION_MD).read_text(encoding="utf-8")
            payload = read_json(run_dir / GOLD_RUN_VERIFICATION_JSON)
            json_exists = (run_dir / GOLD_RUN_VERIFICATION_JSON).exists()
            md_exists = (run_dir / GOLD_RUN_VERIFICATION_MD).exists()

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any(item.get("id") == "submission_package" for item in report["repair_plan"]))
        self.assertTrue(json_exists)
        self.assertTrue(md_exists)
        self.assertIn("submission_package", rendered)
        self.assertNotIn("unit-test-api-token", rendered)
        self.assertNotIn("researcher@university.edu", rendered)

    def test_candidate_run_dir_allows_human_handoff_with_package_review_remaining(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(
                root / "candidate",
                package_status="needs_human_submission_review",
                final_handoff_status="ready_for_human_handoff",
            )
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "ready")
        self.assertEqual(checks["candidate_gold_run"]["status"], "pass")
        self.assertIn("final=ready_for_human_handoff:0", checks["candidate_gold_run"]["detail"])

    def test_candidate_run_dir_allows_human_handoff_with_soft_audit_review_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(
                root / "candidate",
                package_status="needs_human_submission_review",
                scorecard_status="needs_human_work",
                final_handoff_status="ready_for_human_handoff",
            )
            write_json(candidate_dir / "13-llm-runtime-contract.json", {"status": "review_required", "blocking_issues": [], "manual_tasks": ["确认 unlimited budget。"]})
            write_json(candidate_dir / "13-agent-stage-contract.json", {"status": "needs_human_review", "blocking_issues": [], "manual_tasks": ["人工 polish。"]})
            write_json(candidate_dir / "13-agent-trajectory.json", {"status": "warn", "blocking_issues": [], "manual_tasks": ["人工复核轨迹。"]})
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        check = {item["name"]: item for item in report["checks"]}["candidate_gold_run"]
        evidence = check["contract_evidence"]

        self.assertEqual(report["status"], "ready")
        self.assertEqual(check["status"], "pass")
        self.assertEqual(evidence["audit_contract_policy"], "human_handoff")
        self.assertTrue(evidence["audit_contracts_ready"])
        self.assertGreater(evidence["audit_contract_manual_tasks"], 0)
        self.assertFalse(evidence["audit_contracts"]["llm_runtime"]["strict_ready"])

    def test_candidate_run_dir_blocks_unbounded_negative_or_neutral_claims(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate", claim_boundary_severity="superiority_claim_risk")
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["candidate_gold_run"]["status"], "fail")
        self.assertIn("boundary=superiority_claim_risk", checks["candidate_gold_run"]["detail"])
        self.assertIn("no-superiority boundary", checks["candidate_gold_run"]["action"])

    def test_candidate_run_dir_requires_benchmark_boundary_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            candidate_dir = _write_candidate_run(root / "candidate")
            benchmark = {
                "status": "warn",
                "evidence_grade": "real_benchmark",
                "adapter_paper_grade_status": "ready",
                "adapter_paper_grade_issues": [],
                "blocking_issues": [],
                "manual_tasks": [],
            }
            write_json(candidate_dir / "04-benchmark-evidence-audit.json", benchmark)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    candidate_run_dir=candidate_dir,
                )

        check = {item["name"]: item for item in report["checks"]}["candidate_gold_run"]
        repair_plan = check["repair_plan"]

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(check["status"], "fail")
        self.assertIn("boundary=-", check["detail"])
        self.assertIn("statistical_outcome", check["action"])
        self.assertTrue(any(item["id"] == "benchmark_evidence_metadata" for item in repair_plan))

    def test_config_credentials_are_marked_without_printing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            config = _gold_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
            config = replace(config, llm=replace(config.llm, base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="config-api-token"))
            config = replace(
                config,
                literature=replace(
                    config.literature,
                    contact_email="researcher@university.edu",
                    semantic_scholar_api_key="semantic-config-secret",
                    openalex_api_key="openalex-config-secret",
                ),
            )
            with _env_override(
                OPENAI_BASE_URL=None,
                OPENAI_MODEL=None,
                OPENAI_API_KEY=None,
                RESEARCH_AGENT_CONTACT_EMAIL=None,
                SEMANTIC_SCHOLAR_API_KEY=None,
                OPENALEX_API_KEY=None,
            ):
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=config,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        details = {item["name"]: item["detail"] for item in report["checks"]}
        statuses = {item["name"]: item["status"] for item in report["checks"]}
        self.assertEqual(report["status"], "warn")
        self.assertEqual(details["llm_api_key"], "config=set")
        self.assertEqual(details["literature_contact_email"], "config=set")
        self.assertEqual(details["semantic_scholar_key"], "config=set")
        self.assertEqual(details["openalex_key"], "config=set")
        self.assertEqual(statuses["credential_transport"], "warn")
        launch = report["launch_manifest"]
        self.assertEqual(launch["status"], "needs_review")
        self.assertFalse(launch["can_start_gold_run"])
        self.assertEqual(launch["launch_readiness"]["status"], "needs_review")
        self.assertEqual(launch["launch_readiness"]["secret_policy"], "move_secrets_to_env")
        self.assertIn("secrets_via_environment", launch["launch_readiness"]["review_items"])
        self.assertEqual(
            launch["secret_handling"]["direct_secret_fields"],
            ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"],
        )
        self.assertIn("llm_api_key", details["credential_transport"])
        self.assertIn('export OPENAI_BASE_URL="http://127.0.0.1:8317"', rendered)
        self.assertIn('export OPENAI_MODEL="gpt-5.5"', rendered)
        self.assertNotIn("config-api-token", rendered)
        self.assertNotIn("researcher@university.edu", rendered)
        self.assertNotIn("semantic-config-secret", rendered)
        self.assertNotIn("openalex-config-secret", rendered)

    def test_placeholder_config_api_key_is_rejected_without_printing_value(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            config = load_config(ROOT / "examples" / "uci-iris-paper-grade-config.toml")
            config = replace(config, llm=replace(config.llm, base_url="http://127.0.0.1:8317", model="gpt-5.5", api_key="replace-for-real-run"))
            config = replace(config, literature=replace(config.literature, contact_email="researcher@university.edu"))
            with _env_override(
                OPENAI_BASE_URL=None,
                OPENAI_MODEL=None,
                OPENAI_API_KEY=None,
                RESEARCH_AGENT_CONTACT_EMAIL=None,
                SEMANTIC_SCHOLAR_API_KEY=None,
                OPENALEX_API_KEY=None,
            ):
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=config,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["llm_api_key"]["status"], "fail")
        self.assertIn("invalid_or_placeholder", checks["llm_api_key"]["detail"])
        self.assertNotIn("replace-for-real-run", rendered)

    def test_unbounded_warn_benchmark_pack_requires_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root, bounded_negative_or_neutral=False)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="researcher@university.edu",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "warn")
        self.assertEqual(checks["benchmark_pack_run"]["status"], "warn")
        self.assertIn("publishable_negative_or_neutral=False", checks["benchmark_pack_run"]["detail"])
        self.assertIn("claim policy", checks["benchmark_pack_run"]["action"])

    def test_rejects_placeholder_contact_email_without_printing_it(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL="http://127.0.0.1:8317",
                OPENAI_MODEL="gpt-5.5",
                OPENAI_API_KEY="unit-test-api-token",
                RESEARCH_AGENT_CONTACT_EMAIL="agent@example.org",
                SEMANTIC_SCHOLAR_API_KEY="semantic-secret",
                OPENALEX_API_KEY="openalex-secret",
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=_gold_config(config_path),
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                )
                rendered = render_gold_run_doctor_markdown(report)

        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["literature_contact_email"]["status"], "fail")
        self.assertIn("invalid_or_placeholder", checks["literature_contact_email"]["detail"])
        self.assertNotIn("agent@example.org", rendered)

    def test_ping_llm_failure_blocks_doctor_without_printing_secret(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir, fulltext_dir = _write_supporting_runs(root)
            with _env_override(
                OPENAI_BASE_URL=None,
                OPENAI_MODEL=None,
                OPENAI_API_KEY=None,
                RESEARCH_AGENT_CONTACT_EMAIL=None,
                SEMANTIC_SCHOLAR_API_KEY=None,
                OPENALEX_API_KEY=None,
            ):
                config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
                config = load_config(config_path)
                config = replace(config, llm=replace(config.llm, base_url="http://127.0.0.1:1", model="gpt-5.5", api_key="unit-test-api-token"))
                config = replace(config, literature=replace(config.literature, contact_email="researcher@university.edu"))
                report = build_gold_run_doctor(
                    topic="Iris classification benchmark smoke",
                    config=config,
                    config_path=config_path,
                    benchmark_pack_run_dir=benchmark_dir,
                    fulltext_grounding_run_dir=fulltext_dir,
                    ping_llm=True,
                    llm_timeout_seconds=1,
                )
                rendered = render_gold_run_doctor_markdown(report)

        checks = {item["name"]: item for item in report["checks"]}
        llm_ping = next(item for item in report["preflight"] if item["name"] == "llm_ping")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(checks["preflight:overall"]["status"], "fail")
        self.assertEqual(llm_ping["status"], "fail")
        self.assertNotIn("unit-test-api-token", rendered)


def _write_supporting_runs(root: Path, *, bounded_negative_or_neutral: bool = True) -> tuple[Path, Path]:
    benchmark_dir = root / "benchmark"
    fulltext_dir = root / "fulltext"
    benchmark_dir.mkdir()
    fulltext_dir.mkdir()
    benchmark_pack = {"status": "warn", "benchmark_evidence_grade": "real_benchmark", "results": 9, "comparisons": 3}
    if bounded_negative_or_neutral:
        benchmark_pack.update(
            {
                "statistical_outcome": "neutral_no_observed_difference",
                "claim_boundary_severity": "negative_or_neutral_no_superiority",
                "publishable_negative_or_neutral_result": True,
                "claim_policy": "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims",
            }
        )
    write_json(
        benchmark_dir / "04-benchmark-pack-run.json",
        benchmark_pack,
    )
    write_json(
        fulltext_dir / "10-fulltext-grounding-run.json",
        {"status": "pass", "grounding_status": "pass", "fulltext_chunks": 3},
    )
    return benchmark_dir, fulltext_dir


def _gold_config(config_path: Path):
    config = load_config(config_path)
    release = replace(
        config.release,
        code_repository_url="https://github.com/research-agent-lab/research-agent",
        code_archive_doi="10.5281/zenodo.7654321",
        code_license="MIT",
        code_version="v1.0.0",
        data_repository_url="https://archive.ics.uci.edu/dataset/53/iris",
        data_archive_doi="10.24432/C56C76",
        data_access_statement="The Iris data are available from the UCI Machine Learning Repository with a frozen local copy used for reproducible benchmark gating.",
        environment_url="https://github.com/research-agent-lab/research-agent/blob/v1.0.0/Dockerfile",
        release_notes="Gold-run release metadata supplied for the UCI Iris benchmark workflow.",
    )
    return replace(config, release=release)


def _write_candidate_run(
    run_dir: Path,
    *,
    claim_boundary_severity: str = "negative_or_neutral_no_superiority",
    package_status: str = "ready_for_human_submission_upload",
    economics_status: str = "pass",
    economics_blockers: list[str] | None = None,
    scorecard_status: str = "ready_for_human_submission_upload",
    scorecard_blockers: list[str] | None = None,
    final_handoff_status: str = "ready_for_submission_upload",
) -> Path:
    run_dir.mkdir()
    write_json(run_dir / "state.json", {"topic": "gold", "stage": "completed"})
    write_json(run_dir / "run-config.json", {"llm": {"api_key": ""}, "literature": {"semantic_scholar_api_key": "", "openalex_api_key": "", "contact_email": ""}})
    write_json(run_dir / "run-manifest.json", {"events": [{"stage": "completed"}], "artifacts": [{"path": "state.json"}, {"path": "run-manifest.json"}, {"path": "run-llm-ledger.json"}]})
    write_json(run_dir / "run-llm-ledger.json", {"summary": {"total_calls": 3, "successful_calls": 3}, "calls": [{"stage": "paper_revision", "status": "success"}]})
    write_json(run_dir / "01-literature-gate-decision.json", {"paper_grade_literature": {"status": "pass", "issues": []}})
    write_json(
        run_dir / "04-benchmark-evidence-audit.json",
        {
            "status": "warn",
            "evidence_grade": "real_benchmark",
            "adapter_paper_grade_status": "ready",
            "adapter_paper_grade_issues": [],
            "claim_boundary_severity": claim_boundary_severity,
            "statistical_outcome": "neutral_no_observed_difference",
            "publishable_negative_or_neutral_result": True,
            "claim_policy": "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims",
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )
    write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(
        run_dir / "10-claim-traceability.json",
        {"status": "pass", "traceability_score": 1.0, "blocked_claims": 0, "review_claims": 0, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(
        run_dir / "10-release-metadata.json",
        {
            "status": "ready_for_release",
            "metadata": {
                "code_repository_url": "https://github.com/research-agent-lab/research-agent",
                "code_archive_doi": "10.5281/zenodo.7654321",
                "code_license": "MIT",
                "code_version": "v1.0.0",
                "data_repository_url": "https://archive.ics.uci.edu/dataset/53/iris",
                "data_archive_doi": "10.24432/C56C76",
                "data_access_statement": "The Iris data are available from the UCI Machine Learning Repository.",
                "environment_url": "https://github.com/research-agent-lab/research-agent/blob/v1.0.0/Dockerfile",
                "release_notes": "Gold-run candidate release metadata.",
            },
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )
    write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "unsupported_after": 0, "blocking_issues": []})
    write_json(run_dir / "11-submission-package.json", {"status": package_status, "blocking_issues": [], "manual_tasks": []})
    with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
        archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
        archive.writestr(
            "submission-package/package-manifest.json",
            json.dumps({"status": "ready_for_human_submission_upload", "files": [{"package_path": "submission-package/CHECKLIST.md"}]}),
        )
    write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0, "block": 0, "high": 0, "medium": 0}})
    write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-runtime-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(
        run_dir / "13-run-economics-audit.json",
        {
            "status": economics_status,
            "summary": {"input_tokens_estimated": 100, "output_tokens_estimated": 50, "total_tokens_estimated": 150},
            "blocking_issues": economics_blockers or [],
            "manual_tasks": [],
            "warnings": [],
        },
    )
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-observability-summary.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-stage-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-trajectory.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(
        run_dir / "13-research-scorecard.json",
        {"status": scorecard_status, "overall_score": 95, "blocking_issues": scorecard_blockers or [], "manual_tasks": []},
    )
    write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"pass": 12, "warn": 0, "block": 0}, "blocking_issues": [], "warnings": []})
    write_json(
        run_dir / "14-final-handoff.json",
        {
            "status": final_handoff_status,
            "package_zip_exists": True,
            "package_zip_valid": True,
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )
    _write_test_run_manifest(run_dir)
    return run_dir


def _write_test_run_manifest(run_dir: Path) -> None:
    artifacts = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        data = path.read_bytes()
        artifacts.append(
            {
                "path": str(path.relative_to(run_dir)),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    write_json(run_dir / "run-manifest.json", {"events": [{"stage": "completed"}], "artifacts": artifacts})


class _env_override:
    def __init__(self, **values: str | None) -> None:
        self.values = values
        self.previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for key, value in self.values.items():
            self.previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, *args: object) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
