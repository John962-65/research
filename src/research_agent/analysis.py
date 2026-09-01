from __future__ import annotations

from .models import Analysis, ExperimentResult, StatisticsReport


METRIC_LABELS = {
    "name": "实验名称",
    "status": "状态",
    "repeat_index": "重复编号",
    "reproduction_success_rate": "复现成功率",
    "artifact_completeness": "产物完整度",
    "audit_minutes": "审计耗时（分钟）",
    "unsupported_claims": "无依据主张数",
}


def analyze_results(results: list[ExperimentResult], statistics: StatisticsReport | None = None, execution_mode: str = "") -> Analysis:
    metric_table = []
    for result in results:
        row: dict[str, str | float] = {
            "name": result.name,
            "status": result.status,
            "repeat_index": result.repeat_index,
            "duration_seconds": result.duration_seconds,
        }
        row.update(result.metrics)
        metric_table.append(row)
    findings = _derive_statistical_findings(statistics) if statistics is not None else _derive_findings(results)
    mode = execution_mode or _infer_execution_mode(results)
    limitations = _limitations(mode)
    next_steps = _next_steps(mode)
    return Analysis(
        headline=findings[0] if findings else "目前还没有形成决定性结论。",
        metric_table=metric_table,
        findings=findings,
        limitations=limitations,
        next_steps=next_steps,
    )


def analysis_matches_execution_mode(analysis: Analysis, execution_mode: str) -> bool:
    text = "\n".join([*analysis.limitations, *analysis.next_steps])
    if execution_mode == "benchmark" and "模拟数据" in text:
        return False
    if execution_mode == "simulated" and "真实 benchmark adapter" in text:
        return False
    return True


def _infer_execution_mode(results: list[ExperimentResult]) -> str:
    if any(result.status == "simulated" for result in results):
        return "simulated"
    if any("benchmark-adapters/" in artifact for result in results for artifact in result.artifacts):
        return "benchmark"
    return "local"


def _limitations(mode: str) -> list[str]:
    common = [
        "统计审计采用近似正态置信区间；真实实验应使用适合指标分布的统计检验。",
        "benchmark 规模仍小，需要加入更多任务、更多随机种子和公开数据集。",
    ]
    if mode == "benchmark":
        return [
            "当前真实 benchmark adapter 已执行，但 Iris smoke 任务规模很小，只能支撑 benchmark provenance、manifest 合约和流程诊断类结论。",
            *common,
        ]
    if mode == "local":
        return [
            "当前为本地脚本执行结果；若要声明外部 benchmark 结论，需要补公开任务来源、下载方式、许可证和引用要求。",
            *common,
        ]
    return [
        "默认运行使用模拟数据，不能直接作为真实科学结论，需要替换为领域实验后再声明贡献。",
        *common,
    ]


def _next_steps(mode: str) -> list[str]:
    common = [
        "增加重复试验数量，报告置信区间、效应量和失败案例。",
        "把论文中的每个关键主张映射到实验产物或文献引用。",
    ]
    if mode == "benchmark":
        return [
            "扩展到更多公开 benchmark 任务，并保留 candidate/baseline/ablation manifest 合约。",
            *common,
        ]
    if mode == "local":
        return [
            "补齐真实 loader、baseline runner、metrics exporter 与公开 benchmark provenance。",
            *common,
        ]
    return [
        "把模拟实验替换为领域专用实验脚本。",
        *common,
    ]


def render_analysis_markdown(analysis: Analysis) -> str:
    lines = ["# 结果分析", "", f"**核心结论：** {analysis.headline}", "", "## 指标表"]
    if analysis.metric_table:
        keys = list(analysis.metric_table[0].keys())
        labels = [METRIC_LABELS.get(key, key) for key in keys]
        lines.append("| " + " | ".join(labels) + " |")
        lines.append("| " + " | ".join("---" for _ in keys) + " |")
        for row in analysis.metric_table:
            lines.append("| " + " | ".join(str(row.get(key, "")) for key in keys) + " |")
    else:
        lines.append("本次运行没有产生结构化指标。")
    lines.extend(["", "## 主要发现"])
    lines.extend(f"- {finding}" for finding in analysis.findings)
    lines.extend(["", "## 局限性"])
    lines.extend(f"- {limitation}" for limitation in analysis.limitations)
    lines.extend(["", "## 下一步"])
    lines.extend(f"- {step}" for step in analysis.next_steps)
    return "\n".join(lines)


def _derive_findings(results: list[ExperimentResult]) -> list[str]:
    artifact = _find_result(results, "artifact")
    baseline = _find_result(results, "baseline")
    if not artifact or not baseline or not artifact.metrics or not baseline.metrics:
        return ["实验已经运行，但还没有可比较的结构化指标。"]
    findings = []
    for metric in sorted(artifact.metrics):
        artifact_value = artifact.metrics[metric]
        baseline_value = baseline.metrics.get(metric)
        if baseline_value is None:
            continue
        delta = round(artifact_value - baseline_value, 3)
        direction = _direction_text(metric, delta)
        label = METRIC_LABELS.get(metric, metric)
        findings.append(
            f"产物中心模式的{label}{direction}基线模式"
            f"（产物中心={artifact_value}，基线={baseline_value}，差值={delta}）。"
        )
    return findings


def _derive_statistical_findings(report: StatisticsReport | None) -> list[str]:
    if report is None or not report.comparisons:
        return ["实验已经运行，但统计审计没有形成可比较指标。"]
    findings = []
    for item in report.comparisons:
        label = METRIC_LABELS.get(item.metric, item.metric)
        effect = "NA" if item.effect_size is None else f"{item.effect_size:.3f}"
        findings.append(
            f"{label}：candidate 均值={item.candidate_mean:.3f}，baseline 均值={item.baseline_mean:.3f}，"
            f"差值={item.delta:.3f}，95% CI=[{item.ci_low:.3f}, {item.ci_high:.3f}]，"
            f"效应量={effect}；{item.interpretation}"
        )
    return findings


def _direction_text(metric: str, delta: float) -> str:
    lowered = metric.lower()
    lower_is_better = metric in {"audit_minutes", "unsupported_claims"} or any(
        token in lowered
        for token in ["time", "cost", "latency", "collision", "failure", "error", "risk", "耗时", "成本", "碰撞", "失败", "误差", "风险"]
    )
    if lower_is_better:
        return "低于" if delta < 0 else "高于"
    return "高于" if delta > 0 else "低于"


def _find_result(results: list[ExperimentResult], token: str) -> ExperimentResult | None:
    for result in results:
        if token in result.name:
            return result
    return None
