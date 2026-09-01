from __future__ import annotations

from .artifacts import write_json, write_text
from .models import BenchmarkCandidate, BenchmarkPlan, ExperimentPlan, ResearchPlan


BENCHMARK_PLAN_JSON = "03-benchmark-plan.json"
BENCHMARK_PLAN_MD = "03-benchmark-plan.md"


def build_benchmark_plan(research_plan: ResearchPlan, experiment_plan: ExperimentPlan) -> BenchmarkPlan:
    candidates = _domain_candidates(research_plan.domain)
    if not candidates:
        candidates = _generic_candidates(research_plan)
    candidates = _rank_candidates(candidates, research_plan)
    selected = candidates[:3]
    required_actions = _required_actions(selected, research_plan, experiment_plan)
    warnings = _warnings(selected, research_plan)
    return BenchmarkPlan(
        topic=research_plan.topic,
        domain=research_plan.domain,
        template_profile=experiment_plan.template_profile,
        candidates=candidates,
        selected_names=[item.name for item in selected],
        required_actions=required_actions,
        warnings=warnings,
    )


def write_benchmark_plan_artifacts(research_plan: ResearchPlan, experiment_plan: ExperimentPlan, out_dir) -> BenchmarkPlan:
    plan = build_benchmark_plan(research_plan, experiment_plan)
    write_json(out_dir / BENCHMARK_PLAN_JSON, plan)
    write_text(out_dir / BENCHMARK_PLAN_MD, render_benchmark_plan_markdown(plan))
    return plan


