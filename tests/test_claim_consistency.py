from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.claim_consistency import build_claim_consistency_report, render_claim_consistency_markdown, write_claim_consistency_artifacts


class ClaimConsistencyTest(unittest.TestCase):
    def test_blocks_strong_claims_for_smoke_only_outcome(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n结果证明该方法显著优于基线，并支持假设。")
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "smoke_only", "support_score": 0.4})

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "block")
            self.assertTrue(any("过强正向结论" in issue for issue in report.blocking_issues))

    def test_reviews_partial_support_without_specific_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n结果章节报告了指标差异。\n\n## 局限性\n本实验仍有局限。")
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "partially_supported", "support_score": 0.6})

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "review_required")
            self.assertTrue(any("结果边界" in task for task in report.manual_tasks))

    def test_passes_negative_outcome_when_paper_reports_negative_result(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n当前实验给出负结果，候选方法不优于 baseline，不能支持原始假设。")
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "refuted_or_negative", "support_score": 0.1})

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertFalse(report.blocking_issues)
            self.assertFalse(report.manual_tasks)
            self.assertTrue(any(item.item == "负结果报告" and item.status == "pass" for item in report.checks))

    def test_blocks_formal_benchmark_claims_for_local_experiment_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n结果表明该方法在公开 benchmark 上显著优于 baseline，并可泛化到广泛任务。")
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 0.9})
            write_json(run_dir / "04-benchmark-evidence-audit.json", {"status": "review_required", "evidence_grade": "local_experiment", "claim_policy": "preliminary_local_evidence_requires_manual_benchmark_context"})

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "block")
            self.assertEqual(report.evidence_inventory["benchmark_grade"], "local_experiment")
            self.assertTrue(any("Benchmark 证据等级" in issue for issue in report.blocking_issues))

    def test_blocks_claim_boundary_preflight_prohibited_patterns(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n结果证明该方法稳定提升。")
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 0.9})
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "limited_claim_paper",
                    "prohibited_patterns": ["证明", "稳定提升"],
                },
            )

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "block")
            self.assertEqual(report.evidence_inventory["claim_preflight_violations"], 1)
            self.assertTrue(any("Claim 预检禁用表述" in issue for issue in report.blocking_issues))

    def test_ignores_prohibited_claim_examples_in_boundary_section(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(
                run_dir / "09-revised-paper.md",
                "# Demo\n\n## 结果边界\n禁止表述：不得声称 candidate 已在正式 benchmark 中显著优于 baseline。",
            )
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 0.9})
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "limited_claim_paper",
                    "prohibited_patterns": ["显著优于", "正式 benchmark"],
                },
            )

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertFalse(report.blocking_issues)
            self.assertEqual(report.evidence_inventory["claim_preflight_violations"], 0)
            self.assertEqual(report.evidence_inventory["strong_positive_claims"], 0)

    def test_ignores_negated_no_superiority_boundary_claims(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(
                run_dir / "09-revised-paper.md",
                (
                    "# Demo\n\n## 结果边界\n"
                    "当前实验给出负结果，候选方法不优于 baseline。"
                    "本文不声称该 smoke run 能证明 Iris 任务上的模型优劣，"
                    "也不声称当前协议已具备跨环境稳定性或外部复现有效性。"
                ),
            )
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "refuted_or_negative", "support_score": 0.1})
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "limited_claim_paper",
                    "prohibited_patterns": ["证明", "优于 baseline", "稳定提升"],
                },
            )

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.evidence_inventory["strong_positive_claims"], 0)
            self.assertEqual(report.evidence_inventory["claim_preflight_violations"], 0)

    def test_ignores_limited_internal_proof_boundary_sentence(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(
                run_dir / "09-revised-paper.md",
                (
                    "# Demo\n\n## 结果边界\n"
                    "当前实验给出负结果，候选方法不优于 baseline。"
                    "该信息仅证明本次 frozen split 的内部执行结果，不证明跨 split 或跨环境稳定性。"
                ),
            )
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "refuted_or_negative", "support_score": 0.1})
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "limited_claim_paper",
                    "prohibited_patterns": ["证明", "稳定性"],
                },
            )

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.evidence_inventory["strong_positive_claims"], 0)
            self.assertEqual(report.evidence_inventory["claim_preflight_violations"], 0)

    def test_ignores_claim_audit_fragments_in_revision_record(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(
                run_dir / "09-revised-paper.md",
                "# Demo\n\n## 结果\n结果限定在当前 benchmark adapter 范围内。\n\n## 修订执行记录\n- 问题：weak claim：candidate 在 accuracy 上优于 baseline，需收窄表述。",
            )
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 0.9})

            report = build_claim_consistency_report("一致性", run_dir)

            self.assertEqual(report.evidence_inventory["strong_positive_claims"], 0)
            self.assertFalse(report.blocking_issues)

    def test_write_claim_consistency_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n## 结果\n当前实验支持假设，但仅限本次 benchmark。")
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 0.9})

            report = write_claim_consistency_artifacts("一致性", run_dir)
            rendered = render_claim_consistency_markdown(report)

            self.assertEqual(report.status, "pass")
            self.assertTrue((run_dir / "10-claim-consistency.json").exists())
            self.assertIn("Claim Consistency Audit", rendered)


if __name__ == "__main__":
    unittest.main()
