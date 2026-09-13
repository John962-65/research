from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import time

from .analysis import analysis_matches_execution_mode, analyze_results, render_analysis_markdown
from .agent_runtime import RoleModelRouter, build_agent_runtime_llm
from .artifacts import read_json, write_json, write_text, cell as _cell, sha256_text as _sha256_text, utc_now as _utc_now
from .ablation_plan import ABLATION_PLAN_JSON, ABLATION_PLAN_MD, write_ablation_plan_artifacts
from .agent_observability_audit import AGENT_OBSERVABILITY_AUDIT_JSON, AGENT_OBSERVABILITY_AUDIT_MD, write_agent_observability_audit_artifacts
from .agent_stage_contract import AGENT_STAGE_CONTRACT_JSON, AGENT_STAGE_CONTRACT_MD, write_agent_stage_contract_artifacts
from .agent_trajectory import AGENT_TRAJECTORY_JSON, AGENT_TRAJECTORY_MD, write_agent_trajectory_artifacts
from .ai_disclosure import AI_DISCLOSURE_JSON, AI_DISCLOSURE_MD, render_ai_disclosure_markdown, write_ai_disclosure_artifacts
from .benchmark_adapter import BENCHMARK_ADAPTER_JSON, BENCHMARK_ADAPTER_MD
from .benchmark_evidence_audit import BENCHMARK_EVIDENCE_AUDIT_JSON, BENCHMARK_EVIDENCE_AUDIT_MD, write_benchmark_evidence_audit_artifacts
from .benchmark_plan import BENCHMARK_PLAN_JSON, BENCHMARK_PLAN_MD, write_benchmark_plan_artifacts
from .benchmark_readiness import BENCHMARK_READINESS_JSON, BENCHMARK_READINESS_MD, write_benchmark_readiness_artifacts
from .benchmark_result_schema_audit import (
    BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
    BENCHMARK_RESULT_SCHEMA_AUDIT_MD,
    write_benchmark_result_schema_audit_artifacts,
)
from .citation_audit import audit_citations, render_citation_audit_markdown
from .citation_coverage import CITATION_COVERAGE_JSON, CITATION_COVERAGE_MD, render_citation_coverage_markdown, write_citation_coverage_artifacts
from .citation_grounding import CITATION_GROUNDING_JSON, CITATION_GROUNDING_MD, render_citation_grounding_markdown, write_citation_grounding_artifacts
from .claim_boundary_preflight import CLAIM_BOUNDARY_PREFLIGHT_JSON, CLAIM_BOUNDARY_PREFLIGHT_MD, render_claim_boundary_preflight_markdown, write_claim_boundary_preflight_artifacts
from .claim_consistency import CLAIM_CONSISTENCY_JSON, CLAIM_CONSISTENCY_MD, render_claim_consistency_markdown, write_claim_consistency_artifacts
from .claim_traceability import CLAIM_TRACEABILITY_JSON, CLAIM_TRACEABILITY_MD, render_claim_traceability_markdown, write_claim_traceability_artifacts
from .code_data_availability import render_code_data_availability_markdown, write_code_data_availability_artifacts
from .config import AgentConfig, MultiAgentConfig, PaperGradeConfig
from .experiments import (
    EXPERIMENT_RUNBOOK_JSON,
    EXPERIMENT_RUNBOOK_MD,
    plan_experiment,
    render_experiment_plan_markdown,
    run_experiments,
    validate_execution_config,
    write_experiment_runbook,
)
from .experiment_audit import EXPERIMENT_AUDIT_JSON, EXPERIMENT_AUDIT_MD, write_experiment_audit_artifacts
from .execution_safety import (
    EXECUTION_SAFETY_AUDIT_JSON,
    EXECUTION_SAFETY_AUDIT_MD,
    benchmark_source_artifacts,
    execution_source_binding_matches,
    write_execution_safety_audit_artifacts,
)
from .experiment_decision import EXPERIMENT_DECISION_JSON, EXPERIMENT_DECISION_MD, write_experiment_decision_artifacts
from .experiment_manager import EXPERIMENT_MANAGER_JSON, EXPERIMENT_MANAGER_MD, experiment_manager_constraints, render_experiment_manager_markdown, write_experiment_manager_artifacts
from .exploration_map import (
    EXPLORATION_MAP_JSON,
    EXPLORATION_MAP_MD,
    EXPLORATION_MAP_SVG,
    render_exploration_map_markdown,
    render_exploration_map_svg,
    selected_idea,
    write_exploration_map_artifacts,
)
from .evidence_integrity import EVIDENCE_INTEGRITY_JSON, EVIDENCE_INTEGRITY_MD, assess_evidence_integrity, write_evidence_integrity_artifacts
from .final_handoff import FINAL_HANDOFF_JSON, FINAL_HANDOFF_MD, write_final_handoff_artifacts
from .final_readiness import build_final_readiness_report, render_final_readiness_markdown
from .failure_analysis import FAILURE_ANALYSIS_JSON, FAILURE_ANALYSIS_MD, write_failure_analysis_artifacts
from .fulltext_corpus import FULLTEXT_CORPUS_JSON, FULLTEXT_CORPUS_MD, write_fulltext_corpus_artifacts
from .human_brief import HUMAN_BRIEF_JSON, HUMAN_BRIEF_MD, human_brief_agent_text, load_human_brief, render_human_brief_markdown, write_human_brief_artifacts
from .human_gate_audit import HUMAN_GATE_AUDIT_JSON, HUMAN_GATE_AUDIT_MD, write_human_gate_audit_artifacts
from .hypothesis_outcome import HYPOTHESIS_OUTCOME_JSON, HYPOTHESIS_OUTCOME_MD, write_hypothesis_outcome_artifacts
from .idea_experiment_contract import (
    CONTRACT_HISTORY_JSON,
    IDEA_EXPERIMENT_CONTRACT_JSON,
    IDEA_EXPERIMENT_CONTRACT_MD,
    append_contract_history,
    write_idea_experiment_contract_artifacts,
)
from .idea_audit import IDEA_AUDIT_JSON, IDEA_AUDIT_MD, render_idea_audit_markdown, write_idea_audit_artifacts
from .ideation import generate_ideas, render_ideas_markdown
from .iteration_plan import ITERATION_PLAN_JSON, ITERATION_PLAN_MD, write_iteration_plan_artifacts
from .literature import literature_source_health_report, render_literature_markdown, render_literature_source_health_markdown, run_literature_review
from .literature_search_strategy import render_literature_search_strategy_markdown
from .literature_context import (
    apply_citation_audit_to_context,
    apply_literature_audits_to_context,
    build_literature_context,
    export_bibtex,
    export_ris,
    render_literature_context_markdown,
    render_review_gate_markdown,
)
from .literature_coverage import LITERATURE_COVERAGE_JSON, LITERATURE_COVERAGE_MD, write_literature_coverage_artifacts
from .literature_evidence_mix import LITERATURE_EVIDENCE_MIX_JSON, LITERATURE_EVIDENCE_MIX_MD, write_literature_evidence_mix_artifacts
from .literature_evidence_contract import LITERATURE_EVIDENCE_CONTRACT_JSON, LITERATURE_EVIDENCE_CONTRACT_MD, write_literature_evidence_contract_artifacts
from .literature_gate_decision import LITERATURE_GATE_DECISION_JSON, LITERATURE_GATE_DECISION_MD, build_literature_context_gate_report, write_literature_gate_decision_artifacts
from .literature_quality import assess_literature_quality, filter_review_by_quality, render_literature_quality_markdown
from .literature_metadata_audit import LITERATURE_METADATA_AUDIT_JSON, LITERATURE_METADATA_AUDIT_MD, write_literature_metadata_audit_artifacts
from .literature_rerank import LITERATURE_RERANK_JSON, LITERATURE_RERANK_MD, write_literature_rerank_artifacts
from .literature_rescue_plan import LITERATURE_RESCUE_PLAN_JSON, LITERATURE_RESCUE_PLAN_MD, write_literature_rescue_plan_artifacts
from .literature_rescue_execution import (
    LITERATURE_RESCUE_EXECUTION_JSON,
    LITERATURE_RESCUE_EXECUTION_MD,
    render_literature_rescue_execution_markdown,
    write_literature_rescue_execution_artifacts,
)
from .literature_search_feedback import LITERATURE_SEARCH_FEEDBACK_JSON, LITERATURE_SEARCH_FEEDBACK_MD, write_literature_search_feedback_artifacts
from .literature_snowball import LITERATURE_SNOWBALL_JSON, LITERATURE_SNOWBALL_MD, write_literature_snowball_artifacts
from .llm_observability_summary import LLM_OBSERVABILITY_SUMMARY_JSON, LLM_OBSERVABILITY_SUMMARY_MD, write_llm_observability_summary_artifacts
from .llm_runtime_contract import LLM_RUNTIME_CONTRACT_JSON, LLM_RUNTIME_CONTRACT_MD, write_llm_runtime_contract_artifacts
from .llm_trace import LLM_TRACE_JSON, LLM_TRACE_MD
from .llm_trace_audit import LLM_TRACE_AUDIT_JSON, LLM_TRACE_AUDIT_MD, write_llm_trace_audit_artifacts
from .multi_agent_assignment import MULTI_AGENT_ASSIGNMENT_JSON, MULTI_AGENT_ASSIGNMENT_MD, agent_roles_for_text, render_multi_agent_assignment_markdown, write_multi_agent_assignment_artifacts
from .multi_agent_deliberation import MULTI_AGENT_DELIBERATION_JSON, MULTI_AGENT_DELIBERATION_MD, render_multi_agent_deliberation_markdown, write_multi_agent_deliberation_artifacts
from .agent_verdict import INDEPENDENT_DELIBERATION_JSON, ROLE_EVIDENCE_VIEWS, run_independent_deliberation, verdicts_match_current_inputs
from .provenance import active_revision
from .workflow_state import WorkflowEngine, NodeOutcome
from .workflow_graph import WORKFLOW_NODES
from .gate_aggregator import GATE_RULE_VERSION, aggregate_final_decision, load_human_override, write_gate_decision_artifacts
from .evidence_snapshot import SnapshotError, load_review_input_snapshot, payload_sha256, verify_snapshot
from .model_failure import record_model_stage_source
from .run_budget import RunBudgetExhausted, ensure_budget, record_execution
from .multi_agent_handoff_audit import MULTI_AGENT_HANDOFF_AUDIT_JSON, MULTI_AGENT_HANDOFF_AUDIT_MD, write_multi_agent_handoff_audit_artifacts
from .multi_agent_paper_audit import MULTI_AGENT_PAPER_AUDIT_JSON, MULTI_AGENT_PAPER_AUDIT_MD, render_multi_agent_paper_audit_markdown, write_multi_agent_paper_audit_artifacts
from .query_execution_audit import QUERY_EXECUTION_AUDIT_JSON, QUERY_EXECUTION_AUDIT_MD, write_query_execution_audit_artifacts
from .research_gap_map import RESEARCH_GAP_MAP_JSON, RESEARCH_GAP_MAP_MD, render_research_gap_map_markdown, write_research_gap_map_artifacts
from .models import (
    Analysis,
    CitationEntry,
    CitationGroundingItem,
    CitationGroundingReport,
    BenchmarkCandidate,
    BenchmarkPlan,
    ClaimConsistencyCheck,
    ClaimConsistencyReport,
    ClaimSupport,
    CodeDataAvailabilityItem,
    CodeDataAvailabilityReport,
    ClaimTraceabilityItem,
    ClaimTraceabilityReport,
    EvidenceChunk,
    ExperimentCommand,
    ExperimentPlan,
    ExperimentResult,
    ExplorationBranch,
    ExplorationMap,
    FullTextCorpus,
    FullTextDocument,
    FinalReadinessReport,
    LiteratureContext,
    LiteratureReview,
    Paper,
    PaperClaimAudit,
    PaperRewriteReport,
    PaperRevisionTaskResult,
    PaperReview,
    PaperRevisionPlan,
    ResearchPlan,
    ResearchIdea,
    ResultsPresentationCheck,
    ResultsPresentationReport,
    ReviewGate,
    RevisionTask,
    SubmissionCheckItem,
    SubmissionCheckReport,
)
from .novelty_audit import NOVELTY_AUDIT_JSON, NOVELTY_AUDIT_MD, write_novelty_audit_artifacts
from .open_source_lessons import (
    OPEN_SOURCE_LESSONS_JSON,
    OPEN_SOURCE_LESSONS_MD,
    OpenSourceLesson,
    OpenSourceLessonsReport,
    OpenSourceProjectEvidence,
    OpenSourceProjectProfile,
    render_open_source_lessons_markdown,
    write_open_source_lessons_artifacts,
)
from .open_source_compliance import OPEN_SOURCE_COMPLIANCE_JSON, OPEN_SOURCE_COMPLIANCE_MD, write_open_source_compliance_artifacts
from .paper_rewrite import render_rewrite_report_markdown, revise_paper_draft
from .paper_review import render_paper_review_markdown, review_paper_draft
from .paper_review_calibration import PAPER_REVIEW_CALIBRATION_JSON, PAPER_REVIEW_CALIBRATION_MD, write_paper_review_calibration_artifacts
from .paper_revision import build_paper_revision_plan, render_paper_revision_plan_markdown
from .preflight import PREFLIGHT_JSON, PREFLIGHT_MD, run_preflight, write_preflight_artifacts
from .prior_run_lessons import (
    PRIOR_RUN_LESSONS_JSON,
    PRIOR_RUN_LESSONS_MD,
    PriorRunLesson,
    PriorRunLessonsReport,
    render_prior_run_lessons_markdown,
    write_prior_run_lessons_artifacts,
)
from .prior_run_library import (
    PRIOR_RUN_LIBRARY_JSON,
    PRIOR_RUN_LIBRARY_MD,
    PriorRunLibraryReference,
    PriorRunLibraryReport,
    render_prior_run_library_markdown,
    write_prior_run_library_artifacts,
)
from .preregistration import PREREGISTRATION_JSON, PREREGISTRATION_MD, write_preregistration_artifacts
from .provenance import RunManifestRecorder
from .release_metadata import RELEASE_METADATA_JSON, RELEASE_METADATA_MD, write_release_metadata_artifacts
from .repair_resume import (
    REPAIR_RESUME_PLAN_JSON,
    REPAIR_RESUME_PLAN_MD,
    apply_repair_resume_recommendations,
    build_repair_resume_plan,
    missing_repair_resume_required_release_values,
    prepare_repair_resume,
    render_repair_resume_plan_markdown,
    write_repair_resume_plan_artifacts,
)
from .repair_resolution_audit import REPAIR_RESOLUTION_AUDIT_JSON, REPAIR_RESOLUTION_AUDIT_MD, write_repair_resolution_audit_artifacts
from .repair_queue import REPAIR_QUEUE_JSON, REPAIR_QUEUE_MD, write_repair_queue_artifacts
from .research_plan import build_research_plan, render_research_plan_markdown
from .result_validation import RESULT_VALIDATION_JSON, RESULT_VALIDATION_MD, write_result_validation_artifacts
from .results_presentation import RESULTS_PRESENTATION_JSON, RESULTS_PRESENTATION_MD, render_results_presentation_markdown, write_results_presentation_artifacts
from .revision_response_audit import REVISION_RESPONSE_AUDIT_JSON, REVISION_RESPONSE_AUDIT_MD, render_revision_response_audit_markdown, write_revision_response_audit_artifacts
from .review_constraints import REVIEW_CONSTRAINTS_JSON, REVIEW_CONSTRAINTS_MD, build_review_constraints, constraints_agent_text, render_review_constraints_markdown
from .review_constraint_compliance import (
    REVIEW_CONSTRAINT_COMPLIANCE_JSON,
    REVIEW_CONSTRAINT_COMPLIANCE_MD,
    write_review_constraint_compliance_artifacts,
)
from .review_revision_plan import REVIEW_REVISION_PLAN_JSON, REVIEW_REVISION_PLAN_MD, write_review_revision_plan_artifacts
from .run_integrity_audit import RUN_INTEGRITY_AUDIT_JSON, RUN_INTEGRITY_AUDIT_MD, write_run_integrity_audit_artifacts
from .run_economics_audit import RUN_ECONOMICS_AUDIT_JSON, RUN_ECONOMICS_AUDIT_MD, write_run_economics_audit_artifacts
from .scorecard import RESEARCH_SCORECARD_JSON, RESEARCH_SCORECARD_MD, write_research_scorecard_artifacts
from .seed_paper_intake import SEED_PAPER_INTAKE_JSON, SEED_PAPER_INTAKE_MD, write_seed_paper_intake_artifacts
from .statistics import (
    STATISTICS_FIGURE_JSON,
    STATISTICS_FIGURE_SVG,
    build_statistics_report,
    render_statistics_markdown,
    write_statistics_figure_artifacts,
)
from .submission_check import SUBMISSION_CHECK_JSON, SUBMISSION_CHECK_MD, render_submission_check_markdown, write_submission_check_artifacts
from .submission_package import SUBMISSION_PACKAGE_JSON, SUBMISSION_PACKAGE_MD, SUBMISSION_PACKAGE_ZIP, write_submission_package_artifacts
from .writing import markdown_to_latex, write_paper_markdown
from .run_lease import acquire_run_lease
from .workflow_state import append_node_event, append_node_events, stage_to_node_events
from .workflow_graph import begin_workflow_node, update_workflow_stage


APPROVAL_FILENAME = "approval.json"
CANCEL_FILENAME = "cancel.json"
REVIEW_FEEDBACK_JSON = "01-review-feedback.json"
REVIEW_FEEDBACK_MD = "01-review-feedback.md"
CITATION_AUDIT_JSON = "01-citation-audit.json"
CITATION_AUDIT_MD = "01-citation-audit.md"
LITERATURE_SOURCE_HEALTH_JSON = "01-literature-source-health.json"
LITERATURE_SOURCE_HEALTH_MD = "01-literature-source-health.md"
LITERATURE_SEARCH_STRATEGY_JSON = "01-literature-search-strategy.json"
LITERATURE_SEARCH_STRATEGY_MD = "01-literature-search-strategy.md"
EXECUTION_APPROVAL_JSON = "03-execution-approval.json"
EXECUTION_APPROVAL_MD = "03-execution-approval.md"
REVISION_PLAN_JSON = "08-revision-plan.json"
REVISION_PLAN_MD = "08-revision-plan.md"
REVISED_PAPER_MD = "09-revised-paper.md"
REVISED_PAPER_TEX = "09-revised-paper.tex"
REVISION_REPORT_JSON = "09-revision-report.json"
REVISION_REPORT_MD = "09-revision-report.md"
REVISED_PAPER_REVIEW_JSON = "10-revised-paper-review.json"
REVISED_PAPER_REVIEW_MD = "10-revised-paper-review.md"
FINAL_READINESS_JSON = "10-final-readiness.json"
FINAL_READINESS_MD = "10-final-readiness.md"
CODE_DATA_AVAILABILITY_JSON = "10-code-data-availability.json"
CODE_DATA_AVAILABILITY_MD = "10-code-data-availability.md"
EXPERIMENT_REPAIR_REPORT_JSON = "06-experiment-repair-report.json"
EXPERIMENT_REPAIR_REPORT_MD = "06-experiment-repair-report.md"
CHECKPOINT_CONTRACT_JSON = "run-checkpoint-contract.json"


class PipelineCancelled(RuntimeError):
    def __init__(self, out_dir: Path, stage: str) -> None:
        self.out_dir = out_dir
        self.stage = stage
        super().__init__(f"Pipeline cancelled at stage '{stage}' in {out_dir}")


class PipelineReviewRevisionRequested(RuntimeError):
    def __init__(self, out_dir: Path, notes: str = "") -> None:
        self.out_dir = out_dir
        self.notes = notes
        super().__init__(f"Review revision requested in {out_dir}: {notes}")


_LITERATURE_CHAIN_KEYS = (
    "review",
    "rerank_report",
    "source_health",
    "query_execution_audit",
    "quality_report",
    "snowball_report",
    "curated_review",
    "metadata_audit",
    "seed_intake",
    "coverage_report",
    "evidence_mix_report",
    "rescue_report",
)


def _bind_literature_chain(chain: dict[str, Any]) -> list[Any]:
    return [chain[key] for key in _LITERATURE_CHAIN_KEYS]


def _run_literature_audit_chain(
    topic: str,
    config: AgentConfig,
    research_plan: ResearchPlan,
    review: Any,
    out_dir: Path,
    *,
    write_search_strategy: bool = True,
) -> dict[str, Any]:
    """Rerank the review and write every derived literature audit artifact.

    Shared by the full-run, review-revision-refresh, and rescue-retry paths;
    rescue execution (which may update the review) is orchestrated by the
    caller, which re-enters this chain when the review changed. Checkpoint
    resume keeps its own per-artifact guarded variants.
    """
    review, rerank_report = _write_reranked_literature(out_dir, review, research_plan)
    if write_search_strategy:
        write_literature_search_strategy_artifacts(out_dir, review)
    source_health = write_literature_source_health_artifacts(out_dir, review)
    query_execution_audit = write_query_execution_audit_artifacts(research_plan, review, rerank_report, source_health, out_dir)
    quality_report = assess_literature_quality(review)
    write_json(out_dir / "01-literature-quality.json", quality_report)
    write_text(out_dir / "01-literature-quality.md", render_literature_quality_markdown(quality_report))
    snowball_report = write_literature_snowball_artifacts(review, quality_report, out_dir)
    curated_review = filter_review_by_quality(review, quality_report)
    write_json(out_dir / "01-literature-curated.json", curated_review)
    write_text(out_dir / "01-literature-curated.md", render_literature_markdown(curated_review))
    metadata_audit = write_literature_metadata_audit_artifacts(review, curated_review, quality_report, out_dir)
    seed_intake = write_seed_paper_intake_artifacts(topic, config.literature, review, curated_review, quality_report, out_dir)
    coverage_report = write_literature_coverage_artifacts(research_plan, curated_review, out_dir)
    evidence_mix_report = write_literature_evidence_mix_artifacts(research_plan, review, curated_review, quality_report, coverage_report, out_dir)
    rescue_report = write_literature_rescue_plan_artifacts(research_plan, review, curated_review, quality_report, snowball_report, coverage_report, out_dir)
    return {
        "review": review,
        "rerank_report": rerank_report,
        "source_health": source_health,
        "query_execution_audit": query_execution_audit,
        "quality_report": quality_report,
        "snowball_report": snowball_report,
        "curated_review": curated_review,
        "metadata_audit": metadata_audit,
        "seed_intake": seed_intake,
        "coverage_report": coverage_report,
        "evidence_mix_report": evidence_mix_report,
        "rescue_report": rescue_report,
    }


def _finalize_gate_decision(
    topic: str,
    out_dir: Path,
    config: AgentConfig,
    llm,
    *,
    agent_deliberation: dict[str, Any],
    claim_consistency: dict[str, Any],
    citation_grounding: Any,
    revised_review,
    resume: bool,
) -> tuple[dict[str, Any], list[str]]:
    """GATE-02: aggregate deterministic audits, independent verdicts, and the
    human override into the one final gate decision; returns (decision, outputs).

    决策绑定评审输入快照（decision-contract §4）：稿件与结果文件哈希 +
    确定性审计全量内容进入审批摘要；恢复时独立评审只有在快照一致时才复用；
    提交前复核快照，材料在处理期间变化则丢弃本次决定并阻断（A05–A08）。
    """
    from dataclasses import asdict as _asdict, replace as _replace
    from .evidence_snapshot import (
        build_review_input_snapshot,
        snapshot_digest,
        verify_snapshot,
        write_review_input_snapshot,
    )

    revision = active_revision(out_dir)

    def _audit_payload(value: Any) -> dict[str, Any]:
        if is_dataclass(value) and not isinstance(value, dict):
            return _asdict(value)
        if isinstance(value, dict):
            return value
        return {"status": str(getattr(value, "status", "") or ""), "repr": str(value)[:2000]}

    def _review_payload(value: Any) -> dict[str, Any]:
        """复审全量内容入快照；status 从 decision 派生（保持原门禁语义）。"""
        if is_dataclass(value) and not isinstance(value, dict):
            payload = _asdict(value)
        elif isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {"decision": str(getattr(value, "decision", "") or "")}
        decision = str(payload.get("decision") or "")
        payload.setdefault(
            "status",
            "pass" if decision in {"accept", "accept_with_minor_revisions"} else "warn",
        )
        return payload

    def _safe_payload(value: Any, name: str, non_overridable: list[str]) -> dict[str, Any]:
        payload = _audit_payload(value)
        try:
            payload_sha256(payload)
        except SnapshotError:
            non_overridable.append("corrupted_input")
            return {
                "status": str(getattr(value, "status", "") or ""),
                "snapshot_invalid": "canonicalization_failed",
            }
        return payload

    non_overridable_reasons: list[str] = []
    # 复审第 2 项：快照必须覆盖独立评审真正读取的全部材料——每个角色的
    # 证据视图文件（statistics/experiment plan/context 等）与稿件、结果
    # 一起进入快照；文件缺失按 absent 记录，出现/变化都会改变摘要。
    file_inputs = {"09-revised-paper.md": "manuscript"}
    for name in sorted({item for paths in ROLE_EVIDENCE_VIEWS.values() for item in paths}):
        if (out_dir / name).exists():
            file_inputs.setdefault(name, "role_evidence")
    if (out_dir / "06-paper.md").exists():
        file_inputs["06-paper.md"] = "manuscript_source"
    if (out_dir / "04-results.json").exists():
        file_inputs["04-results.json"] = "experiment_results"

    def _build_snapshot() -> dict[str, Any]:
        return build_review_input_snapshot(
            out_dir,
            revision=revision,
            file_inputs=file_inputs,
            inline_inputs={
                "agent_deliberation": _safe_payload(agent_deliberation, "agent_deliberation", non_overridable_reasons),
                "claim_consistency": _safe_payload(claim_consistency, "claim_consistency", non_overridable_reasons),
                "citation_grounding": _safe_payload(citation_grounding, "citation_grounding", non_overridable_reasons),
                "revised_paper_review": _safe_payload(_review_payload(revised_review), "revised_paper_review", non_overridable_reasons),
            },
            rule_versions={"gate_rule": GATE_RULE_VERSION},
        )

    snapshot = _build_snapshot()
    non_overridable_reasons.extend(
        f"corrupted_input:{item.get('name')}"
        for item in snapshot.get("items", [])
        if isinstance(item, dict) and item.get("invalid")
    )
    write_review_input_snapshot(out_dir, snapshot)
    input_digest = snapshot_digest(snapshot)

    independent_report: dict[str, Any] | None = None
    independent_outputs: list[str] = []
    independent_path = out_dir / INDEPENDENT_DELIBERATION_JSON
    if config.multi_agent.enabled:
        if resume and independent_path.exists():
            existing = _read_dict(independent_path)
            # 恢复时仅在快照一致且每条 verdict 的输入证据包未变化时复用；
            # 稿件/统计/审计内容变化则重评（A06/复审第 2 项）。
            if (
                existing
                and existing.get("review_input_sha256") == input_digest
                and verdicts_match_current_inputs(existing, out_dir)
            ):
                independent_report = existing
        if independent_report is None:
            try:
                independent_report = run_independent_deliberation(
                    topic, out_dir, config, llm, review_input_sha256=input_digest
                )
                independent_outputs = [INDEPENDENT_DELIBERATION_JSON, "10-independent-deliberation.md"]
            except Exception as exc:
                independent_report = {
                    "schema_version": 1,
                    "independent_agent_execution": True,
                    "verdicts": [],
                    "status": "block",
                    "error": str(exc)[:280],
                    "review_input_sha256": input_digest,
                }

    def _aggregate(snapshot_dict: dict[str, Any], allow_override: bool, extra_blocking: list[str]) -> Any:
        # 多智能体开启时读取调用账本，对每张 pass/warn verdict 做存在性/
        # 成功状态/角色/响应哈希核验（A09）；失败票按阻断处理。
        llm_ledger: list[dict[str, Any]] | None = None
        if config.multi_agent.enabled:
            ledger_payload = _read_dict(out_dir / "run-llm-ledger.json")
            entries = ledger_payload.get("entries")
            llm_ledger = entries if isinstance(entries, list) else []
        decision = aggregate_final_decision(
            deterministic_audits={
                "agent_deliberation": agent_deliberation if isinstance(agent_deliberation, dict) else {},
                "claim_consistency": claim_consistency if isinstance(claim_consistency, dict) else {},
                "citation_grounding": _audit_payload(citation_grounding),
                "revised_paper_review": _review_payload(revised_review),
            },
            independent_deliberation=independent_report,
            expected_roles=sorted(ROLE_EVIDENCE_VIEWS) if config.multi_agent.enabled else [],
            revision=revision,
            human_override=load_human_override(out_dir) if allow_override else None,
            review_input_snapshot=snapshot_dict,
            non_overridable_reasons=non_overridable_reasons,
            llm_ledger=llm_ledger,
        )
        if extra_blocking:
            decision = _replace(
                decision,
                status="blocked",
                blocking_sources=[*decision.blocking_sources, *extra_blocking],
                overridden=False,
                override={},
            )
        return decision

    gate_decision = _aggregate(snapshot, True, [])
    # 提交前复核快照：处理期间材料变化 → 丢弃本次待提交决定（A08）。
    changed_inputs = verify_snapshot(out_dir, snapshot)
    if changed_inputs:
        fresh_snapshot = _build_snapshot()
        write_review_input_snapshot(out_dir, fresh_snapshot)
        gate_decision = _aggregate(
            fresh_snapshot,
            False,
            [f"snapshot:inputs_changed_during_processing:{name}" for name in changed_inputs[:4]],
        )
    write_gate_decision_artifacts(out_dir, gate_decision)

    return _asdict(gate_decision), independent_outputs


