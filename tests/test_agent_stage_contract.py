from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.agent_stage_contract import (
    AGENT_STAGE_CONTRACT_JSON,
    AGENT_STAGE_CONTRACT_MD,
    build_agent_stage_contract_report,
    render_agent_stage_contract_markdown,
    write_agent_stage_contract_artifacts,
)
from research_agent.artifacts import write_json


class AgentStageContractTest(unittest.TestCase):
    def test_stage_contract_passes_for_complete_auditable_run(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)
            rendered = render_agent_stage_contract_markdown(report)

            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["blocking_issues"])
            self.assertGreaterEqual(report["score"], 0.99)
            self.assertIn("Agent Stage Contract Audit", rendered)
            self.assertIn("literature_grounding", rendered)
            self.assertTrue(any(check["stage"] == "human_review_gate" and check["status"] == "pass" for check in report["checks"]))
            self.assertTrue(any("rescue_execution=executed:1/0:2" in "；".join(check["evidence"]) for check in report["checks"] if check["stage"] == "literature_grounding"))
            self.assertTrue(any("seed_intake=pass:pass:3/3" in "；".join(check["evidence"]) for check in report["checks"] if check["stage"] == "literature_grounding"))
            self.assertTrue(any("idea_experiment_contract=pass" in "；".join(check["evidence"]) for check in report["checks"] if check["stage"] == "experiment_design"))
            self.assertTrue(any("adapter_paper_grade=ready:0" in "；".join(check["evidence"]) for check in report["checks"] if check["stage"] == "execution_evidence"))
            self.assertTrue(any(check["stage"] == "open_source_lesson_contract" and check["status"] == "pass" for check in report["checks"]))

    def test_stage_contract_blocks_missing_grounding_and_unapproved_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 1})
            write_json(run_dir / "01-context.json", {"citations": [{"key": "a"}]})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": []})

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "literature_grounding" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any(check["stage"] == "human_review_gate" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("人工批准 review gate" in issue for issue in report["blocking_issues"]))

    def test_write_stage_contract_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)

            report = write_agent_stage_contract_artifacts("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / AGENT_STAGE_CONTRACT_JSON).exists())
            self.assertTrue((run_dir / AGENT_STAGE_CONTRACT_MD).exists())

    def test_stage_contract_blocks_failed_revision_response_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "09-revision-response-audit.json", {"status": "block", "response_score": 0.2, "blocking_issues": ["R01 缺少正文回应"], "manual_tasks": []})

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "paper_review_loop" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("R01" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_citation_coverage_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "10-citation-coverage.json", {"status": "block", "coverage_score": 0.2, "blocking_issues": ["正文引用覆盖过低"], "manual_tasks": []})

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "paper_review_loop" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("citation-coverage" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_idea_experiment_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "03-idea-experiment-contract.json", {"status": "block", "blocking_issues": ["idea 与实验计划断链"], "manual_tasks": []})

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "experiment_design" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("idea 到实验断链" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_query_execution_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "01-query-execution-audit.json",
                {
                    "status": "needs_source_repair",
                    "selected_query_count": 3,
                    "recommended_actions": ["设置 SEMANTIC_SCHOLAR_API_KEY 后重跑。"],
                },
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "literature_grounding" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_literature_rescue_execution(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "01-literature-rescue-execution.json",
                {
                    "status": "no_new_papers",
                    "trigger_status": "needs_rescue_search",
                    "new_unique_papers": 0,
                    "closed_query_outcomes": 0,
                    "unresolved_query_outcomes": 1,
                    "repair_task_ids": ["RQ-007"],
                    "required_actions": ["补检索没有带来新增去重候选；需要调整 query 后重跑。"],
                },
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "literature_grounding" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("补检索没有带来新增" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_reviews_rescue_residual_after_paper_grade_literature_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "01-literature-gate-decision.json", {"status": "pass", "paper_grade_literature": {"status": "pass", "issues": []}})
            write_json(
                run_dir / "01-literature-rescue-execution.json",
                {
                    "status": "no_new_papers",
                    "trigger_status": "needs_rescue_search",
                    "new_unique_papers": 0,
                    "closed_query_outcomes": 0,
                    "unresolved_query_outcomes": 1,
                    "repair_task_ids": ["RQ-007"],
                    "required_actions": ["补检索没有带来新增去重候选；需要调整 query 后重跑。"],
                },
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)
            literature = next(check for check in report["checks"] if check["stage"] == "literature_grounding")

            self.assertEqual(report["status"], "needs_human_review")
            self.assertFalse(report["blocking_issues"])
            self.assertEqual(literature["status"], "warn")
            self.assertTrue(any("paper-grade literature gate 已通过" in item for item in report["manual_tasks"]))

    def test_stage_contract_requires_review_for_seed_role_coverage(self) -> None:
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

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "needs_human_review")
            literature = next(check for check in report["checks"] if check["stage"] == "literature_grounding")
            self.assertEqual(literature["status"], "warn")
            self.assertTrue(any("seed_intake=pass:review_required:3/3" in item for item in literature["evidence"]))
            self.assertTrue(any("seed 角色覆盖" in item for item in report["manual_tasks"]))

    def test_stage_contract_requires_review_for_non_paper_grade_literature(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "01-literature-gate-decision.json",
                {
                    "status": "review_required",
                    "paper_grade_literature": {
                        "status": "review_required",
                        "issues": ["paper-grade 文献至少需要 2 个来源成功返回，当前 1。"],
                    },
                },
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "needs_human_review")
            literature = next(check for check in report["checks"] if check["stage"] == "literature_grounding")
            self.assertEqual(literature["status"], "warn")
            self.assertTrue(any("paper_grade_literature=review_required:1" in item for item in literature["evidence"]))
            self.assertTrue(any("来源成功返回" in item for item in report["manual_tasks"]))

    def test_stage_contract_requires_review_for_non_paper_grade_benchmark(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "04-benchmark-evidence-audit.json",
                {
                    "status": "review_required",
                    "evidence_grade": "local_experiment",
                    "adapter_paper_grade_status": "review_required",
                    "adapter_paper_grade_issues": ["缺少 baseline/ablation role 或 repeats/min_repeats。"],
                    "required_actions": ["补齐 paper-grade benchmark manifest 后重跑。"],
                    "blocking_issues": [],
                    "manual_tasks": ["补齐 paper-grade benchmark manifest 后重跑。"],
                },
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "needs_human_review")
            execution = next(check for check in report["checks"] if check["stage"] == "execution_evidence")
            self.assertEqual(execution["status"], "warn")
            self.assertTrue(any("adapter_paper_grade=review_required:1" in item for item in execution["evidence"]))
            self.assertTrue(any("paper-grade benchmark manifest" in item for item in report["manual_tasks"]))

    def test_stage_contract_blocks_unresolved_repair_resume_items(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "12-repair-resolution-audit.json", {"status": "block", "blocking_issues": ["原修复项仍未闭环"], "manual_tasks": []})

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "release_reproducibility" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("未闭环" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_agent_observability_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {"status": "block", "blocking_issues": ["run-manifest 没有 artifact inventory。"], "manual_tasks": []},
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "observability_resume" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("artifact inventory" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_run_economics_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "13-run-economics-audit.json",
                {"status": "block", "blocking_issues": ["run-llm-ledger.json 缺失或不可读"], "manual_tasks": []},
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "observability_resume" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("run-llm-ledger" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_blocks_failed_llm_runtime_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "13-llm-runtime-contract.json",
                {"status": "block", "blocking_issues": ["run-config.json 中 llm.api_key 非空"], "manual_tasks": []},
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "observability_resume" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("api_key" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_reviews_recovered_llm_failures(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "run-llm-ledger.json",
                {
                    "failed_calls": 1,
                    "budget_exceeded_calls": 0,
                    "entries": [
                        {"stage": "paper_writing", "purpose": "paper writing", "status": "failed"},
                        {"stage": "paper_writing", "purpose": "paper writing", "status": "success"},
                    ],
                },
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "needs_human_review")
            self.assertFalse(report["blocking_issues"])
            self.assertTrue(any(check["stage"] == "observability_resume" and check["status"] == "warn" for check in report["checks"]))

    def test_stage_contract_blocks_failed_open_source_compliance(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "13-open-source-compliance.json",
                {"status": "block", "score": 0.4, "checked_lessons": 10, "blocking_issues": ["外部项目约束未闭环"], "manual_tasks": []},
            )

            report = build_agent_stage_contract_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any(check["stage"] == "open_source_lesson_contract" and check["status"] == "block" for check in report["checks"]))
            self.assertTrue(any("外部项目约束未闭环" in issue for issue in report["blocking_issues"]))

    def test_stage_contract_reviews_stale_calibration_after_clean_revised_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(run_dir / "07-paper-review-calibration.json", {"status": "block", "blocking_issues": ["旧草稿 unsupported claim。"]})
            write_json(run_dir / "10-revised-paper-review.json", {"decision": "accept_with_minor_revisions", "unsupported_claims": []})
            write_json(
                run_dir / "10-final-readiness.json",
                {"status": "ready_for_submission_check", "unsupported_after": 0, "weak_after": 0, "blocking_issues": []},
            )
            write_json(run_dir / "10-claim-traceability.json", {"status": "pass"})

            report = build_agent_stage_contract_report("Iris benchmark smoke", run_dir)
            paper = next(check for check in report["checks"] if check["stage"] == "paper_review_loop")

            self.assertEqual(report["status"], "needs_human_review")
            self.assertFalse(report["blocking_issues"])
            self.assertEqual(paper["status"], "warn")
            self.assertTrue(any("原始草稿 calibration" in item for item in report["manual_tasks"]))

    def test_stage_contract_treats_high_repair_queue_as_manual_release_task(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_inputs(run_dir)
            write_json(
                run_dir / "12-repair-queue.json",
                {"status": "needs_repair", "summary": {"total": 1, "block": 0, "high": 1, "medium": 0}, "blocking_issues": [], "manual_tasks": ["人工确认结果呈现。"]},
            )

            report = build_agent_stage_contract_report("Iris benchmark smoke", run_dir)
            release = next(check for check in report["checks"] if check["stage"] == "release_reproducibility")

            self.assertEqual(report["status"], "needs_human_review")
            self.assertFalse(report["blocking_issues"])
            self.assertEqual(release["status"], "warn")
            self.assertTrue(any("repair-queue" in item or "12-repair-queue" in item for item in report["manual_tasks"]))


def _write_complete_inputs(run_dir: Path) -> None:
    write_json(
        run_dir / "00-research-plan.json",
        {
            "search_queries": ["robot manipulator motion planning RRT*"],
            "baselines": ["RRT*", "CHOMP"],
            "benchmarks": ["OMPL"],
            "metrics": ["planning time", "path length"],
        },
    )
    write_json(
        run_dir / "00-open-source-lessons.json",
        {
            "lessons": [{"lesson_id": "grounded-context", "requirement": "所有 idea 必须由可核验文献上下文支撑。"}],
            "project_evidence": [
                {
                    "project_name": "SakanaAI/AI-Scientist-v2",
                    "repository_url": "https://github.com/SakanaAI/AI-Scientist-v2",
                    "status": "catalogued",
                    "verification_mode": "built_in_catalog",
                    "evidence_targets": ["README.md"],
                }
            ],
        },
    )
    write_json(run_dir / "run-llm-ledger.json", {"failed_calls": 0})
    write_json(run_dir / "run-manifest.json", {"events": [{"stage": str(i)} for i in range(6)], "artifacts": [{"path": "x"}]})
    write_json(run_dir / "01-literature-rerank.json", {"status": "pass", "warnings": [], "recommended_actions": []})
    write_json(run_dir / "01-query-execution-audit.json", {"status": "pass", "selected_query_count": 3, "recommended_actions": []})
    write_json(run_dir / "01-literature-quality.json", {"selected_papers": 5})
    write_json(run_dir / "01-literature-metadata-audit.json", {"status": "pass", "blocked": 0})
    write_json(run_dir / "01-literature-coverage.json", {"status": "pass"})
    write_json(run_dir / "01-literature-evidence-mix.json", {"status": "pass", "mix_score": 0.9, "blocking_issues": [], "required_actions": []})
    write_json(run_dir / "01-literature-rescue-plan.json", {"status": "pass", "required_actions": []})
    write_json(
        run_dir / "01-literature-rescue-execution.json",
        {"status": "executed", "trigger_status": "needs_rescue_search", "new_unique_papers": 2, "closed_query_outcomes": 1, "unresolved_query_outcomes": 0, "required_actions": []},
    )
    write_json(run_dir / "01-seed-paper-intake.json", {"status": "pass", "role_coverage_status": "pass", "total_seed_entries": 3, "curated_seed_papers": 3, "required_actions": []})
    write_json(run_dir / "01-context.json", {"citations": [{"key": str(i)} for i in range(5)]})
    write_json(run_dir / "01-citation-audit.json", {"blocked_citations": 0})
    write_json(
        run_dir / "approval.json",
        {"approved": True, "gate_status": "pass", "notes": "", "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]},
    )
    write_json(run_dir / "01-review-constraints.json", {"constraints": [{"category": "baseline"}]})
    write_json(run_dir / "02-ideas.json", [{"title": "a"}, {"title": "b"}])
    write_json(run_dir / "02-novelty-audit.json", {"status": "pass"})
    write_json(run_dir / "02-idea-audit.json", {"status": "pass", "blocked": 0})
    write_json(run_dir / "02-exploration-map.json", {"selected_branch_id": "B1", "branches": [{"branch_id": "B1"}]})
    write_json(run_dir / "02-experiment-manager.json", {"status": "pass", "execution_policy": "standard", "planning_constraints": ["实验必须包含直接 baseline：RRT*。"]})
    write_json(run_dir / "03-experiment-plan.json", {"commands": [{"name": "run"}]})
    write_json(run_dir / "03-review-constraint-compliance.json", {"status": "pass", "blocked": 0})
    write_json(run_dir / "03-experiment-audit.json", {"status": "pass"})
    write_json(run_dir / "03-idea-experiment-contract.json", {"status": "pass", "contract_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "03-execution-safety-audit.json", {"status": "pass"})
    write_json(run_dir / "03-ablation-plan.json", {"status": "pass"})
    write_json(run_dir / "03-preregistration.json", {"status": "locked"})
    write_json(run_dir / "03-benchmark-plan.json", {"status": "ready"})
    write_json(run_dir / "03-benchmark-readiness.json", {"status": "ready_for_benchmark", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "04-experiment-runbook.json", {"runs": [{"name": "a"}], "artifacts": [{"path": "metrics.json"}]})
    write_json(run_dir / "04-statistics.json", {"comparisons": [{"metric": "success"}]})
    write_json(run_dir / "04-result-validation.json", {"status": "pass"})
    write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "04-failure-analysis.json", {"status": "pass"})
    write_json(run_dir / "04-benchmark-evidence-audit.json", {"status": "pass", "evidence_grade": "real_benchmark", "adapter_paper_grade_status": "ready", "adapter_paper_grade_issues": []})
    write_json(run_dir / "04-experiment-decision.json", {"status": "pass", "decision": "proceed_to_paper"})
    write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported"})
    write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "pass", "writing_mode": "conservative_paper", "blocking_issues": [], "warnings": [], "required_actions": []})
    write_json(run_dir / "07-paper-review.json", {"decision": "revise"})
    write_json(run_dir / "07-paper-review-calibration.json", {"status": "pass"})
    write_json(run_dir / "08-revision-plan.json", {"tasks": [{"id": "R1"}]})
    write_json(run_dir / "09-revision-report.json", {"tasks": [{"id": "R1"}]})
    write_json(run_dir / "09-revision-response-audit.json", {"status": "pass", "response_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-revised-paper-review.json", {"decision": "accept"})
    write_json(run_dir / "10-claim-traceability.json", {"status": "pass"})
    write_json(run_dir / "10-citation-grounding.json", {"status": "pass"})
    write_json(run_dir / "10-citation-coverage.json", {"status": "pass", "coverage_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-results-presentation.json", {"status": "pass"})
    write_json(run_dir / "10-claim-consistency.json", {"status": "pass"})
    write_json(run_dir / "10-code-data-availability.json", {"status": "ready", "manual_tasks": []})
    write_json(run_dir / "10-submission-check.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "10-final-readiness.json", {"status": "ready", "blocking_issues": []})
    write_json(run_dir / "11-submission-package.json", {"status": "ready", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "12-next-iteration-plan.json", {"status": "pass"})
    write_json(run_dir / "12-repair-queue.json", {"status": "pass"})
    write_json(run_dir / "12-repair-resolution-audit.json", {"status": "not_applicable", "resolution_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-runtime-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "13-open-source-compliance.json", {"status": "pass", "score": 1.0, "blocking_issues": [], "manual_tasks": []})


if __name__ == "__main__":
    unittest.main()
