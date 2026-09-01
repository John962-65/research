from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .open_source_compliance import OPEN_SOURCE_COMPLIANCE_JSON, OPEN_SOURCE_COMPLIANCE_MD, write_open_source_compliance_artifacts
from .open_source_lessons import OPEN_SOURCE_LESSONS_JSON, OPEN_SOURCE_LESSONS_MD, write_open_source_lessons_artifacts
from .repair_queue import REPAIR_QUEUE_JSON, write_repair_queue_artifacts
from .artifacts import cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json


def backfill_open_source_compliance(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "scanned_runs": 0,
        "lessons_written": 0,
        "compliance_written": 0,
        "repair_queue_written": 0,
        "would_write_lessons": 0,
        "would_write_compliance": 0,
        "would_write_repair_queue": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "errors": [],
        "items": [],
    }
    candidates = 0
    for run_dir in run_dirs:
        state_path = run_dir / "state.json"
        if not state_path.exists():
            report["skipped_no_state"] += 1
            continue
        if limit > 0 and candidates >= limit:
            break
        candidates += 1
        report["scanned_runs"] += 1
        topic = _topic_from_state(run_dir)
        lessons_exist = (run_dir / OPEN_SOURCE_LESSONS_JSON).exists() and (run_dir / OPEN_SOURCE_LESSONS_MD).exists()
        compliance_exist = (run_dir / OPEN_SOURCE_COMPLIANCE_JSON).exists() and (run_dir / OPEN_SOURCE_COMPLIANCE_MD).exists()
        lessons_data = _read_json(run_dir / OPEN_SOURCE_LESSONS_JSON) if lessons_exist else {}
        compliance = _read_json(run_dir / OPEN_SOURCE_COMPLIANCE_JSON) if compliance_exist else {}
        lessons_stale = lessons_exist and not _has_lesson_contract(lessons_data)
        compliance_stale = compliance_exist and not _has_compliance_contract(compliance)
        needs_lessons = force or not lessons_exist or lessons_stale
        needs_compliance = force or not compliance_exist or needs_lessons or compliance_stale
        needs_repair_queue = _needs_repair_queue_refresh(run_dir, compliance, compliance_will_change=needs_compliance)
        if not needs_lessons and not needs_compliance and not needs_repair_queue:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing"))
            continue
        if dry_run:
            if needs_lessons:
                report["would_write_lessons"] += 1
            if needs_compliance:
                report["would_write_compliance"] += 1
            if needs_repair_queue:
                report["would_write_repair_queue"] += 1
            report["items"].append(
                _item(
                    run_dir,
                    "would_write",
                    lessons=needs_lessons,
                    compliance=needs_compliance,
                    repair_queue=needs_repair_queue,
                    lessons_stale=lessons_stale,
                    compliance_stale=compliance_stale,
                    status=str(compliance.get("status") or ""),
                    score=_safe_float(compliance.get("score")),
                    checked_lessons=_safe_int(compliance.get("checked_lessons")),
                    blocking_issues=len(compliance.get("blocking_issues", [])) if isinstance(compliance.get("blocking_issues"), list) else 0,
                    manual_tasks=len(compliance.get("manual_tasks", [])) if isinstance(compliance.get("manual_tasks"), list) else 0,
                )
            )
            continue
        try:
            lessons_written = False
            if needs_lessons:
                write_open_source_lessons_artifacts(topic, run_dir)
                lessons_written = True
                report["lessons_written"] += 1
            compliance = write_open_source_compliance_artifacts(topic, run_dir) if needs_compliance else _read_json(run_dir / OPEN_SOURCE_COMPLIANCE_JSON)
            if needs_compliance:
                report["compliance_written"] += 1
            repair_queue_written = False
            if _needs_repair_queue_refresh(run_dir, compliance):
                write_repair_queue_artifacts(topic, run_dir)
                repair_queue_written = True
                report["repair_queue_written"] += 1
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", error=str(exc)))
            continue
        report["items"].append(
            _item(
                run_dir,
                "write" if lessons_written or needs_compliance or repair_queue_written else "skipped_existing",
                lessons=lessons_written,
                compliance=needs_compliance,
                repair_queue=repair_queue_written,
                lessons_stale=lessons_stale,
                compliance_stale=compliance_stale,
                status=str(compliance.get("status") or ""),
                score=_safe_float(compliance.get("score")),
                checked_lessons=_safe_int(compliance.get("checked_lessons")),
                blocking_issues=len(compliance.get("blocking_issues", [])) if isinstance(compliance.get("blocking_issues"), list) else 0,
                manual_tasks=len(compliance.get("manual_tasks", [])) if isinstance(compliance.get("manual_tasks"), list) else 0,
            )
        )
    return report


