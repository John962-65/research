from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, utc_now as _utc_now, read_json_dict as _read_json
from .run_memory import build_run_memory
from .run_summary import RunSummary, build_run_dashboard


PLATFORM_AUDIT_JSON = "runs-platform-audit.json"
PLATFORM_AUDIT_MD = "runs-platform-audit.md"


@dataclass(frozen=True)
class PlatformGap:
    gap_id: str
    category: str
    severity: str
    source_projects: list[str]
    affected_runs: list[str]
    evidence: list[str]
    recommended_action: str
    target_artifacts: list[str]


@dataclass(frozen=True)
class PlatformAuditReport:
    generated_at: str
    runs_dir: str
    total_runs: int
    analyzed_runs: int
    status: str
    capability_scores: dict[str, float]
    gaps: list[PlatformGap]
    next_actions: list[str]


def build_platform_audit(runs_dir: Path, limit: int = 100) -> PlatformAuditReport:
    dashboard = build_run_dashboard(runs_dir, limit=limit)
    memory = build_run_memory(runs_dir, limit=limit)
    run_dirs = {run.id: runs_dir / run.id for run in dashboard.runs}
    gaps = _build_gaps(dashboard.runs, run_dirs)
    gaps = sorted(gaps, key=lambda item: (_severity_rank(item.severity), len(item.affected_runs), item.gap_id), reverse=True)
    status = _status(gaps, dashboard.runs)
    return PlatformAuditReport(
        generated_at=_utc_now(),
        runs_dir=str(runs_dir),
        total_runs=dashboard.total_runs,
        analyzed_runs=len(dashboard.runs),
        status=status,
        capability_scores=_capability_scores(gaps, dashboard.runs, memory.status),
        gaps=gaps,
        next_actions=_next_actions(gaps),
    )


def write_platform_audit(report: PlatformAuditReport, out_dir: Path, basename: str = "runs-platform-audit") -> tuple[Path, Path]:
    json_path = out_dir / f"{basename}.json"
    md_path = out_dir / f"{basename}.md"
    write_json(json_path, report)
    write_text(md_path, render_platform_audit_markdown(report))
    return json_path, md_path


