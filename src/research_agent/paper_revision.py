from __future__ import annotations

from typing import Any

from .models import PaperClaimAudit, PaperRevisionPlan, PaperReview, RevisionTask
from .artifacts import cell as _cell


def build_paper_revision_plan(
    topic: str,
    paper_review: PaperReview,
    experiment_decision: dict[str, Any] | None = None,
    review_calibration: dict[str, Any] | None = None,
) -> PaperRevisionPlan:
    tasks: list[RevisionTask] = []
    for index, item in enumerate(paper_review.required_revisions, start=1):
        tasks.append(
            RevisionTask(
                task_id=f"R{index:02d}",
                section=_section_for_revision(item),
                severity=_severity_for_revision(item),
                issue=item,
                action=_action_for_revision(item),
                evidence_refs=[],
            )
        )

    next_index = len(tasks) + 1
    for audit in paper_review.claim_audit:
        if audit.support_level not in {"weak", "unsupported"}:
            continue
        tasks.append(_claim_task(next_index, audit))
        next_index += 1
    for task in _experiment_decision_tasks(next_index, experiment_decision):
        tasks.append(task)
        next_index += 1
    for task in _review_calibration_tasks(next_index, review_calibration):
        tasks.append(task)
        next_index += 1

    readiness = _readiness(paper_review, tasks)
    summary = _summary(paper_review, tasks, readiness)
    acceptance_checks = _acceptance_checks(tasks)
    return PaperRevisionPlan(
        topic=topic,
        decision=paper_review.decision,
        readiness=readiness,
        summary=summary,
        tasks=tasks,
        acceptance_checks=acceptance_checks,
        next_iteration_prompt=_next_iteration_prompt(topic, paper_review, tasks),
    )


def _review_calibration_tasks(start_index: int, review_calibration: dict[str, Any] | None) -> list[RevisionTask]:
    if not isinstance(review_calibration, dict):
        return []
    status = str(review_calibration.get("status") or "").strip()
    if status not in {"block", "review_required"}:
        return []
    actions = [str(item).strip() for item in review_calibration.get("required_actions", []) if str(item).strip()] if isinstance(review_calibration.get("required_actions"), list) else []
    flags = review_calibration.get("flags") if isinstance(review_calibration.get("flags"), list) else []
    blockers = [str(item.get("evidence") or item.get("name") or "").strip() for item in flags if isinstance(item, dict) and item.get("severity") == "block"]
    warnings = [str(item.get("evidence") or item.get("name") or "").strip() for item in flags if isinstance(item, dict) and item.get("severity") == "warn"]
    issue = f"Paper review calibration={status}; " + "；".join([*(blockers[:2]), *(warnings[:2])] or ["自动复核可能过宽。"])
    action = "；".join(actions[:3]) if actions else "下调复核结论，补证或降级过强 claim 后再进入投稿稿打磨。"
    return [
        RevisionTask(
            task_id=f"R{start_index:02d}",
            section="Review Calibration",
            severity="high" if status == "block" else "medium",
            issue=issue,
            action=action,
            evidence_refs=["07-paper-review-calibration", "07-paper-review", "04-hypothesis-outcome"],
        )
    ]


def _experiment_decision_tasks(start_index: int, experiment_decision: dict[str, Any] | None) -> list[RevisionTask]:
    if not isinstance(experiment_decision, dict):
        return []
    decision = str(experiment_decision.get("decision") or "").strip()
    if decision in {"", "proceed_to_paper"}:
        return []
    next_actions = [str(item).strip() for item in experiment_decision.get("next_actions", []) if str(item).strip()] if isinstance(experiment_decision.get("next_actions"), list) else []
    boundaries = [str(item).strip() for item in experiment_decision.get("claim_boundaries", []) if str(item).strip()] if isinstance(experiment_decision.get("claim_boundaries"), list) else []
    issue = f"实验后决策为 {decision}；" + ("；".join(next_actions[:3]) if next_actions else "需要人工复核实验后写作策略。")
    if boundaries:
        issue += " 结论边界：" + "；".join(boundaries[:3])
    severity = "high" if decision == "repair_before_writing" else "medium"
    action = {
        "repair_before_writing": "先修复实验验证/失败分析阻断项；修订稿不得把当前结果写成候选方法有效。",
        "pivot_or_refine": "在结果和结论中报告负结果，明确是否 pivot 或 refine，不得只保留正向指标。",
        "refine_experiment": "把结论降级为初步趋势，并列出下一轮需补重复、补任务或补指标。",
        "benchmark_upgrade": "明确当前结果只是 smoke/simulated 证据，正式主结论需真实 benchmark 后再写。",
    }.get(decision, "按 04-experiment-decision.md 收窄结果和结论。")
    return [
        RevisionTask(
            task_id=f"R{start_index:02d}",
            section="Experiments/Results",
            severity=severity,
            issue=issue,
            action=action,
            evidence_refs=["04-experiment-decision", "04-result-validation", "04-failure-analysis"],
        )
    ]


