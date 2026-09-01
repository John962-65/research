from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .human_gate_audit import HUMAN_GATE_AUDIT_JSON, HUMAN_GATE_AUDIT_MD, write_human_gate_audit_artifacts
from .artifacts import cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json


def backfill_human_gate_audits(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        exists = (run_dir / HUMAN_GATE_AUDIT_JSON).exists() and (run_dir / HUMAN_GATE_AUDIT_MD).exists()
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", _read_json(run_dir / HUMAN_GATE_AUDIT_JSON)))
            continue
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, "would_overwrite" if exists else "would_write", {}))
            continue
        try:
            audit = write_human_gate_audit_artifacts(_topic_from_state(run_dir), run_dir)
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append({"run_id": run_dir.name, "action": "error", "error": str(exc)})
            continue
        report["written"] += 1
        report["items"].append(_item(run_dir, "overwrite" if exists else "write", audit))
    return report


def render_human_gate_audit_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Human Gate Audit Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入审计：{report.get('written', 0)}",
        f"- 将写入审计：{report.get('would_write', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 13-human-gate-audit.*；不会补写 approval、不会批准 review/execution gate、不会恢复 pipeline。",
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
                "| Run | Action | Status | Review | Downstream | Execution | Blocking | Manual |",
                "| --- | --- | --- | --- | ---: | --- | ---: | ---: |",
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
                        _cell("approved" if item.get("review_approved") else "not_approved"),
                        str(item.get("downstream_artifacts") or 0),
                        _cell(str(item.get("execution_mode") or "-")),
                        str(item.get("blocking_issues") or 0),
                        str(item.get("manual_tasks") or 0),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, audit: dict[str, Any]) -> dict[str, Any]:
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": audit.get("status", ""),
        "review_approved": summary.get("review_approved") is True,
        "downstream_artifacts": _safe_int(summary.get("downstream_artifacts")),
        "execution_mode": summary.get("execution_mode", ""),
        "blocking_issues": len(audit.get("blocking_issues", [])) if isinstance(audit.get("blocking_issues"), list) else 0,
        "manual_tasks": len(audit.get("manual_tasks", [])) if isinstance(audit.get("manual_tasks"), list) else 0,
    }


def _topic_from_state(run_dir: Path) -> str:
    state = _read_json(run_dir / "state.json")
    return str(state.get("topic") or run_dir.name)


