from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


RUN_RECOVERY_PLAN_JSON = "run-recovery-plan.json"
RUN_RECOVERY_PLAN_MD = "run-recovery-plan.md"


def write_run_recovery_plan_artifacts(run_dir: Path, status: str = "") -> dict[str, Any]:
    report = build_run_recovery_plan(run_dir, status=status)
    write_json(run_dir / RUN_RECOVERY_PLAN_JSON, report)
    write_text(run_dir / RUN_RECOVERY_PLAN_MD, render_run_recovery_plan_markdown(report))
    return report


def build_run_recovery_plan(run_dir: Path, status: str = "") -> dict[str, Any]:
    state = _read_json(run_dir / "state.json")
    diagnostic = _read_json(run_dir / "run-diagnostics.json")
    approval = _read_json(run_dir / "approval.json")
    execution_approval = _read_json(run_dir / "03-execution-approval.json")
    cancel = _read_json(run_dir / "cancel.json")
    stage = str(state.get("stage") or approval.get("stage") or execution_approval.get("stage") or status or "unknown")
    topic = str(state.get("topic") or approval.get("topic") or run_dir.name)
    category = _category(status, stage, diagnostic, approval, execution_approval, cancel)
    actions, commands, stop_conditions = _recovery_steps(run_dir, category, stage, diagnostic, approval, execution_approval, cancel)
    blockers = _blockers(category, diagnostic, approval, cancel)
    return {
        "schema_version": 1,
        "topic": topic,
        "run_dir": str(run_dir),
        "generated_at": _utc_now(),
        "status": status or category,
        "stage": stage,
        "category": category,
        "diagnostic_category": str(diagnostic.get("category") or ""),
        "diagnostic_summary": str(diagnostic.get("summary") or ""),
        "approval_state": _approval_state(approval),
        "execution_approval_state": _approval_state(execution_approval),
        "cancel_state": _cancel_state(cancel),
        "checkpoint_artifacts": _checkpoint_artifacts(run_dir),
        "blocking_issues": blockers,
        "recommended_actions": actions,
        "commands": commands,
        "stop_conditions": stop_conditions,
    }


def render_run_recovery_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Run 恢复计划：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 阶段：{report.get('stage') or '-'}",
        f"- 类别：{report.get('category') or '-'}",
        f"- 诊断：{report.get('diagnostic_category') or '-'}",
        f"- 目录：{report.get('run_dir') or '-'}",
        f"- 生成时间：{report.get('generated_at') or '-'}",
        "",
    ]
    for key, title in [
        ("blocking_issues", "当前阻断"),
        ("recommended_actions", "推荐动作"),
        ("commands", "可执行命令"),
        ("stop_conditions", "停止条件"),
        ("checkpoint_artifacts", "可复用 checkpoint"),
    ]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.extend([f"## {title}"])
        if values:
            if key == "commands":
                lines.extend(f"- `{item}`" for item in values)
            elif key == "stop_conditions":
                lines.extend(f"- [ ] {item}" for item in values)
            else:
                lines.extend(f"- {item}" for item in values)
        else:
            lines.append("- 无")
        lines.append("")
    return "\n".join(lines)


def _category(status: str, stage: str, diagnostic: dict[str, Any], approval: dict[str, Any], execution_approval: dict[str, Any], cancel: dict[str, Any]) -> str:
    if cancel.get("cancelled") is True or stage == "cancelled" or status == "cancelled":
        return "cancelled"
    if cancel.get("requested") is True or status == "cancelling":
        return "cancelling"
    if diagnostic:
        return "failed"
    if approval.get("revision_requested") is True or stage == "review_revision_requested":
        return "review_revision_requested"
    if approval and approval.get("approved") is not True:
        return "awaiting_review_approval"
    if execution_approval and execution_approval.get("approved") is not True:
        return "awaiting_execution_approval"
    if stage == "awaiting_execution_approval":
        return "awaiting_execution_approval"
    if stage == "completed" or status == "completed":
        return "completed"
    return "checkpoint_resume"


