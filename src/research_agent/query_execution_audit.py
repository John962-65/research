from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int
from .models import LiteratureReview, Paper, ResearchPlan


QUERY_EXECUTION_AUDIT_JSON = "01-query-execution-audit.json"
QUERY_EXECUTION_AUDIT_MD = "01-query-execution-audit.md"


def write_query_execution_audit_artifacts(
    research_plan: ResearchPlan,
    review: LiteratureReview,
    rerank_report: dict[str, Any],
    source_health_report: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    report = build_query_execution_audit(research_plan, review, rerank_report, source_health_report)
    write_json(run_dir / QUERY_EXECUTION_AUDIT_JSON, report)
    write_text(run_dir / QUERY_EXECUTION_AUDIT_MD, render_query_execution_audit_markdown(report))
    return report


def build_query_execution_audit(
    research_plan: ResearchPlan,
    review: LiteratureReview,
    rerank_report: dict[str, Any] | None = None,
    source_health_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rerank = rerank_report if isinstance(rerank_report, dict) else {}
    source_health = source_health_report if isinstance(source_health_report, dict) else {}
    strategy = review.search_strategy if isinstance(review.search_strategy, dict) else {}
    selected_queries = _selected_queries(strategy, research_plan, review)
    query_results = _query_results(source_health, review)
    candidates = _candidate_map(strategy)
    query_rows = [
        _query_row(query, candidates.get(_norm(query), {}), review.papers, query_results, rerank)
        for query in selected_queries
    ]
    intent_coverage = _intent_coverage(research_plan, query_rows, review.papers)
    source_coverage = _source_coverage(strategy, source_health, review, query_rows, query_results)
    top_coverage = _top_rerank_coverage(rerank, selected_queries)
    warnings, required_actions, manual_tasks = _findings(query_rows, intent_coverage, source_coverage, top_coverage, review)
    status = _status(required_actions, warnings, source_coverage)
    return {
        "schema_version": 1,
        "topic": research_plan.topic or review.topic,
        "status": status,
        "selected_query_count": len(selected_queries),
        "raw_candidate_count": len(review.papers),
        "source_coverage": source_coverage,
        "intent_coverage": intent_coverage,
        "top_rerank_coverage": top_coverage,
        "queries": query_rows,
        "warnings": warnings,
        "required_actions": required_actions,
        "manual_tasks": manual_tasks,
        "blocking_issues": [],
        "recommended_actions": _recommended_actions(status, required_actions, manual_tasks, warnings),
    }


def render_query_execution_audit_markdown(report: dict[str, Any]) -> str:
    source = report.get("source_coverage") if isinstance(report.get("source_coverage"), dict) else {}
    intent = report.get("intent_coverage") if isinstance(report.get("intent_coverage"), dict) else {}
    top = report.get("top_rerank_coverage") if isinstance(report.get("top_rerank_coverage"), dict) else {}
    lines = [
        f"# Query Execution Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 已选检索式：{report.get('selected_query_count', 0)}",
        f"- 原始候选：{report.get('raw_candidate_count', 0)}",
        f"- 来源成功/配置：{source.get('sources_with_success', 0)}/{source.get('configured_source_count', 0)}",
        f"- Query 返回/零返回：{source.get('queries_with_source_results', 0)}/{source.get('queries_with_zero_source_results', 0)}",
        f"- Top rerank 覆盖：{top.get('covered_top_count', 0)}/{top.get('top_count', 0)}，平均 query coverage={float(top.get('average_query_coverage') or 0.0):.2f}",
        f"- Required intents：{', '.join(str(item) for item in intent.get('required_intents', []) if str(item).strip()) or '-'}",
        f"- Missing intents：{', '.join(str(item) for item in intent.get('missing_required_intents', []) if str(item).strip()) or '-'}",
        "",
    ]
    for key, title in [("warnings", "警告"), ("required_actions", "必需动作"), ("manual_tasks", "人工待办")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(
        [
            "## Query 覆盖表",
            "| 状态 | Intent | Source 返回 | 成功源 | 失败源 | 限流源 | 候选命中 | 高质量命中 | Top 命中 | 检索式 | 动作 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    queries = report.get("queries") if isinstance(report.get("queries"), list) else []
    if not queries:
        lines.append("| - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | - | - |")
    for item in queries:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("intent") or "")),
                    str(item.get("source_returned") or 0),
                    str(item.get("successful_sources") or 0),
                    str(item.get("failed_sources") or 0),
                    str(item.get("rate_limited_sources") or 0),
                    str(item.get("candidate_hits") or 0),
                    str(item.get("high_quality_hits") or 0),
                    str(item.get("top_hits") or 0),
                    "`" + _cell(str(item.get("query") or "")) + "`",
                    _cell("; ".join(str(value) for value in item.get("actions", []) if str(value).strip()) or "-"),
                ]
            )
            + " |"
        )
    uncovered = top.get("uncovered_top_titles") if isinstance(top.get("uncovered_top_titles"), list) else []
    if uncovered:
        lines.extend(["", "## Top 未覆盖候选"])
        lines.extend(f"- {item}" for item in uncovered[:8])
    lines.extend(["", "## 使用方式", "- 先处理 `needs_source_repair`，再处理 query/seed 修复；否则后续 rerank、quality 和 citation gate 会继续被低质量候选污染。"])
    return "\n".join(lines)


