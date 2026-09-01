from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import write_json, write_text
from .literature_coverage import (
    LITERATURE_COVERAGE_JSON,
    LITERATURE_COVERAGE_MD,
    build_literature_coverage_report,
    render_literature_coverage_markdown,
)
from .literature_evidence_mix import (
    LITERATURE_EVIDENCE_MIX_JSON,
    LITERATURE_EVIDENCE_MIX_MD,
    build_literature_evidence_mix_report,
    render_literature_evidence_mix_markdown,
)
from .literature_metadata_audit import (
    LITERATURE_METADATA_AUDIT_JSON,
    LITERATURE_METADATA_AUDIT_MD,
    build_literature_metadata_audit_report,
    render_literature_metadata_audit_markdown,
)
from .literature_quality import assess_literature_quality, filter_review_by_quality
from .literature_quality_backfill import LITERATURE_CURATED_JSON, LITERATURE_QUALITY_JSON, _quality_report_value
from .literature_rescue_backfill import _load_raw_review, _load_research_plan, _read_json, _read_literature_review, _safe_int, _topic_from_state, _utc_now
from .literature_search_audit_backfill import _source_health_review
from .models import LiteratureReview


AUDIT_BUNDLE = {
    "metadata": (LITERATURE_METADATA_AUDIT_JSON, LITERATURE_METADATA_AUDIT_MD),
    "coverage": (LITERATURE_COVERAGE_JSON, LITERATURE_COVERAGE_MD),
    "evidence_mix": (LITERATURE_EVIDENCE_MIX_JSON, LITERATURE_EVIDENCE_MIX_MD),
}


def backfill_literature_audits(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "written_metadata": 0,
        "written_coverage": 0,
        "written_evidence_mix": 0,
        "fallback_research_plan": 0,
        "fallback_quality": 0,
        "generated_curated": 0,
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
        existing = {name: _artifact_pair_exists(run_dir, *paths) for name, paths in AUDIT_BUNDLE.items()}
        if all(existing.values()) and not force:
            report["skipped_existing"] += 1
            report["items"].append(
                _item(
                    run_dir,
                    "skipped_existing",
                    _read_json(run_dir / LITERATURE_METADATA_AUDIT_JSON),
                    _read_json(run_dir / LITERATURE_COVERAGE_JSON),
                    _read_json(run_dir / LITERATURE_EVIDENCE_MIX_JSON),
                    meta={},
                    artifact_actions=[],
                )
            )
            continue
        try:
            reports, meta = build_literature_audits_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, {}, {}, meta={}, artifact_actions=[], error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, {}, {}, meta={}, artifact_actions=[], error=str(exc)))
            continue
        _accumulate_meta(report, meta)
        artifact_actions = _planned_actions(existing, force)
        action = "overwrite" if force and any(existing.values()) else "write"
        if dry_run:
            report["would_write_runs"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", reports["metadata"], reports["coverage"], reports["evidence_mix"], meta=meta, artifact_actions=artifact_actions))
            continue
        if force or not existing["metadata"]:
            write_json(run_dir / LITERATURE_METADATA_AUDIT_JSON, reports["metadata"])
            write_text(run_dir / LITERATURE_METADATA_AUDIT_MD, render_literature_metadata_audit_markdown(reports["metadata"]))
            report["written_metadata"] += 1
        if force or not existing["coverage"]:
            write_json(run_dir / LITERATURE_COVERAGE_JSON, reports["coverage"])
            write_text(run_dir / LITERATURE_COVERAGE_MD, render_literature_coverage_markdown(reports["coverage"]))
            report["written_coverage"] += 1
        if force or not existing["evidence_mix"]:
            write_json(run_dir / LITERATURE_EVIDENCE_MIX_JSON, reports["evidence_mix"])
            write_text(run_dir / LITERATURE_EVIDENCE_MIX_MD, render_literature_evidence_mix_markdown(reports["evidence_mix"]))
            report["written_evidence_mix"] += 1
        report["written_runs"] += 1
        report["items"].append(_item(run_dir, action, reports["metadata"], reports["coverage"], reports["evidence_mix"], meta=meta, artifact_actions=artifact_actions))
    return report


def build_literature_audits_for_run(run_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, bool]]:
    raw_review = _load_raw_review(run_dir)
    research_plan, fallback_research_plan = _load_research_plan(run_dir, raw_review.topic or _topic_from_state(run_dir) or run_dir.name)
    quality_report, curated_review, quality_meta = _load_quality_and_curated(run_dir, raw_review)
    coverage_report = build_literature_coverage_report(research_plan, curated_review)
    return (
        {
            "metadata": build_literature_metadata_audit_report(raw_review, curated_review, quality_report),
            "coverage": coverage_report,
            "evidence_mix": build_literature_evidence_mix_report(research_plan, raw_review, curated_review, quality_report, coverage_report),
        },
        {
            "fallback_research_plan": fallback_research_plan,
            "fallback_quality": quality_meta["fallback_quality"],
            "generated_curated": quality_meta["generated_curated"],
            "reconstructed_source_health": quality_meta["reconstructed_source_health"],
        },
    )


