from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from research_agent.claim_evidence_polarity import assess_claim_polarity


class ClaimPolarityRuleTest(unittest.TestCase):
    def test_negated_direction_is_contradicted(self) -> None:
        # A17：原文"提升准确率"，稿件写"未提升准确率" → 不得因词相似自动通过。
        assessment = assess_claim_polarity(
            "本文方法将准确率提升了 3.2 个百分点。",
            "实验表明该技术在 UCI Iris 数据集上未提升准确率，与 baseline 持平。",
        )
        self.assertEqual(assessment.polarity, "contradicted")
        self.assertTrue(any("direction_conflict" in item for item in assessment.conflicts))

    def test_number_mismatch_is_flagged(self) -> None:
        assessment = assess_claim_polarity(
            "准确率从 91.7% 提升至 97.2%。",
            "所提模型在 UCI Iris 上将准确率提升了 1.4 个百分点，取得 93.1% 的最终成绩。",
        )
        self.assertEqual(assessment.polarity, "contradicted")
        self.assertTrue(any("number_conflict" in item for item in assessment.conflicts))

    def test_dataset_mismatch_is_flagged(self) -> None:
        # 把数据集 A 的结果写成数据集 B → 条件冲突。
        assessment = assess_claim_polarity(
            "该方法在 Iris 数据集上提升了分类准确率。",
            "MNIST 基准上准确率提升明显，训练收敛加快。",
        )
        self.assertEqual(assessment.polarity, "contradicted")
        self.assertTrue(any("condition_conflict" in item for item in assessment.conflicts))

    def test_matching_claim_with_complete_evidence_is_supported(self) -> None:
        # A18：正确主张且证据完整 → 可通过并定位证据。
        assessment = assess_claim_polarity(
            "候选方法在 UCI Iris 上将 macro_f1 提升至 0.966。",
            "在 UCI Iris 固定测试划分上，候选分类器 macro_f1 提升，达到 0.966，优于 knn3 baseline。",
        )
        self.assertEqual(assessment.polarity, "supported")
        self.assertEqual(assessment.conflicts, [])

    def test_no_direction_claim_is_not_assessed(self) -> None:
        assessment = assess_claim_polarity(
            "本文仅在固定测试划分上报告结果，不声称跨任务泛化。",
            "任何相关证据文本。",
        )
        self.assertEqual(assessment.polarity, "not_assessed")

    def test_empty_evidence_is_insufficient(self) -> None:
        assessment = assess_claim_polarity("准确率显著提升。", "")
        self.assertEqual(assessment.polarity, "insufficient_evidence")

    def test_short_abstract_without_direction_is_insufficient(self) -> None:
        # 短题录摘录不含方向信息 → 模块判 insufficient_evidence；是否据此
        # 降级由 claim_traceability 的长度门控决定（<200 字符不降级，A18）。
        assessment = assess_claim_polarity(
            "结果显示 success_rate 优于 baseline。",
            "Robot manipulator motion planning benchmark.",
        )
        self.assertEqual(assessment.polarity, "insufficient_evidence")
        self.assertEqual(assessment.conflicts, [])


if __name__ == "__main__":
    unittest.main()
