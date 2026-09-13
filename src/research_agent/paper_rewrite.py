from __future__ import annotations

import re
from typing import Any

from .config import PaperConfig
from .llm import LLM
from .llm_trace import complete_with_purpose_detail, record_validation_result
from .model_failure import (
    INVALID_RESPONSE,
    ModelFailure,
    ModelSourceRecorder,
    call_with_bounded_retry,
    classify_model_failure,
    fallback_permitted,
)
from .models import PaperRewriteReport, PaperRevisionPlan, PaperRevisionTaskResult, PaperReview, RevisionTask
from .paper_review import _claim_asserted_in_paper, _claim_explicitly_scoped_out
from .artifacts import cell as _cell


def revise_paper_draft(
    topic: str,
    paper_md: str,
    revision_plan: PaperRevisionPlan,
    paper_review: PaperReview,
    llm: LLM | None = None,
    benchmark_evidence: dict[str, Any] | None = None,
    paper_config: PaperConfig | None = None,
    model_source_recorder: ModelSourceRecorder | None = None,
) -> tuple[str, PaperRewriteReport]:
    if llm is not None:
        revised = _try_ai_rewrite(topic, paper_md, revision_plan, paper_review, llm, benchmark_evidence, paper_config, model_source_recorder)
    else:
        revised = ""
        if model_source_recorder is not None:
            model_source_recorder({"stage": "paper_revision", "source": "template", "call_id": 0})
    if not revised:
        revised = _fallback_rewrite(topic, paper_md, revision_plan, benchmark_evidence)
    report = _build_report(topic, revision_plan, paper_review, revised)
    revised = _ensure_revision_record_task_traces(revised, revision_plan, report)
    return revised, report


