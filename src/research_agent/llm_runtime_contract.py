from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .llm_ledger_recovery import summarize_llm_failure_recovery


LLM_RUNTIME_CONTRACT_JSON = "13-llm-runtime-contract.json"
LLM_RUNTIME_CONTRACT_MD = "13-llm-runtime-contract.md"


_SENSITIVE_ENTRY_KEYS = {
    "content",
    "messages",
    "prompt",
    "raw_prompt",
    "raw_response",
    "response",
    "system",
    "system_prompt",
    "user",
    "user_prompt",
}


def write_llm_runtime_contract_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_llm_runtime_contract_report(topic, run_dir)
    write_json(run_dir / LLM_RUNTIME_CONTRACT_JSON, report)
    write_text(run_dir / LLM_RUNTIME_CONTRACT_MD, render_llm_runtime_contract_markdown(report))
    return report


def build_llm_runtime_contract_report(topic: str, run_dir: Path) -> dict[str, Any]:
    run_config = _read_json(run_dir / "run-config.json")
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    trace = _read_json(run_dir / "13-llm-trace-audit.json")
    economics = _read_json(run_dir / "13-run-economics-audit.json")
    ai_disclosure = _read_json(run_dir / "10-ai-disclosure.json")
    entries = _dicts(ledger.get("entries")) if ledger else []
    llm_config = _dict(run_config.get("llm"))
    checks: list[dict[str, Any]] = []
    blocking: list[str] = []
    manual: list[str] = []
    warnings: list[str] = []

    checks.append(_run_config_check(run_config, blocking))
    checks.append(_llm_provider_check(llm_config, blocking))
    checks.append(_llm_secret_check(llm_config, blocking))
    checks.append(_llm_budget_policy_check(llm_config, blocking, manual, warnings))
    checks.append(_llm_pricing_policy_check(llm_config, blocking, manual, warnings))
    checks.append(_ledger_presence_check(ledger, entries, blocking, manual, warnings))
    checks.append(_ledger_privacy_check(entries, blocking))
    checks.append(_ledger_metadata_check(entries, llm_config, blocking))
    checks.append(_audit_status_check("llm_trace_audit", trace, blocking, manual, warnings))
    checks.append(_audit_status_check("run_economics_audit", economics, blocking, manual, warnings))
    checks.append(_ai_disclosure_check(ai_disclosure, ledger, blocking, manual, warnings))

    status = "block" if blocking else "review_required" if manual or warnings else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "generated_at": _utc_now(),
        "source_projects": ["SamuelSchmidgall/AgentLaboratory", "SakanaAI/AI-Scientist-v2", "MLAgentBench"],
        "summary": {
            "provider": str(llm_config.get("provider") or ""),
            "model_configured": bool(str(llm_config.get("model") or "").strip() or str(llm_config.get("model_env") or "").strip()),
            "model_from_env": not bool(str(llm_config.get("model") or "").strip()) and bool(str(llm_config.get("model_env") or "").strip()),
            "base_url_configured": bool(str(llm_config.get("base_url") or "").strip() or str(llm_config.get("base_url_env") or "").strip()),
            "api_key_persisted": bool(str(llm_config.get("api_key") or "").strip()),
            "call_budget_configured": "max_calls" in llm_config and _safe_int(llm_config.get("max_calls")) >= 0,
            "prompt_budget_configured": "max_prompt_chars" in llm_config and _safe_int(llm_config.get("max_prompt_chars")) >= 0,
            "pricing_configured": _safe_float(llm_config.get("input_cost_per_million_tokens")) > 0 and _safe_float(llm_config.get("output_cost_per_million_tokens")) > 0,
            "total_calls": _safe_int(ledger.get("total_calls")) if ledger else 0,
            "successful_calls": _safe_int(ledger.get("successful_calls")) if ledger else 0,
            "failed_calls": _safe_int(ledger.get("failed_calls")) if ledger else 0,
            "budget_exceeded_calls": _safe_int(ledger.get("budget_exceeded_calls")) if ledger else 0,
            "entries": len(entries),
            "trace_status": str(trace.get("status") or "missing"),
            "economics_status": str(economics.get("status") or "missing"),
            "ai_disclosure_status": str(ai_disclosure.get("status") or "missing"),
        },
        "checks": checks,
        "blocking_issues": _unique(blocking),
        "manual_tasks": _unique(manual),
        "warnings": _unique(warnings),
        "recommended_actions": _recommended_actions(status, blocking, manual, warnings),
    }


