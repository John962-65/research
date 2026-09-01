from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research_agent.artifacts import write_json
from research_agent.config import ExecutionConfig
from research_agent.evidence_integrity import assess_evidence_integrity
from research_agent.experiments import run_experiments
from research_agent.models import ExperimentPlan

MANIFEST = Path("examples/rrt-2d-benchmark/manifest.json")


class RRTBenchmarkIntegrationTest(unittest.TestCase):
    """M1 闭环：真规划器经 benchmark adapter 产出真实（非 simulated）结果，并翻转 evidence_integrity。"""

    def test_benchmark_adapter_produces_real_nonsimulated_results(self) -> None:
        if not MANIFEST.exists():
            self.skipTest("manifest 在当前工作目录不可达；从仓库根运行该测试")
        plan = ExperimentPlan(
            idea_title="RRT 变体比较",
            objective="比较 greedy 与 conservative RRT 在等迭代预算下的表现。",
            variables=["goal_bias", "step"],
            metrics=["greedy_success_rate", "conservative_success_rate"],
            protocol=["程序生成 2D 障碍场景批", "等迭代预算"],
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
                # 真实子进程执行，绝不能是 simulated。
                self.assertEqual(result.status, "passed")
                self.assertNotEqual(result.status, "simulated")
                self.assertIn("greedy_success_rate", result.metrics)
                self.assertIn("conservative_mean_iterations", result.metrics)
                # 物理 sanity：路径长度必须 ≥ 起终点直线距离 ≈ 12.73（真实碰撞场景的下界）。
                if "greedy_path_length_mutual" in result.metrics:
                    self.assertGreater(result.metrics["greedy_path_length_mutual"], 12.0)

            write_json(run_dir / "04-results.json", results)
            integrity = assess_evidence_integrity(run_dir)
            # 实验已真实，但未接 LLM —— 诚实状态应为"部分真实"。
            self.assertTrue(integrity.real_experiment)
            self.assertFalse(integrity.real_llm)
            self.assertEqual(integrity.status, "partial_real_evidence")


if __name__ == "__main__":
    unittest.main()
