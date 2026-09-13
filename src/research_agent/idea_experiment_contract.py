from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import read_json, write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now
from .config import ExecutionConfig
from .evidence_snapshot import payload_sha256
from .models import ExplorationMap, ExperimentPlan, ResearchIdea, ResearchPlan


IDEA_EXPERIMENT_CONTRACT_JSON = "03-idea-experiment-contract.json"
IDEA_EXPERIMENT_CONTRACT_MD = "03-idea-experiment-contract.md"
CONTRACT_HISTORY_JSON = "03-experiment-contract-history.json"
CONTRACT_SCHEMA_VERSION = 2


def write_idea_experiment_contract_artifacts(
    research_plan: ResearchPlan,
    selected_idea: ResearchIdea,
    exploration_map: ExplorationMap,
    experiment_plan: ExperimentPlan,
    benchmark_readiness: dict[str, Any] | None,
    execution_config: ExecutionConfig,
    run_dir: Path,
    *,
    ablation_plan: dict[str, Any] | None = None,
    preregistration: dict[str, Any] | None = None,
    constraint_compliance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_idea_experiment_contract_report(
        research_plan,
        selected_idea,
        exploration_map,
        experiment_plan,
        benchmark_readiness or {},
        execution_config,
        ablation_plan=ablation_plan or {},
        preregistration=preregistration or {},
        constraint_compliance=constraint_compliance or {},
    )
    write_json(run_dir / IDEA_EXPERIMENT_CONTRACT_JSON, report)
    write_text(run_dir / IDEA_EXPERIMENT_CONTRACT_MD, render_idea_experiment_contract_markdown(report))
    return report


def read_json_local(path: Path) -> Any:
    return read_json(path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(value or "")).strip("-").lower()
    return slug[:40]


def _infer_group(name: str) -> str:
    lowered = str(name or "").lower()
    if any(token in lowered for token in ("candidate", "artifact", "proposed")):
        return "candidate"
    if any(token in lowered for token in ("baseline", "control")):
        return "baseline"
    if any(token in lowered for token in ("ablation", "without", "ablated")):
        return "ablation"
    return ""


def build_execution_contract(
    research_plan: ResearchPlan,
    selected_idea: ResearchIdea,
    experiment_plan: ExperimentPlan,
    execution_config: ExecutionConfig,
    *,
    preregistration: dict[str, Any] | None = None,
    ablation_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """任务书 T05：执行与评估共同读取的权威结构化契约（八字段组）。

    idea 自然语言只用于解释，不重复执行细节；契约冻结后修改必须产生新版本
    并说明原因、受影响结果与是否需要重跑。
    """
    prereg = preregistration or {}
    ablation = ablation_plan or {}
    primary_metrics = [str(item) for item in (prereg.get("primary_metrics") or experiment_plan.metrics[:2]) if str(item).strip()]
    secondary_metrics = [str(item) for item in (prereg.get("secondary_metrics") or experiment_plan.metrics[2:]) if str(item).strip()]
    commands = [
        {
            "name": command.name,
            "command": list(command.command),
            "comparison_group": str(command.comparison_group or "") or _infer_group(command.name),
        }
        for command in experiment_plan.commands
    ]
    has_ablation = any(item["comparison_group"] == "ablation" for item in commands)
    fingerprint = str(prereg.get("plan_fingerprint") or "")
    data_block: dict[str, Any] = {
        "mode": execution_config.mode,
        "benchmark_manifests": list(execution_config.benchmark_manifest_paths),
    }
    if execution_config.mode in {"local", "benchmark"} and not execution_config.benchmark_manifest_paths:
        data_block["reason"] = "本地固定输入执行，未使用外部数据划分；数据标识由实验命令与环境快照绑定。"
    contract = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": "",
        "revision": 0,
        "frozen": True,
        "frozen_at": "",
        "hypothesis": {
            "hypothesis_id": _slug(selected_idea.title) or "hypothesis",
            "question": str(selected_idea.hypothesis or ""),
            "task_boundary": str(experiment_plan.objective or ""),
        },
        "method": {
            "candidate": str(experiment_plan.idea_title or selected_idea.title or ""),
            "baseline": str(experiment_plan.baseline or selected_idea.baseline or ""),
            "plan_fingerprint": fingerprint,
            "allowed_changes": "仅允许修改候选实现与其实验命令；baseline、数据与主指标冻结，改动必须生成新契约版本。",
        },
        "data": data_block,
        "evaluation": {
            "primary_metrics": primary_metrics,
            "secondary_metrics": secondary_metrics,
            "direction": "candidate_better",
            "computation": "04-statistics 的均值差与 95% CI（candidate - baseline）",
            "comparison_unit": "candidate_vs_baseline",
            "repeats": max(1, int(execution_config.repeats)),
            "seed_policy": "由执行器按 repeat 序号派生固定种子，记录在 04-experiment-runbook。",
        },
        "criteria": {
            "supported": "至少一个 primary metric 的均值差 95% CI 不跨 0 且方向为 candidate_better，且结果验证无阻断。",
            "not_supported": "primary metric 的均值差 95% CI 明确偏负（baseline 更优）；此时输出准确负结果，不自动改写或搜索正结果。",
            "inconclusive": "CI 跨 0、存在未检验 primary metric 或结果验证为 warn；不得把未显著简单等同无效。",
        },
        "verification": {
            "has_ablation": has_ablation,
            "ablation_commands": [item["name"] for item in commands if item["comparison_group"] == "ablation"],
            "expected": "ablation（移除核心机制）相对 candidate 的表现应当变差；若不变差，机制贡献声明必须降级。",
            "not_applicable_note": "" if has_ablation else str(ablation.get("required_actions") or ["本契约未声明 ablation；机制贡献只能作为未验证解释，不进入主要结论。"][0]) ,
        },
        "execution": {
            "mode": execution_config.mode,
            "commands": commands,
            "timeout_seconds": int(execution_config.timeout_seconds),
            "repeats": max(1, int(execution_config.repeats)),
            "allowed_commands": list(execution_config.allowed_commands),
            "stopping_rules": [str(item) for item in (prereg.get("stopping_rules") or [])],
        },
        "approvals": [],
    }
    contract["contract_id"] = f"contract-{payload_sha256({'topic': research_plan.topic, 'plan_fingerprint': fingerprint, 'evaluation': contract['evaluation'], 'method': contract['method']})[:12]}"
    contract["digest"] = _contract_content_digest(contract)
    return contract


def _contract_content_digest(contract: dict[str, Any]) -> str:
    """内容摘要：排除 revision/frozen_at/approvals 等过程字段，专用于版本比较。"""
    payload = {key: value for key, value in contract.items() if key not in {"revision", "frozen_at", "approvals", "digest"}}
    return payload_sha256(payload)


def append_contract_history(
    run_dir: Path,
    contract: dict[str, Any],
    *,
    results_exist: bool = False,
) -> dict[str, Any]:
    """冻结/版本化：内容变化时追加新版本，说明原因、影响与是否需要重跑。"""
    path = Path(run_dir) / CONTRACT_HISTORY_JSON
    try:
        history = read_json_local(path)
    except (OSError, ValueError):
        history = None
    entries = history.get("entries") if isinstance(history, dict) else None
    if not isinstance(entries, list):
        entries = []
    digest = str(contract.get("digest") or "")
    if entries and str(entries[-1].get("digest") or "") == digest:
        contract["revision"] = int(entries[-1].get("revision") or len(entries))
        return history if isinstance(history, dict) else {"schema_version": 1, "entries": entries}
    revision = len(entries) + 1
    contract["revision"] = revision
    if not contract.get("frozen_at"):
        contract["frozen_at"] = _utc_now_local()
    reason = "initial_freeze" if revision == 1 else "post_results_change" if results_exist else "contract_revised"
    affected = "实验尚未执行，无受影响结果。" if not results_exist else (
        "已有结果基于旧契约版本；旧批准与分析身份不再沿用，重新执行比较前必须人工确认。"
    )
    entry = {
        "revision": revision,
        "frozen_at": contract.get("frozen_at"),
        "digest": digest,
        "contract_id": contract.get("contract_id"),
        "reason": reason,
        "rerun_required": results_exist,
        "affected_results": affected,
    }
    entries.append(entry)
    write_json(path, {"schema_version": 1, "entries": entries})
    return {"schema_version": 1, "entries": entries}


def load_contract_history(run_dir: Path) -> dict[str, Any]:
    try:
        history = read_json_local(Path(run_dir) / CONTRACT_HISTORY_JSON)
    except (OSError, ValueError):
        return {"schema_version": 1, "entries": []}
    return history if isinstance(history, dict) and isinstance(history.get("entries"), list) else {"schema_version": 1, "entries": []}


def build_idea_experiment_contract_report(
    research_plan: ResearchPlan,
    selected_idea: ResearchIdea,
    exploration_map: ExplorationMap,
    experiment_plan: ExperimentPlan,
    benchmark_readiness: dict[str, Any],
    execution_config: ExecutionConfig,
    *,
    ablation_plan: dict[str, Any] | None = None,
    preregistration: dict[str, Any] | None = None,
    constraint_compliance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = [
        _selected_idea_alignment(selected_idea, exploration_map, experiment_plan),
        _evidence_carryover(selected_idea, experiment_plan),
        _baseline_carryover(research_plan, selected_idea, experiment_plan),
        _metric_contract(research_plan, selected_idea, experiment_plan, benchmark_readiness),
        _command_contract(experiment_plan),
        _benchmark_contract(benchmark_readiness, execution_config),
        _pre_experiment_lock(preregistration or {}),
        _ablation_contract(ablation_plan or {}),
        _human_constraint_contract(constraint_compliance or {}),
    ]
    blocking = _unique(action for check in checks if check["status"] == "block" for action in check["required_actions"])
    manual = _unique(action for check in checks if check["status"] == "review_required" for action in check["required_actions"])
    status = "block" if blocking else "review_required" if manual else "pass"
    score = sum(_check_weight(str(check.get("status") or "")) for check in checks) / max(1, len(checks))
    contract = build_execution_contract(
        research_plan,
        selected_idea,
        experiment_plan,
        execution_config,
        preregistration=preregistration,
        ablation_plan=ablation_plan,
    )
    return {
        "topic": research_plan.topic,
        "status": status,
        "contract_score": round(score, 3),
        "selected_idea_title": selected_idea.title,
        "exploration_selected_title": exploration_map.selected_idea_title,
        "experiment_plan_title": experiment_plan.idea_title,
        "execution_mode": execution_config.mode,
        "contract": contract,
        "contract_digest": contract.get("digest") or "",
        "checks": checks,
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "required_actions": _required_actions(status, blocking, manual),
    }


def render_idea_experiment_contract_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Idea-实验契约：{report.get('selected_idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 契约分：{float(report.get('contract_score') or 0.0):.3f}",
        f"- 执行模式：{report.get('execution_mode') or '-'}",
        f"- 选中 idea：{report.get('selected_idea_title') or '-'}",
        f"- 探索图选中：{report.get('exploration_selected_title') or '-'}",
        f"- 实验计划标题：{report.get('experiment_plan_title') or '-'}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("manual_tasks", "人工待办"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.extend([f"## {title}"])
        lines.extend(f"- [ ] {item}" for item in values) if values else lines.append("- 无")
        lines.append("")
    lines.extend(["## 契约检查", "| 检查 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- |"])
    for check in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if not isinstance(check, dict):
            continue
        evidence = "；".join(str(item) for item in check.get("evidence", []) if str(item).strip()) or "-"
        actions = "；".join(str(item) for item in check.get("required_actions", []) if str(item).strip()) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(check.get("name") or "")),
                    _cell(str(check.get("status") or "")),
                    _cell(evidence),
                    _cell(actions),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _selected_idea_alignment(selected_idea: ResearchIdea, exploration_map: ExplorationMap, plan: ExperimentPlan) -> dict[str, Any]:
    expected = _normalize_title(selected_idea.title)
    exploration = _normalize_title(exploration_map.selected_idea_title)
    actual = _normalize_title(plan.idea_title)
    if expected and actual == expected and (not exploration or exploration == expected):
        return _check("selected_idea_alignment", "pass", [f"idea={selected_idea.title}", f"plan={plan.idea_title}"], [])
    return _check(
        "selected_idea_alignment",
        "block",
        [f"idea={selected_idea.title or '-'}", f"exploration={exploration_map.selected_idea_title or '-'}", f"plan={plan.idea_title or '-'}"],
        ["实验计划标题必须与 02-exploration-map 选中的 idea 一致，避免错跑其他 idea。"],
    )


def _evidence_carryover(selected_idea: ResearchIdea, plan: ExperimentPlan) -> dict[str, Any]:
    idea_keys = _clean_values(selected_idea.evidence_keys)
    plan_keys = _clean_values(plan.evidence_keys)
    overlap = sorted(set(idea_keys) & set(plan_keys))
    if idea_keys and overlap:
        return _check("evidence_carryover", "pass", [f"idea_evidence={len(idea_keys)}", f"plan_evidence={len(plan_keys)}", f"overlap={len(overlap)}"], [])
    if idea_keys and plan_keys:
        return _check(
            "evidence_carryover",
            "review_required",
            [f"idea_evidence={len(idea_keys)}", f"plan_evidence={len(plan_keys)}", "overlap=0"],
            ["把选中 idea 的 evidence_keys 带入 03-experiment-plan，或人工说明替换证据链。"],
        )
    if idea_keys:
        return _check(
            "evidence_carryover",
            "review_required",
            [f"idea_evidence={len(idea_keys)}", "plan_evidence=0"],
            ["在 03-experiment-plan.json 补齐从选中 idea 继承的 evidence_keys。"],
        )
    return _check(
        "evidence_carryover",
        "block",
        ["idea_evidence=0", f"plan_evidence={len(plan_keys)}"],
        ["选中 idea 没有 evidence_keys，必须先回到文献/idea 阶段补证据再进入实验。"],
    )


def _baseline_carryover(research_plan: ResearchPlan, selected_idea: ResearchIdea, plan: ExperimentPlan) -> dict[str, Any]:
    baseline = str(plan.baseline or "").strip()
    if not baseline or _is_generic(baseline):
        return _check("baseline_carryover", "block", [f"plan_baseline={baseline or '-'}"], ["03-experiment-plan 必须声明具体 baseline，不能使用泛化占位。"])
    expected_terms = _terms([selected_idea.baseline, *research_plan.baselines])
    plan_terms = _terms([baseline])
    overlap = sorted(expected_terms & plan_terms)
    if overlap:
        return _check("baseline_carryover", "pass", [f"overlap={', '.join(overlap[:6])}", f"plan_baseline={baseline}"], [])
    return _check(
        "baseline_carryover",
        "review_required",
        [f"expected_terms={len(expected_terms)}", f"plan_terms={len(plan_terms)}", "overlap=0"],
        ["让实验 baseline 与选中 idea 或 00-research-plan 的 baseline 对齐，或写明等价映射。"],
    )


def _metric_contract(
    research_plan: ResearchPlan,
    selected_idea: ResearchIdea,
    plan: ExperimentPlan,
    benchmark_readiness: dict[str, Any],
) -> dict[str, Any]:
    metrics = _clean_values(plan.metrics)
    if len(metrics) < 2:
        return _check("metric_contract", "block", [f"plan_metrics={len(metrics)}"], ["实验计划至少需要 2 个可量化指标。"])
    expected_terms = _terms([*research_plan.metrics, *selected_idea.evaluation])
    plan_terms = _terms(metrics)
    readiness_terms = _terms(_benchmark_check_evidence(benchmark_readiness, "metric_alignment"))
    overlap = sorted(plan_terms & (expected_terms | readiness_terms))
    if overlap:
        return _check("metric_contract", "pass", [f"plan_metrics={len(metrics)}", f"overlap={', '.join(overlap[:8])}"], [])
    return _check(
        "metric_contract",
        "review_required",
        [f"plan_metrics={len(metrics)}", f"expected_terms={len(expected_terms)}", "overlap=0"],
        ["让 03-experiment-plan metrics 与 idea evaluation、research plan 或 benchmark expected metrics 至少共享一个核心指标。"],
    )


def _command_contract(plan: ExperimentPlan) -> dict[str, Any]:
    texts = [" ".join([command.name, *command.command, *command.expected_artifacts]) for command in plan.commands]
    # A11：命令带显式 comparison_group（机器可读契约字段）时优先采用，
    # 不因命令名未重复关键词而误拦。
    explicit_groups = {
        str(command.comparison_group or "").strip().lower()
        for command in plan.commands
        if str(command.comparison_group or "").strip().lower() in {"candidate", "baseline", "ablation"}
    }
    missing_blockers: list[str] = []
    missing_manual: list[str] = []
    if "candidate" not in explicit_groups and not _has_token(texts, {"candidate", "artifact", "proposed"}):
        missing_blockers.append("candidate/proposed")
    if "baseline" not in explicit_groups and not _has_token(texts, {"baseline", "control"}):
        missing_blockers.append("baseline/control")
    if "ablation" not in explicit_groups and not _has_token(texts, {"ablation", "without", "ablated"}):
        missing_manual.append("ablation")
    if missing_blockers:
        return _check("command_contract", "block", [f"commands={len(texts)}", "missing=" + ", ".join(missing_blockers + missing_manual)], ["补齐 candidate/proposed 与 baseline/control 命令后再申请执行。"])
    if missing_manual:
        return _check("command_contract", "review_required", [f"commands={len(texts)}", "missing=ablation"], ["补齐 ablation 命令，或人工确认该实验只支持非机制性结论。"])
    return _check("command_contract", "pass", [f"commands={len(texts)}", "candidate/baseline/ablation present"], [])


def _benchmark_contract(benchmark_readiness: dict[str, Any], execution_config: ExecutionConfig) -> dict[str, Any]:
    status = str(benchmark_readiness.get("status") or "")
    mode = str(execution_config.mode or "")
    blockers = _clean_values(benchmark_readiness.get("blocking_issues", []))
    manual = _clean_values(benchmark_readiness.get("manual_tasks", []))
    if status == "block" or blockers:
        return _check("benchmark_contract", "block", [f"readiness={status or '-'}", f"mode={mode or '-'}"], blockers or ["修复 03-benchmark-readiness 阻断项后再进入实验执行。"])
    if mode in {"simulated", "local"} or status == "needs_benchmark_upgrade" or manual:
        actions = manual[:3] or ["当前实验模式不足以支撑正式 benchmark claim；需要人工确认降级声明或升级到 benchmark manifest。"]
        return _check("benchmark_contract", "review_required", [f"readiness={status or '-'}", f"mode={mode or '-'}"], actions)
    return _check("benchmark_contract", "pass", [f"readiness={status or '-'}", f"mode={mode or '-'}"], [])


def _pre_experiment_lock(preregistration: dict[str, Any]) -> dict[str, Any]:
    status = str(preregistration.get("status") or "")
    timing = str(preregistration.get("timing") or "")
    blockers = _clean_values(preregistration.get("blocking_issues", []))
    warnings = _clean_values(preregistration.get("warnings", []))
    if status == "block" or blockers:
        return _check("pre_experiment_lock", "block", [f"preregistration={status or '-'}", f"timing={timing or '-'}"], blockers or ["修复 03-preregistration 阻断项。"])
    if status == "locked" and timing in {"", "before_results"}:
        return _check("pre_experiment_lock", "pass", [f"preregistration={status}", f"timing={timing or 'before_results'}"], [])
    return _check(
        "pre_experiment_lock",
        "review_required",
        [f"preregistration={status or '-'}", f"timing={timing or '-'}"],
        warnings[:3] or ["生成 before_results 的 03-preregistration，或人工声明当前为事后审计。"],
    )


def _ablation_contract(ablation_plan: dict[str, Any]) -> dict[str, Any]:
    status = str(ablation_plan.get("status") or "")
    blockers = _clean_values(ablation_plan.get("blocking_issues", []))
    actions = _clean_values(ablation_plan.get("required_actions", []))
    if status == "block" or blockers:
        return _check("ablation_contract", "block", [f"ablation={status or '-'}"], blockers or ["修复 03-ablation-plan 阻断项。"])
    if status == "pass" and ablation_plan.get("has_ablation") is not False:
        return _check("ablation_contract", "pass", [f"ablation={status}", "has_ablation=yes"], [])
    return _check("ablation_contract", "review_required", [f"ablation={status or '-'}"], actions[:3] or ["补齐 ablation 或人工降级机制贡献声明。"])


def _human_constraint_contract(compliance: dict[str, Any]) -> dict[str, Any]:
    status = str(compliance.get("status") or "")
    blocked = _safe_int(compliance.get("blocked"))
    review_required = _safe_int(compliance.get("review_required"))
    blockers = _clean_values(compliance.get("blocking_issues", []))
    manual = _clean_values(compliance.get("manual_tasks", []))
    if status == "block" or blocked or blockers:
        return _check("human_constraint_contract", "block", [f"status={status or '-'}", f"blocked={blocked}"], blockers or ["落实人工审核约束后再进入实验。"])
    if status == "review_required" or review_required or manual:
        return _check("human_constraint_contract", "review_required", [f"status={status or '-'}", f"review_required={review_required}"], manual[:3] or ["人工确认 review constraints 已落实。"])
    return _check("human_constraint_contract", "pass", [f"status={status or 'pass'}"], [])


def _check(name: str, status: str, evidence: list[str], actions: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "evidence": [item for item in evidence if str(item).strip()],
        "required_actions": _unique(actions),
    }


def _required_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "pass":
        return ["契约通过：允许进入执行审批或后续实验阶段。"]
    if status == "block":
        return ["先修复 idea->experiment 契约阻断项，再重新生成实验计划。", *blocking[:4]]
    return ["人工确认契约待办，必要时补齐证据、baseline、metric、ablation 或 benchmark manifest。", *manual[:4]]


def _benchmark_check_evidence(report: dict[str, Any], name: str) -> list[str]:
    checks = report.get("checks", []) if isinstance(report.get("checks"), list) else []
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            evidence = check.get("evidence", []) if isinstance(check.get("evidence"), list) else []
            return [str(item) for item in evidence]
    return []


def _check_weight(status: str) -> float:
    return {"pass": 1.0, "review_required": 0.55, "block": 0.0}.get(status, 0.0)


def _terms(values: list[Any]) -> set[str]:
    terms: set[str] = set()
    aliases = {"rrt*": "rrt", "rrt_star": "rrt", "runtime": "planning_time", "time": "planning_time"}
    for value in values:
        for match in re.findall(r"[A-Za-z][A-Za-z0-9_*.-]{1,}|[\u4e00-\u9fff]{2,}", str(value).lower()):
            normalized = match.replace("-", "_").replace(".", "_")
            terms.add(aliases.get(normalized, normalized))
    return terms


def _has_token(values: list[str], tokens: set[str]) -> bool:
    return any(token in str(value).lower() for value in values for token in tokens)


def _clean_values(values: Any) -> list[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, tuple):
        return [str(value).strip() for value in values if str(value).strip()]
    value = str(values or "").strip()
    return [value] if value else []


def _is_generic(value: str) -> bool:
    lower = value.lower()
    generic = {"baseline", "control", "sota", "state of the art", "相关 baseline", "最相关 baseline", "基线", "对照方法"}
    return lower in generic or any(term in lower for term in {"todo", "tbd", "placeholder"})


def _normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result


