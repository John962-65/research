from __future__ import annotations

from .evidence_integrity import EvidenceIntegrity
from .models import ClaimTraceabilityReport, CodeDataAvailabilityReport, FinalReadinessReport, PaperRewriteReport, PaperReview, SubmissionCheckReport


def build_final_readiness_report(
    topic: str,
    original_review: PaperReview,
    revised_review: PaperReview,
    rewrite_report: PaperRewriteReport,
    availability_report: CodeDataAvailabilityReport | None = None,
    submission_report: SubmissionCheckReport | None = None,
    traceability_report: ClaimTraceabilityReport | None = None,
    evidence_integrity: EvidenceIntegrity | None = None,
    gate_decision: dict | None = None,
) -> FinalReadinessReport:
    unsupported_before = _count_support(original_review, "unsupported")
    unsupported_after = _count_support(revised_review, "unsupported")
    weak_before = _count_support(original_review, "weak")
    raw_weak_after = _count_support(revised_review, "weak")
    weak_after = _effective_weak_after(raw_weak_after, traceability_report)
    structured_audits_ready = _structured_audits_ready(
        revised_review,
        rewrite_report,
        unsupported_after,
        availability_report,
        submission_report,
        traceability_report,
        evidence_integrity,
    )
    blocking = _blocking_issues(
        revised_review,
        rewrite_report,
        unsupported_after,
        weak_after,
        availability_report,
        submission_report,
        traceability_report,
        evidence_integrity,
        structured_audits_ready,
    )
    status = _status(
        revised_review,
        rewrite_report,
        blocking,
        unsupported_after,
        weak_after,
        availability_report,
        submission_report,
        traceability_report,
        evidence_integrity,
        structured_audits_ready,
    )
    report = FinalReadinessReport(
        topic=topic,
        status=status,
        score_before=original_review.score,
        score_after=revised_review.score,
        unsupported_before=unsupported_before,
        unsupported_after=unsupported_after,
        weak_before=weak_before,
        weak_after=weak_after,
        deferred_tasks=rewrite_report.deferred_tasks,
        blocking_issues=blocking,
        recommendation=_recommendation(status, original_review, revised_review, unsupported_before, unsupported_after, weak_before, weak_after, availability_report, traceability_report),
        next_actions=_next_actions(status, rewrite_report, revised_review.score, unsupported_after, weak_after, availability_report, submission_report, traceability_report, evidence_integrity=evidence_integrity),
        availability_status=availability_report.status if availability_report is not None else "",
        availability_blocking_issues=availability_report.blocking_issues if availability_report is not None else [],
        availability_manual_tasks=availability_report.manual_tasks if availability_report is not None else [],
        submission_status=submission_report.status if submission_report is not None else "",
        submission_blocking_issues=submission_report.blocking_issues if submission_report is not None else [],
        submission_manual_tasks=submission_report.manual_tasks if submission_report is not None else [],
        traceability_status=traceability_report.status if traceability_report is not None else "",
        traceability_blocking_issues=traceability_report.blocking_issues if traceability_report is not None else [],
        traceability_manual_tasks=traceability_report.manual_tasks if traceability_report is not None else [],
    )
    return apply_gate_to_final_readiness(report, gate_decision)


def apply_gate_to_final_readiness(
    report: FinalReadinessReport,
    gate_decision: dict | None,
) -> FinalReadinessReport:
    """GATE-02: a blocked aggregate decision forbids a publishable readiness."""
    if not gate_decision:
        return report
    status = str(gate_decision.get("status") or "")
    sources = [str(item) for item in gate_decision.get("blocking_sources") or []]
    if status != "blocked" or not sources:
        return report
    blocking = list(dict.fromkeys([*report.blocking_issues, *(f"gate:{source}" for source in sources)]))
    recommendation = report.recommendation
    if not report.overridden:
        recommendation = "最终 Gate 决策为 blocked：在完成修复或提供带 reviewer/reason/revision/verdict 哈希的人工 override 前，不允许 publishable handoff。"
    from dataclasses import replace as _replace

    return _replace(
        report,
        status="blocked",
        blocking_issues=blocking,
        recommendation=recommendation,
        gate_status=status,
        overridden=report.overridden or bool(gate_decision.get("overridden")),
    )


