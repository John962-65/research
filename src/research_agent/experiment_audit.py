from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExperimentPlan, ResearchPlan


EXPERIMENT_AUDIT_JSON = "03-experiment-audit.json"
EXPERIMENT_AUDIT_MD = "03-experiment-audit.md"


def write_experiment_audit_artifacts(
    research_plan: ResearchPlan,
    plan: ExperimentPlan,
    run_dir: Path,
    *,
    literature_coverage: dict[str, Any] | None = None,
    novelty_audit: dict[str, Any] | None = None,
    ablation_plan: dict[str, Any] | None = None,
    preregistration: dict[str, Any] | None = None,
    constraint_compliance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_experiment_audit_report(
        research_plan,
        plan,
        literature_coverage=literature_coverage,
        novelty_audit=novelty_audit,
        ablation_plan=ablation_plan,
        preregistration=preregistration,
        constraint_compliance=constraint_compliance,
    )
    write_json(run_dir / EXPERIMENT_AUDIT_JSON, report)
    write_text(run_dir / EXPERIMENT_AUDIT_MD, render_experiment_audit_markdown(report))
    return report


def build_experiment_audit_report(
    research_plan: ResearchPlan,
    plan: ExperimentPlan,
    *,
    literature_coverage: dict[str, Any] | None = None,
    novelty_audit: dict[str, Any] | None = None,
    ablation_plan: dict[str, Any] | None = None,
    preregistration: dict[str, Any] | None = None,
    constraint_compliance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    blocking: list[str] = []
    warnings: list[str] = []
    _check_baseline_alignment(research_plan, plan, items, blocking, warnings)
    _check_metric_alignment(research_plan, plan, items, blocking, warnings)
    _check_command_structure(plan, items, blocking)
    _check_evidence(plan, items, warnings)
    _check_literature_coverage(literature_coverage or {}, items, blocking, warnings)
    if novelty_audit is not None:
        _check_novelty(novelty_audit, plan, items, blocking, warnings)
    _check_ablation(ablation_plan or {}, items, blocking, warnings)
    _check_preregistration(preregistration or {}, items, blocking, warnings)
    _check_review_constraint_compliance(constraint_compliance or {}, items, blocking, warnings)
    status = "block" if blocking else "warn" if warnings else "pass"
    return {
        "idea_title": plan.idea_title,
        "status": status,
        "template_profile": plan.template_profile,
        "blocking_issues": blocking,
        "warnings": warnings,
        "items": items,
        "required_actions": _required_actions(blocking, warnings),
    }


def render_experiment_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 实验计划审计：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 实验模板：{report.get('template_profile') or '-'}",
        f"- 阻断问题：{len(report.get('blocking_issues', []) if isinstance(report.get('blocking_issues'), list) else [])}",
        f"- 警告：{len(report.get('warnings', []) if isinstance(report.get('warnings'), list) else [])}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("warnings", "警告"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(["## 检查项", "| 检查 | 状态 | 详情 |", "| --- | --- | --- |"])
    for item in report.get("items", []):
        if isinstance(item, dict):
            lines.append(f"| {_cell(str(item.get('name') or ''))} | {_cell(str(item.get('status') or ''))} | {_cell(str(item.get('detail') or ''))} |")
    return "\n".join(lines)


def _check_baseline_alignment(
    research_plan: ResearchPlan,
    plan: ExperimentPlan,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    baseline = plan.baseline.strip()
    if not baseline:
        detail = "实验计划没有声明 baseline。"
        items.append({"name": "baseline_alignment", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    if _is_generic(baseline):
        detail = f"baseline 仍是泛化占位：{baseline}"
        items.append({"name": "baseline_alignment", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    matched = _matched_terms(baseline, research_plan.baselines)
    if matched:
        items.append({"name": "baseline_alignment", "status": "pass", "detail": "matched " + ", ".join(matched[:5])})
        return
    detail = "baseline 与 00-research-plan 中的建议 baseline 没有明显重合。"
    items.append({"name": "baseline_alignment", "status": "warn", "detail": detail})
    warnings.append(detail)


def _check_metric_alignment(
    research_plan: ResearchPlan,
    plan: ExperimentPlan,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    metrics = [metric for metric in plan.metrics if metric.strip()]
    if len(metrics) < 2:
        detail = "实验计划少于 2 个可量化指标。"
        items.append({"name": "metric_alignment", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    matched = _matched_terms(" ".join(metrics), research_plan.metrics)
    if matched:
        items.append({"name": "metric_alignment", "status": "pass", "detail": "matched " + ", ".join(matched[:6])})
        return
    detail = "实验指标与 00-research-plan 中的领域指标没有明显重合。"
    items.append({"name": "metric_alignment", "status": "warn", "detail": detail})
    warnings.append(detail)


def _check_command_structure(plan: ExperimentPlan, items: list[dict[str, Any]], blocking: list[str]) -> None:
    names = [command.name for command in plan.commands]
    missing = []
    if not any(_has_token(name, {"candidate", "artifact", "proposed"}) for name in names):
        missing.append("candidate/proposed")
    if not any(_has_token(name, {"baseline", "control"}) for name in names):
        missing.append("baseline/control")
    if not any(_has_token(name, {"ablation", "without", "ablated"}) for name in names):
        missing.append("ablation")
    if missing:
        detail = "实验命令缺少：" + ", ".join(missing)
        items.append({"name": "command_structure", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    items.append({"name": "command_structure", "status": "pass", "detail": f"{len(names)} commands include candidate/baseline/ablation"})


def _check_evidence(plan: ExperimentPlan, items: list[dict[str, Any]], warnings: list[str]) -> None:
    if plan.evidence_keys:
        items.append({"name": "evidence_keys", "status": "pass", "detail": f"{len(plan.evidence_keys)} evidence keys"})
        return
    detail = "实验计划没有 evidence_keys，后续论文结论应保留人工补证要求。"
    items.append({"name": "evidence_keys", "status": "warn", "detail": detail})
    warnings.append(detail)


def _check_literature_coverage(
    coverage: dict[str, Any],
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    status = str(coverage.get("status") or "")
    ratio = coverage.get("coverage_ratio")
    if status == "block":
        detail = f"文献覆盖审计未通过：{status}"
        items.append({"name": "literature_coverage", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    if status in {"needs_literature", "needs_coverage"}:
        detail = f"文献覆盖仍有缺口，coverage_ratio={ratio}"
        items.append({"name": "literature_coverage", "status": "warn", "detail": detail})
        warnings.append(detail)
        return
    if status == "pass":
        items.append({"name": "literature_coverage", "status": "pass", "detail": f"coverage_ratio={ratio}"})
        return
    detail = "缺少 01-literature-coverage 审计，无法确认 baseline/benchmark 文献覆盖。"
    items.append({"name": "literature_coverage", "status": "warn", "detail": detail})
    warnings.append(detail)


def _check_novelty(
    novelty: dict[str, Any],
    plan: ExperimentPlan,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    item = _novelty_item(novelty, plan.idea_title)
    if not item:
        detail = "缺少选中 idea 的 02-novelty-audit 记录，无法确认实验不是复述已有文献。"
        items.append({"name": "selected_idea_novelty", "status": "warn", "detail": detail})
        warnings.append(detail)
        return
    decision = str(item.get("decision") or "")
    risk = _safe_float(item.get("duplicate_risk"))
    closest = item.get("closest_paper") if isinstance(item.get("closest_paper"), dict) else {}
    closest_title = str(closest.get("title") or "-")
    if decision == "likely_duplicate":
        detail = f"选中 idea 高重复风险 duplicate_risk={risk:.3f}，最相似文献：{closest_title}"
        items.append({"name": "selected_idea_novelty", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    if decision == "review_required":
        detail = f"选中 idea novelty 边界需人工复核 duplicate_risk={risk:.3f}，最相似文献：{closest_title}"
        items.append({"name": "selected_idea_novelty", "status": "warn", "detail": detail})
        warnings.append(detail)
        return
    items.append({"name": "selected_idea_novelty", "status": "pass", "detail": f"{decision or 'unknown'} duplicate_risk={risk:.3f}"})


def _check_ablation(
    ablation: dict[str, Any],
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    status = str(ablation.get("status") or "")
    if status == "block":
        detail = "消融计划存在阻断问题。"
        items.append({"name": "ablation_plan", "status": "block", "detail": detail})
        blocking.append(detail)
    elif status == "needs_ablation":
        detail = "消融计划未通过，核心机制贡献不能支撑。"
        items.append({"name": "ablation_plan", "status": "warn", "detail": detail})
        warnings.append(detail)
    elif status == "pass":
        items.append({"name": "ablation_plan", "status": "pass", "detail": "ablation command planned"})
    else:
        detail = "缺少 03-ablation-plan。"
        items.append({"name": "ablation_plan", "status": "warn", "detail": detail})
        warnings.append(detail)


def _check_preregistration(
    preregistration: dict[str, Any],
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    status = str(preregistration.get("status") or "")
    if status == "block":
        detail = "预注册存在阻断问题。"
        items.append({"name": "preregistration", "status": "block", "detail": detail})
        blocking.append(detail)
    elif status == "posthoc":
        detail = "预注册是在已有结果之后补写的 posthoc checkpoint。"
        items.append({"name": "preregistration", "status": "warn", "detail": detail})
        warnings.append(detail)
    elif status == "locked":
        items.append({"name": "preregistration", "status": "pass", "detail": "analysis plan locked"})
    else:
        detail = "缺少 03-preregistration。"
        items.append({"name": "preregistration", "status": "warn", "detail": detail})
        warnings.append(detail)


def _check_review_constraint_compliance(
    compliance: dict[str, Any],
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    status = str(compliance.get("status") or "")
    blocked = int(compliance.get("blocked") or 0)
    review_required = int(compliance.get("review_required") or 0)
    if status == "block" or blocked:
        first_issue = _first_text(compliance.get("blocking_issues"))
        detail = f"人工审核约束未落实，blocked={blocked}。" + (f" {first_issue}" if first_issue else "")
        items.append({"name": "review_constraint_compliance", "status": "block", "detail": detail})
        blocking.append(detail)
    elif status == "review_required" or review_required:
        first_task = _first_text(compliance.get("manual_tasks"))
        detail = f"人工审核约束需复核，review_required={review_required}。" + (f" {first_task}" if first_task else "")
        items.append({"name": "review_constraint_compliance", "status": "warn", "detail": detail})
        warnings.append(detail)
    elif status == "pass":
        items.append({"name": "review_constraint_compliance", "status": "pass", "detail": f"checked={compliance.get('checked_constraints', 0)}"})
    else:
        detail = "缺少 03-review-constraint-compliance。"
        items.append({"name": "review_constraint_compliance", "status": "warn", "detail": detail})
        warnings.append(detail)


def _required_actions(blocking: list[str], warnings: list[str]) -> list[str]:
    if blocking:
        return ["修复阻断项后再执行实验；不要用当前计划生成结果或论文结论。"]
    if warnings:
        return ["可继续 smoke run，但论文中必须标注实验计划局限，并优先修复警告项。"]
    return ["实验计划已通过结构审计，可以进入 benchmark/local/simulated 执行。"]


def _first_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        text = str(item).strip()
        if text:
            return text
    return ""


def _matched_terms(text: str, candidates: list[str]) -> list[str]:
    lowered = _normalize(text)
    matches: list[str] = []
    for candidate in candidates:
        tokens = _tokens(candidate)
        if any(token in lowered for token in tokens):
            matches.append(candidate)
    return matches


def _tokens(value: str) -> list[str]:
    lowered = _normalize(value.replace("*", " star"))
    return [token for token in lowered.split() if len(token) >= 3]


def _normalize(value: str) -> str:
    return value.lower().replace("-", " ").replace("_", " ")


def _is_generic(value: str) -> bool:
    lowered = value.lower()
    markers = ["待人工", "最相关", "传统 baseline", "strong baseline", "relevant baseline", "现有方法"]
    return any(marker in lowered for marker in markers)


def _has_token(value: str, tokens: set[str]) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in tokens)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _novelty_item(novelty: dict[str, Any], title: str) -> dict[str, Any]:
    for item in novelty.get("items", []) if isinstance(novelty.get("items"), list) else []:
        if isinstance(item, dict) and str(item.get("idea_title") or "") == title:
            return item
    return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