def run_pipeline(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    with acquire_run_lease(out_dir, "run", owner="pipeline"):
        return _run_pipeline_unlocked(topic, out_dir, config)


def _run_pipeline_unlocked(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _validate_or_create_checkpoint_contract(out_dir, topic, config)
    _write_run_config_snapshot(out_dir, config)
    manifest = RunManifestRecorder(out_dir, topic)
    _check_cancelled(out_dir, topic, manifest, "queued")
    if not (out_dir / PREFLIGHT_JSON).exists() or not (out_dir / PREFLIGHT_MD).exists():
        preflight = run_preflight(topic, config, ping_llm=False)
        write_preflight_artifacts(preflight, out_dir)
        manifest.record(
            "preflight",
            inputs=["run-config.json"],
            outputs=[PREFLIGHT_JSON, PREFLIGHT_MD],
            metrics={"status": preflight.status, "checks": len(preflight.checks)},
        )
    llm = build_agent_runtime_llm(config, Path(__file__).resolve().parents[2], out_dir)
    _check_cancelled(out_dir, topic, manifest, "started")
    citation_audit = None
    context = None
    coverage_report = None
    curated_review = None
    evidence_mix_report = None
    fulltext_corpus = None
    human_brief = None
    metadata_audit = None
    planning_context = None
    quality_report = None
    query_execution_audit = None
    rerank_report = None
    rescue_execution = None
    rescue_report = None
    research_plan = None
    review_constraints = None
    review_feedback = None
    seed_intake = None
    source_health = None

    def _node_research_planning():
        nonlocal human_brief, planning_context, research_plan
        write_text(out_dir / "00-question.md", f"# 研究问题\n\n{topic}")
        manifest.record("question", inputs=[], outputs=["00-question.md"], metrics={"topic_chars": len(topic)})
        _check_cancelled(out_dir, topic, manifest, "question")

        human_brief = write_human_brief_artifacts(topic, config.human, out_dir)
        prior_lessons = write_prior_run_lessons_artifacts(topic, out_dir.parent, out_dir)
        prior_library = write_prior_run_library_artifacts(topic, out_dir.parent, out_dir)
        open_source_lessons = write_open_source_lessons_artifacts(topic, out_dir)
        manifest.record(
            "human_brief",
            inputs=["run-config.json"],
            outputs=[HUMAN_BRIEF_JSON, HUMAN_BRIEF_MD],
            metrics={
                "status": human_brief.get("status"),
                "constraints": len(human_brief.get("constraints", []) if isinstance(human_brief.get("constraints"), list) else []),
                "success_criteria": len(human_brief.get("success_criteria", []) if isinstance(human_brief.get("success_criteria"), list) else []),
                "resource_limits": len(human_brief.get("resource_limits", []) if isinstance(human_brief.get("resource_limits"), list) else []),
            },
        )
        manifest.record(
            "prior_run_lessons",
            inputs=[],
            outputs=[PRIOR_RUN_LESSONS_JSON, PRIOR_RUN_LESSONS_MD],
            metrics={"status": prior_lessons.status, "lessons": len(prior_lessons.lessons), "analyzed_runs": prior_lessons.analyzed_runs},
        )
        manifest.record(
            "prior_run_library",
            inputs=[],
            outputs=[PRIOR_RUN_LIBRARY_JSON, PRIOR_RUN_LIBRARY_MD],
            metrics={"status": prior_library.status, "references": len(prior_library.references), "indexed_runs": prior_library.indexed_runs},
        )
        manifest.record(
            "open_source_lessons",
            inputs=[],
            outputs=[OPEN_SOURCE_LESSONS_JSON, OPEN_SOURCE_LESSONS_MD],
            metrics={"status": open_source_lessons.status, "lessons": len(open_source_lessons.lessons), "profiles": len(open_source_lessons.profiles)},
        )
        _write_state(out_dir, topic, "started")
        planning_context = _planning_context(
            str(human_brief.get("agent_prompt_text") or ""),
            prior_lessons.agent_prompt_text,
            prior_library.agent_prompt_text,
            open_source_lessons.agent_prompt_text,
        )
        research_plan = build_research_plan(topic, llm, prior_lessons=planning_context)
        write_json(out_dir / "00-research-plan.json", research_plan)
        write_text(out_dir / "00-research-plan.md", render_research_plan_markdown(research_plan))
        _write_state(out_dir, topic, "research_plan_completed")
        manifest.record(
            "research_plan",
            inputs=["00-question.md", HUMAN_BRIEF_JSON, PRIOR_RUN_LESSONS_JSON, PRIOR_RUN_LIBRARY_JSON, OPEN_SOURCE_LESSONS_JSON],
            outputs=["00-research-plan.json", "00-research-plan.md"],
            metrics={
                "domain": research_plan.domain,
                "queries": len(research_plan.search_queries),
                "benchmarks": len(research_plan.benchmarks),
                "baselines": len(research_plan.baselines),
            },
        )
        _check_cancelled(out_dir, topic, manifest, "research_plan_completed")

    def _node_literature_review():
        nonlocal coverage_report, curated_review, evidence_mix_report, fulltext_corpus, metadata_audit, quality_report, query_execution_audit, rerank_report, rescue_execution, rescue_report, seed_intake, source_health

        review = run_literature_review(topic, config.literature, llm, research_plan.search_queries)
        chain = _run_literature_audit_chain(topic, config, research_plan, review, out_dir)
        (
            review,
            rerank_report,
            source_health,
            query_execution_audit,
            quality_report,
            snowball_report,
            curated_review,
            metadata_audit,
            seed_intake,
            coverage_report,
            evidence_mix_report,
            rescue_report,
        ) = _bind_literature_chain(chain)
        review, rescue_execution = write_literature_rescue_execution_artifacts(topic, config.literature, llm, review, rescue_report, out_dir, repair_tasks=_repair_resume_retrieval_tasks(out_dir))
        if rescue_execution.get("updated_review"):
            chain = _run_literature_audit_chain(topic, config, research_plan, review, out_dir, write_search_strategy=False)
            (
                review,
                rerank_report,
                source_health,
                query_execution_audit,
                quality_report,
                snowball_report,
                curated_review,
                metadata_audit,
                seed_intake,
                coverage_report,
                evidence_mix_report,
                rescue_report,
            ) = _bind_literature_chain(chain)
        search_feedback = write_literature_search_feedback_artifacts(
            research_plan,
            review,
            curated_review,
            quality_report,
            snowball_report,
            coverage_report,
            rescue_report,
            source_health,
            config.literature,
            out_dir,
            seed_intake_report=seed_intake,
            rerank_report=rerank_report,
            evidence_mix_report=evidence_mix_report,
            query_execution_report=query_execution_audit,
        )
        fulltext_corpus = write_fulltext_corpus_artifacts(topic, config.literature.fulltext_paths, out_dir, base_dir=Path.cwd())
        _write_state(out_dir, topic, "literature_review_completed")
        manifest.record(
            "literature_review",
            inputs=["00-research-plan.json"],
            outputs=[
                "01-literature.json",
                "01-literature.md",
                LITERATURE_RERANK_JSON,
                LITERATURE_RERANK_MD,
                LITERATURE_SEARCH_STRATEGY_JSON,
                LITERATURE_SEARCH_STRATEGY_MD,
                LITERATURE_SOURCE_HEALTH_JSON,
                LITERATURE_SOURCE_HEALTH_MD,
                QUERY_EXECUTION_AUDIT_JSON,
                QUERY_EXECUTION_AUDIT_MD,
                "01-literature-quality.json",
                "01-literature-quality.md",
                LITERATURE_SNOWBALL_JSON,
                LITERATURE_SNOWBALL_MD,
                LITERATURE_COVERAGE_JSON,
                LITERATURE_COVERAGE_MD,
                LITERATURE_EVIDENCE_MIX_JSON,
                LITERATURE_EVIDENCE_MIX_MD,
                LITERATURE_RESCUE_PLAN_JSON,
                LITERATURE_RESCUE_PLAN_MD,
                LITERATURE_RESCUE_EXECUTION_JSON,
                LITERATURE_RESCUE_EXECUTION_MD,
                LITERATURE_SEARCH_FEEDBACK_JSON,
                LITERATURE_SEARCH_FEEDBACK_MD,
                SEED_PAPER_INTAKE_JSON,
                SEED_PAPER_INTAKE_MD,
                "01-literature-curated.json",
                "01-literature-curated.md",
                LITERATURE_METADATA_AUDIT_JSON,
                LITERATURE_METADATA_AUDIT_MD,
                FULLTEXT_CORPUS_JSON,
                FULLTEXT_CORPUS_MD,
            ],
            metrics={
                "raw_papers": len(review.papers),
                "selected_papers": len(curated_review.papers),
                "fulltext_documents": len(fulltext_corpus.documents),
                "fulltext_chunks": fulltext_corpus.total_chunks,
                "quality_warnings": len(quality_report.warnings),
                "rerank_status": rerank_report.get("status"),
                "rerank_warnings": len(rerank_report.get("warnings", []) if isinstance(rerank_report.get("warnings"), list) else []),
                "query_execution_status": query_execution_audit.get("status"),
                "query_execution_selected": query_execution_audit.get("selected_query_count"),
                "snowball_status": snowball_report.get("status"),
                "snowball_queries": snowball_report.get("query_count"),
                "coverage_status": coverage_report.get("status"),
                "coverage_ratio": coverage_report.get("coverage_ratio"),
                "evidence_mix_status": evidence_mix_report.get("status"),
                "evidence_mix_score": evidence_mix_report.get("mix_score"),
                "rescue_status": rescue_report.get("status"),
                "rescue_queries": len(rescue_report.get("rescue_queries", []) if isinstance(rescue_report.get("rescue_queries"), list) else []),
                "rescue_execution_status": rescue_execution.get("status"),
                "rescue_execution_new_papers": rescue_execution.get("new_unique_papers"),
                "search_feedback_status": search_feedback.get("status"),
                "search_feedback_tasks": len(search_feedback.get("retrieval_repair_tasks", []) if isinstance(search_feedback.get("retrieval_repair_tasks"), list) else []),
                "seed_intake_status": seed_intake.get("status"),
                "seed_intake_curated": seed_intake.get("curated_seed_papers"),
                "metadata_audit_status": metadata_audit.get("status"),
                "metadata_audit_blocked": metadata_audit.get("blocked"),
                "rate_limited_sources": source_health.get("rate_limited_sources"),
                "cache_hits": source_health.get("cache_hits"),
                "cache_misses": source_health.get("cache_misses"),
            },
            notes=review.source_diagnostics[:4],
        )
        _check_cancelled(out_dir, topic, manifest, "literature_review_completed")

    def _node_literature_context():
        nonlocal citation_audit, context
        context = apply_literature_audits_to_context(
            build_literature_context(curated_review, fulltext_corpus),
            quality_report=quality_report,
            metadata_report=metadata_audit,
            coverage_report=coverage_report,
            evidence_mix_report=evidence_mix_report,
            rescue_report=rescue_report,
            seed_intake_report=seed_intake,
        )
        context, citation_audit = write_context_and_citation_artifacts(
            out_dir,
            context,
            topic=topic,
            quality_report=quality_report,
            source_health_report=source_health,
            query_execution_report=query_execution_audit,
            rerank_report=rerank_report,
            coverage_report=coverage_report,
            evidence_mix_report=evidence_mix_report,
            rescue_report=rescue_report,
            rescue_execution_report=rescue_execution,
            seed_intake_report=seed_intake,
            paper_grade_config=config.paper_grade,
        )

    def _node_review_gate():
        nonlocal review_constraints, review_feedback
        request_review_approval(out_dir, topic, context)
        _write_state(out_dir, topic, "awaiting_review_approval")
        manifest.record(
            "literature_context",
            inputs=["01-literature-curated.json", FULLTEXT_CORPUS_JSON],
            outputs=["01-context.json", "01-context.md", "01-review-gate.md", "01-references.bib", "01-references.ris", CITATION_AUDIT_JSON, CITATION_AUDIT_MD, LITERATURE_EVIDENCE_CONTRACT_JSON, LITERATURE_EVIDENCE_CONTRACT_MD, LITERATURE_GATE_DECISION_JSON, LITERATURE_GATE_DECISION_MD, APPROVAL_FILENAME],
            metrics={
                "citations": len(context.citations),
                "chunks": len(context.chunks),
                "fulltext_chunks": fulltext_corpus.total_chunks,
                "claim_support": len(context.claim_support),
                "gate_status": context.review_gate.status,
                "blocked_citations": citation_audit.blocked_citations,
                "citation_review_required": citation_audit.review_required,
                "citation_integrity_score": citation_audit.integrity_score,
                "citation_integrity_status": citation_audit.integrity_status,
            },
            notes=[*context.review_gate.warnings[:4], *citation_audit.warnings[:2]],
        )
        wait_for_review_approval(out_dir, topic=topic, manifest=manifest)
        _write_state(out_dir, topic, "review_approved")
        manifest.record("review_approval", inputs=[APPROVAL_FILENAME, "01-review-gate.md"], outputs=[APPROVAL_FILENAME], metrics={"approved": True})
        review_feedback = write_review_feedback_artifacts(out_dir, topic)
        manifest.record("review_feedback", inputs=[APPROVAL_FILENAME], outputs=[REVIEW_FEEDBACK_JSON, REVIEW_FEEDBACK_MD], metrics={"items": len(review_feedback.get("items", []))})
        review_constraints = write_review_constraints_artifacts(out_dir, topic, review_feedback)
        manifest.record(
            "review_constraints",
            inputs=[REVIEW_FEEDBACK_JSON],
            outputs=[REVIEW_CONSTRAINTS_JSON, REVIEW_CONSTRAINTS_MD],
            metrics={"constraints": len(review_constraints.get("constraints", [])) if isinstance(review_constraints.get("constraints"), list) else 0},
        )
        _check_cancelled(out_dir, topic, manifest, "review_approved")

    engine = WorkflowEngine([node.node_id for node in WORKFLOW_NODES])
    engine.run(out_dir, start="research_planning", handlers={
        "research_planning": _node_research_planning,
        "literature_review": _node_literature_review,
        "literature_context": _node_literature_context,
        "review_gate": _node_review_gate,
    }, facts=lambda: {}, terminal_nodes={"review_gate"},
       before_node=lambda node: begin_workflow_node(out_dir, topic, node),
       on_edge=lambda source, target: manifest.record("workflow_dispatch", inputs=[], outputs=[], metrics={"from": source, "to": target}))

    _run_after_review_approval(
        topic,
        out_dir,
        config,
        llm,
        research_plan,
        curated_review,
        context,
        manifest,
        review_feedback_text=_combined_review_feedback_text(review_feedback, review_constraints, planning_context),
        review_constraints=review_constraints,
        human_brief=human_brief,
        prior_lessons_text=planning_context,
    )
    return out_dir


def resume_pipeline_after_review_approval(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    with acquire_run_lease(out_dir, "resume_after_review", owner="pipeline"):
        return _resume_pipeline_after_review_approval_unlocked(topic, out_dir, config)


def _resume_pipeline_after_review_approval_unlocked(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    _check_cancelled(out_dir, topic, None, "resume_requested")
    revision_repair = _approval_requires_revision_repair(out_dir / APPROVAL_FILENAME)
    if revision_repair:
        if not _approval_granted(out_dir / APPROVAL_FILENAME):
            raise RuntimeError(f"{APPROVAL_FILENAME} is not approved in {out_dir}")
        _validate_checkpoint_topic_identity(out_dir, topic)
        _renew_checkpoint_contract_for_review_revision(out_dir, topic, config)
    else:
        _validate_or_create_checkpoint_contract(out_dir, topic, config)
        _write_run_config_snapshot(out_dir, config)
        if not _approval_granted(out_dir / APPROVAL_FILENAME):
            raise RuntimeError(f"{APPROVAL_FILENAME} is not approved in {out_dir}")
    manifest = RunManifestRecorder(out_dir, topic)
    _check_cancelled(out_dir, topic, manifest, "resume_requested")
    llm = build_agent_runtime_llm(config, Path(__file__).resolve().parents[2], out_dir)
    _check_cancelled(out_dir, topic, manifest, "resume_started")
    research_plan = _load_research_plan(out_dir / "00-research-plan.json")
    resume_downstream = True
    if revision_repair:
        review, context = _refresh_literature_context_after_review_revision(topic, out_dir, config, llm, research_plan, manifest)
        resume_downstream = False
        if not _approval_granted(out_dir / APPROVAL_FILENAME):
            _write_state(out_dir, topic, "awaiting_review_approval")
            manifest.record(
                "review_revision_reapproval_required",
                inputs=[APPROVAL_FILENAME, "01-context.json", "01-review-gate.md"],
                outputs=["state.json"],
                metrics={"approved": False, "gate_status": context.review_gate.status},
                notes=["退回修复已刷新文献 gate；当前批准记录不满足新 gate 策略，等待人工再次批准。"],
            )
            wait_for_review_approval(out_dir, topic=topic, manifest=manifest)
        review_path = out_dir / "01-literature-curated.json"
        citation_audit = None
    else:
        review_path = out_dir / "01-literature-curated.json"
        if not review_path.exists():
            review_path = out_dir / "01-literature.json"
        review = _load_literature_review(review_path)
        context = _load_literature_context(out_dir / "01-context.json")
        if not (out_dir / CITATION_AUDIT_JSON).exists() or not (out_dir / CITATION_AUDIT_MD).exists():
            context, citation_audit = write_context_and_citation_artifacts(out_dir, context, paper_grade_config=config.paper_grade)
        else:
            citation_audit = None
    _write_state(out_dir, topic, "review_approved")
    manifest.record(
        "resume_after_review_approval",
        inputs=[APPROVAL_FILENAME, "00-research-plan.json", str(review_path.name), "01-context.json"],
        outputs=[],
        metrics={"approved": True, "resume_downstream": resume_downstream},
    )
    manifest.record("review_approval_checkpoint", inputs=[APPROVAL_FILENAME], outputs=[], metrics={"approved": True})
    if citation_audit is not None:
        manifest.record(
            "citation_audit_checkpoint",
            inputs=["01-context.json"],
            outputs=[CITATION_AUDIT_JSON, CITATION_AUDIT_MD],
            metrics={"blocked_citations": citation_audit.blocked_citations, "citation_review_required": citation_audit.review_required},
        )
    review_feedback = write_review_feedback_artifacts(out_dir, topic)
    manifest.record("review_feedback", inputs=[APPROVAL_FILENAME], outputs=[REVIEW_FEEDBACK_JSON, REVIEW_FEEDBACK_MD], metrics={"items": len(review_feedback.get("items", []))})
    review_constraints = write_review_constraints_artifacts(out_dir, topic, review_feedback)
    manifest.record(
        "review_constraints",
        inputs=[REVIEW_FEEDBACK_JSON],
        outputs=[REVIEW_CONSTRAINTS_JSON, REVIEW_CONSTRAINTS_MD],
        metrics={"constraints": len(review_constraints.get("constraints", [])) if isinstance(review_constraints.get("constraints"), list) else 0},
    )
    _check_cancelled(out_dir, topic, manifest, "review_approved")
    human_brief = _load_or_write_human_brief(topic, config, out_dir, manifest)
    prior_lessons = _load_or_write_prior_run_lessons(topic, out_dir, manifest)
    prior_library = _load_or_write_prior_run_library(topic, out_dir, manifest)
    open_source_lessons = _load_or_write_open_source_lessons(topic, out_dir, manifest)
    planning_context = _planning_context(
        str(human_brief.get("agent_prompt_text") or ""),
        prior_lessons.agent_prompt_text,
        prior_library.agent_prompt_text,
        open_source_lessons.agent_prompt_text,
        _repair_resume_context(out_dir),
    )
    _run_after_review_approval(
        topic,
        out_dir,
        config,
        llm,
        research_plan,
        review,
        context,
        manifest,
        resume=resume_downstream,
        review_feedback_text=_combined_review_feedback_text(review_feedback, review_constraints, planning_context),
        review_constraints=review_constraints,
        human_brief=human_brief,
        prior_lessons_text=planning_context,
    )
    return out_dir


def _refresh_literature_context_after_review_revision(
    topic: str,
    out_dir: Path,
    config: AgentConfig,
    llm: Any,
    research_plan: ResearchPlan,
    manifest: RunManifestRecorder,
) -> tuple[LiteratureReview, LiteratureContext]:
    raw_review = run_literature_review(topic, config.literature, llm, research_plan.search_queries)
    chain = _run_literature_audit_chain(topic, config, research_plan, raw_review, out_dir)
    (
        raw_review,
        rerank_report,
        source_health,
        query_execution_audit,
        quality_report,
        snowball_report,
        curated_review,
        metadata_audit,
        seed_intake,
        coverage_report,
        evidence_mix_report,
        rescue_report,
    ) = _bind_literature_chain(chain)
    raw_after_rescue, rescue_execution = write_literature_rescue_execution_artifacts(topic, config.literature, llm, raw_review, rescue_report, out_dir, repair_tasks=_repair_resume_retrieval_tasks(out_dir))
    if rescue_execution.get("updated_review"):
        chain = _run_literature_audit_chain(topic, config, research_plan, raw_after_rescue, out_dir, write_search_strategy=False)
        (
            raw_review,
            rerank_report,
            source_health,
            query_execution_audit,
            quality_report,
            snowball_report,
            curated_review,
            metadata_audit,
            seed_intake,
            coverage_report,
            evidence_mix_report,
            rescue_report,
        ) = _bind_literature_chain(chain)

    search_feedback = write_literature_search_feedback_artifacts(
        research_plan,
        raw_review,
        curated_review,
        quality_report,
        snowball_report,
        coverage_report,
        rescue_report,
        source_health,
        config.literature,
        out_dir,
        seed_intake_report=seed_intake,
        rerank_report=rerank_report,
        evidence_mix_report=evidence_mix_report,
        query_execution_report=query_execution_audit,
    )
    fulltext_corpus = write_fulltext_corpus_artifacts(topic, config.literature.fulltext_paths, out_dir, base_dir=Path.cwd())
    context = apply_literature_audits_to_context(
        build_literature_context(curated_review, fulltext_corpus),
        quality_report=quality_report,
        metadata_report=metadata_audit,
        coverage_report=coverage_report,
        evidence_mix_report=evidence_mix_report,
        rescue_report=rescue_report,
        seed_intake_report=seed_intake,
    )
    context, citation_audit = write_context_and_citation_artifacts(
        out_dir,
        context,
        topic=topic,
        quality_report=quality_report,
        source_health_report=source_health,
        query_execution_report=query_execution_audit,
        rerank_report=rerank_report,
        coverage_report=coverage_report,
        evidence_mix_report=evidence_mix_report,
        rescue_report=rescue_report,
        rescue_execution_report=rescue_execution,
        seed_intake_report=seed_intake,
        paper_grade_config=config.paper_grade,
    )
    approval = refresh_review_revision_repair_approval(out_dir, context)
    _write_state(out_dir, topic, "literature_review_completed")
    manifest.record(
        "review_revision_literature_repair",
        inputs=[APPROVAL_FILENAME, "00-research-plan.json", "run-config.json"],
        outputs=[
            "01-literature.json",
            "01-literature.md",
            LITERATURE_RERANK_JSON,
            LITERATURE_RERANK_MD,
            LITERATURE_SEARCH_STRATEGY_JSON,
            LITERATURE_SEARCH_STRATEGY_MD,
            LITERATURE_SOURCE_HEALTH_JSON,
            LITERATURE_SOURCE_HEALTH_MD,
            QUERY_EXECUTION_AUDIT_JSON,
            QUERY_EXECUTION_AUDIT_MD,
            "01-literature-quality.json",
            "01-literature-quality.md",
            LITERATURE_SNOWBALL_JSON,
            LITERATURE_SNOWBALL_MD,
            LITERATURE_COVERAGE_JSON,
            LITERATURE_COVERAGE_MD,
            LITERATURE_EVIDENCE_MIX_JSON,
            LITERATURE_EVIDENCE_MIX_MD,
            LITERATURE_RESCUE_PLAN_JSON,
            LITERATURE_RESCUE_PLAN_MD,
            LITERATURE_RESCUE_EXECUTION_JSON,
            LITERATURE_RESCUE_EXECUTION_MD,
            LITERATURE_SEARCH_FEEDBACK_JSON,
            LITERATURE_SEARCH_FEEDBACK_MD,
            SEED_PAPER_INTAKE_JSON,
            SEED_PAPER_INTAKE_MD,
            FULLTEXT_CORPUS_JSON,
            FULLTEXT_CORPUS_MD,
            "01-literature-curated.json",
            "01-literature-curated.md",
            LITERATURE_METADATA_AUDIT_JSON,
            LITERATURE_METADATA_AUDIT_MD,
            "01-context.json",
            "01-context.md",
            "01-review-gate.md",
            "01-references.bib",
            "01-references.ris",
            CITATION_AUDIT_JSON,
            CITATION_AUDIT_MD,
            LITERATURE_EVIDENCE_CONTRACT_JSON,
            LITERATURE_EVIDENCE_CONTRACT_MD,
            LITERATURE_GATE_DECISION_JSON,
            LITERATURE_GATE_DECISION_MD,
            APPROVAL_FILENAME,
        ],
        metrics={
            "raw_papers": len(raw_review.papers),
            "selected_papers": len(curated_review.papers),
            "fulltext_documents": len(fulltext_corpus.documents),
            "fulltext_chunks": fulltext_corpus.total_chunks,
            "quality_warnings": len(quality_report.warnings),
            "rerank_status": rerank_report.get("status"),
            "rerank_warnings": len(rerank_report.get("warnings", []) if isinstance(rerank_report.get("warnings"), list) else []),
            "query_execution_status": query_execution_audit.get("status"),
            "query_execution_selected": query_execution_audit.get("selected_query_count"),
            "snowball_status": snowball_report.get("status"),
            "coverage_status": coverage_report.get("status"),
            "evidence_mix_status": evidence_mix_report.get("status"),
            "evidence_mix_score": evidence_mix_report.get("mix_score"),
            "rescue_status": rescue_report.get("status"),
            "rescue_execution_status": rescue_execution.get("status"),
            "rescue_execution_new_papers": rescue_execution.get("new_unique_papers"),
            "search_feedback_status": search_feedback.get("status"),
            "search_feedback_tasks": len(search_feedback.get("retrieval_repair_tasks", []) if isinstance(search_feedback.get("retrieval_repair_tasks"), list) else []),
            "seed_intake_status": seed_intake.get("status"),
            "seed_intake_curated": seed_intake.get("curated_seed_papers"),
            "metadata_audit_status": metadata_audit.get("status"),
            "metadata_audit_blocked": metadata_audit.get("blocked"),
            "gate_status": context.review_gate.status,
            "approval_granted_after_repair": _approval_granted(out_dir / APPROVAL_FILENAME),
            "citation_review_required": citation_audit.review_required,
        },
        notes=["退回后重新生成文献池、seed intake、context 和 review gate。"],
    )
    return curated_review, context


def resume_pipeline_from_checkpoint(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    with acquire_run_lease(out_dir, "checkpoint_resume", owner="pipeline"):
        return _resume_pipeline_from_checkpoint_unlocked(topic, out_dir, config)


def _resume_pipeline_from_checkpoint_unlocked(topic: str, out_dir: Path, config: AgentConfig) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _validate_or_create_checkpoint_contract(out_dir, topic, config)
    _write_run_config_snapshot(out_dir, config)
    _check_cancelled(out_dir, topic, None, "resume_requested")
    manifest = RunManifestRecorder(out_dir, topic)
    manifest.record(
        "resume_from_checkpoint",
        inputs=["state.json", "run-config.json"],
        outputs=[],
        metrics={"existing_stage": _current_stage(out_dir)},
    )
    llm = build_agent_runtime_llm(config, Path(__file__).resolve().parents[2], out_dir)
    _check_cancelled(out_dir, topic, manifest, "resume_started")
    context = None
    coverage_report = None
    curated_path = None
    evidence_mix_report = None
    human_brief = None
    metadata_audit = None
    planning_context = None
    quality_report = None
    query_execution_audit = None
    raw_review_for_metadata = None
    raw_review_path = None
    rerank_report = None
    rescue_execution = None
    rescue_report = None
    research_plan = None
    review = None
    review_constraints = None
    review_feedback = None
    seed_intake = None
    snowball_report = None
    source_health = None

    def _node_research_planning():
        nonlocal human_brief, planning_context, research_plan
        if not (out_dir / "00-question.md").exists():
            write_text(out_dir / "00-question.md", f"# 研究问题\n\n{topic}")
            manifest.record("question", inputs=[], outputs=["00-question.md"], metrics={"topic_chars": len(topic)})

        research_plan_path = out_dir / "00-research-plan.json"
        human_brief = _load_or_write_human_brief(topic, config, out_dir, manifest)
        prior_lessons = _load_or_write_prior_run_lessons(topic, out_dir, manifest)
        prior_library = _load_or_write_prior_run_library(topic, out_dir, manifest)
        open_source_lessons = _load_or_write_open_source_lessons(topic, out_dir, manifest)
        planning_context = _planning_context(
            str(human_brief.get("agent_prompt_text") or ""),
            prior_lessons.agent_prompt_text,
            prior_library.agent_prompt_text,
            open_source_lessons.agent_prompt_text,
            _repair_resume_context(out_dir),
        )
        if research_plan_path.exists():
            research_plan = _load_research_plan(research_plan_path)
            if not (out_dir / "00-research-plan.md").exists():
                write_text(out_dir / "00-research-plan.md", render_research_plan_markdown(research_plan))
            manifest.record(
                "research_plan_checkpoint",
                inputs=["00-research-plan.json"],
                outputs=[],
                notes=["reused existing research plan"],
                metrics={"domain": research_plan.domain},
            )
        else:
            research_plan = build_research_plan(topic, llm, prior_lessons=planning_context)
            write_json(research_plan_path, research_plan)
            write_text(out_dir / "00-research-plan.md", render_research_plan_markdown(research_plan))
            _write_state(out_dir, topic, "research_plan_completed")
            manifest.record(
                "research_plan",
                inputs=["00-question.md", HUMAN_BRIEF_JSON, PRIOR_RUN_LESSONS_JSON, PRIOR_RUN_LIBRARY_JSON, OPEN_SOURCE_LESSONS_JSON],
                outputs=["00-research-plan.json", "00-research-plan.md"],
                metrics={
                    "domain": research_plan.domain,
                    "queries": len(research_plan.search_queries),
                    "benchmarks": len(research_plan.benchmarks),
                    "baselines": len(research_plan.baselines),
                },
            )
        _check_cancelled(out_dir, topic, manifest, "research_plan_completed")

    def _node_literature_review():
        nonlocal coverage_report, curated_path, evidence_mix_report, metadata_audit, quality_report, query_execution_audit, raw_review_for_metadata, raw_review_path, rerank_report, rescue_execution, rescue_report, review, seed_intake, snowball_report, source_health
        curated_path = out_dir / "01-literature-curated.json"
        raw_review_path = out_dir / "01-literature.json"
        snowball_written_in_literature = False
        coverage_written_in_literature = False
        seed_intake_written_in_literature = False
        if curated_path.exists():
            review = _load_literature_review(curated_path)
            if not (out_dir / "01-literature-curated.md").exists():
                write_text(out_dir / "01-literature-curated.md", render_literature_markdown(review))
            if not (out_dir / LITERATURE_SEARCH_STRATEGY_JSON).exists() or not (out_dir / LITERATURE_SEARCH_STRATEGY_MD).exists():
                write_literature_search_strategy_artifacts(out_dir, review)
            if not (out_dir / LITERATURE_SOURCE_HEALTH_JSON).exists() or not (out_dir / LITERATURE_SOURCE_HEALTH_MD).exists():
                write_literature_source_health_artifacts(out_dir, review)
            raw_for_seed_intake = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            quality_for_seed_intake = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(raw_for_seed_intake)
            if not (out_dir / SEED_PAPER_INTAKE_JSON).exists() or not (out_dir / SEED_PAPER_INTAKE_MD).exists():
                seed_intake = write_seed_paper_intake_artifacts(topic, config.literature, raw_for_seed_intake, review, quality_for_seed_intake, out_dir)
                seed_intake_written_in_literature = True
            else:
                seed_intake = _read_dict(out_dir / SEED_PAPER_INTAKE_JSON)
            rerank_report = _read_dict(out_dir / LITERATURE_RERANK_JSON)
            if not rerank_report:
                raw_for_rerank = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
                _, rerank_report = write_literature_rerank_artifacts(raw_for_rerank, research_plan, out_dir)
            raw_for_query_audit = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            _load_or_write_query_execution_audit(research_plan, raw_for_query_audit, rerank_report, out_dir, manifest)
            manifest.record(
                "literature_review_checkpoint",
                inputs=["01-literature-curated.json"],
                outputs=[LITERATURE_RERANK_JSON, LITERATURE_RERANK_MD, QUERY_EXECUTION_AUDIT_JSON, QUERY_EXECUTION_AUDIT_MD] if rerank_report else [],
                notes=["reused curated literature review"],
                metrics={"selected_papers": len(review.papers)},
            )
        else:
            if raw_review_path.exists():
                review = _load_literature_review(raw_review_path)
                manifest.record(
                    "literature_raw_checkpoint",
                    inputs=["01-literature.json"],
                    outputs=[],
                    notes=["reused raw literature review"],
                    metrics={"raw_papers": len(review.papers)},
                )
            else:
                review = run_literature_review(topic, config.literature, llm, research_plan.search_queries)
            review, rerank_report = _write_reranked_literature(out_dir, review, research_plan)
            write_literature_search_strategy_artifacts(out_dir, review)
            source_health = write_literature_source_health_artifacts(out_dir, review)
            query_execution_audit = write_query_execution_audit_artifacts(research_plan, review, rerank_report, source_health, out_dir)
            quality_report = assess_literature_quality(review)
            write_json(out_dir / "01-literature-quality.json", quality_report)
            write_text(out_dir / "01-literature-quality.md", render_literature_quality_markdown(quality_report))
            snowball_report = write_literature_snowball_artifacts(review, quality_report, out_dir)
            snowball_written_in_literature = True
            raw_review_for_metadata = review
            review = filter_review_by_quality(review, quality_report)
            write_json(curated_path, review)
            write_text(out_dir / "01-literature-curated.md", render_literature_markdown(review))
            metadata_audit = write_literature_metadata_audit_artifacts(raw_review_for_metadata, review, quality_report, out_dir)
            seed_intake = write_seed_paper_intake_artifacts(topic, config.literature, _load_literature_review(raw_review_path) if raw_review_path.exists() else review, review, quality_report, out_dir)
            seed_intake_written_in_literature = True
            coverage_report = write_literature_coverage_artifacts(research_plan, review, out_dir)
            coverage_written_in_literature = True
            rescue_report = write_literature_rescue_plan_artifacts(research_plan, _load_literature_review(raw_review_path) if raw_review_path.exists() else review, review, quality_report, snowball_report, coverage_report, out_dir)
            raw_review_for_rescue = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            raw_review_after_rescue, rescue_execution = write_literature_rescue_execution_artifacts(topic, config.literature, llm, raw_review_for_rescue, rescue_report, out_dir, repair_tasks=_repair_resume_retrieval_tasks(out_dir))
            if rescue_execution.get("updated_review"):
                review = raw_review_after_rescue
                review, rerank_report = _write_reranked_literature(out_dir, review, research_plan)
                source_health = write_literature_source_health_artifacts(out_dir, review)
                query_execution_audit = write_query_execution_audit_artifacts(research_plan, review, rerank_report, source_health, out_dir)
                quality_report = assess_literature_quality(review)
                write_json(out_dir / "01-literature-quality.json", quality_report)
                write_text(out_dir / "01-literature-quality.md", render_literature_quality_markdown(quality_report))
                snowball_report = write_literature_snowball_artifacts(review, quality_report, out_dir)
                raw_review_for_metadata = review
                review = filter_review_by_quality(review, quality_report)
                write_json(curated_path, review)
                write_text(out_dir / "01-literature-curated.md", render_literature_markdown(review))
                metadata_audit = write_literature_metadata_audit_artifacts(raw_review_for_metadata, review, quality_report, out_dir)
                seed_intake = write_seed_paper_intake_artifacts(topic, config.literature, raw_review_for_metadata, review, quality_report, out_dir)
                seed_intake_written_in_literature = True
                coverage_report = write_literature_coverage_artifacts(research_plan, review, out_dir)
                rescue_report = write_literature_rescue_plan_artifacts(research_plan, raw_review_for_metadata, review, quality_report, snowball_report, coverage_report, out_dir)
            _write_state(out_dir, topic, "literature_review_completed")
            manifest.record(
                "literature_review",
                inputs=["00-research-plan.json"],
                outputs=[
                    "01-literature.json",
                    "01-literature.md",
                    LITERATURE_RERANK_JSON,
                    LITERATURE_RERANK_MD,
                    LITERATURE_SEARCH_STRATEGY_JSON,
                    LITERATURE_SEARCH_STRATEGY_MD,
                    LITERATURE_SOURCE_HEALTH_JSON,
                    LITERATURE_SOURCE_HEALTH_MD,
                    QUERY_EXECUTION_AUDIT_JSON,
                    QUERY_EXECUTION_AUDIT_MD,
                    "01-literature-quality.json",
                    "01-literature-quality.md",
                    LITERATURE_SNOWBALL_JSON,
                    LITERATURE_SNOWBALL_MD,
                    LITERATURE_COVERAGE_JSON,
                    LITERATURE_COVERAGE_MD,
                    LITERATURE_RESCUE_PLAN_JSON,
                    LITERATURE_RESCUE_PLAN_MD,
                    LITERATURE_RESCUE_EXECUTION_JSON,
                    LITERATURE_RESCUE_EXECUTION_MD,
                    SEED_PAPER_INTAKE_JSON,
                    SEED_PAPER_INTAKE_MD,
                    "01-literature-curated.json",
                    "01-literature-curated.md",
                    LITERATURE_METADATA_AUDIT_JSON,
                    LITERATURE_METADATA_AUDIT_MD,
                ],
                metrics={
                    "selected_papers": len(review.papers),
                    "rerank_status": rerank_report.get("status"),
                    "rerank_warnings": len(rerank_report.get("warnings", []) if isinstance(rerank_report.get("warnings"), list) else []),
                    "query_execution_status": query_execution_audit.get("status"),
                    "query_execution_selected": query_execution_audit.get("selected_query_count"),
                    "snowball_status": snowball_report.get("status"),
                    "snowball_queries": snowball_report.get("query_count"),
                    "coverage_status": coverage_report.get("status"),
                    "coverage_ratio": coverage_report.get("coverage_ratio"),
                    "rescue_status": rescue_report.get("status"),
                    "rescue_queries": len(rescue_report.get("rescue_queries", []) if isinstance(rescue_report.get("rescue_queries"), list) else []),
                    "rescue_execution_status": rescue_execution.get("status"),
                    "rescue_execution_new_papers": rescue_execution.get("new_unique_papers"),
                    "seed_intake_status": seed_intake.get("status"),
                    "seed_intake_curated": seed_intake.get("curated_seed_papers"),
                    "metadata_audit_status": metadata_audit.get("status"),
                    "metadata_audit_blocked": metadata_audit.get("blocked"),
                },
            )
        if not (out_dir / LITERATURE_METADATA_AUDIT_JSON).exists() or not (out_dir / LITERATURE_METADATA_AUDIT_MD).exists():
            raw_for_metadata = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            quality_for_metadata = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(raw_for_metadata)
            metadata_audit = write_literature_metadata_audit_artifacts(raw_for_metadata, review, quality_for_metadata, out_dir)
            manifest.record(
                "literature_metadata_audit",
                inputs=["01-literature.json" if raw_review_path.exists() else "01-literature-curated.json", "01-literature-curated.json", "01-literature-quality.json"],
                outputs=[LITERATURE_METADATA_AUDIT_JSON, LITERATURE_METADATA_AUDIT_MD],
                metrics={"status": metadata_audit.get("status"), "blocked": metadata_audit.get("blocked"), "review_required": metadata_audit.get("review_required")},
            )
        else:
            metadata_audit = _read_dict(out_dir / LITERATURE_METADATA_AUDIT_JSON)
            manifest.record(
                "literature_metadata_audit_checkpoint",
                inputs=[LITERATURE_METADATA_AUDIT_JSON],
                outputs=[],
                notes=["reused existing literature metadata audit"],
                metrics={"status": metadata_audit.get("status"), "blocked": metadata_audit.get("blocked"), "review_required": metadata_audit.get("review_required")},
            )
        if not (out_dir / SEED_PAPER_INTAKE_JSON).exists() or not (out_dir / SEED_PAPER_INTAKE_MD).exists():
            raw_for_seed_intake = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            quality_for_seed_intake = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(raw_for_seed_intake)
            seed_intake = write_seed_paper_intake_artifacts(topic, config.literature, raw_for_seed_intake, review, quality_for_seed_intake, out_dir)
            manifest.record(
                "seed_paper_intake",
                inputs=["01-literature.json" if raw_review_path.exists() else "01-literature-curated.json", "01-literature-quality.json"],
                outputs=[SEED_PAPER_INTAKE_JSON, SEED_PAPER_INTAKE_MD],
                metrics={"status": seed_intake.get("status"), "curated": seed_intake.get("curated_seed_papers"), "total": seed_intake.get("total_seed_entries")},
            )
        elif not seed_intake_written_in_literature:
            seed_intake = _read_dict(out_dir / SEED_PAPER_INTAKE_JSON)
            manifest.record(
                "seed_paper_intake_checkpoint",
                inputs=[SEED_PAPER_INTAKE_JSON],
                outputs=[],
                notes=["reused existing seed paper intake audit"],
                metrics={"status": seed_intake.get("status"), "curated": seed_intake.get("curated_seed_papers"), "total": seed_intake.get("total_seed_entries")},
            )
        if not (out_dir / LITERATURE_SNOWBALL_JSON).exists() or not (out_dir / LITERATURE_SNOWBALL_MD).exists():
            snowball_source_review = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            snowball_quality = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(snowball_source_review)
            snowball_report = write_literature_snowball_artifacts(snowball_source_review, snowball_quality, out_dir)
            manifest.record(
                "literature_snowball",
                inputs=["01-literature.json" if raw_review_path.exists() else "01-literature-curated.json", "01-literature-quality.json"],
                outputs=[LITERATURE_SNOWBALL_JSON, LITERATURE_SNOWBALL_MD],
                metrics={"status": snowball_report.get("status"), "seed_count": snowball_report.get("seed_count"), "query_count": snowball_report.get("query_count")},
            )
        elif not snowball_written_in_literature:
            snowball_report = _read_dict(out_dir / LITERATURE_SNOWBALL_JSON)
            manifest.record(
                "literature_snowball_checkpoint",
                inputs=[LITERATURE_SNOWBALL_JSON],
                outputs=[],
                notes=["reused existing literature snowball plan"],
                metrics={"status": snowball_report.get("status"), "seed_count": snowball_report.get("seed_count"), "query_count": snowball_report.get("query_count")},
            )
        if not (out_dir / LITERATURE_COVERAGE_JSON).exists() or not (out_dir / LITERATURE_COVERAGE_MD).exists():
            coverage_report = write_literature_coverage_artifacts(research_plan, review, out_dir)
            manifest.record(
                "literature_coverage",
                inputs=["00-research-plan.json", "01-literature-curated.json"],
                outputs=[LITERATURE_COVERAGE_JSON, LITERATURE_COVERAGE_MD],
                metrics={"status": coverage_report.get("status"), "coverage_ratio": coverage_report.get("coverage_ratio")},
            )
        elif not coverage_written_in_literature:
            coverage_report = _read_dict(out_dir / LITERATURE_COVERAGE_JSON)
            manifest.record(
                "literature_coverage_checkpoint",
                inputs=[LITERATURE_COVERAGE_JSON],
                outputs=[],
                notes=["reused existing literature coverage audit"],
                metrics={"status": coverage_report.get("status"), "coverage_ratio": coverage_report.get("coverage_ratio")},
            )
        raw_for_evidence_mix = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
        quality_for_evidence_mix = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(raw_for_evidence_mix)
        evidence_mix_report = _load_or_write_literature_evidence_mix(
            research_plan,
            raw_for_evidence_mix,
            review,
            quality_for_evidence_mix,
            coverage_report,
            out_dir,
            manifest,
        )
        if not (out_dir / LITERATURE_RESCUE_PLAN_JSON).exists() or not (out_dir / LITERATURE_RESCUE_PLAN_MD).exists():
            raw_for_rescue = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
            quality_for_rescue = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(raw_for_rescue)
            rescue_report = write_literature_rescue_plan_artifacts(research_plan, raw_for_rescue, review, quality_for_rescue, snowball_report, coverage_report, out_dir)
            manifest.record(
                "literature_rescue_plan",
                inputs=["00-research-plan.json", "01-literature.json", "01-literature-curated.json", LITERATURE_SNOWBALL_JSON, LITERATURE_COVERAGE_JSON],
                outputs=[LITERATURE_RESCUE_PLAN_JSON, LITERATURE_RESCUE_PLAN_MD],
                metrics={"status": rescue_report.get("status"), "queries": len(rescue_report.get("rescue_queries", []) if isinstance(rescue_report.get("rescue_queries"), list) else [])},
            )
        else:
            rescue_report = _read_dict(out_dir / LITERATURE_RESCUE_PLAN_JSON)
            manifest.record(
                "literature_rescue_plan_checkpoint",
                inputs=[LITERATURE_RESCUE_PLAN_JSON],
                outputs=[],
                notes=["reused existing literature rescue plan"],
                metrics={"status": rescue_report.get("status"), "queries": len(rescue_report.get("rescue_queries", []) if isinstance(rescue_report.get("rescue_queries"), list) else [])},
            )

    def _node_literature_context():
        nonlocal context, coverage_report, evidence_mix_report, metadata_audit, quality_report, query_execution_audit, raw_review_for_metadata, rerank_report, rescue_execution, rescue_report, review, seed_intake, snowball_report, source_health
        context_path = out_dir / "01-context.json"
        if not (out_dir / LITERATURE_RESCUE_EXECUTION_JSON).exists() or not (out_dir / LITERATURE_RESCUE_EXECUTION_MD).exists():
            if context_path.exists():
                rescue_execution = {
                    "topic": topic,
                    "status": "skipped_existing_context",
                    "trigger_status": rescue_report.get("status"),
                    "updated_review": False,
                    "original_papers": len(review.papers),
                    "rescue_candidates": 0,
                    "new_unique_papers": 0,
                    "final_papers": len(review.papers),
                    "selected_queries": [],
                    "diagnostics": [],
                    "source_health": [],
                    "rescue_titles": [],
                    "note": "01-context.json 已存在，避免改变已经进入人工审核的文献池。",
                }
                write_json(out_dir / LITERATURE_RESCUE_EXECUTION_JSON, rescue_execution)
                write_text(out_dir / LITERATURE_RESCUE_EXECUTION_MD, render_literature_rescue_execution_markdown(rescue_execution))
            else:
                raw_for_rescue_execution = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
                raw_after_rescue_execution, rescue_execution = write_literature_rescue_execution_artifacts(
                    topic,
                    config.literature,
                    llm,
                    raw_for_rescue_execution,
                    rescue_report,
                    out_dir,
                    repair_tasks=_repair_resume_retrieval_tasks(out_dir),
                )
                if rescue_execution.get("updated_review"):
                    review = raw_after_rescue_execution
                    review, rerank_report = _write_reranked_literature(out_dir, review, research_plan)
                    source_health = write_literature_source_health_artifacts(out_dir, review)
                    write_query_execution_audit_artifacts(research_plan, review, rerank_report, source_health, out_dir)
                    quality_report = assess_literature_quality(review)
                    write_json(out_dir / "01-literature-quality.json", quality_report)
                    write_text(out_dir / "01-literature-quality.md", render_literature_quality_markdown(quality_report))
                    snowball_report = write_literature_snowball_artifacts(review, quality_report, out_dir)
                    raw_review_for_metadata = review
                    review = filter_review_by_quality(review, quality_report)
                    write_json(curated_path, review)
                    write_text(out_dir / "01-literature-curated.md", render_literature_markdown(review))
                    metadata_audit = write_literature_metadata_audit_artifacts(raw_review_for_metadata, review, quality_report, out_dir)
                    seed_intake = write_seed_paper_intake_artifacts(topic, config.literature, raw_review_for_metadata, review, quality_report, out_dir)
                    coverage_report = write_literature_coverage_artifacts(research_plan, review, out_dir)
                    evidence_mix_report = write_literature_evidence_mix_artifacts(research_plan, raw_review_for_metadata, review, quality_report, coverage_report, out_dir)
                    rescue_report = write_literature_rescue_plan_artifacts(research_plan, raw_review_for_metadata, review, quality_report, snowball_report, coverage_report, out_dir)
            manifest.record(
                "literature_rescue_execution",
                inputs=[LITERATURE_RESCUE_PLAN_JSON, "01-literature.json" if raw_review_path.exists() else "01-literature-curated.json"],
                outputs=[LITERATURE_RESCUE_EXECUTION_JSON, LITERATURE_RESCUE_EXECUTION_MD, LITERATURE_RERANK_JSON, LITERATURE_RERANK_MD],
                metrics={"status": rescue_execution.get("status"), "new_unique_papers": rescue_execution.get("new_unique_papers")},
            )
        else:
            rescue_execution = _read_dict(out_dir / LITERATURE_RESCUE_EXECUTION_JSON)
            manifest.record(
                "literature_rescue_execution_checkpoint",
                inputs=[LITERATURE_RESCUE_EXECUTION_JSON],
                outputs=[],
                notes=["reused existing literature rescue execution"],
                metrics={"status": rescue_execution.get("status"), "new_unique_papers": rescue_execution.get("new_unique_papers")},
            )
        raw_for_query_execution = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
        query_execution_audit = _load_or_write_query_execution_audit(
            research_plan,
            raw_for_query_execution,
            _read_dict(out_dir / LITERATURE_RERANK_JSON),
            out_dir,
            manifest,
        )
        raw_for_feedback = _load_literature_review(raw_review_path) if raw_review_path.exists() else review
        quality_for_feedback = _read_dict(out_dir / "01-literature-quality.json") or assess_literature_quality(raw_for_feedback)
        source_health_for_feedback = _read_dict(out_dir / LITERATURE_SOURCE_HEALTH_JSON)
        search_feedback = write_literature_search_feedback_artifacts(
            research_plan,
            raw_for_feedback,
            review,
            quality_for_feedback,
            snowball_report,
            coverage_report,
            rescue_report,
            source_health_for_feedback,
            config.literature,
            out_dir,
            seed_intake_report=seed_intake,
            rerank_report=_read_dict(out_dir / LITERATURE_RERANK_JSON),
            evidence_mix_report=evidence_mix_report,
            query_execution_report=query_execution_audit,
        )
        manifest.record(
            "literature_search_feedback",
            inputs=[
                "01-literature.json" if raw_review_path.exists() else "01-literature-curated.json",
                "01-literature-quality.json",
                LITERATURE_SNOWBALL_JSON,
                LITERATURE_COVERAGE_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                LITERATURE_RESCUE_PLAN_JSON,
                LITERATURE_RESCUE_EXECUTION_JSON,
                LITERATURE_SOURCE_HEALTH_JSON,
                QUERY_EXECUTION_AUDIT_JSON,
                SEED_PAPER_INTAKE_JSON,
            ],
            outputs=[LITERATURE_SEARCH_FEEDBACK_JSON, LITERATURE_SEARCH_FEEDBACK_MD],
            metrics={
                "status": search_feedback.get("status"),
                "queries": len(search_feedback.get("recommended_queries", []) if isinstance(search_feedback.get("recommended_queries"), list) else []),
                "seed_targets": len(search_feedback.get("seed_paper_targets", []) if isinstance(search_feedback.get("seed_paper_targets"), list) else []),
                "retrieval_repair_tasks": len(search_feedback.get("retrieval_repair_tasks", []) if isinstance(search_feedback.get("retrieval_repair_tasks"), list) else []),
                "rescue_execution_status": rescue_execution.get("status"),
            },
        )
        fulltext_corpus = _load_or_write_fulltext_corpus(topic, config, out_dir, manifest)
        _check_cancelled(out_dir, topic, manifest, "literature_review_completed")

        if context_path.exists():
            context = apply_literature_audits_to_context(
                _load_literature_context(context_path),
                quality_report=_read_dict(out_dir / "01-literature-quality.json"),
                metadata_report=_read_dict(out_dir / LITERATURE_METADATA_AUDIT_JSON),
                coverage_report=coverage_report,
                evidence_mix_report=evidence_mix_report,
                rescue_report=rescue_report,
                seed_intake_report=seed_intake,
            )
            context, citation_audit = write_context_and_citation_artifacts(out_dir, context, paper_grade_config=config.paper_grade)
            manifest.record(
                "literature_context_checkpoint",
                inputs=["01-context.json"],
                outputs=["01-context.json", "01-context.md", "01-review-gate.md", CITATION_AUDIT_JSON, CITATION_AUDIT_MD, LITERATURE_EVIDENCE_CONTRACT_JSON, LITERATURE_EVIDENCE_CONTRACT_MD, LITERATURE_GATE_DECISION_JSON, LITERATURE_GATE_DECISION_MD],
                notes=["reused literature context"],
                metrics={
                    "citations": len(context.citations),
                    "chunks": len(context.chunks),
                    "blocked_citations": citation_audit.blocked_citations,
                    "citation_review_required": citation_audit.review_required,
                    "citation_integrity_score": citation_audit.integrity_score,
                    "citation_integrity_status": citation_audit.integrity_status,
                },
            )
        else:
            context = apply_literature_audits_to_context(
                build_literature_context(review, fulltext_corpus),
                quality_report=_read_dict(out_dir / "01-literature-quality.json"),
                metadata_report=_read_dict(out_dir / LITERATURE_METADATA_AUDIT_JSON),
                coverage_report=coverage_report,
                evidence_mix_report=evidence_mix_report,
                rescue_report=rescue_report,
                seed_intake_report=seed_intake,
            )
            context, citation_audit = write_context_and_citation_artifacts(out_dir, context, paper_grade_config=config.paper_grade)
            request_review_approval(out_dir, topic, context)
            _write_state(out_dir, topic, "awaiting_review_approval")
            manifest.record(
                "literature_context",
                inputs=["01-literature-curated.json", FULLTEXT_CORPUS_JSON],
                outputs=["01-context.json", "01-context.md", "01-review-gate.md", "01-references.bib", "01-references.ris", CITATION_AUDIT_JSON, CITATION_AUDIT_MD, LITERATURE_EVIDENCE_CONTRACT_JSON, LITERATURE_EVIDENCE_CONTRACT_MD, LITERATURE_GATE_DECISION_JSON, LITERATURE_GATE_DECISION_MD, APPROVAL_FILENAME],
                metrics={
                    "citations": len(context.citations),
                    "chunks": len(context.chunks),
                    "fulltext_chunks": fulltext_corpus.total_chunks,
                    "gate_status": context.review_gate.status,
                    "blocked_citations": citation_audit.blocked_citations,
                    "citation_review_required": citation_audit.review_required,
                    "citation_integrity_score": citation_audit.integrity_score,
                    "citation_integrity_status": citation_audit.integrity_status,
                },
            )

    def _node_review_gate():
        nonlocal review_constraints, review_feedback
        refresh_pending_review_approval(out_dir, context)
        if not (out_dir / APPROVAL_FILENAME).exists():
            request_review_approval(out_dir, topic, context)
            _write_state(out_dir, topic, "awaiting_review_approval")
        if not _approval_granted(out_dir / APPROVAL_FILENAME):
            _write_state(out_dir, topic, "awaiting_review_approval")
            wait_for_review_approval(out_dir, topic=topic, manifest=manifest)
        _write_state(out_dir, topic, "review_approved")
        manifest.record("review_approval_checkpoint", inputs=[APPROVAL_FILENAME], outputs=[], metrics={"approved": True})
        review_feedback = write_review_feedback_artifacts(out_dir, topic)
        manifest.record("review_feedback", inputs=[APPROVAL_FILENAME], outputs=[REVIEW_FEEDBACK_JSON, REVIEW_FEEDBACK_MD], metrics={"items": len(review_feedback.get("items", []))})
        review_constraints = write_review_constraints_artifacts(out_dir, topic, review_feedback)
        manifest.record(
            "review_constraints",
            inputs=[REVIEW_FEEDBACK_JSON],
            outputs=[REVIEW_CONSTRAINTS_JSON, REVIEW_CONSTRAINTS_MD],
            metrics={"constraints": len(review_constraints.get("constraints", [])) if isinstance(review_constraints.get("constraints"), list) else 0},
        )
        _check_cancelled(out_dir, topic, manifest, "review_approved")

    engine = WorkflowEngine([node.node_id for node in WORKFLOW_NODES])
    engine.run(out_dir, start="research_planning", handlers={
        "research_planning": _node_research_planning,
        "literature_review": _node_literature_review,
        "literature_context": _node_literature_context,
        "review_gate": _node_review_gate,
    }, facts=lambda: {}, terminal_nodes={"review_gate"},
       before_node=lambda node: begin_workflow_node(out_dir, topic, node),
       on_edge=lambda source, target: manifest.record("workflow_dispatch", inputs=[], outputs=[], metrics={"from": source, "to": target}))

    _run_after_review_approval(
        topic,
        out_dir,
        config,
        llm,
        research_plan,
        review,
        context,
        manifest,
        resume=True,
        review_feedback_text=_combined_review_feedback_text(review_feedback, review_constraints, planning_context),
        review_constraints=review_constraints,
        human_brief=human_brief,
        prior_lessons_text=planning_context,
    )
    return out_dir


def resume_pipeline_from_repair_queue(
    topic: str,
    out_dir: Path,
    config: AgentConfig,
    doctor_report_path: Path | None = None,
    gold_verification_report_path: Path | None = None,
) -> Path:
    with acquire_run_lease(out_dir, "repair_resume", owner="pipeline"):
        return _resume_pipeline_from_repair_queue_unlocked(
            topic,
            out_dir,
            config,
            doctor_report_path=doctor_report_path,
            gold_verification_report_path=gold_verification_report_path,
        )


def _resume_pipeline_from_repair_queue_unlocked(
    topic: str,
    out_dir: Path,
    config: AgentConfig,
    doctor_report_path: Path | None = None,
    gold_verification_report_path: Path | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # T07/A16：修复恢复入口受冻结次数上限约束；恢复不能绕过预算。
    ensure_budget(out_dir, "repair_resumes")
    preflight_report = build_repair_resume_plan(out_dir, doctor_report_path=doctor_report_path, gold_verification_report_path=gold_verification_report_path)
    if preflight_report.get("can_resume") is not True:
        raise RuntimeError(str(preflight_report.get("reason") or "repair queue cannot be used for resume"))
    record_execution(out_dir, "repair_resumes", note="repair-resume accepted")
    _validate_repair_resume_identity(out_dir, topic, preflight_report)
    _validate_repair_resume_approval_cleanup(out_dir, preflight_report)
    missing_release = missing_repair_resume_required_release_values(config, preflight_report)
    if missing_release:
        cli_args = ["--" + field.replace("_", "-") for field in missing_release]
        raise RuntimeError(
            "Missing required release metadata before repair-resume apply: "
            + ", ".join(missing_release)
            + "; provide "
            + ", ".join(cli_args)
            + " or update 10-release-metadata.json before deleting artifacts."
        )
    preflight_config = apply_repair_resume_recommendations(config, {**preflight_report, "applied": True})
    # Fail fast while no model is reachable for the resumed run, before any
    # artifact cleanup makes the existing run unrecoverable.
    RoleModelRouter(preflight_config).resolve(stage="research_planning")
    validate_execution_config(preflight_config.execution)
    report = prepare_repair_resume(out_dir, apply=True, doctor_report_path=doctor_report_path, gold_verification_report_path=gold_verification_report_path)
    if report.get("can_resume") is not True:
        raise RuntimeError(str(report.get("reason") or "repair queue cannot be used for resume"))
    config = apply_repair_resume_recommendations(config, report)
    contract_record = _renew_checkpoint_contract_after_repair(out_dir, topic, config, report)
    report["checkpoint_contract"] = contract_record
    write_json(out_dir / REPAIR_RESUME_PLAN_JSON, report)
    write_text(out_dir / REPAIR_RESUME_PLAN_MD, render_repair_resume_plan_markdown(report))
    _write_state(out_dir, topic, "repair_resume_applied")
    manifest = RunManifestRecorder(out_dir, topic)
    manifest.record(
        "repair_resume_prepare",
        inputs=[REPAIR_QUEUE_JSON],
        outputs=[REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD, "state.json"],
        metrics={
            "rerun_from": report.get("rerun_from"),
            "removed_artifacts": len(report.get("removed_artifacts", []) if isinstance(report.get("removed_artifacts"), list) else []),
            "removed_directories": len(report.get("removed_directories", []) if isinstance(report.get("removed_directories"), list) else []),
            "review_reapproval_required": report.get("review_reapproval_required") is True,
            "execution_reapproval_required": report.get("execution_reapproval_required") is True,
            "checkpoint_fingerprint": contract_record.get("fingerprint"),
            "state_stage": "repair_resume_applied",
        },
    )
    return resume_pipeline_from_checkpoint(topic, out_dir, config)


def _run_after_review_approval(
    topic: str,
    out_dir: Path,
    config: AgentConfig,
    llm,
    research_plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext,
    manifest: RunManifestRecorder,
    resume: bool = False,
    review_feedback_text: str = "",
    review_constraints: dict[str, Any] | None = None,
    human_brief: dict[str, Any] | None = None,
    prior_lessons_text: str = "",
) -> None:
    """Dispatch post-approval nodes through the executable workflow registry."""
    agent_assignment = None
    analysis = None
    benchmark_evidence = None
    chosen_idea = None
    claim_boundary_preflight = None
    evidence_integrity = None
    execution_safety = None
    experiment_decision = None
    exploration_map = None
    failure_analysis = None
    hypothesis_outcome = None
    ideas = None
    manager_constraints_text = None
    novelty_audit = None
    paper_checkpoint_reusable = None
    paper_md = None
    paper_path = None
    paper_review = None
    paper_review_path = None
    plan = None
    preregistration = None
    repair_queue = None
    repair_resume = None
    result_validation = None
    results = None
    results_path = None
    review_calibration = None
    review_calibration_outputs = None
    review_calibration_path = None
    revised_paper_md = None
    revised_paper_path = None
    revision_report = None
    runbook = None
    statistics = None

    def _node_ideation():
        nonlocal agent_assignment, chosen_idea, exploration_map, ideas, manager_constraints_text, novelty_audit, repair_queue, repair_resume, review_feedback_text
        _check_cancelled(out_dir, topic, manifest, "review_approved")

        gap_map_path = out_dir / RESEARCH_GAP_MAP_JSON
        if resume and gap_map_path.exists():
            research_gap_map = _read_dict(gap_map_path)
            if not (out_dir / RESEARCH_GAP_MAP_MD).exists():
                write_text(out_dir / RESEARCH_GAP_MAP_MD, render_research_gap_map_markdown(research_gap_map))
            manifest.record(
                "research_gap_map_checkpoint",
                inputs=[RESEARCH_GAP_MAP_JSON],
                outputs=[],
                notes=["reused existing research gap map"],
                metrics={
                    "status": research_gap_map.get("status"),
                    "gaps": research_gap_map.get("gap_count"),
                    "ready": research_gap_map.get("ready_gap_count"),
                },
            )
        else:
            research_gap_map = write_research_gap_map_artifacts(
                topic,
                research_plan,
                review,
                context,
                _read_dict(out_dir / LITERATURE_COVERAGE_JSON),
                out_dir,
                review_constraints=review_constraints,
            )
            manifest.record(
                "research_gap_map",
                inputs=["01-literature-curated.json", "01-context.json", LITERATURE_COVERAGE_JSON, REVIEW_CONSTRAINTS_JSON],
                outputs=[RESEARCH_GAP_MAP_JSON, RESEARCH_GAP_MAP_MD],
                metrics={
                    "status": research_gap_map.get("status"),
                    "gaps": research_gap_map.get("gap_count"),
                    "ready": research_gap_map.get("ready_gap_count"),
                },
            )
        agent_team_path = out_dir / MULTI_AGENT_ASSIGNMENT_JSON
        if resume and agent_team_path.exists():
            agent_assignment = _read_dict(agent_team_path)
            if not (out_dir / MULTI_AGENT_ASSIGNMENT_MD).exists():
                write_text(out_dir / MULTI_AGENT_ASSIGNMENT_MD, render_multi_agent_assignment_markdown(agent_assignment))
            manifest.record(
                "multi_agent_assignment_checkpoint",
                inputs=[MULTI_AGENT_ASSIGNMENT_JSON],
                outputs=[],
                notes=["reused existing multi-agent assignment"],
                metrics={
                    "status": agent_assignment.get("status"),
                    "active_agents": len(agent_assignment.get("active_agents", []) if isinstance(agent_assignment.get("active_agents"), list) else []),
                    "tasks": len(agent_assignment.get("tasks", []) if isinstance(agent_assignment.get("tasks"), list) else []),
                },
            )
        else:
            agent_assignment = write_multi_agent_assignment_artifacts(
                topic,
                research_plan,
                review,
                context,
                _read_dict(out_dir / LITERATURE_COVERAGE_JSON),
                _read_dict(out_dir / LITERATURE_EVIDENCE_MIX_JSON),
                research_gap_map,
                review_constraints,
                config.execution,
                out_dir,
            )
            manifest.record(
                "multi_agent_assignment",
                inputs=[RESEARCH_GAP_MAP_JSON, "01-context.json", LITERATURE_COVERAGE_JSON, LITERATURE_EVIDENCE_MIX_JSON, REVIEW_CONSTRAINTS_JSON, "run-config.json"],
                outputs=[MULTI_AGENT_ASSIGNMENT_JSON, MULTI_AGENT_ASSIGNMENT_MD],
                metrics={
                    "status": agent_assignment.get("status"),
                    "active_agents": len(agent_assignment.get("active_agents", []) if isinstance(agent_assignment.get("active_agents"), list) else []),
                    "tasks": len(agent_assignment.get("tasks", []) if isinstance(agent_assignment.get("tasks"), list) else []),
                },
            )
        ideas_path = out_dir / "02-ideas.json"
        if resume and ideas_path.exists():
            ideas = _load_ideas(ideas_path)
            if not (out_dir / "02-ideas.md").exists():
                write_text(out_dir / "02-ideas.md", render_ideas_markdown(ideas))
            manifest.record(
                "ideation_checkpoint",
                inputs=["02-ideas.json"],
                outputs=[],
                notes=["reused existing ideas"],
                metrics={"ideas": len(ideas), "top_score": ideas[0].score if ideas else None},
            )
        else:
            if prior_lessons_text and prior_lessons_text not in review_feedback_text:
                review_feedback_text = "\n\n".join(part for part in [review_feedback_text.strip(), prior_lessons_text.strip()] if part)
            ideas = generate_ideas(
                review,
                config.ideation,
                llm,
                context,
                review_feedback=review_feedback_text,
                research_gap_map=research_gap_map,
                agent_assignment=agent_assignment,
            )
            write_json(ideas_path, ideas)
            write_text(out_dir / "02-ideas.md", render_ideas_markdown(ideas))
            _write_state(out_dir, topic, "ideation_completed")
            manifest.record(
                "ideation",
                inputs=["01-literature-curated.json", "01-context.json", RESEARCH_GAP_MAP_JSON, MULTI_AGENT_ASSIGNMENT_JSON, PRIOR_RUN_LESSONS_JSON, PRIOR_RUN_LIBRARY_JSON],
                outputs=["02-ideas.json", "02-ideas.md"],
                metrics={"ideas": len(ideas), "top_score": ideas[0].score if ideas else None},
            )
        ideas = _ensure_idea_agent_roles(ideas, agent_assignment)
        write_json(ideas_path, ideas)
        write_text(out_dir / "02-ideas.md", render_ideas_markdown(ideas))
        _check_cancelled(out_dir, topic, manifest, "ideation_completed")

        if not ideas:
            raise RuntimeError("No research ideas available for experiment planning")
        if resume and (out_dir / NOVELTY_AUDIT_JSON).exists():
            novelty_audit = _read_dict(out_dir / NOVELTY_AUDIT_JSON)
            manifest.record(
                "novelty_audit_checkpoint",
                inputs=[NOVELTY_AUDIT_JSON],
                outputs=[],
                notes=["reused existing novelty audit"],
                metrics={"likely_duplicates": novelty_audit.get("likely_duplicates", 0)},
            )
        else:
            novelty_audit = write_novelty_audit_artifacts(topic, ideas, review, out_dir)
            manifest.record(
                "novelty_audit",
                inputs=["02-ideas.json", "01-literature-curated.json"],
                outputs=[NOVELTY_AUDIT_JSON, NOVELTY_AUDIT_MD],
                metrics={
                    "likely_duplicates": novelty_audit.get("likely_duplicates", 0),
                    "review_required": novelty_audit.get("review_required", 0),
                },
            )
        idea_audit_path = out_dir / IDEA_AUDIT_JSON
        if resume and idea_audit_path.exists():
            idea_audit = _read_dict(idea_audit_path)
            if not (out_dir / IDEA_AUDIT_MD).exists():
                write_text(out_dir / IDEA_AUDIT_MD, render_idea_audit_markdown(idea_audit))
            manifest.record(
                "idea_audit_checkpoint",
                inputs=[IDEA_AUDIT_JSON, "02-ideas.json"],
                outputs=[],
                notes=["reused existing idea audit"],
                metrics={
                    "status": idea_audit.get("status"),
                    "blocked": idea_audit.get("blocked"),
                    "review_required": idea_audit.get("review_required"),
                },
            )
        else:
            idea_audit = write_idea_audit_artifacts(
                topic,
                ideas,
                context,
                out_dir,
                review_constraints=review_constraints,
                novelty_audit=novelty_audit,
            )
            manifest.record(
                "idea_audit",
                inputs=["02-ideas.json", "01-context.json", REVIEW_CONSTRAINTS_JSON, NOVELTY_AUDIT_JSON],
                outputs=[IDEA_AUDIT_JSON, IDEA_AUDIT_MD],
                metrics={
                    "status": idea_audit.get("status"),
                    "blocked": idea_audit.get("blocked"),
                    "review_required": idea_audit.get("review_required"),
                },
            )
        exploration_path = out_dir / EXPLORATION_MAP_JSON
        if resume and exploration_path.exists():
            exploration_map = _load_exploration_map(exploration_path)
            if not (out_dir / EXPLORATION_MAP_MD).exists():
                write_text(out_dir / EXPLORATION_MAP_MD, render_exploration_map_markdown(exploration_map))
            if not (out_dir / EXPLORATION_MAP_SVG).exists():
                write_text(out_dir / EXPLORATION_MAP_SVG, render_exploration_map_svg(exploration_map))
            manifest.record(
                "exploration_map_checkpoint",
                inputs=[EXPLORATION_MAP_JSON, "02-ideas.json"],
                outputs=[],
                notes=["reused existing exploration map"],
                metrics={"branches": len(exploration_map.branches), "selected": exploration_map.selected_branch_id},
            )
        else:
            exploration_map = write_exploration_map_artifacts(topic, ideas, out_dir, novelty_audit=novelty_audit, idea_audit=idea_audit)
            _write_state(out_dir, topic, "exploration_map_completed")
            manifest.record(
                "exploration_map",
                inputs=["02-ideas.json", "01-context.json", NOVELTY_AUDIT_JSON, IDEA_AUDIT_JSON],
                outputs=[EXPLORATION_MAP_JSON, EXPLORATION_MAP_MD, EXPLORATION_MAP_SVG],
                metrics={
                    "branches": len(exploration_map.branches),
                    "selected": exploration_map.selected_branch_id,
                    "warnings": len(exploration_map.warnings),
                },
            )
        chosen_idea = selected_idea(exploration_map, ideas)
        _check_cancelled(out_dir, topic, manifest, "exploration_map_completed")

        manager_path = out_dir / EXPERIMENT_MANAGER_JSON
        if resume and manager_path.exists():
            experiment_manager = _read_dict(manager_path)
            if not (out_dir / EXPERIMENT_MANAGER_MD).exists():
                write_text(out_dir / EXPERIMENT_MANAGER_MD, render_experiment_manager_markdown(experiment_manager))
            manifest.record(
                "experiment_manager_checkpoint",
                inputs=[EXPERIMENT_MANAGER_JSON, EXPLORATION_MAP_JSON, IDEA_AUDIT_JSON, NOVELTY_AUDIT_JSON],
                outputs=[],
                notes=["reused existing experiment manager decision"],
                metrics={
                    "status": experiment_manager.get("status"),
                    "decision": experiment_manager.get("manager_decision"),
                    "policy": experiment_manager.get("execution_policy"),
                },
            )
        else:
            experiment_manager = write_experiment_manager_artifacts(
                topic,
                ideas,
                exploration_map,
                out_dir,
                idea_audit=idea_audit,
                novelty_audit=novelty_audit,
            )
            _write_state(out_dir, topic, "experiment_manager_completed")
            manifest.record(
                "experiment_manager",
                inputs=[EXPLORATION_MAP_JSON, IDEA_AUDIT_JSON, NOVELTY_AUDIT_JSON],
                outputs=[EXPERIMENT_MANAGER_JSON, EXPERIMENT_MANAGER_MD],
                metrics={
                    "status": experiment_manager.get("status"),
                    "decision": experiment_manager.get("manager_decision"),
                    "policy": experiment_manager.get("execution_policy"),
                    "next_candidates": len(experiment_manager.get("next_expansion_candidates", []) if isinstance(experiment_manager.get("next_expansion_candidates"), list) else []),
                },
            )
        manager_constraints_text = experiment_manager_constraints(experiment_manager)
        _check_cancelled(out_dir, topic, manifest, "experiment_manager_completed")
        if experiment_manager.get("status") == "block":
            _write_state(out_dir, topic, "experiment_manager_blocked")
            repair_queue = write_repair_queue_artifacts(topic, out_dir)
            repair_resume = write_repair_resume_plan_artifacts(out_dir, apply=False)
            manifest.record(
                "experiment_manager_blocked",
                inputs=[EXPERIMENT_MANAGER_JSON, EXPLORATION_MAP_JSON, IDEA_AUDIT_JSON, NOVELTY_AUDIT_JSON],
                outputs=[REPAIR_QUEUE_JSON, REPAIR_QUEUE_MD, REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD],
                status="blocked",
                metrics={
                    "repair_queue_status": repair_queue.status,
                    "repair_queue_items": len(repair_queue.items),
                    "repair_resume_can_resume": repair_resume.get("can_resume") is True,
                    "repair_resume_rerun_from": repair_resume.get("rerun_from"),
                },
            )
            actions = experiment_manager.get("required_actions") if isinstance(experiment_manager.get("required_actions"), list) else []
            detail = "; ".join(str(item) for item in actions[:4]) or str(experiment_manager.get("rationale") or "experiment manager requires human repair")
            raise RuntimeError("Experiment manager blocked downstream planning: " + detail)

    def _node_experiment_plan():
        nonlocal execution_safety, plan, preregistration
        plan_path = out_dir / "03-experiment-plan.json"
        if resume and plan_path.exists():
            plan = _load_experiment_plan(plan_path)
            if not (out_dir / "03-experiment-plan.md").exists():
                write_text(out_dir / "03-experiment-plan.md", render_experiment_plan_markdown(plan))
            manifest.record(
                "experiment_plan_checkpoint",
                inputs=["03-experiment-plan.json"],
                outputs=[],
                notes=["reused existing experiment plan"],
                metrics={"template_profile": plan.template_profile, "metrics": len(plan.metrics), "commands": len(plan.commands)},
            )
        else:
            plan = plan_experiment(chosen_idea, context, llm, research_plan, review_feedback=review_feedback_text, manager_constraints=manager_constraints_text)
            write_json(plan_path, plan)
            write_text(out_dir / "03-experiment-plan.md", render_experiment_plan_markdown(plan))
            _write_state(out_dir, topic, "experiment_plan_completed")
            manifest.record(
                "experiment_plan",
                inputs=[EXPLORATION_MAP_JSON, "02-ideas.json", "01-context.json", "00-research-plan.json"],
                outputs=["03-experiment-plan.json", "03-experiment-plan.md"],
                metrics={
                    "template_profile": plan.template_profile,
                    "metrics": len(plan.metrics),
                    "commands": len(plan.commands),
                    "selected_branch": exploration_map.selected_branch_id,
                },
            )
        plan = _ensure_experiment_plan_agent_roles(plan, chosen_idea)
        write_json(plan_path, plan)
        write_text(out_dir / "03-experiment-plan.md", render_experiment_plan_markdown(plan))
        _check_cancelled(out_dir, topic, manifest, "experiment_plan_completed")

        agent_handoff = write_multi_agent_handoff_audit_artifacts(topic, chosen_idea, plan, agent_assignment, out_dir)
        manifest.record(
            "multi_agent_handoff_audit",
            inputs=[MULTI_AGENT_ASSIGNMENT_JSON, "02-ideas.json", "03-experiment-plan.json"],
            outputs=[MULTI_AGENT_HANDOFF_AUDIT_JSON, MULTI_AGENT_HANDOFF_AUDIT_MD],
            metrics={
                "status": agent_handoff.get("status"),
                "blocking_issues": len(agent_handoff.get("blocking_issues", []) if isinstance(agent_handoff.get("blocking_issues"), list) else []),
                "manual_tasks": len(agent_handoff.get("manual_tasks", []) if isinstance(agent_handoff.get("manual_tasks"), list) else []),
            },
        )
        if agent_handoff.get("status") == "block":
            raise RuntimeError("Multi-agent handoff audit blocked execution: " + "; ".join(str(item) for item in agent_handoff.get("blocking_issues", [])[:4]))

        constraint_compliance = write_review_constraint_compliance_artifacts(topic, review_constraints, chosen_idea, plan, out_dir, human_brief=human_brief)
        manifest.record(
            "review_constraint_compliance",
            inputs=[REVIEW_CONSTRAINTS_JSON, HUMAN_BRIEF_JSON, EXPLORATION_MAP_JSON, "03-experiment-plan.json"],
            outputs=[REVIEW_CONSTRAINT_COMPLIANCE_JSON, REVIEW_CONSTRAINT_COMPLIANCE_MD],
            metrics={
                "status": constraint_compliance.get("status"),
                "checked_constraints": constraint_compliance.get("checked_constraints"),
                "human_brief_constraints": constraint_compliance.get("human_brief_constraints"),
                "blocked": constraint_compliance.get("blocked"),
                "review_required": constraint_compliance.get("review_required"),
            },
        )
        _check_cancelled(out_dir, topic, manifest, "review_constraint_compliance_completed")

        ablation_outputs: list[str] = []
        if not (out_dir / ABLATION_PLAN_JSON).exists() or not (out_dir / ABLATION_PLAN_MD).exists():
            ablation_plan = write_ablation_plan_artifacts(chosen_idea, plan, out_dir)
            ablation_outputs = [ABLATION_PLAN_JSON, ABLATION_PLAN_MD]
        else:
            ablation_plan = _read_dict(out_dir / ABLATION_PLAN_JSON)
        manifest.record(
            "ablation_plan" if ablation_outputs else "ablation_plan_checkpoint",
            inputs=["03-experiment-plan.json", EXPLORATION_MAP_JSON],
            outputs=ablation_outputs,
            notes=[] if ablation_outputs else ["reused existing ablation plan"],
            metrics={
                "status": ablation_plan.get("status"),
                "has_ablation": ablation_plan.get("has_ablation"),
                "variants": len(ablation_plan.get("suggested_variants", []) if isinstance(ablation_plan.get("suggested_variants"), list) else []),
            },
        )

        preregistration_outputs: list[str] = []
        if not (out_dir / PREREGISTRATION_JSON).exists() or not (out_dir / PREREGISTRATION_MD).exists():
            preregistration = write_preregistration_artifacts(
                topic,
                chosen_idea,
                plan,
                out_dir,
                results_exist=(out_dir / "04-results.json").exists(),
            )
            preregistration_outputs = [PREREGISTRATION_JSON, PREREGISTRATION_MD]
        else:
            preregistration = _read_dict(out_dir / PREREGISTRATION_JSON)
        manifest.record(
            "preregistration" if preregistration_outputs else "preregistration_checkpoint",
            inputs=["03-experiment-plan.json", ABLATION_PLAN_JSON],
            outputs=preregistration_outputs,
            notes=[] if preregistration_outputs else ["reused existing preregistration"],
            metrics={
                "status": preregistration.get("status"),
                "timing": preregistration.get("timing"),
                "primary_metrics": len(preregistration.get("primary_metrics", []) if isinstance(preregistration.get("primary_metrics"), list) else []),
            },
        )

        experiment_audit = write_experiment_audit_artifacts(
            research_plan,
            plan,
            out_dir,
            literature_coverage=_read_dict(out_dir / LITERATURE_COVERAGE_JSON),
            novelty_audit=novelty_audit,
            ablation_plan=ablation_plan,
            preregistration=preregistration,
            constraint_compliance=constraint_compliance,
        )
        manifest.record(
            "experiment_audit",
            inputs=["03-experiment-plan.json", LITERATURE_COVERAGE_JSON, NOVELTY_AUDIT_JSON, ABLATION_PLAN_JSON, PREREGISTRATION_JSON, REVIEW_CONSTRAINT_COMPLIANCE_JSON],
            outputs=[EXPERIMENT_AUDIT_JSON, EXPERIMENT_AUDIT_MD],
            metrics={"status": experiment_audit.get("status"), "blocking_issues": len(experiment_audit.get("blocking_issues", []) if isinstance(experiment_audit.get("blocking_issues"), list) else [])},
        )
        if experiment_audit.get("status") == "block":
            raise RuntimeError("Experiment audit blocked execution: " + "; ".join(str(item) for item in experiment_audit.get("blocking_issues", [])[:4]))

        execution_safety = write_execution_safety_audit_artifacts(plan, config.execution, out_dir, paper_grade=config.paper_grade)
        manifest.record(
            "execution_safety_audit",
            inputs=["03-experiment-plan.json", "run-config.json"],
            outputs=[EXECUTION_SAFETY_AUDIT_JSON, EXECUTION_SAFETY_AUDIT_MD],
            metrics={
                "status": execution_safety.get("status"),
                "commands": len(execution_safety.get("commands", []) if isinstance(execution_safety.get("commands"), list) else []),
                "blocking_issues": len(execution_safety.get("blocking_issues", []) if isinstance(execution_safety.get("blocking_issues"), list) else []),
            },
        )
        if execution_safety.get("status") == "block":
            raise RuntimeError("Execution safety audit blocked execution: " + "; ".join(str(item) for item in execution_safety.get("blocking_issues", [])[:4]))

        benchmark_outputs: list[str] = []
        if not (out_dir / BENCHMARK_PLAN_JSON).exists() or not (out_dir / BENCHMARK_PLAN_MD).exists():
            benchmark_plan = write_benchmark_plan_artifacts(research_plan, plan, out_dir)
            benchmark_outputs = [BENCHMARK_PLAN_JSON, BENCHMARK_PLAN_MD]
            manifest.record(
                "benchmark_plan",
                inputs=["00-research-plan.json", "03-experiment-plan.json"],
                outputs=benchmark_outputs,
                metrics={"candidates": len(benchmark_plan.candidates), "selected": len(benchmark_plan.selected_names)},
            )
        elif resume:
            benchmark_plan = _load_benchmark_plan(out_dir / BENCHMARK_PLAN_JSON)
            manifest.record(
                "benchmark_plan_checkpoint",
                inputs=[BENCHMARK_PLAN_JSON],
                outputs=[],
                notes=["reused existing benchmark plan"],
            )
        else:
            benchmark_plan = _load_benchmark_plan(out_dir / BENCHMARK_PLAN_JSON)
        benchmark_readiness = write_benchmark_readiness_artifacts(research_plan, plan, benchmark_plan, config.execution, out_dir, base_dir=Path.cwd())
        manifest.record(
            "benchmark_readiness",
            inputs=[BENCHMARK_PLAN_JSON, "03-experiment-plan.json", "run-config.json"],
            outputs=[BENCHMARK_READINESS_JSON, BENCHMARK_READINESS_MD],
            metrics={
                "status": benchmark_readiness.get("status"),
                "confidence_score": benchmark_readiness.get("confidence_score"),
                "blocking_issues": len(benchmark_readiness.get("blocking_issues", []) if isinstance(benchmark_readiness.get("blocking_issues"), list) else []),
                "manual_tasks": len(benchmark_readiness.get("manual_tasks", []) if isinstance(benchmark_readiness.get("manual_tasks"), list) else []),
            },
        )
        idea_experiment_contract = write_idea_experiment_contract_artifacts(
            research_plan,
            chosen_idea,
            exploration_map,
            plan,
            benchmark_readiness,
            config.execution,
            out_dir,
            ablation_plan=ablation_plan,
            preregistration=preregistration,
            constraint_compliance=constraint_compliance,
        )
        # T05：契约冻结/版本化——内容变化产生新版本并说明原因与影响（A12）。
        contract_history = append_contract_history(
            out_dir,
            idea_experiment_contract.get("contract") if isinstance(idea_experiment_contract.get("contract"), dict) else {},
            results_exist=(out_dir / "04-results.json").exists(),
        )
        manifest.record(
            "idea_experiment_contract",
            inputs=[
                "00-research-plan.json",
                "02-ideas.json",
                EXPLORATION_MAP_JSON,
                "03-experiment-plan.json",
                BENCHMARK_READINESS_JSON,
                ABLATION_PLAN_JSON,
                PREREGISTRATION_JSON,
                REVIEW_CONSTRAINT_COMPLIANCE_JSON,
                "run-config.json",
            ],
            outputs=[IDEA_EXPERIMENT_CONTRACT_JSON, IDEA_EXPERIMENT_CONTRACT_MD, CONTRACT_HISTORY_JSON],
            metrics={
                "status": idea_experiment_contract.get("status"),
                "contract_score": idea_experiment_contract.get("contract_score"),
                "contract_digest": idea_experiment_contract.get("contract_digest"),
                "contract_revision": (idea_experiment_contract.get("contract") or {}).get("revision") if isinstance(idea_experiment_contract.get("contract"), dict) else None,
                "history_revisions": len(contract_history.get("entries", []) if isinstance(contract_history.get("entries"), list) else []),
                "blocking_issues": len(idea_experiment_contract.get("blocking_issues", []) if isinstance(idea_experiment_contract.get("blocking_issues"), list) else []),
                "manual_tasks": len(idea_experiment_contract.get("manual_tasks", []) if isinstance(idea_experiment_contract.get("manual_tasks"), list) else []),
            },
        )
        if idea_experiment_contract.get("status") == "block":
            raise RuntimeError("Idea-experiment contract blocked execution: " + "; ".join(str(item) for item in idea_experiment_contract.get("blocking_issues", [])[:4]))
        _check_cancelled(out_dir, topic, manifest, "benchmark_plan_completed")

    def _node_execution_gate():
        nonlocal results_path
        results_path = out_dir / "04-results.json"
        if config.execution.mode in {"local", "benchmark"}:
            execution_approval = request_execution_approval(out_dir, topic, plan, execution_safety, config.execution.mode)
            _write_state(out_dir, topic, "awaiting_execution_approval")
            manifest.record(
                "execution_approval_requested",
                inputs=["03-experiment-plan.json", EXECUTION_SAFETY_AUDIT_JSON, "run-config.json"],
                outputs=[EXECUTION_APPROVAL_JSON, EXECUTION_APPROVAL_MD],
                metrics={
                    "approved": execution_approval.get("approved") is True,
                    "execution_mode": config.execution.mode,
                    "commands": len(plan.commands),
                },
            )
            if not _execution_approval_granted(out_dir):
                wait_for_execution_approval(out_dir, topic=topic, manifest=manifest)
            _write_state(out_dir, topic, "execution_approved")
            manifest.record(
                "execution_approval",
                inputs=[EXECUTION_APPROVAL_JSON],
                outputs=[EXECUTION_APPROVAL_JSON],
                metrics={"approved": True, "execution_mode": config.execution.mode},
            )

    def _node_experiments():
        nonlocal benchmark_evidence, experiment_decision, failure_analysis, hypothesis_outcome, result_validation, results, results_path, runbook, statistics
        results_path = out_dir / "04-results.json"
        # T06/A13：恢复前核对执行尝试——活任务不重复进入；结果文件损坏/
        # 为空则不按旧结果复用，转入重新执行。
        reuse_results: list | None = None
        if resume and results_path.exists():
            from . import experiment_attempts as _attempts

            live_attempt = _attempts.find_live_attempt(out_dir)
            if live_attempt is not None:
                raise RuntimeError(
                    "恢复中止：检测到仍在运行的实验执行尝试（task_id="
                    f"{live_attempt.get('task_id')}，pid={live_attempt.get('pid')}）；"
                    "请先停止旧进程或等其结束后再恢复，避免重复启动。"
                )
            _attempts.mark_interrupted_attempts(out_dir)
            loaded = _load_experiment_results(results_path)
            if _experiment_results_usable(loaded):
                reuse_results = loaded
        if reuse_results is not None:
            results = reuse_results
            runbook_outputs: list[str] = []
            if not (out_dir / EXPERIMENT_RUNBOOK_JSON).exists() or not (out_dir / EXPERIMENT_RUNBOOK_MD).exists():
                runbook = write_experiment_runbook(plan, config.execution, out_dir, results)
                runbook_outputs = [EXPERIMENT_RUNBOOK_JSON, EXPERIMENT_RUNBOOK_MD]
            else:
                runbook = _read_dict(out_dir / EXPERIMENT_RUNBOOK_JSON)
            benchmark_plan_report = _read_dict(out_dir / BENCHMARK_PLAN_JSON)
            adapter_report = _read_dict(out_dir / BENCHMARK_ADAPTER_JSON)
            audit_plan = _execution_audit_plan(plan, runbook, adapter_report, config.execution.mode)
            statistics = build_statistics_report(audit_plan, results)
            if not (out_dir / "04-statistics.json").exists():
                write_json(out_dir / "04-statistics.json", statistics)
            if not (out_dir / "04-statistics.md").exists():
                write_text(out_dir / "04-statistics.md", render_statistics_markdown(statistics))
            if not (out_dir / STATISTICS_FIGURE_JSON).exists() or not (out_dir / STATISTICS_FIGURE_SVG).exists():
                write_statistics_figure_artifacts(out_dir, statistics)
                runbook_outputs.extend([STATISTICS_FIGURE_JSON, STATISTICS_FIGURE_SVG])
            result_validation = write_result_validation_artifacts(
                audit_plan,
                results,
                statistics,
                out_dir,
                config.execution.repeats,
                preregistration=preregistration,
                execution_mode=config.execution.mode,
            )
            failure_analysis = write_failure_analysis_artifacts(audit_plan, results, statistics, result_validation, out_dir)
            benchmark_result_schema = write_benchmark_result_schema_audit_artifacts(
                audit_plan,
                results,
                statistics,
                runbook,
                out_dir,
                benchmark_plan=benchmark_plan_report,
                adapter_report=adapter_report,
                result_validation=result_validation,
            )
            benchmark_evidence = write_benchmark_evidence_audit_artifacts(
                audit_plan,
                results,
                statistics,
                result_validation,
                runbook,
                out_dir,
                execution_mode=config.execution.mode,
                benchmark_plan=benchmark_plan_report,
                adapter_report=adapter_report,
                paper_grade=config.paper_grade,
            )
            experiment_decision = write_experiment_decision_artifacts(
                audit_plan,
                statistics,
                result_validation,
                failure_analysis,
                out_dir,
                execution_mode=config.execution.mode,
                benchmark_plan=benchmark_plan_report,
                benchmark_evidence=benchmark_evidence,
            )
            hypothesis_outcome = write_hypothesis_outcome_artifacts(
                chosen_idea,
                audit_plan,
                statistics,
                result_validation,
                failure_analysis,
                experiment_decision,
                out_dir,
                execution_mode=config.execution.mode,
            )
            runbook_outputs.extend([RESULT_VALIDATION_JSON, RESULT_VALIDATION_MD, FAILURE_ANALYSIS_JSON, FAILURE_ANALYSIS_MD, BENCHMARK_RESULT_SCHEMA_AUDIT_JSON, BENCHMARK_RESULT_SCHEMA_AUDIT_MD, BENCHMARK_EVIDENCE_AUDIT_JSON, BENCHMARK_EVIDENCE_AUDIT_MD, EXPERIMENT_DECISION_JSON, EXPERIMENT_DECISION_MD, HYPOTHESIS_OUTCOME_JSON, HYPOTHESIS_OUTCOME_MD])
            manifest.record(
                "experiments_checkpoint",
                inputs=["04-results.json"],
                outputs=runbook_outputs,
                notes=["reused existing experiment results"],
                metrics={
                    "results": len(results),
                    "repeats": statistics.repeats,
                    "comparisons": len(statistics.comparisons),
                    "validation_status": result_validation.get("status"),
                    "failure_analysis_status": failure_analysis.get("status"),
                    "benchmark_result_schema_status": benchmark_result_schema.get("status"),
                    "benchmark_evidence_status": benchmark_evidence.get("status"),
                    "experiment_decision": experiment_decision.get("decision"),
                    "hypothesis_outcome": hypothesis_outcome.get("outcome"),
                },
            )
        else:

            # T07/A16：实验真实执行受冻结次数上限约束（checkpoint 复用不计数）。
            ensure_budget(out_dir, "experiment_runs")
            # T05：执行启动时绑定当前契约内容摘要（审计器读取同一契约做一致性核对）。
            _contract_report = _read_dict(out_dir / IDEA_EXPERIMENT_CONTRACT_JSON)
            results = run_experiments(
                plan,
                config.execution,
                out_dir,
                paper_grade=config.paper_grade,
                contract_digest=str(_contract_report.get("contract_digest") or ""),
            )
            record_execution(out_dir, "experiment_runs", note="experiments node executed")
            write_json(results_path, results)
            runbook = _read_dict(out_dir / EXPERIMENT_RUNBOOK_JSON)
            benchmark_plan_report = _read_dict(out_dir / BENCHMARK_PLAN_JSON)
            adapter_report = _read_dict(out_dir / BENCHMARK_ADAPTER_JSON)
            audit_plan = _execution_audit_plan(plan, runbook, adapter_report, config.execution.mode)
            statistics = build_statistics_report(audit_plan, results)
            write_json(out_dir / "04-statistics.json", statistics)
            write_text(out_dir / "04-statistics.md", render_statistics_markdown(statistics))
            write_statistics_figure_artifacts(out_dir, statistics)
            result_validation = write_result_validation_artifacts(
                audit_plan,
                results,
                statistics,
                out_dir,
                config.execution.repeats,
                preregistration=preregistration,
                execution_mode=config.execution.mode,
            )
            failure_analysis = write_failure_analysis_artifacts(audit_plan, results, statistics, result_validation, out_dir)
            benchmark_result_schema = write_benchmark_result_schema_audit_artifacts(
                audit_plan,
                results,
                statistics,
                runbook,
                out_dir,
                benchmark_plan=benchmark_plan_report,
                adapter_report=adapter_report,
                result_validation=result_validation,
            )
            benchmark_evidence = write_benchmark_evidence_audit_artifacts(
                audit_plan,
                results,
                statistics,
                result_validation,
                runbook,
                out_dir,
                execution_mode=config.execution.mode,
                benchmark_plan=benchmark_plan_report,
                adapter_report=adapter_report,
                paper_grade=config.paper_grade,
            )
            experiment_decision = write_experiment_decision_artifacts(
                audit_plan,
                statistics,
                result_validation,
                failure_analysis,
                out_dir,
                execution_mode=config.execution.mode,
                benchmark_plan=benchmark_plan_report,
                benchmark_evidence=benchmark_evidence,
            )
            hypothesis_outcome = write_hypothesis_outcome_artifacts(
                chosen_idea,
                audit_plan,
                statistics,
                result_validation,
                failure_analysis,
                experiment_decision,
                out_dir,
                execution_mode=config.execution.mode,
            )
            experiment_outputs = [
                "04-results.json",
                "04-results.csv",
                EXPERIMENT_RUNBOOK_JSON,
                EXPERIMENT_RUNBOOK_MD,
                "04-statistics.json",
                "04-statistics.md",
                STATISTICS_FIGURE_JSON,
                STATISTICS_FIGURE_SVG,
                RESULT_VALIDATION_JSON,
                RESULT_VALIDATION_MD,
                FAILURE_ANALYSIS_JSON,
                FAILURE_ANALYSIS_MD,
                BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
                BENCHMARK_RESULT_SCHEMA_AUDIT_MD,
                BENCHMARK_EVIDENCE_AUDIT_JSON,
                BENCHMARK_EVIDENCE_AUDIT_MD,
                EXPERIMENT_DECISION_JSON,
                EXPERIMENT_DECISION_MD,
                HYPOTHESIS_OUTCOME_JSON,
                HYPOTHESIS_OUTCOME_MD,
                "experiments/experiment-template.json",
            ]
            if (out_dir / BENCHMARK_ADAPTER_JSON).exists():
                experiment_outputs.extend([BENCHMARK_ADAPTER_JSON, BENCHMARK_ADAPTER_MD])
            _write_state(out_dir, topic, "experiments_completed")
            manifest.record(
                "experiments",
                inputs=["03-experiment-plan.json"],
                outputs=experiment_outputs,
                metrics={
                    "results": len(results),
                    "repeats": statistics.repeats,
                    "comparisons": len(statistics.comparisons),
                    "validation_status": result_validation.get("status"),
                    "failure_analysis_status": failure_analysis.get("status"),
                    "benchmark_result_schema_status": benchmark_result_schema.get("status"),
                    "benchmark_evidence_status": benchmark_evidence.get("status"),
                    "experiment_decision": experiment_decision.get("decision"),
                    "hypothesis_outcome": hypothesis_outcome.get("outcome"),
                },
            )
        _check_cancelled(out_dir, topic, manifest, "experiments_completed")

    def _node_analysis():
        nonlocal analysis, claim_boundary_preflight
        analysis_path = out_dir / "05-analysis.json"
        checkpoint_analysis = _load_analysis(analysis_path) if resume and analysis_path.exists() else None
        if checkpoint_analysis is not None and analysis_matches_execution_mode(checkpoint_analysis, config.execution.mode):
            analysis = checkpoint_analysis
            if not (out_dir / "05-analysis.md").exists():
                write_text(out_dir / "05-analysis.md", render_analysis_markdown(analysis))
            manifest.record(
                "analysis_checkpoint",
                inputs=["05-analysis.json"],
                outputs=[],
                notes=["reused existing analysis"],
                metrics={"findings": len(analysis.findings), "limitations": len(analysis.limitations)},
            )
        else:

            analysis = analyze_results(results, statistics, execution_mode=config.execution.mode)
            write_json(analysis_path, analysis)
            write_text(out_dir / "05-analysis.md", render_analysis_markdown(analysis))
            _write_state(out_dir, topic, "analysis_completed")
            manifest.record(
                "analysis",
                inputs=["04-results.json", "04-statistics.json"],
                outputs=["05-analysis.json", "05-analysis.md"],
                metrics={"findings": len(analysis.findings), "limitations": len(analysis.limitations)},
            )
        _check_cancelled(out_dir, topic, manifest, "analysis_completed")

        claim_preflight_path = out_dir / CLAIM_BOUNDARY_PREFLIGHT_JSON
        claim_boundary_preflight = _read_dict(claim_preflight_path) if resume and claim_preflight_path.exists() else {}
        if resume and claim_preflight_path.exists() and _claim_boundary_preflight_checkpoint_matches(
            claim_boundary_preflight,
            result_validation,
            failure_analysis,
            benchmark_evidence,
            experiment_decision,
            hypothesis_outcome,
            config.execution.mode,
        ):
            if not (out_dir / CLAIM_BOUNDARY_PREFLIGHT_MD).exists():
                write_text(out_dir / CLAIM_BOUNDARY_PREFLIGHT_MD, render_claim_boundary_preflight_markdown(claim_boundary_preflight))
            manifest.record(
                "claim_boundary_preflight_checkpoint",
                inputs=[CLAIM_BOUNDARY_PREFLIGHT_JSON],
                outputs=[],
                notes=["reused existing claim boundary preflight"],
                metrics={"status": claim_boundary_preflight.get("status"), "writing_mode": claim_boundary_preflight.get("writing_mode")},
            )
        else:
            claim_boundary_preflight = write_claim_boundary_preflight_artifacts(
                topic,
                plan,
                statistics,
                analysis,
                result_validation,
                failure_analysis,
                benchmark_evidence,
                experiment_decision,
                hypothesis_outcome,
                out_dir,
                execution_mode=config.execution.mode,
            )
            manifest.record(
                "claim_boundary_preflight",
                inputs=[RESULT_VALIDATION_JSON, FAILURE_ANALYSIS_JSON, BENCHMARK_EVIDENCE_AUDIT_JSON, EXPERIMENT_DECISION_JSON, HYPOTHESIS_OUTCOME_JSON, "05-analysis.json"],
                outputs=[CLAIM_BOUNDARY_PREFLIGHT_JSON, CLAIM_BOUNDARY_PREFLIGHT_MD],
                metrics={
                    "status": claim_boundary_preflight.get("status"),
                    "writing_mode": claim_boundary_preflight.get("writing_mode"),
                    "risk_score": claim_boundary_preflight.get("risk_score"),
                    "blocking_issues": len(claim_boundary_preflight.get("blocking_issues", []) if isinstance(claim_boundary_preflight.get("blocking_issues"), list) else []),
                    "warnings": len(claim_boundary_preflight.get("warnings", []) if isinstance(claim_boundary_preflight.get("warnings"), list) else []),
                },
            )
        _check_cancelled(out_dir, topic, manifest, "claim_boundary_preflight_completed")

    def _node_paper_writing():
        nonlocal evidence_integrity, paper_checkpoint_reusable, paper_md, paper_path, paper_review_path, review_calibration_outputs, review_calibration_path
        paper_path = out_dir / "06-paper.md"
        paper_review_path = out_dir / "07-paper-review.json"
        review_calibration_path = out_dir / PAPER_REVIEW_CALIBRATION_JSON
        review_calibration_outputs = []
        paper_checkpoint_reusable = resume and paper_path.exists() and _paper_matches_benchmark_evidence(paper_path, benchmark_evidence, config.execution.mode)

        evidence_integrity = write_evidence_integrity_artifacts(topic, out_dir)
        if paper_checkpoint_reusable:
            paper_md = paper_path.read_text(encoding="utf-8")
            if not (out_dir / "06-paper.tex").exists():
                write_text(out_dir / "06-paper.tex", markdown_to_latex(paper_md))
        else:
            paper_md = write_paper_markdown(
                topic,
                review,
                ideas,
                plan,
                analysis,
                config.paper,
                llm,
                failure_analysis=failure_analysis,
                experiment_decision=experiment_decision,
                hypothesis_outcome=hypothesis_outcome,
                claim_boundary_preflight=claim_boundary_preflight,
                benchmark_evidence=benchmark_evidence,
                evidence_integrity=evidence_integrity,
                runbook=runbook,
                model_source_recorder=_model_source_recorder(out_dir),
            )
            write_text(paper_path, paper_md)
            write_text(out_dir / "06-paper.tex", markdown_to_latex(paper_md))

    def _node_paper_review():
        nonlocal paper_review, review_calibration, review_calibration_outputs
        if paper_checkpoint_reusable and paper_review_path.exists():
            paper_review = _load_paper_review(paper_review_path)
            if not (out_dir / "06-paper.tex").exists():
                write_text(out_dir / "06-paper.tex", markdown_to_latex(paper_path.read_text(encoding="utf-8")))
            if not (out_dir / "07-paper-review.md").exists():
                write_text(out_dir / "07-paper-review.md", render_paper_review_markdown(paper_review))
            review_calibration = _read_dict(review_calibration_path) if review_calibration_path.exists() else {}
            if not review_calibration_path.exists() or not _paper_review_calibration_checkpoint_matches(
                review_calibration,
                experiment_decision,
                hypothesis_outcome,
                config.execution.mode,
            ):
                review_calibration = write_paper_review_calibration_artifacts(
                    topic,
                    paper_review,
                    out_dir,
                    experiment_decision=experiment_decision,
                    hypothesis_outcome=hypothesis_outcome,
                    execution_mode=config.execution.mode,
                )
                review_calibration_outputs = [PAPER_REVIEW_CALIBRATION_JSON, PAPER_REVIEW_CALIBRATION_MD]
            manifest.record(
                "paper_and_review_checkpoint",
                inputs=["06-paper.md", "07-paper-review.json"],
                outputs=review_calibration_outputs,
                notes=["reused existing paper draft and review"],
                metrics={"calibration_status": review_calibration.get("status")},
            )
        else:
            paper_review = review_paper_draft(topic, review, ideas, plan, analysis, paper_md, context, llm, paper_config=config.paper, model_source_recorder=_model_source_recorder(out_dir))
            write_json(paper_review_path, paper_review)
            write_text(out_dir / "07-paper-review.md", render_paper_review_markdown(paper_review))
            review_calibration = write_paper_review_calibration_artifacts(
                topic,
                paper_review,
                out_dir,
                experiment_decision=experiment_decision,
                hypothesis_outcome=hypothesis_outcome,
                execution_mode=config.execution.mode,
            )
            _write_state(out_dir, topic, "paper_review_completed")
            manifest.record(
                "paper_and_review",
                inputs=["01-literature-curated.json", "02-ideas.json", "03-experiment-plan.json", "04-results.json", "05-analysis.json", CLAIM_BOUNDARY_PREFLIGHT_JSON, "01-context.json"],
                outputs=["06-paper.md", "06-paper.tex", "07-paper-review.json", "07-paper-review.md", PAPER_REVIEW_CALIBRATION_JSON, PAPER_REVIEW_CALIBRATION_MD, EVIDENCE_INTEGRITY_JSON, EVIDENCE_INTEGRITY_MD],
                metrics={
                    "decision": paper_review.decision,
                    "score": paper_review.score,
                    "required_revisions": len(paper_review.required_revisions),
                    "calibration_status": review_calibration.get("status"),
                    "evidence_integrity": evidence_integrity.status,
                },
            )
        _check_cancelled(out_dir, topic, manifest, "paper_review_completed")

    def _node_paper_revision():
        nonlocal paper_md, revised_paper_md, revised_paper_path, revision_report

        # T07/A16：修订轮次冻结上限；恢复同样在此被拦。
        ensure_budget(out_dir, "paper_revisions")
        revision_plan_path = out_dir / REVISION_PLAN_JSON
        if resume and revision_plan_path.exists() and _paper_revision_plan_checkpoint_matches(
            _load_paper_revision_plan(revision_plan_path),
            build_paper_revision_plan(topic, paper_review, experiment_decision=experiment_decision, review_calibration=review_calibration),
        ):
            revision_plan = _load_paper_revision_plan(revision_plan_path)
            if not (out_dir / REVISION_PLAN_MD).exists():
                write_text(out_dir / REVISION_PLAN_MD, render_paper_revision_plan_markdown(revision_plan))
            manifest.record(
                "paper_revision_plan_checkpoint",
                inputs=[REVISION_PLAN_JSON],
                outputs=[],
                notes=["reused existing paper revision plan"],
                metrics={"tasks": len(revision_plan.tasks), "readiness": revision_plan.readiness},
            )
        else:
            revision_plan = build_paper_revision_plan(topic, paper_review, experiment_decision=experiment_decision, review_calibration=review_calibration)
            write_json(revision_plan_path, revision_plan)
            write_text(out_dir / REVISION_PLAN_MD, render_paper_revision_plan_markdown(revision_plan))
            _write_state(out_dir, topic, "revision_plan_completed")
            manifest.record(
                "paper_revision_plan",
                inputs=["07-paper-review.json"],
                outputs=[REVISION_PLAN_JSON, REVISION_PLAN_MD],
                metrics={"tasks": len(revision_plan.tasks), "readiness": revision_plan.readiness},
            )
        _check_cancelled(out_dir, topic, manifest, "revision_plan_completed")

        revised_paper_path = out_dir / REVISED_PAPER_MD
        revision_report_path = out_dir / REVISION_REPORT_JSON
        if resume and revised_paper_path.exists() and revision_report_path.exists() and _paper_matches_benchmark_evidence(revised_paper_path, benchmark_evidence, config.execution.mode):
            revision_report = _load_paper_rewrite_report(revision_report_path)
            if not (out_dir / REVISED_PAPER_TEX).exists():
                write_text(out_dir / REVISED_PAPER_TEX, markdown_to_latex(revised_paper_path.read_text(encoding="utf-8")))
            if not (out_dir / REVISION_REPORT_MD).exists():
                write_text(out_dir / REVISION_REPORT_MD, render_rewrite_report_markdown(revision_report))
            manifest.record(
                "paper_rewrite_checkpoint",
                inputs=[REVISED_PAPER_MD, REVISION_REPORT_JSON],
                outputs=[],
                notes=["reused existing revised paper draft"],
                metrics={"deferred_tasks": len(revision_report.deferred_tasks)},
            )
        else:
            paper_md = paper_path.read_text(encoding="utf-8")
            revised_paper_md, revision_report = revise_paper_draft(topic, paper_md, revision_plan, paper_review, llm, benchmark_evidence=benchmark_evidence, paper_config=config.paper, model_source_recorder=_model_source_recorder(out_dir))
            record_execution(out_dir, "paper_revisions", note="paper_revision node executed")
            write_text(revised_paper_path, revised_paper_md)
            write_text(out_dir / REVISED_PAPER_TEX, markdown_to_latex(revised_paper_md))
            write_json(revision_report_path, revision_report)
            write_text(out_dir / REVISION_REPORT_MD, render_rewrite_report_markdown(revision_report))
            _write_state(out_dir, topic, "paper_revision_completed")
            manifest.record(
                "paper_rewrite",
                inputs=["06-paper.md", "07-paper-review.json", REVISION_PLAN_JSON],
                outputs=[REVISED_PAPER_MD, REVISED_PAPER_TEX, REVISION_REPORT_JSON, REVISION_REPORT_MD],
                metrics={"tasks": len(revision_report.task_results), "deferred_tasks": len(revision_report.deferred_tasks)},
            )
        _check_cancelled(out_dir, topic, manifest, "paper_revision_completed")

        revision_response_audit_path = out_dir / REVISION_RESPONSE_AUDIT_JSON
        if resume and revision_response_audit_path.exists():
            revision_response_audit = _read_dict(revision_response_audit_path)
            if not (out_dir / REVISION_RESPONSE_AUDIT_MD).exists():
                write_text(out_dir / REVISION_RESPONSE_AUDIT_MD, render_revision_response_audit_markdown(revision_response_audit))
            manifest.record(
                "revision_response_audit_checkpoint",
                inputs=[REVISION_RESPONSE_AUDIT_JSON],
                outputs=[],
                notes=["reused existing revision response audit"],
                metrics={"status": revision_response_audit.get("status"), "response_score": revision_response_audit.get("response_score")},
            )
        else:
            revised_paper_md = revised_paper_path.read_text(encoding="utf-8")
            revision_response_audit = write_revision_response_audit_artifacts(topic, revision_plan, revision_report, revised_paper_md, out_dir)
            _write_state(out_dir, topic, "revision_response_audit_completed")
            manifest.record(
                "revision_response_audit",
                inputs=[REVISION_PLAN_JSON, REVISION_REPORT_JSON, REVISED_PAPER_MD],
                outputs=[REVISION_RESPONSE_AUDIT_JSON, REVISION_RESPONSE_AUDIT_MD],
                metrics={
                    "status": revision_response_audit.get("status"),
                    "response_score": revision_response_audit.get("response_score"),
                    "blocking_issues": len(revision_response_audit.get("blocking_issues", []) if isinstance(revision_response_audit.get("blocking_issues"), list) else []),
                    "manual_tasks": len(revision_response_audit.get("manual_tasks", []) if isinstance(revision_response_audit.get("manual_tasks"), list) else []),
                },
            )
        _check_cancelled(out_dir, topic, manifest, "revision_response_audit_completed")

    def _node_finalization():
        nonlocal repair_queue, repair_resume, revised_paper_md, revised_paper_path, revision_report
        if revision_report is None:
            from .models import PaperRewriteReport

            revision_report = PaperRewriteReport(
                topic=topic,
                source_paper="06-paper.md",
                revised_paper=REVISED_PAPER_MD,
                revision_plan="08-revision-plan.json",
                summary="实验后决策路由跳过修订轮（如负结果报告），本次未执行修订任务。",
                task_results=[],
                deferred_tasks=[],
                next_checks=["如需修订，人工发起 revision 或 repair-resume。"],
            )
        if experiment_decision.get("downstream_writing_allowed") is False:
            repair_report = _write_experiment_repair_gate(
                topic,
                out_dir,
                experiment_decision,
                claim_boundary_preflight,
                result_validation,
                failure_analysis,
            )
            repair_queue = write_repair_queue_artifacts(topic, out_dir)
            repair_resume = write_repair_resume_plan_artifacts(out_dir, apply=False)
            _write_state(out_dir, topic, "awaiting_experiment_repair")
            manifest.record(
                "experiment_repair_gate",
                status="blocked",
                inputs=[EXPERIMENT_DECISION_JSON, CLAIM_BOUNDARY_PREFLIGHT_JSON, RESULT_VALIDATION_JSON, FAILURE_ANALYSIS_JSON],
                outputs=[EXPERIMENT_REPAIR_REPORT_JSON, EXPERIMENT_REPAIR_REPORT_MD, REPAIR_QUEUE_JSON, REPAIR_QUEUE_MD, REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD, "state.json"],
                metrics={
                    "decision": experiment_decision.get("decision"),
                    "writing_allowed": False,
                    "blocking_issues": len(repair_report.get("blocking_issues", [])),
                    "repair_queue_items": len(repair_queue.items),
                    "rerun_from": repair_resume.get("rerun_from"),
                },
                notes=["论文 LLM、审稿 LLM 和后续投稿阶段均未调用。"],
            )
            # STATE-01: writing and its downstream review/revision nodes are
            # deliberately skipped in the writing-blocked branch.
            try:
                append_node_events(
                    out_dir,
                    [("paper_writing", "skipped"), ("paper_review", "skipped"), ("paper_revision", "skipped")],
                    detail="writing_blocked",
                )
            except Exception:
                pass
            return NodeOutcome("waiting")

        # T07/A15 兜底：正常写作路径上若修订稿缺失（旧 run 恢复或路由变化），
        # 以复核后的原稿进入审计链路，并如实记录修订未执行。
        paper_file = out_dir / "06-paper.md"
        revised_paper_file = out_dir / REVISED_PAPER_MD
        if revised_paper_path is None:
            revised_paper_path = revised_paper_file
        if revised_paper_md is None and revised_paper_file.exists():
            revised_paper_md = revised_paper_file.read_text(encoding="utf-8")
        if revised_paper_md is None and not resume:
            revised_paper_md = paper_md if paper_md else paper_file.read_text(encoding="utf-8")
            write_text(revised_paper_file, revised_paper_md)
            if not (out_dir / REVISED_PAPER_TEX).exists():
                write_text(out_dir / REVISED_PAPER_TEX, markdown_to_latex(revised_paper_md))
            manifest.record(
                "paper_revision_skipped_by_decision",
                inputs=["06-paper.md", EXPERIMENT_DECISION_JSON],
                outputs=[REVISED_PAPER_MD],
                notes=["实验后决策路由跳过修订轮（如负结果报告），09 稿与 06 稿一致。"],
                metrics={"decision": experiment_decision.get("decision") if experiment_decision else ""},
            )


        revised_review_path = out_dir / REVISED_PAPER_REVIEW_JSON
        availability_path = out_dir / CODE_DATA_AVAILABILITY_JSON
        submission_path = out_dir / SUBMISSION_CHECK_JSON
        release_path = out_dir / RELEASE_METADATA_JSON
        ai_disclosure_path = out_dir / AI_DISCLOSURE_JSON
        claim_traceability_path = out_dir / CLAIM_TRACEABILITY_JSON
        agent_claim_audit_path = out_dir / MULTI_AGENT_PAPER_AUDIT_JSON
        agent_deliberation_path = out_dir / MULTI_AGENT_DELIBERATION_JSON
        citation_grounding_path = out_dir / CITATION_GROUNDING_JSON
        citation_coverage_path = out_dir / CITATION_COVERAGE_JSON
        results_presentation_path = out_dir / RESULTS_PRESENTATION_JSON
        claim_consistency_path = out_dir / CLAIM_CONSISTENCY_JSON
        final_readiness_path = out_dir / FINAL_READINESS_JSON
        if resume and revised_review_path.exists() and final_readiness_path.exists() and availability_path.exists() and submission_path.exists() and _submission_check_has_item(submission_path, "修订响应审计") and _submission_check_has_item(submission_path, "Citation coverage 审计") and release_path.exists() and ai_disclosure_path.exists() and claim_traceability_path.exists() and citation_grounding_path.exists() and citation_coverage_path.exists() and results_presentation_path.exists() and claim_consistency_path.exists() and _final_readiness_checkpoint_reusable(out_dir, benchmark_evidence, config.execution.mode):
            revised_review = _load_paper_review(revised_review_path)
            availability_report = _load_code_data_availability_report(availability_path)
            submission_report = _load_submission_check_report(submission_path)
            claim_traceability = _load_claim_traceability_report(claim_traceability_path)
            agent_claim_audit_outputs: list[str] = []
            if agent_claim_audit_path.exists():
                agent_claim_audit = _read_dict(agent_claim_audit_path)
                if not (out_dir / MULTI_AGENT_PAPER_AUDIT_MD).exists():
                    write_text(out_dir / MULTI_AGENT_PAPER_AUDIT_MD, render_multi_agent_paper_audit_markdown(agent_claim_audit))
                    agent_claim_audit_outputs = [MULTI_AGENT_PAPER_AUDIT_MD]
            else:
                agent_claim_audit = write_multi_agent_paper_audit_artifacts(topic, chosen_idea, plan, paper_review, revised_review, claim_traceability, agent_assignment, out_dir)
                agent_claim_audit_outputs = [MULTI_AGENT_PAPER_AUDIT_JSON, MULTI_AGENT_PAPER_AUDIT_MD]
            citation_grounding = _load_citation_grounding_report(citation_grounding_path)
            citation_coverage = _read_dict(citation_coverage_path)
            results_presentation = _load_results_presentation_report(results_presentation_path)
            claim_consistency = _load_claim_consistency_report(claim_consistency_path)
            agent_deliberation_outputs: list[str] = []
            if agent_deliberation_path.exists():
                agent_deliberation = _read_dict(agent_deliberation_path)
                if not (out_dir / MULTI_AGENT_DELIBERATION_MD).exists():
                    write_text(out_dir / MULTI_AGENT_DELIBERATION_MD, render_multi_agent_deliberation_markdown(agent_deliberation))
                    agent_deliberation_outputs = [MULTI_AGENT_DELIBERATION_MD]
            else:
                agent_deliberation = write_multi_agent_deliberation_artifacts(
                    topic,
                    agent_assignment,
                    agent_claim_audit,
                    claim_traceability,
                    citation_grounding,
                    citation_coverage,
                    results_presentation,
                    claim_consistency,
                    out_dir,
                )
                agent_deliberation_outputs = [MULTI_AGENT_DELIBERATION_JSON, MULTI_AGENT_DELIBERATION_MD]
            gate_decision, gate_outputs = _finalize_gate_decision(
                topic,
                out_dir,
                config,
                llm,
                agent_deliberation=agent_deliberation,
                claim_consistency=claim_consistency if isinstance(claim_consistency, dict) else {},
                citation_grounding=citation_grounding,
                revised_review=revised_review,
                resume=True,
            )
            agent_deliberation_outputs = [*agent_deliberation_outputs, *gate_outputs]
            final_readiness = _load_final_readiness_report(final_readiness_path)
            from .final_readiness import apply_gate_to_final_readiness as _apply_gate

            final_readiness = _apply_gate(final_readiness, gate_decision)
            if not (out_dir / REVISED_PAPER_REVIEW_MD).exists():
                write_text(out_dir / REVISED_PAPER_REVIEW_MD, render_paper_review_markdown(revised_review))
            if not (out_dir / CLAIM_TRACEABILITY_MD).exists():
                write_text(out_dir / CLAIM_TRACEABILITY_MD, render_claim_traceability_markdown(claim_traceability))
            if not (out_dir / CITATION_GROUNDING_MD).exists():
                write_text(out_dir / CITATION_GROUNDING_MD, render_citation_grounding_markdown(citation_grounding))
            if not (out_dir / CITATION_COVERAGE_MD).exists():
                write_text(out_dir / CITATION_COVERAGE_MD, render_citation_coverage_markdown(citation_coverage))
            if not (out_dir / RESULTS_PRESENTATION_MD).exists():
                write_text(out_dir / RESULTS_PRESENTATION_MD, render_results_presentation_markdown(results_presentation))
            if not (out_dir / CLAIM_CONSISTENCY_MD).exists():
                write_text(out_dir / CLAIM_CONSISTENCY_MD, render_claim_consistency_markdown(claim_consistency))
            if not (out_dir / CODE_DATA_AVAILABILITY_MD).exists():
                write_text(out_dir / CODE_DATA_AVAILABILITY_MD, render_code_data_availability_markdown(availability_report))
            if not (out_dir / SUBMISSION_CHECK_MD).exists():
                write_text(out_dir / SUBMISSION_CHECK_MD, render_submission_check_markdown(submission_report))
            if not (out_dir / AI_DISCLOSURE_MD).exists():
                write_text(out_dir / AI_DISCLOSURE_MD, render_ai_disclosure_markdown(_read_dict(ai_disclosure_path)))
            if not (out_dir / FINAL_READINESS_MD).exists():
                write_text(out_dir / FINAL_READINESS_MD, render_final_readiness_markdown(final_readiness))
            manifest.record(
                "final_readiness_checkpoint",
                inputs=[REVISED_PAPER_REVIEW_JSON, REVISION_RESPONSE_AUDIT_JSON, CITATION_COVERAGE_JSON, RESULTS_PRESENTATION_JSON, CLAIM_CONSISTENCY_JSON, CODE_DATA_AVAILABILITY_JSON, SUBMISSION_CHECK_JSON, FINAL_READINESS_JSON],
                outputs=[*agent_claim_audit_outputs, *agent_deliberation_outputs],
                notes=["reused existing final readiness report"],
                metrics={"status": final_readiness.status, "score_after": final_readiness.score_after, "agent_claim_audit_status": agent_claim_audit.get("status"), "agent_deliberation_status": agent_deliberation.get("status")},
            )
        else:
            revised_paper_md = revised_paper_path.read_text(encoding="utf-8")
            revised_review = review_paper_draft(topic, review, ideas, plan, analysis, revised_paper_md, context, llm, paper_config=config.paper, model_source_recorder=_model_source_recorder(out_dir))
            write_json(revised_review_path, revised_review)
            write_text(out_dir / REVISED_PAPER_REVIEW_MD, render_paper_review_markdown(revised_review))
            claim_traceability = write_claim_traceability_artifacts(topic, out_dir, revised_review, context)
            agent_claim_audit = write_multi_agent_paper_audit_artifacts(topic, chosen_idea, plan, paper_review, revised_review, claim_traceability, agent_assignment, out_dir)
            citation_grounding = write_citation_grounding_artifacts(topic, out_dir, context)
            _write_literature_gate_decision_from_artifacts(out_dir=out_dir, context=context, topic=topic, citation_grounding_report=citation_grounding, paper_grade_config=config.paper_grade)
            citation_coverage = write_citation_coverage_artifacts(topic, out_dir, context)
            results_presentation = write_results_presentation_artifacts(topic, out_dir)
            claim_consistency = write_claim_consistency_artifacts(topic, out_dir)
            agent_deliberation = write_multi_agent_deliberation_artifacts(
                topic,
                agent_assignment,
                agent_claim_audit,
                claim_traceability,
                citation_grounding,
                citation_coverage,
                results_presentation,
                claim_consistency,
                out_dir,
            )
            release_report = write_release_metadata_artifacts(topic, out_dir, config.release)
            availability_report = write_code_data_availability_artifacts(topic, out_dir, revised_paper_md)
            ai_disclosure_report = write_ai_disclosure_artifacts(topic, out_dir)
            submission_report = write_submission_check_artifacts(topic, out_dir, config.paper)
            gate_decision, gate_outputs = _finalize_gate_decision(
                topic,
                out_dir,
                config,
                llm,
                agent_deliberation=agent_deliberation,
                claim_consistency=claim_consistency if isinstance(claim_consistency, dict) else {},
                citation_grounding=citation_grounding,
                revised_review=revised_review,
                resume=False,
            )
            final_readiness = build_final_readiness_report(topic, paper_review, revised_review, revision_report, availability_report, submission_report, claim_traceability, evidence_integrity=assess_evidence_integrity(out_dir), gate_decision=gate_decision)
            write_json(final_readiness_path, final_readiness)
            write_text(out_dir / FINAL_READINESS_MD, render_final_readiness_markdown(final_readiness))
            _write_state(out_dir, topic, "final_readiness_completed")
            manifest.record(
                "final_readiness",
                inputs=[REVISED_PAPER_MD, REVISION_REPORT_JSON, REVISION_RESPONSE_AUDIT_JSON, "07-paper-review.json", EXPERIMENT_RUNBOOK_JSON, CLAIM_TRACEABILITY_JSON, CITATION_GROUNDING_JSON, CITATION_COVERAGE_JSON, RESULTS_PRESENTATION_JSON, CLAIM_CONSISTENCY_JSON],
                outputs=[
                    REVISED_PAPER_REVIEW_JSON,
                    REVISED_PAPER_REVIEW_MD,
                    CLAIM_TRACEABILITY_JSON,
                    CLAIM_TRACEABILITY_MD,
                    MULTI_AGENT_PAPER_AUDIT_JSON,
                    MULTI_AGENT_PAPER_AUDIT_MD,
                    CITATION_GROUNDING_JSON,
                    CITATION_GROUNDING_MD,
                    CITATION_COVERAGE_JSON,
                    CITATION_COVERAGE_MD,
                    RESULTS_PRESENTATION_JSON,
                    RESULTS_PRESENTATION_MD,
                    CLAIM_CONSISTENCY_JSON,
                    CLAIM_CONSISTENCY_MD,
                    MULTI_AGENT_DELIBERATION_JSON,
                    MULTI_AGENT_DELIBERATION_MD,
                    RELEASE_METADATA_JSON,
                    RELEASE_METADATA_MD,
                    CODE_DATA_AVAILABILITY_JSON,
                    CODE_DATA_AVAILABILITY_MD,
                    AI_DISCLOSURE_JSON,
                    AI_DISCLOSURE_MD,
                    SUBMISSION_CHECK_JSON,
                    SUBMISSION_CHECK_MD,
                    FINAL_READINESS_JSON,
                    FINAL_READINESS_MD,
                ],
                metrics={
                    "status": final_readiness.status,
                    "score_before": final_readiness.score_before,
                    "score_after": final_readiness.score_after,
                    "deferred_tasks": len(final_readiness.deferred_tasks),
                    "release_status": release_report.status,
                    "ai_disclosure_status": ai_disclosure_report.get("status"),
                    "claim_traceability_status": claim_traceability.status,
                    "claim_traceability_score": claim_traceability.traceability_score,
                    "agent_claim_audit_status": agent_claim_audit.get("status"),
                    "agent_claim_orphaned_claims": agent_claim_audit.get("claim_owner_summary", {}).get("orphaned_claims") if isinstance(agent_claim_audit.get("claim_owner_summary"), dict) else None,
                    "citation_grounding_status": citation_grounding.status,
                    "citation_grounding_score": citation_grounding.grounding_score,
                    "citation_coverage_status": citation_coverage.get("status"),
                    "citation_coverage_score": citation_coverage.get("coverage_score"),
                    "results_presentation_status": results_presentation.status,
                    "results_presentation_score": results_presentation.presentation_score,
                    "claim_consistency_status": claim_consistency.status,
                    "claim_consistency_score": claim_consistency.consistency_score,
                    "agent_deliberation_status": agent_deliberation.get("status"),
                    "agent_deliberation_consensus": agent_deliberation.get("consensus", {}).get("decision") if isinstance(agent_deliberation.get("consensus"), dict) else None,
                    "availability_status": final_readiness.availability_status,
                    "submission_status": final_readiness.submission_status,
                },
            )
        submission_package = write_submission_package_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "submission_package_completed")
        manifest.record(
            "submission_package",
            inputs=[REVISED_PAPER_MD, "01-references.bib", CLAIM_BOUNDARY_PREFLIGHT_JSON, REVISION_RESPONSE_AUDIT_JSON, FINAL_READINESS_JSON, CLAIM_TRACEABILITY_JSON, MULTI_AGENT_PAPER_AUDIT_JSON, MULTI_AGENT_DELIBERATION_JSON, CITATION_GROUNDING_JSON, CITATION_COVERAGE_JSON, RESULTS_PRESENTATION_JSON, CLAIM_CONSISTENCY_JSON, CODE_DATA_AVAILABILITY_JSON, AI_DISCLOSURE_JSON, SUBMISSION_CHECK_JSON, "run-manifest.json"],
            outputs=[SUBMISSION_PACKAGE_MD, SUBMISSION_PACKAGE_JSON, SUBMISSION_PACKAGE_ZIP],
            metrics={
                "status": submission_package.status,
                "files": len(submission_package.files),
                "blocking_issues": len(submission_package.blocking_issues),
                "manual_tasks": len(submission_package.manual_tasks),
            },
        )
        iteration_plan = write_iteration_plan_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "iteration_plan_completed")
        manifest.record(
            "iteration_plan",
            inputs=[
                LITERATURE_RESCUE_PLAN_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                RESULT_VALIDATION_JSON,
                FAILURE_ANALYSIS_JSON,
                REVISION_RESPONSE_AUDIT_JSON,
                FINAL_READINESS_JSON,
                CITATION_GROUNDING_JSON,
                CITATION_COVERAGE_JSON,
                CODE_DATA_AVAILABILITY_JSON,
                SUBMISSION_CHECK_JSON,
                SUBMISSION_PACKAGE_JSON,
                EXPERIMENT_RUNBOOK_JSON,
                BENCHMARK_PLAN_JSON,
            ],
            outputs=[ITERATION_PLAN_MD, ITERATION_PLAN_JSON],
            metrics={
                "status": iteration_plan.status,
                "items": len(iteration_plan.items),
                "decision": iteration_plan.decision,
            },
        )
        llm_trace_audit = write_llm_trace_audit_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "llm_trace_audit_completed")
        llm_coverage = llm_trace_audit.get("coverage") if isinstance(llm_trace_audit.get("coverage"), dict) else {}
        manifest.record(
            "llm_trace_audit",
            inputs=[LLM_TRACE_JSON, AI_DISCLOSURE_JSON, "00-research-plan.json", "01-literature.json", "02-ideas.json", "03-experiment-plan.json", "06-paper.md", "07-paper-review.json", REVISED_PAPER_MD],
            outputs=[LLM_TRACE_AUDIT_MD, LLM_TRACE_AUDIT_JSON],
            metrics={
                "status": llm_trace_audit.get("status"),
                "coverage_ratio": llm_coverage.get("coverage_ratio"),
                "blocking_issues": len(llm_trace_audit.get("blocking_issues", []) if isinstance(llm_trace_audit.get("blocking_issues"), list) else []),
                "warnings": len(llm_trace_audit.get("warnings", []) if isinstance(llm_trace_audit.get("warnings"), list) else []),
            },
        )
        run_economics = write_run_economics_audit_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "run_economics_audit_completed")
        run_economics_summary = run_economics.get("summary") if isinstance(run_economics.get("summary"), dict) else {}
        manifest.record(
            "run_economics_audit",
            inputs=[LLM_TRACE_JSON, "run-config.json"],
            outputs=[RUN_ECONOMICS_AUDIT_MD, RUN_ECONOMICS_AUDIT_JSON],
            metrics={
                "status": run_economics.get("status"),
                "input_tokens_estimated": run_economics_summary.get("input_tokens_estimated"),
                "output_tokens_estimated": run_economics_summary.get("output_tokens_estimated"),
                "estimated_cost_usd": run_economics_summary.get("estimated_cost_usd"),
            },
        )
        llm_runtime_contract = write_llm_runtime_contract_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "llm_runtime_contract_completed")
        manifest.record(
            "llm_runtime_contract",
            inputs=[LLM_TRACE_JSON, "run-config.json", LLM_TRACE_AUDIT_JSON, RUN_ECONOMICS_AUDIT_JSON, AI_DISCLOSURE_JSON],
            outputs=[LLM_RUNTIME_CONTRACT_MD, LLM_RUNTIME_CONTRACT_JSON],
            metrics={
                "status": llm_runtime_contract.get("status"),
                "blocking_issues": len(llm_runtime_contract.get("blocking_issues", []) if isinstance(llm_runtime_contract.get("blocking_issues"), list) else []),
                "manual_tasks": len(llm_runtime_contract.get("manual_tasks", []) if isinstance(llm_runtime_contract.get("manual_tasks"), list) else []),
            },
        )
        observability_audit = write_agent_observability_audit_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "agent_observability_audit_completed")
        manifest.record(
            "agent_observability_audit",
            inputs=["state.json", "run-manifest.json", LLM_TRACE_JSON, RUN_ECONOMICS_AUDIT_JSON, "run-config.json", APPROVAL_FILENAME, EXECUTION_APPROVAL_JSON, EXPERIMENT_RUNBOOK_JSON, "run-diagnostics.json", REPAIR_QUEUE_JSON],
            outputs=[AGENT_OBSERVABILITY_AUDIT_MD, AGENT_OBSERVABILITY_AUDIT_JSON],
            metrics={
                "status": observability_audit.get("status"),
                "blocking_issues": len(observability_audit.get("blocking_issues", []) if isinstance(observability_audit.get("blocking_issues"), list) else []),
                "manual_tasks": len(observability_audit.get("manual_tasks", []) if isinstance(observability_audit.get("manual_tasks"), list) else []),
            },
        )
        llm_observability_summary = write_llm_observability_summary_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "llm_observability_summary_completed")
        llm_calls = llm_observability_summary.get("llm_calls") if isinstance(llm_observability_summary.get("llm_calls"), dict) else {}
        manifest.record(
            "llm_observability_summary",
            inputs=[LLM_TRACE_JSON, LLM_TRACE_AUDIT_JSON, RUN_ECONOMICS_AUDIT_JSON, LLM_RUNTIME_CONTRACT_JSON, AGENT_OBSERVABILITY_AUDIT_JSON],
            outputs=[LLM_OBSERVABILITY_SUMMARY_MD, LLM_OBSERVABILITY_SUMMARY_JSON],
            metrics={
                "status": llm_observability_summary.get("status"),
                "total_calls": llm_calls.get("total"),
                "successful_calls": llm_calls.get("successful"),
                "blocking_issues": len(llm_observability_summary.get("blocking_issues", []) if isinstance(llm_observability_summary.get("blocking_issues"), list) else []),
            },
        )
        open_source_compliance = write_open_source_compliance_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "open_source_compliance_completed")
        manifest.record(
            "open_source_compliance",
            inputs=[
                OPEN_SOURCE_LESSONS_JSON,
                PRIOR_RUN_LESSONS_JSON,
                QUERY_EXECUTION_AUDIT_JSON,
                LITERATURE_SOURCE_HEALTH_JSON,
                LITERATURE_RERANK_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                APPROVAL_FILENAME,
                REVIEW_CONSTRAINT_COMPLIANCE_JSON,
                IDEA_EXPERIMENT_CONTRACT_JSON,
                EXECUTION_SAFETY_AUDIT_JSON,
                BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
                BENCHMARK_EVIDENCE_AUDIT_JSON,
                AI_DISCLOSURE_JSON,
                LLM_TRACE_AUDIT_JSON,
                RUN_ECONOMICS_AUDIT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
            ],
            outputs=[OPEN_SOURCE_COMPLIANCE_MD, OPEN_SOURCE_COMPLIANCE_JSON],
            metrics={
                "status": open_source_compliance.get("status"),
                "score": open_source_compliance.get("score"),
                "checked_lessons": open_source_compliance.get("checked_lessons"),
                "blocking_issues": len(open_source_compliance.get("blocking_issues", []) if isinstance(open_source_compliance.get("blocking_issues"), list) else []),
                "manual_tasks": len(open_source_compliance.get("manual_tasks", []) if isinstance(open_source_compliance.get("manual_tasks"), list) else []),
            },
        )
        human_gate_audit = write_human_gate_audit_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "human_gate_audit_completed")
        manifest.record(
            "human_gate_audit",
            inputs=[APPROVAL_FILENAME, EXECUTION_APPROVAL_JSON, "state.json", EXPERIMENT_RUNBOOK_JSON, "02-ideas.json", "03-experiment-plan.json", "04-results.json"],
            outputs=[HUMAN_GATE_AUDIT_MD, HUMAN_GATE_AUDIT_JSON],
            metrics={
                "status": human_gate_audit.get("status"),
                "blocking_issues": len(human_gate_audit.get("blocking_issues", []) if isinstance(human_gate_audit.get("blocking_issues"), list) else []),
                "manual_tasks": len(human_gate_audit.get("manual_tasks", []) if isinstance(human_gate_audit.get("manual_tasks"), list) else []),
            },
        )
        repair_queue = write_repair_queue_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "repair_queue_completed")
        manifest.record(
            "repair_queue",
            inputs=[
                LITERATURE_METADATA_AUDIT_JSON,
                QUERY_EXECUTION_AUDIT_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                LITERATURE_RESCUE_PLAN_JSON,
                SEED_PAPER_INTAKE_JSON,
                CITATION_AUDIT_JSON,
                IDEA_AUDIT_JSON,
                REVIEW_CONSTRAINT_COMPLIANCE_JSON,
                EXPERIMENT_AUDIT_JSON,
                IDEA_EXPERIMENT_CONTRACT_JSON,
                EXECUTION_SAFETY_AUDIT_JSON,
                RESULT_VALIDATION_JSON,
                FAILURE_ANALYSIS_JSON,
                BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
                BENCHMARK_EVIDENCE_AUDIT_JSON,
                EXPERIMENT_DECISION_JSON,
                HYPOTHESIS_OUTCOME_JSON,
                CLAIM_BOUNDARY_PREFLIGHT_JSON,
                PAPER_REVIEW_CALIBRATION_JSON,
                REVISION_RESPONSE_AUDIT_JSON,
                CLAIM_TRACEABILITY_JSON,
                CITATION_GROUNDING_JSON,
                CITATION_COVERAGE_JSON,
                RESULTS_PRESENTATION_JSON,
                CLAIM_CONSISTENCY_JSON,
                RELEASE_METADATA_JSON,
                CODE_DATA_AVAILABILITY_JSON,
                SUBMISSION_CHECK_JSON,
                FINAL_READINESS_JSON,
                SUBMISSION_PACKAGE_JSON,
                ITERATION_PLAN_JSON,
                LLM_TRACE_AUDIT_JSON,
                RUN_ECONOMICS_AUDIT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
                OPEN_SOURCE_COMPLIANCE_JSON,
                HUMAN_GATE_AUDIT_JSON,
            ],
            outputs=[REPAIR_QUEUE_MD, REPAIR_QUEUE_JSON],
            metrics={
                "status": repair_queue.status,
                "items": len(repair_queue.items),
                "blocking_issues": len(repair_queue.blocking_issues),
                "manual_tasks": len(repair_queue.manual_tasks),
            },
        )
        repair_resolution = write_repair_resolution_audit_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "repair_resolution_audit_completed")
        manifest.record(
            "repair_resolution_audit",
            inputs=[REPAIR_RESUME_PLAN_JSON, REPAIR_QUEUE_JSON],
            outputs=[REPAIR_RESOLUTION_AUDIT_MD, REPAIR_RESOLUTION_AUDIT_JSON],
            metrics={
                "status": repair_resolution.get("status"),
                "resolution_score": repair_resolution.get("resolution_score"),
                "remaining_items": len(repair_resolution.get("remaining_items", []) if isinstance(repair_resolution.get("remaining_items"), list) else []),
                "new_items": len(repair_resolution.get("new_items", []) if isinstance(repair_resolution.get("new_items"), list) else []),
            },
        )
        stage_contract = write_agent_stage_contract_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "agent_stage_contract_completed")
        manifest.record(
            "agent_stage_contract",
            inputs=[
                OPEN_SOURCE_LESSONS_JSON,
                "00-research-plan.json",
                "01-context.json",
                CITATION_AUDIT_JSON,
                QUERY_EXECUTION_AUDIT_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                APPROVAL_FILENAME,
                IDEA_AUDIT_JSON,
                EXPLORATION_MAP_JSON,
                EXPERIMENT_AUDIT_JSON,
                EXECUTION_SAFETY_AUDIT_JSON,
                EXPERIMENT_RUNBOOK_JSON,
                RESULT_VALIDATION_JSON,
                BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
                BENCHMARK_EVIDENCE_AUDIT_JSON,
                HYPOTHESIS_OUTCOME_JSON,
                CLAIM_BOUNDARY_PREFLIGHT_JSON,
                REVISION_RESPONSE_AUDIT_JSON,
                CLAIM_TRACEABILITY_JSON,
                CITATION_GROUNDING_JSON,
                CITATION_COVERAGE_JSON,
                RESULTS_PRESENTATION_JSON,
                CLAIM_CONSISTENCY_JSON,
                CODE_DATA_AVAILABILITY_JSON,
                SUBMISSION_PACKAGE_JSON,
                REPAIR_QUEUE_JSON,
                REPAIR_RESOLUTION_AUDIT_JSON,
                RUN_ECONOMICS_AUDIT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
                OPEN_SOURCE_COMPLIANCE_JSON,
            ],
            outputs=[AGENT_STAGE_CONTRACT_MD, AGENT_STAGE_CONTRACT_JSON],
            metrics={
                "status": stage_contract.get("status"),
                "score": stage_contract.get("score"),
                "blocking_issues": len(stage_contract.get("blocking_issues", []) if isinstance(stage_contract.get("blocking_issues"), list) else []),
                "manual_tasks": len(stage_contract.get("manual_tasks", []) if isinstance(stage_contract.get("manual_tasks"), list) else []),
            },
        )
        trajectory = write_agent_trajectory_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "agent_trajectory_completed")
        trajectory_summary = trajectory.get("summary") if isinstance(trajectory.get("summary"), dict) else {}
        manifest.record(
            "agent_trajectory",
            inputs=[
                "state.json",
                "run-manifest.json",
                PREFLIGHT_JSON,
                HUMAN_BRIEF_JSON,
                PRIOR_RUN_LESSONS_JSON,
                OPEN_SOURCE_LESSONS_JSON,
                QUERY_EXECUTION_AUDIT_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                APPROVAL_FILENAME,
                IDEA_AUDIT_JSON,
                EXPERIMENT_MANAGER_JSON,
                REVIEW_CONSTRAINT_COMPLIANCE_JSON,
                EXPERIMENT_AUDIT_JSON,
                IDEA_EXPERIMENT_CONTRACT_JSON,
                RESULT_VALIDATION_JSON,
                BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
                CLAIM_BOUNDARY_PREFLIGHT_JSON,
                REVISION_RESPONSE_AUDIT_JSON,
                FINAL_READINESS_JSON,
                REPAIR_QUEUE_JSON,
                AGENT_STAGE_CONTRACT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
                OPEN_SOURCE_COMPLIANCE_JSON,
            ],
            outputs=[AGENT_TRAJECTORY_MD, AGENT_TRAJECTORY_JSON],
            metrics={
                "status": trajectory.get("status"),
                "events": trajectory_summary.get("event_count"),
                "blocking_issues": trajectory_summary.get("blocking_issues"),
                "manual_tasks": trajectory_summary.get("manual_tasks"),
            },
        )
        submission_package = write_submission_package_artifacts(topic, out_dir)
        manifest.record(
            "submission_package_refresh",
            inputs=[SUBMISSION_PACKAGE_JSON, REPAIR_QUEUE_JSON, REPAIR_QUEUE_MD, AGENT_STAGE_CONTRACT_JSON, AGENT_TRAJECTORY_JSON, LLM_TRACE_AUDIT_JSON, RUN_ECONOMICS_AUDIT_JSON, AGENT_OBSERVABILITY_AUDIT_JSON, OPEN_SOURCE_COMPLIANCE_JSON],
            outputs=[SUBMISSION_PACKAGE_MD, SUBMISSION_PACKAGE_JSON, SUBMISSION_PACKAGE_ZIP],
            metrics={
                "status": submission_package.status,
                "files": len(submission_package.files),
                "blocking_issues": len(submission_package.blocking_issues),
                "manual_tasks": len(submission_package.manual_tasks),
            },
        )
        scorecard = write_research_scorecard_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "scorecard_completed")
        manifest.record(
            "research_scorecard",
            inputs=[
                "01-literature-quality.json",
                QUERY_EXECUTION_AUDIT_JSON,
                LITERATURE_EVIDENCE_MIX_JSON,
                EXPLORATION_MAP_JSON,
                "04-statistics.json",
                CLAIM_BOUNDARY_PREFLIGHT_JSON,
                BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
                REVISION_RESPONSE_AUDIT_JSON,
                FINAL_READINESS_JSON,
                CITATION_COVERAGE_JSON,
                RESULTS_PRESENTATION_JSON,
                CLAIM_CONSISTENCY_JSON,
                CODE_DATA_AVAILABILITY_JSON,
                SUBMISSION_CHECK_JSON,
                SUBMISSION_PACKAGE_JSON,
                ITERATION_PLAN_JSON,
                REPAIR_QUEUE_JSON,
                AGENT_STAGE_CONTRACT_JSON,
                AGENT_TRAJECTORY_JSON,
                LLM_TRACE_AUDIT_JSON,
                RUN_ECONOMICS_AUDIT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
                OPEN_SOURCE_COMPLIANCE_JSON,
            ],
            outputs=[RESEARCH_SCORECARD_MD, RESEARCH_SCORECARD_JSON],
            metrics={
                "status": scorecard.status,
                "overall_score": scorecard.overall_score,
                "blocking_issues": len(scorecard.blocking_issues),
                "manual_tasks": len(scorecard.manual_tasks),
            },
        )
        integrity = write_run_integrity_audit_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "run_integrity_audit_completed")
        manifest.record(
            "run_integrity_audit",
            inputs=[
                "state.json",
                APPROVAL_FILENAME,
                "run-manifest.json",
                "run-llm-ledger.json",
                LLM_TRACE_AUDIT_JSON,
                RUN_ECONOMICS_AUDIT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
                SUBMISSION_PACKAGE_JSON,
                RESEARCH_SCORECARD_JSON,
                AGENT_STAGE_CONTRACT_JSON,
            ],
            outputs=[RUN_INTEGRITY_AUDIT_MD, RUN_INTEGRITY_AUDIT_JSON],
            metrics={
                "status": integrity.get("status"),
                "blocking_issues": len(integrity.get("blocking_issues", []) if isinstance(integrity.get("blocking_issues"), list) else []),
                "warnings": len(integrity.get("warnings", []) if isinstance(integrity.get("warnings"), list) else []),
            },
        )
        scorecard = write_research_scorecard_artifacts(topic, out_dir)
        manifest.record(
            "research_scorecard_integrity_refresh",
            inputs=[
                RESEARCH_SCORECARD_JSON,
                RUN_INTEGRITY_AUDIT_JSON,
                AGENT_STAGE_CONTRACT_JSON,
                REPAIR_QUEUE_JSON,
                LLM_TRACE_AUDIT_JSON,
                RUN_ECONOMICS_AUDIT_JSON,
                AGENT_OBSERVABILITY_AUDIT_JSON,
                OPEN_SOURCE_COMPLIANCE_JSON,
            ],
            outputs=[RESEARCH_SCORECARD_MD, RESEARCH_SCORECARD_JSON],
            metrics={
                "status": scorecard.status,
                "overall_score": scorecard.overall_score,
                "blocking_issues": len(scorecard.blocking_issues),
                "manual_tasks": len(scorecard.manual_tasks),
                "run_integrity_status": integrity.get("status"),
            },
        )
        handoff = write_final_handoff_artifacts(topic, out_dir)
        _write_state(out_dir, topic, "final_handoff_completed")
        manifest.record(
            "final_handoff",
            inputs=[SUBMISSION_PACKAGE_JSON, SUBMISSION_PACKAGE_ZIP, RESEARCH_SCORECARD_JSON, RUN_INTEGRITY_AUDIT_JSON],
            outputs=[FINAL_HANDOFF_MD, FINAL_HANDOFF_JSON],
            metrics={
                "status": handoff.get("status"),
                "blocking_issues": len(handoff.get("blocking_issues", []) if isinstance(handoff.get("blocking_issues"), list) else []),
                "manual_tasks": len(handoff.get("manual_tasks", []) if isinstance(handoff.get("manual_tasks"), list) else []),
                "package_has_integrity_audit": handoff.get("package_has_integrity_audit") is True,
            },
        )

    def _node_completed():
        _write_state(out_dir, topic, "completed")
        manifest.record("completed", inputs=[FINAL_HANDOFF_JSON, RUN_INTEGRITY_AUDIT_JSON, AGENT_STAGE_CONTRACT_JSON], outputs=["state.json"], status="completed")
        trajectory = write_agent_trajectory_artifacts(topic, out_dir)
        trajectory_summary = trajectory.get("summary") if isinstance(trajectory.get("summary"), dict) else {}
        manifest.record(
            "agent_trajectory_final_refresh",
            inputs=["state.json", "run-manifest.json", FINAL_HANDOFF_JSON, RUN_INTEGRITY_AUDIT_JSON, RESEARCH_SCORECARD_JSON],
            outputs=[AGENT_TRAJECTORY_MD, AGENT_TRAJECTORY_JSON],
            metrics={
                "status": trajectory.get("status"),
                "events": trajectory_summary.get("event_count"),
                "last_event": trajectory_summary.get("last_event"),
                "blocking_issues": trajectory_summary.get("blocking_issues"),
                "manual_tasks": trajectory_summary.get("manual_tasks"),
            },
        )

    engine = WorkflowEngine([node.node_id for node in WORKFLOW_NODES])
    try:
        engine.run(out_dir, start="ideation", from_node="review_gate", handlers={
            "ideation": _node_ideation,
            "experiment_plan": _node_experiment_plan,
            "execution_gate": _node_execution_gate,
            "experiments": _node_experiments,
            "analysis": _node_analysis,
            "paper_writing": _node_paper_writing,
            "paper_review": _node_paper_review,
            "paper_revision": _node_paper_revision,
            "finalization": _node_finalization,
            "completed": _node_completed,
        }, facts=lambda: {
            "execution_requires_approval": config.execution.mode in {"local", "benchmark"},
            "writing_blocked": bool(experiment_decision and experiment_decision.get("downstream_writing_allowed") is False),
            # T07/A15：负结果（pivot_or_refine）按契约 §1.4 为 proceed——正常完成
            # 负结果报告后终止本轮（decision_states.stop_after_report=true），
            # 不自动开新实验轮；修订轮保留用于收敛结论边界措辞，轮次受
            # run_budget 冻结上限约束（A16）。真正的阻断路由走
            # writing_blocked → awaiting_experiment_repair。
            "revision_required": True,
            "recheck_required": False,
        }, terminal_nodes={"completed"},
           before_node=lambda node: begin_workflow_node(out_dir, topic, node),
           on_edge=lambda source, target: manifest.record("workflow_dispatch", inputs=[], outputs=[], metrics={"from": source, "to": target}))
    except RunBudgetExhausted as exc:
        # T07/A16：预算耗尽 → 停止并保留已有证据；状态可被人工识别。
        _write_state(out_dir, topic, "stopped_budget_exhausted")
        manifest.record(
            "budget_exhausted",
            inputs=["04-run-budget.json"],
            outputs=["state.json"],
            status="blocked",
            notes=[str(exc)[:280]],
        )
        raise


