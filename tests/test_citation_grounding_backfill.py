from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.citation_grounding import CITATION_GROUNDING_JSON, CITATION_GROUNDING_MD
from research_agent.citation_grounding_backfill import backfill_citation_grounding, render_citation_grounding_backfill_markdown


class CitationGroundingBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_groundable_run(run_dir)

            report = backfill_citation_grounding(runs_dir, dry_run=True)
            rendered = render_citation_grounding_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write"], 1)
            self.assertFalse((run_dir / CITATION_GROUNDING_JSON).exists())
            self.assertIn("不会生成论文", rendered)
            self.assertIn("06-paper", rendered)

    def test_write_creates_grounding_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_groundable_run(run_dir)

            report = backfill_citation_grounding(runs_dir)
            saved = (run_dir / CITATION_GROUNDING_JSON).read_text(encoding="utf-8")

            self.assertEqual(report["written"], 1)
            self.assertTrue((run_dir / CITATION_GROUNDING_MD).exists())
            self.assertIn('"status": "pass"', saved)
            self.assertNotIn("Robot manipulator motion planning uses benchmark", str(report["items"][0]))

    def test_write_can_use_draft_when_revised_paper_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "paper_draft_completed"})
            write_json(run_dir / "01-context.json", _context_payload())
            write_text(run_dir / "06-paper.md", "Robot manipulator motion planning uses benchmark evaluation for collision-free paths [lovelace2024robot1].")

            report = backfill_citation_grounding(runs_dir)
            saved = (run_dir / CITATION_GROUNDING_JSON).read_text(encoding="utf-8")

            self.assertEqual(report["written"], 1)
            self.assertIn('"paper_source": "06-paper.md"', saved)

    def test_skips_missing_context_or_paper_without_fabricating(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            no_context = runs_dir / "no-context"
            no_context.mkdir(parents=True)
            write_json(no_context / "state.json", {"topic": "机械臂路径规划"})
            write_text(no_context / "09-revised-paper.md", "Claim [a].")
            no_paper = runs_dir / "no-paper"
            no_paper.mkdir(parents=True)
            write_json(no_paper / "state.json", {"topic": "机械臂路径规划"})
            write_json(no_paper / "01-context.json", _context_payload())

            report = backfill_citation_grounding(runs_dir)

            self.assertEqual(report["written"], 0)
            self.assertEqual(report["skipped_no_context"], 1)
            self.assertEqual(report["skipped_no_paper"], 1)
            self.assertFalse((no_context / CITATION_GROUNDING_JSON).exists())
            self.assertFalse((no_paper / CITATION_GROUNDING_JSON).exists())

    def test_existing_skips_unless_forced(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_groundable_run(run_dir)
            backfill_citation_grounding(runs_dir)

            skipped = backfill_citation_grounding(runs_dir)
            forced = backfill_citation_grounding(runs_dir, force=True)

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written"], 1)


def _write_groundable_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(run_dir / "01-context.json", _context_payload())
    write_text(run_dir / "09-revised-paper.md", "Robot manipulator motion planning uses benchmark evaluation for collision-free paths [lovelace2024robot1].")


def _context_payload() -> dict[str, object]:
    return {
        "topic": "机械臂路径规划",
        "citations": [
            {
                "key": "lovelace2024robot1",
                "title": "Robot manipulator motion planning benchmark",
                "authors": ["Ada Lovelace"],
                "year": 2024,
                "venue": "Robotics",
                "url": "https://example.test",
                "doi": "10.1234/example",
                "source": "openalex",
            }
        ],
        "chunks": [
            {
                "chunk_id": "chunk-001",
                "citation_key": "lovelace2024robot1",
                "title": "Robot manipulator motion planning benchmark",
                "text": "Robot manipulator motion planning benchmark evaluates collision-free path quality and planning success.",
                "source": "openalex",
                "url": "https://example.test",
                "relevance": 0.9,
            }
        ],
        "claim_support": [],
        "review_gate": {"status": "pass", "warnings": [], "required_actions": []},
    }


if __name__ == "__main__":
    unittest.main()
