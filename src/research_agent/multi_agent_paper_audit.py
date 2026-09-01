from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ClaimTraceabilityReport, ExperimentPlan, PaperReview, ResearchIdea


MULTI_AGENT_PAPER_AUDIT_JSON = "10-agent-claim-audit.json"
MULTI_AGENT_PAPER_AUDIT_MD = "10-agent-claim-audit.md"


def write_multi_agent_paper_audit_artifacts(
    topic: str,
    selected_idea: ResearchIdea,
    experiment_plan: ExperimentPlan,
    paper_review: PaperReview,
    revised_review: PaperReview,
    claim_traceability: ClaimTraceabilityReport,
    agent_assignment: dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_multi_agent_paper_audit(
        topic,
        selected_idea,
        experiment_plan,
        paper_review,
        revised_review,
        claim_traceability,
        agent_assignment,
        run_dir,
    )
    write_json(run_dir / MULTI_AGENT_PAPER_AUDIT_JSON, report)
    write_text(run_dir / MULTI_AGENT_PAPER_AUDIT_MD, render_multi_agent_paper_audit_markdown(report))
    return report


def build_multi_agent_paper_audit(
    topic: str,
    selected_idea: ResearchIdea,
    experiment_plan: ExperimentPlan,
    paper_review: PaperReview,
    revised_review: PaperReview,
    claim_traceability: ClaimTraceabilityReport,
    agent_assignment: dict[str, Any] | None,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    assignment = agent_assignment if isinstance(agent_assignment, dict) else {}
    active_agents = _clean_roles(assignment.get("active_agents") if isinstance(assignment.get("active_agents"), list) else [])
    combined_roles = _unique([*active_agents, *selected_idea.agent_roles, *experiment_plan.agent_roles])
    claim_matrix = _claim_role_matrix(claim_traceability, active_agents)
    checks = [
        _assignment_present(assignment),
        _handoff_roles_check(selected_idea, experiment_plan),
        _paper_role_family_check(combined_roles),
        _review_loop_check(paper_review, revised_review),
        _claim_traceability_check(claim_traceability),
        _claim_owner_check(claim_matrix),
        _paper_artifacts_check(run_dir),
    ]
    blocking = [action for check in checks if check["status"] == "block" for action in check["required_actions"]]
    manual = [action for check in checks if check["status"] == "review_required" for action in check["required_actions"]]
    status = "block" if blocking else "review_required" if manual else "pass"
    orphaned = [item for item in claim_matrix if item.get("owner_status") != "pass"]
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "selected_idea_title": selected_idea.title,
        "experiment_plan_title": experiment_plan.idea_title,
        "idea_agent_roles": selected_idea.agent_roles,
        "experiment_agent_roles": experiment_plan.agent_roles,
        "active_agents": active_agents,
        "paper_stage_roles": _paper_stage_roles(combined_roles),
        "claim_owner_summary": {
            "total_claims": len(claim_matrix),
            "mapped_claims": len(claim_matrix) - len(orphaned),
            "orphaned_claims": len(orphaned),
        },
        "claim_role_matrix": claim_matrix,
        "checks": checks,
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "recommended_actions": _recommended_actions(status, blocking, manual),
    }


def render_multi_agent_paper_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 多智能体 Claim 审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 选中 idea：{report.get('selected_idea_title') or '-'}",
        f"- 实验计划：{report.get('experiment_plan_title') or '-'}",
        f"- 活跃智能体：{', '.join(str(item) for item in report.get('active_agents', []) if str(item).strip()) or '-'}",
        f"- Idea roles：{', '.join(str(item) for item in report.get('idea_agent_roles', []) if str(item).strip()) or '-'}",
        f"- Experiment roles：{', '.join(str(item) for item in report.get('experiment_agent_roles', []) if str(item).strip()) or '-'}",
        "",
    ]
    summary = report.get("claim_owner_summary") if isinstance(report.get("claim_owner_summary"), dict) else {}
    lines.extend(
        [
            "## Claim Owner Summary",
            f"- Claims：{summary.get('total_claims', 0)}",
            f"- 已映射/需复核：{summary.get('mapped_claims', 0)}/{summary.get('orphaned_claims', 0)}",
            "",
        ]
    )
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
    lines.extend(["", "## Claim Role Matrix", "| 决策 | Claim | Owners | 缺失 | 证据 |", "| --- | --- | --- | --- | --- |"])
    for item in report.get("claim_role_matrix", []) if isinstance(report.get("claim_role_matrix"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("decision") or "")),
                    _cell(str(item.get("claim") or "")),
                    _cell(", ".join(str(role) for role in item.get("owners", []) if str(role).strip()) or "-"),
                    _cell(", ".join(str(role) for role in item.get("missing_active_owners", []) if str(role).strip()) or "-"),
                    _cell(str(item.get("evidence_profile") or "")),
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
        ["缺少 02-agent-team.json 或 active_agents，无法证明论文阶段 claim 由多智能体分工负责。"],
    )


