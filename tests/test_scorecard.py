from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.scorecard import build_research_scorecard_report, render_research_scorecard_markdown, write_research_scorecard_artifacts


class ResearchScorecardTest(unittest.TestCase):
    def test_scorecard_scores_complete_run_dimensions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)

            report = write_research_scorecard_artifacts("机械臂路径规划", run_dir)
            rendered = render_research_scorecard_markdown(report)
            saved = json.loads((run_dir / "13-research-scorecard.json").read_text(encoding="utf-8"))

            self.assertGreaterEqual(report.overall_score, 75.0)
            self.assertFalse(report.blocking_issues)
            self.assertTrue(any(item.category == "experiment_benchmark" for item in report.dimensions))
            self.assertTrue(any("snowball=ready_for_review" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("coverage=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("evidence_mix=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("rescue=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("rescue_execution=executed:1/0:2" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("seed_intake=pass:pass:3/3" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("search_strategy=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("query_execution=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("citation_integrity=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("metadata=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "literature_evidence"))
            self.assertTrue(any("novelty=likely_novel" in "；".join(item.evidence) for item in report.dimensions if item.category == "idea_exploration"))
            self.assertTrue(any("idea_audit=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "idea_exploration"))
            self.assertTrue(any("traceability=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("citation_grounding=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("citation_coverage=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("results_presentation=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("claim_consistency=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("claim_preflight=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("revision_response=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "paper_quality"))
            self.assertTrue(any("ai_disclosure=not_applicable" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("repair_queue=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("repair_resolution=not_applicable" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("llm_trace_audit=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("run_economics=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("observability=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("open_source_compliance=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("run_integrity=pass:12/0/0" in "；".join(item.evidence) for item in report.dimensions if item.category == "submission_readiness"))
            self.assertTrue(any("environment=complete" in "；".join(item.evidence) for item in report.dimensions if item.category == "reproducibility_release"))
            self.assertTrue(any("experiment_audit=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("idea_experiment_contract=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("review_constraint_compliance=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("execution_safety=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("failure_analysis=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("benchmark_schema=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("benchmark_evidence=pass:real_benchmark" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("adapter_paper_grade=ready:0" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("benchmark_readiness=ready_for_benchmark" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("experiment_decision=proceed_to_paper" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("hypothesis_outcome=supported" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("ablation=pass" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertTrue(any("preregistration=locked" in "；".join(item.evidence) for item in report.dimensions if item.category == "experiment_benchmark"))
            self.assertIn(report.status, {"needs_targeted_iteration", "ready_for_human_submission_upload"})
            self.assertIn("研究 Run 分数卡", rendered)
            self.assertEqual(saved["topic"], "机械臂路径规划")

    def test_scorecard_blocks_bad_citations_and_adapter_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(run_dir / "01-citation-audit.json", {"total_citations": 3, "usable_citations": 1, "blocked_citations": 2, "doi_coverage": 0.1})
            write_json(run_dir / "03-benchmark-adapters.json", {"blocking_issues": ["manifest 命令越界"]})

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("literature_evidence" in issue for issue in report.blocking_issues))
            self.assertTrue(any("experiment_benchmark" in issue for issue in report.blocking_issues))

    def test_scorecard_warns_on_weak_literature_search_strategy(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "01-literature-search-strategy.json",
                {
                    "status": "needs_query_repair",
                    "quality_score": 0.41,
                    "missing_required_intents": ["baseline", "benchmark"],
                    "weak_selected_queries": ["robot"],
                    "recommendations": ["补 baseline query", "补 benchmark query"],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)
            evidence = next(item for item in report.dimensions if item.category == "literature_evidence")

            self.assertEqual(evidence.status, "manual_required")
            self.assertTrue(any("search_strategy=needs_query_repair" in item for item in evidence.evidence))
            self.assertTrue(any("baseline query" in action for action in evidence.actions))

    def test_scorecard_blocks_invalid_experiment_results(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "04-result-validation.json",
                {
                    "status": "block",
                    "blocking_issues": ["candidate 与 baseline 没有可比较的共同指标。"],
                    "warnings": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("共同指标" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_benchmark_result_schema_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "04-benchmark-result-schema-audit.json",
                {"status": "block", "blocking_issues": ["candidate 与 baseline schema 不一致"], "manual_tasks": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("schema 不一致" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_results_presentation_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "10-results-presentation.json",
                {"status": "block", "presentation_score": 0.2, "blocking_issues": ["无统计支撑的比较性主张"], "manual_tasks": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("结果呈现" in issue or "results" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_citation_coverage_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "10-citation-coverage.json",
                {"status": "block", "coverage_score": 0.1, "blocking_issues": ["正文没有可核对 citation marker"], "manual_tasks": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("citation coverage" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_claim_consistency_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "10-claim-consistency.json",
                {"status": "block", "consistency_score": 0.2, "blocking_issues": ["过强正向结论"], "manual_tasks": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("过强结论" in issue or "hypothesis outcome" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_claim_boundary_preflight(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {"status": "block", "writing_mode": "repair_report_only", "risk_score": 1.0, "blocking_issues": ["实验后决策不允许正常写作"], "warnings": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("claim boundary preflight" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_revision_response_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "09-revision-response-audit.json",
                {"status": "block", "response_score": 0.2, "blocking_issues": ["R01 高优先级任务缺少正文回应"], "manual_tasks": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("revision response" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_execution_safety_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(run_dir / "03-execution-safety-audit.json", {"status": "block", "blocking_issues": ["bash 不在 allowed_commands"], "warnings": []})

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("bash 不在 allowed_commands" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_benchmark_readiness_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(run_dir / "03-benchmark-readiness.json", {"status": "block", "blocking_issues": ["benchmark 模式必须配置 manifest"], "manual_tasks": []})

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("benchmark 模式必须配置 manifest" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_idea_experiment_contract_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "03-idea-experiment-contract.json",
                {"status": "block", "contract_score": 0.2, "blocking_issues": ["选中 idea 没有 evidence_keys"], "manual_tasks": []},
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("evidence_keys" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_literature_evidence_mix_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "01-literature-evidence-mix.json",
                {
                    "status": "block",
                    "mix_score": 0.2,
                    "blocking_issues": ["证据池少于 3 篇且缺失必需 anchor"],
                    "required_actions": ["补核心 DOI seed。"],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("anchor" in issue for issue in report.blocking_issues))

    def test_scorecard_requires_manual_seed_role_coverage_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
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

            report = build_research_scorecard_report("机械臂路径规划", run_dir)
            evidence = next(item for item in report.dimensions if item.category == "literature_evidence")

            self.assertEqual(evidence.status, "manual_required")
            self.assertTrue(any("seed_intake=pass:review_required:3/3" in item for item in evidence.evidence))
            self.assertTrue(any("seed 角色覆盖" in item for item in evidence.actions))

    def test_scorecard_requires_manual_paper_grade_literature_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "01-literature-gate-decision.json",
                {
                    "status": "review_required",
                    "paper_grade_literature": {
                        "status": "review_required",
                        "issues": ["paper-grade 文献需要 literature.provider=online/auto，当前 offline。"],
                    },
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)
            evidence = next(item for item in report.dimensions if item.category == "literature_evidence")

            self.assertEqual(evidence.status, "manual_required")
            self.assertTrue(any("paper_grade_literature=review_required:1" in item for item in evidence.evidence))
            self.assertTrue(any("provider=online/auto" in item for item in evidence.actions))

    def test_scorecard_uses_seed_suggestions_when_seed_intake_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            (run_dir / "01-seed-paper-intake.json").unlink()
            write_json(
                run_dir / "01-literature-quality.json",
                {
                    "selected_papers": 2,
                    "warnings": [],
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

            report = build_research_scorecard_report("机械臂路径规划", run_dir)
            evidence = next(item for item in report.dimensions if item.category == "literature_evidence")

            self.assertEqual(evidence.status, "manual_required")
            self.assertTrue(any("seed_intake=not_configured:review_required:0/0" in item for item in evidence.evidence))
            self.assertTrue(any("seed_suggestions=1" in item for item in evidence.evidence))
            self.assertTrue(any("survey review" in item for item in evidence.actions))

    def test_scorecard_blocks_unresolved_literature_rescue_execution(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
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
                    "query_outcomes": [{"status": "no_hits", "query": "robot arm path planning benchmark"}],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)
            evidence = next(item for item in report.dimensions if item.category == "literature_evidence")

            self.assertEqual(report.status, "blocked")
            self.assertEqual(evidence.status, "block")
            self.assertTrue(any("rescue_execution=no_new_papers:0/1:0" in item for item in evidence.evidence))
            self.assertTrue(any("补检索没有带来新增" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_duplicate_selected_idea(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "02-novelty-audit.json",
                {
                    "items": [
                        {
                            "idea_title": "idea-a",
                            "decision": "likely_duplicate",
                            "duplicate_risk": 0.78,
                            "closest_paper": {"title": "Existing planner"},
                        }
                    ]
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("idea_exploration" in issue for issue in report.blocking_issues))
            self.assertTrue(any("高度相似" in issue for issue in report.blocking_issues))

    def test_scorecard_marks_ai_disclosure_policy_check_as_manual_work(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(run_dir / "10-ai-disclosure.json", {"status": "needs_human_policy_check", "used_ai": True, "total_llm_calls": 8})

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "needs_human_work")
            self.assertTrue(any("AI disclosure policy" in task for task in report.manual_tasks))

    def test_scorecard_blocks_open_repair_queue_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "status": "blocked_repair_required",
                    "summary": {"total": 1, "block": 1, "high": 0, "medium": 0},
                    "items": [{"task_id": "RQ-001", "severity": "block"}],
                    "blocking_issues": ["RQ-001 04-result-validation.json: 修复共同指标"],
                    "manual_tasks": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("repair-queue" in issue or "12-repair-queue" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_agent_stage_contract_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "13-agent-stage-contract.json",
                {
                    "status": "block",
                    "score": 0.66,
                    "blocking_issues": ["literature_grounding: context citations too low"],
                    "manual_tasks": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("13-agent-stage-contract" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_unresolved_repair_resume_items(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "12-repair-resolution-audit.json",
                {
                    "status": "block",
                    "resolution_score": 0.2,
                    "blocking_issues": ["03-idea-experiment-contract.json 仍未闭环"],
                    "manual_tasks": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("12-repair-resolution" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_llm_trace_audit_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "13-llm-trace-audit.json",
                {
                    "status": "block",
                    "coverage": {"coverage_ratio": 0.71},
                    "blocking_issues": ["paper_revision: missing success call"],
                    "warnings": [],
                    "manual_tasks": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("13-llm-trace-audit" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_agent_observability_audit_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "13-agent-observability-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["approval.json 缺失，无法证明 idea/实验前有人工 gate。"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("13-agent-observability-audit" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_run_economics_audit_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "13-run-economics-audit.json",
                {
                    "status": "block",
                    "blocking_issues": ["LLM ledger 存在 failed=1 budget_exceeded=0。"],
                    "manual_tasks": [],
                    "warnings": [],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("13-run-economics-audit" in issue for issue in report.blocking_issues))

    def test_scorecard_blocks_run_integrity_audit_blockers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            write_json(
                run_dir / "14-run-integrity-audit.json",
                {
                    "status": "block",
                    "summary": {"pass": 8, "warn": 1, "block": 1},
                    "blocking_issues": ["security/run_config_secret: run-config.json 中 llm.api_key 非空。"],
                    "warnings": [],
                    "recommended_actions": ["清除落盘 API key。"],
                },
            )

            report = build_research_scorecard_report("机械臂路径规划", run_dir)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("14-run-integrity-audit" in issue for issue in report.blocking_issues))

    def test_scorecard_accepts_bounded_negative_or_neutral_benchmark_handoff(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ready_inputs(run_dir)
            warning = "所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽；当前 repeat 未观察到差异，不能据此声明优势或稳定性。"
            write_json(
                run_dir / "04-result-validation.json",
                {
                    "status": "warn",
                    "blocking_issues": [],
                    "warnings": [warning],
                    "items": [{"name": "statistical_comparability", "status": "warn", "detail": warning}],
                },
            )
            write_json(
                run_dir / "04-failure-analysis.json",
                {
                    "status": "warn",
                    "summary": {"failed_runs": 0, "negative_metrics": 2, "uncertain_metrics": 2},
                    "required_actions": ["负向/中性指标必须进入结果和局限性。"],
                },
            )
            write_json(
                run_dir / "04-benchmark-evidence-audit.json",
                {
                    "status": "warn",
                    "evidence_grade": "real_benchmark",
                    "statistical_outcome": "neutral_no_observed_difference",
                    "claim_boundary_severity": "negative_or_neutral_no_superiority",
                    "publishable_negative_or_neutral_result": True,
                    "adapter_paper_grade_status": "ready",
                    "adapter_paper_grade_issues": [],
                    "blocking_issues": [],
                    "manual_tasks": [],
                    "required_actions": ["将负/中性 benchmark 结果作为可发表结果报告。"],
                },
            )
            write_json(run_dir / "04-experiment-decision.json", {"status": "warn", "decision": "pivot_or_refine", "next_actions": []})
            write_json(run_dir / "04-hypothesis-outcome.json", {"status": "review_required", "outcome": "refuted_or_negative", "support_score": 0.0, "next_actions": []})
            write_json(
                run_dir / "04-claim-boundary-preflight.json",
                {
                    "status": "review_required",
                    "writing_mode": "negative_or_pivot_report",
                    "risk_score": 0.55,
                    "blocking_issues": [],
                    "warnings": ["必须报告负/中性结果。"],
                    "required_actions": ["不得声明 candidate 优于 baseline。"],
                },
            )
            write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})

            report = build_research_scorecard_report("机械臂路径规划", run_dir)
            experiment = next(item for item in report.dimensions if item.category == "experiment_benchmark")
            paper = next(item for item in report.dimensions if item.category == "paper_quality")

            self.assertEqual(experiment.status, "pass")
            self.assertEqual(paper.status, "pass")
            self.assertTrue(any("bounded_negative_or_neutral=True" in item for item in experiment.evidence))
            self.assertTrue(any("bounded_negative_or_neutral=True" in item for item in paper.evidence))
            self.assertFalse(any("04-hypothesis-outcome" in action for action in report.next_actions))


def _write_ready_inputs(run_dir: Path) -> None:
    write_json(
        run_dir / "01-literature-search-strategy.json",
        {
            "status": "pass",
            "quality_score": 0.94,
            "selected_queries": [
                "robot manipulator motion planning collision avoidance",
                "sampling-based motion planning RRT RRT* PRM robot manipulator",
                "OMPL motion planning benchmark robot manipulator",
            ],
            "selected_intents": ["baseline", "benchmark", "method"],
            "missing_required_intents": [],
            "weak_selected_queries": [],
            "recommendations": [],
        },
    )
    write_json(run_dir / "01-literature-rerank.json", {"status": "pass", "warnings": [], "recommended_actions": []})
    write_json(
        run_dir / "01-query-execution-audit.json",
        {
            "status": "pass",
            "selected_query_count": 3,
            "source_coverage": {"sources_with_success": 2, "configured_source_count": 2},
            "top_rerank_coverage": {"covered_top_count": 5, "top_count": 5},
            "recommended_actions": [],
        },
    )
    write_json(run_dir / "01-literature-quality.json", {"selected_papers": 5, "warnings": []})
    write_json(run_dir / "01-literature-metadata-audit.json", {"status": "pass", "verifiability_score": 0.92, "blocked": 0, "review_required": 0, "required_actions": []})
    write_json(run_dir / "01-literature-snowball.json", {"status": "ready_for_review", "required_actions": [], "seed_count": 5, "query_count": 12})
    write_json(run_dir / "01-literature-coverage.json", {"status": "pass", "coverage_ratio": 1.0, "required_actions": []})
    write_json(run_dir / "01-literature-evidence-mix.json", {"status": "pass", "mix_score": 0.9, "blocking_issues": [], "warnings": [], "required_actions": []})
    write_json(run_dir / "01-literature-rescue-plan.json", {"status": "pass", "rescue_queries": [], "required_actions": []})
    write_json(
        run_dir / "01-literature-rescue-execution.json",
        {"status": "executed", "trigger_status": "needs_rescue_search", "new_unique_papers": 2, "closed_query_outcomes": 1, "unresolved_query_outcomes": 0, "required_actions": []},
    )
    write_json(
        run_dir / "01-seed-paper-intake.json",
        {"status": "pass", "role_coverage_status": "pass", "total_seed_entries": 3, "curated_seed_papers": 3, "required_actions": []},
    )
    write_json(run_dir / "01-context.json", {"citations": [{"key": "a"}, {"key": "b"}, {"key": "c"}, {"key": "d"}, {"key": "e"}]})
    write_json(run_dir / "01-citation-audit.json", {"total_citations": 5, "usable_citations": 5, "blocked_citations": 0, "doi_coverage": 0.8, "integrity_status": "pass", "integrity_score": 0.91})
    write_json(run_dir / "02-ideas.json", [{"title": "idea-a"}, {"title": "idea-b"}])
    write_json(
        run_dir / "02-novelty-audit.json",
        {"items": [{"idea_title": "idea-a", "decision": "likely_novel", "duplicate_risk": 0.12, "closest_paper": {"title": "Prior work"}}]},
    )
    write_json(run_dir / "02-idea-audit.json", {"status": "pass", "blocked": 0, "review_required": 0})
    write_json(
        run_dir / "02-exploration-map.json",
        {
            "selected_branch_id": "B1",
            "selected_idea_title": "idea-a",
            "warnings": [],
            "branches": [{"branch_id": "B1", "status": "selected", "score": 8.2, "evidence_count": 4, "title": "idea-a"}],
        },
    )
    write_json(
        run_dir / "04-experiment-runbook.json",
        {
            "execution": {"mode": "local", "repeats": 3},
            "runs": [{"seed": "a"}, {"seed": "b"}, {"seed": "c"}],
            "artifacts": [{"path": "experiments/metrics.json"}],
            "environment": {"status": "complete", "source_tree": {"file_count": 3}, "package_versions": [{"name": "pip", "version": "1"}]},
        },
    )
    write_json(
        run_dir / "04-environment-snapshot.json",
        {"status": "complete", "source_tree": {"file_count": 3}, "package_versions": [{"name": "pip", "version": "1"}]},
    )
    write_json(run_dir / "04-statistics.json", {"repeats": 3, "comparisons": [{"metric": "success"}, {"metric": "time"}]})
    write_json(run_dir / "03-experiment-audit.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "03-idea-experiment-contract.json", {"status": "pass", "contract_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "03-review-constraint-compliance.json", {"status": "pass", "checked_constraints": 1, "blocked": 0, "review_required": 0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "03-execution-safety-audit.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "04-result-validation.json", {"status": "pass", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(
        run_dir / "04-failure-analysis.json",
        {
            "status": "pass",
            "summary": {"failed_runs": 0, "negative_metrics": 0, "uncertain_metrics": 0},
            "required_actions": [],
        },
    )
    write_json(
        run_dir / "04-benchmark-evidence-audit.json",
        {
            "status": "pass",
            "evidence_grade": "real_benchmark",
            "adapter_paper_grade_status": "ready",
            "adapter_paper_grade_issues": [],
            "blocking_issues": [],
            "manual_tasks": [],
            "required_actions": [],
        },
    )
    write_json(run_dir / "04-experiment-decision.json", {"status": "pass", "decision": "proceed_to_paper", "next_actions": []})
    write_json(run_dir / "04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported", "support_score": 1.0, "next_actions": []})
    write_json(run_dir / "04-claim-boundary-preflight.json", {"status": "pass", "writing_mode": "conservative_paper", "risk_score": 0.1, "blocking_issues": [], "warnings": [], "required_actions": []})
    write_json(run_dir / "09-revision-response-audit.json", {"status": "pass", "response_score": 1.0, "blocking_issues": [], "manual_tasks": [], "required_actions": []})
    write_json(run_dir / "03-benchmark-readiness.json", {"status": "ready_for_benchmark", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "03-ablation-plan.json", {"status": "pass", "has_ablation": True, "blocking_issues": [], "warnings": [], "required_actions": []})
    write_json(run_dir / "03-preregistration.json", {"status": "locked", "blocking_issues": [], "warnings": []})
    write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo"], "required_actions": []})
    write_json(run_dir / "03-benchmark-adapters.json", {"blocking_issues": []})
    write_json(run_dir / "10-revised-paper-review.json", {"score": 8.5})
    write_json(
        run_dir / "10-claim-traceability.json",
        {"status": "pass", "traceability_score": 1.0, "blocked_claims": 0, "review_claims": 0, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(
        run_dir / "10-citation-grounding.json",
        {"status": "pass", "grounding_score": 1.0, "blocked_citations": 0, "review_citations": 0, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(run_dir / "10-citation-coverage.json", {"status": "pass", "coverage_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(
        run_dir / "10-results-presentation.json",
        {"status": "pass", "presentation_score": 1.0, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(
        run_dir / "10-claim-consistency.json",
        {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []},
    )
    write_json(
        run_dir / "10-final-readiness.json",
        {"status": "ready_for_submission_check", "score_after": 8.5, "unsupported_after": 0, "weak_after": 0, "deferred_tasks": []},
    )
    write_json(run_dir / "10-code-data-availability.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
    write_json(run_dir / "10-release-metadata.json", {"status": "ready_for_release", "manual_tasks": [], "blocking_issues": []})
    write_json(run_dir / "10-ai-disclosure.json", {"status": "not_applicable", "used_ai": False, "total_llm_calls": 0})
    write_json(run_dir / "10-submission-check.json", {"status": "ready_for_submission_check", "manual_tasks": [], "blocking_issues": []})
    write_json(run_dir / "11-submission-package.json", {"status": "ready_for_human_submission_upload", "manual_tasks": [], "blocking_issues": []})
    write_json(run_dir / "12-next-iteration-plan.json", {"status": "ready_for_submission_upload"})
    write_json(
        run_dir / "12-repair-queue.json",
        {"status": "pass", "summary": {"total": 0, "block": 0, "high": 0, "medium": 0}, "items": [], "blocking_issues": [], "manual_tasks": []},
    )
    write_json(run_dir / "12-repair-resolution-audit.json", {"status": "not_applicable", "resolution_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-stage-contract.json", {"status": "pass", "score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass", "coverage": {"coverage_ratio": 1.0}, "blocking_issues": [], "warnings": [], "manual_tasks": []})
    write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "summary": {"input_tokens_estimated": 100, "output_tokens_estimated": 50}, "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "13-open-source-compliance.json", {"status": "pass", "score": 1.0, "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"pass": 12, "warn": 0, "block": 0}, "blocking_issues": [], "warnings": []})


if __name__ == "__main__":
    unittest.main()
