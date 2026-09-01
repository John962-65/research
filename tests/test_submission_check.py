from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.config import PaperConfig
from research_agent.submission_check import build_submission_check_report, render_submission_check_markdown


class SubmissionCheckTest(unittest.TestCase):
    def test_submission_check_reports_manual_template_and_release_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(
                run_dir / "09-revised-paper.md",
                "# 标题\n\n## 摘要\n文本。\n\n## 方法\n文本。\n\n## 结果\n文本。\n\n## 局限性\n文本。\n\n## 结论\n文本。\n\n## 代码和数据可用性\n待补公开仓库。",
            )
            write_text(run_dir / "09-revised-paper.tex", "\\documentclass{ctexart}\n\\title{Demo}\n\\begin{document}\n\\end{document}")
            write_text(run_dir / "01-references.bib", "\n\n".join(f"@article{{demo{i}, title={{Demo}}}}" for i in range(5)))
            write_text(run_dir / "04-statistics-figure.svg", "<svg></svg>")
            write_json(
                run_dir / "10-code-data-availability.json",
                {"status": "needs_human_release_metadata", "manual_tasks": ["补许可证"], "blocking_issues": []},
            )
            write_json(run_dir / "run-llm-ledger.json", {"total_calls": 3, "successful_calls": 3, "failed_calls": 0, "entries": []})
            write_json(
                run_dir / "10-ai-disclosure.json",
                {
                    "status": "needs_human_policy_check",
                    "used_ai": True,
                    "total_llm_calls": 3,
                    "disclosure_statement": "This manuscript was prepared with assistance from an automated research-agent workflow.",
                },
            )
            write_json(run_dir / "04-failure-analysis.json", {"status": "warn", "claim_boundaries": ["模拟结果只能作为工程烟测。"]})
            write_json(run_dir / "04-experiment-decision.json", {"status": "warn", "decision": "benchmark_upgrade", "claim_boundaries": ["当前结果只能作为 smoke test。"]})
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "smoke_only", "support_score": 0.4})
            write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "review_required", "writing_mode": "smoke_limited_paper", "risk_score": 0.7, "warnings": ["smoke 证据"], "blocking_issues": []})
            write_json(run_dir / "09-revision-response-audit.json", {"status": "review_required", "response_score": 0.8, "blocking_issues": [], "manual_tasks": ["R01 仍需人工补证"], "summary": {"missing_results": 0, "missing_paper_traces": 0}})
            write_json(run_dir / "10-citation-grounding.json", {"status": "review_required", "total_citations": 1, "grounding_score": 0.5, "blocked_citations": 0, "review_citations": 1})
            write_json(run_dir / "10-citation-coverage.json", {"status": "review_required", "coverage_score": 0.6, "context_coverage_ratio": 0.4, "unique_cited_keys": 2, "context_citations": 5, "blocking_issues": [], "manual_tasks": ["补核心文献"]})
            write_json(run_dir / "10-results-presentation.json", {"status": "review_required", "presentation_score": 0.8, "blocking_issues": [], "manual_tasks": ["补图表引用"], "evidence_inventory": {"metrics": 2, "matched_metrics": 1, "comparisons": 2}})
            write_json(run_dir / "10-claim-consistency.json", {"status": "review_required", "consistency_score": 0.8, "blocking_issues": [], "manual_tasks": ["补结果边界"], "evidence_inventory": {"outcome": "smoke_only", "strong_positive_claims": 0}})

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="ieee"))
            rendered = render_submission_check_markdown(report)

            self.assertEqual(report.status, "needs_human_format_check")
            self.assertTrue(any(item.item == "目标模板" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "代码/数据可用性" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "AI 使用披露" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "正文 citation key" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "Citation grounding 审计" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "Citation coverage 审计" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "结果呈现审计" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "Claim consistency 审计" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "结果边界" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "实验后决策" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "假设结果审计" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "Claim 边界预检" and item.status == "manual_required" for item in report.checks))
            self.assertTrue(any(item.item == "修订响应审计" and item.status == "manual_required" for item in report.checks))
            self.assertIn("投稿格式检查", rendered)
            self.assertTrue(report.manual_tasks)

    def test_submission_check_blocks_repair_before_writing_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(run_dir / "04-experiment-decision.json", {"status": "block", "decision": "repair_before_writing", "claim_boundaries": ["当前结果不得用于主张有效。"]})

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "实验后决策" and item.status == "block" for item in report.checks))

    def test_submission_check_accepts_pivot_decision_when_boundary_section_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(run_dir / "04-experiment-decision.json", {"status": "warn", "decision": "pivot_or_refine", "claim_boundaries": ["负结果必须作为发现报告。"]})

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertTrue(any(item.item == "实验后决策" and item.status == "pass" for item in report.checks))

    def test_submission_check_blocks_failed_results_presentation_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(
                run_dir / "10-results-presentation.json",
                {
                    "status": "block",
                    "presentation_score": 0.4,
                    "blocking_issues": ["统计指标呈现: 未报告核心指标。"],
                    "manual_tasks": [],
                    "evidence_inventory": {"metrics": 2, "matched_metrics": 0, "comparisons": 2},
                },
            )

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "结果呈现审计" and item.status == "block" for item in report.checks))

    def test_submission_check_blocks_failed_citation_coverage_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(
                run_dir / "10-citation-coverage.json",
                {
                    "status": "block",
                    "coverage_score": 0.1,
                    "context_coverage_ratio": 0.0,
                    "unique_cited_keys": 0,
                    "context_citations": 5,
                    "blocking_issues": ["修订稿没有可核对的 citation marker"],
                    "manual_tasks": [],
                },
            )

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "Citation coverage 审计" and item.status == "block" for item in report.checks))

    def test_submission_check_blocks_untested_hypothesis_outcome(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "block", "outcome": "untested", "support_score": 0.0})

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "假设结果审计" and item.status == "block" for item in report.checks))

    def test_submission_check_blocks_failed_claim_consistency_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(
                run_dir / "10-claim-consistency.json",
                {
                    "status": "block",
                    "consistency_score": 0.3,
                    "blocking_issues": ["过强正向结论: 删除或降级强正向结论。"],
                    "manual_tasks": [],
                    "evidence_inventory": {"outcome": "smoke_only", "strong_positive_claims": 2},
                },
            )

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "Claim consistency 审计" and item.status == "block" for item in report.checks))

    def test_submission_check_blocks_failed_claim_boundary_preflight(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {"status": "block", "writing_mode": "repair_report_only", "risk_score": 1.0, "blocking_issues": ["实验后决策不允许正常写作"], "warnings": []},
            )

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "Claim 边界预检" and item.status == "block" for item in report.checks))

    def test_submission_check_blocks_failed_revision_response_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_base_submission_fixture(run_dir, include_boundary=True)
            write_json(
                run_dir / "09-revision-response-audit.json",
                {"status": "block", "response_score": 0.3, "blocking_issues": ["R01 高优先级任务缺少正文痕迹"], "manual_tasks": [], "summary": {"missing_results": 0, "missing_paper_traces": 1}},
            )

            report = build_submission_check_report("投稿检查", run_dir, PaperConfig(target_venue="generic"))

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any(item.item == "修订响应审计" and item.status == "block" for item in report.checks))


