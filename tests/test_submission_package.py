from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from research_agent.artifacts import write_json, write_text
from research_agent.models import SubmissionPackageFile
from research_agent.submission_package import _safe_package_arcname, _write_zip, write_submission_package_artifacts


class SubmissionPackageTest(unittest.TestCase):
    def test_submission_package_collects_required_artifacts_and_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_required_artifacts(run_dir)

            report = write_submission_package_artifacts("投稿包测试", run_dir)

            self.assertEqual(report.status, "needs_human_submission_review")
            self.assertTrue((run_dir / "11-submission-package.md").exists())
            self.assertTrue((run_dir / "11-submission-package.json").exists())
            self.assertTrue((run_dir / "11-submission-package.zip").exists())
            self.assertTrue((run_dir / "submission-package" / "README.md").exists())
            self.assertTrue((run_dir / "submission-package" / "CHECKLIST.md").exists())
            self.assertTrue(any(item.package_path == "submission-package/paper/revised-paper.tex" for item in report.files))
            self.assertFalse(report.blocking_issues)
            self.assertTrue(report.manual_tasks)
            with zipfile.ZipFile(run_dir / "11-submission-package.zip") as archive:
                names = set(archive.namelist())
            self.assertIn("submission-package/README.md", names)
            self.assertIn("submission-package/paper/revised-paper.md", names)
            self.assertIn("submission-package/provenance/prior-run-lessons.md", names)
            self.assertIn("submission-package/provenance/open-source-lessons.md", names)
            self.assertIn("submission-package/references/references.bib", names)
            self.assertIn("submission-package/audits/literature-rerank.md", names)
            self.assertIn("submission-package/audits/query-execution-audit.md", names)
            self.assertIn("submission-package/audits/literature-rescue-plan.md", names)
            self.assertIn("submission-package/audits/literature-evidence-mix.md", names)
            self.assertIn("submission-package/audits/literature-metadata-audit.md", names)
            self.assertIn("submission-package/audits/idea-audit.md", names)
            self.assertIn("submission-package/audits/repair-queue.md", names)
            self.assertIn("submission-package/audits/repair-resolution-audit.md", names)
            self.assertIn("submission-package/audits/agent-stage-contract.md", names)
            self.assertIn("submission-package/audits/agent-trajectory.md", names)
            self.assertIn("submission-package/audits/llm-trace-audit.md", names)
            self.assertIn("submission-package/audits/run-economics-audit.md", names)
            self.assertIn("submission-package/audits/agent-observability-audit.md", names)
            self.assertIn("submission-package/audits/run-integrity-audit.md", names)
            self.assertIn("submission-package/audits/run-integrity-audit.json", names)
            self.assertIn("submission-package/audits/ai-disclosure.md", names)
            self.assertIn("submission-package/reproducibility/review-constraint-compliance.md", names)
            self.assertIn("submission-package/reproducibility/idea-experiment-contract.md", names)
            self.assertIn("submission-package/audits/claim-traceability.md", names)
            self.assertIn("submission-package/audits/agent-claim-audit.md", names)
            self.assertIn("submission-package/audits/agent-deliberation.md", names)
            self.assertIn("submission-package/audits/citation-grounding.md", names)
            self.assertIn("submission-package/audits/citation-coverage.md", names)
            self.assertIn("submission-package/audits/results-presentation.md", names)
            self.assertIn("submission-package/results/failure-analysis.md", names)
            self.assertIn("submission-package/results/benchmark-result-schema-audit.md", names)
            self.assertIn("submission-package/results/benchmark-evidence-audit.md", names)
            self.assertIn("submission-package/results/experiment-decision.md", names)
            self.assertIn("submission-package/results/hypothesis-outcome.md", names)
            self.assertIn("submission-package/audits/claim-boundary-preflight.md", names)
            self.assertIn("submission-package/audits/revision-response-audit.md", names)
            self.assertIn("submission-package/reproducibility/benchmark-readiness.md", names)
            self.assertIn("submission-package/reproducibility/environment-snapshot.md", names)
            self.assertIn("submission-package/provenance/llm-ledger.md", names)

    def test_submission_package_arcname_guard_rejects_unsafe_paths(self) -> None:
        self.assertEqual(_safe_package_arcname("submission-package/audits/report.json"), "submission-package/audits/report.json")
        unsafe_paths = [
            "",
            "README.md",
            "/submission-package/audits/report.json",
            "C:/submission-package/audits/report.json",
            "submission-package/../private.txt",
            "submission-package/./report.txt",
            "submission-package//report.txt",
            "submission-package/",
            "submission-package\\audits\\report.json",
        ]
        for unsafe_path in unsafe_paths:
            with self.subTest(unsafe_path=unsafe_path):
                self.assertEqual(_safe_package_arcname(unsafe_path), "")

    def test_submission_package_zip_writer_errors_on_unsafe_file_records(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            package_dir = run_dir / "submission-package"
            package_dir.mkdir()
            record = SubmissionPackageFile("", "submission-package/../private.txt", "pass", 1, "abc", True, "")

            zip_record = _write_zip(run_dir, package_dir, [record])

        self.assertEqual(zip_record.status, "error")
        self.assertIn("Unsafe package path", zip_record.note)

    def test_submission_package_reviews_repair_queue_status_without_block_items(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_required_artifacts(run_dir)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 1, "block": 0, "high": 1, "medium": 0},
                    "items": [],
                    "blocking_issues": [],
                    "manual_tasks": ["人工确认 high 任务是否接受风险。"],
                },
            )

            report = write_submission_package_artifacts("投稿包测试", run_dir)

            self.assertEqual(report.status, "needs_human_submission_review")
            self.assertFalse(report.blocking_issues)
            self.assertTrue(any("block 计数为 0" in item for item in report.manual_tasks))


