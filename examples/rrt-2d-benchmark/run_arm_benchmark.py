"""Benchmark adapter runner：真实 7-DOF KUKA iiwa 关节空间规划（pybullet 验证碰撞）。

由 research-agent 的 benchmark adapter 以 cwd=experiments/ 调用：
    python3 benchmark-adapters/<slug>/run_arm_benchmark.py --metrics benchmark-adapters/<slug>/metrics.json
读取 RESEARCH_AGENT_SEED / RESEARCH_AGENT_REPEAT_INDEX 保证可复现。

输出真实算法跑出来的数字（中性键名 greedy_*/conservative_*，不预设谁胜）。
为了 pipeline 集成速度，单次只跑一个适中批量（密度3、8场景）；定量定论见 power_study.py
（n=40 + Wilson CI + Fisher：成功率无显著差异，greedy 约 2× 更省迭代）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arm_planner as A  # noqa: E402

DENSITY = 3
N_SCENES = 8
MAX_ITER = 800


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    args = parser.parse_args()

    seed_hex = os.environ.get("RESEARCH_AGENT_SEED", "0")
    repeat = int(os.environ.get("RESEARCH_AGENT_REPEAT_INDEX", "0"))
    try:
        base_seed = int(seed_hex, 16)
    except ValueError:
        base_seed = abs(hash(seed_hex))
    base_seed = (base_seed % 1_000_000_007) + repeat * 101

    started = time.perf_counter()
    world = A.ArmWorld()
    try:
        dof = world.dof
        per = {v: A.evaluate(world, v, base_seed, DENSITY, N_SCENES, MAX_ITER) for v in A.VARIANTS}
        solved = {v: set(per[v]["solved_scene_ids"]) for v in A.VARIANTS}
        mutual = sorted(solved["greedy"] & solved["conservative"])
        paired: dict[str, float | None] = {}
        for v in A.VARIANTS:
            lengths = []
            for k in mutual:
                r = A.plan_one(world, v, base_seed * 100003 + DENSITY * 911 + k, base_seed * 7919 + k, DENSITY, MAX_ITER)
                if r and r.success:
                    lengths.append(r.path_length)
            paired[v] = (sum(lengths) / len(lengths)) if lengths else None
    finally:
        world.disconnect()
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    g, c = per["greedy"], per["conservative"]
    metrics = {
        "dof": float(dof),
        "n_obstacles": float(DENSITY),
        "n_scenes": float(N_SCENES),
        "greedy_attempted": float(g["attempted"]),
        "conservative_attempted": float(c["attempted"]),
        "greedy_success_rate": g["success_rate"],
        "conservative_success_rate": c["success_rate"],
        "greedy_mean_iterations": round(g["mean_iterations"], 3),
        "conservative_mean_iterations": round(c["mean_iterations"], 3),
        "mutual_solved_scenes": float(len(mutual)),
        "wall_time_ms": round(elapsed_ms, 2),
    }
    if paired["greedy"] is not None:
        metrics["greedy_path_length_mutual_rad"] = round(paired["greedy"], 4)
    if paired["conservative"] is not None:
        metrics["conservative_path_length_mutual_rad"] = round(paired["conservative"], 4)

    with open(args.metrics, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"wrote": args.metrics, "metrics": metrics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
