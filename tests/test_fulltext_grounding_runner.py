from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from research_agent.fulltext_grounding_runner import run_fulltext_grounding


class FulltextGroundingRunnerTest(unittest.TestCase):
    def test_builds_fulltext_context_and_passes_grounding(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fulltext = root / "iris-note.txt"
            fulltext.write_text(
                "The Iris data set contains three classes of 50 instances each. "
                "It has four numeric predictive attributes and one class label.",
                encoding="utf-8",
            )
            out_dir = root / "run"

            with patch.dict("os.environ", {"RESEARCH_AGENT_FULLTEXT_ROOTS": str(root)}):
                report = run_fulltext_grounding(
                    topic="Iris fulltext grounding",
                    fulltext_paths=[str(fulltext)],
                    claim="The Iris data set contains three classes of 50 instances each and four numeric predictive attributes.",
                    out_dir=out_dir,
                )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["fulltext_documents"], 1)
            self.assertEqual(report["fulltext_chunks"], 1)
            self.assertEqual(report["grounding_status"], "pass")
            self.assertEqual(report["passed_citations"], 1)
            for name in [
                "01-fulltext-corpus.json",
                "01-context.json",
                "09-revised-paper.md",
                "10-citation-grounding.json",
                "10-fulltext-grounding-run.json",
            ]:
                self.assertTrue((out_dir / name).exists(), name)

            context = json.loads((out_dir / "01-context.json").read_text(encoding="utf-8"))
            grounding = json.loads((out_dir / "10-citation-grounding.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item["source"] == "local_fulltext" for item in context["citations"]))
            self.assertEqual(grounding["status"], "pass")
            self.assertEqual(grounding["blocked_citations"], 0)


if __name__ == "__main__":
    unittest.main()
