"""主动实验规划（P1-B）：把竞争假设转化为实验候选，六维透明评分排序。

评分命名（如实声明）：本模块的分数是 **Experiment Readiness Score（实验准备度）**——
它衡量"方案形式是否完备、可执行、可复算"，不衡量"该实验能带来多少信息"。
- 它能证明方案写对了，不能证明 Agent 知道哪个实验最有科学价值；
- 判断"不同假设对实验结果的预测是否真的不同"需要独立的 **Discrimination Score**
  （对每个竞争假设分别预测实验结果分布，度量预测差异），属后续工作（docs/roadmap.md）；
- 两者都不是信息论信息增益——后者需要对假设与实验结果建立概率模型。

权重：hypothesis_discrimination=0.25, gap_relevance=0.20, measurability=0.15,
control_completeness=0.15, cost_efficiency=0.15, reproducibility=0.10。

P1 不执行任何实验：候选止步于 proposed / approved（人工批准标记）。
"""
from __future__ import annotations

import json
from typing import Any

from ..core.models import ExperimentCandidate, ScoreDimension
from ..core.storage import ProjectStore, now_iso

READINESS_SCORE_NAME = "experiment_readiness"  # 实验准备度评分（非信息增益，非区分度）

PLANNER_SYSTEM_PROMPT = """你是主动实验规划助手。针对给定的研究问题与竞争假设，设计能够区分这些假设的实验方案。
规则：
1. 实验的价值在于能否区分竞争性解释，而不在于可能带来多大性能提升；
2. 必须给出：设计（含控制变量）、主要指标（每个指标声明 direction: lower_is_better 或 higher_is_better）、
   预期结果、可证伪条件（什么结果出现时假设被否定）、成本估计（low/medium/high）；
3. 只能基于给定的假设与观测，不得引入材料之外的机制断言；
4. 只输出 JSON：{"experiments": [...]}，每个元素形如：
   {"research_question": "...", "scientific_hypothesis": "...", "competing_explanations": [...],
    "hypothesis_ids": ["H-001"], "design": "...", "controls": [...],
    "metrics": [{"name": "...", "direction": "lower_is_better"}],
    "expected_outcome": "...", "falsification_condition": "...", "cost_estimate": "low|medium|high"}"""

SCORE_WEIGHTS = {
    "hypothesis_discrimination": 0.25,
    "measurability": 0.15,
    "control_completeness": 0.15,
    "gap_relevance": 0.20,
    "cost_efficiency": 0.15,
    "reproducibility": 0.10,
}


def form_check(candidate: ExperimentCandidate) -> dict[str, Any]:
    """四项形式检查：可证伪条件 / 控制变量 / 主要指标（带方向）/ 竞争性解释。缺一不可。"""
    checks = {
        "falsification_condition": bool(candidate.falsification_condition.strip()),
        "controls": len(candidate.controls) > 0,
        "metrics_with_direction": bool(candidate.metrics)
        and all(m.get("direction") in ("lower_is_better", "higher_is_better") for m in candidate.metrics),
        "competing_explanations": len(candidate.competing_explanations) > 0,
    }
    checks["form_complete"] = all(checks.values())
    return checks


