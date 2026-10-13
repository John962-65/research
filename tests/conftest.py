"""测试共用：确定性合成数据生成器（不用随机数，全部公式化，便于断言精确值）。"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def require_sandbox():
    """实际探测命名空间能力；不可用明确跳过，不能用执行失败冒充安全测试通过。"""
    import os
    from research_copilot.evaluation.sandbox import check_bwrap_available
    if not check_bwrap_available():
        reason = "bwrap 不存在或命名空间实际启动失败：未验证沙箱集成"
        if os.environ.get("RC_REQUIRE_SANDBOX") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
    return path


def latency_rows(
    group: str,
    n_queries: int = 120,
    scale: float = 1.0,
    tail_ratio: float = 0.05,
    tail_multiplier: float = 25.0,
    timeout_ids: set[int] | None = None,
    repeats: int = 1,
    scenario_fn=None,
    seed_offset: int = 0,
) -> list[dict[str, Any]]:
    """公式化规划耗时数据：base = 1.0 + 0.1*(q % 10)；尾部查询放大 tail_multiplier 倍。

    两组使用相同 query_id/seed/repeat_index，天然可配对。
    """
    timeout_ids = timeout_ids or set()
    n_tail = int(n_queries * tail_ratio)
    tail_ids = set(range(n_queries - n_tail, n_queries))
    rows = []
    for q in range(n_queries):
        base = 1.0 + 0.1 * (q % 10)
        if q in tail_ids:
            base *= tail_multiplier
        for repeat in range(repeats):
            status = "timeout" if q in timeout_ids else "success"
            row = {
                "query_id": f"q{q:03d}",
                "comparison_group": group,
                "seed": 1000 + q + seed_offset,
                "repeat_index": repeat,
                "status": status,
                "planning_time_s": round(base * scale, 4),
                "success_rate": 0.97 if status == "success" else 0.0,
                "scenario": scenario_fn(q) if scenario_fn else ("easy" if q % 3 else "hard"),
                "arm_count": 2 + (q % 5),
            }
            rows.append(row)
    return rows


def manifest(path: Path, metric_schema: dict[str, str]) -> Path:
    payload = {
        "benchmark": "synthetic",
        "metric_schema": {name: {"direction": direction} for name, direction in metric_schema.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
