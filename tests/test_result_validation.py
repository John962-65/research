from __future__ import annotations

import unittest

from research_agent.models import ExperimentCommand, ExperimentPlan, ExperimentResult
from research_agent.preregistration import plan_fingerprint
from research_agent.result_validation import build_result_validation_report, render_result_validation_markdown
from research_agent.statistics import build_statistics_report


class ResultValidationTest(unittest.TestCase):
    def test_validation_passes_complete_candidate_baseline_results(self) -> None:
        plan = _plan()
        results = [
            _result("candidate", 0, {"success_rate": 0.8, "runtime_cost": 0.3}),
            _result("baseline", 0, {"success_rate": 0.7, "runtime_cost": 0.4}),
            _result("ablation", 0, {"success_rate": 0.74, "runtime_cost": 0.36}),
            _result("candidate", 1, {"success_rate": 0.82, "runtime_cost": 0.31}),
            _result("baseline", 1, {"success_rate": 0.69, "runtime_cost": 0.42}),
            _result("ablation", 1, {"success_rate": 0.75, "runtime_cost": 0.35}),
            _result("candidate", 2, {"success_rate": 0.84, "runtime_cost": 0.29}),
            _result("baseline", 2, {"success_rate": 0.68, "runtime_cost": 0.43}),
            _result("ablation", 2, {"success_rate": 0.76, "runtime_cost": 0.34}),
        ]
        statistics = build_statistics_report(plan, results)

        report = build_result_validation_report(plan, results, statistics, expected_repeats=3, preregistration=_preregistration(plan))
        rendered = render_result_validation_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["blocking_issues"])
        self.assertIn("实验结果有效性验证", rendered)

    def test_validation_blocks_failed_and_missing_metric_results(self) -> None:
        plan = _plan()
        results = [
            _result("candidate", 0, {"success_rate": 0.8}),
            _result("baseline", 0, {"success_rate": 0.7, "runtime_cost": 0.4}),
            ExperimentResult(name="candidate", status="timeout", metrics={}, artifacts=[], repeat_index=1),
        ]
        statistics = build_statistics_report(plan, results)

        report = build_result_validation_report(plan, results, statistics, expected_repeats=2, preregistration=_preregistration(plan))

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("timeout" in item for item in report["blocking_issues"]))
        self.assertTrue(any("runtime_cost" in item for item in report["blocking_issues"]))

    def test_validation_blocks_preregistration_fingerprint_drift(self) -> None:
        plan = _plan()
        results = [
            _result("candidate", 0, {"success_rate": 0.8, "runtime_cost": 0.3}),
            _result("baseline", 0, {"success_rate": 0.7, "runtime_cost": 0.4}),
            _result("ablation", 0, {"success_rate": 0.74, "runtime_cost": 0.36}),
        ]
        statistics = build_statistics_report(plan, results)
        preregistration = _preregistration(plan)
        preregistration["plan_fingerprint"] = "changed"

        report = build_result_validation_report(plan, results, statistics, expected_repeats=1, preregistration=preregistration)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("plan_fingerprint" in item for item in report["blocking_issues"]))

    def test_validation_blocks_missing_ablation_command(self) -> None:
        plan = ExperimentPlan(
            idea_title="validation test",
            objective="validate result checks",
            variables=["method"],
            metrics=["success_rate"],
            protocol=["run candidate", "run baseline", "compare"],
            commands=[
                ExperimentCommand(name="candidate", command=["python3", "simulate.py"]),
                ExperimentCommand(name="baseline", command=["python3", "simulate.py"]),
            ],
        )
        results = [
            _result("candidate", 0, {"success_rate": 0.8}),
            _result("baseline", 0, {"success_rate": 0.7}),
        ]
        statistics = build_statistics_report(plan, results)

        report = build_result_validation_report(plan, results, statistics, expected_repeats=1, preregistration=_preregistration(plan))

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("ablation" in item for item in report["blocking_issues"]))

    def test_benchmark_adapter_without_comparison_warns_instead_of_blocking_execution_validity(self) -> None:
        plan = ExperimentPlan(
            idea_title="benchmark adapter validation",
            objective="validate a single external benchmark adapter",
            variables=["adapter"],
            metrics=["success_rate", "runtime_cost"],
            protocol=["run benchmark adapter"],
            commands=[
                ExperimentCommand(
                    name="toy-benchmark-adapter",
                    command=["python3", "run_benchmark.py"],
                    expected_artifacts=["benchmark-adapters/toy/metrics.json"],
                )
            ],
        )
        results = [_result("toy-benchmark-adapter", 0, {"success_rate": 0.82, "runtime_cost": 1.5})]
        statistics = build_statistics_report(plan, results)

        report = build_result_validation_report(
            plan,
            results,
            statistics,
            expected_repeats=1,
            preregistration=_preregistration(plan),
            execution_mode="benchmark",
        )

        self.assertEqual(report["status"], "warn")
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(any("ablation" in item for item in report["warnings"]))
        self.assertTrue(any("candidate 与 baseline" in item for item in report["warnings"]))

    def test_benchmark_adapter_fingerprint_drift_warns_for_manifest_execution_contract(self) -> None:
        original_plan = _plan()
        adapter_plan = ExperimentPlan(
            idea_title=original_plan.idea_title,
            objective=original_plan.objective,
            variables=original_plan.variables,
            metrics=["success_rate", "runtime_cost"],
            protocol=original_plan.protocol,
            commands=[
                ExperimentCommand(
                    name="toy-benchmark-adapter",
                    command=["python3", "run_benchmark.py"],
                    expected_artifacts=["benchmark-adapters/toy/metrics.json"],
                )
            ],
        )
        results = [_result("toy-benchmark-adapter", 0, {"success_rate": 0.82, "runtime_cost": 1.5})]
        statistics = build_statistics_report(adapter_plan, results)

        report = build_result_validation_report(
            adapter_plan,
            results,
            statistics,
            expected_repeats=1,
            preregistration=_preregistration(original_plan),
            execution_mode="benchmark",
        )

        self.assertEqual(report["status"], "warn")
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(any("manifest" in item for item in report["warnings"]))


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="validation test",
        objective="validate result checks",
        variables=["method"],
        metrics=["success_rate", "runtime_cost"],
        protocol=["run candidate", "run baseline", "compare"],
        commands=[
            ExperimentCommand(name="candidate", command=["python3", "simulate.py"]),
            ExperimentCommand(name="baseline", command=["python3", "simulate.py"]),
            ExperimentCommand(name="ablation", command=["python3", "simulate.py"]),
        ],
    )


def _result(name: str, repeat: int, metrics: dict[str, float]) -> ExperimentResult:
    return ExperimentResult(
        name=name,
        status="passed",
        metrics=metrics,
        artifacts=["metrics.json"],
        repeat_index=repeat,
        seed=f"seed-{repeat}",
    )


def _preregistration(plan: ExperimentPlan) -> dict[str, object]:
    return {
        "status": "locked",
        "plan_fingerprint": plan_fingerprint(plan),
        "primary_metrics": plan.metrics[:2],
        "blocking_issues": [],
        "warnings": [],
    }


if __name__ == "__main__":
    unittest.main()
