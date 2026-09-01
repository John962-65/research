from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .run_summary import RunSummary, build_run_dashboard


RUN_MEMORY_JSON = "runs-memory.json"
RUN_MEMORY_MD = "runs-memory.md"


@dataclass(frozen=True)
class RunMemorySignal:
    category: str
    severity: str
    count: int
    run_ids: list[str]
    evidence: list[str]
    recommended_action: str
    next_run_hint: str
    recommended_config: dict[str, Any]


@dataclass(frozen=True)
class RunMemoryReport:
    generated_at: str
    runs_dir: str
    total_runs: int
    analyzed_runs: int
    status: str
    recurring_signals: list[RunMemorySignal]
    recommended_defaults: list[str]
    recommended_config: dict[str, Any]
    next_run_checklist: list[str]
    carry_forward_notes: list[str]


def build_run_memory(runs_dir: Path, limit: int = 100) -> RunMemoryReport:
    dashboard = build_run_dashboard(runs_dir, limit=limit)
    signals = _build_signals(runs_dir, dashboard.runs)
    return RunMemoryReport(
        generated_at=_utc_now(),
        runs_dir=str(runs_dir),
        total_runs=dashboard.total_runs,
        analyzed_runs=len(dashboard.runs),
        status=_status(signals, dashboard.runs),
        recurring_signals=signals,
        recommended_defaults=_recommended_defaults(signals),
        recommended_config=_recommended_config(signals),
        next_run_checklist=_next_run_checklist(signals),
        carry_forward_notes=_carry_forward_notes(signals, dashboard.runs),
    )


def write_run_memory(memory: RunMemoryReport, out_dir: Path, basename: str = "runs-memory") -> tuple[Path, Path]:
    json_path = out_dir / f"{basename}.json"
    md_path = out_dir / f"{basename}.md"
    write_json(json_path, memory)
    write_text(md_path, render_run_memory_markdown(memory))
    return json_path, md_path


def render_run_memory_markdown(memory: RunMemoryReport) -> str:
    lines = [
        "# Runs 复盘记忆",
        "",
        f"- 生成时间：{memory.generated_at}",
        f"- Runs 目录：{memory.runs_dir}",
        f"- 纳入 run：{memory.analyzed_runs}/{memory.total_runs}",
        f"- 状态：{memory.status}",
        "",
        "## 反复信号",
        "| 类别 | 严重性 | 次数 | Runs | 证据 | 建议动作 | 下次默认 |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    if not memory.recurring_signals:
        lines.append("| 无 | - | 0 | - | - | 当前没有可沉淀的跨 run 风险。 | - |")
    for signal in memory.recurring_signals:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(signal.category),
                    _cell(signal.severity),
                    str(signal.count),
                    _cell(", ".join(signal.run_ids)),
                    _cell("；".join(signal.evidence[:3])),
                    _cell(signal.recommended_action),
                    _cell(signal.next_run_hint),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 推荐默认设置"])
    lines.extend(f"- {item}" for item in memory.recommended_defaults) if memory.recommended_defaults else lines.append("- 暂无额外默认设置。")
    if memory.recommended_config:
        lines.extend(["", "## 推荐表单配置"])
        for key, value in memory.recommended_config.items():
            if isinstance(value, list):
                rendered = ", ".join(str(item) for item in value)
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
    lines.extend(["", "## 下一次启动前检查"])
    lines.extend(f"- [ ] {item}" for item in memory.next_run_checklist)
    lines.extend(["", "## 继承说明"])
    lines.extend(f"- {item}" for item in memory.carry_forward_notes) if memory.carry_forward_notes else lines.append("- 无")
    return "\n".join(lines)


def _build_signals(runs_dir: Path, runs: list[RunSummary]) -> list[RunMemorySignal]:
    buckets: dict[str, dict[str, Any]] = {}
    for run in runs:
        run_dir = runs_dir / run.id
        _add_status_signals(buckets, run)
        _add_llm_trace_signals(buckets, run, _read_json(run_dir / "13-llm-trace-audit.json"))
        _add_run_economics_signals(buckets, run, _read_json(run_dir / "13-run-economics-audit.json"))
        _add_agent_observability_signals(buckets, run, _read_json(run_dir / "13-agent-observability-audit.json"))
        _add_open_source_compliance_signals(buckets, run, _read_json(run_dir / "13-open-source-compliance.json"))
        _add_agent_stage_contract_signals(buckets, run, _read_json(run_dir / "13-agent-stage-contract.json"))
        _add_research_scorecard_signals(buckets, run, _read_json(run_dir / "13-research-scorecard.json"))
        _add_run_integrity_signals(buckets, run, _read_json(run_dir / "14-run-integrity-audit.json"))
        _add_final_handoff_signals(buckets, run, _read_json(run_dir / "14-final-handoff.json"))
        _add_repair_resolution_signals(buckets, run, _read_json(run_dir / "12-repair-resolution-audit.json"))
        _add_literature_search_feedback_signals(buckets, run, _read_json(run_dir / "01-literature-search-feedback.json"))
        _add_literature_rescue_execution_signals(buckets, run, _read_json(run_dir / "01-literature-rescue-execution.json"))
        _add_literature_source_health_signals(buckets, run, _read_json(run_dir / "01-literature-source-health.json"))
        _add_literature_signals(buckets, run, _read_json(run_dir / "01-literature-rescue-plan.json"), _read_json(run_dir / "01-seed-paper-intake.json"))
        _add_experiment_manager_signals(buckets, run, _read_json(run_dir / "02-experiment-manager.json"))
        _add_review_constraint_signals(buckets, run, _read_json(run_dir / "03-review-constraint-compliance.json"))
        _add_experiment_signals(
            buckets,
            run,
            _read_json(run_dir / "04-result-validation.json"),
            _read_json(run_dir / "04-failure-analysis.json"),
            _read_json(run_dir / "04-hypothesis-outcome.json"),
            _read_json(run_dir / "04-experiment-runbook.json"),
            _read_json(run_dir / "03-benchmark-plan.json"),
            _read_json(run_dir / "03-benchmark-adapters.json"),
            _read_json(run_dir / "04-benchmark-result-schema-audit.json"),
        )
        _add_environment_snapshot_signals(buckets, run, _read_json(run_dir / "04-environment-snapshot.json"))
        _add_paper_release_signals(
            buckets,
            run,
            _read_json(run_dir / "10-citation-grounding.json"),
            _read_json(run_dir / "10-citation-coverage.json"),
            _read_json(run_dir / "10-results-presentation.json"),
            _read_json(run_dir / "10-claim-consistency.json"),
            _read_json(run_dir / "10-release-metadata.json"),
        )
        _add_gate_notes(buckets, run, _read_json(run_dir / "approval.json"))
    signals = [_to_signal(category, payload) for category, payload in buckets.items()]
    return sorted(signals, key=lambda item: (_severity_rank(item.severity), item.count, item.category), reverse=True)


def _add_status_signals(buckets: dict[str, dict[str, Any]], run: RunSummary) -> None:
    if run.status == "failed":
        category = "llm_configuration" if run.diagnostic_category == "llm_configuration" else "run_failure"
        _bucket(
            buckets,
            category,
            "block",
            run,
            f"{run.id}: status=failed category={run.diagnostic_category or '-'}",
            "先修复失败类别，再继续从 checkpoint resume。",
            "每次启动前运行 preflight，并确认模型名、Base URL、API Key 与网络连通。",
        )
    elif run.status == "cancelled":
        _bucket(
            buckets,
            "cancelled_runs",
            "warn",
            run,
            f"{run.id}: run was cancelled",
            "确认取消原因是否来自配置、等待审批或实验耗时过长。",
            "长任务启动前先限制预算和执行模式，避免无目标地长跑。",
        )


def _add_llm_trace_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, audit: dict[str, Any]) -> None:
    if not audit:
        return
    status = str(audit.get("status") or "")
    if status not in {"block", "warn"}:
        return
    coverage = audit.get("coverage") if isinstance(audit.get("coverage"), dict) else {}
    ledger = audit.get("ledger_summary") if isinstance(audit.get("ledger_summary"), dict) else {}
    blockers = _list_values(audit, "blocking_issues", limit=2)
    warnings = _list_values(audit, "warnings", limit=2)
    failed = _safe_int(ledger.get("failed_calls"))
    budget = _safe_int(ledger.get("budget_exceeded_calls"))
    severity = "block" if status == "block" or blockers or failed or budget else "warn"
    _bucket(
        buckets,
        "llm_trace_audit",
        severity,
        run,
        (
            f"{run.id}: llm_trace={status}, coverage={coverage.get('passed_required', 0)}/{coverage.get('required_stages', 0)}, "
            f"total_calls={ledger.get('total_calls', 0)}, success={ledger.get('successful_calls', 0)}, failed={failed}, budget={budget}"
        ),
        (blockers or warnings or ["修复 13-llm-trace-audit 中的 LLM ledger 覆盖、失败调用、预算或 AI disclosure 问题。"])[0],
        "下一轮必须保留 run-llm-ledger 和 13-llm-trace-audit；关键科研阶段要有 success LLM 调用，预算不足时提高 llm_max_calls 后从 checkpoint 重跑。",
    )


