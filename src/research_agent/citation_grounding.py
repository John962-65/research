from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text, cell as _cell
from .models import CitationGroundingItem, CitationGroundingReport, LiteratureContext


CITATION_GROUNDING_JSON = "10-citation-grounding.json"
CITATION_GROUNDING_MD = "10-citation-grounding.md"


_CITE_RE = re.compile(r"\\cite\{([^}]+)\}")
_BRACKET_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_.:-]*(?:\s*[,;]\s*[A-Za-z][A-Za-z0-9_.:-]*)*)\]")
_WORD_RE = re.compile(r"[a-z][a-z0-9_+-]{2,}", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_STOPWORDS = {
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "has",
    "have",
    "into",
    "not",
    "our",
    "paper",
    "research",
    "result",
    "results",
    "study",
    "that",
    "the",
    "this",
    "was",
    "were",
    "with",
}


def write_citation_grounding_artifacts(topic: str, run_dir: Path, context: LiteratureContext) -> CitationGroundingReport:
    report = build_citation_grounding_report(topic, run_dir, context)
    write_json(run_dir / CITATION_GROUNDING_JSON, report)
    write_text(run_dir / CITATION_GROUNDING_MD, render_citation_grounding_markdown(report))
    return report


def build_citation_grounding_report(topic: str, run_dir: Path, context: LiteratureContext) -> CitationGroundingReport:
    paper_source, paper_md = _read_paper_text(run_dir)
    citation_keys = {item.key for item in context.citations}
    chunks_by_key = _chunks_by_key(context)
    markers = _citation_markers(paper_md, citation_keys)
    items = [_evaluate_marker(paper_md, marker, citation_keys, chunks_by_key) for marker in markers]
    total = len(items)
    passed = sum(1 for item in items if item.decision == "pass")
    review = sum(1 for item in items if item.decision == "review")
    blocked = sum(1 for item in items if item.decision == "block")
    score = round((passed + review * 0.45) / total, 3) if total else 0.0
    status = "block" if blocked or not total else "review_required" if review or score < 0.85 else "pass"
    return CitationGroundingReport(
        topic=topic,
        status=status,
        grounding_score=score,
        total_citations=total,
        passed_citations=passed,
        review_citations=review,
        blocked_citations=blocked,
        items=items,
        blocking_issues=_blocking_issues(items, total),
        manual_tasks=_manual_tasks(items, status),
        evidence_inventory={
            "context_citations": len(citation_keys),
            "context_chunks": len(context.chunks),
            "paper_source": paper_source,
            "paper_chars": len(paper_md),
            "unique_cited_keys": len({item.citation_key for item in items}),
        },
    )


def render_citation_grounding_markdown(report: CitationGroundingReport) -> str:
    lines = [
        f"# Citation Grounding：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 分数：{report.grounding_score:.3f}",
        f"- Citation markers：{report.total_citations}",
        f"- 通过/复核/阻断：{report.passed_citations}/{report.review_citations}/{report.blocked_citations}",
        f"- 上下文引用数：{report.evidence_inventory.get('context_citations', 0)}",
        f"- 上下文 chunks：{report.evidence_inventory.get('context_chunks', 0)}",
        f"- 审计文稿：{report.evidence_inventory.get('paper_source') or '-'}",
        "",
        "## 阻断问题",
    ]
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(
        [
            "",
            "## Citation Grounding Matrix",
            "| 决策 | Citation | Marker | Overlap | Terms | Chunks | Claim Window | 问题 |",
            "| --- | --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for item in report.items:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.decision,
                    _cell(item.citation_key),
                    _cell(item.marker),
                    f"{item.overlap_score:.2f}",
                    _cell(", ".join(item.matched_terms[:8]) or "-"),
                    _cell(", ".join(item.chunk_ids[:4]) or "-"),
                    _cell(item.claim_window),
                    _cell("；".join(item.issues) or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _citation_markers(text: str, known_keys: set[str]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for match in _CITE_RE.finditer(text):
        for key in _split_keys(match.group(1)):
            markers.append({"key": key, "marker": match.group(0), "start": match.start(), "end": match.end()})
    for match in _BRACKET_RE.finditer(text):
        content = match.group(1)
        keys = _split_keys(content)
        if not _looks_like_citation_group(keys, known_keys):
            continue
        for key in keys:
            markers.append({"key": key, "marker": match.group(0), "start": match.start(), "end": match.end()})
    markers.sort(key=lambda item: int(item["start"]))
    return markers


def _evaluate_marker(
    paper_md: str,
    marker: dict[str, Any],
    citation_keys: set[str],
    chunks_by_key: dict[str, list[dict[str, str]]],
) -> CitationGroundingItem:
    key = str(marker["key"])
    window = _claim_window(paper_md, int(marker["start"]), int(marker["end"]))
    chunks = chunks_by_key.get(key, [])
    issues: list[str] = []
    if key not in citation_keys:
        issues.append("citation key not found in 01-context.json")
    if key in citation_keys and not chunks:
        issues.append("citation key has no supporting evidence chunk")
    if not window.strip():
        issues.append("citation marker has no local claim window")

    score, terms, best_excerpt, chunk_ids = _best_overlap(window, chunks)
    if key not in citation_keys or not chunks or not window.strip():
        decision = "block"
        grounding_status = "missing"
    elif score >= 0.18 or len(terms) >= 3:
        decision = "pass"
        grounding_status = "grounded"
    else:
        decision = "review"
        grounding_status = "weak_overlap"
        issues.append("local claim has weak lexical overlap with the cited context chunk")
    return CitationGroundingItem(
        citation_key=key,
        marker=str(marker["marker"]),
        decision=decision,
        grounding_status=grounding_status,
        claim_window=_truncate(window, 260),
        overlap_score=round(score, 3),
        matched_terms=terms[:12],
        chunk_ids=chunk_ids[:5],
        support_excerpt=_truncate(best_excerpt, 220),
        issues=issues,
    )


def _best_overlap(window: str, chunks: list[dict[str, str]]) -> tuple[float, list[str], str, list[str]]:
    window_terms = _terms(window)
    if not window_terms or not chunks:
        return 0.0, [], "", []
    best_score = 0.0
    best_terms: list[str] = []
    best_excerpt = ""
    best_chunk_ids: list[str] = []
    for chunk in chunks:
        support_text = " ".join([chunk.get("title", ""), chunk.get("text", "")]).strip()
        support_terms = _terms(support_text)
        if not support_terms:
            continue
        matched = sorted(window_terms & support_terms)
        denominator = max(1, min(len(window_terms), len(support_terms)))
        score = len(matched) / denominator
        if score > best_score or (score == best_score and len(matched) > len(best_terms)):
            best_score = score
            best_terms = matched
            best_excerpt = chunk.get("text", "") or chunk.get("title", "")
            best_chunk_ids = [chunk.get("chunk_id", "") or "-"]
    if best_score > 0:
        return best_score, best_terms, best_excerpt, best_chunk_ids
    return 0.0, [], chunks[0].get("text", "") if chunks else "", [chunks[0].get("chunk_id", "") or "-"] if chunks else []


def _chunks_by_key(context: LiteratureContext) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for chunk in context.chunks:
        result.setdefault(chunk.citation_key, []).append(
            {
                "chunk_id": chunk.chunk_id,
                "title": chunk.title,
                "text": chunk.text,
                "source": chunk.source,
                "url": chunk.url,
            }
        )
    return result


def _claim_window(text: str, start: int, end: int) -> str:
    before_candidates = [text.rfind(delim, 0, start) for delim in ["。", "！", "？", ".", "!", "?", "\n"]]
    after_candidates = [text.find(delim, end) for delim in ["。", "！", "？", ".", "!", "?", "\n"]]
    left = max(before_candidates)
    right_values = [value for value in after_candidates if value >= 0]
    right = min(right_values) if right_values else -1
    if left < 0 or start - left > 220:
        left = max(0, start - 180)
    else:
        left += 1
    if right < 0 or right - end > 220:
        right = min(len(text), end + 180)
    else:
        right += 1
    return " ".join(text[left:right].strip().split())


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = {match.group(0) for match in _WORD_RE.finditer(lowered) if match.group(0) not in _STOPWORDS}
    for match in _CJK_RE.finditer(text):
        seq = match.group(0)
        for size in (2, 3):
            for index in range(0, max(0, len(seq) - size + 1)):
                terms.add(seq[index : index + size])
    return terms


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


def _blocking_issues(items: list[CitationGroundingItem], total: int) -> list[str]:
    if total == 0:
        return ["修订稿未检测到可核对的 citation marker；不能确认正文引用 grounding。"]
    return [f"{item.citation_key}: {'；'.join(item.issues) or item.grounding_status}" for item in items if item.decision == "block"]


def _manual_tasks(items: list[CitationGroundingItem], status: str) -> list[str]:
    tasks: list[str] = []
    for item in items:
        if item.decision == "review":
            tasks.append(f"人工核对 `{item.citation_key}` 附近 claim 是否被对应 chunk 支撑；必要时换引用、补句子或删除 claim。")
        elif item.decision == "block":
            tasks.append(f"修复 `{item.citation_key}`：补入 01-context 证据 chunk、替换 citation key，或删除无法支撑的正文 claim。")
    if status == "pass":
        return []
    return _dedupe(tasks)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_paper_text(run_dir: Path) -> tuple[str, str]:
    for name in ["09-revised-paper.md", "06-paper.md"]:
        text = _read_text(run_dir / name)
        if text.strip():
            return name, text
    return "", ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _truncate(value: str, limit: int) -> str:
    text = " ".join(value.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


