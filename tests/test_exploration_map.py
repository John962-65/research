from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.exploration_map import (
    build_exploration_map,
    render_exploration_map_markdown,
    render_exploration_map_svg,
    selected_idea,
    write_exploration_map_artifacts,
)
from research_agent.models import ResearchIdea


class ExplorationMapTest(unittest.TestCase):
    def test_exploration_map_selects_evidence_rich_branch_and_writes_artifacts(self) -> None:
        ideas = [
            _idea("高风险弱证据", novelty=5, feasibility=3, risk=5, evidence_keys=[]),
            _idea("证据充分路径", novelty=4, feasibility=4, risk=2, evidence_keys=["a", "b"], baseline="RRT*"),
        ]
        with TemporaryDirectory() as tmp:
            report = write_exploration_map_artifacts("机械臂路径规划", ideas, Path(tmp))
            rendered = render_exploration_map_markdown(report)
            svg = render_exploration_map_svg(report)
            saved = json.loads((Path(tmp) / "02-exploration-map.json").read_text(encoding="utf-8"))

            self.assertEqual(report.selected_branch_id, "B2")
            self.assertEqual(selected_idea(report, ideas).title, "证据充分路径")
            self.assertTrue(any(branch.status == "pruned" for branch in report.branches))
            self.assertIn("研究分支探索图", rendered)
            self.assertIn("<svg", svg)
            self.assertEqual(saved["selected_idea_title"], "证据充分路径")

    def test_exploration_map_warns_when_selected_branch_has_no_evidence(self) -> None:
        report = build_exploration_map("科研 agent", [_idea("无证据但可行", novelty=3, feasibility=5, risk=1, evidence_keys=[])])

        self.assertEqual(report.selected_branch_id, "B1")
        self.assertTrue(any("缺少显式文献证据" in warning for warning in report.warnings))

    def test_exploration_map_penalizes_blocked_idea_audit_branch(self) -> None:
        ideas = [
            _idea("高分但证据无效", novelty=5, feasibility=5, risk=1, evidence_keys=["bad"]),
            _idea("较稳健可执行", novelty=4, feasibility=4, risk=2, evidence_keys=["paper2024"], baseline="RRT*"),
        ]
        idea_audit = {
            "items": [
                {"idea_title": "高分但证据无效", "decision": "block", "issues": ["invalid citation keys: bad"]},
                {"idea_title": "较稳健可执行", "decision": "pass", "issues": []},
            ]
        }

        report = build_exploration_map("机械臂路径规划", ideas, idea_audit=idea_audit)

        self.assertEqual(report.selected_branch_id, "B2")
        self.assertIn("idea_audit=block", report.branches[0].rationale)


def _idea(title: str, novelty: int, feasibility: int, risk: int, evidence_keys: list[str], baseline: str = "") -> ResearchIdea:
    return ResearchIdea(
        title=title,
        hypothesis=f"{title} 可以提升实验可信度。",
        mechanism="使用文献证据约束分支选择。",
        expected_contribution="形成可审计的研究探索记录。",
        novelty=novelty,
        feasibility=feasibility,
        risk=risk,
        evidence_keys=evidence_keys,
        evidence_chunks=[f"{item}-chunk" for item in evidence_keys],
        baseline=baseline,
        evaluation=["success_rate", "runtime", "coverage"],
        experiment_sketch=["生成分支", "评分", "选择实验路径"],
    )


if __name__ == "__main__":
    unittest.main()
