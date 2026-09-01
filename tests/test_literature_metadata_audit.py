from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.literature_context import apply_literature_audits_to_context, build_literature_context
from research_agent.literature_metadata_audit import (
    LITERATURE_METADATA_AUDIT_JSON,
    LITERATURE_METADATA_AUDIT_MD,
    build_literature_metadata_audit_report,
    render_literature_metadata_audit_markdown,
    write_literature_metadata_audit_artifacts,
)
from research_agent.models import LiteratureReview, Paper


class LiteratureMetadataAuditTest(unittest.TestCase):
    def test_metadata_audit_passes_verifiable_multi_source_papers(self) -> None:
        review = _review([_strong_paper(index) for index in range(5)])

        report = build_literature_metadata_audit_report(review, review, None)
        rendered = render_literature_metadata_audit_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["blocked"], 0)
        self.assertGreaterEqual(report["verifiability_score"], 0.75)
        self.assertIn("文献 Metadata 审计", rendered)

    def test_metadata_audit_blocks_unverifiable_curated_paper(self) -> None:
        raw = _review([_strong_paper(1), _weak_paper()])
        curated = _review([_weak_paper()])

        report = build_literature_metadata_audit_report(raw, curated, None)

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["blocked"], 1)
        self.assertTrue(any("no locator" in issue for issue in report["items"][0]["issues"]))
        self.assertTrue(any("不要批准进入 idea/实验" in item for item in report["required_actions"]))

    def test_metadata_audit_updates_review_gate(self) -> None:
        raw = _review([_strong_paper(1), _weak_paper()])
        curated = _review([_weak_paper()])
        report = build_literature_metadata_audit_report(raw, curated, None)
        context = build_literature_context(curated)

        enriched = apply_literature_audits_to_context(context, metadata_report=report)

        self.assertEqual(enriched.review_gate.status, "block")
        self.assertTrue(any("metadata" in item.lower() for item in enriched.review_gate.warnings))

    def test_writes_metadata_audit_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            review = _review([_strong_paper(1)])

            report = write_literature_metadata_audit_artifacts(review, review, None, run_dir)

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / LITERATURE_METADATA_AUDIT_JSON).exists())
            self.assertTrue((run_dir / LITERATURE_METADATA_AUDIT_MD).exists())


def _review(papers: list[Paper]) -> LiteratureReview:
    return LiteratureReview(
        topic="robot manipulator motion planning benchmark",
        papers=papers,
        themes=["Robot manipulator motion planning needs benchmark grounding."],
        gaps=["Compare RRT star and trajectory optimization baselines."],
        summary="测试",
    )


def _strong_paper(index: int) -> Paper:
    return Paper(
        title=f"Robot manipulator motion planning benchmark with RRT star {index}",
        authors=["Ada Lovelace"],
        year=2022,
        venue="Robotics Journal",
        url=f"https://example.test/robot/{index}",
        abstract=(
            "Robot manipulator motion planning benchmark with obstacle avoidance, "
            "RRT star, trajectory optimization, planning time, path length, collision rate, "
            "and reproducible baseline evaluation."
        ),
        relevance=0.92,
        source="openalex",
        sources=["openalex", "semantic_scholar", "crossref"],
        doi=f"10.1234/robot.{index}",
        citation_count=100,
    )


def _weak_paper() -> Paper:
    return Paper(
        title="Unrelated note",
        authors=[],
        year=0,
        venue="Crossref",
        url="",
        abstract="Short.",
        relevance=0.2,
        source="crossref",
        sources=["crossref"],
    )


if __name__ == "__main__":
    unittest.main()