def _write_required_artifacts(run_dir: Path) -> None:
    write_text(run_dir / "09-revised-paper.md", "# 修订稿\n\n## 摘要\n文本")
    write_text(run_dir / "09-revised-paper.tex", "\\documentclass{article}\n\\title{Demo}\n\\begin{document}\n\\end{document}")
    write_text(run_dir / "00-prior-run-lessons.md", "# Prior Run Lessons")
    write_json(run_dir / "00-prior-run-lessons.json", {"status": "pass", "lessons": [], "agent_prompt_text": "无"})
    write_text(run_dir / "00-open-source-lessons.md", "# Open-Source Project Lessons")
    write_json(run_dir / "00-open-source-lessons.json", {"status": "constraints_ready", "profiles": [], "lessons": [], "agent_prompt_text": "无"})
    write_text(run_dir / "01-references.bib", "@article{demo, title={Demo}}")
    write_text(run_dir / "01-references.ris", "TY  - JOUR")
    write_text(run_dir / "01-literature-rerank.md", "# 文献候选重排")
    write_json(run_dir / "01-literature-rerank.json", {"status": "pass", "items": []})
    write_text(run_dir / "01-query-execution-audit.md", "# Query Execution Audit")
    write_json(run_dir / "01-query-execution-audit.json", {"status": "pass", "selected_query_count": 3})
    write_text(run_dir / "01-literature-rescue-plan.md", "# 文献补检索计划")
    write_json(run_dir / "01-literature-rescue-plan.json", {"status": "pass", "rescue_queries": []})
    write_text(run_dir / "01-literature-evidence-mix.md", "# 文献证据组合审计")
    write_json(run_dir / "01-literature-evidence-mix.json", {"status": "pass", "mix_score": 0.9, "blocking_issues": [], "warnings": [], "required_actions": []})
    write_text(run_dir / "01-literature-metadata-audit.md", "# 文献 Metadata 审计")
    write_json(run_dir / "01-literature-metadata-audit.json", {"status": "pass", "blocked": 0, "review_required": 0})
    write_text(run_dir / "02-idea-audit.md", "# Idea 证据与约束审计")
    write_json(run_dir / "02-idea-audit.json", {"status": "pass", "blocked": 0, "review_required": 0})
    write_text(run_dir / "12-repair-queue.md", "# 修复队列")
    write_json(
        run_dir / "12-repair-queue.json",
        {"status": "pass", "summary": {"total": 0, "block": 0, "high": 0, "medium": 0}, "items": [], "blocking_issues": [], "manual_tasks": []},
    )
    write_text(run_dir / "12-repair-resolution-audit.md", "# 修复闭环审计")
    write_json(run_dir / "12-repair-resolution-audit.json", {"status": "not_applicable", "resolution_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_text(run_dir / "13-agent-stage-contract.md", "# Agent Stage Contract Audit")
    write_json(run_dir / "13-agent-stage-contract.json", {"status": "pass", "score": 1.0, "checks": []})
    write_text(run_dir / "13-agent-trajectory.md", "# Agent Trajectory")
    write_json(run_dir / "13-agent-trajectory.json", {"status": "pass", "phases": [], "timeline": []})
    write_text(run_dir / "13-llm-trace-audit.md", "# LLM Trace Audit")
    write_json(
        run_dir / "13-llm-trace-audit.json",
        {"status": "pass", "coverage": {"coverage_ratio": 1.0}, "blocking_issues": [], "warnings": [], "manual_tasks": []},
    )
    write_text(run_dir / "13-agent-observability-audit.md", "# Agent Observability Audit")
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_text(run_dir / "13-run-economics-audit.md", "# Run Economics Audit")
    write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_text(run_dir / "14-run-integrity-audit.md", "# Run Integrity Audit")
    write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"checks": 12, "pass": 12, "warn": 0, "block": 0}, "blocking_issues": [], "warnings": []})
    write_text(run_dir / "03-review-constraint-compliance.md", "# 人工审核约束落实审计")
    write_json(run_dir / "03-review-constraint-compliance.json", {"status": "pass", "blocked": 0, "review_required": 0})
    write_text(run_dir / "03-idea-experiment-contract.md", "# Idea-实验契约")
    write_json(run_dir / "03-idea-experiment-contract.json", {"status": "pass", "contract_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_text(run_dir / "04-results.csv", "metric,value\nsuccess,1\n")
    write_json(run_dir / "04-results.json", [{"name": "candidate", "status": "passed", "metrics": {"success": 1.0}, "artifacts": []}])
    write_text(run_dir / "04-statistics.md", "# 统计")
    write_json(run_dir / "04-statistics.json", {"repeats": 1, "comparisons": [], "warnings": []})
    write_text(run_dir / "04-failure-analysis.md", "# 失败/负结果分析")
    write_json(run_dir / "04-failure-analysis.json", {"status": "pass", "required_actions": []})
    write_text(run_dir / "04-benchmark-result-schema-audit.md", "# Benchmark Result Schema Audit")
    write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_text(run_dir / "04-benchmark-evidence-audit.md", "# Benchmark 证据审计")
    write_json(run_dir / "04-benchmark-evidence-audit.json", {"status": "pass", "evidence_grade": "real_benchmark"})
    write_text(run_dir / "04-experiment-decision.md", "# 实验后决策")
    write_json(run_dir / "04-experiment-decision.json", {"status": "pass", "decision": "proceed_to_paper", "next_actions": []})
    write_text(run_dir / "04-hypothesis-outcome.md", "# 假设结果审计")
    write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 1.0, "next_actions": []})
    write_text(run_dir / "04-claim-boundary-preflight.md", "# Claim Boundary Preflight")
    write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "pass", "writing_mode": "conservative_paper", "blocking_issues": [], "warnings": []})
    write_text(run_dir / "09-revision-response-audit.md", "# Revision Response Audit")
    write_json(run_dir / "09-revision-response-audit.json", {"status": "pass", "response_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_text(run_dir / "03-benchmark-readiness.md", "# Benchmark Readiness Audit")
    write_json(run_dir / "03-benchmark-readiness.json", {"status": "ready_for_benchmark", "blocking_issues": [], "manual_tasks": []})
    write_text(run_dir / "04-experiment-runbook.md", "# Runbook")
    write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "simulate"}, "artifacts": []})
    write_text(run_dir / "04-environment-snapshot.md", "# 实验环境快照")
    write_json(run_dir / "04-environment-snapshot.json", {"status": "complete", "source_tree": {"file_count": 1}})
    write_text(run_dir / "10-release-metadata.md", "# Release Metadata")
    write_json(
        run_dir / "10-release-metadata.json",
        {"status": "needs_release_metadata", "manual_tasks": ["补归档 DOI"], "blocking_issues": []},
    )
    write_text(run_dir / "10-code-data-availability.md", "# 代码和数据可用性审计")
    write_json(
        run_dir / "10-code-data-availability.json",
        {"status": "needs_human_release_metadata", "manual_tasks": ["补许可证"], "blocking_issues": []},
    )
    write_text(run_dir / "10-submission-check.md", "# 投稿格式检查")
    write_json(
        run_dir / "10-submission-check.json",
        {"status": "needs_human_format_check", "manual_tasks": ["换模板"], "blocking_issues": []},
    )
    write_text(run_dir / "10-ai-disclosure.md", "# AI 使用披露")
    write_json(
        run_dir / "10-ai-disclosure.json",
        {"status": "needs_human_policy_check", "used_ai": True, "total_llm_calls": 1, "manual_tasks": ["确认 AI policy"]},
    )
    write_text(run_dir / "10-claim-traceability.md", "# Claim Traceability")
    write_json(
        run_dir / "10-claim-traceability.json",
        {"status": "pass", "traceability_score": 1.0, "blocking_issues": [], "manual_tasks": [], "items": []},
    )
    write_text(run_dir / "10-agent-claim-audit.md", "# 多智能体 Claim 审计")
    write_json(
        run_dir / "10-agent-claim-audit.json",
        {"status": "pass", "claim_owner_summary": {"total_claims": 0, "mapped_claims": 0, "orphaned_claims": 0}, "blocking_issues": [], "manual_tasks": []},
    )
    write_text(run_dir / "10-agent-deliberation.md", "# 多智能体 Deliberation")
    write_json(
        run_dir / "10-agent-deliberation.json",
        {"status": "pass", "consensus": {"decision": "approve"}, "agent_verdicts": [], "blocking_issues": [], "manual_tasks": []},
    )
    write_text(run_dir / "10-citation-grounding.md", "# Citation Grounding")
    write_json(
        run_dir / "10-citation-grounding.json",
        {"status": "pass", "grounding_score": 1.0, "blocking_issues": [], "manual_tasks": [], "items": []},
    )
    write_text(run_dir / "10-citation-coverage.md", "# Citation Coverage Audit")
    write_json(run_dir / "10-citation-coverage.json", {"status": "pass", "coverage_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_text(run_dir / "10-results-presentation.md", "# Results Presentation Audit")
    write_json(
        run_dir / "10-results-presentation.json",
        {"status": "pass", "presentation_score": 1.0, "blocking_issues": [], "manual_tasks": [], "checks": []},
    )
    write_text(run_dir / "10-final-readiness.md", "# 最终就绪报告")
    write_json(
        run_dir / "10-final-readiness.json",
        {"status": "ready_for_human_polish", "next_actions": ["人工润色"], "blocking_issues": []},
    )
    write_text(run_dir / "run-manifest.md", "# Run Manifest")
    write_json(run_dir / "run-manifest.json", {"status": "running", "artifacts": []})
    write_text(run_dir / "run-llm-ledger.md", "# LLM 调用账本")
    write_json(run_dir / "run-llm-ledger.json", {"total_calls": 1, "successful_calls": 1, "failed_calls": 0, "entries": []})


if __name__ == "__main__":
    unittest.main()
