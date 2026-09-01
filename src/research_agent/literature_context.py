from __future__ import annotations

from dataclasses import replace
from typing import Any
import re

from .models import (
    CitationEntry,
    ClaimSupport,
    EvidenceChunk,
    FullTextCorpus,
    LiteratureContext,
    LiteratureReview,
    Paper,
    ReviewGate,
)


def build_literature_context(review: LiteratureReview, fulltext_corpus: FullTextCorpus | None = None) -> LiteratureContext:
    citations = [_citation_from_paper(paper, index) for index, paper in enumerate(review.papers, start=1)]
    key_by_title = {citation.title: citation.key for citation in citations}
    fulltext_start = len(citations) + 1
    if fulltext_corpus is not None:
        citations.extend(_citations_from_fulltext(fulltext_corpus, start=fulltext_start))
    chunks = _build_chunks(review.papers, key_by_title)
    if fulltext_corpus is not None:
        chunks.extend(_chunks_from_fulltext(fulltext_corpus, chunk_start=len(chunks) + 1, citation_start=fulltext_start))
    claim_support = _build_claim_support(review, chunks)
    gate = _build_review_gate(review, citations, chunks, claim_support, fulltext_corpus)
    return LiteratureContext(
        topic=review.topic,
        citations=citations,
        chunks=chunks,
        claim_support=claim_support,
        review_gate=gate,
    )


