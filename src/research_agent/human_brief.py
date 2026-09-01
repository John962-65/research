from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .config import HumanConfig


HUMAN_BRIEF_JSON = "00-human-brief.json"
HUMAN_BRIEF_MD = "00-human-brief.md"


def write_human_brief_artifacts(topic: str, config: HumanConfig, out_dir: Path) -> dict[str, Any]:
    report = build_human_brief(topic, config)
    write_json(out_dir / HUMAN_BRIEF_JSON, report)
    write_text(out_dir / HUMAN_BRIEF_MD, render_human_brief_markdown(report))
    return report


def load_human_brief(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def build_human_brief(topic: str, config: HumanConfig) -> dict[str, Any]:
    notes = _clean_list(config.notes)
    constraints = _clean_list(config.constraints)
    success_criteria = _clean_list(config.success_criteria)
    resource_limits = _clean_list(config.resource_limits)
    risks = _clean_list(config.risks)
    provided = bool(notes or constraints or success_criteria or resource_limits or risks)
    report = {
        "schema_version": 1,
        "topic": topic,
        "status": "provided" if provided else "not_provided",
        "notes": notes,
        "constraints": constraints,
        "success_criteria": success_criteria,
        "resource_limits": resource_limits,
        "risks": risks,
        "warnings": [] if provided else ["未提供人工 brief；研究计划只能依据课题、历史 run 和开源项目经验生成。"],
    }
    report["agent_prompt_text"] = human_brief_agent_text(report)
    return report


def human_brief_agent_text(report: dict[str, Any]) -> str:
    if report.get("status") != "provided":
        return ""
    lines = ["Human brief constraints:"]
    for key, label in [
        ("notes", "note"),
        ("constraints", "constraint"),
        ("success_criteria", "success"),
        ("resource_limits", "resource"),
        ("risks", "risk"),
    ]:
        for item in _list_values(report.get(key)):
            lines.append(f"- {label}: {item}")
    return "\n".join(lines)


def render_human_brief_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Human Brief：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        "",
    ]
    sections = [
        ("notes", "人工说明"),
        ("constraints", "人工约束"),
        ("success_criteria", "成功标准"),
        ("resource_limits", "资源限制"),
        ("risks", "人工标记风险"),
        ("warnings", "警告"),
    ]
    for key, title in sections:
        values = _list_values(report.get(key))
        if not values:
            continue
        lines.extend([f"## {title}"])
        lines.extend(f"- {item}" for item in values)
        lines.append("")
    lines.extend(
        [
            "## 使用方式",
            "- 这些人工输入会在 `00-research-plan` 生成前进入 planning context。",
            "- 它们不会替代 `01-review-gate` 或 `03-execution-approval`；idea/实验仍必须经过对应人工 gate。",
        ]
    )
    return "\n".join(lines)


def _clean_list(values: Any) -> list[str]:
    if isinstance(values, str):
        values = values.splitlines()
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        item = " ".join(str(value or "").split())
        if not item:
            continue
        if len(item) > 300:
            item = item[:299].rstrip() + "…"
        if item not in cleaned:
            cleaned.append(item)
    return cleaned[:12]


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
