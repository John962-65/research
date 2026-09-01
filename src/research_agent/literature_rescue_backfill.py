from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .literature_coverage import build_literature_coverage_report
from .literature_quality import assess_literature_quality, filter_review_by_quality
from .literature_rescue_plan import (
    LITERATURE_RESCUE_PLAN_JSON,
    LITERATURE_RESCUE_PLAN_MD,
    build_literature_rescue_plan,
    render_literature_rescue_plan_markdown,
)
from .literature_snowball import build_literature_snowball_report
from .models import LiteratureReview, Paper, ResearchPlan
from .research_plan import build_research_plan


PAPER_FIELDS = {field.name for field in fields(Paper)}


def backfill_literature_rescue_plans(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "scanned_runs": 0,
        "written": 0,
        "would_write": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "skipped_no_literature": 0,
        "fallback_research_plan": 0,
        "fallback_quality": 0,
        "fallback_coverage": 0,
        "fallback_snowball": 0,
        "generated_curated": 0,
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
        exists = (run_dir / LITERATURE_RESCUE_PLAN_JSON).exists() and (run_dir / LITERATURE_RESCUE_PLAN_MD).exists()
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", _read_json(run_dir / LITERATURE_RESCUE_PLAN_JSON), meta={}))
            continue
        try:
            rescue_plan, meta = build_literature_rescue_plan_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, meta={}, error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, meta={}, error=str(exc)))
            continue
        _accumulate_meta(report, meta)
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", rescue_plan, meta=meta))
            continue
        write_json(run_dir / LITERATURE_RESCUE_PLAN_JSON, rescue_plan)
        write_text(run_dir / LITERATURE_RESCUE_PLAN_MD, render_literature_rescue_plan_markdown(rescue_plan))
        report["written"] += 1
        report["items"].append(_item(run_dir, action, rescue_plan, meta=meta))
    return report


def build_literature_rescue_plan_for_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    raw_review = _load_raw_review(run_dir)
    research_plan, fallback_plan = _load_research_plan(run_dir, raw_review.topic or _topic_from_state(run_dir) or run_dir.name)
    quality_report, fallback_quality = _load_quality_report(run_dir, raw_review)
    curated_review, generated_curated = _load_curated_review(run_dir, raw_review, quality_report)
    coverage_report, fallback_coverage = _load_coverage_report(run_dir, research_plan, curated_review)
    snowball_report, fallback_snowball = _load_snowball_report(run_dir, raw_review, quality_report)
    report = build_literature_rescue_plan(
        research_plan,
        raw_review,
        curated_review,
        quality_report,
        snowball_report,
        coverage_report,
    )
    meta = {
        "fallback_research_plan": fallback_plan,
        "fallback_quality": fallback_quality,
        "fallback_coverage": fallback_coverage,
        "fallback_snowball": fallback_snowball,
        "generated_curated": generated_curated,
    }
    return report, meta


def render_literature_rescue_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Rescue Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 rescue plan：{report.get('written', 0)}",
        f"- 将写入 rescue plan：{report.get('would_write', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 规则 plan fallback：{report.get('fallback_research_plan', 0)}",
        f"- 重算 quality：{report.get('fallback_quality', 0)}",
        f"- 重算 coverage：{report.get('fallback_coverage', 0)}",
        f"- 重算 snowball：{report.get('fallback_snowball', 0)}",
        f"- 重建 curated review：{report.get('generated_curated', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 01-literature-rescue-plan.*；不会批准 review gate、不会恢复 pipeline、不会执行补检索或实验。",
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
                "| Run | Action | Status | Raw | Selected | Coverage | Queries | Fallbacks |",
                "| --- | --- | --- | ---: | ---: | --- | ---: | --- |",
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
                        _cell(str(item.get("status") or "-")),
                        str(item.get("raw_papers") or 0),
                        str(item.get("selected_papers") or 0),
                        _cell(str(item.get("coverage_status") or "-")),
                        str(item.get("rescue_queries") or 0),
                        _cell(", ".join(_string_list(item.get("fallbacks"))) or "-"),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _load_raw_review(run_dir: Path) -> LiteratureReview:
    for name in ["01-literature.json", "01-literature-curated.json"]:
        path = run_dir / name
        if path.exists():
            return _read_literature_review(path)
    raise ValueError("missing literature review artifacts")


def _load_research_plan(run_dir: Path, topic: str) -> tuple[ResearchPlan, bool]:
    fallback = build_research_plan(topic)
    data = _read_json(run_dir / "00-research-plan.json")
    if not data:
        return fallback, True
    used_fallback = not (
        str(data.get("domain") or "").strip()
        and str(data.get("objective") or "").strip()
        and _string_list(data.get("search_queries"))
        and _string_list(data.get("benchmarks"))
        and _string_list(data.get("baselines"))
        and _string_list(data.get("metrics"))
    )
    return (
        ResearchPlan(
            topic=str(data.get("topic") or fallback.topic or topic),
            domain=str(data.get("domain") or fallback.domain),
            objective=str(data.get("objective") or fallback.objective),
            search_queries=_string_list(data.get("search_queries")) or fallback.search_queries,
            benchmarks=_string_list(data.get("benchmarks")) or fallback.benchmarks,
            baselines=_string_list(data.get("baselines")) or fallback.baselines,
            metrics=_string_list(data.get("metrics")) or fallback.metrics,
            constraints=_string_list(data.get("constraints")) or fallback.constraints,
            risks=_string_list(data.get("risks")) or fallback.risks,
            success_criteria=_string_list(data.get("success_criteria")) or fallback.success_criteria,
        ),
        used_fallback,
    )


