from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable
import re

from .artifacts import write_json, write_text, cell as _cell
from .config import LiteratureConfig
from .literature import build_literature_review_from_papers
from .literature_sources import OnlineLiteratureClient, deduplicate_papers, filter_relevant_papers, rank_papers
from .llm import LLM
from .models import LiteratureReview, Paper


LITERATURE_RESCUE_EXECUTION_JSON = "01-literature-rescue-execution.json"
LITERATURE_RESCUE_EXECUTION_MD = "01-literature-rescue-execution.md"

_TRIGGER_STATUSES = {"block", "needs_rescue_search", "needs_manual_seed"}


def write_literature_rescue_execution_artifacts(
    topic: str,
    config: LiteratureConfig,
    llm: LLM,
    raw_review: LiteratureReview,
    rescue_report: dict[str, Any],
    run_dir: Path,
    client_factory: Callable[[LiteratureConfig], OnlineLiteratureClient] | None = None,
    repair_tasks: list[dict[str, Any]] | None = None,
) -> tuple[LiteratureReview, dict[str, Any]]:
    review, report = execute_literature_rescue(
        topic,
        config,
        llm,
        raw_review,
        rescue_report,
        client_factory=client_factory,
        repair_tasks=repair_tasks,
    )
    write_json(run_dir / LITERATURE_RESCUE_EXECUTION_JSON, report)
    write_text(run_dir / LITERATURE_RESCUE_EXECUTION_MD, render_literature_rescue_execution_markdown(report))
    return review, report


def execute_literature_rescue(
    topic: str,
    config: LiteratureConfig,
    llm: LLM,
    raw_review: LiteratureReview,
    rescue_report: dict[str, Any],
    client_factory: Callable[[LiteratureConfig], OnlineLiteratureClient] | None = None,
    repair_tasks: list[dict[str, Any]] | None = None,
) -> tuple[LiteratureReview, dict[str, Any]]:
    task_queries, selected_task_ids, query_task_ids = _selected_task_queries(repair_tasks or [])
    selected_queries = _dedupe_queries([*task_queries, *_selected_queries(rescue_report)])[:6]
    trigger_status = str(rescue_report.get("status") or "unknown")
    if config.provider not in {"online", "auto"}:
        return raw_review, _report("not_applicable", trigger_status, raw_review, [], [], [], [], "当前 literature.provider 不是 online/auto。", repair_task_ids=selected_task_ids)
    if trigger_status not in _TRIGGER_STATUSES and not task_queries:
        return raw_review, _report("skipped", trigger_status, raw_review, selected_queries, [], [], [], "补检索计划状态未要求自动补检索。", repair_task_ids=selected_task_ids, query_outcomes=_not_executed_outcomes(selected_queries, query_task_ids))
    if not selected_queries:
        return raw_review, _report("skipped", trigger_status, raw_review, [], [], [], [], "没有 priority >= 94 的补检索式或 agent 检索修复任务。", repair_task_ids=selected_task_ids)

    rescue_config = replace(
        config,
        max_search_queries=max(config.max_search_queries, len(selected_queries)),
        max_papers=max(config.max_papers, 12),
    )
    client = (client_factory or OnlineLiteratureClient)(rescue_config)
    rescue_papers, diagnostics = client.search(topic, selected_queries)
    merged = _merged_papers(raw_review.papers, rescue_papers, topic, selected_queries, max(1, config.max_papers))
    new_unique = _new_unique_count(raw_review.papers, rescue_papers)
    source_health = [*(raw_review.source_health or []), *client.source_health]
    merged_diagnostics = [
        *raw_review.source_diagnostics,
        "自动补检索: 执行 " + " | ".join(selected_queries),
        *[f"自动补检索: {item}" for item in diagnostics],
        f"自动补检索: 新候选 {len(rescue_papers)} 条，新增去重候选 {new_unique} 条，最终保留 {len(merged)} 条。",
    ]
    if not rescue_papers or not new_unique:
        status = "no_new_papers"
        updated = False
        final_review = raw_review
    else:
        status = "executed"
        updated = True
        final_review = build_literature_review_from_papers(
            topic,
            merged,
            llm,
            merged_diagnostics,
            source_health=source_health,
            search_strategy=raw_review.search_strategy,
        )
    query_outcomes = _query_outcomes(selected_queries, query_task_ids, raw_review.papers, rescue_papers, final_review.papers)
    return final_review, _report(status, trigger_status, final_review, selected_queries, diagnostics, client.source_health, rescue_papers, "", updated, new_unique, len(raw_review.papers), selected_task_ids, query_outcomes=query_outcomes)


