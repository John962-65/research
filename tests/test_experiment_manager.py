from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.experiment_manager import (
    build_experiment_manager_report,
    experiment_manager_constraints,
    render_experiment_manager_markdown,
    write_experiment_manager_artifacts,
)
from research_agent.exploration_map import build_exploration_map
from research_agent.models import ResearchIdea


class ExperimentManagerTest(unittest.TestCase):
    def test_manager_adds_smoke_first_constraints_for_risky_selected_branch(self) -> None:
        ideas = [
            _idea("高风险但证据充分", risk=5, evidence_keys=["p1", "p2"], baseline="RRT*"),
            _idea("下一轮候选", risk=5, evidence_keys=["p3"], baseline="CHOMP"),
        ]
        exploration = build_exploration_map("机械臂路径规划", ideas)

        report = build_experiment_manager_report("机械臂路径规划", ideas, exploration)

        self.assertEqual(report["selected_idea_title"], "高风险但证据充分")
        self.assertEqual(report["manager_decision"], "proceed_with_cautions")
        self.assertEqual(report["execution_policy"], "smoke_first")
        self.assertTrue(any("smoke-first" in item for item in report["planning_constraints"]))
        self.assertTrue(any("RRT*" in item for item in report["planning_constraints"]))
        self.assertIn("Experiment manager constraints", experiment_manager_constraints(report))
        self.assertEqual(report["queue_summary"]["active"], 1)
        self.assertEqual(report["queue_summary"]["human_review"], 1)
        self.assertEqual(report["queue_summary"]["ready_backlog"], 1)
        self.assertEqual(report["manager_queue"][0]["queue_state"], "active_smoke_first")
        self.assertEqual(report["manager_queue"][0]["owner"], "human+agent")
        self.assertFalse(report["manager_queue"][0]["blocks_current_experiment"])

    def test_manager_blocks_selected_branch_with_blocked_idea_audit(self) -> None:
        ideas = [_idea("证据无效分支", risk=1, evidence_keys=["bad"], baseline="RRT*")]
        exploration = build_exploration_map("机械臂路径规划", ideas)
        idea_audit = {"items": [{"idea_title": "证据无效分支", "decision": "block", "issues": ["invalid citation keys: bad"]}]}

        report = build_experiment_manager_report("机械臂路径规划", ideas, exploration, idea_audit=idea_audit)

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["manager_decision"], "needs_human_reselection")
        self.assertTrue(any("idea audit 为 block" in item for item in report["required_actions"]))
        self.assertEqual(report["queue_summary"]["blocked"], 1)
        self.assertEqual(report["queue_summary"]["blocks_current_experiment"], 1)
        self.assertEqual(report["manager_queue"][0]["queue_state"], "blocked_human_repair")
        self.assertTrue(report["manager_queue"][0]["requires_human"])
        self.assertTrue(report["manager_queue"][0]["blocks_current_experiment"])
        self.assertEqual(report["manager_queue"][0]["resume_from"], "ideation")
        self.assertIn("invalid citation keys: bad", report["manager_queue"][0]["issues"])

    def test_manager_writes_markdown_and_json_artifacts(self) -> None:
        ideas = [
            _idea("主分支", risk=2, evidence_keys=["p1"], baseline="RRT*"),
            _idea("候选分支", risk=2, evidence_keys=["p2"], baseline="CHOMP"),
        ]
        exploration = build_exploration_map("机械臂路径规划", ideas)
        with TemporaryDirectory() as tmp:
            report = write_experiment_manager_artifacts("机械臂路径规划", ideas, exploration, Path(tmp))
            rendered = render_experiment_manager_markdown(report)
            saved = json.loads((Path(tmp) / "02-experiment-manager.json").read_text(encoding="utf-8"))

        self.assertIn("Experiment Manager", rendered)
        self.assertIn("Manager Queue", rendered)
        self.assertEqual(saved["selected_branch_id"], report["selected_branch_id"])
        self.assertEqual(saved["branch_budget"]["expand_now"], 1)
        self.assertEqual(saved["queue_summary"]["total"], 2)
        self.assertEqual(len(saved["manager_queue"]), 2)


def _idea(title: str, risk: int, evidence_keys: list[str], baseline: str) -> ResearchIdea:
    return ResearchIdea(
        title=title,
        hypothesis=f"{title} 可以改善路径规划评估。",
        mechanism="用可审计分支约束实验管理。",
        expected_contribution="减少无证据 idea 进入实验。",
        novelty=5 if "高风险" in title else 4,
        feasibility=5,
        risk=risk,
        evidence_keys=evidence_keys,
        evidence_chunks=[f"{item}-chunk" for item in evidence_keys],
        baseline=baseline,
        gap_alignment="覆盖 benchmark/baseline 空白。",
        evaluation=["planning_success_rate", "planning_time", "path_length"],
        experiment_sketch=["构建任务集", "运行 baseline", "比较候选"],
    )


if __name__ == "__main__":
    unittest.main()
