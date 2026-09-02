from __future__ import annotations

from typing import Any
import json
import re

from .config import IdeationConfig
from .llm import LLM
from .llm_trace import complete_with_purpose_detail, record_validation_result
from .literature_context import retrieve_chunks
from .multi_agent_assignment import agent_roles_for_text, multi_agent_prompt_context
from .research_gap_map import best_gap_for_text, research_gap_map_prompt_context
from .models import LiteratureContext, LiteratureReview, ResearchIdea


def generate_ideas(
    review: LiteratureReview,
    config: IdeationConfig,
    llm: LLM,
    context: LiteratureContext | None = None,
    review_feedback: str = "",
    research_gap_map: dict[str, Any] | None = None,
    agent_assignment: dict[str, Any] | None = None,
) -> list[ResearchIdea]:
    ai_ideas = _generate_ai_ideas(review, config, llm, context, review_feedback, research_gap_map, agent_assignment)
    if ai_ideas:
        return sorted(ai_ideas[: config.max_ideas], key=lambda idea: idea.score, reverse=True)
    candidates = _fallback_ideas(review, context, review_feedback, research_gap_map, agent_assignment)
    return sorted(candidates[: config.max_ideas], key=lambda idea: idea.score, reverse=True)


def render_ideas_markdown(ideas: list[ResearchIdea]) -> str:
    lines = ["# 研究 Ideas", ""]
    for index, idea in enumerate(ideas, start=1):
        lines.extend(
            [
                f"## {index}. {idea.title}",
                "",
                f"- 假设：{idea.hypothesis}",
                f"- 机制：{idea.mechanism}",
                f"- 预期贡献：{idea.expected_contribution}",
                f"- 文献依据：{', '.join(idea.evidence_keys) if idea.evidence_keys else '待人工补充'}",
                f"- 证据 Chunk：{', '.join(idea.evidence_chunks) if idea.evidence_chunks else '待人工补充'}",
                f"- 对齐空白：{idea.gap_alignment or '待人工确认'}",
                f"- Baseline：{idea.baseline or '待人工确认'}",
                f"- Agent Roles：{', '.join(idea.agent_roles) if idea.agent_roles else '待任务分配'}",
                f"- 评分：新颖性={idea.novelty}，可行性={idea.feasibility}，风险={idea.risk}，总分={idea.score}",
                "- 评估方式：" + "；".join(idea.evaluation),
                "- 实验草案：" + ("；".join(idea.experiment_sketch) if idea.experiment_sketch else "待实验计划阶段细化"),
                "",
            ]
        )
    return "\n".join(lines)


def _generate_ai_ideas(
    review: LiteratureReview,
    config: IdeationConfig,
    llm: LLM,
    context: LiteratureContext | None,
    review_feedback: str,
    research_gap_map: dict[str, Any] | None,
    agent_assignment: dict[str, Any] | None,
) -> list[ResearchIdea]:
    raw, call_id = complete_with_purpose_detail(
        llm,
        "Research ideas. You generate testable scientific ideas. Return only valid JSON in Chinese.",
        _ideas_prompt(review, config.max_ideas, context, review_feedback, research_gap_map, agent_assignment),
        stage="idea_generation",
        purpose="research ideas",
        requires_validation=True,
    )
    data = _parse_json(raw)
    items = data.get("ideas") if isinstance(data, dict) else data
    if not isinstance(items, list):
        record_validation_result(llm, stage="idea_generation", valid=False, error="response does not contain an ideas list", call_id=call_id)
        return []
    ideas: list[ResearchIdea] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        hypothesis = str(item.get("hypothesis") or "").strip()
        mechanism = str(item.get("mechanism") or "").strip()
        expected_contribution = str(item.get("expected_contribution") or item.get("contribution") or "").strip()
        evaluation = _as_str_list(item.get("evaluation"))
        evidence_keys = _as_str_list(item.get("evidence_keys") or item.get("citations"))
        evidence_chunks = _as_str_list(item.get("evidence_chunks") or item.get("chunks"))
        if context is not None:
            evidence_keys, evidence_chunks = _complete_evidence(context, f"{title} {hypothesis} {mechanism}", evidence_keys, evidence_chunks)
        gap = best_gap_for_text(research_gap_map, f"{title} {hypothesis} {mechanism}")
        if not all([title, hypothesis, mechanism, expected_contribution, evaluation]):
            continue
        roles = _agent_roles(item, agent_assignment, f"{title} {hypothesis} {mechanism} {gap.get('gap') or ''}")
        ideas.append(
            ResearchIdea(
                title=title,
                hypothesis=hypothesis,
                mechanism=mechanism,
                expected_contribution=expected_contribution,
                novelty=_clamp_score(item.get("novelty"), 3),
                feasibility=_clamp_score(item.get("feasibility"), 3),
                risk=_clamp_score(item.get("risk"), 3),
                evaluation=evaluation[:5],
                evidence_keys=evidence_keys[:5],
                evidence_chunks=evidence_chunks[:5],
                gap_alignment=str(item.get("gap_alignment") or gap.get("gap") or "").strip(),
                baseline=str(item.get("baseline") or gap.get("baseline") or "").strip(),
                experiment_sketch=_experiment_sketch(item, gap)[:5],
                agent_roles=roles[:5],
            )
        )
    record_validation_result(
        llm,
        stage="idea_generation",
        valid=bool(ideas),
        error="no idea satisfied the required schema" if not ideas else "",
        call_id=call_id,
    )
    return ideas


