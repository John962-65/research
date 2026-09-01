from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any
from unittest.mock import patch
import json
import time
import unittest

from research_agent.config import AgentConfig, ExecutionConfig, LiteratureConfig
from research_agent.artifacts import write_json, write_text
from research_agent.literature import render_literature_markdown, run_literature_review
from research_agent.literature_context import (
    build_literature_context,
    export_bibtex,
    export_ris,
    render_literature_context_markdown,
    render_review_gate_markdown,
)
from research_agent.research_plan import build_research_plan, render_research_plan_markdown
from research_agent.models import ExperimentCommand, ExperimentPlan, LiteratureContext, PaperRevisionPlan, ResearchIdea, ReviewGate, RevisionTask
import research_agent.pipeline as pipeline_module

class NoopLLM:
    model = "noop-test-model"
    base_url = "https://noop.example.test/v1"

    def complete(self, system: str, user: str) -> str:
        return "测试 LLM 输出"


def _run_pipeline_with_noop_llm(topic, out_dir, config):
    original = pipeline_module.build_llm
    pipeline_module.build_llm = lambda _: NoopLLM()
    errors = []
    results = []

    def worker():
        try:
            results.append(pipeline_module.run_pipeline(topic, out_dir, config))
        except BaseException as exc:  # pragma: no cover - surfaced in the parent thread
            errors.append(exc)

    thread = Thread(target=worker, daemon=True)
    try:
        thread.start()
        _wait_for_stage(out_dir, "awaiting_review_approval")
        if (out_dir / "02-ideas.json").exists():
            raise AssertionError("Pipeline generated ideas before review approval")
        pipeline_module.approve_review_gate(out_dir, reviewer="test", notes="人工确认文献风险，允许 smoke run 继续")
        if config.execution.mode in {"local", "benchmark"}:
            _wait_for_stage(out_dir, "awaiting_execution_approval")
            if (out_dir / "04-results.json").exists():
                raise AssertionError("Pipeline executed local/benchmark experiments before execution approval")
            pipeline_module.approve_execution_gate(out_dir, reviewer="test", notes="人工确认实验命令和安全审计后允许执行")
        thread.join(timeout=15)
        if thread.is_alive():
            raise AssertionError("Pipeline did not continue after review approval")
        if errors:
            raise errors[0]
        return results[0]
    finally:
        if thread.is_alive():
            try:
                pipeline_module.approve_review_gate(out_dir, reviewer="test-cleanup", notes="清理测试线程，人工允许继续退出")
            except FileNotFoundError:
                pass
            try:
                pipeline_module.approve_execution_gate(out_dir, reviewer="test-cleanup", notes="清理测试线程，人工允许执行退出")
            except (FileNotFoundError, RuntimeError):
                pass
            thread.join(timeout=5)
        pipeline_module.build_llm = original


