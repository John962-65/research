from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.experiments import plan_experiment, render_experiment_plan_markdown
from research_agent.models import ExperimentCommand, ExperimentPlan, ResearchIdea
from research_agent.multi_agent_handoff_audit import (
    MULTI_AGENT_HANDOFF_AUDIT_JSON,
    build_multi_agent_handoff_audit,
    render_multi_agent_handoff_audit_markdown,
    write_multi_agent_handoff_audit_artifacts,
)


class MultiAgentHandoffAuditTest(unittest.TestCase):
    def test_experiment_plan_inherits_agent_roles_from_idea(self) -> None:
        idea = _idea()

        plan = plan_experiment(idea)
        rendered = render_experiment_plan_markdown(plan)

        self.assertIn("method_architect", plan.agent_roles)
        self.assertIn("statistician", plan.agent_roles)
        self.assertIn("Agent Roles", rendered)

    def test_handoff_audit_passes_when_assignment_idea_and_plan_align(self) -> None:
        idea = _idea()
        plan = _plan(agent_roles=idea.agent_roles)
        report = build_multi_agent_handoff_audit("机械臂路径规划", idea, plan, _assignment())
        rendered = render_multi_agent_handoff_audit_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(any(check["name"] == "experiment_agent_roles" and check["status"] == "pass" for check in report["checks"]))
        self.assertIn("多智能体 Handoff 审计", rendered)

    def test_handoff_audit_blocks_missing_roles(self) -> None:
        idea = _idea(agent_roles=[])
        plan = _plan(agent_roles=[])

        report = build_multi_agent_handoff_audit("机械臂路径规划", idea, plan, _assignment())

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("agent_roles" in issue for issue in report["blocking_issues"]))

    def test_write_handoff_audit_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_multi_agent_handoff_audit_artifacts("机械臂路径规划", _idea(), _plan(), _assignment(), run_dir)
            saved = json.loads((run_dir / MULTI_AGENT_HANDOFF_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(saved["schema_version"], 1)
            self.assertTrue((run_dir / "03-agent-handoff-audit.md").exists())


def _idea(agent_roles: list[str] | None = None) -> ResearchIdea:
    return ResearchIdea(
        title="多智能体机械臂规划验证",
        hypothesis="collision-margin smoothing improves planning success.",
        mechanism="adaptive collision margin with trajectory smoothing",
        expected_contribution="higher success rate under clutter",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=["planning_success_rate", "planning_time", "collision_rate"],
        evidence_keys=["paper2011", "ompl2012"],
        baseline="RRT*",
        experiment_sketch=["run candidate", "run baseline", "run ablation"],
        agent_roles=agent_roles
        if agent_roles is not None
        else ["gap_analyst", "method_architect", "benchmark_engineer", "statistician", "skeptical_reviewer"],
    )


def _plan(agent_roles: list[str] | None = None) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="多智能体机械臂规划验证",
        objective="Compare candidate planner against RRT* on benchmark tasks.",
        variables=["planner", "scene_complexity"],
        metrics=["planning_success_rate", "planning_time", "collision_rate"],
        protocol=["run candidate", "run baseline", "run ablation"],
        commands=[
            ExperimentCommand(name="candidate", command=["python3", "simulate.py"]),
            ExperimentCommand(name="baseline", command=["python3", "simulate.py"]),
            ExperimentCommand(name="ablation", command=["python3", "simulate.py"]),
        ],
        baseline="RRT*",
        evidence_keys=["paper2011", "ompl2012"],
        agent_roles=agent_roles
        if agent_roles is not None
        else ["gap_analyst", "method_architect", "benchmark_engineer", "statistician", "skeptical_reviewer"],
    )


def _assignment() -> dict[str, object]:
    return {
        "status": "active",
        "active_agents": ["literature_scout", "evidence_curator", "gap_analyst", "method_architect", "benchmark_engineer", "statistician", "skeptical_reviewer", "manuscript_editor"],
        "tasks": [
            {"task_id": "A03", "agent_id": "gap_analyst", "status": "active"},
            {"task_id": "A04", "agent_id": "method_architect", "status": "active"},
            {"task_id": "A05", "agent_id": "benchmark_engineer", "status": "active"},
            {"task_id": "A06", "agent_id": "statistician", "status": "active"},
            {"task_id": "A07", "agent_id": "skeptical_reviewer", "status": "active"},
        ],
    }


if __name__ == "__main__":
    unittest.main()
