from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text
from .run_summary import RunSummary, build_run_dashboard


RUN_LIBRARY_JSON = "runs-library.json"
RUN_LIBRARY_MD = "runs-library.md"


@dataclass(frozen=True)
class RunLibraryEntry:
    id: str
    topic: str
    status: str
    stage: str
    updated_at: str
    title: str
    abstract: str
    paper_artifact: str
    analysis_artifact: str
    next_iteration_artifact: str
    selected_papers: int
    citations: int
    ideas: int
    readiness_score: float
    repair_queue_status: str
    final_readiness_status: str
    reusable_status: str
    keywords: list[str]


@dataclass(frozen=True)
class RunLibrarySearchResult:
    score: float
    matched_fields: list[str]
    entry: RunLibraryEntry


@dataclass(frozen=True)
class RunLibrary:
    generated_at: str
    runs_dir: str
    total_runs: int
    indexed_runs: int
    entries: list[RunLibraryEntry]


def build_run_library(runs_dir: Path, limit: int = 100) -> RunLibrary:
    dashboard = build_run_dashboard(runs_dir, limit=limit)
    entries = [_entry_from_summary(runs_dir, run) for run in dashboard.runs]
    entries = [entry for entry in entries if entry is not None]
    return RunLibrary(
        generated_at=_utc_now(),
        runs_dir=str(runs_dir),
        total_runs=dashboard.total_runs,
        indexed_runs=len(entries),
        entries=entries,
    )


def write_run_library(library: RunLibrary, out_dir: Path, basename: str = "runs-library") -> tuple[Path, Path]:
    json_path = out_dir / f"{basename}.json"
    md_path = out_dir / f"{basename}.md"
    write_json(json_path, library)
    write_text(md_path, render_run_library_markdown(library))
    return json_path, md_path


def search_run_library(library: RunLibrary, query: str, limit: int = 10) -> list[RunLibrarySearchResult]:
    query_text = " ".join(str(query or "").split())
    scored = [_score_entry(entry, query_text) for entry in library.entries]
    if query_text:
        scored = [item for item in scored if item.score > 0]
    scored = sorted(scored, key=lambda item: (item.score, item.entry.readiness_score, item.entry.updated_at, item.entry.id), reverse=True)
    return scored[: max(0, limit)]


