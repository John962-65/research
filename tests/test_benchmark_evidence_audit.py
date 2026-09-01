from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.benchmark_evidence_audit import (
    BENCHMARK_EVIDENCE_AUDIT_JSON,
    BENCHMARK_EVIDENCE_AUDIT_MD,
    build_benchmark_evidence_audit_report,
    render_benchmark_evidence_audit_markdown,
    write_benchmark_evidence_audit_artifacts,
)
from research_agent.config import PaperGradeConfig
from research_agent.experiment_decision import build_experiment_decision_report
from research_agent.models import ExperimentCommand, ExperimentPlan, ExperimentResult, MetricComparison, StatisticsReport


class BenchmarkEvidenceAuditTest(unittest.TestCase):
    def test_marks_simulated_results_as_smoke_only(self) -> None:
        report = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _statistics(),
            {"status": "pass"},
            _runbook(mode="simulated"),
            execution_mode="simulated",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
        )
        rendered = render_benchmark_evidence_audit_markdown(report)

        self.assertEqual(report["status"], "smoke_only")
        self.assertEqual(report["evidence_grade"], "smoke_only")
        self.assertIn("Benchmark 证据审计", rendered)

    def test_passes_ready_benchmark_adapter_evidence(self) -> None:
        report = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _statistics(),
            {"status": "pass"},
            _runbook(mode="benchmark"),
            execution_mode="benchmark",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
            adapter_report={"status": "ready", "paper_grade_status": "ready", "paper_grade_issues": [], "commands": [{"name": "candidate"}]},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["evidence_grade"], "real_benchmark")
        self.assertEqual(report["claim_policy"], "conservative_benchmark_claims_allowed")
        self.assertEqual(report["adapter_paper_grade_status"], "ready")

    def test_repeat_warning_uses_paper_grade_threshold(self) -> None:
        report = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _statistics(),
            {"status": "pass"},
            _runbook(mode="benchmark"),
            execution_mode="benchmark",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
            adapter_report={"status": "ready", "paper_grade_status": "ready", "paper_grade_issues": [], "commands": [{"name": "candidate"}]},
            paper_grade=PaperGradeConfig(enabled=True, min_execution_repeats=5),
        )

        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["min_execution_repeats"], 5)
        self.assertTrue(any("repeats=3 < 5" in item for item in report["warnings"]))

    def test_marks_neutral_real_benchmark_as_publishable_with_no_superiority_claims(self) -> None:
        report = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _neutral_statistics(),
            {
                "status": "warn",
                "warnings": ["所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽；当前 repeat 未观察到差异，不能据此声明优势或稳定性。"],
                "items": [
                    {"name": "statistical_comparability", "status": "warn", "detail": "所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽；当前 repeat 未观察到差异，不能据此声明优势或稳定性。"}
                ],
            },
            _runbook(mode="benchmark"),
            execution_mode="benchmark",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
            adapter_report={"status": "ready", "paper_grade_status": "ready", "paper_grade_issues": [], "commands": [{"name": "candidate"}]},
        )
        rendered = render_benchmark_evidence_audit_markdown(report)

        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["evidence_grade"], "real_benchmark")
        self.assertEqual(report["statistical_outcome"], "neutral_no_observed_difference")
        self.assertEqual(report["claim_boundary_severity"], "negative_or_neutral_no_superiority")
        self.assertTrue(report["publishable_negative_or_neutral_result"])
        self.assertEqual(report["claim_policy"], "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims")
        self.assertTrue(any("负/中性" in item for item in report["required_actions"]))
        self.assertIn("可发表负/中性结果：是", rendered)

    def test_downgrades_ready_adapter_without_paper_grade_manifest_set(self) -> None:
        report = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _statistics(),
            {"status": "pass"},
            _runbook(mode="benchmark"),
            execution_mode="benchmark",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
            adapter_report={
                "status": "ready",
                "paper_grade_status": "review_required",
                "paper_grade_issues": ["paper-grade benchmark 需要 candidate/baseline/ablation 三类 role：baseline, ablation"],
                "paper_grade_repair_suggestions": [{"kind": "missing_manifest_role", "role": "baseline", "target": "role:baseline"}],
                "commands": [{"name": "candidate"}],
            },
        )

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["evidence_grade"], "local_experiment")
        self.assertEqual(report["claim_policy"], "preliminary_local_evidence_requires_manual_benchmark_context")
        self.assertEqual(report["adapter_paper_grade_repair_suggestions"][0]["role"], "baseline")
        self.assertTrue(any("paper-grade benchmark" in item for item in report["manual_tasks"]))
        self.assertTrue(any("paper-grade benchmark manifest" in item for item in report["required_actions"]))

    def test_blocks_benchmark_mode_without_ready_adapter(self) -> None:
        report = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _statistics(),
            {"status": "pass"},
            _runbook(mode="benchmark"),
            execution_mode="benchmark",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
            adapter_report={"status": "blocked", "blocking_issues": ["manifest missing"]},
        )

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["evidence_grade"], "blocked")
        self.assertTrue(report["blocking_issues"])

    def test_experiment_decision_uses_benchmark_evidence_boundaries(self) -> None:
        evidence = build_benchmark_evidence_audit_report(
            _plan(),
            _results(),
            _statistics(),
            {"status": "pass"},
            _runbook(mode="simulated"),
            execution_mode="simulated",
            benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
        )
        decision = build_experiment_decision_report(
            _plan(),
            _statistics(),
            {"status": "pass"},
            {"status": "pass", "summary": {"failed_runs": 0, "negative_metrics": 0, "uncertain_metrics": 0}},
            execution_mode="simulated",
            benchmark_evidence=evidence,
        )

        self.assertEqual(decision["decision"], "benchmark_upgrade")
        self.assertTrue(any("smoke_only" in item for item in decision["claim_boundaries"]))

    def test_writes_benchmark_evidence_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_benchmark_evidence_audit_artifacts(
                _plan(),
                _results(),
                _statistics(),
                {"status": "pass"},
                _runbook(mode="local"),
                run_dir,
                execution_mode="local",
                benchmark_plan={"selected_names": ["OMPL Benchmark"], "required_actions": []},
            )

            self.assertEqual(report["evidence_grade"], "local_experiment")
            self.assertTrue((run_dir / BENCHMARK_EVIDENCE_AUDIT_JSON).exists())
            self.assertTrue((run_dir / BENCHMARK_EVIDENCE_AUDIT_MD).exists())


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="机械臂路径规划验证",
        objective="验证候选规划器。",
        variables=["planner"],
        metrics=["success_rate", "planning_time"],
        protocol=["构建任务", "运行 candidate/baseline/ablation", "统计指标"],
        commands=[
            ExperimentCommand("candidate", ["python3", "run.py"], ["candidate_metrics.json"]),
            ExperimentCommand("baseline", ["python3", "run.py"], ["baseline_metrics.json"]),
            ExperimentCommand("ablation", ["python3", "run.py"], ["ablation_metrics.json"]),
        ],
        baseline="RRT*",
    )


