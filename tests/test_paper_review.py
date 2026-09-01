from __future__ import annotations

import json
import unittest

from research_agent.models import (
    Analysis,
    ClaimTraceabilityReport,
    CodeDataAvailabilityReport,
    ExperimentCommand,
    ExperimentPlan,
    PaperClaimAudit,
    PaperRewriteReport,
    PaperReview,
    LiteratureReview,
    Paper,
    PaperRevisionPlan,
    ResearchIdea,
    RevisionTask,
    SubmissionCheckReport,
)
from research_agent.final_readiness import build_final_readiness_report, render_final_readiness_markdown
from research_agent.paper_review import _paper_review_excerpt, _review_prompt, render_paper_review_markdown, review_paper_draft
from research_agent.paper_revision import build_paper_revision_plan, render_paper_revision_plan_markdown
from research_agent.paper_rewrite import _benchmark_scope_mismatch, _rewrite_prompt, render_rewrite_report_markdown, revise_paper_draft


class ContextOnlyUnsupportedReviewLLM:
    def __init__(self) -> None:
        self.user_prompt = ""

    def complete(self, system: str, user: str) -> str:
        self.user_prompt = user
        return json.dumps(
            {
                "decision": "revise",
                "score": 7.0,
                "novelty": 3,
                "soundness": 3,
                "evidence_quality": 3,
                "reproducibility": 3,
                "summary": "草稿范围较窄，但未把旧计划目标写成已验证结论。",
                "strengths": ["明确写出当前 run 的边界。"],
                "weaknesses": ["仍需扩展更多 benchmark。"],
                "required_revisions": ["保持范围声明。"],
                "claim_audit": [
                    {
                        "claim": "统一 Iris smoke benchmark 协议能降低重复运行、不同机器和 CI 环境中的结果方差。",
                        "support_level": "unsupported",
                        "evidence_keys": [],
                        "result_refs": [],
                        "risk": "high",
                    }
                ],
            },
            ensure_ascii=False,
        )


class SparseRevisionLLM:
    def complete(self, system: str, user: str) -> str:
        return "\n".join(
            [
                "# Iris 修订稿",
                "",
                "## 摘要",
                "本文只报告当前 evidence_grade=real_benchmark 的 adapter 运行记录，不声称模型优劣或协议稳定性。",
                "",
                "## 方法",
                "方法限定为当前单环境、单 frozen split 的 smoke run。",
                "",
                "## 结果",
                "结果仅用于描述当前 runbook 中可复核的执行记录。",
                "",
                "## 局限性",
                "外部复现、更多 baseline 和稳定性结论均待后续补证。",
                "",
                "## 9. 修订执行记录",
                "| 任务 | 处理状态 |",
                "| --- | --- |",
                "| R01 | 已处理。 |",
            ]
        )


