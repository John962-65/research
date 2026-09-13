"""Import existing code/results entry (T09 / 任务书 §5 T09).

"我已有代码和实验结果，帮我检查是否足以支持结论"：允许把已有结果/契约/
预注册导入一个 run 目录，生成字段映射、来源与缺失项清单，不强迫重新生成
idea 或重写论文。导入不改变证据语义：04-results 按白名单与来源绑定校验，
evidence 状态由 evidence_integrity 独立评估；缺失字段按 unknown/incomplete
处理，不自动补成已验证。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import read_json, safe_int as _safe_int, utc_now as _utc_now, write_json
from .evidence_integrity import assess_evidence_integrity


IMPORT_REPORT_JSON = "00-import-report.json"

# 现有字段 → 冻结四类状态的映射（decision-contract §1.1/§1.2）。
_EXECUTION_MAP = {
    "passed": "completed",
    "failed": "failed",
    "timeout": "timed_out",
    "blocked": "blocked",
    "cancelled": "cancelled",
    "simulated": "simulated",
}


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def import_existing_results(
    run_dir: Path,
    results_source: Path | str,
    *,
    contract_source: Path | str | None = None,
    preregistration_source: Path | str | None = None,
    replace: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """导入已有结果（必需）与契约/预注册（可选），写入导入报告。"""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "imported_at": _utc_now(),
        "notes": str(notes or ""),
        "imported_files": [],
        "field_mapping": [],
        "missing_fields": [],
        "warnings": [],
        "result_summary": {},
    }

    rows = _load_results(results_source, report)
    if rows is None:
        report["warnings"].append("结果导入失败：04-results.json 未写入。")
        write_json(run_dir / IMPORT_REPORT_JSON, report)
        return report

    existing_path = run_dir / "04-results.json"
    if existing_path.exists() and not replace:
        report["warnings"].append(
            "run 目录已有 04-results.json；未写入新结果（replace=false）。如确需覆盖请显式 replace=true。"
        )
        report["result_summary"] = _summarize(rows)
        write_json(run_dir / IMPORT_REPORT_JSON, report)
        return report
    write_json(existing_path, rows)
    report["imported_files"].append(
        {
            "path": "04-results.json",
            "source": str(results_source),
            "source_sha256": _sha256_file(Path(results_source)) if isinstance(results_source, (str, Path)) else None,
            "action": "replaced" if existing_path.exists() else "created",
        }
    )
    report["field_mapping"] = _field_mapping(rows)
    report["missing_fields"] = _missing_fields(rows)
    report["result_summary"] = _summarize(rows)

    for key, source, target in (
        ("contract", contract_source, "03-idea-experiment-contract.json"),
        ("preregistration", preregistration_source, "03-preregistration.json"),
    ):
        if source is None:
            report["missing_fields"].append(
                f"{key}: 未提供；将按 unknown 处理，不自动补成已批准/已锁定。"
            )
            continue
        if isinstance(source, dict):
            payload = source
            source_desc = f"inline:{key}"
            source_sha = None
        elif isinstance(source, str) and source.strip().startswith("{"):
            try:
                payload = json.loads(source)
            except ValueError:
                payload = None
            source_desc = f"inline-json:{key}"
            source_sha = None
        else:
            payload = _load_json_file(Path(source))
            source_desc = str(source)
            source_sha = _sha256_file(Path(source))
        if payload is None:
            report["warnings"].append(f"{key} 导入失败：{source_desc} 不是可读 JSON。")
            continue
        write_json(run_dir / target, payload)
        report["imported_files"].append(
            {"path": target, "source": source_desc, "source_sha256": source_sha, "action": "created"}
        )

    integrity = assess_evidence_integrity(run_dir)
    report["evidence_assessment"] = {
        "llm_evidence_status": integrity.llm_evidence_status,
        "experiment_evidence_status": integrity.experiment_evidence_status,
        "research_outcome_note": "研究结论需在契约判据与统计比较完成后评估；导入本身不产生结论。",
        "next_step": (
            "导入完成：请核对 00-import-report 的缺失项，补齐后从 checkpoint 恢复执行分析/决策阶段。"
            if not report["missing_fields"]
            else "导入完成但存在缺失项：按 00-import-report 逐项补齐材料。"
        ),
    }
    write_json(run_dir / IMPORT_REPORT_JSON, report)
    return report


def _load_results(source: Path | str, report: dict[str, Any]) -> list[dict[str, Any]] | None:
    if isinstance(source, (str, Path)):
        payload = _load_json_file(Path(source))
        if payload is None:
            report["warnings"].append(f"结果文件不可读或不是 JSON：{source}")
            return None
    else:
        payload = source
    rows = payload if isinstance(payload, list) else (payload or {}).get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        report["warnings"].append("结果必须是非空数组（或含 results 数组的对象）。")
        return None
    cleaned: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            report["warnings"].append(f"第 {index} 行缺少 name 字段，已跳过。")
            continue
        cleaned.append(row)
    if not cleaned:
        report["warnings"].append("没有可用的结果行（全部缺少 name）。")
        return None
    return cleaned


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _field_mapping(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: list[dict[str, Any]] = []
    for row in rows[:50]:
        raw_status = str(row.get("status") or "").strip().lower()
        mapping.append(
            {
                "name": str(row.get("name")),
                "raw_status": raw_status,
                "execution_status": _EXECUTION_MAP.get(raw_status, "unknown（按 blocked+incomplete 处理）"),
                "usable_as_evidence": raw_status == "passed",
            }
        )
    return mapping


def _missing_fields(rows: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if any(not row.get("metrics") for row in rows):
        missing.append("metrics: 部分行缺少指标，证据将判 incomplete。")
    if any(not row.get("artifact_records") and row.get("returncode") is None for row in rows):
        missing.append("artifact_records/returncode: 部分行缺少来源绑定，证据将判 incomplete。")
    if any(not row.get("seed") for row in rows):
        missing.append("seed: 部分行缺少随机种子记录。")
    if any(not row.get("command") for row in rows):
        missing.append("command: 部分行缺少执行命令记录。")
    return missing


def evaluate_imported_results(run_dir: Path) -> dict[str, Any]:
    """复审第 7 项：导入后的完整用户路径——

    导入已有结果 → 补齐/核对比较条件 → 生成统计、结果验证、实验后决策
    （读取契约主指标）与假设结论 → 输出定位到的问题与下一步动作。
    不调用模型、不重新生成 idea：分析完全基于导入与已有材料。
    """
    from .artifacts import write_json as _write_json, write_text as _write_text
    from .config import ExecutionConfig
    from .evidence_integrity import write_evidence_integrity_artifacts
    from .experiment_decision import write_experiment_decision_artifacts
    from .hypothesis_outcome import write_hypothesis_outcome_artifacts
    from .models import ExperimentCommand, ExperimentPlan, ExperimentResult, ResearchIdea, ResearchPlan
    from .result_validation import write_result_validation_artifacts
    from .statistics import build_statistics_report

    run_dir = Path(run_dir)
    report: dict[str, Any] = {"schema_version": 1, "run_dir": str(run_dir), "steps": [], "blockers": [], "next_actions": []}
    rows_payload = _load_json_file(run_dir / "04-results.json")
    rows = rows_payload if isinstance(rows_payload, list) else []
    rows = [row for row in rows if isinstance(row, dict) and str(row.get("name") or "").strip()]
    if not rows:
        report["blockers"].append("04-results.json 缺失或没有可用结果行：请先运行 import-existing 导入结果。")
        report["next_actions"].append("用 import-existing 导入已有结果后重试 evaluate-imported。")
        write_json(run_dir / IMPORT_REPORT_JSON, {**(_load_json_file(run_dir / IMPORT_REPORT_JSON) or {}), "evaluate": report})
        return report
    report["steps"].append(f"读取导入结果 {len(rows)} 行")

    plan = _imported_plan(rows, run_dir)
    report["steps"].append(
        f"比较条件：candidate={sum(1 for c in plan.commands if c.comparison_group == 'candidate')}"
        f" baseline={sum(1 for c in plan.commands if c.comparison_group == 'baseline')}"
        f" ablation={sum(1 for c in plan.commands if c.comparison_group == 'ablation')}"
    )
    results = [
        ExperimentResult(
            name=str(row.get("name")),
            status=str(row.get("status") or "unknown"),
            metrics=row.get("metrics") or {},
            artifacts=row.get("artifacts") or [],
            stdout=str(row.get("stdout") or ""),
            stderr=str(row.get("stderr") or ""),
            repeat_index=_safe_int(row.get("repeat_index")),
            seed=str(row.get("seed") or ""),
            command=row.get("command") or [],
            returncode=row.get("returncode"),
            duration_seconds=row.get("duration_seconds"),
            comparison_group=str(row.get("comparison_group") or "default"),
            adapter_id=str(row.get("adapter_id") or ""),
            artifact_records=row.get("artifact_records") or [],
            validation_issues=row.get("validation_issues") or [],
        )
        for row in rows
    ]
    statistics = build_statistics_report(plan, results)
    _write_json(run_dir / "04-statistics.json", statistics)
    report["steps"].append(f"统计比较 {len(statistics.comparisons)} 项")

    prereg = _load_json_file(run_dir / "03-preregistration.json") or {}
    contract_report = _load_json_file(run_dir / "03-idea-experiment-contract.json") or {}
    contract = contract_report.get("contract") if isinstance(contract_report.get("contract"), dict) else None
    binding = None
    runbook = _load_json_file(run_dir / "04-experiment-runbook.json")
    if isinstance(runbook, dict) and isinstance(runbook.get("contract_binding"), dict):
        binding = runbook["contract_binding"]
    result_validation = write_result_validation_artifacts(
        plan,
        results,
        statistics,
        run_dir,
        expected_repeats=max(1, max((_safe_int(row.get("repeat_index")) or 0) for row in rows) + 1),
        preregistration=prereg or None,
        execution_mode="imported",
    )
    # 复审第 9 轮第 2 项：失败/模拟计数复用真实失败分析模块（从原始结果
    # 统计），不再固定为零——否则全部 simulated 的导入会被当成真实比较。
    from .failure_analysis import build_failure_analysis_report

    failure_analysis = build_failure_analysis_report(plan, results, statistics, result_validation)
    integrity = write_evidence_integrity_artifacts(str(prereg.get("topic") or plan.idea_title), run_dir)
    decision = write_experiment_decision_artifacts(
        plan,
        statistics,
        result_validation,
        failure_analysis,
        run_dir,
        execution_mode="imported",
        contract=contract,
        experiment_evidence_status=integrity.experiment_evidence_status,
    )
    idea = _imported_idea(plan, prereg, contract)
    write_hypothesis_outcome_artifacts(
        idea, plan, statistics, result_validation, failure_analysis, decision, run_dir, execution_mode="imported",
    )
    states = decision.get("decision_states") if isinstance(decision.get("decision_states"), dict) else {}
    report["decision"] = decision.get("decision")
    report["decision_states"] = states
    report["blockers"] = [
        str(item)
        for item in result_validation.get("blocking_issues", [])
        if str(item).strip()
    ]
    if not statistics.comparisons:
        groups = {str(row.get("comparison_group") or "default") for row in rows}
        if len(groups) > 1:
            report["blockers"].append(
                "结果包含多个 comparison_group（数据集/任务/划分身份）："
                + "、".join(sorted(groups)[:5])
                + "；不同组之间不进入同一个统计比较。请明确映射或补齐同一数据集的 candidate/baseline 对照。"
            )
        else:
            report["blockers"].append("没有 candidate/baseline 可比较项：需要补齐另一侧的执行结果（比较条件不完整）。")
    report["next_actions"] = [str(item) for item in decision.get("next_actions", [])]
    report["evidence"] = {
        "llm": integrity.llm_evidence_status,
        "experiment": integrity.experiment_evidence_status,
    }
    merged = _load_json_file(run_dir / IMPORT_REPORT_JSON) or {}
    merged["evaluate"] = report
    write_json(run_dir / IMPORT_REPORT_JSON, merged)
    return report


_RESULT_FIELDS = (
    "name", "status", "metrics", "artifacts", "stdout", "stderr", "repeat_index",
    "seed", "command", "returncode", "duration_seconds", "comparison_group",
    "adapter_id", "artifact_records", "validation_issues",
)


def _imported_plan(rows: list[dict[str, Any]], run_dir: Path) -> "ExperimentPlan":
    """优先使用已导入/已有的 03-experiment-plan；否则从结果行构造最小计划。"""
    from .models import ExperimentCommand, ExperimentPlan

    stored = _load_json_file(run_dir / "03-experiment-plan.json")
    if isinstance(stored, dict) and stored.get("commands"):
        try:
            from .models import ExperimentPlan as _Plan

            return _Plan(
                idea_title=str(stored.get("idea_title") or ""),
                objective=str(stored.get("objective") or ""),
                variables=[str(v) for v in (stored.get("variables") or [])],
                metrics=[str(m) for m in (stored.get("metrics") or [])],
                protocol=[str(p) for p in (stored.get("protocol") or [])],
                commands=[ExperimentCommand(**c) for c in (stored.get("commands") or []) if isinstance(c, dict)],
                baseline=str(stored.get("baseline") or ""),
                evidence_keys=[str(k) for k in (stored.get("evidence_keys") or [])],
            )
        except TypeError:
            pass
    metrics: list[str] = []
    names: list[str] = []
    commands: list[ExperimentCommand] = []
    baseline = ""
    # 复审第 9 轮第 1 项：comparison_group 是数据集/任务/划分身份，必须
    # 逐条保留——不同 comparison_group 的结果不得进入同一个统计比较。
    # candidate 与 baseline 是否可配对由统计模块的池化拒绝逻辑判定；
    # 分组缺失（无 comparison_group）时要求明确映射（见 evaluate blockers）。
    name_groups: dict[str, str] = {}
    for row in rows:
        name = str(row.get("name"))
        group = str(row.get("comparison_group") or "")
        if name in name_groups and name_groups[name] != group:
            raise ValueError(
                f"结果行 {name} 带有多种 comparison_group（{name_groups[name]} vs {group}）："
                "同一命令的数据集/划分身份不一致，请先明确映射。"
            )
        name_groups.setdefault(name, group)
    for row in rows:
        name = str(row.get("name"))
        if name not in names:
            names.append(name)
            role = _infer_group(name) or name
            if role == "baseline" and not baseline:
                baseline = name
            command = row.get("command")
            commands.append(
                ExperimentCommand(
                    name=name,
                    command=[str(part) for part in command] if isinstance(command, list) else [name],
                    role=role,
                    comparison_group=name_groups[name] or "default",
                )
            )
        for key in (row.get("metrics") or {}):
            if str(key) not in metrics:
                metrics.append(str(key))
    title = "导入结果的比较分析"
    return ExperimentPlan(
        idea_title=title,
        objective="基于导入的已有实验结果重建统计比较与决策（不重新执行实验）。",
        variables=["method_role"],
        metrics=metrics,
        protocol=["导入结果核对", "统计比较", "契约判据映射"],
        commands=commands,
        baseline=baseline,
        evidence_keys=[],
    )


def _imported_idea(plan: "ExperimentPlan", prereg: dict[str, Any], contract: dict[str, Any] | None) -> "ResearchIdea":
    from .models import ResearchIdea

    hypothesis = str((prereg or {}).get("primary_hypothesis") or "")
    if not hypothesis and isinstance((contract or {}).get("hypothesis"), dict):
        hypothesis = str(contract["hypothesis"].get("question") or "")
    return ResearchIdea(
        title=plan.idea_title,
        hypothesis=hypothesis or "由导入材料与契约判据评估。",
        mechanism="导入路径：不做机制声明。",
        expected_contribution="对已有结果的可复查评审。",
        novelty=2,
        feasibility=5,
        risk=1,
        evaluation=plan.metrics,
        evidence_keys=[],
        baseline=plan.baseline,
    )


def _infer_group(name: str) -> str:
    lowered = str(name or "").lower()
    if any(token in lowered for token in ("candidate", "artifact", "proposed")):
        return "candidate"
    if any(token in lowered for token in ("baseline", "control")):
        return "baseline"
    if any(token in lowered for token in ("ablation", "without", "ablated")):
        return "ablation"
    return ""


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {"total": len(rows), "status_counts": counts}
