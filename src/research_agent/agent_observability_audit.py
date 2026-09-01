from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .llm_ledger_recovery import summarize_llm_failure_recovery


AGENT_OBSERVABILITY_AUDIT_JSON = "13-agent-observability-audit.json"
AGENT_OBSERVABILITY_AUDIT_MD = "13-agent-observability-audit.md"


def write_agent_observability_audit_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_agent_observability_audit_report(topic, run_dir)
    write_json(run_dir / AGENT_OBSERVABILITY_AUDIT_JSON, report)
    write_text(run_dir / AGENT_OBSERVABILITY_AUDIT_MD, render_agent_observability_audit_markdown(report))
    return report


def build_agent_observability_audit_report(topic: str, run_dir: Path) -> dict[str, Any]:
    state = _read_json(run_dir / "state.json")
    manifest = _read_json(run_dir / "run-manifest.json")
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    run_config = _read_json(run_dir / "run-config.json")
    approval = _read_json(run_dir / "approval.json")
    execution_approval = _read_json(run_dir / "03-execution-approval.json")
    runbook = _read_json(run_dir / "04-experiment-runbook.json")
    diagnostic = _read_json(run_dir / "run-diagnostics.json")
    recovery = _read_json(run_dir / "run-recovery-plan.json")
    repair_queue = _read_json(run_dir / "12-repair-queue.json")

    checks: list[dict[str, Any]] = []
    blocking: list[str] = []
    manual: list[str] = []
    warnings: list[str] = []
    checks.append(_state_manifest_check(state, manifest, blocking, manual))
    checks.append(_manifest_event_check(state, manifest, blocking, manual))
    checks.append(_artifact_inventory_check(manifest, blocking, manual))
    checks.append(_llm_budget_check(ledger, run_config, blocking, manual, warnings))
    checks.append(_human_gate_check(approval, execution_approval, runbook, blocking, manual))
    checks.append(_experiment_trace_check(runbook, blocking, manual, warnings))
    checks.append(_diagnostic_recovery_check(state, diagnostic, recovery, blocking, manual))
    checks.append(_repair_trace_check(repair_queue, manual))

    blocking = _unique(blocking)
    manual = _unique(manual)
    warnings = _unique(warnings)
    status = "block" if blocking else "review_required" if manual or warnings else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "generated_at": _utc_now(),
        "run_dir": str(run_dir),
        "summary": _summary(state, manifest, ledger, runbook, repair_queue),
        "budget": _budget_summary(ledger, run_config),
        "checks": checks,
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "warnings": warnings,
        "recommended_actions": _recommended_actions(status, blocking, manual, warnings),
    }


def render_agent_observability_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    budget = report.get("budget") if isinstance(report.get("budget"), dict) else {}
    lines = [
        f"# Agent Observability Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- Run 目录：{report.get('run_dir') or '-'}",
        f"- 阶段：{summary.get('state_stage') or '-'} / manifest={summary.get('manifest_status') or '-'}",
        f"- Manifest events/artifacts：{summary.get('manifest_events', 0)}/{summary.get('manifest_artifacts', 0)}",
        f"- LLM calls：{summary.get('llm_total_calls', 0)} total / {summary.get('llm_successful_calls', 0)} success / {summary.get('llm_failed_calls', 0)} failed / {summary.get('llm_budget_exceeded_calls', 0)} budget",
        f"- Experiment runs：{summary.get('experiment_runs', 0)}",
        f"- Repair queue：{summary.get('repair_queue_status') or '-'}",
        "",
        "## Budget",
        f"- Call budget：{budget.get('used_calls', 0)}/{budget.get('max_calls', 0)} ({float(budget.get('call_utilization') or 0.0):.2f})",
        f"- Prompt budget：{budget.get('used_prompt_chars', 0)}/{budget.get('max_prompt_chars', 0)} ({float(budget.get('prompt_utilization') or 0.0):.2f})",
        f"- Total duration：{float(budget.get('total_llm_duration_seconds') or 0.0):.3f}s",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("warnings", "警告"), ("recommended_actions", "推荐动作")]:
        values = _as_list(report.get(key))
        if values:
            lines.extend([f"## {title}"])
            prefix = "- [ ] " if key in {"manual_tasks", "recommended_actions"} else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(["## 检查项", "| 检查 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
    for item in _as_list(report.get("checks")):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("name") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("evidence") or "")),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- `block` 表示 run 的核心轨迹、状态、人工 gate、诊断或实验 trace 断链，不能作为可审计科研 agent 运行记录。",
            "- `review_required` 表示轨迹存在但存在预算压力、artifact trace 或恢复信息需要人工确认。",
            "- `pass` 表示 manifest、LLM ledger、human gate、experiment runbook、repair queue 和恢复诊断形成可追踪闭环。",
        ]
    )
    return "\n".join(lines)


