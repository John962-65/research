from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.models import PaperClaimAudit, PaperReview
from research_agent.paper_review_calibration import (
    PAPER_REVIEW_CALIBRATION_JSON,
    PAPER_REVIEW_CALIBRATION_MD,
    build_paper_review_calibration_report,
    render_paper_review_calibration_markdown,
    write_paper_review_calibration_artifacts,
)
from research_agent.paper_revision import build_paper_revision_plan


class PaperReviewCalibrationTest(unittest.TestCase):
    def test_blocks_overly_lenient_review_with_unsupported_claims(self) -> None:
        review = _review(
            score=8.6,
            decision="accept_with_minor_revisions",
            claim=PaperClaimAudit(
                claim="候选方法已经显著优于基线。",
                support_level="unsupported",
                evidence_keys=[],
                result_refs=[],
                risk="high",
            ),
        )

        report = build_paper_review_calibration_report(
            "机械臂路径规划",
            review,
            experiment_decision={"decision": "repair_before_writing"},
            hypothesis_outcome={"outcome": "blocked_unverified"},
            execution_mode="simulated",
        )
        rendered = render_paper_review_calibration_markdown(report)

        self.assertEqual(report["status"], "block")
        self.assertLess(report["max_recommended_score"], review.score)
        self.assertTrue(any(item["name"] == "unsupported_claims_present" for item in report["flags"]))
        self.assertTrue(any(item["name"] == "review_score_too_lenient" for item in report["flags"]))
        self.assertIn("Paper Review Calibration", rendered)

    def test_revision_plan_includes_calibration_task(self) -> None:
        review = _review(
            score=8.2,
            decision="accept_with_minor_revisions",
            claim=PaperClaimAudit(
                claim="结果只能作为 smoke test。",
                support_level="supported",
                evidence_keys=["paper2024"],
                result_refs=["planning_success_rate"],
                risk="low",
            ),
        )
        calibration = build_paper_review_calibration_report(
            "机械臂路径规划",
            review,
            experiment_decision={"decision": "benchmark_upgrade"},
            hypothesis_outcome={"outcome": "smoke_only"},
            execution_mode="simulated",
        )

        plan = build_paper_revision_plan("机械臂路径规划", review, review_calibration=calibration)

        self.assertTrue(any(task.section == "Review Calibration" for task in plan.tasks))
        self.assertIn("review calibration", plan.tasks[-1].issue.lower())

    def test_writes_calibration_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_paper_review_calibration_artifacts("校准测试", _review(), run_dir, execution_mode="local")

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / PAPER_REVIEW_CALIBRATION_JSON).exists())
            self.assertTrue((run_dir / PAPER_REVIEW_CALIBRATION_MD).exists())


def _review(
    score: float = 7.0,
    decision: str = "revise",
    claim: PaperClaimAudit | None = None,
) -> PaperReview:
    return PaperReview(
        decision=decision,
        score=score,
        novelty=3,
        soundness=3,
        evidence_quality=3,
        reproducibility=3,
        summary="结构完整，但需要校准。",
        strengths=["有完整链路"],
        weaknesses=[],
        required_revisions=[],
        claim_audit=[
            claim
            or PaperClaimAudit(
                claim="结论保持在证据范围内。",
                support_level="supported",
                evidence_keys=["paper2024"],
                result_refs=["metric"],
                risk="low",
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