def _wait_for_stage(out_dir: Path, expected: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    state_path = out_dir / "state.json"
    last_state = {}
    while time.monotonic() < deadline:
        if state_path.exists():
            try:
                last_state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                last_state = {}
            if last_state.get("stage") == expected:
                return last_state
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for stage {expected}; last state: {last_state}")


def _prepare_run_at_review_gate(topic: str, out: Path, config: AgentConfig) -> None:
    out.mkdir(parents=True, exist_ok=True)
    pipeline_module._validate_or_create_checkpoint_contract(out, topic, config)
    pipeline_module._write_run_config_snapshot(out, config)
    llm = NoopLLM()
    pipeline_module._write_state(out, topic, "started")
    write_text(out / "00-question.md", f"# 研究问题\n\n{topic}")
    research_plan = build_research_plan(topic, llm)
    write_json(out / "00-research-plan.json", research_plan)
    write_text(out / "00-research-plan.md", render_research_plan_markdown(research_plan))
    pipeline_module._write_state(out, topic, "research_plan_completed")
    review = run_literature_review(topic, config.literature, llm, research_plan.search_queries)
    write_json(out / "01-literature.json", review)
    write_text(out / "01-literature.md", render_literature_markdown(review))
    pipeline_module._write_state(out, topic, "literature_review_completed")
    context = build_literature_context(review)
    context, _citation_audit = pipeline_module.write_context_and_citation_artifacts(out, context, topic=topic)
    pipeline_module.request_review_approval(out, topic, context)
    pipeline_module._write_state(out, topic, "awaiting_review_approval")



class PipelineTest(unittest.TestCase):
    def test_revision_plan_checkpoint_must_match_current_review_signature(self) -> None:
        current = PaperRevisionPlan(
            topic="demo",
            decision="major_revision",
            readiness="major_revision_required",
            summary="当前复核分数为 3.0/10，存在旧任务。",
            tasks=[
                RevisionTask(
                    task_id="R01",
                    section="Experiments/Results",
                    severity="medium",
                    issue="旧 dry-run/scaffold 任务。",
                    action="旧动作。",
                    evidence_refs=[],
                )
            ],
            acceptance_checks=["旧检查。"],
            next_iteration_prompt="旧提示。",
        )
        expected = PaperRevisionPlan(
            topic="demo",
            decision="major_revision",
            readiness="major_revision_required",
            summary="当前复核分数为 4.0/10，存在新任务。",
            tasks=[
                RevisionTask(
                    task_id="R01",
                    section="Experiments/Results",
                    severity="medium",
                    issue="新 real benchmark 任务。",
                    action="新动作。",
                    evidence_refs=["04-benchmark-evidence-audit"],
                )
            ],
            acceptance_checks=["新检查。"],
            next_iteration_prompt="新提示。",
        )

        self.assertFalse(pipeline_module._paper_revision_plan_checkpoint_matches(current, expected))
        self.assertTrue(pipeline_module._paper_revision_plan_checkpoint_matches(expected, expected))

    def test_real_benchmark_checkpoint_allows_negated_dry_run_boundary(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_text("结果来自真实 benchmark adapter，而不是 dry-run、scaffold 或模拟替代。", encoding="utf-8")
            self.assertTrue(
                pipeline_module._paper_matches_benchmark_evidence(
                    path,
                    {"evidence_grade": "real_benchmark"},
                    "benchmark",
                )
            )
            path.write_text("当前结果只能视为 dry-run/scaffold 记录。", encoding="utf-8")
            self.assertFalse(
                pipeline_module._paper_matches_benchmark_evidence(
                    path,
                    {"evidence_grade": "real_benchmark"},
                    "benchmark",
                )
            )

    def test_offline_pipeline_writes_expected_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            _run_pipeline_with_noop_llm("auditable autonomous research agents", out, AgentConfig())
            expected = [
                "run-manifest.json",
                "run-manifest.md",
                "run-llm-ledger.json",
                "run-llm-ledger.md",
                "00-preflight.json",
                "00-preflight.md",
                "00-question.md",
                "00-human-brief.json",
                "00-human-brief.md",
                "00-prior-run-lessons.json",
                "00-prior-run-lessons.md",
                "00-prior-run-library.json",
                "00-prior-run-library.md",
                "00-open-source-lessons.json",
                "00-open-source-lessons.md",
                "00-research-plan.json",
                "00-research-plan.md",
                "01-literature.json",
                "01-literature.md",
                "01-literature-rerank.json",
                "01-literature-rerank.md",
                "01-literature-search-strategy.json",
                "01-literature-search-strategy.md",
                "01-literature-source-health.json",
                "01-literature-source-health.md",
                "01-query-execution-audit.json",
                "01-query-execution-audit.md",
                "01-literature-snowball.json",
                "01-literature-snowball.md",
                "01-literature-coverage.json",
                "01-literature-coverage.md",
                "01-literature-evidence-mix.json",
                "01-literature-evidence-mix.md",
                "01-literature-rescue-plan.json",
                "01-literature-rescue-plan.md",
                "01-literature-rescue-execution.json",
                "01-literature-rescue-execution.md",
                "01-literature-search-feedback.json",
                "01-literature-search-feedback.md",
                "01-seed-paper-intake.json",
                "01-seed-paper-intake.md",
                "01-literature-gate-decision.json",
                "01-literature-gate-decision.md",
                "01-literature-quality.json",
                "01-literature-quality.md",
                "01-literature-curated.json",
                "01-literature-curated.md",
                "01-literature-metadata-audit.json",
                "01-literature-metadata-audit.md",
                "01-fulltext-corpus.json",
                "01-fulltext-corpus.md",
                "01-context.json",
                "01-context.md",
                "01-review-gate.md",
                "01-citation-audit.json",
                "01-citation-audit.md",
                "approval.json",
                "01-review-feedback.json",
                "01-review-feedback.md",
                "01-review-constraints.json",
                "01-review-constraints.md",
                "01-references.bib",
                "01-references.ris",
                "02-research-gap-map.json",
                "02-research-gap-map.md",
                "02-agent-team.json",
                "02-agent-team.md",
                "02-ideas.json",
                "02-ideas.md",
                "02-novelty-audit.json",
                "02-novelty-audit.md",
                "02-idea-audit.json",
                "02-idea-audit.md",
                "02-exploration-map.json",
                "02-exploration-map.md",
                "02-exploration-map.svg",
                "02-experiment-manager.json",
                "02-experiment-manager.md",
                "03-experiment-plan.md",
                "03-experiment-plan.json",
                "03-agent-handoff-audit.md",
                "03-agent-handoff-audit.json",
                "03-review-constraint-compliance.md",
                "03-review-constraint-compliance.json",
                "03-experiment-audit.md",
                "03-experiment-audit.json",
                "03-idea-experiment-contract.md",
                "03-idea-experiment-contract.json",
                "03-execution-safety-audit.md",
                "03-execution-safety-audit.json",
                "03-ablation-plan.md",
                "03-ablation-plan.json",
                "03-preregistration.md",
                "03-preregistration.json",
                "03-benchmark-plan.json",
                "03-benchmark-plan.md",
                "03-benchmark-readiness.json",
                "03-benchmark-readiness.md",
                "04-results.json",
                "04-results.csv",
                "04-experiment-runbook.json",
                "04-experiment-runbook.md",
                "04-environment-snapshot.json",
                "04-environment-snapshot.md",
                "04-statistics.json",
                "04-statistics.md",
                "04-result-validation.json",
                "04-result-validation.md",
                "04-failure-analysis.json",
                "04-failure-analysis.md",
                "04-benchmark-result-schema-audit.json",
                "04-benchmark-result-schema-audit.md",
                "04-benchmark-evidence-audit.json",
                "04-benchmark-evidence-audit.md",
                "04-experiment-decision.json",
                "04-experiment-decision.md",
                "04-hypothesis-outcome.json",
                "04-hypothesis-outcome.md",
                "04-claim-boundary-preflight.json",
                "04-claim-boundary-preflight.md",
                "04-statistics-figure.json",
                "04-statistics-figure.svg",
                "05-analysis.json",
                "05-analysis.md",
                "06-paper.md",
                "06-paper.tex",
                "07-paper-review.json",
                "07-paper-review.md",
                "07-paper-review-calibration.json",
                "07-paper-review-calibration.md",
                "08-revision-plan.json",
                "08-revision-plan.md",
                "09-revised-paper.md",
                "09-revised-paper.tex",
                "09-revision-report.json",
                "09-revision-report.md",
                "09-revision-response-audit.json",
                "09-revision-response-audit.md",
                "10-revised-paper-review.json",
                "10-revised-paper-review.md",
                "10-claim-traceability.json",
                "10-claim-traceability.md",
                "10-agent-claim-audit.json",
                "10-agent-claim-audit.md",
                "10-agent-deliberation.json",
                "10-agent-deliberation.md",
                "10-citation-grounding.json",
                "10-citation-grounding.md",
                "10-citation-coverage.json",
                "10-citation-coverage.md",
                "10-results-presentation.json",
                "10-results-presentation.md",
                "10-claim-consistency.json",
                "10-claim-consistency.md",
                "10-release-metadata.json",
                "10-release-metadata.md",
                "10-code-data-availability.json",
                "10-code-data-availability.md",
                "10-ai-disclosure.json",
                "10-ai-disclosure.md",
                "10-submission-check.json",
                "10-submission-check.md",
                "10-final-readiness.json",
                "10-final-readiness.md",
                "11-submission-package.json",
                "11-submission-package.md",
                "11-submission-package.zip",
                "12-next-iteration-plan.json",
                "12-next-iteration-plan.md",
                "12-repair-queue.json",
                "12-repair-queue.md",
                "12-repair-resolution-audit.json",
                "12-repair-resolution-audit.md",
                "13-agent-stage-contract.json",
                "13-agent-stage-contract.md",
                "13-agent-trajectory.json",
                "13-agent-trajectory.md",
                "13-llm-trace-audit.json",
                "13-llm-trace-audit.md",
                "13-run-economics-audit.json",
                "13-run-economics-audit.md",
                "13-agent-observability-audit.json",
                "13-agent-observability-audit.md",
                "13-llm-observability-summary.json",
                "13-llm-observability-summary.md",
                "13-open-source-compliance.json",
                "13-open-source-compliance.md",
                "13-research-scorecard.json",
                "13-research-scorecard.md",
                "14-run-integrity-audit.json",
                "14-run-integrity-audit.md",
                "state.json",
            ]
            for filename in expected:
                self.assertTrue((out / filename).exists(), filename)
            approval = json.loads((out / "approval.json").read_text(encoding="utf-8"))
            self.assertTrue(approval["approved"])
            self.assertEqual(approval["reviewer"], "test")
            self.assertIn("idea_generation", approval["blocks"])
            self.assertIn("completed", (out / "state.json").read_text(encoding="utf-8"))
            manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(any(event["stage"] == "literature_review" for event in manifest["events"]))
            self.assertTrue(any(event["stage"] == "experiments" for event in manifest["events"]))
            self.assertTrue(any(item["path"] == "06-paper.md" for item in manifest["artifacts"]))
            llm_ledger = json.loads((out / "run-llm-ledger.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(llm_ledger["total_calls"], 1)
            self.assertEqual(llm_ledger["failed_calls"], 0)
            self.assertIn("研究计划", (out / "00-research-plan.md").read_text(encoding="utf-8"))
            self.assertIn("Prior Run Lessons", (out / "00-prior-run-lessons.md").read_text(encoding="utf-8"))
            self.assertIn("Prior Run Library", (out / "00-prior-run-library.md").read_text(encoding="utf-8"))
            self.assertIn("Open-Source Project Lessons", (out / "00-open-source-lessons.md").read_text(encoding="utf-8"))
            self.assertIn("预检报告", (out / "00-preflight.md").read_text(encoding="utf-8"))
            self.assertIn("文献候选重排", (out / "01-literature-rerank.md").read_text(encoding="utf-8"))
            self.assertIn("文献检索策略", (out / "01-literature-search-strategy.md").read_text(encoding="utf-8"))
            self.assertIn("文献源健康", (out / "01-literature-source-health.md").read_text(encoding="utf-8"))
            self.assertIn("Query Execution Audit", (out / "01-query-execution-audit.md").read_text(encoding="utf-8"))
            self.assertIn("文献滚雪球计划", (out / "01-literature-snowball.md").read_text(encoding="utf-8"))
            self.assertIn("文献覆盖审计", (out / "01-literature-coverage.md").read_text(encoding="utf-8"))
            self.assertIn("文献证据组合审计", (out / "01-literature-evidence-mix.md").read_text(encoding="utf-8"))
            self.assertIn("文献补检索计划", (out / "01-literature-rescue-plan.md").read_text(encoding="utf-8"))
            self.assertIn("文献检索反馈策略", (out / "01-literature-search-feedback.md").read_text(encoding="utf-8"))
            self.assertIn("Seed Paper Intake", (out / "01-seed-paper-intake.md").read_text(encoding="utf-8"))
            self.assertIn("质量筛选", (out / "01-literature-quality.md").read_text(encoding="utf-8"))
            self.assertIn("文献 Metadata 审计", (out / "01-literature-metadata-audit.md").read_text(encoding="utf-8"))
            self.assertIn("全文语料", (out / "01-fulltext-corpus.md").read_text(encoding="utf-8"))
            self.assertIn("引用审计", (out / "01-citation-audit.md").read_text(encoding="utf-8"))
            self.assertIn("引用完整性", (out / "01-citation-audit.md").read_text(encoding="utf-8"))
            self.assertIn("审核约束", (out / "01-review-constraints.md").read_text(encoding="utf-8"))
            self.assertIn("文献依据", (out / "02-ideas.md").read_text(encoding="utf-8"))
            self.assertIn("Idea 新颖性审计", (out / "02-novelty-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Idea 证据与约束审计", (out / "02-idea-audit.md").read_text(encoding="utf-8"))
            self.assertIn("研究分支探索图", (out / "02-exploration-map.md").read_text(encoding="utf-8"))
            self.assertIn("<svg", (out / "02-exploration-map.svg").read_text(encoding="utf-8"))
            self.assertIn("Experiment Manager", (out / "02-experiment-manager.md").read_text(encoding="utf-8"))
            self.assertIn("Baseline", (out / "03-experiment-plan.md").read_text(encoding="utf-8"))
            self.assertIn("人工审核约束落实审计", (out / "03-review-constraint-compliance.md").read_text(encoding="utf-8"))
            self.assertIn("实验计划审计", (out / "03-experiment-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Idea-实验契约", (out / "03-idea-experiment-contract.md").read_text(encoding="utf-8"))
            self.assertIn("实验执行安全审计", (out / "03-execution-safety-audit.md").read_text(encoding="utf-8"))
            self.assertIn("消融计划", (out / "03-ablation-plan.md").read_text(encoding="utf-8"))
            self.assertIn("实验预注册", (out / "03-preregistration.md").read_text(encoding="utf-8"))
            self.assertIn("Benchmark 接入计划", (out / "03-benchmark-plan.md").read_text(encoding="utf-8"))
            self.assertIn("Benchmark Readiness Audit", (out / "03-benchmark-readiness.md").read_text(encoding="utf-8"))
            self.assertIn("95% CI", (out / "04-statistics.md").read_text(encoding="utf-8"))
            self.assertIn("实验结果有效性验证", (out / "04-result-validation.md").read_text(encoding="utf-8"))
            self.assertIn("失败/负结果分析", (out / "04-failure-analysis.md").read_text(encoding="utf-8"))
            self.assertIn("Benchmark Result Schema Audit", (out / "04-benchmark-result-schema-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Benchmark 证据审计", (out / "04-benchmark-evidence-audit.md").read_text(encoding="utf-8"))
            self.assertIn("实验后决策", (out / "04-experiment-decision.md").read_text(encoding="utf-8"))
            self.assertIn("假设结果审计", (out / "04-hypothesis-outcome.md").read_text(encoding="utf-8"))
            self.assertIn("Claim Boundary Preflight", (out / "04-claim-boundary-preflight.md").read_text(encoding="utf-8"))
            self.assertIn("<svg", (out / "04-statistics-figure.svg").read_text(encoding="utf-8"))
            self.assertIn("实验运行手册", (out / "04-experiment-runbook.md").read_text(encoding="utf-8"))
            self.assertIn("实验环境快照", (out / "04-environment-snapshot.md").read_text(encoding="utf-8"))
            self.assertIn("可复现实验草稿", (out / "06-paper.md").read_text(encoding="utf-8"))
            self.assertIn("Claim-Grounding", (out / "07-paper-review.md").read_text(encoding="utf-8"))
            self.assertIn("修订任务", (out / "08-revision-plan.md").read_text(encoding="utf-8"))
            self.assertIn("修订执行记录", (out / "09-revised-paper.md").read_text(encoding="utf-8"))
            self.assertIn("任务处理", (out / "09-revision-report.md").read_text(encoding="utf-8"))
            self.assertIn("Revision Response Audit", (out / "09-revision-response-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Claim-Grounding", (out / "10-revised-paper-review.md").read_text(encoding="utf-8"))
            self.assertIn("Claim Traceability", (out / "10-claim-traceability.md").read_text(encoding="utf-8"))
            self.assertIn("多智能体 Claim 审计", (out / "10-agent-claim-audit.md").read_text(encoding="utf-8"))
            self.assertIn("角色规则审计（非独立 Agent）", (out / "10-agent-deliberation.md").read_text(encoding="utf-8"))
            self.assertIn("Citation Grounding", (out / "10-citation-grounding.md").read_text(encoding="utf-8"))
            self.assertIn("Citation Coverage Audit", (out / "10-citation-coverage.md").read_text(encoding="utf-8"))
            self.assertIn("Results Presentation Audit", (out / "10-results-presentation.md").read_text(encoding="utf-8"))
            self.assertIn("Claim Consistency Audit", (out / "10-claim-consistency.md").read_text(encoding="utf-8"))
            self.assertIn("Release Metadata", (out / "10-release-metadata.md").read_text(encoding="utf-8"))
            self.assertIn("代码和数据可用性审计", (out / "10-code-data-availability.md").read_text(encoding="utf-8"))
            self.assertIn("投稿格式检查", (out / "10-submission-check.md").read_text(encoding="utf-8"))
            self.assertIn("AI 使用披露", (out / "10-ai-disclosure.md").read_text(encoding="utf-8"))
            self.assertIn("最终就绪报告", (out / "10-final-readiness.md").read_text(encoding="utf-8"))
            self.assertIn("投稿/归档包", (out / "11-submission-package.md").read_text(encoding="utf-8"))
            self.assertIn("下一轮迭代计划", (out / "12-next-iteration-plan.md").read_text(encoding="utf-8"))
            self.assertIn("修复队列", (out / "12-repair-queue.md").read_text(encoding="utf-8"))
            self.assertIn("修复闭环审计", (out / "12-repair-resolution-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Agent Stage Contract Audit", (out / "13-agent-stage-contract.md").read_text(encoding="utf-8"))
            self.assertIn("Agent Trajectory", (out / "13-agent-trajectory.md").read_text(encoding="utf-8"))
            self.assertIn("LLM Trace Audit", (out / "13-llm-trace-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Run Economics Audit", (out / "13-run-economics-audit.md").read_text(encoding="utf-8"))
            self.assertIn("Agent Observability Audit", (out / "13-agent-observability-audit.md").read_text(encoding="utf-8"))
            self.assertIn("研究 Run 分数卡", (out / "13-research-scorecard.md").read_text(encoding="utf-8"))
            self.assertIn("Run Integrity Audit", (out / "14-run-integrity-audit.md").read_text(encoding="utf-8"))
            self.assertTrue((out / "submission-package" / "README.md").exists())
            self.assertTrue((out / "submission-package" / "CHECKLIST.md").exists())
            final_readiness = json.loads((out / "10-final-readiness.json").read_text(encoding="utf-8"))
            self.assertIn("availability_status", final_readiness)
            self.assertIn("submission_status", final_readiness)
            release = json.loads((out / "10-release-metadata.json").read_text(encoding="utf-8"))
            self.assertIn("status", release)
            claim_traceability = json.loads((out / "10-claim-traceability.json").read_text(encoding="utf-8"))
            self.assertIn("traceability_score", claim_traceability)
            agent_claim_audit = json.loads((out / "10-agent-claim-audit.json").read_text(encoding="utf-8"))
            self.assertIn("claim_owner_summary", agent_claim_audit)
            agent_deliberation = json.loads((out / "10-agent-deliberation.json").read_text(encoding="utf-8"))
            self.assertIn("consensus", agent_deliberation)
            citation_grounding = json.loads((out / "10-citation-grounding.json").read_text(encoding="utf-8"))
            self.assertIn("grounding_score", citation_grounding)
            citation_coverage = json.loads((out / "10-citation-coverage.json").read_text(encoding="utf-8"))
            self.assertIn("coverage_score", citation_coverage)
            results_presentation = json.loads((out / "10-results-presentation.json").read_text(encoding="utf-8"))
            self.assertIn("presentation_score", results_presentation)
            claim_consistency = json.loads((out / "10-claim-consistency.json").read_text(encoding="utf-8"))
            self.assertIn("consistency_score", claim_consistency)
            citation_audit = json.loads((out / "01-citation-audit.json").read_text(encoding="utf-8"))
            self.assertIn("integrity_status", citation_audit)
            self.assertIn("integrity_layers", citation_audit)
            package = json.loads((out / "11-submission-package.json").read_text(encoding="utf-8"))
            self.assertIn("package_zip", package)
            self.assertTrue(package["files"])
            iteration = json.loads((out / "12-next-iteration-plan.json").read_text(encoding="utf-8"))
            self.assertIn("decision", iteration)
            self.assertTrue(iteration["items"])
            repair_queue = json.loads((out / "12-repair-queue.json").read_text(encoding="utf-8"))
            self.assertIn("summary", repair_queue)
            self.assertTrue(repair_queue["items"])
            llm_trace_audit = json.loads((out / "13-llm-trace-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(llm_trace_audit["status"], "block")
            self.assertTrue(llm_trace_audit["blocking_issues"])
            self.assertEqual(llm_trace_audit["coverage"]["coverage_ratio"], 0.0)
            run_economics = json.loads((out / "13-run-economics-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(run_economics["status"], "pass")
            self.assertGreater(run_economics["summary"]["input_tokens_estimated"], 0)
            observability = json.loads((out / "13-agent-observability-audit.json").read_text(encoding="utf-8"))
            self.assertIn(observability["status"], {"pass", "review_required"})
            scorecard = json.loads((out / "13-research-scorecard.json").read_text(encoding="utf-8"))
            self.assertIn("overall_score", scorecard)
            self.assertTrue(scorecard["dimensions"])
            self.assertTrue(any("run_integrity=" in "；".join(item.get("evidence", [])) for item in scorecard["dimensions"] if item.get("category") == "submission_readiness"))
            integrity = json.loads((out / "14-run-integrity-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(integrity["status"], "block")
            self.assertTrue(integrity["blocking_issues"])
            handoff = json.loads((out / "14-final-handoff.json").read_text(encoding="utf-8"))
            self.assertIn(handoff["status"], {"blocked", "ready_for_human_handoff", "ready_for_submission_upload"})
            self.assertIn("package_has_integrity_audit", handoff)
            if handoff["status"] == "blocked":
                self.assertTrue(handoff["blocking_issues"])
            trajectory = json.loads((out / "13-agent-trajectory.json").read_text(encoding="utf-8"))
            self.assertEqual(trajectory["summary"]["last_event"], "completed")
            trajectory_stages = {item.get("stage") for item in trajectory.get("timeline", [])}
            self.assertIn("final_handoff", trajectory_stages)
            self.assertIn("completed", trajectory_stages)
            manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item.get("stage") == "research_scorecard_integrity_refresh" for item in manifest.get("events", [])))
            self.assertTrue(any(item.get("stage") == "final_handoff" for item in manifest.get("events", [])))
            self.assertTrue(any(item.get("stage") == "agent_trajectory_final_refresh" for item in manifest.get("events", [])))
            environment = json.loads((out / "04-environment-snapshot.json").read_text(encoding="utf-8"))
            self.assertTrue(environment["source_tree"]["aggregate_sha256"])
            hypothesis_outcome = json.loads((out / "04-hypothesis-outcome.json").read_text(encoding="utf-8"))
            self.assertIn("outcome", hypothesis_outcome)
            open_source_lessons = json.loads((out / "00-open-source-lessons.json").read_text(encoding="utf-8"))
            self.assertIn("agent_prompt_text", open_source_lessons)
            exploration = json.loads((out / "02-exploration-map.json").read_text(encoding="utf-8"))
            plan = json.loads((out / "03-experiment-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["idea_title"], exploration["selected_idea_title"])
            preregistration = json.loads((out / "03-preregistration.json").read_text(encoding="utf-8"))
            self.assertEqual(preregistration["status"], "locked")
            results = json.loads((out / "04-results.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(results), 10)

    def test_pipeline_merges_configured_fulltext_into_context(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            fulltext = root / "paper.txt"
            fulltext.write_text(
                "Auditable research agents need claim grounding, local fulltext chunks, and reproducible experiment artifacts.",
                encoding="utf-8",
            )
            out = root / "run"
            config = AgentConfig(literature=LiteratureConfig(fulltext_paths=[str(fulltext)]))
            with patch.dict("os.environ", {"RESEARCH_AGENT_FULLTEXT_ROOTS": str(root)}):
                _run_pipeline_with_noop_llm("auditable autonomous research agents", out, config)

            context = json.loads((out / "01-context.json").read_text(encoding="utf-8"))
            corpus = json.loads((out / "01-fulltext-corpus.json").read_text(encoding="utf-8"))

            self.assertEqual(corpus["total_chunks"], 1)
            self.assertTrue(any(chunk["source"] == "local_fulltext" for chunk in context["chunks"]))
            self.assertTrue(any(citation["source"] == "local_fulltext" for citation in context["citations"]))

    def test_local_pipeline_reads_metrics_from_generated_script(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            config = AgentConfig(execution=ExecutionConfig(mode="local", allowed_commands=["python3"]))
            _run_pipeline_with_noop_llm("auditable autonomous research agents", out, config)
            results = (out / "04-results.json").read_text(encoding="utf-8")
            self.assertIn('"status": "passed"', results)
            self.assertIn('"artifact_completeness": 0.9', results)
            execution_approval = json.loads((out / "03-execution-approval.json").read_text(encoding="utf-8"))
            self.assertTrue(execution_approval["approved"])
            self.assertEqual(execution_approval["execution_mode"], "local")
            self.assertTrue((out / "03-execution-approval.md").exists())
            self.assertTrue((out / "experiments" / "simulate.py").exists())
            runbook = json.loads((out / "04-experiment-runbook.json").read_text(encoding="utf-8"))
            self.assertEqual(runbook["execution"]["mode"], "local")
            self.assertTrue(runbook["environment"]["source_tree"]["aggregate_sha256"])
            self.assertTrue(any(item["path"] == "experiments/artifact_metrics.json" and len(item["sha256"]) == 64 for item in runbook["artifacts"]))
            self.assertTrue(any(item["path"] == "experiments/ablation_metrics.json" and len(item["sha256"]) == 64 for item in runbook["artifacts"]))

    def test_pipeline_can_resume_after_review_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            config = AgentConfig(execution=ExecutionConfig(repeats=2))
            _prepare_run_at_review_gate("机械臂路径规划", out, config)
            self.assertFalse((out / "02-ideas.json").exists())
            pipeline_module.approve_review_gate(out, reviewer="resume-test", notes="人工确认文献风险，允许 resume 测试继续")
            original = pipeline_module.build_llm
            pipeline_module.build_llm = lambda _: NoopLLM()
            try:
                pipeline_module.resume_pipeline_after_review_approval("机械臂路径规划", out, config)
            finally:
                pipeline_module.build_llm = original

            self.assertIn("completed", (out / "state.json").read_text(encoding="utf-8"))
            self.assertTrue((out / "02-ideas.json").exists())
            self.assertTrue((out / "02-idea-audit.md").exists())
            self.assertTrue((out / "02-exploration-map.md").exists())
            self.assertTrue((out / "07-paper-review.md").exists())
            self.assertTrue((out / "08-revision-plan.md").exists())
            self.assertTrue((out / "09-revised-paper.md").exists())
            self.assertTrue((out / "10-claim-traceability.md").exists())
            self.assertTrue((out / "10-agent-claim-audit.md").exists())
            self.assertTrue((out / "10-agent-deliberation.md").exists())
            self.assertTrue((out / "10-citation-grounding.md").exists())
            self.assertTrue((out / "10-results-presentation.md").exists())
            self.assertTrue((out / "10-final-readiness.md").exists())
            self.assertTrue((out / "10-release-metadata.md").exists())
            self.assertTrue((out / "10-code-data-availability.md").exists())
            self.assertTrue((out / "10-submission-check.md").exists())
            self.assertTrue((out / "11-submission-package.md").exists())
            self.assertTrue((out / "12-next-iteration-plan.md").exists())
            self.assertTrue((out / "12-repair-queue.md").exists())
            self.assertTrue((out / "12-repair-resolution-audit.md").exists())
            self.assertTrue((out / "13-research-scorecard.md").exists())
            self.assertTrue((out / "14-run-integrity-audit.md").exists())
            self.assertTrue((out / "03-experiment-audit.md").exists())
            self.assertTrue((out / "03-idea-experiment-contract.md").exists())
            self.assertTrue((out / "03-ablation-plan.md").exists())
            self.assertTrue((out / "03-preregistration.md").exists())
            self.assertTrue((out / "04-hypothesis-outcome.md").exists())
            self.assertTrue((out / "04-claim-boundary-preflight.md").exists())
            self.assertIn("RRT", (out / "03-experiment-plan.md").read_text(encoding="utf-8"))

    def test_review_feedback_guides_downstream_fallback_planning(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            config = AgentConfig(execution=ExecutionConfig(repeats=1))
            _prepare_run_at_review_gate("机械臂路径规划", out, config)
            notes = "必须比较 RRT* 并补人工种子文献"
            pipeline_module.approve_review_gate(out, reviewer="feedback-test", notes=notes)
            original = pipeline_module.build_llm
            pipeline_module.build_llm = lambda _: NoopLLM()
            try:
                pipeline_module.resume_pipeline_after_review_approval("机械臂路径规划", out, config)
            finally:
                pipeline_module.build_llm = original

            feedback_md = (out / "01-review-feedback.md").read_text(encoding="utf-8")
            feedback_json = json.loads((out / "01-review-feedback.json").read_text(encoding="utf-8"))
            constraints_md = (out / "01-review-constraints.md").read_text(encoding="utf-8")
            constraints_json = json.loads((out / "01-review-constraints.json").read_text(encoding="utf-8"))
            ideas_md = (out / "02-ideas.md").read_text(encoding="utf-8")
            plan_md = (out / "03-experiment-plan.md").read_text(encoding="utf-8")
            self.assertIn(notes, feedback_md)
            self.assertIn(notes, feedback_json["text"])
            self.assertEqual(constraints_json["constraints"][0]["category"], "baseline")
            self.assertIn("结构化审核约束", constraints_json["agent_text"])
            self.assertIn("审核约束", constraints_md)
            self.assertIn("落实人工审核意见", ideas_md)
            self.assertIn("必须比较 RRT*", ideas_md)
            self.assertIn("补人工种子文献", ideas_md)
            self.assertIn("结构化审核约束", ideas_md)
            self.assertIn("落实人工审核意见", plan_md)
            self.assertIn("已纳入人工审核反馈", plan_md)
            self.assertIn("结构化审核约束", plan_md)
            self.assertIn("补人工种子文献", plan_md)

    def test_review_revision_approval_refreshes_literature_before_downstream(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            topic = "robot manipulator path planning"
            seed_entry = "Closed-loop robot manipulator path planning seed 2026 https://example.org/repair-seed"
            _prepare_run_at_review_gate(topic, out, AgentConfig())
            before_context = json.loads((out / "01-context.json").read_text(encoding="utf-8"))
            self.assertFalse(any("Closed-loop robot manipulator" in item["title"] for item in before_context["citations"]))
            write_json(out / "02-ideas.json", [{"title": "stale idea from old context"}])
            write_text(out / "02-ideas.md", "# stale ideas")

            pipeline_module.request_review_revision(out, reviewer="reviewer", notes="补人工 seed 文献")
            pipeline_module.approve_review_gate(out, reviewer="reviewer", notes="已补入 URL seed 并人工核对文献风险")

            captured: dict[str, Any] = {}
            original_build_llm = pipeline_module.build_llm
            original_after = pipeline_module._run_after_review_approval

            def fake_after(run_topic, run_out, run_config, run_llm, research_plan, review, context, manifest, **kwargs):
                captured["review_titles"] = [paper.title for paper in review.papers]
                captured["context_titles"] = [citation.title for citation in context.citations]
                captured["resume"] = kwargs.get("resume")
                pipeline_module._write_state(run_out, run_topic, "completed")

            pipeline_module.build_llm = lambda _: NoopLLM()
            pipeline_module._run_after_review_approval = fake_after
            errors: list[BaseException] = []

            def resume_worker() -> None:
                try:
                    pipeline_module.resume_pipeline_after_review_approval(
                        topic,
                        out,
                        AgentConfig(literature=LiteratureConfig(seed_papers=[seed_entry])),
                    )
                except BaseException as exc:  # pragma: no cover - surfaced below
                    errors.append(exc)

            thread = Thread(target=resume_worker, daemon=True)
            try:
                thread.start()
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    approval = json.loads((out / "approval.json").read_text(encoding="utf-8"))
                    if approval.get("revision_repair", {}).get("status") == "reapproval_required":
                        break
                    time.sleep(0.05)
                else:
                    self.fail("Timed out waiting for refreshed review approval")
                pipeline_module.approve_review_gate(out, reviewer="reviewer", notes="已复核刷新后的文献池、context 和 review gate")
                thread.join(timeout=15)
                self.assertFalse(thread.is_alive())
                if errors:
                    raise errors[0]
            finally:
                pipeline_module.build_llm = original_build_llm
                pipeline_module._run_after_review_approval = original_after

            approval = json.loads((out / "approval.json").read_text(encoding="utf-8"))
            seed_intake = json.loads((out / "01-seed-paper-intake.json").read_text(encoding="utf-8"))
            repaired_context = json.loads((out / "01-context.json").read_text(encoding="utf-8"))
            history_actions = [item["action"] for item in approval["history"]]

            self.assertIn("revision_repaired_at", approval)
            self.assertEqual(approval["revision_repair"]["status"], "approved")
            self.assertIn("revision_repaired", history_actions)
            self.assertEqual(seed_intake["total_seed_entries"], 1)
            self.assertEqual(seed_intake["curated_seed_papers"], 1)
            self.assertFalse(captured["resume"])
            self.assertTrue(any("Closed-loop robot manipulator" in title for title in captured["review_titles"]))
            self.assertTrue(any("Closed-loop robot manipulator" in title for title in captured["context_titles"]))
            self.assertTrue(any("Closed-loop robot manipulator" in item["title"] for item in repaired_context["citations"]))

    def test_review_gate_wait_can_be_cancelled(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            pipeline_module._write_state(out, "机械臂路径规划", "awaiting_review_approval")
            pipeline_module.request_cancel(out, requester="test", reason="unit_test")

            with self.assertRaises(pipeline_module.PipelineCancelled):
                pipeline_module.wait_for_review_approval(out, poll_seconds=0.01, topic="机械臂路径规划")

            state = json.loads((out / "state.json").read_text(encoding="utf-8"))
            cancel = json.loads((out / "cancel.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "cancelled")
            self.assertTrue(cancel["requested"])
            self.assertTrue(cancel["cancelled"])
            self.assertEqual(cancel["requester"], "test")

    def test_review_gate_wait_can_request_revision(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            pipeline_module._write_state(out, "机械臂路径规划", "awaiting_review_approval")
            write_json(out / "approval.json", {"topic": "机械臂路径规划", "approved": False, "stage": "awaiting_review_approval"})
            pipeline_module.request_review_revision(out, reviewer="test", notes="补充 RRT* 文献")

            with self.assertRaises(pipeline_module.PipelineReviewRevisionRequested):
                pipeline_module.wait_for_review_approval(out, poll_seconds=0.01, topic="机械臂路径规划")

            state = json.loads((out / "state.json").read_text(encoding="utf-8"))
            approval = json.loads((out / "approval.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "review_revision_requested")
            self.assertFalse(approval["approved"])
            self.assertTrue(approval["revision_requested"])
            self.assertEqual(approval["notes"], "补充 RRT* 文献")
            self.assertEqual(approval["history"][0]["action"], "revision_requested")
            self.assertTrue((out / "01-review-revision-plan.json").exists())
            self.assertTrue((out / "01-review-revision-plan.md").exists())
            revision_plan = json.loads((out / "01-review-revision-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(revision_plan["notes"], "补充 RRT* 文献")
            self.assertIn("Review Revision Plan", (out / "01-review-revision-plan.md").read_text(encoding="utf-8"))

    def test_pending_review_approval_refreshes_gate_audit_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            context = LiteratureContext(
                topic="机械臂路径规划",
                citations=[],
                chunks=[],
                claim_support=[],
                review_gate=ReviewGate(status="review_required", warnings=["old warning"], required_actions=["old action"]),
            )
            pipeline_module.request_review_approval(out, "机械臂路径规划", context)
            refreshed = LiteratureContext(
                topic="机械臂路径规划",
                citations=[],
                chunks=[],
                claim_support=[],
                review_gate=ReviewGate(status="literature_repair_required", warnings=["new warning"], required_actions=["new action"]),
            )

            approval = pipeline_module.refresh_pending_review_approval(out, refreshed)
            saved = json.loads((out / "approval.json").read_text(encoding="utf-8"))

            self.assertEqual(approval["gate_status"], "literature_repair_required")
            self.assertEqual(saved["warnings"], ["new warning"])
            self.assertEqual(saved["required_actions"], ["new action"])
            self.assertTrue(saved["approval_policy"]["notes_required"])

    def test_review_gate_requires_notes_for_non_pass_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(
                out / "approval.json",
                {
                    "topic": "机械臂路径规划",
                    "approved": False,
                    "revision_requested": False,
                    "stage": "awaiting_review_approval",
                    "gate_status": "literature_repair_required",
                    "warnings": ["核心文献不足"],
                },
            )

            with self.assertRaises(RuntimeError):
                pipeline_module.approve_review_gate(out, reviewer="reviewer", notes="")

            approval = json.loads((out / "approval.json").read_text(encoding="utf-8"))
            approval["approved"] = True
            approval["notes"] = ""
            write_json(out / "approval.json", approval)

            self.assertFalse(pipeline_module._approval_granted(out / "approval.json"))

            approved = pipeline_module.approve_review_gate(out, reviewer="reviewer", notes="已人工补充核心文献并接受剩余风险")

            self.assertTrue(approved["approved"])
            self.assertTrue(approved["approval_policy"]["notes_required"])
            self.assertTrue(pipeline_module._approval_granted(out / "approval.json"))

    def test_pass_review_gate_can_approve_without_notes(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(
                out / "approval.json",
                {
                    "topic": "机械臂路径规划",
                    "approved": False,
                    "revision_requested": False,
                    "stage": "awaiting_review_approval",
                    "gate_status": "pass",
                    "warnings": [],
                },
            )

            approved = pipeline_module.approve_review_gate(out, reviewer="reviewer")

            self.assertTrue(approved["approved"])
            self.assertFalse(approved["approval_policy"]["notes_required"])
            self.assertTrue(pipeline_module._approval_granted(out / "approval.json"))

    def test_review_approval_rejects_inputs_changed_after_request(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            config = AgentConfig()
            _prepare_run_at_review_gate("机械臂路径规划", out, config)
            context = json.loads((out / "01-context.json").read_text(encoding="utf-8"))
            context["topic"] = "请求后被修改的 context"
            write_json(out / "01-context.json", context)

            with self.assertRaisesRegex(RuntimeError, "changed after approval was requested"):
                pipeline_module.approve_review_gate(out, reviewer="reviewer", notes="已人工核对文献风险并确认继续")

            refreshed = json.loads((out / "approval.json").read_text(encoding="utf-8"))
            self.assertFalse(refreshed["approved"])
            self.assertTrue(refreshed["stale_previous_approval"])
            self.assertEqual(refreshed["history"][-1]["action"], "approval_request_refreshed")
            approved = pipeline_module.approve_review_gate(out, reviewer="reviewer", notes="已重新核对刷新后的 context 与文献风险")
            self.assertTrue(approved["approved"])
            self.assertTrue(pipeline_module._approval_granted(out / "approval.json"))

    def test_execution_approval_rejects_changed_benchmark_source_and_tampering(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp).resolve()
            out = root / "run"
            out.mkdir()
            script = root / "run_benchmark.py"
            script.write_text("print('v1')\n", encoding="utf-8")
            manifest = root / "manifest.json"
            write_json(
                manifest,
                {
                    "name": "approval adapter",
                    "command": ["python3", script.name],
                    "source_files": [script.name],
                    "metrics_path": "metrics.json",
                    "expected_artifacts": ["metrics.json"],
                },
            )
            config = ExecutionConfig(
                mode="benchmark",
                allowed_commands=["python3"],
                repeats=1,
                benchmark_manifest_paths=[str(manifest.relative_to(Path.cwd()))],
            )
            plan = ExperimentPlan("approval", "audit", ["adapter"], ["score"], ["run"], [])
            write_json(out / "03-experiment-plan.json", plan)
            safety = pipeline_module.write_execution_safety_audit_artifacts(plan, config, out)
            pipeline_module.request_execution_approval(out, "approval", plan, safety, "benchmark")

            script.write_text("print('v2')\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Execution inputs changed"):
                pipeline_module.approve_execution_gate(out, reviewer="reviewer", notes="已核对命令、安全审计和 benchmark source")
            self.assertFalse(pipeline_module._execution_approval_granted(out))

            safety = pipeline_module.write_execution_safety_audit_artifacts(plan, config, out)
            pipeline_module.request_execution_approval(out, "approval", plan, safety, "benchmark")
            pipeline_module.approve_execution_gate(out, reviewer="reviewer", notes="已重新核对命令、安全审计和 benchmark source")
            self.assertTrue(pipeline_module._execution_approval_granted(out))

            approval = json.loads((out / "03-execution-approval.json").read_text(encoding="utf-8"))
            approval["execution_binding"]["source_artifacts"] = []
            write_json(out / "03-execution-approval.json", approval)
            self.assertFalse(pipeline_module._execution_approval_granted(out))

    def test_checkpoint_contract_tracks_benchmark_source_split_and_grader(self) -> None:
        with TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp).resolve()
            out = root / "run"
            out.mkdir()
            script = root / "run.py"
            split = root / "split.json"
            grader = root / "grader.py"
            script.write_text("print('v1')\n", encoding="utf-8")
            split.write_text('{"ids":[1]}\n', encoding="utf-8")
            grader.write_text("print('grade')\n", encoding="utf-8")
            manifest = root / "manifest.json"
            write_json(
                manifest,
                {
                    "name": "checkpoint adapter",
                    "command": ["python3", script.name],
                    "source_files": [script.name],
                    "metrics_path": "metrics.json",
                    "expected_artifacts": ["metrics.json"],
                    "split_path": split.name,
                    "grader_path": grader.name,
                },
            )
            config = AgentConfig(
                execution=ExecutionConfig(
                    mode="benchmark",
                    benchmark_manifest_paths=[str(manifest.relative_to(Path.cwd()))],
                )
            )

            contract = pipeline_module._validate_or_create_checkpoint_contract(out, "checkpoint", config)
            recorded = {item["resolved_path"] for item in contract["configured_inputs"]}
            self.assertGreaterEqual(recorded, {str(manifest), str(script), str(split), str(grader)})
            script.write_text("print('v2')\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "fingerprint changed"):
                pipeline_module._validate_or_create_checkpoint_contract(out, "checkpoint", config)

    def test_legacy_checkpoint_without_config_or_contract_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "02-ideas.json", [{"title": "unbound legacy artifact"}])

            with self.assertRaisesRegex(RuntimeError, "Legacy checkpoint artifacts"):
                pipeline_module._validate_or_create_checkpoint_contract(out, "legacy", AgentConfig())

            self.assertFalse((out / "run-checkpoint-contract.json").exists())

    def test_resume_from_checkpoint_reuses_existing_ideas(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            config = AgentConfig(execution=ExecutionConfig(repeats=1))
            _prepare_run_at_review_gate("机械臂路径规划", out, config)
            pipeline_module.approve_review_gate(out, reviewer="checkpoint-test", notes="人工确认文献风险，允许 checkpoint 测试继续")
            context = json.loads((out / "01-context.json").read_text(encoding="utf-8"))
            stomp_key = next(item["key"] for item in context["citations"] if "STOMP" in item["title"])
            idea = ResearchIdea(
                title="checkpoint idea",
                hypothesis="复用已有 idea 后继续实验计划。",
                mechanism="读取 02-ideas.json 作为检查点。",
                expected_contribution="避免失败后重跑前序阶段。",
                novelty=7,
                feasibility=8,
                risk=2,
                evaluation=["planning_success_rate", "planning_time"],
                evidence_keys=[stomp_key],
                baseline="RRT*",
                experiment_sketch=["复用 idea", "生成实验计划", "运行统计"],
            )
            write_json(out / "02-ideas.json", [idea])
            write_text(out / "02-ideas.md", "# Ideas\n\n- checkpoint idea")
            pipeline_module._write_state(out, "机械臂路径规划", "ideation_completed")

            original = pipeline_module.build_llm
            pipeline_module.build_llm = lambda _: NoopLLM()
            errors: list[BaseException] = []

            def checkpoint_worker() -> None:
                try:
                    pipeline_module.resume_pipeline_from_checkpoint("机械臂路径规划", out, config)
                except BaseException as exc:  # pragma: no cover - surfaced below
                    errors.append(exc)

            thread = Thread(target=checkpoint_worker, daemon=True)
            try:
                thread.start()
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    approval = json.loads((out / "approval.json").read_text(encoding="utf-8"))
                    if approval.get("approved") is False and approval.get("stale_previous_approval"):
                        break
                    time.sleep(0.05)
                else:
                    self.fail("Timed out waiting for checkpoint review reapproval")
                pipeline_module.approve_review_gate(out, reviewer="checkpoint-test", notes="已复核 checkpoint 刷新后的 context 和 review gate")
                thread.join(timeout=15)
                self.assertFalse(thread.is_alive())
                if errors:
                    raise errors[0]
            finally:
                pipeline_module.build_llm = original

            self.assertEqual(json.loads((out / "02-ideas.json").read_text(encoding="utf-8"))[0]["title"], "checkpoint idea")
            self.assertIn("checkpoint idea", (out / "03-experiment-plan.md").read_text(encoding="utf-8"))
            self.assertTrue((out / "03-experiment-audit.json").exists())
            self.assertTrue((out / "03-idea-experiment-contract.json").exists())
            self.assertTrue((out / "03-ablation-plan.json").exists())
            self.assertTrue((out / "03-preregistration.json").exists())
            self.assertTrue((out / "02-exploration-map.json").exists())
            self.assertTrue((out / "12-repair-queue.json").exists())
            self.assertTrue((out / "12-repair-resolution-audit.json").exists())
            self.assertTrue((out / "13-research-scorecard.json").exists())
            self.assertTrue((out / "06-paper.md").exists())
            manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(any(event["stage"] == "ideation_checkpoint" for event in manifest["events"]))

    def test_claim_boundary_checkpoint_invalidates_when_experiment_evidence_changes(self) -> None:
        result_validation = {"status": "ok"}
        failure_analysis = {"status": "pass"}
        benchmark_evidence = {"status": "pass", "evidence_grade": "benchmark", "claim_policy": "benchmark_claims_allowed"}
        experiment_decision = {
            "decision": "continue_writing",
            "status": "pass",
            "paper_policy": "normal_paper",
            "downstream_writing_allowed": True,
        }
        hypothesis_outcome = {"outcome": "supported", "status": "pass"}
        checkpoint = {
            "evidence_summary": {
                "execution_mode": "benchmark",
                "validation_status": "ok",
                "failure_status": "pass",
                "benchmark_status": "pass",
                "benchmark_grade": "benchmark",
                "benchmark_claim_policy": "benchmark_claims_allowed",
                "experiment_decision": "continue_writing",
                "experiment_decision_status": "pass",
                "paper_policy": "normal_paper",
                "downstream_writing_allowed": True,
                "hypothesis_outcome": "supported",
                "hypothesis_status": "pass",
            }
        }

        self.assertTrue(
            pipeline_module._claim_boundary_preflight_checkpoint_matches(
                checkpoint,
                result_validation,
                failure_analysis,
                benchmark_evidence,
                experiment_decision,
                hypothesis_outcome,
                "benchmark",
            )
        )
        stale_validation = dict(result_validation, status="block")
        self.assertFalse(
            pipeline_module._claim_boundary_preflight_checkpoint_matches(
                checkpoint,
                stale_validation,
                failure_analysis,
                benchmark_evidence,
                experiment_decision,
                hypothesis_outcome,
                "benchmark",
            )
        )

    def test_paper_review_calibration_checkpoint_invalidates_when_outcome_changes(self) -> None:
        checkpoint = {
            "execution_mode": "benchmark",
            "experiment_decision": "continue_writing",
            "hypothesis_outcome": "supported",
        }
        experiment_decision = {"decision": "continue_writing"}
        hypothesis_outcome = {"outcome": "supported"}

        self.assertTrue(
            pipeline_module._paper_review_calibration_checkpoint_matches(
                checkpoint,
                experiment_decision,
                hypothesis_outcome,
                "benchmark",
            )
        )
        self.assertFalse(
            pipeline_module._paper_review_calibration_checkpoint_matches(
                checkpoint,
                experiment_decision,
                {"outcome": "blocked_unverified"},
                "benchmark",
            )
        )

    def test_experiment_manager_block_stops_before_experiment_plan_and_writes_repair_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            config = AgentConfig(execution=ExecutionConfig(repeats=1))
            _prepare_run_at_review_gate("机械臂路径规划", out, config)
            pipeline_module.approve_review_gate(out, reviewer="manager-test", notes="人工确认文献风险，允许测试 manager 阻断")
            idea = ResearchIdea(
                title="证据无效分支",
                hypothesis="使用不可核对证据的 idea 不应进入实验计划。",
                mechanism="manager 应在 ideation 后阻断。",
                expected_contribution="验证人工修复门禁。",
                novelty=8,
                feasibility=8,
                risk=1,
                evaluation=["planning_success_rate", "planning_time", "path_length"],
                evidence_keys=["bad-citation-key"],
                baseline="RRT*",
                gap_alignment="覆盖路径规划 baseline 对比。",
                experiment_sketch=["构建任务", "运行 baseline", "比较候选"],
            )
            write_json(out / "02-ideas.json", [idea])
            write_text(out / "02-ideas.md", "# Ideas\n\n- 证据无效分支")
            pipeline_module._write_state(out, "机械臂路径规划", "ideation_completed")

            original = pipeline_module.build_llm
            pipeline_module.build_llm = lambda _: NoopLLM()
            try:
                with self.assertRaisesRegex(RuntimeError, "Experiment manager blocked downstream planning"):
                    pipeline_module.resume_pipeline_after_review_approval("机械臂路径规划", out, config)
            finally:
                pipeline_module.build_llm = original

            state = json.loads((out / "state.json").read_text(encoding="utf-8"))
            manager = json.loads((out / "02-experiment-manager.json").read_text(encoding="utf-8"))
            repair_queue = json.loads((out / "12-repair-queue.json").read_text(encoding="utf-8"))
            repair_resume = json.loads((out / "12-repair-resume-plan.json").read_text(encoding="utf-8"))
            manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(state["stage"], "experiment_manager_blocked")
            self.assertEqual(manager["status"], "block")
            self.assertFalse((out / "03-experiment-plan.json").exists())
            self.assertEqual(repair_queue["status"], "blocked_repair_required")
            self.assertIn(repair_resume["rerun_from"], {"literature_review", "literature_context", "ideation"})
            self.assertTrue(repair_resume["can_resume"])
            self.assertIn("02-ideas.json", repair_resume["artifacts_to_remove"])
            self.assertTrue(any("禁止生成实验计划" in item for item in repair_resume["repair_context"]["constraints"]))
            self.assertTrue(any(event["stage"] == "experiment_manager_blocked" for event in manifest["events"]))

    def test_repair_resume_validates_llm_before_cleanup(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                out / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "重新运行实验。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(out / "04-results.json", [{"status": "stale"}])

            with self.assertRaisesRegex(RuntimeError, "Missing model"):
                pipeline_module.resume_pipeline_from_repair_queue("机械臂路径规划", out, AgentConfig())

            self.assertTrue((out / "04-results.json").exists())
            self.assertFalse((out / "12-repair-resume-plan.json").exists())

    def test_repair_resume_requires_release_values_before_cleanup(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "Iris", "stage": "completed"})
            write_json(
                out / "12-repair-queue.json",
                {
                    "topic": "Iris",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-REL",
                            "severity": "high",
                            "category": "release_metadata",
                            "source_artifact": "10-release-metadata.json",
                            "action": "补齐 release metadata。",
                            "rerun_from": "final_readiness",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                out / "10-release-metadata.json",
                {
                    "status": "needs_release_metadata",
                    "recommended_config": {
                        "status": "needs_input",
                        "required_fields": ["release_code_repository_url", "release_code_archive_doi"],
                        "recommended_fields": [],
                        "config_fields": {"code_repository_url": "", "code_archive_doi": ""},
                    },
                },
            )
            write_json(out / "10-final-readiness.json", {"status": "stale"})

            with self.assertRaisesRegex(RuntimeError, "Missing required release metadata"):
                pipeline_module.resume_pipeline_from_repair_queue("Iris", out, AgentConfig())

            self.assertTrue((out / "10-final-readiness.json").exists())
            self.assertFalse((out / "12-repair-resume-plan.json").exists())

    def test_repair_resume_rejects_topic_mismatch_before_cleanup(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "original topic", "stage": "completed"})
            write_json(
                out / "12-repair-queue.json",
                {
                    "topic": "original topic",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "重新运行实验。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(out / "04-results.json", [{"status": "stale"}])

            with self.assertRaisesRegex(RuntimeError, "topic does not match"):
                pipeline_module.resume_pipeline_from_repair_queue("different topic", out, AgentConfig())

            self.assertTrue((out / "04-results.json").exists())
            self.assertFalse((out / "12-repair-resume-plan.json").exists())

    def test_repair_resume_rejects_invalid_resource_limits_before_cleanup(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "Iris", "stage": "completed"})
            write_json(
                out / "12-repair-queue.json",
                {
                    "topic": "Iris",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "重新运行实验。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(out / "04-results.json", [{"status": "stale"}])
            original_build_llm = pipeline_module.build_llm
            pipeline_module.build_llm = lambda _: NoopLLM()
            try:
                with self.assertRaisesRegex(ValueError, "repeats"):
                    pipeline_module.resume_pipeline_from_repair_queue(
                        "Iris",
                        out,
                        AgentConfig(execution=ExecutionConfig(repeats=101)),
                    )
            finally:
                pipeline_module.build_llm = original_build_llm

            self.assertTrue((out / "04-results.json").exists())
            self.assertFalse((out / "12-repair-resume-plan.json").exists())

    def test_repair_resume_apply_marks_state_before_checkpoint_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            out.mkdir()
            write_json(out / "state.json", {"topic": "Iris", "stage": "completed"})
            write_json(
                out / "12-repair-queue.json",
                {
                    "topic": "Iris",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-001",
                            "severity": "block",
                            "category": "result_validation",
                            "source_artifact": "04-result-validation.json",
                            "action": "重新运行实验。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(out / "04-results.json", [{"status": "stale"}])
            config = AgentConfig()

            original_build_llm = pipeline_module.build_llm
            original_resume = pipeline_module.resume_pipeline_from_checkpoint

            def fake_resume(topic: str, run_dir: Path, config: AgentConfig) -> Path:
                self.assertFalse((run_dir / "04-results.json").exists())
                state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["stage"], "repair_resume_applied")
                contract = json.loads((run_dir / "run-checkpoint-contract.json").read_text(encoding="utf-8"))
                self.assertEqual(contract["renewal"]["renewed_by"], "repair_resume")
                self.assertEqual(contract["fingerprint"], pipeline_module._checkpoint_contract(topic, config)["fingerprint"])
                raise RuntimeError("checkpoint failed after cleanup")

            try:
                pipeline_module.build_llm = lambda _: NoopLLM()
                pipeline_module.resume_pipeline_from_checkpoint = fake_resume
                with self.assertRaisesRegex(RuntimeError, "checkpoint failed after cleanup"):
                    pipeline_module.resume_pipeline_from_repair_queue("Iris", out, config)
            finally:
                pipeline_module.build_llm = original_build_llm
                pipeline_module.resume_pipeline_from_checkpoint = original_resume

            state = json.loads((out / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "repair_resume_applied")
            self.assertFalse((out / "04-results.json").exists())
            plan = json.loads((out / "12-repair-resume-plan.json").read_text(encoding="utf-8"))
            self.assertTrue(plan["applied"])
            self.assertEqual(plan["checkpoint_contract"]["renewed_by"], "repair_resume")


if __name__ == "__main__":
    unittest.main()