def _results() -> list[ExperimentResult]:
    return [
        ExperimentResult("candidate", "passed", {"success_rate": 0.9, "planning_time": 1.0}, ["candidate_metrics.json"], repeat_index=0),
        ExperimentResult("baseline", "passed", {"success_rate": 0.8, "planning_time": 1.2}, ["baseline_metrics.json"], repeat_index=0),
        ExperimentResult("ablation", "passed", {"success_rate": 0.84, "planning_time": 1.1}, ["ablation_metrics.json"], repeat_index=0),
    ]


def _statistics() -> StatisticsReport:
    return StatisticsReport(
        idea_title="机械臂路径规划验证",
        repeats=3,
        candidate_name="candidate",
        baseline_name="baseline",
        comparisons=[
            MetricComparison("success_rate", 0.9, 0.8, 0.1, 0.02, 0.18, 0.01, 0.01, 1.0, "candidate_better", "ok"),
            MetricComparison("planning_time", 1.0, 1.2, -0.2, -0.3, -0.1, 0.01, 0.01, 1.0, "candidate_better", "ok"),
        ],
        warnings=[],
    )


def _neutral_statistics() -> StatisticsReport:
    return StatisticsReport(
        idea_title="机械臂路径规划验证",
        repeats=3,
        candidate_name="candidate",
        baseline_name="baseline",
        comparisons=[
            MetricComparison("success_rate", 0.8, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, None, "baseline_better_or_equal", "candidate 与 baseline 数值相同。"),
            MetricComparison("planning_time", 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, "baseline_better_or_equal", "candidate 与 baseline 数值相同。"),
        ],
        warnings=[],
    )


def _runbook(mode: str) -> dict[str, object]:
    return {
        "execution": {"mode": mode, "repeats": 3},
        "environment": {"source_tree": {"aggregate_sha256": "abc", "file_count": 3}},
        "runs": [
            {"name": "candidate", "produced_artifacts": [{"path": "candidate_metrics.json", "sha256": "1"}]},
            {"name": "baseline", "produced_artifacts": [{"path": "baseline_metrics.json", "sha256": "2"}]},
            {"name": "ablation", "produced_artifacts": [{"path": "ablation_metrics.json", "sha256": "3"}]},
        ],
    }


if __name__ == "__main__":
    unittest.main()
