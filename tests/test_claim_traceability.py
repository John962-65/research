from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.claim_traceability import build_claim_traceability_report, render_claim_traceability_markdown, write_claim_traceability_artifacts
from research_agent.final_readiness import build_final_readiness_report
from research_agent.models import (
    CitationEntry,
    ClaimSupport,
    EvidenceChunk,
    LiteratureContext,
    PaperClaimAudit,
    PaperReview,
    PaperRewriteReport,
    ReviewGate,
)


class ClaimTraceabilityTest(unittest.TestCase):
    def test_traceability_passes_when_claim_refs_existing_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="local")
            report = write_claim_traceability_artifacts("机械臂路径规划", run_dir, _review("supported"), _context())
            rendered = render_claim_traceability_markdown(report)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertTrue((run_dir / "10-claim-traceability.json").exists())
            self.assertIn("Traceability Matrix", rendered)

    def test_traceability_blocks_missing_citation_and_result_refs(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="local")
            review = PaperReview(
                decision="major_revision",
                score=5.0,
                novelty=3,
                soundness=3,
                evidence_quality=2,
                reproducibility=3,
                summary="缺证据。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="结果显示 success_rate 显著优于 baseline。",
                        support_level="supported",
                        evidence_keys=["missing2024paper"],
                        result_refs=["missing_metric"],
                        risk="high",
                    )
                ],
            )

            report = build_claim_traceability_report("机械臂路径规划", run_dir, review, _context())
            readiness = build_final_readiness_report("机械臂路径规划", _review("supported"), review, _rewrite_report(), traceability_report=report)

            self.assertEqual(report.status, "block")
            self.assertTrue(report.blocking_issues)
            self.assertEqual(readiness.status, "requires_human_evidence")
            self.assertTrue(readiness.traceability_blocking_issues)

    def test_traceability_allows_result_only_artifact_claims(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="benchmark")
            write_json(run_dir / "03-experiment-plan.json", {"commands": ["python3 simulate.py --mode artifact"]})
            write_text(
                run_dir / "09-revised-paper.md",
                "# Demo\n\n## 结果\n本次产物标记为 evidence_grade=real_benchmark，benchmark adapter/runbook 已实际执行，并留下 runbook、results 和 statistics 等内部记录。",
            )
            review = PaperReview(
                decision="revise",
                score=7.0,
                novelty=3,
                soundness=3,
                evidence_quality=3,
                reproducibility=3,
                summary="运行产物 claim。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="本次产物标记为 evidence_grade=real_benchmark，benchmark adapter/runbook 已实际执行，并留下 runbook、results 和 statistics 等内部记录。",
                        support_level="weak",
                        evidence_keys=[],
                        result_refs=["03-experiment-plan.json", "04-experiment-runbook.json", "04-results.json", "04-statistics.json"],
                        risk="medium",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertEqual(report.items[0].citation_status, "not_required")
            self.assertEqual(report.items[0].decision, "pass")

    def test_traceability_closes_weak_internal_scope_claims_when_artifacts_match(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="benchmark")
            claim = "实验范围限定为单环境、单 frozen split、三次执行一致性检查。"
            write_text(run_dir / "09-revised-paper.md", f"# Demo\n\n{claim}")
            review = PaperReview(
                decision="major_revision",
                score=4.0,
                novelty=2,
                soundness=3,
                evidence_quality=2,
                reproducibility=3,
                summary="scope claim。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim=claim,
                        support_level="weak",
                        evidence_keys=[],
                        result_refs=["04-experiment-runbook.json", "04-results.json", "04-statistics.json"],
                        risk="medium",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.items[0].decision, "pass")
            self.assertEqual(report.items[0].result_status, "pass")
            self.assertEqual(report.items[0].runbook_status, "pass")

    def test_traceability_does_not_require_results_for_literature_scope_claims(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="benchmark")
            claim = "文献引用仅用于标注数据来源、API 入口和背景 baseline，不用于证明协议有效性或性能优势。"
            write_text(run_dir / "09-revised-paper.md", f"# Demo\n\n{claim}")
            review = PaperReview(
                decision="revise",
                score=7.0,
                novelty=3,
                soundness=3,
                evidence_quality=3,
                reproducibility=3,
                summary="citation scope。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim=claim,
                        support_level="supported",
                        evidence_keys=["lovelace2024robot1"],
                        result_refs=["摘要中的引用角色声明", "引言中的文献限定声明"],
                        risk="low",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertEqual(report.items[0].result_status, "not_required")

    def test_traceability_does_not_require_metrics_for_evidence_gap_boundary_claims(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="benchmark")
            claim = "多数类 reference check 当前材料未提供可核验的具体指标值，Dummy stratified 等 sanity baseline 亦未提供完整执行证据。"
            write_text(run_dir / "09-revised-paper.md", f"# Demo\n\n## 结果边界\n{claim}")
            review = PaperReview(
                decision="revise",
                score=7.0,
                novelty=3,
                soundness=3,
                evidence_quality=3,
                reproducibility=3,
                summary="boundary claim。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim=claim,
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=["methods list", "absence of reported metrics for majority and Dummy stratified"],
                        risk="low",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertEqual(report.items[0].result_status, "not_required")

    def test_traceability_matches_anchored_artifact_claim_without_explicit_result_refs(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_iris_evidence_artifacts(run_dir)
            claim = (
                "内部产物审计将本次 run 标记为 evidence_grade=real_benchmark，含义仅是 adapter 命令实际执行并留下 "
                "runbook/results/statistics；accuracy：candidate 均值=0.967，baseline 均值=0.967，差值=0.000。"
            )
            write_text(run_dir / "09-revised-paper.md", f"# Demo\n\n{claim}")
            review = PaperReview(
                decision="revise",
                score=7.0,
                novelty=3,
                soundness=3,
                evidence_quality=3,
                reproducibility=3,
                summary="artifact scope。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim=claim,
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=[],
                        risk="medium",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertEqual(report.items[0].citation_status, "not_required")
            self.assertEqual(report.items[0].result_status, "pass")
            self.assertEqual(report.items[0].matched_result_refs, ["implicit:claim_text_artifact_match"])

    def test_traceability_matches_freeform_artifact_hash_references(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_iris_evidence_artifacts(run_dir)
            write_text(
                run_dir / "09-revised-paper.md",
                "# Demo\n\n本次 run 标记为 evidence_grade=real_benchmark，含义是 adapter 命令实际执行并留下 runbook/results/statistics。",
            )
            review = PaperReview(
                decision="revise",
                score=6.0,
                novelty=2,
                soundness=3,
                evidence_quality=3,
                reproducibility=4,
                summary="artifact refs。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="本次 run 标记为 evidence_grade=real_benchmark，含义是 adapter 命令实际执行并留下 runbook/results/statistics。",
                        support_level="weak",
                        evidence_keys=[],
                        result_refs=[
                            "source_tree aggregate_sha256=5934546dc0dcd4d6a2035e3cb8bd75964c896e4369e9aa1fbdacb6a59ca89d40",
                            "metrics artifact SHA256",
                            "data/split/grader SHA256",
                        ],
                        risk="medium",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertEqual(report.items[0].result_status, "pass")

    def test_traceability_matches_freeform_frozen_split_reference(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_iris_evidence_artifacts(run_dir)
            write_text(run_dir / "09-revised-paper.md", "# Demo\n\n当前稿件本身只定位为单环境 smoke run 记录。")
            review = PaperReview(
                decision="revise",
                score=6.0,
                novelty=2,
                soundness=3,
                evidence_quality=3,
                reproducibility=4,
                summary="scope refs。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="当前稿件本身只定位为单环境 smoke run 记录。",
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=[
                            "mode=benchmark",
                            "Python 3.12 / Linux",
                            "repeats=3",
                            "single frozen split",
                        ],
                        risk="low",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.items[0].result_status, "pass")
            self.assertIn("single frozen split", report.items[0].matched_result_refs)

    def test_traceability_matches_freeform_result_evidence_phrases(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_iris_evidence_artifacts(run_dir)
            review = PaperReview(
                decision="revise",
                score=6.0,
                novelty=3,
                soundness=3,
                evidence_quality=3,
                reproducibility=3,
                summary="结果证据短语。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="candidate 与 baseline 在当前重复下 accuracy、macro-F1、error rate 数值相同，accuracy 均值均为 0.967，差值为 0.000。",
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=[
                            "candidate repeats 0-2 accuracy=0.966667, macro_f1=0.966583, error=0.033333",
                            "baseline summary accuracy=0.966667, macro_f1=0.966583",
                        ],
                        risk="low",
                    ),
                    PaperClaimAudit(
                        claim="所有角色使用同一 split，训练/测试样本数为 120/30，类别分布均衡。",
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=[
                            "Train/Test=120/30",
                            "train setosa=40, versicolor=40, virginica=40",
                            "test setosa=10, versicolor=10, virginica=10",
                            "Split 生成规则",
                        ],
                        risk="low",
                    ),
                    PaperClaimAudit(
                        claim="本文当前稿件本身只定位为单环境 smoke run 记录。",
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=["执行环境为单一 Linux/Python 配置", "mode=benchmark, repeats=3", "三次 repeat 使用同一 frozen split"],
                        risk="low",
                    ),
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_claims, 0)
            self.assertTrue(all(item.result_status == "pass" for item in report.items))

    def test_traceability_does_not_match_unobserved_freeform_result_phrase(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_iris_evidence_artifacts(run_dir)
            review = PaperReview(
                decision="revise",
                score=6.0,
                novelty=3,
                soundness=3,
                evidence_quality=3,
                reproducibility=3,
                summary="缺失结果证据。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="external benchmark 上 AUC=0.999。",
                        support_level="supported",
                        evidence_keys=[],
                        result_refs=["external benchmark auc=0.999"],
                        risk="high",
                    )
                ],
            )

            report = build_claim_traceability_report("Iris", run_dir, review, _context())

            self.assertEqual(report.status, "block")
            self.assertEqual(report.blocked_claims, 1)

    def test_traceability_ignores_unsupported_reviewer_risk_not_asserted_in_paper(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="benchmark")
            write_text(
                run_dir / "09-revised-paper.md",
                "# Demo\n\n## 结果边界\n本文不再声称统一协议已经显著降低方差。\n禁止表述：不得声称 candidate 在正式意义上优于 baseline。",
            )
            review = PaperReview(
                decision="major_revision",
                score=5.0,
                novelty=3,
                soundness=3,
                evidence_quality=2,
                reproducibility=3,
                summary="列出风险样例。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim="本文已经证明统一协议已经显著降低方差。",
                        support_level="unsupported",
                        evidence_keys=[],
                        result_refs=[],
                        risk="high",
                    ),
                    PaperClaimAudit(
                        claim="candidate 在正式意义上优于 baseline。",
                        support_level="unsupported",
                        evidence_keys=[],
                        result_refs=[],
                        risk="high",
                    ),
                ],
            )

            report = build_claim_traceability_report("机械臂路径规划", run_dir, review, _context())

            self.assertNotEqual(report.status, "block")
            self.assertEqual(report.blocked_claims, 0)
            self.assertTrue(all(item.decision == "pass" for item in report.items))

    def test_traceability_blocks_actual_unsupported_claim_asserted_in_paper(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_evidence_artifacts(run_dir, mode="benchmark")
            claim = "本文已经证明统一协议已经显著降低方差。"
            write_text(run_dir / "09-revised-paper.md", f"# Demo\n\n## 结果\n{claim}")
            review = PaperReview(
                decision="major_revision",
                score=5.0,
                novelty=3,
                soundness=3,
                evidence_quality=2,
                reproducibility=3,
                summary="缺证据。",
                strengths=[],
                weaknesses=[],
                required_revisions=[],
                claim_audit=[
                    PaperClaimAudit(
                        claim=claim,
                        support_level="unsupported",
                        evidence_keys=[],
                        result_refs=[],
                        risk="high",
                    )
                ],
            )

            report = build_claim_traceability_report("机械臂路径规划", run_dir, review, _context())

            self.assertEqual(report.status, "block")
            self.assertEqual(report.blocked_claims, 1)


def _write_evidence_artifacts(run_dir: Path, mode: str) -> None:
    write_json(run_dir / "04-results.json", [{"name": "candidate", "status": "passed", "metrics": {"success_rate": 0.9}}])
    write_json(run_dir / "04-statistics.json", {"comparisons": [{"metric": "success_rate"}]})
    write_json(run_dir / "05-analysis.json", {"headline": "success_rate improved", "metric_table": [{"success_rate": 0.9}]})
    write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": mode}, "runs": [{"name": "candidate"}], "artifacts": []})


def _write_iris_evidence_artifacts(run_dir: Path) -> None:
    common_metrics = {
        "accuracy": 0.966667,
        "macro_f1": 0.966583,
        "error_rate": 0.033333,
        "train_cases": 120.0,
        "test_cases": 30.0,
        "train_class_count_setosa": 40.0,
        "train_class_count_versicolor": 40.0,
        "train_class_count_virginica": 40.0,
        "test_class_count_setosa": 10.0,
        "test_class_count_versicolor": 10.0,
        "test_class_count_virginica": 10.0,
    }
    write_json(
        run_dir / "04-results.json",
        [
            {"name": "candidate-uci-iris-nearest-centroid-candidate", "status": "passed", "repeat_index": i, "metrics": common_metrics}
            for i in range(3)
        ]
        + [
            {"name": "baseline-uci-iris-3-nearest-neighbor-baseline", "status": "passed", "repeat_index": i, "metrics": common_metrics}
            for i in range(3)
        ],
    )
    write_json(
        run_dir / "04-statistics.json",
        {
            "comparisons": [
                {
                    "metric": "accuracy",
                    "candidate_mean": 0.966667,
                    "baseline_mean": 0.966667,
                    "delta": 0.0,
                    "ci_low": 0.0,
                    "ci_high": 0.0,
                    "interpretation": "candidate 与 baseline 在当前重复下数值相同；零宽区间只表示这些 repeat 没有观测到差异。",
                }
            ]
        },
    )
    write_json(
        run_dir / "05-analysis.json",
        {
            "headline": "accuracy：candidate 均值=0.967，baseline 均值=0.967，差值=0.000",
            "metric_table": [{"accuracy": 0.966667, "macro_f1": 0.966583, "error_rate": 0.033333}],
        },
    )
    write_json(
        run_dir / "04-experiment-runbook.json",
        {
            "execution": {"mode": "benchmark", "repeats": 3, "platform": "Linux", "python_version": "3.12"},
            "environment": {"source_tree": {"aggregate_sha256": "5934546dc0dcd4d6a2035e3cb8bd75964c896e4369e9aa1fbdacb6a59ca89d40"}},
            "artifacts": [{"path": "split/iris-stratified-test-v1.json"}],
            "runs": [
                {
                    "name": "candidate-uci-iris-nearest-centroid-candidate",
                    "repeat_index": 0,
                    "produced_artifacts": [
                        {"path": "candidate_metrics.json", "sha256": "f4a9abe33deeb13b101e4ad6a648121a871f6a7017229c0331fb7c1c2f6caa6a"},
                        {"path": "data/iris.data", "sha256": "6f608b71a7317216319b4d27b4d9bc84e6abd734eda7872b71a458569e2656c0"},
                        {"path": "split/iris-stratified-test-v1.json", "sha256": "89b38bc09de1c44e7aa0efc016103b5ddaa4032cfdc7ae674bff4371a2b78fef"},
                        {"path": "grade_iris.py", "sha256": "a44cb55398d8caf6eae8e685f07121add8c5ef1cec492c9a45b436b1ad112fe6"},
                    ],
                }
            ],
            "split": {
                "name": "iris-stratified-test-v1",
                "policy": "每类 40 train cases / 10 test cases，所有角色使用同一 split。",
            },
        },
    )
    write_text(
        run_dir / "04-experiment-runbook.md",
        "# Runbook\n\n- Python：3.12\n- 平台：Linux\n- 所有角色使用同一 frozen split。\n",
    )
    write_json(run_dir / "04-environment-snapshot.json", {"python": {"version": "3.12"}, "system": {"platform": "Linux"}})
    write_json(run_dir / "split" / "iris-stratified-test-v1.json", {"split_policy": "Split 生成规则：每类 10 test cases / 40 train cases。"})


def _context() -> LiteratureContext:
    return LiteratureContext(
        topic="机械臂路径规划",
        citations=[
            CitationEntry(
                key="lovelace2024robot1",
                title="Robot manipulator motion planning",
                authors=["Ada Lovelace"],
                year=2024,
                venue="Robotics",
                url="https://example.test",
                doi="10.1234/example",
                source="openalex",
            )
        ],
        chunks=[
            EvidenceChunk(
                chunk_id="chunk-001",
                citation_key="lovelace2024robot1",
                title="Robot manipulator motion planning",
                text="Robot manipulator motion planning benchmark.",
                source="openalex",
                url="https://example.test",
                relevance=0.9,
            )
        ],
        claim_support=[ClaimSupport("机器人路径规划需要 benchmark。", "theme", "supported", ["lovelace2024robot1"], [])],
        review_gate=ReviewGate("pass", [], []),
    )


def _review(support_level: str) -> PaperReview:
    return PaperReview(
        decision="accept_with_minor_revisions",
        score=8.0,
        novelty=4,
        soundness=4,
        evidence_quality=4,
        reproducibility=4,
        summary="通过。",
        strengths=[],
        weaknesses=[],
        required_revisions=[],
        claim_audit=[
            PaperClaimAudit(
                claim="结果显示 success_rate 优于 baseline。",
                support_level=support_level,
                evidence_keys=["lovelace2024robot1"],
                result_refs=["success_rate"],
                risk="low",
            )
        ],
    )


def _rewrite_report() -> PaperRewriteReport:
    return PaperRewriteReport(
        topic="机械臂路径规划",
        source_paper="06-paper.md",
        revised_paper="09-revised-paper.md",
        revision_plan="08-revision-plan.json",
        summary="已修订。",
        task_results=[],
        deferred_tasks=[],
        next_checks=[],
    )


if __name__ == "__main__":
    unittest.main()
