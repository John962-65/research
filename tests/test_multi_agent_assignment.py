from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.config import ExecutionConfig, IdeationConfig
from research_agent.ideation import generate_ideas
from research_agent.literature_context import build_literature_context
from research_agent.models import LiteratureReview, Paper, ResearchPlan
from research_agent.multi_agent_assignment import (
    agent_roles_for_text,
    build_multi_agent_assignment,
    multi_agent_prompt_context,
    render_multi_agent_assignment_markdown,
    write_multi_agent_assignment_artifacts,
)
from research_agent.research_gap_map import build_research_gap_map


class EmptyLLM:
    def complete(self, system: str, user: str) -> str:
        return "{}"


class MultiAgentAssignmentTest(unittest.TestCase):
    def test_assignment_routes_research_tasks_to_specialized_agents(self) -> None:
        plan = _plan()
        review = _review()
        context = build_literature_context(review)
        gap_map = build_research_gap_map("机械臂路径规划", plan, review, context, {"status": "pass", "missing_required": []})

        report = build_multi_agent_assignment(
            "机械臂路径规划",
            plan,
            review,
            context,
            {"status": "pass", "missing_required": []},
            {"status": "pass"},
            gap_map,
            {"constraints": [{"id": "RC01", "category": "baseline", "priority": "high", "text": "必须比较 RRT*"}]},
            ExecutionConfig(mode="benchmark", repeats=3, benchmark_manifest_paths=["candidate.json", "baseline.json", "ablation.json"]),
        )
        rendered = render_multi_agent_assignment_markdown(report)

        self.assertEqual(report["status"], "active")
        self.assertTrue(report["multi_agent_ready"])
        self.assertIn("benchmark_engineer", report["active_agents"])
        self.assertIn("statistician", report["active_agents"])
        self.assertEqual(len(report["tasks"]), 8)
        self.assertEqual(report["team_profile"]["profile"], "benchmark_paper_grade")
        self.assertTrue(report["task_routes"])
        benchmark_route = next(item for item in report["task_routes"] if item["task_type"] == "benchmark_execution")
        paper_route = next(item for item in report["task_routes"] if item["task_type"] == "paper_deliberation")
        self.assertEqual(benchmark_route["primary_agents"], ["benchmark_engineer", "statistician"])
        self.assertIn("manuscript_editor", paper_route["primary_agents"])
        self.assertNotEqual(benchmark_route["all_agents"], paper_route["all_agents"])
        benchmark_task = next(item for item in report["tasks"] if item["agent_id"] == "benchmark_engineer")
        self.assertEqual(benchmark_task["priority"], "critical")
        self.assertIn("多智能体任务分配", rendered)
        self.assertIn("Task-Team Routing", rendered)

    def test_agent_roles_feed_ideation_fallback(self) -> None:
        plan = _plan()
        review = _review()
        context = build_literature_context(review)
        gap_map = build_research_gap_map("机械臂路径规划", plan, review, context, {"status": "pass", "missing_required": []})
        assignment = build_multi_agent_assignment(
            "机械臂路径规划",
            plan,
            review,
            context,
            {"status": "pass", "missing_required": []},
            {"status": "pass"},
            gap_map,
            {},
            ExecutionConfig(mode="benchmark", repeats=3, benchmark_manifest_paths=["candidate.json"]),
        )

        ideas = generate_ideas(review, IdeationConfig(max_ideas=1), EmptyLLM(), context, research_gap_map=gap_map, agent_assignment=assignment)

        self.assertEqual(len(ideas), 1)
        self.assertIn("method_architect", ideas[0].agent_roles)
        self.assertTrue(any(role in ideas[0].agent_roles for role in ["benchmark_engineer", "statistician", "skeptical_reviewer"]))
        self.assertIn("method_architect", agent_roles_for_text(assignment, ideas[0].gap_alignment))
        self.assertIn("benchmark_engineer", multi_agent_prompt_context(assignment))
        self.assertIn("paper_deliberation", multi_agent_prompt_context(assignment))

    def test_write_assignment_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            plan = _plan()
            review = _review()
            context = build_literature_context(review)
            gap_map = build_research_gap_map("机械臂路径规划", plan, review, context, {"status": "pass", "missing_required": []})

            report = write_multi_agent_assignment_artifacts(
                "机械臂路径规划",
                plan,
                review,
                context,
                {"status": "pass", "missing_required": []},
                {"status": "pass"},
                gap_map,
                {},
                ExecutionConfig(),
                Path(tmp),
            )
            saved = json.loads((Path(tmp) / "02-agent-team.json").read_text(encoding="utf-8"))

            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(saved["tasks"][0]["agent_id"], "literature_scout")
            self.assertIn("task_routes", saved)
            self.assertTrue((Path(tmp) / "02-agent-team.md").exists())


def _plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="评估机械臂路径规划方法。",
        search_queries=["robot manipulator motion planning benchmark"],
        benchmarks=["OMPL manipulation benchmark"],
        baselines=["RRT*", "TrajOpt"],
        metrics=["planning_success_rate", "planning_time", "collision_rate"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _review() -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="RRT star for narrow passage robot manipulator planning",
                authors=["A. Author"],
                year=2024,
                venue="Robotics",
                url="https://example.org/rrt",
                abstract="RRT* and OMPL manipulation benchmark studies report planning_success_rate, planning_time, and collision_rate for narrow passage robot manipulator motion planning.",
                relevance=0.95,
                source="offline",
                sources=["offline"],
                doi="10.1234/rrt",
            )
        ],
        themes=["机械臂路径规划需要公平 baseline。"],
        gaps=["窄通道失败模式缺少与 RRT* 的可复现比较。"],
        summary="测试综述。",
    )


if __name__ == "__main__":
    unittest.main()
