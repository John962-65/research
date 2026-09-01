from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text, cell as _cell


MULTI_AGENT_DELIBERATION_JSON = "10-agent-deliberation.json"
MULTI_AGENT_DELIBERATION_MD = "10-agent-deliberation.md"


ROLE_ORDER = [
    "literature_scout",
    "evidence_curator",
    "gap_analyst",
    "method_architect",
    "benchmark_engineer",
    "statistician",
    "skeptical_reviewer",
    "manuscript_editor",
]


def write_multi_agent_deliberation_artifacts(
    topic: str,
    agent_assignment: dict[str, Any] | None,
    agent_claim_audit: dict[str, Any] | None,
    claim_traceability: Any,
    citation_grounding: Any,
    citation_coverage: dict[str, Any] | None,
    results_presentation: Any,
    claim_consistency: Any,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_multi_agent_deliberation(
        topic,
        agent_assignment,
        agent_claim_audit,
        claim_traceability,
        citation_grounding,
        citation_coverage,
        results_presentation,
        claim_consistency,
    )
    write_json(run_dir / MULTI_AGENT_DELIBERATION_JSON, report)
    write_text(run_dir / MULTI_AGENT_DELIBERATION_MD, render_multi_agent_deliberation_markdown(report))
    return report


def build_multi_agent_deliberation(
    topic: str,
    agent_assignment: dict[str, Any] | None,
    agent_claim_audit: dict[str, Any] | None,
    claim_traceability: Any,
    citation_grounding: Any,
    citation_coverage: dict[str, Any] | None,
    results_presentation: Any,
    claim_consistency: Any,
) -> dict[str, Any]:
    assignment = agent_assignment if isinstance(agent_assignment, dict) else {}
    claim_audit = agent_claim_audit if isinstance(agent_claim_audit, dict) else {}
    active_agents = _active_agents(assignment, claim_audit)
    verdicts = [
        _agent_verdict(
            agent_id,
            claim_audit,
            claim_traceability,
            citation_grounding,
            citation_coverage if isinstance(citation_coverage, dict) else {},
            results_presentation,
            claim_consistency,
        )
        for agent_id in active_agents
    ]
    family_check = _role_family_check(active_agents)
    conflicts = _conflicts(verdicts)
    consensus = _consensus(verdicts, family_check, conflicts)
    blocking = [action for verdict in verdicts if verdict["verdict"] == "block" for action in verdict["required_actions"]]
    manual = [action for verdict in verdicts if verdict["verdict"] == "revise" for action in verdict["required_actions"]]
    if family_check["status"] == "block":
        blocking.extend(family_check["required_actions"])
    elif family_check["status"] == "review_required":
        manual.extend(family_check["required_actions"])
    manual.extend(conflict["resolution"] for conflict in conflicts)
    rules_status = "block" if consensus["decision"] == "block" else "review_required" if consensus["decision"] == "revise" else "pass"
    status = "block" if rules_status == "block" else "review_required"
    if rules_status == "pass":
        manual.append("当前 verdict 来自确定性角色规则投影，不是独立 Agent 执行；必须人工复核或接入独立模型上下文后才能形成多智能体共识。")
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "rules_status": rules_status,
        "assessment_kind": "deterministic_role_projection",
        "independent_agent_execution": False,
        "independent_verdict_count": 0,
        "consensus": consensus,
        "active_agents": active_agents,
        "agent_verdicts": verdicts,
        "role_family_check": family_check,
        "conflicts": conflicts,
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "recommended_actions": _recommended_actions(status, consensus, conflicts),
    }


