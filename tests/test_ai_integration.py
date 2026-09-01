from __future__ import annotations

import unittest

from research_agent.config import IdeationConfig, LiteratureConfig, PaperConfig
from research_agent.experiments import plan_experiment
from research_agent.ideation import generate_ideas
from research_agent.literature import run_literature_review
from research_agent.literature_context import build_literature_context
from research_agent.models import (
    Analysis,
    ExperimentCommand,
    ExperimentPlan,
    LiteratureReview,
    Paper,
    PaperClaimAudit,
    PaperReview,
    PaperRevisionPlan,
    ResearchIdea,
    RevisionTask,
)
from research_agent.paper_review import review_paper_draft
from research_agent.paper_rewrite import revise_paper_draft
from research_agent.research_plan import build_research_plan
from research_agent.web_server import _config_from_payload, _public_config
from research_agent.writing import write_paper_markdown


class JsonLLM:
    def complete(self, system: str, user: str) -> str:
        if "Literature synthesis" in system:
            return '{"summary":"AI 生成的文献综述。","themes":["AI 主题一"],"gaps":["AI 空白一"]}'
        if "Research ideas" in system:
            return '{"ideas":[{"title":"AI 生成 Idea","hypothesis":"AI 生成的可检验假设。","mechanism":"使用文献证据约束规划器生成实验。","expected_contribution":"形成真实 AI 驱动的科研 agent 第一阶段。","novelty":5,"feasibility":4,"risk":2,"evaluation":["引用覆盖率","综述一致性","人工审核耗时"]}]}'
        return ""


class FailingLLM:
    def complete(self, system: str, user: str) -> str:
        raise TimeoutError("timed out")


def _sample_review() -> LiteratureReview:
    return LiteratureReview(
        topic="机械臂路径规划",
        papers=[
            Paper(
                title="Robot manipulator motion planning with obstacle avoidance",
                authors=["Ada Lovelace"],
                year=2024,
                venue="arXiv",
                url="https://arxiv.org/abs/0000.00001",
                abstract="This paper studies robot manipulator motion planning and obstacle avoidance.",
                relevance=0.9,
                source="arxiv",
                sources=["arxiv"],
                doi="10.1234/example",
            )
        ],
        themes=["机械臂路径规划需要避障和轨迹连续性。"],
        gaps=["需要可复现 benchmark。"],
        summary="测试综述",
        evidence_table=[{"title": "Robot manipulator motion planning with obstacle avoidance", "year": 2024, "sources": "arxiv"}],
    )


def _sample_idea() -> ResearchIdea:
    return ResearchIdea(
        title="避障路径规划验证",
        hypothesis="候选规划器可以在复杂障碍场景中提高规划成功率。",
        mechanism="结合采样式规划和轨迹平滑约束。",
        expected_contribution="提供机械臂路径规划的可复现实验起点。",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=["planning_success_rate", "planning_time", "path_length"],
        evidence_keys=["robot_2024"],
        baseline="RRT*",
    )


def _sample_plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="避障路径规划验证",
        objective="比较候选规划器与 RRT* 的规划成功率。",
        variables=["方法", "障碍密度"],
        metrics=["planning_success_rate", "planning_time"],
        protocol=["固定起终位姿", "运行候选方案和 baseline", "统计重复试验结果"],
        commands=[ExperimentCommand(name="simulate", command=["python3", "simulate.py"])],
        baseline="RRT*",
        evidence_keys=["robot_2024"],
    )


def _sample_analysis() -> Analysis:
    return Analysis(
        headline="候选方案在模拟实验中取得更高成功率。",
        metric_table=[{"name": "planning_success_rate", "candidate": 0.82, "baseline": 0.74}],
        findings=["成功率高于 baseline。"],
        limitations=["当前仍是模拟实验。"],
        next_steps=["接入真实 benchmark。"],
    )


def _sample_paper_review() -> PaperReview:
    return PaperReview(
        decision="revise",
        score=6.0,
        novelty=3,
        soundness=3,
        evidence_quality=3,
        reproducibility=3,
        summary="需要补充证据。",
        strengths=["结构完整。"],
        weaknesses=["证据不足。"],
        required_revisions=["降低强结论。"],
        claim_audit=[PaperClaimAudit(claim="候选方案提高成功率", support_level="weak", evidence_keys=["robot_2024"], result_refs=["planning_success_rate"], risk="medium")],
    )


def _sample_revision_plan() -> PaperRevisionPlan:
    return PaperRevisionPlan(
        topic="机械臂路径规划",
        decision="revise",
        readiness="blocked",
        summary="需要修订。",
        tasks=[RevisionTask(task_id="R1", section="结果", severity="medium", issue="强结论需要降级", action="降级表述", evidence_refs=["planning_success_rate"])],
        acceptance_checks=["确认没有新增未验证证据。"],
        next_iteration_prompt="补充真实 benchmark。",
    )


