from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .config import PaperGradeConfig


LITERATURE_GATE_DECISION_JSON = "01-literature-gate-decision.json"
LITERATURE_GATE_DECISION_MD = "01-literature-gate-decision.md"
LITERATURE_GATE_DECISION_SCHEMA_VERSION = 7
PAPER_GRADE_MIN_SELECTED_PAPERS = 5


def build_literature_context_gate_report(context: Any) -> dict[str, Any]:
    if context is None:
        return {}
    if isinstance(context, dict):
        citations = context.get("citations")
        chunks = context.get("chunks")
        claim_support = context.get("claim_support")
        return {
            "citations": len(citations) if isinstance(citations, list) else _safe_int(citations),
            "chunks": len(chunks) if isinstance(chunks, list) else _safe_int(chunks),
            "claim_support": len(claim_support) if isinstance(claim_support, list) else _safe_int(claim_support),
        }
    citations = getattr(context, "citations", None)
    chunks = getattr(context, "chunks", None)
    claim_support = getattr(context, "claim_support", None)
    return {
        "citations": len(citations) if isinstance(citations, list) else _safe_int(citations),
        "chunks": len(chunks) if isinstance(chunks, list) else _safe_int(chunks),
        "claim_support": len(claim_support) if isinstance(claim_support, list) else _safe_int(claim_support),
    }


