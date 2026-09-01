from __future__ import annotations

import unittest

from research_agent.review_constraints import build_review_constraints, constraints_agent_text, render_review_constraints_markdown


class ReviewConstraintsTest(unittest.TestCase):
    def test_build_constraints_classifies_baseline_and_literature_notes(self) -> None:
        report = build_review_constraints(
            "机械臂路径规划",
            {
                "approved": True,
                "notes": "必须比较 RRT* 并补人工种子文献",
                "items": [{"notes": "必须比较 RRT* 并补人工种子文献"}, {"notes": "建议报告碰撞率指标"}],
            },
        )
        rendered = render_review_constraints_markdown(report)
        agent_text = constraints_agent_text(report)

        self.assertEqual(len(report["constraints"]), 3)
        self.assertEqual(report["constraints"][0]["category"], "baseline")
        self.assertEqual(report["constraints"][0]["priority"], "high")
        self.assertEqual(report["constraints"][1]["category"], "literature")
        self.assertEqual(report["constraints"][2]["category"], "metric")
        self.assertIn("结构化审核约束", agent_text)
        self.assertIn("RC01", rendered)
        self.assertIn("experiment_plan", rendered)

    def test_no_notes_records_warning(self) -> None:
        report = build_review_constraints("机械臂路径规划", {"approved": True, "items": []})

        self.assertFalse(report["constraints"])
        self.assertTrue(report["warnings"])
        self.assertEqual(constraints_agent_text(report), "")

    def test_approval_audit_summaries_are_not_split_into_constraints(self) -> None:
        report = build_review_constraints(
            "Iris classification benchmark smoke",
            {
                "approved": True,
                "notes": (
                    "Manual review for UCI Iris smoke gold run: accepted remaining literature risks because "
                    "paper-grade literature passed (online provider, 4 configured sources, 3 successful sources, "
                    "11 DOI/URL seeds, 11/11 curated seeds, metadata_resolved=6, seed role coverage pass), "
                    "coverage passed (11/11 required external benchmark/baseline facets), no blocking citation "
                    "or evidence-contract issues remain. "
                    "Do not claim broad scientific novelty from Iris alone; use it to validate benchmark provenance, "
                    "manifest contracts, repeated execution, statistics, and release flow."
                ),
            },
        )

        texts = [item["text"] for item in report["constraints"]]
        self.assertNotIn("4 configured sources", texts)
        self.assertNotIn("coverage passed (11/11 required external benchmark/baseline facets)", texts)
        self.assertTrue(any("Do not claim broad scientific novelty" in text for text in texts))


if __name__ == "__main__":
    unittest.main()