def _write_base_submission_fixture(run_dir: Path, include_boundary: bool) -> None:
    boundary = "\n\n## 结果边界\n当前结果边界已按实验后决策收窄。" if include_boundary else ""
    write_text(
        run_dir / "09-revised-paper.md",
        "# 标题\n\n## 摘要\n文本。\n\n## 方法\n文本。\n\n## 结果\n文本。\n\n## 局限性\n文本。\n\n## 结论\n文本。\n\n## 代码和数据可用性\n待补公开仓库。" + boundary,
    )
    write_text(run_dir / "09-revised-paper.tex", "\\documentclass{article}\n\\title{Demo}\n\\begin{document}\n\\end{document}")
    write_text(run_dir / "01-references.bib", "\n\n".join(f"@article{{demo{i}, title={{Demo}}}}" for i in range(5)))
    write_text(run_dir / "04-statistics-figure.svg", "<svg></svg>")
    write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
    write_json(run_dir / "run-llm-ledger.json", {"total_calls": 0, "entries": []})
    write_json(run_dir / "10-ai-disclosure.json", {"status": "not_applicable", "used_ai": False, "disclosure_statement": ""})
    write_json(run_dir / "04-failure-analysis.json", {"status": "pass", "claim_boundaries": []})
    write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 1.0})
    write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "pass", "writing_mode": "conservative_paper", "risk_score": 0.1, "blocking_issues": [], "warnings": []})
    write_json(run_dir / "09-revision-response-audit.json", {"status": "pass", "response_score": 1.0, "blocking_issues": [], "manual_tasks": [], "summary": {"missing_results": 0, "missing_paper_traces": 0}})
    write_json(run_dir / "10-citation-grounding.json", {"status": "pass", "total_citations": 3, "grounding_score": 1.0, "blocked_citations": 0, "review_citations": 0})
    write_json(run_dir / "10-citation-coverage.json", {"status": "pass", "coverage_score": 1.0, "context_coverage_ratio": 1.0, "unique_cited_keys": 3, "context_citations": 3, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-results-presentation.json", {"status": "pass", "presentation_score": 1.0, "blocking_issues": [], "manual_tasks": [], "evidence_inventory": {"metrics": 1, "matched_metrics": 1, "comparisons": 1}})
    write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": [], "evidence_inventory": {"outcome": "supported", "strong_positive_claims": 1}})


if __name__ == "__main__":
    unittest.main()
