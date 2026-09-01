from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import PaperReview


PAPER_REVIEW_CALIBRATION_JSON = "07-paper-review-calibration.json"
PAPER_REVIEW_CALIBRATION_MD = "07-paper-review-calibration.md"


def write_paper_review_calibration_artifacts(
    topic: str,
    paper_review: PaperReview,
    run_dir: Path,
    experiment_decision: dict[str, Any] | None = None,
    hypothesis_outcome: dict[str, Any] | None = None,
    execution_mode: str = "",
) -> dict[str, Any]:
    report = build_paper_review_calibration_report(topic, paper_review, experiment_decision, hypothesis_outcome, execution_mode)
    write_json(run_dir / PAPER_REVIEW_CALIBRATION_JSON, report)
    write_text(run_dir / PAPER_REVIEW_CALIBRATION_MD, render_paper_review_calibration_markdown(report))
    return report


def build_paper_review_calibration_report(
    topic: str,
    paper_review: PaperReview,
    experiment_decision: dict[str, Any] | None = None,
    hypothesis_outcome: dict[str, Any] | None = None,
    execution_mode: str = "",
) -> dict[str, Any]:
    unsupported = sum(1 for item in paper_review.claim_audit if item.support_level == "unsupported")
    weak = sum(1 for item in paper_review.claim_audit if item.support_level == "weak")
    high_risk = sum(1 for item in paper_review.claim_audit if item.risk == "high")
    decision = str(paper_review.decision or "").strip()
    score = float(paper_review.score)
    flags: list[dict[str, Any]] = []
    max_score = 10.0
    max_score = _apply_claim_rules(flags, max_score, unsupported, weak, high_risk)
    max_score = _apply_experiment_rules(flags, max_score, experiment_decision or {}, hypothesis_outcome or {}, execution_mode)
    max_score = round(max_score, 1)
    over_score = score > max_score
    if over_score:
        flags.append(
            {
                "name": "review_score_too_lenient",
                "severity": "block" if max_score < 6.5 else "warn",
                "evidence": f"review_score={score:.1f} exceeds max_recommended_score={max_score:.1f}",
                "action": "下调复核分数/决定，或先补齐证据、实验和 claim 边界后再接受当前分数。",
            }
        )
    if _decision_too_lenient(decision, max_score):
        flags.append(
            {
                "name": "review_decision_too_lenient",
                "severity": "block" if max_score < 6.5 else "warn",
                "evidence": f"decision={decision or '-'} is too permissive for max_recommended_score={max_score:.1f}",
                "action": "把复核决定降级为 revise/major_revision/reject，并把问题写入修订计划。",
            }
        )
    blockers = [item for item in flags if item.get("severity") == "block"]
    warnings = [item for item in flags if item.get("severity") == "warn"]
    status = "block" if blockers else "review_required" if warnings else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "review_decision": decision,
        "review_score": score,
        "max_recommended_score": max_score,
        "calibrated_decision": _calibrated_decision(max_score, blockers, warnings),
        "unsupported_claims": unsupported,
        "weak_claims": weak,
        "high_risk_claims": high_risk,
        "execution_mode": execution_mode,
        "experiment_decision": str((experiment_decision or {}).get("decision") or ""),
        "hypothesis_outcome": str((hypothesis_outcome or {}).get("outcome") or ""),
        "flags": flags,
        "blocking_issues": [str(item.get("evidence") or item.get("name") or "") for item in blockers],
        "manual_tasks": [str(item.get("evidence") or item.get("name") or "") for item in warnings],
        "required_actions": _required_actions(flags),
    }


