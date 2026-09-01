from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .config import PaperConfig
from .evidence_integrity import (
    EvidenceIntegrity,
    evidence_integrity_banner,
    evidence_integrity_prompt_constraint,
)
from .literature_context import citation_key_for_paper
from .llm import LLM
from .llm_trace import complete_with_purpose, record_validation_result
from .models import Analysis, ExperimentPlan, LiteratureReview, Paper, ResearchIdea


METRIC_LABELS = {
    "reproduction_success_rate": "复现成功率",
    "artifact_completeness": "产物完整度",
    "audit_minutes": "审计耗时",
    "unsupported_claims": "无依据主张数",
}


def write_paper_markdown(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    config: PaperConfig,
    llm: LLM | None = None,
    failure_analysis: dict[str, Any] | None = None,
    experiment_decision: dict[str, Any] | None = None,
    hypothesis_outcome: dict[str, Any] | None = None,
    claim_boundary_preflight: dict[str, Any] | None = None,
    benchmark_evidence: dict[str, Any] | None = None,
    evidence_integrity: EvidenceIntegrity | None = None,
    runbook: dict[str, Any] | None = None,
) -> str:
    citation_keys = _citation_keys(review, ideas, plan)
    claim_boundaries = _claim_boundaries(failure_analysis, experiment_decision, hypothesis_outcome, claim_boundary_preflight)
    if llm is not None:
        ai_draft = _try_ai_paper(
            topic,
            review,
            ideas,
            plan,
            analysis,
            config,
            llm,
            citation_keys,
            claim_boundaries,
            failure_analysis,
            experiment_decision,
            hypothesis_outcome,
            claim_boundary_preflight,
            benchmark_evidence,
            evidence_integrity,
            runbook,
        )
        if ai_draft:
            return _prepend_integrity_banner(ai_draft, evidence_integrity)
    fallback = _fallback_paper(
        topic,
        review,
        ideas,
        plan,
        analysis,
        config,
        claim_boundaries=claim_boundaries,
        claim_boundary_preflight=claim_boundary_preflight,
        benchmark_evidence=benchmark_evidence,
        runbook=runbook,
    )
    return _prepend_integrity_banner(fallback, evidence_integrity)


def _prepend_integrity_banner(paper_md: str, integrity: EvidenceIntegrity | None) -> str:
    """把诚实性横幅插到标题行之后；证据充分时原样返回。"""
    banner = evidence_integrity_banner(integrity)
    if not banner:
        return paper_md
    head, _, rest = paper_md.partition("\n")
    if head.startswith("# "):
        return f"{head}\n\n{banner}\n\n{rest}" if rest else f"{head}\n\n{banner}"
    return f"{banner}\n\n{paper_md}"


def _try_ai_paper(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    config: PaperConfig,
    llm: LLM,
    citation_keys: list[str],
    claim_boundaries: list[str],
    failure_analysis: dict[str, Any] | None,
    experiment_decision: dict[str, Any] | None,
    hypothesis_outcome: dict[str, Any] | None,
    claim_boundary_preflight: dict[str, Any] | None,
    benchmark_evidence: dict[str, Any] | None,
    evidence_integrity: EvidenceIntegrity | None = None,
    runbook: dict[str, Any] | None = None,
) -> str:
    draft = complete_with_purpose(
        llm,
        "Paper writing. You write concise Chinese academic Markdown. Use only provided evidence and experimental results.",
        _paper_prompt(topic, review, ideas, plan, analysis, config, failure_analysis, experiment_decision, hypothesis_outcome, claim_boundary_preflight, benchmark_evidence, evidence_integrity, runbook),
        stage="paper_writing",
        purpose="paper writing",
        requires_validation=True,
    )
    draft = _strip_code_fence(draft).strip()
    valid = _looks_like_paper(draft, citation_keys, claim_boundaries, claim_boundary_preflight)
    record_validation_result(llm, stage="paper_writing", valid=valid, error="paper draft failed structure/evidence validation")
    if valid:
        return draft
    return ""


def _paper_prompt(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    config: PaperConfig,
    failure_analysis: dict[str, Any] | None = None,
    experiment_decision: dict[str, Any] | None = None,
    hypothesis_outcome: dict[str, Any] | None = None,
    claim_boundary_preflight: dict[str, Any] | None = None,
    benchmark_evidence: dict[str, Any] | None = None,
    evidence_integrity: EvidenceIntegrity | None = None,
    runbook: dict[str, Any] | None = None,
) -> str:
    best = ideas[0]
    paper_entries = _citation_entries(review)
    paper_titles = [f"[{key}] {paper.title} ({paper.year}, {paper.venue})" for key, paper in paper_entries[:8]]
    citation_keys = _citation_keys(review, ideas, plan)
    claim_boundaries = _claim_boundaries(failure_analysis, experiment_decision, hypothesis_outcome, claim_boundary_preflight)
    integrity_constraint = evidence_integrity_prompt_constraint(evidence_integrity)
    return "\n".join(
        [
            *([integrity_constraint] if integrity_constraint else []),
            f"课题：{topic}",
            f"目标场景：{config.target_venue}；写作风格：{config.style}",
            "请写一篇中文 Markdown 论文草稿，必须包含这些二级标题：摘要、引言、相关工作、方法、结果、局限性、结论、代码和数据可用性、复现清单。",
            "不要编造不存在的实验结果；所有结论必须受下面证据约束。",
            "正文中的文献性主张必须使用方括号 citation key，例如 [key]；只能使用下列 citation keys：",
            ", ".join(citation_keys) if citation_keys else "当前没有可用 citation key，必须标记待人工补充。",
            "文献综述：",
            review.summary,
            "代表性文献：",
            "\n".join(f"- {title}" for title in paper_titles),
            "引用角色表要求：",
            "\n".join(_citation_role_table_lines(review)) or "当前没有可用 citation key；不要用文献支撑实验结论。",
            "研究空白：",
            "\n".join(f"- {gap}" for gap in review.gaps),
            "选定 idea：",
            f"标题：{best.title}\n假设：{best.hypothesis}\n机制：{best.mechanism}\n预期贡献：{best.expected_contribution}",
            "多智能体职责：",
            _agent_role_prompt_text(best, plan),
            "实验计划：",
            f"目标：{plan.objective}\n协议：" + "；".join(plan.protocol),
            "结果分析：",
            analysis.headline,
            "主要发现：",
            "\n".join(f"- {finding}" for finding in analysis.findings),
            "结果边界/失败分析约束：",
            "\n".join(f"- {item}" for item in claim_boundaries) or "如果提供了失败/负结果分析，必须新增“结果边界”小节并逐条响应。",
            "实验后决策：",
            _decision_prompt_text(experiment_decision),
            "假设结果审计：",
            _hypothesis_outcome_prompt_text(hypothesis_outcome),
            "Claim 边界预检：",
            _claim_preflight_prompt_text(claim_boundary_preflight),
            "Benchmark 证据审计：",
            _benchmark_evidence_prompt_text(benchmark_evidence),
            "Runbook 摘要：",
            _runbook_prompt_text(runbook),
            "Artifact 索引要求：",
            _artifact_index_prompt_text(benchmark_evidence),
            "局限性：",
            "\n".join(f"- {limitation}" for limitation in analysis.limitations),
        ]
    )


def _looks_like_paper(
    text: str,
    citation_keys: list[str] | None = None,
    claim_boundaries: list[str] | None = None,
    claim_boundary_preflight: dict[str, Any] | None = None,
) -> bool:
    required = ["摘要", "相关工作", "方法", "结果", "局限", "结论"]
    has_structure = text.startswith("#") and len(text) > 120 and sum(1 for item in required if item in text) >= 5
    if not has_structure:
        return False
    keys = [key for key in citation_keys or [] if key.strip()]
    if not keys:
        return True
    if not any(f"[{key}]" in text for key in keys):
        return False
    has_boundary_section = "结果边界" in text or "结论边界" in text
    if claim_boundaries and not has_boundary_section:
        return False
    if _preflight_needs_boundary(claim_boundary_preflight) and not has_boundary_section:
        return False
    if _violates_preflight(text, claim_boundary_preflight):
        return False
    return True


