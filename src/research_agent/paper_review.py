from __future__ import annotations

from typing import Any
import json
import re

from .llm import LLM
from .llm_trace import complete_with_purpose_detail, record_validation_result
from .models import (
    Analysis,
    ExperimentPlan,
    LiteratureContext,
    LiteratureReview,
    PaperClaimAudit,
    PaperReview,
    ResearchIdea,
)
from .artifacts import cell as _cell


def review_paper_draft(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    paper_md: str,
    context: LiteratureContext | None = None,
    llm: LLM | None = None,
) -> PaperReview:
    if llm is not None:
        ai_review = _try_ai_review(topic, review, ideas, plan, analysis, paper_md, context, llm)
        if ai_review is not None:
            return ai_review
    return _fallback_review(topic, review, ideas, plan, analysis, paper_md, context)


def render_paper_review_markdown(paper_review: PaperReview) -> str:
    lines = [
        "# 论文草稿复核",
        "",
        f"**决定：** {paper_review.decision}",
        f"**总分：** {paper_review.score:.1f}/10",
        "",
        "## 分项评分",
        f"- 新颖性：{paper_review.novelty}/5",
        f"- 技术可靠性：{paper_review.soundness}/5",
        f"- 证据质量：{paper_review.evidence_quality}/5",
        f"- 可复现性：{paper_review.reproducibility}/5",
        "",
        "## 总评",
        paper_review.summary,
        "",
        "## 优点",
    ]
    lines.extend(f"- {item}" for item in paper_review.strengths)
    lines.extend(["", "## 问题"])
    lines.extend(f"- {item}" for item in paper_review.weaknesses)
    lines.extend(["", "## 必须修改"])
    lines.extend(f"- [ ] {item}" for item in paper_review.required_revisions)
    lines.extend(["", "## Claim-Grounding 审计", "| Claim | 支撑 | 文献 | 结果 | 风险 |", "| --- | --- | --- | --- | --- |"])
    for item in paper_review.claim_audit:
        evidence = ", ".join(item.evidence_keys) or "待补"
        results = ", ".join(item.result_refs) or "待补"
        lines.append(f"| {_cell(item.claim)} | {item.support_level} | {evidence} | {results} | {item.risk} |")
    return "\n".join(lines)


def _try_ai_review(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    paper_md: str,
    context: LiteratureContext | None,
    llm: LLM,
) -> PaperReview | None:
    raw, call_id = complete_with_purpose_detail(
        llm,
        "Scientific peer review. You are a rigorous reviewer. Return only valid JSON in Chinese.",
        _review_prompt(topic, review, ideas, plan, analysis, paper_md, context),
        stage="paper_review_loop",
        purpose="scientific peer review",
        requires_validation=True,
    )
    data = _parse_json(raw)
    if not isinstance(data, dict):
        record_validation_result(llm, stage="paper_review_loop", valid=False, error="response is not a JSON object", call_id=call_id)
        return None
    summary = str(data.get("summary") or "").strip()
    if not summary:
        record_validation_result(llm, stage="paper_review_loop", valid=False, error="review schema is missing summary", call_id=call_id)
        return None
    record_validation_result(llm, stage="paper_review_loop", valid=True, call_id=call_id)
    claim_audit = _parse_claim_audit(data.get("claim_audit"))
    if claim_audit:
        claim_audit = _paper_only_claim_audit(claim_audit, paper_md)
    if not claim_audit:
        claim_audit = _fallback_claim_audit(ideas, plan, analysis, paper_md)
    return PaperReview(
        decision=str(data.get("decision") or "revise").strip(),
        score=_float_score(data.get("score"), 6.0),
        novelty=_score(data.get("novelty"), 3),
        soundness=_score(data.get("soundness"), 3),
        evidence_quality=_score(data.get("evidence_quality"), 3),
        reproducibility=_score(data.get("reproducibility"), 3),
        summary=summary,
        strengths=_as_str_list(data.get("strengths"))[:8] or ["草稿已经形成完整研究链路。"],
        weaknesses=_as_str_list(data.get("weaknesses"))[:8] or ["仍需人工复核关键 claim 与证据。"],
        required_revisions=_as_str_list(data.get("required_revisions"))[:10] or _default_revisions(claim_audit),
        claim_audit=claim_audit[:12],
    )