def apply_literature_audits_to_context(
    context: LiteratureContext,
    quality_report: dict[str, Any] | None = None,
    metadata_report: dict[str, Any] | None = None,
    coverage_report: dict[str, Any] | None = None,
    evidence_mix_report: dict[str, Any] | None = None,
    rescue_report: dict[str, Any] | None = None,
    seed_intake_report: dict[str, Any] | None = None,
    evidence_contract_report: dict[str, Any] | None = None,
    gate_decision_report: dict[str, Any] | None = None,
) -> LiteratureContext:
    gate = context.review_gate
    warnings = list(gate.warnings)
    required_actions = list(gate.required_actions)

    quality = _quality_dict(quality_report)
    metadata = metadata_report if isinstance(metadata_report, dict) else {}
    coverage = coverage_report if isinstance(coverage_report, dict) else {}
    evidence_mix = evidence_mix_report if isinstance(evidence_mix_report, dict) else {}
    rescue = rescue_report if isinstance(rescue_report, dict) else {}
    seed_intake = seed_intake_report if isinstance(seed_intake_report, dict) else {}
    evidence_contract = evidence_contract_report if isinstance(evidence_contract_report, dict) else {}
    gate_decision = gate_decision_report if isinstance(gate_decision_report, dict) else {}

    selected = _safe_int(quality.get("selected_papers"))
    total = _safe_int(quality.get("total_papers"))
    quality_warnings = _as_list(quality.get("warnings"))
    confidence_status = str(quality.get("confidence_status") or "")
    confidence_score = _safe_float(quality.get("confidence_score"))
    quality_actions = _as_list(quality.get("recommended_actions"))
    if quality and selected < 5:
        warnings.append(f"质量筛选后保留文献 {selected}/{total} 篇，证据池偏小。")
        required_actions.append("批准前检查 01-literature-quality.md，补充高相关 seed paper 或扩大检索式。")
    if quality_warnings:
        warnings.extend(str(item) for item in quality_warnings[:4])
    if confidence_status in {"weak", "block"}:
        warnings.append(f"文献证据置信度未通过：{confidence_status}，score={confidence_score:.3f}。")
        required_actions.append("批准前处理 01-literature-quality.md 的证据置信度问题，或在 approval notes 写明人工豁免理由。")
    elif confidence_status == "review_required":
        warnings.append(f"文献证据置信度需要人工复核：score={confidence_score:.3f}。")
    if quality_actions:
        required_actions.extend(str(item) for item in quality_actions[:4])

    metadata_status = str(metadata.get("status") or "")
    metadata_score = _safe_float(metadata.get("verifiability_score"))
    metadata_blocked = _safe_int(metadata.get("blocked"))
    metadata_review = _safe_int(metadata.get("review_required"))
    metadata_actions = _as_list(metadata.get("required_actions"))
    metadata_warnings = _as_list(metadata.get("warnings"))
    if metadata_status in {"block", "literature_repair_required"} or metadata_blocked:
        warnings.append(f"文献 metadata 审计未通过：{metadata_status or 'unknown'}，verifiability={metadata_score:.3f}，blocked={metadata_blocked}。")
        required_actions.append("批准前处理 01-literature-metadata-audit.md；移除或替换 metadata 不可核验文献。")
    elif metadata_status == "review_required" or metadata_review:
        warnings.append(f"文献 metadata 需要人工复核：review_required={metadata_review}，verifiability={metadata_score:.3f}。")
    if metadata_actions:
        required_actions.extend(str(item) for item in metadata_actions[:4])
    if metadata_warnings:
        warnings.extend(str(item) for item in metadata_warnings[:4])

    coverage_status = str(coverage.get("status") or "")
    coverage_ratio = _safe_float(coverage.get("coverage_ratio"))
    coverage_actions = _as_list(coverage.get("required_actions"))
    if coverage_status in {"block", "needs_literature", "needs_coverage"}:
        warnings.append(f"文献 baseline/benchmark 覆盖未通过：{coverage_status}，coverage_ratio={coverage_ratio:.2f}。")
        required_actions.append("批准前处理 01-literature-coverage.md 的缺失 facet，特别是 baseline 和 benchmark。")
        required_actions.extend(str(item) for item in coverage_actions[:3])

    evidence_mix_status = str(evidence_mix.get("status") or "")
    evidence_mix_score = _safe_float(evidence_mix.get("mix_score"))
    evidence_mix_actions = _as_list(evidence_mix.get("required_actions"))
    if evidence_mix_status in {"block", "needs_evidence_upgrade"}:
        warnings.append(f"文献证据组合审计未通过：{evidence_mix_status}，mix_score={evidence_mix_score:.3f}。")
        required_actions.append("批准前处理 01-literature-evidence-mix.md；补齐综述/高引用、benchmark/dataset、baseline/method 和近期文献 anchor。")
        required_actions.extend(str(item) for item in evidence_mix_actions[:4])
    elif evidence_mix_status == "review_required":
        warnings.append(f"文献证据组合需要人工复核：mix_score={evidence_mix_score:.3f}。")
        required_actions.extend(str(item) for item in evidence_mix_actions[:2])

    rescue_status = str(rescue.get("status") or "")
    rescue_actions = _as_list(rescue.get("required_actions"))
    rescue_queries = _as_list(rescue.get("rescue_queries"))
    if rescue_status in {"block", "needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        warnings.append(f"文献补检索计划仍需处理：{rescue_status}，候选补检索式 {len(rescue_queries)} 条。")
        required_actions.append("批准前检查 01-literature-rescue-plan.md；若状态不是 pass，应补检索或记录明确人工豁免理由。")
        required_actions.extend(str(item) for item in rescue_actions[:3])

    seed_status = str(seed_intake.get("status") or "")
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    seed_actions = _as_list(seed_intake.get("required_actions"))
    seed_warnings = _as_list(seed_intake.get("warnings"))
    if seed_status in {"block", "review_required"}:
        warnings.append(f"人工 seed intake 需要处理：{seed_status}，curated={_safe_int(seed_intake.get('curated_seed_papers'))}/{_safe_int(seed_intake.get('total_seed_entries'))}。")
        required_actions.append("批准前检查 01-seed-paper-intake.md，确认人工 seed 已进入 curated context 或写明豁免理由。")
        required_actions.extend(str(item) for item in seed_actions[:3])
        warnings.extend(str(item) for item in seed_warnings[:3])
    elif seed_role_status == "review_required":
        missing_roles = seed_intake.get("missing_curated_seed_roles") if isinstance(seed_intake.get("missing_curated_seed_roles"), list) else []
        warnings.append("人工 seed 进入 curated context 的角色覆盖不足：" + ", ".join(str(item) for item in missing_roles[:4]) + "。")
        required_actions.append("批准前检查 01-seed-paper-intake.md；补齐 review/survey、benchmark/dataset、baseline/method、recent work 中至少 3 类 seed，或写明人工豁免理由。")
        required_actions.extend(str(item) for item in seed_actions[:2])
        warnings.extend(str(item) for item in seed_warnings[:2])

    evidence_contract_status = str(evidence_contract.get("status") or "")
    evidence_contract_blocks = _as_list(evidence_contract.get("blocking_issues"))
    evidence_contract_reviews = _as_list(evidence_contract.get("review_reasons"))
    evidence_contract_actions = _as_list(evidence_contract.get("required_actions"))
    if evidence_contract_status == "block":
        warnings.append(f"文献证据契约阻断：{len(evidence_contract_blocks)} 个阻断原因。")
        required_actions.append("批准前处理 01-literature-evidence-contract.md；状态为 block 时不得进入 idea/实验。")
    elif evidence_contract_status == "review_required":
        warnings.append(f"文献证据契约需要人工复核：{len(evidence_contract_reviews)} 个复核原因。")
        required_actions.append("批准前检查 01-literature-evidence-contract.md，并在 approval notes 写明核对过的 DOI/URL、摘要/全文和剩余风险。")
    required_actions.extend(str(item) for item in evidence_contract_actions[:4])

    gate_decision_status = str(gate_decision.get("status") or "")
    gate_blocking = _as_list(gate_decision.get("blocking_reasons"))
    gate_reviews = _as_list(gate_decision.get("review_reasons"))
    gate_actions = _as_list(gate_decision.get("required_actions"))
    if gate_decision_status == "block":
        warnings.append(f"文献证据总门禁阻断：{len(gate_blocking)} 个阻断原因。")
        required_actions.append("批准前处理 01-literature-gate-decision.md；状态为 block 时不得进入 idea/实验。")
    elif gate_decision_status == "review_required":
        warnings.append(f"文献证据总门禁需要人工复核：{len(gate_reviews)} 个复核原因。")
        required_actions.append("批准前检查 01-literature-gate-decision.md，并在 approval notes 写明核对内容和剩余风险。")
    required_actions.extend(str(item) for item in gate_actions[:4])

    status = _gate_status(warnings, coverage_status, rescue_status, confidence_status, seed_status, metadata_status, metadata_blocked, evidence_mix_status, gate_decision_status, evidence_contract_status)
    return replace(
        context,
        review_gate=ReviewGate(
            status=status,
            warnings=_unique([str(item) for item in warnings if str(item).strip()]),
            required_actions=_unique([str(item) for item in required_actions if str(item).strip()]),
        ),
    )


def apply_citation_audit_to_context(context: LiteratureContext, citation_audit: Any) -> LiteratureContext:
    audit = _citation_audit_dict(citation_audit)
    if not audit:
        return context
    gate = context.review_gate
    warnings = list(gate.warnings)
    required_actions = list(gate.required_actions)
    integrity_status = str(audit.get("integrity_status") or "")
    integrity_score = _safe_float(audit.get("integrity_score"))
    blocked = _safe_int(audit.get("blocked_citations"))
    review_required = _safe_int(audit.get("review_required"))
    if integrity_status in {"block", "review_required"}:
        warnings.append(f"引用完整性审计状态：{integrity_status}，score={integrity_score:.3f}。")
        required_actions.append("批准前检查 01-citation-audit.md，修复 block 引用并人工核对 review_required 引用。")
    if blocked:
        warnings.append(f"存在 {blocked} 条阻断引用，不能直接作为 idea 或论文证据。")
    elif review_required:
        warnings.append(f"存在 {review_required} 条引用需要人工核对。")
    required_actions.extend(str(item) for item in _as_list(audit.get("required_actions"))[:3])
    warnings.extend(str(item) for item in _as_list(audit.get("warnings"))[:3])
    status = _citation_gate_status(gate.status, integrity_status, blocked)
    return replace(
        context,
        review_gate=ReviewGate(
            status=status,
            warnings=_unique([str(item) for item in warnings if str(item).strip()]),
            required_actions=_unique([str(item) for item in required_actions if str(item).strip()]),
        ),
    )


def render_literature_context_markdown(context: LiteratureContext) -> str:
    lines = [f"# 文献上下文包：{context.topic}", ""]
    lines.extend(["## 审核 Gate", f"状态：**{context.review_gate.status}**", ""])
    if context.review_gate.warnings:
        lines.append("警告：")
        lines.extend(f"- {item}" for item in context.review_gate.warnings)
        lines.append("")
    if context.review_gate.required_actions:
        lines.append("人工审核动作：")
        lines.extend(f"- {item}" for item in context.review_gate.required_actions)
        lines.append("")

    lines.extend(["## Claim-Support 表", "| 主张 | 类型 | 支撑强度 | 引用 |", "| --- | --- | --- | --- |"])
    for item in context.claim_support:
        citations = ", ".join(item.citation_keys) or "待补"
        lines.append(f"| {_cell(item.claim)} | {item.claim_type} | {item.support_level} | {citations} |")

    lines.extend(["", "## RAG Chunks"])
    for chunk in context.chunks:
        lines.extend(
            [
                f"### {chunk.chunk_id} [{chunk.citation_key}]",
                f"来源：{chunk.source}；相关性：{chunk.relevance:.3f}；URL：{chunk.url}",
                "",
                chunk.text,
                "",
            ]
        )

    lines.extend(["## 引用条目"])
    for citation in context.citations:
        authors = ", ".join(citation.authors) if citation.authors else "Unknown authors"
        doi = f" DOI: {citation.doi}." if citation.doi else ""
        lines.append(f"- [{citation.key}] {authors}. {citation.title}. {citation.venue}, {citation.year}.{doi} {citation.url}")
    return "\n".join(lines)


def render_review_gate_markdown(context: LiteratureContext) -> str:
    lines = [f"# 人工审核 Gate：{context.topic}", "", f"状态：**{context.review_gate.status}**", ""]
    lines.extend(["## 必查项"])
    lines.extend(f"- [ ] {item}" for item in context.review_gate.required_actions)
    if context.review_gate.warnings:
        lines.extend(["", "## 警告"])
        lines.extend(f"- {item}" for item in context.review_gate.warnings)
    lines.extend(["", "## Claim-Support 快照"])
    for item in context.claim_support:
        citations = ", ".join(item.citation_keys) or "待补"
        lines.append(f"- {item.support_level}：{item.claim}（{citations}）")
    return "\n".join(lines)


def export_bibtex(context: LiteratureContext) -> str:
    entries = []
    for citation in context.citations:
        fields = {
            "title": citation.title,
            "author": " and ".join(citation.authors),
            "year": str(citation.year or ""),
            "journal": citation.venue,
            "url": citation.url,
            "doi": citation.doi,
        }
        body = []
        for key, value in fields.items():
            if value:
                body.append(f"  {key} = {{{_bib_escape(value)}}}")
        entries.append("@article{" + citation.key + ",\n" + ",\n".join(body) + "\n}")
    return "\n\n".join(entries)


def export_ris(context: LiteratureContext) -> str:
    records = []
    for citation in context.citations:
        lines = ["TY  - JOUR", f"ID  - {citation.key}", f"TI  - {citation.title}"]
        for author in citation.authors:
            lines.append(f"AU  - {author}")
        if citation.year:
            lines.append(f"PY  - {citation.year}")
        if citation.venue:
            lines.append(f"JO  - {citation.venue}")
        if citation.doi:
            lines.append(f"DO  - {citation.doi}")
        if citation.url:
            lines.append(f"UR  - {citation.url}")
        lines.append("ER  -")
        records.append("\n".join(lines))
    return "\n\n".join(records)


def retrieve_chunks(context: LiteratureContext, query: str, top_k: int = 5) -> list[EvidenceChunk]:
    terms = set(_terms(query))
    scored = []
    for chunk in context.chunks:
        text = f"{chunk.title} {chunk.text}".lower()
        overlap = sum(1 for term in terms if term in text)
        scored.append((overlap + chunk.relevance * 0.1, chunk))
    return [chunk for _, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]]


