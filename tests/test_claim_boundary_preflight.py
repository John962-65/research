from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.claim_boundary_preflight import (
    build_claim_boundary_preflight_report,
    render_claim_boundary_preflight_markdown,
    write_claim_boundary_preflight_artifacts,
)
from research_agent.models import Analysis, ExperimentCommand, ExperimentPlan, MetricComparison, StatisticsReport


class ClaimBoundaryPreflightTest(unittest.TestCase):
    def test_passes_real_benchmark_supported_hypothesis(self) -> None:
        report = build_claim_boundary_preflight_report(
            "机械臂路径规划",
            _plan(),
            _statistics([_comparison("success_rate", 0.2, "candidate_better")]),
            _analysis(),
            {"status": "pass"},
            {"status": "pass", "summary": {"failed_runs": 0}},
            {"status": "pass", "evidence_grade": "real_benchmark", "claim_policy": "conservative_benchmark_claims_allowed"},
            {"status": "pass", "decision": "proceed_to_paper", "paper_policy": "conservative_claims_allowed", "downstream_writing_allowed": True},
            {"status": "pass", "outcome": "supported", "support_score": 0.9},
            execution_mode="benchmark",
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["writing_mode"], "conservative_paper")
        self.assertFalse(report["blocking_issues"])

    def test_smoke_evidence_requires_limited_claims(self) -> None:
        report = build_claim_boundary_preflight_report(
            "机械臂路径规划",
            _plan(),
            _statistics([_comparison("success_rate", 0.2, "candidate_better")]),
            _analysis(),
            {"status": "pass"},
            {"status": "pass", "summary": {"simulated_runs": 3}},
            {"status": "smoke_only", "evidence_grade": "smoke_only", "claim_policy": "smoke_test_only_no_scientific_main_claim"},
            {"status": "warn", "decision": "benchmark_upgrade", "paper_policy": "smoke_test_only_until_real_benchmark"},
            {"status": "review_required", "outcome": "smoke_only", "support_score": 0.4},
            execution_mode="simulated",
        )
        rendered = render_claim_boundary_preflight_markdown(report)

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["writing_mode"], "smoke_limited_paper")
        self.assertTrue(any("smoke" in item.lower() for item in report["required_boundary_statements"]))
        self.assertIn("Claim Boundary Preflight", rendered)

    def test_blocks_repair_before_writing(self) -> None:
        report = build_claim_boundary_preflight_report(
            "机械臂路径规划",
            _plan(),
            _statistics([]),
            _analysis(),
            {"status": "block", "blocking_issues": ["candidate 与 baseline 没有共同指标"]},
            {"status": "block", "blocking_issues": ["失败运行未修复"], "claim_boundaries": ["当前结果不得用于主张有效。"]},
            {"status": "block", "evidence_grade": "blocked"},
            {"status": "block", "decision": "repair_before_writing", "downstream_writing_allowed": False},
            {"status": "block", "outcome": "blocked_unverified", "support_score": 0.0},
            execution_mode="local",
        )

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["writing_mode"], "repair_report_only")
        self.assertGreaterEqual(len(report["blocking_issues"]), 3)
        self.assertTrue(any("不得写成方法有效性" in item for item in report["required_boundary_statements"]))

    def test_write_claim_boundary_preflight_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_claim_boundary_preflight_artifacts(
                "机械臂路径规划",
                _plan(),
                _statistics([_comparison("success_rate", 0.2, "candidate_better")]),
                _analysis(),
                {"status": "pass"},
                {"status": "pass", "summary": {}},
                {"status": "pass", "evidence_grade": "real_benchmark"},
                {"status": "pass", "decision": "proceed_to_paper"},
                {"status": "pass", "outcome": "supported", "support_score": 1.0},
                run_dir,
                execution_mode="benchmark",
            )
            saved = json.loads((run_dir / "04-claim-boundary-preflight.json").read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(saved["writing_mode"], "conservative_paper")
            self.assertTrue((run_dir / "04-claim-boundary-preflight.md").exists())


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="机械臂路径规划验证",
        objective="验证候选规划器。",
        variables=["planner"],
        metrics=["success_rate", "planning_time"],
        protocol=["运行 candidate", "运行 baseline", "统计指标"],
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
        ci_low=delta - 0.05,
        ci_high=delta + 0.05,
        candidate_std=0.1,
        baseline_std=0.1,
        effect_size=0.5,
        direction=direction,
        interpretation="test",
    )


def _analysis() -> Analysis:
    return Analysis(
        headline="候选方案在当前任务中更好。",
        metric_table=[{"name": "success_rate", "candidate": 0.8, "baseline": 0.6}],
        findings=["候选成功率更高。"],
        limitations=["样本量有限。"],
        next_steps=["扩大 benchmark。"],
    )


if __name__ == "__main__":
    unittest.main()
