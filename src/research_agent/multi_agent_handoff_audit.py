from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExperimentPlan, ResearchIdea


MULTI_AGENT_HANDOFF_AUDIT_JSON = "03-agent-handoff-audit.json"
MULTI_AGENT_HANDOFF_AUDIT_MD = "03-agent-handoff-audit.md"


def write_multi_agent_handoff_audit_artifacts(
    topic: str,
    selected_idea: ResearchIdea,
    experiment_plan: ExperimentPlan,
    agent_assignment: dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_multi_agent_handoff_audit(topic, selected_idea, experiment_plan, agent_assignment)
    write_json(run_dir / MULTI_AGENT_HANDOFF_AUDIT_JSON, report)
    write_text(run_dir / MULTI_AGENT_HANDOFF_AUDIT_MD, render_multi_agent_handoff_audit_markdown(report))
    return report


def build_multi_agent_handoff_audit(
    topic: str,
    selected_idea: ResearchIdea,
    experiment_plan: ExperimentPlan,
    agent_assignment: dict[str, Any] | None,
) -> dict[str, Any]:
    assignment = agent_assignment if isinstance(agent_assignment, dict) else {}
    checks = [
        _assignment_present(assignment),
        _idea_roles_check(selected_idea),
        _experiment_roles_check(selected_idea, experiment_plan),
        _role_family_check(selected_idea, experiment_plan, assignment),
    ]
    blocking = [action for check in checks if check["status"] == "block" for action in check["required_actions"]]
    manual = [action for check in checks if check["status"] == "review_required" for action in check["required_actions"]]
    status = "block" if blocking else "review_required" if manual else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "selected_idea_title": selected_idea.title,
        "experiment_plan_title": experiment_plan.idea_title,
        "idea_agent_roles": selected_idea.agent_roles,
        "experiment_agent_roles": experiment_plan.agent_roles,
        "active_agents": assignment.get("active_agents", []) if isinstance(assignment.get("active_agents"), list) else [],
        "checks": checks,
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "recommended_actions": _recommended_actions(status, blocking, manual),
    }


def render_multi_agent_handoff_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 多智能体 Handoff 审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 选中 idea：{report.get('selected_idea_title') or '-'}",
        f"- 实验计划：{report.get('experiment_plan_title') or '-'}",
        f"- Idea roles：{', '.join(str(item) for item in report.get('idea_agent_roles', []) if str(item).strip()) or '-'}",
        f"- Experiment roles：{', '.join(str(item) for item in report.get('experiment_agent_roles', []) if str(item).strip()) or '-'}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("recommended_actions", "推荐动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.append(f"## {title}")
        lines.extend(f"- [ ] {item}" for item in values) if values else lines.append("- 无")
        lines.append("")
    lines.extend(["## 检查表", "| 检查 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
    for check in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if not isinstance(check, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(check.get("name") or "")),
                    _cell(str(check.get("status") or "")),
                    _cell("；".join(str(item) for item in check.get("evidence", []) if str(item).strip()) or "-"),
                    _cell("；".join(str(item) for item in check.get("required_actions", []) if str(item).strip()) or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _assignment_present(assignment: dict[str, Any]) -> dict[str, Any]:
    tasks = assignment.get("tasks") if isinstance(assignment.get("tasks"), list) else []
    active = assignment.get("active_agents") if isinstance(assignment.get("active_agents"), list) else []
    if tasks and active:
        return _check("assignment_present", "pass", [f"tasks={len(tasks)}", f"active_agents={len(active)}"], [])
    return _check(
        "assignment_present",
        "block",
        [f"tasks={len(tasks)}", f"active_agents={len(active)}"],
        ["缺少 02-agent-team.json 或其中没有 active_agents；必须先生成多智能体任务分配。"],
    )


def _idea_roles_check(idea: ResearchIdea) -> dict[str, Any]:
    roles = _clean_roles(idea.agent_roles)
    if "method_architect" in roles and len(roles) >= 2:
        return _check("idea_agent_roles", "pass", [f"roles={', '.join(roles)}"], [])
    if roles:
        return _check(
            "idea_agent_roles",
            "review_required",
            [f"roles={', '.join(roles)}"],
            ["选中 idea 的 agent_roles 应包含 method_architect，并至少再包含一个证据、benchmark、统计或复核角色。"],
        )
    return _check("idea_agent_roles", "block", ["roles=0"], ["选中 idea 缺少 agent_roles，不能证明多智能体分工进入 idea 阶段。"])


def _experiment_roles_check(idea: ResearchIdea, plan: ExperimentPlan) -> dict[str, Any]:
    idea_roles = set(_clean_roles(idea.agent_roles))
    plan_roles = set(_clean_roles(plan.agent_roles))
    overlap = sorted(idea_roles & plan_roles)
    if plan_roles and "method_architect" in plan_roles and overlap:
        return _check("experiment_agent_roles", "pass", [f"plan_roles={', '.join(sorted(plan_roles))}", f"overlap={', '.join(overlap)}"], [])
    if plan_roles:
        return _check(
            "experiment_agent_roles",
            "review_required",
            [f"plan_roles={', '.join(sorted(plan_roles))}", f"overlap={', '.join(overlap) or '0'}"],
            ["03-experiment-plan 的 agent_roles 应继承选中 idea 的 method_architect 和至少一个其他角色。"],
        )
    return _check("experiment_agent_roles", "block", ["plan_roles=0"], ["03-experiment-plan 缺少 agent_roles，不能进入多智能体执行前 handoff。"])


def _role_family_check(idea: ResearchIdea, plan: ExperimentPlan, assignment: dict[str, Any]) -> dict[str, Any]:
    roles = set(_clean_roles([*idea.agent_roles, *plan.agent_roles]))
    active = set(_clean_roles(assignment.get("active_agents") if isinstance(assignment.get("active_agents"), list) else []))
    required_families = {
        "evidence_or_gap": {"literature_scout", "evidence_curator", "gap_analyst"},
        "method": {"method_architect"},
        "execution_or_statistics": {"benchmark_engineer", "statistician"},
        "skeptical_review": {"skeptical_reviewer"},
    }
    missing = [name for name, options in required_families.items() if not (roles & options)]
    inactive = sorted((roles - active) - {"method_architect"}) if active else []
    evidence = [f"roles={', '.join(sorted(roles)) or '-'}", f"active={', '.join(sorted(active)) or '-'}"]
    if not missing and not inactive:
        return _check("role_family_coverage", "pass", evidence, [])
    actions = []
    if missing:
        actions.append("补齐多智能体角色族：" + ", ".join(missing))
    if inactive:
        actions.append("确认这些 idea/plan roles 是否仍由 02-agent-team 激活：" + ", ".join(inactive))
    return _check("role_family_coverage", "review_required", evidence, actions)


def _check(name: str, status: str, evidence: list[str], actions: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "evidence": evidence,
        "required_actions": actions,
    }


def _recommended_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "block":
        return ["先修复多智能体 handoff 断链，再继续实验执行。", *blocking[:3]]
    if status == "review_required":
        return ["人工核对 03-agent-handoff-audit.md；缺失角色只允许支撑降级 claim。", *manual[:3]]
    return ["多智能体 handoff 已从 02-agent-team 延伸到 idea 和 experiment plan。"]


def _clean_roles(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return _unique([str(item).strip() for item in values if str(item).strip()])


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
