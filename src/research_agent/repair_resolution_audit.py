from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


REPAIR_RESOLUTION_AUDIT_JSON = "12-repair-resolution-audit.json"
REPAIR_RESOLUTION_AUDIT_MD = "12-repair-resolution-audit.md"


def write_repair_resolution_audit_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_repair_resolution_audit(topic, run_dir)
    write_json(run_dir / REPAIR_RESOLUTION_AUDIT_JSON, report)
    write_text(run_dir / REPAIR_RESOLUTION_AUDIT_MD, render_repair_resolution_audit_markdown(report))
    return report


def build_repair_resolution_audit(topic: str, run_dir: Path) -> dict[str, Any]:
    resume = _read_json(run_dir / "12-repair-resume-plan.json")
    queue = _read_json(run_dir / "12-repair-queue.json")
    if resume.get("applied") is not True:
        return {
            "topic": topic,
            "status": "not_applicable",
            "resolution_score": 1.0,
            "applied": False,
            "rerun_from": str(resume.get("rerun_from") or ""),
            "original_items": [],
            "remaining_items": [],
            "new_items": [],
            "resolved_items": [],
            "blocking_issues": [],
            "manual_tasks": [],
            "required_actions": ["没有应用 repair-resume；无需修复闭环审计。"],
        }
    original = [item for item in resume.get("repair_items", []) if isinstance(item, dict)]
    current = [item for item in queue.get("items", []) if isinstance(item, dict)]
    remaining, resolved, new_items = _classify_items(original, current)
    blocking_remaining = [item for item in remaining if str(item.get("severity") or "") == "block"]
    review_remaining = [item for item in remaining if str(item.get("severity") or "") in {"high", "medium"}]
    queue_status = str(queue.get("status") or "")
    blocking: list[str] = []
    manual: list[str] = []
    if blocking_remaining:
        blocking.extend(_item_summary(item) for item in blocking_remaining)
    elif queue_status == "blocked_repair_required":
        blocking.append("当前 12-repair-queue 仍为 blocked_repair_required。")
    if review_remaining:
        manual.extend(_item_summary(item) for item in review_remaining)
    elif queue_status == "needs_repair":
        manual.append("当前 12-repair-queue 仍有 high/medium 修复或人工确认项。")
    status = "block" if blocking else "review_required" if manual else "pass"
    total = max(1, len(original))
    score = (len(resolved) + (0.5 * max(0, len(original) - len(resolved) - len(blocking_remaining)))) / total
    return {
        "topic": topic,
        "status": status,
        "resolution_score": round(max(0.0, min(1.0, score)), 3),
        "applied": True,
        "rerun_from": str(resume.get("rerun_from") or ""),
        "queue_status": queue_status,
        "original_items": [_compact_item(item) for item in original],
        "remaining_items": [_compact_item(item) for item in remaining],
        "new_items": [_compact_item(item) for item in new_items],
        "resolved_items": [_compact_item(item) for item in resolved],
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "required_actions": _required_actions(status, blocking, manual),
    }


def render_repair_resolution_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 修复闭环审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 已应用 repair-resume：{'是' if report.get('applied') else '否'}",
        f"- 重跑入口：{report.get('rerun_from') or '-'}",
        f"- 当前修复队列：{report.get('queue_status') or '-'}",
        f"- 闭环分：{float(report.get('resolution_score') or 0.0):.3f}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.extend([f"## {title}"])
        lines.extend(f"- [ ] {item}" for item in values) if values else lines.append("- 无")
        lines.append("")
    for key, title in [("remaining_items", "仍未闭环的原修复项"), ("resolved_items", "已闭环的原修复项"), ("new_items", "新增修复项")]:
        lines.extend([f"## {title}", "| ID | 严重级别 | 类别 | 来源 | 动作 |", "| --- | --- | --- | --- | --- |"])
        items = report.get(key) if isinstance(report.get(key), list) else []
        if items:
            for item in items:
                if isinstance(item, dict):
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _cell(str(item.get("task_id") or "")),
                                _cell(str(item.get("severity") or "")),
                                _cell(str(item.get("category") or "")),
                                _cell(str(item.get("source_artifact") or "")),
                                _cell(str(item.get("action") or "")),
                            ]
                        )
                        + " |"
                    )
        else:
            lines.append("| - | - | - | - | - |")
        lines.append("")
    return "\n".join(lines)


def _classify_items(original: list[dict[str, Any]], current: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    original_keys = {_item_key(item) for item in original}
    current_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in current:
        current_by_key[_item_key(item)] = item
    remaining = [current_by_key[key] for key in original_keys if key in current_by_key]
    resolved = [item for item in original if _item_key(item) not in current_by_key]
    new_items = [item for item in current if _item_key(item) not in original_keys]
    return remaining, resolved, new_items


def _item_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("source_artifact") or "").strip(), str(item.get("category") or "").strip())


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": str(item.get("task_id") or ""),
        "severity": str(item.get("severity") or ""),
        "category": str(item.get("category") or ""),
        "source_artifact": str(item.get("source_artifact") or ""),
        "action": str(item.get("action") or ""),
    }


def _item_summary(item: dict[str, Any]) -> str:
    source = str(item.get("source_artifact") or "-")
    category = str(item.get("category") or "-")
    action = str(item.get("action") or "原修复项仍未闭环。")
    return f"{source}/{category}: {action}"


def _required_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "pass":
        return ["原 repair-resume 修复项已闭环；继续检查 scorecard 和 run integrity。"]
    if status == "block":
        return ["原 repair-resume 修复项仍有阻断，继续从 repair queue 恢复或人工修复来源审计。", *blocking[:4]]
    return ["原 repair-resume 修复项已降级为人工/高优先级待办；人工确认后再归档。", *manual[:4]]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
