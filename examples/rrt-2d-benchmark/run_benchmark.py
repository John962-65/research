"""Benchmark adapter runner：在固定密度的场景批上跑两个真实 RRT 变体，输出真实指标。

由 research-agent 的 benchmark adapter 以 cwd=experiments/ 调用，命令形如：
    python3 benchmark-adapters/<slug>/run_benchmark.py --metrics benchmark-adapters/<slug>/metrics.json
读取 RESEARCH_AGENT_SEED / RESEARCH_AGENT_REPEAT_INDEX 保证可复现。

输出的是真实算法跑出来的数字，不是占位常数。键名中性（greedy_*/conservative_*），
不预设谁是"候选"、谁更优——盲跑结论是 greedy 等迭代预算下弱占优、权衡不成立，
所以这里不把任一方包装成必胜的 candidate。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rrt_planner as P  # noqa: E402

DENSITY = 12
N_SCENES = 20


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--variant", choices=sorted(P.VARIANTS), default="")
    parser.add_argument("--max-iter", type=int, default=1500)
    args = parser.parse_args()

    seed_hex = os.environ.get("RESEARCH_AGENT_SEED", "0")
    repeat = int(os.environ.get("RESEARCH_AGENT_REPEAT_INDEX", "0"))
    try:
        base_seed = int(seed_hex, 16)
    except ValueError:
        base_seed = abs(hash(seed_hex))
    # repeat_index 改变场景批，保证重复实验之间不是同一批场景。
    base_seed = (base_seed % 1_000_000_007) + repeat * 101

    started = time.perf_counter()
    if args.variant:
        result = P.evaluate(args.variant, base_seed, DENSITY, N_SCENES, max(1, args.max_iter))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        metrics = {
            "n_obstacles": float(DENSITY),
            "n_scenes": float(N_SCENES),
            "success_rate": result["success_rate"],
            "mean_iterations": round(result["mean_iterations"], 3),
            "wall_time_ms": round(elapsed_ms, 2),
        }
        if result["mean_path_length_solved"] is not None:
            metrics["mean_path_length_solved"] = round(result["mean_path_length_solved"], 4)
        with open(args.metrics, "w", encoding="utf-8") as handle:
            json.dump(metrics, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(json.dumps({"wrote": args.metrics, "variant": args.variant, "metrics": metrics}, ensure_ascii=False))
        return

    per = {v: P.evaluate(v, base_seed, DENSITY, N_SCENES) for v in P.VARIANTS}
    solved = {v: set(per[v]["solved_scene_ids"]) for v in P.VARIANTS}
    mutual = sorted(solved["greedy"] & solved["conservative"])
    paired = P.paired_path_length(base_seed, DENSITY, mutual, N_SCENES)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    metrics = {
        "n_obstacles": float(DENSITY),
        "n_scenes": float(N_SCENES),
        "greedy_success_rate": per["greedy"]["success_rate"],
        "conservative_success_rate": per["conservative"]["success_rate"],
        "greedy_mean_iterations": round(per["greedy"]["mean_iterations"], 3),
        "conservative_mean_iterations": round(per["conservative"]["mean_iterations"], 3),
        "mutual_solved_scenes": float(len(mutual)),
        "wall_time_ms": round(elapsed_ms, 2),
    }
    if paired["greedy"] is not None:
        metrics["greedy_path_length_mutual"] = round(paired["greedy"], 4)
    if paired["conservative"] is not None:
        metrics["conservative_path_length_mutual"] = round(paired["conservative"], 4)

    with open(args.metrics, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"wrote": args.metrics, "metrics": metrics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
