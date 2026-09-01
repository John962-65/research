from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text, cell as _cell
from .models import LiteratureQualityReport, LiteratureReview, ResearchPlan


LITERATURE_RESCUE_PLAN_JSON = "01-literature-rescue-plan.json"
LITERATURE_RESCUE_PLAN_MD = "01-literature-rescue-plan.md"


def write_literature_rescue_plan_artifacts(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    snowball_report: dict[str, Any],
    coverage_report: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_rescue_plan(
        research_plan,
        raw_review,
        curated_review,
        quality_report,
        snowball_report,
        coverage_report,
    )
    write_json(run_dir / LITERATURE_RESCUE_PLAN_JSON, report)
    write_text(run_dir / LITERATURE_RESCUE_PLAN_MD, render_literature_rescue_plan_markdown(report))
    return report


def build_literature_rescue_plan(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    snowball_report: dict[str, Any],
    coverage_report: dict[str, Any],
) -> dict[str, Any]:
    quality = _quality_data(quality_report)
    selected_papers = _safe_int(quality.get("selected_papers"), len(curated_review.papers))
    quality_warnings = _as_list(quality.get("warnings"))
    coverage_status = str(coverage_report.get("status") or "")
    coverage_ratio = _safe_float(coverage_report.get("coverage_ratio"))
    missing_required = _as_list(coverage_report.get("missing_required"))
    missing_roles = [str(item) for item in _as_list(quality.get("missing_evidence_roles")) if str(item).strip()]
    source_repairs = _source_repairs(raw_review)
    source_repair_severity = _source_repair_severity(raw_review, source_repairs)
    weak_reasons = _weak_reasons(raw_review, curated_review, selected_papers, quality_warnings, coverage_status, missing_required, missing_roles, source_repairs)
    rescue_queries = _rescue_queries(research_plan, raw_review, snowball_report, coverage_report, missing_roles)
    required_actions = _required_actions(weak_reasons, rescue_queries, source_repairs)
    status = _status(weak_reasons, coverage_status, source_repairs, source_repair_severity, selected_papers, rescue_queries)
    return {
        "schema_version": 1,
        "topic": research_plan.topic or raw_review.topic,
        "domain": research_plan.domain,
        "status": status,
        "raw_papers": len(raw_review.papers),
        "selected_papers": len(curated_review.papers),
        "quality_selected_papers": selected_papers,
        "coverage_status": coverage_status,
        "coverage_ratio": coverage_ratio,
        "missing_evidence_roles": missing_roles,
        "weak_reasons": weak_reasons,
        "source_repairs": source_repairs,
        "source_repair_severity": source_repair_severity,
        "rescue_queries": rescue_queries,
        "required_actions": required_actions,
        "next_run_config_hints": _config_hints(source_repairs),
    }


def render_literature_rescue_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 文献补检索计划：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 原始候选：{report.get('raw_papers', 0)}",
        f"- 筛选保留：{report.get('selected_papers', 0)}",
        f"- 覆盖状态：{report.get('coverage_status') or '-'}",
        f"- 覆盖率：{float(report.get('coverage_ratio') or 0):.1%}",
        "",
    ]
    for key, title in [("weak_reasons", "文献薄弱原因"), ("source_repairs", "文献源修复"), ("required_actions", "下一轮动作")]:
        values = _as_list(report.get(key))
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(
        [
            "## 补检索式",
            "| 优先级 | 类别 | 检索式 | 依据 |",
            "| ---: | --- | --- | --- |",
        ]
    )
    queries = _as_list(report.get("rescue_queries"))
    if not queries:
        lines.append("|  |  | 无 |  |")
    for item in queries:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("priority") or ""),
                        _cell(str(item.get("kind") or "")),
                        "`" + _cell(str(item.get("query") or "")) + "`",
                        _cell(str(item.get("rationale") or "")),
                    ]
                )
                + " |"
            )
    hints = _as_list(report.get("next_run_config_hints"))
    if hints:
        lines.extend(["", "## 下次运行配置提示"])
        lines.extend(f"- {item}" for item in hints)
    return "\n".join(lines)


