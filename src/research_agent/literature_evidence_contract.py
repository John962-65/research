from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text, cell as _cell
from .literature_quality import CORE_EVIDENCE_ROLES
from .models import LiteratureContext


LITERATURE_EVIDENCE_CONTRACT_JSON = "01-literature-evidence-contract.json"
LITERATURE_EVIDENCE_CONTRACT_MD = "01-literature-evidence-contract.md"
LITERATURE_EVIDENCE_CONTRACT_SCHEMA_VERSION = 2
SUBSTANTIVE_CHUNK_MIN_CHARS = 180


def write_literature_evidence_contract_artifacts(
    *,
    context: LiteratureContext | dict[str, Any],
    quality_report: dict[str, Any] | Any | None = None,
    source_health_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    citation_audit_report: dict[str, Any] | Any | None = None,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_evidence_contract(
        context=context,
        quality_report=quality_report,
        source_health_report=source_health_report,
        query_execution_report=query_execution_report,
        rerank_report=rerank_report,
        citation_audit_report=citation_audit_report,
    )
    write_json(run_dir / LITERATURE_EVIDENCE_CONTRACT_JSON, report)
    write_text(run_dir / LITERATURE_EVIDENCE_CONTRACT_MD, render_literature_evidence_contract_markdown(report))
    return report


def build_literature_evidence_contract(
    *,
    context: LiteratureContext | dict[str, Any],
    quality_report: dict[str, Any] | Any | None = None,
    source_health_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    citation_audit_report: dict[str, Any] | Any | None = None,
) -> dict[str, Any]:
    ctx = _context_dict(context)
    quality = _report_dict(quality_report)
    source_health = source_health_report if isinstance(source_health_report, dict) else {}
    query_execution = query_execution_report if isinstance(query_execution_report, dict) else {}
    rerank = rerank_report if isinstance(rerank_report, dict) else {}
    citation_audit = _report_dict(citation_audit_report)

    citations = _list_dicts(ctx.get("citations"))
    chunks = _list_dicts(ctx.get("chunks"))
    citation_keys = {str(item.get("key") or "").strip() for item in citations if str(item.get("key") or "").strip()}
    chunk_keys = {str(item.get("citation_key") or "").strip() for item in chunks if str(item.get("citation_key") or "").strip()}
    citations_with_chunks = len(citation_keys & chunk_keys)
    chunk_lengths_by_key = _chunk_lengths_by_key(chunks)
    substantive_keys = {
        key
        for key in citation_keys
        if max(chunk_lengths_by_key.get(key, [0])) >= SUBSTANTIVE_CHUNK_MIN_CHARS
    }
    per_citation_chunk_chars = [max(chunk_lengths_by_key.get(key, [0])) for key in citation_keys]
    source_values = _source_values(citations)
    single_crossref = [item for item in citations if _is_single_crossref(item)]
    locators = [item for item in citations if str(item.get("doi") or "").strip() or str(item.get("url") or "").strip()]
    doi_values = [item for item in citations if str(item.get("doi") or "").strip()]
    url_values = [item for item in citations if str(item.get("url") or "").strip()]
    local_fulltext_chunks = [item for item in chunks if "local_fulltext" in str(item.get("source") or "").lower()]
    thin_chunks = [item for item in chunks if len(str(item.get("text") or "").strip()) < 120 and "local_fulltext" not in str(item.get("source") or "").lower()]
    role_coverage = quality.get("role_coverage") if isinstance(quality.get("role_coverage"), dict) else {}
    missing_roles = [str(item) for item in quality.get("missing_evidence_roles", [])] if isinstance(quality.get("missing_evidence_roles"), list) else []
    role_count = sum(1 for role in CORE_EVIDENCE_ROLES if _safe_int(role_coverage.get(role)) > 0)
    top_rerank = _top_rerank_coverage(query_execution, rerank)
    source_successes = _source_successes(source_health, query_execution)
    rate_limited_sources = _safe_int(source_health.get("rate_limited_sources"))
    failed_sources = _safe_int(source_health.get("failed_sources"))

    summary = {
        "citations": len(citations),
        "chunks": len(chunks),
        "citations_with_chunks": citations_with_chunks,
        "citations_with_substantive_chunks": len(substantive_keys),
        "chunk_coverage": _ratio(citations_with_chunks, len(citations)),
        "substantive_chunk_coverage": _ratio(len(substantive_keys), len(citations)),
        "median_chunk_chars": _median_int(per_citation_chunk_chars),
        "locator_coverage": _ratio(len(locators), len(citations)),
        "doi_coverage": _ratio(len(doi_values), len(citations)),
        "url_coverage": _ratio(len(url_values), len(citations)),
        "source_diversity": len(source_values),
        "single_crossref_citations": len(single_crossref),
        "single_crossref_ratio": _ratio(len(single_crossref), len(citations)),
        "thin_chunks": len(thin_chunks),
        "local_fulltext_chunks": len(local_fulltext_chunks),
        "evidence_role_count": role_count,
        "missing_evidence_roles": missing_roles,
        "sources_with_success": source_successes,
        "rate_limited_sources": rate_limited_sources,
        "failed_sources": failed_sources,
        "query_execution_status": str(query_execution.get("status") or ""),
        "rerank_status": str(rerank.get("status") or ""),
        "top_rerank_covered": _safe_int(top_rerank.get("covered_top_count")),
        "top_rerank_count": _safe_int(top_rerank.get("top_count")),
        "average_query_coverage": _safe_float(top_rerank.get("average_query_coverage")),
        "citation_integrity_status": str(citation_audit.get("integrity_status") or ""),
        "blocked_citations": _safe_int(citation_audit.get("blocked_citations")),
        "review_citations": _safe_int(citation_audit.get("review_required")),
    }
    checks = _checks(summary)
    blocking_issues = [item["message"] for item in checks if item["status"] == "block"]
    review_reasons = [item["message"] for item in checks if item["status"] == "review_required"]
    status = "block" if blocking_issues else "review_required" if review_reasons else "pass"
    return {
        "schema_version": LITERATURE_EVIDENCE_CONTRACT_SCHEMA_VERSION,
        "topic": str(ctx.get("topic") or ""),
        "status": status,
        "blocks_downstream": status == "block",
        "human_approval_required": True,
        "summary": summary,
        "checks": checks,
        "blocking_issues": _unique(blocking_issues),
        "review_reasons": _unique(review_reasons),
        "required_actions": _required_actions(status, summary, blocking_issues, review_reasons),
        "approval_guidance": _approval_guidance(status),
    }


def render_literature_evidence_contract_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# 文献证据契约：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 阻断后续：{'yes' if report.get('blocks_downstream') else 'no'}",
        f"- 人工批准必需：{'yes' if report.get('human_approval_required') else 'no'}",
        f"- Citation/chunk：{summary.get('citations', 0)}/{summary.get('chunks', 0)}，chunk coverage={float(summary.get('chunk_coverage') or 0.0):.3f}",
        f"- 实质证据片段：{summary.get('citations_with_substantive_chunks', 0)}/{summary.get('citations', 0)}，coverage={float(summary.get('substantive_chunk_coverage') or 0.0):.3f}，median chars={summary.get('median_chunk_chars', 0)}",
        f"- Locator：DOI={float(summary.get('doi_coverage') or 0.0):.3f}，URL={float(summary.get('url_coverage') or 0.0):.3f}，任一定位符={float(summary.get('locator_coverage') or 0.0):.3f}",
        f"- 来源多样性：{summary.get('source_diversity', 0)}，单源 Crossref={summary.get('single_crossref_citations', 0)} ({float(summary.get('single_crossref_ratio') or 0.0):.3f})",
        f"- 证据角色：{summary.get('evidence_role_count', 0)}/{len(CORE_EVIDENCE_ROLES)}，缺失={', '.join(str(item) for item in summary.get('missing_evidence_roles', []) or []) or '-'}",
        f"- Query/Rerank：query={summary.get('query_execution_status') or '-'}，rerank={summary.get('rerank_status') or '-'}，top covered={summary.get('top_rerank_covered', 0)}/{summary.get('top_rerank_count', 0)}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断原因"), ("review_reasons", "人工复核原因"), ("required_actions", "必须动作"), ("approval_guidance", "批准指导")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.append(f"## {title}")
            prefix = "- [ ] " if key == "required_actions" else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(["## 检查表", "| 检查 | 状态 | 值 | 说明 |", "| --- | --- | ---: | --- |"])
    for item in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("name") or "")),
                        _cell(str(item.get("status") or "")),
                        _cell(str(item.get("value") if item.get("value") is not None else "-")),
                        _cell(str(item.get("message") or "")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## 使用规则",
            "- 状态为 block 时，不能批准进入 idea 或实验；先替换弱题录、补 seed/fulltext 或重跑检索。",
            "- 状态为 review_required 时，批准 notes 必须写明人工核对过的 DOI/URL、摘要/全文和保留风险。",
            "- 该契约参考 PaperQA2/OpenScholar 的可追溯 RAG 思路，检查进入 context 的证据是否可定位、可支撑、可复核。",
        ]
    )
    return "\n".join(lines)