def render_multi_agent_deliberation_markdown(report: dict[str, Any]) -> str:
    consensus = report.get("consensus") if isinstance(report.get("consensus"), dict) else {}
    lines = [
        f"# 角色规则审计（非独立 Agent）：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 规则汇总：{consensus.get('decision') or '-'}",
        f"- 评估类型：{report.get('assessment_kind') or '-'}",
        f"- 独立 Agent 执行：{'是' if report.get('independent_agent_execution') is True else '否'}",
        f"- 阻断/修订/批准：{consensus.get('block', 0)}/{consensus.get('revise', 0)}/{consensus.get('approve', 0)}",
        f"- 活跃智能体：{', '.join(str(item) for item in report.get('active_agents', []) if str(item).strip()) or '-'}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("recommended_actions", "推荐动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.append(f"## {title}")
        lines.extend(f"- [ ] {item}" for item in values) if values else lines.append("- 无")
        lines.append("")
    lines.extend(["## Agent Verdicts", "| Agent | Verdict | Confidence | Evidence | Required actions | Handoff |", "| --- | --- | --- | --- | --- | --- |"])
    for verdict in report.get("agent_verdicts", []) if isinstance(report.get("agent_verdicts"), list) else []:
        if not isinstance(verdict, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(verdict.get("agent_id") or "")),
                    _cell(str(verdict.get("verdict") or "")),
                    _cell(str(verdict.get("confidence") or "")),
                    _cell("；".join(str(item) for item in verdict.get("evidence", []) if str(item).strip()) or "-"),
                    _cell("；".join(str(item) for item in verdict.get("required_actions", []) if str(item).strip()) or "-"),
                    _cell(", ".join(str(item) for item in verdict.get("handoff_to", []) if str(item).strip()) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Conflicts", "| Conflict | Agents | Resolution |", "| --- | --- | --- |"])
    conflicts = report.get("conflicts") if isinstance(report.get("conflicts"), list) else []
    if conflicts:
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(conflict.get("type") or "")),
                        _cell(", ".join(str(item) for item in conflict.get("agents", []) if str(item).strip()) or "-"),
                        _cell(str(conflict.get("resolution") or "")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - |")
    return "\n".join(lines)


def _active_agents(assignment: dict[str, Any], agent_claim_audit: dict[str, Any]) -> list[str]:
    routed = _route_agents(assignment, "paper_deliberation")
    if routed:
        return [role for role in ROLE_ORDER if role in set(routed)] + [role for role in routed if role not in ROLE_ORDER]
    agents = _clean_roles(assignment.get("active_agents") if isinstance(assignment.get("active_agents"), list) else [])
    if not agents:
        agents = _clean_roles(agent_claim_audit.get("active_agents") if isinstance(agent_claim_audit.get("active_agents"), list) else [])
    return [role for role in ROLE_ORDER if role in set(agents)] + [role for role in agents if role not in ROLE_ORDER]


def _route_agents(assignment: dict[str, Any], task_type: str) -> list[str]:
    routes = assignment.get("task_routes") if isinstance(assignment.get("task_routes"), list) else []
    for route in routes:
        if not isinstance(route, dict) or str(route.get("task_type") or "") != task_type:
            continue
        if str(route.get("status") or "") not in {"active", "repair"}:
            continue
        agents = route.get("all_agents") if isinstance(route.get("all_agents"), list) else []
        if not agents:
            agents = [*(route.get("primary_agents") if isinstance(route.get("primary_agents"), list) else []), *(route.get("support_agents") if isinstance(route.get("support_agents"), list) else [])]
        return _clean_roles(agents)
    return []


def _agent_verdict(
    agent_id: str,
    agent_claim_audit: dict[str, Any],
    claim_traceability: Any,
    citation_grounding: Any,
    citation_coverage: dict[str, Any],
    results_presentation: Any,
    claim_consistency: Any,
) -> dict[str, Any]:
    if agent_id == "literature_scout":
        return _literature_scout_verdict(citation_grounding, citation_coverage)
    if agent_id == "evidence_curator":
        return _evidence_curator_verdict(claim_traceability, citation_grounding)
    if agent_id == "gap_analyst":
        return _gap_analyst_verdict(claim_consistency)
    if agent_id == "method_architect":
        return _method_architect_verdict(agent_claim_audit, claim_consistency)
    if agent_id == "benchmark_engineer":
        return _benchmark_engineer_verdict(claim_traceability, results_presentation)
    if agent_id == "statistician":
        return _statistician_verdict(results_presentation, claim_consistency)
    if agent_id == "skeptical_reviewer":
        return _skeptical_reviewer_verdict(agent_claim_audit, claim_traceability, claim_consistency)
    if agent_id == "manuscript_editor":
        return _manuscript_editor_verdict(agent_claim_audit, claim_traceability, results_presentation, claim_consistency)
    return _verdict(agent_id, "revise", 0.25, [f"unknown_agent={agent_id}"], ["为未知 agent 定义独立审计规则。"], [])


def _literature_scout_verdict(citation_grounding: Any, citation_coverage: dict[str, Any]) -> dict[str, Any]:
    statuses = [_status(citation_grounding), _status(citation_coverage)]
    evidence = [f"citation_grounding={statuses[0] or '-'}", f"citation_coverage={statuses[1] or '-'}"]
    actions = _actions(citation_grounding) + _actions(citation_coverage)
    return _status_verdict("literature_scout", statuses, evidence, actions or ["核对未覆盖高相关文献和未知 citation key。"], ["evidence_curator"])


def _evidence_curator_verdict(claim_traceability: Any, citation_grounding: Any) -> dict[str, Any]:
    statuses = [_status(claim_traceability), _status(citation_grounding)]
    evidence = [
        f"claim_traceability={statuses[0] or '-'}",
        f"citation_grounding={statuses[1] or '-'}",
        f"blocked_claims={_int(_get(claim_traceability, 'blocked_claims'))}",
        f"blocked_citations={_int(_get(citation_grounding, 'blocked_citations'))}",
    ]
    actions = _actions(claim_traceability) + _actions(citation_grounding)
    return _status_verdict("evidence_curator", statuses, evidence, actions or ["复核 claim 到 citation/result/runbook 的证据链。"], ["skeptical_reviewer", "manuscript_editor"])


def _gap_analyst_verdict(claim_consistency: Any) -> dict[str, Any]:
    status = _status(claim_consistency)
    evidence = [f"claim_consistency={status or '-'}", f"consistency_score={_get(claim_consistency, 'consistency_score') or '-'}"]
    actions = _actions(claim_consistency)
    return _status_verdict("gap_analyst", [status], evidence, actions or ["确认结论边界仍对齐研究 gap 和假设结果。"], ["method_architect", "skeptical_reviewer"])


def _method_architect_verdict(agent_claim_audit: dict[str, Any], claim_consistency: Any) -> dict[str, Any]:
    orphaned = _int(_nested(agent_claim_audit, "claim_owner_summary", "orphaned_claims"))
    statuses = [_status(agent_claim_audit), _status(claim_consistency)]
    evidence = [f"agent_claim_audit={statuses[0] or '-'}", f"claim_consistency={statuses[1] or '-'}", f"orphaned_claims={orphaned}"]
    actions = _actions(agent_claim_audit) + _actions(claim_consistency)
    if orphaned:
        actions.append("把无 owner 的方法/实验 claim 分配给 method、benchmark 或 statistics 角色。")
    return _status_verdict("method_architect", statuses, evidence, actions or ["确认方法 claim 未超出 candidate/baseline/ablation 设计。"], ["benchmark_engineer", "statistician"])


def _benchmark_engineer_verdict(claim_traceability: Any, results_presentation: Any) -> dict[str, Any]:
    inventory = _get(claim_traceability, "evidence_inventory")
    has_runbook = bool(inventory.get("has_runbook")) if isinstance(inventory, dict) else False
    has_results = bool(inventory.get("has_results")) if isinstance(inventory, dict) else False
    statuses = [_status(claim_traceability), _status(results_presentation)]
    evidence = [f"claim_traceability={statuses[0] or '-'}", f"results_presentation={statuses[1] or '-'}", f"has_runbook={has_runbook}", f"has_results={has_results}"]
    actions = _actions(claim_traceability) + _actions(results_presentation)
    if not has_runbook or not has_results:
        return _verdict("benchmark_engineer", "block", 0.9, evidence, actions + ["补齐 runbook/results 产物后再允许实验 claim。"], ["statistician", "skeptical_reviewer"])
    return _status_verdict("benchmark_engineer", statuses, evidence, actions or ["确认 benchmark manifest、runbook 和结果产物仍可复现。"], ["statistician"])


def _statistician_verdict(results_presentation: Any, claim_consistency: Any) -> dict[str, Any]:
    statuses = [_status(results_presentation), _status(claim_consistency)]
    evidence = [
        f"results_presentation={statuses[0] or '-'}",
        f"claim_consistency={statuses[1] or '-'}",
        f"presentation_score={_get(results_presentation, 'presentation_score') or '-'}",
        f"consistency_score={_get(claim_consistency, 'consistency_score') or '-'}",
    ]
    actions = _actions(results_presentation) + _actions(claim_consistency)
    return _status_verdict("statistician", statuses, evidence, actions or ["确认 CI、effect size、repeats 和负/中性结果边界。"], ["skeptical_reviewer", "manuscript_editor"])


def _skeptical_reviewer_verdict(agent_claim_audit: dict[str, Any], claim_traceability: Any, claim_consistency: Any) -> dict[str, Any]:
    orphaned = _int(_nested(agent_claim_audit, "claim_owner_summary", "orphaned_claims"))
    statuses = [_status(agent_claim_audit), _status(claim_traceability), _status(claim_consistency)]
    evidence = [f"agent_claim_audit={statuses[0] or '-'}", f"claim_traceability={statuses[1] or '-'}", f"claim_consistency={statuses[2] or '-'}", f"orphaned_claims={orphaned}"]
    actions = _actions(agent_claim_audit) + _actions(claim_traceability) + _actions(claim_consistency)
    if orphaned:
        actions.append("对无 owner claim 执行降级、删除或补证。")
    return _status_verdict("skeptical_reviewer", statuses, evidence, actions or ["保留负/中性边界，禁止 superiority 越界。"], ["manuscript_editor"])


def _manuscript_editor_verdict(agent_claim_audit: dict[str, Any], claim_traceability: Any, results_presentation: Any, claim_consistency: Any) -> dict[str, Any]:
    statuses = [_status(agent_claim_audit), _status(claim_traceability), _status(results_presentation), _status(claim_consistency)]
    evidence = [f"agent_claim_audit={statuses[0] or '-'}", f"claim_traceability={statuses[1] or '-'}", f"results_presentation={statuses[2] or '-'}", f"claim_consistency={statuses[3] or '-'}"]
    actions = _actions(agent_claim_audit) + _actions(claim_traceability) + _actions(results_presentation) + _actions(claim_consistency)
    return _status_verdict("manuscript_editor", statuses, evidence, actions or ["把 reviewer/statistician/evidence verdict 反映到修订稿和投稿包。"], ["skeptical_reviewer"])


def _status_verdict(agent_id: str, statuses: list[str], evidence: list[str], actions: list[str], handoff_to: list[str]) -> dict[str, Any]:
    normalized = {_normalize_status(status) for status in statuses if status}
    if "block" in normalized:
        return _verdict(agent_id, "block", 0.9, evidence, actions, handoff_to)
    if "review" in normalized or not normalized:
        return _verdict(agent_id, "revise", 0.75, evidence, actions, handoff_to)
    return _verdict(agent_id, "approve", 0.85, evidence, [], handoff_to)


def _verdict(agent_id: str, verdict: str, confidence: float, evidence: list[str], actions: list[str], handoff_to: list[str]) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "verdict": verdict,
        "confidence": confidence,
        "verdict_source": "deterministic_role_rule",
        "evidence": _unique(evidence),
        "required_actions": _unique(actions),
        "handoff_to": _unique(handoff_to),
    }


def _role_family_check(active_agents: list[str]) -> dict[str, Any]:
    if not active_agents:
        return {"status": "block", "evidence": ["active_agents=0"], "required_actions": ["缺少 active_agents，不能执行多智能体 deliberation。"]}
    active = set(active_agents)
    families = {
        "literature_or_evidence": {"literature_scout", "evidence_curator"},
        "method": {"method_architect"},
        "execution_or_statistics": {"benchmark_engineer", "statistician"},
        "skeptical_review": {"skeptical_reviewer"},
        "writing": {"manuscript_editor"},
    }
    missing = [name for name, roles in families.items() if not (active & roles)]
    evidence = [f"active_agents={', '.join(active_agents)}", f"missing={', '.join(missing) or '-'}"]
    if not missing:
        return {"status": "pass", "evidence": evidence, "required_actions": []}
    return {"status": "review_required", "evidence": evidence, "required_actions": ["补齐 deliberation 角色族：" + ", ".join(missing)]}


def _conflicts(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_agent = {str(item.get("agent_id")): str(item.get("verdict")) for item in verdicts}
    conflicts: list[dict[str, Any]] = []
    if by_agent.get("manuscript_editor") == "approve" and by_agent.get("skeptical_reviewer") in {"revise", "block"}:
        conflicts.append({"type": "editor_vs_reviewer", "agents": ["manuscript_editor", "skeptical_reviewer"], "resolution": "以 skeptical_reviewer 的边界 verdict 为准，先修订再交付。"})
    if by_agent.get("benchmark_engineer") == "approve" and by_agent.get("statistician") in {"revise", "block"}:
        conflicts.append({"type": "execution_vs_statistics", "agents": ["benchmark_engineer", "statistician"], "resolution": "执行产物可用但统计呈现不足，先补统计边界和结果报告。"})
    if by_agent.get("literature_scout") == "approve" and by_agent.get("evidence_curator") in {"revise", "block"}:
        conflicts.append({"type": "source_vs_evidence", "agents": ["literature_scout", "evidence_curator"], "resolution": "文献入口可用但 claim grounding 不足，先补 citation/chunk 对齐。"})
    return conflicts


def _consensus(verdicts: list[dict[str, Any]], family_check: dict[str, Any], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "approve": sum(1 for verdict in verdicts if verdict.get("verdict") == "approve"),
        "revise": sum(1 for verdict in verdicts if verdict.get("verdict") == "revise"),
        "block": sum(1 for verdict in verdicts if verdict.get("verdict") == "block"),
    }
    if family_check.get("status") == "block" or counts["block"]:
        decision = "block"
    elif family_check.get("status") == "review_required" or counts["revise"] or conflicts:
        decision = "revise"
    else:
        decision = "approve"
    return {
        "decision": decision,
        "approve": counts["approve"],
        "revise": counts["revise"],
        "block": counts["block"],
        "conflicts": len(conflicts),
        "family_status": family_check.get("status") or "",
    }


def _recommended_actions(status: str, consensus: dict[str, Any], conflicts: list[dict[str, Any]]) -> list[str]:
    if status == "block":
        return ["按 block verdict 修复证据、统计或 claim 边界，再重新生成最终论文审计。"]
    if status == "review_required":
        actions = ["人工核对 10-agent-deliberation.md；当前规则投影不能作为独立多智能体共识证据。"]
        actions.extend(str(conflict.get("resolution")) for conflict in conflicts[:3] if isinstance(conflict, dict))
        if consensus.get("family_status") == "review_required":
            actions.append("补齐缺失角色族或把相关 claim 降级为待补证。")
        return _unique(actions)
    return ["角色规则汇总为 approve；仍需独立 Agent 执行证据或人工复核。"]


def _status(value: Any) -> str:
    return str(_get(value, "status") or "")


def _normalize_status(status: str) -> str:
    value = str(status or "").strip().lower()
    if value in {"pass", "ready", "ready_for_release", "ready_for_submission_check", "ready_for_human_polish"}:
        return "pass"
    if value in {"block", "blocked", "fail", "failed", "requires_human_evidence", "requires_revision"}:
        return "block"
    if value:
        return "review"
    return ""


def _actions(value: Any) -> list[str]:
    return _list(_get(value, "blocking_issues")) + _list(_get(value, "manual_tasks")) + _list(_get(value, "required_actions"))


def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _nested(value: dict[str, Any], key: str, nested_key: str) -> Any:
    child = value.get(key) if isinstance(value.get(key), dict) else {}
    return child.get(nested_key)


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


