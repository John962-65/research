from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.failure_analysis import (
    FAILURE_ANALYSIS_JSON,
    FAILURE_ANALYSIS_MD,
    build_failure_analysis_report,
    render_failure_analysis_markdown,
    write_failure_analysis_artifacts,
)
from research_agent.models import ExperimentCommand, ExperimentPlan, ExperimentResult, MetricComparison, StatisticsReport
from research_agent.statistics import build_statistics_report


class FailureAnalysisTest(unittest.TestCase):
    def test_failure_analysis_passes_clean_positive_results(self) -> None:
        plan = _plan()
        results = [
            _result("candidate", 0, {"success_rate": 0.9, "runtime_cost": 0.30}),
            _result("baseline", 0, {"success_rate": 0.7, "runtime_cost": 0.40}),
            _result("candidate", 1, {"success_rate": 0.9, "runtime_cost": 0.30}),
            _result("baseline", 1, {"success_rate": 0.7, "runtime_cost": 0.40}),
            _result("candidate", 2, {"success_rate": 0.9, "runtime_cost": 0.30}),
            _result("baseline", 2, {"success_rate": 0.7, "runtime_cost": 0.40}),
        ]
        statistics = build_statistics_report(plan, results)

        report = build_failure_analysis_report(plan, results, statistics, {"status": "pass", "blocking_issues": [], "warnings": []})
        rendered = render_failure_analysis_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["failed_runs"], 0)
        self.assertFalse(report["negative_metrics"])
        self.assertIn("失败/负结果分析", rendered)

    def test_failure_analysis_warns_on_negative_or_uncertain_metrics(self) -> None:
        plan = _plan()
        statistics = StatisticsReport(
            idea_title=plan.idea_title,
            repeats=3,
            candidate_name="candidate",
            baseline_name="baseline",
            comparisons=[
                MetricComparison(
                    metric="success_rate",
                    candidate_mean=0.72,
                    baseline_mean=0.75,
                    delta=-0.03,
                    ci_low=-0.10,
                    ci_high=0.04,
                    candidate_std=0.03,
                    baseline_std=0.02,
                    effect_size=-1.0,
                    direction="baseline_better_or_equal",
                    interpretation="差异跨过 0，需要更多重复实验确认。",
                )
            ],
            warnings=[],
        )

        report = build_failure_analysis_report(plan, [], statistics, {"status": "pass", "blocking_issues": [], "warnings": []})

        self.assertEqual(report["status"], "warn")
        self.assertTrue(report["negative_metrics"])
        self.assertTrue(report["uncertain_metrics"])
        self.assertTrue(any("不得写成整体优于 baseline" in item for item in report["required_actions"]))
        self.assertTrue(any("增加重复次数" in item for item in report["required_actions"]))

    def test_failure_analysis_blocks_failed_runs_or_validation_block(self) -> None:
        plan = _plan()
        results = [
            ExperimentResult(
                name="candidate",
                status="timeout",
                metrics={},
                artifacts=[],
                stderr="命令超过 1s 超时限制，已终止。",
                repeat_index=0,
                seed="abc",
                command=["python3", "slow.py"],
            )
        ]
        statistics = StatisticsReport(plan.idea_title, 0, "", "", [], [])
        validation = {"status": "block", "blocking_issues": ["存在失败/阻断/超时结果：candidate:timeout"], "warnings": []}

        with TemporaryDirectory() as tmp:
            report = write_failure_analysis_artifacts(plan, results, statistics, validation, Path(tmp))
            saved = json.loads((Path(tmp) / FAILURE_ANALYSIS_JSON).read_text(encoding="utf-8"))
            rendered = (Path(tmp) / FAILURE_ANALYSIS_MD).read_text(encoding="utf-8")

        self.assertEqual(report["status"], "block")
        self.assertEqual(saved["status"], "block")
        self.assertEqual(report["failure_modes"]["bad_by_command_family"]["candidate"], 1)
        self.assertTrue(any("先修复 04-result-validation" in item for item in report["required_actions"]))
        self.assertIn("不得用于主张候选方法有效", rendered)


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="failure analysis test",
        objective="validate failure analysis",
        variables=["method"],
        metrics=["success_rate", "runtime_cost"],
        protocol=["run candidate", "run baseline", "compare"],
        commands=[
            ExperimentCommand(name="candidate", command=["python3", "simulate.py"]),
            ExperimentCommand(name="baseline", command=["python3", "simulate.py"]),
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


if __name__ == "__main__":
    unittest.main()
