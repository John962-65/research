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
GATE_RULE_VERSION = "2"
OVERRIDE_REQUIRED_FIELDS = ("reviewer", "reason", "revision", "verdict_sha256", "approved")

# decision-contract §3.1：可覆盖原因码（人工可以接受的已知风险）。
OVERRIDE_REASON_CODES = frozenset(
    {"scope_limitation", "advisory_only", "documented_exception", "known_deferral", "resource_constraint"}
)
# decision-contract §3.2：不可覆盖原因码（出现即拒绝覆盖，补材料后重新检查）。
NON_OVERRIDABLE_REASON_CODES = frozenset(
    {"corrupted_input", "unverifiable_source", "invalid_approval", "missing_required_evidence", "contract_violation"}
)


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
    review_input_snapshot: dict[str, Any] | None = None,
    non_overridable_reasons: list[str] | None = None,
    llm_ledger: list[dict[str, Any]] | None = None,
) -> GateDecision:
    """Aggregate every gate input into the one final decision.

    ``deterministic_audits`` maps an audit name to its report dict (must have
    a ``status``). Reports are bound by FULL content: any change to an audit
    body changes ``verdict_sha256`` and invalidates prior approvals (A05).
    ``review_input_snapshot`` is the decision-contract §4 review-input
    snapshot (files + inline inputs, no review outputs); its digest joins the
    approval binding. ``non_overridable_reasons`` marks blocking situations
    that a human override may not clear (contract §3.2).
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
    ledger_by_call = {
        int(entry.get("call_id") or 0): entry
        for entry in (llm_ledger or [])
        if isinstance(entry, dict) and entry.get("call_id") is not None
    }
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
            # A09：用实际调用账本核验 pass/warn 票；不信任 JSON 自报的
            # independent 标记。核验失败按阻断处理，原始响应保留在
            # deliberation 文件中供排查。
            if verdict_value in {"pass", "warn"} and llm_ledger is not None:
                problem = _verdict_ledger_problem(verdict, ledger_by_call)
                if problem:
                    blocking_sources.append(f"verdict:{agent_id}:unverified_call")
                    warning_sources.append(f"verdict:{agent_id}:{problem}")
    for role_id in expected_roles or []:
        if not any(str(item.get("agent_id") or "") == role_id for item in verdicts):
            missing_roles.append(role_id)
    if missing_roles:
        blocking_sources.extend(f"missing_verdict:{role_id}" for role_id in missing_roles)

    snapshot_digest = ""
    if isinstance(review_input_snapshot, dict) and review_input_snapshot.get("items"):
        snapshot_digest = str(review_input_snapshot.get("digest") or "")
        blocking_sources.extend(
            f"snapshot:invalid_input:{item.get('name')}"
            for item in review_input_snapshot.get("items", [])
            if isinstance(item, dict) and item.get("invalid")
        )

    status = "blocked" if blocking_sources else ("repair_required" if warning_sources else "publishable")
    # Bind approval to the actual evidence content, not just the names of its
    # sources: full audit bodies + the review-input snapshot digest.
    # Deliberately exclude the output timestamp and the override itself.
    verdict_sha256 = hashlib.sha256(json.dumps({
        "rule_version": GATE_RULE_VERSION,
        "revision": revision,
        "deterministic_audits": deterministic_audits,
        "independent_deliberation": independent_deliberation,
        "expected_roles": sorted(set(expected_roles or [])),
        "review_input_digest": snapshot_digest,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()

    override_applied = False
    override_payload: dict[str, Any] = {}
    if human_override is not None and status == "blocked":
        approved_blockers, override_errors = _override_approved_blockers(
            human_override, blocking_sources=blocking_sources
        )
        errors = _validate_override(
            human_override,
            revision=revision,
            verdict_sha256=verdict_sha256,
            blocking_sources=blocking_sources,
            non_overridable_reasons=non_overridable_reasons or [],
        )
        errors = [*override_errors, *errors]
        if errors:
            warning_sources.extend(f"override_rejected:{error}" for error in errors)
        else:
            # 逐项批准、逐项消解：覆盖只消解批准人明确列出且属于可覆盖类别
            # 的阻断；任何未被合法覆盖的阻断（含系统判定的不可覆盖项）继续
            # 阻止放行。原始阻断记录全部保留。
            override = dict(human_override)
            dissolved: list[str] = []
            remaining: list[str] = []
            for name in blocking_sources:
                overridable, why = _blocker_overridability(name, deterministic_audits)
                if name in approved_blockers and overridable:
                    dissolved.append(name)
                    continue
                remaining.append(name)
                if name in approved_blockers and not overridable:
                    warning_sources.append(f"override_rejected:non_overridable:{name}:{why}")
            override_applied = True
            override_payload = {
                "reviewer": str(override.get("reviewer"))[:120],
                "reason": str(override.get("reason"))[:500],
                "reason_code": str(override.get("reason_code")),
                "approval_object": str(override.get("approval_object")),
                "approved_blockers": list(approved_blockers),
                "scope": str(override.get("scope"))[:300],
                "revision": override.get("revision"),
                "verdict_sha256": str(override.get("verdict_sha256"))[:64],
                "approved": bool(override.get("approved")),
                "original_status": status,
                "original_blocking_sources": list(blocking_sources),
                "dissolved_blockers": dissolved,
                "remaining_blockers": remaining,
                "status_after": "publishable" if not remaining else "blocked",
            }
            if remaining:
                warning_sources.append(
                    "override_partial:批准未覆盖全部阻断，剩余阻断继续阻止放行："
                    + ", ".join(remaining[:5])
                )
            else:
                status = "publishable"

    decision = GateDecision(
        status=status,
        blocking_sources=blocking_sources,
        warning_sources=warning_sources,
        missing_verdict_roles=missing_roles,
        overridden=override_applied,
        override=override_payload,
        inputs={
            "rule_version": GATE_RULE_VERSION,
            "revision": revision,
            "deterministic_audits": sorted(deterministic_audits),
            "independent_deliberation": independent_deliberation is not None,
            "verdict_count": len(verdicts),
            "verdict_sha256": verdict_sha256,
            "review_input_digest": snapshot_digest,
            "non_overridable_reasons": sorted(set(non_overridable_reasons or [])),
        },
        created_at=_utc_now(),
    )
    return decision


def _override_approved_blockers(
    override: dict[str, Any], *, blocking_sources: list[str]
) -> tuple[list[str], list[str]]:
    """解析覆盖批准的阻断清单；返回 (批准清单, 错误列表)。

    ``approved_blockers``（列表）为规范字段；旧的 ``approval_object``（单个）
    作为兼容别名。批准的每一项都必须匹配当前实际阻断来源。
    """
    raw = override.get("approved_blockers")
    items: list[str] = []
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        items = [raw.strip()]
    elif isinstance(override.get("approval_object"), str) and override.get("approval_object").strip():
        items = [str(override.get("approval_object")).strip()]
    errors: list[str] = []
    if not items:
        errors.append("approved_blockers must list at least one current blocking source")
        return [], errors
    unknown = [item for item in items if item not in blocking_sources]
    if unknown:
        errors.append("approved_blockers must match current blocking sources: unknown " + ", ".join(unknown[:4]))
    deduped = list(dict.fromkeys(items))
    return deduped, errors


def _blocker_overridability(name: str, deterministic_audits: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    """由系统推导阻断来源是否可被人工覆盖（不依赖批准人填写的原因码）。

    不可覆盖（任务书/decision-contract §3.2 的系统识别）：
    - 缺少必需评审角色（missing_verdict:*）
    - 评审输入快照损坏/不可核验（snapshot:*）
    - verdict 与调用账本核验失败（verdict:*:unverified_call）
    - 独立评审层整体阻断（independent_deliberation）
    - 确定性审计自报 overridable=false（如 provenance/来源不可核验）
    其余确定性阻断默认可覆盖（需合法覆盖字段齐全且逐项列出）。
    """
    if name.startswith(("missing_verdict:", "snapshot:", "verdict:")) or name == "independent_deliberation":
        return False, "system_identified_non_overridable"
    if name.startswith("deterministic:"):
        audit_name = name.split(":", 1)[1]
        report = deterministic_audits.get(audit_name) or {}
        if report.get("overridable") is False:
            return False, str(report.get("block_reason_code") or "audit_declared_non_overridable")
    return True, ""


def _verdict_ledger_problem(verdict: dict[str, Any], ledger_by_call: dict[int, dict[str, Any]]) -> str:
    """核验一条 pass/warn verdict 的调用账本凭据；返回问题说明或空串。"""
    try:
        call_id = int(verdict.get("call_id") or 0)
    except (TypeError, ValueError):
        call_id = 0
    if call_id <= 0:
        return "missing call_id"
    entry = ledger_by_call.get(call_id)
    if entry is None:
        return "call_id not found in ledger"
    if str(entry.get("status") or "") != "success":
        return f"call status {entry.get('status') or 'unknown'} is not success"
    if str(entry.get("agent_id") or "") != str(verdict.get("agent_id") or ""):
        return "call agent_id does not match verdict role"
    if str(entry.get("stage") or "") != "paper_deliberation":
        return f"call stage {entry.get('stage') or 'unknown'} is not paper_deliberation"
    entry_response = str(entry.get("response_sha256") or "")
    verdict_response = str(verdict.get("response_sha256") or "")
    if entry_response and verdict_response and not (
        entry_response.startswith(verdict_response) or verdict_response.startswith(entry_response)
    ):
        return "response hash does not match ledger"
    return ""


def _validate_override(
    override: dict[str, Any],
    *,
    revision: int,
    verdict_sha256: str,
    blocking_sources: list[str],
    non_overridable_reasons: list[str],
) -> list[str]:
    """decision-contract §3.3 的覆盖校验；返回错误列表（空 = 通过）。"""
    errors: list[str] = []
    missing = [
        name
        for name in (*OVERRIDE_REQUIRED_FIELDS, "reason_code", "approval_object", "scope")
        if override.get(name) is None or override.get(name) == ""
    ]
    if missing:
        errors.append(f"missing fields {','.join(missing)}")
        return errors
    if override.get("approved") is not True:
        errors.append("approved must be true")
    if type(override.get("revision")) is not int or override["revision"] != revision:
        errors.append("revision does not match current decision")
    for name, limit in (("reviewer", 120), ("reason", 500), ("approval_object", 200), ("scope", 300)):
        value = override.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            errors.append(f"{name} must be nonblank text of at most {limit} characters")
    reason_code = override.get("reason_code")
    if reason_code not in OVERRIDE_REASON_CODES:
        errors.append(f"reason_code must be one of {sorted(OVERRIDE_REASON_CODES)}")
    elif str(reason_code) in NON_OVERRIDABLE_REASON_CODES:
        errors.append(f"reason_code {reason_code} is not overridable")
    digest = override.get("verdict_sha256")
    if not isinstance(digest, str) or not digest.isascii() or not hmac.compare_digest(digest, verdict_sha256):
        errors.append("verdict_sha256 does not match current evidence")
    for reason in non_overridable_reasons:
        errors.append(f"non_overridable:{reason}")
    return errors


def write_gate_decision_artifacts(run_dir: Path, decision: GateDecision) -> tuple[Path, Path]:
    payload = asdict(decision)
    json_path = Path(run_dir) / GATE_DECISION_JSON
    md_path = Path(run_dir) / GATE_DECISION_MD
    write_json(json_path, payload)
    write_text(md_path, render_gate_decision_markdown(payload))
    return json_path, md_path


def render_gate_decision_markdown(decision: dict[str, Any]) -> str:
    override = decision.get("override") or {}
    lines = [
        "# 最终 Gate 决策",
        "",
        f"- 状态：{decision.get('status')}",
        f"- 人工覆盖：{'是（' + str(override.get('reviewer')) + '，原因码 ' + str(override.get('reason_code')) + '）' if decision.get('overridden') else '否'}",
        f"- 规则版本：{(decision.get('inputs') or {}).get('rule_version', '-')}",
        f"- 评审输入快照：{(decision.get('inputs') or {}).get('review_input_digest') or '未绑定'}",
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
    if decision.get("overridden"):
        lines.extend([
            "",
            "## 覆盖记录",
            f"- 审批对象：{override.get('approval_object')}",
            f"- 范围：{override.get('scope')}",
            f"- 理由：{override.get('reason')}",
            f"- 覆盖前机器状态：{override.get('original_status')}（原始阻断来源保留在上方，不因批准消除）",
        ])
    lines.extend([
        "",
        "## 说明",
        "- blocked 状态下不允许生成 publishable handoff；人工 override 必须记录 reviewer/reason/reason_code/approval_object/scope/revision/verdict 哈希。",
        "- 覆盖只表示人工接受允许范围内的已知风险；原始阻断记录保留，缺失数据不会变成已验证证据。",
        "- 确定性审计与独立 verdict 是两层证据，彼此独立保存，不能互相冒充。",
        "- publishable 仅表示通过本系统约定的发布前检查，不代表论文达到期刊发表标准。",
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
