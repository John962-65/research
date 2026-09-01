from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .literature_rerank import LITERATURE_RERANK_JSON, LITERATURE_RERANK_MD, render_literature_rerank_markdown, rerank_literature_review
from .literature_rescue_backfill import _load_raw_review, _load_research_plan


def backfill_literature_rerank_artifacts(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "fallback_research_plan": 0,
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
        exists = (run_dir / LITERATURE_RERANK_JSON).exists() and (run_dir / LITERATURE_RERANK_MD).exists()
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", _read_json(run_dir / LITERATURE_RERANK_JSON)))
            continue
        try:
            rerank_report, fallback_research_plan = build_literature_rerank_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, error=str(exc)))
            continue
        if fallback_research_plan:
            report["fallback_research_plan"] += 1
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", rerank_report, fallback_research_plan=fallback_research_plan))
            continue
        write_json(run_dir / LITERATURE_RERANK_JSON, rerank_report)
        write_text(run_dir / LITERATURE_RERANK_MD, render_literature_rerank_markdown(rerank_report))
        report["written"] += 1
        report["items"].append(_item(run_dir, action, rerank_report, fallback_research_plan=fallback_research_plan))
    return report


def build_literature_rerank_for_run(run_dir: Path) -> tuple[dict[str, Any], bool]:
    review = _load_raw_review(run_dir)
    research_plan, fallback_research_plan = _load_research_plan(run_dir, review.topic or run_dir.name)
    _, rerank_report = rerank_literature_review(review, research_plan)
    return rerank_report, fallback_research_plan


def render_literature_rerank_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Rerank Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 rerank：{report.get('written', 0)}",
        f"- 将写入 rerank：{report.get('would_write', 0)}",
        f"- 规则 plan fallback：{report.get('fallback_research_plan', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成 01-literature-rerank.*；不会改写 01-literature.json、不会批准 gate、不会恢复 pipeline。",
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
                "| Run | Action | Status | Candidates | Top Titles | Warnings | Fallbacks |",
                "| --- | --- | --- | ---: | ---: | ---: | --- |",
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
                        str(item.get("total_candidates") or 0),
                        str(item.get("top_titles") or 0),
                        str(item.get("warnings") or 0),
                        "research_plan" if item.get("fallback_research_plan") else "-",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, rerank_report: dict[str, Any], *, fallback_research_plan: bool = False, error: str = "") -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": str(rerank_report.get("status") or ""),
        "total_candidates": _safe_int(rerank_report.get("total_candidates")),
        "top_titles": len(rerank_report.get("top_titles", [])) if isinstance(rerank_report.get("top_titles"), list) else 0,
        "warnings": len(rerank_report.get("warnings", [])) if isinstance(rerank_report.get("warnings"), list) else 0,
        "fallback_research_plan": fallback_research_plan,
        "error": error,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