def _strip_code_fence(text: str) -> str:
    if text.strip().startswith("```"):
        lines = text.strip().splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def _fallback_paper(
    topic: str,
    review: LiteratureReview,
    ideas: list[ResearchIdea],
    plan: ExperimentPlan,
    analysis: Analysis,
    config: PaperConfig,
    claim_boundaries: list[str] | None = None,
    claim_boundary_preflight: dict[str, Any] | None = None,
    benchmark_evidence: dict[str, Any] | None = None,
    runbook: dict[str, Any] | None = None,
) -> str:
    best = ideas[0]
    paper_entries = _citation_entries(review)
    citation_role_lines = _citation_role_table_lines(review)
    boundaries = claim_boundaries or []
    benchmark_scope = _benchmark_scope_text(benchmark_evidence)
    scoped = _scoped_paper_inputs(best, plan, analysis, benchmark_evidence, runbook)
    title_suffix = benchmark_scope.get("title_suffix", "可复现实验草稿")
    lines = [
        f"# {scoped['title']}：围绕“{topic}”的{title_suffix}",
        "",
        "## 摘要",
        (
            f"本文围绕“{topic}”给出一个受运行产物约束的{benchmark_scope['result_label']}。"
            "文献引用仅用于标注数据来源、API 入口和背景 baseline，不用于证明协议有效性或性能优势；逐条职责见引用角色表。"
            f"当前草稿保留文献、idea、实验计划、结果和分析等中间产物，{benchmark_scope['continuation']}{benchmark_scope['evidence_sentence']}："
            f"{scoped['headline']}"
        ),
        "",
        "## 1. 引言",
        (
            f"本文不把“{topic}”写成已验证的通用 benchmark 协议。"
            "方法选择、实验可复现性和评价指标一致性在这里只作为本次写作与审计需要避免越界的内部风险，"
            "不是由当前 Iris smoke run 证明的领域性结论。"
            "本文将文献限定为数据来源、API 入口和背景 baseline 的说明材料；实验性表述只来自 04-experiment-runbook、04-results 和 04-statistics。"
        ),
        "",
        "## 多智能体责任边界",
        _agent_role_prompt_text(best, plan),
        "",
        "## 2. 相关工作",
            _related_work_summary(review, benchmark_evidence, scoped),
        "",
        "代表性文献：",
    ]
    for key, paper in paper_entries[:5]:
        lines.append(f"- [{key}] {paper.title}（{paper.year}，{paper.venue}）")
    if citation_role_lines:
        lines.extend(["", "引用角色表："])
        lines.extend(citation_role_lines)
    lines.extend(
        [
            "",
            "## 3. 方法",
            f"选定 idea：**{scoped['title']}**。",
            "",
            f"本次可检验问题：{scoped['hypothesis']}",
            "",
            "文献依据：见引用角色表；本次实验性结果只由 runbook/results/statistics 支撑。",
            "",
            f"对齐空白：{scoped.get('gap_alignment') or best.gap_alignment or '待人工确认'}。",
            "",
            f"实验目标：{scoped['objective']}",
            "",
            f"Baseline：{scoped['baseline']}",
            "",
            "数据、split 与执行环境：",
        ]
    )
    lines.extend(f"- {item}" for item in scoped.get("data_protocol_lines", []))
    artifact_index_lines = scoped.get("artifact_index_lines") if isinstance(scoped.get("artifact_index_lines"), list) else []
    if artifact_index_lines:
        lines.extend(["", "Artifact 索引："])
        lines.extend(f"- {item}" for item in artifact_index_lines)
    lines.extend(
        [
            "",
            "evidence_grade 定义：",
        ]
    )
    lines.extend(f"- {item}" for item in scoped.get("evidence_grade_lines", []))
    data_provenance_lines = scoped.get("data_provenance_lines") if isinstance(scoped.get("data_provenance_lines"), list) else []
    if data_provenance_lines:
        lines.extend(["", "数据 provenance 与 split 复现："])
        lines.extend(f"- {item}" for item in data_provenance_lines)
    baseline_scope_lines = scoped.get("baseline_scope_lines") if isinstance(scoped.get("baseline_scope_lines"), list) else []
    if baseline_scope_lines:
        lines.extend(["", "未运行 baseline 清单："])
        lines.extend(f"- {item}" for item in baseline_scope_lines)
    lines.extend(
        [
            "",
            "实验协议：",
        ]
    )
    lines.extend(f"- {step}" for step in scoped["protocol"])
    lines.extend(["", "评估指标："])
    lines.extend(f"- {METRIC_LABELS.get(metric, metric)}" for metric in scoped["metrics"])
    lines.extend(["", "## 4. 结果", scoped["headline"], "", "主要发现："])
    lines.extend(f"- {finding}" for finding in scoped["findings"])
    role_lines = scoped.get("role_metric_lines") if isinstance(scoped.get("role_metric_lines"), list) else []
    if role_lines:
        lines.extend(["", "实际执行角色指标："])
        lines.extend(f"- {line}" for line in role_lines)
    ablation_lines = scoped.get("ablation_interpretation_lines") if isinstance(scoped.get("ablation_interpretation_lines"), list) else []
    if ablation_lines:
        lines.extend(["", "Ablation 诊断解释："])
        lines.extend(f"- {line}" for line in ablation_lines)
    result_table = scoped.get("result_table_lines") if isinstance(scoped.get("result_table_lines"), list) else []
    if result_table:
        lines.extend(["", "完整 per-repeat 结果表："])
        lines.extend(result_table)
    audit_lines = scoped.get("audit_summary_lines") if isinstance(scoped.get("audit_summary_lines"), list) else []
    if audit_lines:
        lines.extend(["", "可审计产物摘要："])
        lines.extend(f"- {line}" for line in audit_lines)
    lines.extend(["", "## 5. 局限性"])
    limitation_lines = [_scope_result_sentence(limitation) for limitation in analysis.limitations] if _is_real_benchmark(benchmark_evidence) else analysis.limitations
    lines.extend(f"- {limitation}" for limitation in limitation_lines)
    lines.extend(["", "## 结果边界"])
    if boundaries:
        lines.extend(f"- {item}" for item in boundaries)
    else:
        lines.append("- 当前结果边界由 04-result-validation、04-failure-analysis 和 04-statistics 审计约束；正式结论不得超出这些产物支持范围。")
    if isinstance(claim_boundary_preflight, dict):
        lines.extend(["", "## Claim 边界预检"])
        lines.append(f"- 状态：{claim_boundary_preflight.get('status') or '-'}")
        lines.append(f"- 写作模式：{claim_boundary_preflight.get('writing_mode') or '-'}")
        allowed = _as_string_list(claim_boundary_preflight.get("allowed_claims"))
        prohibited = _as_string_list(claim_boundary_preflight.get("prohibited_claims"))
        if allowed:
            lines.append("- 允许表述：" + "；".join(allowed[:3]))
        if prohibited:
            lines.append("- 禁止表述：" + "；".join(prohibited[:3]))
    lines.extend(
        [
            "",
            "## 6. 结论",
            (
                f"当前草稿已经把数据/背景引用、研究假设、实验计划和{benchmark_scope['chain_label']}串联为一个内部可复核记录。"
                f"{benchmark_scope['conclusion_boundary']}"
                "本文的主要价值在于给出一个可以继续人工审阅和复现实验的结构化起点；引用只承担来源、API 和背景说明职责。"
            ),
            "",
            "## 参考证据",
        ]
    )
    for key, paper in paper_entries[:8]:
        lines.append(f"- [{key}] {paper.title}（{paper.year}，{paper.venue}）。{paper.url}")
    lines.extend(
        [
            "",
            "## 复现清单",
            "- 所有中间产物都保存在本次 run 目录中。",
            "- 实验配置记录在 `03-experiment-plan.json`。",
            "- 实验结果记录在 `04-results.json` 和 `04-results.csv`。",
            "- 实验 runbook 记录在 `04-experiment-runbook.md/json`，包含命令、随机种子、执行状态和产物哈希。",
            "- 统计可视化记录在 `04-statistics-figure.svg/json`，用于检查差值、置信区间和不确定指标。",
            "- 正式投稿前，应把论文中的每个关键主张映射到实验产物或文献引用。",
            "",
            "## 代码和数据可用性",
            benchmark_scope["availability"],
            "",
            f"_目标场景：{config.target_venue}；写作风格：{config.style}。_",
        ]
    )
    return "\n".join(lines)


