from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .models import ResearchScorecardReport, ScorecardDimension
from .seed_paper_intake import build_seed_paper_suggestion_report


RESEARCH_SCORECARD_JSON = "13-research-scorecard.json"
RESEARCH_SCORECARD_MD = "13-research-scorecard.md"


def write_research_scorecard_artifacts(topic: str, run_dir: Path) -> ResearchScorecardReport:
    report = build_research_scorecard_report(topic, run_dir)
    write_json(run_dir / RESEARCH_SCORECARD_JSON, report)
    write_text(run_dir / RESEARCH_SCORECARD_MD, render_research_scorecard_markdown(report))
    return report


def build_research_scorecard_report(topic: str, run_dir: Path) -> ResearchScorecardReport:
    data = {
        "search_strategy": _read_json(run_dir / "01-literature-search-strategy.json"),
        "rerank": _read_json(run_dir / "01-literature-rerank.json"),
        "query_execution": _read_json(run_dir / "01-query-execution-audit.json"),
        "quality": _read_json(run_dir / "01-literature-quality.json"),
        "metadata": _read_json(run_dir / "01-literature-metadata-audit.json"),
        "snowball": _read_json(run_dir / "01-literature-snowball.json"),
        "coverage": _read_json(run_dir / "01-literature-coverage.json"),
        "evidence_mix": _read_json(run_dir / "01-literature-evidence-mix.json"),
        "rescue": _read_json(run_dir / "01-literature-rescue-plan.json"),
        "rescue_execution": _read_json(run_dir / "01-literature-rescue-execution.json"),
        "seed_intake": _read_json(run_dir / "01-seed-paper-intake.json"),
        "literature_gate": _read_json(run_dir / "01-literature-gate-decision.json"),
        "seed_suggestion": build_seed_paper_suggestion_report(topic, run_dir),
        "context": _read_json(run_dir / "01-context.json"),
        "citation": _read_json(run_dir / "01-citation-audit.json"),
        "ideas": _read_json(run_dir / "02-ideas.json"),
        "novelty": _read_json(run_dir / "02-novelty-audit.json"),
        "idea_audit": _read_json(run_dir / "02-idea-audit.json"),
        "exploration": _read_json(run_dir / "02-exploration-map.json"),
        "runbook": _read_json(run_dir / "04-experiment-runbook.json"),
        "statistics": _read_json(run_dir / "04-statistics.json"),
        "result_validation": _read_json(run_dir / "04-result-validation.json"),
        "failure_analysis": _read_json(run_dir / "04-failure-analysis.json"),
        "benchmark_schema": _read_json(run_dir / "04-benchmark-result-schema-audit.json"),
        "benchmark_evidence": _read_json(run_dir / "04-benchmark-evidence-audit.json"),
        "experiment_decision": _read_json(run_dir / "04-experiment-decision.json"),
        "hypothesis_outcome": _read_json(run_dir / "04-hypothesis-outcome.json"),
        "claim_preflight": _read_json(run_dir / "04-claim-boundary-preflight.json"),
        "experiment_audit": _read_json(run_dir / "03-experiment-audit.json"),
        "idea_experiment_contract": _read_json(run_dir / "03-idea-experiment-contract.json"),
        "constraint_compliance": _read_json(run_dir / "03-review-constraint-compliance.json"),
        "execution_safety": _read_json(run_dir / "03-execution-safety-audit.json"),
        "ablation": _read_json(run_dir / "03-ablation-plan.json"),
        "preregistration": _read_json(run_dir / "03-preregistration.json"),
        "benchmark": _read_json(run_dir / "03-benchmark-plan.json"),
        "benchmark_readiness": _read_json(run_dir / "03-benchmark-readiness.json"),
        "adapter": _read_json(run_dir / "03-benchmark-adapters.json"),
        "review": _read_json(run_dir / "10-revised-paper-review.json") or _read_json(run_dir / "07-paper-review.json"),
        "review_calibration": _read_json(run_dir / "07-paper-review-calibration.json"),
        "claim_traceability": _read_json(run_dir / "10-claim-traceability.json"),
        "citation_grounding": _read_json(run_dir / "10-citation-grounding.json"),
        "citation_coverage": _read_json(run_dir / "10-citation-coverage.json"),
        "results_presentation": _read_json(run_dir / "10-results-presentation.json"),
        "claim_consistency": _read_json(run_dir / "10-claim-consistency.json"),
        "final": _read_json(run_dir / "10-final-readiness.json"),
        "revision_response": _read_json(run_dir / "09-revision-response-audit.json"),
        "availability": _read_json(run_dir / "10-code-data-availability.json"),
        "release": _read_json(run_dir / "10-release-metadata.json"),
        "environment": _read_json(run_dir / "04-environment-snapshot.json"),
        "ai_disclosure": _read_json(run_dir / "10-ai-disclosure.json"),
        "submission": _read_json(run_dir / "10-submission-check.json"),
        "package": _read_json(run_dir / "11-submission-package.json"),
        "iteration": _read_json(run_dir / "12-next-iteration-plan.json"),
        "repair_queue": _read_json(run_dir / "12-repair-queue.json"),
        "repair_resolution": _read_json(run_dir / "12-repair-resolution-audit.json"),
        "stage_contract": _read_json(run_dir / "13-agent-stage-contract.json"),
        "llm_trace_audit": _read_json(run_dir / "13-llm-trace-audit.json"),
        "run_economics": _read_json(run_dir / "13-run-economics-audit.json"),
        "observability": _read_json(run_dir / "13-agent-observability-audit.json"),
        "open_source_compliance": _read_json(run_dir / "13-open-source-compliance.json"),
        "run_integrity": _read_json(run_dir / "14-run-integrity-audit.json"),
    }
    dimensions = [
        _evidence_dimension(data),
        _exploration_dimension(data),
        _experiment_dimension(data),
        _paper_dimension(data),
        _reproducibility_dimension(data),
        _submission_dimension(data),
    ]
    overall = _weighted_score(dimensions)
    blocking = [f"{item.category}: {action}" for item in dimensions for action in item.actions if item.status == "block"]
    manual = [f"{item.category}: {action}" for item in dimensions for action in item.actions if item.status in {"manual_required", "warn"}]
    status = _status(overall, dimensions)
    return ResearchScorecardReport(
        topic=topic,
        status=status,
        overall_score=overall,
        dimensions=dimensions,
        blocking_issues=blocking,
        manual_tasks=manual,
        recommendation=_recommendation(status, overall, dimensions),
        next_actions=_next_actions(status, dimensions),
    )


