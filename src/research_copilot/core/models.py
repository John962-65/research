"""Research Copilot 核心数据模型。

约定：
- 所有持久化对象带 ``schema_version``，字段只增不改名；反序列化忽略未知字段。
- 每条科学主张（Finding）必须携带证据引用（EvidenceRef），并经三层校验。
- 主张五级分类：observation / statistical_finding / hypothesis / causal_claim /
  unverified_conjecture。只有前两级可升级为已证实结果。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION = "rc/1.0"

CLAIM_TYPES = (
    "observation",
    "statistical_finding",
    "hypothesis",
    "causal_claim",
    "unverified_conjecture",
)
# 可升级为已证实结果的主张级别（L3 通过后）
UPGRADABLE_CLAIM_TYPES = ("observation", "statistical_finding")

HYPOTHESIS_STATUSES = ("candidate", "active", "supported", "refuted", "uncertain", "retired")
QUESTION_STATUSES = ("proposed", "confirmed", "resolved", "retired")
CANDIDATE_STATUSES = ("needs_revision", "proposed", "approved", "rejected")
DECISION_ACTIONS = ("continue", "refine", "investigate", "replicate", "pivot", "stop", "report")

MATERIAL_KINDS = ("results", "dataset", "code_repo", "paper_draft", "config", "review", "note", "legacy_run")


def _new_list() -> list:
    return field(default_factory=list)


@dataclass
class EvidenceRef:
    """证据引用：不仅指向材料 ID，还固定内容哈希、数据范围与配置摘要。

    材料更新后 sha256 变化，引用自动失效（stale），防止"引用还在、内容已变"。
    """

    material_id: str
    sha256: str
    locator: str = ""  # 例 "rows 12-14" / "column latency_ms" / "file:paper.md#L30-40"
    data_range: str = ""  # 数据范围说明，例 "60 queries, repeats 0-2"
    config_digest: str = ""  # 实验配置摘要哈希（无则为空）
    analysis_code_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        return cls(
            material_id=str(data.get("material_id") or ""),
            sha256=str(data.get("sha256") or ""),
            locator=str(data.get("locator") or ""),
            data_range=str(data.get("data_range") or ""),
            config_digest=str(data.get("config_digest") or ""),
            analysis_code_version=str(data.get("analysis_code_version") or SCHEMA_VERSION),
        )


@dataclass
class Material:
    """导入的科研材料登记项。文件本体不复制，登记路径 + sha256 + 解析摘要。"""

    id: str  # MAT-001
    kind: str  # MATERIAL_KINDS
    path: str  # 绝对路径或相对项目数据目录
    sha256: str
    imported_at: str
    summary: str = ""
    meta: dict[str, Any] = field(default_factory=dict)  # 解析摘要：n_rows/columns/metric_directions 等

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Material":
        return cls(
            id=str(data.get("id") or ""),
            kind=str(data.get("kind") or "note"),
            path=str(data.get("path") or ""),
            sha256=str(data.get("sha256") or ""),
            imported_at=str(data.get("imported_at") or ""),
            summary=str(data.get("summary") or ""),
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class NumericAssertion:
    """LLM 发现中可程序复核的数值断言。L2 校验据此重算。"""

    metric: str
    value: float
    unit: str = ""  # 例 percent_improvement / seconds / ratio
    basis_observation: str = ""  # 依据的观测 ID（OBS-001）
    check: str = ""  # 期望的复核方式：percent_change_from_baseline / mean / median / percentile_p95 / direction

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NumericAssertion":
        try:
            value = float(data.get("value"))
        except (TypeError, ValueError):
            value = float("nan")
        return cls(
            metric=str(data.get("metric") or ""),
            value=value,
            unit=str(data.get("unit") or ""),
            basis_observation=str(data.get("basis_observation") or ""),
            check=str(data.get("check") or ""),
        )


@dataclass
class Observation:
    """确定性统计观测：由分析代码从材料计算得到，不经 LLM。"""

    id: str  # OBS-001
    statement: str
    value: dict[str, Any] = field(default_factory=dict)  # 结构化数值，供 L2 复核
    evidence_refs: list[EvidenceRef] = _new_list()
    computed_by: str = ""  # 生成函数名，例 statistics.tail_report
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "value": self.value,
            "evidence_refs": [r.to_dict() for r in self.evidence_refs],
            "computed_by": self.computed_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        return cls(
            id=str(data.get("id") or ""),
            statement=str(data.get("statement") or ""),
            value=dict(data.get("value") or {}),
            evidence_refs=[EvidenceRef.from_dict(r) for r in data.get("evidence_refs") or []],
            computed_by=str(data.get("computed_by") or ""),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass
class Finding:
    """科学发现（诊断输出）。带三层校验结果与最终主张级别。"""

    id: str  # F-001
    statement: str
    claim_type: str = "unverified_conjecture"  # 校验后的最终级别
    claim_type_hint: str = ""  # LLM 自称的级别（仅参考）
    observation_ids: list[str] = _new_list()
    numeric_assertions: list[NumericAssertion] = _new_list()
    alternative_explanations: list[str] = _new_list()
    verification_method: str = ""
    confidence: str = ""  # low / medium / high
    confidence_rationale: str = ""
    validation: dict[str, Any] = field(default_factory=dict)  # {l1, l2, l3, downgrades[], final_claim_type, status}
    origin: str = "diagnosis"  # diagnosis / llm / offline_rules / human
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "claim_type": self.claim_type,
            "claim_type_hint": self.claim_type_hint,
            "observation_ids": list(self.observation_ids),
            "numeric_assertions": [a.to_dict() for a in self.numeric_assertions],
            "alternative_explanations": list(self.alternative_explanations),
            "verification_method": self.verification_method,
            "confidence": self.confidence,
            "confidence_rationale": self.confidence_rationale,
            "validation": dict(self.validation),
            "origin": self.origin,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        return cls(
            id=str(data.get("id") or ""),
            statement=str(data.get("statement") or ""),
            claim_type=str(data.get("claim_type") or "unverified_conjecture"),
            claim_type_hint=str(data.get("claim_type_hint") or ""),
            observation_ids=[str(x) for x in data.get("observation_ids") or []],
            numeric_assertions=[NumericAssertion.from_dict(a) for a in data.get("numeric_assertions") or []],
            alternative_explanations=[str(x) for x in data.get("alternative_explanations") or []],
            verification_method=str(data.get("verification_method") or ""),
            confidence=str(data.get("confidence") or ""),
            confidence_rationale=str(data.get("confidence_rationale") or ""),
            validation=dict(data.get("validation") or {}),
            origin=str(data.get("origin") or "diagnosis"),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass
class OpenQuestion:
    """待研究问题。diagnosis 只能以 proposed 提出，人工确认后才驱动假设/实验。"""

    id: str  # Q-001
    statement: str
    status: str = "proposed"  # QUESTION_STATUSES
    proposed_by: str = "diagnosis"  # diagnosis / human
    finding_ids: list[str] = _new_list()
    evidence_refs: list[EvidenceRef] = _new_list()
    status_rationale: str = ""
    human_override: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "status": self.status,
            "proposed_by": self.proposed_by,
            "finding_ids": list(self.finding_ids),
            "evidence_refs": [r.to_dict() for r in self.evidence_refs],
            "status_rationale": self.status_rationale,
            "human_override": self.human_override,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpenQuestion":
        return cls(
            id=str(data.get("id") or ""),
            statement=str(data.get("statement") or ""),
            status=str(data.get("status") or "proposed"),
            proposed_by=str(data.get("proposed_by") or "diagnosis"),
            finding_ids=[str(x) for x in data.get("finding_ids") or []],
            evidence_refs=[EvidenceRef.from_dict(r) for r in data.get("evidence_refs") or []],
            status_rationale=str(data.get("status_rationale") or ""),
            human_override=bool(data.get("human_override") or False),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class Hypothesis:
    """竞争性科学假设。状态迁移必须附证据与理由；支持人工覆盖并留痕。"""

    id: str  # H-001
    question_id: str  # Q-001
    statement: str
    competing_with: list[str] = _new_list()  # 同问题的其他假设 ID
    falsification_criteria: str = ""
    status: str = "candidate"  # HYPOTHESIS_STATUSES
    evidence_links: list[str] = _new_list()  # EV-xxx 台账 ID
    status_rationale: str = ""
    human_override: bool = False
    origin: str = "hypothesis_agent"  # hypothesis_agent / human
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question_id": self.question_id,
            "statement": self.statement,
            "competing_with": list(self.competing_with),
            "falsification_criteria": self.falsification_criteria,
            "status": self.status,
            "evidence_links": list(self.evidence_links),
            "status_rationale": self.status_rationale,
            "human_override": self.human_override,
            "origin": self.origin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hypothesis":
        return cls(
            id=str(data.get("id") or ""),
            question_id=str(data.get("question_id") or ""),
            statement=str(data.get("statement") or ""),
            competing_with=[str(x) for x in data.get("competing_with") or []],
            falsification_criteria=str(data.get("falsification_criteria") or ""),
            status=str(data.get("status") or "candidate"),
            evidence_links=[str(x) for x in data.get("evidence_links") or []],
            status_rationale=str(data.get("status_rationale") or ""),
            human_override=bool(data.get("human_override") or False),
            origin=str(data.get("origin") or "hypothesis_agent"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class ScoreDimension:
    """六维评分中的单维：分数 + 依据（可复算）。"""

    name: str
    score: int  # 0-5
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreDimension":
        try:
            score = max(0, min(5, int(data.get("score"))))
        except (TypeError, ValueError):
            score = 0
        return cls(name=str(data.get("name") or ""), score=score, rationale=str(data.get("rationale") or ""))


@dataclass
class ExperimentCandidate:
    """实验候选。P1 止步于 proposed/approved 标记，不触发任何执行。"""

    id: str  # EXP-001
    question_id: str
    hypothesis_ids: list[str] = _new_list()
    research_question: str = ""
    scientific_hypothesis: str = ""
    competing_explanations: list[str] = _new_list()
    design: str = ""
    controls: list[str] = _new_list()
    metrics: list[dict[str, str]] = _new_list()  # [{"name": ..., "direction": lower_is_better|higher_is_better}]
    expected_outcome: str = ""
    falsification_condition: str = ""
    cost_estimate: str = "medium"  # low / medium / high
    scores: list[ScoreDimension] = _new_list()
    priority_score: float = 0.0
    form_check: dict[str, Any] = field(default_factory=dict)  # 四项形式检查结果
    status: str = "needs_revision"  # CANDIDATE_STATUSES
    origin: str = "planner"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question_id": self.question_id,
            "hypothesis_ids": list(self.hypothesis_ids),
            "research_question": self.research_question,
            "scientific_hypothesis": self.scientific_hypothesis,
            "competing_explanations": list(self.competing_explanations),
            "design": self.design,
            "controls": list(self.controls),
            "metrics": [dict(m) for m in self.metrics],
            "expected_outcome": self.expected_outcome,
            "falsification_condition": self.falsification_condition,
            "cost_estimate": self.cost_estimate,
            "scores": [s.to_dict() for s in self.scores],
            "priority_score": self.priority_score,
            "form_check": dict(self.form_check),
            "status": self.status,
            "origin": self.origin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentCandidate":
        return cls(
            id=str(data.get("id") or ""),
            question_id=str(data.get("question_id") or ""),
            hypothesis_ids=[str(x) for x in data.get("hypothesis_ids") or []],
            research_question=str(data.get("research_question") or ""),
            scientific_hypothesis=str(data.get("scientific_hypothesis") or ""),
            competing_explanations=[str(x) for x in data.get("competing_explanations") or []],
            design=str(data.get("design") or ""),
            controls=[str(x) for x in data.get("controls") or []],
            metrics=[dict(m) for m in data.get("metrics") or [] if isinstance(m, dict)],
            expected_outcome=str(data.get("expected_outcome") or ""),
            falsification_condition=str(data.get("falsification_condition") or ""),
            cost_estimate=str(data.get("cost_estimate") or "medium"),
            scores=[ScoreDimension.from_dict(s) for s in data.get("scores") or []],
            priority_score=float(data.get("priority_score") or 0.0),
            form_check=dict(data.get("form_check") or {}),
            status=str(data.get("status") or "needs_revision"),
            origin=str(data.get("origin") or "planner"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass
class EvidenceEntry:
    """证据台账条目（追加式）。记录材料/观测/外部证据，以及对各假设的判定。"""

    id: str  # EV-001
    ts: str
    kind: str  # material / observation / finding / literature / human_note
    ref_id: str = ""  # MAT/OBS/F/Q/EXP id
    summary: str = ""
    sha256: str = ""
    verdicts: dict[str, str] = field(default_factory=dict)  # {hypothesis_id: supports|contradicts|inconclusive}
    rationale: str = ""
    actor: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "kind": self.kind,
            "ref_id": self.ref_id,
            "summary": self.summary,
            "sha256": self.sha256,
            "verdicts": dict(self.verdicts),
            "rationale": self.rationale,
            "actor": self.actor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceEntry":
        return cls(
            id=str(data.get("id") or ""),
            ts=str(data.get("ts") or ""),
            kind=str(data.get("kind") or ""),
            ref_id=str(data.get("ref_id") or ""),
            summary=str(data.get("summary") or ""),
            sha256=str(data.get("sha256") or ""),
            verdicts={str(k): str(v) for k, v in (data.get("verdicts") or {}).items()},
            rationale=str(data.get("rationale") or ""),
            actor=str(data.get("actor") or "system"),
        )


@dataclass
class DecisionRecord:
    """科研决策记录（P1 仅记录：动作、依据、人工覆盖）。"""

    id: str  # D-001
    action: str  # DECISION_ACTIONS
    rationale: str = ""
    evidence_refs: list[str] = _new_list()
    question_id: str = ""
    hypothesis_ids: list[str] = _new_list()
    human_override: bool = False
    actor: str = "system"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        return cls(
            id=str(data.get("id") or ""),
            action=str(data.get("action") or ""),
            rationale=str(data.get("rationale") or ""),
            evidence_refs=[str(x) for x in data.get("evidence_refs") or []],
            question_id=str(data.get("question_id") or ""),
            hypothesis_ids=[str(x) for x in data.get("hypothesis_ids") or []],
            human_override=bool(data.get("human_override") or False),
            actor=str(data.get("actor") or "system"),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass
class Project:
    """科研项目。"""

    id: str
    name: str
    description: str = ""
    goals: list[str] = _new_list()
    created_at: str = ""
    updated_at: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            goals=[str(g) for g in data.get("goals") or []],
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            schema_version=str(data.get("schema_version") or SCHEMA_VERSION),
        )


@dataclass
class ResearchState:
    """可变研究状态：已证实结果 / 当前主张 / 证据不足主张 / 未解决问题 / 阶段与目标。"""

    established_results: list[dict[str, Any]] = _new_list()  # {statement, claim_type, finding_id, evidence_refs[]}
    current_claims: list[dict[str, Any]] = _new_list()
    insufficient_claims: list[dict[str, Any]] = _new_list()
    open_questions: list[OpenQuestion] = _new_list()
    current_stage: str = ""
    next_objective: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "established_results": list(self.established_results),
            "current_claims": list(self.current_claims),
            "insufficient_claims": list(self.insufficient_claims),
            "open_questions": [q.to_dict() for q in self.open_questions],
            "current_stage": self.current_stage,
            "next_objective": self.next_objective,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchState":
        return cls(
            established_results=[dict(x) for x in data.get("established_results") or []],
            current_claims=[dict(x) for x in data.get("current_claims") or []],
            insufficient_claims=[dict(x) for x in data.get("insufficient_claims") or []],
            open_questions=[OpenQuestion.from_dict(q) for q in data.get("open_questions") or []],
            current_stage=str(data.get("current_stage") or ""),
            next_objective=str(data.get("next_objective") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )
