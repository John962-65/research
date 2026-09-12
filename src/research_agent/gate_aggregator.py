"""Final gate aggregation (GATE-02).

One place combines deterministic audits, independent agent verdicts, missing
role coverage, and the human override into the single decision that governs
whether the run may produce a publishable handoff. Deterministic audits and
independent verdicts are kept as separate layers; neither may impersonate the
other.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import hashlib
import hmac

from .artifacts import write_json, write_text, cell as _cell, utc_now as _utc_now


GATE_DECISION_JSON = "10-gate-decision.json"
GATE_DECISION_MD = "10-gate-decision.md"

GATE_STATUSES = frozenset({"publishable", "repair_required", "blocked"})
OVERRIDE_REQUIRED_FIELDS = ("reviewer", "reason", "revision", "verdict_sha256", "approved")


@dataclass(frozen=True)
class GateDecision:
    status: str  # publishable | repair_required | blocked
    blocking_sources: list[str] = field(default_factory=list)
    warning_sources: list[str] = field(default_factory=list)
    missing_verdict_roles: list[str] = field(default_factory=list)
    overridden: bool = False
    override: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


def aggregate_final_decision(
    *,
    deterministic_audits: dict[str, dict[str, Any]],
    independent_deliberation: dict[str, Any] | None,
    expected_roles: list[str] | None = None,
    revision: int = 0,
    human_override: dict[str, Any] | None = None,
) -> GateDecision:
    """Aggregate every gate input into the one final decision.

    ``deterministic_audits`` maps an audit name to its report dict (must have
    a ``status``). ``independent_deliberation`` is the report produced by
    ``run_independent_deliberation`` (verdict layer), if the feature is on.
    """
    blocking_sources: list[str] = []
    warning_sources: list[str] = []
    for name, report in deterministic_audits.items():
        status = str((report or {}).get("status") or "")
        if status not in {"pass", "warn", "review_required"}:
            blocking_sources.append(f"deterministic:{name}")
        elif status in {"warn", "review_required"}:
            warning_sources.append(f"deterministic:{name}")

    missing_roles: list[str] = []
    verdicts: list[dict[str, Any]] = []
    if independent_deliberation is not None:
        if independent_deliberation.get("status") in {"block", "invalid"}:
            blocking_sources.append("independent_deliberation")
        if "revision" in independent_deliberation and independent_deliberation["revision"] != revision:
            blocking_sources.append("independent_deliberation:stale_revision")
        verdicts = [
            item for item in (independent_deliberation.get("verdicts") or []) if isinstance(item, dict)
        ]
        for verdict in verdicts:
            verdict_value = str(verdict.get("verdict") or "")
            agent_id = str(verdict.get("agent_id") or "unknown")
            if verdict_value not in {"pass", "warn"}:
                blocking_sources.append(f"verdict:{agent_id}")
            elif verdict_value == "warn":
                warning_sources.append(f"verdict:{agent_id}")
    for role_id in expected_roles or []:
        if not any(str(item.get("agent_id") or "") == role_id for item in verdicts):
            missing_roles.append(role_id)
    if missing_roles:
        blocking_sources.extend(f"missing_verdict:{role_id}" for role_id in missing_roles)

    status = "blocked" if blocking_sources else ("repair_required" if warning_sources else "publishable")
    # Bind approval to the actual evidence, not just the names of its sources.
    # Deliberately exclude the output timestamp and the override itself.
    verdict_sha256 = hashlib.sha256(json.dumps({
        "schema_version": 1,
        "revision": revision,
        "deterministic_audits": deterministic_audits,
        "independent_deliberation": independent_deliberation,
        "expected_roles": sorted(set(expected_roles or [])),
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()

    override_applied = False
    override_payload: dict[str, Any] = {}
    if human_override is not None and status == "blocked":
        override = dict(human_override)
        missing = [
            name
            for name in OVERRIDE_REQUIRED_FIELDS
            if override.get(name) is None or override.get(name) == ""
        ]
        errors = [f"missing fields {','.join(missing)}"] if missing else []
        if override.get("approved") is not True:
            errors.append("approved must be true")
        if type(override.get("revision")) is not int or override["revision"] != revision:
            errors.append("revision does not match current decision")
        for name, limit in (("reviewer", 120), ("reason", 500)):
            value = override.get(name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                errors.append(f"{name} must be nonblank text of at most {limit} characters")
        digest = override.get("verdict_sha256")
        if not isinstance(digest, str) or not digest.isascii() or not hmac.compare_digest(digest, verdict_sha256):
            errors.append("verdict_sha256 does not match current evidence")
        if errors:
            warning_sources.extend(f"override_rejected:{error}" for error in errors)
        else:
            override_applied = True
            override_payload = {
                "reviewer": str(override.get("reviewer"))[:120],
                "reason": str(override.get("reason"))[:500],
                "revision": override.get("revision"),
                "verdict_sha256": str(override.get("verdict_sha256"))[:64],
                "approved": bool(override.get("approved")),
                "original_status": status,
            }
            status = "publishable"

    decision = GateDecision(
        status=status,
        blocking_sources=blocking_sources,
        warning_sources=warning_sources,
        missing_verdict_roles=missing_roles,
        overridden=override_applied,
        override=override_payload,
        inputs={
            "revision": revision,
            "deterministic_audits": sorted(deterministic_audits),
            "independent_deliberation": independent_deliberation is not None,
            "verdict_count": len(verdicts),
            "verdict_sha256": verdict_sha256,
        },
        created_at=_utc_now(),
    )
    return decision


def write_gate_decision_artifacts(run_dir: Path, decision: GateDecision) -> tuple[Path, Path]:
    payload = asdict(decision)
    json_path = Path(run_dir) / GATE_DECISION_JSON
    md_path = Path(run_dir) / GATE_DECISION_MD
    write_json(json_path, payload)
    write_text(md_path, render_gate_decision_markdown(payload))
    return json_path, md_path


def render_gate_decision_markdown(decision: dict[str, Any]) -> str:
    lines = [
        "# 最终 Gate 决策",
        "",
        f"- 状态：{decision.get('status')}",
        f"- 人工覆盖：{'是（' + str((decision.get('override') or {}).get('reviewer')) + '）' if decision.get('overridden') else '否'}",
        f"- 生成时间：{decision.get('created_at')}",
        "",
        "## 阻断来源",
    ]
    blocking = decision.get("blocking_sources") or []
    lines.extend(f"- {source}" for source in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 警告来源"])
    warnings = decision.get("warning_sources") or []
    lines.extend(f"- {source}" for source in warnings) if warnings else lines.append("- 无")
    missing = decision.get("missing_verdict_roles") or []
    if missing:
        lines.extend(["", "## 缺失的独立 Verdict 角色"])
        lines.extend(f"- {role}" for role in missing)
    lines.extend([
        "",
        "## 说明",
        "- blocked 状态下不允许生成 publishable handoff；人工 override 必须记录 reviewer/reason/revision/verdict 哈希。",
        "- 确定性审计与独立 verdict 是两层证据，彼此独立保存，不能互相冒充。",
    ])
    return "\n".join(lines)


def load_human_override(run_dir: Path) -> dict[str, Any] | None:
    """Read the optional human override file; absent means no override."""
    path = Path(run_dir) / "10-gate-override.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
