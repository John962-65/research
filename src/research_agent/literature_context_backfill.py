from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .citation_audit import audit_citations
from .literature_context import apply_literature_audits_to_context, build_literature_context
from .literature_evidence_contract import LITERATURE_EVIDENCE_CONTRACT_JSON, LITERATURE_EVIDENCE_CONTRACT_MD
from .literature_gate_backfill import _read_context
from .literature_gate_decision import LITERATURE_GATE_DECISION_JSON, LITERATURE_GATE_DECISION_MD
from .literature_quality import assess_literature_quality, filter_review_by_quality
from .literature_quality_backfill import (
    LITERATURE_CURATED_JSON,
    LITERATURE_QUALITY_JSON,
    _quality_report_value,
)
from .literature_rescue_backfill import _load_raw_review, _read_literature_review
from .literature_search_audit_backfill import _source_health_review
from .pipeline import CITATION_AUDIT_JSON, CITATION_AUDIT_MD, write_context_and_citation_artifacts
from .artifacts import cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json


LITERATURE_CONTEXT_JSON = "01-context.json"
LITERATURE_CONTEXT_MD = "01-context.md"
REVIEW_GATE_MD = "01-review-gate.md"
REFERENCES_BIB = "01-references.bib"
REFERENCES_RIS = "01-references.ris"


CONTEXT_BUNDLE = [
    LITERATURE_CONTEXT_JSON,
    LITERATURE_CONTEXT_MD,
    REVIEW_GATE_MD,
    REFERENCES_BIB,
    REFERENCES_RIS,
    CITATION_AUDIT_JSON,
    CITATION_AUDIT_MD,
    LITERATURE_EVIDENCE_CONTRACT_JSON,
    LITERATURE_EVIDENCE_CONTRACT_MD,
    LITERATURE_GATE_DECISION_JSON,
    LITERATURE_GATE_DECISION_MD,
]


