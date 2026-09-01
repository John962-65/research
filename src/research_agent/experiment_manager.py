from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExplorationMap, ResearchIdea


EXPERIMENT_MANAGER_JSON = "02-experiment-manager.json"
EXPERIMENT_MANAGER_MD = "02-experiment-manager.md"


def write_experiment_manager_artifacts(
    topic: str,
    ideas: list[ResearchIdea],
    exploration_map: ExplorationMap,
    run_dir: Path,
    idea_audit: dict[str, Any] | None = None,
    novelty_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_experiment_manager_report(topic, ideas, exploration_map, idea_audit=idea_audit, novelty_audit=novelty_audit)
    write_json(run_dir / EXPERIMENT_MANAGER_JSON, report)
    write_text(run_dir / EXPERIMENT_MANAGER_MD, render_experiment_manager_markdown(report))
    return report


def build_experiment_manager_report(
    topic: str,
    ideas: list[ResearchIdea],
    exploration_map: ExplorationMap,
    idea_audit: dict[str, Any] | None = None,
    novelty_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    branches = [_branch_row(branch, ideas, idea_audit, novelty_audit) for branch in exploration_map.branches]
    selected = next((branch for branch in branches if branch["branch_id"] == exploration_map.selected_branch_id), {})
    decision, execution_policy, warnings, required_actions = _decision(selected, exploration_map.warnings)
    planning_constraints = _planning_constraints(selected, execution_policy, warnings)
    next_expansion = [
        {
            "branch_id": branch["branch_id"],
            "title": branch["title"],
            "reason": _expansion_reason(branch),
            "score": branch["score"],
        }
        for branch in sorted(branches, key=lambda item: item["score"], reverse=True)
        if branch.get("branch_id") != selected.get("branch_id") and branch.get("manager_status") in {"ready_for_next_iteration", "needs_human_repair"}
    ][:3]
    manager_queue = _manager_queue(branches, str(selected.get("branch_id") or ""))
    return {
        "schema_version": 1,
        "topic": topic,
        "status": "block" if decision == "needs_human_reselection" else "review_required" if warnings or required_actions else "pass",
        "selected_branch_id": selected.get("branch_id") or "",
        "selected_idea_title": selected.get("title") or "",
        "manager_decision": decision,
        "execution_policy": execution_policy,
        "branch_budget": {
            "total_branches": len(branches),
            "expand_now": 1 if selected else 0,
            "next_iteration_candidates": len(next_expansion),
        },
        "queue_summary": _queue_summary(manager_queue),
        "manager_queue": manager_queue,
        "planning_constraints": planning_constraints,
        "next_expansion_candidates": next_expansion,
        "branches": branches,
        "warnings": warnings,
        "required_actions": required_actions,
        "rationale": _rationale(decision, execution_policy, selected),
    }


def render_experiment_manager_markdown(report: dict[str, Any]) -> str:
    budget = report.get("branch_budget") if isinstance(report.get("branch_budget"), dict) else {}
    lines = [
        f"# Experiment Manager：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 决策：{report.get('manager_decision') or '-'}",
        f"- 执行策略：{report.get('execution_policy') or '-'}",
        f"- 选中分支：{report.get('selected_branch_id') or '-'} / {report.get('selected_idea_title') or '-'}",
        f"- 分支预算：本轮 {budget.get('expand_now', 0)}/{budget.get('total_branches', 0)}，下一轮候选 {budget.get('next_iteration_candidates', 0)}",
        f"- 理由：{report.get('rationale') or '-'}",
        "",
    ]
    for key, title in [("warnings", "警告"), ("required_actions", "必需动作"), ("planning_constraints", "实验计划约束")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(["## 分支管理表", "| 分支 | 状态 | Manager | 分数 | 风险 | 证据 | Idea Audit | Novelty | 动作 |", "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |"])
    branches = report.get("branches") if isinstance(report.get("branches"), list) else []
    if not branches:
        lines.append("| - | - | - | 0 | 0 | 0 | - | - | - |")
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(f"{branch.get('branch_id') or ''} {branch.get('title') or ''}"),
                    _cell(str(branch.get("exploration_status") or "")),
                    _cell(str(branch.get("manager_status") or "")),
                    f"{float(branch.get('score') or 0.0):.2f}",
                    str(branch.get("risk") or 0),
                    str(branch.get("evidence_count") or 0),
                    _cell(str(branch.get("idea_audit_decision") or "-")),
                    _cell(str(branch.get("novelty_decision") or "-")),
                    _cell(str(branch.get("action") or "")),
                ]
            )
            + " |"
        )
    queue = report.get("manager_queue") if isinstance(report.get("manager_queue"), list) else []
    queue_summary = report.get("queue_summary") if isinstance(report.get("queue_summary"), dict) else {}
    lines.extend(
        [
            "",
            "## Manager Queue",
            f"- 活跃：{queue_summary.get('active', 0)}；阻断：{queue_summary.get('blocked', 0)}；需人工：{queue_summary.get('human_review', 0)}；候选：{queue_summary.get('ready_backlog', 0)}；延后：{queue_summary.get('deferred', 0)}",
            "",
            "| 优先级 | 分支 | 队列状态 | owner | 阻断当前实验 | 需人工 | 下一步 |",
            "| ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not queue:
        lines.append("| 0 | - | - | - | 否 | 否 | - |")
    for item in queue:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("priority") or 0),
                    _cell(f"{item.get('branch_id') or ''} {item.get('title') or ''}"),
                    _cell(str(item.get("queue_state") or "")),
                    _cell(str(item.get("owner") or "")),
                    "是" if item.get("blocks_current_experiment") else "否",
                    "是" if item.get("requires_human") else "否",
                    _cell(str(item.get("next_action") or "")),
                ]
            )
            + " |"
        )
    candidates = report.get("next_expansion_candidates") if isinstance(report.get("next_expansion_candidates"), list) else []
    if candidates:
        lines.extend(["", "## 下一轮候选"])
        lines.extend(f"- {item.get('branch_id')}: {item.get('title')}（{item.get('reason')}）" for item in candidates if isinstance(item, dict))
    lines.extend(
        [
            "",
            "## 使用方式",
            "- `planning_constraints` 会注入 `03-experiment-plan`，用于约束实验范围、baseline 和 claim 强度。",
            "- 如果状态为 `block`，应人工改选或修复 idea 后再从 checkpoint resume。",
        ]
    )
    return "\n".join(lines)


