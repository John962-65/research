from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import LiteratureQualityReport, LiteratureReview, Paper


LITERATURE_METADATA_AUDIT_JSON = "01-literature-metadata-audit.json"
LITERATURE_METADATA_AUDIT_MD = "01-literature-metadata-audit.md"


def write_literature_metadata_audit_artifacts(
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_metadata_audit_report(raw_review, curated_review, quality_report)
    write_json(run_dir / LITERATURE_METADATA_AUDIT_JSON, report)
    write_text(run_dir / LITERATURE_METADATA_AUDIT_MD, render_literature_metadata_audit_markdown(report))
    return report


def build_literature_metadata_audit_report(
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any] | None = None,
) -> dict[str, Any]:
    topic = curated_review.topic or raw_review.topic
    items = [_audit_paper(topic, paper) for paper in curated_review.papers]
    blocked = [item for item in items if item["decision"] == "block"]
    review_required = [item for item in items if item["decision"] == "review_required"]
    passed = [item for item in items if item["decision"] == "pass"]
    verifiability_score = round(
        sum(float(item.get("verifiability_score") or 0.0) for item in items) / max(len(items), 1),
        3,
    )
    source_diversity = len(_source_set(curated_review.papers))
    doi_coverage = _coverage(curated_review.papers, "doi")
    url_coverage = _coverage(curated_review.papers, "url")
    abstract_coverage = sum(1 for paper in curated_review.papers if len(paper.abstract or "") >= 100) / max(len(curated_review.papers), 1)
    warnings: list[str] = []
    if not items:
        warnings.append("没有保留文献可审计，不能进入 idea/实验。")
    if blocked:
        warnings.append(f"{len(blocked)} 篇保留文献存在阻断级 metadata 问题。")
    if review_required:
        warnings.append(f"{len(review_required)} 篇保留文献需要人工核对 DOI/URL/摘要/主题匹配。")
    if source_diversity < 2 and items:
        warnings.append("保留文献来源少于 2 类，去噪和 metadata 交叉验证能力不足。")
    if doi_coverage < 0.5 and items:
        warnings.append(f"保留文献 DOI 覆盖率偏低（{doi_coverage:.0%}）。")
    if abstract_coverage < 0.6 and items:
        warnings.append(f"保留文献摘要覆盖率偏低（{abstract_coverage:.0%}）。")
    status = _status(items, blocked, review_required, verifiability_score)
    return {
        "topic": topic,
        "status": status,
        "raw_papers": len(raw_review.papers),
        "curated_papers": len(curated_review.papers),
        "quality_status": _quality_status(quality_report),
        "source_diversity": source_diversity,
        "doi_coverage": round(doi_coverage, 3),
        "url_coverage": round(url_coverage, 3),
        "abstract_coverage": round(abstract_coverage, 3),
        "verifiability_score": verifiability_score,
        "passed": len(passed),
        "review_required": len(review_required),
        "blocked": len(blocked),
        "items": items,
        "warnings": _unique(warnings),
        "required_actions": _required_actions(status, warnings, blocked, review_required, source_diversity, doi_coverage),
    }


