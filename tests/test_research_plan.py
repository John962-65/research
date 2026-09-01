from __future__ import annotations

import unittest

from research_agent.experiments import plan_experiment
from research_agent.models import ResearchIdea
from research_agent.research_plan import build_research_plan, render_research_plan_markdown


class ResearchPlanTest(unittest.TestCase):
    def test_robotics_topic_gets_motion_planning_profile(self) -> None:
        plan = build_research_plan("机械臂路径规划")
        rendered = render_research_plan_markdown(plan)

        self.assertEqual(plan.domain, "robotics_motion_planning")
        self.assertTrue(any("RRT" in item for item in plan.baselines))
        self.assertIn("planning_success_rate", plan.metrics)
        self.assertIn("robot manipulator", " ".join(plan.search_queries))
        self.assertIn("Benchmark", rendered)

    def test_bearing_topic_gets_fault_diagnosis_profile(self) -> None:
        plan = build_research_plan("轴承故障诊断")

        self.assertEqual(plan.domain, "bearing_fault_diagnosis")
        self.assertTrue(any("CWRU" in item for item in plan.benchmarks))
        self.assertIn("macro_f1", plan.metrics)

    def test_prior_lessons_are_visible_in_rule_plan_constraints(self) -> None:
        plan = build_research_plan("机械臂路径规划", prior_lessons="- [warn] literature_repair: 补充高相关 DOI seed papers。")

        self.assertTrue(any("历史经验约束" in item and "seed papers" in item for item in plan.constraints))
        self.assertTrue(any("00-prior-run-lessons" in item for item in plan.success_criteria))

    def test_open_source_lessons_are_visible_in_rule_plan_constraints(self) -> None:
        plan = build_research_plan("科研 agent", prior_lessons="- [required] sandbox_generated_code: 自动实验命令必须经过 allowlist。")

        self.assertTrue(any("sandbox_generated_code" in item for item in plan.constraints))
        self.assertTrue(any("历史 run 风险" in item for item in plan.risks))

    def test_prior_run_library_is_visible_in_rule_plan_constraints(self) -> None:
        plan = build_research_plan(
            "机械臂路径规划",
            prior_lessons="历史成果库参考：\n- [ready_reference] robot-run: OMPL benchmark RRT* baseline；artifact=robot-run/06-paper.md",
        )

        self.assertTrue(any("robot-run" in item or "OMPL benchmark" in item for item in plan.constraints))
        self.assertTrue(any("00-prior-run-lessons" in item for item in plan.success_criteria))

    def test_human_brief_is_visible_in_rule_plan_constraints(self) -> None:
        plan = build_research_plan(
            "机械臂路径规划",
            prior_lessons="\n".join(
                [
                    "Human brief constraints:",
                    "- constraint: 必须比较 RRT* 和 CHOMP。",
                    "- resource: 只允许 smoke-first 运行。",
                ]
            ),
        )

        self.assertTrue(any("必须比较 RRT*" in item for item in plan.constraints))
        self.assertTrue(any("smoke-first" in item for item in plan.constraints))

    def test_experiment_plan_uses_domain_baseline_when_idea_is_generic(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        idea = ResearchIdea(
            title="可复现路径规划验证",
            hypothesis="候选方法应在公开任务上优于经典规划器。",
            mechanism="对相同障碍布局和随机种子运行候选方法与 baseline。",
            expected_contribution="给出可复现的机械臂路径规划评估协议。",
            novelty=4,
            feasibility=4,
            risk=2,
            evaluation=["任务成功率"],
            baseline="文献中最高相关的传统 baseline 或消融版本",
        )

        experiment_plan = plan_experiment(idea, research_plan=research_plan)

        self.assertIn("RRT", experiment_plan.baseline)
        self.assertIn("planning_success_rate", experiment_plan.metrics)


if __name__ == "__main__":
    unittest.main()
