from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.models import PaperRewriteReport, PaperRevisionPlan, PaperRevisionTaskResult, RevisionTask
from research_agent.revision_response_audit import (
    REVISION_RESPONSE_AUDIT_JSON,
    REVISION_RESPONSE_AUDIT_MD,
    build_revision_response_audit_report,
    render_revision_response_audit_markdown,
    write_revision_response_audit_artifacts,
)


class RevisionResponseAuditTest(unittest.TestCase):
    def test_passes_when_every_revision_task_has_report_and_paper_trace(self) -> None:
        plan = _plan(
            [
                _task("R01", "medium", "Claim-Grounding", "weak claim 需要降级。"),
                _task("R02", "low", "Manuscript", "摘要需要说明局限。"),
            ]
        )
        rewrite = _rewrite_report(
            [
                _result("R01", "draft_adjusted"),
                _result("R02", "applied_in_draft"),
            ]
        )
        paper = "# 修订稿\n\n## 局限性\n结果边界已说明。\n\n## 修订执行记录\n### R01\n已降级。\n\n### R02\n已处理。"

        report = build_revision_response_audit_report("机械臂路径规划", plan, rewrite, paper)
        rendered = render_revision_response_audit_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["missing_results"], 0)
        self.assertEqual(report["summary"]["missing_paper_traces"], 0)
        self.assertIn("Revision Response Audit", rendered)

    def test_review_required_when_human_evidence_task_is_explicitly_carried(self) -> None:
        plan = _plan([_task("R01", "high", "Claim-Grounding", "unsupported claim 必须补证。")])
        rewrite = _rewrite_report([_result("R01", "needs_human_evidence")])
        paper = "# 修订稿\n\n## 局限性\n结果边界已说明。\n\n## 修订执行记录\n### R01\n处理状态：needs_human_evidence，待补证。"

        report = build_revision_response_audit_report("机械臂路径规划", plan, rewrite, paper)

        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(any("needs_human_evidence" in item for item in report["manual_tasks"]))

    def test_accepts_numbered_revision_record_heading(self) -> None:
        plan = _plan([_task("R01", "medium", "Manuscript", "摘要需要说明局限。")])
        rewrite = _rewrite_report([_result("R01", "applied_in_draft")])
        paper = "# 修订稿\n\n## 9. 修订执行记录\n### R01\n已处理。"

        report = build_revision_response_audit_report("机械臂路径规划", plan, rewrite, paper)

        self.assertTrue(report["summary"]["has_revision_log"])
        self.assertEqual(report["status"], "pass")

    def test_blocks_high_priority_task_missing_from_report_or_paper(self) -> None:
        plan = _plan([_task("R01", "high", "Claim-Grounding", "unsupported claim 必须补证。")])
        rewrite = _rewrite_report([])
        paper = "# 修订稿\n\n## 摘要\n没有修订执行记录。"

        report = build_revision_response_audit_report("机械臂路径规划", plan, rewrite, paper)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("缺少“修订执行记录”" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any("缺少处理结果" in issue for issue in report["blocking_issues"]))

    def test_write_revision_response_audit_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            plan = _plan([_task("R01", "low", "Manuscript", "补摘要。")])
            rewrite = _rewrite_report([_result("R01", "applied_in_draft")])
            paper = "# 修订稿\n\n## 修订执行记录\n### R01\n已处理。"

            report = write_revision_response_audit_artifacts("机械臂路径规划", plan, rewrite, paper, run_dir)
            saved = json.loads((run_dir / REVISION_RESPONSE_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(saved["response_score"], 1.0)
            self.assertTrue((run_dir / REVISION_RESPONSE_AUDIT_MD).exists())


def _task(task_id: str, severity: str, section: str, issue: str) -> RevisionTask:
    return RevisionTask(
        task_id=task_id,
        section=section,
        severity=severity,
        issue=issue,
        action="按审稿意见处理。",
        evidence_refs=["07-paper-review"],
    )


def _result(task_id: str, status: str) -> PaperRevisionTaskResult:
    return PaperRevisionTaskResult(task_id=task_id, status=status, action_taken="已处理。", evidence_refs=["07-paper-review"])


def _plan(tasks: list[RevisionTask]) -> PaperRevisionPlan:
    return PaperRevisionPlan(
        topic="机械臂路径规划",
        decision="revise",
        readiness="revise_before_submission",
        summary="需要修订。",
        tasks=tasks,
        acceptance_checks=[],
        next_iteration_prompt="继续修订。",
    )


def _rewrite_report(results: list[PaperRevisionTaskResult]) -> PaperRewriteReport:
    return PaperRewriteReport(
        topic="机械臂路径规划",
        source_paper="06-paper.md",
        revised_paper="09-revised-paper.md",
        revision_plan="08-revision-plan.json",
        summary="已修订。",
        task_results=results,
        deferred_tasks=[],
        next_checks=[],
    )


if __name__ == "__main__":
    unittest.main()
