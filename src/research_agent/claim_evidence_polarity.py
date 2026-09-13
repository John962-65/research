"""Claim polarity and condition conflict rules (T08 / A17–A18 / 复审第 5 项).

词面重合只用于候选证据检索；关键结论的支持性判断必须核对：
- 否定方向（原文"提升"，稿件"未提升" → 不得因词相似判支持）；
- 数字（目标数值必须能在证据文本中找到；年份等背景数字不参与比较）；
- 比较对象与实验条件（主张与证据引用不同数据集/对象 → 条件冲突）。

方向判断按**从句+指标**归因：同一句里"提高准确率，但没有提高速度"
是两个指标各自的极性，不得互相污染（复审第 5 项）。

判定输出四值：
- supported：主张的每个正向指标在证据同指标从句中得到同向支持；
- contradicted：同指标方向相反、目标数值缺失或条件冲突（阻断级）；
- insufficient_evidence：证据文本不含对应方向信息或数值语义无法绑定
  （待核验，不伪造语义理解）；
- not_assessed：主张本身无方向断言，仅做证据定位核对。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


_POSITIVE_STEMS = ["提升", "提高", "改善", "优于", "超过", "加快", "增加", "outperform", "improve", "higher", "faster", "better", "superior", "gain"]
_DIRECTION_NEGATIVE = [
    "未提升", "没有提升", "未见提升", "不提升", "没有提高", "未提高", "不提高", "未改善",
    "不优于", "低于", "差于", "下降", "减少", "恶化", "更差", "更慢", "无效", "持平",
    "no improvement", "not improve", "does not outperform", "lower", "worse", "decrease", "degrade", "slower",
]
_NEGATION_MARKERS = ["未", "没有", "不", "无", "未能", "not ", "no ", "does not", "did not", "fails to"]

_METRIC_KEYWORDS = [
    "准确率", "精度", "成功率", "召回", "查准", "误差", "错误率", "速度", "耗时", "延迟", "吞吐", "成本",
    "accuracy", "precision", "recall", "f1", "speed", "latency", "throughput", "success_rate", "error_rate", "time", "cost",
]
_CLAUSE_SPLIT = re.compile(r"[，。；,;、（）()]|\bbut\b|\bhowever\b|\bwhile\b|但是|但|而|不过")

_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
_YEAR_PATTERN = re.compile(r"(?:^|\D)((?:19|20)\d{2})(?:\D|$)")
# 目标数值：提升(到)/提高(到)/达到/增加到 X；从 A 提升到/提高到/到 B；improve(d) to X
_TARGET_PATTERN = re.compile(
    r"(?:提升到|提高到|提升至|提高至|增加到|增长到|上升到|达到|improve(?:s|d)?\s+to|reach(?:es|ed)?)\s*[\d.]+%?"
    r"|(?:从)\s*[\d.]+%?\s*(?:到|至|提升到|提高到|提升至)\s*[\d.]+%?"
    # 复审第 9 轮第 6 项：指标词穿插形式——"提高准确率到 99%"。
    r"|(?:提升|提高|增加|上升|达到)[^，。；%;]{0,12}?(?:到|至|为)\s*[\d.]+%?"
)
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
    if not _has_direction(claim):
        return PolarityAssessment("not_assessed", [], ["主张不含方向断言，仅做证据定位核对"])
    if not evidence.strip():
        return PolarityAssessment("insufficient_evidence", [], ["引用证据文本为空，无法核对方向"])

    conflicts: list[str] = []
    notes: list[str] = []
    claim_map = _metric_polarity_map(claim)
    evidence_map = _metric_polarity_map(evidence)

    # 1) 同指标方向核对（复审第 5 项：从句极性按指标归因，不整句污染）；
    #    复审第 9 轮第 6 项：否定主张同样需要证据同指标同向确认——
    #    "没有检测到矛盾"不等于"有证据支持"。
    direction_conflict = False
    for metric, claim_pols in claim_map.items():
        evidence_pols = evidence_map.get(metric, set())
        if claim_pols & evidence_pols:
            continue  # 同指标同向（正正或负负）
        if evidence_pols:
            if claim_pols & {"pos"} and evidence_pols & {"neg"}:
                conflicts.append(
                    f"direction_conflict[{metric}]: 主张为正向断言，但所引证据同一指标为否定表述；词面重合不能作为支持依据。"
                )
                direction_conflict = True
            elif claim_pols & {"neg"} and evidence_pols & {"pos"}:
                conflicts.append(
                    f"direction_conflict[{metric}]: 主张为否定断言，但所引证据同一指标为正向表述；请核对引用是否用反。"
                )
                direction_conflict = True
            continue
        notes.append(f"指标 {metric} 在证据文本中无方向信息，待人工核验。")

    # 1b) 方法/对象主体匹配（复审第 9 轮第 6 项）：
    #     "Method A improves accuracy" ≠ "Method B improves accuracy"。
    subject_conflict, subject_insufficient = _subject_conflict(claim, evidence)
    if subject_conflict:
        conflicts.append(subject_conflict)
    if subject_insufficient:
        notes.append(subject_insufficient)

    # 2) 目标数值核对：主张的目标数值必须出现在证据数值中（年份除外）。
    number_conflict = _number_conflict(claim, evidence)
    if number_conflict:
        conflicts.append(number_conflict)

    # 3) 数据集/对象条件核对。
    condition = _condition_conflict(claim, evidence)
    if condition:
        conflicts.append(condition)

    if conflicts:
        return PolarityAssessment("contradicted", conflicts, notes)
    # 4) 支持判定：主张的每个方向断言（正向或否定）都必须在证据中找到
    #    同指标同向表述；找不到 → insufficient_evidence（待核验），
    #    不得落回 supported（复审第 9 轮第 6 项：否定主张同样需要确认）。
    directional_metrics = [metric for metric, pols in claim_map.items() if pols]
    if directional_metrics and not direction_conflict:
        unverified = [
            metric
            for metric in directional_metrics
            if not (claim_map[metric] & evidence_map.get(metric, set()))
        ]
        if unverified:
            return PolarityAssessment(
                "insufficient_evidence",
                [],
                ["证据文本未对以下指标给出同向支持，需人工核对：" + "、".join(unverified[:4])] + notes,
            )
    # 5) 主张含数值但无法绑定目标语义（如差值表述）且证据有数字 → 待核验。
    if _numbers_without_years(claim) and not _targets(claim) and _numbers_without_years(evidence):
        return PolarityAssessment("insufficient_evidence", [], ["主张数值语义无法绑定目标值（如差值），需人工核对"] + notes)
    # 5b) 复审第 9 轮第 6 项：主张声明了目标数值，而证据文本不含任何数值
    #     → 无法确认该数值有来源，待核验（"提高准确率到 99%" vs "提高准确率"）。
    if _targets(claim) and not _numbers_without_years(evidence):
        return PolarityAssessment(
            "insufficient_evidence",
            [],
            ["主张声明了目标数值，但证据文本不含任何数值，无法确认其来源，需人工核对"] + notes,
        )
    return PolarityAssessment("supported", conflicts, notes)


def _has_direction(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _POSITIVE_STEMS + _DIRECTION_NEGATIVE)


def _metric_polarity_map(text: str) -> dict[str, set[str]]:
    """按从句+指标归因极性；无法归因到具体指标的进入 _general。"""
    result: dict[str, set[str]] = {}
    for clause in _CLAUSE_SPLIT.split(text):
        clause = clause.strip()
        if not clause:
            continue
        pols: set[str] = set()
        if _clause_positive(clause):
            pols.add("pos")
        if _clause_negative(clause):
            pols.add("neg")
        if not pols:
            continue
        lowered = clause.lower()
        metric = next((k for k in _METRIC_KEYWORDS if k.lower() in lowered), "_general")
        result.setdefault(metric, set()).update(pols)
    return result


def _clause_positive(clause: str) -> bool:
    lowered = clause.lower()
    for stem in _POSITIVE_STEMS:
        index = lowered.find(stem.lower())
        while index >= 0:
            window = lowered[max(0, index - 12) : index]
            if not any(marker in window for marker in _NEGATION_MARKERS):
                return True
            index = lowered.find(stem.lower(), index + 1)
    return False


def _clause_negative(clause: str) -> bool:
    lowered = clause.lower()
    return any(token in lowered for token in _DIRECTION_NEGATIVE)


def _numbers_without_years(text: str) -> list[str]:
    raw = _NUMBER_PATTERN.findall(text or "")
    years = set(_YEAR_PATTERN.findall(text or ""))
    return [n for n in raw if n.strip("%") not in years]


def _targets(claim: str) -> list[str]:
    """主张中的目标数值（提升到/达到/从 A 到 B 的 B 等语义绑定数值）。"""
    targets: list[str] = []
    for match in _TARGET_PATTERN.finditer(claim or ""):
        nums = _NUMBER_PATTERN.findall(match.group(0))
        if nums:
            targets.append(nums[-1])  # 取目标端数值
    return targets


def _number_conflict(claim: str, evidence: str) -> str:
    """目标数值未出现在证据数值中 → 冲突；语义无法绑定时交由待核验分支。"""
    targets = _targets(claim)
    evidence_numbers = _numbers_without_years(evidence)
    if not targets or not evidence_numbers:
        return ""
    missing = [t for t in targets if t not in evidence_numbers]
    if missing:
        return (
            f"number_conflict: 主张的目标数值 {missing[:4]} 在证据文本的数值 {evidence_numbers[:8]} 中未出现；"
            "引用数值必须与来源一致。"
        )
    return ""


_SUBJECT_PATTERN = re.compile(
    r"\b(?:method|model|approach|planner|agent|variant|algorithm)\s+[-]?[A-Za-z0-9]\b"
    r"|(?:方法|模型|方案|算法|变体)\s*[-]?[A-Za-z0-9](?:[A-Za-z0-9]*)",
    re.IGNORECASE,
)


def _subject_conflict(claim: str, evidence: str) -> tuple[str, str]:
    """方法/对象主体核对：主张与证据的方法标识必须相交，否则矛盾或待核验。"""
    claim_subjects = {match.group(0).lower() for match in _SUBJECT_PATTERN.finditer(claim)}
    evidence_subjects = {match.group(0).lower() for match in _SUBJECT_PATTERN.finditer(evidence)}
    if claim_subjects and evidence_subjects:
        if not (claim_subjects & evidence_subjects):
            return (
                f"subject_conflict: 主张方法 {sorted(claim_subjects)[:3]} 与证据方法 {sorted(evidence_subjects)[:3]} 不一致；"
                "不得把方法 A 的结果写成方法 B。"
            ), ""
        return "", ""
    if claim_subjects and not evidence_subjects:
        return "", (
            f"主张声明了方法标识 {sorted(claim_subjects)[:3]}，但证据文本未提及任何方法标识，"
            "无法确认是否同一方法，需人工核对。"
        )
    return "", ""


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