def _citation_entries(review: LiteratureReview) -> list[tuple[str, Paper]]:
    return [(citation_key_for_paper(paper, index), paper) for index, paper in enumerate(review.papers, start=1)]


def _citation_keys(review: LiteratureReview, ideas: list[ResearchIdea], plan: ExperimentPlan) -> list[str]:
    valid_entries = [key for key, _ in _citation_entries(review)]
    valid = set(valid_entries)
    values: list[str] = [*valid_entries]
    for idea in ideas:
        values.extend(key for key in idea.evidence_keys if str(key).strip().strip("[]") in valid)
    values.extend(key for key in plan.evidence_keys if str(key).strip().strip("[]") in valid)
    return _unique([str(value).strip().strip("[]") for value in values if str(value).strip()])


def _claim_boundaries(
    failure_analysis: dict[str, Any] | None,
    experiment_decision: dict[str, Any] | None = None,
    hypothesis_outcome: dict[str, Any] | None = None,
    claim_boundary_preflight: dict[str, Any] | None = None,
) -> list[str]:
    values: list[str] = []
    if isinstance(failure_analysis, dict) and isinstance(failure_analysis.get("claim_boundaries"), list):
        values.extend(str(item).strip() for item in failure_analysis.get("claim_boundaries", []) if str(item).strip())
    if isinstance(experiment_decision, dict) and isinstance(experiment_decision.get("claim_boundaries"), list):
        values.extend(str(item).strip() for item in experiment_decision.get("claim_boundaries", []) if str(item).strip())
    if isinstance(hypothesis_outcome, dict) and isinstance(hypothesis_outcome.get("claim_boundaries"), list):
        values.extend(str(item).strip() for item in hypothesis_outcome.get("claim_boundaries", []) if str(item).strip())
    if isinstance(claim_boundary_preflight, dict) and isinstance(claim_boundary_preflight.get("required_boundary_statements"), list):
        values.extend(str(item).strip() for item in claim_boundary_preflight.get("required_boundary_statements", []) if str(item).strip())
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped[:10]


def _decision_prompt_text(experiment_decision: dict[str, Any] | None) -> str:
    if not isinstance(experiment_decision, dict):
        return "未提供 04-experiment-decision；保持保守表述。"
    parts = [
        f"decision={experiment_decision.get('decision') or '-'}",
        f"status={experiment_decision.get('status') or '-'}",
        f"paper_policy={experiment_decision.get('paper_policy') or '-'}",
    ]
    actions = experiment_decision.get("next_actions") if isinstance(experiment_decision.get("next_actions"), list) else []
    if actions:
        parts.append("next_actions=" + "；".join(str(item) for item in actions[:4]))
    return "\n".join(parts)


def _hypothesis_outcome_prompt_text(hypothesis_outcome: dict[str, Any] | None) -> str:
    if not isinstance(hypothesis_outcome, dict):
        return "未提供 04-hypothesis-outcome；保持保守表述。"
    parts = [
        f"outcome={hypothesis_outcome.get('outcome') or '-'}",
        f"status={hypothesis_outcome.get('status') or '-'}",
        f"support_score={hypothesis_outcome.get('support_score') if hypothesis_outcome.get('support_score') is not None else '-'}",
        f"paper_statement={hypothesis_outcome.get('paper_statement') or '-'}",
    ]
    actions = hypothesis_outcome.get("next_actions") if isinstance(hypothesis_outcome.get("next_actions"), list) else []
    if actions:
        parts.append("next_actions=" + "；".join(str(item) for item in actions[:4]))
    return "\n".join(parts)


def _claim_preflight_prompt_text(claim_boundary_preflight: dict[str, Any] | None) -> str:
    if not isinstance(claim_boundary_preflight, dict):
        return "未提供 04-claim-boundary-preflight；保持保守表述。"
    parts = [
        f"status={claim_boundary_preflight.get('status') or '-'}",
        f"writing_mode={claim_boundary_preflight.get('writing_mode') or '-'}",
        f"risk_score={claim_boundary_preflight.get('risk_score') if claim_boundary_preflight.get('risk_score') is not None else '-'}",
    ]
    constraints = _as_string_list(claim_boundary_preflight.get("prompt_constraints"))
    if constraints:
        parts.append("constraints=" + "；".join(constraints[:8]))
    return "\n".join(parts)


def _benchmark_evidence_prompt_text(benchmark_evidence: dict[str, Any] | None) -> str:
    if not isinstance(benchmark_evidence, dict):
        return "未提供 04-benchmark-evidence-audit；不要把结果写成正式公开 benchmark 结论。"
    parts = [
        f"status={benchmark_evidence.get('status') or '-'}",
        f"evidence_grade={benchmark_evidence.get('evidence_grade') or '-'}",
        f"claim_policy={benchmark_evidence.get('claim_policy') or '-'}",
    ]
    if benchmark_evidence.get("evidence_grade") == "real_benchmark":
        parts.append("写作约束=结果来自已执行的真实 benchmark adapter/runbook；不得误写为 dry-run、scaffold 或模拟实验，但仍需说明 scope、重复次数、baseline/ablation 和外部泛化边界。")
    return "\n".join(parts)


def _benchmark_scope_text(benchmark_evidence: dict[str, Any] | None) -> dict[str, str]:
    grade = str(benchmark_evidence.get("evidence_grade") or "") if isinstance(benchmark_evidence, dict) else ""
    if grade == "real_benchmark":
        return {
            "result_label": "内部已执行 benchmark adapter artifact/smoke-run report",
            "chain_label": "内部已执行 benchmark adapter artifact/smoke-run report",
            "title_suffix": "artifact/smoke-run report（单环境）",
            "continuation": "便于后续扩展到更多公开 benchmark、外部复现和更大规模统计检验；当前稿件本身只定位为单环境 smoke run 记录。",
            "evidence_sentence": "内部产物审计将本次 run 标记为 evidence_grade=real_benchmark，含义仅是 adapter 命令实际执行并留下 runbook/results/statistics，而不是 dry-run、scaffold 或模拟替代",
            "conclusion_boundary": "这些结果只能支持当前 manifest、seed、candidate/baseline/ablation、固定 split 和单一环境范围内的执行一致性观察，不能自动外推为跨数据集、跨环境、故障检测或任务族优势结论。",
            "availability": "当前原型代码、benchmark manifest、数据来源、实验计划、结果、统计审计和 runbook 均保存在本次运行产物中，用于内部复查。正式投稿或公开发布前，需要补充公开代码仓库、版本标签、许可证、归档 DOI、数据访问条件和限制说明；若扩展到更多 benchmark，应同步归档新增 manifest、split、grader 和重复运行日志。",
        }
    return {
        "result_label": "初步模拟结果",
        "chain_label": "模拟结果",
        "title_suffix": "可复现实验草稿",
        "continuation": "便于后续替换为真实领域 benchmark。",
        "evidence_sentence": "默认模拟实验显示",
        "conclusion_boundary": "但模拟结果不能直接支持正式科学结论；正式研究仍需替换为真实数据集、领域实验脚本、重复试验和统计检验。",
        "availability": "当前原型代码、实验计划、结果、统计审计和 runbook 均保存在本次运行产物中，用于内部复查。正式投稿或公开发布前，需要补充公开代码仓库、版本标签、许可证、归档 DOI、真实数据集来源、访问条件和限制说明；若继续使用模拟实验，应明确其不能替代真实 benchmark 结果。",
        }


def _related_work_summary(review: LiteratureReview, benchmark_evidence: dict[str, Any] | None, scoped: dict[str, Any]) -> str:
    if not _is_real_benchmark(benchmark_evidence):
        return review.summary
    role_text = str(scoped.get("role_text") or "candidate/baseline/ablation")
    future_models = "Dummy stratified、逻辑回归、RBF-SVM、决策树"
    if "knn" not in role_text.lower() and "neighbor" not in role_text.lower():
        future_models = "Dummy stratified、逻辑回归、KNN、RBF-SVM、决策树"
    return (
        "相关文献和 API 文档提供了 Iris 数据 provenance、经典分类器入口和后续可扩展 baseline 背景。"
        "本次实证部分只覆盖当前 runbook 实际执行的 "
        f"{role_text}；"
        f"{future_models}等未运行模型只作为后续扩展或背景，不作为本次已比较结果。"
        "Fisher 原始测量、UCI 数据集页面和 scikit-learn loader/API 文档在本文中分别承担数据来源和实现入口说明，不用于支撑协议有效性或性能优越性。"
    )