def backfill_literature_context_artifacts(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "reused_existing_context": 0,
        "built_from_curated": 0,
        "fallback_quality": 0,
        "reconstructed_source_health": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "skipped_no_context_source": 0,
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
        existing_bundle = _bundle_exists(run_dir)
        if existing_bundle and not force:
            context = _read_context(run_dir / LITERATURE_CONTEXT_JSON)
            citation_audit = _read_json(run_dir / CITATION_AUDIT_JSON)
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", context, citation_audit, meta={}, artifact_actions=[]))
            continue
        try:
            context, reports, meta = build_literature_context_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_context_source"] += 1
            report["items"].append(_item(run_dir, "skipped_no_context_source", None, {}, meta={}, artifact_actions=[], error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", None, {}, meta={}, artifact_actions=[], error=str(exc)))
            continue
        _accumulate_meta(report, meta)
        artifact_actions = _planned_actions(run_dir, force)
        action = _action(meta.get("reused_existing_context") is True, force, run_dir)
        if dry_run:
            report["would_write_runs"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", context, _report_dict(audit_citations(context)), meta=meta, artifact_actions=artifact_actions))
            continue
        context, citation_audit = write_context_and_citation_artifacts(
            run_dir,
            context,
            topic=_topic(run_dir, context.topic),
            quality_report=reports["quality"],
            source_health_report=reports["source_health"],
            query_execution_report=reports["query_execution"],
            rerank_report=reports["rerank"],
            coverage_report=reports["coverage"],
            evidence_mix_report=reports["evidence_mix"],
            rescue_report=reports["rescue"],
            rescue_execution_report=reports["rescue_execution"],
            seed_intake_report=reports["seed_intake"],
        )
        report["written_runs"] += 1
        report["items"].append(_item(run_dir, action, context, _report_dict(citation_audit), meta=meta, artifact_actions=artifact_actions))
    return report


def build_literature_context_for_run(run_dir: Path) -> tuple[Any, dict[str, Any], dict[str, bool]]:
    reports = _reports(run_dir)
    existing_context = _read_context(run_dir / LITERATURE_CONTEXT_JSON)
    if existing_context is not None:
        return (
            apply_literature_audits_to_context(
                existing_context,
                quality_report=reports["quality"],
                metadata_report=reports["metadata"],
                coverage_report=reports["coverage"],
                evidence_mix_report=reports["evidence_mix"],
                rescue_report=reports["rescue"],
                seed_intake_report=reports["seed_intake"],
            ),
            reports,
            {
                "reused_existing_context": True,
                "built_from_curated": False,
                "fallback_quality": False,
                "reconstructed_source_health": False,
            },
        )

    raw_review = _load_raw_review(run_dir)
    review_for_quality, reconstructed_source_health = _source_health_review(raw_review)
    fallback_quality = False
    quality_report = reports["quality"]
    if not quality_report:
        quality_report = assess_literature_quality(review_for_quality)
        reports["quality"] = quality_report
        fallback_quality = True

    curated_path = run_dir / LITERATURE_CURATED_JSON
    if curated_path.exists():
        curated_review = _read_literature_review(curated_path)
    else:
        quality_value = _quality_report_value(quality_report)
        if isinstance(quality_value, dict):
            quality_value = assess_literature_quality(review_for_quality)
        curated_review = filter_review_by_quality(review_for_quality, quality_value)

    context = apply_literature_audits_to_context(
        build_literature_context(curated_review),
        quality_report=quality_report,
        metadata_report=reports["metadata"],
        coverage_report=reports["coverage"],
        evidence_mix_report=reports["evidence_mix"],
        rescue_report=reports["rescue"],
        seed_intake_report=reports["seed_intake"],
    )
    return (
        context,
        reports,
        {
            "reused_existing_context": False,
            "built_from_curated": True,
            "fallback_quality": fallback_quality,
            "reconstructed_source_health": reconstructed_source_health,
        },
    )


def render_literature_context_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Context Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 run：{report.get('written_runs', 0)}",
        f"- 将写入 run：{report.get('would_write_runs', 0)}",
        f"- 复用已有 context：{report.get('reused_existing_context', 0)}",
        f"- 从 curated review 重建：{report.get('built_from_curated', 0)}",
        f"- quality fallback：{report.get('fallback_quality', 0)}",
        f"- 重建 source health：{report.get('reconstructed_source_health', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少 context 来源跳过：{report.get('skipped_no_context_source', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 01-context.*、01-review-gate.md、01-references.*、01-citation-audit.*、01-literature-evidence-contract.*、01-literature-gate-decision.*；不会生成论文、不会批准 gate、不会恢复 pipeline。",
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
                "| Run | Action | Source | Gate | Citations | Chunks | Claims | Review | Blocked | Fallbacks | Artifacts |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
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
                        _cell(str(item.get("context_source") or "-")),
                        _cell(str(item.get("gate_status") or "-")),
                        str(item.get("citations") or 0),
                        str(item.get("chunks") or 0),
                        str(item.get("claim_support") or 0),
                        str(item.get("review_citations") or 0),
                        str(item.get("blocked_citations") or 0),
                        _cell(", ".join(_string_list(item.get("fallbacks"))) or "-"),
                        _cell(", ".join(_string_list(item.get("artifact_actions"))) or "-"),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _bundle_exists(run_dir: Path) -> bool:
    return all((run_dir / name).exists() for name in CONTEXT_BUNDLE)


def _reports(run_dir: Path) -> dict[str, Any]:
    return {
        "quality": _read_json(run_dir / LITERATURE_QUALITY_JSON),
        "metadata": _read_json(run_dir / "01-literature-metadata-audit.json"),
        "coverage": _read_json(run_dir / "01-literature-coverage.json"),
        "evidence_mix": _read_json(run_dir / "01-literature-evidence-mix.json"),
        "rescue": _read_json(run_dir / "01-literature-rescue-plan.json"),
        "rescue_execution": _read_json(run_dir / "01-literature-rescue-execution.json"),
        "seed_intake": _read_json(run_dir / "01-seed-paper-intake.json"),
        "source_health": _read_json(run_dir / "01-literature-source-health.json"),
        "query_execution": _read_json(run_dir / "01-query-execution-audit.json"),
        "rerank": _read_json(run_dir / "01-literature-rerank.json"),
    }


def _accumulate_meta(report: dict[str, Any], meta: dict[str, bool]) -> None:
    if meta.get("reused_existing_context"):
        report["reused_existing_context"] += 1
    if meta.get("built_from_curated"):
        report["built_from_curated"] += 1
    if meta.get("fallback_quality"):
        report["fallback_quality"] += 1
    if meta.get("reconstructed_source_health"):
        report["reconstructed_source_health"] += 1


def _planned_actions(run_dir: Path, force: bool) -> list[str]:
    if force:
        return list(CONTEXT_BUNDLE)
    return [name for name in CONTEXT_BUNDLE if not (run_dir / name).exists()]


def _action(reused_existing_context: bool, force: bool, run_dir: Path) -> str:
    existing_any = any((run_dir / name).exists() for name in CONTEXT_BUNDLE)
    if reused_existing_context:
        return "overwrite_existing_context" if force and existing_any else "refresh_existing_context"
    return "overwrite_from_curated" if force and existing_any else "write_from_curated"


def _item(
    run_dir: Path,
    action: str,
    context: Any,
    citation_audit: dict[str, Any],
    *,
    meta: dict[str, bool],
    artifact_actions: list[str],
    error: str = "",
) -> dict[str, Any]:
    gate = getattr(context, "review_gate", None)
    citations = getattr(context, "citations", None) if context is not None else None
    chunks = getattr(context, "chunks", None) if context is not None else None
    claim_support = getattr(context, "claim_support", None) if context is not None else None
    return {
        "run_id": run_dir.name,
        "action": action,
        "context_source": "existing_context" if meta.get("reused_existing_context") else "curated_review" if meta.get("built_from_curated") else "",
        "gate_status": getattr(gate, "status", "") if gate is not None else "",
        "citations": len(citations) if isinstance(citations, list) else 0,
        "chunks": len(chunks) if isinstance(chunks, list) else 0,
        "claim_support": len(claim_support) if isinstance(claim_support, list) else 0,
        "review_citations": _safe_int(citation_audit.get("review_required")),
        "blocked_citations": _safe_int(citation_audit.get("blocked_citations")),
        "fallbacks": _fallbacks(meta),
        "artifact_actions": artifact_actions,
        "error": error,
    }


def _fallbacks(meta: dict[str, bool]) -> list[str]:
    rows: list[str] = []
    if meta.get("fallback_quality"):
        rows.append("quality")
    if meta.get("reconstructed_source_health"):
        rows.append("source_health")
    return rows


def _report_dict(report: Any) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    result: dict[str, Any] = {}
    for key in dir(report):
        if key.startswith("_"):
            continue
        value = getattr(report, key, None)
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
            result[key] = value
    return result


def _topic(run_dir: Path, fallback: str) -> str:
    state = _read_json(run_dir / "state.json")
    return str(state.get("topic") or fallback or run_dir.name)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


