from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.literature_context import build_literature_context
from research_agent.literature_evidence_contract import (
    LITERATURE_EVIDENCE_CONTRACT_JSON,
    LITERATURE_EVIDENCE_CONTRACT_MD,
    build_literature_evidence_contract,
    render_literature_evidence_contract_markdown,
    write_literature_evidence_contract_artifacts,
)
from research_agent.models import LiteratureReview, Paper


class LiteratureEvidenceContractTest(unittest.TestCase):
    def test_contract_blocks_empty_or_unverifiable_context(self) -> None:
        context = build_literature_context(
            LiteratureReview(
                topic="robot manipulator path planning",
                papers=[
                    Paper(
                        title="Generic path planning note",
                        authors=[],
                        year=2025,
                        venue="Crossref",
                        url="",
                        abstract="Short note.",
                        relevance=0.9,
                        source="crossref",
                        sources=["crossref"],
                    ),
                    Paper(
                        title="Another generic path planning record",
                        authors=[],
                        year=2024,
                        venue="Crossref",
                        url="",
                        abstract="Short.",
                        relevance=0.8,
                        source="crossref",
                        sources=["crossref"],
                    ),
                    Paper(
                        title="Thin robot planning metadata",
                        authors=[],
                        year=2024,
                        venue="Crossref",
                        url="",
                        abstract="Thin.",
                        relevance=0.7,
                        source="crossref",
                        sources=["crossref"],
                    ),
                ],
                themes=[],
                gaps=[],
                summary="test",
            )
        )

        report = build_literature_evidence_contract(
            context=context,
            quality_report={"role_coverage": {}, "missing_evidence_roles": ["baseline_method", "benchmark_dataset"]},
            citation_audit_report={"integrity_status": "block", "blocked_citations": 3, "review_required": 0},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(report["blocks_downstream"])
        self.assertEqual(report["summary"]["locator_coverage"], 0.0)
        self.assertEqual(report["summary"]["single_crossref_ratio"], 1.0)
        self.assertEqual(report["summary"]["substantive_chunk_coverage"], 0.0)
        self.assertTrue(any(item["name"] == "substantive_chunk_coverage" and item["status"] == "block" for item in report["checks"]))
        self.assertTrue(any("Crossref" in item for item in report["required_actions"]))
        self.assertTrue(any(item["name"] == "citation_integrity" and item["status"] == "block" for item in report["checks"]))

    def test_contract_requires_review_for_single_source_or_role_gaps(self) -> None:
        context = build_literature_context(
            LiteratureReview(
                topic="robot manipulator path planning",
                papers=[
                    _paper("Robot manipulator motion planning with RRT star", "openalex"),
                    _paper("CHOMP trajectory optimization for robot arms", "openalex"),
                    _paper("STOMP stochastic trajectory optimization", "openalex"),
                    _paper("OMPL benchmark for sampling based planning", "openalex"),
                    _paper("Recent robot arm planning with TrajOpt", "openalex"),
                ],
                themes=["robot arm motion planning benchmarks need reproducible baselines"],
                gaps=[],
                summary="test",
            )
        )

        report = build_literature_evidence_contract(
            context=context,
            quality_report={"role_coverage": {"baseline_method": 2}, "missing_evidence_roles": ["review_survey", "benchmark_dataset", "recent_work"]},
            query_execution_report={"top_rerank_coverage": {"top_count": 5, "covered_top_count": 1, "average_query_coverage": 0.12}},
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0},
        )

        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["blocks_downstream"])
        self.assertTrue(any(item["name"] == "source_diversity" and item["status"] == "review_required" for item in report["checks"]))
        self.assertTrue(any(item["name"] == "top_rerank_query_coverage" and item["status"] == "review_required" for item in report["checks"]))
        self.assertIn("approval notes", " ".join(report["approval_guidance"]))

    def test_contract_passes_for_verifiable_diverse_context(self) -> None:
        context = build_literature_context(
            LiteratureReview(
                topic="robot manipulator path planning",
                papers=[
                    _paper("Robot manipulator motion planning with RRT star", "semantic_scholar"),
                    _paper("CHOMP trajectory optimization for robot arms", "openalex"),
                    _paper("STOMP stochastic trajectory optimization", "arxiv"),
                    _paper("OMPL benchmark for sampling based planning", "semantic_scholar"),
                    _paper("Recent robot arm planning with TrajOpt", "openalex"),
                ],
                themes=["robot arm motion planning benchmarks need reproducible baselines"],
                gaps=["recent work still needs reliable collision-rate evaluation"],
                summary="test",
            )
        )

        report = build_literature_evidence_contract(
            context=context,
            quality_report={
                "role_coverage": {
                    "review_survey": 1,
                    "benchmark_dataset": 1,
                    "baseline_method": 3,
                    "recent_work": 2,
                },
                "missing_evidence_roles": [],
            },
            query_execution_report={"top_rerank_coverage": {"top_count": 5, "covered_top_count": 4, "average_query_coverage": 0.54}},
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["blocking_issues"], [])
        self.assertEqual(report["summary"]["citations"], 5)
        self.assertGreaterEqual(report["summary"]["locator_coverage"], 1.0)
        self.assertEqual(report["summary"]["substantive_chunk_coverage"], 1.0)
        self.assertGreaterEqual(report["summary"]["median_chunk_chars"], 180)
        rendered = render_literature_evidence_contract_markdown(report)
        self.assertIn("文献证据契约", rendered)
        self.assertIn("实质证据片段", rendered)
        self.assertIn("检查表", rendered)

    def test_contract_blocks_title_only_chunks_even_with_doi_and_diverse_sources(self) -> None:
        context = {
            "topic": "robot manipulator path planning",
            "citations": [
                {"key": "c1", "title": "RRT star robot arm planning", "source": "semantic_scholar", "doi": "10.1/a", "url": "https://example.test/a"},
                {"key": "c2", "title": "CHOMP trajectory optimization", "source": "openalex", "doi": "10.1/b", "url": "https://example.test/b"},
                {"key": "c3", "title": "STOMP stochastic optimization", "source": "arxiv", "doi": "10.1/c", "url": "https://example.test/c"},
                {"key": "c4", "title": "OMPL benchmark planning", "source": "semantic_scholar", "doi": "10.1/d", "url": "https://example.test/d"},
                {"key": "c5", "title": "Recent robot arm planning", "source": "openalex", "doi": "10.1/e", "url": "https://example.test/e"},
            ],
            "chunks": [
                {"citation_key": "c1", "text": "RRT star robot arm planning."},
                {"citation_key": "c2", "text": "CHOMP trajectory optimization."},
                {"citation_key": "c3", "text": "STOMP stochastic optimization."},
                {"citation_key": "c4", "text": "OMPL benchmark planning."},
                {"citation_key": "c5", "text": "Recent robot arm planning."},
            ],
        }

        report = build_literature_evidence_contract(
            context=context,
            quality_report={
                "role_coverage": {
                    "review_survey": 1,
                    "benchmark_dataset": 1,
                    "baseline_method": 3,
                    "recent_work": 2,
                },
                "missing_evidence_roles": [],
            },
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0},
        )

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["summary"]["chunk_coverage"], 1.0)
        self.assertEqual(report["summary"]["substantive_chunk_coverage"], 0.0)
        self.assertTrue(any(item["name"] == "substantive_chunk_coverage" and item["status"] == "block" for item in report["checks"]))
        self.assertTrue(any("摘要或本地全文 chunk" in item for item in report["required_actions"]))

    def test_write_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            context = build_literature_context(
                LiteratureReview(topic="robot", papers=[_paper("Robot planning", "openalex")], themes=[], gaps=[], summary="test")
            )

            report = write_literature_evidence_contract_artifacts(context=context, run_dir=run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertTrue((run_dir / LITERATURE_EVIDENCE_CONTRACT_JSON).exists())
            self.assertTrue((run_dir / LITERATURE_EVIDENCE_CONTRACT_MD).exists())


def _paper(title: str, source: str) -> Paper:
    return Paper(
        title=title,
        authors=["Ada Lovelace"],
        year=2024,
        venue="IEEE International Conference on Robotics and Automation",
        url=f"https://example.test/{title.lower().replace(' ', '-')}",
        abstract=(
            f"{title} studies robot manipulator motion planning, obstacle avoidance, "
            "benchmark evaluation, planning time, path length, collision rate, and reproducible baselines."
        ),
        relevance=0.8,
        source=source,
        sources=[source],
        doi="10.1234/" + title.lower().replace(" ", ".")[:40],
    )


if __name__ == "__main__":
    unittest.main()