def _state_manifest_check(state: dict[str, Any], manifest: dict[str, Any], blocking: list[str], manual: list[str]) -> dict[str, str]:
    state_stage = str(state.get("stage") or "")
    manifest_status = str(manifest.get("status") or "")
    if not state:
        detail = "state.json 缺失或不可读。"
        blocking.append(detail)
        return _check("state_manifest_alignment", "block", detail, "恢复或重新生成 state.json。")
    if not manifest:
        detail = "run-manifest.json 缺失或不可读。"
        blocking.append(detail)
        return _check("state_manifest_alignment", "block", detail, "重新生成 run manifest。")
    if state_stage == "completed" and manifest_status != "completed":
        detail = f"state completed 但 manifest status={manifest_status or '-'}。"
        manual.append(detail)
        return _check("state_manifest_alignment", "review_required", detail, "重新刷新 run-manifest 或 run-integrity。")
    return _check("state_manifest_alignment", "pass", f"state={state_stage or '-'} manifest={manifest_status or '-'}", "无需处理。")


def _manifest_event_check(state: dict[str, Any], manifest: dict[str, Any], blocking: list[str], manual: list[str]) -> dict[str, str]:
    events = _dicts(manifest.get("events"))
    stage = str(state.get("stage") or "")
    if not events:
        detail = "run-manifest 没有 events。"
        blocking.append(detail)
        return _check("manifest_event_trace", "block", detail, "重新运行或恢复 pipeline，让每个阶段写入 manifest。")
    missing_timestamps = [str(item.get("stage") or "") for item in events if not str(item.get("started_at") or "") or not str(item.get("completed_at") or "")]
    if missing_timestamps:
        detail = "部分 manifest event 缺少 started_at/completed_at：" + ", ".join(missing_timestamps[:6])
        manual.append(detail)
        return _check("manifest_event_trace", "review_required", detail, "重新生成 manifest 或人工核对旧 run。")
    if stage == "completed" and len(events) < 15:
        detail = f"completed run 的 manifest events 偏少：{len(events)}。"
        manual.append(detail)
        return _check("manifest_event_trace", "review_required", detail, "确认是否为旧版 run 或不完整 resume。")
    return _check("manifest_event_trace", "pass", f"events={len(events)}; latest={events[-1].get('stage') or '-'}", "无需处理。")


def _artifact_inventory_check(manifest: dict[str, Any], blocking: list[str], manual: list[str]) -> dict[str, str]:
    artifacts = _dicts(manifest.get("artifacts"))
    if not artifacts:
        detail = "run-manifest 没有 artifact inventory。"
        blocking.append(detail)
        return _check("artifact_inventory_trace", "block", detail, "重新写入 manifest artifact inventory。")
    missing = [str(item.get("path") or "") for item in artifacts if not str(item.get("path") or "") or not str(item.get("sha256") or "") or int(item.get("bytes") or 0) <= 0]
    if missing:
        detail = "部分 artifact 缺少 path/sha256/bytes：" + ", ".join(missing[:8])
        manual.append(detail)
        return _check("artifact_inventory_trace", "review_required", detail, "重新生成 run-manifest。")
    key_paths = {"state.json", "run-manifest.json", "run-llm-ledger.json"}
    present = {str(item.get("path") or "") for item in artifacts}
    key_missing = sorted(key_paths - present)
    if key_missing:
        detail = "manifest artifact inventory 缺少关键文件：" + ", ".join(key_missing)
        manual.append(detail)
        return _check("artifact_inventory_trace", "review_required", detail, "重新刷新 manifest artifact inventory。")
    return _check("artifact_inventory_trace", "pass", f"artifacts={len(artifacts)}; key_files=present", "无需处理。")


