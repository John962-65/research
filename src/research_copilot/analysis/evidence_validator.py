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


def _has_controlled_experiment_evidence(
    refs: list[EvidenceRef], materials_by_id: dict[str, Material], claim_variables: list[str] | None = None
) -> bool:
    """受控实验证据必须与主张变量相关：meta 需声明 experiment_kind=controlled，
    且（若声明了 intervention_variables）干预变量须与主张变量有交集。"""
    for ref in refs:
        material = materials_by_id.get(ref.material_id)
        if not material or str(material.meta.get("experiment_kind") or "").lower() not in ("controlled", "randomized", "rct"):
            continue
        interventions = [str(v).lower() for v in (material.meta.get("intervention_variables") or [])]
        if not interventions or not claim_variables:
            return True  # 未声明干预变量时保守放行（仍需人工复核整体合理性）
        claim_vars = {v.lower() for v in claim_variables if v}
        if claim_vars & set(interventions):
            return True
    return False


def _check_relation_claims(
    finding: Finding, observations_by_id: dict[str, Observation]
) -> tuple[list[dict[str, Any]], list[str]]:
    """L2b：结构化关系主张的方向核对。

    - 有匹配观测且方向一致 → pass；
    - 有匹配观测且方向矛盾 → fail（数值性错误，触发降级）；
    - 找不到可核对的相关计算 → unverifiable（不 fail，但阻止自动升级）。
    """
    checks: list[dict[str, Any]] = []
    issues: list[str] = []
    for claim in finding.claims or []:
        relation = claim.relation
        if relation not in ("positive", "negative", "none"):
            continue
        candidates = [observations_by_id[cid] for cid in finding.observation_ids if cid in observations_by_id]
        if claim.basis_observation:
            target = observations_by_id.get(claim.basis_observation)
            if target is not None and target.id in finding.observation_ids:
                candidates = [target]
        matched = None
        for observation in candidates:
            for rel in (observation.value or {}).get("relations") or []:
                pair = {str(rel.get("a", "")).lower(), str(rel.get("b", "")).lower()}
                if {claim.variable_a.lower(), claim.variable_b.lower()} == pair:
                    matched = rel
                    break
            if matched:
                break
        if matched is None:
            checks.append(
                {
                    "claim": f"{claim.variable_a}~{claim.variable_b}",
                    "claimed_relation": relation,
                    "status": "unverifiable",
                    "note": "被引观测中没有该变量对的计算相关，无法程序核对",
                }
            )
            # unverifiable 不算 L2 失败（不是数值错误），只阻止自动升级（见 needs_human_review）
        elif matched.get("sign") != relation:
            checks.append(
                {
                    "claim": f"{claim.variable_a}~{claim.variable_b}",
                    "claimed_relation": relation,
                    "computed_relation": matched.get("sign"),
                    "computed_r": matched.get("pearson_r"),
                    "status": "fail",
                }
            )
            issues.append(
                f"关系方向不符：声称 {claim.variable_a}~{claim.variable_b}={relation}，"
                f"计算结果为 {matched.get('sign')}(r={matched.get('pearson_r')})"
            )
        else:
            checks.append(
                {
                    "claim": f"{claim.variable_a}~{claim.variable_b}",
                    "claimed_relation": relation,
                    "computed_relation": matched.get("sign"),
                    "status": "pass",
                }
            )
    return checks, issues


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

    # ---- L2b 关系主张方向核对 ----
    relation_checks, relation_issues = _check_relation_claims(finding, observations_by_id)
    l2_issues.extend(relation_issues)
    relation_unverifiable = any(c["status"] == "unverifiable" for c in relation_checks)
    relation_failed = any(c["status"] == "fail" for c in relation_checks)

    l2_status = "fail" if l2_issues else ("pass" if (l2_checks or relation_checks) else "not_applicable")

    # ---- L3 解释有效性 ----
    l3_note = "无因果标记"
    if CAUSAL_MARKERS.search(finding.statement or ""):
        claim_variables = [v for claim in (finding.claims or []) for v in (claim.variable_a, claim.variable_b)]
        if _has_controlled_experiment_evidence(resolved_refs, materials_by_id, claim_variables):
            l3_note = "存在与主张变量相关的受控实验证据，因果表述可保留"
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
            downgrades.append("L2: 数值/关系复核未通过，降级为 unverified_conjecture")
            claim_type = "unverified_conjecture"
        elif claim_type in ("hypothesis", "causal_claim"):
            downgrades.append("L2: 数值/关系复核未通过，假设保留但标记证据不足")
            claim_type = "unverified_conjecture"

    # ---- 不可程序核对的关系主张：阻止自动升级，转人工复核 ----
    final_status = "verified" if claim_type in ("observation", "statistical_finding") else "downgraded"
    if final_status == "verified" and relation_unverifiable:
        final_status = "needs_human_review"
        downgrades.append(
            "L2b: 关系主张方向无法由程序核对（无计算依据），不自动升级为已证实结果，转人工复核"
        )

    validation = {
        "l1": {"status": "pass", "issues": []},
        "l2": {
            "status": l2_status,
            "checks": l2_checks,
            "relation_checks": relation_checks,
            "relation_unverifiable": relation_unverifiable,
            "relation_failed": relation_failed,
            "issues": l2_issues,
        },
        "l3": {"status": "downgraded" if any("L3" in d for d in downgrades) else "pass", "note": l3_note},
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