def render_final_readiness_markdown(report: FinalReadinessReport) -> str:
    lines = [
        f"# 最终就绪报告：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 复核分数：{report.score_before:.1f}/10 -> {report.score_after:.1f}/10",
        f"- Unsupported claims：{report.unsupported_before} -> {report.unsupported_after}",
        f"- Weak claims：{report.weak_before} -> {report.weak_after}",
        f"- 延后任务：{len(report.deferred_tasks)}",
        f"- 代码/数据可用性：{report.availability_status or '未审计'}",
        f"- 投稿格式检查：{report.submission_status or '未审计'}",
        f"- Claim Traceability：{report.traceability_status or '未审计'}",
        "",
        "## 建议",
        report.recommendation,
        "",
        "## 阻断问题",
    ]
    if report.blocking_issues:
        lines.extend(f"- {item}" for item in report.blocking_issues)
    else:
        lines.append("- 无自动检测到的阻断问题")
    lines.extend(["", "## 下一步动作"])
    lines.extend(f"- [ ] {item}" for item in report.next_actions)
    if report.deferred_tasks:
        lines.extend(["", "## 延后任务明细"])
        lines.extend(f"- {item}" for item in report.deferred_tasks)
    if report.availability_blocking_issues or report.availability_manual_tasks:
        lines.extend(["", "## 代码/数据可用性待办"])
        lines.extend(f"- [ ] {item}" for item in report.availability_blocking_issues)
        lines.extend(f"- [ ] {item}" for item in report.availability_manual_tasks)
    if report.submission_blocking_issues or report.submission_manual_tasks:
        lines.extend(["", "## 投稿格式待办"])
        lines.extend(f"- [ ] {item}" for item in report.submission_blocking_issues)
        lines.extend(f"- [ ] {item}" for item in report.submission_manual_tasks)
    if report.traceability_blocking_issues or report.traceability_manual_tasks:
        lines.extend(["", "## Claim Traceability 待办"])
        lines.extend(f"- [ ] {item}" for item in report.traceability_blocking_issues)
        lines.extend(f"- [ ] {item}" for item in report.traceability_manual_tasks)
    return "\n".join(lines)


def _count_support(review: PaperReview, support_level: str) -> int:
    return sum(1 for item in review.claim_audit if item.support_level == support_level)


def _blocking_issues(
    revised_review: PaperReview,
    rewrite_report: PaperRewriteReport,
    unsupported_after: int,
    weak_after: int,
    availability_report: CodeDataAvailabilityReport | None,
    submission_report: SubmissionCheckReport | None,
    traceability_report: ClaimTraceabilityReport | None,
    evidence_integrity: EvidenceIntegrity | None = None,
    structured_audits_ready: bool = False,
) -> list[str]:
    issues: list[str] = []
    if evidence_integrity is not None and not evidence_integrity.real_experiment:
        issues.append("实验结果为模拟/占位数据或未通过真实性校验，不能支撑任何性能或比较结论；正式投稿前必须接入真实 benchmark 并重跑。")
    if unsupported_after:
        issues.append(f"修订稿仍有 {unsupported_after} 条 unsupported claim。")
    if weak_after >= 3:
        issues.append(f"修订稿仍有 {weak_after} 条 weak claim，需要继续收窄或补证。")
    if _deferred_tasks_block(rewrite_report, revised_review, unsupported_after, traceability_report):
        issues.append(f"修订执行报告中仍有 {len(rewrite_report.deferred_tasks)} 个 needs_human_evidence 延后任务。")
    if revised_review.score < 6 and not structured_audits_ready:
        issues.append(f"修订稿复核分数仍低于 6/10：{revised_review.score:.1f}。")
    if availability_report is not None:
        issues.extend(availability_report.blocking_issues)
    if submission_report is not None:
        issues.extend(submission_report.blocking_issues)
    if traceability_report is not None:
        issues.extend(traceability_report.blocking_issues)
        if traceability_report.status == "block":
            issues.append(f"Claim traceability 仍有 {traceability_report.blocked_claims} 条阻断 claim。")
    return issues


def _status(
    revised_review: PaperReview,
    rewrite_report: PaperRewriteReport,
    blocking: list[str],
    unsupported_after: int,
    weak_after: int,
    availability_report: CodeDataAvailabilityReport | None,
    submission_report: SubmissionCheckReport | None,
    traceability_report: ClaimTraceabilityReport | None,
    evidence_integrity: EvidenceIntegrity | None = None,
    structured_audits_ready: bool = False,
) -> str:
    if evidence_integrity is not None and not evidence_integrity.real_experiment:
        return "requires_real_experiment"
    availability_blocked = availability_report is not None and availability_report.status == "blocked"
    submission_blocked = submission_report is not None and submission_report.status == "blocked"
    traceability_blocked = traceability_report is not None and traceability_report.status == "block"
    if unsupported_after or _deferred_tasks_block(rewrite_report, revised_review, unsupported_after, traceability_report) or availability_blocked or traceability_blocked:
        return "requires_human_evidence"
    if submission_blocked or blocking or weak_after or (revised_review.score < 7 and not structured_audits_ready):
        return "requires_revision"
    if traceability_report is not None and traceability_report.status == "review_required":
        return "requires_revision"
    if revised_review.score < 8:
        return "ready_for_human_polish"
    return "ready_for_submission_check"


