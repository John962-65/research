from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.benchmark_plan import BENCHMARK_PLAN_JSON, build_benchmark_plan, render_benchmark_plan_markdown, write_benchmark_plan_artifacts
from research_agent.experiments import plan_experiment
from research_agent.models import ResearchIdea
from research_agent.research_plan import build_research_plan


class BenchmarkPlanTest(unittest.TestCase):
    def test_robotics_benchmark_plan_recommends_real_planning_benchmarks(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        experiment_plan = plan_experiment(_idea(), research_plan=research_plan)

        plan = build_benchmark_plan(research_plan, experiment_plan)
        rendered = render_benchmark_plan_markdown(plan)

        self.assertEqual(plan.domain, "robotics_motion_planning")
        self.assertTrue(plan.candidates)
        self.assertIn("OMPL", " ".join(item.name for item in plan.candidates))
        self.assertTrue(plan.required_actions)
        self.assertIn("Benchmark 接入计划", rendered)
        self.assertIn("MoveIt", rendered)

    def test_benchmark_plan_artifacts_are_written(self) -> None:
        research_plan = build_research_plan("科研 agent")
        experiment_plan = plan_experiment(_idea(), research_plan=research_plan)
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            plan = write_benchmark_plan_artifacts(research_plan, experiment_plan, out)
            data = json.loads((out / BENCHMARK_PLAN_JSON).read_text(encoding="utf-8"))

            self.assertEqual(data["topic"], research_plan.topic)
            self.assertEqual(data["selected_names"], plan.selected_names)
            self.assertTrue((out / "03-benchmark-plan.md").exists())


def _idea() -> ResearchIdea:
    return ResearchIdea(
        title="真实 benchmark 接入",
        hypothesis="用真实 benchmark 替换模拟器可以提升实验可信度。",
        mechanism="选择领域公开任务集并固定数据/任务划分。",
        expected_contribution="形成可复现的真实实验入口。",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=["success_rate", "runtime_cost"],
        baseline="RRT*",
    )


if __name__ == "__main__":
    unittest.main()
