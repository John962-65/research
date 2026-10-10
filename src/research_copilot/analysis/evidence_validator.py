"""三层证据校验（Research Copilot 的信任核心）。

- L1 引用有效性：引用的观测存在，其证据引用的材料可访问且哈希一致；
- L2 数值一致性：可程序验证的数值/方向断言由确定性代码重算复核，不用 LLM；
- L3 解释有效性：因果/机制主张在没有受控实验证据时自动降级为 hypothesis。

校验后主张级别（五级分类）：
    observation / statistical_finding  → 可升级为已证实结果（须注明适用条件）
    hypothesis / causal_claim          → 待验证，不得写成结论
    unverified_conjecture              → 缺证据猜想，仅保留供人工审阅
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.evidence import check_ref
from ..core.models import EvidenceRef, Finding, Material, NumericAssertion, Observation

CAUSAL_MARKERS = re.compile(
    r"因为|由于|导致|归因|原因是|机制是|造成|引发|因而|所以|caused by|due to|because of|results in|"
    r"leads? to|explains|attribut\w+|mechanism is|the reason",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?%?")


def _close(value: float, expected: float, rel_tol: float = 0.05, abs_tol: float = 0.1) -> bool:
    return abs(value - expected) <= max(abs(expected) * rel_tol, abs_tol)


def _observation_value(observation: Observation) -> dict[str, Any]:
    return observation.value or {}


def _check_numeric_assertion(
    assertion_dict: dict[str, Any], observation: Observation
) -> dict[str, Any]:
    """对单条数值断言做确定性复核。"""
    assertion = NumericAssertion.from_dict(assertion_dict)
    value = observation.value or {}
    check = assertion.check or "lookup"
    expected: float | None = None
    note = ""

    if check == "percent_change_from_baseline":
        baseline = value.get("baseline_mean", value.get("baseline"))
        candidate = value.get("candidate_mean", value.get("candidate"))
        if baseline is None or candidate is None:
            note = "观测缺少 baseline/candidate 均值，无法复核百分比"
        elif float(baseline) == 0:
            note = "baseline 均值为 0，百分比无定义"
        else:
            # 约定：改善为正。lower_is_better 时 (基线-候选)/|基线|；higher_is_better 时 (候选-基线)/|基线|
            lower = value.get("lower_is_better")
            if lower is True:
                expected = (float(baseline) - float(candidate)) / abs(float(baseline)) * 100.0
            else:
                expected = (float(candidate) - float(baseline)) / abs(float(baseline)) * 100.0
    elif check == "ratio":
        a, b = value.get("a"), value.get("b")
        if a is None or b in (None, 0):
            note = "观测缺少 ratio 分子/分母"
        else:
            expected = float(a) / float(b)
    elif check in ("mean", "median"):
        expected = value.get(check)
        if expected is None:
            note = f"观测缺少 {check} 字段"
    elif check.startswith("percentile"):
        q = check.rsplit("p", 1)[-1] or "95"
        expected = (value.get("percentiles") or {}).get(f"p{q}")
        if expected is None:
            note = f"观测缺少 p{q}（可能因样本不足未报告）"
    elif check == "direction":
        interp = value.get("interpretation")
        if interp not in ("candidate_better", "baseline_better_or_equal", "no_clear_difference"):
            note = "观测缺少方向化解读"
        else:
            return {
                "metric": assertion.metric,
                "check": check,
                "claimed": assertion.value,
                "expected": interp,
                "status": "pass" if str(assertion.value) == interp else "fail",
                "note": note,
            }
    else:  # lookup：断言值应直接出现在观测 value 的某个字段里
        flat = _flatten_numbers(value)
        expected = None
        if flat and _close(assertion.value, min(flat, key=lambda x: abs(x - assertion.value))):
            return {"metric": assertion.metric, "check": "lookup", "claimed": assertion.value, "status": "pass", "note": ""}
        return {
            "metric": assertion.metric,
            "check": "lookup",
            "claimed": assertion.value,
            "status": "fail",
            "note": "断言数值无法在所引观测中找到",
        }

    if expected is None:
        return {
            "metric": assertion.metric,
            "check": check,
            "claimed": assertion.value,
            "status": "not_applicable",
            "note": note,
        }
    return {
        "metric": assertion.metric,
        "check": check,
        "claimed": assertion.value,
        "expected": expected,
        "status": "pass" if _close(assertion.value, expected) else "fail",
        "note": note,
    }


def _flatten_numbers(payload: Any) -> list[float]:
    out: list[float] = []
    if isinstance(payload, bool):
        return out
    if isinstance(payload, (int, float)):
        out.append(float(payload))
    elif isinstance(payload, dict):
        for item in payload.values():
            out.extend(_flatten_numbers(item))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            out.extend(_flatten_numbers(item))
    return out


def _unverified_numbers_in_text(statement: str, assertions: list[NumericAssertion], observation: Observation | None) -> list[float]:
    """文本中的数字若既不在断言里、也不在被引观测中出现 → 视为无依据数字。

    带百分号的数字按 value/100 与观测值匹配（如"3.3%"对应 tail_share=0.033）。
    """
    allowed = {a.value for a in assertions if a.value == a.value}
    if observation is not None:
        allowed.update(_flatten_numbers(observation.value))
    suspicious = []
    for raw in _NUMBER_RE.findall(statement):
        is_percent = raw.endswith("%")
        number = float(raw.rstrip("%"))
        candidates = (number, number / 100.0) if is_percent else (number,)
        if not any(any(_close(c, allowed_value) for allowed_value in allowed) for c in candidates):
            suspicious.append(number)
    return suspicious


def _has_controlled_experiment_evidence(refs: list[EvidenceRef], materials_by_id: dict[str, Material]) -> bool:
    for ref in refs:
        material = materials_by_id.get(ref.material_id)
        if material and str(material.meta.get("experiment_kind") or "").lower() in ("controlled", "randomized", "rct"):
            return True
    return False


def validate_finding(
    finding: Finding,
    observations_by_id: dict[str, Observation],
    materials_by_id: dict[str, Material],
    project_dir: Path | None = None,
) -> dict[str, Any]:
    """对单条发现执行三层校验，返回 validation 字典（含最终 claim_type 与 status）。"""
    downgrades: list[str] = []
    claim_type = finding.claim_type or "unverified_conjecture"

    # ---- L1 引用有效性 ----
    resolved_refs: list[EvidenceRef] = []
    l1_issues: list[str] = []
    cited_observations: list[Observation] = []
    for obs_id in finding.observation_ids:
        observation = observations_by_id.get(obs_id)
        if observation is None:
            l1_issues.append(f"引用的观测 {obs_id} 不存在")
            continue
        cited_observations.append(observation)
        if not observation.evidence_refs:
            l1_issues.append(f"观测 {obs_id} 没有证据引用")
            continue
        for ref in observation.evidence_refs:
            result = check_ref(ref, materials_by_id, project_dir)
            if result["status"] == "valid":
                resolved_refs.append(ref)
            else:
                l1_issues.append(f"观测 {obs_id} 的证据失效（{result['status']}）：{result['detail']}")

    if l1_issues:
        return {
            "l1": {"status": "fail", "issues": l1_issues},
            "l2": {"status": "not_applicable"},
            "l3": {"status": "not_applicable"},
            "downgrades": downgrades,
            "final_claim_type": "unverified_conjecture",
            "status": "rejected",
            "resolved_refs": [],
        }
    if not finding.observation_ids:
        return {
            "l1": {"status": "fail", "issues": ["发现未引用任何观测"]},
            "l2": {"status": "not_applicable"},
            "l3": {"status": "not_applicable"},
            "downgrades": downgrades,
            "final_claim_type": "unverified_conjecture",
            "status": "rejected",
            "resolved_refs": [],
        }

    # ---- L2 数值一致性 ----
    l2_checks: list[dict[str, Any]] = []
    l2_issues: list[str] = []
    primary_obs = cited_observations[0] if cited_observations else None
    for assertion in (finding.numeric_assertions or []):
        # 断言须指向被引用的观测
        basis = assertion.basis_observation
        target = observations_by_id.get(basis) if basis else primary_obs
        if target is None or (basis and basis not in finding.observation_ids):
            l2_issues.append(f"数值断言 {assertion.metric} 的依据观测 {basis or '(缺省)'} 未被引用")
            continue
        result = _check_numeric_assertion(assertion.to_dict(), target)
        l2_checks.append(result)
        if result["status"] == "fail":
            l2_issues.append(
                f"数值断言不符：{result['metric']} 声称 {result['claimed']}，"
                f"按 {result['check']} 重算为 {result.get('expected')}"
            )
    for number in _unverified_numbers_in_text(finding.statement, finding.numeric_assertions, primary_obs):
        l2_issues.append(f"陈述含无依据数字 {number}（未在数值断言或被引观测中出现）")

    l2_status = "fail" if l2_issues else ("pass" if l2_checks else "not_applicable")

    # ---- L3 解释有效性 ----
    l3_note = "无因果标记"
    if CAUSAL_MARKERS.search(finding.statement or ""):
        if _has_controlled_experiment_evidence(resolved_refs, materials_by_id):
            l3_note = "存在受控实验证据，因果表述可保留"
        else:
            if claim_type in ("observation", "statistical_finding"):
                downgrades.append(
                    "L3: 陈述含因果/机制表述但无受控实验证据，降级为 hypothesis（数据只支持相关性/现象）"
                )
            claim_type = "hypothesis"
            l3_note = "因果/机制主张需受控实验或因果识别证据；当前降级为待验证假设"

    # ---- L2 失败降级 ----
    if l2_status == "fail":
        if claim_type in ("observation", "statistical_finding"):
            downgrades.append("L2: 数值复核未通过，降级为 unverified_conjecture")
            claim_type = "unverified_conjecture"
        elif claim_type in ("hypothesis", "causal_claim"):
            downgrades.append("L2: 数值复核未通过，假设保留但标记证据不足")
            claim_type = "unverified_conjecture"

    final_status = "verified" if claim_type in ("observation", "statistical_finding") else "downgraded"
    validation = {
        "l1": {"status": "pass", "issues": []},
        "l2": {"status": l2_status, "checks": l2_checks, "issues": l2_issues},
        "l3": {"status": "downgraded" if downgrades else "pass", "note": l3_note},
        "downgrades": downgrades,
        "final_claim_type": claim_type,
        "status": final_status,
        "resolved_refs": [ref.to_dict() for ref in resolved_refs],
    }
    return validation


def apply_validation(finding: Finding, validation: dict[str, Any]) -> Finding:
    """把校验结果写回发现对象。"""
    finding.validation = validation
    finding.claim_type = validation["final_claim_type"]
    return finding
