from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .agent_trajectory import AGENT_TRAJECTORY_JSON, AGENT_TRAJECTORY_MD, write_agent_trajectory_artifacts
from .artifacts import cell as _cell, utc_now as _utc_now


def backfill_agent_trajectories(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        target_json = run_dir / AGENT_TRAJECTORY_JSON
        target_md = run_dir / AGENT_TRAJECTORY_MD
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
            trajectory = write_agent_trajectory_artifacts(_topic_from_state(run_dir), run_dir)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", target_json, error=str(exc)))
            continue
        report["written"] += 1
        summary = trajectory.get("summary") if isinstance(trajectory.get("summary"), dict) else {}
        report["items"].append(
            _item(
                run_dir,
                action,
                target_json,
                status=str(trajectory.get("status") or ""),
                last_event=str(summary.get("last_event") or ""),
            )
        )
    return report


def render_agent_trajectory_backfill_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Trajectory Backfill",
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
        lines.extend(["## Runs", "", "| Run | Action | Status | Last Event |", "| --- | --- | --- | --- |"])
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
                        _cell(str(item.get("last_event") or "-")),
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