def experiment_manager_constraints(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    constraints = report.get("planning_constraints")
    if not isinstance(constraints, list) or not constraints:
        return ""
    return "Experiment manager constraints:\n" + "\n".join(f"- {item}" for item in constraints if str(item).strip())


def _branch_row(branch, ideas: list[ResearchIdea], idea_audit: dict[str, Any] | None, novelty_audit: dict[str, Any] | None) -> dict[str, Any]:
    idea = next((item for item in ideas if item.title == branch.title), None)
    audit_item = _item_for_title(idea_audit, branch.title)
    novelty_item = _item_for_title(novelty_audit, branch.title)
    audit_decision = str(audit_item.get("decision") or "")
    novelty_decision = str(novelty_item.get("decision") or "")
    manager_status = _manager_status(branch.status, audit_decision, novelty_decision, branch.evidence_count, branch.risk)
    return {
        "branch_id": branch.branch_id,
        "title": branch.title,
        "exploration_status": branch.status,
        "manager_status": manager_status,
        "score": branch.score,
        "risk": branch.risk,
        "evidence_count": branch.evidence_count,
        "baseline": branch.baseline or (idea.baseline if idea else ""),
        "evidence_keys": branch.evidence_keys,
        "idea_audit_decision": audit_decision,
        "novelty_decision": novelty_decision,
        "issues": _as_strings(audit_item.get("issues")) + ([f"novelty={novelty_decision}"] if novelty_decision == "likely_duplicate" else []),
        "action": _branch_action(manager_status, branch.status),
    }


def _decision(selected: dict[str, Any], exploration_warnings: list[str]) -> tuple[str, str, list[str], list[str]]:
    warnings = list(exploration_warnings)
    required_actions: list[str] = []
    if not selected:
        return "needs_human_reselection", "blocked", ["没有选中分支。"], ["补充 idea 后重新生成探索图。"]
    if selected.get("idea_audit_decision") == "block":
        required_actions.append("选中分支的 idea audit 为 block；修正不可核对 citation/chunk 或人工改选。")
    if selected.get("novelty_decision") == "likely_duplicate":
        warnings.append("选中分支 novelty audit 为 likely_duplicate；实验计划只能作为复核/消融，不得主张新颖贡献。")
    if int(selected.get("evidence_count") or 0) == 0:
        warnings.append("选中分支缺少文献证据；实验前需要补证或只做方法可行性 smoke。")
    if int(selected.get("risk") or 0) >= 4:
        warnings.append("选中分支风险较高；先做低成本 smoke-first 实验。")
    if required_actions:
        return "needs_human_reselection", "blocked", _unique(warnings), required_actions
    if warnings:
        return "proceed_with_cautions", "smoke_first", _unique(warnings), required_actions
    return "proceed_to_experiment_plan", "standard", warnings, required_actions


def _planning_constraints(selected: dict[str, Any], execution_policy: str, warnings: list[str]) -> list[str]:
    constraints: list[str] = []
    baseline = str(selected.get("baseline") or "").strip()
    if baseline:
        constraints.append(f"实验必须包含直接 baseline：{baseline}。")
    if execution_policy == "smoke_first":
        constraints.append("先规划低成本 smoke-first 实验；不要把 smoke 结果写成最终科学结论。")
    if selected.get("novelty_decision") == "likely_duplicate":
        constraints.append("该分支疑似重复；实验目标应验证差异点或失败边界，不得声称完整新颖性。")
    if int(selected.get("evidence_count") or 0) == 0:
        constraints.append("文献证据不足；实验计划必须列出补证步骤或把 claim 限制为工程可行性。")
    constraints.extend(warnings[:3])
    return _unique(constraints)


def _manager_status(branch_status: str, audit_decision: str, novelty_decision: str, evidence_count: int, risk: int) -> str:
    if audit_decision == "block":
        return "needs_human_repair"
    if branch_status == "selected":
        if novelty_decision == "likely_duplicate" or evidence_count == 0 or risk >= 4 or audit_decision == "review":
            return "selected_with_cautions"
        return "selected_ready"
    if novelty_decision == "likely_duplicate":
        return "defer_duplicate_check"
    if audit_decision == "review" or evidence_count == 0:
        return "needs_human_repair"
    return "ready_for_next_iteration"


def _branch_action(manager_status: str, branch_status: str) -> str:
    if manager_status == "selected_ready":
        return "按标准实验计划继续。"
    if manager_status == "selected_with_cautions":
        return "按 smoke-first/保守 claim 约束继续。"
    if manager_status == "needs_human_repair":
        return "补证、修正 citation/chunk 或人工改选后再展开。"
    if manager_status == "defer_duplicate_check":
        return "先做 novelty 人工复核。"
    if branch_status == "pruned":
        return "保留为下一轮扩展候选。"
    return "等待人工确认。"


def _manager_queue(branches: list[dict[str, Any]], selected_branch_id: str) -> list[dict[str, Any]]:
    items = [_queue_item(branch, selected_branch_id) for branch in branches]
    return sorted(items, key=lambda item: (int(item.get("priority") or 0), str(item.get("branch_id") or "")))


def _queue_item(branch: dict[str, Any], selected_branch_id: str) -> dict[str, Any]:
    branch_id = str(branch.get("branch_id") or "")
    manager_status = str(branch.get("manager_status") or "")
    selected = bool(branch_id and branch_id == selected_branch_id)
    queue_state = _queue_state(manager_status, selected)
    requires_human = queue_state in {"active_smoke_first", "blocked_human_repair", "needs_human_repair", "deferred_novelty_check"}
    blocks_current = selected and queue_state == "blocked_human_repair"
    return {
        "branch_id": branch_id,
        "title": str(branch.get("title") or ""),
        "selected": selected,
        "queue_state": queue_state,
        "manager_status": manager_status,
        "priority": _queue_priority(queue_state, selected),
        "owner": _queue_owner(queue_state),
        "requires_human": requires_human,
        "blocks_current_experiment": blocks_current,
        "resume_from": "ideation" if queue_state in {"blocked_human_repair", "needs_human_repair"} else "experiment_plan" if selected else "next_iteration",
        "next_action": str(branch.get("action") or ""),
        "evidence_count": int(branch.get("evidence_count") or 0),
        "risk": int(branch.get("risk") or 0),
        "issues": _as_strings(branch.get("issues")),
        "source_artifacts": [EXPERIMENT_MANAGER_JSON, "02-exploration-map.json", "02-idea-audit.json", "02-novelty-audit.json"],
    }


def _queue_state(manager_status: str, selected: bool) -> str:
    if selected and manager_status == "selected_ready":
        return "active_standard"
    if selected and manager_status == "selected_with_cautions":
        return "active_smoke_first"
    if manager_status == "needs_human_repair":
        return "blocked_human_repair" if selected else "needs_human_repair"
    if manager_status == "ready_for_next_iteration":
        return "ready_backlog"
    if manager_status == "defer_duplicate_check":
        return "deferred_novelty_check"
    return "deferred"


def _queue_priority(queue_state: str, selected: bool) -> int:
    if queue_state == "blocked_human_repair":
        return 5
    if queue_state == "active_standard":
        return 10
    if queue_state == "active_smoke_first":
        return 20
    if selected:
        return 30
    if queue_state == "needs_human_repair":
        return 60
    if queue_state == "ready_backlog":
        return 70
    if queue_state == "deferred_novelty_check":
        return 80
    return 90


def _queue_owner(queue_state: str) -> str:
    if queue_state in {"blocked_human_repair", "needs_human_repair", "active_smoke_first"}:
        return "human+agent"
    if queue_state == "deferred_novelty_check":
        return "human"
    return "agent"


def _queue_summary(queue: list[dict[str, Any]]) -> dict[str, int]:
    states = [str(item.get("queue_state") or "") for item in queue if isinstance(item, dict)]
    return {
        "total": len(queue),
        "active": sum(1 for state in states if state in {"active_standard", "active_smoke_first"}),
        "blocked": sum(1 for state in states if state == "blocked_human_repair"),
        "human_review": sum(1 for item in queue if isinstance(item, dict) and item.get("requires_human")),
        "ready_backlog": sum(1 for state in states if state == "ready_backlog"),
        "deferred": sum(1 for state in states if state.startswith("deferred")),
        "blocks_current_experiment": sum(1 for item in queue if isinstance(item, dict) and item.get("blocks_current_experiment")),
    }


def _expansion_reason(branch: dict[str, Any]) -> str:
    if branch.get("manager_status") == "needs_human_repair":
        return "有可用方向但需要先补证或修复审计问题"
    return "非选中分支中分数较高且审计未阻断"


def _rationale(decision: str, execution_policy: str, selected: dict[str, Any]) -> str:
    if not selected:
        return "探索图没有选中可执行分支。"
    return (
        f"选择 {selected.get('branch_id')}：{selected.get('title')}；"
        f"manager_decision={decision}，execution_policy={execution_policy}，"
        f"score={float(selected.get('score') or 0.0):.2f}，risk={selected.get('risk') or 0}，evidence={selected.get('evidence_count') or 0}。"
    )


def _item_for_title(report: dict[str, Any] | None, title: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if isinstance(item, dict) and str(item.get("idea_title") or "") == title:
            return item
    return {}


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