def _handoff_roles_check(idea: ResearchIdea, plan: ExperimentPlan) -> dict[str, Any]:
    idea_roles = set(_clean_roles(idea.agent_roles))
    plan_roles = set(_clean_roles(plan.agent_roles))
    overlap = sorted(idea_roles & plan_roles)
    if idea_roles and plan_roles and overlap:
        return _check("paper_stage_handoff_roles", "pass", [f"idea_roles={len(idea_roles)}", f"plan_roles={len(plan_roles)}", f"overlap={', '.join(overlap)}"], [])
    if not idea_roles or not plan_roles:
        return _check("paper_stage_handoff_roles", "block", [f"idea_roles={len(idea_roles)}", f"plan_roles={len(plan_roles)}"], ["补齐 02-ideas.json 和 03-experiment-plan.json 中的 agent_roles，再生成论文阶段审计。"])
    return _check("paper_stage_handoff_roles", "review_required", [f"idea_roles={len(idea_roles)}", f"plan_roles={len(plan_roles)}", "overlap=0"], ["确认 03-experiment-plan 的 agent_roles 是否继承选中 idea 的多智能体分工。"])


def _paper_role_family_check(roles: list[str]) -> dict[str, Any]:
    role_set = set(_clean_roles(roles))
    required = {
        "writer": {"manuscript_editor"},
        "reviewer": {"skeptical_reviewer"},
        "evidence": {"literature_scout", "evidence_curator"},
        "execution_or_statistics": {"benchmark_engineer", "statistician"},
    }
    missing = [name for name, options in required.items() if not (role_set & options)]
    evidence = [f"roles={', '.join(sorted(role_set)) or '-'}"]
    if not missing:
        return _check("paper_role_family_coverage", "pass", evidence, [])
    return _check("paper_role_family_coverage", "review_required", evidence, ["补齐论文阶段角色族：" + ", ".join(missing)])


def _review_loop_check(paper_review: PaperReview, revised_review: PaperReview) -> dict[str, Any]:
    initial_claims = len(paper_review.claim_audit)
    revised_claims = len(revised_review.claim_audit)
    evidence = [f"initial_claim_audit={initial_claims}", f"revised_claim_audit={revised_claims}"]
    if initial_claims and revised_claims:
        return _check("review_loop_claim_audit", "pass", evidence, [])
    if revised_claims:
        return _check("review_loop_claim_audit", "review_required", evidence, ["初稿复核缺少 claim_audit，修订稿 claim audit 只能作为补救证据。"])
    return _check("review_loop_claim_audit", "block", evidence, ["修订稿复核缺少 claim_audit，不能给 claim 分配多智能体责任。"])


def _claim_traceability_check(report: ClaimTraceabilityReport) -> dict[str, Any]:
    evidence = [
        f"status={report.status}",
        f"claims={report.total_claims}",
        f"blocked_claims={report.blocked_claims}",
        f"traceability_score={report.traceability_score:.3f}",
    ]
    if report.total_claims <= 0:
        return _check("claim_traceability_present", "block", evidence, ["10-claim-traceability.json 没有可审计 claim。"])
    if report.blocked_claims or report.status == "block":
        return _check("claim_traceability_present", "review_required", evidence, ["先处理 claim traceability 阻断项，再把对应 claim 标给 evidence/stat/reviewer 角色复核。"])
    return _check("claim_traceability_present", "pass", evidence, [])


def _claim_owner_check(matrix: list[dict[str, Any]]) -> dict[str, Any]:
    if not matrix:
        return _check("claim_owner_matrix", "block", ["claims=0"], ["没有 claim-role matrix，无法证明论文阶段多智能体责任可追踪。"])
    orphaned = [item for item in matrix if item.get("owner_status") != "pass"]
    evidence = [f"claims={len(matrix)}", f"orphaned={len(orphaned)}"]
    if not orphaned:
        return _check("claim_owner_matrix", "pass", evidence, [])
    missing = sorted({role for item in orphaned for role in item.get("missing_active_owners", []) if str(role).strip()})
    return _check("claim_owner_matrix", "review_required", evidence, ["这些 claim owner 未在 active_agents 中激活：" + ", ".join(missing or ["unknown"])])


def _paper_artifacts_check(run_dir: Path | None) -> dict[str, Any]:
    if run_dir is None:
        return _check("paper_stage_artifacts", "review_required", ["run_dir=not_provided"], ["写入 run 目录时应核对论文、复核和 claim traceability 产物是否存在。"])
    required = ["07-paper-review.json", "09-revised-paper.md", "10-revised-paper-review.json", "10-claim-traceability.json"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if not missing:
        return _check("paper_stage_artifacts", "pass", [f"required={len(required)}"], [])
    return _check("paper_stage_artifacts", "review_required", [f"missing={', '.join(missing)}"], ["补齐论文阶段产物：" + ", ".join(missing)])


def _claim_role_matrix(report: ClaimTraceabilityReport, active_agents: list[str]) -> list[dict[str, Any]]:
    active = set(_clean_roles(active_agents))
    rows: list[dict[str, Any]] = []
    for item in report.items:
        owners = _claim_owners(item.evidence_keys, item.result_refs, item.result_status, item.runbook_status)
        missing = sorted(role for role in owners if active and role not in active)
        rows.append(
            {
                "claim": item.claim,
                "decision": item.decision,
                "support_level": item.support_level,
                "owners": owners,
                "missing_active_owners": missing,
                "owner_status": "pass" if not missing and owners else "review_required",
                "evidence_profile": _evidence_profile(item.evidence_keys, item.result_refs, item.result_status, item.runbook_status),
            }
        )
    return rows


def _claim_owners(evidence_keys: list[str], result_refs: list[str], result_status: str, runbook_status: str) -> list[str]:
    owners = ["manuscript_editor", "skeptical_reviewer"]
    if evidence_keys:
        owners.extend(["evidence_curator", "literature_scout"])
    if result_refs or result_status not in {"not_required", "not_provided"} or runbook_status not in {"not_required", "not_provided"}:
        owners.extend(["benchmark_engineer", "statistician"])
    return _unique(owners)


def _paper_stage_roles(roles: list[str]) -> dict[str, list[str]]:
    role_set = set(_clean_roles(roles))
    return {
        "writer": sorted(role_set & {"manuscript_editor"}),
        "reviewer": sorted(role_set & {"skeptical_reviewer"}),
        "evidence": sorted(role_set & {"literature_scout", "evidence_curator"}),
        "execution_or_statistics": sorted(role_set & {"benchmark_engineer", "statistician"}),
    }


def _evidence_profile(evidence_keys: list[str], result_refs: list[str], result_status: str, runbook_status: str) -> str:
    parts = [f"citations={len(evidence_keys)}", f"results={len(result_refs)}", f"result_status={result_status}", f"runbook_status={runbook_status}"]
    return "; ".join(parts)


def _check(name: str, status: str, evidence: list[str], actions: list[str]) -> dict[str, Any]:
    return {"name": name, "status": status, "evidence": evidence, "required_actions": actions}


def _recommended_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "block":
        return ["先修复论文阶段多智能体责任断链，再把该 run 作为论文级证据。", *blocking[:3]]
    if status == "review_required":
        return ["人工核对 10-agent-claim-audit.md；缺失 owner 的 claim 只能保留为弱支撑或待补证。", *manual[:3]]
    return ["论文阶段 claim 已映射到写作、复核、证据和统计/benchmark 角色。"]


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