def _recovery_steps(
    run_dir: Path,
    category: str,
    stage: str,
    diagnostic: dict[str, Any],
    approval: dict[str, Any],
    execution_approval: dict[str, Any],
    cancel: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    run_ref = str(run_dir)
    if category == "failed":
        actions = _diagnostic_actions(diagnostic)
        commands = [
            f"PYTHONPATH=src python3 -m research_agent preflight --topic \"{_topic_arg(run_dir)}\" --no-llm-ping",
            f"PYTHONPATH=src python3 -m research_agent resume {run_ref} --llm-model \"$OPENAI_MODEL\"",
        ]
        stops = ["run-diagnostics.md 中对应配置问题已修复。", "resume 后 state.json 不再停留在 failed。"]
        return actions, commands, stops
    if category == "review_revision_requested":
        notes = str(approval.get("notes") or "").strip()
        action = "根据退回意见修复文献、人工 seed 或审核约束后再批准。"
        if notes:
            action += f" 退回意见：{notes}"
        return (
            [action, "重新查看 01-review-gate.md，确认 idea/实验仍被人工 gate 阻断。"],
            [
                f"PYTHONPATH=src python3 -m research_agent approve {run_ref} --reviewer cli --notes \"已处理退回意见\"",
                f"PYTHONPATH=src python3 -m research_agent resume {run_ref} --llm-model \"$OPENAI_MODEL\"",
            ],
            ["approval.json 中 revision_requested=false 且 approved=true。", "02-ideas.md 或后续产物开始生成。"],
        )
    if category == "awaiting_review_approval":
        return (
            ["人工审核 01-review-gate.md、01-context.md、01-literature-curated.md 后再批准。", "不要在未批准前进入 idea 或实验。"],
            [
                f"PYTHONPATH=src python3 -m research_agent approve {run_ref} --reviewer cli --notes \"文献审核通过\"",
                f"PYTHONPATH=src python3 -m research_agent resume {run_ref} --llm-model \"$OPENAI_MODEL\"",
            ],
            ["approval.json 中 approved=true。", "state.json 进入 review_approved 或后续阶段。"],
        )
    if category == "awaiting_execution_approval":
        mode = str(execution_approval.get("execution_mode") or "local/benchmark")
        return (
            [f"人工审核 03-execution-approval.md、03-execution-safety-audit.md 和 03-experiment-plan.md 后再批准 {mode} 执行。", "未批准前不要运行本地或 benchmark 命令。"],
            [
                f"PYTHONPATH=src python3 -m research_agent approve-execution {run_ref} --reviewer cli --notes \"已检查实验命令和安全审计，允许执行\"",
                f"PYTHONPATH=src python3 -m research_agent resume {run_ref} --llm-model \"$OPENAI_MODEL\"",
            ],
            ["03-execution-approval.json 中 approved=true。", "04-results.json 或 04-experiment-runbook.md 开始生成。"],
        )
    if category == "cancelled":
        reason = str(cancel.get("reason") or "").strip()
        action = "该 run 已取消，当前 Web/CLI 不支持直接恢复 cancelled run。"
        if reason:
            action += f" 取消原因：{reason}"
        return (
            [action, "复用已有文献/计划产物作为人工参考，启动一个新 run。"],
            ["PYTHONPATH=src python3 -m research_agent run --topic \"<same topic>\" --llm-model \"$OPENAI_MODEL\""],
            ["新 run 生成新的 state.json 和 approval gate。"],
        )
    if category == "cancelling":
        return (
            ["等待当前步骤观察到 cancel.json 后自然停止。", "若长时间不停止，检查后台进程和 run-diagnostics.md。"],
            [],
            ["state.json 进入 cancelled，或 Web run 状态不再是 cancelling。"],
        )
    if category == "completed":
        return (
            ["该 run 已完成，不需要恢复；查看 12-next-iteration-plan.md 和 13-research-scorecard.md 决定下一轮。"],
            ["PYTHONPATH=src python3 -m research_agent summary --runs-dir runs --limit 20"],
            ["分数卡和下一轮计划已人工查看。"],
        )
    return (
        [f"当前停在 checkpoint：{stage}。确认配置后从 checkpoint resume。"],
        [f"PYTHONPATH=src python3 -m research_agent resume {run_ref} --llm-model \"$OPENAI_MODEL\""],
        ["state.json 进入后续阶段，或 run-diagnostics.md 给出新的失败原因。"],
    )


def _diagnostic_actions(diagnostic: dict[str, Any]) -> list[str]:
    actions = diagnostic.get("recommended_actions") if isinstance(diagnostic.get("recommended_actions"), list) else []
    if actions:
        return [str(item) for item in actions[:6]]
    return ["查看 run-diagnostics.md，修复 traceback 指向的配置或产物问题。"]


def _blockers(category: str, diagnostic: dict[str, Any], approval: dict[str, Any], cancel: dict[str, Any]) -> list[str]:
    if category == "failed":
        summary = str(diagnostic.get("summary") or "运行失败。")
        return [summary]
    if category == "review_revision_requested":
        return ["人工退回仍未处理。"]
    if category == "awaiting_review_approval":
        return ["等待人工批准文献审核 gate。"]
    if category == "awaiting_execution_approval":
        return ["等待人工批准 local/benchmark 实验执行。"]
    if category == "cancelled":
        return ["run 已取消，不能直接 resume。"]
    if category == "cancelling":
        return ["取消请求已发出，等待流水线停止。"]
    return []


def _checkpoint_artifacts(run_dir: Path) -> list[str]:
    candidates = [
        "00-research-plan.json",
        "01-literature-curated.json",
        "01-context.json",
        "approval.json",
        "02-ideas.json",
        "02-experiment-manager.json",
        "03-experiment-plan.json",
        "03-execution-approval.json",
        "04-results.json",
        "04-experiment-decision.json",
        "06-paper.md",
        "09-revision-response-audit.json",
        "10-final-readiness.json",
    ]
    return [name for name in candidates if (run_dir / name).exists()]


def _approval_state(approval: dict[str, Any]) -> str:
    if not approval:
        return "missing"
    if approval.get("approved") is True:
        return "approved"
    if approval.get("revision_requested") is True:
        return "revision_requested"
    return "pending"


def _cancel_state(cancel: dict[str, Any]) -> str:
    if not cancel:
        return "none"
    if cancel.get("cancelled") is True:
        return "cancelled"
    if cancel.get("requested") is True:
        return "requested"
    return "present"


def _topic_arg(run_dir: Path) -> str:
    state = _read_json(run_dir / "state.json")
    return str(state.get("topic") or run_dir.name).replace('"', "'")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
