"""Import existing code/results entry (T09 / 任务书 §5 T09).

"我已有代码和实验结果，帮我检查是否足以支持结论"：允许把已有结果/契约/
预注册导入一个 run 目录，生成字段映射、来源与缺失项清单，不强迫重新生成
idea 或重写论文。导入不改变证据语义：04-results 按白名单与来源绑定校验，
evidence 状态由 evidence_integrity 独立评估；缺失字段按 unknown/incomplete
处理，不自动补成已验证。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import read_json, safe_int as _safe_int, utc_now as _utc_now, write_json
from .evidence_integrity import assess_evidence_integrity


IMPORT_REPORT_JSON = "00-import-report.json"

# 现有字段 → 冻结四类状态的映射（decision-contract §1.1/§1.2）。
_EXECUTION_MAP = {
    "passed": "completed",
    "failed": "failed",
    "timeout": "timed_out",
    "blocked": "blocked",
    "cancelled": "cancelled",
    "simulated": "simulated",
}


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def import_existing_results(
    run_dir: Path,
    results_source: Path | str,
    *,
    contract_source: Path | str | None = None,
    preregistration_source: Path | str | None = None,
    replace: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """导入已有结果（必需）与契约/预注册（可选），写入导入报告。"""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "imported_at": _utc_now(),
        "notes": str(notes or ""),
        "imported_files": [],
        "field_mapping": [],
        "missing_fields": [],
        "warnings": [],
        "result_summary": {},
    }

    rows = _load_results(results_source, report)
    if rows is None:
        report["warnings"].append("结果导入失败：04-results.json 未写入。")
        write_json(run_dir / IMPORT_REPORT_JSON, report)
        return report

    existing_path = run_dir / "04-results.json"
    if existing_path.exists() and not replace:
        report["warnings"].append(
            "run 目录已有 04-results.json；未写入新结果（replace=false）。如确需覆盖请显式 replace=true。"
        )
        report["result_summary"] = _summarize(rows)
        write_json(run_dir / IMPORT_REPORT_JSON, report)
        return report
    write_json(existing_path, rows)
    report["imported_files"].append(
        {
            "path": "04-results.json",
            "source": str(results_source),
            "source_sha256": _sha256_file(Path(results_source)) if isinstance(results_source, (str, Path)) else None,
            "action": "replaced" if existing_path.exists() else "created",
        }
    )
    report["field_mapping"] = _field_mapping(rows)
    report["missing_fields"] = _missing_fields(rows)
    report["result_summary"] = _summarize(rows)

    for key, source, target in (
        ("contract", contract_source, "03-idea-experiment-contract.json"),
        ("preregistration", preregistration_source, "03-preregistration.json"),
    ):
        if source is None:
            report["missing_fields"].append(
                f"{key}: 未提供；将按 unknown 处理，不自动补成已批准/已锁定。"
            )
            continue
        if isinstance(source, dict):
            payload = source
            source_desc = f"inline:{key}"
            source_sha = None
        elif isinstance(source, str) and source.strip().startswith("{"):
            try:
                payload = json.loads(source)
            except ValueError:
                payload = None
            source_desc = f"inline-json:{key}"
            source_sha = None
        else:
            payload = _load_json_file(Path(source))
            source_desc = str(source)
            source_sha = _sha256_file(Path(source))
        if payload is None:
            report["warnings"].append(f"{key} 导入失败：{source_desc} 不是可读 JSON。")
            continue
        write_json(run_dir / target, payload)
        report["imported_files"].append(
            {"path": target, "source": source_desc, "source_sha256": source_sha, "action": "created"}
        )

    integrity = assess_evidence_integrity(run_dir)
    report["evidence_assessment"] = {
        "llm_evidence_status": integrity.llm_evidence_status,
        "experiment_evidence_status": integrity.experiment_evidence_status,
        "research_outcome_note": "研究结论需在契约判据与统计比较完成后评估；导入本身不产生结论。",
        "next_step": (
            "导入完成：请核对 00-import-report 的缺失项，补齐后从 checkpoint 恢复执行分析/决策阶段。"
            if not report["missing_fields"]
            else "导入完成但存在缺失项：按 00-import-report 逐项补齐材料。"
        ),
    }
    write_json(run_dir / IMPORT_REPORT_JSON, report)
    return report


def _load_results(source: Path | str, report: dict[str, Any]) -> list[dict[str, Any]] | None:
    if isinstance(source, (str, Path)):
        payload = _load_json_file(Path(source))
        if payload is None:
            report["warnings"].append(f"结果文件不可读或不是 JSON：{source}")
            return None
    else:
        payload = source
    rows = payload if isinstance(payload, list) else (payload or {}).get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        report["warnings"].append("结果必须是非空数组（或含 results 数组的对象）。")
        return None
    cleaned: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            report["warnings"].append(f"第 {index} 行缺少 name 字段，已跳过。")
            continue
        cleaned.append(row)
    if not cleaned:
        report["warnings"].append("没有可用的结果行（全部缺少 name）。")
        return None
    return cleaned


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _field_mapping(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: list[dict[str, Any]] = []
    for row in rows[:50]:
        raw_status = str(row.get("status") or "").strip().lower()
        mapping.append(
            {
                "name": str(row.get("name")),
                "raw_status": raw_status,
                "execution_status": _EXECUTION_MAP.get(raw_status, "unknown（按 blocked+incomplete 处理）"),
                "usable_as_evidence": raw_status == "passed",
            }
        )
    return mapping


def _missing_fields(rows: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if any(not row.get("metrics") for row in rows):
        missing.append("metrics: 部分行缺少指标，证据将判 incomplete。")
    if any(not row.get("artifact_records") and row.get("returncode") is None for row in rows):
        missing.append("artifact_records/returncode: 部分行缺少来源绑定，证据将判 incomplete。")
    if any(not row.get("seed") for row in rows):
        missing.append("seed: 部分行缺少随机种子记录。")
    if any(not row.get("command") for row in rows):
        missing.append("command: 部分行缺少执行命令记录。")
    return missing


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {"total": len(rows), "status_counts": counts}
