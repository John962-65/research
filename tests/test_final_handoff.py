from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import zipfile

from research_agent.artifacts import write_json, write_text
from research_agent.final_handoff import (
    FINAL_HANDOFF_JSON,
    FINAL_HANDOFF_MD,
    build_final_handoff_report,
    render_final_handoff_markdown,
    write_final_handoff_artifacts,
)


class FinalHandoffTest(unittest.TestCase):
    def test_ready_handoff_flags_manual_snapshot_when_package_lacks_integrity_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/references/references.bib"])

            report = write_final_handoff_artifacts("机械臂路径规划", run_dir)
            rendered = render_final_handoff_markdown(report)

            self.assertEqual(report["status"], "ready_for_human_handoff")
            self.assertFalse(report["blocking_issues"])
            self.assertFalse(report["package_has_integrity_audit"])
            self.assertTrue(any("run-integrity-audit.json" in item for item in report["manual_tasks"]))
            self.assertTrue((run_dir / FINAL_HANDOFF_JSON).exists())
            self.assertTrue((run_dir / FINAL_HANDOFF_MD).exists())
            self.assertIn("最终交付清单", rendered)

    def test_ready_for_submission_when_package_scorecard_and_integrity_all_clear(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/audits/run-integrity-audit.json"])

            report = build_final_handoff_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "ready_for_submission_upload")
            self.assertTrue(report["package_has_integrity_audit"])
            self.assertFalse(report["manual_tasks"])
            self.assertEqual(report["paper_grade_summary"]["literature"]["status"], "pass")
            self.assertEqual(report["paper_grade_summary"]["benchmark"]["grade"], "real_benchmark")
            self.assertEqual(report["paper_grade_summary"]["adapter"]["status"], "ready")

    def test_bounded_negative_or_neutral_result_can_be_handed_off(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/audits/run-integrity-audit.json"])
            _write_negative_or_neutral_benchmark(run_dir, claim_boundary_severity="negative_or_neutral_no_superiority")

            report = build_final_handoff_report("机械臂路径规划", run_dir)
            rendered = render_final_handoff_markdown(report)

            self.assertEqual(report["status"], "ready_for_submission_upload")
            boundary = report["paper_grade_summary"]["negative_or_neutral_boundary"]
            self.assertEqual(boundary["status"], "bounded_negative_or_neutral")
            self.assertTrue(boundary["publishable"])
            self.assertIn("negneutral=bounded_negative_or_neutral/negative_or_neutral_no_superiority", rendered)

    def test_blocks_negative_or_neutral_result_without_no_superiority_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/audits/run-integrity-audit.json"])
            _write_negative_or_neutral_benchmark(run_dir, claim_boundary_severity="superiority_claim_risk")

            report = build_final_handoff_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "blocked")
            boundary = report["paper_grade_summary"]["negative_or_neutral_boundary"]
            self.assertEqual(boundary["status"], "unbounded_negative_or_neutral")
            self.assertTrue(any("negative/neutral benchmark result" in item for item in report["blocking_issues"]))

    def test_blocks_non_paper_grade_claim_handoff(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/audits/run-integrity-audit.json"])
            write_json(
                run_dir / "04-benchmark-evidence-audit.json",
                {
                    "status": "review_required",
                    "evidence_grade": "local_experiment",
                    "adapter_paper_grade_status": "review_required",
                    "adapter_paper_grade_issues": ["缺少 baseline manifest。"],
                    "blocking_issues": [],
                    "manual_tasks": ["补齐 ablation manifest。"],
                },
            )
            write_json(
                run_dir / "10-claim-consistency.json",
                {
                    "status": "block",
                    "consistency_score": 0.55,
                    "blocking_issues": ["正式 benchmark claim 越界。"],
                    "manual_tasks": [],
                },
            )

            report = build_final_handoff_report("机械臂路径规划", run_dir)
            rendered = render_final_handoff_markdown(report)

            self.assertEqual(report["status"], "blocked")
            self.assertEqual(report["paper_grade_summary"]["benchmark"]["grade"], "local_experiment")
            self.assertTrue(any("claim consistency" in item for item in report["blocking_issues"]))
            self.assertTrue(any("adapter paper-grade" in item for item in report["manual_tasks"]))
            self.assertIn("论文级", rendered)
            self.assertIn("bench=review_required/local_experiment:1", rendered)

    def test_blocks_missing_zip_and_integrity_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "11-submission-package.json",
                {
                    "status": "ready_for_human_submission_upload",
                    "package_zip": "11-submission-package.zip",
                    "files": [],
                    "blocking_issues": [],
                },
            )
            write_json(run_dir / "13-research-scorecard.json", {"status": "ready_for_human_submission_upload", "overall_score": 91})

            report = build_final_handoff_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "blocked")
            self.assertTrue(any("zip" in item.lower() for item in report["blocking_issues"]))
            self.assertTrue(any("14-run-integrity-audit.json" in item for item in report["blocking_issues"]))

    def test_blocks_corrupt_submission_package_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/audits/run-integrity-audit.json"])
            write_text(run_dir / "11-submission-package.zip", "not a zip archive")

            report = build_final_handoff_report("机械臂路径规划", run_dir)
            rendered = render_final_handoff_markdown(report)

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["package_zip_exists"])
        self.assertFalse(report["package_zip_valid"])
        self.assertIn("ZIP：11-submission-package.zip（存在，无效）", rendered)
        self.assertTrue(any("不是可读 ZIP" in item for item in report["blocking_issues"]))

    def test_blocks_unsafe_submission_package_zip_metadata_path(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_common(run_dir, package_files=["submission-package/audits/run-integrity-audit.json"])
            write_json(
                run_dir / "11-submission-package.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "ready_for_human_submission_upload",
                    "package_zip": "../11-submission-package.zip",
                    "files": [{"package_path": "submission-package/audits/run-integrity-audit.json", "source_path": "", "status": "pass", "required": False}],
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            report = build_final_handoff_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["package_zip_exists"])
        self.assertFalse(report["package_zip_valid"])
        self.assertTrue(any("路径不安全" in item for item in report["blocking_issues"]))


def _write_common(run_dir: Path, package_files: list[str]) -> None:
    with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
        archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
        archive.writestr(
            "submission-package/package-manifest.json",
            json.dumps(
                {
                    "status": "ready_for_human_submission_upload",
                    "files": [{"package_path": item} for item in package_files],
                }
            ),
        )
        for item in package_files:
            archive.writestr(item, "{}")
    write_json(
        run_dir / "11-submission-package.json",
        {
            "topic": "机械臂路径规划",
            "status": "ready_for_human_submission_upload",
            "package_zip": "11-submission-package.zip",
            "files": [{"package_path": item, "source_path": item, "status": "pass", "required": False} for item in package_files],
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )
    write_json(
        run_dir / "13-research-scorecard.json",
        {"topic": "机械臂路径规划", "status": "ready_for_human_submission_upload", "overall_score": 92, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(
        run_dir / "14-run-integrity-audit.json",
        {"topic": "机械臂路径规划", "status": "pass", "summary": {"checks": 12, "pass": 12, "warn": 0, "block": 0}, "blocking_issues": [], "warnings": []},
    )
    write_json(run_dir / "01-literature-gate-decision.json", {"paper_grade_literature": {"status": "pass", "issues": []}})
    write_json(
        run_dir / "04-benchmark-evidence-audit.json",
        {
            "status": "pass",
            "evidence_grade": "real_benchmark",
            "adapter_paper_grade_status": "ready",
            "adapter_paper_grade_issues": [],
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )
    write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "pass", "writing_mode": "conservative_benchmark_claims_allowed", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 0.97, "blocking_issues": [], "manual_tasks": []})


def _write_negative_or_neutral_benchmark(run_dir: Path, *, claim_boundary_severity: str) -> None:
    write_json(
        run_dir / "04-benchmark-evidence-audit.json",
        {
            "status": "warn",
            "evidence_grade": "real_benchmark",
            "adapter_paper_grade_status": "ready",
            "adapter_paper_grade_issues": [],
            "statistical_outcome": "neutral_no_observed_difference",
            "claim_boundary_severity": claim_boundary_severity,
            "publishable_negative_or_neutral_result": True,
            "blocking_issues": [],
            "manual_tasks": [],
        },
    )


if __name__ == "__main__":
    unittest.main()