class PaperReviewTest(unittest.TestCase):
    def test_review_prompt_is_compacted_for_long_revised_papers(self) -> None:
        review, idea, plan, analysis = _sample_review_inputs()

        prompt = _review_prompt(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            "# 长稿\n\n" + ("结果来自真实 benchmark adapter，而不是 dry-run。正文。" * 1000),
            None,
        )

        self.assertLess(len(prompt), 11000)
        self.assertIn("claim_audit 各最多 8 条", prompt)
        self.assertIn("claim_audit 只能记录论文草稿正文实际断言", prompt)
        self.assertIn("系统节选说明", prompt)
        self.assertIn("不得把它列为稿件中段省略", prompt)
        self.assertNotIn("原稿中段省略", prompt)

    def test_review_excerpt_does_not_cut_artifact_names_mid_token(self) -> None:
        paper = (
            "# 长稿\n\n"
            + ("背景句。" * 80)
            + "实验性表述只来自 04-experiment-runbook、04-results 和 04-statistics。"
            + "\n\n完整 per-repeat 结果表：\n| Role | Repeat | Accuracy |\n| candidate | 0 | 0.966667 |\n"
            + ("后续句。" * 80)
        )

        excerpt = _paper_review_excerpt(paper, limit=220)

        self.assertNotIn("04-ex", excerpt.replace("04-experiment", ""))
        self.assertFalse(excerpt.endswith("04-ex"))

    def test_ai_review_filters_context_only_unsupported_plan_claims(self) -> None:
        review, idea, plan, analysis = _sample_review_inputs()
        llm = ContextOnlyUnsupportedReviewLLM()
        paper = "\n".join(
            [
                "# Iris 三角色 Benchmark Adapter Smoke Run 报告",
                "",
                "本文只记录同一 UCI Iris 数据、同一 stratified split、同一运行环境和三次重复下的执行一致性检查。",
                "跨机器/CI 方差、故障注入检测率和更大任务族泛化不是本次已检验结果。",
                "结果显示 04-results.json 与 04-statistics.json 已记录 candidate、baseline 和 ablation 的描述性指标。",
            ]
        )

        result = review_paper_draft("Iris classification benchmark smoke", review, [idea], plan, analysis, paper, llm=llm)

        self.assertIn("claim_audit 只能记录论文草稿正文实际断言", llm.user_prompt)
        self.assertFalse(any(item.support_level == "unsupported" for item in result.claim_audit))
        self.assertFalse(any("不同机器" in item.claim and item.support_level == "unsupported" for item in result.claim_audit))

    def test_final_readiness_treats_release_and_format_tasks_as_manual_after_clean_review(self) -> None:
        original = PaperReview(
            decision="major_revision",
            score=4.0,
            novelty=2,
            soundness=2,
            evidence_quality=2,
            reproducibility=3,
            summary="原稿需修。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[PaperClaimAudit("旧 unsupported claim", "unsupported", [], [], "high")],
        )
        revised = PaperReview(
            decision="accept_with_minor_revisions",
            score=8.0,
            novelty=4,
            soundness=4,
            evidence_quality=4,
            reproducibility=4,
            summary="已收敛。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        rewrite = PaperRewriteReport(
            topic="Iris",
            source_paper="06-paper.md",
            revised_paper="09-revised-paper.md",
            revision_plan="08-revision-plan.json",
            summary="已修订。",
            task_results=[],
            deferred_tasks=["R01: old task now closed by revised review"],
            next_checks=[],
        )
        availability = CodeDataAvailabilityReport(
            topic="Iris",
            status="needs_human_release_metadata",
            ready_for_internal_release=True,
            ready_for_submission_check=False,
            checks=[],
            blocking_issues=[],
            manual_tasks=["补 DOI"],
            code_statement="code",
            data_statement="data",
            reproduction_statement="run",
        )
        submission = SubmissionCheckReport(
            topic="Iris",
            target_venue="workshop",
            status="needs_human_format_check",
            checks=[],
            blocking_issues=[],
            manual_tasks=["套模板"],
            recommended_actions=[],
        )
        traceability = ClaimTraceabilityReport(
            topic="Iris",
            status="pass",
            traceability_score=1.0,
            total_claims=1,
            passed_claims=1,
            review_claims=0,
            blocked_claims=0,
            items=[],
            blocking_issues=[],
            manual_tasks=[],
            evidence_inventory={},
        )

        readiness = build_final_readiness_report("Iris", original, revised, rewrite, availability, submission, traceability)

        self.assertEqual(readiness.status, "ready_for_submission_check")
        self.assertFalse(readiness.blocking_issues)
        self.assertEqual(readiness.availability_manual_tasks, ["补 DOI"])
        self.assertEqual(readiness.submission_manual_tasks, ["套模板"])

    def test_final_readiness_low_score_without_weak_claims_uses_score_action(self) -> None:
        original = PaperReview(
            decision="major_revision",
            score=8.0,
            novelty=4,
            soundness=4,
            evidence_quality=4,
            reproducibility=4,
            summary="原始复核。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        revised = PaperReview(
            decision="revise",
            score=6.0,
            novelty=3,
            soundness=3,
            evidence_quality=3,
            reproducibility=3,
            summary="分数不足但 claim audit 干净。",
            strengths=[],
            weaknesses=["贡献边界仍需收窄。"],
            required_revisions=["补充限制。"],
            claim_audit=[],
        )
        rewrite = PaperRewriteReport(
            topic="Iris",
            source_paper="06-paper.md",
            revised_paper="09-revised-paper.md",
            revision_plan="08-revision-plan.json",
            summary="已修订。",
            task_results=[],
            deferred_tasks=[],
            next_checks=[],
        )

        readiness = build_final_readiness_report("Iris", original, revised, rewrite)

        self.assertEqual(readiness.status, "requires_revision")
        self.assertTrue(any("复核分数" in action for action in readiness.next_actions))
        self.assertFalse(any("unsupported=0, weak=0" in action for action in readiness.next_actions))

    def test_real_benchmark_scope_mismatch_ignores_negated_dry_run_language(self) -> None:
        evidence = {"evidence_grade": "real_benchmark"}

        self.assertFalse(_benchmark_scope_mismatch("结果来自真实 benchmark adapter，而不是 dry-run、scaffold 或模拟替代。", evidence))
        self.assertTrue(_benchmark_scope_mismatch("当前结果只能视为 dry-run/scaffold 记录。", evidence))

    def test_rewrite_prompt_is_compacted_for_large_revision_plans(self) -> None:
        review = PaperReview(
            decision="major_revision",
            score=4.0,
            novelty=2,
            soundness=2,
            evidence_quality=2,
            reproducibility=3,
            summary="需要大修。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        plan = PaperRevisionPlan(
            topic="Iris",
            decision="major_revision",
            readiness="major_revision_required",
            summary="很多任务。",
            tasks=[
                RevisionTask(
                    task_id=f"R{index:02d}",
                    section="Experiments/Results",
                    severity="high" if index < 20 else "medium",
                    issue=("需要修复 very long issue " + str(index) + "。") * 40,
                    action=("需要采取 very long action " + str(index) + "。") * 30,
                    evidence_refs=["04-results.json", "04-statistics.json"],
                )
                for index in range(40)
            ],
            acceptance_checks=[],
            next_iteration_prompt="修订。",
        )

        prompt = _rewrite_prompt("Iris", "# 原稿\n\n" + ("正文。" * 5000), plan, review, {"evidence_grade": "real_benchmark"})

        self.assertLess(len(prompt), 9000)
        self.assertIn("原始修订任务数：40", prompt)
        self.assertIn("全部任务 ID：R00, R01", prompt)
        self.assertIn("R-remaining", prompt)
        self.assertIn("omitted_task_ids", prompt)

    def test_review_generates_claim_audit_and_revisions(self) -> None:
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[
                Paper(
                    title="Robot manipulator motion planning with obstacle avoidance",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="arXiv",
                    url="https://example.test",
                    abstract="Obstacle avoidance and robot manipulator motion planning.",
                    relevance=0.9,
                    doi="10.1234/example",
                )
            ],
            themes=["机械臂路径规划需要避障。"],
            gaps=["需要可复现 benchmark。"],
            summary="测试综述",
        )
        idea = ResearchIdea(
            title="机械臂避障 benchmark",
            hypothesis="系统化 benchmark 可以更稳定地评价机械臂避障规划。",
            mechanism="比较 proposed、baseline 和消融版本。",
            expected_contribution="提供可复现实验协议。",
            novelty=4,
            feasibility=4,
            risk=3,
            evaluation=["success_rate", "collision_rate"],
            evidence_keys=["lovelace2024robot1"],
            evidence_chunks=["chunk-001"],
        )
        plan = ExperimentPlan(
            idea_title=idea.title,
            objective="验证 benchmark 的区分能力。",
            variables=["方法条件", "障碍复杂度"],
            metrics=["success_rate", "collision_rate"],
            protocol=["构建任务", "运行 baseline", "运行 proposed"],
            commands=[ExperimentCommand(name="simulate_artifact_pipeline", command=["python3", "simulate.py"])],
            baseline="RRT baseline",
            evidence_keys=["lovelace2024robot1"],
        )
        analysis = Analysis(
            headline="proposed 在 success_rate 上高于 baseline。",
            metric_table=[{"name": "simulate_artifact_pipeline", "status": "simulated", "success_rate": 0.8}],
            findings=["success_rate 提高。"],
            limitations=["模拟实验。"],
            next_steps=["真实 benchmark。"],
        )

        result = review_paper_draft(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            "# 机械臂避障 benchmark\n\n本文提出可复现 benchmark。结果显示 success_rate 提高。",
        )
        rendered = render_paper_review_markdown(result)
        revision_plan = build_paper_revision_plan(
            "机械臂路径规划",
            result,
            experiment_decision={"status": "warn", "decision": "pivot_or_refine", "next_actions": ["报告负结果"], "claim_boundaries": ["负结果必须作为发现报告。"]},
        )
        rendered_revision_plan = render_paper_revision_plan_markdown(revision_plan)
        revised_paper, rewrite_report = revise_paper_draft(
            "机械臂路径规划",
            "# 草稿\n\n## 摘要\n本文证明了方法有效。\n\n## 方法\n待补。\n\n## 结果\n结果显示 success_rate 提高。\n\n## 局限性\n模拟实验。\n\n## 结论\n本文证明了该方法优于 baseline。",
            revision_plan,
            result,
        )
        rendered_rewrite_report = render_rewrite_report_markdown(rewrite_report)

        self.assertTrue(result.claim_audit)
        self.assertTrue(result.required_revisions)
        self.assertIn("Claim-Grounding", rendered)
        self.assertTrue(revision_plan.tasks)
        self.assertTrue(any("pivot_or_refine" in task.issue for task in revision_plan.tasks))
        self.assertIn("验收检查", rendered_revision_plan)
        self.assertIn("下一轮修改提示", rendered_revision_plan)
        self.assertIn("修订执行记录", revised_paper)
        self.assertIn("任务处理", rendered_rewrite_report)
        self.assertEqual(rewrite_report.source_paper, "06-paper.md")

        blocked_plan = PaperRevisionPlan(
            topic="机械臂路径规划",
            decision="major_revision",
            readiness="major_revision_required",
            summary="存在未支撑 claim。",
            tasks=[
                RevisionTask(
                    task_id="R99",
                    section="Claim-Grounding",
                    severity="high",
                    issue="unsupported claim：本文证明了方法在真实场景中最优。",
                    action="补充直接支撑该 claim 的文献或实验结果。",
                    evidence_refs=[],
                )
            ],
            acceptance_checks=["unsupported claim 已补证、删除或降级。"],
            next_iteration_prompt="补证。",
        )
        _, blocked_report = revise_paper_draft("机械臂路径规划", "# 草稿\n\n## 摘要\n待修订。", blocked_plan, result)
        self.assertEqual(blocked_report.task_results[0].status, "needs_human_evidence")

        real_benchmark_revised, _ = revise_paper_draft(
            "机械臂路径规划",
            "# 草稿\n\n## 摘要\n初步模拟结果。\n\n## 方法\n待补。\n\n## 结果\n模拟结果显示 success_rate 提高。\n\n## 局限性\n仍需真实 benchmark。\n\n## 结论\n模拟实验不能替代真实 benchmark 结果。",
            revision_plan,
            result,
            benchmark_evidence={"status": "pass", "evidence_grade": "real_benchmark"},
        )
        self.assertIn("benchmark adapter 结果", real_benchmark_revised)
        self.assertNotIn("模拟结果", real_benchmark_revised)

        scoped_revised, _ = revise_paper_draft(
            "Iris",
            "# 草稿\n\n## 摘要\n固定协议后，结果方差在不同机器和不同 CI 环境中显著降低，并能稳定暴露管线错误。\n\n## 方法\n待补。\n\n## 结果\ncandidate 在 accuracy 上优于 baseline。\n\n## 局限性\n待补。\n\n## 结论\n该套件能以极低运行成本提供比单一高精度模型更可靠的 smoke benchmark 诊断信号。",
            revision_plan,
            result,
            benchmark_evidence={"status": "warn", "evidence_grade": "real_benchmark"},
        )
        self.assertIn("跨机器/CI 方差和故障注入检测率未检验", scoped_revised)
        self.assertIn("诊断可靠性尚需更多 baseline 和故障注入实验", scoped_revised)
        self.assertNotIn("显著降低", scoped_revised)
        self.assertNotIn("稳定暴露管线错误", scoped_revised)
        self.assertNotIn("优于 baseline", scoped_revised)

        revised_review = PaperReview(
            decision="major_revision",
            score=5.5,
            novelty=3,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="仍需补证。",
            strengths=[],
            weaknesses=["仍有未支撑 claim。"],
            required_revisions=["补证。"],
            claim_audit=[
                PaperClaimAudit(
                    claim="本文证明了方法在真实场景中最优。",
                    support_level="unsupported",
                    evidence_keys=[],
                    result_refs=[],
                    risk="high",
                )
            ],
        )
        readiness = build_final_readiness_report("机械臂路径规划", result, revised_review, blocked_report)
        rendered_readiness = render_final_readiness_markdown(readiness)
        self.assertEqual(readiness.status, "requires_human_evidence")
        self.assertIn("最终就绪报告", rendered_readiness)
        self.assertTrue(readiness.blocking_issues)

    def test_rewrite_report_closes_deleted_or_scoped_unsupported_claim_tasks(self) -> None:
        review = PaperReview(
            decision="major_revision",
            score=5.0,
            novelty=3,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="需要降级。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        revision_plan = PaperRevisionPlan(
            topic="Iris",
            decision="major_revision",
            readiness="major_revision_required",
            summary="降级越界 claim。",
            tasks=[
                RevisionTask(
                    task_id="R01",
                    section="Claim-Grounding",
                    severity="high",
                    issue="unsupported claim：统一 Iris smoke benchmark 能稳定暴露管线错误。",
                    action="补证；如果无法补证，删除该 claim 或改写为明确的局限/假设。",
                    evidence_refs=[],
                )
            ],
            acceptance_checks=[],
            next_iteration_prompt="继续。",
        )
        paper = "# Iris\n\n## 结果边界\n故障注入检测率不是本次已检验结果。\n"

        revised, report = revise_paper_draft("Iris", paper, revision_plan, review, benchmark_evidence={"evidence_grade": "real_benchmark"})

        self.assertIn("修订执行记录", revised)
        self.assertFalse(report.deferred_tasks)
        self.assertEqual(report.task_results[0].status, "applied_in_draft")

    def test_rewrite_keeps_task_traces_when_ai_omits_compacted_ids(self) -> None:
        review = PaperReview(
            decision="major_revision",
            score=5.0,
            novelty=3,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="需要修订。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        revision_plan = PaperRevisionPlan(
            topic="Iris",
            decision="major_revision",
            readiness="major_revision_required",
            summary="保留任务闭环。",
            tasks=[
                RevisionTask("R01", "Claim-Grounding", "medium", "收窄强结论。", "降级表述。", []),
                RevisionTask("R02", "Experiments/Results", "medium", "补充结果边界。", "在修订记录中说明状态。", ["04-results.json"]),
            ],
            acceptance_checks=[],
            next_iteration_prompt="继续。",
        )

        revised, _ = revise_paper_draft("Iris", "# 原稿\n\n## 摘要\n待修订。", revision_plan, review, SparseRevisionLLM())

        self.assertIn("## 9. 修订执行记录", revised)
        self.assertIn("自动补全任务闭环索引", revised)
        self.assertIn("| R02 |", revised)

    def test_rewrite_report_closes_generic_real_benchmark_boundary_tasks(self) -> None:
        review = PaperReview(
            decision="major_revision",
            score=5.0,
            novelty=3,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="需要边界化。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        revision_plan = PaperRevisionPlan(
            topic="Iris",
            decision="major_revision",
            readiness="major_revision_required",
            summary="补齐边界。",
            tasks=[
                RevisionTask(
                    task_id="R01",
                    section="Claim-Grounding",
                    severity="high",
                    issue="把所有高风险或弱支撑 claim 改写为文献和实验结果能直接支持的范围。",
                    action="逐条检查对应 claim，无法补证时删除或降级表述。",
                    evidence_refs=[],
                ),
                RevisionTask(
                    task_id="R02",
                    section="Experiments/Results",
                    severity="medium",
                    issue="在结果段落中明确区分模拟结果、真实实验结果和推测性解释。",
                    action="补齐实验设置、baseline、重复次数、统计检验和结果边界。",
                    evidence_refs=[],
                ),
                RevisionTask(
                    task_id="R03",
                    section="Experiments/Results",
                    severity="medium",
                    issue="实验后决策为 pivot_or_refine；把负向指标作为结果报告。",
                    action="在结果和结论中报告负结果，明确是否 pivot 或 refine。",
                    evidence_refs=["04-experiment-decision"],
                ),
            ],
            acceptance_checks=[],
            next_iteration_prompt="继续。",
        )
        paper = "\n".join(
            [
                "# Iris",
                "",
                "## 摘要",
                "evidence_grade=real_benchmark，结果来自 04-experiment-runbook 和 04-results，不是 dry-run、scaffold 或模拟替代。",
                "",
                "## 结果",
                "完整 per-repeat 结果表显示 accuracy 差值=0.000；candidate 与 baseline 数值相同，不支持显著性或稳定性结论。",
                "",
                "## 结果边界",
                "负结果必须作为发现报告；当前结论按 pivot_or_refine 处理。",
                "",
                "## Claim 边界预检",
                "禁止外推到未检验任务。",
                "",
                "## 可审计产物摘要",
                "04-results.json 与 04-experiment-runbook.json 保留完整证据链。",
            ]
        )

        _, report = revise_paper_draft("Iris", paper, revision_plan, review, benchmark_evidence={"evidence_grade": "real_benchmark"})

        self.assertFalse(report.deferred_tasks)
        self.assertEqual({item.status for item in report.task_results}, {"applied_in_draft"})

    def test_rewrite_report_closes_equivalent_gold_smoke_boundary_phrasing(self) -> None:
        review = PaperReview(
            decision="major_revision",
            score=5.0,
            novelty=3,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="需要边界化。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        revision_plan = PaperRevisionPlan(
            topic="Iris",
            decision="major_revision",
            readiness="major_revision_required",
            summary="补齐边界。",
            tasks=[
                RevisionTask(
                    task_id="R02",
                    section="Experiments/Results",
                    severity="high",
                    issue="统一实验目标、方法列表和正文结果：若实际 run 使用 nearest_centroid/knn3/sepal_centroid，应将论文标题、方法和结论改为该 adapter smoke run。",
                    action="补齐实验设置、baseline、重复次数、统计检验和结果边界。",
                    evidence_refs=[],
                ),
                RevisionTask(
                    task_id="R04",
                    section="Experiments/Results",
                    severity="high",
                    issue="将所有结果结论限定为单环境、单 frozen split、三次执行一致性检查，删除协议有效性或模型优劣表述。",
                    action="补齐实验设置、baseline、重复次数、统计检验和结果边界。",
                    evidence_refs=[],
                ),
                RevisionTask(
                    task_id="R10",
                    section="Experiments/Results",
                    severity="medium",
                    issue="实验后决策为 pivot_or_refine；把负向指标作为结果报告。",
                    action="在结果和结论中报告负结果，明确是否 pivot 或 refine。",
                    evidence_refs=["04-experiment-decision"],
                ),
            ],
            acceptance_checks=[],
            next_iteration_prompt="继续。",
        )
        paper = "\n".join(
            [
                "# Iris Classification Benchmark Smoke",
                "",
                "## 摘要",
                "根据证据审计，本次产物标记为 `evidence_grade=real_benchmark`，benchmark adapter/runbook 已实际执行，并留下 runbook、results 和 statistics；本文不得将其写作 dry-run、scaffold 或模拟实验。实验范围限定为单环境、单 frozen split、三次执行一致性检查。nearest_centroid candidate 与 knn3 baseline 的 accuracy 观测差值为 0.000，该结果不构成模型优劣或协议稳定性证据。",
                "",
                "## 方法",
                "adapter variants 包括 nearest_centroid、knn3 和 sepal-centroid；Dummy stratified 未作为当前结果表中的已完成比较项。",
                "",
                "## 结果",
                "三次重复中未观察到 candidate 与 baseline 的数值差异，不支持显著性或模型优越性结论。",
                "",
                "## 证据边界",
                "当前观察只支持有限范围内的执行一致性描述，不能推断外部稳定性。",
            ]
        )

        _, report = revise_paper_draft("Iris", paper, revision_plan, review, benchmark_evidence={"evidence_grade": "real_benchmark"})

        self.assertFalse(report.deferred_tasks)
        self.assertEqual({item.status for item in report.task_results}, {"applied_in_draft"})

    def test_rewrite_report_closes_artifact_availability_task_when_index_present(self) -> None:
        review = PaperReview(
            decision="major_revision",
            score=5.0,
            novelty=3,
            soundness=3,
            evidence_quality=2,
            reproducibility=3,
            summary="需要 artifact availability。",
            strengths=[],
            weaknesses=[],
            required_revisions=[],
            claim_audit=[],
        )
        revision_plan = PaperRevisionPlan(
            topic="Iris",
            decision="major_revision",
            readiness="major_revision_required",
            summary="补齐 artifact。",
            tasks=[
                RevisionTask(
                    task_id="R02",
                    section="Methods/Reproducibility",
                    severity="high",
                    issue="公开或附录列出 04-experiment-runbook、04-results、04-statistics、manifest schema、环境快照和完整 metrics JSON，否则删除或降级与内部产物审计相关的强主张。",
                    action="补充 artifact availability，逐项列出 runbook/results/statistics/schema/environment/metrics JSON。",
                    evidence_refs=[],
                )
            ],
            acceptance_checks=[],
            next_iteration_prompt="继续。",
        )
        paper = "\n".join(
            [
                "# Iris",
                "",
                "## Artifact 索引",
                "- `04-experiment-runbook.json`：adapter 命令、seed 和 SHA256。",
                "- `04-results.json` / `04-results.csv`：per-repeat 指标。",
                "- `04-statistics.json` / `04-statistics.md`：描述性比较。",
                "- `04-benchmark-result-schema-audit.json`：manifest schema 和字段一致性审计。",
                "- `04-environment-snapshot.json`：环境快照。",
                "- `benchmark-adapters/*/*_metrics.json`：完整 metrics.json 产物。",
            ]
        )

        _, report = revise_paper_draft("Iris", paper, revision_plan, review, benchmark_evidence={"evidence_grade": "real_benchmark"})

        self.assertFalse(report.deferred_tasks)
        self.assertEqual(report.task_results[0].status, "applied_in_draft")


