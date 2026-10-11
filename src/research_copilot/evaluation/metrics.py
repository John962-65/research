"""评测指标：任务完成率、无依据结论比例、HMS（官方协议）、成本与统计不确定性。

- 无依据结论比例 = (数值断言复核失败数 + 无因果依据的机制表述数) / 总检查数；
  全部由确定性代码重算，不用 LLM 判断数值。
- HMS 按官方两步协议（结构化抽取 → 0/1/2 匹配分）由 judge LLM 评分；
  judge 模型单独记录，与被测模型无关；judge 不可用时 HMS=None，绝不伪造。
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

import math

from ..analysis.statistics import compare_metric, describe, mean, numeric, regress, split_by_status
from ..analysis.evidence_validator import CAUSAL_MARKERS

_HMS_SYSTEM = """你是科学假设评分器。给定参考假设与被评假设，按官方 DiscoveryBench 协议输出匹配分：
0 = 无匹配（未捕捉参考假设的核心关系）；1 = 部分匹配（方向或主要变量对，但关系/条件不完整）；2 = 完全匹配。
只考虑数据可支持的内容；被评假设引入数据外机制不加分。
只输出 JSON：{"score": 0|1|2, "reason": "一句话"}"""


def _verify_analysis(rows: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
    """结构化分析声明重算（审查 P0-2）。

    边界（如实声明）：重算一致只证明**所声明的分析过程可复现**，
    不自动证明分析方法在科学上合理（如用相关性回答因果问题）。
    """
    a_type = str(analysis.get("analysis_type") or "")
    if a_type == "regression":
        y_col = str(analysis.get("dependent_variable") or "")
        x_cols = [str(x) for x in analysis.get("independent_variables") or []]
        controls = [str(c) for c in analysis.get("controls") or []]
        filters = {str(k): str(v) for k, v in (analysis.get("filters") or {}).items()}
        result = regress(rows, y_col, x_cols + controls, filters)
        target = str(analysis.get("reported_variable") or (x_cols[0] if x_cols else ""))
        if result is None or target not in result["betas"]:
            return {"status": "unverifiable", "note": "回归不可解（样本不足/奇异/过滤后为空）"}
        return {"status": "ok", "expected": result["betas"][target], "n": result["n"], "spec": {"y": y_col, "x": x_cols, "controls": controls, "filter": filters}}
    if a_type == "group_mean":
        column, gfield, group = str(analysis.get("column")), str(analysis.get("group_field")), str(analysis.get("group"))
        values = numeric([r for r in rows if str(r.get(gfield)) == group], column)
        if not values:
            return {"status": "unverifiable", "note": "组内无数值"}
        return {"status": "ok", "expected": describe(values, column)["mean"], "n": len(values)}
    if a_type == "group_diff":
        column, gfield = str(analysis.get("column")), str(analysis.get("group_field"))
        cand = [r for r in rows if str(r.get(gfield)) == str(analysis.get("candidate_group"))]
        base = [r for r in rows if str(r.get(gfield)) == str(analysis.get("baseline_group"))]
        cv, bv = numeric(cand, column), numeric(base, column)
        if not cv or not bv:
            return {"status": "unverifiable", "note": "组内无数值"}
        return {"status": "ok", "expected": mean(cv) - mean(bv), "n": len(cv) + len(bv)}
    if a_type == "correlation":
        x_col, y_col = str(analysis.get("x")), str(analysis.get("y"))
        pairs = [(float(r.get(x_col)), float(r.get(y_col))) for r in rows
                 if _is_number(r.get(x_col)) and _is_number(r.get(y_col))]
        if len(pairs) < 3:
            return {"status": "unverifiable", "note": "有效样本 <3"}
        xs = [p[0] for p in pairs]; ys = [p[1] for p in pairs]
        mx, my = mean(xs), mean(ys)
        sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        denom = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
        if denom <= 0:
            return {"status": "unverifiable", "note": "零方差"}
        return {"status": "ok", "expected": sxy / denom, "n": len(pairs)}
    return {"status": "unverifiable", "note": f"analysis_type {a_type} 暂不支持（如 pca_score，列入验证器路线）"}


def _is_number(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed)


def check_numeric_assertions(answer: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对答案的 numeric_assertions 逐条确定性重算。"""
    results: list[dict[str, Any]] = []
    for assertion in answer.get("numeric_assertions") or []:
        if not isinstance(assertion, dict):
            continue
        metric = str(assertion.get("metric") or "")
        claimed = assertion.get("value")
        check = str(assertion.get("check") or "mean")
        try:
            claimed_value = float(claimed)
        except (TypeError, ValueError):
            results.append({"metric": metric, "check": check, "status": "unverifiable", "note": "值不可解析"})
            continue
        # 结构化分析声明优先（P0-2）：验证器按声明重算全过程
        analysis = assertion.get("analysis")
        if isinstance(analysis, dict) and analysis.get("analysis_type"):
            verdict = _verify_analysis(rows, analysis)
            if verdict.get("status") == "unverifiable":
                results.append({"metric": metric, "check": f"analysis:{analysis.get('analysis_type')}", "status": "unverifiable", "note": verdict.get("note")})
            else:
                ok = abs(claimed_value - verdict["expected"]) <= max(abs(verdict["expected"]) * 0.05, 0.05)
                results.append({"metric": metric, "check": f"analysis:{analysis.get('analysis_type')}", "claimed": claimed_value,
                                "expected": verdict["expected"], "n": verdict.get("n"), "spec": verdict.get("spec"),
                                "status": "pass" if ok else "fail"})
            continue
        group_field = "comparison_group"
        if check == "ols_beta":
            # 回归断言验证：按断言给出的模型设定重算（修复审查 #3：回归系数不可验证）
            spec = assertion.get("regression") or {}
            y_col = str(spec.get("y") or "")
            x_cols = [str(x) for x in spec.get("x") or []]
            controls = [str(c) for c in spec.get("controls") or []]
            filters = {str(k): str(v) for k, v in (spec.get("filter") or {}).items()}
            target_var = str(spec.get("report") or (x_cols[0] if x_cols else ""))
            if not y_col or not x_cols:
                results.append({"metric": metric, "check": check, "status": "unverifiable", "note": "缺少回归设定 y/x"})
                continue
            result = regress(rows, y_col, x_cols + controls, filters)
            if result is None or target_var not in result["betas"]:
                results.append({"metric": metric, "check": check, "status": "unverifiable", "note": "回归不可解（样本不足/奇异/过滤后为空）"})
                continue
            expected = result["betas"][target_var]
            ok = abs(claimed_value - expected) <= max(abs(expected) * 0.05, abs(expected) > 0 and 0.05 * abs(expected) or 0.05)
            results.append(
                {
                    "metric": metric,
                    "check": check,
                    "claimed": claimed_value,
                    "expected": expected,
                    "n": result["n"],
                    "spec": {"y": y_col, "x": x_cols, "controls": controls, "filter": filters},
                    "status": "pass" if ok else "fail",
                }
            )
            continue
        if check == "percent_change_from_baseline":
            candidate_group = str(assertion.get("candidate_group") or "")
            baseline_group = str(assertion.get("baseline_group") or "")
            if not candidate_group or not baseline_group:
                results.append({**{"metric": metric, "check": check}, "status": "unverifiable", "note": "缺组名"})
                continue
            comparison = compare_metric(rows, metric, candidate_group, baseline_group)
            expected = None
            cand_mean = (comparison.get("candidate") or {}).get("mean")
            base_mean = (comparison.get("baseline") or {}).get("mean")
            if cand_mean is not None and base_mean:
                if comparison.get("lower_is_better") is True:
                    expected = (base_mean - cand_mean) / abs(base_mean) * 100
                else:
                    expected = (cand_mean - base_mean) / abs(base_mean) * 100
        else:
            group_name = str(assertion.get("group") or "")
            subset = [r for r in rows if not group_name or str(r.get(group_field) or "") == group_name]
            success_rows, _ = split_by_status(subset)
            values = numeric(success_rows, metric)
            if not values:
                values = numeric(subset, metric)
            if not values:
                results.append({"metric": metric, "check": check, "status": "unverifiable", "note": "数据中无该列/组"})
                continue
            stats = describe(values, metric)
            if check in ("mean", "median"):
                expected = stats.get(check)
            elif check == "percentile_p95":
                expected = (stats.get("percentiles") or {}).get("p95")
            else:
                expected = None
        if expected is None:
            results.append({"metric": metric, "check": check, "status": "unverifiable", "note": "无法重算（样本不足或字段缺失）"})
            continue
        ok = abs(claimed_value - expected) <= max(abs(expected) * 0.05, 0.1)
        results.append(
            {
                "metric": metric,
                "check": check,
                "claimed": claimed_value,
                "expected": expected,
                "status": "pass" if ok else "fail",
            }
        )
    return results