def render_llm_runtime_contract_markdown(report: dict[str, Any]) -> str:
    summary = _dict(report.get("summary"))
    lines = [
        f"# LLM Runtime Contract：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Provider：{summary.get('provider') or '-'}",
        f"- 模型配置：{'yes' if summary.get('model_configured') else 'no'}；env：{'yes' if summary.get('model_from_env') else 'no'}",
        f"- API key 落盘：{'yes' if summary.get('api_key_persisted') else 'no'}",
        f"- 调用预算：{'yes' if summary.get('call_budget_configured') else 'no'}；Prompt 预算：{'yes' if summary.get('prompt_budget_configured') else 'no'}",
        f"- 成本单价：{'yes' if summary.get('pricing_configured') else 'no'}",
        f"- LLM 调用：{summary.get('total_calls', 0)} total / {summary.get('successful_calls', 0)} success / {summary.get('failed_calls', 0)} failed / {summary.get('budget_exceeded_calls', 0)} budget",
        f"- 审计状态：trace={summary.get('trace_status') or '-'} / economics={summary.get('economics_status') or '-'} / AI disclosure={summary.get('ai_disclosure_status') or '-'}",
        "",
        "## 检查项",
        "| 检查 | 状态 | 证据 | 动作 |",
        "| --- | --- | --- | --- |",
    ]
    for item in _dicts(report.get("checks")):
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
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("warnings", "警告"), ("recommended_actions", "推荐动作")]:
        values = _list(report.get(key))
        lines.extend(["", f"## {title}"])
        if values:
            prefix = "- [ ] " if key in {"manual_tasks", "recommended_actions"} else "- "
            lines.extend(prefix + str(item) for item in values)
        else:
            lines.append("- 无")
    lines.extend(
        [
            "",
            "## 隐私边界",
            "- 本契约只检查 run-config、ledger 元数据、长度/hash 统计和聚合审计状态。",
            "- 不保存 API key，不读取或输出完整 prompt/response。",
        ]
    )
    return "\n".join(lines)


def _run_config_check(run_config: dict[str, Any], blocking: list[str]) -> dict[str, str]:
    if not run_config:
        detail = "run-config.json 缺失或不可读，无法证明模型、预算和密钥落盘策略。"
        blocking.append(detail)
        return _check("run_config_presence", "block", detail, "恢复或重新运行时保留脱敏 run-config.json。")
    return _check("run_config_presence", "pass", "run-config.json 可读。", "无需处理。")


def _llm_provider_check(llm: dict[str, Any], blocking: list[str]) -> dict[str, str]:
    provider = str(llm.get("provider") or "")
    model = str(llm.get("model") or "").strip()
    model_env = str(llm.get("model_env") or "").strip()
    base_url = str(llm.get("base_url") or "").strip()
    base_url_env = str(llm.get("base_url_env") or "").strip()
    issues: list[str] = []
    from .llm import KNOWN_LLM_PROVIDERS
    if provider not in KNOWN_LLM_PROVIDERS and provider != "openai-compatible":
        issues.append(f"unsupported_provider={provider or '-'}")
    if not model and not model_env:
        issues.append("missing_model_and_model_env")
    if not base_url and not base_url_env:
        issues.append("missing_base_url_and_base_url_env")
    if issues:
        detail = "LLM 配置不满足运行契约：" + ", ".join(issues)
        blocking.append(detail)
        return _check("llm_provider_config", "block", detail, "配置 openai-compatible provider、model/model_env 和 base_url/base_url_env。")
    return _check("llm_provider_config", "pass", f"provider={provider}; model_configured={bool(model or model_env)}; base_url_configured={bool(base_url or base_url_env)}", "无需处理。")


def _llm_secret_check(llm: dict[str, Any], blocking: list[str]) -> dict[str, str]:
    if str(llm.get("api_key") or "").strip():
        detail = "run-config.json 中 llm.api_key 非空，API key 不允许落盘。"
        blocking.append(detail)
        return _check("llm_secret_persistence", "block", detail, "清除 run-config.json 中的 API key，改用环境变量或一次性表单输入。")
    return _check("llm_secret_persistence", "pass", "run-config.json 未保存 llm.api_key。", "无需处理。")