def render_research_scorecard_markdown(report: ResearchScorecardReport) -> str:
    lines = [
        f"# 研究 Run 分数卡：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 总分：{report.overall_score:.1f}/100",
        f"- 阻断问题：{len(report.blocking_issues)}",
        f"- 人工待办：{len(report.manual_tasks)}",
        "",
        "## 维度评分",
        "| 维度 | 权重 | 分数 | 状态 | 证据 | 动作 |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for item in report.dimensions:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.category),
                    f"{item.weight:.2f}",
                    f"{item.score:.1f}",
                    item.status,
                    _cell("；".join(item.evidence) or "-"),
                    _cell("；".join(item.actions) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 建议", report.recommendation, "", "## 阻断问题"])
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(["", "## 下一步动作"])
    lines.extend(f"- [ ] {item}" for item in report.next_actions) if report.next_actions else lines.append("- 暂无")
    return "\n".join(lines)


def _evidence_dimension(data: dict[str, Any]) -> ScorecardDimension:
    quality = _dict(data["quality"])
    metadata = _dict(data["metadata"])
    search_strategy = _dict(data["search_strategy"])
    rerank = _dict(data["rerank"])
    query_execution = _dict(data["query_execution"])
    snowball = _dict(data["snowball"])
    coverage = _dict(data["coverage"])
    evidence_mix = _dict(data["evidence_mix"])
    rescue = _dict(data["rescue"])
    rescue_execution = _dict(data["rescue_execution"])
    seed_intake = _dict(data["seed_intake"])
    literature_gate = _dict(data["literature_gate"])
    paper_grade_literature = _dict(literature_gate.get("paper_grade_literature"))
    seed_suggestion = _dict(data["seed_suggestion"])
    context = _dict(data["context"])
    citation = _dict(data["citation"])
    selected = _safe_int(quality.get("selected_papers"))
    citations = len(context.get("citations", [])) if isinstance(context.get("citations"), list) else 0
    total_citations = _safe_int(citation.get("total_citations")) or citations
    usable = _safe_int(citation.get("usable_citations"))
    blocked = _safe_int(citation.get("blocked_citations"))
    doi_coverage = _safe_float(citation.get("doi_coverage"))
    integrity_score = _safe_float(citation.get("integrity_score"))
    integrity_status = str(citation.get("integrity_status") or "")
    score = min(selected or citations, 10) * 4.0
    if total_citations:
        score += min(1.0, usable / max(1, total_citations)) * 30.0
    score += doi_coverage * 20.0
    score += integrity_score * 10.0
    if blocked == 0 and total_citations:
        score += 10.0
    warnings = len(quality.get("warnings", [])) if isinstance(quality.get("warnings"), list) else 0
    snowball_status = str(snowball.get("status") or "")
    snowball_actions = snowball.get("required_actions", []) if isinstance(snowball.get("required_actions"), list) else []
    coverage_status = str(coverage.get("status") or "")
    coverage_ratio = _safe_float(coverage.get("coverage_ratio"))
    coverage_actions = coverage.get("required_actions", []) if isinstance(coverage.get("required_actions"), list) else []
    mix_status = str(evidence_mix.get("status") or "")
    mix_score = _safe_float(evidence_mix.get("mix_score"))
    mix_actions = evidence_mix.get("required_actions", []) if isinstance(evidence_mix.get("required_actions"), list) else []
    mix_blockers = evidence_mix.get("blocking_issues", []) if isinstance(evidence_mix.get("blocking_issues"), list) else []
    rescue_status = str(rescue.get("status") or "")
    rescue_actions = rescue.get("required_actions", []) if isinstance(rescue.get("required_actions"), list) else []
    rescue_queries = rescue.get("rescue_queries", []) if isinstance(rescue.get("rescue_queries"), list) else []
    rescue_execution_status = str(rescue_execution.get("status") or "")
    rescue_execution_trigger = str(rescue_execution.get("trigger_status") or "")
    rescue_execution_closed = _safe_int(rescue_execution.get("closed_query_outcomes"))
    rescue_execution_unresolved = _safe_int(rescue_execution.get("unresolved_query_outcomes"))
    rescue_execution_new = _safe_int(rescue_execution.get("new_unique_papers"))
    rescue_execution_actions = rescue_execution.get("required_actions", []) if isinstance(rescue_execution.get("required_actions"), list) else []
    rescue_execution_repair_tasks = rescue_execution.get("repair_task_ids", []) if isinstance(rescue_execution.get("repair_task_ids"), list) else []
    seed_status = str(seed_intake.get("status") or "")
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    seed_actions = seed_intake.get("required_actions", []) if isinstance(seed_intake.get("required_actions"), list) else []
    seed_missing_roles = seed_intake.get("missing_curated_seed_roles", []) if isinstance(seed_intake.get("missing_curated_seed_roles"), list) else []
    seed_suggestion_count = _safe_int(seed_suggestion.get("suggested_seed_count"))
    seed_suggestion_missing_roles = seed_suggestion.get("missing_roles", []) if isinstance(seed_suggestion.get("missing_roles"), list) else []
    seed_suggestion_role_queries = seed_suggestion.get("role_repair_queries", []) if isinstance(seed_suggestion.get("role_repair_queries"), list) else []
    paper_grade_status = str(paper_grade_literature.get("status") or "")
    paper_grade_issues = paper_grade_literature.get("issues", []) if isinstance(paper_grade_literature.get("issues"), list) else []
    if not seed_status and seed_suggestion_count:
        seed_status = "not_configured"
        seed_role_status = "review_required"
        seed_missing_roles = seed_suggestion_missing_roles
        seed_actions = [
            *[str(item) for item in seed_suggestion_role_queries[:3]],
            "人工核对候选 DOI/URL seed，写入 seed_papers 后重新生成 01-seed-paper-intake.json。",
        ]
    metadata_status = str(metadata.get("status") or "")
    metadata_score = _safe_float(metadata.get("verifiability_score"))
    metadata_blocked = _safe_int(metadata.get("blocked"))
    metadata_review = _safe_int(metadata.get("review_required"))
    metadata_actions = metadata.get("required_actions", []) if isinstance(metadata.get("required_actions"), list) else []
    strategy_status = str(search_strategy.get("status") or "")
    strategy_score = _safe_float(search_strategy.get("quality_score"))
    strategy_missing = search_strategy.get("missing_required_intents", []) if isinstance(search_strategy.get("missing_required_intents"), list) else []
    strategy_weak = search_strategy.get("weak_selected_queries", []) if isinstance(search_strategy.get("weak_selected_queries"), list) else []
    strategy_actions = search_strategy.get("recommendations", []) if isinstance(search_strategy.get("recommendations"), list) else []
    rerank_status = str(rerank.get("status") or "")
    rerank_warnings = rerank.get("warnings", []) if isinstance(rerank.get("warnings"), list) else []
    rerank_actions = rerank.get("recommended_actions", []) if isinstance(rerank.get("recommended_actions"), list) else []
    query_execution_status = str(query_execution.get("status") or "")
    query_execution_actions = query_execution.get("recommended_actions", []) if isinstance(query_execution.get("recommended_actions"), list) else []
    query_execution_source = query_execution.get("source_coverage", {}) if isinstance(query_execution.get("source_coverage"), dict) else {}
    query_execution_top = query_execution.get("top_rerank_coverage", {}) if isinstance(query_execution.get("top_rerank_coverage"), dict) else {}
    if strategy_status == "pass":
        score += 3.0
    elif strategy_status == "review_required":
        score -= 3.0
    elif strategy_status == "needs_query_repair":
        score -= 8.0
    if rerank_status == "pass":
        score += 3.0
    elif rerank_status == "review_required":
        score -= 3.0
    if query_execution_status == "pass":
        score += 4.0
    elif query_execution_status == "review_required":
        score -= 3.0
    elif query_execution_status == "needs_query_repair":
        score -= 8.0
    elif query_execution_status == "needs_source_repair":
        score -= 12.0
    if snowball_status == "ready_for_review":
        score += 5.0
    elif snowball_status in {"needs_seed_papers", "needs_source_repair"}:
        score -= 8.0
    elif snowball_status == "needs_snowball":
        score -= 3.0
    if coverage_status == "pass":
        score += 5.0
    elif coverage_status == "needs_coverage":
        score -= 5.0
    elif coverage_status in {"needs_literature", "block"}:
        score -= 12.0
    if mix_status == "pass":
        score += 6.0
    elif mix_status == "review_required":
        score -= 3.0
    elif mix_status == "needs_evidence_upgrade":
        score -= 9.0
    elif mix_status == "block":
        score -= 15.0
    if rescue_status == "pass":
        score += 5.0
    elif rescue_status in {"needs_rescue_search", "needs_manual_seed"}:
        score -= 5.0
    elif rescue_status == "needs_source_repair":
        score -= 8.0
    elif rescue_status == "block":
        score -= 12.0
    if rescue_execution_status == "executed" and not rescue_execution_unresolved:
        score += 4.0 if rescue_execution_new else 1.0
    elif rescue_execution_status == "no_new_papers":
        score -= 12.0
    elif rescue_execution_status in {"not_applicable", "skipped"} and (
        rescue_execution_trigger in {"block", "needs_rescue_search", "needs_manual_seed"} or rescue_execution_repair_tasks or rescue_execution_actions
    ):
        score -= 8.0
    if rescue_execution_unresolved:
        score -= min(15.0, rescue_execution_unresolved * 5.0)
    if seed_status == "block":
        score -= 12.0
    elif seed_status in {"review_required", "not_configured"} or seed_role_status == "review_required":
        score -= 5.0
    if paper_grade_status == "review_required":
        score -= 5.0
    if metadata_status == "pass":
        score += 5.0
    elif metadata_status == "review_required":
        score -= 4.0
    elif metadata_status == "literature_repair_required":
        score -= 8.0
    elif metadata_status == "block":
        score -= 14.0
    if integrity_status == "block":
        score -= 15.0
    elif integrity_status == "review_required":
        score -= 5.0
    score -= min(10.0, warnings * 2.0 + blocked * 8.0)
    evidence = [
        f"selected_papers={selected}",
        f"citations={citations}",
        f"doi_coverage={doi_coverage:.2f}",
        f"blocked_citations={blocked}",
        f"citation_integrity={integrity_status or '-'}:{integrity_score:.2f}",
        f"search_strategy={strategy_status or '-'}:{strategy_score:.2f}:{len(strategy_missing)}/{len(strategy_weak)}",
        f"rerank={rerank_status or '-'}:{len(rerank_warnings)}",
        f"query_execution={query_execution_status or '-'}:{query_execution.get('selected_query_count', 0)}:{query_execution_top.get('covered_top_count', 0)}/{query_execution_top.get('top_count', 0)}",
        f"query_sources={query_execution_source.get('sources_with_success', 0)}/{query_execution_source.get('configured_source_count', 0)}",
        f"metadata={metadata_status or '-'}:{metadata_score:.2f}:{metadata_blocked}/{metadata_review}",
        f"snowball={snowball_status or '-'}",
        f"coverage={coverage_status or '-'}:{coverage_ratio:.2f}",
        f"evidence_mix={mix_status or '-'}:{mix_score:.2f}",
        f"rescue={rescue_status or '-'}:{len(rescue_queries)}",
        f"rescue_execution={rescue_execution_status or '-'}:{rescue_execution_closed}/{rescue_execution_unresolved}:{rescue_execution_new}",
        f"seed_intake={seed_status or '-'}:{seed_role_status or '-'}:{seed_intake.get('curated_seed_papers', 0)}/{seed_intake.get('total_seed_entries', 0)}",
        f"paper_grade_literature={paper_grade_status or '-'}:{len(paper_grade_issues)}",
        f"seed_suggestions={seed_suggestion_count}:{len(seed_suggestion_missing_roles)}",
    ]
    actions: list[str] = []
    status = "pass"
    if selected < 3 and citations < 3:
        status = "manual_required"
        actions.append("补充高相关种子文献或提高在线检索质量。")
    if strategy_status == "needs_query_repair":
        status = "manual_required" if status != "block" else status
        actions.extend(str(item) for item in strategy_actions[:3])
    elif strategy_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in strategy_actions[:2])
    if rerank_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in rerank_actions[:2])
    if query_execution_status == "needs_source_repair":
        status = "manual_required" if status != "block" else status
        actions.extend(str(item) for item in query_execution_actions[:3])
    elif query_execution_status == "needs_query_repair" and status != "block":
        status = "manual_required"
        actions.extend(str(item) for item in query_execution_actions[:3])
    elif query_execution_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in query_execution_actions[:2])
    if snowball_status in {"needs_seed_papers", "needs_source_repair"}:
        status = "manual_required"
        actions.extend(str(item) for item in snowball_actions[:3])
    elif snowball_status == "needs_snowball" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in snowball_actions[:2])
    if coverage_status in {"needs_literature", "block"}:
        status = "manual_required" if status != "block" else status
        actions.extend(str(item) for item in coverage_actions[:3])
    elif coverage_status == "needs_coverage" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in coverage_actions[:3])
    if mix_status == "block" or mix_blockers:
        status = "block"
        actions.extend(str(item) for item in (mix_blockers or mix_actions)[:3])
    elif mix_status == "needs_evidence_upgrade" and status != "block":
        status = "manual_required"
        actions.extend(str(item) for item in mix_actions[:3])
    elif mix_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in mix_actions[:2])
    if rescue_status == "block":
        status = "block"
        actions.extend(str(item) for item in rescue_actions[:3])
    elif rescue_status == "needs_source_repair":
        status = "manual_required" if status != "block" else status
        actions.extend(str(item) for item in rescue_actions[:3])
    elif rescue_status in {"needs_rescue_search", "needs_manual_seed"} and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in rescue_actions[:3])
    if rescue_execution_status == "no_new_papers" or rescue_execution_unresolved:
        status = "block"
        actions.extend(
            str(item)
            for item in (
                rescue_execution_actions[:3]
                or ["修复 01-literature-rescue-execution.md 中未闭环 query，替换为更具体的 facet-aware 检索式或补 DOI/URL seed 后重跑。"]
            )
        )
    elif rescue_execution_status in {"not_applicable", "skipped"} and (
        rescue_execution_trigger in {"block", "needs_rescue_search", "needs_manual_seed"} or rescue_execution_repair_tasks or rescue_execution_actions
    ):
        status = "manual_required" if status != "block" else status
        actions.extend(
            str(item)
            for item in (
                rescue_execution_actions[:3]
                or ["确认 literature.provider、source/API key 和 seed papers 后重跑 01-literature-rescue-execution。"]
            )
        )
    if seed_status == "block":
        status = "block"
        actions.extend(str(item) for item in seed_actions[:3])
    elif seed_status in {"review_required", "not_configured"} and status != "block":
        status = "manual_required"
        actions.extend(str(item) for item in seed_actions[:3])
    elif seed_role_status == "review_required" and status != "block":
        status = "manual_required"
        actions.extend(
            str(item)
            for item in (
                seed_actions[:3]
                or [f"补齐 seed paper 角色覆盖，当前缺失：{', '.join(str(item) for item in seed_missing_roles[:4]) or '-'}。"]
            )
        )
    if paper_grade_status == "review_required" and status != "block":
        status = "manual_required"
        actions.extend(str(item) for item in paper_grade_issues[:3])
    if metadata_status == "block" or metadata_blocked:
        status = "block"
        actions.extend(str(item) for item in metadata_actions[:3])
    elif metadata_status == "literature_repair_required" and status != "block":
        status = "manual_required"
        actions.extend(str(item) for item in metadata_actions[:3])
    elif metadata_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in metadata_actions[:3])
    if blocked:
        status = "block"
        actions.append("修复 citation audit 中不可核对或不可引用的条目。")
    if integrity_status == "block":
        status = "block"
        actions.append("修复 01-citation-audit.md 中 citation integrity 阻断项。")
    elif integrity_status == "review_required" and status == "pass":
        status = "warn"
        actions.append("人工复核 01-citation-audit.md 中 citation integrity review_required 条目。")
    if (
        paper_grade_status == "pass"
        and status == "block"
        and selected >= 3
        and citations >= 3
        and not blocked
        and coverage_status not in {"needs_literature", "block"}
    ):
        status = "warn"
        actions = [
            "paper-grade literature gate 已通过；底层 query/source/rescue 残余作为人工复核项，不再阻断当前 gold run。",
            *actions,
        ]
    return _dimension("literature_evidence", score, 0.18, status, evidence, actions)


