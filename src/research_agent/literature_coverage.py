from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .artifacts import write_json, write_text
from .models import LiteratureReview, ResearchPlan


LITERATURE_COVERAGE_JSON = "01-literature-coverage.json"
LITERATURE_COVERAGE_MD = "01-literature-coverage.md"


def write_literature_coverage_artifacts(
    research_plan: ResearchPlan,
    review: LiteratureReview,
    run_dir: Path,
) -> dict[str, Any]:
    report = build_literature_coverage_report(research_plan, review)
    write_json(run_dir / LITERATURE_COVERAGE_JSON, report)
    write_text(run_dir / LITERATURE_COVERAGE_MD, render_literature_coverage_markdown(report))
    return report


def build_literature_coverage_report(research_plan: ResearchPlan, review: LiteratureReview) -> dict[str, Any]:
    facets = _facets(research_plan)
    paper_texts = [_paper_text(item) for item in review.papers]
    rows = [_facet_row(facet, paper_texts) for facet in facets]
    required = [row for row in rows if row["required"]]
    covered_required = [row for row in required if row["covered"]]
    coverage_ratio = round(len(covered_required) / max(1, len(required)), 3)
    missing_required = [row for row in required if not row["covered"]]
    warnings = _warnings(review, missing_required, coverage_ratio)
    status = _status(review, missing_required, coverage_ratio)
    return {
        "topic": review.topic or research_plan.topic,
        "domain": research_plan.domain,
        "status": status,
        "coverage_ratio": coverage_ratio,
        "covered_required": len(covered_required),
        "total_required": len(required),
        "curated_papers": len(review.papers),
        "facets": rows,
        "missing_required": [_missing_row(item, research_plan) for item in missing_required],
        "warnings": warnings,
        "required_actions": _required_actions(missing_required, research_plan),
    }