def _citation_role_table_lines(review: LiteratureReview) -> list[str]:
    entries = _citation_entries(review)
    if not entries:
        return []
    lines = [
        "| Citation key | 本文角色 | 可支撑事实 | 明确边界 |",
        "| --- | --- | --- | --- |",
    ]
    for key, paper in entries[:8]:
        role, supported, boundary = _citation_role_for_key(key, paper)
        lines.append(f"| [{key}] | {_table_cell(role)} | {_table_cell(supported)} | {_table_cell(boundary)} |")
    return lines


def _citation_role_for_key(key: str, paper: Paper) -> tuple[str, str, str]:
    lowered = key.lower()
    title = (paper.title or "").lower()
    if lowered.startswith("fisher1936iris"):
        return (
            "Iris 数据 provenance",
            "Fisher Iris / UCI Machine Learning Repository 数据集与原始测量来源背景。",
            "不支撑本次 adapter 协议有效性、性能优势或统计显著性。",
        )
    if lowered.startswith("seed2024review"):
        return (
            "UCI repository/dataset metadata",
            "UCI Iris 数据页面、数据集描述和 repository 入口。",
            "不支撑本次实验结果或跨环境泛化。",
        )
    if lowered.startswith("seedndscikitlearn7") or "load_iris" in title:
        return (
            "scikit-learn load_iris provenance fallback",
            "load_iris API 和内置 Iris 数据入口说明。",
            "不支撑本次 runbook 之外的数据处理或结果有效性。",
        )
    if lowered.startswith("seedndscikitlearn6") or "nearest neighbors" in title or "k-nearest" in title:
        return (
            "KNN API/background",
            "scikit-learn KNeighborsClassifier / k-Nearest Neighbors Iris classification baseline 的实现入口和背景。",
            "只作已运行 knn3 baseline 的 API 背景；数值结果仍以 04-results/04-statistics 为准。",
        )
    if "logistic" in title or "lightgbm" in title or "bilstm" in title or "sentiment" in title:
        return (
            "external benchmark/baseline background only",
            f"{paper.title} 的 benchmark/baseline 术语背景。",
            "不是 Iris 数据、sklearn API 或本次 protocol validity 的证据。",
        )
    if lowered.startswith("seedndscikitlearn3") or "svm" in title or "rbf" in title:
        return (
            "SVC/RBF API background",
            "RBF-SVM 作为后续 baseline 扩展的 API 背景。",
            "RBF-SVM 未在本次 runbook 中执行，不能写成本次已比较 baseline。",
        )
    if lowered.startswith("akrom2025a1") or "iris benchmark" in title:
        return (
            "Iris benchmark/application background only",
            f"{paper.title} 作为近期 Iris benchmark dataset / binary classification application 语境示例。",
            "不支撑本次 protocol validity、real_benchmark 等级、性能优势或外部泛化。",
        )
    if lowered.startswith("seedndscikitlearn"):
        return (
            "sklearn baseline API background",
            "对应 sklearn classifier/baseline 的 API 背景。",
            "除非 runbook/results 明确出现，否则不能写成本次已运行结果。",
        )
    return (
        "background-only",
        f"{paper.title} 的背景材料。",
        "不支撑未在本次实验产物中出现的结果、协议有效性或泛化 claim。",
    )