def _add_run_economics_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, audit: dict[str, Any]) -> None:
    if not audit:
        return
    status = str(audit.get("status") or "")
    if status not in {"block", "review_required"}:
        return
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    budget = audit.get("budget") if isinstance(audit.get("budget"), dict) else {}
    pricing = audit.get("pricing") if isinstance(audit.get("pricing"), dict) else {}
    blockers = _list_values(audit, "blocking_issues", limit=2)
    manual = _list_values(audit, "manual_tasks", limit=2)
    warnings = _list_values(audit, "warnings", limit=2)
    actions = _list_values(audit, "recommended_actions", limit=2)
    failed = _safe_int(summary.get("failed_calls"))
    budget_exceeded = _safe_int(summary.get("budget_exceeded_calls"))
    call_utilization = _safe_float(summary.get("call_utilization") or budget.get("call_utilization"))
    prompt_utilization = _safe_float(summary.get("prompt_utilization") or budget.get("prompt_utilization"))
    cost = summary.get("estimated_cost_usd")
    cost_text = f"${float(cost):.6f}" if isinstance(cost, (int, float)) else "unpriced"
    severity = "block" if status == "block" or blockers or failed or budget_exceeded else "warn"
    _bucket(
        buckets,
        "run_economics",
        severity,
        run,
        (
            f"{run.id}: run_economics={status}, calls={summary.get('total_calls', 0)}, "
            f"input_tokens={summary.get('input_tokens_estimated', 0)}, output_tokens={summary.get('output_tokens_estimated', 0)}, "
            f"failed={failed}, budget={budget_exceeded}, call_util={call_utilization:.2f}, "
            f"prompt_util={prompt_utilization:.2f}, cost={cost_text}, pricing={'on' if pricing.get('cost_estimation_enabled') else 'off'}"
        ),
        (blockers or manual or warnings or actions or ["修复 13-run-economics-audit 中的 LLM ledger、预算压力或 token 单价配置问题。"])[0],
        "下一轮配置 LLM 调用/prompt 预算和 input/output token 单价；保留 run-llm-ledger 与 13-run-economics-audit。",
    )


def _add_agent_observability_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, audit: dict[str, Any]) -> None:
    if not audit:
        return
    status = str(audit.get("status") or "")
    if status not in {"block", "review_required"}:
        return
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    blockers = _list_values(audit, "blocking_issues", limit=2)
    manual = _list_values(audit, "manual_tasks", limit=2)
    warnings = _list_values(audit, "warnings", limit=2)
    severity = "block" if status == "block" or blockers else "warn"
    _bucket(
        buckets,
        "agent_observability",
        severity,
        run,
        (
            f"{run.id}: observability={status}, events={summary.get('manifest_events', 0)}, "
            f"artifacts={summary.get('manifest_artifacts', 0)}, llm_failed={summary.get('llm_failed_calls', 0)}, "
            f"repair_queue={summary.get('repair_queue_status') or '-'}"
        ),
        (blockers or manual or warnings or ["修复 13-agent-observability-audit 中的 manifest、ledger、human gate、runbook、recovery 或 repair queue trace 问题。"])[0],
        "下一轮必须保留 state/run-manifest/run-llm-ledger/run-config/approval/runbook/repair queue；失败或等待状态要生成 diagnostics 和 recovery plan。",
    )


def _add_agent_stage_contract_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, audit: dict[str, Any]) -> None:
    if not audit:
        return
    status = str(audit.get("status") or "")
    if status not in {"block", "needs_human_review"}:
        return
    checks = [item for item in _list_values_raw(audit.get("checks")) if isinstance(item, dict)]
    blocking = _list_values(audit, "blocking_issues", limit=2)
    manual = _list_values(audit, "manual_tasks", limit=2)
    actions = _list_values(audit, "recommended_actions", limit=2)
    blocked_stages = [
        str(item.get("stage") or "").strip()
        for item in checks
        if str(item.get("status") or "") in {"block", "missing"} and str(item.get("stage") or "").strip()
    ]
    review_stages = [
        str(item.get("stage") or "").strip()
        for item in checks
        if str(item.get("status") or "") == "warn" and str(item.get("stage") or "").strip()
    ]
    severity = "block" if status == "block" or blocking or blocked_stages else "warn"
    _bucket(
        buckets,
        "agent_stage_contract",
        severity,
        run,
        (
            f"{run.id}: stage_contract={status}, score={_safe_float(audit.get('score')):.2f}, "
            f"blocked_stages={','.join(blocked_stages[:4]) or '-'}, review_stages={','.join(review_stages[:4]) or '-'}"
        ),
        (blocking or manual or actions or ["修复 13-agent-stage-contract 中的 planning、literature、human gate、experiment、release 或 observability 契约缺口。"])[0],
        "下一轮启动前把 13-agent-stage-contract 的阻断阶段转成 preflight 配置、人工约束、文献 seed、benchmark/release 元数据或 repair-resume 任务。",
    )


def _add_research_scorecard_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, scorecard: dict[str, Any]) -> None:
    if not scorecard:
        return
    status = str(scorecard.get("status") or "")
    if status not in {"blocked", "needs_human_work", "needs_iteration", "needs_targeted_iteration"}:
        return
    dimensions = [item for item in _list_values_raw(scorecard.get("dimensions")) if isinstance(item, dict)]
    weakest = sorted(dimensions, key=lambda item: _safe_float(item.get("score")))[:3]
    weak_text = ",".join(f"{item.get('category') or '-'}:{_safe_float(item.get('score')):.1f}" for item in weakest) or "-"
    blocking = _list_values(scorecard, "blocking_issues", limit=2)
    manual = _list_values(scorecard, "manual_tasks", limit=2)
    next_actions = _list_values(scorecard, "next_actions", limit=2)
    recommendation = str(scorecard.get("recommendation") or "").strip()
    severity = "block" if status == "blocked" or blocking else "warn"
    _bucket(
        buckets,
        "research_scorecard",
        severity,
        run,
        (
            f"{run.id}: scorecard={status}, overall={_safe_float(scorecard.get('overall_score')):.1f}, "
            f"weakest={weak_text}, blocking={len(scorecard.get('blocking_issues', []) if isinstance(scorecard.get('blocking_issues'), list) else [])}, "
            f"manual={len(scorecard.get('manual_tasks', []) if isinstance(scorecard.get('manual_tasks'), list) else [])}"
        ),
        (blocking or manual or next_actions or [recommendation] or ["按 13-research-scorecard 的最低维度规划下一轮检索、实验、写作或投稿修复。"])[0],
        "下一轮启动前先读取 13-research-scorecard；把最低分维度转成文献 seed、真实 benchmark、claim 修订、release 元数据或人工待办。",
    )


def _add_run_integrity_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, audit: dict[str, Any]) -> None:
    if not audit:
        return
    status = str(audit.get("status") or "")
    if status not in {"block", "warn"}:
        return
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    blockers = _list_values(audit, "blocking_issues", limit=2)
    warnings = _list_values(audit, "warnings", limit=2)
    actions = _list_values(audit, "recommended_actions", limit=2)
    items = [item for item in _list_values_raw(audit.get("items")) if isinstance(item, dict)]
    problem_items = [
        f"{item.get('category') or '-'}:{item.get('name') or '-'}"
        for item in items
        if str(item.get("status") or "") in {"block", "warn"}
    ][:4]
    severity = "block" if status == "block" or blockers else "warn"
    _bucket(
        buckets,
        "run_integrity_audit",
        severity,
        run,
        (
            f"{run.id}: integrity={status}, pass={summary.get('pass', 0)}, warn={summary.get('warn', 0)}, "
            f"block={summary.get('block', 0)}, problems={','.join(problem_items) or '-'}"
        ),
        (blockers or warnings or actions or ["修复 14-run-integrity-audit 中的 artifact、JSON、manifest、gate、package、LLM ledger 或 secret persistence 问题。"])[0],
        "下一轮必须保留完整 artifact inventory、JSON、manifest events/artifacts、human/execution gate、LLM ledger、submission package 和无密钥 run-config。",
    )