def render_literature_coverage_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 文献覆盖审计：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 领域：{report.get('domain') or '-'}",
        f"- 必需覆盖：{report.get('covered_required', 0)}/{report.get('total_required', 0)}",
        f"- 覆盖率：{float(report.get('coverage_ratio') or 0):.1%}",
        f"- 筛选文献：{report.get('curated_papers', 0)}",
        "",
    ]
    for key, title in [("warnings", "警告"), ("required_actions", "必要动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(
        [
            "## 覆盖表",
            "| 覆盖 | 必需 | 类别 | 名称 | 命中词 | 证据文献 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    facets = report.get("facets") if isinstance(report.get("facets"), list) else []
    if not facets:
        lines.append("| no | yes | - | 无 facet | - | - |")
    for item in facets:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        "yes" if item.get("covered") else "no",
                        "yes" if item.get("required") else "no",
                        _cell(str(item.get("category") or "")),
                        _cell(str(item.get("name") or "")),
                        _cell(", ".join(str(value) for value in item.get("matched_terms", []) if str(value).strip()) or "-"),
                        _cell("；".join(str(value) for value in item.get("evidence_titles", []) if str(value).strip()) or "-"),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _facets(plan: ResearchPlan) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_items("benchmark", plan.benchmarks, True))
    rows.extend(_items("baseline", plan.baselines, True))
    rows.extend(_items("metric", plan.metrics[:6], False))
    rows.extend(_domain_facets(plan.domain))
    return _dedupe_facets(rows)


def _items(category: str, values: list[str], required: bool) -> list[dict[str, Any]]:
    return [
        {
            "category": category,
            "name": str(value),
            "terms": _facet_terms(str(value)),
            "required": required and not _is_internal_process_facet(category, str(value)),
        }
        for value in values
        if str(value).strip()
    ]


def _is_internal_process_facet(category: str, value: str) -> bool:
    if category != "benchmark":
        return False
    lower = value.lower()
    markers = [
        "artifact",
        "diagnostics",
        "human gate",
        "internal",
        "manifest",
        "paper-grade",
        "preflight",
        "probe",
        "release flow",
        "repair queue",
        "runbook",
        "scaffold",
    ]
    return any(marker in lower for marker in markers)


def _domain_facets(domain: str) -> list[dict[str, Any]]:
    if domain == "robotics_motion_planning":
        return [
            _facet("baseline_family", "sampling-based planning", ["rrt", "rrt*", "prm", "sampling based"], True),
            _facet("baseline_family", "trajectory optimization", ["chomp", "stomp", "trajopt", "trajectory optimization"], True),
            _facet("benchmark", "OMPL or MoveIt benchmarking", ["ompl", "moveit", "benchmark"], True),
        ]
    if domain == "bearing_fault_diagnosis":
        return [
            _facet("dataset", "CWRU/Paderborn/XJTU-SY/IMS datasets", ["cwru", "paderborn", "xjtu", "ims bearing"], True),
            _facet("baseline_family", "classical and neural baselines", ["svm", "cnn", "resnet", "transformer", "lstm"], True),
            _facet("risk", "cross-domain/noise robustness", ["domain adaptation", "cross load", "noise", "robust"], True),
        ]
    if domain == "ai_research_agents":
        return [
            _facet("system", "AI Scientist / Agent Laboratory style workflows", ["ai scientist", "agent laboratory", "autonomous scientific discovery"], True),
            _facet("evidence", "citation grounding", ["citation", "grounding", "paperqa", "openscholar", "storm"], True),
            _facet("benchmark", "agent evaluation benchmark", ["mlagentbench", "benchmark", "litqa", "review rubric"], True),
        ]
    return [_facet("generic", "benchmark/baseline coverage", ["benchmark", "baseline", "evaluation"], True)]


def _facet(category: str, name: str, terms: list[str], required: bool) -> dict[str, Any]:
    return {"category": category, "name": name, "terms": terms, "required": required}


def _facet_row(facet: dict[str, Any], paper_texts: list[dict[str, str]]) -> dict[str, Any]:
    terms = [term for term in facet.get("terms", []) if str(term).strip()]
    matches: list[str] = []
    titles: list[str] = []
    for item in paper_texts:
        text = item["text"]
        local = [term for term in terms if _term_matches(str(term), text)]
        if local:
            matches.extend(local)
            titles.append(item["title"])
    return {
        "category": facet.get("category"),
        "name": facet.get("name"),
        "terms": terms[:8],
        "required": bool(facet.get("required")),
        "covered": bool(titles),
        "matched_terms": _unique(matches)[:8],
        "evidence_titles": _unique(titles)[:4],
    }


def _paper_text(paper: Any) -> dict[str, str]:
    title = str(getattr(paper, "title", "") or "")
    text = " ".join(
        [
            title,
            str(getattr(paper, "abstract", "") or ""),
            str(getattr(paper, "venue", "") or ""),
            " ".join(str(item) for item in getattr(paper, "authors", []) or []),
        ]
    )
    return {"title": title, "text": _normalize(text)}


def _facet_terms(value: str) -> list[str]:
    raw = value.replace("*", " star")
    parts = re.findall(r"[A-Za-z][A-Za-z0-9+-]{1,}|[\u4e00-\u9fff]{2,}", raw.lower())
    terms = [part for part in parts if part not in {"with", "and", "the", "dataset", "baseline", "benchmark"}]
    if value.strip():
        terms.append(value.lower().replace("*", " star"))
    return _unique(terms)


def _term_matches(term: str, text: str) -> bool:
    normalized = _normalize(term)
    if not normalized:
        return False
    if normalized in text:
        return True
    if normalized.endswith(" star"):
        return normalized.replace(" star", "*") in text
    return False


def _warnings(review: LiteratureReview, missing_required: list[dict[str, Any]], coverage_ratio: float) -> list[str]:
    warnings: list[str] = []
    if not review.papers:
        warnings.append("筛选文献为空，不能支撑后续 idea 和实验计划。")
    if coverage_ratio < 0.6:
        warnings.append("必需 facet 覆盖率偏低，当前文献池可能遗漏关键 baseline/benchmark。")
    if missing_required:
        warnings.append("缺失必需 facet：" + "；".join(str(item.get("name")) for item in missing_required[:6]))
    return warnings


def _required_actions(missing_required: list[dict[str, Any]], plan: ResearchPlan) -> list[str]:
    if not missing_required:
        return ["当前 curated 文献已覆盖主要 baseline/benchmark，可进入人工审核。"]
    actions = ["补检索缺失 facet 后再批准进入 idea/实验。"]
    for item in missing_required[:6]:
        queries = _suggested_queries_for_facet(item, plan)
        suggestion = queries[0] if queries else f"{plan.topic} {item.get('name') or ''}"
        actions.append(f"{item.get('category')}: {item.get('name')}；建议检索 `{suggestion}`。")
    return actions


def _status(review: LiteratureReview, missing_required: list[dict[str, Any]], coverage_ratio: float) -> str:
    if not review.papers:
        return "block"
    if coverage_ratio < 0.45:
        return "needs_literature"
    if missing_required:
        return "needs_coverage"
    return "pass"


def _missing_row(row: dict[str, Any], plan: ResearchPlan) -> dict[str, Any]:
    terms = [str(term) for term in row.get("terms", []) if str(term).strip()]
    return {
        "category": row.get("category"),
        "name": row.get("name"),
        "terms": terms[:8],
        "suggested_queries": _suggested_queries_for_facet(row, plan),
    }


def _suggested_queries_for_facet(row: dict[str, Any], plan: ResearchPlan) -> list[str]:
    name = str(row.get("name") or "").strip()
    if not name:
        return []
    base = _query_base(plan)
    category = str(row.get("category") or "").lower()
    terms = [str(term) for term in row.get("terms", []) if str(term).strip()]
    primary_terms = " ".join(terms[:4]) or name
    modifier = _category_modifier(category)
    values = [
        _clean_query(f"{base} {primary_terms} {modifier}"),
        _clean_query(f'"{name}" {base}'),
    ]
    return _unique([value for value in values if value])[:3]


def _query_base(plan: ResearchPlan) -> str:
    for query in plan.search_queries:
        value = str(query).strip()
        if value:
            return value
    return str(plan.topic).strip()


def _category_modifier(category: str) -> str:
    if category in {"benchmark", "dataset"}:
        return "benchmark dataset evaluation"
    if category in {"baseline", "baseline_family"}:
        return "baseline comparison evaluation"
    if category == "metric":
        return "metric evaluation reproducibility"
    if category in {"evidence", "system"}:
        return "citation grounding workflow evaluation"
    if category == "risk":
        return "robustness evaluation failure analysis"
    return "benchmark baseline evaluation"


def _clean_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("|", " ")).strip()


def _dedupe_facets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("category")), str(row.get("name")).lower())
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("-", " ").replace("_", " ")).strip()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