def _deferred_tasks_block(
    rewrite_report: PaperRewriteReport,
    revised_review: PaperReview,
    unsupported_after: int,
    traceability_report: ClaimTraceabilityReport | None,
) -> bool:
    if not rewrite_report.deferred_tasks:
        return False
    if unsupported_after:
        return True
    if revised_review.score < 7:
        return True
    if traceability_report is None:
        return True
    return traceability_report.status == "block"


def _effective_weak_after(raw_weak_after: int, traceability_report: ClaimTraceabilityReport | None) -> int:
    if raw_weak_after <= 0:
        return 0
    if _traceability_fully_passed(traceability_report):
        return 0
    return raw_weak_after


def _structured_audits_ready(
    revised_review: PaperReview,
    rewrite_report: PaperRewriteReport,
    unsupported_after: int,
    availability_report: CodeDataAvailabilityReport | None,
    submission_report: SubmissionCheckReport | None,
    traceability_report: ClaimTraceabilityReport | None,
    evidence_integrity: EvidenceIntegrity | None,
) -> bool:
    if unsupported_after or rewrite_report.deferred_tasks:
        return False
    if evidence_integrity is not None and not evidence_integrity.real_experiment:
        return False
    if not _traceability_fully_passed(traceability_report):
        return False
    if availability_report is not None and availability_report.status == "blocked":
        return False
    if submission_report is not None and submission_report.status == "blocked":
        return False
    return bool(revised_review.claim_audit)


def _traceability_fully_passed(traceability_report: ClaimTraceabilityReport | None) -> bool:
    if traceability_report is None:
        return False
    return (
        traceability_report.status == "pass"
        and traceability_report.total_claims > 0
        and traceability_report.passed_claims == traceability_report.total_claims
        and traceability_report.blocked_claims == 0
        and traceability_report.review_claims == 0
        and not traceability_report.blocking_issues
        and not traceability_report.manual_tasks
    )


def _recommendation(
    status: str,
    original_review: PaperReview,
    revised_review: PaperReview,
    unsupported_before: int,
    unsupported_after: int,
    weak_before: int,
    weak_after: int,
    availability_report: CodeDataAvailabilityReport | None,
    traceability_report: ClaimTraceabilityReport | None,
) -> str:
    delta = revised_review.score - original_review.score
    claim_delta = (unsupported_before + weak_before) - (unsupported_after + weak_after)
    if status == "requires_real_experiment":
        return (
            "本 run 的实验证据未通过真实性校验（模拟、失败或来源不可核验），实验结果不能作为科学结论或进入投稿核查。"
            "请接入真实 benchmark 重跑并产出可用结果后，再评估就绪度；"
            "论文文本来源（模型/模板/人工）单独记录在 04-evidence-integrity，不与实验证据混判。"
        )
    if status == "requires_human_evidence":
        availability_note = _availability_note(availability_report)
        return (
            f"修订稿分数变化为 {delta:+.1f}，弱/未支撑 claim 总数变化为 {claim_delta:+d}。"
            f"仍存在需要人工补文献、真实实验或可用性材料的阻断项，暂不应进入投稿稿打磨。{availability_note}{_traceability_note(traceability_report)}"
        )
    if status == "requires_revision":
        reasons: list[str] = []
        if weak_after:
            reasons.append(f"仍有 {weak_after} 条 weak claim")
        if revised_review.score < 7:
            reasons.append(f"复核分数仍低于 7/10（{revised_review.score:.1f}）")
        if traceability_report is not None and traceability_report.status == "review_required":
            reasons.append("claim traceability 仍需人工复核")
        reason_text = "，".join(reasons) if reasons else "仍有修订或人工核查事项"
        return (
            f"修订稿分数变化为 {delta:+.1f}，但{reason_text}。"
            "建议继续执行一轮修订计划，优先处理复核意见指出的贡献边界、实验限制和复现材料。"
        )
    if status == "ready_for_human_polish":
        return "自动复核未发现硬阻断项，但分数尚未达到投稿前标准，建议人工做语言、格式、引用和图表层面的打磨。"
    return "自动复核未发现硬阻断项，下一步进入人工投稿前核查：引用、数据、代码、伦理和格式。"


