"""Independent multi-agent deliberation (AGENT-01).

The deterministic projection in ``multi_agent_deliberation.py`` stays as the
first safety layer: it re-derives role verdicts from the audit artifacts with
pure rules. This module adds the *independent execution layer*: each role
receives its own minimal evidence bundle, calls the role-routed LLM
serially, and returns a strongly typed verdict bound to the exact ledger
call, model, and workflow revision. A verdict is only counted as independent
when it carries its own call id and evidence hashes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import read_json, write_json, write_text, cell as _cell, utc_now as _utc_now


INDEPENDENT_DELIBERATION_JSON = "10-independent-deliberation.json"
INDEPENDENT_DELIBERATION_MD = "10-independent-deliberation.md"

VALID_VERDICTS = frozenset({"pass", "warn", "block"})

# Each independent role sees only the minimal artifacts its responsibility
# needs; verdicts must cite which of them the conclusion rests on.
ROLE_EVIDENCE_VIEWS: dict[str, tuple[str, ...]] = {
    "evidence_curator": ("01-context.json", "01-citation-audit.json", "10-citation-grounding.json"),
    "method_architect": ("02-ideas.json", "03-experiment-plan.json"),
    "benchmark_engineer": ("03-benchmark-plan.json", "04-benchmark-result-schema-audit.json", "04-benchmark-evidence-audit.json"),
    "statistician": ("04-statistics.json", "04-result-validation.json", "04-hypothesis-outcome.json"),
    "skeptical_reviewer": ("09-revised-paper.md", "10-claim-traceability.json"),
    "manuscript_editor": ("09-revised-paper.md", "10-results-presentation.json", "10-code-data-availability.json"),
}

VERDICT_SCHEMA = {
    "verdict": "pass|warn|block",
    "confidence": 0.0,
    "evidence_refs": ["01-context.json"],
    "counter_evidence": ["what contradicts the conclusion"],
    "required_actions": ["what must happen before this can be accepted"],
    "summary": "one-paragraph justification",
}


@dataclass(frozen=True)
class AgentVerdict:
    agent_id: str
    role: str
    responsibility: str
    verdict: str
    confidence: float
    evidence_refs: list[str]
    counter_evidence: list[str]
    required_actions: list[str]
    summary: str
    route_id: str
    model: str
    call_id: int
    revision: int
    attempt_id: str
    prompt_sha256: str
    response_sha256: str
    independent: bool
    created_at: str
    validation_error: str = ""


def run_independent_deliberation(
    topic: str,
    run_dir: Path,
    config: Any,
    llm: Any,
    roles: list[str] | None = None,
    review_input_sha256: str = "",
) -> dict[str, Any]:
    """Run one independent LLM verdict per role; never raises on role failure.

    ``review_input_sha256`` 把本次评审绑定到评审输入快照（decision-contract
    §4）；恢复时快照不一致的旧 deliberation 不得复用（A06）。
    """
    from .agent_runtime import agent_for_stage
    from .multi_agent_assignment import AGENT_PROFILES
    from .provenance import active_revision
    from .workflow_state import read_node_states

    profiles = {str(profile["agent_id"]): profile for profile in AGENT_PROFILES}
    role_ids = roles or [role_id for role_id in ROLE_EVIDENCE_VIEWS if role_id in profiles]
    revision = active_revision(run_dir)
    states = read_node_states(run_dir)
    attempt_id = f"deliberation-r{revision}"
    verdicts: list[dict[str, Any]] = []
    for agent_id in role_ids:
        profile = profiles.get(agent_id, {})
        try:
            verdict = _run_role_verdict(
                topic,
                run_dir,
                config,
                llm,
                agent_id=agent_id,
                profile=profile,
                revision=revision,
                attempt_id=attempt_id,
                stage_node_status=str(states.get(agent_id, {}).get("status") or "pending"),
            )
        except Exception as exc:
            verdict = {
                "agent_id": agent_id,
                "role": str(profile.get("role") or agent_id),
                "responsibility": str(profile.get("responsibility") or ""),
                "verdict": "invalid",
                "confidence": 0.0,
                "evidence_refs": [],
                "counter_evidence": [],
                "required_actions": [f"重新执行 {agent_id} 独立审查：{exc}"[:200]],
                "summary": "",
                "route_id": f"T09:{agent_id}",
                "model": "",
                "call_id": 0,
                "revision": revision,
                "attempt_id": attempt_id,
                "prompt_sha256": "",
                "response_sha256": "",
                "independent": False,
                "created_at": _utc_now(),
                "validation_error": str(exc)[:280],
            }
        verdicts.append(verdict)
    report = {
        "schema_version": 1,
        "topic": topic,
        "independent_agent_execution": True,
        "revision": revision,
        "attempt_id": attempt_id,
        "review_input_sha256": str(review_input_sha256),
        "verdicts": verdicts,
        "status": _aggregate_status(verdicts),
        "created_at": _utc_now(),
    }
    write_json(run_dir / INDEPENDENT_DELIBERATION_JSON, report)
    write_text(run_dir / INDEPENDENT_DELIBERATION_MD, _render_markdown(report))
    return report


def _run_role_verdict(
    topic: str,
    run_dir: Path,
    config: Any,
    llm: Any,
    *,
    agent_id: str,
    profile: dict[str, Any],
    revision: int,
    attempt_id: str,
    stage_node_status: str,
) -> dict[str, Any]:
    from .llm_trace import complete_with_purpose_detail, record_validation_result

    evidence = _evidence_bundle(run_dir, ROLE_EVIDENCE_VIEWS.get(agent_id, ()))
    prompt_sha = hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    system = (
        "Independent multi-agent deliberation. You are one reviewer with a narrow responsibility; "
        "other roles cover the rest. Return ONLY a JSON object matching: "
        f"{json.dumps(VERDICT_SCHEMA, ensure_ascii=False)}"
    )
    user = (
        f"研究课题：{topic}\n角色：{profile.get('role') or agent_id}（{agent_id}）\n"
        f"职责：{profile.get('responsibility') or ''}\n"
        f"节点状态：{stage_node_status}\n\n"
        "以下是你职责范围内的全部证据（JSON），请独立给出 verdict：\n"
        + json.dumps(evidence, ensure_ascii=False)
    )
    response, call_id = complete_with_purpose_detail(
        llm,
        system,
        user,
        stage="paper_deliberation",
        purpose=f"independent deliberation: {agent_id}",
        agent_id=agent_id,
        requires_validation=True,
    )
    parsed, validation_error = _parse_verdict(response)
    verdict_value = str(parsed.get("verdict") or "")
    valid = verdict_value in VALID_VERDICTS and not validation_error
    from .llm_trace import record_validation_result

    record_validation_result(
        llm,
        stage="paper_deliberation",
        valid=valid,
        error=validation_error,
        call_id=call_id,
    )
    return {
        "agent_id": agent_id,
        "role": str(profile.get("role") or agent_id),
        "responsibility": str(profile.get("responsibility") or ""),
        "verdict": verdict_value if valid else "invalid",
        "confidence": _safe_confidence(parsed.get("confidence")) if valid else 0.0,
        "evidence_refs": [str(item) for item in parsed.get("evidence_refs", [])][:10] if valid else [],
        "counter_evidence": [str(item) for item in parsed.get("counter_evidence", [])][:10] if valid else [],
        "required_actions": [str(item) for item in parsed.get("required_actions", [])][:10] if valid else [],
        "summary": str(parsed.get("summary") or "")[:800] if valid else "",
        "route_id": f"T09:{agent_id}",
        "model": _route_model(llm, agent_id),
        "call_id": call_id,
        "revision": revision,
        "attempt_id": attempt_id,
        "prompt_sha256": prompt_sha[:16],
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest()[:16] if response else "",
        "independent": valid and call_id > 0,
        "created_at": _utc_now(),
        "validation_error": validation_error,
    }


def _route_model(llm: Any, agent_id: str) -> str:
    try:
        prepared = llm.prepare_request(system="", user="", stage="paper_deliberation", agent_id=agent_id)
        return str(getattr(prepared.route, "model", "") or "")
    except Exception:
        return ""


def _evidence_bundle(run_dir: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    for name in paths:
        path = run_dir / name
        if not path.is_file():
            bundle[name] = {"available": False}
            continue
        if name.endswith(".json"):
            try:
                bundle[name] = {"available": True, "content": read_json(path)}
            except (OSError, json.JSONDecodeError):
                bundle[name] = {"available": False}
        else:
            try:
                bundle[name] = {"available": True, "content": path.read_text(encoding="utf-8")[:20000]}
            except OSError:
                bundle[name] = {"available": False}
    return bundle


def _parse_verdict(response: str) -> tuple[dict[str, Any], str]:
    text = str(response or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"response is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, "response is not a JSON object"
    verdict = str(data.get("verdict") or "")
    if verdict not in VALID_VERDICTS:
        return {}, f"verdict must be one of {sorted(VALID_VERDICTS)}"
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        return {}, "confidence must be a number in [0, 1]"
    return data, ""


def _safe_confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_status(verdicts: list[dict[str, Any]]) -> str:
    values = [str(item.get("verdict") or "") for item in verdicts]
    if "block" in values or "invalid" in values or (verdicts and "" in values):
        return "block"
    if "warn" in values:
        return "warn"
    return "pass"


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 独立多智能体 Deliberation：{report.get('topic') or ''}",
        "",
        f"- 独立执行：{'是' if report.get('independent_agent_execution') else '否'}",
        f"- Revision：{report.get('revision')}",
        f"- 汇总状态：{report.get('status')}",
        "",
        "| 角色 | Verdict | 置信度 | Call | Model | 摘要 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for verdict in report.get("verdicts", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(f"{verdict.get('role')} ({verdict.get('agent_id')})"),
                    _cell(str(verdict.get("verdict"))),
                    f"{verdict.get('confidence', 0):.2f}",
                    str(verdict.get("call_id") or "-"),
                    _cell(str(verdict.get("model") or "-")),
                    _cell(str(verdict.get("summary") or verdict.get("validation_error") or "-")),
                ]
            )
            + " |"
        )
    lines.extend([
        "",
        "## 说明",
        "- 每条 verdict 来自独立的一次角色化 LLM 调用；call id 可在 run-llm-ledger.json 中核对。",
        "- verdict=invalid 或调用失败的角色按 block 处理，不能计入独立共识。",
    ])
    return "\n".join(lines)
