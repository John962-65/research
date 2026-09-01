from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text


AI_DISCLOSURE_JSON = "10-ai-disclosure.json"
AI_DISCLOSURE_MD = "10-ai-disclosure.md"


def write_ai_disclosure_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_ai_disclosure_report(topic, run_dir)
    write_json(run_dir / AI_DISCLOSURE_JSON, report)
    write_text(run_dir / AI_DISCLOSURE_MD, render_ai_disclosure_markdown(report))
    return report


def build_ai_disclosure_report(topic: str, run_dir: Path) -> dict[str, Any]:
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    manifest = _read_json(run_dir / "run-manifest.json")
    total_calls = _safe_int(ledger.get("total_calls")) if isinstance(ledger, dict) else 0
    successful_calls = _safe_int(ledger.get("successful_calls")) if isinstance(ledger, dict) else 0
    failed_calls = _safe_int(ledger.get("failed_calls")) if isinstance(ledger, dict) else 0
    purposes = _purposes(ledger)
    generated_artifacts = _generated_artifacts(manifest)
    used_ai = total_calls > 0
    status = "needs_human_policy_check" if used_ai else "not_applicable"
    statement = _disclosure_statement(used_ai)
    manual_tasks = _manual_tasks(used_ai)
    warnings = []
    if used_ai and not purposes:
        warnings.append("LLM ledger 存在调用计数，但缺少用途明细；投稿前需人工核对 run-llm-ledger。")
    if not isinstance(ledger, dict) or not ledger:
        warnings.append("缺少 run-llm-ledger.json，无法完整判断 AI 使用范围。")
        status = "needs_human_policy_check"
        manual_tasks.append("人工核对该 run 是否使用外部 LLM，并按目标 venue 政策补写披露。")
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "used_ai": used_ai,
        "total_llm_calls": total_calls,
        "successful_llm_calls": successful_calls,
        "failed_llm_calls": failed_calls,
        "llm_purposes": purposes,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts_sample": generated_artifacts[:12],
        "disclosure_statement": statement,
        "human_responsibility_statement": (
            "Human researchers remain responsible for verifying the literature, experiments, claims, "
            "authorship, venue policy compliance, and final submitted manuscript."
        ),
        "manual_tasks": _dedupe(manual_tasks),
        "warnings": _dedupe(warnings),
        "recommended_locations": ["Methods", "Acknowledgements", "Cover letter", "Submission system AI-use field"],
    }


def render_ai_disclosure_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# AI 使用披露：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 使用 AI/LLM：{'yes' if report.get('used_ai') else 'no'}",
        f"- LLM 调用：{report.get('total_llm_calls', 0)} total / {report.get('successful_llm_calls', 0)} success / {report.get('failed_llm_calls', 0)} failed",
        f"- 生成产物样本：{report.get('generated_artifact_count', 0)}",
        "",
        "## 建议披露文本",
        str(report.get("disclosure_statement") or "-"),
        "",
        "## 人类责任声明",
        str(report.get("human_responsibility_statement") or "-"),
        "",
    ]
    for key, title in [("llm_purposes", "LLM 用途"), ("recommended_locations", "建议放置位置"), ("warnings", "警告"), ("manual_tasks", "人工待办")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.append(f"## {title}")
        if values:
            prefix = "- [ ] " if key == "manual_tasks" else "- "
            lines.extend(prefix + str(item) for item in values)
        else:
            lines.append("- 无")
        lines.append("")
    artifacts = report.get("generated_artifacts_sample") if isinstance(report.get("generated_artifacts_sample"), list) else []
    lines.extend(["## 生成产物样本"])
    lines.extend(f"- {item}" for item in artifacts) if artifacts else lines.append("- 无")
    return "\n".join(lines)


def _disclosure_statement(used_ai: bool) -> str:
    if not used_ai:
        return "No LLM calls were recorded for this run. Confirm manually before submission."
    return (
        "This manuscript was prepared with assistance from an automated research-agent workflow using large language models. "
        "The system assisted with research planning, literature-grounded ideation, experiment planning, result analysis, "
        "drafting, revision, and audit generation. All literature, experiments, claims, authorship decisions, and venue-policy "
        "requirements should be manually verified by the human researchers before submission."
    )


def _manual_tasks(used_ai: bool) -> list[str]:
    if not used_ai:
        return ["确认该 run 未使用外部 LLM；若人工后续使用 AI 工具，按目标 venue 政策补充披露。"]
    return [
        "按目标会议/期刊 AI policy 调整披露措辞，不要直接提交未经人工确认的通用文本。",
        "在 Methods、Acknowledgements、cover letter 或投稿系统 AI-use 字段中加入披露。",
        "人工确认作者贡献、责任归属、引用和实验结论，避免把自动生成内容当作已核验事实。",
    ]


def _purposes(ledger: Any) -> list[str]:
    if not isinstance(ledger, dict):
        return []
    purposes: list[str] = []
    for item in ledger.get("entries", []) if isinstance(ledger.get("entries"), list) else []:
        if isinstance(item, dict):
            purpose = str(item.get("purpose") or "").strip()
            status = str(item.get("status") or "").strip()
            if purpose:
                purposes.append(f"{purpose} ({status or 'unknown'})")
    return _dedupe(purposes)[:16]


def _generated_artifacts(manifest: Any) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    result: list[str] = []
    for item in manifest.get("artifacts", []) if isinstance(manifest.get("artifacts"), list) else []:
        if isinstance(item, dict):
            path = str(item.get("path") or "").strip()
            if path:
                result.append(path)
    if result:
        return _dedupe(result)
    for event in manifest.get("events", []) if isinstance(manifest.get("events"), list) else []:
        if isinstance(event, dict):
            for path in event.get("outputs", []) if isinstance(event.get("outputs"), list) else []:
                if str(path).strip():
                    result.append(str(path).strip())
    return _dedupe(result)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