def _weak_reasons(
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    selected_papers: int,
    quality_warnings: list[Any],
    coverage_status: str,
    missing_required: list[Any],
    missing_roles: list[str],
    source_repairs: list[str],
) -> list[str]:
    reasons: list[str] = []
    if len(raw_review.papers) < 8:
        reasons.append(f"原始候选只有 {len(raw_review.papers)} 篇，召回不足。")
    if selected_papers < 5 or len(curated_review.papers) < 5:
        reasons.append(f"质量筛选后仅保留 {len(curated_review.papers)} 篇，进入 RAG/idea 的证据池偏小。")
    if coverage_status in {"block", "needs_literature", "needs_coverage"}:
        reasons.append("baseline/benchmark 覆盖不足：" + "；".join(_missing_names(missing_required)[:6]))
    if missing_roles:
        reasons.append("证据角色覆盖不足，缺失：" + "；".join(missing_roles[:4]))
    if quality_warnings:
        reasons.extend(str(item) for item in quality_warnings[:4])
    if source_repairs:
        reasons.append("至少一个在线文献源需要修复，当前结果可能被限流或单一来源污染。")
    return _unique(reasons)


def _source_repairs(review: LiteratureReview) -> list[str]:
    repairs: list[str] = []
    for item in review.source_health or []:
        source = str(item.get("source") or "")
        status = str(item.get("status") or "")
        returned = _safe_int(item.get("returned"))
        if source == "semantic_scholar" and (item.get("rate_limited") or status == "rate_limited"):
            repairs.append("设置 SEMANTIC_SCHOLAR_API_KEY 后重跑，避免 Semantic Scholar 429 让结果质量下降。")
        elif status in {"failed", "partial"} and returned == 0:
            repairs.append(f"修复 {source} 检索失败或从 sources 临时移除，避免空结果拉低召回。")
    if any("检索失败" in str(item) for item in review.source_diagnostics):
        repairs.append("查看 01-literature-source-health.md，优先修复失败最多的来源。")
    return _unique(repairs)


def _source_repair_severity(review: LiteratureReview, source_repairs: list[str]) -> str:
    if not source_repairs:
        return "none"
    successes = 0
    for item in review.source_health or []:
        status = str(item.get("status") or "")
        returned = _safe_int(item.get("returned"))
        if returned > 0 and status in {"ok", "partial", "offline_ranked"}:
            successes += 1
    return "review" if successes else "block"


def _rescue_queries(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    snowball_report: dict[str, Any],
    coverage_report: dict[str, Any],
    missing_roles: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_role_rescue_queries(research_plan, missing_roles))
    for item in _as_list(coverage_report.get("missing_required")):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            category = str(item.get("category") or "facet").strip()
            if name:
                rows.append(_query(f"{research_plan.topic} {name} benchmark baseline", "missing_facet", 98, f"{category}: {name}"))
                rows.append(_query(f'"{name}" {research_plan.topic}', "exact_missing_facet", 94, f"{category}: {name}"))
    for query in _as_list(snowball_report.get("expansion_queries")):
        if isinstance(query, dict):
            text = str(query.get("query") or "").strip()
            priority = _safe_int(query.get("priority"), 80)
            purpose = str(query.get("purpose") or "snowball")
            if text:
                rows.append(_query(text, "snowball", min(96, priority), purpose))
    rows.extend(_domain_rescue_queries(research_plan))
    if len(raw_review.papers) < 8:
        rows.append(_query(f"{research_plan.topic} survey review benchmark", "recall_repair", 88, "原始召回不足，补综述和 benchmark 入口"))
    return _dedupe_queries(rows)[:18]


