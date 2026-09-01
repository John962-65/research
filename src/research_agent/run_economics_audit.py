from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .llm_ledger_recovery import summarize_llm_failure_recovery


RUN_ECONOMICS_AUDIT_JSON = "13-run-economics-audit.json"
RUN_ECONOMICS_AUDIT_MD = "13-run-economics-audit.md"
CHARS_PER_TOKEN_ESTIMATE = 4

_STAGE_RULES = [
    ("research_planning", ["research planning"]),
    ("online_search_query_planning", ["online search query planning"]),
    ("literature_synthesis", ["literature synthesis"]),
    ("idea_generation", ["research ideas"]),
    ("experiment_planning", ["experiment planning"]),
    ("paper_writing", ["paper writing"]),
    ("paper_review", ["scientific peer review"]),
    ("paper_revision", ["paper revision"]),
]


def write_run_economics_audit_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_run_economics_audit_report(topic, run_dir)
    write_json(run_dir / RUN_ECONOMICS_AUDIT_JSON, report)
    write_text(run_dir / RUN_ECONOMICS_AUDIT_MD, render_run_economics_audit_markdown(report))
    return report


def build_run_economics_audit_report(topic: str, run_dir: Path) -> dict[str, Any]:
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    run_config = _read_json(run_dir / "run-config.json")
    checks: list[dict[str, str]] = []
    blocking: list[str] = []
    manual: list[str] = []
    warnings: list[str] = []

    checks.append(_ledger_check(ledger, blocking, manual, warnings))
    budget = _budget_summary(ledger, run_config)
    checks.append(_budget_check(budget, blocking, manual, warnings))
    pricing = _pricing(run_config)
    checks.append(_pricing_check(pricing, manual, warnings))

    entries = _dicts(ledger.get("entries")) if ledger else []
    stages = _stage_summaries(entries, pricing)
    summary = _summary(ledger, budget, pricing, stages)
    status = "block" if blocking else "review_required" if manual or warnings else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "generated_at": _utc_now(),
        "run_dir": str(run_dir),
        "token_estimate": {"method": "ceil(chars / 4)", "chars_per_token": CHARS_PER_TOKEN_ESTIMATE},
        "pricing": pricing,
        "summary": summary,
        "budget": budget,
        "stages": stages,
        "checks": checks,
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "warnings": _unique(warnings),
        "recommended_actions": _recommended_actions(status, blocking, manual, warnings, pricing),
    }


