from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.repair_queue import build_repair_queue_report, render_repair_queue_markdown, write_repair_queue_artifacts
from research_agent.repair_queue_backfill import backfill_repair_queues, render_repair_queue_backfill_markdown


class RepairQueueTest(unittest.TestCase):
    def test_repair_queue_blocks_on_failed_audits(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-metadata-audit.json",
                {
                    "status": "block",
                    "blocked": 2,
                    "review_required": 1,
                    "required_actions": ["替换无 DOI/URL 且摘要过薄的文献。"],
                },
            )
            write_json(
                run_dir / "04-result-validation.json",
                {
                    "status": "block",
                    "blocking_issues": ["candidate 与 baseline 没有可比较的共同指标。"],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertEqual(report.summary["block"], 2)
            self.assertTrue(any(item.source_artifact == "01-literature-metadata-audit.json" for item in report.items))
            self.assertTrue(any(item.blocks_downstream for item in report.items))
            self.assertTrue(any("共同指标" in issue for issue in report.blocking_issues))

    def test_repair_queue_marks_smoke_benchmark_as_repair_needed(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "04-benchmark-evidence-audit.json",
                {
                    "status": "smoke_only",
                    "evidence_grade": "smoke_only",
                    "required_actions": ["升级到 benchmark manifest 后再写正式结论。"],
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            report = write_repair_queue_artifacts("机械臂路径规划", run_dir)
            rendered = render_repair_queue_markdown(report)
            saved = json.loads((run_dir / "12-repair-queue.json").read_text(encoding="utf-8"))

            self.assertEqual(report.status, "needs_repair")
            self.assertEqual(report.summary["high"], 1)
            self.assertFalse(report.blocking_issues)
            self.assertIn("修复队列", rendered)
            self.assertEqual(saved["status"], "needs_repair")

    def test_repair_queue_blocks_benchmark_result_schema_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "04-benchmark-result-schema-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["benchmark adapter artifact contract 未闭环"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "04-benchmark-result-schema-audit.json" for item in report.items))
            self.assertTrue(any(item.rerun_from == "experiments" for item in report.items))

    def test_repair_queue_surfaces_partial_environment_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "04-environment-snapshot.json",
                {
                    "status": "partial",
                    "warnings": ["部分白名单命令当前不可定位：python3"],
                    "source_tree": {"file_count": 3, "aggregate_sha256": "abc"},
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            item = next(item for item in report.items if item.source_artifact == "04-environment-snapshot.json")
            self.assertEqual(item.category, "environment_snapshot")
            self.assertEqual(item.severity, "high")
            self.assertTrue(item.blocks_submission)
            self.assertFalse(item.blocks_downstream)

    def test_repair_queue_blocks_experiment_manager(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "02-experiment-manager.json",
                {
                    "status": "block",
                    "required_actions": ["选中分支的 idea audit 为 block；修正不可核对 citation/chunk 或人工改选。"],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "02-experiment-manager.json" for item in report.items))
            self.assertTrue(any(item.rerun_from == "ideation" for item in report.items))

    def test_repair_queue_blocks_literature_gate_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-gate-decision.json",
                {
                    "status": "block",
                    "blocking_reasons": ["citation grounding 为 block"],
                    "review_reasons": [],
                    "required_actions": ["修复 grounding 后重跑文献 gate"],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            item = next(item for item in report.items if item.source_artifact == "01-literature-gate-decision.json")
            self.assertEqual(item.category, "literature_rag_gate")
            self.assertEqual(item.rerun_from, "literature_review")
            self.assertTrue(item.blocks_downstream)

    def test_repair_queue_blocks_human_gate_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "13-human-gate-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["review gate 未批准但已进入 idea"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            item = next(item for item in report.items if item.source_artifact == "13-human-gate-audit.json")
            self.assertEqual(item.category, "human_gate")
            self.assertEqual(item.rerun_from, "literature_context")
            self.assertTrue(item.blocks_downstream)

    def test_repair_queue_blocks_agent_observability_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["run-manifest artifact inventory 缺少关键文件"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "13-agent-observability-audit.json" for item in report.items))
            self.assertTrue(any(item.category == "agent_observability" for item in report.items))

    def test_repair_queue_blocks_run_economics_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "13-run-economics-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["run-llm-ledger.json 缺失或不可读"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "13-run-economics-audit.json" for item in report.items))
            self.assertTrue(any(item.category == "run_economics" for item in report.items))

    def test_repair_queue_blocks_run_integrity_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "14-run-integrity-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["zip_valid: 11-submission-package.zip 不是可读 ZIP。"],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            item = next(item for item in report.items if item.source_artifact == "14-run-integrity-audit.json")
            self.assertEqual(item.category, "run_integrity")
            self.assertEqual(item.severity, "block")
            self.assertEqual(item.rerun_from, "submission_package")
            self.assertTrue(item.blocks_submission)
            self.assertIn("11-submission-package.zip", item.target_artifacts)

    def test_repair_queue_blocks_invalid_final_handoff_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "package_zip": "11-submission-package.zip",
                    "package_zip_exists": True,
                    "package_zip_valid": False,
                    "package_status": "ready_for_human_submission_upload",
                    "run_integrity_status": "pass",
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            item = next(item for item in report.items if item.source_artifact == "14-final-handoff.json")
            self.assertEqual(item.category, "final_handoff")
            self.assertEqual(item.severity, "block")
            self.assertEqual(item.rerun_from, "submission_package")
            self.assertIn("package_zip_valid=False", item.trigger_status)
            self.assertIn("11-submission-package.zip", item.target_artifacts)

    def test_repair_queue_ignores_final_handoff_upstream_block_echoes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "blocked",
                    "package_zip": "11-submission-package.zip",
                    "package_zip_exists": True,
                    "package_zip_valid": True,
                    "package_status": "blocked",
                    "run_integrity_status": "warn",
                    "blocking_issues": ["submission_package: 修复队列仍有 1 个 block 任务，不应把当前包标记为最终版本。"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertFalse(any(item.source_artifact == "14-final-handoff.json" for item in report.items))

    def test_repair_queue_blocks_llm_runtime_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "13-llm-runtime-contract.json",
                {
                    "status": "block",
                    "blocking_issues": ["run-config.json 中 llm.api_key 非空"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            item = next(item for item in report.items if item.source_artifact == "13-llm-runtime-contract.json")
            self.assertEqual(item.category, "llm_runtime_contract")
            self.assertEqual(item.rerun_from, "checkpoint")
            self.assertTrue(item.blocks_submission)

    def test_repair_queue_blocks_open_source_compliance_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "13-open-source-compliance.json",
                {"status": "block", "blocking_issues": ["外部项目约束未闭环"], "manual_tasks": []},
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "13-open-source-compliance.json" for item in report.items))
            self.assertTrue(any(item.category == "open_source_compliance" for item in report.items))

    def test_repair_queue_surfaces_agent_observability_review_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {
                    "status": "review_required",
                    "blocking_issues": [],
                    "manual_tasks": ["LLM 预算压力接近上限：calls=0.90"],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            self.assertTrue(any(item.source_artifact == "13-agent-observability-audit.json" for item in report.items))
            self.assertTrue(any(item.severity == "high" for item in report.items))

    def test_repair_queue_backfill_converts_observability_blocks_to_open_queue(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["run-manifest artifact inventory 缺少关键文件"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            dry = backfill_repair_queues(runs_dir, dry_run=True)
            report = backfill_repair_queues(runs_dir)
            rendered = render_repair_queue_backfill_markdown(report)
            saved = json.loads((run_dir / "12-repair-queue.json").read_text(encoding="utf-8"))

            self.assertEqual(dry["would_write"], 1)
            self.assertEqual(report["written"], 1)
            self.assertEqual(report["items"][0]["status"], "blocked_repair_required")
            self.assertEqual(saved["status"], "blocked_repair_required")
            self.assertEqual(saved["summary"]["block"], 1)
            self.assertTrue((run_dir / "12-repair-queue.md").exists())
            self.assertIn("Repair Queue Backfill", rendered)

    def test_repair_queue_surfaces_literature_search_feedback_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-search-feedback.json",
                {
                    "status": "needs_search_revision",
                    "retrieval_repair_tasks": [
                        {
                            "task_id": "retrieval-repair-001",
                            "category": "query_repair",
                            "action": "执行补检索式并合并去重候选。",
                        }
                    ],
                    "approval_guidance": ["不要直接批准进入 idea/实验。"],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            self.assertTrue(any(item.source_artifact == "01-literature-search-feedback.json" for item in report.items))
            self.assertTrue(any(item.category == "literature_search_feedback" for item in report.items))

    def test_repair_queue_surfaces_seed_role_coverage_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
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

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            item = next(item for item in report.items if item.source_artifact == "01-seed-paper-intake.json")
            self.assertEqual(item.category, "seed_papers")
            self.assertEqual(item.severity, "high")
            self.assertIn("role_coverage_status=review_required", item.trigger_status)
            self.assertTrue(item.blocks_downstream)

    def test_repair_queue_surfaces_missing_seed_intake_suggestions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-quality.json",
                {
                    "items": [
                        {
                            "title": "The Open Motion Planning Library",
                            "doi": "10.1109/MRA.2012.2205651",
                            "url": "https://doi.org/10.1109/MRA.2012.2205651",
                            "selected": True,
                            "quality_score": 0.94,
                            "evidence_roles": ["benchmark_dataset", "baseline_method"],
                        }
                    ]
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            item = next(item for item in report.items if item.source_artifact == "01-seed-paper-intake.json")
            self.assertEqual(item.category, "seed_papers")
            self.assertEqual(item.severity, "high")
            self.assertIn("status=missing", item.trigger_status)
            self.assertIn("suggested_seed_count=1", item.trigger_status)
            self.assertIn("survey review", item.evidence)
            self.assertTrue(item.blocks_downstream)

    def test_repair_queue_surfaces_failed_literature_rescue_execution(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-rescue-execution.json",
                {
                    "status": "no_new_papers",
                    "repair_task_ids": ["retrieval-repair-001"],
                    "query_outcomes": [
                        {
                            "query": "robot manipulator OMPL benchmark",
                            "repair_task_ids": ["retrieval-repair-001"],
                            "status": "no_hits",
                            "matched_candidates": 0,
                            "new_unique_candidates": 0,
                            "final_new_papers": 0,
                        }
                    ],
                    "required_actions": ["检索修复任务 retrieval-repair-001 未闭环。"],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            item = next(item for item in report.items if item.source_artifact == "01-literature-rescue-execution.json")
            self.assertEqual(item.category, "literature_rescue_execution")
            self.assertEqual(item.severity, "high")
            self.assertTrue(item.blocks_downstream)

    def test_repair_queue_surfaces_query_execution_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-query-execution-audit.json",
                {
                    "status": "needs_query_repair",
                    "required_actions": ["补齐 selected_queries 缺失的检索意图：baseline"],
                    "recommended_actions": ["补 baseline query"],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_repair")
            self.assertTrue(any(item.source_artifact == "01-query-execution-audit.json" for item in report.items))
            self.assertTrue(any(item.category == "query_execution" for item in report.items))

    def test_repair_queue_surfaces_weak_literature_search_strategy(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-search-strategy.json",
                {
                    "status": "needs_query_repair",
                    "quality_score": 0.42,
                    "missing_required_intents": ["baseline", "benchmark"],
                    "weak_selected_queries": ["robot"],
                    "recommendations": ["补 baseline 和 benchmark query"],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "01-literature-search-strategy.json" for item in report.items))
            self.assertTrue(any(item.category == "literature_search_strategy" for item in report.items))

    def test_repair_queue_downgrades_query_residual_after_paper_grade_literature_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "01-literature-gate-decision.json",
                {"status": "pass", "paper_grade_literature": {"status": "pass", "issues": []}},
            )
            write_json(
                run_dir / "01-literature-search-strategy.json",
                {
                    "status": "needs_query_repair",
                    "quality_score": 0.42,
                    "missing_required_intents": ["method"],
                    "weak_selected_queries": ["iris"],
                    "recommendations": ["补 method query"],
                },
            )

            report = build_repair_queue_report("Iris benchmark smoke", run_dir)

            self.assertEqual(report.status, "needs_repair")
            self.assertFalse(report.blocking_issues)
            item = next(item for item in report.items if item.source_artifact == "01-literature-search-strategy.json")
            self.assertEqual(item.severity, "high")

    def test_repair_queue_ignores_stale_calibration_and_deferred_tasks_after_clean_revised_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "07-paper-review-calibration.json",
                {
                    "status": "block",
                    "blocking_issues": ["原始草稿仍有 unsupported claim。"],
                    "required_actions": ["重写原始草稿。"],
                },
            )
            write_json(
                run_dir / "10-final-readiness.json",
                {
                    "status": "ready_for_submission_check",
                    "unsupported_after": 0,
                    "weak_after": 0,
                    "deferred_tasks": ["旧修订任务已由当前修订稿关闭。"],
                    "blocking_issues": [],
                },
            )
            write_json(run_dir / "10-revised-paper-review.json", {"decision": "accept_with_minor_revisions", "score": 8.0, "unsupported_claims": []})
            write_json(run_dir / "10-claim-traceability.json", {"status": "pass"})

            report = build_repair_queue_report("Iris benchmark smoke", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.summary["total"], 0)

    def test_repair_queue_ignores_stale_package_block_caused_by_old_repair_queue(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "11-submission-package.json",
                {
                    "status": "blocked",
                    "blocking_issues": ["修复队列仍有 4 个 block 任务，不应把当前包标记为最终版本。"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("Iris benchmark smoke", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertFalse(report.items)

    def test_repair_queue_ignores_pass_artifact_required_actions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "03-experiment-audit.json",
                {
                    "status": "pass",
                    "required_actions": ["实验计划已通过结构审计，可以进入执行。"],
                    "blocking_issues": [],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("Iris benchmark smoke", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertFalse(report.items)

    def test_repair_queue_blocks_idea_experiment_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "03-idea-experiment-contract.json",
                {
                    "status": "block",
                    "blocking_issues": ["实验计划标题必须与选中 idea 一致。"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "03-idea-experiment-contract.json" for item in report.items))
            self.assertTrue(any(item.category == "idea_experiment_contract" for item in report.items))

    def test_repair_queue_blocks_review_constraint_compliance(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "03-review-constraint-compliance.json",
                {
                    "status": "block",
                    "blocked": 1,
                    "review_required": 0,
                    "human_brief_constraints": 1,
                    "blocking_issues": ["HB-C01 未落实：必须比较 RRT*"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            item = next(item for item in report.items if item.source_artifact == "03-review-constraint-compliance.json")
            self.assertEqual(item.category, "review_constraints")
            self.assertEqual(item.rerun_from, "experiment_plan")
            self.assertTrue(item.blocks_downstream)
            self.assertIn("RRT", item.evidence)

    def test_repair_queue_blocks_claim_boundary_preflight(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {
                    "status": "block",
                    "writing_mode": "repair_report_only",
                    "blocking_issues": ["实验后决策不允许正常写作"],
                    "warnings": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "04-claim-boundary-preflight.json" for item in report.items))
            self.assertTrue(any("正常写作" in issue for issue in report.blocking_issues))

    def test_repair_queue_blocks_revision_response_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "09-revision-response-audit.json",
                {
                    "status": "block",
                    "response_score": 0.4,
                    "blocking_issues": ["R01 高优先级任务缺少正文回应"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "09-revision-response-audit.json" for item in report.items))
            self.assertTrue(any(item.rerun_from == "paper_rewrite" for item in report.items))

    def test_repair_queue_blocks_citation_coverage_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "10-citation-coverage.json",
                {
                    "status": "block",
                    "coverage_score": 0.2,
                    "blocking_issues": ["正文没有可核对 citation marker"],
                    "manual_tasks": [],
                },
            )

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked_repair_required")
            self.assertTrue(any(item.source_artifact == "10-citation-coverage.json" for item in report.items))
            self.assertTrue(any(item.rerun_from == "paper_rewrite" for item in report.items))

    def test_repair_queue_passes_when_audits_are_clean(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "01-literature-metadata-audit.json", {"status": "pass", "blocked": 0, "review_required": 0, "required_actions": []})
            write_json(run_dir / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "unsupported_after": 0, "weak_after": 0, "deferred_tasks": []})

            report = build_repair_queue_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "pass")
            self.assertEqual(report.items, [])
            self.assertEqual(report.summary["total"], 0)


if __name__ == "__main__":
    unittest.main()
