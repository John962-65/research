from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from research_agent.config import PaperGradeConfig
from research_agent.literature_gate_decision import (
    LITERATURE_GATE_DECISION_JSON,
    LITERATURE_GATE_DECISION_MD,
    build_literature_gate_decision,
    write_literature_gate_decision_artifacts,
)


class LiteratureGateDecisionTest(unittest.TestCase):
    def test_gate_blocks_weak_sources_and_blocked_citations(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 2, "total_papers": 10, "confidence_status": "weak", "confidence_score": 0.48},
            source_health_report={"sources_with_success": 0, "failed_sources": 2, "rate_limited_sources": 1},
            citation_audit_report={"integrity_status": "block", "blocked_citations": 1, "review_required": 0, "usable_citations": 1, "total_citations": 2},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(report["blocks_downstream"])
        self.assertIn("idea_generation", report["blocks"])
        self.assertGreaterEqual(len(report["blocking_reasons"]), 2)
        self.assertTrue(any("不要批准进入 idea/实验" in item for item in report["required_actions"]))

    def test_gate_requires_review_for_rescue_and_seed_role_gaps(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 5, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            rescue_report={"status": "needs_rescue_search", "rescue_queries": [{"query": "robot benchmark"}], "required_actions": ["补检索后重跑。"]},
            seed_intake_report={"status": "pass", "role_coverage_status": "review_required", "curated_seed_papers": 2, "total_seed_entries": 3},
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 5, "total_citations": 5},
        )

        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["blocks_downstream"])
        self.assertTrue(report["human_approval_required"])
        self.assertTrue(any("approval notes" in item for item in report["approval_guidance"]))

    def test_gate_requires_review_when_literature_is_not_paper_grade(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 6, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            source_health_report={"provider": "offline", "configured_source_count": 1, "sources_with_success": 1, "failed_sources": 0, "rate_limited_sources": 0},
            query_execution_report={"status": "pass", "selected_query_count": 4, "raw_candidate_count": 12, "source_coverage": {"configured_source_count": 1, "sources_with_success": 1}},
            seed_intake_report={"status": "not_configured", "role_coverage_status": "review_required", "curated_seed_papers": 0, "total_seed_entries": 0, "doi_entries": 0, "url_entries": 0, "title_only_entries": 0},
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 6, "total_citations": 6},
        )

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["paper_grade_literature"]["status"], "review_required")
        self.assertFalse(report["blocks_downstream"])
        self.assertTrue(any("provider=online/auto" in item for item in report["paper_grade_literature"]["issues"]))
        suggestions = report["paper_grade_literature"]["repair_suggestions"]
        kinds = {item["kind"] for item in suggestions}
        self.assertIn("set_literature_provider", kinds)
        self.assertIn("increase_literature_sources", kinds)
        self.assertIn("repair_doi_url_seed_papers", kinds)
        self.assertTrue(any(item.get("recommended_config", {}).get("sources") for item in suggestions))
        self.assertTrue(any("DOI/URL seed" in item for item in report["required_actions"]))

    def test_gate_blocks_failed_citation_grounding(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 6, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            context_report={"citations": 6, "chunks": 6, "claim_support": 3},
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 6, "total_citations": 6},
            citation_grounding_report={"status": "block", "grounding_score": 0.45, "blocked_citations": 2, "review_citations": 1, "passed_citations": 3, "total_citations": 6},
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(report["blocks_downstream"])
        self.assertEqual(report["summary"]["citation_grounding_status"], "block")
        self.assertEqual(report["summary"]["citation_grounding_blocked"], 2)
        self.assertTrue(any("grounding" in item for item in report["blocking_reasons"]))

    def test_gate_blocks_failed_evidence_contract(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 6, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            context_report={"citations": 6, "chunks": 6, "claim_support": 3},
            evidence_contract_report={
                "status": "block",
                "summary": {"chunk_coverage": 0.5, "substantive_chunk_coverage": 0.2, "median_chunk_chars": 90, "locator_coverage": 0.4, "single_crossref_ratio": 0.7},
                "blocking_issues": ["单源 Crossref 题录不能主导 RAG/context。"],
                "review_reasons": [],
                "required_actions": ["补 DOI seed 后重跑。"],
            },
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 6, "total_citations": 6},
        )

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["summary"]["evidence_contract_status"], "block")
        self.assertEqual(report["summary"]["evidence_contract_blocking"], 1)
        self.assertEqual(report["summary"]["evidence_contract_substantive_chunk_coverage"], 0.2)
        self.assertEqual(report["summary"]["evidence_contract_median_chunk_chars"], 90)
        self.assertTrue(any("证据契约" in item for item in report["blocking_reasons"]))
        self.assertTrue(any("补 DOI seed" in item for item in report["required_actions"]))

    def test_gate_passes_when_all_signals_pass(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 6, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            source_health_report={"provider": "online", "configured_source_count": 3, "sources_with_success": 2, "failed_sources": 0, "rate_limited_sources": 0},
            query_execution_report={"status": "pass", "selected_query_count": 4, "raw_candidate_count": 20, "source_coverage": {"configured_source_count": 3, "sources_with_success": 2}},
            rerank_report={"status": "pass", "warnings": [], "recommended_actions": []},
            coverage_report={"status": "pass", "coverage_ratio": 1.0, "covered_required": 4, "total_required": 4},
            evidence_mix_report={"status": "pass", "mix_score": 0.88, "summary": {"anchor_coverage": 1.0}},
            rescue_report={"status": "pass", "rescue_queries": [], "required_actions": []},
            rescue_execution_report={"status": "not_needed", "new_unique_papers": 0, "unresolved_query_outcomes": 0},
            seed_intake_report={
                "status": "pass",
                "role_coverage_status": "pass",
                "curated_seed_papers": 3,
                "total_seed_entries": 3,
                "doi_entries": 2,
                "url_entries": 1,
                "title_only_entries": 0,
                "metadata_resolved_seed_papers": 3,
                "metadata_unresolved_doi_url_seed_papers": 0,
            },
            evidence_contract_report={
                "status": "pass",
                "summary": {"chunk_coverage": 1.0, "substantive_chunk_coverage": 1.0, "median_chunk_chars": 240, "locator_coverage": 1.0, "single_crossref_ratio": 0.0},
                "blocking_issues": [],
                "review_reasons": [],
                "required_actions": [],
            },
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 6, "total_citations": 6},
            context_report={"citations": 6, "chunks": 8, "claim_support": 4},
            citation_grounding_report={"status": "pass", "grounding_score": 1.0, "blocked_citations": 0, "review_citations": 0, "passed_citations": 6, "total_citations": 6},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["decision"], "ready_for_human_approval")
        self.assertEqual(report["blocking_reasons"], [])
        self.assertEqual(report["paper_grade_literature"]["status"], "pass")

    def test_paper_grade_literature_uses_configured_thresholds(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 6, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            source_health_report={"provider": "online", "configured_source_count": 3, "sources_with_success": 2, "failed_sources": 0, "rate_limited_sources": 0},
            query_execution_report={"status": "pass", "selected_query_count": 4, "raw_candidate_count": 20, "source_coverage": {"configured_source_count": 3, "sources_with_success": 2}},
            seed_intake_report={
                "status": "pass",
                "role_coverage_status": "pass",
                "curated_seed_papers": 3,
                "total_seed_entries": 3,
                "doi_entries": 2,
                "url_entries": 1,
                "title_only_entries": 0,
                "metadata_resolved_seed_papers": 3,
                "metadata_unresolved_doi_url_seed_papers": 0,
                "curated_seed_role_counts": {"review": 1, "benchmark_dataset": 1, "baseline_method": 1, "recent": 0},
            },
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 6, "total_citations": 6},
            paper_grade_config=PaperGradeConfig(
                enabled=True,
                min_literature_sources=4,
                min_successful_literature_sources=3,
                min_seed_papers=4,
                min_doi_url_seed_papers=4,
                min_curated_seed_roles=4,
            ),
        )

        paper_grade = report["paper_grade_literature"]
        self.assertEqual(report["status"], "review_required")
        self.assertEqual(paper_grade["status"], "review_required")
        summary = paper_grade["summary"]
        self.assertEqual(summary["min_configured_sources"], 4)
        self.assertEqual(summary["min_sources_with_success"], 3)
        self.assertEqual(summary["min_total_seed_entries"], 4)
        self.assertEqual(summary["min_strong_seed_entries"], 4)
        self.assertEqual(summary["min_seed_role_classes"], 4)
        self.assertEqual(summary["seed_role_classes"], 3)
        issues_text = "\n".join(paper_grade["issues"])
        self.assertIn("4 个在线来源", issues_text)
        self.assertIn("3 个来源成功返回", issues_text)
        self.assertIn("4 条人工 seed", issues_text)
        self.assertIn("4 类", issues_text)
        suggestions_text = "\n".join(str(item.get("action") or "") for item in paper_grade["repair_suggestions"])
        self.assertIn("至少 4 个在线来源", suggestions_text)
        self.assertIn("至少 4 条进入 curated context", suggestions_text)

    def test_paper_grade_literature_requires_resolved_seed_metadata(self) -> None:
        report = build_literature_gate_decision(
            topic="机械臂路径规划",
            quality_report={"selected_papers": 6, "total_papers": 12, "confidence_status": "pass", "confidence_score": 0.82},
            source_health_report={"provider": "online", "configured_source_count": 3, "sources_with_success": 2, "failed_sources": 0, "rate_limited_sources": 0},
            query_execution_report={"status": "pass", "selected_query_count": 4, "raw_candidate_count": 20, "source_coverage": {"configured_source_count": 3, "sources_with_success": 2}},
            seed_intake_report={
                "status": "pass",
                "role_coverage_status": "pass",
                "curated_seed_papers": 3,
                "total_seed_entries": 3,
                "doi_entries": 3,
                "url_entries": 0,
                "title_only_entries": 0,
                "metadata_resolved_seed_papers": 1,
                "metadata_unresolved_doi_url_seed_papers": 2,
            },
            citation_audit_report={"integrity_status": "pass", "blocked_citations": 0, "review_required": 0, "usable_citations": 6, "total_citations": 6},
        )

        self.assertEqual(report["paper_grade_literature"]["status"], "review_required")
        self.assertTrue(any("解析到来源题录元数据" in item for item in report["paper_grade_literature"]["issues"]))
        suggestion = next(item for item in report["paper_grade_literature"]["repair_suggestions"] if item["kind"] == "repair_doi_url_seed_papers")
        self.assertEqual(suggestion["metadata_unresolved_doi_url_seed_papers"], 2)

    def test_write_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = write_literature_gate_decision_artifacts(
                topic="科研 agent",
                quality_report={"selected_papers": 0, "total_papers": 0, "confidence_status": "block"},
                source_health_report={},
                query_execution_report={},
                rerank_report={},
                coverage_report={},
                evidence_mix_report={},
                rescue_report={},
                rescue_execution_report={},
                seed_intake_report={},
                citation_audit_report={},
                context_report={},
                citation_grounding_report={},
                run_dir=out,
            )

            self.assertEqual(report["status"], "block")
            self.assertTrue((out / LITERATURE_GATE_DECISION_JSON).exists())
            self.assertIn("文献证据总门禁", (out / LITERATURE_GATE_DECISION_MD).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