def _write_experiment_repair_gate(
    topic: str,
    out_dir: Path,
    experiment_decision: dict[str, Any],
    claim_preflight: dict[str, Any],
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
) -> dict[str, Any]:
    blocking = _unique_strings(
        [
            *(
                claim_preflight.get("blocking_issues", [])
                if isinstance(claim_preflight.get("blocking_issues"), list)
                else []
            ),
            *(
                result_validation.get("blocking_issues", [])
                if isinstance(result_validation.get("blocking_issues"), list)
                else []
            ),
            *(
                failure_analysis.get("blocking_issues", [])
                if isinstance(failure_analysis.get("blocking_issues"), list)
                else []
            ),
        ]
    )
    actions = _unique_strings(
        [
            *(
                experiment_decision.get("next_actions", [])
                if isinstance(experiment_decision.get("next_actions"), list)
                else []
            ),
            *(
                claim_preflight.get("required_actions", [])
                if isinstance(claim_preflight.get("required_actions"), list)
                else []
            ),
        ]
    )
    report = {
        "schema_version": 1,
        "topic": topic,
        "status": "blocked",
        "stage": "awaiting_experiment_repair",
        "document_type": "experiment_repair_report_not_a_paper",
        "paper_llm_called": False,
        "decision": experiment_decision.get("decision"),
        "writing_mode": claim_preflight.get("writing_mode"),
        "blocking_issues": blocking,
        "required_actions": actions,
    }
    write_json(out_dir / EXPERIMENT_REPAIR_REPORT_JSON, report)
    lines = [
        f"# 实验修复报告（非论文）：{topic}",
        "",
        "当前实验 gate 禁止进入论文写作。本文件由确定性规则生成，未调用论文或审稿 LLM。",
        "",
        f"- 决策：{report['decision'] or '-'}",
        f"- 写作模式：{report['writing_mode'] or '-'}",
        "- 状态：awaiting_experiment_repair",
        "",
        "## 阻断问题",
    ]
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 实验后决策禁止继续写作。")
    lines.extend(["", "## 修复动作"])
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- [ ] 修复实验验证与失败分析后重跑。")
    write_text(out_dir / EXPERIMENT_REPAIR_REPORT_MD, "\n".join(lines))
    return report


