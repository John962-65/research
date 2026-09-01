from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.hypothesis_outcome import build_hypothesis_outcome_report, render_hypothesis_outcome_markdown, write_hypothesis_outcome_artifacts
from research_agent.models import ExperimentCommand, ExperimentPlan, MetricComparison, ResearchIdea, StatisticsReport


class HypothesisOutcomeTest(unittest.TestCase):
    def test_supported_when_all_planned_metrics_are_stable_positive(self) -> None:
        report = build_hypothesis_outcome_report(
            _idea(),
            _plan(["success_rate"]),
            _statistics([_comparison("success_rate", 0.2, "candidate_better", ci_low=0.1, ci_high=0.3)]),
            {"status": "pass"},
            {"status": "pass"},
            {"decision": "proceed_to_paper"},
            execution_mode="local",
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["outcome"], "supported")
        self.assertGreater(report["support_score"], 0.9)

    def test_smoke_only_when_execution_is_simulated(self) -> None:
        report = build_hypothesis_outcome_report(
            _idea(),
            _plan(["success_rate"]),
            _statistics([_comparison("success_rate", 0.2, "candidate_better", ci_low=0.1, ci_high=0.3)]),
            {"status": "pass"},
            {"status": "warn"},
            {"decision": "benchmark_upgrade"},
            execution_mode="simulated",
        )

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["outcome"], "smoke_only")
        self.assertTrue(any("smoke" in item.lower() or "模拟" in item for item in report["claim_boundaries"]))

    def test_blocks_when_hypothesis_has_no_statistical_comparisons(self) -> None:
        report = build_hypothesis_outcome_report(
            _idea(),
            _plan(["success_rate"]),
            _statistics([]),
            {"status": "block"},
            {"status": "block"},
            {"decision": "repair_before_writing"},
            execution_mode="local",
        )
        rendered = render_hypothesis_outcome_markdown(report)

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["outcome"], "blocked_unverified")
        self.assertIn("假设结果审计", rendered)

    def test_write_hypothesis_outcome_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_hypothesis_outcome_artifacts(
                _idea(),
                _plan(["success_rate"]),
                _statistics([_comparison("success_rate", -0.2, "baseline_better_or_equal", ci_low=-0.3, ci_high=-0.1)]),
                {"status": "pass"},
                {"status": "warn", "negative_metrics": [{"metric": "success_rate"}]},
                {"decision": "pivot_or_refine"},
                run_dir,
                execution_mode="benchmark",
            )

            self.assertEqual(report["outcome"], "refuted_or_negative")
            self.assertTrue((run_dir / "04-hypothesis-outcome.json").exists())
            self.assertTrue((run_dir / "04-hypothesis-outcome.md").exists())


def _idea() -> ResearchIdea:
    return ResearchIdea(
        title="机械臂路径规划验证",
        hypothesis="候选规划器能在成功率上优于 RRT*。",
        mechanism="固定场景和 seed 后比较 candidate 与 baseline。",
        expected_contribution="提供可复现实验验证。",
        novelty=5,
        feasibility=6,
        risk=2,
        evaluation=["success_rate"],
        baseline="RRT*",
    )


def _plan(metrics: list[str]) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="机械臂路径规划验证",
        objective="验证候选规划器是否优于 baseline。",
        variables=["planner"],
        metrics=metrics,
        protocol=["运行 candidate/baseline", "统计比较"],
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


def _comparison(metric: str, delta: float, direction: str, ci_low: float, ci_high: float) -> MetricComparison:
    return MetricComparison(
        metric=metric,
        candidate_mean=1.0,
        baseline_mean=1.0 - delta,
        delta=delta,
        ci_low=ci_low,
        ci_high=ci_high,
        candidate_std=0.1,
        baseline_std=0.1,
        effect_size=0.5,
        direction=direction,
        interpretation="test comparison",
    )


if __name__ == "__main__":
    unittest.main()