def _scoped_paper_inputs(
    idea: ResearchIdea,
    plan: ExperimentPlan,
    analysis: Analysis,
    benchmark_evidence: dict[str, Any] | None,
    runbook: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not _is_real_benchmark(benchmark_evidence):
        return {
            "title": idea.title,
            "hypothesis": idea.hypothesis,
            "objective": plan.objective,
            "baseline": plan.baseline or idea.baseline or "待人工确认",
            "protocol": plan.protocol,
            "metrics": plan.metrics,
            "headline": analysis.headline,
            "findings": analysis.findings,
        }
    roles = _role_names_from_analysis(analysis)
    role_text = _role_summary(roles)
    metrics = _real_benchmark_metrics(plan.metrics, analysis)
    role_metric_lines = _role_metric_lines(analysis)
    return {
        "title": "Iris Benchmark Adapter Smoke Run 报告",
        "role_text": role_text.strip(),
        "gap_alignment": (
            "本次只检查固定 split 和单一环境下的 adapter 执行记录是否完整；"
            "原始空白中的跨机器/CI 方差、release flow、故障检测率和更多 sklearn baseline（如逻辑回归/RBF-SVM/决策树）比较均未完成验证。"
        ),
        "hypothesis": (
            "在同一 UCI Iris 数据、同一 stratified split、同一运行环境和三次重复下，"
            f"{role_text}能否通过同一 benchmark adapter 产生可审计的描述性指标。"
            "跨机器/CI 方差、故障注入检测率和更大任务族泛化不是本次已检验结果。"
        ),
        "objective": (
            "记录当前 manifest/runbook 中已执行的 candidate、baseline、ablation 和 reference smoke benchmark，"
            "报告 accuracy、macro_f1、error_rate、train_cases 与 test_cases 等描述性结果；"
            "不把预注册中的扩展 baseline、故障检测率或 release flow 写成已完成实证贡献。"
        ),
        "baseline": _real_benchmark_baseline_text(roles, plan.baseline or idea.baseline),
        "protocol": _real_benchmark_protocol(roles),
        "metrics": metrics,
        "headline": _scope_result_sentence(analysis.headline),
        "findings": [_scope_result_sentence(item) for item in analysis.findings],
        "role_metric_lines": role_metric_lines,
        "ablation_interpretation_lines": _ablation_interpretation_lines(analysis),
        "result_table_lines": _result_table_lines(analysis, runbook),
        "data_protocol_lines": _data_protocol_lines(analysis, runbook),
        "artifact_index_lines": _artifact_index_lines(),
        "data_provenance_lines": _data_provenance_lines(runbook),
        "baseline_scope_lines": _baseline_scope_lines(roles),
        "evidence_grade_lines": _evidence_grade_lines(benchmark_evidence),
        "audit_summary_lines": _audit_summary_lines(benchmark_evidence, analysis),
    }


def _is_real_benchmark(benchmark_evidence: dict[str, Any] | None) -> bool:
    return isinstance(benchmark_evidence, dict) and str(benchmark_evidence.get("evidence_grade") or "") == "real_benchmark"


def _role_names_from_analysis(analysis: Analysis) -> dict[str, list[str]]:
    roles = {"candidate": [], "baseline": [], "ablation": [], "reference": []}
    for row in analysis.metric_table:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        role = _role_from_name(name)
        if role in roles and name not in roles[role]:
            roles[role].append(name)
    return roles


def _role_summary(roles: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for role in ["candidate", "baseline", "ablation", "reference"]:
        if roles.get(role):
            parts.append(f"{role}={roles[role][0]}")
    return "、".join(parts) + " " if parts else "candidate/baseline/ablation "


def _real_benchmark_baseline_text(roles: dict[str, list[str]], fallback: str | None) -> str:
    if roles.get("baseline"):
        baseline = roles["baseline"][0]
        lowered = baseline.lower()
        if "majority" in lowered:
            return (
                f"本次结果中的 baseline 是 `{baseline}`，即当前 adapter 已执行并写入 04-results/04-statistics 的对照。"
                "这是一个很弱的 majority baseline，只能作为 sanity check；Dummy stratified、RBF-SVM、KNN、逻辑回归、决策树等只作为后续扩展或文献/API 背景，不在本次结果中冒充已比较 baseline。"
            )
        if "knn" in lowered or "nearest-neighbor" in lowered or "neighbor" in lowered:
            text = (
                f"本次结果中的 baseline 是 `{baseline}`，即当前 adapter 已执行并写入 04-results/04-statistics 的对照。"
                "它是同一 frozen split 上的 deterministic k-nearest-neighbor 直接对照；本文只报告与该已运行 baseline 的描述性差异，不把未运行的逻辑回归、RBF-SVM 或决策树写成已比较结果。"
            )
            if roles.get("reference"):
                text += f" 另有 reference baseline `{roles['reference'][0]}` 作为 sanity check 写入 04-results/runbook，但不进入主 candidate-vs-knn3 统计比较。"
            return text
        return (
            f"本次结果中的 baseline 是 `{baseline}`，即当前 adapter 已执行并写入 04-results/04-statistics 的对照。"
            "本文只报告与该已运行 baseline 的描述性差异，不把未运行的逻辑回归、RBF-SVM 或决策树写成已比较结果。"
        )
    return (fallback or "待人工确认") + "；本稿只报告 04-results/04-statistics 中实际出现的 baseline。"


def _real_benchmark_protocol(roles: dict[str, list[str]]) -> list[str]:
    role_text = _role_summary(roles).strip() or "candidate/baseline/ablation"
    return [
        "使用 04-experiment-runbook.json 记录的 benchmark adapter 命令、运行环境、repeat_index、seed 和 artifact hash。",
        f"只报告 04-results.json 中实际执行的角色：{role_text}。",
        "用 04-statistics.json 汇总 accuracy、macro_f1、error_rate、train_cases 和 test_cases；固定 split 下的零方差/单点区间不作为显著性、稳定性或鲁棒性证据。",
        "三次 repeat 使用同一 stratified split；本文把它解释为执行一致性检查，而不是独立统计重复实验。",
        "将跨机器/CI 方差、故障注入检测率、manifest pass rate 和更多未运行 sklearn baseline 明确列为未检验项或下一轮工作。",
    ]


def _real_benchmark_metrics(plan_metrics: list[str], analysis: Analysis) -> list[str]:
    values: list[str] = []
    for row in analysis.metric_table:
        if not isinstance(row, dict):
            continue
        values.extend(str(key) for key in row if key not in {"name", "status", "repeat_index"})
    if not values:
        values = plan_metrics
    return _unique([value for value in values if value])


def _scope_result_sentence(text: str) -> str:
    value = str(text).strip()
    value = _strip_degenerate_ci(value)
    value = value.replace(
        "差值=0.000；差异跨过 0，需要更多重复实验确认。",
        "差值=0.000；当前 repeat 未观察到 candidate-baseline 数值差异，零宽区间不支持显著性或跨环境稳定性结论。",
    )
    replacements = {
        "candidate 在该指标上优于 baseline。": "该差值仅作为当前同一 split、同一环境和三次重复下的描述性 smoke 结果；不构成显著性或跨环境稳定性结论。",
        "candidate 在该指标上高于 baseline。": "该差值仅作为当前同一 split、同一环境和三次重复下的描述性 smoke 结果；不构成显著性或跨环境稳定性结论。",
        "candidate 在该指标上未优于 baseline。": "candidate 与当前 baseline 在该指标上的描述性均值持平或未形成优势。",
        "candidate 在 accuracy 上优于 baseline": "candidate 与当前 baseline 的 accuracy 描述性均值存在差值",
        "candidate 在 error_rate 上优于 baseline": "candidate 与当前 baseline 的 error_rate 描述性均值存在差值",
        "candidate 在 macro_f1 上优于 baseline": "candidate 与当前 baseline 的 macro_f1 描述性均值存在差值",
        "显著优于": "在当前描述性统计中数值不同于",
        "显著提高": "在当前描述性统计中提高",
        "显著降低": "在当前描述性统计中降低",
        "优于 baseline": "相对当前 baseline 的描述性差值",
        "优于基线": "相对当前基线的描述性差值",
        "只能支撑 benchmark provenance、manifest 合约和流程诊断类结论": "只能支撑当前运行的 benchmark provenance、manifest 合约和 artifact 完整性观察",
        "流程诊断类结论": "artifact 完整性观察",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    if ("95% CI" in value or "置信区间" in value or "效应量=NA" in value) and "不构成显著性" not in value:
        value += "；由于当前重复结果无变异或效应量为 NA，本文不据此作显著性、鲁棒性或稳定性结论。"
    return value


def _strip_degenerate_ci(text: str) -> str:
    value = re.sub(r"，?95% CI=\[[^\]]+\]，?效应量=NA", "", text)
    value = re.sub(r"，?95% CI=\[[^\]]+\]", "", value)
    value = value.replace("，；", "；").replace("，，", "，")
    return value


def _role_metric_lines(analysis: Analysis) -> list[str]:
    by_role: dict[str, list[dict[str, Any]]] = {"candidate": [], "baseline": [], "ablation": [], "reference": []}
    for row in analysis.metric_table:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        role = _role_from_name(name)
        if role in by_role:
            by_role[role].append(row)
    lines: list[str] = []
    for role in ["candidate", "baseline", "ablation", "reference"]:
        rows = sorted(by_role.get(role) or [], key=lambda item: int(item.get("repeat_index", 0) or 0))
        for row in rows[:6]:
            metrics = []
            if "repeat_index" in row:
                metrics.append(f"repeat={row['repeat_index']}")
            for key in ["accuracy", "macro_f1", "error_rate", "train_cases", "test_cases"]:
                if key in row:
                    metrics.append(f"{key}={row[key]}")
            lines.append(f"{role} `{row.get('name')}`: " + "，".join(metrics))
        if len(rows) > 6:
            lines.append(f"{role} `{rows[0].get('name')}`: 另有 {len(rows) - 6} 条 repeat 记录见 04-results.json。")
    return lines


def _ablation_interpretation_lines(analysis: Analysis) -> list[str]:
    rows = [row for row in analysis.metric_table if isinstance(row, dict)]
    candidates = [row for row in rows if _role_from_name(str(row.get("name") or "")) == "candidate"]
    baselines = [row for row in rows if _role_from_name(str(row.get("name") or "")) == "baseline"]
    ablations = [row for row in rows if _role_from_name(str(row.get("name") or "")) == "ablation"]
    if not ablations:
        return []
    ablation_name = str(ablations[0].get("name") or "ablation")
    lines = [
        (
            f"`{ablation_name}` 是 sepal-only centroid ablation：它保留同一 grader、data、split、repeat 和 metrics schema，"
            "但只使用 sepal length/width 两个特征计算类中心，用于检查 adapter 是否能暴露特征子集退化。"
        )
    ]
    candidate_accuracy = _mean_metric(candidates, "accuracy")
    baseline_accuracy = _mean_metric(baselines, "accuracy")
    ablation_accuracy = _mean_metric(ablations, "accuracy")
    candidate_f1 = _mean_metric(candidates, "macro_f1")
    baseline_f1 = _mean_metric(baselines, "macro_f1")
    ablation_f1 = _mean_metric(ablations, "macro_f1")
    if ablation_accuracy is not None:
        parts = [f"ablation accuracy={_format_number(ablation_accuracy)}"]
        if candidate_accuracy is not None:
            parts.append(f"candidate accuracy={_format_number(candidate_accuracy)}")
        if baseline_accuracy is not None:
            parts.append(f"baseline accuracy={_format_number(baseline_accuracy)}")
        lines.append("Ablation 结果摘要：" + "，".join(parts) + "；该差异只说明当前 fixed split 上 sepal-only 版本退化，不构成跨数据集诊断能力结论。")
    if ablation_f1 is not None:
        parts = [f"ablation macro_f1={_format_number(ablation_f1)}"]
        if candidate_f1 is not None:
            parts.append(f"candidate macro_f1={_format_number(candidate_f1)}")
        if baseline_f1 is not None:
            parts.append(f"baseline macro_f1={_format_number(baseline_f1)}")
        lines.append("Ablation macro-F1 摘要：" + "，".join(parts) + "；confusion matrix 显示错误主要来自 versicolor/virginica 混淆，完整 per-repeat 见下表。")
    return lines


def _mean_metric(rows: list[dict[str, Any]], metric: str) -> float | None:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row[metric]))
        except (KeyError, TypeError, ValueError):
            continue
    return sum(values) / len(values) if values else None


def _runbook_prompt_text(runbook: dict[str, Any] | None) -> str:
    if not isinstance(runbook, dict):
        return "未提供 04-experiment-runbook；论文必须说明缺少命令、seed、环境和 artifact hash 细节。"
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    environment = runbook.get("environment") if isinstance(runbook.get("environment"), dict) else {}
    source_tree = environment.get("source_tree") if isinstance(environment.get("source_tree"), dict) else {}
    runs = [item for item in runbook.get("runs", []) if isinstance(item, dict)] if isinstance(runbook.get("runs"), list) else []
    commands = [item for item in runbook.get("commands", []) if isinstance(item, dict)] if isinstance(runbook.get("commands"), list) else []
    statuses: dict[str, int] = {}
    for run in runs:
        status = str(run.get("status") or "-")
        statuses[status] = statuses.get(status, 0) + 1
    command_text = "; ".join(_command_summary(command) for command in commands[:6]) or "-"
    status_text = ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())) or "-"
    artifact_count = sum(len(run.get("produced_artifacts") or []) for run in runs)
    return "\n".join(
        [
            f"mode={execution.get('mode') or '-'}, repeats={execution.get('repeats') or '-'}, timeout_seconds={execution.get('timeout_seconds') or '-'}",
            f"python={execution.get('python_version') or '-'}, executable={execution.get('python_executable') or '-'}, platform={execution.get('platform') or '-'}",
            f"runs={len(runs)}, statuses={status_text}, produced_artifacts={artifact_count}, source_tree_sha256={source_tree.get('aggregate_sha256') or '-'}",
            f"commands={command_text}",
            "写作要求：正文或复现清单必须报告 runbook、seed、命令、固定 split、训练/测试样本数、执行环境和 artifact hash 的入口；不得把单环境 repeat 写成独立外部复现。",
        ]
    )


