from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.experiment_decision import (
    build_experiment_decision_report,
    render_experiment_decision_markdown,
    write_experiment_decision_artifacts,
)
from research_agent.models import ExperimentCommand, ExperimentPlan, MetricComparison, StatisticsReport


class ExperimentDecisionTest(unittest.TestCase):
    def test_blocks_writing_when_results_need_repair(self) -> None:
        report = build_experiment_decision_report(
            _plan(),
            _statistics([]),
            {"status": "block", "blocking_issues": ["candidate 与 baseline 没有共同指标"]},
            {"status": "block", "summary": {"failed_runs": 1}, "failed_runs": [{"name": "candidate"}], "claim_boundaries": ["当前结果不得用于主张有效。"]},
            execution_mode="local",
        )

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["decision"], "repair_before_writing")
        self.assertFalse(report["downstream_writing_allowed"])
        self.assertTrue(any("repair_before_writing" in item for item in report["claim_boundaries"]))

    def test_negative_metrics_trigger_pivot_or_refine(self) -> None:
        report = build_experiment_decision_report(
            _plan(),
            _statistics([_comparison("planning_time", -0.2, "baseline_better_or_equal")]),
            {"status": "pass"},
            {"status": "warn", "summary": {"negative_metrics": 1}, "negative_metrics": [{"metric": "planning_time"}]},
            execution_mode="benchmark",
        )
        rendered = render_experiment_decision_markdown(report)

        self.assertEqual(report["decision"], "pivot_or_refine")
        self.assertEqual(report["paper_policy"], "report_negative_results_and_consider_pivot")
        self.assertIn("planning_time", " ".join(report["next_actions"]))
        self.assertIn("实验后决策", rendered)

    def test_negative_result_maps_to_not_supported_with_stop_after_report(self) -> None:
        # A15：合格负结果 → not_supported + proceed + stop_after_report，四态独立。
        report = build_experiment_decision_report(
            _plan(),
            _statistics([_comparison("planning_time", -0.2, "baseline_better_or_equal")]),
            {"status": "pass"},
            {"status": "warn", "summary": {"negative_metrics": 1}, "negative_metrics": [{"metric": "planning_time"}]},
            execution_mode="benchmark",
        )
        states = report["decision_states"]
        self.assertEqual(states["research_outcome"], "not_supported")
        self.assertEqual(states["next_action"], "proceed")
        self.assertTrue(states["stop_after_report"])
        self.assertEqual(states["evidence_status"], "verified")
        self.assertEqual(states["execution_status"], "completed")
        rendered = render_experiment_decision_markdown(report)
        self.assertIn("四类决策状态", rendered)
        self.assertIn("not_supported", rendered)

    def test_blocked_validation_maps_to_repair_and_not_assessed(self) -> None:
        report = build_experiment_decision_report(
            _plan(),
            _statistics([]),
            {"status": "block", "blocking_issues": ["x"]},
            {"status": "block", "summary": {"failed_runs": 1}, "failed_runs": [{"name": "c", "status": "failed"}]},
            execution_mode="local",
        )
        states = report["decision_states"]
        self.assertEqual(states["next_action"], "repair")
        self.assertEqual(states["research_outcome"], "not_assessed")
        self.assertEqual(states["evidence_status"], "invalid")
        self.assertEqual(states["execution_status"], "failed")

    def test_simulated_mode_maps_to_simulated_evidence(self) -> None:
        report = build_experiment_decision_report(
            _plan(),
            _statistics([_comparison("success_rate", 0.2, "candidate_better")]),
            {"status": "pass"},
            {"status": "pass", "summary": {"simulated_runs": 5}, "failed_runs": []},
            execution_mode="simulated",
        )
        states = report["decision_states"]
        self.assertEqual(states["evidence_status"], "simulated")
        self.assertEqual(states["research_outcome"], "not_assessed")
        self.assertEqual(states["next_action"], "request_material")

    def test_primary_metric_governs_when_secondary_improves(self) -> None:
        # 复审第 4 项复现：主指标变差、次指标变好 → 不得同时输出
        # pivot_or_refine 与 supported；契约主指标决定结论。
        contract = {"evaluation": {"primary_metrics": ["accuracy"]}}
        report = build_experiment_decision_report(
            _plan(),
            _statistics([
                _comparison("accuracy", -0.2, "baseline_better_or_equal"),
                _comparison("speed", 0.5, "candidate_better"),
            ]),
            {"status": "pass"},
            {"status": "pass", "summary": {}, "failed_runs": [],
             "negative_metrics": [{"metric": "accuracy"}], "uncertain_metrics": []},
            execution_mode="benchmark",
            contract=contract,
        )
        self.assertEqual(report["decision"], "pivot_or_refine")
        states = report["decision_states"]
        self.assertEqual(states["research_outcome"], "not_supported")
        self.assertNotEqual(states["research_outcome"], "supported")
        self.assertEqual(report["primary_metrics"], ["accuracy"])
        # 次指标单独变差不影响主指标结论：主指标稳定为正 → supported。
        report2 = build_experiment_decision_report(
            _plan(),
            _statistics([
                _comparison("accuracy", 0.2, "candidate_better"),
                _comparison("speed", -0.5, "baseline_better_or_equal"),
            ]),
            {"status": "pass"},
            {"status": "pass", "summary": {}, "failed_runs": [],
             "negative_metrics": [{"metric": "speed"}], "uncertain_metrics": []},
            execution_mode="benchmark",
            contract=contract,
        )
        self.assertEqual(report2["decision"], "proceed_to_paper")
        self.assertEqual(report2["decision_states"]["research_outcome"], "supported")
        # 无契约时保持旧行为（全部指标参与判定）。
        report3 = build_experiment_decision_report(
            _plan(),
            _statistics([_comparison("accuracy", 0.2, "candidate_better")]),
            {"status": "pass"},
            {"status": "pass", "summary": {}, "failed_runs": [], "negative_metrics": [], "uncertain_metrics": []},
            execution_mode="benchmark",
        )
        self.assertEqual(report3["decision_states"]["research_outcome"], "supported")

    def test_write_experiment_decision_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            report = write_experiment_decision_artifacts(
                _plan(),
                _statistics([_comparison("success_rate", 0.2, "candidate_better")]),
                {"status": "pass"},
                {"status": "pass", "summary": {"failed_runs": 0, "negative_metrics": 0, "uncertain_metrics": 0}},
                Path(tmp),
                execution_mode="local",
            )
            saved = json.loads((Path(tmp) / "04-experiment-decision.json").read_text(encoding="utf-8"))

            self.assertEqual(report["decision"], "proceed_to_paper")
            self.assertTrue((Path(tmp) / "04-experiment-decision.md").exists())
            self.assertEqual(saved["status"], "pass")


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="机械臂路径规划验证",
        objective="验证候选规划器。",
        variables=["planner"],
        metrics=["success_rate", "planning_time"],
        protocol=["构建任务", "运行 candidate/baseline", "统计指标"],
        commands=[ExperimentCommand(name="candidate", command=["python3", "run.py"])],
        baseline="RRT*",
    )


def _statistics(comparisons: list[MetricComparison]) -> StatisticsReport:
    return StatisticsReport(
        idea_title="机械臂路径规划验证",
        repeats=3,
        candidate_name="candidate",
        baseline_name="baseline",
        comparisons=comparisons,
        warnings=[],
    )


def _comparison(metric: str, delta: float, direction: str) -> MetricComparison:
    return MetricComparison(
        metric=metric,
        candidate_mean=1.0,
        baseline_mean=1.0 - delta,
        delta=delta,
        ci_low=delta - 0.1,
        ci_high=delta + 0.1,
        candidate_std=0.1,
        baseline_std=0.1,
        effect_size=0.5,
        direction=direction,
        interpretation="test comparison",
    )


if __name__ == "__main__":
    unittest.main()