def render_literature_rescue_execution_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 自动补检索执行：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 触发状态：{report.get('trigger_status') or '-'}",
        f"- 是否更新文献池：{'yes' if report.get('updated_review') else 'no'}",
        f"- 原始候选：{report.get('original_papers', 0)}",
        f"- 补检索候选：{report.get('rescue_candidates', 0)}",
        f"- 新增去重候选：{report.get('new_unique_papers', 0)}",
        f"- 最终候选：{report.get('final_papers', 0)}",
        "",
    ]
    note = str(report.get("note") or "").strip()
    if note:
        lines.extend(["## 说明", note, ""])
    lines.extend(["## 执行检索式"])
    queries = report.get("selected_queries") if isinstance(report.get("selected_queries"), list) else []
    lines.extend(f"- `{_cell(str(query))}`" for query in queries) if queries else lines.append("- 无")
    task_ids = report.get("repair_task_ids") if isinstance(report.get("repair_task_ids"), list) else []
    if task_ids:
        lines.extend(["", "## 来源检索修复任务"])
        lines.extend(f"- `{_cell(str(item))}`" for item in task_ids)
    outcomes = report.get("query_outcomes") if isinstance(report.get("query_outcomes"), list) else []
    if outcomes:
        lines.extend(
            [
                "",
                "## Query 闭环",
                "| 状态 | Query | Repair Task | 命中候选 | 新增候选 | 进入最终池 |",
                "| --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for item in outcomes:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("status") or "")),
                            "`" + _cell(str(item.get("query") or "")) + "`",
                            _cell(", ".join(str(value) for value in item.get("repair_task_ids", []) if str(value).strip()) or "-"),
                            str(item.get("matched_candidates") or 0),
                            str(item.get("new_unique_candidates") or 0),
                            str(item.get("final_new_papers") or 0),
                        ]
                    )
                    + " |"
                )
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), list) else []
    if diagnostics:
        lines.extend(["", "## 诊断"])
        lines.extend(f"- {item}" for item in diagnostics[:12])
    source_health = report.get("source_health") if isinstance(report.get("source_health"), list) else []
    if source_health:
        lines.extend(["", "## 来源健康", "| 来源 | 状态 | 返回 | 错误 | 限流 |", "| --- | --- | ---: | ---: | --- |"])
        for item in source_health:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("source") or "")),
                            _cell(str(item.get("status") or "")),
                            str(item.get("returned") or 0),
                            str(item.get("errors") or 0),
                            "yes" if item.get("rate_limited") is True else "no",
                        ]
                    )
                    + " |"
                )
    titles = report.get("rescue_titles") if isinstance(report.get("rescue_titles"), list) else []
    if titles:
        lines.extend(["", "## 新检索候选"])
        lines.extend(f"- {item}" for item in titles[:12])
    return "\n".join(lines)


def _selected_queries(report: dict[str, Any], priority_cutoff: int = 94, limit: int = 6) -> list[str]:
    rows = report.get("rescue_queries") if isinstance(report.get("rescue_queries"), list) else []
    selected: list[str] = []
    for item in sorted((row for row in rows if isinstance(row, dict)), key=lambda row: int(row.get("priority") or 0), reverse=True):
        if int(item.get("priority") or 0) < priority_cutoff:
            continue
        query = str(item.get("query") or "").strip()
        if query and query not in selected:
            selected.append(query)
        if len(selected) >= limit:
            break
    return selected


