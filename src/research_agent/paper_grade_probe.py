from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

from .artifacts import write_json, write_text, cell as _cell
from .config import AgentConfig, LiteratureConfig, PaperGradeConfig
from .literature import parse_manual_seed_papers
from .literature_sources import OnlineLiteratureClient
from .models import Paper


PAPER_GRADE_ONLINE_PROBE_JSON = "00-paper-grade-online-probe.json"
PAPER_GRADE_ONLINE_PROBE_MD = "00-paper-grade-online-probe.md"


def write_paper_grade_online_probe_artifacts(
    topic: str,
    config: AgentConfig,
    out_dir: Path,
    queries: list[str] | None = None,
    client_factory: Callable[[LiteratureConfig], Any] | None = None,
) -> dict[str, Any]:
    report = build_paper_grade_online_probe(topic, config, queries=queries, client_factory=client_factory)
    write_json(out_dir / PAPER_GRADE_ONLINE_PROBE_JSON, report)
    write_text(out_dir / PAPER_GRADE_ONLINE_PROBE_MD, render_paper_grade_online_probe_markdown(report))
    return report


def build_paper_grade_online_probe(
    topic: str,
    config: AgentConfig,
    queries: list[str] | None = None,
    client_factory: Callable[[LiteratureConfig], Any] | None = None,
) -> dict[str, Any]:
    literature = config.literature
    selected_queries = _selected_probe_queries(topic, literature, queries)
    checks: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    papers: list[Paper] = []
    source_health: list[dict[str, Any]] = []
    seed_papers: list[Paper] = []
    seed_diagnostics: list[str] = []
    client = (client_factory or OnlineLiteratureClient)(literature)

    if literature.provider in {"online", "auto"}:
        checks.append(_check("literature_provider", "pass", f"provider={literature.provider}"))
        try:
            seed_papers, seed_diagnostics = parse_manual_seed_papers(literature.seed_papers, resolver=_seed_resolver(client))
        except Exception as exc:
            seed_diagnostics = [f"manual_seed_probe: seed metadata probe failed: {_safe_diagnostic(exc, literature)}"]
            seed_papers = []
        try:
            papers, diagnostics = client.search(topic, selected_queries)
        except Exception as exc:
            diagnostics = [f"online_probe: search failed: {_safe_diagnostic(exc, literature)}"]
            papers = []
        source_health = [dict(item) for item in getattr(client, "source_health", []) if isinstance(item, dict)]
    else:
        checks.append(_check("literature_provider", "fail", f"provider={literature.provider}", "paper-grade online probe requires literature.provider=online or auto."))
        seed_papers, seed_diagnostics = parse_manual_seed_papers(literature.seed_papers)

    seed_diagnostics = _safe_diagnostics(seed_diagnostics, literature)
    diagnostics = _safe_diagnostics(diagnostics, literature)
    source_health = [_safe_source_health_item(item, literature) for item in source_health]
    source_summary = _source_summary(literature, source_health)
    seed_summary = _seed_summary(seed_papers, seed_diagnostics)
    checks.extend(_source_checks(source_summary, config.paper_grade))
    checks.extend(_seed_checks(seed_summary, config.paper_grade))
    checks.append(
        _check(
            "online_candidates",
            "pass" if len(papers) > 0 else "fail",
            f"filtered_candidates={len(papers)}",
            "Adjust queries, sources, contact email, API keys, or max_papers if online candidates are empty.",
        )
    )
    status = "pass" if all(item["status"] == "pass" for item in checks) else "review_required"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "queries": selected_queries,
        "checks": checks,
        "source_summary": source_summary,
        "seed_summary": seed_summary,
        "candidate_count": len(papers),
        "candidate_titles": [paper.title for paper in papers[:8]],
        "source_health": source_health,
        "diagnostics": [*seed_diagnostics, *diagnostics],
    }