def _artifact_index_prompt_text(benchmark_evidence: dict[str, Any] | None) -> str:
    if not _is_real_benchmark(benchmark_evidence):
        return "非 real_benchmark 稿件只需说明 run 目录保存了实验计划、结果和复现清单；不得编造不存在的 artifact。"
    return "正文必须包含 Artifact 索引，并逐项列出：" + "；".join(_artifact_index_lines()) + "。"


def _artifact_index_lines() -> list[str]:
    return [
        "`04-experiment-runbook.json`：adapter 命令、repeat_index、seed、执行状态、runtime 和 produced_artifacts SHA256。",
        "`04-results.json` / `04-results.csv`：candidate/baseline/ablation/reference 的 per-repeat 指标和 confusion matrix 字段。",
        "`04-statistics.json` / `04-statistics.md` / `04-statistics-figure.svg/json`：candidate-vs-baseline 描述性比较、差值和固定 split 下的不确定性限制。",
        "`03-benchmark-adapters.json`：benchmark adapter/manifest 与命令矩阵入口。",
        "`04-benchmark-result-schema-audit.json`：结果 schema、角色、指标和 per-repeat 字段一致性审计。",
        "`04-benchmark-evidence-audit.json`：evidence_grade、claim_policy、results/comparisons/repeats 计数和保留警告。",
        "`04-environment-snapshot.json`：Python、平台、工作目录和 source_tree aggregate_sha256。",
        "`run-manifest.json`：本次 run 的阶段产物清单和顶层 trace。",
        "`benchmark-adapters/*/{data,split,grade_iris.py,*_metrics.json}`：数据、split、grader 和 metrics 产物；具体 SHA256 以 runbook produced_artifacts 为准。",
    ]


def _data_provenance_lines(runbook: dict[str, Any] | None) -> list[str]:
    lines = [
        "公开来源：UCI Iris 数据集页面 `https://archive.ics.uci.edu/dataset/53/iris`，数据 DOI `10.24432/C56C76`；Fisher/UCI 引用只支持数据来源和 metadata，不支持本次协议有效性。",
        "冻结本地副本：各 adapter 使用 runbook produced_artifacts 中的 `data/iris.data`；正文列出的 data SHA256 必须与 `04-experiment-runbook.json` 中每个角色的 produced_artifacts 对齐。",
        "split 文件：`iris-stratified-test-v1.json` 记录 `source_dataset=UCI Iris`、`dataset_doi=10.24432/C56C76` 和 test_indices；当前策略是在原始按类别连续排列的 UCI 行序中每 5 行 hold out 1 行。",
        "样本顺序假设：当前 split 依赖冻结文件的行序；若外部复现从 UCI 重新下载数据，应先核对原始文件 SHA256、标签字符串和行顺序，再应用同一 test_indices。",
        "公开可访问性边界：本次报告只证明 run 目录内产物齐全；若提交给外部审稿，应把 runbook、results、statistics、split、grader、metrics JSON、环境快照和数据获取说明作为仓库或补充材料公开。",
    ]
    if isinstance(runbook, dict):
        runs = [item for item in runbook.get("runs", []) if isinstance(item, dict)] if isinstance(runbook.get("runs"), list) else []
        data_hashes = _artifact_hashes_by_suffix(runs, "data/iris.data")
        split_hashes = _artifact_hashes_by_suffix(runs, "split/iris-stratified-test-v1.json")
        grader_hashes = _artifact_hashes_by_suffix(runs, "grade_iris.py")
        if data_hashes:
            lines.append("已审计 data SHA256：" + "；".join(data_hashes[:4]) + ("；..." if len(data_hashes) > 4 else "") + "。")
        if split_hashes:
            lines.append("已审计 split SHA256：" + "；".join(split_hashes[:4]) + ("；..." if len(split_hashes) > 4 else "") + "。")
        if grader_hashes:
            lines.append("已审计 grader SHA256：" + "；".join(grader_hashes[:4]) + ("；..." if len(grader_hashes) > 4 else "") + "。")
    return lines


def _artifact_hashes_by_suffix(runs: list[dict[str, Any]], suffix: str) -> list[str]:
    values: list[str] = []
    seen: set[tuple[str, str]] = set()
    for run in runs:
        artifacts = run.get("produced_artifacts") if isinstance(run.get("produced_artifacts"), list) else []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path") or "")
            sha = str(artifact.get("sha256") or "")
            if not path.endswith(suffix) or not sha:
                continue
            key = (path, sha)
            if key in seen:
                continue
            seen.add(key)
            values.append(f"`{path}` sha256={sha}")
    return values


def _baseline_scope_lines(roles: dict[str, list[str]]) -> list[str]:
    executed = _role_summary(roles).strip() or "candidate/baseline/ablation"
    lines = [
        f"本次已执行角色只包括：{executed}；主统计比较只解释 candidate 与已运行 knn3 baseline 的描述性差值。",
        "majority_class 仅作为 reference sanity check 写入 04-results/runbook；它不是 sklearn DummyClassifier stratified，也不替代完整 baseline suite。",
        "DummyClassifier stratified：未在本次 runbook 执行；不能写成已比较结果。",
        "LogisticRegression 默认/线性 baseline：未在本次 runbook 执行；只能作为后续扩展或 API 背景。",
        "RBF-SVM/SVC 默认 baseline：未在本次 runbook 执行；seedndscikitlearn3 只提供 API 背景。",
        "DecisionTreeClassifier 默认 baseline：未在本次 runbook 执行；不能支撑当前结果段落。",
        "多 split、多随机种子、跨机器/CI 复跑和故障注入检测率：均未完成；当前稿件不据此声称 benchmark 可靠性、稳定性或诊断能力。",
    ]
    return lines


def _result_table_lines(analysis: Analysis, runbook: dict[str, Any] | None = None) -> list[str]:
    rows = [row for row in analysis.metric_table if isinstance(row, dict)]
    if not rows:
        return []
    run_lookup = _runbook_run_lookup(runbook)
    lines = [
        "| Role | Repeat | Seed | Method | Accuracy | Macro-F1 | Error | Train/Test | Runtime(s) | Confusion matrix | Metrics artifact SHA256 |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: | --- | ---: | --- | --- |",
    ]
    for row in sorted(rows, key=_result_row_sort_key):
        name = str(row.get("name") or "")
        repeat = _safe_int(row.get("repeat_index"))
        run = run_lookup.get((name, repeat), {})
        seed = str(run.get("seed") or row.get("seed") or "-")
        method = _command_option(run.get("command"), "--method") or _method_from_name(name)
        train_test = _train_test_text(row)
        runtime = _format_number(row.get("duration_seconds", run.get("duration_seconds")))
        lines.append(
            "| "
            + " | ".join(
                [
                    _table_cell(_role_from_name(name)),
                    str(repeat),
                    _table_cell(seed),
                    _table_cell(method),
                    _format_number(row.get("accuracy")),
                    _format_number(row.get("macro_f1")),
                    _format_number(row.get("error_rate")),
                    _table_cell(train_test),
                    runtime,
                    _table_cell(_confusion_summary(row)),
                    _table_cell(_metrics_artifact_hash(run)),
                ]
            )
            + " |"
        )
    return lines


