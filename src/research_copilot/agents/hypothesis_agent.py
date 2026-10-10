"""假设 Agent / 竞争假设管理。

规则：
- 同一问题的假设互为竞争假设（competing_with 自动互链）；
- 迁移到 supported / refuted 必须附 evidence_links（台账 EV-xxx）与 rationale，
  否则拒绝——防止"无证据改结论"；
- 人工覆盖永远可用并留痕（human_override=True）。
"""
from __future__ import annotations

import json
from typing import Any

from ..core.models import EvidenceEntry, Hypothesis
from ..core.storage import ProjectStore, now_iso

HYPOTHESIS_SYSTEM_PROMPT = """你是科研假设助手。针对给定研究问题，生成 2-4 个互为竞争的科学假设。
规则：
1. 假设必须是对现象的可能解释，彼此可区分（不同假设在不同实验下应产生不同结果）；
2. 每个假设必须给出可证伪条件（falsification_criteria）：什么观测结果出现时该假设被否定；
3. 只能基于给定的发现与观测，不得引入材料之外的机制断言；
4. 只输出 JSON：{"hypotheses": [{"statement": "...", "falsification_criteria": "..."}]}"""


class HypothesisManager:
    def __init__(self, store: ProjectStore, project_id: str) -> None:
        self.store = store
        self.project_id = project_id

    # ---------- 生成 ----------
    def generate(self, llm: Any | None = None, question_ids: list[str] | None = None) -> dict[str, Any]:
        from ..core.research_state import confirm_question  # noqa: F401  (确保模块可用)

        state = self.store.load_state(self.project_id)
        findings = {f.id: f for f in self.store.load_findings(self.project_id)}
        questions = state.open_questions
        if question_ids:
            questions = [q for q in questions if q.id in set(question_ids)]
        targets = [q for q in questions if q.status == "confirmed"]
        if not targets:
            return {
                "generated": [],
                "note": "没有 confirmed 状态的待研究问题：请先人工确认问题（research-copilot question confirm），"
                "diagnosis 提出的问题默认 proposed、不会自动驱动假设。",
            }

        hypotheses = self.store.load_hypotheses(self.project_id)
        mode = "offline"
        llm_error = ""
        generated: list[Hypothesis] = []
        for question in targets:
            if llm is not None:
                try:
                    drafts = self._llm_drafts(llm, question, findings)
                    mode = "llm"
                except Exception as exc:  # LLMUnavailable or parse error
                    llm_error = str(exc)
                    drafts = self._offline_drafts(question, findings)
            else:
                drafts = self._offline_drafts(question, findings)
            existing_ids = [h.id for h in hypotheses]
            start_number = max([int(h.id.split("-")[1]) for h in hypotheses if "-" in h.id] or [0])
            for offset, draft in enumerate(drafts, start=1):
                hypothesis = Hypothesis(
                    id=f"H-{start_number + offset:03d}",
                    question_id=question.id,
                    statement=draft["statement"],
                    falsification_criteria=draft.get("falsification_criteria", ""),
                    status="candidate",
                    origin="llm" if mode == "llm" else "offline_rules",
                    created_at=now_iso(),
                    updated_at=now_iso(),
                )
                generated.append(hypothesis)
                hypotheses.append(hypothesis)
        # 竞争假设互链
        by_question: dict[str, list[Hypothesis]] = {}
        for hypothesis in hypotheses:
            by_question.setdefault(hypothesis.question_id, []).append(hypothesis)
        for group in by_question.values():
            ids = [h.id for h in group]
            for hypothesis in group:
                hypothesis.competing_with = [i for i in ids if i != hypothesis.id]
        self.store.save_hypotheses(self.project_id, hypotheses)
        if generated:
            self.store.log_event(
                self.project_id, "hypotheses_generated", detail=f"mode={mode}; n={len(generated)}"
            )
        return {
            "generated": [h.to_dict() for h in generated],
            "mode": mode,
            "llm_error": llm_error,
            "note": "" if generated else "离线模式下无含竞争性解释的发现可用；请配置 LLM 或人工添加假设。",
        }

    def _offline_drafts(self, question, findings: dict[str, Any]) -> list[dict[str, str]]:
        drafts: list[dict[str, str]] = []
        for finding_id in question.finding_ids:
            finding = findings.get(finding_id)
            if finding is None:
                continue
            for explanation in finding.alternative_explanations:
                drafts.append(
                    {
                        "statement": explanation,
                        "falsification_criteria": finding.verification_method
                        or "未定义：请人工补充可证伪条件",
                    }
                )
        return drafts

    def _llm_drafts(self, llm: Any, question, findings: dict[str, Any]) -> list[dict[str, str]]:
        context = {
            "question": {"id": question.id, "statement": question.statement},
            "related_findings": [
                findings[fid].to_dict() for fid in question.finding_ids if fid in findings
            ],
        }
        response = llm.complete(
            HYPOTHESIS_SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False, indent=2), purpose="hypothesis"
        )
        from .diagnosis_agent import _parse_json_block

        parsed = _parse_json_block(response)
        drafts = (parsed or {}).get("hypotheses") if isinstance(parsed, dict) else None
        if not drafts:
            raise ValueError("LLM 假设输出无法解析")
        return [
            {"statement": str(d["statement"]), "falsification_criteria": str(d.get("falsification_criteria") or "")}
            for d in drafts
            if isinstance(d, dict) and d.get("statement")
        ]

    def add_manual(self, question_id: str, statement: str, falsification_criteria: str = "") -> Hypothesis:
        hypotheses = self.store.load_hypotheses(self.project_id)
        number = max([int(h.id.split("-")[1]) for h in hypotheses if "-" in h.id] or [0]) + 1
        hypothesis = Hypothesis(
            id=f"H-{number:03d}",
            question_id=question_id,
            statement=statement,
            falsification_criteria=falsification_criteria,
            status="candidate",
            origin="human",
            human_override=True,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        hypotheses.append(hypothesis)
        by_question: dict[str, list[Hypothesis]] = {}
        for item in hypotheses:
            by_question.setdefault(item.question_id, []).append(item)
        for group in by_question.values():
            ids = [h.id for h in group]
            for item in group:
                item.competing_with = [i for i in ids if i != item.id]
        self.store.save_hypotheses(self.project_id, hypotheses)
        self.store.log_event(self.project_id, "hypothesis_added", target=hypothesis.id, actor="human")
        return hypothesis

    # ---------- 状态迁移 ----------
    TRANSITIONS_REQUIRING_EVIDENCE = ("supported", "refuted")

    def set_status(
        self,
        hypothesis_id: str,
        new_status: str,
        rationale: str = "",
        evidence_links: list[str] | None = None,
        actor: str = "human",
    ) -> Hypothesis:
        if new_status not in ("candidate", "active", "supported", "refuted", "uncertain", "retired"):
            raise ValueError(f"非法假设状态: {new_status}")
        hypotheses = self.store.load_hypotheses(self.project_id)
        target = next((h for h in hypotheses if h.id == hypothesis_id), None)
        if target is None:
            raise KeyError(f"假设不存在: {hypothesis_id}")
        if new_status in self.TRANSITIONS_REQUIRING_EVIDENCE:
            links = evidence_links or target.evidence_links
            if not links:
                raise ValueError(
                    f"{hypothesis_id} → {new_status} 需要至少一条证据台账引用（EV-xxx）；"
                    "请先调用 record-evidence，再迁移状态。"
                )
            if not rationale:
                raise ValueError("状态迁移必须附 rationale")
            target.evidence_links = links
        target.status = new_status
        target.status_rationale = rationale or target.status_rationale
        target.human_override = actor == "human" or target.human_override
        target.updated_at = now_iso()
        self.store.save_hypotheses(self.project_id, hypotheses)
        self.store.log_event(
            self.project_id, "hypothesis_status", target=hypothesis_id, detail=f"→ {new_status}: {rationale[:120]}", actor=actor
        )
        return target

    # ---------- 证据台账 ----------
    def record_evidence(
        self,
        hypothesis_id: str,
        verdict: str,
        rationale: str,
        ref_id: str = "",
        kind: str = "observation",
        summary: str = "",
        sha256: str = "",
        actor: str = "system",
    ) -> EvidenceEntry:
        if verdict not in ("supports", "contradicts", "inconclusive"):
            raise ValueError(f"非法证据判定: {verdict}")
        entry = EvidenceEntry(
            id="",
            ts=now_iso(),
            kind=kind,
            ref_id=ref_id,
            summary=summary or rationale[:200],
            sha256=sha256,
            verdicts={hypothesis_id: verdict},
            rationale=rationale,
            actor=actor,
        )
        entry = self.store.append_evidence(self.project_id, entry)
        # 同步进假设 evidence_links（不自动改状态）
        hypotheses = self.store.load_hypotheses(self.project_id)
        for hypothesis in hypotheses:
            if hypothesis.id == hypothesis_id and entry.id not in hypothesis.evidence_links:
                hypothesis.evidence_links.append(entry.id)
                hypothesis.updated_at = now_iso()
        self.store.save_hypotheses(self.project_id, hypotheses)
        return entry
