from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.run_memory import build_run_memory, render_run_memory_markdown, write_run_memory


class RunMemoryTest(unittest.TestCase):
    def test_memory_collects_cross_run_repair_signals(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            literature = runs_dir / "literature-run"
            experiment = runs_dir / "experiment-run"
            failed = runs_dir / "failed-run"
            literature.mkdir(parents=True)
            experiment.mkdir(parents=True)
            failed.mkdir(parents=True)

            write_json(literature / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(literature / "01-literature-quality.json", {"selected_papers": 2, "total_papers": 4})
            write_json(
                literature / "01-literature-rescue-plan.json",
                {
                    "status": "needs_source_repair",
                    "rescue_queries": [{"query": "robot manipulator motion planning benchmark"}],
                    "source_repairs": ["设置 SEMANTIC_SCHOLAR_API_KEY 后重跑，避免 Semantic Scholar 429。"],
                    "required_actions": ["先修复文献源/API key，再执行补检索式。"],
                },
            )

            write_json(experiment / "state.json", {"topic": "实验失败", "stage": "completed", "updated_at": "2026-06-08T11:00:00+00:00"})
            write_json(experiment / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(experiment / "04-result-validation.json", {"status": "block", "blocking_issues": ["存在 timeout 结果"], "warnings": []})
            write_json(
                experiment / "04-failure-analysis.json",
                {
                    "status": "block",
                    "summary": {"failed_runs": 1, "negative_metrics": 1, "uncertain_metrics": 1},
                    "required_actions": ["重跑或修复失败/阻断/超时命令。"],
                },
            )
            write_json(experiment / "04-hypothesis-outcome.json", {"status": "block", "outcome": "blocked_unverified", "next_actions": ["补齐统计比较。"]})
            write_json(experiment / "04-experiment-runbook.json", {"execution": {"mode": "simulated"}})
            write_json(experiment / "03-benchmark-plan.json", {"required_actions": ["接入真实 benchmark。"]})
            write_json(experiment / "10-citation-grounding.json", {"status": "review_required", "blocked_citations": 0, "review_citations": 2})
            write_json(experiment / "10-citation-coverage.json", {"status": "review_required", "coverage_score": 0.55, "blocking_issues": [], "manual_tasks": ["高相关 context 文献未进入正文"]})
            write_json(experiment / "10-results-presentation.json", {"status": "review_required", "blocking_issues": [], "manual_tasks": ["补图表引用和 CI 表述"]})

            write_json(failed / "state.json", {"topic": "配置失败", "stage": "failed", "updated_at": "2026-06-08T12:00:00+00:00"})
            write_json(failed / "run-diagnostics.json", {"category": "llm_configuration"})

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

            categories = {item.category for item in memory.recurring_signals}
            self.assertEqual(memory.status, "needs_process_repair")
            self.assertIn("literature_repair", categories)
            self.assertIn("result_validation", categories)
            self.assertIn("failure_or_negative_results", categories)
            self.assertIn("hypothesis_outcome", categories)
            self.assertIn("simulated_evidence", categories)
            self.assertIn("benchmark_gap", categories)
            self.assertIn("citation_grounding", categories)
            self.assertIn("citation_coverage", categories)
            self.assertIn("results_presentation", categories)
            self.assertIn("llm_configuration", categories)
            self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in memory.next_run_checklist))
            self.assertTrue(any("模型未配置" in item for item in memory.recommended_defaults))
            self.assertIn("Runs 复盘记忆", rendered)
            self.assertIn("literature_repair", rendered)

    def test_write_memory_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "runs" / "one-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "测试", "stage": "completed", "updated_at": "now"})
            memory = build_run_memory(root / "runs")

            json_path, md_path = write_run_memory(memory, root)

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["total_runs"], 1)
            self.assertIn("Runs 复盘记忆", md_path.read_text(encoding="utf-8"))

    def test_publishable_negative_or_neutral_benchmark_does_not_create_repair_memory(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "neutral-benchmark"
            run_dir.mkdir(parents=True)
            warning = "candidate-baseline 差值为 0 且 CI 零宽，不能声明优势。"
            write_json(run_dir / "state.json", {"topic": "neutral", "stage": "completed", "updated_at": "2026-06-08T12:00:00+00:00"})
            write_json(run_dir / "04-result-validation.json", {"status": "warn", "blocking_issues": [], "warnings": [warning]})
            write_json(
                run_dir / "04-failure-analysis.json",
                {
                    "status": "warn",
                    "summary": {"failed_runs": 0, "negative_metrics": 3, "uncertain_metrics": 3},
                    "required_actions": ["报告负/中性结果。"],
                },
            )
            write_json(
                run_dir / "04-benchmark-evidence-audit.json",
                {
                    "status": "warn",
                    "evidence_grade": "real_benchmark",
                    "claim_boundary_severity": "negative_or_neutral_no_superiority",
                    "publishable_negative_or_neutral_result": True,
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "refuted_or_negative"})
            write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})

            memory = build_run_memory(runs_dir)
            categories = {item.category for item in memory.recurring_signals}

            self.assertNotIn("result_validation", categories)
            self.assertNotIn("failure_or_negative_results", categories)
            self.assertNotIn("hypothesis_outcome", categories)

    def test_unbounded_negative_or_neutral_benchmark_creates_repair_memory(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "unbounded-neutral-benchmark"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "neutral", "stage": "completed", "updated_at": "2026-06-08T12:00:00+00:00"})
            write_json(run_dir / "04-result-validation.json", {"status": "warn", "blocking_issues": [], "warnings": ["结果为中性，不能声明优势。"]})
            write_json(
                run_dir / "04-failure-analysis.json",
                {
                    "status": "warn",
                    "summary": {"failed_runs": 0, "negative_metrics": 3, "uncertain_metrics": 3},
                    "required_actions": ["报告负/中性结果。"],
                },
            )
            write_json(
                run_dir / "04-benchmark-evidence-audit.json",
                {
                    "status": "warn",
                    "evidence_grade": "real_benchmark",
                    "claim_boundary_severity": "superiority_claim_risk",
                    "publishable_negative_or_neutral_result": True,
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "refuted_or_negative"})
            write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})

            memory = build_run_memory(runs_dir)
            categories = {item.category for item in memory.recurring_signals}

            self.assertIn("result_validation", categories)
            self.assertIn("failure_or_negative_results", categories)
            self.assertIn("hypothesis_outcome", categories)

    def test_memory_collects_experiment_manager_signals(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            blocked = runs_dir / "manager-blocked"
            smoke = runs_dir / "manager-smoke"
            blocked.mkdir(parents=True)
            smoke.mkdir(parents=True)
            write_json(blocked / "state.json", {"topic": "分支阻断", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(blocked / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                blocked / "02-experiment-manager.json",
                {
                    "status": "block",
                    "manager_decision": "needs_human_reselection",
                    "execution_policy": "blocked",
                    "selected_branch_id": "b1",
                    "selected_idea_title": "证据不可核对分支",
                    "required_actions": ["选中分支的 idea audit 为 block；修正不可核对 citation/chunk 或人工改选。"],
                },
            )
            write_json(smoke / "state.json", {"topic": "高风险分支", "stage": "completed", "updated_at": "2026-06-08T11:00:00+00:00"})
            write_json(smoke / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                smoke / "02-experiment-manager.json",
                {
                    "status": "review_required",
                    "manager_decision": "proceed_with_cautions",
                    "execution_policy": "smoke_first",
                    "selected_branch_id": "b2",
                    "selected_idea_title": "高风险分支",
                    "planning_constraints": ["先规划低成本 smoke-first 实验；不要把 smoke 结果写成最终科学结论。"],
                    "next_expansion_candidates": [{"branch_id": "b3", "title": "替代分支"}],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        severities = {item.category: item.severity for item in memory.recurring_signals}
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(severities["experiment_manager"], "block")
        self.assertEqual(severities["experiment_manager_smoke_first"], "warn")
        self.assertEqual(severities["experiment_branch_backlog"], "info")
        self.assertTrue(any("02-experiment-manager" in item for item in memory.recommended_defaults))
        self.assertTrue(any("next_expansion_candidates" in item for item in memory.next_run_checklist))
        self.assertIn("experiment_manager_smoke_first", rendered)

    def test_memory_collects_benchmark_result_schema_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "schema-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Benchmark schema", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "04-benchmark-result-schema-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["benchmark result provenance 不完整：candidate: license, baseline_version, citation"],
                    "manual_tasks": [],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        categories = {item.category: item for item in memory.recurring_signals}
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(categories["benchmark_result_schema"].severity, "block")
        self.assertTrue(any("baseline_version" in item for item in memory.next_run_checklist))
        self.assertTrue(any("metrics_path" in item for item in memory.recommended_defaults))
        self.assertIn("benchmark_result_schema", rendered)

    def test_memory_collects_llm_trace_audit_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "llm-trace-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "LLM trace", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-llm-trace-audit.json",
                {
                    "status": "block",
                    "coverage": {"required_stages": 7, "passed_required": 4, "coverage_ratio": 0.571},
                    "ledger_summary": {"total_calls": 5, "successful_calls": 4, "failed_calls": 1, "budget_exceeded_calls": 0},
                    "blocking_issues": ["paper_writing: 06-paper.md 已生成，但匹配到的成功 LLM 调用为 0/1。"],
                    "warnings": [],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "llm_trace_audit")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("coverage=4/7" in item for item in signal.evidence))
        self.assertTrue(any("run-llm-ledger" in item for item in memory.recommended_defaults))
        self.assertTrue(any("13-llm-trace-audit" in item for item in memory.next_run_checklist))
        self.assertIn("llm_trace_audit", rendered)

    def test_memory_collects_run_economics_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "economics-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Run economics", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-run-economics-audit.json",
                {
                    "status": "review_required",
                    "summary": {
                        "total_calls": 3,
                        "failed_calls": 0,
                        "budget_exceeded_calls": 0,
                        "input_tokens_estimated": 4500,
                        "output_tokens_estimated": 900,
                        "call_utilization": 1.0,
                        "prompt_utilization": 0.92,
                        "estimated_cost_usd": None,
                    },
                    "budget": {"call_utilization": 1.0, "prompt_utilization": 0.92},
                    "pricing": {"cost_estimation_enabled": False},
                    "blocking_issues": [],
                    "manual_tasks": ["只配置了部分 token 单价，美元成本不完整。"],
                    "warnings": ["LLM 使用接近配置预算上限：calls=1.00"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "run_economics")
        self.assertEqual(memory.status, "has_carry_forward_work")
        self.assertEqual(signal.severity, "warn")
        self.assertTrue(any("call_util=1.00" in item for item in signal.evidence))
        self.assertTrue(any("13-run-economics-audit" in item for item in memory.recommended_defaults))
        self.assertTrue(any("13-run-economics-audit" in item for item in memory.next_run_checklist))
        self.assertIn("run_economics", rendered)

    def test_memory_collects_agent_observability_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "observability-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Observability", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
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
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "agent_observability")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("events=0" in item for item in signal.evidence))
        self.assertTrue(any("manifest events" in item for item in memory.recommended_defaults))
        self.assertTrue(any("diagnostics" in item for item in memory.next_run_checklist))
        self.assertIn("agent_observability", rendered)

    def test_memory_collects_agent_stage_contract_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "stage-contract-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Stage contract", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-agent-stage-contract.json",
                {
                    "status": "block",
                    "score": 0.44,
                    "checks": [
                        {"stage": "literature_grounding", "status": "block", "required_actions": ["补充高相关文献。"]},
                        {"stage": "human_review_gate", "status": "missing", "required_actions": ["人工批准 review gate。"]},
                        {"stage": "release_reproducibility", "status": "warn", "required_actions": ["补 release 元数据。"]},
                    ],
                    "blocking_issues": ["补充高相关文献或 seed papers，确保至少 3 篇文献进入 context。"],
                    "manual_tasks": ["完成 code/data、投稿格式和 ZIP 上传前的人工待办。"],
                    "recommended_actions": ["先处理阻断问题，再运行 repair-resume。"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "agent_stage_contract")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("blocked_stages=literature_grounding,human_review_gate" in item for item in signal.evidence))
        self.assertTrue(any("13-agent-stage-contract" in item for item in memory.recommended_defaults))
        self.assertTrue(any("stage-contract" in item or "13-agent-stage-contract" in item for item in memory.next_run_checklist))
        self.assertIn("agent_stage_contract", rendered)

    def test_memory_collects_research_scorecard_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "scorecard-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Scorecard", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "13-research-scorecard.json",
                {
                    "status": "blocked",
                    "overall_score": 42.0,
                    "dimensions": [
                        {"category": "experiment_benchmark", "score": 20.0, "status": "block"},
                        {"category": "literature_evidence", "score": 35.0, "status": "manual_required"},
                        {"category": "paper_quality", "score": 50.0, "status": "warn"},
                    ],
                    "blocking_issues": ["experiment_benchmark: candidate 与 baseline 没有共同指标。"],
                    "manual_tasks": ["literature_evidence: 补 seed papers。"],
                    "next_actions": ["修复实验结果验证。"],
                    "recommendation": "当前 run 总分 42.0/100，仍有阻断项。",
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "research_scorecard")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("overall=42.0" in item for item in signal.evidence))
        self.assertTrue(any("experiment_benchmark:20.0" in item for item in signal.evidence))
        self.assertTrue(any("13-research-scorecard" in item for item in memory.recommended_defaults))
        self.assertTrue(any("13-research-scorecard" in item for item in memory.next_run_checklist))
        self.assertIn("research_scorecard", rendered)

    def test_memory_collects_run_integrity_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "integrity-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Integrity", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "14-run-integrity-audit.json",
                {
                    "status": "block",
                    "summary": {"checks": 7, "pass": 4, "warn": 1, "block": 2, "required_artifacts": 150},
                    "items": [
                        {"category": "artifacts", "name": "required_inventory", "status": "block", "evidence": "缺少 run-manifest.json"},
                        {"category": "security", "name": "secret_persistence", "status": "warn", "evidence": "run-config contains api_key"},
                    ],
                    "blocking_issues": ["artifacts/required_inventory: 缺少 run-manifest.json"],
                    "warnings": ["security/secret_persistence: run-config contains api_key"],
                    "recommended_actions": ["补齐 required artifacts 后重跑 integrity audit。"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "run_integrity_audit")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("block=2" in item for item in signal.evidence))
        self.assertTrue(any("artifacts:required_inventory" in item for item in signal.evidence))
        self.assertTrue(any("14-run-integrity-audit" in item for item in memory.recommended_defaults))
        self.assertTrue(any("artifact inventory" in item for item in memory.next_run_checklist))
        self.assertIn("run_integrity_audit", rendered)

    def test_memory_collects_final_handoff_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            blocked = runs_dir / "handoff-blocked"
            manual = runs_dir / "handoff-manual"
            blocked.mkdir(parents=True)
            manual.mkdir(parents=True)
            write_json(blocked / "state.json", {"topic": "Final handoff", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(blocked / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                blocked / "14-final-handoff.json",
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
            write_json(manual / "state.json", {"topic": "Final handoff", "stage": "completed", "updated_at": "2026-06-08T11:00:00+00:00"})
            write_json(manual / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                manual / "14-final-handoff.json",
                {
                    "status": "ready_for_human_handoff",
                    "package_zip": "11-submission-package.zip",
                    "package_zip_exists": True,
                    "package_status": "ready_for_human_submission_upload",
                    "scorecard_status": "ready_for_human_submission_upload",
                    "run_integrity_status": "pass",
                    "package_has_integrity_audit": False,
                    "blocking_issues": [],
                    "manual_tasks": ["submission package 未包含 run-integrity-audit.json。"],
                    "recommended_actions": ["人工核对 ZIP、scorecard、完整性审计和 submission checklist。"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "final_handoff")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertEqual(signal.count, 2)
        self.assertTrue(any("zip_exists=N" in item for item in signal.evidence))
        self.assertTrue(any("ready_for_human_handoff" in item for item in signal.evidence))
        self.assertTrue(any("14-final-handoff" in item for item in memory.recommended_defaults))
        self.assertTrue(any("14-final-handoff" in item for item in memory.next_run_checklist))
        self.assertIn("final_handoff", rendered)

    def test_memory_collects_invalid_upload_ready_final_handoff_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "handoff-invalid-zip"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Final handoff", "stage": "completed", "updated_at": "2026-06-08T12:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "package_zip": "11-submission-package.zip",
                    "package_zip_exists": True,
                    "package_zip_valid": False,
                    "package_status": "ready_for_human_submission_upload",
                    "scorecard_status": "ready_for_human_submission_upload",
                    "run_integrity_status": "pass",
                    "package_has_integrity_audit": True,
                    "blocking_issues": [],
                    "manual_tasks": [],
                    "recommended_actions": [],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "final_handoff")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertEqual(signal.count, 1)
        self.assertTrue(any("ready_for_submission_upload" in item for item in signal.evidence))
        self.assertTrue(any("zip_valid=N" in item for item in signal.evidence))
        self.assertTrue(any("ZIP 缺失或无效" in item for item in memory.next_run_checklist))
        self.assertIn("final_handoff", rendered)

    def test_memory_collects_repair_resolution_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "repair-resolution-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "Repair resolution", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
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
                    "resolved_items": [{"task_id": "R2", "severity": "high", "category": "release"}],
                    "new_items": [{"task_id": "R3", "severity": "medium", "category": "citation"}],
                    "blocking_issues": ["04-result-validation.json/result_validation: 共同指标仍缺失"],
                    "manual_tasks": [],
                    "required_actions": ["继续从 repair queue 恢复。"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "repair_resolution_audit")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("remaining=1" in item for item in signal.evidence))
        self.assertTrue(any("rerun_from=experiment_plan" in item for item in signal.evidence))
        self.assertTrue(any("12-repair-resolution-audit" in item for item in memory.recommended_defaults))
        self.assertTrue(any("repair-resume" in item for item in memory.next_run_checklist))
        self.assertIn("repair_resolution_audit", rendered)

    def test_memory_collects_literature_search_feedback_signal(self) -> None:
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
                        {"query": "robot manipulator motion planning OMPL benchmark RRT* CHOMP", "priority": 96, "source": "coverage"},
                        {"query": "TrajOpt STOMP robot arm trajectory optimization baseline", "priority": 90, "source": "snowball"},
                    ],
                    "seed_paper_targets": [{"category": "benchmark", "name": "OMPL", "hint": "补 OMPL DOI seed"}],
                    "source_actions": ["文献源暂无结构化故障；重点补 query 和 seed paper。"],
                    "retrieval_repair_tasks": [
                        {
                            "category": "query_repair",
                            "priority": 96,
                            "owner": "agent",
                            "action": "执行补检索式并合并去重候选。",
                            "query": "robot manipulator motion planning OMPL benchmark RRT* CHOMP",
                            "rationale": "补齐 benchmark/method 覆盖。",
                        }
                    ],
                    "next_run_config": {
                        "literature_provider": "online",
                        "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
                        "max_papers": 14,
                        "max_search_queries": 7,
                        "seed_papers_min": 3,
                    },
                    "approval_guidance": ["不要直接批准进入 idea/实验；先按本反馈策略补检索或补 seed_papers。"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "literature_search_feedback")
        self.assertEqual(memory.status, "has_carry_forward_work")
        self.assertEqual(signal.severity, "warn")
        self.assertTrue(any("recommended_queries=2" in item for item in signal.evidence))
        self.assertTrue(any("agent_queries=1" in item for item in signal.evidence))
        self.assertTrue(any("seed_min:3" in item for item in signal.evidence))
        self.assertTrue(any("01-literature-search-feedback" in item for item in memory.recommended_defaults))
        self.assertTrue(any("OMPL benchmark" in item for item in memory.next_run_checklist))
        self.assertEqual(memory.recommended_config["literature_provider"], "online")
        self.assertEqual(memory.recommended_config["max_papers"], 14)
        self.assertEqual(memory.recommended_config["max_search_queries"], 7)
        self.assertEqual(memory.recommended_config["seed_papers_min"], 3)
        self.assertIn("semantic_scholar", memory.recommended_config["sources"])
        self.assertIn("robot manipulator motion planning OMPL benchmark RRT* CHOMP", memory.recommended_config["extra_search_queries"])
        self.assertTrue(memory.recommended_config["manual_seed_required"])
        self.assertEqual(signal.recommended_config["max_papers"], 14)
        self.assertIn("推荐表单配置", rendered)
        self.assertIn("literature_search_feedback", rendered)

    def test_memory_collects_seed_role_coverage_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "seed-role-review"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
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

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "seed_paper_intake")
        self.assertEqual(memory.status, "has_carry_forward_work")
        self.assertEqual(signal.severity, "warn")
        self.assertTrue(any("role_coverage=review_required" in item for item in signal.evidence))
        self.assertTrue(any("missing_roles=review,benchmark_dataset" in item for item in signal.evidence))
        self.assertTrue(any("至少 3 类" in item for item in memory.next_run_checklist))
        self.assertIn("seed_paper_intake", rendered)

    def test_memory_collects_literature_source_health_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "source-health-blocked"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 10})
            write_json(
                run_dir / "01-literature-source-health.json",
                {
                    "topic": "机械臂路径规划",
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
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "literature_source_health")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("query_successes=0" in item for item in signal.evidence))
        self.assertTrue(any("semantic_scholar" in item for item in signal.evidence))
        self.assertTrue(any("01-literature-source-health" in item for item in memory.recommended_defaults))
        self.assertTrue(any("SEMANTIC_SCHOLAR_API_KEY" in item for item in memory.next_run_checklist))
        self.assertEqual(memory.recommended_config["literature_provider"], "online")
        self.assertEqual(memory.recommended_config["max_papers"], 12)
        self.assertEqual(memory.recommended_config["max_search_queries"], 6)
        self.assertNotIn("semantic_scholar", memory.recommended_config["sources"])
        self.assertTrue(memory.recommended_config["semantic_scholar_api_key_required"])
        self.assertTrue(memory.recommended_config["contact_email_required"])
        self.assertIn("literature_source_health", rendered)

    def test_memory_collects_literature_rescue_execution_signal(self) -> None:
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
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "literature_rescue_execution")
        self.assertEqual(memory.status, "has_carry_forward_work")
        self.assertEqual(signal.severity, "warn")
        self.assertTrue(any("unresolved=1" in item for item in signal.evidence))
        self.assertTrue(any("01-literature-rescue-execution" in item for item in memory.recommended_defaults))
        self.assertTrue(any("robot manipulator OMPL benchmark" in item for item in memory.next_run_checklist))
        self.assertIn("literature_rescue_execution", rendered)

    def test_memory_collects_environment_snapshot_signal(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            partial = runs_dir / "env-partial"
            missing_source = runs_dir / "env-missing-source"
            partial.mkdir(parents=True)
            missing_source.mkdir(parents=True)
            write_json(partial / "state.json", {"topic": "环境快照", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(partial / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                partial / "04-environment-snapshot.json",
                {
                    "status": "partial",
                    "warnings": ["部分白名单命令当前不可定位：pytest"],
                    "package_versions": [{"name": "pip", "version": "25.0"}],
                    "tool_versions": [{"command": "pytest", "available": False, "path": ""}],
                    "source_tree": {"file_count": 3, "aggregate_sha256": "abc"},
                },
            )
            write_json(missing_source / "state.json", {"topic": "源码缺失", "stage": "completed", "updated_at": "2026-06-08T11:00:00+00:00"})
            write_json(missing_source / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                missing_source / "04-environment-snapshot.json",
                {
                    "status": "partial",
                    "warnings": ["未能记录源码快照，复现时无法核对代码版本。"],
                    "package_versions": [],
                    "tool_versions": [],
                    "source_tree": {"file_count": 0, "aggregate_sha256": ""},
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "environment_snapshot")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertEqual(signal.count, 2)
        self.assertTrue(any("source_files=0" in item for item in signal.evidence))
        self.assertTrue(any("04-environment-snapshot" in item for item in memory.recommended_defaults))
        self.assertTrue(any("release.environment_url" in item for item in memory.next_run_checklist))
        self.assertIn("environment_snapshot", rendered)

    def test_memory_carries_release_metadata_recommended_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "release-metadata-missing"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "发布元数据", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "10-code-data-availability.json",
                {
                    "status": "needs_human_release_metadata",
                    "manual_tasks": ["Release metadata 仍缺少公开仓库、数据说明和环境归档。"],
                    "blocking_issues": [],
                },
            )
            write_json(
                run_dir / "10-release-metadata.json",
                {
                    "status": "needs_release_metadata",
                    "recommended_config": {
                        "required_fields": ["release_code_repository_url", "release_data_access_statement"],
                        "recommended_fields": ["release_data_archive_doi"],
                        "cli_args": [
                            "--release-code-repository-url",
                            "--release-data-access-statement",
                            "--release-data-archive-doi",
                        ],
                    },
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "release_metadata")
        self.assertEqual(memory.status, "has_carry_forward_work")
        self.assertEqual(signal.severity, "warn")
        self.assertIn("release_code_repository_url", memory.recommended_config["release_required_fields"])
        self.assertIn("release_data_archive_doi", memory.recommended_config["release_recommended_fields"])
        self.assertIn("--release-code-repository-url", memory.recommended_config["release_cli_args"])
        self.assertIn("release_required_fields", rendered)

    def test_memory_derives_release_fields_from_legacy_release_checks(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-release-metadata"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "旧发布元数据", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(
                run_dir / "10-code-data-availability.json",
                {
                    "status": "needs_human_release_metadata",
                    "manual_tasks": ["Release metadata 缺少代码仓库和代码归档。"],
                    "blocking_issues": [],
                },
            )
            write_json(
                run_dir / "10-release-metadata.json",
                {
                    "status": "needs_release_metadata",
                    "checks": [
                        {"item": "代码仓库 URL", "status": "manual_required"},
                        {"item": "代码归档 DOI", "status": "manual_required"},
                        {"item": "许可证", "status": "pass"},
                    ],
                },
            )

            memory = build_run_memory(runs_dir)

        self.assertIn("release_code_repository_url", memory.recommended_config["release_required_fields"])
        self.assertIn("release_code_archive_doi", memory.recommended_config["release_required_fields"])
        self.assertIn("--release-code-archive-doi", memory.recommended_config["release_cli_args"])

    def test_memory_collects_human_brief_constraint_compliance_signal(self) -> None:
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
                    "checked_constraints": 2,
                    "review_constraints": 0,
                    "human_brief_constraints": 2,
                    "blocked": 1,
                    "review_required": 1,
                    "blocking_issues": ["HB-C01 未落实：必须比较 RRT*"],
                    "manual_tasks": ["人工确认 HB-S01：成功率提升"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        categories = {item.category: item for item in memory.recurring_signals}
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(categories["human_brief_constraints"].severity, "block")
        self.assertTrue(any("human_constraints" in item for item in memory.next_run_checklist))
        self.assertTrue(any("03-review-constraint-compliance" in item for item in memory.recommended_defaults))
        self.assertIn("human_brief_constraints", rendered)

    def test_memory_collects_open_source_compliance_signal(self) -> None:
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
                    "lesson_results": [
                        {"lesson_id": "query_execution_coverage_audit", "status": "block"},
                        {"lesson_id": "runtime_cost_observability", "status": "warn"},
                    ],
                    "blocking_issues": ["Semantic Scholar 429 导致 selected query 没有 source 返回。"],
                    "manual_tasks": ["补齐 run-manifest 和 LLM ledger。"],
                },
            )

            memory = build_run_memory(runs_dir)
            rendered = render_run_memory_markdown(memory)

        signal = next(item for item in memory.recurring_signals if item.category == "open_source_compliance")
        self.assertEqual(memory.status, "needs_process_repair")
        self.assertEqual(signal.severity, "block")
        self.assertTrue(any("checked_lessons=12" in item for item in signal.evidence))
        self.assertTrue(any("query_execution_coverage_audit" in item for item in signal.evidence))
        self.assertTrue(any("13-open-source-compliance" in item for item in memory.recommended_defaults))
        self.assertTrue(any("open_source_compliance" in item for item in memory.carry_forward_notes))
        self.assertIn("open_source_compliance", rendered)


if __name__ == "__main__":
    unittest.main()
