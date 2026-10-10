"""示例项目数据生成：模拟「多机械臂规划长尾」科研数据（公式化、可复现）。

场景设定（虚构示例，演示诊断闭环用）：
- paco（候选）与 baseline 两组，相同 200 个查询、相同种子；
- paco 总体更快（×0.85），但 3% 查询存在 2 倍长尾（均值优势仍在，尾部风险真实存在）；
- paco 组测试时 arm_count 系统性偏高（混杂因素，诊断应暴露）；
- 少量 timeout 行（诊断应报告而非忽略）。
"""
from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).parent


def base_time(q: int) -> float:
    return 1.0 + 0.1 * (q % 10)


def rows_for(group: str, scale: float, n: int = 200, arm_shift: int = 0, tail_ratio: float = 0.0, tail_multiplier: float = 1.0) -> list[dict]:
    n_tail = int(n * tail_ratio)
    tail_ids = set(range(n - n_tail, n))
    timeout_ids = {7, 23} if group == "paco" else {57}
    rows = []
    for q in range(n):
        t = base_time(q)
        if q in tail_ids:
            t *= tail_multiplier
        t *= scale
        status = "timeout" if q in timeout_ids else "success"
        rows.append(
            {
                "query_id": f"q{q:03d}",
                "comparison_group": group,
                "seed": 1000 + q,
                "repeat_index": 0,
                "status": status,
                "planning_time_s": round(t, 4),
                "success_rate": 0.0 if status == "timeout" else 0.97,
                "arm_count": 2 + (q % 5) + arm_shift,
                "scenario": "hard" if q % 3 == 0 else "easy",
            }
        )
    return rows


def main() -> None:
    out = HERE / "results.csv"
    rows = rows_for("baseline", 1.0) + rows_for("paco", 0.85, arm_shift=3, tail_ratio=0.03, tail_multiplier=2.0)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    manifest = HERE / "manifest.json"
    manifest.write_text(
        '{"benchmark": "demo", "metric_schema": {'
        '"planning_time_s": {"direction": "lower_is_better"},'
        '"success_rate": {"direction": "higher_is_better"}}}',
        encoding="utf-8",
    )
    print(f"已生成 {out}（{len(rows)} 行）与 {manifest}")


if __name__ == "__main__":
    main()
