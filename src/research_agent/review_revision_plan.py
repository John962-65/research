from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, read_json_dict as _read_json


REVIEW_REVISION_PLAN_JSON = "01-review-revision-plan.json"
REVIEW_REVISION_PLAN_MD = "01-review-revision-plan.md"


def write_review_revision_plan_artifacts(out_dir: Path, approval: dict[str, Any]) -> dict[str, Any]:
    report = build_review_revision_plan(out_dir, approval)
    write_json(out_dir / REVIEW_REVISION_PLAN_JSON, report)
    write_text(out_dir / REVIEW_REVISION_PLAN_MD, render_review_revision_plan_markdown(report))
    return report


def build_review_revision_plan(out_dir: Path, approval: dict[str, Any]) -> dict[str, Any]:
    gate = _read_json(out_dir / "01-context.json")
    quality = _read_json(out_dir / "01-literature-quality.json")
    coverage = _read_json(out_dir / "01-literature-coverage.json")
    rescue = _read_json(out_dir / "01-literature-rescue-plan.json")
    seed_intake = _read_json(out_dir / "01-seed-paper-intake.json")
    citation = _read_json(out_dir / "01-citation-audit.json")
    source_health = _read_json(out_dir / "01-literature-source-health.json")
    search_feedback = _read_json(out_dir / "01-literature-search-feedback.json")
    notes = str(approval.get("notes") or "").strip()
    items = _items(notes, gate, quality, coverage, rescue, seed_intake, citation, source_health, search_feedback)
    return {
        "topic": approval.get("topic") or _topic_from_state(out_dir),
        "status": "revision_requested",
        "reviewer": approval.get("reviewer") or "manual",
        "notes": notes,
        "gate_status": approval.get("gate_status") or _gate_status(gate),
        "literature_search_feedback": _feedback_summary(search_feedback),
        "items": items,
        "rerun_commands": _rerun_commands(str(out_dir), search_feedback),
        "stop_conditions": _stop_conditions(items),
        "next_approval_checklist": _approval_checklist(items),
    }


def render_review_revision_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Review Revision Plan：{report.get('topic') or '未命名课题'}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 审核人：{report.get('reviewer') or '-'}",
        f"- Gate：{report.get('gate_status') or '-'}",
        f"- 审核意见：{report.get('notes') or '无'}",
        "",
        "## 修复项",
        "| 优先级 | 类别 | 动作 | Query/Seed | 原因 | 目标产物 |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        query_or_seed = str(item.get("query") or item.get("seed_target") or "")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("priority") or ""),
                    _cell(str(item.get("category") or "")),
                    _cell(str(item.get("action") or "")),
                    _cell(query_or_seed or "-"),
                    _cell(str(item.get("rationale") or "")),
                    _cell(", ".join(item.get("target_artifacts") or [])),
                ]
            )
            + " |"
        )
    feedback = report.get("literature_search_feedback") if isinstance(report.get("literature_search_feedback"), dict) else {}
    if feedback:
        config = feedback.get("next_run_config") if isinstance(feedback.get("next_run_config"), dict) else {}
        sources = config.get("sources") if isinstance(config.get("sources"), list) else []
        lines.extend(
            [
                "",
                "## 检索反馈承接",
                f"- 状态：{feedback.get('status') or '-'}",
                f"- 推荐配置：provider={config.get('literature_provider') or '-'}; sources={', '.join(str(item) for item in sources) or '-'}; max_papers={config.get('max_papers') or '-'}; max_search_queries={config.get('max_search_queries') or '-'}; seed_papers_min={config.get('seed_papers_min') or '-'}",
            ]
        )
        queries = feedback.get("top_queries") if isinstance(feedback.get("top_queries"), list) else []
        seeds = feedback.get("seed_targets") if isinstance(feedback.get("seed_targets"), list) else []
        if queries:
            lines.extend(["", "### 推荐检索式"])
            lines.extend(f"- `{item}`" for item in queries if item)
        if seeds:
            lines.extend(["", "### Seed 目标"])
            lines.extend(f"- {item}" for item in seeds if item)
    lines.extend(["", "## Resume 命令"])
    lines.extend(f"- `{item}`" for item in report.get("rerun_commands", []) if item)
    lines.extend(["", "## 再次批准前停止条件"])
    lines.extend(f"- [ ] {item}" for item in report.get("stop_conditions", []) if item)
    lines.extend(["", "## 再次批准 checklist"])
    lines.extend(f"- [ ] {item}" for item in report.get("next_approval_checklist", []) if item)
    return "\n".join(lines)


