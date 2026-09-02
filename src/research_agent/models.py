from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Paper:
    title: str
    authors: list[str]
    year: int
    venue: str
    url: str
    abstract: str
    relevance: float
    source: str = "offline"
    sources: list[str] = field(default_factory=list)
    doi: str = ""
    external_ids: dict[str, str] = field(default_factory=dict)
    citation_count: int | None = None
    evidence_note: str = ""


@dataclass(frozen=True)
class LiteratureReview:
    topic: str
    papers: list[Paper]
    themes: list[str]
    gaps: list[str]
    summary: str
    source_diagnostics: list[str] = field(default_factory=list)
    evidence_table: list[dict[str, str | int | float | None]] = field(default_factory=list)
    source_health: list[dict[str, Any]] = field(default_factory=list)
    search_strategy: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LiteratureSearchQuery:
    query: str
    origin: str
    intent: str
    priority: int
    selected: bool
    rationale: str
    risk: str = ""


@dataclass(frozen=True)
class LiteratureSearchStrategy:
    topic: str
    provider: str
    sources: list[str]
    max_queries: int
    selected_queries: list[str]
    candidates: list[LiteratureSearchQuery]
    status: str = ""
    quality_score: float = 0.0
    selected_intents: list[str] = field(default_factory=list)
    missing_required_intents: list[str] = field(default_factory=list)
    weak_selected_queries: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LiteratureQualityItem:
    title: str
    year: int
    venue: str
    sources: list[str]
    relevance: float
    quality_score: float
    decision: str
    selected: bool
    reasons: list[str]
    doi: str = ""
    url: str = ""
    evidence_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LiteratureQualityReport:
    topic: str
    total_papers: int
    selected_papers: int
    min_keep: int
    items: list[LiteratureQualityItem]
    warnings: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    confidence_status: str = ""
    confidence_factors: dict[str, float | int | str] = field(default_factory=dict)
    source_warnings: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    role_coverage: dict[str, int] = field(default_factory=dict)
    missing_evidence_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchPlan:
    topic: str
    domain: str
    objective: str
    search_queries: list[str]
    benchmarks: list[str]
    baselines: list[str]
    metrics: list[str]
    constraints: list[str]
    risks: list[str]
    success_criteria: list[str]


@dataclass(frozen=True)
class CitationEntry:
    key: str
    title: str
    authors: list[str]
    year: int
    venue: str
    url: str
    doi: str = ""
    source: str = ""


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    citation_key: str
    title: str
    text: str
    source: str
    url: str
    relevance: float


@dataclass(frozen=True)
class ClaimSupport:
    claim: str
    claim_type: str
    support_level: str
    citation_keys: list[str]
    evidence_notes: list[str]


@dataclass(frozen=True)
class ReviewGate:
    status: str
    warnings: list[str]
    required_actions: list[str]


@dataclass(frozen=True)
class LiteratureContext:
    topic: str
    citations: list[CitationEntry]
    chunks: list[EvidenceChunk]
    claim_support: list[ClaimSupport]
    review_gate: ReviewGate


@dataclass(frozen=True)
class FullTextDocument:
    title: str
    path: str
    sha256: str
    status: str
    text_chars: int
    chunks: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FullTextCorpus:
    topic: str
    documents: list[FullTextDocument]
    total_chunks: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CitationAuditItem:
    citation_key: str
    title: str
    decision: str
    risk: str
    issues: list[str]
    doi: str = ""
    url: str = ""
    year: int = 0
    source: str = ""
    locator_status: str = ""
    source_agreement: str = ""
    claim_support_count: int = 0


