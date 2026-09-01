from __future__ import annotations

import re

from .models import CitationAuditItem, CitationAuditReport, CitationEntry, LiteratureContext
from .artifacts import cell as _cell


def audit_citations(context: LiteratureContext) -> CitationAuditReport:
    support_counts = _claim_support_counts(context)
    items = [_audit_citation(citation, support_counts.get(citation.key, 0)) for citation in context.citations]
    total = len(items)
    usable = sum(1 for item in items if item.decision == "usable")
    review = sum(1 for item in items if item.decision == "review")
    blocked = sum(1 for item in items if item.decision == "block")
    doi_count = sum(1 for item in items if item.doi)
    url_count = sum(1 for item in items if item.url)
    layers = _integrity_layers(context, items)
    integrity_score = _integrity_score(layers)
    integrity_status = _integrity_status(integrity_score, blocked, review, total)
    warnings = _warnings(items, integrity_status, integrity_score, layers)
    return CitationAuditReport(
        topic=context.topic,
        total_citations=total,
        usable_citations=usable,
        review_required=review,
        blocked_citations=blocked,
        doi_coverage=round(doi_count / total, 3) if total else 0.0,
        url_coverage=round(url_count / total, 3) if total else 0.0,
        items=items,
        warnings=warnings,
        required_actions=_required_actions(items, warnings),
        integrity_score=integrity_score,
        integrity_status=integrity_status,
        integrity_layers=layers,
    )


