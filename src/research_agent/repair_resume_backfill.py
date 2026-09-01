from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .repair_resume import REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD, build_repair_resume_plan, write_repair_resume_plan_artifacts
from .repair_resume_backlog import backlog_item_from_plan


ACTIVE_QUEUE_STATUSES = {"blocked_repair_required", "needs_repair"}


def backfill_repair_resume_plans(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "stale_existing": 0,
        "refreshed_stale": 0,
        "still_needs_preconditions": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "skipped_no_active_queue": 0,
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
        queue = _read_json(run_dir / "12-repair-queue.json")
        if not _has_active_queue(queue):
            report["skipped_no_active_queue"] += 1
            report["items"].append(_item(run_dir, "skipped_no_active_queue", queue=queue))
            continue
        exists = (run_dir / REPAIR_RESUME_PLAN_JSON).exists() and (run_dir / REPAIR_RESUME_PLAN_MD).exists()
        if exists and not force:
            existing = _read_json(run_dir / REPAIR_RESUME_PLAN_JSON)
            existing_item = _item(run_dir, "existing", queue=queue, plan=existing)
            if not _needs_refresh(existing_item):
                report["skipped_existing"] += 1
                report["items"].append({**existing_item, "action": "skipped_existing"})
                continue
            rebuilt = build_repair_resume_plan(run_dir)
            rebuilt_item = _item(run_dir, "rebuilt", queue=queue, plan=rebuilt)
            if _is_improved(existing_item, rebuilt_item):
                report["stale_existing"] += 1
                if dry_run:
                    report["would_write"] += 1
                    report["items"].append({**rebuilt_item, "action": "would_refresh_stale"})
                    continue
                try:
                    plan = write_repair_resume_plan_artifacts(run_dir, apply=False)
                except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
                    report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
                    report["items"].append(_item(run_dir, "error", queue=queue, error=str(exc)))
                    continue
                report["written"] += 1
                report["refreshed_stale"] += 1
                report["items"].append(_item(run_dir, "refresh_stale", queue=queue, plan=plan))
                continue
            report["still_needs_preconditions"] += 1
            report["skipped_existing"] += 1
            report["items"].append({**existing_item, "action": "skipped_needs_preconditions"})
            continue
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            plan = build_repair_resume_plan(run_dir)
            report["items"].append(_item(run_dir, f"would_{action}", queue=queue, plan=plan))
            continue
        try:
            plan = write_repair_resume_plan_artifacts(run_dir, apply=False)
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", queue=queue, error=str(exc)))
            continue
        report["written"] += 1
        report["items"].append(_item(run_dir, action, queue=queue, plan=plan))
    return report


def render_repair_resume_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    error_count = _safe_int(report.get("error_count")) if "error_count" in report else len(errors)
    lines = [
        "# Repair Resume Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入预案：{report.get('written', 0)}",
        f"- 将写入预案：{report.get('would_write', 0)}",
        f"- 旧预案可刷新：{report.get('stale_existing', 0)}",
        f"- 已刷新旧预案：{report.get('refreshed_stale', 0)}",
        f"- 仍缺前置条件：{report.get('still_needs_preconditions', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 无 active repair queue 跳过：{report.get('skipped_no_active_queue', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{error_count}",
        "",
        "说明：该回填只生成 12-repair-resume-plan.* 预案，apply=false；不会删除产物、不会恢复 pipeline、不会批准 gate 或执行实验。",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        for item in errors[:20]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('run_id') or '-'}: {item.get('error') or '-'}")
        lines.append("")
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if items:
        lines.extend(
            [
                "## Runs",
                "",
                "| Run | Action | Readiness | Missing | Queue | Queue Items | Plan | Rerun From | Repair Items | Cleanup | Review Gate | Execution Gate | Applied |",
                "| --- | --- | --- | --- | --- | ---: | --- | --- | ---: | ---: | --- | --- | --- |",
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
                        _cell(str(item.get("resume_readiness") or "-")),
                        _cell(", ".join(_string_list(item.get("precondition_codes"))) or "-"),
                        _cell(str(item.get("queue_status") or "-")),
                        str(item.get("queue_items") or 0),
                        _cell(str(item.get("plan_status") or "-")),
                        _cell(str(item.get("rerun_from") or "-")),
                        str(item.get("repair_items") or 0),
                        str((_safe_int(item.get("artifacts_to_remove")) + _safe_int(item.get("directories_to_remove")))),
                        "yes" if item.get("review_reapproval_required") else "no",
                        "yes" if item.get("execution_reapproval_required") else "no",
                        "yes" if item.get("applied") else "no",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _has_active_queue(queue: dict[str, Any]) -> bool:
    if str(queue.get("status") or "") in ACTIVE_QUEUE_STATUSES:
        return True
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "open") == "open" and str(item.get("severity") or "") in {"block", "high", "medium"}:
            return True
    return False


def _item(run_dir: Path, action: str, *, queue: dict[str, Any] | None = None, plan: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    queue = queue or {}
    plan = plan or {}
    queue_summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    queue_items = queue_summary.get("total") if queue_summary else len(queue.get("items", [])) if isinstance(queue.get("items"), list) else 0
    backlog_item = backlog_item_from_plan(run_dir, queue, plan) if queue and plan else {}
    return {
        "run_id": run_dir.name,
        "action": action,
        "queue_status": str(queue.get("status") or ""),
        "queue_items": _safe_int(queue_items),
        "queue_block": _safe_int(queue_summary.get("block")),
        "queue_high": _safe_int(queue_summary.get("high")),
        "queue_medium": _safe_int(queue_summary.get("medium")),
        "plan_status": str(plan.get("status") or ""),
        "can_resume": plan.get("can_resume") is True,
        "rerun_from": str(plan.get("rerun_from") or ""),
        "repair_items": len(plan.get("repair_items", [])) if isinstance(plan.get("repair_items"), list) else 0,
        "retrieval_repair_tasks": len(plan.get("retrieval_repair_tasks", [])) if isinstance(plan.get("retrieval_repair_tasks"), list) else 0,
        "artifacts_to_remove": len(plan.get("artifacts_to_remove", [])) if isinstance(plan.get("artifacts_to_remove"), list) else 0,
        "directories_to_remove": len(plan.get("directories_to_remove", [])) if isinstance(plan.get("directories_to_remove"), list) else 0,
        "review_reapproval_required": plan.get("review_reapproval_required") is True,
        "execution_reapproval_required": plan.get("execution_reapproval_required") is True,
        "resume_readiness": str(backlog_item.get("resume_readiness") or ""),
        "blocking_preconditions": _safe_int(backlog_item.get("blocking_preconditions")),
        "precondition_codes": _string_list(backlog_item.get("precondition_codes")),
        "required_config": _string_list(backlog_item.get("required_config")),
        "applied": plan.get("applied") is True,
        **extra,
    }


def _needs_refresh(item: dict[str, Any]) -> bool:
    return str(item.get("resume_readiness") or "") == "needs_preconditions"


def _is_improved(old: dict[str, Any], new: dict[str, Any]) -> bool:
    old_count = _safe_int(old.get("blocking_preconditions"))
    new_count = _safe_int(new.get("blocking_preconditions"))
    if str(new.get("resume_readiness") or "") == "ready_to_apply" and str(old.get("resume_readiness") or "") != "ready_to_apply":
        return True
    return new_count < old_count


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