def _query_row(
    query: str,
    candidate: dict[str, Any],
    papers: list[Paper],
    query_results: list[dict[str, Any]],
    rerank_report: dict[str, Any],
) -> dict[str, Any]:
    matched_results = [row for row in query_results if _norm(row.get("query")) == _norm(query)]
    source_returned = sum(_safe_int(row.get("returned")) for row in matched_results)
    successful_sources = {str(row.get("source") or "") for row in matched_results if str(row.get("status") or "") in {"ok", "offline_ranked"} and _safe_int(row.get("returned")) > 0}
    failed_sources = {str(row.get("source") or "") for row in matched_results if str(row.get("status") or "") == "failed"}
    rate_limited_sources = {str(row.get("source") or "") for row in matched_results if row.get("rate_limited") is True or str(row.get("status") or "") == "rate_limited"}
    terms = _terms(query)
    candidate_hits = [paper for paper in papers if _matches_query(paper, terms)]
    high_quality_hits = [paper for paper in candidate_hits if _is_high_quality_hit(paper)]
    top_hits = _top_hits(rerank_report, query)
    actions: list[str] = []
    status = "pass"
    if matched_results and source_returned == 0:
        status = "no_source_results"
        actions.append("修复 source/API key 或替换该检索式后重跑。")
    elif not matched_results:
        status = "no_execution_trace" if not candidate_hits else "pass"
        if status == "no_execution_trace":
            actions.append("重新生成 source health，确保每条 query 有 source 执行记录。")
    if candidate_hits == 0:
        status = "no_candidate_hits" if status == "pass" else status
        actions.append("收窄或重写检索式，并加入核心 DOI/URL seed。")
    elif not high_quality_hits:
        status = "weak_candidate_hits" if status == "pass" else status
        actions.append("补 DOI/URL seed 或提高 metadata/source 质量。")
    return {
        "query": query,
        "intent": str(candidate.get("intent") or _query_intent(query)),
        "origin": str(candidate.get("origin") or ""),
        "risk": str(candidate.get("risk") or ""),
        "status": status,
        "source_attempts": len(matched_results),
        "source_returned": source_returned,
        "successful_sources": len([source for source in successful_sources if source]),
        "failed_sources": len([source for source in failed_sources if source]),
        "rate_limited_sources": len([source for source in rate_limited_sources if source]),
        "candidate_hits": len(candidate_hits),
        "high_quality_hits": len(high_quality_hits),
        "top_hits": top_hits,
        "actions": _unique(actions),
    }


