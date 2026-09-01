from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_text
from research_agent.citation_coverage import (
    CITATION_COVERAGE_JSON,
    CITATION_COVERAGE_MD,
    build_citation_coverage_report,
    render_citation_coverage_markdown,
    write_citation_coverage_artifacts,
)
from research_agent.models import CitationEntry, ClaimSupport, EvidenceChunk, LiteratureContext, ReviewGate


class CitationCoverageTest(unittest.TestCase):
    def test_citation_coverage_passes_when_core_context_is_cited(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(
                run_dir / "09-revised-paper.md",
                "Robot planning baselines use RRT* [key1], CHOMP [key2], and benchmark datasets [key3].",
            )

            report = write_citation_coverage_artifacts("机械臂路径规划", run_dir, _context(3))
            rendered = render_citation_coverage_markdown(report)
            saved = json.loads((run_dir / CITATION_COVERAGE_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["unique_cited_keys"], 3)
            self.assertFalse(report["blocking_issues"])
            self.assertTrue((run_dir / CITATION_COVERAGE_MD).exists())
            self.assertIn("Citation Coverage Audit", rendered)
            self.assertEqual(saved["status"], "pass")

    def test_citation_coverage_blocks_unknown_keys_and_missing_markers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "Robot planning cites an unknown source [missing2024paper].")

            report = build_citation_coverage_report("机械臂路径规划", run_dir, _context(3))

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("不存在" in item for item in report["blocking_issues"]))

    def test_citation_coverage_reviews_thin_or_dominated_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "Only one source is cited repeatedly [key1] [key1] [key1] [key1].")

            report = build_citation_coverage_report("机械臂路径规划", run_dir, _context(6))

            self.assertEqual(report["status"], "review_required")
            self.assertLess(report["context_coverage_ratio"], 0.4)
            self.assertTrue(any("覆盖" in item or "集中" in item for item in report["manual_tasks"]))

    def test_citation_coverage_blocks_when_paper_has_no_citations(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_text(run_dir / "09-revised-paper.md", "Robot planning has no citation markers.")

            report = build_citation_coverage_report("机械臂路径规划", run_dir, _context(2))

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("没有可核对" in item for item in report["blocking_issues"]))


def _context(count: int) -> LiteratureContext:
    citations = [
        CitationEntry(
            key=f"key{index}",
            title=f"Robot manipulator planning paper {index}",
            authors=["Ada Lovelace"],
            year=2024 - index,
            venue="Robotics",
            url=f"https://example.test/{index}",
            doi=f"10.1234/example.{index}",
            source="openalex",
        )
        for index in range(1, count + 1)
    ]
    chunks = [
        EvidenceChunk(
            chunk_id=f"chunk-{index:03d}",
            citation_key=f"key{index}",
            title=f"Robot manipulator planning paper {index}",
            text="Robot manipulator motion planning benchmark, baseline and path quality evidence.",
            source="openalex",
            url=f"https://example.test/{index}",
            relevance=0.9 if index <= 3 else 0.5,
        )
        for index in range(1, count + 1)
    ]
    return LiteratureContext(
        topic="机械臂路径规划",
        citations=citations,
        chunks=chunks,
        claim_support=[ClaimSupport("机器人路径规划需要 benchmark。", "theme", "supported", ["key1"], [])],
        review_gate=ReviewGate("pass", [], []),
    )


if __name__ == "__main__":
    unittest.main()
