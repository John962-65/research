from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .repair_resume import build_repair_resume_plan
from .artifacts import cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json


REPAIR_BACKLOG_STATUSES = {"blocked_repair_required", "needs_repair"}
SEVERITY_RANK = {"block": 3, "high": 2, "medium": 1}


def build_repair_resume_backlog(runs_dir: Path, *, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    items: list[dict[str, Any]] = []
    skipped_no_state = 0
    scanned = 0
    for run_dir in run_dirs:
        if not (run_dir / "state.json").exists():
            skipped_no_state += 1
            continue
        if limit > 0 and scanned >= limit:
            break
        scanned += 1
        queue = _read_json(run_dir / "12-repair-queue.json")
        plan = _read_json(run_dir / "12-repair-resume-plan.json")
        if not _has_active_queue(queue) and not _has_doctor_resume_plan(plan):
            continue
        if not plan:
            plan = build_repair_resume_plan(run_dir)
        items.append(backlog_item_from_plan(run_dir, queue, plan))
    items.sort(key=lambda item: (item["priority_score"], item["queue_items"], item["run_id"]), reverse=True)
    ready = [item for item in items if item.get("can_resume") and not item.get("applied")]
    ready_to_apply = [item for item in ready if item.get("resume_readiness") == "ready_to_apply"]
    needs_preconditions = [item for item in ready if item.get("resume_readiness") == "needs_preconditions"]
    applied = [item for item in items if item.get("applied")]
    blocked = [item for item in items if not item.get("can_resume")]
    review = sum(1 for item in items if item.get("review_reapproval_required"))
    execution = sum(1 for item in items if item.get("execution_reapproval_required"))
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "scanned_runs": scanned,
        "skipped_no_state": skipped_no_state,
        "status": "blocked" if ready or blocked else "pass" if not items else "in_progress",
        "summary": {
            "total": len(items),
            "ready_to_apply": len(ready_to_apply),
            "needs_preconditions": len(needs_preconditions),
            "applied": len(applied),
            "blocked": len(blocked),
            "review_reapproval_required": review,
            "execution_reapproval_required": execution,
            "blocking_preconditions": sum(_safe_int(item.get("blocking_preconditions")) for item in items),
        },
        "items": items,
        "next_actions": _next_actions(ready_to_apply, needs_preconditions, blocked),
    }