def _exploration_dimension(data: dict[str, Any]) -> ScorecardDimension:
    ideas = data["ideas"] if isinstance(data["ideas"], list) else []
    novelty = _dict(data["novelty"])
    idea_audit = _dict(data["idea_audit"])
    exploration = _dict(data["exploration"])
    branches = exploration.get("branches", []) if isinstance(exploration.get("branches"), list) else []
    selected = next((item for item in branches if isinstance(item, dict) and item.get("status") == "selected"), {})
    selected_score = _safe_float(selected.get("score")) if isinstance(selected, dict) else 0.0
    evidence_count = _safe_int(selected.get("evidence_count")) if isinstance(selected, dict) else 0
    warnings = exploration.get("warnings", []) if isinstance(exploration.get("warnings"), list) else []
    novelty_item = _novelty_item(novelty, str(exploration.get("selected_idea_title") or ""))
    novelty_decision = str(novelty_item.get("decision") or "")
    duplicate_risk = _safe_float(novelty_item.get("duplicate_risk")) if novelty_item else 0.0
    audit_status = str(idea_audit.get("status") or "")
    audit_blocked = _safe_int(idea_audit.get("blocked"))
    audit_review = _safe_int(idea_audit.get("review_required"))
    score = 0.0
    if ideas:
        score += min(len(ideas), 5) * 8.0
    if branches:
        score += 25.0
    if selected:
        score += min(max(selected_score, 0.0), 10.0) * 4.0
    score += min(evidence_count, 5) * 4.0
    score -= min(15.0, len(warnings) * 5.0)
    if novelty_decision == "likely_duplicate":
        score -= 20.0
    elif novelty_decision == "review_required":
        score -= 8.0
    if audit_status == "pass":
        score += 5.0
    elif audit_status == "review":
        score -= min(12.0, audit_review * 4.0 + audit_blocked * 6.0)
    elif audit_status == "block":
        score -= 20.0
    status = "pass"
    actions: list[str] = []
    if not branches:
        status = "manual_required"
        actions.append("重新运行 idea 阶段，生成 02-exploration-map。")
    elif novelty_decision == "likely_duplicate":
        status = "block"
        actions.append("选中 idea 与已纳入文献高度相似，重写 hypothesis 或人工选择更有差异的分支。")
    elif novelty_decision == "review_required":
        status = "manual_required"
        actions.append("人工核对 02-novelty-audit.md 中最相似文献，明确 novelty 边界后再继续。")
    elif audit_status == "block" or audit_blocked:
        status = "block"
        actions.append("修复 02-idea-audit.md 中不可核对的 idea citation/chunk。")
    elif audit_status == "review" or audit_review:
        status = "manual_required"
        actions.append("补齐 02-idea-audit.md 标出的证据、baseline、metric、实验草案或人工约束响应。")
    elif warnings:
        status = "warn"
        actions.extend(str(item) for item in warnings[:3])
    evidence = [
        f"ideas={len(ideas)}",
        f"branches={len(branches)}",
        f"selected={exploration.get('selected_branch_id') or '-'}",
        f"selected_evidence={evidence_count}",
        f"novelty={novelty_decision or '-'}:{duplicate_risk:.2f}",
        f"idea_audit={audit_status or '-'}:{audit_blocked}/{audit_review}",
    ]
    return _dimension("idea_exploration", score, 0.12, status, evidence, actions)


