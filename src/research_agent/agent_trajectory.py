from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


AGENT_TRAJECTORY_JSON = "13-agent-trajectory.json"
AGENT_TRAJECTORY_MD = "13-agent-trajectory.md"


PHASES: list[dict[str, Any]] = [
    {
        "id": "planning",
        "name": "问题、人工输入与计划",
        "stage_prefixes": ["preflight", "question", "human_brief", "prior_run_lessons", "open_source_lessons", "research_plan"],
        "required_artifacts": ["00-research-plan.json"],
        "status_artifacts": ["00-preflight.json"],
        "next_action": "检查 00-human-brief、00-prior-run-lessons 和 00-research-plan 后再进入检索。",
    },
    {
        "id": "literature_grounding",
        "name": "文献检索、质量和引用 grounding",
        "stage_prefixes": ["literature", "query_execution", "fulltext_corpus", "citation_audit"],
        "required_artifacts": ["01-context.json", "01-review-gate.md"],
        "status_artifacts": [
            "01-query-execution-audit.json",
            "01-literature-evidence-mix.json",
            "01-literature-rescue-plan.json",
            "01-literature-metadata-audit.json",
            "01-citation-audit.json",
        ],
        "next_action": "优先看 01-review-gate、01-query-execution-audit 和 01-literature-evidence-mix。",
    },
    {
        "id": "human_gate",
        "name": "人工 review gate",
        "stage_prefixes": ["review_approval", "review_feedback", "review_constraints"],
        "required_artifacts": ["approval.json"],
        "status_artifacts": ["approval.json", "01-review-constraints.json"],
        "next_action": "确认 approval.json 记录已批准且 blocks 覆盖 idea、实验计划和实验执行。",
    },
    {
        "id": "ideation",
        "name": "Idea 探索和分支选择",
        "stage_prefixes": ["research_gap_map", "multi_agent_assignment", "ideation", "novelty_audit", "idea_audit", "exploration_map", "experiment_manager"],
        "required_artifacts": ["02-ideas.json", "02-exploration-map.json", "02-experiment-manager.json"],
        "status_artifacts": ["02-agent-team.json", "02-idea-audit.json", "02-experiment-manager.json"],
        "next_action": "查看 02-exploration-map 和 02-experiment-manager，确认选中分支没有 block。",
    },
    {
        "id": "experiment_design",
        "name": "实验计划、约束和执行前 gate",
        "stage_prefixes": ["experiment_plan", "multi_agent_handoff", "review_constraint_compliance", "experiment_audit", "idea_experiment_contract", "execution_safety", "ablation", "preregistration", "benchmark"],
        "required_artifacts": ["03-experiment-plan.json"],
        "status_artifacts": [
            "03-review-constraint-compliance.json",
            "03-agent-handoff-audit.json",
            "03-experiment-audit.json",
            "03-idea-experiment-contract.json",
            "03-execution-safety-audit.json",
            "03-benchmark-readiness.json",
        ],
        "next_action": "执行前必须检查 03-experiment-audit、03-idea-experiment-contract 和 execution approval。",
    },
    {
        "id": "execution_analysis",
        "name": "实验执行、统计和 claim 边界",
        "stage_prefixes": ["execution_approval", "experiments", "statistics", "result_validation", "failure_analysis", "benchmark_result_schema", "benchmark_evidence", "experiment_decision", "hypothesis_outcome", "claim_boundary"],
        "required_artifacts": ["04-experiment-runbook.json", "04-statistics.json"],
        "status_artifacts": [
            "04-result-validation.json",
            "04-benchmark-result-schema-audit.json",
            "04-failure-analysis.json",
            "04-benchmark-evidence-audit.json",
            "04-hypothesis-outcome.json",
            "04-claim-boundary-preflight.json",
        ],
        "next_action": "写作前确认 04-result-validation、04-benchmark-result-schema 和 04-claim-boundary-preflight。",
    },
    {
        "id": "writing_review",
        "name": "论文写作、复核和修订闭环",
        "stage_prefixes": ["paper", "paper_review", "revision", "claim_traceability", "agent_deliberation", "citation_grounding", "citation_coverage", "results_presentation", "claim_consistency"],
        "required_artifacts": ["06-paper.md", "09-revised-paper.md"],
        "status_artifacts": [
            "07-paper-review-calibration.json",
            "09-revision-response-audit.json",
            "10-claim-traceability.json",
            "10-agent-claim-audit.json",
            "10-agent-deliberation.json",
            "10-citation-grounding.json",
            "10-citation-coverage.json",
            "10-results-presentation.json",
            "10-claim-consistency.json",
        ],
        "next_action": "查看修订响应、claim traceability、citation grounding/coverage 和结果呈现审计。",
    },
    {
        "id": "release_observability",
        "name": "发布、修复队列和可观测性",
        "stage_prefixes": ["release", "code_data", "submission", "iteration", "repair", "llm_trace", "run_economics", "llm_observability", "agent_observability", "agent_stage_contract", "research_scorecard", "run_integrity", "final_handoff", "completed"],
        "required_artifacts": ["12-repair-queue.json", "13-agent-observability-audit.json", "13-llm-observability-summary.json", "14-run-integrity-audit.json"],
        "status_artifacts": [
            "10-code-data-availability.json",
            "10-submission-check.json",
            "10-final-readiness.json",
            "11-submission-package.json",
            "12-repair-queue.json",
            "12-repair-resolution-audit.json",
            "13-open-source-compliance.json",
            "13-agent-stage-contract.json",
            "13-agent-observability-audit.json",
            "13-llm-observability-summary.json",
            "13-research-scorecard.json",
            "14-run-integrity-audit.json",
        ],
        "next_action": "最终归档前检查 repair queue、stage contract、observability、scorecard 和 run integrity。",
    },
]