def render_paper_review_calibration_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Paper Review Calibration：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 原始决定/分数：{report.get('review_decision') or '-'} / {float(report.get('review_score') or 0):.1f}",
        f"- 建议最高分：{float(report.get('max_recommended_score') or 0):.1f}",
        f"- 校准后建议决定：{report.get('calibrated_decision') or '-'}",
        f"- Unsupported/weak/high-risk claims：{report.get('unsupported_claims', 0)}/{report.get('weak_claims', 0)}/{report.get('high_risk_claims', 0)}",
        f"- 实验决策/假设结果：{report.get('experiment_decision') or '-'} / {report.get('hypothesis_outcome') or '-'}",
        "",
    ]
    flags = report.get("flags") if isinstance(report.get("flags"), list) else []
    if flags:
        lines.extend(["## 校准标记", "| 名称 | 严重性 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
        for item in flags:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("name") or "")),
                        _cell(str(item.get("severity") or "")),
                        _cell(str(item.get("evidence") or "")),
                        _cell(str(item.get("action") or "")),
                    ]
                )
                + " |"
            )
    else:
        lines.extend(["## 校准标记", "- 未发现明显过宽自评。"])
    actions = report.get("required_actions") if isinstance(report.get("required_actions"), list) else []
    lines.extend(["", "## 必要动作"])
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 无")
    return "\n".join(lines)


def _apply_claim_rules(flags: list[dict[str, Any]], max_score: float, unsupported: int, weak: int, high_risk: int) -> float:
    if unsupported:
        max_score = min(max_score, 5.9)
        flags.append(
            {
                "name": "unsupported_claims_present",
                "severity": "block",
                "evidence": f"unsupported_claims={unsupported}",
                "action": "删除、降级或补证所有 unsupported claim 后再提高复核分数。",
            }
        )
    if high_risk:
        max_score = min(max_score, 6.4)
        flags.append(
            {
                "name": "high_risk_claims_present",
                "severity": "block" if high_risk > 1 else "warn",
                "evidence": f"high_risk_claims={high_risk}",
                "action": "逐条处理高风险 claim 的证据和结果边界。",
            }
        )
    if weak:
        max_score = min(max_score, 7.4)
        flags.append(
            {
                "name": "weak_claims_present",
                "severity": "warn",
                "evidence": f"weak_claims={weak}",
                "action": "收窄 weak claim，补充直接 citation key 或结果指标。",
            }
        )
    return max_score


def _apply_experiment_rules(
    flags: list[dict[str, Any]],
    max_score: float,
    experiment_decision: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    execution_mode: str,
) -> float:
    decision = str(experiment_decision.get("decision") or "").strip()
    if decision in {"repair_before_writing", "pivot_or_refine", "refine_experiment", "benchmark_upgrade"}:
        cap = 5.8 if decision == "repair_before_writing" else 6.8
        max_score = min(max_score, cap)
        flags.append(
            {
                "name": "experiment_decision_not_ready",
                "severity": "block" if decision == "repair_before_writing" else "warn",
                "evidence": f"experiment_decision={decision}",
                "action": "按 04-experiment-decision.md 先修复或降级实验结论。",
            }
        )
    outcome = str(hypothesis_outcome.get("outcome") or "").strip()
    if outcome in {"blocked_unverified", "untested", "refuted_or_negative", "inconclusive", "smoke_only"}:
        cap = 5.5 if outcome in {"blocked_unverified", "untested"} else 6.8
        max_score = min(max_score, cap)
        flags.append(
            {
                "name": "hypothesis_outcome_limits_review",
                "severity": "block" if outcome in {"blocked_unverified", "untested"} else "warn",
                "evidence": f"hypothesis_outcome={outcome}",
                "action": "让论文结论与 04-hypothesis-outcome.md 的结果边界一致。",
            }
        )
    if execution_mode == "simulated":
        max_score = min(max_score, 7.0)
        flags.append(
            {
                "name": "simulated_evidence_limit",
                "severity": "warn",
                "evidence": "execution_mode=simulated",
                "action": "明确结果只是 smoke test；正式主结论需 local 或 benchmark 证据。",
            }
        )
    return max_score


def _decision_too_lenient(decision: str, max_score: float) -> bool:
    lowered = decision.lower()
    if max_score < 6.0:
        return any(term in lowered for term in ["accept", "minor", "revise"])
    if max_score < 7.0:
        return any(term in lowered for term in ["accept", "minor"])
    return "accept" in lowered and "minor" not in lowered


def _calibrated_decision(max_score: float, blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
    if blockers and max_score < 6.0:
        return "major_revision_or_reject"
    if blockers:
        return "major_revision"
    if warnings:
        return "revise"
    return "unchanged"


def _required_actions(flags: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for item in flags:
        action = str(item.get("action") or "").strip()
        if action and action not in actions:
            actions.append(action)
    return actions


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