def default_out_dir(topic: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", topic).strip("-").lower()
    if not slug:
        slug = "research-run"
    if len(slug) > 48:
        slug = slug[:48].rstrip("-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path("runs") / f"{slug}-{stamp}"


def request_review_approval(out_dir: Path, topic: str, context: LiteratureContext) -> dict[str, Any]:
    policy = _approval_policy(context.review_gate.status, context.review_gate.warnings)
    binding = _review_approval_binding(out_dir, topic)
    approval = {
        "schema_version": 2,
        "topic": topic,
        "approved": False,
        "revision_requested": False,
        "requested_at": _utc_now(),
        "approved_at": None,
        "revision_requested_at": None,
        "reviewer": None,
        "notes": "",
        "history": [],
        "stage": "awaiting_review_approval",
        "gate_status": context.review_gate.status,
        "warnings": context.review_gate.warnings,
        "required_actions": context.review_gate.required_actions,
        "approval_policy": policy,
        "approval_binding": binding,
        "approval_binding_sha256": _digest_payload(binding),
        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
    }
    write_json(out_dir / APPROVAL_FILENAME, approval)
    return approval


def refresh_pending_review_approval(out_dir: Path, context: LiteratureContext) -> dict[str, Any] | None:
    approval_path = out_dir / APPROVAL_FILENAME
    if not approval_path.exists():
        return None
    approval = read_json(approval_path)
    if not isinstance(approval, dict):
        return None
    topic = str(approval.get("topic") or "")
    binding = _review_approval_binding(out_dir, topic)
    binding_matches = bool(
        approval.get("approval_binding_sha256")
        and approval.get("approval_binding_sha256") == _digest_payload(binding)
        and approval.get("approval_binding") == binding
    )
    if approval.get("approved") is True and binding_matches:
        return approval
    if approval.get("approved") is True:
        approval["approved"] = False
        approval["approved_at"] = None
        approval["stage"] = "awaiting_review_approval"
        approval["stale_previous_approval"] = True
    approval.update(
        {
            "gate_status": context.review_gate.status,
            "warnings": context.review_gate.warnings,
            "required_actions": context.review_gate.required_actions,
            "approval_policy": _approval_policy(context.review_gate.status, context.review_gate.warnings),
            "approval_binding": binding,
            "approval_binding_sha256": _digest_payload(binding),
            "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
        }
    )
    write_json(approval_path, approval)
    return approval


def refresh_review_revision_repair_approval(out_dir: Path, context: LiteratureContext) -> dict[str, Any]:
    approval_path = out_dir / APPROVAL_FILENAME
    if not approval_path.exists():
        raise FileNotFoundError(f"No {APPROVAL_FILENAME} found in {out_dir}")
    approval = read_json(approval_path)
    if not isinstance(approval, dict):
        approval = {}
    history = _approval_history(approval)
    repaired_at = _utc_now()
    policy = _approval_policy(context.review_gate.status, context.review_gate.warnings)
    note_text = str(approval.get("notes") or "")
    approved = False
    history.append(
        {
            "action": "revision_repaired",
            "reviewer": str(approval.get("reviewer") or "system"),
            "at": repaired_at,
            "notes": "退回后已重新生成文献池、seed intake、context 和 review gate。",
        }
    )
    approval.update(
        {
            "approved": approved,
            "revision_requested": False,
            "revision_repaired_at": repaired_at,
            "revision_repair_revision_requested_at": _latest_revision_requested_at(approval),
            "stage": "review_approved" if approved else "awaiting_review_approval",
            "gate_status": context.review_gate.status,
            "warnings": context.review_gate.warnings,
            "required_actions": context.review_gate.required_actions,
            "approval_policy": policy,
            "approval_binding": _review_approval_binding(out_dir, str(approval.get("topic") or "")),
            "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
            "history": history,
            "revision_repair": {
                "status": "approved" if approved else "reapproval_required",
                "gate_status": context.review_gate.status,
                "warnings": context.review_gate.warnings,
                "required_actions": context.review_gate.required_actions,
            },
        }
    )
    if not approved:
        approval["approved_at"] = None
    approval["approval_binding_sha256"] = _digest_payload(approval["approval_binding"])
    write_json(approval_path, approval)
    return approval


def approve_review_gate(out_dir: Path, reviewer: str = "manual", notes: str = "") -> dict[str, Any]:
    approval_path = out_dir / APPROVAL_FILENAME
    if not approval_path.exists():
        raise FileNotFoundError(f"No {APPROVAL_FILENAME} found in {out_dir}")
    approval = read_json(approval_path)
    if not isinstance(approval, dict):
        approval = {}
    current_binding = _review_approval_binding(out_dir, str(approval.get("topic") or ""))
    stored_binding = approval.get("approval_binding") if isinstance(approval.get("approval_binding"), dict) else {}
    stored_binding_hash = str(approval.get("approval_binding_sha256") or "")
    has_bound_review_inputs = any(
        current_binding.get(key)
        for key in ["context_sha256", "review_gate_sha256", "literature_gate_decision_sha256", "run_config_sha256"]
    )
    binding_stale = bool(stored_binding) and (
        stored_binding != current_binding or stored_binding_hash != _digest_payload(current_binding)
    )
    if binding_stale or (not stored_binding and has_bound_review_inputs):
        history = _approval_history(approval)
        history.append(
            {
                "action": "approval_request_refreshed",
                "reviewer": reviewer,
                "at": _utc_now(),
                "notes": "Review inputs changed after the approval request; inspect the refreshed request before approving.",
            }
        )
        approval.update(
            {
                "approved": False,
                "approved_at": None,
                "stage": "awaiting_review_approval",
                "stale_previous_approval": True,
                "approval_binding": current_binding,
                "approval_binding_sha256": _digest_payload(current_binding),
                "approval_policy": {
                    "notes_required": True,
                    "gate_status": str(approval.get("gate_status") or "unknown"),
                    "warning_count": len(approval.get("warnings", []) if isinstance(approval.get("warnings"), list) else []),
                    "reason": "Review inputs changed after the request; approval notes must confirm the refreshed artifacts were reviewed.",
                },
                "history": history,
            }
        )
        write_json(approval_path, approval)
        raise RuntimeError("Review inputs changed after approval was requested; review the refreshed gate and approve again.")
    note_text = notes or str(approval.get("notes") or "")
    policy = _approval_policy_from_record(approval)
    if policy.get("notes_required") and not _substantive_approval_notes(note_text):
        raise RuntimeError(str(policy.get("reason") or "This review gate requires approval notes before continuing."))
    history = _approval_history(approval)
    history.append({"action": "approved", "reviewer": reviewer, "at": _utc_now(), "notes": notes})
    approval.update(
        {
            "approved": True,
            "revision_requested": False,
            "approved_at": _utc_now(),
            "reviewer": reviewer,
            "notes": note_text,
            "stage": "review_approved",
            "approval_policy": policy,
            "approval_binding": current_binding,
            "approval_binding_sha256": _digest_payload(current_binding),
            "history": history,
        }
    )
    revision_repair = approval.get("revision_repair")
    if isinstance(revision_repair, dict) and revision_repair.get("status") == "reapproval_required":
        approval["revision_repair"] = {**revision_repair, "status": "approved", "approved_at": approval["approved_at"]}
    write_json(approval_path, approval)
    return approval


def request_review_revision(out_dir: Path, reviewer: str = "manual", notes: str = "") -> dict[str, Any]:
    approval_path = out_dir / APPROVAL_FILENAME
    if not approval_path.exists():
        raise FileNotFoundError(f"No {APPROVAL_FILENAME} found in {out_dir}")
    approval = read_json(approval_path)
    if not isinstance(approval, dict):
        approval = {}
    history = _approval_history(approval)
    history.append({"action": "revision_requested", "reviewer": reviewer, "at": _utc_now(), "notes": notes})
    approval.update(
        {
            "approved": False,
            "revision_requested": True,
            "revision_requested_at": _utc_now(),
            "reviewer": reviewer,
            "notes": notes,
            "stage": "review_revision_requested",
            "history": history,
        }
    )
    write_json(approval_path, approval)
    write_review_revision_plan_artifacts(out_dir, approval)
    return approval


def request_execution_approval(out_dir: Path, topic: str, plan: ExperimentPlan, safety_report: dict[str, Any], execution_mode: str) -> dict[str, Any]:
    approval_path = out_dir / EXECUTION_APPROVAL_JSON
    existing = _read_dict(approval_path)
    plan_hash = _file_sha256(out_dir / "03-experiment-plan.json")
    safety_hash = _file_sha256(out_dir / EXECUTION_SAFETY_AUDIT_JSON)
    binding_hash = str(safety_report.get("execution_binding_sha256") or "")
    plan_changed = bool(existing) and str(existing.get("plan_sha256") or "") != plan_hash
    safety_changed = bool(existing) and str(existing.get("safety_sha256") or "") != safety_hash
    current_binding = safety_report.get("execution_binding") if isinstance(safety_report.get("execution_binding"), dict) else {}
    existing_binding = existing.get("execution_binding") if isinstance(existing.get("execution_binding"), dict) else {}
    binding_changed = bool(existing) and (
        not current_binding
        or existing_binding != current_binding
        or str(existing.get("execution_binding_sha256") or "") != binding_hash
        or binding_hash != _digest_payload(current_binding)
        or not execution_source_binding_matches(current_binding)
    )
    approved = existing.get("approved") is True and not plan_changed and not safety_changed and not binding_changed
    history = _approval_history(existing)
    approval = {
        "schema_version": 1,
        "topic": topic,
        "approved": approved,
        "requested_at": existing.get("requested_at") or _utc_now(),
        "approved_at": existing.get("approved_at") if approved else None,
        "reviewer": existing.get("reviewer") if approved else None,
        "notes": existing.get("notes") if approved else "",
        "history": history,
        "stage": "execution_approved" if approved else "awaiting_execution_approval",
        "execution_mode": execution_mode,
        "idea_title": plan.idea_title,
        "commands": safety_report.get("approved_commands")
        if isinstance(safety_report.get("approved_commands"), list)
        else [
            {"name": command.name, "command": command.command, "expected_artifacts": command.expected_artifacts}
            for command in plan.commands
        ],
        "safety_status": safety_report.get("status"),
        "safety_blocking_issues": safety_report.get("blocking_issues") if isinstance(safety_report.get("blocking_issues"), list) else [],
        "safety_warnings": safety_report.get("warnings") if isinstance(safety_report.get("warnings"), list) else [],
        "plan_sha256": plan_hash,
        "safety_sha256": safety_hash,
        "execution_binding": current_binding,
        "execution_binding_sha256": binding_hash,
        "approval_policy": {
            "notes_required": True,
            "reason": "local/benchmark execution runs commands on this machine; approval notes must confirm the plan, command scope, and safety audit were reviewed.",
        },
        "blocks": ["experiment_execution"],
    }
    if plan_changed or safety_changed or binding_changed:
        approval["stale_previous_approval"] = {
            "plan_changed": plan_changed,
            "safety_changed": safety_changed,
            "binding_changed": binding_changed,
            "previous_plan_sha256": existing.get("plan_sha256"),
            "previous_safety_sha256": existing.get("safety_sha256"),
        }
    write_json(approval_path, approval)
    write_text(out_dir / EXECUTION_APPROVAL_MD, render_execution_approval_markdown(approval))
    return approval


def approve_execution_gate(out_dir: Path, reviewer: str = "manual", notes: str = "") -> dict[str, Any]:
    approval_path = out_dir / EXECUTION_APPROVAL_JSON
    if not approval_path.exists():
        raise FileNotFoundError(f"No {EXECUTION_APPROVAL_JSON} found in {out_dir}")
    approval = read_json(approval_path)
    if not isinstance(approval, dict):
        approval = {}
    if not _execution_approval_context_matches(out_dir, approval):
        approval.update(
            {
                "approved": False,
                "approved_at": None,
                "stage": "awaiting_execution_approval",
                "stale_previous_approval": {
                    "approval_attempt_rejected": True,
                    "reason": "plan, safety audit, execution binding, or benchmark source changed",
                    "at": _utc_now(),
                },
            }
        )
        write_json(approval_path, approval)
        write_text(out_dir / EXECUTION_APPROVAL_MD, render_execution_approval_markdown(approval))
        raise RuntimeError("Execution inputs changed after approval was requested; regenerate the safety audit before approving.")
    note_text = notes or str(approval.get("notes") or "")
    if not _substantive_approval_notes(note_text):
        raise RuntimeError("Execution approval requires notes confirming the command plan and safety audit were reviewed.")
    history = _approval_history(approval)
    history.append({"action": "execution_approved", "reviewer": reviewer, "at": _utc_now(), "notes": notes})
    approval.update(
        {
            "approved": True,
            "approved_at": _utc_now(),
            "reviewer": reviewer,
            "notes": note_text,
            "stage": "execution_approved",
            "history": history,
        }
    )
    write_json(approval_path, approval)
    write_text(out_dir / EXECUTION_APPROVAL_MD, render_execution_approval_markdown(approval))
    return approval


def render_execution_approval_markdown(approval: dict[str, Any]) -> str:
    lines = [
        f"# 实验执行人工确认：{approval.get('topic') or ''}",
        "",
        f"- 状态：{'已批准' if approval.get('approved') is True else '待批准'}",
        f"- 执行模式：{approval.get('execution_mode') or '-'}",
        f"- Safety audit：{approval.get('safety_status') or '-'}",
        f"- 审核人：{approval.get('reviewer') or '未记录'}",
        f"- 审核意见：{approval.get('notes') or '无'}",
        "",
        "## 阻断范围",
        "- experiment_execution",
        "",
    ]
    for key, title in [("safety_blocking_issues", "Safety 阻断"), ("safety_warnings", "Safety 警告")]:
        values = approval.get(key) if isinstance(approval.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(["## 待执行命令", "| 名称 | 命令 | 预期产物 |", "| --- | --- | --- |"])
    commands = approval.get("commands") if isinstance(approval.get("commands"), list) else []
    if not commands:
        lines.append("| 无 | - | - |")
    for command in commands:
        if not isinstance(command, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(command.get("name") or "")),
                    _cell(" ".join(str(item) for item in command.get("command", []) if str(item))),
                    _cell(", ".join(str(item) for item in command.get("expected_artifacts", []) if str(item)) or "-"),
                ]
            )
            + " |"
        )
    stale = approval.get("stale_previous_approval") if isinstance(approval.get("stale_previous_approval"), dict) else {}
    if stale:
        lines.extend(
            [
                "",
                "## 旧批准失效",
                f"- plan_changed：{stale.get('plan_changed')}",
                f"- safety_changed：{stale.get('safety_changed')}",
            ]
        )
    return "\n".join(lines)


