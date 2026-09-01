from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text, cell as _cell
from .models import LiteratureContext


CITATION_COVERAGE_JSON = "10-citation-coverage.json"
CITATION_COVERAGE_MD = "10-citation-coverage.md"


_CITE_RE = re.compile(r"\\cite\{([^}]+)\}")
_BRACKET_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_.:-]*(?:\s*[,;]\s*[A-Za-z][A-Za-z0-9_.:-]*)*)\]")


def write_citation_coverage_artifacts(topic: str, run_dir: Path, context: LiteratureContext) -> dict[str, Any]:
    report = build_citation_coverage_report(topic, run_dir, context)
    write_json(run_dir / CITATION_COVERAGE_JSON, report)
    write_text(run_dir / CITATION_COVERAGE_MD, render_citation_coverage_markdown(report))
    return report


def build_citation_coverage_report(topic: str, run_dir: Path, context: LiteratureContext) -> dict[str, Any]:
    paper_md = _read_text(run_dir / "09-revised-paper.md")
    known_keys = {item.key for item in context.citations}
    marker_counts = Counter(_citation_marker_keys(paper_md, known_keys))
    cited_keys = {key for key in marker_counts if key in known_keys}
    unknown_keys = sorted(key for key in marker_counts if key not in known_keys)
    relevance_by_key = _chunk_relevance_by_key(context)
    item_checks = [_citation_item(citation, marker_counts, relevance_by_key) for citation in context.citations]
    total_context = len(context.citations)
    total_markers = sum(marker_counts.values())
    coverage_ratio = round(len(cited_keys) / total_context, 3) if total_context else 0.0
    diversity_ratio = round(len(cited_keys) / total_markers, 3) if total_markers else 0.0
    max_key, max_count = _dominant_key(marker_counts)
    max_share = round(max_count / total_markers, 3) if total_markers else 0.0
    recent_keys = _recent_keys(context)
    recent_cited = sorted(recent_keys & cited_keys)
    high_relevance_uncited = [
        item["citation_key"]
        for item in item_checks
        if item["cited_count"] == 0 and float(item["max_chunk_relevance"] or 0.0) >= 0.75
    ]
    blocking, manual = _issues(
        total_context=total_context,
        total_markers=total_markers,
        unknown_keys=unknown_keys,
        coverage_ratio=coverage_ratio,
        cited_count=len(cited_keys),
        high_relevance_uncited=high_relevance_uncited,
        recent_keys=recent_keys,
        recent_cited=recent_cited,
        max_share=max_share,
        max_key=max_key,
    )
    score = _score(coverage_ratio, len(cited_keys), total_markers, recent_keys, recent_cited, max_share)
    status = "block" if blocking else "review_required" if manual else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "coverage_score": score,
        "context_citations": total_context,
        "total_citation_markers": total_markers,
        "unique_cited_keys": len(cited_keys),
        "context_coverage_ratio": coverage_ratio,
        "marker_diversity_ratio": diversity_ratio,
        "unknown_citation_keys": unknown_keys,
        "recent_context_keys": sorted(recent_keys),
        "recent_cited_keys": recent_cited,
        "source_balance": {"dominant_key": max_key, "dominant_count": max_count, "dominant_marker_share": max_share},
        "item_checks": item_checks,
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "required_actions": _required_actions(status),
        "evidence_inventory": {
            "paper_chars": len(paper_md),
            "high_relevance_uncited": len(high_relevance_uncited),
            "citation_sources": _source_counts(context, cited_keys),
        },
    }