def _experiment_dimension(data: dict[str, Any]) -> ScorecardDimension:
    runbook = _dict(data["runbook"])
    statistics = _dict(data["statistics"])
    result_validation = _dict(data["result_validation"])
    failure_analysis = _dict(data["failure_analysis"])
    benchmark_schema = _dict(data["benchmark_schema"])
    benchmark_evidence = _dict(data["benchmark_evidence"])
    experiment_decision = _dict(data["experiment_decision"])
    hypothesis_outcome = _dict(data["hypothesis_outcome"])
    claim_preflight = _dict(data["claim_preflight"])
    claim_consistency = _dict(data["claim_consistency"])
    final = _dict(data["final"])
    experiment_audit = _dict(data["experiment_audit"])
    constraint_compliance = _dict(data["constraint_compliance"])
    execution_safety = _dict(data["execution_safety"])
    ablation = _dict(data["ablation"])
    preregistration = _dict(data["preregistration"])
    benchmark = _dict(data["benchmark"])
    benchmark_readiness = _dict(data["benchmark_readiness"])
    adapter = _dict(data["adapter"])
    execution = runbook.get("execution", {}) if isinstance(runbook.get("execution"), dict) else {}
    mode = str(execution.get("mode") or "")
    runs = runbook.get("runs", []) if isinstance(runbook.get("runs"), list) else []
    artifacts = runbook.get("artifacts", []) if isinstance(runbook.get("artifacts"), list) else []
    repeats = _safe_int(statistics.get("repeats")) or _safe_int(execution.get("repeats"))
    comparisons = statistics.get("comparisons", []) if isinstance(statistics.get("comparisons"), list) else []
    benchmark_actions = benchmark.get("required_actions", []) if isinstance(benchmark.get("required_actions"), list) else []
    readiness_status = str(benchmark_readiness.get("status") or "")
    readiness_blockers = benchmark_readiness.get("blocking_issues", []) if isinstance(benchmark_readiness.get("blocking_issues"), list) else []
    readiness_manual = benchmark_readiness.get("manual_tasks", []) if isinstance(benchmark_readiness.get("manual_tasks"), list) else []
    adapter_blockers = adapter.get("blocking_issues", []) if isinstance(adapter.get("blocking_issues"), list) else []
    benchmark_evidence_status = str(benchmark_evidence.get("status") or "")
    benchmark_evidence_grade = str(benchmark_evidence.get("evidence_grade") or "")
    claim_boundary_severity = str(benchmark_evidence.get("claim_boundary_severity") or "")
    publishable_negative_or_neutral = benchmark_evidence.get("publishable_negative_or_neutral_result") is True
    bounded_negative_or_neutral = _bounded_negative_or_neutral_ready(benchmark_evidence, claim_preflight, claim_consistency, final)
    validation_status = str(result_validation.get("status") or "")
    validation_blockers = result_validation.get("blocking_issues", []) if isinstance(result_validation.get("blocking_issues"), list) else []
    validation_warnings = result_validation.get("warnings", []) if isinstance(result_validation.get("warnings"), list) else []
    effective_validation_warnings = [] if bounded_negative_or_neutral else validation_warnings
    failure_status = str(failure_analysis.get("status") or "")
    benchmark_schema_status = str(benchmark_schema.get("status") or "")
    benchmark_schema_blockers = benchmark_schema.get("blocking_issues", []) if isinstance(benchmark_schema.get("blocking_issues"), list) else []
    benchmark_schema_manual = benchmark_schema.get("manual_tasks", []) if isinstance(benchmark_schema.get("manual_tasks"), list) else []
    benchmark_schema_warnings = benchmark_schema.get("warnings", []) if isinstance(benchmark_schema.get("warnings"), list) else []
    adapter_paper_grade_status = str(benchmark_evidence.get("adapter_paper_grade_status") or "")
    adapter_paper_grade_issues = benchmark_evidence.get("adapter_paper_grade_issues", []) if isinstance(benchmark_evidence.get("adapter_paper_grade_issues"), list) else []
    benchmark_evidence_blockers = benchmark_evidence.get("blocking_issues", []) if isinstance(benchmark_evidence.get("blocking_issues"), list) else []
    benchmark_evidence_manual = benchmark_evidence.get("manual_tasks", []) if isinstance(benchmark_evidence.get("manual_tasks"), list) else []
    benchmark_evidence_actions = benchmark_evidence.get("required_actions", []) if isinstance(benchmark_evidence.get("required_actions"), list) else []
    decision = str(experiment_decision.get("decision") or "")
    decision_status = str(experiment_decision.get("status") or "")
    hypothesis_status = str(hypothesis_outcome.get("status") or "")
    hypothesis_decision = str(hypothesis_outcome.get("outcome") or "")
    hypothesis_score = _safe_float(hypothesis_outcome.get("support_score"))
    failure_actions = failure_analysis.get("required_actions", []) if isinstance(failure_analysis.get("required_actions"), list) else []
    effective_failure_actions = [] if bounded_negative_or_neutral else failure_actions
    failure_summary = failure_analysis.get("summary", {}) if isinstance(failure_analysis.get("summary"), dict) else {}
    failed_runs = _safe_int(failure_summary.get("failed_runs"))
    negative_metrics = _safe_int(failure_summary.get("negative_metrics"))
    uncertain_metrics = _safe_int(failure_summary.get("uncertain_metrics"))
    audit_status = str(experiment_audit.get("status") or "")
    audit_blockers = experiment_audit.get("blocking_issues", []) if isinstance(experiment_audit.get("blocking_issues"), list) else []
    audit_warnings = experiment_audit.get("warnings", []) if isinstance(experiment_audit.get("warnings"), list) else []
    idea_contract = _dict(data["idea_experiment_contract"])
    idea_contract_status = str(idea_contract.get("status") or "")
    idea_contract_score = _safe_float(idea_contract.get("contract_score"))
    idea_contract_blockers = idea_contract.get("blocking_issues", []) if isinstance(idea_contract.get("blocking_issues"), list) else []
    idea_contract_manual = idea_contract.get("manual_tasks", []) if isinstance(idea_contract.get("manual_tasks"), list) else []
    compliance_status = str(constraint_compliance.get("status") or "")
    compliance_blockers = constraint_compliance.get("blocking_issues", []) if isinstance(constraint_compliance.get("blocking_issues"), list) else []
    compliance_manual = constraint_compliance.get("manual_tasks", []) if isinstance(constraint_compliance.get("manual_tasks"), list) else []
    compliance_blocked = _safe_int(constraint_compliance.get("blocked"))
    compliance_review = _safe_int(constraint_compliance.get("review_required"))
    safety_status = str(execution_safety.get("status") or "")
    safety_blockers = execution_safety.get("blocking_issues", []) if isinstance(execution_safety.get("blocking_issues"), list) else []
    safety_warnings = execution_safety.get("warnings", []) if isinstance(execution_safety.get("warnings"), list) else []
    ablation_status = str(ablation.get("status") or "")
    ablation_blockers = ablation.get("blocking_issues", []) if isinstance(ablation.get("blocking_issues"), list) else []
    ablation_warnings = ablation.get("warnings", []) if isinstance(ablation.get("warnings"), list) else []
    ablation_actions = ablation.get("required_actions", []) if isinstance(ablation.get("required_actions"), list) else []
    preregistration_status = str(preregistration.get("status") or "")
    preregistration_blockers = preregistration.get("blocking_issues", []) if isinstance(preregistration.get("blocking_issues"), list) else []
    preregistration_warnings = preregistration.get("warnings", []) if isinstance(preregistration.get("warnings"), list) else []
    score = 0.0
    if runbook:
        score += 15.0
    if runs:
        score += 15.0
    if artifacts:
        score += 10.0
    score += min(repeats, 5) * 5.0
    score += min(len(comparisons), 8) * 3.0
    if mode == "benchmark":
        score += 20.0
    elif mode == "local":
        score += 12.0
    elif mode == "simulated":
        score += 4.0
    if benchmark.get("selected_names"):
        score += 8.0
    if readiness_status == "ready_for_benchmark":
        score += 8.0
    elif readiness_status == "needs_benchmark_upgrade":
        score -= 4.0
    elif readiness_status == "block":
        score -= 15.0
    if audit_status == "pass":
        score += 5.0
    elif audit_status == "warn":
        score -= 3.0
    elif audit_status == "block":
        score -= 15.0
    if idea_contract_status == "pass":
        score += 5.0
    elif idea_contract_status == "review_required":
        score -= 5.0
    elif idea_contract_status == "block":
        score -= 18.0
    if compliance_status == "pass":
        score += 5.0
    elif compliance_status == "review_required":
        score -= 5.0
    elif compliance_status == "block":
        score -= 15.0
    if safety_status == "pass":
        score += 5.0
    elif safety_status == "warn":
        score -= 3.0
    elif safety_status == "block":
        score -= 15.0
    if ablation.get("has_ablation"):
        score += 5.0
    elif ablation:
        score -= 8.0
    if preregistration_status == "locked":
        score += 5.0
    elif preregistration_status == "posthoc":
        score -= 5.0
    if failure_status == "pass":
        score += 5.0
    elif failure_status == "warn":
        if bounded_negative_or_neutral:
            score += 2.0
        else:
            score -= 5.0
    elif failure_status == "block":
        score -= 15.0
    if benchmark_schema_status == "pass":
        score += 5.0
    elif benchmark_schema_status == "review_required":
        score -= 4.0
    elif benchmark_schema_status == "block":
        score -= 15.0
    if benchmark_evidence_grade == "real_benchmark" and benchmark_evidence_status in {"pass", "warn"}:
        score += 10.0
    elif benchmark_evidence_grade == "local_experiment":
        score -= 4.0
    elif benchmark_evidence_grade == "smoke_only" or benchmark_evidence_status == "smoke_only":
        score -= 12.0
    elif benchmark_evidence_grade == "blocked" or benchmark_evidence_status == "block":
        score -= 18.0
    if decision_status == "pass":
        score += 5.0
    elif decision == "repair_before_writing" or decision_status == "block":
        score -= 18.0
    elif decision in {"pivot_or_refine", "refine_experiment", "benchmark_upgrade"} or decision_status == "warn":
        if not bounded_negative_or_neutral:
            score -= 6.0
    if hypothesis_status == "pass":
        score += 5.0
    elif hypothesis_status == "review_required":
        if bounded_negative_or_neutral:
            score += 2.0
        else:
            score -= 5.0
    elif hypothesis_status == "block":
        score -= 15.0
    score -= min(
        30.0,
        len(benchmark_actions) * 3.0
        + len(readiness_blockers) * 8.0
        + len(readiness_manual) * 2.0
        + len(adapter_blockers) * 8.0
        + len(effective_failure_actions) * 2.0
        + len(benchmark_schema_blockers) * 8.0
        + len(benchmark_schema_manual) * 3.0
        + len(benchmark_schema_warnings) * 2.0
        + len(benchmark_evidence_blockers) * 8.0
        + len(benchmark_evidence_manual) * 3.0
        + len(audit_blockers) * 10.0
        + len(audit_warnings) * 3.0
        + len(idea_contract_blockers) * 10.0
        + len(idea_contract_manual) * 3.0
        + len(compliance_blockers) * 8.0
        + len(compliance_manual) * 3.0
        + len(safety_blockers) * 10.0
        + len(safety_warnings) * 3.0
        + len(validation_blockers) * 10.0
        + len(effective_validation_warnings) * 3.0
        + len(ablation_blockers) * 8.0
        + len(ablation_warnings) * 3.0
        + len(preregistration_blockers) * 8.0
        + len(preregistration_warnings) * 2.0,
    )
    status = "pass"
    actions: list[str] = []
    if audit_status == "block" or audit_blockers:
        status = "block"
        actions.extend(str(item) for item in audit_blockers[:4])
    elif idea_contract_status == "block" or idea_contract_blockers:
        status = "block"
        actions.extend(str(item) for item in idea_contract_blockers[:4])
    elif compliance_status == "block" or compliance_blockers or compliance_blocked:
        status = "block"
        actions.extend(str(item) for item in (compliance_blockers or compliance_manual)[:4])
    elif safety_status == "block" or safety_blockers:
        status = "block"
        actions.extend(str(item) for item in safety_blockers[:4])
    elif validation_status == "block" or validation_blockers:
        status = "block"
        actions.extend(str(item) for item in validation_blockers[:4])
    elif failure_status == "block":
        status = "block"
        actions.extend(str(item) for item in failure_actions[:4])
    elif benchmark_schema_status == "block" or benchmark_schema_blockers:
        status = "block"
        actions.extend(str(item) for item in benchmark_schema_blockers[:4])
    elif benchmark_evidence_status == "block" or benchmark_evidence_grade == "blocked" or benchmark_evidence_blockers:
        status = "block"
        actions.extend(str(item) for item in (benchmark_evidence_blockers or benchmark_evidence_actions)[:4])
    elif readiness_status == "block" or readiness_blockers:
        status = "block"
        actions.extend(str(item) for item in readiness_blockers[:4])
    elif decision == "repair_before_writing" or decision_status == "block":
        status = "block"
        actions.append("先处理 04-experiment-decision.md 中的 repair_before_writing 决策。")
    elif hypothesis_status == "block":
        status = "block"
        actions.append("先处理 04-hypothesis-outcome.md 中未检验或被阻断的 hypothesis outcome。")
    elif adapter_blockers:
        status = "block"
        actions.extend(str(item) for item in adapter_blockers[:4])
    elif ablation_status == "block" or ablation_blockers:
        status = "block"
        actions.extend(str(item) for item in ablation_blockers[:4])
    elif preregistration_status == "block" or preregistration_blockers:
        status = "block"
        actions.extend(str(item) for item in preregistration_blockers[:4])
    elif mode == "simulated":
        status = "manual_required"
        actions.append("把模拟实验替换为 local 或 benchmark manifest 真实任务。")
        if ablation_status == "needs_ablation":
            actions.extend(str(item) for item in ablation_actions[:2])
        if compliance_manual:
            actions.extend(str(item) for item in compliance_manual[:3])
        actions.extend(str(item) for item in benchmark_evidence_actions[:3])
    elif benchmark_evidence_status in {"smoke_only", "review_required"} or benchmark_evidence_grade in {"smoke_only", "local_experiment"}:
        status = "manual_required"
        actions.extend(str(item) for item in benchmark_evidence_actions[:4])
    elif readiness_status == "needs_benchmark_upgrade" or readiness_manual:
        status = "manual_required"
        actions.extend(str(item) for item in readiness_manual[:4])
    elif idea_contract_status == "review_required" or idea_contract_manual:
        status = "manual_required"
        actions.extend(str(item) for item in idea_contract_manual[:4])
    elif compliance_status == "review_required" or compliance_manual or compliance_review:
        status = "manual_required"
        actions.extend(str(item) for item in compliance_manual[:4])
    elif audit_status == "warn" or audit_warnings:
        status = "warn"
        actions.extend(str(item) for item in audit_warnings[:3])
    elif safety_status == "warn" or safety_warnings:
        status = "warn"
        actions.extend(str(item) for item in safety_warnings[:3])
    elif (validation_status == "warn" or effective_validation_warnings) and not bounded_negative_or_neutral:
        status = "warn"
        actions.extend(str(item) for item in effective_validation_warnings[:3])
    elif failure_status == "warn" and not bounded_negative_or_neutral:
        status = "warn"
        actions.extend(str(item) for item in effective_failure_actions[:3])
    elif benchmark_schema_status == "review_required" or benchmark_schema_manual:
        status = "warn"
        actions.extend(str(item) for item in (benchmark_schema_manual or benchmark_schema_warnings)[:4])
    elif (decision in {"pivot_or_refine", "refine_experiment", "benchmark_upgrade"} or decision_status == "warn") and not bounded_negative_or_neutral:
        status = "warn"
        actions.append("按 04-experiment-decision.md 的 pivot/refine/benchmark_upgrade 决策规划下一轮实验。")
    elif hypothesis_status == "review_required" and not bounded_negative_or_neutral:
        status = "warn"
        actions.append("按 04-hypothesis-outcome.md 区分 supported、partial、negative、inconclusive 或 smoke-only 证据。")
    elif ablation_status == "needs_ablation":
        status = "warn"
        actions.extend(str(item) for item in ablation_actions[:3])
    elif preregistration_status == "posthoc":
        status = "warn"
        actions.append("该 run 的预注册是在已有结果后补写；重新从 checkpoint 跑一次以获得 before_results 锁定。")
    elif benchmark_actions:
        status = "warn"
        actions.extend(str(item) for item in benchmark_actions[:3])
    evidence = [
        f"mode={mode or '-'}",
        f"repeats={repeats}",
        f"runs={len(runs)}",
        f"comparisons={len(comparisons)}",
        f"experiment_audit={audit_status or '-'}",
        f"idea_experiment_contract={idea_contract_status or '-'}:{idea_contract_score:.2f}",
        f"review_constraint_compliance={compliance_status or '-'}:{compliance_blocked}/{compliance_review}",
        f"execution_safety={safety_status or '-'}",
        f"validation={validation_status or '-'}",
        f"failure_analysis={failure_status or '-'}",
        f"benchmark_schema={benchmark_schema_status or '-'}",
        f"benchmark_evidence={benchmark_evidence_status or '-'}:{benchmark_evidence_grade or '-'}",
        f"claim_boundary_severity={claim_boundary_severity or '-'}",
        f"publishable_negative_or_neutral={publishable_negative_or_neutral}",
        f"bounded_negative_or_neutral={bounded_negative_or_neutral}",
        f"adapter_paper_grade={adapter_paper_grade_status or '-'}:{len(adapter_paper_grade_issues)}",
        f"benchmark_readiness={readiness_status or '-'}",
        f"experiment_decision={decision or '-'}:{decision_status or '-'}",
        f"hypothesis_outcome={hypothesis_decision or '-'}:{hypothesis_status or '-'}:{hypothesis_score:.2f}",
        f"failed_runs={failed_runs}",
        f"negative_metrics={negative_metrics}",
        f"uncertain_metrics={uncertain_metrics}",
        f"ablation={ablation_status or '-'}",
        f"preregistration={preregistration_status or '-'}",
    ]
    return _dimension("experiment_benchmark", score, 0.20, status, evidence, actions)


