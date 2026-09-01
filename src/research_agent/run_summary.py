from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


@dataclass(frozen=True)
class RunSummary:
    id: str
    topic: str
    status: str
    stage: str
    out_dir: str
    started_at: str
    updated_at: str
    approved: bool
    cancelled: bool
    diagnostic_category: str
    preflight_status: str
    preflight_fails: int
    preflight_warnings: int
    recovery_category: str
    recovery_blocking_issues: int
    recovery_actions: int
    raw_papers: int
    selected_papers: int
    evidence_confidence_score: float | None
    evidence_confidence_status: str
    citations: int
    ideas: int
    top_idea_score: float | None
    experiment_manager_status: str
    experiment_manager_policy: str
    experiment_manager_next_candidates: int
    experiment_manager_queue_blocked: int
    experiment_manager_queue_human_review: int
    experiment_manager_queue_ready_backlog: int
    experiment_repeats: int
    compared_metrics: int
    candidate_better_metrics: int
    statistics_warnings: int
    seed_intake_status: str
    seed_role_coverage_status: str
    seed_total_entries: int
    seed_curated_papers: int
    seed_missing_roles: int
    seed_required_actions: int
    paper_grade_literature_status: str
    paper_grade_literature_issues: int
    literature_rescue_status: str
    literature_rescue_queries: int
    literature_rescue_execution_status: str
    literature_rescue_execution_closed: int
    literature_rescue_execution_unresolved: int
    literature_rescue_execution_new_unique: int
    result_validation_status: str
    result_validation_blocking_issues: int
    result_validation_warnings: int
    benchmark_schema_status: str
    benchmark_schema_blocking_issues: int
    benchmark_schema_manual_tasks: int
    benchmark_evidence_status: str
    benchmark_evidence_grade: str
    benchmark_statistical_outcome: str
    benchmark_claim_boundary_severity: str
    benchmark_publishable_negative_or_neutral: bool
    benchmark_evidence_blocking_issues: int
    benchmark_evidence_manual_tasks: int
    adapter_paper_grade_status: str
    adapter_paper_grade_issues: int
    failure_analysis_status: str
    failed_runs: int
    negative_metrics: int
    uncertain_metrics: int
    claim_preflight_status: str
    claim_preflight_mode: str
    claim_preflight_blocking_issues: int
    claim_preflight_warnings: int
    claim_traceability_status: str
    claim_traceability_score: float | None
    claim_traceability_blocked_claims: int
    claim_traceability_blocking_issues: int
    claim_traceability_manual_tasks: int
    claim_consistency_status: str
    claim_consistency_score: float | None
    claim_consistency_blocking_issues: int
    claim_consistency_manual_tasks: int
    paper_review_score: float | None
    paper_review_decision: str
    required_revisions: int
    final_readiness_status: str
    final_score_after: float | None
    unsupported_after: int
    weak_after: int
    deferred_tasks: int
    blocking_issues: int
    availability_status: str
    availability_manual_tasks: int
    availability_blocking_issues: int
    submission_status: str
    submission_manual_tasks: int
    submission_blocking_issues: int
    package_status: str
    package_manual_tasks: int
    package_blocking_issues: int
    scorecard_status: str
    scorecard_overall_score: float | None
    scorecard_manual_tasks: int
    scorecard_blocking_issues: int
    iteration_status: str
    iteration_items: int
    repair_queue_status: str
    repair_queue_items: int
    repair_queue_block: int
    repair_queue_high: int
    repair_queue_medium: int
    repair_queue_blocks_submission: int
    repair_resume_status: str
    repair_resume_applied: bool
    repair_resume_rerun_from: str
    repair_resume_items: int
    repair_resume_retrieval_tasks: int
    repair_resume_review_reapproval_required: bool
    repair_resume_execution_reapproval_required: bool
    run_integrity_status: str
    run_integrity_pass: int
    run_integrity_warnings: int
    run_integrity_blocking_issues: int
    final_handoff_status: str
    final_handoff_blocking_issues: int
    final_handoff_manual_tasks: int
    final_handoff_package_has_integrity_audit: bool
    final_handoff_package_zip_valid: bool | None
    agent_trajectory_status: str
    agent_trajectory_pass: int
    agent_trajectory_warn: int
    agent_trajectory_block: int
    agent_trajectory_not_started: int
    agent_trajectory_blocking_issues: int
    agent_trajectory_manual_tasks: int
    agent_trajectory_last_event: str
    agent_trajectory_backfilled_events: int
    agent_observability_status: str
    agent_observability_manifest_events: int
    agent_observability_manifest_artifacts: int
    agent_observability_llm_failed_calls: int
    agent_observability_experiment_runs: int
    agent_observability_repair_queue_status: str
    agent_observability_blocking_issues: int
    agent_observability_manual_tasks: int
    agent_observability_warnings: int
    agent_observability_call_pressure: float
    agent_observability_prompt_pressure: float
    run_economics_status: str
    llm_total_calls: int
    llm_input_tokens_estimated: int
    llm_output_tokens_estimated: int
    llm_duration_seconds: float
    llm_estimated_cost_usd: float | None
    llm_budget_call_utilization: float
    llm_budget_prompt_utilization: float
    run_economics_manual_tasks: int
    run_economics_blocking_issues: int
    artifact_count: int
    readiness_score: float


@dataclass(frozen=True)
class RunDashboard:
    generated_at: str
    runs_dir: str
    total_runs: int
    status_counts: dict[str, int]
    runs: list[RunSummary]


STAGE_ORDER = [
    "queued",
    "started",
    "research_plan_completed",
    "literature_review_completed",
    "awaiting_review_approval",
    "review_revision_requested",
    "review_approved",
    "ideation_completed",
    "exploration_map_completed",
    "experiment_manager_completed",
    "experiment_plan_completed",
    "experiments_completed",
    "analysis_completed",
    "paper_review_completed",
    "revision_plan_completed",
    "paper_revision_completed",
    "revision_response_audit_completed",
    "final_readiness_completed",
    "submission_package_completed",
    "iteration_plan_completed",
    "scorecard_completed",
    "final_handoff_completed",
    "completed",
]


def build_run_dashboard(runs_dir: Path, limit: int = 100) -> RunDashboard:
    runs = [_summarize_run(path) for path in sorted(_run_dirs(runs_dir))]
    runs = [run for run in runs if run is not None]
    runs = sorted(runs, key=lambda item: (item.readiness_score, item.updated_at, item.id), reverse=True)
    if limit > 0:
        runs = runs[:limit]
    status_counts: dict[str, int] = {}
    for run in runs:
        status_counts[run.status] = status_counts.get(run.status, 0) + 1
    return RunDashboard(
        generated_at=_utc_now(),
        runs_dir=str(runs_dir),
        total_runs=len(runs),
        status_counts=status_counts,
        runs=runs,
    )


def write_run_dashboard(dashboard: RunDashboard, out_dir: Path, basename: str = "runs-summary") -> tuple[Path, Path]:
    json_path = out_dir / f"{basename}.json"
    md_path = out_dir / f"{basename}.md"
    write_json(json_path, dashboard)
    write_text(md_path, render_run_dashboard_markdown(dashboard))
    return json_path, md_path


