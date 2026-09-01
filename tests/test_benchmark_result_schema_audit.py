from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.benchmark_result_schema_audit import (
    BENCHMARK_RESULT_SCHEMA_AUDIT_JSON,
    BENCHMARK_RESULT_SCHEMA_AUDIT_MD,
    build_benchmark_result_schema_audit_report,
    render_benchmark_result_schema_audit_markdown,
    write_benchmark_result_schema_audit_artifacts,
)
from research_agent.models import ExperimentCommand, ExperimentPlan, ExperimentResult, MetricComparison, StatisticsReport


class BenchmarkResultSchemaAuditTest(unittest.TestCase):
    def test_passes_complete_benchmark_schema_contract(self) -> None:
        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=_adapter_report(),
            result_validation={"status": "pass"},
        )
        rendered = render_benchmark_result_schema_audit_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["blocking_issues"])
        self.assertIn("Benchmark Result Schema Audit", rendered)
        self.assertIn("Adapter Provenance", rendered)
        self.assertIn("Benchmark Execution Contract", rendered)
        self.assertEqual(report["role_summary"]["candidate"]["results"], 1)
        self.assertEqual(report["adapter_provenance"]["candidate"]["license"], "BSD-3-Clause")
        self.assertEqual(report["adapter_execution_contract"]["candidate"]["expected_metrics"], ["success_rate", "planning_time"])
        self.assertTrue(any(check["name"] == "adapter_role_command_contract" and check["status"] == "pass" for check in report["checks"]))

    def test_blocks_missing_benchmark_expected_artifact(self) -> None:
        runbook = _runbook(mode="benchmark")
        runbook["runs"][0]["produced_artifacts"] = []

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            runbook,
            benchmark_plan=_benchmark_plan(),
            adapter_report=_adapter_report(),
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("artifact contract" in issue for issue in report["blocking_issues"]))

    def test_accepts_command_bound_repeat_artifact_snapshots(self) -> None:
        runbook = _runbook(mode="benchmark")
        for run in runbook["runs"]:
            name = run["name"]
            expected = next(item["expected_artifacts"][0] for item in runbook["commands"] if item["name"] == name)
            run["produced_artifacts"] = [
                {
                    "path": f"experiments/repeat-artifacts/{name}/repeat-001/{expected}",
                    "sha256": "a" * 64,
                }
            ]

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            runbook,
            benchmark_plan=_benchmark_plan(),
            adapter_report=_adapter_report(),
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["blocking_issues"])

    def test_repeat_artifact_snapshot_must_match_command_and_repeat(self) -> None:
        runbook = _runbook(mode="benchmark")
        runbook["runs"][0]["produced_artifacts"] = [
            {
                "path": "experiments/repeat-artifacts/baseline/repeat-002/benchmark-adapters/candidate/metrics.json",
                "sha256": "a" * 64,
            }
        ]

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            runbook,
            benchmark_plan=_benchmark_plan(),
            adapter_report=_adapter_report(),
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("artifact contract" in issue for issue in report["blocking_issues"]))

    def test_requires_review_when_benchmark_metrics_do_not_align(self) -> None:
        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="local"),
            benchmark_plan={
                "selected_names": ["External"],
                "candidates": [{"name": "External", "expected_metrics": ["map_score"]}],
            },
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "review_required")
        self.assertTrue(any("expected_metrics" in item for item in report["manual_tasks"]))

    def test_blocks_missing_adapter_provenance_in_benchmark_mode(self) -> None:
        adapter = _adapter_report()
        for item in adapter["adapters"]:
            item.pop("dataset_url", None)
            item.pop("benchmark_url", None)
            item.pop("license", None)
            item.pop("baseline_version", None)
            item.pop("citation", None)

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=adapter,
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("provenance" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any(check["name"] == "adapter_provenance_contract" and check["status"] == "block" for check in report["checks"]))

    def test_blocks_procedural_adapter_provenance_in_benchmark_mode(self) -> None:
        adapter = _adapter_report()
        for item in adapter["adapters"]:
            item["benchmark_kind"] = "fixture"
            item["dataset_url"] = "procedural://research-agent/test-scenes"
            item["provenance_status"] = "review_required"
            item["provenance_issues"] = [
                f"{item['name']}: benchmark_kind=fixture 不是公开外部 benchmark",
                f"{item['name']}: paper-grade formal benchmark 需要公开 http(s) dataset_url，当前 procedural://research-agent/test-scenes",
            ]

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=adapter,
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("公开外部 benchmark" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any(check["name"] == "adapter_provenance_contract" and check["status"] == "block" for check in report["checks"]))

    def test_blocks_missing_benchmark_execution_contract_in_benchmark_mode(self) -> None:
        adapter = _adapter_report()
        for item in adapter["adapters"]:
            item.pop("expected_metrics", None)
            item.pop("grader", None)
            item.pop("submission_path", None)
            item.pop("seed_policy", None)
            item.pop("min_repeats", None)

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=adapter,
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("execution contract" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any(check["name"] == "benchmark_execution_contract" and check["status"] == "block" for check in report["checks"]))

    def test_blocks_when_configured_repeats_are_below_manifest_min_repeats(self) -> None:
        adapter = _adapter_report()
        for item in adapter["adapters"]:
            item["min_repeats"] = 5

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=adapter,
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("repeats 1 < min_repeats 5" in issue for issue in report["blocking_issues"]))

    def test_blocks_adapter_role_commands_that_only_change_outputs(self) -> None:
        adapter = _adapter_report()
        for item in adapter["adapters"]:
            item["role_command_signature"] = "python3 grade.py --metrics <output>"

        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=adapter,
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("重复 role command" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any(check["name"] == "adapter_role_command_contract" and check["status"] == "block" for check in report["checks"]))

    def test_single_benchmark_adapter_without_role_matrix_requires_review_not_repair_block(self) -> None:
        plan = ExperimentPlan(
            idea_title="single adapter schema",
            objective="validate one benchmark adapter execution",
            variables=["adapter"],
            metrics=["success_rate", "runtime_cost"],
            protocol=["run adapter"],
            commands=[
                ExperimentCommand(
                    "toy-benchmark-adapter",
                    ["python3", "run_benchmark.py"],
                    ["benchmark-adapters/toy-benchmark-adapter/metrics.json"],
                )
            ],
            baseline="RRT*",
        )
        results = [
            ExperimentResult(
                "toy-benchmark-adapter",
                "passed",
                {"success_rate": 0.82, "runtime_cost": 1.5},
                ["benchmark-adapters/toy-benchmark-adapter/metrics.json"],
                repeat_index=0,
            )
        ]
        statistics = StatisticsReport(
            idea_title="single adapter schema",
            repeats=1,
            candidate_name="",
            baseline_name="",
            comparisons=[],
            warnings=["没有 candidate-baseline 统计比较。"],
        )

        report = build_benchmark_result_schema_audit_report(
            plan,
            results,
            statistics,
            _single_adapter_runbook(),
            benchmark_plan={"selected_names": ["Toy"], "candidates": [{"name": "Toy", "expected_metrics": ["success_rate", "runtime_cost"]}]},
            adapter_report=_single_adapter_report(),
            result_validation={"status": "warn"},
        )

        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(any("角色矩阵" in item for item in report["manual_tasks"]))
        self.assertTrue(any(check["name"] == "result_validation_link" and check["status"] == "review_required" for check in report["checks"]))

    def test_statistical_result_warning_does_not_force_schema_review(self) -> None:
        report = build_benchmark_result_schema_audit_report(
            _plan(),
            _results(),
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=_adapter_report(),
            result_validation={
                "status": "warn",
                "warnings": ["所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽；当前 repeat 未观察到差异，不能据此声明优势或稳定性。"],
                "items": [
                    {
                        "name": "statistical_comparability",
                        "status": "warn",
                        "detail": "所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽。",
                    }
                ],
            },
        )

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["manual_tasks"])
        link = next(check for check in report["checks"] if check["name"] == "result_validation_link")
        self.assertEqual(link["status"], "pass")
        self.assertIn("非 schema", link["evidence"])

    def test_descriptive_confusion_metrics_do_not_require_statistical_comparisons(self) -> None:
        plan = _plan()
        results = [
            ExperimentResult(
                "candidate",
                "passed",
                {"success_rate": 0.9, "planning_time": 1.0, "cm_setosa_setosa": 10.0, "train_cases": 120.0},
                ["benchmark-adapters/candidate/metrics.json"],
                repeat_index=0,
            ),
            ExperimentResult(
                "baseline",
                "passed",
                {"success_rate": 0.8, "planning_time": 1.2, "cm_setosa_setosa": 10.0, "train_cases": 120.0},
                ["benchmark-adapters/baseline/metrics.json"],
                repeat_index=0,
            ),
            ExperimentResult(
                "ablation",
                "passed",
                {"success_rate": 0.84, "planning_time": 1.1, "cm_setosa_setosa": 10.0, "train_cases": 120.0},
                ["benchmark-adapters/ablation/metrics.json"],
                repeat_index=0,
            ),
        ]

        report = build_benchmark_result_schema_audit_report(
            plan,
            results,
            _statistics(),
            _runbook(mode="benchmark"),
            benchmark_plan=_benchmark_plan(),
            adapter_report=_adapter_report(),
            result_validation={"status": "pass"},
        )

        self.assertEqual(report["status"], "pass")
        coverage = next(check for check in report["checks"] if check["name"] == "statistics_metric_coverage")
        self.assertEqual(coverage["status"], "pass")
        self.assertIn("descriptive metrics", coverage["evidence"])

    def test_writes_benchmark_result_schema_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_benchmark_result_schema_audit_artifacts(
                _plan(),
                _results(),
                _statistics(),
                _runbook(mode="benchmark"),
                run_dir,
                benchmark_plan=_benchmark_plan(),
                adapter_report=_adapter_report(),
                result_validation={"status": "pass"},
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / BENCHMARK_RESULT_SCHEMA_AUDIT_JSON).exists())
            self.assertTrue((run_dir / BENCHMARK_RESULT_SCHEMA_AUDIT_MD).exists())


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="机械臂路径规划 schema",
        objective="验证 schema contract。",
        variables=["planner"],
        metrics=["success_rate", "planning_time"],
        protocol=["run candidate", "run baseline", "run ablation"],
        commands=[
            ExperimentCommand("candidate", ["python3", "run.py"], ["benchmark-adapters/candidate/metrics.json"]),
            ExperimentCommand("baseline", ["python3", "run.py"], ["benchmark-adapters/baseline/metrics.json"]),
            ExperimentCommand("ablation", ["python3", "run.py"], ["benchmark-adapters/ablation/metrics.json"]),
        ],
        baseline="RRT*",
    )


