from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .models import ExperimentPlan, ResearchIdea


ABLATION_PLAN_JSON = "03-ablation-plan.json"
ABLATION_PLAN_MD = "03-ablation-plan.md"


def write_ablation_plan_artifacts(idea: ResearchIdea, plan: ExperimentPlan, run_dir: Path) -> dict[str, Any]:
    report = build_ablation_plan(idea, plan)
    write_json(run_dir / ABLATION_PLAN_JSON, report)
    write_text(run_dir / ABLATION_PLAN_MD, render_ablation_plan_markdown(report))
    return report


def build_ablation_plan(idea: ResearchIdea, plan: ExperimentPlan) -> dict[str, Any]:
    command_names = [command.name for command in plan.commands]
    has_candidate = any(_has_token(name, {"candidate", "artifact", "proposed"}) for name in command_names)
    has_baseline = any(_has_token(name, {"baseline", "control"}) for name in command_names)
    has_ablation = any(_has_token(name, {"ablation", "without", "ablated"}) for name in command_names)
    variants = _suggested_variants(plan.template_profile, idea, plan)
    blocking: list[str] = []
    warnings: list[str] = []
    if not has_candidate:
        blocking.append("缺少 candidate/proposed 命令，无法验证候选方案。")
    if not has_baseline:
        blocking.append("缺少 baseline/control 命令，无法公平比较。")
    if not has_ablation:
        warnings.append("缺少 ablation 命令；当前论文结论应避免声称核心机制已被消融验证。")
    status = "block" if blocking else "pass" if has_ablation else "needs_ablation"
    return {
        "idea_title": idea.title,
        "status": status,
        "template_profile": plan.template_profile,
        "has_candidate": has_candidate,
        "has_baseline": has_baseline,
        "has_ablation": has_ablation,
        "commands": command_names,
        "suggested_variants": variants,
        "blocking_issues": blocking,
        "warnings": warnings,
        "required_actions": _required_actions(status, variants),
    }


def render_ablation_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 消融计划：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 实验模板：{report.get('template_profile') or '-'}",
        f"- Candidate 命令：{'yes' if report.get('has_candidate') else 'no'}",
        f"- Baseline 命令：{'yes' if report.get('has_baseline') else 'no'}",
        f"- Ablation 命令：{'yes' if report.get('has_ablation') else 'no'}",
        "",
    ]
    for section, title in [("blocking_issues", "阻断问题"), ("warnings", "警告"), ("required_actions", "必要动作")]:
        values = report.get(section) if isinstance(report.get(section), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(
        [
            "## 命令覆盖",
            "| 类型 | 状态 |",
            "| --- | --- |",
            f"| candidate | {'yes' if report.get('has_candidate') else 'no'} |",
            f"| baseline | {'yes' if report.get('has_baseline') else 'no'} |",
            f"| ablation | {'yes' if report.get('has_ablation') else 'no'} |",
            "",
            "## 建议消融变体",
            "| 名称 | 目的 | 指标 |",
            "| --- | --- | --- |",
        ]
    )
    variants = report.get("suggested_variants") if isinstance(report.get("suggested_variants"), list) else []
    if not variants:
        lines.append("| - | 当前模板没有生成建议消融。 | - |")
    for item in variants:
        if isinstance(item, dict):
            lines.append(f"| {_cell(str(item.get('name') or ''))} | {_cell(str(item.get('purpose') or ''))} | {_cell(', '.join(str(v) for v in item.get('metrics', []) if str(v).strip()))} |")
    return "\n".join(lines)


def _suggested_variants(template_profile: str, idea: ResearchIdea, plan: ExperimentPlan) -> list[dict[str, Any]]:
    if template_profile == "robotics_motion_planning":
        return [
            {"name": "without_trajectory_smoothing", "purpose": "验证轨迹平滑机制是否贡献路径质量。", "metrics": ["trajectory_smoothness", "path_length", "planning_time"]},
            {"name": "without_collision_margin", "purpose": "验证安全距离/碰撞约束是否贡献可执行性。", "metrics": ["collision_rate", "minimum_clearance", "planning_success_rate"]},
        ]
    if template_profile == "bearing_fault_diagnosis":
        return [
            {"name": "without_domain_adaptation", "purpose": "验证跨工况泛化模块是否贡献性能。", "metrics": ["cross_domain_accuracy", "macro_f1"]},
            {"name": "without_noise_augmentation", "purpose": "验证噪声鲁棒性增强是否有效。", "metrics": ["noise_robustness", "accuracy"]},
        ]
    if template_profile == "ai_research_agents":
        return [
            {"name": "without_human_gate", "purpose": "验证人工审核 gate 对引用和结果质量的贡献。", "metrics": ["citation_precision", "unsupported_claims", "review_revision_count"]},
            {"name": "without_rag_grounding", "purpose": "验证文献 grounding 对论文主张支持的贡献。", "metrics": ["unsupported_claims", "artifact_completeness"]},
        ]
    first_metric = plan.metrics[0] if plan.metrics else "success_rate"
    return [
        {"name": "without_core_mechanism", "purpose": f"验证核心机制是否支撑 hypothesis：{idea.hypothesis}", "metrics": [first_metric]},
    ]


def _required_actions(status: str, variants: list[dict[str, Any]]) -> list[str]:
    if status == "pass":
        return ["在论文结果部分单独报告 ablation 与 candidate/baseline 的差异。"]
    if status == "needs_ablation":
        return ["实现至少一个 ablation 命令，并把产物写入 experiments/ 目录。"]
    return ["先补齐 candidate 和 baseline 命令，再设计 ablation。"]


def _has_token(value: str, tokens: set[str]) -> bool:
    lower = value.lower()
    return any(token in lower for token in tokens)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
