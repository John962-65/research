from __future__ import annotations

import unittest

from research_agent.config import PaperConfig
from research_agent.literature_context import citation_key_for_paper
from research_agent.models import Analysis, ExperimentCommand, ExperimentPlan, LiteratureReview, Paper, ResearchIdea
from research_agent.writing import write_paper_markdown


class NoCitationPaperLLM:
    def complete(self, system: str, user: str) -> str:
        return "\n".join(
            [
                "# AI 草稿",
                "",
                "## 摘要",
                "本文讨论机械臂路径规划并给出实验草稿，但没有使用任何 citation key。",
                "## 相关工作",
                "相关工作讨论了运动规划和避障。",
                "## 方法",
                "方法部分描述候选规划器。",
                "## 结果",
                "结果部分描述模拟结果。",
                "## 局限性",
                "局限性是仍需真实 benchmark。",
                "## 结论",
                "结论部分保持保守。",
            ]
        )


class CitationPaperLLM:
    def __init__(self, key: str) -> None:
        self.key = key
        self.user_prompt = ""

    def complete(self, system: str, user: str) -> str:
        self.user_prompt = user
        return "\n".join(
            [
                "# AI 引用草稿",
                "",
                "## 摘要",
                f"本文围绕机械臂路径规划形成证据约束草稿 [{self.key}]。",
                "## 相关工作",
                f"相关工作使用给定 citation key 约束背景 [{self.key}]。",
                "## 方法",
                "方法部分描述候选规划器和 baseline。",
                "## 结果",
                "结果部分只讨论已有模拟结果。",
                "## 局限性",
                "局限性是仍需真实 benchmark。",
                "## 结论",
                "结论保持在当前证据范围内。",
            ]
        )


class OverclaimPaperLLM:
    def __init__(self, key: str) -> None:
        self.key = key

    def complete(self, system: str, user: str) -> str:
        return "\n".join(
            [
                "# AI 越界草稿",
                "",
                "## 摘要",
                f"本文证明候选方法显著优于基线 [{self.key}]。",
                "## 相关工作",
                f"相关工作使用给定 citation key [{self.key}]。",
                "## 方法",
                "方法部分描述候选规划器。",
                "## 结果",
                "结果证明方法有效。",
                "## 局限性",
                "局限性很少。",
                "## 结论",
                "候选方法支持假设。",
            ]
        )


