from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.review_revision_plan import (
    REVIEW_REVISION_PLAN_JSON,
    REVIEW_REVISION_PLAN_MD,
    build_review_revision_plan,
    render_review_revision_plan_markdown,
    write_review_revision_plan_artifacts,
)


class ReviewRevisionPlanTest(unittest.TestCase):
    def test_builds_structured_repair_plan_from_review_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            approval = {
                "topic": "机械臂路径规划",
                "reviewer": "pi",
                "notes": "补充 RRT* 和 OMPL benchmark 文献",
                "gate_status": "literature_repair_required",
            }
            write_json(
                out / "01-context.json",
                {
                    "review_gate": {
                        "status": "literature_repair_required",
                        "warnings": ["baseline 覆盖不足"],
                        "required_actions": ["补齐 RRT* baseline 证据"],
                    }
                },
            )
            write_json(out / "01-literature-quality.json", {"confidence_status": "weak", "selected_papers": 2})
            write_json(out / "01-literature-coverage.json", {"status": "needs_coverage", "coverage_ratio": 0.4})
            write_json(out / "01-literature-rescue-plan.json", {"status": "needs_rescue_search"})
            write_json(out / "01-citation-audit.json", {"integrity_status": "block", "blocked_citations": 1})
            write_json(out / "01-literature-source-health.json", {"rate_limited_sources": 1, "failed_sources": 0})

            report = write_review_revision_plan_artifacts(out, approval)

            categories = [item["category"] for item in report["items"]]
            self.assertEqual(report["status"], "revision_requested")
            self.assertEqual(report["notes"], approval["notes"])
            self.assertIn("human_feedback", categories)
            self.assertIn("literature_rescue", categories)
            self.assertIn("coverage", categories)
            self.assertIn("quality", categories)
            self.assertIn("citation", categories)
            self.assertIn("source_health", categories)
            self.assertIn("gate_required_action", categories)
            self.assertIn("gate_warning", categories)
            self.assertTrue(report["rerun_commands"])
            self.assertTrue(report["stop_conditions"])
            self.assertTrue(report["next_approval_checklist"])
            self.assertTrue((out / REVIEW_REVISION_PLAN_JSON).exists())
            self.assertTrue((out / REVIEW_REVISION_PLAN_MD).exists())

            saved = json.loads((out / REVIEW_REVISION_PLAN_JSON).read_text(encoding="utf-8"))
            markdown = (out / REVIEW_REVISION_PLAN_MD).read_text(encoding="utf-8")
            self.assertEqual(saved["topic"], "机械臂路径规划")
            self.assertIn("Review Revision Plan", markdown)
            self.assertIn("补充 RRT*", markdown)
            self.assertIn("Resume 命令", markdown)

    def test_missing_audits_do_not_create_false_quality_findings(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "机械臂路径规划"})

            report = build_review_revision_plan(out, {"notes": "人工补充种子文献"})
            markdown = render_review_revision_plan_markdown(report)

            categories = [item["category"] for item in report["items"]]
            self.assertEqual(categories, ["human_feedback"])
            self.assertNotIn("selected_papers=0", markdown)
            self.assertIn("人工补充种子文献", markdown)

    def test_review_revision_plan_carries_literature_search_feedback(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "机械臂路径规划"})
            write_json(
                out / "01-literature-search-feedback.json",
                {
                    "status": "needs_search_revision",
                    "recommended_queries": [
                        {"query": "robot manipulator OMPL benchmark RRT* CHOMP", "priority": 96},
                        {"query": "TrajOpt STOMP robot arm trajectory optimization baseline", "priority": 90},
                    ],
                    "seed_paper_targets": [
                        {"category": "benchmark", "name": "OMPL benchmark", "hint": "补 OMPL DOI"},
                        {"category": "baseline", "name": "RRT* baseline", "hint": "补 RRT* DOI"},
                    ],
                    "retrieval_repair_tasks": [
                        {
                            "priority": 96,
                            "owner": "agent",
                            "action": "执行补检索式并合并去重候选。",
                            "query": "robot manipulator OMPL benchmark RRT* CHOMP",
                        }
                    ],
                    "next_run_config": {
                        "literature_provider": "online",
                        "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
                        "max_papers": 14,
                        "max_search_queries": 7,
                        "seed_papers_min": 3,
                    },
                },
            )

            report = build_review_revision_plan(out, {"notes": "论文质量差，退回补检索"})
            markdown = render_review_revision_plan_markdown(report)

        categories = [item["category"] for item in report["items"]]
        self.assertIn("literature_search_feedback", categories)
        self.assertIn("search_feedback_query", categories)
        self.assertIn("search_feedback_seed", categories)
        self.assertEqual(report["literature_search_feedback"]["status"], "needs_search_revision")
        self.assertEqual(report["literature_search_feedback"]["next_run_config"]["max_papers"], 14)
        self.assertTrue(any("--max-search-queries 7" in item for item in report["rerun_commands"]))
        self.assertTrue(any("--extra-search-query" in item and "OMPL benchmark" in item for item in report["rerun_commands"]))
        self.assertIn("检索反馈承接", markdown)
        self.assertIn("robot manipulator OMPL", markdown)
        self.assertIn("OMPL benchmark", markdown)
        self.assertTrue(any("01-literature-search-feedback.md" in item for item in report["stop_conditions"]))
        self.assertTrue(any("next_run_config" in item for item in report["next_approval_checklist"]))

    def test_review_revision_plan_carries_seed_role_coverage_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "机械臂路径规划"})
            write_json(
                out / "01-seed-paper-intake.json",
                {
                    "status": "pass",
                    "role_coverage_status": "review_required",
                    "total_seed_entries": 3,
                    "curated_seed_papers": 3,
                    "missing_curated_seed_roles": ["review", "benchmark_dataset"],
                    "required_actions": ["补齐进入 curated context 的 seed 角色覆盖。"],
                },
            )

            report = build_review_revision_plan(out, {"notes": "seed 结构不够，退回补文献"})
            markdown = render_review_revision_plan_markdown(report)

        item = next(value for value in report["items"] if value["category"] == "seed_paper_intake")
        self.assertIn("角色覆盖", item["action"])
        self.assertIn("missing_roles=review, benchmark_dataset", item["rationale"])
        self.assertTrue(any("角色覆盖不再是 review_required" in value for value in report["stop_conditions"]))
        self.assertIn("角色覆盖", markdown)


if __name__ == "__main__":
    unittest.main()
