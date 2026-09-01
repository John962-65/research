from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.run_summary import build_run_dashboard, render_run_dashboard_markdown, write_run_dashboard


class RunSummaryTest(unittest.TestCase):
    def test_dashboard_ranks_completed_evidence_rich_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            rich = runs_dir / "rich-run"
            failed = runs_dir / "failed-run"
            rich.mkdir(parents=True)
            failed.mkdir(parents=True)
            write_json(rich / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(
                rich / "01-literature-quality.json",
                {
                    "topic": "机械臂路径规划",
                    "total_papers": 8,
                    "selected_papers": 5,
                    "confidence_status": "pass",
                    "confidence_score": 0.82,
                },
            )
            write_json(
                rich / "01-literature-gate-decision.json",
                {
                    "status": "review_required",
                    "paper_grade_literature": {
                        "status": "review_required",
                        "issues": ["provider=online/auto 未配置。", "DOI/URL seed 不足。"],
                        "repair_suggestions": [],
                    },
                },
            )
            write_json(rich / "01-context.json", {"citations": [{"key": "paper1"}, {"key": "paper2"}]})
            write_json(rich / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 7, "risk": 2}])
            write_json(
                rich / "02-experiment-manager.json",
                {
                    "status": "review_required",
                    "execution_policy": "smoke_first",
                    "next_expansion_candidates": [{"branch_id": "B2", "title": "next"}],
                    "queue_summary": {
                        "total": 3,
                        "active": 1,
                        "blocked": 1,
                        "human_review": 2,
                        "ready_backlog": 1,
                        "deferred": 0,
                        "blocks_current_experiment": 1,
                    },
                },
            )
            write_json(
                rich / "04-statistics.json",
                {
                    "repeats": 3,
                    "comparisons": [
                        {"metric": "success", "direction": "candidate_better"},
                        {"metric": "time", "direction": "candidate_better"},
                    ],
                    "warnings": [],
                },
            )
            write_json(rich / "01-literature-rescue-plan.json", {"status": "pass", "rescue_queries": []})
            write_json(
                rich / "01-literature-rescue-execution.json",
                {
                    "status": "executed",
                    "new_unique_papers": 2,
                    "closed_query_outcomes": 1,
                    "unresolved_query_outcomes": 0,
                    "selected_queries": ["robot manipulator OMPL benchmark"],
                },
            )
            write_json(
                rich / "01-seed-paper-intake.json",
                {
                    "status": "pass",
                    "role_coverage_status": "review_required",
                    "total_seed_entries": 3,
                    "curated_seed_papers": 3,
                    "missing_curated_seed_roles": ["review", "benchmark_dataset"],
                    "required_actions": ["补齐进入 curated context 的 seed 角色覆盖。"],
                },
            )
            write_json(rich / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
            write_json(
                rich / "04-benchmark-result-schema-audit.json",
                {
                    "status": "review_required",
                    "execution_mode": "benchmark",
                    "blocking_issues": [],
                    "manual_tasks": ["人工核对 benchmark repeat 与 adapter provenance。"],
                    "warnings": [],
                },
            )
            write_json(
                rich / "04-benchmark-evidence-audit.json",
                {
                    "status": "review_required",
                    "evidence_grade": "local_experiment",
                    "adapter_paper_grade_status": "review_required",
                    "adapter_paper_grade_issues": ["缺少 baseline role。"],
                    "blocking_issues": [],
                    "manual_tasks": ["补齐 ablation manifest。"],
                },
            )
            write_json(
                rich / "04-failure-analysis.json",
                {"status": "pass", "summary": {"failed_runs": 0, "negative_metrics": 0, "uncertain_metrics": 0}},
            )
            write_json(
                rich / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "bounded_local_evidence",
                    "blocking_issues": [],
                    "warnings": ["只能写 preliminary/local evidence。"],
                },
            )
            write_json(
                rich / "07-paper-review.json",
                {"score": 8.0, "decision": "accept_with_minor_revisions", "required_revisions": ["补充真实 benchmark"]},
            )
            write_json(
                rich / "10-final-readiness.json",
                {
                    "status": "ready_for_human_polish",
                    "score_before": 8.0,
                    "score_after": 7.5,
                    "unsupported_after": 0,
                    "weak_after": 1,
                    "deferred_tasks": [],
                    "blocking_issues": [],
                    "availability_status": "needs_human_release_metadata",
                    "availability_manual_tasks": ["补充许可证"],
                    "availability_blocking_issues": [],
                    "submission_status": "needs_human_format_check",
                    "submission_manual_tasks": ["替换 IEEE 官方模板"],
                    "submission_blocking_issues": [],
                },
            )
            write_json(
                rich / "10-code-data-availability.json",
                {
                    "status": "needs_human_release_metadata",
                    "manual_tasks": ["许可证: 发布前补充代码许可证。", "公开仓库或归档 DOI: 创建归档。"],
                    "blocking_issues": [],
                },
            )
            write_json(
                rich / "10-submission-check.json",
                {
                    "status": "needs_human_format_check",
                    "manual_tasks": ["目标模板: 替换为目标会议/期刊官方模板。"],
                    "blocking_issues": [],
                },
            )
            write_json(
                rich / "10-claim-consistency.json",
                {
                    "status": "block",
                    "consistency_score": 0.62,
                    "blocking_issues": ["存在正式 benchmark claim。"],
                    "manual_tasks": ["降级结果表述。"],
                },
            )
            write_json(
                rich / "11-submission-package.json",
                {
                    "status": "needs_human_submission_review",
                    "manual_tasks": ["人工核验 ZIP"],
                    "blocking_issues": [],
                    "files": [{"package_path": "submission-package/README.md"}],
                },
            )
            write_json(
                rich / "13-research-scorecard.json",
                {
                    "status": "ready_for_human_submission_upload",
                    "overall_score": 91.5,
                    "manual_tasks": ["人工确认目标 venue。"],
                    "blocking_issues": [],
                },
            )
            write_json(
                rich / "12-next-iteration-plan.json",
                {
                    "status": "needs_targeted_iteration",
                    "decision": "按优先级处理阻断项。",
                    "items": [{"category": "format"}, {"category": "release"}],
                },
            )
            write_json(
                rich / "12-repair-queue.json",
                {
                    "status": "needs_repair",
                    "summary": {"total": 2, "block": 0, "high": 1, "medium": 1, "blocks_submission": 1},
                    "items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}],
                },
            )
            write_json(
                rich / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": True,
                    "rerun_from": "literature_review",
                    "repair_items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}],
                    "retrieval_repair_tasks": [{"task_id": "seed-role-review"}],
                    "review_reapproval_required": True,
                    "execution_reapproval_required": False,
                },
            )
            write_json(
                rich / "13-run-economics-audit.json",
                {
                    "status": "pass",
                    "summary": {
                        "total_calls": 8,
                        "input_tokens_estimated": 1200,
                        "output_tokens_estimated": 360,
                        "total_duration_seconds": 4.2,
                        "estimated_cost_usd": 0.006,
                    },
                    "budget": {"call_utilization": 0.4, "prompt_utilization": 0.25},
                    "manual_tasks": [],
                    "blocking_issues": [],
                },
            )
            write_json(
                rich / "13-agent-trajectory.json",
                {
                    "status": "pass",
                    "summary": {
                        "phase_counts": {"pass": 8, "warn": 0, "block": 0, "not_started": 0},
                        "last_event": "completed",
                        "event_count": 32,
                        "backfilled_events": 2,
                        "artifact_count": 120,
                        "blocking_issues": 0,
                        "manual_tasks": 0,
                    },
                    "phases": [{"phase_id": "private phase details must not affect dashboard"}],
                    "timeline": [{"stage": "private timeline must not affect dashboard"}],
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )
            write_json(
                rich / "13-agent-observability-audit.json",
                {
                    "status": "review_required",
                    "summary": {
                        "state_stage": "completed",
                        "manifest_status": "completed",
                        "manifest_events": 15,
                        "manifest_artifacts": 120,
                        "llm_total_calls": 8,
                        "llm_successful_calls": 8,
                        "llm_failed_calls": 0,
                        "llm_budget_exceeded_calls": 0,
                        "experiment_runs": 2,
                        "repair_queue_status": "needs_repair",
                    },
                    "budget": {"call_utilization": 0.41, "prompt_utilization": 0.92},
                    "checks": [{"name": "private check details must not affect dashboard"}],
                    "blocking_issues": [],
                    "manual_tasks": ["private observability manual task"],
                    "warnings": ["private observability warning"],
                    "recommended_actions": ["private action"],
                },
            )
            write_json(
                rich / "14-run-integrity-audit.json",
                {
                    "status": "pass",
                    "summary": {"checks": 12, "pass": 10, "warn": 0, "block": 0, "required_artifacts": 120},
                    "blocking_issues": [],
                    "warnings": [],
                },
            )
            write_json(
                rich / "14-final-handoff.json",
                {
                    "status": "ready_for_human_handoff",
                    "package_has_integrity_audit": False,
                    "blocking_issues": [],
                    "manual_tasks": ["重新生成投稿包以包含完整性审计快照。"],
                },
            )
            write_json(
                rich / "00-preflight.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "warn",
                    "checks": [
                        {"name": "topic", "status": "pass", "summary": "研究课题已填写"},
                        {"name": "semantic_scholar_key", "status": "warn", "summary": "Semantic Scholar API key 未配置"},
                    ],
                },
            )
            write_json(
                rich / "run-recovery-plan.json",
                {
                    "status": "completed",
                    "category": "completed",
                    "blocking_issues": [],
                    "recommended_actions": ["查看下一轮计划"],
                },
            )
            write_json(rich / "run-manifest.json", {"status": "completed", "artifacts": [{"path": "06-paper.md"}]})

            write_json(failed / "state.json", {"topic": "失败 run", "stage": "failed", "updated_at": "2026-06-08T09:00:00+00:00"})
            write_json(failed / "run-diagnostics.json", {"category": "llm_configuration"})
            write_json(
                failed / "00-preflight.json",
                {
                    "topic": "失败 run",
                    "status": "fail",
                    "checks": [
                        {"name": "llm_model", "status": "fail", "summary": "模型名缺失"},
                        {"name": "release_metadata", "status": "warn", "summary": "未配置发布元数据"},
                    ],
                },
            )
            write_json(
                failed / "run-recovery-plan.json",
                {
                    "status": "failed",
                    "category": "failed",
                    "blocking_issues": ["LLM 模型名缺失"],
                    "recommended_actions": ["填写模型名"],
                },
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.total_runs, 2)
            self.assertEqual(dashboard.runs[0].id, "rich-run")
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertEqual(dashboard.runs[0].final_readiness_status, "ready_for_human_polish")
            self.assertEqual(dashboard.runs[0].final_score_after, 7.5)
            self.assertEqual(dashboard.runs[0].evidence_confidence_status, "pass")
            self.assertEqual(dashboard.runs[0].evidence_confidence_score, 0.82)
            self.assertEqual(dashboard.runs[0].experiment_manager_status, "review_required")
            self.assertEqual(dashboard.runs[0].experiment_manager_policy, "smoke_first")
            self.assertEqual(dashboard.runs[0].experiment_manager_next_candidates, 1)
            self.assertEqual(dashboard.runs[0].experiment_manager_queue_blocked, 1)
            self.assertEqual(dashboard.runs[0].experiment_manager_queue_human_review, 2)
            self.assertEqual(dashboard.runs[0].experiment_manager_queue_ready_backlog, 1)
            self.assertEqual(dashboard.runs[0].availability_status, "needs_human_release_metadata")
            self.assertEqual(dashboard.runs[0].availability_manual_tasks, 2)
            self.assertEqual(dashboard.runs[0].submission_status, "needs_human_format_check")
            self.assertEqual(dashboard.runs[0].submission_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].package_status, "needs_human_submission_review")
            self.assertEqual(dashboard.runs[0].package_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].scorecard_status, "ready_for_human_submission_upload")
            self.assertEqual(dashboard.runs[0].scorecard_overall_score, 91.5)
            self.assertEqual(dashboard.runs[0].scorecard_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].scorecard_blocking_issues, 0)
            self.assertEqual(dashboard.runs[0].iteration_status, "needs_targeted_iteration")
            self.assertEqual(dashboard.runs[0].iteration_items, 2)
            self.assertEqual(dashboard.runs[0].repair_queue_status, "needs_repair")
            self.assertEqual(dashboard.runs[0].repair_queue_items, 2)
            self.assertEqual(dashboard.runs[0].repair_queue_high, 1)
            self.assertEqual(dashboard.runs[0].repair_queue_medium, 1)
            self.assertEqual(dashboard.runs[0].repair_queue_blocks_submission, 1)
            self.assertEqual(dashboard.runs[0].repair_resume_status, "ready_to_resume_repair")
            self.assertTrue(dashboard.runs[0].repair_resume_applied)
            self.assertEqual(dashboard.runs[0].repair_resume_rerun_from, "literature_review")
            self.assertEqual(dashboard.runs[0].repair_resume_items, 2)
            self.assertEqual(dashboard.runs[0].repair_resume_retrieval_tasks, 1)
            self.assertTrue(dashboard.runs[0].repair_resume_review_reapproval_required)
            self.assertEqual(dashboard.runs[0].run_economics_status, "pass")
            self.assertEqual(dashboard.runs[0].llm_total_calls, 8)
            self.assertEqual(dashboard.runs[0].llm_input_tokens_estimated, 1200)
            self.assertEqual(dashboard.runs[0].llm_output_tokens_estimated, 360)
            self.assertEqual(dashboard.runs[0].llm_duration_seconds, 4.2)
            self.assertEqual(dashboard.runs[0].llm_estimated_cost_usd, 0.006)
            self.assertEqual(dashboard.runs[0].agent_trajectory_status, "pass")
            self.assertEqual(dashboard.runs[0].agent_trajectory_pass, 8)
            self.assertEqual(dashboard.runs[0].agent_trajectory_warn, 0)
            self.assertEqual(dashboard.runs[0].agent_trajectory_block, 0)
            self.assertEqual(dashboard.runs[0].agent_trajectory_not_started, 0)
            self.assertEqual(dashboard.runs[0].agent_trajectory_last_event, "completed")
            self.assertEqual(dashboard.runs[0].agent_trajectory_backfilled_events, 2)
            self.assertEqual(dashboard.runs[0].agent_observability_status, "review_required")
            self.assertEqual(dashboard.runs[0].agent_observability_manifest_events, 15)
            self.assertEqual(dashboard.runs[0].agent_observability_manifest_artifacts, 120)
            self.assertEqual(dashboard.runs[0].agent_observability_llm_failed_calls, 0)
            self.assertEqual(dashboard.runs[0].agent_observability_experiment_runs, 2)
            self.assertEqual(dashboard.runs[0].agent_observability_repair_queue_status, "needs_repair")
            self.assertEqual(dashboard.runs[0].agent_observability_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].agent_observability_warnings, 1)
            self.assertEqual(dashboard.runs[0].agent_observability_prompt_pressure, 0.92)
            self.assertEqual(dashboard.runs[0].run_integrity_status, "pass")
            self.assertEqual(dashboard.runs[0].run_integrity_pass, 10)
            self.assertEqual(dashboard.runs[0].run_integrity_warnings, 0)
            self.assertEqual(dashboard.runs[0].run_integrity_blocking_issues, 0)
            self.assertEqual(dashboard.runs[0].final_handoff_status, "ready_for_human_handoff")
            self.assertEqual(dashboard.runs[0].final_handoff_blocking_issues, 0)
            self.assertEqual(dashboard.runs[0].final_handoff_manual_tasks, 1)
            self.assertFalse(dashboard.runs[0].final_handoff_package_has_integrity_audit)
            self.assertEqual(dashboard.runs[0].literature_rescue_status, "pass")
            self.assertEqual(dashboard.runs[0].literature_rescue_execution_status, "executed")
            self.assertEqual(dashboard.runs[0].literature_rescue_execution_closed, 1)
            self.assertEqual(dashboard.runs[0].literature_rescue_execution_unresolved, 0)
            self.assertEqual(dashboard.runs[0].literature_rescue_execution_new_unique, 2)
            self.assertEqual(dashboard.runs[0].seed_intake_status, "pass")
            self.assertEqual(dashboard.runs[0].seed_role_coverage_status, "review_required")
            self.assertEqual(dashboard.runs[0].seed_total_entries, 3)
            self.assertEqual(dashboard.runs[0].seed_curated_papers, 3)
            self.assertEqual(dashboard.runs[0].seed_missing_roles, 2)
            self.assertEqual(dashboard.runs[0].seed_required_actions, 1)
            self.assertEqual(dashboard.runs[0].result_validation_status, "pass")
            self.assertEqual(dashboard.runs[0].benchmark_schema_status, "review_required")
            self.assertEqual(dashboard.runs[0].benchmark_schema_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].paper_grade_literature_status, "review_required")
            self.assertEqual(dashboard.runs[0].paper_grade_literature_issues, 2)
            self.assertEqual(dashboard.runs[0].benchmark_evidence_status, "review_required")
            self.assertEqual(dashboard.runs[0].benchmark_evidence_grade, "local_experiment")
            self.assertEqual(dashboard.runs[0].benchmark_statistical_outcome, "")
            self.assertEqual(dashboard.runs[0].benchmark_claim_boundary_severity, "")
            self.assertFalse(dashboard.runs[0].benchmark_publishable_negative_or_neutral)
            self.assertEqual(dashboard.runs[0].benchmark_evidence_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].adapter_paper_grade_status, "review_required")
            self.assertEqual(dashboard.runs[0].adapter_paper_grade_issues, 1)
            self.assertEqual(dashboard.runs[0].claim_preflight_status, "review_required")
            self.assertEqual(dashboard.runs[0].claim_preflight_mode, "bounded_local_evidence")
            self.assertEqual(dashboard.runs[0].claim_preflight_warnings, 1)
            self.assertEqual(dashboard.runs[0].claim_consistency_status, "block")
            self.assertEqual(dashboard.runs[0].claim_consistency_score, 0.62)
            self.assertEqual(dashboard.runs[0].claim_consistency_blocking_issues, 1)
            self.assertEqual(dashboard.runs[0].claim_consistency_manual_tasks, 1)
            self.assertEqual(dashboard.runs[0].failure_analysis_status, "pass")
            self.assertEqual(dashboard.runs[0].preflight_status, "warn")
            self.assertEqual(dashboard.runs[0].preflight_warnings, 1)
            self.assertEqual(dashboard.runs[0].recovery_category, "completed")
            self.assertEqual(dashboard.runs[1].preflight_status, "fail")
            self.assertEqual(dashboard.runs[1].preflight_fails, 1)
            self.assertEqual(dashboard.runs[1].recovery_category, "failed")
            self.assertEqual(dashboard.runs[1].recovery_blocking_issues, 1)
            self.assertIn("Runs 对比", rendered)
            self.assertIn("rich-run", rendered)
            self.assertIn("5 pass 0.82", rendered)
            self.assertIn("ready_for_human_polish", rendered)
            self.assertIn("预检", rendered)
            self.assertIn("warn W1", rendered)
            self.assertIn("恢复", rendered)
            self.assertIn("completed", rendered)
            self.assertIn("failed (1)", rendered)
            self.assertIn("实验管理", rendered)
            self.assertIn("review_required:smoke_first next=1 QB1H2R1", rendered)
            self.assertIn("代码/数据", rendered)
            self.assertIn("needs_human_release_metadata (2)", rendered)
            self.assertIn("投稿检查", rendered)
            self.assertIn("needs_human_format_check (1)", rendered)
            self.assertIn("投稿包", rendered)
            self.assertIn("needs_human_submission_review (1)", rendered)
            self.assertIn("Scorecard", rendered)
            self.assertIn("ready_for_human_submission_upload 91.5 M1", rendered)
            self.assertIn("下一轮", rendered)
            self.assertIn("needs_targeted_iteration (2)", rendered)
            self.assertIn("修复队列", rendered)
            self.assertIn("needs_repair T2 H1 M1 S1", rendered)
            self.assertIn("修复恢复", rendered)
            self.assertIn("ready_to_resume_repair applied from=literature_review T2 Q1 gate=review", rendered)
            self.assertIn("LLM 资源", rendered)
            self.assertIn("pass 8c/1560t/4.2s $0.0060 p0.40", rendered)
            self.assertIn("轨迹", rendered)
            self.assertIn("pass P8 last=completed BF2", rendered)
            self.assertIn("可观测性", rendered)
            self.assertIn("review_required E15 A120 X2 Rneeds_repair M1 W1 p0.92", rendered)
            self.assertIn("完整性", rendered)
            self.assertIn("pass P10", rendered)
            self.assertIn("交付", rendered)
            self.assertIn("ready_for_human_handoff M1 audit=N", rendered)
            self.assertIn("补检索", rendered)
            self.assertIn("exec:executed C1 N2", rendered)
            self.assertIn("Seed", rendered)
            self.assertIn("pass roles:review_required 3/3 missing=2 A1", rendered)
            self.assertIn("验证", rendered)
            self.assertIn("Benchmark Schema", rendered)
            self.assertIn("review_required (1)", rendered)
            self.assertIn("论文级", rendered)
            self.assertIn("lit=review_required:2", rendered)
            self.assertIn("bench=review_required/local_experiment:1", rendered)
            self.assertIn("adapter=review_required:1", rendered)
            self.assertIn("claim=review_required/bounded_local_evidence:1", rendered)
            self.assertIn("cc=block:2", rendered)
            self.assertIn("失败分析", rendered)

    def test_dashboard_penalizes_scorecard_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-scorecard-run"
            blocked = runs_dir / "blocked-scorecard-run"
            clean.mkdir(parents=True)
            blocked.mkdir(parents=True)
            for run_dir in (clean, blocked):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(
                clean / "13-research-scorecard.json",
                {"status": "ready_for_human_submission_upload", "overall_score": 92.0, "blocking_issues": [], "manual_tasks": []},
            )
            write_json(
                blocked / "13-research-scorecard.json",
                {
                    "status": "blocked",
                    "overall_score": 61.0,
                    "blocking_issues": ["claim consistency 未通过。"],
                    "manual_tasks": ["人工复核最低分维度。"],
                },
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "clean-scorecard-run")
            self.assertEqual(dashboard.runs[1].scorecard_status, "blocked")
            self.assertEqual(dashboard.runs[1].scorecard_blocking_issues, 1)
            self.assertEqual(dashboard.runs[1].scorecard_manual_tasks, 1)
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertIn("ready_for_human_submission_upload 92.0", rendered)
            self.assertIn("blocked 61.0 B1 M1", rendered)

    def test_dashboard_penalizes_literature_and_experiment_repair_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            good = runs_dir / "good-run"
            bad = runs_dir / "bad-run"
            good.mkdir(parents=True)
            bad.mkdir(parents=True)
            for run_dir in (good, bad):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "01-context.json", {"citations": [{"key": "a"}]})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(good / "01-literature-rescue-plan.json", {"status": "pass", "rescue_queries": []})
            write_json(good / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
            write_json(good / "04-failure-analysis.json", {"status": "pass", "summary": {"failed_runs": 0, "negative_metrics": 0, "uncertain_metrics": 0}})
            write_json(good / "12-next-iteration-plan.json", {"status": "ready_for_submission_upload", "items": []})
            write_json(bad / "01-literature-rescue-plan.json", {"status": "needs_rescue_search", "rescue_queries": [{"query": "CHOMP"}]})
            write_json(
                bad / "01-literature-rescue-execution.json",
                {
                    "status": "no_new_papers",
                    "new_unique_papers": 0,
                    "closed_query_outcomes": 0,
                    "unresolved_query_outcomes": 1,
                    "selected_queries": ["CHOMP"],
                },
            )
            write_json(bad / "04-result-validation.json", {"status": "block", "blocking_issues": ["timeout"], "warnings": []})
            write_json(bad / "04-failure-analysis.json", {"status": "block", "summary": {"failed_runs": 1, "negative_metrics": 1, "uncertain_metrics": 1}})
            write_json(bad / "12-next-iteration-plan.json", {"status": "needs_experiment_repair", "items": [{"category": "experiment"}]})
            write_json(
                bad / "13-run-economics-audit.json",
                {
                    "status": "review_required",
                    "summary": {"total_calls": 5, "input_tokens_estimated": 900, "output_tokens_estimated": 200, "total_duration_seconds": 3.0},
                    "budget": {"call_utilization": 0.95, "prompt_utilization": 0.2},
                    "manual_tasks": ["LLM 使用接近配置预算上限：calls=0.95"],
                    "blocking_issues": [],
                },
            )
            write_json(
                bad / "14-run-integrity-audit.json",
                {
                    "status": "block",
                    "summary": {"checks": 12, "pass": 8, "warn": 1, "block": 1},
                    "blocking_issues": ["security/run_config_secret: run-config.json 中 llm.api_key 非空。"],
                    "warnings": ["manifest/artifact_inventory: 缺少部分记录。"],
                },
            )
            write_json(
                bad / "14-final-handoff.json",
                {
                    "status": "blocked",
                    "package_has_integrity_audit": False,
                    "blocking_issues": ["11-submission-package.zip 缺失或为空。"],
                    "manual_tasks": [],
                },
            )

            dashboard = build_run_dashboard(runs_dir)

            self.assertEqual(dashboard.runs[0].id, "good-run")
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertEqual(dashboard.runs[1].literature_rescue_status, "needs_rescue_search")
            self.assertEqual(dashboard.runs[1].literature_rescue_execution_status, "no_new_papers")
            self.assertEqual(dashboard.runs[1].literature_rescue_execution_unresolved, 1)
            self.assertEqual(dashboard.runs[1].result_validation_status, "block")
            self.assertEqual(dashboard.runs[1].failure_analysis_status, "block")
            self.assertEqual(dashboard.runs[1].run_economics_status, "review_required")
            self.assertEqual(dashboard.runs[1].run_economics_manual_tasks, 1)
            self.assertEqual(dashboard.runs[1].run_integrity_status, "block")
            self.assertEqual(dashboard.runs[1].run_integrity_blocking_issues, 1)
            self.assertEqual(dashboard.runs[1].run_integrity_warnings, 1)
            self.assertEqual(dashboard.runs[1].final_handoff_status, "blocked")
            self.assertEqual(dashboard.runs[1].final_handoff_blocking_issues, 1)

    def test_dashboard_penalizes_open_repair_queue(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-run"
            blocked = runs_dir / "blocked-repair-run"
            clean.mkdir(parents=True)
            blocked.mkdir(parents=True)
            for run_dir in (clean, blocked):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(clean / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0, "block": 0, "high": 0, "medium": 0}, "items": []})
            write_json(
                blocked / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 3, "block": 1, "high": 1, "medium": 1, "blocks_submission": 2},
                    "items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}, {"task_id": "RQ-003"}],
                },
            )
            write_json(
                blocked / "12-repair-resume-plan.json",
                {
                    "status": "ready_to_resume_repair",
                    "applied": False,
                    "rerun_from": "literature_review",
                    "repair_items": [{"task_id": "RQ-001"}, {"task_id": "RQ-002"}],
                    "retrieval_repair_tasks": [{"task_id": "seed-role-review"}],
                    "review_reapproval_required": True,
                    "execution_reapproval_required": True,
                },
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "clean-run")
            self.assertEqual(dashboard.runs[1].repair_queue_status, "blocked_repair_required")
            self.assertEqual(dashboard.runs[1].repair_queue_block, 1)
            self.assertEqual(dashboard.runs[1].repair_queue_high, 1)
            self.assertEqual(dashboard.runs[1].repair_queue_medium, 1)
            self.assertEqual(dashboard.runs[1].repair_resume_status, "ready_to_resume_repair")
            self.assertFalse(dashboard.runs[1].repair_resume_applied)
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertIn("blocked_repair_required T3 B1 H1 M1 S2", rendered)
            self.assertIn("ready_to_resume_repair planned from=literature_review T2 Q1 gate=review,exec", rendered)

    def test_dashboard_penalizes_invalid_final_handoff_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-run"
            invalid = runs_dir / "invalid-zip-run"
            clean.mkdir(parents=True)
            invalid.mkdir(parents=True)
            for run_dir, zip_valid in [(clean, True), (invalid, False)]:
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
                write_json(run_dir / "13-research-scorecard.json", {"status": "ready_for_human_submission_upload", "overall_score": 90, "manual_tasks": [], "blocking_issues": []})
                write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"pass": 12, "warn": 0, "block": 0}, "blocking_issues": [], "warnings": []})
                write_json(
                    run_dir / "14-final-handoff.json",
                    {
                        "status": "ready_for_submission_upload",
                        "package_zip_valid": zip_valid,
                        "package_has_integrity_audit": True,
                        "blocking_issues": [],
                        "manual_tasks": [],
                    },
                )
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "clean-run")
            self.assertEqual(dashboard.runs[1].id, "invalid-zip-run")
            self.assertTrue(dashboard.runs[0].final_handoff_package_zip_valid)
            self.assertFalse(dashboard.runs[1].final_handoff_package_zip_valid)
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertIn("ready_for_submission_upload audit=Y zip=N", rendered)

    def test_dashboard_penalizes_seed_intake_role_coverage_review(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-run"
            weak = runs_dir / "weak-seed-run"
            clean.mkdir(parents=True)
            weak.mkdir(parents=True)
            for run_dir in (clean, weak):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(
                clean / "01-seed-paper-intake.json",
                {
                    "status": "pass",
                    "role_coverage_status": "pass",
                    "total_seed_entries": 3,
                    "curated_seed_papers": 3,
                    "missing_curated_seed_roles": [],
                    "required_actions": [],
                },
            )
            write_json(
                weak / "01-seed-paper-intake.json",
                {
                    "status": "pass",
                    "role_coverage_status": "review_required",
                    "total_seed_entries": 3,
                    "curated_seed_papers": 2,
                    "missing_curated_seed_roles": ["review", "benchmark_dataset"],
                    "required_actions": ["补齐进入 curated context 的 seed 角色覆盖。"],
                },
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "clean-run")
            self.assertEqual(dashboard.runs[1].seed_role_coverage_status, "review_required")
            self.assertEqual(dashboard.runs[1].seed_missing_roles, 2)
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertIn("pass roles:review_required 2/3 missing=2 A1", rendered)

    def test_dashboard_penalizes_benchmark_schema_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-run"
            blocked = runs_dir / "blocked-run"
            clean.mkdir(parents=True)
            blocked.mkdir(parents=True)
            for run_dir in (clean, blocked):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(clean / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
            write_json(
                blocked / "04-benchmark-result-schema-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["adapter provenance missing license"],
                    "manual_tasks": ["补 dataset_url"],
                },
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "clean-run")
            self.assertEqual(dashboard.runs[1].benchmark_schema_status, "block")
            self.assertEqual(dashboard.runs[1].benchmark_schema_blocking_issues, 1)
            self.assertEqual(dashboard.runs[1].benchmark_schema_manual_tasks, 1)
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertIn("block (2)", rendered)

    def test_dashboard_penalizes_paper_grade_gaps(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "paper-grade-run"
            weak = runs_dir / "local-only-run"
            clean.mkdir(parents=True)
            weak.mkdir(parents=True)
            for run_dir in (clean, weak):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(clean / "01-literature-gate-decision.json", {"paper_grade_literature": {"status": "pass", "issues": []}})
            write_json(
                clean / "04-benchmark-evidence-audit.json",
                {
                    "status": "pass",
                    "evidence_grade": "real_benchmark",
                    "statistical_outcome": "neutral_no_observed_difference",
                    "claim_boundary_severity": "negative_or_neutral_no_superiority",
                    "publishable_negative_or_neutral_result": True,
                    "adapter_paper_grade_status": "ready",
                    "adapter_paper_grade_issues": [],
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )
            write_json(clean / "04-claim-boundary-preflight.json", {"status": "pass", "writing_mode": "conservative_benchmark_claims_allowed", "blocking_issues": [], "warnings": []})
            write_json(clean / "10-claim-consistency.json", {"status": "pass", "consistency_score": 0.95, "blocking_issues": [], "manual_tasks": []})
            write_json(
                weak / "01-literature-gate-decision.json",
                {"paper_grade_literature": {"status": "review_required", "issues": ["provider=online/auto 未配置。", "成功来源不足。", "DOI/URL seed 不足。"]}},
            )
            write_json(
                weak / "04-benchmark-evidence-audit.json",
                {
                    "status": "review_required",
                    "evidence_grade": "local_experiment",
                    "adapter_paper_grade_status": "review_required",
                    "adapter_paper_grade_issues": ["缺少 baseline manifest。", "缺少 ablation manifest。"],
                    "blocking_issues": [],
                    "manual_tasks": ["补齐 candidate/baseline/ablation manifest。"],
                },
            )
            write_json(
                weak / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "bounded_local_evidence",
                    "blocking_issues": [],
                    "warnings": ["local evidence 不允许写正式 benchmark claim。"],
                },
            )
            write_json(
                weak / "10-claim-consistency.json",
                {"status": "block", "consistency_score": 0.55, "blocking_issues": ["正式 benchmark claim 越界。"], "manual_tasks": []},
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "paper-grade-run")
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertEqual(dashboard.runs[1].paper_grade_literature_status, "review_required")
            self.assertEqual(dashboard.runs[1].benchmark_evidence_grade, "local_experiment")
            self.assertEqual(dashboard.runs[1].adapter_paper_grade_issues, 2)
            self.assertEqual(dashboard.runs[1].claim_consistency_status, "block")
            self.assertEqual(dashboard.runs[0].benchmark_statistical_outcome, "neutral_no_observed_difference")
            self.assertEqual(dashboard.runs[0].benchmark_claim_boundary_severity, "negative_or_neutral_no_superiority")
            self.assertTrue(dashboard.runs[0].benchmark_publishable_negative_or_neutral)
            self.assertIn("lit=pass bench=pass/real_benchmark adapter=ready boundary=negative_or_neutral_no_superiority negneutral=publishable claim=pass/conservative_benchmark_claims_allowed cc=pass", rendered)
            self.assertIn("lit=review_required:3 bench=review_required/local_experiment:1 adapter=review_required:2 claim=review_required/bounded_local_evidence:1 cc=block:1", rendered)

    def test_dashboard_penalizes_failed_preflight_and_recovery_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            clean = runs_dir / "clean-run"
            blocked = runs_dir / "blocked-run"
            clean.mkdir(parents=True)
            blocked.mkdir(parents=True)
            for run_dir in (clean, blocked):
                write_json(run_dir / "state.json", {"topic": run_dir.name, "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
                write_json(run_dir / "01-literature-quality.json", {"total_papers": 8, "selected_papers": 6})
                write_json(run_dir / "02-ideas.json", [{"title": "idea", "novelty": 8, "feasibility": 8, "risk": 1}])
                write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"direction": "candidate_better"}], "warnings": []})
                write_json(run_dir / "07-paper-review.json", {"score": 8.0, "decision": "minor", "required_revisions": []})
                write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 8.0, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": [], "blocking_issues": []})
                write_json(run_dir / "run-manifest.json", {"status": "completed", "artifacts": []})
            write_json(
                clean / "00-preflight.json",
                {"status": "pass", "checks": [{"name": "topic", "status": "pass", "summary": "研究课题已填写"}]},
            )
            write_json(clean / "run-recovery-plan.json", {"category": "completed", "blocking_issues": [], "recommended_actions": []})
            write_json(
                blocked / "00-preflight.json",
                {
                    "status": "fail",
                    "checks": [
                        {"name": "llm_model", "status": "fail", "summary": "模型名缺失"},
                        {"name": "llm_api_key", "status": "fail", "summary": "API key 缺失"},
                    ],
                },
            )
            write_json(
                blocked / "run-recovery-plan.json",
                {"category": "failed", "blocking_issues": ["LLM 未配置"], "recommended_actions": ["填写模型配置"]},
            )

            dashboard = build_run_dashboard(runs_dir)
            rendered = render_run_dashboard_markdown(dashboard)

            self.assertEqual(dashboard.runs[0].id, "clean-run")
            self.assertEqual(dashboard.runs[1].preflight_fails, 2)
            self.assertEqual(dashboard.runs[1].recovery_category, "failed")
            self.assertEqual(dashboard.runs[1].recovery_blocking_issues, 1)
            self.assertGreater(dashboard.runs[0].readiness_score, dashboard.runs[1].readiness_score)
            self.assertIn("fail F2", rendered)
            self.assertIn("failed (1)", rendered)

    def test_write_dashboard_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "one-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "测试", "stage": "completed", "updated_at": "now"})
            dashboard = build_run_dashboard(root / "runs")

            json_path, md_path = write_run_dashboard(dashboard, root)

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["total_runs"], 1)
            self.assertIn("Runs 对比", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