def _ideas_prompt(
    review: LiteratureReview,
    max_ideas: int,
    context: LiteratureContext | None,
    review_feedback: str = "",
    research_gap_map: dict[str, Any] | None = None,
    agent_assignment: dict[str, Any] | None = None,
) -> str:
    evidence = review.evidence_table[:10]
    schema = {
        "ideas": [
            {
                "title": "中文标题",
                "hypothesis": "可检验假设",
                "mechanism": "为什么这个方法可能有效",
                "expected_contribution": "预期学术/工程贡献",
                "novelty": "1-5整数",
                "feasibility": "1-5整数",
                "risk": "1-5整数，越高风险越大",
                "evidence_keys": ["必须来自文献上下文中的 citation key"],
                "evidence_chunks": ["必须来自文献上下文中的 chunk id"],
                "gap_alignment": "说明该 idea 对应哪个研究空白",
                "baseline": "最直接可比较 baseline",
                "agent_roles": ["负责推进该 idea 的 agent_id，例如 method_architect、benchmark_engineer、statistician、skeptical_reviewer"],
                "evaluation": ["至少3个可测评指标或实验协议"],
                "experiment_sketch": ["至少3步实验草案"],
            }
        ]
    }
    lines = [
        f"课题：{review.topic}",
        f"请生成 {max_ideas} 个可检验研究 idea。必须受下面文献证据和研究空白约束。",
        "每个 idea 必须显式给出 evidence_keys 和 evidence_chunks；这些值只能来自提供的文献上下文，不要编造 citation key 或 chunk id。",
        "文献综述：",
        review.summary,
        "研究空白：",
        json.dumps(review.gaps, ensure_ascii=False, indent=2),
        "证据表：",
        json.dumps(evidence, ensure_ascii=False, indent=2),
    ]
    gap_context = research_gap_map_prompt_context(research_gap_map)
    if gap_context:
        lines.extend(
            [
                "结构化研究空白矩阵：",
                gap_context,
                "优先围绕 testability=ready 的 gap 生成 idea；每个 idea 的 gap_alignment、baseline、evaluation 和 experiment_sketch 必须与其中一个 gap 对齐。",
            ]
        )
    agent_context = multi_agent_prompt_context(agent_assignment)
    if agent_context:
        lines.extend(
            [
                "多智能体任务分配：",
                agent_context,
                "每个 idea 必须给出 agent_roles；至少包含 method_architect，并根据任务需要加入 literature_scout、evidence_curator、benchmark_engineer、statistician 或 skeptical_reviewer。",
            ]
        )
    if review_feedback.strip():
        lines.extend(
            [
                "人工审核反馈/约束：",
                review_feedback.strip(),
                "生成 idea 时必须响应该反馈；如果反馈要求补文献、限定 baseline 或收窄问题，必须体现在 gap_alignment、baseline 或 experiment_sketch 中。",
            ]
        )
    if context is not None:
        lines.extend(
            [
                "文献上下文 citation keys：",
                json.dumps([_citation_payload(item) for item in context.citations[:12]], ensure_ascii=False, indent=2),
                "Top RAG chunks：",
                json.dumps([_chunk_payload(item) for item in context.chunks[:12]], ensure_ascii=False, indent=2),
                "Claim-support 表：",
                json.dumps([_claim_payload(item) for item in context.claim_support[:12]], ensure_ascii=False, indent=2),
            ]
        )
    lines.extend(["输出严格 JSON，不要 Markdown，不要代码块。Schema：", json.dumps(schema, ensure_ascii=False, indent=2)])
    return "\n".join(lines)


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
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


