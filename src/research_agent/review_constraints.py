from __future__ import annotations

from typing import Any
import re
from .artifacts import cell as _cell


REVIEW_CONSTRAINTS_JSON = "01-review-constraints.json"
REVIEW_CONSTRAINTS_MD = "01-review-constraints.md"


def build_review_constraints(topic: str, feedback: dict[str, Any]) -> dict[str, Any]:
    notes = _feedback_notes(feedback)
    constraints: list[dict[str, Any]] = []
    for index, note in enumerate(notes, start=1):
        category = _category(note)
        priority = _priority(note)
        constraints.append(
            {
                "id": f"RC{index:02d}",
                "category": category,
                "priority": priority,
                "text": note,
                "action": _action(category, note),
                "applies_to": _applies_to(category),
            }
        )
    warnings = []
    if feedback.get("approved") is True and not constraints:
        warnings.append("审核已批准但没有记录额外约束，后续阶段只使用默认文献 gate。")
    agent_text = _agent_text(constraints)
    return {
        "topic": topic,
        "approved": feedback.get("approved") is True,
        "revision_requested": feedback.get("revision_requested") is True,
        "constraints": constraints,
        "warnings": warnings,
        "agent_text": agent_text,
    }


def render_review_constraints_markdown(report: dict[str, Any]) -> str:
    constraints = report.get("constraints") if isinstance(report.get("constraints"), list) else []
    lines = [
        f"# 审核约束：{report.get('topic') or '未命名课题'}",
        "",
        f"- 状态：{'已批准' if report.get('approved') is True else '已退回' if report.get('revision_requested') is True else '待审核'}",
        f"- 约束数：{len(constraints)}",
        "",
    ]
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    lines.extend(
        [
            "## 约束表",
            "| ID | 优先级 | 类别 | 作用阶段 | 约束 | 落实动作 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not constraints:
        lines.append("| - | - | - | - | 无额外人工约束 | - |")
    for item in constraints:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("id") or "")),
                    _cell(str(item.get("priority") or "")),
                    _cell(str(item.get("category") or "")),
                    _cell(", ".join(str(value) for value in item.get("applies_to", []) if str(value).strip())),
                    _cell(str(item.get("text") or "")),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    agent_text = str(report.get("agent_text") or "").strip()
    lines.extend(["", "## 给 Agent 的强约束文本", agent_text or "无额外人工约束"])
    return "\n".join(lines)


def constraints_agent_text(report: dict[str, Any]) -> str:
    return str(report.get("agent_text") or "").strip()


def _feedback_notes(feedback: dict[str, Any]) -> list[str]:
    values: list[str] = []
    current = str(feedback.get("notes") or "").strip()
    if current:
        values.append(current)
    items = feedback.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            note = str(item.get("notes") or "").strip()
            if note:
                values.append(note)
    deduped: list[str] = []
    for value in values:
        normalized = re.sub(r"\s+", " ", value).strip()
        for note in _split_note(normalized):
            if note and not _is_status_summary(note) and note not in deduped:
                deduped.append(note)
    return deduped


def _split_note(value: str) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in re.split(r"[；;。\n]+|(?<=[.!?])\s+(?=[A-Z\u4e00-\u9fff])", value) if part.strip()]
    expanded: list[str] = []
    for part in parts:
        if "并" in part and len(part) <= 80:
            expanded.extend(piece.strip() for piece in part.split("并") if piece.strip())
        else:
            expanded.append(part)
    return expanded or [value]


def _is_status_summary(text: str) -> bool:
    normalized = _normalized_status_text(text)
    if re.fullmatch(r"\d+\s+(configured|successful)\s+sources", normalized):
        return True
    if re.fullmatch(r"\d+/\d+\s+curated\s+seeds", normalized):
        return True
    if re.fullmatch(r"metadata\s+resolved\s*=?\s*\d+", normalized):
        return True
    return normalized.startswith(
        (
            "coverage passed",
            "manual review",
            "no blocking citation",
            "paper grade literature passed",
            "seed role coverage pass",
        )
    )


def _normalized_status_text(text: str) -> str:
    return re.sub(r"[\s_-]+", " ", text.strip().lower()).strip(" .)")


def _category(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ["baseline", "rrt", "prm", "chomp", "stomp", "trajopt", "svm", "cnn", "transformer"]) or any(term in text for term in ["对照", "比较"]):
        return "baseline"
    if any(term in lower for term in ["doi", "paper", "reference", "citation", "seed"]) or any(term in text for term in ["文献", "引用", "种子"]):
        return "literature"
    if any(term in lower for term in ["metric", "f1", "accuracy", "collision", "runtime"]) or any(term in text for term in ["指标", "成功率", "耗时", "碰撞"]):
        return "metric"
    if any(term in lower for term in ["benchmark", "reproduc", "seed"]) or any(term in text for term in ["复现", "重复", "随机种子", "公开数据集"]):
        return "reproducibility"
    if any(term in lower for term in ["scope", "exclude", "only"]) or any(term in text for term in ["收窄", "限定", "范围", "排除", "不要", "只"]):
        return "scope"
    if any(term in lower for term in ["safe", "permission", "command"]) or any(term in text for term in ["安全", "权限", "命令", "白名单"]):
        return "safety"
    return "general"


def _priority(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ["must", "required", "block"]) or any(term in text for term in ["必须", "强制", "不允许", "不要", "阻断", "补"]):
        return "high"
    if any(term in lower for term in ["should", "recommend"]) or any(term in text for term in ["建议", "最好"]):
        return "medium"
    return "medium"


def _applies_to(category: str) -> list[str]:
    mapping = {
        "baseline": ["ideation", "experiment_plan"],
        "literature": ["ideation", "paper"],
        "metric": ["experiment_plan", "analysis"],
        "reproducibility": ["experiment_plan", "runbook"],
        "scope": ["ideation", "experiment_plan"],
        "safety": ["experiment_plan", "execution"],
        "general": ["ideation", "experiment_plan"],
    }
    return mapping.get(category, mapping["general"])


def _action(category: str, note: str) -> str:
    if category == "baseline":
        return "在 idea.baseline 和实验变量中显式加入该对照要求。"
    if category == "literature":
        return "在 idea 的文献依据、gap_alignment 或后续引用核对中落实该要求。"
    if category == "metric":
        return "在实验 metrics 和 protocol 中加入该测量要求。"
    if category == "reproducibility":
        return "在实验 protocol、repeats、随机种子或 runbook 中记录该复现要求。"
    if category == "scope":
        return "在 idea 假设和实验范围中收窄问题边界。"
    if category == "safety":
        return "在实验计划中保持安全执行边界，不放宽命令权限。"
    return f"后续 idea 与实验计划必须响应：{note}"


def _agent_text(constraints: list[dict[str, Any]]) -> str:
    if not constraints:
        return ""
    lines = ["结构化审核约束："]
    for item in constraints:
        lines.append(
            f"- {item['id']} [{item['priority']}/{item['category']}]: {item['text']} -> {item['action']}"
        )
    return "\n".join(lines)