def _add_final_handoff_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, handoff: dict[str, Any]) -> None:
    if not handoff:
        return
    status = str(handoff.get("status") or "")
    zip_invalid = handoff.get("package_zip_valid") is False or handoff.get("package_zip_exists") is False
    if status not in {"blocked", "ready_for_human_handoff"} and not zip_invalid:
        return
    blockers = _list_values(handoff, "blocking_issues", limit=2)
    manual = _list_values(handoff, "manual_tasks", limit=2)
    actions = _list_values(handoff, "recommended_actions", limit=2)
    all_blockers = handoff.get("blocking_issues") if isinstance(handoff.get("blocking_issues"), list) else []
    all_manual = handoff.get("manual_tasks") if isinstance(handoff.get("manual_tasks"), list) else []
    severity = "block" if status == "blocked" or blockers or zip_invalid else "warn"
    package_zip_exists = handoff.get("package_zip_exists") is True
    package_zip_valid = handoff.get("package_zip_valid") if isinstance(handoff.get("package_zip_valid"), bool) else None
    package_has_integrity_audit = handoff.get("package_has_integrity_audit") is True
    hint = (
        "下一轮必须以 14-final-handoff 收尾；blocked 不得交付 ZIP，ready_for_human_handoff 必须完成人工核验后才标记为可上传。"
    )
    if zip_invalid:
        hint += " 若 ZIP 缺失或无效，重新生成 11-submission-package.zip、14-run-integrity-audit 和 14-final-handoff。"
    if not package_has_integrity_audit:
        hint += " 若需离线交付，重新生成投稿包或附上 14-run-integrity-audit.*。"
    _bucket(
        buckets,
        "final_handoff",
        severity,
        run,
        (
            f"{run.id}: final_handoff={status}, package={handoff.get('package_status') or '-'}, "
            f"scorecard={handoff.get('scorecard_status') or '-'}, integrity={handoff.get('run_integrity_status') or '-'}, "
            f"zip_exists={'Y' if package_zip_exists else 'N'}, zip_valid={_tri_state(package_zip_valid)}, "
            f"audit_snapshot={'Y' if package_has_integrity_audit else 'N'}, "
            f"blocking={len(all_blockers)}, manual={len(all_manual)}"
        ),
        (blockers or manual or actions or ["修复 14-final-handoff 中的 ZIP、scorecard、run integrity、投稿包审计快照或人工交付待办。"])[0],
        hint,
    )


def _add_repair_resolution_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, audit: dict[str, Any]) -> None:
    if not audit:
        return
    status = str(audit.get("status") or "")
    if status not in {"block", "review_required"}:
        return
    blockers = _list_values(audit, "blocking_issues", limit=2)
    manual = _list_values(audit, "manual_tasks", limit=2)
    actions = _list_values(audit, "required_actions", limit=2)
    remaining = len(audit.get("remaining_items", []) if isinstance(audit.get("remaining_items"), list) else [])
    new_items = len(audit.get("new_items", []) if isinstance(audit.get("new_items"), list) else [])
    resolved = len(audit.get("resolved_items", []) if isinstance(audit.get("resolved_items"), list) else [])
    severity = "block" if status == "block" or blockers else "warn"
    _bucket(
        buckets,
        "repair_resolution_audit",
        severity,
        run,
        (
            f"{run.id}: repair_resolution={status}, score={_safe_float(audit.get('resolution_score')):.2f}, "
            f"applied={bool(audit.get('applied'))}, queue={audit.get('queue_status') or '-'}, "
            f"remaining={remaining}, resolved={resolved}, new={new_items}, rerun_from={audit.get('rerun_from') or '-'}"
        ),
        (blockers or manual or actions or ["修复 12-repair-resolution-audit 中仍未闭环的原 repair-resume 项。"])[0],
        "下一轮优先从 repair-resume 继续，而不是新开低上下文 run；修复后重新检查 repair queue、scorecard 和 run integrity。",
    )


def _add_literature_search_feedback_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, feedback: dict[str, Any]) -> None:
    if not feedback:
        return
    status = str(feedback.get("status") or "")
    if status not in {"needs_source_repair", "needs_search_revision", "needs_manual_seed"}:
        return
    recommended_queries = [item for item in _list_values_raw(feedback.get("recommended_queries")) if isinstance(item, dict)]
    seed_targets = [item for item in _list_values_raw(feedback.get("seed_paper_targets")) if isinstance(item, dict)]
    repair_tasks = [item for item in _list_values_raw(feedback.get("retrieval_repair_tasks")) if isinstance(item, dict)]
    agent_query_tasks = [
        item
        for item in repair_tasks
        if str(item.get("query") or "").strip() and str(item.get("owner") or "") in {"agent", "agent+human"}
    ]
    source_actions = _list_values(feedback, "source_actions", limit=2)
    guidance = _list_values(feedback, "approval_guidance", limit=2)
    next_config = feedback.get("next_run_config") if isinstance(feedback.get("next_run_config"), dict) else {}
    top_task = _top_priority_task(repair_tasks)
    top_query = _first_query(recommended_queries, agent_query_tasks)
    seed_min = _safe_int(next_config.get("seed_papers_min"))
    max_papers = _safe_int(next_config.get("max_papers"))
    max_queries = _safe_int(next_config.get("max_search_queries"))
    sources = next_config.get("sources") if isinstance(next_config.get("sources"), list) else []
    action = str(top_task.get("action") or "").strip() if top_task else ""
    rationale = str(top_task.get("rationale") or "").strip() if top_task else ""
    if action and rationale:
        action = f"{action}（{rationale}）"
    action = action or (source_actions or guidance or ["承接 01-literature-search-feedback 的 query/seed/source 修复任务后再进入 idea/实验。"])[0]
    hint = (
        f"下一轮把 01-literature-search-feedback 推荐配置写入表单：provider={next_config.get('literature_provider') or 'online/auto'}, "
        f"max_papers>={max_papers or 12}, max_search_queries>={max_queries or 6}, seed_papers>={seed_min or 3}, "
        f"sources={','.join(str(item) for item in sources[:4]) or 'openalex,arxiv,crossref'}"
    )
    if top_query:
        hint += f"，并加入补充检索式：{top_query}"
    recommended_config = _literature_recommended_config(
        provider=str(next_config.get("literature_provider") or "online"),
        sources=[str(item) for item in sources if str(item).strip()] or ["openalex", "arxiv", "crossref"],
        max_papers=max_papers or 12,
        max_search_queries=max_queries or 6,
        seed_papers_min=seed_min or 3,
        extra_search_queries=[top_query] if top_query else [],
    )
    _bucket(
        buckets,
        "literature_search_feedback",
        "warn",
        run,
        (
            f"{run.id}: search_feedback={status}, recommended_queries={len(recommended_queries)}, "
            f"agent_queries={len(agent_query_tasks)}, seed_targets={len(seed_targets)}, source_actions={len(source_actions)}, "
            f"next=max_papers:{max_papers or '-'}, max_search_queries:{max_queries or '-'}, seed_min:{seed_min or '-'}"
        ),
        action,
        hint,
        recommended_config=recommended_config,
    )


def _add_literature_rescue_execution_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, execution: dict[str, Any]) -> None:
    if not execution:
        return
    status = str(execution.get("status") or "")
    unresolved = _safe_int(execution.get("unresolved_query_outcomes"))
    if status != "no_new_papers" and unresolved <= 0:
        return
    repair_task_ids = [str(item).strip() for item in _list_values_raw(execution.get("repair_task_ids")) if str(item).strip()]
    selected_queries = [str(item).strip() for item in _list_values_raw(execution.get("selected_queries")) if str(item).strip()]
    actions = _list_values(execution, "required_actions", limit=2)
    warnings = _list_values(execution, "warnings", limit=2)
    closed = _safe_int(execution.get("closed_query_outcomes"))
    new_unique = _safe_int(execution.get("new_unique_papers"))
    top_query = selected_queries[0] if selected_queries else ""
    action = (actions or warnings or ["补检索执行没有改善候选池；需要换 query、修复 source 或补 DOI/URL seed。"])[0]
    hint = "下一轮不要重复同一批低收益 query；改用 facet-aware 英文检索式，保留 online/auto 多源检索，并补 3 篇以上 DOI/URL seed。"
    if top_query:
        hint += f" 需要替换或增强的上一轮 query：{top_query}"
    _bucket(
        buckets,
        "literature_rescue_execution",
        "warn",
        run,
        (
            f"{run.id}: rescue_execution={status}, repair_tasks={len(repair_task_ids)}, "
            f"closed={closed}, unresolved={unresolved}, new_unique={new_unique}, selected_queries={len(selected_queries)}"
        ),
        action,
        hint,
        recommended_config=_literature_recommended_config(extra_search_queries=[top_query] if top_query else []),
    )


