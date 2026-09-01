from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.config import LiteratureConfig
from research_agent.literature_search_feedback import (
    LITERATURE_SEARCH_FEEDBACK_JSON,
    LITERATURE_SEARCH_FEEDBACK_MD,
    build_literature_search_feedback,
    render_literature_search_feedback_markdown,
    write_literature_search_feedback_artifacts,
)
from research_agent.models import LiteratureReview, Paper, ResearchPlan


class LiteratureSearchFeedbackTest(unittest.TestCase):
    def test_feedback_consolidates_rescue_queries_source_actions_and_seed_targets(self) -> None:
        plan = _plan()
        raw = _review([_paper("Generic robot paper", doi="")], source_health=[{"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True}])
        curated = _review([_paper("Generic robot paper", doi="")])
        quality = {"confidence_status": "weak", "confidence_score": 0.42, "selected_papers": 1}
        snowball = {"expansion_queries": [{"query": "robot arm RRT* benchmark", "priority": 82, "purpose": "baseline"}]}
        coverage = {
            "status": "needs_coverage",
            "coverage_ratio": 0.4,
            "missing_required": [
                {
                    "category": "baseline",
                    "name": "RRT*",
                    "suggested_queries": ["robot manipulator motion planning RRT star baseline comparison"],
                },
                {
                    "category": "benchmark",
                    "name": "OMPL",
                    "suggested_queries": ["robot manipulator motion planning OMPL benchmark evaluation"],
                },
            ],
        }
        rescue = {
            "status": "needs_source_repair",
            "source_repairs": ["设置 SEMANTIC_SCHOLAR_API_KEY 后重跑，避免 Semantic Scholar 429。"],
            "rescue_queries": [{"query": "robot manipulator OMPL RRT* CHOMP", "priority": 98, "kind": "domain", "rationale": "覆盖 baseline matrix"}],
        }
        source_health = {"rate_limited_sources": 1, "failed_sources": 0}

        report = build_literature_search_feedback(plan, raw, curated, quality, snowball, coverage, rescue, source_health, LiteratureConfig(provider="offline", max_papers=4, max_search_queries=2))
        rendered = render_literature_search_feedback_markdown(report)

        self.assertEqual(report["status"], "needs_source_repair")
        self.assertTrue(report["retrieval_repair_tasks"])
        self.assertEqual(report["next_run_config"]["literature_provider"], "online")
        self.assertGreaterEqual(report["next_run_config"]["max_papers"], 12)
        self.assertGreaterEqual(report["next_run_config"]["max_search_queries"], 6)
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in report["source_actions"]))
        self.assertTrue(any("robot manipulator OMPL RRT*" in item["query"] for item in report["recommended_queries"]))
        self.assertTrue(any(item["source"] == "missing_facet_suggested" and "RRT star" in item["query"] for item in report["recommended_queries"]))
        self.assertTrue(any(item["name"] == "RRT*" for item in report["seed_paper_targets"]))
        self.assertIn("文献检索反馈策略", rendered)
        self.assertIn("推荐检索式", rendered)
        self.assertIn("检索修复任务", rendered)

    def test_feedback_artifacts_write_ready_for_review_when_audits_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            plan = _plan()
            papers = [_paper("Sampling-based Algorithms for Optimal Motion Planning", doi="10.1177/0278364911406761")]
            raw = _review(papers, search_strategy={"selected_queries": ["robot manipulator motion planning"]})
            curated = _review(papers)

            report = write_literature_search_feedback_artifacts(
                plan,
                raw,
                curated,
                {"confidence_status": "pass", "confidence_score": 0.9, "selected_papers": 5},
                {"expansion_queries": []},
                {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
                {"status": "pass", "rescue_queries": [], "source_repairs": []},
                {"rate_limited_sources": 0, "failed_sources": 0},
                LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
                run_dir,
            )

            saved = json.loads((run_dir / LITERATURE_SEARCH_FEEDBACK_JSON).read_text(encoding="utf-8"))
            self.assertIn(report["status"], {"ready_for_review", "pass"})
            self.assertEqual(saved["topic"], "机械臂路径规划")
            self.assertTrue((run_dir / LITERATURE_SEARCH_FEEDBACK_MD).exists())

    def test_feedback_keeps_optional_rate_limit_as_review_when_fallback_sources_succeed(self) -> None:
        plan = _plan()
        papers = [_paper(f"Robot manipulator benchmark baseline {index}") for index in range(8)]
        raw = _review(papers)
        curated = _review(papers)

        report = build_literature_search_feedback(
            plan,
            raw,
            curated,
            {"confidence_status": "pass", "confidence_score": 0.9, "selected_papers": 8},
            {"expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
            {
                "status": "pass",
                "rescue_queries": [],
                "source_repairs": ["设置 SEMANTIC_SCHOLAR_API_KEY 后重跑，避免 Semantic Scholar 429。"],
            },
            {"sources_with_success": 2, "rate_limited_sources": 1, "failed_sources": 0},
            LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
        )

        self.assertEqual(report["status"], "pass")
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in report["source_actions"]))

    def test_feedback_surfaces_seed_intake_repair(self) -> None:
        plan = _plan()
        raw = _review([_paper("Generic robot paper")])
        curated = _review([_paper("Generic robot paper")])
        seed_intake = {
            "status": "block",
            "total_seed_entries": 1,
            "curated_seed_papers": 0,
            "required_actions": ["修复未进入原始池的 seed。"],
        }

        report = build_literature_search_feedback(
            plan,
            raw,
            curated,
            {"confidence_status": "pass", "confidence_score": 0.9, "selected_papers": 5},
            {"expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
            {"status": "pass", "rescue_queries": [], "source_repairs": []},
            {"rate_limited_sources": 0, "failed_sources": 0},
            LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
            seed_intake_report=seed_intake,
        )
        rendered = render_literature_search_feedback_markdown(report)

        self.assertEqual(report["status"], "needs_manual_seed")
        self.assertTrue(any(item["category"] == "seed_intake" for item in report["seed_paper_targets"]))
        self.assertIn("Seed intake", rendered)

    def test_feedback_surfaces_seed_role_coverage_repair(self) -> None:
        plan = _plan()
        raw = _review([_paper("Generic robot paper")])
        curated = _review([_paper("Generic robot paper")])
        seed_intake = {
            "status": "pass",
            "role_coverage_status": "review_required",
            "total_seed_entries": 3,
            "curated_seed_papers": 3,
            "missing_curated_seed_roles": ["review", "benchmark_dataset"],
            "required_actions": ["补齐进入 curated context 的 seed 角色覆盖。"],
        }

        report = build_literature_search_feedback(
            plan,
            raw,
            curated,
            {"confidence_status": "pass", "confidence_score": 0.9, "selected_papers": 5},
            {"expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
            {"status": "pass", "rescue_queries": [], "source_repairs": []},
            {"rate_limited_sources": 0, "failed_sources": 0},
            LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
            seed_intake_report=seed_intake,
        )
        rendered = render_literature_search_feedback_markdown(report)

        self.assertEqual(report["status"], "needs_manual_seed")
        self.assertEqual(report["diagnosis"]["seed_role_coverage_status"], "review_required")
        self.assertTrue(any(item["category"] == "seed_intake" for item in report["seed_paper_targets"]))
        self.assertTrue(any(item["category"] == "seed_repair" for item in report["retrieval_repair_tasks"]))
        self.assertIn("角色覆盖：review_required", rendered)

    def test_feedback_turns_rerank_and_evidence_mix_findings_into_repair_tasks(self) -> None:
        plan = _plan()
        raw = _review([_paper("Generic robot paper")])
        curated = _review([_paper("Generic robot paper")])
        rerank = {
            "status": "review_required",
            "warnings": ["Top 候选仍包含标题过泛或对象不匹配的题录，建议补核心方法/benchmark DOI seed。"],
            "items": [
                {
                    "title": "Path planning applications overview",
                    "penalties": ["generic title/object mismatch", "weak venue/source signal"],
                }
            ],
        }
        evidence_mix = {
            "status": "needs_evidence_upgrade",
            "mix_score": 0.42,
            "anchor_checks": [
                {
                    "name": "benchmark_or_dataset_anchor",
                    "required": True,
                    "status": "missing",
                    "matched_terms": ["OMPL", "benchmark"],
                    "action": "补覆盖公开 benchmark 的文献。",
                }
            ],
        }

        report = build_literature_search_feedback(
            plan,
            raw,
            curated,
            {"confidence_status": "pass", "confidence_score": 0.9, "selected_papers": 5},
            {"expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
            {"status": "pass", "rescue_queries": [], "source_repairs": []},
            {"rate_limited_sources": 0, "failed_sources": 0},
            LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
            rerank_report=rerank,
            evidence_mix_report=evidence_mix,
        )

        categories = {item["category"] for item in report["retrieval_repair_tasks"]}
        self.assertIn("rerank_repair", categories)
        self.assertIn("evidence_anchor_repair", categories)
        self.assertTrue(all(item["task_id"].startswith("retrieval-repair-") for item in report["retrieval_repair_tasks"]))

    def test_feedback_turns_query_execution_failures_into_executable_repair_tasks(self) -> None:
        plan = _plan()
        raw = _review([_paper("Generic robot paper")])
        curated = _review([_paper("Generic robot paper")])
        query_execution = {
            "status": "needs_query_repair",
            "selected_query_count": 2,
            "queries": [
                {
                    "query": "RRT* CHOMP robot arm trajectory optimization",
                    "intent": "baseline",
                    "status": "no_candidate_hits",
                    "candidate_hits": 0,
                    "high_quality_hits": 0,
                    "actions": ["收窄或重写检索式，并加入核心 DOI/URL seed。"],
                }
            ],
        }

        report = build_literature_search_feedback(
            plan,
            raw,
            curated,
            {"confidence_status": "pass", "confidence_score": 0.9, "selected_papers": 5},
            {"expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
            {"status": "pass", "rescue_queries": [], "source_repairs": []},
            {"rate_limited_sources": 0, "failed_sources": 0},
            LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
            query_execution_report=query_execution,
        )
        rendered = render_literature_search_feedback_markdown(report)

        self.assertEqual(report["status"], "needs_search_revision")
        self.assertEqual(report["diagnosis"]["query_execution_status"], "needs_query_repair")
        self.assertTrue(any(item["source"] == "query_execution" and "baseline method comparison DOI" in item["query"] for item in report["recommended_queries"]))
        self.assertTrue(any(item["category"] == "query_execution_repair" and item["owner"] == "agent" for item in report["retrieval_repair_tasks"]))
        self.assertIn("query_execution_status", json.dumps(report["diagnosis"], ensure_ascii=False))
        self.assertIn("Query/Seed", rendered)

    def test_feedback_turns_missing_evidence_roles_into_queries_tasks_and_seed_targets(self) -> None:
        plan = _plan()
        raw = _review([_paper("Generic robot paper")])
        curated = _review([_paper("Generic robot paper") for _ in range(5)])
        quality = {
            "confidence_status": "weak",
            "confidence_score": 0.52,
            "selected_papers": 5,
            "missing_evidence_roles": ["review_survey", "benchmark_dataset", "baseline_method"],
        }

        report = build_literature_search_feedback(
            plan,
            raw,
            curated,
            quality,
            {"expansion_queries": []},
            {"status": "pass", "coverage_ratio": 1.0, "missing_required": []},
            {"status": "pass", "rescue_queries": [], "source_repairs": []},
            {"rate_limited_sources": 0, "failed_sources": 0},
            LiteratureConfig(provider="online", max_papers=12, max_search_queries=6),
        )
        rendered = render_literature_search_feedback_markdown(report)

        self.assertEqual(report["status"], "needs_search_revision")
        self.assertEqual(report["diagnosis"]["missing_evidence_roles"], 3)
        self.assertGreaterEqual(report["next_run_config"]["seed_papers_min"], 6)
        self.assertTrue(any(item["source"] == "missing_evidence_role" and "survey review state of the art DOI" in item["query"] for item in report["recommended_queries"]))
        self.assertTrue(any(item["source"] == "missing_evidence_role" and "benchmark dataset evaluation protocol DOI" in item["query"] for item in report["recommended_queries"]))
        self.assertTrue(any(item["source"] == "missing_evidence_role" and "baseline method comparison DOI" in item["query"] for item in report["recommended_queries"]))
        self.assertTrue(any(item["category"] == "evidence_role_repair" and item["owner"] == "agent+human" for item in report["retrieval_repair_tasks"]))
        self.assertTrue(any(item["category"] == "evidence_role" and item["name"] == "review/survey evidence" for item in report["seed_paper_targets"]))
        self.assertIn("missing_evidence_role", rendered)
        self.assertIn("evidence_role_repair", rendered)


def _plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="规划避障路径",
        search_queries=["robot manipulator motion planning"],
        benchmarks=["OMPL"],
        baselines=["RRT*", "CHOMP"],
        metrics=["planning_time", "path_length"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _review(papers: list[Paper], source_health: list[dict[str, object]] | None = None, search_strategy: dict[str, object] | None = None) -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=papers,
        themes=[],
        gaps=[],
        summary="",
        source_health=source_health or [],
        search_strategy=search_strategy or {},
    )


def _paper(title: str, doi: str = "10.1234/example") -> Paper:
    return Paper(
        title=title,
        authors=["Ada"],
        year=2024,
        venue="Robotics",
        url=f"https://doi.org/{doi}" if doi else "",
        abstract="Robot manipulator motion planning with benchmark and baseline evidence.",
        relevance=0.8,
        source="openalex",
        sources=["openalex"],
        doi=doi,
    )


if __name__ == "__main__":
    unittest.main()