def _review_prompt(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    paper_md: str,
    context: LiteratureContext | None,
) -> str:
    best = ideas[0]
    schema = {
        "decision": "accept_with_minor_revisions | revise | major_revision | reject",
        "score": "0-10数字",
        "novelty": "1-5整数",
        "soundness": "1-5整数",
        "evidence_quality": "1-5整数",
        "reproducibility": "1-5整数",
        "summary": "审稿总评",
        "strengths": ["优点"],
        "weaknesses": ["问题"],
        "required_revisions": ["必须修改项"],
        "claim_audit": [
            {
                "claim": "论文中的关键主张",
                "support_level": "supported | weak | unsupported",
                "evidence_keys": ["citation key"],
                "result_refs": ["metric/result reference"],
                "risk": "low | medium | high",
            }
        ],
    }
    citation_keys = [item.key for item in context.citations[:12]] if context else []
    return "\n".join(
        [
            f"课题：{topic}",
            "请从审稿人视角评估论文草稿。严格检查 claim 是否有文献或实验结果支撑，不要替作者辩护。",
            "同时检查论文 claim 是否能映射到多智能体责任边界：manuscript_editor 负责成文，skeptical_reviewer 负责反驳和边界，evidence_curator/literature_scout 负责文献证据，benchmark_engineer/statistician 负责实验和统计证据。",
            "重要边界：claim_audit 只能记录论文草稿正文实际断言的 claim；选定 idea、实验计划和结果分析仅作上下文，不是自动成立的论文主张。",
            "如果原始 idea/plan 中的强目标已在论文正文中明确写为未检验、局限性、后续工作或禁止外推，不要把该目标列为 unsupported paper claim；可以在 weaknesses 中指出范围较窄。",
            "审稿输入说明：如果论文草稿中出现“系统节选说明”或“系统抽取的后续关键段落”，它是 prompt 压缩标记，不是论文正文；不得把它列为稿件中段省略、章节缺失或不可审查问题。",
            "输出要简洁：weaknesses、required_revisions、claim_audit 各最多 8 条；只审计最关键、最可能影响结论的 claim。",
            "可用 citation keys：",
            json.dumps((citation_keys or best.evidence_keys or plan.evidence_keys)[:8], ensure_ascii=False),
            "文献综述：",
            _short_text(review.summary, 800),
            "选定 idea：",
            json.dumps(
                {
                    "title": best.title,
                    "hypothesis": best.hypothesis,
                    "evidence_keys": best.evidence_keys,
                    "gap_alignment": best.gap_alignment,
                    "baseline": best.baseline,
                    "agent_roles": best.agent_roles,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "实验计划：",
            json.dumps(
                {
                    "objective": plan.objective,
                    "baseline": plan.baseline,
                    "metrics": plan.metrics,
                    "protocol": plan.protocol,
                    "evidence_keys": plan.evidence_keys,
                    "agent_roles": plan.agent_roles,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "结果分析：",
            json.dumps(
                {
                    "headline": analysis.headline,
                    "findings": analysis.findings,
                    "limitations": analysis.limitations,
                    "next_steps": analysis.next_steps,
                },
                ensure_ascii=False,
                indent=2,
            ),
            "论文草稿：",
            _paper_review_excerpt(paper_md),
            "输出严格 JSON，不要 Markdown，不要代码块。Schema：",
            json.dumps(schema, ensure_ascii=False, indent=2),
        ]
    )


def _paper_review_excerpt(paper_md: str, limit: int = 6000) -> str:
    text = str(paper_md or "")
    if len(text) <= limit:
        return text
    head_limit = min(900, max(400, limit // 4))
    head = _truncate_review_segment(text, head_limit)
    markers = [
        ("完整 per-repeat", 8),
        ("Ablation 诊断解释", 4),
        ("数据、split", 14),
        ("evidence_grade", 5),
        ("SHA256", 8),
        ("结果边界", 10),
        ("Claim 边界预检", 8),
        ("复现清单", 8),
        ("代码和数据可用性", 5),
    ]
    lines = text.splitlines()
    focus_lines: list[str] = []
    seen: set[str] = set()
    for marker, span in markers:
        start = next((index for index, line in enumerate(lines) if marker in line), -1)
        if start < 0:
            continue
        for line in lines[start : start + span]:
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                focus_lines.append(line)
    focus = "\n".join(focus_lines).strip()
    prefix = head + "\n\n[系统节选说明：为控制 prompt 长度，下方是系统抽取的后续关键段落，覆盖 runbook/results/statistics/availability；此行不是论文正文。]\n\n"
    remaining = max(0, limit - len(prefix))
    return (prefix + _truncate_review_segment(focus, remaining)).rstrip()


def _truncate_review_segment(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value.rstrip()
    if limit <= 0:
        return ""
    window = value[:limit]
    min_cut = max(1, int(limit * 0.55))
    candidates: list[int] = []
    for separator in ["\n\n", "\n", "。", "；", ".", ";"]:
        index = window.rfind(separator)
        if index >= min_cut:
            candidates.append(index + len(separator))
    if candidates:
        return window[: max(candidates)].rstrip()
    return window.rstrip()


def _fallback_review(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    paper_md: str,
    context: LiteratureContext | None,
) -> PaperReview:
    best = ideas[0]
    claim_audit = _fallback_claim_audit(ideas, plan, analysis, paper_md)
    unsupported = [item for item in claim_audit if item.support_level == "unsupported"]
    weak = [item for item in claim_audit if item.support_level == "weak"]
    novelty = best.novelty
    soundness = 4 if plan.metrics and analysis.metric_table else 3
    evidence_quality = _evidence_quality(best, plan, context, unsupported, weak)
    reproducibility = 4 if plan.protocol and plan.commands else 3
    score = round((novelty + soundness + evidence_quality + reproducibility) / 2.0, 1)
    decision = _decision(score, unsupported)
    weaknesses = []
    if unsupported:
        weaknesses.append(f"存在 {len(unsupported)} 条未支撑 claim，正式投稿前必须补文献或删改。")
    if weak:
        weaknesses.append(f"存在 {len(weak)} 条弱支撑 claim，需要把主张收窄到文献和实验可证明范围。")
    if analysis.metric_table:
        weaknesses.append("当前结果仍是模拟或小规模实验，不能直接支持强科学结论。")
    else:
        weaknesses.append("缺少结构化实验结果，方法有效性尚未验证。")
    required = _default_revisions(claim_audit)
    if context is not None and len(context.citations) < 5:
        required.append("扩大文献检索并补充至少 5 篇高相关可引用文献。")
    return PaperReview(
        decision=decision,
        score=score,
        novelty=novelty,
        soundness=soundness,
        evidence_quality=evidence_quality,
        reproducibility=reproducibility,
        summary=f"草稿围绕“{topic}”形成了从文献空白到实验计划的链路，但仍需要把关键 claim 与文献/结果逐条锁定。",
        strengths=[
            "保留了文献、idea、实验计划、结果和论文草稿等可审计产物。",
            "idea 和实验计划包含 citation key、baseline 与指标，便于人工复核。",
            f"选定假设具有可测试形式：{best.hypothesis}",
        ],
        weaknesses=weaknesses,
        required_revisions=required,
        claim_audit=claim_audit,
    )


def _paper_only_claim_audit(claim_audit: list[PaperClaimAudit], paper_md: str) -> list[PaperClaimAudit]:
    return [_with_inferred_result_refs(item) for item in claim_audit if _is_paper_claim_audit_item(item, paper_md)]


def _is_paper_claim_audit_item(item: PaperClaimAudit, paper_md: str) -> bool:
    if not paper_md.strip():
        return True
    asserted = _claim_asserted_in_paper(item.claim, paper_md)
    if asserted:
        return True
    if _claim_explicitly_scoped_out(item.claim, paper_md):
        return False
    if item.support_level in {"weak", "unsupported"}:
        return False
    return True


def _with_inferred_result_refs(item: PaperClaimAudit) -> PaperClaimAudit:
    if item.result_refs:
        return item
    refs = _inferred_result_refs(item.claim)
    if not refs:
        return item
    return PaperClaimAudit(
        claim=item.claim,
        support_level=item.support_level,
        evidence_keys=item.evidence_keys,
        result_refs=refs,
        risk=item.risk,
    )


def _inferred_result_refs(claim: str) -> list[str]:
    normalized = _normalize_claim(claim)
    if _contains_any(normalized, ["evidencegrade", "realbenchmark", "runbook", "results", "statistics", "adapter"]):
        return ["04-results.json", "04-statistics.json"]
    if _contains_any(normalized, ["accuracy", "macrof1", "errorrate", "candidate", "baseline", "均值", "差值", "指标"]):
        return ["04-results.json", "04-statistics.json"]
    return []


def _claim_asserted_in_paper(claim: str, paper_md: str) -> bool:
    claim_norm = _normalize_claim(claim)
    claim_core = _claim_core(claim_norm)
    if not claim_norm:
        return False
    for sentence in _sentences(paper_md):
        if _is_nonassertive_context(sentence):
            continue
        sentence_norm = _normalize_claim(sentence)
        if claim_norm in sentence_norm or (len(sentence_norm) >= 12 and sentence_norm in claim_norm):
            return True
        if len(claim_core) >= 8 and claim_core in sentence_norm:
            return True
        if _claim_token_overlap(claim_norm, sentence_norm):
            return True
    return False


def _claim_explicitly_scoped_out(claim: str, paper_md: str) -> bool:
    claim_terms = _claim_scope_terms(claim)
    if not claim_terms:
        return False
    for sentence in _sentences(paper_md):
        if not _is_scope_boundary(sentence):
            continue
        sentence_norm = _normalize_claim(sentence)
        if any(term in sentence_norm for term in claim_terms):
            return True
    return False


def _claim_scope_terms(claim: str) -> list[str]:
    normalized = _normalize_claim(claim)
    term_groups = [
        ["跨机器", "不同机器", "ci", "跨环境", "方差", "稳定性", "variance"],
        ["故障", "fault", "管线错误", "错误", "检测率", "暴露"],
        ["更可靠", "可靠诊断", "诊断信号", "诊断"],
        ["泛化", "跨数据集", "任务族"],
        ["release", "发布", "归档"],
        ["rbfsvm", "逻辑回归", "决策树", "dummy", "stratified"],
    ]
    terms: list[str] = []
    for group in term_groups:
        if any(term in normalized for term in group):
            terms.extend(group)
    return _unique(terms)


def _claim_core(claim_norm: str) -> str:
    core = claim_norm
    for prefix in ["本文已经证明", "本文证明", "结果显示", "实验显示", "结果表明", "实验表明", "我们证明", "我们发现"]:
        if core.startswith(prefix):
            return core[len(prefix) :]
    return core


def _claim_token_overlap(claim_norm: str, sentence_norm: str) -> bool:
    claim_numbers = _number_tokens(claim_norm)
    if claim_numbers and not claim_numbers <= _number_tokens(sentence_norm):
        return False
    claim_tokens = _semantic_tokens(claim_norm)
    if len(claim_tokens) < 4:
        return False
    sentence_tokens = _semantic_tokens(sentence_norm)
    overlap = claim_tokens & sentence_tokens
    threshold = min(5, max(4, len(claim_tokens) // 2))
    return len(overlap) >= threshold


def _number_tokens(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _semantic_tokens(text: str) -> set[str]:
    tokens = {item for item in re.findall(r"[a-z0-9_]+", text) if len(item) >= 2}
    for term in [
        "真实",
        "执行",
        "描述性",
        "指标",
        "文献",
        "支撑",
        "数据来源",
        "实现入口",
        "差值",
        "同一环境",
        "三次重复",
        "显著性",
        "跨环境",
        "稳定性",
    ]:
        if term in text:
            tokens.add(term)
    return tokens


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？.!?；;])\s*|\n+", text)
    return [item.strip() for item in raw if item.strip() and not item.lstrip().startswith("#")]


def _is_nonassertive_context(sentence: str) -> bool:
    return _contains_any(_normalize_claim(sentence), _NONASSERTIVE_MARKERS)


def _is_scope_boundary(sentence: str) -> bool:
    return _contains_any(_normalize_claim(sentence), _SCOPE_BOUNDARY_MARKERS)


def _fallback_claim_audit(
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    paper_md: str,
) -> list[PaperClaimAudit]:
    best = ideas[0]
    evidence_keys = _unique(best.evidence_keys + plan.evidence_keys)
    metric_refs = [str(key) for row in analysis.metric_table for key in row if key not in {"name", "status"}]
    result_refs = _unique(metric_refs + ["analysis.headline"] if analysis.headline else metric_refs)
    claims = _extract_claims(paper_md)
    if not claims:
        claims = [best.hypothesis, best.expected_contribution, analysis.headline]
    audited: list[PaperClaimAudit] = []
    for claim in claims[:10]:
        needs_result = _looks_like_empirical_claim(claim)
        has_evidence = bool(evidence_keys)
        has_result = bool(result_refs) and (needs_result or _contains_any(claim, ["结果", "显示", "高于", "低于", "改善", "降低", "提高"]))
        if has_evidence and (has_result or not needs_result):
            support = "supported"
            risk = "low"
        elif has_evidence or has_result:
            support = "weak"
            risk = "medium"
        else:
            support = "unsupported"
            risk = "high"
        audited.append(
            PaperClaimAudit(
                claim=claim,
                support_level=support,
                evidence_keys=evidence_keys[:5],
                result_refs=result_refs[:5] if has_result else [],
                risk=risk,
            )
        )
    return audited


def _extract_claims(paper_md: str) -> list[str]:
    claims: list[str] = []
    for raw in re.split(r"[。！？!?]\s*", paper_md):
        text = re.sub(r"^#+\s*", "", raw).strip()
        text = re.sub(r"^\-\s*", "", text).strip()
        if len(text) < 18 or text.startswith("|"):
            continue
        if _contains_any(text, ["本文", "结果", "显示", "提出", "证明", "支持", "降低", "提高", "优于", "贡献", "结论", "假设"]):
            claims.append(_short_text(text, 180))
    return _unique(claims)


def _evidence_quality(
    idea: ResearchIdea,
    plan: ExperimentPlan,
    context: LiteratureContext | None,
    unsupported: list[PaperClaimAudit],
    weak: list[PaperClaimAudit],
) -> int:
    score = 3
    if idea.evidence_keys or plan.evidence_keys:
        score += 1
    if context is not None and len(context.citations) >= 5:
        score += 1
    if unsupported:
        score -= 2
    elif weak:
        score -= 1
    return max(1, min(5, score))


def _decision(score: float, unsupported: list[PaperClaimAudit]) -> str:
    if unsupported and score < 6.5:
        return "major_revision"
    if score >= 8:
        return "accept_with_minor_revisions"
    if score >= 6:
        return "revise"
    return "major_revision"


def _default_revisions(claim_audit: list[PaperClaimAudit]) -> list[str]:
    revisions = [
        "把所有高风险或弱支撑 claim 改写为文献和实验结果能直接支持的范围。",
        "在结果段落中明确区分模拟结果、真实实验结果和推测性解释。",
        "补充可复现实验设置：数据/任务、baseline、随机种子、重复次数和统计检验。",
    ]
    if any(item.support_level == "unsupported" for item in claim_audit):
        revisions.insert(0, "删除或补证所有 unsupported claim。")
    return revisions


def _parse_claim_audit(value: Any) -> list[PaperClaimAudit]:
    if not isinstance(value, list):
        return []
    audits: list[PaperClaimAudit] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        audits.append(
            PaperClaimAudit(
                claim=claim,
                support_level=str(item.get("support_level") or "weak").strip(),
                evidence_keys=_as_str_list(item.get("evidence_keys")),
                result_refs=_as_str_list(item.get("result_refs")),
                risk=str(item.get("risk") or "medium").strip(),
            )
        )
    return audits


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


def _score(value: Any, default: int) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = default
    return max(1, min(5, score))


def _float_score(value: Any, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(10.0, score))


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _looks_like_empirical_claim(claim: str) -> bool:
    return _contains_any(claim, ["结果", "显示", "提高", "降低", "高于", "低于", "优于", "成功率", "误差", "耗时", "成本", "实验"])


def _contains_any(text: str, tokens: list[str]) -> bool:
    return any(token in text for token in tokens)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _short_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _normalize_claim(text: str) -> str:
    return re.sub(r"[\s，,。.;；:：!！?？、（）()【】\[\]\"'`\\-_/]+", "", text.lower())


_NONASSERTIVE_MARKERS = [
    "禁止表述",
    "禁用表述",
    "不得声称",
    "不能声称",
    "不应声称",
    "不再声称",
    "未声称",
    "没有声称",
    "未检验",
    "未完成验证",
    "不是本次已检验结果",
    "不构成",
    "不作为",
    "不用于",
    "不能自动外推",
    "尚需",
    "后续扩展",
    "后续工作",
    "下一轮",
    "prohibitedclaim",
    "donotclaim",
    "mustnotclaim",
]

_SCOPE_BOUNDARY_MARKERS = [
    "未检验",
    "未完成验证",
    "不是本次已检验结果",
    "不构成",
    "不作为",
    "不用于",
    "不能自动外推",
    "尚需",
    "需要更多",
    "局限",
    "后续扩展",
    "后续工作",
    "下一轮",
]
