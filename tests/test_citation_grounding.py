from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_text
from research_agent.citation_grounding import build_citation_grounding_report, render_citation_grounding_markdown, write_citation_grounding_artifacts
from research_agent.models import CitationEntry, ClaimSupport, EvidenceChunk, LiteratureContext, ReviewGate


class CitationGroundingTest(unittest.TestCase):
    def test_grounding_passes_when_citation_context_overlaps_local_claim(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "Robot manipulator motion planning uses benchmark evaluation for collision-free paths [lovelace2024robot1].")

            report = write_citation_grounding_artifacts("机械臂路径规划", run_dir, _context())
            rendered = render_citation_grounding_markdown(report)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.blocked_citations, 0)
            self.assertEqual(report.evidence_inventory["paper_source"], "09-revised-paper.md")
            self.assertTrue((run_dir / "10-citation-grounding.json").exists())
            self.assertIn("Citation Grounding Matrix", rendered)
            self.assertIn("审计文稿", rendered)

    def test_grounding_can_audit_draft_when_revised_paper_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "06-paper.md", "Robot manipulator motion planning uses benchmark evaluation for collision-free paths [lovelace2024robot1].")

            report = build_citation_grounding_report("机械臂路径规划", run_dir, _context())

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.evidence_inventory["paper_source"], "06-paper.md")

    def test_grounding_reviews_weak_overlap_for_known_citation(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "The system improves data-release workflow quality [lovelace2024robot1].")

            report = build_citation_grounding_report("机械臂路径规划", run_dir, _context())

            self.assertEqual(report.status, "review_required")
            self.assertEqual(report.review_citations, 1)
            self.assertTrue(report.manual_tasks)

    def test_grounding_blocks_unknown_citation_key(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "Robot manipulator planning requires evaluation [missing2024paper].")

            report = build_citation_grounding_report("机械臂路径规划", run_dir, _context())

            self.assertEqual(report.status, "block")
            self.assertEqual(report.blocked_citations, 1)
            self.assertTrue(report.blocking_issues)


def _context() -> LiteratureContext:
    return LiteratureContext(
        topic="机械臂路径规划",
        citations=[
            CitationEntry(
                key="lovelace2024robot1",
                title="Robot manipulator motion planning benchmark",
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
                title="Robot manipulator motion planning benchmark",
                text="Robot manipulator motion planning benchmark evaluates collision-free path quality and planning success.",
                source="openalex",
                url="https://example.test",
                relevance=0.9,
            )
        ],
        claim_support=[ClaimSupport("机器人路径规划需要 benchmark。", "theme", "supported", ["lovelace2024robot1"], [])],
        review_gate=ReviewGate("pass", [], []),
    )


if __name__ == "__main__":
    unittest.main()