def _llm_budget_check(
    ledger: dict[str, Any],
    run_config: dict[str, Any],
    blocking: list[str],
    manual: list[str],
    warnings: list[str],
) -> dict[str, str]:
    if not ledger:
        detail = "run-llm-ledger.json 缺失或不可读。"
        blocking.append(detail)
        return _check("llm_budget_telemetry", "block", detail, "重新运行并保留 LLM ledger。")
    failed = _safe_int(ledger.get("failed_calls"))
    budget_exceeded = _safe_int(ledger.get("budget_exceeded_calls"))
    if failed or budget_exceeded:
        recovery = summarize_llm_failure_recovery(ledger)
        unrecovered_failed = _safe_int(recovery.get("unrecovered_failed_calls"))
        unrecovered_budget = _safe_int(recovery.get("unrecovered_budget_exceeded_calls"))
        if unrecovered_failed or unrecovered_budget:
            detail = f"LLM ledger 存在 failed={failed} budget_exceeded={budget_exceeded}; unrecovered_failed={unrecovered_failed}; unrecovered_budget_exceeded={unrecovered_budget}。"
            blocking.append(detail)
            return _check("llm_budget_telemetry", "block", detail, "修复模型配置或预算后从 checkpoint 重跑。")
        detail = f"LLM ledger 存在 failed={failed} budget_exceeded={budget_exceeded}，但均已由后续同阶段 success 恢复。"
        warnings.append(detail)
        manual.append(detail)
        return _check("llm_budget_telemetry", "review_required", detail, "人工核对恢复链路，确认最终产物来自成功调用。")
    budget = _budget_summary(ledger, run_config)
    high_pressure = []
    if budget["max_calls"] and budget["call_utilization"] >= 0.9:
        high_pressure.append(f"calls={budget['call_utilization']:.2f}")
    if budget["max_prompt_chars"] and budget["prompt_utilization"] >= 0.9:
        high_pressure.append(f"prompt={budget['prompt_utilization']:.2f}")
    if high_pressure:
        detail = "LLM 预算压力接近上限：" + ", ".join(high_pressure)
        warnings.append(detail)
        manual.append(detail)
        return _check("llm_budget_telemetry", "review_required", detail, "提高预算或减少下一轮 prompt 规模。")
    if not run_config:
        detail = "run-config.json 缺失，无法核对 LLM budget policy。"
        warnings.append(detail)
        return _check("llm_budget_telemetry", "review_required", detail, "补齐 run-config 或在归档中说明旧 run。")
    return _check("llm_budget_telemetry", "pass", f"calls={budget['used_calls']} duration={budget['total_llm_duration_seconds']:.3f}s", "无需处理。")


