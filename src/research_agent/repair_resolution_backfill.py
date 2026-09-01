from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .repair_resolution_audit import REPAIR_RESOLUTION_AUDIT_JSON, REPAIR_RESOLUTION_AUDIT_MD, build_repair_resolution_audit, render_repair_resolution_audit_markdown


def backfill_repair_resolution_audits(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "scanned_runs": 0,
        "written": 0,
        "would_write": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "skipped_no_repair_inputs": 0,
        "errors": [],
        "items": [],
    }
    candidates = 0
    for run_dir in run_dirs:
        if not (run_dir / "state.json").exists():
            report["skipped_no_state"] += 1
            continue
        if limit > 0 and candidates >= limit:
            break
        candidates += 1
        report["scanned_runs"] += 1
        if not (run_dir / "12-repair-resume-plan.json").exists() and not (run_dir / "12-repair-queue.json").exists():
            report["skipped_no_repair_inputs"] += 1
            report["items"].append(_item(run_dir, "skipped_no_repair_inputs", {}))
            continue
        exists = (run_dir / REPAIR_RESOLUTION_AUDIT_JSON).exists() and (run_dir / REPAIR_RESOLUTION_AUDIT_MD).exists()
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", _read_json(run_dir / REPAIR_RESOLUTION_AUDIT_JSON)))
            continue
        try:
            audit = build_repair_resolution_audit(_topic(run_dir), run_dir)
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, error=str(exc)))
            continue
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", audit))
            continue
        write_json(run_dir / REPAIR_RESOLUTION_AUDIT_JSON, audit)
        write_text(run_dir / REPAIR_RESOLUTION_AUDIT_MD, render_repair_resolution_audit_markdown(audit))
        report["written"] += 1
        report["items"].append(_item(run_dir, action, audit))
    return report


def render_repair_resolution_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Repair Resolution Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入闭环审计：{report.get('written', 0)}",
        f"- 将写入闭环审计：{report.get('would_write', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少 repair 输入跳过：{report.get('skipped_no_repair_inputs', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 12-repair-resolution-audit.*；不会应用 repair-resume、不会删除产物、不会批准 gate 或恢复 pipeline。",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        for item in errors[:20]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('run_id') or '-'}: {item.get('error') or '-'}")
        lines.append("")
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if items:
        lines.extend(
            [
                "## Runs",
                "",
                "| Run | Action | Status | Applied | Rerun From | Score | Remaining | Resolved | New | Blocking | Manual |",
                "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("run_id") or "")),
                        _cell(str(item.get("action") or "")),
                        _cell(str(item.get("status") or "-")),
                        "yes" if item.get("applied") else "no",
                        _cell(str(item.get("rerun_from") or "-")),
                        f"{float(item.get('resolution_score') or 0.0):.3f}",
                        str(item.get("remaining_items") or 0),
                        str(item.get("resolved_items") or 0),
                        str(item.get("new_items") or 0),
                        str(item.get("blocking_issues") or 0),
                        str(item.get("manual_tasks") or 0),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, audit: dict[str, Any], error: str = "") -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": audit.get("status", ""),
        "applied": audit.get("applied") is True,
        "rerun_from": str(audit.get("rerun_from") or ""),
        "resolution_score": _safe_float(audit.get("resolution_score")),
        "remaining_items": _count_list(audit.get("remaining_items")),
        "resolved_items": _count_list(audit.get("resolved_items")),
        "new_items": _count_list(audit.get("new_items")),
        "blocking_issues": _count_list(audit.get("blocking_issues")),
        "manual_tasks": _count_list(audit.get("manual_tasks")),
        "error": error,
    }


def _topic(run_dir: Path) -> str:
    state = _read_json(run_dir / "state.json")
    queue = _read_json(run_dir / "12-repair-queue.json")
    resume = _read_json(run_dir / "12-repair-resume-plan.json")
    return str(state.get("topic") or queue.get("topic") or resume.get("topic") or run_dir.name)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
