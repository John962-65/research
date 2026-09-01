from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


HUMAN_GATE_AUDIT_JSON = "13-human-gate-audit.json"
HUMAN_GATE_AUDIT_MD = "13-human-gate-audit.md"

REVIEW_BLOCKS = {"idea_generation", "experiment_planning", "experiment_execution"}


def write_human_gate_audit_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_human_gate_audit_report(topic, run_dir)
    write_json(run_dir / HUMAN_GATE_AUDIT_JSON, report)
    write_text(run_dir / HUMAN_GATE_AUDIT_MD, render_human_gate_audit_markdown(report))
    return report


def build_human_gate_audit_report(topic: str, run_dir: Path) -> dict[str, Any]:
    state = _read_json(run_dir / "state.json")
    approval = _read_json(run_dir / "approval.json")
    execution_approval = _read_json(run_dir / "03-execution-approval.json")
    runbook = _read_json(run_dir / "04-experiment-runbook.json")
    repair_resume = _repair_resume_evidence(_read_json(run_dir / "12-repair-resume-plan.json"))
    stage = str(state.get("stage") or "")
    downstream = _downstream_evidence(run_dir, stage)
    execution = _execution_evidence(run_dir, runbook)
    checks = [
        _review_gate_check(approval, downstream),
        _execution_gate_check(execution_approval, execution),
        _repair_resume_reapproval_check(approval, execution_approval, repair_resume),
    ]
    blocking = [action for check in checks if check["status"] == "block" for action in check["required_actions"]]
    manual = [action for check in checks if check["status"] == "review_required" for action in check["required_actions"]]
    status = "block" if blocking else "review_required" if manual else "pass"
    return {
        "schema_version": 2,
        "topic": topic,
        "status": status,
        "summary": {
            "review_approved": approval.get("approved") is True,
            "review_blocks": len(_list(approval.get("blocks"))),
            "downstream_artifacts": len(downstream["artifacts"]),
            "downstream_stage": downstream["stage"],
            "execution_approved": execution_approval.get("approved") is True,
            "execution_mode": execution["mode"],
            "execution_artifacts": len(execution["artifacts"]),
            "repair_resume_status": repair_resume["status"],
            "repair_resume_applied": repair_resume["applied"],
            "repair_resume_applied_at": repair_resume["applied_at"],
            "review_reapproval_required": repair_resume["review_reapproval_required"],
            "execution_reapproval_required": repair_resume["execution_reapproval_required"],
        },
        "checks": checks,
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "recommended_actions": _recommended_actions(status),
    }


def render_human_gate_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# Human Gate Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Review approved：{'yes' if summary.get('review_approved') else 'no'}",
        f"- Review blocks：{summary.get('review_blocks', 0)}",
        f"- Downstream：stage={summary.get('downstream_stage') or '-'}, artifacts={summary.get('downstream_artifacts', 0)}",
        f"- Execution approved：{'yes' if summary.get('execution_approved') else 'no'}",
        f"- Execution：mode={summary.get('execution_mode') or '-'}, artifacts={summary.get('execution_artifacts', 0)}",
        f"- Repair resume：status={summary.get('repair_resume_status') or '-'}, applied={'yes' if summary.get('repair_resume_applied') else 'no'}",
        f"- Repair reapproval：review={'yes' if summary.get('review_reapproval_required') else 'no'}, execution={'yes' if summary.get('execution_reapproval_required') else 'no'}",
        "",
        "## Checks",
        "| Gate | Status | Evidence | Action |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if not isinstance(check, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(check.get("gate") or "")),
                    _cell(str(check.get("status") or "")),
                    _cell("；".join(str(item) for item in _list(check.get("evidence"))) or "-"),
                    _cell("；".join(str(item) for item in _list(check.get("required_actions"))) or "-"),
                ]
            )
            + " |"
        )
    for key, title, prefix in [
        ("blocking_issues", "阻断问题", "- "),
        ("manual_tasks", "人工待办", "- [ ] "),
        ("recommended_actions", "推荐动作", "- [ ] "),
    ]:
        values = _list(report.get(key))
        lines.extend(["", f"## {title}"])
        lines.extend(prefix + str(item) for item in values) if values else lines.append("- 无")
    return "\n".join(lines)


def _review_gate_check(approval: dict[str, Any], downstream: dict[str, Any]) -> dict[str, Any]:
    approved = approval.get("approved") is True
    blocks = {str(item) for item in _list(approval.get("blocks"))}
    has_downstream = bool(downstream["artifacts"]) or _stage_after_review(str(downstream.get("stage") or ""))
    actions: list[str] = []
    status = "pass"
    if has_downstream and not approved:
        status = "block"
        actions.append("当前 run 已进入 idea/实验/写作下游，但 approval.json 未批准；必须回退到 review gate 或重新人工批准后重跑。")
    if has_downstream and not REVIEW_BLOCKS.issubset(blocks):
        status = "block"
        actions.append("approval.json 未记录 idea_generation、experiment_planning、experiment_execution 三类阻断范围。")
    if not has_downstream and approval and not approved:
        status = "review_required"
        actions.append("当前 run 正在等待 review gate；批准前不得进入 idea/实验。")
    return {
        "gate": "review",
        "status": status,
        "evidence": [
            f"approved={approved}",
            f"blocks={len(blocks)}",
            f"downstream_artifacts={len(downstream['artifacts'])}",
            f"downstream_stage={downstream.get('stage') or '-'}",
        ],
        "required_actions": actions,
    }