def _clamp_score(value: Any, default: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = default
    return min(5, max(1, score))


def _fallback_ideas(
    review: LiteratureReview | None = None,
    context: LiteratureContext | None = None,
    review_feedback: str = "",
    research_gap_map: dict[str, Any] | None = None,
    agent_assignment: dict[str, Any] | None = None,
) -> list[ResearchIdea]:
    gap_ideas = _gap_map_fallback_ideas(review, context, review_feedback, research_gap_map, agent_assignment)
    if gap_ideas:
        return gap_ideas
    if review is not None:
        ideas = _contextual_fallback_ideas(review, context, review_feedback)
        if ideas:
            return ideas
    return [
        ResearchIdea(
            title="以产物为中心的科研 Agent",
            hypothesis="显式暴露结构化中间产物的科研 agent，比只输出最终论文的 agent 更容易复现和审计。",
            mechanism="要求文献、idea、实验计划、结果和论文每一阶段都写入机器可读文件，并在进入下一阶段前做一致性检查。",
            expected_contribution="提出一套可审计科研 agent 架构，并给出可复现实验 benchmark。",
            novelty=4,
            feasibility=5,
            risk=2,
            evaluation=["产物完整度评分", "复现实验成功率", "人工审计耗时"],
            agent_roles=["method_architect", "benchmark_engineer", "skeptical_reviewer"],
        ),
        ResearchIdea(
            title="基于文献空白对比的 Idea 新颖性评估",
            hypothesis="如果 idea 生成器必须显式对齐文献空白、baseline 和实验成本，则生成的研究计划会更有新颖性且更可执行。",
            mechanism="用空白覆盖度、baseline 差异和实验成本对候选 idea 排序。",
            expected_contribution="提供一种自动科研 ideation 的评分协议。",
            novelty=4,
            feasibility=4,
            risk=3,
            evaluation=["新颖性 rubric", "可行性 rubric", "评审偏好对比"],
            agent_roles=["gap_analyst", "statistician", "skeptical_reviewer"],
        ),
        ResearchIdea(
            title="自主实验执行的安全沙箱策略",
            hypothesis="命令白名单、资源限制和 run-local 工作目录可以降低实验自动执行风险，同时保留大多数有用的计算实验能力。",
            mechanism="在一组自动生成实验计划上比较不同沙箱策略的阻断率、成功率和开销。",
            expected_contribution="形成科研 agent 实验执行层的安全策略模板。",
            novelty=3,
            feasibility=5,
            risk=2,
            evaluation=["危险命令阻断率", "实验成功率", "运行时开销"],
            agent_roles=["benchmark_engineer", "statistician", "skeptical_reviewer"],
        ),
        ResearchIdea(
            title="论文写作前的自我批判 Gate",
            hypothesis="在写论文前强制进行 claim-grounding 检查，可以减少自动生成论文中的无依据结论。",
            mechanism="加入一个批判阶段，把每个论文主张映射到实验产物或文献引用。",
            expected_contribution="提出自动论文生成中的主张约束和证据追踪协议。",
            novelty=3,
            feasibility=4,
            risk=2,
            evaluation=["无依据主张数量", "引用覆盖率", "修改轮次"],
            agent_roles=["evidence_curator", "skeptical_reviewer", "manuscript_editor"],
        ),
        ResearchIdea(
            title="成本感知的科研规划器",
            hypothesis="按单位计算成本的信息增益来规划实验，比只追求新颖性的规划器更早发现有价值的负结果。",
            mechanism="估计候选实验的信息增益、计算成本和失败价值，并据此调度实验。",
            expected_contribution="提出面向预算约束的自主科研调度方法。",
            novelty=5,
            feasibility=3,
            risk=4,
            evaluation=["单位成本有效发现数", "负结果发现时间", "计算资源利用率"],
            agent_roles=["method_architect", "statistician", "skeptical_reviewer"],
        ),
    ]


def _gap_map_fallback_ideas(
    review: LiteratureReview | None,
    context: LiteratureContext | None,
    review_feedback: str,
    research_gap_map: dict[str, Any] | None,
    agent_assignment: dict[str, Any] | None,
) -> list[ResearchIdea]:
    if not isinstance(research_gap_map, dict):
        return []
    gaps = [item for item in research_gap_map.get("gaps", []) if isinstance(item, dict)]
    if not gaps:
        return []
    ordered = sorted(gaps, key=lambda item: 0 if item.get("testability") == "ready" else 1)
    ideas: list[ResearchIdea] = []
    feedback_step = f"落实人工审核意见：{_short_text(review_feedback, 180)}" if review_feedback.strip() else ""
    topic = review.topic if review is not None else str(research_gap_map.get("topic") or "当前课题")
    for item in ordered[:5]:
        gap = str(item.get("gap") or "").strip()
        if not gap:
            continue
        baseline = str(item.get("baseline") or "").strip()
        benchmark = str(item.get("benchmark_or_dataset") or "").strip()
        metrics = _as_str_list(item.get("metrics"))
        evidence_keys = _as_str_list(item.get("evidence_keys"))
        evidence_chunks = _as_str_list(item.get("evidence_chunks"))
        if context is not None:
            evidence_keys, evidence_chunks = _complete_evidence(context, gap, evidence_keys, evidence_chunks)
        roles = agent_roles_for_text(agent_assignment, f"{gap} {baseline} {benchmark}", limit=4)
        if "method_architect" not in roles:
            roles.insert(0, "method_architect")
        experiment_hint = str(item.get("experiment_hint") or "").strip()
        steps = [
            f"围绕 {benchmark or '公开 benchmark/data'} 构建代表性任务集",
            f"比较 candidate、{baseline or '强 baseline'} 和消融版本",
            f"报告 {', '.join(metrics[:3]) if metrics else '核心指标'} 并分析失败模式",
        ]
        if experiment_hint:
            steps.append(experiment_hint)
        if feedback_step:
            steps.append(feedback_step)
        ideas.append(
            ResearchIdea(
                title=f"面向{topic}的{_short_text(gap, 24)}可检验研究",
                hypothesis=str(item.get("hypothesis_seed") or f"针对“{gap}”的候选方案可以在明确 baseline 和 benchmark 下产生可验证差异。"),
                mechanism="把结构化研究空白转化为 baseline、benchmark、指标和消融协议，避免只凭主观新颖性推进实验。",
                expected_contribution="提供一个由文献证据、coverage 缺口和人工约束共同限定的可复现研究问题。",
                novelty=4 if item.get("testability") == "ready" else 3,
                feasibility=4 if item.get("testability") in {"ready", "review"} else 3,
                risk=2 if item.get("testability") == "ready" else 4,
                evaluation=metrics[:5] or ["主指标差值", "重复试验稳定性", "失败案例覆盖"],
                evidence_keys=evidence_keys[:5],
                evidence_chunks=evidence_chunks[:5],
                gap_alignment=gap,
                baseline=baseline or "研究空白矩阵建议补齐的强 baseline",
                experiment_sketch=steps[:5],
                agent_roles=roles[:5],
            )
        )
    return ideas


def _contextual_fallback_ideas(review: LiteratureReview, context: LiteratureContext | None, review_feedback: str = "") -> list[ResearchIdea]:
    claims = list(review.gaps or review.themes or [review.topic])
    ideas: list[ResearchIdea] = []
    feedback_step = f"落实人工审核意见：{_short_text(review_feedback, 180)}" if review_feedback.strip() else ""
    feedback_baseline = _baseline_from_feedback(review_feedback)
    for claim in claims[:5]:
        evidence_keys, evidence_chunks = _complete_evidence(context, claim, [], []) if context is not None else ([], [])
        short = _short_text(claim, 28)
        ideas.append(
            ResearchIdea(
                title=f"面向{review.topic}的{short}验证框架",
                hypothesis=f"如果围绕“{claim}”设计可复现实验协议，则可以比现有方法更清楚地区分有效改进和仅在个别场景成立的结果。",
                mechanism="把文献中反复出现的问题、baseline 和失败模式转化为可测指标，再用消融实验验证关键机制。",
                expected_contribution="形成一个由文献证据约束的研究 idea 和实验协议，降低无依据创新点的风险。",
                novelty=4,
                feasibility=4,
                risk=3,
                evaluation=["任务成功率或核心性能指标", "与强 baseline 的差值", "失败案例分类", "重复试验稳定性"],
                evidence_keys=evidence_keys,
                evidence_chunks=evidence_chunks,
                gap_alignment=claim,
                baseline=feedback_baseline or "文献中最高相关的传统 baseline 或消融版本",
                experiment_sketch=["构建代表性任务集", "比较 proposed/baseline/ablation", "统计核心指标和失败模式"] + ([feedback_step] if feedback_step else []),
                agent_roles=agent_roles_for_text(None, claim, limit=4) or ["gap_analyst", "method_architect", "statistician", "skeptical_reviewer"],
            )
        )
    return ideas


def _baseline_from_feedback(review_feedback: str) -> str:
    if not review_feedback.strip():
        return ""
    patterns = [
        r"RRT\*",
        r"\bRRT\b",
        r"\bPRM\b",
        r"\bCHOMP\b",
        r"\bSTOMP\b",
        r"\bTrajOpt\b",
        r"\bSVM\b",
        r"\bCNN\b",
        r"\bLSTM\b",
        r"\bResNet\b",
        r"\bTransformer\b",
    ]
    matches: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, review_feedback, flags=re.I):
            value = _canonical_baseline(match)
            if value and value not in matches:
                matches.append(value)
    return " / ".join(matches[:4])


