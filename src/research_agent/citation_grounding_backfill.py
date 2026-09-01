from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .citation_grounding import CITATION_GROUNDING_JSON, CITATION_GROUNDING_MD, build_citation_grounding_report, render_citation_grounding_markdown
from .literature_gate_backfill import _read_context


def backfill_citation_grounding(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "skipped_no_context": 0,
        "skipped_no_paper": 0,
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
        exists = (run_dir / CITATION_GROUNDING_JSON).exists() and (run_dir / CITATION_GROUNDING_MD).exists()
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", _read_json(run_dir / CITATION_GROUNDING_JSON)))
            continue
        context = _read_context(run_dir / "01-context.json")
        if context is None:
            report["skipped_no_context"] += 1
            report["items"].append(_item(run_dir, "skipped_no_context", {}))
            continue
        if not _has_paper(run_dir):
            report["skipped_no_paper"] += 1
            report["items"].append(_item(run_dir, "skipped_no_paper", {}))
            continue
        try:
            grounding = build_citation_grounding_report(_topic(run_dir, context.topic), run_dir, context)
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, error=str(exc)))
            continue
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", _report_dict(grounding)))
            continue
        write_json(run_dir / CITATION_GROUNDING_JSON, grounding)
        write_text(run_dir / CITATION_GROUNDING_MD, render_citation_grounding_markdown(grounding))
        report["written"] += 1
        report["items"].append(_item(run_dir, action, _report_dict(grounding)))
    return report


def render_citation_grounding_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Citation Grounding Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 grounding：{report.get('written', 0)}",
        f"- 将写入 grounding：{report.get('would_write', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少 context 跳过：{report.get('skipped_no_context', 0)}",
        f"- 缺少修订稿跳过：{report.get('skipped_no_paper', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只根据 01-context.json 和现有 09-revised-paper.md/06-paper.md 生成 10-citation-grounding.*；不会生成论文、不会批准 gate、不会恢复 pipeline。",
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
                "| Run | Action | Status | Total | Pass | Review | Block | Score |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
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
                        str(item.get("total_citations") or 0),
                        str(item.get("passed_citations") or 0),
                        str(item.get("review_citations") or 0),
                        str(item.get("blocked_citations") or 0),
                        f"{float(item.get('grounding_score') or 0.0):.3f}",
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, report: dict[str, Any], error: str = "") -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": report.get("status", ""),
        "grounding_score": _safe_float(report.get("grounding_score")),
        "total_citations": _safe_int(report.get("total_citations")),
        "passed_citations": _safe_int(report.get("passed_citations")),
        "review_citations": _safe_int(report.get("review_citations")),
        "blocked_citations": _safe_int(report.get("blocked_citations")),
        "error": error,
    }


def _topic(run_dir: Path, fallback: str) -> str:
    state = _read_json(run_dir / "state.json")
    return str(state.get("topic") or fallback or run_dir.name)


def _has_paper(run_dir: Path) -> bool:
    for name in ["09-revised-paper.md", "06-paper.md"]:
        try:
            if (run_dir / name).read_text(encoding="utf-8").strip():
                return True
        except OSError:
            continue
    return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


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