def _add_literature_source_health_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, health: dict[str, Any]) -> None:
    if not health:
        return
    rate_limited = _safe_int(health.get("rate_limited_sources"))
    failed = _safe_int(health.get("failed_sources"))
    query_attempts = _safe_int(health.get("query_attempts"))
    query_successes = _safe_int(health.get("query_successes"))
    query_failures = _safe_int(health.get("query_failures"))
    query_rate_limits = _safe_int(health.get("query_rate_limits"))
    if not any([rate_limited, failed, query_failures, query_rate_limits]) and not (query_attempts > 0 and query_successes == 0):
        return

    sources = [item for item in _list_values_raw(health.get("sources")) if isinstance(item, dict)]
    problematic_sources = _problematic_literature_sources(sources)
    total_sources = _safe_int(health.get("total_sources")) or len(sources)
    all_sources_problematic = bool(total_sources and len({item for item in problematic_sources if item}) >= total_sources)
    severity = "block" if (query_attempts > 0 and query_successes == 0) or all_sources_problematic else "warn"
    source_text = ",".join(problematic_sources[:5]) or "-"
    action = "修复 01-literature-source-health 中的限流/失败文献源，再重新执行检索健康检查。"
    hint = "下一轮使用 online/auto，至少保留 openalex、arxiv、crossref 兜底，max_search_queries>=6，max_papers>=12。"
    if any(source == "semantic_scholar" for source in problematic_sources):
        action = "Semantic Scholar 出现限流/失败时，设置 SEMANTIC_SCHOLAR_API_KEY 或暂时从 sources 移除并用 OpenAlex/arXiv/Crossref 兜底。"
        hint = "配置 SEMANTIC_SCHOLAR_API_KEY 后重启服务；同时保留 openalex、arxiv、crossref，批准前重跑文献源健康检查。"
    if any(source in {"openalex", "crossref", "pubmed"} for source in problematic_sources):
        hint += " 对 OpenAlex/Crossref/PubMed 设置 RESEARCH_AGENT_CONTACT_EMAIL，提高请求稳定性。"
    recommended_sources = ["openalex", "arxiv", "crossref"]
    semantic_key_required = any(source == "semantic_scholar" for source in problematic_sources)
    if not semantic_key_required:
        recommended_sources = ["semantic_scholar", *recommended_sources]
    _bucket(
        buckets,
        "literature_source_health",
        severity,
        run,
        (
            f"{run.id}: rate_limited_sources={rate_limited}, failed_sources={failed}, "
            f"query_attempts={query_attempts}, query_successes={query_successes}, "
            f"query_failures={query_failures}, query_rate_limits={query_rate_limits}, "
            f"problematic_sources={source_text}"
        ),
        action,
        hint,
        recommended_config=_literature_recommended_config(
            sources=recommended_sources,
            semantic_scholar_api_key_required=semantic_key_required,
            contact_email_required=any(source in {"openalex", "crossref", "pubmed"} for source in problematic_sources),
        ),
    )


def _add_literature_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, rescue: dict[str, Any], seed_intake: dict[str, Any]) -> None:
    status = run.literature_rescue_status
    if status in {"block", "needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        actions = _list_values(rescue, "required_actions", limit=2)
        repairs = _list_values(rescue, "source_repairs", limit=2)
        action = actions[0] if actions else "补检索、补人工 seed paper 或修复文献源后，再重新生成审核 gate。"
        hint = "下一轮优先设置 literature_provider=online/auto、max_papers>=12，并填入高相关 DOI/URL 作为 seed_papers。"
        if any("SEMANTIC_SCHOLAR_API_KEY" in item for item in repairs + actions):
            hint = "设置 SEMANTIC_SCHOLAR_API_KEY 后重启服务，同时保留 openalex/arxiv/crossref 兜底。"
        _bucket(
            buckets,
            "literature_repair",
            "block" if status == "block" else "warn",
            run,
            f"{run.id}: literature_rescue={status}, rescue_queries={run.literature_rescue_queries}",
            action,
            hint,
            recommended_config=_literature_recommended_config(
                sources=["openalex", "arxiv", "crossref"] if any("SEMANTIC_SCHOLAR_API_KEY" in item for item in repairs + actions) else None,
                semantic_scholar_api_key_required=any("SEMANTIC_SCHOLAR_API_KEY" in item for item in repairs + actions),
            ),
        )
    if run.selected_papers < 3 and run.citations < 3 and run.stage != "failed":
        _bucket(
            buckets,
            "thin_evidence_pool",
            "warn",
            run,
            f"{run.id}: selected_papers={run.selected_papers}, citations={run.citations}",
            "人工补充强相关种子文献，避免 idea 阶段建立在过小证据池上。",
            "下一轮至少提供 3 篇人工 seed papers，并提高 max_papers。",
            recommended_config=_literature_recommended_config(),
        )
    seed_status = str(seed_intake.get("status") or "")
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    if seed_status in {"block", "review_required"} or seed_role_status == "review_required":
        _bucket(
            buckets,
            "seed_paper_intake",
            "block" if seed_status == "block" else "warn",
            run,
            (
                f"{run.id}: seed_intake={seed_status or '-'}, role_coverage={seed_role_status or '-'}, "
                f"curated={seed_intake.get('curated_seed_papers', 0)}/{seed_intake.get('total_seed_entries', 0)}, "
                f"missing_roles={','.join(str(item) for item in seed_intake.get('missing_curated_seed_roles', [])[:4]) if isinstance(seed_intake.get('missing_curated_seed_roles'), list) else '-'}"
            ),
            _first_list_value(seed_intake, "required_actions", "修复人工 seed，使核心 DOI/URL 进入 curated context。"),
            "下一轮优先填 DOI 或 URL，并覆盖 review/survey、benchmark/dataset、baseline/method、recent work 中至少 3 类；批准前检查 01-seed-paper-intake.md。",
            recommended_config=_literature_recommended_config(),
        )


def _add_open_source_compliance_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, compliance: dict[str, Any]) -> None:
    if not compliance:
        return
    status = str(compliance.get("status") or "")
    if status not in {"block", "needs_human_review"}:
        return
    results = [item for item in _list_values_raw(compliance.get("lesson_results")) if isinstance(item, dict)]
    blocked_lessons = [str(item.get("lesson_id") or "") for item in results if str(item.get("status") or "") == "block"]
    review_lessons = [str(item.get("lesson_id") or "") for item in results if str(item.get("status") or "") == "warn"]
    blocking = _list_values(compliance, "blocking_issues", limit=3)
    manual = _list_values(compliance, "manual_tasks", limit=3)
    action = (blocking or manual or ["修复 13-open-source-compliance 中未满足的外部项目约束。"])[0]
    if blocked_lessons:
        action = f"{action}（lesson={', '.join(blocked_lessons[:8])}）"
    hint = (
        "下一轮启动前按 13-open-source-compliance 修复：online/auto 文献、多源 query/source 审计、人工约束、local/benchmark 执行证据、"
        "run-manifest/LLM ledger/成本审计和 AI disclosure 缺口。"
    )
    _bucket(
        buckets,
        "open_source_compliance",
        "block" if status == "block" else "warn",
        run,
        (
            f"{run.id}: open_source_compliance={status}, score={_safe_float(compliance.get('score')):.2f}, "
            f"checked_lessons={_safe_int(compliance.get('checked_lessons'))}, "
            f"blocked_lessons={','.join(blocked_lessons[:8]) or '-'}, review_lessons={','.join(review_lessons[:8]) or '-'}"
        ),
        action,
        hint,
    )