def write_literature_gate_decision_artifacts(
    *,
    topic: str,
    quality_report: dict[str, Any] | Any,
    source_health_report: dict[str, Any] | None,
    query_execution_report: dict[str, Any] | None,
    rerank_report: dict[str, Any] | None,
    coverage_report: dict[str, Any] | None,
    evidence_mix_report: dict[str, Any] | None,
    rescue_report: dict[str, Any] | None,
    rescue_execution_report: dict[str, Any] | None,
    seed_intake_report: dict[str, Any] | None,
    evidence_contract_report: dict[str, Any] | None = None,
    citation_audit_report: dict[str, Any] | Any | None,
    context_report: dict[str, Any] | None = None,
    citation_grounding_report: dict[str, Any] | Any | None = None,
    paper_grade_config: PaperGradeConfig | None = None,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_gate_decision(
        topic=topic,
        quality_report=quality_report,
        source_health_report=source_health_report,
        query_execution_report=query_execution_report,
        rerank_report=rerank_report,
        coverage_report=coverage_report,
        evidence_mix_report=evidence_mix_report,
        rescue_report=rescue_report,
        rescue_execution_report=rescue_execution_report,
        seed_intake_report=seed_intake_report,
        evidence_contract_report=evidence_contract_report,
        citation_audit_report=citation_audit_report,
        context_report=context_report,
        citation_grounding_report=citation_grounding_report,
        paper_grade_config=paper_grade_config,
    )
    write_json(run_dir / LITERATURE_GATE_DECISION_JSON, report)
    write_text(run_dir / LITERATURE_GATE_DECISION_MD, render_literature_gate_decision_markdown(report))
    return report


def build_literature_gate_decision(
    *,
    topic: str,
    quality_report: dict[str, Any] | Any,
    source_health_report: dict[str, Any] | None = None,
    query_execution_report: dict[str, Any] | None = None,
    rerank_report: dict[str, Any] | None = None,
    coverage_report: dict[str, Any] | None = None,
    evidence_mix_report: dict[str, Any] | None = None,
    rescue_report: dict[str, Any] | None = None,
    rescue_execution_report: dict[str, Any] | None = None,
    seed_intake_report: dict[str, Any] | None = None,
    evidence_contract_report: dict[str, Any] | None = None,
    citation_audit_report: dict[str, Any] | Any | None = None,
    context_report: dict[str, Any] | None = None,
    citation_grounding_report: dict[str, Any] | Any | None = None,
    paper_grade_config: PaperGradeConfig | None = None,
) -> dict[str, Any]:
    quality = _report_dict(quality_report)
    source_health = source_health_report if isinstance(source_health_report, dict) else {}
    query_execution = query_execution_report if isinstance(query_execution_report, dict) else {}
    rerank = rerank_report if isinstance(rerank_report, dict) else {}
    coverage = coverage_report if isinstance(coverage_report, dict) else {}
    evidence_mix = evidence_mix_report if isinstance(evidence_mix_report, dict) else {}
    rescue = rescue_report if isinstance(rescue_report, dict) else {}
    rescue_execution = rescue_execution_report if isinstance(rescue_execution_report, dict) else {}
    seed_intake = seed_intake_report if isinstance(seed_intake_report, dict) else {}
    evidence_contract = evidence_contract_report if isinstance(evidence_contract_report, dict) else {}
    citation = _report_dict(citation_audit_report)
    context = context_report if isinstance(context_report, dict) else {}
    citation_grounding = _report_dict(citation_grounding_report)
    paper_grade = _paper_grade_literature_contract(quality, source_health, query_execution, seed_intake, paper_grade_config)

    signals = [
        _signal("paper_grade_literature", paper_grade["status"], None, _paper_grade_summary(paper_grade)),
        _signal("literature_quality", _quality_status(quality), quality.get("confidence_score"), _quality_summary(quality)),
        _signal("source_health", _source_health_status(source_health), None, _source_health_summary(source_health)),
        _signal("query_execution", str(query_execution.get("status") or ""), None, _query_execution_summary(query_execution)),
        _signal("rerank", str(rerank.get("status") or ""), None, _rerank_summary(rerank)),
        _signal("coverage", str(coverage.get("status") or ""), coverage.get("coverage_ratio"), _coverage_summary(coverage)),
        _signal("evidence_mix", str(evidence_mix.get("status") or ""), evidence_mix.get("mix_score"), _evidence_mix_summary(evidence_mix)),
        _signal("rescue_plan", str(rescue.get("status") or ""), None, _rescue_summary(rescue)),
        _signal("rescue_execution", str(rescue_execution.get("status") or ""), None, _rescue_execution_summary(rescue_execution)),
        _signal("seed_intake", _seed_status(seed_intake), None, _seed_summary(seed_intake)),
        _signal("evidence_contract", str(evidence_contract.get("status") or ""), None, _evidence_contract_summary(evidence_contract)),
        _signal("citation_integrity", str(citation.get("integrity_status") or ""), citation.get("integrity_score"), _citation_summary(citation)),
        _signal("rag_context", _context_status(context), None, _context_summary(context)),
        _signal("citation_grounding", str(citation_grounding.get("status") or ""), citation_grounding.get("grounding_score"), _citation_grounding_summary(citation_grounding)),
    ]
    signals = [item for item in signals if item["status"] or item["summary"]]

    blockers = _blocking_reasons(signals, quality, source_health, coverage, evidence_mix, rescue, rescue_execution, seed_intake, evidence_contract, citation, context, citation_grounding)
    review_items = _review_reasons(signals, quality, source_health, query_execution, rerank, coverage, evidence_mix, rescue, rescue_execution, seed_intake, evidence_contract, citation, context, citation_grounding)
    required_actions = _required_actions(blockers, review_items, paper_grade, quality, source_health, coverage, evidence_mix, rescue, rescue_execution, seed_intake, evidence_contract, citation, context, citation_grounding)
    status = "block" if blockers else "review_required" if review_items or required_actions else "pass"
    if not signals:
        status = "block"
        blockers.append("缺少文献质量、检索执行和引用完整性审计，不能证明文献证据可支撑后续阶段。")
        required_actions.append("重新运行文献阶段并生成 01-literature-quality、source/query、coverage、seed intake 和 citation audit。")

    return {
        "schema_version": LITERATURE_GATE_DECISION_SCHEMA_VERSION,
        "topic": topic,
        "status": status,
        "decision": "hold_for_repair" if status == "block" else "human_review_required" if status == "review_required" else "ready_for_human_approval",
        "blocks_downstream": status == "block",
        "human_approval_required": True,
        "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
        "summary": {
            "raw_papers": _safe_int(quality.get("total_papers")),
            "selected_papers": _safe_int(quality.get("selected_papers")),
            "quality_confidence": quality.get("confidence_status") or "",
            "quality_score": _safe_float(quality.get("confidence_score")),
            "source_health_status": _source_health_status(source_health),
            "query_execution_status": query_execution.get("status") or "",
            "rerank_status": rerank.get("status") or "",
            "coverage_status": coverage.get("status") or "",
            "coverage_ratio": _safe_float(coverage.get("coverage_ratio")),
            "evidence_mix_status": evidence_mix.get("status") or "",
            "evidence_mix_score": _safe_float(evidence_mix.get("mix_score")),
            "rescue_status": rescue.get("status") or "",
            "rescue_execution_status": rescue_execution.get("status") or "",
            "seed_status": seed_intake.get("status") or "",
            "seed_role_coverage_status": seed_intake.get("role_coverage_status") or "",
            "evidence_contract_status": evidence_contract.get("status") or "",
            "evidence_contract_blocking": _count_list(evidence_contract.get("blocking_issues")),
            "evidence_contract_review": _count_list(evidence_contract.get("review_reasons")),
            "evidence_contract_chunk_coverage": _safe_float((evidence_contract.get("summary") if isinstance(evidence_contract.get("summary"), dict) else {}).get("chunk_coverage")),
            "evidence_contract_substantive_chunk_coverage": _safe_float((evidence_contract.get("summary") if isinstance(evidence_contract.get("summary"), dict) else {}).get("substantive_chunk_coverage")),
            "evidence_contract_median_chunk_chars": _safe_int((evidence_contract.get("summary") if isinstance(evidence_contract.get("summary"), dict) else {}).get("median_chunk_chars")),
            "evidence_contract_locator_coverage": _safe_float((evidence_contract.get("summary") if isinstance(evidence_contract.get("summary"), dict) else {}).get("locator_coverage")),
            "citation_integrity_status": citation.get("integrity_status") or "",
            "citation_integrity_score": _safe_float(citation.get("integrity_score")),
            "context_citations": _safe_int(context.get("citations")),
            "context_chunks": _safe_int(context.get("chunks")),
            "context_claim_support": _safe_int(context.get("claim_support")),
            "citation_grounding_status": citation_grounding.get("status") or "",
            "citation_grounding_score": _safe_float(citation_grounding.get("grounding_score")),
            "citation_grounding_blocked": _safe_int(citation_grounding.get("blocked_citations")),
            "citation_grounding_review": _safe_int(citation_grounding.get("review_citations")),
            "paper_grade_literature_status": paper_grade["status"],
            "paper_grade_literature_issues": len(paper_grade["issues"]),
        },
        "paper_grade_literature": paper_grade,
        "signals": signals,
        "blocking_reasons": _unique(blockers),
        "review_reasons": _unique(review_items),
        "required_actions": _unique(required_actions),
        "approval_guidance": _approval_guidance(status),
    }


def render_literature_gate_decision_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# 文献证据总门禁：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 决策：{report.get('decision') or '-'}",
        f"- 阻断后续：{'yes' if report.get('blocks_downstream') else 'no'}",
        f"- 人工批准必需：{'yes' if report.get('human_approval_required') else 'no'}",
        f"- 原始/筛选文献：{summary.get('raw_papers', 0)}/{summary.get('selected_papers', 0)}",
        f"- 文献置信度：{summary.get('quality_confidence') or '-'} ({float(summary.get('quality_score') or 0.0):.3f})",
        f"- 覆盖/证据组合：{summary.get('coverage_status') or '-'} ({float(summary.get('coverage_ratio') or 0.0):.3f}) / {summary.get('evidence_mix_status') or '-'} ({float(summary.get('evidence_mix_score') or 0.0):.3f})",
        f"- 文献证据契约：{summary.get('evidence_contract_status') or '-'}，block/review={summary.get('evidence_contract_blocking', 0)}/{summary.get('evidence_contract_review', 0)}，chunk/substantive/locator={float(summary.get('evidence_contract_chunk_coverage') or 0.0):.3f}/{float(summary.get('evidence_contract_substantive_chunk_coverage') or 0.0):.3f}/{float(summary.get('evidence_contract_locator_coverage') or 0.0):.3f}，median chars={summary.get('evidence_contract_median_chunk_chars', 0)}",
        f"- 引用完整性：{summary.get('citation_integrity_status') or '-'} ({float(summary.get('citation_integrity_score') or 0.0):.3f})",
        f"- RAG context：citations={summary.get('context_citations', 0)}, chunks={summary.get('context_chunks', 0)}, claim_support={summary.get('context_claim_support', 0)}",
        f"- Citation grounding：{summary.get('citation_grounding_status') or '-'} ({float(summary.get('citation_grounding_score') or 0.0):.3f})，block/review={summary.get('citation_grounding_blocked', 0)}/{summary.get('citation_grounding_review', 0)}",
        f"- Paper-grade literature：{summary.get('paper_grade_literature_status') or '-'}，issues={summary.get('paper_grade_literature_issues', 0)}",
        "",
    ]
    paper_grade = report.get("paper_grade_literature") if isinstance(report.get("paper_grade_literature"), dict) else {}
    if paper_grade:
        lines.extend(["## Paper-Grade Literature"])
        lines.append(f"- 状态：{paper_grade.get('status') or '-'}")
        details = paper_grade.get("summary") if isinstance(paper_grade.get("summary"), dict) else {}
        lines.append(
            "- 契约："
            f"provider={details.get('provider') or '-'}; "
            f"sources={details.get('sources_with_success', 0)}/{details.get('configured_source_count', 0)}; "
            f"selected={details.get('selected_papers', 0)}; "
            f"seed DOI/URL/title={details.get('doi_entries', 0)}/{details.get('url_entries', 0)}/{details.get('title_only_entries', 0)}; "
            f"curated_seed={details.get('curated_seed_papers', 0)}/{details.get('total_seed_entries', 0)}; "
            f"role={details.get('seed_role_coverage_status') or '-'}"
        )
        issues = paper_grade.get("issues") if isinstance(paper_grade.get("issues"), list) else []
        lines.extend(f"- {item}" for item in issues) if issues else lines.append("- 已满足 online/auto、多源、DOI/URL seed 和 seed 角色覆盖要求。")
        suggestions = paper_grade.get("repair_suggestions") if isinstance(paper_grade.get("repair_suggestions"), list) else []
        if suggestions:
            lines.extend(["", "### Paper-Grade 修复建议", "| 类型 | 目标 | 动作 |", "| --- | --- | --- |"])
            for item in suggestions:
                if isinstance(item, dict):
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _cell(str(item.get("kind") or "")),
                                _cell(str(item.get("target") or "")),
                                _cell(str(item.get("action") or "")),
                            ]
                        )
                        + " |"
                    )
        lines.append("")
    for key, title in [("blocking_reasons", "阻断原因"), ("review_reasons", "人工复核原因"), ("required_actions", "必须动作"), ("approval_guidance", "批准指导")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            prefix = "- [ ] " if key == "required_actions" else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(["## 信号表", "| 信号 | 状态 | 分数 | 摘要 |", "| --- | --- | ---: | --- |"])
    for item in report.get("signals", []) if isinstance(report.get("signals"), list) else []:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("name") or "")),
                        _cell(str(item.get("status") or "")),
                        _cell(str(item.get("score") if item.get("score") is not None else "-")),
                        _cell(str(item.get("summary") or "")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## 使用规则",
            "- 状态为 block 时，不应批准进入 idea 或实验；先完成必须动作后重跑文献 gate。",
            "- 状态为 review_required 时，必须由人工在 approval notes 中说明已核对的证据和接受的剩余风险。",
            "- 该门禁聚合检索、重排、覆盖、seed、证据组合和 citation integrity；不替代人工阅读核心论文。",
        ]
    )
    return "\n".join(lines)