def render_literature_metadata_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 文献 Metadata 审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 原始/保留文献：{report.get('raw_papers', 0)}/{report.get('curated_papers', 0)}",
        f"- 来源多样性：{report.get('source_diversity', 0)}",
        f"- DOI/URL/摘要覆盖率：{float(report.get('doi_coverage') or 0.0):.3f}/{float(report.get('url_coverage') or 0.0):.3f}/{float(report.get('abstract_coverage') or 0.0):.3f}",
        f"- 可核验分：{float(report.get('verifiability_score') or 0.0):.3f}",
        f"- 通过/需复核/阻断：{report.get('passed', 0)}/{report.get('review_required', 0)}/{report.get('blocked', 0)}",
        "",
    ]
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    actions = report.get("required_actions") if isinstance(report.get("required_actions"), list) else []
    if actions:
        lines.extend(["## 必要动作"])
        lines.extend(f"- {item}" for item in actions)
        lines.append("")
    lines.extend(
        [
            "## 文献表",
            "| 决策 | 分数 | 年份 | 来源 | DOI | URL | 文献 | 问题 | 动作 |",
            "| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("decision") or "")),
                    f"{float(item.get('verifiability_score') or 0.0):.3f}",
                    str(item.get("year") or ""),
                    _cell(", ".join(str(value) for value in item.get("sources", []) if str(value).strip())),
                    "yes" if item.get("has_doi") else "no",
                    "yes" if item.get("has_url") else "no",
                    _cell(str(item.get("title") or "")),
                    _cell("; ".join(str(value) for value in item.get("issues", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _audit_paper(topic: str, paper: Paper) -> dict[str, Any]:
    issues: list[str] = []
    blockers: list[str] = []
    title_terms = set(_terms(paper.title))
    topic_terms = set(_terms(topic))
    text_terms = set(_terms(" ".join([paper.title, paper.abstract, paper.venue])))
    topic_overlap = len(topic_terms & text_terms) / max(len(topic_terms), 1) if topic_terms else 0.0
    title_overlap = len(topic_terms & title_terms) / max(len(topic_terms), 1) if topic_terms else 0.0
    sources = sorted(set(paper.sources or [paper.source]))
    current_year = datetime.now(timezone.utc).year

    if not paper.title.strip():
        blockers.append("missing title")
    if not paper.doi:
        issues.append("missing DOI")
    if not paper.url:
        issues.append("missing URL")
    if not paper.authors:
        issues.append("missing authors")
    if not paper.year:
        issues.append("missing year")
    elif paper.year > current_year + 1:
        blockers.append(f"future year {paper.year}")
    elif paper.year < 1900:
        issues.append(f"suspicious year {paper.year}")
    if len(paper.abstract or "") < 80:
        issues.append("thin abstract")
    if topic_terms and topic_overlap < 0.18 and "manual_seed" not in sources:
        issues.append("weak topic metadata match")
    if topic_terms and title_overlap == 0 and topic_overlap < 0.34 and "manual_seed" not in sources:
        issues.append("title weakly matches topic")
    if len(sources) <= 1 and paper.source in {"crossref", "openalex"} and not paper.abstract:
        issues.append("single metadata source without abstract")
    if _looks_like_dataset_or_web_record(paper) and not _topic_dataset_allowed(topic):
        issues.append("dataset/web record needs manual citation check")
    if not paper.doi and not paper.url and len(paper.abstract or "") < 80:
        blockers.append("no locator and thin abstract")

    score = _verifiability_score(paper, sources, topic_overlap, title_overlap)
    if blockers:
        decision = "block"
        action = "替换该文献或补齐 DOI/URL/摘要后再进入 context。"
    elif score < 0.48 or len(issues) >= 4:
        decision = "review_required"
        action = "人工打开题录核对主题、作者、年份和可引用性；必要时加入 DOI seed 后重跑。"
    elif issues:
        decision = "review_required"
        action = "人工抽查 metadata，确认可引用后批准。"
    else:
        decision = "pass"
        action = "可进入 citation/context。"
    return {
        "title": paper.title,
        "year": paper.year,
        "venue": paper.venue,
        "sources": sources,
        "source_count": len(sources),
        "has_doi": bool(paper.doi),
        "has_url": bool(paper.url),
        "has_authors": bool(paper.authors),
        "abstract_chars": len(paper.abstract or ""),
        "topic_overlap": round(topic_overlap, 3),
        "title_overlap": round(title_overlap, 3),
        "verifiability_score": score,
        "decision": decision,
        "issues": _unique([*blockers, *issues]),
        "action": action,
        "doi": paper.doi,
        "url": paper.url,
    }


def _verifiability_score(paper: Paper, sources: list[str], topic_overlap: float, title_overlap: float) -> float:
    score = 0.0
    if paper.doi:
        score += 0.22
    if paper.url:
        score += 0.16
    if paper.authors:
        score += 0.10
    if paper.year:
        score += 0.08
    if len(paper.abstract or "") >= 160:
        score += 0.16
    elif len(paper.abstract or "") >= 80:
        score += 0.08
    score += min(0.14, 0.06 * max(0, len(sources) - 1))
    score += min(0.10, topic_overlap * 0.20)
    score += min(0.04, title_overlap * 0.10)
    if "manual_seed" in sources:
        score += 0.08
    return round(min(1.0, score), 3)


def _status(items: list[dict[str, Any]], blocked: list[dict[str, Any]], review_required: list[dict[str, Any]], verifiability_score: float) -> str:
    if not items:
        return "block"
    if blocked:
        return "block"
    if verifiability_score < 0.45:
        return "block"
    if len(review_required) >= max(2, (len(items) + 1) // 2) or verifiability_score < 0.62:
        return "literature_repair_required"
    if review_required:
        return "review_required"
    return "pass"


def _required_actions(
    status: str,
    warnings: list[str],
    blocked: list[dict[str, Any]],
    review_required: list[dict[str, Any]],
    source_diversity: int,
    doi_coverage: float,
) -> list[str]:
    actions: list[str] = []
    if blocked:
        actions.append("移除或替换 block 文献；不要把无 locator、年份异常或题录缺失的条目放入 context。")
    if review_required:
        actions.append("人工打开 review_required 文献的 DOI/URL，核对标题、作者、年份、venue 和摘要是否匹配课题。")
    if source_diversity < 2:
        actions.append("增加第二个在线来源，或为核心文献补 DOI seed，让 metadata 可交叉验证。")
    if doi_coverage < 0.5:
        actions.append("至少为 benchmark、baseline 和综述类核心文献补 DOI。")
    if status in {"block", "literature_repair_required"}:
        actions.append("处理本审计前不要批准进入 idea/实验；如人工豁免，必须在 approval notes 写明保留理由。")
    if not warnings and not actions:
        actions.append("人工抽查 Top 文献 URL/DOI 后可批准进入 idea/实验。")
    return _unique(actions)


def _source_set(papers: list[Paper]) -> set[str]:
    values: set[str] = set()
    for paper in papers:
        for source in paper.sources or [paper.source]:
            value = str(source).strip().lower()
            if value:
                values.add(value)
    return values


def _coverage(papers: list[Paper], attr: str) -> float:
    if not papers:
        return 0.0
    return sum(1 for paper in papers if getattr(paper, attr)) / len(papers)


def _quality_status(value: LiteratureQualityReport | dict[str, Any] | None) -> str:
    if isinstance(value, dict):
        return str(value.get("confidence_status") or value.get("status") or "")
    if value is None:
        return ""
    return str(getattr(value, "confidence_status", "") or "")


def _looks_like_dataset_or_web_record(paper: Paper) -> bool:
    text = f"{paper.title} {paper.venue}".lower()
    markers = ["dataset", "data center", "tutorial", "web page", "github", "benchmark suite"]
    return any(marker in text for marker in markers)


def _topic_dataset_allowed(topic: str) -> bool:
    lower = topic.lower()
    return "数据集" in topic or "dataset" in lower or "benchmark" in lower


def _terms(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "into",
        "using",
        "from",
        "研究",
        "文献",
        "系统",
        "路径",
        "规划",
        "方法",
        "实验",
    }
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return [term.replace("-", "_") for term in terms if term not in stop]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
