from __future__ import annotations

import unittest

from research_agent.diagnostics import diagnose_exception, render_diagnostic_markdown


class DiagnosticsTest(unittest.TestCase):
    def test_missing_model_is_classified_as_llm_configuration(self) -> None:
        diagnostic = diagnose_exception(RuntimeError("Missing model. Set llm.model or env var: OPENAI_MODEL"), topic="测试")

        self.assertEqual(diagnostic.category, "llm_configuration")
        self.assertEqual(diagnostic.severity, "blocking")
        self.assertIn("模型名", diagnostic.summary)
        self.assertTrue(any("OPENAI_MODEL" in item for item in diagnostic.recommended_actions))

    def test_semantic_scholar_429_is_classified_as_literature_rate_limit(self) -> None:
        diagnostic = diagnose_exception(RuntimeError("semantic_scholar returned HTTP 429: Too Many Requests"))

        self.assertEqual(diagnostic.category, "literature_rate_limit")
        self.assertIn("SEMANTIC_SCHOLAR_API_KEY", " ".join(diagnostic.recommended_actions))

    def test_llm_budget_is_classified(self) -> None:
        diagnostic = diagnose_exception(RuntimeError("LLM budget exceeded: max_calls=1, used_calls=1"))

        self.assertEqual(diagnostic.category, "llm_budget")
        self.assertIn("run-llm-ledger.md", " ".join(diagnostic.recommended_actions))

    def test_markdown_contains_actions_and_traceback(self) -> None:
        diagnostic = diagnose_exception(RuntimeError("unexpected failure"), traceback_text="Traceback line")
        rendered = render_diagnostic_markdown(diagnostic)

        self.assertIn("# Run 诊断", rendered)
        self.assertIn("建议动作", rendered)
        self.assertIn("Traceback line", rendered)


if __name__ == "__main__":
    unittest.main()