def render_paper_revision_plan_markdown(plan: PaperRevisionPlan) -> str:
    lines = [
        f"# 论文修订计划：{plan.topic}",
        "",
        f"- 复核决定：{plan.decision}",
        f"- 修订状态：{plan.readiness}",
        f"- 任务数：{len(plan.tasks)}",
        "",
        "## 摘要",
        plan.summary,
        "",
        "## 修订任务",
        "| ID | 严重性 | 章节 | 问题 | 动作 | 证据/结果引用 | 状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for task in plan.tasks:
        refs = ", ".join(task.evidence_refs) or "待补"
        lines.append(
            f"| {task.task_id} | {task.severity} | {_cell(task.section)} | {_cell(task.issue)} | {_cell(task.action)} | {_cell(refs)} | {task.status} |"
        )
    lines.extend(["", "## 验收检查"])
    lines.extend(f"- [ ] {item}" for item in plan.acceptance_checks)
    lines.extend(["", "## 下一轮修改提示", plan.next_iteration_prompt])
    return "\n".join(lines)


def _claim_task(index: int, audit: PaperClaimAudit) -> RevisionTask:
    severity = "high" if audit.support_level == "unsupported" or audit.risk == "high" else "medium"
    refs = _unique([*audit.evidence_keys, *audit.result_refs])
    action = (
        "补充直接支撑该 claim 的文献或实验结果；如果无法补证，删除该 claim 或改写为明确的局限/假设。"
        if audit.support_level == "unsupported"
        else "收窄该 claim 的表述，并补充更直接的 citation key、结果指标或局限说明。"
    )
    return RevisionTask(
        task_id=f"R{index:02d}",
        section="Claim-Grounding",
        severity=severity,
        issue=f"{audit.support_level} claim：{audit.claim}",
        action=action,
        evidence_refs=refs,
    )


def _readiness(paper_review: PaperReview, tasks: list[RevisionTask]) -> str:
    high = sum(1 for task in tasks if task.severity == "high")
    medium = sum(1 for task in tasks if task.severity == "medium")
    decision = paper_review.decision.lower()
    if high or "major" in decision or "reject" in decision or paper_review.score < 6:
        return "major_revision_required"
    if medium or "revise" in decision or paper_review.score < 8:
        return "revise_before_submission"
    return "ready_after_minor_checks"


def _summary(paper_review: PaperReview, tasks: list[RevisionTask], readiness: str) -> str:
    high = sum(1 for task in tasks if task.severity == "high")
    medium = sum(1 for task in tasks if task.severity == "medium")
    if readiness == "major_revision_required":
        return f"当前复核分数为 {paper_review.score:.1f}/10，存在 {high} 个高优先级和 {medium} 个中优先级修订任务，正式写作前应先完成证据补强和 claim 降级。"
    if readiness == "revise_before_submission":
        return f"当前复核分数为 {paper_review.score:.1f}/10，主要问题集中在证据表述、实验设置和局限说明，需要完成修订后再进入投稿稿打磨。"
    return f"当前复核分数为 {paper_review.score:.1f}/10，未发现阻断性修订任务，仍需人工完成格式、引用和结果一致性检查。"


def _acceptance_checks(tasks: list[RevisionTask]) -> list[str]:
    checks = [
        "所有 high/medium 修订任务都有明确处理记录。",
        "所有 unsupported claim 已补证、删除或降级为假设/局限。",
        "结果段落只陈述当前实验和统计审计能够支持的结论。",
        "方法、实验设置、baseline、随机种子、重复次数和统计指标可复现。",
        "引用 key、DOI、年份、作者和 venue 已人工核对。",
    ]
    if not tasks:
        checks.insert(0, "人工复核确认无新增必须修改项。")
    return checks


def _next_iteration_prompt(topic: str, paper_review: PaperReview, tasks: list[RevisionTask]) -> str:
    task_lines = "\n".join(f"- {task.task_id} [{task.severity}] {task.action} 问题：{task.issue}" for task in tasks)
    return "\n".join(
        [
            f"请基于课题“{topic}”修订论文草稿。",
            f"自动复核决定：{paper_review.decision}，分数：{paper_review.score:.1f}/10。",
            "必须逐条处理以下修订任务，并在修改后保留 claim 与文献/实验结果的对应关系：",
            task_lines or "- 暂无阻断性修订任务，执行格式、引用和一致性检查。",
        ]
    )


def _section_for_revision(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["claim", "主张", "支撑", "证据", "unsupported"]):
        return "Claim-Grounding"
    if any(term in lowered for term in ["实验", "baseline", "随机", "重复", "统计", "结果"]):
        return "Experiments/Results"
    if any(term in lowered for term in ["文献", "引用", "doi", "检索"]):
        return "Literature/Citations"
    return "Manuscript"


def _severity_for_revision(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["unsupported", "删除", "必须", "高风险"]):
        return "high"
    if any(term in lowered for term in ["补充", "明确", "统计", "baseline", "weak", "弱支撑"]):
        return "medium"
    return "low"


def _action_for_revision(text: str) -> str:
    section = _section_for_revision(text)
    if section == "Claim-Grounding":
        return "逐条检查对应 claim，补充直接证据；无法补证时删除或降级表述。"
    if section == "Experiments/Results":
        return "补齐实验设置、baseline、重复次数、统计检验和结果边界，避免过度解释。"
    if section == "Literature/Citations":
        return "补充高相关可引用文献，并人工核对题录、DOI、年份、作者和 venue。"
    return "在正文中完成该修改，并确认摘要、结论和局限部分保持一致。"


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