def write_agent_trajectory_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_agent_trajectory_report(topic, run_dir)
    write_json(run_dir / AGENT_TRAJECTORY_JSON, report)
    write_text(run_dir / AGENT_TRAJECTORY_MD, render_agent_trajectory_markdown(report))
    return report


def build_agent_trajectory_report(topic: str, run_dir: Path) -> dict[str, Any]:
    state = _read_json(run_dir / "state.json")
    manifest = _read_json(run_dir / "run-manifest.json")
    events = _dicts(manifest.get("events"))
    backfilled_events = _backfilled_event_count(events)
    phases = [_phase_report(spec, run_dir, events) for spec in PHASES]
    blocking = _unique(item for phase in phases for item in phase["blocking_issues"])
    manual = _unique(item for phase in phases for item in phase["manual_tasks"])
    phase_counts = {status: sum(1 for phase in phases if phase["status"] == status) for status in ["pass", "warn", "block", "not_started"]}
    status = "block" if phase_counts["block"] else "warn" if phase_counts["warn"] or manual else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "generated_at": _utc_now(),
        "run_dir": str(run_dir),
        "summary": {
            "state_stage": str(state.get("stage") or ""),
            "manifest_status": str(manifest.get("status") or ""),
            "event_count": len(events),
            "backfilled_events": backfilled_events,
            "artifact_count": len(_dicts(manifest.get("artifacts"))),
            "last_event": str(events[-1].get("stage") or "") if events else "",
            "phase_counts": phase_counts,
            "blocking_issues": len(blocking),
            "manual_tasks": len(manual),
        },
        "phases": phases,
        "timeline": [_timeline_event(index, event) for index, event in enumerate(events, start=1)],
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "recommended_actions": _recommended_actions(status, phases, blocking, manual),
    }