def render_run_dashboard_markdown(dashboard: RunDashboard) -> str:
    lines = [
        "# Runs 对比",
        "",
        f"- 生成时间：{dashboard.generated_at}",
        f"- Runs 目录：{dashboard.runs_dir}",
        f"- 纳入 run：{dashboard.total_runs}",
        f"- 状态分布：{', '.join(f'{key}={value}' for key, value in sorted(dashboard.status_counts.items())) or '-'}",
        "",
        "## 排行榜",
        "| Run | 状态 | 阶段 | 预检 | 恢复 | 证据 | Seed | Ideas | 实验管理 | 实验 | LLM 资源 | 补检索 | 验证 | Benchmark Schema | 论文级 | 失败分析 | 复核 | 最终 Gate | 代码/数据 | 投稿检查 | 投稿包 | Scorecard | 下一轮 | 修复队列 | 修复恢复 | 轨迹 | 可观测性 | 完整性 | 交付 | 阻断 | Readiness |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    if not dashboard.runs:
        lines.append("| 无 run | - | - | - | - | 0 | - | 0 | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | 0 | 0 |")
    for run in dashboard.runs:
        experiment = f"{run.candidate_better_metrics}/{run.compared_metrics}" if run.compared_metrics else "-"
        review = f"{run.paper_review_score:.1f} {run.paper_review_decision}" if run.paper_review_score is not None else "-"
        final_gate = _final_gate_cell(run)
        blocking = _blocking_count(run)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(run.id),
                    run.status,
                    run.stage,
                    _cell(_preflight_cell(run)),
                    _cell(_recovery_cell(run)),
                    _cell(_evidence_cell(run)),
                    _cell(_seed_intake_cell(run)),
                    str(run.ideas),
                    _cell(_experiment_manager_cell(run)),
                    experiment,
                    _cell(_run_economics_cell(run)),
                    _cell(_literature_rescue_cell(run)),
                    _cell(_result_validation_cell(run)),
                    _cell(_benchmark_schema_cell(run)),
                    _cell(_paper_grade_cell(run)),
                    _cell(_failure_analysis_cell(run)),
                    _cell(review),
                    _cell(final_gate),
                    _cell(_availability_cell(run)),
                    _cell(_submission_cell(run)),
                    _cell(_package_cell(run)),
                    _cell(_scorecard_cell(run)),
                    _cell(_iteration_cell(run)),
                    _cell(_repair_queue_cell(run)),
                    _cell(_repair_resume_cell(run)),
                    _cell(_agent_trajectory_cell(run)),
                    _cell(_agent_observability_cell(run)),
                    _cell(_run_integrity_cell(run)),
                    _cell(_final_handoff_cell(run)),
                    str(blocking),
                    f"{run.readiness_score:.2f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 字段说明",
            "- 预检：读取 `00-preflight.json`，显示启动前配置检查状态、失败项和警告项。",
            "- 恢复：读取 `run-recovery-plan.json`，显示失败、取消、退回或 checkpoint resume 的恢复类别。",
            "- 证据：优先使用质量筛选后的文献数，缺失时使用 citation chunk 数；若存在 `confidence_status`，同时显示整批证据置信度。",
            "- Seed：读取 `01-seed-paper-intake.json`，显示人工种子文献 intake 状态、进入 curated context 的角色覆盖、curated/total 数量和缺失角色数。",
            "- 实验管理：读取 `02-experiment-manager.json`，显示分支管理状态、执行策略和下一轮候选数。",
            "- 实验：candidate_better_metrics / compared_metrics，仅代表当前统计产物中的方向计数。",
            "- LLM 资源：读取 `13-run-economics-audit.json`，显示调用数、估算 token、耗时、可选美元成本和预算压力。",
            "- 补检索：读取 `01-literature-rescue-plan.json` 和 `01-literature-rescue-execution.json`，显示弱文献修复计划、执行状态、未闭环 query、新增去重候选数。",
            "- 验证：读取 `04-result-validation.json`，显示实验结果有效性验证状态和阻断/警告数量。",
            "- Benchmark Schema：读取 `04-benchmark-result-schema-audit.json`，显示真实 benchmark 结果 schema、adapter provenance 和产物闭环状态。",
            "- 论文级：读取 `01-literature-gate-decision.json`、`04-benchmark-evidence-audit.json`、`04-claim-boundary-preflight.json` 和 `10-claim-consistency.json`，显示 paper-grade literature、真实 benchmark/adapter paper-grade 与 claim 边界状态。",
            "- 失败分析：读取 `04-failure-analysis.json`，显示失败运行、负向指标和不确定指标数量。",
            "- 最终 Gate：优先使用 `10-final-readiness.json`；缺失时显示 `07-paper-review` 的初始复核。",
            "- 代码/数据：优先读取 `10-code-data-availability.json`；若缺失则读取 `10-final-readiness.json` 中的 availability 字段。",
            "- 投稿检查：优先读取 `10-submission-check.json`；若缺失则读取 `10-final-readiness.json` 中的 submission 字段。",
            "- 投稿包：读取 `11-submission-package.json`，显示最终可下载包的阻断和人工待办。",
            "- Scorecard：读取 `13-research-scorecard.json`，显示研究分数卡状态、总分、阻断项和人工待办。",
            "- 下一轮：读取 `12-next-iteration-plan.json`，显示自动生成的下一轮决策。",
            "- 修复队列：读取 `12-repair-queue.json`，显示 block/high/medium 修复项和是否阻断投稿。",
            "- 修复恢复：读取 `12-repair-resume-plan.json`，显示 repair-resume 是否已应用、重跑入口、检索修复任务和是否需要重新人工 gate。",
            "- 轨迹：读取 `13-agent-trajectory.json`，显示阶段 pass/warn/block/not_started 计数、人工待办和最终 manifest 事件。",
            "- 可观测性：读取 `13-agent-observability-audit.json`，显示 manifest 事件/产物、LLM 失败、实验 run、repair queue、阻断/待办/警告和预算压力。",
            "- 完整性：读取 `14-run-integrity-audit.json`，显示最终产物完整性、manifest/hash、人工 gate、LLM ledger、投稿包和密钥落盘审计状态。",
            "- 交付：读取 `14-final-handoff.json`，显示 ZIP、scorecard、完整性审计和包内完整性审计快照的最终交付判定。",
            "- 阻断：预检失败、恢复阻断、seed intake/角色覆盖人工处理、paper-grade literature/benchmark/claim 缺口、deferred tasks、blocking issues、修订后 unsupported claim、benchmark schema 待办、代码/数据待办、投稿格式待办、投稿包、scorecard 待办、repair queue、agent 轨迹、可观测性审计、完整性审计和最终交付阻断的合计。",
            "- Readiness：流程进度、文献证据、实验统计、复核分和最终 gate 的综合排序分，不等同于科学结论。",
        ]
    )
    return "\n".join(lines)