def _selected_task_queries(tasks: list[dict[str, Any]], priority_cutoff: int = 80, limit: int = 6) -> tuple[list[str], list[str], dict[str, list[str]]]:
    selected_queries: list[str] = []
    selected_ids: list[str] = []
    query_task_ids: dict[str, list[str]] = {}
    rows = [row for row in tasks if isinstance(row, dict)]
    for item in sorted(rows, key=lambda row: int(row.get("priority") or 0), reverse=True):
        if int(item.get("priority") or 0) < priority_cutoff:
            continue
        owner = str(item.get("owner") or "")
        query = str(item.get("query") or "").strip()
        if owner not in {"agent", "agent+human"} or not query:
            continue
        task_id = str(item.get("task_id") or f"retrieval-task-{len(selected_ids) + 1}")
        if query not in selected_queries:
            selected_queries.append(query)
            selected_ids.append(task_id)
        query_task_ids.setdefault(query, [])
        if task_id not in query_task_ids[query]:
            query_task_ids[query].append(task_id)
        if len(selected_queries) >= limit:
            break
    return selected_queries, selected_ids, query_task_ids


def _dedupe_queries(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        query = " ".join(str(value).split())
        if query and query not in result:
            result.append(query)
    return result


def _merged_papers(original: list[Paper], rescue: list[Paper], topic: str, queries: list[str], max_papers: int) -> list[Paper]:
    merged = deduplicate_papers([*original, *rescue])
    ranked = rank_papers(merged, topic, queries)
    filtered = filter_relevant_papers(ranked, topic, queries, min_relevance=0.0)
    candidates = filtered or ranked
    manual_keys = {_paper_key(paper) for paper in original if _is_manual_seed(paper)}
    manual_papers = [paper for paper in ranked if _paper_key(paper) in manual_keys or _is_manual_seed(paper)]
    other_papers = [paper for paper in candidates if paper not in manual_papers]
    return [*manual_papers, *other_papers][:max_papers]


def _is_manual_seed(paper: Paper) -> bool:
    return "manual_seed" in set(paper.sources or [paper.source])


def _new_unique_count(original: list[Paper], rescue: list[Paper]) -> int:
    original_keys = {_paper_key(item) for item in deduplicate_papers(original)}
    rescue_keys = {_paper_key(item) for item in deduplicate_papers(rescue)}
    return len([key for key in rescue_keys if key and key not in original_keys])


def _paper_key(paper: Paper) -> str:
    if paper.doi:
        return "doi:" + paper.doi.lower()
    arxiv_id = paper.external_ids.get("arXiv") or paper.external_ids.get("ARXIV")
    if arxiv_id:
        return "arxiv:" + arxiv_id.lower()
    return "title:" + "".join(ch for ch in paper.title.lower() if ch.isalnum())[:180]


def _query_outcomes(
    selected_queries: list[str],
    query_task_ids: dict[str, list[str]],
    original_papers: list[Paper],
    rescue_papers: list[Paper],
    final_papers: list[Paper],
) -> list[dict[str, Any]]:
    original_keys = {_paper_key(item) for item in original_papers}
    final_keys = {_paper_key(item) for item in final_papers}
    rows: list[dict[str, Any]] = []
    for query in selected_queries:
        matched = [paper for paper in rescue_papers if _query_matches_paper(query, paper)]
        new_candidates = [paper for paper in matched if _paper_key(paper) not in original_keys]
        final_new = [paper for paper in new_candidates if _paper_key(paper) in final_keys]
        rows.append(
            {
                "query": query,
                "repair_task_ids": query_task_ids.get(query, []),
                "matched_candidates": len(matched),
                "new_unique_candidates": len(new_candidates),
                "final_new_papers": len(final_new),
                "status": _outcome_status(len(matched), len(new_candidates), len(final_new)),
                "final_titles": [paper.title for paper in final_new[:4]],
            }
        )
    return rows


def _not_executed_outcomes(selected_queries: list[str], query_task_ids: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        {
            "query": query,
            "repair_task_ids": query_task_ids.get(query, []),
            "matched_candidates": 0,
            "new_unique_candidates": 0,
            "final_new_papers": 0,
            "status": "not_executed",
            "final_titles": [],
        }
        for query in selected_queries
    ]


def _outcome_status(matched: int, new_candidates: int, final_new: int) -> str:
    if final_new:
        return "closed"
    if new_candidates:
        return "partial"
    if matched:
        return "no_new_papers"
    return "no_hits"


def _query_matches_paper(query: str, paper: Paper) -> bool:
    terms = _query_terms(query)
    if not terms:
        return False
    text = _paper_text(paper)
    hits = sum(1 for term in terms if term in text)
    return hits >= min(2, len(terms))


def _query_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z][A-Za-z0-9+*.-]{2,}|[\u4e00-\u9fff]{2,}", query.lower().replace("*", " star"))
    stop = {"and", "with", "the", "for", "from", "study", "paper", "review", "comparison", "evaluation"}
    return _dedupe_queries([term.replace(" star", "") for term in raw_terms if term not in stop])


