from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import PaperRewriteReport, PaperRevisionPlan, PaperRevisionTaskResult, RevisionTask


REVISION_RESPONSE_AUDIT_JSON = "09-revision-response-audit.json"
REVISION_RESPONSE_AUDIT_MD = "09-revision-response-audit.md"


MANUAL_RESULT_STATUSES = {"needs_human_evidence", "needs_human_verification"}
APPLIED_RESULT_STATUSES = {"applied_in_draft", "draft_adjusted"}
MANUAL_MARKERS = ["待补证", "人工核对", "人工验证", "人工确认", "待补", "needs_human", "human verification"]
BOUNDARY_MARKERS = ["结果边界", "结论边界", "Claim 边界", "claim boundary", "局限", "边界"]


def write_revision_response_audit_artifacts(
    topic: str,
    revision_plan: PaperRevisionPlan,
    revision_report: PaperRewriteReport,
    revised_paper_md: str,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_revision_response_audit_report(topic, revision_plan, revision_report, revised_paper_md)
    write_json(run_dir / REVISION_RESPONSE_AUDIT_JSON, report)
    write_text(run_dir / REVISION_RESPONSE_AUDIT_MD, render_revision_response_audit_markdown(report))
    return report


def build_revision_response_audit_report(
    topic: str,
    revision_plan: PaperRevisionPlan,
    revision_report: PaperRewriteReport,
    revised_paper_md: str,
) -> dict[str, Any]:
    paper_text = revised_paper_md or ""
    result_by_id = _result_index(revision_report.task_results)
    has_revision_log = _has_revision_log(paper_text)
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []
    manual: list[str] = []
    score = 1.0

    if revision_plan.tasks and not has_revision_log:
        blocking.append("修订稿缺少“修订执行记录”章节，无法逐条核对审稿任务回应。")
        score -= 0.25

    for task in revision_plan.tasks:
        result = result_by_id.get(task.task_id)
        check, penalty = _check_task_response(task, result, paper_text)
        checks.append(check)
        score -= penalty
        if check["status"] == "block":
            blocking.extend(str(item) for item in check["issues"])
        elif check["status"] == "review_required":
            manual.extend(str(item) for item in check["issues"])

    extra_results = sorted(task_id for task_id in result_by_id if task_id not in {task.task_id for task in revision_plan.tasks})
    if extra_results:
        manual.append("修订报告包含修订计划之外的任务结果：" + ", ".join(extra_results[:8]))
        score -= min(0.12, 0.03 * len(extra_results))

    score = round(max(0.0, min(1.0, score)), 3)
    status = "block" if blocking else "review_required" if manual else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "response_score": score,
        "summary": {
            "planned_tasks": len(revision_plan.tasks),
            "reported_results": len(revision_report.task_results),
            "answered_tasks": sum(1 for item in checks if item["result_status"] != "missing"),
            "missing_results": sum(1 for item in checks if item["result_status"] == "missing"),
            "missing_paper_traces": sum(1 for item in checks if item["paper_trace"] == "missing"),
            "manual_results": sum(1 for item in checks if item["result_status"] in MANUAL_RESULT_STATUSES),
            "extra_results": len(extra_results),
            "has_revision_log": has_revision_log,
        },
        "task_checks": checks,
        "extra_results": extra_results,
        "blocking_issues": _dedupe(blocking),
        "manual_tasks": _dedupe(manual),
        "required_actions": _required_actions(status, blocking, manual),
        "source_artifacts": ["08-revision-plan.json", "09-revision-report.json", "09-revised-paper.md"],
    }