def write_review_feedback_artifacts(out_dir: Path, topic: str) -> dict[str, Any]:
    approval_path = out_dir / APPROVAL_FILENAME
    approval: dict[str, Any] = {}
    if approval_path.exists():
        try:
            loaded = read_json(approval_path)
            approval = loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, OSError):
            approval = {}

    history = _approval_history(approval)
    current_notes = str(approval.get("notes") or "").strip()
    current_reviewer = str(approval.get("reviewer") or "").strip()
    items: list[dict[str, str]] = []
    text_lines: list[str] = []

    state_label = "approved" if approval.get("approved") is True else "revision_requested" if approval.get("revision_requested") is True else "pending"
    text_lines.append(f"审核状态：{state_label}")
    if current_reviewer:
        text_lines.append(f"当前审核人：{current_reviewer}")
    if current_notes:
        text_lines.append(f"当前审核意见：{current_notes}")

    for index, event in enumerate(history, start=1):
        action = str(event.get("action") or "").strip()
        reviewer = str(event.get("reviewer") or "").strip()
        at = str(event.get("at") or "").strip()
        notes = str(event.get("notes") or "").strip()
        item = {
            "index": str(index),
            "action": action,
            "reviewer": reviewer,
            "at": at,
            "notes": notes,
        }
        items.append(item)
        label = f"{index}. {action or 'review'}"
        metadata = "，".join(value for value in [reviewer, at] if value)
        if metadata:
            label = f"{label}（{metadata}）"
        text_lines.append(f"{label}：{notes}" if notes else label)

    feedback = {
        "topic": topic,
        "approved": approval.get("approved") is True,
        "revision_requested": approval.get("revision_requested") is True,
        "reviewer": current_reviewer,
        "notes": current_notes,
        "items": items,
        "text": "\n".join(line for line in text_lines if line.strip()).strip(),
    }
    write_json(out_dir / REVIEW_FEEDBACK_JSON, feedback)
    write_text(out_dir / REVIEW_FEEDBACK_MD, render_review_feedback_markdown(feedback))
    return feedback