def _paper_grade_literature_contract(
    quality: dict[str, Any],
    source_health: dict[str, Any],
    query_execution: dict[str, Any],
    seed_intake: dict[str, Any],
    paper_grade_config: PaperGradeConfig | None = None,
) -> dict[str, Any]:
    thresholds = _paper_grade_thresholds(paper_grade_config)
    source_coverage = query_execution.get("source_coverage") if isinstance(query_execution.get("source_coverage"), dict) else {}
    provider = str(source_health.get("provider") or "").strip()
    configured_sources = _safe_int(source_coverage.get("configured_source_count")) or _safe_int(source_health.get("configured_source_count"))
    sources_with_success = _safe_int(source_coverage.get("sources_with_success")) or _safe_int(source_health.get("sources_with_success"))
    selected_papers = _safe_int(quality.get("selected_papers"))
    total_seed_entries = _safe_int(seed_intake.get("total_seed_entries"))
    curated_seed_papers = _safe_int(seed_intake.get("curated_seed_papers"))
    doi_entries = _safe_int(seed_intake.get("doi_entries"))
    url_entries = _safe_int(seed_intake.get("url_entries"))
    title_only_entries = _safe_int(seed_intake.get("title_only_entries"))
    metadata_resolved_seed_papers = _safe_int(seed_intake.get("metadata_resolved_seed_papers"))
    metadata_unresolved_doi_url_seed_papers = _safe_int(seed_intake.get("metadata_unresolved_doi_url_seed_papers"))
    strong_seed_entries = doi_entries + url_entries
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    seed_role_classes = _covered_seed_role_classes(seed_intake)
    issues: list[str] = []
    if provider and provider not in {"online", "auto"}:
        issues.append(f"paper-grade 文献需要 literature.provider=online/auto，当前 {provider}。")
    elif not provider:
        issues.append("paper-grade 文献缺少 provider 记录；请用新版 run-config/source-health 重新生成文献阶段。")
    if configured_sources < thresholds["min_configured_sources"]:
        issues.append(f"paper-grade 文献至少配置 {thresholds['min_configured_sources']} 个在线来源，当前 {configured_sources}。")
    if sources_with_success < thresholds["min_sources_with_success"]:
        issues.append(f"paper-grade 文献至少需要 {thresholds['min_sources_with_success']} 个来源成功返回，当前 {sources_with_success}。")
    if selected_papers < thresholds["min_selected_papers"]:
        issues.append(f"paper-grade 文献至少需要 {thresholds['min_selected_papers']} 篇 curated 文献，当前 {selected_papers}。")
    if total_seed_entries < thresholds["min_total_seed_entries"]:
        issues.append(f"paper-grade 文献至少需要 {thresholds['min_total_seed_entries']} 条人工 seed，当前 {total_seed_entries}。")
    if strong_seed_entries < thresholds["min_strong_seed_entries"]:
        issues.append(f"paper-grade 文献 seed 必须以 DOI/URL 为主，当前 DOI/URL seed {strong_seed_entries}/{thresholds['min_strong_seed_entries']} 条。")
    if metadata_resolved_seed_papers < thresholds["min_metadata_resolved_seed_papers"]:
        issues.append(f"paper-grade 文献至少需要 {thresholds['min_metadata_resolved_seed_papers']} 条 DOI/URL seed 解析到来源题录元数据，当前 {metadata_resolved_seed_papers}。")
    if title_only_entries:
        issues.append(f"paper-grade 文献不接受 title-only seed，当前 {title_only_entries} 条。")
    if curated_seed_papers < thresholds["min_curated_seed_papers"]:
        issues.append(f"paper-grade 文献至少需要 {thresholds['min_curated_seed_papers']} 条 seed 进入 curated context，当前 {curated_seed_papers}。")
    if seed_role_classes is not None:
        if seed_role_classes < thresholds["min_seed_role_classes"]:
            issues.append(f"paper-grade 文献 seed 需覆盖 review/benchmark/baseline/recent 至少 {thresholds['min_seed_role_classes']} 类，当前 {seed_role_classes} 类。")
    elif seed_role_status != "pass":
        issues.append(f"paper-grade 文献 seed 需覆盖 review/benchmark/baseline/recent 至少 {thresholds['min_seed_role_classes']} 类，当前 {seed_role_status or 'missing'}。")
    repair_suggestions = _paper_grade_literature_repair_suggestions(
        provider=provider,
        configured_sources=configured_sources,
        sources_with_success=sources_with_success,
        selected_papers=selected_papers,
        total_seed_entries=total_seed_entries,
        strong_seed_entries=strong_seed_entries,
        metadata_resolved_seed_papers=metadata_resolved_seed_papers,
        metadata_unresolved_doi_url_seed_papers=metadata_unresolved_doi_url_seed_papers,
        title_only_entries=title_only_entries,
        curated_seed_papers=curated_seed_papers,
        seed_role_status=seed_role_status,
        seed_role_classes=seed_role_classes,
        thresholds=thresholds,
        seed_intake=seed_intake,
    )
    summary = {
        "provider": provider,
        "configured_source_count": configured_sources,
        "sources_with_success": sources_with_success,
        "selected_papers": selected_papers,
        "total_seed_entries": total_seed_entries,
        "curated_seed_papers": curated_seed_papers,
        "doi_entries": doi_entries,
        "url_entries": url_entries,
        "title_only_entries": title_only_entries,
        "metadata_resolved_seed_papers": metadata_resolved_seed_papers,
        "metadata_unresolved_doi_url_seed_papers": metadata_unresolved_doi_url_seed_papers,
        "seed_role_coverage_status": seed_role_status,
        "seed_role_classes": seed_role_classes,
        "min_configured_sources": thresholds["min_configured_sources"],
        "min_sources_with_success": thresholds["min_sources_with_success"],
        "min_selected_papers": thresholds["min_selected_papers"],
        "min_total_seed_entries": thresholds["min_total_seed_entries"],
        "min_strong_seed_entries": thresholds["min_strong_seed_entries"],
        "min_metadata_resolved_seed_papers": thresholds["min_metadata_resolved_seed_papers"],
        "min_curated_seed_papers": thresholds["min_curated_seed_papers"],
        "min_seed_role_classes": thresholds["min_seed_role_classes"],
        "thresholds": thresholds,
    }
    return {"status": "pass" if not issues else "review_required", "issues": _unique(issues), "repair_suggestions": repair_suggestions, "summary": summary}