def _paper_text(paper: Paper) -> str:
    return " ".join(
        [
            paper.title,
            paper.abstract,
            paper.venue,
            " ".join(paper.authors),
            paper.doi,
            paper.url,
        ]
    ).lower().replace("*", "")


def _report(
    status: str,
    trigger_status: str,
    review: LiteratureReview,
    selected_queries: list[str],
    diagnostics: list[str],
    source_health: list[dict[str, Any]],
    rescue_papers: list[Paper],
    note: str = "",
    updated: bool = False,
    new_unique: int = 0,
    original_count: int | None = None,
    repair_task_ids: list[str] | None = None,
    query_outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    actions = _required_actions(status, query_outcomes or [], repair_task_ids or [])
    warnings = _warnings(status, query_outcomes or [])
    return {
        "topic": review.topic,
        "status": status,
        "trigger_status": trigger_status,
        "updated_review": updated,
        "original_papers": len(review.papers) if original_count is None else original_count,
        "rescue_candidates": len(rescue_papers),
        "new_unique_papers": new_unique,
        "final_papers": len(review.papers),
        "selected_queries": selected_queries,
        "diagnostics": diagnostics,
        "source_health": source_health,
        "rescue_titles": [paper.title for paper in rescue_papers[:12]],
        "repair_task_ids": repair_task_ids or [],
        "query_outcomes": query_outcomes or [],
        "closed_query_outcomes": sum(1 for item in query_outcomes or [] if str(item.get("status") or "") == "closed"),
        "unresolved_query_outcomes": sum(1 for item in query_outcomes or [] if str(item.get("status") or "") in {"partial", "no_new_papers", "no_hits"}),
        "warnings": warnings,
        "required_actions": actions,
        "note": note,
    }


def _required_actions(status: str, query_outcomes: list[dict[str, Any]], repair_task_ids: list[str]) -> list[str]:
    actions: list[str] = []
    if status == "no_new_papers":
        actions.append("补检索没有带来新增去重候选；需要调整 query、修复 source 或补 DOI/URL seed 后重跑文献 gate。")
    unresolved = [
        item
        for item in query_outcomes
        if item.get("repair_task_ids") and str(item.get("status") or "") in {"partial", "no_new_papers", "no_hits", "not_executed"}
    ]
    for item in unresolved[:4]:
        actions.append(f"检索修复任务 {', '.join(str(value) for value in item.get('repair_task_ids', []))} 未闭环：{item.get('status')}；query=`{item.get('query')}`。")
    if repair_task_ids and status in {"not_applicable", "skipped"} and not actions:
        actions.append("检索修复任务未执行；确认 literature_provider、source/API key 和 rescue trigger 后重跑。")
    return actions


def _warnings(status: str, query_outcomes: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if status == "no_new_papers":
        warnings.append("补检索执行完成但未改善候选池。")
    open_outcomes = [item for item in query_outcomes if str(item.get("status") or "") in {"partial", "no_new_papers", "no_hits", "not_executed"}]
    if open_outcomes:
        warnings.append(f"仍有 {len(open_outcomes)} 条 query outcome 未闭环。")
    return warnings