def score_candidate(candidate: ExperimentCandidate, question_status: str) -> list[ScoreDimension]:
    """六维启发式评分，每维 0-5 分并给出依据。"""
    scores: list[ScoreDimension] = []

    n_hypotheses = len(candidate.hypothesis_ids) or len(candidate.competing_explanations)
    if candidate.falsification_condition and n_hypotheses >= 2:
        discrimination, why = 5, f"可证伪条件明确，且能区分 {n_hypotheses} 个竞争解释"
    elif candidate.falsification_condition:
        discrimination, why = 3, "可证伪条件明确，但未显式区分多个竞争解释"
    else:
        discrimination, why = 0, "缺少可证伪条件：无法区分假设"
    scores.append(ScoreDimension("hypothesis_discrimination", discrimination, why))

    with_direction = [m for m in candidate.metrics if m.get("direction") in ("lower_is_better", "higher_is_better")]
    without_direction = len(candidate.metrics) - len(with_direction)
    if not candidate.metrics:
        measurability, why = 0, "未定义主要指标"
    elif not with_direction:
        measurability, why = 1, f"{len(candidate.metrics)} 个指标均未声明方向"
    elif without_direction:
        measurability, why = 3, f"{len(with_direction)} 个指标已声明方向，{without_direction} 个未声明"
    else:
        measurability, why = 5, f"全部 {len(with_direction)} 个指标均声明了方向"
    scores.append(ScoreDimension("measurability", measurability, why))

    n_controls = len(candidate.controls)
    control_scores = {0: 0, 1: 3, 2: 4}
    control_score = control_scores.get(n_controls, 5)
    scores.append(
        ScoreDimension(
            "control_completeness",
            control_score,
            f"{n_controls} 个控制变量" + ("：覆盖充分" if n_controls >= 3 else "：需检查是否遗漏主要混杂因素" if n_controls else "：未列出控制变量"),
        )
    )

    gap_scores = {"confirmed": 5, "proposed": 2, "resolved": 0, "retired": 0}
    gap_score = gap_scores.get(question_status, 0)
    scores.append(
        ScoreDimension(
            "gap_relevance",
            gap_score,
            f"目标问题状态为 {question_status}"
            + ("（人工已确认的证据缺口）" if question_status == "confirmed" else "（尚未人工确认，信息缺口可能不真实）" if question_status == "proposed" else ""),
        )
    )

    cost_scores = {"low": 5, "medium": 3, "high": 1}
    cost = candidate.cost_estimate if candidate.cost_estimate in cost_scores else "medium"
    scores.append(
        ScoreDimension(
            "cost_efficiency",
            cost_scores[cost],
            f"预估执行成本 {cost}（越低成本分越高；依据历史执行记录估算更佳）",
        )
    )

    text = " ".join([candidate.design, " ".join(candidate.controls)]).lower()
    if any(token in text for token in ("seed", "种子", "固定", "random_state", "受控")):
        repro, why = 5, "设计中明确固定了随机种子/环境等可复现条件"
    elif text:
        repro, why = 2, "未明确说明可复现条件（种子/环境/版本）"
    else:
        repro, why = 0, "无设计方案"
    scores.append(ScoreDimension("reproducibility", repro, why))

    return scores


def priority_score(scores: list[ScoreDimension]) -> float:
    return round(sum(SCORE_WEIGHTS[s.name] * s.score for s in scores), 3)