def _load_quality_report(run_dir: Path, raw_review: LiteratureReview) -> tuple[dict[str, Any] | Any, bool]:
    data = _read_json(run_dir / "01-literature-quality.json")
    if data:
        return data, False
    return assess_literature_quality(raw_review), True


def _load_curated_review(run_dir: Path, raw_review: LiteratureReview, quality_report: dict[str, Any] | Any) -> tuple[LiteratureReview, bool]:
    curated_path = run_dir / "01-literature-curated.json"
    if curated_path.exists():
        return _read_literature_review(curated_path), False
    if is_dataclass(quality_report):
        return filter_review_by_quality(raw_review, quality_report), True
    quality = _quality_dict(quality_report)
    selected_titles = {
        str(item.get("title") or "").strip()
        for item in quality.get("items", [])
        if isinstance(item, dict) and item.get("selected") is True and str(item.get("title") or "").strip()
    }
    if not selected_titles:
        return raw_review, False
    return replace(raw_review, papers=[paper for paper in raw_review.papers if paper.title in selected_titles]), True


def _load_coverage_report(run_dir: Path, research_plan: ResearchPlan, curated_review: LiteratureReview) -> tuple[dict[str, Any], bool]:
    data = _read_json(run_dir / "01-literature-coverage.json")
    if data:
        return data, False
    return build_literature_coverage_report(research_plan, curated_review), True


def _load_snowball_report(run_dir: Path, raw_review: LiteratureReview, quality_report: dict[str, Any] | Any) -> tuple[dict[str, Any], bool]:
    data = _read_json(run_dir / "01-literature-snowball.json")
    if data:
        return data, False
    return build_literature_snowball_report(raw_review, quality_report), True


def _read_literature_review(path: Path) -> LiteratureReview:
    data = _read_json(path)
    if not data:
        raise ValueError(f"invalid literature review JSON: {path.name}")
    papers: list[Paper] = []
    for item in data.get("papers", []) if isinstance(data.get("papers"), list) else []:
        if not isinstance(item, dict):
            continue
        payload = {key: item[key] for key in PAPER_FIELDS if key in item}
        try:
            papers.append(Paper(**payload))
        except TypeError:
            continue
    return LiteratureReview(
        topic=str(data.get("topic") or ""),
        papers=papers,
        themes=_string_list(data.get("themes")),
        gaps=_string_list(data.get("gaps")),
        summary=str(data.get("summary") or ""),
        source_diagnostics=_string_list(data.get("source_diagnostics")),
        evidence_table=[dict(item) for item in data.get("evidence_table", []) if isinstance(item, dict)],
        source_health=[dict(item) for item in data.get("source_health", []) if isinstance(item, dict)],
        search_strategy=dict(data.get("search_strategy", {})) if isinstance(data.get("search_strategy"), dict) else {},
    )


def _item(run_dir: Path, action: str, rescue_plan: dict[str, Any], *, meta: dict[str, bool], error: str = "") -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": str(rescue_plan.get("status") or ""),
        "raw_papers": _safe_int(rescue_plan.get("raw_papers")),
        "selected_papers": _safe_int(rescue_plan.get("selected_papers")),
        "coverage_status": str(rescue_plan.get("coverage_status") or ""),
        "weak_reasons": len(rescue_plan.get("weak_reasons", [])) if isinstance(rescue_plan.get("weak_reasons"), list) else 0,
        "source_repairs": len(rescue_plan.get("source_repairs", [])) if isinstance(rescue_plan.get("source_repairs"), list) else 0,
        "rescue_queries": len(rescue_plan.get("rescue_queries", [])) if isinstance(rescue_plan.get("rescue_queries"), list) else 0,
        "required_actions": len(rescue_plan.get("required_actions", [])) if isinstance(rescue_plan.get("required_actions"), list) else 0,
        "fallbacks": _fallbacks(meta),
        "error": error,
    }


def _accumulate_meta(report: dict[str, Any], meta: dict[str, bool]) -> None:
    if meta.get("fallback_research_plan"):
        report["fallback_research_plan"] += 1
    if meta.get("fallback_quality"):
        report["fallback_quality"] += 1
    if meta.get("fallback_coverage"):
        report["fallback_coverage"] += 1
    if meta.get("fallback_snowball"):
        report["fallback_snowball"] += 1
    if meta.get("generated_curated"):
        report["generated_curated"] += 1


def _fallbacks(meta: dict[str, bool]) -> list[str]:
    rows: list[str] = []
    if meta.get("fallback_research_plan"):
        rows.append("research_plan")
    if meta.get("fallback_quality"):
        rows.append("quality")
    if meta.get("fallback_coverage"):
        rows.append("coverage")
    if meta.get("fallback_snowball"):
        rows.append("snowball")
    if meta.get("generated_curated"):
        rows.append("curated")
    return rows


def _quality_dict(report: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    if is_dataclass(report):
        return asdict(report)
    return {}


def _topic_from_state(run_dir: Path) -> str:
    data = _read_json(run_dir / "state.json")
    return str(data.get("topic") or "")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


