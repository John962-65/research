from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text, cell as _cell
from .models import ResultsPresentationCheck, ResultsPresentationReport


RESULTS_PRESENTATION_JSON = "10-results-presentation.json"
RESULTS_PRESENTATION_MD = "10-results-presentation.md"


_KNOWN_METRIC_LABELS = {
    "reproduction_success_rate": "复现成功率",
    "artifact_completeness": "产物完整度",
    "audit_minutes": "审计耗时",
    "unsupported_claims": "无依据主张数",
}


def write_results_presentation_artifacts(topic: str, run_dir: Path) -> ResultsPresentationReport:
    report = build_results_presentation_report(topic, run_dir)
    write_json(run_dir / RESULTS_PRESENTATION_JSON, report)
    write_text(run_dir / RESULTS_PRESENTATION_MD, render_results_presentation_markdown(report))
    return report


def build_results_presentation_report(topic: str, run_dir: Path) -> ResultsPresentationReport:
    paper_md = _read_text(run_dir / "09-revised-paper.md")
    statistics = _read_json(run_dir / "04-statistics.json")
    figure_data = _read_json(run_dir / "04-statistics-figure.json")
    analysis = _read_json(run_dir / "05-analysis.json")
    results = _read_json(run_dir / "04-results.json")
    figure_exists = (run_dir / "04-statistics-figure.svg").exists() and (run_dir / "04-statistics-figure.svg").stat().st_size > 0
    metrics = _metric_names(statistics, figure_data, analysis, results)
    comparisons = _comparison_rows(statistics, figure_data)
    result_section = _result_section_text(paper_md)
    matched_metrics = _matched_metrics(result_section or paper_md, metrics)
    checks = [
        _result_section_check(paper_md),
        _metric_coverage_check(metrics, matched_metrics),
        _figure_reference_check(paper_md, figure_exists, figure_data),
        _uncertainty_check(paper_md, comparisons),
        _comparison_claim_check(result_section or paper_md, comparisons),
    ]
    total = len(checks)
    passed = sum(1 for item in checks if item.status == "pass")
    review = sum(1 for item in checks if item.status == "review")
    score = round((passed + review * 0.45) / total, 3) if total else 0.0
    status = _status(checks)
    return ResultsPresentationReport(
        topic=topic,
        status=status,
        presentation_score=score,
        checks=checks,
        blocking_issues=[f"{item.item}: {item.action}" for item in checks if item.status == "block"],
        manual_tasks=[f"{item.item}: {item.action}" for item in checks if item.status == "review"],
        evidence_inventory={
            "paper_chars": len(paper_md),
            "metrics": len(metrics),
            "matched_metrics": len(matched_metrics),
            "comparisons": len(comparisons),
            "uncertain_comparisons": sum(1 for item in comparisons if _ci_crosses_zero(item)),
            "has_figure_file": figure_exists,
            "figure_status": str(figure_data.get("status") or "") if isinstance(figure_data, dict) else "",
        },
    )


