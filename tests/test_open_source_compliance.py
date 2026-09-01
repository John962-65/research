from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.open_source_compliance import (
    OPEN_SOURCE_COMPLIANCE_JSON,
    OPEN_SOURCE_COMPLIANCE_MD,
    build_open_source_compliance_report,
    render_open_source_compliance_markdown,
    write_open_source_compliance_artifacts,
)
from research_agent.repair_queue import build_repair_queue_report
from research_agent.scorecard import build_research_scorecard_report


class OpenSourceComplianceTest(unittest.TestCase):
    def test_compliance_passes_when_external_lessons_have_artifact_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)

            report = write_open_source_compliance_artifacts("机械臂路径规划", run_dir)
            rendered = render_open_source_compliance_markdown(report)
            json_exists = (run_dir / OPEN_SOURCE_COMPLIANCE_JSON).exists()
            md_exists = (run_dir / OPEN_SOURCE_COMPLIANCE_MD).exists()

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["schema_version"], 3)
        self.assertGreaterEqual(report["score"], 0.99)
        self.assertEqual(report["source_project_summary"]["project_count"], 5)
        self.assertEqual(report["source_project_summary"]["blocked_project_count"], 0)
        self.assertFalse(report["blocking_issues"])
        self.assertIn("来源项目闭环", rendered)
        self.assertIn("structured_idea_to_experiment_loop", rendered)
        self.assertTrue(json_exists)
        self.assertTrue(md_exists)

    def test_compliance_blocks_when_query_execution_lesson_is_not_satisfied(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "01-query-execution-audit.json",
                {"status": "needs_source_repair", "blocking_issues": ["Semantic Scholar 429 导致 selected query 没有 source 返回。"]},
            )

            report = build_open_source_compliance_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        lesson = next(item for item in report["lesson_results"] if item["lesson_id"] == "query_execution_coverage_audit")
        self.assertEqual(lesson["status"], "block")
        self.assertIn("Future-House/PaperQA2", report["source_project_summary"]["blocked_projects"])
        self.assertIn("OpenScholar", report["source_project_summary"]["blocked_projects"])
        self.assertTrue(any("Semantic Scholar 429" in item for item in report["blocking_issues"]))

    def test_compliance_blocks_when_source_project_provenance_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            data = {
                "lessons": [
                    {
                        "lesson_id": "source_project_provenance",
                        "source_projects": ["AI-Scientist-v2"],
                        "pipeline_targets": ["open_source_lessons"],
                        "requirement": "开源项目约束必须带 provenance。",
                    }
                ],
                "profiles": [{"name": "SakanaAI/AI-Scientist-v2", "url": "https://github.com/SakanaAI/AI-Scientist-v2"}],
            }
            write_json(run_dir / "00-open-source-lessons.json", data)

            report = build_open_source_compliance_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        lesson = next(item for item in report["lesson_results"] if item["lesson_id"] == "source_project_provenance")
        self.assertEqual(lesson["status"], "block")
        self.assertTrue(any("project_evidence" in item for item in report["blocking_issues"]))

    def test_compliance_blocks_when_lesson_contract_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            data = json.loads((run_dir / "00-open-source-lessons.json").read_text(encoding="utf-8"))
            data.pop("contract_summary", None)
            write_json(run_dir / "00-open-source-lessons.json", data)

            report = build_open_source_compliance_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertEqual(report["contract_summary"]["status"], "block")
        self.assertTrue(any("contract_summary" in item for item in report["blocking_issues"]))

    def test_compliance_warns_when_seed_role_coverage_is_weak(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "01-seed-paper-intake.json",
                {
                    "status": "pass",
                    "role_coverage_status": "review_required",
                    "total_seed_entries": 3,
                    "curated_seed_papers": 3,
                    "missing_curated_seed_roles": ["review", "benchmark_dataset"],
                    "required_actions": ["补齐进入 curated context 的 seed 角色覆盖。"],
                },
            )

            report = build_open_source_compliance_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "needs_human_review")
        lesson = next(item for item in report["lesson_results"] if item["lesson_id"] == "retrieval_rerank_before_synthesis")
        self.assertEqual(lesson["status"], "warn")
        self.assertTrue(any("01-seed-paper-intake.json=pass:review_required" in item for item in lesson["evidence"]))
        self.assertTrue(any("seed 角色覆盖" in item for item in report["manual_tasks"]))

    def test_compliance_uses_seed_suggestions_when_seed_intake_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            (run_dir / "01-seed-paper-intake.json").unlink()
            write_json(
                run_dir / "01-literature-quality.json",
                {
                    "selected_papers": 2,
                    "items": [
                        {
                            "title": "The Open Motion Planning Library",
                            "doi": "10.1109/MRA.2012.2205651",
                            "url": "https://doi.org/10.1109/MRA.2012.2205651",
                            "selected": True,
                            "quality_score": 0.94,
                            "evidence_roles": ["benchmark_dataset", "baseline_method"],
                        }
                    ],
                },
            )

            report = build_open_source_compliance_report("机械臂路径规划", run_dir)

        lesson = next(item for item in report["lesson_results"] if item["lesson_id"] == "retrieval_rerank_before_synthesis")
        self.assertEqual(report["status"], "needs_human_review")
        self.assertEqual(lesson["status"], "warn")
        self.assertTrue(any("suggested_seed_count=1" in item for item in lesson["evidence"]))
        self.assertTrue(any("survey review" in item for item in report["manual_tasks"]))

    def test_compliance_flows_into_repair_queue_and_scorecard(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "13-open-source-compliance.json", {"status": "block", "blocking_issues": ["外部项目约束未闭环"], "manual_tasks": []})
            write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0}, "blocking_issues": [], "manual_tasks": []})

            queue = build_repair_queue_report("机械臂路径规划", run_dir)
            scorecard = build_research_scorecard_report("机械臂路径规划", run_dir)

        self.assertEqual(queue.status, "blocked_repair_required")
        self.assertTrue(any(item.category == "open_source_compliance" for item in queue.items))
        self.assertEqual(scorecard.status, "blocked")
        self.assertTrue(any("13-open-source-compliance" in action for action in scorecard.next_actions))

    def test_query_repair_is_manual_when_paper_grade_literature_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "01-literature-gate-decision.json", {"status": "pass", "paper_grade_literature": {"status": "pass", "issues": []}})
            write_json(run_dir / "01-query-execution-audit.json", {"status": "needs_query_repair", "recommended_actions": ["补齐 selected_queries 缺失的检索意图：method"]})

            report = build_open_source_compliance_report("Iris benchmark smoke", run_dir)

        lesson = next(item for item in report["lesson_results"] if item["lesson_id"] == "query_execution_coverage_audit")
        self.assertEqual(report["status"], "needs_human_review")
        self.assertFalse(report["blocking_issues"])
        self.assertEqual(lesson["status"], "warn")
        self.assertTrue(any("method" in item for item in report["manual_tasks"]))