def _results() -> list[ExperimentResult]:
    return [
        ExperimentResult("candidate", "passed", {"success_rate": 0.9, "planning_time": 1.0}, ["benchmark-adapters/candidate/metrics.json"], repeat_index=0),
        ExperimentResult("baseline", "passed", {"success_rate": 0.8, "planning_time": 1.2}, ["benchmark-adapters/baseline/metrics.json"], repeat_index=0),
        ExperimentResult("ablation", "passed", {"success_rate": 0.84, "planning_time": 1.1}, ["benchmark-adapters/ablation/metrics.json"], repeat_index=0),
    ]


def _statistics() -> StatisticsReport:
    return StatisticsReport(
        idea_title="机械臂路径规划 schema",
        repeats=1,
        candidate_name="candidate",
        baseline_name="baseline",
        comparisons=[
            MetricComparison("success_rate", 0.9, 0.8, 0.1, 0.02, 0.18, 0.01, 0.01, 1.0, "candidate_better", "ok"),
            MetricComparison("planning_time", 1.0, 1.2, -0.2, -0.3, -0.1, 0.01, 0.01, 1.0, "candidate_better", "ok"),
        ],
        warnings=[],
    )


def _benchmark_plan() -> dict[str, object]:
    return {
        "selected_names": ["OMPL Benchmark"],
        "candidates": [{"name": "OMPL Benchmark", "expected_metrics": ["planning_success_rate", "planning_time"]}],
    }


