from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.analysis import analysis_matches_execution_mode, analyze_results
from research_agent.config import ExecutionConfig
from research_agent.experiments import run_experiments
from research_agent.models import ExperimentCommand, ExperimentPlan, ExperimentResult
from research_agent.statistics import build_statistics_report, render_statistics_markdown, write_statistics_figure_artifacts


class StatisticsTest(unittest.TestCase):
    def test_repeated_simulated_experiments_build_statistics_report(self) -> None:
        plan = ExperimentPlan(
            idea_title="机械臂避障 benchmark",
            objective="验证 candidate 是否优于 baseline。",
            variables=["方法条件", "障碍复杂度"],
            metrics=["success_rate", "collision_rate"],
            protocol=["构建任务", "运行 baseline", "运行 candidate"],
            commands=[
                ExperimentCommand(name="simulate_artifact_pipeline", command=["python3", "simulate.py", "--mode", "artifact"]),
                ExperimentCommand(name="simulate_baseline_pipeline", command=["python3", "simulate.py", "--mode", "baseline"]),
            ],
        )
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            results = run_experiments(plan, ExecutionConfig(mode="simulated", repeats=4), out)
            report = build_statistics_report(plan, results)
            analysis = analyze_results(results, report)
            rendered = render_statistics_markdown(report)
            figure = write_statistics_figure_artifacts(out, report)

            self.assertEqual(len(results), 8)
            self.assertEqual(report.repeats, 4)
            self.assertTrue(report.comparisons)
            self.assertEqual(report.multiplicity["status"], "pass")
            self.assertEqual(report.multiplicity["family_size"], len(report.comparisons))
            self.assertEqual(report.power_analysis["status"], "profile_ready")
            self.assertEqual(report.power_analysis["per_group_repeats"], 4)
            self.assertIsNotNone(report.power_analysis["minimum_detectable_standardized_effect"])
            self.assertEqual(figure["status"], "ok")
            self.assertIn("95% CI", rendered)
            self.assertIn("统计设计", rendered)
            self.assertIn("多重比较策略", rendered)
            self.assertIn("近似 MDE", rendered)
            self.assertIn("repeat_index", (out / "04-results.csv").read_text(encoding="utf-8"))
            self.assertIn("<svg", (out / "04-statistics-figure.svg").read_text(encoding="utf-8"))
            self.assertIn("candidate - baseline", (out / "04-statistics-figure.json").read_text(encoding="utf-8"))
            self.assertIn("95% CI", analysis.findings[0])
            self.assertTrue(any("模拟数据" in item for item in analysis.limitations))

    def test_benchmark_analysis_does_not_claim_simulated_data(self) -> None:
        plan = ExperimentPlan(
            idea_title="Iris benchmark",
            objective="比较真实 benchmark adapter。",
            variables=["method"],
            metrics=["accuracy"],
            protocol=["run candidate and baseline"],
            commands=[
                ExperimentCommand(name="candidate_adapter", command=["python3", "grade.py"]),
                ExperimentCommand(name="baseline_adapter", command=["python3", "grade.py"]),
            ],
        )
        results = [
            ExperimentResult("candidate_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/candidate/metrics.json"], repeat_index=0, seed="seed-0"),
            ExperimentResult("baseline_adapter", "passed", {"accuracy": 0.7}, ["benchmark-adapters/baseline/metrics.json"], repeat_index=0, seed="seed-0"),
        ]
        report = build_statistics_report(plan, results)
        analysis = analyze_results(results, report, execution_mode="benchmark")

        joined = "\n".join([*analysis.limitations, *analysis.next_steps])
        self.assertNotIn("模拟数据", joined)
        self.assertIn("真实 benchmark adapter", analysis.limitations[0])
        self.assertTrue(analysis_matches_execution_mode(analysis, "benchmark"))
        self.assertFalse(analysis_matches_execution_mode(analysis, "simulated"))

    def test_zero_width_equal_ci_uses_equal_value_wording(self) -> None:
        plan = ExperimentPlan(
            idea_title="Iris benchmark",
            objective="比较真实 benchmark adapter。",
            variables=["method"],
            metrics=["accuracy"],
            protocol=["run candidate and baseline"],
            commands=[
                ExperimentCommand(name="candidate_adapter", command=["python3", "grade.py"], role="candidate"),
                ExperimentCommand(name="baseline_adapter", command=["python3", "grade.py"], role="baseline"),
            ],
        )
        results = [
            ExperimentResult("candidate_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/candidate/metrics.json"], repeat_index=0, seed="seed-0"),
            ExperimentResult("candidate_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/candidate/metrics.json"], repeat_index=1, seed="seed-1"),
            ExperimentResult("candidate_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/candidate/metrics.json"], repeat_index=2, seed="seed-2"),
            ExperimentResult("baseline_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/baseline/metrics.json"], repeat_index=0, seed="seed-0"),
            ExperimentResult("baseline_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/baseline/metrics.json"], repeat_index=1, seed="seed-1"),
            ExperimentResult("baseline_adapter", "passed", {"accuracy": 0.9}, ["benchmark-adapters/baseline/metrics.json"], repeat_index=2, seed="seed-2"),
        ]

        report = build_statistics_report(plan, results)
        rendered = render_statistics_markdown(report)

        self.assertIn("数值相同", report.comparisons[0].interpretation)
        self.assertNotIn("差异跨过 0", rendered)

    def test_failed_result_with_metrics_is_not_statistical_evidence(self) -> None:
        plan = _paired_plan()
        results = [
            ExperimentResult("candidate", "failed", {"accuracy": 0.99}, [], repeat_index=0, seed="seed-0", adapter_id="candidate-a"),
            ExperimentResult("baseline", "passed", {"accuracy": 0.50}, [], repeat_index=0, seed="seed-0", adapter_id="baseline-a"),
        ]

        report = build_statistics_report(plan, results)

        self.assertEqual(report.repeats, 0)
        self.assertEqual(report.comparisons, [])
        self.assertTrue(any("failed" in warning for warning in report.warnings))

    def test_missing_seed_and_empty_metrics_are_not_counted_as_pairs(self) -> None:
        plan = _paired_plan()
        missing_seed = [
            ExperimentResult("candidate", "passed", {"accuracy": 0.9}, [], repeat_index=0, adapter_id="candidate-a"),
            ExperimentResult("baseline", "passed", {"accuracy": 0.7}, [], repeat_index=0, adapter_id="baseline-a"),
        ]
        empty_metrics = [
            ExperimentResult("candidate", "passed", {}, [], repeat_index=0, seed="seed-0", adapter_id="candidate-a"),
            ExperimentResult("baseline", "passed", {}, [], repeat_index=0, seed="seed-0", adapter_id="baseline-a"),
        ]

        missing_seed_report = build_statistics_report(plan, missing_seed)
        empty_metrics_report = build_statistics_report(plan, empty_metrics)

        self.assertEqual(missing_seed_report.repeats, 0)
        self.assertTrue(any("缺少 candidate/baseline seed" in warning for warning in missing_seed_report.warnings))
        self.assertEqual(empty_metrics_report.repeats, 0)
        self.assertTrue(any("共同有限数值指标" in warning for warning in empty_metrics_report.warnings))

    def test_same_role_multiple_adapter_ids_are_not_pooled(self) -> None:
        plan = _paired_plan()
        results = [
            ExperimentResult("candidate", "passed", {"accuracy": 0.9}, [], repeat_index=0, seed="seed-0", adapter_id="candidate-a"),
            ExperimentResult("candidate", "passed", {"accuracy": 0.8}, [], repeat_index=1, seed="seed-1", adapter_id="candidate-b"),
            ExperimentResult("baseline", "passed", {"accuracy": 0.7}, [], repeat_index=0, seed="seed-0", adapter_id="baseline-a"),
            ExperimentResult("baseline", "passed", {"accuracy": 0.7}, [], repeat_index=1, seed="seed-1", adapter_id="baseline-a"),
        ]

        report = build_statistics_report(plan, results)

        self.assertEqual(report.repeats, 0)
        self.assertEqual(report.comparisons, [])
        self.assertTrue(any("多个 adapter" in warning for warning in report.warnings))


def _paired_plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="paired audit",
        objective="only compare valid paired evidence",
        variables=["method"],
        metrics=["accuracy"],
        protocol=["run"],
        commands=[
            ExperimentCommand(name="candidate", command=["python3", "candidate.py"], role="candidate", comparison_group="task-a"),
            ExperimentCommand(name="baseline", command=["python3", "baseline.py"], role="baseline", comparison_group="task-a"),
        ],
    )


if __name__ == "__main__":
    unittest.main()
