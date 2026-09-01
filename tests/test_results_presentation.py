from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.results_presentation import build_results_presentation_report, render_results_presentation_markdown, write_results_presentation_artifacts


class ResultsPresentationTest(unittest.TestCase):
    def test_results_presentation_passes_when_paper_reports_metric_figure_and_ci(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_result_artifacts(run_dir)
            write_text(
                run_dir / "09-revised-paper.md",
                "# Demo\n\n## 结果\n\n### 指标表\n统计图 04-statistics-figure.svg 显示 candidate 相对 baseline 的 reproduction_success_rate 均值差值为 0.200，95% CI=[0.100, 0.300]。",
            )

            report = write_results_presentation_artifacts("结果呈现", run_dir)
            rendered = render_results_presentation_markdown(report)

            self.assertEqual(report.status, "pass")
            self.assertFalse(report.blocking_issues)
            self.assertTrue((run_dir / "10-results-presentation.json").exists())
            self.assertIn("Results Presentation Audit", rendered)

    def test_results_presentation_blocks_when_metrics_are_missing_from_results_section(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_result_artifacts(run_dir)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n统计图显示 candidate 优于 baseline，但正文没有报告具体指标或 CI。")

            report = build_results_presentation_report("结果呈现", run_dir)

            self.assertEqual(report.status, "block")
            self.assertTrue(any("统计指标" in issue for issue in report.blocking_issues))

    def test_results_presentation_reviews_uncertain_ci_without_uncertainty_text(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_result_artifacts(run_dir, ci_low=-0.1, ci_high=0.3)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n统计图显示 candidate 相对 baseline 的 reproduction_success_rate 均值差值为 0.100。")

            report = build_results_presentation_report("结果呈现", run_dir)

            self.assertEqual(report.status, "review_required")
            self.assertTrue(any("不确定性" in task or "CI" in task for task in report.manual_tasks))

    def test_results_presentation_blocks_comparative_claims_without_comparisons(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "04-statistics-figure.svg", "<svg></svg>")
            write_json(run_dir / "04-statistics.json", {"comparisons": []})
            write_json(run_dir / "04-statistics-figure.json", {"status": "no_comparisons", "comparisons": []})
            write_json(run_dir / "05-analysis.json", {"metric_table": [{"name": "candidate", "status": "passed", "success": 1.0}]})
            write_json(run_dir / "04-results.json", [{"name": "candidate", "status": "passed", "metrics": {"success": 1.0}}])
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\nsuccess 指标显示 candidate 优于 baseline。")

            report = build_results_presentation_report("结果呈现", run_dir)

            self.assertEqual(report.status, "block")
            self.assertTrue(any("比较性结果主张" in issue for issue in report.blocking_issues))


def _write_result_artifacts(run_dir: Path, ci_low: float = 0.1, ci_high: float = 0.3) -> None:
    write_text(run_dir / "04-statistics-figure.svg", "<svg></svg>")
    comparison = {
        "metric": "reproduction_success_rate",
        "candidate_mean": 0.8,
        "baseline_mean": 0.6,
        "delta": 0.2,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "direction": "candidate_better",
        "ci_crosses_zero": ci_low <= 0 <= ci_high,
    }
    write_json(run_dir / "04-statistics.json", {"comparisons": [comparison], "repeats": 3})
    write_json(run_dir / "04-statistics-figure.json", {"status": "ok", "comparisons": [comparison]})
    write_json(run_dir / "05-analysis.json", {"metric_table": [{"name": "candidate", "status": "passed", "reproduction_success_rate": 0.8}]})
    write_json(run_dir / "04-results.json", [{"name": "candidate", "status": "passed", "metrics": {"reproduction_success_rate": 0.8}}])


if __name__ == "__main__":
    unittest.main()