def render_revision_response_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# Revision Response Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 回应得分：{float(report.get('response_score') or 0.0):.3f}",
        f"- 计划任务：{summary.get('planned_tasks', 0)}",
        f"- 已报告结果：{summary.get('reported_results', 0)}",
        f"- 缺失结果：{summary.get('missing_results', 0)}",
        f"- 正文缺失任务痕迹：{summary.get('missing_paper_traces', 0)}",
        f"- 人工补证/核对结果：{summary.get('manual_results', 0)}",
        "",
        "## 任务闭环",
        "| 任务 | 严重性 | 章节 | 结果状态 | 正文痕迹 | 审计状态 | 问题 | 动作 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("task_checks", []) if isinstance(report.get("task_checks"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("task_id") or "")),
                    _cell(str(item.get("severity") or "")),
                    _cell(str(item.get("section") or "")),
                    _cell(str(item.get("result_status") or "")),
                    _cell(str(item.get("paper_trace") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell("；".join(str(value) for value in item.get("issues", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("required_action") or "-")),
                ]
            )
            + " |"
        )
    if not report.get("task_checks"):
        lines.append("| - | - | - | - | - | pass | 无修订任务 | - |")
    lines.extend(["", "## 阻断问题"])
    blocking = report.get("blocking_issues") if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    manual = report.get("manual_tasks") if isinstance(report.get("manual_tasks"), list) else []
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    actions = report.get("required_actions") if isinstance(report.get("required_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    return "\n".join(lines)


def _check_task_response(task: RevisionTask, result: PaperRevisionTaskResult | None, paper_text: str) -> tuple[dict[str, Any], float]:
    issues: list[str] = []
    status = "pass"
    penalty = 0.0
    task_id = str(task.task_id or "").strip()
    result_status = str(result.status or "").strip() if result is not None else "missing"
    mentions_task = _mentions_task(paper_text, task_id)
    paper_trace = "present" if mentions_task else "missing"

    if result is None:
        issues.append(f"{task_id} 在 09-revision-report.json 中缺少处理结果。")
        status = _missing_status(task)
        penalty += 0.25 if task.severity == "high" else 0.14
    elif result_status in MANUAL_RESULT_STATUSES:
        if not mentions_task or not _contains_any(paper_text, MANUAL_MARKERS):
            issues.append(f"{task_id} 标为 {result_status}，但修订稿未显式保留任务 ID 和待补证/人工核对标记。")
            status = _missing_status(task)
            penalty += 0.22 if task.severity == "high" else 0.12
        else:
            issues.append(f"{task_id} 仍为 {result_status}，需要人工补证或核对后才能关闭。")
            status = "review_required"
            penalty += 0.08
    elif result_status in APPLIED_RESULT_STATUSES:
        if not mentions_task:
            issues.append(f"{task_id} 标为 {result_status}，但修订稿中未检测到该任务 ID。")
            status = _missing_status(task)
            penalty += 0.20 if task.severity == "high" else 0.10
    else:
        issues.append(f"{task_id} 使用未知修订结果状态：{result_status or '-'}。")
        status = "review_required"
        penalty += 0.08

    if _task_requires_boundary(task) and not _contains_any(paper_text, BOUNDARY_MARKERS):
        issues.append(f"{task_id} 涉及 claim/结果边界，但修订稿未检测到结果边界、结论边界或局限性章节。")
        status = "block" if task.severity == "high" else "review_required" if status == "pass" else status
        penalty += 0.12 if task.severity == "high" else 0.06

    return (
        {
            "task_id": task_id,
            "severity": task.severity,
            "section": task.section,
            "issue": task.issue,
            "planned_action": task.action,
            "result_status": result_status,
            "paper_trace": paper_trace,
            "status": status,
            "issues": _dedupe(issues),
            "required_action": _required_action_for_task(task, result_status, status),
            "evidence_refs": list(result.evidence_refs if result is not None else task.evidence_refs),
        },
        penalty,
    )


def _result_index(results: list[PaperRevisionTaskResult]) -> dict[str, PaperRevisionTaskResult]:
    output: dict[str, PaperRevisionTaskResult] = {}
    for result in results:
        task_id = str(result.task_id or "").strip()
        if task_id and task_id not in output:
            output[task_id] = result
    return output


def _missing_status(task: RevisionTask) -> str:
    return "block" if task.severity == "high" else "review_required"


def _has_revision_log(text: str) -> bool:
    for line in text.splitlines():
        heading = line.strip()
        if not heading.startswith("#"):
            continue
        title = heading.lstrip("#").strip().lower()
        title = re.sub(r"^(?:\d+|[ivxlcdm]+)[.)、\s-]+", "", title, flags=re.IGNORECASE).strip()
        if title.startswith("修订执行记录") or title.startswith("revision response") or title.startswith("revision log"):
            return True
    return False


def _mentions_task(text: str, task_id: str) -> bool:
    return bool(task_id) and task_id.lower() in text.lower()


def _task_requires_boundary(task: RevisionTask) -> bool:
    text = " ".join([task.section, task.issue, task.action]).lower()
    markers = ["claim", "主张", "结果边界", "结论边界", "unsupported", "weak", "smoke", "repair_before_writing", "假设", "负结果"]
    return any(marker.lower() in text for marker in markers)


def _required_action_for_task(task: RevisionTask, result_status: str, status: str) -> str:
    if status == "pass":
        return "无需处理。"
    if result_status == "missing":
        return f"补写 {task.task_id} 的 task_result，并在修订稿“修订执行记录”中逐条回应。"
    if result_status in MANUAL_RESULT_STATUSES:
        return f"补齐 {task.task_id} 所需文献、真实实验或人工核对记录；无法补证时删除或降级相关 claim。"
    return f"在修订稿中显式标注 {task.task_id} 的处理结果，并重新运行修订响应审计。"


def _required_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "pass":
        return ["当前修订任务闭环可接受；继续人工核对文献、图表和投稿格式。"]
    actions = []
    if blocking:
        actions.append("先处理所有 block 项；高优先级审稿任务未闭环前不要进入最终投稿包。")
    if manual:
        actions.append("逐条补齐 needs_human_evidence / needs_human_verification 任务，或在正文中删除、降级无法补证的 claim。")
    actions.append("修复后从 paper_rewrite checkpoint 重新生成 09-revised-paper、09-revision-report 和后续审计。")
    return _dedupe(actions)


def _contains_any(text: str, markers: list[str]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