def _paper_dimension(data: dict[str, Any]) -> ScorecardDimension:
    review = _dict(data["review"])
    review_calibration = _dict(data["review_calibration"])
    traceability = _dict(data["claim_traceability"])
    citation_grounding = _dict(data["citation_grounding"])
    citation_coverage = _dict(data["citation_coverage"])
    results_presentation = _dict(data["results_presentation"])
    claim_consistency = _dict(data["claim_consistency"])
    claim_preflight = _dict(data["claim_preflight"])
    benchmark_evidence = _dict(data["benchmark_evidence"])
    revision_response = _dict(data["revision_response"])
    final = _dict(data["final"])
    score_after = _safe_float(final.get("score_after")) or _safe_float(review.get("score"))
    unsupported = _safe_int(final.get("unsupported_after"))
    weak = _safe_int(final.get("weak_after"))
    deferred = len(final.get("deferred_tasks", [])) if isinstance(final.get("deferred_tasks"), list) else 0
    final_status = str(final.get("status") or "")
    calibration_status = str(review_calibration.get("status") or "")
    calibration_flags = len(review_calibration.get("flags", [])) if isinstance(review_calibration.get("flags"), list) else 0
    traceability_status = str(traceability.get("status") or "")
    traceability_score = _safe_float(traceability.get("traceability_score"))
    traceability_blocked = _safe_int(traceability.get("blocked_claims"))
    traceability_review = _safe_int(traceability.get("review_claims"))
    grounding_status = str(citation_grounding.get("status") or "")
    grounding_score = _safe_float(citation_grounding.get("grounding_score"))
    grounding_blocked = _safe_int(citation_grounding.get("blocked_citations"))
    grounding_review = _safe_int(citation_grounding.get("review_citations"))
    coverage_status = str(citation_coverage.get("status") or "")
    coverage_score = _safe_float(citation_coverage.get("coverage_score"))
    coverage_blockers = len(citation_coverage.get("blocking_issues", [])) if isinstance(citation_coverage.get("blocking_issues"), list) else 0
    coverage_manual = len(citation_coverage.get("manual_tasks", [])) if isinstance(citation_coverage.get("manual_tasks"), list) else 0
    presentation_status = str(results_presentation.get("status") or "")
    presentation_score = _safe_float(results_presentation.get("presentation_score"))
    presentation_blockers = len(results_presentation.get("blocking_issues", [])) if isinstance(results_presentation.get("blocking_issues"), list) else 0
    presentation_manual = len(results_presentation.get("manual_tasks", [])) if isinstance(results_presentation.get("manual_tasks"), list) else 0
    consistency_status = str(claim_consistency.get("status") or "")
    consistency_score = _safe_float(claim_consistency.get("consistency_score"))
    consistency_blockers = len(claim_consistency.get("blocking_issues", [])) if isinstance(claim_consistency.get("blocking_issues"), list) else 0
    consistency_manual = len(claim_consistency.get("manual_tasks", [])) if isinstance(claim_consistency.get("manual_tasks"), list) else 0
    preflight_status = str(claim_preflight.get("status") or "")
    preflight_mode = str(claim_preflight.get("writing_mode") or "")
    preflight_risk = _safe_float(claim_preflight.get("risk_score"))
    preflight_blockers = len(claim_preflight.get("blocking_issues", [])) if isinstance(claim_preflight.get("blocking_issues"), list) else 0
    preflight_warnings = len(claim_preflight.get("warnings", [])) if isinstance(claim_preflight.get("warnings"), list) else 0
    preflight_actions = claim_preflight.get("required_actions", []) if isinstance(claim_preflight.get("required_actions"), list) else []
    bounded_negative_or_neutral = _bounded_negative_or_neutral_ready(benchmark_evidence, claim_preflight, claim_consistency, final)
    response_status = str(revision_response.get("status") or "")
    response_score = _safe_float(revision_response.get("response_score"))
    response_blockers = len(revision_response.get("blocking_issues", [])) if isinstance(revision_response.get("blocking_issues"), list) else 0
    response_manual = len(revision_response.get("manual_tasks", [])) if isinstance(revision_response.get("manual_tasks"), list) else 0
    response_actions = revision_response.get("required_actions", []) if isinstance(revision_response.get("required_actions"), list) else []
    revised_gate_clean = final_status == "ready_for_submission_check" and unsupported == 0 and weak == 0 and traceability_status == "pass"
    deferred_penalty = 0 if revised_gate_clean else deferred
    calibration_blocks = calibration_status == "block" and not revised_gate_clean
    response_blocks = response_status == "block"
    score = min(100.0, max(0.0, score_after * 10.0 - unsupported * 18.0 - weak * 5.0 - deferred_penalty * 8.0))
    if final_status == "ready_for_submission_check":
        score += 5.0
    elif final_status == "requires_human_evidence":
        score -= 10.0
    if calibration_blocks:
        score -= 15.0
    elif calibration_status == "review_required":
        score -= 7.0
    if traceability_status == "pass":
        score += 5.0
    elif traceability_status == "review_required":
        score -= 5.0
    elif traceability_status == "block":
        score -= 15.0
    if grounding_status == "pass":
        score += 5.0
    elif grounding_status == "review_required":
        score -= 5.0
    elif grounding_status == "block":
        score -= 15.0
    if coverage_status == "pass":
        score += 4.0
    elif coverage_status == "review_required":
        score -= 4.0
    elif coverage_status == "block":
        score -= 12.0
    if presentation_status == "pass":
        score += 5.0
    elif presentation_status == "review_required":
        score -= 5.0
    elif presentation_status == "block":
        score -= 15.0
    if consistency_status == "pass":
        score += 5.0
    elif consistency_status == "review_required":
        score -= 5.0
    elif consistency_status == "block":
        score -= 15.0
    if preflight_status == "pass":
        score += 3.0
    elif preflight_status == "review_required":
        if bounded_negative_or_neutral:
            score += 2.0
        else:
            score -= 5.0
    elif preflight_status == "block":
        score -= 15.0
    if response_status == "pass" or (response_status == "review_required" and revised_gate_clean):
        score += 3.0
    elif response_status == "review_required":
        score -= 6.0
    elif response_status == "block":
        score -= 15.0
    score = _clamp(score)
    actions: list[str] = []
    status = "pass"
    if unsupported or deferred_penalty or calibration_blocks or traceability_status == "block" or grounding_status == "block" or grounding_blocked or coverage_status == "block" or coverage_blockers or presentation_status == "block" or presentation_blockers or consistency_status == "block" or consistency_blockers or preflight_status == "block" or preflight_blockers or response_blocks or response_blockers:
        status = "block"
        actions.append("补证或删除 unsupported claim、needs_human_evidence 延后任务、review calibration、revision response、traceability/citation grounding/citation coverage 阻断项、结果呈现阻断问题、claim boundary preflight 阻断项和与 hypothesis outcome 不一致的过强结论。")
    elif weak or calibration_status == "review_required" or final_status in {"requires_revision", "ready_for_human_polish"}:
        status = "warn"
        actions.append("继续收窄 weak claim，并做人工语言、图表和引用打磨。")
    elif traceability_status == "review_required":
        status = "warn"
        actions.append("人工复核 10-claim-traceability.md 中 review_required 的 claim 证据链。")
    elif grounding_status == "review_required" or grounding_review:
        status = "warn"
        actions.append("人工复核 10-citation-grounding.md 中 weak overlap 的引用与附近正文 claim。")
    elif coverage_status == "review_required" or coverage_manual:
        status = "warn"
        actions.append("人工复核 10-citation-coverage.md 中未进入正文的高相关/近年 context 文献和 citation 过度集中问题。")
    elif presentation_status == "review_required" or presentation_manual:
        status = "warn"
        actions.append("人工复核 10-results-presentation.md 中结果章节、指标覆盖、图表引用和 CI/不确定性待办。")
    elif consistency_status == "review_required" or consistency_manual:
        status = "warn"
        actions.append("人工复核 10-claim-consistency.md 中 claim 强度、负结果和结果边界是否匹配 hypothesis outcome。")
    elif (preflight_status == "review_required" or preflight_warnings) and not bounded_negative_or_neutral:
        status = "warn"
        actions.extend(str(item) for item in preflight_actions[:3])
    elif response_status == "review_required" or response_manual:
        status = "warn"
        actions.extend(str(item) for item in response_actions[:3] or ["人工关闭 09-revision-response-audit.md 中未完成的修订任务回应。"])
    evidence = [
        f"review_score={score_after:.1f}",
        f"final_status={final_status or '-'}",
        f"review_calibration={calibration_status or '-'}:{calibration_flags}",
        f"traceability={traceability_status or '-'}:{traceability_score:.2f}",
        f"citation_grounding={grounding_status or '-'}:{grounding_score:.2f}",
        f"citation_coverage={coverage_status or '-'}:{coverage_score:.2f}",
        f"results_presentation={presentation_status or '-'}:{presentation_score:.2f}",
        f"claim_consistency={consistency_status or '-'}:{consistency_score:.2f}",
        f"claim_preflight={preflight_status or '-'}:{preflight_mode or '-'}:{preflight_risk:.2f}",
        f"bounded_negative_or_neutral={bounded_negative_or_neutral}",
        f"revision_response={response_status or '-'}:{response_score:.2f}",
        f"traceability_blocked={traceability_blocked}",
        f"traceability_review={traceability_review}",
        f"citation_grounding_blocked={grounding_blocked}",
        f"citation_grounding_review={grounding_review}",
        f"citation_coverage_blocking={coverage_blockers}",
        f"citation_coverage_manual={coverage_manual}",
        f"results_presentation_blocking={presentation_blockers}",
        f"results_presentation_manual={presentation_manual}",
        f"claim_consistency_blocking={consistency_blockers}",
        f"claim_consistency_manual={consistency_manual}",
        f"claim_preflight_blocking={preflight_blockers}",
        f"claim_preflight_warnings={preflight_warnings}",
        f"revision_response_blocking={response_blockers}",
        f"revision_response_manual={response_manual}",
        f"unsupported={unsupported}",
        f"weak={weak}",
        f"deferred={deferred}",
    ]
    return _dimension("paper_quality", score, 0.20, status, evidence, actions)