def _human_gate_check(
    approval: dict[str, Any],
    execution_approval: dict[str, Any],
    runbook: dict[str, Any],
    blocking: list[str],
    manual: list[str],
) -> dict[str, str]:
    if not approval:
        detail = "approval.json 缺失，无法证明 idea/实验前有人工 gate。"
        blocking.append(detail)
        return _check("human_gate_trace", "block", detail, "重新生成 review approval gate。")
    if approval.get("approved") is not True:
        detail = "review approval 尚未批准。"
        blocking.append(detail)
        return _check("human_gate_trace", "block", detail, "人工审核文献 gate 后再继续。")
    blocks = {str(item) for item in _as_list(approval.get("blocks"))}
    if not {"idea_generation", "experiment_planning", "experiment_execution"}.issubset(blocks):
        detail = "approval.json 未记录完整阻断范围。"
        manual.append(detail)
        return _check("human_gate_trace", "review_required", detail, "刷新 approval gate 或人工说明旧 run。")
    mode = str((_dict(runbook.get("execution"))).get("mode") or "")
    if mode in {"local", "benchmark"} and execution_approval.get("approved") is not True:
        detail = f"{mode} 执行缺少 approved execution gate。"
        blocking.append(detail)
        return _check("human_gate_trace", "block", detail, "补齐 03-execution-approval。")
    return _check("human_gate_trace", "pass", f"review_approved=true; execution_mode={mode or '-'}", "无需处理。")


def _experiment_trace_check(
    runbook: dict[str, Any],
    blocking: list[str],
    manual: list[str],
    warnings: list[str],
) -> dict[str, str]:
    if not runbook:
        return _check("experiment_runtime_trace", "not_applicable", "未生成 04-experiment-runbook，跳过实验运行 trace。", "无需处理。")
    runs = _dicts(runbook.get("runs"))
    if not runs:
        detail = "04-experiment-runbook 没有 runs。"
        blocking.append(detail)
        return _check("experiment_runtime_trace", "block", detail, "重新生成实验 runbook。")
    missing_seed = [str(item.get("name") or "") for item in runs if not str(item.get("seed") or "")]
    missing_duration = [str(item.get("name") or "") for item in runs if "duration_seconds" not in item]
    missing_artifacts = [str(item.get("name") or "") for item in runs if not _dicts(item.get("produced_artifacts"))]
    if missing_seed or missing_duration:
        detail = f"部分实验 run 缺少 seed/duration：seed={len(missing_seed)} duration={len(missing_duration)}。"
        manual.append(detail)
        return _check("experiment_runtime_trace", "review_required", detail, "重新执行或刷新 runbook runtime 字段。")
    if missing_artifacts:
        detail = f"部分实验 run 没有 produced_artifacts：{len(missing_artifacts)}。"
        warnings.append(detail)
        manual.append(detail)
        return _check("experiment_runtime_trace", "review_required", detail, "补齐 artifact hash trace。")
    failed = [str(item.get("name") or "") for item in runs if str(item.get("status") or "") in {"failed", "blocked", "timeout"}]
    if failed:
        detail = "runbook 存在失败/阻断/超时运行：" + ", ".join(failed[:6])
        manual.append(detail)
        return _check("experiment_runtime_trace", "review_required", detail, "结合 failure analysis 决定重跑或降级结论。")
    return _check("experiment_runtime_trace", "pass", f"runs={len(runs)}; seeds/durations/artifacts present", "无需处理。")


def _diagnostic_recovery_check(
    state: dict[str, Any],
    diagnostic: dict[str, Any],
    recovery: dict[str, Any],
    blocking: list[str],
    manual: list[str],
) -> dict[str, str]:
    stage = str(state.get("stage") or "")
    if stage == "failed" and not diagnostic:
        detail = "state=failed 但缺少 run-diagnostics。"
        blocking.append(detail)
        return _check("diagnostic_recovery_trace", "block", detail, "写出 run-diagnostics 并生成 run-recovery-plan。")
    if diagnostic and not recovery:
        detail = "存在 run-diagnostics 但缺少 run-recovery-plan。"
        manual.append(detail)
        return _check("diagnostic_recovery_trace", "review_required", detail, "生成 run-recovery-plan 以指导恢复。")
    if recovery and str(recovery.get("category") or "") in {"failed", "cancelled", "awaiting_review_approval", "awaiting_execution_approval"}:
        detail = f"run-recovery-plan category={recovery.get('category')} 仍需人工处理。"
        manual.append(detail)
        return _check("diagnostic_recovery_trace", "review_required", detail, "按 run-recovery-plan 推荐动作处理。")
    return _check("diagnostic_recovery_trace", "pass", f"diagnostic={'yes' if diagnostic else 'no'} recovery={recovery.get('category') or '-'}", "无需处理。")