def render_review_feedback_markdown(feedback: dict[str, Any]) -> str:
    lines = [
        f"# 审核反馈：{feedback.get('topic') or '未命名课题'}",
        "",
        f"- 状态：{'已批准' if feedback.get('approved') is True else '已退回' if feedback.get('revision_requested') is True else '待审核'}",
        f"- 审核人：{feedback.get('reviewer') or '未记录'}",
        f"- 当前意见：{feedback.get('notes') or '无'}",
        "",
        "## 历史记录",
    ]
    items = feedback.get("items")
    if not isinstance(items, list) or not items:
        lines.append("- 无历史审核意见")
    else:
        for item in items:
            if not isinstance(item, dict):
                continue
            action = item.get("action") or "review"
            reviewer = item.get("reviewer") or "unknown"
            at = item.get("at") or "unknown time"
            notes = item.get("notes") or "无备注"
            lines.append(f"- {action}｜{reviewer}｜{at}：{notes}")
    text = str(feedback.get("text") or "").strip()
    lines.extend(["", "## 供 Agent 使用的约束文本", text or "无额外人工约束"])
    return "\n".join(lines)


def write_review_constraints_artifacts(out_dir: Path, topic: str, feedback: dict[str, Any]) -> dict[str, Any]:
    report = build_review_constraints(topic, feedback)
    write_json(out_dir / REVIEW_CONSTRAINTS_JSON, report)
    write_text(out_dir / REVIEW_CONSTRAINTS_MD, render_review_constraints_markdown(report))
    return report


