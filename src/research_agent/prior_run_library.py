from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .artifacts import write_json, write_text
from .run_library import RunLibrary, RunLibrarySearchResult, build_run_library, search_run_library


PRIOR_RUN_LIBRARY_JSON = "00-prior-run-library.json"
PRIOR_RUN_LIBRARY_MD = "00-prior-run-library.md"


@dataclass(frozen=True)
class PriorRunLibraryReference:
    run_id: str
    topic: str
    title: str
    reusable_status: str
    selected_papers: int
    citations: int
    ideas: int
    readiness_score: float
    repair_queue_status: str
    paper_artifact: str
    artifact_path: str
    matched_fields: list[str]
    score: float
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PriorRunLibraryReport:
    topic: str
    status: str
    source_runs_dir: str
    indexed_runs: int
    query: str
    references: list[PriorRunLibraryReference]
    manual_checklist: list[str]
    agent_prompt_text: str


def write_prior_run_library_artifacts(topic: str, runs_dir: Path, out_dir: Path, limit: int = 100) -> PriorRunLibraryReport:
    library = build_run_library(runs_dir, limit=limit)
    report = build_prior_run_library(topic, library, current_run_id=out_dir.name)
    write_json(out_dir / PRIOR_RUN_LIBRARY_JSON, report)
    write_text(out_dir / PRIOR_RUN_LIBRARY_MD, render_prior_run_library_markdown(report))
    return report


def build_prior_run_library(topic: str, library: RunLibrary, current_run_id: str = "", result_limit: int = 8) -> PriorRunLibraryReport:
    results = [result for result in search_run_library(library, topic, limit=result_limit + 1) if result.entry.id != current_run_id]
    references = [_reference_from_result(result) for result in results[:result_limit]]
    status = _status(library.indexed_runs, references)
    manual_checklist = _manual_checklist(references)
    return PriorRunLibraryReport(
        topic=topic,
        status=status,
        source_runs_dir=library.runs_dir,
        indexed_runs=library.indexed_runs,
        query=topic,
        references=references,
        manual_checklist=manual_checklist,
        agent_prompt_text=_agent_prompt_text(library, references),
    )


def render_prior_run_library_markdown(report: PriorRunLibraryReport) -> str:
    lines = [
        f"# Prior Run Library：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 来源 runs：{report.source_runs_dir}",
        f"- 已索引历史 run：{report.indexed_runs}",
        f"- 查询：`{report.query}`",
        "",
        "## 相关历史成果",
        "| Run | 可复用性 | 题名 | 证据 | 修复 | 关键词 | 匹配 | 分数 | 产物 |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    if not report.references:
        lines.append("| 无匹配 | - | - | - | - | - | - | 0.00 | - |")
    for ref in report.references:
        evidence = f"papers={ref.selected_papers}, citations={ref.citations}, ideas={ref.ideas}, readiness={ref.readiness_score:.2f}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(ref.run_id),
                    _cell(ref.reusable_status),
                    _cell(ref.title),
                    _cell(evidence),
                    _cell(ref.repair_queue_status or "-"),
                    _cell(", ".join(ref.keywords[:6]) or "-"),
                    _cell(", ".join(ref.matched_fields) or "-"),
                    f"{ref.score:.2f}",
                    _cell(ref.artifact_path or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 启动前人工检查"])
    lines.extend(f"- [ ] {item}" for item in report.manual_checklist) if report.manual_checklist else lines.append("- 暂无")
    lines.extend(["", "## 给 Agent 的继承文本", report.agent_prompt_text])
    return "\n".join(lines)


def _reference_from_result(result: RunLibrarySearchResult) -> PriorRunLibraryReference:
    entry = result.entry
    artifact_path = f"{entry.id}/{entry.paper_artifact}" if entry.paper_artifact else ""
    return PriorRunLibraryReference(
        run_id=entry.id,
        topic=entry.topic,
        title=entry.title,
        reusable_status=entry.reusable_status,
        selected_papers=entry.selected_papers,
        citations=entry.citations,
        ideas=entry.ideas,
        readiness_score=entry.readiness_score,
        repair_queue_status=entry.repair_queue_status,
        paper_artifact=entry.paper_artifact,
        artifact_path=artifact_path,
        matched_fields=result.matched_fields,
        keywords=entry.keywords[:10],
        score=result.score,
    )


def _status(indexed_runs: int, references: list[PriorRunLibraryReference]) -> str:
    if indexed_runs == 0:
        return "no_prior_library"
    if not references:
        return "no_relevant_prior_runs"
    if any(ref.reusable_status == "ready_reference" for ref in references):
        return "prior_references_ready"
    return "prior_context_available"


def _manual_checklist(references: list[PriorRunLibraryReference]) -> list[str]:
    if not references:
        return []
    items = [
        "只把历史成果库作为规划上下文，不要把它当作本轮论文证据或 citation。",
        "人工确认 ready_reference 的论文、benchmark 和 baseline 是否仍适用于当前课题。",
    ]
    if any(ref.reusable_status in {"context_only", "needs_repair", "failure_case"} for ref in references):
        items.append("context_only、needs_repair 和 failure_case 只能提示风险或失败经验，不能支撑强结论。")
    return items


def _agent_prompt_text(library: RunLibrary, references: list[PriorRunLibraryReference]) -> str:
    if library.indexed_runs == 0:
        return "历史成果库为空；本轮不得假设已有可复用论文或实验结果。"
    if not references:
        return f"历史成果库已索引 {library.indexed_runs} 个 run，但没有与本课题直接匹配的成果；按新课题完整执行检索、人工 gate 和实验审计。"
    lines = [
        "历史成果库参考仅用于规划和避免重复，不是本轮文献证据或 citation：",
        f"- 已索引 run：{library.indexed_runs}；相关参考：{len(references)}",
    ]
    for ref in references[:5]:
        evidence = f"papers={ref.selected_papers}, citations={ref.citations}, readiness={ref.readiness_score:.2f}"
        artifact = ref.artifact_path or "-"
        keywords = "；keywords=" + ", ".join(ref.keywords[:5]) if ref.keywords else ""
        lines.append(f"- [{ref.reusable_status}] {ref.run_id}: {ref.title}；{evidence}{keywords}；artifact={artifact}")
    if any(ref.reusable_status in {"context_only", "needs_repair", "failure_case"} for ref in references):
        lines.append("context_only、needs_repair 和 failure_case 只能作为风险/失败经验，不能作为强证据。")
    return "\n".join(lines)


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
