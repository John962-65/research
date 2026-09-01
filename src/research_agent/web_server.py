from __future__ import annotations

from dataclasses import asdict, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
import argparse
import base64
import binascii
import hmac
import ipaddress
import json
import math
import mimetypes
import os
import re
import shlex
import socket
import traceback

from .config import AgentConfig, AgentRoleConfig, ExecutionConfig, HumanConfig, IdeationConfig, LiteratureConfig, LLMConfig, MCPServerConfig, MultiAgentConfig, PaperConfig, PaperGradeConfig, ReleaseConfig, load_config
from .agent_runtime import agent_runtime_catalog
from .artifacts import write_json, write_text
from .benchmark_adapter import audit_benchmark_adapter_config, formal_benchmark_metric_contract_issues, formal_benchmark_provenance_issues, render_benchmark_adapter_markdown
from .credential_validation import valid_contact_email
from .diagnostics import diagnose_exception, render_diagnostic_markdown
from .experiments import ENVIRONMENT_SNAPSHOT_JSON, ENVIRONMENT_SNAPSHOT_MD
from .pipeline import (
    APPROVAL_FILENAME,
    ABLATION_PLAN_JSON,
    ABLATION_PLAN_MD,
    AGENT_OBSERVABILITY_AUDIT_JSON,
    AGENT_OBSERVABILITY_AUDIT_MD,
    AGENT_STAGE_CONTRACT_JSON,
    AGENT_STAGE_CONTRACT_MD,
    AGENT_TRAJECTORY_JSON,
    AGENT_TRAJECTORY_MD,
    AI_DISCLOSURE_JSON,
    AI_DISCLOSURE_MD,
    BENCHMARK_ADAPTER_JSON,
    BENCHMARK_ADAPTER_MD,
    BENCHMARK_EVIDENCE_AUDIT_JSON,
    BENCHMARK_EVIDENCE_AUDIT_MD,
    BENCHMARK_PLAN_JSON,
    BENCHMARK_PLAN_MD,
    BENCHMARK_READINESS_JSON,
    BENCHMARK_READINESS_MD,
    BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
    BENCHMARK_RESULT_SCHEMA_AUDIT_MD,
    CITATION_AUDIT_JSON,
    CITATION_AUDIT_MD,
    CITATION_COVERAGE_JSON,
    CITATION_COVERAGE_MD,
    CITATION_GROUNDING_JSON,
    CITATION_GROUNDING_MD,
    CLAIM_BOUNDARY_PREFLIGHT_JSON,
    CLAIM_BOUNDARY_PREFLIGHT_MD,
    CLAIM_CONSISTENCY_JSON,
    CLAIM_CONSISTENCY_MD,
    CODE_DATA_AVAILABILITY_JSON,
    CODE_DATA_AVAILABILITY_MD,
    CANCEL_FILENAME,
    EXPLORATION_MAP_JSON,
    EXPLORATION_MAP_MD,
    EXPLORATION_MAP_SVG,
    EXPERIMENT_AUDIT_JSON,
    EXPERIMENT_AUDIT_MD,
    EXPERIMENT_MANAGER_JSON,
    EXPERIMENT_MANAGER_MD,
    EXECUTION_SAFETY_AUDIT_JSON,
    EXECUTION_SAFETY_AUDIT_MD,
    EXECUTION_APPROVAL_JSON,
    EXECUTION_APPROVAL_MD,
    EXPERIMENT_DECISION_JSON,
    EXPERIMENT_DECISION_MD,
    EXPERIMENT_RUNBOOK_JSON,
    EXPERIMENT_RUNBOOK_MD,
    FAILURE_ANALYSIS_JSON,
    FAILURE_ANALYSIS_MD,
    FINAL_HANDOFF_JSON,
    FINAL_HANDOFF_MD,
    FINAL_READINESS_JSON,
    FINAL_READINESS_MD,
    FULLTEXT_CORPUS_JSON,
    FULLTEXT_CORPUS_MD,
    HUMAN_BRIEF_JSON,
    HUMAN_BRIEF_MD,
    HYPOTHESIS_OUTCOME_JSON,
    HYPOTHESIS_OUTCOME_MD,
    IDEA_EXPERIMENT_CONTRACT_JSON,
    IDEA_EXPERIMENT_CONTRACT_MD,
    IDEA_AUDIT_JSON,
    IDEA_AUDIT_MD,
    ITERATION_PLAN_JSON,
    ITERATION_PLAN_MD,
    LITERATURE_SEARCH_STRATEGY_JSON,
    LITERATURE_SEARCH_STRATEGY_MD,
    LITERATURE_COVERAGE_JSON,
    LITERATURE_COVERAGE_MD,
    LITERATURE_EVIDENCE_MIX_JSON,
    LITERATURE_EVIDENCE_MIX_MD,
    LITERATURE_EVIDENCE_CONTRACT_JSON,
    LITERATURE_EVIDENCE_CONTRACT_MD,
    LITERATURE_GATE_DECISION_JSON,
    LITERATURE_GATE_DECISION_MD,
    LITERATURE_RESCUE_PLAN_JSON,
    LITERATURE_RESCUE_PLAN_MD,
    LITERATURE_RESCUE_EXECUTION_JSON,
    LITERATURE_RESCUE_EXECUTION_MD,
    LITERATURE_SEARCH_FEEDBACK_JSON,
    LITERATURE_SEARCH_FEEDBACK_MD,
    LITERATURE_SNOWBALL_JSON,
    LITERATURE_SNOWBALL_MD,
    LITERATURE_SOURCE_HEALTH_JSON,
    LITERATURE_SOURCE_HEALTH_MD,
    LITERATURE_METADATA_AUDIT_JSON,
    LITERATURE_METADATA_AUDIT_MD,
    LITERATURE_RERANK_JSON,
    LITERATURE_RERANK_MD,
    LLM_TRACE_JSON,
    LLM_TRACE_MD,
    LLM_TRACE_AUDIT_JSON,
    LLM_TRACE_AUDIT_MD,
    LLM_OBSERVABILITY_SUMMARY_JSON,
    LLM_OBSERVABILITY_SUMMARY_MD,
    RUN_ECONOMICS_AUDIT_JSON,
    RUN_ECONOMICS_AUDIT_MD,
    NOVELTY_AUDIT_JSON,
    NOVELTY_AUDIT_MD,
    OPEN_SOURCE_LESSONS_JSON,
    OPEN_SOURCE_LESSONS_MD,
    OPEN_SOURCE_COMPLIANCE_JSON,
    OPEN_SOURCE_COMPLIANCE_MD,
    PAPER_REVIEW_CALIBRATION_JSON,
    PAPER_REVIEW_CALIBRATION_MD,
    PRIOR_RUN_LESSONS_JSON,
    PRIOR_RUN_LESSONS_MD,
    PRIOR_RUN_LIBRARY_JSON,
    PRIOR_RUN_LIBRARY_MD,
    PREREGISTRATION_JSON,
    PREREGISTRATION_MD,
    QUERY_EXECUTION_AUDIT_JSON,
    QUERY_EXECUTION_AUDIT_MD,
    RELEASE_METADATA_JSON,
    RELEASE_METADATA_MD,
    REPAIR_RESUME_PLAN_JSON,
    REPAIR_RESUME_PLAN_MD,
    REPAIR_RESOLUTION_AUDIT_JSON,
    REPAIR_RESOLUTION_AUDIT_MD,
    REPAIR_QUEUE_JSON,
    REPAIR_QUEUE_MD,
    RESULT_VALIDATION_JSON,
    RESULT_VALIDATION_MD,
    RESULTS_PRESENTATION_JSON,
    RESULTS_PRESENTATION_MD,
    RESEARCH_SCORECARD_JSON,
    RESEARCH_SCORECARD_MD,
    RUN_INTEGRITY_AUDIT_JSON,
    RUN_INTEGRITY_AUDIT_MD,
    SEED_PAPER_INTAKE_JSON,
    SEED_PAPER_INTAKE_MD,
    REVIEW_FEEDBACK_JSON,
    REVIEW_FEEDBACK_MD,
    REVIEW_CONSTRAINT_COMPLIANCE_JSON,
    REVIEW_CONSTRAINT_COMPLIANCE_MD,
    REVIEW_CONSTRAINTS_JSON,
    REVIEW_CONSTRAINTS_MD,
    REVIEW_REVISION_PLAN_JSON,
    REVIEW_REVISION_PLAN_MD,
    REVISED_PAPER_MD,
    REVISED_PAPER_TEX,
    REVISED_PAPER_REVIEW_JSON,
    REVISED_PAPER_REVIEW_MD,
    REVISION_PLAN_JSON,
    REVISION_PLAN_MD,
    REVISION_RESPONSE_AUDIT_JSON,
    REVISION_RESPONSE_AUDIT_MD,
    REVISION_REPORT_JSON,
    REVISION_REPORT_MD,
    STATISTICS_FIGURE_JSON,
    STATISTICS_FIGURE_SVG,
    SUBMISSION_PACKAGE_JSON,
    SUBMISSION_PACKAGE_MD,
    SUBMISSION_PACKAGE_ZIP,
    SUBMISSION_CHECK_JSON,
    SUBMISSION_CHECK_MD,
    PipelineCancelled,
    PipelineReviewRevisionRequested,
    approve_execution_gate,
    approve_review_gate,
    default_out_dir,
    mark_cancelled,
    request_cancel,
    request_review_revision,
    resume_pipeline_after_review_approval,
    resume_pipeline_from_checkpoint,
    resume_pipeline_from_repair_queue,
    run_pipeline,
)
from .literature_search_strategy import build_literature_search_strategy
from .literature_sources import OnlineLiteratureClient, annotate_evidence
from .human_gate_audit import HUMAN_GATE_AUDIT_JSON, HUMAN_GATE_AUDIT_MD
from .gold_run_doctor import (
    GOLD_LAUNCH_MANIFEST_JSON,
    GOLD_LAUNCH_MANIFEST_MD,
    GOLD_RUN_DOCTOR_JSON,
    GOLD_RUN_DOCTOR_MD,
    GOLD_RUN_VERIFICATION_JSON,
    GOLD_RUN_VERIFICATION_MD,
    write_gold_run_verification_artifacts,
    build_gold_environment_lint,
    build_gold_release_metadata_lint,
    build_gold_run_doctor,
    render_gold_environment_lint_markdown,
    render_gold_release_metadata_lint_markdown,
)
from .llm_observability_backfill import backfill_llm_observability, render_llm_observability_backfill_markdown
from .llm_runtime_contract import LLM_RUNTIME_CONTRACT_JSON, LLM_RUNTIME_CONTRACT_MD
from .open_source_compliance_backfill import backfill_open_source_compliance, render_open_source_compliance_backfill_markdown
from .paper_grade_probe import build_paper_grade_online_probe, render_paper_grade_online_probe_markdown
from .platform_audit import build_platform_audit, render_platform_audit_markdown
from .perfect_agent_readiness import (
    PERFECT_AGENT_READINESS_JSON,
    PERFECT_AGENT_READINESS_MD,
    build_perfect_agent_readiness,
    render_perfect_agent_readiness_markdown,
    write_perfect_agent_readiness_artifacts,
)
from .preflight import PREFLIGHT_JSON, PREFLIGHT_MD, render_preflight_markdown, run_preflight, write_preflight_artifacts
from .repair_resume import write_repair_resume_plan_artifacts
from .repair_resume_backlog import build_repair_resume_backlog, render_repair_resume_backlog_markdown
from .repair_resume_backfill import backfill_repair_resume_plans, render_repair_resume_backfill_markdown
from .run_library import build_run_library, render_run_library_markdown, search_run_library
from .run_memory import build_run_memory, render_run_memory_markdown
from .run_recovery import RUN_RECOVERY_PLAN_JSON, RUN_RECOVERY_PLAN_MD, write_run_recovery_plan_artifacts
from .run_summary import build_run_dashboard, render_run_dashboard_markdown
from .seed_paper_intake import build_seed_paper_suggestion_report, seed_role_repair_queries
from .tool_runtime import TOOL_RECEIPTS_JSON, list_project_skills, validate_multi_agent_tools
from .workflow_graph import (
    WORKFLOW_STATUS_JSON,
    apply_rollback,
    issue_rollback_preview,
    read_workflow_status,
    rollback_options,
    update_workflow_stage,
    workflow_definition,
)


ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
RUNS_DIR = ROOT / "runs"
RUN_CONFIG_FILENAME = "run-config.json"
RUN_DIAGNOSTIC_JSON = "run-diagnostics.json"
RUN_DIAGNOSTIC_MD = "run-diagnostics.md"
GOLD_LAUNCH_BUNDLE_JSON = "00-gold-launch-bundle.json"
GOLD_LAUNCH_BUNDLE_MD = "00-gold-launch-bundle.md"
GOLD_DEFAULT_SMOKE_TOPIC = "Iris classification benchmark smoke"
ACTIVE_REPAIR_QUEUE_STATUSES = {"blocked_repair_required", "needs_repair"}
WEB_AUTH_USERNAME = "research-agent"
WEB_TOKEN_ENV = "RESEARCH_AGENT_WEB_TOKEN"
WEB_MAX_BODY_BYTES_ENV = "RESEARCH_AGENT_WEB_MAX_BODY_BYTES"
WEB_MAX_RESPONSE_BYTES_ENV = "RESEARCH_AGENT_WEB_MAX_RESPONSE_BYTES"
WEB_MAX_LLM_TIMEOUT_SECONDS_ENV = "RESEARCH_AGENT_WEB_MAX_LLM_TIMEOUT_SECONDS"
DEFAULT_WEB_MAX_BODY_BYTES = 1_048_576
DEFAULT_WEB_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_WEB_MAX_LLM_TIMEOUT_SECONDS = 30.0
WEB_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)
ARTIFACT_CONTENT_SECURITY_POLICY = (
    "sandbox; "
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "img-src data:; "
    "font-src data:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)
ARTIFACT_CONTENT_TYPES = {
    ".bib": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".md": "text/plain",
    ".ris": "text/plain",
    ".svg": "image/svg+xml",
    ".tex": "text/plain",
    ".zip": "application/zip",
}
RUN_SUMMARY_FIELDS = (
    "id",
    "topic",
    "stage",
    "status",
    "worker_active",
    "out_dir",
    "created_at",
    "updated_at",
    "approval",
    "execution_approval",
    "cancel",
    "repair_queue",
    "repair_resume_plan",
    "diagnostic",
    "final_readiness",
    "final_handoff",
    "error",
    "workflow",
)
ARTIFACTS = [
    "run-manifest.md",
    "run-manifest.json",
    LLM_TRACE_MD,
    LLM_TRACE_JSON,
    WORKFLOW_STATUS_JSON,
    TOOL_RECEIPTS_JSON,
    LLM_RUNTIME_CONTRACT_MD,
    LLM_RUNTIME_CONTRACT_JSON,
    LLM_OBSERVABILITY_SUMMARY_MD,
    LLM_OBSERVABILITY_SUMMARY_JSON,
    CANCEL_FILENAME,
    RUN_RECOVERY_PLAN_MD,
    RUN_RECOVERY_PLAN_JSON,
    PREFLIGHT_MD,
    PREFLIGHT_JSON,
    GOLD_RUN_DOCTOR_MD,
    GOLD_RUN_DOCTOR_JSON,
    GOLD_RUN_VERIFICATION_MD,
    GOLD_RUN_VERIFICATION_JSON,
    GOLD_LAUNCH_BUNDLE_MD,
    GOLD_LAUNCH_BUNDLE_JSON,
    GOLD_LAUNCH_MANIFEST_MD,
    GOLD_LAUNCH_MANIFEST_JSON,
    "00-question.md",
    HUMAN_BRIEF_MD,
    HUMAN_BRIEF_JSON,
    PRIOR_RUN_LESSONS_MD,
    PRIOR_RUN_LESSONS_JSON,
    PRIOR_RUN_LIBRARY_MD,
    PRIOR_RUN_LIBRARY_JSON,
    OPEN_SOURCE_LESSONS_MD,
    OPEN_SOURCE_LESSONS_JSON,
    OPEN_SOURCE_COMPLIANCE_MD,
    OPEN_SOURCE_COMPLIANCE_JSON,
    "00-research-plan.md",
    "00-research-plan.json",
    "01-literature.md",
    LITERATURE_RERANK_MD,
    LITERATURE_RERANK_JSON,
    LITERATURE_SEARCH_STRATEGY_MD,
    LITERATURE_SEARCH_STRATEGY_JSON,
    LITERATURE_SOURCE_HEALTH_MD,
    LITERATURE_SOURCE_HEALTH_JSON,
    QUERY_EXECUTION_AUDIT_MD,
    QUERY_EXECUTION_AUDIT_JSON,
    LITERATURE_SNOWBALL_MD,
    LITERATURE_SNOWBALL_JSON,
    LITERATURE_COVERAGE_MD,
    LITERATURE_COVERAGE_JSON,
    LITERATURE_EVIDENCE_MIX_MD,
    LITERATURE_EVIDENCE_MIX_JSON,
    LITERATURE_EVIDENCE_CONTRACT_MD,
    LITERATURE_EVIDENCE_CONTRACT_JSON,
    LITERATURE_GATE_DECISION_MD,
    LITERATURE_GATE_DECISION_JSON,
    LITERATURE_RESCUE_PLAN_MD,
    LITERATURE_RESCUE_PLAN_JSON,
    LITERATURE_RESCUE_EXECUTION_MD,
    LITERATURE_RESCUE_EXECUTION_JSON,
    LITERATURE_SEARCH_FEEDBACK_MD,
    LITERATURE_SEARCH_FEEDBACK_JSON,
    SEED_PAPER_INTAKE_MD,
    SEED_PAPER_INTAKE_JSON,
    "01-literature-curated.md",
    "01-literature-curated.json",
    LITERATURE_METADATA_AUDIT_MD,
    LITERATURE_METADATA_AUDIT_JSON,
    FULLTEXT_CORPUS_MD,
    FULLTEXT_CORPUS_JSON,
    "01-literature-quality.md",
    "01-literature-quality.json",
    "01-context.md",
    "01-review-gate.md",
    CITATION_AUDIT_MD,
    CITATION_AUDIT_JSON,
    APPROVAL_FILENAME,
    REVIEW_FEEDBACK_MD,
    REVIEW_FEEDBACK_JSON,
    REVIEW_REVISION_PLAN_MD,
    REVIEW_REVISION_PLAN_JSON,
    REVIEW_CONSTRAINTS_MD,
    REVIEW_CONSTRAINTS_JSON,
    "01-references.bib",
    "01-references.ris",
    "02-ideas.md",
    NOVELTY_AUDIT_MD,
    NOVELTY_AUDIT_JSON,
    IDEA_AUDIT_MD,
    IDEA_AUDIT_JSON,
    EXPLORATION_MAP_MD,
    EXPLORATION_MAP_JSON,
    EXPLORATION_MAP_SVG,
    EXPERIMENT_MANAGER_MD,
    EXPERIMENT_MANAGER_JSON,
    "03-experiment-plan.md",
    "03-experiment-plan.json",
    REVIEW_CONSTRAINT_COMPLIANCE_MD,
    REVIEW_CONSTRAINT_COMPLIANCE_JSON,
    EXPERIMENT_AUDIT_MD,
    EXPERIMENT_AUDIT_JSON,
    IDEA_EXPERIMENT_CONTRACT_MD,
    IDEA_EXPERIMENT_CONTRACT_JSON,
    EXECUTION_SAFETY_AUDIT_MD,
    EXECUTION_SAFETY_AUDIT_JSON,
    EXECUTION_APPROVAL_MD,
    EXECUTION_APPROVAL_JSON,
    ABLATION_PLAN_MD,
    ABLATION_PLAN_JSON,
    PREREGISTRATION_MD,
    PREREGISTRATION_JSON,
    BENCHMARK_PLAN_MD,
    BENCHMARK_PLAN_JSON,
    BENCHMARK_READINESS_MD,
    BENCHMARK_READINESS_JSON,
    BENCHMARK_ADAPTER_MD,
    BENCHMARK_ADAPTER_JSON,
    "04-results.csv",
    "04-results.json",
    EXPERIMENT_RUNBOOK_MD,
    EXPERIMENT_RUNBOOK_JSON,
    ENVIRONMENT_SNAPSHOT_MD,
    ENVIRONMENT_SNAPSHOT_JSON,
    "04-statistics.md",
    "04-statistics.json",
    "04-benchmark-pack-run.md",
    "04-benchmark-pack-run.json",
    RESULT_VALIDATION_MD,
    RESULT_VALIDATION_JSON,
    FAILURE_ANALYSIS_MD,
    FAILURE_ANALYSIS_JSON,
    BENCHMARK_RESULT_SCHEMA_AUDIT_MD,
    BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
    BENCHMARK_EVIDENCE_AUDIT_MD,
    BENCHMARK_EVIDENCE_AUDIT_JSON,
    EXPERIMENT_DECISION_MD,
    EXPERIMENT_DECISION_JSON,
    HYPOTHESIS_OUTCOME_MD,
    HYPOTHESIS_OUTCOME_JSON,
    CLAIM_BOUNDARY_PREFLIGHT_MD,
    CLAIM_BOUNDARY_PREFLIGHT_JSON,
    STATISTICS_FIGURE_SVG,
    STATISTICS_FIGURE_JSON,
    "05-analysis.md",
    "06-paper.md",
    "06-paper.tex",
    "07-paper-review.md",
    "07-paper-review.json",
    PAPER_REVIEW_CALIBRATION_MD,
    PAPER_REVIEW_CALIBRATION_JSON,
    REVISION_PLAN_MD,
    REVISION_PLAN_JSON,
    REVISED_PAPER_MD,
    REVISED_PAPER_TEX,
    REVISION_REPORT_MD,
    REVISION_REPORT_JSON,
    REVISION_RESPONSE_AUDIT_MD,
    REVISION_RESPONSE_AUDIT_JSON,
    REVISED_PAPER_REVIEW_MD,
    REVISED_PAPER_REVIEW_JSON,
    CITATION_GROUNDING_MD,
    CITATION_GROUNDING_JSON,
    CITATION_COVERAGE_MD,
    CITATION_COVERAGE_JSON,
    RESULTS_PRESENTATION_MD,
    RESULTS_PRESENTATION_JSON,
    CLAIM_CONSISTENCY_MD,
    CLAIM_CONSISTENCY_JSON,
    RELEASE_METADATA_MD,
    RELEASE_METADATA_JSON,
    CODE_DATA_AVAILABILITY_MD,
    CODE_DATA_AVAILABILITY_JSON,
    AI_DISCLOSURE_MD,
    AI_DISCLOSURE_JSON,
    SUBMISSION_CHECK_MD,
    SUBMISSION_CHECK_JSON,
    SUBMISSION_PACKAGE_MD,
    SUBMISSION_PACKAGE_JSON,
    SUBMISSION_PACKAGE_ZIP,
    ITERATION_PLAN_MD,
    ITERATION_PLAN_JSON,
    REPAIR_RESUME_PLAN_MD,
    REPAIR_RESUME_PLAN_JSON,
    REPAIR_RESOLUTION_AUDIT_MD,
    REPAIR_RESOLUTION_AUDIT_JSON,
    REPAIR_QUEUE_MD,
    REPAIR_QUEUE_JSON,
    HUMAN_GATE_AUDIT_MD,
    HUMAN_GATE_AUDIT_JSON,
    AGENT_STAGE_CONTRACT_MD,
    AGENT_STAGE_CONTRACT_JSON,
    AGENT_TRAJECTORY_MD,
    AGENT_TRAJECTORY_JSON,
    LLM_TRACE_AUDIT_MD,
    LLM_TRACE_AUDIT_JSON,
    RUN_ECONOMICS_AUDIT_MD,
    RUN_ECONOMICS_AUDIT_JSON,
    AGENT_OBSERVABILITY_AUDIT_MD,
    AGENT_OBSERVABILITY_AUDIT_JSON,
    RESEARCH_SCORECARD_MD,
    RESEARCH_SCORECARD_JSON,
    RUN_INTEGRITY_AUDIT_MD,
    RUN_INTEGRITY_AUDIT_JSON,
    FINAL_HANDOFF_MD,
    FINAL_HANDOFF_JSON,
    FINAL_READINESS_MD,
    FINAL_READINESS_JSON,
    RUN_DIAGNOSTIC_MD,
    RUN_DIAGNOSTIC_JSON,
]


class PreflightGateError(RuntimeError):
    def __init__(self, report: Any) -> None:
        self.report = report
        public = _public_preflight(report)
        super().__init__(f"preflight failed: {public.get('fails', 0)} blocking check(s)")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_safe_existing_path(path: Path, root: Path) -> bool:
    return path.exists() and _is_relative_to(path, root)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _created_at_from_run_id(run_id: str) -> str | None:
    from datetime import datetime, timezone

    match = re.search(r"-(\d{8}-\d{6})(?:-\d+)?$", run_id)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def _apply_run_status(record: dict[str, Any]) -> dict[str, Any]:
    worker_active = record.get("worker_active") is True
    cancel = record.get("cancel") if isinstance(record.get("cancel"), dict) else {}
    if cancel.get("cancelled") is True:
        record["status"] = "cancelled"
        record["stage"] = "cancelled"
        return record
    if cancel.get("requested") is True:
        record["status"] = "cancelling" if worker_active else "cancelled"
        if not worker_active:
            record["stage"] = "cancelled"
        return record
    if record.get("stage") == "review_revision_requested":
        record["status"] = "revision_requested"
    elif record.get("stage") == "awaiting_review_approval" and worker_active:
        approval = record.get("approval") if isinstance(record.get("approval"), dict) else {}
        record["status"] = "running" if approval.get("approved") is True else "waiting"
    elif record.get("stage") == "awaiting_review_approval" and record.get("status") not in {"completed", "failed"}:
        record["status"] = "waiting"
    elif record.get("stage") == "awaiting_execution_approval" and worker_active:
        approval = record.get("execution_approval") if isinstance(record.get("execution_approval"), dict) else {}
        record["status"] = "running" if approval.get("approved") is True else "waiting"
    elif record.get("stage") == "awaiting_execution_approval" and record.get("status") not in {"completed", "failed"}:
        record["status"] = "waiting"
    elif record.get("stage") == "awaiting_experiment_repair" and record.get("status") not in {"completed", "failed"}:
        record["status"] = "waiting"
    elif record.get("status") == "waiting" and not worker_active:
        record["status"] = "unknown"
    elif record.get("status") == "waiting":
        record["status"] = "running"
    if record.get("stage") == "completed" and record.get("status") in {"running", "waiting"}:
        record["status"] = "completed"
    return record


def _run_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {field: record.get(field) for field in RUN_SUMMARY_FIELDS}


def _workflow_summary(workflow: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(workflow, dict) or not workflow:
        return None
    return {
        key: workflow.get(key)
        for key in [
            "revision",
            "pipeline_stage",
            "current_node",
            "current_node_title",
            "agent_id",
            "task",
            "model",
            "activity_status",
            "activity_started_at",
            "updated_at",
            "completed_nodes",
            "total_nodes",
        ]
    }


def _reserve_new_run_out_dir(base_dir: Path) -> Path:
    parent = base_dir.parent
    stem = base_dir.name
    for index in range(1, 1000):
        candidate = base_dir if index == 1 else parent / f"{stem}-{index}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not allocate a fresh run output directory for {stem}")


class RunStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._run_operation_locks: dict[str, Lock] = {}
        self._runs: dict[str, dict[str, Any]] = {}
        self._load_existing_runs()

    def create(self, topic: str, config: AgentConfig, *, gold_launch_bundle_report: dict[str, Any] | None = None) -> dict[str, Any]:
        memory = build_run_memory(RUNS_DIR, limit=100)
        preflight = run_preflight(topic, config, ping_llm=False, run_memory=memory)
        if preflight.status == "fail":
            raise PreflightGateError(preflight)
        out_dir = _reserve_new_run_out_dir(ROOT / default_out_dir(topic))
        _write_run_config(out_dir, config)
        write_preflight_artifacts(preflight, out_dir)
        if gold_launch_bundle_report is not None:
            _write_gold_launch_bundle_artifacts(out_dir, gold_launch_bundle_report)
        run_id = out_dir.name
        created_at = _utc_now()
        record = {
            "id": run_id,
            "topic": topic,
            "stage": "queued",
            "status": "running",
            "worker_active": True,
            "out_dir": str(out_dir.relative_to(ROOT)),
            "config": _public_config(config),
            "artifacts": [name for name in ARTIFACTS if (out_dir / name).exists()],
            "approval": None,
            "execution_approval": None,
            "diagnostic": None,
            "final_readiness": None,
            "availability": None,
            "submission_package": None,
            "iteration_plan": None,
            "repair_queue": None,
            "repair_resume_plan": None,
            "gold_run_doctor": None,
            "gold_run_verification": None,
            "gold_post_launch": None,
            "experiment_manager": None,
            "benchmark_schema": None,
            "idea_experiment_gate": None,
            "literature_retrieval_gate": None,
            "literature_search_feedback": None,
            "literature_search_strategy": None,
            "literature_rescue_plan": None,
            "literature_rescue_execution": None,
            "seed_intake": None,
            "literature_evidence_contract": None,
            "literature_quality_gate": None,
            "run_integrity": None,
            "final_handoff": None,
            "agent_trajectory": None,
            "agent_observability": None,
            "workflow": None,
            "preflight": _public_preflight(preflight),
            "error": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        with self._lock:
            self._runs[run_id] = record
        worker = Thread(target=self._run_worker, args=(run_id, topic, out_dir, config), daemon=True)
        try:
            worker.start()
        except BaseException:
            with self._lock:
                stored = self._runs.get(run_id)
                if stored is not None:
                    stored.update({"status": "failed", "worker_active": False, "error": "worker failed to start"})
            raise
        return dict(record)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = [self._refresh_record(dict(record)) for record in self._runs.values()]
        return sorted(runs, key=lambda item: item["id"], reverse=True)

    def list_summary(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = [self._refresh_summary_record(dict(record)) for record in self._runs.values()]
        return sorted(runs, key=lambda item: item["id"], reverse=True)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            refreshed = self._refresh_record(dict(record))
            self._runs[run_id] = refreshed
            return dict(refreshed)

    def _run_exclusive_operation(self, run_id: str, operation: Any) -> Any:
        with self._lock:
            operation_lock = self._run_operation_locks.setdefault(run_id, Lock())
        if not operation_lock.acquire(blocking=False):
            raise RuntimeError("run already has an active operation")
        try:
            return operation()
        finally:
            operation_lock.release()

    def artifact_path(self, run_id: str, filename: str) -> Path | None:
        if filename not in ARTIFACTS:
            return None
        record = self.get(run_id)
        if record is None:
            return None
        path = (ROOT / record["out_dir"] / filename).resolve()
        if not _is_safe_existing_path(path, ROOT):
            return None
        return path

    def out_dir(self, run_id: str) -> Path | None:
        record = self.get(run_id)
        if record is None:
            return None
        path = (ROOT / record["out_dir"]).resolve()
        if not _is_safe_existing_path(path, ROOT):
            return None
        return path

    def approve(self, run_id: str, reviewer: str = "web") -> dict[str, Any] | None:
        return self.approve_with_config(run_id, reviewer=reviewer, payload={})

    def approve_with_config(self, run_id: str, reviewer: str = "web", payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._run_exclusive_operation(
            run_id,
            lambda: self._approve_with_config(run_id, reviewer=reviewer, payload=payload),
        )

    def _approve_with_config(self, run_id: str, reviewer: str = "web", payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        if record.get("status") in {"cancelling", "cancelled"}:
            raise RuntimeError("run is cancelling or cancelled")
        stage = str(record.get("stage") or "")
        if stage not in {"awaiting_review_approval", "review_revision_requested", "awaiting_execution_approval"}:
            raise RuntimeError("run is not waiting for approval")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        notes = str((payload or {}).get("review_notes") or "")
        worker_active = record.get("worker_active") is True
        approval_key = "execution_approval" if stage == "awaiting_execution_approval" else "approval"
        existing_approval = record.get(approval_key) if isinstance(record.get(approval_key), dict) else {}
        if worker_active and existing_approval.get("approved") is True:
            raise RuntimeError("run approval has already been granted")
        config: AgentConfig | None = None
        if not worker_active:
            config = _resume_config(out_dir, payload or {})
            _write_resume_preflight_or_raise(record.get("topic") or run_id, config, out_dir)
        if stage == "awaiting_execution_approval":
            approval = approve_execution_gate(out_dir, reviewer=reviewer, notes=notes)
        else:
            approval = approve_review_gate(out_dir, reviewer=reviewer, notes=notes)
        with self._lock:
            stored = self._runs.get(run_id)
            if stored is not None:
                stored[approval_key] = approval
                stored["status"] = "running"
                stored["error"] = None
                self._runs[run_id] = stored
        if not worker_active:
            assert config is not None
            topic = record.get("topic") or approval.get("topic") or run_id
            if stage == "awaiting_execution_approval":
                self._start_checkpoint_resume_worker(run_id, topic, out_dir, config)
            else:
                self._start_resume_worker(run_id, topic, out_dir, config)
        result = {"run": self.get(run_id), approval_key: approval}
        if approval_key != "approval":
            result["approval"] = approval
        return result

    def request_revision(self, run_id: str, reviewer: str = "web", notes: str = "") -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        if record.get("stage") != "awaiting_review_approval":
            raise RuntimeError("run is not waiting for review approval")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        approval = request_review_revision(out_dir, reviewer=reviewer, notes=notes)
        if record.get("worker_active") is True:
            self._update(run_id, status="revision_requested", error=None, approval=approval)
        else:
            _write_state_file(out_dir, record.get("topic") or approval.get("topic") or run_id, "review_revision_requested")
            write_run_recovery_plan_artifacts(out_dir, status="revision_requested")
            self._update(run_id, status="revision_requested", stage="review_revision_requested", worker_active=False, error=None, approval=approval)
        return {"run": self.get(run_id), "approval": approval}

    def cancel(self, run_id: str, requester: str = "web", reason: str = "") -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        if record.get("status") in {"completed", "failed", "cancelled"} or record.get("stage") in {"completed", "failed", "cancelled"}:
            raise RuntimeError("run is already terminal")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        cancel = request_cancel(out_dir, requester=requester, reason=reason)
        if record.get("worker_active") is True:
            self._update(run_id, status="cancelling", error=None, cancel=cancel)
        else:
            cancel = mark_cancelled(out_dir, topic=record.get("topic") or run_id, stage=record.get("stage") or "unknown")
            write_run_recovery_plan_artifacts(out_dir, status="cancelled")
            self._update(run_id, status="cancelled", stage="cancelled", worker_active=False, error=None, cancel=cancel)
        return {"run": self.get(run_id), "cancel": cancel}

    def resume_with_config(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._run_exclusive_operation(
            run_id,
            lambda: self._resume_with_config(run_id, payload=payload),
        )

    def _resume_with_config(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        if record.get("worker_active") is True:
            raise RuntimeError("run already has an active worker")
        if record.get("status") in {"completed", "cancelled", "cancelling"} or record.get("stage") in {"completed", "cancelled"}:
            raise RuntimeError("run is terminal and cannot be resumed")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        config = _resume_config(out_dir, payload or {})
        _write_resume_preflight_or_raise(record.get("topic") or run_id, config, out_dir)
        self._start_checkpoint_resume_worker(run_id, record.get("topic") or run_id, out_dir, config)
        return {"run": self.get(run_id)}

    def preview_repair_resume(self, run_id: str) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        if record.get("worker_active") is True:
            raise RuntimeError("run already has an active worker")
        if record.get("status") in {"cancelled", "cancelling"} or record.get("stage") == "cancelled":
            raise RuntimeError("run is cancelled and cannot be repair-resumed")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        if not _record_can_repair_resume(record):
            raise RuntimeError("run has no open repair queue or repair-resume plan")
        gold_verification_report_path = _repair_resume_gold_verification_report_path(out_dir)
        if _record_has_active_repair_queue(record):
            report = write_repair_resume_plan_artifacts(
                out_dir,
                apply=False,
                gold_verification_report_path=gold_verification_report_path,
            )
        else:
            report = _read_json_dict(out_dir / REPAIR_RESUME_PLAN_JSON)
            if report.get("can_resume") is not True:
                raise RuntimeError("run has no open repair queue or repair-resume plan")
        public_plan = _public_repair_resume_preview(report)
        return {
            "run": self.get(run_id),
            "plan": public_plan,
            "markdown": _render_public_repair_resume_preview_markdown(public_plan),
        }

    def repair_resume_with_config(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._run_exclusive_operation(
            run_id,
            lambda: self._repair_resume_with_config(run_id, payload=payload),
        )

    def _repair_resume_with_config(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        if record.get("worker_active") is True:
            raise RuntimeError("run already has an active worker")
        if record.get("status") in {"cancelled", "cancelling"} or record.get("stage") == "cancelled":
            raise RuntimeError("run is cancelled and cannot be repair-resumed")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        if not _record_can_repair_resume(record):
            raise RuntimeError("run has no open repair queue or repair-resume plan")
        gold_verification_report_path = _repair_resume_gold_verification_report_path(out_dir)
        config = _resume_config(out_dir, payload or {})
        _write_resume_preflight_or_raise(record.get("topic") or run_id, config, out_dir)
        self._start_repair_resume_worker(
            run_id,
            record.get("topic") or run_id,
            out_dir,
            config,
            gold_verification_report_path=gold_verification_report_path,
        )
        return {"run": self.get(run_id)}

    def rollback_options(self, run_id: str) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        return {
            "run_id": run_id,
            "revision": int((record.get("workflow") or {}).get("revision") or 0),
            "options": rollback_options(out_dir),
        }

    def preview_rollback(self, run_id: str, target: str) -> dict[str, Any] | None:
        return self._run_exclusive_operation(
            run_id,
            lambda: self._preview_rollback(run_id, target),
        )

    def _preview_rollback(self, run_id: str, target: str) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        self._validate_rollback_record(record)
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        return {"run": record, "preview": issue_rollback_preview(out_dir, target)}

    def rollback_with_config(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._run_exclusive_operation(
            run_id,
            lambda: self._rollback_with_config(run_id, payload),
        )

    def _rollback_with_config(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        record = self.get(run_id)
        if record is None:
            return None
        self._validate_rollback_record(record)
        target = str(payload.get("target") or payload.get("target_stage") or "").strip()
        preview_id = str(payload.get("preview_id") or "").strip()
        preview_token = str(payload.get("preview_token") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if len(reason) < 4:
            raise ValueError("rollback reason must contain at least 4 characters")
        out_dir = (ROOT / record["out_dir"]).resolve()
        if not _is_relative_to(out_dir, ROOT):
            return None
        config_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"target", "target_stage", "preview_id", "preview_token", "reason"}
        }
        config = _resume_config(out_dir, config_payload)
        _write_resume_preflight_or_raise(record.get("topic") or run_id, config, out_dir)
        report = apply_rollback(out_dir, target, preview_id, preview_token)
        report["reason"] = reason[:500]
        self._update(
            run_id,
            status="running",
            stage="rollback_applied",
            worker_active=False,
            error=None,
        )
        self._start_checkpoint_resume_worker(run_id, record.get("topic") or run_id, out_dir, config)
        return {"run": self.get(run_id), "rollback": report}

    @staticmethod
    def _validate_rollback_record(record: dict[str, Any]) -> None:
        if record.get("worker_active") is True:
            raise RuntimeError("stop the active worker before rolling back")
        if record.get("status") in {"cancelling", "cancelled"} or record.get("stage") == "cancelled":
            raise RuntimeError("cancelled runs cannot be rolled back")
        if record.get("status") == "running":
            raise RuntimeError("run state is still active; refresh it before rolling back")

    def _run_worker(self, run_id: str, topic: str, out_dir: Path, config: AgentConfig) -> None:
        try:
            self._update(run_id, status="running", stage="started")
            run_pipeline(topic, out_dir, config)
            _write_gold_verification_if_gold_launch(out_dir)
            self._record_worker_return(run_id, out_dir)
        except PipelineCancelled as exc:
            self._record_cancelled(run_id, topic, out_dir, exc)
        except PipelineReviewRevisionRequested as exc:
            self._record_revision_requested(run_id, topic, out_dir, exc)
        except Exception as exc:  # pragma: no cover - exposed through Web API
            self._record_failure(run_id, topic, out_dir, exc)
        finally:
            self._update(run_id, worker_active=False)

    def _start_resume_worker(self, run_id: str, topic: str, out_dir: Path, config: AgentConfig) -> None:
        self._start_worker(run_id, self._resume_worker, (run_id, topic, out_dir, config))

    def _start_checkpoint_resume_worker(self, run_id: str, topic: str, out_dir: Path, config: AgentConfig) -> None:
        self._start_worker(run_id, self._checkpoint_resume_worker, (run_id, topic, out_dir, config))

    def _start_repair_resume_worker(
        self,
        run_id: str,
        topic: str,
        out_dir: Path,
        config: AgentConfig,
        *,
        gold_verification_report_path: Path | None = None,
    ) -> None:
        self._start_worker(
            run_id,
            self._repair_resume_worker,
            (run_id, topic, out_dir, config, gold_verification_report_path),
        )

    def _start_worker(self, run_id: str, target: Any, args: tuple[Any, ...]) -> None:
        worker = Thread(target=target, args=args, daemon=True)
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                raise RuntimeError("run not found")
            if record.get("worker_active") is True:
                raise RuntimeError("run already has an active worker")
            previous_status = record.get("status")
            previous_error = record.get("error")
            record.update({"status": "running", "worker_active": True, "error": None})
            self._runs[run_id] = record
        try:
            worker.start()
        except BaseException:
            with self._lock:
                record = self._runs.get(run_id)
                if record is not None and record.get("worker_active") is True:
                    record.update({"status": previous_status, "worker_active": False, "error": previous_error})
                    self._runs[run_id] = _apply_run_status(record)
            raise

    def _resume_worker(self, run_id: str, topic: str, out_dir: Path, config: AgentConfig) -> None:
        try:
            self._update(run_id, status="running", stage="review_approved", worker_active=True, error=None)
            resume_pipeline_after_review_approval(topic, out_dir, config)
            _write_gold_verification_if_gold_launch(out_dir)
            self._record_worker_return(run_id, out_dir)
        except PipelineCancelled as exc:
            self._record_cancelled(run_id, topic, out_dir, exc)
        except PipelineReviewRevisionRequested as exc:
            self._record_revision_requested(run_id, topic, out_dir, exc)
        except Exception as exc:  # pragma: no cover - exposed through Web API
            self._record_failure(run_id, topic, out_dir, exc)
        finally:
            self._update(run_id, worker_active=False)

    def _checkpoint_resume_worker(self, run_id: str, topic: str, out_dir: Path, config: AgentConfig) -> None:
        try:
            self._update(run_id, status="running", worker_active=True, error=None)
            resume_pipeline_from_checkpoint(topic, out_dir, config)
            _write_gold_verification_if_gold_launch(out_dir)
            self._record_worker_return(run_id, out_dir)
        except PipelineCancelled as exc:
            self._record_cancelled(run_id, topic, out_dir, exc)
        except PipelineReviewRevisionRequested as exc:
            self._record_revision_requested(run_id, topic, out_dir, exc)
        except Exception as exc:  # pragma: no cover - exposed through Web API
            self._record_failure(run_id, topic, out_dir, exc)
        finally:
            self._update(run_id, worker_active=False)

    def _repair_resume_worker(
        self,
        run_id: str,
        topic: str,
        out_dir: Path,
        config: AgentConfig,
        gold_verification_report_path: Path | None = None,
    ) -> None:
        try:
            self._update(run_id, status="running", worker_active=True, error=None)
            if gold_verification_report_path is None:
                resume_pipeline_from_repair_queue(topic, out_dir, config)
            else:
                resume_pipeline_from_repair_queue(
                    topic,
                    out_dir,
                    config,
                    gold_verification_report_path=gold_verification_report_path,
                )
            _write_gold_verification_if_gold_launch(out_dir)
            self._record_worker_return(run_id, out_dir)
        except PipelineCancelled as exc:
            self._record_cancelled(run_id, topic, out_dir, exc)
        except PipelineReviewRevisionRequested as exc:
            self._record_revision_requested(run_id, topic, out_dir, exc)
        except Exception as exc:  # pragma: no cover - exposed through Web API
            self._record_failure(run_id, topic, out_dir, exc)
        finally:
            self._update(run_id, worker_active=False)

    def _record_worker_return(self, run_id: str, out_dir: Path) -> None:
        state = _read_json_object(out_dir / "state.json") or {}
        stage = str(state.get("stage") or "completed")
        if stage == "awaiting_experiment_repair":
            self._update(run_id, status="waiting", stage=stage, error=None)
        elif stage == "review_revision_requested":
            self._update(run_id, status="revision_requested", stage=stage, error=None)
        elif stage in {"awaiting_review_approval", "awaiting_execution_approval"}:
            self._update(run_id, status="waiting", stage=stage, error=None)
        else:
            self._update(run_id, status="completed", stage="completed", error=None)

    def _record_failure(self, run_id: str, topic: str, out_dir: Path, exc: BaseException) -> None:
        if (out_dir / CANCEL_FILENAME).exists():
            self._record_cancelled(run_id, topic, out_dir, PipelineCancelled(out_dir, self.get(run_id).get("stage", "unknown") if self.get(run_id) else "unknown"))
            return
        trace = traceback.format_exc()
        stage = self.get(run_id).get("stage", "failed") if self.get(run_id) else "failed"
        diagnostic = diagnose_exception(exc, topic=topic, stage=stage, traceback_text=trace)
        write_json(out_dir / RUN_DIAGNOSTIC_JSON, diagnostic)
        write_text(out_dir / RUN_DIAGNOSTIC_MD, render_diagnostic_markdown(diagnostic))
        write_run_recovery_plan_artifacts(out_dir, status="failed")
        self._update(
            run_id,
            status="failed",
            stage="failed",
            error=diagnostic.summary,
            diagnostic=_public_diagnostic(diagnostic),
        )

    def _record_cancelled(self, run_id: str, topic: str, out_dir: Path, exc: PipelineCancelled) -> None:
        cancel = mark_cancelled(out_dir, topic=topic, stage=exc.stage)
        write_run_recovery_plan_artifacts(out_dir, status="cancelled")
        self._update(run_id, status="cancelled", stage="cancelled", error=None, diagnostic=None, cancel=cancel)

    def _record_revision_requested(self, run_id: str, topic: str, out_dir: Path, exc: PipelineReviewRevisionRequested) -> None:
        _write_state_file(out_dir, topic, "review_revision_requested")
        write_run_recovery_plan_artifacts(out_dir, status="revision_requested")
        self._update(run_id, status="revision_requested", stage="review_revision_requested", error=None, diagnostic=None)

    def _update(self, run_id: str, **changes: Any) -> None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return
            record.update(changes)
            self._runs[run_id] = self._refresh_record(record)

    def _refresh_record(self, record: dict[str, Any]) -> dict[str, Any]:
        try:
            out_dir = (ROOT / record["out_dir"]).resolve()
        except OSError:
            record["artifacts"] = []
            record["status"] = "invalid"
            record["error"] = "run path cannot be resolved"
            return record
        if not _is_relative_to(out_dir, ROOT):
            record["artifacts"] = []
            record["status"] = "invalid"
            record["error"] = "run path is outside project root"
            return record
        state_path = out_dir / "state.json"
        if state_path.exists() and record.get("status") != "failed":
            state = _read_json_object(state_path)
            if state is not None:
                record["stage"] = state.get("stage", record["stage"])
                record["updated_at"] = state.get("updated_at")
                record["created_at"] = state.get("created_at", record.get("created_at"))
        approval_path = out_dir / APPROVAL_FILENAME
        record["approval"] = None
        if approval_path.exists():
            approval = _read_json_object(approval_path)
            if approval is not None:
                record["approval"] = _public_approval_record(approval)
        execution_approval_path = out_dir / EXECUTION_APPROVAL_JSON
        record["execution_approval"] = None
        if execution_approval_path.exists():
            execution_approval = _read_json_object(execution_approval_path)
            if execution_approval is not None:
                record["execution_approval"] = _public_execution_approval_record(execution_approval)
        cancel_path = out_dir / CANCEL_FILENAME
        record["cancel"] = None
        if cancel_path.exists():
            record["cancel"] = _read_json_object(cancel_path)
        record["artifacts"] = [name for name in ARTIFACTS if (out_dir / name).exists()]
        record["diagnostic"] = _read_public_diagnostic(out_dir)
        record["final_readiness"] = _read_public_final_readiness(out_dir)
        record["availability"] = _read_public_availability(out_dir)
        record["submission_package"] = _read_public_submission_package(out_dir)
        record["iteration_plan"] = _read_public_iteration_plan(out_dir)
        record["repair_queue"] = _read_public_repair_queue(out_dir)
        record["repair_resume_plan"] = _read_public_repair_resume_plan(out_dir)
        record["gold_run_doctor"] = _read_public_gold_run_doctor(out_dir)
        record["gold_run_verification"] = _read_public_gold_run_verification(out_dir)
        record["gold_post_launch"] = _read_public_gold_post_launch(out_dir)
        record["repair_resolution"] = _read_public_repair_resolution(out_dir)
        record["experiment_manager"] = _read_public_experiment_manager(out_dir)
        record["benchmark_schema"] = _read_public_benchmark_schema(out_dir)
        record["idea_experiment_gate"] = _read_public_idea_experiment_gate(record, out_dir)
        record["literature_retrieval_gate"] = _read_public_literature_retrieval_gate(out_dir)
        record["literature_search_feedback"] = _read_public_literature_search_feedback(out_dir)
        record["literature_search_strategy"] = _read_public_literature_search_strategy(out_dir)
        record["literature_rescue_plan"] = _read_public_literature_rescue_plan(out_dir)
        record["literature_rescue_execution"] = _read_public_literature_rescue_execution(out_dir)
        record["seed_intake"] = _read_public_seed_intake(out_dir, topic=str(record.get("topic") or ""))
        record["literature_evidence_contract"] = _read_public_literature_evidence_contract(out_dir)
        record["literature_gate_decision"] = _read_public_literature_gate_decision(out_dir)
        record["literature_quality_gate"] = _read_public_literature_quality_gate(record, out_dir)
        record["run_integrity"] = _read_public_run_integrity(out_dir)
        record["final_handoff"] = _read_public_final_handoff(out_dir)
        record["agent_trajectory"] = _read_public_agent_trajectory(out_dir)
        record["agent_observability"] = _read_public_agent_observability(out_dir)
        record["workflow"] = read_workflow_status(out_dir)
        record["human_gate_audit"] = _read_public_human_gate_audit(out_dir)
        record["llm_runtime_contract"] = _read_public_llm_runtime_contract(out_dir)
        record["llm_observability"] = _read_public_llm_observability_summary(out_dir)
        record["open_source_compliance"] = _read_public_open_source_compliance(out_dir)
        record["preflight"] = _read_public_preflight(out_dir)
        return _apply_run_status(record)

    def _refresh_summary_record(self, record: dict[str, Any]) -> dict[str, Any]:
        try:
            out_dir = (ROOT / record["out_dir"]).resolve()
        except (KeyError, OSError):
            record["status"] = "invalid"
            record["error"] = "run path cannot be resolved"
            return _run_summary(record)
        if not _is_relative_to(out_dir, ROOT):
            record["status"] = "invalid"
            record["error"] = "run path is outside project root"
            return _run_summary(record)

        state = _read_json_object(out_dir / "state.json")
        if state is not None and record.get("status") != "failed":
            record["stage"] = state.get("stage", record.get("stage", "unknown"))
            record["updated_at"] = state.get("updated_at", record.get("updated_at"))
            record["created_at"] = state.get("created_at", record.get("created_at"))

        approval = _read_json_object(out_dir / APPROVAL_FILENAME)
        record["approval"] = _public_approval_record(approval) if approval is not None else None
        execution_approval = _read_json_object(out_dir / EXECUTION_APPROVAL_JSON)
        record["execution_approval"] = _public_execution_approval_record(execution_approval) if execution_approval is not None else None
        record["cancel"] = _read_json_object(out_dir / CANCEL_FILENAME)
        record["diagnostic"] = _read_public_diagnostic(out_dir)
        record["final_readiness"] = _read_public_final_readiness(out_dir)
        record["repair_queue"] = _read_public_repair_queue(out_dir)
        record["repair_resume_plan"] = _read_public_repair_resume_plan(out_dir)
        record["final_handoff"] = _read_public_final_handoff(out_dir)
        record["workflow"] = _workflow_summary(read_workflow_status(out_dir))
        return _run_summary(_apply_run_status(record))

    def _load_existing_runs(self) -> None:
        if not RUNS_DIR.exists():
            return
        for state_path in RUNS_DIR.glob("*/state.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(state, dict):
                continue
            run_id = state_path.parent.name
            run_config = _load_run_config(state_path.parent)
            stage = state.get("stage", "unknown")
            self._runs[run_id] = {
                "id": run_id,
                "topic": state.get("topic", run_id),
                "stage": stage,
                "status": "completed" if stage == "completed" else "cancelled" if stage == "cancelled" else "revision_requested" if stage == "review_revision_requested" else "unknown",
                "worker_active": False,
                "out_dir": str(state_path.parent.relative_to(ROOT)),
                "config": _public_config(run_config) if run_config is not None else None,
                "artifacts": [],
                "approval": None,
                "execution_approval": None,
                "cancel": None,
                "diagnostic": None,
                "final_readiness": None,
                "availability": None,
                "submission_package": None,
                "iteration_plan": None,
                "repair_queue": None,
                "repair_resume_plan": None,
                "gold_run_doctor": None,
                "gold_run_verification": None,
                "gold_post_launch": None,
                "experiment_manager": None,
                "benchmark_schema": None,
                "idea_experiment_gate": None,
                "literature_retrieval_gate": None,
                "literature_search_feedback": None,
                "literature_search_strategy": None,
                "literature_rescue_plan": None,
                "literature_rescue_execution": None,
                "seed_intake": None,
                "literature_evidence_contract": None,
                "literature_quality_gate": None,
                "run_integrity": None,
                "final_handoff": None,
                "agent_trajectory": None,
                "agent_observability": None,
                "workflow": None,
                "human_gate_audit": None,
                "llm_runtime_contract": None,
                "llm_observability": None,
                "open_source_compliance": None,
                "preflight": None,
                "error": None,
                "created_at": state.get("created_at") or _created_at_from_run_id(run_id) or state.get("updated_at"),
                "updated_at": state.get("updated_at"),
            }


def _normalize_web_host(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        return host


def _web_authority(value: str) -> tuple[str, int | None] | None:
    if not value or any(char in value for char in "\r\n"):
        return None
    try:
        parsed = urlparse(f"//{value}")
        port = parsed.port
    except ValueError:
        return None
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path or parsed.query or parsed.fragment:
        return None
    return _normalize_web_host(parsed.hostname), port


def _is_loopback_host(host: str) -> bool:
    normalized = _normalize_web_host(host)
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        pass
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
            if item[4]
        }
    except socket.gaierror:
        return False
    return bool(addresses) and all(ipaddress.ip_address(address).is_loopback for address in addresses)


def _allowed_web_hosts(bind_host: str) -> set[str]:
    normalized = _normalize_web_host(bind_host)
    allowed = {normalized}
    wildcard = normalized in {"", "0.0.0.0", "::"}
    if wildcard or _is_loopback_host(normalized):
        allowed.update({"localhost", "127.0.0.1", "::1"})
    names = {socket.gethostname(), socket.getfqdn()} if wildcard else {bind_host}
    if wildcard:
        allowed.update(_normalize_web_host(name) for name in names if name)
    for name in names:
        try:
            addresses = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            continue
        allowed.update(_normalize_web_host(item[4][0]) for item in addresses if item[4])
    return {host for host in allowed if host and host not in {"0.0.0.0", "::"}}


def _web_max_body_bytes() -> int:
    return _positive_web_env_int(WEB_MAX_BODY_BYTES_ENV, DEFAULT_WEB_MAX_BODY_BYTES)


def _web_max_response_bytes() -> int:
    return _positive_web_env_int(WEB_MAX_RESPONSE_BYTES_ENV, DEFAULT_WEB_MAX_RESPONSE_BYTES)


def _positive_web_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _web_max_llm_timeout_seconds() -> float:
    raw = os.environ.get(WEB_MAX_LLM_TIMEOUT_SECONDS_ENV, "").strip()
    if not raw:
        return DEFAULT_WEB_MAX_LLM_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{WEB_MAX_LLM_TIMEOUT_SECONDS_ENV} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{WEB_MAX_LLM_TIMEOUT_SECONDS_ENV} must be a positive finite number")
    return value


def _bounded_llm_timeout(value: Any, default: float) -> float:
    timeout = float(value) if value not in {None, ""} else default
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("LLM timeout must be a positive finite number")
    return min(timeout, _web_max_llm_timeout_seconds())


def _configure_web_server(server: ThreadingHTTPServer, bind_host: str) -> None:
    token = os.environ.get(WEB_TOKEN_ENV, "")
    if not _is_loopback_host(bind_host):
        if not token:
            raise ValueError(f"{WEB_TOKEN_ENV} is required when binding to a non-loopback host")
        if len(token) < 16:
            raise ValueError(f"{WEB_TOKEN_ENV} must contain at least 16 characters when binding to a non-loopback host")
    server.research_agent_bind_host = bind_host  # type: ignore[attr-defined]
    server.research_agent_allowed_hosts = _allowed_web_hosts(bind_host)  # type: ignore[attr-defined]
    server.research_agent_web_token = token  # type: ignore[attr-defined]
    server.research_agent_max_body_bytes = _web_max_body_bytes()  # type: ignore[attr-defined]
    server.research_agent_max_response_bytes = _web_max_response_bytes()  # type: ignore[attr-defined]
    _web_max_llm_timeout_seconds()


class ResearchAgentHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not self._validate_request(require_json=False):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/summary":
            dashboard = build_run_dashboard(RUNS_DIR, limit=100)
            memory = build_run_memory(RUNS_DIR, limit=100)
            dashboard_markdown = render_run_dashboard_markdown(dashboard)
            memory_markdown = render_run_memory_markdown(memory)
            self._send_json(
                {
                    "dashboard": asdict(dashboard),
                    "memory": asdict(memory),
                    "markdown": dashboard_markdown + "\n\n" + memory_markdown,
                    "memory_markdown": memory_markdown,
                }
            )
            return
        if parsed.path == "/api/library":
            query = parse_qs(parsed.query).get("q", [""])[0]
            library = build_run_library(RUNS_DIR, limit=100)
            results = search_run_library(library, query, limit=20) if query else None
            self._send_json(
                {
                    "library": asdict(library),
                    "results": [asdict(item) for item in results] if results is not None else None,
                    "markdown": render_run_library_markdown(library, query=query, results=results),
                }
            )
            return
        if parsed.path == "/api/platform-audit":
            report = build_platform_audit(RUNS_DIR, limit=100)
            self._send_json(
                {
                    "audit": asdict(report),
                    "markdown": render_platform_audit_markdown(report),
                }
            )
            return
        if parsed.path == "/api/perfect-readiness":
            report = build_perfect_agent_readiness(ROOT, RUNS_DIR, limit=0)
            self._send_json(
                {
                    "report": asdict(report),
                    "markdown": render_perfect_agent_readiness_markdown(report),
                }
            )
            return
        if parsed.path == "/api/open-source-compliance-backfill":
            report = backfill_open_source_compliance(RUNS_DIR, dry_run=True, force=False, limit=0)
            self._send_json({"report": report, "markdown": render_open_source_compliance_backfill_markdown(report)})
            return
        if parsed.path == "/api/llm-observability-backfill":
            report = backfill_llm_observability(RUNS_DIR, dry_run=True, force=False, limit=0)
            public_report = _public_llm_observability_backfill_report(report)
            self._send_json({"report": public_report, "markdown": render_llm_observability_backfill_markdown(public_report)})
            return
        if parsed.path == "/api/repair-resume-backfill":
            report = backfill_repair_resume_plans(RUNS_DIR, dry_run=True, force=False, limit=0)
            public_report = _public_repair_resume_backfill_report(report)
            self._send_json({"report": public_report, "markdown": render_repair_resume_backfill_markdown(public_report)})
            return
        if parsed.path == "/api/repair-resume-backlog":
            report = build_repair_resume_backlog(RUNS_DIR, limit=0)
            public_report = _public_repair_resume_backlog_report(report)
            self._send_json({"report": public_report, "markdown": render_repair_resume_backlog_markdown(public_report)})
            return
        if parsed.path == "/api/runs":
            query = parse_qs(parsed.query)
            view = query.get("view", [""])[0].strip().lower()
            if not view and query.get("summary", [""])[0].strip().lower() in {"1", "true", "yes"}:
                view = "summary"
            if view == "summary":
                self._send_json({"runs": STORE.list_summary()})
            elif view in {"", "full", "detail"}:
                self._send_json({"runs": STORE.list()})
            else:
                self._send_json({"error": "unsupported runs view"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/benchmark-examples":
            self._send_json({"examples": _benchmark_examples()})
            return
        if parsed.path == "/api/gold-defaults":
            defaults = _gold_defaults()
            self._send_json({"defaults": defaults, "markdown": _render_gold_defaults_markdown(defaults)})
            return
        if parsed.path == "/api/gold-defaults-smoke":
            report = build_gold_defaults_smoke_report()
            self._send_json({"report": report, "markdown": render_gold_defaults_smoke_markdown(report)})
            return
        if parsed.path == "/api/gold-env-launch-kit":
            report = build_gold_env_launch_kit(AgentConfig(), payload={})
            self._send_json({"report": report, "markdown": render_gold_env_launch_kit_markdown(report)})
            return
        if parsed.path == "/api/benchmark-template":
            topic = parse_qs(parsed.query).get("topic", [""])[0]
            self._send_json(_benchmark_template(topic))
            return
        if parsed.path.startswith("/api/runs/"):
            self._handle_run_get(parsed.path, parsed.query)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        if not self._validate_request(require_json=True):
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/runs":
            self._handle_run_create()
            return
        if parsed.path == "/api/fetch-models":
            self._handle_fetch_models()
            return
        if parsed.path == "/api/test-llm":
            self._handle_test_llm()
            return
        if parsed.path == "/api/preflight":
            self._handle_preflight()
            return
        if parsed.path == "/api/env-llm-preflight":
            self._handle_env_llm_preflight()
            return
        if parsed.path == "/api/gold-env-lint":
            self._handle_gold_env_lint()
            return
        if parsed.path == "/api/gold-env-launch-kit":
            self._handle_gold_env_launch_kit()
            return
        if parsed.path == "/api/gold-defaults-smoke":
            self._handle_gold_defaults_smoke()
            return
        if parsed.path == "/api/gold-launch-bundle":
            self._handle_gold_launch_bundle()
            return
        if parsed.path == "/api/gold-run-launch":
            self._handle_gold_run_launch()
            return
        if parsed.path == "/api/gold-run-doctor":
            self._handle_gold_run_doctor()
            return
        if parsed.path == "/api/gold-run-verify":
            self._handle_gold_run_verify()
            return
        if parsed.path == "/api/literature-preview":
            self._handle_literature_preview()
            return
        if parsed.path == "/api/paper-grade-probe":
            self._handle_paper_grade_probe()
            return
        if parsed.path == "/api/benchmark-preview":
            self._handle_benchmark_preview()
            return
        if parsed.path == "/api/benchmark-manifest-lint":
            self._handle_benchmark_manifest_lint()
            return
        if parsed.path == "/api/benchmark-manifest-save":
            self._handle_benchmark_manifest_save()
            return
        if parsed.path == "/api/release-metadata-lint":
            self._handle_release_metadata_lint()
            return
        if parsed.path == "/api/open-source-compliance-backfill":
            self._handle_open_source_compliance_backfill()
            return
        if parsed.path == "/api/llm-observability-backfill":
            self._handle_llm_observability_backfill()
            return
        if parsed.path == "/api/repair-resume-backfill":
            self._handle_repair_resume_backfill()
            return
        if parsed.path.startswith("/api/runs/"):
            self._handle_run_post(parsed.path)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_fetch_models(self) -> None:
        from .llm import fetch_provider_models
        try:
            payload = self._read_json()
            _validate_payload_llm_connection(payload)
            provider = str(payload.get("llm_provider", "openai-compatible")).strip()
            base_url = str(payload.get("llm_base_url", "")).strip()
            api_key = str(payload.get("llm_api_key", "")).strip()
            timeout = _bounded_llm_timeout(payload.get("timeout_seconds"), 8.0)
            res = fetch_provider_models(provider, base_url, api_key, timeout_seconds=timeout)
            self._send_json(res)
        except Exception as exc:
            self._send_json({"success": False, "error": str(exc), "models": []}, HTTPStatus.BAD_REQUEST)

    def _handle_test_llm(self) -> None:
        import time
        from .preflight import _llm_ping_check
        try:
            payload = self._read_json()
            config = _config_from_payload(payload)
            timeout = _bounded_llm_timeout(payload.get("timeout_seconds"), 10.0)
            start_time = time.perf_counter()
            check = _llm_ping_check(config, timeout_seconds=timeout)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            self._send_json({
                "status": check.status,
                "summary": check.summary,
                "detail": check.detail,
                "action": check.action,
                "latency_ms": elapsed_ms,
                "model": config.llm.model or os.environ.get("OPENAI_MODEL", ""),
                "base_url": config.llm.base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            })
        except Exception as exc:
            self._send_json({"status": "fail", "summary": "测试异常", "detail": str(exc), "latency_ms": 0}, HTTPStatus.BAD_REQUEST)

    def _handle_preflight(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            ping_llm = bool(payload.get("ping_llm", True))
            _reject_paper_grade_payload_secrets(AgentConfig(), payload)
            memory = build_run_memory(RUNS_DIR, limit=100)
            report = run_preflight(topic, _config_from_payload(payload), ping_llm=ping_llm, run_memory=memory)
            self._send_json({"report": asdict(report), "memory": asdict(memory), "markdown": render_preflight_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_env_llm_preflight(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip() or "server env LLM preflight"
            config = _env_llm_config_from_payload(payload)
            report = run_preflight(
                topic,
                config,
                ping_llm=True,
                llm_timeout_seconds=_bounded_llm_timeout(payload.get("llm_timeout_seconds"), 8.0),
                run_memory=None,
            )
            secrets = _env_llm_public_secrets(payload, config)
            env_llm = _public_env_llm_preflight(report, config, payload)
            self._send_json(
                {
                    "report": _public_preflight(report),
                    "env_llm": env_llm,
                    "markdown": _sanitize_public_text(_render_env_llm_preflight_markdown(report, env_llm), secrets),
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_env_lint(self) -> None:
        try:
            payload = self._read_json()
            ignored = _payload_secret_fields(payload)
            public_payload = {key: value for key, value in payload.items() if key not in ignored}
            config = _config_from_payload(public_payload)
            report = build_gold_environment_lint(config)
            public_report = {**report, "ignored_payload_secret_fields": ignored}
            self._send_json({"report": public_report, "markdown": render_gold_environment_lint_markdown(public_report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_env_launch_kit(self) -> None:
        try:
            payload = self._read_json()
            config = _config_from_payload(payload)
            report = build_gold_env_launch_kit(config, payload=payload)
            self._send_json({"report": report, "markdown": render_gold_env_launch_kit_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_defaults_smoke(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic") or "").strip() or GOLD_DEFAULT_SMOKE_TOPIC
            report = build_gold_defaults_smoke_report(topic)
            self._send_json({"report": report, "markdown": render_gold_defaults_smoke_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_launch_bundle(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            if not topic:
                self._send_json({"error": "topic is required"}, HTTPStatus.BAD_REQUEST)
                return
            config = _config_from_payload(payload)
            report = build_gold_launch_bundle_report(
                topic,
                config,
                benchmark_pack_run_dir=_payload_existing_path(payload, "benchmark_pack_run_dir"),
                fulltext_grounding_run_dir=_payload_existing_path(payload, "fulltext_grounding_run_dir"),
                candidate_run_dir=_candidate_run_dir_from_payload(payload),
                payload=payload,
                base_dir=ROOT,
            )
            self._send_json({"report": report, "markdown": render_gold_launch_bundle_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_run_launch(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            if not topic:
                self._send_json({"error": "topic is required"}, HTTPStatus.BAD_REQUEST)
                return
            launch_payload = {**payload, "paper_grade_enabled": True}
            _reject_paper_grade_payload_secrets(AgentConfig(), launch_payload)
            config = _config_from_payload(launch_payload)
            report = build_gold_launch_bundle_report(
                topic,
                config,
                benchmark_pack_run_dir=_payload_existing_path(launch_payload, "benchmark_pack_run_dir"),
                fulltext_grounding_run_dir=_payload_existing_path(launch_payload, "fulltext_grounding_run_dir"),
                candidate_run_dir=None,
                payload=launch_payload,
                base_dir=ROOT,
            )
            markdown = render_gold_launch_bundle_markdown(report)
            if report.get("status") != "ready_to_start" or report.get("can_start_gold_run") is not True:
                self._send_json({"error": "gold launch blocked", "report": report, "markdown": markdown}, HTTPStatus.CONFLICT)
                return
            record = STORE.create(topic, config, gold_launch_bundle_report=report)
            self._send_json(
                {
                    "run": record,
                    "launch_bundle": report,
                    "post_launch_guidance": _gold_run_post_launch_guidance(record),
                    "markdown": markdown,
                },
                HTTPStatus.CREATED,
            )
        except PreflightGateError as exc:
            self._send_json(_preflight_error_payload(exc.report), HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_run_doctor(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            if not topic:
                self._send_json({"error": "topic is required"}, HTTPStatus.BAD_REQUEST)
                return
            report = build_gold_run_doctor(
                topic=topic,
                config=_config_from_payload(payload),
                benchmark_pack_run_dir=_payload_existing_path(payload, "benchmark_pack_run_dir"),
                fulltext_grounding_run_dir=_payload_existing_path(payload, "fulltext_grounding_run_dir"),
                candidate_run_dir=_candidate_run_dir_from_payload(payload),
                ping_llm=bool(payload.get("ping_llm", False)),
                llm_timeout_seconds=_bounded_llm_timeout(payload.get("llm_timeout_seconds"), 8.0),
            )
            public_report = _public_gold_run_doctor_report(report)
            launch = report.get("launch_manifest") if isinstance(report.get("launch_manifest"), dict) else {}
            public_launch = _public_gold_launch_manifest_report(launch) if launch else {}
            doctor_markdown = _render_public_summary_artifact_markdown(GOLD_RUN_DOCTOR_MD, public_report)
            launch_markdown = _render_public_summary_artifact_markdown(GOLD_LAUNCH_MANIFEST_MD, public_launch) if public_launch else ""
            launch_commands = _live_gold_launch_commands(report)
            command_markdown = _render_live_gold_launch_commands_markdown(launch_commands)
            self._send_json(
                {
                    "report": public_report,
                    "launch_manifest": public_launch,
                    "launch_commands": launch_commands,
                    "markdown": doctor_markdown + (f"\n\n{launch_markdown}" if launch_markdown else "") + (f"\n\n{command_markdown}" if command_markdown else ""),
                    "launch_markdown": launch_markdown,
                    "launch_command_markdown": command_markdown,
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_gold_run_verify(self) -> None:
        try:
            payload = self._read_json()
            if not str(payload.get("candidate_run_id") or "").strip():
                self._send_json({"error": "candidate_run_id is required"}, HTTPStatus.BAD_REQUEST)
                return
            candidate_dir = _candidate_run_dir_from_payload(payload)
            if candidate_dir is None:
                self._send_json({"error": "candidate_run_id is required"}, HTTPStatus.BAD_REQUEST)
                return
            report = write_gold_run_verification_artifacts(candidate_dir)
            followups = _write_gold_verification_followups(candidate_dir, report)
            public_report = _public_gold_run_verification_report(report, fallback_run_id=candidate_dir.name)
            STORE.get(candidate_dir.name)
            self._send_json(
                {
                    "report": public_report,
                    "markdown": _render_public_summary_artifact_markdown(GOLD_RUN_VERIFICATION_MD, public_report),
                    "read_only": False,
                    "wrote_artifacts": followups["verification_written"],
                    "repair_resume_plan": _read_public_repair_resume_plan(candidate_dir),
                    "gold_post_launch": _read_public_gold_post_launch(candidate_dir),
                    "perfect_readiness_written": followups["perfect_readiness_written"],
                }
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_literature_preview(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            config = _config_from_payload(payload)
            report = _literature_preview_report(topic, config.literature)
            self._send_json({"report": report, "markdown": _render_literature_preview_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_paper_grade_probe(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            if not topic:
                self._send_json({"error": "topic is required"}, HTTPStatus.BAD_REQUEST)
                return
            config = _config_from_payload(payload)
            report = build_paper_grade_online_probe(topic, config, client_factory=OnlineLiteratureClient)
            public_report = _public_paper_grade_probe_report(report, config)
            self._send_json({"report": public_report, "markdown": render_paper_grade_online_probe_markdown(public_report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_benchmark_preview(self) -> None:
        try:
            payload = self._read_json()
            config = _config_from_payload(payload)
            report = audit_benchmark_adapter_config(config.execution, base_dir=ROOT, paper_grade=config.paper_grade)
            self._send_json({"report": asdict(report), "markdown": render_benchmark_adapter_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_benchmark_manifest_lint(self) -> None:
        try:
            payload = self._read_json()
            report = _lint_benchmark_manifest_payload(payload, _paper_grade_config_from_payload(payload))
            self._send_json({"report": report, "markdown": _render_benchmark_manifest_lint_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_benchmark_manifest_save(self) -> None:
        try:
            payload = self._read_json()
            report = _lint_benchmark_manifest_payload(payload, _paper_grade_config_from_payload(payload))
            if report["status"] == "blocked":
                self._send_json({"error": "manifest lint blocked save", "report": report, "markdown": _render_benchmark_manifest_lint_markdown(report)}, HTTPStatus.BAD_REQUEST)
                return
            path_value = str(payload.get("path") or "").strip()
            destination = _benchmark_manifest_save_path(path_value)
            if destination is None:
                self._send_json({"error": "path must be benchmarks/**/manifest.json"}, HTTPStatus.BAD_REQUEST)
                return
            write_json(destination, report["manifest"])
            relative = str(destination.relative_to(ROOT))
            saved_report = {**report, "path": relative}
            self._send_json({"path": relative, "report": saved_report, "markdown": _render_benchmark_manifest_lint_markdown(saved_report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_release_metadata_lint(self) -> None:
        try:
            payload = self._read_json()
            config = _config_from_payload(payload)
            report = build_gold_release_metadata_lint(config)
            self._send_json({"report": report, "markdown": render_gold_release_metadata_lint_markdown(report)})
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_open_source_compliance_backfill(self) -> None:
        try:
            payload = self._read_json()
            report = backfill_open_source_compliance(
                RUNS_DIR,
                dry_run=bool(payload.get("dry_run", False)),
                force=bool(payload.get("force", False)),
                limit=_safe_positive_int(payload.get("limit")),
            )
            status = HTTPStatus.BAD_REQUEST if report.get("errors") else HTTPStatus.OK
            self._send_json({"report": report, "markdown": render_open_source_compliance_backfill_markdown(report)}, status)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_llm_observability_backfill(self) -> None:
        try:
            payload = self._read_json()
            report = backfill_llm_observability(
                RUNS_DIR,
                dry_run=bool(payload.get("dry_run", False)),
                force=bool(payload.get("force", False)),
                limit=_safe_positive_int(payload.get("limit")),
            )
            status = HTTPStatus.BAD_REQUEST if report.get("errors") else HTTPStatus.OK
            public_report = _public_llm_observability_backfill_report(report)
            self._send_json(
                {
                    "report": public_report,
                    "markdown": render_llm_observability_backfill_markdown(public_report),
                },
                status,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_repair_resume_backfill(self) -> None:
        try:
            payload = self._read_json()
            report = backfill_repair_resume_plans(
                RUNS_DIR,
                dry_run=bool(payload.get("dry_run", False)),
                force=bool(payload.get("force", False)),
                limit=_safe_positive_int(payload.get("limit")),
            )
            status = HTTPStatus.BAD_REQUEST if report.get("errors") else HTTPStatus.OK
            public_report = _public_repair_resume_backfill_report(report)
            self._send_json(
                {
                    "report": public_report,
                    "markdown": render_repair_resume_backfill_markdown(public_report),
                },
                status,
            )
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_run_create(self) -> None:
        try:
            payload = self._read_json()
            topic = str(payload.get("topic", "")).strip()
            if not topic:
                self._send_json({"error": "topic is required"}, HTTPStatus.BAD_REQUEST)
                return
            _reject_paper_grade_payload_secrets(AgentConfig(), payload)
            record = STORE.create(topic, _config_from_payload(payload))
            self._send_json(record, HTTPStatus.CREATED)
        except PreflightGateError as exc:
            self._send_json(_preflight_error_payload(exc.report), HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _handle_run_post(self, path: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 4 or parts[3] not in {"approve", "revision", "cancel", "resume", "repair-resume", "repair-resume-preview", "rollback-preview", "rollback-apply"}:
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            if parts[3] == "approve":
                result = STORE.approve_with_config(parts[2], reviewer="web", payload=payload)
            elif parts[3] == "revision":
                result = STORE.request_revision(parts[2], reviewer="web", notes=str(payload.get("review_notes") or payload.get("notes") or ""))
            elif parts[3] == "cancel":
                result = STORE.cancel(parts[2], requester="web", reason=str(payload.get("reason") or "user_requested"))
            elif parts[3] == "resume":
                result = STORE.resume_with_config(parts[2], payload=payload)
            elif parts[3] == "repair-resume":
                result = STORE.repair_resume_with_config(parts[2], payload=payload)
            elif parts[3] == "repair-resume-preview":
                result = STORE.preview_repair_resume(parts[2])
            elif parts[3] == "rollback-preview":
                result = STORE.preview_rollback(parts[2], str(payload.get("target") or payload.get("target_stage") or "").strip())
            else:
                result = STORE.rollback_with_config(parts[2], payload)
        except PreflightGateError as exc:
            self._send_json(_preflight_error_payload(exc.report), HTTPStatus.CONFLICT)
            return
        except FileNotFoundError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except (RuntimeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        if result is None:
            self._send_json({"error": "run not found"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json(result)

    def _validate_request(self, *, require_json: bool) -> bool:
        if not self._valid_host_header():
            self._send_json({"error": "invalid Host header"}, HTTPStatus.BAD_REQUEST)
            return False
        if not self._valid_origin_header():
            self._send_json({"error": "cross-origin request rejected"}, HTTPStatus.FORBIDDEN)
            return False
        if not self._valid_basic_authorization():
            self._send_json(
                {"error": "authentication required"},
                HTTPStatus.UNAUTHORIZED,
                extra_headers={"WWW-Authenticate": 'Basic realm="research-agent", charset="UTF-8"'},
            )
            return False
        if not require_json:
            return True
        transfer_encoding = str(self.headers.get("Transfer-Encoding") or "").strip()
        if transfer_encoding:
            self.close_connection = True
            self._send_json({"error": "Transfer-Encoding is not supported"}, HTTPStatus.BAD_REQUEST)
            return False
        content_type = str(self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_json({"error": "Content-Type must be application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return False
        try:
            content_length = self._content_length()
        except ValueError as exc:
            self.close_connection = True
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return False
        if content_length > self._max_body_bytes():
            self.close_connection = True
            self._send_json({"error": "request body is too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return False
        return True

    def _valid_host_header(self) -> bool:
        values = self.headers.get_all("Host") or []
        if len(values) != 1:
            return False
        authority = _web_authority(values[0])
        if authority is None:
            return False
        host, port = authority
        server_port = int(getattr(self.server, "server_port", self.server.server_address[1]))
        if (port if port is not None else 80) != server_port:
            return False
        allowed = getattr(self.server, "research_agent_allowed_hosts", None)
        if not isinstance(allowed, set):
            bind_host = str(getattr(self.server, "research_agent_bind_host", self.server.server_address[0]))
            allowed = _allowed_web_hosts(bind_host)
        return host in allowed

    def _valid_origin_header(self) -> bool:
        fetch_site = str(self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if fetch_site == "cross-site":
            return False
        values = self.headers.get_all("Origin") or []
        if not values:
            return True
        if len(values) != 1:
            return False
        origin = values[0].strip()
        try:
            parsed = urlparse(origin)
            origin_port = parsed.port
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None or parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            return False
        host_values = self.headers.get_all("Host") or []
        request_authority = _web_authority(host_values[0]) if len(host_values) == 1 else None
        if request_authority is None:
            return False
        request_host, request_port = request_authority
        effective_request_port = request_port if request_port is not None else 80
        effective_origin_port = origin_port if origin_port is not None else (443 if parsed.scheme == "https" else 80)
        return _normalize_web_host(parsed.hostname) == request_host and effective_origin_port == effective_request_port

    def _valid_basic_authorization(self) -> bool:
        token = getattr(self.server, "research_agent_web_token", None)
        if token is None:
            token = os.environ.get(WEB_TOKEN_ENV, "")
        if not token:
            return True
        values = self.headers.get_all("Authorization") or []
        if len(values) != 1:
            return False
        try:
            scheme, encoded = values[0].split(None, 1)
            supplied = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return False
        expected = f"{WEB_AUTH_USERNAME}:{token}".encode("utf-8")
        return scheme.lower() == "basic" and hmac.compare_digest(supplied, expected)

    def _content_length(self) -> int:
        values = self.headers.get_all("Content-Length") or []
        if not values:
            return 0
        if len(values) != 1:
            raise ValueError("invalid Content-Length")
        try:
            length = int(values[0])
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0:
            raise ValueError("invalid Content-Length")
        return length

    def _max_body_bytes(self) -> int:
        configured = getattr(self.server, "research_agent_max_body_bytes", None)
        return configured if isinstance(configured, int) and configured > 0 else _web_max_body_bytes()

    def _max_response_bytes(self) -> int:
        configured = getattr(self.server, "research_agent_max_response_bytes", None)
        return configured if isinstance(configured, int) and configured > 0 else _web_max_response_bytes()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_run_get(self, path: str, query: str) -> None:
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) < 3:
            self._send_json({"error": "run id missing"}, HTTPStatus.BAD_REQUEST)
            return
        run_id = parts[2]
        if len(parts) == 3:
            record = STORE.get(run_id)
            if record is None:
                self._send_json({"error": "run not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(record)
            return
        if len(parts) == 4 and parts[3] == "artifact":
            filename = parse_qs(query).get("file", [""])[0]
            out_dir = STORE.out_dir(run_id)
            public_artifact = _public_artifact_response(out_dir, filename) if out_dir is not None else None
            if _is_public_summary_artifact(filename):
                if public_artifact is None:
                    self._send_json({"error": "artifact not found"}, HTTPStatus.NOT_FOUND)
                    return
                body, _content_type = public_artifact
                self._send_bytes(
                    body,
                    _artifact_content_type(filename),
                    extra_headers=_artifact_response_headers(filename),
                )
                return
            artifact = STORE.artifact_path(run_id, filename)
            if artifact is None:
                self._send_json({"error": "artifact not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_bytes(
                artifact.read_bytes(),
                _artifact_content_type(filename),
                extra_headers=_artifact_response_headers(filename),
            )
            return
        if len(parts) == 4 and parts[3] == "rollback-options":
            options = STORE.rollback_options(run_id)
            if options is None:
                self._send_json({"error": "run not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(options)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _serve_static(self, path: str) -> None:
        filename = "index.html" if path in {"", "/"} else path.lstrip("/")
        static_path = (WEB_DIR / filename).resolve()
        if not _is_safe_existing_path(static_path, WEB_DIR):
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        self._send_bytes(static_path.read_bytes(), content_type)

    def _read_json(self) -> dict[str, Any]:
        length = self._content_length()
        if length > self._max_body_bytes():
            raise ValueError("request body is too large")
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_json(
        self,
        payload: Any,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(body, "application/json", status, extra_headers=extra_headers)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        is_api = urlparse(self.path).path.startswith("/api/")
        response_headers = dict(extra_headers or {})
        content_security_policy = response_headers.pop("Content-Security-Policy", WEB_CONTENT_SECURITY_POLICY)
        if is_api and len(body) > self._max_response_bytes():
            body = json.dumps({"error": "response body is too large"}).encode("utf-8")
            content_type = "application/json"
            status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", content_security_policy)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if is_api:
            self.send_header("Cache-Control", "no-store")
        for name, value in response_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def _artifact_content_type(filename: str) -> str:
    return ARTIFACT_CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _artifact_response_headers(filename: str) -> dict[str, str]:
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name) or "artifact"
    disposition = "inline" if Path(filename).suffix.lower() == ".svg" else "attachment"
    return {
        "Content-Security-Policy": ARTIFACT_CONTENT_SECURITY_POLICY,
        "Content-Disposition": f'{disposition}; filename="{safe_filename}"',
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def _public_config(config: AgentConfig) -> dict[str, Any]:
    data = asdict(config)
    llm = data.get("llm", {})
    if llm.get("api_key"):
        llm["api_key"] = "***"
    literature = data.get("literature", {})
    if isinstance(literature, dict):
        for key in ["semantic_scholar_api_key", "openalex_api_key", "contact_email"]:
            if literature.get(key):
                literature[key] = "***"
    return data


def _public_approval_record(approval: dict[str, Any]) -> dict[str, Any]:
    policy = approval.get("approval_policy") if isinstance(approval.get("approval_policy"), dict) else {}
    return {
        "approved": approval.get("approved") is True,
        "revision_requested": approval.get("revision_requested") is True,
        "requested_at": approval.get("requested_at"),
        "approved_at": approval.get("approved_at"),
        "revision_requested_at": approval.get("revision_requested_at"),
        "reviewer": approval.get("reviewer", ""),
        "stage": approval.get("stage", ""),
        "gate_status": approval.get("gate_status", ""),
        "notes": approval.get("notes", ""),
        "has_notes": bool(str(approval.get("notes") or "").strip()),
        "warning_count": _count_list(approval.get("warnings")),
        "required_action_count": _count_list(approval.get("required_actions")),
        "blocks": _list_from_payload(approval.get("blocks", [])),
        "history_count": _count_list(approval.get("history")),
        "approval_policy": {
            "notes_required": policy.get("notes_required") is True,
            "gate_status": policy.get("gate_status", approval.get("gate_status", "")),
            "warning_count": _count_from_payload(policy.get("warning_count")) or _count_list(approval.get("warnings")),
        },
    }


def _public_execution_approval_record(approval: dict[str, Any]) -> dict[str, Any]:
    policy = approval.get("approval_policy") if isinstance(approval.get("approval_policy"), dict) else {}
    return {
        "approved": approval.get("approved") is True,
        "approved_at": approval.get("approved_at"),
        "reviewer": approval.get("reviewer", ""),
        "stage": approval.get("stage", ""),
        "execution_mode": approval.get("execution_mode", ""),
        "notes": approval.get("notes", ""),
        "has_notes": bool(str(approval.get("notes") or "").strip()),
        "plan_hash": approval.get("plan_hash", ""),
        "safety_hash": approval.get("safety_hash", ""),
        "blocks": _list_from_payload(approval.get("blocks", [])),
        "history_count": _count_list(approval.get("history")),
        "approval_policy": {
            "notes_required": policy.get("notes_required") is True,
            "reason_count": 1 if str(policy.get("reason") or "").strip() else 0,
        },
    }


def _literature_preview_report(topic: str, config: LiteratureConfig) -> dict[str, Any]:
    topic = topic.strip()
    strategy = build_literature_search_strategy(
        topic,
        config,
        seed_queries=[],
        extra_queries=config.extra_search_queries,
        llm_queries=[],
    )
    strategy_data = asdict(strategy)
    secrets = _literature_preview_secrets(config)
    diagnostics: list[str] = []
    source_health: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocking_issues: list[str] = []

    if not topic:
        blocking_issues.append("topic is required")
    if config.provider not in {"online", "auto"}:
        blocking_issues.append("literature_provider must be online or auto for live preview")
        diagnostics.append("当前文献模式未执行在线检索；请切换为 online 或 auto 后再预览候选论文。")

    if not blocking_issues:
        client = OnlineLiteratureClient(config)
        try:
            found, diagnostics = client.search(topic, strategy.selected_queries)
        except Exception as exc:
            found = []
            diagnostics = [f"文献预览检索失败：{exc}"]
        source_health = [_public_literature_source_health(item, secrets) for item in client.source_health]
        papers = [_public_literature_paper(item, secrets) for item in annotate_evidence(found, topic)]

    warnings.extend(str(item) for item in strategy.warnings)
    warnings.extend(_literature_preview_health_warnings(source_health))
    if not papers and not blocking_issues:
        blocking_issues.append("online preview returned no candidate papers")
    status = "blocked" if blocking_issues else "needs_review" if warnings or strategy.status != "pass" else "ready"
    recommended_seed_items = _literature_preview_seed_items(papers)
    recommended_seed_entries = [str(item.get("entry") or "") for item in recommended_seed_items if str(item.get("entry") or "").strip()]
    seed_role_coverage = _literature_preview_seed_role_coverage(recommended_seed_items)
    return {
        "status": status,
        "topic": _sanitize_public_text(topic, secrets),
        "provider": config.provider,
        "sources": [source.strip().lower() for source in config.sources if source.strip()],
        "max_papers": config.max_papers,
        "max_search_queries": config.max_search_queries,
        "selected_queries": [_sanitize_public_text(query, secrets) for query in strategy.selected_queries],
        "search_strategy": _public_literature_strategy(strategy_data, secrets),
        "source_health": source_health,
        "papers": papers,
        "recommended_seed_entries": recommended_seed_entries,
        "recommended_seed_items": recommended_seed_items,
        "seed_role_coverage": seed_role_coverage,
        "diagnostics": [_sanitize_public_text(item, secrets) for item in diagnostics],
        "warnings": _unique_strings([_sanitize_public_text(item, secrets) for item in warnings]),
        "blocking_issues": _unique_strings([_sanitize_public_text(item, secrets) for item in blocking_issues]),
        "manual_tasks": _literature_preview_manual_tasks(status, papers, source_health),
        "read_only": True,
    }


def _public_paper_grade_probe_report(report: dict[str, Any], config: AgentConfig) -> dict[str, Any]:
    secrets = _literature_preview_secrets(config.literature)
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    source_summary = report.get("source_summary") if isinstance(report.get("source_summary"), dict) else {}
    seed_summary = report.get("seed_summary") if isinstance(report.get("seed_summary"), dict) else {}
    return {
        "schema_version": report.get("schema_version", 1),
        "topic": _sanitize_public_text(report.get("topic", ""), secrets),
        "status": str(report.get("status") or ""),
        "queries": [_sanitize_public_text(item, secrets) for item in _list_from_payload(report.get("queries"))],
        "checks": [_public_paper_grade_probe_check(item, secrets) for item in checks if isinstance(item, dict)],
        "source_summary": {
            "provider": _sanitize_public_text(source_summary.get("provider", ""), secrets),
            "configured_sources": _count_from_payload(source_summary.get("configured_sources")),
            "probed_sources": _count_from_payload(source_summary.get("probed_sources")),
            "successful_sources": _count_from_payload(source_summary.get("successful_sources")),
            "rate_limited_sources": _count_from_payload(source_summary.get("rate_limited_sources")),
            "failed_sources": _count_from_payload(source_summary.get("failed_sources")),
            "returned": _count_from_payload(source_summary.get("returned")),
        },
        "seed_summary": _sanitize_public_payload(seed_summary, secrets),
        "candidate_count": _count_from_payload(report.get("candidate_count")),
        "candidate_titles": [_sanitize_public_text(item, secrets) for item in _list_from_payload(report.get("candidate_titles"))[:8]],
        "source_health": _sanitize_public_payload(report.get("source_health") if isinstance(report.get("source_health"), list) else [], secrets),
        "diagnostics": [_sanitize_public_text(item, secrets) for item in _list_from_payload(report.get("diagnostics"))[:40]],
        "read_only": True,
    }


def build_gold_launch_bundle_report(
    topic: str,
    config: AgentConfig,
    *,
    benchmark_pack_run_dir: Path | None,
    fulltext_grounding_run_dir: Path | None,
    candidate_run_dir: Path | None,
    payload: dict[str, Any] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    env_report = build_gold_environment_lint(config)
    server_environment = _gold_bundle_server_environment_summary(
        _gold_env_kit_server_environment(
            [
                config.llm.base_url_env,
                config.llm.model_env,
                config.llm.api_key_env,
                config.literature.contact_email_env,
            ],
            [
                config.literature.semantic_scholar_api_key_env,
                config.literature.openalex_api_key_env,
            ],
            base_url_env=config.llm.base_url_env,
            fallback_base_url=str(config.llm.base_url or "").strip() or "http://127.0.0.1:8317",
            contact_email_env=config.literature.contact_email_env,
        )
    )
    paper_probe = _public_paper_grade_probe_report(
        build_paper_grade_online_probe(topic, config, client_factory=OnlineLiteratureClient),
        config,
    )
    benchmark_report = _public_gold_bundle_benchmark_report(audit_benchmark_adapter_config(config.execution, base_dir=base_dir or ROOT, paper_grade=config.paper_grade))
    release_report = build_gold_release_metadata_lint(config)
    doctor = build_gold_run_doctor(
        topic=topic,
        config=config,
        benchmark_pack_run_dir=benchmark_pack_run_dir,
        fulltext_grounding_run_dir=fulltext_grounding_run_dir,
        candidate_run_dir=candidate_run_dir,
        ping_llm=False,
    )
    public_doctor = _public_gold_run_doctor_report(doctor)
    launch = doctor.get("launch_manifest") if isinstance(doctor.get("launch_manifest"), dict) else {}
    public_launch = _public_gold_launch_manifest_report(launch) if launch else {}
    ignored = [name for name in ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"] if str(payload.get(name) or "").strip()]
    components = [
        _gold_bundle_component(
            "gold_env",
            "pass" if env_report.get("status") == "ready" else "block",
            "Gold Env",
            f"required_ready={env_report.get('required_ready') is True}; "
            f"server_env={server_environment.get('required_present') or 0}/{server_environment.get('required_total') or 0}; "
            f"gateway={(server_environment.get('gateway_socket') if isinstance(server_environment.get('gateway_socket'), dict) else {}).get('status') or '-'}; "
            f"missing={len(_list_from_payload(env_report.get('missing_required_fields')))}; invalid={len(_list_from_payload(env_report.get('invalid_required_fields')))}",
            "Set required server environment variables, then rerun Gold Env.",
        ),
        _gold_bundle_paper_probe_component(paper_probe, config),
        _gold_bundle_component(
            "benchmark_preview",
            "pass" if benchmark_report.get("status") == "ready" and benchmark_report.get("paper_grade_status") == "ready" else "block",
            "校验 Benchmark",
            f"status={benchmark_report.get('status') or '-'}; paper_grade={benchmark_report.get('paper_grade_status') or '-'}; ready_adapters={benchmark_report.get('ready_adapters') or 0}; roles={','.join(_list_from_payload(benchmark_report.get('roles'))) or '-'}",
            "Run Benchmark Preview and fix candidate/baseline/ablation manifest provenance, metrics, grader, and repeat issues.",
        ),
        _gold_bundle_component(
            "release_metadata",
            "pass" if release_report.get("status") == "ready" else "block",
            "校验 Release",
            f"status={release_report.get('status') or '-'}; blocking_fields={len(_list_from_payload(release_report.get('blocking_fields')))}",
            "Fill real release metadata and rerun Release lint.",
        ),
        _gold_bundle_component(
            "gold_doctor",
            _gold_bundle_doctor_status(public_doctor, public_launch),
            "Gold Doctor",
            f"status={public_doctor.get('status') or '-'}; launch={public_launch.get('status') or '-'}; can_start={public_launch.get('can_start_gold_run') is True}",
            "Run Gold Doctor after Env, literature, benchmark, and release checks are clean.",
        ),
    ]
    status = _gold_bundle_status(components)
    launch_plan = _gold_bundle_launch_plan(status, doctor, env_report)
    repair_plan = _gold_bundle_repair_plan(components)
    prelaunch_focus = _gold_bundle_prelaunch_focus(components)
    return {
        "schema_version": 1,
        "topic": _sanitize_public_text(topic, _literature_preview_secrets(config.literature)),
        "status": status,
        "can_start_gold_run": status == "ready_to_start" and public_launch.get("can_start_gold_run") is True,
        "components": components,
        "component_status_counts": _status_counts(components),
        "prelaunch_focus": prelaunch_focus,
        "next_steps": _gold_bundle_next_steps(components),
        "repair_plan": repair_plan,
        "repair_plan_items": len(repair_plan),
        "launch_plan": launch_plan,
        "ignored_payload_secret_fields": ignored,
        "read_only": True,
        "reports": {
            "gold_env": {
                "status": env_report.get("status"),
                "required_ready": env_report.get("required_ready") is True,
                "missing_required_fields": _list_from_payload(env_report.get("missing_required_fields")),
                "invalid_required_fields": _list_from_payload(env_report.get("invalid_required_fields")),
                "expected_mismatch_fields": _list_from_payload(env_report.get("expected_mismatch_fields")),
                "missing_optional_fields": _list_from_payload(env_report.get("missing_optional_fields")),
                "target_environment": _sanitize_public_payload(env_report.get("target_environment") if isinstance(env_report.get("target_environment"), dict) else {}, []),
                "server_environment": _public_gold_server_environment(server_environment),
            },
            "paper_grade_probe": paper_probe,
            "benchmark_preview": benchmark_report,
            "release_metadata": {
                "status": release_report.get("status"),
                "required_ready": release_report.get("required_ready") is True,
                "blocking_fields": _list_from_payload(release_report.get("blocking_fields")),
                "recommended_fields": _list_from_payload(release_report.get("recommended_fields")),
            },
            "gold_doctor": public_doctor,
            "launch_manifest": public_launch,
        },
    }


def _gold_bundle_server_environment_summary(server_environment: dict[str, Any]) -> dict[str, Any]:
    gateway = server_environment.get("gateway_socket") if isinstance(server_environment.get("gateway_socket"), dict) else {}
    return {
        "status": str(server_environment.get("status") or ""),
        "required_present": _count_from_payload(server_environment.get("required_present")),
        "required_total": _count_from_payload(server_environment.get("required_total")),
        "missing_required": _list_from_payload(server_environment.get("missing_required")),
        "invalid_required": _list_from_payload(server_environment.get("invalid_required")),
        "optional_present": _count_from_payload(server_environment.get("optional_present")),
        "optional_total": _count_from_payload(server_environment.get("optional_total")),
        "gateway_socket": {
            "status": str(gateway.get("status") or ""),
            "target": str(gateway.get("target") or ""),
        },
        "safe_to_render": True,
    }


def _gold_bundle_paper_probe_component(paper_probe: dict[str, Any], config: AgentConfig) -> dict[str, Any]:
    source_summary = paper_probe.get("source_summary") if isinstance(paper_probe.get("source_summary"), dict) else {}
    seed_summary = paper_probe.get("seed_summary") if isinstance(paper_probe.get("seed_summary"), dict) else {}
    provider = str(source_summary.get("provider") or "").strip()
    configured_sources = _count_from_payload(source_summary.get("configured_sources"))
    successful_sources = _count_from_payload(source_summary.get("successful_sources"))
    strong_seeds = _count_from_payload(seed_summary.get("strong_seed_papers"))
    resolved_seeds = _count_from_payload(seed_summary.get("metadata_resolved_seed_papers"))
    candidates = _count_from_payload(paper_probe.get("candidate_count"))
    min_configured_sources = max(1, int(config.paper_grade.min_literature_sources or 0))
    min_successful_sources = max(1, int(config.paper_grade.min_successful_literature_sources or 0))
    min_strong_seeds = max(1, int(config.paper_grade.min_seed_papers or 0))
    min_resolved_seeds = max(1, int(config.paper_grade.min_doi_url_seed_papers or 0))
    ready = (
        paper_probe.get("status") == "pass"
        and provider in {"online", "auto"}
        and configured_sources >= min_configured_sources
        and successful_sources >= min_successful_sources
        and strong_seeds >= min_strong_seeds
        and resolved_seeds >= min_resolved_seeds
        and candidates > 0
    )
    return _gold_bundle_component(
        "paper_grade_literature_probe",
        "pass" if ready else "block",
        "Gold 文献 Probe",
        (
            f"status={paper_probe.get('status') or '-'}; provider={provider or '-'}; "
            f"configured_sources={configured_sources}/{min_configured_sources}; "
            f"successful_sources={successful_sources}/{min_successful_sources}; "
            f"doi_url_seeds={resolved_seeds}/{min_resolved_seeds}; strong_seeds={strong_seeds}/{min_strong_seeds}; "
            f"candidates={candidates}"
        ),
        "Run Gold 文献 Probe with online/auto literature, enough configured/successful sources, and DOI/URL seeds resolving to metadata.",
    )


def render_gold_launch_bundle_markdown(report: dict[str, Any]) -> str:
    focus = report.get("prelaunch_focus") if isinstance(report.get("prelaunch_focus"), dict) else {}
    reports = report.get("reports") if isinstance(report.get("reports"), dict) else {}
    gold_env = reports.get("gold_env") if isinstance(reports.get("gold_env"), dict) else {}
    server_env = gold_env.get("server_environment") if isinstance(gold_env.get("server_environment"), dict) else {}
    gateway = server_env.get("gateway_socket") if isinstance(server_env.get("gateway_socket"), dict) else {}
    lines = [
        "# Gold Launch Bundle",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 可启动 gold run：{'是' if report.get('can_start_gold_run') else '否'}",
        f"- 只读：{'是' if report.get('read_only') else '否'}",
        f"- 忽略的 payload secret 字段：{', '.join(_list_from_payload(report.get('ignored_payload_secret_fields'))) or '-'}",
    ]
    if focus:
        lines.extend(
            [
                f"- 主要阻断：{focus.get('category') or '-'}",
                f"- 仅差服务端环境：{'是' if focus.get('ready_except_server_environment') else '否'}",
                f"- 环境刷新要求：{'是' if focus.get('server_environment_refresh_required') else '否'}",
            ]
        )
        if server_env:
            lines.extend(
                [
                    f"- 服务端环境：`{server_env.get('status') or '-'}`；必填 {server_env.get('required_present') or 0}/{server_env.get('required_total') or 0}",
                    f"- Gateway socket：`{gateway.get('status') or '-'}`；target=`{gateway.get('target') or '-'}`",
                ]
            )
        next_action = str(focus.get("next_action") or "").strip()
        if next_action:
            lines.append(f"- 聚焦下一步：{next_action}")
    lines.extend(
        [
            "",
            "## Components",
            "| Component | Status | Button | Evidence | Next step |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.get("components", []) if isinstance(report.get("components"), list) else []:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(item.get("item", "")),
                        _md_cell(item.get("status", "")),
                        _md_cell(item.get("button", "")),
                        _md_cell(item.get("evidence", "")),
                        _md_cell(item.get("next_step", "")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Next Steps"])
    steps = _list_from_payload(report.get("next_steps"))
    lines.extend(f"- {item}" for item in steps) if steps else lines.append("- 无")
    repairs = [item for item in (report.get("repair_plan") if isinstance(report.get("repair_plan"), list) else []) if isinstance(item, dict)]
    if repairs:
        lines.extend(
            [
                "",
                "## Repair Plan",
                "| Priority | Component | Status | Button | Fields | CLI hint | Next step |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in repairs:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(item.get("priority", "")),
                        _md_cell(item.get("component", "")),
                        _md_cell(item.get("status", "")),
                        _md_cell(item.get("button", "")),
                        _md_cell(", ".join(_list_from_payload(item.get("form_fields"))) or "-"),
                        _md_cell(item.get("cli_hint", "")),
                        _md_cell(item.get("next_step", "")),
                    ]
                )
                + " |"
            )
    launch_plan = report.get("launch_plan") if isinstance(report.get("launch_plan"), dict) else {}
    if launch_plan:
        lines.extend(
            [
                "",
                "## Safe Launch Plan",
                f"- 状态：{launch_plan.get('status') or '-'}",
                f"- 可执行命令：{'是' if launch_plan.get('ready_to_execute_commands') else '否'}",
                f"- Secret policy：`{launch_plan.get('secret_policy') or '-'}`",
                f"- 必需环境：{', '.join(_list_from_payload(launch_plan.get('required_environment'))) or '-'}",
                f"- 目标环境：`{(launch_plan.get('target_environment') or {}).get('status') if isinstance(launch_plan.get('target_environment'), dict) else '-'}`",
                f"- 人工 gate：{', '.join(_list_from_payload(launch_plan.get('required_human_gates'))) or '-'}",
                f"- 最终证据：{', '.join(_list_from_payload(launch_plan.get('required_final_evidence'))) or '-'}",
            ]
        )
        commands = _list_from_payload(launch_plan.get("safe_commands"))
        if commands:
            lines.extend(["", "```bash", *commands, "```"])
    lines.append("")
    lines.append("该 bundle 只读；不会创建 run、批准 gate、执行 benchmark、写入 secret 或启动 LLM 论文生成。")
    return "\n".join(lines)


def _write_gold_launch_bundle_artifacts(out_dir: Path, report: dict[str, Any]) -> None:
    write_json(out_dir / GOLD_LAUNCH_BUNDLE_JSON, report)
    write_text(out_dir / GOLD_LAUNCH_BUNDLE_MD, render_gold_launch_bundle_markdown(report))


def _write_gold_verification_followups(out_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    verification_json = out_dir / GOLD_RUN_VERIFICATION_JSON
    repair_plan = None
    if report.get("status") == "blocked" and verification_json.exists():
        repair_plan = write_repair_resume_plan_artifacts(
            out_dir,
            apply=False,
            gold_verification_report_path=verification_json,
        )
    readiness_written = False
    if _is_relative_to(out_dir.resolve(), RUNS_DIR.resolve()):
        write_perfect_agent_readiness_artifacts(ROOT, RUNS_DIR, ROOT, limit=0)
        readiness_written = True
    return {
        "verification_written": verification_json.exists(),
        "repair_resume_plan_written": repair_plan is not None,
        "perfect_readiness_written": readiness_written,
    }


def _write_gold_verification_if_gold_launch(out_dir: Path) -> None:
    if (out_dir / GOLD_LAUNCH_BUNDLE_JSON).exists():
        report = write_gold_run_verification_artifacts(out_dir)
        _write_gold_verification_followups(out_dir, report)


def _public_gold_bundle_benchmark_report(report: Any) -> dict[str, Any]:
    data = asdict(report) if hasattr(report, "__dataclass_fields__") else {}
    adapters = [item for item in data.get("adapters", []) if isinstance(item, dict)] if isinstance(data.get("adapters"), list) else []
    ready = [item for item in adapters if str(item.get("status") or "") == "ready"]
    roles = _unique_strings([str(item.get("role") or "") for item in ready if str(item.get("role") or "")])
    return {
        "status": str(data.get("status") or ""),
        "mode": str(data.get("mode") or ""),
        "manifest_paths": _count_from_payload(data.get("manifest_paths")),
        "adapters": len(adapters),
        "ready_adapters": len(ready),
        "roles": roles,
        "blocking_issues": _list_from_payload(data.get("blocking_issues"))[:12],
        "manual_tasks": _count_from_payload(data.get("manual_tasks")),
        "paper_grade_status": str(data.get("paper_grade_status") or ""),
        "paper_grade_issues": _list_from_payload(data.get("paper_grade_issues"))[:12],
    }


def _gold_bundle_component(item: str, status: str, button: str, evidence: str, next_step: str) -> dict[str, Any]:
    public_status = status if status in {"pass", "review", "block"} else "block"
    return {
        "item": item,
        "status": public_status,
        "button": button,
        "form_fields": _gold_bundle_form_fields(item),
        "evidence": evidence,
        "next_step": next_step,
    }


def _gold_bundle_doctor_status(public_doctor: dict[str, Any], public_launch: dict[str, Any]) -> str:
    if public_launch.get("can_start_gold_run") is True:
        return "pass"
    if public_doctor.get("status") == "warn" or public_launch.get("status") == "needs_review":
        return "review"
    return "block"


def _gold_bundle_status(components: list[dict[str, Any]]) -> str:
    statuses = [str(item.get("status") or "") for item in components]
    if "block" in statuses:
        return "blocked"
    if "review" in statuses:
        return "needs_review"
    return "ready_to_start"


def _gold_bundle_next_steps(components: list[dict[str, Any]]) -> list[str]:
    steps: list[str] = []
    for item in components:
        if str(item.get("status") or "") == "pass":
            continue
        parts = [f"{item.get('item') or '-'}={item.get('status') or '-'}"]
        if item.get("button"):
            parts.append(f"button={item.get('button')}")
        if item.get("next_step"):
            parts.append(str(item.get("next_step")))
        steps.append("; ".join(parts))
    return steps[:12]


def _gold_bundle_repair_plan(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    for priority, item in enumerate(components, start=1):
        status = str(item.get("status") or "")
        if status == "pass":
            continue
        component = str(item.get("item") or "").strip()
        if not component:
            continue
        repairs.append(
            {
                "id": f"{component}_repair",
                "component": component,
                "status": status if status in {"review", "block"} else "block",
                "priority": priority,
                "button": str(item.get("button") or ""),
                "form_fields": _list_from_payload(item.get("form_fields"))[:12],
                "next_step": str(item.get("next_step") or ""),
                "cli_hint": _gold_bundle_cli_hint(component),
                "evidence": str(item.get("evidence") or ""),
            }
        )
    return repairs[:12]


def _gold_bundle_prelaunch_focus(components: list[dict[str, Any]]) -> dict[str, Any]:
    blocking = [item for item in components if str(item.get("status") or "") != "pass"]
    blocking_components = [str(item.get("item") or "").strip() for item in blocking if str(item.get("item") or "").strip()]
    blocking_without_doctor = [item for item in blocking_components if item != "gold_doctor"]
    fields = _unique_strings(
        str(field)
        for item in blocking
        for field in _list_from_payload(item.get("form_fields"))
        if re.fullmatch(r"[A-Za-z0-9_]+", str(field or ""))
    )[:12]
    ready_except_environment = bool(blocking_components) and set(blocking_without_doctor).issubset({"gold_env"}) and "gold_env" in blocking_without_doctor
    if not blocking_components:
        category = "ready"
        next_action = "Gold launch checks are ready; use Gold Launch to start the strict paper-grade run."
    elif ready_except_environment:
        category = "server_environment"
        next_action = "Set the required server-side environment fields, restart or refresh the serving process, then rerun Gold Bundle."
    elif "paper_grade_literature_probe" in blocking_components:
        category = "literature"
        next_action = "Fix online/auto literature sources, DOI/URL seed metadata, and candidate retrieval before launch."
    elif "benchmark_preview" in blocking_components:
        category = "benchmark_manifest"
        next_action = "Fix candidate/baseline/ablation benchmark manifests and rerun Benchmark Preview."
    elif "release_metadata" in blocking_components:
        category = "release_metadata"
        next_action = "Fill real release metadata and rerun Release lint."
    else:
        category = "doctor_or_final_evidence"
        next_action = "Rerun Gold Doctor after upstream checks are clean and inspect remaining launch checklist items."
    return {
        "category": category,
        "blocking_components": blocking_components[:12],
        "ready_except_server_environment": ready_except_environment,
        "server_environment_refresh_required": ready_except_environment,
        "form_fields": fields,
        "next_action": next_action,
    }


def _gold_bundle_form_fields(item: str) -> list[str]:
    return {
        "gold_env": [
            "llm_base_url",
            "llm_model",
            "llm_api_key",
            "literature_contact_email",
        ],
        "paper_grade_literature_probe": [
            "literature_provider",
            "literature_sources",
            "seed_papers",
            "fulltext_paths",
            "max_papers",
            "max_search_queries",
            "extra_search_queries",
        ],
        "benchmark_preview": [
            "execution_mode",
            "execution_repeats",
            "benchmark_manifests",
            "allowed_commands",
            "timeout_seconds",
        ],
        "release_metadata": [
            "release_code_repository_url",
            "release_code_archive_doi",
            "release_code_license",
            "release_code_version",
            "release_data_access_statement",
            "release_environment_url",
        ],
        "gold_doctor": [
            "benchmark_pack_run_id",
            "fulltext_grounding_run_id",
            "candidate_run_id",
        ],
    }.get(item, [])


def _gold_bundle_cli_hint(item: str) -> str:
    return {
        "gold_env": "Configure server environment, then rerun gold-launch-bundle --no-write.",
        "paper_grade_literature_probe": "research_agent paper-grade-probe --literature-provider online --literature-sources openalex,arxiv,crossref --seed-paper <doi-or-url> --no-write",
        "benchmark_preview": "research_agent benchmark-manifest-build ...; research_agent gold-launch-bundle --benchmark-manifest <candidate> --benchmark-manifest <baseline> --benchmark-manifest <ablation> --no-write",
        "release_metadata": "research_agent gold-launch-bundle --release-code-repository-url <url> --release-code-archive-doi <doi> --release-code-license <license> --no-write",
        "gold_doctor": "research_agent gold-run-doctor --paper-grade --no-write",
    }.get(item, "Rerun gold-launch-bundle --no-write after fixing this component.")


def _gold_bundle_launch_plan(status: str, doctor: dict[str, Any], env_report: dict[str, Any] | None = None) -> dict[str, Any]:
    commands = _live_gold_launch_commands(doctor)
    launch = doctor.get("launch_manifest") if isinstance(doctor.get("launch_manifest"), dict) else {}
    target_environment = {}
    if isinstance(env_report, dict) and isinstance(env_report.get("target_environment"), dict):
        target_environment = _sanitize_public_payload(env_report["target_environment"], [])
    return {
        "status": "ready" if status == "ready_to_start" else "blocked",
        "ready_to_execute_commands": status == "ready_to_start",
        "secret_policy": "env_only",
        "required_environment": [
            "llm_base_url",
            "llm_model",
            "llm_api_key",
            "literature_contact_email",
        ],
        "optional_environment": [
            "semantic_scholar_api_key",
            "openalex_api_key",
        ],
        "required_human_gates": _list_from_payload(launch.get("required_human_gates"))[:8],
        "required_final_evidence": _list_from_payload(launch.get("required_final_evidence"))[:12],
        "target_environment": target_environment,
        "safe_commands": commands,
        "command_count": len(commands),
    }


def _nested_int(data: dict[str, Any], section: str, key: str) -> int:
    nested = data.get(section) if isinstance(data.get(section), dict) else {}
    return _count_from_payload(nested.get(key))


def _public_paper_grade_probe_check(item: dict[str, Any], secrets: list[str]) -> dict[str, str]:
    return {
        "name": _sanitize_public_text(item.get("name", ""), secrets),
        "status": _sanitize_public_text(item.get("status", ""), secrets),
        "detail": _sanitize_public_text(item.get("detail", ""), secrets),
        "action": _sanitize_public_text(item.get("action", ""), secrets),
    }


def _sanitize_public_payload(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        return _sanitize_public_text(value, secrets)
    if isinstance(value, list):
        return [_sanitize_public_payload(item, secrets) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_public_payload(item, secrets) for key, item in value.items()}
    return value


def _public_literature_strategy(data: dict[str, Any], secrets: list[str]) -> dict[str, Any]:
    candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
    return {
        "status": data.get("status", ""),
        "quality_score": data.get("quality_score", 0.0),
        "selected_queries": [_sanitize_public_text(item, secrets) for item in data.get("selected_queries", [])] if isinstance(data.get("selected_queries"), list) else [],
        "selected_intents": [_sanitize_public_text(item, secrets) for item in _list_from_payload(data.get("selected_intents", []))],
        "missing_required_intents": [_sanitize_public_text(item, secrets) for item in _list_from_payload(data.get("missing_required_intents", []))],
        "weak_selected_queries": [_sanitize_public_text(item, secrets) for item in _list_from_payload(data.get("weak_selected_queries", []))],
        "warnings": [_sanitize_public_text(item, secrets) for item in _list_from_payload(data.get("warnings", []))],
        "recommendations": [_sanitize_public_text(item, secrets) for item in _list_from_payload(data.get("recommendations", []))],
        "candidates": [
            {
                "query": _sanitize_public_text(item.get("query", ""), secrets),
                "origin": _sanitize_public_text(item.get("origin", ""), secrets),
                "intent": _sanitize_public_text(item.get("intent", ""), secrets),
                "priority": int(item.get("priority") or 0),
                "selected": item.get("selected") is True,
                "risk": _sanitize_public_text(item.get("risk", ""), secrets),
                "rationale": _sanitize_public_text(item.get("rationale", ""), secrets),
            }
            for item in candidates
            if isinstance(item, dict)
        ],
    }


def _public_literature_paper(paper: Any, secrets: list[str]) -> dict[str, Any]:
    return {
        "title": _sanitize_public_text(getattr(paper, "title", ""), secrets),
        "authors": [_sanitize_public_text(item, secrets) for item in list(getattr(paper, "authors", []) or [])[:8]],
        "year": int(getattr(paper, "year", 0) or 0),
        "venue": _sanitize_public_text(getattr(paper, "venue", ""), secrets),
        "url": _sanitize_public_text(getattr(paper, "url", ""), secrets),
        "doi": _sanitize_public_text(getattr(paper, "doi", ""), secrets),
        "sources": [_sanitize_public_text(item, secrets) for item in list(getattr(paper, "sources", []) or [getattr(paper, "source", "")]) if str(item).strip()],
        "relevance": round(float(getattr(paper, "relevance", 0.0) or 0.0), 4),
        "citation_count": getattr(paper, "citation_count", None),
        "evidence_note": _sanitize_public_text(getattr(paper, "evidence_note", ""), secrets),
    }


def _public_literature_source_health(item: dict[str, Any], secrets: list[str]) -> dict[str, Any]:
    query_results = item.get("query_results") if isinstance(item.get("query_results"), list) else []
    return {
        "source": _sanitize_public_text(item.get("source", ""), secrets),
        "status": _sanitize_public_text(item.get("status", ""), secrets),
        "queries": _count_from_payload(item.get("queries")),
        "returned": _count_from_payload(item.get("returned")),
        "errors": _count_from_payload(item.get("errors")),
        "rate_limited": item.get("rate_limited") is True,
        "elapsed_seconds": float(item.get("elapsed_seconds") or 0.0),
        "cache_hits": _count_from_payload(item.get("cache_hits")),
        "cache_misses": _count_from_payload(item.get("cache_misses")),
        "cache_writes": _count_from_payload(item.get("cache_writes")),
        "stale_cache_uses": _count_from_payload(item.get("stale_cache_uses")),
        "query_results": [
            {
                "source": _sanitize_public_text(entry.get("source", ""), secrets),
                "query": _sanitize_public_text(entry.get("query", ""), secrets),
                "status": _sanitize_public_text(entry.get("status", ""), secrets),
                "returned": _count_from_payload(entry.get("returned")),
                "error": _sanitize_public_text(entry.get("error", ""), secrets),
                "rate_limited": entry.get("rate_limited") is True,
                "elapsed_seconds": float(entry.get("elapsed_seconds") or 0.0),
            }
            for entry in query_results
            if isinstance(entry, dict)
        ],
    }


def _literature_preview_health_warnings(source_health: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for item in source_health:
        source = str(item.get("source") or "unknown")
        status = str(item.get("status") or "")
        if status in {"failed", "partial", "rate_limited", "skipped"}:
            warnings.append(f"{source}: source status {status}")
        if int(item.get("returned") or 0) == 0:
            warnings.append(f"{source}: returned zero papers")
    return warnings


def _literature_preview_manual_tasks(status: str, papers: list[dict[str, Any]], source_health: list[dict[str, Any]]) -> list[str]:
    tasks = [
        "人工核对前 5 篇候选论文的题名、年份、来源和 DOI/URL。",
        "把确认高相关的 DOI/URL 写入人工种子文献，再启动正式研究。",
        "预览只读；它不会创建 run、批准 review gate 或进入 idea/实验。",
    ]
    if status == "blocked":
        tasks.insert(0, "先修复阻断问题，再重新预览文献。")
    if len(papers) < 3:
        tasks.append("候选论文少于 3 篇；补充更具体的检索式或增加在线来源。")
    if any(item.get("rate_limited") for item in source_health):
        tasks.append("存在限流来源；配置对应 API key 或暂时移除该来源。")
    return _unique_strings(tasks)


def _literature_preview_seed_items(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for role in _literature_preview_seed_role_names():
        candidate = next((paper for paper in papers if role in _literature_preview_paper_roles(paper) and _literature_preview_seed_entry(paper)), None)
        if candidate is None:
            continue
        entry = _literature_preview_seed_entry(candidate)
        if not entry or any(str(item.get("entry") or "").lower() == entry.lower() for item in items):
            continue
        roles = _literature_preview_paper_roles(candidate)
        items.append(_literature_preview_seed_item(candidate, entry, roles, role))

    for paper in papers:
        if len(items) >= 5:
            break
        entry = _literature_preview_seed_entry(paper)
        if not entry or any(str(item.get("entry") or "").lower() == entry.lower() for item in items):
            continue
        roles = _literature_preview_paper_roles(paper)
        items.append(_literature_preview_seed_item(paper, entry, roles, "supplemental"))
    return items[:5]


def _literature_preview_seed_entry(paper: dict[str, Any]) -> str:
    doi = str(paper.get("doi") or "").strip()
    url = str(paper.get("url") or "").strip()
    identifier = doi or url
    if not identifier:
        return ""
    title = str(paper.get("title") or "").strip()
    year = int(paper.get("year") or 0)
    suffix = f" {title}" if title else ""
    if year:
        suffix += f" ({year})"
    return f"{identifier}{suffix}".strip()


def _literature_preview_seed_item(paper: dict[str, Any], entry: str, roles: list[str], primary_role: str) -> dict[str, Any]:
    return {
        "entry": entry,
        "title": str(paper.get("title") or ""),
        "year": int(paper.get("year") or 0),
        "doi": str(paper.get("doi") or ""),
        "url": str(paper.get("url") or ""),
        "relevance": float(paper.get("relevance") or 0.0),
        "roles": roles,
        "primary_role": primary_role,
    }


def _literature_preview_seed_role_coverage(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {role: 0 for role in _literature_preview_seed_role_names()}
    for item in items:
        for role in item.get("roles", []) if isinstance(item.get("roles"), list) else []:
            if role in counts:
                counts[role] += 1
    covered = [role for role, count in counts.items() if count > 0]
    missing = [role for role, count in counts.items() if count <= 0]
    status = "pass" if len(covered) >= 3 else "review_required" if items else "empty"
    return {
        "status": status,
        "role_counts": counts,
        "covered_roles": covered,
        "missing_roles": missing,
    }


def _literature_preview_paper_roles(paper: dict[str, Any]) -> list[str]:
    text = " ".join(str(paper.get(key) or "") for key in ["title", "venue", "evidence_note"]).lower()
    year = int(paper.get("year") or 0)
    roles: list[str] = []
    if any(term in text for term in ["survey", "review", "systematic", "tutorial", "overview", "state of the art", "taxonomy", "meta-analysis", "综述"]):
        roles.append("review")
    if any(term in text for term in ["benchmark", "dataset", "evaluation", "protocol", "corpus", "suite", "leaderboard", "challenge", "experiment", "ompl", "moveit", "基准", "数据集", "评测"]):
        roles.append("benchmark_dataset")
    if any(term in text for term in ["baseline", "method", "algorithm", "planner", "planning", "approach", "framework", "model", "rrt", "rrt*", "prm", "chomp", "stomp", "trajopt", "sampling-based", "sampling based", "trajectory optimization", "sequential convex optimization", "方法", "算法", "规划"]):
        roles.append("baseline_method")
    if year >= _current_year() - 5:
        roles.append("recent")
    return _unique_strings(roles)


def _literature_preview_seed_role_names() -> list[str]:
    return ["review", "benchmark_dataset", "baseline_method", "recent"]


def _current_year() -> int:
    from datetime import datetime

    return datetime.now().year


def _render_literature_preview_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 文献预览",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- Topic：{report.get('topic') or '-'}",
        f"- 文献模式：{report.get('provider') or '-'}",
        f"- 来源：{', '.join(str(item) for item in report.get('sources', [])) or '-'}",
        f"- 候选论文：{len(report.get('papers', []) if isinstance(report.get('papers'), list) else [])}",
        "- 边界：只读预览，不创建 run、不批准 review gate、不进入 idea/实验、不调用 LLM。",
        "",
        "## 已选检索式",
    ]
    selected_queries = report.get("selected_queries") if isinstance(report.get("selected_queries"), list) else []
    lines.extend(f"{index}. `{query}`" for index, query in enumerate(selected_queries, start=1)) if selected_queries else lines.append("- 无")

    strategy = report.get("search_strategy") if isinstance(report.get("search_strategy"), dict) else {}
    lines.extend(
        [
            "",
            "## 检索策略",
            f"- 策略状态：{strategy.get('status') or '-'}",
            f"- 质量分：{float(strategy.get('quality_score') or 0.0):.3f}",
            f"- 已覆盖意图：{', '.join(str(item) for item in strategy.get('selected_intents', [])) or '-'}",
            f"- 缺失意图：{', '.join(str(item) for item in strategy.get('missing_required_intents', [])) or '-'}",
        ]
    )

    lines.extend(["", "## 文献源状态", "| Source | Status | Queries | Returned | Errors | Cache |", "| --- | --- | ---: | ---: | ---: | --- |"])
    source_health = report.get("source_health") if isinstance(report.get("source_health"), list) else []
    if source_health:
        for item in source_health:
            if not isinstance(item, dict):
                continue
            cache = f"hit {item.get('cache_hits', 0)} / miss {item.get('cache_misses', 0)} / stale {item.get('stale_cache_uses', 0)}"
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(item.get("source", "")),
                        _md_cell(item.get("status", "")),
                        str(item.get("queries", 0)),
                        str(item.get("returned", 0)),
                        str(item.get("errors", 0)),
                        _md_cell(cache),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | not_run | 0 | 0 | 0 | - |")

    lines.extend(["", "## 候选论文", "| # | Title | Year | Venue | Sources | DOI/URL | Relevance | Citations | Note |", "| ---: | --- | ---: | --- | --- | --- | ---: | ---: | --- |"])
    papers = report.get("papers") if isinstance(report.get("papers"), list) else []
    if papers:
        for index, paper in enumerate(papers, start=1):
            if not isinstance(paper, dict):
                continue
            link = paper.get("doi") or paper.get("url") or "-"
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(index),
                        _md_cell(paper.get("title", "")),
                        str(paper.get("year") or 0),
                        _md_cell(paper.get("venue", "")),
                        _md_cell(", ".join(str(item) for item in paper.get("sources", []))),
                        _md_cell(link),
                        f"{float(paper.get('relevance') or 0.0):.3f}",
                        str(paper.get("citation_count") if paper.get("citation_count") is not None else "-"),
                        _md_cell(paper.get("evidence_note", "")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | 无候选 | 0 | - | - | - | 0.000 | - | - |")

    lines.extend(["", "## 推荐人工 Seed"])
    seed_entries = report.get("recommended_seed_entries") if isinstance(report.get("recommended_seed_entries"), list) else []
    seed_role = report.get("seed_role_coverage") if isinstance(report.get("seed_role_coverage"), dict) else {}
    if seed_role:
        counts = seed_role.get("role_counts") if isinstance(seed_role.get("role_counts"), dict) else {}
        count_text = ", ".join(f"{role}={int(counts.get(role) or 0)}" for role in _literature_preview_seed_role_names())
        lines.append(f"- 角色覆盖：{seed_role.get('status') or '-'}；{count_text}")
        missing = seed_role.get("missing_roles") if isinstance(seed_role.get("missing_roles"), list) else []
        lines.append("- 缺失角色：" + (", ".join(str(item) for item in missing) if missing else "无"))
    if seed_entries:
        items = report.get("recommended_seed_items") if isinstance(report.get("recommended_seed_items"), list) else []
        for entry in seed_entries:
            match = next((item for item in items if isinstance(item, dict) and item.get("entry") == entry), {})
            roles = ", ".join(str(role) for role in match.get("roles", []) if str(role).strip()) if isinstance(match.get("roles"), list) else ""
            suffix = f" ({roles})" if roles else ""
            lines.append(f"- `{entry}`{suffix}")
    else:
        lines.append("- 无 DOI/URL 候选；不要自动回填标题-only 文献。")

    for heading, key in [("阻断问题", "blocking_issues"), ("警告", "warnings"), ("诊断", "diagnostics"), ("人工待办", "manual_tasks")]:
        lines.extend(["", f"## {heading}"])
        items = report.get(key) if isinstance(report.get(key), list) else []
        lines.extend(f"- {item}" for item in items) if items else lines.append("- 无")
    return "\n".join(lines)


def _literature_preview_secrets(config: LiteratureConfig) -> list[str]:
    values = [
        config.semantic_scholar_api_key,
        config.openalex_api_key,
        config.contact_email,
        os.environ.get(config.semantic_scholar_api_key_env, ""),
        os.environ.get(config.openalex_api_key_env, ""),
        os.environ.get(config.contact_email_env, ""),
    ]
    return [value for value in _unique_strings([str(item).strip() for item in values]) if len(value) >= 4]


def _sanitize_public_text(value: Any, secrets: list[str]) -> str:
    text = str(value or "")
    for secret in secrets:
        text = text.replace(secret, "***")
    text = re.sub(r"(?i)(api[_-]?key=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(mailto=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(email=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(x-api-key['\"]?\s*[:=]\s*)[^,\s}]+", r"\1***", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", text)
    return text


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _benchmark_examples() -> list[dict[str, Any]]:
    examples_root = ROOT / "examples"
    if not examples_root.exists():
        return []
    records: list[dict[str, Any]] = []
    for manifest in sorted(examples_root.glob("**/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            relative = str(manifest.relative_to(ROOT))
        except ValueError:
            continue
        command = data.get("command") if isinstance(data.get("command"), list) else []
        records.append(
            {
                "name": str(data.get("name") or manifest.parent.name),
                "path": relative,
                "command": [str(item) for item in command],
                "metrics_path": str(data.get("metrics_path") or ""),
                "expected_artifacts": [str(item) for item in data.get("expected_artifacts", [])] if isinstance(data.get("expected_artifacts"), list) else [],
                "benchmark_url": str(data.get("benchmark_url") or ""),
                "dataset_url": str(data.get("dataset_url") or ""),
                "dataset_version": str(data.get("dataset_version") or ""),
                "split_name": str(data.get("split_name") or ""),
                "split_path": str(data.get("split_path") or ""),
                "split_sha256": str(data.get("split_sha256") or ""),
                "license": str(data.get("license") or ""),
                "baseline": str(data.get("baseline") or ""),
                "baseline_version": str(data.get("baseline_version") or ""),
                "citation": str(data.get("citation") or ""),
                "expected_metrics": [str(item) for item in data.get("expected_metrics", [])] if isinstance(data.get("expected_metrics"), list) else [],
                "metric_schema": data.get("metric_schema") if isinstance(data.get("metric_schema"), dict) else {},
                "grader": str(data.get("grader") or ""),
                "grader_path": str(data.get("grader_path") or ""),
                "grader_version": str(data.get("grader_version") or ""),
                "grader_sha256": str(data.get("grader_sha256") or ""),
                "submission_path": str(data.get("submission_path") or ""),
                "seed_policy": str(data.get("seed_policy") or ""),
                "min_repeats": int(data.get("min_repeats") or 0),
                "benchmark_kind": str(data.get("benchmark_kind") or ""),
                "notes": [str(item) for item in data.get("notes", [])] if isinstance(data.get("notes"), list) else [],
            }
        )
    return records


def _gold_defaults() -> dict[str, Any]:
    config = _gold_default_config()
    benchmark_pack = _gold_default_benchmark_pack()
    support_runs = _gold_default_support_runs()
    release_overrides = _gold_env_kit_release_overrides()
    manual_todos = [
        "Gold Defaults 已回填 UCI Iris DOI/URL seed papers、全文路径和额外检索式；运行 Literature Preview 后仍需人工核对题名、年份、DOI/URL 和相关性。",
        "人工核对自动回填的 release metadata，确认仓库、归档 URL、许可证、版本、数据和环境 URL 与正式提交一致。",
        "启动前依次运行 Env LLM、Preflight、Benchmark Preview 和 Gold Doctor；blocked 时不要启动正式 run。",
    ]
    if not benchmark_pack.get("paths"):
        manual_todos.insert(2, "准备非 examples 的公开外部 candidate/baseline/ablation benchmark manifest。")
    if support_runs.get("status") != "ready":
        manual_todos.insert(3, "先运行 standalone benchmark-pack-run 和 fulltext-grounding-run，并回填对应 run 目录。")
    return {
        "schema_version": 1,
        "paper_grade_enabled": True,
        "literature": {
            "provider": config.literature.provider or "online",
            "sources": config.literature.sources,
            "max_papers": config.literature.max_papers,
            "max_search_queries": config.literature.max_search_queries,
            "seed_papers": config.literature.seed_papers,
            "fulltext_paths": config.literature.fulltext_paths,
            "extra_search_queries": config.literature.extra_search_queries,
            "min_seed_papers": config.paper_grade.min_seed_papers,
            "min_doi_url_seed_papers": config.paper_grade.min_doi_url_seed_papers,
            "required_seed_roles": ["review/survey", "benchmark/dataset", "baseline/method", "recent work"],
            "optional_sources": ["semantic_scholar"],
        },
        "execution": {
            "mode": "benchmark",
            "repeats": 5,
            "timeout_seconds": 900,
            "allowed_commands": ["python3"],
            "benchmark_manifest_paths": benchmark_pack.get("paths", []),
            "benchmark_pack": benchmark_pack,
        },
        "support_runs": support_runs,
        "release": {
            "required_fields": [
                "release_code_repository_url",
                "release_code_archive_doi",
                "release_code_license",
                "release_code_version",
                "release_data_access_statement",
                "release_environment_url",
            ],
            "recommended_fields": ["release_data_repository_url", "release_data_archive_doi", "release_notes"],
            "config_fields": {
                "code_repository_url": release_overrides["release_code_repository_url"],
                "code_archive_doi": release_overrides["release_code_archive_doi"],
                "code_license": release_overrides["release_code_license"],
                "code_version": release_overrides["release_code_version"],
                "data_repository_url": "https://archive.ics.uci.edu/dataset/53/iris",
                "data_archive_doi": "10.24432/C56C76",
                "data_access_statement": release_overrides["release_data_access_statement"],
                "environment_url": release_overrides["release_environment_url"],
                "release_notes": release_overrides["release_notes"],
            },
        },
        "manual_todos": manual_todos,
    }


def _gold_default_support_runs() -> dict[str, Any]:
    benchmark_pack_run = ROOT / "runs" / "uci-iris-expanded-baseline-pack-run"
    fulltext_grounding_run = ROOT / "runs" / "uci-iris-fulltext-grounding"
    benchmark_ready = (benchmark_pack_run / "04-benchmark-evidence-audit.json").exists()
    fulltext_ready = (fulltext_grounding_run / "10-citation-grounding.json").exists()
    return {
        "status": "ready" if benchmark_ready and fulltext_ready else "missing",
        "benchmark_pack_run_dir": _safe_relative_path(benchmark_pack_run) if benchmark_ready else "",
        "fulltext_grounding_run_dir": _safe_relative_path(fulltext_grounding_run) if fulltext_ready else "",
    }


def _gold_default_config() -> AgentConfig:
    config_path = ROOT / "examples" / "uci-iris-paper-grade-config.toml"
    try:
        return load_config(config_path)
    except OSError:
        return AgentConfig()


def build_gold_defaults_smoke_report(topic: str = GOLD_DEFAULT_SMOKE_TOPIC, *, base_dir: Path | None = None) -> dict[str, Any]:
    defaults = _gold_defaults()
    support = defaults.get("support_runs") if isinstance(defaults.get("support_runs"), dict) else {}
    config = _gold_default_config_with_release()
    bundle = build_gold_launch_bundle_report(
        topic or GOLD_DEFAULT_SMOKE_TOPIC,
        config,
        benchmark_pack_run_dir=_gold_default_support_run_path(support, "benchmark_pack_run_dir"),
        fulltext_grounding_run_dir=_gold_default_support_run_path(support, "fulltext_grounding_run_dir"),
        candidate_run_dir=None,
        base_dir=base_dir or ROOT,
    )
    components = [item for item in (bundle.get("components") if isinstance(bundle.get("components"), list) else []) if isinstance(item, dict)]
    component_status = {str(item.get("item") or ""): str(item.get("status") or "") for item in components}
    input_components = ["paper_grade_literature_probe", "benchmark_preview", "release_metadata"]
    input_ready = all(component_status.get(item) == "pass" for item in input_components) and support.get("status") == "ready"
    focus = bundle.get("prelaunch_focus") if isinstance(bundle.get("prelaunch_focus"), dict) else {}
    ready_except_environment = bool(input_ready and focus.get("ready_except_server_environment") is True)
    if bundle.get("status") == "ready_to_start" and bundle.get("can_start_gold_run") is True:
        status = "ready_to_start"
    elif ready_except_environment:
        status = "ready_except_server_environment"
    else:
        status = "blocked"
    literature = defaults.get("literature") if isinstance(defaults.get("literature"), dict) else {}
    execution = defaults.get("execution") if isinstance(defaults.get("execution"), dict) else {}
    launch_kit = build_gold_env_launch_kit(config)
    bundle_public = _public_gold_launch_bundle_report(bundle)
    bundle_reports = bundle.get("reports") if isinstance(bundle.get("reports"), dict) else {}
    bundle_gold_env = bundle_reports.get("gold_env") if isinstance(bundle_reports.get("gold_env"), dict) else {}
    server_environment = _public_gold_server_environment(bundle_gold_env.get("server_environment") if isinstance(bundle_gold_env.get("server_environment"), dict) else {})
    gold_run_out_dir = "runs/iris-classification-benchmark-smoke-gold-run"
    gold_run_output = _gold_defaults_output_summary(gold_run_out_dir)
    gold_run_launch_dir = str(gold_run_output.get("launch_path") or gold_run_out_dir)
    post_launch_guidance = _gold_run_post_launch_guidance({"out_dir": gold_run_launch_dir})
    cli_launcher_command = _gold_defaults_cli_launcher_command(
        str(launch_kit.get("cli_launcher_command") or "scripts/run_gold_cli_env.sh"),
        out_dir=gold_run_launch_dir,
        default_out_dir=gold_run_out_dir,
    )
    cli_launcher_dry_run_command = _gold_defaults_cli_launcher_command(
        str(launch_kit.get("cli_launcher_dry_run_command") or "RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh"),
        out_dir=gold_run_launch_dir,
        default_out_dir=gold_run_out_dir,
    )
    return {
        "schema_version": 1,
        "topic": _sanitize_public_text(topic or GOLD_DEFAULT_SMOKE_TOPIC, []),
        "status": status,
        "read_only": True,
        "input_ready": input_ready,
        "ready_except_server_environment": ready_except_environment,
        "can_start_gold_run": bundle.get("can_start_gold_run") is True,
        "bundle_status": str(bundle.get("status") or ""),
        "component_status_counts": _status_counts(components),
        "components": components,
        "prelaunch_focus": bundle_public.get("prelaunch_focus") if isinstance(bundle_public.get("prelaunch_focus"), dict) else {},
        "server_environment": server_environment,
        "environment_setup_checklist": _public_gold_env_setup_checklist(launch_kit.get("environment_setup_checklist")),
        "gold_defaults": {
            "config_path": "examples/uci-iris-paper-grade-config.toml",
            "benchmark_pack_run_dir": str(support.get("benchmark_pack_run_dir") or ""),
            "fulltext_grounding_run_dir": str(support.get("fulltext_grounding_run_dir") or ""),
            "support_runs_status": str(support.get("status") or ""),
            "seed_papers": _count_list(literature.get("seed_papers")),
            "doi_url_seed_requirement": _count_from_payload(literature.get("min_doi_url_seed_papers")),
            "fulltext_paths": _count_list(literature.get("fulltext_paths")),
            "extra_search_queries": _count_list(literature.get("extra_search_queries")),
            "benchmark_manifest_paths": _list_from_payload(execution.get("benchmark_manifest_paths")),
            "release_overrides": sorted(_gold_env_kit_release_overrides()),
        },
        "gold_run_output": gold_run_output,
        "next_steps": _gold_defaults_smoke_next_steps(status, ready_except_environment, output_exists=gold_run_output.get("exists") is True),
        "safe_commands": {
            "env_launch_kit": str(launch_kit.get("helper_script_command") or "scripts/start_gold_web_env.sh"),
            "env_launch_kit_replace": "RESEARCH_AGENT_WEB_REPLACE=1 scripts/start_gold_web_env.sh",
            "cli_launcher_dry_run": cli_launcher_dry_run_command,
            "cli_launcher": cli_launcher_command,
            "bundle_check": _gold_env_kit_cli_command(["gold-launch-bundle", "--topic", topic or GOLD_DEFAULT_SMOKE_TOPIC, "--gold-defaults", "--no-write"]),
            "gold_launch": _gold_env_kit_cli_command(
                [
                    "gold-run-launch",
                    "--topic",
                    topic or GOLD_DEFAULT_SMOKE_TOPIC,
                    "--gold-defaults",
                    "--out",
                    gold_run_launch_dir,
                ]
            ),
        },
        "post_launch_gate_commands": _list_from_payload(post_launch_guidance.get("gate_commands")),
        "post_launch_verification_commands": _list_from_payload(post_launch_guidance.get("verification_commands")),
        "bundle_summary": bundle_public,
    }


def _gold_default_config_with_release() -> AgentConfig:
    config = _gold_default_config()
    release = config.release
    release_overrides = _gold_env_kit_release_overrides()
    field_map = {
        "release_code_repository_url": "code_repository_url",
        "release_code_archive_doi": "code_archive_doi",
        "release_code_license": "code_license",
        "release_code_version": "code_version",
        "release_data_access_statement": "data_access_statement",
        "release_environment_url": "environment_url",
        "release_notes": "release_notes",
    }
    updates = {field: value for key, field in field_map.items() if (value := release_overrides.get(key))}
    return replace(
        config,
        release=replace(release, **updates),
        paper_grade=replace(config.paper_grade, enabled=True),
    )


def _gold_default_support_run_path(support: dict[str, Any], field: str) -> Path | None:
    value = str(support.get(field) or "").strip()
    if not value:
        return None
    path = ROOT / value
    return path if path.exists() else None


def _gold_defaults_output_summary(gold_run_out_dir: str) -> dict[str, Any]:
    path = ROOT / gold_run_out_dir
    exists = path.exists()
    launch_path = _gold_defaults_fresh_output_path(gold_run_out_dir) if exists else gold_run_out_dir
    return {
        "path": gold_run_out_dir,
        "status": "exists" if exists else "available",
        "exists": exists,
        "launch_path": launch_path,
        "suggested_path": launch_path if exists else "",
        "safe_to_render": True,
        "next_action": "Choose a fresh --out directory or archive/remove the previous run before launch." if exists else "Default --out is available for a new gold run.",
    }


def _gold_defaults_fresh_output_path(gold_run_out_dir: str) -> str:
    path = Path(gold_run_out_dir)
    for suffix in range(2, 100):
        candidate = path.with_name(f"{path.name}-{suffix}")
        if not (ROOT / candidate).exists():
            return str(candidate)
    return str(path.with_name(f"{path.name}-fresh"))


def _gold_defaults_cli_launcher_command(command: str, *, out_dir: str, default_out_dir: str) -> str:
    if out_dir and out_dir != default_out_dir:
        return f"RESEARCH_AGENT_GOLD_OUT={shlex.quote(out_dir)} {command}"
    return command


def _gold_defaults_smoke_next_steps(status: str, ready_except_environment: bool, *, output_exists: bool = False) -> list[str]:
    output_step = "Default gold-run output exists; choose a fresh --out directory before launching." if output_exists else ""
    if status == "ready_to_start":
        steps = [
            "Gold Defaults smoke is fully ready; run gold-run-launch --gold-defaults or use Web Gold Launch.",
            "Keep API keys in environment variables only; do not paste them into the Web form.",
        ]
        return [*steps, output_step] if output_step else steps
    if ready_except_environment:
        steps = [
            "Run RESEARCH_AGENT_WEB_REPLACE=1 scripts/start_gold_web_env.sh in a local terminal and provide the API key/contact email interactively.",
            "After Web restarts from that environment, rerun Gold Defaults Smoke or Gold Bundle.",
            "When the bundle reports ready_to_start, use Gold Launch for the strict paper-grade run.",
        ]
        return [*steps, output_step] if output_step else steps
    return [
        "Run Gold Defaults, inspect the blocked components below, and fix the listed local inputs before launching.",
        "Do not use Gold Launch until Gold Bundle reports ready_to_start.",
        *([output_step] if output_step else []),
    ]


def _public_gold_server_environment(server_environment: dict[str, Any]) -> dict[str, Any]:
    result = dict(server_environment)
    result["missing_required"] = _unique_strings(_public_environment_name(item) for item in _list_from_payload(server_environment.get("missing_required")))
    result["invalid_required"] = _unique_strings(_public_environment_name(item) for item in _list_from_payload(server_environment.get("invalid_required")))
    return result


def render_gold_defaults_smoke_markdown(report: dict[str, Any]) -> str:
    defaults = report.get("gold_defaults") if isinstance(report.get("gold_defaults"), dict) else {}
    gold_run_output = report.get("gold_run_output") if isinstance(report.get("gold_run_output"), dict) else {}
    focus = report.get("prelaunch_focus") if isinstance(report.get("prelaunch_focus"), dict) else {}
    server_env = report.get("server_environment") if isinstance(report.get("server_environment"), dict) else {}
    gateway = server_env.get("gateway_socket") if isinstance(server_env.get("gateway_socket"), dict) else {}
    commands = report.get("safe_commands") if isinstance(report.get("safe_commands"), dict) else {}
    lines = [
        "# Gold Defaults Smoke",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 只读：{'是' if report.get('read_only') else '否'}",
        f"- 默认输入就绪：{'是' if report.get('input_ready') else '否'}",
        f"- 仅差服务端环境：{'是' if report.get('ready_except_server_environment') else '否'}",
        f"- Bundle 状态：{report.get('bundle_status') or '-'}",
        f"- 可启动 gold run：{'是' if report.get('can_start_gold_run') else '否'}",
        f"- 主要阻断：{focus.get('category') or '-'}",
        f"- 服务端环境：`{server_env.get('status') or '-'}`；必填 {server_env.get('required_present') or 0}/{server_env.get('required_total') or 0}",
        f"- 缺失必填环境：{_gold_env_missing_required_public_label(report, server_env)}",
        f"- Gateway socket：`{gateway.get('status') or '-'}`；target=`{gateway.get('target') or '-'}`",
        f"- Config：`{defaults.get('config_path') or '-'}`",
        f"- Support runs：benchmark=`{defaults.get('benchmark_pack_run_dir') or '-'}`；fulltext=`{defaults.get('fulltext_grounding_run_dir') or '-'}`",
        f"- Gold run output：`{gold_run_output.get('path') or '-'}`；status=`{gold_run_output.get('status') or '-'}`",
    ]
    launch_path = str(gold_run_output.get("launch_path") or "").strip()
    if launch_path and launch_path != str(gold_run_output.get("path") or "").strip():
        lines.append(f"- Suggested launch output：`{launch_path}`")
    lines.extend(_gold_env_setup_checklist_markdown_lines(report))
    lines.extend(
        [
            f"- Seed/fulltext/query：seeds={defaults.get('seed_papers') or 0}；fulltext={defaults.get('fulltext_paths') or 0}；queries={defaults.get('extra_search_queries') or 0}",
            f"- Benchmark manifests：{', '.join(_list_from_payload(defaults.get('benchmark_manifest_paths'))) or '-'}",
            "",
            "## Components",
            "| Component | Status | Evidence |",
            "| --- | --- | --- |",
        ]
    )
    for item in report.get("components", []) if isinstance(report.get("components"), list) else []:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(item.get("item", "")),
                        _md_cell(item.get("status", "")),
                        _md_cell(item.get("evidence", "")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Next Steps"])
    steps = _list_from_payload(report.get("next_steps"))
    lines.extend(f"- {item}" for item in steps) if steps else lines.append("- 无")
    if commands:
        lines.extend(
            [
                "",
                "## Commands",
                "```bash",
                str(commands.get("env_launch_kit_replace") or commands.get("env_launch_kit") or ""),
                str(commands.get("cli_launcher_dry_run") or ""),
                str(commands.get("cli_launcher") or ""),
                str(commands.get("bundle_check") or ""),
                str(commands.get("gold_launch") or ""),
                "```",
            ]
        )
    gate_commands = _list_from_payload(report.get("post_launch_gate_commands"))
    if gate_commands:
        lines.extend(["", "## Post-Launch Human Gates", "```bash", *gate_commands, "```"])
    verification_commands = _list_from_payload(report.get("post_launch_verification_commands"))
    if verification_commands:
        lines.extend(["", "## Final Verification", "```bash", *verification_commands, "```"])
    lines.append("")
    lines.append("该 smoke 只读；不会创建 run、批准 gate、执行 benchmark、调用 LLM 或保存 secret。")
    return "\n".join(lines)


def build_gold_env_launch_kit(config: AgentConfig, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    base_url = str(config.llm.base_url or "").strip() or "http://127.0.0.1:8317"
    model = str(config.llm.model or "").strip() or "gpt-5.5"
    ignored = _payload_secret_fields(payload)
    required_environment = [
        config.llm.base_url_env,
        config.llm.model_env,
        config.llm.api_key_env,
        config.literature.contact_email_env,
    ]
    optional_environment = [
        config.literature.semantic_scholar_api_key_env,
        config.literature.openalex_api_key_env,
    ]
    server_environment = _gold_env_kit_server_environment(
        required_environment,
        optional_environment,
        base_url_env=config.llm.base_url_env,
        fallback_base_url=base_url,
        contact_email_env=config.literature.contact_email_env,
    )
    environment_setup_checklist = _gold_env_setup_checklist(
        config,
        server_environment,
        base_url=base_url,
        model=model,
    )
    shell_steps = [
        f"export {config.llm.base_url_env}={shlex.quote(base_url)}",
        f"export {config.llm.model_env}={shlex.quote(model)}",
        f"export {config.literature.contact_email_env}='<your-real-contact-email>'",
        f"read -rsp '{config.llm.api_key_env}: ' {config.llm.api_key_env}; export {config.llm.api_key_env}; echo",
    ]
    release_overrides = _gold_env_kit_release_overrides()
    release_args = _gold_env_kit_release_args(release_overrides)
    gold_run_out_dir = "runs/iris-classification-benchmark-smoke-gold-run"
    gold_run_output = _gold_defaults_output_summary(gold_run_out_dir)
    gold_run_launch_dir = str(gold_run_output.get("launch_path") or gold_run_out_dir)
    post_launch_guidance = _gold_run_post_launch_guidance({"out_dir": gold_run_launch_dir})
    cli_launcher_command = _gold_defaults_cli_launcher_command(
        "scripts/run_gold_cli_env.sh",
        out_dir=gold_run_launch_dir,
        default_out_dir=gold_run_out_dir,
    )
    cli_launcher_dry_run_command = _gold_defaults_cli_launcher_command(
        "RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh",
        out_dir=gold_run_launch_dir,
        default_out_dir=gold_run_out_dir,
    )
    verification_steps = [
        _gold_env_kit_cli_command(
            [
                "gold-run-doctor",
                "--topic",
                "Iris classification benchmark smoke",
                "--config",
                "examples/uci-iris-paper-grade-config.toml",
                "--benchmark-pack-run-dir",
                "runs/uci-iris-expanded-baseline-pack-run",
                "--fulltext-grounding-run-dir",
                "runs/uci-iris-fulltext-grounding",
                "--paper-grade",
                "--ping-llm",
                *release_args,
                "--no-write",
            ]
        ),
        _gold_env_kit_cli_command(
            [
                "gold-launch-bundle",
                "--topic",
                "Iris classification benchmark smoke",
                "--config",
                "examples/uci-iris-paper-grade-config.toml",
                "--benchmark-pack-run-dir",
                "runs/uci-iris-expanded-baseline-pack-run",
                "--fulltext-grounding-run-dir",
                "runs/uci-iris-fulltext-grounding",
                "--paper-grade",
                *release_args,
                "--no-write",
            ]
        ),
    ]
    return {
        "schema_version": 1,
        "status": "ready",
        "read_only": True,
        "secret_policy": "env_only",
        "ignored_payload_secret_fields": ignored,
        "target": {
            "llm_base_url": base_url,
            "llm_model": model,
            "api_key": "<read-from-local-shell>",
            "literature_contact_email": "<your-real-contact-email>",
        },
        "required_environment": required_environment,
        "optional_environment": optional_environment,
        "environment_setup_checklist": environment_setup_checklist,
        "server_environment": server_environment,
        "helper_script": "scripts/start_gold_web_env.sh",
        "helper_script_command": "scripts/start_gold_web_env.sh",
        "cli_launcher_command": cli_launcher_command,
        "cli_launcher_dry_run_command": cli_launcher_dry_run_command,
        "gateway_precheck": "socket_before_secret",
        "gateway_precheck_skip_environment": "RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK=1",
        "startup_verification_policy": "post_key_doctor_ping_and_bundle_gate",
        "helper_script_post_key_checks": ["gold-run-doctor --ping-llm --no-write", "gold-launch-bundle --no-write"],
        "port_conflict_policy": "prompt_before_secret",
        "web_replace_environment": "RESEARCH_AGENT_WEB_REPLACE=1",
        "shell_steps": shell_steps,
        "web_restart_command": "scripts/start_gold_web_env.sh",
        "web_restart_fallback_command": "PYTHONPATH=src python3 -m research_agent.web_server --host 127.0.0.1 --port 8766",
        "release_overrides": release_overrides,
        "verification_steps": verification_steps,
        "gold_run_output": gold_run_output,
        "post_launch_gate_commands": _list_from_payload(post_launch_guidance.get("gate_commands")),
        "post_launch_verification_commands": _list_from_payload(post_launch_guidance.get("verification_commands")),
        "next_steps": [
            "Run scripts/start_gold_web_env.sh in a local terminal; it checks port conflicts and gold-defaults-smoke before reading the API key.",
            "After the hidden API key prompt, the helper script runs gold-run-doctor --ping-llm and gold-launch-bundle before starting Web.",
            "Both gold launcher scripts check the configured LLM gateway socket before reading the API key.",
            "If an old Web server is already on the target port, approve the prompt or set RESEARCH_AGENT_WEB_REPLACE=1.",
            "After the Web server restarts from that environment, rerun Gold Env and Gold Bundle.",
            "For a CLI-only launch path, run scripts/run_gold_cli_env.sh; set RESEARCH_AGENT_GOLD_DRY_RUN=1 to verify gates without starting a run.",
            "If Gold Bundle reports ready_to_start, use Gold Launch for the strict paper-grade run, then use status/approve/approve-execution from the post-launch gate commands as needed.",
        ],
    }


def _gold_env_setup_checklist(
    config: AgentConfig,
    server_environment: dict[str, Any],
    *,
    base_url: str,
    model: str,
) -> list[dict[str, Any]]:
    missing_required = set(_list_from_payload(server_environment.get("missing_required")))
    invalid_required = set(_list_from_payload(server_environment.get("invalid_required")))

    def required_item(field: str, env_name: str, *, secret: bool, safe_action: str) -> dict[str, Any]:
        status = "missing" if env_name in missing_required else "invalid" if env_name in invalid_required else "present"
        return {
            "field": field,
            "environment": env_name,
            "required": True,
            "secret": secret,
            "status": status,
            "safe_action": safe_action,
        }

    def optional_item(field: str, env_name: str, *, secret: bool, safe_action: str) -> dict[str, Any]:
        return {
            "field": field,
            "environment": env_name,
            "required": False,
            "secret": secret,
            "status": "present" if os.environ.get(env_name) else "missing",
            "safe_action": safe_action,
        }

    return [
        required_item(
            "llm_base_url",
            config.llm.base_url_env,
            secret=False,
            safe_action=f"export {config.llm.base_url_env}={shlex.quote(base_url)}",
        ),
        required_item(
            "llm_model",
            config.llm.model_env,
            secret=False,
            safe_action=f"export {config.llm.model_env}={shlex.quote(model)}",
        ),
        required_item(
            "literature_contact_email",
            config.literature.contact_email_env,
            secret=False,
            safe_action=f"export {config.literature.contact_email_env}='<your-real-contact-email>'",
        ),
        required_item(
            "llm_api_key",
            config.llm.api_key_env,
            secret=True,
            safe_action="Use scripts/start_gold_web_env.sh or scripts/run_gold_cli_env.sh; both read this value with a hidden prompt after gateway/contact checks.",
        ),
        optional_item(
            "semantic_scholar_api_key",
            config.literature.semantic_scholar_api_key_env,
            secret=True,
            safe_action=f"export {config.literature.semantic_scholar_api_key_env}='<optional-api-key>'",
        ),
        optional_item(
            "openalex_api_key",
            config.literature.openalex_api_key_env,
            secret=True,
            safe_action=f"export {config.literature.openalex_api_key_env}='<optional-api-key>'",
        ),
    ]


def _public_gold_env_setup_checklist(value: Any) -> list[dict[str, Any]]:
    checklist = [item for item in (value if isinstance(value, list) else []) if isinstance(item, dict)]
    public: list[dict[str, Any]] = []
    for item in checklist:
        field = str(item.get("field") or "").strip()
        secret = bool(item.get("secret"))
        if secret and field == "llm_api_key":
            safe_action = "Use scripts/start_gold_web_env.sh or scripts/run_gold_cli_env.sh; both read this value with a hidden prompt after gateway/contact checks."
        elif secret:
            safe_action = "Optional; export this provider key in your local shell only when needed."
        else:
            safe_action = str(item.get("safe_action") or "").strip()
        public.append(
            {
                "field": field,
                "environment": "<secret-env>" if secret else str(item.get("environment") or "").strip(),
                "required": bool(item.get("required")),
                "secret": secret,
                "status": str(item.get("status") or "").strip(),
                "safe_action": safe_action,
            }
        )
    return public


def _gold_env_kit_server_environment(
    required_environment: list[str],
    optional_environment: list[str],
    *,
    base_url_env: str,
    fallback_base_url: str,
    contact_email_env: str = "",
) -> dict[str, Any]:
    raw_required_present = [name for name in required_environment if os.environ.get(name)]
    invalid_required = [
        name
        for name in raw_required_present
        if contact_email_env and name == contact_email_env and not valid_contact_email(os.environ.get(name, ""))
    ]
    required_present = [name for name in raw_required_present if name not in invalid_required]
    required_missing = [name for name in required_environment if name not in raw_required_present]
    optional_present = [name for name in optional_environment if os.environ.get(name)]
    gateway = _gold_env_kit_gateway_socket_status(os.environ.get(base_url_env, "").strip() or fallback_base_url)
    ready = not required_missing and not invalid_required and gateway.get("status") == "reachable"
    return {
        "status": "ready" if ready else "needs_server_environment",
        "required_present": len(required_present),
        "required_total": len(required_environment),
        "missing_required": required_missing,
        "invalid_required": invalid_required,
        "optional_present": len(optional_present),
        "optional_total": len(optional_environment),
        "gateway_socket": gateway,
        "safe_to_render": True,
    }


def _gold_env_kit_gateway_socket_status(raw_base_url: str) -> dict[str, str]:
    parsed = urlparse(raw_base_url if "://" in raw_base_url else f"http://{raw_base_url}")
    host = parsed.hostname
    if not host:
        return {"status": "invalid", "target": "-"}
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = parsed.scheme or "http"
    target = f"{scheme}://{host}:{port}"
    try:
        with socket.create_connection((host, port), timeout=0.25):
            pass
    except OSError:
        return {"status": "unreachable", "target": target}
    return {"status": "reachable", "target": target}


def _gold_env_kit_release_overrides() -> dict[str, str]:
    return {
        "release_code_repository_url": "https://github.com/research-agent-lab/research-agent",
        "release_code_archive_doi": "https://github.com/research-agent-lab/research-agent/archive/refs/tags/v0.1.0.zip",
        "release_code_license": "MIT",
        "release_code_version": "v0.1.0",
        "release_data_access_statement": "The Iris data are available from the UCI Machine Learning Repository; frozen benchmark splits and manifests are included in this repository for reproducible evaluation.",
        "release_environment_url": "https://github.com/research-agent-lab/research-agent/blob/v0.1.0/Dockerfile",
        "release_notes": "Gold launch kit defaults for the UCI Iris benchmark path; verify repository, archive, and environment URLs before submission.",
    }


def _gold_env_kit_release_args(release_overrides: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key, value in release_overrides.items():
        args.extend(["--" + key.replace("_", "-"), value])
    return args


def _gold_env_kit_cli_command(args: list[str]) -> str:
    return "PYTHONPATH=src " + shlex.join(["python3", "-m", "research_agent", *args])


def _gold_env_kit_post_launch_gate_commands() -> list[str]:
    out_dir = "runs/iris-classification-benchmark-smoke-gold-run"
    return [
        _gold_env_kit_cli_command(["status", out_dir]),
        _gold_env_kit_cli_command(
            [
                "approve",
                out_dir,
                "--reviewer",
                "human",
                "--notes",
                "Literature gate inspected; DOI/URL seed coverage, source health, and claim boundaries accepted for this gold run.",
            ]
        ),
        _gold_env_kit_cli_command(
            [
                "approve-execution",
                out_dir,
                "--reviewer",
                "human",
                "--notes",
                "Benchmark manifests, allowed commands, frozen split, and grader hash inspected.",
            ]
        ),
    ]


def _gold_run_post_launch_guidance(record: dict[str, Any]) -> dict[str, Any]:
    run_dir = str(record.get("out_dir") or "").strip() or f"runs/{str(record.get('id') or '<run-id>').strip()}"
    gate_commands = [
        _gold_env_kit_cli_command(["status", run_dir]),
        _gold_env_kit_cli_command(
            [
                "approve",
                run_dir,
                "--reviewer",
                "human",
                "--notes",
                "Literature gate inspected; DOI/URL seed coverage, source health, and claim boundaries accepted for this gold run.",
            ]
        ),
        _gold_env_kit_cli_command(
            [
                "approve-execution",
                run_dir,
                "--reviewer",
                "human",
                "--notes",
                "Benchmark manifests, allowed commands, frozen split, and grader hash inspected.",
            ]
        ),
    ]
    verification_commands = [
        _gold_env_kit_cli_command(["gold-run-verify", "--run-dir", run_dir]),
        _gold_env_kit_cli_command(["perfect-readiness", "--project-dir", ".", "--runs-dir", "runs", "--no-write"]),
    ]
    return {
        "run_dir": run_dir,
        "gate_commands": gate_commands,
        "verification_commands": verification_commands,
        "commands": [*gate_commands, *verification_commands],
        "safe_to_render": True,
    }


def render_gold_env_launch_kit_markdown(report: dict[str, Any]) -> str:
    target = report.get("target") if isinstance(report.get("target"), dict) else {}
    release = report.get("release_overrides") if isinstance(report.get("release_overrides"), dict) else {}
    server_env = report.get("server_environment") if isinstance(report.get("server_environment"), dict) else {}
    gateway = server_env.get("gateway_socket") if isinstance(server_env.get("gateway_socket"), dict) else {}
    gold_run_output = report.get("gold_run_output") if isinstance(report.get("gold_run_output"), dict) else {}
    lines = [
        "# Gold Env Launch Kit",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 只读：{'是' if report.get('read_only') else '否'}",
        f"- Secret policy：`{report.get('secret_policy') or '-'}`",
        f"- 忽略的 payload secret 字段：{', '.join(_list_from_payload(report.get('ignored_payload_secret_fields'))) or '-'}",
        f"- 目标 Base URL：`{target.get('llm_base_url') or '-'}`",
        f"- 目标模型：`{target.get('llm_model') or '-'}`",
        f"- Helper script：`{report.get('helper_script') or '-'}`",
        f"- Gateway precheck：`{report.get('gateway_precheck') or '-'}`",
        f"- Startup verification：`{report.get('startup_verification_policy') or '-'}`",
        f"- Gateway skip env：`{report.get('gateway_precheck_skip_environment') or '-'}`",
        f"- Port conflict：`{report.get('port_conflict_policy') or '-'}`",
        f"- Replace env：`{report.get('web_replace_environment') or '-'}`",
        f"- 服务端环境：`{server_env.get('status') or '-'}`；必填 {server_env.get('required_present') or 0}/{server_env.get('required_total') or 0}",
        f"- 缺失必填环境：{', '.join(_list_from_payload(server_env.get('missing_required'))) or '-'}",
        f"- Gateway socket：`{gateway.get('status') or '-'}`；target=`{gateway.get('target') or '-'}`",
        f"- Release 覆盖：{', '.join(release) or '-'}",
        f"- Gold run output：`{gold_run_output.get('path') or '-'}`；status=`{gold_run_output.get('status') or '-'}`",
    ]
    launch_path = str(gold_run_output.get("launch_path") or "").strip()
    if launch_path and launch_path != str(gold_run_output.get("path") or "").strip():
        lines.append(f"- Suggested launch output：`{launch_path}`")
    lines.extend(_gold_env_setup_checklist_markdown_lines(report))
    lines.extend(
        [
        "",
        "## Local Shell Steps",
        "```bash",
        *_list_from_payload(report.get("shell_steps")),
        "```",
        "",
        "## Restart Web",
        "```bash",
        str(report.get("web_restart_command") or ""),
        "```",
        "",
        "Helper post-key checks:",
        "```text",
        *_list_from_payload(report.get("helper_script_post_key_checks")),
        "```",
        "",
        "Fallback command after exporting the environment manually:",
        "```bash",
        str(report.get("web_restart_fallback_command") or ""),
        "```",
        "",
        "## CLI Launcher",
        "```bash",
        str(report.get("cli_launcher_dry_run_command") or ""),
        str(report.get("cli_launcher_command") or ""),
        "```",
        "",
        "## Verify",
        "```bash",
        *_list_from_payload(report.get("verification_steps")),
        "```",
        "",
        "## Post-Launch Human Gates",
        "```bash",
        *_list_from_payload(report.get("post_launch_gate_commands")),
        "```",
        "",
        "## Final Verification",
        "```bash",
        *_list_from_payload(report.get("post_launch_verification_commands")),
        "```",
        "",
        "## Next Steps",
        ]
    )
    steps = _list_from_payload(report.get("next_steps"))
    lines.extend(f"- {item}" for item in steps) if steps else lines.append("- 无")
    lines.append("")
    lines.append("该启动包只包含占位符和交互式读取命令；不会返回、记录或保存任何真实 API key。")
    return "\n".join(lines)


def _gold_env_setup_checklist_markdown_lines(report: dict[str, Any]) -> list[str]:
    checklist = [item for item in (report.get("environment_setup_checklist") if isinstance(report.get("environment_setup_checklist"), list) else []) if isinstance(item, dict)]
    if not checklist:
        return []
    lines = [
        "",
        "## Environment Setup Checklist",
        "| Field | Env | Required | Status | Secret | Safe action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in checklist:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(item.get("field", "")),
                    _md_cell(item.get("environment", "")),
                    _md_cell("yes" if item.get("required") else "no"),
                    _md_cell(item.get("status", "")),
                    _md_cell("yes" if item.get("secret") else "no"),
                    _md_cell(item.get("safe_action", "")),
                ]
            )
            + " |"
        )
    return lines


def _gold_env_missing_required_public_label(report: dict[str, Any], server_env: dict[str, Any]) -> str:
    checklist = [item for item in (report.get("environment_setup_checklist") if isinstance(report.get("environment_setup_checklist"), list) else []) if isinstance(item, dict)]
    public_missing = [
        str(item.get("environment") or "").strip()
        for item in checklist
        if item.get("required") and str(item.get("status") or "") in {"missing", "invalid"} and str(item.get("environment") or "").strip()
    ]
    if public_missing:
        return ", ".join(_unique_strings(public_missing))
    missing = _list_from_payload(server_env.get("missing_required"))
    invalid = _list_from_payload(server_env.get("invalid_required"))
    return ", ".join(_unique_strings(_public_environment_name(item) for item in [*missing, *invalid])) or "-"


def _public_environment_name(value: Any) -> str:
    text = str(value or "").strip()
    if "API_KEY" in text or text.endswith("_KEY"):
        return "<secret-env>"
    return text


def _gold_default_benchmark_pack() -> dict[str, Any]:
    benchmarks_root = ROOT / "benchmarks"
    if not benchmarks_root.exists():
        return {"status": "missing", "paths": [], "roles": {}, "reason": "benchmarks directory not found"}
    groups: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(benchmarks_root.rglob("*.json")):
        if "manifest" not in path.name or path.name.endswith(".schema.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("command"), list):
            continue
        role = _gold_default_manifest_role(path, data)
        if role not in {"candidate", "baseline", "ablation"}:
            continue
        if _benchmark_manifest_paper_grade_issues(data):
            continue
        if not data.get("source_files") or not (str(data.get("grader") or "").strip() or str(data.get("grader_path") or "").strip()):
            continue
        group = _gold_default_manifest_group(path, role)
        groups.setdefault(group, []).append({"path": path, "role": role, "data": data})
    for group in sorted(groups):
        by_role: dict[str, dict[str, Any]] = {}
        for record in sorted(groups[group], key=lambda item: str(item["path"])):
            by_role.setdefault(str(record["role"]), record)
        if not {"candidate", "baseline", "ablation"}.issubset(by_role):
            continue
        selected = [by_role[role] for role in ["candidate", "baseline", "ablation"]]
        signatures = {_gold_default_command_signature(record["data"]) for record in selected}
        if len(signatures) < 3:
            continue
        return {
            "status": "ready",
            "group": _safe_relative_path(Path(group)),
            "paths": [_safe_relative_path(record["path"]) for record in selected],
            "roles": {str(record["role"]): _safe_relative_path(record["path"]) for record in selected},
            "dataset_url": str(selected[0]["data"].get("dataset_url") or ""),
            "benchmark_url": str(selected[0]["data"].get("benchmark_url") or ""),
            "citation": str(selected[0]["data"].get("citation") or ""),
            "license": str(selected[0]["data"].get("license") or ""),
        }
    return {"status": "missing", "paths": [], "roles": {}, "reason": "no formal external candidate/baseline/ablation pack found"}


def _gold_default_manifest_role(path: Path, data: dict[str, Any]) -> str:
    role = str(data.get("role") or "").strip().lower()
    if role:
        return role
    for value in [path.parent.name, path.stem]:
        lowered = value.lower()
        for candidate in ["candidate", "baseline", "ablation"]:
            if candidate in lowered:
                return candidate
    return ""


def _gold_default_manifest_group(path: Path, role: str) -> str:
    if role in {"candidate", "baseline", "ablation"} and path.parent.name.lower() == role:
        return str(path.parent.parent)
    return str(path.parent)


def _gold_default_command_signature(data: dict[str, Any]) -> str:
    output_values = {str(data.get("metrics_path") or "").strip(), str(data.get("submission_path") or "").strip()}
    expected = data.get("expected_artifacts")
    if isinstance(expected, list):
        output_values.update(str(item).strip() for item in expected if str(item).strip())
    output_values.discard("")
    normalized: list[str] = []
    for token in data.get("command", []) if isinstance(data.get("command"), list) else []:
        value = str(token).strip()
        normalized.append("<output>" if value in output_values else value)
    return " ".join(normalized)


def _safe_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def _render_gold_defaults_markdown(defaults: dict[str, Any]) -> str:
    literature = defaults.get("literature") if isinstance(defaults.get("literature"), dict) else {}
    execution = defaults.get("execution") if isinstance(defaults.get("execution"), dict) else {}
    pack = execution.get("benchmark_pack") if isinstance(execution.get("benchmark_pack"), dict) else {}
    support = defaults.get("support_runs") if isinstance(defaults.get("support_runs"), dict) else {}
    release = defaults.get("release") if isinstance(defaults.get("release"), dict) else {}
    lines = [
        "# Gold Defaults",
        "",
        "- 作用：只回填正式 run 的启动门槛配置；不启动研究、不批准 gate、不生成 seed。",
        f"- 论文级门槛：{'on' if defaults.get('paper_grade_enabled') else 'off'}",
        f"- 文献：provider={literature.get('provider') or '-'}；sources={', '.join(_list_from_payload(literature.get('sources'))) or '-'}；max_papers>={literature.get('max_papers') or '-'}；max_search_queries>={literature.get('max_search_queries') or '-'}",
        f"- Seed 要求：至少 {literature.get('min_doi_url_seed_papers') or 0} 条 DOI/URL seed，覆盖 {', '.join(_list_from_payload(literature.get('required_seed_roles'))) or '-'}",
        f"- 执行：mode={execution.get('mode') or '-'}；repeats>={execution.get('repeats') or '-'}；timeout>={execution.get('timeout_seconds') or '-'}s",
        f"- Benchmark pack：{pack.get('status') or '-'}；{', '.join(_list_from_payload(pack.get('paths'))) or pack.get('reason') or '-'}",
        f"- Support runs：{support.get('status') or '-'}；benchmark={support.get('benchmark_pack_run_dir') or '-'}；fulltext={support.get('fulltext_grounding_run_dir') or '-'}",
        f"- Release 必填：{', '.join(_list_from_payload(release.get('required_fields'))) or '-'}",
        "",
        "## Manual Todos",
    ]
    todos = _list_from_payload(defaults.get("manual_todos"))
    lines.extend(f"- {item}" for item in todos) if todos else lines.append("- 无")
    return "\n".join(lines)


def _benchmark_template(topic: str) -> dict[str, Any]:
    topic = topic.strip()
    is_motion_planning = any(token in topic.lower() for token in ["机械臂", "路径规划", "motion planning", "robot"])
    slug = "robot-motion-planning" if is_motion_planning else "research-benchmark"
    baseline = "RRT*" if is_motion_planning else "baseline-method"
    benchmark_url = "https://ompl.kavrakilab.org/benchmark.html" if is_motion_planning else "https://example.org/benchmark"
    citation = (
        "OMPL benchmark and baseline citation; replace with exact paper DOI/BibTeX before publication"
        if is_motion_planning
        else "Benchmark/dataset/baseline paper DOI or BibTeX key"
    )
    template = {
        "name": slug,
        "role": "candidate",
        "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
        "metrics_path": "metrics.json",
        "expected_artifacts": ["metrics.json"],
        "expected_metrics": ["success_rate", "planning_time"] if is_motion_planning else ["score", "runtime_cost"],
        "metric_schema": {
            "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction of benchmark tasks solved."},
            "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Wall-clock planning time."},
        }
        if is_motion_planning
        else {
            "score": {"direction": "higher_is_better", "unit": "points", "description": "Primary benchmark score."},
            "runtime_cost": {"direction": "lower_is_better", "unit": "seconds", "description": "Evaluation runtime cost."},
        },
        "grader": "grade.py",
        "grader_path": "grade.py",
        "grader_version": "VERIFY-BEFORE-RUN",
        "grader_sha256": "VERIFY-BEFORE-RUN",
        "submission_path": "submission.csv",
        "seed_policy": "RESEARCH_AGENT_SEED fixes task sampling and split selection",
        "min_repeats": 5,
        "source_files": ["run_benchmark.py"],
        "benchmark_kind": "external",
        "benchmark_url": benchmark_url,
        "dataset_url": benchmark_url,
        "dataset_version": "VERIFY-BEFORE-RUN",
        "split_name": "VERIFY-BEFORE-RUN",
        "split_path": "split-manifest.json",
        "split_sha256": "VERIFY-BEFORE-RUN",
        "license": "VERIFY-BEFORE-RUN",
        "baseline": baseline,
        "baseline_version": "VERIFY-BEFORE-RUN",
        "citation": citation,
        "notes": [
            "Template only: replace dataset_url, dataset_version, split_name, split_sha256, metric_schema, grader_version, grader_sha256, license, baseline_version, and citation before running.",
            "Use the Web Benchmark preview after creating the manifest file.",
        ],
    }
    required_fields = _benchmark_required_fields()
    schema_path = ROOT / "examples" / "benchmark-adapter" / "manifest.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if isinstance(schema, dict) and isinstance(schema.get("required"), list):
            required_fields = [str(item) for item in schema["required"]]
    except (OSError, json.JSONDecodeError):
        pass
    suggested_path = f"benchmarks/{slug}/manifest.json"
    markdown = "\n".join(
        [
            "# Benchmark Manifest 模板",
            "",
            f"- Topic: {topic or '(未填写)'}",
            f"- Suggested path: `{suggested_path}`",
            "- Read-only: this endpoint does not create files, create runs, or execute commands.",
            "- Required fields: " + ", ".join(f"`{field}`" for field in required_fields),
            "",
            "人工准备步骤：",
            "1. 用下方 JSON 作为起点创建 manifest。",
            "2. 替换 `dataset_url`、`dataset_version`、`split_name`、`split_path`、`split_sha256`、`metric_schema`、`grader_path`、`grader_version`、`grader_sha256`、`license`、`baseline_version`、`citation`、`grader/submission_path` 和 `seed_policy`，确保来源、评分和重复实验可追溯；正式论文级 run 的 `dataset_url` 必须是公开 http(s) 来源，不能是 `procedural://` 或本地路径。",
            "3. 论文级 run 需要分别准备 `candidate`、`baseline`、`ablation` 三个 role 的 manifest，且 expected_metrics 至少有共同核心指标。",
            "4. 在 Web 表单填入真实 manifest 路径，先运行只读 Benchmark preview。",
            "5. 只有人工审核和执行确认通过后，benchmark 才能进入实验执行。",
        ]
    )
    return {
        "template": template,
        "markdown": markdown,
        "suggested_path": suggested_path,
        "required_fields": required_fields,
    }


def _lint_benchmark_manifest_payload(payload: dict[str, Any], paper_grade: PaperGradeConfig | None = None) -> dict[str, Any]:
    raw = str(payload.get("manifest") or "").strip()
    allowed_commands = _comma_items(str(payload.get("allowed_commands") or "python3, pytest"))
    paper_grade_config = paper_grade or PaperGradeConfig()
    min_execution_repeats = max(1, int(paper_grade_config.min_execution_repeats or 0))
    issues: list[str] = []
    warnings: list[str] = []
    try:
        manifest = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        manifest = {}
        issues.append(f"manifest JSON 解析失败：{exc}")
    if not isinstance(manifest, dict):
        manifest = {}
        issues.append("manifest 顶层必须是 JSON object。")

    required = _benchmark_required_fields()
    for field in required:
        if not _has_manifest_value(manifest.get(field)):
            issues.append(f"缺少必填字段：{field}")

    role = str(manifest.get("role") or "").strip().lower()
    if role and role not in {"candidate", "baseline", "ablation", "other"}:
        issues.append(f"role 必须是 candidate、baseline、ablation 或 other：{role}")

    command = manifest.get("command")
    command_items = [str(item) for item in command] if isinstance(command, list) else []
    if not isinstance(command, list):
        issues.append("command 必须是字符串数组。")
    elif not command_items:
        issues.append("command 不能为空。")
    elif str(command_items[0]).strip() not in allowed_commands:
        issues.append(f"命令 '{command_items[0]}' 不在 allowed_commands 白名单中。")
    for index, token in enumerate(command_items):
        value = str(token)
        if not value.strip():
            issues.append(f"command[{index}] 不能为空。")
        elif any(char in value for char in [";", "&", "|", "<", ">", "`", "$", "\n", "\r"]):
            issues.append(f"command[{index}] 含 shell 元字符：{value}")

    metrics_path = str(manifest.get("metrics_path") or "").strip()
    expected = manifest.get("expected_artifacts")
    expected_items = [str(item) for item in expected] if isinstance(expected, list) else []
    if not isinstance(expected, list):
        issues.append("expected_artifacts 必须是字符串数组。")
    elif metrics_path and metrics_path not in expected_items:
        issues.append("metrics_path 必须出现在 expected_artifacts 中。")
    for value, label in [
        (metrics_path, "metrics_path"),
        *[(item, "expected_artifacts") for item in expected_items],
        *[(item, "source_files") for item in _manifest_string_list(manifest.get("source_files"))],
        *([(str(manifest.get("grader") or ""), "grader")] if str(manifest.get("grader") or "").strip() else []),
        *([(str(manifest.get("grader_path") or ""), "grader_path")] if str(manifest.get("grader_path") or "").strip() else []),
        *([(str(manifest.get("split_path") or ""), "split_path")] if str(manifest.get("split_path") or "").strip() else []),
        *([(str(manifest.get("submission_path") or ""), "submission_path")] if str(manifest.get("submission_path") or "").strip() else []),
    ]:
        if not _safe_relative_token(value):
            issues.append(f"{label} 必须是 manifest 目录内的相对路径：{value}")

    expected_metrics = manifest.get("expected_metrics")
    if not isinstance(expected_metrics, list) or not [str(item).strip() for item in expected_metrics if str(item).strip()]:
        issues.append("expected_metrics 必须是非空字符串数组。")
    if not str(manifest.get("grader") or "").strip() and not str(manifest.get("submission_path") or "").strip():
        issues.append("grader 或 submission_path 至少需要配置一个。")
    if not str(manifest.get("seed_policy") or "").strip():
        issues.append("seed_policy 不能为空。")
    try:
        min_repeats = int(manifest.get("min_repeats") or 0)
    except (TypeError, ValueError):
        min_repeats = 0
    if min_repeats <= 0:
        issues.append("min_repeats 必须是正整数。")
    elif min_repeats < min_execution_repeats:
        warnings.append(f"min_repeats={min_repeats} 低于当前 paper-grade 阈值 {min_execution_repeats}；只适合 smoke。")

    for field in ["dataset_url", "dataset_version", "split_name", "split_sha256", "grader_version", "grader_sha256", "license", "baseline_version", "citation", "seed_policy"]:
        value = str(manifest.get(field) or "").strip()
        if value.upper().startswith("VERIFY") or "replace" in value.lower() or "example" in value.lower():
            warnings.append(f"{field} 仍像占位符，正式执行前需要替换为可追溯信息。")

    path_value = str(payload.get("path") or "").strip()
    if path_value and _benchmark_manifest_save_path(path_value) is None:
        issues.append("保存路径必须位于 benchmarks/**/manifest.json。")

    paper_grade_issues = _benchmark_manifest_paper_grade_issues(manifest, min_execution_repeats=min_execution_repeats)
    status = "blocked" if issues else "ready"
    return {
        "status": status,
        "paper_grade_status": "ready" if not paper_grade_issues else "review_required",
        "paper_grade_issues": paper_grade_issues,
        "min_execution_repeats": min_execution_repeats,
        "path": path_value,
        "required_fields": required,
        "manifest": manifest,
        "allowed_commands": allowed_commands,
        "blocking_issues": _unique_strings(issues),
        "warnings": _unique_strings(warnings),
        "manual_tasks": _benchmark_manifest_manual_tasks(manifest),
    }


def _render_benchmark_manifest_lint_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Manifest 草稿校验",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 路径：{report.get('path') or '-'}",
        f"- 白名单：{', '.join(str(item) for item in report.get('allowed_commands', [])) or '-'}",
        "",
        "## 阻断问题",
    ]
    blocking = report.get("blocking_issues") if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 警告"])
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- 无")
    lines.extend(["", "## Paper-grade"])
    lines.append(f"- 状态：{report.get('paper_grade_status') or '-'}")
    paper_grade = report.get("paper_grade_issues") if isinstance(report.get("paper_grade_issues"), list) else []
    lines.extend(f"- {item}" for item in paper_grade) if paper_grade else lines.append("- 单 manifest 字段满足 paper-grade 单角色要求；完整论文级 run 仍需 candidate/baseline/ablation manifest set。")
    lines.extend(["", "## 人工待办"])
    tasks = report.get("manual_tasks") if isinstance(report.get("manual_tasks"), list) else []
    lines.extend(f"- [ ] {item}" for item in tasks) if tasks else lines.append("- 无")
    lines.extend(
        [
            "",
            "## 边界",
            "- 草稿校验和保存不会创建 run 或执行命令。",
            "- 保存后仍需点击只读 Benchmark preview，再经人工 review gate 和 execution gate。",
        ]
    )
    return "\n".join(lines)


def _benchmark_required_fields() -> list[str]:
    schema_path = ROOT / "examples" / "benchmark-adapter" / "manifest.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if isinstance(schema, dict) and isinstance(schema.get("required"), list):
            return [str(item) for item in schema["required"]]
    except (OSError, json.JSONDecodeError):
        pass
    return ["name", "command", "metrics_path", "expected_artifacts", "expected_metrics", "metric_schema", "dataset_url", "dataset_version", "split_name", "split_sha256", "grader_version", "grader_sha256", "license", "baseline_version", "citation", "seed_policy", "min_repeats"]


def _benchmark_manifest_save_path(value: str) -> Path | None:
    if not value:
        return None
    raw = Path(value)
    if raw.is_absolute() or any(part in {"..", ""} for part in raw.parts):
        return None
    if raw.suffix.lower() != ".json" or raw.name != "manifest.json":
        return None
    if not raw.parts or raw.parts[0] != "benchmarks" or len(raw.parts) < 3:
        return None
    candidate = ROOT
    for part in raw.parts:
        candidate /= part
        try:
            if candidate.is_symlink():
                return None
        except OSError:
            return None
    try:
        target = (ROOT / raw).resolve()
        root = ROOT.resolve()
    except OSError:
        return None
    if target == root or not _is_relative_to(target, root):
        return None
    return target


def _benchmark_manifest_manual_tasks(manifest: dict[str, Any]) -> list[str]:
    tasks = [
        "确认 command 指向的 adapter 源文件已经放在 manifest 同目录，并能写出 metrics_path。",
        "确认 dataset_url/benchmark_url、dataset_version、split_name、split_sha256、metric_schema、grader_version、grader_sha256、license、baseline_version、citation、grader/submission_path、expected_metrics 和 seed_policy 可以支撑论文中的 benchmark 声明。",
        "保存后先运行只读 Benchmark preview；不要跳过人工 review gate 和 execution gate。",
    ]
    if manifest.get("baseline"):
        tasks.append(f"核对 baseline 映射：{manifest.get('baseline')}")
    return _unique_strings(tasks)


def _benchmark_manifest_paper_grade_issues(manifest: dict[str, Any], *, min_execution_repeats: int = 3) -> list[str]:
    issues: list[str] = []
    role = str(manifest.get("role") or "").strip().lower()
    if role not in {"candidate", "baseline", "ablation"}:
        issues.append("单个 manifest 需要声明 role=candidate/baseline/ablation；完整论文级 run 需要三类 role 都存在。")
    metrics = [str(item).strip() for item in manifest.get("expected_metrics", [])] if isinstance(manifest.get("expected_metrics"), list) else []
    if not metrics:
        issues.append("expected_metrics 需要声明可与其他 role 共享的核心指标。")
    try:
        min_repeats = int(manifest.get("min_repeats") or 0)
    except (TypeError, ValueError):
        min_repeats = 0
    if min_repeats < min_execution_repeats:
        preferred = max(5, min_execution_repeats)
        issues.append(f"paper-grade manifest 需要 min_repeats >= {min_execution_repeats}；强结论优先 >= {preferred}。")
    issues.extend(
        formal_benchmark_provenance_issues(
            name=str(manifest.get("name") or "manifest"),
            benchmark_kind=str(manifest.get("benchmark_kind") or ""),
            benchmark_url=str(manifest.get("benchmark_url") or ""),
            dataset_url=str(manifest.get("dataset_url") or ""),
            dataset_version=str(manifest.get("dataset_version") or ""),
            split_name=str(manifest.get("split_name") or ""),
            split_sha256=str(manifest.get("split_sha256") or ""),
            license_value=str(manifest.get("license") or ""),
            baseline_version=str(manifest.get("baseline_version") or ""),
            citation=str(manifest.get("citation") or ""),
        )
    )
    issues.extend(
        formal_benchmark_metric_contract_issues(
            name=str(manifest.get("name") or "manifest"),
            expected_metrics=metrics,
            metric_schema=_manifest_metric_schema(manifest.get("metric_schema")),
            grader_version=str(manifest.get("grader_version") or ""),
            grader_sha256=str(manifest.get("grader_sha256") or ""),
        )
    )
    return _unique_strings(issues)


def _manifest_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _manifest_metric_schema(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for key, raw in value.items():
        if not isinstance(raw, dict):
            continue
        metric = str(key).strip()
        if not metric:
            continue
        result[metric] = {
            "direction": str(raw.get("direction") or "").strip(),
            "unit": str(raw.get("unit") or "").strip(),
            "description": str(raw.get("description") or "").strip(),
        }
    return result


def _has_manifest_value(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _safe_relative_token(value: str) -> bool:
    path = Path(str(value or ""))
    return bool(str(value or "").strip()) and not path.is_absolute() and all(part != ".." for part in path.parts)


def _comma_items(value: str) -> list[str]:
    return _unique_strings([item.strip() for item in value.split(",") if item.strip()])


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _public_diagnostic(diagnostic: Any) -> dict[str, Any]:
    data = asdict(diagnostic) if hasattr(diagnostic, "__dataclass_fields__") else dict(diagnostic)
    return {
        "status": data.get("status", "") or data.get("severity", ""),
        "category": data.get("category", ""),
        "severity": data.get("severity", ""),
        "summary": data.get("summary", ""),
        "likely_cause": data.get("likely_cause", ""),
        "recommended_actions": len(data.get("recommended_actions", [])) if isinstance(data.get("recommended_actions"), list) else 0,
        "stage": data.get("stage", ""),
        "created_at": data.get("created_at", ""),
    }


def _read_public_diagnostic(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / RUN_DIAGNOSTIC_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _public_diagnostic(data)


def _public_preflight(report: Any) -> dict[str, Any]:
    data = asdict(report) if hasattr(report, "__dataclass_fields__") else dict(report)
    checks = data.get("checks", []) if isinstance(data.get("checks"), list) else []
    return {
        "status": data.get("status", ""),
        "checks": len(checks),
        "fails": sum(1 for item in checks if isinstance(item, dict) and item.get("status") == "fail"),
        "warnings": sum(1 for item in checks if isinstance(item, dict) and item.get("status") == "warn"),
    }


def _read_public_preflight(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / PREFLIGHT_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _public_preflight(data)


def _read_public_final_readiness(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / FINAL_READINESS_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "status": data.get("status", ""),
        "score_before": data.get("score_before"),
        "score_after": data.get("score_after"),
        "unsupported_after": data.get("unsupported_after", 0),
        "weak_after": data.get("weak_after", 0),
        "deferred_tasks": len(data.get("deferred_tasks", [])) if isinstance(data.get("deferred_tasks"), list) else 0,
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
        "submission_status": data.get("submission_status", ""),
        "submission_blocking_issues": len(data.get("submission_blocking_issues", [])) if isinstance(data.get("submission_blocking_issues"), list) else 0,
        "submission_manual_tasks": len(data.get("submission_manual_tasks", [])) if isinstance(data.get("submission_manual_tasks"), list) else 0,
    }


def _read_public_availability(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / CODE_DATA_AVAILABILITY_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "status": data.get("status", ""),
        "ready_for_internal_release": data.get("ready_for_internal_release") is True,
        "ready_for_submission_check": data.get("ready_for_submission_check") is True,
        "manual_tasks": len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0,
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
    }


def _read_public_submission_package(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / SUBMISSION_PACKAGE_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "status": data.get("status", ""),
        "package_zip": data.get("package_zip", ""),
        "files": len(data.get("files", [])) if isinstance(data.get("files"), list) else 0,
        "manual_tasks": len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0,
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
    }


def _read_public_iteration_plan(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / ITERATION_PLAN_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "status": data.get("status", ""),
        "decision": data.get("decision", ""),
        "items": len(data.get("items", [])) if isinstance(data.get("items"), list) else 0,
        "execution_mode": data.get("execution_mode", ""),
        "benchmark_status": data.get("benchmark_status", ""),
    }


def _read_public_experiment_manager(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / EXPERIMENT_MANAGER_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    queue_summary = data.get("queue_summary") if isinstance(data.get("queue_summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "decision": data.get("manager_decision", ""),
        "execution_policy": data.get("execution_policy", ""),
        "selected_branch_id": data.get("selected_branch_id", ""),
        "selected_idea_title": data.get("selected_idea_title", ""),
        "next_candidates": len(data.get("next_expansion_candidates", [])) if isinstance(data.get("next_expansion_candidates"), list) else 0,
        "constraints": len(data.get("planning_constraints", [])) if isinstance(data.get("planning_constraints"), list) else 0,
        "queue_total": queue_summary.get("total", 0),
        "queue_active": queue_summary.get("active", 0),
        "queue_blocked": queue_summary.get("blocked", 0),
        "queue_human_review": queue_summary.get("human_review", 0),
        "queue_ready_backlog": queue_summary.get("ready_backlog", 0),
        "queue_deferred": queue_summary.get("deferred", 0),
        "queue_blocks_current_experiment": queue_summary.get("blocks_current_experiment", 0),
    }


def _read_public_benchmark_schema(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / BENCHMARK_RESULT_SCHEMA_AUDIT_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    provenance = data.get("adapter_provenance") if isinstance(data.get("adapter_provenance"), dict) else {}
    return {
        "status": data.get("status", ""),
        "execution_mode": data.get("execution_mode", ""),
        "actual_metrics": len(data.get("actual_metrics", [])) if isinstance(data.get("actual_metrics"), list) else 0,
        "benchmark_expected_metrics": len(data.get("benchmark_expected_metrics", [])) if isinstance(data.get("benchmark_expected_metrics"), list) else 0,
        "adapter_expected_artifacts": len(data.get("adapter_expected_artifacts", [])) if isinstance(data.get("adapter_expected_artifacts"), list) else 0,
        "adapter_provenance": len(provenance),
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
        "manual_tasks": len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0,
        "warnings": len(data.get("warnings", [])) if isinstance(data.get("warnings"), list) else 0,
    }


def _read_public_repair_queue(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / REPAIR_QUEUE_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "items": len(data.get("items", [])) if isinstance(data.get("items"), list) else 0,
        "block": summary.get("block", 0),
        "high": summary.get("high", 0),
        "medium": summary.get("medium", 0),
        "blocks_submission": summary.get("blocks_submission", 0),
    }


def _read_public_open_source_lessons(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / OPEN_SOURCE_LESSONS_JSON)
    if not data:
        return None
    evidence = data.get("project_evidence") if isinstance(data.get("project_evidence"), list) else []
    statuses: dict[str, int] = {}
    verified_projects = 0
    for item in evidence:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        if item.get("verified_files") or str(item.get("head_commit") or "").strip():
            verified_projects += 1
    return {
        "status": data.get("status", ""),
        "topic": data.get("topic", ""),
        "profiles": _count_list(data.get("profiles")),
        "project_evidence": len(evidence),
        "project_statuses": statuses,
        "version_verified_projects": verified_projects,
        "lessons": _count_list(data.get("lessons")),
        "manual_checklist": _count_list(data.get("manual_checklist")),
    }


def _read_public_open_source_compliance(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / OPEN_SOURCE_COMPLIANCE_JSON)
    if not data:
        return None
    results = data.get("lesson_results") if isinstance(data.get("lesson_results"), list) else []
    counts: dict[str, int] = {}
    blocked_lessons: list[str] = []
    warn_lessons: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        lesson_id = str(item.get("lesson_id") or "")
        if status == "block" and lesson_id:
            blocked_lessons.append(lesson_id)
        elif status == "warn" and lesson_id:
            warn_lessons.append(lesson_id)
    project_summary = data.get("source_project_summary") if isinstance(data.get("source_project_summary"), dict) else _open_source_project_summary_from_results(results)
    blocking_count = _count_list(data.get("blocking_issues"))
    manual_count = _count_list(data.get("manual_tasks"))
    recommended_count = _count_list(data.get("recommended_actions"))
    return {
        "status": data.get("status", ""),
        "topic": data.get("topic", ""),
        "score": _float_from_payload(data.get("score")),
        "checked_lessons": _count_from_payload(data.get("checked_lessons")),
        "lesson_statuses": counts,
        "blocked_lessons": blocked_lessons[:8],
        "warn_lessons": warn_lessons[:8],
        "project_count": _count_from_payload(project_summary.get("project_count")) if isinstance(project_summary, dict) else 0,
        "blocked_project_count": _count_from_payload(project_summary.get("blocked_project_count")) if isinstance(project_summary, dict) else 0,
        "warn_project_count": _count_from_payload(project_summary.get("warn_project_count")) if isinstance(project_summary, dict) else 0,
        "pass_project_count": _count_from_payload(project_summary.get("pass_project_count")) if isinstance(project_summary, dict) else 0,
        "blocked_projects": _public_open_source_project_names(project_summary.get("blocked_projects") if isinstance(project_summary, dict) else []),
        "warn_projects": _public_open_source_project_names(project_summary.get("warn_projects") if isinstance(project_summary, dict) else []),
        "project_evidence_statuses": dict(project_summary.get("evidence_statuses") or {}) if isinstance(project_summary, dict) and isinstance(project_summary.get("evidence_statuses"), dict) else {},
        "blocking_issue_count": blocking_count,
        "manual_task_count": manual_count,
        "recommended_action_count": recommended_count,
        "blocking_issues": blocking_count,
        "manual_tasks": manual_count,
        "recommended_actions": recommended_count,
    }


def _open_source_project_summary_from_results(results: list[Any]) -> dict[str, Any]:
    projects: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        for project in _list_from_payload(item.get("source_projects")):
            name = str(project).strip()
            key = _public_project_key(name)
            if not key:
                continue
            entry = projects.setdefault(key, {"project_name": name, "pass": 0, "warn": 0, "block": 0, "unknown": 0})
            entry[status] = _count_from_payload(entry.get(status)) + 1
    project_items: list[dict[str, Any]] = []
    for item in projects.values():
        status = "block" if item.get("block") else "warn" if item.get("warn") else "pass"
        project_items.append({"project_name": item.get("project_name", ""), "status": status})
    blocked = [str(item.get("project_name") or "") for item in project_items if item.get("status") == "block" and str(item.get("project_name") or "").strip()]
    warn = [str(item.get("project_name") or "") for item in project_items if item.get("status") == "warn" and str(item.get("project_name") or "").strip()]
    return {
        "project_count": len(project_items),
        "blocked_project_count": len(blocked),
        "warn_project_count": len(warn),
        "pass_project_count": sum(1 for item in project_items if item.get("status") == "pass"),
        "blocked_projects": blocked,
        "warn_projects": warn,
        "evidence_statuses": {},
    }


def _public_open_source_project_names(value: Any) -> list[str]:
    return [str(item).strip() for item in _list_from_payload(value) if str(item).strip()][:8]


def _public_project_key(value: str) -> str:
    text = value.strip().lower()
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if "mlagentbench" in compact or "mlebench" in compact:
        return "mlagentbench"
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text.replace("-style tasks", "").replace(" ", "").replace("-", "").replace("_", "")


def _public_llm_observability_backfill_report(report: dict[str, Any]) -> dict[str, Any]:
    items = report.get("items") if isinstance(report.get("items"), list) else []
    public_items: list[dict[str, Any]] = []
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        public_items.append(
            {
                "run_id": str(item.get("run_id") or ""),
                "action": str(item.get("action") or ""),
                "trace": bool(item.get("trace")),
                "economics": bool(item.get("economics")),
                "observability": bool(item.get("observability")),
                "trace_status": str(item.get("trace_status") or ""),
                "economics_status": str(item.get("economics_status") or ""),
                "observability_status": str(item.get("observability_status") or ""),
                "total_calls": _count_from_payload(item.get("total_calls")),
                "successful_calls": _count_from_payload(item.get("successful_calls")),
                "failed_calls": _count_from_payload(item.get("failed_calls")),
                "trace_blocking_issues": _count_from_payload(item.get("trace_blocking_issues")),
                "economics_blocking_issues": _count_from_payload(item.get("economics_blocking_issues")),
                "observability_blocking_issues": _count_from_payload(item.get("observability_blocking_issues")),
            }
        )
    return {
        "schema_version": _count_from_payload(report.get("schema_version")),
        "generated_at": str(report.get("generated_at") or ""),
        "runs_dir": str(report.get("runs_dir") or ""),
        "dry_run": bool(report.get("dry_run")),
        "force": bool(report.get("force")),
        "limit": _count_from_payload(report.get("limit")),
        "scanned_runs": _count_from_payload(report.get("scanned_runs")),
        "trace_written": _count_from_payload(report.get("trace_written")),
        "economics_written": _count_from_payload(report.get("economics_written")),
        "observability_written": _count_from_payload(report.get("observability_written")),
        "would_write_trace": _count_from_payload(report.get("would_write_trace")),
        "would_write_economics": _count_from_payload(report.get("would_write_economics")),
        "would_write_observability": _count_from_payload(report.get("would_write_observability")),
        "skipped_existing": _count_from_payload(report.get("skipped_existing")),
        "skipped_no_state": _count_from_payload(report.get("skipped_no_state")),
        "error_count": _count_list(report.get("errors")),
        "errors": [],
        "items": public_items,
    }


def _public_repair_resume_backfill_report(report: dict[str, Any]) -> dict[str, Any]:
    items = report.get("items") if isinstance(report.get("items"), list) else []
    public_items: list[dict[str, Any]] = []
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        public_items.append(
            {
                "run_id": str(item.get("run_id") or ""),
                "action": str(item.get("action") or ""),
                "queue_status": str(item.get("queue_status") or ""),
                "queue_items": _count_from_payload(item.get("queue_items")),
                "queue_block": _count_from_payload(item.get("queue_block")),
                "queue_high": _count_from_payload(item.get("queue_high")),
                "queue_medium": _count_from_payload(item.get("queue_medium")),
                "plan_status": str(item.get("plan_status") or ""),
                "can_resume": bool(item.get("can_resume")),
                "rerun_from": str(item.get("rerun_from") or ""),
                "repair_items": _count_from_payload(item.get("repair_items")),
                "retrieval_repair_tasks": _count_from_payload(item.get("retrieval_repair_tasks")),
                "artifacts_to_remove": _count_from_payload(item.get("artifacts_to_remove")),
                "directories_to_remove": _count_from_payload(item.get("directories_to_remove")),
                "review_reapproval_required": bool(item.get("review_reapproval_required")),
                "execution_reapproval_required": bool(item.get("execution_reapproval_required")),
                "resume_readiness": str(item.get("resume_readiness") or ""),
                "blocking_preconditions": _count_from_payload(item.get("blocking_preconditions")),
                "precondition_codes": [str(value) for value in _list_from_payload(item.get("precondition_codes"))[:8]],
                "required_config": [str(value) for value in _list_from_payload(item.get("required_config"))[:8]],
                "applied": bool(item.get("applied")),
            }
        )
    return {
        "schema_version": _count_from_payload(report.get("schema_version")),
        "generated_at": str(report.get("generated_at") or ""),
        "runs_dir": str(report.get("runs_dir") or ""),
        "dry_run": bool(report.get("dry_run")),
        "force": bool(report.get("force")),
        "limit": _count_from_payload(report.get("limit")),
        "scanned_runs": _count_from_payload(report.get("scanned_runs")),
        "written": _count_from_payload(report.get("written")),
        "would_write": _count_from_payload(report.get("would_write")),
        "stale_existing": _count_from_payload(report.get("stale_existing")),
        "refreshed_stale": _count_from_payload(report.get("refreshed_stale")),
        "still_needs_preconditions": _count_from_payload(report.get("still_needs_preconditions")),
        "skipped_existing": _count_from_payload(report.get("skipped_existing")),
        "skipped_no_state": _count_from_payload(report.get("skipped_no_state")),
        "skipped_no_active_queue": _count_from_payload(report.get("skipped_no_active_queue")),
        "error_count": _count_list(report.get("errors")),
        "errors": [],
        "items": public_items,
    }


def _public_repair_resume_backlog_report(report: dict[str, Any]) -> dict[str, Any]:
    items = report.get("items") if isinstance(report.get("items"), list) else []
    public_items: list[dict[str, Any]] = []
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        run_id = str(item.get("run_id") or "")
        public_items.append(
            {
                "run_id": run_id,
                "queue_status": str(item.get("queue_status") or ""),
                "queue_items": _count_from_payload(item.get("queue_items")),
                "queue_block": _count_from_payload(item.get("queue_block")),
                "queue_high": _count_from_payload(item.get("queue_high")),
                "queue_medium": _count_from_payload(item.get("queue_medium")),
                "plan_status": str(item.get("plan_status") or ""),
                "can_resume": bool(item.get("can_resume")),
                "applied": bool(item.get("applied")),
                "rerun_from": str(item.get("rerun_from") or ""),
                "repair_items": _count_from_payload(item.get("repair_items")),
                "retrieval_repair_tasks": _count_from_payload(item.get("retrieval_repair_tasks")),
                "artifacts_to_remove": _count_from_payload(item.get("artifacts_to_remove")),
                "directories_to_remove": _count_from_payload(item.get("directories_to_remove")),
                "review_reapproval_required": bool(item.get("review_reapproval_required")),
                "execution_reapproval_required": bool(item.get("execution_reapproval_required")),
                "resume_readiness": str(item.get("resume_readiness") or ""),
                "blocking_preconditions": _count_from_payload(item.get("blocking_preconditions")),
                "precondition_codes": [str(value) for value in _list_from_payload(item.get("precondition_codes"))[:8]],
                "required_config": [str(value) for value in _list_from_payload(item.get("required_config"))[:8]],
                "repair_plan_sources": [str(value) for value in _list_from_payload(item.get("repair_plan_sources"))[:6]],
                "doctor_report": item.get("doctor_report") is True,
                "priority_score": _count_from_payload(item.get("priority_score")),
                "command": f"PYTHONPATH=src python3 -m research_agent repair-resume runs/{run_id} --apply" if run_id else "",
            }
        )
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "schema_version": _count_from_payload(report.get("schema_version")),
        "generated_at": str(report.get("generated_at") or ""),
        "runs_dir": "runs",
        "scanned_runs": _count_from_payload(report.get("scanned_runs")),
        "skipped_no_state": _count_from_payload(report.get("skipped_no_state")),
        "status": str(report.get("status") or ""),
        "summary": {
            "total": _count_from_payload(summary.get("total")),
            "ready_to_apply": _count_from_payload(summary.get("ready_to_apply")),
            "needs_preconditions": _count_from_payload(summary.get("needs_preconditions")),
            "applied": _count_from_payload(summary.get("applied")),
            "blocked": _count_from_payload(summary.get("blocked")),
            "blocking_preconditions": _count_from_payload(summary.get("blocking_preconditions")),
            "review_reapproval_required": _count_from_payload(summary.get("review_reapproval_required")),
            "execution_reapproval_required": _count_from_payload(summary.get("execution_reapproval_required")),
        },
        "items": public_items,
        "next_actions": [str(item) for item in _list_from_payload(report.get("next_actions"))[:8]],
    }


PUBLIC_SUMMARY_ARTIFACT_READERS = {
    REPAIR_RESUME_PLAN_JSON: lambda out_dir: _read_public_repair_resume_artifact(out_dir),
    REPAIR_RESUME_PLAN_MD: lambda out_dir: _read_public_repair_resume_artifact(out_dir),
    GOLD_RUN_DOCTOR_JSON: lambda out_dir: _read_public_gold_run_doctor(out_dir),
    GOLD_RUN_DOCTOR_MD: lambda out_dir: _read_public_gold_run_doctor(out_dir),
    GOLD_RUN_VERIFICATION_JSON: lambda out_dir: _read_public_gold_run_verification(out_dir),
    GOLD_RUN_VERIFICATION_MD: lambda out_dir: _read_public_gold_run_verification(out_dir),
    GOLD_LAUNCH_BUNDLE_JSON: lambda out_dir: _read_public_gold_launch_bundle(out_dir),
    GOLD_LAUNCH_BUNDLE_MD: lambda out_dir: _read_public_gold_launch_bundle(out_dir),
    GOLD_LAUNCH_MANIFEST_JSON: lambda out_dir: _read_public_gold_launch_manifest(out_dir),
    GOLD_LAUNCH_MANIFEST_MD: lambda out_dir: _read_public_gold_launch_manifest(out_dir),
    REPAIR_RESOLUTION_AUDIT_JSON: lambda out_dir: _read_public_repair_resolution(out_dir),
    REPAIR_RESOLUTION_AUDIT_MD: lambda out_dir: _read_public_repair_resolution(out_dir),
    REPAIR_QUEUE_JSON: lambda out_dir: _read_public_repair_queue(out_dir),
    REPAIR_QUEUE_MD: lambda out_dir: _read_public_repair_queue(out_dir),
    OPEN_SOURCE_LESSONS_JSON: lambda out_dir: _read_public_open_source_lessons(out_dir),
    OPEN_SOURCE_LESSONS_MD: lambda out_dir: _read_public_open_source_lessons(out_dir),
    OPEN_SOURCE_COMPLIANCE_JSON: lambda out_dir: _read_public_open_source_compliance(out_dir),
    OPEN_SOURCE_COMPLIANCE_MD: lambda out_dir: _read_public_open_source_compliance(out_dir),
    EXPERIMENT_MANAGER_JSON: lambda out_dir: _read_public_experiment_manager(out_dir),
    EXPERIMENT_MANAGER_MD: lambda out_dir: _read_public_experiment_manager(out_dir),
    AGENT_TRAJECTORY_JSON: lambda out_dir: _read_public_agent_trajectory(out_dir),
    AGENT_TRAJECTORY_MD: lambda out_dir: _read_public_agent_trajectory(out_dir),
    AGENT_OBSERVABILITY_AUDIT_JSON: lambda out_dir: _read_public_agent_observability(out_dir),
    AGENT_OBSERVABILITY_AUDIT_MD: lambda out_dir: _read_public_agent_observability(out_dir),
    RUN_DIAGNOSTIC_JSON: lambda out_dir: _read_public_diagnostic(out_dir),
    RUN_DIAGNOSTIC_MD: lambda out_dir: _read_public_diagnostic(out_dir),
    HUMAN_GATE_AUDIT_JSON: lambda out_dir: _read_public_human_gate_audit(out_dir),
    HUMAN_GATE_AUDIT_MD: lambda out_dir: _read_public_human_gate_audit(out_dir),
    LLM_TRACE_JSON: lambda out_dir: _read_public_llm_trace(out_dir),
    LLM_TRACE_MD: lambda out_dir: _read_public_llm_trace(out_dir),
    LLM_TRACE_AUDIT_JSON: lambda out_dir: _read_public_llm_trace_audit(out_dir),
    LLM_TRACE_AUDIT_MD: lambda out_dir: _read_public_llm_trace_audit(out_dir),
    LLM_RUNTIME_CONTRACT_JSON: lambda out_dir: _read_public_llm_runtime_contract(out_dir),
    LLM_RUNTIME_CONTRACT_MD: lambda out_dir: _read_public_llm_runtime_contract(out_dir),
    RUN_ECONOMICS_AUDIT_JSON: lambda out_dir: _read_public_run_economics_audit(out_dir),
    RUN_ECONOMICS_AUDIT_MD: lambda out_dir: _read_public_run_economics_audit(out_dir),
    LLM_OBSERVABILITY_SUMMARY_JSON: lambda out_dir: _read_public_llm_observability_summary(out_dir),
    LLM_OBSERVABILITY_SUMMARY_MD: lambda out_dir: _read_public_llm_observability_summary(out_dir),
    LITERATURE_EVIDENCE_CONTRACT_JSON: lambda out_dir: _read_public_literature_evidence_contract(out_dir),
    LITERATURE_EVIDENCE_CONTRACT_MD: lambda out_dir: _read_public_literature_evidence_contract(out_dir),
    LITERATURE_GATE_DECISION_JSON: lambda out_dir: _read_public_literature_gate_decision(out_dir),
    LITERATURE_GATE_DECISION_MD: lambda out_dir: _read_public_literature_gate_decision(out_dir),
}


def _is_public_summary_artifact(filename: str) -> bool:
    return filename in PUBLIC_SUMMARY_ARTIFACT_READERS


def _public_artifact_response(out_dir: Path, filename: str) -> tuple[bytes, str] | None:
    reader = PUBLIC_SUMMARY_ARTIFACT_READERS.get(filename)
    if reader is None:
        return None
    data = reader(out_dir)
    if data is None:
        return None
    if filename.endswith(".json"):
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"
    if filename == REPAIR_RESUME_PLAN_MD:
        rendered = _render_public_repair_resume_preview_markdown(data)
    else:
        rendered = _render_public_summary_artifact_markdown(filename, data)
    return rendered.encode("utf-8"), "text/plain"


def _render_public_summary_artifact_markdown(filename: str, data: dict[str, Any]) -> str:
    title = _public_summary_title(filename)
    lines = [f"# {title}", "", f"- 状态：{data.get('status') or '-'}"]
    for key, value in data.items():
        if key == "status":
            continue
        lines.append(f"- {key}：{_public_summary_value(value)}")
    lines.extend(["", "该视图是 Web 公开摘要；完整内部产物保留在本地 run 目录中。"])
    return "\n".join(lines)


def _public_summary_title(filename: str) -> str:
    titles = {
        REPAIR_QUEUE_MD: "修复队列摘要",
        OPEN_SOURCE_LESSONS_MD: "开源经验摘要",
        OPEN_SOURCE_COMPLIANCE_MD: "开源合规摘要",
        EXPERIMENT_MANAGER_MD: "实验管理摘要",
        AGENT_TRAJECTORY_MD: "Agent 轨迹摘要",
        AGENT_OBSERVABILITY_AUDIT_MD: "Agent 可观测性摘要",
        RUN_DIAGNOSTIC_MD: "运行诊断摘要",
        LLM_TRACE_MD: "LLM 调用账本摘要",
        LLM_TRACE_AUDIT_MD: "LLM 阶段审计摘要",
        RUN_ECONOMICS_AUDIT_MD: "运行成本审计摘要",
        LLM_OBSERVABILITY_SUMMARY_MD: "LLM 可观测性总览",
        HUMAN_GATE_AUDIT_MD: "人工 Gate 审计摘要",
        GOLD_RUN_DOCTOR_MD: "Gold Run Doctor 摘要",
        GOLD_RUN_VERIFICATION_MD: "Gold Run Verification 摘要",
        GOLD_LAUNCH_BUNDLE_MD: "Gold Launch Bundle 摘要",
        GOLD_LAUNCH_MANIFEST_MD: "Gold Launch Manifest 摘要",
        LITERATURE_EVIDENCE_CONTRACT_MD: "文献证据契约摘要",
        LITERATURE_GATE_DECISION_MD: "文献证据总门禁摘要",
    }
    return titles.get(filename, f"{filename} 摘要")


def _public_summary_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "0"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value if value is not None else "-")


def _read_public_llm_trace(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / LLM_TRACE_JSON)
    if not data:
        return None
    return {
        "status": "available",
        "total_calls": _count_from_payload(data.get("total_calls")),
        "successful_calls": _count_from_payload(data.get("successful_calls")),
        "failed_calls": _count_from_payload(data.get("failed_calls")),
        "budget_exceeded_calls": _count_from_payload(data.get("budget_exceeded_calls")),
        "total_prompt_chars": _count_from_payload(data.get("total_prompt_chars")),
        "total_response_chars": _count_from_payload(data.get("total_response_chars")),
        "entries": _count_list(data.get("entries")),
    }


def _read_public_llm_trace_audit(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / LLM_TRACE_AUDIT_JSON)
    if not data:
        return None
    summary = data.get("ledger_summary") if isinstance(data.get("ledger_summary"), dict) else {}
    coverage = data.get("coverage") if isinstance(data.get("coverage"), dict) else {}
    stage_gaps = data.get("stage_gap_summary") if isinstance(data.get("stage_gap_summary"), dict) else {}
    disclosure = data.get("ai_disclosure_check") if isinstance(data.get("ai_disclosure_check"), dict) else {}
    return {
        "status": data.get("status", ""),
        "topic": data.get("topic", ""),
        "total_calls": _count_from_payload(summary.get("total_calls")),
        "successful_calls": _count_from_payload(summary.get("successful_calls")),
        "failed_calls": _count_from_payload(summary.get("failed_calls")),
        "budget_exceeded_calls": _count_from_payload(summary.get("budget_exceeded_calls")),
        "entries": _count_from_payload(summary.get("entries")),
        "required_stages": _count_from_payload(coverage.get("required_stages")),
        "passed_required": _count_from_payload(coverage.get("passed_required")),
        "missing_required_stage_count": _count_from_payload(stage_gaps.get("missing_required_stage_count")),
        "missing_required_stages": _public_llm_stage_ids(stage_gaps.get("missing_required_stages", [])),
        "warned_optional_stage_count": _count_from_payload(stage_gaps.get("warned_optional_stage_count")),
        "warned_optional_stages": _public_llm_stage_ids(stage_gaps.get("warned_optional_stages", [])),
        "stage_checks": _count_list(data.get("stage_checks")),
        "ai_disclosure_status": disclosure.get("status", ""),
        "blocking_issues": _count_list(data.get("blocking_issues")),
        "warnings": _count_list(data.get("warnings")),
        "manual_tasks": _count_list(data.get("manual_tasks")),
        "recommended_actions": _count_list(data.get("recommended_actions")),
    }


def _read_public_run_economics_audit(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / RUN_ECONOMICS_AUDIT_JSON)
    if not data:
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    budget = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    return {
        "status": data.get("status", ""),
        "topic": data.get("topic", ""),
        "total_calls": _count_from_payload(summary.get("total_calls")),
        "successful_calls": _count_from_payload(summary.get("successful_calls")),
        "failed_calls": _count_from_payload(summary.get("failed_calls")),
        "budget_exceeded_calls": _count_from_payload(summary.get("budget_exceeded_calls")),
        "input_tokens_estimated": _count_from_payload(summary.get("input_tokens_estimated")),
        "output_tokens_estimated": _count_from_payload(summary.get("output_tokens_estimated")),
        "estimated_cost_usd": summary.get("estimated_cost_usd"),
        "call_utilization": _float_from_payload(summary.get("call_utilization")),
        "prompt_utilization": _float_from_payload(summary.get("prompt_utilization")),
        "used_calls": _count_from_payload(budget.get("used_calls")),
        "max_calls": _count_from_payload(budget.get("max_calls")),
        "used_prompt_chars": _count_from_payload(budget.get("used_prompt_chars")),
        "max_prompt_chars": _count_from_payload(budget.get("max_prompt_chars")),
        "stages": _count_list(data.get("stages")),
        "blocking_issues": _count_list(data.get("blocking_issues")),
        "warnings": _count_list(data.get("warnings")),
        "manual_tasks": _count_list(data.get("manual_tasks")),
        "recommended_actions": _count_list(data.get("recommended_actions")),
    }


def _read_public_llm_observability_summary(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / LLM_OBSERVABILITY_SUMMARY_JSON)
    if not data:
        return None
    statuses = data.get("statuses") if isinstance(data.get("statuses"), dict) else {}
    runtime = data.get("runtime_contract") if isinstance(data.get("runtime_contract"), dict) else {}
    calls = data.get("llm_calls") if isinstance(data.get("llm_calls"), dict) else {}
    coverage = data.get("stage_coverage") if isinstance(data.get("stage_coverage"), dict) else {}
    tokens = data.get("token_and_cost") if isinstance(data.get("token_and_cost"), dict) else {}
    budget = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    traceability = data.get("traceability") if isinstance(data.get("traceability"), dict) else {}
    return {
        "status": data.get("status", ""),
        "topic": data.get("topic", ""),
        "runtime_contract_status": statuses.get("runtime_contract", ""),
        "trace_status": statuses.get("trace", ""),
        "economics_status": statuses.get("economics", ""),
        "agent_observability_status": statuses.get("agent_observability", ""),
        "runtime_model_configured": runtime.get("model_configured") is True,
        "runtime_api_key_persisted": runtime.get("api_key_persisted") is True,
        "runtime_call_budget_configured": runtime.get("call_budget_configured") is True,
        "runtime_prompt_budget_configured": runtime.get("prompt_budget_configured") is True,
        "runtime_pricing_configured": runtime.get("pricing_configured") is True,
        "total_calls": _count_from_payload(calls.get("total")),
        "successful_calls": _count_from_payload(calls.get("successful")),
        "failed_calls": _count_from_payload(calls.get("failed")),
        "budget_exceeded_calls": _count_from_payload(calls.get("budget_exceeded")),
        "entries": _count_from_payload(calls.get("entries")),
        "required_stages": _count_from_payload(coverage.get("required_stages")),
        "passed_required": _count_from_payload(coverage.get("passed_required")),
        "coverage_ratio": _float_from_payload(coverage.get("coverage_ratio")),
        "missing_required_stage_count": _count_from_payload(coverage.get("missing_required_stage_count")),
        "missing_required_stages": _public_llm_stage_ids(coverage.get("missing_required_stages", [])),
        "warned_optional_stage_count": _count_from_payload(coverage.get("warned_optional_stage_count")),
        "warned_optional_stages": _public_llm_stage_ids(coverage.get("warned_optional_stages", [])),
        "input_tokens_estimated": _count_from_payload(tokens.get("input_tokens_estimated")),
        "output_tokens_estimated": _count_from_payload(tokens.get("output_tokens_estimated")),
        "estimated_cost_usd": tokens.get("estimated_cost_usd"),
        "total_duration_seconds": _float_from_payload(tokens.get("total_duration_seconds")),
        "call_utilization": _float_from_payload(budget.get("call_utilization")),
        "prompt_utilization": _float_from_payload(budget.get("prompt_utilization")),
        "manifest_events": _count_from_payload(traceability.get("manifest_events")),
        "manifest_artifacts": _count_from_payload(traceability.get("manifest_artifacts")),
        "experiment_runs": _count_from_payload(traceability.get("experiment_runs")),
        "repair_queue_status": traceability.get("repair_queue_status", ""),
        "blocking_issue_count": _count_list(data.get("blocking_issues")),
        "manual_task_count": _count_list(data.get("manual_tasks")),
        "warning_count": _count_list(data.get("warnings")),
        "recommended_action_count": _count_list(data.get("recommended_actions")),
    }


def _read_public_llm_runtime_contract(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / LLM_RUNTIME_CONTRACT_JSON)
    if not data:
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "provider": summary.get("provider", ""),
        "model_configured": summary.get("model_configured") is True,
        "base_url_configured": summary.get("base_url_configured") is True,
        "api_key_persisted": summary.get("api_key_persisted") is True,
        "call_budget_configured": summary.get("call_budget_configured") is True,
        "prompt_budget_configured": summary.get("prompt_budget_configured") is True,
        "pricing_configured": summary.get("pricing_configured") is True,
        "total_calls": _count_from_payload(summary.get("total_calls")),
        "successful_calls": _count_from_payload(summary.get("successful_calls")),
        "failed_calls": _count_from_payload(summary.get("failed_calls")),
        "budget_exceeded_calls": _count_from_payload(summary.get("budget_exceeded_calls")),
        "entries": _count_from_payload(summary.get("entries")),
        "trace_status": summary.get("trace_status", ""),
        "economics_status": summary.get("economics_status", ""),
        "ai_disclosure_status": summary.get("ai_disclosure_status", ""),
        "check_count": _count_list(data.get("checks")),
        "blocking_issue_count": _count_list(data.get("blocking_issues")),
        "manual_task_count": _count_list(data.get("manual_tasks")),
        "warning_count": _count_list(data.get("warnings")),
        "recommended_action_count": _count_list(data.get("recommended_actions")),
    }


def _read_public_repair_resume_plan(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / REPAIR_RESUME_PLAN_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _public_repair_resume_summary(data, include_cleanup_paths=False)


def _record_has_active_repair_queue(record: dict[str, Any]) -> bool:
    repair_queue = record.get("repair_queue") if isinstance(record.get("repair_queue"), dict) else {}
    return repair_queue.get("status") in ACTIVE_REPAIR_QUEUE_STATUSES


def _record_has_resume_repair_plan(record: dict[str, Any]) -> bool:
    plan = record.get("repair_resume_plan") if isinstance(record.get("repair_resume_plan"), dict) else {}
    return plan.get("can_resume") is True and str(plan.get("status") or "") == "ready_to_resume_repair"


def _record_can_repair_resume(record: dict[str, Any]) -> bool:
    return _record_has_active_repair_queue(record) or _record_has_resume_repair_plan(record)


def _repair_resume_gold_verification_report_path(out_dir: Path) -> Path | None:
    plan = _read_json_dict(out_dir / REPAIR_RESUME_PLAN_JSON)
    path_text = str(plan.get("gold_verification_report_path") or "").strip()
    candidates: list[Path] = []
    if path_text:
        raw = Path(path_text)
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.extend([ROOT / raw, out_dir / raw])
    if "gold-run-verification" in _list_from_payload(plan.get("repair_plan_sources")):
        candidates.append(out_dir / GOLD_RUN_VERIFICATION_JSON)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if _is_safe_existing_path(resolved, out_dir):
            return resolved
    return None


def _read_public_repair_resume_artifact(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / REPAIR_RESUME_PLAN_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return _public_repair_resume_preview(data)


def _read_public_gold_run_doctor(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / GOLD_RUN_DOCTOR_JSON)
    if not data:
        return None
    return _public_gold_run_doctor_report(data)


def _read_public_gold_run_verification(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / GOLD_RUN_VERIFICATION_JSON)
    if not data:
        return None
    return _public_gold_run_verification_report(data, fallback_run_id=out_dir.name)


def _read_public_gold_post_launch(out_dir: Path) -> dict[str, Any] | None:
    if not (out_dir / GOLD_LAUNCH_BUNDLE_JSON).exists():
        return None
    verification = _read_public_gold_run_verification(out_dir)
    if verification is None:
        return None
    repair_plan = _read_public_repair_resume_plan(out_dir)
    verification_artifacts = [
        name for name in (GOLD_RUN_VERIFICATION_JSON, GOLD_RUN_VERIFICATION_MD) if (out_dir / name).exists()
    ]
    repair_plan_artifacts = [
        name for name in (REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD) if (out_dir / name).exists()
    ]
    readiness_artifacts = [
        name for name in (PERFECT_AGENT_READINESS_JSON, PERFECT_AGENT_READINESS_MD) if (ROOT / name).exists()
    ]
    return {
        "status": str(verification.get("status") or ""),
        "candidate_run_id": str(verification.get("candidate_run_id") or out_dir.name),
        "gold_contract_ready": verification.get("gold_contract_ready") is True,
        "verification_status": str(verification.get("status") or ""),
        "verification_artifacts": verification_artifacts,
        "verification_artifact_count": len(verification_artifacts),
        "repair_resume_plan_written": repair_plan is not None,
        "repair_resume_plan_status": str(repair_plan.get("status") or "") if isinstance(repair_plan, dict) else "",
        "repair_resume_plan_artifacts": repair_plan_artifacts,
        "repair_resume_plan_artifact_count": len(repair_plan_artifacts),
        "perfect_readiness_artifacts": readiness_artifacts,
        "perfect_readiness_artifact_count": len(readiness_artifacts),
    }


def _read_public_gold_launch_bundle(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / GOLD_LAUNCH_BUNDLE_JSON)
    if not data:
        return None
    return _public_gold_launch_bundle_report(data)


def _read_public_gold_launch_manifest(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / GOLD_LAUNCH_MANIFEST_JSON)
    if not data:
        doctor = _read_json_dict(out_dir / GOLD_RUN_DOCTOR_JSON)
        data = doctor.get("launch_manifest") if isinstance(doctor.get("launch_manifest"), dict) else {}
    if not data:
        return None
    return _public_gold_launch_manifest_report(data)


def _public_gold_run_doctor_report(data: dict[str, Any]) -> dict[str, Any]:
    checks = [item for item in (data.get("checks") if isinstance(data.get("checks"), list) else []) if isinstance(item, dict)]
    preflight = [item for item in (data.get("preflight") if isinstance(data.get("preflight"), list) else []) if isinstance(item, dict)]
    candidate = next((item for item in checks if item.get("name") == "candidate_gold_run"), {})
    repair_plan = candidate.get("repair_plan") if isinstance(candidate, dict) and isinstance(candidate.get("repair_plan"), list) else []
    resume_plan = data.get("candidate_repair_resume_plan") if isinstance(data.get("candidate_repair_resume_plan"), dict) else {}
    launch = data.get("launch_manifest") if isinstance(data.get("launch_manifest"), dict) else {}
    launch_checklist = [item for item in (launch.get("launch_checklist") if isinstance(launch.get("launch_checklist"), list) else []) if isinstance(item, dict)]
    public_launch_checklist = _public_launch_checklist(launch_checklist)
    public_launch_readiness = _public_launch_readiness(launch.get("launch_readiness"), public_launch_checklist)
    return {
        "schema_version": data.get("schema_version", 1),
        "topic": data.get("topic", ""),
        "status": data.get("status", ""),
        "preflight_status": data.get("preflight_status", ""),
        "launch_status": str(launch.get("status") or ""),
        "can_start_gold_run": launch.get("can_start_gold_run") is True,
        "launch_readiness": public_launch_readiness,
        "launch_check_status_counts": _status_counts(launch_checklist),
        "launch_checklist": public_launch_checklist,
        "launch_next_steps": _public_launch_next_steps(public_launch_checklist),
        "checks": len(checks),
        "check_status_counts": _status_counts(checks),
        "failed_checks": _public_check_names(checks, "fail"),
        "warn_checks": _public_check_names(checks, "warn"),
        "preflight_checks": len(preflight),
        "preflight_status_counts": _status_counts(preflight),
        "failed_preflight_checks": _public_check_names(preflight, "fail"),
        "warn_preflight_checks": _public_check_names(preflight, "warn"),
        "candidate_gold_run_status": str(candidate.get("status") or "") if isinstance(candidate, dict) else "",
        "candidate_repair_plan_items": len(repair_plan),
        "candidate_repair_plan": _public_candidate_repair_plan(repair_plan),
        "candidate_repair_resume_plan": _public_candidate_repair_resume_plan(resume_plan),
        "command_count": len(data.get("commands", [])) if isinstance(data.get("commands"), list) else 0,
    }


def _public_gold_run_verification_report(data: dict[str, Any], *, fallback_run_id: str = "") -> dict[str, Any]:
    check = data.get("check") if isinstance(data.get("check"), dict) else {}
    evidence = data.get("contract_evidence") if isinstance(data.get("contract_evidence"), dict) else {}
    repair_plan = data.get("repair_plan") if isinstance(data.get("repair_plan"), list) else []
    required = _list_from_payload(data.get("required_artifacts"))
    missing = _list_from_payload(data.get("missing_artifacts"))
    unsafe_artifacts = _public_gold_unsafe_artifacts(data.get("unsafe_artifacts"))
    artifact_safety = data.get("artifact_safety") if isinstance(data.get("artifact_safety"), dict) else {}
    manifest_inventory = data.get("manifest_inventory") if isinstance(data.get("manifest_inventory"), dict) else {}
    secret_scan = data.get("secret_scan") if isinstance(data.get("secret_scan"), dict) else {}
    candidate_run_id = _path_name(data.get("run_dir")) or fallback_run_id
    check_status = str(check.get("status") or "")
    return {
        "schema_version": data.get("schema_version", 1),
        "status": str(data.get("status") or ""),
        "gold_contract_ready": data.get("gold_contract_ready") is True,
        "candidate_run_id": candidate_run_id,
        "read_only": data.get("read_only") is True,
        "check_status": check_status,
        "required_artifacts": required,
        "required_artifact_count": len(required),
        "missing_artifacts": missing,
        "missing_artifact_count": len(missing),
        "artifact_safety_status": str(artifact_safety.get("status") or ""),
        "unsafe_artifact_count": len(unsafe_artifacts),
        "unsafe_artifacts": unsafe_artifacts,
        "manifest_inventory_status": str(manifest_inventory.get("status") or ""),
        "manifest_inventory_missing_count": len(_list_from_payload(manifest_inventory.get("missing_required_artifacts"))),
        "manifest_inventory_hash_mismatch_count": len(_list_from_payload(manifest_inventory.get("hash_mismatches"))),
        "manifest_inventory_size_mismatch_count": len(_list_from_payload(manifest_inventory.get("size_mismatches"))),
        "manifest_inventory_duplicate_count": len(_list_from_payload(manifest_inventory.get("duplicate_required_artifacts"))),
        "manifest_inventory_unsafe_path_count": len(_list_from_payload(manifest_inventory.get("unsafe_artifact_paths"))),
        "audit_contracts_ready": evidence.get("audit_contracts_ready") is True,
        "audit_contract_ready_count": _count_from_payload(evidence.get("audit_contract_ready_count")),
        "audit_contract_total": _count_from_payload(evidence.get("audit_contract_total")),
        "audit_contract_blocking_issues": _count_from_payload(evidence.get("audit_contract_blocking_issues")),
        "audit_contract_manual_tasks": _count_from_payload(evidence.get("audit_contract_manual_tasks")),
        "audit_contracts": _public_gold_audit_contracts(evidence.get("audit_contracts")),
        "secret_scan_status": str(secret_scan.get("status") or ""),
        "secret_scan_findings": _count_from_payload(secret_scan.get("finding_count")),
        "secret_scan_scanned_files": _count_from_payload(secret_scan.get("scanned_files")),
        "secret_scan_paths": _public_secret_scan_paths(secret_scan.get("findings")),
        "repair_plan_items": len(repair_plan),
        "repair_plan": _public_candidate_repair_plan(repair_plan),
    }


def _public_gold_unsafe_artifacts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    public: list[dict[str, str]] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        path = _public_artifact_path(item.get("path"))
        issue = _public_artifact_issue(item.get("issue"))
        if path:
            public.append({"path": path, "issue": issue})
    return public


def _public_artifact_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    return "/".join(parts[-3:])


def _public_artifact_issue(value: Any) -> str:
    issue = str(value or "")
    return issue if issue in {"symlink", "not_file", "path_escape", "unreadable"} else "other" if issue else ""


def _public_gold_audit_contracts(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "llm_trace",
        "llm_runtime",
        "run_economics",
        "agent_observability",
        "llm_observability",
        "stage_contract",
        "trajectory",
    }
    return {
        key: {
            "status": _public_gold_audit_status(item.get("status")),
            "blocking_issues": _count_from_payload(item.get("blocking_issues")),
            "manual_tasks": _count_from_payload(item.get("manual_tasks")),
            "ready": item.get("ready") is True,
        }
        for key, item in value.items()
        if key in allowed and isinstance(item, dict)
    }


def _public_gold_audit_status(value: Any) -> str:
    status = str(value or "")
    return status if status in {"pass", "block", "warn", "review_required", "needs_human_review", "missing"} else "other" if status else ""


def _public_gold_launch_bundle_report(data: dict[str, Any]) -> dict[str, Any]:
    components = [item for item in (data.get("components") if isinstance(data.get("components"), list) else []) if isinstance(item, dict)]
    launch_plan = data.get("launch_plan") if isinstance(data.get("launch_plan"), dict) else {}
    repair_plan = data.get("repair_plan") if isinstance(data.get("repair_plan"), list) else []
    focus = data.get("prelaunch_focus") if isinstance(data.get("prelaunch_focus"), dict) else {}
    return {
        "schema_version": data.get("schema_version", 1),
        "topic": str(data.get("topic") or ""),
        "status": str(data.get("status") or ""),
        "can_start_gold_run": data.get("can_start_gold_run") is True,
        "component_status_counts": _status_counts(components),
        "blocked_components": _public_check_names(components, "block"),
        "review_components": _public_check_names(components, "review"),
        "warn_components": _public_check_names(components, "warn"),
        "prelaunch_focus": _public_gold_bundle_prelaunch_focus(focus),
        "next_steps": _list_from_payload(data.get("next_steps"))[:12],
        "repair_plan_items": len(repair_plan),
        "repair_plan": _public_gold_bundle_repair_plan(repair_plan),
        "launch_plan_status": str(launch_plan.get("status") or ""),
        "ready_to_execute_commands": launch_plan.get("ready_to_execute_commands") is True,
        "secret_policy": str(launch_plan.get("secret_policy") or ""),
        "required_environment": _list_from_payload(launch_plan.get("required_environment"))[:8],
        "required_human_gates": _list_from_payload(launch_plan.get("required_human_gates"))[:8],
        "required_final_evidence": _count_list(launch_plan.get("required_final_evidence")),
    }


def _public_secret_scan_paths(value: Any) -> list[str]:
    paths: list[str] = []
    items = value if isinstance(value, list) else []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path or path.startswith("/") or ".." in Path(path).parts:
            continue
        paths.append(path)
    return _unique_strings(paths)[:20]


def _public_gold_launch_manifest_report(data: dict[str, Any]) -> dict[str, Any]:
    checklist = [item for item in (data.get("launch_checklist") if isinstance(data.get("launch_checklist"), list) else []) if isinstance(item, dict)]
    public_checklist = _public_launch_checklist(checklist)
    literature = data.get("literature") if isinstance(data.get("literature"), dict) else {}
    benchmark = data.get("benchmark") if isinstance(data.get("benchmark"), dict) else {}
    fulltext = data.get("fulltext_grounding") if isinstance(data.get("fulltext_grounding"), dict) else {}
    candidate = data.get("candidate_run") if isinstance(data.get("candidate_run"), dict) else {}
    release = data.get("release_metadata") if isinstance(data.get("release_metadata"), dict) else {}
    secret = data.get("secret_handling") if isinstance(data.get("secret_handling"), dict) else {}
    return {
        "schema_version": data.get("schema_version", 1),
        "topic": data.get("topic", ""),
        "status": data.get("status", ""),
        "can_start_gold_run": data.get("can_start_gold_run") is True,
        "launch_readiness": _public_launch_readiness(data.get("launch_readiness"), public_checklist),
        "doctor_status": data.get("doctor_status", ""),
        "preflight_status": data.get("preflight_status", ""),
        "check_status_counts": _public_status_count_dict(data.get("check_status_counts")),
        "failed_checks": _list_from_payload(data.get("failed_checks"))[:12],
        "warn_checks": _list_from_payload(data.get("warn_checks"))[:12],
        "launch_check_status_counts": _status_counts(checklist),
        "launch_checklist": public_checklist,
        "launch_next_steps": _public_launch_next_steps(public_checklist),
        "blocking_launch_items": _public_check_names(checklist, "block"),
        "warn_launch_items": _public_check_names(checklist, "warn"),
        "secrets_in_config": secret.get("secrets_in_config") is True,
        "direct_secret_fields": _list_from_payload(secret.get("direct_secret_fields"))[:8],
        "literature_provider": literature.get("provider", ""),
        "literature_sources": _list_from_payload(literature.get("sources"))[:8],
        "literature_source_count": _count_from_payload(literature.get("source_count")),
        "min_literature_sources": _count_from_payload(literature.get("min_literature_sources")),
        "seed_papers": _count_from_payload(literature.get("seed_papers")),
        "min_seed_papers": _count_from_payload(literature.get("min_seed_papers")),
        "doi_url_seed_papers": _count_from_payload(literature.get("doi_url_seed_papers")),
        "min_doi_url_seed_papers": _count_from_payload(literature.get("min_doi_url_seed_papers")),
        "fulltext_paths": _count_from_payload(literature.get("fulltext_paths")),
        "paper_grade_literature_ready": literature.get("paper_grade_ready") is True,
        "execution_mode": benchmark.get("execution_mode", ""),
        "execution_repeats": _count_from_payload(benchmark.get("execution_repeats")),
        "benchmark_manifest_paths": _count_from_payload(benchmark.get("benchmark_manifest_paths")),
        "benchmark_ready": benchmark.get("benchmark_ready") is True,
        "benchmark_pack_run_id": _path_name(benchmark.get("standalone_pack_run_id")),
        "fulltext_grounding_run_id": _path_name(fulltext.get("standalone_run_id")),
        "candidate_run_id": _path_name(candidate.get("run_id")),
        "release_required_ready": release.get("required_ready") is True,
        "release_missing_required_fields": _list_from_payload(release.get("missing_required_fields"))[:12],
        "release_invalid_required_fields": _list_from_payload(release.get("invalid_required_fields"))[:12],
        "release_placeholder_required_fields": _list_from_payload(release.get("placeholder_required_fields"))[:12],
        "required_human_gates": _list_from_payload(data.get("required_human_gates"))[:8],
        "required_final_evidence": _count_list(data.get("required_final_evidence")),
        "command_count": _count_list(data.get("safe_commands")),
    }


def _public_launch_readiness(value: Any, checklist: list[dict[str, Any]]) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    blocking = _list_from_payload(data.get("blocking_items"))[:12]
    review = _list_from_payload(data.get("review_items"))[:12]
    if not blocking:
        blocking = [str(item.get("item") or "") for item in checklist if str(item.get("status") or "") in {"block", "fail"} and str(item.get("item") or "")]
    if not review:
        review = [str(item.get("item") or "") for item in checklist if str(item.get("status") or "") == "warn" and str(item.get("item") or "")]
    status = str(data.get("status") or "")
    if status not in {"ready_to_start", "blocked", "needs_review"}:
        status = "blocked" if blocking else "needs_review" if review else "ready_to_start"
    secret_policy = str(data.get("secret_policy") or "")
    if secret_policy not in {"env_only", "move_secrets_to_env"}:
        secret_policy = "env_only"
    return {
        "schema_version": data.get("schema_version", 1),
        "status": status,
        "can_start_gold_run": data.get("can_start_gold_run") is True,
        "blocking_items": blocking,
        "review_items": review,
        "required_before_start": _list_from_payload(data.get("required_before_start"))[:12],
        "review_before_start": _list_from_payload(data.get("review_before_start"))[:12],
        "secret_policy": secret_policy,
        "safe_launch_command_count": _count_from_payload(data.get("safe_launch_command_count")),
    }


def _public_launch_checklist(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for raw in items[:12]:
        item = str(raw.get("item") or raw.get("name") or raw.get("id") or "").strip()
        if not item:
            continue
        status = str(raw.get("status") or "").strip()
        public.append(
            {
                "item": item,
                "status": status if status in {"pass", "warn", "block", "fail"} else "other",
                "button": _gold_launch_button_hint(item),
                "form_fields": _gold_launch_form_fields(item),
                "next_step": _gold_launch_next_step(item),
            }
        )
    return public


def _public_launch_next_steps(items: list[dict[str, Any]]) -> list[str]:
    steps: list[str] = []
    for item in items:
        status = str(item.get("status") or "")
        if status == "pass":
            continue
        name = str(item.get("item") or "")
        button = str(item.get("button") or "")
        next_step = str(item.get("next_step") or "")
        parts = [f"{name}={status}"]
        if button:
            parts.append(f"button={button}")
        if next_step:
            parts.append(next_step)
        steps.append("; ".join(parts))
    return steps[:12]


def _gold_launch_button_hint(item: str) -> str:
    return {
        "doctor_ready": "Gold Doctor",
        "preflight_pass": "预检配置",
        "secrets_via_environment": "server environment",
        "paper_grade_literature": "预览文献",
        "benchmark_manifest": "校验 Benchmark",
        "release_metadata": "Release metadata fields",
        "candidate_run_optional": "current run",
    }.get(item, "Gold Doctor")


def _gold_launch_form_fields(item: str) -> list[str]:
    return {
        "doctor_ready": [],
        "preflight_pass": [],
        "secrets_via_environment": ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"],
        "paper_grade_literature": [
            "literature_provider",
            "literature_sources",
            "seed_papers",
            "fulltext_paths",
            "max_papers",
            "max_search_queries",
            "extra_search_queries",
        ],
        "benchmark_manifest": ["execution_mode", "execution_repeats", "benchmark_manifests"],
        "release_metadata": [
            "release_code_repository_url",
            "release_code_archive_doi",
            "release_code_license",
            "release_code_version",
            "release_data_access_statement",
            "release_environment_url",
        ],
        "candidate_run_optional": ["candidate_run_id"],
    }.get(item, [])


def _gold_launch_next_step(item: str) -> str:
    return {
        "doctor_ready": "Resolve failed Gold Doctor checks, then rerun Gold Doctor.",
        "preflight_pass": "Run Preflight and fix failed preflight checks before launch.",
        "secrets_via_environment": "Move secret values to environment variables before a real run; leave Web/config secret fields empty.",
        "paper_grade_literature": "Use online/auto literature with source and DOI/URL seed counts meeting paper_grade thresholds; run Literature Preview.",
        "benchmark_manifest": "Use benchmark execution with repeats and candidate/baseline/ablation manifest counts meeting paper_grade thresholds; run Benchmark Preview.",
        "release_metadata": "Fill real release metadata: code repository/archive, license, version, data access statement, and environment URL.",
        "candidate_run_optional": "Optional before launch; after a candidate run finishes, rerun Gold Doctor against that run for final gold evidence.",
    }.get(item, "Review this launch checklist item and rerun Gold Doctor.")


def _live_gold_launch_commands(data: dict[str, Any]) -> list[str]:
    commands = data.get("commands") if isinstance(data.get("commands"), list) else []
    safe: list[str] = []
    for raw in commands:
        command = str(raw or "").strip()
        if not command or _command_has_secret_shape(command):
            continue
        safe.append(_redact_command_secret_shapes(command))
    return safe[:8]


def _command_has_secret_shape(command: str) -> bool:
    if command.startswith("export "):
        return True
    secret_patterns = [
        r"(?i)\b(?:OPENAI_API_KEY|SEMANTIC_SCHOLAR_API_KEY|OPENALEX_API_KEY)\b",
        r"(?i)--(?:llm-api-key|semantic-scholar-api-key|openalex-api-key)(?:=|\s+)",
        r"(?i)\b(?:api_key|llm_api_key|semantic_scholar_api_key|openalex_api_key)\s*=",
        r"(?i)\b(?:bearer|token|x-api-key)=\S+",
        r"sk-[A-Za-z0-9_-]{8,}",
    ]
    return any(re.search(pattern, command) for pattern in secret_patterns)


def _redact_command_secret_shapes(command: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-<redacted>", command)


def _render_live_gold_launch_commands_markdown(commands: list[str]) -> str:
    if not commands:
        return ""
    lines = [
        "## Safe Launch Commands",
        "",
        "Set the required credentials in your shell first; these commands intentionally omit secret export lines.",
        "",
        "```bash",
        *commands,
        "```",
    ]
    return "\n".join(lines)


def _candidate_run_dir_from_payload(payload: dict[str, Any]) -> Path | None:
    run_id = str(payload.get("candidate_run_id") or "").strip()
    if run_id:
        out_dir = STORE.out_dir(run_id)
        if out_dir is None:
            raise ValueError("candidate_run_id must reference an existing run")
        return out_dir
    return _payload_existing_path(payload, "candidate_run_dir")


def _payload_existing_path(payload: dict[str, Any], key: str) -> Path | None:
    value = str(payload.get(key) or "").strip()
    if not value:
        return None
    raw = Path(value)
    path = raw if raw.is_absolute() else ROOT / raw
    path = path.resolve()
    if not _is_safe_existing_path(path, ROOT):
        raise ValueError(f"{key} must be an existing path under the project root")
    return path


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "review": 0, "fail": 0, "block": 0, "other": 0}
    for item in items:
        status = str(item.get("status") or "").strip()
        if status in counts:
            counts[status] += 1
        elif status:
            counts["other"] += 1
    return {key: value for key, value in counts.items() if value}


def _public_gold_bundle_repair_plan(items: list[Any]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        public.append(
            {
                "id": str(item.get("id") or ""),
                "component": str(item.get("component") or ""),
                "status": str(item.get("status") or ""),
                "priority": _count_from_payload(item.get("priority")),
                "button": str(item.get("button") or ""),
                "form_fields": _list_from_payload(item.get("form_fields"))[:12],
                "next_step": str(item.get("next_step") or ""),
                "cli_hint": str(item.get("cli_hint") or ""),
                "evidence": str(item.get("evidence") or ""),
            }
        )
    return public


def _public_gold_bundle_prelaunch_focus(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    category = str(data.get("category") or "")
    allowed_categories = {"ready", "server_environment", "literature", "benchmark_manifest", "release_metadata", "doctor_or_final_evidence"}
    return {
        "category": category if category in allowed_categories else "doctor_or_final_evidence",
        "blocking_components": _list_from_payload(data.get("blocking_components"))[:12],
        "ready_except_server_environment": data.get("ready_except_server_environment") is True,
        "server_environment_refresh_required": data.get("server_environment_refresh_required") is True,
        "form_fields": [
            field
            for field in _list_from_payload(data.get("form_fields"))[:12]
            if re.fullmatch(r"[A-Za-z0-9_]+", field)
        ],
        "next_action": str(data.get("next_action") or "")[:260],
    }


def _public_status_count_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    allowed = {"pass", "warn", "fail", "block", "other", "ready", "blocked", "needs_review", "ready_to_start"}
    return {str(key): _count_from_payload(item) for key, item in value.items() if str(key) in allowed}


def _public_check_names(items: list[dict[str, Any]], status: str) -> list[str]:
    names: list[str] = []
    for item in items:
        if str(item.get("status") or "") != status:
            continue
        name = str(item.get("name") or item.get("id") or item.get("item") or "").strip()
        if name:
            names.append(name)
    return names[:12]


def _public_candidate_repair_plan(items: list[Any]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for item in items[:12]:
        if not isinstance(item, dict):
            continue
        public.append(
            {
                "id": str(item.get("id") or ""),
                "priority": _count_from_payload(item.get("priority")),
                "rerun_from": str(item.get("rerun_from") or ""),
                "source_artifact": str(item.get("source_artifact") or ""),
                "target_artifacts": _list_from_payload(item.get("target_artifacts"))[:12],
            }
        )
    return public


def _public_candidate_repair_resume_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not plan:
        return {}
    return {
        "status": str(plan.get("status") or ""),
        "candidate_run_id": _path_name(plan.get("candidate_run_dir")),
        "can_resume": plan.get("can_resume") is True,
        "rerun_from": str(plan.get("rerun_from") or ""),
        "repair_items": _count_from_payload(plan.get("repair_items")),
        "plan_json": _path_name(plan.get("plan_json")),
        "plan_md": _path_name(plan.get("plan_md")),
    }


def _path_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return Path(text).name


def _public_repair_resume_preview(report: dict[str, Any]) -> dict[str, Any]:
    return _public_repair_resume_summary(report, include_cleanup_paths=True)


def _public_repair_resume_summary(report: dict[str, Any], *, include_cleanup_paths: bool) -> dict[str, Any]:
    recommended = report.get("recommended_config") if isinstance(report.get("recommended_config"), dict) else {}
    recommended_execution = report.get("recommended_execution_config") if isinstance(report.get("recommended_execution_config"), dict) else {}
    recommended_paper_grade = report.get("recommended_paper_grade_config") if isinstance(report.get("recommended_paper_grade_config"), dict) else {}
    recommended_release = report.get("recommended_release_config") if isinstance(report.get("recommended_release_config"), dict) else {}
    artifacts_to_remove = _list_from_payload(report.get("artifacts_to_remove", []))
    directories_to_remove = _list_from_payload(report.get("directories_to_remove", []))
    summary = {
        "schema_version": report.get("schema_version", 1),
        "topic": report.get("topic", ""),
        "status": report.get("status", ""),
        "applied": report.get("applied") is True,
        "can_resume": report.get("can_resume") is True,
        "queue_status": report.get("queue_status", ""),
        "repair_plan_sources": _list_from_payload(report.get("repair_plan_sources", [])),
        "rerun_from": report.get("rerun_from", ""),
        "repair_items": len(report.get("repair_items", [])) if isinstance(report.get("repair_items"), list) else 0,
        "retrieval_repair_tasks": len(report.get("retrieval_repair_tasks", [])) if isinstance(report.get("retrieval_repair_tasks"), list) else 0,
        "manager_resume_action_count": len(report.get("experiment_manager_resume_actions", [])) if isinstance(report.get("experiment_manager_resume_actions"), list) else 0,
        "recommended_seed_paper_count": len(report.get("recommended_seed_papers", [])) if isinstance(report.get("recommended_seed_papers"), list) else 0,
        "recommended_config": {
            "literature_provider": recommended.get("literature_provider", ""),
            "sources": _list_from_payload(recommended.get("sources", [])),
            "max_papers": recommended.get("max_papers", 0),
            "max_search_queries": recommended.get("max_search_queries", 0),
        },
        "recommended_execution_config": {
            "execution_mode": recommended_execution.get("execution_mode", ""),
            "allowed_commands": _list_from_payload(recommended_execution.get("allowed_commands", [])),
            "execution_repeats": recommended_execution.get("execution_repeats", 0),
            "timeout_seconds": recommended_execution.get("timeout_seconds", 0),
            "benchmark_manifest_paths": _list_from_payload(recommended_execution.get("benchmark_manifest_paths", [])),
        },
        "recommended_paper_grade_config": {
            "enabled": recommended_paper_grade.get("enabled") is True,
            "trigger_count": max(_count_list(recommended_paper_grade.get("reasons")), _count_from_payload(recommended_paper_grade.get("trigger_count"))),
        },
        "recommended_release_config": {
            "status": str(recommended_release.get("status") or ""),
            "required_fields": _list_from_payload(recommended_release.get("required_fields", [])),
            "recommended_fields": _list_from_payload(recommended_release.get("recommended_fields", [])),
            "cli_args": _list_from_payload(recommended_release.get("cli_args", [])),
            "config_fields": _public_release_config_fields(recommended_release),
        },
        "review_reapproval_required": report.get("review_reapproval_required") is True,
        "execution_reapproval_required": report.get("execution_reapproval_required") is True,
        "artifacts_to_remove": artifacts_to_remove if include_cleanup_paths else len(artifacts_to_remove),
        "directories_to_remove": directories_to_remove if include_cleanup_paths else len(directories_to_remove),
        "removed_artifacts": len(report.get("removed_artifacts", [])) if isinstance(report.get("removed_artifacts"), list) else 0,
        "removed_directories": len(report.get("removed_directories", [])) if isinstance(report.get("removed_directories"), list) else 0,
        "stop_conditions": len(report.get("stop_conditions", [])) if isinstance(report.get("stop_conditions"), list) else 0,
    }
    return summary


def _public_release_config_fields(recommended_release: dict[str, Any]) -> dict[str, str]:
    allowed = {
        "code_repository_url",
        "code_archive_doi",
        "code_license",
        "code_version",
        "data_repository_url",
        "data_archive_doi",
        "data_access_statement",
        "environment_url",
        "release_notes",
    }
    config_fields = recommended_release.get("config_fields") if isinstance(recommended_release.get("config_fields"), dict) else {}
    return {
        str(key): str(value).strip()
        for key, value in config_fields.items()
        if str(key) in allowed and str(value or "").strip()
    }


def _read_public_repair_resolution(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / REPAIR_RESOLUTION_AUDIT_JSON)
    if not data:
        return None
    return {
        "status": data.get("status", ""),
        "applied": data.get("applied") is True,
        "rerun_from": data.get("rerun_from", ""),
        "queue_status": data.get("queue_status", ""),
        "resolution_score": _float_from_payload(data.get("resolution_score")),
        "original_items": _count_list(data.get("original_items")),
        "remaining_items": _count_list(data.get("remaining_items")),
        "resolved_items": _count_list(data.get("resolved_items")),
        "new_items": _count_list(data.get("new_items")),
        "blocking_issue_count": _count_list(data.get("blocking_issues")),
        "manual_task_count": _count_list(data.get("manual_tasks")),
        "required_action_count": _count_list(data.get("required_actions")),
    }


def _render_public_repair_resume_preview_markdown(plan: dict[str, Any]) -> str:
    recommended = plan.get("recommended_config") if isinstance(plan.get("recommended_config"), dict) else {}
    recommended_execution = plan.get("recommended_execution_config") if isinstance(plan.get("recommended_execution_config"), dict) else {}
    recommended_paper_grade = plan.get("recommended_paper_grade_config") if isinstance(plan.get("recommended_paper_grade_config"), dict) else {}
    recommended_release = plan.get("recommended_release_config") if isinstance(plan.get("recommended_release_config"), dict) else {}
    artifacts = plan.get("artifacts_to_remove") if isinstance(plan.get("artifacts_to_remove"), list) else []
    directories = plan.get("directories_to_remove") if isinstance(plan.get("directories_to_remove"), list) else []
    manifests = _list_from_payload(recommended_execution.get("benchmark_manifest_paths", []))
    lines = [
        f"# 修复恢复预览：{plan.get('topic') or ''}",
        "",
        f"- 状态：{plan.get('status') or '-'}",
        f"- 可恢复：{'是' if plan.get('can_resume') else '否'}",
        f"- 队列状态：{plan.get('queue_status') or '-'}",
        f"- 重跑入口：{plan.get('rerun_from') or '-'}",
        f"- 修复任务：{plan.get('repair_items', 0)}",
        f"- 检索修复任务：{plan.get('retrieval_repair_tasks', 0)}",
        f"- Experiment Manager 恢复动作：{plan.get('manager_resume_action_count', 0)}",
        f"- 推荐 seed papers：{plan.get('recommended_seed_paper_count', 0)}",
        f"- 文献重新批准：{'需要' if plan.get('review_reapproval_required') else '不需要'}",
        f"- 执行重新批准：{'需要' if plan.get('execution_reapproval_required') else '不需要'}",
        "",
        "## 推荐配置摘要",
        f"- literature_provider：`{recommended.get('literature_provider') or '-'}`",
        f"- sources：`{', '.join(_list_from_payload(recommended.get('sources', []))) or '-'}`",
        f"- max_papers：`{recommended.get('max_papers') or '-'}`",
        f"- max_search_queries：`{recommended.get('max_search_queries') or '-'}`",
        f"- execution_mode：`{recommended_execution.get('execution_mode') or '-'}`",
        f"- allowed_commands：`{', '.join(_list_from_payload(recommended_execution.get('allowed_commands', []))) or '-'}`",
        f"- execution_repeats：`{recommended_execution.get('execution_repeats') or '-'}`",
        f"- timeout_seconds：`{recommended_execution.get('timeout_seconds') or '-'}`",
        f"- benchmark manifests：`{', '.join(manifests) or '-'}`",
        f"- paper_grade_enabled：`{recommended_paper_grade.get('enabled') is True}`",
        f"- release_required_fields：`{', '.join(_list_from_payload(recommended_release.get('required_fields', []))) or '-'}`",
        f"- release_cli_args：`{', '.join(_list_from_payload(recommended_release.get('cli_args', []))) or '-'}`",
        "",
        "## 将清理的产物",
    ]
    lines.extend(f"- `{item}`" for item in artifacts[:40]) if artifacts else lines.append("- 无")
    lines.extend(["", "## 将清理的目录"])
    lines.extend(f"- `{item}`" for item in directories[:20]) if directories else lines.append("- 无")
    return "\n".join(lines)


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_public_literature_retrieval_gate(out_dir: Path) -> dict[str, Any] | None:
    source_health = _read_json_dict(out_dir / LITERATURE_SOURCE_HEALTH_JSON)
    query_audit = _read_json_dict(out_dir / QUERY_EXECUTION_AUDIT_JSON)
    rerank = _read_json_dict(out_dir / LITERATURE_RERANK_JSON)
    coverage = _read_json_dict(out_dir / LITERATURE_COVERAGE_JSON)
    evidence_mix = _read_json_dict(out_dir / LITERATURE_EVIDENCE_MIX_JSON)
    if not any([source_health, query_audit, rerank, coverage, evidence_mix]):
        return _read_public_legacy_literature_retrieval_gate(out_dir)

    source_coverage = query_audit.get("source_coverage") if isinstance(query_audit.get("source_coverage"), dict) else {}
    top_coverage = query_audit.get("top_rerank_coverage") if isinstance(query_audit.get("top_rerank_coverage"), dict) else {}
    intent_coverage = query_audit.get("intent_coverage") if isinstance(query_audit.get("intent_coverage"), dict) else {}
    sources = source_health.get("sources") if isinstance(source_health.get("sources"), list) else []
    rate_limited_sources = _source_names_by_status(sources, {"rate_limited"}, rate_limited=True)
    failed_sources = _source_names_by_status(sources, {"failed"})
    query_status = str(query_audit.get("status") or "")
    rerank_status = str(rerank.get("status") or "")
    coverage_status = str(coverage.get("status") or "")
    mix_status = str(evidence_mix.get("status") or "")
    blocking = 0
    review = 0
    statuses = [query_status, rerank_status, coverage_status, mix_status]
    for status in statuses:
        if status in {"block", "blocked", "failed", "error", "needs_source_repair"}:
            blocking += 1
        elif status in {"review", "review_required", "needs_query_repair", "needs_literature", "needs_coverage", "needs_evidence_upgrade", "warn"}:
            review += 1
    if _count_from_payload(source_coverage.get("sources_with_success")) == 0 and (rate_limited_sources or failed_sources):
        blocking += 1
    if _count_from_payload(query_audit.get("raw_candidate_count")) == 0:
        blocking += 1
    manual_tasks = _count_list(query_audit.get("required_actions")) + _count_list(query_audit.get("manual_tasks"))
    manual_tasks += _count_list(rerank.get("recommended_actions"))
    manual_tasks += _count_list(coverage.get("required_actions"))
    manual_tasks += _count_list(evidence_mix.get("required_actions"))
    warnings = _count_list(query_audit.get("warnings")) + _count_list(rerank.get("warnings")) + _count_list(coverage.get("warnings")) + _count_list(evidence_mix.get("warnings"))
    status = "block" if blocking else "review_required" if review or manual_tasks or warnings else "pass"
    return {
        "status": status,
        "source_health_status": _public_source_health_status(source_health, source_coverage),
        "query_execution_status": query_status,
        "rerank_status": rerank_status,
        "coverage_status": coverage_status,
        "evidence_mix_status": mix_status,
        "configured_sources": _count_from_payload(source_coverage.get("configured_source_count")) or _count_from_payload(source_health.get("total_sources")),
        "sources_with_success": _count_from_payload(source_coverage.get("sources_with_success")),
        "rate_limited_sources": len(rate_limited_sources) or _count_from_payload(source_health.get("rate_limited_sources")),
        "failed_sources": len(failed_sources) or _count_from_payload(source_health.get("failed_sources")),
        "rate_limited_source_names": rate_limited_sources[:4],
        "failed_source_names": failed_sources[:4],
        "query_attempts": _count_from_payload(source_health.get("query_attempts")),
        "query_successes": _count_from_payload(source_health.get("query_successes")),
        "selected_queries": _count_from_payload(query_audit.get("selected_query_count")),
        "raw_candidates": _count_from_payload(query_audit.get("raw_candidate_count")),
        "queries_with_source_results": _count_from_payload(source_coverage.get("queries_with_source_results")),
        "queries_with_zero_source_results": _count_from_payload(source_coverage.get("queries_with_zero_source_results")),
        "missing_required_intents": _list_from_payload(intent_coverage.get("missing_required_intents", [])),
        "top_count": _count_from_payload(top_coverage.get("top_count")),
        "covered_top_count": _count_from_payload(top_coverage.get("covered_top_count")),
        "average_query_coverage": top_coverage.get("average_query_coverage", 0.0),
        "coverage_ratio": coverage.get("coverage_ratio", 0.0),
        "covered_required": _count_from_payload(coverage.get("covered_required")),
        "total_required": _count_from_payload(coverage.get("total_required")),
        "mix_score": evidence_mix.get("mix_score", 0.0),
        "manual_tasks": manual_tasks,
        "warnings": warnings,
        "blocking_signals": blocking,
        "review_signals": review,
        "approval_hint": _literature_retrieval_gate_hint(status, rate_limited_sources, failed_sources, manual_tasks, warnings),
    }


def _public_source_health_status(source_health: dict[str, Any], source_coverage: dict[str, Any]) -> str:
    if not source_health and not source_coverage:
        return ""
    successes = _count_from_payload(source_coverage.get("sources_with_success"))
    rate_limited = _count_from_payload(source_health.get("rate_limited_sources")) or _count_from_payload(source_coverage.get("rate_limited_sources"))
    failed = _count_from_payload(source_health.get("failed_sources")) or _count_from_payload(source_coverage.get("failed_sources"))
    if successes == 0 and (rate_limited or failed):
        return "needs_source_repair"
    if rate_limited or failed or _count_from_payload(source_health.get("stale_cache_uses")):
        return "review_required"
    return "pass"


def _read_public_legacy_literature_retrieval_gate(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / "01-literature.json")
    if not data:
        return None
    papers = data.get("papers") if isinstance(data.get("papers"), list) else []
    diagnostics = _list_from_payload(data.get("source_diagnostics", []))
    if not papers and not diagnostics:
        return None
    stats = _legacy_literature_diagnostic_stats(diagnostics)
    raw_candidates = len(papers)
    blocking = 1 if raw_candidates == 0 else 0
    review = 1 if stats["failed_sources"] or stats["rate_limited_sources"] or stats["offline_only"] else 0
    status = "block" if blocking else "review_required" if review else "pass"
    warnings = stats["failed_sources"] + stats["rate_limited_sources"] + (1 if stats["offline_only"] else 0)
    return {
        "status": status,
        "source_health_status": "legacy_summary",
        "query_execution_status": "legacy_summary",
        "rerank_status": "",
        "coverage_status": "",
        "evidence_mix_status": "",
        "configured_sources": stats["configured_sources"],
        "sources_with_success": stats["sources_with_success"],
        "rate_limited_sources": stats["rate_limited_sources"],
        "failed_sources": stats["failed_sources"],
        "rate_limited_source_names": stats["rate_limited_source_names"],
        "failed_source_names": stats["failed_source_names"],
        "query_attempts": stats["query_attempts"],
        "query_successes": stats["query_successes"],
        "selected_queries": stats["selected_queries"],
        "raw_candidates": raw_candidates,
        "queries_with_source_results": stats["query_successes"],
        "queries_with_zero_source_results": 0,
        "missing_required_intents": [],
        "top_count": 0,
        "covered_top_count": 0,
        "average_query_coverage": 0.0,
        "coverage_ratio": 0.0,
        "covered_required": 0,
        "total_required": 0,
        "mix_score": 0.0,
        "manual_tasks": 0,
        "warnings": warnings,
        "blocking_signals": blocking,
        "review_signals": review,
        "legacy_summary": True,
        "approval_hint": _legacy_literature_retrieval_gate_hint(status, raw_candidates, stats),
    }


def _legacy_literature_diagnostic_stats(diagnostics: list[str]) -> dict[str, Any]:
    source_names: set[str] = set()
    success_names: set[str] = set()
    failed_names: set[str] = set()
    rate_limited_names: set[str] = set()
    selected_queries = 0
    query_attempts = 0
    query_successes = 0
    offline_only = False
    for item in diagnostics:
        text = str(item or "")
        lower = text.lower()
        if "offline:" in lower or "离线" in text:
            offline_only = True
        if "检索式:" in text:
            selected_queries = max(selected_queries, len([part for part in text.split("检索式:", 1)[-1].split("|") if part.strip()]))
        source = _legacy_source_name(text)
        if source:
            source_names.add(source)
            if "检索失败" in text or " failed" in lower or "http 5" in lower or "http 4" in lower:
                failed_names.add(source)
            if "429" in text or "限流" in text or "rate_limited" in lower:
                rate_limited_names.add(source)
            returned = _legacy_returned_count(text)
            if returned > 0:
                success_names.add(source)
                query_successes += 1
                query_attempts += 1
            elif "检索失败" in text or "返回" in text:
                query_attempts += 1
    return {
        "configured_sources": len(source_names),
        "sources_with_success": len(success_names),
        "failed_sources": len(failed_names),
        "rate_limited_sources": len(rate_limited_names),
        "failed_source_names": _unique_strings(sorted(failed_names))[:4],
        "rate_limited_source_names": _unique_strings(sorted(rate_limited_names))[:4],
        "selected_queries": selected_queries,
        "query_attempts": query_attempts,
        "query_successes": query_successes,
        "offline_only": offline_only,
    }


def _legacy_source_name(text: str) -> str:
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:", text)
    return match.group(1).lower() if match else ""


def _legacy_returned_count(text: str) -> int:
    match = re.search(r"返回\s+(\d+)\s+条", text)
    return int(match.group(1)) if match else 0


def _legacy_literature_retrieval_gate_hint(status: str, raw_candidates: int, stats: dict[str, Any]) -> str:
    if status == "pass":
        return "历史文献检索摘要通过；该 run 缺少新版 source/query 审计，批准前仍需人工抽查 Top 文献。"
    parts = []
    if raw_candidates == 0:
        parts.append("候选文献为空")
    if stats.get("rate_limited_source_names"):
        parts.append("限流来源：" + ", ".join(stats["rate_limited_source_names"][:4]))
    if stats.get("failed_source_names"):
        parts.append("失败来源：" + ", ".join(stats["failed_source_names"][:4]))
    if stats.get("offline_only"):
        parts.append("历史 run 使用离线/旧格式文献检索摘要")
    if not parts:
        parts.append("历史 run 缺少新版 source/query 审计")
    return "；".join(parts) + "。批准进入 idea 前建议补 seed/query 或用新版流程重跑文献阶段。"


def _source_names_by_status(sources: list[Any], statuses: set[str], rate_limited: bool = False) -> list[str]:
    names = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status in statuses or (rate_limited and item.get("rate_limited") is True):
            names.append(str(item.get("source") or "").strip())
    return _unique_strings([name for name in names if name])


def _literature_retrieval_gate_hint(status: str, rate_limited_sources: list[str], failed_sources: list[str], manual_tasks: int, warnings: int) -> str:
    if status == "pass":
        return "检索执行门禁通过；批准前仍需抽查 Top 文献 DOI、URL 和摘要。"
    parts = []
    if rate_limited_sources:
        parts.append("限流来源：" + ", ".join(rate_limited_sources[:4]))
    if failed_sources:
        parts.append("失败来源：" + ", ".join(failed_sources[:4]))
    if manual_tasks:
        parts.append(f"检索/覆盖待办 {manual_tasks} 个")
    if warnings:
        parts.append(f"警告 {warnings} 个")
    if not parts:
        parts.append("需人工核对 source health、query execution、rerank 和 coverage 审计")
    return "；".join(parts) + "。批准进入 idea 前应先修复检索源或补 seed/query。"


def _read_public_idea_experiment_gate(record: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    novelty = _read_json_dict(out_dir / NOVELTY_AUDIT_JSON)
    idea_audit = _read_json_dict(out_dir / IDEA_AUDIT_JSON)
    manager_raw = _read_json_dict(out_dir / EXPERIMENT_MANAGER_JSON)
    experiment_audit = _read_json_dict(out_dir / EXPERIMENT_AUDIT_JSON)
    contract = _read_json_dict(out_dir / IDEA_EXPERIMENT_CONTRACT_JSON)
    safety = _read_json_dict(out_dir / EXECUTION_SAFETY_AUDIT_JSON)
    benchmark_plan = _read_json_dict(out_dir / BENCHMARK_PLAN_JSON)
    benchmark_readiness = _read_json_dict(out_dir / BENCHMARK_READINESS_JSON)
    benchmark_adapter = _read_json_dict(out_dir / BENCHMARK_ADAPTER_JSON)
    manager_public = record.get("experiment_manager") if isinstance(record.get("experiment_manager"), dict) else {}
    if not any([novelty, idea_audit, manager_raw, manager_public, experiment_audit, contract, safety, benchmark_plan, benchmark_readiness, benchmark_adapter]):
        return None

    novelty_status = _public_novelty_status(novelty)
    idea_status = str(idea_audit.get("status") or "")
    manager_status = str((manager_public or manager_raw).get("status") or "")
    experiment_status = str(experiment_audit.get("status") or "")
    contract_status = str(contract.get("status") or "")
    safety_status = str(safety.get("status") or "")
    benchmark_plan_status = _public_benchmark_plan_status(benchmark_plan)
    benchmark_readiness_status = str(benchmark_readiness.get("status") or "")
    benchmark_adapter_status = str(benchmark_adapter.get("status") or "")
    if not benchmark_adapter_status:
        safety_adapter = safety.get("benchmark_adapter_audit") if isinstance(safety.get("benchmark_adapter_audit"), dict) else {}
        benchmark_adapter_status = str(safety_adapter.get("status") or "")

    blocking_issues = 0
    blocking_issues += _count_from_payload(idea_audit.get("blocked"))
    blocking_issues += _count_list(manager_raw.get("required_actions")) if manager_status == "block" else 0
    blocking_issues += _count_list(experiment_audit.get("blocking_issues"))
    blocking_issues += _count_list(contract.get("blocking_issues"))
    safety_blocking = _count_list(safety.get("blocking_issues"))
    blocking_issues += safety_blocking
    benchmark_blocking = _count_list(benchmark_readiness.get("blocking_issues")) + _count_list(benchmark_adapter.get("blocking_issues"))
    blocking_issues += benchmark_blocking

    manual_tasks = 0
    manual_tasks += _count_from_payload(novelty.get("likely_duplicates")) + _count_from_payload(novelty.get("review_required"))
    manual_tasks += _count_from_payload(idea_audit.get("review_required"))
    manual_tasks += _count_list(manager_raw.get("required_actions"))
    manual_tasks += _count_list(experiment_audit.get("required_actions"))
    manual_tasks += _count_list(contract.get("manual_tasks"))
    manual_tasks += _count_list(safety.get("required_actions")) if safety_status == "warn" else 0
    manual_tasks += _count_list(benchmark_plan.get("required_actions"))
    manual_tasks += _count_list(benchmark_readiness.get("manual_tasks"))
    manual_tasks += _count_list(benchmark_adapter.get("manual_tasks"))

    warnings = 0
    warnings += _count_list(novelty.get("warnings"))
    warnings += _count_list(idea_audit.get("warnings"))
    warnings += _count_list(manager_raw.get("warnings"))
    warnings += _count_list(experiment_audit.get("warnings"))
    warnings += _count_list(safety.get("warnings"))
    warnings += _count_list(benchmark_plan.get("warnings"))

    statuses = [
        novelty_status,
        idea_status,
        manager_status,
        experiment_status,
        contract_status,
        safety_status,
        benchmark_plan_status,
        benchmark_readiness_status,
        benchmark_adapter_status,
    ]
    status = _idea_experiment_gate_status(statuses, blocking_issues, manual_tasks, warnings)
    selected_title = _first_string(
        (manager_public or manager_raw).get("selected_idea_title"),
        contract.get("selected_idea_title"),
        experiment_audit.get("idea_title"),
        safety.get("idea_title"),
    )
    execution_mode = _first_string(
        safety.get("execution_mode"),
        contract.get("execution_mode"),
        benchmark_readiness.get("execution_mode"),
    )
    return {
        "status": status,
        "novelty_status": novelty_status,
        "idea_audit_status": idea_status,
        "experiment_manager_status": manager_status,
        "experiment_audit_status": experiment_status,
        "contract_status": contract_status,
        "execution_safety_status": safety_status,
        "benchmark_plan_status": benchmark_plan_status,
        "benchmark_readiness_status": benchmark_readiness_status,
        "benchmark_adapter_status": benchmark_adapter_status,
        "selected_idea_title": selected_title,
        "execution_mode": execution_mode,
        "blocking_issues": blocking_issues,
        "manual_tasks": manual_tasks,
        "warnings": warnings,
        "safety_blocking_issues": safety_blocking,
        "benchmark_blocking_issues": benchmark_blocking,
        "novelty_likely_duplicates": _count_from_payload(novelty.get("likely_duplicates")),
        "novelty_review_required": _count_from_payload(novelty.get("review_required")),
        "idea_review_required": _count_from_payload(idea_audit.get("review_required")),
        "benchmark_candidates": _count_list(benchmark_plan.get("candidates")),
        "benchmark_manual_tasks": _count_list(benchmark_readiness.get("manual_tasks")) + _count_list(benchmark_adapter.get("manual_tasks")),
        "approval_hint": _idea_experiment_gate_hint(status, blocking_issues, manual_tasks, warnings, safety_blocking, benchmark_blocking),
    }


def _public_novelty_status(report: dict[str, Any]) -> str:
    if not report:
        return ""
    total = _count_from_payload(report.get("total_ideas")) or _count_list(report.get("items"))
    if total == 0:
        return "review_required"
    if _count_from_payload(report.get("likely_duplicates")) or _count_from_payload(report.get("review_required")):
        return "review_required"
    return "pass"


def _public_benchmark_plan_status(report: dict[str, Any]) -> str:
    if not report:
        return ""
    if not _count_list(report.get("candidates")):
        return "review_required"
    if _count_list(report.get("required_actions")) or _count_list(report.get("warnings")):
        return "review_required"
    return "pass"


def _idea_experiment_gate_status(statuses: list[str], blocking_issues: int, manual_tasks: int, warnings: int) -> str:
    block_statuses = {"block", "blocked", "failed", "error", "needs_human_reselection"}
    review_statuses = {"review", "review_required", "warn", "warning", "needs_benchmark_upgrade", "proceed_with_cautions", "smoke_first"}
    normalized = {str(status or "").strip() for status in statuses if str(status or "").strip()}
    if blocking_issues or normalized & block_statuses:
        return "block"
    if manual_tasks or warnings or normalized & review_statuses:
        return "review_required"
    return "pass"


def _idea_experiment_gate_hint(status: str, blocking_issues: int, manual_tasks: int, warnings: int, safety_blocking: int, benchmark_blocking: int) -> str:
    if status == "pass":
        return "Idea-实验门禁通过；执行前仍需人工核对计划和命令范围。"
    parts = []
    if blocking_issues:
        parts.append(f"阻断项 {blocking_issues} 个")
    if safety_blocking:
        parts.append(f"执行安全阻断 {safety_blocking} 个")
    if benchmark_blocking:
        parts.append(f"Benchmark 阻断 {benchmark_blocking} 个")
    if manual_tasks:
        parts.append(f"人工待办 {manual_tasks} 个")
    if warnings:
        parts.append(f"警告 {warnings} 个")
    if not parts:
        parts.append("需人工核对 idea 新颖性、实验契约和执行安全审计")
    return "；".join(parts) + "。批准执行前应填写审核意见，确认风险已修复或接受。"


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _count_from_payload(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, list):
        return len(value)
    return 0


def _safe_positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _float_from_payload(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _first_string(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _read_public_literature_search_feedback(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / LITERATURE_SEARCH_FEEDBACK_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    queries = data.get("recommended_queries") if isinstance(data.get("recommended_queries"), list) else []
    seed_targets = data.get("seed_paper_targets") if isinstance(data.get("seed_paper_targets"), list) else []
    tasks = data.get("retrieval_repair_tasks") if isinstance(data.get("retrieval_repair_tasks"), list) else []
    next_config = data.get("next_run_config") if isinstance(data.get("next_run_config"), dict) else {}
    return {
        "status": data.get("status", ""),
        "recommended_queries": len(queries),
        "seed_targets": len(seed_targets),
        "retrieval_repair_tasks": len(tasks),
        "agent_queries": sum(1 for item in tasks if isinstance(item, dict) and str(item.get("owner") or "") in {"agent", "agent+human"} and str(item.get("query") or "").strip()),
        "top_queries": [str(item.get("query") or "").strip() for item in queries[:3] if isinstance(item, dict) and str(item.get("query") or "").strip()],
        "next_run_config": {
            "literature_provider": next_config.get("literature_provider", ""),
            "sources": _list_from_payload(next_config.get("sources", [])),
            "max_papers": next_config.get("max_papers", 0),
            "max_search_queries": next_config.get("max_search_queries", 0),
            "seed_papers_min": next_config.get("seed_papers_min", 0),
        },
        "approval_guidance": len(data.get("approval_guidance", [])) if isinstance(data.get("approval_guidance"), list) else 0,
    }


def _read_public_literature_rescue_plan(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / LITERATURE_RESCUE_PLAN_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    rows = data.get("rescue_queries") if isinstance(data.get("rescue_queries"), list) else []
    queries = [
        str(item.get("query") or "").strip()
        for item in rows
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    ]
    role_queries = [
        str(item.get("query") or "").strip()
        for item in rows
        if isinstance(item, dict)
        and str(item.get("kind") or "") == "missing_evidence_role"
        and str(item.get("query") or "").strip()
    ]
    return {
        "status": data.get("status", ""),
        "coverage_status": data.get("coverage_status", ""),
        "coverage_ratio": data.get("coverage_ratio", 0.0),
        "missing_evidence_roles": _list_from_payload(data.get("missing_evidence_roles", [])),
        "weak_reasons": len(data.get("weak_reasons", [])) if isinstance(data.get("weak_reasons"), list) else 0,
        "source_repairs": len(data.get("source_repairs", [])) if isinstance(data.get("source_repairs"), list) else 0,
        "rescue_queries": len(rows),
        "role_queries": _unique_strings(role_queries)[:6],
        "top_queries": _unique_strings(queries)[:8],
        "required_actions": len(data.get("required_actions", [])) if isinstance(data.get("required_actions"), list) else 0,
    }


def _read_public_literature_rescue_execution(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / LITERATURE_RESCUE_EXECUTION_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    outcomes = data.get("query_outcomes") if isinstance(data.get("query_outcomes"), list) else []
    unresolved_statuses = {"partial", "no_new_papers", "no_hits", "not_executed"}
    unresolved_queries = [
        str(item.get("query") or "").strip()
        for item in outcomes
        if isinstance(item, dict)
        and str(item.get("status") or "") in unresolved_statuses
        and str(item.get("query") or "").strip()
    ]
    return {
        "status": data.get("status", ""),
        "trigger_status": data.get("trigger_status", ""),
        "updated_review": data.get("updated_review") is True,
        "selected_queries": len(data.get("selected_queries", [])) if isinstance(data.get("selected_queries"), list) else 0,
        "repair_tasks": len(data.get("repair_task_ids", [])) if isinstance(data.get("repair_task_ids"), list) else 0,
        "closed_query_outcomes": data.get("closed_query_outcomes", 0),
        "unresolved_query_outcomes": data.get("unresolved_query_outcomes", 0),
        "new_unique_papers": data.get("new_unique_papers", 0),
        "query_outcomes": len(outcomes),
        "unresolved_queries": _unique_strings(unresolved_queries)[:6],
        "required_actions": len(data.get("required_actions", [])) if isinstance(data.get("required_actions"), list) else 0,
        "warnings": len(data.get("warnings", [])) if isinstance(data.get("warnings"), list) else 0,
    }


def _read_public_run_integrity(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / RUN_INTEGRITY_AUDIT_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "checks": summary.get("checks", 0),
        "pass": summary.get("pass", 0),
        "warn": summary.get("warn", 0),
        "block": summary.get("block", 0),
        "required_artifacts": summary.get("required_artifacts", 0),
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
        "warnings": len(data.get("warnings", [])) if isinstance(data.get("warnings"), list) else 0,
        "recommended_actions": len(data.get("recommended_actions", [])) if isinstance(data.get("recommended_actions"), list) else 0,
    }


def _read_public_final_handoff(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / FINAL_HANDOFF_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "status": data.get("status", ""),
        "package_zip": data.get("package_zip", ""),
        "package_zip_exists": data.get("package_zip_exists") is True,
        "package_zip_valid": data.get("package_zip_valid") if isinstance(data.get("package_zip_valid"), bool) else None,
        "package_status": data.get("package_status", ""),
        "scorecard_status": data.get("scorecard_status", ""),
        "scorecard_overall_score": data.get("scorecard_overall_score", 0.0),
        "run_integrity_status": data.get("run_integrity_status", ""),
        "package_has_integrity_audit": data.get("package_has_integrity_audit") is True,
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
        "manual_tasks": len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0,
        "recommended_actions": len(data.get("recommended_actions", [])) if isinstance(data.get("recommended_actions"), list) else 0,
    }


def _read_public_agent_trajectory(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / AGENT_TRAJECTORY_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    counts = summary.get("phase_counts") if isinstance(summary.get("phase_counts"), dict) else {}
    return {
        "status": data.get("status", ""),
        "pass": _count_from_payload(counts.get("pass")),
        "warn": _count_from_payload(counts.get("warn")),
        "block": _count_from_payload(counts.get("block")),
        "not_started": _count_from_payload(counts.get("not_started")),
        "blocking_issues": _trajectory_issue_count(data, summary, "blocking_issues"),
        "manual_tasks": _trajectory_issue_count(data, summary, "manual_tasks"),
        "last_event": summary.get("last_event", ""),
        "event_count": _count_from_payload(summary.get("event_count")),
        "backfilled_events": _count_from_payload(summary.get("backfilled_events")),
        "artifact_count": _count_from_payload(summary.get("artifact_count")),
    }


def _read_public_agent_observability(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / AGENT_OBSERVABILITY_AUDIT_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    budget = data.get("budget") if isinstance(data.get("budget"), dict) else {}
    return {
        "status": data.get("status", ""),
        "state_stage": summary.get("state_stage", ""),
        "manifest_status": summary.get("manifest_status", ""),
        "manifest_events": _count_from_payload(summary.get("manifest_events")),
        "manifest_artifacts": _count_from_payload(summary.get("manifest_artifacts")),
        "llm_total_calls": _count_from_payload(summary.get("llm_total_calls")),
        "llm_failed_calls": _count_from_payload(summary.get("llm_failed_calls")),
        "llm_budget_exceeded_calls": _count_from_payload(summary.get("llm_budget_exceeded_calls")),
        "experiment_runs": _count_from_payload(summary.get("experiment_runs")),
        "repair_queue_status": summary.get("repair_queue_status", ""),
        "blocking_issues": len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0,
        "manual_tasks": len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0,
        "warnings": len(data.get("warnings", [])) if isinstance(data.get("warnings"), list) else 0,
        "call_utilization": _float_from_payload(budget.get("call_utilization")),
        "prompt_utilization": _float_from_payload(budget.get("prompt_utilization")),
        "total_llm_duration_seconds": _float_from_payload(budget.get("total_llm_duration_seconds")),
    }


def _trajectory_issue_count(data: dict[str, Any], summary: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, list):
        return len(value)
    return _count_from_payload(summary.get(key))


def _read_public_human_gate_audit(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / HUMAN_GATE_AUDIT_JSON)
    if not data:
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "review_approved": summary.get("review_approved") is True,
        "review_blocks": _count_from_payload(summary.get("review_blocks")),
        "downstream_artifacts": _count_from_payload(summary.get("downstream_artifacts")),
        "downstream_stage": summary.get("downstream_stage", ""),
        "execution_approved": summary.get("execution_approved") is True,
        "execution_mode": summary.get("execution_mode", ""),
        "execution_artifacts": _count_from_payload(summary.get("execution_artifacts")),
        "repair_resume_status": summary.get("repair_resume_status", ""),
        "repair_resume_applied": summary.get("repair_resume_applied") is True,
        "review_reapproval_required": summary.get("review_reapproval_required") is True,
        "execution_reapproval_required": summary.get("execution_reapproval_required") is True,
        "check_count": _count_list(data.get("checks")),
        "blocking_issue_count": _count_list(data.get("blocking_issues")),
        "manual_task_count": _count_list(data.get("manual_tasks")),
        "recommended_action_count": _count_list(data.get("recommended_actions")),
    }


def _read_public_literature_search_strategy(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / LITERATURE_SEARCH_STRATEGY_JSON
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "status": data.get("status", ""),
        "quality_score": data.get("quality_score", 0.0),
        "selected_queries": len(data.get("selected_queries", [])) if isinstance(data.get("selected_queries"), list) else 0,
        "selected_intents": _list_from_payload(data.get("selected_intents", [])),
        "missing_required_intents": _list_from_payload(data.get("missing_required_intents", [])),
        "weak_selected_queries": len(data.get("weak_selected_queries", [])) if isinstance(data.get("weak_selected_queries"), list) else 0,
    }


def _read_public_literature_gate_decision(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / LITERATURE_GATE_DECISION_JSON)
    if not data:
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "decision": data.get("decision", ""),
        "blocks_downstream": data.get("blocks_downstream") is True,
        "human_approval_required": data.get("human_approval_required") is True,
        "raw_papers": _count_from_payload(summary.get("raw_papers")),
        "selected_papers": _count_from_payload(summary.get("selected_papers")),
        "quality_confidence": summary.get("quality_confidence", ""),
        "quality_score": _float_from_payload(summary.get("quality_score")),
        "source_health_status": summary.get("source_health_status", ""),
        "query_execution_status": summary.get("query_execution_status", ""),
        "rerank_status": summary.get("rerank_status", ""),
        "coverage_status": summary.get("coverage_status", ""),
        "coverage_ratio": _float_from_payload(summary.get("coverage_ratio")),
        "evidence_mix_status": summary.get("evidence_mix_status", ""),
        "evidence_mix_score": _float_from_payload(summary.get("evidence_mix_score")),
        "rescue_status": summary.get("rescue_status", ""),
        "rescue_execution_status": summary.get("rescue_execution_status", ""),
        "seed_status": summary.get("seed_status", ""),
        "seed_role_coverage_status": summary.get("seed_role_coverage_status", ""),
        "evidence_contract_status": summary.get("evidence_contract_status", ""),
        "evidence_contract_blocking": _count_from_payload(summary.get("evidence_contract_blocking")),
        "evidence_contract_review": _count_from_payload(summary.get("evidence_contract_review")),
        "evidence_contract_chunk_coverage": _float_from_payload(summary.get("evidence_contract_chunk_coverage")),
        "evidence_contract_substantive_chunk_coverage": _float_from_payload(summary.get("evidence_contract_substantive_chunk_coverage")),
        "evidence_contract_median_chunk_chars": _count_from_payload(summary.get("evidence_contract_median_chunk_chars")),
        "evidence_contract_locator_coverage": _float_from_payload(summary.get("evidence_contract_locator_coverage")),
        "citation_integrity_status": summary.get("citation_integrity_status", ""),
        "citation_integrity_score": _float_from_payload(summary.get("citation_integrity_score")),
        "context_citations": _count_from_payload(summary.get("context_citations")),
        "context_chunks": _count_from_payload(summary.get("context_chunks")),
        "context_claim_support": _count_from_payload(summary.get("context_claim_support")),
        "citation_grounding_status": summary.get("citation_grounding_status", ""),
        "citation_grounding_score": _float_from_payload(summary.get("citation_grounding_score")),
        "citation_grounding_blocked": _count_from_payload(summary.get("citation_grounding_blocked")),
        "citation_grounding_review": _count_from_payload(summary.get("citation_grounding_review")),
        "signal_count": _count_list(data.get("signals")),
        "blocking_reason_count": _count_list(data.get("blocking_reasons")),
        "review_reason_count": _count_list(data.get("review_reasons")),
        "required_action_count": _count_list(data.get("required_actions")),
        "approval_guidance_count": _count_list(data.get("approval_guidance")),
    }


def _read_public_literature_evidence_contract(out_dir: Path) -> dict[str, Any] | None:
    data = _read_json_dict(out_dir / LITERATURE_EVIDENCE_CONTRACT_JSON)
    if not data:
        return None
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "status": data.get("status", ""),
        "blocks_downstream": data.get("blocks_downstream") is True,
        "human_approval_required": data.get("human_approval_required") is True,
        "citations": _count_from_payload(summary.get("citations")),
        "chunks": _count_from_payload(summary.get("chunks")),
        "citations_with_chunks": _count_from_payload(summary.get("citations_with_chunks")),
        "citations_with_substantive_chunks": _count_from_payload(summary.get("citations_with_substantive_chunks")),
        "chunk_coverage": _float_from_payload(summary.get("chunk_coverage")),
        "substantive_chunk_coverage": _float_from_payload(summary.get("substantive_chunk_coverage")),
        "median_chunk_chars": _count_from_payload(summary.get("median_chunk_chars")),
        "locator_coverage": _float_from_payload(summary.get("locator_coverage")),
        "doi_coverage": _float_from_payload(summary.get("doi_coverage")),
        "url_coverage": _float_from_payload(summary.get("url_coverage")),
        "source_diversity": _count_from_payload(summary.get("source_diversity")),
        "single_crossref_citations": _count_from_payload(summary.get("single_crossref_citations")),
        "single_crossref_ratio": _float_from_payload(summary.get("single_crossref_ratio")),
        "thin_chunks": _count_from_payload(summary.get("thin_chunks")),
        "local_fulltext_chunks": _count_from_payload(summary.get("local_fulltext_chunks")),
        "evidence_role_count": _count_from_payload(summary.get("evidence_role_count")),
        "missing_evidence_roles": _list_from_payload(summary.get("missing_evidence_roles", [])),
        "sources_with_success": _count_from_payload(summary.get("sources_with_success")),
        "rate_limited_sources": _count_from_payload(summary.get("rate_limited_sources")),
        "failed_sources": _count_from_payload(summary.get("failed_sources")),
        "query_execution_status": summary.get("query_execution_status", ""),
        "rerank_status": summary.get("rerank_status", ""),
        "top_rerank_covered": _count_from_payload(summary.get("top_rerank_covered")),
        "top_rerank_count": _count_from_payload(summary.get("top_rerank_count")),
        "average_query_coverage": _float_from_payload(summary.get("average_query_coverage")),
        "citation_integrity_status": summary.get("citation_integrity_status", ""),
        "blocked_citations": _count_from_payload(summary.get("blocked_citations")),
        "review_citations": _count_from_payload(summary.get("review_citations")),
        "check_count": _count_list(data.get("checks")),
        "blocking_issue_count": _count_list(data.get("blocking_issues")),
        "review_reason_count": _count_list(data.get("review_reasons")),
        "required_action_count": _count_list(data.get("required_actions")),
        "approval_guidance_count": _count_list(data.get("approval_guidance")),
    }


def _read_public_literature_quality_gate(record: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    gate_decision = record.get("literature_gate_decision") if isinstance(record.get("literature_gate_decision"), dict) else {}
    quality = _read_json_dict(out_dir / "01-literature-quality.json")
    feedback = record.get("literature_search_feedback") if isinstance(record.get("literature_search_feedback"), dict) else {}
    strategy = record.get("literature_search_strategy") if isinstance(record.get("literature_search_strategy"), dict) else {}
    rescue = record.get("literature_rescue_plan") if isinstance(record.get("literature_rescue_plan"), dict) else {}
    execution = record.get("literature_rescue_execution") if isinstance(record.get("literature_rescue_execution"), dict) else {}
    seed = record.get("seed_intake") if isinstance(record.get("seed_intake"), dict) else {}
    if gate_decision:
        missing_roles = _normalized_literature_roles(
            [
                *_list_from_payload(rescue.get("missing_evidence_roles", [])),
                *_list_from_payload(seed.get("missing_roles", [])),
                *_list_from_payload(strategy.get("missing_required_intents", [])),
            ]
        )
        repair_queries = int(feedback.get("recommended_queries") or 0)
        repair_queries += len(rescue.get("role_queries", []) if isinstance(rescue.get("role_queries"), list) else [])
        repair_queries += len(execution.get("unresolved_queries", []) if isinstance(execution.get("unresolved_queries"), list) else [])
        repair_queries += len(seed.get("role_repair_queries", []) if isinstance(seed.get("role_repair_queries"), list) else [])
        return {
            "status": gate_decision.get("status", ""),
            "raw_papers": gate_decision.get("raw_papers", 0),
            "selected_papers": gate_decision.get("selected_papers", 0),
            "quality_confidence": gate_decision.get("quality_confidence", ""),
            "quality_score": gate_decision.get("quality_score", 0.0),
            "quality_role_coverage": quality.get("role_coverage", {}) if isinstance(quality.get("role_coverage") if quality else None, dict) else {},
            "search_strategy_status": strategy.get("status", ""),
            "feedback_status": feedback.get("status", ""),
            "rescue_status": gate_decision.get("rescue_status", ""),
            "rescue_execution_status": gate_decision.get("rescue_execution_status", ""),
            "seed_status": gate_decision.get("seed_status", ""),
            "seed_role_coverage_status": gate_decision.get("seed_role_coverage_status", ""),
            "missing_roles": missing_roles,
            "repair_queries": repair_queries,
            "suggested_seed_count": int(seed.get("suggested_seed_count") or 0),
            "manual_tasks": int(gate_decision.get("required_actions") or 0),
            "blocking_signals": int(gate_decision.get("blocking_reasons") or 0),
            "review_signals": int(gate_decision.get("review_reasons") or 0),
            "approval_hint": _literature_quality_gate_hint(str(gate_decision.get("status") or ""), repair_queries, int(seed.get("suggested_seed_count") or 0), missing_roles),
            "gate_decision_status": gate_decision.get("status", ""),
            "blocks_downstream": gate_decision.get("blocks_downstream") is True,
            "citation_integrity_status": gate_decision.get("citation_integrity_status", ""),
            "context_citations": int(gate_decision.get("context_citations") or 0),
            "context_chunks": int(gate_decision.get("context_chunks") or 0),
            "citation_grounding_status": gate_decision.get("citation_grounding_status", ""),
            "citation_grounding_blocked": int(gate_decision.get("citation_grounding_blocked") or 0),
            "citation_grounding_review": int(gate_decision.get("citation_grounding_review") or 0),
        }
    if not any([quality, feedback, strategy, rescue, execution, seed]):
        return None

    blocking = 0
    review_required = 0
    repair_queries = 0
    manual_tasks = 0
    statuses = [
        str(quality.get("confidence_status") or "") if quality else "",
        str(strategy.get("status") or ""),
        str(feedback.get("status") or ""),
        str(rescue.get("status") or ""),
        str(execution.get("status") or ""),
        str(seed.get("status") or ""),
        str(seed.get("role_coverage_status") or ""),
    ]
    for status in statuses:
        if status in {"block", "blocked", "failed", "error"}:
            blocking += 1
        elif status in {"weak", "review_required", "needs_search_revision", "needs_rescue_search", "needs_coverage", "partial", "no_new_papers", "no_hits"}:
            review_required += 1
    repair_queries += int(feedback.get("recommended_queries") or 0)
    repair_queries += len(rescue.get("role_queries", []) if isinstance(rescue.get("role_queries"), list) else [])
    repair_queries += len(execution.get("unresolved_queries", []) if isinstance(execution.get("unresolved_queries"), list) else [])
    repair_queries += len(seed.get("role_repair_queries", []) if isinstance(seed.get("role_repair_queries"), list) else [])
    manual_tasks += int(feedback.get("seed_targets") or 0)
    manual_tasks += int(rescue.get("required_actions") or 0)
    manual_tasks += int(execution.get("required_actions") or 0)
    manual_tasks += int(seed.get("required_actions") or 0)
    manual_tasks += int(seed.get("warnings") or 0)
    suggested_seed_count = int(seed.get("suggested_seed_count") or 0)
    missing_roles = _normalized_literature_roles(
        [
            *_list_from_payload(rescue.get("missing_evidence_roles", [])),
            *_list_from_payload(seed.get("missing_roles", [])),
            *_list_from_payload(strategy.get("missing_required_intents", [])),
        ]
    )
    status = "block" if blocking else "review_required" if review_required or missing_roles or repair_queries or suggested_seed_count else "pass"
    approval_hint = _literature_quality_gate_hint(status, repair_queries, suggested_seed_count, missing_roles)
    return {
        "status": status,
        "raw_papers": _quality_count(quality, "total_papers"),
        "selected_papers": _quality_count(quality, "selected_papers"),
        "quality_confidence": quality.get("confidence_status", "") if quality else "",
        "quality_score": quality.get("confidence_score", 0.0) if quality else 0.0,
        "quality_role_coverage": quality.get("role_coverage", {}) if isinstance(quality.get("role_coverage") if quality else None, dict) else {},
        "search_strategy_status": strategy.get("status", ""),
        "feedback_status": feedback.get("status", ""),
        "rescue_status": rescue.get("status", ""),
        "rescue_execution_status": execution.get("status", ""),
        "seed_status": seed.get("status", ""),
        "seed_role_coverage_status": seed.get("role_coverage_status", ""),
        "missing_roles": missing_roles,
        "repair_queries": repair_queries,
        "suggested_seed_count": suggested_seed_count,
        "manual_tasks": manual_tasks,
        "blocking_signals": blocking,
        "review_signals": review_required,
        "approval_hint": approval_hint,
    }


def _literature_quality_gate_hint(status: str, repair_queries: int, suggested_seed_count: int, missing_roles: list[str]) -> str:
    if status == "pass":
        return "文献证据门禁通过；仍需人工抽查核心文献。"
    parts = []
    if missing_roles:
        parts.append("缺失证据角色：" + ", ".join(missing_roles[:4]))
    if repair_queries:
        parts.append(f"可回填 {repair_queries} 条补检索式")
    if suggested_seed_count:
        parts.append(f"可回填 {suggested_seed_count} 条候选 seed")
    if not parts:
        parts.append("需人工核对 01-review-gate、01-literature-quality 和 01-seed-paper-intake")
    return "；".join(parts) + "。批准进入 idea 前应填写审核意见或先应用检索建议。"


def _normalized_literature_roles(values: list[str]) -> list[str]:
    aliases = {
        "review": "review_survey",
        "survey": "review_survey",
        "review_survey": "review_survey",
        "benchmark": "benchmark_dataset",
        "dataset": "benchmark_dataset",
        "benchmark_dataset": "benchmark_dataset",
        "baseline": "baseline_method",
        "method": "baseline_method",
        "baseline_method": "baseline_method",
        "recent": "recent_work",
        "recent_work": "recent_work",
    }
    return _unique_strings([aliases.get(str(value).strip(), str(value).strip()) for value in values])


def _quality_count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, int | float):
        return int(value)
    if key == "selected_papers" and isinstance(data.get("items"), list):
        return sum(1 for item in data["items"] if isinstance(item, dict) and item.get("selected") is True)
    if key == "total_papers" and isinstance(data.get("items"), list):
        return len(data["items"])
    return 0


def _read_public_seed_intake(out_dir: Path, topic: str = "") -> dict[str, Any] | None:
    path = out_dir / SEED_PAPER_INTAKE_JSON
    suggestion = build_seed_paper_suggestion_report(topic, out_dir)
    if not path.exists():
        if not suggestion.get("suggested_seed_count"):
            return None
        missing_roles = _list_from_payload(suggestion.get("missing_roles", []))
        return {
            "status": "not_configured",
            "role_coverage_status": "review_required",
            "total_seed_entries": 0,
            "curated_seed_papers": 0,
            "missing_roles": missing_roles,
            "role_repair_queries": _list_from_payload(suggestion.get("role_repair_queries", [])),
            "suggested_seed_entries": _list_from_payload(suggestion.get("suggested_seed_entries", [])),
            "suggested_seed_count": suggestion.get("suggested_seed_count", 0),
            "suggested_seed_role_counts": suggestion.get("suggested_seed_role_counts", {}),
            "required_actions": 0,
            "warnings": 0,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    missing_roles = _list_from_payload(data.get("missing_curated_seed_roles", []))
    return {
        "status": data.get("status", ""),
        "role_coverage_status": data.get("role_coverage_status", ""),
        "total_seed_entries": data.get("total_seed_entries", 0),
        "curated_seed_papers": data.get("curated_seed_papers", 0),
        "missing_roles": missing_roles,
        "role_repair_queries": seed_role_repair_queries(topic, missing_roles),
        "suggested_seed_entries": _list_from_payload(suggestion.get("suggested_seed_entries", [])),
        "suggested_seed_count": suggestion.get("suggested_seed_count", 0),
        "suggested_seed_role_counts": suggestion.get("suggested_seed_role_counts", {}),
        "required_actions": len(data.get("required_actions", [])) if isinstance(data.get("required_actions"), list) else 0,
        "warnings": len(data.get("warnings", [])) if isinstance(data.get("warnings"), list) else 0,
    }


def _write_state_file(out_dir: Path, topic: str, stage: str) -> None:
    write_json(out_dir / "state.json", {"topic": topic, "stage": stage, "updated_at": _utc_now()})
    update_workflow_stage(out_dir, topic, stage)


def _write_run_config(out_dir: Path, config: AgentConfig) -> None:
    data = asdict(config)
    llm = data.get("llm", {})
    if isinstance(llm, dict):
        llm["api_key"] = ""
    literature = data.get("literature", {})
    if isinstance(literature, dict):
        literature["semantic_scholar_api_key"] = ""
        literature["openalex_api_key"] = ""
        literature["contact_email"] = ""
    if config.multi_agent == MultiAgentConfig():
        data.pop("multi_agent", None)
    write_json(out_dir / RUN_CONFIG_FILENAME, data)


def _write_resume_preflight_or_raise(topic: str, config: AgentConfig, out_dir: Path) -> None:
    memory = build_run_memory(RUNS_DIR, limit=100)
    preflight = run_preflight(topic, config, ping_llm=False, run_memory=memory)
    write_preflight_artifacts(preflight, out_dir)
    if preflight.status == "fail":
        raise PreflightGateError(preflight)


def _preflight_error_payload(report: Any) -> dict[str, Any]:
    return {
        "error": "preflight failed",
        "preflight": _public_preflight(report),
        "report": asdict(report) if hasattr(report, "__dataclass_fields__") else report,
        "markdown": render_preflight_markdown(report),
    }


def _env_llm_config_from_payload(payload: dict[str, Any]) -> AgentConfig:
    config = _config_from_payload(payload)
    default_llm = AgentConfig().llm
    llm = replace(
        config.llm,
        base_url_env=default_llm.base_url_env,
        api_key_env=default_llm.api_key_env,
        model_env=default_llm.model_env,
        base_url="",
        model="",
        api_key="",
    )
    literature = replace(config.literature, semantic_scholar_api_key="", openalex_api_key="")
    return replace(config, llm=llm, literature=literature)


def _env_llm_public_secrets(payload: dict[str, Any], config: AgentConfig) -> list[str]:
    candidates = [
        payload.get("llm_api_key"),
        payload.get("semantic_scholar_api_key"),
        payload.get("openalex_api_key"),
        os.environ.get(config.llm.api_key_env, ""),
        os.environ.get(config.literature.semantic_scholar_api_key_env, ""),
        os.environ.get(config.literature.openalex_api_key_env, ""),
    ]
    return [value for value in _unique_strings([str(item or "").strip() for item in candidates]) if len(value) >= 4]


def _public_env_llm_preflight(report: Any, config: AgentConfig, payload: dict[str, Any]) -> dict[str, Any]:
    data = asdict(report) if hasattr(report, "__dataclass_fields__") else dict(report)
    checks = [item for item in (data.get("checks") if isinstance(data.get("checks"), list) else []) if isinstance(item, dict)]
    llm_checks = [item for item in checks if str(item.get("name") or "").startswith("llm_")]
    by_name = {str(item.get("name") or ""): item for item in llm_checks}
    required = ["llm_provider", "llm_base_url", "llm_model", "llm_api_key", "llm_ping"]
    failed = [name for name in required if str((by_name.get(name) or {}).get("status") or "") == "fail"]
    ping_status = str((by_name.get("llm_ping") or {}).get("status") or "")
    static_ok = all(str((by_name.get(name) or {}).get("status") or "") == "pass" for name in ["llm_provider", "llm_base_url", "llm_model", "llm_api_key"])
    status = "pass" if static_ok and ping_status == "pass" else "warn" if ping_status in {"warn", "skipped"} and not failed else "block"
    ignored = [name for name in ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"] if str(payload.get(name) or "").strip()]
    return {
        "status": status,
        "ping_status": ping_status or "missing",
        "llm_check_status_counts": _status_counts(llm_checks),
        "failed_llm_checks": failed,
        "warn_llm_checks": [name for name in required if str((by_name.get(name) or {}).get("status") or "") == "warn"],
        "server_env_configured": {
            "base_url": bool(os.environ.get(config.llm.base_url_env, "").strip()),
            "model": bool(os.environ.get(config.llm.model_env, "").strip()),
            "api_key": bool(os.environ.get(config.llm.api_key_env, "").strip()),
        },
        "required_env_vars": [config.llm.base_url_env, config.llm.model_env, config.llm.api_key_env],
        "ignored_payload_secret_fields": ignored,
    }


def _render_env_llm_preflight_markdown(report: Any, env_llm: dict[str, Any]) -> str:
    data = asdict(report) if hasattr(report, "__dataclass_fields__") else dict(report)
    checks = [item for item in (data.get("checks") if isinstance(data.get("checks"), list) else []) if isinstance(item, dict)]
    llm_checks = [item for item in checks if str(item.get("name") or "").startswith("llm_")]
    env_configured = env_llm.get("server_env_configured") if isinstance(env_llm.get("server_env_configured"), dict) else {}
    lines = [
        "# Env LLM Preflight",
        "",
        f"- 状态：{env_llm.get('status') or '-'}",
        f"- Ping：{env_llm.get('ping_status') or '-'}",
        f"- 服务端环境：base_url={'yes' if env_configured.get('base_url') else 'no'}；model={'yes' if env_configured.get('model') else 'no'}；api_key={'yes' if env_configured.get('api_key') else 'no'}",
        f"- 忽略的 payload secret 字段：{', '.join(_list_from_payload(env_llm.get('ignored_payload_secret_fields'))) or '-'}",
        "",
        "| Check | Status | Summary | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for item in llm_checks:
        lines.append(
            "| "
            + " | ".join(
                [
                    _env_llm_markdown_cell(str(item.get("name") or "")),
                    _env_llm_markdown_cell(str(item.get("status") or "")),
                    _env_llm_markdown_cell(str(item.get("summary") or "")),
                    _env_llm_markdown_cell(str(item.get("detail") or "")),
                ]
            )
            + " |"
        )
    lines.extend(["", "该检查只使用服务端环境变量中的 LLM 连接信息；Web payload 中的 API key 字段会被忽略。"])
    return "\n".join(lines)


def _env_llm_markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _load_run_config(out_dir: Path) -> AgentConfig | None:
    path = out_dir / RUN_CONFIG_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return _config_from_dict(data)
    except TypeError:
        return None


def _config_from_dict(data: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        llm=LLMConfig(**dict(data.get("llm") or {})),
        literature=LiteratureConfig(**dict(data.get("literature") or {})),
        ideation=IdeationConfig(**dict(data.get("ideation") or {})),
        execution=ExecutionConfig(**dict(data.get("execution") or {})),
        paper=PaperConfig(**dict(data.get("paper") or {})),
        release=ReleaseConfig(**dict(data.get("release") or {})),
        paper_grade=PaperGradeConfig(**dict(data.get("paper_grade") or {})),
        human=HumanConfig(**dict(data.get("human") or {})),
        multi_agent=_multi_agent_config_from_data(data.get("multi_agent", {})),
    )


def _resume_config(out_dir: Path, payload: dict[str, Any]) -> AgentConfig:
    config = _load_run_config(out_dir) or AgentConfig()
    _reject_paper_grade_payload_secrets(config, payload)
    return _apply_payload_overrides(config, payload)


def _reject_paper_grade_payload_secrets(config: AgentConfig, payload: dict[str, Any]) -> None:
    paper_grade_updates = _paper_grade_payload_updates(payload)
    payload_enabled = paper_grade_updates.get("enabled") is True
    if not (config.paper_grade.enabled or payload_enabled):
        return
    fields = _payload_secret_fields(payload)
    if not fields:
        return
    raise RuntimeError(
        "paper-grade Web actions require env-only secret handling; "
        f"remove payload secret fields: {', '.join(fields)}. "
        "Set the corresponding server environment variables instead."
    )


def _payload_secret_fields(payload: dict[str, Any]) -> list[str]:
    return [
        field
        for field in ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"]
        if _has_payload_value(payload, field)
    ]


def _validate_payload_llm_connection(
    payload: dict[str, Any],
    current_llm: LLMConfig | None = None,
) -> None:
    from .llm import validate_llm_base_url, validate_llm_provider

    has_base_url = _has_payload_value(payload, "llm_base_url")
    has_api_key = _has_payload_value(payload, "llm_api_key")
    requested_provider = ""
    if _has_payload_value(payload, "llm_provider"):
        requested_provider = validate_llm_provider(str(payload["llm_provider"]))
    if current_llm is not None and requested_provider:
        current_provider = str(current_llm.provider or "openai-compatible").strip().lower()
        if requested_provider != current_provider and not has_base_url:
            raise ValueError(
                "changing llm_provider requires an explicit non-empty llm_base_url in the same request"
            )
    if has_api_key and not has_base_url:
        raise ValueError("llm_api_key requires an explicit llm_base_url in the same request")
    if has_base_url:
        validate_llm_base_url(str(payload["llm_base_url"]))


def _validate_payload_fulltext_paths(payload: dict[str, Any]) -> None:
    if not _has_payload_value(payload, "fulltext_paths"):
        return
    from .fulltext_corpus import fulltext_collection_issues, inspect_fulltext_path

    paths = _list_from_lines(payload["fulltext_paths"])
    failures = fulltext_collection_issues(paths, ROOT) + [
        warning
        for value in paths
        for _path, status, warning in [inspect_fulltext_path(value, ROOT)]
        if status != "ok"
    ]
    if failures:
        raise ValueError("invalid fulltext_paths: " + "; ".join(failures))


def _apply_payload_overrides(config: AgentConfig, payload: dict[str, Any]) -> AgentConfig:
    _validate_payload_llm_connection(payload, config.llm)
    _validate_payload_fulltext_paths(payload)
    llm = config.llm
    if _has_payload_value(payload, "llm_provider"):
        llm = replace(llm, provider=str(payload["llm_provider"]))
    if _has_payload_value(payload, "llm_base_url"):
        llm = replace(
            llm,
            base_url=str(payload["llm_base_url"]).strip(),
            api_key="",
        )
    if _has_payload_value(payload, "llm_model"):
        llm = replace(llm, model=str(payload["llm_model"]).strip())
    if _has_payload_value(payload, "llm_api_key"):
        llm = replace(llm, api_key=str(payload["llm_api_key"]).strip())
    if _has_payload_value(payload, "llm_max_calls"):
        llm = replace(llm, max_calls=int(payload["llm_max_calls"]))
    if _has_payload_value(payload, "llm_max_prompt_chars"):
        llm = replace(llm, max_prompt_chars=int(payload["llm_max_prompt_chars"]))
    if _has_payload_value(payload, "llm_input_cost_per_million_tokens"):
        llm = replace(llm, input_cost_per_million_tokens=float(payload["llm_input_cost_per_million_tokens"]))
    if _has_payload_value(payload, "llm_output_cost_per_million_tokens"):
        llm = replace(llm, output_cost_per_million_tokens=float(payload["llm_output_cost_per_million_tokens"]))
    if llm is not config.llm:
        config = replace(config, llm=llm)

    literature = config.literature
    if _has_payload_value(payload, "literature_provider"):
        literature = replace(literature, provider=str(payload["literature_provider"]))
    if _has_payload_value(payload, "literature_sources"):
        literature = replace(literature, sources=_list_from_payload(payload["literature_sources"]))
    if _has_payload_value(payload, "extra_search_queries"):
        literature = replace(literature, extra_search_queries=_list_from_lines(payload["extra_search_queries"]))
    if _has_payload_value(payload, "seed_papers"):
        literature = replace(literature, seed_papers=_list_from_lines(payload["seed_papers"]))
    if _has_payload_value(payload, "fulltext_paths"):
        literature = replace(literature, fulltext_paths=_list_from_lines(payload["fulltext_paths"]))
    if _has_payload_value(payload, "max_papers"):
        literature = replace(literature, max_papers=int(payload["max_papers"]))
    if _has_payload_value(payload, "literature_timeout_seconds"):
        literature = replace(literature, timeout_seconds=int(payload["literature_timeout_seconds"]))
    if _has_payload_value(payload, "max_search_queries"):
        literature = replace(literature, max_search_queries=int(payload["max_search_queries"]))
    if _has_payload_value(payload, "min_relevance"):
        literature = replace(literature, min_relevance=float(payload["min_relevance"]))
    if _has_payload_value(payload, "semantic_scholar_api_key"):
        literature = replace(literature, semantic_scholar_api_key=str(payload["semantic_scholar_api_key"]).strip())
    if _has_payload_value(payload, "openalex_api_key"):
        literature = replace(literature, openalex_api_key=str(payload["openalex_api_key"]).strip())
    if _has_payload_value(payload, "literature_contact_email"):
        literature = replace(literature, contact_email=str(payload["literature_contact_email"]).strip())
    if literature is not config.literature:
        config = replace(config, literature=literature)

    ideation = config.ideation
    if _has_payload_value(payload, "max_ideas"):
        ideation = replace(ideation, max_ideas=int(payload["max_ideas"]))
    if ideation is not config.ideation:
        config = replace(config, ideation=ideation)

    execution = config.execution
    if _has_payload_value(payload, "execution_mode"):
        execution = replace(execution, mode=str(payload["execution_mode"]))
    if _has_payload_value(payload, "timeout_seconds"):
        execution = replace(execution, timeout_seconds=int(payload["timeout_seconds"]))
    if _has_payload_value(payload, "allowed_commands"):
        allowed_commands = payload["allowed_commands"]
        if isinstance(allowed_commands, str):
            allowed_commands = [item.strip() for item in allowed_commands.split(",") if item.strip()]
        execution = replace(execution, allowed_commands=list(allowed_commands))
    if _has_payload_value(payload, "execution_repeats"):
        execution = replace(execution, repeats=int(payload["execution_repeats"]))
    if _has_payload_value(payload, "benchmark_manifests"):
        execution = replace(execution, benchmark_manifest_paths=_list_from_lines(payload["benchmark_manifests"]))
    if execution is not config.execution:
        config = replace(config, execution=execution)

    paper = config.paper
    if _has_payload_value(payload, "target_venue"):
        paper = replace(paper, target_venue=str(payload["target_venue"]))
    if _has_payload_value(payload, "paper_style"):
        paper = replace(paper, style=str(payload["paper_style"]))
    if paper is not config.paper:
        config = replace(config, paper=paper)
    paper_grade_updates = _paper_grade_payload_updates(payload)
    if paper_grade_updates:
        config = replace(config, paper_grade=replace(config.paper_grade, **paper_grade_updates))
    release = config.release
    release_fields = {
        "release_code_repository_url": "code_repository_url",
        "release_code_archive_doi": "code_archive_doi",
        "release_code_license": "code_license",
        "release_code_version": "code_version",
        "release_data_repository_url": "data_repository_url",
        "release_data_archive_doi": "data_archive_doi",
        "release_data_access_statement": "data_access_statement",
        "release_environment_url": "environment_url",
        "release_notes": "release_notes",
    }
    release_updates: dict[str, str] = {}
    for payload_key, field_name in release_fields.items():
        if _has_payload_value(payload, payload_key):
            release_updates[field_name] = str(payload[payload_key]).strip()
    if release_updates:
        release = replace(release, **release_updates)
    if release is not config.release:
        config = replace(config, release=release)
    human = config.human
    if _has_payload_value(payload, "human_notes"):
        human = replace(human, notes=_list_from_lines(payload["human_notes"]))
    if _has_payload_value(payload, "human_constraints"):
        human = replace(human, constraints=_list_from_lines(payload["human_constraints"]))
    if _has_payload_value(payload, "human_success_criteria"):
        human = replace(human, success_criteria=_list_from_lines(payload["human_success_criteria"]))
    if _has_payload_value(payload, "human_resource_limits"):
        human = replace(human, resource_limits=_list_from_lines(payload["human_resource_limits"]))
    if _has_payload_value(payload, "human_risks"):
        human = replace(human, risks=_list_from_lines(payload["human_risks"]))
    if human is not config.human:
        config = replace(config, human=human)
    multi_agent_keys = {
        "multi_agent",
        "multi_agent_enabled",
        "agent_models",
        "agent_skills",
        "agent_mcp_servers",
        "agent_enabled",
        "task_models",
        "mcp_servers",
        "max_tool_rounds",
        "tool_timeout_seconds",
        "max_tool_output_chars",
    }
    if any(key in payload for key in multi_agent_keys):
        config = replace(
            config,
            multi_agent=_multi_agent_config_from_payload(payload, config.multi_agent),
        )
    return config


def _has_payload_value(payload: dict[str, Any], key: str) -> bool:
    if key not in payload:
        return False
    value = payload[key]
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def _multi_agent_config_from_data(value: Any) -> MultiAgentConfig:
    data = dict(value or {}) if isinstance(value, dict) else {}
    roles_value = data.pop("roles", [])
    servers_value = data.pop("mcp_servers", [])
    task_models = data.get("task_models") if isinstance(data.get("task_models"), dict) else {}
    data["task_models"] = {
        str(stage).strip(): str(model).strip()
        for stage, model in task_models.items()
        if str(stage).strip() and str(model).strip()
    }
    return MultiAgentConfig(
        roles=[AgentRoleConfig(**dict(item)) for item in roles_value if isinstance(item, dict)],
        mcp_servers=[MCPServerConfig(**dict(item)) for item in servers_value if isinstance(item, dict)],
        **data,
    )


def _multi_agent_config_from_payload(
    payload: dict[str, Any],
    current: MultiAgentConfig | None = None,
) -> MultiAgentConfig:
    base = current or MultiAgentConfig()
    nested = payload.get("multi_agent") if isinstance(payload.get("multi_agent"), dict) else {}
    enabled = base.enabled
    if "enabled" in nested:
        enabled = _bool_from_payload(nested.get("enabled"))
    if "multi_agent_enabled" in payload:
        enabled = _bool_from_payload(payload.get("multi_agent_enabled"))

    existing_roles = {role.agent_id: role for role in base.roles}
    nested_roles = nested.get("roles") if isinstance(nested.get("roles"), list) else []
    for item in nested_roles:
        if isinstance(item, dict) and str(item.get("agent_id") or "").strip():
            role = AgentRoleConfig(**dict(item))
            existing_roles[role.agent_id] = role
    role_models = _object_from_payload(payload.get("agent_models"))
    role_skills = _object_from_payload(payload.get("agent_skills"))
    role_servers = _object_from_payload(payload.get("agent_mcp_servers"))
    role_enabled = _object_from_payload(payload.get("agent_enabled"))
    for agent_id in set(role_models) | set(role_skills) | set(role_servers) | set(role_enabled):
        normalized = str(agent_id).strip()
        role = existing_roles.get(normalized, AgentRoleConfig(agent_id=normalized))
        model = str(role_models.get(agent_id, role.model) or "").strip()
        if len(model) > 200 or any(char in model for char in "\r\n\x00"):
            raise ValueError(f"invalid model override for agent {normalized}")
        skills = _string_list_value(role_skills[agent_id]) if agent_id in role_skills else role.skills
        servers = _string_list_value(role_servers[agent_id]) if agent_id in role_servers else role.mcp_servers
        is_enabled = _bool_from_payload(role_enabled[agent_id]) if agent_id in role_enabled else role.enabled
        existing_roles[normalized] = AgentRoleConfig(
            agent_id=normalized,
            model=model,
            enabled=is_enabled,
            skills=skills,
            mcp_servers=servers,
        )

    task_models = dict(base.task_models)
    nested_task_models = nested.get("task_models") if isinstance(nested.get("task_models"), dict) else {}
    flat_task_models = _object_from_payload(payload.get("task_models"))
    if nested_task_models or flat_task_models or "task_models" in payload:
        task_models = {
            str(stage).strip(): str(model).strip()
            for stage, model in {**nested_task_models, **flat_task_models}.items()
            if str(stage).strip() and str(model).strip()
        }
    if any(len(model) > 200 or any(char in model for char in "\r\n\x00") for model in task_models.values()):
        raise ValueError("invalid task model override")

    servers = list(base.mcp_servers)
    if "mcp_servers" in nested:
        values = nested.get("mcp_servers")
        if not isinstance(values, list):
            raise ValueError("multi_agent.mcp_servers must be a list")
        servers = [MCPServerConfig(**dict(item)) for item in values if isinstance(item, dict)]
    if "mcp_servers" in payload:
        values = payload.get("mcp_servers")
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except json.JSONDecodeError as exc:
                raise ValueError("mcp_servers must be valid JSON") from exc
        if not isinstance(values, list):
            raise ValueError("mcp_servers must be a list")
        servers = [MCPServerConfig(**dict(item)) for item in values if isinstance(item, dict)]

    scalar_values = {
        "max_tool_rounds": int(nested.get("max_tool_rounds", base.max_tool_rounds)),
        "tool_timeout_seconds": int(nested.get("tool_timeout_seconds", base.tool_timeout_seconds)),
        "max_tool_output_chars": int(nested.get("max_tool_output_chars", base.max_tool_output_chars)),
    }
    for flat_key, field_name in [
        ("max_tool_rounds", "max_tool_rounds"),
        ("tool_timeout_seconds", "tool_timeout_seconds"),
        ("max_tool_output_chars", "max_tool_output_chars"),
    ]:
        if flat_key in payload:
            scalar_values[field_name] = int(payload[flat_key])
    result = MultiAgentConfig(
        enabled=enabled,
        roles=list(existing_roles.values()),
        task_models=task_models,
        mcp_servers=servers,
        **scalar_values,
    )
    issues = validate_multi_agent_tools(result, ROOT)
    if issues:
        raise ValueError("invalid multi-agent configuration: " + "; ".join(issues))
    return result


def _object_from_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("configuration object must be valid JSON") from exc
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("configuration value must be an object")
    return {}


def _string_list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _config_from_payload(payload: dict[str, Any]) -> AgentConfig:
    _validate_payload_llm_connection(payload)
    _validate_payload_fulltext_paths(payload)
    allowed_commands = payload.get("allowed_commands", ["python3", "pytest"])
    if isinstance(allowed_commands, str):
        allowed_commands = [item.strip() for item in allowed_commands.split(",") if item.strip()]
    payload_base_url = str(payload.get("llm_base_url", "")).strip()
    return AgentConfig(
        llm=LLMConfig(
            provider=str(payload.get("llm_provider", "openai-compatible")),
            base_url=payload_base_url,
            api_key=str(payload.get("llm_api_key", "")).strip(),
            model=str(payload.get("llm_model", "")).strip(),
            max_calls=int(payload.get("llm_max_calls") or 0),
            max_prompt_chars=int(payload.get("llm_max_prompt_chars") or 0),
            input_cost_per_million_tokens=float(payload.get("llm_input_cost_per_million_tokens") or 0.0),
            output_cost_per_million_tokens=float(payload.get("llm_output_cost_per_million_tokens") or 0.0),
        ),
        literature=LiteratureConfig(
            provider=str(payload.get("literature_provider", "offline")),
            max_papers=int(payload.get("max_papers", 8)),
            sources=_list_from_payload(payload.get("literature_sources", ["semantic_scholar", "openalex", "arxiv", "crossref"])),
            extra_search_queries=_list_from_lines(payload.get("extra_search_queries", "")),
            seed_papers=_list_from_lines(payload.get("seed_papers", "")),
            fulltext_paths=_list_from_lines(payload.get("fulltext_paths", "")),
            timeout_seconds=int(payload.get("literature_timeout_seconds", 12)),
            max_search_queries=int(payload.get("max_search_queries", 4)),
            min_relevance=float(payload.get("min_relevance", 0.24)),
            semantic_scholar_api_key=str(payload.get("semantic_scholar_api_key", "")).strip(),
            openalex_api_key=str(payload.get("openalex_api_key", "")).strip(),
            contact_email=str(payload.get("literature_contact_email", "")).strip(),
        ),
        ideation=IdeationConfig(max_ideas=int(payload.get("max_ideas", 5))),
        execution=ExecutionConfig(
            mode=str(payload.get("execution_mode", "simulated")),
            timeout_seconds=int(payload.get("timeout_seconds", 300)),
            allowed_commands=list(allowed_commands),
            repeats=int(payload.get("execution_repeats", 5)),
            benchmark_manifest_paths=_list_from_lines(payload.get("benchmark_manifests", "")),
        ),
        paper=PaperConfig(
            target_venue=str(payload.get("target_venue", "workshop")),
            style=str(payload.get("paper_style", "concise")),
        ),
        paper_grade=_paper_grade_config_from_payload(payload),
        release=ReleaseConfig(
            code_repository_url=str(payload.get("release_code_repository_url", "")).strip(),
            code_archive_doi=str(payload.get("release_code_archive_doi", "")).strip(),
            code_license=str(payload.get("release_code_license", "")).strip(),
            code_version=str(payload.get("release_code_version", "")).strip(),
            data_repository_url=str(payload.get("release_data_repository_url", "")).strip(),
            data_archive_doi=str(payload.get("release_data_archive_doi", "")).strip(),
            data_access_statement=str(payload.get("release_data_access_statement", "")).strip(),
            environment_url=str(payload.get("release_environment_url", "")).strip(),
            release_notes=str(payload.get("release_notes", "")).strip(),
        ),
        human=HumanConfig(
            notes=_list_from_lines(payload.get("human_notes", "")),
            constraints=_list_from_lines(payload.get("human_constraints", "")),
            success_criteria=_list_from_lines(payload.get("human_success_criteria", "")),
            resource_limits=_list_from_lines(payload.get("human_resource_limits", "")),
            risks=_list_from_lines(payload.get("human_risks", "")),
        ),
        multi_agent=_multi_agent_config_from_payload(payload),
    )


_PAPER_GRADE_PAYLOAD_INT_FIELDS = (
    "min_literature_sources",
    "min_successful_literature_sources",
    "min_seed_papers",
    "min_doi_url_seed_papers",
    "min_curated_seed_roles",
    "min_benchmark_roles",
    "min_execution_repeats",
)


def _paper_grade_config_from_payload(payload: dict[str, Any]) -> PaperGradeConfig:
    return PaperGradeConfig(**_paper_grade_payload_updates(payload))


def _paper_grade_payload_updates(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    nested = payload.get("paper_grade") if isinstance(payload.get("paper_grade"), dict) else {}
    if _has_payload_value(nested, "enabled"):
        updates["enabled"] = _bool_from_payload(nested.get("enabled"))
    if _has_payload_value(payload, "paper_grade_enabled"):
        updates["enabled"] = _bool_from_payload(payload.get("paper_grade_enabled"))
    for field_name in _PAPER_GRADE_PAYLOAD_INT_FIELDS:
        if _has_payload_value(nested, field_name):
            updates[field_name] = int(nested[field_name])
        flat_key = f"paper_grade_{field_name}"
        if _has_payload_value(payload, flat_key):
            updates[field_name] = int(payload[flat_key])
    return updates


def _bool_from_payload(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _list_from_payload(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _public_llm_stage_ids(value: Any) -> list[str]:
    allowed = {
        "research_planning",
        "literature_synthesis",
        "idea_generation",
        "experiment_planning",
        "paper_writing",
        "paper_review_loop",
        "paper_revision",
        "online_search_query_planning",
    }
    return [item for item in _list_from_payload(value) if item in allowed]


def _list_from_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        key = item.lower()
        if not item or key in seen:
            continue
        result.append(item)
        seen.add(key)
    return result


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


STORE = RunStore()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="research-agent-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), ResearchAgentHandler)
    try:
        _configure_web_server(server, args.host)
    except ValueError as exc:
        server.server_close()
        parser.error(str(exc))
    print(f"Research Agent Web UI: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
