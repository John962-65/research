from __future__ import annotations

from dataclasses import asdict
from typing import Any
import re

from .config import LiteratureConfig
from .models import LiteratureSearchQuery, LiteratureSearchStrategy


def build_literature_search_strategy(
    topic: str,
    config: LiteratureConfig,
    seed_queries: list[str] | None = None,
    extra_queries: list[str] | None = None,
    llm_queries: list[str] | None = None,
) -> LiteratureSearchStrategy:
    candidates: list[LiteratureSearchQuery] = []
    candidates.extend(_domain_queries(topic))
    candidates.extend(_query_items(seed_queries or [], "research_plan", 78, "研究计划给出的检索式"))
    candidates.extend(_query_items(extra_queries or [], "human", 98, "人工或检索反馈补充的高优先级检索式"))
    candidates.extend(_query_items(llm_queries or [], "llm", 70, "LLM 生成的补充检索式"))
    candidates.extend(_fallback_queries(topic))

    normalized: dict[str, LiteratureSearchQuery] = {}
    for item in candidates:
        query = _normalize_query(item.query)
        if not query:
            continue
        risk = item.risk or _query_risk(query)
        current = LiteratureSearchQuery(
            query=query,
            origin=item.origin,
            intent=item.intent or _query_intent(query),
            priority=item.priority,
            selected=False,
            rationale=item.rationale,
            risk=risk,
        )
        key = query.lower()
        if key not in normalized or _rank_key(current) > _rank_key(normalized[key]):
            normalized[key] = current

    ordered = sorted(normalized.values(), key=_rank_key, reverse=True)
    required_intents = _required_intents(topic, ordered, config.max_search_queries)
    selected = _select_queries(ordered, max(1, config.max_search_queries), required_intents)
    selected_set = {query.lower() for query in selected}
    final_candidates = [
        LiteratureSearchQuery(
            query=item.query,
            origin=item.origin,
            intent=item.intent,
            priority=item.priority,
            selected=item.query.lower() in selected_set,
            rationale=item.rationale,
            risk=item.risk,
        )
        for item in ordered
    ]
    audit = _strategy_audit(topic, config, final_candidates, selected)
    warnings = _warnings(config, final_candidates, selected, audit)
    recommendations = _recommendations(config, final_candidates, selected, audit)
    return LiteratureSearchStrategy(
        topic=topic,
        provider=config.provider,
        sources=[source.strip().lower() for source in config.sources if source.strip()],
        max_queries=config.max_search_queries,
        selected_queries=selected,
        candidates=final_candidates,
        status=str(audit["status"]),
        quality_score=float(audit["quality_score"]),
        selected_intents=[str(item) for item in audit["selected_intents"]],
        missing_required_intents=[str(item) for item in audit["missing_required_intents"]],
        weak_selected_queries=[str(item) for item in audit["weak_selected_queries"]],
        warnings=warnings,
        recommendations=recommendations,
    )


def strategy_to_dict(strategy: LiteratureSearchStrategy) -> dict[str, Any]:
    return asdict(strategy)