class WritingTest(unittest.TestCase):
    def test_ai_paper_without_citation_key_falls_back_to_cited_rule_draft(self) -> None:
        review, idea, plan, analysis = _fixtures()
        key = citation_key_for_paper(review.papers[0], 1)

        paper = write_paper_markdown("机械臂路径规划", review, [idea], plan, analysis, PaperConfig(), NoCitationPaperLLM())

        self.assertIn("可复现实验草稿", paper)
        self.assertIn("## 参考证据", paper)
        self.assertIn(f"[{key}]", paper)
        self.assertNotIn("[manual2024robot]", paper)
        self.assertNotIn("# AI 草稿", paper)

    def test_ai_paper_with_known_citation_key_is_accepted(self) -> None:
        review, idea, plan, analysis = _fixtures()
        key = citation_key_for_paper(review.papers[0], 1)
        llm = CitationPaperLLM(key)

        paper = write_paper_markdown("机械臂路径规划", review, [idea], plan, analysis, PaperConfig(), llm)

        self.assertIn("# AI 引用草稿", paper)
        self.assertIn(f"[{key}]", paper)
        self.assertIn(key, llm.user_prompt)
        self.assertIn("只能使用下列 citation keys", llm.user_prompt)
        self.assertIn("多智能体职责", llm.user_prompt)
        self.assertIn("manuscript_editor", llm.user_prompt)

    def test_real_benchmark_evidence_reaches_prompt_and_fallback_scope(self) -> None:
        review, idea, plan, analysis = _fixtures()
        key = citation_key_for_paper(review.papers[0], 1)
        llm = CitationPaperLLM(key)
        benchmark_evidence = {"status": "pass", "evidence_grade": "real_benchmark", "claim_policy": "limited_scope_real_benchmark"}

        accepted = write_paper_markdown(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            llm,
            benchmark_evidence=benchmark_evidence,
        )
        fallback = write_paper_markdown(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            benchmark_evidence=benchmark_evidence,
        )

        self.assertIn("# AI 引用草稿", accepted)
        self.assertIn("evidence_grade=real_benchmark", llm.user_prompt)
        self.assertIn("内部已执行 benchmark adapter artifact/smoke-run report", fallback)
        self.assertIn("artifact/smoke-run report", fallback)
        self.assertNotIn("初步模拟结果", fallback)
        self.assertNotIn("默认模拟实验显示", fallback)
        self.assertNotIn("替换为真实领域 benchmark", fallback)

    def test_real_benchmark_fallback_scopes_unexecuted_claims_to_boundaries(self) -> None:
        review, idea, plan, analysis = _fixtures()
        strong_idea = ResearchIdea(
            title=idea.title,
            hypothesis="固定协议后，结果方差在不同机器和不同 CI 环境中显著降低，并能稳定暴露管线错误。",
            mechanism=idea.mechanism,
            expected_contribution=idea.expected_contribution,
            novelty=idea.novelty,
            feasibility=idea.feasibility,
            risk=idea.risk,
            evaluation=idea.evaluation,
            evidence_keys=[*idea.evidence_keys, "seedndscikitlearn12"],
            evidence_chunks=idea.evidence_chunks,
            gap_alignment=idea.gap_alignment,
            baseline=idea.baseline,
        )
        broad_plan = ExperimentPlan(
            idea_title=plan.idea_title,
            objective="验证最小套件是否能提供比单一高精度模型更可靠的 smoke benchmark 诊断信号。",
            variables=plan.variables,
            metrics=["accuracy", "failure_detection_rate", "manifest_schema_validation_pass_rate"],
            protocol=[
                "运行 RBF-SVM、KNN、逻辑回归和决策树。",
                "报告 failure_detection_rate 与 manifest_schema_validation_pass_rate。",
            ],
            commands=plan.commands,
            baseline="RBF-SVM 或 KNN 示例脚本。",
            evidence_keys=[*plan.evidence_keys, "seedndscikitlearn14"],
        )
        real_analysis = Analysis(
            headline="accuracy：candidate 均值=0.967，baseline 均值=0.333，差值=0.633，95% CI=[0.633, 0.633]，效应量=NA；candidate 在该指标上优于 baseline。",
            metric_table=[
                {"name": "candidate-uci-iris-nearest-centroid-candidate", "status": "passed", "repeat_index": 0, "accuracy": 0.966667, "macro_f1": 0.966583, "error_rate": 0.033333, "train_cases": 120.0, "test_cases": 30.0},
                {"name": "baseline-uci-iris-majority-baseline", "status": "passed", "repeat_index": 0, "accuracy": 0.333333, "macro_f1": 0.166667, "error_rate": 0.666667, "train_cases": 120.0, "test_cases": 30.0},
                {"name": "ablation-uci-iris-sepal-centroid-ablation", "status": "passed", "repeat_index": 0, "accuracy": 0.733333, "macro_f1": 0.725253, "error_rate": 0.266667, "train_cases": 120.0, "test_cases": 30.0},
            ],
            findings=["macro_f1：candidate 均值=0.967，baseline 均值=0.167，差值=0.800，95% CI=[0.800, 0.800]，效应量=NA；candidate 在该指标上优于 baseline。"],
            limitations=analysis.limitations,
            next_steps=analysis.next_steps,
        )

        paper = write_paper_markdown(
            "Iris classification benchmark smoke",
            review,
            [strong_idea],
            broad_plan,
            real_analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            benchmark_evidence={"status": "warn", "evidence_grade": "real_benchmark"},
        )

        self.assertIn("本次可检验问题", paper)
        self.assertIn("Iris Benchmark Adapter Smoke Run 报告", paper)
        self.assertIn("不是由当前 Iris smoke run 证明的领域性结论", paper)
        self.assertIn("baseline-uci-iris-majority-baseline", paper)
        self.assertIn("ablation-uci-iris-sepal-centroid-ablation", paper)
        self.assertIn("跨机器/CI 方差、故障注入检测率和更大任务族泛化不是本次已检验结果", paper)
        self.assertIn("RBF-SVM、KNN、逻辑回归、决策树等只作为后续扩展", paper)
        self.assertIn("描述性 smoke 结果", paper)
        self.assertIn("不构成显著性或跨环境稳定性结论", paper)
        self.assertNotIn("显著降低", paper)
        self.assertNotIn("稳定暴露管线错误", paper)
        self.assertNotIn("failure_detection_rate\n", paper)
        self.assertNotIn("seedndscikitlearn12", paper)
        self.assertNotIn("seedndscikitlearn14", paper)
        self.assertNotIn("95% CI=[0.633, 0.633]", paper)
        self.assertNotIn("相关研究通常同时面对方法选择、实验可复现性和评价指标一致性等问题", paper)

    def test_real_benchmark_fallback_reports_runbook_table_and_hash_scope(self) -> None:
        review, idea, plan, analysis = _fixtures()
        real_analysis = Analysis(
            headline="accuracy：candidate 均值=0.967，baseline 均值=0.967，差值=0.000，95% CI=[0.000, 0.000]，效应量=NA；差异跨过 0，需要更多重复实验确认。",
            metric_table=[
                {
                    "name": "candidate-uci-iris-nearest-centroid-candidate",
                    "status": "passed",
                    "repeat_index": 0,
                    "duration_seconds": 0.123,
                    "accuracy": 0.966667,
                    "macro_f1": 0.966583,
                    "error_rate": 0.033333,
                    "train_cases": 120.0,
                    "test_cases": 30.0,
                    "train_class_count_setosa": 40.0,
                    "test_class_count_setosa": 10.0,
                    "cm_setosa_setosa": 10.0,
                    "cm_setosa_versicolor": 0.0,
                    "cm_setosa_virginica": 0.0,
                    "cm_versicolor_setosa": 0.0,
                    "cm_versicolor_versicolor": 9.0,
                    "cm_versicolor_virginica": 1.0,
                    "cm_virginica_setosa": 0.0,
                    "cm_virginica_versicolor": 0.0,
                    "cm_virginica_virginica": 10.0,
                }
            ],
            findings=[],
            limitations=[
                "当前真实 benchmark adapter 已执行，但 Iris smoke 任务规模很小，只能支撑 benchmark provenance、manifest 合约和流程诊断类结论。"
            ],
            next_steps=analysis.next_steps,
        )
        runbook = {
            "execution": {
                "mode": "benchmark",
                "repeats": 3,
                "timeout_seconds": 300,
                "allowed_commands": ["python3"],
                "env_policy": "minimal",
                "working_directory": "experiments/",
                "python_version": "3.12.3",
                "python_executable": "/usr/bin/python3",
                "platform": "Linux-test",
            },
            "environment": {"source_tree": {"aggregate_sha256": "srcsha", "file_count": 12}},
            "commands": [
                {
                    "name": "candidate-uci-iris-nearest-centroid-candidate",
                    "role": "candidate",
                    "command": ["python3", "grade_iris.py", "--method", "nearest_centroid"],
                }
            ],
            "runs": [
                {
                    "name": "candidate-uci-iris-nearest-centroid-candidate",
                    "repeat_index": 0,
                    "seed": "seed-c0",
                    "status": "passed",
                    "duration_seconds": 0.123,
                    "command": ["python3", "grade_iris.py", "--method", "nearest_centroid"],
                    "produced_artifacts": [
                        {"path": "experiments/benchmark-adapters/candidate/candidate_metrics.json", "sha256": "abc1234567890"},
                        {"path": "experiments/benchmark-adapters/candidate/data/iris.data", "sha256": "datasha"},
                        {"path": "experiments/benchmark-adapters/candidate/split/iris-stratified-test-v1.json", "sha256": "splitsha"},
                        {"path": "experiments/benchmark-adapters/candidate/grade_iris.py", "sha256": "gradersha"},
                    ],
                }
            ],
        }

        paper = write_paper_markdown(
            "Iris classification benchmark smoke",
            review,
            [idea],
            plan,
            real_analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            benchmark_evidence={"status": "warn", "evidence_grade": "real_benchmark", "results": 1, "comparisons": 1, "repeats": 3},
            runbook=runbook,
        )

        self.assertIn("数据、split 与执行环境", paper)
        self.assertIn("Python 3.12.3", paper)
        self.assertIn("source_tree aggregate_sha256=srcsha", paper)
        self.assertIn("evidence_grade=real_benchmark", paper)
        self.assertIn("real_benchmark 是本系统的内部产物审计等级", paper)
        self.assertIn("Artifact 索引", paper)
        self.assertIn("04-experiment-runbook.json", paper)
        self.assertIn("04-results.json", paper)
        self.assertIn("04-statistics.json", paper)
        self.assertIn("03-benchmark-adapters.json", paper)
        self.assertIn("04-benchmark-result-schema-audit.json", paper)
        self.assertIn("04-benchmark-evidence-audit.json", paper)
        self.assertIn("04-environment-snapshot.json", paper)
        self.assertIn("run-manifest.json", paper)
        self.assertIn("数据 provenance 与 split 复现", paper)
        self.assertIn("10.24432/C56C76", paper)
        self.assertIn("样本顺序假设", paper)
        self.assertIn("公开可访问性边界", paper)
        self.assertIn("已审计 data SHA256", paper)
        self.assertIn("未运行 baseline 清单", paper)
        self.assertIn("DummyClassifier stratified：未在本次 runbook 执行", paper)
        self.assertIn("RBF-SVM/SVC 默认 baseline：未在本次 runbook 执行", paper)
        self.assertIn("完整 per-repeat 结果表", paper)
        self.assertIn("| candidate | 0 | seed-c0 | nearest_centroid | 0.966667", paper)
        self.assertIn("setosa 10/0/0", paper)
        self.assertIn("candidate_metrics.json:abc123456789", paper)
        self.assertIn("当前 repeat 未观察到 candidate-baseline 数值差异", paper)
        self.assertIn("artifact 完整性观察", paper)
        self.assertNotIn("流程诊断类结论", paper)
        self.assertNotIn("差异跨过 0，需要更多重复实验确认", paper)

    def test_real_benchmark_fallback_writes_citation_role_map(self) -> None:
        review = _iris_review()
        _, idea, plan, analysis = _fixtures()

        paper = write_paper_markdown(
            "Iris classification benchmark smoke",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            benchmark_evidence={"status": "pass", "evidence_grade": "real_benchmark", "results": 4, "comparisons": 3, "repeats": 3},
        )

        self.assertIn("引用角色表", paper)
        self.assertIn("| [akrom2025a1] | Iris benchmark/application background only |", paper)
        self.assertIn("不支撑本次 protocol validity、real_benchmark 等级、性能优势或外部泛化", paper)
        self.assertIn("| [fisher1936iris2] | Iris 数据 provenance |", paper)
        self.assertIn("RBF-SVM 未在本次 runbook 中执行", paper)
        self.assertIn("见引用角色表；本次实验性结果只由 runbook/results/statistics 支撑", paper)
        self.assertNotIn("可追踪 citation key 包括", paper)

    def test_real_benchmark_reference_baseline_does_not_pollute_primary_baseline(self) -> None:
        review, idea, plan, analysis = _fixtures()
        real_analysis = Analysis(
            headline="accuracy：candidate 均值=0.967，baseline 均值=0.967，差值=0.000，95% CI=[0.000, 0.000]，效应量=NA；差异跨过 0，需要更多重复实验确认。",
            metric_table=[
                {"name": "candidate-uci-iris-nearest-centroid-candidate", "status": "passed", "repeat_index": 0, "accuracy": 0.966667, "macro_f1": 0.966583, "error_rate": 0.033333, "train_cases": 120.0, "test_cases": 30.0},
                {"name": "baseline-uci-iris-3-nearest-neighbor-baseline", "status": "passed", "repeat_index": 0, "accuracy": 0.966667, "macro_f1": 0.966583, "error_rate": 0.033333, "train_cases": 120.0, "test_cases": 30.0},
                {"name": "ablation-uci-iris-sepal-centroid-ablation", "status": "passed", "repeat_index": 0, "accuracy": 0.733333, "macro_f1": 0.725253, "error_rate": 0.266667, "train_cases": 120.0, "test_cases": 30.0},
                {"name": "uci-iris-majority-class-reference-baseline", "status": "passed", "repeat_index": 0, "accuracy": 0.333333, "macro_f1": 0.166667, "error_rate": 0.666667, "train_cases": 120.0, "test_cases": 30.0},
            ],
            findings=analysis.findings,
            limitations=analysis.limitations,
            next_steps=analysis.next_steps,
        )

        paper = write_paper_markdown(
            "Iris classification benchmark smoke",
            review,
            [idea],
            plan,
            real_analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            benchmark_evidence={"status": "pass", "evidence_grade": "real_benchmark", "results": 4, "comparisons": 3, "repeats": 3},
        )

        self.assertIn("reference=uci-iris-majority-class-reference-baseline", paper)
        self.assertIn("不进入主 candidate-vs-knn3 统计比较", paper)
        self.assertIn("Ablation 结果摘要：ablation accuracy=0.733333，candidate accuracy=0.966667，baseline accuracy=0.966667", paper)
        self.assertIn("| reference | 0 | - | majority_class | 0.333333", paper)
        self.assertIn("reference `uci-iris-majority-class-reference-baseline`: repeat=0", paper)
        self.assertNotIn("baseline accuracy=0.65", paper)

    def test_failure_analysis_boundaries_are_written_into_fallback_paper(self) -> None:
        review, idea, plan, analysis = _fixtures()
        boundary = "模拟结果只能作为工程烟测；论文主结论需要 local 或 benchmark 真实实验支撑。"

        paper = write_paper_markdown(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            failure_analysis={"status": "warn", "claim_boundaries": [boundary]},
        )

        self.assertIn("## 结果边界", paper)
        self.assertIn(boundary, paper)
        self.assertNotIn("# AI 草稿", paper)

    def test_experiment_decision_boundaries_are_written_into_fallback_paper(self) -> None:
        review, idea, plan, analysis = _fixtures()
        boundary = "实验后决策为 pivot_or_refine；负结果必须作为发现报告。"

        paper = write_paper_markdown(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            experiment_decision={"status": "warn", "decision": "pivot_or_refine", "claim_boundaries": [boundary]},
        )

        self.assertIn("## 结果边界", paper)
        self.assertIn(boundary, paper)

    def test_hypothesis_outcome_boundaries_are_written_into_fallback_paper(self) -> None:
        review, idea, plan, analysis = _fixtures()
        boundary = "假设只得到部分支持；论文必须区分稳定正向、不确定和未检验指标。"

        paper = write_paper_markdown(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            NoCitationPaperLLM(),
            hypothesis_outcome={"status": "review_required", "outcome": "partially_supported", "claim_boundaries": [boundary]},
        )

        self.assertIn("## 结果边界", paper)
        self.assertIn(boundary, paper)

    def test_claim_boundary_preflight_rejects_overclaiming_ai_draft(self) -> None:
        review, idea, plan, analysis = _fixtures()
        key = citation_key_for_paper(review.papers[0], 1)
        boundary = "当前仅为 smoke 证据；不得写成正式科学主结论。"

        paper = write_paper_markdown(
            "机械臂路径规划",
            review,
            [idea],
            plan,
            analysis,
            PaperConfig(),
            OverclaimPaperLLM(key),
            claim_boundary_preflight={
                "status": "review_required",
                "writing_mode": "smoke_limited_paper",
                "required_boundary_statements": [boundary],
                "allowed_claims": ["只能描述 smoke test 初步趋势。"],
                "prohibited_claims": ["不得声称显著优于或证明假设。"],
                "prohibited_patterns": ["证明", "显著优于", "方法有效", "支持假设"],
                "prompt_constraints": ["必须新增结果边界。"],
            },
        )

        self.assertNotIn("# AI 越界草稿", paper)
        self.assertIn("## 结果边界", paper)
        self.assertIn("## Claim 边界预检", paper)
        self.assertIn(boundary, paper)