def _sample_review_inputs() -> tuple[LiteratureReview, ResearchIdea, ExperimentPlan, Analysis]:
    review = LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="Robot manipulator motion planning with obstacle avoidance",
                authors=["Ada Lovelace"],
                year=2024,
                venue="arXiv",
                url="https://example.test",
                abstract="Obstacle avoidance and robot manipulator motion planning.",
                relevance=0.9,
                doi="10.1234/example",
            )
        ],
        themes=["机械臂路径规划需要避障。"],
        gaps=["需要可复现 benchmark。"],
        summary="测试综述",
    )
    idea = ResearchIdea(
        title="机械臂避障 benchmark",
        hypothesis="系统化 benchmark 可以更稳定地评价机械臂避障规划。",
        mechanism="比较 proposed、baseline 和消融版本。",
        expected_contribution="提供可复现实验协议。",
        novelty=4,
        feasibility=4,
        risk=3,
        evaluation=["success_rate", "collision_rate"],
        evidence_keys=["lovelace2024robot1"],
        evidence_chunks=["chunk-001"],
    )
    plan = ExperimentPlan(
        idea_title=idea.title,
        objective="验证 benchmark 的区分能力。",
        variables=["方法条件", "障碍复杂度"],
        metrics=["success_rate", "collision_rate"],
        protocol=["构建任务", "运行 baseline", "运行 proposed"],
        commands=[ExperimentCommand(name="simulate_artifact_pipeline", command=["python3", "simulate.py"])],
        baseline="RRT baseline",
        evidence_keys=["lovelace2024robot1"],
    )
    analysis = Analysis(
        headline="proposed 在 success_rate 上高于 baseline。",
        metric_table=[{"name": "simulate_artifact_pipeline", "status": "simulated", "success_rate": 0.8}],
        findings=["success_rate 提高。"],
        limitations=["模拟实验。"],
        next_steps=["真实 benchmark。"],
    )
    return review, idea, plan, analysis


if __name__ == "__main__":
    unittest.main()
