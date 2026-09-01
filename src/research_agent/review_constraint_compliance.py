from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import ExperimentPlan, ResearchIdea


REVIEW_CONSTRAINT_COMPLIANCE_JSON = "03-review-constraint-compliance.json"
REVIEW_CONSTRAINT_COMPLIANCE_MD = "03-review-constraint-compliance.md"


def write_review_constraint_compliance_artifacts(
    topic: str,
    review_constraints: dict[str, Any] | None,
    selected_idea: ResearchIdea,
    plan: ExperimentPlan,
    run_dir: Path,
    *,
    human_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_review_constraint_compliance_report(topic, review_constraints, selected_idea, plan, human_brief=human_brief)
    write_json(run_dir / REVIEW_CONSTRAINT_COMPLIANCE_JSON, report)
    write_text(run_dir / REVIEW_CONSTRAINT_COMPLIANCE_MD, render_review_constraint_compliance_markdown(report))
    return report


def build_review_constraint_compliance_report(
    topic: str,
    review_constraints: dict[str, Any] | None,
    selected_idea: ResearchIdea,
    plan: ExperimentPlan,
    *,
    human_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_items = _constraints(review_constraints)
    human_items = _human_brief_constraints(human_brief)
    constraints = [*review_items, *human_items]
    items = [_check_constraint(item, selected_idea, plan) for item in constraints]
    blocked = [item for item in items if item["decision"] == "block"]
    manual = [item for item in items if item["decision"] == "review_required"]
    passed = [item for item in items if item["decision"] == "pass"]
    warnings: list[str] = []
    if not constraints:
        warnings.append("没有额外人工审核约束或 human brief 约束；后续仅依赖默认文献 gate、idea audit 和实验审计。")
    if blocked:
        warnings.append(f"{len(blocked)} 条高优先级人工约束没有在选中 idea 或实验计划中落实。")
    if manual:
        warnings.append(f"{len(manual)} 条人工约束需要人工确认或在下一轮补写。")
    status = "block" if blocked else "review_required" if manual else "pass"
    checked = len(items)
    return {
        "topic": topic,
        "status": status,
        "checked_constraints": checked,
        "review_constraints": len(review_items),
        "human_brief_constraints": len(human_items),
        "passed": len(passed),
        "review_required": len(manual),
        "blocked": len(blocked),
        "compliance_rate": round(len(passed) / checked, 3) if checked else 1.0,
        "selected_idea_title": selected_idea.title,
        "experiment_plan_title": plan.idea_title,
        "items": items,
        "blocking_issues": [str(item["action"]) for item in blocked],
        "manual_tasks": [str(item["action"]) for item in manual],
        "warnings": warnings,
    }


def render_review_constraint_compliance_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 人工审核约束落实审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 检查约束：{report.get('checked_constraints', 0)}",
        f"- Review/Human brief：{report.get('review_constraints', 0)}/{report.get('human_brief_constraints', 0)}",
        f"- 通过/需复核/阻断：{report.get('passed', 0)}/{report.get('review_required', 0)}/{report.get('blocked', 0)}",
        f"- 落实率：{report.get('compliance_rate', 0):.3f}",
        f"- 选中 idea：{report.get('selected_idea_title') or '-'}",
        "",
    ]
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    lines.extend(
        [
            "## 检查表",
            "| ID | 来源 | 优先级 | 类别 | 必需落点 | 决策 | 命中 | 缺失 | 动作 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("id") or "")),
                    _cell(str(item.get("source") or "")),
                    _cell(str(item.get("priority") or "")),
                    _cell(str(item.get("category") or "")),
                    _cell(", ".join(str(value) for value in item.get("required_surfaces", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("decision") or "")),
                    _cell(", ".join(str(value) for value in item.get("matched_terms", []) if str(value).strip()) or "-"),
                    _cell(", ".join(str(value) for value in item.get("missing_surfaces", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- 该审计把 `01-review-constraints` 中的人工意见映射到选中 idea 和 `03-experiment-plan`。",
            "- 如果存在 `00-human-brief`，其中的人工约束、成功标准、资源限制和已知风险也会作为同一张检查表核对。",
            "- 高优先级约束缺失会进入 `block`，并通过实验审计阻止继续执行。",
            "- 中优先级约束缺失会进入 `review_required`，分数卡会把它列为人工待办。",
        ]
    )
    return "\n".join(lines)


def _check_constraint(item: dict[str, Any], selected_idea: ResearchIdea, plan: ExperimentPlan) -> dict[str, Any]:
    constraint_id = str(item.get("id") or "").strip() or "RC"
    category = str(item.get("category") or "general").strip()
    priority = str(item.get("priority") or "medium").strip()
    source = str(item.get("source") or "review_gate").strip()
    text = str(item.get("text") or "").strip()
    required_surfaces = _required_surfaces(item, category)
    terms = _terms(text)
    plan_payload = _plan_payload(plan, category)
    if source == "review_gate" and _is_review_gate_status_summary(text):
        plan_payload = {"text": _plan_text(plan), "category_ok": True}
    surface_results = {
        "selected_idea": _surface_status(category, terms, _idea_payload(selected_idea, category)),
        "experiment_plan": _surface_status(category, terms, plan_payload),
    }
    missing = [surface for surface in required_surfaces if surface_results.get(surface, {}).get("status") != "pass"]
    matched_terms = sorted({term for surface in required_surfaces for term in surface_results.get(surface, {}).get("matched_terms", [])})
    if missing and priority == "high":
        decision = "block"
        action = f"{constraint_id} 未落实：{text}"
    elif missing:
        decision = "review_required"
        action = f"人工确认或补写 {constraint_id}：{text}"
    else:
        decision = "pass"
        action = "已在必需落点中体现。"
    return {
        "id": constraint_id,
        "source": source,
        "priority": priority,
        "category": category,
        "text": text,
        "required_surfaces": required_surfaces,
        "decision": decision,
        "matched_terms": matched_terms,
        "missing_surfaces": missing,
        "surface_results": surface_results,
        "action": action,
    }


def _surface_status(category: str, terms: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    normalized = _normalize(text)
    matched = [term for term in terms if _term_in_text(term, normalized)]
    category_ok = bool(payload.get("category_ok"))
    if category_ok and (not terms or matched):
        status = "pass"
    else:
        status = "missing"
    return {
        "status": status,
        "category_ok": category_ok,
        "matched_terms": matched,
        "checked_category": category,
    }


def _required_surfaces(item: dict[str, Any], category: str) -> list[str]:
    source = str(item.get("source") or "review_gate").strip()
    text = str(item.get("text") or "").strip()
    if source == "review_gate" and _is_review_gate_status_summary(text):
        return ["experiment_plan"]
    if source == "human_brief" and _is_claim_boundary(text):
        return ["experiment_plan"]
    applies_to = [str(value) for value in item.get("applies_to", []) if str(value).strip()] if isinstance(item.get("applies_to"), list) else []
    surfaces: list[str] = []
    if any(value in {"ideation", "paper"} for value in applies_to):
        surfaces.append("selected_idea")
    if any(value in {"experiment_plan", "analysis", "runbook", "execution"} for value in applies_to):
        surfaces.append("experiment_plan")
    if not surfaces:
        if category in {"baseline", "metric", "reproducibility", "scope", "safety"}:
            surfaces.append("experiment_plan")
        else:
            surfaces.append("selected_idea")
    return list(dict.fromkeys(surfaces))


def _is_review_gate_status_summary(text: str) -> bool:
    normalized = _normalize(text).strip(" .)")
    if re.fullmatch(r"\d+\s+(configured|successful)\s+sources", normalized):
        return True
    if re.fullmatch(r"\d+/\d+\s+curated\s+seeds", normalized):
        return True
    if re.fullmatch(r"metadata\s+resolved\s*=?\s*\d+", normalized):
        return True
    return normalized.startswith(
        (
            "coverage passed",
            "paper grade literature passed",
            "seed role coverage pass",
        )
    )


def _is_claim_boundary(text: str) -> bool:
    normalized = _normalize(text)
    return any(token in normalized for token in ["do not claim", "not claim", "不声称", "不要声称", "不宣称", "不要宣称"])


def _idea_payload(idea: ResearchIdea, category: str) -> dict[str, Any]:
    if category == "baseline":
        text = idea.baseline
        ok = bool(idea.baseline.strip())
    elif category == "literature":
        text = " ".join([*idea.evidence_keys, *idea.evidence_chunks, idea.gap_alignment, " ".join(idea.experiment_sketch)])
        ok = bool(idea.evidence_keys or idea.evidence_chunks)
    elif category == "metric":
        text = " ".join(idea.evaluation)
        ok = bool(idea.evaluation)
    elif category in {"reproducibility", "safety"}:
        text = " ".join(idea.experiment_sketch)
        ok = bool(idea.experiment_sketch)
    elif category == "scope":
        text = " ".join([idea.title, idea.hypothesis, idea.gap_alignment])
        ok = bool(idea.hypothesis.strip() or idea.gap_alignment.strip())
    else:
        text = _idea_text(idea)
        ok = bool(text.strip())
    return {"text": text, "category_ok": ok}


def _plan_payload(plan: ExperimentPlan, category: str) -> dict[str, Any]:
    if category == "baseline":
        text = " ".join([plan.baseline, *plan.variables, plan.rationale])
        ok = bool(plan.baseline.strip())
    elif category == "literature":
        text = " ".join([*plan.evidence_keys, plan.rationale, *plan.protocol])
        ok = bool(plan.evidence_keys)
    elif category == "metric":
        text = " ".join([*plan.metrics, *plan.protocol])
        ok = bool(plan.metrics)
    elif category == "reproducibility":
        text = " ".join([*plan.protocol, *plan.metrics, *[command.name for command in plan.commands]])
        ok = bool(plan.protocol and plan.commands)
    elif category == "safety":
        text = " ".join([*plan.protocol, plan.rationale, *[command.name for command in plan.commands], *[" ".join(command.command) for command in plan.commands]])
        ok = bool(plan.commands)
    elif category == "scope":
        text = " ".join([plan.objective, *plan.variables, *plan.protocol, plan.rationale])
        ok = bool(plan.objective.strip())
    else:
        text = _plan_text(plan)
        ok = bool(text.strip())
    return {"text": text, "category_ok": ok}


def _constraints(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    values = report.get("constraints")
    if not isinstance(values, list):
        return []
    constraints = []
    for item in values:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        copied.setdefault("source", "review_gate")
        constraints.append(copied)
    return constraints


def _human_brief_constraints(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(report, dict) or report.get("status") != "provided":
        return []
    items: list[dict[str, Any]] = []
    for index, text in enumerate(_list_values(report.get("constraints")), start=1):
        items.append(
            {
                "id": f"HB-C{index:02d}",
                "source": "human_brief",
                "priority": "high",
                "category": _infer_category(text),
                "text": text,
                "applies_to": ["ideation", "experiment_plan"],
            }
        )
    for index, text in enumerate(_list_values(report.get("success_criteria")), start=1):
        items.append(
            {
                "id": f"HB-S{index:02d}",
                "source": "human_brief",
                "priority": "medium",
                "category": _infer_category(text),
                "text": text,
                "applies_to": ["experiment_plan", "analysis"],
            }
        )
    for index, text in enumerate(_list_values(report.get("resource_limits")), start=1):
        items.append(
            {
                "id": f"HB-R{index:02d}",
                "source": "human_brief",
                "priority": "high",
                "category": "safety",
                "text": text,
                "applies_to": ["experiment_plan", "execution"],
            }
        )
    for index, text in enumerate(_list_values(report.get("risks")), start=1):
        items.append(
            {
                "id": f"HB-K{index:02d}",
                "source": "human_brief",
                "priority": "medium",
                "category": _infer_category(text),
                "text": text,
                "applies_to": ["ideation", "experiment_plan"],
            }
        )
    return items


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _infer_category(text: str) -> str:
    normalized = _normalize(text)
    if any(token in normalized for token in ["baseline", "rrt", "chomp", "stomp", "trajopt", "比较"]):
        return "baseline"
    if any(token in normalized for token in ["metric", "success", "rate", "f1", "auc", "成功率", "指标"]):
        return "metric"
    if any(token in normalized for token in ["seed", "repeat", "random", "复现", "随机", "重复"]):
        return "reproducibility"
    if any(token in normalized for token in ["safe", "allowlist", "smoke", "local", "命令", "安全", "白名单"]):
        return "safety"
    return "general"


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
            " ".join(idea.evidence_keys),
            " ".join(idea.evidence_chunks),
        ]
    )


def _plan_text(plan: ExperimentPlan) -> str:
    return " ".join(
        [
            plan.idea_title,
            plan.objective,
            plan.baseline,
            plan.rationale,
            plan.template_profile,
            " ".join(plan.variables),
            " ".join(plan.metrics),
            " ".join(plan.protocol),
            " ".join(plan.evidence_keys),
            " ".join(command.name for command in plan.commands),
        ]
    )


def _terms(text: str) -> list[str]:
    lowered = text.lower().replace("rrt*", "rrt*")
    ascii_terms = re.findall(r"[a-z][a-z0-9*+.-]{1,}", lowered)
    cjk_text = text
    for stopword in [
        "必须",
        "强制",
        "不允许",
        "不要",
        "建议",
        "最好",
        "比较",
        "补充",
        "补",
        "报告",
        "加入",
        "记录",
        "人工",
        "审核",
        "意见",
        "约束",
        "要求",
        "指标",
    ]:
        cjk_text = cjk_text.replace(stopword, " ")
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", cjk_text)
    return sorted(set(term.strip().lower() for term in [*ascii_terms, *cjk_terms] if _useful_term(term)))


def _useful_term(term: str) -> bool:
    normalized = term.strip().lower()
    if len(normalized) < 2:
        return False
    return normalized not in {
        "must",
        "should",
        "required",
        "recommend",
        "baseline",
        "metric",
        "paper",
        "seed",
        "only",
        "scope",
        "safe",
    }


def _normalize(value: str) -> str:
    return value.lower().replace("rrt star", "rrt*").replace("-", " ").replace("_", " ")


def _term_in_text(term: str, normalized_text: str) -> bool:
    normalized_term = _normalize(term)
    if normalized_term in normalized_text:
        return True
    if normalized_term.endswith("*") and normalized_term.rstrip("*") in normalized_text:
        return True
    return False


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
