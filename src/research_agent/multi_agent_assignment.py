from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text, cell as _cell
from .config import ExecutionConfig
from .models import LiteratureContext, LiteratureReview, ResearchPlan


MULTI_AGENT_ASSIGNMENT_JSON = "02-agent-team.json"
MULTI_AGENT_ASSIGNMENT_MD = "02-agent-team.md"


AGENT_PROFILES: list[dict[str, str]] = [
    {
        "agent_id": "literature_scout",
        "name": "Literature Scout",
        "role": "检索与种子文献智能体",
        "responsibility": "补齐检索式、DOI/URL seed、综述/benchmark/baseline/recent 文献覆盖。",
    },
    {
        "agent_id": "evidence_curator",
        "name": "Evidence Curator",
        "role": "证据与引用智能体",
        "responsibility": "核对 citation key、metadata、全文 chunk、证据强度和引用可用性。",
    },
    {
        "agent_id": "gap_analyst",
        "name": "Gap Analyst",
        "role": "研究空白智能体",
        "responsibility": "把文献 gap、coverage 缺失和人工约束转成可检验研究问题。",
    },
    {
        "agent_id": "method_architect",
        "name": "Method Architect",
        "role": "方法设计智能体",
        "responsibility": "提出 candidate、机制假设、消融变量和最小可测方法差异。",
    },
    {
        "agent_id": "benchmark_engineer",
        "name": "Benchmark Engineer",
        "role": "Benchmark 智能体",
        "responsibility": "确认公开 benchmark/data、manifest、grader、baseline/ablation 命令和 release provenance。",
    },
    {
        "agent_id": "statistician",
        "name": "Statistician",
        "role": "统计设计智能体",
        "responsibility": "设计 repeats、主指标、置信区间、效应量、多重比较和负/中性结果边界。",
    },
    {
        "agent_id": "skeptical_reviewer",
        "name": "Skeptical Reviewer",
        "role": "批判复核智能体",
        "responsibility": "检查 novelty、claim boundary、失败模式和不能主张 superiority 的证据边界。",
    },
    {
        "agent_id": "manuscript_editor",
        "name": "Manuscript Editor",
        "role": "论文与交付智能体",
        "responsibility": "把证据、实验、限制、AI 披露和代码/数据可用性组织成可审稿文本。",
    },
]