def render_run_economics_audit_markdown(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    budget = _dict(report.get("budget"))
    pricing = _dict(report.get("pricing"))
    cost = summary.get("estimated_cost_usd")
    cost_text = f"${float(cost):.6f}" if isinstance(cost, (float, int)) else "未配置单价"
    lines = [
        f"# Run Economics Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Run 目录：{report.get('run_dir') or '-'}",
        f"- LLM calls：{summary.get('total_calls', 0)} total / {summary.get('successful_calls', 0)} success / {summary.get('failed_calls', 0)} failed / {summary.get('budget_exceeded_calls', 0)} budget",
        f"- 估算 token：input={summary.get('input_tokens_estimated', 0)} / output={summary.get('output_tokens_estimated', 0)}",
        f"- 总耗时：{float(summary.get('total_duration_seconds') or 0.0):.3f}s",
        f"- 估算成本：{cost_text}",
        f"- 计价配置：input=${float(pricing.get('input_cost_per_million_tokens') or 0.0):.4f}/M, output=${float(pricing.get('output_cost_per_million_tokens') or 0.0):.4f}/M",
        f"- 调用预算：{budget.get('used_calls', 0)}/{budget.get('max_calls', 0)} ({float(budget.get('call_utilization') or 0.0):.2f})",
        f"- Prompt 预算：{budget.get('used_prompt_chars', 0)}/{budget.get('max_prompt_chars', 0)} ({float(budget.get('prompt_utilization') or 0.0):.2f})",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("warnings", "警告"), ("recommended_actions", "推荐动作")]:
        values = _as_list(report.get(key))
        if values:
            lines.append(f"## {title}")
            prefix = "- [ ] " if key in {"manual_tasks", "recommended_actions"} else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(["## 阶段成本/耗时", "| 阶段 | 调用 | 成功/失败/预算 | Input tokens | Output tokens | 耗时 | 估算成本 |", "| --- | ---: | --- | ---: | ---: | ---: | ---: |"])
    for stage in _dicts(report.get("stages")):
        stage_cost = stage.get("estimated_cost_usd")
        stage_cost_text = f"${float(stage_cost):.6f}" if isinstance(stage_cost, (float, int)) else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(stage.get("stage") or "")),
                    str(stage.get("calls") or 0),
                    f"{stage.get('successful_calls', 0)}/{stage.get('failed_calls', 0)}/{stage.get('budget_exceeded_calls', 0)}",
                    str(stage.get("input_tokens_estimated") or 0),
                    str(stage.get("output_tokens_estimated") or 0),
                    f"{float(stage.get('duration_seconds') or 0.0):.3f}s",
                    stage_cost_text,
                ]
            )
            + " |"
        )
    lines.extend(["", "## 检查项", "| 检查 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
    for item in _dicts(report.get("checks")):
        lines.append("| " + " | ".join([_cell(str(item.get("name") or "")), _cell(str(item.get("status") or "")), _cell(str(item.get("evidence") or "")), _cell(str(item.get("action") or ""))]) + " |")
    lines.extend(
        [
            "",
            "## 说明",
            "- Token 使用 `ceil(chars / 4)` 估算，只用于 run 级预算与趋势判断，不替代供应商账单。",
            "- 若未配置 `llm.input_cost_per_million_tokens` 和 `llm.output_cost_per_million_tokens`，报告只给 token/耗时，不给美元成本。",
        ]
    )
    return "\n".join(lines)


def _ledger_check(ledger: dict[str, Any], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    if not ledger:
        detail = "run-llm-ledger.json 缺失或不可读，无法审计 LLM runtime/cost。"
        blocking.append(detail)
        return _check("llm_ledger_presence", "block", detail, "重新运行并保留 LLM ledger。")
    failed = _safe_int(ledger.get("failed_calls"))
    budget_exceeded = _safe_int(ledger.get("budget_exceeded_calls"))
    if failed or budget_exceeded:
        recovery = summarize_llm_failure_recovery(ledger)
        unrecovered_failed = _safe_int(recovery.get("unrecovered_failed_calls"))
        unrecovered_budget = _safe_int(recovery.get("unrecovered_budget_exceeded_calls"))
        if unrecovered_failed or unrecovered_budget:
            detail = f"LLM ledger 存在 failed={failed} budget_exceeded={budget_exceeded}; unrecovered_failed={unrecovered_failed}; unrecovered_budget_exceeded={unrecovered_budget}。"
            blocking.append(detail)
            return _check("llm_ledger_presence", "block", detail, "修复失败或预算拦截调用后从 checkpoint 重跑。")
        detail = f"LLM ledger 存在 failed={failed} budget_exceeded={budget_exceeded}，但均已由后续同阶段 success 恢复。"
        manual.append(detail)
        warnings.append(detail)
        return _check("llm_ledger_presence", "review_required", detail, "人工核对恢复链路，确认最终产物来自成功调用。")
    entries = _dicts(ledger.get("entries"))
    total = _safe_int(ledger.get("total_calls"))
    if total and not entries:
        detail = "LLM ledger 有 total_calls 但缺少 entries，无法做阶段级成本归因。"
        manual.append(detail)
        return _check("llm_ledger_presence", "review_required", detail, "重新生成 run-llm-ledger 或人工说明旧 run。")
    return _check("llm_ledger_presence", "pass", f"total_calls={total}; entries={len(entries)}", "无需处理。")


def _budget_check(budget: dict[str, Any], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    high: list[str] = []
    if budget["max_calls"] and budget["call_utilization"] >= 0.9:
        high.append(f"calls={budget['call_utilization']:.2f}")
    if budget["max_prompt_chars"] and budget["prompt_utilization"] >= 0.9:
        high.append(f"prompt={budget['prompt_utilization']:.2f}")
    if high:
        detail = "LLM 使用接近配置预算上限：" + ", ".join(high)
        manual.append(detail)
        warnings.append(detail)
        return _check("llm_budget_pressure", "review_required", detail, "提高预算、减少 prompt 规模或拆分下一轮任务。")
    return _check("llm_budget_pressure", "pass", f"calls={budget['used_calls']}/{budget['max_calls']}; prompt={budget['used_prompt_chars']}/{budget['max_prompt_chars']}", "无需处理。")


def _pricing_check(pricing: dict[str, Any], manual: list[str], warnings: list[str]) -> dict[str, str]:
    input_price = _safe_float(pricing.get("input_cost_per_million_tokens"))
    output_price = _safe_float(pricing.get("output_cost_per_million_tokens"))
    if input_price < 0 or output_price < 0:
        detail = "LLM token 单价不能为负数。"
        manual.append(detail)
        warnings.append(detail)
        return _check("pricing_config", "review_required", detail, "修正 run-config.json 中的 token 单价。")
    if input_price == 0.0 and output_price == 0.0:
        return _check("pricing_config", "pass", "未配置美元单价；仅报告 token/耗时。", "如需成本审计，在配置中填写每百万 input/output token 单价。")
    if input_price == 0.0 or output_price == 0.0:
        detail = "只配置了部分 token 单价，美元成本不完整。"
        manual.append(detail)
        warnings.append(detail)
        return _check("pricing_config", "review_required", detail, "同时配置 input 与 output 每百万 token 单价。")
    return _check("pricing_config", "pass", f"input=${input_price:.4f}/M output=${output_price:.4f}/M", "无需处理。")


def _summary(ledger: dict[str, Any], budget: dict[str, Any], pricing: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, Any]:
    input_chars = _safe_int(ledger.get("total_prompt_chars"))
    output_chars = _safe_int(ledger.get("total_response_chars"))
    input_tokens = _tokens(input_chars)
    output_tokens = _tokens(output_chars)
    return {
        "total_calls": _safe_int(ledger.get("total_calls")),
        "successful_calls": _safe_int(ledger.get("successful_calls")),
        "failed_calls": _safe_int(ledger.get("failed_calls")),
        "budget_exceeded_calls": _safe_int(ledger.get("budget_exceeded_calls")),
        "input_chars": input_chars,
        "output_chars": output_chars,
        "input_tokens_estimated": input_tokens,
        "output_tokens_estimated": output_tokens,
        "total_duration_seconds": round(sum(_safe_float(stage.get("duration_seconds")) for stage in stages), 3),
        "estimated_cost_usd": _estimated_cost(input_tokens, output_tokens, pricing),
        "call_utilization": budget.get("call_utilization", 0.0),
        "prompt_utilization": budget.get("prompt_utilization", 0.0),
    }


def _budget_summary(ledger: dict[str, Any], run_config: dict[str, Any]) -> dict[str, Any]:
    llm = _dict(run_config.get("llm"))
    used_calls = _safe_int(ledger.get("total_calls"))
    used_prompt = _safe_int(ledger.get("total_prompt_chars"))
    max_calls = _safe_int(llm.get("max_calls"))
    max_prompt = _safe_int(llm.get("max_prompt_chars"))
    return {
        "used_calls": used_calls,
        "max_calls": max_calls,
        "call_utilization": round(used_calls / max_calls, 3) if max_calls > 0 else 0.0,
        "used_prompt_chars": used_prompt,
        "max_prompt_chars": max_prompt,
        "prompt_utilization": round(used_prompt / max_prompt, 3) if max_prompt > 0 else 0.0,
    }


def _stage_summaries(entries: list[dict[str, Any]], pricing: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(_stage_from_entry(entry), []).append(entry)
    summaries: list[dict[str, Any]] = []
    for stage in sorted(grouped):
        items = grouped[stage]
        input_chars = sum(_safe_int(item.get("system_chars")) + _safe_int(item.get("user_chars")) for item in items)
        output_chars = sum(_safe_int(item.get("response_chars")) for item in items)
        input_tokens = _tokens(input_chars)
        output_tokens = _tokens(output_chars)
        summaries.append(
            {
                "stage": stage,
                "calls": len(items),
                "successful_calls": sum(1 for item in items if str(item.get("status") or "") == "success"),
                "failed_calls": sum(1 for item in items if str(item.get("status") or "") == "failed"),
                "budget_exceeded_calls": sum(1 for item in items if str(item.get("status") or "") == "budget_exceeded"),
                "input_chars": input_chars,
                "output_chars": output_chars,
                "input_tokens_estimated": input_tokens,
                "output_tokens_estimated": output_tokens,
                "duration_seconds": round(sum(_safe_float(item.get("duration_seconds")) for item in items), 3),
                "estimated_cost_usd": _estimated_cost(input_tokens, output_tokens, pricing),
            }
        )
    return summaries


def _pricing(run_config: dict[str, Any]) -> dict[str, Any]:
    llm = _dict(run_config.get("llm"))
    input_price = _safe_float(llm.get("input_cost_per_million_tokens"))
    output_price = _safe_float(llm.get("output_cost_per_million_tokens"))
    return {
        "input_cost_per_million_tokens": input_price,
        "output_cost_per_million_tokens": output_price,
        "cost_estimation_enabled": input_price > 0.0 and output_price > 0.0,
    }


def _stage_from_purpose(purpose: str) -> str:
    lowered = purpose.lower()
    for stage, needles in _STAGE_RULES:
        if any(needle in lowered for needle in needles):
            return stage
    return "other"


def _stage_from_entry(entry: dict[str, Any]) -> str:
    stage = str(entry.get("stage") or "").strip().lower()
    if stage:
        return stage
    return _stage_from_purpose(str(entry.get("purpose") or ""))


def _estimated_cost(input_tokens: int, output_tokens: int, pricing: dict[str, Any]) -> float | None:
    input_price = _safe_float(pricing.get("input_cost_per_million_tokens"))
    output_price = _safe_float(pricing.get("output_cost_per_million_tokens"))
    if input_price <= 0.0 or output_price <= 0.0:
        return None
    return round((input_tokens / 1_000_000.0) * input_price + (output_tokens / 1_000_000.0) * output_price, 6)


def _tokens(chars: int) -> int:
    return ceil(max(0, chars) / CHARS_PER_TOKEN_ESTIMATE)


def _recommended_actions(status: str, blocking: list[str], manual: list[str], warnings: list[str], pricing: dict[str, Any]) -> list[str]:
    if status == "block":
        return ["先修复 LLM ledger 的缺失、失败或预算拦截，再采信 run economics。", *blocking[:4]]
    actions = [*(manual or warnings)[:4]]
    if not pricing.get("cost_estimation_enabled"):
        actions.append("如需美元成本趋势，在配置中填写 llm.input_cost_per_million_tokens 和 llm.output_cost_per_million_tokens。")
    return actions or ["可用当前报告追踪 LLM 调用、估算 token 和阶段耗时。"]


def _check(name: str, status: str, evidence: str, action: str) -> dict[str, str]:
    return {"name": name, "status": status, "evidence": evidence, "action": action}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