def _adapter_report() -> dict[str, object]:
    return {
        "status": "ready",
        "paper_grade_status": "ready",
        "adapters": [
            _adapter("candidate", "candidate-method", "v2"),
            _adapter("baseline", "RRT*", "ompl-1.6.0"),
            _adapter("ablation", "candidate-without-map", "v2"),
        ],
    }


def _adapter(name: str, baseline: str, version: str) -> dict[str, object]:
    return {
        "name": name,
        "role": name,
        "status": "ready",
        "role_command_signature": f"python3 grade.py --method {name}",
        "metrics_path": f"benchmark-adapters/{name}/metrics.json",
        "expected_artifacts": [f"benchmark-adapters/{name}/metrics.json"],
        "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
        "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
        "dataset_version": "ompl-1.6.0",
        "split_name": "official schema split",
        "split_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "license": "BSD-3-Clause",
        "baseline": baseline,
        "baseline_version": version,
        "citation": "10.1109/MRA.2012.2205651",
        "expected_metrics": ["success_rate", "planning_time"],
        "metric_schema": {
            "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
            "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
        },
        "grader": f"benchmark-adapters/{name}/grade.py",
        "grader_version": f"{name}-grader-v1",
        "grader_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        "submission_path": f"benchmark-adapters/{name}/submission.csv",
        "seed_policy": "RESEARCH_AGENT_SEED controls deterministic benchmark split",
        "min_repeats": 1,
    }


