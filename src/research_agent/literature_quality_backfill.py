from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .literature import render_literature_markdown
from .literature_quality import assess_literature_quality, filter_review_by_quality, render_literature_quality_markdown
from .literature_rescue_backfill import _load_raw_review, _read_literature_review
from .literature_search_audit_backfill import _source_health_review
from .models import LiteratureReview


LITERATURE_QUALITY_JSON = "01-literature-quality.json"
LITERATURE_QUALITY_MD = "01-literature-quality.md"
LITERATURE_CURATED_JSON = "01-literature-curated.json"
LITERATURE_CURATED_MD = "01-literature-curated.md"


def backfill_literature_quality_artifacts(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "written_quality": 0,
        "written_curated": 0,
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
            "quality": _artifact_pair_exists(run_dir, LITERATURE_QUALITY_JSON, LITERATURE_QUALITY_MD),
            "curated": _artifact_pair_exists(run_dir, LITERATURE_CURATED_JSON, LITERATURE_CURATED_MD),
        }
        if all(existing.values()) and not force:
            quality = _read_json(run_dir / LITERATURE_QUALITY_JSON)
            curated = _read_literature_review(run_dir / LITERATURE_CURATED_JSON)
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", quality, curated, meta={}))
            continue
        try:
            quality_report, curated_review, meta = build_literature_quality_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, None, meta={}, error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, None, meta={}, error=str(exc)))
            continue
        _accumulate_meta(report, meta)
        planned_actions = _planned_actions(existing, force)
        action = "overwrite" if force and any(existing.values()) else "write"
        if dry_run:
            report["would_write_runs"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", quality_report, curated_review, meta=meta, artifact_actions=planned_actions))
            continue
        if force or not existing["quality"]:
            write_json(run_dir / LITERATURE_QUALITY_JSON, quality_report)
            write_text(run_dir / LITERATURE_QUALITY_MD, render_literature_quality_markdown(_quality_report_value(quality_report)))
            report["written_quality"] += 1
        if force or not existing["curated"]:
            write_json(run_dir / LITERATURE_CURATED_JSON, curated_review)
            write_text(run_dir / LITERATURE_CURATED_MD, render_literature_markdown(curated_review))
            report["written_curated"] += 1
        report["written_runs"] += 1
        report["items"].append(_item(run_dir, action, quality_report, curated_review, meta=meta, artifact_actions=planned_actions))
    return report


def build_literature_quality_for_run(run_dir: Path) -> tuple[dict[str, Any] | Any, LiteratureReview, dict[str, bool]]:
    raw_review = _load_raw_review(run_dir)
    review_for_quality, reconstructed_source_health = _source_health_review(raw_review)
    quality_report = assess_literature_quality(review_for_quality)
    curated_review = filter_review_by_quality(review_for_quality, quality_report)
    return quality_report, curated_review, {"reconstructed_source_health": reconstructed_source_health}


def render_literature_quality_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Quality Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 run：{report.get('written_runs', 0)}",
        f"- 将写入 run：{report.get('would_write_runs', 0)}",
        f"- 写入 quality：{report.get('written_quality', 0)}",
        f"- 写入 curated：{report.get('written_curated', 0)}",
        f"- 重建 source health：{report.get('reconstructed_source_health', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 01-literature-quality.*、01-literature-curated.*；不会改写 01-literature.json、不会批准 gate、不会恢复 pipeline。",
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
                "| Run | Action | Confidence | Raw | Selected | Curated | Warnings | Missing Roles | Fallbacks | Artifacts |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
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
                        _cell(str(item.get("confidence_status") or "-")),
                        str(item.get("raw_papers") or 0),
                        str(item.get("selected_papers") or 0),
                        str(item.get("curated_papers") or 0),
                        str(item.get("warnings") or 0),
                        str(item.get("missing_roles") or 0),
                        _cell(", ".join(_string_list(item.get("fallbacks"))) or "-"),
                        _cell(", ".join(_string_list(item.get("artifact_actions"))) or "-"),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(
    run_dir: Path,
    action: str,
    quality_report: dict[str, Any] | Any,
    curated_review: LiteratureReview | None,
    *,
    meta: dict[str, bool],
    artifact_actions: list[str] | None = None,
    error: str = "",
) -> dict[str, Any]:
    quality = _quality_dict(quality_report)
    warnings = quality.get("warnings", []) if isinstance(quality.get("warnings"), list) else []
    missing_roles = quality.get("missing_evidence_roles", []) if isinstance(quality.get("missing_evidence_roles"), list) else []
    return {
        "run_id": run_dir.name,
        "action": action,
        "confidence_status": str(quality.get("confidence_status") or ""),
        "raw_papers": _safe_int(quality.get("total_papers")),
        "selected_papers": _safe_int(quality.get("selected_papers")),
        "curated_papers": len(curated_review.papers) if curated_review is not None else 0,
        "warnings": len(warnings),
        "missing_roles": len(missing_roles),
        "fallbacks": _fallbacks(meta),
        "artifact_actions": artifact_actions or [],
        "error": error,
    }


def _artifact_pair_exists(run_dir: Path, json_name: str, md_name: str) -> bool:
    return (run_dir / json_name).exists() and (run_dir / md_name).exists()


def _accumulate_meta(report: dict[str, Any], meta: dict[str, bool]) -> None:
    if meta.get("reconstructed_source_health"):
        report["reconstructed_source_health"] += 1


def _planned_actions(existing: dict[str, bool], force: bool) -> list[str]:
    if force:
        return ["quality", "curated"]
    rows: list[str] = []
    if not existing.get("quality"):
        rows.append("quality")
    if not existing.get("curated"):
        rows.append("curated")
    return rows


def _fallbacks(meta: dict[str, bool]) -> list[str]:
    rows: list[str] = []
    if meta.get("reconstructed_source_health"):
        rows.append("source_health")
    return rows


def _quality_dict(report: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    if is_dataclass(report):
        return asdict(report)
    return {}


def _quality_report_value(report: dict[str, Any] | Any) -> Any:
    return report if not isinstance(report, dict) else _quality_report_from_dict(report)


def _quality_report_from_dict(report: dict[str, Any]) -> Any:
    try:
        from .models import LiteratureQualityItem, LiteratureQualityReport

        items = []
        raw_items = report.get("items") if isinstance(report.get("items"), list) else []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            items.append(
                LiteratureQualityItem(
                    title=str(item.get("title") or ""),
                    year=_safe_int(item.get("year")),
                    venue=str(item.get("venue") or ""),
                    sources=_item_sources(item),
                    relevance=_safe_float(item.get("relevance")),
                    quality_score=_safe_float(item.get("quality_score")),
                    decision=str(item.get("decision") or ""),
                    selected=item.get("selected") is True,
                    reasons=_string_list(item.get("reasons")),
                    doi=str(item.get("doi") or ""),
                    url=str(item.get("url") or ""),
                    evidence_roles=_string_list(item.get("evidence_roles")),
                )
            )
        return LiteratureQualityReport(
            topic=str(report.get("topic") or ""),
            total_papers=_safe_int(report.get("total_papers")),
            selected_papers=_safe_int(report.get("selected_papers")),
            min_keep=_safe_int(report.get("min_keep")),
            items=items,
            warnings=_string_list(report.get("warnings")),
            confidence_score=_safe_float(report.get("confidence_score")),
            confidence_status=str(report.get("confidence_status") or ""),
            confidence_factors=dict(report.get("confidence_factors", {})) if isinstance(report.get("confidence_factors"), dict) else {},
            source_warnings=_string_list(report.get("source_warnings")),
            recommended_actions=_string_list(report.get("recommended_actions")),
            role_coverage={str(key): _safe_int(value) for key, value in report.get("role_coverage", {}).items()} if isinstance(report.get("role_coverage"), dict) else {},
            missing_evidence_roles=_string_list(report.get("missing_evidence_roles")),
        )
    except Exception:  # pragma: no cover - defensive markdown fallback
        return report


def _item_sources(item: dict[str, Any]) -> list[str]:
    sources = _string_list(item.get("sources"))
    if sources:
        return sources
    source = str(item.get("source") or "").strip()
    return [source] if source else []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