def render_literature_audit_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Audit Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 run：{report.get('written_runs', 0)}",
        f"- 将写入 run：{report.get('would_write_runs', 0)}",
        f"- 写入 metadata audit：{report.get('written_metadata', 0)}",
        f"- 写入 coverage：{report.get('written_coverage', 0)}",
        f"- 写入 evidence mix：{report.get('written_evidence_mix', 0)}",
        f"- 规则 plan fallback：{report.get('fallback_research_plan', 0)}",
        f"- 重算 quality：{report.get('fallback_quality', 0)}",
        f"- 重建 curated review：{report.get('generated_curated', 0)}",
        f"- 重建 source health：{report.get('reconstructed_source_health', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 01-literature-metadata-audit.*、01-literature-coverage.*、01-literature-evidence-mix.*；不会批准 gate、不会恢复 pipeline、不会伪造 seed 配置。",
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
                "| Run | Action | Metadata | Coverage | Mix | Raw | Curated | Coverage Ratio | Mix Score | Fallbacks | Artifacts |",
                "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
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
                        _cell(str(item.get("metadata_status") or "-")),
                        _cell(str(item.get("coverage_status") or "-")),
                        _cell(str(item.get("evidence_mix_status") or "-")),
                        str(item.get("raw_papers") or 0),
                        str(item.get("curated_papers") or 0),
                        f"{float(item.get('coverage_ratio') or 0.0):.3f}",
                        f"{float(item.get('mix_score') or 0.0):.3f}",
                        _cell(", ".join(_string_list(item.get("fallbacks"))) or "-"),
                        _cell(", ".join(_string_list(item.get("artifact_actions"))) or "-"),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _load_quality_and_curated(run_dir: Path, raw_review: LiteratureReview) -> tuple[dict[str, Any] | Any, LiteratureReview, dict[str, bool]]:
    quality_report = _read_json(run_dir / LITERATURE_QUALITY_JSON)
    curated_path = run_dir / LITERATURE_CURATED_JSON
    need_generated_inputs = not quality_report or not curated_path.exists()
    review_for_quality = raw_review
    reconstructed_source_health = False
    if need_generated_inputs:
        review_for_quality, reconstructed_source_health = _source_health_review(raw_review)
    fallback_quality = not quality_report
    if fallback_quality:
        quality_report = assess_literature_quality(review_for_quality)
    if curated_path.exists():
        return quality_report, _read_literature_review(curated_path), {"fallback_quality": fallback_quality, "generated_curated": False, "reconstructed_source_health": reconstructed_source_health}
    quality_value = _quality_report_value(quality_report)
    return quality_report, filter_review_by_quality(review_for_quality, quality_value), {"fallback_quality": fallback_quality, "generated_curated": True, "reconstructed_source_health": reconstructed_source_health}


def _item(
    run_dir: Path,
    action: str,
    metadata_report: dict[str, Any],
    coverage_report: dict[str, Any],
    evidence_mix_report: dict[str, Any],
    *,
    meta: dict[str, bool],
    artifact_actions: list[str],
    error: str = "",
) -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "action": action,
        "metadata_status": str(metadata_report.get("status") or ""),
        "coverage_status": str(coverage_report.get("status") or ""),
        "evidence_mix_status": str(evidence_mix_report.get("status") or ""),
        "raw_papers": _safe_int(metadata_report.get("raw_papers")),
        "curated_papers": _safe_int(metadata_report.get("curated_papers")),
        "coverage_ratio": _safe_float(coverage_report.get("coverage_ratio")),
        "mix_score": _safe_float(evidence_mix_report.get("mix_score")),
        "fallbacks": _fallbacks(meta),
        "artifact_actions": artifact_actions,
        "error": error,
    }


def _accumulate_meta(report: dict[str, Any], meta: dict[str, bool]) -> None:
    if meta.get("fallback_research_plan"):
        report["fallback_research_plan"] += 1
    if meta.get("fallback_quality"):
        report["fallback_quality"] += 1
    if meta.get("generated_curated"):
        report["generated_curated"] += 1
    if meta.get("reconstructed_source_health"):
        report["reconstructed_source_health"] += 1


def _artifact_pair_exists(run_dir: Path, json_name: str, md_name: str) -> bool:
    return (run_dir / json_name).exists() and (run_dir / md_name).exists()


def _planned_actions(existing: dict[str, bool], force: bool) -> list[str]:
    if force:
        return list(AUDIT_BUNDLE)
    return [name for name, present in existing.items() if not present]


def _fallbacks(meta: dict[str, bool]) -> list[str]:
    rows: list[str] = []
    if meta.get("fallback_research_plan"):
        rows.append("research_plan")
    if meta.get("fallback_quality"):
        rows.append("quality")
    if meta.get("generated_curated"):
        rows.append("curated")
    if meta.get("reconstructed_source_health"):
        rows.append("source_health")
    return rows


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _safe_float(value: Any) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return 0.0


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
