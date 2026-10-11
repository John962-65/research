"""材料导入：登记 + 哈希固定 + 表格解析摘要 + 指标方向声明提取。

支持格式：CSV / JSON（行数组或 {"rows": [...]}）/ JSONL。文件本体不复制、不修改；
导入只写登记项（含 sha256 与解析摘要），诊断时重新读取并核对哈希。

指标方向声明优先级：显式 meta["metric_directions"] > 同目录 manifest*.json 的
metric_schema.direction > 无声明（由名称启发式缺省并在输出中标注）。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from ..core.evidence import sha256_file
from ..core.models import Material
from ..core.storage import ProjectStore, now_iso

_QUERY_FIELD_CANDIDATES = ("query_id", "query", "case_id", "scene_id", "scenario_id", "task_id", "id")
_GROUP_FIELD_CANDIDATES = ("comparison_group", "group", "method", "variant", "arm")
_METRIC_FIELDS_TO_EXCLUDE = set(_QUERY_FIELD_CANDIDATES) | set(_GROUP_FIELD_CANDIDATES) | {
    "status", "seed", "repeat_index", "repeat", "name", "command", "stdout", "stderr",
}


def _sanitize_value(value: Any) -> Any:
    """numpy 标量 → Python 原生类型（JSON 安全）。"""
    module = type(value).__module__
    if module.startswith("numpy"):
        if value != value:  # NaN
            return None
        try:
            return value.item()
        except AttributeError:
            return str(value)
    return value


def _read_dta(path: Path) -> list[dict[str, Any]]:
    """Stata .dta（pandas 可选依赖；缺失时给出明确指引）。"""
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import pandas as pd

            frame = pd.read_stata(str(path))
    except ImportError as exc:
        raise ValueError(
            f"读取 .dta 需要 pandas（pip install 'research-copilot[eval]' 或 pip install pandas）：{exc}"
        ) from exc
    rows = []
    for record in frame.to_dict("records"):
        rows.append(
            {
                (str(key) if key is not None else "unnamed"): _sanitize_value(value)
                for key, value in record.items()
            }
        )
    return rows


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    """把 CSV/JSON/JSONL/DTA 读成行字典数组。"""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                {key: _maybe_number(value) for key, value in row.items() if key is not None}
                for row in csv.DictReader(handle)
            ]
    if suffix == ".jsonl":
        rows = []
        for line in source.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    if suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(row) for row in data]
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return [dict(row) for row in data["rows"]]
        raise ValueError(f"JSON 材料需为行数组或含 rows 字段: {source}")
    if suffix == ".dta":
        return _read_dta(source)
    raise ValueError(f"不支持的表格格式: {source}（支持 .csv/.json/.jsonl/.dta）")


def _maybe_number(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text) if text else value
        except ValueError:
            return value
    return value


def detect_query_field(columns: list[str]) -> str | None:
    for candidate in _QUERY_FIELD_CANDIDATES:
        if candidate in columns:
            return candidate
    return None


def detect_group_field(columns: list[str]) -> str | None:
    for candidate in _GROUP_FIELD_CANDIDATES:
        if candidate in columns:
            return candidate
    return None


def extract_metric_directions(path: str | Path, explicit: dict[str, str] | None = None) -> dict[str, str]:
    """提取指标方向声明：显式参数 > 同目录 manifest*.json。"""
    if explicit:
        return {str(k): str(v) for k, v in explicit.items() if v in ("lower_is_better", "higher_is_better")}
    source = Path(path)
    for manifest_path in sorted(source.parent.glob("manifest*.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        schema = manifest.get("metric_schema") or manifest.get("metrics") or {}
        directions: dict[str, str] = {}
        if isinstance(schema, dict):
            for name, spec in schema.items():
                if isinstance(spec, dict) and spec.get("direction") in ("lower_is_better", "higher_is_better"):
                    directions[str(name)] = spec["direction"]
                elif spec in ("lower_is_better", "higher_is_better"):
                    directions[str(name)] = str(spec)
        if directions:
            return directions
    return {}


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """解析摘要：列、数值列、状态取值、查询/分组字段探测。"""
    columns: list[str] = []
    for row in rows[:50]:
        for key in row:
            if key not in columns:
                columns.append(key)
    numeric_columns = []
    for column in columns:
        values = [row.get(column) for row in rows]
        numeric_hits = sum(1 for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))
        if numeric_hits >= max(1, int(0.5 * len(values))) and column not in _METRIC_FIELDS_TO_EXCLUDE:
            numeric_columns.append(column)
    status_values = sorted({str(row.get("status")) for row in rows if row.get("status") is not None})
    return {
        "n_rows": len(rows),
        "columns": columns,
        "numeric_columns": numeric_columns,
        "status_values": status_values,
        "query_field": detect_query_field(columns),
        "group_field": detect_group_field(columns),
    }


def import_material(
    store: ProjectStore,
    project_id: str,
    kind: str,
    path: str | Path,
    summary: str = "",
    meta: dict[str, Any] | None = None,
    rows_for_summary: list[dict[str, Any]] | None = None,
) -> Material:
    """登记材料。表格类材料自动解析摘要并提取方向声明。"""
    if kind not in ("results", "dataset", "code_repo", "paper_draft", "config", "review", "note", "legacy_run"):
        raise ValueError(f"未知材料类型: {kind}")
    source = Path(path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"材料文件不存在: {source}")
    meta = dict(meta or {})
    if kind in ("results", "dataset"):
        rows = rows_for_summary if rows_for_summary is not None else read_rows(source)
        parsed = summarize_rows(rows)
        directions = extract_metric_directions(source, meta.get("metric_directions"))
        parsed["metric_directions"] = directions
        parsed["directions_declared"] = bool(directions)
        meta["table"] = parsed
        if not summary:
            summary = f"表格 {parsed['n_rows']} 行 × {len(parsed['columns'])} 列；数值列 {parsed['numeric_columns']}"
    material = Material(
        id="",
        kind=kind,
        path=str(source),
        sha256=sha256_file(source),
        imported_at=now_iso(),
        summary=summary or source.name,
        meta=meta,
    )
    materials = store.load_materials(project_id)
    material.id = store.next_id(project_id, "MAT", [m.id for m in materials])
    materials.append(material)
    store.save_materials(project_id, materials)
    store.log_event(project_id, "material_imported", target=material.id, detail=f"{kind}: {source.name}")
    return material