def _reproducibility_dimension(data: dict[str, Any]) -> ScorecardDimension:
    availability = _dict(data["availability"])
    release = _dict(data["release"])
    runbook = _dict(data["runbook"])
    environment = _dict(data["environment"])
    if not environment:
        environment = _dict(runbook.get("environment"))
    availability_status = str(availability.get("status") or "")
    release_status = str(release.get("status") or "")
    environment_status = str(environment.get("status") or "")
    manual = _list_count(availability, "manual_tasks") + _list_count(release, "manual_tasks")
    blocking = _list_count(availability, "blocking_issues") + _list_count(release, "blocking_issues")
    run_artifacts = len(runbook.get("artifacts", [])) if isinstance(runbook.get("artifacts"), list) else 0
    source_tree = environment.get("source_tree", {}) if isinstance(environment.get("source_tree"), dict) else {}
    source_files = _safe_int(source_tree.get("file_count"))
    package_versions = len(environment.get("package_versions", [])) if isinstance(environment.get("package_versions"), list) else 0
    has_environment = bool(environment)
    score = 20.0 if runbook else 0.0
    score += min(run_artifacts, 6) * 5.0
    score += 10.0 if environment_status == "complete" else 5.0 if has_environment else 0.0
    score += 5.0 if source_files else 0.0
    score += min(package_versions, 4) * 1.5
    score += _status_score(availability_status, {"ready_for_submission_check": 35, "ready_for_internal_release": 24, "needs_human_release_metadata": 12, "blocked": 0})
    score += _status_score(release_status, {"ready_for_release": 20, "ready_with_warnings": 15, "needs_release_metadata": 6, "blocked": 0})
    score -= min(25.0, manual * 3.0 + blocking * 10.0 + (0.0 if has_environment else 6.0))
    status = "pass"
    actions: list[str] = []
    if blocking or availability_status == "blocked" or release_status == "blocked":
        status = "block"
        actions.append("修复代码/数据可用性或 release metadata 阻断项。")
    elif manual or availability_status == "needs_human_release_metadata" or release_status == "needs_release_metadata":
        status = "manual_required"
        actions.append("补齐代码仓库、许可证、版本、归档 DOI、数据访问说明和环境归档。")
    elif not has_environment:
        status = "warn"
        actions.append("重新运行实验阶段，生成 04-environment-snapshot.md/json 以固定 Python、工具路径、包版本和源码哈希。")
    elif environment_status == "partial":
        status = "warn"
        actions.append("补齐环境快照中的警告项，优先归档 requirements/lockfile 或容器环境。")
    evidence = [
        f"availability={availability_status or '-'}",
        f"release={release_status or '-'}",
        f"runbook_artifacts={run_artifacts}",
        f"environment={environment_status or '-'}",
        f"source_files={source_files}",
        f"package_versions={package_versions}",
        f"manual={manual}",
        f"blocking={blocking}",
    ]
    return _dimension("reproducibility_release", score, 0.18, status, evidence, actions)