def render_benchmark_plan_markdown(plan: BenchmarkPlan) -> str:
    lines = [
        f"# Benchmark 接入计划：{plan.topic}",
        "",
        f"- 领域：{plan.domain}",
        f"- 实验模板：{plan.template_profile}",
        f"- 推荐接入：{', '.join(plan.selected_names) if plan.selected_names else '待人工选择'}",
        "",
        "## 候选 Benchmark / 数据集",
        "| 名称 | 类型 | 状态 | 访问 | URL | 指标 | Baseline |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in plan.candidates:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.name),
                    _cell(item.benchmark_type),
                    item.status,
                    _cell(item.access),
                    _cell(item.url or "-"),
                    _cell(", ".join(item.expected_metrics) or "-"),
                    _cell(", ".join(item.baselines) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 接入动作"])
    if plan.required_actions:
        lines.extend(f"- [ ] {item}" for item in plan.required_actions)
    else:
        lines.append("- 无")
    if plan.warnings:
        lines.extend(["", "## 风险"])
        lines.extend(f"- {item}" for item in plan.warnings)
    lines.extend(["", "## 候选详情"])
    for item in plan.candidates:
        lines.extend(
            [
                f"### {item.name}",
                f"- 许可/使用限制：{item.license_notes}",
                "- 集成步骤：",
                *[f"  - {step}" for step in item.integration_steps],
                "- 风险：",
                *[f"  - {risk}" for risk in item.risks],
                "",
            ]
        )
    return "\n".join(lines)


def _domain_candidates(domain: str) -> list[BenchmarkCandidate]:
    if domain == "robotics_motion_planning":
        return [
            BenchmarkCandidate(
                name="OMPL Benchmark",
                domain=domain,
                benchmark_type="motion planning benchmark suite",
                url="https://ompl.kavrakilab.org/benchmark.html",
                access="公开文档和开源库；需本地安装 OMPL/绑定环境",
                license_notes="按 OMPL 项目许可证和本地依赖许可证人工核对。",
                expected_metrics=["planning_success_rate", "planning_time", "path_length"],
                baselines=["RRT", "RRT*", "PRM"],
                integration_steps=[
                    "用固定随机种子生成 planner 配置和规划问题。",
                    "把 OMPL benchmark 输出转换为 04-results.json 兼容指标。",
                    "记录 planning scene、起终状态、超时和失败原因。",
                ],
                risks=["只覆盖几何规划时，可能弱化真实机械臂动力学和控制约束。"],
            ),
            BenchmarkCandidate(
                name="MoveIt Benchmarking",
                domain=domain,
                benchmark_type="robot arm planning benchmark",
                url="https://moveit.picknik.ai/main/doc/examples/benchmarking/benchmarking_tutorial.html",
                access="公开文档；需 ROS/MoveIt 环境和机械臂模型",
                license_notes="需核对 MoveIt、机器人模型和场景资源的许可证。",
                expected_metrics=["planning_success_rate", "planning_time", "trajectory_smoothness", "collision_rate"],
                baselines=["RRTConnect", "PRM", "CHOMP", "STOMP"],
                integration_steps=[
                    "固定机器人 URDF/SRDF、planning scene 和 planner 参数。",
                    "实现 MoveIt benchmark 结果到统一 metrics JSON 的转换脚本。",
                    "保留失败场景、碰撞检测配置和 planner 日志。",
                ],
                risks=["ROS 版本、插件和碰撞检测器差异会影响可复现性。"],
            ),
            BenchmarkCandidate(
                name="Narrow Passage / Cluttered Manipulation Tasks",
                domain=domain,
                benchmark_type="scenario suite",
                url="",
                access="需人工构造或从论文/公开仓库复用场景",
                license_notes="复用公开场景时需逐项核对资产许可证。",
                expected_metrics=["planning_success_rate", "minimum_clearance", "path_length", "failure_cases"],
                baselines=["RRT*", "TrajOpt", "STOMP"],
                integration_steps=[
                    "定义至少 20 个固定障碍布局和起终位姿。",
                    "保存每个场景的配置文件和 hash。",
                    "按场景难度分层报告结果。",
                ],
                risks=["人工场景过小会导致结论只适用于 demo。"],
            ),
        ]
    if domain == "bearing_fault_diagnosis":
        return [
            BenchmarkCandidate(
                name="CWRU Bearing Dataset",
                domain=domain,
                benchmark_type="bearing vibration dataset",
                url="https://engineering.case.edu/bearingdatacenter",
                access="公开下载；需人工确认当前下载入口和引用要求",
                license_notes="需人工核对 Case Western Reserve University 数据使用条款和引用要求。",
                expected_metrics=["accuracy", "macro_f1", "noise_robustness"],
                baselines=["SVM with handcrafted features", "1D-CNN", "ResNet"],
                integration_steps=[
                    "固定训练/验证/测试 split，避免同工况泄漏。",
                    "实现振动信号切窗、归一化和标签映射脚本。",
                    "输出 macro_f1、混淆矩阵和噪声鲁棒性结果。",
                ],
                risks=["同工况随机切分容易得到虚高结果。"],
            ),
            BenchmarkCandidate(
                name="Paderborn Bearing Dataset",
                domain=domain,
                benchmark_type="bearing vibration dataset",
                url="https://mb.uni-paderborn.de/kat/forschung/datacenter/bearing-datacenter",
                access="公开数据中心；需人工确认下载和引用条款",
                license_notes="需人工核对 Paderborn 数据中心使用条款。",
                expected_metrics=["cross_domain_accuracy", "macro_f1", "inference_latency"],
                baselines=["1D-CNN", "domain adaptation baseline", "Transformer encoder"],
                integration_steps=[
                    "按工况或损伤类型做跨域划分。",
                    "记录采样率、负载条件和预处理参数。",
                    "输出跨域准确率和类别级指标。",
                ],
                risks=["跨工况划分不清会削弱实验结论。"],
            ),
            BenchmarkCandidate(
                name="IMS Bearing Dataset",
                domain=domain,
                benchmark_type="bearing run-to-failure dataset",
                url="https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/",
                access="NASA PCoE 数据仓库；需人工确认数据集条目和下载路径",
                license_notes="需人工核对 NASA PCoE 数据使用说明和引用要求。",
                expected_metrics=["accuracy", "macro_f1", "failure_cases"],
                baselines=["LSTM", "ResNet", "Transformer encoder"],
                integration_steps=[
                    "实现 run-to-failure 序列切分。",
                    "分离训练和测试轴承实例。",
                    "报告随退化阶段变化的性能。",
                ],
                risks=["时间序列泄漏会导致评估不可信。"],
            ),
        ]
    if domain == "ai_research_agents":
        return [
            BenchmarkCandidate(
                name="MLAgentBench",
                domain=domain,
                benchmark_type="machine learning agent benchmark",
                url="https://github.com/snap-stanford/MLAgentBench",
                access="开源仓库；需本地配置任务和依赖",
                license_notes="按仓库许可证和任务数据许可证人工核对。",
                expected_metrics=["reproduction_success_rate", "artifact_completeness", "runtime_cost"],
                baselines=["single-shot LLM", "agent without human gate"],
                integration_steps=[
                    "选择小规模任务子集作为 smoke benchmark。",
                    "把 agent 轨迹、产物和任务成功率映射到统一结果格式。",
                    "记录每个任务的预算、失败原因和人工介入次数。",
                ],
                risks=["任务环境和依赖版本会影响可复现性。"],
            ),
            BenchmarkCandidate(
                name="PaperQA / citation QA task",
                domain=domain,
                benchmark_type="citation-grounded QA",
                url="https://github.com/Future-House/paper-qa",
                access="开源仓库；需准备文献集合和问题集",
                license_notes="需核对论文 PDF 和问答数据的使用权限。",
                expected_metrics=["citation_precision", "unsupported_claims"],
                baselines=["RAG-only assistant", "single-shot LLM"],
                integration_steps=[
                    "构造带 citation key 的问题集。",
                    "把回答中的 citation 映射到 01-context chunks。",
                    "人工抽样核验 citation precision。",
                ],
                risks=["如果问题集太小，citation precision 不稳定。"],
            ),
            BenchmarkCandidate(
                name="Claim-grounding audit set",
                domain=domain,
                benchmark_type="paper claim audit",
                url="",
                access="需人工构造或从历史 runs 采样",
                license_notes="使用真实论文片段时需核对版权和分享限制。",
                expected_metrics=["unsupported_claims", "review_revision_count"],
                baselines=["manual workflow", "agent without review gate"],
                integration_steps=[
                    "从历史论文草稿中抽取 claim。",
                    "标注 supported/weak/unsupported 金标准。",
                    "比较不同 agent 配置的审计召回和误报。",
                ],
                risks=["标注一致性不足会影响结论。"],
            ),
        ]
    return []


def _generic_candidates(research_plan: ResearchPlan) -> list[BenchmarkCandidate]:
    values = research_plan.benchmarks or ["领域公开数据集或任务集"]
    return [
        BenchmarkCandidate(
            name=value,
            domain=research_plan.domain,
            benchmark_type="domain benchmark",
            url="",
            access="需人工确认公开来源、下载方式和引用要求",
            license_notes="需人工核对数据/代码许可证和再分发限制。",
            expected_metrics=research_plan.metrics[:6],
            baselines=research_plan.baselines[:5],
            integration_steps=[
                "确认数据或任务集的正式来源 URL。",
                "实现 loader/preprocess 脚本并写入 experiments/。",
                "固定 split、随机种子、评价指标和失败样本记录方式。",
            ],
            risks=["benchmark 来源、许可或 split 不清会阻断正式研究结论。"],
        )
        for value in values[:5]
    ]


def _rank_candidates(candidates: list[BenchmarkCandidate], research_plan: ResearchPlan) -> list[BenchmarkCandidate]:
    hints = " ".join(research_plan.benchmarks + research_plan.metrics + research_plan.baselines).lower()
    return sorted(candidates, key=lambda item: _score_candidate(item, hints), reverse=True)


def _score_candidate(item: BenchmarkCandidate, hints: str) -> int:
    text = " ".join([item.name, item.benchmark_type, *item.expected_metrics, *item.baselines]).lower()
    score = 0
    for token in hints.replace("/", " ").replace("-", " ").split():
        if len(token) >= 3 and token in text:
            score += 1
    if item.url:
        score += 2
    if "manual_required" == item.status:
        score += 1
    return score


def _required_actions(candidates: list[BenchmarkCandidate], research_plan: ResearchPlan, experiment_plan: ExperimentPlan) -> list[str]:
    actions = [
        "从推荐 benchmark 中至少选择 1 个作为真实实验入口，并记录选择理由。",
        "确认数据/代码许可证、引用格式、下载方式和是否允许再分发。",
        "把 `experiments/simulate.py` 替换或扩展为真实 loader、baseline runner 和 metrics exporter。",
        "确保真实实验仍输出 `04-results.json` 兼容字段，并保留 seed、split、失败案例和产物 hash。",
    ]
    if experiment_plan.template_profile == "robotics_motion_planning":
        actions.append("固定机器人模型、planning scene、planner 参数、碰撞检测器和超时预算。")
    elif experiment_plan.template_profile == "bearing_fault_diagnosis":
        actions.append("固定训练/测试工况隔离策略，禁止同工况随机切分造成数据泄漏。")
    elif experiment_plan.template_profile == "ai_research_agents":
        actions.append("固定任务预算、工具权限、人工 gate 策略和评价 rubrics。")
    if research_plan.baselines:
        actions.append("至少实现或复用这些 baseline 的强对照：" + " / ".join(research_plan.baselines[:3]) + "。")
    for candidate in candidates:
        if candidate.url:
            actions.append(f"核对 {candidate.name} 的来源：{candidate.url}")
    return _unique(actions)


def _warnings(candidates: list[BenchmarkCandidate], research_plan: ResearchPlan) -> list[str]:
    warnings: list[str] = []
    if not candidates:
        warnings.append("未找到领域 benchmark 候选，需要人工补充。")
    if any(not item.url for item in candidates[:3]):
        warnings.append("部分推荐项缺少稳定 URL，正式研究前必须人工确认来源。")
    if research_plan.domain == "general_scientific_research":
        warnings.append("通用领域只能生成占位 benchmark 计划，需要人工替换为领域公开数据或任务集。")
    warnings.append("当前计划不会自动下载数据；下载、许可、引用和数据治理必须由人工确认。")
    return warnings


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
