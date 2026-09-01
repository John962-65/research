from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any
from urllib.parse import quote
import contextlib
import hashlib
import json
import os
import time
import unittest
import urllib.error
import urllib.request
import zipfile

from research_agent.artifacts import write_json, write_text
from research_agent.config import AgentConfig, ExecutionConfig, PaperGradeConfig
import research_agent.pipeline as pipeline_module
import research_agent.web_server as web_server


def _write_gold_verification_candidate(run_dir: Path, *, package_status: str = "ready_for_human_submission_upload") -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "state.json", {"topic": "Iris", "stage": "completed", "updated_at": "test"})
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
            "claim_boundary_severity": "negative_or_neutral_no_superiority",
            "statistical_outcome": "neutral_no_observed_difference",
            "publishable_negative_or_neutral_result": True,
            "claim_policy": "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims",
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )
    write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(
        run_dir / "10-claim-traceability.json",
        {"status": "pass", "traceability_score": 1.0, "blocked_claims": 0, "review_claims": 0, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(run_dir / "10-release-metadata.json", {"status": "ready_for_release", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "unsupported_after": 0, "blocking_issues": []})
    write_json(run_dir / "11-submission-package.json", {"status": package_status, "blocking_issues": [], "manual_tasks": []})
    with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
        archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
        archive.writestr(
            "submission-package/package-manifest.json",
            json.dumps({"status": "ready_for_human_submission_upload", "files": [{"package_path": "submission-package/CHECKLIST.md"}]}),
        )
    write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0, "block": 0}})
    write_json(
        run_dir / "13-run-economics-audit.json",
        {
            "status": "pass",
            "summary": {"input_tokens_estimated": 100, "output_tokens_estimated": 50, "total_tokens_estimated": 150},
            "blocking_issues": [],
            "manual_tasks": [],
            "warnings": [],
        },
    )
    write_json(run_dir / "13-research-scorecard.json", {"status": "ready_for_human_submission_upload", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-runtime-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-observability-summary.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-stage-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-trajectory.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(
        run_dir / "14-final-handoff.json",
        {
            "status": "ready_for_submission_upload",
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


def _bind_review_approval(run_dir: Path) -> None:
    approval = json.loads((run_dir / "approval.json").read_text(encoding="utf-8"))
    binding = pipeline_module._review_approval_binding(run_dir, str(approval.get("topic") or ""))
    approval["approval_binding"] = binding
    approval["approval_binding_sha256"] = pipeline_module._digest_payload(binding)
    write_json(run_dir / "approval.json", approval)


def _bind_execution_approval(run_dir: Path) -> None:
    binding = {"schema_version": 1, "source_artifacts": []}
    binding_hash = pipeline_module._digest_payload(binding)
    write_json(run_dir / "03-experiment-plan.json", {"idea_title": "test"})
    write_json(
        run_dir / pipeline_module.EXECUTION_SAFETY_AUDIT_JSON,
        {
            "status": "pass",
            "execution_binding": binding,
            "execution_binding_sha256": binding_hash,
        },
    )
    approval = json.loads((run_dir / "03-execution-approval.json").read_text(encoding="utf-8"))
    approval.update(
        {
            "plan_sha256": pipeline_module._file_sha256(run_dir / "03-experiment-plan.json"),
            "safety_sha256": pipeline_module._file_sha256(run_dir / pipeline_module.EXECUTION_SAFETY_AUDIT_JSON),
            "execution_binding": binding,
            "execution_binding_sha256": binding_hash,
        }
    )
    write_json(run_dir / "03-execution-approval.json", approval)


def _write_gold_launch_bundle_marker(run_dir: Path) -> None:
    write_json(
        run_dir / web_server.GOLD_LAUNCH_BUNDLE_JSON,
        {"status": "ready_to_start", "can_start_gold_run": True, "components": [], "launch_plan": {}, "read_only": True},
    )


class WebResumeTest(unittest.TestCase):
    def test_live_gold_launch_commands_drop_secret_bearing_commands(self) -> None:
        commands = web_server._live_gold_launch_commands(
            {
                "commands": [
                    "export OPENAI_API_KEY=unit-test-api-token",
                    "OPENAI_API_KEY=unit-test-api-token PYTHONPATH=src python3 -m research_agent run --paper-grade",
                    "PYTHONPATH=src python3 -m research_agent run --llm-api-key unit-test-api-token",
                    "PYTHONPATH=src python3 -m research_agent run api_key=unit-test-api-token",
                    "curl https://example.test?token=unit-test-api-token",
                    "PYTHONPATH=src python3 -m research_agent run --paper-grade",
                    "PYTHONPATH=src python3 -m research_agent status runs/gold-run",
                ]
            }
        )

        self.assertEqual(
            commands,
            [
                "PYTHONPATH=src python3 -m research_agent run --paper-grade",
                "PYTHONPATH=src python3 -m research_agent status runs/gold-run",
            ],
        )
        payload = "\n".join(commands)
        self.assertNotIn("OPENAI_API_KEY", payload)
        self.assertNotIn("unit-test-api-token", payload)
        self.assertNotIn("--llm-api-key", payload)

    def test_run_store_rejects_prefix_sibling_run_paths(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            root = parent / "research-agent"
            sibling = parent / "research-agent-evil"
            root.mkdir()
            run_dir = sibling / "runs" / "evil"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "evil", "stage": "completed", "updated_at": "test"})
            write_text(run_dir / "00-question.md", "# outside\n")
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            try:
                store = web_server.RunStore()
                store._runs["evil"] = {
                    "id": "evil",
                    "topic": "evil",
                    "stage": "completed",
                    "status": "unknown",
                    "worker_active": False,
                    "out_dir": "../research-agent-evil/runs/evil",
                    "error": None,
                }

                self.assertIsNone(store.out_dir("evil"))
                self.assertIsNone(store.artifact_path("evil", "00-question.md"))
                self.assertFalse(web_server._is_safe_existing_path(run_dir / "00-question.md", root))
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_web_payload_populates_human_brief_config(self) -> None:
        config = web_server._config_from_payload(
            {
                "human_notes": "优先窄通道\n保留失败案例",
                "human_constraints": "必须比较 RRT*",
                "human_success_criteria": "成功率提升",
                "human_resource_limits": "只允许 smoke-first",
                "human_risks": "避免玩具场景",
            }
        )

        self.assertEqual(config.human.notes, ["优先窄通道", "保留失败案例"])
        self.assertEqual(config.human.constraints, ["必须比较 RRT*"])
        self.assertEqual(config.human.success_criteria, ["成功率提升"])
        self.assertEqual(config.human.resource_limits, ["只允许 smoke-first"])
        self.assertEqual(config.human.risks, ["避免玩具场景"])

    def test_web_payload_populates_execution_timeout_config(self) -> None:
        config = web_server._config_from_payload(
            {
                "execution_mode": "benchmark",
                "timeout_seconds": 900,
                "execution_repeats": 7,
                "allowed_commands": "python3, pytest",
                "benchmark_manifests": "examples/benchmark-adapter/manifest.json",
            }
        )

        self.assertEqual(config.execution.mode, "benchmark")
        self.assertEqual(config.execution.timeout_seconds, 900)
        self.assertEqual(config.execution.repeats, 7)
        self.assertEqual(config.execution.allowed_commands, ["python3", "pytest"])
        self.assertEqual(config.execution.benchmark_manifest_paths, ["examples/benchmark-adapter/manifest.json"])

    def test_web_payload_populates_paper_grade_config(self) -> None:
        config = web_server._config_from_payload({"paper_grade_enabled": True, "paper_grade_min_execution_repeats": 5})
        overridden = web_server._apply_payload_overrides(
            AgentConfig(),
            {"paper_grade": {"enabled": True, "min_benchmark_roles": 4}, "paper_grade_min_execution_repeats": 6},
        )
        reloaded = web_server._config_from_dict({"paper_grade": {"enabled": True, "min_execution_repeats": 4}})

        self.assertTrue(config.paper_grade.enabled)
        self.assertEqual(config.paper_grade.min_execution_repeats, 5)
        self.assertTrue(overridden.paper_grade.enabled)
        self.assertEqual(overridden.paper_grade.min_benchmark_roles, 4)
        self.assertEqual(overridden.paper_grade.min_execution_repeats, 6)
        self.assertTrue(reloaded.paper_grade.enabled)
        self.assertEqual(reloaded.paper_grade.min_execution_repeats, 4)

    def test_existing_run_provider_switch_requires_explicit_nonempty_base_url(self) -> None:
        config = replace(
            AgentConfig(),
            llm=replace(
                AgentConfig().llm,
                provider="openai-compatible",
                base_url="https://api.openai.com/v1",
                model="old-model",
            ),
        )

        for payload in [
            {"llm_provider": "custom-http"},
            {"llm_provider": "custom-http", "llm_base_url": ""},
        ]:
            with self.subTest(payload=payload), self.assertRaisesRegex(
                ValueError,
                "changing llm_provider requires an explicit non-empty llm_base_url",
            ):
                web_server._apply_payload_overrides(config, payload)

    def test_existing_run_provider_switch_with_explicit_base_clears_old_inline_key(self) -> None:
        config = replace(
            AgentConfig(),
            llm=replace(
                AgentConfig().llm,
                provider="openai-compatible",
                base_url="https://api.openai.com/v1",
                api_key="old-inline-secret",
                model="old-model",
            ),
        )

        overridden = web_server._apply_payload_overrides(
            config,
            {
                "llm_provider": "custom-http",
                "llm_base_url": "http://192.0.2.1:8080/v1",
            },
        )

        self.assertEqual(overridden.llm.provider, "custom-http")
        self.assertEqual(overridden.llm.base_url, "http://192.0.2.1:8080/v1")
        self.assertEqual(overridden.llm.api_key, "")

    def test_paper_grade_web_create_rejects_payload_secret_without_echoing_value(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_server.ROOT = root
            web_server.RUNS_DIR = root / "runs"
            server = None
            thread = None
            try:
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                payload = {
                    "topic": "Paper-grade secret guard",
                    "paper_grade_enabled": True,
                    "llm_api_key": "payload-secret-token",
                    "semantic_scholar_api_key": "semantic-payload-secret",
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/runs",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=5)
                body = raised.exception.read().decode("utf-8")
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

        self.assertEqual(raised.exception.code, 400)
        self.assertIn("env-only secret handling", body)
        self.assertIn("llm_api_key", body)
        self.assertIn("semantic_scholar_api_key", body)
        self.assertNotIn("payload-secret-token", body)
        self.assertNotIn("semantic-payload-secret", body)

    def test_paper_grade_web_preflight_rejects_payload_secret_without_echoing_value(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = {
                "topic": "Paper-grade preflight secret guard",
                "paper_grade_enabled": True,
                "llm_api_key": "payload-secret-token",
            }
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/preflight",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=5)
            body = raised.exception.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()
            with contextlib.suppress(RuntimeError):
                thread.join(timeout=2)

        self.assertEqual(raised.exception.code, 400)
        self.assertIn("env-only secret handling", body)
        self.assertIn("llm_api_key", body)
        self.assertNotIn("payload-secret-token", body)

    def test_paper_grade_resume_rejects_payload_secret_without_echoing_value(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "paper-grade-resume"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "Paper-grade resume", "stage": "awaiting_review_approval", "updated_at": "test"})
                web_server._write_run_config(run_dir, replace(AgentConfig(), paper_grade=PaperGradeConfig(enabled=True)))
                store = web_server.RunStore()

                with self.assertRaises(RuntimeError) as raised:
                    store.resume_with_config("paper-grade-resume", payload={"openalex_api_key": "payload-openalex-secret"})
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

        message = str(raised.exception)
        self.assertIn("env-only secret handling", message)
        self.assertIn("openalex_api_key", message)
        self.assertNotIn("payload-openalex-secret", message)

    def test_existing_run_exposes_availability_summary(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "availability-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "可用性审计", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "10-release-metadata.json",
                    {
                        "status": "needs_release_metadata",
                        "manual_tasks": ["补归档 DOI"],
                        "blocking_issues": [],
                    },
                )
                write_json(
                    run_dir / "10-code-data-availability.json",
                    {
                        "status": "needs_human_release_metadata",
                        "ready_for_internal_release": True,
                        "ready_for_submission_check": False,
                        "manual_tasks": ["补许可证", "补归档 DOI"],
                        "blocking_issues": [],
                    },
                )
                write_json(
                    run_dir / "11-submission-package.json",
                    {
                        "status": "needs_human_submission_review",
                        "package_zip": "11-submission-package.zip",
                        "files": [{"package_path": "submission-package/README.md"}],
                        "manual_tasks": ["人工核验 ZIP"],
                        "blocking_issues": [],
                    },
                )
                write_json(
                    run_dir / "12-next-iteration-plan.json",
                    {
                        "status": "needs_targeted_iteration",
                        "decision": "按优先级处理阻断项。",
                        "items": [{"category": "release"}],
                    },
                )
                write_json(
                    run_dir / "12-repair-queue.json",
                    {
                        "status": "needs_repair",
                        "summary": {"total": 2, "block": 0, "high": 1, "medium": 1, "blocks_submission": 2},
                        "items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}],
                    },
                )
                write_json(
                    run_dir / "12-repair-resume-plan.json",
                    {
                        "status": "ready_to_resume_repair",
                        "applied": True,
                        "can_resume": True,
                        "queue_status": "needs_repair",
                        "rerun_from": "literature_review",
                        "repair_items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}],
                        "retrieval_repair_tasks": [{"task_id": "seed-role-review", "query": "private query"}],
                        "recommended_config": {
                            "literature_provider": "online",
                            "sources": ["semantic_scholar", "openalex"],
                            "max_papers": 12,
                            "max_search_queries": 6,
                        },
                        "recommended_execution_config": {
                            "execution_mode": "benchmark",
                            "allowed_commands": ["python3"],
                            "execution_repeats": 5,
                            "timeout_seconds": 300,
                            "benchmark_manifest_paths": ["examples/benchmark-adapter/manifest.json"],
                        },
                        "recommended_release_config": {
                            "status": "needs_input",
                            "required_fields": ["release_code_repository_url"],
                            "recommended_fields": ["release_data_archive_doi"],
                            "cli_args": ["--release-code-repository-url", "--release-data-archive-doi"],
                            "field_actions": {
                                "release_code_repository_url": {
                                    "action": "private release action must not leak",
                                    "recommended_value": "",
                                }
                            },
                        },
                        "review_reapproval_required": True,
                        "execution_reapproval_required": True,
                        "artifacts_to_remove": ["01-literature.json"],
                        "directories_to_remove": [],
                        "removed_artifacts": ["01-literature.json"],
                        "removed_directories": [],
                        "repair_context": {"prompt_text": "private repair prompt must not leak"},
                        "experiment_manager_resume_actions": [
                            {
                                "branch_id": "B1",
                                "title": "private manager branch must not leak",
                                "queue_state": "blocked_human_repair",
                                "action": "private manager action must not leak",
                            }
                        ],
                        "stop_conditions": ["queue pass"],
                    },
                )
                write_json(
                    run_dir / "02-experiment-manager.json",
                    {
                        "status": "review_required",
                        "manager_decision": "proceed_with_cautions",
                        "execution_policy": "smoke_first",
                        "selected_branch_id": "B1",
                        "selected_idea_title": "谨慎分支",
                        "next_expansion_candidates": [{"branch_id": "B2", "title": "候选"}],
                        "planning_constraints": ["先规划低成本 smoke-first 实验。"],
                        "queue_summary": {
                            "total": 2,
                            "active": 1,
                            "blocked": 0,
                            "human_review": 1,
                            "ready_backlog": 1,
                            "deferred": 0,
                            "blocks_current_experiment": 0,
                        },
                        "manager_queue": [
                            {
                                "branch_id": "B1",
                                "queue_state": "active_smoke_first",
                                "owner": "human+agent",
                                "requires_human": True,
                                "repair_context": {"prompt_text": "private manager prompt must not leak"},
                            }
                        ],
                    },
                )
                write_json(
                    run_dir / "02-novelty-audit.json",
                    {
                        "topic": "可用性审计",
                        "total_ideas": 2,
                        "likely_duplicates": 1,
                        "review_required": 1,
                        "items": [
                            {"idea_title": "谨慎分支", "decision": "review_required"},
                            {"idea_title": "重复分支", "decision": "likely_duplicate"},
                        ],
                        "warnings": ["1 个 idea 与已纳入文献高度相似。", "1 个 idea 需要人工复核 novelty 边界。"],
                    },
                )
                write_json(
                    run_dir / "02-idea-audit.json",
                    {
                        "topic": "可用性审计",
                        "status": "review",
                        "total_ideas": 2,
                        "pass": 1,
                        "review_required": 1,
                        "blocked": 0,
                        "items": [{"idea_title": "谨慎分支", "decision": "review", "issues": ["missing baseline"]}],
                        "warnings": ["1 个 idea 缺少证据、baseline、评估协议或实验草案。"],
                    },
                )
                write_json(
                    run_dir / "03-experiment-audit.json",
                    {
                        "idea_title": "谨慎分支",
                        "status": "block",
                        "template_profile": "benchmark",
                        "blocking_issues": ["实验命令缺少 baseline/control。", "实验命令缺少 ablation。"],
                        "warnings": ["文献覆盖仍有缺口。"],
                        "required_actions": ["补齐 baseline/control 和 ablation 命令。"],
                    },
                )
                write_json(
                    run_dir / "03-idea-experiment-contract.json",
                    {
                        "topic": "可用性审计",
                        "status": "review_required",
                        "contract_score": 0.72,
                        "selected_idea_title": "谨慎分支",
                        "execution_mode": "benchmark",
                        "blocking_issues": [],
                        "manual_tasks": ["让实验 metrics 与 benchmark expected_metrics 对齐。", "人工确认降级声明。"],
                        "required_actions": ["人工确认契约风险。"],
                        "repair_context": {"prompt_text": "private idea experiment prompt must not leak"},
                    },
                )
                write_json(
                    run_dir / "03-execution-safety-audit.json",
                    {
                        "idea_title": "谨慎分支",
                        "status": "block",
                        "execution_mode": "benchmark",
                        "blocking_issues": ["benchmark adapter: manifest 缺少 license。"],
                        "warnings": ["部分命令未声明 expected_artifacts。"],
                        "required_actions": ["修复 manifest 后再运行实验。"],
                        "benchmark_adapter_audit": {
                            "status": "blocked",
                            "blocking_issues": ["manifest 缺少 license。"],
                            "manual_tasks": ["补 citation。"],
                        },
                    },
                )
                write_json(
                    run_dir / "03-benchmark-plan.json",
                    {
                        "topic": "可用性审计",
                        "domain": "robotics_motion_planning",
                        "template_profile": "benchmark",
                        "candidates": [{"name": "OMPL Benchmark"}, {"name": "MoveIt Benchmarking"}],
                        "selected_names": ["OMPL Benchmark"],
                        "required_actions": ["人工确认 benchmark 访问方式和许可证。"],
                        "warnings": ["人工场景过小会削弱实验结论。"],
                    },
                )
                write_json(
                    run_dir / "03-benchmark-readiness.json",
                    {
                        "topic": "可用性审计",
                        "status": "block",
                        "execution_mode": "benchmark",
                        "confidence_score": 0.45,
                        "blocking_issues": ["manifest provenance 缺少 baseline_version。"],
                        "manual_tasks": ["补 dataset_url。", "补 citation。"],
                        "recommended_actions": ["补齐 manifest provenance 后再批准执行。"],
                    },
                )
                write_json(
                    run_dir / "03-benchmark-adapters.json",
                    {
                        "status": "blocked",
                        "mode": "benchmark",
                        "manifest_paths": ["benchmarks/robotics/manifest.json"],
                        "adapters": [{"name": "OMPL Benchmark", "status": "blocked", "issues": ["source file 缺失"]}],
                        "commands": [],
                        "blocking_issues": ["manifest 缺少 source file。"],
                        "manual_tasks": ["补许可证。"],
                    },
                )
                write_json(
                    run_dir / "04-benchmark-result-schema-audit.json",
                    {
                        "status": "block",
                        "execution_mode": "benchmark",
                        "actual_metrics": ["success_rate"],
                        "benchmark_expected_metrics": ["success_rate", "planning_time"],
                        "adapter_expected_artifacts": ["metrics.json"],
                        "adapter_provenance": {"baseline": {"license": "BSD-3-Clause"}},
                        "blocking_issues": ["baseline adapter 缺少 citation"],
                        "manual_tasks": ["补充 dataset_url"],
                        "warnings": ["repeat 数较少"],
                    },
                )
                write_json(
                    run_dir / "01-literature-search-feedback.json",
                    {
                        "status": "needs_search_revision",
                        "recommended_queries": [{"query": "robot manipulator OMPL benchmark"}],
                        "seed_paper_targets": [{"name": "OMPL"}],
                        "retrieval_repair_tasks": [{"owner": "agent", "query": "robot manipulator OMPL benchmark"}],
                        "next_run_config": {
                            "literature_provider": "online",
                            "sources": ["openalex", "crossref"],
                            "max_papers": 12,
                            "max_search_queries": 6,
                            "seed_papers_min": 3,
                        },
                        "approval_guidance": ["补检索后再批准。"],
                    },
                )
                write_json(
                    run_dir / "01-literature-search-strategy.json",
                    {
                        "status": "review_required",
                        "quality_score": 0.66,
                        "selected_queries": ["robot"],
                        "selected_intents": ["method"],
                        "missing_required_intents": ["baseline", "benchmark"],
                        "weak_selected_queries": ["robot"],
                    },
                )
                write_json(
                    run_dir / "01-literature-source-health.json",
                    {
                        "topic": "可用性审计",
                        "sources": [
                            {
                                "source": "semantic_scholar",
                                "status": "rate_limited",
                                "queries": 1,
                                "returned": 0,
                                "errors": 1,
                                "rate_limited": True,
                                "query_results": [
                                    {
                                        "source": "semantic_scholar",
                                        "query": "robot manipulator OMPL benchmark",
                                        "status": "rate_limited",
                                        "returned": 0,
                                        "rate_limited": True,
                                    }
                                ],
                            },
                            {"source": "openalex", "status": "ok", "queries": 1, "returned": 3, "errors": 0, "rate_limited": False},
                            {"source": "crossref", "status": "failed", "queries": 1, "returned": 0, "errors": 1, "rate_limited": False},
                        ],
                        "query_results": [
                            {"source": "semantic_scholar", "query": "robot manipulator OMPL benchmark", "status": "rate_limited", "returned": 0, "rate_limited": True},
                            {"source": "openalex", "query": "robot manipulator OMPL benchmark", "status": "ok", "returned": 3, "rate_limited": False},
                        ],
                        "total_sources": 3,
                        "rate_limited_sources": 1,
                        "failed_sources": 1,
                        "cache_hits": 0,
                        "cache_misses": 2,
                        "stale_cache_uses": 0,
                        "query_attempts": 2,
                        "query_successes": 1,
                        "query_failures": 0,
                        "query_rate_limits": 1,
                    },
                )
                write_json(
                    run_dir / "01-query-execution-audit.json",
                    {
                        "status": "needs_query_repair",
                        "selected_query_count": 2,
                        "raw_candidate_count": 3,
                        "source_coverage": {
                            "configured_source_count": 3,
                            "sources_with_success": 1,
                            "rate_limited_sources": 1,
                            "failed_sources": 1,
                            "queries_with_source_results": 1,
                            "queries_with_zero_source_results": 1,
                        },
                        "intent_coverage": {
                            "required_intents": ["method", "baseline", "benchmark"],
                            "missing_required_intents": ["benchmark"],
                        },
                        "top_rerank_coverage": {
                            "top_count": 5,
                            "covered_top_count": 2,
                            "average_query_coverage": 0.32,
                        },
                        "warnings": ["Top rerank 候选对 selected queries 覆盖不足。"],
                        "required_actions": ["补齐 selected_queries 缺失的检索意图：benchmark"],
                        "manual_tasks": ["如使用 Semantic Scholar，设置 SEMANTIC_SCHOLAR_API_KEY 后重跑。"],
                        "queries": [{"query": "private query should not leak"}],
                    },
                )
                write_json(
                    run_dir / "01-literature-rerank.json",
                    {
                        "status": "review_required",
                        "total_candidates": 3,
                        "query_count": 2,
                        "warnings": ["单源 Crossref 候选过多。"],
                        "recommended_actions": ["补 DOI/URL seed。"],
                        "items": [{"title": "private rerank title should not leak"}],
                    },
                )
                write_json(
                    run_dir / "01-literature-coverage.json",
                    {
                        "status": "needs_coverage",
                        "coverage_ratio": 0.5,
                        "covered_required": 2,
                        "total_required": 4,
                        "missing_required": [{"category": "benchmark", "name": "OMPL"}],
                        "warnings": ["缺少 benchmark 覆盖。"],
                        "required_actions": ["补 benchmark 文献。"],
                    },
                )
                write_json(
                    run_dir / "01-literature-evidence-mix.json",
                    {
                        "status": "needs_evidence_upgrade",
                        "mix_score": 0.42,
                        "summary": {"raw_papers": 3, "curated_papers": 2, "source_diversity": 1},
                        "warnings": ["来源多样性不足。"],
                        "blocking_issues": [],
                        "required_actions": ["补 review/benchmark/baseline anchor。"],
                    },
                )
                write_json(
                    run_dir / "01-literature-rescue-plan.json",
                    {
                        "status": "needs_rescue_search",
                        "coverage_status": "needs_coverage",
                        "coverage_ratio": 0.42,
                        "missing_evidence_roles": ["review_survey", "benchmark_dataset"],
                        "weak_reasons": ["证据角色覆盖不足。"],
                        "source_repairs": ["设置 SEMANTIC_SCHOLAR_API_KEY 后重跑。"],
                        "rescue_queries": [
                            {
                                "kind": "missing_evidence_role",
                                "priority": 99,
                                "query": "robot manipulator motion planning survey review systematic review benchmark",
                                "rationale": "缺少 review/survey anchor",
                            },
                            {
                                "kind": "missing_evidence_role",
                                "priority": 99,
                                "query": "robot manipulator motion planning benchmark dataset evaluation testbed",
                                "rationale": "缺少 benchmark/dataset anchor",
                            },
                            {
                                "kind": "domain_baseline_matrix",
                                "priority": 96,
                                "query": "robot manipulator motion planning benchmark OMPL MoveIt RRT*",
                                "rationale": "领域 baseline",
                            },
                        ],
                        "required_actions": ["补检索后重跑文献阶段。"],
                        "repair_context": {"prompt_text": "private rescue prompt must not leak"},
                    },
                )
                write_json(
                    run_dir / "01-literature-rescue-execution.json",
                    {
                        "status": "no_new_papers",
                        "trigger_status": "needs_rescue_search",
                        "updated_review": False,
                        "selected_queries": ["robot manipulator OMPL benchmark"],
                        "repair_task_ids": ["retrieval-repair-001"],
                        "closed_query_outcomes": 0,
                        "unresolved_query_outcomes": 1,
                        "new_unique_papers": 0,
                        "query_outcomes": [
                            {
                                "query": "robot manipulator OMPL benchmark",
                                "status": "no_hits",
                            }
                        ],
                        "required_actions": ["检索修复任务 retrieval-repair-001 未闭环。"],
                        "warnings": ["仍有 1 条 query outcome 未闭环。"],
                    },
                )
                write_json(
                    run_dir / "01-literature-quality.json",
                    {
                        "items": [
                            {
                                "title": "OMPL benchmark suite for robot manipulator motion planning",
                                "doi": "10.1109/MRA.2012.2205651",
                                "url": "https://doi.org/10.1109/MRA.2012.2205651",
                                "quality_score": 0.93,
                                "selected": True,
                            },
                            {
                                "title": "Survey of robot manipulator motion planning methods",
                                "doi": "",
                                "url": "https://example.test/robot-survey",
                                "quality_score": 0.88,
                                "selected": True,
                            },
                            {
                                "title": "Excluded weak robot paper",
                                "doi": "10.9999/weak",
                                "url": "https://doi.org/10.9999/weak",
                                "quality_score": 0.2,
                                "selected": False,
                            },
                        ]
                    },
                )
                write_json(
                    run_dir / "01-literature-curated.json",
                    {
                        "papers": [
                            {
                                "title": "Existing Seed",
                                "doi": "10.0000/existing",
                                "url": "https://doi.org/10.0000/existing",
                                "relevance": 0.99,
                            },
                            {
                                "title": "CHOMP robot manipulator trajectory optimization",
                                "doi": "10.1109/ICRA.2009.5152817",
                                "url": "https://doi.org/10.1109/ICRA.2009.5152817",
                                "relevance": 0.86,
                            },
                        ]
                    },
                )
                write_json(
                    run_dir / "01-seed-paper-intake.json",
                    {
                        "status": "pass",
                        "role_coverage_status": "review_required",
                        "total_seed_entries": 3,
                        "curated_seed_papers": 2,
                        "missing_curated_seed_roles": ["review", "benchmark_dataset"],
                        "required_actions": ["补齐进入 curated context 的 seed 角色覆盖。"],
                        "warnings": ["seed 角色覆盖不足。"],
                        "items": [{"doi": "10.0000/existing", "parsed_title": "Existing Seed"}],
                        "seed_entries": [{"doi": "10.0000/private-seed"}],
                    },
                )
                write_json(
                    run_dir / "14-run-integrity-audit.json",
                    {
                        "status": "warn",
                        "summary": {"checks": 12, "pass": 10, "warn": 1, "block": 0, "required_artifacts": 120},
                        "blocking_issues": [],
                        "warnings": ["manifest/artifact_inventory: 缺少部分记录。"],
                        "recommended_actions": ["补齐 manifest 记录。"],
                    },
                )
                write_json(
                    run_dir / "14-final-handoff.json",
                    {
                        "status": "ready_for_human_handoff",
                        "package_zip": "11-submission-package.zip",
                        "package_zip_exists": True,
                        "package_zip_valid": False,
                        "package_status": "needs_human_submission_review",
                        "scorecard_status": "needs_human_work",
                        "scorecard_overall_score": 78.5,
                        "run_integrity_status": "warn",
                        "package_has_integrity_audit": False,
                        "blocking_issues": [],
                        "manual_tasks": ["人工核验 ZIP。"],
                        "recommended_actions": ["重新生成投稿包。"],
                    },
                )
                write_json(
                    run_dir / "13-agent-trajectory.json",
                    {
                        "status": "warn",
                        "summary": {
                            "phase_counts": {"pass": 6, "warn": 2, "block": 0, "not_started": 0},
                            "last_event": "completed",
                            "event_count": 42,
                            "backfilled_events": 11,
                            "artifact_count": 130,
                            "blocking_issues": 0,
                            "manual_tasks": 2,
                        },
                        "phases": [{"phase_id": "private phase must not leak", "next_action": "private phase action"}],
                        "timeline": [{"stage": "private timeline must not leak", "metrics_summary": "private metric"}],
                        "blocking_issues": [],
                        "manual_tasks": ["private manual task must not leak", "private second task must not leak"],
                    },
                )
                write_json(
                    run_dir / "13-agent-observability-audit.json",
                    {
                        "status": "review_required",
                        "summary": {
                            "state_stage": "completed",
                            "manifest_status": "completed",
                            "manifest_events": 42,
                            "manifest_artifacts": 130,
                            "llm_total_calls": 8,
                            "llm_successful_calls": 8,
                            "llm_failed_calls": 0,
                            "llm_budget_exceeded_calls": 1,
                            "experiment_runs": 2,
                            "repair_queue_status": "needs_repair",
                        },
                        "budget": {
                            "call_utilization": 0.4,
                            "prompt_utilization": 0.91,
                            "total_llm_duration_seconds": 12.5,
                        },
                        "checks": [{"name": "private check must not leak", "evidence": "private evidence"}],
                        "blocking_issues": ["private observability blocker must not leak"],
                        "manual_tasks": ["private observability manual task must not leak", "private second manual task must not leak"],
                        "warnings": ["private observability warning must not leak"],
                        "recommended_actions": ["private observability action must not leak"],
                    },
                )
                store = web_server.RunStore()

                loaded = store.get("availability-run")

                self.assertEqual(loaded["availability"]["status"], "needs_human_release_metadata")
                self.assertEqual(loaded["availability"]["manual_tasks"], 2)
                self.assertEqual(loaded["submission_package"]["status"], "needs_human_submission_review")
                self.assertEqual(loaded["submission_package"]["manual_tasks"], 1)
                self.assertEqual(loaded["iteration_plan"]["status"], "needs_targeted_iteration")
                self.assertEqual(loaded["iteration_plan"]["items"], 1)
                self.assertEqual(loaded["repair_queue"]["status"], "needs_repair")
                self.assertEqual(loaded["repair_queue"]["items"], 2)
                self.assertEqual(loaded["repair_resume_plan"]["status"], "ready_to_resume_repair")
                self.assertTrue(loaded["repair_resume_plan"]["applied"])
                self.assertEqual(loaded["repair_resume_plan"]["rerun_from"], "literature_review")
                self.assertEqual(loaded["repair_resume_plan"]["repair_items"], 2)
                self.assertEqual(loaded["repair_resume_plan"]["retrieval_repair_tasks"], 1)
                self.assertEqual(loaded["repair_resume_plan"]["recommended_config"]["literature_provider"], "online")
                self.assertEqual(loaded["repair_resume_plan"]["recommended_config"]["sources"], ["semantic_scholar", "openalex"])
                self.assertEqual(loaded["repair_resume_plan"]["recommended_execution_config"]["execution_mode"], "benchmark")
                self.assertEqual(loaded["repair_resume_plan"]["recommended_execution_config"]["allowed_commands"], ["python3"])
                self.assertEqual(loaded["repair_resume_plan"]["recommended_execution_config"]["benchmark_manifest_paths"], ["examples/benchmark-adapter/manifest.json"])
                self.assertEqual(loaded["repair_resume_plan"]["recommended_release_config"]["required_fields"], ["release_code_repository_url"])
                self.assertEqual(loaded["repair_resume_plan"]["recommended_release_config"]["cli_args"], ["--release-code-repository-url", "--release-data-archive-doi"])
                self.assertTrue(loaded["repair_resume_plan"]["review_reapproval_required"])
                self.assertTrue(loaded["repair_resume_plan"]["execution_reapproval_required"])
                self.assertEqual(loaded["repair_resume_plan"]["removed_artifacts"], 1)
                self.assertEqual(loaded["repair_resume_plan"]["stop_conditions"], 1)
                self.assertEqual(loaded["repair_resume_plan"]["manager_resume_action_count"], 1)
                self.assertNotIn("experiment_manager_resume_actions", loaded["repair_resume_plan"])
                self.assertNotIn("repair_context", loaded["repair_resume_plan"])
                self.assertNotIn("private manager action must not leak", json.dumps(loaded["repair_resume_plan"], ensure_ascii=False))
                self.assertNotIn("private release action must not leak", json.dumps(loaded["repair_resume_plan"], ensure_ascii=False))
                self.assertEqual(loaded["experiment_manager"]["status"], "review_required")
                self.assertEqual(loaded["experiment_manager"]["execution_policy"], "smoke_first")
                self.assertEqual(loaded["experiment_manager"]["next_candidates"], 1)
                self.assertEqual(loaded["experiment_manager"]["queue_total"], 2)
                self.assertEqual(loaded["experiment_manager"]["queue_human_review"], 1)
                self.assertEqual(loaded["experiment_manager"]["queue_ready_backlog"], 1)
                self.assertNotIn("manager_queue", loaded["experiment_manager"])
                self.assertNotIn("repair_context", loaded["experiment_manager"])
                self.assertEqual(loaded["idea_experiment_gate"]["status"], "block")
                self.assertEqual(loaded["idea_experiment_gate"]["novelty_status"], "review_required")
                self.assertEqual(loaded["idea_experiment_gate"]["idea_audit_status"], "review")
                self.assertEqual(loaded["idea_experiment_gate"]["experiment_manager_status"], "review_required")
                self.assertEqual(loaded["idea_experiment_gate"]["experiment_audit_status"], "block")
                self.assertEqual(loaded["idea_experiment_gate"]["contract_status"], "review_required")
                self.assertEqual(loaded["idea_experiment_gate"]["execution_safety_status"], "block")
                self.assertEqual(loaded["idea_experiment_gate"]["benchmark_plan_status"], "review_required")
                self.assertEqual(loaded["idea_experiment_gate"]["benchmark_readiness_status"], "block")
                self.assertEqual(loaded["idea_experiment_gate"]["benchmark_adapter_status"], "blocked")
                self.assertEqual(loaded["idea_experiment_gate"]["selected_idea_title"], "谨慎分支")
                self.assertEqual(loaded["idea_experiment_gate"]["execution_mode"], "benchmark")
                self.assertEqual(loaded["idea_experiment_gate"]["blocking_issues"], 5)
                self.assertEqual(loaded["idea_experiment_gate"]["manual_tasks"], 10)
                self.assertEqual(loaded["idea_experiment_gate"]["warnings"], 6)
                self.assertEqual(loaded["idea_experiment_gate"]["safety_blocking_issues"], 1)
                self.assertEqual(loaded["idea_experiment_gate"]["benchmark_blocking_issues"], 2)
                self.assertEqual(loaded["idea_experiment_gate"]["benchmark_candidates"], 2)
                self.assertEqual(loaded["idea_experiment_gate"]["benchmark_manual_tasks"], 3)
                self.assertIn("批准执行前", loaded["idea_experiment_gate"]["approval_hint"])
                self.assertNotIn("repair_context", loaded["idea_experiment_gate"])
                self.assertEqual(loaded["benchmark_schema"]["status"], "block")
                self.assertEqual(loaded["benchmark_schema"]["execution_mode"], "benchmark")
                self.assertEqual(loaded["benchmark_schema"]["benchmark_expected_metrics"], 2)
                self.assertEqual(loaded["benchmark_schema"]["adapter_provenance"], 1)
                self.assertEqual(loaded["benchmark_schema"]["blocking_issues"], 1)
                self.assertEqual(loaded["benchmark_schema"]["manual_tasks"], 1)
                self.assertEqual(loaded["benchmark_schema"]["warnings"], 1)
                self.assertEqual(loaded["literature_search_feedback"]["status"], "needs_search_revision")
                self.assertEqual(loaded["literature_search_feedback"]["recommended_queries"], 1)
                self.assertEqual(loaded["literature_search_feedback"]["agent_queries"], 1)
                self.assertEqual(loaded["literature_search_feedback"]["next_run_config"]["literature_provider"], "online")
                self.assertEqual(loaded["literature_quality_gate"]["status"], "review_required")
                self.assertEqual(loaded["literature_quality_gate"]["raw_papers"], 3)
                self.assertEqual(loaded["literature_quality_gate"]["selected_papers"], 2)
                self.assertEqual(loaded["literature_quality_gate"]["search_strategy_status"], "review_required")
                self.assertEqual(loaded["literature_quality_gate"]["feedback_status"], "needs_search_revision")
                self.assertEqual(loaded["literature_quality_gate"]["rescue_status"], "needs_rescue_search")
                self.assertEqual(loaded["literature_quality_gate"]["rescue_execution_status"], "no_new_papers")
                self.assertEqual(loaded["literature_quality_gate"]["seed_role_coverage_status"], "review_required")
                self.assertEqual(
                    loaded["literature_quality_gate"]["missing_roles"],
                    ["review_survey", "benchmark_dataset", "baseline_method"],
                )
                self.assertEqual(loaded["literature_quality_gate"]["repair_queries"], 6)
                self.assertEqual(loaded["literature_quality_gate"]["suggested_seed_count"], 3)
                self.assertGreaterEqual(loaded["literature_quality_gate"]["manual_tasks"], 3)
                self.assertIn("批准进入 idea 前", loaded["literature_quality_gate"]["approval_hint"])
                self.assertEqual(loaded["literature_search_strategy"]["status"], "review_required")
                self.assertEqual(loaded["literature_search_strategy"]["missing_required_intents"], ["baseline", "benchmark"])
                self.assertEqual(loaded["literature_retrieval_gate"]["status"], "review_required")
                self.assertEqual(loaded["literature_retrieval_gate"]["source_health_status"], "review_required")
                self.assertEqual(loaded["literature_retrieval_gate"]["query_execution_status"], "needs_query_repair")
                self.assertEqual(loaded["literature_retrieval_gate"]["rerank_status"], "review_required")
                self.assertEqual(loaded["literature_retrieval_gate"]["coverage_status"], "needs_coverage")
                self.assertEqual(loaded["literature_retrieval_gate"]["evidence_mix_status"], "needs_evidence_upgrade")
                self.assertEqual(loaded["literature_retrieval_gate"]["configured_sources"], 3)
                self.assertEqual(loaded["literature_retrieval_gate"]["sources_with_success"], 1)
                self.assertEqual(loaded["literature_retrieval_gate"]["rate_limited_sources"], 1)
                self.assertEqual(loaded["literature_retrieval_gate"]["failed_sources"], 1)
                self.assertEqual(loaded["literature_retrieval_gate"]["rate_limited_source_names"], ["semantic_scholar"])
                self.assertEqual(loaded["literature_retrieval_gate"]["failed_source_names"], ["crossref"])
                self.assertEqual(loaded["literature_retrieval_gate"]["query_attempts"], 2)
                self.assertEqual(loaded["literature_retrieval_gate"]["query_successes"], 1)
                self.assertEqual(loaded["literature_retrieval_gate"]["selected_queries"], 2)
                self.assertEqual(loaded["literature_retrieval_gate"]["raw_candidates"], 3)
                self.assertEqual(loaded["literature_retrieval_gate"]["queries_with_zero_source_results"], 1)
                self.assertEqual(loaded["literature_retrieval_gate"]["missing_required_intents"], ["benchmark"])
                self.assertEqual(loaded["literature_retrieval_gate"]["covered_top_count"], 2)
                self.assertEqual(loaded["literature_retrieval_gate"]["top_count"], 5)
                self.assertEqual(loaded["literature_retrieval_gate"]["covered_required"], 2)
                self.assertEqual(loaded["literature_retrieval_gate"]["total_required"], 4)
                self.assertEqual(loaded["literature_retrieval_gate"]["manual_tasks"], 5)
                self.assertEqual(loaded["literature_retrieval_gate"]["warnings"], 4)
                self.assertIn("批准进入 idea 前", loaded["literature_retrieval_gate"]["approval_hint"])
                self.assertNotIn("queries", loaded["literature_retrieval_gate"])
                self.assertEqual(loaded["literature_rescue_plan"]["status"], "needs_rescue_search")
                self.assertEqual(loaded["literature_rescue_plan"]["coverage_status"], "needs_coverage")
                self.assertEqual(loaded["literature_rescue_plan"]["missing_evidence_roles"], ["review_survey", "benchmark_dataset"])
                self.assertEqual(loaded["literature_rescue_plan"]["weak_reasons"], 1)
                self.assertEqual(loaded["literature_rescue_plan"]["source_repairs"], 1)
                self.assertEqual(loaded["literature_rescue_plan"]["rescue_queries"], 3)
                self.assertEqual(
                    loaded["literature_rescue_plan"]["role_queries"],
                    [
                        "robot manipulator motion planning survey review systematic review benchmark",
                        "robot manipulator motion planning benchmark dataset evaluation testbed",
                    ],
                )
                self.assertIn("robot manipulator motion planning benchmark OMPL MoveIt RRT*", loaded["literature_rescue_plan"]["top_queries"])
                self.assertNotIn("repair_context", loaded["literature_rescue_plan"])
                self.assertEqual(loaded["literature_rescue_execution"]["status"], "no_new_papers")
                self.assertEqual(loaded["literature_rescue_execution"]["unresolved_query_outcomes"], 1)
                self.assertEqual(loaded["literature_rescue_execution"]["repair_tasks"], 1)
                self.assertEqual(loaded["literature_rescue_execution"]["required_actions"], 1)
                self.assertEqual(loaded["literature_rescue_execution"]["unresolved_queries"], ["robot manipulator OMPL benchmark"])
                self.assertEqual(loaded["seed_intake"]["status"], "pass")
                self.assertEqual(loaded["seed_intake"]["role_coverage_status"], "review_required")
                self.assertEqual(loaded["seed_intake"]["total_seed_entries"], 3)
                self.assertEqual(loaded["seed_intake"]["curated_seed_papers"], 2)
                self.assertEqual(loaded["seed_intake"]["missing_roles"], ["review", "benchmark_dataset"])
                self.assertEqual(
                    loaded["seed_intake"]["role_repair_queries"],
                    [
                        "可用性审计 survey review state of the art",
                        "可用性审计 benchmark dataset evaluation protocol",
                    ],
                )
                self.assertEqual(loaded["seed_intake"]["suggested_seed_count"], 3)
                self.assertEqual(
                    loaded["seed_intake"]["suggested_seed_entries"],
                    [
                        "https://example.test/robot-survey Survey of robot manipulator motion planning methods",
                        "10.1109/MRA.2012.2205651 OMPL benchmark suite for robot manipulator motion planning",
                        "10.1109/ICRA.2009.5152817 CHOMP robot manipulator trajectory optimization",
                    ],
                )
                self.assertEqual(loaded["seed_intake"]["suggested_seed_role_counts"]["review"], 1)
                self.assertEqual(loaded["seed_intake"]["suggested_seed_role_counts"]["benchmark_dataset"], 1)
                self.assertEqual(loaded["seed_intake"]["suggested_seed_role_counts"]["baseline_method"], 3)
                self.assertEqual(loaded["seed_intake"]["required_actions"], 1)
                self.assertEqual(loaded["seed_intake"]["warnings"], 1)
                self.assertNotIn("items", loaded["seed_intake"])
                self.assertNotIn("seed_entries", loaded["seed_intake"])
                self.assertEqual(loaded["run_integrity"]["status"], "warn")
                self.assertEqual(loaded["run_integrity"]["checks"], 12)
                self.assertEqual(loaded["run_integrity"]["pass"], 10)
                self.assertEqual(loaded["run_integrity"]["warn"], 1)
                self.assertEqual(loaded["run_integrity"]["block"], 0)
                self.assertEqual(loaded["run_integrity"]["required_artifacts"], 120)
                self.assertEqual(loaded["run_integrity"]["blocking_issues"], 0)
                self.assertEqual(loaded["run_integrity"]["warnings"], 1)
                self.assertEqual(loaded["run_integrity"]["recommended_actions"], 1)
                self.assertEqual(loaded["final_handoff"]["status"], "ready_for_human_handoff")
                self.assertEqual(loaded["final_handoff"]["package_zip"], "11-submission-package.zip")
                self.assertTrue(loaded["final_handoff"]["package_zip_exists"])
                self.assertFalse(loaded["final_handoff"]["package_zip_valid"])
                self.assertFalse(loaded["final_handoff"]["package_has_integrity_audit"])
                self.assertEqual(loaded["final_handoff"]["blocking_issues"], 0)
                self.assertEqual(loaded["final_handoff"]["manual_tasks"], 1)
                self.assertEqual(loaded["final_handoff"]["recommended_actions"], 1)
                self.assertEqual(loaded["agent_trajectory"]["status"], "warn")
                self.assertEqual(loaded["agent_trajectory"]["pass"], 6)
                self.assertEqual(loaded["agent_trajectory"]["warn"], 2)
                self.assertEqual(loaded["agent_trajectory"]["block"], 0)
                self.assertEqual(loaded["agent_trajectory"]["not_started"], 0)
                self.assertEqual(loaded["agent_trajectory"]["manual_tasks"], 2)
                self.assertEqual(loaded["agent_trajectory"]["last_event"], "completed")
                self.assertEqual(loaded["agent_trajectory"]["event_count"], 42)
                self.assertEqual(loaded["agent_trajectory"]["backfilled_events"], 11)
                self.assertEqual(loaded["agent_trajectory"]["artifact_count"], 130)
                self.assertNotIn("timeline", loaded["agent_trajectory"])
                self.assertNotIn("phases", loaded["agent_trajectory"])
                self.assertNotIn("private manual task", json.dumps(loaded["agent_trajectory"], ensure_ascii=False))
                self.assertEqual(loaded["agent_observability"]["status"], "review_required")
                self.assertEqual(loaded["agent_observability"]["manifest_events"], 42)
                self.assertEqual(loaded["agent_observability"]["manifest_artifacts"], 130)
                self.assertEqual(loaded["agent_observability"]["llm_total_calls"], 8)
                self.assertEqual(loaded["agent_observability"]["llm_failed_calls"], 0)
                self.assertEqual(loaded["agent_observability"]["llm_budget_exceeded_calls"], 1)
                self.assertEqual(loaded["agent_observability"]["experiment_runs"], 2)
                self.assertEqual(loaded["agent_observability"]["repair_queue_status"], "needs_repair")
                self.assertEqual(loaded["agent_observability"]["blocking_issues"], 1)
                self.assertEqual(loaded["agent_observability"]["manual_tasks"], 2)
                self.assertEqual(loaded["agent_observability"]["warnings"], 1)
                self.assertEqual(loaded["agent_observability"]["prompt_utilization"], 0.91)
                self.assertNotIn("checks", loaded["agent_observability"])
                self.assertNotIn("recommended_actions", loaded["agent_observability"])
                self.assertNotIn("private observability", json.dumps(loaded["agent_observability"], ensure_ascii=False))
                self.assertIn("10-code-data-availability.json", loaded["artifacts"])
                self.assertIn("10-release-metadata.json", loaded["artifacts"])
                self.assertIn("02-exploration-map.json", web_server.ARTIFACTS)
                self.assertIn("02-exploration-map.svg", web_server.ARTIFACTS)
                self.assertIn("02-experiment-manager.json", web_server.ARTIFACTS)
                self.assertIn("02-novelty-audit.json", web_server.ARTIFACTS)
                self.assertIn("02-idea-audit.json", web_server.ARTIFACTS)
                self.assertIn("13-research-scorecard.json", web_server.ARTIFACTS)
                self.assertIn("run-llm-ledger.json", web_server.ARTIFACTS)
                self.assertIn("07-paper-review-calibration.json", web_server.ARTIFACTS)
                self.assertIn("09-revision-response-audit.json", web_server.ARTIFACTS)
                self.assertIn("00-preflight.json", web_server.ARTIFACTS)
                self.assertIn("00-human-brief.json", web_server.ARTIFACTS)
                self.assertIn("00-prior-run-lessons.json", web_server.ARTIFACTS)
                self.assertIn("00-prior-run-library.json", web_server.ARTIFACTS)
                self.assertIn("00-open-source-lessons.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-rerank.json", web_server.ARTIFACTS)
                self.assertIn("01-review-constraints.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-snowball.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-coverage.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-evidence-mix.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-gate-decision.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-rescue-plan.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-rescue-execution.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-search-feedback.json", web_server.ARTIFACTS)
                self.assertIn("01-query-execution-audit.json", web_server.ARTIFACTS)
                self.assertIn("01-seed-paper-intake.json", web_server.ARTIFACTS)
                self.assertIn("01-literature-metadata-audit.json", web_server.ARTIFACTS)
                self.assertIn("03-experiment-audit.json", web_server.ARTIFACTS)
                self.assertIn("03-idea-experiment-contract.json", web_server.ARTIFACTS)
                self.assertIn("03-review-constraint-compliance.json", web_server.ARTIFACTS)
                self.assertIn("03-execution-safety-audit.json", web_server.ARTIFACTS)
                self.assertIn("03-execution-approval.json", web_server.ARTIFACTS)
                self.assertIn("03-ablation-plan.json", web_server.ARTIFACTS)
                self.assertIn("03-preregistration.json", web_server.ARTIFACTS)
                self.assertIn("04-result-validation.json", web_server.ARTIFACTS)
                self.assertIn("04-failure-analysis.json", web_server.ARTIFACTS)
                self.assertIn("04-benchmark-result-schema-audit.json", web_server.ARTIFACTS)
                self.assertIn("04-benchmark-evidence-audit.json", web_server.ARTIFACTS)
                self.assertIn("04-environment-snapshot.json", web_server.ARTIFACTS)
                self.assertIn("04-experiment-decision.json", web_server.ARTIFACTS)
                self.assertIn("04-hypothesis-outcome.json", web_server.ARTIFACTS)
                self.assertIn("04-claim-boundary-preflight.json", web_server.ARTIFACTS)
                self.assertIn("03-benchmark-readiness.json", web_server.ARTIFACTS)
                self.assertIn("10-ai-disclosure.json", web_server.ARTIFACTS)
                self.assertIn("10-citation-grounding.json", web_server.ARTIFACTS)
                self.assertIn("10-citation-coverage.json", web_server.ARTIFACTS)
                self.assertIn("10-results-presentation.json", web_server.ARTIFACTS)
                self.assertIn("10-claim-consistency.json", web_server.ARTIFACTS)
                self.assertIn("run-recovery-plan.json", web_server.ARTIFACTS)
                self.assertIn("01-review-revision-plan.json", web_server.ARTIFACTS)
                self.assertIn("14-run-integrity-audit.json", web_server.ARTIFACTS)
                self.assertIn("14-final-handoff.json", web_server.ARTIFACTS)
                self.assertIn("12-repair-queue.json", web_server.ARTIFACTS)
                self.assertIn("12-repair-resume-plan.json", web_server.ARTIFACTS)
                self.assertIn("12-repair-resolution-audit.json", web_server.ARTIFACTS)
                self.assertIn("13-agent-stage-contract.json", web_server.ARTIFACTS)
                self.assertIn("13-agent-trajectory.json", web_server.ARTIFACTS)
                self.assertIn("13-llm-trace-audit.json", web_server.ARTIFACTS)
                self.assertIn("13-run-economics-audit.json", web_server.ARTIFACTS)
                self.assertIn("13-agent-observability-audit.json", web_server.ARTIFACTS)
                self.assertIn("13-open-source-compliance.json", web_server.ARTIFACTS)
                self.assertIn("11-submission-package.json", loaded["artifacts"])
                self.assertIn("12-next-iteration-plan.json", loaded["artifacts"])
                self.assertIn("12-repair-queue.json", loaded["artifacts"])
                self.assertIn("04-benchmark-result-schema-audit.json", loaded["artifacts"])
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_literature_gate_decision_public_summary_does_not_leak_private_text(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "literature-gate-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "01-literature-gate-decision.json",
                    {
                        "status": "block",
                        "decision": "hold_for_repair",
                        "blocks_downstream": True,
                        "human_approval_required": True,
                        "summary": {
                            "raw_papers": 2,
                            "selected_papers": 1,
                            "quality_confidence": "weak",
                            "quality_score": 0.42,
                            "coverage_status": "block",
                            "coverage_ratio": 0.25,
                            "citation_integrity_status": "block",
                            "citation_integrity_score": 0.3,
                            "context_citations": 2,
                            "context_chunks": 3,
                            "citation_grounding_status": "block",
                            "citation_grounding_score": 0.2,
                            "citation_grounding_blocked": 1,
                            "citation_grounding_review": 1,
                        },
                        "signals": [{"name": "private", "summary": "prompt_text should not leak"}],
                        "blocking_reasons": ["private issue text"],
                        "review_reasons": ["private review text"],
                        "required_actions": ["private action text"],
                        "approval_guidance": ["private guidance text"],
                        "repair_context": {"prompt_text": "secret repair prompt"},
                    },
                )

                loaded = web_server.RunStore().get("literature-gate-run")
                text = json.dumps(loaded, ensure_ascii=False)

                self.assertEqual(loaded["literature_gate_decision"]["status"], "block")
                self.assertTrue(loaded["literature_gate_decision"]["blocks_downstream"])
                self.assertEqual(loaded["literature_gate_decision"]["blocking_reason_count"], 1)
                self.assertEqual(loaded["literature_gate_decision"]["citation_grounding_status"], "block")
                self.assertEqual(loaded["literature_gate_decision"]["citation_grounding_blocked"], 1)
                self.assertEqual(loaded["literature_quality_gate"]["gate_decision_status"], "block")
                self.assertEqual(loaded["literature_quality_gate"]["citation_integrity_status"], "block")
                self.assertEqual(loaded["literature_quality_gate"]["citation_grounding_status"], "block")
                self.assertIn("01-literature-gate-decision.json", loaded["artifacts"])
                self.assertNotIn("repair_context", text)
                self.assertNotIn("prompt_text", text)
                self.assertNotIn("private issue text", text)
                self.assertNotIn("private action text", text)
                self.assertNotIn('"blocking_reasons"', text)
                self.assertNotIn('"required_actions"', text)
                self.assertNotIn('"signals"', text)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_human_gate_audit_public_summary_does_not_leak_private_text(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "human-gate-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "13-human-gate-audit.json",
                    {
                        "status": "block",
                        "summary": {
                            "review_approved": False,
                            "review_blocks": 0,
                            "downstream_artifacts": 2,
                            "downstream_stage": "completed",
                            "execution_approved": False,
                            "execution_mode": "benchmark",
                            "execution_artifacts": 1,
                            "repair_resume_status": "ready_to_resume_repair",
                            "repair_resume_applied": True,
                            "review_reapproval_required": True,
                            "execution_reapproval_required": True,
                        },
                        "checks": [{"gate": "review", "required_actions": ["private gate action must not leak"]}],
                        "blocking_issues": ["private gate issue must not leak"],
                        "manual_tasks": ["private manual task must not leak"],
                        "recommended_actions": ["private recommendation must not leak"],
                    },
                )

                loaded = web_server.RunStore().get("human-gate-run")
                text = json.dumps(loaded, ensure_ascii=False)

                self.assertEqual(loaded["human_gate_audit"]["status"], "block")
                self.assertEqual(loaded["human_gate_audit"]["downstream_artifacts"], 2)
                self.assertEqual(loaded["human_gate_audit"]["blocking_issue_count"], 1)
                self.assertTrue(loaded["human_gate_audit"]["repair_resume_applied"])
                self.assertTrue(loaded["human_gate_audit"]["review_reapproval_required"])
                self.assertTrue(loaded["human_gate_audit"]["execution_reapproval_required"])
                self.assertIn("13-human-gate-audit.json", loaded["artifacts"])
                self.assertNotIn("private gate issue", text)
                self.assertNotIn("private gate action", text)
                self.assertNotIn("private recommendation", text)
                self.assertNotIn('"blocking_issues"', text)
                self.assertNotIn('"recommended_actions"', text)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_repair_resolution_public_summary_does_not_leak_private_text(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "repair-resolution-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "12-repair-resolution-audit.json",
                    {
                        "status": "block",
                        "applied": True,
                        "rerun_from": "literature_review",
                        "queue_status": "blocked_repair_required",
                        "resolution_score": 0.25,
                        "remaining_items": [{"task_id": "RQ-001", "action": "private remaining action must not leak"}],
                        "resolved_items": [{"task_id": "RQ-002", "action": "private resolved action must not leak"}],
                        "new_items": [{"task_id": "RQ-003", "action": "private new action must not leak"}],
                        "blocking_issues": ["private repair issue must not leak"],
                        "manual_tasks": ["private repair manual must not leak"],
                        "required_actions": ["private repair required action must not leak"],
                    },
                )

                loaded = web_server.RunStore().get("repair-resolution-run")
                text = json.dumps(loaded, ensure_ascii=False)

                self.assertEqual(loaded["repair_resolution"]["status"], "block")
                self.assertTrue(loaded["repair_resolution"]["applied"])
                self.assertEqual(loaded["repair_resolution"]["remaining_items"], 1)
                self.assertEqual(loaded["repair_resolution"]["blocking_issue_count"], 1)
                self.assertIn("12-repair-resolution-audit.json", loaded["artifacts"])
                self.assertNotIn("private repair issue", text)
                self.assertNotIn("private remaining action", text)
                self.assertNotIn('"blocking_issues"', text)
                self.assertNotIn('"required_actions"', text)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_llm_runtime_contract_public_summary_does_not_leak_private_text(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "llm-runtime-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "13-llm-runtime-contract.json",
                    {
                        "status": "block",
                        "summary": {
                            "provider": "openai-compatible",
                            "model_configured": True,
                            "base_url_configured": True,
                            "api_key_persisted": False,
                            "call_budget_configured": True,
                            "prompt_budget_configured": False,
                            "pricing_configured": True,
                            "total_calls": 3,
                            "successful_calls": 2,
                            "failed_calls": 1,
                            "budget_exceeded_calls": 0,
                            "entries": 3,
                            "trace_status": "block",
                            "economics_status": "review_required",
                            "ai_disclosure_status": "needs_human_policy_check",
                        },
                        "checks": [{"evidence": "private runtime evidence must not leak"}],
                        "blocking_issues": ["private runtime issue must not leak"],
                        "manual_tasks": ["private runtime task must not leak"],
                        "warnings": ["private runtime warning must not leak"],
                        "recommended_actions": ["private runtime action must not leak"],
                    },
                )

                loaded = web_server.RunStore().get("llm-runtime-run")
                text = json.dumps(loaded, ensure_ascii=False)
                contract_text = json.dumps(loaded["llm_runtime_contract"], ensure_ascii=False)

                self.assertEqual(loaded["llm_runtime_contract"]["status"], "block")
                self.assertEqual(loaded["llm_runtime_contract"]["total_calls"], 3)
                self.assertEqual(loaded["llm_runtime_contract"]["blocking_issue_count"], 1)
                self.assertEqual(loaded["llm_runtime_contract"]["manual_task_count"], 1)
                self.assertIn("13-llm-runtime-contract.json", loaded["artifacts"])
                self.assertNotIn("private runtime", text)
                self.assertNotIn('"blocking_issues"', contract_text)
                self.assertNotIn('"recommended_actions"', contract_text)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_public_run_approval_summary_does_not_leak_full_gate_text(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "approval-summary-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "approval.json",
                    {
                        "approved": False,
                        "revision_requested": False,
                        "stage": "awaiting_review_approval",
                        "gate_status": "block",
                        "warnings": ["private warning text"],
                        "required_actions": ["private required action text"],
                        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                        "approval_policy": {"notes_required": True, "gate_status": "block", "warning_count": 1, "reason": "private reason text"},
                    },
                )

                loaded = web_server.RunStore().get("approval-summary-run")
                text = json.dumps(loaded, ensure_ascii=False)

                self.assertEqual(loaded["approval"]["gate_status"], "block")
                self.assertEqual(loaded["approval"]["warning_count"], 1)
                self.assertEqual(loaded["approval"]["required_action_count"], 1)
                self.assertTrue(loaded["approval"]["approval_policy"]["notes_required"])
                self.assertNotIn("private warning text", text)
                self.assertNotIn("private required action text", text)
                self.assertNotIn("private reason text", text)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_legacy_run_without_seed_intake_exposes_seed_role_repair(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "legacy-literature-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "01-literature-quality.json",
                    {
                        "items": [
                            {
                                "title": "The Open Motion Planning Library",
                                "doi": "10.1109/MRA.2012.2205651",
                                "url": "https://doi.org/10.1109/MRA.2012.2205651",
                                "quality_score": 0.94,
                                "selected": True,
                                "evidence_roles": ["benchmark_dataset", "baseline_method"],
                            },
                            {
                                "title": "CHOMP robot manipulator trajectory optimization",
                                "doi": "10.1109/ICRA.2009.5152817",
                                "url": "https://doi.org/10.1109/ICRA.2009.5152817",
                                "quality_score": 0.91,
                                "selected": True,
                                "evidence_roles": ["baseline_method"],
                            },
                        ]
                    },
                )
                store = web_server.RunStore()

                loaded = store.get("legacy-literature-run")

                self.assertEqual(loaded["seed_intake"]["status"], "not_configured")
                self.assertEqual(loaded["seed_intake"]["role_coverage_status"], "review_required")
                self.assertEqual(loaded["seed_intake"]["suggested_seed_count"], 2)
                self.assertEqual(loaded["seed_intake"]["suggested_seed_role_counts"]["benchmark_dataset"], 1)
                self.assertEqual(loaded["seed_intake"]["suggested_seed_role_counts"]["baseline_method"], 2)
                self.assertEqual(loaded["seed_intake"]["missing_roles"], ["review", "recent"])
                self.assertEqual(
                    loaded["seed_intake"]["role_repair_queries"],
                    [
                        "机械臂路径规划 survey review state of the art",
                        "机械臂路径规划 2024 2025 latest recent advances",
                    ],
                )
                self.assertEqual(
                    loaded["seed_intake"]["suggested_seed_entries"],
                    [
                        "10.1109/MRA.2012.2205651 The Open Motion Planning Library",
                        "10.1109/ICRA.2009.5152817 CHOMP robot manipulator trajectory optimization",
                    ],
                )
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_legacy_literature_run_exposes_retrieval_gate_from_diagnostics(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "legacy-retrieval-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "轴承故障诊断", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "01-literature.json",
                    {
                        "topic": "轴承故障诊断",
                        "papers": [
                            {"title": "CWRU Bearing Dataset", "source": "crossref", "sources": ["crossref"]},
                            {"title": "Paderborn Bearing Dataset", "source": "arxiv", "sources": ["arxiv"]},
                        ],
                        "source_diagnostics": [
                            "检索式: bearing fault diagnosis CWRU benchmark | Paderborn bearing fault diagnosis dataset",
                            "arxiv: 2 个检索式返回 12 条，用时 1.2s",
                            "crossref: query='bearing fault diagnosis CWRU benchmark' 检索失败：HTTP 500: upstream error",
                            "crossref: 2 个检索式返回 8 条，用时 2.4s",
                            "合并去重后 16 条，相关性过滤后 2 条。",
                        ],
                    },
                )
                write_json(run_dir / "approval.json", {"approved": False, "stage": "awaiting_review_approval"})
                store = web_server.RunStore()

                loaded = store.get("legacy-retrieval-run")

                gate = loaded["literature_retrieval_gate"]
                self.assertEqual(gate["status"], "review_required")
                self.assertTrue(gate["legacy_summary"])
                self.assertEqual(gate["source_health_status"], "legacy_summary")
                self.assertEqual(gate["configured_sources"], 2)
                self.assertEqual(gate["sources_with_success"], 2)
                self.assertEqual(gate["failed_sources"], 1)
                self.assertEqual(gate["failed_source_names"], ["crossref"])
                self.assertEqual(gate["selected_queries"], 2)
                self.assertEqual(gate["raw_candidates"], 2)
                self.assertIn("新版流程重跑文献阶段", gate["approval_hint"])
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_inactive_review_gate_run_can_be_approved_and_resumed(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_after_review_approval
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "resume-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "approval.json",
                    {
                        "topic": "机械臂路径规划",
                        "approved": False,
                        "stage": "awaiting_review_approval",
                        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    },
                )
                write_text(run_dir / "01-review-gate.md", "# 审核")
                historical_config = replace(
                    AgentConfig(),
                    llm=replace(AgentConfig().llm, model="resume-model", base_url="http://127.0.0.1:9/v1"),
                )
                web_server._write_run_config(run_dir, historical_config)
                _bind_review_approval(run_dir)

                def fake_resume(topic, out_dir, config):
                    write_json(out_dir / "state.json", {"topic": topic, "stage": "completed", "updated_at": "done"})
                    write_text(out_dir / "02-ideas.md", "# Ideas")

                web_server.resume_pipeline_after_review_approval = fake_resume
                store = web_server.RunStore()

                loaded = store.get("resume-run")
                self.assertEqual(loaded["status"], "waiting")
                self.assertFalse(loaded["worker_active"])

                result = store.approve_with_config(
                    "resume-run",
                    reviewer="test",
                    payload={},
                )
                self.assertTrue(result["approval"]["approved"])

                completed = _wait_for_completed(store, "resume-run")
                self.assertEqual(completed["stage"], "completed")
                self.assertEqual(completed["status"], "completed")
                self.assertFalse(completed["worker_active"])
                persisted = json.loads((run_dir / web_server.RUN_CONFIG_FILENAME).read_text(encoding="utf-8"))
                self.assertEqual(persisted["llm"]["model"], "resume-model")
                self.assertEqual(persisted["llm"]["api_key"], "")
                self.assertEqual(persisted["literature"]["semantic_scholar_api_key"], "")
                self.assertEqual(persisted["literature"]["openalex_api_key"], "")
                self.assertEqual(persisted["literature"]["contact_email"], "")
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_after_review_approval = original_resume

    def test_completed_run_with_repair_queue_can_repair_resume(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_repair_resume = web_server.resume_pipeline_from_repair_queue
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "repair-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "12-repair-queue.json",
                    {
                        "status": "blocked_repair_required",
                        "summary": {"total": 1, "block": 1, "high": 0, "medium": 0},
                        "items": [{"task_id": "RQ-001", "severity": "block", "rerun_from": "paper_rewrite", "status": "open"}],
                    },
                )
                web_server._write_run_config(run_dir, AgentConfig())

                def fake_repair_resume(topic, out_dir, config):
                    web_server._write_run_config(out_dir, config)
                    write_json(out_dir / "state.json", {"topic": topic, "stage": "completed", "updated_at": "done"})
                    write_text(out_dir / "12-repair-resume-plan.md", "# 修复恢复计划")
                    write_json(out_dir / "12-repair-resume-plan.json", {"status": "ready_to_resume_repair", "applied": True})

                web_server.resume_pipeline_from_repair_queue = fake_repair_resume
                store = web_server.RunStore()

                loaded = store.get("repair-run")
                self.assertEqual(loaded["status"], "completed")
                self.assertEqual(loaded["repair_queue"]["status"], "blocked_repair_required")

                result = store.repair_resume_with_config("repair-run", payload={"llm_model": "repair-model", "llm_base_url": "http://127.0.0.1:9/v1"})

                self.assertIsNotNone(result)
                completed = _wait_for_completed(store, "repair-run")
                self.assertEqual(completed["status"], "completed")
                self.assertIn("12-repair-resume-plan.json", completed["artifacts"])
                persisted = json.loads((run_dir / web_server.RUN_CONFIG_FILENAME).read_text(encoding="utf-8"))
                self.assertEqual(persisted["llm"]["model"], "repair-model")
                self.assertEqual(persisted["llm"]["api_key"], "")
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_from_repair_queue = original_repair_resume

    def test_repair_resume_preview_writes_plan_without_starting_worker_or_cleaning(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "repair-preview-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_json(run_dir / "01-literature.json", {"papers": []})
                write_text(run_dir / "06-paper.md", "# stale paper")
                write_json(
                    run_dir / "01-literature-search-feedback.json",
                    {
                        "retrieval_repair_tasks": [
                            {
                                "task_id": "retrieval-repair-001",
                                "owner": "agent",
                                "priority": 90,
                                "query": "robot manipulator OMPL benchmark",
                                "action": "补检索 benchmark/baseline 文献",
                            }
                        ],
                        "next_run_config": {
                            "literature_provider": "online",
                            "sources": ["semantic_scholar", "openalex"],
                            "max_papers": 12,
                            "max_search_queries": 6,
                        },
                    },
                )
                write_json(
                    run_dir / "12-repair-queue.json",
                    {
                        "status": "blocked_repair_required",
                        "summary": {"total": 1, "block": 1, "high": 0, "medium": 0},
                        "items": [
                            {
                                "task_id": "RQ-001",
                                "severity": "block",
                                "category": "literature_grounding",
                                "source_artifact": "01-literature-search-feedback.json",
                                "rerun_from": "literature_review",
                                "status": "open",
                                "action": "补齐真实 benchmark/baseline 文献后重跑。",
                            }
                        ],
                    },
                )
                write_json(
                    run_dir / "02-experiment-manager.json",
                    {
                        "status": "block",
                        "selected_branch_id": "B1",
                        "manager_decision": "needs_human_reselection",
                        "execution_policy": "blocked",
                        "required_actions": ["private manager required action must not leak in preview plan"],
                        "manager_queue": [
                            {
                                "branch_id": "B1",
                                "title": "private manager branch must not leak in preview plan",
                                "selected": True,
                                "queue_state": "blocked_human_repair",
                                "requires_human": True,
                                "blocks_current_experiment": True,
                                "resume_from": "ideation",
                                "issues": ["private manager issue must not leak in preview plan"],
                            }
                        ],
                    },
                )
                store = web_server.RunStore()

                result = store.preview_repair_resume("repair-preview-run")

                self.assertIsNotNone(result)
                self.assertFalse(result["plan"]["applied"])
                self.assertTrue(result["plan"]["can_resume"])
                self.assertEqual(result["plan"]["rerun_from"], "literature_review")
                self.assertIn("01-literature.json", result["plan"]["artifacts_to_remove"])
                self.assertIn("06-paper.md", result["plan"]["artifacts_to_remove"])
                self.assertEqual(result["plan"]["recommended_config"]["literature_provider"], "online")
                self.assertEqual(result["plan"]["retrieval_repair_tasks"], 1)
                self.assertEqual(result["plan"]["manager_resume_action_count"], 1)
                self.assertNotIn("experiment_manager_resume_actions", result["plan"])
                self.assertNotIn("repair_context", result["plan"])
                self.assertNotIn("private manager branch", json.dumps(result["plan"], ensure_ascii=False))
                self.assertIn("修复恢复预览", result["markdown"])
                preview_payload = json.dumps(result, ensure_ascii=False)
                self.assertNotIn("private manager required action", preview_payload)
                self.assertNotIn("private manager issue", preview_payload)
                self.assertNotIn("repair_context", preview_payload)
                self.assertTrue((run_dir / "01-literature.json").exists())
                self.assertTrue((run_dir / "06-paper.md").exists())
                self.assertFalse((run_dir / web_server.RUN_CONFIG_FILENAME).exists())
                self.assertEqual(result["run"]["status"], "completed")
                self.assertEqual(result["run"]["stage"], "completed")
                self.assertFalse(result["run"]["worker_active"])
                self.assertIn("12-repair-resume-plan.md", result["run"]["artifacts"])
                self.assertIn("12-repair-resume-plan.json", result["run"]["artifacts"])
                reloaded = store.get("repair-preview-run")
                self.assertEqual(reloaded["repair_resume_plan"]["status"], "ready_to_resume_repair")
                self.assertFalse(reloaded["repair_resume_plan"]["applied"])
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_repair_resume_artifact_endpoint_returns_public_plan(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "repair-artifact-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "test"})
                write_text(run_dir / "12-repair-resume-plan.md", "# private repair plan must not leak")
                write_json(
                    run_dir / "12-repair-resume-plan.json",
                    {
                        "schema_version": 1,
                        "topic": "机械臂路径规划",
                        "status": "ready_to_resume_repair",
                        "applied": False,
                        "can_resume": True,
                        "queue_status": "blocked_repair_required",
                        "rerun_from": "literature_review",
                        "repair_items": [{"task_id": "RQ-001", "action": "private repair action must not leak"}],
                        "retrieval_repair_tasks": [{"query": "private query must not leak"}],
                        "recommended_config": {
                            "literature_provider": "online",
                            "sources": ["semantic_scholar", "openalex"],
                            "max_papers": 12,
                            "max_search_queries": 6,
                        },
                        "recommended_execution_config": {
                            "execution_mode": "benchmark",
                            "allowed_commands": ["python3"],
                            "execution_repeats": 5,
                            "timeout_seconds": 300,
                            "benchmark_manifest_paths": ["benchmarks/robotics/manifest.json"],
                        },
                        "recommended_paper_grade_config": {
                            "enabled": True,
                            "reasons": ["private paper-grade reason must not leak"],
                            "trigger_count": 1,
                            "min_execution_repeats": 5,
                        },
                        "recommended_release_config": {
                            "status": "needs_input",
                            "required_fields": ["release_code_repository_url"],
                            "recommended_fields": ["release_data_archive_doi"],
                            "cli_args": ["--release-code-repository-url", "--release-data-archive-doi"],
                            "field_actions": {
                                "release_code_repository_url": {
                                    "action": "private release action must not leak",
                                    "recommended_value": "",
                                }
                            },
                        },
                        "experiment_manager_resume_actions": [
                            {
                                "title": "private manager branch must not leak",
                                "queue_state": "blocked_human_repair",
                                "action": "private manager action must not leak",
                            }
                        ],
                        "recommended_seed_papers": ["private seed paper must not leak"],
                        "repair_context": {"prompt_text": "private repair prompt must not leak"},
                        "review_reapproval_required": True,
                        "execution_reapproval_required": True,
                        "artifacts_to_remove": ["01-literature.json"],
                        "directories_to_remove": [],
                        "removed_artifacts": [],
                        "removed_directories": [],
                        "stop_conditions": ["private stop condition must not leak"],
                    },
                )
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}/api/runs/{quote('repair-artifact-run')}/artifact"

                with urllib.request.urlopen(f"{base}?file=12-repair-resume-plan.json", timeout=5) as response:
                    public_text = response.read().decode("utf-8")
                public_json = json.loads(public_text)
                self.assertEqual(public_json["status"], "ready_to_resume_repair")
                self.assertTrue(public_json["can_resume"])
                self.assertEqual(public_json["repair_items"], 1)
                self.assertEqual(public_json["retrieval_repair_tasks"], 1)
                self.assertEqual(public_json["manager_resume_action_count"], 1)
                self.assertEqual(public_json["recommended_seed_paper_count"], 1)
                self.assertEqual(public_json["recommended_execution_config"]["benchmark_manifest_paths"], ["benchmarks/robotics/manifest.json"])
                self.assertTrue(public_json["recommended_paper_grade_config"]["enabled"])
                self.assertEqual(public_json["recommended_paper_grade_config"]["trigger_count"], 1)
                self.assertEqual(public_json["recommended_release_config"]["required_fields"], ["release_code_repository_url"])
                self.assertEqual(public_json["recommended_release_config"]["cli_args"], ["--release-code-repository-url", "--release-data-archive-doi"])
                public_payload = json.dumps(public_json, ensure_ascii=False)
                for needle in [
                    "repair_context",
                    "prompt_text",
                    "private repair",
                    "private paper-grade",
                    "private manager",
                    "private query",
                    "private seed",
                    "blocked_human_repair",
                    "experiment_manager_resume_actions",
                    "recommended_seed_papers",
                    "private release",
                    "field_actions",
                ]:
                    self.assertNotIn(needle, public_payload)

                with urllib.request.urlopen(f"{base}?file=12-repair-resume-plan.md", timeout=5) as response:
                    public_markdown = response.read().decode("utf-8")
                self.assertIn("修复恢复预览", public_markdown)
                self.assertIn("benchmarks/robotics/manifest.json", public_markdown)
                self.assertIn("paper_grade_enabled：`True`", public_markdown)
                self.assertIn("release_required_fields：`release_code_repository_url`", public_markdown)
                self.assertIn("--release-code-repository-url", public_markdown)
                for needle in [
                    "repair_context",
                    "prompt_text",
                    "private repair",
                    "private paper-grade",
                    "private manager",
                    "private query",
                    "private seed",
                    "blocked_human_repair",
                    "experiment_manager_resume_actions",
                    "recommended_seed_papers",
                    "private release",
                    "field_actions",
                ]:
                    self.assertNotIn(needle, public_markdown)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

    def test_gold_run_doctor_artifact_endpoint_returns_public_summary(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "doctor-artifact-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                write_json(run_dir / "state.json", {"topic": "Iris", "stage": "completed", "updated_at": "test"})
                write_text(run_dir / "00-gold-run-doctor.md", "# private doctor markdown must not leak")
                write_text(run_dir / "00-gold-launch-manifest.md", "# private launch markdown must not leak")
                write_json(
                    run_dir / "00-gold-launch-manifest.json",
                    {
                        "schema_version": 1,
                        "topic": "Iris classification benchmark smoke",
                        "status": "blocked",
                        "can_start_gold_run": False,
                        "doctor_status": "blocked",
                        "preflight_status": "fail",
                        "check_status_counts": {"fail": 2, "warn": 1, "private_status": 99},
                        "failed_checks": ["llm_api_key", "literature_contact_email"],
                        "warn_checks": ["semantic_scholar_key"],
                        "launch_checklist": [
                            {"item": "doctor_ready", "status": "block", "evidence": "private launch evidence must not leak"},
                            {"item": "release_metadata", "status": "pass", "evidence": "release ready"},
                        ],
                        "secret_handling": {
                            "secrets_in_config": True,
                            "direct_secret_fields": ["llm_api_key"],
                            "private": "unit-test-api-token must not leak",
                        },
                        "literature": {
                            "provider": "online",
                            "sources": ["openalex", "crossref"],
                            "seed_papers": 3,
                            "doi_url_seed_papers": 3,
                            "fulltext_paths": 1,
                            "paper_grade_ready": True,
                        },
                        "benchmark": {
                            "execution_mode": "benchmark",
                            "execution_repeats": 3,
                            "benchmark_manifest_paths": 3,
                            "benchmark_ready": True,
                            "standalone_pack_run_id": str(root / "runs" / "benchmark-safe-run"),
                        },
                        "fulltext_grounding": {"standalone_run_id": str(root / "runs" / "fulltext-safe-run")},
                        "candidate_run": {"run_id": str(root / "runs" / "candidate-safe-run")},
                        "release_metadata": {"required_ready": False, "missing_required_fields": ["release_code_archive_doi"]},
                        "required_human_gates": ["01-review-gate approval"],
                        "required_final_evidence": ["private final evidence must not leak"],
                        "safe_commands": ['export OPENAI_API_KEY="unit-test-api-token"'],
                    },
                )
                write_json(
                    run_dir / "00-gold-run-doctor.json",
                    {
                        "schema_version": 1,
                        "topic": "Iris classification benchmark smoke",
                        "status": "blocked",
                        "preflight_status": "fail",
                        "checks": [
                            {
                                "name": "llm_api_key",
                                "status": "fail",
                                "detail": "unit-test-api-token private key detail must not leak",
                                "action": "private credential action must not leak",
                            },
                            {
                                "name": "literature_contact_email",
                                "status": "fail",
                                "detail": "researcher@university.edu must not leak",
                            },
                            {
                                "name": "candidate_gold_run",
                                "status": "fail",
                                "action": "private candidate action must not leak",
                                "repair_plan": [
                                    {
                                        "id": "submission_package",
                                        "priority": 70,
                                        "rerun_from": "submission_package",
                                        "source_artifact": "11-submission-package.json",
                                        "target_artifacts": ["11-submission-package.json", "11-submission-package.zip"],
                                        "action": "private repair action must not leak",
                                    }
                                ],
                            },
                        ],
                        "preflight": [
                            {"name": "llm_ping", "status": "fail", "detail": "private ping detail must not leak"},
                            {"name": "paper_grade_mode", "status": "pass"},
                        ],
                        "launch_manifest": {
                            "status": "blocked",
                            "can_start_gold_run": False,
                            "launch_checklist": [
                                {"item": "doctor_ready", "status": "block", "evidence": "private launch evidence must not leak"},
                                {"item": "release_metadata", "status": "pass", "evidence": "release ready"},
                            ],
                            "secret_handling": {"direct_secret_fields": ["llm_api_key"]},
                        },
                        "commands": ['export OPENAI_API_KEY="unit-test-api-token"'],
                        "candidate_repair_resume_plan": {
                            "status": "written",
                            "candidate_run_dir": str(root / "runs" / "candidate-safe-run"),
                            "doctor_report_path": str(run_dir / "00-gold-run-doctor.json"),
                            "plan_json": str(root / "runs" / "candidate-safe-run" / "12-repair-resume-plan.json"),
                            "plan_md": str(root / "runs" / "candidate-safe-run" / "12-repair-resume-plan.md"),
                            "can_resume": True,
                            "rerun_from": "submission_package",
                            "repair_items": 1,
                        },
                    },
                )
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}/api/runs/{quote('doctor-artifact-run')}/artifact"

                with urllib.request.urlopen(f"{base}?file=00-gold-run-doctor.json", timeout=5) as response:
                    public_text = response.read().decode("utf-8")
                public_json = json.loads(public_text)
                self.assertEqual(public_json["status"], "blocked")
                self.assertEqual(public_json["preflight_status"], "fail")
                self.assertEqual(public_json["launch_status"], "blocked")
                self.assertFalse(public_json["can_start_gold_run"])
                self.assertEqual(public_json["launch_check_status_counts"]["block"], 1)
                self.assertEqual(public_json["launch_check_status_counts"]["pass"], 1)
                self.assertEqual(public_json["launch_checklist"][0]["item"], "doctor_ready")
                self.assertIn("Gold Doctor", public_json["launch_checklist"][0]["button"])
                self.assertIn("rerun Gold Doctor", public_json["launch_checklist"][0]["next_step"])
                self.assertNotIn("evidence", public_json["launch_checklist"][0])
                self.assertTrue(any("doctor_ready=block" in item for item in public_json["launch_next_steps"]))
                self.assertIn("llm_api_key", public_json["failed_checks"])
                self.assertEqual(public_json["candidate_repair_plan_items"], 1)
                self.assertEqual(public_json["candidate_repair_plan"][0]["id"], "submission_package")
                self.assertEqual(public_json["candidate_repair_resume_plan"]["candidate_run_id"], "candidate-safe-run")
                self.assertEqual(public_json["candidate_repair_resume_plan"]["plan_json"], "12-repair-resume-plan.json")
                self.assertEqual(public_json["command_count"], 1)
                public_payload = json.dumps(public_json, ensure_ascii=False)
                for needle in [
                    "unit-test-api-token",
                    "researcher@university.edu",
                    "private",
                    str(root),
                    "OPENAI_API_KEY",
                    "action",
                    "detail",
                    "commands",
                ]:
                    self.assertNotIn(needle, public_payload)

                with urllib.request.urlopen(f"{base}?file=00-gold-run-doctor.md", timeout=5) as response:
                    public_markdown = response.read().decode("utf-8")
                self.assertIn("Gold Run Doctor 摘要", public_markdown)
                self.assertIn("candidate-safe-run", public_markdown)
                for needle in [
                    "unit-test-api-token",
                    "researcher@university.edu",
                    "private",
                    str(root),
                    "OPENAI_API_KEY",
                    "action",
                    "detail",
                    "commands",
                ]:
                    self.assertNotIn(needle, public_markdown)

                with urllib.request.urlopen(f"{base}?file=00-gold-launch-manifest.json", timeout=5) as response:
                    launch_text = response.read().decode("utf-8")
                launch_json = json.loads(launch_text)
                self.assertEqual(launch_json["status"], "blocked")
                self.assertEqual(launch_json["doctor_status"], "blocked")
                self.assertEqual(launch_json["preflight_status"], "fail")
                self.assertEqual(launch_json["check_status_counts"], {"fail": 2, "warn": 1})
                self.assertEqual(launch_json["blocking_launch_items"], ["doctor_ready"])
                self.assertEqual(launch_json["launch_checklist"][0]["item"], "doctor_ready")
                self.assertEqual(launch_json["launch_checklist"][0]["form_fields"], [])
                self.assertIn("rerun Gold Doctor", launch_json["launch_checklist"][0]["next_step"])
                self.assertNotIn("evidence", launch_json["launch_checklist"][0])
                self.assertEqual(launch_json["launch_next_steps"], ["doctor_ready=block; button=Gold Doctor; Resolve failed Gold Doctor checks, then rerun Gold Doctor."])
                self.assertEqual(launch_json["benchmark_pack_run_id"], "benchmark-safe-run")
                self.assertEqual(launch_json["fulltext_grounding_run_id"], "fulltext-safe-run")
                self.assertEqual(launch_json["candidate_run_id"], "candidate-safe-run")
                self.assertEqual(launch_json["required_final_evidence"], 1)
                self.assertEqual(launch_json["command_count"], 1)
                for needle in [
                    "unit-test-api-token",
                    "researcher@university.edu",
                    "private",
                    str(root),
                    "OPENAI_API_KEY",
                    "private launch evidence",
                    "private final evidence",
                    "safe_commands",
                ]:
                    self.assertNotIn(needle, launch_text)

                with urllib.request.urlopen(f"{base}?file=00-gold-launch-manifest.md", timeout=5) as response:
                    launch_markdown = response.read().decode("utf-8")
                self.assertIn("Gold Launch Manifest 摘要", launch_markdown)
                self.assertIn("candidate-safe-run", launch_markdown)
                for needle in [
                    "unit-test-api-token",
                    "researcher@university.edu",
                    "private",
                    str(root),
                    "OPENAI_API_KEY",
                    "private launch evidence",
                    "private final evidence",
                    "safe_commands",
                ]:
                    self.assertNotIn(needle, launch_markdown)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

    def test_gold_run_verify_api_and_artifact_endpoint_return_public_summary(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = _write_gold_verification_candidate(runs_dir / "verify-run", package_status="blocked")
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                write_text(run_dir / "15-gold-run-verification.md", "# private verification markdown must not leak")
                write_json(
                    run_dir / "15-gold-run-verification.json",
                    {
                        "schema_version": 1,
                        "status": "blocked",
                        "gold_contract_ready": False,
                        "run_dir": str(run_dir),
                        "required_artifacts": ["11-submission-package.json", "14-final-handoff.json"],
                        "missing_artifacts": ["11-submission-package.json"],
                        "unsafe_artifacts": [
                            {"path": "11-submission-package.json", "issue": "symlink", "target": f"private target {root}"}
                        ],
                        "artifact_safety": {
                            "status": "blocked",
                            "checked_artifacts": 2,
                            "unsafe_artifacts": [
                                {"path": "11-submission-package.json", "issue": "symlink", "target": f"private target {root}"}
                            ],
                        },
                        "manifest_inventory": {
                            "status": "blocked",
                            "missing_required_artifacts": ["11-submission-package.json"],
                            "hash_mismatches": [],
                            "size_mismatches": ["11-submission-package.json"],
                            "duplicate_required_artifacts": ["14-final-handoff.json"],
                            "unsafe_artifact_paths": [{"path": f"private/{root}/escape.json", "issue": "absolute"}],
                        },
                        "check": {
                            "name": "candidate_gold_run",
                            "status": "fail",
                            "detail": f"sk-unit-test-secret private detail {root}",
                            "action": "private action must not leak",
                        },
                        "contract_evidence": {
                            "audit_contracts_ready": False,
                            "audit_contract_ready_count": 0,
                            "audit_contract_total": 1,
                            "audit_contract_blocking_issues": 1,
                            "audit_contract_manual_tasks": 1,
                            "audit_contracts": {
                                "llm_trace": {
                                    "status": "private audit status must not leak",
                                    "blocking_issues": 1,
                                    "manual_tasks": 1,
                                    "ready": False,
                                }
                            },
                        },
                        "repair_plan": [
                            {
                                "id": "submission_package",
                                "priority": 70,
                                "rerun_from": "submission_package",
                                "source_artifact": "11-submission-package.json",
                                "target_artifacts": ["11-submission-package.json", "11-submission-package.zip"],
                                "action": "private repair action must not leak",
                            }
                        ],
                        "read_only": True,
                    },
                )
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()

                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/gold-run-verify",
                    data=json.dumps({"candidate_run_id": "verify-run", "llm_api_key": "unit-test-api-token"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    api_text = response.read().decode("utf-8")
                api_data = json.loads(api_text)
                api_report = api_data["report"]
                self.assertEqual(api_report["status"], "blocked")
                self.assertFalse(api_report["gold_contract_ready"])
                self.assertEqual(api_report["candidate_run_id"], "verify-run")
                self.assertEqual(api_report["missing_artifact_count"], 0)
                self.assertEqual(api_report["unsafe_artifact_count"], 0)
                self.assertEqual(api_report["secret_scan_status"], "blocked")
                self.assertGreaterEqual(api_report["secret_scan_findings"], 1)
                self.assertIn("15-gold-run-verification.json", api_report["secret_scan_paths"])
                self.assertTrue(api_report["audit_contracts_ready"])
                self.assertEqual(api_report["audit_contract_ready_count"], 7)
                self.assertEqual(api_report["audit_contract_total"], 7)
                self.assertEqual(api_report["audit_contract_manual_tasks"], 0)
                self.assertEqual(api_report["audit_contracts"]["run_economics"]["status"], "pass")
                self.assertEqual(api_report["repair_plan_items"], 1)
                self.assertEqual(api_report["repair_plan"][0]["id"], "submission_package")
                self.assertIn("Gold Run Verification 摘要", api_data["markdown"])
                self.assertFalse(api_data["read_only"])
                self.assertTrue(api_data["wrote_artifacts"])
                self.assertTrue(api_data["perfect_readiness_written"])
                self.assertEqual(api_data["repair_resume_plan"]["status"], "ready_to_resume_repair")
                self.assertEqual(api_data["repair_resume_plan"]["repair_items"], 1)
                self.assertNotIn("run", api_data)
                for needle in ["unit-test-api-token", "sk-unit-test-secret", "private", str(root), "detail", "private repair action", "llm_api_key"]:
                    self.assertNotIn(needle, api_text)

                base = f"http://127.0.0.1:{server.server_port}/api/runs/{quote('verify-run')}/artifact"
                with urllib.request.urlopen(f"{base}?file=15-gold-run-verification.json", timeout=5) as response:
                    public_text = response.read().decode("utf-8")
                public_json = json.loads(public_text)
                self.assertEqual(public_json["status"], "blocked")
                self.assertEqual(public_json["candidate_run_id"], "verify-run")
                self.assertEqual(public_json["missing_artifacts"], [])
                self.assertEqual(public_json["artifact_safety_status"], "pass")
                self.assertEqual(public_json["unsafe_artifact_count"], 0)
                self.assertEqual(public_json["unsafe_artifacts"], [])
                self.assertEqual(public_json["manifest_inventory_size_mismatch_count"], 0)
                self.assertEqual(public_json["manifest_inventory_duplicate_count"], 0)
                self.assertEqual(public_json["manifest_inventory_unsafe_path_count"], 0)
                self.assertEqual(public_json["audit_contract_ready_count"], 7)
                self.assertEqual(public_json["audit_contract_total"], 7)
                self.assertEqual(public_json["audit_contract_blocking_issues"], 0)
                self.assertEqual(public_json["audit_contract_manual_tasks"], 0)
                self.assertEqual(public_json["audit_contracts"]["llm_trace"]["status"], "pass")
                self.assertEqual(public_json["repair_plan"][0]["target_artifacts"], ["11-submission-package.json", "11-submission-package.zip"])
                for needle in ["unit-test-api-token", "sk-unit-test-secret", "private", str(root), "detail", "private repair action"]:
                    self.assertNotIn(needle, public_text)

                with urllib.request.urlopen(f"{base}?file=12-repair-resume-plan.json", timeout=5) as response:
                    repair_text = response.read().decode("utf-8")
                repair_json = json.loads(repair_text)
                self.assertEqual(repair_json["status"], "ready_to_resume_repair")
                self.assertEqual(repair_json["repair_items"], 1)
                self.assertNotIn("private repair action", repair_text)

                with urllib.request.urlopen(f"{base}?file=15-gold-run-verification.md", timeout=5) as response:
                    public_markdown = response.read().decode("utf-8")
                self.assertIn("Gold Run Verification 摘要", public_markdown)
                self.assertIn("verify-run", public_markdown)
                for needle in ["unit-test-api-token", "sk-unit-test-secret", "private", str(root), "detail", "private repair action"]:
                    self.assertNotIn(needle, public_markdown)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

    def test_gold_verification_repair_plan_can_drive_web_repair_resume_without_active_queue(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_preflight = web_server._write_resume_preflight_or_raise
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-verification-only-repair"
            run_dir.mkdir(parents=True)
            verification_report = run_dir / "15-gold-run-verification.json"
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            captured: dict[str, Any] = {}
            try:
                write_json(run_dir / "state.json", {"topic": "Iris", "stage": "completed", "updated_at": "test"})
                write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0, "block": 0}, "items": []})
                write_json(
                    verification_report,
                    {
                        "status": "blocked",
                        "repair_plan": [
                            {
                                "id": "submission_package",
                                "priority": 70,
                                "rerun_from": "submission_package",
                                "source_artifact": "11-submission-package.json",
                                "target_artifacts": ["11-submission-package.json", "11-submission-package.zip"],
                                "action": "private repair action must not leak",
                            }
                        ],
                    },
                )
                web_server.write_repair_resume_plan_artifacts(
                    run_dir,
                    apply=False,
                    gold_verification_report_path=verification_report,
                )
                store = web_server.RunStore()

                preview = store.preview_repair_resume("gold-verification-only-repair")

                self.assertIsNotNone(preview)
                assert preview is not None
                self.assertEqual(preview["plan"]["status"], "ready_to_resume_repair")
                self.assertTrue(preview["plan"]["can_resume"])
                self.assertEqual(preview["plan"]["queue_status"], "pass")
                self.assertEqual(preview["plan"]["repair_plan_sources"], ["12-repair-queue", "gold-run-verification"])
                self.assertEqual(preview["plan"]["repair_items"], 1)
                self.assertNotIn("private repair action", json.dumps(preview, ensure_ascii=False))

                def fake_preflight(topic, out_dir, config):
                    captured["preflight_topic"] = topic

                def fake_start(run_id, topic, out_dir, config, *, gold_verification_report_path=None):
                    captured["run_id"] = run_id
                    captured["path"] = gold_verification_report_path

                web_server._write_resume_preflight_or_raise = fake_preflight
                store._start_repair_resume_worker = fake_start

                result = store.repair_resume_with_config("gold-verification-only-repair", {})

                self.assertIsNotNone(result)
                self.assertEqual(captured["run_id"], "gold-verification-only-repair")
                self.assertEqual(captured["path"], verification_report.resolve())
            finally:
                web_server._write_resume_preflight_or_raise = original_preflight
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_gold_run_launch_endpoint_rejects_payload_secrets_without_echoing_values(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/gold-run-launch",
                data=json.dumps(
                    {
                        "topic": "secret launch smoke",
                        "paper_grade_enabled": False,
                        "llm_api_key": "unit-test-api-token",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            body = caught.exception.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()
            with contextlib.suppress(RuntimeError):
                thread.join(timeout=2)

        self.assertEqual(caught.exception.code, 400)
        self.assertIn("paper-grade Web actions require env-only secret handling", body)
        self.assertIn("llm_api_key", body)
        self.assertNotIn("unit-test-api-token", body)

    def test_gold_run_launch_endpoint_blocks_before_creating_run(self) -> None:
        original_bundle = web_server.build_gold_launch_bundle_report
        original_store = web_server.STORE

        class FakeStore:
            def __init__(self) -> None:
                self.created = False

            def create(self, *args, **kwargs):  # pragma: no cover - should not be reached
                self.created = True
                raise AssertionError("blocked launch must not create a run")

        fake_store = FakeStore()

        def fake_bundle(*args, **kwargs):
            return {
                "schema_version": 1,
                "topic": "blocked launch",
                "status": "blocked",
                "can_start_gold_run": False,
                "components": [{"item": "gold_env", "status": "block", "button": "Gold Env", "evidence": "missing=1", "next_step": "Set env."}],
                "next_steps": ["gold_env=block"],
                "launch_plan": {"status": "blocked", "ready_to_execute_commands": False, "secret_policy": "env_only"},
                "ignored_payload_secret_fields": [],
                "read_only": True,
            }

        web_server.build_gold_launch_bundle_report = fake_bundle
        web_server.STORE = fake_store
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/gold-run-launch",
                data=json.dumps({"topic": "blocked launch", "paper_grade_enabled": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
            body = caught.exception.read().decode("utf-8")
        finally:
            server.shutdown()
            server.server_close()
            with contextlib.suppress(RuntimeError):
                thread.join(timeout=2)
            web_server.build_gold_launch_bundle_report = original_bundle
            web_server.STORE = original_store

        data = json.loads(body)
        self.assertEqual(caught.exception.code, 409)
        self.assertFalse(fake_store.created)
        self.assertEqual(data["error"], "gold launch blocked")
        self.assertEqual(data["report"]["status"], "blocked")
        self.assertIn("Gold Launch Bundle", data["markdown"])

    def test_gold_run_launch_endpoint_starts_after_ready_bundle(self) -> None:
        original_bundle = web_server.build_gold_launch_bundle_report
        original_store = web_server.STORE

        class FakeStore:
            def __init__(self) -> None:
                self.created: list[dict[str, Any]] = []

            def create(self, topic, config, *, gold_launch_bundle_report=None):
                self.created.append(
                    {
                        "topic": topic,
                        "paper_grade": config.paper_grade.enabled,
                        "bundle_status": (gold_launch_bundle_report or {}).get("status"),
                    }
                )
                return {
                    "id": "ready-gold-run",
                    "topic": topic,
                    "status": "running",
                    "stage": "queued",
                    "worker_active": True,
                    "out_dir": "runs/ready-gold-run",
                    "artifacts": [],
                }

        fake_store = FakeStore()

        def fake_bundle(*args, **kwargs):
            return {
                "schema_version": 1,
                "topic": "ready launch",
                "status": "ready_to_start",
                "can_start_gold_run": True,
                "components": [{"item": "gold_doctor", "status": "pass", "button": "Gold Doctor", "evidence": "ready", "next_step": "Start."}],
                "next_steps": [],
                "launch_plan": {
                    "status": "ready_to_start",
                    "ready_to_execute_commands": True,
                    "secret_policy": "env_only",
                    "safe_commands": ["PYTHONPATH=src python3 -m research_agent run --paper-grade"],
                },
                "ignored_payload_secret_fields": [],
                "read_only": True,
            }

        web_server.build_gold_launch_bundle_report = fake_bundle
        web_server.STORE = fake_store
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/gold-run-launch",
                data=json.dumps({"topic": "ready launch", "paper_grade_enabled": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8")
                status = response.status
        finally:
            server.shutdown()
            server.server_close()
            with contextlib.suppress(RuntimeError):
                thread.join(timeout=2)
            web_server.build_gold_launch_bundle_report = original_bundle
            web_server.STORE = original_store

        data = json.loads(body)
        self.assertEqual(status, 201)
        self.assertEqual(data["run"]["id"], "ready-gold-run")
        self.assertEqual(data["launch_bundle"]["status"], "ready_to_start")
        self.assertEqual(data["post_launch_guidance"]["run_dir"], "runs/ready-gold-run")
        self.assertTrue(any(" research_agent status " in command for command in data["post_launch_guidance"]["commands"]))
        self.assertTrue(any(" research_agent approve " in command for command in data["post_launch_guidance"]["commands"]))
        self.assertTrue(any(" research_agent approve-execution " in command for command in data["post_launch_guidance"]["commands"]))
        self.assertTrue(any(" gold-run-verify " in command for command in data["post_launch_guidance"]["commands"]))
        self.assertTrue(any(" perfect-readiness " in command for command in data["post_launch_guidance"]["commands"]))
        self.assertEqual(fake_store.created, [{"topic": "ready launch", "paper_grade": True, "bundle_status": "ready_to_start"}])
        self.assertNotIn("api-key", body)
        self.assertNotIn("sk-", body)

    def test_gold_launch_worker_writes_final_verification_artifacts(self) -> None:
        original_run_pipeline = web_server.run_pipeline
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "runs" / "gold-worker-run"
            out_dir.mkdir(parents=True)
            _write_gold_launch_bundle_marker(out_dir)

            def fake_run_pipeline(topic, run_dir, config):
                _write_gold_verification_candidate(run_dir)
                return run_dir

            web_server.run_pipeline = fake_run_pipeline
            try:
                store = web_server.RunStore()
                store._run_worker("gold-worker-run", "Iris", out_dir, AgentConfig())
            finally:
                web_server.run_pipeline = original_run_pipeline

            verification = json.loads((out_dir / "15-gold-run-verification.json").read_text(encoding="utf-8"))
            markdown = (out_dir / "15-gold-run-verification.md").read_text(encoding="utf-8")

        self.assertEqual(verification["status"], "ready")
        self.assertTrue(verification["gold_contract_ready"])
        self.assertIn("Gold Run Verification", markdown)

    def test_gold_launch_worker_writes_repair_plan_and_readiness_when_verification_blocks(self) -> None:
        original_run_pipeline = web_server.run_pipeline
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_readiness = web_server.write_perfect_agent_readiness_artifacts
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            out_dir = runs_dir / "blocked-gold-worker-run"
            out_dir.mkdir(parents=True)
            _write_gold_launch_bundle_marker(out_dir)
            readiness_calls: list[tuple[Path, Path, Path]] = []
            public_record = None

            def fake_run_pipeline(topic, run_dir, config):
                _write_gold_verification_candidate(run_dir, package_status="blocked")
                return run_dir

            def fake_readiness(project_dir, runs_dir_arg, out_dir_arg, limit=0):
                readiness_calls.append((project_dir, runs_dir_arg, out_dir_arg))
                return {"status": "block"}

            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            web_server.run_pipeline = fake_run_pipeline
            web_server.write_perfect_agent_readiness_artifacts = fake_readiness
            try:
                store = web_server.RunStore()
                store._runs["blocked-gold-worker-run"] = {
                    "id": "blocked-gold-worker-run",
                    "topic": "Iris",
                    "stage": "queued",
                    "status": "running",
                    "worker_active": True,
                    "out_dir": "runs/blocked-gold-worker-run",
                    "config": None,
                    "artifacts": [],
                    "error": None,
                }
                store._run_worker("blocked-gold-worker-run", "Iris", out_dir, AgentConfig())
                public_record = store.get("blocked-gold-worker-run")
            finally:
                web_server.run_pipeline = original_run_pipeline
                web_server.write_perfect_agent_readiness_artifacts = original_readiness
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

            verification = json.loads((out_dir / "15-gold-run-verification.json").read_text(encoding="utf-8"))
            repair_plan = json.loads((out_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))

        self.assertEqual(verification["status"], "blocked")
        self.assertEqual(repair_plan["repair_plan_sources"], ["12-repair-queue", "gold-run-verification"])
        self.assertEqual(readiness_calls, [(root, runs_dir, root)])
        self.assertIsNotNone(public_record)
        assert public_record is not None
        self.assertIn("15-gold-run-verification.json", public_record["artifacts"])
        self.assertIn("12-repair-resume-plan.json", public_record["artifacts"])
        self.assertEqual(public_record["gold_run_verification"]["status"], "blocked")
        self.assertEqual(public_record["repair_resume_plan"]["status"], "ready_to_resume_repair")
        self.assertEqual(public_record["gold_post_launch"]["status"], "blocked")
        self.assertTrue(public_record["gold_post_launch"]["repair_resume_plan_written"])
        self.assertEqual(
            public_record["gold_post_launch"]["verification_artifacts"],
            ["15-gold-run-verification.json", "15-gold-run-verification.md"],
        )
        self.assertEqual(
            public_record["gold_post_launch"]["repair_resume_plan_artifacts"],
            ["12-repair-resume-plan.json", "12-repair-resume-plan.md"],
        )

    def test_gold_launch_resume_workers_write_final_verification_artifacts(self) -> None:
        cases = [
            ("review", "_resume_worker", "resume_pipeline_after_review_approval"),
            ("checkpoint", "_checkpoint_resume_worker", "resume_pipeline_from_checkpoint"),
            ("repair", "_repair_resume_worker", "resume_pipeline_from_repair_queue"),
        ]
        for label, worker_name, resume_name in cases:
            with self.subTest(label=label), TemporaryDirectory() as tmp:
                root = Path(tmp)
                out_dir = root / "runs" / f"gold-{label}-run"
                out_dir.mkdir(parents=True)
                _write_gold_launch_bundle_marker(out_dir)
                original_resume = getattr(web_server, resume_name)

                def fake_resume(topic, run_dir, config):
                    _write_gold_verification_candidate(run_dir)
                    return run_dir

                setattr(web_server, resume_name, fake_resume)
                try:
                    store = web_server.RunStore()
                    getattr(store, worker_name)(f"gold-{label}-run", "Iris", out_dir, AgentConfig())
                finally:
                    setattr(web_server, resume_name, original_resume)

                verification = json.loads((out_dir / "15-gold-run-verification.json").read_text(encoding="utf-8"))
                markdown = (out_dir / "15-gold-run-verification.md").read_text(encoding="utf-8")

                self.assertEqual(verification["status"], "ready")
                self.assertTrue(verification["gold_contract_ready"])
                self.assertIn("Gold Run Verification", markdown)

    def test_regular_worker_does_not_write_gold_verification_artifacts(self) -> None:
        original_run_pipeline = web_server.run_pipeline
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "runs" / "regular-worker-run"
            out_dir.mkdir(parents=True)

            def fake_run_pipeline(topic, run_dir, config):
                _write_gold_verification_candidate(run_dir)
                return run_dir

            web_server.run_pipeline = fake_run_pipeline
            try:
                store = web_server.RunStore()
                store._run_worker("regular-worker-run", "Iris", out_dir, AgentConfig())
            finally:
                web_server.run_pipeline = original_run_pipeline

            verification_exists = (out_dir / "15-gold-run-verification.json").exists()

        self.assertFalse(verification_exists)

    def test_gold_run_doctor_api_uses_form_release_metadata_without_leaking_private_fields(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            runs_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                payload = {
                    "topic": "Iris classification benchmark smoke",
                    "paper_grade_enabled": True,
                    "llm_base_url": "http://127.0.0.1:8317",
                    "llm_model": "gpt-5.5",
                    "llm_api_key": "unit-test-api-token",
                    "literature_provider": "auto",
                    "literature_sources": "semantic_scholar, openalex, arxiv, crossref",
                    "literature_contact_email": "researcher@university.edu",
                    "seed_papers": "10.5281/zenodo.1234567\nhttps://doi.org/10.1145/3368089.3409742\nhttps://arxiv.org/abs/1706.03762",
                    "execution_mode": "benchmark",
                    "execution_repeats": 5,
                    "benchmark_manifests": "benchmarks/missing/manifest.json",
                    "release_code_repository_url": "https://github.com/research-lab/iris-study",
                    "release_code_archive_doi": "10.5281/zenodo.7654321",
                    "release_code_license": "MIT",
                    "release_code_version": "v1.0.0",
                    "release_data_access_statement": "No restricted external data are used; benchmark data are available from the cited public source.",
                    "release_environment_url": "https://zenodo.org/records/7654321",
                    "ping_llm": False,
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/gold-run-doctor",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(request, timeout=5) as response:
                    body = response.read().decode("utf-8")
                data = json.loads(body)
                report = data["report"]
                launch = data["launch_manifest"]

                self.assertEqual(report["status"], "blocked")
                self.assertNotIn("gold_release_metadata", report["failed_checks"])
                self.assertIn("preflight:paper_grade_benchmark_manifests", report["failed_checks"])
                self.assertEqual(launch["status"], "blocked")
                self.assertFalse(launch["can_start_gold_run"])
                self.assertEqual(launch["launch_readiness"]["status"], "blocked")
                self.assertFalse(launch["launch_readiness"]["can_start_gold_run"])
                self.assertIn("benchmark_manifest", launch["launch_readiness"]["blocking_items"])
                self.assertEqual(launch["launch_readiness"]["secret_policy"], "move_secrets_to_env")
                self.assertTrue(launch["paper_grade_literature_ready"])
                self.assertEqual(launch["literature_source_count"], 4)
                self.assertEqual(launch["min_literature_sources"], 3)
                self.assertEqual(launch["seed_papers"], 3)
                self.assertEqual(launch["min_seed_papers"], 3)
                self.assertEqual(launch["doi_url_seed_papers"], 3)
                self.assertEqual(launch["min_doi_url_seed_papers"], 3)
                self.assertFalse(launch["benchmark_ready"])
                self.assertTrue(launch["release_required_ready"])
                self.assertEqual(launch["direct_secret_fields"], ["llm_api_key"])
                self.assertTrue(any(item["item"] == "benchmark_manifest" for item in launch["launch_checklist"]))
                benchmark_item = next(item for item in launch["launch_checklist"] if item["item"] == "benchmark_manifest")
                self.assertEqual(benchmark_item["status"], "block")
                self.assertIn("benchmark_manifests", benchmark_item["form_fields"])
                self.assertIn("Benchmark Preview", benchmark_item["next_step"])
                self.assertTrue(any("benchmark_manifest=block" in item for item in launch["launch_next_steps"]))
                self.assertIn("Gold Launch Manifest 摘要", data["markdown"])
                self.assertIn("Gold Launch Manifest 摘要", data["launch_markdown"])
                self.assertIn("Safe Launch Commands", data["markdown"])
                self.assertIn("Safe Launch Commands", data["launch_command_markdown"])
                self.assertTrue(data["launch_commands"])
                launch_command_text = "\n".join(data["launch_commands"])
                self.assertIn("--paper-grade", launch_command_text)
                self.assertIn("--seed-paper", launch_command_text)
                self.assertIn("--benchmark-manifest", launch_command_text)
                self.assertIn("--release-code-archive-doi", launch_command_text)
                self.assertNotIn("export ", launch_command_text)
                public_payload = json.dumps(data, ensure_ascii=False)
                for needle in [
                    "unit-test-api-token",
                    "researcher@university.edu",
                    str(root),
                    "OPENAI_API_KEY",
                    "detail",
                    "action",
                    "safe_commands",
                ]:
                    self.assertNotIn(needle, public_payload)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

    def test_release_metadata_lint_reports_gold_blockers_without_values(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            bad_payload = {
                "topic": "Release lint",
                "release_code_repository_url": "https://example.org/private-release-repo",
                "release_code_archive_doi": "not-a-doi",
                "release_code_license": "placeholder-license",
                "release_code_version": "todo-version",
                "release_data_archive_doi": "not-a-data-doi",
                "release_data_access_statement": "Uses the public benchmark data described in the manifest.",
                "release_environment_url": "docker-image-local",
                "release_notes": "private release note must not leak",
            }
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/release-metadata-lint",
                data=json.dumps(bad_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                bad_text = response.read().decode("utf-8")
            bad = json.loads(bad_text)

            self.assertEqual(bad["report"]["status"], "blocked")
            self.assertIn("release_code_repository_url", bad["report"]["placeholder_required_fields"])
            self.assertIn("release_code_archive_doi", bad["report"]["invalid_required_fields"])
            self.assertIn("release_environment_url", bad["report"]["invalid_required_fields"])
            self.assertIn("release_data_archive_doi", bad["report"]["blocking_fields"])
            self.assertIn("Gold Release Metadata Lint", bad["markdown"])
            for needle in [
                "https://example.org/private-release-repo",
                "not-a-doi",
                "placeholder-license",
                "todo-version",
                "not-a-data-doi",
                "private release note must not leak",
                "docker-image-local",
            ]:
                self.assertNotIn(needle, bad_text)

            good_payload = {
                "topic": "Release lint",
                "release_code_repository_url": "https://github.com/research-lab/iris-study",
                "release_code_archive_doi": "10.5281/zenodo.7654321",
                "release_code_license": "MIT",
                "release_code_version": "v1.0.0",
                "release_data_access_statement": "No restricted external data are used; benchmark data are available from the cited public source.",
                "release_environment_url": "https://zenodo.org/records/7654321",
            }
            good_request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/release-metadata-lint",
                data=json.dumps(good_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(good_request, timeout=5) as response:
                good = json.loads(response.read().decode("utf-8"))
            self.assertEqual(good["report"]["status"], "ready")
            self.assertTrue(good["report"]["required_ready"])
            self.assertEqual(good["report"]["blocking_fields"], [])
        finally:
            server.shutdown()
            server.server_close()
            with contextlib.suppress(RuntimeError):
                thread.join(timeout=2)

    def test_perfect_readiness_get_is_read_only(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            runs_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()

                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/perfect-readiness", timeout=5) as response:
                    body = response.read().decode("utf-8")
                data = json.loads(body)
                report = data["report"]

                self.assertEqual(report["status"], "block")
                self.assertIn("Perfect Research Agent Readiness", data["markdown"])
                self.assertFalse((root / "perfect-agent-readiness.json").exists())
                self.assertFalse((root / "perfect-agent-readiness.md").exists())
                public_payload = json.dumps(data, ensure_ascii=False)
                for needle in ["unit-test-api-token", "OPENAI_API_KEY", "sk-"]:
                    self.assertNotIn(needle, public_payload)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

    def test_gold_run_doctor_summary_is_visible_in_run_store_without_private_detail(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "doctor-list-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "Iris", "stage": "completed", "updated_at": "test"})
                write_json(
                    run_dir / "00-gold-run-doctor.json",
                    {
                        "schema_version": 1,
                        "topic": "Iris",
                        "status": "blocked",
                        "preflight_status": "fail",
                        "checks": [
                            {"name": "llm_api_key", "status": "fail", "detail": "private key detail must not leak"},
                            {"name": "candidate_gold_run", "status": "warn", "repair_plan": [{"id": "claim_consistency", "priority": 90}]},
                        ],
                        "preflight": [{"name": "llm_ping", "status": "fail", "detail": "private ping detail must not leak"}],
                        "commands": ["OPENAI_API_KEY=private-token"],
                        "candidate_repair_resume_plan": {
                            "status": "written",
                            "candidate_run_dir": str(root / "runs" / "candidate-run"),
                            "plan_json": str(root / "runs" / "candidate-run" / "12-repair-resume-plan.json"),
                            "plan_md": str(root / "runs" / "candidate-run" / "12-repair-resume-plan.md"),
                            "can_resume": True,
                            "rerun_from": "literature_review",
                            "repair_items": 1,
                        },
                    },
                )

                loaded = web_server.RunStore().get("doctor-list-run")

                self.assertEqual(loaded["gold_run_doctor"]["status"], "blocked")
                self.assertEqual(loaded["gold_run_doctor"]["preflight_status"], "fail")
                self.assertEqual(loaded["gold_run_doctor"]["check_status_counts"]["fail"], 1)
                self.assertEqual(loaded["gold_run_doctor"]["check_status_counts"]["warn"], 1)
                self.assertEqual(loaded["gold_run_doctor"]["preflight_status_counts"]["fail"], 1)
                self.assertEqual(loaded["gold_run_doctor"]["candidate_repair_plan_items"], 1)
                self.assertEqual(loaded["gold_run_doctor"]["candidate_repair_resume_plan"]["candidate_run_id"], "candidate-run")
                self.assertTrue(loaded["gold_run_doctor"]["candidate_repair_resume_plan"]["can_resume"])
                public_payload = json.dumps(loaded["gold_run_doctor"], ensure_ascii=False)
                for needle in ["private", "OPENAI_API_KEY", "detail", str(root)]:
                    self.assertNotIn(needle, public_payload)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_open_source_artifact_endpoint_returns_public_summary_without_prompt(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "open-source-artifact-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
                write_json(
                    run_dir / "00-open-source-lessons.json",
                    {
                        "topic": "机械臂路径规划",
                        "status": "constraints_ready",
                        "profiles": [{"name": "PaperQA2"}],
                        "project_evidence": [{"project_name": "PaperQA2", "status": "verified", "verified_files": ["README.md"]}],
                        "lessons": [{"lesson_id": "citation_grounded_fulltext"}],
                        "manual_checklist": ["private checklist item must not leak"],
                        "agent_prompt_text": "private prompt text must not leak",
                    },
                )
                write_text(run_dir / "00-open-source-lessons.md", "private prompt markdown must not leak")
                write_json(
                    run_dir / "13-open-source-compliance.json",
                    {
                        "topic": "机械臂路径规划",
                        "status": "block",
                        "score": 0.5,
                        "checked_lessons": 2,
                        "lesson_results": [
                            {"lesson_id": "citation_grounded_fulltext", "status": "block", "source_projects": ["PaperQA2"]},
                            {"lesson_id": "runtime_cost_observability", "status": "warn", "source_projects": ["AgentLaboratory"]},
                        ],
                        "source_project_summary": {
                            "project_count": 2,
                            "blocked_project_count": 1,
                            "warn_project_count": 1,
                            "pass_project_count": 0,
                            "blocked_projects": ["PaperQA2"],
                            "warn_projects": ["AgentLaboratory"],
                            "evidence_statuses": {"catalogued": 2},
                            "projects": [{"project_name": "PaperQA2", "status": "block", "blocked_lessons": ["private lesson detail must not leak"]}],
                        },
                        "blocking_issues": ["private blocking detail must not leak"],
                        "manual_tasks": ["private manual detail must not leak"],
                        "recommended_actions": ["private recommended action must not leak"],
                    },
                )
                write_text(run_dir / "13-open-source-compliance.md", "private compliance markdown must not leak")
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}/api/runs/{quote('open-source-artifact-run')}/artifact"

                with urllib.request.urlopen(f"{base}?file=00-open-source-lessons.json", timeout=5) as response:
                    lessons_text = response.read().decode("utf-8")
                with urllib.request.urlopen(f"{base}?file=00-open-source-lessons.md", timeout=5) as response:
                    lessons_md = response.read().decode("utf-8")
                with urllib.request.urlopen(f"{base}?file=13-open-source-compliance.json", timeout=5) as response:
                    compliance_text = response.read().decode("utf-8")
                with urllib.request.urlopen(f"{base}?file=13-open-source-compliance.md", timeout=5) as response:
                    compliance_md = response.read().decode("utf-8")
                lessons = json.loads(lessons_text)
                compliance = json.loads(compliance_text)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

        self.assertEqual(lessons["status"], "constraints_ready")
        self.assertEqual(lessons["lessons"], 1)
        self.assertEqual(compliance["status"], "block")
        self.assertEqual(compliance["blocking_issues"], 1)
        self.assertEqual(compliance["blocking_issue_count"], 1)
        self.assertEqual(compliance["manual_task_count"], 1)
        self.assertEqual(compliance["recommended_actions"], 1)
        self.assertEqual(compliance["recommended_action_count"], 1)
        self.assertEqual(compliance["project_count"], 2)
        self.assertEqual(compliance["blocked_project_count"], 1)
        self.assertEqual(compliance["warn_project_count"], 1)
        self.assertEqual(compliance["blocked_projects"], ["PaperQA2"])
        public_payload = lessons_text + lessons_md + compliance_text + compliance_md
        for needle in [
            "agent_prompt_text",
            "private prompt",
            "private checklist",
            "private lesson detail",
            "private blocking detail",
            "private manual detail",
            "private recommended action",
            "private compliance markdown",
        ]:
            self.assertNotIn(needle, public_payload)

    def test_sensitive_artifact_endpoints_return_public_summaries(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "sensitive-artifact-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            server = None
            thread = None
            try:
                write_json(run_dir / "state.json", {"topic": "敏感产物", "stage": "completed", "updated_at": "test"})
                write_text(run_dir / "02-experiment-manager.md", "private manager markdown must not leak")
                write_json(
                    run_dir / "02-experiment-manager.json",
                    {
                        "status": "review_required",
                        "manager_decision": "proceed_with_cautions",
                        "execution_policy": "smoke_first",
                        "manager_queue": [{"issue": "private manager queue must not leak"}],
                        "repair_context": {"prompt_text": "private manager prompt must not leak"},
                    },
                )
                write_text(run_dir / "13-agent-trajectory.md", "private timeline markdown must not leak")
                write_json(
                    run_dir / "13-agent-trajectory.json",
                    {
                        "status": "warn",
                        "summary": {"phase_counts": {"pass": 1, "warn": 1, "block": 0, "not_started": 0}, "last_event": "done", "event_count": 2},
                        "phases": [{"phase_id": "private phase must not leak"}],
                        "timeline": [{"stage": "private timeline must not leak"}],
                        "manual_tasks": ["private trajectory task must not leak"],
                    },
                )
                write_text(run_dir / "13-agent-observability-audit.md", "private checks markdown must not leak")
                write_json(
                    run_dir / "13-agent-observability-audit.json",
                    {
                        "status": "review_required",
                        "summary": {"manifest_events": 2, "manifest_artifacts": 4, "llm_total_calls": 1, "llm_failed_calls": 0},
                        "budget": {"prompt_utilization": 0.5},
                        "checks": [{"name": "private check must not leak", "evidence": "private evidence"}],
                        "recommended_actions": ["private observability action must not leak"],
                    },
                )
                write_text(run_dir / "run-diagnostics.md", "Traceback private stack must not leak")
                write_json(
                    run_dir / "run-diagnostics.json",
                    {
                        "category": "llm_configuration",
                        "severity": "error",
                        "summary": "模型未配置",
                        "likely_cause": "OPENAI_MODEL 缺失",
                        "recommended_actions": ["private diagnostic action must not leak"],
                        "traceback": "Traceback private stack must not leak",
                    },
                )
                write_text(run_dir / "run-llm-ledger.md", "private ledger entry must not leak")
                write_json(
                    run_dir / "run-llm-ledger.json",
                    {
                        "total_calls": 1,
                        "successful_calls": 1,
                        "failed_calls": 0,
                        "budget_exceeded_calls": 0,
                        "total_prompt_chars": 10,
                        "total_response_chars": 5,
                        "entries": [{"purpose": "private purpose must not leak", "error": "private llm error must not leak"}],
                    },
                )
                write_text(run_dir / "13-llm-trace-audit.md", "private stage check must not leak")
                write_json(
                    run_dir / "13-llm-trace-audit.json",
                    {
                        "status": "block",
                        "ledger_summary": {"total_calls": 1, "successful_calls": 1, "failed_calls": 0, "budget_exceeded_calls": 0, "entries": 1},
                        "coverage": {"required_stages": 7, "passed_required": 1},
                        "stage_checks": [{"evidence": "private stage evidence must not leak"}],
                        "recommended_actions": ["private trace action must not leak"],
                    },
                )
                write_text(run_dir / "13-run-economics-audit.md", "private economics check must not leak")
                write_json(
                    run_dir / "13-run-economics-audit.json",
                    {
                        "status": "review_required",
                        "summary": {"total_calls": 1, "successful_calls": 1, "input_tokens_estimated": 3, "output_tokens_estimated": 2, "call_utilization": 0.1},
                        "budget": {"used_calls": 1, "max_calls": 10},
                        "checks": [{"evidence": "private economics evidence must not leak"}],
                        "recommended_actions": ["private economics action must not leak"],
                    },
                )
                write_text(run_dir / "13-llm-observability-summary.md", "private summary markdown must not leak")
                write_json(
                    run_dir / "13-llm-observability-summary.json",
                    {
                        "status": "block",
                        "statuses": {"trace": "block", "economics": "review_required", "agent_observability": "review_required"},
                        "llm_calls": {"total": 1, "successful": 1, "failed": 0, "budget_exceeded": 0, "entries": 1},
                        "stage_coverage": {
                            "required_stages": 7,
                            "passed_required": 1,
                            "coverage_ratio": 0.14,
                            "missing_required_stage_count": 6,
                            "missing_required_stages": ["literature_synthesis", "private stage evidence must not leak"],
                            "warned_optional_stage_count": 1,
                            "warned_optional_stages": ["online_search_query_planning"],
                        },
                        "token_and_cost": {"input_tokens_estimated": 3, "output_tokens_estimated": 2, "estimated_cost_usd": None, "total_duration_seconds": 0.2},
                        "budget": {"call_utilization": 0.1, "prompt_utilization": 0.2},
                        "traceability": {"manifest_events": 2, "manifest_artifacts": 4, "experiment_runs": 0, "repair_queue_status": "blocked_repair_required"},
                        "blocking_issues": ["private summary blocker must not leak"],
                        "recommended_actions": ["private summary action must not leak"],
                    },
                )
                web_server.STORE = web_server.RunStore()
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}/api/runs/{quote('sensitive-artifact-run')}/artifact"
                files = [
                    "02-experiment-manager.json",
                    "02-experiment-manager.md",
                    "13-agent-trajectory.json",
                    "13-agent-trajectory.md",
                    "13-agent-observability-audit.json",
                    "13-agent-observability-audit.md",
                    "run-diagnostics.json",
                    "run-diagnostics.md",
                    "run-llm-ledger.json",
                    "run-llm-ledger.md",
                    "13-llm-trace-audit.json",
                    "13-llm-trace-audit.md",
                    "13-run-economics-audit.json",
                    "13-run-economics-audit.md",
                    "13-llm-observability-summary.json",
                    "13-llm-observability-summary.md",
                ]
                for filename in files:
                    with urllib.request.urlopen(f"{base}?file={quote(filename)}", timeout=5) as response:
                        body = response.read().decode("utf-8")
                    self.assertIn("status" if filename.endswith(".json") else "状态", body, filename)
                    if filename == "13-llm-observability-summary.json":
                        payload = json.loads(body)
                        self.assertEqual(payload["missing_required_stage_count"], 6)
                        self.assertEqual(payload["missing_required_stages"], ["literature_synthesis"])
                        self.assertEqual(payload["warned_optional_stages"], ["online_search_query_planning"])
                        self.assertEqual(payload["blocking_issue_count"], 1)
                        self.assertNotIn("blocking_issues", payload)
                        self.assertNotIn("recommended_actions", payload)
                    for needle in [
                        "manager_queue",
                        "repair_context",
                        "prompt_text",
                        "timeline",
                        "phases",
                        "private manager",
                        "private timeline",
                        "private phase",
                        "private check",
                        "private evidence",
                        "private observability action",
                        "Traceback private stack",
                        "private diagnostic action",
                        "private purpose",
                        "private llm error",
                        "private stage evidence",
                        "private trace action",
                        "private economics evidence",
                        "private economics action",
                        "private summary markdown",
                        "private summary blocker",
                        "private summary action",
                    ]:
                        self.assertNotIn(needle, body, f"{filename} leaked {needle}")
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    with contextlib.suppress(RuntimeError):
                        thread.join(timeout=2)
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.STORE = original_store

    def test_non_pass_review_gate_requires_web_approval_notes(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_after_review_approval
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "needs-notes-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            resume_called = False
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "approval.json",
                    {
                        "topic": "机械臂路径规划",
                        "approved": False,
                        "stage": "awaiting_review_approval",
                        "gate_status": "literature_repair_required",
                        "warnings": ["核心文献不足"],
                        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    },
                )
                historical_config = replace(
                    AgentConfig(),
                    llm=replace(AgentConfig().llm, model="resume-model", base_url="http://127.0.0.1:9/v1"),
                )
                web_server._write_run_config(run_dir, historical_config)
                _bind_review_approval(run_dir)

                def fake_resume(topic, out_dir, config):
                    nonlocal resume_called
                    resume_called = True

                web_server.resume_pipeline_after_review_approval = fake_resume
                store = web_server.RunStore()

                with self.assertRaises(RuntimeError):
                    store.approve_with_config(
                        "needs-notes-run",
                        reviewer="test",
                        payload={"llm_model": "resume-model", "llm_base_url": "http://127.0.0.1:9/v1", "review_notes": ""},
                    )

                loaded = store.get("needs-notes-run")
                approval = json.loads((run_dir / "approval.json").read_text(encoding="utf-8"))
                self.assertEqual(loaded["status"], "waiting")
                self.assertFalse(approval["approved"])
                self.assertFalse(resume_called)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_after_review_approval = original_resume

    def test_inactive_review_gate_resume_blocks_failed_preflight_before_approval(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_after_review_approval
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "preflight-blocked-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            resume_called = False
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "approval.json",
                    {
                        "topic": "机械臂路径规划",
                        "approved": False,
                        "stage": "awaiting_review_approval",
                        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    },
                )
                web_server._write_run_config(run_dir, AgentConfig())

                def fake_resume(topic, out_dir, config):
                    nonlocal resume_called
                    resume_called = True

                web_server.resume_pipeline_after_review_approval = fake_resume
                store = web_server.RunStore()

                with self.assertRaises(web_server.PreflightGateError) as caught:
                    store.approve_with_config("preflight-blocked-run", reviewer="test", payload={"review_notes": "已人工核对文献质量并接受风险"})

                loaded = store.get("preflight-blocked-run")
                approval = json.loads((run_dir / "approval.json").read_text(encoding="utf-8"))
                preflight = json.loads((run_dir / "00-preflight.json").read_text(encoding="utf-8"))
                self.assertEqual(caught.exception.report.status, "fail")
                self.assertEqual(preflight["status"], "fail")
                self.assertEqual(loaded["status"], "waiting")
                self.assertFalse(approval["approved"])
                self.assertFalse(resume_called)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_after_review_approval = original_resume

    def test_checkpoint_resume_blocks_failed_preflight_before_worker(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_from_checkpoint
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "checkpoint-preflight-blocked"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            resume_called = False
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "ideation_completed", "updated_at": "test"})
                write_text(run_dir / "02-ideas.md", "# Ideas")
                web_server._write_run_config(run_dir, AgentConfig())

                def fake_resume(topic, out_dir, config):
                    nonlocal resume_called
                    resume_called = True

                web_server.resume_pipeline_from_checkpoint = fake_resume
                store = web_server.RunStore()

                with self.assertRaises(web_server.PreflightGateError):
                    store.resume_with_config("checkpoint-preflight-blocked", payload={})

                loaded = store.get("checkpoint-preflight-blocked")
                preflight = json.loads((run_dir / "00-preflight.json").read_text(encoding="utf-8"))
                self.assertEqual(preflight["status"], "fail")
                self.assertFalse(loaded["worker_active"])
                self.assertFalse(resume_called)
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_from_checkpoint = original_resume

    def test_inactive_review_gate_run_can_be_cancelled(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "cancel-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "approval.json",
                    {
                        "topic": "机械臂路径规划",
                        "approved": False,
                        "stage": "awaiting_review_approval",
                        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    },
                )
                web_server._write_run_config(run_dir, AgentConfig())
                store = web_server.RunStore()

                loaded = store.get("cancel-run")
                self.assertEqual(loaded["status"], "waiting")
                result = store.cancel("cancel-run", requester="test", reason="unit_test")

                self.assertTrue(result["cancel"]["cancelled"])
                cancelled = store.get("cancel-run")
                self.assertEqual(cancelled["status"], "cancelled")
                self.assertEqual(cancelled["stage"], "cancelled")
                self.assertIn("cancel.json", cancelled["artifacts"])
                self.assertIn("run-recovery-plan.md", cancelled["artifacts"])
                recovery = json.loads((run_dir / "run-recovery-plan.json").read_text(encoding="utf-8"))
                self.assertEqual(recovery["category"], "cancelled")
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

    def test_inactive_review_gate_run_can_request_revision_then_approve(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_after_review_approval
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "revision-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval", "updated_at": "test"})
                write_json(
                    run_dir / "approval.json",
                    {
                        "topic": "机械臂路径规划",
                        "approved": False,
                        "stage": "awaiting_review_approval",
                        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                    },
                )
                historical_config = replace(
                    AgentConfig(),
                    llm=replace(AgentConfig().llm, model="resume-model", base_url="http://127.0.0.1:9/v1"),
                )
                web_server._write_run_config(run_dir, historical_config)
                _bind_review_approval(run_dir)

                def fake_resume(topic, out_dir, config):
                    write_json(out_dir / "state.json", {"topic": topic, "stage": "completed", "updated_at": "done"})
                    write_text(out_dir / "02-ideas.md", "# Ideas")

                web_server.resume_pipeline_after_review_approval = fake_resume
                store = web_server.RunStore()

                revision = store.request_revision("revision-run", reviewer="test", notes="补 DOI")
                self.assertTrue(revision["approval"]["revision_requested"])
                self.assertEqual(revision["run"]["status"], "revision_requested")
                self.assertEqual(revision["run"]["stage"], "review_revision_requested")
                self.assertIn("run-recovery-plan.md", revision["run"]["artifacts"])
                self.assertIn("01-review-revision-plan.md", revision["run"]["artifacts"])
                self.assertTrue((run_dir / "01-review-revision-plan.md").exists())
                recovery = json.loads((run_dir / "run-recovery-plan.json").read_text(encoding="utf-8"))
                self.assertEqual(recovery["category"], "review_revision_requested")

                result = store.approve_with_config(
                    "revision-run",
                    reviewer="test",
                    payload={"review_notes": "已补 DOI"},
                )
                self.assertTrue(result["approval"]["approved"])
                self.assertFalse(result["approval"]["revision_requested"])
                self.assertEqual(result["approval"]["notes"], "已补 DOI")

                completed = _wait_for_completed(store, "revision-run")
                self.assertEqual(completed["status"], "completed")
                history = json.loads((run_dir / "approval.json").read_text(encoding="utf-8"))["history"]
                self.assertEqual([item["action"] for item in history], ["revision_requested", "approved"])
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_after_review_approval = original_resume

    def test_inactive_execution_gate_run_can_be_approved_and_resumed(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_from_checkpoint
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "execution-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_execution_approval", "updated_at": "test"})
                write_json(
                    run_dir / "03-execution-approval.json",
                    {
                        "topic": "机械臂路径规划",
                        "approved": False,
                        "stage": "awaiting_execution_approval",
                        "execution_mode": "local",
                        "approval_policy": {"notes_required": True},
                        "blocks": ["experiment_execution"],
                    },
                )
                write_text(run_dir / "03-execution-approval.md", "# 执行确认")
                historical_config = replace(
                    AgentConfig(),
                    llm=replace(AgentConfig().llm, model="resume-model", base_url="http://127.0.0.1:9/v1"),
                    execution=ExecutionConfig(mode="local"),
                )
                web_server._write_run_config(run_dir, historical_config)
                _bind_execution_approval(run_dir)

                def fake_resume(topic, out_dir, config):
                    write_json(out_dir / "state.json", {"topic": topic, "stage": "completed", "updated_at": "done"})
                    write_text(out_dir / "04-results.json", "[]")

                web_server.resume_pipeline_from_checkpoint = fake_resume
                store = web_server.RunStore()

                loaded = store.get("execution-run")
                self.assertEqual(loaded["status"], "waiting")
                self.assertEqual(loaded["stage"], "awaiting_execution_approval")
                self.assertFalse(loaded["execution_approval"]["approved"])

                result = store.approve_with_config(
                    "execution-run",
                    reviewer="test",
                    payload={"review_notes": "已检查本地命令和安全审计，允许执行"},
                )
                self.assertTrue(result["execution_approval"]["approved"])
                self.assertEqual(result["execution_approval"]["notes"], "已检查本地命令和安全审计，允许执行")

                completed = _wait_for_completed(store, "execution-run")
                self.assertEqual(completed["status"], "completed")
                self.assertTrue((run_dir / "04-results.json").exists())
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_from_checkpoint = original_resume

    def test_inactive_checkpoint_run_can_be_resumed(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_resume = web_server.resume_pipeline_from_checkpoint
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "checkpoint-run"
            run_dir.mkdir(parents=True)
            web_server.ROOT = root
            web_server.RUNS_DIR = runs_dir
            try:
                write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "ideation_completed", "updated_at": "test"})
                write_text(run_dir / "02-ideas.md", "# Ideas")
                historical_config = replace(
                    AgentConfig(),
                    llm=replace(AgentConfig().llm, model="resume-model", base_url="http://127.0.0.1:9/v1"),
                )
                web_server._write_run_config(run_dir, historical_config)

                def fake_resume(topic, out_dir, config):
                    write_json(out_dir / "state.json", {"topic": topic, "stage": "completed", "updated_at": "done"})
                    write_text(out_dir / "06-paper.md", "# Paper")

                web_server.resume_pipeline_from_checkpoint = fake_resume
                store = web_server.RunStore()

                loaded = store.get("checkpoint-run")
                self.assertEqual(loaded["status"], "unknown")

                result = store.resume_with_config("checkpoint-run", payload={})
                self.assertIn(result["run"]["status"], {"running", "completed"})

                completed = _wait_for_completed(store, "checkpoint-run")
                self.assertEqual(completed["stage"], "completed")
                self.assertEqual(completed["status"], "completed")
                persisted = json.loads((run_dir / web_server.RUN_CONFIG_FILENAME).read_text(encoding="utf-8"))
                self.assertEqual(persisted["llm"]["model"], "resume-model")
                self.assertEqual(persisted["llm"]["api_key"], "")
            finally:
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs
                web_server.resume_pipeline_from_checkpoint = original_resume

    def test_env_llm_preflight_uses_server_environment_without_payload_secrets(self) -> None:
        llm_server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeEnvOpenAIHandler)
        llm_thread = Thread(target=llm_server.serve_forever, daemon=True)
        llm_thread.start()
        app_server = None
        app_thread = None
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        _FakeEnvOpenAIHandler.authorizations = []
        try:
            os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{llm_server.server_port}/v1"
            os.environ["OPENAI_MODEL"] = "fake-env-model"
            os.environ["OPENAI_API_KEY"] = "env-secret-token"
            app_server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            app_thread = Thread(target=app_server.serve_forever, daemon=True)
            app_thread.start()
            payload = {
                "topic": "Env LLM smoke",
                "paper_grade_enabled": True,
                "llm_base_url": "http://127.0.0.1:1/not-used",
                "llm_model": "payload-model-not-used",
                "llm_api_key": "payload-secret-token",
                "semantic_scholar_api_key": "semantic-payload-secret",
                "openalex_api_key": "openalex-payload-secret",
                "ping_llm": True,
            }
            request = urllib.request.Request(
                f"http://127.0.0.1:{app_server.server_port}/api/env-llm-preflight",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))

            self.assertEqual(data["env_llm"]["status"], "pass")
            self.assertEqual(data["env_llm"]["ping_status"], "pass")
            self.assertEqual(data["env_llm"]["server_env_configured"], {"base_url": True, "model": True, "api_key": True})
            self.assertEqual(
                data["env_llm"]["ignored_payload_secret_fields"],
                ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"],
            )
            self.assertEqual(_FakeEnvOpenAIHandler.authorizations, ["Bearer env-secret-token"])
            public_payload = json.dumps(data, ensure_ascii=False)
            for needle in [
                "payload-secret-token",
                "semantic-payload-secret",
                "openalex-payload-secret",
                "env-secret-token",
                "payload-model-not-used",
                "not-used",
            ]:
                self.assertNotIn(needle, public_payload)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if app_server is not None:
                app_server.shutdown()
                app_server.server_close()
            if app_thread is not None:
                with contextlib.suppress(RuntimeError):
                    app_thread.join(timeout=2)
            llm_server.shutdown()
            llm_server.server_close()
            with contextlib.suppress(RuntimeError):
                llm_thread.join(timeout=2)

    def test_gold_env_lint_uses_server_environment_without_payload_secrets(self) -> None:
        app_server = None
        app_thread = None
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL", "SEMANTIC_SCHOLAR_API_KEY", "OPENALEX_API_KEY"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8317"
            os.environ["OPENAI_MODEL"] = "gpt-5.5"
            os.environ["OPENAI_API_KEY"] = "env-secret-token"
            os.environ["RESEARCH_AGENT_CONTACT_EMAIL"] = "researcher@university.edu"
            os.environ.pop("SEMANTIC_SCHOLAR_API_KEY", None)
            os.environ.pop("OPENALEX_API_KEY", None)
            app_server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
            app_thread = Thread(target=app_server.serve_forever, daemon=True)
            app_thread.start()
            payload = {
                "topic": "Gold env smoke",
                "llm_api_key": "payload-secret-token",
                "semantic_scholar_api_key": "semantic-payload-secret",
                "openalex_api_key": "openalex-payload-secret",
            }
            request = urllib.request.Request(
                f"http://127.0.0.1:{app_server.server_port}/api/gold-env-lint",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))

            report = data["report"]
            self.assertEqual(report["status"], "ready")
            self.assertTrue(report["required_ready"])
            self.assertEqual(report["missing_required_fields"], [])
            self.assertEqual(report["missing_optional_fields"], ["semantic_scholar_api_key", "openalex_api_key"])
            self.assertEqual(report["ignored_payload_secret_fields"], ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"])
            public_payload = json.dumps(data, ensure_ascii=False)
            for needle in [
                "payload-secret-token",
                "semantic-payload-secret",
                "openalex-payload-secret",
                "env-secret-token",
                "researcher@university.edu",
                "http://127.0.0.1:8317",
                "OPENAI_API_KEY",
            ]:
                self.assertNotIn(needle, public_payload)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if app_server is not None:
                app_server.shutdown()
                app_server.server_close()
            if app_thread is not None:
                with contextlib.suppress(RuntimeError):
                    app_thread.join(timeout=2)


def _wait_for_completed(store: web_server.RunStore, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = store.get(run_id) or {}
        if last.get("stage") == "completed" and last.get("worker_active") is False:
            return last
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for resumed run; last={last}")


class _FakeEnvOpenAIHandler(BaseHTTPRequestHandler):
    authorizations: list[str] = []

    def do_POST(self) -> None:
        self.authorizations.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        body = json.dumps(
            {
                "id": "chatcmpl-env-test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    unittest.main()
