from __future__ import annotations

from typing import Any
import json
import re

from .llm import LLM
from .llm_trace import complete_with_purpose_detail, record_validation_result
from .models import ResearchPlan


def build_research_plan(topic: str, llm: LLM | None = None, prior_lessons: str = "") -> ResearchPlan:
    if llm is not None:
        plan = _try_ai_plan(topic, llm, prior_lessons=prior_lessons)
        if plan is not None:
            return _apply_prior_lessons(plan, prior_lessons)
    return _apply_prior_lessons(_rule_plan(topic), prior_lessons)


def render_research_plan_markdown(plan: ResearchPlan) -> str:
    lines = [
        f"# 研究计划：{plan.topic}",
        "",
        f"- 领域：{plan.domain}",
        f"- 目标：{plan.objective}",
        "",
        "## 检索式",
    ]
    lines.extend(f"- {item}" for item in plan.search_queries)
    lines.extend(["", "## Benchmark / 数据集 / 任务"])
    lines.extend(f"- {item}" for item in plan.benchmarks)
    lines.extend(["", "## Baseline"])
    lines.extend(f"- {item}" for item in plan.baselines)
    lines.extend(["", "## 指标"])
    lines.extend(f"- {item}" for item in plan.metrics)
    lines.extend(["", "## 约束"])
    lines.extend(f"- {item}" for item in plan.constraints)
    lines.extend(["", "## 风险"])
    lines.extend(f"- {item}" for item in plan.risks)
    lines.extend(["", "## 成功标准"])
    lines.extend(f"- {item}" for item in plan.success_criteria)
    return "\n".join(lines)


def _try_ai_plan(topic: str, llm: LLM, prior_lessons: str = "") -> ResearchPlan | None:
    raw, call_id = complete_with_purpose_detail(
        llm,
        "Research planning. You create domain profiles for scientific agents. Return only valid JSON in Chinese.",
        _prompt(topic, prior_lessons=prior_lessons),
        stage="research_planning",
        purpose="research planning",
        requires_validation=True,
    )
    data = _parse_json(raw)
    if not isinstance(data, dict):
        record_validation_result(llm, stage="research_planning", valid=False, error="response is not a JSON object", call_id=call_id)
        return None
    domain = str(data.get("domain") or "").strip()
    objective = str(data.get("objective") or "").strip()
    search_queries = _as_str_list(data.get("search_queries"))
    metrics = _as_str_list(data.get("metrics"))
    if not domain or not objective or len(search_queries) < 2 or len(metrics) < 2:
        record_validation_result(llm, stage="research_planning", valid=False, error="research plan schema is incomplete", call_id=call_id)
        return None
    record_validation_result(llm, stage="research_planning", valid=True, call_id=call_id)
    fallback = _rule_plan(topic)
    return ResearchPlan(
        topic=topic,
        domain=domain,
        objective=objective,
        search_queries=_unique(search_queries + fallback.search_queries)[:8],
        benchmarks=_as_str_list(data.get("benchmarks"))[:8] or fallback.benchmarks,
        baselines=_as_str_list(data.get("baselines"))[:8] or fallback.baselines,
        metrics=_unique(metrics + fallback.metrics)[:10],
        constraints=_as_str_list(data.get("constraints"))[:8] or fallback.constraints,
        risks=_as_str_list(data.get("risks"))[:8] or fallback.risks,
        success_criteria=_as_str_list(data.get("success_criteria"))[:8] or fallback.success_criteria,
    )


def _prompt(topic: str, prior_lessons: str = "") -> str:
    schema = {
        "domain": "领域英文短名，例如 robotics_motion_planning",
        "objective": "一句话研究目标",
        "search_queries": ["英文 scholarly search query，2-8条"],
        "benchmarks": ["公开 benchmark、数据集或任务集"],
        "baselines": ["可比较 baseline"],
        "metrics": ["可量化指标"],
        "constraints": ["实验/安全/可复现约束"],
        "risks": ["主要研究风险"],
        "success_criteria": ["成功标准"],
    }
    return "\n".join(
        [
            f"课题：{topic}",
            "请为科研 agent 生成前置研究计划。重点是让后续文献检索、idea 和实验计划更贴合领域。",
            "对中文课题，必须给出英文 scholarly search queries。",
            "如果提供了历史 run 经验，必须把它转成 constraints、risks、success_criteria 或 search_queries，不要忽略。",
            "历史 run 经验：",
            prior_lessons.strip() or "无",
            "输出严格 JSON，不要 Markdown，不要代码块。Schema：",
            json.dumps(schema, ensure_ascii=False, indent=2),
        ]
    )


