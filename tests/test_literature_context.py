from __future__ import annotations

import unittest

from research_agent.citation_audit import audit_citations, render_citation_audit_markdown
from research_agent.literature_context import apply_citation_audit_to_context, apply_literature_audits_to_context, build_literature_context, export_bibtex, export_ris, retrieve_chunks
from research_agent.models import LiteratureReview, Paper


class LiteratureContextTest(unittest.TestCase):
    def test_context_builds_citations_chunks_and_gate(self) -> None:
        review = LiteratureReview(
            topic="robot manipulator path planning",
            papers=[
                Paper(
                    title="Robot manipulator motion planning with obstacle avoidance",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="arXiv",
                    url="https://arxiv.org/abs/0000.00001",
                    abstract="This paper studies robot manipulator motion planning and obstacle avoidance using sampling based planning.",
                    relevance=0.9,
                    source="arxiv",
                    sources=["arxiv"],
                    doi="10.1234/example",
                    evidence_note="包含实验线索。",
                )
            ],
            themes=["机械臂路径规划需要避障和轨迹连续性。"],
            gaps=["需要可复现 benchmark。"],
            summary="测试综述",
        )

        context = build_literature_context(review)

        self.assertEqual(len(context.citations), 1)
        self.assertEqual(len(context.chunks), 1)
        self.assertTrue(context.claim_support)
        self.assertIn(context.review_gate.status, {"pass", "review_required"})
        self.assertIn("Robot manipulator", export_bibtex(context))
        self.assertIn("TY  - JOUR", export_ris(context))
        self.assertEqual(retrieve_chunks(context, "obstacle avoidance", top_k=1)[0].chunk_id, "chunk-001")

    def test_context_gate_absorbs_literature_quality_and_rescue_audits(self) -> None:
        review = LiteratureReview(
            topic="robot manipulator path planning",
            papers=[
                Paper(
                    title="Robot manipulator motion planning",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="arXiv",
                    url="https://arxiv.org/abs/0000.00001",
                    abstract="Robot manipulator motion planning benchmark.",
                    relevance=0.9,
                    source="arxiv",
                    sources=["arxiv"],
                )
            ],
            themes=["机械臂路径规划需要 benchmark。"],
            gaps=["需要补 baseline 覆盖。"],
            summary="测试综述",
        )
        context = build_literature_context(review)

        enriched = apply_literature_audits_to_context(
            context,
            quality_report={"selected_papers": 1, "total_papers": 4, "warnings": ["质量筛选后可用文献偏少"]},
            coverage_report={"status": "needs_coverage", "coverage_ratio": 0.4, "required_actions": ["补检索 CHOMP"]},
            rescue_report={"status": "needs_rescue_search", "rescue_queries": [{"query": "CHOMP"}], "required_actions": ["执行补检索式"]},
        )

        self.assertEqual(enriched.review_gate.status, "literature_repair_required")
        self.assertTrue(any("01-literature-quality.md" in item for item in enriched.review_gate.required_actions))
        self.assertTrue(any("01-literature-coverage.md" in item for item in enriched.review_gate.required_actions))
        self.assertTrue(any("01-literature-rescue-plan.md" in item for item in enriched.review_gate.required_actions))

    def test_context_gate_absorbs_weak_evidence_confidence(self) -> None:
        review = LiteratureReview(
            topic="robot manipulator path planning",
            papers=[
                Paper(
                    title="Generic path planning note",
                    authors=[],
                    year=2020,
                    venue="Crossref",
                    url="",
                    abstract="Short note.",
                    relevance=0.4,
                    source="crossref",
                    sources=["crossref"],
                )
            ],
            themes=[],
            gaps=[],
            summary="测试综述",
        )
        context = build_literature_context(review)

        enriched = apply_literature_audits_to_context(
            context,
            quality_report={
                "selected_papers": 1,
                "total_papers": 3,
                "warnings": ["整批证据置信度为 weak，不建议直接进入 idea/实验。"],
                "confidence_status": "weak",
                "confidence_score": 0.48,
                "recommended_actions": ["未处理上述问题前不要批准进入 idea/实验。"],
            },
            coverage_report={"status": "pass", "coverage_ratio": 1.0},
            rescue_report={"status": "pass", "rescue_queries": []},
        )

        self.assertEqual(enriched.review_gate.status, "literature_repair_required")
        self.assertTrue(any("文献证据置信度未通过" in item for item in enriched.review_gate.warnings))
        self.assertTrue(any("不要批准进入 idea/实验" in item for item in enriched.review_gate.required_actions))

    def test_context_gate_absorbs_literature_gate_decision(self) -> None:
        review = LiteratureReview(
            topic="robot manipulator path planning",
            papers=[
                Paper(
                    title="Robot manipulator motion planning",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="arXiv",
                    url="https://arxiv.org/abs/0000.00001",
                    abstract="Robot manipulator motion planning benchmark.",
                    relevance=0.9,
                    source="arxiv",
                    sources=["arxiv"],
                )
            ],
            themes=["机械臂路径规划需要 benchmark。"],
            gaps=["需要补 baseline 覆盖。"],
            summary="测试综述",
        )
        context = build_literature_context(review)

        enriched = apply_literature_audits_to_context(
            context,
            gate_decision_report={
                "status": "block",
                "blocking_reasons": ["citation integrity 为 block。"],
                "review_reasons": [],
                "required_actions": ["阻断项处理前不要批准进入 idea/实验。"],
            },
        )

        self.assertEqual(enriched.review_gate.status, "block")
        self.assertTrue(any("文献证据总门禁阻断" in item for item in enriched.review_gate.warnings))
        self.assertTrue(any("01-literature-gate-decision.md" in item for item in enriched.review_gate.required_actions))

    def test_context_gate_absorbs_evidence_contract(self) -> None:
        review = LiteratureReview(
            topic="robot manipulator path planning",
            papers=[
                Paper(
                    title="Generic Crossref planner",
                    authors=[],
                    year=2024,
                    venue="Crossref",
                    url="",
                    abstract="Short.",
                    relevance=0.7,
                    source="crossref",
                    sources=["crossref"],
                )
            ],
            themes=[],
            gaps=[],
            summary="测试综述",
        )
        context = build_literature_context(review)

        enriched = apply_literature_audits_to_context(
            context,
            evidence_contract_report={
                "status": "block",
                "blocking_issues": ["单源 Crossref 题录不能主导 RAG/context。"],
                "review_reasons": [],
                "required_actions": ["降低单源 Crossref 题录占比。"],
            },
        )

        self.assertEqual(enriched.review_gate.status, "block")
        self.assertTrue(any("文献证据契约阻断" in item for item in enriched.review_gate.warnings))
        self.assertTrue(any("01-literature-evidence-contract.md" in item for item in enriched.review_gate.required_actions))

    def test_citation_audit_flags_unverifiable_references(self) -> None:
        review = LiteratureReview(
            topic="robot manipulator path planning",
            papers=[
                Paper(
                    title="Verified robot planner",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="Robotics Journal",
                    url="https://doi.org/10.1234/example",
                    abstract="Robot manipulator motion planning benchmark.",
                    relevance=0.9,
                    source="openalex",
                    sources=["openalex"],
                    doi="10.1234/example",
                ),
                Paper(
                    title="Manual unverifiable planner",
                    authors=[],
                    year=0,
                    venue="Manual seed",
                    url="",
                    abstract="Manual note.",
                    relevance=0.7,
                    source="manual_seed",
                    sources=["manual_seed"],
                ),
            ],
            themes=["Robot manipulator motion planning benchmark requires verifiable references."],
            gaps=["缺少稳定 DOI 或 URL 的引用需要人工处理。"],
            summary="测试综述",
        )
        context = build_literature_context(review)
        audit = audit_citations(context)
        rendered = render_citation_audit_markdown(audit)
        gated = apply_citation_audit_to_context(context, audit)

        self.assertEqual(audit.total_citations, 2)
        self.assertEqual(audit.usable_citations, 1)
        self.assertEqual(audit.blocked_citations, 1)
        self.assertEqual(audit.integrity_status, "block")
        self.assertGreater(audit.integrity_layers["metadata_pass_rate"], 0)
        self.assertEqual(gated.review_gate.status, "block")
        self.assertTrue(any("引用完整性审计状态" in item for item in gated.review_gate.warnings))
        self.assertIn("missing DOI", rendered)
        self.assertIn("完整性分层", rendered)
        self.assertIn("引用审计", rendered)


if __name__ == "__main__":
    unittest.main()
