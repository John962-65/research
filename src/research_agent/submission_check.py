from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text
from .config import PaperConfig
from .models import SubmissionCheckItem, SubmissionCheckReport


SUBMISSION_CHECK_JSON = "10-submission-check.json"
SUBMISSION_CHECK_MD = "10-submission-check.md"


def build_submission_check_report(topic: str, run_dir: Path, config: PaperConfig) -> SubmissionCheckReport:
    paper_md_path = run_dir / "09-revised-paper.md"
    paper_tex_path = run_dir / "09-revised-paper.tex"
    bib_path = run_dir / "01-references.bib"
    figure_path = run_dir / "04-statistics-figure.svg"
    availability = _read_json(run_dir / "10-code-data-availability.json")
    ai_disclosure = _read_json(run_dir / "10-ai-disclosure.json")
    llm_ledger = _read_json(run_dir / "run-llm-ledger.json")
    failure_analysis = _read_json(run_dir / "04-failure-analysis.json")
    experiment_decision = _read_json(run_dir / "04-experiment-decision.json")
    hypothesis_outcome = _read_json(run_dir / "04-hypothesis-outcome.json")
    claim_preflight = _read_json(run_dir / "04-claim-boundary-preflight.json")
    revision_response = _read_json(run_dir / "09-revision-response-audit.json")
    citation_grounding = _read_json(run_dir / "10-citation-grounding.json")
    citation_coverage = _read_json(run_dir / "10-citation-coverage.json")
    results_presentation = _read_json(run_dir / "10-results-presentation.json")
    claim_consistency = _read_json(run_dir / "10-claim-consistency.json")
    paper_md = _read_text(paper_md_path)
    paper_tex = _read_text(paper_tex_path)
    checks = [
        _file_check("paper", "修订稿 Markdown", paper_md_path, "重新运行修订阶段生成 09-revised-paper.md。"),
        _file_check("latex", "修订稿 TeX", paper_tex_path, "重新运行修订阶段生成 09-revised-paper.tex。"),
        _latex_structure_check(paper_tex),
        _required_sections_check(paper_md),
        _references_check(bib_path),
        _citation_marker_check(paper_md, bib_path),
        _citation_grounding_check(citation_grounding),
        _citation_coverage_check(citation_coverage),
        _results_presentation_check(results_presentation),
        _claim_consistency_check(claim_consistency),
        _failure_boundary_check(paper_md, failure_analysis),
        _experiment_decision_check(paper_md, experiment_decision),
        _hypothesis_outcome_check(paper_md, hypothesis_outcome),
        _claim_boundary_preflight_check(paper_md, claim_preflight),
        _revision_response_check(revision_response),
        _figure_check(figure_path),
        _availability_check(availability),
        _ai_disclosure_check(ai_disclosure, llm_ledger),
        _venue_template_check(config.target_venue, paper_tex),
        _length_check(paper_md),
    ]
    blocking = [f"{item.item}: {item.action}" for item in checks if item.status == "block"]
    manual = [f"{item.item}: {item.action}" for item in checks if item.status == "manual_required"]
    status = _status(checks)
    return SubmissionCheckReport(
        topic=topic,
        target_venue=config.target_venue,
        status=status,
        checks=checks,
        blocking_issues=blocking,
        manual_tasks=manual,
        recommended_actions=_recommended_actions(status, config.target_venue, checks),
    )


def write_submission_check_artifacts(topic: str, run_dir: Path, config: PaperConfig) -> SubmissionCheckReport:
    report = build_submission_check_report(topic, run_dir, config)
    write_json(run_dir / SUBMISSION_CHECK_JSON, report)
    write_text(run_dir / SUBMISSION_CHECK_MD, render_submission_check_markdown(report))
    return report