def render_agent_trajectory_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    counts = summary.get("phase_counts") if isinstance(summary.get("phase_counts"), dict) else {}
    lines = [
        f"# Agent Trajectory：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- Run 目录：{report.get('run_dir') or '-'}",
        f"- 当前阶段：{summary.get('state_stage') or '-'} / manifest={summary.get('manifest_status') or '-'}",
        f"- 事件/产物：{summary.get('event_count', 0)}/{summary.get('artifact_count', 0)}；backfilled={summary.get('backfilled_events', 0)}",
        f"- 阶段 pass/warn/block/not_started：{counts.get('pass', 0)}/{counts.get('warn', 0)}/{counts.get('block', 0)}/{counts.get('not_started', 0)}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("recommended_actions", "推荐动作")]:
        values = [str(item) for item in report.get(key, []) if str(item).strip()] if isinstance(report.get(key), list) else []
        if values:
            lines.append(f"## {title}")
            prefix = "- [ ] " if key in {"manual_tasks", "recommended_actions"} else "- "
            lines.extend(prefix + item for item in values)
            lines.append("")
    lines.extend(["## 阶段轨迹", "| 阶段 | 状态 | 事件 | 最近事件 | 缺失产物 | Gate/审计 | 下一步 |", "| --- | --- | ---: | --- | --- | --- | --- |"])
    for phase in report.get("phases", []) if isinstance(report.get("phases"), list) else []:
        if not isinstance(phase, dict):
            continue
        gate = "；".join(str(item) for item in phase.get("gate_statuses", [])[:4]) if isinstance(phase.get("gate_statuses"), list) else ""
        missing = ", ".join(str(item) for item in phase.get("missing_artifacts", [])[:5]) if isinstance(phase.get("missing_artifacts"), list) else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(phase.get("name") or phase.get("phase_id") or "")),
                    _cell(str(phase.get("status") or "")),
                    str(phase.get("event_count") or 0),
                    _cell(str(phase.get("latest_stage") or "-")),
                    _cell(missing or "-"),
                    _cell(gate or "-"),
                    _cell(str(phase.get("next_action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Manifest Timeline", "| # | 阶段 | 状态 | 输出 | 指标 |", "| ---: | --- | --- | --- | --- |"])
    for event in report.get("timeline", []) if isinstance(report.get("timeline"), list) else []:
        if not isinstance(event, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(event.get("index") or ""),
                    _cell(str(event.get("stage") or "")),
                    _cell(str(event.get("status") or "")),
                    _cell(", ".join(str(item) for item in event.get("outputs", [])[:4]) if isinstance(event.get("outputs"), list) else "-"),
                    _cell(str(event.get("metrics_summary") or "-")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _phase_report(spec: dict[str, Any], run_dir: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    prefixes = [str(item) for item in spec.get("stage_prefixes", [])]
    phase_events = [event for event in events if _stage_matches(str(event.get("stage") or ""), prefixes)]
    required = [str(item) for item in spec.get("required_artifacts", [])]
    status_artifacts = [str(item) for item in spec.get("status_artifacts", [])]
    present = [artifact for artifact in required if (run_dir / artifact).exists()]
    missing = [artifact for artifact in required if artifact not in present]
    statuses: list[str] = []
    blocking: list[str] = []
    manual: list[str] = []
    for artifact in status_artifacts:
        data = _read_json(run_dir / artifact)
        if not data:
            continue
        artifact_statuses, artifact_blocking, artifact_manual = _artifact_signals(artifact, data)
        statuses.extend(artifact_statuses)
        blocking.extend(artifact_blocking)
        manual.extend(artifact_manual)
    touched = bool(phase_events or present or statuses)
    if not touched:
        status = "not_started"
    elif blocking or any(value in {"block", "blocked", "fail", "failed", "requires_human_evidence", "requires_revision", "blocked_repair_required"} for value in statuses):
        status = "block"
    elif missing or manual or any(_warn_status(value) for value in statuses):
        status = "warn"
    else:
        status = "pass"
    if missing and touched:
        manual.extend(f"{spec.get('id')}: 缺少关键产物 {artifact}" for artifact in missing)
    return {
        "phase_id": str(spec.get("id") or ""),
        "name": str(spec.get("name") or ""),
        "status": status,
        "event_count": len(phase_events),
        "latest_stage": str(phase_events[-1].get("stage") or "") if phase_events else "",
        "required_artifacts": required,
        "present_artifacts": present,
        "missing_artifacts": missing if touched else [],
        "gate_statuses": _unique(statuses),
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "next_action": str(spec.get("next_action") or ""),
    }


def _artifact_signals(artifact: str, data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    if artifact == "approval.json":
        approved = data.get("approved") is True
        statuses = ["pass" if approved else "block"]
        blocking = [] if approved else ["approval.json: review gate 尚未批准。"]
        manual: list[str] = []
        blocks = {str(item) for item in data.get("blocks", [])} if isinstance(data.get("blocks"), list) else set()
        if approved and not {"idea_generation", "experiment_planning", "experiment_execution"}.issubset(blocks):
            statuses.append("review_required")
            manual.append("approval.json: 未记录完整 blocks 范围。")
        return statuses, blocking, manual
    statuses = [str(data.get(key) or "").strip() for key in ["status", "decision", "outcome", "evidence_grade"] if str(data.get(key) or "").strip()]
    blocking = [f"{artifact}: {item}" for item in _list_values(data, "blocking_issues")]
    manual = [f"{artifact}: {item}" for item in [*_list_values(data, "manual_tasks"), *_list_values(data, "required_actions"), *_list_values(data, "warnings")]]
    for count_field in ["blocked", "blocked_citations", "blocking_issues", "unsupported_after", "deferred_tasks"]:
        if _count_value(data.get(count_field)) > 0:
            statuses.append("block")
    for count_field in ["review_required", "review_citations", "manual_tasks", "warnings", "weak_after"]:
        if _count_value(data.get(count_field)) > 0:
            statuses.append("review_required")
    return statuses, blocking, manual


def _timeline_event(index: int, event: dict[str, Any]) -> dict[str, Any]:
    metrics = event.get("metrics") if isinstance(event.get("metrics"), dict) else {}
    return {
        "index": index,
        "stage": str(event.get("stage") or ""),
        "status": str(event.get("status") or ""),
        "started_at": str(event.get("started_at") or ""),
        "completed_at": str(event.get("completed_at") or ""),
        "outputs": [str(item) for item in event.get("outputs", []) if str(item).strip()] if isinstance(event.get("outputs"), list) else [],
        "metrics_summary": "; ".join(f"{key}={value}" for key, value in list(metrics.items())[:6]) if metrics else "",
    }


def _backfilled_event_count(events: list[dict[str, Any]]) -> int:
    count = 0
    for event in events:
        metrics = event.get("metrics") if isinstance(event.get("metrics"), dict) else {}
        if str(event.get("status") or "") == "backfilled" or metrics.get("backfilled") is True:
            count += 1
    return count


def _recommended_actions(status: str, phases: list[dict[str, Any]], blocking: list[str], manual: list[str]) -> list[str]:
    if status == "block":
        first = next((phase for phase in phases if phase["status"] == "block"), {})
        return [f"先处理 `{first.get('phase_id') or 'unknown'}` 阶段阻断，再继续后续科研流程。", *blocking[:4]]
    if status == "warn":
        first = next((phase for phase in phases if phase["status"] == "warn"), {})
        return [f"人工核对 `{first.get('phase_id') or 'unknown'}` 阶段警告，确认缺失产物或待办是否可接受。", *manual[:4]]
    return ["当前阶段轨迹没有发现阻断；继续查看 scorecard、stage contract 和 repair queue。"]


def _stage_matches(stage: str, prefixes: list[str]) -> bool:
    return any(stage == prefix or stage.startswith(prefix + "_") or stage.startswith(prefix + "-") for prefix in prefixes)


def _warn_status(value: str) -> bool:
    return value in {"warn", "warning", "review_required", "needs_repair", "needs_evidence_upgrade", "needs_rescue_search", "needs_manual_seed", "needs_query_repair", "ready_for_human_polish", "needs_human_submission_review", "needs_human_release_metadata", "smoke_only", "local_experiment"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list_values(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _count_value(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
