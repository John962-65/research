from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .agent_observability_audit import (
    AGENT_OBSERVABILITY_AUDIT_JSON,
    AGENT_OBSERVABILITY_AUDIT_MD,
    write_agent_observability_audit_artifacts,
)


def backfill_agent_observability_audits(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        state_path = run_dir / "state.json"
        if not state_path.exists():
            report["skipped_no_state"] += 1
            continue
        if limit > 0 and candidates >= limit:
            break
        candidates += 1
        report["scanned_runs"] += 1
        target_json = run_dir / AGENT_OBSERVABILITY_AUDIT_JSON
        target_md = run_dir / AGENT_OBSERVABILITY_AUDIT_MD
        exists = target_json.exists() and target_md.exists()
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", target_json))
            continue
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", target_json))
            continue
        try:
            audit = write_agent_observability_audit_artifacts(_topic_from_state(run_dir), run_dir)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", target_json, error=str(exc)))
            continue
        report["written"] += 1
        summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
        report["items"].append(
            _item(
                run_dir,
                action,
                target_json,
                status=str(audit.get("status") or ""),
                manifest_events=_safe_int(summary.get("manifest_events")),
                manifest_artifacts=_safe_int(summary.get("manifest_artifacts")),
                llm_failed_calls=_safe_int(summary.get("llm_failed_calls")),
                blocking_issues=len(audit.get("blocking_issues", [])) if isinstance(audit.get("blocking_issues"), list) else 0,
                manual_tasks=len(audit.get("manual_tasks", [])) if isinstance(audit.get("manual_tasks"), list) else 0,
                warnings=len(audit.get("warnings", [])) if isinstance(audit.get("warnings"), list) else 0,
            )
        )
    return report


def render_agent_observability_backfill_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Observability Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入：{report.get('written', 0)}",
        f"- 将写入：{report.get('would_write', 0)}",
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
        lines.extend(["## Runs", "", "| Run | Action | Status | Events | Artifacts | LLM Failed | Blocking | Manual | Warnings |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
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
                        str(item.get("manifest_events") or 0),
                        str(item.get("manifest_artifacts") or 0),
                        str(item.get("llm_failed_calls") or 0),
                        str(item.get("blocking_issues") or 0),
                        str(item.get("manual_tasks") or 0),
                        str(item.get("warnings") or 0),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, target: Path, **extra: Any) -> dict[str, Any]:
    return {"run_id": run_dir.name, "action": action, "path": str(target), **extra}


def _topic_from_state(run_dir: Path) -> str:
    try:
        data = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return run_dir.name
    if not isinstance(data, dict):
        return run_dir.name
    return str(data.get("topic") or run_dir.name)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
