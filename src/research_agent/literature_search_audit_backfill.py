from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .literature import literature_source_health_report, render_literature_source_health_markdown
from .literature_rescue_backfill import _load_raw_review, _load_research_plan
from .literature_search_strategy import render_literature_search_strategy_markdown
from .models import LiteratureReview, ResearchPlan
from .query_execution_audit import QUERY_EXECUTION_AUDIT_JSON, QUERY_EXECUTION_AUDIT_MD, build_query_execution_audit, render_query_execution_audit_markdown


LITERATURE_SEARCH_STRATEGY_JSON = "01-literature-search-strategy.json"
LITERATURE_SEARCH_STRATEGY_MD = "01-literature-search-strategy.md"
LITERATURE_SOURCE_HEALTH_JSON = "01-literature-source-health.json"
LITERATURE_SOURCE_HEALTH_MD = "01-literature-source-health.md"


def backfill_literature_search_audits(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "scanned_runs": 0,
        "written_runs": 0,
        "would_write_runs": 0,
        "written_search_strategy": 0,
        "written_source_health": 0,
        "written_query_execution": 0,
        "fallback_research_plan": 0,
        "reconstructed_search_strategy": 0,
        "reconstructed_source_health": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "skipped_no_literature": 0,
        "errors": [],
        "items": [],
    }
    candidates = 0
    for run_dir in run_dirs:
        if not (run_dir / "state.json").exists():
            report["skipped_no_state"] += 1
            continue
        if limit > 0 and candidates >= limit:
            break
        candidates += 1
        report["scanned_runs"] += 1
        existing = {
            "search_strategy": _artifact_pair_exists(run_dir, LITERATURE_SEARCH_STRATEGY_JSON, LITERATURE_SEARCH_STRATEGY_MD),
            "source_health": _artifact_pair_exists(run_dir, LITERATURE_SOURCE_HEALTH_JSON, LITERATURE_SOURCE_HEALTH_MD),
            "query_execution": _artifact_pair_exists(run_dir, QUERY_EXECUTION_AUDIT_JSON, QUERY_EXECUTION_AUDIT_MD),
        }
        if all(existing.values()) and not force:
            report["skipped_existing"] += 1
            query = _read_json(run_dir / QUERY_EXECUTION_AUDIT_JSON)
            source = _read_json(run_dir / LITERATURE_SOURCE_HEALTH_JSON)
            strategy = _read_json(run_dir / LITERATURE_SEARCH_STRATEGY_JSON)
            report["items"].append(_item(run_dir, "skipped_existing", strategy, source, query, meta={}))
            continue
        try:
            strategy, source_health, query_execution, meta = build_literature_search_audits_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, {}, {}, meta={}, error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, {}, {}, meta={}, error=str(exc)))
            continue
        _accumulate_meta(report, meta)
        planned_actions = _planned_actions(existing, force)
        action = "overwrite" if force and any(existing.values()) else "write"
        if dry_run:
            report["would_write_runs"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", strategy, source_health, query_execution, meta=meta, artifact_actions=planned_actions))
            continue
        if force or not existing["search_strategy"]:
            write_json(run_dir / LITERATURE_SEARCH_STRATEGY_JSON, strategy)
            write_text(run_dir / LITERATURE_SEARCH_STRATEGY_MD, render_literature_search_strategy_markdown(strategy))
            report["written_search_strategy"] += 1
        if force or not existing["source_health"]:
            review_for_source = _review_with_source_health(_load_raw_review(run_dir), source_health)
            write_json(run_dir / LITERATURE_SOURCE_HEALTH_JSON, source_health)
            write_text(run_dir / LITERATURE_SOURCE_HEALTH_MD, render_literature_source_health_markdown(review_for_source))
            report["written_source_health"] += 1
        if force or not existing["query_execution"]:
            write_json(run_dir / QUERY_EXECUTION_AUDIT_JSON, query_execution)
            write_text(run_dir / QUERY_EXECUTION_AUDIT_MD, render_query_execution_audit_markdown(query_execution))
            report["written_query_execution"] += 1
        report["written_runs"] += 1
        report["items"].append(_item(run_dir, action, strategy, source_health, query_execution, meta=meta, artifact_actions=planned_actions))
    return report


def build_literature_search_audits_for_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, bool]]:
    raw_review = _load_raw_review(run_dir)
    research_plan, fallback_research_plan = _load_research_plan(run_dir, raw_review.topic or run_dir.name)
    source_review, reconstructed_source_health = _source_health_review(raw_review)
    source_health = literature_source_health_report(source_review)
    strategy, reconstructed_search_strategy = _search_strategy_report(run_dir, source_review, research_plan, source_health)
    review_for_query = replace(source_review, search_strategy=strategy)
    rerank_report = _read_json(run_dir / "01-literature-rerank.json")
    query_execution = build_query_execution_audit(research_plan, review_for_query, rerank_report, source_health)
    meta = {
        "fallback_research_plan": fallback_research_plan,
        "reconstructed_search_strategy": reconstructed_search_strategy,
        "reconstructed_source_health": reconstructed_source_health,
    }
    return strategy, source_health, query_execution, meta


