from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


LLM_OBSERVABILITY_SUMMARY_JSON = "13-llm-observability-summary.json"
LLM_OBSERVABILITY_SUMMARY_MD = "13-llm-observability-summary.md"


def write_llm_observability_summary_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_llm_observability_summary_report(topic, run_dir)
    write_json(run_dir / LLM_OBSERVABILITY_SUMMARY_JSON, report)
    write_text(run_dir / LLM_OBSERVABILITY_SUMMARY_MD, render_llm_observability_summary_markdown(report))
    return report


def build_llm_observability_summary_report(topic: str, run_dir: Path) -> dict[str, Any]:
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    runtime = _read_json(run_dir / "13-llm-runtime-contract.json")
    trace = _read_json(run_dir / "13-llm-trace-audit.json")
    economics = _read_json(run_dir / "13-run-economics-audit.json")
    observability = _read_json(run_dir / "13-agent-observability-audit.json")
    runtime_summary = _dict(runtime.get("summary"))
    trace_summary = _dict(trace.get("ledger_summary"))
    coverage = _dict(trace.get("coverage"))
    stage_gaps = _dict(trace.get("stage_gap_summary"))
    economics_summary = _dict(economics.get("summary"))
    budget = _dict(economics.get("budget"))
    observability_summary = _dict(observability.get("summary"))
    statuses = {
        "runtime_contract": str(runtime.get("status") or "missing"),
        "trace": str(trace.get("status") or "missing"),
        "economics": str(economics.get("status") or "missing"),
        "agent_observability": str(observability.get("status") or "missing"),
    }
    blocking = _unique(
        [
            *[f"runtime_contract: {item}" for item in _list(runtime.get("blocking_issues"))],
            *[f"trace: {item}" for item in _list(trace.get("blocking_issues"))],
            *[f"economics: {item}" for item in _list(economics.get("blocking_issues"))],
            *[f"agent_observability: {item}" for item in _list(observability.get("blocking_issues"))],
        ]
    )
    manual = _unique(
        [
            *[f"runtime_contract: {item}" for item in _list(runtime.get("manual_tasks"))],
            *[f"trace: {item}" for item in _list(trace.get("manual_tasks"))],
            *[f"economics: {item}" for item in _list(economics.get("manual_tasks"))],
            *[f"agent_observability: {item}" for item in _list(observability.get("manual_tasks"))],
        ]
    )
    warnings = _unique(
        [
            *[f"runtime_contract: {item}" for item in _list(runtime.get("warnings"))],
            *[f"trace: {item}" for item in _list(trace.get("warnings"))],
            *[f"economics: {item}" for item in _list(economics.get("warnings"))],
            *[f"agent_observability: {item}" for item in _list(observability.get("warnings"))],
        ]
    )
    missing = [name for name, data in [("run-llm-ledger.json", ledger), ("13-llm-runtime-contract.json", runtime), ("13-llm-trace-audit.json", trace), ("13-run-economics-audit.json", economics), ("13-agent-observability-audit.json", observability)] if not data]
    blocking.extend(f"{item} 缺失或不可读。" for item in missing)
    status = "block" if blocking or any(value == "block" for value in statuses.values()) else "review_required" if manual or warnings or any(value in {"review_required", "warn"} for value in statuses.values()) else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "generated_at": _utc_now(),
        "source_projects": ["SamuelSchmidgall/AgentLaboratory", "SakanaAI/AI-Scientist-v2", "MLAgentBench"],
        "statuses": statuses,
        "llm_calls": {
            "total": _first_int(trace_summary.get("total_calls"), economics_summary.get("total_calls"), observability_summary.get("llm_total_calls"), ledger.get("total_calls")),
            "successful": _first_int(trace_summary.get("successful_calls"), economics_summary.get("successful_calls"), observability_summary.get("llm_successful_calls"), ledger.get("successful_calls")),
            "failed": _first_int(trace_summary.get("failed_calls"), economics_summary.get("failed_calls"), observability_summary.get("llm_failed_calls"), ledger.get("failed_calls")),
            "budget_exceeded": _first_int(trace_summary.get("budget_exceeded_calls"), economics_summary.get("budget_exceeded_calls"), observability_summary.get("llm_budget_exceeded_calls"), ledger.get("budget_exceeded_calls")),
            "entries": _first_int(trace_summary.get("entries"), len(_list(ledger.get("entries")))),
        },
        "runtime_contract": {
            "provider": str(runtime_summary.get("provider") or ""),
            "model_configured": runtime_summary.get("model_configured") is True,
            "api_key_persisted": runtime_summary.get("api_key_persisted") is True,
            "call_budget_configured": runtime_summary.get("call_budget_configured") is True,
            "prompt_budget_configured": runtime_summary.get("prompt_budget_configured") is True,
            "pricing_configured": runtime_summary.get("pricing_configured") is True,
        },
        "stage_coverage": {
            "required_stages": _int(coverage.get("required_stages")),
            "passed_required": _int(coverage.get("passed_required")),
            "coverage_ratio": _float(coverage.get("coverage_ratio")),
            "missing_required_stage_count": _first_int(stage_gaps.get("missing_required_stage_count"), len(_list(stage_gaps.get("missing_required_stages")))),
            "missing_required_stages": _string_list(stage_gaps.get("missing_required_stages")),
            "warned_optional_stage_count": _first_int(stage_gaps.get("warned_optional_stage_count"), len(_list(stage_gaps.get("warned_optional_stages")))),
            "warned_optional_stages": _string_list(stage_gaps.get("warned_optional_stages")),
        },
        "token_and_cost": {
            "input_tokens_estimated": _int(economics_summary.get("input_tokens_estimated")),
            "output_tokens_estimated": _int(economics_summary.get("output_tokens_estimated")),
            "estimated_cost_usd": economics_summary.get("estimated_cost_usd"),
            "total_duration_seconds": _float(economics_summary.get("total_duration_seconds")),
        },
        "budget": {
            "used_calls": _int(budget.get("used_calls")),
            "max_calls": _int(budget.get("max_calls")),
            "call_utilization": _float(budget.get("call_utilization")),
            "used_prompt_chars": _int(budget.get("used_prompt_chars")),
            "max_prompt_chars": _int(budget.get("max_prompt_chars")),
            "prompt_utilization": _float(budget.get("prompt_utilization")),
        },
        "traceability": {
            "manifest_events": _int(observability_summary.get("manifest_events")),
            "manifest_artifacts": _int(observability_summary.get("manifest_artifacts")),
            "experiment_runs": _int(observability_summary.get("experiment_runs")),
            "repair_queue_status": str(observability_summary.get("repair_queue_status") or ""),
        },
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "warnings": _unique(warnings),
        "recommended_actions": _recommended_actions(status, blocking, manual, warnings),
    }


