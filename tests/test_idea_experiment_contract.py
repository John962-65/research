from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.config import ExecutionConfig
from research_agent.idea_experiment_contract import (
    IDEA_EXPERIMENT_CONTRACT_JSON,
    IDEA_EXPERIMENT_CONTRACT_MD,
    append_contract_history,
    build_execution_contract,
    build_idea_experiment_contract_report,
    render_idea_experiment_contract_markdown,
    write_idea_experiment_contract_artifacts,
)
from research_agent.models import ExplorationBranch, ExplorationMap, ExperimentCommand, ExperimentPlan, ResearchIdea, ResearchPlan


class IdeaExperimentContractTest(unittest.TestCase):
    def test_contract_passes_aligned_benchmark_plan(self) -> None:
        report = build_idea_experiment_contract_report(
            _research_plan(),
            _idea(),
            _exploration_map(),
            _plan(),
            _benchmark_readiness("ready_for_benchmark"),
            ExecutionConfig(mode="benchmark"),
            ablation_plan={"status": "pass", "has_ablation": True},
            preregistration={"status": "locked", "timing": "before_results"},
            constraint_compliance={"status": "pass", "blocked": 0, "review_required": 0},
        )
        rendered = render_idea_experiment_contract_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["blocking_issues"])
        self.assertGreater(report["contract_score"], 0.99)
        self.assertIn("Idea-实验契约", rendered)
        self.assertTrue(any(check["name"] == "evidence_carryover" and check["status"] == "pass" for check in report["checks"]))

    def test_complete_contract_passes_without_keyword_echo(self) -> None:
        # A11：命令带显式 comparison_group 时，不因名称缺 candidate/baseline 关键词误拦。
        plan = _plan()
        plan_commands = [
            ExperimentCommand(name="run-a", command=["python3", "simulate.py"], comparison_group="candidate"),
            ExperimentCommand(name="run-b", command=["python3", "simulate.py"], comparison_group="baseline"),
            ExperimentCommand(name="run-c", command=["python3", "simulate.py"], comparison_group="ablation"),
        ]
        plan = ExperimentPlan(
            idea_title=plan.idea_title,
            objective=plan.objective,
            variables=plan.variables,
            metrics=plan.metrics,
            protocol=plan.protocol,
            commands=plan_commands,
            baseline=plan.baseline,
            evidence_keys=plan.evidence_keys,
        )
        report = build_idea_experiment_contract_report(
            _research_plan(),
            _idea(),
            _exploration_map(),
            plan,
            _benchmark_readiness("ready_for_benchmark"),
            ExecutionConfig(mode="benchmark"),
            ablation_plan={"status": "pass", "has_ablation": True},
            preregistration={"status": "locked", "timing": "before_results"},
            constraint_compliance={"status": "pass", "blocked": 0, "review_required": 0},
        )
        self.assertEqual(report["status"], "pass")
        command_check = next(check for check in report["checks"] if check["name"] == "command_contract")
        self.assertEqual(command_check["status"], "pass")

    def test_execution_contract_has_eight_field_groups(self) -> None:
        # T05：契约是执行与评估共同读取的权威结构，包含全部字段组与内容摘要。
        contract = build_execution_contract(
            _research_plan(), _idea(), _plan(), ExecutionConfig(mode="local", repeats=5),
            preregistration={"status": "locked", "timing": "before_results", "primary_metrics": ["planning_success_rate", "planning_time"]},
            ablation_plan={"status": "pass", "has_ablation": True},
        )
        for group in ("hypothesis", "method", "data", "evaluation", "criteria", "verification", "execution"):
            self.assertIn(group, contract)
        self.assertTrue(contract["contract_id"])
        self.assertTrue(contract["digest"])
        self.assertEqual(contract["evaluation"]["primary_metrics"], ["planning_success_rate", "planning_time"])
        self.assertIn("不得把未显著简单等同无效", str(contract["criteria"]))

    def test_contract_history_versions_after_results(self) -> None:
        # A12：结果出来后改契约 → 新版本 + rerun_required，旧批准不沿用。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            contract = build_execution_contract(_research_plan(), _idea(), _plan(), ExecutionConfig(mode="local"))
            history = append_contract_history(run_dir, dict(contract), results_exist=False)
            self.assertEqual(len(history["entries"]), 1)
            self.assertEqual(history["entries"][0]["reason"], "initial_freeze")
            # 结果存在后契约内容变化（改主指标）。
            changed = dict(contract)
            changed["evaluation"] = dict(contract["evaluation"], primary_metrics=["planning_time"])
            changed["digest"] = __import__("research_agent.evidence_snapshot", fromlist=["payload_sha256"]).payload_sha256(
                {k: v for k, v in changed.items() if k not in {"revision", "frozen_at", "approvals", "digest"}}
            )
            history = append_contract_history(run_dir, changed, results_exist=True)
            self.assertEqual(len(history["entries"]), 2)
            self.assertEqual(history["entries"][-1]["reason"], "post_results_change")
            self.assertTrue(history["entries"][-1]["rerun_required"])
            # 相同内容重复冻结不产生新版本。
            history = append_contract_history(run_dir, dict(changed), results_exist=True)
            self.assertEqual(len(history["entries"]), 2)

    def test_contract_blocks_title_drift_and_missing_evidence(self) -> None:
        weak_idea = ResearchIdea(
            title="evidence-free idea",
            hypothesis="no evidence",
            mechanism="unknown",
            expected_contribution="none",
            novelty=3,
            feasibility=3,
            risk=1,
            evaluation=["planning_success_rate"],
            baseline="",
        )
        plan = _plan(idea_title="different idea", baseline="最相关 baseline", evidence_keys=[])

        report = build_idea_experiment_contract_report(
            _research_plan(),
            weak_idea,
            _exploration_map(title=weak_idea.title),
            plan,
            _benchmark_readiness("ready_for_benchmark"),
            ExecutionConfig(mode="benchmark"),
            ablation_plan={"status": "pass", "has_ablation": True},
            preregistration={"status": "locked", "timing": "before_results"},
            constraint_compliance={"status": "pass", "blocked": 0},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("标题" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any("evidence_keys" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any("baseline" in issue for issue in report["blocking_issues"]))

    def test_contract_marks_simulated_mode_as_review_required(self) -> None:
        report = build_idea_experiment_contract_report(
            _research_plan(),
            _idea(),
            _exploration_map(),
            _plan(),
            _benchmark_readiness("needs_benchmark_upgrade", manual_tasks=["切换 benchmark manifest。"]),
            ExecutionConfig(mode="simulated"),
            ablation_plan={"status": "pass", "has_ablation": True},
            preregistration={"status": "locked", "timing": "before_results"},
            constraint_compliance={"status": "pass", "blocked": 0, "review_required": 0},
        )

        self.assertEqual(report["status"], "review_required")
        self.assertTrue(any("benchmark" in task.lower() for task in report["manual_tasks"]))

    def test_write_contract_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            report = write_idea_experiment_contract_artifacts(
                _research_plan(),
                _idea(),
                _exploration_map(),
                _plan(),
                _benchmark_readiness("ready_for_benchmark"),
                ExecutionConfig(mode="benchmark"),
                run_dir,
                ablation_plan={"status": "pass", "has_ablation": True},
                preregistration={"status": "locked", "timing": "before_results"},
                constraint_compliance={"status": "pass", "blocked": 0, "review_required": 0},
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / IDEA_EXPERIMENT_CONTRACT_JSON).exists())
            self.assertTrue((run_dir / IDEA_EXPERIMENT_CONTRACT_MD).exists())


def _research_plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="提升机械臂路径规划成功率和轨迹质量。",
        search_queries=["robot manipulator motion planning RRT OMPL"],
        benchmarks=["OMPL"],
        baselines=["RRT", "RRT*"],
        metrics=["planning_success_rate", "planning_time", "path_length"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _idea() -> ResearchIdea:
    return ResearchIdea(
        title="evidence-grounded planner",
        hypothesis="collision-margin smoothing improves planning success.",
        mechanism="adaptive collision margin with trajectory smoothing",
        expected_contribution="higher success rate under clutter",
        novelty=8,
        feasibility=7,
        risk=3,
        evaluation=["planning_success_rate", "planning_time"],
        evidence_keys=["paper2011", "ompl2012"],
        baseline="RRT",
        experiment_sketch=["run candidate", "run baseline", "run ablation"],
    )


def _exploration_map(title: str = "evidence-grounded planner") -> ExplorationMap:
    return ExplorationMap(
        topic="机械臂路径规划",
        selected_branch_id="B1",
        selected_idea_title=title,
        branches=[
            ExplorationBranch(
                branch_id="B1",
                title=title,
                status="selected",
                score=0.9,
                idea_score=12,
                evidence_count=2,
                risk=3,
                rationale="best supported",
                action="select",
                evidence_keys=["paper2011"],
                baseline="RRT",
            )
        ],
        decision="select B1",
    )


def _plan(idea_title: str = "evidence-grounded planner", baseline: str = "RRT", evidence_keys: list[str] | None = None) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title=idea_title,
        objective="Compare candidate planner against RRT on OMPL tasks.",
        variables=["planner", "scene_complexity"],
        metrics=["planning_success_rate", "planning_time", "path_length"],
        protocol=["run candidate", "run baseline", "run ablation"],
        commands=[
            ExperimentCommand(name="robotics_candidate_planner", command=["python3", "simulate.py"]),
            ExperimentCommand(name="robotics_baseline_planner", command=["python3", "simulate.py"]),
            ExperimentCommand(name="robotics_ablation_planner", command=["python3", "simulate.py"]),
        ],
        baseline=baseline,
        evidence_keys=evidence_keys if evidence_keys is not None else ["paper2011", "ompl2012"],
        template_profile="robotics_motion_planning",
    )


def _benchmark_readiness(status: str, manual_tasks: list[str] | None = None) -> dict[str, object]:
    return {
        "status": status,
        "blocking_issues": ["benchmark manifest missing"] if status == "block" else [],
        "manual_tasks": manual_tasks or [],
        "checks": [{"name": "metric_alignment", "evidence": ["overlap=planning_success_rate, planning_time"]}],
    }


if __name__ == "__main__":
    unittest.main()