def _write_complete_inputs(run_dir: Path) -> None:
    write_json(
        run_dir / "00-open-source-lessons.json",
        {
            "lessons": [
                {
                    "lesson_id": "source_project_provenance",
                    "source_projects": ["AI-Scientist-v2", "PaperQA2", "OpenScholar", "AgentLaboratory", "MLAgentBench"],
                    "pipeline_targets": ["open_source_lessons"],
                    "requirement": "开源项目约束必须带 provenance。",
                },
                {
                    "lesson_id": "structured_idea_to_experiment_loop",
                    "source_projects": ["AI-Scientist-v2"],
                    "pipeline_targets": ["ideation", "experiment_plan"],
                    "requirement": "idea 到实验必须有结构化契约。",
                },
                {
                    "lesson_id": "query_execution_coverage_audit",
                    "source_projects": ["PaperQA2", "OpenScholar"],
                    "pipeline_targets": ["literature_search"],
                    "requirement": "必须审计 query/source 覆盖。",
                },
                {
                    "lesson_id": "retrieval_rerank_before_synthesis",
                    "source_projects": ["PaperQA2", "OpenScholar"],
                    "pipeline_targets": ["literature_rerank", "literature_quality"],
                    "requirement": "文献合成前必须完成重排、质量筛选、metadata 和 seed intake 审计。",
                },
                {
                    "lesson_id": "runtime_cost_observability",
                    "source_projects": ["AgentLaboratory", "MLAgentBench"],
                    "pipeline_targets": ["run_manifest", "run_economics"],
                    "requirement": "必须保留运行轨迹和成本审计。",
                },
            ],
            "profiles": [
                {"name": "SakanaAI/AI-Scientist-v2", "url": "https://github.com/SakanaAI/AI-Scientist-v2"},
                {"name": "Future-House/PaperQA2", "url": "https://github.com/Future-House/paper-qa"},
                {"name": "OpenScholar", "url": "https://github.com/AkariAsai/OpenScholar"},
                {"name": "SamuelSchmidgall/AgentLaboratory", "url": "https://github.com/SamuelSchmidgall/AgentLaboratory"},
                {"name": "MLAgentBench / MLE-bench-style tasks", "url": "https://github.com/snap-stanford/MLAgentBench"},
            ],
            "project_evidence": [
                {
                    "project_name": "SakanaAI/AI-Scientist-v2",
                    "repository_url": "https://github.com/SakanaAI/AI-Scientist-v2",
                    "status": "catalogued",
                    "verification_mode": "built_in_catalog",
                    "evidence_targets": ["README.md", "ai_scientist/"],
                    "verified_files": [],
                    "missing_files": [],
                },
                {
                    "project_name": "Future-House/PaperQA2",
                    "repository_url": "https://github.com/Future-House/paper-qa",
                    "status": "catalogued",
                    "verification_mode": "built_in_catalog",
                    "evidence_targets": ["README.md", "paperqa/"],
                    "verified_files": [],
                    "missing_files": [],
                },
                {
                    "project_name": "OpenScholar",
                    "repository_url": "https://github.com/AkariAsai/OpenScholar",
                    "status": "catalogued",
                    "verification_mode": "built_in_catalog",
                    "evidence_targets": ["README.md", "retriever", "rerank"],
                    "verified_files": [],
                    "missing_files": [],
                },
                {
                    "project_name": "SamuelSchmidgall/AgentLaboratory",
                    "repository_url": "https://github.com/SamuelSchmidgall/AgentLaboratory",
                    "status": "catalogued",
                    "verification_mode": "built_in_catalog",
                    "evidence_targets": ["README.md", "ai_lab_repo/"],
                    "verified_files": [],
                    "missing_files": [],
                },
                {
                    "project_name": "MLAgentBench / MLE-bench-style tasks",
                    "repository_url": "https://github.com/snap-stanford/MLAgentBench",
                    "status": "catalogued",
                    "verification_mode": "built_in_catalog",
                    "evidence_targets": ["README.md", "MLAgentBench/"],
                    "verified_files": [],
                    "missing_files": [],
                },
            ],
            "contract_summary": {
                "schema_version": 1,
                "profile_count": 5,
                "project_evidence_count": 5,
                "lesson_count": 5,
                "required_project_names": [
                    "SakanaAI/AI-Scientist-v2",
                    "Future-House/PaperQA2",
                    "OpenScholar",
                    "SamuelSchmidgall/AgentLaboratory",
                    "MLAgentBench / MLE-bench-style tasks",
                ],
                "project_evidence_names": [
                    "SakanaAI/AI-Scientist-v2",
                    "Future-House/PaperQA2",
                    "OpenScholar",
                    "SamuelSchmidgall/AgentLaboratory",
                    "MLAgentBench / MLE-bench-style tasks",
                ],
                "required_lesson_ids": [
                    "source_project_provenance",
                    "structured_idea_to_experiment_loop",
                    "query_execution_coverage_audit",
                    "retrieval_rerank_before_synthesis",
                    "runtime_cost_observability",
                ],
                "required_pipeline_targets": [
                    "open_source_lessons",
                    "ideation",
                    "experiment_plan",
                    "literature_search",
                    "literature_rerank",
                    "literature_quality",
                    "run_manifest",
                    "run_economics",
                ],
                "required_source_projects": [
                    "AI-Scientist-v2",
                    "PaperQA2",
                    "OpenScholar",
                    "AgentLaboratory",
                    "MLAgentBench",
                ],
            },
        },
    )
    write_json(run_dir / "00-prior-run-lessons.json", {"status": "pass"})
    write_json(run_dir / "02-ideas.json", [{"title": "A"}, {"title": "B"}])
    write_json(run_dir / "02-exploration-map.json", {"selected_branch_id": "B1"})
    write_json(run_dir / "02-experiment-manager.json", {"status": "pass"})
    write_json(run_dir / "03-experiment-plan.json", {"commands": [{"name": "run"}]})
    write_json(run_dir / "03-idea-experiment-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "01-literature-search-strategy.json", {"status": "pass"})
    write_json(run_dir / "01-query-execution-audit.json", {"status": "pass"})
    write_json(run_dir / "01-literature-source-health.json", {"status": "pass", "rate_limited_sources": 0, "failed_sources": 0, "query_attempts": 3, "query_successes": 3})
    write_json(run_dir / "run-manifest.json", {"events": [{"stage": "a"} for _ in range(6)], "artifacts": [{"path": "x"}]})
    write_json(run_dir / "run-llm-ledger.json", {"failed_calls": 0})
    write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass"})
    write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})

    # Minimal scorecard inputs outside the tested submission dimension.
    write_json(run_dir / "01-literature-quality.json", {"selected_papers": 5})
    write_json(run_dir / "01-citation-audit.json", {"total_citations": 5, "usable_citations": 5, "blocked_citations": 0, "doi_coverage": 1.0, "integrity_score": 1.0, "integrity_status": "pass"})
    write_json(run_dir / "01-context.json", {"citations": [{"key": str(i)} for i in range(5)], "chunks": [{"id": str(i)} for i in range(5)]})
    write_json(run_dir / "01-literature-rerank.json", {"status": "pass", "warnings": [], "recommended_actions": []})
    write_json(run_dir / "01-literature-metadata-audit.json", {"status": "pass", "blocked": 0})
    write_json(run_dir / "01-literature-snowball.json", {"status": "ready_for_review", "required_actions": []})
    write_json(run_dir / "01-literature-coverage.json", {"status": "pass", "coverage_ratio": 1.0})
    write_json(run_dir / "01-literature-evidence-mix.json", {"status": "pass", "mix_score": 1.0, "blocking_issues": [], "required_actions": []})
    write_json(
        run_dir / "01-literature-evidence-contract.json",
        {
            "status": "pass",
            "summary": {
                "citations": 5,
                "chunks": 5,
                "chunk_coverage": 1.0,
                "locator_coverage": 1.0,
                "single_crossref_ratio": 0.0,
                "evidence_role_count": 3,
            },
            "blocking_issues": [],
            "review_reasons": [],
            "required_actions": [],
        },
    )
    write_json(run_dir / "01-seed-paper-intake.json", {"status": "pass", "role_coverage_status": "pass", "total_seed_entries": 3, "curated_seed_papers": 3, "required_actions": []})
    write_json(run_dir / "01-literature-rescue-plan.json", {"status": "pass", "rescue_queries": [], "required_actions": []})
    write_json(run_dir / "02-novelty-audit.json", {"items": []})
    write_json(run_dir / "02-idea-audit.json", {"status": "pass", "blocked": 0, "review_required": 0})
    write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "benchmark", "repeats": 5}, "runs": [{"name": "r"}], "artifacts": [{"path": "metrics.json"}]})
    write_json(run_dir / "04-statistics.json", {"repeats": 5, "comparisons": [{"metric": "success"}]})
    write_json(run_dir / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "04-failure-analysis.json", {"status": "pass", "summary": {}})
    write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "04-benchmark-evidence-audit.json", {"status": "pass", "evidence_grade": "real_benchmark", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "04-experiment-decision.json", {"status": "pass", "decision": "proceed_to_paper"})
    write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 1.0})
    write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "03-experiment-audit.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "03-review-constraint-compliance.json", {"status": "pass", "blocked": 0, "review_required": 0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "03-execution-safety-audit.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "03-ablation-plan.json", {"status": "pass", "has_ablation": True})
    write_json(run_dir / "03-preregistration.json", {"status": "locked"})
    write_json(run_dir / "03-benchmark-plan.json", {"status": "pass", "selected_names": ["OMPL"], "required_actions": []})
    write_json(run_dir / "03-benchmark-readiness.json", {"status": "ready_for_benchmark", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "03-benchmark-adapters.json", {"blocking_issues": []})
    write_json(run_dir / "10-revised-paper-review.json", {"score": 8.5})
    write_json(run_dir / "07-paper-review-calibration.json", {"status": "pass"})
    write_json(run_dir / "10-claim-traceability.json", {"status": "pass", "traceability_score": 1.0, "blocked_claims": 0, "review_claims": 0})
    write_json(run_dir / "10-citation-grounding.json", {"status": "pass", "grounding_score": 1.0, "blocked_citations": 0, "review_citations": 0})
    write_json(run_dir / "10-citation-coverage.json", {"status": "pass", "coverage_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-results-presentation.json", {"status": "pass", "presentation_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-final-readiness.json", {"status": "ready", "unsupported_after": 0, "weak_after": 0, "deferred_tasks": 0, "blocking_issues": []})
    write_json(run_dir / "09-revision-response-audit.json", {"status": "pass", "response_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-release-metadata.json", {"status": "ready_for_release", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "04-environment-snapshot.json", {"status": "complete", "source_tree": {"file_count": 1}, "package_versions": ["pytest==1"]})
    write_json(run_dir / "10-ai-disclosure.json", {"status": "not_applicable"})
    write_json(run_dir / "10-submission-check.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "12-next-iteration-plan.json", {"status": "ready_for_submission_upload"})
    write_json(run_dir / "12-repair-resolution-audit.json", {"status": "not_applicable", "resolution_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-stage-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})


if __name__ == "__main__":
    unittest.main()