def render_platform_audit_markdown(report: PlatformAuditReport) -> str:
    lines = [
        "# 平台能力审计",
        "",
        f"- 生成时间：{report.generated_at}",
        f"- Runs 目录：{report.runs_dir}",
        f"- 纳入 run：{report.analyzed_runs}/{report.total_runs}",
        f"- 状态：{report.status}",
        "",
        "## 能力分",
    ]
    if report.capability_scores:
        for key, value in sorted(report.capability_scores.items()):
            lines.append(f"- {key}: {value:.2f}")
    else:
        lines.append("- 暂无 run，无法评分。")
    lines.extend(
        [
            "",
            "## 优先缺口",
            "| 缺口 | 类别 | 严重性 | 来源项目 | Runs | 证据 | 建议动作 | 目标产物 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not report.gaps:
        lines.append("| 无 | - | - | - | - | - | 暂无跨 run 平台缺口。 | - |")
    for gap in report.gaps:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(gap.gap_id),
                    _cell(gap.category),
                    _cell(gap.severity),
                    _cell(", ".join(gap.source_projects)),
                    _cell(", ".join(gap.affected_runs)),
                    _cell("；".join(gap.evidence[:4])),
                    _cell(gap.recommended_action),
                    _cell(", ".join(gap.target_artifacts)),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 下一阶段动作"])
    lines.extend(f"- [ ] {item}" for item in report.next_actions) if report.next_actions else lines.append("- 暂无。")
    lines.extend(
        [
            "",
            "## 判定来源",
            "- AI-Scientist-v2：结构化 idea->experiment、自动调试修复和提交前质量门禁。",
            "- PaperQA2 / OpenScholar：检索、重排、全文/引用 grounding 和多源失败韧性。",
            "- AgentLaboratory：人工反馈 gate、阶段轨迹和 LLM 成本/可观测性。",
            "- MLAgentBench / MLE-bench：真实 benchmark、可复现实验产物和失败分析。",
        ]
    )
    return "\n".join(lines)


def _build_gaps(runs: list[RunSummary], run_dirs: dict[str, Path]) -> list[PlatformGap]:
    if not runs:
        return []
    gaps = []
    for gap in [
        _literature_quality_gap(runs, run_dirs),
        _human_gate_gap(runs, run_dirs),
        _experiment_benchmark_gap(runs, run_dirs),
        _llm_observability_gap(runs),
        _repair_loop_gap(runs),
        _release_readiness_gap(runs),
        _open_source_compliance_gap(runs, run_dirs),
    ]:
        if gap is not None:
            gaps.append(gap)
    return gaps


def _literature_quality_gap(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        if run.status == "failed" and not run.raw_papers and not run.citations:
            continue
        health = _read_json(run_dirs[run.id] / "01-literature-source-health.json")
        gate = _read_json(run_dirs[run.id] / "01-literature-gate-decision.json")
        gate_summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
        grounding = _read_json(run_dirs[run.id] / "10-citation-grounding.json")
        source_issues = _int(health.get("rate_limited_sources")) + _int(health.get("failed_sources"))
        gate_status = str(gate.get("status") or "").strip()
        grounding_status = str(grounding.get("status") or gate_summary.get("citation_grounding_status") or "").strip()
        context_chunks = _int(gate_summary.get("context_chunks"))
        weak_evidence = (run.selected_papers < 5 and run.citations < 5) or run.evidence_confidence_status in {"block", "warn", "low"}
        rescue_needed = run.literature_rescue_status in {"block", "needs_source_repair", "needs_rescue_search", "needs_manual_seed"}
        rescue_unresolved = run.literature_rescue_execution_unresolved > 0
        gate_gap = gate_status in {"block", "review_required"}
        grounding_gap = grounding_status in {"block", "review_required"}
        context_gap = bool(gate) and context_chunks == 0
        if not (weak_evidence or rescue_needed or rescue_unresolved or source_issues or gate_gap or grounding_gap or context_gap):
            continue
        affected.append(run.id)
        evidence.append(
            f"{run.id}: gate={gate_status or '-'}, selected={run.selected_papers}, citations={run.citations}, context_chunks={context_chunks}, grounding={grounding_status or '-'}, confidence={run.evidence_confidence_status or '-'}, rescue={run.literature_rescue_status or '-'}, unresolved={run.literature_rescue_execution_unresolved}"
        )
        severe = severe or gate_status == "block" or grounding_status == "block" or rescue_needed or (run.selected_papers == 0 and run.citations == 0)
    if not affected:
        return None
    return PlatformGap(
        gap_id="literature_rag_quality",
        category="literature",
        severity="block" if severe else "warn",
        source_projects=["Future-House/PaperQA2", "OpenScholar"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="把文献检索从数量检查升级为多源健康、seed 角色覆盖、rerank、全文 context 和 citation grounding 的一体化门禁；弱证据不得进入 idea/实验。",
        target_artifacts=[
            "01-literature-gate-decision.json",
            "01-literature-source-health.json",
            "01-seed-paper-intake.json",
            "01-literature-rerank.json",
            "01-context.json",
            "10-citation-grounding.json",
        ],
    )


def _human_gate_gap(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        approval = _read_json(run_dirs[run.id] / "approval.json")
        blocks = {str(item) for item in approval.get("blocks", [])} if isinstance(approval.get("blocks"), list) else set()
        after_review = _stage_at_or_after(run.stage, "ideation_completed") or run.ideas > 0 or run.compared_metrics > 0
        if after_review and approval.get("approved") is not True:
            affected.append(run.id)
            evidence.append(f"{run.id}: downstream_stage={run.stage}, review_approved=false")
            severe = True
            continue
        if after_review and not {"idea_generation", "experiment_planning", "experiment_execution"}.issubset(blocks):
            affected.append(run.id)
            evidence.append(f"{run.id}: approval_blocks={len(blocks)}/3")
        execution = _read_json(run_dirs[run.id] / "03-execution-approval.json")
        runbook = _read_json(run_dirs[run.id] / "04-experiment-runbook.json")
        mode = str(execution.get("execution_mode") or _nested(runbook, "execution", "mode") or "").strip()
        has_results = run.compared_metrics > 0 or (run_dirs[run.id] / "04-results.json").exists() or (run_dirs[run.id] / "04-results.csv").exists()
        if mode in {"local", "benchmark"} and has_results and execution.get("approved") is not True:
            affected.append(run.id)
            evidence.append(f"{run.id}: execution_mode={mode}, execution_approved=false")
            severe = True
    if not affected:
        return None
    return PlatformGap(
        gap_id="human_review_and_execution_gate",
        category="human_gate",
        severity="block" if severe else "warn",
        source_projects=["SamuelSchmidgall/AgentLaboratory"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="强制保留 review gate 与 local/benchmark execution gate 的结构化批准记录；未批准时禁止 idea、实验计划和执行继续推进。",
        target_artifacts=["approval.json", "01-review-gate.md", "03-execution-approval.json", "03-execution-safety-audit.json"],
    )


def _experiment_benchmark_gap(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        runbook = _read_json(run_dirs[run.id] / "04-experiment-runbook.json")
        mode = str(_nested(runbook, "execution", "mode") or "").strip()
        reached_experiment = _stage_at_or_after(run.stage, "experiments_completed") or run.compared_metrics > 0
        benchmark_gap = run.benchmark_schema_status in {"block", "review_required"} or run.benchmark_schema_blocking_issues or run.benchmark_schema_manual_tasks
        validation_gap = run.result_validation_status == "block" or run.failed_runs > 0 or run.uncertain_metrics > 0
        simulated = reached_experiment and mode == "simulated"
        no_metrics = reached_experiment and run.compared_metrics == 0
        if not (benchmark_gap or validation_gap or simulated or no_metrics):
            continue
        affected.append(run.id)
        evidence.append(
            f"{run.id}: mode={mode or '-'}, validation={run.result_validation_status or '-'}, benchmark_schema={run.benchmark_schema_status or '-'}, metrics={run.compared_metrics}"
        )
        severe = severe or validation_gap or run.benchmark_schema_status == "block"
    if not affected:
        return None
    return PlatformGap(
        gap_id="real_benchmark_execution",
        category="experiment",
        severity="block" if severe else "warn",
        source_projects=["SakanaAI/AI-Scientist-v2", "MLAgentBench", "MLE-bench"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="把 simulated 结果降级为 smoke，下一阶段优先接入 benchmark manifest、共同指标、重复实验、失败分析和 schema 审计。",
        target_artifacts=[
            "03-benchmark-plan.json",
            "03-benchmark-adapters.json",
            "04-experiment-runbook.json",
            "04-result-validation.json",
            "04-benchmark-result-schema-audit.json",
        ],
    )


def _llm_observability_gap(runs: list[RunSummary]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        failed_calls = run.agent_observability_llm_failed_calls
        observability_gap = run.agent_observability_status in {"block", "review_required"} or run.agent_observability_blocking_issues
        economics_gap = run.run_economics_status in {"block", "review_required"} or run.run_economics_blocking_issues
        missing_calls = run.status == "completed" and run.llm_total_calls == 0
        if not (failed_calls or observability_gap or economics_gap or missing_calls):
            continue
        affected.append(run.id)
        evidence.append(
            f"{run.id}: llm_calls={run.llm_total_calls}, failed={failed_calls}, economics={run.run_economics_status or '-'}, observability={run.agent_observability_status or '-'}"
        )
        severe = severe or economics_gap or observability_gap or missing_calls
    if not affected:
        return None
    return PlatformGap(
        gap_id="llm_trace_and_budget_observability",
        category="observability",
        severity="block" if severe else "warn",
        source_projects=["SamuelSchmidgall/AgentLaboratory", "MLAgentBench"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="所有关键科研阶段必须记录 LLM ledger、失败调用、预算压力和 AI disclosure；未配置模型时直接失败，不再规则兜底。",
        target_artifacts=["run-llm-ledger.json", "13-llm-trace-audit.json", "13-run-economics-audit.json", "13-agent-observability-audit.json"],
    )


def _repair_loop_gap(runs: list[RunSummary]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        queue_active = run.repair_queue_status in {"blocked_repair_required", "needs_repair"} or run.repair_queue_items > 0
        resume_needed = run.repair_resume_status and run.repair_resume_applied is not True and (run.repair_resume_items or run.repair_resume_retrieval_tasks)
        if not (queue_active or resume_needed):
            continue
        affected.append(run.id)
        evidence.append(
            f"{run.id}: repair_queue={run.repair_queue_status or '-'} items={run.repair_queue_items}, repair_resume={run.repair_resume_status or '-'} applied={run.repair_resume_applied}"
        )
        severe = severe or run.repair_queue_status == "blocked_repair_required" or run.repair_queue_block > 0
    if not affected:
        return None
    return PlatformGap(
        gap_id="repair_resume_backlog",
        category="repair_loop",
        severity="block" if severe else "warn",
        source_projects=["SakanaAI/AI-Scientist-v2"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="优先清理 repair queue，并用 repair-resume 从受影响 checkpoint 继续；修复后重新生成 scorecard、integrity 和 final handoff。",
        target_artifacts=["12-repair-queue.json", "12-repair-resume-plan.json", "12-repair-resolution-audit.json", "13-research-scorecard.json"],
    )


def _release_readiness_gap(runs: list[RunSummary]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        release_gap = (
            run.final_handoff_status == "blocked"
            or run.run_integrity_status == "block"
            or run.package_status == "blocked"
            or run.final_handoff_blocking_issues
            or run.final_handoff_package_zip_valid is False
            or run.run_integrity_blocking_issues
            or run.package_blocking_issues
            or run.availability_blocking_issues
            or run.submission_blocking_issues
        )
        manual_gap = run.final_handoff_manual_tasks or run.package_manual_tasks or run.availability_manual_tasks or run.submission_manual_tasks
        reached_release = _stage_at_or_after(run.stage, "final_readiness_completed") or run.final_readiness_status or run.package_status or run.final_handoff_status
        if not reached_release or not (release_gap or manual_gap):
            continue
        affected.append(run.id)
        evidence.append(
            f"{run.id}: integrity={run.run_integrity_status or '-'}, package={run.package_status or '-'}, "
            f"handoff={run.final_handoff_status or '-'}, zip_valid={_tri_state(run.final_handoff_package_zip_valid)}, manual={manual_gap}"
        )
        severe = severe or bool(release_gap)
    if not affected:
        return None
    return PlatformGap(
        gap_id="submission_release_readiness",
        category="release",
        severity="block" if severe else "warn",
        source_projects=["SakanaAI/AI-Scientist-v2", "OpenScholar"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="把最终交付拆成 integrity、代码/数据可用性、投稿格式、ZIP 包和人工交付检查，blocked 时不得把 run 标记为可提交。",
        target_artifacts=["10-code-data-availability.json", "10-submission-check.json", "11-submission-package.json", "14-run-integrity-audit.json", "14-final-handoff.json"],
    )


def _open_source_compliance_gap(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PlatformGap | None:
    affected: list[str] = []
    evidence: list[str] = []
    severe = False
    for run in runs:
        if run.status == "failed" and not _stage_at_or_after(run.stage, "literature_review_completed"):
            continue
        compliance = _read_json(run_dirs[run.id] / "13-open-source-compliance.json")
        status = str(compliance.get("status") or "").strip()
        if not compliance and _stage_at_or_after(run.stage, "analysis_completed"):
            affected.append(run.id)
            evidence.append(f"{run.id}: open_source_compliance=missing")
            severe = True
            continue
        if status in {"block", "needs_human_review"}:
            queue_has_item = _repair_queue_has_open_source_item(run_dirs[run.id])
            contract = compliance.get("contract_summary") if isinstance(compliance.get("contract_summary"), dict) else {}
            affected.append(run.id)
            evidence.append(
                f"{run.id}: open_source_compliance={status}, score={_float(compliance.get('score')):.2f}, checked={_int(compliance.get('checked_lessons'))}, contract={contract.get('status') or 'missing'}, repair_queue_open_source_item={'yes' if queue_has_item else 'missing'}"
            )
            severe = severe or status == "block" or not queue_has_item
    if not affected:
        return None
    return PlatformGap(
        gap_id="open_source_lesson_contract",
        category="platform_governance",
        severity="block" if severe else "warn",
        source_projects=["SakanaAI/AI-Scientist-v2", "Future-House/PaperQA2", "OpenScholar", "SamuelSchmidgall/AgentLaboratory", "MLAgentBench"],
        affected_runs=_limit_unique(affected),
        evidence=_limit_unique(evidence),
        recommended_action="把开源项目经验作为每个 run 的契约审计，而不是只作为 README 方案；合规失败必须进入 repair queue。",
        target_artifacts=["00-open-source-lessons.json", "13-open-source-compliance.json", "12-repair-queue.json"],
    )


def _capability_scores(gaps: list[PlatformGap], runs: list[RunSummary], memory_status: str) -> dict[str, float]:
    if not runs:
        return {}
    run_count = max(1, len(runs))
    categories = {
        "literature": "literature_rag_quality",
        "human_gate": "human_review_and_execution_gate",
        "experiment": "real_benchmark_execution",
        "observability": "llm_trace_and_budget_observability",
        "repair_loop": "repair_resume_backlog",
        "release": "submission_release_readiness",
        "platform_governance": "open_source_lesson_contract",
    }
    by_id = {gap.gap_id: gap for gap in gaps}
    scores: dict[str, float] = {}
    for category, gap_id in categories.items():
        gap = by_id.get(gap_id)
        if gap is None:
            scores[category] = 1.0
            continue
        severity_penalty = 0.35 if gap.severity == "block" else 0.2 if gap.severity == "warn" else 0.1
        affected_penalty = min(0.55, len(gap.affected_runs) / run_count * 0.55)
        scores[category] = round(max(0.0, 1.0 - severity_penalty - affected_penalty), 3)
    if memory_status == "needs_process_repair":
        scores["cross_run_memory"] = 0.55
    elif memory_status == "has_recommendations":
        scores["cross_run_memory"] = 0.75
    else:
        scores["cross_run_memory"] = 1.0
    return scores


def _next_actions(gaps: list[PlatformGap]) -> list[str]:
    actions: list[str] = []
    for gap in gaps[:6]:
        action = f"{gap.severity}: {gap.recommended_action}"
        if action not in actions:
            actions.append(action)
    return actions


def _status(gaps: list[PlatformGap], runs: list[RunSummary]) -> str:
    if not runs:
        return "empty"
    if any(gap.severity == "block" for gap in gaps):
        return "blocked"
    if gaps:
        return "needs_platform_work"
    return "stable"


STAGE_ORDER = [
    "queued",
    "started",
    "research_plan_completed",
    "literature_review_completed",
    "literature_context_completed",
    "awaiting_review_approval",
    "review_revision_requested",
    "review_approved",
    "ideation_completed",
    "exploration_map_completed",
    "experiment_manager_completed",
    "experiment_plan_completed",
    "awaiting_execution_approval",
    "execution_approved",
    "experiments_completed",
    "analysis_completed",
    "paper_review_completed",
    "revision_plan_completed",
    "paper_revision_completed",
    "revision_response_audit_completed",
    "final_readiness_completed",
    "submission_package_completed",
    "iteration_plan_completed",
    "llm_trace_audit_completed",
    "run_economics_audit_completed",
    "agent_observability_audit_completed",
    "repair_queue_completed",
    "repair_resolution_audit_completed",
    "agent_stage_contract_completed",
    "scorecard_completed",
    "run_integrity_audit_completed",
    "final_handoff_completed",
    "completed",
]


def _stage_at_or_after(stage: str, target: str) -> bool:
    try:
        return STAGE_ORDER.index(stage) >= STAGE_ORDER.index(target)
    except ValueError:
        return stage == "completed"


def _nested(data: dict[str, Any], first: str, second: str) -> Any:
    value = data.get(first) if isinstance(data, dict) else None
    if not isinstance(value, dict):
        return None
    return value.get(second)


def _repair_queue_has_open_source_item(run_dir: Path) -> bool:
    queue = _read_json(run_dir / "12-repair-queue.json")
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("category") or "") == "open_source_compliance":
            return True
        if str(item.get("source_artifact") or "") == "13-open-source-compliance.json":
            return True
    return False


def _limit_unique(values: list[str], limit: int = 8) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tri_state(value: bool | None) -> str:
    if value is True:
        return "Y"
    if value is False:
        return "N"
    return "?"


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warn": 1, "block": 2}.get(severity, 0)


