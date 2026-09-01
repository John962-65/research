"""真实的 2D 采样运动规划器（纯标准库，无第三方依赖）。

把 research-agent 的实验环节从硬编码常数升级为真实算法：真碰撞检测、真采样、
种子可复现。比较的两个变体是真实的工程权衡，谁赢不预设：

  greedy       : 高 goal-bias + 大步长 —— 空旷场景快，密集场景容易撞墙失败
  conservative : 低 goal-bias + 小步长 —— 密集场景更稳，但迭代更多更慢

胜负随障碍密度可能翻转；本模块只负责跑出真实数字，不替结论站队。
参数（步长/bias/迭代上限/场景数/密度档）按先验一次性定死，不得为了"让结果更好看"事后调整。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Scene:
    width: float
    height: float
    obstacles: tuple[tuple[float, float, float], ...]  # (cx, cy, r)
    start: tuple[float, float]
    goal: tuple[float, float]


@dataclass(frozen=True)
class PlanResult:
    success: bool
    path_length: float
    iterations: int


# (goal_bias, step) —— 先验设定，不为结果调参。
VARIANTS: dict[str, tuple[float, float]] = {
    "greedy": (0.30, 1.0),
    "conservative": (0.05, 0.4),
}

DENSITIES: tuple[int, ...] = (4, 8, 12, 16)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def make_scene(seed: int, n_obstacles: int, width: float = 10.0, height: float = 10.0) -> Scene:
    rng = random.Random(seed)
    start = (0.5, 0.5)
    goal = (width - 0.5, height - 0.5)
    obstacles: list[tuple[float, float, float]] = []
    attempts = 0
    while len(obstacles) < n_obstacles and attempts < 4000:
        attempts += 1
        r = rng.uniform(0.5, 1.0)
        cx = rng.uniform(r, width - r)
        cy = rng.uniform(r, height - r)
        # 不要盖住起点/终点，否则该场景无解、对两个变体都不公平。
        if _dist((cx, cy), start) < r + 0.7 or _dist((cx, cy), goal) < r + 0.7:
            continue
        obstacles.append((cx, cy, r))
    return Scene(width, height, tuple(obstacles), start, goal)


def _point_collides(p: tuple[float, float], scene: Scene) -> bool:
    for cx, cy, r in scene.obstacles:
        if math.hypot(p[0] - cx, p[1] - cy) <= r:
            return True
    return False


def _seg_pt_dist(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg2
    t = max(0.0, min(1.0, t))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def _seg_collides(a: tuple[float, float], b: tuple[float, float], scene: Scene) -> bool:
    for cx, cy, r in scene.obstacles:
        if _seg_pt_dist(a, b, (cx, cy)) <= r:
            return True
    return False


def _steer(frm: tuple[float, float], to: tuple[float, float], step: float) -> tuple[float, float]:
    d = _dist(frm, to)
    if d <= step:
        return to
    return (frm[0] + (to[0] - frm[0]) / d * step, frm[1] + (to[1] - frm[1]) / d * step)


def rrt(scene: Scene, seed: int, goal_bias: float, step: float, max_iter: int = 1500) -> PlanResult:
    rng = random.Random(seed)
    nodes: list[tuple[float, float]] = [scene.start]
    parents: list[int] = [-1]
    for it in range(1, max_iter + 1):
        if rng.random() < goal_bias:
            sample = scene.goal
        else:
            sample = (rng.uniform(0.0, scene.width), rng.uniform(0.0, scene.height))
        # 最近节点（线性扫描，toy 规模足够）
        best_i = 0
        best_d = _dist(nodes[0], sample)
        for i in range(1, len(nodes)):
            d = _dist(nodes[i], sample)
            if d < best_d:
                best_d = d
                best_i = i
        new = _steer(nodes[best_i], sample, step)
        if _point_collides(new, scene) or _seg_collides(nodes[best_i], new, scene):
            continue
        nodes.append(new)
        parents.append(best_i)
        if _dist(new, scene.goal) <= step and not _seg_collides(new, scene.goal, scene):
            length = _dist(new, scene.goal)
            cur = len(nodes) - 1
            while parents[cur] != -1:
                length += _dist(nodes[cur], nodes[parents[cur]])
                cur = parents[cur]
            return PlanResult(True, length, it)
    return PlanResult(False, float("inf"), max_iter)


def plan(variant: str, scene: Scene, seed: int, max_iter: int = 1500) -> PlanResult:
    goal_bias, step = VARIANTS[variant]
    return rrt(scene, seed, goal_bias, step, max_iter)


def _scene_seed(base_seed: int, n_obstacles: int, k: int) -> int:
    return base_seed * 100003 + n_obstacles * 911 + k


def _plan_seed(base_seed: int, k: int) -> int:
    return base_seed * 7919 + k


def evaluate(variant: str, base_seed: int, n_obstacles: int, n_scenes: int = 30, max_iter: int = 1500) -> dict:
    """在一批随机场景上评估一个变体。场景与规划种子和变体无关，保证两变体见到相同场景（配对比较）。"""
    successes = 0
    total_iters = 0
    solved_lengths: list[float] = []
    solved_scene_ids: list[int] = []
    for k in range(n_scenes):
        scene = make_scene(_scene_seed(base_seed, n_obstacles, k), n_obstacles)
        res = plan(variant, scene, _plan_seed(base_seed, k), max_iter)
        total_iters += res.iterations
        if res.success:
            successes += 1
            solved_lengths.append(res.path_length)
            solved_scene_ids.append(k)
    return {
        "variant": variant,
        "n_obstacles": n_obstacles,
        "n_scenes": n_scenes,
        "successes": successes,
        "success_rate": successes / n_scenes,
        "mean_iterations": total_iters / n_scenes,
        "mean_path_length_solved": (sum(solved_lengths) / len(solved_lengths)) if solved_lengths else None,
        "solved_scene_ids": solved_scene_ids,
    }


def paired_path_length(base_seed: int, n_obstacles: int, mutual_ids: list[int], n_scenes: int = 30, max_iter: int = 1500) -> dict:
    """只在两个变体都解出的场景上，计算各自平均路径长度（公平的配对比较）。"""
    out: dict[str, float | None] = {}
    for variant in VARIANTS:
        lengths: list[float] = []
        for k in mutual_ids:
            scene = make_scene(_scene_seed(base_seed, n_obstacles, k), n_obstacles)
            res = plan(variant, scene, _plan_seed(base_seed, k), max_iter)
            if res.success:
                lengths.append(res.path_length)
        out[variant] = (sum(lengths) / len(lengths)) if lengths else None
    return out


def run_sweep(base_seed: int = 20260615, n_scenes: int = 30, max_iter: int = 1500) -> list[dict]:
    rows: list[dict] = []
    for n_obs in DENSITIES:
        per = {v: evaluate(v, base_seed, n_obs, n_scenes, max_iter) for v in VARIANTS}
        solved = {v: set(per[v]["solved_scene_ids"]) for v in VARIANTS}
        mutual = sorted(solved["greedy"] & solved["conservative"])
        paired = paired_path_length(base_seed, n_obs, mutual, n_scenes, max_iter)
        rows.append({"n_obstacles": n_obs, "per": per, "n_mutual": len(mutual), "paired_path_length": paired})
    return rows


if __name__ == "__main__":
    import json

    print(json.dumps(run_sweep(), ensure_ascii=False, indent=2))
