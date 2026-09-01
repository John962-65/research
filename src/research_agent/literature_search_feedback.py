from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .config import LiteratureConfig
from .models import LiteratureQualityReport, LiteratureReview, ResearchPlan


LITERATURE_SEARCH_FEEDBACK_JSON = "01-literature-search-feedback.json"
LITERATURE_SEARCH_FEEDBACK_MD = "01-literature-search-feedback.md"


def write_literature_search_feedback_artifacts(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    snowball_report: dict[str, Any],
    coverage_report: dict[str, Any],
    rescue_report: dict[str, Any],
    source_health_report: dict[str, Any],
    config: LiteratureConfig,
    run_dir: Path,
    seed_intake_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    evidence_mix_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_literature_search_feedback(
        research_plan,
        raw_review,
        curated_review,
        quality_report,
        snowball_report,
        coverage_report,
        rescue_report,
        source_health_report,
        config,
        seed_intake_report=seed_intake_report,
        rerank_report=rerank_report,
        evidence_mix_report=evidence_mix_report,
        query_execution_report=query_execution_report,
    )
    write_json(run_dir / LITERATURE_SEARCH_FEEDBACK_JSON, report)
    write_text(run_dir / LITERATURE_SEARCH_FEEDBACK_MD, render_literature_search_feedback_markdown(report))
    return report


def build_literature_search_feedback(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    snowball_report: dict[str, Any],
    coverage_report: dict[str, Any],
    rescue_report: dict[str, Any],
    source_health_report: dict[str, Any],
    config: LiteratureConfig,
    seed_intake_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    evidence_mix_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = _quality_data(quality_report)
    source_actions = _source_actions(source_health_report, rescue_report)
    query_execution = query_execution_report if isinstance(query_execution_report, dict) else {}
    missing_roles = _missing_evidence_roles(quality)
    recommended_queries = _recommended_queries(research_plan, raw_review, quality, snowball_report, coverage_report, rescue_report, query_execution)
    seed_intake = seed_intake_report if isinstance(seed_intake_report, dict) else {}
    seed_targets = _seed_targets(research_plan, coverage_report, quality, curated_review, seed_intake)
    status = _status(quality, coverage_report, rescue_report, source_actions, recommended_queries, seed_intake, query_execution)
    rerank = rerank_report if isinstance(rerank_report, dict) else {}
    evidence_mix = evidence_mix_report if isinstance(evidence_mix_report, dict) else {}
    repair_tasks = _retrieval_repair_tasks(
        research_plan,
        recommended_queries,
        seed_targets,
        source_actions,
        coverage_report,
        rescue_report,
        seed_intake,
        rerank,
        evidence_mix,
        query_execution,
        quality,
    )
    return {
        "schema_version": 1,
        "topic": research_plan.topic or raw_review.topic,
        "domain": research_plan.domain,
        "status": status,
        "diagnosis": {
            "raw_papers": len(raw_review.papers),
            "selected_papers": len(curated_review.papers),
            "quality_confidence": quality.get("confidence_status") or "",
            "quality_score": quality.get("confidence_score", 0.0),
            "coverage_status": coverage_report.get("status") or "",
            "coverage_ratio": coverage_report.get("coverage_ratio", 0.0),
            "rescue_status": rescue_report.get("status") or "",
            "rate_limited_sources": source_health_report.get("rate_limited_sources", 0),
            "failed_sources": source_health_report.get("failed_sources", 0),
            "seed_intake_status": seed_intake.get("status") or "",
            "seed_role_coverage_status": seed_intake.get("role_coverage_status") or "",
            "seed_entries": seed_intake.get("total_seed_entries", 0),
            "curated_seed_papers": seed_intake.get("curated_seed_papers", 0),
            "rerank_status": rerank.get("status") or "",
            "rerank_warnings": len(rerank.get("warnings", []) if isinstance(rerank.get("warnings"), list) else []),
            "evidence_mix_status": evidence_mix.get("status") or "",
            "evidence_mix_score": evidence_mix.get("mix_score", 0.0),
            "query_execution_status": query_execution.get("status") or "",
            "query_execution_selected": query_execution.get("selected_query_count", 0),
            "query_execution_repair_queries": len(_query_execution_repair_queries(research_plan, query_execution)),
            "missing_evidence_roles": len(missing_roles),
        },
        "source_actions": source_actions,
        "recommended_queries": recommended_queries,
        "seed_paper_targets": seed_targets,
        "retrieval_repair_tasks": repair_tasks,
        "next_run_config": {
            "literature_provider": "online" if config.provider == "offline" else config.provider,
            "sources": _recommended_sources(config.sources, source_actions),
            "max_papers": max(int(config.max_papers or 0), 12),
            "max_search_queries": max(int(config.max_search_queries or 0), 6),
            "seed_papers_min": _seed_papers_min(seed_targets, missing_roles),
        },
        "approval_guidance": _approval_guidance(status),
    }


def render_literature_search_feedback_markdown(report: dict[str, Any]) -> str:
    diagnosis = report.get("diagnosis") if isinstance(report.get("diagnosis"), dict) else {}
    config = report.get("next_run_config") if isinstance(report.get("next_run_config"), dict) else {}
    lines = [
        f"# 文献检索反馈策略：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 领域：{report.get('domain') or '-'}",
        f"- 原始/筛选文献：{diagnosis.get('raw_papers', 0)}/{diagnosis.get('selected_papers', 0)}",
        f"- 证据置信度：{diagnosis.get('quality_confidence') or '-'} ({diagnosis.get('quality_score') or 0})",
        f"- 覆盖：{diagnosis.get('coverage_status') or '-'} ({diagnosis.get('coverage_ratio') or 0})",
        f"- Rescue：{diagnosis.get('rescue_status') or '-'}",
        f"- Seed intake：{diagnosis.get('seed_intake_status') or '-'} ({diagnosis.get('curated_seed_papers', 0)}/{diagnosis.get('seed_entries', 0)})；角色覆盖：{diagnosis.get('seed_role_coverage_status') or '-'}",
        "",
        "## 下次运行配置",
        f"- literature_provider：`{config.get('literature_provider') or '-'}`",
        f"- sources：`{', '.join(config.get('sources') or []) or '-'}`",
        f"- max_papers：`{config.get('max_papers') or '-'}`",
        f"- max_search_queries：`{config.get('max_search_queries') or '-'}`",
        f"- seed_papers_min：`{config.get('seed_papers_min') or '-'}`",
        "",
    ]
    for key, title in [("source_actions", "文献源动作"), ("approval_guidance", "批准前指导")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(["## 推荐检索式", "| 优先级 | 来源 | 检索式 | 理由 |", "| ---: | --- | --- | --- |"])
    queries = report.get("recommended_queries") if isinstance(report.get("recommended_queries"), list) else []
    if not queries:
        lines.append("| - | - | 无 | - |")
    for item in queries:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("priority") or ""),
                        _cell(str(item.get("source") or "")),
                        "`" + _cell(str(item.get("query") or "")) + "`",
                        _cell(str(item.get("rationale") or "")),
                    ]
                )
                + " |"
            )
    seed_targets = report.get("seed_paper_targets") if isinstance(report.get("seed_paper_targets"), list) else []
    lines.extend(["", "## 人工 seed paper 目标", "| 类别 | 名称 | 建议 |", "| --- | --- | --- |"])
    if not seed_targets:
        lines.append("| - | - | 暂无 |")
    for item in seed_targets:
        if isinstance(item, dict):
            lines.append("| " + " | ".join([_cell(str(item.get("category") or "")), _cell(str(item.get("name") or "")), _cell(str(item.get("hint") or ""))]) + " |")
    tasks = report.get("retrieval_repair_tasks") if isinstance(report.get("retrieval_repair_tasks"), list) else []
    lines.extend(["", "## 检索修复任务", "| 优先级 | 类别 | Owner | 动作 | Query/Seed | 依据 |", "| ---: | --- | --- | --- | --- | --- |"])
    if not tasks:
        lines.append("| - | - | - | 暂无 | - | - |")
    for item in tasks:
        if isinstance(item, dict):
            query_or_seed = str(item.get("query") or item.get("seed_target") or "-")
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("priority") or ""),
                        _cell(str(item.get("category") or "")),
                        _cell(str(item.get("owner") or "")),
                        _cell(str(item.get("action") or "")),
                        "`" + _cell(query_or_seed) + "`" if query_or_seed != "-" else "-",
                        _cell(str(item.get("rationale") or "")),
                    ]
                )
                + " |"
    )
    return "\n".join(lines)