@dataclass(frozen=True)
class CitationAuditReport:
    topic: str
    total_citations: int
    usable_citations: int
    review_required: int
    blocked_citations: int
    doi_coverage: float
    url_coverage: float
    items: list[CitationAuditItem]
    warnings: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    integrity_score: float = 0.0
    integrity_status: str = ""
    integrity_layers: dict[str, float | int | str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchIdea:
    title: str
    hypothesis: str
    mechanism: str
    expected_contribution: str
    novelty: int
    feasibility: int
    risk: int
    evaluation: list[str]
    evidence_keys: list[str] = field(default_factory=list)
    evidence_chunks: list[str] = field(default_factory=list)
    gap_alignment: str = ""
    baseline: str = ""
    experiment_sketch: list[str] = field(default_factory=list)
    agent_roles: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return self.novelty + self.feasibility - self.risk


@dataclass(frozen=True)
class ExplorationBranch:
    branch_id: str
    title: str
    status: str
    score: float
    idea_score: int
    evidence_count: int
    risk: int
    rationale: str
    action: str
    evidence_keys: list[str] = field(default_factory=list)
    baseline: str = ""


@dataclass(frozen=True)
class ExplorationMap:
    topic: str
    selected_branch_id: str
    selected_idea_title: str
    branches: list[ExplorationBranch]
    decision: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExperimentCommand:
    name: str
    command: list[str]
    expected_artifacts: list[str] = field(default_factory=list)
    role: str = ""
    comparison_group: str = ""
    adapter_id: str = ""


@dataclass(frozen=True)
class ExperimentPlan:
    idea_title: str
    objective: str
    variables: list[str]
    metrics: list[str]
    protocol: list[str]
    commands: list[ExperimentCommand]
    rationale: str = ""
    baseline: str = ""
    evidence_keys: list[str] = field(default_factory=list)
    template_profile: str = "generic"
    agent_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExperimentResult:
    name: str
    status: str
    metrics: dict[str, float]
    artifacts: list[str]
    stdout: str = ""
    stderr: str = ""
    repeat_index: int = 0
    seed: str = ""
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    duration_seconds: float = 0.0
    validation_issues: list[str] = field(default_factory=list)
    comparison_group: str = ""
    adapter_id: str = ""
    artifact_records: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class BenchmarkCandidate:
    name: str
    domain: str
    benchmark_type: str
    url: str
    access: str
    license_notes: str
    expected_metrics: list[str]
    baselines: list[str]
    integration_steps: list[str]
    risks: list[str]
    status: str = "manual_required"


@dataclass(frozen=True)
class BenchmarkPlan:
    topic: str
    domain: str
    template_profile: str
    candidates: list[BenchmarkCandidate]
    selected_names: list[str]
    required_actions: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Analysis:
    headline: str
    metric_table: list[dict[str, str | float]]
    findings: list[str]
    limitations: list[str]
    next_steps: list[str]


@dataclass(frozen=True)
class MetricComparison:
    metric: str
    candidate_mean: float
    baseline_mean: float
    delta: float
    ci_low: float
    ci_high: float
    candidate_std: float
    baseline_std: float
    effect_size: float | None
    direction: str
    interpretation: str


@dataclass(frozen=True)
class StatisticsReport:
    idea_title: str
    repeats: int
    candidate_name: str
    baseline_name: str
    comparisons: list[MetricComparison]
    warnings: list[str]
    multiplicity: dict[str, Any] = field(default_factory=dict)
    power_analysis: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaperClaimAudit:
    claim: str
    support_level: str
    evidence_keys: list[str]
    result_refs: list[str]
    risk: str


@dataclass(frozen=True)
class PaperReview:
    decision: str
    score: float
    novelty: int
    soundness: int
    evidence_quality: int
    reproducibility: int
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    required_revisions: list[str]
    claim_audit: list[PaperClaimAudit]


@dataclass(frozen=True)
class ClaimTraceabilityItem:
    claim: str
    support_level: str
    decision: str
    citation_status: str
    result_status: str
    runbook_status: str
    evidence_keys: list[str]
    missing_evidence_keys: list[str]
    result_refs: list[str]
    matched_result_refs: list[str]
    issues: list[str]


@dataclass(frozen=True)
class ClaimTraceabilityReport:
    topic: str
    status: str
    traceability_score: float
    total_claims: int
    passed_claims: int
    review_claims: int
    blocked_claims: int
    items: list[ClaimTraceabilityItem]
    blocking_issues: list[str]
    manual_tasks: list[str]
    evidence_inventory: dict[str, int | str | bool]


@dataclass(frozen=True)
class CitationGroundingItem:
    citation_key: str
    marker: str
    decision: str
    grounding_status: str
    claim_window: str
    overlap_score: float
    matched_terms: list[str]
    chunk_ids: list[str]
    support_excerpt: str
    issues: list[str]


@dataclass(frozen=True)
class CitationGroundingReport:
    topic: str
    status: str
    grounding_score: float
    total_citations: int
    passed_citations: int
    review_citations: int
    blocked_citations: int
    items: list[CitationGroundingItem]
    blocking_issues: list[str]
    manual_tasks: list[str]
    evidence_inventory: dict[str, int | str | bool]


@dataclass(frozen=True)
class ResultsPresentationCheck:
    category: str
    item: str
    status: str
    evidence: str
    action: str = ""


@dataclass(frozen=True)
class ResultsPresentationReport:
    topic: str
    status: str
    presentation_score: float
    checks: list[ResultsPresentationCheck]
    blocking_issues: list[str]
    manual_tasks: list[str]
    evidence_inventory: dict[str, int | str | bool]


@dataclass(frozen=True)
class ClaimConsistencyCheck:
    category: str
    item: str
    status: str
    evidence: str
    action: str = ""


@dataclass(frozen=True)
class ClaimConsistencyReport:
    topic: str
    status: str
    consistency_score: float
    checks: list[ClaimConsistencyCheck]
    blocking_issues: list[str]
    manual_tasks: list[str]
    evidence_inventory: dict[str, int | str | bool]


@dataclass(frozen=True)
class RevisionTask:
    task_id: str
    section: str
    severity: str
    issue: str
    action: str
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "planned"


@dataclass(frozen=True)
class PaperRevisionPlan:
    topic: str
    decision: str
    readiness: str
    summary: str
    tasks: list[RevisionTask]
    acceptance_checks: list[str]
    next_iteration_prompt: str


@dataclass(frozen=True)
class PaperRevisionTaskResult:
    task_id: str
    status: str
    action_taken: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PaperRewriteReport:
    topic: str
    source_paper: str
    revised_paper: str
    revision_plan: str
    summary: str
    task_results: list[PaperRevisionTaskResult]
    deferred_tasks: list[str]
    next_checks: list[str]


@dataclass(frozen=True)
class CodeDataAvailabilityItem:
    category: str
    item: str
    status: str
    evidence: str
    action: str = ""


@dataclass(frozen=True)
class CodeDataAvailabilityReport:
    topic: str
    status: str
    ready_for_internal_release: bool
    ready_for_submission_check: bool
    checks: list[CodeDataAvailabilityItem]
    blocking_issues: list[str]
    manual_tasks: list[str]
    code_statement: str
    data_statement: str
    reproduction_statement: str


@dataclass(frozen=True)
class ReleaseMetadataCheck:
    category: str
    item: str
    status: str
    evidence: str
    action: str = ""


@dataclass(frozen=True)
class ReleaseMetadataReport:
    topic: str
    status: str
    metadata: dict[str, str]
    checks: list[ReleaseMetadataCheck]
    recommended_config: dict[str, Any]
    blocking_issues: list[str]
    manual_tasks: list[str]
    code_statement: str
    data_statement: str
    release_statement: str


@dataclass(frozen=True)
class SubmissionCheckItem:
    category: str
    item: str
    status: str
    evidence: str
    action: str = ""


@dataclass(frozen=True)
class SubmissionCheckReport:
    topic: str
    target_venue: str
    status: str
    checks: list[SubmissionCheckItem]
    blocking_issues: list[str]
    manual_tasks: list[str]
    recommended_actions: list[str]


@dataclass(frozen=True)
class SubmissionPackageFile:
    source_path: str
    package_path: str
    status: str
    bytes: int
    sha256: str
    required: bool
    note: str = ""


@dataclass(frozen=True)
class SubmissionPackageReport:
    topic: str
    status: str
    package_dir: str
    package_zip: str
    final_readiness_status: str
    availability_status: str
    submission_status: str
    files: list[SubmissionPackageFile]
    blocking_issues: list[str]
    manual_tasks: list[str]
    recommended_actions: list[str]


@dataclass(frozen=True)
class IterationPlanItem:
    priority: int
    category: str
    action: str
    rationale: str
    owner: str
    target_artifacts: list[str]
    automation: str = "manual"


@dataclass(frozen=True)
class IterationPlanReport:
    topic: str
    status: str
    decision: str
    final_readiness_status: str
    availability_status: str
    submission_status: str
    package_status: str
    execution_mode: str
    benchmark_status: str
    items: list[IterationPlanItem]
    rerun_commands: list[str]
    stop_conditions: list[str]
    carry_forward_notes: list[str]


@dataclass(frozen=True)
class RepairQueueItem:
    task_id: str
    category: str
    severity: str
    source_artifact: str
    trigger_status: str
    evidence: str
    action: str
    target_artifacts: list[str]
    rerun_from: str
    automation: str
    blocks_submission: bool
    blocks_downstream: bool
    status: str = "open"


@dataclass(frozen=True)
class RepairQueueReport:
    topic: str
    status: str
    summary: dict[str, int]
    items: list[RepairQueueItem]
    blocking_issues: list[str]
    manual_tasks: list[str]
    recommended_actions: list[str]


@dataclass(frozen=True)
class FinalReadinessReport:
    topic: str
    status: str
    score_before: float
    score_after: float
    unsupported_before: int
    unsupported_after: int
    weak_before: int
    weak_after: int
    deferred_tasks: list[str]
    blocking_issues: list[str]
    recommendation: str
    next_actions: list[str]
    availability_status: str = ""
    availability_blocking_issues: list[str] = field(default_factory=list)
    availability_manual_tasks: list[str] = field(default_factory=list)
    submission_status: str = ""
    submission_blocking_issues: list[str] = field(default_factory=list)
    submission_manual_tasks: list[str] = field(default_factory=list)
    traceability_status: str = ""
    traceability_blocking_issues: list[str] = field(default_factory=list)
    traceability_manual_tasks: list[str] = field(default_factory=list)
    gate_status: str = ""
    overridden: bool = False


@dataclass(frozen=True)
class ScorecardDimension:
    category: str
    score: float
    weight: float
    status: str
    evidence: list[str]
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchScorecardReport:
    topic: str
    status: str
    overall_score: float
    dimensions: list[ScorecardDimension]
    blocking_issues: list[str]
    manual_tasks: list[str]
    recommendation: str
    next_actions: list[str]
