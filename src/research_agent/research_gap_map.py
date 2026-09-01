from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text
from .literature_context import retrieve_chunks
from .models import LiteratureContext, LiteratureReview, ResearchPlan


RESEARCH_GAP_MAP_JSON = "02-research-gap-map.json"
RESEARCH_GAP_MAP_MD = "02-research-gap-map.md"


def write_research_gap_map_artifacts(
    topic: str,
    research_plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext | None,
    coverage_report: dict[str, Any] | None,
    run_dir: Path,
    review_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_research_gap_map(topic, research_plan, review, context, coverage_report, review_constraints=review_constraints)
    write_json(run_dir / RESEARCH_GAP_MAP_JSON, report)
    write_text(run_dir / RESEARCH_GAP_MAP_MD, render_research_gap_map_markdown(report))
    return report


def build_research_gap_map(
    topic: str,
    research_plan: ResearchPlan,
    review: LiteratureReview,
    context: LiteratureContext | None,
    coverage_report: dict[str, Any] | None,
    review_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _gap_candidates(research_plan, review, coverage_report or {}, review_constraints)
    gaps = [_gap_row(index, row, research_plan, context) for index, row in enumerate(rows, start=1)]
    ready = [item for item in gaps if item.get("testability") == "ready"]
    status = _status(gaps, ready)
    warnings = _warnings(gaps, ready, context)
    actions = _recommended_actions(gaps, research_plan)
    return {
        "topic": topic or review.topic or research_plan.topic,
        "domain": research_plan.domain,
        "status": status,
        "gap_count": len(gaps),
        "ready_gap_count": len(ready),
        "context_chunks_available": len(context.chunks) if context is not None else 0,
        "gaps": gaps,
        "warnings": warnings,
        "recommended_actions": actions,
    }


def render_research_gap_map_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 研究空白矩阵：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 领域：{report.get('domain') or '-'}",
        f"- Gap：{report.get('ready_gap_count', 0)}/{report.get('gap_count', 0)} ready",
        f"- 可用 chunk：{report.get('context_chunks_available', 0)}",
        "",
    ]
    for key, title in [("warnings", "警告"), ("recommended_actions", "建议动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    lines.extend(
        [
            "## Gap 表",
            "| ID | 可检验性 | 证据 | 来源 | Gap | Baseline | Benchmark/Data | 指标 | 下一步 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    gaps = report.get("gaps") if isinstance(report.get("gaps"), list) else []
    if not gaps:
        lines.append("| - | block | none | - | 未发现结构化研究空白 | - | - | - | 补充文献综述和 coverage 后重试 |")
    for item in gaps:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("gap_id") or "")),
                    _cell(str(item.get("testability") or "")),
                    _cell(str(item.get("evidence_strength") or "")),
                    _cell(str(item.get("source") or "")),
                    _cell(str(item.get("gap") or "")),
                    _cell(str(item.get("baseline") or "-")),
                    _cell(str(item.get("benchmark_or_dataset") or "-")),
                    _cell(", ".join(str(value) for value in item.get("metrics", []) if str(value).strip()) or "-"),
                    _cell(str(item.get("next_action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 使用方式",
            "- Idea 生成必须优先选择 `ready` gap；`needs_evidence` gap 先补检索或补 seed paper。",
            "- 每个 gap 同时给出 baseline、benchmark/data、指标和 evidence chunks，供后续 novelty、exploration map 和实验计划复核。",
        ]
    )
    return "\n".join(lines)


def research_gap_map_prompt_context(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    gaps = report.get("gaps") if isinstance(report.get("gaps"), list) else []
    payload = []
    for item in gaps[:8]:
        if not isinstance(item, dict):
            continue
        payload.append(
            {
                "gap_id": item.get("gap_id"),
                "testability": item.get("testability"),
                "gap": item.get("gap"),
                "baseline": item.get("baseline"),
                "benchmark_or_dataset": item.get("benchmark_or_dataset"),
                "metrics": item.get("metrics"),
                "evidence_keys": item.get("evidence_keys"),
                "evidence_chunks": item.get("evidence_chunks"),
                "hypothesis_seed": item.get("hypothesis_seed"),
                "experiment_hint": item.get("experiment_hint"),
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def best_gap_for_text(report: dict[str, Any] | None, text: str = "") -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    gaps = [item for item in report.get("gaps", []) if isinstance(item, dict)]
    if not gaps:
        return {}
    terms = set(_terms(text))
    best: dict[str, Any] = {}
    best_score = -1
    for item in gaps:
        item_text = " ".join(str(item.get(key) or "") for key in ["gap", "baseline", "benchmark_or_dataset", "hypothesis_seed"])
        overlap = len(terms & set(_terms(item_text))) if terms else 0
        readiness_bonus = 2 if item.get("testability") == "ready" else 0
        score = overlap + readiness_bonus
        if score > best_score:
            best = item
            best_score = score
    return best


def _gap_candidates(
    research_plan: ResearchPlan,
    review: LiteratureReview,
    coverage_report: dict[str, Any],
    review_constraints: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gap in review.gaps[:6]:
        rows.append({"source": "literature_gap", "gap": str(gap), "suggested_queries": []})
    missing = coverage_report.get("missing_required") if isinstance(coverage_report.get("missing_required"), list) else []
    for item in missing[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        category = str(item.get("category") or "facet").strip()
        if name:
            rows.append(
                {
                    "source": "coverage_gap",
                    "gap": f"缺少 {category} 证据：{name}",
                    "facet_category": category,
                    "facet_name": name,
                    "suggested_queries": _as_strings(item.get("suggested_queries"))[:3],
                }
            )
    for constraint in _constraints(review_constraints)[:4]:
        text = str(constraint.get("text") or "").strip()
        if text:
            rows.append(
                {
                    "source": "review_constraint",
                    "gap": f"人工约束需要落实：{text}",
                    "facet_category": str(constraint.get("category") or ""),
                    "suggested_queries": [],
                }
            )
    if not rows:
        for theme in review.themes[:3]:
            rows.append({"source": "theme_gap", "gap": f"围绕主题补充可检验问题：{theme}", "suggested_queries": []})
    if not rows:
        rows.append({"source": "plan_gap", "gap": research_plan.objective or research_plan.topic, "suggested_queries": []})
    return _dedupe_gap_rows(rows)[:10]


def _gap_row(
    index: int,
    row: dict[str, Any],
    research_plan: ResearchPlan,
    context: LiteratureContext | None,
) -> dict[str, Any]:
    gap_text = str(row.get("gap") or "").strip()
    retrieved = retrieve_chunks(context, gap_text, top_k=5) if context is not None and gap_text else []
    chunks = [chunk for chunk in retrieved if _chunk_matches(gap_text, chunk)][:3]
    evidence_chunks = [chunk.chunk_id for chunk in chunks]
    evidence_keys: list[str] = []
    for chunk in chunks:
        if chunk.citation_key not in evidence_keys:
            evidence_keys.append(chunk.citation_key)
    baseline = _select_baseline(gap_text, row, research_plan)
    benchmark = _select_benchmark(gap_text, row, research_plan)
    metrics = _select_metrics(gap_text, research_plan)
    strength = _evidence_strength(evidence_keys, evidence_chunks)
    testability = _testability(strength, baseline, benchmark, metrics)
    return {
        "gap_id": f"G{index}",
        "source": row.get("source") or "unknown",
        "gap": gap_text,
        "facet_category": row.get("facet_category") or "",
        "facet_name": row.get("facet_name") or "",
        "evidence_strength": strength,
        "testability": testability,
        "evidence_keys": evidence_keys,
        "evidence_chunks": evidence_chunks,
        "baseline": baseline,
        "benchmark_or_dataset": benchmark,
        "metrics": metrics,
        "hypothesis_seed": _hypothesis_seed(gap_text, baseline, benchmark),
        "experiment_hint": _experiment_hint(baseline, benchmark, metrics),
        "suggested_queries": _as_strings(row.get("suggested_queries")) or _suggested_queries(gap_text, research_plan),
        "next_action": _next_action(testability),
    }


def _select_baseline(gap: str, row: dict[str, Any], plan: ResearchPlan) -> str:
    if str(row.get("facet_category") or "").lower() in {"baseline", "baseline_family"}:
        return str(row.get("facet_name") or "").strip()
    return _best_matching(gap, plan.baselines) or (plan.baselines[0] if plan.baselines else "")


def _select_benchmark(gap: str, row: dict[str, Any], plan: ResearchPlan) -> str:
    if str(row.get("facet_category") or "").lower() in {"benchmark", "dataset"}:
        return str(row.get("facet_name") or "").strip()
    return _best_matching(gap, plan.benchmarks) or (plan.benchmarks[0] if plan.benchmarks else "")


def _select_metrics(gap: str, plan: ResearchPlan) -> list[str]:
    matches = [_best_matching(gap, plan.metrics)]
    values = [item for item in matches if item]
    for metric in plan.metrics:
        if metric not in values:
            values.append(metric)
        if len(values) >= 3:
            break
    return values[:3]


def _best_matching(text: str, values: list[str]) -> str:
    terms = set(_terms(text))
    best = ""
    best_score = 0
    for value in values:
        value_terms = set(_terms(value))
        score = len(terms & value_terms)
        if score > best_score:
            best = value
            best_score = score
    return best


def _evidence_strength(keys: list[str], chunks: list[str]) -> str:
    evidence_count = len(set(keys + chunks))
    if evidence_count >= 4:
        return "strong"
    if evidence_count >= 2:
        return "moderate"
    if evidence_count == 1:
        return "weak"
    return "none"


def _testability(strength: str, baseline: str, benchmark: str, metrics: list[str]) -> str:
    if strength in {"strong", "moderate"} and baseline and benchmark and len(metrics) >= 2:
        return "ready"
    if strength == "none":
        return "needs_evidence"
    if not baseline:
        return "needs_baseline"
    if not benchmark:
        return "needs_benchmark"
    if len(metrics) < 2:
        return "needs_metrics"
    return "review"


def _next_action(testability: str) -> str:
    if testability == "ready":
        return "进入 idea 生成和实验草案，保持 baseline/benchmark/metric 对齐。"
    if testability == "needs_evidence":
        return "先补 DOI/URL seed、全文或检索式，增加可核对文献证据。"
    if testability == "needs_baseline":
        return "先明确最直接 baseline，并补对应文献或 benchmark manifest。"
    if testability == "needs_benchmark":
        return "先确认公开 benchmark/data 来源、版本、许可和评价协议。"
    if testability == "needs_metrics":
        return "先明确主指标、辅助指标和重复统计协议。"
    return "人工复核 gap 边界后再推进 idea 或补检索。"


def _hypothesis_seed(gap: str, baseline: str, benchmark: str) -> str:
    parts = [f"围绕“{_short(gap, 80)}”提出可检验假设"]
    if baseline:
        parts.append(f"相对 {baseline} 改善关键指标")
    if benchmark:
        parts.append(f"在 {benchmark} 上验证")
    return "，".join(parts) + "。"


def _experiment_hint(baseline: str, benchmark: str, metrics: list[str]) -> str:
    metric_text = "、".join(metrics[:3]) if metrics else "核心指标"
    baseline_text = baseline or "明确 baseline"
    benchmark_text = benchmark or "公开 benchmark/data"
    return f"在 {benchmark_text} 上比较 candidate、{baseline_text} 和 ablation，并报告 {metric_text}。"


def _suggested_queries(gap: str, plan: ResearchPlan) -> list[str]:
    base = plan.search_queries[0] if plan.search_queries else plan.topic
    return [_clean_query(f"{base} {_short(gap, 80)} benchmark baseline")]


def _status(gaps: list[dict[str, Any]], ready: list[dict[str, Any]]) -> str:
    if not gaps:
        return "block"
    if ready:
        return "pass"
    if any(item.get("testability") != "needs_evidence" for item in gaps):
        return "review"
    return "needs_evidence"


def _warnings(gaps: list[dict[str, Any]], ready: list[dict[str, Any]], context: LiteratureContext | None) -> list[str]:
    warnings: list[str] = []
    if context is None or not context.chunks:
        warnings.append("没有可用文献 chunk，gap 只能作为检索/人工规划提示。")
    if gaps and not ready:
        warnings.append("尚无 ready gap；idea 生成前应补齐证据、baseline、benchmark 或指标。")
    evidence_poor = [item for item in gaps if item.get("evidence_strength") in {"none", "weak"}]
    if evidence_poor:
        warnings.append(f"{len(evidence_poor)} 个 gap 证据较弱，优先补 DOI/URL seed 或全文。")
    return warnings


def _recommended_actions(gaps: list[dict[str, Any]], plan: ResearchPlan) -> list[str]:
    if not gaps:
        return ["补充文献综述和 coverage 后重新生成 gap map。"]
    ready = [item for item in gaps if item.get("testability") == "ready"]
    if ready:
        return [f"优先让 ideation 围绕 {ready[0].get('gap_id')}：{_short(str(ready[0].get('gap') or ''), 120)}。"]
    actions = []
    for item in gaps[:3]:
        queries = item.get("suggested_queries") if isinstance(item.get("suggested_queries"), list) else []
        query = str(queries[0]) if queries else _clean_query(f"{plan.topic} {item.get('gap') or ''}")
        actions.append(f"{item.get('gap_id')}: 先补检索 `{query}`。")
    return actions


def _constraints(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    values = report.get("constraints") if isinstance(report, dict) else None
    if not isinstance(values, list):
        return []
    return [dict(item) for item in values if isinstance(item, dict)]


def _dedupe_gap_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = _clean_query(str(row.get("gap") or "")).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _terms(text: str) -> list[str]:
    lower = text.lower()
    return re.findall(r"[a-z][a-z0-9*+-]{1,}|[\u4e00-\u9fff]{2,}", lower)


def _chunk_matches(query: str, chunk: Any) -> bool:
    terms = set(_terms(query))
    if not terms:
        return False
    text = f"{getattr(chunk, 'title', '')} {getattr(chunk, 'text', '')}".lower()
    return any(term in text for term in terms)


def _short(text: str, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean_query(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("|", " ")).strip()


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
