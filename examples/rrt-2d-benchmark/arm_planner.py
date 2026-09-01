"""真实 7-DOF 机械臂关节空间运动规划（pybullet 验证碰撞，headless）。

把实验从 2D toy 抬到真实机械臂 + 经过验证的 3D 碰撞检测：
- KUKA iiwa URDF（pybullet_data 自带），真实关节限位与几何
- 状态有效性 = 关节限位内 且 与障碍无碰撞（pybullet getClosestPoints，Bullet 引擎验证）
- 边有效性 = 关节空间线性插值离散化后逐点查碰撞
- RRT，两个诚实变体（greedy/conservative），等迭代预算，谁优不预设

诚实边界：碰撞与机器人模型为真且经过验证，但规划器仍是自写；真正 publication 级
还需换 OMPL 验证规划器 + 标准 benchmark 问题。自碰撞未强制（见 is_collision_free 注释）。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pybullet as p
import pybullet_data

# (goal_bias, step_rad) —— 先验设定，不为结果调参。step 是关节空间单次扩展上限（弧度）。
VARIANTS: dict[str, tuple[float, float]] = {
    "greedy": (0.30, 0.60),
    "conservative": (0.05, 0.25),
}

DENSITIES: tuple[int, ...] = (2, 3, 4)  # 工作空间内 box 障碍数
_EDGE_RES = 0.12  # 边插值分辨率（弧度），每段不超过该角度
_SAFETY = 0.01    # 碰撞安全余量（米）


@dataclass(frozen=True)
class PlanResult:
    success: bool
    path_length: float  # 关节空间 L2 路径长度
    iterations: int


class ArmWorld:
    """持有一个 headless pybullet 连接、KUKA iiwa 与一组可替换障碍。"""

    def __init__(self) -> None:
        self.cid = p.connect(p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=self.cid)
        self.robot = p.loadURDF("kuka_iiwa/model.urdf", useFixedBase=True, physicsClientId=self.cid)
        self.joints: list[int] = []
        self.lower: list[float] = []
        self.upper: list[float] = []
        for j in range(p.getNumJoints(self.robot, physicsClientId=self.cid)):
            info = p.getJointInfo(self.robot, j, physicsClientId=self.cid)
            if info[2] == p.JOINT_REVOLUTE:
                lo, hi = info[8], info[9]
                if hi <= lo:  # 连续关节，限到对称范围
                    lo, hi = -2.96, 2.96
                self.joints.append(j)
                self.lower.append(lo)
                self.upper.append(hi)
        self.dof = len(self.joints)
        self._obstacles: list[int] = []

    def set_obstacles(self, specs: list[tuple[tuple[float, float, float], tuple[float, float, float]]]) -> None:
        for body in self._obstacles:
            p.removeBody(body, physicsClientId=self.cid)
        self._obstacles = []
        for half_extents, position in specs:
            shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=list(half_extents), physicsClientId=self.cid)
            body = p.createMultiBody(baseMass=0, baseCollisionShapeIndex=shape, basePosition=list(position), physicsClientId=self.cid)
            self._obstacles.append(body)

    def _set_config(self, config: tuple[float, ...]) -> None:
        for joint, angle in zip(self.joints, config):
            p.resetJointState(self.robot, joint, angle, physicsClientId=self.cid)

    def in_limits(self, config: tuple[float, ...]) -> bool:
        return all(lo <= a <= hi for a, lo, hi in zip(config, self.lower, self.upper))

    def is_collision_free(self, config: tuple[float, ...]) -> bool:
        """关节限位内且机器人各连杆与所有障碍无接触/穿透。

        用 getClosestPoints(robot, obstacle, distance=_SAFETY)：返回非空即在安全余量内有接触。
        注意：只检机器人-障碍碰撞，未强制自碰撞（KUKA iiwa 常规范围内自碰撞少见；这是已记录的局限）。
        """
        if not self.in_limits(config):
            return False
        self._set_config(config)
        for obstacle in self._obstacles:
            pts = p.getClosestPoints(self.robot, obstacle, distance=_SAFETY, physicsClientId=self.cid)
            if pts:
                return False
        return True

    def edge_collision_free(self, a: tuple[float, ...], b: tuple[float, ...]) -> bool:
        dist = _joint_dist(a, b)
        steps = max(1, int(math.ceil(dist / _EDGE_RES)))
        for i in range(1, steps + 1):
            t = i / steps
            mid = tuple(ai + (bi - ai) * t for ai, bi in zip(a, b))
            if not self.is_collision_free(mid):
                return False
        return True

    def sample(self, rng: random.Random) -> tuple[float, ...]:
        return tuple(rng.uniform(lo, hi) for lo, hi in zip(self.lower, self.upper))

    def sample_free(self, rng: random.Random, max_tries: int = 200) -> tuple[float, ...] | None:
        for _ in range(max_tries):
            c = self.sample(rng)
            if self.is_collision_free(c):
                return c
        return None

    def disconnect(self) -> None:
        p.disconnect(self.cid)


def _joint_dist(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def _steer(frm: tuple[float, ...], to: tuple[float, ...], step: float) -> tuple[float, ...]:
    d = _joint_dist(frm, to)
    if d <= step:
        return to
    return tuple(fi + (ti - fi) / d * step for fi, ti in zip(frm, to))


def rrt(world: ArmWorld, start: tuple[float, ...], goal: tuple[float, ...], seed: int,
        goal_bias: float, step: float, max_iter: int = 800) -> PlanResult:
    rng = random.Random(seed)
    nodes = [start]
    parents = [-1]
    for it in range(1, max_iter + 1):
        sample = goal if rng.random() < goal_bias else world.sample(rng)
        best_i = 0
        best_d = _joint_dist(nodes[0], sample)
        for i in range(1, len(nodes)):
            d = _joint_dist(nodes[i], sample)
            if d < best_d:
                best_d, best_i = d, i
        new = _steer(nodes[best_i], sample, step)
        if not world.is_collision_free(new) or not world.edge_collision_free(nodes[best_i], new):
            continue
        nodes.append(new)
        parents.append(best_i)
        if _joint_dist(new, goal) <= step and world.edge_collision_free(new, goal):
            length = _joint_dist(new, goal)
            cur = len(nodes) - 1
            while parents[cur] != -1:
                length += _joint_dist(nodes[cur], nodes[parents[cur]])
                cur = parents[cur]
            return PlanResult(True, length, it)
    return PlanResult(False, float("inf"), max_iter)


def make_obstacles(rng: random.Random, n: int) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """在 KUKA iiwa 工作空间内随机放 n 个 box 障碍（种子可复现）。"""
    specs = []
    for _ in range(n):
        half = (rng.uniform(0.05, 0.12), rng.uniform(0.05, 0.12), rng.uniform(0.05, 0.15))
        ang = rng.uniform(0, 2 * math.pi)
        radius = rng.uniform(0.35, 0.62)
        pos = (radius * math.cos(ang), radius * math.sin(ang), rng.uniform(0.35, 0.85))
        specs.append((half, pos))
    return specs


def plan_one(world: ArmWorld, variant: str, scene_seed: int, plan_seed: int, n_obstacles: int,
             max_iter: int = 800) -> PlanResult | None:
    """构建一个场景（障碍+合法起终点）并用一个变体规划。场景与变体无关，保证配对比较。"""
    srng = random.Random(scene_seed)
    world.set_obstacles(make_obstacles(srng, n_obstacles))
    start = (0.0,) * world.dof
    if not world.is_collision_free(start):
        return None  # 起点被障碍占据，跳过该场景（对两变体都跳过）
    goal = world.sample_free(srng)
    if goal is None:
        return None
    goal_bias, step = VARIANTS[variant]
    return rrt(world, start, goal, plan_seed, goal_bias, step, max_iter)


def evaluate(world: ArmWorld, variant: str, base_seed: int, n_obstacles: int,
             n_scenes: int = 10, max_iter: int = 800) -> dict:
    successes = 0
    attempted = 0
    total_iters = 0
    solved_lengths: list[float] = []
    solved_ids: list[int] = []
    for k in range(n_scenes):
        res = plan_one(world, variant, base_seed * 100003 + n_obstacles * 911 + k,
                       base_seed * 7919 + k, n_obstacles, max_iter)
        if res is None:
            continue
        attempted += 1
        total_iters += res.iterations
        if res.success:
            successes += 1
            solved_lengths.append(res.path_length)
            solved_ids.append(k)
    return {
        "variant": variant,
        "n_obstacles": n_obstacles,
        "attempted": attempted,
        "successes": successes,
        "success_rate": (successes / attempted) if attempted else 0.0,
        "mean_iterations": (total_iters / attempted) if attempted else 0.0,
        "mean_path_length_solved": (sum(solved_lengths) / len(solved_lengths)) if solved_lengths else None,
        "solved_scene_ids": solved_ids,
    }


def selftest() -> None:
    """验证碰撞检测器真的有效：已知自由判自由、已知碰撞判碰撞。不通过就抛错。"""
    world = ArmWorld()
    try:
        world.set_obstacles([])
        home = (0.0,) * world.dof
        assert world.is_collision_free(home), "无障碍时 home 应自由"
        # 在 home 位形下，把一个大 box 直接罩在机器人上半身（z≈0.4 处，靠近 base 轴线）→ 必碰
        world.set_obstacles([((0.25, 0.25, 0.25), (0.0, 0.0, 0.4))])
        assert not world.is_collision_free(home), "大 box 罩住机器人时 home 应判碰撞"
        # 障碍挪到远处（2m 外）→ 又自由
        world.set_obstacles([((0.1, 0.1, 0.1), (2.0, 2.0, 0.5))])
        assert world.is_collision_free(home), "远处障碍时 home 应自由"
        print("collision-checker selftest PASSED")
    finally:
        world.disconnect()


if __name__ == "__main__":
    selftest()