def _combined_review_feedback_text(feedback: dict[str, Any], constraints: dict[str, Any], prior_lessons_text: str = "") -> str:
    parts = [constraints_agent_text(constraints), str(feedback.get("text") or "").strip(), prior_lessons_text.strip()]
    return "\n\n".join(part for part in parts if part)


def _planning_context(*texts: str) -> str:
    return "\n\n".join(text.strip() for text in texts if text and text.strip())


def _load_or_write_human_brief(topic: str, config: AgentConfig, out_dir: Path, manifest: RunManifestRecorder | None = None) -> dict[str, Any]:
    path = out_dir / HUMAN_BRIEF_JSON
    if path.exists():
        report = load_human_brief(path)
        if report is None:
            report = write_human_brief_artifacts(topic, config.human, out_dir)
        elif not (out_dir / HUMAN_BRIEF_MD).exists():
            write_text(out_dir / HUMAN_BRIEF_MD, render_human_brief_markdown(report))
        if "agent_prompt_text" not in report:
            report["agent_prompt_text"] = human_brief_agent_text(report)
        if manifest is not None:
            manifest.record(
                "human_brief_checkpoint",
                inputs=[HUMAN_BRIEF_JSON],
                outputs=[],
                notes=["reused existing human brief"],
                metrics={
                    "status": report.get("status"),
                    "constraints": len(report.get("constraints", []) if isinstance(report.get("constraints"), list) else []),
                    "success_criteria": len(report.get("success_criteria", []) if isinstance(report.get("success_criteria"), list) else []),
                    "resource_limits": len(report.get("resource_limits", []) if isinstance(report.get("resource_limits"), list) else []),
                },
            )
        return report
    report = write_human_brief_artifacts(topic, config.human, out_dir)
    if manifest is not None:
        manifest.record(
            "human_brief",
            inputs=["run-config.json"],
            outputs=[HUMAN_BRIEF_JSON, HUMAN_BRIEF_MD],
            metrics={
                "status": report.get("status"),
                "constraints": len(report.get("constraints", []) if isinstance(report.get("constraints"), list) else []),
                "success_criteria": len(report.get("success_criteria", []) if isinstance(report.get("success_criteria"), list) else []),
                "resource_limits": len(report.get("resource_limits", []) if isinstance(report.get("resource_limits"), list) else []),
            },
        )
    return report


def _load_or_write_prior_run_lessons(topic: str, out_dir: Path, manifest: RunManifestRecorder | None = None) -> PriorRunLessonsReport:
    path = out_dir / PRIOR_RUN_LESSONS_JSON
    if path.exists():
        report = _load_prior_run_lessons_report(path)
        if not (out_dir / PRIOR_RUN_LESSONS_MD).exists():
            write_text(out_dir / PRIOR_RUN_LESSONS_MD, render_prior_run_lessons_markdown(report))
        if manifest is not None:
            manifest.record(
                "prior_run_lessons_checkpoint",
                inputs=[PRIOR_RUN_LESSONS_JSON],
                outputs=[],
                notes=["reused existing prior run lessons"],
                metrics={"status": report.status, "lessons": len(report.lessons), "analyzed_runs": report.analyzed_runs},
            )
        return report
    report = write_prior_run_lessons_artifacts(topic, out_dir.parent, out_dir)
    if manifest is not None:
        manifest.record(
            "prior_run_lessons",
            inputs=[],
            outputs=[PRIOR_RUN_LESSONS_JSON, PRIOR_RUN_LESSONS_MD],
            metrics={"status": report.status, "lessons": len(report.lessons), "analyzed_runs": report.analyzed_runs},
        )
    return report


def _load_or_write_prior_run_library(topic: str, out_dir: Path, manifest: RunManifestRecorder | None = None) -> PriorRunLibraryReport:
    path = out_dir / PRIOR_RUN_LIBRARY_JSON
    if path.exists():
        report = _load_prior_run_library_report(path)
        if not (out_dir / PRIOR_RUN_LIBRARY_MD).exists():
            write_text(out_dir / PRIOR_RUN_LIBRARY_MD, render_prior_run_library_markdown(report))
        if manifest is not None:
            manifest.record(
                "prior_run_library_checkpoint",
                inputs=[PRIOR_RUN_LIBRARY_JSON],
                outputs=[],
                notes=["reused existing prior run library references"],
                metrics={"status": report.status, "references": len(report.references), "indexed_runs": report.indexed_runs},
            )
        return report
    report = write_prior_run_library_artifacts(topic, out_dir.parent, out_dir)
    if manifest is not None:
        manifest.record(
            "prior_run_library",
            inputs=[],
            outputs=[PRIOR_RUN_LIBRARY_JSON, PRIOR_RUN_LIBRARY_MD],
            metrics={"status": report.status, "references": len(report.references), "indexed_runs": report.indexed_runs},
        )
    return report


def _load_or_write_open_source_lessons(topic: str, out_dir: Path, manifest: RunManifestRecorder | None = None) -> OpenSourceLessonsReport:
    path = out_dir / OPEN_SOURCE_LESSONS_JSON
    if path.exists():
        report = _load_open_source_lessons_report(path)
        if not (out_dir / OPEN_SOURCE_LESSONS_MD).exists():
            write_text(out_dir / OPEN_SOURCE_LESSONS_MD, render_open_source_lessons_markdown(report))
        if manifest is not None:
            manifest.record(
                "open_source_lessons_checkpoint",
                inputs=[OPEN_SOURCE_LESSONS_JSON],
                outputs=[],
                notes=["reused existing open-source project lessons"],
                metrics={"status": report.status, "lessons": len(report.lessons), "profiles": len(report.profiles)},
            )
        return report
    report = write_open_source_lessons_artifacts(topic, out_dir)
    if manifest is not None:
        manifest.record(
            "open_source_lessons",
            inputs=[],
            outputs=[OPEN_SOURCE_LESSONS_JSON, OPEN_SOURCE_LESSONS_MD],
            metrics={"status": report.status, "lessons": len(report.lessons), "profiles": len(report.profiles)},
        )
    return report