def render_citation_coverage_markdown(report: dict[str, Any]) -> str:
    balance = report.get("source_balance") if isinstance(report.get("source_balance"), dict) else {}
    lines = [
        f"# Citation Coverage Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 覆盖得分：{float(report.get('coverage_score') or 0.0):.3f}",
        f"- Context 引用：{int(report.get('context_citations') or 0)}",
        f"- 正文 citation markers：{int(report.get('total_citation_markers') or 0)}",
        f"- 唯一已引用 key：{int(report.get('unique_cited_keys') or 0)}",
        f"- Context 覆盖率：{float(report.get('context_coverage_ratio') or 0.0):.3f}",
        f"- 最高占比 key：{balance.get('dominant_key') or '-'} ({float(balance.get('dominant_marker_share') or 0.0):.3f})",
        "",
        "## 阻断问题",
    ]
    blocking = report.get("blocking_issues") if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    manual = report.get("manual_tasks") if isinstance(report.get("manual_tasks"), list) else []
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- 无")
    lines.extend(
        [
            "",
            "## Coverage Matrix",
            "| 决策 | Citation | 年份 | 来源 | 被引次数 | Chunk 相关性 | 标题 | 动作 |",
            "| --- | --- | ---: | --- | ---: | ---: | --- | --- |",
        ]
    )
    items = report.get("item_checks") if isinstance(report.get("item_checks"), list) else []
    if items:
        for item in items:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("decision") or "")),
                        _cell(str(item.get("citation_key") or "")),
                        str(item.get("year") or 0),
                        _cell(str(item.get("source") or "")),
                        str(item.get("cited_count") or 0),
                        f"{float(item.get('max_chunk_relevance') or 0.0):.2f}",
                        _cell(str(item.get("title") or "")),
                        _cell(str(item.get("action") or "-")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - |")
    lines.extend(["", "## 推荐动作"])
    actions = report.get("required_actions") if isinstance(report.get("required_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    return "\n".join(lines)


def _citation_marker_keys(text: str, known_keys: set[str]) -> list[str]:
    keys: list[str] = []
    for match in _CITE_RE.finditer(text):
        keys.extend(_split_keys(match.group(1)))
    for match in _BRACKET_RE.finditer(text):
        group = _split_keys(match.group(1))
        if _looks_like_citation_group(group, known_keys):
            keys.extend(group)
    return keys


def _citation_item(citation: Any, marker_counts: Counter[str], relevance_by_key: dict[str, float]) -> dict[str, Any]:
    key = str(citation.key)
    count = int(marker_counts.get(key, 0))
    relevance = float(relevance_by_key.get(key, 0.0))
    if count:
        decision = "cited"
        action = "无需处理。"
    elif relevance >= 0.75:
        decision = "review"
        action = "该高相关 context 文献未进入正文；人工确认是否应加入相关工作、方法或结果边界。"
    else:
        decision = "not_cited"
        action = "可保留为背景证据；如为核心 baseline/benchmark 文献，应补入正文。"
    return {
        "citation_key": key,
        "title": citation.title,
        "year": int(citation.year or 0),
        "venue": citation.venue,
        "source": citation.source,
        "doi": citation.doi,
        "url": citation.url,
        "cited_count": count,
        "max_chunk_relevance": round(relevance, 3),
        "decision": decision,
        "action": action,
    }


def _issues(
    *,
    total_context: int,
    total_markers: int,
    unknown_keys: list[str],
    coverage_ratio: float,
    cited_count: int,
    high_relevance_uncited: list[str],
    recent_keys: set[str],
    recent_cited: list[str],
    max_share: float,
    max_key: str,
) -> tuple[list[str], list[str]]:
    blocking: list[str] = []
    manual: list[str] = []
    if total_context == 0:
        blocking.append("01-context.json 中没有 citation，无法形成文献到正文覆盖审计。")
    if total_markers == 0:
        blocking.append("修订稿没有可核对的 citation marker，无法证明文献证据进入正文。")
    if unknown_keys:
        blocking.append("正文引用了 01-context 中不存在的 citation key：" + ", ".join(unknown_keys[:8]))
    if total_context >= 5 and coverage_ratio < 0.15:
        blocking.append(f"正文只覆盖 {coverage_ratio:.2f} 的 context 文献，低于最低覆盖要求。")
    elif total_context >= 5 and coverage_ratio < 0.4:
        manual.append(f"正文 context 覆盖率为 {coverage_ratio:.2f}，建议补入更多 curated/core 文献。")
    if total_context >= 3 and cited_count < 3:
        manual.append(f"正文仅引用 {cited_count} 个唯一 context key，文献覆盖过窄。")
    if high_relevance_uncited:
        manual.append("高相关 context 文献未被正文引用：" + ", ".join(high_relevance_uncited[:8]))
    if recent_keys and not recent_cited:
        manual.append("context 中有近年文献，但修订稿没有引用任何近年文献。")
    if total_markers >= 3 and max_share > 0.65:
        manual.append(f"正文 citation 过度集中在 `{max_key}`，占 markers 的 {max_share:.2f}。")
    return _dedupe(blocking), _dedupe(manual)


def _score(
    coverage_ratio: float,
    cited_count: int,
    total_markers: int,
    recent_keys: set[str],
    recent_cited: list[str],
    max_share: float,
) -> float:
    diversity = min(1.0, cited_count / 3.0) if cited_count else 0.0
    recent = 1.0 if not recent_keys else min(1.0, len(recent_cited) / max(1, min(2, len(recent_keys))))
    dominance = 1.0 if total_markers < 3 else max(0.0, 1.0 - max_share)
    return round(max(0.0, min(1.0, coverage_ratio * 0.55 + diversity * 0.25 + recent * 0.10 + dominance * 0.10)), 3)


def _recent_keys(context: LiteratureContext) -> set[str]:
    years = [int(item.year or 0) for item in context.citations if int(item.year or 0) > 0]
    if not years:
        return set()
    threshold = max(years) - 5
    return {item.key for item in context.citations if int(item.year or 0) >= threshold}


def _chunk_relevance_by_key(context: LiteratureContext) -> dict[str, float]:
    relevance: dict[str, float] = {}
    for chunk in context.chunks:
        relevance[chunk.citation_key] = max(relevance.get(chunk.citation_key, 0.0), float(chunk.relevance or 0.0))
    return relevance


def _dominant_key(marker_counts: Counter[str]) -> tuple[str, int]:
    if not marker_counts:
        return "", 0
    key, count = marker_counts.most_common(1)[0]
    return key, int(count)


def _source_counts(context: LiteratureContext, cited_keys: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for citation in context.citations:
        if citation.key not in cited_keys:
            continue
        source = citation.source or "unknown"
        counts[source] = counts.get(source, 0) + 1
    return counts


def _required_actions(status: str) -> list[str]:
    if status == "pass":
        return ["当前文献到正文覆盖可接受；继续人工核对 citation key、DOI、作者和年份。"]
    actions = [
        "把高相关、近年、baseline/benchmark 或人工 seed 文献补入相关工作、方法、结果边界或局限性段落。",
        "避免全文引用集中在单一来源；每个核心主张优先使用可核验 context 文献组合支撑。",
        "修复后重新运行最终审计和投稿检查。",
    ]
    if status == "block":
        actions.insert(0, "先处理未知 citation key 或完全缺失 citation marker 的阻断项。")
    return actions


def _split_keys(value: str) -> list[str]:
    keys: list[str] = []
    for part in re.split(r"[,;]", value):
        key = part.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _looks_like_citation_group(keys: list[str], known_keys: set[str]) -> bool:
    if not keys:
        return False
    if any(key in known_keys for key in keys):
        return True
    return all(re.search(r"\d{4}", key) for key in keys)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