def _fixtures() -> tuple[LiteratureReview, ResearchIdea, ExperimentPlan, Analysis]:
    paper = Paper(
        title="Robot manipulator motion planning with obstacle avoidance",
        authors=["Ada Lovelace"],
        year=2024,
        venue="arXiv",
        url="https://arxiv.org/abs/0000.00001",
        abstract="Robot manipulator motion planning and obstacle avoidance benchmark.",
        relevance=0.9,
        source="arxiv",
        sources=["arxiv"],
        doi="10.1234/example",
    )
    review = LiteratureReview(
        topic="机械臂路径规划",
        papers=[paper],
        themes=["机械臂路径规划需要避障和轨迹连续性。"],
        gaps=["需要可复现 benchmark。"],
        summary="测试综述",
    )
    idea = ResearchIdea(
        title="避障路径规划验证",
        hypothesis="候选规划器可以在复杂障碍场景中提高规划成功率。",
        mechanism="结合采样式规划和轨迹平滑约束。",
        expected_contribution="提供机械臂路径规划的可复现实验起点。",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=["planning_success_rate", "planning_time", "path_length"],
        evidence_keys=["manual2024robot"],
        evidence_chunks=["chunk-001"],
        baseline="RRT*",
        agent_roles=["method_architect", "evidence_curator", "skeptical_reviewer"],
    )
    plan = ExperimentPlan(
        idea_title=idea.title,
        objective="比较候选规划器与 RRT* 的规划成功率。",
        variables=["方法", "障碍密度"],
        metrics=["planning_success_rate", "planning_time"],
        protocol=["固定起终位姿", "运行候选方案和 baseline", "统计重复试验结果"],
        commands=[ExperimentCommand(name="simulate", command=["python3", "simulate.py"])],
        baseline="RRT*",
        evidence_keys=["manual2024robot"],
        agent_roles=["method_architect", "benchmark_engineer", "statistician", "manuscript_editor"],
    )
    analysis = Analysis(
        headline="候选方案在模拟实验中取得更高成功率。",
        metric_table=[{"name": "planning_success_rate", "candidate": 0.82, "baseline": 0.74}],
        findings=["成功率高于 baseline。"],
        limitations=["当前仍是模拟实验。"],
        next_steps=["接入真实 benchmark。"],
    )
    return review, idea, plan, analysis