def _add_experiment_signals(
    buckets: dict[str, dict[str, Any]],
    run: RunSummary,
    validation: dict[str, Any],
    failure: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    runbook: dict[str, Any],
    benchmark: dict[str, Any],
    adapter: dict[str, Any],
    benchmark_schema: dict[str, Any],
) -> None:
    publishable_negative_or_neutral = run.benchmark_publishable_negative_or_neutral and not run.failed_runs
    bounded_negative_or_neutral = (
        publishable_negative_or_neutral
        and run.benchmark_claim_boundary_severity == "negative_or_neutral_no_superiority"
        and run.claim_consistency_status == "pass"
        and not run.claim_consistency_blocking_issues
    )
    if run.result_validation_status == "block":
        _bucket(
            buckets,
            "result_validation",
            "block",
            run,
            f"{run.id}: validation=block, blocking={run.result_validation_blocking_issues}",
            _first_list_value(validation, "blocking_issues", "修复失败、超时、缺共同指标或重复不足后再写分析。"),
            "下一轮先用 preflight 和 local smoke 验证命令，再提高 repeats。",
        )
    elif run.result_validation_status == "warn" and not bounded_negative_or_neutral:
        _bucket(
            buckets,
            "result_validation",
            "warn",
            run,
            f"{run.id}: validation=warn, warnings={run.result_validation_warnings}",
            _first_list_value(validation, "warnings", "把结果验证警告写入局限性，并补重复或共同指标。"),
            "下一轮默认 execution_repeats>=5，并保留完整 stdout/stderr。",
        )
    if run.failure_analysis_status in {"block", "warn"} and not bounded_negative_or_neutral:
        severity = "block" if run.failure_analysis_status == "block" else "warn"
        _bucket(
            buckets,
            "failure_or_negative_results",
            severity,
            run,
            f"{run.id}: failed={run.failed_runs}, negative={run.negative_metrics}, uncertain={run.uncertain_metrics}",
            _first_list_value(failure, "required_actions", "修复失败运行或降级负结果相关论文结论。"),
            "下一轮先锁定预注册规则；失败/负结果不得在论文中选择性隐藏。",
        )
    hypothesis_status = str(hypothesis_outcome.get("status") or "")
    hypothesis_decision = str(hypothesis_outcome.get("outcome") or "")
    if hypothesis_status == "block" or hypothesis_decision in {"blocked_unverified", "untested"}:
        _bucket(
            buckets,
            "hypothesis_outcome",
            "block",
            run,
            f"{run.id}: hypothesis_outcome={hypothesis_decision or '-'}:{hypothesis_status or '-'}",
            "补齐假设验证所需的实验执行、统计比较和计划指标覆盖。",
            "下一轮必须在实验计划中先锁定 hypothesis、primary metrics、baseline 和统计比较，再进入写作。",
        )
    elif (hypothesis_status == "review_required" or hypothesis_decision in {"partially_supported", "refuted_or_negative", "inconclusive", "smoke_only"}) and not bounded_negative_or_neutral:
        _bucket(
            buckets,
            "hypothesis_outcome",
            "warn",
            run,
            f"{run.id}: hypothesis_outcome={hypothesis_decision or '-'}:{hypothesis_status or '-'}",
            "把假设结果写成 partial/negative/inconclusive/smoke-only，不得写成完整支持。",
            "下一轮优先补齐真实 benchmark、未检验指标和 CI 跨 0 指标。",
        )
    mode = _execution_mode(runbook)
    if mode == "simulated":
        _bucket(
            buckets,
            "simulated_evidence",
            "warn",
            run,
            f"{run.id}: execution_mode=simulated",
            "把模拟实验替换为 local 或 benchmark manifest，或明确只作为烟测。",
            "下一轮默认选择 local/benchmark；仅在调试 UI 时使用 simulated。",
        )
    benchmark_actions = _list_values(benchmark, "required_actions", limit=2)
    adapter_blockers = _list_values(adapter, "blocking_issues", limit=2)
    if benchmark_actions or adapter_blockers:
        _bucket(
            buckets,
            "benchmark_gap",
            "warn" if not adapter_blockers else "block",
            run,
            f"{run.id}: benchmark_actions={len(benchmark_actions)}, adapter_blockers={len(adapter_blockers)}",
            (adapter_blockers or benchmark_actions)[0],
            "下一轮启动前先准备 benchmark manifest、公开数据入口、baseline 和许可说明。",
        )
    schema_status = str(benchmark_schema.get("status") or "")
    schema_blockers = _list_values(benchmark_schema, "blocking_issues", limit=2)
    schema_manual = _list_values(benchmark_schema, "manual_tasks", limit=2)
    if schema_status == "block" or schema_blockers:
        action = (schema_blockers or ["修复 benchmark result schema、artifact trace、baseline/candidate 角色或 manifest provenance 后重跑实验。"])[0]
        hint = "下一轮 benchmark manifest 必须补齐 dataset_url/benchmark_url、license、baseline_version、citation，并确认 metrics_path/expected_artifacts 与 runbook 产物闭环。"
        _bucket(
            buckets,
            "benchmark_result_schema",
            "block",
            run,
            f"{run.id}: benchmark_schema={schema_status or '-'}, blockers={len(schema_blockers)}, manual={len(schema_manual)}",
            action,
            hint,
        )
    elif schema_status == "review_required" or schema_manual:
        _bucket(
            buckets,
            "benchmark_result_schema",
            "warn",
            run,
            f"{run.id}: benchmark_schema={schema_status or '-'}, manual={len(schema_manual)}",
            (schema_manual or ["人工核对 benchmark result schema、metric 映射和 artifact trace。"])[0],
            "下一轮执行前先用 Benchmark preview/readiness 检查 manifest provenance 和 metrics schema。",
        )


def _add_environment_snapshot_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, environment: dict[str, Any]) -> None:
    if not environment:
        return
    status = str(environment.get("status") or "")
    source_tree = environment.get("source_tree") if isinstance(environment.get("source_tree"), dict) else {}
    packages = environment.get("package_versions") if isinstance(environment.get("package_versions"), list) else []
    tools = environment.get("tool_versions") if isinstance(environment.get("tool_versions"), list) else []
    warnings = _list_values(environment, "warnings", limit=4)
    source_file_count = _safe_int(source_tree.get("file_count"))
    missing_tools = [
        str(item.get("command") or "").strip()
        for item in tools
        if isinstance(item, dict) and not item.get("available") and str(item.get("command") or "").strip()
    ]
    warning_text = " ".join(warnings).lower()
    source_missing = source_file_count == 0 or "源码快照" in warning_text or "source tree" in warning_text
    package_missing = not packages or "包版本" in warning_text or "package version" in warning_text
    tool_missing = bool(missing_tools) or "不可定位" in warning_text or "allowed command" in warning_text
    if status not in {"block", "partial"} and not warnings and not source_missing and not package_missing and not tool_missing:
        return
    severity = "block" if status == "block" or source_missing else "warn"
    details = []
    if warnings:
        details.append("warnings=" + " / ".join(warnings[:2]))
    if missing_tools:
        details.append("missing_tools=" + ",".join(missing_tools[:3]))
    _bucket(
        buckets,
        "environment_snapshot",
        severity,
        run,
        (
            f"{run.id}: environment={status or '-'}, source_files={source_file_count}, "
            f"package_versions={len(packages)}, warnings={len(warnings)}"
            + (f", {'; '.join(details)}" if details else "")
        ),
        "补齐 Python/package/tool/source tree 环境快照；重新运行 experiments 或重新生成 runbook。",
        "下一轮实验阶段必须保留 04-environment-snapshot；优先使用 local/benchmark，确保 allowed_commands 可定位，并归档 requirements/lockfile 或 release.environment_url。",
    )


def _add_experiment_manager_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, manager: dict[str, Any]) -> None:
    if not manager:
        return
    status = str(manager.get("status") or run.experiment_manager_status or "")
    decision = str(manager.get("manager_decision") or "")
    policy = str(manager.get("execution_policy") or run.experiment_manager_policy or "")
    selected = str(manager.get("selected_idea_title") or manager.get("selected_branch_id") or "")
    required_actions = _list_values(manager, "required_actions", limit=2)
    warnings = _list_values(manager, "warnings", limit=2)
    constraints = _list_values(manager, "planning_constraints", limit=2)
    if status == "block" or policy == "blocked" or decision == "needs_human_reselection":
        _bucket(
            buckets,
            "experiment_manager",
            "block",
            run,
            f"{run.id}: manager={status or '-'}, decision={decision or '-'}, policy={policy or '-'}, selected={selected or '-'}",
            (required_actions or warnings or ["人工改选分支、修正 idea audit，或重新生成探索图和实验管理策略。"])[0],
            "下一轮批准进入实验前先打开 02-experiment-manager.md；block 未解除不得进入实验计划。",
        )
    if policy == "smoke_first":
        _bucket(
            buckets,
            "experiment_manager_smoke_first",
            "warn",
            run,
            f"{run.id}: manager={status or '-'}, policy=smoke_first, selected={selected or '-'}",
            (constraints or warnings or ["先规划低成本 smoke-first 实验；不要把 smoke 结果写成最终科学结论。"])[0],
            "下一轮若仍是 smoke-first，先补文献证据或降低分支风险，并用 local/benchmark smoke 后再扩大实验。",
        )
    candidates = manager.get("next_expansion_candidates")
    if isinstance(candidates, list) and candidates:
        candidate_ids = [
            str(item.get("branch_id") or item.get("title") or "").strip()
            for item in candidates
            if isinstance(item, dict) and str(item.get("branch_id") or item.get("title") or "").strip()
        ]
        _bucket(
            buckets,
            "experiment_branch_backlog",
            "info",
            run,
            f"{run.id}: next_expansion_candidates={len(candidates)} {', '.join(candidate_ids[:3]) or '-'}",
            "复核未扩展分支；如果当前分支 smoke/负结果，下一轮优先从候选中改选。",
            "下一轮不要从零发散；先读取 02-experiment-manager 的 next_expansion_candidates。",
        )