def _intent_coverage(research_plan: ResearchPlan, query_rows: list[dict[str, Any]], papers: list[Paper]) -> dict[str, Any]:
    required = ["method"]
    if research_plan.baselines:
        required.append("baseline")
    if research_plan.benchmarks:
        required.append("benchmark")
    selected = sorted({str(row.get("intent") or "") for row in query_rows if str(row.get("intent") or "")})
    paper_hits: dict[str, int] = {}
    for intent in selected:
        intent_terms = _intent_terms(intent, research_plan)
        paper_hits[intent] = sum(1 for paper in papers if _matches_terms(_paper_text(paper), intent_terms))
    missing = [intent for intent in required if intent not in selected]
    return {
        "required_intents": required,
        "selected_intents": selected,
        "missing_required_intents": missing,
        "paper_hits_by_intent": paper_hits,
    }


def _source_coverage(
    strategy: dict[str, Any],
    source_health_report: dict[str, Any],
    review: LiteratureReview,
    query_rows: list[dict[str, Any]],
    query_results: list[dict[str, Any]],
) -> dict[str, Any]:
    sources = source_health_report.get("sources") if isinstance(source_health_report.get("sources"), list) else review.source_health
    configured = [str(source).strip().lower() for source in _as_list(strategy.get("sources")) if str(source).strip()]
    sources_with_success = {
        str(row.get("source") or "")
        for row in query_results
        if str(row.get("status") or "") in {"ok", "offline_ranked"} and _safe_int(row.get("returned")) > 0
    }
    if not sources_with_success:
        sources_with_success = {str(item.get("source") or "") for item in sources if _safe_int(item.get("returned")) > 0 and str(item.get("status") or "") in {"ok", "partial"}}
    rate_limited = sum(1 for item in sources if isinstance(item, dict) and (item.get("rate_limited") is True or str(item.get("status") or "") == "rate_limited"))
    failed = sum(1 for item in sources if isinstance(item, dict) and str(item.get("status") or "") == "failed")
    returned_total = sum(_safe_int(row.get("source_returned")) for row in query_rows) or sum(_safe_int(item.get("returned")) for item in sources if isinstance(item, dict))
    stale_cache = sum(_safe_int(item.get("stale_cache_uses")) for item in sources if isinstance(item, dict))
    return {
        "configured_sources": configured,
        "configured_source_count": len(configured),
        "sources_with_success": len([source for source in sources_with_success if source]),
        "rate_limited_sources": rate_limited,
        "failed_sources": failed,
        "returned_total": returned_total,
        "stale_cache_uses": stale_cache,
        "queries_with_source_results": sum(1 for row in query_rows if _safe_int(row.get("source_returned")) > 0),
        "queries_with_zero_source_results": sum(1 for row in query_rows if row.get("source_attempts") and _safe_int(row.get("source_returned")) == 0),
    }


def _top_rerank_coverage(rerank_report: dict[str, Any], selected_queries: list[str]) -> dict[str, Any]:
    items = rerank_report.get("items") if isinstance(rerank_report.get("items"), list) else []
    top = [item for item in items[: min(10, len(items))] if isinstance(item, dict)]
    coverages = [_safe_float(item.get("query_coverage")) for item in top]
    uncovered: list[str] = []
    covered_count = 0
    for item in top:
        coverage = _safe_float(item.get("query_coverage"))
        title = str(item.get("title") or "")
        if coverage > 0 or _title_matches_any_query(title, selected_queries):
            covered_count += 1
        elif title:
            uncovered.append(title)
    return {
        "top_count": len(top),
        "covered_top_count": covered_count,
        "average_query_coverage": round(sum(coverages) / max(1, len(coverages)), 3) if coverages else 0.0,
        "uncovered_top_titles": uncovered,
    }


