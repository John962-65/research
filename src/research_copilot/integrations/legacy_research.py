"""旧 research 仓库 run 产物的只读导入适配器。

只读取旧 run 目录的 04-results.json / 03-benchmark-adapters.json 等文件，
转换为 Research Copilot 的行格式并登记为 legacy_run 材料；绝不修改旧仓库。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.storage import ProjectStore
from .material_importer import import_material

_RESULT_STATUSES_OK = {"passed", "success", "ok"}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def normalize_legacy_results(run_dir: str | Path) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    """把旧 04-results.json 展平为逐指标行。

    返回 (rows, metric_directions, notes)。
    旧格式：{"results": [{name, status, metrics: {metric: value}, seed, repeat_index,
    comparison_group, duration_seconds, ...}]}。name 作为查询近似键（旧数据无独立
    query_id 时按 run 名聚合，导入摘要有说明）。
    """
    run_dir = Path(run_dir)
    notes: list[str] = []
    payload = _load_json(run_dir / "04-results.json")
    rows: list[dict[str, Any]] = []
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        for index, result in enumerate(payload["results"]):
            if not isinstance(result, dict):
                continue
            status = str(result.get("status") or "")
            status = status if status in _RESULT_STATUSES_OK else status or "unknown"
            base = {
                "name": result.get("name") or f"row-{index}",
                "status": status,
                "seed": result.get("seed") or "",
                "repeat_index": result.get("repeat_index"),
                "comparison_group": result.get("comparison_group") or "default",
                "duration_seconds": result.get("duration_seconds"),
            }
            metrics = result.get("metrics") or {}
            if not isinstance(metrics, dict):
                continue
            if not metrics:
                base["value"] = None
                rows.append(base)
                continue
            for metric, value in metrics.items():
                row = dict(base)
                row["metric"] = str(metric)
                row["value"] = value
                rows.append(row)
        notes.append("旧格式 04-results.json 为逐 run 记录：name 字段用作查询近似键")
    else:
        notes.append("未找到可解析的 04-results.json")

    directions: dict[str, str] = {}
    adapters = _load_json(run_dir / "03-benchmark-adapters.json")
    if isinstance(adapters, dict):
        for adapter in adapters.get("adapters", []) if isinstance(adapters.get("adapters"), list) else []:
            if not isinstance(adapter, dict):
                continue
            schema = adapter.get("metric_schema") or {}
            if isinstance(schema, dict):
                for metric, spec in schema.items():
                    if isinstance(spec, dict) and spec.get("direction") in ("lower_is_better", "higher_is_better"):
                        directions[str(metric)] = spec["direction"]
    if not directions:
        notes.append("未在 03-benchmark-adapters.json 找到指标方向声明：解释时将回退名称启发式并标注")
    return rows, directions, notes


def import_legacy_run(store: ProjectStore, project_id: str, run_dir: str | Path) -> list:
    """把旧 run 目录导入为材料（results 表格 + 其余产物的引用登记）。"""
    run_dir = Path(run_dir).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"旧 run 目录不存在: {run_dir}")
    rows, directions, notes = normalize_legacy_results(run_dir)
    materials = []
    if rows:
        import json as _json

        normalized_path = store.require(project_id) / "imported"
        normalized_path.mkdir(parents=True, exist_ok=True)
        out_file = normalized_path / f"{run_dir.name}-results-normalized.json"
        out_file.write_text(
            _json.dumps({"rows": rows, "notes": notes, "metric_directions": directions}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        materials.append(
            import_material(
                store,
                project_id,
                "legacy_run",
                out_file,
                summary=f"来自旧 run {run_dir.name} 的规范化结果（源文件只读）",
                meta={
                    "legacy_run_dir": str(run_dir),
                    "metric_directions": directions,
                    "notes": notes,
                    "query_field": "name",
                },
                rows_for_summary=rows,
            )
        )
    for extra in ("paper-draft.md", "03-preregistration.json", "04-hypothesis-outcome.json", "04-statistics.json"):
        source = run_dir / extra
        if source.exists():
            materials.append(
                import_material(store, project_id, "legacy_run", source, summary=f"旧 run 产物 {extra}", meta={"legacy_run_dir": str(run_dir)})
            )
    return materials