def causal_claims_without_basis(answer: dict[str, Any]) -> list[str]:
    """含因果标记的表述；P1 无受控实验元数据 → 一律计为无因果依据（如实计数）。"""
    claims: list[str] = []
    for text in [str(answer.get("mechanism") or "")] + [str(r) for r in answer.get("relationships") or []]:
        if text and CAUSAL_MARKERS.search(text):
            claims.append(text)
    return claims


def unsupported_conclusion_rate(answer: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """无依据结论比例 = (失败/无依据数值断言 + 无因果依据表述) / (数值断言数 + 机制/关系表述数)。

    evaluable=False（无有效答案/无数据）时返回 None 并标注 not_evaluable，
    绝不把无法检查的答案当作零风险。
    """
    if not isinstance(answer, dict) or not answer.get("hypothesis"):
        return {
            "evaluable": False,
            "not_evaluable_reason": "no_valid_answer",
            "unsupported_conclusion_rate": None,
        }
    if not rows:
        return {
            "evaluable": False,
            "not_evaluable_reason": "no_dataset_rows",
            "unsupported_conclusion_rate": None,
        }
    checks = check_numeric_assertions(answer, rows)
    failed_numeric = [c for c in checks if c["status"] == "fail"]
    unverifiable = [c for c in checks if c["status"] == "unverifiable"]
    causal = causal_claims_without_basis(answer)
    denominator = len(checks) + 1  # 机制/关系表述合并计 1
    unsupported = len(failed_numeric) + (1 if causal else 0)
    return {
        "evaluable": True,
        "numeric_checks": checks,
        "n_numeric": len(checks),
        "n_numeric_fail": len(failed_numeric),
        "n_numeric_unverifiable": len(unverifiable),
        "causal_without_basis": causal,
        "unsupported_conclusion_rate": round(unsupported / denominator, 4) if denominator else 0.0,
    }


def hms_score(answer: dict[str, Any], gold_hypothesis: str, judge_llm: Any) -> dict[str, Any]:
    """官方两步协议：结构化抽取（本答案已结构化）→ judge 打 0/1/2。"""
    if not answer.get("hypothesis"):
        return {"hms": None, "reason": "无有效答案", "judge_model": getattr(judge_llm, "config", None) and judge_llm.config.model}
    payload = {
        "gold_hypothesis": gold_hypothesis,
        "candidate": {
            "hypothesis": answer.get("hypothesis"),
            "variables": answer.get("variables") or [],
            "relationships": answer.get("relationships") or [],
            "mechanism": answer.get("mechanism") or "",
        },
    }
    response = judge_llm.complete(_HMS_SYSTEM, json.dumps(payload, ensure_ascii=False), purpose="hms_judge")
    match = re.search(r"\{.*\}", response, re.DOTALL)
    try:
        parsed = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        parsed = {}
    score = parsed.get("score")
    if score not in (0, 1, 2, "0", "1", "2"):
        return {"hms": None, "reason": f"judge 输出无法解析: {response[:120]}", "judge_model": _judge_model(judge_llm)}
    return {"hms": int(score), "reason": str(parsed.get("reason") or ""), "judge_model": _judge_model(judge_llm)}


def _judge_model(judge_llm: Any) -> str:
    config = getattr(judge_llm, "config", None)
    return getattr(config, "model", "unknown") if config else "unknown"


def _bootstrap_cluster_ci(by_dataset: dict[str, list[float]], n_boot: int = 1000, seed: int = 0) -> tuple[float, float] | None:
    """按数据集分层 bootstrap 百分位 CI，钳位 [0,1]（确定性 seed=0）。"""
    keys = sorted(by_dataset)
    if len(keys) < 2:
        return None
    means = []
    for b in range(n_boot):
        rng = __import__("random").Random(seed + b)
        sample = [by_dataset[keys[rng.randrange(len(keys))]] for _ in range(len(keys))]
        flat = [v for group in sample for v in group]
        means.append(sum(flat) / len(flat))
    means.sort()
    lo = max(0.0, means[int(0.025 * n_boot)])
    hi = min(1.0, means[min(n_boot - 1, int(0.975 * n_boot))])
    return (round(lo, 4), round(hi, 4))


def ci95(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    half = 1.96 * math.sqrt(variance / len(values))
    return (round(m - half, 4), round(m + half, 4))


def var_precision_heuristic(answer: dict[str, Any], gold_text: str) -> float | None:
    """确定性变量精确率交叉核对（不经 LLM）：答案 variables 的归一化 token 是否出现在金标文本。

    只算精确率（金标变量集合未知，召回率无法确定）；与 judge var_F1 互相校验。
    """
    import re as _re

    variables = answer.get("variables") or []
    if not variables or not gold_text:
        return None
    gold_norm = _re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", gold_text.lower())
    matched = 0
    for variable in variables:
        tokens = [t for t in _re.split(r"[^a-z0-9\u4e00-\u9fff]+", str(variable).lower()) if len(t) > 2]
        if not tokens:
            matched += 1  # 无法分词的短名视为匹配（保守）
            continue
        if any(token in gold_norm for token in tokens):
            matched += 1
    return round(matched / len(variables), 4)


def evidence_rates(records: list[dict[str, Any]]) -> dict[str, Any]:
    """证据三指标（修复审查 #3：unverifiable 不再被 0% 无依据比例掩盖）。

    - verified_rate: 程序复算且与声称一致的断言比例；
    - contradicted_rate: 复算与声称矛盾的比例；
    - unverifiable_rate: 缺少验证方法/数据无法重算的比例。
    """
    verified = contradicted = unverifiable = 0
    for record in records:
        for check in (record.get("unsupported") or {}).get("numeric_checks") or []:
            status = check.get("status")
            if status == "pass":
                verified += 1
            elif status == "fail":
                contradicted += 1
            else:
                unverifiable += 1
    total = verified + contradicted + unverifiable
    return {
        "n_assertions": total,
        "verified_rate": round(verified / total, 4) if total else None,
        "contradicted_rate": round(contradicted / total, 4) if total else None,
        "unverifiable_rate": round(unverifiable / total, 4) if total else None,
        "note": "unverifiable 高说明断言未被验证（不是无风险）；应通过更完整的验证器（如 ols_beta）降低",
    }


def _dataset_of(task_id: str) -> str:
    # real/test/<dataset>/metadata_N → <dataset>（同数据集多题相关，CI 须按簇计）
    parts = task_id.split("/")
    return parts[-2] if len(parts) >= 2 else task_id


def aggregate_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    """组级汇总：完成率、官方协议 accuracy 均值±95%CI（跨任务）、无依据结论比例、成本。

    - 无依据结论比例只在 **evaluable** 任务上取均值并单独报告 n_not_evaluable；
      失败/无法解析的任务不会被当作零风险计入。
    - official = 官方单子假设协议（context × var_F1 × rel，judge LLM）；hms_custom 为
      自定义 0/1/2 辅助分。
    """
    valid = [r for r in records if not r.get("error") and (r.get("answer") or {}).get("hypothesis")]
    hms_values = [r["hms_custom"] for r in records if r.get("hms_custom") is not None]
    accuracy_values = [
        float(r["official"]["accuracy"]) for r in records if (r.get("official") or {}).get("accuracy") is not None
    ]
    context_scores = [
        r["official"]["context"]["score"] for r in records if (r.get("official") or {}).get("context", {}).get("score") is not None
    ]
    var_f1 = [
        float(r["official"]["var"]["score"]["f1"])
        for r in records
        if (r.get("official") or {}).get("var", {}).get("score", {}).get("f1") is not None
        and float(r["official"]["var"]["score"]["f1"]) >= 0
    ]
    rel_scores = [
        float(r["official"]["rel"]["score"]) for r in records if (r.get("official") or {}).get("rel", {}).get("score") is not None
    ]
    unsupported_all = [r.get("unsupported") or {} for r in records]
    evaluable_unsupported = [
        item["unsupported_conclusion_rate"] for item in unsupported_all if item.get("evaluable")
    ]
    n_not_evaluable = sum(1 for item in unsupported_all if item.get("evaluable") is False)
    evidence = evidence_rates(records)
    interval = ci95(accuracy_values)

    # 数据集聚类 CI（审查 P1-2）：按数据集分层 bootstrap 重采样（确定性 seed），
    # 百分位区间钳位到 [0,1]（正态近似在小样本会越界，如 [0.111, 1.032]）。
    by_dataset: dict[str, list[float]] = {}
    for record in records:
        value = (record.get("official") or {}).get("accuracy")
        if value is not None:
            by_dataset.setdefault(_dataset_of(record["task_id"]), []).append(float(value))
    dataset_means = [sum(vs) / len(vs) for vs in by_dataset.values()]
    cluster_interval = _bootstrap_cluster_ci(by_dataset)
    # 全任务得分（审查 P1-2）：未完成任务统一记 0，与"成功任务平均"分开报告
    full_task_scores = [
        float((r.get("official") or {}).get("accuracy") or 0.0) for r in records
    ]
    full_task_score_mean = round(sum(full_task_scores) / len(full_task_scores), 4) if full_task_scores else None
    full_task_interval = _bootstrap_cluster_ci(
        {str(i): [v] for i, v in enumerate(full_task_scores)}  # 任务级 bootstrap（全分母口径）
    ) if full_task_scores else None
    failure_breakdown: dict[str, int] = {}
    for record in records:
        fc = record.get("failure_class") or ("" if (record.get("answer") or {}).get("hypothesis") else "unknown")
        if fc:
            failure_breakdown[fc] = failure_breakdown.get(fc, 0) + 1

    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    return {
        "n_tasks": len(records),
        "completion_rate": round(len(valid) / len(records), 4) if records else 0.0,
        "official_accuracy_mean": _mean(accuracy_values),
        "official_accuracy_ci95": interval,
        "official_accuracy_cluster_ci95": cluster_interval,
        "cluster_ci_method": "dataset-stratified bootstrap (1000, seed=0), clamped [0,1]",
        "n_datasets": len(by_dataset),
        "full_task_score_mean": full_task_score_mean,
        "full_task_score_ci95": full_task_interval,
        "full_task_note": "全任务分母：未完成任务记 0 分（与成功任务平均分开报告，审查 P1-2）",
        "failure_breakdown": failure_breakdown,
        "n_official_scored": len(accuracy_values),
        "context_match_rate": _mean([1.0 if s == 1.0 else 0.0 for s in context_scores]) if context_scores else None,
        "var_f1_mean": _mean(var_f1),
        "rel_score_mean": _mean(rel_scores),
        "hms_custom_mean": _mean([float(v) for v in hms_values]),
        "unsupported_rate_mean_evaluable": _mean([float(v) for v in evaluable_unsupported]),
        "n_not_evaluable": n_not_evaluable,
        "evidence": evidence,
        "total_llm_calls": sum(r.get("llm_calls", 0) for r in records),
        "total_tool_calls": sum(r.get("tool_calls", 0) for r in records),
        "total_prompt_tokens": sum(r.get("prompt_tokens", 0) for r in records),
        "total_completion_tokens": sum(r.get("completion_tokens", 0) for r in records),
        "total_judge_calls": sum(r.get("judge_calls", 0) for r in records),
    }


def paired_delta(records_x: list[dict[str, Any]], records_y: list[dict[str, Any]], value_key: str = "official_accuracy", key: str = "task_id") -> dict[str, Any]:
    """按任务配对的组间差（x - y），CI 优先、无 p 值。默认用官方协议 accuracy。"""

    def _value(record: dict[str, Any]) -> float | None:
        if value_key == "official_accuracy":
            return (record.get("official") or {}).get("accuracy")
        return record.get(value_key)

    y_by_task = {r[key]: r for r in records_y}
    deltas = []
    for record in records_x:
        other = y_by_task.get(record[key])
        vx = _value(record)
        vy = _value(other) if other else None
        if other is None or vx is None or vy is None:
            continue
        deltas.append(vx - vy)
    mean_delta = round(sum(deltas) / len(deltas), 4) if deltas else None
    return {
        "value_key": value_key,
        "n_paired": len(deltas),
        "delta_mean": mean_delta,
        "delta_ci95": ci95([float(d) for d in deltas]),
        "note": "官方协议 accuracy ∈ [0,1]（context×var_F1×rel）；delta>0 表示 x 组更优。跨任务 CI 仅描述本任务子集的不确定性。",
    }