def _findings(
    query_rows: list[dict[str, Any]],
    intent_coverage: dict[str, Any],
    source_coverage: dict[str, Any],
    top_coverage: dict[str, Any],
    review: LiteratureReview,
) -> tuple[list[str], list[str], list[str]]:
    warnings: list[str] = []
    actions: list[str] = []
    manual: list[str] = []
    if not query_rows:
        actions.append("没有可审计的 selected_queries；补充研究计划检索式并重新生成文献检索策略。")
    if not review.papers:
        actions.append("原始候选为空；先修复 source/API key，再执行补检索或补 seed paper。")
    missing = intent_coverage.get("missing_required_intents") if isinstance(intent_coverage.get("missing_required_intents"), list) else []
    if missing:
        actions.append("补齐 selected_queries 缺失的检索意图：" + ", ".join(str(item) for item in missing))
    zero_source = [row for row in query_rows if str(row.get("status") or "") == "no_source_results"]
    no_hits = [row for row in query_rows if str(row.get("status") or "") in {"no_candidate_hits", "no_execution_trace"}]
    weak_hits = [row for row in query_rows if str(row.get("status") or "") == "weak_candidate_hits"]
    if zero_source:
        actions.append(f"{len(zero_source)} 条 selected query 没有 source 返回；查看 01-literature-source-health.md 的 Query 执行表。")
    if no_hits:
        actions.append(f"{len(no_hits)} 条 selected query 没有进入候选池；需要重写 query 或补 DOI/URL seed。")
    if weak_hits:
        warnings.append(f"{len(weak_hits)} 条 selected query 只有弱候选，metadata/source 质量不足。")
    if _safe_int(source_coverage.get("rate_limited_sources")):
        warnings.append("存在限流文献源，Semantic Scholar 等来源可能未参与高质量候选召回。")
        manual.append("如使用 Semantic Scholar，设置 SEMANTIC_SCHOLAR_API_KEY 后重跑。")
    if _safe_int(source_coverage.get("failed_sources")):
        warnings.append("存在失败文献源，当前召回可能偏窄。")
    if _safe_int(source_coverage.get("stale_cache_uses")):
        warnings.append("使用过期缓存兜底，需人工确认是否接受旧 metadata。")
    top_count = _safe_int(top_coverage.get("top_count"))
    covered_top = _safe_int(top_coverage.get("covered_top_count"))
    if top_count and covered_top < max(1, top_count // 2):
        warnings.append("Top rerank 候选对 selected queries 覆盖不足，可能仍有泛题录污染。")
    if query_rows and sum(1 for row in query_rows if _safe_int(row.get("high_quality_hits")) > 0) < max(1, len(query_rows) // 2):
        warnings.append("少于一半 selected queries 有高质量命中，建议补核心 DOI seed。")
    return _unique(warnings), _unique(actions), _unique(manual)


def _status(required_actions: list[str], warnings: list[str], source_coverage: dict[str, Any]) -> str:
    severe_source = (
        _safe_int(source_coverage.get("sources_with_success")) == 0
        and (_safe_int(source_coverage.get("failed_sources")) or _safe_int(source_coverage.get("rate_limited_sources")))
    )
    if severe_source:
        return "needs_source_repair"
    if required_actions:
        if any("source/API key" in item or "没有 source 返回" in item for item in required_actions):
            return "needs_source_repair" if _safe_int(source_coverage.get("sources_with_success")) == 0 else "needs_query_repair"
        return "needs_query_repair"
    if warnings:
        return "review_required"
    return "pass"


def _recommended_actions(status: str, required: list[str], manual: list[str], warnings: list[str]) -> list[str]:
    if status == "pass":
        return ["抽查 Top 5 DOI/URL 后可进入人工 review gate。"]
    return _unique([*required, *manual, *warnings])[:8]


def _selected_queries(strategy: dict[str, Any], research_plan: ResearchPlan, review: LiteratureReview) -> list[str]:
    selected = [str(item).strip() for item in _as_list(strategy.get("selected_queries")) if str(item).strip()]
    if selected:
        return _unique(selected)
    if research_plan.search_queries:
        return _unique([str(item).strip() for item in research_plan.search_queries if str(item).strip()])
    return _unique(_legacy_queries(review))


def _candidate_map(strategy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in _as_list(strategy.get("candidates")):
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if query:
            rows[_norm(query)] = item
    return rows


def _query_results(source_health_report: dict[str, Any], review: LiteratureReview) -> list[dict[str, Any]]:
    rows = source_health_report.get("query_results") if isinstance(source_health_report.get("query_results"), list) else []
    if rows:
        return [dict(item) for item in rows if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    for source in review.source_health or []:
        source_rows = source.get("query_results") if isinstance(source.get("query_results"), list) else []
        for item in source_rows:
            if isinstance(item, dict):
                result.append(dict(item))
    return result


def _legacy_queries(review: LiteratureReview) -> list[str]:
    queries: list[str] = []
    for item in review.source_diagnostics:
        if "检索式:" in item:
            queries.extend(query.strip() for query in item.split("检索式:", 1)[-1].split("|") if query.strip())
    return queries


def _top_hits(rerank_report: dict[str, Any], query: str) -> int:
    items = rerank_report.get("items") if isinstance(rerank_report.get("items"), list) else []
    terms = _terms(query)
    count = 0
    for item in items[: min(10, len(items))]:
        if isinstance(item, dict) and _matches_text(str(item.get("title") or ""), terms):
            count += 1
    return count


def _is_high_quality_hit(paper: Paper) -> bool:
    has_locator = bool(paper.doi or paper.url)
    has_metadata = bool(paper.year and paper.authors and len(paper.abstract or "") >= 80)
    trusted_source = bool(set(paper.sources or [paper.source]) - {"crossref", "offline"})
    return paper.relevance >= 0.45 and has_locator and (has_metadata or trusted_source or "manual_seed" in set(paper.sources or [paper.source]))


def _matches_query(paper: Paper, query_terms: list[str]) -> bool:
    return _matches_text(_paper_text(paper), query_terms)


def _matches_terms(text: str, terms: list[str]) -> bool:
    if not terms:
        return False
    return _matches_text(text, terms)


def _matches_text(text: str, terms: list[str]) -> bool:
    if not terms:
        return False
    text_terms = set(_terms(text))
    lower = text.lower().replace("-", "_")
    hits = 0
    for term in terms:
        base = term.replace("*", "")
        if term in text_terms or term in lower or (base and base in lower):
            hits += 1
    needed = max(1, min(3, len(terms) // 4 or 1))
    return hits >= needed


def _title_matches_any_query(title: str, queries: list[str]) -> bool:
    return any(_matches_text(title, _terms(query)) for query in queries)


def _intent_terms(intent: str, plan: ResearchPlan) -> list[str]:
    if intent == "baseline":
        return _terms(" ".join(plan.baselines))
    if intent == "benchmark":
        return _terms(" ".join(plan.benchmarks))
    if intent == "experiment":
        return _terms(" ".join(plan.metrics))
    if intent == "survey":
        return ["review", "survey", "systematic", "综述"]
    return _terms(f"{plan.topic} {plan.objective} {plan.domain}")


def _query_intent(query: str) -> str:
    lower = query.lower()
    if any(term in lower for term in ["benchmark", "dataset", "ompl", "cwru", "paderborn", "xjtu"]):
        return "benchmark"
    if any(term in lower for term in ["baseline", "rrt", "prm", "chomp", "stomp", "trajopt", "cnn", "transformer"]):
        return "baseline"
    if any(term in lower for term in ["review", "survey", "literature"]):
        return "survey"
    if any(term in lower for term in ["experiment", "evaluation", "metric"]):
        return "experiment"
    return "method"


def _paper_text(paper: Paper) -> str:
    return f"{paper.title} {paper.abstract} {paper.venue} {' '.join(paper.authors)}".lower()


def _terms(text: Any) -> list[str]:
    values: list[str] = []
    for match in re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{1,}|[\u4e00-\u9fff]{2,}", str(text).lower()):
        normalized = match.replace("-", "_")
        if re.fullmatch(r"[\u4e00-\u9fff]+", normalized):
            values.append(normalized)
            if len(normalized) > 2:
                values.extend(normalized[index : index + 2] for index in range(0, len(normalized) - 1))
        else:
            values.append(normalized)
    stop = {"the", "and", "for", "with", "using", "from", "based", "research", "study", "method", "methods"}
    return _unique([value for value in values if value not in stop])


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = str(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