def render_paper_grade_online_probe_markdown(report: dict[str, Any]) -> str:
    source_summary = report.get("source_summary") if isinstance(report.get("source_summary"), dict) else {}
    seed_summary = report.get("seed_summary") if isinstance(report.get("seed_summary"), dict) else {}
    lines = [
        f"# Paper-grade Online Probe：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 检索式：{', '.join(_string_list(report.get('queries'))) or '-'}",
        f"- 候选文献：{report.get('candidate_count', 0)}",
        f"- 来源成功：{source_summary.get('successful_sources', 0)}/{source_summary.get('configured_sources', 0)}",
        f"- Seed 元数据解析：{seed_summary.get('metadata_resolved_seed_papers', 0)}/{seed_summary.get('strong_seed_papers', 0)}",
        "",
        "## Checks",
        "| Check | Status | Detail | Action |",
        "| --- | --- | --- | --- |",
    ]
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    for item in checks:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("name") or "")),
                        _cell(str(item.get("status") or "")),
                        _cell(str(item.get("detail") or "")),
                        _cell(str(item.get("action") or "-")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Candidate Titles"])
    titles = _string_list(report.get("candidate_titles"))
    lines.extend(f"- {item}" for item in titles) if titles else lines.append("- 无")
    lines.extend(["", "## Diagnostics"])
    diagnostics = _string_list(report.get("diagnostics"))
    lines.extend(f"- {item}" for item in diagnostics[:40]) if diagnostics else lines.append("- 无")
    return "\n".join(lines)


def _selected_probe_queries(topic: str, literature: LiteratureConfig, queries: list[str] | None) -> list[str]:
    values = [*(queries or []), *literature.extra_search_queries, topic]
    result: list[str] = []
    for value in values:
        query = " ".join(str(value or "").split()).strip()
        if query and query not in result:
            result.append(query)
        if len(result) >= max(1, literature.max_search_queries):
            break
    return result or [topic]


def _seed_resolver(client: Any) -> Callable[[str], Paper | None]:
    resolver = getattr(client, "resolve_doi_metadata", None)
    if callable(resolver):
        return resolver
    return client.resolve_crossref_doi


def _source_summary(literature: LiteratureConfig, source_health: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [
        item
        for item in source_health
        if str(item.get("status") or "") in {"ok", "partial"} and int(item.get("returned") or 0) > 0
    ]
    return {
        "provider": literature.provider,
        "configured_sources": len([source for source in literature.sources if str(source).strip()]),
        "probed_sources": len(source_health),
        "successful_sources": len(successful),
        "rate_limited_sources": len([item for item in source_health if item.get("rate_limited") is True or str(item.get("status") or "") == "rate_limited"]),
        "failed_sources": len([item for item in source_health if str(item.get("status") or "") == "failed"]),
        "returned": sum(int(item.get("returned") or 0) for item in source_health),
    }


def _seed_summary(seed_papers: list[Paper], diagnostics: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for paper in seed_papers:
        metadata_sources = _metadata_sources(paper)
        rows.append(
            {
                "title": paper.title,
                "doi": paper.doi,
                "url": paper.url,
                "strong": bool(paper.doi or paper.url),
                "metadata_resolved": bool(metadata_sources),
                "metadata_sources": metadata_sources,
            }
        )
    return {
        "total_seed_papers": len(seed_papers),
        "strong_seed_papers": sum(1 for item in rows if item["strong"]),
        "metadata_resolved_seed_papers": sum(1 for item in rows if item["metadata_resolved"]),
        "metadata_unresolved_doi_url_seed_papers": sum(1 for item in rows if item["strong"] and not item["metadata_resolved"]),
        "items": rows,
        "diagnostics": diagnostics,
    }


def _source_checks(summary: dict[str, Any], paper_grade: PaperGradeConfig) -> list[dict[str, Any]]:
    configured = int(summary.get("configured_sources") or 0)
    successful = int(summary.get("successful_sources") or 0)
    min_configured = max(1, int(paper_grade.min_literature_sources or 0))
    min_successful = max(1, int(paper_grade.min_successful_literature_sources or 0))
    return [
        _check(
            "online_source_count",
            "pass" if configured >= min_configured else "fail",
            f"configured_sources={configured}/{min_configured}",
            f"Configure at least {min_configured} online literature sources.",
        ),
        _check(
            "online_source_success",
            "pass" if successful >= min_successful else "fail",
            f"successful_sources={successful}/{min_successful}",
            f"At least {min_successful} sources should return candidates before a paper-grade run.",
        ),
    ]


def _seed_checks(summary: dict[str, Any], paper_grade: PaperGradeConfig) -> list[dict[str, Any]]:
    strong = int(summary.get("strong_seed_papers") or 0)
    resolved = int(summary.get("metadata_resolved_seed_papers") or 0)
    min_strong = max(1, int(paper_grade.min_seed_papers or 0))
    min_resolved = max(1, int(paper_grade.min_doi_url_seed_papers or 0))
    return [
        _check(
            "doi_url_seed_count",
            "pass" if strong >= min_strong else "fail",
            f"strong_seed_papers={strong}/{min_strong}",
            f"Provide at least {min_strong} DOI/URL seed papers.",
        ),
        _check(
            "doi_seed_metadata_resolution",
            "pass" if resolved >= min_resolved else "fail",
            f"metadata_resolved_seed_papers={resolved}/{min_resolved}",
            f"Use at least {min_resolved} DOI/URL seed papers that resolve to Crossref/online/offline metadata.",
        ),
    ]


def _metadata_sources(paper: Paper) -> list[str]:
    sources: list[str] = []
    for source in [*(paper.sources or []), paper.source]:
        value = str(source or "").strip()
        if value and value != "manual_seed" and value not in sources:
            sources.append(value)
    return sources


def _check(name: str, status: str, detail: str, action: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "action": action}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _safe_diagnostic(value: Exception | str, literature: LiteratureConfig) -> str:
    text = str(value)
    for secret in _diagnostic_secrets(literature):
        text = text.replace(secret, "***")
    text = re.sub(r"(?i)(api[_-]?key=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(mailto=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(email=)[^&\s]+", r"\1***", text)
    text = re.sub(r"(?i)(x-api-key['\"]?\s*[:=]\s*)[^,\s}]+", r"\1***", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", text)
    return text


def _safe_diagnostics(values: list[str], literature: LiteratureConfig) -> list[str]:
    return [_safe_diagnostic(value, literature) for value in values]


def _safe_source_health_item(item: dict[str, Any], literature: LiteratureConfig) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in item.items():
        safe[key] = _safe_source_health_value(value, literature)
    return safe


def _safe_source_health_value(value: Any, literature: LiteratureConfig) -> Any:
    if isinstance(value, str):
        return _safe_diagnostic(value, literature)
    if isinstance(value, list):
        return [_safe_source_health_value(entry, literature) for entry in value]
    if isinstance(value, dict):
        return _safe_source_health_item(value, literature)
    return value


def _diagnostic_secrets(literature: LiteratureConfig) -> list[str]:
    values = [
        literature.semantic_scholar_api_key,
        literature.openalex_api_key,
        literature.contact_email,
        os.environ.get(literature.semantic_scholar_api_key_env, ""),
        os.environ.get(literature.openalex_api_key_env, ""),
        os.environ.get(literature.contact_email_env, ""),
    ]
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if len(text) >= 4 and text not in result:
            result.append(text)
    return result