def _summarize_run(run_dir: Path) -> RunSummary | None:
    state = _read_json(run_dir / "state.json")
    if not isinstance(state, dict):
        return None
    manifest = _read_json(run_dir / "run-manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    quality = _read_json(run_dir / "01-literature-quality.json")
    quality = quality if isinstance(quality, dict) else {}
    literature_gate = _read_json(run_dir / "01-literature-gate-decision.json")
    literature_gate = literature_gate if isinstance(literature_gate, dict) else {}
    context = _read_json(run_dir / "01-context.json")
    context = context if isinstance(context, dict) else {}
    ideas = _read_json(run_dir / "02-ideas.json")
    ideas = ideas if isinstance(ideas, list) else []
    experiment_manager = _read_json(run_dir / "02-experiment-manager.json")
    experiment_manager = experiment_manager if isinstance(experiment_manager, dict) else {}
    statistics = _read_json(run_dir / "04-statistics.json")
    statistics = statistics if isinstance(statistics, dict) else {}
    result_validation = _read_json(run_dir / "04-result-validation.json")
    result_validation = result_validation if isinstance(result_validation, dict) else {}
    benchmark_schema = _read_json(run_dir / "04-benchmark-result-schema-audit.json")
    benchmark_schema = benchmark_schema if isinstance(benchmark_schema, dict) else {}
    benchmark_evidence = _read_json(run_dir / "04-benchmark-evidence-audit.json")
    benchmark_evidence = benchmark_evidence if isinstance(benchmark_evidence, dict) else {}
    claim_preflight = _read_json(run_dir / "04-claim-boundary-preflight.json")
    claim_preflight = claim_preflight if isinstance(claim_preflight, dict) else {}
    claim_traceability = _read_json(run_dir / "10-claim-traceability.json")
    claim_traceability = claim_traceability if isinstance(claim_traceability, dict) else {}
    failure_analysis = _read_json(run_dir / "04-failure-analysis.json")
    failure_analysis = failure_analysis if isinstance(failure_analysis, dict) else {}
    literature_rescue = _read_json(run_dir / "01-literature-rescue-plan.json")
    literature_rescue = literature_rescue if isinstance(literature_rescue, dict) else {}
    literature_rescue_execution = _read_json(run_dir / "01-literature-rescue-execution.json")
    literature_rescue_execution = literature_rescue_execution if isinstance(literature_rescue_execution, dict) else {}
    seed_intake = _read_json(run_dir / "01-seed-paper-intake.json")
    seed_intake = seed_intake if isinstance(seed_intake, dict) else {}
    review = _read_json(run_dir / "07-paper-review.json")
    review = review if isinstance(review, dict) else {}
    final_readiness = _read_json(run_dir / "10-final-readiness.json")
    final_readiness = final_readiness if isinstance(final_readiness, dict) else {}
    claim_consistency = _read_json(run_dir / "10-claim-consistency.json")
    claim_consistency = claim_consistency if isinstance(claim_consistency, dict) else {}
    availability = _read_json(run_dir / "10-code-data-availability.json")
    availability = availability if isinstance(availability, dict) else {}
    submission = _read_json(run_dir / "10-submission-check.json")
    submission = submission if isinstance(submission, dict) else {}
    package = _read_json(run_dir / "11-submission-package.json")
    package = package if isinstance(package, dict) else {}
    scorecard = _read_json(run_dir / "13-research-scorecard.json")
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    iteration = _read_json(run_dir / "12-next-iteration-plan.json")
    iteration = iteration if isinstance(iteration, dict) else {}
    repair_queue = _read_json(run_dir / "12-repair-queue.json")
    repair_queue = repair_queue if isinstance(repair_queue, dict) else {}
    repair_resume = _read_json(run_dir / "12-repair-resume-plan.json")
    repair_resume = repair_resume if isinstance(repair_resume, dict) else {}
    run_integrity = _read_json(run_dir / "14-run-integrity-audit.json")
    run_integrity = run_integrity if isinstance(run_integrity, dict) else {}
    final_handoff = _read_json(run_dir / "14-final-handoff.json")
    final_handoff = final_handoff if isinstance(final_handoff, dict) else {}
    agent_trajectory = _read_json(run_dir / "13-agent-trajectory.json")
    agent_trajectory = agent_trajectory if isinstance(agent_trajectory, dict) else {}
    agent_observability = _read_json(run_dir / "13-agent-observability-audit.json")
    agent_observability = agent_observability if isinstance(agent_observability, dict) else {}
    run_economics = _read_json(run_dir / "13-run-economics-audit.json")
    run_economics = run_economics if isinstance(run_economics, dict) else {}
    preflight = _read_json(run_dir / "00-preflight.json")
    preflight = preflight if isinstance(preflight, dict) else {}
    recovery = _read_json(run_dir / "run-recovery-plan.json")
    recovery = recovery if isinstance(recovery, dict) else {}
    diagnostic = _read_json(run_dir / "run-diagnostics.json")
    diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
    cancel = _read_json(run_dir / "cancel.json")
    cancel = cancel if isinstance(cancel, dict) else {}
    approval = _read_json(run_dir / "approval.json")
    approval = approval if isinstance(approval, dict) else {}

    stage = str(state.get("stage") or "unknown")
    status = _status(stage, diagnostic, cancel, manifest)
    comparisons = [item for item in statistics.get("comparisons", []) if isinstance(item, dict)]
    candidate_better = sum(1 for item in comparisons if item.get("direction") == "candidate_better")
    top_idea_score = _top_idea_score(ideas)
    paper_score = _safe_float_or_none(review.get("score"))
    final_score_after = _safe_float_or_none(final_readiness.get("score_after"))
    selected_papers = _safe_int(quality.get("selected_papers"))
    evidence_confidence_score = _safe_float_or_none(quality.get("confidence_score"))
    evidence_confidence_status = str(quality.get("confidence_status") or "")
    citations = len(context.get("citations", [])) if isinstance(context.get("citations"), list) else 0
    artifact_count = len(manifest.get("artifacts", [])) if isinstance(manifest.get("artifacts"), list) else _artifact_count(run_dir)
    availability_status = str(availability.get("status") or final_readiness.get("availability_status") or "")
    availability_manual_tasks = _availability_list_count(availability, final_readiness, "manual_tasks", "availability_manual_tasks")
    availability_blocking_issues = _availability_list_count(
        availability,
        final_readiness,
        "blocking_issues",
        "availability_blocking_issues",
    )
    submission_status = str(submission.get("status") or final_readiness.get("submission_status") or "")
    submission_manual_tasks = _availability_list_count(submission, final_readiness, "manual_tasks", "submission_manual_tasks")
    submission_blocking_issues = _availability_list_count(
        submission,
        final_readiness,
        "blocking_issues",
        "submission_blocking_issues",
    )
    package_status = str(package.get("status") or "")
    package_manual_tasks = len(package.get("manual_tasks", [])) if isinstance(package.get("manual_tasks"), list) else 0
    package_blocking_issues = len(package.get("blocking_issues", [])) if isinstance(package.get("blocking_issues"), list) else 0
    scorecard_status = str(scorecard.get("status") or "")
    scorecard_overall_score = _safe_float_or_none(scorecard.get("overall_score"))
    scorecard_manual_tasks = len(scorecard.get("manual_tasks", [])) if isinstance(scorecard.get("manual_tasks"), list) else 0
    scorecard_blocking_issues = len(scorecard.get("blocking_issues", [])) if isinstance(scorecard.get("blocking_issues"), list) else 0
    iteration_status = str(iteration.get("status") or "")
    iteration_items = len(iteration.get("items", [])) if isinstance(iteration.get("items"), list) else 0
    repair_queue_status = str(repair_queue.get("status") or "")
    repair_queue_summary = repair_queue.get("summary") if isinstance(repair_queue.get("summary"), dict) else {}
    repair_resume_status = str(repair_resume.get("status") or "")
    run_integrity_status = str(run_integrity.get("status") or "")
    run_integrity_summary = run_integrity.get("summary") if isinstance(run_integrity.get("summary"), dict) else {}
    final_handoff_status = str(final_handoff.get("status") or "")
    agent_trajectory_summary = agent_trajectory.get("summary") if isinstance(agent_trajectory.get("summary"), dict) else {}
    agent_trajectory_counts = agent_trajectory_summary.get("phase_counts") if isinstance(agent_trajectory_summary.get("phase_counts"), dict) else {}
    agent_observability_summary = agent_observability.get("summary") if isinstance(agent_observability.get("summary"), dict) else {}
    agent_observability_budget = agent_observability.get("budget") if isinstance(agent_observability.get("budget"), dict) else {}
    economics_summary = run_economics.get("summary") if isinstance(run_economics.get("summary"), dict) else {}
    economics_budget = run_economics.get("budget") if isinstance(run_economics.get("budget"), dict) else {}
    preflight_checks = [item for item in preflight.get("checks", []) if isinstance(item, dict)]
    recovery_blocking_issues = len(recovery.get("blocking_issues", [])) if isinstance(recovery.get("blocking_issues"), list) else 0
    recovery_actions = len(recovery.get("recommended_actions", [])) if isinstance(recovery.get("recommended_actions"), list) else 0
    failure_summary = failure_analysis.get("summary") if isinstance(failure_analysis.get("summary"), dict) else {}
    seed_missing_roles = seed_intake.get("missing_curated_seed_roles", [])
    paper_grade_literature = literature_gate.get("paper_grade_literature") if isinstance(literature_gate.get("paper_grade_literature"), dict) else {}
    paper_grade_literature_issues = paper_grade_literature.get("issues", []) if isinstance(paper_grade_literature.get("issues"), list) else []
    manager_queue_summary = experiment_manager.get("queue_summary") if isinstance(experiment_manager.get("queue_summary"), dict) else {}
    summary = RunSummary(
        id=run_dir.name,
        topic=str(state.get("topic") or manifest.get("topic") or run_dir.name),
        status=status,
        stage=stage,
        out_dir=str(run_dir),
        started_at=str(manifest.get("started_at") or ""),
        updated_at=str(state.get("updated_at") or manifest.get("updated_at") or ""),
        approved=approval.get("approved") is True,
        cancelled=cancel.get("cancelled") is True,
        diagnostic_category=str(diagnostic.get("category") or ""),
        preflight_status=str(preflight.get("status") or ""),
        preflight_fails=sum(1 for item in preflight_checks if item.get("status") == "fail"),
        preflight_warnings=sum(1 for item in preflight_checks if item.get("status") == "warn"),
        recovery_category=str(recovery.get("category") or ""),
        recovery_blocking_issues=recovery_blocking_issues,
        recovery_actions=recovery_actions,
        raw_papers=_safe_int(quality.get("total_papers")),
        selected_papers=selected_papers,
        evidence_confidence_score=evidence_confidence_score,
        evidence_confidence_status=evidence_confidence_status,
        citations=citations,
        ideas=len(ideas),
        top_idea_score=top_idea_score,
        experiment_manager_status=str(experiment_manager.get("status") or ""),
        experiment_manager_policy=str(experiment_manager.get("execution_policy") or ""),
        experiment_manager_next_candidates=len(experiment_manager.get("next_expansion_candidates", [])) if isinstance(experiment_manager.get("next_expansion_candidates"), list) else 0,
        experiment_manager_queue_blocked=_safe_int(manager_queue_summary.get("blocked")),
        experiment_manager_queue_human_review=_safe_int(manager_queue_summary.get("human_review")),
        experiment_manager_queue_ready_backlog=_safe_int(manager_queue_summary.get("ready_backlog")),
        experiment_repeats=_safe_int(statistics.get("repeats")),
        compared_metrics=len(comparisons),
        candidate_better_metrics=candidate_better,
        statistics_warnings=len(statistics.get("warnings", [])) if isinstance(statistics.get("warnings"), list) else 0,
        seed_intake_status=str(seed_intake.get("status") or ""),
        seed_role_coverage_status=str(seed_intake.get("role_coverage_status") or ""),
        seed_total_entries=_safe_int(seed_intake.get("total_seed_entries")),
        seed_curated_papers=_safe_int(seed_intake.get("curated_seed_papers")),
        seed_missing_roles=len(seed_missing_roles) if isinstance(seed_missing_roles, list) else 0,
        seed_required_actions=len(seed_intake.get("required_actions", [])) if isinstance(seed_intake.get("required_actions"), list) else 0,
        paper_grade_literature_status=str(paper_grade_literature.get("status") or ""),
        paper_grade_literature_issues=len(paper_grade_literature_issues),
        literature_rescue_status=str(literature_rescue.get("status") or ""),
        literature_rescue_queries=len(literature_rescue.get("rescue_queries", [])) if isinstance(literature_rescue.get("rescue_queries"), list) else 0,
        literature_rescue_execution_status=str(literature_rescue_execution.get("status") or ""),
        literature_rescue_execution_closed=_safe_int(literature_rescue_execution.get("closed_query_outcomes")),
        literature_rescue_execution_unresolved=_safe_int(literature_rescue_execution.get("unresolved_query_outcomes")),
        literature_rescue_execution_new_unique=_safe_int(literature_rescue_execution.get("new_unique_papers")),
        result_validation_status=str(result_validation.get("status") or ""),
        result_validation_blocking_issues=len(result_validation.get("blocking_issues", [])) if isinstance(result_validation.get("blocking_issues"), list) else 0,
        result_validation_warnings=len(result_validation.get("warnings", [])) if isinstance(result_validation.get("warnings"), list) else 0,
        benchmark_schema_status=str(benchmark_schema.get("status") or ""),
        benchmark_schema_blocking_issues=len(benchmark_schema.get("blocking_issues", [])) if isinstance(benchmark_schema.get("blocking_issues"), list) else 0,
        benchmark_schema_manual_tasks=len(benchmark_schema.get("manual_tasks", [])) if isinstance(benchmark_schema.get("manual_tasks"), list) else 0,
        benchmark_evidence_status=str(benchmark_evidence.get("status") or ""),
        benchmark_evidence_grade=str(benchmark_evidence.get("evidence_grade") or ""),
        benchmark_statistical_outcome=str(benchmark_evidence.get("statistical_outcome") or ""),
        benchmark_claim_boundary_severity=str(benchmark_evidence.get("claim_boundary_severity") or ""),
        benchmark_publishable_negative_or_neutral=benchmark_evidence.get("publishable_negative_or_neutral_result") is True,
        benchmark_evidence_blocking_issues=len(benchmark_evidence.get("blocking_issues", [])) if isinstance(benchmark_evidence.get("blocking_issues"), list) else 0,
        benchmark_evidence_manual_tasks=len(benchmark_evidence.get("manual_tasks", [])) if isinstance(benchmark_evidence.get("manual_tasks"), list) else 0,
        adapter_paper_grade_status=str(benchmark_evidence.get("adapter_paper_grade_status") or ""),
        adapter_paper_grade_issues=len(benchmark_evidence.get("adapter_paper_grade_issues", [])) if isinstance(benchmark_evidence.get("adapter_paper_grade_issues"), list) else 0,
        failure_analysis_status=str(failure_analysis.get("status") or ""),
        failed_runs=_safe_int(failure_summary.get("failed_runs")),
        negative_metrics=_safe_int(failure_summary.get("negative_metrics")),
        uncertain_metrics=_safe_int(failure_summary.get("uncertain_metrics")),
        claim_preflight_status=str(claim_preflight.get("status") or ""),
        claim_preflight_mode=str(claim_preflight.get("writing_mode") or ""),
        claim_preflight_blocking_issues=len(claim_preflight.get("blocking_issues", [])) if isinstance(claim_preflight.get("blocking_issues"), list) else 0,
        claim_preflight_warnings=len(claim_preflight.get("warnings", [])) if isinstance(claim_preflight.get("warnings"), list) else 0,
        claim_traceability_status=str(claim_traceability.get("status") or ""),
        claim_traceability_score=_safe_float_or_none(claim_traceability.get("traceability_score")),
        claim_traceability_blocked_claims=_safe_int(claim_traceability.get("blocked_claims")),
        claim_traceability_blocking_issues=len(claim_traceability.get("blocking_issues", [])) if isinstance(claim_traceability.get("blocking_issues"), list) else 0,
        claim_traceability_manual_tasks=len(claim_traceability.get("manual_tasks", [])) if isinstance(claim_traceability.get("manual_tasks"), list) else 0,
        claim_consistency_status=str(claim_consistency.get("status") or ""),
        claim_consistency_score=_safe_float_or_none(claim_consistency.get("consistency_score")),
        claim_consistency_blocking_issues=len(claim_consistency.get("blocking_issues", [])) if isinstance(claim_consistency.get("blocking_issues"), list) else 0,
        claim_consistency_manual_tasks=len(claim_consistency.get("manual_tasks", [])) if isinstance(claim_consistency.get("manual_tasks"), list) else 0,
        paper_review_score=paper_score,
        paper_review_decision=str(review.get("decision") or ""),
        required_revisions=len(review.get("required_revisions", [])) if isinstance(review.get("required_revisions"), list) else 0,
        final_readiness_status=str(final_readiness.get("status") or ""),
        final_score_after=final_score_after,
        unsupported_after=_safe_int(final_readiness.get("unsupported_after")),
        weak_after=_safe_int(final_readiness.get("weak_after")),
        deferred_tasks=len(final_readiness.get("deferred_tasks", [])) if isinstance(final_readiness.get("deferred_tasks"), list) else 0,
        blocking_issues=len(final_readiness.get("blocking_issues", [])) if isinstance(final_readiness.get("blocking_issues"), list) else 0,
        availability_status=availability_status,
        availability_manual_tasks=availability_manual_tasks,
        availability_blocking_issues=availability_blocking_issues,
        submission_status=submission_status,
        submission_manual_tasks=submission_manual_tasks,
        submission_blocking_issues=submission_blocking_issues,
        package_status=package_status,
        package_manual_tasks=package_manual_tasks,
        package_blocking_issues=package_blocking_issues,
        scorecard_status=scorecard_status,
        scorecard_overall_score=scorecard_overall_score,
        scorecard_manual_tasks=scorecard_manual_tasks,
        scorecard_blocking_issues=scorecard_blocking_issues,
        iteration_status=iteration_status,
        iteration_items=iteration_items,
        repair_queue_status=repair_queue_status,
        repair_queue_items=len(repair_queue.get("items", [])) if isinstance(repair_queue.get("items"), list) else _safe_int(repair_queue_summary.get("total")),
        repair_queue_block=_safe_int(repair_queue_summary.get("block")),
        repair_queue_high=_safe_int(repair_queue_summary.get("high")),
        repair_queue_medium=_safe_int(repair_queue_summary.get("medium")),
        repair_queue_blocks_submission=_safe_int(repair_queue_summary.get("blocks_submission")),
        repair_resume_status=repair_resume_status,
        repair_resume_applied=repair_resume.get("applied") is True,
        repair_resume_rerun_from=str(repair_resume.get("rerun_from") or ""),
        repair_resume_items=len(repair_resume.get("repair_items", [])) if isinstance(repair_resume.get("repair_items"), list) else 0,
        repair_resume_retrieval_tasks=len(repair_resume.get("retrieval_repair_tasks", [])) if isinstance(repair_resume.get("retrieval_repair_tasks"), list) else 0,
        repair_resume_review_reapproval_required=repair_resume.get("review_reapproval_required") is True,
        repair_resume_execution_reapproval_required=repair_resume.get("execution_reapproval_required") is True,
        run_integrity_status=run_integrity_status,
        run_integrity_pass=_safe_int(run_integrity_summary.get("pass")),
        run_integrity_warnings=len(run_integrity.get("warnings", [])) if isinstance(run_integrity.get("warnings"), list) else _safe_int(run_integrity_summary.get("warn")),
        run_integrity_blocking_issues=len(run_integrity.get("blocking_issues", [])) if isinstance(run_integrity.get("blocking_issues"), list) else _safe_int(run_integrity_summary.get("block")),
        final_handoff_status=final_handoff_status,
        final_handoff_blocking_issues=len(final_handoff.get("blocking_issues", [])) if isinstance(final_handoff.get("blocking_issues"), list) else 0,
        final_handoff_manual_tasks=len(final_handoff.get("manual_tasks", [])) if isinstance(final_handoff.get("manual_tasks"), list) else 0,
        final_handoff_package_has_integrity_audit=final_handoff.get("package_has_integrity_audit") is True,
        final_handoff_package_zip_valid=final_handoff.get("package_zip_valid") if isinstance(final_handoff.get("package_zip_valid"), bool) else None,
        agent_trajectory_status=str(agent_trajectory.get("status") or ""),
        agent_trajectory_pass=_safe_int(agent_trajectory_counts.get("pass")),
        agent_trajectory_warn=_safe_int(agent_trajectory_counts.get("warn")),
        agent_trajectory_block=_safe_int(agent_trajectory_counts.get("block")),
        agent_trajectory_not_started=_safe_int(agent_trajectory_counts.get("not_started")),
        agent_trajectory_blocking_issues=_trajectory_count(agent_trajectory, agent_trajectory_summary, "blocking_issues"),
        agent_trajectory_manual_tasks=_trajectory_count(agent_trajectory, agent_trajectory_summary, "manual_tasks"),
        agent_trajectory_last_event=str(agent_trajectory_summary.get("last_event") or ""),
        agent_trajectory_backfilled_events=_safe_int(agent_trajectory_summary.get("backfilled_events")),
        agent_observability_status=str(agent_observability.get("status") or ""),
        agent_observability_manifest_events=_safe_int(agent_observability_summary.get("manifest_events")),
        agent_observability_manifest_artifacts=_safe_int(agent_observability_summary.get("manifest_artifacts")),
        agent_observability_llm_failed_calls=_safe_int(agent_observability_summary.get("llm_failed_calls")),
        agent_observability_experiment_runs=_safe_int(agent_observability_summary.get("experiment_runs")),
        agent_observability_repair_queue_status=str(agent_observability_summary.get("repair_queue_status") or ""),
        agent_observability_blocking_issues=len(agent_observability.get("blocking_issues", [])) if isinstance(agent_observability.get("blocking_issues"), list) else 0,
        agent_observability_manual_tasks=len(agent_observability.get("manual_tasks", [])) if isinstance(agent_observability.get("manual_tasks"), list) else 0,
        agent_observability_warnings=len(agent_observability.get("warnings", [])) if isinstance(agent_observability.get("warnings"), list) else 0,
        agent_observability_call_pressure=_safe_float(agent_observability_budget.get("call_utilization")),
        agent_observability_prompt_pressure=_safe_float(agent_observability_budget.get("prompt_utilization")),
        run_economics_status=str(run_economics.get("status") or ""),
        llm_total_calls=_safe_int(economics_summary.get("total_calls")),
        llm_input_tokens_estimated=_safe_int(economics_summary.get("input_tokens_estimated")),
        llm_output_tokens_estimated=_safe_int(economics_summary.get("output_tokens_estimated")),
        llm_duration_seconds=_safe_float(economics_summary.get("total_duration_seconds")),
        llm_estimated_cost_usd=_safe_float_or_none(economics_summary.get("estimated_cost_usd")),
        llm_budget_call_utilization=_safe_float(economics_budget.get("call_utilization")),
        llm_budget_prompt_utilization=_safe_float(economics_budget.get("prompt_utilization")),
        run_economics_manual_tasks=len(run_economics.get("manual_tasks", [])) if isinstance(run_economics.get("manual_tasks"), list) else 0,
        run_economics_blocking_issues=len(run_economics.get("blocking_issues", [])) if isinstance(run_economics.get("blocking_issues"), list) else 0,
        artifact_count=artifact_count,
        readiness_score=0.0,
    )
    return _with_readiness(summary)


def _with_readiness(summary: RunSummary) -> RunSummary:
    progress = _stage_progress(summary.stage) * 4.0
    evidence = min(max(summary.selected_papers or summary.citations, 0), 10) / 10.0 * 2.0
    review_score = summary.final_score_after if summary.final_score_after is not None else summary.paper_review_score
    review = (review_score or 0.0) / 10.0 * 8.0
    experiment = (summary.candidate_better_metrics / summary.compared_metrics * 4.0) if summary.compared_metrics else 0.0
    idea = min(max(summary.top_idea_score or 0.0, 0.0), 15.0) / 15.0 * 2.0
    penalty = min(summary.statistics_warnings * 0.4 + summary.required_revisions * 0.15, 3.0)
    penalty += _final_gate_penalty(summary)
    penalty += _audit_penalty(summary)
    if summary.status == "failed":
        penalty += 4.0
    if summary.status == "cancelled":
        penalty += 2.0
    if summary.diagnostic_category:
        penalty += 1.0
    penalty += _preflight_penalty(summary)
    penalty += _recovery_penalty(summary)
    penalty += _evidence_confidence_penalty(summary)
    penalty += _paper_grade_penalty(summary)
    penalty += _iteration_penalty(summary.iteration_status)
    penalty += _scorecard_penalty(summary)
    penalty += _run_economics_penalty(summary)
    score = max(0.0, min(20.0, progress + evidence + review + experiment + idea - penalty))
    return RunSummary(**{**summary.__dict__, "readiness_score": round(score, 3)})


def _preflight_cell(run: RunSummary) -> str:
    if not run.preflight_status:
        return "-"
    parts = [run.preflight_status]
    if run.preflight_fails:
        parts.append(f"F{run.preflight_fails}")
    if run.preflight_warnings:
        parts.append(f"W{run.preflight_warnings}")
    return " ".join(parts)


def _evidence_cell(run: RunSummary) -> str:
    evidence = run.selected_papers or run.citations
    if not run.evidence_confidence_status:
        return str(evidence)
    score = f" {run.evidence_confidence_score:.2f}" if run.evidence_confidence_score is not None else ""
    return f"{evidence} {run.evidence_confidence_status}{score}"


def _seed_intake_cell(run: RunSummary) -> str:
    if not run.seed_intake_status and not run.seed_role_coverage_status:
        return "-"
    parts = [run.seed_intake_status or "-"]
    if run.seed_role_coverage_status and run.seed_role_coverage_status != run.seed_intake_status:
        parts.append(f"roles:{run.seed_role_coverage_status}")
    if run.seed_total_entries or run.seed_curated_papers:
        parts.append(f"{run.seed_curated_papers}/{run.seed_total_entries}")
    if run.seed_missing_roles:
        parts.append(f"missing={run.seed_missing_roles}")
    if run.seed_required_actions:
        parts.append(f"A{run.seed_required_actions}")
    return " ".join(parts)


def _recovery_cell(run: RunSummary) -> str:
    if not run.recovery_category:
        return "-"
    suffix = f" ({run.recovery_blocking_issues})" if run.recovery_blocking_issues else ""
    return f"{run.recovery_category}{suffix}"


def _experiment_manager_cell(run: RunSummary) -> str:
    if not run.experiment_manager_status:
        return "-"
    policy = f":{run.experiment_manager_policy}" if run.experiment_manager_policy else ""
    parts = []
    if run.experiment_manager_next_candidates:
        parts.append(f"next={run.experiment_manager_next_candidates}")
    queue = []
    if run.experiment_manager_queue_blocked:
        queue.append(f"B{run.experiment_manager_queue_blocked}")
    if run.experiment_manager_queue_human_review:
        queue.append(f"H{run.experiment_manager_queue_human_review}")
    if run.experiment_manager_queue_ready_backlog:
        queue.append(f"R{run.experiment_manager_queue_ready_backlog}")
    if queue:
        parts.append("Q" + "".join(queue))
    suffix = f" {' '.join(parts)}" if parts else ""
    return f"{run.experiment_manager_status}{policy}{suffix}"


def _final_gate_cell(run: RunSummary) -> str:
    if run.final_readiness_status:
        score = f" {run.final_score_after:.1f}" if run.final_score_after is not None else ""
        return f"{run.final_readiness_status}{score}"
    if run.paper_review_decision:
        return f"initial:{run.paper_review_decision}"
    return "-"


def _literature_rescue_cell(run: RunSummary) -> str:
    if not run.literature_rescue_status and not run.literature_rescue_execution_status:
        return "-"
    plan = run.literature_rescue_status or "-"
    suffix = f" ({run.literature_rescue_queries})" if run.literature_rescue_queries else ""
    execution = ""
    if run.literature_rescue_execution_status:
        parts = [f"exec:{run.literature_rescue_execution_status}"]
        if run.literature_rescue_execution_unresolved:
            parts.append(f"U{run.literature_rescue_execution_unresolved}")
        if run.literature_rescue_execution_closed:
            parts.append(f"C{run.literature_rescue_execution_closed}")
        if run.literature_rescue_execution_new_unique:
            parts.append(f"N{run.literature_rescue_execution_new_unique}")
        execution = " / " + " ".join(parts)
    return f"{plan}{suffix}{execution}"


def _result_validation_cell(run: RunSummary) -> str:
    if not run.result_validation_status:
        return "-"
    issues = run.result_validation_blocking_issues + run.result_validation_warnings
    suffix = f" ({issues})" if issues else ""
    return f"{run.result_validation_status}{suffix}"


def _benchmark_schema_cell(run: RunSummary) -> str:
    if not run.benchmark_schema_status:
        return "-"
    issues = run.benchmark_schema_blocking_issues + run.benchmark_schema_manual_tasks
    suffix = f" ({issues})" if issues else ""
    return f"{run.benchmark_schema_status}{suffix}"


def _paper_grade_cell(run: RunSummary) -> str:
    parts: list[str] = []
    if run.paper_grade_literature_status:
        suffix = f":{run.paper_grade_literature_issues}" if run.paper_grade_literature_issues else ""
        parts.append(f"lit={run.paper_grade_literature_status}{suffix}")
    if run.benchmark_evidence_status or run.benchmark_evidence_grade:
        grade = f"/{run.benchmark_evidence_grade}" if run.benchmark_evidence_grade else ""
        issues = run.benchmark_evidence_blocking_issues + run.benchmark_evidence_manual_tasks
        suffix = f":{issues}" if issues else ""
        parts.append(f"bench={run.benchmark_evidence_status or '-'}{grade}{suffix}")
    if run.adapter_paper_grade_status:
        suffix = f":{run.adapter_paper_grade_issues}" if run.adapter_paper_grade_issues else ""
        parts.append(f"adapter={run.adapter_paper_grade_status}{suffix}")
    if run.benchmark_claim_boundary_severity:
        parts.append(f"boundary={run.benchmark_claim_boundary_severity}")
    if run.benchmark_publishable_negative_or_neutral:
        parts.append("negneutral=publishable")
    if run.claim_preflight_status:
        mode = f"/{run.claim_preflight_mode}" if run.claim_preflight_mode else ""
        issues = run.claim_preflight_blocking_issues + run.claim_preflight_warnings
        suffix = f":{issues}" if issues else ""
        parts.append(f"claim={run.claim_preflight_status}{mode}{suffix}")
    if run.claim_consistency_status:
        issues = run.claim_consistency_blocking_issues + run.claim_consistency_manual_tasks
        suffix = f":{issues}" if issues else ""
        parts.append(f"cc={run.claim_consistency_status}{suffix}")
    return " ".join(parts) if parts else "-"


def _failure_analysis_cell(run: RunSummary) -> str:
    if not run.failure_analysis_status:
        return "-"
    issues = run.failed_runs + run.negative_metrics + run.uncertain_metrics
    suffix = f" ({issues})" if issues else ""
    return f"{run.failure_analysis_status}{suffix}"


def _run_economics_cell(run: RunSummary) -> str:
    if not run.run_economics_status:
        return "-"
    tokens = run.llm_input_tokens_estimated + run.llm_output_tokens_estimated
    cost = f" ${run.llm_estimated_cost_usd:.4f}" if run.llm_estimated_cost_usd is not None else ""
    pressure = max(run.llm_budget_call_utilization, run.llm_budget_prompt_utilization)
    pressure_text = f" p{pressure:.2f}" if pressure else ""
    issues = run.run_economics_blocking_issues + run.run_economics_manual_tasks
    suffix = f" ({issues})" if issues else ""
    return f"{run.run_economics_status}{suffix} {run.llm_total_calls}c/{tokens}t/{run.llm_duration_seconds:.1f}s{cost}{pressure_text}"


def _final_gate_penalty(summary: RunSummary) -> float:
    status = summary.final_readiness_status
    if not status:
        return 0.0
    penalty = (
        summary.deferred_tasks * 0.6
        + summary.blocking_issues * 0.5
        + summary.unsupported_after * 0.8
        + summary.weak_after * 0.15
        + summary.availability_blocking_issues * 0.7
        + summary.availability_manual_tasks * 0.25
        + summary.submission_blocking_issues * 0.5
        + summary.submission_manual_tasks * 0.2
        + summary.package_blocking_issues * 0.5
        + summary.package_manual_tasks * 0.15
    )
    if status == "requires_human_evidence":
        penalty += 3.0
    elif status == "requires_revision":
        penalty += 1.5
    elif status == "ready_for_human_polish":
        penalty += 0.3
    elif status == "ready_for_submission_check":
        penalty -= 0.8
    penalty += _availability_penalty(summary.availability_status)
    penalty += _submission_penalty(summary.submission_status)
    penalty += _package_penalty(summary.package_status)
    return max(-1.0, min(5.0, penalty))


def _audit_penalty(summary: RunSummary) -> float:
    penalty = 0.0
    if summary.seed_intake_status == "block":
        penalty += 2.0
    elif summary.seed_intake_status == "review_required":
        penalty += 0.9
    elif summary.seed_intake_status == "pass":
        penalty -= 0.1
    if summary.seed_role_coverage_status == "review_required":
        penalty += 0.8
    elif summary.seed_role_coverage_status == "pass":
        penalty -= 0.1
    penalty += min(1.2, summary.seed_required_actions * 0.25 + summary.seed_missing_roles * 0.2)
    if summary.literature_rescue_status in {"block", "needs_source_repair"}:
        penalty += 2.0
    elif summary.literature_rescue_status in {"needs_rescue_search", "needs_manual_seed"}:
        penalty += 1.2
    elif summary.literature_rescue_status == "pass":
        penalty -= 0.2
    if summary.literature_rescue_execution_status == "no_new_papers":
        penalty += 1.0
    if summary.literature_rescue_execution_unresolved:
        penalty += min(summary.literature_rescue_execution_unresolved * 0.4, 1.2)
    if summary.result_validation_status == "block":
        penalty += 2.5
    elif summary.result_validation_status == "warn":
        penalty += 0.8
    elif summary.result_validation_status == "pass":
        penalty -= 0.2
    if summary.benchmark_schema_status == "block":
        penalty += 2.5
    elif summary.benchmark_schema_status == "review_required":
        penalty += 0.9
    elif summary.benchmark_schema_status == "pass":
        penalty -= 0.2
    if summary.failure_analysis_status == "block":
        penalty += 2.5
    elif summary.failure_analysis_status == "warn":
        penalty += 1.0
    elif summary.failure_analysis_status == "pass":
        penalty -= 0.2
    if summary.run_integrity_status == "block":
        penalty += 2.5
    elif summary.run_integrity_status == "warn":
        penalty += 0.9
    elif summary.run_integrity_status == "pass":
        penalty -= 0.2
    if summary.final_handoff_status == "blocked":
        penalty += 2.0
    elif summary.final_handoff_status == "ready_for_human_handoff":
        penalty += 0.4
    elif summary.final_handoff_status == "ready_for_submission_upload":
        penalty -= 0.2
    if summary.final_handoff_package_zip_valid is False:
        penalty += 1.5
    if summary.agent_trajectory_status == "block":
        penalty += 2.0
    elif summary.agent_trajectory_status == "warn":
        penalty += 0.6
    elif summary.agent_trajectory_status == "pass":
        penalty -= 0.1
    if summary.agent_observability_status == "block":
        penalty += 2.2
    elif summary.agent_observability_status == "review_required":
        penalty += 0.7
    elif summary.agent_observability_status == "pass":
        penalty -= 0.1
    if summary.repair_queue_status == "blocked_repair_required":
        penalty += 2.0
    elif summary.repair_queue_status == "needs_repair":
        penalty += 0.9
    elif summary.repair_queue_status == "pass":
        penalty -= 0.2
    if summary.repair_resume_status and not summary.repair_resume_applied and summary.repair_queue_status in {"blocked_repair_required", "needs_repair"}:
        penalty += 0.4
    penalty += min(2.5, summary.failed_runs * 0.6 + summary.negative_metrics * 0.25 + summary.uncertain_metrics * 0.2)
    penalty += min(1.5, summary.result_validation_blocking_issues * 0.5 + summary.result_validation_warnings * 0.2)
    penalty += min(1.8, summary.benchmark_schema_blocking_issues * 0.6 + summary.benchmark_schema_manual_tasks * 0.25)
    penalty += min(2.2, summary.repair_queue_block * 0.7 + summary.repair_queue_high * 0.35 + summary.repair_queue_medium * 0.15)
    penalty += min(
        1.8,
        summary.agent_trajectory_block * 0.4
        + summary.agent_trajectory_blocking_issues * 0.5
        + summary.agent_trajectory_warn * 0.15
        + summary.agent_trajectory_manual_tasks * 0.1,
    )
    penalty += min(
        2.0,
        summary.agent_observability_blocking_issues * 0.6
        + summary.agent_observability_manual_tasks * 0.2
        + summary.agent_observability_warnings * 0.15
        + summary.agent_observability_llm_failed_calls * 0.5,
    )
    if max(summary.agent_observability_call_pressure, summary.agent_observability_prompt_pressure) >= 0.9:
        penalty += 0.35
    penalty += min(2.0, summary.run_integrity_blocking_issues * 0.7 + summary.run_integrity_warnings * 0.25)
    penalty += min(1.5, summary.final_handoff_blocking_issues * 0.6 + summary.final_handoff_manual_tasks * 0.2)
    return max(-0.6, min(6.0, penalty))


def _preflight_penalty(summary: RunSummary) -> float:
    if summary.preflight_status == "fail":
        return min(3.0, 1.2 + summary.preflight_fails * 0.45 + summary.preflight_warnings * 0.1)
    if summary.preflight_status == "warn":
        return min(1.0, summary.preflight_warnings * 0.2)
    if summary.preflight_status == "pass":
        return -0.1
    return 0.0


def _evidence_confidence_penalty(summary: RunSummary) -> float:
    if summary.evidence_confidence_status == "block":
        return 2.5
    if summary.evidence_confidence_status == "weak":
        return 1.4
    if summary.evidence_confidence_status == "review_required":
        return 0.5
    if summary.evidence_confidence_status == "pass":
        return -0.2
    return 0.0


def _paper_grade_penalty(summary: RunSummary) -> float:
    penalty = 0.0
    if summary.paper_grade_literature_status == "block":
        penalty += 2.0
    elif summary.paper_grade_literature_status == "review_required":
        penalty += 1.2
    elif summary.paper_grade_literature_status == "pass":
        penalty -= 0.2
    penalty += min(1.2, summary.paper_grade_literature_issues * 0.2)

    if summary.benchmark_evidence_status == "block" or summary.benchmark_evidence_grade == "blocked":
        penalty += 2.5
    elif summary.benchmark_evidence_status == "smoke_only" or summary.benchmark_evidence_grade == "smoke_only":
        penalty += 1.8
    elif summary.benchmark_evidence_status == "review_required" or summary.benchmark_evidence_grade == "local_experiment":
        penalty += 1.2
    elif summary.benchmark_evidence_status in {"pass", "warn"} and summary.benchmark_evidence_grade == "real_benchmark":
        penalty -= 0.3
    penalty += min(1.5, summary.benchmark_evidence_blocking_issues * 0.6 + summary.benchmark_evidence_manual_tasks * 0.25)

    if summary.adapter_paper_grade_status == "review_required":
        penalty += 1.2
    elif summary.adapter_paper_grade_status == "ready":
        penalty -= 0.2
    penalty += min(1.2, summary.adapter_paper_grade_issues * 0.25)

    if summary.claim_preflight_status == "block":
        penalty += 2.0
    elif summary.claim_preflight_status == "review_required":
        penalty += 0.9
    elif summary.claim_preflight_status == "pass":
        penalty -= 0.2
    penalty += min(1.5, summary.claim_preflight_blocking_issues * 0.6 + summary.claim_preflight_warnings * 0.2)

    if summary.claim_consistency_status == "block":
        penalty += 2.0
    elif summary.claim_consistency_status == "review_required":
        penalty += 0.8
    elif summary.claim_consistency_status == "pass":
        penalty -= 0.2
    penalty += min(1.5, summary.claim_consistency_blocking_issues * 0.6 + summary.claim_consistency_manual_tasks * 0.2)
    return max(-0.8, min(6.0, penalty))


def _recovery_penalty(summary: RunSummary) -> float:
    penalty = min(2.0, summary.recovery_blocking_issues * 0.6)
    if summary.recovery_category == "failed":
        penalty += 2.0
    elif summary.recovery_category == "cancelled":
        penalty += 1.5
    elif summary.recovery_category == "cancelling":
        penalty += 1.0
    elif summary.recovery_category == "review_revision_requested":
        penalty += 1.0
    elif summary.recovery_category == "awaiting_review_approval":
        penalty += 0.6
    elif summary.recovery_category == "checkpoint_resume":
        penalty += 0.3
    elif summary.recovery_category == "completed":
        penalty -= 0.1
    return max(-0.1, min(4.0, penalty))


def _availability_cell(run: RunSummary) -> str:
    if not run.availability_status:
        return "-"
    blockers = run.availability_blocking_issues + run.availability_manual_tasks
    suffix = f" ({blockers})" if blockers else ""
    return f"{run.availability_status}{suffix}"


def _submission_cell(run: RunSummary) -> str:
    if not run.submission_status:
        return "-"
    blockers = run.submission_blocking_issues + run.submission_manual_tasks
    suffix = f" ({blockers})" if blockers else ""
    return f"{run.submission_status}{suffix}"


def _package_cell(run: RunSummary) -> str:
    if not run.package_status:
        return "-"
    blockers = run.package_blocking_issues + run.package_manual_tasks
    suffix = f" ({blockers})" if blockers else ""
    return f"{run.package_status}{suffix}"


def _scorecard_cell(run: RunSummary) -> str:
    if not run.scorecard_status:
        return "-"
    parts = [run.scorecard_status]
    if run.scorecard_overall_score is not None:
        parts.append(f"{run.scorecard_overall_score:.1f}")
    if run.scorecard_blocking_issues:
        parts.append(f"B{run.scorecard_blocking_issues}")
    if run.scorecard_manual_tasks:
        parts.append(f"M{run.scorecard_manual_tasks}")
    return " ".join(parts)


def _iteration_cell(run: RunSummary) -> str:
    if not run.iteration_status:
        return "-"
    suffix = f" ({run.iteration_items})" if run.iteration_items else ""
    return f"{run.iteration_status}{suffix}"


def _repair_queue_cell(run: RunSummary) -> str:
    if not run.repair_queue_status:
        return "-"
    parts = [run.repair_queue_status]
    if run.repair_queue_items:
        parts.append(f"T{run.repair_queue_items}")
    if run.repair_queue_block:
        parts.append(f"B{run.repair_queue_block}")
    if run.repair_queue_high:
        parts.append(f"H{run.repair_queue_high}")
    if run.repair_queue_medium:
        parts.append(f"M{run.repair_queue_medium}")
    if run.repair_queue_blocks_submission:
        parts.append(f"S{run.repair_queue_blocks_submission}")
    return " ".join(parts)


def _repair_resume_cell(run: RunSummary) -> str:
    if not run.repair_resume_status:
        return "-"
    state = "applied" if run.repair_resume_applied else "planned"
    parts = [run.repair_resume_status, state]
    if run.repair_resume_rerun_from:
        parts.append(f"from={run.repair_resume_rerun_from}")
    if run.repair_resume_items:
        parts.append(f"T{run.repair_resume_items}")
    if run.repair_resume_retrieval_tasks:
        parts.append(f"Q{run.repair_resume_retrieval_tasks}")
    gates = []
    if run.repair_resume_review_reapproval_required:
        gates.append("review")
    if run.repair_resume_execution_reapproval_required:
        gates.append("exec")
    if gates:
        parts.append("gate=" + ",".join(gates))
    return " ".join(parts)


def _run_integrity_cell(run: RunSummary) -> str:
    if not run.run_integrity_status:
        return "-"
    issues = [f"P{run.run_integrity_pass}"]
    if run.run_integrity_warnings:
        issues.append(f"W{run.run_integrity_warnings}")
    if run.run_integrity_blocking_issues:
        issues.append(f"B{run.run_integrity_blocking_issues}")
    return f"{run.run_integrity_status} {' '.join(issues)}"


def _agent_trajectory_cell(run: RunSummary) -> str:
    if not run.agent_trajectory_status:
        return "-"
    parts = []
    if run.agent_trajectory_pass:
        parts.append(f"P{run.agent_trajectory_pass}")
    if run.agent_trajectory_warn:
        parts.append(f"W{run.agent_trajectory_warn}")
    if run.agent_trajectory_block:
        parts.append(f"B{run.agent_trajectory_block}")
    if run.agent_trajectory_not_started:
        parts.append(f"N{run.agent_trajectory_not_started}")
    if run.agent_trajectory_manual_tasks:
        parts.append(f"M{run.agent_trajectory_manual_tasks}")
    if run.agent_trajectory_last_event:
        parts.append(f"last={run.agent_trajectory_last_event}")
    if run.agent_trajectory_backfilled_events:
        parts.append(f"BF{run.agent_trajectory_backfilled_events}")
    suffix = " " + " ".join(parts) if parts else ""
    return f"{run.agent_trajectory_status}{suffix}"


def _agent_observability_cell(run: RunSummary) -> str:
    if not run.agent_observability_status:
        return "-"
    parts = []
    if run.agent_observability_manifest_events:
        parts.append(f"E{run.agent_observability_manifest_events}")
    if run.agent_observability_manifest_artifacts:
        parts.append(f"A{run.agent_observability_manifest_artifacts}")
    if run.agent_observability_llm_failed_calls:
        parts.append(f"L{run.agent_observability_llm_failed_calls}")
    if run.agent_observability_experiment_runs:
        parts.append(f"X{run.agent_observability_experiment_runs}")
    if run.agent_observability_repair_queue_status:
        parts.append(f"R{run.agent_observability_repair_queue_status}")
    if run.agent_observability_blocking_issues:
        parts.append(f"B{run.agent_observability_blocking_issues}")
    if run.agent_observability_manual_tasks:
        parts.append(f"M{run.agent_observability_manual_tasks}")
    if run.agent_observability_warnings:
        parts.append(f"W{run.agent_observability_warnings}")
    pressure = max(run.agent_observability_call_pressure, run.agent_observability_prompt_pressure)
    if pressure:
        parts.append(f"p{pressure:.2f}")
    suffix = " " + " ".join(parts) if parts else ""
    return f"{run.agent_observability_status}{suffix}"


def _final_handoff_cell(run: RunSummary) -> str:
    if not run.final_handoff_status:
        return "-"
    issues = []
    if run.final_handoff_blocking_issues:
        issues.append(f"B{run.final_handoff_blocking_issues}")
    if run.final_handoff_manual_tasks:
        issues.append(f"M{run.final_handoff_manual_tasks}")
    issues.append("audit=Y" if run.final_handoff_package_has_integrity_audit else "audit=N")
    if run.final_handoff_package_zip_valid is not None:
        issues.append("zip=Y" if run.final_handoff_package_zip_valid else "zip=N")
    return f"{run.final_handoff_status} {' '.join(issues)}"


def _blocking_count(run: RunSummary) -> int:
    return (
        run.deferred_tasks
        + run.blocking_issues
        + run.unsupported_after
        + run.preflight_fails
        + run.recovery_blocking_issues
        + (1 if run.seed_intake_status == "block" else 0)
        + (1 if run.seed_role_coverage_status == "review_required" else 0)
        + run.paper_grade_literature_issues
        + (1 if run.paper_grade_literature_status == "block" and not run.paper_grade_literature_issues else 0)
        + run.literature_rescue_execution_unresolved
        + run.result_validation_blocking_issues
        + run.benchmark_schema_blocking_issues
        + run.benchmark_schema_manual_tasks
        + run.benchmark_evidence_blocking_issues
        + run.benchmark_evidence_manual_tasks
        + run.adapter_paper_grade_issues
        + (1 if run.benchmark_evidence_status in {"block", "smoke_only", "review_required"} and not run.benchmark_evidence_blocking_issues else 0)
        + (1 if run.benchmark_evidence_grade in {"blocked", "smoke_only", "local_experiment"} and not run.benchmark_evidence_manual_tasks else 0)
        + (1 if run.adapter_paper_grade_status == "review_required" and not run.adapter_paper_grade_issues else 0)
        + run.failed_runs
        + run.claim_preflight_blocking_issues
        + (1 if run.claim_preflight_status == "block" and not run.claim_preflight_blocking_issues else 0)
        + run.claim_consistency_blocking_issues
        + (1 if run.claim_consistency_status == "block" and not run.claim_consistency_blocking_issues else 0)
        + run.availability_blocking_issues
        + run.availability_manual_tasks
        + run.submission_blocking_issues
        + run.submission_manual_tasks
        + run.package_blocking_issues
        + run.package_manual_tasks
        + run.scorecard_blocking_issues
        + run.scorecard_manual_tasks
        + run.repair_queue_block
        + run.repair_queue_high
        + run.repair_queue_medium
        + (1 if run.repair_queue_status == "blocked_repair_required" and not run.repair_queue_block else 0)
        + run.agent_trajectory_blocking_issues
        + run.agent_trajectory_block
        + (1 if run.agent_trajectory_status == "block" and not run.agent_trajectory_blocking_issues and not run.agent_trajectory_block else 0)
        + run.agent_observability_blocking_issues
        + (1 if run.agent_observability_status == "block" and not run.agent_observability_blocking_issues else 0)
        + run.run_integrity_blocking_issues
        + run.final_handoff_blocking_issues
        + (1 if run.final_handoff_package_zip_valid is False else 0)
    )


def _availability_penalty(status: str) -> float:
    if status == "blocked":
        return 2.0
    if status == "needs_human_release_metadata":
        return 1.0
    if status == "ready_for_internal_release":
        return 0.3
    if status == "ready_for_submission_check":
        return -0.3
    return 0.0


def _submission_penalty(status: str) -> float:
    if status == "blocked":
        return 1.2
    if status == "needs_human_format_check":
        return 0.6
    if status == "ready_for_submission_check":
        return -0.2
    return 0.0


def _package_penalty(status: str) -> float:
    if status == "blocked":
        return 1.0
    if status == "needs_human_submission_review":
        return 0.5
    if status == "ready_for_human_submission_upload":
        return -0.2
    return 0.0


def _scorecard_penalty(summary: RunSummary) -> float:
    penalty = min(1.8, summary.scorecard_blocking_issues * 0.7 + summary.scorecard_manual_tasks * 0.2)
    if summary.scorecard_status == "blocked":
        penalty += 1.4
    elif summary.scorecard_status in {"needs_human_review", "review_required"}:
        penalty += 0.5
    elif summary.scorecard_status == "ready_for_human_submission_upload":
        penalty -= 0.1
    return max(-0.1, min(2.5, penalty))


def _iteration_penalty(status: str) -> float:
    if status == "needs_literature_repair":
        return 1.4
    if status == "needs_experiment_repair":
        return 1.6
    if status == "needs_human_evidence":
        return 1.5
    if status == "needs_real_benchmark_iteration":
        return 1.0
    if status == "needs_targeted_iteration":
        return 0.6
    if status == "ready_for_submission_upload":
        return -0.3
    if status == "ready_for_next_research_question":
        return -0.2
    return 0.0


def _run_economics_penalty(summary: RunSummary) -> float:
    penalty = min(1.5, summary.run_economics_blocking_issues * 0.6 + summary.run_economics_manual_tasks * 0.25)
    if summary.run_economics_status == "block":
        penalty += 1.2
    elif summary.run_economics_status == "review_required":
        penalty += 0.5
    elif summary.run_economics_status == "pass":
        penalty -= 0.1
    if max(summary.llm_budget_call_utilization, summary.llm_budget_prompt_utilization) >= 0.9:
        penalty += 0.4
    return max(-0.1, min(2.5, penalty))


def _availability_list_count(
    availability: dict[str, Any],
    final_readiness: dict[str, Any],
    availability_key: str,
    final_readiness_key: str,
) -> int:
    value = availability.get(availability_key)
    if isinstance(value, list):
        return len(value)
    value = final_readiness.get(final_readiness_key)
    if isinstance(value, list):
        return len(value)
    return 0


def _trajectory_count(data: dict[str, Any], summary: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, list):
        return len(value)
    return _safe_int(summary.get(key))


def _status(stage: str, diagnostic: dict[str, Any], cancel: dict[str, Any], manifest: dict[str, Any]) -> str:
    if cancel.get("cancelled") is True or stage == "cancelled":
        return "cancelled"
    if diagnostic or stage == "failed":
        return "failed"
    if stage == "completed" or manifest.get("status") == "completed":
        return "completed"
    if stage == "review_revision_requested":
        return "revision_requested"
    if stage == "awaiting_review_approval":
        return "waiting"
    return "unknown"


def _stage_progress(stage: str) -> float:
    if stage == "failed":
        return 0.0
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return 0.0
    return index / max(len(STAGE_ORDER) - 1, 1)


def _top_idea_score(ideas: list[Any]) -> float | None:
    scores: list[float] = []
    for idea in ideas:
        if not isinstance(idea, dict):
            continue
        if "score" in idea:
            score = _safe_float_or_none(idea.get("score"))
        else:
            score = _safe_float_or_none(idea.get("novelty"))
            feasibility = _safe_float_or_none(idea.get("feasibility"))
            risk = _safe_float_or_none(idea.get("risk"))
            score = None if score is None or feasibility is None or risk is None else score + feasibility - risk
        if score is not None:
            scores.append(score)
    return max(scores) if scores else None


def _run_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return [path for path in runs_dir.iterdir() if path.is_dir()]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _artifact_count(run_dir: Path) -> int:
    return sum(1 for path in run_dir.rglob("*") if path.is_file()) if run_dir.exists() else 0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
