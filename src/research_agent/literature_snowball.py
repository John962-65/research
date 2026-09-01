from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import LiteratureQualityReport, LiteratureReview, Paper


LITERATURE_SNOWBALL_JSON = "01-literature-snowball.json"
LITERATURE_SNOWBALL_MD = "01-literature-snowball.md"


def write_literature_snowball_artifacts(
    review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_snowball_report(review, quality_report)
    write_json(run_dir / LITERATURE_SNOWBALL_JSON, report)
    write_text(run_dir / LITERATURE_SNOWBALL_MD, render_literature_snowball_markdown(report))
    return report


def build_literature_snowball_report(
    review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
) -> dict[str, Any]:
    quality = _quality_data(quality_report)
    items = [item for item in quality.get("items", []) if isinstance(item, dict)]
    selected = [item for item in items if item.get("selected")]
    selected.sort(key=lambda item: float(item.get("quality_score") or 0), reverse=True)
    papers_by_title = {paper.title: paper for paper in review.papers}
    seeds = [_seed_row(item, papers_by_title.get(str(item.get("title") or ""))) for item in selected[:8]]
    expansion_queries = _expansion_queries(review.topic, seeds)
    coverage_gaps = _coverage_gaps(review, quality, seeds)
    source_actions = _source_actions(review)
    required_actions = _required_actions(coverage_gaps, source_actions, expansion_queries)
    status = _status(seeds, coverage_gaps, source_actions)
    return {
        "topic": review.topic,
        "status": status,
        "seed_count": len(seeds),
        "query_count": len(expansion_queries),
        "seed_papers": seeds,
        "expansion_queries": expansion_queries,
        "coverage_gaps": coverage_gaps,
        "source_actions": source_actions,
        "required_actions": required_actions,
        "manual_seed_template": [
            "DOI | Title | Why it is central | Dataset/benchmark/baseline covered",
            "10.xxxx/example | Exact paper title | Covers missing baseline | benchmark name",
        ],
    }


def render_literature_snowball_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 文献滚雪球计划：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- Seed papers：{report.get('seed_count', 0)}",
        f"- 扩展检索式：{report.get('query_count', 0)}",
        "",
    ]
    for key, title in [("coverage_gaps", "覆盖缺口"), ("source_actions", "文献源动作"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(
        [
            "## Seed Papers",
            "| 优先级 | 分数 | 年份 | DOI | 文献 | 来源 | 原因 |",
            "| ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    seeds = report.get("seed_papers") if isinstance(report.get("seed_papers"), list) else []
    if not seeds:
        lines.append("|  |  |  |  | 无可用 seed paper |  |  |")
    for seed in seeds:
        if isinstance(seed, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(seed.get("priority") or ""),
                        f"{float(seed.get('quality_score') or 0):.3f}",
                        str(seed.get("year") or ""),
                        _cell(str(seed.get("doi") or "-")),
                        _cell(str(seed.get("title") or "")),
                        _cell(", ".join(str(item) for item in seed.get("sources", []) if str(item).strip())),
                        _cell("；".join(str(item) for item in seed.get("reasons", []) if str(item).strip())),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## 扩展检索式", "| 优先级 | 用途 | 检索式 | Seed |", "| ---: | --- | --- | --- |"])
    queries = report.get("expansion_queries") if isinstance(report.get("expansion_queries"), list) else []
    if not queries:
        lines.append("|  |  | 无 |  |")
    for query in queries:
        if isinstance(query, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(query.get("priority") or ""),
                        _cell(str(query.get("purpose") or "")),
                        "`" + _cell(str(query.get("query") or "")) + "`",
                        _cell(str(query.get("seed_title") or "")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## 人工 Seed 模板"])
    template = report.get("manual_seed_template") if isinstance(report.get("manual_seed_template"), list) else []
    lines.extend(f"- {item}" for item in template)
    return "\n".join(lines)


def _quality_data(report: LiteratureQualityReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    if is_dataclass(report):
        return asdict(report)
    return {}


def _seed_row(item: dict[str, Any], paper: Paper | None) -> dict[str, Any]:
    sources = item.get("sources") if isinstance(item.get("sources"), list) else []
    reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
    doi = str(item.get("doi") or (paper.doi if paper else "") or "")
    url = str(item.get("url") or (paper.url if paper else "") or "")
    score = float(item.get("quality_score") or 0)
    return {
        "title": str(item.get("title") or (paper.title if paper else "")),
        "year": int(item.get("year") or (paper.year if paper else 0) or 0),
        "venue": str(item.get("venue") or (paper.venue if paper else "")),
        "doi": doi,
        "url": url,
        "sources": [str(source) for source in sources if str(source).strip()],
        "quality_score": round(score, 3),
        "priority": _priority(score, doi, sources),
        "reasons": [str(reason) for reason in reasons if str(reason).strip()],
        "abstract_terms": _terms(paper.abstract if paper else "")[:8],
    }


def _expansion_queries(topic: str, seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    topic_terms = " ".join(_terms(topic)[:5])
    for seed in seeds:
        title = str(seed.get("title") or "").strip()
        if not title:
            continue
        doi = str(seed.get("doi") or "").strip()
        title_terms = " ".join(_terms(title)[:8])
        rows = []
        if doi:
            rows.append((f'"{doi}"', "doi_lookup", 96))
        rows.extend(
            [
                (f'"{title}"', "exact_title", 92),
                (f'{title_terms} benchmark baseline', "benchmark_baseline_snowball", 82),
                (f'{title_terms} cited by related work', "forward_citation_snowball", 78),
            ]
        )
        if topic_terms and title_terms:
            rows.append((f'{topic_terms} {title_terms} survey', "topic_seed_synthesis", 74))
        for query, purpose, priority in rows:
            normalized = re.sub(r"\s+", " ", query).strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            result.append({"query": normalized, "purpose": purpose, "priority": priority, "seed_title": title})
    return sorted(result, key=lambda item: int(item["priority"]), reverse=True)[:24]


def _coverage_gaps(review: LiteratureReview, quality: dict[str, Any], seeds: list[dict[str, Any]]) -> list[str]:
    gaps: list[str] = []
    selected_papers = int(quality.get("selected_papers") or len(seeds))
    if selected_papers < 5:
        gaps.append(f"保留文献只有 {selected_papers} 篇，建议用 seed DOI 和精确标题做一轮 snowball。")
    doi_count = sum(1 for seed in seeds if seed.get("doi"))
    if seeds and doi_count < max(1, len(seeds) // 2):
        gaps.append("Seed papers DOI 覆盖不足，引用导出和精确追踪需要人工补 DOI。")
    source_sets = [set(seed.get("sources", [])) for seed in seeds]
    multi_source = sum(1 for sources in source_sets if len(sources) >= 2)
    if seeds and multi_source == 0 and any(seed.get("sources") for seed in seeds):
        gaps.append("Seed papers 缺少多源交叉确认，建议用 OpenAlex/Crossref/Semantic Scholar 复核。")
    if len(review.papers) < 5:
        gaps.append("原始候选过少，可能是检索式过窄或文献源限流。")
    return gaps


def _source_actions(review: LiteratureReview) -> list[str]:
    actions: list[str] = []
    for item in review.source_health or []:
        source = str(item.get("source") or "")
        status = str(item.get("status") or "")
        returned = int(item.get("returned") or 0)
        if source == "semantic_scholar" and (item.get("rate_limited") or status == "rate_limited"):
            actions.append("设置 SEMANTIC_SCHOLAR_API_KEY 后重跑，降低 429 限流导致的弱结果。")
        elif status in {"failed", "partial"} and returned == 0:
            actions.append(f"{source} 没有返回可用结果，检查网络/API key，或暂时从 sources 中移除。")
    if any("检索失败" in item for item in review.source_diagnostics):
        actions.append("查看 01-literature-source-health，优先修复失败最多的来源再重跑检索。")
    return _unique(actions)


def _required_actions(coverage_gaps: list[str], source_actions: list[str], queries: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if source_actions:
        actions.append("先处理文献源动作，再用当前 snowball queries 重跑在线检索。")
    if coverage_gaps:
        actions.append("把高优先级 seed paper DOI/标题加入人工种子文献或下一轮检索式。")
    if queries:
        actions.append("优先执行 priority >= 90 的 exact title / DOI 查询，确认核心 seed 的相关 work 和 cited-by。")
    if not actions:
        actions.append("当前 seed 足够进入人工审核；下一轮可按扩展检索式补 benchmark/baseline 文献。")
    return actions


def _status(seeds: list[dict[str, Any]], coverage_gaps: list[str], source_actions: list[str]) -> str:
    if len(seeds) < 3:
        return "needs_seed_papers"
    if source_actions:
        return "needs_source_repair"
    if coverage_gaps:
        return "needs_snowball"
    return "ready_for_review"


def _priority(score: float, doi: str, sources: list[Any]) -> int:
    value = int(score * 100)
    if doi:
        value += 8
    if len(set(str(source) for source in sources)) >= 2:
        value += 5
    return min(100, max(0, value))


def _terms(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "that", "this", "from", "into", "using", "review", "survey"}
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return [term.replace("-", "_") for term in terms if term not in stop]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