def _submission_dimension(data: dict[str, Any]) -> ScorecardDimension:
    ai_disclosure = _dict(data["ai_disclosure"])
    submission = _dict(data["submission"])
    package = _dict(data["package"])
    iteration = _dict(data["iteration"])
    repair_queue = _dict(data["repair_queue"])
    repair_resolution = _dict(data["repair_resolution"])
    stage_contract = _dict(data["stage_contract"])
    llm_trace_audit = _dict(data["llm_trace_audit"])
    run_economics = _dict(data["run_economics"])
    observability = _dict(data["observability"])
    open_source_compliance = _dict(data["open_source_compliance"])
    run_integrity = _dict(data["run_integrity"])
    submission_status = str(submission.get("status") or "")
    ai_status = str(ai_disclosure.get("status") or "")
    package_status = str(package.get("status") or "")
    iteration_status = str(iteration.get("status") or "")
    repair_status = str(repair_queue.get("status") or "")
    repair_resolution_status = str(repair_resolution.get("status") or "")
    repair_resolution_score = _safe_float(repair_resolution.get("resolution_score"))
    stage_contract_status = str(stage_contract.get("status") or "")
    llm_trace_status = str(llm_trace_audit.get("status") or "")
    run_economics_status = str(run_economics.get("status") or "")
    observability_status = str(observability.get("status") or "")
    open_source_status = str(open_source_compliance.get("status") or "")
    open_source_score = _safe_float(open_source_compliance.get("score"))
    run_integrity_status = str(run_integrity.get("status") or "")
    integrity_summary = run_integrity.get("summary") if isinstance(run_integrity.get("summary"), dict) else {}
    integrity_pass = _safe_int(integrity_summary.get("pass"))
    integrity_warn = _safe_int(integrity_summary.get("warn"))
    integrity_block = _safe_int(integrity_summary.get("block"))
    repair_summary = repair_queue.get("summary") if isinstance(repair_queue.get("summary"), dict) else {}
    repair_total = _safe_int(repair_summary.get("total"))
    repair_block = _safe_int(repair_summary.get("block"))
    repair_high = _safe_int(repair_summary.get("high"))
    repair_medium = _safe_int(repair_summary.get("medium"))
    llm_coverage = llm_trace_audit.get("coverage") if isinstance(llm_trace_audit.get("coverage"), dict) else {}
    llm_coverage_ratio = _safe_float(llm_coverage.get("coverage_ratio"))
    manual = _list_count(submission, "manual_tasks") + _list_count(package, "manual_tasks")
    if repair_status == "needs_repair":
        manual += max(1, repair_high + repair_medium)
    if repair_resolution_status == "review_required":
        manual += max(1, _list_count(repair_resolution, "manual_tasks"))
    if stage_contract_status == "needs_human_review":
        manual += max(1, _list_count(stage_contract, "manual_tasks"))
    if llm_trace_status == "warn":
        manual += max(1, _list_count(llm_trace_audit, "manual_tasks"))
    if run_economics_status == "review_required":
        manual += max(1, _list_count(run_economics, "manual_tasks"))
    if observability_status == "review_required":
        manual += max(1, _list_count(observability, "manual_tasks"))
    if open_source_status == "needs_human_review":
        manual += max(1, _list_count(open_source_compliance, "manual_tasks"))
    if run_integrity_status == "warn":
        manual += max(1, _list_count(run_integrity, "warnings"))
    blocking = _list_count(submission, "blocking_issues") + _list_count(package, "blocking_issues")
    if repair_status == "blocked_repair_required":
        blocking += max(1, repair_block)
    if repair_resolution_status == "block":
        blocking += max(1, _list_count(repair_resolution, "blocking_issues"))
    if stage_contract_status == "block":
        blocking += max(1, _list_count(stage_contract, "blocking_issues"))
    if llm_trace_status in {"", "block"}:
        blocking += max(1, _list_count(llm_trace_audit, "blocking_issues"))
    if run_economics_status in {"", "block"}:
        blocking += max(1, _list_count(run_economics, "blocking_issues"))
    if observability_status in {"", "block"}:
        blocking += max(1, _list_count(observability, "blocking_issues"))
    if open_source_status in {"", "block"}:
        blocking += max(1, _list_count(open_source_compliance, "blocking_issues"))
    if run_integrity_status == "block":
        blocking += max(1, _list_count(run_integrity, "blocking_issues"))
    score = _status_score(submission_status, {"ready_for_submission_check": 45, "needs_human_format_check": 24, "blocked": 0})
    score += _status_score(ai_status, {"not_applicable": 10, "needs_human_policy_check": 4})
    score += _status_score(package_status, {"ready_for_human_submission_upload": 40, "needs_human_submission_review": 25, "blocked": 0})
    score += _status_score(iteration_status, {"ready_for_submission_upload": 15, "ready_for_next_research_question": 12, "needs_targeted_iteration": 6, "needs_real_benchmark_iteration": 3, "needs_human_evidence": 0})
    score += _status_score(repair_status, {"pass": 10, "needs_repair": 3, "blocked_repair_required": 0})
    score += _status_score(repair_resolution_status, {"not_applicable": 6, "pass": 6, "review_required": 2, "block": 0})
    score += _status_score(stage_contract_status, {"pass": 8, "needs_human_review": 3, "block": 0})
    score += _status_score(llm_trace_status, {"pass": 8, "warn": 3, "block": 0})
    score += _status_score(run_economics_status, {"pass": 5, "review_required": 2, "block": 0})
    score += _status_score(observability_status, {"pass": 8, "review_required": 3, "block": 0})
    score += _status_score(open_source_status, {"pass": 8, "needs_human_review": 3, "block": 0, "no_external_lessons": 0})
    if run_integrity_status:
        score += _status_score(run_integrity_status, {"pass": 8, "warn": 3, "block": 0})
    score -= min(20.0, manual * 3.0 + blocking * 8.0)
    status = "pass"
    actions: list[str] = []
    if blocking or submission_status == "blocked" or package_status == "blocked" or repair_status == "blocked_repair_required" or repair_resolution_status == "block" or stage_contract_status == "block" or llm_trace_status in {"", "block"} or run_economics_status in {"", "block"} or observability_status in {"", "block"} or open_source_status in {"", "block"} or run_integrity_status == "block":
        status = "block"
        actions.append("修复投稿格式检查、投稿包缺失文件、12-repair-queue.md、12-repair-resolution-audit.md、13-open-source-compliance.md、13-agent-stage-contract.md、13-llm-trace-audit.md、13-run-economics-audit.md、13-agent-observability-audit.md 或 14-run-integrity-audit.md 中的 block 任务。")
    elif manual or submission_status == "needs_human_format_check" or package_status == "needs_human_submission_review" or ai_status == "needs_human_policy_check" or repair_status == "needs_repair" or repair_resolution_status == "review_required" or stage_contract_status == "needs_human_review" or llm_trace_status == "warn" or run_economics_status == "review_required" or observability_status == "review_required" or open_source_status == "needs_human_review" or run_integrity_status == "warn":
        status = "manual_required"
        actions.append("按目标 venue 模板、AI disclosure policy、submission-package/CHECKLIST.md、12-repair-queue.md、12-repair-resolution-audit.md、13-open-source-compliance.md、13-agent-stage-contract.md、13-llm-trace-audit.md、13-run-economics-audit.md、13-agent-observability-audit.md 和 14-run-integrity-audit.md 完成人工核验。")
    evidence = [
        f"submission={submission_status or '-'}",
        f"ai_disclosure={ai_status or '-'}",
        f"package={package_status or '-'}",
        f"iteration={iteration_status or '-'}",
        f"repair_queue={repair_status or '-'}:{repair_total}/{repair_block}/{repair_high}/{repair_medium}",
        f"repair_resolution={repair_resolution_status or '-'}:{repair_resolution_score:.2f}",
        f"stage_contract={stage_contract_status or '-'}",
        f"llm_trace_audit={llm_trace_status or '-'}:{llm_coverage_ratio:.2f}",
        f"run_economics={run_economics_status or '-'}",
        f"observability={observability_status or '-'}",
        f"open_source_compliance={open_source_status or '-'}:{open_source_score:.2f}",
        f"run_integrity={run_integrity_status or '-'}:{integrity_pass}/{integrity_warn}/{integrity_block}",
        f"manual={manual}",
        f"blocking={blocking}",
    ]
    return _dimension("submission_readiness", score, 0.12, status, evidence, actions)