def render_submission_check_markdown(report: SubmissionCheckReport) -> str:
    lines = [
        f"# 投稿格式检查：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 目标场景：{report.target_venue}",
        "",
        "## 检查项",
        "| 类别 | 项目 | 状态 | 证据 | 动作 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.checks:
        lines.append(
            "| "
            + " | ".join([_cell(item.category), _cell(item.item), item.status, _cell(item.evidence), _cell(item.action or "-")])
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    if report.blocking_issues:
        lines.extend(f"- {item}" for item in report.blocking_issues)
    else:
        lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    if report.manual_tasks:
        lines.extend(f"- [ ] {item}" for item in report.manual_tasks)
    else:
        lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    lines.extend(f"- [ ] {item}" for item in report.recommended_actions)
    return "\n".join(lines)


def _file_check(category: str, item: str, path: Path, action: str) -> SubmissionCheckItem:
    if path.exists() and path.is_file() and path.stat().st_size > 0:
        return SubmissionCheckItem(category, item, "pass", f"{path.name} 存在，{path.stat().st_size} bytes")
    return SubmissionCheckItem(category, item, "block", f"{path.name} 缺失或为空", action)


def _latex_structure_check(tex: str) -> SubmissionCheckItem:
    required = ["\\documentclass", "\\begin{document}", "\\end{document}", "\\title{"]
    missing = [token for token in required if token not in tex]
    if missing:
        return SubmissionCheckItem("latex", "TeX 基本结构", "block", "缺少 " + ", ".join(missing), "重新生成 TeX 或人工修复 LaTeX 结构。")
    return SubmissionCheckItem("latex", "TeX 基本结构", "pass", "documentclass/title/document 环境完整")


def _required_sections_check(paper_md: str) -> SubmissionCheckItem:
    required = ["摘要", "方法", "结果", "局限", "结论", "代码和数据可用性"]
    missing = [section for section in required if section not in paper_md]
    if missing:
        return SubmissionCheckItem("paper", "必需章节", "manual_required", "缺少：" + ", ".join(missing), "补齐缺失章节后重新运行论文复核。")
    return SubmissionCheckItem("paper", "必需章节", "pass", "核心章节齐全")


def _references_check(path: Path) -> SubmissionCheckItem:
    text = _read_text(path)
    entries = len(re.findall(r"@\w+\{", text))
    if entries == 0:
        return SubmissionCheckItem("references", "BibTeX 参考文献", "block", "未找到 BibTeX 条目", "重新生成 01-references.bib 或人工导入参考文献。")
    if entries < 5:
        return SubmissionCheckItem("references", "BibTeX 参考文献", "manual_required", f"仅 {entries} 条 BibTeX", "投稿前补充并核对参考文献覆盖。")
    return SubmissionCheckItem("references", "BibTeX 参考文献", "pass", f"{entries} 条 BibTeX")


def _citation_marker_check(paper_md: str, bib_path: Path) -> SubmissionCheckItem:
    keys = _bib_keys(_read_text(bib_path))
    if not keys:
        return SubmissionCheckItem("references", "正文 citation key", "block", "缺少可核对 BibTeX key", "重新生成 01-references.bib 或人工导入参考文献。")
    matched = [key for key in keys if f"[{key}]" in paper_md or f"\\cite{{{key}}}" in paper_md]
    if not matched:
        return SubmissionCheckItem("references", "正文 citation key", "manual_required", "正文未检测到 BibTeX citation key", "在相关工作、方法和证据段落加入 `[citation_key]` 或正式 LaTeX cite。")
    if len(matched) < min(3, len(keys)):
        return SubmissionCheckItem("references", "正文 citation key", "manual_required", f"仅检测到 {len(matched)}/{len(keys)} 个 key", "人工确认核心文献是否都在正文被引用。")
    return SubmissionCheckItem("references", "正文 citation key", "pass", f"检测到 {len(matched)}/{len(keys)} 个 key")


def _citation_grounding_check(data: Any) -> SubmissionCheckItem:
    if not isinstance(data, dict) or not data:
        return SubmissionCheckItem("references", "Citation grounding 审计", "manual_required", "缺少 10-citation-grounding.json", "重新运行最终审计阶段，或人工逐条核对正文 citation 附近 claim 与对应文献 chunk。")
    status = str(data.get("status") or "")
    total = _safe_int(data.get("total_citations"))
    blocked = _safe_int(data.get("blocked_citations"))
    review = _safe_int(data.get("review_citations"))
    score = _safe_float(data.get("grounding_score"))
    if status == "block" or blocked:
        return SubmissionCheckItem("references", "Citation grounding 审计", "block", f"status={status or '-'}; blocked={blocked}; total={total}", "先处理 10-citation-grounding.md 中 citation key 缺失、无证据 chunk 或无法支撑的正文 claim。")
    if status == "review_required" or review:
        return SubmissionCheckItem("references", "Citation grounding 审计", "manual_required", f"status={status or '-'}; review={review}; score={score:.2f}", "人工核对 10-citation-grounding.md 中 weak overlap 的引用，必要时换引用、补证或删除 claim。")
    if total == 0:
        return SubmissionCheckItem("references", "Citation grounding 审计", "block", "未检测到 citation marker", "在修订稿正文加入可核对 citation key 并重新运行 grounding 审计。")
    return SubmissionCheckItem("references", "Citation grounding 审计", "pass", f"status={status or 'pass'}; total={total}; score={score:.2f}")


def _citation_coverage_check(data: Any) -> SubmissionCheckItem:
    if not isinstance(data, dict) or not data:
        return SubmissionCheckItem("references", "Citation coverage 审计", "manual_required", "缺少 10-citation-coverage.json", "重新运行最终审计阶段，或人工确认 context 核心文献是否进入正文。")
    status = str(data.get("status") or "")
    score = _safe_float(data.get("coverage_score"))
    ratio = _safe_float(data.get("context_coverage_ratio"))
    unique = _safe_int(data.get("unique_cited_keys"))
    context = _safe_int(data.get("context_citations"))
    blocking = len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0
    manual = len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0
    evidence = f"status={status or '-'}; score={score:.2f}; coverage={unique}/{context}; ratio={ratio:.2f}; blocking={blocking}; manual={manual}"
    if status == "block" or blocking:
        return SubmissionCheckItem("references", "Citation coverage 审计", "block", evidence, "先处理 10-citation-coverage.md 中未知 citation key、缺失 marker 或 context 覆盖过低问题。")
    if status == "review_required" or manual:
        return SubmissionCheckItem("references", "Citation coverage 审计", "manual_required", evidence, "人工核对 10-citation-coverage.md 中高相关/近年/核心文献未被正文引用或 citation 过度集中问题。")
    return SubmissionCheckItem("references", "Citation coverage 审计", "pass", evidence)


def _results_presentation_check(data: Any) -> SubmissionCheckItem:
    if not isinstance(data, dict) or not data:
        return SubmissionCheckItem("paper", "结果呈现审计", "manual_required", "缺少 10-results-presentation.json", "重新运行最终审计阶段，或人工核对结果章节、统计指标、图表引用和 CI 表述。")
    status = str(data.get("status") or "")
    score = _safe_float(data.get("presentation_score"))
    blockers = data.get("blocking_issues") if isinstance(data.get("blocking_issues"), list) else []
    manual = data.get("manual_tasks") if isinstance(data.get("manual_tasks"), list) else []
    inventory = data.get("evidence_inventory") if isinstance(data.get("evidence_inventory"), dict) else {}
    metrics = _safe_int(inventory.get("metrics"))
    matched = _safe_int(inventory.get("matched_metrics"))
    comparisons = _safe_int(inventory.get("comparisons"))
    evidence = f"status={status or '-'}; score={score:.2f}; metrics={matched}/{metrics}; comparisons={comparisons}"
    if status == "block" or blockers:
        return SubmissionCheckItem("paper", "结果呈现审计", "block", evidence, "先处理 10-results-presentation.md 中的结果章节、指标覆盖或无依据比较性主张。")
    if status == "review_required" or manual:
        return SubmissionCheckItem("paper", "结果呈现审计", "manual_required", evidence, "人工核对 10-results-presentation.md 中的图表引用、CI/不确定性和指标覆盖待办。")
    return SubmissionCheckItem("paper", "结果呈现审计", "pass", evidence)


def _claim_consistency_check(data: Any) -> SubmissionCheckItem:
    if not isinstance(data, dict) or not data:
        return SubmissionCheckItem("paper", "Claim consistency 审计", "manual_required", "缺少 10-claim-consistency.json", "重新运行最终审计阶段，或人工核对论文结论是否和 04-hypothesis-outcome 一致。")
    status = str(data.get("status") or "")
    score = _safe_float(data.get("consistency_score"))
    blockers = data.get("blocking_issues") if isinstance(data.get("blocking_issues"), list) else []
    manual = data.get("manual_tasks") if isinstance(data.get("manual_tasks"), list) else []
    inventory = data.get("evidence_inventory") if isinstance(data.get("evidence_inventory"), dict) else {}
    outcome = str(inventory.get("outcome") or "")
    strong_claims = _safe_int(inventory.get("strong_positive_claims"))
    evidence = f"status={status or '-'}; score={score:.2f}; outcome={outcome or '-'}; strong_claims={strong_claims}"
    if status == "block" or blockers:
        return SubmissionCheckItem("paper", "Claim consistency 审计", "block", evidence, "先处理 10-claim-consistency.md 中与假设结果不一致的过强结论。")
    if status == "review_required" or manual:
        return SubmissionCheckItem("paper", "Claim consistency 审计", "manual_required", evidence, "人工核对 10-claim-consistency.md 中的保守表述、负结果和结果边界待办。")
    return SubmissionCheckItem("paper", "Claim consistency 审计", "pass", evidence)


def _failure_boundary_check(paper_md: str, failure_analysis: Any) -> SubmissionCheckItem:
    if not isinstance(failure_analysis, dict) or not failure_analysis:
        return SubmissionCheckItem("paper", "结果边界", "manual_required", "缺少 04-failure-analysis.json", "重新运行实验后审计，或人工确认论文结论边界。")
    status = str(failure_analysis.get("status") or "")
    boundaries = failure_analysis.get("claim_boundaries") if isinstance(failure_analysis.get("claim_boundaries"), list) else []
    if status in {"warn", "block"} and not ("结果边界" in paper_md or "结论边界" in paper_md):
        return SubmissionCheckItem("paper", "结果边界", "manual_required", f"failure_analysis={status}; 边界 {len(boundaries)} 条", "在修订稿中加入“结果边界”小节并响应 04-failure-analysis。")
    if status == "block":
        return SubmissionCheckItem("paper", "结果边界", "manual_required", f"failure_analysis=block; 边界 {len(boundaries)} 条", "确认修订稿没有把阻断实验写成有效性结论。")
    if status == "warn":
        return SubmissionCheckItem("paper", "结果边界", "pass", f"failure_analysis=warn; 已检测到边界小节")
    return SubmissionCheckItem("paper", "结果边界", "pass", f"failure_analysis={status or 'unknown'}")


def _experiment_decision_check(paper_md: str, experiment_decision: Any) -> SubmissionCheckItem:
    if not isinstance(experiment_decision, dict) or not experiment_decision:
        return SubmissionCheckItem("paper", "实验后决策", "manual_required", "缺少 04-experiment-decision.json", "重新运行实验后决策，或人工确认 proceed/refine/pivot/repair 边界。")
    decision = str(experiment_decision.get("decision") or "")
    status = str(experiment_decision.get("status") or "")
    boundaries = experiment_decision.get("claim_boundaries") if isinstance(experiment_decision.get("claim_boundaries"), list) else []
    if decision == "repair_before_writing" or status == "block":
        return SubmissionCheckItem("paper", "实验后决策", "block", f"decision={decision or '-'}; status={status or '-'}", "先修复 04-experiment-decision.md 中的 repair 决策，不能把当前稿件作为可投稿结果。")
    if decision in {"pivot_or_refine", "refine_experiment", "benchmark_upgrade"} or status == "warn":
        if not ("结果边界" in paper_md or "结论边界" in paper_md):
            return SubmissionCheckItem("paper", "实验后决策", "manual_required", f"decision={decision or '-'}; boundaries={len(boundaries)}", "在修订稿中加入“结果边界”或“结论边界”，响应 04-experiment-decision。")
        return SubmissionCheckItem("paper", "实验后决策", "pass", f"decision={decision or '-'}; 已检测到边界小节")
    return SubmissionCheckItem("paper", "实验后决策", "pass", f"decision={decision or 'unknown'}; status={status or 'unknown'}")


def _hypothesis_outcome_check(paper_md: str, hypothesis_outcome: Any) -> SubmissionCheckItem:
    if not isinstance(hypothesis_outcome, dict) or not hypothesis_outcome:
        return SubmissionCheckItem("paper", "假设结果审计", "manual_required", "缺少 04-hypothesis-outcome.json", "重新运行实验后审计，或人工确认原始 hypothesis 是否被当前结果检验。")
    status = str(hypothesis_outcome.get("status") or "")
    outcome = str(hypothesis_outcome.get("outcome") or "")
    score = _safe_float(hypothesis_outcome.get("support_score"))
    if status == "block" or outcome in {"blocked_unverified", "untested"}:
        return SubmissionCheckItem("paper", "假设结果审计", "block", f"outcome={outcome or '-'}; status={status or '-'}; score={score:.2f}", "先处理 04-hypothesis-outcome.md 中未检验、无统计比较或被阻断的 hypothesis 结果。")
    if status == "review_required" or outcome in {"partially_supported", "refuted_or_negative", "inconclusive", "smoke_only"}:
        if not ("结果边界" in paper_md or "结论边界" in paper_md):
            return SubmissionCheckItem("paper", "假设结果审计", "manual_required", f"outcome={outcome or '-'}; status={status or '-'}; score={score:.2f}", "在修订稿中加入结果/结论边界，明确假设只是部分支持、负结果、不确定或 smoke-only。")
        return SubmissionCheckItem("paper", "假设结果审计", "pass", f"outcome={outcome or '-'}; 已检测到边界小节")
    return SubmissionCheckItem("paper", "假设结果审计", "pass", f"outcome={outcome or 'supported'}; score={score:.2f}")


def _claim_boundary_preflight_check(paper_md: str, claim_preflight: Any) -> SubmissionCheckItem:
    if not isinstance(claim_preflight, dict) or not claim_preflight:
        return SubmissionCheckItem("paper", "Claim 边界预检", "manual_required", "缺少 04-claim-boundary-preflight.json", "重新运行分析后写作阶段，或人工确认 allowed/prohibited claim 和结果边界。")
    status = str(claim_preflight.get("status") or "")
    mode = str(claim_preflight.get("writing_mode") or "")
    risk = _safe_float(claim_preflight.get("risk_score"))
    blockers = claim_preflight.get("blocking_issues") if isinstance(claim_preflight.get("blocking_issues"), list) else []
    warnings = claim_preflight.get("warnings") if isinstance(claim_preflight.get("warnings"), list) else []
    has_boundary = "结果边界" in paper_md or "结论边界" in paper_md
    evidence = f"status={status or '-'}; mode={mode or '-'}; risk={risk:.2f}; warnings={len(warnings)}"
    if status == "block" or blockers:
        return SubmissionCheckItem("paper", "Claim 边界预检", "block", evidence, "先处理 04-claim-boundary-preflight.md 中的阻断项，再把论文限制为诊断/修复报告或重跑实验。")
    if status == "review_required":
        if not has_boundary:
            return SubmissionCheckItem("paper", "Claim 边界预检", "manual_required", evidence, "在修订稿中加入结果/结论边界，并响应 allowed/prohibited claim。")
        return SubmissionCheckItem("paper", "Claim 边界预检", "manual_required", evidence, "人工确认修订稿没有使用 04-claim-boundary-preflight.md 禁止的强结论。")
    return SubmissionCheckItem("paper", "Claim 边界预检", "pass", evidence)


def _revision_response_check(revision_response: Any) -> SubmissionCheckItem:
    if not isinstance(revision_response, dict) or not revision_response:
        return SubmissionCheckItem("paper", "修订响应审计", "manual_required", "缺少 09-revision-response-audit.json", "重新运行 paper_rewrite 阶段，确认每条审稿修订任务都有处理结果和正文痕迹。")
    status = str(revision_response.get("status") or "")
    score = _safe_float(revision_response.get("response_score"))
    blocking = len(revision_response.get("blocking_issues", [])) if isinstance(revision_response.get("blocking_issues"), list) else 0
    manual = len(revision_response.get("manual_tasks", [])) if isinstance(revision_response.get("manual_tasks"), list) else 0
    summary = revision_response.get("summary") if isinstance(revision_response.get("summary"), dict) else {}
    missing_results = _safe_int(summary.get("missing_results"))
    missing_traces = _safe_int(summary.get("missing_paper_traces"))
    evidence = f"status={status or '-'}; score={score:.2f}; missing_results={missing_results}; missing_traces={missing_traces}; blocking={blocking}; manual={manual}"
    if status == "block" or blocking:
        return SubmissionCheckItem("paper", "修订响应审计", "block", evidence, "先处理 09-revision-response-audit.md 中缺失 result、缺失正文任务痕迹或高优先级任务静默消失问题。")
    if status == "review_required" or manual or missing_results or missing_traces:
        return SubmissionCheckItem("paper", "修订响应审计", "manual_required", evidence, "人工关闭 09-revision-response-audit.md 中的 needs_human_evidence/needs_human_verification 任务后再投稿。")
    return SubmissionCheckItem("paper", "修订响应审计", "pass", evidence)


def _figure_check(path: Path) -> SubmissionCheckItem:
    if path.exists() and path.stat().st_size > 0:
        return SubmissionCheckItem("figures", "统计图", "pass", f"{path.name} 存在")
    return SubmissionCheckItem("figures", "统计图", "manual_required", "缺少 04-statistics-figure.svg", "重新运行统计阶段或补充论文图表。")


def _availability_check(data: Any) -> SubmissionCheckItem:
    if not isinstance(data, dict):
        return SubmissionCheckItem("availability", "代码/数据可用性", "block", "缺少 10-code-data-availability.json", "重新运行最终审计阶段。")
    status = str(data.get("status") or "")
    manual_count = len(data.get("manual_tasks", [])) if isinstance(data.get("manual_tasks"), list) else 0
    blocking_count = len(data.get("blocking_issues", [])) if isinstance(data.get("blocking_issues"), list) else 0
    if status == "blocked" or blocking_count:
        return SubmissionCheckItem("availability", "代码/数据可用性", "block", f"{status}; blocking={blocking_count}", "先处理 10-code-data-availability.md 的阻断项。")
    if manual_count:
        return SubmissionCheckItem("availability", "代码/数据可用性", "manual_required", f"{status}; manual_tasks={manual_count}", "补齐公开仓库、许可证、数据访问和归档 DOI。")
    return SubmissionCheckItem("availability", "代码/数据可用性", "pass", status or "ready")


def _ai_disclosure_check(data: Any, ledger: Any) -> SubmissionCheckItem:
    calls = _safe_int(ledger.get("total_calls")) if isinstance(ledger, dict) else 0
    if not isinstance(data, dict) or not data:
        if calls:
            return SubmissionCheckItem(
                "ai_disclosure",
                "AI 使用披露",
                "manual_required",
                f"LLM 调用 {calls} 次，但缺少 10-ai-disclosure.json",
                "重新生成 10-ai-disclosure.md，并按目标 venue AI policy 加入披露。",
            )
        return SubmissionCheckItem("ai_disclosure", "AI 使用披露", "manual_required", "缺少 AI 使用披露审计", "人工确认是否使用 AI，并补充披露或不适用说明。")
    status = str(data.get("status") or "")
    used_ai = data.get("used_ai") is True
    statement = str(data.get("disclosure_statement") or "").strip()
    if used_ai and not statement:
        return SubmissionCheckItem("ai_disclosure", "AI 使用披露", "block", "使用了 AI/LLM 但 disclosure_statement 为空", "补写 AI 使用披露后再投稿。")
    if status == "needs_human_policy_check":
        return SubmissionCheckItem(
            "ai_disclosure",
            "AI 使用披露",
            "manual_required",
            f"status={status}; used_ai={used_ai}; calls={data.get('total_llm_calls', calls)}",
            "按目标 venue AI policy 人工确认披露位置和措辞。",
        )
    if status == "not_applicable":
        return SubmissionCheckItem("ai_disclosure", "AI 使用披露", "pass", "未记录 LLM 调用；仍需人工确认")
    return SubmissionCheckItem("ai_disclosure", "AI 使用披露", "manual_required", f"status={status or 'unknown'}", "人工核对 AI 使用披露状态。")


def _venue_template_check(target_venue: str, tex: str) -> SubmissionCheckItem:
    venue = target_venue.lower()
    expected = ""
    if "ieee" in venue:
        expected = "IEEEtran"
    elif "acm" in venue:
        expected = "acmart"
    elif "nature" in venue:
        expected = "nature"
    if not expected:
        return SubmissionCheckItem("venue", "目标模板", "manual_required", f"目标场景 {target_venue} 未绑定正式模板", "投稿前按目标会议/期刊替换 LaTeX 模板和参考文献样式。")
    if expected in tex:
        return SubmissionCheckItem("venue", "目标模板", "pass", f"检测到 {expected}")
    return SubmissionCheckItem("venue", "目标模板", "manual_required", f"目标 {target_venue} 期望 {expected}，当前未检测到", "替换为目标会议/期刊官方模板。")


def _length_check(paper_md: str) -> SubmissionCheckItem:
    chars = len(paper_md.strip())
    if chars < 800:
        return SubmissionCheckItem("paper", "草稿长度", "manual_required", f"{chars} chars", "草稿偏短，投稿前补充方法、实验细节和相关工作。")
    return SubmissionCheckItem("paper", "草稿长度", "pass", f"{chars} chars")


def _status(checks: list[SubmissionCheckItem]) -> str:
    if any(item.status == "block" for item in checks):
        return "blocked"
    if any(item.status == "manual_required" for item in checks):
        return "needs_human_format_check"
    return "ready_for_submission_check"


def _recommended_actions(status: str, target_venue: str, checks: list[SubmissionCheckItem]) -> list[str]:
    actions = [
        "用目标会议/期刊官方模板人工替换当前通用 TeX 骨架。",
        "检查参考文献样式、图表编号、页数限制、匿名要求和附录格式。",
        "确认 10-code-data-availability.md 中的公开仓库、数据访问和归档 DOI 已补齐。",
    ]
    if status == "blocked":
        actions.insert(0, "先处理投稿格式检查中的 block 项，再进入人工格式打磨。")
    if target_venue:
        actions.append(f"按 `{target_venue}` 的 author guideline 做最终人工核对。")
    return actions


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


def _bib_keys(text: str) -> list[str]:
    keys: list[str] = []
    for match in re.finditer(r"@\w+\{([^,\s]+)", text):
        key = match.group(1).strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
