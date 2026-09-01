from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.iteration_plan import build_iteration_plan_report, render_iteration_plan_markdown, write_iteration_plan_artifacts


class IterationPlanTest(unittest.TestCase):
    def test_iteration_plan_prioritizes_human_evidence_and_real_benchmark(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "10-final-readiness.json",
                {
                    "status": "requires_human_evidence",
                    "next_actions": ["补齐 needs_human_evidence 任务", "删除 unsupported claim"],
                },
            )
            write_json(
                run_dir / "10-code-data-availability.json",
                {"status": "needs_human_release_metadata", "manual_tasks": ["补许可证"], "blocking_issues": []},
            )
            write_json(
                run_dir / "10-submission-check.json",
                {"status": "needs_human_format_check", "manual_tasks": ["换官方模板"], "blocking_issues": []},
            )
            write_json(
                run_dir / "11-submission-package.json",
                {"status": "needs_human_submission_review", "manual_tasks": ["核验 ZIP"], "blocking_issues": []},
            )
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "simulated"}, "warnings": ["模拟结果不能支撑强结论"]})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": ["接入真实数据"]})

            report = write_iteration_plan_artifacts("下一轮测试", run_dir)
            rendered = render_iteration_plan_markdown(report)

            self.assertEqual(report.status, "needs_human_evidence")
            self.assertTrue(any(item.category == "evidence" for item in report.items))
            self.assertTrue(any(item.category == "benchmark" for item in report.items))
            self.assertTrue(report.rerun_commands)
            self.assertFalse(any("--llm-api-key" in item for item in report.rerun_commands))
            self.assertTrue((run_dir / "12-next-iteration-plan.md").exists())
            self.assertIn("下一轮迭代计划", rendered)
            self.assertIn("暂停自动推进", rendered)

    def test_iteration_plan_allows_submission_upload_when_audits_are_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(run_dir / "04-experiment-decision.json", {"status": "pass", "decision": "proceed_to_paper", "next_actions": []})

            report = build_iteration_plan_report("下一轮测试", run_dir)

            self.assertEqual(report.status, "ready_for_submission_upload")
            self.assertEqual(report.items, [])
            self.assertIn("上传", report.decision)

    def test_iteration_plan_blocks_submission_upload_when_final_handoff_zip_is_invalid(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "package_zip_exists": True,
                    "package_zip_valid": False,
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(run_dir / "04-experiment-decision.json", {"status": "pass", "decision": "proceed_to_paper", "next_actions": []})

            report = build_iteration_plan_report("下一轮测试", run_dir)
            rendered = render_iteration_plan_markdown(report)

            self.assertEqual(report.status, "needs_targeted_iteration")
            self.assertTrue(any(item.category == "package" and "final handoff" in item.action.lower() for item in report.items))
            self.assertTrue(any("14-final-handoff.json 未报告 ZIP 缺失或无效" in item for item in report.stop_conditions))
            self.assertIn("package_zip_valid=false", rendered)

    def test_iteration_plan_prioritizes_literature_rescue_before_downstream_work(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(
                run_dir / "01-literature-rescue-plan.json",
                {"status": "needs_rescue_search", "required_actions": ["执行 priority >= 94 的补检索式"], "rescue_queries": [{"query": "CHOMP"}]},
            )

            report = build_iteration_plan_report("下一轮测试", run_dir)
            rendered = render_iteration_plan_markdown(report)

            self.assertEqual(report.status, "needs_literature_repair")
            self.assertTrue(any(item.category == "literature" for item in report.items))
            self.assertIn("补检索", rendered)
            self.assertTrue(any("01-literature-rescue-plan.json 状态为 pass" in item for item in report.stop_conditions))

    def test_iteration_plan_prioritizes_seed_role_coverage_before_downstream_work(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
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

            report = build_iteration_plan_report("下一轮测试", run_dir)
            rendered = render_iteration_plan_markdown(report)

            self.assertEqual(report.status, "needs_literature_repair")
            self.assertTrue(any(item.category == "literature" and "角色覆盖" in item.action for item in report.items))
            self.assertTrue(any("role_coverage_status" in item for item in report.stop_conditions))
            self.assertTrue(any("Seed intake: 补齐进入 curated context" in item for item in report.carry_forward_notes))
            self.assertIn("review, benchmark_dataset", rendered)

    def test_iteration_plan_prioritizes_failed_experiment_repairs(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(run_dir / "04-result-validation.json", {"status": "block", "blocking_issues": ["存在失败/阻断/超时结果"], "warnings": []})
            write_json(run_dir / "04-failure-analysis.json", {"status": "block", "required_actions": ["重跑 timeout 命令"]})
            write_json(run_dir / "04-experiment-decision.json", {"status": "block", "decision": "repair_before_writing", "next_actions": ["先修复实验"]})
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "block", "outcome": "blocked_unverified", "next_actions": ["补齐统计比较"]})

            report = build_iteration_plan_report("下一轮测试", run_dir)

            self.assertEqual(report.status, "needs_experiment_repair")
            self.assertTrue(any(item.category == "experiment" for item in report.items))
            self.assertTrue(any(item.category == "experiment_failure" for item in report.items))
            self.assertTrue(any(item.category == "experiment_decision" for item in report.items))
            self.assertTrue(any(item.category == "hypothesis" for item in report.items))
            self.assertTrue(any("04-result-validation.json 不再是 block" in item for item in report.stop_conditions))

    def test_iteration_plan_prioritizes_blocked_experiment_manager(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(
                run_dir / "02-experiment-manager.json",
                {"status": "block", "required_actions": ["选中分支的 idea audit 为 block；人工改选。"]},
            )

            report = build_iteration_plan_report("下一轮测试", run_dir)

            self.assertEqual(report.status, "needs_experiment_repair")
            self.assertTrue(any(item.category == "experiment_manager" for item in report.items))

    def test_iteration_plan_carries_forward_manager_next_branches(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(
                run_dir / "02-experiment-manager.json",
                {
                    "status": "review_required",
                    "manager_decision": "proceed_with_cautions",
                    "execution_policy": "smoke_first",
                    "selected_idea_title": "主分支",
                    "planning_constraints": ["先规划低成本 smoke-first 实验。"],
                    "next_expansion_candidates": [{"branch_id": "B2", "title": "候选分支", "reason": "非选中分支中分数较高"}],
                },
            )

            report = build_iteration_plan_report("下一轮测试", run_dir)
            rendered = render_iteration_plan_markdown(report)

            self.assertTrue(any("Experiment manager" in note for note in report.carry_forward_notes))
            self.assertTrue(any("候选分支" in note for note in report.carry_forward_notes))
            self.assertIn("smoke-first", rendered)

    def test_iteration_plan_uses_pivot_or_refine_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(run_dir / "04-experiment-decision.json", {"status": "warn", "decision": "pivot_or_refine", "next_actions": ["报告负结果"]})

            report = build_iteration_plan_report("下一轮测试", run_dir)

            self.assertEqual(report.status, "needs_experiment_repair")
            self.assertTrue(any(item.category == "experiment_decision" for item in report.items))
            self.assertTrue(any("报告负结果" in note for note in report.carry_forward_notes))

    def test_iteration_plan_prioritizes_revision_response_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(run_dir / "09-revision-response-audit.json", {"status": "block", "blocking_issues": ["R01 缺少正文回应"], "manual_tasks": []})

            report = build_iteration_plan_report("下一轮测试", run_dir)

            self.assertEqual(report.status, "needs_targeted_iteration")
            self.assertTrue(any(item.category == "revision" for item in report.items))
            self.assertTrue(any("Revision response" in note for note in report.carry_forward_notes))

    def test_iteration_plan_prioritizes_citation_coverage_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "next_actions": []})
            write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}, "warnings": []})
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
            write_json(run_dir / "10-citation-coverage.json", {"status": "review_required", "blocking_issues": [], "manual_tasks": ["高相关文献未引用"]})

            report = build_iteration_plan_report("下一轮测试", run_dir)

            self.assertEqual(report.status, "needs_targeted_iteration")
            self.assertTrue(any(item.category == "citation_coverage" for item in report.items))
            self.assertTrue(any("Citation coverage" in note for note in report.carry_forward_notes))


if __name__ == "__main__":
    unittest.main()
