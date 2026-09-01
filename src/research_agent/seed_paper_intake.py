from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text
from .config import LiteratureConfig
from .models import LiteratureQualityReport, LiteratureReview, Paper


SEED_PAPER_INTAKE_JSON = "01-seed-paper-intake.json"
SEED_PAPER_INTAKE_MD = "01-seed-paper-intake.md"


def build_seed_paper_suggestion_report(
    topic: str,
    run_dir: Path,
    seed_intake: dict[str, Any] | None = None,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    intake = seed_intake if isinstance(seed_intake, dict) else _read_json(run_dir / SEED_PAPER_INTAKE_JSON)
    candidates = _seed_suggestion_candidates(run_dir)
    entries = _suggested_seed_entries_from_candidates(candidates, intake, limit=limit)
    suggested_role_counts = _suggested_seed_role_counts(entries, candidates)
    existing_role_counts = intake.get("curated_seed_role_counts") if isinstance(intake.get("curated_seed_role_counts"), dict) else {}
    combined_role_counts = {role: int(existing_role_counts.get(role) or 0) + int(suggested_role_counts.get(role) or 0) for role in _seed_role_names()}
    missing_roles = _missing_seed_roles(combined_role_counts)
    return {
        "status": "available" if entries else "empty",
        "suggested_seed_entries": entries,
        "suggested_seed_count": len(entries),
        "suggested_seed_role_counts": suggested_role_counts,
        "combined_seed_role_counts": combined_role_counts,
        "missing_roles": missing_roles,
        "role_repair_queries": _seed_role_repair_queries(topic, missing_roles),
    }


def build_unconfigured_seed_paper_intake_report(topic: str, suggestion_report: dict[str, Any] | None = None) -> dict[str, Any]:
    suggestion = suggestion_report if isinstance(suggestion_report, dict) else {}
    role_names = _seed_role_names()
    suggested_seed_role_counts = suggestion.get("suggested_seed_role_counts") if isinstance(suggestion.get("suggested_seed_role_counts"), dict) else {}
    combined_seed_role_counts = suggestion.get("combined_seed_role_counts") if isinstance(suggestion.get("combined_seed_role_counts"), dict) else {}
    suggested_entries = _list_from_payload(suggestion.get("suggested_seed_entries"))
    missing_roles = _list_from_payload(suggestion.get("missing_roles")) or _missing_seed_roles(
        {role: int(combined_seed_role_counts.get(role) or 0) for role in role_names}
    )
    role_repair_queries = _list_from_payload(suggestion.get("role_repair_queries")) or _seed_role_repair_queries(topic, missing_roles)
    actions = [*role_repair_queries]
    if suggested_entries:
        actions.append("人工核对候选 DOI/URL seed，写入 seed_papers 后重新生成 01-seed-paper-intake.json。")
    else:
        actions.append("如果 01-literature-quality 或 01-literature-coverage 偏弱，在 Web 表单补 3-5 条 DOI/URL seed_papers 后重跑。")
    if missing_roles:
        actions.append("补齐 review/survey、benchmark/dataset、baseline/method、recent work 中至少 3 类 seed，当前仍缺：" + ", ".join(missing_roles[:4]) + "。")
    warnings = ["未配置人工 seed_papers；当前 run 不能证明人工 seed 曾约束文献上下文。"]
    if suggested_entries:
        warnings.append("已根据当前 quality/curated 文献生成候选 seed 建议；这些建议不是历史人工输入。")
    return {
        "schema_version": 1,
        "topic": topic,
        "status": "not_configured",
        "role_coverage_status": "review_required",
        "seed_role_counts": {role: 0 for role in role_names},
        "curated_seed_role_counts": {role: 0 for role in role_names},
        "missing_curated_seed_roles": list(role_names),
        "total_seed_entries": 0,
        "raw_seed_papers": 0,
        "curated_seed_papers": 0,
        "doi_entries": 0,
        "url_entries": 0,
        "title_only_entries": 0,
        "metadata_resolved_seed_papers": 0,
        "metadata_unresolved_doi_url_seed_papers": 0,
        "items": [],
        "warnings": warnings,
        "required_actions": _unique_strings(actions),
        "suggested_seed_entries": suggested_entries,
        "suggested_seed_count": len(suggested_entries),
        "suggested_seed_role_counts": {role: int(suggested_seed_role_counts.get(role) or 0) for role in role_names},
        "combined_seed_role_counts": {role: int(combined_seed_role_counts.get(role) or 0) for role in role_names},
        "missing_roles": missing_roles,
        "role_repair_queries": role_repair_queries,
    }


def seed_role_repair_queries(topic: str, missing_roles: list[str]) -> list[str]:
    return _seed_role_repair_queries(topic, missing_roles)


def write_seed_paper_intake_artifacts(
    topic: str,
    config: LiteratureConfig,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    report = build_seed_paper_intake_report(topic, config, raw_review, curated_review, quality_report)
    write_json(run_dir / SEED_PAPER_INTAKE_JSON, report)
    write_text(run_dir / SEED_PAPER_INTAKE_MD, render_seed_paper_intake_markdown(report))
    return report


def build_seed_paper_intake_report(
    topic: str,
    config: LiteratureConfig,
    raw_review: LiteratureReview,
    curated_review: LiteratureReview,
    quality_report: LiteratureQualityReport | dict[str, Any],
) -> dict[str, Any]:
    entries = [re.sub(r"\s+", " ", str(item)).strip() for item in config.seed_papers if str(item).strip()]
    quality_items = _quality_items(quality_report)
    items = [_seed_item(topic, entry, raw_review.papers, curated_review.papers, quality_items, index) for index, entry in enumerate(entries, start=1)]
    role_coverage = _role_coverage(items, entries)
    status = _status(items, entries)
    return {
        "schema_version": 1,
        "topic": topic or raw_review.topic,
        "status": status,
        "role_coverage_status": role_coverage["status"],
        "seed_role_counts": role_coverage["seed_role_counts"],
        "curated_seed_role_counts": role_coverage["curated_seed_role_counts"],
        "missing_curated_seed_roles": role_coverage["missing_curated_seed_roles"],
        "total_seed_entries": len(entries),
        "raw_seed_papers": sum(1 for item in items if item["raw_included"]),
        "curated_seed_papers": sum(1 for item in items if item["curated_included"]),
        "doi_entries": sum(1 for item in items if item["doi"]),
        "url_entries": sum(1 for item in items if item["url"]),
        "title_only_entries": sum(1 for item in items if item["entry_type"] == "title"),
        "metadata_resolved_seed_papers": sum(1 for item in items if item["metadata_resolved"]),
        "metadata_unresolved_doi_url_seed_papers": sum(1 for item in items if item["entry_type"] in {"doi", "url"} and not item["metadata_resolved"]),
        "items": items,
        "warnings": _warnings(items, entries, role_coverage),
        "required_actions": _required_actions(items, entries, role_coverage),
    }


def render_seed_paper_intake_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Seed Paper Intake：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 人工 seed：{report.get('total_seed_entries', 0)}",
        f"- 原始文献池命中：{report.get('raw_seed_papers', 0)}",
        f"- Curated context 命中：{report.get('curated_seed_papers', 0)}",
        f"- DOI/URL/标题-only：{report.get('doi_entries', 0)}/{report.get('url_entries', 0)}/{report.get('title_only_entries', 0)}",
        f"- Seed 元数据解析：{report.get('metadata_resolved_seed_papers', 0)} resolved；{report.get('metadata_unresolved_doi_url_seed_papers', 0)} unresolved DOI/URL",
        f"- 角色覆盖：{report.get('role_coverage_status') or '-'}；全部 seed {_role_counts_text(report.get('seed_role_counts'))}；curated {_role_counts_text(report.get('curated_seed_role_counts'))}",
        "",
    ]
    for key, title in [("warnings", "警告"), ("required_actions", "下一步动作")]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        if values:
            lines.extend([f"## {title}"])
            lines.extend(f"- {item}" for item in values)
            lines.append("")
    suggestions = report.get("suggested_seed_entries") if isinstance(report.get("suggested_seed_entries"), list) else []
    if suggestions:
        lines.extend(["## 候选建议"])
        lines.extend(f"- {str(item)}" for item in suggestions[:10] if str(item).strip())
        lines.append("")
    lines.extend(
        [
            "## Seed 明细",
            "| # | 类型 | 角色 | 状态 | DOI | URL | 原始池 | Curated | 元数据来源 | 质量筛选 | Topic overlap | 解析标题 | 动作 |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    rows = report.get("items") if isinstance(report.get("items"), list) else []
    if not rows:
        lines.append("| - | - | - | not_configured | - | - | - | - | - | - | - | 未配置人工 seed | 如文献质量弱，请在 Web 表单填入 DOI/URL/题名 |")
    for item in rows:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("index") or ""),
                    _cell(str(item.get("entry_type") or "")),
                    _cell(", ".join(item.get("roles") or []) or "-"),
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("doi") or "-")),
                    _cell(str(item.get("url") or "-")),
                    "yes" if item.get("raw_included") else "no",
                    "yes" if item.get("curated_included") else "no",
                    _cell(", ".join(item.get("metadata_sources") or []) or "-"),
                    "yes" if item.get("quality_selected") else "no",
                    _cell(", ".join(item.get("topic_overlap_terms") or []) or "-"),
                    _cell(str(item.get("parsed_title") or "")),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _seed_item(
    topic: str,
    entry: str,
    raw_papers: list[Paper],
    curated_papers: list[Paper],
    quality_items: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    doi = _extract_doi(entry)
    url = _extract_url(entry)
    title = _manual_title(entry, doi, url, index)
    entry_type = "doi" if doi else "url" if url else "title"
    raw_matches = _matching_papers(doi, url, title, raw_papers)
    curated_matches = _matching_papers(doi, url, title, curated_papers)
    quality_selected = _quality_selected(doi, url, title, quality_items)
    metadata_sources = _metadata_sources([*raw_matches, *curated_matches])
    evidence_text = _paper_text((curated_matches or raw_matches or [None])[0]) or f"{title} {entry}"
    overlap = _overlap_terms(topic, evidence_text)
    status, action = _item_status(entry_type, raw_matches, curated_matches, overlap)
    roles = _seed_roles(entry, title, raw_matches, curated_matches)
    return {
        "index": index,
        "raw_entry": entry,
        "entry_type": entry_type,
        "roles": roles,
        "doi": doi,
        "url": url,
        "parsed_title": title,
        "status": status,
        "raw_included": bool(raw_matches),
        "curated_included": bool(curated_matches),
        "metadata_resolved": bool(metadata_sources),
        "metadata_sources": metadata_sources,
        "quality_selected": quality_selected,
        "matched_raw_titles": [paper.title for paper in raw_matches[:3]],
        "matched_curated_titles": [paper.title for paper in curated_matches[:3]],
        "topic_overlap_terms": overlap,
        "action": action,
    }


def _item_status(entry_type: str, raw_matches: list[Paper], curated_matches: list[Paper], overlap: list[str]) -> tuple[str, str]:
    if not raw_matches:
        return "block", "该 seed 没有进入原始文献池；检查 DOI/URL/标题格式，或提高 max_papers 后重跑。"
    if not curated_matches:
        return "review", "该 seed 已进入原始池但未进入 curated context；检查质量筛选原因，必要时补 DOI/URL 或人工豁免。"
    if entry_type == "title":
        return "review", "该 seed 只有标题，投稿前需补 DOI 或 URL 并核对作者/年份。"
    if not overlap:
        return "review", "该 seed 与课题词面重叠很弱；人工确认它是否真是核心文献。"
    return "pass", "无需处理。"


def _status(items: list[dict[str, Any]], entries: list[str]) -> str:
    if not entries:
        return "not_configured"
    if any(item["status"] == "block" for item in items):
        return "block"
    if any(item["status"] == "review" for item in items):
        return "review_required"
    return "pass"


def _role_coverage(items: list[dict[str, Any]], entries: list[str]) -> dict[str, Any]:
    role_names = _seed_role_names()
    seed_counts = {role: 0 for role in role_names}
    curated_counts = {role: 0 for role in role_names}
    for item in items:
        roles = [str(role) for role in item.get("roles", []) if str(role).strip()]
        for role in roles:
            if role in seed_counts:
                seed_counts[role] += 1
                if item.get("curated_included"):
                    curated_counts[role] += 1
    covered = [role for role in role_names if curated_counts.get(role, 0) > 0]
    missing = [role for role in role_names if curated_counts.get(role, 0) == 0]
    if not entries:
        status = "not_configured"
    elif len(entries) < 3:
        status = "not_applicable"
    elif len(covered) >= 3:
        status = "pass"
    else:
        status = "review_required"
    return {
        "status": status,
        "seed_role_counts": seed_counts,
        "curated_seed_role_counts": curated_counts,
        "missing_curated_seed_roles": missing,
    }


def _warnings(items: list[dict[str, Any]], entries: list[str], role_coverage: dict[str, Any]) -> list[str]:
    if not entries:
        return []
    warnings: list[str] = []
    not_raw = sum(1 for item in items if not item["raw_included"])
    not_curated = sum(1 for item in items if item["raw_included"] and not item["curated_included"])
    title_only = sum(1 for item in items if item["entry_type"] == "title")
    unresolved_metadata = sum(1 for item in items if item["entry_type"] in {"doi", "url"} and not item["metadata_resolved"])
    low_overlap = sum(1 for item in items if item["curated_included"] and not item["topic_overlap_terms"])
    if not_raw:
        warnings.append(f"{not_raw} 条人工 seed 未进入原始文献池。")
    if not_curated:
        warnings.append(f"{not_curated} 条人工 seed 未进入 curated context。")
    if title_only:
        warnings.append(f"{title_only} 条人工 seed 只有标题，缺 DOI/URL。")
    if unresolved_metadata:
        warnings.append(f"{unresolved_metadata} 条 DOI/URL seed 只作为人工输入保留，尚未解析到 Crossref/在线来源/离线题录元数据。")
    if low_overlap:
        warnings.append(f"{low_overlap} 条 curated seed 与课题词面重叠弱，需要人工确认相关性。")
    if role_coverage.get("status") == "review_required":
        missing = role_coverage.get("missing_curated_seed_roles") if isinstance(role_coverage.get("missing_curated_seed_roles"), list) else []
        warnings.append("人工 seed 进入 curated context 的角色覆盖不足：" + ", ".join(str(item) for item in missing[:4]) + "。")
    return warnings


def _required_actions(items: list[dict[str, Any]], entries: list[str], role_coverage: dict[str, Any]) -> list[str]:
    if not entries:
        return ["如果 01-literature-quality 或 01-literature-coverage 偏弱，在 Web 表单补 3-5 条 DOI/URL seed_papers 后重跑。"]
    actions: list[str] = []
    if any(not item["raw_included"] for item in items):
        actions.append("修复未进入原始池的 seed：优先填写 DOI，其次 URL，避免只写模糊标题。")
    if any(item["raw_included"] and not item["curated_included"] for item in items):
        actions.append("检查 01-literature-quality.md 中对应 seed 的筛选原因；核心文献被排除时应补元数据或人工说明豁免。")
    if any(item["entry_type"] == "title" for item in items):
        actions.append("投稿前为 title-only seed 补 DOI/URL、作者、年份和 venue。")
    if any(item["entry_type"] in {"doi", "url"} and not item["metadata_resolved"] for item in items):
        actions.append("修复未解析元数据的 DOI/URL seed：检查 DOI/URL 是否真实可访问，或改用能被 Crossref/在线来源解析的核心论文。")
    if role_coverage.get("status") == "review_required":
        actions.append("补齐进入 curated context 的 seed 角色覆盖：至少覆盖 review/survey、benchmark/dataset、baseline/method、recent work 中的 3 类。")
    if not actions:
        actions.append("人工 seed 已进入 curated context；批准前抽查 DOI/URL 和摘要是否匹配。")
    return actions


def _matching_papers(doi: str, url: str, title: str, papers: list[Paper]) -> list[Paper]:
    result: list[Paper] = []
    title_norm = _norm_title(title)
    for paper in papers:
        if doi and paper.doi and paper.doi.lower() == doi.lower():
            result.append(paper)
        elif url and paper.url and _norm_url(paper.url) == _norm_url(url):
            result.append(paper)
        elif title_norm and (_norm_title(paper.title) == title_norm or title_norm in _norm_title(paper.title) or _norm_title(paper.title) in title_norm):
            result.append(paper)
        elif "manual_seed" in set(paper.sources or [paper.source]) and title_norm and title_norm in _norm_title(paper.evidence_note or ""):
            result.append(paper)
    return _unique_papers(result)


def _metadata_sources(papers: list[Paper]) -> list[str]:
    sources: list[str] = []
    for paper in papers:
        for source in [*(paper.sources or []), paper.source]:
            value = str(source or "").strip()
            if value and value != "manual_seed" and value not in sources:
                sources.append(value)
    return sources


def _quality_items(report: LiteratureQualityReport | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(report, LiteratureQualityReport):
        return [
            {"title": item.title, "doi": item.doi, "url": item.url, "selected": item.selected}
            for item in report.items
        ]
    rows = report.get("items") if isinstance(report, dict) else []
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _quality_selected(doi: str, url: str, title: str, rows: list[dict[str, Any]]) -> bool:
    title_norm = _norm_title(title)
    for item in rows:
        if doi and str(item.get("doi") or "").lower() == doi.lower():
            return item.get("selected") is True
        if url and _norm_url(str(item.get("url") or "")) == _norm_url(url):
            return item.get("selected") is True
        if title_norm and _norm_title(str(item.get("title") or "")) == title_norm:
            return item.get("selected") is True
    return False


def _seed_suggestion_candidates(run_dir: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    quality = _read_json(run_dir / "01-literature-quality.json")
    for item in quality.get("items", []) if isinstance(quality.get("items"), list) else []:
        if not isinstance(item, dict) or item.get("selected") is not True:
            continue
        candidates.append(_seed_suggestion_candidate(item, score=item.get("quality_score", 0.0)))
    curated = _read_json(run_dir / "01-literature-curated.json")
    for item in curated.get("papers", []) if isinstance(curated.get("papers"), list) else []:
        if isinstance(item, dict):
            candidates.append(_seed_suggestion_candidate(item, score=item.get("relevance", 0.0)))
    return candidates


def _seed_suggestion_candidate(item: dict[str, Any], score: Any) -> dict[str, Any]:
    title = str(item.get("title") or "")
    roles = _candidate_roles(item)
    return {
        "title": title,
        "doi": str(item.get("doi") or ""),
        "url": str(item.get("url") or ""),
        "year": item.get("year", 0),
        "venue": str(item.get("venue") or ""),
        "abstract": str(item.get("abstract") or ""),
        "roles": roles,
        "score": _safe_float(score),
    }


def _suggested_seed_entries_from_candidates(candidates: list[dict[str, Any]], seed_intake: dict[str, Any], *, limit: int) -> list[str]:
    existing = _seed_keys_from_intake(seed_intake)
    existing_roles = _seed_roles_from_intake(seed_intake)
    missing_seed_roles = [role for role in _seed_role_names() if role not in existing_roles]
    entries: list[str] = []
    seen: set[str] = set(existing)
    for role in missing_seed_roles:
        item = _best_seed_candidate_for_role(candidates, role, seen)
        if item:
            _append_seed_entry(entries, seen, item)
        if len(entries) >= limit:
            return entries
    for item in sorted(candidates, key=_seed_candidate_rank, reverse=True):
        _append_seed_entry(entries, seen, item)
        if len(entries) >= limit:
            break
    return entries


def _seed_keys_from_intake(seed_intake: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    rows = seed_intake.get("items") if isinstance(seed_intake.get("items"), list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        for key in _seed_keys(str(item.get("doi") or ""), str(item.get("url") or ""), str(item.get("parsed_title") or "")):
            keys.add(key)
    return keys


def _seed_roles_from_intake(seed_intake: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    counts = seed_intake.get("curated_seed_role_counts") if isinstance(seed_intake.get("curated_seed_role_counts"), dict) else {}
    for role in _seed_role_names():
        if int(counts.get(role) or 0) > 0:
            roles.add(role)
    return roles


def _best_seed_candidate_for_role(candidates: list[dict[str, Any]], role: str, seen: set[str]) -> dict[str, Any] | None:
    rows = [item for item in candidates if role in [str(value) for value in item.get("roles", [])] and not any(key in seen for key in _seed_candidate_keys(item))]
    if not rows:
        return None
    return max(rows, key=_seed_candidate_rank)


def _append_seed_entry(entries: list[str], seen: set[str], item: dict[str, Any]) -> None:
    entry = _seed_entry_from_candidate(item)
    keys = _seed_candidate_keys(item)
    if not entry or not keys or any(key in seen for key in keys):
        return
    entries.append(entry)
    seen.update(keys)


def _seed_entry_from_candidate(item: dict[str, Any]) -> str:
    title = " ".join(str(item.get("title") or "").split()).strip()
    doi = str(item.get("doi") or "").strip()
    url = str(item.get("url") or "").strip()
    locator = doi or url
    if not locator or not title:
        return ""
    return f"{locator} {title}"


def _seed_candidate_keys(item: dict[str, Any]) -> list[str]:
    return _seed_keys(str(item.get("doi") or ""), str(item.get("url") or ""), str(item.get("title") or ""))


def _seed_candidate_rank(item: dict[str, Any]) -> tuple[int, float]:
    roles = [str(role) for role in item.get("roles", []) if str(role).strip()]
    core_hits = sum(1 for role in roles if role in _seed_role_names())
    return (core_hits, _safe_float(item.get("score")))


def _suggested_seed_role_counts(entries: list[str], candidates: list[dict[str, Any]]) -> dict[str, int]:
    candidates_by_entry = {_seed_entry_from_candidate(item): item for item in candidates}
    counts = {role: 0 for role in _seed_role_names()}
    for entry in entries:
        item = candidates_by_entry.get(entry)
        if not item:
            continue
        for role in item.get("roles", []):
            if role in counts:
                counts[role] += 1
    return counts


def _candidate_roles(item: dict[str, Any]) -> list[str]:
    mapped = [_map_quality_role(str(role)) for role in _list_from_payload(item.get("evidence_roles", []))]
    roles = [role for role in mapped if role]
    if roles:
        return _unique_strings(roles)
    title = str(item.get("title") or "")
    text = " ".join([title, str(item.get("abstract") or ""), str(item.get("venue") or ""), str(item.get("year") or "")])
    return _roles_from_text(text)


def _roles_from_text(text: str) -> list[str]:
    lowered = text.lower().replace("*", " star")
    roles: list[str] = []
    if any(token in lowered for token in ["review", "survey", "tutorial", "overview", "state of the art", "taxonomy", "systematic", "meta-analysis", "综述", "调研"]):
        roles.append("review")
    if any(token in lowered for token in ["benchmark", "dataset", "data set", "evaluation", "corpus", "suite", "testbed", "test bed", "leaderboard", "challenge", "ompl", "moveit", "基准", "数据集", "评测"]):
        roles.append("benchmark_dataset")
    if any(token in lowered for token in ["baseline", "method", "algorithm", "planner", "planning", "approach", "framework", "model", "rrt", "rrt star", "prm", "chomp", "stomp", "trajopt", "ompl", "trajectory optimization", "sampling based", "方法", "算法", "规划"]):
        roles.append("baseline_method")
    if any(year >= _recent_year_cutoff() for year in _years(lowered)):
        roles.append("recent")
    return _unique_strings(roles)


def _map_quality_role(role: str) -> str:
    mapping = {
        "review_survey": "review",
        "benchmark_dataset": "benchmark_dataset",
        "baseline_method": "baseline_method",
        "recent_work": "recent",
        "review": "review",
        "recent": "recent",
    }
    return mapping.get(role, "")


def _missing_seed_roles(counts: dict[str, int]) -> list[str]:
    return [role for role in _seed_role_names() if int(counts.get(role) or 0) <= 0]


def _seed_role_repair_queries(topic: str, missing_roles: list[str]) -> list[str]:
    topic_text = " ".join(str(topic or "").split()).strip()
    if not topic_text:
        return []
    role_terms = {
        "review": "survey review state of the art",
        "benchmark_dataset": "benchmark dataset evaluation protocol",
        "baseline_method": "baseline method comparison",
        "recent": "2024 2025 latest recent advances",
    }
    queries = [f"{topic_text} {role_terms[role]}" for role in missing_roles if role in role_terms]
    return _unique_strings(queries)


def _seed_keys(doi: str, url: str, title: str) -> list[str]:
    keys: list[str] = []
    if doi:
        keys.append("doi:" + doi.lower())
    if url:
        keys.append("url:" + _norm_url(url))
    title_key = "".join(ch for ch in title.lower() if ch.isalnum())[:180]
    if title_key:
        keys.append("title:" + title_key)
    return keys


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _list_from_payload(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        key = item.lower()
        if not item or key in seen:
            continue
        result.append(item)
        seen.add(key)
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _paper_text(paper: Paper | None) -> str:
    if paper is None:
        return ""
    return " ".join([paper.title, paper.abstract or "", paper.evidence_note or ""])


def _seed_roles(entry: str, title: str, raw_matches: list[Paper], curated_matches: list[Paper]) -> list[str]:
    text_parts = [entry, title]
    for paper in (curated_matches or raw_matches)[:3]:
        text_parts.append(_paper_text(paper))
        text_parts.append(str(paper.year or ""))
    text = " ".join(text_parts).lower()
    roles: list[str] = []
    if any(token in text for token in ["review", "survey", "tutorial", "overview", "state of the art", "taxonomy", "systematic", "meta-analysis", "综述"]):
        roles.append("review")
    if any(token in text for token in ["benchmark", "dataset", "evaluation", "corpus", "suite", "leaderboard", "challenge", "基准", "数据集", "评测"]):
        roles.append("benchmark_dataset")
    if any(
        token in text
        for token in [
            "baseline",
            "method",
            "algorithm",
            "planner",
            "planning",
            "approach",
            "framework",
            "model",
            "rrt",
            "prm",
            "chomp",
            "stomp",
            "trajopt",
            "ompl",
            "方法",
            "算法",
            "规划",
        ]
    ):
        roles.append("baseline_method")
    if any(year >= _recent_year_cutoff() for year in _years(text)):
        roles.append("recent")
    return roles


def _seed_role_names() -> list[str]:
    return ["review", "benchmark_dataset", "baseline_method", "recent"]


def _role_counts_text(value: Any) -> str:
    counts = value if isinstance(value, dict) else {}
    return ", ".join(f"{role}={int(counts.get(role) or 0)}" for role in _seed_role_names())


def _years(value: str) -> list[int]:
    years: list[int] = []
    for match in re.findall(r"\b(20\d{2})\b", value):
        try:
            years.append(int(match))
        except ValueError:
            continue
    return years


def _recent_year_cutoff() -> int:
    return datetime.now(timezone.utc).year - 5


def _overlap_terms(topic: str, text: str) -> list[str]:
    terms = _terms(topic)
    lowered = text.lower()
    return [term for term in terms if term in lowered][:8]


def _terms(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    stop = {"the", "and", "for", "with", "how", "what", "研究", "课题", "方法"}
    result: list[str] = []
    for term in raw:
        if term not in stop and term not in result:
            result.append(term)
    lowered = text.lower()
    if "机械臂" in text or "路径规划" in text or "manipulator" in lowered:
        result.extend(term for term in ["robot", "manipulator", "motion", "planning", "path"] if term not in result)
    if "轴承" in text or "故障" in text or "bearing" in lowered:
        result.extend(term for term in ["bearing", "fault", "diagnosis", "vibration"] if term not in result)
    if "科研 agent" in text or "research agent" in lowered:
        result.extend(term for term in ["research", "agent", "scientific", "discovery"] if term not in result)
    return result[:12]


def _extract_doi(entry: str) -> str:
    match = re.search(r"(10\.\d{4,9}/[^\s,;]+)", entry, flags=re.I)
    return match.group(1).rstrip(").]") if match else ""


def _extract_url(entry: str) -> str:
    match = re.search(r"https?://[^\s,;]+", entry)
    return match.group(0).rstrip(").]") if match else ""


def _manual_title(entry: str, doi: str, url: str, index: int) -> str:
    title = entry
    if url:
        title = title.replace(url, " ")
    if doi:
        title = title.replace(doi, " ")
    title = re.sub(r"\b(19\d{2}|20\d{2})\b", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -:;,")
    if title:
        return title[:180]
    if doi:
        return f"Manual seed DOI {doi}"
    return f"Manual seed paper {index}"


def _norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.lower()).strip()


def _norm_url(value: str) -> str:
    return value.strip().rstrip("/").lower()


def _unique_papers(values: list[Paper]) -> list[Paper]:
    result: list[Paper] = []
    seen: set[tuple[str, str]] = set()
    for paper in values:
        key = (paper.doi.lower(), _norm_title(paper.title))
        if key not in seen:
            seen.add(key)
            result.append(paper)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
