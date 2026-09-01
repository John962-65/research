from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .literature_sources import build_evidence_table
from .models import LiteratureReview, Paper, ResearchPlan


LITERATURE_RERANK_JSON = "01-literature-rerank.json"
LITERATURE_RERANK_MD = "01-literature-rerank.md"


def write_literature_rerank_artifacts(review: LiteratureReview, research_plan: ResearchPlan, run_dir: Path) -> tuple[LiteratureReview, dict[str, Any]]:
    reranked, report = rerank_literature_review(review, research_plan)
    write_json(run_dir / LITERATURE_RERANK_JSON, report)
    write_text(run_dir / LITERATURE_RERANK_MD, render_literature_rerank_markdown(report))
    return reranked, report


def rerank_literature_review(review: LiteratureReview, research_plan: ResearchPlan) -> tuple[LiteratureReview, dict[str, Any]]:
    query_terms = _term_groups(research_plan.search_queries or review.search_strategy.get("selected_queries", []))
    baseline_terms = set(_terms(" ".join(research_plan.baselines)))
    benchmark_terms = set(_terms(" ".join(research_plan.benchmarks)))
    topic_terms = set(_terms(" ".join([review.topic, research_plan.objective, research_plan.domain])))
    core_terms = _core_terms(topic_terms | baseline_terms | benchmark_terms)
    scored = [_score_paper(paper, topic_terms, core_terms, query_terms, baseline_terms, benchmark_terms) for paper in review.papers]
    scored.sort(key=lambda item: item["rerank_score"], reverse=True)
    papers = [
        replace(
            item["paper"],
            relevance=round(float(item["rerank_score"]), 4),
            evidence_note=_evidence_note(item),
        )
        for item in scored
    ]
    selected = papers[: min(len(papers), 10)]
    warnings = _warnings(scored)
    report = {
        "topic": review.topic,
        "status": "review_required" if warnings else "pass",
        "total_candidates": len(scored),
        "query_count": len(query_terms),
        "baseline_terms": sorted(baseline_terms),
        "benchmark_terms": sorted(benchmark_terms),
        "top_titles": [paper.title for paper in selected[:5]],
        "warnings": warnings,
        "recommended_actions": _recommended_actions(warnings, scored),
        "items": [
            {
                "rank": index,
                "title": item["paper"].title,
                "year": item["paper"].year,
                "venue": item["paper"].venue,
                "sources": item["paper"].sources or [item["paper"].source],
                "doi": item["paper"].doi,
                "url": item["paper"].url,
                "original_relevance": round(float(item["paper"].relevance), 4),
                "rerank_score": round(float(item["rerank_score"]), 4),
                "topic_overlap": item["topic_overlap"],
                "query_coverage": item["query_coverage"],
                "title_specificity": item["title_specificity"],
                "baseline_hits": sorted(item["baseline_hits"]),
                "benchmark_hits": sorted(item["benchmark_hits"]),
                "metadata_score": item["metadata_score"],
                "source_score": item["source_score"],
                "venue_score": item["venue_score"],
                "penalties": item["penalties"],
                "reasons": item["reasons"],
            }
            for index, item in enumerate(scored, start=1)
        ],
    }
    reranked = replace(
        review,
        papers=papers,
        evidence_table=build_evidence_table(papers),
        source_diagnostics=[
            *review.source_diagnostics,
            f"文献重排: {len(papers)} 条候选已按 topic/query/baseline/benchmark/metadata 信号重新排序。",
        ],
    )
    return reranked, report


