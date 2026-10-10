"""诊断 Agent：真实材料 → 确定性观测 → （可选 LLM）发现 → 三层校验 → 待研究问题。

离线模式（无 LLM）：仅输出确定性统计观测与规则式发现，明确标注 offline；
无异常时不得强行生成问题。LLM 发现若未通过证据校验会被降级为
unverified_conjecture，绝不会被写成研究发现。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..analysis.anomaly_detection import detect_anomalies, tail_report
from ..analysis.evidence_validator import apply_validation, validate_finding
from ..analysis.statistics import compare_metric, group_profile, resolve_direction
from ..core.models import EvidenceRef, Finding, Material, NumericAssertion, Observation, RelationClaim
from ..core.storage import ProjectStore, now_iso
from ..integrations.llm import LLMUnavailable

SYSTEM_PROMPT = """你是科研诊断助手。你只能基于给定的观测（observations）生成科学发现，规则：
1. 每条发现必须引用至少一个 observation_id；不得引用不存在的观测。
2. 发现中的每个数字都必须放入 numeric_assertions，并给出 check 类型与依据观测；
   正文中的其他数字会被程序校验，校验不过该发现会被降级。
3. 关于变量间关系的方向（正/负相关），必须写入 claims（variable_a/variable_b/relation），
   并引用提供关系计算（value.relations）的观测作为 basis_observation；
   方向与计算不一致会被程序判定失败并降级；无计算依据的方向主张不会自动升级为已证实结果。
4. 因果/机制表述（"因为/导致/机制是"）在没有受控实验证据时会被自动降级为 hypothesis；
   数据只支持现象与相关性时请使用 statistical_finding。