def _load_prior_run_lessons_report(path: Path) -> PriorRunLessonsReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid prior run lessons JSON: {path}")
    lessons = [PriorRunLesson(**item) for item in data.get("lessons", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["lessons"] = lessons
    return PriorRunLessonsReport(**payload)


def _load_prior_run_library_report(path: Path) -> PriorRunLibraryReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid prior run library JSON: {path}")
    references = [PriorRunLibraryReference(**item) for item in data.get("references", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["references"] = references
    return PriorRunLibraryReport(**payload)


def _load_open_source_lessons_report(path: Path) -> OpenSourceLessonsReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid open-source lessons JSON: {path}")
    profiles = [OpenSourceProjectProfile(**item) for item in data.get("profiles", []) if isinstance(item, dict)]
    project_evidence = [OpenSourceProjectEvidence(**item) for item in data.get("project_evidence", []) if isinstance(item, dict)]
    lessons = [OpenSourceLesson(**item) for item in data.get("lessons", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["profiles"] = profiles
    payload["project_evidence"] = project_evidence
    payload["lessons"] = lessons
    payload.setdefault("contract_summary", {})
    return OpenSourceLessonsReport(**payload)


def _load_or_write_fulltext_corpus(topic: str, config: AgentConfig, out_dir: Path, manifest: RunManifestRecorder | None = None) -> FullTextCorpus:
    path = out_dir / FULLTEXT_CORPUS_JSON
    if path.exists():
        corpus = _load_fulltext_corpus(path)
        if not (out_dir / FULLTEXT_CORPUS_MD).exists():
            from .fulltext_corpus import render_fulltext_corpus_markdown

            write_text(out_dir / FULLTEXT_CORPUS_MD, render_fulltext_corpus_markdown(corpus))
        if manifest is not None:
            manifest.record(
                "fulltext_corpus_checkpoint",
                inputs=[FULLTEXT_CORPUS_JSON],
                outputs=[],
                notes=["reused existing fulltext corpus"],
                metrics={"documents": len(corpus.documents), "chunks": corpus.total_chunks},
            )
        return corpus
    corpus = write_fulltext_corpus_artifacts(topic, config.literature.fulltext_paths, out_dir, base_dir=Path.cwd())
    if manifest is not None:
        manifest.record(
            "fulltext_corpus",
            inputs=[],
            outputs=[FULLTEXT_CORPUS_JSON, FULLTEXT_CORPUS_MD],
            metrics={"documents": len(corpus.documents), "chunks": corpus.total_chunks},
        )
    return corpus


def _load_or_write_literature_evidence_mix(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: Any,
    coverage_report: dict[str, Any],
    out_dir: Path,
    manifest: RunManifestRecorder | None = None,
) -> dict[str, Any]:
    if (out_dir / LITERATURE_EVIDENCE_MIX_JSON).exists() and (out_dir / LITERATURE_EVIDENCE_MIX_MD).exists():
        report = _read_dict(out_dir / LITERATURE_EVIDENCE_MIX_JSON)
        if manifest is not None:
            manifest.record(
                "literature_evidence_mix_checkpoint",
                inputs=[LITERATURE_EVIDENCE_MIX_JSON],
                outputs=[],
                notes=["reused existing literature evidence mix audit"],
                metrics={"status": report.get("status"), "mix_score": report.get("mix_score")},
            )
        return report
    report = write_literature_evidence_mix_artifacts(research_plan, raw_review, curated_review, quality_report, coverage_report, out_dir)
    if manifest is not None:
        manifest.record(
            "literature_evidence_mix",
            inputs=["00-research-plan.json", "01-literature.json", "01-literature-curated.json", "01-literature-quality.json", LITERATURE_COVERAGE_JSON],
            outputs=[LITERATURE_EVIDENCE_MIX_JSON, LITERATURE_EVIDENCE_MIX_MD],
            metrics={"status": report.get("status"), "mix_score": report.get("mix_score")},
        )
    return report


def write_context_and_citation_artifacts(
    out_dir: Path,
    context: LiteratureContext,
    *,
    topic: str = "",
    quality_report: Any | None = None,
    source_health_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    coverage_report: dict[str, Any] | None = None,
    evidence_mix_report: dict[str, Any] | None = None,
    rescue_report: dict[str, Any] | None = None,
    rescue_execution_report: dict[str, Any] | None = None,
    seed_intake_report: dict[str, Any] | None = None,
    paper_grade_config: PaperGradeConfig | None = None,
) -> tuple[LiteratureContext, Any]:
    report = audit_citations(context)
    evidence_contract = write_literature_evidence_contract_artifacts(
        context=context,
        quality_report=quality_report if quality_report is not None else _read_dict(out_dir / "01-literature-quality.json"),
        source_health_report=source_health_report if source_health_report is not None else _read_dict(out_dir / LITERATURE_SOURCE_HEALTH_JSON),
        query_execution_report=query_execution_report if query_execution_report is not None else _read_dict(out_dir / QUERY_EXECUTION_AUDIT_JSON),
        rerank_report=rerank_report if rerank_report is not None else _read_dict(out_dir / LITERATURE_RERANK_JSON),
        citation_audit_report=report,
        run_dir=out_dir,
    )
    gate_decision = _write_literature_gate_decision_from_artifacts(
        out_dir=out_dir,
        context=context,
        topic=topic or context.topic,
        quality_report=quality_report if quality_report is not None else _read_dict(out_dir / "01-literature-quality.json"),
        source_health_report=source_health_report if source_health_report is not None else _read_dict(out_dir / LITERATURE_SOURCE_HEALTH_JSON),
        query_execution_report=query_execution_report if query_execution_report is not None else _read_dict(out_dir / QUERY_EXECUTION_AUDIT_JSON),
        rerank_report=rerank_report if rerank_report is not None else _read_dict(out_dir / LITERATURE_RERANK_JSON),
        coverage_report=coverage_report if coverage_report is not None else _read_dict(out_dir / LITERATURE_COVERAGE_JSON),
        evidence_mix_report=evidence_mix_report if evidence_mix_report is not None else _read_dict(out_dir / LITERATURE_EVIDENCE_MIX_JSON),
        rescue_report=rescue_report if rescue_report is not None else _read_dict(out_dir / LITERATURE_RESCUE_PLAN_JSON),
        rescue_execution_report=rescue_execution_report if rescue_execution_report is not None else _read_dict(out_dir / LITERATURE_RESCUE_EXECUTION_JSON),
        seed_intake_report=seed_intake_report if seed_intake_report is not None else _read_dict(out_dir / SEED_PAPER_INTAKE_JSON),
        evidence_contract_report=evidence_contract,
        citation_audit_report=report,
        paper_grade_config=paper_grade_config,
    )
    enriched_context = apply_literature_audits_to_context(context, evidence_contract_report=evidence_contract, gate_decision_report=gate_decision)
    enriched_context = apply_citation_audit_to_context(enriched_context, report)
    write_json(out_dir / "01-context.json", enriched_context)
    write_text(out_dir / "01-context.md", render_literature_context_markdown(enriched_context))
    write_text(out_dir / "01-review-gate.md", render_review_gate_markdown(enriched_context))
    write_text(out_dir / "01-references.bib", export_bibtex(enriched_context))
    write_text(out_dir / "01-references.ris", export_ris(enriched_context))
    write_citation_audit_artifacts(out_dir, enriched_context, report)
    return enriched_context, report


def _write_literature_gate_decision_from_artifacts(
    *,
    out_dir: Path,
    context: LiteratureContext,
    topic: str = "",
    quality_report: Any | None = None,
    source_health_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    coverage_report: dict[str, Any] | None = None,
    evidence_mix_report: dict[str, Any] | None = None,
    rescue_report: dict[str, Any] | None = None,
    rescue_execution_report: dict[str, Any] | None = None,
    seed_intake_report: dict[str, Any] | None = None,
    evidence_contract_report: dict[str, Any] | None = None,
    citation_audit_report: Any | None = None,
    citation_grounding_report: Any | None = None,
    paper_grade_config: PaperGradeConfig | None = None,
) -> dict[str, Any]:
    return write_literature_gate_decision_artifacts(
        topic=topic or context.topic,
        quality_report=quality_report if quality_report is not None else _read_dict(out_dir / "01-literature-quality.json"),
        source_health_report=source_health_report if source_health_report is not None else _read_dict(out_dir / LITERATURE_SOURCE_HEALTH_JSON),
        query_execution_report=query_execution_report if query_execution_report is not None else _read_dict(out_dir / QUERY_EXECUTION_AUDIT_JSON),
        rerank_report=rerank_report if rerank_report is not None else _read_dict(out_dir / LITERATURE_RERANK_JSON),
        coverage_report=coverage_report if coverage_report is not None else _read_dict(out_dir / LITERATURE_COVERAGE_JSON),
        evidence_mix_report=evidence_mix_report if evidence_mix_report is not None else _read_dict(out_dir / LITERATURE_EVIDENCE_MIX_JSON),
        rescue_report=rescue_report if rescue_report is not None else _read_dict(out_dir / LITERATURE_RESCUE_PLAN_JSON),
        rescue_execution_report=rescue_execution_report if rescue_execution_report is not None else _read_dict(out_dir / LITERATURE_RESCUE_EXECUTION_JSON),
        seed_intake_report=seed_intake_report if seed_intake_report is not None else _read_dict(out_dir / SEED_PAPER_INTAKE_JSON),
        evidence_contract_report=evidence_contract_report if evidence_contract_report is not None else _read_dict(out_dir / LITERATURE_EVIDENCE_CONTRACT_JSON),
        citation_audit_report=citation_audit_report if citation_audit_report is not None else _read_dict(out_dir / CITATION_AUDIT_JSON),
        context_report=build_literature_context_gate_report(context),
        citation_grounding_report=citation_grounding_report if citation_grounding_report is not None else _read_dict(out_dir / CITATION_GROUNDING_JSON),
        paper_grade_config=paper_grade_config,
        run_dir=out_dir,
    )


def write_citation_audit_artifacts(out_dir: Path, context: LiteratureContext, report: Any | None = None) -> Any:
    if report is None:
        report = audit_citations(context)
    write_json(out_dir / CITATION_AUDIT_JSON, report)
    write_text(out_dir / CITATION_AUDIT_MD, render_citation_audit_markdown(report))
    return report


def write_literature_source_health_artifacts(out_dir: Path, review: LiteratureReview) -> dict[str, Any]:
    report = literature_source_health_report(review)
    write_json(out_dir / LITERATURE_SOURCE_HEALTH_JSON, report)
    write_text(out_dir / LITERATURE_SOURCE_HEALTH_MD, render_literature_source_health_markdown(review))
    return report


def write_literature_search_strategy_artifacts(out_dir: Path, review: LiteratureReview) -> dict[str, Any]:
    strategy = review.search_strategy or _legacy_search_strategy(review)
    write_json(out_dir / LITERATURE_SEARCH_STRATEGY_JSON, strategy)
    write_text(out_dir / LITERATURE_SEARCH_STRATEGY_MD, render_literature_search_strategy_markdown(strategy))
    return strategy


def _load_or_write_query_execution_audit(
    research_plan: ResearchPlan,
    review: LiteratureReview,
    rerank_report: dict[str, Any],
    out_dir: Path,
    manifest: RunManifestRecorder | None = None,
) -> dict[str, Any]:
    source_health = _read_dict(out_dir / LITERATURE_SOURCE_HEALTH_JSON)
    if not source_health:
        source_health = write_literature_source_health_artifacts(out_dir, review)
    if not (out_dir / QUERY_EXECUTION_AUDIT_JSON).exists() or not (out_dir / QUERY_EXECUTION_AUDIT_MD).exists():
        report = write_query_execution_audit_artifacts(research_plan, review, rerank_report, source_health, out_dir)
        if manifest is not None:
            manifest.record(
                "query_execution_audit",
                inputs=[LITERATURE_SEARCH_STRATEGY_JSON, LITERATURE_SOURCE_HEALTH_JSON, LITERATURE_RERANK_JSON],
                outputs=[QUERY_EXECUTION_AUDIT_JSON, QUERY_EXECUTION_AUDIT_MD],
                metrics={
                    "status": report.get("status"),
                    "selected_queries": report.get("selected_query_count"),
                    "raw_candidates": report.get("raw_candidate_count"),
                },
            )
        return report
    report = _read_dict(out_dir / QUERY_EXECUTION_AUDIT_JSON)
    if manifest is not None:
        manifest.record(
            "query_execution_audit_checkpoint",
            inputs=[QUERY_EXECUTION_AUDIT_JSON],
            outputs=[],
            notes=["reused existing query execution audit"],
            metrics={"status": report.get("status"), "selected_queries": report.get("selected_query_count")},
        )
    return report


def _write_reranked_literature(out_dir: Path, review: LiteratureReview, research_plan: ResearchPlan) -> tuple[LiteratureReview, dict[str, Any]]:
    reranked, report = write_literature_rerank_artifacts(review, research_plan, out_dir)
    write_json(out_dir / "01-literature.json", reranked)
    write_text(out_dir / "01-literature.md", render_literature_markdown(reranked))
    return reranked, report


def _legacy_search_strategy(review: LiteratureReview) -> dict[str, Any]:
    selected_queries: list[str] = []
    for item in review.source_diagnostics:
        if "检索式:" not in item:
            continue
        selected_queries.extend(query.strip() for query in item.split("检索式:", 1)[-1].split("|") if query.strip())
    deduped: list[str] = []
    for query in selected_queries:
        if query not in deduped:
            deduped.append(query)
    return {
        "topic": review.topic,
        "provider": "unknown",
        "sources": sorted({source for paper in review.papers for source in (paper.sources or [paper.source])}),
        "max_queries": len(deduped),
        "selected_queries": deduped,
        "candidates": [],
        "warnings": ["历史 run 没有结构化检索策略，已从诊断文本恢复可见检索式。"],
        "recommendations": ["后续 run 会自动生成完整候选检索式、风险和选择理由。"],
    }


def request_cancel(out_dir: Path, requester: str = "manual", reason: str = "") -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cancel_path = out_dir / CANCEL_FILENAME
    existing = _read_cancel(cancel_path)
    if existing.get("cancelled") is True:
        return existing
    cancel = {
        "requested": True,
        "requested_at": existing.get("requested_at") or _utc_now(),
        "requester": requester,
        "reason": reason,
        "stage": "cancel_requested",
        "interrupted_stage": existing.get("interrupted_stage") or _current_stage(out_dir),
        "cancelled": False,
        "cancelled_at": None,
    }
    write_json(cancel_path, cancel)
    return cancel


def mark_cancelled(out_dir: Path, topic: str | None = None, stage: str | None = None) -> dict[str, Any]:
    cancel_path = out_dir / CANCEL_FILENAME
    cancel = _read_cancel(cancel_path)
    if not cancel:
        cancel = request_cancel(out_dir)
    interrupted_stage = stage or str(cancel.get("interrupted_stage") or _current_stage(out_dir) or "unknown")
    cancel.update(
        {
            "requested": True,
            "stage": "cancelled",
            "interrupted_stage": interrupted_stage,
            "cancelled": True,
            "cancelled_at": cancel.get("cancelled_at") or _utc_now(),
        }
    )
    write_json(cancel_path, cancel)
    topic_value = topic or _current_topic(out_dir)
    if topic_value:
        _write_state(out_dir, topic_value, "cancelled")
    return cancel


def wait_for_review_approval(
    out_dir: Path,
    poll_seconds: float = 1.0,
    topic: str | None = None,
    manifest: RunManifestRecorder | None = None,
) -> None:
    approval_path = out_dir / APPROVAL_FILENAME
    while True:
        _check_cancelled(out_dir, topic, manifest, "awaiting_review_approval")
        if _review_revision_requested(approval_path):
            if topic:
                _write_state(out_dir, topic, "review_revision_requested")
            raise PipelineReviewRevisionRequested(out_dir, _review_revision_notes(approval_path))
        if _approval_granted(approval_path):
            return
        time.sleep(poll_seconds)


def wait_for_execution_approval(
    out_dir: Path,
    poll_seconds: float = 1.0,
    topic: str | None = None,
    manifest: RunManifestRecorder | None = None,
) -> None:
    while True:
        _check_cancelled(out_dir, topic, manifest, "awaiting_execution_approval")
        if _execution_approval_granted(out_dir):
            return
        time.sleep(poll_seconds)


def _write_state(out_dir: Path, topic: str, stage: str) -> None:
    state = {
        "topic": topic,
        "stage": stage,
        "updated_at": _utc_now(),
    }
    write_json(out_dir / "state.json", state)
    update_workflow_stage(out_dir, topic, stage)
    _emit_node_state_events(out_dir, stage)


def _emit_node_state_events(out_dir: Path, stage: str) -> None:
    """STATE-01: adapt pipeline state transitions into node events."""
    try:
        if stage in {"cancelled", "failed"}:
            from .workflow_graph import read_workflow_status

            current_node = str(read_workflow_status(out_dir).get("current_node") or "")
            if current_node:
                append_node_event(
                    out_dir,
                    node_id=current_node,
                    event_type="cancelled" if stage == "cancelled" else "failed",
                    detail=f"state={stage}",
                )
            return
        pairs = stage_to_node_events(stage)
        if pairs:
            append_node_events(out_dir, pairs, detail=f"state={stage}")
    except Exception:
        # State bookkeeping must never break the pipeline.
        return


def _stage_begin(out_dir: Path, topic: str, node_id: str) -> None:
    """Mark a workflow node as running while its (possibly long) work executes."""
    begin_workflow_node(out_dir, topic, node_id)
    try:
        append_node_event(out_dir, node_id=node_id, event_type="started", detail=f"state={node_id}_started")
    except Exception:
        return


def _write_run_config_snapshot(out_dir: Path, config: AgentConfig) -> None:
    write_json(out_dir / "run-config.json", _run_config_snapshot_data(config))


def _run_config_snapshot_data(config: AgentConfig) -> dict[str, Any]:
    data = asdict(config)
    llm = data.get("llm")
    if isinstance(llm, dict):
        llm["api_key"] = ""
    literature = data.get("literature")
    if isinstance(literature, dict):
        literature["semantic_scholar_api_key"] = ""
        literature["openalex_api_key"] = ""
        literature["contact_email"] = ""
    if config.multi_agent == MultiAgentConfig():
        data.pop("multi_agent", None)
    return data


def _validate_or_create_checkpoint_contract(out_dir: Path, topic: str, config: AgentConfig) -> dict[str, Any]:
    current = _checkpoint_contract(topic, config)
    path = out_dir / CHECKPOINT_CONTRACT_JSON
    existing = _read_dict(path)
    if existing:
        if existing.get("fingerprint") != current["fingerprint"]:
            raise RuntimeError(
                "Checkpoint input/config/topic fingerprint changed; refusing to mix stale artifacts. "
                "Start a new run or use an explicit repair-resume cleanup."
            )
        return existing

    config_path = out_dir / "run-config.json"
    if config_path.exists():
        stored_config = _read_dict(config_path)
        if not stored_config and _has_legacy_checkpoint_artifacts(out_dir):
            raise RuntimeError("Legacy checkpoint has an empty or unreadable run-config.json; refusing to claim existing artifacts.")
        if stored_config and _digest_payload(stored_config) != current["config_sha256"]:
            raise RuntimeError("Checkpoint config changed; refusing to overwrite run-config.json before validation.")
    elif _has_legacy_checkpoint_artifacts(out_dir):
        raise RuntimeError(
            "Legacy checkpoint artifacts exist without run-config.json or a checkpoint contract; "
            "refusing to claim them under the current config. Use repair-resume cleanup or start a new run."
        )
    state = _read_dict(out_dir / "state.json")
    stored_topic = str(state.get("topic") or "")
    if stored_topic and stored_topic != topic:
        raise RuntimeError("Checkpoint topic changed; refusing to reuse artifacts from another research question.")
    write_json(path, current)
    return current


def _has_legacy_checkpoint_artifacts(out_dir: Path) -> bool:
    markers = [
        "00-research-plan.json",
        "01-literature.json",
        "01-literature-curated.json",
        "01-context.json",
        APPROVAL_FILENAME,
        "02-ideas.json",
        "03-experiment-plan.json",
        EXECUTION_APPROVAL_JSON,
        "04-results.json",
        "05-analysis.json",
        "06-paper.md",
    ]
    return any((out_dir / name).exists() for name in markers)


def _validate_checkpoint_topic_identity(out_dir: Path, topic: str) -> None:
    expected = str(topic or "").strip()
    state_topic = str(_read_dict(out_dir / "state.json").get("topic") or "").strip()
    approval_topic = str(_read_dict(out_dir / APPROVAL_FILENAME).get("topic") or "").strip()
    if any(value and value != expected for value in [state_topic, approval_topic]):
        raise RuntimeError("Checkpoint topic changed; refusing to reuse artifacts from another research question.")
    contract = _read_dict(out_dir / CHECKPOINT_CONTRACT_JSON)
    contract_topic_hash = str(contract.get("topic_sha256") or "")
    if contract_topic_hash and contract_topic_hash != _sha256_text(expected):
        raise RuntimeError("Checkpoint topic changed; refusing to reuse artifacts from another research question.")


def _renew_checkpoint_contract_for_review_revision(out_dir: Path, topic: str, config: AgentConfig) -> None:
    previous = _read_dict(out_dir / CHECKPOINT_CONTRACT_JSON)
    current = _checkpoint_contract(topic, config)
    renewal = {
        "renewed_by": "review_revision_repair",
        "renewed_at": _utc_now(),
        "previous_fingerprint": str(previous.get("fingerprint") or ""),
        "fingerprint": current["fingerprint"],
    }
    write_json(out_dir / CHECKPOINT_CONTRACT_JSON, {**current, "renewal": renewal})
    _write_run_config_snapshot(out_dir, config)


def _validate_repair_resume_identity(out_dir: Path, topic: str, report: dict[str, Any]) -> None:
    expected_topic = str(topic or "").strip()
    recorded_topics = [
        str(report.get("topic") or "").strip(),
        str(_read_dict(out_dir / "state.json").get("topic") or "").strip(),
        str(_read_dict(out_dir / REPAIR_QUEUE_JSON).get("topic") or "").strip(),
    ]
    mismatches = [value for value in recorded_topics if value and value != expected_topic]
    if mismatches:
        raise RuntimeError("Repair-resume topic does not match the run state/queue; refusing cleanup.")
    existing_contract = _read_dict(out_dir / CHECKPOINT_CONTRACT_JSON)
    contract_topic_hash = str(existing_contract.get("topic_sha256") or "")
    if contract_topic_hash and contract_topic_hash != _sha256_text(expected_topic):
        raise RuntimeError("Repair-resume topic does not match the checkpoint contract; refusing cleanup.")


def _validate_repair_resume_approval_cleanup(out_dir: Path, report: dict[str, Any]) -> None:
    scheduled = set(str(item) for item in report.get("artifacts_to_remove", []) if str(item))
    required: list[str] = []
    if report.get("review_reapproval_required") is True and (out_dir / APPROVAL_FILENAME).is_file():
        required.append(APPROVAL_FILENAME)
    if report.get("execution_reapproval_required") is True and (out_dir / EXECUTION_APPROVAL_JSON).is_file():
        required.append(EXECUTION_APPROVAL_JSON)
    missing = [name for name in required if name not in scheduled]
    if missing:
        raise RuntimeError("Repair-resume did not schedule stale approvals for removal: " + ", ".join(missing))


def _renew_checkpoint_contract_after_repair(
    out_dir: Path,
    topic: str,
    config: AgentConfig,
    report: dict[str, Any],
) -> dict[str, Any]:
    path = out_dir / CHECKPOINT_CONTRACT_JSON
    previous = _read_dict(path)
    current = _checkpoint_contract(topic, config)
    renewal = {
        "renewed_by": "repair_resume",
        "renewed_at": _utc_now(),
        "rerun_from": str(report.get("rerun_from") or ""),
        "previous_fingerprint": str(previous.get("fingerprint") or ""),
        "fingerprint": current["fingerprint"],
    }
    write_json(path, {**current, "renewal": renewal})
    _write_run_config_snapshot(out_dir, config)
    return renewal


def _checkpoint_contract(topic: str, config: AgentConfig) -> dict[str, Any]:
    config_data = _run_config_snapshot_data(config)
    inputs = _configured_input_records(config)
    payload = {
        "schema_version": 1,
        "topic": topic,
        "topic_sha256": _sha256_text(topic),
        "config_sha256": _digest_payload(config_data),
        "configured_inputs": inputs,
    }
    return {**payload, "fingerprint": _digest_payload(payload)}


def _configured_input_records(config: AgentConfig) -> list[dict[str, Any]]:
    values = [*config.literature.fulltext_paths, *config.execution.benchmark_manifest_paths]
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        try:
            path = Path(raw).resolve()
        except OSError:
            path = Path(raw)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "configured_path": raw,
                "resolved_path": key,
                "exists": path.is_file(),
                "sha256": _file_sha256(path) if path.is_file() else "",
            }
        )
    manifest_paths: dict[str, str] = {}
    for value in config.execution.benchmark_manifest_paths:
        raw = str(value).strip()
        if not raw:
            continue
        try:
            manifest_paths[str(Path(raw).resolve())] = raw
        except OSError:
            continue
    for item in benchmark_source_artifacts(config.execution):
        resolved_path = str(item.get("path") or "")
        if not resolved_path or resolved_path in seen:
            continue
        seen.add(resolved_path)
        records.append(
            {
                "configured_path": manifest_paths.get(resolved_path, resolved_path),
                "resolved_path": resolved_path,
                "exists": item.get("exists") is True,
                "sha256": str(item.get("sha256") or ""),
                "benchmark_dependency": resolved_path not in manifest_paths,
            }
        )
    project_root = Path(__file__).resolve().parents[2]
    # SKILL-02: the fingerprint must cover the skills that will actually be
    # injected, i.e. the effective binding (explicit role skills or the
    # built-in defaults), not just explicitly configured ones. Skipped while
    # multi_agent is disabled so legacy checkpoints stay resumable.
    if config.multi_agent.enabled:
        from .agent_runtime import DEFAULT_ROLE_SKILLS

        role_map = {role.agent_id: role for role in config.multi_agent.roles}
        for agent_id in sorted(set(role_map) | set(DEFAULT_ROLE_SKILLS)):
            role = role_map.get(agent_id)
            if role is not None and role.skills:
                effective_skills = list(role.skills)
                skill_source = "explicit"
            else:
                effective_skills = list(DEFAULT_ROLE_SKILLS.get(agent_id, []))
                skill_source = "default"
            for skill_id in effective_skills:
                path = project_root / "skills" / str(skill_id) / "SKILL.md"
                try:
                    resolved_path = str(path.resolve())
                except OSError:
                    resolved_path = str(path)
                if resolved_path in seen:
                    continue
                seen.add(resolved_path)
                safe_file = path.is_file() and not path.is_symlink()
                records.append(
                    {
                        "configured_path": f"skill:{skill_id}",
                        "resolved_path": resolved_path,
                        "exists": safe_file,
                        "sha256": _file_sha256(path) if safe_file else "",
                        "agent_id": agent_id,
                        "skill_source": skill_source,
                        "agent_dependency": True,
                    }
                )
    for role in config.multi_agent.roles:
        for skill_id in role.skills:
            path = project_root / "skills" / str(skill_id) / "SKILL.md"
            try:
                resolved_path = str(path.resolve())
            except OSError:
                resolved_path = str(path)
            if resolved_path in seen:
                continue
            seen.add(resolved_path)
            safe_file = path.is_file() and not path.is_symlink()
            records.append(
                {
                    "configured_path": f"skill:{skill_id}",
                    "resolved_path": resolved_path,
                    "exists": safe_file,
                    "sha256": _file_sha256(path) if safe_file else "",
                    "agent_dependency": True,
                }
            )
    return records


def _digest_payload(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _approval_granted(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict) or data.get("approved") is not True:
        return False
    policy = _approval_policy_from_record(data)
    if policy.get("notes_required") and not _substantive_approval_notes(str(data.get("notes") or "")):
        return False
    binding = data.get("approval_binding") if isinstance(data.get("approval_binding"), dict) else {}
    if binding:
        current = _review_approval_binding(path.parent, str(data.get("topic") or ""))
        if data.get("approval_binding_sha256") != _digest_payload(current) or binding != current:
            return False
    elif (path.parent / "01-context.json").exists() or (path.parent / "01-review-gate.md").exists():
        return False
    return True


def _review_approval_binding(out_dir: Path, topic: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "topic_sha256": _sha256_text(topic),
        "context_sha256": _file_sha256(out_dir / "01-context.json"),
        "review_gate_sha256": _file_sha256(out_dir / "01-review-gate.md"),
        "literature_gate_decision_sha256": _file_sha256(out_dir / LITERATURE_GATE_DECISION_JSON),
        "run_config_sha256": _file_sha256(out_dir / "run-config.json"),
    }


def _approval_requires_revision_repair(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        approval = read_json(path)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    revision_at = _latest_revision_requested_at(approval)
    if not revision_at:
        return False
    repaired_at = str(approval.get("revision_repaired_at") or "").strip()
    return not repaired_at or repaired_at < revision_at


def _latest_revision_requested_at(approval: dict[str, Any]) -> str:
    values: list[str] = []
    direct = str(approval.get("revision_requested_at") or "").strip()
    if direct:
        values.append(direct)
    for item in _approval_history(approval):
        if str(item.get("action") or "").strip() != "revision_requested":
            continue
        at = str(item.get("at") or "").strip()
        if at:
            values.append(at)
    return max(values) if values else ""


def _review_revision_requested(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, dict) and data.get("revision_requested") is True


def _execution_approval_granted(out_dir: Path) -> bool:
    path = out_dir / EXECUTION_APPROVAL_JSON
    if not path.exists():
        return False
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict) or data.get("approved") is not True:
        return False
    if not _substantive_approval_notes(str(data.get("notes") or "")):
        return False
    return _execution_approval_context_matches(out_dir, data)


def _execution_approval_context_matches(out_dir: Path, data: dict[str, Any]) -> bool:
    plan_hash = _file_sha256(out_dir / "03-experiment-plan.json")
    safety_hash = _file_sha256(out_dir / EXECUTION_SAFETY_AUDIT_JSON)
    safety_report = _read_dict(out_dir / EXECUTION_SAFETY_AUDIT_JSON)
    binding = data.get("execution_binding") if isinstance(data.get("execution_binding"), dict) else {}
    binding_hash = str(data.get("execution_binding_sha256") or "")
    current_binding = safety_report.get("execution_binding") if isinstance(safety_report.get("execution_binding"), dict) else {}
    current_binding_hash = str(safety_report.get("execution_binding_sha256") or "")
    return bool(
        plan_hash
        and safety_hash
        and binding
        and binding_hash
        and current_binding
        and data.get("plan_sha256") == plan_hash
        and data.get("safety_sha256") == safety_hash
        and binding_hash == current_binding_hash
        and binding_hash == _digest_payload(binding)
        and binding == current_binding
        and safety_report.get("status") != "block"
        and execution_source_binding_matches(binding)
    )


def _review_revision_notes(path: Path) -> str:
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return ""
    return str(data.get("notes") or "") if isinstance(data, dict) else ""


def _approval_history(approval: dict[str, Any]) -> list[dict[str, Any]]:
    history = approval.get("history")
    if not isinstance(history, list):
        return []
    return [dict(item) for item in history if isinstance(item, dict)]


def _approval_policy(gate_status: str, warnings: list[str] | None = None) -> dict[str, Any]:
    status = str(gate_status or "").strip() or "unknown"
    warning_count = len(warnings or [])
    notes_required = status not in {"pass", "unknown"}
    reason = ""
    if notes_required:
        reason = (
            f"review gate status is {status}; approval notes must explain manual rationale, "
            "remaining risks, or completed literature/citation repairs before idea/experiment can continue."
        )
    return {
        "notes_required": notes_required,
        "gate_status": status,
        "warning_count": warning_count,
        "reason": reason,
    }


def _approval_policy_from_record(approval: dict[str, Any]) -> dict[str, Any]:
    stored_policy = approval.get("approval_policy")
    policy_status = ""
    stored_notes_required = False
    if isinstance(stored_policy, dict):
        policy_status = str(stored_policy.get("gate_status") or "").strip()
        stored_notes_required = stored_policy.get("notes_required") is True

    record_status = str(approval.get("gate_status") or "").strip()
    status = record_status or policy_status
    warnings = approval.get("warnings") if isinstance(approval.get("warnings"), list) else []
    policy = _approval_policy(status, [str(item) for item in warnings])
    if stored_notes_required:
        policy["notes_required"] = True
        policy["reason"] = str(stored_policy.get("reason") or "This review gate requires approval notes before continuing.") if isinstance(stored_policy, dict) else policy["reason"]
    return policy


def _substantive_approval_notes(notes: str) -> bool:
    normalized = " ".join(str(notes or "").split())
    return len(normalized) >= 8


def _file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _check_cancelled(
    out_dir: Path,
    topic: str | None,
    manifest: RunManifestRecorder | None,
    stage: str,
) -> None:
    if not _cancel_requested(out_dir):
        return
    cancel = mark_cancelled(out_dir, topic=topic, stage=stage)
    if manifest is not None:
        manifest.record(
            "cancelled",
            status="cancelled",
            inputs=[CANCEL_FILENAME],
            outputs=[CANCEL_FILENAME, "state.json"],
            metrics={"interrupted_stage": cancel.get("interrupted_stage")},
        )
    raise PipelineCancelled(out_dir, str(cancel.get("interrupted_stage") or stage))


def _cancel_requested(out_dir: Path) -> bool:
    return _read_cancel(out_dir / CANCEL_FILENAME).get("requested") is True


def _read_cancel(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _current_stage(out_dir: Path) -> str:
    try:
        state = read_json(out_dir / "state.json")
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return "unknown"
    if not isinstance(state, dict):
        return "unknown"
    return str(state.get("stage") or "unknown")


def _current_topic(out_dir: Path) -> str:
    try:
        state = read_json(out_dir / "state.json")
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return ""
    if not isinstance(state, dict):
        return ""
    return str(state.get("topic") or "")


def _load_research_plan(path: Path) -> ResearchPlan:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid research plan JSON: {path}")
    return ResearchPlan(**data)


def _load_benchmark_plan(path: Path) -> BenchmarkPlan:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid benchmark plan JSON: {path}")
    candidates = [BenchmarkCandidate(**item) for item in data.get("candidates", []) if isinstance(item, dict)]
    return BenchmarkPlan(
        topic=str(data.get("topic") or ""),
        domain=str(data.get("domain") or ""),
        template_profile=str(data.get("template_profile") or "generic"),
        candidates=candidates,
        selected_names=[str(item) for item in data.get("selected_names", [])],
        required_actions=[str(item) for item in data.get("required_actions", [])],
        warnings=[str(item) for item in data.get("warnings", [])],
    )


def _experiment_results_usable(results: Any) -> bool:
    """04-results.json 完整性校验：非空列表且每行有名称与状态才算可用。"""
    if not isinstance(results, list) or not results:
        return False
    return all(
        isinstance(row, dict) and str(row.get("name") or "").strip() and str(row.get("status") or "").strip()
        for row in results
    )


def _model_source_recorder(out_dir: Path):
    """把模型阶段来源（model/template/paused）持久化到 04-model-stage-sources.json。"""
    run_dir = Path(out_dir)

    def _record(event: dict[str, Any]) -> None:
        record_model_stage_source(
            run_dir,
            str(event.get("stage") or ""),
            str(event.get("source") or ""),
            call_id=int(event.get("call_id") or 0),
            failure=event.get("failure"),
            independent_completed=event.get("independent_review_completed"),
        )

    return _record


def _read_dict(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _paper_matches_benchmark_evidence(path: Path, benchmark_evidence: dict[str, Any], execution_mode: str) -> bool:
    if execution_mode != "benchmark" or str(benchmark_evidence.get("evidence_grade") or "") != "real_benchmark":
        return True
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return not any(_has_unnegated_stale_benchmark_scope(sentence) for sentence in _scope_sentences(text))


def _final_readiness_checkpoint_reusable(out_dir: Path, benchmark_evidence: dict[str, Any], execution_mode: str) -> bool:
    # 评审输入快照（若存在）不一致 → 稿件/结果在终局后变化过，禁止复用（A06）。
    snapshot = load_review_input_snapshot(out_dir)
    if snapshot is not None and verify_snapshot(out_dir, snapshot):
        return False
    if not _paper_matches_benchmark_evidence(out_dir / REVISED_PAPER_MD, benchmark_evidence, execution_mode):
        return False
    for name in [
        REVISED_PAPER_REVIEW_JSON,
        CLAIM_TRACEABILITY_JSON,
        CITATION_GROUNDING_JSON,
        CITATION_COVERAGE_JSON,
        RESULTS_PRESENTATION_JSON,
        CLAIM_CONSISTENCY_JSON,
        SUBMISSION_CHECK_JSON,
        FINAL_READINESS_JSON,
    ]:
        data = _read_dict(out_dir / name)
        status = str(data.get("status") or data.get("decision") or "")
        if status in {"block", "blocked", "requires_human_evidence", "requires_real_experiment"}:
            return False
        if data.get("blocking_issues"):
            return False
    return True


def _has_unnegated_stale_benchmark_scope(sentence: str) -> bool:
    lowered = sentence.lower()
    stale_markers = ["dry-run", "dry run", "scaffold", "脚手架", "模拟实验", "模拟结果", "模拟数据"]
    if not any(marker in lowered for marker in stale_markers):
        return False
    negation_markers = ["不是", "而不是", "不得", "不能", "不应", "不要", "避免", "不能替代", "not ", "not a", "not an", "instead of", "rather than", "do not"]
    return not any(marker in lowered for marker in negation_markers)


def _scope_sentences(text: str) -> list[str]:
    normalized = text.replace("\n", "。").replace("；", "。").replace(";", ".")
    return [item.strip() for item in normalized.split("。") if item.strip()]


def _paper_revision_plan_checkpoint_matches(current: PaperRevisionPlan, expected: PaperRevisionPlan) -> bool:
    return _revision_plan_signature(current) == _revision_plan_signature(expected)


def _revision_plan_signature(plan: PaperRevisionPlan) -> tuple[Any, ...]:
    return (
        plan.decision,
        plan.readiness,
        plan.summary,
        tuple((task.section, task.severity, task.issue, task.action, tuple(task.evidence_refs)) for task in plan.tasks),
        tuple(plan.acceptance_checks),
    )


def _claim_boundary_preflight_checkpoint_matches(
    report: dict[str, Any],
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    benchmark_evidence: dict[str, Any],
    experiment_decision: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    execution_mode: str,
) -> bool:
    summary = report.get("evidence_summary") if isinstance(report.get("evidence_summary"), dict) else {}
    if not summary:
        return False
    expected = {
        "execution_mode": execution_mode,
        "validation_status": result_validation.get("status"),
        "failure_status": failure_analysis.get("status"),
        "benchmark_status": benchmark_evidence.get("status"),
        "benchmark_grade": benchmark_evidence.get("evidence_grade"),
        "benchmark_claim_policy": benchmark_evidence.get("claim_policy"),
        "experiment_decision": experiment_decision.get("decision"),
        "experiment_decision_status": experiment_decision.get("status"),
        "paper_policy": experiment_decision.get("paper_policy"),
        "downstream_writing_allowed": experiment_decision.get("downstream_writing_allowed") is not False,
        "hypothesis_outcome": hypothesis_outcome.get("outcome"),
        "hypothesis_status": hypothesis_outcome.get("status"),
    }
    return _checkpoint_values_match(summary, expected)


def _paper_review_calibration_checkpoint_matches(
    report: dict[str, Any],
    experiment_decision: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    execution_mode: str,
) -> bool:
    expected = {
        "execution_mode": execution_mode,
        "experiment_decision": experiment_decision.get("decision"),
        "hypothesis_outcome": hypothesis_outcome.get("outcome"),
    }
    return _checkpoint_values_match(report, expected)


def _checkpoint_values_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(_checkpoint_value(actual.get(key)) == _checkpoint_value(value) for key, value in expected.items())


def _checkpoint_value(value: Any) -> str:
    return "" if value is None else str(value)


def _repair_resume_retrieval_tasks(out_dir: Path) -> list[dict[str, Any]]:
    plan = _read_dict(out_dir / REPAIR_RESUME_PLAN_JSON)
    if plan.get("applied") is not True or str(plan.get("rerun_from") or "") != "literature_review":
        return []
    tasks = plan.get("retrieval_repair_tasks") if isinstance(plan.get("retrieval_repair_tasks"), list) else []
    return [item for item in tasks if isinstance(item, dict)]


def _repair_resume_context(out_dir: Path) -> str:
    plan = _read_dict(out_dir / REPAIR_RESUME_PLAN_JSON)
    if plan.get("applied") is not True:
        return ""
    context = plan.get("repair_context") if isinstance(plan.get("repair_context"), dict) else {}
    text = str(context.get("prompt_text") or "").strip()
    if text:
        return text
    constraints = context.get("constraints") if isinstance(context.get("constraints"), list) else []
    values = [str(item).strip() for item in constraints if str(item).strip()]
    if not values:
        return ""
    return "Repair-resume constraints:\n" + "\n".join(f"- {item}" for item in values)


def _submission_check_has_item(path: Path, item_name: str) -> bool:
    data = _read_dict(path)
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    return any(isinstance(item, dict) and str(item.get("item") or "") == item_name for item in checks)


def _load_literature_review(path: Path) -> LiteratureReview:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid literature review JSON: {path}")
    papers = [Paper(**item) for item in data.get("papers", []) if isinstance(item, dict)]
    return LiteratureReview(
        topic=str(data.get("topic") or ""),
        papers=papers,
        themes=[str(item) for item in data.get("themes", [])],
        gaps=[str(item) for item in data.get("gaps", [])],
        summary=str(data.get("summary") or ""),
        source_diagnostics=[str(item) for item in data.get("source_diagnostics", [])],
        evidence_table=list(data.get("evidence_table", [])) if isinstance(data.get("evidence_table"), list) else [],
        source_health=[dict(item) for item in data.get("source_health", []) if isinstance(item, dict)],
        search_strategy=dict(data.get("search_strategy", {})) if isinstance(data.get("search_strategy"), dict) else {},
    )


def _load_literature_context(path: Path) -> LiteratureContext:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid literature context JSON: {path}")
    gate_data = data.get("review_gate") if isinstance(data.get("review_gate"), dict) else {}
    return LiteratureContext(
        topic=str(data.get("topic") or ""),
        citations=[CitationEntry(**item) for item in data.get("citations", []) if isinstance(item, dict)],
        chunks=[EvidenceChunk(**item) for item in data.get("chunks", []) if isinstance(item, dict)],
        claim_support=[ClaimSupport(**item) for item in data.get("claim_support", []) if isinstance(item, dict)],
        review_gate=ReviewGate(
            status=str(gate_data.get("status") or "review_required"),
            warnings=[str(item) for item in gate_data.get("warnings", [])],
            required_actions=[str(item) for item in gate_data.get("required_actions", [])],
        ),
    )


def _load_fulltext_corpus(path: Path) -> FullTextCorpus:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid fulltext corpus JSON: {path}")
    documents = [FullTextDocument(**item) for item in data.get("documents", []) if isinstance(item, dict)]
    return FullTextCorpus(
        topic=str(data.get("topic") or ""),
        documents=documents,
        total_chunks=int(data.get("total_chunks") or sum(len(item.chunks) for item in documents)),
        warnings=[str(item) for item in data.get("warnings", [])],
    )


def _load_ideas(path: Path) -> list[ResearchIdea]:
    data = read_json(path)
    if not isinstance(data, list):
        raise RuntimeError(f"Invalid ideas JSON: {path}")
    return [ResearchIdea(**item) for item in data if isinstance(item, dict)]


def _ensure_idea_agent_roles(ideas: list[ResearchIdea], agent_assignment: dict[str, Any] | None) -> list[ResearchIdea]:
    updated: list[ResearchIdea] = []
    for idea in ideas:
        roles = list(idea.agent_roles)
        if not roles:
            roles = agent_roles_for_text(
                agent_assignment,
                " ".join([idea.title, idea.hypothesis, idea.mechanism, idea.gap_alignment, idea.baseline]),
                limit=4,
            )
        if roles and "method_architect" not in roles:
            roles.insert(0, "method_architect")
        normalized = _unique_strings(roles)[:5]
        updated.append(replace(idea, agent_roles=normalized) if normalized != idea.agent_roles else idea)
    return updated


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _load_exploration_map(path: Path) -> ExplorationMap:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid exploration map JSON: {path}")
    branches = [ExplorationBranch(**item) for item in data.get("branches", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["branches"] = branches
    return ExplorationMap(**payload)


def _load_experiment_plan(path: Path) -> ExperimentPlan:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid experiment plan JSON: {path}")
    commands = [ExperimentCommand(**item) for item in data.get("commands", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["commands"] = commands
    return ExperimentPlan(**payload)


def _ensure_experiment_plan_agent_roles(plan: ExperimentPlan, idea: ResearchIdea) -> ExperimentPlan:
    roles = list(plan.agent_roles) or list(idea.agent_roles)
    if roles and "method_architect" not in roles:
        roles.insert(0, "method_architect")
    normalized = _unique_strings(roles)[:5]
    return replace(plan, agent_roles=normalized) if normalized != plan.agent_roles else plan


def _execution_audit_plan(
    plan: ExperimentPlan,
    runbook: dict[str, Any],
    adapter_report: dict[str, Any],
    execution_mode: str,
) -> ExperimentPlan:
    if execution_mode != "benchmark":
        return plan
    commands = _runbook_experiment_commands(runbook) or plan.commands
    metrics = _adapter_expected_metrics(adapter_report) or _runbook_plan_metrics(runbook) or plan.metrics
    if commands == plan.commands and metrics == plan.metrics:
        return plan
    return ExperimentPlan(
        idea_title=plan.idea_title,
        objective=plan.objective,
        variables=plan.variables,
        metrics=metrics,
        protocol=[*plan.protocol, "结果审计使用 benchmark runbook 中实际执行的 adapter 命令和 manifest 指标。"],
        commands=commands,
        rationale=plan.rationale,
        baseline=plan.baseline,
        evidence_keys=plan.evidence_keys,
        template_profile=plan.template_profile,
    )


def _runbook_experiment_commands(runbook: dict[str, Any]) -> list[ExperimentCommand]:
    commands: list[ExperimentCommand] = []
    for item in runbook.get("commands", []) if isinstance(runbook.get("commands"), list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        command = [str(value) for value in item.get("command", [])] if isinstance(item.get("command"), list) else []
        expected = [str(value) for value in item.get("expected_artifacts", [])] if isinstance(item.get("expected_artifacts"), list) else []
        role = str(item.get("role") or "").strip()
        commands.append(
            ExperimentCommand(
                name=name,
                command=command,
                expected_artifacts=expected,
                role=role,
                comparison_group=str(item.get("comparison_group") or "default"),
                adapter_id=str(item.get("adapter_id") or name),
            )
        )
    return commands


def _adapter_expected_metrics(adapter_report: dict[str, Any]) -> list[str]:
    metrics: list[str] = []
    for key in ("adapters", "commands"):
        for item in adapter_report.get(key, []) if isinstance(adapter_report.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            if "status" in item and str(item.get("status") or "") != "ready":
                continue
            if isinstance(item.get("expected_metrics"), list):
                metrics.extend(str(value) for value in item.get("expected_metrics", []) if str(value).strip())
    unique: list[str] = []
    for metric in metrics:
        if metric not in unique:
            unique.append(metric)
    return unique


def _runbook_plan_metrics(runbook: dict[str, Any]) -> list[str]:
    plan = runbook.get("plan") if isinstance(runbook.get("plan"), dict) else {}
    metrics = plan.get("metrics") if isinstance(plan.get("metrics"), list) else []
    return [str(value) for value in metrics if str(value).strip()]


def _load_experiment_results(path: Path) -> list[ExperimentResult]:
    data = read_json(path)
    if not isinstance(data, list):
        raise RuntimeError(f"Invalid experiment results JSON: {path}")
    return [ExperimentResult(**item) for item in data if isinstance(item, dict)]


def _load_analysis(path: Path) -> Analysis:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid analysis JSON: {path}")
    return Analysis(**data)


def _load_paper_review(path: Path) -> PaperReview:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid paper review JSON: {path}")
    claim_audit = [PaperClaimAudit(**item) for item in data.get("claim_audit", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["claim_audit"] = claim_audit
    return PaperReview(**payload)


def _load_paper_revision_plan(path: Path) -> PaperRevisionPlan:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid paper revision plan JSON: {path}")
    tasks = [RevisionTask(**item) for item in data.get("tasks", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["tasks"] = tasks
    return PaperRevisionPlan(**payload)


def _load_paper_rewrite_report(path: Path) -> PaperRewriteReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid paper rewrite report JSON: {path}")
    task_results = [PaperRevisionTaskResult(**item) for item in data.get("task_results", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["task_results"] = task_results
    return PaperRewriteReport(**payload)


def _load_code_data_availability_report(path: Path) -> CodeDataAvailabilityReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid code/data availability JSON: {path}")
    checks = [CodeDataAvailabilityItem(**item) for item in data.get("checks", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["checks"] = checks
    return CodeDataAvailabilityReport(**payload)


def _load_submission_check_report(path: Path) -> SubmissionCheckReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid submission check JSON: {path}")
    checks = [SubmissionCheckItem(**item) for item in data.get("checks", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["checks"] = checks
    return SubmissionCheckReport(**payload)


def _load_claim_traceability_report(path: Path) -> ClaimTraceabilityReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid claim traceability JSON: {path}")
    items = [ClaimTraceabilityItem(**item) for item in data.get("items", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["items"] = items
    return ClaimTraceabilityReport(**payload)


def _load_citation_grounding_report(path: Path) -> CitationGroundingReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid citation grounding JSON: {path}")
    items = [CitationGroundingItem(**item) for item in data.get("items", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["items"] = items
    return CitationGroundingReport(**payload)


def _load_results_presentation_report(path: Path) -> ResultsPresentationReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid results presentation JSON: {path}")
    checks = [ResultsPresentationCheck(**item) for item in data.get("checks", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["checks"] = checks
    return ResultsPresentationReport(**payload)


def _load_claim_consistency_report(path: Path) -> ClaimConsistencyReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid claim consistency JSON: {path}")
    checks = [ClaimConsistencyCheck(**item) for item in data.get("checks", []) if isinstance(item, dict)]
    payload = dict(data)
    payload["checks"] = checks
    return ClaimConsistencyReport(**payload)


def _load_final_readiness_report(path: Path) -> FinalReadinessReport:
    data = read_json(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid final readiness JSON: {path}")
    return FinalReadinessReport(**data)