def _data_protocol_lines(analysis: Analysis, runbook: dict[str, Any] | None = None) -> list[str]:
    rows = [row for row in analysis.metric_table if isinstance(row, dict)]
    if not isinstance(runbook, dict):
        base = ["未提供 04-experiment-runbook；只能从 05-analysis 中读取样本数和指标，命令、seed、环境与 artifact hash 需人工补齐。"]
        if rows:
            base.append(f"分析表记录的训练/测试样本数：{_unique_train_test(rows) or '-'}。")
        return base
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    environment = runbook.get("environment") if isinstance(runbook.get("environment"), dict) else {}
    source_tree = environment.get("source_tree") if isinstance(environment.get("source_tree"), dict) else {}
    runs = [item for item in runbook.get("runs", []) if isinstance(item, dict)] if isinstance(runbook.get("runs"), list) else []
    artifact_groups = _artifact_groups(runs)
    class_counts = _class_count_summary(rows)
    lines = [
        (
            f"数据与 split：当前 run 使用 UCI/Fisher Iris adapter 文件；训练/测试样本数为 "
            f"{_unique_train_test(rows) or '见 04-results.json'}，split 固定并在 runbook 产物中记录 SHA256。"
        ),
        (
            f"执行环境：mode={execution.get('mode') or '-'}，repeats={execution.get('repeats') or '-'}，"
            f"timeout={execution.get('timeout_seconds') or '-'}s，allowed_commands={', '.join(execution.get('allowed_commands') or []) or '-'}，"
            f"env_policy={execution.get('env_policy') or '-'}，working_directory={execution.get('working_directory') or '-'}。"
        ),
        (
            f"Python/平台：Python {execution.get('python_version') or '-'}，"
            f"executable={execution.get('python_executable') or '-'}，platform={execution.get('platform') or '-'}。"
        ),
        (
            f"代码快照：source_tree aggregate_sha256={source_tree.get('aggregate_sha256') or '-'}，"
            f"file_count={source_tree.get('file_count') or 0}；完整环境见 04-environment-snapshot.json。"
        ),
        "Split 生成规则：`iris-stratified-test-v1.json` 在 UCI 原始按类别连续排列的数据中每 5 行 hold out 1 行，形成每类 10 个 test case、40 个 train case；所有角色使用同一 split。",
        "预处理与超参数：adapter 使用原始四维 Iris 数值特征，不做标准化；nearest_centroid 使用四个特征的类均值，knn3 使用 k=3 欧氏距离近邻多数表决并按距离和打破平局，sepal_centroid 只使用 sepal length/width 两个特征。",
        "命令矩阵：" + ("；".join(_command_summary(command) for command in _runbook_commands(runbook)) or "-") + "。",
        f"Seed/重复：runbook 记录 {len(runs)} 条 run；per-repeat seed 已在结果表列出，三次 repeat 使用同一 frozen split，解释为执行一致性检查而非独立抽样。",
    ]
    if class_counts:
        lines.append(class_counts)
    for label, artifacts in artifact_groups:
        if artifacts:
            lines.append(f"{label} SHA256：" + "；".join(artifacts[:4]) + ("；..." if len(artifacts) > 4 else "") + "。")
    return lines


def _evidence_grade_lines(benchmark_evidence: dict[str, Any] | None) -> list[str]:
    if not isinstance(benchmark_evidence, dict):
        return ["未提供 benchmark evidence audit；论文只能按未审计实验草稿处理。"]
    lines = [
        (
            f"evidence_grade={benchmark_evidence.get('evidence_grade') or '-'}，status={benchmark_evidence.get('status') or '-'}，"
            f"claim_policy={benchmark_evidence.get('claim_policy') or '-'}。"
        ),
        "real_benchmark 是本系统的内部产物审计等级，含义是 adapter 命令实际执行，并留下 04-experiment-runbook、04-results、04-statistics、schema/evidence audit、environment snapshot 和 run manifest；它不是跨环境复现、外部泛化、模型优越性或故障检测有效性的证明。",
    ]
    counts = [
        f"results={benchmark_evidence.get('results')}" if benchmark_evidence.get("results") is not None else "",
        f"comparisons={benchmark_evidence.get('comparisons')}" if benchmark_evidence.get("comparisons") is not None else "",
        f"repeats={benchmark_evidence.get('repeats')}" if benchmark_evidence.get("repeats") is not None else "",
    ]
    count_text = ", ".join(item for item in counts if item)
    if count_text:
        lines.append(f"审计计数：{count_text}。")
    warnings = _as_string_list(benchmark_evidence.get("warnings"))
    required = _as_string_list(benchmark_evidence.get("required_actions"))
    if warnings:
        lines.append("保留警告：" + "；".join(warnings[:3]) + "。")
    if required:
        lines.append("需要处理：" + "；".join(required[:3]) + "。")
    return lines


def _audit_summary_lines(benchmark_evidence: dict[str, Any] | None, analysis: Analysis) -> list[str]:
    if not isinstance(benchmark_evidence, dict):
        return []
    lines = [
        "04-experiment-runbook.json：记录 benchmark adapter 命令、repeat_index、seed、执行状态和 artifact hash；正文数据协议段给出关键产物路径与 SHA256，完整清单见 runbook。",
        "04-results.json / 04-results.csv：记录已执行 adapter 的 per-repeat 数值指标；主角色为 candidate、baseline、ablation，可另含 reference/other sanity baseline；各 metrics JSON 另含 confusion_matrix、prediction_sha256、data_sha256 和 split_sha256_actual。",
        "04-statistics.json / 04-statistics.md / 04-statistics-figure.svg/json：记录 candidate-vs-baseline 描述性比较；固定 split 下零方差不用于显著性推断。",
        "split 文件：各角色使用 benchmark-adapters/<role>/split/iris-stratified-test-v1.json；训练/测试样本数由结果中的 train_cases/test_cases 给出。",
        "manifest 与 artifact trace：03-benchmark-adapters.json、run-manifest.json、04-benchmark-result-schema-audit.json、04-benchmark-evidence-audit.json 和 04-environment-snapshot.json 用于核对产物存在性、角色矩阵、环境与 trace；本文不声称完成跨环境 manifest pass-rate 实验。",
    ]
    role_lines = _role_metric_lines(analysis)
    if role_lines:
        lines.append("角色指标摘录：" + "；".join(role_lines))
    if benchmark_evidence.get("results") is not None or benchmark_evidence.get("comparisons") is not None or benchmark_evidence.get("repeats") is not None:
        lines.append(
            "审计计数："
            f"results={benchmark_evidence.get('results', '-')}, "
            f"comparisons={benchmark_evidence.get('comparisons', '-')}, "
            f"repeats={benchmark_evidence.get('repeats', '-')}。"
        )
    return lines


def _runbook_commands(runbook: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in runbook.get("commands", []) if isinstance(item, dict)] if isinstance(runbook.get("commands"), list) else []


def _command_summary(command: dict[str, Any]) -> str:
    name = str(command.get("name") or "-")
    role = str(command.get("role") or _role_from_name(name) or "-")
    argv = command.get("command") if isinstance(command.get("command"), list) else []
    method = _command_option(argv, "--method") or _method_from_name(name)
    return f"{role}/{name}: method={method}"


def _runbook_run_lookup(runbook: dict[str, Any] | None) -> dict[tuple[str, int], dict[str, Any]]:
    if not isinstance(runbook, dict) or not isinstance(runbook.get("runs"), list):
        return {}
    lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for run in runbook.get("runs", []):
        if not isinstance(run, dict):
            continue
        lookup[(str(run.get("name") or ""), _safe_int(run.get("repeat_index")))] = run
    return lookup


