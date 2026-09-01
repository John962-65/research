from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re
import shutil

from .artifacts import write_json, write_text
from .citation_grounding import build_citation_grounding_report, render_citation_grounding_markdown
from .fulltext_corpus import write_fulltext_corpus_artifacts
from .literature_context import build_literature_context, render_literature_context_markdown
from .models import EvidenceChunk, LiteratureContext, LiteratureReview


FULLTEXT_GROUNDING_RUN_JSON = "10-fulltext-grounding-run.json"
FULLTEXT_GROUNDING_RUN_MD = "10-fulltext-grounding-run.md"


def run_fulltext_grounding(
    *,
    topic: str,
    fulltext_paths: list[str],
    out_dir: Path,
    claim: str = "",
    force: bool = False,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        if not force:
            raise FileExistsError(f"Output directory is not empty: {out_dir}")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_state(out_dir, topic, "started")

    paths = [str(item).strip() for item in fulltext_paths if str(item).strip()]
    if not paths:
        raise ValueError("At least one --fulltext-path is required.")
    corpus = write_fulltext_corpus_artifacts(topic, paths, out_dir, base_dir=Path.cwd())
    context = build_literature_context(_empty_review(topic), corpus)
    write_json(out_dir / "01-context.json", context)
    write_text(out_dir / "01-context.md", render_literature_context_markdown(context))

    citation_key, note = _grounding_note(topic, context, claim)
    write_text(out_dir / "09-revised-paper.md", note)

    grounding = build_citation_grounding_report(topic, out_dir, context)
    write_json(out_dir / "10-citation-grounding.json", grounding)
    write_text(out_dir / "10-citation-grounding.md", render_citation_grounding_markdown(grounding))

    report = _report(topic, paths, corpus, context, citation_key, grounding)
    write_json(out_dir / FULLTEXT_GROUNDING_RUN_JSON, report)
    write_text(out_dir / FULLTEXT_GROUNDING_RUN_MD, render_fulltext_grounding_run_markdown(report))
    _write_state(out_dir, topic, "completed")
    return report


def render_fulltext_grounding_run_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Fulltext Grounding Run：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 全文文档：{report.get('fulltext_documents', 0)}",
        f"- 全文 chunks：{report.get('fulltext_chunks', 0)}",
        f"- Context citations/chunks：{report.get('context_citations', 0)}/{report.get('context_chunks', 0)}",
        f"- Citation key：{report.get('citation_key') or '-'}",
        f"- Grounding：{report.get('grounding_status') or '-'} / score={float(report.get('grounding_score') or 0.0):.3f}",
        f"- Citation pass/review/block：{report.get('passed_citations', 0)}/{report.get('review_citations', 0)}/{report.get('blocked_citations', 0)}",
        "",
    ]
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## Warnings"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    lines.extend(["## Artifacts"])
    for artifact in report.get("artifacts", []) if isinstance(report.get("artifacts"), list) else []:
        lines.append(f"- `{artifact}`")
    return "\n".join(lines)


def _empty_review(topic: str) -> LiteratureReview:
    return LiteratureReview(
        topic=topic,
        papers=[],
        themes=[],
        gaps=[],
        summary="Standalone local fulltext grounding validation.",
    )


def _grounding_note(topic: str, context: LiteratureContext, claim: str) -> tuple[str, str]:
    chunk = _first_fulltext_chunk(context)
    if chunk is None:
        raise ValueError("No readable local fulltext chunk was available for citation grounding.")
    citation_key = chunk.citation_key
    body = claim.strip() or _claim_from_chunk(chunk)
    if citation_key not in body and f"\\cite{{{citation_key}}}" not in body:
        body = body.rstrip(".。 ") + f" [{citation_key}]."
    return citation_key, f"# Fulltext Grounding Verification\n\nTopic: {topic}\n\n{body}\n"


def _first_fulltext_chunk(context: LiteratureContext) -> EvidenceChunk | None:
    for chunk in context.chunks:
        if chunk.source == "local_fulltext" and chunk.text.strip():
            return chunk
    return None


def _claim_from_chunk(chunk: EvidenceChunk) -> str:
    text = re.sub(r"\[local_fulltext chunk [^\]]+\]\s*", " ", chunk.text)
    text = " ".join(text.split())
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]
    for sentence in sentences:
        if len(sentence) >= 50:
            return sentence[:360].rstrip()
    return text[:360].rstrip() or chunk.title


def _report(
    topic: str,
    fulltext_paths: list[str],
    corpus: Any,
    context: LiteratureContext,
    citation_key: str,
    grounding: Any,
) -> dict[str, Any]:
    grounding_status = str(getattr(grounding, "status", "") or "")
    corpus_warnings = list(getattr(corpus, "warnings", []) or [])
    status = "block" if grounding_status == "block" else "review_required" if grounding_status != "pass" or corpus_warnings else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "fulltext_paths": fulltext_paths,
        "fulltext_documents": len(getattr(corpus, "documents", []) or []),
        "fulltext_chunks": int(getattr(corpus, "total_chunks", 0) or 0),
        "context_citations": len(context.citations),
        "context_chunks": len(context.chunks),
        "citation_key": citation_key,
        "grounding_status": grounding_status,
        "grounding_score": float(getattr(grounding, "grounding_score", 0.0) or 0.0),
        "total_citations": int(getattr(grounding, "total_citations", 0) or 0),
        "passed_citations": int(getattr(grounding, "passed_citations", 0) or 0),
        "review_citations": int(getattr(grounding, "review_citations", 0) or 0),
        "blocked_citations": int(getattr(grounding, "blocked_citations", 0) or 0),
        "warnings": [*corpus_warnings],
        "artifacts": [
            "01-fulltext-corpus.json",
            "01-fulltext-corpus.md",
            "01-context.json",
            "01-context.md",
            "09-revised-paper.md",
            "10-citation-grounding.json",
            "10-citation-grounding.md",
            FULLTEXT_GROUNDING_RUN_JSON,
            FULLTEXT_GROUNDING_RUN_MD,
        ],
    }


def _write_state(out_dir: Path, topic: str, stage: str) -> None:
    write_json(out_dir / "state.json", {"topic": topic, "stage": stage, "updated_at": datetime.now(timezone.utc).isoformat()})