def _checks(summary: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    citations = _safe_int(summary.get("citations"))
    chunks = _safe_int(summary.get("chunks"))
    source_diversity = _safe_int(summary.get("source_diversity"))
    chunk_coverage = _safe_float(summary.get("chunk_coverage"))
    substantive_chunk_coverage = _safe_float(summary.get("substantive_chunk_coverage"))
    median_chunk_chars = _safe_int(summary.get("median_chunk_chars"))
    locator_coverage = _safe_float(summary.get("locator_coverage"))
    doi_coverage = _safe_float(summary.get("doi_coverage"))
    single_crossref_ratio = _safe_float(summary.get("single_crossref_ratio"))
    role_count = _safe_int(summary.get("evidence_role_count"))
    top_count = _safe_int(summary.get("top_rerank_count"))
    top_covered = _safe_int(summary.get("top_rerank_covered"))
    avg_query_coverage = _safe_float(summary.get("average_query_coverage"))
    blocked_citations = _safe_int(summary.get("blocked_citations"))
    review_citations = _safe_int(summary.get("review_citations"))

    checks.append(_check("citation_count", "block" if citations == 0 else "review_required" if citations < 5 else "pass", citations, "进入 context 的 citation 数量不足 5 篇会削弱综述和 idea 证据池。"))
    checks.append(_check("chunk_count", "block" if chunks == 0 else "pass", chunks, "必须有可追踪 evidence chunk。"))
    checks.append(_check("chunk_coverage", "block" if chunk_coverage == 0.0 else "review_required" if chunk_coverage < 0.75 else "pass", round(chunk_coverage, 3), "大多数 citation 需要至少一个摘要或全文 chunk 支撑。"))
    checks.append(_check("substantive_chunk_coverage", "block" if citations and substantive_chunk_coverage < 0.60 else "review_required" if citations and substantive_chunk_coverage < 0.80 else "pass", round(substantive_chunk_coverage, 3), f"核心 citation 需要不少于 {SUBSTANTIVE_CHUNK_MIN_CHARS} 字符的摘要或全文 evidence chunk，避免题名/短题录冒充证据。"))
    checks.append(_check("median_chunk_chars", "review_required" if chunks and median_chunk_chars < SUBSTANTIVE_CHUNK_MIN_CHARS else "pass", median_chunk_chars, "按 citation 聚合后的 evidence chunk 中位长度过短时，RAG/context 需要人工核对。"))
    checks.append(_check("locator_coverage", "block" if locator_coverage < 0.60 else "review_required" if doi_coverage < 0.50 else "pass", round(locator_coverage, 3), "核心文献需要 DOI 或 URL；DOI 覆盖过低时需人工核验。"))
    checks.append(_check("source_diversity", "review_required" if citations >= 3 and source_diversity < 2 else "pass", source_diversity, "文献来源过于单一会放大单个 API 的噪声。"))
    checks.append(_check("single_crossref_ratio", "block" if citations >= 3 and single_crossref_ratio > 0.60 else "review_required" if single_crossref_ratio > 0.35 else "pass", round(single_crossref_ratio, 3), "单源 Crossref 题录不能主导 RAG/context。"))
    checks.append(_check("evidence_roles", "review_required" if role_count < 3 else "pass", role_count, "至少覆盖 review/survey、benchmark/dataset、baseline/method、recent work 中 3 类。"))
    if top_count:
        checks.append(_check("top_rerank_query_coverage", "review_required" if top_covered < max(1, top_count // 2) or avg_query_coverage < 0.25 else "pass", round(avg_query_coverage, 3), "Top rerank 候选需要覆盖选中检索式，避免泛题录上浮。"))
    if blocked_citations:
        checks.append(_check("citation_integrity", "block", blocked_citations, "存在 citation audit 阻断引用。"))
    elif review_citations:
        checks.append(_check("citation_integrity", "review_required", review_citations, "存在需要人工核对的引用。"))
    else:
        checks.append(_check("citation_integrity", "pass", 0, "没有 citation audit 阻断项。"))
    return checks


def _required_actions(status: str, summary: dict[str, Any], blockers: list[str], reviews: list[str]) -> list[str]:
    actions: list[str] = []
    if _safe_int(summary.get("citations")) < 5:
        actions.append("补充至少 5 篇可核验核心文献，优先 DOI/URL seed、OpenAlex/Semantic Scholar 或本地全文。")
    if _safe_float(summary.get("locator_coverage")) < 0.80 or _safe_float(summary.get("doi_coverage")) < 0.50:
        actions.append("替换缺 DOI/URL 的候选，或在 seed_papers 中补入核心 DOI/URL 后重跑文献阶段。")
    if _safe_float(summary.get("substantive_chunk_coverage")) < 0.80:
        actions.append("为核心文献补充可核验摘要或本地全文 chunk，避免仅凭题名/短题录进入 RAG/context。")
    if _safe_float(summary.get("single_crossref_ratio")) > 0.35:
        actions.append("降低单源 Crossref 题录占比：启用 OpenAlex/Semantic Scholar、补 DOI seed，或加入可核验全文。")
    if _safe_int(summary.get("evidence_role_count")) < 3:
        actions.append("补齐 review_survey、benchmark_dataset、baseline_method、recent_work 中至少 3 类证据角色。")
    if _safe_int(summary.get("blocked_citations")):
        actions.append("处理 01-citation-audit.md 中的 block 引用后重新生成 context 和文献证据契约。")
    if status == "block":
        actions.append("阻断项处理前不要批准进入 idea/实验；修复后重新生成 01-literature-evidence-contract 和总门禁。")
    elif reviews:
        actions.append("批准前人工打开 Top DOI/URL 和 evidence chunk，在 approval notes 写明核对内容和剩余风险。")
    return _unique(actions)


def _approval_guidance(status: str) -> list[str]:
    if status == "block":
        return [
            "当前文献证据契约阻断 idea_generation、experiment_planning 和 experiment_execution。",
            "先修复 citation/chunk、locator、source diversity 或 Crossref 噪声，再请求人工审核。",
        ]
    if status == "review_required":
        return [
            "必须人工确认 Top 文献 DOI/URL、摘要/全文 chunk 和缺失证据角色。",
            "approval notes 需要说明已核对的具体文献和接受的剩余风险。",
        ]
    return ["证据契约已通过；仍需人工批准后才允许进入 idea/实验。"]


def _context_dict(context: LiteratureContext | dict[str, Any]) -> dict[str, Any]:
    if isinstance(context, dict):
        return context
    return {
        "topic": getattr(context, "topic", ""),
        "citations": [getattr(item, "__dict__", item) for item in getattr(context, "citations", [])],
        "chunks": [getattr(item, "__dict__", item) for item in getattr(context, "chunks", [])],
    }


def _report_dict(report: dict[str, Any] | Any | None) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    if report is None:
        return {}
    result: dict[str, Any] = {}
    for key in dir(report):
        if key.startswith("_"):
            continue
        value = getattr(report, key, None)
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
            result[key] = value
    return result


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _source_values(citations: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for item in citations:
        source = str(item.get("source") or "").lower()
        for part in source.split(","):
            part = part.strip()
            if part:
                values.add(part)
    return values


def _is_single_crossref(citation: dict[str, Any]) -> bool:
    values = _source_values([citation])
    return values == {"crossref"}


def _top_rerank_coverage(query_execution: dict[str, Any], rerank: dict[str, Any]) -> dict[str, Any]:
    coverage = query_execution.get("top_rerank_coverage") if isinstance(query_execution.get("top_rerank_coverage"), dict) else {}
    if coverage:
        return coverage
    items = rerank.get("items") if isinstance(rerank.get("items"), list) else []
    top = [item for item in items[: min(5, len(items))] if isinstance(item, dict)]
    if not top:
        return {}
    covered = sum(1 for item in top if _safe_float(item.get("query_coverage")) > 0)
    return {
        "top_count": len(top),
        "covered_top_count": covered,
        "average_query_coverage": sum(_safe_float(item.get("query_coverage")) for item in top) / max(len(top), 1),
    }


def _source_successes(source_health: dict[str, Any], query_execution: dict[str, Any]) -> int:
    source_coverage = query_execution.get("source_coverage") if isinstance(query_execution.get("source_coverage"), dict) else {}
    successes = _safe_int(source_coverage.get("sources_with_success"))
    if successes:
        return successes
    sources = source_health.get("sources") if isinstance(source_health.get("sources"), list) else []
    if sources:
        return sum(1 for item in sources if isinstance(item, dict) and _safe_int(item.get("returned")) > 0)
    return 0


def _check(name: str, status: str, value: Any, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "value": value, "message": message}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(max(0.0, min(1.0, numerator / denominator)), 3)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _chunk_lengths_by_key(chunks: list[dict[str, Any]]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for chunk in chunks:
        key = str(chunk.get("citation_key") or "").strip()
        if not key:
            continue
        result.setdefault(key, []).append(len(str(chunk.get("text") or "").strip()))
    return result


def _median_int(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return int(ordered[midpoint])
    return int(round((ordered[midpoint - 1] + ordered[midpoint]) / 2))


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