def _role_rescue_queries(plan: ResearchPlan, missing_roles: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role in missing_roles:
        if role == "review_survey":
            rows.append(_query(f"{plan.topic} survey review systematic review benchmark", "missing_evidence_role", 99, "缺少 review/survey anchor"))
            rows.append(_query(f"{_query_base(plan)} survey review", "missing_evidence_role", 95, "补综述入口，避免只用孤立方法论文"))
        elif role == "benchmark_dataset":
            rows.append(_query(f"{plan.topic} benchmark dataset evaluation testbed", "missing_evidence_role", 99, "缺少 benchmark/dataset anchor"))
            rows.append(_query(f"{_query_base(plan)} benchmark dataset evaluation", "missing_evidence_role", 95, "补实验任务和数据集依据"))
        elif role == "baseline_method":
            rows.append(_query(f"{plan.topic} baseline method comparison algorithm", "missing_evidence_role", 99, "缺少 baseline/method anchor"))
            rows.append(_query(f"{_query_base(plan)} baseline comparison method", "missing_evidence_role", 95, "补可比较 baseline 依据"))
        elif role == "recent_work":
            rows.append(_query(f"{plan.topic} 2023 2024 2025 recent advances", "missing_evidence_role", 90, "缺少 recent work anchor"))
    return rows


def _domain_rescue_queries(plan: ResearchPlan) -> list[dict[str, Any]]:
    if plan.domain == "robotics_motion_planning":
        return [
            _query("robot manipulator motion planning benchmark OMPL MoveIt RRT* CHOMP STOMP TrajOpt", "domain_baseline_matrix", 96, "机械臂路径规划必须覆盖采样规划和轨迹优化 baseline"),
            _query("robot arm path planning collision avoidance trajectory optimization survey", "domain_survey", 86, "补综述入口，防止只拿到孤立算法论文"),
        ]
    if plan.domain == "bearing_fault_diagnosis":
        return [
            _query("bearing fault diagnosis CWRU Paderborn XJTU-SY benchmark cross load baseline", "domain_baseline_matrix", 96, "轴承故障诊断必须覆盖公开数据集和跨工况 baseline"),
            _query("bearing fault diagnosis domain adaptation vibration signal survey benchmark", "domain_survey", 86, "补综述入口和跨域鲁棒性文献"),
        ]
    if plan.domain == "ai_research_agents":
        return [
            _query("AI Scientist Agent Laboratory MLE-bench MLAgentBench autonomous research agent", "domain_systems", 96, "科研 agent 需要覆盖端到端系统和 benchmark"),
            _query("citation grounded research agent PaperQA STORM OpenScholar literature review", "domain_grounding", 92, "补 citation-grounded 文献工作流"),
        ]
    return [_query(f"{plan.topic} benchmark baseline systematic review", "generic_rescue", 82, "补 benchmark/baseline 和综述入口")]


def _query_base(plan: ResearchPlan) -> str:
    for query in plan.search_queries:
        value = str(query).strip()
        if value:
            return value
    return str(plan.topic).strip()


def _required_actions(weak_reasons: list[str], queries: list[dict[str, Any]], source_repairs: list[str]) -> list[str]:
    actions: list[str] = []
    if source_repairs:
        actions.append("先修复文献源/API key，再执行补检索式。")
    if weak_reasons:
        actions.append("下一轮至少执行 priority >= 94 的补检索式，并把高相关 DOI 加入人工 seed_papers。")
    if queries:
        actions.append("补检索后重新生成 01-literature-quality、01-literature-coverage 和 01-review-gate，再由人工确认是否进入 idea/实验。")
    if not actions:
        actions.append("当前文献质量和覆盖可进入人工审核；后续只需按领域审稿标准补少量人工 seed。")
    return actions


def _status(
    weak_reasons: list[str],
    coverage_status: str,
    source_repairs: list[str],
    source_repair_severity: str,
    selected_papers: int,
    queries: list[dict[str, Any]],
) -> str:
    if selected_papers == 0 or coverage_status == "block":
        return "block"
    if source_repairs and source_repair_severity == "block":
        return "needs_source_repair"
    actionable_weak_reasons = _non_source_weak_reasons(weak_reasons)
    if actionable_weak_reasons and queries:
        return "needs_rescue_search"
    if actionable_weak_reasons:
        return "needs_manual_seed"
    return "pass"


def _non_source_weak_reasons(weak_reasons: list[str]) -> list[str]:
    return [reason for reason in weak_reasons if not reason.startswith("至少一个在线文献源需要修复")]


def _config_hints(source_repairs: list[str]) -> list[str]:
    hints = ["literature.provider=online 或 auto 时，保留 openalex/arxiv/crossref 作为 Semantic Scholar 限流兜底。"]
    if any("SEMANTIC_SCHOLAR_API_KEY" in item for item in source_repairs):
        hints.insert(0, "设置环境变量 SEMANTIC_SCHOLAR_API_KEY 后重启服务。")
    return hints


def _quality_data(report: LiteratureQualityReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    return {
        "selected_papers": report.selected_papers,
        "warnings": report.warnings,
        "missing_evidence_roles": report.missing_evidence_roles,
        "role_coverage": report.role_coverage,
    }


def _missing_names(rows: list[Any]) -> list[str]:
    result: list[str] = []
    for item in rows:
        if isinstance(item, dict):
            value = str(item.get("name") or "").strip()
            if value:
                result.append(value)
    return result


def _query(query: str, kind: str, priority: int, rationale: str) -> dict[str, Any]:
    return {"query": re.sub(r"\s+", " ", query).strip(), "kind": kind, "priority": priority, "rationale": rationale}


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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