def _dimension(category: str, score: float, weight: float, status: str, evidence: list[str], actions: list[str]) -> ScorecardDimension:
    return ScorecardDimension(category, round(_clamp(score), 1), weight, status, evidence, actions)


def _status(overall: float, dimensions: list[ScorecardDimension]) -> str:
    statuses = {item.status for item in dimensions}
    if "block" in statuses:
        return "blocked"
    if "manual_required" in statuses:
        return "needs_human_work"
    if overall < 70:
        return "needs_iteration"
    if "warn" in statuses or overall < 85:
        return "needs_targeted_iteration"
    return "ready_for_human_submission_upload"


def _recommendation(status: str, overall: float, dimensions: list[ScorecardDimension]) -> str:
    weakest = sorted(dimensions, key=lambda item: item.score)[:2]
    weak_text = "、".join(f"{item.category}={item.score:.1f}" for item in weakest)
    if status == "blocked":
        return f"当前 run 总分 {overall:.1f}/100，仍有阻断项。优先修复最低维度：{weak_text}。"
    if status == "needs_human_work":
        return f"当前 run 总分 {overall:.1f}/100，自动流程已给出材料，但仍需要人工补齐发布、实验或投稿待办。"
    if status == "needs_iteration":
        return f"当前 run 总分 {overall:.1f}/100，建议进入下一轮实验/修订，而不是直接打包投稿。"
    if status == "needs_targeted_iteration":
        return f"当前 run 总分 {overall:.1f}/100，主要剩余问题集中在：{weak_text}。"
    return f"当前 run 总分 {overall:.1f}/100，可进入人工投稿系统前最终核验。"


def _next_actions(status: str, dimensions: list[ScorecardDimension]) -> list[str]:
    actions = [action for item in sorted(dimensions, key=lambda value: value.score) for action in item.actions]
    if actions:
        return _dedupe(actions)[:8]
    if status == "ready_for_human_submission_upload":
        return ["下载 11-submission-package.zip，按目标 venue 官方系统完成最终人工提交。"]
    return ["从最低分维度开始补证、重跑 resume，并重新生成 13-research-scorecard。"]


def _weighted_score(dimensions: list[ScorecardDimension]) -> float:
    total_weight = sum(item.weight for item in dimensions)
    if total_weight <= 0:
        return 0.0
    return round(sum(item.score * item.weight for item in dimensions) / total_weight, 1)


def _bounded_negative_or_neutral_ready(
    benchmark_evidence: dict[str, Any],
    claim_preflight: dict[str, Any],
    claim_consistency: dict[str, Any],
    final: dict[str, Any],
) -> bool:
    if benchmark_evidence.get("publishable_negative_or_neutral_result") is not True:
        return False
    if str(benchmark_evidence.get("evidence_grade") or "") != "real_benchmark":
        return False
    if _list_count(benchmark_evidence, "blocking_issues") or _list_count(benchmark_evidence, "manual_tasks"):
        return False
    if str(final.get("status") or "") != "ready_for_submission_check":
        return False
    if _safe_int(final.get("unsupported_after")) or _safe_int(final.get("weak_after")):
        return False
    if str(claim_consistency.get("status") or "") != "pass" or _list_count(claim_consistency, "blocking_issues"):
        return False
    preflight_status = str(claim_preflight.get("status") or "")
    preflight_mode = str(claim_preflight.get("writing_mode") or "")
    if preflight_status == "pass":
        return True
    return preflight_status == "review_required" and preflight_mode == "negative_or_pivot_report" and not _list_count(claim_preflight, "blocking_issues")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _list_count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    return len(value) if isinstance(value, list) else 0


def _novelty_item(novelty: dict[str, Any], title: str) -> dict[str, Any]:
    for item in novelty.get("items", []) if isinstance(novelty.get("items"), list) else []:
        if isinstance(item, dict) and str(item.get("idea_title") or "") == title:
            return item
    return {}


def _status_score(status: str, mapping: dict[str, float]) -> float:
    return float(mapping.get(status, 0.0))


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
