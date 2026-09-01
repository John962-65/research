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
from .llm_observability_summary import (
    LLM_OBSERVABILITY_SUMMARY_JSON,
    LLM_OBSERVABILITY_SUMMARY_MD,
    write_llm_observability_summary_artifacts,
)
from .llm_runtime_contract import LLM_RUNTIME_CONTRACT_JSON, LLM_RUNTIME_CONTRACT_MD, write_llm_runtime_contract_artifacts
from .llm_trace_audit import LLM_TRACE_AUDIT_JSON, LLM_TRACE_AUDIT_MD, write_llm_trace_audit_artifacts
from .run_economics_audit import RUN_ECONOMICS_AUDIT_JSON, RUN_ECONOMICS_AUDIT_MD, write_run_economics_audit_artifacts
from .artifacts import cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json


def backfill_llm_observability(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "scanned_runs": 0,
        "trace_written": 0,
        "runtime_written": 0,
        "economics_written": 0,
        "observability_written": 0,
        "summary_written": 0,
        "would_write_trace": 0,
        "would_write_runtime": 0,
        "would_write_economics": 0,
        "would_write_observability": 0,
        "would_write_summary": 0,
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
        targets = _targets(run_dir)
        needs_trace = force or not targets["trace"]
        needs_runtime = force or not targets["runtime"]
        needs_economics = force or not targets["economics"]
        needs_observability = force or not targets["observability"]
        needs_summary = force or not targets["summary"] or needs_trace or needs_runtime or needs_economics or needs_observability
        if not needs_trace and not needs_runtime and not needs_economics and not needs_observability and not needs_summary:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", trace=False, runtime=False, economics=False, observability=False, summary=False))
            continue
        if dry_run:
            if needs_trace:
                report["would_write_trace"] += 1
            if needs_runtime:
                report["would_write_runtime"] += 1
            if needs_economics:
                report["would_write_economics"] += 1
            if needs_observability:
                report["would_write_observability"] += 1
            if needs_summary:
                report["would_write_summary"] += 1
            report["items"].append(_item(run_dir, "would_write", trace=needs_trace, runtime=needs_runtime, economics=needs_economics, observability=needs_observability, summary=needs_summary))
            continue

        try:
            topic = _topic_from_state(run_dir)
            trace = write_llm_trace_audit_artifacts(topic, run_dir) if needs_trace else _read_json(run_dir / LLM_TRACE_AUDIT_JSON)
            economics = write_run_economics_audit_artifacts(topic, run_dir) if needs_economics else _read_json(run_dir / RUN_ECONOMICS_AUDIT_JSON)
            runtime = write_llm_runtime_contract_artifacts(topic, run_dir) if needs_runtime else _read_json(run_dir / LLM_RUNTIME_CONTRACT_JSON)
            observability = write_agent_observability_audit_artifacts(topic, run_dir) if needs_observability else _read_json(run_dir / AGENT_OBSERVABILITY_AUDIT_JSON)
            summary = write_llm_observability_summary_artifacts(topic, run_dir) if needs_summary else _read_json(run_dir / LLM_OBSERVABILITY_SUMMARY_JSON)
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", trace=needs_trace, runtime=needs_runtime, economics=needs_economics, observability=needs_observability, summary=needs_summary, error=str(exc)))
            continue

        if needs_trace:
            report["trace_written"] += 1
        if needs_runtime:
            report["runtime_written"] += 1
        if needs_economics:
            report["economics_written"] += 1
        if needs_observability:
            report["observability_written"] += 1
        if needs_summary:
            report["summary_written"] += 1
        trace_summary = trace.get("ledger_summary") if isinstance(trace.get("ledger_summary"), dict) else {}
        economics_summary = economics.get("summary") if isinstance(economics.get("summary"), dict) else {}
        observability_summary = observability.get("summary") if isinstance(observability.get("summary"), dict) else {}
        public_summary = summary.get("llm_calls") if isinstance(summary.get("llm_calls"), dict) else {}
        report["items"].append(
            _item(
                run_dir,
                "write",
                trace=needs_trace,
                runtime=needs_runtime,
                economics=needs_economics,
                observability=needs_observability,
                summary=needs_summary,
                trace_status=str(trace.get("status") or ""),
                runtime_status=str(runtime.get("status") or ""),
                economics_status=str(economics.get("status") or ""),
                observability_status=str(observability.get("status") or ""),
                summary_status=str(summary.get("status") or ""),
                total_calls=_safe_int(public_summary.get("total") or trace_summary.get("total_calls") or economics_summary.get("total_calls") or observability_summary.get("llm_total_calls")),
                successful_calls=_safe_int(public_summary.get("successful") or trace_summary.get("successful_calls") or economics_summary.get("successful_calls")),
                failed_calls=_safe_int(trace_summary.get("failed_calls") or economics_summary.get("failed_calls") or observability_summary.get("llm_failed_calls")),
                trace_blocking_issues=_count_list(trace.get("blocking_issues")),
                runtime_blocking_issues=_count_list(runtime.get("blocking_issues")),
                economics_blocking_issues=_count_list(economics.get("blocking_issues")),
                observability_blocking_issues=_count_list(observability.get("blocking_issues")),
                summary_blocking_issues=_count_list(summary.get("blocking_issues")),
            )
        )
    return report


def render_llm_observability_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    error_count = _safe_int(report.get("error_count")) if "error_count" in report else len(errors)
    lines = [
        "# LLM Observability Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- Trace 审计写入：{report.get('trace_written', 0)}",
        f"- Runtime Contract 写入：{report.get('runtime_written', 0)}",
        f"- Economics 审计写入：{report.get('economics_written', 0)}",
        f"- Observability 审计写入：{report.get('observability_written', 0)}",
        f"- Summary 写入：{report.get('summary_written', 0)}",
        f"- 将写入 Trace 审计：{report.get('would_write_trace', 0)}",
        f"- 将写入 Runtime Contract：{report.get('would_write_runtime', 0)}",
        f"- 将写入 Economics 审计：{report.get('would_write_economics', 0)}",
        f"- 将写入 Observability 审计：{report.get('would_write_observability', 0)}",
        f"- 将写入 Summary：{report.get('would_write_summary', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{error_count}",
        "",
        "说明：该回填只生成审计产物，不创建或修改 run-llm-ledger.json；旧 run 缺失模型账本时仍会保持阻断。",
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
                "| Run | Action | Trace | Runtime | Economics | Observability | Summary | Trace Status | Runtime Status | Economics Status | Observability Status | Summary Status | Calls | Success | Failed | Blocking |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            blocking = _safe_int(item.get("trace_blocking_issues")) + _safe_int(item.get("runtime_blocking_issues")) + _safe_int(item.get("economics_blocking_issues")) + _safe_int(item.get("observability_blocking_issues")) + _safe_int(item.get("summary_blocking_issues"))
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("run_id") or "")),
                        _cell(str(item.get("action") or "")),
                        "yes" if item.get("trace") else "no",
                        "yes" if item.get("runtime") else "no",
                        "yes" if item.get("economics") else "no",
                        "yes" if item.get("observability") else "no",
                        "yes" if item.get("summary") else "no",
                        _cell(str(item.get("trace_status") or "-")),
                        _cell(str(item.get("runtime_status") or "-")),
                        _cell(str(item.get("economics_status") or "-")),
                        _cell(str(item.get("observability_status") or "-")),
                        _cell(str(item.get("summary_status") or "-")),
                        str(item.get("total_calls") or 0),
                        str(item.get("successful_calls") or 0),
                        str(item.get("failed_calls") or 0),
                        str(blocking),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _targets(run_dir: Path) -> dict[str, bool]:
    return {
        "trace": (run_dir / LLM_TRACE_AUDIT_JSON).exists() and (run_dir / LLM_TRACE_AUDIT_MD).exists(),
        "runtime": (run_dir / LLM_RUNTIME_CONTRACT_JSON).exists() and (run_dir / LLM_RUNTIME_CONTRACT_MD).exists(),
        "economics": (run_dir / RUN_ECONOMICS_AUDIT_JSON).exists() and (run_dir / RUN_ECONOMICS_AUDIT_MD).exists(),
        "observability": (run_dir / AGENT_OBSERVABILITY_AUDIT_JSON).exists() and (run_dir / AGENT_OBSERVABILITY_AUDIT_MD).exists(),
        "summary": (run_dir / LLM_OBSERVABILITY_SUMMARY_JSON).exists() and (run_dir / LLM_OBSERVABILITY_SUMMARY_MD).exists(),
    }


def _item(run_dir: Path, action: str, **extra: Any) -> dict[str, Any]:
    return {"run_id": run_dir.name, "action": action, **extra}


def _topic_from_state(run_dir: Path) -> str:
    data = _read_json(run_dir / "state.json")
    return str(data.get("topic") or run_dir.name)


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