def render_results_presentation_markdown(report: ResultsPresentationReport) -> str:
    lines = [
        f"# Results Presentation Audit：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 分数：{report.presentation_score:.3f}",
        f"- 指标覆盖：{report.evidence_inventory.get('matched_metrics', 0)}/{report.evidence_inventory.get('metrics', 0)}",
        f"- 统计比较：{report.evidence_inventory.get('comparisons', 0)}",
        f"- CI 跨 0 指标：{report.evidence_inventory.get('uncertain_comparisons', 0)}",
        f"- 统计图：{'存在' if report.evidence_inventory.get('has_figure_file') else '缺失'}",
        "",
        "## 阻断问题",
    ]
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(
        [
            "",
            "## Presentation Checks",
            "| 类别 | 项目 | 状态 | 证据 | 动作 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.checks:
        lines.append(
            "| "
            + " | ".join([_cell(item.category), _cell(item.item), item.status, _cell(item.evidence), _cell(item.action or "-")])
            + " |"
        )
    return "\n".join(lines)


def _result_section_check(paper_md: str) -> ResultsPresentationCheck:
    if not paper_md.strip():
        return ResultsPresentationCheck("paper", "结果章节", "block", "09-revised-paper.md 缺失或为空", "重新生成修订稿。")
    if _has_result_heading(paper_md):
        return ResultsPresentationCheck("paper", "结果章节", "pass", "检测到独立结果章节")
    if "结果" in paper_md or "results" in paper_md.lower():
        return ResultsPresentationCheck("paper", "结果章节", "review", "检测到结果相关文字，但没有明确二级结果章节", "把实验发现整理到独立“结果/Results”章节，避免只在摘要或局限性中提到结果。")
    return ResultsPresentationCheck("paper", "结果章节", "block", "正文没有结果章节或结果讨论", "补写结果章节，并只呈现 04-results、04-statistics 和 05-analysis 能支持的发现。")


def _metric_coverage_check(metrics: list[str], matched: list[str]) -> ResultsPresentationCheck:
    if not metrics:
        return ResultsPresentationCheck("results", "统计指标呈现", "review", "没有从统计/分析/结果产物中提取到指标", "确认 04-results.json、04-statistics.json 和 05-analysis.json 是否包含可报告指标。")
    if not matched:
        return ResultsPresentationCheck("results", "统计指标呈现", "block", f"{len(metrics)} 个结构化指标均未在结果正文中出现", "在结果章节至少报告一个核心指标的 candidate/baseline 均值、差值或方向。")
    if len(matched) < len(metrics):
        return ResultsPresentationCheck("results", "统计指标呈现", "review", f"仅覆盖 {len(matched)}/{len(metrics)} 个指标：" + ", ".join(matched[:5]), "人工确认未写入正文的指标是否应删除、移入附录或补充到结果段落。")
    return ResultsPresentationCheck("results", "统计指标呈现", "pass", f"覆盖 {len(matched)}/{len(metrics)} 个指标")


def _figure_reference_check(paper_md: str, figure_exists: bool, figure_data: Any) -> ResultsPresentationCheck:
    if not figure_exists:
        status = str(figure_data.get("status") or "") if isinstance(figure_data, dict) else ""
        if status == "no_comparisons":
            return ResultsPresentationCheck("figures", "图表引用", "pass", "统计图无可比较指标，图表引用非必需")
        return ResultsPresentationCheck("figures", "图表引用", "review", "04-statistics-figure.svg 缺失或为空", "重新运行统计图阶段，或在论文中改用表格呈现核心结果。")
    if _contains_any(
        paper_md,
        ["04-statistics-figure", "统计图", "统计可视化", "图表", "图 ", "Figure", "Fig.", "table", "表 "],
    ):
        return ResultsPresentationCheck("figures", "图表引用", "pass", "正文引用了统计图或结果表")
    return ResultsPresentationCheck("figures", "图表引用", "review", "统计图文件存在，但正文没有显式图/表引用", "在结果章节加入图或表引用，并说明图中 delta、CI 和方向代表什么。")


def _uncertainty_check(paper_md: str, comparisons: list[dict[str, Any]]) -> ResultsPresentationCheck:
    if not comparisons:
        return ResultsPresentationCheck("statistics", "不确定性呈现", "pass", "没有统计比较，CI 呈现非必需")
    uncertain = sum(1 for item in comparisons if _ci_crosses_zero(item))
    has_uncertainty_text = _contains_any(paper_md, ["95% CI", "CI", "置信区间", "不确定", "跨过 0", "跨 0", "更多重复", "效应量"])
    if uncertain and not has_uncertainty_text:
        return ResultsPresentationCheck("statistics", "不确定性呈现", "review", f"{uncertain} 个比较的 CI 跨过 0，但正文没有不确定性/CI 表述", "在结果或结果边界中明确 CI 跨 0 的指标不能作为确定性优势结论。")
    if not has_uncertainty_text:
        return ResultsPresentationCheck("statistics", "不确定性呈现", "review", f"{len(comparisons)} 个比较未在正文中报告 CI/不确定性", "在结果章节报告 95% CI 或解释统计审计的置信区间。")
    return ResultsPresentationCheck("statistics", "不确定性呈现", "pass", f"检测到 CI/不确定性表述；CI 跨 0 指标 {uncertain} 个")


def _comparison_claim_check(result_text: str, comparisons: list[dict[str, Any]]) -> ResultsPresentationCheck:
    has_comparative_text = _contains_any(
        result_text,
        ["candidate", "baseline", "候选", "基线", "对照", "均值", "差值", "delta", "高于", "低于", "改善", "降低", "提高", "优于"],
    )
    if comparisons:
        if has_comparative_text:
            return ResultsPresentationCheck("claims", "比较性结果主张", "pass", f"正文包含 candidate/baseline 或差值语言，统计比较 {len(comparisons)} 个")
        return ResultsPresentationCheck("claims", "比较性结果主张", "review", f"存在 {len(comparisons)} 个统计比较，但结果段落没有比较性表述", "用 candidate、baseline、均值差值和方向改写结果段落。")
    if has_comparative_text:
        return ResultsPresentationCheck("claims", "比较性结果主张", "block", "统计审计没有比较项，但结果段落存在比较/改善语言", "删除或降级无法由 04-statistics.json 支撑的比较性主张。")
    return ResultsPresentationCheck("claims", "比较性结果主张", "pass", "无统计比较，也未检测到比较性结果主张")


def _metric_names(statistics: Any, figure_data: Any, analysis: Any, results: Any) -> list[str]:
    values: list[str] = []
    for source in [statistics, figure_data]:
        if isinstance(source, dict):
            for item in source.get("comparisons", []) if isinstance(source.get("comparisons"), list) else []:
                if isinstance(item, dict) and item.get("metric"):
                    values.append(str(item["metric"]))
    if isinstance(analysis, dict):
        for row in analysis.get("metric_table", []) if isinstance(analysis.get("metric_table"), list) else []:
            if isinstance(row, dict):
                values.extend(str(key) for key in row if key not in {"name", "status", "repeat_index"})
    if isinstance(results, list):
        for row in results:
            metrics = row.get("metrics") if isinstance(row, dict) else None
            if isinstance(metrics, dict):
                values.extend(str(key) for key in metrics)
    return _unique([value.strip() for value in values if value.strip()])


def _comparison_rows(statistics: Any, figure_data: Any) -> list[dict[str, Any]]:
    for source in [figure_data, statistics]:
        if not isinstance(source, dict) or not isinstance(source.get("comparisons"), list):
            continue
        rows = [item for item in source["comparisons"] if isinstance(item, dict) and item.get("metric")]
        if rows:
            return rows
    return []


def _matched_metrics(text: str, metrics: list[str]) -> list[str]:
    matched: list[str] = []
    lowered = text.lower()
    for metric in metrics:
        variants = _metric_variants(metric)
        if any(variant and variant.lower() in lowered for variant in variants):
            matched.append(metric)
    return matched


def _metric_variants(metric: str) -> list[str]:
    label = _KNOWN_METRIC_LABELS.get(metric, "")
    variants = [metric, metric.replace("_", " "), metric.replace("_", "-")]
    if label:
        variants.append(label)
    return _unique([item for item in variants if item])


def _has_result_heading(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if _heading_level(stripped) < 2:
            continue
        heading = stripped.lstrip("#").strip()
        heading = re.sub(r"^\d+[\.\s、-]*", "", heading).strip()
        lowered = heading.lower()
        if "边界" in heading or "boundary" in lowered:
            continue
        if lowered in {"结果", "results"} or lowered.startswith("结果与") or lowered.startswith("results "):
            return True
    return False


def _result_section_text(text: str) -> str:
    lines = text.splitlines()
    start = -1
    start_level = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        level = _heading_level(stripped)
        if level < 2:
            continue
        heading = stripped.lstrip("#").strip()
        heading = re.sub(r"^\d+[\.\s、-]*", "", heading).strip()
        lowered = heading.lower()
        if ("边界" not in heading and "boundary" not in lowered) and (
            lowered in {"结果", "results"} or lowered.startswith("结果与") or lowered.startswith("results ")
        ):
            start = index
            start_level = level
            break
    if start < 0:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        level = _heading_level(lines[index].strip())
        if level and level <= start_level:
            end = index
            break
    return "\n".join(lines[start:end])


def _heading_level(stripped_line: str) -> int:
    match = re.match(r"^(#{1,6})\s+", stripped_line)
    return len(match.group(1)) if match else 0


def _ci_crosses_zero(item: dict[str, Any]) -> bool:
    if item.get("ci_crosses_zero") is True:
        return True
    ci_low = _safe_float(item.get("ci_low"))
    ci_high = _safe_float(item.get("ci_high"))
    return ci_low <= 0 <= ci_high


def _status(checks: list[ResultsPresentationCheck]) -> str:
    if any(item.status == "block" for item in checks):
        return "block"
    if any(item.status == "review" for item in checks):
        return "review_required"
    return "pass"


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