def _add_review_constraint_signals(buckets: dict[str, dict[str, Any]], run: RunSummary, compliance: dict[str, Any]) -> None:
    if not compliance:
        return
    status = str(compliance.get("status") or "")
    blocked = _safe_int(compliance.get("blocked"))
    review_required = _safe_int(compliance.get("review_required"))
    review_constraints = _safe_int(compliance.get("review_constraints"))
    human_constraints = _safe_int(compliance.get("human_brief_constraints"))
    blockers = _list_values(compliance, "blocking_issues", limit=2)
    manual = _list_values(compliance, "manual_tasks", limit=2)
    category = "human_brief_constraints" if human_constraints else "review_constraints"
    evidence = (
        f"{run.id}: review_constraint_compliance={status or '-'}, blocked={blocked}, "
        f"review_required={review_required}, review_constraints={review_constraints}, human_brief_constraints={human_constraints}"
    )
    hint = (
        "下一轮把硬性人工要求写入 human_constraints/human_resource_limits，背景写入 human_notes；"
        "检查 00-human-brief.md 和 03-review-constraint-compliance.md，修复后从 experiment_plan resume。"
    )
    if status == "block" or blocked or blockers:
        _bucket(
            buckets,
            category,
            "block",
            run,
            evidence,
            (blockers or ["把人工审核约束落实到选中 idea 和实验计划；未通过 03-review-constraint-compliance 前不要执行实验。"])[0],
            hint,
        )
    elif status == "review_required" or review_required or manual:
        _bucket(
            buckets,
            category,
            "warn",
            run,
            evidence,
            (manual or ["人工确认或补写 review/human brief 约束后再进入实验执行。"])[0],
            hint,
        )


def _add_paper_release_signals(
    buckets: dict[str, dict[str, Any]],
    run: RunSummary,
    citation_grounding: dict[str, Any],
    citation_coverage: dict[str, Any],
    results_presentation: dict[str, Any],
    claim_consistency: dict[str, Any],
    release_metadata: dict[str, Any],
) -> None:
    if run.final_readiness_status in {"requires_human_evidence", "requires_revision"}:
        _bucket(
            buckets,
            "paper_gate",
            "block" if run.final_readiness_status == "requires_human_evidence" else "warn",
            run,
            f"{run.id}: final_readiness={run.final_readiness_status}, unsupported={run.unsupported_after}, weak={run.weak_after}",
            "补证据、删除 unsupported claim，或重新走修订和复核。",
            "下一轮写作前先检查 claim-support，不让弱证据进入强结论。",
        )
    grounding_status = str(citation_grounding.get("status") or "")
    grounding_blocked = _safe_int(citation_grounding.get("blocked_citations"))
    grounding_review = _safe_int(citation_grounding.get("review_citations"))
    if grounding_status == "block" or grounding_blocked:
        _bucket(
            buckets,
            "citation_grounding",
            "block",
            run,
            f"{run.id}: citation_grounding={grounding_status or '-'}, blocked={grounding_blocked}, review={grounding_review}",
            "修复正文引用附近无法由对应 context chunk 支撑的 claim。",
            "下一轮写作和修订阶段必须逐条核对 10-citation-grounding.md，弱重叠 citation 不得直接进入投稿稿。",
        )
    elif grounding_status == "review_required" or grounding_review:
        _bucket(
            buckets,
            "citation_grounding",
            "warn",
            run,
            f"{run.id}: citation_grounding={grounding_status or '-'}, review={grounding_review}",
            "人工复核 weak-overlap citation，必要时替换引用或删除过强 claim。",
            "下一轮写作时优先使用 01-context chunks 中与 claim 词面和语义都匹配的 citation key。",
        )
    coverage_status = str(citation_coverage.get("status") or "")
    coverage_blockers = len(citation_coverage.get("blocking_issues", [])) if isinstance(citation_coverage.get("blocking_issues"), list) else 0
    coverage_manual = len(citation_coverage.get("manual_tasks", [])) if isinstance(citation_coverage.get("manual_tasks"), list) else 0
    coverage_score = float(citation_coverage.get("coverage_score") or 0.0)
    if coverage_status == "block" or coverage_blockers:
        _bucket(
            buckets,
            "citation_coverage",
            "block",
            run,
            f"{run.id}: citation_coverage={coverage_status or '-'}, blocking={coverage_blockers}, manual={coverage_manual}, score={coverage_score:.2f}",
            "补齐 context 核心文献到正文的覆盖，修复未知 citation key 或 citation 过度集中问题。",
            "下一轮写作时把高相关、近年、baseline/benchmark context 文献显式写入相关工作、方法、结果边界或局限性。",
        )
    elif coverage_status == "review_required" or coverage_manual:
        _bucket(
            buckets,
            "citation_coverage",
            "warn",
            run,
            f"{run.id}: citation_coverage={coverage_status or '-'}, manual={coverage_manual}, score={coverage_score:.2f}",
            "人工复核未进入正文的高相关/近年 context 文献和 citation 过度集中问题。",
            "下一轮修订稿至少覆盖核心 context 文献，并避免全文 citation marker 集中在单一 key。",
        )
    presentation_status = str(results_presentation.get("status") or "")
    presentation_blockers = len(results_presentation.get("blocking_issues", [])) if isinstance(results_presentation.get("blocking_issues"), list) else 0
    presentation_manual = len(results_presentation.get("manual_tasks", [])) if isinstance(results_presentation.get("manual_tasks"), list) else 0
    if presentation_status == "block" or presentation_blockers:
        _bucket(
            buckets,
            "results_presentation",
            "block",
            run,
            f"{run.id}: results_presentation={presentation_status or '-'}, blocking={presentation_blockers}, manual={presentation_manual}",
            "修复结果章节、指标覆盖或无统计支撑的比较性主张。",
            "下一轮写作时先把 04-statistics、04-statistics-figure 和 05-analysis 的指标/CI 写入结果章节。",
        )
    elif presentation_status == "review_required" or presentation_manual:
        _bucket(
            buckets,
            "results_presentation",
            "warn",
            run,
            f"{run.id}: results_presentation={presentation_status or '-'}, manual={presentation_manual}",
            "人工复核结果章节、图表引用、统计指标覆盖和 CI/不确定性表述。",
            "下一轮修订稿必须显式引用结果图/表，并说明 CI 跨 0 指标的结论边界。",
        )
    consistency_status = str(claim_consistency.get("status") or "")
    consistency_blockers = len(claim_consistency.get("blocking_issues", [])) if isinstance(claim_consistency.get("blocking_issues"), list) else 0
    consistency_manual = len(claim_consistency.get("manual_tasks", [])) if isinstance(claim_consistency.get("manual_tasks"), list) else 0
    if consistency_status == "block" or consistency_blockers:
        _bucket(
            buckets,
            "claim_consistency",
            "block",
            run,
            f"{run.id}: claim_consistency={consistency_status or '-'}, blocking={consistency_blockers}, manual={consistency_manual}",
            "删除或降级与 hypothesis outcome 不一致的过强结论。",
            "下一轮写作必须先读取 04-hypothesis-outcome.md，只能按 supported/partial/negative/inconclusive/smoke-only 的证据等级写结论。",
        )
    elif consistency_status == "review_required" or consistency_manual:
        _bucket(
            buckets,
            "claim_consistency",
            "warn",
            run,
            f"{run.id}: claim_consistency={consistency_status or '-'}, manual={consistency_manual}",
            "人工复核 claim 强度、负结果和结果边界是否匹配 hypothesis outcome。",
            "下一轮修订稿结论必须点名写出假设结果等级，避免把部分支持或 smoke-only 概括成正式支持。",
        )
    if run.availability_status in {"blocked", "needs_human_release_metadata"}:
        release_config = _release_metadata_recommended_config(release_metadata)
        _bucket(
            buckets,
            "release_metadata",
            "block" if run.availability_status == "blocked" else "warn",
            run,
            f"{run.id}: availability={run.availability_status}, tasks={run.availability_manual_tasks + run.availability_blocking_issues}",
            "补齐代码仓库、许可证、版本、归档 DOI、数据访问说明和环境归档。",
            "新 run 启动时就填写 release metadata，避免最后打包前集中补。",
            release_config,
        )
    if run.submission_status in {"blocked", "needs_human_format_check"} or run.package_status in {"blocked", "needs_human_submission_review"}:
        _bucket(
            buckets,
            "submission_packaging",
            "block" if run.submission_status == "blocked" or run.package_status == "blocked" else "warn",
            run,
            f"{run.id}: submission={run.submission_status or '-'}, package={run.package_status or '-'}",
            "按目标 venue 官方模板、CHECKLIST 和 ZIP 文件清单做人工核验。",
            "下一轮在表单中提前选择 target_venue，并准备目标模板要求。",
        )