def render_citation_audit_markdown(report: CitationAuditReport) -> str:
    lines = [
        f"# 引用审计：{report.topic}",
        "",
        f"- 引用条目：{report.total_citations}",
        f"- 可直接使用：{report.usable_citations}",
        f"- 需人工核对：{report.review_required}",
        f"- 阻断引用：{report.blocked_citations}",
        f"- DOI 覆盖率：{report.doi_coverage:.1%}",
        f"- URL 覆盖率：{report.url_coverage:.1%}",
        f"- 引用完整性：{report.integrity_status or '-'}（{report.integrity_score:.3f}）",
        "",
    ]
    if report.integrity_layers:
        lines.extend(["## 完整性分层", "| 层级 | 值 |", "| --- | ---: |"])
        for key, value in report.integrity_layers.items():
            lines.append(f"| {_cell(str(key))} | {_cell(str(value))} |")
        lines.append("")
    if report.warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in report.warnings)
        lines.append("")
    lines.extend(["## 必查动作"])
    lines.extend(f"- [ ] {item}" for item in report.required_actions)
    lines.extend(
        [
            "",
            "## 引用审计表",
            "| Key | 决策 | 风险 | 年份 | 来源 | Locator | 来源一致性 | Claim 支撑 | DOI | URL | 标题 | 问题 |",
            "| --- | --- | --- | ---: | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for item in report.items:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.citation_key),
                    item.decision,
                    item.risk,
                    str(item.year or ""),
                    _cell(item.source or "-"),
                    item.locator_status or "-",
                    item.source_agreement or "-",
                    str(item.claim_support_count),
                    _cell(item.doi or "-"),
                    _cell(item.url or "-"),
                    _cell(item.title),
                    _cell("；".join(item.issues) or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _audit_citation(citation: CitationEntry, claim_support_count: int = 0) -> CitationAuditItem:
    issues: list[str] = []
    if not citation.title.strip():
        issues.append("missing title")
    if not citation.authors:
        issues.append("missing authors")
    if not citation.year:
        issues.append("missing year")
    if not citation.doi:
        issues.append("missing DOI")
    elif not _looks_like_doi(citation.doi):
        issues.append("invalid DOI format")
    is_local_fulltext = "local_fulltext" in citation.source
    if not citation.url:
        issues.append("missing URL")
    elif not is_local_fulltext and not citation.url.startswith(("http://", "https://")):
        issues.append("invalid URL")
    if "manual_seed" in citation.source:
        issues.append("manual seed needs verification")
    if citation.venue.lower() in {"crossref", "manual seed", "dataset", ""}:
        issues.append("weak venue metadata")
    locator_status = _locator_status(citation)
    source_agreement = _source_agreement(citation.source)
    if source_agreement == "single_weak_source":
        issues.append("single weak source")
    if claim_support_count == 0:
        issues.append("not used in claim support")

    decision = _decision(issues)
    return CitationAuditItem(
        citation_key=citation.key,
        title=citation.title,
        decision=decision,
        risk="high" if decision == "block" else "medium" if decision == "review" else "low",
        issues=issues,
        doi=citation.doi,
        url=citation.url,
        year=citation.year,
        source=citation.source,
        locator_status=locator_status,
        source_agreement=source_agreement,
        claim_support_count=claim_support_count,
    )


def _decision(issues: list[str]) -> str:
    hard = {"missing title", "invalid URL", "invalid DOI format"}
    if "missing DOI" in issues and "missing URL" in issues:
        return "block"
    if any(issue in hard for issue in issues):
        return "block"
    if "not used in claim support" in issues and len(issues) == 1:
        return "review"
    if issues:
        return "review"
    return "usable"


def _warnings(items: list[CitationAuditItem], integrity_status: str, integrity_score: float, layers: dict[str, float | int | str]) -> list[str]:
    warnings: list[str] = []
    blocked = [item for item in items if item.decision == "block"]
    review = [item for item in items if item.decision == "review"]
    missing_doi = [item for item in items if "missing DOI" in item.issues]
    manual = [item for item in items if "manual seed needs verification" in item.issues]
    if blocked:
        warnings.append(f"存在 {len(blocked)} 条阻断引用，进入 idea 前应替换、补 URL/DOI 或删除。")
    if review:
        warnings.append(f"存在 {len(review)} 条引用需要人工核对元数据。")
    if missing_doi:
        warnings.append(f"存在 {len(missing_doi)} 条引用缺 DOI，导入引用管理器前需核对。")
    if manual:
        warnings.append(f"存在 {len(manual)} 条人工种子引用，需确认题录和摘要是否匹配。")
    if integrity_status == "block":
        warnings.append(f"引用完整性为 block（score={integrity_score:.3f}），批准前必须修复阻断引用或补充可核验文献。")
    elif integrity_status == "review_required":
        warnings.append(f"引用完整性需要人工复核（score={integrity_score:.3f}）。")
    if _safe_float(layers.get("claim_support_coverage")) < 0.8:
        warnings.append("Claim-Support 表中可用引用覆盖不足，后续 idea/论文可能引用弱证据。")
    return warnings


def _required_actions(items: list[CitationAuditItem], warnings: list[str]) -> list[str]:
    actions = [
        "逐条打开 DOI/URL，核对标题、作者、年份、venue 与摘要。",
        "对 decision=block 的引用，补齐稳定 URL/DOI 或从候选文献中删除。",
        "对 manual_seed 引用，确认用户输入和解析题录一致后再进入 idea 阶段。",
        "将 BibTeX/RIS 导入 Zotero/EndNote 前处理所有 missing DOI、missing year 和 missing authors。",
        "优先保留 multi_source 或 trusted_single_source 条目，替换 single_weak_source 且缺 DOI/URL 的候选。",
    ]
    if not items:
        actions.insert(0, "当前没有可审计引用，必须重新检索或添加人工种子文献。")
    elif not warnings:
        actions.append("抽查至少 2 条高相关引用，确认摘要确实支撑 Claim-Support 表。")
    return actions


def _claim_support_counts(context: LiteratureContext) -> dict[str, int]:
    counts: dict[str, int] = {}
    for support in context.claim_support:
        for key in support.citation_keys:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _integrity_layers(context: LiteratureContext, items: list[CitationAuditItem]) -> dict[str, float | int | str]:
    total = len(items)
    if not total:
        return {
            "metadata_pass_rate": 0.0,
            "locator_coverage": 0.0,
            "source_agreement_rate": 0.0,
            "claim_support_coverage": 0.0,
            "supported_claims": 0,
            "total_claims": len(context.claim_support),
        }
    blocked_keys = {item.citation_key for item in items if item.decision == "block"}
    usable_or_review_keys = {item.citation_key for item in items if item.decision in {"usable", "review"}}
    source_good = sum(1 for item in items if item.source_agreement in {"multi_source", "trusted_single_source", "local_fulltext"})
    locator_good = sum(1 for item in items if item.locator_status in {"doi_and_url", "doi_only", "url_only", "local_path"})
    metadata_good = sum(1 for item in items if item.decision != "block")
    supported_claims = 0
    for support in context.claim_support:
        keys = set(support.citation_keys)
        if support.support_level != "unsupported" and keys and keys <= usable_or_review_keys and not keys & blocked_keys:
            supported_claims += 1
    total_claims = len(context.claim_support)
    return {
        "metadata_pass_rate": round(metadata_good / total, 3),
        "locator_coverage": round(locator_good / total, 3),
        "source_agreement_rate": round(source_good / total, 3),
        "claim_support_coverage": round(supported_claims / total_claims, 3) if total_claims else 0.0,
        "supported_claims": supported_claims,
        "total_claims": total_claims,
    }


def _integrity_score(layers: dict[str, float | int | str]) -> float:
    score = (
        _safe_float(layers.get("metadata_pass_rate")) * 0.30
        + _safe_float(layers.get("locator_coverage")) * 0.25
        + _safe_float(layers.get("source_agreement_rate")) * 0.20
        + _safe_float(layers.get("claim_support_coverage")) * 0.25
    )
    return round(max(0.0, min(1.0, score)), 3)


def _integrity_status(score: float, blocked: int, review: int, total: int) -> str:
    if not total:
        return "block"
    if blocked or score < 0.55:
        return "block"
    if review or score < 0.82:
        return "review_required"
    return "pass"


def _locator_status(citation: CitationEntry) -> str:
    has_doi = bool(citation.doi and _looks_like_doi(citation.doi))
    has_url = bool(citation.url and (citation.url.startswith(("http://", "https://")) or citation.source == "local_fulltext"))
    if citation.source == "local_fulltext" and citation.url:
        return "local_path"
    if has_doi and has_url:
        return "doi_and_url"
    if has_doi:
        return "doi_only"
    if has_url:
        return "url_only"
    return "missing_locator"


def _source_agreement(source: str) -> str:
    values = {item.strip().lower() for item in re.split(r",\s*", source or "") if item.strip()}
    if "local_fulltext" in values:
        return "local_fulltext"
    if len(values) >= 2:
        return "multi_source"
    trusted = {"semantic_scholar", "openalex", "arxiv", "pubmed"}
    weak = {"crossref", "manual_seed", "offline", "local_fulltext", ""}
    if values & trusted:
        return "trusted_single_source"
    if values <= weak:
        return "single_weak_source"
    return "single_source"


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _looks_like_doi(value: str) -> bool:
    return bool(re.match(r"^10\.\d{4,9}/\S+$", value.strip(), flags=re.I))