def render_literature_search_audit_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Search Audit Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 run：{report.get('written_runs', 0)}",
        f"- 将写入 run：{report.get('would_write_runs', 0)}",
        f"- 写入 search strategy：{report.get('written_search_strategy', 0)}",
        f"- 写入 source health：{report.get('written_source_health', 0)}",
        f"- 写入 query execution：{report.get('written_query_execution', 0)}",
        f"- 规则 plan fallback：{report.get('fallback_research_plan', 0)}",
        f"- 重建 search strategy：{report.get('reconstructed_search_strategy', 0)}",
        f"- 重建 source health：{report.get('reconstructed_source_health', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 01-literature-search-strategy.*、01-literature-source-health.*、01-query-execution-audit.*；不会批准 gate、不会恢复 pipeline、不会执行补检索。",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        for item in errors[:20]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('run_id') or '-'}: {item.get('error') or '-'}")
        lines.append("")
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if items:
        lines.extend(
            [
                "## Runs",
                "",
                "| Run | Action | Query Audit | Search Strategy | Sources | Success | Failed | Rate Limit | Fallbacks | Artifacts |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("run_id") or "")),
                        _cell(str(item.get("action") or "")),
                        _cell(str(item.get("query_execution_status") or "-")),
                        _cell(str(item.get("search_strategy_status") or "-")),
                        str(item.get("source_count") or 0),
                        str(item.get("sources_with_success") or 0),
                        str(item.get("failed_sources") or 0),
                        str(item.get("rate_limited_sources") or 0),
                        _cell(", ".join(_string_list(item.get("fallbacks"))) or "-"),
                        _cell(", ".join(_string_list(item.get("artifact_actions"))) or "-"),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _source_health_review(review: LiteratureReview) -> tuple[LiteratureReview, bool]:
    if review.source_health:
        return review, False
    sources = _source_rows_from_diagnostics(review)
    if sources:
        return replace(review, source_health=sources), True
    return review, True


def _search_strategy_report(
    run_dir: Path,
    review: LiteratureReview,
    research_plan: ResearchPlan,
    source_health: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    existing = _read_json(run_dir / LITERATURE_SEARCH_STRATEGY_JSON)
    if existing:
        return existing, False
    if review.search_strategy:
        return dict(review.search_strategy), False
    selected_queries = _diagnostic_queries(review.source_diagnostics)
    reconstructed_from = "legacy_diagnostics"
    if not selected_queries:
        selected_queries = [str(item).strip() for item in research_plan.search_queries if str(item).strip()]
        reconstructed_from = "research_plan_fallback"
    intents = [_query_intent(query) for query in selected_queries]
    warnings = []
    if reconstructed_from == "legacy_diagnostics":
        warnings.append("历史 run 缺少结构化检索策略，已从 diagnostics 文本恢复 selected queries。")
    else:
        warnings.append("历史 run 缺少结构化检索策略和可见检索式，已使用 research plan query 生成最小审计。")
    recommendations = ["后续 run 会自动生成完整候选检索式、风险和选择理由。"]
    if reconstructed_from == "research_plan_fallback":
        recommendations.insert(0, "下一轮优先把实际执行过的 query 写入 01-literature-search-strategy.json。")
    return (
        {
            "topic": review.topic or research_plan.topic,
            "provider": _strategy_provider(review, source_health),
            "sources": _strategy_sources(review, source_health),
            "max_queries": len(selected_queries),
            "selected_queries": selected_queries,
            "candidates": [
                {
                    "query": query,
                    "origin": reconstructed_from,
                    "intent": intent,
                    "priority": 80 if reconstructed_from == "legacy_diagnostics" else 70,
                    "selected": True,
                    "rationale": "从历史 run 可见信息恢复的最小检索策略。",
                    "risk": "",
                }
                for query, intent in zip(selected_queries, intents)
            ],
            "status": "legacy_summary",
            "quality_score": 0.0,
            "selected_intents": _unique(intents),
            "missing_required_intents": [],
            "weak_selected_queries": [],
            "warnings": warnings,
            "recommendations": recommendations,
        },
        True,
    )


def _source_rows_from_diagnostics(review: LiteratureReview) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in review.source_diagnostics:
        text = str(line).strip()
        if not text or text.startswith("LLM 检索式:") or text.startswith("检索式:") or text.startswith("合并去重后"):
            continue
        offline = re.match(r"^(?P<source>[a-z_]+): 使用内置种子文献库。$", text, flags=re.I)
        if offline:
            source = str(offline.group("source") or "").strip().lower()
            row = rows.setdefault(source, _empty_source_row(source))
            row["status"] = "offline_ranked"
            row["returned"] = max(_safe_int(row.get("returned")), len(review.papers))
            continue
        aggregate = re.match(
            r"^(?P<source>[a-z_]+): (?:(?P<queries>\d+) 个检索式)?返回 (?P<returned>\d+) 条，用时 (?P<elapsed>[0-9.]+)s(?:，状态 (?P<status>[a-z_]+))?\.?$",
            text,
            flags=re.I,
        )
        if aggregate:
            source = str(aggregate.group("source") or "").strip().lower()
            row = rows.setdefault(source, _empty_source_row(source))
            row["queries"] = _safe_int(row.get("queries")) + max(0, _safe_int(aggregate.group("queries")))
            row["returned"] = _safe_int(row.get("returned")) + _safe_int(aggregate.group("returned"))
            row["elapsed_seconds"] = round(_safe_float(row.get("elapsed_seconds")) + _safe_float(aggregate.group("elapsed")), 3)
            if aggregate.group("status"):
                row["status"] = str(aggregate.group("status") or "").strip().lower()
            continue
        query_failure = re.match(r"^(?P<source>[a-z_]+): query='(?P<query>.+)' 检索失败：HTTP (?P<code>\d+)", text, flags=re.I)
        if query_failure:
            source = str(query_failure.group("source") or "").strip().lower()
            code = _safe_int(query_failure.group("code"))
            row = rows.setdefault(source, _empty_source_row(source))
            row["queries"] = _safe_int(row.get("queries")) + 1
            row["errors"] = _safe_int(row.get("errors")) + 1
            if code == 429:
                row["rate_limited"] = True
            query_results = row.get("query_results") if isinstance(row.get("query_results"), list) else []
            query_results.append(
                {
                    "source": source,
                    "query": str(query_failure.group("query") or "").strip(),
                    "status": "rate_limited" if code == 429 else "failed",
                    "returned": 0,
                    "errors": 1,
                    "rate_limited": code == 429,
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "stale_cache_uses": 0,
                }
            )
            row["query_results"] = query_results
            continue
        source_failure = re.match(r"^(?P<source>[a-z_]+): 检索失败：HTTP (?P<code>\d+)", text, flags=re.I)
        if source_failure:
            source = str(source_failure.group("source") or "").strip().lower()
            code = _safe_int(source_failure.group("code"))
            row = rows.setdefault(source, _empty_source_row(source))
            row["queries"] = max(1, _safe_int(row.get("queries")))
            row["errors"] = _safe_int(row.get("errors")) + 1
            if code == 429:
                row["rate_limited"] = True
            continue
    if not rows and _only_offline_papers(review):
        row = _empty_source_row("offline")
        row["status"] = "offline_ranked"
        row["returned"] = len(review.papers)
        rows["offline"] = row
    finalized = [_finalize_source_row(item) for item in rows.values()]
    return sorted(finalized, key=lambda item: str(item.get("source") or ""))


def _review_with_source_health(review: LiteratureReview, source_health: dict[str, Any]) -> LiteratureReview:
    sources = source_health.get("sources") if isinstance(source_health.get("sources"), list) else []
    return replace(review, source_health=[dict(item) for item in sources if isinstance(item, dict)])


def _artifact_pair_exists(run_dir: Path, json_name: str, md_name: str) -> bool:
    return (run_dir / json_name).exists() and (run_dir / md_name).exists()


def _planned_actions(existing: dict[str, bool], force: bool) -> list[str]:
    actions: list[str] = []
    for name in ["search_strategy", "source_health", "query_execution"]:
        if force and existing.get(name):
            actions.append(f"overwrite_{name}")
        elif not existing.get(name):
            actions.append(f"write_{name}")
    return actions


def _item(
    run_dir: Path,
    action: str,
    strategy: dict[str, Any],
    source_health: dict[str, Any],
    query_execution: dict[str, Any],
    *,
    meta: dict[str, bool],
    artifact_actions: list[str] | None = None,
    error: str = "",
) -> dict[str, Any]:
    source_coverage = query_execution.get("source_coverage") if isinstance(query_execution.get("source_coverage"), dict) else {}
    return {
        "run_id": run_dir.name,
        "action": action,
        "search_strategy_status": str(strategy.get("status") or ""),
        "query_execution_status": str(query_execution.get("status") or ""),
        "source_count": _safe_int(source_health.get("total_sources")),
        "sources_with_success": _safe_int(source_coverage.get("sources_with_success")),
        "failed_sources": _safe_int(source_coverage.get("failed_sources") or source_health.get("failed_sources")),
        "rate_limited_sources": _safe_int(source_coverage.get("rate_limited_sources") or source_health.get("rate_limited_sources")),
        "selected_queries": _safe_int(query_execution.get("selected_query_count")),
        "fallbacks": _fallbacks(meta),
        "artifact_actions": artifact_actions or [],
        "error": error,
    }


def _accumulate_meta(report: dict[str, Any], meta: dict[str, bool]) -> None:
    if meta.get("fallback_research_plan"):
        report["fallback_research_plan"] += 1
    if meta.get("reconstructed_search_strategy"):
        report["reconstructed_search_strategy"] += 1
    if meta.get("reconstructed_source_health"):
        report["reconstructed_source_health"] += 1


def _fallbacks(meta: dict[str, bool]) -> list[str]:
    rows: list[str] = []
    if meta.get("fallback_research_plan"):
        rows.append("research_plan")
    if meta.get("reconstructed_search_strategy"):
        rows.append("search_strategy")
    if meta.get("reconstructed_source_health"):
        rows.append("source_health")
    return rows


def _diagnostic_queries(lines: list[str]) -> list[str]:
    for prefix in ["检索式:", "LLM 检索式:"]:
        for line in lines:
            text = str(line).strip()
            if not text.startswith(prefix):
                continue
            queries = [part.strip() for part in text.split(":", 1)[-1].split("|") if part.strip()]
            if queries:
                return _unique(queries)
    return []


def _strategy_provider(review: LiteratureReview, source_health: dict[str, Any]) -> str:
    if any(str(line).strip().startswith("offline:") for line in review.source_diagnostics):
        return "offline"
    sources = _strategy_sources(review, source_health)
    if sources and any(source != "offline" for source in sources):
        return "online"
    return "unknown"


def _strategy_sources(review: LiteratureReview, source_health: dict[str, Any]) -> list[str]:
    from_health = [
        str(item.get("source") or "").strip().lower()
        for item in source_health.get("sources", [])
        if isinstance(item, dict) and str(item.get("source") or "").strip()
    ]
    if from_health:
        return _unique(from_health)
    from_papers = [
        str(source).strip().lower()
        for paper in review.papers
        for source in (paper.sources or [paper.source])
        if str(source).strip()
    ]
    return _unique(from_papers)


def _query_intent(query: str) -> str:
    lower = query.lower()
    if any(term in lower for term in ["benchmark", "dataset", "ompl", "cwru", "paderborn", "xjtu"]):
        return "benchmark"
    if any(term in lower for term in ["baseline", "rrt", "prm", "chomp", "stomp", "trajopt", "cnn", "transformer"]):
        return "baseline"
    if any(term in lower for term in ["review", "survey", "literature"]):
        return "survey"
    if any(term in lower for term in ["recent", "latest", "2024", "2025", "2026", "state of the art"]):
        return "recent"
    if any(term in lower for term in ["experiment", "evaluation", "metric"]):
        return "experiment"
    return "method"


def _only_offline_papers(review: LiteratureReview) -> bool:
    paper_sources = {
        str(source).strip().lower()
        for paper in review.papers
        for source in (paper.sources or [paper.source])
        if str(source).strip()
    }
    return bool(paper_sources) and paper_sources <= {"offline", "manual_seed"}


def _empty_source_row(source: str) -> dict[str, Any]:
    return {
        "source": source,
        "status": "",
        "queries": 0,
        "returned": 0,
        "errors": 0,
        "rate_limited": False,
        "elapsed_seconds": 0.0,
        "cache_hits": 0,
        "cache_misses": 0,
        "stale_cache_uses": 0,
        "query_results": [],
    }


def _finalize_source_row(row: dict[str, Any]) -> dict[str, Any]:
    if str(row.get("status") or "") == "offline_ranked":
        return row
    returned = _safe_int(row.get("returned"))
    errors = _safe_int(row.get("errors"))
    rate_limited = row.get("rate_limited") is True
    if rate_limited and returned == 0:
        status = "rate_limited"
    elif errors and returned:
        status = "partial"
    elif errors:
        status = "failed"
    elif returned:
        status = "ok"
    else:
        status = "ok"
    return {**row, "status": status}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


