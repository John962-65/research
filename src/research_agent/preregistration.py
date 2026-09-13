from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import read_json, safe_int as _safe_int, write_json, write_text
from .models import ExperimentPlan, ResearchIdea


PREREGISTRATION_JSON = "03-preregistration.json"
PREREGISTRATION_MD = "03-preregistration.md"
PREREGISTRATION_HISTORY_JSON = "03-preregistration-history.json"


def write_preregistration_artifacts(
    topic: str,
    idea: ResearchIdea,
    plan: ExperimentPlan,
    run_dir: Path,
    *,
    results_exist: bool = False,
) -> dict[str, Any]:
    report = build_preregistration_report(topic, idea, plan, results_exist=results_exist)
    _versioned_write(run_dir, report)
    write_text(run_dir / PREREGISTRATION_MD, render_preregistration_markdown(report))
    return report


def _versioned_write(run_dir: Path, report: dict[str, Any]) -> None:
    """T05：预注册版本化——不再就地覆盖；计划指纹变化时旧版本进入历史。"""
    path = run_dir / PREREGISTRATION_JSON
    previous: dict[str, Any] | None = None
    try:
        data = read_json(path)
        if isinstance(data, dict) and data.get("plan_fingerprint"):
            previous = data
    except (OSError, ValueError):
        previous = None
    revision = 1
    history_entries: list[dict[str, Any]] = []
    history_path = run_dir / PREREGISTRATION_HISTORY_JSON
    try:
        history = read_json(history_path)
        if isinstance(history, dict) and isinstance(history.get("entries"), list):
            history_entries = history["entries"]
    except (OSError, ValueError):
        history_entries = []
    if previous is not None and str(previous.get("plan_fingerprint")) == str(report.get("plan_fingerprint")):
        revision = max(1, _safe_int(previous.get("revision")) or 1)
    else:
        if previous is not None:
            history_entries.append(
                {
                    "revision": max(1, _safe_int(previous.get("revision")) or len(history_entries) + 1),
                    "superseded_at": datetime.now(timezone.utc).isoformat(),
                    "plan_fingerprint": previous.get("plan_fingerprint"),
                    "primary_metrics": previous.get("primary_metrics"),
                    "status": previous.get("status"),
                    "note": "计划指纹变化，旧预注册保留为历史版本；新版本为新的分析身份。",
                }
            )
        revision = len(history_entries) + 1
    report["revision"] = revision
    write_json(history_path, {"schema_version": 1, "entries": history_entries})
    write_json(path, report)


