from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import LiteratureReview, ResearchIdea


NOVELTY_AUDIT_JSON = "02-novelty-audit.json"
NOVELTY_AUDIT_MD = "02-novelty-audit.md"


def write_novelty_audit_artifacts(topic: str, ideas: list[ResearchIdea], review: LiteratureReview, run_dir: Path) -> dict[str, Any]:
    report = build_novelty_audit(topic, ideas, review)
    write_json(run_dir / NOVELTY_AUDIT_JSON, report)
    write_text(run_dir / NOVELTY_AUDIT_MD, render_novelty_audit_markdown(report))
    return report


def build_novelty_audit(topic: str, ideas: list[ResearchIdea], review: LiteratureReview) -> dict[str, Any]:
    items = [_audit_idea(idea, review) for idea in ideas]
    likely_duplicates = sum(1 for item in items if item["decision"] == "likely_duplicate")
    review_required = sum(1 for item in items if item["decision"] == "review_required")
    warnings: list[str] = []
    if likely_duplicates:
        warnings.append(f"{likely_duplicates} 个 idea 与已纳入文献高度相似，进入实验前需要人工确认新颖性。")
    if review_required:
        warnings.append(f"{review_required} 个 idea 需要人工复核 novelty 边界。")
    if not items:
        warnings.append("没有 idea，无法执行 novelty audit。")
    return {
        "topic": topic,
        "total_ideas": len(items),
        "likely_duplicates": likely_duplicates,
        "review_required": review_required,
        "items": items,
        "warnings": warnings,
    }


def render_novelty_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Idea 新颖性审计：{report.get('topic') or ''}",
        "",
        f"- Idea 数：{report.get('total_ideas', 0)}",
        f"- 高重复风险：{report.get('likely_duplicates', 0)}",
        f"- 需人工复核：{report.get('review_required', 0)}",
        "",
    ]
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    lines.extend(
        [
            "## 审计表",
            "| 决策 | 新颖性分 | 重复风险 | Idea | 最相似文献 | 相似度 | 共享术语 | 说明 |",
            "| --- | ---: | ---: | --- | --- | ---: | --- | --- |",
        ]
    )
    for item in report.get("items", []):
        if not isinstance(item, dict):
            continue
        closest = item.get("closest_paper") if isinstance(item.get("closest_paper"), dict) else {}
        closest_label = f"{closest.get('title') or '-'} ({closest.get('year') or 'n.d.'})"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("decision") or "")),
                    f"{float(item.get('novelty_score') or 0):.3f}",
                    f"{float(item.get('duplicate_risk') or 0):.3f}",
                    _cell(str(item.get("idea_title") or "")),
                    _cell(closest_label),
                    f"{float(closest.get('similarity') or 0):.3f}",
                    _cell(", ".join(str(term) for term in item.get("shared_terms", [])[:8])),
                    _cell(str(item.get("note") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- `likely_duplicate` 不会自动删除 idea，但探索图会降低其分支得分。",
            "- 人工可打开最相似文献核对该 idea 是否只是已有工作的复述。",
        ]
    )
    return "\n".join(lines)


def _audit_idea(idea: ResearchIdea, review: LiteratureReview) -> dict[str, Any]:
    idea_terms = set(_terms(_idea_text(idea)))
    best: dict[str, Any] = {"title": "", "year": 0, "sources": [], "similarity": 0.0}
    best_shared: list[str] = []
    for paper in review.papers:
        paper_terms = set(_terms(f"{paper.title} {paper.abstract} {paper.venue}"))
        if not idea_terms or not paper_terms:
            similarity = 0.0
            shared: list[str] = []
        else:
            shared = sorted(idea_terms & paper_terms)
            similarity = len(shared) / max(1, min(len(idea_terms), len(paper_terms)))
        if similarity > float(best["similarity"]):
            best = {
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "url": paper.url,
                "doi": paper.doi,
                "sources": paper.sources or [paper.source],
                "similarity": round(similarity, 4),
            }
            best_shared = shared
    duplicate_risk = float(best["similarity"])
    novelty_score = max(0.0, round(1.0 - duplicate_risk, 4))
    decision = _decision(duplicate_risk, idea)
    return {
        "idea_title": idea.title,
        "decision": decision,
        "novelty_score": novelty_score,
        "duplicate_risk": round(duplicate_risk, 4),
        "closest_paper": best,
        "shared_terms": best_shared[:12],
        "evidence_keys": idea.evidence_keys,
        "baseline": idea.baseline,
        "note": _note(decision, best_shared),
    }


def novelty_item_for_title(report: dict[str, Any] | None, title: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    for item in report.get("items", []):
        if isinstance(item, dict) and str(item.get("idea_title") or "") == title:
            return item
    return {}


def duplicate_penalty(item: dict[str, Any]) -> float:
    decision = str(item.get("decision") or "")
    risk = float(item.get("duplicate_risk") or 0.0)
    if decision == "likely_duplicate":
        return max(4.0, risk * 6.0)
    if decision == "review_required":
        return max(0.75, risk * 1.6)
    return 0.0


def _decision(duplicate_risk: float, idea: ResearchIdea) -> str:
    evidence_count = len(set(idea.evidence_keys + idea.evidence_chunks))
    if duplicate_risk >= 0.58:
        return "likely_duplicate"
    if duplicate_risk >= 0.36 or evidence_count == 0:
        return "review_required"
    return "likely_novel"


def _note(decision: str, shared_terms: list[str]) -> str:
    if decision == "likely_duplicate":
        return "与候选文献共享较多核心术语，建议人工确认不是已有工作的复述。"
    if decision == "review_required":
        return "新颖性边界不够清晰，建议在 hypothesis 或 baseline 中进一步说明差异。"
    return "与已纳入文献未发现高相似风险。"


def _idea_text(idea: ResearchIdea) -> str:
    return " ".join(
        [
            idea.title,
            idea.hypothesis,
            idea.mechanism,
            idea.expected_contribution,
            idea.gap_alignment,
            idea.baseline,
            " ".join(idea.evaluation),
            " ".join(idea.experiment_sketch),
        ]
    )


def _terms(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return [term for term in raw if term not in _STOPWORDS and len(term) <= 40]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


_STOPWORDS = {
    "the",
    "and",
    "with",
    "for",
    "from",
    "this",
    "that",
    "using",
    "method",
    "methods",
    "paper",
    "study",
    "研究",
    "方法",
    "实验",
    "候选",
    "方案",
    "文献",
    "基于",
    "需要",
    "可以",
    "进行",
    "比较",
}