def render_run_library_markdown(
    library: RunLibrary,
    query: str = "",
    results: list[RunLibrarySearchResult] | None = None,
) -> str:
    selected = results if results is not None else [RunLibrarySearchResult(0.0, [], entry) for entry in library.entries]
    title = "# Runs 本地成果库"
    lines = [
        title,
        "",
        f"- 生成时间：{library.generated_at}",
        f"- Runs 目录：{library.runs_dir}",
        f"- 已索引：{library.indexed_runs}/{library.total_runs}",
    ]
    if query:
        lines.append(f"- 查询：`{query}`")
    lines.extend(
        [
            "",
            "## 条目",
            "| Run | 状态 | 可复用性 | 题名 | 证据 | 修复 | 匹配 | 产物 |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    if not selected:
        lines.append("| 无匹配 | - | - | - | - | - | 0.00 | - |")
        return "\n".join(lines)
    for result in selected:
        entry = result.entry
        evidence = f"papers={entry.selected_papers}, citations={entry.citations}, ideas={entry.ideas}, readiness={entry.readiness_score:.2f}"
        repair = entry.repair_queue_status or "-"
        artifacts = ", ".join(item for item in [entry.paper_artifact, entry.analysis_artifact, entry.next_iteration_artifact] if item) or "-"
        score = f"{result.score:.2f}" if query else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(entry.id),
                    _cell(f"{entry.status}/{entry.stage}"),
                    _cell(entry.reusable_status),
                    _cell(entry.title),
                    _cell(evidence),
                    _cell(repair),
                    score,
                    _cell(artifacts),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 摘要"])
    for result in selected[:10]:
        entry = result.entry
        abstract = entry.abstract or "无摘要。"
        keywords = ", ".join(entry.keywords[:10]) or "-"
        matched = ", ".join(result.matched_fields) if result.matched_fields else "-"
        lines.extend(
            [
                f"### {entry.id}",
                f"- 主题：{entry.topic}",
                f"- 题名：{entry.title}",
                f"- 匹配字段：{matched}",
                f"- 关键词：{keywords}",
                f"- 摘要：{abstract}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _entry_from_summary(runs_dir: Path, run: RunSummary) -> RunLibraryEntry | None:
    run_dir = runs_dir / run.id
    paper_artifact = _first_existing(run_dir, ["09-revised-paper.md", "06-paper.md"])
    analysis_artifact = _first_existing(run_dir, ["05-analysis.md"])
    next_iteration_artifact = _first_existing(run_dir, ["12-next-iteration-plan.md", "12-repair-queue.md"])
    title, abstract = _paper_title_and_abstract(run_dir / paper_artifact if paper_artifact else None)
    if not title:
        title = run.topic or run.id
    keywords = _keywords(run_dir, run, title, abstract)
    return RunLibraryEntry(
        id=run.id,
        topic=run.topic,
        status=run.status,
        stage=run.stage,
        updated_at=run.updated_at,
        title=title,
        abstract=abstract,
        paper_artifact=paper_artifact,
        analysis_artifact=analysis_artifact,
        next_iteration_artifact=next_iteration_artifact,
        selected_papers=run.selected_papers,
        citations=run.citations,
        ideas=run.ideas,
        readiness_score=run.readiness_score,
        repair_queue_status=run.repair_queue_status,
        final_readiness_status=run.final_readiness_status,
        reusable_status=_reusable_status(run, paper_artifact),
        keywords=keywords,
    )


def _score_entry(entry: RunLibraryEntry, query: str) -> RunLibrarySearchResult:
    if not query:
        return RunLibrarySearchResult(entry.readiness_score, [], entry)
    fields = {
        "id": (entry.id, 0.8),
        "topic": (entry.topic, 4.0),
        "title": (entry.title, 5.0),
        "abstract": (entry.abstract, 2.0),
        "keywords": (" ".join(entry.keywords), 3.0),
        "status": (f"{entry.status} {entry.stage} {entry.reusable_status}", 1.0),
    }
    tokens = _tokens(query)
    exact_query = query.casefold()
    score = 0.0
    matched: list[str] = []
    for name, (text, weight) in fields.items():
        haystack = str(text or "").casefold()
        hits = 0
        if exact_query and exact_query in haystack:
            hits += 2
        hits += sum(1 for token in tokens if token in haystack)
        if hits:
            matched.append(name)
            score += weight * hits
    if entry.reusable_status == "ready_reference":
        score += 1.5
    elif entry.reusable_status == "needs_repair":
        score -= 0.5
    return RunLibrarySearchResult(score=max(score, 0.0), matched_fields=matched, entry=entry)


def _paper_title_and_abstract(path: Path | None) -> tuple[str, str]:
    if path is None or not path.exists():
        return "", ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "", ""
    lines = text.splitlines()
    title = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            break
    abstract = _extract_section(lines, {"abstract", "摘要"})
    if not abstract:
        abstract = _first_paragraph(lines)
    return _short(title, 160), _short(abstract, 700)


def _extract_section(lines: list[str], names: set[str]) -> str:
    collecting = False
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().casefold()
            if collecting:
                break
            collecting = heading in names or any(heading.startswith(name + " ") for name in names)
            continue
        if collecting:
            values.append(stripped)
    return _clean_paragraph(values)


def _first_paragraph(lines: list[str]) -> str:
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("- "):
            if values:
                break
            continue
        values.append(stripped)
    return _clean_paragraph(values)


def _clean_paragraph(lines: list[str]) -> str:
    text = " ".join(line for line in lines if line)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _keywords(run_dir: Path, run: RunSummary, title: str, abstract: str) -> list[str]:
    values = [run.topic, title]
    plan = _read_json(run_dir / "00-research-plan.json")
    if isinstance(plan, dict):
        for key in ["domain", "search_queries", "benchmarks", "baselines", "metrics", "constraints", "success_criteria"]:
            values.extend(_string_values(plan.get(key)))
    ideas = _read_json(run_dir / "02-ideas.json")
    if isinstance(ideas, list):
        for item in ideas[:3]:
            if isinstance(item, dict):
                values.extend(_string_values([item.get("title"), item.get("hypothesis"), item.get("baseline")]))
    values.extend(_tokens(f"{title} {abstract}"))
    return _dedupe([_short(value, 80) for value in values if str(value).strip()])[:30]


def _reusable_status(run: RunSummary, paper_artifact: str) -> str:
    if run.repair_queue_status in {"blocked_repair_required", "needs_repair"}:
        return "needs_repair"
    if run.final_handoff_package_zip_valid is False:
        return "needs_repair"
    if run.status == "completed" and paper_artifact and (run.selected_papers >= 3 or run.citations >= 3):
        return "ready_reference"
    if run.status in {"waiting", "revision_requested"}:
        return "waiting_human_gate"
    if run.status == "failed":
        return "failure_case"
    return "context_only"


def _first_existing(run_dir: Path, names: list[str]) -> str:
    for name in names:
        if (run_dir / name).exists():
            return name
    return ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _string_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", str(text or "").casefold())
    return _dedupe(raw)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = " ".join(str(value or "").split()).strip()
        key = item.casefold()
        if not item or key in seen:
            continue
        result.append(item)
        seen.add(key)
    return result


def _short(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
