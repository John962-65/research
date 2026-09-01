"""publication 形态的标准规划器对比：OMPL RRT/RRTConnect/PRM/RRTstar 在同一批真实
KUKA iiwa 场景上（pybullet 验证碰撞），时间预算式查询 + Wilson 95% CI。

没有"候选"——都是标准验证规划器，如实报告各自权衡。
预注册（跑前定死）：密度3，15 场景，每查询 2.0s 预算，全局种子 20260616。
预测：RRTConnect 求解最快；RRTstar 路径最短但耗满预算；成功率排序未知。结果如何报如何。
"""
from __future__ import annotations

import math
import random

import ompl_arm_planner as O
from arm_planner import ArmWorld, make_obstacles

SEED = 20260616
N_SCENES = 15
DENSITY = 3
TIME_BUDGET = 2.0
PLANNERS = ["rrt", "rrtconnect", "prm", "rrtstar"]
Z = 1.96


def wilson(s: int, n: int, z: float = Z) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = s / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def main() -> None:
    O.set_global_seed(SEED)
    world = ArmWorld()
    home = (0.0,) * world.dof

    # 预生成可复现场景（障碍 + 合法 home/goal）；start 必须 free，否则跳过（对所有 planner 一致）
    scenes = []
    for k in range(N_SCENES):
        specs = make_obstacles(random.Random(SEED * 100003 + DENSITY * 911 + k), DENSITY)
        world.set_obstacles(specs)
        if not world.is_collision_free(home):
            continue
        goal = world.sample_free(random.Random(SEED * 7919 + k))
        if goal is None:
            continue
        scenes.append((specs, goal))

    stats = {p: {"succ": 0, "n": 0, "tsum": 0.0, "lengths": []} for p in PLANNERS}
    for specs, goal in scenes:
        for planner in PLANNERS:
            world.set_obstacles(specs)
            res = O.solve(world, planner, home, goal, TIME_BUDGET)
            st = stats[planner]
            st["n"] += 1
            st["tsum"] += res.solve_time
            if res.success:
                st["succ"] += 1
                st["lengths"].append(res.path_length)
    world.disconnect()

    print(f"预注册: 密度{DENSITY} {len(scenes)}场景(start-free) 每查询{TIME_BUDGET}s 全局种子{SEED}", flush=True)
    hdr = f"{'planner':>12} | {'成功/n':>7} | {'成功率':>7} | {'Wilson 95% CI':>16} | {'平均求解s':>9} | {'平均路径rad(解出)':>16}"
    print(hdr)
    print("-" * len(hdr))
    for planner in PLANNERS:
        st = stats[planner]
        lo, hi = wilson(st["succ"], st["n"])
        rate = st["succ"] / st["n"] if st["n"] else 0.0
        mt = st["tsum"] / st["n"] if st["n"] else 0.0
        ml = (sum(st["lengths"]) / len(st["lengths"])) if st["lengths"] else None
        mls = f"{ml:.3f}" if ml is not None else "  -  "
        print(f"{planner:>12} | {st['succ']:>3}/{st['n']:>3} | {rate*100:6.1f}% | "
              f"[{lo*100:4.1f},{hi*100:4.1f}]% | {mt:9.3f} | {mls:>16}")
    print("OMPL_COMPARE_DONE", flush=True)


if __name__ == "__main__":
    main()
