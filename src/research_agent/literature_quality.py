from __future__ import annotations

from dataclasses import replace
import re

from .literature_sources import build_evidence_table
from .models import LiteratureQualityItem, LiteratureQualityReport, LiteratureReview, Paper
from .artifacts import cell as _cell


CORE_EVIDENCE_ROLES = ["review_survey", "benchmark_dataset", "baseline_method", "recent_work"]


def assess_literature_quality(review: LiteratureReview, min_keep: int = 5) -> LiteratureQualityReport:
    ranked: list[tuple[float, Paper, LiteratureQualityItem]] = []
    for paper in review.papers:
        evidence_roles = _evidence_roles(paper)
        score, reasons = _quality_score(paper, review.topic, evidence_roles)
        decision = _decision(score)
        ranked.append(
            (
                score,
                paper,
                LiteratureQualityItem(
                    title=paper.title,
                    year=paper.year,
                    venue=paper.venue,
                    sources=paper.sources or [paper.source],
                    relevance=round(paper.relevance, 3),
                    quality_score=round(score, 3),
                    decision=decision,
                    selected=False,
                    reasons=reasons,
                    doi=paper.doi,
                    url=paper.url,
                    evidence_roles=evidence_roles,
                ),
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    keep_target = min(len(ranked), max(1, min_keep))
    selected_titles = _selected_titles(ranked, keep_target)
    items = [
        replace(item, selected=item.title in selected_titles)
        for _, _, item in ranked
    ]
    warnings: list[str] = []
    selected_count = sum(1 for item in items if item.selected)
    if selected_count < min(3, len(items)):
        warnings.append("质量筛选后可用文献偏少，建议扩大检索式或增加文献源。")
    if selected_count < keep_target:
        warnings.append(f"质量筛选未凑满最低保留目标：仅 {selected_count}/{keep_target} 篇达到 keep/review；已拒绝用 exclude 文献填充上下文。")
    if any(item.decision == "exclude" for item in items):
        warnings.append("存在低质量或弱相关候选，已阻止其进入 RAG/idea 阶段。")
    if sum(1 for item in items if item.doi and item.selected) < max(1, selected_count // 3):
        warnings.append("保留文献中 DOI 比例偏低，引用导出前需要人工核对。")
    (
        confidence_score,
        confidence_status,
        confidence_factors,
        confidence_warnings,
        recommended_actions,
        role_coverage,
        missing_evidence_roles,
    ) = _evidence_confidence(
        review,
        ranked,
        selected_titles,
    )
    warnings = _unique([*warnings, *confidence_warnings])
    return LiteratureQualityReport(
        topic=review.topic,
        total_papers=len(items),
        selected_papers=selected_count,
        min_keep=keep_target,
        items=items,
        warnings=warnings,
        confidence_score=confidence_score,
        confidence_status=confidence_status,
        confidence_factors=confidence_factors,
        source_warnings=confidence_warnings,
        recommended_actions=recommended_actions,
        role_coverage=role_coverage,
        missing_evidence_roles=missing_evidence_roles,
    )


def filter_review_by_quality(review: LiteratureReview, report: LiteratureQualityReport) -> LiteratureReview:
    selected_titles = {item.title for item in report.items if item.selected}
    selected_papers = [paper for paper in review.papers if paper.title in selected_titles]
    diagnostics = list(review.source_diagnostics)
    diagnostics.append(
        f"质量筛选: 原始 {len(review.papers)} 条，保留 {len(selected_papers)} 条，排除 {len(review.papers) - len(selected_papers)} 条。"
    )
    return replace(
        review,
        papers=selected_papers,
        source_diagnostics=diagnostics,
        evidence_table=build_evidence_table(selected_papers),
    )


def render_literature_quality_markdown(report: LiteratureQualityReport) -> str:
    lines = [
        f"# 文献质量筛选：{report.topic}",
        "",
        f"- 原始候选：{report.total_papers}",
        f"- 保留进入上下文：{report.selected_papers}",
        f"- 最低保留目标：{report.min_keep}",
        f"- 证据置信度：{report.confidence_status or '-'} ({report.confidence_score:.3f})",
        "",
    ]
    if report.confidence_factors:
        lines.extend(
            [
                "## 证据置信度",
                "| 指标 | 值 |",
                "| --- | ---: |",
            ]
        )
        for key in [
            "avg_quality",
            "selected_papers",
            "source_diversity",
            "doi_coverage",
            "abstract_coverage",
            "source_health",
            "evidence_role_score",
            "evidence_role_count",
            "rate_limited_sources",
            "failed_sources",
            "manual_seed_papers",
        ]:
            if key in report.confidence_factors:
                lines.append(f"| {_cell(key)} | {_cell(str(report.confidence_factors[key]))} |")
        lines.append("")
    if report.warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in report.warnings)
        lines.append("")
    if report.recommended_actions:
        lines.extend(["## 建议动作"])
        lines.extend(f"- {item}" for item in report.recommended_actions)
        lines.append("")
    if report.role_coverage:
        lines.extend(["## 证据角色覆盖", "| 角色 | 文献数 |", "| --- | ---: |"])
        for role in CORE_EVIDENCE_ROLES:
            lines.append(f"| {_cell(role)} | {int(report.role_coverage.get(role, 0))} |")
        if report.missing_evidence_roles:
            lines.extend(["", "缺失角色："])
            lines.extend(f"- {item}" for item in report.missing_evidence_roles)
        lines.append("")
    lines.extend(
        [
            "## 筛选表",
            "| 选择 | 决策 | 分数 | 年份 | 来源 | 角色 | 文献 | 原因 |",
            "| --- | --- | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for item in report.items:
        selected = "yes" if item.selected else "no"
        sources = _cell(", ".join(item.sources))
        roles = _cell(", ".join(item.evidence_roles) or "-")
        title = _cell(item.title)
        reasons = _cell("；".join(item.reasons))
        lines.append(f"| {selected} | {item.decision} | {item.quality_score:.3f} | {item.year or ''} | {sources} | {roles} | {title} | {reasons} |")
    return "\n".join(lines)


def _selected_titles(ranked: list[tuple[float, Paper, LiteratureQualityItem]], keep_target: int) -> set[str]:
    selected: set[str] = set()
    for score, _, item in ranked:
        if item.decision == "keep":
            selected.add(item.title)
    _add_manual_seed_anchors(ranked, selected)
    _add_role_fillers(ranked, selected)
    for _, _, item in ranked:
        if len(selected) >= keep_target:
            break
        if item.decision == "review":
            selected.add(item.title)
    return selected


def _add_manual_seed_anchors(ranked: list[tuple[float, Paper, LiteratureQualityItem]], selected: set[str]) -> None:
    for _, paper, item in ranked:
        sources = set(paper.sources or [paper.source])
        if "manual_seed" not in sources or item.decision == "exclude":
            continue
        if not (paper.doi or paper.url):
            continue
        selected.add(item.title)


def _add_role_fillers(ranked: list[tuple[float, Paper, LiteratureQualityItem]], selected: set[str]) -> None:
    covered = _covered_roles(ranked, selected)
    for role in CORE_EVIDENCE_ROLES:
        if role in covered:
            continue
        candidate = _best_review_role_candidate(ranked, selected, role)
        if candidate is None:
            continue
        selected.add(candidate.title)
        covered.update(role for role in candidate.evidence_roles if role in CORE_EVIDENCE_ROLES)


def _covered_roles(ranked: list[tuple[float, Paper, LiteratureQualityItem]], selected: set[str]) -> set[str]:
    covered: set[str] = set()
    for _, _, item in ranked:
        if item.title not in selected:
            continue
        covered.update(role for role in item.evidence_roles if role in CORE_EVIDENCE_ROLES)
    return covered


def _best_review_role_candidate(
    ranked: list[tuple[float, Paper, LiteratureQualityItem]],
    selected: set[str],
    role: str,
) -> LiteratureQualityItem | None:
    for _, _, item in ranked:
        if item.title in selected or item.decision != "review":
            continue
        if role in item.evidence_roles:
            return item
    return None


def _evidence_confidence(
    review: LiteratureReview,
    ranked: list[tuple[float, Paper, LiteratureQualityItem]],
    selected_titles: set[str],
) -> tuple[float, str, dict[str, float | int | str], list[str], list[str], dict[str, int], list[str]]:
    selected = [(score, paper, item) for score, paper, item in ranked if item.title in selected_titles]
    selected_count = len(selected)
    if not selected:
        rate_limited_sources = _source_health_count(review, {"rate_limited"})
        failed_sources = _source_health_count(review, {"failed"})
        warnings = ["没有文献进入上下文，不能支撑后续 idea/实验。"]
        actions = ["先扩大检索式或加入人工 seed_papers，再重新生成文献质量筛选。"]
        if rate_limited_sources:
            warnings.append(f"存在 {rate_limited_sources} 个文献源被限流，当前召回可能不完整。")
            actions.insert(0, "先设置 SEMANTIC_SCHOLAR_API_KEY 或降低 Semantic Scholar 频率，再重新检索。")
        if failed_sources:
            warnings.append(f"存在 {failed_sources} 个文献源检索失败，当前召回可能偏窄。")
            actions.insert(0, "查看 01-literature-source-health.md，修复 failed 来源或从 sources 临时移除。")
        actions.append("未处理上述问题前不要批准进入 idea/实验；如人工豁免，需在 approval notes 写明理由。")
        return (
            0.0,
            "block",
            {
                "avg_quality": 0.0,
                "selected_papers": 0,
                "source_diversity": 0,
                "doi_coverage": 0.0,
                "abstract_coverage": 0.0,
                "source_health": _source_health_score(review),
                "evidence_role_score": 0.0,
                "evidence_role_count": 0,
                "rate_limited_sources": rate_limited_sources,
                "failed_sources": failed_sources,
            },
            warnings,
            _unique(actions),
            {role: 0 for role in CORE_EVIDENCE_ROLES},
            list(CORE_EVIDENCE_ROLES),
        )

    avg_quality = sum(score for score, _, _ in selected) / selected_count
    source_values = _selected_sources(selected)
    source_diversity = len(source_values)
    doi_coverage = sum(1 for _, paper, _ in selected if paper.doi) / selected_count
    abstract_coverage = sum(1 for _, paper, _ in selected if len(paper.abstract or "") >= 100) / selected_count
    source_health = _source_health_score(review)
    rate_limited_sources = _source_health_count(review, {"rate_limited"})
    failed_sources = _source_health_count(review, {"failed"})
    manual_seed_papers = sum(1 for _, paper, _ in selected if "manual_seed" in set(paper.sources or [paper.source]))
    offline_only = source_values == {"offline"}
    role_coverage = _role_coverage(selected)
    role_count = sum(1 for role in CORE_EVIDENCE_ROLES if role_coverage.get(role, 0) > 0)
    missing_roles = [role for role in CORE_EVIDENCE_ROLES if role_coverage.get(role, 0) == 0]
    role_score = min(role_count / 3.0, 1.0)

    source_diversity_score = min(source_diversity / 3.0, 1.0)
    selection_score = min(selected_count / 5.0, 1.0)
    doi_score = min(doi_coverage / 0.6, 1.0)
    score = (
        avg_quality * 0.22
        + selection_score * 0.16
        + source_diversity_score * 0.16
        + doi_score * 0.13
        + abstract_coverage * 0.09
        + source_health * 0.12
        + role_score * 0.12
    )
    if selected_count < 3:
        score = min(score, 0.50)
    if source_diversity <= 1:
        score = min(score, 0.70)
    if role_count < 2:
        score = min(score, 0.66)
    if role_count == 0:
        score = min(score, 0.58)
    if offline_only:
        score = min(score, 0.66)
    if rate_limited_sources and source_diversity <= 1:
        score = min(score, 0.58)
    score = round(max(0.0, min(1.0, score)), 3)
    status = _confidence_status(score)
    factors: dict[str, float | int | str] = {
        "avg_quality": round(avg_quality, 3),
        "selected_papers": selected_count,
        "source_diversity": source_diversity,
        "doi_coverage": round(doi_coverage, 3),
        "abstract_coverage": round(abstract_coverage, 3),
        "source_health": round(source_health, 3),
        "evidence_role_score": round(role_score, 3),
        "evidence_role_count": role_count,
        "rate_limited_sources": rate_limited_sources,
        "failed_sources": failed_sources,
        "manual_seed_papers": manual_seed_papers,
    }
    warnings = _confidence_warnings(
        status,
        selected_count,
        source_diversity,
        doi_coverage,
        abstract_coverage,
        rate_limited_sources,
        failed_sources,
        offline_only,
        avg_quality,
        role_count,
        missing_roles,
    )
    actions = _confidence_actions(status, selected_count, source_diversity, doi_coverage, rate_limited_sources, failed_sources, offline_only, role_count, missing_roles)
    return score, status, factors, warnings, actions, role_coverage, missing_roles


def _confidence_status(score: float) -> str:
    if score >= 0.74:
        return "pass"
    if score >= 0.60:
        return "review_required"
    if score >= 0.45:
        return "weak"
    return "block"


def _confidence_warnings(
    status: str,
    selected_count: int,
    source_diversity: int,
    doi_coverage: float,
    abstract_coverage: float,
    rate_limited_sources: int,
    failed_sources: int,
    offline_only: bool,
    avg_quality: float,
    role_count: int,
    missing_roles: list[str],
) -> list[str]:
    warnings: list[str] = []
    if selected_count < 5:
        warnings.append(f"证据池偏小：仅 {selected_count} 篇文献进入上下文，建议至少保留 5 篇高相关文献。")
    if source_diversity < 2:
        warnings.append("文献来源过于单一，容易被单个 API 排序或离线种子污染。")
    if doi_coverage < 0.50:
        warnings.append(f"DOI 覆盖率偏低（{doi_coverage:.0%}），引用导出和人工核对风险较高。")
    if abstract_coverage < 0.60:
        warnings.append(f"摘要覆盖率偏低（{abstract_coverage:.0%}），RAG chunk 可能缺少可验证语义。")
    if rate_limited_sources:
        warnings.append(f"存在 {rate_limited_sources} 个文献源被限流，当前召回可能不完整。")
    if failed_sources:
        warnings.append(f"存在 {failed_sources} 个文献源检索失败，当前召回可能偏窄。")
    if offline_only:
        warnings.append("当前仅使用离线种子文献，适合演示流程，不足以作为真实调研结论。")
    if avg_quality < 0.58:
        warnings.append(f"保留文献平均质量分偏低（{avg_quality:.3f}），建议补检索后再批准。")
    if role_count < 2:
        warnings.append("证据角色覆盖不足：缺少 review/survey、benchmark/dataset、baseline/method 或 recent work anchor。")
    if missing_roles:
        warnings.append("缺失证据角色：" + ", ".join(missing_roles[:4]))
    if status in {"weak", "block"}:
        warnings.append(f"整批证据置信度为 {status}，不建议直接进入 idea/实验。")
    return warnings


def _confidence_actions(
    status: str,
    selected_count: int,
    source_diversity: int,
    doi_coverage: float,
    rate_limited_sources: int,
    failed_sources: int,
    offline_only: bool,
    role_count: int,
    missing_roles: list[str],
) -> list[str]:
    actions: list[str] = []
    if rate_limited_sources:
        actions.append("先设置 SEMANTIC_SCHOLAR_API_KEY 或降低 Semantic Scholar 频率，再重新检索。")
    if failed_sources:
        actions.append("查看 01-literature-source-health.md，修复 failed 来源或从 sources 临时移除。")
    if offline_only:
        actions.append("真实调研请切换 literature.provider=online/auto，并保留 openalex、crossref、arxiv 等多源兜底。")
    if source_diversity < 2:
        actions.append("至少启用两个在线来源，或把 3-5 篇核心 DOI 加入 seed_papers。")
    if doi_coverage < 0.50:
        actions.append("把核心综述、benchmark、baseline 论文 DOI 加入人工 seed_papers。")
    if selected_count < 5:
        actions.append("执行 01-literature-rescue-plan.md 中的高优先级补检索式后重跑文献阶段。")
    if role_count < 2:
        actions.append("补齐至少两类 evidence roles：review/survey、benchmark/dataset、baseline/method、recent work；优先用 DOI seed 或精确题名检索。")
    if "benchmark_dataset" in missing_roles:
        actions.append("补检索 benchmark/dataset 论文，避免只用泛相关方法论文生成实验计划。")
    if "baseline_method" in missing_roles:
        actions.append("补检索 baseline/method 论文，确保 idea 和实验计划有可比较对象。")
    if status in {"weak", "block"}:
        actions.append("未处理上述问题前不要批准进入 idea/实验；如人工豁免，需在 approval notes 写明理由。")
    if not actions:
        actions.append("人工打开核心 URL/DOI 抽查题录、摘要和主题匹配后再批准。")
    return _unique(actions)


def _selected_sources(selected: list[tuple[float, Paper, LiteratureQualityItem]]) -> set[str]:
    sources: set[str] = set()
    for _, paper, _ in selected:
        for source in paper.sources or [paper.source]:
            value = str(source).strip().lower()
            if value:
                sources.add(value)
    return sources


def _source_health_score(review: LiteratureReview) -> float:
    rows = review.source_health or []
    if not rows:
        return 1.0
    penalty = 0.0
    for item in rows:
        status = str(item.get("status") or "")
        returned = _safe_int(item.get("returned"))
        errors = _safe_int(item.get("errors"))
        if status == "rate_limited" or item.get("rate_limited"):
            penalty += 1.0
        elif status == "failed":
            penalty += 0.9
        elif status == "partial" or errors:
            penalty += 0.4
        elif status == "skipped" and returned == 0:
            penalty += 0.2
    return max(0.0, min(1.0, 1.0 - penalty / max(len(rows), 1)))


def _source_health_count(review: LiteratureReview, statuses: set[str]) -> int:
    count = 0
    for item in review.source_health or []:
        status = str(item.get("status") or "")
        if status in statuses or ("rate_limited" in statuses and item.get("rate_limited")):
            count += 1
    return count


def _quality_score(paper: Paper, topic: str, evidence_roles: list[str]) -> tuple[float, list[str]]:
    topic_terms = set(_terms(topic))
    text = f"{paper.title} {paper.abstract} {paper.venue}".lower()
    title = paper.title.lower()
    sources = set(paper.sources or [paper.source])
    overlap = sum(1 for term in topic_terms if term in text)
    title_overlap = sum(1 for term in topic_terms if term in title)
    lexical = overlap / max(len(topic_terms), 1) if topic_terms else 0.0
    title_signal = min(0.16, 0.05 * title_overlap)
    abstract_score = _abstract_score(paper.abstract)
    metadata_score = _metadata_score(paper)
    source_score = min(0.12, 0.05 * len(set(paper.sources or [paper.source])))
    citation_score = min(0.08, (paper.citation_count or 0) / 2500.0)
    recency_score = min(max(paper.year - 2015, 0), 10) / 180.0 if paper.year else 0.0
    manual_seed_bonus = 0.16 if "manual_seed" in sources else 0.0
    role_score = _paper_role_score(evidence_roles)
    locator_penalty = _locator_penalty(paper, sources)
    score = (
        paper.relevance * 0.31
        + lexical * 0.23
        + title_signal
        + abstract_score
        + metadata_score
        + source_score
        + citation_score
        + recency_score
        + role_score
        + manual_seed_bonus
        - locator_penalty
    )
    reasons = _score_reasons(paper, lexical, abstract_score, metadata_score, source_score, citation_score)
    if manual_seed_bonus:
        reasons.insert(0, "manual seed")
    if evidence_roles and evidence_roles != ["generic_context"]:
        reasons.append("evidence roles: " + ", ".join(evidence_roles))
    elif evidence_roles == ["generic_context"]:
        reasons.append("generic context only")
    score, blockers = _apply_quality_caps(score, paper, lexical, title_overlap, sources)
    reasons.extend(blockers)
    return min(1.0, round(max(0.0, score), 4)), reasons


def _decision(score: float) -> str:
    if score >= 0.58:
        return "keep"
    if score >= 0.42:
        return "review"
    return "exclude"


def _abstract_score(abstract: str) -> float:
    length = len(abstract or "")
    if length >= 240:
        return 0.14
    if length >= 100:
        return 0.09
    if length >= 40:
        return 0.04
    return -0.06


def _metadata_score(paper: Paper) -> float:
    score = 0.0
    if paper.doi:
        score += 0.08
    if paper.url:
        score += 0.04
    if paper.year:
        score += 0.03
    if paper.authors:
        score += 0.03
    return score


def _locator_penalty(paper: Paper, sources: set[str]) -> float:
    if "manual_seed" in sources:
        return 0.0
    if paper.doi or paper.url:
        return 0.0
    return 0.18 if len(paper.abstract or "") < 100 else 0.10


def _apply_quality_caps(score: float, paper: Paper, lexical: float, title_overlap: int, sources: set[str]) -> tuple[float, list[str]]:
    if "manual_seed" in sources:
        return score, []
    blockers: list[str] = []
    if not paper.doi and not paper.url and len(paper.abstract or "") < 80:
        score = min(score, 0.36)
        blockers.append("unverifiable thin record")
    if sources == {"crossref"} and len(paper.abstract or "") < 100:
        score = min(score, 0.40)
        blockers.append("single Crossref thin metadata")
    if lexical < 0.12 and title_overlap == 0 and not (paper.doi or paper.url) and len(sources) <= 1:
        score = min(score, 0.38)
        blockers.append("topic mismatch cap")
    return score, blockers


def _evidence_roles(paper: Paper) -> list[str]:
    text = _normalize_text(f"{paper.title} {paper.abstract} {paper.venue}")
    roles: list[str] = []
    if _has_any(
        text,
        [
            "review",
            "survey",
            "systematic review",
            "meta analysis",
            "meta-analysis",
            "scoping review",
            "综述",
            "调研",
        ],
    ):
        roles.append("review_survey")
    if _has_any(
        text,
        [
            "benchmark",
            "dataset",
            "data set",
            "corpus",
            "testbed",
            "test bed",
            "evaluation suite",
            "ompl",
            "open motion planning library",
            "moveit",
            "cwru",
            "paderborn",
            "xjtu",
            "ims bearing",
            "litqa",
            "mlagentbench",
            "mle bench",
            "mle-bench",
            "基准",
            "数据集",
        ],
    ):
        roles.append("benchmark_dataset")
    if _has_any(
        text,
        [
            "baseline",
            "method",
            "algorithm",
            "planner",
            "rrt",
            "rrt star",
            "prm",
            "chomp",
            "stomp",
            "trajopt",
            "svm",
            "cnn",
            "lstm",
            "resnet",
            "transformer",
            "trajectory optimization",
            "sampling based",
            "方法",
            "算法",
            "对照",
        ],
    ):
        roles.append("baseline_method")
    if paper.year and paper.year >= 2022:
        roles.append("recent_work")
    return _unique(roles) or ["generic_context"]


def _paper_role_score(evidence_roles: list[str]) -> float:
    core_count = sum(1 for role in CORE_EVIDENCE_ROLES if role in evidence_roles)
    if core_count >= 3:
        return 0.08
    if core_count == 2:
        return 0.05
    if core_count == 1:
        return 0.025
    return 0.0


def _role_coverage(selected: list[tuple[float, Paper, LiteratureQualityItem]]) -> dict[str, int]:
    coverage = {role: 0 for role in CORE_EVIDENCE_ROLES}
    for _, _, item in selected:
        roles = set(item.evidence_roles)
        for role in CORE_EVIDENCE_ROLES:
            if role in roles:
                coverage[role] += 1
    return coverage


def _score_reasons(
    paper: Paper,
    lexical: float,
    abstract_score: float,
    metadata_score: float,
    source_score: float,
    citation_score: float,
) -> list[str]:
    reasons: list[str] = []
    if lexical >= 0.45:
        reasons.append("topic terms match")
    elif lexical <= 0.12:
        reasons.append("weak topic match")
    if abstract_score >= 0.09:
        reasons.append("usable abstract")
    else:
        reasons.append("thin abstract")
    if metadata_score >= 0.12:
        reasons.append("verifiable metadata")
    elif not paper.doi:
        reasons.append("missing DOI")
    if source_score >= 0.10:
        reasons.append("multi-source")
    if citation_score > 0:
        reasons.append("citation signal")
    if paper.year and paper.year < 2000:
        reasons.append("older source")
    return reasons or ["candidate evidence"]


def _terms(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "that", "this", "into", "using", "from", "研究", "文献", "系统", "路径", "规划"}
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return [term.replace("-", "_") for term in terms if term not in stop]


def _has_any(text: str, terms: list[str]) -> bool:
    return any(_normalize_text(term) in text for term in terms if str(term).strip())


def _normalize_text(text: str) -> str:
    value = str(text or "").lower().replace("*", " star")
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _safe_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
