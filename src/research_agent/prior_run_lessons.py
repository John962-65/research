from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .artifacts import write_json, write_text
from .run_memory import RunMemoryReport, RunMemorySignal, build_run_memory


PRIOR_RUN_LESSONS_JSON = "00-prior-run-lessons.json"
PRIOR_RUN_LESSONS_MD = "00-prior-run-lessons.md"


@dataclass(frozen=True)
class PriorRunLesson:
    category: str
    severity: str
    rationale: str
    action: str
    pipeline_targets: list[str] = field(default_factory=list)
    source_runs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PriorRunLessonsReport:
    topic: str
    status: str
    source_runs_dir: str
    analyzed_runs: int
    lessons: list[PriorRunLesson]
    recommended_defaults: list[str]
    manual_checklist: list[str]
    agent_prompt_text: str


def write_prior_run_lessons_artifacts(topic: str, runs_dir: Path, out_dir: Path, limit: int = 100) -> PriorRunLessonsReport:
    memory = build_run_memory(runs_dir, limit=limit)
    report = build_prior_run_lessons(topic, memory)
    write_json(out_dir / PRIOR_RUN_LESSONS_JSON, report)
    write_text(out_dir / PRIOR_RUN_LESSONS_MD, render_prior_run_lessons_markdown(report))
    return report


def build_prior_run_lessons(topic: str, memory: RunMemoryReport) -> PriorRunLessonsReport:
    lessons = [_lesson_from_signal(signal) for signal in memory.recurring_signals[:10]]
    lessons = [lesson for lesson in lessons if lesson is not None]
    status = _status(memory.status, lessons)
    prompt_text = _agent_prompt_text(memory, lessons)
    return PriorRunLessonsReport(
        topic=topic,
        status=status,
        source_runs_dir=memory.runs_dir,
        analyzed_runs=memory.analyzed_runs,
        lessons=lessons,
        recommended_defaults=memory.recommended_defaults[:8],
        manual_checklist=memory.next_run_checklist[:10],
        agent_prompt_text=prompt_text,
    )


