from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .llm_ledger_recovery import summarize_llm_failure_recovery


LLM_TRACE_AUDIT_JSON = "13-llm-trace-audit.json"
LLM_TRACE_AUDIT_MD = "13-llm-trace-audit.md"


REQUIRED_STAGE_SPECS = [
    {
        "stage": "research_planning",
        "artifact": "00-research-plan.json",
        "stage_ids": ["research_planning"],
        "patterns": ["research planning"],
        "required_successes": 1,
        "action": "重新运行研究计划阶段，确认模型已成功返回 research planning 调用。",
    },
    {
        "stage": "literature_synthesis",
        "artifact": "01-literature.json",
        "stage_ids": ["literature_synthesis"],
        "patterns": ["literature synthesis"],
        "required_successes": 1,
        "action": "重新运行文献阶段，确认模型完成 literature synthesis，而不是只留下规则摘要。",
    },
    {
        "stage": "idea_generation",
        "artifact": "02-ideas.json",
        "stage_ids": ["idea_generation"],
        "patterns": ["research ideas"],
        "required_successes": 1,
        "action": "重新运行 idea 阶段，确认模型完成 research ideas 调用。",
    },
    {
        "stage": "experiment_planning",
        "artifact": "03-experiment-plan.json",
        "stage_ids": ["experiment_planning"],
        "patterns": ["experiment planning"],
        "required_successes": 1,
        "action": "重新运行实验计划阶段，确认模型完成 experiment planning 调用。",
    },
    {
        "stage": "paper_writing",
        "artifact": "06-paper.md",
        "stage_ids": ["paper_writing"],
        "patterns": ["paper writing"],
        "required_successes": 1,
        "action": "重新运行论文草稿阶段，确认模型完成 paper writing 调用。",
    },
    {
        "stage": "paper_review_loop",
        "artifact": "07-paper-review.json",
        "stage_ids": ["paper_review_loop"],
        "patterns": ["scientific peer review"],
        "required_successes": 1,
        "action": "重新运行论文复核阶段，确认模型完成 scientific peer review 调用。",
    },
    {
        "stage": "paper_revision",
        "artifact": "09-revised-paper.md",
        "stage_ids": ["paper_revision"],
        "patterns": ["paper revision"],
        "required_successes": 1,
        "action": "重新运行论文修订阶段，确认模型完成 paper revision 调用。",
    },
]


OPTIONAL_STAGE_SPECS = [
    {
        "stage": "online_search_query_planning",
        "artifact": "01-literature-search-strategy.json",
        "stage_ids": ["online_search_query_planning"],
        "patterns": ["academic search query planning"],
        "action": "在线/自动文献模式应有 LLM scholarly search query planning 调用。",
    }
]


def write_llm_trace_audit_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_llm_trace_audit_report(topic, run_dir)
    write_json(run_dir / LLM_TRACE_AUDIT_JSON, report)
    write_text(run_dir / LLM_TRACE_AUDIT_MD, render_llm_trace_audit_markdown(report))
    return report


