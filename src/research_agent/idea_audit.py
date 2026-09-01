from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import LiteratureContext, ResearchIdea


IDEA_AUDIT_JSON = "02-idea-audit.json"
IDEA_AUDIT_MD = "02-idea-audit.md"


def write_idea_audit_artifacts(
    topic: str,
    ideas: list[ResearchIdea],
    context: LiteratureContext | None,
    run_dir: Path,
    review_constraints: dict[str, Any] | None = None,
    novelty_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_idea_audit(topic, ideas, context, review_constraints=review_constraints, novelty_audit=novelty_audit)
    write_json(run_dir / IDEA_AUDIT_JSON, report)
    write_text(run_dir / IDEA_AUDIT_MD, render_idea_audit_markdown(report))
    return report


def build_idea_audit(
    topic: str,
    ideas: list[ResearchIdea],
    context: LiteratureContext | None,
    review_constraints: dict[str, Any] | None = None,
    novelty_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = _constraints(review_constraints)
    items = [_audit_idea(index, idea, context, constraints, novelty_audit) for index, idea in enumerate(ideas, start=1)]
    blocked = sum(1 for item in items if item["decision"] == "block")
    review_required = sum(1 for item in items if item["decision"] == "review")
    pass_count = sum(1 for item in items if item["decision"] == "pass")
    warnings: list[str] = []
    if not items:
        warnings.append("没有 idea，无法执行 idea audit。")
    if blocked:
        warnings.append(f"{blocked} 个 idea 使用了不可核对的 citation key 或 chunk id，探索图会强力降权。")
    if review_required:
        warnings.append(f"{review_required} 个 idea 缺少证据、baseline、评估协议、实验草案或人工约束响应。")
    if constraints and not any(item.get("covered_constraints") for item in items):
        warnings.append("已有人工审核约束，但没有任何 idea 明确覆盖这些约束。")
    status = "block" if blocked == len(items) and items else "review" if blocked or review_required or not items else "pass"
    return {
        "topic": topic,
        "status": status,
        "total_ideas": len(items),
        "pass": pass_count,
        "review_required": review_required,
        "blocked": blocked,
        "constraints_checked": len(constraints),
        "items": items,
        "warnings": warnings,
    }


def render_idea_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Idea 证据与约束审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Idea 数：{report.get('total_ideas', 0)}",
        f"- 通过/需复核/阻断：{report.get('pass', 0)}/{report.get('review_required', 0)}/{report.get('blocked', 0)}",
        f"- 已检查人工约束：{report.get('constraints_checked', 0)}",
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
            "| 分支 | 决策 | 证据 | Baseline | 评估 | 实验草案 | 约束覆盖 | 问题 | 动作 |",
            "| --- | --- | ---: | --- | ---: | ---: | --- | --- | --- |",
        ]
    )
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("branch_id") or "")),
                    _cell(str(item.get("decision") or "")),
                    str(item.get("evidence_count") or 0),
                    "yes" if item.get("has_baseline") else "no",
                    str(item.get("evaluation_count") or 0),
                    str(item.get("experiment_steps") or 0),
                    _cell(", ".join(str(value) for value in item.get("covered_constraints", []) if str(value).strip()) or "-"),
                    _cell("; ".join(str(value) for value in item.get("issues", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- 该审计在探索图之前运行，用于检查 idea 是否有可核对证据和可执行实验轮廓。",
            "- `block` 分支不会被删除，但探索图会强力降权，避免无效 citation 或 chunk 进入实验计划。",
            "- `review` 分支需要人工确认缺失项，或在下一轮补充 idea/baseline/metric/seed 文献。",
        ]
    )
    return "\n".join(lines)


def idea_audit_item_for_title(report: dict[str, Any] | None, title: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if isinstance(item, dict) and str(item.get("idea_title") or "") == title:
            return item
    return {}


def idea_audit_penalty(item: dict[str, Any]) -> float:
    decision = str(item.get("decision") or "")
    issue_count = len(item.get("issues", []) if isinstance(item.get("issues"), list) else [])
    if decision == "block":
        return 8.0 + issue_count * 0.5
    if decision == "review":
        return 1.0 + issue_count * 0.25
    return 0.0


def _audit_idea(
    index: int,
    idea: ResearchIdea,
    context: LiteratureContext | None,
    constraints: list[dict[str, Any]],
    novelty_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    known_keys = {item.key for item in context.citations} if context is not None else set()
    known_chunks = {item.chunk_id for item in context.chunks} if context is not None else set()
    invalid_keys = [key for key in idea.evidence_keys if known_keys and key not in known_keys]
    invalid_chunks = [chunk for chunk in idea.evidence_chunks if known_chunks and chunk not in known_chunks]
    evidence_count = len(set(idea.evidence_keys + idea.evidence_chunks))
    issues: list[str] = []
    if invalid_keys:
        issues.append("invalid citation keys: " + ", ".join(invalid_keys[:4]))
    if invalid_chunks:
        issues.append("invalid evidence chunks: " + ", ".join(invalid_chunks[:4]))
    if evidence_count == 0:
        issues.append("missing literature evidence")
    if not idea.baseline.strip():
        issues.append("missing baseline")
    if len(idea.evaluation) < 3:
        issues.append("needs at least 3 evaluation metrics/protocol items")
    if len(idea.experiment_sketch) < 3:
        issues.append("needs at least 3 experiment sketch steps")
    if not idea.gap_alignment.strip():
        issues.append("missing gap alignment")

    covered_constraints, missing_constraints = _constraint_coverage(idea, constraints)
    for constraint_id in missing_constraints:
        issues.append(f"uncovered high-priority review constraint: {constraint_id}")

    novelty_item = _novelty_item_for_title(novelty_audit, idea.title)
    novelty_decision = str(novelty_item.get("decision") or "")
    if novelty_decision == "likely_duplicate":
        issues.append("novelty audit marks likely duplicate")

    if invalid_keys or invalid_chunks:
        decision = "block"
        action = "删除或修正不可核对 citation/chunk 后再进入实验。"
    elif issues:
        decision = "review"
        action = "补齐证据、baseline、评估协议、实验草案或审核约束响应。"
    else:
        decision = "pass"
        action = "可进入探索图分支评分。"

    return {
        "branch_id": f"B{index}",
        "idea_title": idea.title,
        "decision": decision,
        "evidence_count": evidence_count,
        "has_baseline": bool(idea.baseline.strip()),
        "evaluation_count": len(idea.evaluation),
        "experiment_steps": len(idea.experiment_sketch),
        "invalid_evidence_keys": invalid_keys,
        "invalid_evidence_chunks": invalid_chunks,
        "covered_constraints": covered_constraints,
        "missing_constraints": missing_constraints,
        "novelty_decision": novelty_decision,
        "issues": issues,
        "action": action,
    }


def _constraints(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    values = report.get("constraints")
    if not isinstance(values, list):
        return []
    return [dict(item) for item in values if isinstance(item, dict)]


def _constraint_coverage(idea: ResearchIdea, constraints: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    covered: list[str] = []
    missing: list[str] = []
    idea_text = _idea_text(idea)
    idea_terms = set(_terms(idea_text))
    for item in constraints:
        constraint_id = str(item.get("id") or "").strip()
        text = str(item.get("text") or "").strip()
        category = str(item.get("category") or "").strip()
        priority = str(item.get("priority") or "").strip()
        terms = set(_terms(text))
        category_ok = _category_coverage(category, idea)
        text_ok = not terms or bool(idea_terms & terms)
        if category_ok and text_ok:
            covered.append(constraint_id or text[:16])
        elif priority == "high":
            missing.append(constraint_id or text[:16])
    return covered, missing


def _category_coverage(category: str, idea: ResearchIdea) -> bool:
    if category == "baseline":
        return bool(idea.baseline.strip())
    if category == "literature":
        return bool(idea.evidence_keys or idea.evidence_chunks)
    if category == "metric":
        return bool(idea.evaluation)
    if category in {"reproducibility", "safety"}:
        return bool(idea.experiment_sketch)
    if category == "scope":
        return bool(idea.gap_alignment.strip() or idea.hypothesis.strip())
    return bool(_idea_text(idea).strip())


def _novelty_item_for_title(report: dict[str, Any] | None, title: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if isinstance(item, dict) and str(item.get("idea_title") or "") == title:
            return item
    return {}


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
    lower = text.lower()
    ascii_terms = re.findall(r"[a-z][a-z0-9*+-]{1,}", lower)
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    return sorted(set(ascii_terms + cjk_terms))


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
