from __future__ import annotations

import unittest

from research_agent.exploration_map import build_exploration_map, selected_idea
from research_agent.models import LiteratureReview, Paper, ResearchIdea
from research_agent.novelty_audit import build_novelty_audit, duplicate_penalty, render_novelty_audit_markdown


class NoveltyAuditTest(unittest.TestCase):
    def test_audit_flags_idea_that_restates_existing_paper(self) -> None:
        review = _review()
        duplicate = ResearchIdea(
            title="RRT robot manipulator motion planning",
            hypothesis="RRT improves robot manipulator motion planning with collision avoidance.",
            mechanism="Use sampling based planning for robot arm path planning.",
            expected_contribution="Reproduce an existing motion planning result.",
            novelty=5,
            feasibility=4,
            risk=1,
            evaluation=["planning_success_rate"],
            evidence_keys=["paper1"],
        )

        report = build_novelty_audit("机械臂路径规划", [duplicate], review)
        rendered = render_novelty_audit_markdown(report)

        self.assertEqual(report["likely_duplicates"], 1)
        self.assertEqual(report["items"][0]["decision"], "likely_duplicate")
        self.assertGreater(duplicate_penalty(report["items"][0]), 1.0)
        self.assertIn("Idea 新颖性审计", rendered)
        self.assertIn("RRT robot manipulator motion planning", rendered)

    def test_exploration_map_penalizes_duplicate_branch(self) -> None:
        review = _review()
        duplicate = ResearchIdea(
            title="RRT robot manipulator motion planning",
            hypothesis="RRT improves robot manipulator motion planning with collision avoidance.",
            mechanism="Use sampling based planning for robot arm path planning.",
            expected_contribution="Reproduce an existing motion planning result.",
            novelty=5,
            feasibility=5,
            risk=1,
            evaluation=["planning_success_rate"],
            evidence_keys=["paper1"],
        )
        distinct = ResearchIdea(
            title="Failure taxonomy for narrow-passage manipulator planning",
            hypothesis="Failure taxonomy can expose when planners break in narrow passages.",
            mechanism="Classify infeasible, collision-prone, and unstable planning cases before comparing baselines.",
            expected_contribution="A review-grounded evaluation protocol rather than a restated planner.",
            novelty=4,
            feasibility=4,
            risk=2,
            evaluation=["failure_case_coverage"],
            evidence_keys=["paper1"],
        )
        novelty = build_novelty_audit("机械臂路径规划", [duplicate, distinct], review)

        exploration = build_exploration_map("机械臂路径规划", [duplicate, distinct], novelty)

        self.assertEqual(selected_idea(exploration, [duplicate, distinct]).title, distinct.title)
        self.assertIn("novelty=likely_duplicate", exploration.branches[0].rationale)


def _review() -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="Sampling-based Algorithms for Optimal Motion Planning",
                authors=["Karaman", "Frazzoli"],
                year=2011,
                venue="IJRR",
                url="https://doi.org/10.1177/0278364911406761",
                abstract="RRT and RRT* sampling based algorithms for optimal robot manipulator motion planning and collision avoidance.",
                relevance=0.9,
                source="offline",
                sources=["offline"],
                doi="10.1177/0278364911406761",
            )
        ],
        themes=["机械臂路径规划需要比较 sampling-based planning。"],
        gaps=["需要失败分类和公平 baseline。"],
        summary="测试综述",
    )


if __name__ == "__main__":
    unittest.main()