def _llm_budget_policy_check(llm: dict[str, Any], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    max_calls = _safe_int(llm.get("max_calls"))
    max_prompt = _safe_int(llm.get("max_prompt_chars"))
    if max_calls < 0 or max_prompt < 0:
        detail = f"LLM 预算不能为负数：max_calls={max_calls}, max_prompt_chars={max_prompt}。"
        blocking.append(detail)
        return _check("llm_budget_policy", "block", detail, "修正 LLM 调用和 prompt 预算配置。")
    if max_calls == 0 and max_prompt == 0:
        detail = "LLM 调用数和 prompt 字符数不限制：max_calls=0; max_prompt_chars=0。"
        return _check("llm_budget_policy", "pass", detail, "无需处理。")
    return _check("llm_budget_policy", "pass", f"max_calls={max_calls}; max_prompt_chars={max_prompt}", "无需处理。")


def _llm_pricing_policy_check(llm: dict[str, Any], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    input_price = _safe_float(llm.get("input_cost_per_million_tokens"))
    output_price = _safe_float(llm.get("output_cost_per_million_tokens"))
    if input_price < 0 or output_price < 0:
        detail = "LLM token 单价不能为负数。"
        blocking.append(detail)
        return _check("llm_pricing_policy", "block", detail, "修正 input/output token 单价。")
    if (input_price == 0) ^ (output_price == 0):
        detail = "只配置了部分 token 单价，成本审计不完整。"
        manual.append(detail)
        warnings.append(detail)
        return _check("llm_pricing_policy", "review_required", detail, "同时配置 input 与 output 每百万 token 单价，或都留空只做 token/耗时审计。")
    return _check("llm_pricing_policy", "pass", f"input=${input_price:.4f}/M; output=${output_price:.4f}/M", "无需处理。")


def _ledger_presence_check(ledger: dict[str, Any], entries: list[dict[str, Any]], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    if not ledger:
        detail = "run-llm-ledger.json 缺失或不可读。"
        blocking.append(detail)
        return _check("ledger_presence", "block", detail, "重新运行并保留 run-llm-ledger.json。")
    total = _safe_int(ledger.get("total_calls"))
    success = _safe_int(ledger.get("successful_calls"))
    failed = _safe_int(ledger.get("failed_calls"))
    budget = _safe_int(ledger.get("budget_exceeded_calls"))
    if total <= 0 or success <= 0:
        detail = f"LLM ledger 不能证明模型成功参与：total_calls={total}, successful_calls={success}。"
        blocking.append(detail)
        return _check("ledger_presence", "block", detail, "修复模型配置后从 checkpoint 重跑。")
    if total != len(entries):
        detail = f"LLM ledger total_calls={total} 但 entries={len(entries)}，账本不一致。"
        blocking.append(detail)
        return _check("ledger_presence", "block", detail, "重新生成 ledger 或从 checkpoint 重跑。")
    if failed or budget:
        recovery = summarize_llm_failure_recovery(ledger)
        unrecovered_failed = _safe_int(recovery.get("unrecovered_failed_calls"))
        unrecovered_budget = _safe_int(recovery.get("unrecovered_budget_exceeded_calls"))
        if unrecovered_failed or unrecovered_budget:
            detail = f"LLM ledger 存在 failed={failed} budget_exceeded={budget}; unrecovered_failed={unrecovered_failed}; unrecovered_budget_exceeded={unrecovered_budget}。"
            blocking.append(detail)
            return _check("ledger_presence", "block", detail, "修复失败或预算拦截调用后从 checkpoint 重跑。")
        detail = f"LLM ledger 存在 failed={failed} budget_exceeded={budget}，但均已由后续同阶段 success 恢复。"
        manual.append(detail)
        warnings.append(detail)
        return _check("ledger_presence", "review_required", detail, "人工核对恢复链路，确认最终产物来自成功调用。")
    return _check("ledger_presence", "pass", f"total_calls={total}; entries={len(entries)}; failed={failed}; budget={budget}", "无需处理。")


def _ledger_privacy_check(entries: list[dict[str, Any]], blocking: list[str]) -> dict[str, str]:
    leaked: list[str] = []
    for index, entry in enumerate(entries, start=1):
        for key in _SENSITIVE_ENTRY_KEYS:
            if _has_value(entry.get(key)):
                leaked.append(f"entry#{index}.{key}")
    if leaked:
        detail = "LLM ledger 含完整 prompt/response 风险字段：" + ", ".join(leaked[:8])
        blocking.append(detail)
        return _check("ledger_privacy", "block", detail, "移除完整文本字段，仅保留长度、hash、purpose 和状态。")
    return _check("ledger_privacy", "pass", "ledger entries 未发现完整 prompt/response 字段。", "无需处理。")


def _ledger_metadata_check(entries: list[dict[str, Any]], llm: dict[str, Any], blocking: list[str]) -> dict[str, str]:
    if not entries:
        return _check("ledger_runtime_metadata", "not_applicable", "无 ledger entries。", "先修复 ledger presence。")
    model_env = str(llm.get("model_env") or "")
    base_url_env = str(llm.get("base_url_env") or "")
    missing_model = 0
    unresolved_model = 0
    missing_base_url = 0
    unresolved_base_url = 0
    risky_base_url = 0
    for entry in entries:
        model = str(entry.get("model") or "").strip()
        base_url = str(entry.get("base_url") or "").strip()
        if not model:
            missing_model += 1
        elif model_env and model == model_env:
            unresolved_model += 1
        if not base_url:
            missing_base_url += 1
        elif base_url_env and base_url == base_url_env:
            unresolved_base_url += 1
        if "sk-" in base_url or "api_key=" in base_url.lower() or "apikey=" in base_url.lower():
            risky_base_url += 1
    issues = []
    if missing_model:
        issues.append(f"missing_model={missing_model}")
    if unresolved_model:
        issues.append(f"unresolved_model_env={unresolved_model}")
    if missing_base_url:
        issues.append(f"missing_base_url={missing_base_url}")
    if unresolved_base_url:
        issues.append(f"unresolved_base_url_env={unresolved_base_url}")
    if risky_base_url:
        issues.append(f"base_url_secret_risk={risky_base_url}")
    if issues:
        detail = "LLM ledger runtime 元数据不可审计：" + ", ".join(issues)
        blocking.append(detail)
        return _check("ledger_runtime_metadata", "block", detail, "使用新版 tracing 重新运行，记录脱敏后的实际 model/base_url。")
    return _check("ledger_runtime_metadata", "pass", f"entries={len(entries)}; model/base_url metadata resolved", "无需处理。")


def _audit_status_check(name: str, data: dict[str, Any], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    if not data:
        detail = f"{name} 缺失或不可读。"
        blocking.append(detail)
        return _check(name, "block", detail, "重新生成 LLM trace/economics 审计。")
    status = str(data.get("status") or "")
    if status == "block":
        detail = f"{name} status=block。"
        blocking.append(detail)
        return _check(name, "block", detail, "先修复对应审计中的阻断项。")
    if status in {"warn", "review_required"}:
        detail = f"{name} status={status}。"
        manual.append(detail)
        warnings.append(detail)
        return _check(name, "review_required", detail, "人工核对后重新生成运行契约。")
    return _check(name, "pass", f"status={status or '-'}", "无需处理。")


def _ai_disclosure_check(ai_disclosure: dict[str, Any], ledger: dict[str, Any], blocking: list[str], manual: list[str], warnings: list[str]) -> dict[str, str]:
    successful = _safe_int(ledger.get("successful_calls")) if ledger else 0
    if not ai_disclosure:
        detail = "10-ai-disclosure.json 缺失或不可读。"
        manual.append(detail)
        warnings.append(detail)
        return _check("ai_disclosure_alignment", "review_required", detail, "重新生成 AI disclosure，并按目标 venue policy 人工核验。")
    used_ai = ai_disclosure.get("used_ai") is True
    disclosed_calls = _safe_int(ai_disclosure.get("total_llm_calls"))
    if successful > 0 and not used_ai:
        detail = "ledger 有成功 LLM 调用，但 AI disclosure 标记 used_ai=false。"
        blocking.append(detail)
        return _check("ai_disclosure_alignment", "block", detail, "重新生成 AI disclosure。")
    if disclosed_calls and disclosed_calls < successful:
        detail = f"AI disclosure total_llm_calls={disclosed_calls} 小于 successful_calls={successful}。"
        manual.append(detail)
        warnings.append(detail)
        return _check("ai_disclosure_alignment", "review_required", detail, "刷新 AI disclosure 调用数。")
    return _check("ai_disclosure_alignment", "pass", f"used_ai={used_ai}; disclosed_calls={disclosed_calls}; successful_calls={successful}", "无需处理。")


def _recommended_actions(status: str, blocking: list[str], manual: list[str], warnings: list[str]) -> list[str]:
    if status == "block":
        return ["修复 LLM 运行契约阻断项后从 checkpoint 重跑，不采信无完整账本或配置证据的 run。", *blocking[:4]]
    if status == "review_required":
        return ["人工核对 LLM 预算、成本单价、AI disclosure 和 ledger 元数据后重新生成契约。", *(manual or warnings)[:4]]
    return ["保留 run-config、run-llm-ledger、LLM trace/economics audit 和 AI disclosure 作为正式归档证据。"]


def _check(name: str, status: str, evidence: str, action: str) -> dict[str, str]:
    return {"name": name, "status": status, "evidence": evidence, "action": action}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _safe_float(value: Any) -> float:
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