def build_preregistration_report(
    topic: str,
    idea: ResearchIdea,
    plan: ExperimentPlan,
    *,
    results_exist: bool = False,
) -> dict[str, Any]:
    primary_metrics = [metric for metric in plan.metrics[:2] if metric]
    secondary_metrics = [metric for metric in plan.metrics[2:] if metric]
    command_names = [command.name for command in plan.commands]
    blocking: list[str] = []
    warnings: list[str] = []
    if not primary_metrics:
        blocking.append("实验计划没有可锁定的 primary metrics。")
    if not _has_command(command_names, {"candidate", "artifact", "proposed"}):
        blocking.append("实验计划缺少 candidate/proposed 命令。")
    if not _has_command(command_names, {"baseline", "control"}):
        blocking.append("实验计划缺少 baseline/control 命令。")
    if not _has_command(command_names, {"ablation", "without", "ablated"}):
        warnings.append("预注册时未发现 ablation 命令，核心机制贡献只能作为未充分验证结论。")
    if not idea.evidence_keys:
        warnings.append("选中 idea 没有显式 evidence_keys，预注册结论需保留文献证据局限。")
    timing = "posthoc_checkpoint" if results_exist else "before_results"
    if results_exist:
        warnings.append("该预注册是在已有实验结果之后补写的，只能作为事后审计，不应称为严格预注册。")
    status = "block" if blocking else "posthoc" if results_exist else "locked"
    fingerprint = plan_fingerprint(plan)
    return {
        "topic": topic,
        "idea_title": idea.title,
        "status": status,
        "timing": timing,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "plan_fingerprint": fingerprint,
        "template_profile": plan.template_profile,
        "primary_hypothesis": idea.hypothesis,
        "primary_metrics": primary_metrics,
        "secondary_metrics": secondary_metrics,
        "planned_comparisons": _planned_comparisons(command_names),
        "analysis_rules": _analysis_rules(primary_metrics),
        "exclusion_rules": [
            "只排除 runbook 中状态为 failed、blocked 或 timeout 的重复结果，并在结果验证中报告。",
            "不得因为结果方向不符合预期而删除重复结果、指标或失败案例。",
        ],
        "stopping_rules": [
            "默认运行配置中的 repeats 是最小重复次数；若结果验证为 block，必须修复后重跑。",
            "新增真实 benchmark 后应重新生成预注册并保留旧版本在 run manifest 中。",
        ],
        "claim_boundaries": [
            "论文主要结论只能围绕 primary metrics、candidate-vs-baseline 和预先声明的 ablation 展开。",
            "secondary metrics 只能作为探索性或机制解释，不得升级为主要贡献。",
            "如果 timing 为 posthoc_checkpoint，论文必须声明指标和分析规则不是严格预注册。",
        ],
        "commands": command_names,
        "blocking_issues": blocking,
        "warnings": warnings,
    }


def render_preregistration_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 实验预注册：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 时序：{report.get('timing') or '-'}",
        f"- 计划指纹：`{report.get('plan_fingerprint') or '-'}`",
        f"- 模板：{report.get('template_profile') or '-'}",
        "",
        "## Primary Hypothesis",
        str(report.get("primary_hypothesis") or "-"),
        "",
        "## Primary Metrics",
    ]
    primary = report.get("primary_metrics") if isinstance(report.get("primary_metrics"), list) else []
    lines.extend(f"- {item}" for item in primary) if primary else lines.append("- 未声明")
    secondary = report.get("secondary_metrics") if isinstance(report.get("secondary_metrics"), list) else []
    if secondary:
        lines.extend(["", "## Secondary Metrics"])
        lines.extend(f"- {item}" for item in secondary)
    for key, title in [
        ("planned_comparisons", "计划比较"),
        ("analysis_rules", "分析规则"),
        ("exclusion_rules", "排除规则"),
        ("stopping_rules", "停止规则"),
        ("claim_boundaries", "结论边界"),
        ("blocking_issues", "阻断问题"),
        ("warnings", "警告"),
    ]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend(["", f"## {title}"])
            lines.extend(f"- {item}" for item in values)
    return "\n".join(lines)


def plan_fingerprint(plan: ExperimentPlan) -> str:
    payload = {
        "idea_title": plan.idea_title,
        "objective": plan.objective,
        "variables": plan.variables,
        "metrics": plan.metrics,
        "protocol": plan.protocol,
        "commands": [asdict(command) for command in plan.commands],
        "baseline": plan.baseline,
        "template_profile": plan.template_profile,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _planned_comparisons(command_names: list[str]) -> list[str]:
    comparisons = ["candidate_vs_baseline"]
    if _has_command(command_names, {"ablation", "without", "ablated"}):
        comparisons.append("candidate_vs_ablation")
    return comparisons


def _analysis_rules(primary_metrics: list[str]) -> list[str]:
    metrics = ", ".join(primary_metrics) if primary_metrics else "未声明 primary metrics"
    return [
        f"优先报告 primary metrics：{metrics}。",
        "使用 04-statistics 中的均值、差值、95% CI 和效应量作为主分析依据。",
        "若 95% CI 跨过 0，结论应降级为不确定或需要更多重复实验。",
    ]


def _has_command(command_names: list[str], tokens: set[str]) -> bool:
    return any(any(token in name.lower() for token in tokens) for name in command_names)