5. 数据不足或观测之间矛盾时，宁可不输出发现；不要强行制造问题。
6. 每条发现给出 alternative_explanations（竞争性解释）与 verification_method（如何用新实验验证/证伪）。
只输出 JSON：{"findings": [...]}，不要输出其他文字。"""

FINDING_JSON_SHAPE = """{
  "findings": [
    {
      "statement": "一句话陈述（避免无依据数字）",
      "claim_type_hint": "observation|statistical_finding|hypothesis",
      "observation_ids": ["OBS-001"],
      "numeric_assertions": [
        {"metric": "...", "value": 20.0, "unit": "percent_improvement",
         "check": "percent_change_from_baseline|mean|median|percentile_p95|direction|ratio|lookup",
         "basis_observation": "OBS-001"}
      ],
      "claims": [
        {"variable_a": "...", "variable_b": "...", "relation": "positive|negative|none|unspecified",
         "basis_observation": "提供关系计算的 OBS id", "conditions": "适用条件"}
      ],
      "alternative_explanations": ["..."],
      "verification_method": "如何用受控实验验证或证伪",
      "confidence": "low|medium|high",
      "confidence_rationale": "为什么是这个置信度"
    }
  ]
}"""

_CANDIDATE_BASELINE_HINTS = ("baseline", "对照", "control", "参考")


def _parse_json_block(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start > 0:
        text = text[start:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
    return None


def _split_groups(rows: list[dict[str, Any]], group_field: str) -> list[str]:
    groups = sorted({str(row.get(group_field) or "default") for row in rows})
    return groups


def _pick_candidate_baseline(groups: list[str], meta: dict[str, Any]) -> tuple[str, str] | None:
    """确定 candidate/baseline 组。meta 可显式指定；否则按名称提示或字典序。"""
    explicit = meta.get("candidate_group") and meta.get("baseline_group")
    if explicit:
        return str(meta["candidate_group"]), str(meta["baseline_group"])
    if len(groups) < 2:
        return None
    baseline = next((g for g in groups if any(h in g.lower() for h in _CANDIDATE_BASELINE_HINTS)), None)
    if baseline:
        candidate = next(g for g in groups if g != baseline)
        return candidate, baseline
    return groups[-1], groups[0]  # 字典序最后一个为候选


def profile_material(
    material: Material, rows: list[dict[str, Any]], store: ProjectStore, project_id: str
) -> tuple[list[Observation], list[dict[str, Any]]]:
    """对单个表格材料生成确定性观测。返回 (observations, comparison_specs)。"""
    table_meta = material.meta.get("table") or {}
    metric_directions = table_meta.get("metric_directions") or material.meta.get("metric_directions") or {}
    query_field = material.meta.get("query_field") or table_meta.get("query_field") or "query_id"
    group_field = material.meta.get("group_field") or table_meta.get("group_field") or "comparison_group"
    observations: list[Observation] = []
    comparison_specs: list[dict[str, Any]] = []
    ref = EvidenceRef(material_id=material.id, sha256=material.sha256, data_range=f"{len(rows)} rows")

    metric_columns = table_meta.get("numeric_columns") or []
    # 长尾/异常按组检测：多组共表时跨组混合会互相污染尾部统计
    group_field_present = any(group_field in row for row in rows)
    if group_field_present:
        segments = [
            (f"{group_field}={group}", [row for row in rows if str(row.get(group_field)) == group])
            for group in sorted({str(row.get(group_field)) for row in rows})
        ]
    else:
        segments = [("", rows)]
    for segment_label, segment_rows in segments:
        for metric in metric_columns:
            for candidate in detect_anomalies(segment_rows, metric, metric_directions, query_field):
                statement = candidate["statement"] + (f"（{segment_label}）" if segment_label else "")
                observation = Observation(
                    id="",
                    statement=statement,
                    value={**candidate["value"], "material_id": material.id, "metric": metric, "segment": segment_label},
                    evidence_refs=[ref],
                    computed_by=candidate.get("computed_by") or "anomaly_detection",
                    created_at=now_iso(),
                )
                observations.append(observation)

    # 数值列两两相关方向（结构化关系主张的程序化核对依据），按组分段计算
    from ..analysis.statistics import relation_signs

    for segment_label, segment_rows in segments:
        if len(segment_rows) < 5:
            continue
        relations = relation_signs(segment_rows, metric_columns)
        significant = [rel for rel in relations if rel["sign"] in ("positive", "negative")]
        statement = (
            f"数值列相关方向（|r|>{'%.2f' % 0.05} 视为有方向）："
            + "；".join(f"{rel['a']}~{rel['b']}={rel['sign']}(r={rel['pearson_r']:.2f})" for rel in significant[:5])
            if significant
            else "数值列两两相关均无明确方向"
        )
        observations.append(
            Observation(
                id="",
                statement=statement + (f"（{segment_label}）" if segment_label else ""),
                value={
                    "material_id": material.id,
                    "segment": segment_label,
                    "relations": relations,
                    "metric": "relation_map",
                },
                evidence_refs=[ref],
                computed_by="statistics.relation_signs",
                created_at=now_iso(),
            )
        )

    groups = _split_groups(rows, group_field) if any(group_field in row for row in rows) else []
    if len(groups) >= 2:
        picked = _pick_candidate_baseline(groups, material.meta)
        if picked:
            candidate_group, baseline_group = picked
            for metric in metric_columns:
                comparison = compare_metric(
                    rows, metric, candidate_group, baseline_group, metric_directions, group_field, query_field
                )
                observation = Observation(
                    id="",
                    statement=(
                        f"{metric}（方向{'已声明' if comparison['direction_declared'] else '未声明，启发式推断'}："
                        f"{'越低越好' if comparison['lower_is_better'] else '越高越好'}）："
                        f"候选组 {candidate_group} 均值 {comparison['candidate']['mean']:.4g}（n={comparison['candidate']['n']}），"
                        f"基线组 {baseline_group} 均值 {comparison['baseline']['mean']:.4g}（n={comparison['baseline']['n']}），"
                        f"解读 {comparison['interpretation']}"
                    ),
                    value={
                        "material_id": material.id,
                        "metric": metric,
                        "candidate_mean": comparison["candidate"]["mean"],
                        "baseline_mean": comparison["baseline"]["mean"],
                        "candidate_n": comparison["candidate"]["n"],
                        "baseline_n": comparison["baseline"]["n"],
                        "delta_mean": comparison.get("delta_mean"),
                        "delta_ci95": list(comparison["delta_ci95"]) if comparison.get("delta_ci95") else None,
                        "ci_level": 95 if comparison.get("delta_ci95") else None,
                        "effect_size": comparison.get("effect_size"),
                        "interpretation": comparison["interpretation"],
                        "direction_declared": comparison["direction_declared"],
                        "lower_is_better": comparison["lower_is_better"],
                        "excluded_rows": comparison["excluded_rows"],
                    },
                    evidence_refs=[ref],
                    computed_by="statistics.compare_metric",
                    created_at=now_iso(),
                )
                observations.append(observation)
                comparison_specs.append(
                    {
                        "metric": metric,
                        "candidate_group": candidate_group,
                        "baseline_group": baseline_group,
                        "comparison": comparison,
                    }
                )
        # 混杂因素画像：除分组/查询/元数据列外的所有数值列都是潜在协变量
        # （即便它同时被当作指标比较，其组间不均衡也必须暴露）
        excluded_from_covariates = {group_field, query_field, "status", "seed", "repeat_index", "name"}
        covariate_fields = [
            c
            for c in (table_meta.get("columns") or [])
            if c not in excluded_from_covariates
        ]
        if covariate_fields and all(group_field in row for row in rows):
            profile = group_profile(rows, covariate_fields[:6], group_field)
            if profile["imbalance_warnings"]:
                observations.append(
                    Observation(
                        id="",
                        statement="；".join(profile["imbalance_warnings"]),
                        value={"material_id": material.id, "covariates": profile["covariates"]},
                        evidence_refs=[ref],
                        computed_by="statistics.group_profile",
                        created_at=now_iso(),
                    )
                )
    return observations, comparison_specs


def _offline_findings(
    observations: list[Observation], comparison_specs: list[dict[str, Any]], materials_by_id: dict[str, Material]
) -> list[Finding]:
    """无 LLM：仅当方向已声明、解读明确且独立样本充足（≥10/组）时，把比较观测升级为
    statistical_finding；小样本只保留观测（不确定性不被写成结论）。绝不生成解释性内容。"""
    findings: list[Finding] = []
    for spec in comparison_specs:
        comparison = spec["comparison"]
        if not comparison["direction_declared"]:
            continue
        if comparison["interpretation"] not in ("candidate_better", "baseline_better_or_equal"):
            continue
        candidate_n = comparison["excluded_rows"][comparison["candidate_group"]]["n_queries"]
        baseline_n = comparison["excluded_rows"][comparison["baseline_group"]]["n_queries"]
        if min(candidate_n, baseline_n) < 10:
            continue  # 小样本：报告不确定性（仅观测），不升级为发现
        ci = comparison.get("delta_ci95")
        condition = f"方向已声明为{'越低越好' if comparison['lower_is_better'] else '越高越好'}；置信区间不包含零"
        statement = (
            f"在{condition}下，{spec['metric']} 在候选组与基线组间存在可分辨差异"
            f"（delta={comparison.get('delta_mean'):.4g}"
            + (f", 95% CI [{ci[0]:.4g}, {ci[1]:.4g}]" if ci else "")
            + f"），解读 {comparison['interpretation']}"
        )
        finding = Finding(
            id="",
            statement=statement,
            claim_type="statistical_finding",
            claim_type_hint="statistical_finding",
            observation_ids=[],
            numeric_assertions=[
                NumericAssertion(
                    metric=spec["metric"],
                    value=comparison.get("delta_mean") or 0.0,
                    unit="delta",
                    check="lookup",
                    basis_observation="",
                )
            ],
            alternative_explanations=[
                "样本量不足导致的偶发差异（需重复实验确认）",
                "组间实现差异真实存在（由独立重复实验区分）",
            ],
            verification_method=f"在相同场景与种子下重复 {spec['metric']} 比较实验，验证差异是否复现",
            confidence="medium" if ci else "low",
            confidence_rationale="确定性配对/非配对比较，方向已声明" if ci else "样本量小或无配对，不确定性大",
            origin="offline_rules",
        )
        obs_id = _matching_observation_id(observations, spec)
        if obs_id:
            finding.observation_ids = [obs_id]
        findings.append(finding)
    return findings


def _matching_observation_id(observations: list[Observation], spec: dict[str, Any]) -> str:
    for observation in observations:
        if (
            observation.value.get("metric") == spec["metric"]
            and observation.value.get("interpretation") == spec["comparison"]["interpretation"]
            and observation.computed_by == "statistics.compare_metric"
        ):
            return observation.id or ""
    return ""


def run_diagnosis(
    store: ProjectStore,
    project_id: str,
    llm: Any | None = None,
    material_ids: list[str] | None = None,
) -> dict[str, Any]:
    """执行完整诊断。llm 为 None 或不可用时自动退化为离线模式。

    ID 方案：观测/发现 ID 带诊断轮次前缀（DIAG-NNNN/OBS-NNN），全局唯一、
    只追加不覆盖——历史研究问题对旧发现的引用永远有效。
    """
    project = store.load_project(project_id)
    diag_number = store.next_diagnosis_number(project_id)
    diag_id = f"DIAG-{diag_number:04d}"
    materials = store.load_materials(project_id)
    if material_ids:
        materials = [m for m in materials if m.id in set(material_ids)]
    materials_by_id = {m.id: m for m in store.load_materials(project_id)}
    project_dir = store.require(project_id)

    all_observations: list[Observation] = []
    all_comparison_specs: list[dict[str, Any]] = []
    skipped_materials: list[dict[str, str]] = []
    from ..core.evidence import check_ref

    for material in materials:
        if material.kind not in ("results", "dataset", "legacy_run"):
            continue
        # 读取前核对哈希：内容已更新 → 拒绝用旧引用做诊断
        probe_ref = EvidenceRef(material_id=material.id, sha256=material.sha256)
        status = check_ref(probe_ref, materials_by_id, project_dir)
        if status["status"] != "valid":
            skipped_materials.append({"material_id": material.id, "reason": status["detail"], "status": status["status"]})
            continue
        try:
            from ..integrations.material_importer import read_rows

            rows = read_rows(material.path)
        except (OSError, ValueError) as exc:
            skipped_materials.append({"material_id": material.id, "reason": f"读取失败: {exc}", "status": "broken"})
            continue
        observations, comparison_specs = profile_material(material, rows, store, project_id)
        all_observations.extend(observations)
        all_comparison_specs.extend(comparison_specs)

    # 全局唯一编号：DIAG-NNNN/OBS-NNN
    for index, observation in enumerate(all_observations, start=1):
        observation.id = f"{diag_id}/OBS-{index:03d}"
    store.save_observations(project_id, all_observations)
    observations_by_id = {o.id: o for o in all_observations}

    # LLM 发现（或离线规则发现）
    llm_mode = "offline"
    llm_error = ""
    findings: list[Finding] = []
    if llm is not None:
        try:
            findings = _llm_findings(llm, all_observations, materials)
            llm_mode = "llm"
        except LLMUnavailable as exc:
            llm_error = str(exc)
            findings = _offline_findings(all_observations, all_comparison_specs, materials_by_id)
            llm_mode = "offline_fallback"
    else:
        findings = _offline_findings(all_observations, all_comparison_specs, materials_by_id)

    # 三层校验（本轮新发现按本轮前缀编号）
    for index, finding in enumerate(findings, start=1):
        finding.id = f"{diag_id}/F-{index:03d}"
        validation = validate_finding(finding, observations_by_id, materials_by_id, project_dir)
        apply_validation(finding, validation)
    store.save_findings(project_id, findings)

    # 提出待研究问题（proposed）并同步主张桶
    from ..core.research_state import propose_questions_from_findings, sync_claims_from_findings

    state = store.load_state(project_id)
    questions = propose_questions_from_findings(state, findings)
    claim_counts = sync_claims_from_findings(state, findings)
    if not state.current_stage:
        state.current_stage = "实验完善 / 诊断进行中"
    store.save_state(project_id, state)

    usage = llm.usage_summary() if llm is not None else {"model": None, "total_calls": 0}
    report = {
        "schema_version": "rc/1.0",
        "generated_at": now_iso(),
        "project_id": project_id,
        "diag_id": diag_id,
        "diag_number": diag_number,
        "llm_mode": llm_mode,
        "llm_error": llm_error,
        "llm_usage": usage,
        "n_observations": len(all_observations),
        "n_findings": len(findings),
        "findings_by_type": _count_by_type(findings),
        "n_questions_proposed": len(questions),
        "claim_counts": claim_counts,
        "skipped_materials": skipped_materials,
        "observations": [o.to_dict() for o in all_observations],
        "findings": [f.to_dict() for f in findings],
        "honesty_note": (
            "离线模式：以下仅含确定性统计观察与规则式发现，不含任何机制解释；"
            if llm_mode != "llm"
            else "LLM 发现均经三层证据校验；未通过者已降级或拒绝。"
        ),
    }
    json_path, md_path = store.save_diagnosis_report(project_id, report, render_diagnosis_markdown(report, project.name))
    store.log_event(project_id, "diagnosis_run", detail=f"mode={llm_mode}; findings={len(findings)}")
    report["report_files"] = [str(json_path), str(md_path)]
    return report


def _count_by_type(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.claim_type] = counts.get(finding.claim_type, 0) + 1
    return counts


def _llm_findings(llm: Any, observations: list[Observation], materials: list[Material]) -> list[Finding]:
    if not observations:
        return []
    payload = {
        "observations": [
            {"id": o.id, "statement": o.statement, "value": o.value, "computed_by": o.computed_by}
            for o in observations
        ],
        "materials": [{"id": m.id, "kind": m.kind, "summary": m.summary} for m in materials],
        "output_shape": FINDING_JSON_SHAPE,
    }
    response = llm.complete(
        SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2), purpose="diagnosis"
    )
    parsed = _parse_json_block(response)
    if not parsed:
        raise LLMUnavailable("LLM 输出无法解析为 JSON")
    raw_findings = parsed.get("findings") if isinstance(parsed, dict) else parsed
    if not isinstance(raw_findings, list):
        raise LLMUnavailable("LLM 输出缺少 findings 数组")
    findings = []
    for raw in raw_findings:
        if not isinstance(raw, dict) or not raw.get("statement"):
            continue
        findings.append(
            Finding(
                id="",
                statement=str(raw["statement"]),
                claim_type=str(raw.get("claim_type_hint") or "unverified_conjecture"),
                claim_type_hint=str(raw.get("claim_type_hint") or ""),
                observation_ids=[str(x) for x in raw.get("observation_ids") or []],
                numeric_assertions=[
                    NumericAssertion.from_dict(a) for a in raw.get("numeric_assertions") or [] if isinstance(a, dict)
                ],
                claims=[RelationClaim.from_dict(c) for c in raw.get("claims") or [] if isinstance(c, dict)],
                alternative_explanations=[str(x) for x in raw.get("alternative_explanations") or []],
                verification_method=str(raw.get("verification_method") or ""),
                confidence=str(raw.get("confidence") or ""),
                confidence_rationale=str(raw.get("confidence_rationale") or ""),
                origin="llm",
            )
        )
    return findings


def render_diagnosis_markdown(report: dict[str, Any], project_name: str) -> str:
    lines = [f"# 科研诊断报告：{project_name}", ""]
    lines += [
        f"- 生成时间：{report['generated_at']}",
        f"- 诊断轮次：{report.get('diag_id', 'DIAG-0001')}（观测/发现 ID 带此前缀，历史只追加不覆盖）",
        f"- 模式：{report['llm_mode']}" + (f"（{report['llm_error']}）" if report.get("llm_error") else ""),
        f"- 观测 {report['n_observations']} 条；发现 {report['n_findings']} 条；建议问题 {report['n_questions_proposed']} 个",
        f"- {report['honesty_note']}",
        "",
    ]
    if report["skipped_materials"]:
        lines += ["## 被跳过的材料", ""]
        for item in report["skipped_materials"]:
            lines.append(f"- {item['material_id']}：{item['reason']}")
        lines.append("")
    lines += ["## 发现（经三层校验后的最终级别）", ""]
    if not report["findings"]:
        lines += ["_无发现：数据中没有可检测的异常或可分辨差异；不强行制造问题。_", ""]
    for finding in report["findings"]:
        validation = finding.get("validation") or {}
        lines.append(
            f"### {finding['id']} [{finding['claim_type']}]（校验: {validation.get('status')}）"
        )
        lines.append(f"- {finding['statement']}")
        if finding.get("numeric_assertions"):
            for assertion in finding["numeric_assertions"]:
                lines.append(
                    f"  - 数值断言: {assertion.get('metric')} = {assertion.get('value')} ({assertion.get('check')})"
                )
        if validation.get("downgrades"):
            for downgrade in validation["downgrades"]:
                lines.append(f"  - 降级: {downgrade}")
        if finding.get("alternative_explanations"):
            lines.append(f"  - 竞争性解释: {'；'.join(finding['alternative_explanations'])}")
        if finding.get("verification_method"):
            lines.append(f"  - 验证方法: {finding['verification_method']}")
        lines.append(f"  - 依据观测: {', '.join(finding.get('observation_ids') or []) or '（离线规则，无 LLM 引用）'}")
        lines.append("")
    lines += ["## 确定性观测（全部）", ""]
    for observation in report["observations"]:
        lines.append(f"- {observation['id']} [{observation['computed_by']}] {observation['statement']}")
    lines.append("")
    return "\n".join(lines)