def render_literature_search_strategy_markdown(strategy: LiteratureSearchStrategy | dict[str, Any]) -> str:
    if isinstance(strategy, dict):
        data = strategy
    else:
        data = strategy_to_dict(strategy)
    candidates = data.get("candidates", [])
    selected_queries = data.get("selected_queries", [])
    lines = [
        f"# 文献检索策略：{data.get('topic') or ''}",
        "",
        f"- 文献模式：{data.get('provider') or ''}",
        f"- 在线来源：{', '.join(data.get('sources') or []) or 'none'}",
        f"- 检索式上限：{data.get('max_queries') or 0}",
        f"- 已选检索式：{len(selected_queries)}",
        f"- 策略状态：{data.get('status') or '-'}",
        f"- 策略质量分：{float(data.get('quality_score') or 0.0):.3f}",
        f"- 已覆盖意图：{', '.join(str(item) for item in data.get('selected_intents', []) if str(item).strip()) or '-'}",
        f"- 缺失必需意图：{', '.join(str(item) for item in data.get('missing_required_intents', []) if str(item).strip()) or '-'}",
        "",
        "## 已选检索式",
    ]
    if selected_queries:
        lines.extend(f"{index}. `{query}`" for index, query in enumerate(selected_queries, start=1))
    else:
        lines.append("- 无")
    warnings = data.get("warnings") or []
    if warnings:
        lines.extend(["", "## 风险"])
        lines.extend(f"- {item}" for item in warnings)
    recommendations = data.get("recommendations") or []
    if recommendations:
        lines.extend(["", "## 建议"])
        lines.extend(f"- {item}" for item in recommendations)
    lines.extend(
        [
            "",
            "## 候选检索式",
            "| 选择 | 来源 | 用途 | 优先级 | 风险 | 检索式 | 理由 |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    candidate_rows = candidates if isinstance(candidates, list) else []
    for item in candidate_rows:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    "yes" if item.get("selected") else "no",
                    _cell(str(item.get("origin") or "")),
                    _cell(str(item.get("intent") or "")),
                    str(item.get("priority") or 0),
                    _cell(str(item.get("risk") or "-")),
                    "`" + _cell(str(item.get("query") or "")) + "`",
                    _cell(str(item.get("rationale") or "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _domain_queries(topic: str) -> list[LiteratureSearchQuery]:
    lower = topic.lower()
    if "机械臂" in topic or "manipulator" in lower or ("robot" in lower and ("path" in lower or "motion" in lower)):
        return _query_items(
            [
                "robot manipulator motion planning survey review",
                "robot manipulator motion planning collision avoidance",
                "robot arm trajectory optimization CHOMP STOMP TrajOpt",
                "sampling-based motion planning RRT RRT* PRM robot manipulator",
                "OMPL motion planning benchmark robot manipulator",
                "recent robot manipulator motion planning learning-based 2024 2025",
            ],
            "domain_rule",
            92,
            "机械臂路径规划领域规则扩展，覆盖综述、采样规划、轨迹优化、benchmark 和近期工作",
        )
    if "轴承" in topic or "bearing" in lower or "fault" in lower:
        return _query_items(
            [
                "bearing fault diagnosis survey review benchmark dataset",
                "bearing fault diagnosis cross load dataset benchmark",
                "CWRU Paderborn XJTU-SY bearing fault diagnosis",
                "bearing fault diagnosis domain adaptation vibration signal",
                "bearing fault diagnosis 1D CNN Transformer baseline",
                "recent bearing fault diagnosis deep learning 2024 2025",
            ],
            "domain_rule",
            92,
            "轴承故障诊断领域规则扩展，覆盖综述、数据集、跨工况、baseline 和近期工作",
        )
    if "科研 agent" in topic or "research agent" in lower or "scientific discovery" in lower:
        return _query_items(
            [
                "survey of automated scientific discovery agents literature review",
                "automated scientific discovery agent literature review experiment",
                "AI scientist autonomous research agent paper writing benchmark",
                "LLM research agent citation grounded report generation",
                "agent laboratory autonomous research workflow human feedback",
                "recent autonomous research agents benchmark 2024 2025",
            ],
            "domain_rule",
            90,
            "科研 agent 领域规则扩展，覆盖综述、端到端科研、引用、benchmark、人工反馈和近期工作",
        )
    return []


def _fallback_queries(topic: str) -> list[LiteratureSearchQuery]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{2,}|[\u4e00-\u9fff]{2,}", topic)
    values = [topic]
    if tokens:
        values.append(" ".join(tokens[:8]))
    if tokens and len(tokens) >= 2:
        values.append(" ".join(tokens[:6]) + " review benchmark baseline")
    return _query_items(values, "fallback", 48, "规则兜底检索式，保证检索不会为空")


def _query_items(values: list[str], origin: str, priority: int, rationale: str) -> list[LiteratureSearchQuery]:
    return [
        LiteratureSearchQuery(
            query=str(value),
            origin=origin,
            intent=_query_intent(str(value)),
            priority=priority,
            selected=False,
            rationale=rationale,
            risk="",
        )
        for value in values
        if str(value).strip()
    ]


def _select_queries(candidates: list[LiteratureSearchQuery], max_queries: int, required_intents: list[str] | None = None) -> list[str]:
    selected: list[str] = []
    seen_intents: set[str] = set()
    for intent in required_intents or []:
        if len(selected) >= max_queries:
            break
        candidate = _best_intent_candidate(candidates, intent, selected)
        if candidate is None:
            continue
        selected.append(candidate.query)
        seen_intents.add(candidate.intent)
    for item in candidates:
        if len(selected) >= max_queries:
            break
        if item.query in selected:
            continue
        if item.risk == "too_broad" and len(candidates) > max_queries:
            continue
        if item.intent in seen_intents and len(selected) + 1 < max_queries:
            continue
        selected.append(item.query)
        seen_intents.add(item.intent)
    for item in candidates:
        if len(selected) >= max_queries:
            break
        if item.query not in selected:
            selected.append(item.query)
    return selected


def _best_intent_candidate(candidates: list[LiteratureSearchQuery], intent: str, selected: list[str]) -> LiteratureSearchQuery | None:
    for item in candidates:
        if item.intent == intent and item.query not in selected and item.risk != "too_broad":
            return item
    return None


def _query_intent(query: str) -> str:
    lower = query.lower()
    if any(term in lower for term in ["recent", "latest", "2024", "2025", "2026", "sota", "state of the art"]):
        return "recent"
    if any(term in lower for term in ["review", "survey", "literature"]):
        return "survey"
    if any(term in lower for term in ["benchmark", "dataset", "ompl", "cwru", "paderborn", "xjtu"]):
        return "benchmark"
    if any(term in lower for term in ["baseline", "rrt", "prm", "chomp", "stomp", "trajopt", "cnn", "transformer"]):
        return "baseline"
    if any(term in lower for term in ["experiment", "evaluation", "metric"]):
        return "experiment"
    return "method"


def _query_risk(query: str) -> str:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{2,}|[\u4e00-\u9fff]{2,}", query)
    if len(terms) < 3:
        return "too_broad"
    if len(query) > 180:
        return "too_long"
    return ""


def _rank_key(item: LiteratureSearchQuery) -> tuple[int, int, int]:
    risk_penalty = 18 if item.risk == "too_broad" else 5 if item.risk == "too_long" else 0
    source_bonus = {"domain_rule": 8, "human": 7, "research_plan": 5, "llm": 3}.get(item.origin, 0)
    intent_bonus = {"survey": 3, "recent": 3, "benchmark": 2, "baseline": 2}.get(item.intent, 0)
    return (item.priority + source_bonus + intent_bonus - risk_penalty, len(set(_terms(item.query))), -len(item.query))


def _strategy_audit(
    topic: str,
    config: LiteratureConfig,
    candidates: list[LiteratureSearchQuery],
    selected: list[str],
) -> dict[str, object]:
    selected_items = [item for item in candidates if item.query in selected]
    selected_intents = sorted({item.intent for item in selected_items if item.intent})
    required_intents = _required_intents(topic, candidates, config.max_search_queries)
    missing_required_intents = [intent for intent in required_intents if intent not in selected_intents]
    weak_selected_queries = [item.query for item in selected_items if item.risk in {"too_broad", "too_long"}]
    selected_count = len(selected_items)
    source_count = len([source for source in config.sources if source.strip()])
    avg_terms = sum(len(set(_terms(item.query))) for item in selected_items) / max(1, selected_count)
    score = 1.0
    if not selected_items:
        score = 0.0
    score -= 0.18 * len(missing_required_intents)
    score -= 0.14 * len(weak_selected_queries)
    if selected_count < min(3, max(1, config.max_search_queries)):
        score -= 0.12
    if avg_terms < 4 and selected_items:
        score -= 0.10
    if config.provider in {"online", "auto"} and source_count < 2:
        score -= 0.10
    score = round(max(0.0, min(1.0, score)), 3)
    if not selected_items or score < 0.55:
        status = "needs_query_repair"
    elif missing_required_intents or weak_selected_queries or score < 0.78:
        status = "review_required"
    else:
        status = "pass"
    return {
        "status": status,
        "quality_score": score,
        "selected_intents": selected_intents,
        "missing_required_intents": missing_required_intents,
        "weak_selected_queries": weak_selected_queries,
        "avg_terms": round(avg_terms, 3),
        "source_count": source_count,
    }


def _required_intents(topic: str, candidates: list[LiteratureSearchQuery], max_queries: int) -> list[str]:
    candidate_intents = {item.intent for item in candidates}
    if _domain_topic(topic):
        required = ["survey", "baseline", "benchmark", "recent", "method"]
    else:
        required = ["method"]
    if not _domain_topic(topic) and "survey" in candidate_intents:
        required.append("survey")
    if not _domain_topic(topic) and "baseline" in candidate_intents:
        required.append("baseline")
    if not _domain_topic(topic) and "benchmark" in candidate_intents:
        required.append("benchmark")
    if not _domain_topic(topic) and "recent" in candidate_intents:
        required.append("recent")
    required = [intent for intent in required if intent in candidate_intents or intent == "method"]
    limit = max(1, min(len(required), max_queries))
    return required[:limit]


def _domain_topic(topic: str) -> bool:
    lower = topic.lower()
    return (
        "机械臂" in topic
        or "轴承" in topic
        or "科研 agent" in topic
        or "research agent" in lower
        or "scientific discovery" in lower
        or "manipulator" in lower
        or ("robot" in lower and ("path" in lower or "motion" in lower))
        or "bearing" in lower
    )


def _warnings(
    config: LiteratureConfig,
    candidates: list[LiteratureSearchQuery],
    selected: list[str],
    audit: dict[str, object],
) -> list[str]:
    warnings: list[str] = []
    status = str(audit.get("status") or "")
    if status in {"needs_query_repair", "review_required"}:
        warnings.append(f"检索策略质量为 {status}，进入在线检索前建议先修复 query/seed。")
    missing = [str(item) for item in audit.get("missing_required_intents", []) if str(item).strip()]
    if missing:
        warnings.append("已选检索式缺少必需意图：" + ", ".join(missing) + "。")
    weak = [str(item) for item in audit.get("weak_selected_queries", []) if str(item).strip()]
    if weak:
        warnings.append("已选检索式包含过宽或过长查询：" + " | ".join(weak[:3]) + "。")
    if config.provider in {"online", "auto"} and not config.sources:
        warnings.append("在线/自动文献模式没有配置 sources，实际检索会退化。")
    elif config.provider in {"online", "auto"} and len([source for source in config.sources if source.strip()]) < 2:
        warnings.append("在线检索来源少于 2 个，建议至少保留 OpenAlex/Semantic Scholar/arXiv/Crossref 中的两个。")
    if any(item.risk == "too_broad" and item.selected for item in candidates):
        warnings.append("已选检索式中存在过宽查询，可能拉入弱相关论文。")
    if len(selected) < max(1, config.max_search_queries):
        warnings.append("可用检索式少于 max_search_queries，建议补充人工种子文献或更具体的术语。")
    if config.provider == "offline":
        warnings.append("当前为 offline 文献模式，检索策略仅用于离线排序；如需最新论文请切换 online 或 auto。")
    return _unique(warnings)


def _recommendations(
    config: LiteratureConfig,
    candidates: list[LiteratureSearchQuery],
    selected: list[str],
    audit: dict[str, object],
) -> list[str]:
    recommendations: list[str] = []
    intents = {item.intent for item in candidates if item.selected}
    missing = {str(item) for item in audit.get("missing_required_intents", [])}
    for intent in ["method", "baseline", "benchmark"]:
        if intent in missing:
            recommendations.append(f"先补一条 {intent} intent 的高精度英文 query，再启动在线检索。")
    for intent, label in [("survey", "综述"), ("benchmark", "benchmark/数据集"), ("baseline", "baseline"), ("recent", "近期工作/SOTA")]:
        if intent not in intents:
            recommendations.append(f"建议补充至少一条 {label} 检索式，减少候选论文偏题或缺少对照。")
    if audit.get("weak_selected_queries"):
        recommendations.append("把过宽 query 改成对象 + 方法族 + benchmark/数据集的组合，例如 robot manipulator + RRT* + OMPL。")
    if config.provider in {"online", "auto"} and "semantic_scholar" in {source.lower() for source in config.sources}:
        recommendations.append("Semantic Scholar 高频检索建议设置 SEMANTIC_SCHOLAR_API_KEY，降低 429 风险。")
    if not selected:
        recommendations.append("未选出检索式，建议在研究计划或人工种子文献中加入英文关键词。")
    return _unique(recommendations)


def _normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().strip('"')


def _terms(query: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_*+-]{2,}|[\u4e00-\u9fff]{2,}", query.lower())


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