def render_open_source_compliance_backfill_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Open-Source Compliance Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- Lessons 写入：{report.get('lessons_written', 0)}",
        f"- Compliance 写入：{report.get('compliance_written', 0)}",
        f"- Repair Queue 写入：{report.get('repair_queue_written', 0)}",
        f"- 将写入 Lessons：{report.get('would_write_lessons', 0)}",
        f"- 将写入 Compliance：{report.get('would_write_compliance', 0)}",
        f"- 将写入 Repair Queue：{report.get('would_write_repair_queue', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(report.get('errors', [])) if isinstance(report.get('errors'), list) else 0}",
        "",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(["## Errors", ""])
        for item in errors[:20]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('run_id') or '-'}: {item.get('error') or '-'}")
        lines.append("")
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if items:
        lines.extend(["## Runs", "", "| Run | Action | Lessons | Compliance | Repair Queue | Status | Score | Checked | Blocking | Manual |", "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |"])
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("run_id") or "")),
                        _cell(str(item.get("action") or "")),
                        "yes" if item.get("lessons") else "no",
                        "yes" if item.get("compliance") else "no",
                        "yes" if item.get("repair_queue") else "no",
                        _cell(str(item.get("status") or "-")),
                        f"{_safe_float(item.get('score')):.3f}",
                        str(item.get("checked_lessons") or 0),
                        str(item.get("blocking_issues") or 0),
                        str(item.get("manual_tasks") or 0),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, **extra: Any) -> dict[str, Any]:
    return {"run_id": run_dir.name, "action": action, **extra}


def _has_lesson_contract(data: dict[str, Any]) -> bool:
    contract = data.get("contract_summary") if isinstance(data.get("contract_summary"), dict) else {}
    return bool(contract.get("required_lesson_ids") and contract.get("required_project_names"))


def _has_compliance_contract(data: dict[str, Any]) -> bool:
    if _safe_int(data.get("schema_version")) < 3:
        return False
    contract = data.get("contract_summary") if isinstance(data.get("contract_summary"), dict) else {}
    return str(contract.get("status") or "").strip() in {"pass", "block"} and bool(contract.get("required_lesson_ids"))


def _topic_from_state(run_dir: Path) -> str:
    data = _read_json(run_dir / "state.json")
    return str(data.get("topic") or run_dir.name)


def _needs_repair_queue_refresh(run_dir: Path, compliance: dict[str, Any], *, compliance_will_change: bool = False) -> bool:
    if compliance_will_change and not _repair_queue_has_open_source_item(run_dir):
        return True
    if not _compliance_needs_repair(compliance):
        return False
    return not _repair_queue_has_open_source_item(run_dir)


def _compliance_needs_repair(compliance: dict[str, Any]) -> bool:
    status = str(compliance.get("status") or "").strip()
    if status in {"block", "needs_human_review"}:
        return True
    return bool(_list(compliance.get("blocking_issues")) or _list(compliance.get("manual_tasks")))


def _repair_queue_has_open_source_item(run_dir: Path) -> bool:
    queue = _read_json(run_dir / REPAIR_QUEUE_JSON)
    items = _list(queue.get("items"))
    if not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("category") or "") == "open_source_compliance":
            return True
        if str(item.get("source_artifact") or "") == OPEN_SOURCE_COMPLIANCE_JSON:
            return True
    return False


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