class AIIntegrationTest(unittest.TestCase):
    def test_literature_review_uses_llm_json(self) -> None:
        review = run_literature_review(
            "AI 科研 agent",
            LiteratureConfig(provider="offline", max_papers=2),
            JsonLLM(),
        )

        self.assertEqual(review.summary, "AI 生成的文献综述。")
        self.assertEqual(review.themes, ["AI 主题一"])
        self.assertEqual(review.gaps, ["AI 空白一"])

    def test_ideation_uses_llm_json(self) -> None:
        review = LiteratureReview(
            topic="AI 科研 agent",
            papers=[
                Paper(
                    title="Tool agents",
                    authors=[],
                    year=2024,
                    venue="arXiv",
                    url="https://example.test",
                    abstract="",
                    relevance=0.7,
                    source="offline",
                    sources=["offline"],
                )
            ],
            themes=["主题"],
            gaps=["空白"],
            summary="综述",
            evidence_table=[{"title": "Tool agents", "year": 2024, "sources": "offline"}],
        )

        ideas = generate_ideas(review, IdeationConfig(max_ideas=1), JsonLLM())

        self.assertEqual(ideas[0].title, "AI 生成 Idea")
        self.assertEqual(ideas[0].novelty, 5)
        self.assertIn("引用覆盖率", ideas[0].evaluation)

    def test_ideation_and_plan_are_grounded_in_context(self) -> None:
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[
                Paper(
                    title="Robot manipulator motion planning with obstacle avoidance",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="arXiv",
                    url="https://arxiv.org/abs/0000.00001",
                    abstract="This paper studies robot manipulator motion planning and obstacle avoidance using sampling based planning.",
                    relevance=0.9,
                    source="arxiv",
                    sources=["arxiv"],
                    doi="10.1234/example",
                )
            ],
            themes=["机械臂路径规划需要避障和轨迹连续性。"],
            gaps=["需要可复现 benchmark。"],
            summary="测试综述",
        )
        context = build_literature_context(review)

        ideas = generate_ideas(review, IdeationConfig(max_ideas=1), JsonLLM(), context)
        plan = plan_experiment(ideas[0], context, JsonLLM())

        self.assertTrue(ideas[0].evidence_keys)
        self.assertTrue(ideas[0].evidence_chunks)
        self.assertTrue(plan.metrics)
        self.assertTrue(plan.evidence_keys)

    def test_llm_call_failures_are_not_replaced_by_rule_fallbacks(self) -> None:
        review = _sample_review()
        idea = _sample_idea()
        plan = _sample_plan()
        analysis = _sample_analysis()
        paper_md = "# 摘要\n\n本文提出机械臂路径规划验证。\n\n## 方法\n\n使用候选方法。\n\n## 结果\n\n结果待验证。\n\n## 局限性\n\n仍需真实实验。\n\n## 结论\n\n当前结论有限。"

        cases = [
            ("research_plan", lambda: build_research_plan("机械臂路径规划", FailingLLM())),
            ("literature", lambda: run_literature_review("机械臂路径规划", LiteratureConfig(provider="offline", max_papers=2), FailingLLM())),
            ("ideas", lambda: generate_ideas(review, IdeationConfig(max_ideas=1), FailingLLM())),
            ("experiment_plan", lambda: plan_experiment(idea, llm=FailingLLM())),
            ("paper", lambda: write_paper_markdown("机械臂路径规划", review, [idea], plan, analysis, PaperConfig(), FailingLLM())),
            ("paper_review", lambda: review_paper_draft("机械臂路径规划", review, [idea], plan, analysis, paper_md, llm=FailingLLM())),
            ("paper_rewrite", lambda: revise_paper_draft("机械臂路径规划", paper_md, _sample_revision_plan(), _sample_paper_review(), FailingLLM())),
        ]
        for name, call in cases:
            with self.subTest(stage=name):
                with self.assertRaises(TimeoutError):
                    call()

    def test_web_config_redacts_api_key(self) -> None:
        config = _config_from_payload(
            {
                "topic": "test",
                "llm_provider": "openai-compatible",
                "llm_base_url": "http://127.0.0.1:3000/v1",
                "llm_model": "local-model",
                "llm_api_key": "secret-key",
                "llm_max_calls": 8,
                "llm_max_prompt_chars": 40000,
                "llm_input_cost_per_million_tokens": 2.0,
                "llm_output_cost_per_million_tokens": 10.0,
                "max_search_queries": 6,
                "extra_search_queries": "robot manipulator OMPL benchmark\nRRT* CHOMP robot arm",
                "seed_papers": "10.1234/manual\nManual seed title 2026",
                "semantic_scholar_api_key": "s2-secret",
                "openalex_api_key": "oa-secret",
                "literature_contact_email": "lab@example.com",
            }
        )

        public = _public_config(config)

        self.assertEqual(config.llm.api_key, "secret-key")
        self.assertEqual(config.llm.max_calls, 8)
        self.assertEqual(config.llm.max_prompt_chars, 40000)
        self.assertEqual(config.llm.input_cost_per_million_tokens, 2.0)
        self.assertEqual(config.llm.output_cost_per_million_tokens, 10.0)
        self.assertEqual(config.literature.max_search_queries, 6)
        self.assertEqual(config.literature.extra_search_queries, ["robot manipulator OMPL benchmark", "RRT* CHOMP robot arm"])
        self.assertEqual(config.literature.seed_papers, ["10.1234/manual", "Manual seed title 2026"])
        self.assertEqual(config.literature.semantic_scholar_api_key, "s2-secret")
        self.assertEqual(config.literature.openalex_api_key, "oa-secret")
        self.assertEqual(config.literature.contact_email, "lab@example.com")
        self.assertEqual(public["llm"]["api_key"], "***")
        self.assertEqual(public["literature"]["semantic_scholar_api_key"], "***")
        self.assertEqual(public["literature"]["openalex_api_key"], "***")
        self.assertEqual(public["literature"]["contact_email"], "***")
        self.assertEqual(public["llm"]["max_calls"], 8)
        self.assertEqual(public["llm"]["input_cost_per_million_tokens"], 2.0)


if __name__ == "__main__":
    unittest.main()