def _runbook(mode: str) -> dict[str, object]:
    commands = [
        {"name": "candidate", "expected_artifacts": ["benchmark-adapters/candidate/metrics.json"]},
        {"name": "baseline", "expected_artifacts": ["benchmark-adapters/baseline/metrics.json"]},
        {"name": "ablation", "expected_artifacts": ["benchmark-adapters/ablation/metrics.json"]},
    ]
    runs = [
        {"name": "candidate", "repeat_index": 0, "produced_artifacts": [{"path": "experiments/benchmark-adapters/candidate/metrics.json", "sha256": "1"}]},
        {"name": "baseline", "repeat_index": 0, "produced_artifacts": [{"path": "experiments/benchmark-adapters/baseline/metrics.json", "sha256": "2"}]},
        {"name": "ablation", "repeat_index": 0, "produced_artifacts": [{"path": "experiments/benchmark-adapters/ablation/metrics.json", "sha256": "3"}]},
    ]
    return {"execution": {"mode": mode, "repeats": 1}, "commands": commands, "runs": runs}


def _single_adapter_report() -> dict[str, object]:
    return {
        "status": "ready",
        "adapters": [
            {
                "name": "toy-benchmark-adapter",
                "status": "ready",
                "metrics_path": "benchmark-adapters/toy-benchmark-adapter/metrics.json",
                "expected_artifacts": ["benchmark-adapters/toy-benchmark-adapter/metrics.json"],
                "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                "dataset_version": "ompl-1.6.0",
                "split_name": "single adapter split",
                "split_sha256": "9999999999999999999999999999999999999999999999999999999999999999",
                "license": "BSD-3-Clause",
                "baseline": "RRT*",
                "baseline_version": "ompl-1.6.0-smoke",
                "citation": "10.1109/MRA.2012.2205651",
                "expected_metrics": ["success_rate", "runtime_cost"],
                "metric_schema": {
                    "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                    "runtime_cost": {"direction": "lower_is_better", "unit": "seconds", "description": "Runtime cost."},
                },
                "grader": "benchmark-adapters/toy-benchmark-adapter/run_benchmark.py",
                "grader_version": "single-grader-v1",
                "grader_sha256": "9999999999999999999999999999999999999999999999999999999999999999",
                "submission_path": "benchmark-adapters/toy-benchmark-adapter/submission.csv",
                "seed_policy": "RESEARCH_AGENT_SEED controls deterministic repeats",
                "min_repeats": 1,
            }
        ],
    }


def _single_adapter_runbook() -> dict[str, object]:
    return {
        "execution": {"mode": "benchmark", "repeats": 1},
        "commands": [
            {
                "name": "toy-benchmark-adapter",
                "expected_artifacts": ["benchmark-adapters/toy-benchmark-adapter/metrics.json"],
            }
        ],
        "runs": [
            {
                "name": "toy-benchmark-adapter",
                "repeat_index": 0,
                "produced_artifacts": [{"path": "experiments/benchmark-adapters/toy-benchmark-adapter/metrics.json", "sha256": "abc"}],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
