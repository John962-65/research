from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research_agent.artifacts import write_json
from research_agent.config import ExecutionConfig
from research_agent.evidence_integrity import assess_evidence_integrity
from research_agent.experiments import run_experiments
from research_agent.models import ExperimentPlan

MANIFEST = Path("examples/rrt-2d-benchmark/manifest-arm.json")
_HAS_PYBULLET = importlib.util.find_spec("pybullet") is not None


class ArmBenchmarkIntegrationTest(unittest.TestCase):
    """M2 闭环：真实 7-DOF KUKA iiwa（pybullet 验证碰撞）经 benchmark adapter 产真实结果。"""

    def test_arm_benchmark_produces_real_nonsimulated_results(self) -> None:
        if not _HAS_PYBULLET:
            self.skipTest("pybullet 未安装")
        if not MANIFEST.exists():
            self.skipTest("manifest-arm.json 在当前工作目录不可达；从仓库根运行")
        plan = ExperimentPlan(
            idea_title="KUKA iiwa 7-DOF RRT 变体比较",
            objective="真实关节空间下比较两个 RRT 变体。",
            variables=["goal_bias", "step"],
            metrics=["greedy_success_rate", "conservative_success_rate"],
            protocol=["pybullet 验证碰撞", "等迭代预算"],
            commands=[],
            baseline="conservative RRT",
            evidence_keys=[],
        )
        cfg = ExecutionConfig(mode="benchmark", repeats=1, benchmark_manifest_paths=[str(MANIFEST)])
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            results = run_experiments(plan, cfg, run_dir)

            self.assertTrue(results)
            for result in results:
                self.assertEqual(result.status, "passed")
                self.assertNotEqual(result.status, "simulated")
                self.assertEqual(result.metrics.get("dof"), 7.0)
                self.assertIn("greedy_success_rate", result.metrics)
                self.assertIn("conservative_mean_iterations", result.metrics)
                # 关节空间路径长度应为正且物理合理（< 7-DOF 满量程上界）。
                for key in ("greedy_path_length_mutual_rad", "conservative_path_length_mutual_rad"):
                    if key in result.metrics:
                        self.assertGreater(result.metrics[key], 0.0)
                        self.assertLess(result.metrics[key], 50.0)

            write_json(run_dir / "04-results.json", results)
            integrity = assess_evidence_integrity(run_dir)
            self.assertTrue(integrity.real_experiment)
            self.assertFalse(integrity.real_llm)
            self.assertEqual(integrity.status, "partial_real_evidence")


if __name__ == "__main__":
    unittest.main()