def _rule_plan(topic: str) -> ResearchPlan:
    lower = topic.lower()
    if "机械臂" in topic or "manipulator" in lower or ("robot" in lower and "path" in lower):
        return ResearchPlan(
            topic=topic,
            domain="robotics_motion_planning",
            objective="构建并评估机械臂路径规划方法在避障、效率和轨迹质量上的可复现改进。",
            search_queries=[
                "robot manipulator motion planning obstacle avoidance",
                "robot arm path planning RRT star trajectory optimization",
                "manipulator trajectory planning benchmark OMPL MoveIt",
                "sampling based motion planning robot manipulator collision avoidance",
                "trajectory optimization CHOMP STOMP TrajOpt robot arm",
            ],
            benchmarks=["OMPL benchmark", "MoveIt benchmarking", "cluttered manipulation scenes", "narrow passage motion planning tasks"],
            baselines=["RRT", "RRT*", "PRM", "CHOMP", "STOMP", "TrajOpt"],
            metrics=["planning_success_rate", "planning_time", "path_length", "collision_rate", "trajectory_smoothness", "minimum_clearance"],
            constraints=["关节限位", "碰撞检测一致性", "固定随机种子", "相同起终位姿和障碍布局"],
            risks=["只在简单场景有效", "仿真碰撞模型与真实机械臂不一致", "路径质量指标和任务成功率冲突"],
            success_criteria=["candidate 在成功率或路径质量上优于 baseline", "至少报告重复试验统计", "失败案例能按碰撞、超时、不可达分类"],
        )
    if "轴承" in topic or "bearing" in lower or "fault" in lower:
        return ResearchPlan(
            topic=topic,
            domain="bearing_fault_diagnosis",
            objective="评估轴承故障诊断方法在跨工况、噪声和少样本条件下的鲁棒性。",
            search_queries=[
                "bearing fault diagnosis vibration signal deep learning",
                "CWRU bearing dataset fault diagnosis benchmark",
                "Paderborn bearing dataset domain adaptation",
                "XJTU-SY bearing fault diagnosis remaining useful life",
                "bearing fault diagnosis transfer learning noisy conditions",
            ],
            benchmarks=["CWRU bearing dataset", "Paderborn bearing dataset", "XJTU-SY bearing dataset", "IMS bearing dataset"],
            baselines=["SVM with handcrafted features", "1D-CNN", "LSTM", "ResNet", "Transformer encoder", "domain adaptation baseline"],
            metrics=["accuracy", "macro_f1", "auc", "cross_domain_accuracy", "noise_robustness", "inference_latency"],
            constraints=["训练/测试工况隔离", "类别不平衡处理", "固定数据划分", "报告混淆矩阵"],
            risks=["数据泄漏", "同工况随机划分导致虚高性能", "只在单一数据集上有效"],
            success_criteria=["跨工况 macro_f1 优于 baseline", "噪声条件下性能下降可控", "提供重复试验均值和置信区间"],
        )
    if "agent" in lower or "科研" in topic or "research" in lower:
        return ResearchPlan(
            topic=topic,
            domain="ai_research_agents",
            objective="评估科研 agent 在文献证据、实验复现、论文草稿和人工审核上的端到端可靠性。",
            search_queries=[
                "autonomous scientific discovery agent experiment paper review",
                "AI Scientist automated scientific discovery simulated review",
                "scientific literature agent retrieval augmented generation citations",
                "research assistant agent paper writing literature review",
            ],
            benchmarks=["LitQA-style citation QA", "paper review rubric", "small reproducible experiment suite", "claim-grounding audit set"],
            baselines=["manual workflow", "single-shot LLM", "RAG-only assistant", "agent without human gate"],
            metrics=["citation_precision", "unsupported_claims", "artifact_completeness", "reproduction_success_rate", "review_revision_count"],
            constraints=["引用可追溯", "人工审批 gate", "实验命令白名单", "产物全量保存"],
            risks=["幻觉引用", "不可复现实验", "自动生成论文夸大结论"],
            success_criteria=["每个关键 claim 有文献或实验支撑", "实验产物可复放", "人工审核能阻断低质量文献进入 idea 阶段"],
        )
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", topic)
    query = " ".join(tokens[:8]) or topic
    return ResearchPlan(
        topic=topic,
        domain="general_scientific_research",
        objective=f"围绕“{topic}”建立可检索、可评估、可复现的研究流程。",
        search_queries=[query, f"{query} benchmark", f"{query} baseline evaluation", f"{query} systematic review"],
        benchmarks=["领域公开数据集或任务集", "人工构造小型 benchmark", "强 baseline 复现实验"],
        baselines=["传统方法 baseline", "当前最相关神经方法", "消融版本"],
        metrics=["success_rate", "quality_score", "runtime_cost", "failure_cases"],
        constraints=["固定数据划分", "固定随机种子", "记录失败案例", "公开所有中间产物"],
        risks=["文献覆盖不足", "baseline 选择不公平", "模拟实验不能代表真实场景"],
        success_criteria=["candidate 在至少一个核心指标上优于 baseline", "重复试验统计支持结论", "关键 claim 均有证据支撑"],
    )


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, flags=re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _apply_prior_lessons(plan: ResearchPlan, prior_lessons: str) -> ResearchPlan:
    lessons = _lesson_lines(prior_lessons)
    if not lessons:
        return plan
    constraints = _unique([*plan.constraints, *[f"历史经验约束：{item}" for item in lessons[:4]]])[:12]
    risks = _unique([*plan.risks, *[f"历史 run 风险：{item}" for item in lessons[:3]]])[:12]
    success = _unique(
        [
            *plan.success_criteria,
            "本轮必须在 00-prior-run-lessons.md、00-prior-run-library.md 和 00-open-source-lessons.md 中可追踪地响应历史 run 经验、历史成果库参考与外部项目约束。",
        ]
    )[:10]
    return ResearchPlan(
        topic=plan.topic,
        domain=plan.domain,
        objective=plan.objective,
        search_queries=plan.search_queries,
        benchmarks=plan.benchmarks,
        baselines=plan.baselines,
        metrics=plan.metrics,
        constraints=constraints,
        risks=risks,
        success_criteria=success,
    )


def _lesson_lines(prior_lessons: str) -> list[str]:
    lines: list[str] = []
    for raw in prior_lessons.splitlines():
        line = raw.strip().lstrip("-").strip()
        if not line or line in {"无", "历史 run 经验："}:
            continue
        if len(line) > 220:
            line = line[:219].rstrip() + "…"
        if line not in lines:
            lines.append(line)
    return lines[:8]