def _paper_grade_literature_repair_suggestions(
    *,
    provider: str,
    configured_sources: int,
    sources_with_success: int,
    selected_papers: int,
    total_seed_entries: int,
    strong_seed_entries: int,
    metadata_resolved_seed_papers: int,
    metadata_unresolved_doi_url_seed_papers: int,
    title_only_entries: int,
    curated_seed_papers: int,
    seed_role_status: str,
    seed_role_classes: int | None,
    thresholds: dict[str, int],
    seed_intake: dict[str, Any],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if provider not in {"online", "auto"}:
        suggestions.append(
            {
                "kind": "set_literature_provider",
                "target": "literature.provider",
                "action": "下一轮使用 online 或 auto 文献 provider，避免 offline-only 文献池支撑论文级 claim。",
                "recommended_config": {"literature_provider": "online"},
            }
        )
    if configured_sources < thresholds["min_configured_sources"] or sources_with_success < thresholds["min_sources_with_success"]:
        suggestions.append(
            {
                "kind": "increase_literature_sources",
                "target": "literature.sources",
                "action": f"配置至少 {thresholds['min_configured_sources']} 个在线来源，并要求至少 {thresholds['min_sources_with_success']} 个来源成功返回后再放行。",
                "recommended_config": {
                    "literature_provider": "online",
                    "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
                },
            }
        )
    if selected_papers < thresholds["min_selected_papers"]:
        suggestions.append(
            {
                "kind": "increase_literature_pool",
                "target": "literature.max_papers",
                "action": f"扩大下一轮候选池，保证至少 {thresholds['min_selected_papers']} 篇 curated 文献进入上下文。",
                "recommended_config": {"max_papers": 12, "max_search_queries": 6},
            }
        )
    role_gap = seed_role_classes < thresholds["min_seed_role_classes"] if seed_role_classes is not None else seed_role_status != "pass"
    seed_gap = (
        total_seed_entries < thresholds["min_total_seed_entries"]
        or strong_seed_entries < thresholds["min_strong_seed_entries"]
        or metadata_resolved_seed_papers < thresholds["min_metadata_resolved_seed_papers"]
        or title_only_entries > 0
        or curated_seed_papers < thresholds["min_curated_seed_papers"]
        or role_gap
    )
    if seed_gap:
        suggestions.append(
            {
                "kind": "repair_doi_url_seed_papers",
                "target": "literature.seed_papers",
                "action": f"补齐 {thresholds['min_metadata_resolved_seed_papers']} 条以上可解析元数据的 DOI/URL seed，并让至少 {thresholds['min_curated_seed_papers']} 条进入 curated context，覆盖 review/benchmark/baseline/recent 中至少 {thresholds['min_seed_role_classes']} 类。",
                "recommended_config": {"literature_provider": "online", "seed_papers_min": thresholds["min_total_seed_entries"], "max_papers": 12},
                "suggested_seed_entries": _list_values(seed_intake.get("suggested_seed_entries"))[:6],
                "role_repair_queries": _list_values(seed_intake.get("role_repair_queries"))[:4],
                "metadata_unresolved_doi_url_seed_papers": metadata_unresolved_doi_url_seed_papers,
            }
        )
    if title_only_entries:
        suggestions.append(
            {
                "kind": "replace_title_only_seeds",
                "target": "literature.seed_papers",
                "action": "把 title-only seed 替换为 DOI 或 URL 形式，并重新跑 seed intake。",
                "title_only_entries": title_only_entries,
            }
        )
    return _unique_dicts(suggestions)


def _paper_grade_thresholds(paper_grade_config: PaperGradeConfig | None) -> dict[str, int]:
    config = paper_grade_config or PaperGradeConfig()
    return {
        "min_configured_sources": max(1, _safe_int(config.min_literature_sources)),
        "min_sources_with_success": max(1, _safe_int(config.min_successful_literature_sources)),
        "min_selected_papers": PAPER_GRADE_MIN_SELECTED_PAPERS,
        "min_total_seed_entries": max(1, _safe_int(config.min_seed_papers)),
        "min_strong_seed_entries": max(1, _safe_int(config.min_doi_url_seed_papers)),
        "min_metadata_resolved_seed_papers": max(1, _safe_int(config.min_doi_url_seed_papers)),
        "min_curated_seed_papers": max(1, _safe_int(config.min_seed_papers)),
        "min_seed_role_classes": max(1, _safe_int(config.min_curated_seed_roles)),
    }


def _covered_seed_role_classes(seed_intake: dict[str, Any]) -> int | None:
    counts = seed_intake.get("curated_seed_role_counts")
    if not isinstance(counts, dict):
        return None
    return sum(1 for value in counts.values() if _safe_int(value) > 0)


def _paper_grade_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return (
        f"provider={summary.get('provider') or '-'}, "
        f"sources={_safe_int(summary.get('sources_with_success'))}/{_safe_int(summary.get('configured_source_count'))}, "
        f"selected={_safe_int(summary.get('selected_papers'))}, "
        f"seed={_safe_int(summary.get('curated_seed_papers'))}/{_safe_int(summary.get('total_seed_entries'))}, "
        f"doi_url={_safe_int(summary.get('doi_entries')) + _safe_int(summary.get('url_entries'))}, "
        f"metadata_resolved={_safe_int(summary.get('metadata_resolved_seed_papers'))}, "
        f"role={summary.get('seed_role_coverage_status') or '-'}"
    )


def _blocking_reasons(
    signals: list[dict[str, Any]],
    quality: dict[str, Any],
    source_health: dict[str, Any],
    coverage: dict[str, Any],
    evidence_mix: dict[str, Any],
    rescue: dict[str, Any],
    rescue_execution: dict[str, Any],
    seed_intake: dict[str, Any],
    evidence_contract: dict[str, Any],
    citation: dict[str, Any],
    context: dict[str, Any],
    citation_grounding: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for signal in signals:
        if _status_class(str(signal.get("status") or "")) == "block":
            reasons.append(f"{signal.get('name')} 状态为 {signal.get('status')}：{signal.get('summary')}")
    if _safe_int(quality.get("selected_papers")) == 0 and quality:
        reasons.append("没有文献进入 curated context。")
    if _safe_int(source_health.get("sources_with_success")) == 0 and (_safe_int(source_health.get("rate_limited_sources")) or _safe_int(source_health.get("failed_sources"))):
        reasons.append("所有可用在线文献源都失败或被限流。")
    if str(coverage.get("status") or "") == "block":
        reasons.append("baseline/benchmark coverage 为 block。")
    if str(evidence_mix.get("status") or "") == "block":
        reasons.append("整批 curated 文献缺少必需 anchor。")
    if str(rescue.get("status") or "") == "block":
        reasons.append("文献补检索计划处于 block。")
    if str(seed_intake.get("status") or "") == "block":
        reasons.append("人工 seed 未进入原始文献池或无法核验。")
    if str(evidence_contract.get("status") or "") == "block":
        reasons.append("文献证据契约为 block，进入 context 的文献不可证明可定位、可支撑或可复核。")
    if _safe_int(citation.get("blocked_citations")):
        reasons.append(f"存在 {_safe_int(citation.get('blocked_citations'))} 条阻断引用。")
    if str(citation.get("integrity_status") or "") == "block":
        reasons.append("citation integrity 为 block。")
    if context and (_safe_int(context.get("citations")) == 0 or _safe_int(context.get("chunks")) == 0):
        reasons.append("RAG context 缺少可引用 citation 或 evidence chunk。")
    if _safe_int(citation_grounding.get("blocked_citations")):
        reasons.append(f"最终正文存在 {_safe_int(citation_grounding.get('blocked_citations'))} 条 grounding 阻断引用。")
    if str(citation_grounding.get("status") or "") == "block":
        reasons.append("citation grounding 为 block。")
    return reasons


def _review_reasons(
    signals: list[dict[str, Any]],
    quality: dict[str, Any],
    source_health: dict[str, Any],
    query_execution: dict[str, Any],
    rerank: dict[str, Any],
    coverage: dict[str, Any],
    evidence_mix: dict[str, Any],
    rescue: dict[str, Any],
    rescue_execution: dict[str, Any],
    seed_intake: dict[str, Any],
    evidence_contract: dict[str, Any],
    citation: dict[str, Any],
    context: dict[str, Any],
    citation_grounding: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for signal in signals:
        if _status_class(str(signal.get("status") or "")) == "review":
            reasons.append(f"{signal.get('name')} 需要人工复核：{signal.get('summary')}")
    if _safe_int(quality.get("selected_papers")) < 5 and quality:
        reasons.append("curated 文献少于 5 篇。")
    if _safe_int(source_health.get("rate_limited_sources")):
        reasons.append("存在被限流文献源。")
    if _safe_int(source_health.get("failed_sources")):
        reasons.append("存在失败文献源。")
    if _count_list(query_execution.get("required_actions")) or _count_list(query_execution.get("manual_tasks")):
        reasons.append("query execution 仍有人工待办。")
    if _count_list(rerank.get("warnings")):
        reasons.append("rerank 有警告。")
    if str(coverage.get("status") or "") in {"needs_literature", "needs_coverage", "review_required"}:
        reasons.append("baseline/benchmark coverage 仍需补强。")
    if str(evidence_mix.get("status") or "") in {"needs_evidence_upgrade", "review_required"}:
        reasons.append("证据组合仍缺少 anchor 或 metadata。")
    if str(rescue.get("status") or "") in {"needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        reasons.append("rescue plan 仍有补检索或 seed 任务。")
    if str(rescue_execution.get("status") or "") in {"partial", "no_new_papers", "no_hits", "not_executed"}:
        reasons.append("补检索执行未闭环或没有新增有效文献。")
    if str(seed_intake.get("status") or "") == "review_required" or str(seed_intake.get("role_coverage_status") or "") == "review_required":
        reasons.append("人工 seed 或 seed 角色覆盖需要复核。")
    if str(evidence_contract.get("status") or "") == "review_required":
        reasons.append("文献证据契约需要人工复核。")
    if _safe_int(citation.get("review_required")):
        reasons.append(f"存在 {_safe_int(citation.get('review_required'))} 条需人工核对引用。")
    if context and _safe_int(context.get("chunks")) < _safe_int(context.get("citations")):
        reasons.append("RAG context evidence chunk 少于 citation 数，需人工确认核心文献是否有可用证据片段。")
    if _safe_int(citation_grounding.get("review_citations")):
        reasons.append(f"最终正文存在 {_safe_int(citation_grounding.get('review_citations'))} 条需人工核对 grounding 引用。")
    return reasons


def _required_actions(
    blockers: list[str],
    review_items: list[str],
    paper_grade: dict[str, Any],
    quality: dict[str, Any],
    source_health: dict[str, Any],
    coverage: dict[str, Any],
    evidence_mix: dict[str, Any],
    rescue: dict[str, Any],
    rescue_execution: dict[str, Any],
    seed_intake: dict[str, Any],
    evidence_contract: dict[str, Any],
    citation: dict[str, Any],
    context: dict[str, Any],
    citation_grounding: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    for source in [quality, coverage, evidence_mix, rescue, rescue_execution, seed_intake, evidence_contract, citation, context, citation_grounding]:
        actions.extend(str(item) for item in _list_values(source.get("required_actions"))[:4])
        actions.extend(str(item) for item in _list_values(source.get("recommended_actions"))[:3])
        actions.extend(str(item) for item in _list_values(source.get("manual_tasks"))[:3])
    if _safe_int(source_health.get("rate_limited_sources")):
        actions.append("修复文献源限流，例如设置 SEMANTIC_SCHOLAR_API_KEY 后重启服务并重跑文献阶段。")
    if _safe_int(source_health.get("failed_sources")):
        actions.append("查看 01-literature-source-health.md，修复 failed 来源或暂时移除不稳定来源。")
    for issue in _list_values(paper_grade.get("issues")):
        actions.append(str(issue))
    for suggestion in paper_grade.get("repair_suggestions", []) if isinstance(paper_grade.get("repair_suggestions"), list) else []:
        if isinstance(suggestion, dict) and str(suggestion.get("action") or "").strip():
            actions.append(str(suggestion.get("action") or ""))
    if blockers:
        actions.append("阻断项处理前不要批准进入 idea/实验；处理后重新生成 01-literature-gate-decision。")
    elif review_items:
        actions.append("批准前必须人工阅读核心 DOI/URL，并在 approval notes 写明已接受的剩余风险。")
    return actions


def _approval_guidance(status: str) -> list[str]:
    if status == "block":
        return [
            "当前文献 gate 阻断 idea_generation、experiment_planning 和 experiment_execution。",
            "请优先修复 source/query/seed/citation 问题，重新生成文献上下文后再请求人工审核。",
        ]
    if status == "review_required":
        return [
            "必须人工确认文献质量、seed 覆盖、citation integrity 和补检索未闭环项。",
            "批准时 approval notes 需要说明具体核对内容和接受的剩余风险。",
        ]
    return ["文献 gate 已通过；仍需人工批准后才允许进入 idea/实验。"]


def _status_class(status: str) -> str:
    normalized = status.strip()
    if normalized in {"block", "blocked", "failed", "error", "needs_source_repair"}:
        return "block"
    if normalized in {
        "weak",
        "review",
        "review_required",
        "warn",
        "warning",
        "needs_literature",
        "needs_coverage",
        "needs_evidence_upgrade",
        "needs_rescue_search",
        "needs_manual_seed",
        "partial",
        "no_new_papers",
        "no_hits",
        "not_executed",
    }:
        return "review"
    return "pass"


def _quality_status(quality: dict[str, Any]) -> str:
    if not quality:
        return ""
    return str(quality.get("confidence_status") or ("pass" if _safe_int(quality.get("selected_papers")) >= 5 else "review_required"))


def _source_health_status(source_health: dict[str, Any]) -> str:
    if not source_health:
        return ""
    successes = _safe_int(source_health.get("sources_with_success"))
    rate_limited = _safe_int(source_health.get("rate_limited_sources"))
    failed = _safe_int(source_health.get("failed_sources"))
    if successes == 0 and (rate_limited or failed):
        return "needs_source_repair"
    if rate_limited or failed or _safe_int(source_health.get("stale_cache_uses")):
        return "review_required"
    return "pass"


def _seed_status(seed_intake: dict[str, Any]) -> str:
    if not seed_intake:
        return ""
    status = str(seed_intake.get("status") or "")
    role_status = str(seed_intake.get("role_coverage_status") or "")
    if status in {"pass", "not_configured"} and role_status == "review_required":
        return "review_required"
    if status == "not_configured":
        return "review_required"
    return status


def _context_status(context: dict[str, Any]) -> str:
    if not context:
        return ""
    if _safe_int(context.get("citations")) == 0 or _safe_int(context.get("chunks")) == 0:
        return "block"
    if _safe_int(context.get("chunks")) < _safe_int(context.get("citations")):
        return "review_required"
    return "pass"


def _signal(name: str, status: str, score: Any, summary: str) -> dict[str, Any]:
    return {"name": name, "status": status, "score": _score(score), "summary": summary}


def _quality_summary(quality: dict[str, Any]) -> str:
    if not quality:
        return ""
    return f"selected={_safe_int(quality.get('selected_papers'))}/{_safe_int(quality.get('total_papers'))}, confidence={quality.get('confidence_status') or '-'}"


def _source_health_summary(source_health: dict[str, Any]) -> str:
    if not source_health:
        return ""
    return f"success_sources={_safe_int(source_health.get('sources_with_success'))}, failed={_safe_int(source_health.get('failed_sources'))}, rate_limited={_safe_int(source_health.get('rate_limited_sources'))}"


def _query_execution_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"selected_queries={_safe_int(report.get('selected_query_count'))}, raw_candidates={_safe_int(report.get('raw_candidate_count'))}"


def _rerank_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"warnings={_count_list(report.get('warnings'))}, actions={_count_list(report.get('recommended_actions'))}"


def _coverage_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"coverage_ratio={_safe_float(report.get('coverage_ratio')):.3f}, covered={_safe_int(report.get('covered_required'))}/{_safe_int(report.get('total_required'))}"


def _evidence_mix_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return f"mix_score={_safe_float(report.get('mix_score')):.3f}, anchors={_safe_float(summary.get('anchor_coverage')):.3f}"


def _rescue_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"queries={_count_list(report.get('rescue_queries'))}, actions={_count_list(report.get('required_actions'))}"


def _rescue_execution_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"new_unique={_safe_int(report.get('new_unique_papers'))}, unresolved={_safe_int(report.get('unresolved_query_outcomes'))}"


def _seed_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"curated_seed={_safe_int(report.get('curated_seed_papers'))}/{_safe_int(report.get('total_seed_entries'))}, role={report.get('role_coverage_status') or '-'}"


def _evidence_contract_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return (
        f"chunk={_safe_float(summary.get('chunk_coverage')):.3f}, "
        f"substantive={_safe_float(summary.get('substantive_chunk_coverage')):.3f}, "
        f"locator={_safe_float(summary.get('locator_coverage')):.3f}, "
        f"crossref={_safe_float(summary.get('single_crossref_ratio')):.3f}, "
        f"blocks={_count_list(report.get('blocking_issues'))}, "
        f"review={_count_list(report.get('review_reasons'))}"
    )


def _citation_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"blocked={_safe_int(report.get('blocked_citations'))}, review={_safe_int(report.get('review_required'))}, usable={_safe_int(report.get('usable_citations'))}/{_safe_int(report.get('total_citations'))}"


def _context_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    return f"citations={_safe_int(report.get('citations'))}, chunks={_safe_int(report.get('chunks'))}, claim_support={_safe_int(report.get('claim_support'))}"


def _citation_grounding_summary(report: dict[str, Any]) -> str:
    if not report:
        return ""
    inventory = report.get("evidence_inventory") if isinstance(report.get("evidence_inventory"), dict) else {}
    return (
        f"blocked={_safe_int(report.get('blocked_citations'))}, "
        f"review={_safe_int(report.get('review_citations'))}, "
        f"passed={_safe_int(report.get('passed_citations'))}/{_safe_int(report.get('total_citations'))}, "
        f"context_chunks={_safe_int(inventory.get('context_chunks'))}"
    )


def _report_dict(report: dict[str, Any] | Any | None) -> dict[str, Any]:
    if report is None:
        return {}
    if isinstance(report, dict):
        return report
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


def _score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


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


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _list_values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _unique_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