def _next_actions(
    status: str,
    rewrite_report: PaperRewriteReport,
    revised_score: float,
    unsupported_after: int,
    weak_after: int,
    availability_report: CodeDataAvailabilityReport | None,
    submission_report: SubmissionCheckReport | None,
    traceability_report: ClaimTraceabilityReport | None,
    evidence_integrity: EvidenceIntegrity | None = None,
) -> list[str]:
    if status == "requires_real_experiment":
        return [
            "接入真实 LLM 端点（配置 llm.model/base_url/api_key），确认 run-llm-ledger.json 记录到成功调用。",
            "用真实 benchmark 适配器（execution.mode=benchmark + manifest）替换模拟实验，产出非 simulated 的 04-results。",
            "重跑流水线后再评估 final-readiness；在此之前不得进入投稿前核查或打包。",
        ]
    if status == "requires_human_evidence":
        actions = [
            "补齐所有 needs_human_evidence 任务所需的文献、数据或真实实验结果。",
            "删除或降级所有无法补证的 unsupported claim。",
            "补证后重新运行 resume，生成新的修订稿和最终就绪报告。",
        ]
        if rewrite_report.deferred_tasks:
            actions.append("优先处理 09-revision-report.md 的延后任务明细。")
        if availability_report is not None and (availability_report.blocking_issues or availability_report.manual_tasks):
            actions.append("按 10-code-data-availability.md 补齐代码仓库、许可证、数据来源、复现入口和公开归档信息。")
        if submission_report is not None and (submission_report.blocking_issues or submission_report.manual_tasks):
            actions.append("按 10-submission-check.md 处理 LaTeX、参考文献、图表和目标模板待办。")
        if traceability_report is not None and (traceability_report.blocking_issues or traceability_report.manual_tasks):
            actions.append("按 10-claim-traceability.md 删除、降级或补证没有可追踪证据的 claim。")
        return actions
    if status == "requires_revision":
        actions: list[str] = []
        if unsupported_after or weak_after:
            actions.append(f"继续处理剩余 claim-grounding 问题：unsupported={unsupported_after}, weak={weak_after}。")
        if revised_score < 7:
            actions.append("根据 10-revised-paper-review.md 的 weaknesses 继续修订贡献范围、固定 split 限制、baseline 覆盖和公开复现路径。")
        if traceability_report is not None and traceability_report.manual_tasks:
            actions.append("逐条处理 10-claim-traceability.md 中 review_required 的 claim。")
        if not actions:
            actions.append("处理 final-readiness 关联审计中的 review_required 项，并重新生成最终就绪报告。")
        actions.extend(
            [
                "把结果段落改写到当前实验和统计审计能直接支持的范围。",
                "再次生成修订计划和修订稿，直到复核分数和人工 gate 达到目标。",
            ]
        )
        if availability_report is not None and availability_report.manual_tasks:
            actions.append("补齐代码/数据可用性人工待办，至少包含仓库 URL、许可证、数据访问说明和归档 DOI。")
        if submission_report is not None and (submission_report.blocking_issues or submission_report.manual_tasks):
            actions.append("按目标 venue 官方模板完成 LaTeX 和投稿格式人工检查。")
        return actions
    if status != "requires_real_experiment" and evidence_integrity is not None and not evidence_integrity.real_llm:
        return [
            "人工核对所有 citation key、DOI、年份、作者和 venue。",
            "核对数据/代码可用性、实验命令、随机种子和统计报告。",
            "检查 LaTeX 输出、章节结构、图表引用和投稿格式。",
            "论文文本未检测到成功的真实 LLM 调用（可能来自模板或人工撰写）；"
            "如需模型生成或独立评审证据，接入真实端点后重跑对应阶段。",
        ]
    return [
        "人工核对所有 citation key、DOI、年份、作者和 venue。",
        "核对数据/代码可用性、实验命令、随机种子和统计报告。",
        "检查 LaTeX 输出、章节结构、图表引用和投稿格式。",
    ]


def _availability_note(report: CodeDataAvailabilityReport | None) -> str:
    if report is None:
        return ""
    if report.status == "ready_for_submission_check":
        return ""
    return f" 代码/数据可用性状态为 {report.status}。"


def _traceability_note(report: ClaimTraceabilityReport | None) -> str:
    if report is None or report.status == "pass":
        return ""
    return f" Claim traceability 状态为 {report.status}。"
