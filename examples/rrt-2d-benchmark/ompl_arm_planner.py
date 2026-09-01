"""OMPL 验证规划器 + pybullet 验证碰撞 + 真实 KUKA iiwa：publication 级的规划器侧升级。

把自写 RRT 换成 OMPL 的标准验证规划器（RRT/RRTConnect/PRM/RRTstar）：
- 状态空间 = 7 维关节空间（RealVectorStateSpace，bounds=真实关节限位）
- 状态有效性 = pybullet ArmWorld.is_collision_free（已独立自检）
- 运动有效性 = OMPL 的 DiscreteMotionValidator（验证过的标准件），分辨率按关节空间尺度设
- 时间预算式查询（OMPL 标准方法学）

诚实边界：planner 与碰撞现在都是验证过的标准件；剩余 gap 仅是"场景仍为程序生成，
非标准 benchmark 套件（如 MotionBenchMaker / OMPL.app 基准）"。
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ompl import base as ob
from ompl import geometric as og

try:
    from ompl import util as ou
except Exception:  # pragma: no cover
    ou = None

from arm_planner import ArmWorld, make_obstacles

PLANNERS = {
    "rrt": og.RRT,
    "rrtconnect": og.RRTConnect,
    "prm": og.PRM,
    "rrtstar": og.RRTstar,
}


@dataclass(frozen=True)
class OmplResult:
    success: bool
    path_length: float  # 关节空间 L2，OMPL 原始解（不做 simplify，避免 shortcut 必然变短的套套逻辑）
    solve_time: float


def set_global_seed(seed: int) -> None:
    """在任何 OMPL 采样发生前设一次全局 RNG 种子（OMPL 要求 setSeed 必须最先调用，之后再设无效）。

    因此 OMPL 内部采样在"整个进程"层面可复现；planner 的逐次随机性靠多场景平均处理。
    场景生成（pybullet + random.Random）独立可复现。
    """
    if ou is not None:
        try:
            ou.RNG.setSeed(int(seed) & 0x7FFFFFFF)
        except Exception:
            pass


def _max_extent(world: ArmWorld) -> float:
    return math.sqrt(sum((hi - lo) ** 2 for lo, hi in zip(world.lower, world.upper)))


class _PyBulletValidity(ob.StateValidityChecker):
    """OMPL 状态有效性回调到 pybullet（ArmWorld，已自检）的碰撞检测。"""

    def __init__(self, si, world: ArmWorld) -> None:
        super().__init__(si)
        self._world = world
        self._dof = world.dof

    def isValid(self, state) -> bool:  # noqa: N802 (OMPL 接口命名)
        return self._world.is_collision_free(tuple(state[i] for i in range(self._dof)))


def _make_setup(world: ArmWorld):
    """返回 (SimpleSetup, checker)。checker 必须被调用方持有引用，否则会被 GC（director 对象）。"""
    space = ob.RealVectorStateSpace(world.dof)
    bounds = ob.RealVectorBounds(world.dof)
    for i in range(world.dof):
        bounds.setLow(i, world.lower[i])
        bounds.setHigh(i, world.upper[i])
    space.setBounds(bounds)
    ss = og.SimpleSetup(space)
    checker = _PyBulletValidity(ss.getSpaceInformation(), world)
    ss.setStateValidityChecker(checker)
    # 运动有效性离散分辨率 ≈ 0.12 rad（与自写 RRT 的 _EDGE_RES 同量级），换算成空间最大跨度的比例。
    ss.getSpaceInformation().setStateValidityCheckingResolution(0.12 / _max_extent(world))
    return ss, checker


def _to_state(space, cfg):
    state = space.allocState()
    for i, a in enumerate(cfg):
        state[i] = a
    return state


def solve(world: ArmWorld, planner_name: str, start_cfg, goal_cfg, time_budget: float = 2.0, seed: int = 0) -> OmplResult:
    ss, _checker = _make_setup(world)  # _checker 必须保活
    space = ss.getStateSpace()
    ss.setStartAndGoalStates(_to_state(space, start_cfg), _to_state(space, goal_cfg))
    planner = PLANNERS[planner_name](ss.getSpaceInformation())
    ss.setPlanner(planner)
    t0 = time.perf_counter()
    ss.solve(time_budget)
    dt = time.perf_counter() - t0
    if ss.haveExactSolutionPath():
        path = ss.getSolutionPath()
        return OmplResult(True, path.length(), dt)
    return OmplResult(False, float("inf"), dt)


def _path_states(world: ArmWorld, planner_name: str, start_cfg, goal_cfg, time_budget: float, seed: int):
    """返回求解出的稠密路径状态列表（用于独立复核解是否真无碰撞）。"""
    ss, _checker = _make_setup(world)  # _checker 必须保活
    space = ss.getStateSpace()
    ss.setStartAndGoalStates(_to_state(space, start_cfg), _to_state(space, goal_cfg))
    planner = PLANNERS[planner_name](ss.getSpaceInformation())
    ss.setPlanner(planner)
    ss.solve(time_budget)
    if not ss.haveExactSolutionPath():
        return None
    path = ss.getSolutionPath()
    path.interpolate(200)
    return [tuple(path.getState(i)[j] for j in range(world.dof)) for i in range(path.getStateCount())]


def selftest() -> None:
    """这一层的反造假验证：OMPL 必须真的在用 pybullet 碰撞，且不伪造成功。"""
    world = ArmWorld()
    try:
        # 1) 状态有效性确实回调 pybullet：大 box 罩住 home → 该状态无效
        world.set_obstacles([((0.25, 0.25, 0.25), (0.0, 0.0, 0.4))])
        home = (0.0,) * world.dof
        assert not world.is_collision_free(home), "前提：home 应被大 box 判碰撞"

        # 2) 无障碍下 OMPL 能解出，且解路径独立复核逐点无碰撞
        world.set_obstacles([((0.1, 0.1, 0.1), (2.0, 2.0, 0.5))])  # 远处障碍
        goal = world.sample_free(__import__("random").Random(1))
        res = solve(world, "rrtconnect", home, goal, time_budget=2.0, seed=1)
        assert res.success and res.path_length > 0, "无障碍问题 RRTConnect 应解出"
        states = _path_states(world, "rrtconnect", home, goal, 2.0, 1)
        assert states is not None
        bad = sum(1 for s in states if not world.is_collision_free(s))
        assert bad == 0, f"OMPL 解路径必须逐点无碰撞，发现 {bad} 个碰撞点"

        # 3) 不伪造成功：goal 设在障碍内 → 必失败
        import random as _r
        world.set_obstacles([((0.2, 0.2, 0.2), (0.0, 0.0, 0.4))])
        rng = _r.Random(2)
        bad_goal = None
        for _ in range(500):
            c = world.sample(rng)
            if not world.is_collision_free(c):
                bad_goal = c
                break
        assert bad_goal is not None, "应能找到一个碰撞构型作为非法 goal"
        res_bad = solve(world, "rrtconnect", home, bad_goal, time_budget=1.0, seed=2)
        assert not res_bad.success, "goal 在障碍内时不应报成功"

        print("ompl-layer selftest PASSED (OMPL 确实在用 pybullet 碰撞，且解路径无碰撞、不伪造成功)")
    finally:
        world.disconnect()


if __name__ == "__main__":
    selftest()
