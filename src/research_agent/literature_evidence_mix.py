from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import LiteratureQualityReport, LiteratureReview, Paper, ResearchPlan


LITERATURE_EVIDENCE_MIX_JSON = "01-literature-evidence-mix.json"
LITERATURE_EVIDENCE_MIX_MD = "01-literature-evidence-mix.md"


def write_literature_evidence_mix_artifacts(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    coverage_report: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_evidence_mix_report(research_plan, raw_review, curated_review, quality_report, coverage_report)
    write_json(run_dir / LITERATURE_EVIDENCE_MIX_JSON, report)
    write_text(run_dir / LITERATURE_EVIDENCE_MIX_MD, render_literature_evidence_mix_markdown(report))
    return report


def build_literature_evidence_mix_report(
    research_plan: ResearchPlan,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    coverage_report: dict[str, Any],
) -> dict[str, Any]:
    papers = curated_review.papers
    quality = _quality_data(quality_report)
    selected = len(papers)
    source_diversity = len(_sources(papers))
    doi_coverage = _ratio(sum(1 for paper in papers if paper.doi), selected)
    abstract_coverage = _ratio(sum(1 for paper in papers if len(paper.abstract or "") >= 100), selected)
    recent_coverage = _ratio(sum(1 for paper in papers if _is_recent(paper.year)), selected)
    thin_crossref = [paper.title for paper in papers if _is_thin_crossref(paper)]
    no_locator = [paper.title for paper in papers if not paper.doi and not paper.url]
    anchor_checks = _anchor_checks(research_plan, papers)
    passed_anchors = sum(1 for item in anchor_checks if item["status"] == "pass")
    required_anchors = sum(1 for item in anchor_checks if item["required"])
    anchor_coverage = _ratio(passed_anchors, required_anchors)
    metadata_score = (
        min(doi_coverage / 0.65, 1.0) * 0.30
        + min(abstract_coverage / 0.75, 1.0) * 0.22
        + min(source_diversity / 3.0, 1.0) * 0.23
        + min(recent_coverage / 0.35, 1.0) * 0.15
        + (0.10 if selected >= 5 else 0.0)
    )
    mix_score = round(
        max(
            0.0,
            min(
                1.0,
                anchor_coverage * 0.46
                + metadata_score * 0.36
                + min(_safe_float(quality.get("confidence_score")), 1.0) * 0.14
                + min(_safe_float(coverage_report.get("coverage_ratio")), 1.0) * 0.04
                - min(0.18, len(thin_crossref) * 0.05 + len(no_locator) * 0.04),
            ),
        ),
        3,
    )
    warnings = _warnings(selected, source_diversity, doi_coverage, abstract_coverage, recent_coverage, anchor_checks, thin_crossref, no_locator)
    blocking = _blocking_issues(selected, anchor_checks)
    status = _status(mix_score, blocking, warnings)
    return {
        "schema_version": 1,
        "topic": curated_review.topic or raw_review.topic or research_plan.topic,
        "domain": research_plan.domain,
        "status": status,
        "mix_score": mix_score,
        "summary": {
            "raw_papers": len(raw_review.papers),
            "curated_papers": selected,
            "source_diversity": source_diversity,
            "doi_coverage": round(doi_coverage, 3),
            "abstract_coverage": round(abstract_coverage, 3),
            "recent_coverage": round(recent_coverage, 3),
            "anchor_coverage": round(anchor_coverage, 3),
            "quality_confidence": quality.get("confidence_status") or "",
            "quality_score": _safe_float(quality.get("confidence_score")),
            "coverage_status": coverage_report.get("status") or "",
            "coverage_ratio": _safe_float(coverage_report.get("coverage_ratio")),
        },
        "anchor_checks": anchor_checks,
        "thin_crossref_titles": thin_crossref[:8],
        "missing_locator_titles": no_locator[:8],
        "blocking_issues": blocking,
        "warnings": warnings,
        "required_actions": _required_actions(status, anchor_checks, thin_crossref, no_locator),
    }


def render_literature_evidence_mix_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# 文献证据组合审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 组合分：{float(report.get('mix_score') or 0.0):.3f}",
        f"- 原始/筛选文献：{summary.get('raw_papers', 0)}/{summary.get('curated_papers', 0)}",
        f"- 来源多样性：{summary.get('source_diversity', 0)}",
        f"- DOI/摘要/近期覆盖：{float(summary.get('doi_coverage') or 0):.1%} / {float(summary.get('abstract_coverage') or 0):.1%} / {float(summary.get('recent_coverage') or 0):.1%}",
        f"- Anchor 覆盖：{float(summary.get('anchor_coverage') or 0):.1%}",
        "",
    ]
    for key, title in [("blocking_issues", "阻断问题"), ("warnings", "警告"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            prefix = "- [ ] " if key == "required_actions" else "- "
            lines.extend(prefix + str(item) for item in values)
            lines.append("")
    lines.extend(
        [
            "## Anchor 检查",
            "| Anchor | 必需 | 状态 | 命中文献 | 证据 | 动作 |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for item in report.get("anchor_checks", []) if isinstance(report.get("anchor_checks"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("name") or "")),
                    "yes" if item.get("required") else "no",
                    _cell(str(item.get("status") or "")),
                    str(item.get("matched_papers") or 0),
                    _cell("；".join(str(value) for value in item.get("evidence_titles", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("action") or "-")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- 该审计检查的是整批 curated 文献是否像一个可用调研包，而不是单篇文献分数。",
            "- 至少应覆盖综述/高引用入口、benchmark/dataset、baseline/method、近期论文和可核验 metadata。",
            "- 状态不是 pass 时，不建议直接批准进入 idea/实验；如人工豁免，应在 approval notes 写明理由。",
        ]
    )
    return "\n".join(lines)


def _anchor_checks(plan: ResearchPlan, papers: list[Paper]) -> list[dict[str, Any]]:
    year = _current_year()
    benchmark_terms = _benchmark_anchor_terms(plan)
    baseline_terms = _terms(" ".join(plan.baselines)) + ["baseline", "method"]
    specs = [
        {
            "name": "survey_or_high_citation_anchor",
            "required": True,
            "terms": ["survey", "review", "systematic review", "benchmarking"],
            "predicate": lambda paper: _has_any(paper, ["survey", "review", "systematic review", "benchmarking"]) or (paper.citation_count or 0) >= 120,
            "action": "补 1-2 篇综述、benchmarking 论文或高引用基础论文 DOI/URL。",
        },
        {
            "name": "benchmark_or_dataset_anchor",
            "required": True,
            "terms": benchmark_terms,
            "predicate": lambda paper: _has_any(paper, benchmark_terms),
            "action": "补覆盖公开 benchmark、dataset 或标准 evaluation protocol 的文献。",
        },
        {
            "name": "baseline_or_method_anchor",
            "required": True,
            "terms": baseline_terms,
            "predicate": lambda paper: _has_any(paper, baseline_terms),
            "action": "补覆盖主要 baseline/method family 的经典或近期论文。",
        },
        {
            "name": "recent_research_anchor",
            "required": True,
            "terms": [str(year - 5), str(year - 4), str(year - 3), str(year - 2), str(year - 1), str(year)],
            "predicate": lambda paper: _is_recent(paper.year),
            "action": f"补 {year - 5} 年以来的近期研究，避免只依赖旧题录。",
        },
    ]
    return [_anchor_row(spec, papers) for spec in specs]


def _benchmark_anchor_terms(plan: ResearchPlan) -> list[str]:
    noisy_plan_terms = {
        "motion",
        "planning",
        "path",
        "trajectory",
        "robot",
        "robots",
        "robotic",
        "manipulator",
        "manipulators",
        "arm",
        "arms",
        "task",
        "tasks",
        "scene",
        "scenes",
        "cluttered",
        "narrow",
        "passage",
    }
    terms = [term for term in _terms(" ".join(plan.benchmarks)) if term not in noisy_plan_terms]
    terms.extend(
        [
            "benchmark",
            "benchmarking",
            "dataset",
            "data set",
            "evaluation protocol",
            "evaluation suite",
            "testbed",
            "test bed",
            "leaderboard",
            "challenge",
            "corpus",
        ]
    )
    if plan.domain == "robotics_motion_planning":
        terms.extend(["ompl", "open motion planning library", "moveit", "moveit benchmarking"])
    elif plan.domain == "bearing_fault_diagnosis":
        terms.extend(["cwru", "paderborn", "xjtu", "xjtu sy", "ims bearing", "bearing data center"])
    elif plan.domain == "ai_research_agents":
        terms.extend(["litqa", "mlagentbench", "mle bench", "paper review rubric", "claim grounding audit set"])
    return _unique(terms)


def _anchor_row(spec: dict[str, Any], papers: list[Paper]) -> dict[str, Any]:
    matched = [paper for paper in papers if spec["predicate"](paper)]
    return {
        "name": spec["name"],
        "required": spec["required"],
        "status": "pass" if matched else "missing",
        "matched_papers": len(matched),
        "matched_terms": list(spec["terms"])[:10],
        "evidence_titles": [paper.title for paper in matched[:4]],
        "action": "无需处理。" if matched else spec["action"],
    }


def _warnings(
    selected: int,
    source_diversity: int,
    doi_coverage: float,
    abstract_coverage: float,
    recent_coverage: float,
    anchor_checks: list[dict[str, Any]],
    thin_crossref: list[str],
    no_locator: list[str],
) -> list[str]:
    warnings: list[str] = []
    if selected < 5:
        warnings.append(f"筛选文献只有 {selected} 篇，组合证据过窄。")
    if source_diversity < 2:
        warnings.append("筛选文献来源过于单一，建议至少覆盖两个在线来源或人工 seed。")
    if doi_coverage < 0.55:
        warnings.append(f"DOI 覆盖不足（{doi_coverage:.0%}），引用导出和核验风险高。")
    if abstract_coverage < 0.60:
        warnings.append(f"摘要覆盖不足（{abstract_coverage:.0%}），RAG chunk 语义支撑偏弱。")
    if recent_coverage < 0.25:
        warnings.append(f"近期文献覆盖不足（{recent_coverage:.0%}），可能遗漏当前 SOTA 或 benchmark。")
    missing = [item["name"] for item in anchor_checks if item["status"] != "pass"]
    if missing:
        warnings.append("缺失证据 anchor：" + "；".join(missing))
    if thin_crossref:
        warnings.append(f"仍有 {len(thin_crossref)} 篇单源 Crossref 且摘要过薄的文献进入 curated context。")
    if no_locator:
        warnings.append(f"仍有 {len(no_locator)} 篇文献缺 DOI/URL locator。")
    return warnings


def _blocking_issues(selected: int, anchor_checks: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    if selected == 0:
        issues.append("没有文献进入 curated context，不能支撑 idea/实验。")
    missing_required = [item["name"] for item in anchor_checks if item["required"] and item["status"] != "pass"]
    if selected < 3 and missing_required:
        issues.append("证据池少于 3 篇且缺失必需 anchor：" + "；".join(missing_required))
    return issues


def _required_actions(status: str, anchor_checks: list[dict[str, Any]], thin_crossref: list[str], no_locator: list[str]) -> list[str]:
    actions = [str(item["action"]) for item in anchor_checks if item["status"] != "pass"]
    if thin_crossref:
        actions.append("用 OpenAlex/Semantic Scholar/arXiv 或人工 DOI seed 替换单源 Crossref 薄摘要题录。")
    if no_locator:
        actions.append("补齐缺 DOI/URL 文献的 locator，或从 curated context 移除。")
    if status in {"block", "needs_evidence_upgrade"}:
        actions.append("处理本审计前，不要批准进入 idea/实验；人工豁免必须写入 approval notes。")
    if not actions:
        actions.append("人工抽查每类 anchor 的 Top 文献，确认题录、摘要和主题匹配。")
    return _unique(actions)


def _status(mix_score: float, blocking: list[str], warnings: list[str]) -> str:
    if blocking:
        return "block"
    if mix_score < 0.55:
        return "needs_evidence_upgrade"
    if warnings or mix_score < 0.72:
        return "review_required"
    return "pass"


def _quality_data(report: LiteratureQualityReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    return {
        "confidence_status": report.confidence_status,
        "confidence_score": report.confidence_score,
        "selected_papers": report.selected_papers,
        "warnings": report.warnings,
    }


def _sources(papers: list[Paper]) -> set[str]:
    values: set[str] = set()
    for paper in papers:
        for source in paper.sources or [paper.source]:
            if str(source).strip():
                values.add(str(source).strip().lower())
    return values


def _is_thin_crossref(paper: Paper) -> bool:
    return set(paper.sources or [paper.source]) == {"crossref"} and len(paper.abstract or "") < 100


def _is_recent(year: int) -> bool:
    return bool(year and year >= _current_year() - 5)


def _has_any(paper: Paper, terms: list[str]) -> bool:
    text = _normalize(" ".join([paper.title, paper.abstract, paper.venue]))
    return any(_normalize(term) and _normalize(term) in text for term in terms)


def _terms(value: str) -> list[str]:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{1,}|[\u4e00-\u9fff]{2,}", value.lower())
    return _unique([term.replace("*", " star") for term in terms if term not in {"with", "and", "the", "for"}])


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / max(1, denominator)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("-", " ").replace("_", " ").replace("*", " star")).strip()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
