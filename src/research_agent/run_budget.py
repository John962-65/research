"""Run budget bounds (T07 / A16).

冻结最大尝试次数与修订轮次，入口与恢复都检查持久化计数，恢复不能绕过
上限；耗尽时停止并保留已有证据。单轮流水线本身无自动循环，本模块约束
的是 repair-resume、实验重跑与论文修订这些可重复入口。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import read_json, safe_int as _safe_int, utc_now as _utc_now, write_json


RUN_BUDGET_JSON = "04-run-budget.json"

# 冻结的默认上限（decision-contract §1.4：超出 → stop，保留证据）。
DEFAULT_LIMITS = {
    "experiment_runs": 3,
    "paper_revisions": 3,
    "repair_resumes": 3,
}


class RunBudgetExhausted(RuntimeError):
    """预算耗尽：运行应停止并保留已有证据；恢复不会绕过上限。"""


def _budget_path(run_dir: Path) -> Path:
    return Path(run_dir) / RUN_BUDGET_JSON


def load_budget(run_dir: Path) -> dict[str, Any]:
    try:
        data = read_json(_budget_path(run_dir))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    consumed = data.get("consumed") if isinstance(data.get("consumed"), dict) else {}
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
    merged_limits = {**DEFAULT_LIMITS, **{key: _safe_int(value) for key, value in limits.items() if _safe_int(value) > 0}}
    return {
        "schema_version": 1,
        "limits": merged_limits,
        "consumed": {key: _safe_int(consumed.get(key)) for key in merged_limits},
    }


def ensure_budget(run_dir: Path, kind: str) -> dict[str, Any]:
    """入口检查：超过上限抛 RunBudgetExhausted（A16，恢复同样被拦）。"""
    budget = load_budget(run_dir)
    limit = int(budget["limits"].get(kind, 0))
    consumed = int(budget["consumed"].get(kind, 0))
    if consumed >= limit:
        raise RunBudgetExhausted(
            f"{kind} 预算已耗尽（{consumed}/{limit}）；运行停止，已有证据保留在 run 目录中。"
            "如确需继续，请人工修改 04-run-budget.json 的 limits 并记录理由。"
        )
    return budget


def record_execution(run_dir: Path, kind: str, *, note: str = "") -> None:
    """记录一次实际执行（不含 checkpoint 复用）。"""
    budget = load_budget(run_dir)
    consumed = budget["consumed"]
    consumed[kind] = int(consumed.get(kind, 0)) + 1
    payload = {
        **budget,
        "last_updated_at": _utc_now(),
    }
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    events.append({"kind": kind, "consumed_after": consumed[kind], "at": payload["last_updated_at"], "note": str(note)[:200]})
    payload["events"] = events[-50:]
    write_json(_budget_path(run_dir), payload)


def budget_summary(run_dir: Path) -> dict[str, Any]:
    budget = load_budget(run_dir)
    return {
        kind: {"consumed": int(budget["consumed"].get(kind, 0)), "limit": int(limit)}
        for kind, limit in budget["limits"].items()
    }