def render_repair_resume_backlog_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Repair Resume Backlog",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 状态：{report.get('status') or '-'}",
        f"- 扫描 run：{report.get('scanned_runs') or 0}",
        f"- 待处理：{summary.get('total') or 0}",
        f"- 可直接预览/应用：{summary.get('ready_to_apply') or 0}",
        f"- 需先补前置条件：{summary.get('needs_preconditions') or 0}",
        f"- 已应用：{summary.get('applied') or 0}",
        f"- 前置阻断：{summary.get('blocking_preconditions') or 0}",
        f"- 需要 review 重新批准：{summary.get('review_reapproval_required') or 0}",
        f"- 需要 execution 重新批准：{summary.get('execution_reapproval_required') or 0}",
        "",
        "说明：该报告只读取 repair queue 和 repair-resume plan；不删除产物、不批准 gate、不恢复 pipeline、不执行实验。",
        "",
        "## 优先队列",
        "",
        "| Run | Priority | Readiness | Queue | Plan | Rerun From | Tasks | Cleanup | Gates | Preconditions | Command |",
        "| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- | ---: | --- |",
    ]
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if not items:
        lines.append("| - | 0 | - | - | - | - | 0 | 0 | - | 0 | - |")
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        gates = ",".join(value for value in ["review" if item.get("review_reapproval_required") else "", "execution" if item.get("execution_reapproval_required") else ""] if value) or "-"
        plan_label = _plan_label(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("run_id") or "")),
                    str(item.get("priority_score") or 0),
                    _cell(str(item.get("resume_readiness") or "-")),
                    _cell(f"{item.get('queue_status') or '-'} B{item.get('queue_block') or 0}/H{item.get('queue_high') or 0}/M{item.get('queue_medium') or 0}"),
                    _cell(plan_label),
                    _cell(str(item.get("rerun_from") or "-")),
                    str(item.get("repair_items") or 0),
                    str((item.get("artifacts_to_remove") or 0) + (item.get("directories_to_remove") or 0)),
                    _cell(gates),
                    str(item.get("blocking_preconditions") or 0),
                    "`" + _cell(str(item.get("command") or "")) + "`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## 前置条件摘要", "", "| Run | Readiness | Required Config | Gate Reapproval | Missing |", "| --- | --- | --- | --- | --- |"])
    if not items:
        lines.append("| - | - | - | - | - |")
    for item in items[:100]:
        if not isinstance(item, dict):
            continue
        gates = ",".join(value for value in ["review" if item.get("review_reapproval_required") else "", "execution" if item.get("execution_reapproval_required") else ""] if value) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("run_id") or "")),
                    _cell(str(item.get("resume_readiness") or "-")),
                    _cell(", ".join(_string_list(item.get("required_config"))) or "-"),
                    _cell(gates),
                    _cell(", ".join(_string_list(item.get("precondition_codes"))) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 下一步"])
    actions = report.get("next_actions") if isinstance(report.get("next_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无。")
    return "\n".join(lines)


def backlog_item_from_plan(run_dir: Path, queue: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    queue_block = _safe_int(summary.get("block")) or _count_items(items, "block")
    queue_high = _safe_int(summary.get("high")) or _count_items(items, "high")
    queue_medium = _safe_int(summary.get("medium")) or _count_items(items, "medium")
    queue_items = _safe_int(summary.get("total")) or len(items)
    repair_items = plan.get("repair_items") if isinstance(plan.get("repair_items"), list) else []
    artifacts = plan.get("artifacts_to_remove") if isinstance(plan.get("artifacts_to_remove"), list) else []
    dirs = plan.get("directories_to_remove") if isinstance(plan.get("directories_to_remove"), list) else []
    can_resume = plan.get("can_resume") is True
    applied = plan.get("applied") is True
    triage = _resume_triage(plan, queue)
    doctor_report_path = str(plan.get("doctor_report_path") or "").strip()
    return {
        "run_id": run_dir.name,
        "queue_status": str(queue.get("status") or ""),
        "queue_items": queue_items,
        "queue_block": queue_block,
        "queue_high": queue_high,
        "queue_medium": queue_medium,
        "plan_status": str(plan.get("status") or ""),
        "can_resume": can_resume,
        "applied": applied,
        "rerun_from": str(plan.get("rerun_from") or ""),
        "repair_items": len(repair_items),
        "retrieval_repair_tasks": len(plan.get("retrieval_repair_tasks", [])) if isinstance(plan.get("retrieval_repair_tasks"), list) else 0,
        "artifacts_to_remove": len(artifacts),
        "directories_to_remove": len(dirs),
        "review_reapproval_required": plan.get("review_reapproval_required") is True,
        "execution_reapproval_required": plan.get("execution_reapproval_required") is True,
        "resume_readiness": triage["resume_readiness"],
        "required_config": triage["required_config"],
        "precondition_codes": triage["precondition_codes"],
        "blocking_preconditions": len(triage["precondition_codes"]),
        "triage_notes": triage["triage_notes"],
        "repair_plan_sources": _string_list(plan.get("repair_plan_sources")),
        "doctor_report": bool(doctor_report_path),
        "doctor_report_path": doctor_report_path,
        "priority_score": queue_block * 100 + queue_high * 10 + queue_medium + (0 if applied else 8 if triage["resume_readiness"] == "ready_to_apply" else 4 if can_resume else 1),
        "command": _repair_resume_command(run_dir, plan),
    }


def _resume_triage(plan: dict[str, Any], queue: dict[str, Any]) -> dict[str, Any]:
    if plan.get("applied") is True:
        return {
            "resume_readiness": "applied",
            "required_config": [],
            "precondition_codes": [],
            "triage_notes": ["repair_resume_already_applied"],
        }
    if plan.get("can_resume") is not True:
        return {
            "resume_readiness": "blocked_plan",
            "required_config": [],
            "precondition_codes": ["plan_not_resumable"],
            "triage_notes": ["rebuild_repair_queue_or_resume_plan"],
        }
    rerun_from = str(plan.get("rerun_from") or "")
    required_config: list[str] = []
    codes: list[str] = []
    notes: list[str] = []
    recommended_config = plan.get("recommended_config") if isinstance(plan.get("recommended_config"), dict) else {}
    recommended_execution = plan.get("recommended_execution_config") if isinstance(plan.get("recommended_execution_config"), dict) else {}
    recommended_release = plan.get("recommended_release_config") if isinstance(plan.get("recommended_release_config"), dict) else {}
    retrieval_tasks = [
        item
        for item in (plan.get("retrieval_repair_tasks") if isinstance(plan.get("retrieval_repair_tasks"), list) else [])
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    ]
    seed_papers = plan.get("recommended_seed_papers") if isinstance(plan.get("recommended_seed_papers"), list) else []
    repair_items = plan.get("repair_items") if isinstance(plan.get("repair_items"), list) else []
    categories = {str(item.get("category") or "") for item in repair_items if isinstance(item, dict)}
    if rerun_from in {"literature_review", "literature_context"}:
        required_config.extend(["literature_provider", "review_approval"])
        if not recommended_config and not retrieval_tasks and not seed_papers:
            codes.append("missing_literature_repair_config")
        if plan.get("review_reapproval_required") is not True:
            codes.append("missing_review_reapproval_marker")
    if plan.get("execution_reapproval_required") is True:
        required_config.append("execution_approval")
    if categories & {"benchmark_readiness", "benchmark_result_schema", "benchmark_evidence"}:
        required_config.append("benchmark_manifest")
        if not recommended_execution.get("benchmark_manifest_paths"):
            codes.append("missing_benchmark_manifest_recommendation")
        paper_grade_status = str(recommended_execution.get("benchmark_paper_grade_status") or "")
        if paper_grade_status and paper_grade_status != "ready":
            required_config.append("paper_grade_benchmark_manifest")
            codes.append("missing_paper_grade_benchmark_manifest_set")
            if isinstance(recommended_execution.get("benchmark_manifest_scaffolds"), list) and recommended_execution.get("benchmark_manifest_scaffolds"):
                notes.append("benchmark_manifest_scaffold_available")
    if categories & {"execution_safety"}:
        required_config.append("allowed_commands")
        if not recommended_execution.get("allowed_commands"):
            codes.append("missing_allowed_command_recommendation")
    if categories & {"release", "release_metadata", "code_data_availability"}:
        required_config.append("release_metadata")
        release_required = _string_list(recommended_release.get("required_fields"))
        if not recommended_release or not release_required:
            codes.append("missing_release_metadata_recommendation")
        elif not _release_required_values_present(recommended_release, release_required):
            codes.append("release_metadata_values_required")
            if _string_list(recommended_release.get("cli_args")):
                notes.append("release_metadata_cli_args_available")
    if str(queue.get("status") or "") not in REPAIR_BACKLOG_STATUSES:
        notes.append("queue_status_from_open_items")
    if not repair_items:
        codes.append("missing_repair_items")
    readiness = "needs_preconditions" if codes else "ready_to_apply"
    return {
        "resume_readiness": readiness,
        "required_config": _dedupe(required_config),
        "precondition_codes": _dedupe(codes),
        "triage_notes": _dedupe(notes),
    }


def _release_required_values_present(recommended_release: dict[str, Any], required_fields: list[str]) -> bool:
    config_fields = recommended_release.get("config_fields") if isinstance(recommended_release.get("config_fields"), dict) else {}
    field_actions = recommended_release.get("field_actions") if isinstance(recommended_release.get("field_actions"), dict) else {}
    for field in required_fields:
        action = field_actions.get(field) if isinstance(field_actions.get(field), dict) else {}
        metadata_key = str(action.get("metadata_key") or "").strip()
        values = []
        if metadata_key:
            values.append(config_fields.get(metadata_key))
        values.append(action.get("recommended_value"))
        if not any(str(value or "").strip() for value in values):
            return False
    return True


def _next_actions(ready: list[dict[str, Any]], needs_preconditions: list[dict[str, Any]], blocked: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if ready:
        first = ready[0]
        actions.append(f"先处理 {first.get('run_id')}：预览 12-repair-resume-plan，确认清理范围后执行 repair-resume。")
    if needs_preconditions:
        first = needs_preconditions[0]
        actions.append(f"先补 {first.get('run_id')} 的恢复前置条件：{', '.join(_string_list(first.get('precondition_codes'))) or '见 backlog triage'}。")
    if any(item.get("review_reapproval_required") for item in ready):
        actions.append("repair-resume 应用后必须重新走 review approval；未批准不得进入 idea/实验。")
    if any(item.get("execution_reapproval_required") for item in [*ready, *needs_preconditions]):
        actions.append("涉及 local/benchmark 的恢复必须重新走 execution approval；未批准不得执行实验。")
    if blocked:
        actions.append("对 can_resume=false 的 run 先重建 12-repair-queue 和 12-repair-resume-plan。")
    return actions


def _has_active_queue(queue: dict[str, Any]) -> bool:
    if str(queue.get("status") or "") in REPAIR_BACKLOG_STATUSES:
        return True
    items = queue.get("items") if isinstance(queue.get("items"), list) else []
    return any(
        isinstance(item, dict)
        and str(item.get("status") or "open") == "open"
        and str(item.get("severity") or "") in SEVERITY_RANK
        for item in items
    )


def _has_doctor_resume_plan(plan: dict[str, Any]) -> bool:
    if not plan or plan.get("can_resume") is not True:
        return False
    sources = set(_string_list(plan.get("repair_plan_sources")))
    return "gold-run-doctor" in sources or bool(str(plan.get("doctor_report_path") or "").strip())


def _repair_resume_command(run_dir: Path, plan: dict[str, Any]) -> str:
    commands = plan.get("commands") if isinstance(plan.get("commands"), list) else []
    for command in commands:
        text = str(command or "").strip()
        if text and " --apply" in text:
            return text
    for command in commands:
        text = str(command or "").strip()
        if text:
            return _ensure_repair_resume_apply_command(text)
    doctor_report_path = str(plan.get("doctor_report_path") or "").strip()
    suffix = f" --gold-run-doctor-report {doctor_report_path}" if doctor_report_path else ""
    return f"PYTHONPATH=src python3 -m research_agent repair-resume {run_dir} --apply{suffix}"


def _ensure_repair_resume_apply_command(command: str) -> str:
    if " repair-resume " in command and " --apply" not in command and " --dry-run" not in command:
        return f"{command} --apply"
    return command


def _plan_label(item: dict[str, Any]) -> str:
    label = str(item.get("plan_status") or "-")
    sources = _string_list(item.get("repair_plan_sources"))
    if sources:
        label = f"{label} ({', '.join(sources)})"
    if item.get("doctor_report"):
        label = f"{label} doctor"
    return label


def _count_items(items: list[Any], severity: str) -> int:
    return sum(1 for item in items if isinstance(item, dict) and str(item.get("severity") or "") == severity and str(item.get("status") or "open") == "open")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


