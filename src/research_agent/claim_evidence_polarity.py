"""Claim polarity and condition conflict rules (T08 / A17–A18).

词面重合只用于候选证据检索；关键结论的支持性判断必须核对：
- 否定方向（原文"提升"，稿件"未提升" → 不得因词相似判支持）；
- 数字（主张中的具体数值必须能在证据文本中找到，否则标记冲突）；
- 比较对象与实验条件（主张与证据引用不同数据集/对象 → 条件冲突）。

判定输出四值（decision-contract §1 语义）：
- supported：方向一致且无冲突；
- contradicted：方向相反或条件/数字冲突（阻断级）；
- insufficient_evidence：主张有方向断言但证据文本不含任何方向信息；
- not_assessed：主张本身无方向断言（如范围/边界陈述），不做极性判断。

规则判定不确定时留待人工（review），不伪造语义理解。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


_DIRECTION_POSITIVE = [
    "提升", "提高", "改善", "优于", "超过", "加快", "更快", "更高", "更强", "增加",
    "outperform", "improve", "increase", "higher", "faster", "better", "superior", "gain",
]
_DIRECTION_NEGATIVE = [
    "未提升", "没有提升", "未见提升", "不优于", "低于", "差于", "下降", "减少", "恶化", "更差", "更慢", "无效",
    "no improvement", "not improve", "does not outperform", "lower", "worse", "decrease", "degrade", "slower",
]
# 词根级方向词（用于在证据文本里匹配"同一个方向"的正/反表述）
_POSITIVE_STEMS = ["提升", "提高", "改善", "优于", "增加", "outperform", "improve", "higher", "faster", "superior"]
_NEGATION_MARKERS = ["未", "没有", "不", "无", "未能", "not ", "no ", "does not", "did not", "fails to"]

_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
_DATASET_TOKEN_PATTERN = re.compile(r"\b(?:UCI|Iris|OMPL|RRT|RRT\*|PRM|CHOMP|STOMP|MoveIt|Ros|ROS|Gazebo|MNIST|CIFAR|GLUE|SQuAD)\b")


@dataclass(frozen=True)
class PolarityAssessment:
    polarity: str
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"polarity": self.polarity, "conflicts": list(self.conflicts), "notes": list(self.notes)}


def assess_claim_polarity(claim_text: str, evidence_text: str) -> PolarityAssessment:
    claim = str(claim_text or "")
    evidence = str(evidence_text or "")
    if not claim.strip():
        return PolarityAssessment("not_assessed", [], ["空主张"])
    claim_has_direction = _has_direction(claim)
    if not claim_has_direction:
        return PolarityAssessment("not_assessed", [], ["主张不含方向断言，仅做证据定位核对"])
    if not evidence.strip():
        return PolarityAssessment("insufficient_evidence", [], ["引用证据文本为空，无法核对方向"])

    conflicts: list[str] = []
    notes: list[str] = []
    claim_positive = _asserts_positive(claim)
    claim_negative = _asserts_negative(claim)
    evidence_positive = _contains_positive(evidence)
    evidence_negative = _contains_negative(evidence)

    if claim_positive and evidence_negative:
        conflicts.append(
            "direction_conflict: 主张为正向断言，但所引证据文本包含反向/否定表述；词面重合不能作为支持依据。"
        )
    elif claim_negative and evidence_positive:
        conflicts.append(
            "direction_conflict: 主张为否定断言，但所引证据文本包含正向表述；请核对引用是否用反。"
        )

    conflict = _number_conflict(claim, evidence)
    if conflict:
        conflicts.append(conflict)

    condition = _condition_conflict(claim, evidence)
    if condition:
        conflicts.append(condition)

    if conflicts:
        return PolarityAssessment("contradicted", conflicts, notes)
    if not evidence_positive and not evidence_negative and _numbers(evidence) == []:
        # 证据文本既无方向信息也无数字 → 无法由该证据支撑方向断言。
        return PolarityAssessment("insufficient_evidence", [], ["证据文本不含方向或数值信息，需人工核对全文"])
    if claim_positive and not evidence_positive and evidence_negative is False:
        notes.append("证据文本未直接复现正向表述；词面重合仅作检索候选，方向支持需人工确认。")
    return PolarityAssessment("supported", conflicts, notes)


def _has_direction(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _DIRECTION_POSITIVE + _DIRECTION_NEGATIVE)


def _asserts_positive(text: str) -> bool:
    """句中存在未被否定的正向方向词。"""
    lowered = text.lower()
    for stem in _POSITIVE_STEMS:
        index = lowered.find(stem)
        while index >= 0:
            window = lowered[max(0, index - 12) : index]
            if not any(marker in window for marker in _NEGATION_MARKERS):
                return True
            index = lowered.find(stem, index + 1)
    return False


def _asserts_negative(text: str) -> bool:
    return any(token in text.lower() for token in _DIRECTION_NEGATIVE)


def _contains_positive(text: str) -> bool:
    return _asserts_positive(text)


def _contains_negative(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _DIRECTION_NEGATIVE)


def _numbers(text: str) -> list[str]:
    return _NUMBER_PATTERN.findall(text or "")


def _number_conflict(claim: str, evidence: str) -> str:
    """主张给了具体数值而证据文本有数字却一个都对不上 → 冲突提示。"""
    claim_numbers = [item for item in _numbers(claim) if item not in {"95", "0.05"}]
    if len(claim_numbers) < 1:
        return ""
    evidence_numbers = _numbers(evidence)
    if not evidence_numbers:
        return ""
    if not any(number in evidence_numbers for number in claim_numbers):
        return (
            f"number_conflict: 主张数值 {claim_numbers[:4]} 在证据文本的数值 {evidence_numbers[:8]} 中均未出现；"
            "引用数值必须与来源一致。"
        )
    return ""


def _condition_conflict(claim: str, evidence: str) -> str:
    """主张与证据引用了不同的数据集/对象 token → 条件冲突提示。"""
    claim_tokens = {token.upper() for token in _DATASET_TOKEN_PATTERN.findall(claim)}
    evidence_tokens = {token.upper() for token in _DATASET_TOKEN_PATTERN.findall(evidence)}
    if claim_tokens and evidence_tokens and not (claim_tokens & evidence_tokens):
        return (
            f"condition_conflict: 主张对象 {sorted(claim_tokens)[:4]} 与证据对象 {sorted(evidence_tokens)[:4]} 不一致；"
            "不得把数据集 A 的结果写成数据集 B。"
        )
    return ""