def write_multi_agent_assignment_artifacts(
    topic: str,
    research_plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext | None,
    coverage_report: dict[str, Any] | None,
    evidence_mix_report: dict[str, Any] | None,
    research_gap_map: dict[str, Any] | None,
    review_constraints: dict[str, Any] | None,
    execution: ExecutionConfig,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_multi_agent_assignment(
        topic,
        research_plan,
        review,
        context,
        coverage_report,
        evidence_mix_report,
        research_gap_map,
        review_constraints,
        execution,
    )
    write_json(run_dir / MULTI_AGENT_ASSIGNMENT_JSON, report)
    write_text(run_dir / MULTI_AGENT_ASSIGNMENT_MD, render_multi_agent_assignment_markdown(report))
    return report


def build_multi_agent_assignment(
    topic: str,
    research_plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext | None,
    coverage_report: dict[str, Any] | None,
    evidence_mix_report: dict[str, Any] | None,
    research_gap_map: dict[str, Any] | None,
    review_constraints: dict[str, Any] | None,
    execution: ExecutionConfig,
) -> dict[str, Any]:
    coverage = coverage_report if isinstance(coverage_report, dict) else {}
    evidence_mix = evidence_mix_report if isinstance(evidence_mix_report, dict) else {}
    gap_map = research_gap_map if isinstance(research_gap_map, dict) else {}
    constraints = _constraints(review_constraints)
    tasks = _tasks(research_plan, review, context, coverage, evidence_mix, gap_map, constraints, execution)
    task_routes = _task_routes(research_plan, review, context, coverage, evidence_mix, gap_map, constraints, execution)
    active_agents = _unique([str(task["agent_id"]) for task in tasks if task.get("status") in {"active", "repair"}])
    status = "active" if len(active_agents) >= 4 else "needs_agent_coverage"
    return {
        "schema_version": 1,
        "topic": topic or research_plan.topic or review.topic,
        "domain": research_plan.domain,
        "status": status,
        "multi_agent_ready": status == "active",
        "team_profile": _team_profile(task_routes, execution),
        "agents": AGENT_PROFILES,
        "tasks": tasks,
        "task_routes": task_routes,
        "active_agents": active_agents,
        "handoffs": _handoffs(tasks),
        "routing_decisions": _routing_decisions(tasks),
        "ideation_constraints": _ideation_constraints(tasks),
        "agent_prompt_text": _agent_prompt_text(tasks),
        "recommended_actions": _recommended_actions(status, tasks),
    }


def render_multi_agent_assignment_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 多智能体任务分配：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 领域：{report.get('domain') or '-'}",
        f"- Multi-agent ready：{bool(report.get('multi_agent_ready'))}",
        f"- 活跃智能体：{', '.join(str(item) for item in report.get('active_agents', []) if str(item).strip()) or '-'}",
        "",
        "## Agent Profiles",
        "| Agent | 角色 | 职责 |",
        "| --- | --- | --- |",
    ]
    for agent in report.get("agents", []) if isinstance(report.get("agents"), list) else []:
        if not isinstance(agent, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(f"{agent.get('name') or ''} (`{agent.get('agent_id') or ''}`)"),
                    _cell(str(agent.get("role") or "")),
                    _cell(str(agent.get("responsibility") or "")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Task Routing", "| 任务 | Agent | 优先级 | 状态 | 关注点 | 输入 | 输出 | Handoff |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for task in report.get("tasks", []) if isinstance(report.get("tasks"), list) else []:
        if not isinstance(task, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(f"{task.get('task_id') or ''} {task.get('task') or ''}"),
                    _cell(str(task.get("agent_id") or "")),
                    _cell(str(task.get("priority") or "")),
                    _cell(str(task.get("status") or "")),
                    _cell(str(task.get("focus") or "")),
                    _cell(", ".join(str(item) for item in task.get("inputs", []) if str(item).strip()) or "-"),
                    _cell(", ".join(str(item) for item in task.get("outputs", []) if str(item).strip()) or "-"),
                    _cell(", ".join(str(item) for item in task.get("handoff_to", []) if str(item).strip()) or "-"),
                ]
            )
            + " |"
        )
    routes = report.get("task_routes") if isinstance(report.get("task_routes"), list) else []
    if routes:
        lines.extend(["", "## Task-Team Routing", "| Route | 状态 | Primary | Support | Trigger | Outputs |", "| --- | --- | --- | --- | --- | --- |"])
        for route in routes:
            if not isinstance(route, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(f"{route.get('route_id') or ''} {route.get('task_type') or ''}"),
                        _cell(str(route.get("status") or "")),
                        _cell(", ".join(str(item) for item in route.get("primary_agents", []) if str(item).strip()) or "-"),
                        _cell(", ".join(str(item) for item in route.get("support_agents", []) if str(item).strip()) or "-"),
                        _cell(str(route.get("trigger") or "")),
                        _cell(", ".join(str(item) for item in route.get("outputs", []) if str(item).strip()) or "-"),
                    ]
                )
                + " |"
            )
    for key, title in [("routing_decisions", "路由依据"), ("ideation_constraints", "Idea 约束"), ("recommended_actions", "建议动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend(["", f"## {title}"])
            lines.extend(f"- {item}" for item in values)
    return "\n".join(lines)


def multi_agent_prompt_context(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    tasks = report.get("tasks") if isinstance(report.get("tasks"), list) else []
    payload = []
    for task in tasks[:10]:
        if not isinstance(task, dict):
            continue
        payload.append(
            {
                "task_id": task.get("task_id"),
                "agent_id": task.get("agent_id"),
                "task": task.get("task"),
                "priority": task.get("priority"),
                "status": task.get("status"),
                "focus": task.get("focus"),
                "outputs": task.get("outputs"),
            }
        )
    routes = report.get("task_routes") if isinstance(report.get("task_routes"), list) else []
    for route in routes[:8]:
        if not isinstance(route, dict):
            continue
        payload.append(
            {
                "route_id": route.get("route_id"),
                "task_type": route.get("task_type"),
                "primary_agents": route.get("primary_agents"),
                "support_agents": route.get("support_agents"),
                "status": route.get("status"),
                "trigger": route.get("trigger"),
                "outputs": route.get("outputs"),
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def agent_roles_for_text(report: dict[str, Any] | None, text: str = "", limit: int = 4) -> list[str]:
    if not isinstance(report, dict):
        return []
    tasks = [task for task in report.get("tasks", []) if isinstance(task, dict)]
    if not tasks:
        return []
    query_terms = set(_terms(text))
    scored: list[tuple[int, str]] = []
    for task in tasks:
        task_text = " ".join(str(task.get(key) or "") for key in ["task", "focus", "rationale", "priority"])
        overlap = len(query_terms & set(_terms(task_text))) if query_terms else 0
        status_bonus = 2 if task.get("status") in {"active", "repair"} else 0
        priority_bonus = {"critical": 3, "high": 2, "medium": 1}.get(str(task.get("priority") or ""), 0)
        scored.append((overlap + status_bonus + priority_bonus, str(task.get("agent_id") or "")))
    roles: list[str] = []
    for _, agent_id in sorted(scored, key=lambda item: item[0], reverse=True):
        if agent_id and agent_id not in roles:
            roles.append(agent_id)
        if len(roles) >= limit:
            break
    return roles


def _tasks(
    plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext | None,
    coverage: dict[str, Any],
    evidence_mix: dict[str, Any],
    gap_map: dict[str, Any],
    constraints: list[dict[str, Any]],
    execution: ExecutionConfig,
) -> list[dict[str, Any]]:
    ready_gaps = [item for item in gap_map.get("gaps", []) if isinstance(item, dict) and item.get("testability") == "ready"]
    missing_coverage = coverage.get("missing_required") if isinstance(coverage.get("missing_required"), list) else []
    evidence_mix_status = str(evidence_mix.get("status") or "")
    benchmark_mode = execution.mode == "benchmark" or bool(execution.benchmark_manifest_paths)
    low_repeats = int(execution.repeats or 0) < 3
    context_chunks = len(context.chunks) if context is not None else 0
    tasks = [
        _task(
            "A01",
            "补齐检索与 seed 覆盖",
            "literature_scout",
            "high" if missing_coverage or evidence_mix_status in {"block", "needs_evidence_upgrade"} else "medium",
            "repair" if missing_coverage or evidence_mix_status == "block" else "active",
            _focus_from_missing(missing_coverage) or "围绕 review/survey、benchmark/dataset、baseline/method、recent work 补齐文献入口。",
            ["00-research-plan.json", "01-literature-coverage.json", "01-literature-evidence-mix.json"],
            ["extra_search_queries", "seed_papers", "01-literature-search-feedback.json"],
            ["evidence_curator", "gap_analyst"],
        ),
        _task(
            "A02",
            "核验证据与引用上下文",
            "evidence_curator",
            "high" if context_chunks < 3 else "medium",
            "repair" if context_chunks == 0 else "active",
            f"当前可用 chunks={context_chunks}；核对 citation key、DOI/URL、metadata 和全文 chunk。",
            ["01-context.json", "01-citation-audit.json", "01-literature-metadata-audit.json"],
            ["usable evidence chunks", "citation repair actions"],
            ["gap_analyst", "skeptical_reviewer"],
        ),
        _task(
            "A03",
            "形成可检验研究空白",
            "gap_analyst",
            "high" if ready_gaps else "medium",
            "active" if gap_map else "repair",
            _focus_from_gaps(ready_gaps) or "把 review.gaps、coverage 缺口和人工约束转成 testable gap。",
            ["01-literature-curated.json", "01-context.json", "02-research-gap-map.json"],
            ["gap_alignment", "hypothesis_seed", "experiment_hint"],
            ["method_architect", "benchmark_engineer", "statistician"],
        ),
        _task(
            "A04",
            "设计 candidate 与 ablation",
            "method_architect",
            "high" if ready_gaps else "medium",
            "active" if ready_gaps else "watch",
            "每个 idea 必须说明机制假设、candidate/baseline 差异和 ablation 变量。",
            ["02-research-gap-map.json", "02-ideas.json"],
            ["candidate design", "ablation variables", "experiment_sketch"],
            ["benchmark_engineer", "statistician", "skeptical_reviewer"],
        ),
        _task(
            "A05",
            "接入 benchmark 与 manifest",
            "benchmark_engineer",
            "critical" if benchmark_mode else "medium",
            "active" if benchmark_mode else "watch",
            _benchmark_focus(plan, execution),
            ["03-benchmark-plan.json", "03-benchmark-readiness.json", "benchmark manifests"],
            ["candidate/baseline/ablation manifests", "grader contract", "release provenance"],
            ["statistician", "skeptical_reviewer"],
        ),
        _task(
            "A06",
            "统计设计与负/中性结果边界",
            "statistician",
            "high" if low_repeats else "medium",
            "repair" if low_repeats else "active",
            f"execution.repeats={execution.repeats}；主指标={', '.join(plan.metrics[:4]) or 'missing'}。",
            ["03-preregistration.json", "04-statistics.json", "04-benchmark-evidence-audit.json"],
            ["planned comparisons", "CI/effect size", "claim boundary"],
            ["skeptical_reviewer", "manuscript_editor"],
        ),
        _task(
            "A07",
            "批判复核 novelty 与 claim",
            "skeptical_reviewer",
            "high",
            "active",
            "在 idea、结果和论文阶段持续阻断 unsupported superiority/stability/novelty claim。",
            ["02-novelty-audit.json", "04-claim-boundary-preflight.json", "10-claim-traceability.json"],
            ["blocked claims", "review constraints", "repair queue items"],
            ["manuscript_editor"],
        ),
        _task(
            "A08",
            "论文写作与交付证据",
            "manuscript_editor",
            "medium" if not constraints else "high",
            "active",
            _constraint_focus(constraints) or "把方法、结果、限制、AI 披露和代码/数据可用性写入 submission package。",
            ["06-paper.md", "09-revised-paper.md", "10-release-metadata.json", "11-submission-package.json"],
            ["human-handoff manuscript", "submission checklist", "release notes"],
            [],
        ),
    ]
    return tasks


def _task_routes(
    plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext | None,
    coverage: dict[str, Any],
    evidence_mix: dict[str, Any],
    gap_map: dict[str, Any],
    constraints: list[dict[str, Any]],
    execution: ExecutionConfig,
) -> list[dict[str, Any]]:
    missing_coverage = coverage.get("missing_required") if isinstance(coverage.get("missing_required"), list) else []
    evidence_mix_status = str(evidence_mix.get("status") or "")
    ready_gaps = [item for item in gap_map.get("gaps", []) if isinstance(item, dict) and item.get("testability") == "ready"]
    context_chunks = len(context.chunks) if context is not None else 0
    benchmark_mode = execution.mode == "benchmark" or bool(execution.benchmark_manifest_paths)
    low_repeats = int(execution.repeats or 0) < 3
    has_constraints = bool(constraints)
    routes = [
        _route(
            "R01",
            "literature_repair",
            ["literature_scout", "evidence_curator"],
            ["gap_analyst", "skeptical_reviewer"],
            "repair" if missing_coverage or evidence_mix_status in {"block", "needs_evidence_upgrade"} or context_chunks == 0 else "active",
            _focus_from_missing(missing_coverage) or f"evidence_mix={evidence_mix_status or '-'}; chunks={context_chunks}",
            ["01-literature-search-feedback.json", "01-literature-metadata-audit.json", "01-context.json"],
        ),
        _route(
            "R02",
            "gap_to_idea",
            ["gap_analyst", "method_architect"],
            ["evidence_curator", "benchmark_engineer", "statistician"],
            "active" if ready_gaps else "repair",
            _focus_from_gaps(ready_gaps) or f"review_gaps={len(review.gaps)}; domain={plan.domain or '-'}",
            ["02-research-gap-map.json", "02-ideas.json", "02-exploration-map.json"],
        ),
        _route(
            "R03",
            "benchmark_execution",
            ["benchmark_engineer", "statistician"],
            ["method_architect", "skeptical_reviewer"],
            "active" if benchmark_mode else "watch",
            _benchmark_focus(plan, execution),
            ["03-benchmark-readiness.json", "04-experiment-runbook.json", "04-benchmark-evidence-audit.json"],
        ),
        _route(
            "R04",
            "claim_boundary_review",
            ["skeptical_reviewer", "statistician"],
            ["evidence_curator", "benchmark_engineer", "manuscript_editor"],
            "repair" if low_repeats else "active",
            f"execution.repeats={execution.repeats}; constraints={len(constraints)}; benchmark_mode={benchmark_mode}",
            ["04-claim-boundary-preflight.json", "10-claim-consistency.json", "10-results-presentation.json"],
        ),
        _route(
            "R05",
            "paper_deliberation",
            ["skeptical_reviewer", "manuscript_editor"],
            _unique(["evidence_curator", "method_architect", "statistician", *([] if not benchmark_mode else ["benchmark_engineer"]), *([] if not has_constraints else ["gap_analyst"])]),
            "active",
            "final paper claims need independent evidence/statistics/reviewer/editor verdicts",
            ["10-agent-claim-audit.json", "10-agent-deliberation.json", "11-submission-package.json"],
        ),
        _route(
            "R06",
            "release_reproducibility",
            ["manuscript_editor", "benchmark_engineer" if benchmark_mode else "evidence_curator"],
            ["evidence_curator", "skeptical_reviewer"],
            "active" if benchmark_mode else "watch",
            "package code/data/release provenance and human handoff evidence",
            ["10-release-metadata.json", "10-code-data-availability.json", "14-final-handoff.json"],
        ),
    ]
    return routes


def _route(
    route_id: str,
    task_type: str,
    primary_agents: list[str],
    support_agents: list[str],
    status: str,
    trigger: str,
    outputs: list[str],
) -> dict[str, Any]:
    primary = _unique([agent for agent in primary_agents if agent])
    support = _unique([agent for agent in support_agents if agent and agent not in primary])
    return {
        "route_id": route_id,
        "task_type": task_type,
        "status": status,
        "primary_agents": primary,
        "support_agents": support,
        "all_agents": _unique([*primary, *support]),
        "trigger": trigger,
        "outputs": outputs,
        "handoff_to": support[:3],
    }


def _team_profile(routes: list[dict[str, Any]], execution: ExecutionConfig) -> dict[str, Any]:
    active_routes = [route for route in routes if route.get("status") in {"active", "repair"}]
    route_agents = _unique([agent for route in active_routes for agent in route.get("all_agents", []) if isinstance(route.get("all_agents"), list)])
    if execution.mode == "benchmark" or execution.benchmark_manifest_paths:
        profile = "benchmark_paper_grade"
    elif any(route.get("status") == "repair" for route in routes):
        profile = "repair_focused"
    else:
        profile = "standard_research"
    return {
        "profile": profile,
        "active_routes": len(active_routes),
        "routed_agents": route_agents,
        "route_count": len(routes),
    }


def _task(
    task_id: str,
    task: str,
    agent_id: str,
    priority: str,
    status: str,
    focus: str,
    inputs: list[str],
    outputs: list[str],
    handoff_to: list[str],
) -> dict[str, Any]:
    profile = _profile(agent_id)
    return {
        "task_id": task_id,
        "task": task,
        "agent_id": agent_id,
        "agent_name": profile.get("name", agent_id),
        "role": profile.get("role", ""),
        "priority": priority,
        "status": status,
        "focus": focus,
        "inputs": inputs,
        "outputs": outputs,
        "handoff_to": handoff_to,
        "rationale": f"{profile.get('role', agent_id)} 负责：{profile.get('responsibility', '')}",
    }


def _handoffs(tasks: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    known = {str(task.get("agent_id") or "") for task in tasks}
    for task in tasks:
        source = str(task.get("agent_id") or "")
        for target in task.get("handoff_to", []) if isinstance(task.get("handoff_to"), list) else []:
            target_id = str(target)
            if source and target_id in known:
                rows.append({"from": source, "to": target_id, "via": str(task.get("task_id") or "")})
    return rows


def _routing_decisions(tasks: list[dict[str, Any]]) -> list[str]:
    return [
        f"{task.get('task_id')}: {task.get('agent_id')} -> {task.get('priority')}/{task.get('status')}；{task.get('focus')}"
        for task in tasks
    ]


def _ideation_constraints(tasks: list[dict[str, Any]]) -> list[str]:
    active = [task for task in tasks if task.get("status") in {"active", "repair"}]
    return [
        "每个 idea 必须标注负责推进的 agent_roles，至少包含 method_architect 和一个 evidence/benchmark/statistics/reviewer 角色。",
        "实验草案必须体现 benchmark_engineer、statistician 或 skeptical_reviewer 的约束之一。",
        *[
            f"{task.get('agent_id')}: {task.get('focus')}"
            for task in active
            if task.get("agent_id") in {"literature_scout", "benchmark_engineer", "statistician", "skeptical_reviewer"}
        ],
    ]


def _agent_prompt_text(tasks: list[dict[str, Any]]) -> str:
    lines = ["多智能体分工："]
    for task in tasks:
        lines.append(f"- {task.get('agent_id')} ({task.get('priority')}/{task.get('status')}): {task.get('focus')}")
    return "\n".join(lines)


def _recommended_actions(status: str, tasks: list[dict[str, Any]]) -> list[str]:
    repair = [task for task in tasks if task.get("status") == "repair"]
    if repair:
        return [f"先处理 {task.get('agent_id')} 的 {task.get('task')}: {task.get('focus')}" for task in repair[:4]]
    if status != "active":
        return ["补齐至少 4 个活跃科研 agent，确保文献、证据、gap、方法、benchmark、统计和复核角色都有任务。"]
    return ["使用 02-agent-team.json 的 active agent_roles 约束 idea、实验计划和论文 claim。"]


def _profile(agent_id: str) -> dict[str, str]:
    for profile in AGENT_PROFILES:
        if profile["agent_id"] == agent_id:
            return profile
    return {}


def _focus_from_missing(missing: list[Any]) -> str:
    names = []
    for item in missing[:4]:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
    return "缺失 coverage facet：" + "；".join(names) if names else ""


def _focus_from_gaps(gaps: list[dict[str, Any]]) -> str:
    values = [str(item.get("gap") or "").strip() for item in gaps[:2] if str(item.get("gap") or "").strip()]
    return "Ready gap：" + "；".join(values) if values else ""


def _benchmark_focus(plan: ResearchPlan, execution: ExecutionConfig) -> str:
    if execution.benchmark_manifest_paths:
        return f"校验 {len(execution.benchmark_manifest_paths)} 个 benchmark manifest 覆盖 candidate/baseline/ablation。"
    if execution.mode == "benchmark":
        return "benchmark 模式必须配置 candidate/baseline/ablation manifest、公开 data URL、grader hash 和 release provenance。"
    return "若要论文级结论，把模拟/本地实验迁移到公开 benchmark manifest。"


def _constraint_focus(constraints: list[dict[str, Any]]) -> str:
    values = [str(item.get("text") or "").strip() for item in constraints[:3] if str(item.get("text") or "").strip()]
    return "落实人工约束：" + "；".join(values) if values else ""


def _constraints(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    values = report.get("constraints") if isinstance(report, dict) else None
    if not isinstance(values, list):
        return []
    return [dict(item) for item in values if isinstance(item, dict)]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9*+-]{1,}|[\u4e00-\u9fff]{2,}", str(text or "").lower())