def render_prior_run_lessons_markdown(report: PriorRunLessonsReport) -> str:
    lines = [
        f"# Prior Run Lessons：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 来源 runs：{report.source_runs_dir}",
        f"- 纳入历史 run：{report.analyzed_runs}",
        "",
        "## 本轮继承约束",
        "| 类别 | 严重性 | 目标阶段 | 来源 Runs | 理由 | 动作 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not report.lessons:
        lines.append("| 无 | - | - | - | 没有历史信号需要继承。 | - |")
    for lesson in report.lessons:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(lesson.category),
                    _cell(lesson.severity),
                    _cell(", ".join(lesson.pipeline_targets) or "-"),
                    _cell(", ".join(lesson.source_runs) or "-"),
                    _cell(lesson.rationale),
                    _cell(lesson.action),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 推荐默认设置"])
    lines.extend(f"- {item}" for item in report.recommended_defaults) if report.recommended_defaults else lines.append("- 暂无")
    lines.extend(["", "## 启动前人工检查"])
    lines.extend(f"- [ ] {item}" for item in report.manual_checklist) if report.manual_checklist else lines.append("- 暂无")
    lines.extend(["", "## 给 Agent 的继承文本"])
    lines.append(report.agent_prompt_text or "无历史经验需要继承。")
    return "\n".join(lines)


def _lesson_from_signal(signal: RunMemorySignal) -> PriorRunLesson | None:
    targets = _targets(signal.category)
    if not targets:
        return None
    action = signal.recommended_action or signal.next_run_hint
    if not action:
        return None
    rationale = "；".join(signal.evidence[:2]) if signal.evidence else signal.next_run_hint
    return PriorRunLesson(
        category=signal.category,
        severity=signal.severity,
        rationale=rationale,
        action=action,
        pipeline_targets=targets,
        source_runs=signal.run_ids[:5],
    )


def _targets(category: str) -> list[str]:
    mapping = {
        "llm_configuration": ["preflight", "research_plan"],
        "llm_trace_audit": ["preflight", "llm_trace_audit", "research_plan", "paper_review_loop"],
        "run_economics": ["preflight", "llm_budget", "run_economics", "agent_observability"],
        "agent_observability": ["preflight", "agent_trajectory", "agent_observability", "repair_resume"],
        "open_source_compliance": ["preflight", "open_source_lessons", "open_source_compliance", "repair_queue", "research_scorecard"],
        "agent_stage_contract": ["preflight", "agent_stage_contract", "repair_resume", "research_scorecard", "submission_package"],
        "research_scorecard": ["preflight", "research_scorecard", "next_iteration", "repair_resume", "submission_package"],
        "run_integrity_audit": ["preflight", "run_integrity_audit", "agent_trajectory", "repair_resume", "submission_package"],
        "final_handoff": ["preflight", "research_scorecard", "run_integrity_audit", "submission_package", "final_handoff", "repair_resume"],
        "repair_resolution_audit": ["preflight", "repair_resume", "repair_resolution_audit", "research_scorecard", "run_integrity_audit"],
        "run_failure": ["preflight", "resume"],
        "literature_repair": ["research_plan", "literature_search", "review_gate"],
        "literature_search_feedback": ["preflight", "research_plan", "literature_search", "literature_rerank", "review_gate"],
        "literature_rescue_execution": ["preflight", "literature_search", "literature_rescue_execution", "repair_queue", "review_gate"],
        "literature_source_health": ["preflight", "literature_search", "query_execution_audit", "literature_search_feedback", "review_gate"],
        "thin_evidence_pool": ["literature_search", "review_gate", "ideation"],
        "seed_paper_intake": ["literature_search", "review_gate", "ideation"],
        "result_validation": ["experiment_plan", "experiment_execution", "analysis"],
        "failure_or_negative_results": ["experiment_plan", "analysis", "writing"],
        "hypothesis_outcome": ["experiment_plan", "experiment_execution", "writing"],
        "experiment_manager": ["ideation", "experiment_manager", "experiment_plan"],
        "experiment_manager_smoke_first": ["experiment_manager", "experiment_plan", "experiment_execution"],
        "experiment_branch_backlog": ["prior_run_lessons", "ideation", "experiment_manager"],
        "review_constraints": ["human_brief", "ideation", "experiment_plan", "review_constraint_compliance"],
        "human_brief_constraints": ["human_brief", "ideation", "experiment_plan", "review_constraint_compliance"],
        "simulated_evidence": ["experiment_plan", "experiment_execution", "writing"],
        "benchmark_gap": ["experiment_plan", "benchmark_adapter"],
        "benchmark_result_schema": ["benchmark_adapter", "experiment_execution", "result_validation"],
        "environment_snapshot": ["experiment_execution", "environment_snapshot", "release", "submission_package"],
        "paper_gate": ["writing", "paper_revision", "final_readiness"],
        "revision_response": ["paper_revision", "submission_check", "submission_package"],
        "citation_grounding": ["writing", "paper_revision", "submission_check"],
        "citation_coverage": ["writing", "paper_revision", "submission_check"],
        "results_presentation": ["writing", "paper_revision", "submission_check"],
        "claim_boundary_preflight": ["writing", "paper_revision", "submission_check"],
        "claim_consistency": ["writing", "paper_revision", "submission_check"],
        "release_metadata": ["release", "submission_package"],
        "submission_packaging": ["paper_revision", "submission_check", "submission_package"],
        "human_gate_feedback": ["research_plan", "ideation", "experiment_plan"],
    }
    return mapping.get(category, [])


def _status(memory_status: str, lessons: list[PriorRunLesson]) -> str:
    if not lessons:
        return "no_prior_constraints" if memory_status == "empty" else "pass"
    if any(item.severity == "block" for item in lessons):
        return "carry_forward_required"
    if any(item.severity == "warn" for item in lessons):
        return "carry_forward_recommended"
    return "informational"


def _agent_prompt_text(memory: RunMemoryReport, lessons: list[PriorRunLesson]) -> str:
    if not lessons:
        return "历史 run 记忆未发现必须继承的约束；仍需保持人工 gate、citation grounding 和实验复现审计。"
    lines = [
        "历史 run 经验必须作为本轮约束处理，不要重复已暴露的问题：",
        f"- 历史记忆状态：{memory.status}；纳入 run：{memory.analyzed_runs}",
    ]
    for lesson in lessons[:8]:
        target = ", ".join(lesson.pipeline_targets)
        lines.append(f"- [{lesson.severity}] {lesson.category} -> {target}: {lesson.action}")
    if memory.recommended_defaults:
        lines.append("推荐默认设置：" + "；".join(memory.recommended_defaults[:4]))
    return "\n".join(lines)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