class ExperimentPlanner:
    def __init__(self, store: ProjectStore, project_id: str) -> None:
        self.store = store
        self.project_id = project_id

    def plan(self, llm: Any | None = None, question_ids: list[str] | None = None, max_per_question: int = 2) -> dict[str, Any]:
        state = self.store.load_state(self.project_id)
        questions = state.open_questions
        if question_ids:
            questions = [q for q in questions if q.id in set(question_ids)]
        targets = [q for q in questions if q.status == "confirmed"]
        if not targets:
            return {
                "created": [],
                "note": "没有 confirmed 状态的待研究问题：实验规划只针对人工确认过的证据缺口。",
            }
        hypotheses = self.store.load_hypotheses(self.project_id)
        by_question: dict[str, list] = {}
        for hypothesis in hypotheses:
            by_question.setdefault(hypothesis.question_id, []).append(hypothesis)

        candidates = self.store.load_candidates(self.project_id)
        mode = "offline"
        llm_error = ""
        created: list[ExperimentCandidate] = []
        for question in targets:
            question_hypotheses = by_question.get(question.id, [])
            if llm is not None:
                try:
                    drafts = self._llm_drafts(llm, question, question_hypotheses)
                    mode = "llm"
                except Exception as exc:
                    llm_error = str(exc)
                    drafts = self._offline_drafts(question, question_hypotheses)
            else:
                drafts = self._offline_drafts(question, question_hypotheses)
            for draft in drafts[:max_per_question]:
                number = max([int(c.id.split("-")[1]) for c in candidates if "-" in c.id] or [0]) + 1
                candidate = ExperimentCandidate(
                    id=f"EXP-{number:03d}",
                    question_id=question.id,
                    hypothesis_ids=list(draft.get("hypothesis_ids") or [h.id for h in question_hypotheses]),
                    research_question=str(draft.get("research_question") or question.statement),
                    scientific_hypothesis=str(draft.get("scientific_hypothesis") or ""),
                    competing_explanations=[str(x) for x in draft.get("competing_explanations") or []],
                    design=str(draft.get("design") or ""),
                    controls=[str(x) for x in draft.get("controls") or []],
                    metrics=[dict(m) for m in draft.get("metrics") or [] if isinstance(m, dict)],
                    expected_outcome=str(draft.get("expected_outcome") or ""),
                    falsification_condition=str(draft.get("falsification_condition") or ""),
                    cost_estimate=str(draft.get("cost_estimate") or "medium"),
                    origin="llm" if mode == "llm" else "offline_draft",
                )
                candidate.form_check = form_check(candidate)
                candidate.scores = score_candidate(candidate, question.status)
                candidate.priority_score = priority_score(candidate.scores)
                candidate.status = "proposed" if candidate.form_check["form_complete"] else "needs_revision"
                candidate.created_at = now_iso()
                candidate.updated_at = now_iso()
                candidates.append(candidate)
                created.append(candidate)
        self.store.save_candidates(self.project_id, candidates)
        if created:
            self.store.log_event(self.project_id, "experiments_planned", detail=f"mode={mode}; n={len(created)}")
        return {
            "created": [c.to_dict() for c in created],
            "mode": mode,
            "llm_error": llm_error,
            "scoring_note": (
                "优先级 = Experiment Readiness Score（实验准备度）：六维启发式加权评分，"
                "每维依据落盘可复算；它衡量方案形式完备性，不衡量科学信息价值——"
                "假设区分能力需要未来独立的 Discrimination Score，两者都不是信息论信息增益。"
                "权重：hypothesis_discrimination=0.25, gap_relevance=0.20, "
                "measurability=0.15, control_completeness=0.15, cost_efficiency=0.15, reproducibility=0.10"
            ),
            "note": "" if created else "离线草稿需要人工补齐后才能进入 proposed。",
        }

    def _offline_drafts(self, question, question_hypotheses: list) -> list[dict[str, Any]]:
        """离线：从假设的可证伪条件生成草稿。指标与控制变量无法凭空可靠给出，
        生成的草稿 form_check 不过 → needs_revision，由人工补齐（诚实降级）。"""
        drafts: list[dict[str, Any]] = []
        for hypothesis in question_hypotheses:
            drafts.append(
                {
                    "research_question": question.statement,
                    "scientific_hypothesis": hypothesis.statement,
                    "competing_explanations": [
                        h.statement for h in question_hypotheses if h.id != hypothesis.id
                    ],
                    "hypothesis_ids": [hypothesis.id],
                    "design": hypothesis.falsification_criteria
                    or "待补：需要人工设计受控对照实验",
                    "controls": [],
                    "metrics": [],
                    "expected_outcome": "",
                    "falsification_condition": hypothesis.falsification_criteria,
                    "cost_estimate": "medium",
                }
            )
        return drafts

    def _llm_drafts(self, llm: Any, question, question_hypotheses: list) -> list[dict[str, Any]]:
        context = {
            "question": {"id": question.id, "statement": question.statement},
            "hypotheses": [h.to_dict() for h in question_hypotheses],
        }
        response = llm.complete(
            PLANNER_SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False, indent=2), purpose="planner"
        )
        from .diagnosis_agent import _parse_json_block

        parsed = _parse_json_block(response)
        drafts = (parsed or {}).get("experiments") if isinstance(parsed, dict) else None
        if not drafts:
            raise ValueError("LLM 实验规划输出无法解析")
        return [d for d in drafts if isinstance(d, dict)]

    def set_status(self, candidate_id: str, new_status: str, actor: str = "human") -> ExperimentCandidate:
        if new_status not in ("needs_revision", "proposed", "approved", "rejected"):
            raise ValueError(f"非法候选状态: {new_status}")
        candidates = self.store.load_candidates(self.project_id)
        target = next((c for c in candidates if c.id == candidate_id), None)
        if target is None:
            raise KeyError(f"实验候选不存在: {candidate_id}")
        if new_status == "approved":
            if not target.form_check.get("form_complete"):
                raise ValueError(f"{candidate_id} 形式检查未通过（缺可证伪条件/控制变量/指标方向/竞争解释），不能批准")
            if target.status != "proposed":
                raise ValueError(f"{candidate_id} 当前状态 {target.status}，仅 proposed 可批准")
            if actor != "human":
                raise ValueError("实验批准必须由人工执行（P1 不自动执行任何实验）")
        target.status = new_status
        target.updated_at = now_iso()
        self.store.save_candidates(self.project_id, candidates)
        self.store.log_event(self.project_id, "candidate_status", target=candidate_id, detail=f"→ {new_status}", actor=actor)
        return target