def render_llm_observability_summary_markdown(report: dict[str, Any]) -> str:
    calls = _dict(report.get("llm_calls"))
    coverage = _dict(report.get("stage_coverage"))
    runtime = _dict(report.get("runtime_contract"))
    tokens = _dict(report.get("token_and_cost"))
    budget = _dict(report.get("budget"))
    traceability = _dict(report.get("traceability"))
    cost = tokens.get("estimated_cost_usd")
    cost_text = f"${float(cost):.6f}" if isinstance(cost, (float, int)) else "未配置单价"
    lines = [
        f"# LLM Observability Summary：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 调用：{calls.get('total', 0)} total / {calls.get('successful', 0)} success / {calls.get('failed', 0)} failed / {calls.get('budget_exceeded', 0)} budget",
        f"- Runtime 契约：provider={runtime.get('provider') or '-'} model={'yes' if runtime.get('model_configured') else 'no'} budget={'yes' if runtime.get('call_budget_configured') or runtime.get('prompt_budget_configured') else 'no'} pricing={'yes' if runtime.get('pricing_configured') else 'no'} key_persisted={'yes' if runtime.get('api_key_persisted') else 'no'}",
        f"- 阶段覆盖：{coverage.get('passed_required', 0)}/{coverage.get('required_stages', 0)} ({float(coverage.get('coverage_ratio') or 0.0):.2f})",
        f"- 缺失成功调用阶段：{coverage.get('missing_required_stage_count', 0)}；可选警告阶段：{coverage.get('warned_optional_stage_count', 0)}",
        f"- Token：input={tokens.get('input_tokens_estimated', 0)} / output={tokens.get('output_tokens_estimated', 0)}",
        f"- 成本：{cost_text}",
        f"- 预算：calls={budget.get('used_calls', 0)}/{budget.get('max_calls', 0)} prompt={budget.get('used_prompt_chars', 0)}/{budget.get('max_prompt_chars', 0)}",
        f"- 轨迹：events={traceability.get('manifest_events', 0)} artifacts={traceability.get('manifest_artifacts', 0)} experiments={traceability.get('experiment_runs', 0)} repair_queue={traceability.get('repair_queue_status') or '-'}",
        "",
        "## 来源项目原则",
        "- AgentLaboratory：分阶段 agent 运行需要保留人工 gate、运行轨迹和可恢复状态。",
        "- AI-Scientist-v2：端到端科研 run 需要能估算阶段成本和模型调用消耗。",
        "- MLAgentBench：实验 agent 的 plans/actions/results 必须可审计、可复盘。",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("warnings", "警告"), ("recommended_actions", "推荐动作")]:
        values = _list(report.get(key))
        if values:
            lines.append(f"## {title}")
            prefix = "- [ ] " if key in {"manual_tasks", "recommended_actions"} else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(
        [
            "## 隐私边界",
            "- 该摘要只聚合状态、计数、hash/长度衍生指标、token/成本估算和阶段覆盖。",
            "- 不输出完整 prompt、response、API key、内部修复上下文或私有推荐动作数组。",
        ]
    )
    return "\n".join(lines)


def _recommended_actions(status: str, blocking: list[str], manual: list[str], warnings: list[str]) -> list[str]:
    if status == "block":
        return ["先修复 LLM trace/economics/observability 阻断项；不能把缺模型账本的 run 作为完整科研 agent 运行。", *blocking[:4]]
    if status == "review_required":
        return ["人工核对预算压力、成本单价、manifest/experiment trace 和 repair queue 后再进入下一轮。", *(manual or warnings)[:4]]
    return ["当前 LLM 观测摘要可用于运行复盘；继续保留 ledger、阶段审计、成本审计和 agent observability。"]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _list(value) if str(item).strip()]


def _first_int(*values: Any) -> int:
    for value in values:
        parsed = _int(value)
        if parsed:
            return parsed
    return 0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