def _iris_review() -> LiteratureReview:
    papers = [
        Paper(
            title="A Quantum Circuit Learning-based Investigation: A Case Study in Iris Benchmark Dataset Binary Classification",
            authors=["M Akrom"],
            year=2025,
            venue="Journal of Computing Theories and Applications",
            url="https://doi.org/10.62411/jcta.11779",
            abstract="A recent Iris benchmark dataset binary classification application.",
            relevance=0.79,
            source="crossref",
            sources=["crossref"],
            doi="10.62411/jcta.11779",
        ),
        Paper(
            title="Iris",
            authors=["R A Fisher"],
            year=1936,
            venue="UCI Machine Learning Repository",
            url="https://archive.ics.uci.edu/dataset/53",
            abstract="Iris dataset original measurements and provenance.",
            relevance=0.76,
            source="doi",
            sources=["doi", "manual_seed"],
            doi="",
        ),
        Paper(
            title="scikit-learn Support Vector Machine RBF kernel Iris baseline",
            authors=["Seed"],
            year=0,
            venue="Manual seed",
            url="https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVC.html",
            abstract="scikit-learn SVC RBF kernel API background for Iris baseline expansion.",
            relevance=0.72,
            source="manual_seed",
            sources=["manual_seed"],
            doi="",
        ),
        Paper(
            title="review overview benchmark dataset official UCI repository page",
            authors=["Seed"],
            year=2024,
            venue="Manual seed",
            url="https://archive.ics.uci.edu/dataset/53/iris",
            abstract="Official UCI repository page and dataset metadata.",
            relevance=0.72,
            source="manual_seed",
            sources=["manual_seed"],
            doi="",
        ),
        Paper(
            title="The Reduced Nearest Neighbor Rule",
            authors=["G W Gates"],
            year=1972,
            venue="IEEE Transactions on Information Theory",
            url="https://doi.org/10.1109/TIT.1972.1054809",
            abstract="Nearest neighbor classification background.",
            relevance=0.68,
            source="doi",
            sources=["doi"],
            doi="10.1109/TIT.1972.1054809",
        ),
        Paper(
            title="scikit-learn k-Nearest Neighbors Iris classification baseline",
            authors=["Seed"],
            year=0,
            venue="Manual seed",
            url="https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.KNeighborsClassifier.html",
            abstract="scikit-learn KNeighborsClassifier API background for Iris classification baseline.",
            relevance=0.67,
            source="manual_seed",
            sources=["manual_seed"],
            doi="",
        ),
        Paper(
            title="scikit-learn load_iris built-in Iris dataset provenance fallback",
            authors=["Seed"],
            year=0,
            venue="Manual seed",
            url="https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_iris.html",
            abstract="scikit-learn load_iris API and built-in Iris dataset provenance fallback.",
            relevance=0.66,
            source="manual_seed",
            sources=["manual_seed"],
            doi="",
        ),
    ]
    return LiteratureReview(
        topic="Iris classification benchmark smoke",
        papers=papers,
        themes=["Iris 数据 provenance、API 入口和 baseline 背景需要分开处理。"],
        gaps=["需要把 citation role 和实验 artifact 支撑边界分离。"],
        summary="Iris 文献池只提供数据来源、API 入口和背景 baseline，不证明本次 adapter 协议有效性。",
    )


if __name__ == "__main__":
    unittest.main()