def _retrieval_repair_tasks(
    plan: ResearchPlan,
    recommended_queries: list[dict[str, Any]],
    seed_targets: list[dict[str, str]],
    source_actions: list[str],
    coverage_report: dict[str, Any],
    rescue_report: dict[str, Any],
    seed_intake: dict[str, Any],
    rerank_report: dict[str, Any],
    evidence_mix_report: dict[str, Any],
    query_execution_report: dict[str, Any],
    quality: dict[str, Any],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for action in source_actions:
        if "暂无结构化故障" in action:
            continue
        tasks.append(
            _task(
                "source_repair",
                100,
                "human",
                action,
                "修复文献源后再补检索，避免低质量候选继续污染排序。",
                source="01-literature-source-health.md",
                artifacts=["01-literature-source-health.md", "01-literature-rescue-plan.md"],
            )
        )
    for query in recommended_queries[:8]:
        text = str(query.get("query") or "").strip()
        if not text:
            continue
        tasks.append(
            _task(
                "query_repair",
                int(query.get("priority") or 80),
                "agent",
                "执行补检索式并合并去重候选。",
                str(query.get("rationale") or query.get("source") or "补检索候选池。"),
                query=text,
                source=str(query.get("source") or "search_feedback"),
                artifacts=["01-literature.json", "01-literature-rerank.md", "01-literature-quality.md"],
            )
        )
    for target in seed_targets[:6]:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        tasks.append(
            _task(
                "seed_repair",
                94 if str(seed_intake.get("status") or "") in {"block", "review_required"} else 88,
                "human",
                "补充或修复人工 seed_papers DOI/URL。",
                str(target.get("hint") or "补核心 seed paper。"),
                seed_target=name,
                source=str(target.get("category") or "seed_target"),
                artifacts=["01-seed-paper-intake.md", "01-literature-curated.md", "01-review-gate.md"],
            )
        )
    for task in _rerank_tasks(plan, rerank_report):
        tasks.append(task)
    for task in _evidence_mix_tasks(evidence_mix_report):
        tasks.append(task)
    for task in _query_execution_tasks(plan, query_execution_report):
        tasks.append(task)
    for task in _evidence_role_tasks(plan, quality):
        tasks.append(task)
    if str(coverage_report.get("status") or "") in {"block", "needs_literature", "needs_coverage"}:
        tasks.append(
            _task(
                "coverage_repair",
                92,
                "agent+human",
                "补齐 coverage 缺失 facet 并重跑文献 gate。",
                "01-literature-coverage 显示 baseline/benchmark/metric 覆盖不足。",
                source="01-literature-coverage.md",
                artifacts=["01-literature-coverage.md", "01-literature-search-feedback.md", "01-review-gate.md"],
            )
        )
    if str(rescue_report.get("status") or "") in {"block", "needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        tasks.append(
            _task(
                "gate_hold",
                90,
                "human",
                "暂停批准进入 idea/实验，先关闭文献修复任务。",
                f"literature_rescue_status={rescue_report.get('status') or '-'}",
                source="01-literature-rescue-plan.md",
                artifacts=["01-review-gate.md", "approval.json"],
            )
        )
    return _dedupe_tasks(tasks)[:20]


def _rerank_tasks(plan: ResearchPlan, rerank_report: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    warnings = [str(item) for item in rerank_report.get("warnings", [])] if isinstance(rerank_report.get("warnings"), list) else []
    if any("标题过泛" in item or "对象不匹配" in item for item in warnings):
        tasks.append(
            _task(
                "rerank_repair",
                86,
                "human",
                "补核心对象/方法/benchmark 的精确标题或 DOI seed。",
                "rerank top 候选仍有标题过泛或对象不匹配问题。",
                seed_target=plan.topic,
                source="01-literature-rerank.md",
                artifacts=["01-literature-rerank.md", "01-seed-paper-intake.md"],
            )
        )
    if any("venue/source" in item for item in warnings):
        tasks.append(
            _task(
                "rerank_repair",
                84,
                "human",
                "人工核验弱 venue/source 候选，必要时从 curated context 移除。",
                "rerank top 候选仍包含来源可靠性较弱的题录。",
                source="01-literature-rerank.md",
                artifacts=["01-literature-rerank.md", "01-literature-curated.md"],
            )
        )
    if any("Crossref" in item for item in warnings):
        tasks.append(
            _task(
                "rerank_repair",
                82,
                "agent",
                "用 OpenAlex/Semantic Scholar/arXiv 结果替换单源 Crossref 薄摘要题录。",
                "单源 Crossref 且摘要过薄的题录会降低后续 RAG 质量。",
                query=f"{plan.topic} benchmark baseline DOI",
                source="01-literature-rerank.md",
                artifacts=["01-literature-rerank.md", "01-literature-quality.md"],
            )
        )
    for item in rerank_report.get("items", []) if isinstance(rerank_report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        penalties = item.get("penalties") if isinstance(item.get("penalties"), list) else []
        if not any(str(value) in {"generic title/object mismatch", "weak venue/source signal", "single Crossref source with thin abstract"} for value in penalties):
            continue
        tasks.append(
            _task(
                "rerank_candidate_review",
                76,
                "human",
                "复核或替换低可信 top candidate。",
                str(item.get("title") or "rerank candidate"),
                source="01-literature-rerank.md",
                artifacts=["01-literature-rerank.md", "01-literature-curated.md"],
            )
        )
        if len(tasks) >= 5:
            break
    return tasks


def _evidence_mix_tasks(report: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    status = str(report.get("status") or "")
    if status not in {"block", "needs_evidence_upgrade", "review_required"}:
        return tasks
    for item in report.get("anchor_checks", []) if isinstance(report.get("anchor_checks"), list) else []:
        if not isinstance(item, dict) or str(item.get("status") or "") == "pass":
            continue
        name = str(item.get("name") or "missing_anchor")
        tasks.append(
            _task(
                "evidence_anchor_repair",
                91 if item.get("required") else 78,
                "agent+human",
                "补齐文献证据组合缺失 anchor。",
                str(item.get("action") or name),
                query=" ".join(str(value) for value in item.get("matched_terms", [])[:4] if str(value).strip()),
                seed_target=name,
                source="01-literature-evidence-mix.md",
                artifacts=["01-literature-evidence-mix.md", "01-literature-curated.md", "01-review-gate.md"],
            )
        )
    return tasks


def _query_execution_tasks(plan: ResearchPlan, report: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    status = str(report.get("status") or "")
    if status not in {"needs_source_repair", "needs_query_repair", "review_required"}:
        return tasks
    for item in report.get("queries", []) if isinstance(report.get("queries"), list) else []:
        if not isinstance(item, dict):
            continue
        row_status = str(item.get("status") or "")
        if row_status not in {"no_source_results", "no_candidate_hits", "weak_candidate_hits", "no_execution_trace"}:
            continue
        query = _repair_query_from_execution_row(plan, item)
        priority = 96 if row_status in {"no_source_results", "no_candidate_hits"} else 88
        tasks.append(
            _task(
                "query_execution_repair",
                priority,
                "agent" if row_status != "no_source_results" else "agent+human",
                "执行 query execution audit 指出的补检索式，并确认该 query 有高质量命中。",
                f"selected query `{item.get('query') or ''}` 未闭环：{row_status}。",
                query=query,
                source="01-query-execution-audit.md",
                artifacts=["01-query-execution-audit.md", "01-literature-search-feedback.md", "01-literature-quality.md"],
            )
        )
    return tasks[:6]



def _task(
    category: str,
    priority: int,
    owner: str,
    action: str,
    rationale: str,
    *,
    query: str = "",
    seed_target: str = "",
    source: str = "",
    artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": "",
        "category": category,
        "priority": priority,
        "owner": owner,
        "action": action,
        "query": " ".join(query.split()),
        "seed_target": " ".join(seed_target.split()),
        "source": source,
        "artifacts": artifacts or [],
        "rationale": rationale,
    }


def _recommended_queries(
    plan: ResearchPlan,
    raw_review: LiteratureReview,
    quality: dict[str, Any],
    snowball_report: dict[str, Any],
    coverage_report: dict[str, Any],
    rescue_report: dict[str, Any],
    query_execution_report: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_evidence_role_queries(plan, quality))
    for item in rescue_report.get("rescue_queries", []) if isinstance(rescue_report.get("rescue_queries"), list) else []:
        if isinstance(item, dict) and str(item.get("query") or "").strip():
            rows.append(_query(str(item.get("query")), int(item.get("priority") or 80), f"rescue:{item.get('kind') or '-'}", str(item.get("rationale") or "")))
    for item in snowball_report.get("expansion_queries", []) if isinstance(snowball_report.get("expansion_queries"), list) else []:
        if isinstance(item, dict) and str(item.get("query") or "").strip():
            rows.append(_query(str(item.get("query")), int(item.get("priority") or 70), "snowball", str(item.get("purpose") or "")))
    for item in coverage_report.get("missing_required", []) if isinstance(coverage_report.get("missing_required"), list) else []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            suggested = [str(query).strip() for query in item.get("suggested_queries", [])] if isinstance(item.get("suggested_queries"), list) else []
            for query in suggested[:3]:
                if query:
                    rows.append(_query(query, 94, "missing_facet_suggested", f"补缺失 facet: {name or query}"))
            if name:
                rows.append(_query(_fallback_missing_facet_query(plan, raw_review, name), 90, "missing_facet_exact", f"补缺失 facet: {name}"))
    selected = raw_review.search_strategy.get("selected_queries") if isinstance(raw_review.search_strategy, dict) else []
    for query in selected if isinstance(selected, list) else []:
        rows.append(_query(str(query), 60, "previous_selected", "保留上一轮已选检索式作为对照。"))
    rows.extend(_query_execution_repair_queries(plan, query_execution_report))
    return _dedupe_queries(rows)[:16]


def _query_execution_repair_queries(plan: ResearchPlan, report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if str(report.get("status") or "") not in {"needs_query_repair", "review_required", "needs_source_repair"}:
        return rows
    for item in report.get("queries", []) if isinstance(report.get("queries"), list) else []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {"no_source_results", "no_candidate_hits", "weak_candidate_hits", "no_execution_trace"}:
            continue
        query = _repair_query_from_execution_row(plan, item)
        priority = 96 if status in {"no_source_results", "no_candidate_hits"} else 90
        rows.append(_query(query, priority, "query_execution", f"selected query 未闭环：{status}"))
    return rows


def _repair_query_from_execution_row(plan: ResearchPlan, item: dict[str, Any]) -> str:
    query = str(item.get("query") or "").strip()
    intent = str(item.get("intent") or "").strip()
    if intent == "benchmark":
        suffix = "benchmark dataset evaluation DOI"
    elif intent == "baseline":
        suffix = "baseline method comparison DOI"
    elif intent == "survey":
        suffix = "survey review systematic review DOI"
    else:
        suffix = "method benchmark baseline DOI"
    base = query or next((str(value).strip() for value in plan.search_queries if str(value).strip()), "") or plan.topic
    return f"{base} {suffix}".strip()


def _fallback_missing_facet_query(plan: ResearchPlan, raw_review: LiteratureReview, name: str) -> str:
    base = next((str(query).strip() for query in plan.search_queries if str(query).strip()), "")
    topic = base or raw_review.topic or plan.topic
    return f'"{name}" {topic}'.strip()


def _evidence_role_tasks(plan: ResearchPlan, quality: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for query in _evidence_role_queries(plan, quality):
        role = str(query.get("role") or "").strip()
        tasks.append(
            _task(
                "evidence_role_repair",
                int(query.get("priority") or 92),
                "agent+human",
                "补齐文献质量报告缺失的核心证据角色，并重跑文献 gate。",
                _role_hint(role) or str(query.get("rationale") or "证据角色覆盖不足。"),
                query=str(query.get("query") or ""),
                seed_target=_role_label(role),
                source="01-literature-quality.md",
                artifacts=["01-literature-quality.md", "01-literature-search-feedback.md", "01-review-gate.md"],
            )
        )
    return tasks


def _evidence_role_queries(plan: ResearchPlan, quality: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role in _missing_evidence_roles(quality):
        spec = _role_query_spec(plan, role)
        if spec:
            rows.append({**_query(spec["query"], int(spec["priority"]), "missing_evidence_role", spec["rationale"]), "role": role})
    return rows


def _role_query_spec(plan: ResearchPlan, role: str) -> dict[str, str | int]:
    topic = plan.topic or next((str(query).strip() for query in plan.search_queries if str(query).strip()), "") or plan.domain or "research topic"
    specs: dict[str, tuple[str, int, str]] = {
        "review_survey": (f'"{topic}" survey review state of the art DOI', 99, "缺少综述/领域入口证据。"),
        "benchmark_dataset": (f'"{topic}" benchmark dataset evaluation protocol DOI', 98, "缺少 benchmark/dataset/evaluation protocol 证据。"),
        "baseline_method": (f'"{topic}" baseline method comparison DOI', 97, "缺少 baseline/method comparison 证据。"),
        "recent_work": (f'"{topic}" recent 2022 2023 2024 2025 DOI', 90, "缺少近期工作证据。"),
    }
    query, priority, rationale = specs.get(role, ("", 0, ""))
    return {"query": query, "priority": priority, "rationale": rationale} if query else {}


def _missing_evidence_roles(quality: dict[str, Any]) -> list[str]:
    roles = quality.get("missing_evidence_roles") if isinstance(quality.get("missing_evidence_roles"), list) else []
    return _dedupe([str(role).strip() for role in roles if str(role).strip()])


def _role_label(role: str) -> str:
    labels = {
        "review_survey": "review/survey evidence",
        "benchmark_dataset": "benchmark/dataset evidence",
        "baseline_method": "baseline/method evidence",
        "recent_work": "recent work evidence",
    }
    return labels.get(role, role or "evidence role")


def _role_hint(role: str) -> str:
    hints = {
        "review_survey": "补 1 篇高相关综述或 state-of-the-art 论文 DOI/URL，先校准问题边界和常用 baseline。",
        "benchmark_dataset": "补 1 篇公开 benchmark、dataset、testbed 或 evaluation protocol 论文 DOI/URL。",
        "baseline_method": "补 1 篇经典 baseline 或方法对比论文 DOI/URL，确保后续 idea 能和强基线比较。",
        "recent_work": "补 1 篇 2022 年以来的高相关近期工作 DOI/URL，避免只依赖过旧证据。",
    }
    return hints.get(role, "")


def _seed_targets(
    plan: ResearchPlan,
    coverage_report: dict[str, Any],
    quality: dict[str, Any],
    curated_review: LiteratureReview,
    seed_intake: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in coverage_report.get("missing_required", []) if isinstance(coverage_report.get("missing_required"), list) else []:
        if isinstance(item, dict):
            category = str(item.get("category") or "facet")
            name = str(item.get("name") or "").strip()
            if name:
                rows.append({"category": category, "name": name, "hint": f"提供 1 篇覆盖 {name} 的 DOI/URL，优先综述、benchmark 或经典 baseline。"})
    confidence = str(quality.get("confidence_status") or "")
    for role in _missing_evidence_roles(quality):
        rows.append({"category": "evidence_role", "name": _role_label(role), "hint": _role_hint(role) or "补齐缺失证据角色的 DOI/URL。"})
    if confidence in {"weak", "block"} or len(curated_review.papers) < 5:
        rows.append({"category": "core_evidence", "name": plan.domain or "topic", "hint": "补 3-5 篇高相关核心论文 DOI/URL；至少包含综述、benchmark 和 baseline。"})
    if str(seed_intake.get("status") or "") in {"block", "review_required"} or str(seed_intake.get("role_coverage_status") or "") == "review_required":
        rows.append({"category": "seed_intake", "name": "manual seed_papers", "hint": "修复 01-seed-paper-intake.md 中未进入 curated context、缺 DOI/URL 或相关性弱的 seed。"})
    return _dedupe_targets(rows)[:10]


def _source_actions(source_health: dict[str, Any], rescue_report: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    actions.extend(str(item) for item in rescue_report.get("source_repairs", []) if str(item).strip()) if isinstance(rescue_report.get("source_repairs"), list) else None
    if int(source_health.get("rate_limited_sources") or 0):
        actions.append("存在限流来源：设置相应 API key、降低请求频率或保留多源兜底后重跑。")
    if int(source_health.get("failed_sources") or 0):
        actions.append("存在失败来源：查看 01-literature-source-health.md，修复网络/API 配置或临时移除失败 source。")
    if not actions:
        actions.append("文献源暂无结构化故障；重点补 query 和 seed paper。")
    return _dedupe(actions)


def _recommended_sources(sources: list[str], source_actions: list[str]) -> list[str]:
    values = [source.strip().lower() for source in sources if source.strip()]
    for source in ["openalex", "arxiv", "crossref"]:
        if source not in values:
            values.append(source)
    if any("SEMANTIC_SCHOLAR_API_KEY" in item for item in source_actions) and "semantic_scholar" in values:
        return values
    if not values:
        return ["openalex", "arxiv", "crossref"]
    return values


def _approval_guidance(status: str) -> list[str]:
    if status in {"needs_source_repair", "needs_search_revision", "needs_manual_seed"}:
        return [
            "不要直接批准进入 idea/实验；先按本反馈策略补检索或补 seed_papers。",
            "重新生成 01-literature-quality、01-literature-coverage、01-citation-audit 和 01-review-gate 后再人工确认。",
        ]
    return ["打开 01-review-gate.md、01-literature-quality.md 和 01-citation-audit.md 抽查核心文献后再批准。"]


def _status(
    quality: dict[str, Any],
    coverage_report: dict[str, Any],
    rescue_report: dict[str, Any],
    source_actions: list[str],
    recommended_queries: list[dict[str, Any]],
    seed_intake: dict[str, Any],
    query_execution_report: dict[str, Any],
) -> str:
    rescue_status = str(rescue_report.get("status") or "")
    coverage_status = str(coverage_report.get("status") or "")
    confidence = str(quality.get("confidence_status") or "")
    seed_status = str(seed_intake.get("status") or "")
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    query_execution_status = str(query_execution_report.get("status") or "")
    if seed_status in {"block", "review_required"} or seed_role_status == "review_required":
        return "needs_manual_seed"
    if rescue_status in {"needs_source_repair", "block"} or query_execution_status == "needs_source_repair":
        return "needs_source_repair"
    if query_execution_status == "needs_query_repair" or coverage_status in {"block", "needs_literature", "needs_coverage"} or rescue_status == "needs_rescue_search" or confidence in {"weak", "block"}:
        return "needs_search_revision"
    if rescue_status == "needs_manual_seed":
        return "needs_manual_seed"
    if recommended_queries:
        return "ready_for_review"
    return "pass"


def _quality_data(report: LiteratureQualityReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    return {
        "confidence_status": report.confidence_status,
        "confidence_score": report.confidence_score,
        "selected_papers": report.selected_papers,
        "warnings": report.warnings,
        "role_coverage": report.role_coverage,
        "missing_evidence_roles": report.missing_evidence_roles,
    }


def _seed_papers_min(seed_targets: list[dict[str, str]], missing_roles: list[str]) -> int:
    base = max(3, min(5, len(seed_targets) or 3))
    if missing_roles:
        return min(6, max(base, len(missing_roles) + 3))
    return base


def _query(query: str, priority: int, source: str, rationale: str) -> dict[str, Any]:
    return {"query": " ".join(str(query).split()), "priority": priority, "source": source, "rationale": rationale}


def _dedupe_queries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: int(item.get("priority") or 0), reverse=True):
        query = str(row.get("query") or "").strip()
        key = query.lower()
        if query and key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _dedupe_targets(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.get("category", ""), row.get("name", "").lower())
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _dedupe_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in sorted(rows, key=lambda item: int(item.get("priority") or 0), reverse=True):
        key = (
            str(row.get("category") or ""),
            str(row.get("action") or ""),
            str(row.get("query") or ""),
            str(row.get("seed_target") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        item = dict(row)
        item["task_id"] = f"retrieval-repair-{len(result) + 1:03d}"
        result.append(item)
    return result


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