def _add_gate_notes(buckets: dict[str, dict[str, Any]], run: RunSummary, approval: dict[str, Any]) -> None:
    notes = str(approval.get("notes") or "").strip() if isinstance(approval, dict) else ""
    if notes:
        _bucket(
            buckets,
            "human_gate_feedback",
            "info",
            run,
            f"{run.id}: {notes[:160]}",
            "把人工审核意见带入下一轮检索、idea 和实验约束。",
            "下一轮启动时把关键审核意见写入 review_notes 或 seed_papers。",
        )


def _bucket(
    buckets: dict[str, dict[str, Any]],
    category: str,
    severity: str,
    run: RunSummary,
    evidence: str,
    action: str,
    hint: str,
    recommended_config: dict[str, Any] | None = None,
) -> None:
    payload = buckets.setdefault(
        category,
        {
            "severity": severity,
            "run_ids": [],
            "evidence": [],
            "actions": [],
            "hints": [],
            "recommended_configs": [],
        },
    )
    if _severity_rank(severity) > _severity_rank(str(payload["severity"])):
        payload["severity"] = severity
    if run.id not in payload["run_ids"]:
        payload["run_ids"].append(run.id)
    _append_unique(payload["evidence"], evidence, limit=8)
    _append_unique(payload["actions"], action, limit=6)
    _append_unique(payload["hints"], hint, limit=6)
    if recommended_config:
        payload["recommended_configs"].append(recommended_config)


def _to_signal(category: str, payload: dict[str, Any]) -> RunMemorySignal:
    return RunMemorySignal(
        category=category,
        severity=str(payload.get("severity") or "info"),
        count=len(payload.get("run_ids", [])) if isinstance(payload.get("run_ids"), list) else 0,
        run_ids=[str(item) for item in payload.get("run_ids", [])[:8]] if isinstance(payload.get("run_ids"), list) else [],
        evidence=[str(item) for item in payload.get("evidence", [])[:8]] if isinstance(payload.get("evidence"), list) else [],
        recommended_action=str((payload.get("actions") or [""])[0]) if isinstance(payload.get("actions"), list) else "",
        next_run_hint=str((payload.get("hints") or [""])[0]) if isinstance(payload.get("hints"), list) else "",
        recommended_config=_merge_recommended_configs(payload.get("recommended_configs", [])),
    )


def _status(signals: list[RunMemorySignal], runs: list[RunSummary]) -> str:
    if not runs:
        return "empty"
    if any(signal.severity == "block" for signal in signals):
        return "needs_process_repair"
    if any(signal.severity == "warn" for signal in signals):
        return "has_carry_forward_work"
    return "stable"


def _recommended_defaults(signals: list[RunMemorySignal]) -> list[str]:
    categories = {signal.category for signal in signals}
    defaults = ["启动前运行 preflight，确认 LLM 连接和文献源可用。"]
    if "llm_configuration" in categories:
        defaults.append("固定可用的 llm_model/base_url/api_key 组合；模型未配置时允许失败，不启用离线 LLM 兜底。")
    if "llm_trace_audit" in categories:
        defaults.append("关键阶段必须保留成功 LLM trace：run-llm-ledger、13-llm-trace-audit 和 AI disclosure 要一起归档。")
    if "run_economics" in categories:
        defaults.append("正式 run 必须归档 13-run-economics-audit，并配置 LLM 调用/prompt 预算和 input/output token 单价以追踪成本、耗时和预算压力。")
    if "agent_observability" in categories:
        defaults.append("每个 run 必须保留 manifest events/artifacts、LLM ledger、human gate、runbook、diagnostics/recovery 和 repair queue 轨迹。")
    if "open_source_compliance" in categories:
        defaults.append("下一轮必须关闭 13-open-source-compliance：把外部项目约束落实为文献、人工 gate、实验证据、可观测性和投稿披露产物。")
    if "agent_stage_contract" in categories:
        defaults.append("每轮必须把 13-agent-stage-contract 的阶段契约缺口转成启动前配置：文献 seed、人工约束、真实执行/benchmark、release 元数据和 repair-resume 任务。")
    if "research_scorecard" in categories:
        defaults.append("下一轮必须先读取 13-research-scorecard，把最低分维度转成启动配置、人工待办和 targeted iteration，不直接重复低分流程。")
    if "run_integrity_audit" in categories:
        defaults.append("正式 run 必须通过 14-run-integrity-audit：保留完整 artifact/manifest/gate/ledger/package 轨迹，并避免 run-config 持久化 API key。")
    if "final_handoff" in categories:
        defaults.append("正式 run 必须以 14-final-handoff 收尾；blocked 不能标记为可提交，ready_for_human_handoff 必须完成 ZIP、scorecard、完整性审计和投稿 checklist 人工核验。")
    if "repair_resolution_audit" in categories:
        defaults.append("repair-resume 后必须检查 12-repair-resolution-audit；原 block/high/medium 修复项未闭环前不要把 run 当成已修复完成。")
    if "literature_search_feedback" in categories:
        defaults.append("下一轮必须承接 01-literature-search-feedback：应用推荐检索式、source 修复、seed paper 目标和 next_run_config 后再批准进入 idea/实验。")
    if "literature_rescue_execution" in categories:
        defaults.append("下一轮必须检查 01-literature-rescue-execution：未闭环 query 要替换为更具体的 facet-aware 检索式，并补 DOI/URL seed。")
    if "literature_source_health" in categories:
        defaults.append("下一轮必须检查 01-literature-source-health：修复限流/失败源，配置 Semantic Scholar key 或联系邮箱，并重跑文献源健康检查后再批准。")
    if categories & {"literature_repair", "thin_evidence_pool"}:
        defaults.append("文献阶段默认 online/auto，max_papers 至少 12，并提前填入人工 seed_papers。")
    if "result_validation" in categories or "failure_or_negative_results" in categories:
        defaults.append("实验阶段默认 repeats>=5；失败、负结果和 CI 跨 0 必须进入分析边界。")
    if "experiment_manager" in categories:
        defaults.append("实验前必须处理 02-experiment-manager 阻断：人工改选分支、修复 idea audit，或重新生成探索图。")
    if "experiment_manager_smoke_first" in categories:
        defaults.append("高风险或低证据分支默认 smoke-first；正式结论必须等 local/benchmark 证据和保守 claim 边界齐备。")
    if "experiment_branch_backlog" in categories:
        defaults.append("下一轮优先复核 02-experiment-manager 的 next_expansion_candidates，不从空白 idea 重新发散。")
    if categories & {"review_constraints", "human_brief_constraints"}:
        defaults.append("启动时把硬性人工约束写入 human_constraints/human_resource_limits，并在 03-review-constraint-compliance 通过前不要进入实验执行。")
    if categories & {"simulated_evidence", "benchmark_gap"}:
        defaults.append("正式 run 默认 local 或 benchmark manifest；simulated 只用于烟测。")
    if "benchmark_result_schema" in categories:
        defaults.append("benchmark manifest 必须声明来源 URL、license、baseline_version、citation，并让 metrics_path/expected_artifacts 与 runbook 产物闭环。")
    if "environment_snapshot" in categories:
        defaults.append("实验阶段必须保留 04-environment-snapshot；白名单命令可定位，源码哈希和包版本要完整。")
    if "release_metadata" in categories:
        defaults.append("启动时同步填写代码仓库、许可证、版本、数据访问和环境归档字段。")
    if "human_gate_feedback" in categories:
        defaults.append("把上一轮人工 gate 意见写入 review_notes，并在批准前确认 01-review-gate。")
    return _dedupe(defaults)


