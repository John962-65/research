from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.ai_disclosure import build_ai_disclosure_report, render_ai_disclosure_markdown, write_ai_disclosure_artifacts
from research_agent.artifacts import write_json


class AIDisclosureTest(unittest.TestCase):
    def test_disclosure_uses_llm_ledger_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "run-llm-ledger.json",
                {
                    "total_calls": 2,
                    "successful_calls": 2,
                    "failed_calls": 0,
                    "entries": [
                        {"purpose": "Research ideas", "status": "success"},
                        {"purpose": "Paper revision", "status": "success"},
                    ],
                },
            )
            write_json(run_dir / "run-manifest.json", {"artifacts": [{"path": "06-paper.md"}, {"path": "09-revised-paper.md"}]})

            report = build_ai_disclosure_report("机械臂路径规划", run_dir)
            rendered = render_ai_disclosure_markdown(report)
            write_ai_disclosure_artifacts("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "needs_human_policy_check")
            self.assertTrue(report["used_ai"])
            self.assertIn("automated research-agent workflow", report["disclosure_statement"])
            self.assertIn("Research ideas", rendered)
            self.assertTrue((run_dir / "10-ai-disclosure.json").exists())
            self.assertTrue((run_dir / "10-ai-disclosure.md").exists())


if __name__ == "__main__":
    unittest.main()