def build_llm_trace_audit_report(topic: str, run_dir: Path) -> dict[str, Any]:
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    run_config = _read_json(run_dir / "run-config.json")
    ai_disclosure = _read_json(run_dir / "10-ai-disclosure.json")
    entries = _entries(ledger)
    stage_checks = _stage_checks(run_dir, entries, run_config)
    blocking_issues: list[str] = []
    warnings: list[str] = []

    if not ledger:
        blocking_issues.append("run-llm-ledger.json 缺失或不可读。")
    total_calls = _safe_int(ledger.get("total_calls")) if isinstance(ledger, dict) else 0
    successful_calls = _safe_int(ledger.get("successful_calls")) if isinstance(ledger, dict) else 0
    failed_calls = _safe_int(ledger.get("failed_calls")) if isinstance(ledger, dict) else 0
    budget_exceeded_calls = _safe_int(ledger.get("budget_exceeded_calls")) if isinstance(ledger, dict) else 0
    recovery = summarize_llm_failure_recovery(ledger)
    if total_calls <= 0:
        blocking_issues.append(f"LLM ledger total_calls={total_calls}，不能证明本 run 接入过模型。")
    if successful_calls <= 0:
        blocking_issues.append(f"LLM ledger successful_calls={successful_calls}，关键阶段没有成功模型调用。")
    if entries and total_calls != len(entries):
        warnings.append(f"LLM ledger total_calls={total_calls} 但 entries={len(entries)}，需核对账本是否被手工改写。")
    if total_calls and not entries:
        blocking_issues.append("LLM ledger 缺少 entries 明细，无法核对模型参与了哪些阶段。")
    if failed_calls:
        unrecovered = _safe_int(recovery.get("unrecovered_failed_calls"))
        recovered = _safe_int(recovery.get("recovered_failed_calls"))
        if unrecovered:
            blocking_issues.append(f"LLM ledger 记录 failed_calls={failed_calls} unrecovered={unrecovered}；完整 run 不应在未恢复的模型失败后继续宣称完成。")
        elif recovered:
            warnings.append(f"LLM ledger 记录 failed_calls={failed_calls}，但均已由后续同阶段 success 恢复。")
    if budget_exceeded_calls:
        unrecovered = _safe_int(recovery.get("unrecovered_budget_exceeded_calls"))
        recovered = _safe_int(recovery.get("recovered_budget_exceeded_calls"))
        if unrecovered:
            blocking_issues.append(f"LLM ledger 记录 budget_exceeded_calls={budget_exceeded_calls} unrecovered={unrecovered}；需要提高预算或从 checkpoint 重跑。")
        elif recovered:
            warnings.append(f"LLM ledger 记录 budget_exceeded_calls={budget_exceeded_calls}，但均已由后续同阶段 success 恢复。")

    for check in stage_checks:
        if check["status"] == "block":
            blocking_issues.append(f"{check['stage']}: {check['evidence']}")
        elif check["status"] == "warn":
            warnings.append(f"{check['stage']}: {check['evidence']}")

    disclosure_check = _ai_disclosure_check(ai_disclosure, successful_calls)
    if disclosure_check["status"] == "block":
        blocking_issues.append(disclosure_check["evidence"])
    elif disclosure_check["status"] == "warn":
        warnings.append(disclosure_check["evidence"])

    coverage = _coverage(stage_checks)
    missing_required_stages = _missing_required_stage_ids(stage_checks)
    warned_optional_stages = _warned_optional_stage_ids(stage_checks)
    status = "block" if blocking_issues else "warn" if warnings else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "generated_at": _utc_now(),
        "ledger_summary": {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "budget_exceeded_calls": budget_exceeded_calls,
            "recovered_failed_calls": recovery.get("recovered_failed_calls", 0),
            "unrecovered_failed_calls": recovery.get("unrecovered_failed_calls", 0),
            "recovered_budget_exceeded_calls": recovery.get("recovered_budget_exceeded_calls", 0),
            "unrecovered_budget_exceeded_calls": recovery.get("unrecovered_budget_exceeded_calls", 0),
            "entries": len(entries),
            "total_prompt_chars": _safe_int(ledger.get("total_prompt_chars")) if isinstance(ledger, dict) else 0,
            "total_response_chars": _safe_int(ledger.get("total_response_chars")) if isinstance(ledger, dict) else 0,
        },
        "coverage": coverage,
        "stage_gap_summary": {
            "missing_required_stage_count": len(missing_required_stages),
            "missing_required_stages": missing_required_stages,
            "warned_optional_stage_count": len(warned_optional_stages),
            "warned_optional_stages": warned_optional_stages,
        },
        "stage_checks": stage_checks,
        "ai_disclosure_check": disclosure_check,
        "blocking_issues": _dedupe(blocking_issues),
        "warnings": _dedupe(warnings),
        "manual_tasks": _manual_tasks(status, blocking_issues, warnings),
        "recommended_actions": _recommended_actions(status),
    }