def _result_row_sort_key(row: dict[str, Any]) -> tuple[int, str, int]:
    role_order = {"candidate": 0, "baseline": 1, "ablation": 2, "reference": 3}
    name = str(row.get("name") or "")
    return (role_order.get(_role_from_name(name), 9), name, _safe_int(row.get("repeat_index")))


def _role_from_name(name: str) -> str:
    lowered = str(name).lower()
    if "reference" in lowered:
        return "reference"
    for role in ["candidate", "baseline", "ablation"]:
        if role in lowered:
            return role
    if "majority" in lowered:
        return "reference"
    return "-"


def _method_from_name(name: str) -> str:
    lowered = str(name).lower().replace("_", "-")
    if "3-nearest-neighbor" in lowered or "knn3" in lowered:
        return "knn3"
    if "nearest-centroid" in lowered:
        return "nearest_centroid"
    if "sepal-centroid" in lowered:
        return "sepal_centroid"
    if "majority" in lowered:
        return "majority_class"
    return "-"


def _command_option(command: Any, option: str) -> str:
    if not isinstance(command, list):
        return ""
    values = [str(item) for item in command]
    for index, item in enumerate(values):
        if item == option and index + 1 < len(values):
            return values[index + 1]
    return ""


def _train_test_text(row: dict[str, Any]) -> str:
    train = _format_number(row.get("train_cases"))
    test = _format_number(row.get("test_cases"))
    return f"{train}/{test}" if train != "-" or test != "-" else "-"


def _unique_train_test(rows: list[dict[str, Any]]) -> str:
    pairs = _unique([_train_test_text(row) for row in rows if _train_test_text(row) != "-"])
    return ", ".join(pairs)


def _class_count_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    row = rows[0]
    train = _count_values(row, "train_class_count_")
    test = _count_values(row, "test_class_count_")
    if not train and not test:
        return ""
    return "类别分布：" + "; ".join(part for part in [f"train {train}" if train else "", f"test {test}" if test else ""] if part) + "。"


def _count_values(row: dict[str, Any], prefix: str) -> str:
    parts: list[str] = []
    for key in sorted(row):
        if key.startswith(prefix):
            parts.append(f"{key.removeprefix(prefix)}={_format_number(row.get(key))}")
    return ", ".join(parts)


def _confusion_summary(row: dict[str, Any]) -> str:
    labels = [label for label in ["setosa", "versicolor", "virginica"] if any(f"cm_{label}_" in key for key in row)]
    if not labels:
        return "-"
    parts: list[str] = []
    for expected in labels:
        values = [_format_number(row.get(f"cm_{expected}_{predicted}")) for predicted in labels]
        parts.append(f"{expected} " + "/".join(values))
    return "; ".join(parts)


def _metrics_artifact_hash(run: dict[str, Any]) -> str:
    artifacts = run.get("produced_artifacts") if isinstance(run.get("produced_artifacts"), list) else []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = str(artifact.get("path") or "")
        if path.endswith("_metrics.json"):
            return f"{Path(path).name}:{_short_hash(artifact.get('sha256'))}"
    return "-"


def _artifact_groups(runs: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {"data": [], "split": [], "grader": [], "metrics": []}
    seen: set[tuple[str, str]] = set()
    for run in runs:
        artifacts = run.get("produced_artifacts") if isinstance(run.get("produced_artifacts"), list) else []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path") or "")
            sha = str(artifact.get("sha256") or "")
            if not path or not sha:
                continue
            label = ""
            if "/data/" in path:
                label = "data"
            elif "/split/" in path:
                label = "split"
            elif path.endswith("grade_iris.py"):
                label = "grader"
            elif path.endswith("_metrics.json"):
                label = "metrics"
            if not label:
                continue
            key = (label, path)
            if key in seen:
                continue
            seen.add(key)
            grouped[label].append(f"`{path}` sha256={sha}")
    return [("数据文件", grouped["data"]), ("split 文件", grouped["split"]), ("grader 脚本", grouped["grader"]), ("metrics 产物", grouped["metrics"])]


def _short_hash(value: Any, chars: int = 12) -> str:
    text = str(value or "")
    return text[:chars] if text else "-"


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_number(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}".rstrip("0").rstrip(".")


def _table_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _preflight_needs_boundary(claim_boundary_preflight: dict[str, Any] | None) -> bool:
    if not isinstance(claim_boundary_preflight, dict):
        return False
    return str(claim_boundary_preflight.get("status") or "") in {"block", "review_required"}


def _violates_preflight(text: str, claim_boundary_preflight: dict[str, Any] | None) -> bool:
    if not _preflight_needs_boundary(claim_boundary_preflight):
        return False
    patterns = _as_string_list(claim_boundary_preflight.get("prohibited_patterns") if isinstance(claim_boundary_preflight, dict) else [])
    if not patterns:
        return False
    for line in text.splitlines():
        normalized = line.strip().lower()
        if not normalized:
            continue
        if _has_negation_or_boundary_marker(normalized):
            continue
        if any(pattern.lower() in normalized for pattern in patterns):
            return True
    return False


def _has_negation_or_boundary_marker(text: str) -> bool:
    markers = ["不得", "不能", "不足以", "无法", "未", "不", "仅", "局限", "边界", "初步", "保守", "not ", "cannot", "can't", "no "]
    return any(marker in text for marker in markers)


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _agent_role_prompt_text(idea: ResearchIdea, plan: ExperimentPlan) -> str:
    roles = _unique([*idea.agent_roles, *plan.agent_roles])
    if not roles:
        return "当前没有显式 agent_roles；必须在论文中保持保守，并把未分配责任的 claim 标为待人工复核。"
    role_tasks = {
        "literature_scout": "只负责检索入口、seed 和文献覆盖，不证明实验结论。",
        "evidence_curator": "负责 citation key、metadata、全文 chunk 和引用可用性核对。",
        "gap_analyst": "负责把文献 gap 和约束转成可检验问题。",
        "method_architect": "负责 candidate、baseline、消融变量和方法机制边界。",
        "benchmark_engineer": "负责 benchmark manifest、grader、adapter、产物和复现入口。",
        "statistician": "负责主指标、repeats、比较、CI/效应量和负/中性结果边界。",
        "skeptical_reviewer": "负责 novelty、claim boundary、失败模式和禁止 superiority 越界。",
        "manuscript_editor": "负责把证据、实验、限制、AI 披露和可用性组织成论文文本。",
    }
    lines = [f"- {role}: {role_tasks.get(role, '负责对应阶段的人工可复核任务。')}" for role in roles]
    lines.append("写作时必须把文献 claim、实验 claim、统计 claim 和结论边界分别交给上述角色约束；没有 owner 的强 claim 必须降级或标记待补证。")
    return "\n".join(lines)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def markdown_to_latex(markdown: str) -> str:
    body_lines = []
    title = "科研 Agent 论文"
    in_items = False
    for line in markdown.splitlines():
        if not line.startswith("- ") and in_items:
            body_lines.append(r"\end{itemize}")
            in_items = False
        if line.startswith("# "):
            title = _escape_latex(line[2:])
        elif line.startswith("## "):
            body_lines.append(r"\section{" + _escape_latex(line[3:]) + "}")
        elif line.startswith("### "):
            body_lines.append(r"\subsection{" + _escape_latex(line[4:]) + "}")
        elif line.startswith("- "):
            if not in_items:
                body_lines.append(r"\begin{itemize}")
                in_items = True
            body_lines.append(r"\item " + _escape_latex(line[2:]))
        elif line.strip():
            body_lines.append(_escape_latex(line))
            body_lines.append("")
    if in_items:
        body_lines.append(r"\end{itemize}")
    body = "\n".join(body_lines)
    return "\n".join(
        [
            r"\documentclass{ctexart}",
            r"\usepackage[margin=1in]{geometry}",
            r"\usepackage{hyperref}",
            r"\title{" + title + "}",
            r"\author{Research Agent}",
            r"\date{\today}",
            r"\begin{document}",
            r"\maketitle",
            body,
            r"\end{document}",
            "",
        ]
    )


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)