def _repair_trace_check(repair_queue: dict[str, Any], manual: list[str]) -> dict[str, str]:
    if not repair_queue:
        return _check("repair_queue_trace", "not_applicable", "未生成 12-repair-queue，跳过修复队列 trace。", "无需处理。")
    status = str(repair_queue.get("status") or "")
    summary = repair_queue.get("summary") if isinstance(repair_queue.get("summary"), dict) else {}
    total = _safe_int(summary.get("total"))
    if status in {"blocked_repair_required", "needs_repair"}:
        detail = f"repair_queue={status}; items={total}"
        manual.append(detail)
        return _check("repair_queue_trace", "review_required", detail, "优先处理 12-repair-queue 中的 block/high 修复项。")
    return _check("repair_queue_trace", "pass", f"repair_queue={status or '-'}; items={total}", "无需处理。")


def _summary(
    state: dict[str, Any],
    manifest: dict[str, Any],
    ledger: dict[str, Any],
    runbook: dict[str, Any],
    repair_queue: dict[str, Any],
) -> dict[str, Any]:
    return {
        "state_stage": str(state.get("stage") or ""),
        "manifest_status": str(manifest.get("status") or ""),
        "manifest_events": len(_dicts(manifest.get("events"))),
        "manifest_artifacts": len(_dicts(manifest.get("artifacts"))),
        "llm_total_calls": _safe_int(ledger.get("total_calls")),
        "llm_successful_calls": _safe_int(ledger.get("successful_calls")),
        "llm_failed_calls": _safe_int(ledger.get("failed_calls")),
        "llm_budget_exceeded_calls": _safe_int(ledger.get("budget_exceeded_calls")),
        "experiment_runs": len(_dicts(runbook.get("runs"))),
        "repair_queue_status": str(repair_queue.get("status") or ""),
    }


def _budget_summary(ledger: dict[str, Any], run_config: dict[str, Any]) -> dict[str, Any]:
    llm = run_config.get("llm") if isinstance(run_config.get("llm"), dict) else {}
    used_calls = _safe_int(ledger.get("total_calls"))
    used_prompt = _safe_int(ledger.get("total_prompt_chars"))
    max_calls = _safe_int(llm.get("max_calls"))
    max_prompt = _safe_int(llm.get("max_prompt_chars"))
    entries = _dicts(ledger.get("entries"))
    total_duration = sum(_safe_float(item.get("duration_seconds")) for item in entries)
    return {
        "used_calls": used_calls,
        "max_calls": max_calls,
        "call_utilization": round(used_calls / max_calls, 3) if max_calls > 0 else 0.0,
        "used_prompt_chars": used_prompt,
        "max_prompt_chars": max_prompt,
        "prompt_utilization": round(used_prompt / max_prompt, 3) if max_prompt > 0 else 0.0,
        "total_llm_duration_seconds": round(total_duration, 3),
    }


def _recommended_actions(status: str, blocking: list[str], manual: list[str], warnings: list[str]) -> list[str]:
    if status == "block":
        return ["先修复 agent observability 阻断项，再把该 run 作为可审计科研记录使用。", *blocking[:4]]
    if status == "review_required":
        return ["人工核对 run manifest、LLM budget、实验 runbook、恢复计划和 repair queue 后再进入下一轮。", *(manual or warnings)[:4]]
    return ["可继续使用该 run 的轨迹；下一轮重点看 12-next-iteration-plan 和 13-research-scorecard。"]


def _check(name: str, status: str, evidence: str, action: str) -> dict[str, str]:
    return {"name": name, "status": status, "evidence": evidence, "action": action}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in result:
            result.append(text)
    return result