def _execution_gate_check(execution_approval: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    approved = execution_approval.get("approved") is True
    mode = str(execution.get("mode") or "")
    artifacts = _list(execution.get("artifacts"))
    requires_approval = mode in {"local", "benchmark"} or bool(artifacts)
    actions: list[str] = []
    status = "pass"
    if requires_approval and not approved:
        status = "block"
        actions.append("当前 run 存在 local/benchmark 执行或结果产物，但 03-execution-approval.json 未批准；必须回退到 execution gate 或重新批准后重跑。")
    if execution_approval and not approved and not artifacts:
        status = "review_required"
        actions.append("当前 run 正在等待执行确认；批准前不得运行 local/benchmark 命令。")
    return {
        "gate": "execution",
        "status": status,
        "evidence": [f"approved={approved}", f"mode={mode or '-'}", f"execution_artifacts={len(artifacts)}"],
        "required_actions": actions,
    }


def _repair_resume_reapproval_check(approval: dict[str, Any], execution_approval: dict[str, Any], repair_resume: dict[str, Any]) -> dict[str, Any]:
    applied = repair_resume.get("applied") is True
    applied_at = str(repair_resume.get("applied_at") or "")
    review_required = repair_resume.get("review_reapproval_required") is True
    execution_required = repair_resume.get("execution_reapproval_required") is True
    review_approved = approval.get("approved") is True
    execution_approved = execution_approval.get("approved") is True
    review_fresh = review_approved and _approval_after(approval, applied_at, {"approved"})
    execution_fresh = execution_approved and _approval_after(execution_approval, applied_at, {"execution_approved"})
    actions: list[str] = []
    status = "pass"
    if applied and review_required:
        if review_approved and not review_fresh:
            status = "block"
            actions.append(
                "12-repair-resume-plan.json 已应用且要求 review 重新批准，但 approval.json 未证明批准发生在修复之后；必须重新人工批准后才能进入 idea/实验。"
            )
        elif not review_approved:
            status = "review_required"
            actions.append("12-repair-resume-plan.json 已应用且要求 review 重新批准；批准前不得进入 idea/实验。")
    if applied and execution_required:
        if execution_approved and not execution_fresh:
            status = "block"
            actions.append(
                "12-repair-resume-plan.json 已应用且要求 execution 重新批准，但 03-execution-approval.json 未证明批准发生在修复之后；必须重新确认后才能运行 local/benchmark。"
            )
        elif not execution_approved and status != "block":
            status = "review_required"
            actions.append("12-repair-resume-plan.json 已应用且要求 execution 重新批准；批准前不得运行 local/benchmark 命令。")
    return {
        "gate": "repair_resume_reapproval",
        "status": status,
        "evidence": [
            f"repair_status={repair_resume.get('status') or '-'}",
            f"applied={applied}",
            f"applied_at={applied_at or '-'}",
            f"review_reapproval_required={review_required}",
            f"execution_reapproval_required={execution_required}",
            f"review_reapproved_after_repair={review_fresh}",
            f"execution_reapproved_after_repair={execution_fresh}",
        ],
        "required_actions": actions,
    }


def _repair_resume_evidence(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(plan.get("status") or ""),
        "applied": plan.get("applied") is True,
        "applied_at": str(plan.get("applied_at") or ""),
        "review_reapproval_required": plan.get("review_reapproval_required") is True,
        "execution_reapproval_required": plan.get("execution_reapproval_required") is True,
    }


def _approval_after(record: dict[str, Any], applied_at: str, actions: set[str]) -> bool:
    repair_time = _parse_time(applied_at)
    if repair_time is None:
        return False
    timestamps = [record.get("approved_at")]
    history = record.get("history") if isinstance(record.get("history"), list) else []
    for item in history:
        if not isinstance(item, dict):
            continue
        if str(item.get("action") or "") in actions:
            timestamps.append(item.get("at"))
    for value in timestamps:
        timestamp = _parse_time(value)
        if timestamp is not None and timestamp >= repair_time:
            return True
    return False


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _downstream_evidence(run_dir: Path, stage: str) -> dict[str, Any]:
    artifacts = [
        name
        for name in [
            "02-ideas.json",
            "02-exploration-map.json",
            "02-experiment-manager.json",
            "03-experiment-plan.json",
            "04-results.json",
            "04-results.csv",
            "06-paper.md",
            "09-revised-paper.md",
        ]
        if (run_dir / name).exists()
    ]
    return {"stage": stage, "artifacts": artifacts}


def _execution_evidence(run_dir: Path, runbook: dict[str, Any]) -> dict[str, Any]:
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    mode = str(execution.get("mode") or runbook.get("execution_mode") or "")
    artifacts = [
        name
        for name in [
            "04-results.json",
            "04-results.csv",
            "04-statistics.json",
        ]
        if (run_dir / name).exists()
    ]
    return {"mode": mode, "artifacts": artifacts}


def _stage_after_review(stage: str) -> bool:
    order = [
        "ideation_completed",
        "exploration_map_completed",
        "experiment_manager_completed",
        "experiment_plan_completed",
        "awaiting_execution_approval",
        "experiments_completed",
        "analysis_completed",
        "paper_draft_completed",
        "completed",
    ]
    return stage in order


def _recommended_actions(status: str) -> list[str]:
    if status == "block":
        return [
            "不要把该 run 当作合规结果；从 review/execution gate 前的 checkpoint 重新批准并重跑受影响阶段。",
            "重新生成 12-repair-queue、12-repair-resume-plan、13-agent-stage-contract 和平台审计。",
        ]
    if status == "review_required":
        return ["保持当前等待状态；人工批准前不要进入 idea、实验计划或 local/benchmark 执行。"]
    return ["Human gate 轨迹闭环；继续保留 approval、execution approval 和本审计产物。"]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