def render_llm_trace_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("ledger_summary") if isinstance(report.get("ledger_summary"), dict) else {}
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    lines = [
        f"# LLM Trace Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 成功覆盖：{coverage.get('passed_required', 0)}/{coverage.get('required_stages', 0)} required stages",
        f"- 缺失成功调用阶段：{len(_missing_required_stage_ids(report.get('stage_checks') if isinstance(report.get('stage_checks'), list) else []))}",
        f"- LLM 调用：{summary.get('total_calls', 0)} total / {summary.get('successful_calls', 0)} success / {summary.get('failed_calls', 0)} failed / {summary.get('budget_exceeded_calls', 0)} budget",
        f"- Ledger entries：{summary.get('entries', 0)}",
        "",
        "## 阶段检查",
        "| 阶段 | 状态 | 成功调用 | 产物 | Stage/Purpose 匹配 | 证据 | 动作 |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in report.get("stage_checks", []) if isinstance(report.get("stage_checks"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("stage") or "")),
                    str(item.get("status") or ""),
                    str(item.get("observed_successes") or 0),
                    _cell(str(item.get("artifact") or "-")),
                    _cell(", ".join(str(value) for value in item.get("matched_entries", []) if str(value)) or "-"),
                    _cell(str(item.get("evidence") or "-")),
                    _cell(str(item.get("action") or "-")),
                ]
            )
            + " |"
        )
    disclosure = report.get("ai_disclosure_check") if isinstance(report.get("ai_disclosure_check"), dict) else {}
    lines.extend(
        [
            "",
            "## AI 披露一致性",
            f"- 状态：{disclosure.get('status') or 'unknown'}",
            f"- 证据：{disclosure.get('evidence') or '-'}",
            "",
            "## 阻断问题",
        ]
    )
    blocking = report.get("blocking_issues") if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.append("")
    lines.append("## 警告")
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- 无")
    lines.append("")
    lines.append("## 推荐动作")
    actions = report.get("recommended_actions") if isinstance(report.get("recommended_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 无")
    lines.extend(
        [
            "",
            "## 说明",
            "- 本审计只使用 ledger 中的 purpose、长度、hash 和状态，不读取完整 prompt/response。",
            "- 模型成功返回后再由确定性规则做 JSON 修复，不计为离线 LLM 兜底；但模型完全缺席、失败或预算拦截会阻断。",
        ]
    )
    return "\n".join(lines)


def _stage_checks(run_dir: Path, entries: list[dict[str, Any]], run_config: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [_required_stage_check(run_dir, entries, spec) for spec in REQUIRED_STAGE_SPECS]
    if _literature_provider(run_config) in {"online", "auto"}:
        checks.extend(_optional_stage_check(run_dir, entries, spec) for spec in OPTIONAL_STAGE_SPECS)
    return checks


def _required_stage_check(run_dir: Path, entries: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    artifact = str(spec["artifact"])
    artifact_exists = (run_dir / artifact).exists()
    required = _required_successes(run_dir, spec)
    observed, matches = _matched_successes(entries, spec)
    if not artifact_exists:
        status = "not_applicable"
        evidence = f"{artifact} 不存在，未检查该阶段。"
    elif observed >= required:
        status = "pass"
        evidence = f"observed_successes={observed}; required_successes={required}"
    else:
        status = "block"
        evidence = f"{artifact} 已生成，但匹配到的成功 LLM 调用为 {observed}/{required}。"
    return {
        "stage": spec["stage"],
        "status": status,
        "artifact": artifact,
        "artifact_exists": artifact_exists,
        "required_successes": required if artifact_exists else 0,
        "observed_successes": observed,
        "stage_ids": list(spec.get("stage_ids") or []),
        "purpose_patterns": list(spec["patterns"]),
        "matched_purposes": _legacy_matched_purposes(matches),
        "matched_entries": matches,
        "evidence": evidence,
        "action": spec["action"],
    }


def _optional_stage_check(run_dir: Path, entries: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    artifact = str(spec["artifact"])
    artifact_exists = (run_dir / artifact).exists()
    observed, matches = _matched_successes(entries, spec)
    if not artifact_exists:
        status = "not_applicable"
        evidence = f"{artifact} 不存在，未检查该可选阶段。"
    elif observed:
        status = "pass"
        evidence = f"online/auto literature provider; observed_successes={observed}"
    else:
        status = "warn"
        evidence = f"online/auto literature provider 生成了 {artifact}，但未匹配到 LLM 检索式规划调用。"
    return {
        "stage": spec["stage"],
        "status": status,
        "artifact": artifact,
        "artifact_exists": artifact_exists,
        "required_successes": 0,
        "observed_successes": observed,
        "stage_ids": list(spec.get("stage_ids") or []),
        "purpose_patterns": list(spec["patterns"]),
        "matched_purposes": _legacy_matched_purposes(matches),
        "matched_entries": matches,
        "evidence": evidence,
        "action": spec["action"],
    }


def _required_successes(run_dir: Path, spec: dict[str, Any]) -> int:
    required = _safe_int(spec.get("required_successes")) or 1
    if spec["stage"] == "paper_review_loop" and (run_dir / "10-revised-paper-review.json").exists():
        return 2
    return required


def _matched_successes(entries: list[dict[str, Any]], spec: dict[str, Any]) -> tuple[int, list[str]]:
    matched: list[str] = []
    stage_ids = {str(value).strip().lower() for value in spec.get("stage_ids", []) if str(value).strip()}
    patterns_lower = [pattern.lower() for pattern in spec.get("patterns", [])]
    for entry in entries:
        status = str(entry.get("status") or "")
        purpose = str(entry.get("purpose") or "")
        stage = str(entry.get("stage") or "").strip().lower()
        if status != "success":
            continue
        if stage and stage in stage_ids:
            matched.append(f"{stage}:{purpose or '-'}")
            continue
        lowered = purpose.lower()
        if any(pattern in lowered for pattern in patterns_lower):
            matched.append(f"legacy:{purpose}")
    return len(matched), _dedupe(matched)[:6]


def _legacy_matched_purposes(matches: list[str]) -> list[str]:
    purposes: list[str] = []
    for item in matches:
        if ":" in item:
            purposes.append(item.split(":", 1)[1])
        else:
            purposes.append(item)
    return _dedupe(purposes)[:6]


def _ai_disclosure_check(ai_disclosure: dict[str, Any], successful_calls: int) -> dict[str, Any]:
    if not ai_disclosure:
        return {
            "status": "warn",
            "evidence": "10-ai-disclosure.json 缺失或不可读；投稿前需要人工补齐 AI 使用披露。",
            "action": "重新生成 final readiness 或 submission package，确保 AI disclosure 随 LLM ledger 一起归档。",
        }
    used_ai = ai_disclosure.get("used_ai") is True
    disclosed_calls = _safe_int(ai_disclosure.get("total_llm_calls"))
    if successful_calls > 0 and not used_ai:
        return {
            "status": "block",
            "evidence": "LLM ledger 记录了成功调用，但 10-ai-disclosure.json 标记 used_ai=false。",
            "action": "重新生成 AI disclosure，并按目标 venue policy 做人工核验。",
        }
    if disclosed_calls and disclosed_calls < successful_calls:
        return {
            "status": "warn",
            "evidence": f"AI disclosure total_llm_calls={disclosed_calls} 小于 successful_calls={successful_calls}。",
            "action": "重新生成 AI disclosure，确认披露调用数与 ledger 一致。",
        }
    return {
        "status": "pass",
        "evidence": f"used_ai={used_ai}; total_llm_calls={disclosed_calls}; successful_calls={successful_calls}",
        "action": "无需处理。",
    }


def _coverage(stage_checks: list[dict[str, Any]]) -> dict[str, Any]:
    required = [item for item in stage_checks if item.get("required_successes")]
    passed = [item for item in required if item.get("status") == "pass"]
    return {
        "required_stages": len(required),
        "passed_required": len(passed),
        "coverage_ratio": round(len(passed) / max(1, len(required)), 3),
    }


def _missing_required_stage_ids(stage_checks: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("stage") or "")
        for item in stage_checks
        if item.get("required_successes") and str(item.get("status") or "") == "block" and str(item.get("stage") or "")
    ]


def _warned_optional_stage_ids(stage_checks: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("stage") or "")
        for item in stage_checks
        if not item.get("required_successes") and str(item.get("status") or "") == "warn" and str(item.get("stage") or "")
    ]


def _manual_tasks(status: str, blocking: list[str], warnings: list[str]) -> list[str]:
    if status == "pass":
        return []
    tasks = []
    if blocking:
        tasks.append("按阻断项从缺失的 LLM 阶段 checkpoint 重跑，不要用无模型产物继续向下游推进。")
    if warnings:
        tasks.append("人工核对 LLM ledger 与 AI disclosure 是否完整覆盖本 run 的模型使用。")
    return tasks


def _recommended_actions(status: str) -> list[str]:
    if status == "pass":
        return ["保留 run-llm-ledger、13-llm-trace-audit 和 10-ai-disclosure 进入投稿/归档包。"]
    if status == "warn":
        return ["核对警告后重新生成 13-llm-trace-audit；必要时刷新 10-ai-disclosure 和投稿包。"]
    return [
        "修复 LLM 配置、预算或缺失阶段后从 checkpoint/resume 重跑。",
        "确认 run-llm-ledger 中每个关键阶段至少有一次 success 调用。",
    ]


def _entries(ledger: Any) -> list[dict[str, Any]]:
    if not isinstance(ledger, dict):
        return []
    return [item for item in ledger.get("entries", []) if isinstance(item, dict)]


def _literature_provider(run_config: dict[str, Any]) -> str:
    literature = run_config.get("literature") if isinstance(run_config.get("literature"), dict) else {}
    return str(literature.get("provider") or "").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