def render_literature_rerank_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 文献候选重排：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 候选数：{report.get('total_candidates', 0)}",
        f"- 检索式组数：{report.get('query_count', 0)}",
        f"- Baseline terms：{', '.join(str(item) for item in report.get('baseline_terms', [])) or '-'}",
        f"- Benchmark terms：{', '.join(str(item) for item in report.get('benchmark_terms', [])) or '-'}",
        "",
    ]
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    actions = report.get("recommended_actions") if isinstance(report.get("recommended_actions"), list) else []
    if actions:
        lines.extend(["## 建议动作"])
        lines.extend(f"- {item}" for item in actions)
        lines.append("")
    lines.extend(
        [
            "## 重排表",
            "| Rank | 分数 | 原相关性 | 年份 | 来源 | DOI | Topic | Title | Query | Venue | Baseline | Benchmark | 文献 | 理由 | 降权 |",
            "| ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("rank") or ""),
                    f"{float(item.get('rerank_score') or 0.0):.3f}",
                    f"{float(item.get('original_relevance') or 0.0):.3f}",
                    str(item.get("year") or ""),
                    _cell(", ".join(str(value) for value in item.get("sources", []) if str(value).strip())),
                    "yes" if item.get("doi") else "no",
                    f"{float(item.get('topic_overlap') or 0.0):.2f}",
                    f"{float(item.get('title_specificity') or 0.0):.2f}",
                    f"{float(item.get('query_coverage') or 0.0):.2f}",
                    f"{float(item.get('venue_score') or 0.0):.2f}",
                    _cell(", ".join(str(value) for value in item.get("baseline_hits", []) if str(value).strip()) or "-"),
                    _cell(", ".join(str(value) for value in item.get("benchmark_hits", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("title") or "")),
                    _cell("; ".join(str(value) for value in item.get("reasons", []) if str(value).strip()) or "-"),
                    _cell("; ".join(str(value) for value in item.get("penalties", []) if str(value).strip()) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- 分数越高，越适合进入 `01-literature-quality` 和后续 RAG/context。",
            "- 单源 Crossref、无摘要、无 DOI、弱 query 覆盖会被降权。",
            "- baseline/benchmark 命中不会替代人工精读，但会提高候选优先级。",
        ]
    )
    return "\n".join(lines)


def _score_paper(
    paper: Paper,
    topic_terms: set[str],
    core_terms: set[str],
    query_terms: list[set[str]],
    baseline_terms: set[str],
    benchmark_terms: set[str],
) -> dict[str, Any]:
    text = _paper_text(paper)
    title_text = f"{paper.title} {paper.venue}".lower()
    topic_hits = {term for term in topic_terms if term in text}
    baseline_hits = {term for term in baseline_terms if term in text}
    benchmark_hits = {term for term in benchmark_terms if term in text}
    query_matches = sum(1 for group in query_terms if group and len(group & _text_terms(text)) / max(len(group), 1) >= 0.25)
    query_coverage = query_matches / max(len(query_terms), 1) if query_terms else 0.0
    topic_overlap = len(topic_hits) / max(len(topic_terms), 1) if topic_terms else 0.0
    title_hits = {term for term in topic_terms if term in title_text}
    title_specificity = _title_specificity(paper, core_terms)
    metadata_score = _metadata_score(paper)
    source_score = _source_score(paper)
    venue_score = _venue_score(paper)
    citation_score = min(0.08, (paper.citation_count or 0) / 3000.0)
    recency_score = min(max((paper.year or 0) - 2016, 0), 10) / 200.0
    baseline_score = min(0.08, 0.03 * len(baseline_hits))
    benchmark_score = min(0.08, 0.03 * len(benchmark_hits))
    manual_seed_bonus = 0.08 if "manual_seed" in set(paper.sources or [paper.source]) else 0.0
    penalties = _penalties(paper, topic_overlap, query_coverage, title_specificity, venue_score)
    penalty_score = sum(value for _, value in penalties)
    score = (
        min(max(paper.relevance, 0.0), 1.0) * 0.22
        + topic_overlap * 0.23
        + min(0.12, 0.04 * len(title_hits))
        + title_specificity * 0.08
        + query_coverage * 0.16
        + baseline_score
        + benchmark_score
        + metadata_score * 0.12
        + source_score * 0.08
        + venue_score * 0.07
        + citation_score
        + recency_score
        + manual_seed_bonus
        - penalty_score
    )
    score = round(max(0.0, min(1.0, score)), 4)
    return {
        "paper": paper,
        "rerank_score": score,
        "topic_overlap": round(topic_overlap, 3),
        "query_coverage": round(query_coverage, 3),
        "title_specificity": round(title_specificity, 3),
        "baseline_hits": baseline_hits,
        "benchmark_hits": benchmark_hits,
        "metadata_score": round(metadata_score, 3),
        "source_score": round(source_score, 3),
        "venue_score": round(venue_score, 3),
        "penalties": [name for name, _ in penalties],
        "reasons": _reasons(paper, topic_overlap, query_coverage, title_specificity, metadata_score, source_score, venue_score, baseline_hits, benchmark_hits),
    }


def _metadata_score(paper: Paper) -> float:
    score = 0.0
    if paper.doi:
        score += 0.28
    if paper.url:
        score += 0.18
    if paper.authors:
        score += 0.16
    if paper.year:
        score += 0.14
    if len(paper.abstract or "") >= 180:
        score += 0.24
    elif len(paper.abstract or "") >= 80:
        score += 0.14
    return min(1.0, score)


def _source_score(paper: Paper) -> float:
    sources = set(paper.sources or [paper.source])
    base = max(
        [
            {
                "semantic_scholar": 0.82,
                "openalex": 0.78,
                "arxiv": 0.78,
                "pubmed": 0.76,
                "manual_seed": 0.74,
                "offline": 0.64,
                "crossref": 0.46,
            }.get(source, 0.50)
            for source in sources
        ]
        or [0.50]
    )
    return min(1.0, base + min(0.18, 0.06 * max(0, len(sources) - 1)))


def _venue_score(paper: Paper) -> float:
    text = f"{paper.venue} {paper.source} {' '.join(paper.sources)}".lower()
    if not text.strip():
        return 0.22
    strong_terms = [
        "nature",
        "science",
        "cell",
        "pnas",
        "ieee",
        "acm",
        "neurips",
        "icml",
        "iclr",
        "aaai",
        "ijcai",
        "acl",
        "emnlp",
        "cvpr",
        "iccv",
        "eccv",
        "iros",
        "icra",
        "rss",
        "corl",
        "ijrr",
        "robotics and automation",
        "jmlr",
        "sigkdd",
        "www",
        "chi",
    ]
    if any(term in text for term in strong_terms):
        return 0.86
    if "arxiv" in text or "preprint" in text:
        return 0.58
    if "dataset" in text or "benchmark" in text:
        return 0.55
    if "journal" in text or "conference" in text or "proceedings" in text:
        return 0.50
    if set(paper.sources or [paper.source]) == {"crossref"}:
        return 0.30
    return 0.42


def _penalties(paper: Paper, topic_overlap: float, query_coverage: float, title_specificity: float, venue_score: float) -> list[tuple[str, float]]:
    penalties: list[tuple[str, float]] = []
    sources = set(paper.sources or [paper.source])
    if sources == {"crossref"} and len(paper.abstract or "") < 80:
        penalties.append(("single Crossref source with thin abstract", 0.16))
    if not paper.doi and not paper.url:
        penalties.append(("no DOI/URL locator", 0.12))
    if topic_overlap < 0.12 and "manual_seed" not in sources:
        penalties.append(("weak topic overlap", 0.10))
    if title_specificity < 0.25 and "manual_seed" not in sources:
        penalties.append(("generic title/object mismatch", 0.07))
    if query_coverage == 0.0 and "manual_seed" not in sources:
        penalties.append(("no selected-query coverage", 0.08))
    if venue_score < 0.35 and "manual_seed" not in sources:
        penalties.append(("weak venue/source signal", 0.05))
    if paper.year and paper.year < 1990:
        penalties.append(("suspiciously old record", 0.06))
    return penalties


def _reasons(
    paper: Paper,
    topic_overlap: float,
    query_coverage: float,
    title_specificity: float,
    metadata_score: float,
    source_score: float,
    venue_score: float,
    baseline_hits: set[str],
    benchmark_hits: set[str],
) -> list[str]:
    reasons: list[str] = []
    if "manual_seed" in set(paper.sources or [paper.source]):
        reasons.append("manual seed")
    if topic_overlap >= 0.35:
        reasons.append("strong topic overlap")
    elif topic_overlap >= 0.18:
        reasons.append("moderate topic overlap")
    else:
        reasons.append("weak topic overlap")
    if query_coverage >= 0.5:
        reasons.append("covers selected queries")
    elif query_coverage > 0:
        reasons.append("partial query coverage")
    if title_specificity >= 0.5:
        reasons.append("specific title")
    elif title_specificity < 0.25:
        reasons.append("generic title")
    if baseline_hits:
        reasons.append("baseline signal")
    if benchmark_hits:
        reasons.append("benchmark signal")
    if metadata_score >= 0.65:
        reasons.append("verifiable metadata")
    if source_score >= 0.70:
        reasons.append("trusted or multi-source")
    if venue_score >= 0.70:
        reasons.append("recognized venue")
    if paper.citation_count:
        reasons.append("citation signal")
    return reasons


def _warnings(scored: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if not scored:
        return ["没有候选文献可重排。"]
    top = scored[: min(5, len(scored))]
    if sum(1 for item in top if item["query_coverage"] > 0) < max(1, len(top) // 2):
        warnings.append("Top 候选对选中检索式覆盖不足，建议检查检索式是否过宽或主题词不匹配。")
    if any("single Crossref source with thin abstract" in item["penalties"] for item in top):
        warnings.append("Top 候选仍包含单源 Crossref 且摘要过薄的题录，建议补 DOI seed 或启用 OpenAlex/Semantic Scholar。")
    if any("generic title/object mismatch" in item["penalties"] for item in top):
        warnings.append("Top 候选仍包含标题过泛或对象不匹配的题录，建议补核心方法/benchmark DOI seed。")
    if any("weak venue/source signal" in item["penalties"] for item in top):
        warnings.append("Top 候选仍包含 venue/source 信号较弱的题录，建议人工核验来源可靠性。")
    if sum(1 for item in top if item["paper"].doi) < max(1, len(top) // 3):
        warnings.append("Top 候选 DOI 覆盖偏低，后续引用导出前需要人工核验。")
    return warnings


def _recommended_actions(warnings: list[str], scored: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if any("Crossref" in item for item in warnings):
        actions.append("优先启用 OpenAlex/Semantic Scholar 或加入核心 DOI seed，降低 Crossref 噪声。")
    if any("检索式覆盖" in item for item in warnings):
        actions.append("查看 01-literature-search-strategy.md，增加 baseline、benchmark 和任务数据集检索式。")
    if any("标题过泛" in item for item in warnings):
        actions.append("把核心对象、方法族和 benchmark 的精确标题或 DOI 写入 seed_papers，压低泛题录。")
    if any("venue/source" in item for item in warnings):
        actions.append("优先保留来自领域会议/期刊、arXiv、Semantic Scholar/OpenAlex 多源交叉验证的候选。")
    if any("DOI" in item for item in warnings):
        actions.append("把核心综述、baseline、benchmark 论文 DOI 写入 seed_papers 后重跑。")
    if not actions and scored:
        actions.append("人工抽查 Top 5 URL/DOI，确认题录和摘要与课题匹配。")
    return actions


def _evidence_note(item: dict[str, Any]) -> str:
    reasons = "; ".join(str(value) for value in item.get("reasons", [])[:3])
    return f"Rerank {float(item.get('rerank_score') or 0.0):.3f}: {reasons or 'candidate evidence'}."


def _term_groups(values: list[Any]) -> list[set[str]]:
    groups: list[set[str]] = []
    for value in values:
        terms = set(_terms(str(value)))
        if terms:
            groups.append(terms)
    return groups


def _core_terms(terms: set[str]) -> set[str]:
    generic = {
        "algorithm",
        "algorithms",
        "analysis",
        "approach",
        "based",
        "benchmark",
        "comparison",
        "data",
        "dataset",
        "evaluation",
        "experiment",
        "experiments",
        "framework",
        "learning",
        "method",
        "methods",
        "model",
        "models",
        "performance",
        "planning",
        "research",
        "review",
        "study",
        "survey",
        "system",
        "systems",
        "task",
        "tasks",
        "using",
        "路径",
        "规划",
        "研究",
        "方法",
        "系统",
        "模型",
        "实验",
        "评估",
        "综述",
    }
    return {term for term in terms if term not in generic and (len(term) >= 4 or re.fullmatch(r"[\u4e00-\u9fff]{2,}", term))}


def _title_specificity(paper: Paper, core_terms: set[str]) -> float:
    if not core_terms:
        return 0.0
    title_terms = _text_terms(f"{paper.title} {paper.venue}")
    hits = {term for term in core_terms if term in title_terms or term in f"{paper.title} {paper.venue}".lower()}
    denominator = max(2, min(5, len(core_terms)))
    return min(1.0, len(hits) / denominator)


def _terms(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "that", "this", "into", "using", "from", "研究", "文献", "系统", "方法", "问题"}
    values: list[str] = []
    for match in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.lower()):
        normalized = match.replace("-", "_")
        if re.fullmatch(r"[\u4e00-\u9fff]+", normalized):
            values.append(normalized)
            if len(normalized) > 2:
                values.extend(normalized[index : index + 2] for index in range(0, len(normalized) - 1))
        else:
            values.append(normalized)
    result: list[str] = []
    for value in values:
        if value not in stop and value not in result:
            result.append(value)
    return result


def _text_terms(text: str) -> set[str]:
    return set(_terms(text))


def _paper_text(paper: Paper) -> str:
    return f"{paper.title} {paper.abstract} {paper.venue} {' '.join(paper.authors)}".lower()


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