def _citation_from_paper(paper: Paper, index: int) -> CitationEntry:
    key = citation_key_for_paper(paper, index)
    return CitationEntry(
        key=key,
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        venue=paper.venue,
        url=paper.url,
        doi=paper.doi,
        source=", ".join(paper.sources or [paper.source]),
    )


def citation_key_for_paper(paper: Paper, index: int) -> str:
    first = paper.authors[0] if paper.authors else "unknown"
    surname = re.sub(r"[^A-Za-z0-9]+", "", first.split()[-1].lower()) or "unknown"
    title_word = re.sub(r"[^A-Za-z0-9]+", "", (paper.title.split() or ["paper"])[0].lower()) or "paper"
    year = paper.year or "nd"
    return f"{surname}{year}{title_word}{index}"


def _build_chunks(papers: list[Paper], key_by_title: dict[str, str]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for paper in papers:
        key = key_by_title.get(paper.title, "unknown")
        text = _chunk_text(paper)
        chunks.append(
            EvidenceChunk(
                chunk_id=f"chunk-{len(chunks) + 1:03d}",
                citation_key=key,
                title=paper.title,
                text=text,
                source=", ".join(paper.sources or [paper.source]),
                url=paper.url,
                relevance=paper.relevance,
            )
        )
    return chunks


def _citations_from_fulltext(corpus: FullTextCorpus, start: int) -> list[CitationEntry]:
    citations: list[CitationEntry] = []
    for offset, document in enumerate(corpus.documents):
        if document.status != "ok" or not document.chunks:
            continue
        key = _fulltext_key(document.title, start + offset)
        citations.append(
            CitationEntry(
                key=key,
                title=document.title,
                authors=[],
                year=0,
                venue="Local fulltext",
                url=document.path,
                doi="",
                source="local_fulltext",
            )
        )
    return citations


def _chunks_from_fulltext(corpus: FullTextCorpus, chunk_start: int, citation_start: int) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    index = chunk_start
    for doc_offset, document in enumerate(corpus.documents):
        if document.status != "ok" or not document.chunks:
            continue
        key = _fulltext_key(document.title, citation_start + doc_offset)
        for chunk_index, text in enumerate(document.chunks, start=1):
            chunks.append(
                EvidenceChunk(
                    chunk_id=f"fulltext-{index:03d}",
                    citation_key=key,
                    title=document.title,
                    text=f"[local_fulltext chunk {chunk_index}; sha256={document.sha256[:12]}]\n{text}",
                    source="local_fulltext",
                    url=document.path,
                    relevance=0.75,
                )
            )
            index += 1
    return chunks


def _chunk_text(paper: Paper) -> str:
    parts = [paper.title]
    if paper.abstract:
        parts.append(paper.abstract)
    if paper.evidence_note:
        parts.append("Evidence note: " + paper.evidence_note)
    return "\n".join(parts)


def _build_claim_support(review: LiteratureReview, chunks: list[EvidenceChunk]) -> list[ClaimSupport]:
    claims: list[ClaimSupport] = []
    for claim in review.themes:
        claims.append(_support_for_claim(claim, "theme", chunks))
    for claim in review.gaps:
        claims.append(_support_for_claim(claim, "gap", chunks))
    return claims


def _support_for_claim(claim: str, claim_type: str, chunks: list[EvidenceChunk]) -> ClaimSupport:
    terms = set(_terms(claim))
    ranked: list[tuple[float, EvidenceChunk]] = []
    for chunk in chunks:
        text = f"{chunk.title} {chunk.text}".lower()
        overlap = sum(1 for term in terms if term in text)
        ranked.append((overlap + chunk.relevance * 0.05, chunk))
    top = [chunk for score, chunk in sorted(ranked, key=lambda item: item[0], reverse=True)[:3] if score > 0]
    keys = [chunk.citation_key for chunk in top]
    if len(keys) >= 2:
        level = "supported"
    elif len(keys) == 1:
        level = "weak"
    else:
        level = "unsupported"
    notes = [chunk.title for chunk in top]
    return ClaimSupport(claim=claim, claim_type=claim_type, support_level=level, citation_keys=keys, evidence_notes=notes)


def _build_review_gate(
    review: LiteratureReview,
    citations: list[CitationEntry],
    chunks: list[EvidenceChunk],
    claim_support: list[ClaimSupport],
    fulltext_corpus: FullTextCorpus | None = None,
) -> ReviewGate:
    warnings: list[str] = []
    if len(citations) < 5:
        warnings.append("候选文献少于 5 篇，建议扩大检索式或增加来源。")
    if sum(1 for citation in citations if citation.doi) < max(1, len(citations) // 3):
        warnings.append("带 DOI 的文献比例偏低，引用导出前需人工核对。")
    unsupported = [item.claim for item in claim_support if item.support_level == "unsupported"]
    if unsupported:
        warnings.append(f"存在 {len(unsupported)} 条未支撑主张，需要补文献或删除。")
    if any("429" in item for item in review.source_diagnostics):
        warnings.append("检索源出现 429 限流，建议设置对应 API key 后重跑。")
    if fulltext_corpus is not None and fulltext_corpus.warnings:
        warnings.append(f"本地全文语料存在 {len(fulltext_corpus.warnings)} 条抽取警告，需要人工核对。")
    required_actions = [
        "逐条检查 Claim-Support 表，确认每个主题和研究空白至少有一篇可引用文献。",
        "打开 Top RAG chunks 对应 URL，人工核对摘要与题录是否匹配。",
        "若使用本地全文 chunk，核对 01-fulltext-corpus.md 中的文件 hash、抽取状态和版权/许可。",
        "将 BibTeX/RIS 导入 Zotero/EndNote 前核对 DOI、年份、作者和 venue。",
        "进入 idea 生成前，删除弱相关或不可引用的候选文献。",
    ]
    status = "review_required" if warnings else "pass"
    return ReviewGate(status=status, warnings=warnings, required_actions=required_actions)


def _terms(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "that", "this", "into", "using", "from", "研究", "文献", "系统"}
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return [term.replace("-", "_") for term in terms if term not in stop]


def _fulltext_key(title: str, index: int) -> str:
    title_word = re.sub(r"[^A-Za-z0-9]+", "", (title.split() or ["fulltext"])[0].lower()) or "fulltext"
    return f"localfulltext{index}{title_word}"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _gate_status(
    warnings: list[str],
    coverage_status: str,
    rescue_status: str,
    confidence_status: str = "",
    seed_status: str = "",
    metadata_status: str = "",
    metadata_blocked: int = 0,
    evidence_mix_status: str = "",
    gate_decision_status: str = "",
    evidence_contract_status: str = "",
) -> str:
    if gate_decision_status == "block" or evidence_contract_status == "block":
        return "block"
    if coverage_status == "block" or rescue_status == "block" or seed_status == "block" or evidence_mix_status == "block":
        return "block"
    if metadata_status == "block" or metadata_blocked:
        return "block"
    if confidence_status == "block":
        return "block"
    if metadata_status == "literature_repair_required":
        return "literature_repair_required"
    if confidence_status == "weak":
        return "literature_repair_required"
    if rescue_status in {"needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        return "literature_repair_required"
    if evidence_mix_status == "needs_evidence_upgrade":
        return "literature_repair_required"
    if coverage_status in {"needs_literature", "needs_coverage"}:
        return "literature_repair_required"
    if gate_decision_status == "review_required" or evidence_contract_status == "review_required":
        return "literature_repair_required"
    return "review_required" if warnings else "pass"


def _citation_gate_status(current_status: str, integrity_status: str, blocked: int) -> str:
    if current_status == "block" or integrity_status == "block" or blocked:
        return "block"
    if current_status == "literature_repair_required":
        return current_status
    if integrity_status == "review_required":
        return "review_required"
    return current_status


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _citation_audit_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {
        "integrity_status": getattr(value, "integrity_status", ""),
        "integrity_score": getattr(value, "integrity_score", 0.0),
        "blocked_citations": getattr(value, "blocked_citations", 0),
        "review_required": getattr(value, "review_required", 0),
        "warnings": getattr(value, "warnings", []),
        "required_actions": getattr(value, "required_actions", []),
    }


def _quality_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {
        "selected_papers": getattr(value, "selected_papers", 0),
        "total_papers": getattr(value, "total_papers", 0),
        "warnings": getattr(value, "warnings", []),
        "confidence_score": getattr(value, "confidence_score", 0.0),
        "confidence_status": getattr(value, "confidence_status", ""),
        "recommended_actions": getattr(value, "recommended_actions", []),
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _bib_escape(value: str) -> str:
    return value.replace("{", "\\{").replace("}", "\\}")