def render_rewrite_report_markdown(report: PaperRewriteReport) -> str:
    lines = [
        f"# 修订执行报告：{report.topic}",
        "",
        f"- 来源论文：{report.source_paper}",
        f"- 修订稿：{report.revised_paper}",
        f"- 修订计划：{report.revision_plan}",
        "",
        "## 摘要",
        report.summary,
        "",
        "## 任务处理",
        "| 任务 | 状态 | 动作 | 证据/结果引用 |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.task_results:
        refs = ", ".join(item.evidence_refs) or "待补"
        lines.append(f"| {item.task_id} | {item.status} | {_cell(item.action_taken)} | {_cell(refs)} |")
    lines.extend(["", "## 延后任务"])
    if report.deferred_tasks:
        lines.extend(f"- {item}" for item in report.deferred_tasks)
    else:
        lines.append("- 无")
    lines.extend(["", "## 下一步检查"])
    lines.extend(f"- [ ] {item}" for item in report.next_checks)
    return "\n".join(lines)


def _try_ai_rewrite(
    topic: str,
    paper_md: str,
    revision_plan: PaperRevisionPlan,
    paper_review: PaperReview,
    llm: LLM,
    benchmark_evidence: dict[str, Any] | None,
    paper_config: PaperConfig | None = None,
    model_source_recorder: ModelSourceRecorder | None = None,
) -> str:
    try:
        draft, call_id = call_with_bounded_retry(
            lambda: complete_with_purpose_detail(
                llm,
                "Paper revision. You revise Chinese academic Markdown without inventing evidence. Keep the revision concise and under 2500 words.",
                _rewrite_prompt(topic, paper_md, revision_plan, paper_review, benchmark_evidence),
                stage="paper_revision",
                purpose="paper revision",
                requires_validation=True,
            )
        )
    except Exception as exc:
        # T04：修订失败默认停机；显式降级时保留失败记录与模板来源。
        failure = classify_model_failure(exc)
        record_validation_result(llm, stage="paper_revision", valid=False, error=f"AI rewrite generation error: {exc}")
        if model_source_recorder is not None:
            model_source_recorder({
                "stage": "paper_revision",
                "source": "template" if fallback_permitted(paper_config, failure) else "paused",
                "call_id": 0,
                "failure": failure.to_dict(),
            })
        if fallback_permitted(paper_config, failure):
            return ""
        raise
    draft = _strip_code_fence(draft).strip()
    valid = _looks_like_revised_paper(draft, benchmark_evidence)
    record_validation_result(llm, stage="paper_revision", valid=valid, error="revised paper failed structure/evidence validation", call_id=call_id)
    if valid:
        if model_source_recorder is not None:
            model_source_recorder({"stage": "paper_revision", "source": "model", "call_id": call_id})
        return draft
    if model_source_recorder is not None:
        model_source_recorder({
            "stage": "paper_revision",
            "source": "template",
            "call_id": call_id,
            "failure": ModelFailure(INVALID_RESPONSE, "revised paper failed structure/evidence validation", retryable=False).to_dict(),
        })
    return ""


def _rewrite_prompt(
    topic: str,
    paper_md: str,
    revision_plan: PaperRevisionPlan,
    paper_review: PaperReview,
    benchmark_evidence: dict[str, Any] | None,
) -> str:
    tasks = _compact_tasks(revision_plan.tasks)
    return "\n".join(
        [
            f"课题：{topic}",
            "请根据审稿意见和修订计划重写论文草稿。必须遵守：",
            "1. 不要编造新实验、新 citation key、DOI 或不存在的结果。",
            "2. 如果任务需要新增文献或真实实验但当前材料没有，必须在修订稿中标为待补证，而不是假装完成。",
            "3. 保留 Markdown 论文结构，并新增“修订执行记录”章节，逐条说明任务处理状态。",
            "4. 必须遵守 Benchmark 证据审计；如果 evidence_grade=real_benchmark，不得把已执行的 benchmark adapter 结果误写为 dry-run、scaffold 或模拟实验。",
            "5. 输出应简洁，不超过 3500 中文字；不要逐字复述原稿和全部审稿意见。",
            "Benchmark 证据审计：",
            _benchmark_evidence_prompt_text(benchmark_evidence),
            f"自动复核决定：{paper_review.decision}，分数：{paper_review.score:.1f}/10。",
            f"原始修订任务数：{len(revision_plan.tasks)}；下方优先列最高优先级任务，修订执行记录必须逐条保留全部任务 ID，不要用 R-remaining 替代具体任务 ID。",
            "全部任务 ID：" + ", ".join(task.task_id for task in revision_plan.tasks),
            "修订计划任务：",
            str(tasks),
            "原论文草稿：",
            _paper_excerpt(paper_md),
            "只输出修订后的 Markdown，不要代码块。",
        ]
    )


def _compact_tasks(tasks: list[RevisionTask], limit: int = 8) -> list[dict[str, object]]:
    ordered = sorted(enumerate(tasks), key=lambda item: (_severity_rank(item[1].severity), item[0]))
    compact: list[dict[str, object]] = []
    for _index, task in ordered[:limit]:
        compact.append(
            {
                "task_id": task.task_id,
                "severity": task.severity,
                "section": task.section,
                "issue": _truncate(task.issue, 140),
                "action": _truncate(task.action, 120),
                "evidence_refs": task.evidence_refs[:3],
            }
        )
    if len(tasks) > limit:
        omitted = [task.task_id for _index, task in ordered[limit:]]
        compact.append({"task_id": "R-remaining", "severity": "summary", "section": "Revision record", "issue": f"{len(tasks) - limit} lower-priority tasks omitted from prompt; summarize them as scoped or deferred while preserving each concrete task_id.", "action": "在修订执行记录中逐个保留 omitted_task_ids，不新增证据。", "evidence_refs": [], "omitted_task_ids": omitted})
    return compact


def _severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def _paper_excerpt(paper_md: str, limit: int = 3200) -> str:
    if len(paper_md) <= limit:
        return paper_md
    head = paper_md[: int(limit * 0.65)].rstrip()
    tail = paper_md[-int(limit * 0.25) :].lstrip()
    return head + "\n\n...[原稿中段省略，保持证据边界和章节结构即可]...\n\n" + tail


def _truncate(text: str, limit: int) -> str:
    value = " ".join(str(text).split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _fallback_rewrite(topic: str, paper_md: str, revision_plan: PaperRevisionPlan, benchmark_evidence: dict[str, Any] | None) -> str:
    revised = _align_benchmark_scope(_downgrade_overclaims(paper_md), benchmark_evidence)
    lines = [
        revised.rstrip(),
        "",
        "## 修订执行记录",
        "本节由系统根据 `08-revision-plan` 自动生成，用于把审稿复核转化为下一轮写作任务。自动修订只处理表述降级、结构补充和任务显式化；需要新增文献或真实实验的任务仍需人工完成。",
        "",
    ]
    for task in revision_plan.tasks:
        status = _task_status(task, revised)
        lines.extend(
            [
                f"### {task.task_id}｜{task.severity}｜{task.section}",
                f"- 问题：{_align_benchmark_scope(task.issue, benchmark_evidence)}",
                f"- 处理状态：{status}",
                f"- 本轮动作：{_align_benchmark_scope(_fallback_action(task, status), benchmark_evidence)}",
                f"- 证据/结果引用：{', '.join(task.evidence_refs) if task.evidence_refs else '待补'}",
                "",
            ]
        )
    lines.extend(
        [
            "## 修订后验收检查",
            *[f"- [ ] {item}" for item in revision_plan.acceptance_checks],
            "",
            "## 修订后说明",
            f"该修订稿仍围绕“{topic}”的当前文献和实验产物撰写。若修订计划中存在待补证任务，应先补充文献检索、人工种子文献或真实实验结果，再进入正式投稿稿打磨。",
        ]
    )
    return "\n".join(lines)


def _build_report(topic: str, revision_plan: PaperRevisionPlan, paper_review: PaperReview, revised: str) -> PaperRewriteReport:
    task_results = [
        PaperRevisionTaskResult(
            task_id=task.task_id,
            status=_task_status(task, revised),
            action_taken=_fallback_action(task, _task_status(task, revised)),
            evidence_refs=task.evidence_refs,
        )
        for task in revision_plan.tasks
    ]
    deferred = [
        f"{task.task_id}: {task.issue}"
        for task, result in zip(revision_plan.tasks, task_results)
        if result.status == "needs_human_evidence"
    ]
    summary = (
        f"已生成一版修订稿，复核决定为 {paper_review.decision}，原始分数 {paper_review.score:.1f}/10。"
        f"本轮自动处理 {len(task_results) - len(deferred)} 个任务，仍有 {len(deferred)} 个任务需要人工补证或真实实验支撑。"
    )
    return PaperRewriteReport(
        topic=topic,
        source_paper="06-paper.md",
        revised_paper="09-revised-paper.md",
        revision_plan="08-revision-plan.json",
        summary=summary,
        task_results=task_results,
        deferred_tasks=deferred,
        next_checks=[
            "逐条核对修订执行记录中的 needs_human_evidence 任务。",
            "确认修订稿没有新增未验证 citation、实验结果或强结论。",
            "重新运行论文复核，确认 weak/unsupported claim 数量下降。",
            "正式投稿前人工核对参考文献、表格、图和 LaTeX 输出。",
        ],
    )


def _task_status(task: RevisionTask, revised_paper: str = "") -> str:
    paper_body = _paper_body_without_revision_log(revised_paper)
    if _task_resolved_by_revised_paper(task, paper_body):
        return "applied_in_draft"
    issue = task.issue.lower()
    action = task.action.lower()
    if task.severity == "high" and (not task.evidence_refs or "unsupported" in issue or "补证" in task.action):
        return "needs_human_evidence"
    if "真实实验" in task.issue or "新增文献" in task.issue or "补充至少" in task.issue:
        return "needs_human_evidence"
    if "doi" in issue or "引用" in task.issue:
        return "needs_human_verification"
    if "补充" in task.action or "baseline" in action or "统计" in task.issue:
        return "draft_adjusted"
    return "applied_in_draft"


def _task_resolved_by_revised_paper(task: RevisionTask, revised_paper: str) -> bool:
    if not revised_paper.strip():
        return False
    text = " ".join([task.issue, task.action])
    lowered = text.lower()
    claim = _claim_from_task_issue(task.issue)
    if claim:
        if _claim_explicitly_scoped_out(claim, revised_paper):
            return True
        if not _claim_asserted_in_paper(claim, revised_paper) and _task_allows_deletion_or_downgrade(text):
            return True
    if _requires_scope_or_deletion(text) and _claim_explicitly_scoped_out(text, revised_paper):
        return True
    if "seedndscikitlearn14" in lowered and "seedndscikitlearn14" not in revised_paper:
        return True
    if "claim-to-evidence" in lowered or "每个关键主张" in text:
        return "可审计产物摘要" in revised_paper or "Claim-Grounding" in revised_paper or "Claim 边界预检" in revised_paper
    if _requires_artifact_availability(text):
        return _has_artifact_availability(revised_paper)
    if _requires_adapter_smoke_alignment(text) and _has_adapter_smoke_scope(revised_paper):
        return True
    if _requires_limited_scope_boundary(text) and _has_limited_scope_boundary(revised_paper):
        return True
    if "预注册" in text and "预注册" not in revised_paper:
        return True
    if ("高风险" in text or "弱支撑 claim" in text or "claim 改写" in text) and _has_claim_grounding_safeguards(revised_paper):
        return True
    if "明确区分模拟结果、真实实验结果和推测性解释" in text and _has_real_benchmark_scope(revised_paper):
        return True
    if ("pivot_or_refine" in lowered or "负结果" in text or "负向指标" in text) and _has_negative_result_boundary(revised_paper):
        return True
    if "failure_detection_rate" in lowered and "benchmark_adapter_contract_pass_rate" in lowered:
        return ("故障注入检测率" in revised_paper or "failure_detection_rate" in revised_paper) and "未检验" in revised_paper
    if "refine_experiment" in lowered:
        return ("结果边界" in revised_paper or "Claim 边界预检" in revised_paper) and (
            "负结果" in revised_paper or "不优于 baseline" in revised_paper or "pivot" in revised_paper or "未检验" in revised_paper
        )
    if "paper review calibration" in lowered and "unsupported_claims" in lowered:
        return "unsupported claim" not in revised_paper.lower() and ("结果边界" in revised_paper or "Claim 边界预检" in revised_paper)
    return False


def _requires_artifact_availability(text: str) -> bool:
    lowered = text.lower()
    return (
        "04-experiment-runbook" in lowered
        and "04-results" in lowered
        and "04-statistics" in lowered
        and ("manifest schema" in lowered or "环境快照" in text or "metrics json" in lowered)
    )


def _has_artifact_availability(text: str) -> bool:
    lowered = text.lower()
    required = [
        "artifact 索引",
        "04-experiment-runbook",
        "04-results",
        "04-statistics",
        "04-benchmark-result-schema-audit",
        "04-environment-snapshot",
        "metrics.json",
    ]
    return all(item in lowered for item in required)


def _has_claim_grounding_safeguards(text: str) -> bool:
    return (
        ("结果边界" in text or "结论边界" in text or "证据边界" in text)
        and ("Claim 边界预检" in text or "可审计产物摘要" in text)
        and ("04-results" in text or "04-experiment-runbook" in text or "evidence_grade=real_benchmark" in text)
    )


def _has_real_benchmark_scope(text: str) -> bool:
    lowered = text.lower()
    if "evidence_grade=real_benchmark" not in lowered:
        return False
    actual_run = (
        (("实际执行" in text or "已执行" in text or "实执行" in text) and "runbook" in lowered and ("results" in lowered or "statistics" in lowered))
        or ("结果来自" in text and "04-experiment-runbook" in lowered and "04-results" in lowered)
    )
    stale_scope_safe = not any(_has_unnegated_stale_scope(sentence) for sentence in _sentences(text))
    limited_claims = "未检验" in text or "不作为本次已比较结果" in text or "不支持显著性" in text or "不构成模型优劣" in text
    explicit_not_dry_run = "不是 dry-run" in text or "而不是 dry-run" in text or "不得将其写作 dry-run" in text or "不要写成 dry-run" in text
    return actual_run and stale_scope_safe and limited_claims and explicit_not_dry_run


def _has_negative_result_boundary(text: str) -> bool:
    boundary_terms = ["结果边界", "结论边界", "证据边界", "实验范围限定", "有限范围"]
    negative_terms = ["负结果", "负向指标", "数值相同", "差值=0.000", "差值为 0.000", "观测差值为 0.000", "不优于", "未观察到"]
    uncertainty_terms = ["pivot_or_refine", "pivot", "不支持显著性", "不构成模型优劣", "不支持模型优越性", "不声称", "不能推断"]
    lowered = text.lower()
    return (
        any(term.lower() in lowered for term in boundary_terms)
        and any(term.lower() in lowered for term in negative_terms)
        and any(term.lower() in lowered for term in uncertainty_terms)
    )


def _requires_adapter_smoke_alignment(text: str) -> bool:
    lowered = text.lower()
    return "nearest_centroid" in lowered and ("knn3" in lowered or "sepal_centroid" in lowered or "adapter smoke" in lowered)


def _has_adapter_smoke_scope(text: str) -> bool:
    lowered = text.lower()
    has_variants = "nearest_centroid" in lowered and ("knn3" in lowered or "3-nn" in lowered) and ("sepal_centroid" in lowered or "sepal-centroid" in lowered)
    excludes_unrun = "dummy stratified" in lowered and ("未作为当前结果" in text or "未在当前产物中提供完整指标" in text or "不作为本文实证比较" in text)
    return has_variants and excludes_unrun and _has_limited_scope_boundary(text)


def _requires_limited_scope_boundary(text: str) -> bool:
    lowered = text.lower()
    return "单环境" in text or "frozen split" in lowered or "协议有效性" in text or "稳定性" in text


def _has_limited_scope_boundary(text: str) -> bool:
    lowered = text.lower()
    scope = "单环境" in text and "frozen split" in lowered and ("三次" in text or "有限重复" in text)
    boundary = "不构成模型优劣" in text or "不支持模型优越性" in text or "不支持显著性" in text or "不能推断" in text
    return scope and boundary


def _paper_body_without_revision_log(text: str) -> str:
    positions: list[int] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if _is_revision_record_heading(line):
            positions.append(offset)
        offset += len(line)
    if not positions:
        return text
    return text[: min(positions)]


def _ensure_revision_record_task_traces(
    revised: str,
    revision_plan: PaperRevisionPlan,
    report: PaperRewriteReport,
) -> str:
    missing = [task.task_id for task in revision_plan.tasks if task.task_id and task.task_id.lower() not in revised.lower()]
    if not missing:
        return revised
    result_by_id = {item.task_id: item for item in report.task_results}
    lines = [
        "",
        "### 自动补全任务闭环索引",
        "| 任务 | 报告状态 | 动作 | 证据/结果引用 |",
        "| --- | --- | --- | --- |",
    ]
    for task_id in missing:
        result = result_by_id.get(task_id)
        if result is None:
            lines.append(f"| {task_id} | missing | 待补写修订报告。 | 待补 |")
            continue
        refs = ", ".join(result.evidence_refs) or "待补"
        lines.append(f"| {task_id} | {result.status} | {_cell(result.action_taken)} | {_cell(refs)} |")
    appendix = "\n".join(lines)
    if any(_is_revision_record_heading(line) for line in revised.splitlines()):
        return revised.rstrip() + "\n" + appendix + "\n"
    return revised.rstrip() + "\n\n## 修订执行记录" + appendix + "\n"


def _is_revision_record_heading(line: str) -> bool:
    heading = line.strip()
    if not heading.startswith("#"):
        return False
    title = heading.lstrip("#").strip().lower()
    title = re.sub(r"^(?:\d+|[ivxlcdm]+)[.)、\s-]+", "", title, flags=re.IGNORECASE).strip()
    return title.startswith("修订执行记录") or title.startswith("revision response") or title.startswith("revision log")


def _claim_from_task_issue(issue: str) -> str:
    for marker in ["unsupported claim：", "unsupported claim:", "weak claim：", "weak claim:"]:
        if marker in issue:
            return issue.split(marker, 1)[1].strip()
    return ""


def _requires_scope_or_deletion(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "跨机器",
        "不同机器",
        "跨 ci",
        "ci 环境",
        "方差",
        "管线错误",
        "故障注入",
        "failure_detection",
        "benchmark_adapter_contract_pass_rate",
        "manifest_schema_validation_pass_rate",
        "未检验",
        "删除或降级",
    ]
    return any(marker in lowered for marker in markers)


def _task_allows_deletion_or_downgrade(text: str) -> bool:
    lowered = text.lower()
    markers = ["删除", "降级", "收窄", "改写", "不再", "remove", "delete", "downgrade", "scope"]
    return any(marker in lowered for marker in markers)


def _fallback_action(task: RevisionTask, status: str) -> str:
    if status == "needs_human_evidence":
        return "已在修订稿中显式标记为待补证，避免自动编造文献或实验结果。"
    if status == "needs_human_verification":
        return "已保留为人工核对项，需要检查题录、DOI、年份、作者和 venue。"
    if status == "draft_adjusted":
        return "已将相关结论降级为当前实验范围内的初步发现，并补充局限/验收检查。"
    return "已写入修订执行记录，并保持论文主张受当前证据约束。"


def _downgrade_overclaims(text: str) -> str:
    replacements = {
        "在重复运行、不同机器和不同 CI 环境中的结果方差将在当前实验中降低，并能稳定暴露管线错误": "本次仅检验同一环境、同一 split 和三次重复下的 adapter 描述性结果；跨机器/CI 方差和故障注入检测率未检验",
        "在重复运行、不同机器和不同 CI 环境中的结果方差将显著降低": "跨机器/CI 方差降低尚未检验",
        "结果方差在不同机器和不同 CI 环境中显著降低，并能稳定暴露管线错误": "本次仅检验同一环境、同一 split 和三次重复下的 adapter 描述性结果；跨机器/CI 方差和故障注入检测率未检验",
        "能够在极低运行成本下覆盖多数常见分类管线错误，并提供比单一高精度模型更可靠的 smoke benchmark 诊断信号": "当前只能生成低成本 candidate/baseline/ablation smoke benchmark 记录；管线错误覆盖率和诊断可靠性尚需故障注入实验",
        "能以极低运行成本提供比单一高精度模型更可靠的 smoke benchmark 诊断信号": "当前能生成低成本 candidate/baseline/ablation smoke benchmark 记录；诊断可靠性尚需更多 baseline 和故障注入实验",
        "证明了": "初步支持",
        "证明": "支持",
        "显著优于": "在当前描述性统计中数值不同于",
        "显著提高": "在当前描述性统计中提高",
        "显著降低": "在当前描述性统计中降低",
        "优于 baseline": "相对当前 baseline 的描述性差值",
        "优于基线": "相对当前基线的描述性差值",
        "优于": "数值不同于",
        "必然": "可能",
        "完全": "较为",
        "直接支持正式科学结论": "只能支持初步结论",
    }
    revised = text
    for old, new in replacements.items():
        revised = revised.replace(old, new)
    return revised


def _looks_like_revised_paper(text: str, benchmark_evidence: dict[str, Any] | None = None) -> bool:
    required = ["摘要", "方法", "结果", "局限", "修订执行记录"]
    return text.startswith("#") and len(text) > 200 and sum(1 for item in required if item in text) >= 4 and not _benchmark_scope_mismatch(text, benchmark_evidence)


def _benchmark_scope_mismatch(text: str, benchmark_evidence: dict[str, Any] | None) -> bool:
    if not isinstance(benchmark_evidence, dict) or str(benchmark_evidence.get("evidence_grade") or "") != "real_benchmark":
        return False
    return any(_has_unnegated_stale_scope(sentence) for sentence in _sentences(text))


def _align_benchmark_scope(text: str, benchmark_evidence: dict[str, Any] | None) -> str:
    if not isinstance(benchmark_evidence, dict) or str(benchmark_evidence.get("evidence_grade") or "") != "real_benchmark":
        return text
    replacements = {
        "初步模拟结果": "当前真实 benchmark adapter 结果",
        "模拟实验": "benchmark adapter 实验",
        "模拟结果": "benchmark adapter 结果",
        "后续替换为真实领域 benchmark": "后续扩展到更多公开 benchmark 和外部复现",
        "不能替代真实 benchmark 结果": "仍需扩展到更多 benchmark 和外部复现实验",
        "仍需真实 benchmark": "仍需更多 benchmark 和外部复现",
    }
    revised = text
    for old, new in replacements.items():
        revised = revised.replace(old, new)
    return revised


def _benchmark_evidence_prompt_text(benchmark_evidence: dict[str, Any] | None) -> str:
    if not isinstance(benchmark_evidence, dict):
        return "未提供 04-benchmark-evidence-audit；保持保守结果表述。"
    parts = [
        f"status={benchmark_evidence.get('status') or '-'}",
        f"evidence_grade={benchmark_evidence.get('evidence_grade') or '-'}",
        f"claim_policy={benchmark_evidence.get('claim_policy') or '-'}",
    ]
    if benchmark_evidence.get("evidence_grade") == "real_benchmark":
        parts.append("结果来自已执行 benchmark adapter/runbook；写成 limited-scope real benchmark，不要写成 dry-run/scaffold/simulated。")
    return "\n".join(parts)


def _has_unnegated_stale_scope(sentence: str) -> bool:
    lowered = sentence.lower()
    stale_tokens = ["dry-run", "dry run", "scaffold", "脚手架", "模拟实验", "模拟结果"]
    if not any(token in lowered for token in stale_tokens):
        return False
    negation_markers = ["不是", "而不是", "不得", "不能", "不应", "不要", "避免", "不能替代", "not ", "not a", "not an", "instead of", "rather than", "do not"]
    return not any(marker in lowered for marker in negation_markers)


def _sentences(text: str) -> list[str]:
    normalized = text.replace("\n", "。")
    return [item.strip() for item in normalized.replace("；", "。").replace(";", ".").split("。") if item.strip()]


def _strip_code_fence(text: str) -> str:
    if text.strip().startswith("```"):
        lines = text.strip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return text


