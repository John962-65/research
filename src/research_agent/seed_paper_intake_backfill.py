from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .seed_paper_intake import (
    SEED_PAPER_INTAKE_JSON,
    SEED_PAPER_INTAKE_MD,
    build_seed_paper_suggestion_report,
    build_unconfigured_seed_paper_intake_report,
    render_seed_paper_intake_markdown,
)


SEED_INPUTS = [
    "01-literature.json",
    "01-literature-curated.json",
    "01-literature-quality.json",
]


def backfill_seed_paper_intake_artifacts(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "written_seed_intake": 0,
        "suggested_runs": 0,
        "zero_suggestion_runs": 0,
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
        exists = _artifact_pair_exists(run_dir)
        if exists and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing", _read_json(run_dir / SEED_PAPER_INTAKE_JSON), suggested=False))
            continue
        try:
            seed_intake = build_seed_paper_intake_backfill_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, suggested=False, error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, suggested=False, error=str(exc)))
            continue
        if _safe_int(seed_intake.get("suggested_seed_count")) > 0:
            report["suggested_runs"] += 1
        else:
            report["zero_suggestion_runs"] += 1
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write_runs"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", seed_intake, suggested=_safe_int(seed_intake.get("suggested_seed_count")) > 0))
            continue
        write_json(run_dir / SEED_PAPER_INTAKE_JSON, seed_intake)
        write_text(run_dir / SEED_PAPER_INTAKE_MD, render_seed_paper_intake_markdown(seed_intake))
        report["written_runs"] += 1
        report["written_seed_intake"] += 1
        report["items"].append(_item(run_dir, action, seed_intake, suggested=_safe_int(seed_intake.get("suggested_seed_count")) > 0))
    return report


def build_seed_paper_intake_backfill_for_run(run_dir: Path) -> dict[str, Any]:
    if not any((run_dir / name).exists() for name in SEED_INPUTS):
        raise ValueError("missing literature artifacts")
    topic = _topic(run_dir)
    suggestion = build_seed_paper_suggestion_report(topic, run_dir)
    return build_unconfigured_seed_paper_intake_report(topic, suggestion_report=suggestion)


def render_seed_paper_intake_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Seed Paper Intake Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入 run：{report.get('written_runs', 0)}",
        f"- 将写入 run：{report.get('would_write_runs', 0)}",
        f"- 写入 seed intake：{report.get('written_seed_intake', 0)}",
        f"- 有候选建议的 run：{report.get('suggested_runs', 0)}",
        f"- 无候选建议的 run：{report.get('zero_suggestion_runs', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只生成保守的 01-seed-paper-intake.*，记录历史 run 未配置人工 seed，并附带候选 DOI/URL 建议；不会伪造 seed 配置、不会批准 gate、不会恢复 pipeline。",
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
                "| Run | Action | Status | Role Coverage | Suggested | Missing Roles | Actions |",
                "| --- | --- | --- | --- | ---: | --- | ---: |",
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
                        _cell(str(item.get("role_coverage_status") or "-")),
                        str(item.get("suggested_seed_count") or 0),
                        _cell(", ".join(_string_list(item.get("missing_roles"))) or "-"),
                        str(item.get("required_actions") or 0),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _artifact_pair_exists(run_dir: Path) -> bool:
    return (run_dir / SEED_PAPER_INTAKE_JSON).exists() and (run_dir / SEED_PAPER_INTAKE_MD).exists()


def _item(run_dir: Path, action: str, seed_intake: dict[str, Any], *, suggested: bool, error: str = "") -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": str(seed_intake.get("status") or ""),
        "role_coverage_status": str(seed_intake.get("role_coverage_status") or ""),
        "suggested_seed_count": _safe_int(seed_intake.get("suggested_seed_count")),
        "missing_roles": _string_list(seed_intake.get("missing_roles")),
        "required_actions": len(seed_intake.get("required_actions", [])) if isinstance(seed_intake.get("required_actions"), list) else 0,
        "suggested": suggested,
        "error": error,
    }


def _topic(run_dir: Path) -> str:
    for name in ["state.json", "01-literature-curated.json", "01-literature.json"]:
        data = _read_json(run_dir / name)
        topic = str(data.get("topic") or "").strip()
        if topic:
            return topic
    return run_dir.name


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


