from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.prior_run_lessons import build_prior_run_lessons, render_prior_run_lessons_markdown, write_prior_run_lessons_artifacts
from research_agent.run_memory import build_run_memory


class PriorRunLessonsTest(unittest.TestCase):
    def test_prior_lessons_turn_memory_signals_into_agent_constraints(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "weak-literature-run"
            out_dir = runs_dir / "new-run"
            run_dir.mkdir(parents=True)
            out_dir.mkdir()
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 2, "total_papers": 4})
            write_json(
                run_dir / "01-literature-rescue-plan.json",
                {"status": "needs_manual_seed", "required_actions": ["补充高相关 DOI seed papers。"], "rescue_queries": []},
            )

            report = write_prior_run_lessons_artifacts("机械臂路径规划", runs_dir, out_dir)
            rendered = render_prior_run_lessons_markdown(report)

            self.assertEqual(report.status, "carry_forward_recommended")
            self.assertTrue(any(item.category == "literature_repair" for item in report.lessons))
            self.assertIn("历史 run 经验必须作为本轮约束处理", report.agent_prompt_text)
            self.assertTrue((out_dir / "00-prior-run-lessons.json").exists())
            self.assertIn("Prior Run Lessons", rendered)

    def test_empty_memory_generates_passive_lesson_report(self) -> None:
        with TemporaryDirectory() as tmp:
            memory = build_run_memory(Path(tmp) / "runs")
            report = build_prior_run_lessons("新课题", memory)

            self.assertEqual(report.status, "no_prior_constraints")
            self.assertFalse(report.lessons)
            self.assertIn("人工 gate", report.agent_prompt_text)

    def test_experiment_manager_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "manager-smoke"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "02-experiment-manager.json",
                {
                    "status": "review_required",
                    "manager_decision": "proceed_with_cautions",
                    "execution_policy": "smoke_first",
                    "selected_idea_title": "高风险分支",
                    "planning_constraints": ["先规划低成本 smoke-first 实验；不要把 smoke 结果写成最终科学结论。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_recommended")
        lesson = next(item for item in report.lessons if item.category == "experiment_manager_smoke_first")
        self.assertIn("experiment_manager", lesson.pipeline_targets)
        self.assertIn("smoke-first", report.agent_prompt_text)

    def test_benchmark_result_schema_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "schema-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "04-benchmark-result-schema-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["benchmark result provenance 不完整：candidate: license, baseline_version, citation"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "benchmark_result_schema")
        self.assertIn("benchmark_adapter", lesson.pipeline_targets)
        self.assertIn("result_validation", lesson.pipeline_targets)
        self.assertIn("benchmark_result_schema", report.agent_prompt_text)

    def test_llm_trace_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "llm-trace-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-llm-trace-audit.json",
                {
                    "status": "block",
                    "coverage": {"required_stages": 7, "passed_required": 4},
                    "ledger_summary": {"total_calls": 5, "successful_calls": 4, "failed_calls": 1, "budget_exceeded_calls": 0},
                    "blocking_issues": ["paper_writing: 06-paper.md 已生成，但匹配到的成功 LLM 调用为 0/1。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "llm_trace_audit")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("llm_trace_audit", lesson.pipeline_targets)
        self.assertIn("paper_review_loop", lesson.pipeline_targets)
        self.assertIn("llm_trace_audit", report.agent_prompt_text)

    def test_run_economics_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "economics-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-run-economics-audit.json",
                {
                    "status": "block",
                    "summary": {
                        "total_calls": 5,
                        "failed_calls": 1,
                        "budget_exceeded_calls": 1,
                        "input_tokens_estimated": 8000,
                        "output_tokens_estimated": 1200,
                    },
                    "budget": {"call_utilization": 1.0, "prompt_utilization": 0.95},
                    "pricing": {"cost_estimation_enabled": False},
                    "blocking_issues": ["LLM ledger 存在 failed=1 budget_exceeded=1。"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "run_economics")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("llm_budget", lesson.pipeline_targets)
        self.assertIn("run_economics", lesson.pipeline_targets)
        self.assertIn("run_economics", report.agent_prompt_text)

    def test_literature_source_health_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "source-health-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-source-health.json",
                {
                    "total_sources": 3,
                    "rate_limited_sources": 1,
                    "failed_sources": 1,
                    "query_attempts": 6,
                    "query_successes": 0,
                    "query_failures": 2,
                    "query_rate_limits": 2,
                    "sources": [
                        {"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True},
                        {"source": "openalex", "status": "failed", "returned": 0, "errors": 2},
                        {"source": "crossref", "status": "ok", "returned": 0},
                    ],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "literature_source_health")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("query_execution_audit", lesson.pipeline_targets)
        self.assertIn("review_gate", lesson.pipeline_targets)
        self.assertIn("literature_source_health", report.agent_prompt_text)

    def test_agent_observability_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "observability-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {
                    "status": "block",
                    "summary": {"manifest_events": 0, "manifest_artifacts": 0, "llm_failed_calls": 0, "repair_queue_status": "blocked_repair_required"},
                    "blocking_issues": ["run-manifest 没有 events。"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "agent_observability")
        self.assertIn("agent_trajectory", lesson.pipeline_targets)
        self.assertIn("agent_observability", lesson.pipeline_targets)
        self.assertIn("repair_resume", lesson.pipeline_targets)
        self.assertIn("agent_observability", report.agent_prompt_text)

    def test_agent_stage_contract_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "stage-contract-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-agent-stage-contract.json",
                {
                    "status": "block",
                    "score": 0.44,
                    "checks": [
                        {"stage": "literature_grounding", "status": "block", "required_actions": ["补充高相关文献。"]},
                        {"stage": "human_review_gate", "status": "missing", "required_actions": ["人工批准 review gate。"]},
                    ],
                    "blocking_issues": ["补充高相关文献或 seed papers，确保至少 3 篇文献进入 context。"],
                    "manual_tasks": [],
                    "recommended_actions": ["先处理阻断问题，再运行 repair-resume。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "agent_stage_contract")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("agent_stage_contract", lesson.pipeline_targets)
        self.assertIn("repair_resume", lesson.pipeline_targets)
        self.assertIn("agent_stage_contract", report.agent_prompt_text)

    def test_research_scorecard_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "scorecard-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-research-scorecard.json",
                {
                    "status": "blocked",
                    "overall_score": 42.0,
                    "dimensions": [
                        {"category": "experiment_benchmark", "score": 20.0, "status": "block"},
                        {"category": "literature_evidence", "score": 35.0, "status": "manual_required"},
                    ],
                    "blocking_issues": ["experiment_benchmark: candidate 与 baseline 没有共同指标。"],
                    "manual_tasks": [],
                    "next_actions": ["修复实验结果验证。"],
                    "recommendation": "当前 run 总分 42.0/100，仍有阻断项。",
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "research_scorecard")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("research_scorecard", lesson.pipeline_targets)
        self.assertIn("next_iteration", lesson.pipeline_targets)
        self.assertIn("research_scorecard", report.agent_prompt_text)

    def test_run_integrity_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "integrity-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "14-run-integrity-audit.json",
                {
                    "status": "block",
                    "summary": {"checks": 7, "pass": 4, "warn": 1, "block": 2, "required_artifacts": 150},
                    "items": [
                        {"category": "artifacts", "name": "required_inventory", "status": "block", "evidence": "缺少 run-manifest.json"},
                    ],
                    "blocking_issues": ["artifacts/required_inventory: 缺少 run-manifest.json"],
                    "warnings": [],
                    "recommended_actions": ["补齐 required artifacts 后重跑 integrity audit。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "run_integrity_audit")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("run_integrity_audit", lesson.pipeline_targets)
        self.assertIn("agent_trajectory", lesson.pipeline_targets)
        self.assertIn("run_integrity_audit", report.agent_prompt_text)

    def test_final_handoff_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "handoff-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "blocked",
                    "package_zip": "11-submission-package.zip",
                    "package_zip_exists": False,
                    "package_status": "ready_for_human_submission_upload",
                    "scorecard_status": "ready_for_human_submission_upload",
                    "run_integrity_status": "block",
                    "package_has_integrity_audit": False,
                    "blocking_issues": ["11-submission-package.zip 缺失或为空。"],
                    "manual_tasks": [],
                    "recommended_actions": ["先处理阻断项，不要把当前 ZIP 标记为最终可提交版本。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "final_handoff")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("research_scorecard", lesson.pipeline_targets)
        self.assertIn("run_integrity_audit", lesson.pipeline_targets)
        self.assertIn("submission_package", lesson.pipeline_targets)
        self.assertIn("final_handoff", report.agent_prompt_text)

    def test_repair_resolution_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-resolution-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "12-repair-resolution-audit.json",
                {
                    "status": "block",
                    "resolution_score": 0.25,
                    "applied": True,
                    "rerun_from": "experiment_plan",
                    "queue_status": "blocked_repair_required",
                    "remaining_items": [{"task_id": "R1", "severity": "block", "category": "result_validation"}],
                    "resolved_items": [],
                    "new_items": [],
                    "blocking_issues": ["04-result-validation.json/result_validation: 共同指标仍缺失"],
                    "manual_tasks": [],
                    "required_actions": ["继续从 repair queue 恢复。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "repair_resolution_audit")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("repair_resume", lesson.pipeline_targets)
        self.assertIn("repair_resolution_audit", lesson.pipeline_targets)
        self.assertIn("repair_resolution_audit", report.agent_prompt_text)

    def test_literature_search_feedback_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "search-feedback-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-search-feedback.json",
                {
                    "status": "needs_search_revision",
                    "recommended_queries": [
                        {"query": "robot manipulator OMPL benchmark RRT* CHOMP", "priority": 96, "source": "coverage"}
                    ],
                    "seed_paper_targets": [{"category": "benchmark", "name": "OMPL", "hint": "补 DOI seed"}],
                    "retrieval_repair_tasks": [
                        {
                            "category": "query_repair",
                            "priority": 96,
                            "owner": "agent",
                            "action": "执行补检索式并合并去重候选。",
                            "query": "robot manipulator OMPL benchmark RRT* CHOMP",
                            "rationale": "补齐 benchmark/method 覆盖。",
                        }
                    ],
                    "next_run_config": {"literature_provider": "online", "max_papers": 12, "max_search_queries": 6, "seed_papers_min": 3},
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_recommended")
        lesson = next(item for item in report.lessons if item.category == "literature_search_feedback")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("research_plan", lesson.pipeline_targets)
        self.assertIn("literature_search", lesson.pipeline_targets)
        self.assertIn("literature_rerank", lesson.pipeline_targets)
        self.assertIn("literature_search_feedback", report.agent_prompt_text)

    def test_literature_rescue_execution_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "rescue-execution-open"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-rescue-execution.json",
                {
                    "status": "no_new_papers",
                    "new_unique_papers": 0,
                    "closed_query_outcomes": 0,
                    "unresolved_query_outcomes": 1,
                    "selected_queries": ["robot manipulator OMPL benchmark"],
                    "repair_task_ids": ["retrieval-repair-001"],
                    "required_actions": ["检索修复任务 retrieval-repair-001 未闭环。"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        lesson = next(item for item in report.lessons if item.category == "literature_rescue_execution")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("literature_search", lesson.pipeline_targets)
        self.assertIn("repair_queue", lesson.pipeline_targets)
        self.assertIn("literature_rescue_execution", report.agent_prompt_text)

    def test_environment_snapshot_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "env-partial"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "04-environment-snapshot.json",
                {
                    "status": "partial",
                    "warnings": ["部分白名单命令当前不可定位：pytest"],
                    "package_versions": [{"name": "pip", "version": "25.0"}],
                    "tool_versions": [{"command": "pytest", "available": False, "path": ""}],
                    "source_tree": {"file_count": 3, "aggregate_sha256": "abc"},
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_recommended")
        lesson = next(item for item in report.lessons if item.category == "environment_snapshot")
        self.assertIn("experiment_execution", lesson.pipeline_targets)
        self.assertIn("environment_snapshot", lesson.pipeline_targets)
        self.assertIn("submission_package", lesson.pipeline_targets)
        self.assertIn("environment_snapshot", report.agent_prompt_text)

    def test_human_brief_constraint_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "human-constraint-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "03-review-constraint-compliance.json",
                {
                    "status": "block",
                    "human_brief_constraints": 1,
                    "blocked": 1,
                    "blocking_issues": ["HB-C01 未落实：必须比较 RRT*"],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "human_brief_constraints")
        self.assertIn("human_brief", lesson.pipeline_targets)
        self.assertIn("review_constraint_compliance", lesson.pipeline_targets)
        self.assertIn("human_brief_constraints", report.agent_prompt_text)

    def test_open_source_compliance_memory_becomes_agent_constraint(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "open-source-compliance-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-open-source-compliance.json",
                {
                    "status": "block",
                    "score": 0.42,
                    "checked_lessons": 12,
                    "lesson_results": [{"lesson_id": "query_execution_coverage_audit", "status": "block"}],
                    "blocking_issues": ["Semantic Scholar 429 导致 selected query 没有 source 返回。"],
                    "manual_tasks": [],
                },
            )

            memory = build_run_memory(runs_dir)
            report = build_prior_run_lessons("机械臂路径规划", memory)

        self.assertEqual(report.status, "carry_forward_required")
        lesson = next(item for item in report.lessons if item.category == "open_source_compliance")
        self.assertIn("preflight", lesson.pipeline_targets)
        self.assertIn("open_source_compliance", lesson.pipeline_targets)
        self.assertIn("repair_queue", lesson.pipeline_targets)
        self.assertIn("research_scorecard", lesson.pipeline_targets)
        self.assertIn("open_source_compliance", report.agent_prompt_text)


if __name__ == "__main__":
    unittest.main()