def _recommended_config(signals: list[RunMemorySignal]) -> dict[str, Any]:
    return _merge_recommended_configs(signal.recommended_config for signal in signals)


def _literature_recommended_config(
    *,
    provider: str = "online",
    sources: list[str] | None = None,
    max_papers: int = 12,
    max_search_queries: int = 6,
    seed_papers_min: int = 3,
    extra_search_queries: list[str] | None = None,
    semantic_scholar_api_key_required: bool = False,
    contact_email_required: bool = False,
) -> dict[str, Any]:
    source_values = _dedupe([source.strip().lower() for source in (sources or ["openalex", "arxiv", "crossref"]) if source.strip()])
    if semantic_scholar_api_key_required:
        source_values = [source for source in source_values if source != "semantic_scholar"]
    return {
        "literature_provider": provider if provider in {"online", "auto"} else "online",
        "sources": source_values,
        "max_papers": max(12, max_papers),
        "max_search_queries": max(6, max_search_queries),
        "seed_papers_min": max(3, seed_papers_min),
        "manual_seed_required": True,
        "extra_search_queries": _dedupe([" ".join(query.split()) for query in (extra_search_queries or []) if str(query).strip()]),
        "semantic_scholar_api_key_required": bool(semantic_scholar_api_key_required),
        "contact_email_required": bool(contact_email_required),
    }


def _release_metadata_recommended_config(report: dict[str, Any]) -> dict[str, Any]:
    recommended = report.get("recommended_config") if isinstance(report.get("recommended_config"), dict) else {}
    if recommended:
        required_fields = _strings(recommended.get("required_fields"))
        recommended_fields = _strings(recommended.get("recommended_fields"))
        cli_args = _strings(recommended.get("cli_args"))
    else:
        required_fields, recommended_fields, cli_args = _release_fields_from_checks(report.get("checks"))
    result: dict[str, Any] = {}
    if required_fields:
        result["release_required_fields"] = required_fields
    if recommended_fields:
        result["release_recommended_fields"] = recommended_fields
    if cli_args:
        result["release_cli_args"] = cli_args
    return result


def _release_fields_from_checks(checks: Any) -> tuple[list[str], list[str], list[str]]:
    field_by_item = {
        "代码仓库 URL": "release_code_repository_url",
        "代码归档 DOI": "release_code_archive_doi",
        "许可证": "release_code_license",
        "代码版本或 commit": "release_code_version",
        "数据访问说明": "release_data_access_statement",
        "数据归档 DOI": "release_data_archive_doi",
        "环境归档": "release_environment_url",
        "发布备注": "release_notes",
    }
    required: list[str] = []
    recommended: list[str] = []
    cli_args: list[str] = []
    for check in _list_values_raw(checks):
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "")
        if status == "pass":
            continue
        field = field_by_item.get(str(check.get("item") or ""))
        if not field:
            continue
        if status in {"block", "manual_required"}:
            _append_unique(required, field, limit=16)
        else:
            _append_unique(recommended, field, limit=16)
        _append_unique(cli_args, "--" + field.replace("_", "-"), limit=16)
    return required, recommended, cli_args


def _merge_recommended_configs(configs: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    sources: list[str] = []
    extra_queries: list[str] = []
    release_required_fields: list[str] = []
    release_recommended_fields: list[str] = []
    release_cli_args: list[str] = []
    semantic_key_required = False
    contact_email_required = False
    manual_seed_required = False
    provider_rank = {"": 0, "offline": 0, "auto": 1, "online": 2}
    provider = ""
    for config in configs:
        if not isinstance(config, dict):
            continue
        candidate_provider = str(config.get("literature_provider") or "").strip()
        if provider_rank.get(candidate_provider, 0) > provider_rank.get(provider, 0):
            provider = candidate_provider
        max_papers = _safe_int(config.get("max_papers"))
        if max_papers:
            merged["max_papers"] = max(_safe_int(merged.get("max_papers")), max_papers)
        max_search_queries = _safe_int(config.get("max_search_queries"))
        if max_search_queries:
            merged["max_search_queries"] = max(_safe_int(merged.get("max_search_queries")), max_search_queries)
        seed_papers_min = _safe_int(config.get("seed_papers_min"))
        if seed_papers_min:
            merged["seed_papers_min"] = max(_safe_int(merged.get("seed_papers_min")), seed_papers_min)
        for source in _list_values_raw(config.get("sources")):
            source_value = str(source).strip().lower()
            if source_value:
                _append_unique(sources, source_value, limit=8)
        for query in _list_values_raw(config.get("extra_search_queries")):
            query_value = " ".join(str(query).split())
            if query_value:
                _append_unique(extra_queries, query_value, limit=12)
        for field in _strings(config.get("release_required_fields")):
            _append_unique(release_required_fields, field, limit=16)
        for field in _strings(config.get("release_recommended_fields")):
            _append_unique(release_recommended_fields, field, limit=16)
        for cli_arg in _strings(config.get("release_cli_args")):
            _append_unique(release_cli_args, cli_arg, limit=16)
        semantic_key_required = semantic_key_required or config.get("semantic_scholar_api_key_required") is True
        contact_email_required = contact_email_required or config.get("contact_email_required") is True
        manual_seed_required = manual_seed_required or config.get("manual_seed_required") is True
    if provider:
        merged["literature_provider"] = provider
    if semantic_key_required:
        sources = [source for source in sources if source != "semantic_scholar"]
    if sources:
        merged["sources"] = sources
    if extra_queries:
        merged["extra_search_queries"] = extra_queries
    if release_required_fields:
        merged["release_required_fields"] = release_required_fields
    if release_recommended_fields:
        merged["release_recommended_fields"] = release_recommended_fields
    if release_cli_args:
        merged["release_cli_args"] = release_cli_args
    if manual_seed_required:
        merged["manual_seed_required"] = True
    if semantic_key_required:
        merged["semantic_scholar_api_key_required"] = True
    if contact_email_required:
        merged["contact_email_required"] = True
    return merged


def _next_run_checklist(signals: list[RunMemorySignal]) -> list[str]:
    checklist = [
        "确认模型、Base URL、API Key 可通过预检。",
        "检查 01-review-gate.md 后人工批准，禁止未批准直接进入 idea/实验。",
        "保留 run-manifest、LLM ledger 和实验 stdout/stderr，便于失败复盘。",
    ]
    for signal in signals[:8]:
        if signal.next_run_hint:
            checklist.append(signal.next_run_hint)
    return _dedupe(checklist)


def _carry_forward_notes(signals: list[RunMemorySignal], runs: list[RunSummary]) -> list[str]:
    notes: list[str] = []
    if runs:
        best = runs[0]
        notes.append(f"当前排序最高 run：{best.id}，readiness={best.readiness_score:.2f}，阶段={best.stage}。")
    for signal in signals[:5]:
        notes.append(f"{signal.category}: 最近 {signal.count} 个 run 触发，优先级由 {signal.severity} 决定。")
    return notes


def _top_priority_task(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    if not tasks:
        return {}
    return sorted(tasks, key=lambda item: _safe_int(item.get("priority")), reverse=True)[0]


def _first_query(recommended_queries: list[dict[str, Any]], agent_query_tasks: list[dict[str, Any]]) -> str:
    for item in [*agent_query_tasks, *recommended_queries]:
        query = str(item.get("query") or "").strip()
        if query:
            return " ".join(query.split())
    return ""


def _problematic_literature_sources(sources: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in sources:
        source = str(item.get("source") or "").strip().lower()
        status = str(item.get("status") or "").strip().lower()
        errors = _safe_int(item.get("errors"))
        if source and (status in {"failed", "rate_limited"} or item.get("rate_limited") is True or errors > 0):
            _append_unique(names, source, limit=8)
    return names


def _list_values(data: dict[str, Any], key: str, limit: int) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:limit]


def _list_values_raw(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in _list_values_raw(value) if str(item).strip()]


def _first_list_value(data: dict[str, Any], key: str, fallback: str) -> str:
    values = _list_values(data, key, limit=1)
    return values[0] if values else fallback


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _tri_state(value: bool | None) -> str:
    if value is True:
        return "Y"
    if value is False:
        return "N"
    return "?"


def _execution_mode(runbook: dict[str, Any]) -> str:
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    return str(execution.get("mode") or "")


def _append_unique(values: list[Any], value: str, limit: int) -> None:
    if value and value not in values and len(values) < limit:
        values.append(value)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _severity_rank(severity: str) -> int:
    return {"info": 0, "warn": 1, "block": 2}.get(severity, 0)


