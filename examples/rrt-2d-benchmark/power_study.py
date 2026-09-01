"""加大样本回答"密集场景是否更偏好 conservative"——Wilson 95% CI + Fisher 精确检验。

预注册（跑前定死）：密度 3/4/5，每档 40 场景，max_iter=800，base_seed=20260616。
预测：若 conservative 真更鲁棒，其成功率 CI 应高于 greedy 且差距随密度拉大；
零假设：CI 重叠、Fisher p>0.05、无显著差异。结果如何报如何。
"""
from __future__ import annotations

import math
import sys
import time

import arm_planner as A

BASE_SEED = 20260616
N_SCENES = 40
MAX_ITER = 800
DENSITIES = (3, 4, 5)
Z = 1.96  # 95%


def wilson_ci(successes: int, n: int, z: float = Z) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def _hypergeom_p(a: int, r1: int, r2: int, c1: int) -> float:
    # P(观察到左上角=a | 固定边际)，超几何分布
    return math.comb(r1, a) * math.comb(r2, c1 - a) / math.comb(r1 + r2, c1)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    # 2x2 表 [[a,b],[c,d]]；双侧 p = 所有同边际表中概率 <= 观察表概率者之和
    r1, r2 = a + b, c + d
    c1 = a + c
    n = r1 + r2
    p_obs = _hypergeom_p(a, r1, r2, c1)
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    total = 0.0
    for x in range(lo, hi + 1):
        px = _hypergeom_p(x, r1, r2, c1)
        if px <= p_obs * (1 + 1e-9):
            total += px
    return min(1.0, total)


def main() -> None:
    print(f"预注册: 密度{DENSITIES} 每档{N_SCENES}场景 max_iter={MAX_ITER} base_seed={BASE_SEED}", flush=True)
    hdr = f"{'密度':>4} | {'变体':>12} | {'成功/尝试':>9} | {'成功率':>7} | {'Wilson 95% CI':>18} | {'平均迭代':>9} | {'Fisher p(差异)':>13}"
    print(hdr, flush=True)
    print("-" * len(hdr), flush=True)
    world = A.ArmWorld()
    try:
        for n_obs in DENSITIES:
            t0 = time.perf_counter()
            res = {v: A.evaluate(world, v, BASE_SEED, n_obs, N_SCENES, MAX_ITER) for v in A.VARIANTS}
            g, c = res["greedy"], res["conservative"]
            # Fisher 在两变体都尝试的公共场景数上比较成功计数（用各自 attempted 的成功/失败）
            p_fisher = fisher_exact_two_sided(
                g["successes"], g["attempted"] - g["successes"],
                c["successes"], c["attempted"] - c["successes"],
            )
            for v in ("greedy", "conservative"):
                e = res[v]
                lo, hi = wilson_ci(e["successes"], e["attempted"])
                ci = f"[{lo*100:4.1f}, {hi*100:4.1f}]%"
                pcell = f"{p_fisher:.3f}" if v == "greedy" else ""
                print(f"{n_obs:>4} | {v:>12} | {e['successes']:>4}/{e['attempted']:>3} | "
                      f"{e['success_rate']*100:6.1f}% | {ci:>18} | {e['mean_iterations']:9.1f} | {pcell:>13}", flush=True)
            print(f"     (密度{n_obs} 用时 {time.perf_counter()-t0:.1f}s)", flush=True)
            print("-" * len(hdr), flush=True)
    finally:
        world.disconnect()
    print("POWER_STUDY_DONE", flush=True)


if __name__ == "__main__":
    main()
