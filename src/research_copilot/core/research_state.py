"""研究状态机：发现 → 待研究问题（proposed）→ 人工确认（confirmed）→ 假设/实验。

升级规则（与 README 三原则一致）：
- observation / statistical_finding 且三层校验通过 → 可进入 established_results；
- hypothesis / causal_claim / unverified_conjecture → 只能进入 current_claims（待验证）或
  insufficient_claims（证据不足），不得写成已证实结果。
"""
from __future__ import annotations

from typing import Any

from .models import (
    CLAIM_TYPES,
    UPGRADABLE_CLAIM_TYPES,
    Finding,
    OpenQuestion,
    ResearchState,
)
from .storage import now_iso


def _question_from_finding(finding: Finding) -> OpenQuestion | None:
    if not finding.verification_method:
        return None
    statement = f"{finding.statement} —— {finding.verification_method}"
    return OpenQuestion(
        id="",
        statement=statement,
        status="proposed",
        proposed_by="diagnosis",
        finding_ids=[finding.id],
        status_rationale=f"来自发现 {finding.id}（claim_type={finding.claim_type}）的验证方法",
    )


def propose_questions_from_findings(state: ResearchState, findings: list[Finding]) -> list[OpenQuestion]:
    """把带验证方法的发现转成 proposed 待研究问题（不覆盖已存在问题）。"""
    existing = {q.statement for q in state.open_questions}
    added = []
    for finding in findings:
        question = _question_from_finding(finding)
        if question is None or question.statement in existing:
            continue
        question.id = f"Q-{len(state.open_questions) + len(added) + 1:03d}"
        question.created_at = now_iso()
        question.updated_at = question.created_at
        state.open_questions.append(question)
        added.append(question)
    return added


def confirm_question(state: ResearchState, question_id: str, rationale: str = "", actor: str = "human") -> OpenQuestion:
    for question in state.open_questions:
        if question.id == question_id:
            question.status = "confirmed"
            question.status_rationale = rationale or question.status_rationale
            question.human_override = actor == "human"
            question.updated_at = now_iso()
            return question
    raise KeyError(f"待研究问题不存在: {question_id}")


def set_question_status(state: ResearchState, question_id: str, status: str, rationale: str = "", actor: str = "human") -> OpenQuestion:
    if status not in ("proposed", "confirmed", "resolved", "retired"):
        raise ValueError(f"非法问题状态: {status}")
    for question in state.open_questions:
        if question.id == question_id:
            question.status = status
            question.status_rationale = rationale or question.status_rationale
            question.human_override = actor == "human"
            question.updated_at = now_iso()
            return question
    raise KeyError(f"待研究问题不存在: {question_id}")


def _claim_entry(finding: Finding) -> dict[str, Any]:
    refs = finding.validation.get("resolved_refs") or []
    evidence = []
    for ref in refs:
        if isinstance(ref, dict):
            evidence.append(
                {
                    "material_id": ref.get("material_id", ""),
                    "sha256": ref.get("sha256", ""),
                    "locator": ref.get("locator", ""),
                    "data_range": ref.get("data_range", ""),
                }
            )
        else:
            evidence.append(
                {
                    "material_id": ref.material_id,
                    "sha256": ref.sha256,
                    "locator": ref.locator,
                    "data_range": ref.data_range,
                }
            )
    return {
        "statement": finding.validation.get("verified_statement", finding.statement) if finding.validation.get("status") == "verified" else finding.statement,
        "claim_type": finding.claim_type,
        "finding_id": finding.id,
        "confidence": finding.confidence,
        "evidence_refs": evidence or finding.observation_ids,
        "validation_status": finding.validation.get("status", ""),
    }


def sync_claims_from_findings(state: ResearchState, findings: list[Finding]) -> dict[str, int]:
    """按最终主张级别把发现归入三个主张桶。返回计数。"""
    state.established_results = [
        entry for entry in state.established_results if entry.get("finding_id") not in {f.id for f in findings}
    ]
    state.current_claims = [
        entry for entry in state.current_claims if entry.get("finding_id") not in {f.id for f in findings}
    ]
    state.insufficient_claims = [
        entry for entry in state.insufficient_claims if entry.get("finding_id") not in {f.id for f in findings}
    ]
    counts = {"established": 0, "current": 0, "insufficient": 0}
    for finding in findings:
        if finding.claim_type in UPGRADABLE_CLAIM_TYPES and finding.validation.get("status") == "verified":
            state.established_results.append(_claim_entry(finding))
            counts["established"] += 1
        elif finding.claim_type in ("hypothesis", "causal_claim"):
            state.current_claims.append(_claim_entry(finding))
            counts["current"] += 1
        else:
            state.insufficient_claims.append(_claim_entry(finding))
            counts["insufficient"] += 1
    return counts


def render_markdown(state: ResearchState, project_name: str = "") -> str:
    lines = [f"# 研究状态报告{'：' + project_name if project_name else ''}", ""]
    lines += [f"- 当前阶段：{state.current_stage or '未设置'}", f"- 下一步目标：{state.next_objective or '未设置'}", ""]

    def _section(title: str, entries: list[dict[str, Any]], note: str) -> list[str]:
        out = [f"## {title}", ""]
        if not entries:
            out += [f"_{note}_", ""]
            return out
        for entry in entries:
            refs = ", ".join(str(r) for r in entry.get("evidence_refs") or []) or "无引用"
            out.append(
                f"- [{entry.get('claim_type', '?')}] {entry.get('statement', '')}"
                f"（发现 {entry.get('finding_id', '?')}；证据: {refs}；校验: {entry.get('validation_status') or '-'}）"
            )
        out.append("")
        return out

    lines += _section("已证实结果（可引用）", state.established_results, "暂无：尚无通过三层校验的 Observation / Statistical Finding。")
    lines += _section("当前科学主张（待验证假设/因果解释）", state.current_claims, "暂无。")
    lines += _section("证据不足的主张（不得进入论文或结论）", state.insufficient_claims, "暂无。")

    lines += ["## 待研究问题", ""]
    if not state.open_questions:
        lines += ["_暂无。_", ""]
    for question in state.open_questions:
        lines.append(
            f"- {question.id} [{question.status}] {question.statement}"
            f"（提出方: {question.proposed_by}{'；人工确认' if question.human_override else ''}）"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "propose_questions_from_findings",
    "confirm_question",
    "set_question_status",
    "sync_claims_from_findings",
    "render_markdown",
    "CLAIM_TYPES",
]