def _items(
    notes: str,
    gate: dict[str, Any],
    quality: dict[str, Any],
    coverage: dict[str, Any],
    rescue: dict[str, Any],
    seed_intake: dict[str, Any],
    citation: dict[str, Any],
    source_health: dict[str, Any],
    search_feedback: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    gate_obj = gate.get("review_gate") if isinstance(gate.get("review_gate"), dict) else {}
    warnings = _as_list(gate_obj.get("warnings"))
    required = _as_list(gate_obj.get("required_actions"))
    if notes:
        items.append(_item(5, "human_feedback", f"落实人工退回意见：{notes}", "人工审核明确要求修复后再批准。", ["approval.json", REVIEW_REVISION_PLAN_MD]))
    if rescue and str(rescue.get("status") or "") in {"block", "needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        items.append(_item(10, "literature_rescue", "执行文献补检索或修复文献源。", f"01-literature-rescue-plan.json 状态为 {rescue.get('status')}", ["01-literature-rescue-plan.md", "01-literature-source-health.md"]))
    seed_status = str(seed_intake.get("status") or "")
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    if seed_intake and seed_status in {"block", "review_required"}:
        items.append(_item(12, "seed_paper_intake", "修复人工 seed 文献输入，确保核心 DOI/URL 进入 curated context。", f"01-seed-paper-intake.json 状态为 {seed_status}; curated={seed_intake.get('curated_seed_papers')}/{seed_intake.get('total_seed_entries')}", ["01-seed-paper-intake.md", "01-literature-quality.md"]))
    elif seed_intake and seed_role_status == "review_required":
        missing_roles = seed_intake.get("missing_curated_seed_roles") if isinstance(seed_intake.get("missing_curated_seed_roles"), list) else []
        items.append(_item(12, "seed_paper_intake", "补齐人工 seed 的角色覆盖，确保 curated context 至少覆盖 3 类核心文献角色。", f"role_coverage={seed_role_status}; missing_roles={', '.join(str(item) for item in missing_roles[:4]) or '-'}; curated={seed_intake.get('curated_seed_papers')}/{seed_intake.get('total_seed_entries')}", ["01-seed-paper-intake.md", "01-literature-quality.md", "01-literature-curated.md"]))
    if coverage and str(coverage.get("status") or "") in {"block", "needs_literature", "needs_coverage"}:
        items.append(_item(15, "coverage", "补齐 benchmark、baseline、metric 或领域 facet 覆盖。", f"coverage_ratio={coverage.get('coverage_ratio')}", ["01-literature-coverage.md", "00-research-plan.md"]))
    confidence = str(quality.get("confidence_status") or "")
    selected = _safe_int(quality.get("selected_papers"))
    if quality and (confidence in {"weak", "block"} or selected < 5):
        items.append(_item(20, "quality", "补充高相关种子文献并重新生成质量筛选。", f"confidence={confidence or '-'}; selected_papers={selected}", ["01-literature-quality.md", "01-literature-curated.md"]))
    if citation and (str(citation.get("integrity_status") or "") in {"block", "review_required"} or _safe_int(citation.get("blocked_citations"))):
        items.append(_item(25, "citation", "修复不可核验引用，补 DOI/URL/作者/年份或删除弱引用。", f"citation_integrity={citation.get('integrity_status') or '-'}", ["01-citation-audit.md", "01-references.bib", "01-references.ris"]))
    if source_health and (_safe_int(source_health.get("rate_limited_sources")) or _safe_int(source_health.get("failed_sources"))):
        items.append(_item(30, "source_health", "修复限流或失败的文献源配置。", "文献源失败会导致召回偏窄。", ["01-literature-source-health.md"]))
    if search_feedback and str(search_feedback.get("status") or "") in {"needs_source_repair", "needs_search_revision", "needs_manual_seed"}:
        summary = _feedback_summary(search_feedback)
        config = summary.get("next_run_config") if isinstance(summary.get("next_run_config"), dict) else {}
        top_queries = summary.get("top_queries") if isinstance(summary.get("top_queries"), list) else []
        seed_targets = summary.get("seed_targets") if isinstance(summary.get("seed_targets"), list) else []
        items.append(
            _item(
                32,
                "literature_search_feedback",
                "承接 search feedback 的推荐配置、检索式和 seed 目标后重跑文献 gate。",
                (
                    f"status={search_feedback.get('status') or '-'}; queries={len(top_queries)}; "
                    f"seed_targets={len(seed_targets)}; max_papers={config.get('max_papers') or '-'}; "
                    f"max_search_queries={config.get('max_search_queries') or '-'}"
                ),
                ["01-literature-search-feedback.md", "01-literature-rerank.md", "01-literature-quality.md", "01-review-gate.md"],
            )
        )
        for query in top_queries[:3]:
            items.append(
                _item(
                    33,
                    "search_feedback_query",
                    "把推荐检索式加入 extra_search_queries 后重跑。",
                    "上一轮 search feedback 推荐的高优先级 query。",
                    ["01-literature-search-feedback.md", "01-literature-source-health.md"],
                    query=str(query),
                )
            )
        for target in seed_targets[:3]:
            items.append(
                _item(
                    34,
                    "search_feedback_seed",
                    "补充覆盖该目标的 DOI/URL seed paper。",
                    "上一轮 search feedback 指出 seed 目标缺口。",
                    ["01-seed-paper-intake.md", "01-literature-curated.md"],
                    seed_target=str(target),
                )
            )
    for action in required[:4]:
        items.append(_item(35, "gate_required_action", str(action), "来自 01-review-gate.md 的人工审核动作。", ["01-review-gate.md"]))
    for warning in warnings[:3]:
        items.append(_item(45, "gate_warning", "人工核对 gate warning 并决定补检索或豁免。", str(warning), ["01-review-gate.md", "approval.json"]))
    return _dedupe_items(items) or [_item(50, "manual_review", "根据审核意见人工补充文献或说明豁免理由。", "未检测到结构化阻断项，但人工已退回。", ["approval.json", "01-review-gate.md"])]


def _stop_conditions(items: list[dict[str, Any]]) -> list[str]:
    conditions = [
        "01-review-gate.md 不再列出 block/literature_repair_required 的必须动作，或 approval notes 明确记录人工豁免理由。",
        "01-citation-audit.json 中 blocked_citations=0，citation integrity 不为 block。",
        "01-literature-quality.json 的 evidence confidence 不为 weak/block。",
    ]
    categories = {str(item.get("category") or "") for item in items}
    if "literature_rescue" in categories:
        conditions.append("01-literature-rescue-plan.json 状态为 pass，或已添加高相关人工 seed_papers。")
    if "literature_search_feedback" in categories or "search_feedback_query" in categories:
        conditions.append("01-literature-search-feedback.md 中推荐的 top queries、sources、max_papers/max_search_queries 已写入本轮配置并重新生成 01-literature-quality。")
    if "search_feedback_seed" in categories:
        conditions.append("search feedback 指出的 seed 目标已补 DOI/URL，且 01-seed-paper-intake.json 显示进入 curated context 或记录人工豁免。")
    if "seed_paper_intake" in categories:
        conditions.append("01-seed-paper-intake.json 中人工 seed 已进入 curated context，角色覆盖不再是 review_required，或 approval notes 明确说明为何豁免。")
    if "coverage" in categories:
        conditions.append("01-literature-coverage.json 覆盖 benchmark、baseline 和核心 metric。")
    return conditions


def _approval_checklist(items: list[dict[str, Any]]) -> list[str]:
    checklist = [
        "重新打开 01-review-gate.md、01-literature-quality.md 和 01-citation-audit.md。",
        "确认人工退回意见已经落实到检索、引用或 approval notes。",
        "确认 approval.json 的批准动作发生在修复之后。",
    ]
    if any(item.get("category") == "human_feedback" for item in items):
        checklist.insert(1, "逐条对照人工审核意见，不要只重跑而不修复。")
    if any(str(item.get("category") or "").startswith("search_feedback") or item.get("category") == "literature_search_feedback" for item in items):
        checklist.insert(1, "确认 01-literature-search-feedback.md 的推荐 query、seed 目标和 next_run_config 已被当前配置承接。")
    return checklist


def _rerun_commands(run_dir: str, search_feedback: dict[str, Any] | None = None) -> list[str]:
    command = f"PYTHONPATH=src python3 -m research_agent resume {run_dir} --literature-provider online --max-papers 12"
    feedback = _feedback_summary(search_feedback or {})
    if feedback:
        config = feedback.get("next_run_config") if isinstance(feedback.get("next_run_config"), dict) else {}
        provider = str(config.get("literature_provider") or "online").strip() or "online"
        max_papers = _safe_int(config.get("max_papers")) or 12
        max_queries = _safe_int(config.get("max_search_queries")) or 6
        sources = [str(item).strip() for item in config.get("sources", []) if str(item).strip()] if isinstance(config.get("sources"), list) else []
        command = (
            f"PYTHONPATH=src python3 -m research_agent resume {run_dir} "
            f"--literature-provider {provider} --max-papers {max_papers} --max-search-queries {max_queries}"
        )
        if sources:
            command += f" --literature-sources {_quote(','.join(sources))}"
        for query in (feedback.get("top_queries") if isinstance(feedback.get("top_queries"), list) else [])[:2]:
            if str(query).strip():
                command += f" --extra-search-query {_quote(str(query))}"
    return [
        command,
        f"PYTHONPATH=src python3 -m research_agent approve {run_dir} --notes \"已按 01-review-revision-plan.md 修复\"",
    ]


def _item(priority: int, category: str, action: str, rationale: str, target_artifacts: list[str], *, query: str = "", seed_target: str = "") -> dict[str, Any]:
    return {
        "priority": priority,
        "category": category,
        "action": action,
        "query": " ".join(query.split()),
        "seed_target": " ".join(seed_target.split()),
        "rationale": rationale,
        "target_artifacts": target_artifacts,
    }


def _feedback_summary(search_feedback: dict[str, Any]) -> dict[str, Any]:
    if not search_feedback:
        return {}
    queries = search_feedback.get("recommended_queries") if isinstance(search_feedback.get("recommended_queries"), list) else []
    seeds = search_feedback.get("seed_paper_targets") if isinstance(search_feedback.get("seed_paper_targets"), list) else []
    tasks = search_feedback.get("retrieval_repair_tasks") if isinstance(search_feedback.get("retrieval_repair_tasks"), list) else []
    next_config = search_feedback.get("next_run_config") if isinstance(search_feedback.get("next_run_config"), dict) else {}
    top_queries = [str(item.get("query") or "").strip() for item in queries if isinstance(item, dict) and str(item.get("query") or "").strip()]
    if not top_queries:
        top_queries = [str(item.get("query") or "").strip() for item in tasks if isinstance(item, dict) and str(item.get("query") or "").strip()]
    seed_targets = [
        str(item.get("name") or item.get("seed_target") or "").strip()
        for item in seeds
        if isinstance(item, dict) and str(item.get("name") or item.get("seed_target") or "").strip()
    ]
    return {
        "status": search_feedback.get("status") or "",
        "top_queries": _dedupe(top_queries)[:5],
        "seed_targets": _dedupe(seed_targets)[:5],
        "retrieval_repair_tasks": len(tasks),
        "agent_queries": sum(1 for item in tasks if isinstance(item, dict) and str(item.get("owner") or "") in {"agent", "agent+human"} and str(item.get("query") or "").strip()),
        "next_run_config": {
            "literature_provider": next_config.get("literature_provider") or "",
            "sources": [str(item).strip() for item in next_config.get("sources", []) if str(item).strip()] if isinstance(next_config.get("sources"), list) else [],
            "max_papers": next_config.get("max_papers") or 0,
            "max_search_queries": next_config.get("max_search_queries") or 0,
            "seed_papers_min": next_config.get("seed_papers_min") or 0,
        },
    }


def _topic_from_state(out_dir: Path) -> str:
    state = _read_json(out_dir / "state.json")
    return str(state.get("topic") or out_dir.name)


def _gate_status(context: dict[str, Any]) -> str:
    gate = context.get("review_gate") if isinstance(context.get("review_gate"), dict) else {}
    return str(gate.get("status") or "")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda value: int(value.get("priority") or 999)):
        key = (
            str(item.get("category") or ""),
            str(item.get("action") or ""),
            str(item.get("query") or ""),
            str(item.get("seed_target") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