def _canonical_baseline(value: str) -> str:
    upper = value.upper()
    if upper == "TRAJOPT":
        return "TrajOpt"
    if upper == "TRANSFORMER":
        return "Transformer"
    if upper == "RESNET":
        return "ResNet"
    return upper


def _complete_evidence(
    context: LiteratureContext | None,
    query: str,
    evidence_keys: list[str],
    evidence_chunks: list[str],
) -> tuple[list[str], list[str]]:
    if context is None:
        return evidence_keys, evidence_chunks
    known_keys = {item.key for item in context.citations}
    known_chunks = {item.chunk_id for item in context.chunks}
    keys = [key for key in evidence_keys if key in known_keys]
    chunks = [chunk for chunk in evidence_chunks if chunk in known_chunks]
    if not keys or not chunks:
        retrieved = retrieve_chunks(context, query, top_k=3)
        if not chunks:
            chunks = [chunk.chunk_id for chunk in retrieved]
        if not keys:
            keys = []
            for chunk in retrieved:
                if chunk.citation_key not in keys:
                    keys.append(chunk.citation_key)
    return keys, chunks


def _experiment_sketch(item: dict[str, Any], gap: dict[str, Any]) -> list[str]:
    values = _as_str_list(item.get("experiment_sketch"))
    hint = str(gap.get("experiment_hint") or "").strip()
    if hint and hint not in values:
        values.append(hint)
    return values


def _agent_roles(item: dict[str, Any], assignment: dict[str, Any] | None, text: str) -> list[str]:
    roles = _as_str_list(item.get("agent_roles") or item.get("assigned_agents"))
    if not roles:
        roles = agent_roles_for_text(assignment, text, limit=4)
    if roles and "method_architect" not in roles:
        roles.insert(0, "method_architect")
    return _unique_roles(roles)


def _unique_roles(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _citation_payload(citation: Any) -> dict[str, Any]:
    return {
        "key": citation.key,
        "title": citation.title,
        "year": citation.year,
        "venue": citation.venue,
        "doi": citation.doi,
    }


def _chunk_payload(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "citation_key": chunk.citation_key,
        "title": chunk.title,
        "text": _short_text(chunk.text, 420),
        "relevance": chunk.relevance,
    }


def _claim_payload(claim: Any) -> dict[str, Any]:
    return {
        "claim": claim.claim,
        "claim_type": claim.claim_type,
        "support_level": claim.support_level,
        "citation_keys": claim.citation_keys,
    }


def _short_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
