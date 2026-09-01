from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.config import AgentConfig, ExecutionConfig, LiteratureConfig, PaperGradeConfig, ReleaseConfig
from research_agent.pipeline import _repair_resume_context
from research_agent.repair_resume import (
    apply_repair_resume_recommendations,
    build_repair_resume_plan,
    missing_repair_resume_required_release_values,
    prepare_repair_resume,
    render_repair_resume_plan_markdown,
)


class RepairResumeTest(unittest.TestCase):
    def test_build_plan_selects_earliest_rerun_and_preserves_upstream_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="experiments")
            write_json(run_dir / "03-experiment-plan.json", {"status": "keep"})
            write_json(run_dir / "03-execution-approval.json", {"approved": True})
            write_json(run_dir / "04-results.json", [{"status": "stale"}])
            write_json(run_dir / "05-analysis.json", {"status": "stale"})
            write_text(run_dir / "06-paper.md", "# stale paper")
            (run_dir / "experiments").mkdir()
            write_text(run_dir / "experiments" / "metrics.json", "{}")

            report = build_repair_resume_plan(run_dir)

            self.assertTrue(report["can_resume"])
            self.assertEqual(report["rerun_from"], "experiments")
            self.assertIn("04-results.json", report["artifacts_to_remove"])
            self.assertIn("05-analysis.json", report["artifacts_to_remove"])
            self.assertIn("06-paper.md", report["artifacts_to_remove"])
            self.assertIn("03-execution-approval.json", report["artifacts_to_remove"])
            self.assertNotIn("03-experiment-plan.json", report["artifacts_to_remove"])
            self.assertTrue(report["execution_reapproval_required"])

    def test_prepare_repair_resume_removes_downstream_artifacts_and_writes_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="paper_rewrite")
            write_text(run_dir / "08-revision-plan.md", "# keep revision plan")
            write_text(run_dir / "09-revised-paper.md", "# stale revised paper")
            write_json(run_dir / "10-final-readiness.json", {"status": "stale"})
            write_text(run_dir / "12-repair-queue.md", "# stale queue")
            (run_dir / "submission-package").mkdir()
            write_text(run_dir / "submission-package" / "README.md", "stale")

            report = prepare_repair_resume(run_dir, apply=True)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertTrue(report["applied"])
            self.assertIsNotNone(report["applied_at"])
            self.assertFalse((run_dir / "09-revised-paper.md").exists())
            self.assertFalse((run_dir / "10-final-readiness.json").exists())
            self.assertFalse((run_dir / "12-repair-queue.json").exists())
            self.assertFalse((run_dir / "submission-package").exists())
            self.assertTrue((run_dir / "08-revision-plan.md").exists())
            self.assertTrue((run_dir / "12-repair-resume-plan.json").exists())
            self.assertIn("修复恢复计划", rendered)

    def test_prepare_repair_resume_does_not_delete_prefix_sibling_symlink_target(self) -> None:
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            sibling = parent / "run-evil"
            run_dir.mkdir()
            sibling.mkdir()
            _write_queue(run_dir, rerun_from="experiments")
            outside_target = sibling / "04-results.json"
            write_json(outside_target, {"status": "outside"})
            (run_dir / "04-results.json").symlink_to(outside_target)

            report = prepare_repair_resume(run_dir, apply=True)

            self.assertTrue(outside_target.exists())
            self.assertTrue((run_dir / "04-results.json").exists())
            self.assertNotIn("04-results.json", report["removed_artifacts"])

    def test_literature_context_repair_requires_review_reapproval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_context")
            write_json(run_dir / "approval.json", {"approved": True})
            write_json(run_dir / "01-context.json", {"citations": []})
            write_json(run_dir / "02-ideas.json", [{"title": "stale"}])

            report = prepare_repair_resume(run_dir, apply=True)

            self.assertTrue(report["review_reapproval_required"])
            self.assertFalse((run_dir / "approval.json").exists())
            self.assertFalse((run_dir / "01-context.json").exists())
            self.assertFalse((run_dir / "02-ideas.json").exists())

    def test_literature_review_repair_preserves_agent_retrieval_tasks(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_review")
            write_json(
                run_dir / "01-literature-search-feedback.json",
                {
                    "retrieval_repair_tasks": [
                        {
                            "task_id": "retrieval-repair-001",
                            "category": "query_repair",
                            "priority": 96,
                            "owner": "agent",
                            "action": "执行补检索式并合并去重候选。",
                            "query": "robot manipulator OMPL benchmark",
                        },
                        {
                            "task_id": "retrieval-repair-002",
                            "category": "seed_repair",
                            "priority": 94,
                            "owner": "human",
                            "action": "补 DOI seed。",
                            "query": "human task should not execute",
                        },
                    ]
                },
            )

            report = prepare_repair_resume(run_dir, apply=True)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertTrue(report["review_reapproval_required"])
            self.assertFalse((run_dir / "01-literature-search-feedback.json").exists())
            self.assertEqual(len(report["retrieval_repair_tasks"]), 1)
            self.assertEqual(report["retrieval_repair_tasks"][0]["task_id"], "retrieval-repair-001")
            self.assertIn("文献检索修复任务", rendered)

    def test_literature_repair_resume_applies_feedback_config_recommendations(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_review")
            write_json(
                run_dir / "01-literature-search-feedback.json",
                {
                    "next_run_config": {
                        "literature_provider": "online",
                        "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
                        "max_papers": 12,
                        "max_search_queries": 6,
                    },
                    "retrieval_repair_tasks": [
                        {
                            "task_id": "retrieval-repair-001",
                            "category": "query_repair",
                            "priority": 96,
                            "owner": "agent",
                            "query": "robot manipulator OMPL benchmark",
                        }
                    ],
                },
            )

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(literature=LiteratureConfig(provider="offline", sources=["crossref"], max_papers=4, max_search_queries=2))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertEqual(report["recommended_config"]["literature_provider"], "online")
            self.assertEqual(updated.literature.provider, "online")
            self.assertGreaterEqual(updated.literature.max_papers, 12)
            self.assertGreaterEqual(updated.literature.max_search_queries, 6)
            self.assertIn("openalex", updated.literature.sources)
            self.assertIn("robot manipulator OMPL benchmark", updated.literature.extra_search_queries)
            self.assertIn("推荐下次文献配置", rendered)

    def test_literature_repair_resume_converts_seed_role_gaps_to_repair_queries(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_review")
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

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(literature=LiteratureConfig(provider="offline", sources=["crossref"], max_papers=4, max_search_queries=2))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            queries = [item["query"] for item in report["retrieval_repair_tasks"]]
            self.assertIn("机械臂路径规划 survey review state of the art", queries)
            self.assertIn("机械臂路径规划 benchmark dataset evaluation protocol", queries)
            self.assertEqual(report["recommended_config"]["literature_provider"], "online")
            self.assertEqual(updated.literature.provider, "online")
            self.assertGreaterEqual(updated.literature.max_papers, 12)
            self.assertGreaterEqual(updated.literature.max_search_queries, 6)
            self.assertIn("机械臂路径规划 survey review state of the art", updated.literature.extra_search_queries)
            self.assertIn("机械臂路径规划 benchmark dataset evaluation protocol", updated.literature.extra_search_queries)
            self.assertIn("seed-role-review", rendered)

    def test_literature_repair_resume_carries_seed_suggestions_without_intake_file(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_review")
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
                        },
                        {
                            "title": "Recent robot manipulator motion planning advances",
                            "doi": "10.1234/recent",
                            "url": "https://doi.org/10.1234/recent",
                            "selected": True,
                            "quality_score": 0.86,
                            "evidence_roles": ["recent_work"],
                        },
                    ]
                },
            )

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(literature=LiteratureConfig(provider="offline", sources=["crossref"], max_papers=4, max_search_queries=2))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertIn("10.1109/MRA.2012.2205651 The Open Motion Planning Library", report["recommended_seed_papers"])
            self.assertIn("10.1234/recent Recent robot manipulator motion planning advances", report["recommended_seed_papers"])
            self.assertIn("10.1109/MRA.2012.2205651 The Open Motion Planning Library", updated.literature.seed_papers)
            self.assertIn("10.1234/recent Recent robot manipulator motion planning advances", updated.literature.seed_papers)
            queries = [item["query"] for item in report["retrieval_repair_tasks"]]
            self.assertIn("机械臂路径规划 survey review state of the art", queries)
            self.assertIn("机械臂路径规划 survey review state of the art", updated.literature.extra_search_queries)
            self.assertEqual(report["recommended_config"]["literature_provider"], "online")
            self.assertIn("推荐下次人工 Seed Papers", rendered)

    def test_literature_repair_resume_consumes_paper_grade_gate_suggestions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_review")
            write_json(
                run_dir / "01-literature-gate-decision.json",
                {
                    "status": "review_required",
                    "paper_grade_literature": {
                        "status": "review_required",
                        "issues": ["paper-grade 文献至少配置 3 个在线来源，当前 1。"],
                        "repair_suggestions": [
                            {
                                "kind": "increase_literature_sources",
                                "target": "literature.sources",
                                "action": "配置至少 3 个在线来源。",
                                "recommended_config": {
                                    "literature_provider": "online",
                                    "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
                                    "max_papers": 12,
                                    "max_search_queries": 6,
                                },
                            },
                            {
                                "kind": "repair_doi_url_seed_papers",
                                "target": "literature.seed_papers",
                                "action": "补齐 DOI/URL seed。",
                                "recommended_config": {"seed_papers_min": 3},
                                "suggested_seed_entries": ["10.1109/MRA.2012.2205651 The Open Motion Planning Library"],
                            },
                        ],
                    },
                },
            )

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(literature=LiteratureConfig(provider="offline", sources=["crossref"], max_papers=4, max_search_queries=2))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertEqual(report["recommended_config"]["literature_provider"], "online")
            self.assertIn("openalex", report["recommended_config"]["sources"])
            self.assertEqual(report["recommended_config"]["seed_papers_min"], 3)
            self.assertTrue(report["recommended_paper_grade_config"]["enabled"])
            self.assertIn("paper_grade_literature_gate", report["recommended_paper_grade_config"]["reasons"])
            self.assertGreaterEqual(report["recommended_paper_grade_config"]["min_seed_papers"], 3)
            self.assertGreaterEqual(report["recommended_paper_grade_config"]["min_doi_url_seed_papers"], 3)
            self.assertIn("10.1109/MRA.2012.2205651 The Open Motion Planning Library", report["recommended_seed_papers"])
            self.assertEqual(updated.literature.provider, "online")
            self.assertTrue(updated.paper_grade.enabled)
            self.assertIn("openalex", updated.literature.sources)
            self.assertIn("10.1109/MRA.2012.2205651 The Open Motion Planning Library", updated.literature.seed_papers)
            self.assertIn("seed_papers_min", rendered)
            self.assertIn("推荐下次论文级门槛", rendered)

    def test_repair_resume_preserves_prior_paper_grade_run_config(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="experiments")
            write_json(run_dir / "run-config.json", {"paper_grade": {"enabled": True, "min_execution_repeats": 4}})

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(paper_grade=PaperGradeConfig(enabled=False, min_execution_repeats=3))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertTrue(report["recommended_paper_grade_config"]["enabled"])
            self.assertIn("run_config.paper_grade.enabled", report["recommended_paper_grade_config"]["reasons"])
            self.assertEqual(report["recommended_paper_grade_config"]["min_execution_repeats"], 4)
            self.assertTrue(updated.paper_grade.enabled)
            self.assertEqual(updated.paper_grade.min_execution_repeats, 4)
            self.assertIn("min_execution_repeats=4", rendered)

    def test_repair_resume_carries_release_metadata_fields_without_fabricating_values(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "Iris",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-REL-001",
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
                run_dir / "10-release-metadata.json",
                {
                    "status": "needs_release_metadata",
                    "recommended_config": {
                        "status": "needs_input",
                        "required_fields": ["release_code_repository_url", "release_code_archive_doi"],
                        "recommended_fields": ["release_data_archive_doi"],
                        "cli_args": [
                            "--release-code-repository-url",
                            "--release-code-archive-doi",
                            "--release-data-archive-doi",
                        ],
                        "config_fields": {
                            "code_repository_url": "",
                            "code_archive_doi": "",
                            "data_archive_doi": "",
                        },
                        "field_actions": {
                            "release_code_repository_url": {
                                "metadata_key": "code_repository_url",
                                "recommended_value": "",
                                "action": "填写公开代码仓库 URL。",
                            }
                        },
                    },
                },
            )

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(release=ReleaseConfig())
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            release_config = report["recommended_release_config"]
            self.assertIn("release_code_repository_url", release_config["required_fields"])
            self.assertIn("release_data_archive_doi", release_config["recommended_fields"])
            self.assertIn("--release-code-repository-url", release_config["cli_args"])
            self.assertEqual(release_config["config_fields"]["code_repository_url"], "")
            self.assertEqual(updated.release.code_repository_url, "")
            self.assertEqual(updated.release.code_archive_doi, "")
            self.assertIn("推荐下次发布配置", rendered)
            self.assertIn("--release-code-repository-url", rendered)

    def test_repair_resume_applies_nonempty_release_values_from_plan(self) -> None:
        report = {
            "applied": True,
            "recommended_release_config": {
                "config_fields": {
                    "code_repository_url": "https://github.com/example/research-agent",
                    "code_archive_doi": "10.5281/zenodo.1234567",
                }
            },
        }

        updated = apply_repair_resume_recommendations(AgentConfig(release=ReleaseConfig()), report)

        self.assertEqual(updated.release.code_repository_url, "https://github.com/example/research-agent")
        self.assertEqual(updated.release.code_archive_doi, "10.5281/zenodo.1234567")

    def test_required_release_value_check_uses_config_and_plan_values(self) -> None:
        report = {
            "recommended_release_config": {
                "required_fields": ["release_code_repository_url", "release_code_archive_doi"],
                "config_fields": {"code_archive_doi": "10.5281/zenodo.1234567"},
            }
        }
        config = AgentConfig(release=ReleaseConfig(code_repository_url="https://github.com/example/research-agent"))

        self.assertEqual(missing_repair_resume_required_release_values(config, report), [])

    def test_literature_repair_resume_falls_back_to_bounded_queries_without_prior_feedback(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="literature_review")

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(literature=LiteratureConfig(provider="offline", sources=["crossref"], max_papers=4, max_search_queries=2))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            queries = [item["query"] for item in report["retrieval_repair_tasks"]]
            self.assertIn("robot manipulator motion planning survey review", queries)
            self.assertIn("OMPL motion planning benchmark robot manipulator", queries)
            self.assertTrue(all(item["category"] == "bounded_rescue_query" for item in report["retrieval_repair_tasks"]))
            self.assertTrue(all(item["owner"] == "agent+human" for item in report["retrieval_repair_tasks"]))
            self.assertTrue(all(item["source"] == "repair-resume-fallback" for item in report["retrieval_repair_tasks"]))
            self.assertEqual(report["recommended_seed_papers"], [])
            self.assertEqual(report["recommended_config"]["literature_provider"], "online")
            self.assertEqual(updated.literature.provider, "online")
            self.assertGreaterEqual(updated.literature.max_papers, 12)
            self.assertGreaterEqual(updated.literature.max_search_queries, 6)
            self.assertIn("robot manipulator motion planning survey review", updated.literature.extra_search_queries)
            self.assertEqual(updated.literature.seed_papers, [])
            self.assertIn("robot manipulator motion planning survey review", rendered)
            self.assertNotIn("推荐下次人工 Seed Papers", rendered)

    def test_repair_resume_preserves_audit_context_for_next_planning(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_queue(run_dir, rerun_from="experiment_plan")
            queue = {
                "topic": "机械臂路径规划",
                "status": "blocked_repair_required",
                "items": [
                    {
                        "task_id": "RQ-007",
                        "severity": "block",
                        "category": "idea_experiment_contract",
                        "source_artifact": "03-idea-experiment-contract.json",
                        "action": "修复 idea 到实验计划的 evidence/baseline 契约。",
                        "rerun_from": "experiment_plan",
                        "status": "open",
                    }
                ],
            }
            write_json(run_dir / "12-repair-queue.json", queue)
            write_json(
                run_dir / "03-idea-experiment-contract.json",
                {
                    "status": "block",
                    "blocking_issues": ["选中 idea 没有 evidence_keys。"],
                    "manual_tasks": ["让 baseline 与 RRT* 对齐。"],
                    "checks": [
                        {
                            "name": "evidence_carryover",
                            "status": "block",
                            "required_actions": ["把选中 idea 的 citation key 带入实验计划。"],
                            "evidence": ["idea_evidence=0"],
                        }
                    ],
                },
            )

            report = prepare_repair_resume(run_dir, apply=True)
            rendered = render_repair_resume_plan_markdown(report)
            context_text = _repair_resume_context(run_dir)

            self.assertTrue(report["applied"])
            self.assertIn("repair_context", report)
            self.assertTrue(any("evidence_keys" in item for item in report["repair_context"]["constraints"]))
            self.assertIn("把选中 idea 的 citation key", context_text)
            self.assertIn("供 Agent 重新规划的修复约束", rendered)

    def test_repair_resume_carries_experiment_manager_queue_actions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-MGR-001",
                            "severity": "block",
                            "category": "experiment_manager",
                            "source_artifact": "02-experiment-manager.json",
                            "action": "修复选中分支阻断、人工改选或重新生成实验管理策略。",
                            "rerun_from": "ideation",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "02-experiment-manager.json",
                {
                    "status": "block",
                    "selected_branch_id": "B1",
                    "manager_decision": "needs_human_reselection",
                    "execution_policy": "blocked",
                    "required_actions": ["选中分支的 idea audit 为 block；人工改选。"],
                    "manager_queue": [
                        {
                            "branch_id": "B1",
                            "title": "证据无效分支",
                            "selected": True,
                            "queue_state": "blocked_human_repair",
                            "requires_human": True,
                            "blocks_current_experiment": True,
                            "resume_from": "ideation",
                            "issues": ["invalid citation keys: bad"],
                        },
                        {
                            "branch_id": "B2",
                            "title": "谨慎候选",
                            "selected": False,
                            "queue_state": "needs_human_repair",
                            "requires_human": True,
                            "blocks_current_experiment": False,
                            "resume_from": "ideation",
                        },
                    ],
                },
            )
            write_json(run_dir / "02-ideas.json", [{"title": "stale"}])
            write_json(run_dir / "03-experiment-plan.json", {"status": "stale"})

            report = prepare_repair_resume(run_dir, apply=True)
            rendered = render_repair_resume_plan_markdown(report)
            context_text = _repair_resume_context(run_dir)

            self.assertEqual(report["rerun_from"], "ideation")
            self.assertFalse((run_dir / "02-ideas.json").exists())
            self.assertFalse((run_dir / "03-experiment-plan.json").exists())
            self.assertEqual(len(report["experiment_manager_resume_actions"]), 2)
            self.assertTrue(report["experiment_manager_resume_actions"][0]["blocks_current_experiment"])
            self.assertTrue(any("禁止生成实验计划" in item for item in report["repair_context"]["constraints"]))
            self.assertTrue(any("Experiment manager 阻断当前选中分支" in item for item in report["recommended_actions"]))
            self.assertIn("Experiment Manager 恢复动作", rendered)
            self.assertIn("invalid citation keys: bad", context_text)

    def test_benchmark_repair_resume_carries_execution_config_without_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest = run_dir / "adapter-manifest.json"
            write_json(
                manifest,
                {
                    "name": "OMPL adapter",
                    "command": ["python3", "run_benchmark.py"],
                    "metrics_path": "metrics.json",
                    "expected_artifacts": ["metrics.json"],
                },
            )
            write_json(
                run_dir / "run-config.json",
                {
                    "execution": {
                        "mode": "simulated",
                        "allowed_commands": ["python3"],
                        "repeats": 1,
                        "timeout_seconds": 120,
                        "benchmark_manifest_paths": [str(manifest)],
                    }
                },
            )
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-BENCH-001",
                            "severity": "block",
                            "category": "benchmark_result_schema",
                            "source_artifact": "04-benchmark-result-schema-audit.json",
                            "action": "修复 benchmark result schema 和 manifest provenance 后重跑实验。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "04-benchmark-result-schema-audit.json",
                {
                    "status": "block",
                    "execution_mode": "benchmark",
                    "blocking_issues": ["benchmark adapter artifact contract 未闭环"],
                    "manual_tasks": ["核对 manifest provenance。"],
                },
            )
            write_json(run_dir / "03-execution-approval.json", {"approved": True})

            report = prepare_repair_resume(run_dir, apply=True)
            config = AgentConfig(execution=ExecutionConfig(mode="simulated", allowed_commands=["pytest"], repeats=1, timeout_seconds=60))
            updated = apply_repair_resume_recommendations(config, report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertEqual(report["recommended_execution_config"]["execution_mode"], "benchmark")
            self.assertIn(str(manifest), report["recommended_execution_config"]["benchmark_manifest_paths"])
            self.assertTrue(report["execution_reapproval_required"])
            self.assertFalse((run_dir / "03-execution-approval.json").exists())
            self.assertEqual(updated.execution.mode, "benchmark")
            self.assertIn("python3", updated.execution.allowed_commands)
            self.assertIn("pytest", updated.execution.allowed_commands)
            self.assertIn(str(manifest), updated.execution.benchmark_manifest_paths)
            self.assertGreaterEqual(updated.execution.repeats, 3)
            self.assertGreaterEqual(updated.execution.timeout_seconds, 120)
            self.assertIn("推荐下次执行配置", rendered)

    def test_benchmark_repair_resume_carries_paper_grade_repair_suggestions(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "run-config.json", {"paper_grade": {"enabled": True, "min_execution_repeats": 5}})
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-BENCH-PAPER",
                            "severity": "high",
                            "category": "benchmark_evidence",
                            "source_artifact": "04-benchmark-evidence-audit.json",
                            "action": "补齐 paper-grade benchmark manifest 集合后重跑。",
                            "rerun_from": "experiments",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(
                run_dir / "03-benchmark-adapters.json",
                {
                    "status": "ready",
                    "manifest_paths": ["benchmarks/candidate.json"],
                    "paper_grade_status": "review_required",
                    "paper_grade_issues": ["paper-grade benchmark 需要 candidate/baseline/ablation 三类 role：baseline, ablation"],
                    "paper_grade_repair_suggestions": [
                        {
                            "kind": "missing_manifest_role",
                            "role": "baseline",
                            "target": "role:baseline",
                            "target_path_hint": "benchmarks/baseline.json",
                            "action": "新增 baseline manifest。",
                            "manifest_template": {"name": "TODO baseline", "role": "baseline"},
                        },
                        {
                            "kind": "missing_manifest_role",
                            "role": "ablation",
                            "target": "role:ablation",
                            "action": "新增 ablation manifest。",
                        },
                    ],
                },
            )

            report = build_repair_resume_plan(run_dir)
            rendered = render_repair_resume_plan_markdown(report)

            execution = report["recommended_execution_config"]
            self.assertEqual(execution["execution_mode"], "benchmark")
            self.assertEqual(execution["benchmark_paper_grade_status"], "review_required")
            self.assertEqual(len(execution["benchmark_manifest_repair_suggestions"]), 2)
            self.assertEqual(len(execution["benchmark_manifest_scaffolds"]), 2)
            self.assertEqual(execution["benchmark_manifest_scaffolds"][0]["path_hint"], "benchmarks/baseline.json")
            self.assertEqual(execution["benchmark_manifest_scaffolds"][0]["manifest"]["role"], "baseline")
            self.assertEqual(execution["benchmark_manifest_scaffolds"][1]["manifest"]["role"], "ablation")
            self.assertEqual(execution["execution_repeats"], 5)
            self.assertEqual(execution["benchmark_manifest_scaffolds"][1]["manifest"]["min_repeats"], 5)
            self.assertIn("benchmarks/candidate.json", execution["benchmark_manifest_paths"])
            self.assertTrue(report["recommended_paper_grade_config"]["enabled"])
            self.assertIn("paper_grade_benchmark_gate", report["recommended_paper_grade_config"]["reasons"])
            self.assertEqual(report["recommended_paper_grade_config"]["min_execution_repeats"], 5)
            self.assertIn("Benchmark Manifest 修复建议", rendered)
            self.assertIn("Benchmark Manifest Scaffold", rendered)
            self.assertIn("benchmarks/baseline.json", rendered)

    def test_checkpoint_repair_resume_only_clears_runtime_audit_tail(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "12-repair-queue.json",
                {
                    "topic": "机械臂路径规划",
                    "status": "blocked_repair_required",
                    "items": [
                        {
                            "task_id": "RQ-TRACE-001",
                            "severity": "block",
                            "category": "run_economics",
                            "source_artifact": "13-run-economics-audit.json",
                            "action": "修复 LLM ledger 和 token 单价配置后重新生成运行成本审计。",
                            "rerun_from": "checkpoint",
                            "status": "open",
                        }
                    ],
                },
            )
            write_json(run_dir / "01-context.json", {"status": "keep"})
            write_json(run_dir / "02-ideas.json", [{"title": "keep"}])
            write_json(run_dir / "03-experiment-plan.json", {"status": "keep"})
            write_json(run_dir / "04-results.json", [{"status": "keep"}])
            write_text(run_dir / "06-paper.md", "# keep paper")
            write_json(run_dir / "12-next-iteration-plan.json", {"status": "keep"})
            write_json(run_dir / "13-run-economics-audit.json", {"status": "block"})
            write_json(run_dir / "13-agent-observability-audit.json", {"status": "block"})
            write_json(run_dir / "13-research-scorecard.json", {"status": "blocked"})
            write_json(run_dir / "14-run-integrity-audit.json", {"status": "block"})
            write_json(run_dir / "run-diagnostics.json", {"status": "stale"})

            report = prepare_repair_resume(run_dir, apply=True)

            self.assertEqual(report["rerun_from"], "checkpoint")
            self.assertTrue(report["applied"])
            self.assertFalse(report["review_reapproval_required"])
            self.assertFalse(report["execution_reapproval_required"])
            self.assertTrue((run_dir / "01-context.json").exists())
            self.assertTrue((run_dir / "02-ideas.json").exists())
            self.assertTrue((run_dir / "03-experiment-plan.json").exists())
            self.assertTrue((run_dir / "04-results.json").exists())
            self.assertTrue((run_dir / "06-paper.md").exists())
            self.assertTrue((run_dir / "12-next-iteration-plan.json").exists())
            self.assertFalse((run_dir / "12-repair-queue.json").exists())
            self.assertFalse((run_dir / "13-run-economics-audit.json").exists())
            self.assertFalse((run_dir / "13-agent-observability-audit.json").exists())
            self.assertFalse((run_dir / "13-research-scorecard.json").exists())
            self.assertFalse((run_dir / "14-run-integrity-audit.json").exists())
            self.assertFalse((run_dir / "run-diagnostics.json").exists())

    def test_gold_run_doctor_repair_plan_can_drive_resume_when_queue_is_clean(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "candidate"
            run_dir.mkdir()
            write_json(run_dir / "12-repair-queue.json", {"topic": "Iris benchmark smoke", "status": "pass", "items": []})
            write_json(run_dir / "04-benchmark-evidence-audit.json", {"status": "warn"})
            write_json(run_dir / "10-claim-consistency.json", {"status": "stale"})
            write_json(run_dir / "14-final-handoff.json", {"status": "blocked"})
            doctor_report = root / "00-gold-run-doctor.json"
            write_json(
                doctor_report,
                {
                    "status": "blocked",
                    "checks": [
                        {
                            "name": "candidate_gold_run",
                            "status": "fail",
                            "repair_plan": [
                                {
                                    "id": "benchmark_evidence_metadata",
                                    "priority": 35,
                                    "rerun_from": "experiments",
                                    "source_artifact": "04-benchmark-evidence-audit.json",
                                    "target_artifacts": [
                                        "04-benchmark-evidence-audit.json",
                                        "04-claim-boundary-preflight.json",
                                        "10-claim-consistency.json",
                                    ],
                                    "action": "重新生成 benchmark evidence metadata。",
                                },
                                {
                                    "id": "final_handoff",
                                    "priority": 100,
                                    "rerun_from": "checkpoint",
                                    "source_artifact": "14-final-handoff.json",
                                    "target_artifacts": ["14-final-handoff.json"],
                                    "action": "重新生成 final handoff。",
                                },
                            ],
                        }
                    ],
                },
            )

            report = build_repair_resume_plan(run_dir, doctor_report_path=doctor_report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertTrue(report["can_resume"])
            self.assertEqual(report["queue_status"], "pass")
            self.assertEqual(report["repair_plan_sources"], ["12-repair-queue", "gold-run-doctor"])
            self.assertEqual(report["rerun_from"], "experiments")
            task_ids = [item["task_id"] for item in report["repair_items"]]
            self.assertIn("gold-doctor:benchmark_evidence_metadata", task_ids)
            self.assertIn("gold-doctor:final_handoff", task_ids)
            categories = {item["category"] for item in report["repair_items"]}
            self.assertIn("benchmark_evidence", categories)
            self.assertIn("04-benchmark-evidence-audit.json", report["artifacts_to_remove"])
            self.assertIn("10-claim-consistency.json", report["artifacts_to_remove"])
            self.assertEqual(report["recommended_execution_config"]["execution_mode"], "benchmark")
            self.assertEqual(report["recommended_execution_config"]["execution_repeats"], 3)
            self.assertTrue(report["execution_reapproval_required"])
            self.assertIn(f"--gold-run-doctor-report {doctor_report}", report["commands"][0])
            self.assertIn("计划来源：12-repair-queue, gold-run-doctor", rendered)

    def test_gold_run_verification_repair_plan_can_drive_resume_when_queue_is_clean(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "candidate"
            run_dir.mkdir()
            write_json(run_dir / "12-repair-queue.json", {"topic": "Iris benchmark smoke", "status": "pass", "items": []})
            write_json(run_dir / "11-submission-package.json", {"status": "blocked"})
            verification_report = run_dir / "15-gold-run-verification.json"
            write_json(
                verification_report,
                {
                    "status": "blocked",
                    "repair_plan": [
                        {
                            "id": "submission_package",
                            "priority": 70,
                            "rerun_from": "submission_package",
                            "source_artifact": "11-submission-package.json",
                            "target_artifacts": ["11-submission-package.json", "11-submission-package.zip"],
                            "action": "重新生成 submission package。",
                        }
                    ],
                },
            )

            report = build_repair_resume_plan(run_dir, gold_verification_report_path=verification_report)
            rendered = render_repair_resume_plan_markdown(report)

            self.assertTrue(report["can_resume"])
            self.assertEqual(report["repair_plan_sources"], ["12-repair-queue", "gold-run-verification"])
            self.assertEqual(report["rerun_from"], "submission_package")
            self.assertIn("gold-verification:submission_package", [item["task_id"] for item in report["repair_items"]])
            self.assertIn("11-submission-package.json", report["artifacts_to_remove"])
            self.assertIn(f"--gold-run-verification-report {verification_report}", report["commands"][0])
            self.assertIn("计划来源：12-repair-queue, gold-run-verification", rendered)

    def test_pipeline_ignores_unapplied_repair_context(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(
                run_dir / "12-repair-resume-plan.json",
                {
                    "applied": False,
                    "repair_context": {"prompt_text": "stale context must not leak"},
                },
            )

            self.assertEqual(_repair_resume_context(run_dir), "")

    def test_missing_or_clean_queue_cannot_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            missing = build_repair_resume_plan(run_dir)
            self.assertFalse(missing["can_resume"])

            write_json(run_dir / "12-repair-queue.json", {"topic": "测试", "status": "pass", "items": []})
            clean = build_repair_resume_plan(run_dir)

            self.assertFalse(clean["can_resume"])
            self.assertEqual(clean["status"], "nothing_to_repair")


def _write_queue(run_dir: Path, rerun_from: str) -> None:
    write_json(
        run_dir / "12-repair-queue.json",
        {
            "topic": "机械臂路径规划",
            "status": "blocked_repair_required",
            "items": [
                {
                    "task_id": "RQ-001",
                    "severity": "block",
                    "category": "repair",
                    "source_artifact": "04-result-validation.json",
                    "action": "重跑修复项",
                    "rerun_from": rerun_from,
                    "status": "open",
                }
            ],
        },
    )


if __name__ == "__main__":
    unittest.main()
