from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell
from .llm_ledger_recovery import summarize_llm_failure_recovery


AGENT_STAGE_CONTRACT_JSON = "13-agent-stage-contract.json"
AGENT_STAGE_CONTRACT_MD = "13-agent-stage-contract.md"


def write_agent_stage_contract_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_agent_stage_contract_report(topic, run_dir)
    write_json(run_dir / AGENT_STAGE_CONTRACT_JSON, report)
    write_text(run_dir / AGENT_STAGE_CONTRACT_MD, render_agent_stage_contract_markdown(report))
    return report


def build_agent_stage_contract_report(topic: str, run_dir: Path) -> dict[str, Any]:
    data = {
        "plan": _read_json(run_dir / "00-research-plan.json"),
        "open_source": _read_json(run_dir / "00-open-source-lessons.json"),
        "ledger": _read_json(run_dir / "run-llm-ledger.json"),
        "manifest": _read_json(run_dir / "run-manifest.json"),
        "rerank": _read_json(run_dir / "01-literature-rerank.json"),
        "query_execution": _read_json(run_dir / "01-query-execution-audit.json"),
        "quality": _read_json(run_dir / "01-literature-quality.json"),
        "metadata": _read_json(run_dir / "01-literature-metadata-audit.json"),
        "coverage": _read_json(run_dir / "01-literature-coverage.json"),
        "evidence_mix": _read_json(run_dir / "01-literature-evidence-mix.json"),
        "rescue": _read_json(run_dir / "01-literature-rescue-plan.json"),
        "rescue_execution": _read_json(run_dir / "01-literature-rescue-execution.json"),
        "seed_intake": _read_json(run_dir / "01-seed-paper-intake.json"),
        "literature_gate": _read_json(run_dir / "01-literature-gate-decision.json"),
        "context": _read_json(run_dir / "01-context.json"),
        "citation": _read_json(run_dir / "01-citation-audit.json"),
        "approval": _read_json(run_dir / "approval.json"),
        "human_gate_audit": _read_json(run_dir / "13-human-gate-audit.json"),
        "constraints": _read_json(run_dir / "01-review-constraints.json"),
        "ideas": _read_json(run_dir / "02-ideas.json"),
        "novelty": _read_json(run_dir / "02-novelty-audit.json"),
        "idea_audit": _read_json(run_dir / "02-idea-audit.json"),
        "exploration": _read_json(run_dir / "02-exploration-map.json"),
        "experiment_manager": _read_json(run_dir / "02-experiment-manager.json"),
        "experiment": _read_json(run_dir / "03-experiment-plan.json"),
        "constraint_compliance": _read_json(run_dir / "03-review-constraint-compliance.json"),
        "experiment_audit": _read_json(run_dir / "03-experiment-audit.json"),
        "idea_experiment_contract": _read_json(run_dir / "03-idea-experiment-contract.json"),
        "execution_safety": _read_json(run_dir / "03-execution-safety-audit.json"),
        "ablation": _read_json(run_dir / "03-ablation-plan.json"),
        "preregistration": _read_json(run_dir / "03-preregistration.json"),
        "benchmark": _read_json(run_dir / "03-benchmark-plan.json"),
        "benchmark_readiness": _read_json(run_dir / "03-benchmark-readiness.json"),
        "execution_approval": _read_json(run_dir / "03-execution-approval.json"),
        "runbook": _read_json(run_dir / "04-experiment-runbook.json"),
        "statistics": _read_json(run_dir / "04-statistics.json"),
        "validation": _read_json(run_dir / "04-result-validation.json"),
        "failure": _read_json(run_dir / "04-failure-analysis.json"),
        "benchmark_schema": _read_json(run_dir / "04-benchmark-result-schema-audit.json"),
        "benchmark_evidence": _read_json(run_dir / "04-benchmark-evidence-audit.json"),
        "experiment_decision": _read_json(run_dir / "04-experiment-decision.json"),
        "hypothesis": _read_json(run_dir / "04-hypothesis-outcome.json"),
        "claim_preflight": _read_json(run_dir / "04-claim-boundary-preflight.json"),
        "review": _read_json(run_dir / "07-paper-review.json"),
        "review_calibration": _read_json(run_dir / "07-paper-review-calibration.json"),
        "revision_plan": _read_json(run_dir / "08-revision-plan.json"),
        "revision_report": _read_json(run_dir / "09-revision-report.json"),
        "revision_response": _read_json(run_dir / "09-revision-response-audit.json"),
        "revised_review": _read_json(run_dir / "10-revised-paper-review.json"),
        "traceability": _read_json(run_dir / "10-claim-traceability.json"),
        "citation_grounding": _read_json(run_dir / "10-citation-grounding.json"),
        "citation_coverage": _read_json(run_dir / "10-citation-coverage.json"),
        "results_presentation": _read_json(run_dir / "10-results-presentation.json"),
        "claim_consistency": _read_json(run_dir / "10-claim-consistency.json"),
        "availability": _read_json(run_dir / "10-code-data-availability.json"),
        "submission": _read_json(run_dir / "10-submission-check.json"),
        "final": _read_json(run_dir / "10-final-readiness.json"),
        "package": _read_json(run_dir / "11-submission-package.json"),
        "iteration": _read_json(run_dir / "12-next-iteration-plan.json"),
        "repair_queue": _read_json(run_dir / "12-repair-queue.json"),
        "repair_resolution": _read_json(run_dir / "12-repair-resolution-audit.json"),
        "llm_runtime_contract": _read_json(run_dir / "13-llm-runtime-contract.json"),
        "run_economics": _read_json(run_dir / "13-run-economics-audit.json"),
        "observability": _read_json(run_dir / "13-agent-observability-audit.json"),
        "open_source_compliance": _read_json(run_dir / "13-open-source-compliance.json"),
    }
    checks = [
        _planning_contract(data),
        _literature_contract(data),
        _human_gate_contract(data),
        _idea_contract(data),
        _experiment_contract(data),
        _execution_contract(data),
        _paper_review_contract(data),
        _release_contract(data),
        _open_source_contract(data),
        _observability_contract(data),
    ]
    blocking = [action for check in checks if check["status"] in {"block", "missing"} for action in check["required_actions"]]
    manual = [action for check in checks if check["status"] == "warn" for action in check["required_actions"]]
    passed = sum(1 for check in checks if check["status"] == "pass")
    score = round(passed / max(1, len(checks)), 3)
    status = "block" if blocking else "needs_human_review" if manual else "pass"
    return {
        "topic": topic,
        "status": status,
        "score": score,
        "checks": checks,
        "blocking_issues": blocking,
        "manual_tasks": manual,
        "open_source_patterns": _open_source_patterns(data["open_source"]),
        "recommended_actions": _recommended_actions(status, blocking, manual),
    }


def render_agent_stage_contract_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Agent Stage Contract Audit：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 契约得分：{float(report.get('score') or 0.0):.3f}",
        f"- 阻断问题：{len(report.get('blocking_issues', []) if isinstance(report.get('blocking_issues'), list) else [])}",
        f"- 人工待办：{len(report.get('manual_tasks', []) if isinstance(report.get('manual_tasks'), list) else [])}",
        "",
        "## 开源项目模式",
    ]
    patterns = report.get("open_source_patterns", []) if isinstance(report.get("open_source_patterns"), list) else []
    lines.extend(f"- {item}" for item in patterns) if patterns else lines.append("- 未读取到 00-open-source-lessons。")
    lines.extend(
        [
            "",
            "## 阶段契约",
            "| 阶段 | 状态 | 来源项目 | 证据 | 要求 | 动作 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for check in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if not isinstance(check, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(check.get("stage") or "")),
                    _cell(str(check.get("status") or "")),
                    _cell(", ".join(str(item) for item in check.get("source_projects", []) if str(item).strip())),
                    _cell("；".join(str(item) for item in check.get("evidence", []) if str(item).strip()) or "-"),
                    _cell(str(check.get("expectation") or "")),
                    _cell("；".join(str(item) for item in check.get("required_actions", []) if str(item).strip()) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    blocking = report.get("blocking_issues", []) if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    manual = report.get("manual_tasks", []) if isinstance(report.get("manual_tasks"), list) else []
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    actions = report.get("recommended_actions", []) if isinstance(report.get("recommended_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    return "\n".join(lines)


def _planning_contract(data: dict[str, Any]) -> dict[str, Any]:
    plan = _dict(data["plan"])
    queries = _list(plan.get("search_queries"))
    baselines = _list(plan.get("baselines"))
    benchmarks = _list(plan.get("benchmarks"))
    metrics = _list(plan.get("metrics"))
    missing = []
    if not queries:
        missing.append("search_queries")
    if not baselines:
        missing.append("baselines")
    if not benchmarks:
        missing.append("benchmarks")
    if not metrics:
        missing.append("metrics")
    return _check(
        "planning",
        "研究计划必须给后续 agent 明确检索式、baseline、benchmark 和 metric。",
        ["AI-Scientist", "Agent Laboratory"],
        "pass" if not missing else "missing",
        [f"queries={len(queries)}", f"baselines={len(baselines)}", f"benchmarks={len(benchmarks)}", f"metrics={len(metrics)}"],
        [f"补齐 00-research-plan.json 中缺失字段：{', '.join(missing)}。"] if missing else [],
    )


def _literature_contract(data: dict[str, Any]) -> dict[str, Any]:
    quality = _dict(data["quality"])
    metadata = _dict(data["metadata"])
    rerank = _dict(data["rerank"])
    query_execution = _dict(data["query_execution"])
    coverage = _dict(data["coverage"])
    evidence_mix = _dict(data["evidence_mix"])
    rescue = _dict(data["rescue"])
    rescue_execution = _dict(data["rescue_execution"])
    seed_intake = _dict(data["seed_intake"])
    literature_gate = _dict(data["literature_gate"])
    paper_grade_literature = _dict(literature_gate.get("paper_grade_literature"))
    context = _dict(data["context"])
    citation = _dict(data["citation"])
    selected = _int(quality.get("selected_papers"))
    citations = len(_list(context.get("citations")))
    blocked_citations = _int(citation.get("blocked_citations"))
    query_status = str(query_execution.get("status") or "")
    query_actions = _list(query_execution.get("recommended_actions"))
    rescue_execution_status = str(rescue_execution.get("status") or "")
    rescue_execution_trigger = str(rescue_execution.get("trigger_status") or "")
    rescue_execution_unresolved = _int(rescue_execution.get("unresolved_query_outcomes"))
    rescue_execution_closed = _int(rescue_execution.get("closed_query_outcomes"))
    rescue_execution_new = _int(rescue_execution.get("new_unique_papers"))
    rescue_execution_actions = _list(rescue_execution.get("required_actions"))
    rescue_execution_repair_tasks = _list(rescue_execution.get("repair_task_ids"))
    seed_status = str(seed_intake.get("status") or "")
    seed_role_status = str(seed_intake.get("role_coverage_status") or "")
    seed_actions = _list(seed_intake.get("required_actions"))
    seed_missing_roles = _list(seed_intake.get("missing_curated_seed_roles"))
    literature_gate_status = str(literature_gate.get("status") or "")
    paper_grade_status = str(paper_grade_literature.get("status") or "")
    paper_grade_issues = _list(paper_grade_literature.get("issues"))
    actions: list[str] = []
    status = "pass"
    if selected < 3 or citations < 3:
        status = "block"
        actions.append("补充高相关文献或 seed papers，确保至少 3 篇文献进入 context。")
    if str(metadata.get("status") or "") in {"block", "literature_repair_required"} or _int(metadata.get("blocked")):
        status = "block"
        actions.append("修复 01-literature-metadata-audit.md 中的低可信题录。")
    if blocked_citations:
        status = "block"
        actions.append("修复 01-citation-audit.md 中 blocked citation。")
    if str(coverage.get("status") or "") in {"needs_literature", "block"}:
        status = "block"
        actions.append("按 01-literature-coverage.md 补齐 baseline/benchmark/metric 覆盖。")
    if query_status == "needs_source_repair":
        status = "block"
        actions.extend(str(item) for item in query_actions[:3] or ["修复 01-query-execution-audit.md 中的 source/query 执行缺口。"])
    elif query_status == "needs_query_repair" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in query_actions[:2])
    elif query_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in query_actions[:2])
    if str(evidence_mix.get("status") or "") == "block":
        status = "block"
        actions.append("按 01-literature-evidence-mix.md 补齐综述/高引用、benchmark/dataset、baseline/method 和近期文献 anchor。")
    elif status == "pass" and str(evidence_mix.get("status") or "") in {"needs_evidence_upgrade", "review_required"}:
        status = "warn"
        actions.extend(str(item) for item in _list(evidence_mix.get("required_actions"))[:2])
    if status == "pass" and str(rerank.get("status") or "") == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(rerank.get("recommended_actions"))[:2])
    if status == "pass" and str(rescue.get("status") or "") in {"needs_rescue_search", "needs_manual_seed", "needs_source_repair"}:
        status = "warn"
        actions.extend(str(item) for item in _list(rescue.get("required_actions"))[:2])
    if rescue_execution_status == "no_new_papers" or rescue_execution_unresolved:
        status = "block"
        actions.extend(
            str(item)
            for item in (
                rescue_execution_actions[:3]
                or ["修复 01-literature-rescue-execution.md 中未闭环 query，替换检索式或补 DOI/URL seed 后重跑文献 gate。"]
            )
        )
    elif rescue_execution_status in {"not_applicable", "skipped"} and (
        rescue_execution_trigger in {"block", "needs_rescue_search", "needs_manual_seed"} or rescue_execution_repair_tasks or rescue_execution_actions
    ):
        status = "block"
        actions.extend(
            str(item)
            for item in (
                rescue_execution_actions[:3]
                or ["补检索已被触发但未执行；确认 online/auto literature provider、source/API key 和 seed papers 后重跑。"]
            )
        )
    if seed_status == "block":
        status = "block"
        actions.extend(str(item) for item in seed_actions[:3] or ["修复 01-seed-paper-intake.md 中未进入原始池或 curated context 的人工 seed。"])
    elif seed_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in seed_actions[:2] or ["人工复核 01-seed-paper-intake.md 中的 seed 文献问题。"])
    elif seed_role_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(
            str(item)
            for item in (
                seed_actions[:2]
                or [f"补齐 seed paper 角色覆盖，当前缺失：{', '.join(str(item) for item in seed_missing_roles[:4]) or '-'}。"]
            )
        )
    if literature_gate_status == "block":
        status = "block"
        actions.extend(str(item) for item in _list(literature_gate.get("required_actions"))[:3])
    elif paper_grade_status == "review_required" and status == "pass":
        status = "warn"
        actions.extend(str(item) for item in paper_grade_issues[:3])
    if status == "block" and _paper_grade_literature_allows_residual_review(
        selected=selected,
        citations=citations,
        blocked_citations=blocked_citations,
        metadata=metadata,
        coverage=coverage,
        evidence_mix=evidence_mix,
        literature_gate=literature_gate,
        paper_grade_status=paper_grade_status,
        query_status=query_status,
    ):
        status = "warn"
        actions = [
            "paper-grade literature gate 已通过；底层 query/rescue/metadata 残余作为人工复核项，不再阻断当前 run。",
            *actions,
        ]
    return _check(
        "literature_grounding",
        "进入 idea 前必须有可核验、覆盖 baseline/benchmark 的 grounded 文献上下文。",
        ["PaperQA2", "Agent Laboratory"],
        status,
        [
            f"selected_papers={selected}",
            f"context_citations={citations}",
            f"rerank={rerank.get('status') or '-'}",
            f"query_execution={query_status or '-'}:{query_execution.get('selected_query_count', 0)}",
            f"metadata={metadata.get('status') or '-'}",
            f"coverage={coverage.get('status') or '-'}",
            f"evidence_mix={evidence_mix.get('status') or '-'}:{_float(evidence_mix.get('mix_score')):.2f}",
            f"rescue={rescue.get('status') or '-'}",
            f"rescue_execution={rescue_execution_status or '-'}:{rescue_execution_closed}/{rescue_execution_unresolved}:{rescue_execution_new}",
            f"seed_intake={seed_status or '-'}:{seed_role_status or '-'}:{seed_intake.get('curated_seed_papers', 0)}/{seed_intake.get('total_seed_entries', 0)}",
            f"literature_gate={literature_gate_status or '-'}",
            f"paper_grade_literature={paper_grade_status or '-'}:{len(paper_grade_issues)}",
            f"blocked_citations={blocked_citations}",
        ],
        actions,
    )


def _human_gate_contract(data: dict[str, Any]) -> dict[str, Any]:
    approval = _dict(data["approval"])
    human_gate_audit = _dict(data["human_gate_audit"])
    constraints = _dict(data["constraints"])
    approved = bool(approval.get("approved"))
    blocks = set(str(item) for item in _list(approval.get("blocks")))
    gate_status = str(approval.get("gate_status") or "")
    notes = str(approval.get("notes") or "").strip()
    parsed_constraints = _list(constraints.get("constraints"))
    actions: list[str] = []
    status = "pass"
    if not approved:
        status = "block"
        actions.append("人工批准 review gate 后才允许进入 idea/实验。")
    if not {"idea_generation", "experiment_planning", "experiment_execution"}.issubset(blocks):
        status = "block"
        actions.append("approval.json 必须记录 idea、experiment planning 和 execution 阻断范围。")
    if str(human_gate_audit.get("status") or "") == "block":
        status = "block"
        actions.extend(str(item) for item in _list(human_gate_audit.get("blocking_issues"))[:3] or ["修复 13-human-gate-audit.md 中的人工 gate 越权问题。"])
    elif status == "pass" and str(human_gate_audit.get("status") or "") == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(human_gate_audit.get("manual_tasks"))[:2] or ["人工核对 13-human-gate-audit.md。"])
    if gate_status and gate_status != "pass" and not notes:
        status = "block"
        actions.append("非 pass gate 的人工批准必须包含实质审核意见。")
    if status == "pass" and not parsed_constraints:
        status = "warn"
        actions.append("补充审核意见，让 01-review-constraints.json 能约束后续 idea/实验。")
    return _check(
        "human_review_gate",
        "人类 gate 必须先于 idea/实验，并把人工意见固化为后续约束。",
        ["Agent Laboratory"],
        status,
        [f"approved={approved}", f"gate_status={gate_status or '-'}", f"blocks={len(blocks)}", f"constraints={len(parsed_constraints)}", f"human_gate_audit={human_gate_audit.get('status') or '-'}"],
        actions,
    )


def _idea_contract(data: dict[str, Any]) -> dict[str, Any]:
    ideas = _list(data["ideas"])
    novelty = _dict(data["novelty"])
    idea_audit = _dict(data["idea_audit"])
    exploration = _dict(data["exploration"])
    branches = _list(exploration.get("branches"))
    selected_branch = str(exploration.get("selected_branch_id") or "")
    status = "pass"
    actions: list[str] = []
    if len(ideas) < 2:
        status = "block"
        actions.append("至少生成 2 个证据约束 idea，避免单一路径过早收敛。")
    if str(idea_audit.get("status") or "") == "block" or _int(idea_audit.get("blocked")):
        status = "block"
        actions.append("修复 02-idea-audit.md 中 evidence/baseline/metric 阻断项。")
    if not selected_branch:
        status = "block"
        actions.append("生成 02-exploration-map 并选择一个研究分支。")
    if status == "pass" and str(novelty.get("status") or "") in {"review_required", "warn"}:
        status = "warn"
        actions.append("人工复核 02-novelty-audit.md 中重复风险较高的 idea。")
    return _check(
        "idea_exploration",
        "Idea 阶段必须保留多候选探索、文献证据和新颖性/分支选择记录。",
        ["AI-Scientist", "Agent Laboratory"],
        status,
        [f"ideas={len(ideas)}", f"branches={len(branches)}", f"selected_branch={selected_branch or '-'}", f"idea_audit={idea_audit.get('status') or '-'}"],
        actions,
    )


def _experiment_contract(data: dict[str, Any]) -> dict[str, Any]:
    manager = _dict(data["experiment_manager"])
    experiment = _dict(data["experiment"])
    audit = _dict(data["experiment_audit"])
    idea_contract = _dict(data["idea_experiment_contract"])
    safety = _dict(data["execution_safety"])
    compliance = _dict(data["constraint_compliance"])
    ablation = _dict(data["ablation"])
    prereg = _dict(data["preregistration"])
    benchmark = _dict(data["benchmark"])
    readiness = _dict(data["benchmark_readiness"])
    commands = _list(experiment.get("commands"))
    status = "pass"
    actions: list[str] = []
    if not manager:
        status = "block"
        actions.append("生成 02-experiment-manager.json，记录选中分支的实验管理策略和下一轮候选。")
    elif str(manager.get("status") or "") == "block":
        status = "block"
        actions.append("修复 02-experiment-manager.md 中的分支阻断或人工改选。")
    if not experiment or not commands:
        status = "block"
        actions.append("补齐 03-experiment-plan.json 中可执行命令和实验协议。")
    for name, report, action in [
        ("experiment_audit", audit, "修复 03-experiment-audit.md 中的阻断项。"),
        ("idea_experiment_contract", idea_contract, "修复 03-idea-experiment-contract.md 中的 idea 到实验断链。"),
        ("execution_safety", safety, "修复 03-execution-safety-audit.md 中的命令安全问题。"),
        ("review_constraint_compliance", compliance, "落实 01-review-constraints 到实验计划。"),
    ]:
        if str(report.get("status") or "") == "block" or _int(report.get("blocked")):
            status = "block"
            actions.append(action)
    if status == "pass" and not ablation:
        status = "warn"
        actions.append("生成 03-ablation-plan，明确必要消融或说明豁免。")
    if status == "pass" and not prereg:
        status = "warn"
        actions.append("生成 03-preregistration，锁定实验前分析规则。")
    if status == "pass" and not benchmark:
        status = "warn"
        actions.append("生成 03-benchmark-plan，明确真实 benchmark 接入路径。")
    if status == "pass" and str(idea_contract.get("status") or "") == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(idea_contract.get("manual_tasks"))[:3])
    if str(readiness.get("status") or "") == "block":
        status = "block"
        actions.extend(str(item) for item in _list(readiness.get("blocking_issues"))[:3])
    elif status == "pass" and str(readiness.get("status") or "") == "needs_benchmark_upgrade":
        status = "warn"
        actions.extend(str(item) for item in _list(readiness.get("manual_tasks"))[:3])
    return _check(
        "experiment_design",
        "实验计划必须可执行、受人工约束、通过安全审计，并有消融/预注册/benchmark 计划。",
        ["AI-Scientist", "MLAgentBench", "Agent Laboratory"],
        status,
        [
            f"manager={manager.get('status') or '-'}:{manager.get('execution_policy') or '-'}",
            f"commands={len(commands)}",
            f"experiment_audit={audit.get('status') or '-'}",
            f"idea_experiment_contract={idea_contract.get('status') or '-'}",
            f"safety={safety.get('status') or '-'}",
            f"constraint_compliance={compliance.get('status') or '-'}",
            f"ablation={ablation.get('status') or '-'}",
            f"preregistration={prereg.get('status') or '-'}",
            f"benchmark={benchmark.get('status') or '-'}",
            f"benchmark_readiness={readiness.get('status') or '-'}",
        ],
        actions,
    )


def _execution_contract(data: dict[str, Any]) -> dict[str, Any]:
    runbook = _dict(data["runbook"])
    stats = _dict(data["statistics"])
    validation = _dict(data["validation"])
    failure = _dict(data["failure"])
    schema = _dict(data["benchmark_schema"])
    benchmark = _dict(data["benchmark_evidence"])
    decision = _dict(data["experiment_decision"])
    hypothesis = _dict(data["hypothesis"])
    preflight = _dict(data["claim_preflight"])
    results = _list(runbook.get("runs")) or _list(runbook.get("artifacts"))
    adapter_paper_grade_status = str(benchmark.get("adapter_paper_grade_status") or "")
    adapter_paper_grade_issues = _list(benchmark.get("adapter_paper_grade_issues"))
    status = "pass"
    actions: list[str] = []
    if not runbook or not results:
        status = "block"
        actions.append("补齐 04-experiment-runbook，记录执行模式、运行和产物。")
    if not stats:
        status = "block"
        actions.append("生成 04-statistics.md/json，避免无统计证据写论文。")
    for report, action in [
        (validation, "修复 04-result-validation.md 中的结果有效性问题。"),
        (schema, "修复 04-benchmark-result-schema-audit.md 中的 result schema 或 artifact contract 断链。"),
        (failure, "修复 04-failure-analysis.md 中的失败或负结果解释。"),
    ]:
        if str(report.get("status") or "") == "block":
            status = "block"
            actions.append(action)
    if str(decision.get("decision") or "") == "repair_before_writing":
        status = "block"
        actions.append("按 04-experiment-decision.md 修复实验后再写作。")
    if str(hypothesis.get("outcome") or "") in {"untested", "blocked_unverified"}:
        status = "block"
        actions.append("补齐假设检验或降级论文主张。")
    if not preflight:
        status = "missing" if status == "pass" else status
        actions.append("生成 04-claim-boundary-preflight，先锁定写作前 claim 边界。")
    elif str(preflight.get("status") or "") == "block":
        status = "block"
        actions.extend(str(item) for item in _list(preflight.get("blocking_issues"))[:3])
    if status == "pass" and str(benchmark.get("evidence_grade") or "") in {"smoke_only", "local_experiment"}:
        status = "warn"
        if adapter_paper_grade_status and adapter_paper_grade_status != "ready":
            actions.extend(
                str(item)
                for item in (
                    _list(benchmark.get("required_actions"))[:3]
                    or adapter_paper_grade_issues[:3]
                    or ["补齐 paper-grade benchmark manifest、共同指标和 repeats 后重跑。"]
                )
            )
        else:
            actions.append("把 smoke/local 证据升级为真实 benchmark，或在论文中明确降级。")
    if status == "pass" and str(schema.get("status") or "") == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(schema.get("manual_tasks"))[:3] or ["人工核对 benchmark result schema audit。"])
    if status == "pass" and str(preflight.get("status") or "") == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(preflight.get("required_actions"))[:3])
    return _check(
        "execution_evidence",
        "执行阶段必须留下 runbook、统计、结果有效性、失败分析、benchmark 证据和假设结论边界。",
        ["AI-Scientist", "MLAgentBench"],
        status,
        [
            f"runbook_runs_or_artifacts={len(results)}",
            f"statistics={'yes' if stats else 'no'}",
            f"validation={validation.get('status') or '-'}",
            f"benchmark_schema={schema.get('status') or '-'}",
            f"failure={failure.get('status') or '-'}",
            f"benchmark_grade={benchmark.get('evidence_grade') or '-'}",
            f"adapter_paper_grade={adapter_paper_grade_status or '-'}:{len(adapter_paper_grade_issues)}",
            f"decision={decision.get('decision') or '-'}",
            f"hypothesis={hypothesis.get('outcome') or '-'}",
            f"claim_preflight={preflight.get('status') or '-'}:{preflight.get('writing_mode') or '-'}",
        ],
        actions,
    )


def _paper_review_contract(data: dict[str, Any]) -> dict[str, Any]:
    review = _dict(data["review"])
    calibration = _dict(data["review_calibration"])
    revision_plan = _dict(data["revision_plan"])
    revision = _dict(data["revision_report"])
    response = _dict(data["revision_response"])
    revised_review = _dict(data["revised_review"])
    final = _dict(data["final"])
    trace = _dict(data["traceability"])
    grounding = _dict(data["citation_grounding"])
    coverage = _dict(data["citation_coverage"])
    presentation = _dict(data["results_presentation"])
    consistency = _dict(data["claim_consistency"])
    calibration_status = str(calibration.get("status") or "")
    revised_gate_clean = _clean_revised_paper_gate(final, revised_review, trace)
    status = "pass"
    actions: list[str] = []
    for name, report, action in [
        ("review", review, "生成 07-paper-review.md/json。"),
        ("review_calibration", calibration, "生成 07-paper-review-calibration.md/json。"),
        ("revision_plan", revision_plan, "生成 08-revision-plan.md/json。"),
        ("revision_report", revision, "生成 09-revision-report.md/json。"),
        ("revision_response", response, "生成 09-revision-response-audit.md/json。"),
        ("revised_review", revised_review, "生成 10-revised-paper-review.md/json。"),
    ]:
        if not report:
            status = "missing"
            actions.append(action)
    for report, action in [
        (trace, "修复 10-claim-traceability.md 中无证据 claim。"),
        (grounding, "修复 10-citation-grounding.md 中 citation 支撑问题。"),
        (coverage, "修复 10-citation-coverage.md 中文献覆盖、未知 key 或引用过度集中问题。"),
        (presentation, "修复 10-results-presentation.md 中结果呈现问题。"),
        (consistency, "修复 10-claim-consistency.md 中过强结论。"),
    ]:
        if str(report.get("status") or "") == "block":
            status = "block"
            actions.append(action)
    if calibration and calibration_status == "block" and not revised_gate_clean:
        status = "block"
        actions.extend(str(item) for item in _list(calibration.get("blocking_issues"))[:3] or ["修复 07-paper-review-calibration.md 中旧草稿复核校准阻断项。"])
    elif calibration and calibration_status in {"block", "review_required"} and status == "pass":
        status = "warn"
        actions.extend(
            str(item)
            for item in (
                _list(calibration.get("manual_tasks"))[:3]
                or _list(calibration.get("required_actions"))[:3]
                or ["原始草稿 calibration 已被干净修订稿覆盖；人工确认 07-paper-review-calibration.md 不再适用于当前修订稿。"]
            )
        )
    if str(response.get("status") or "") == "block":
        status = "block"
        actions.extend(str(item) for item in _list(response.get("blocking_issues"))[:3] or ["修复 09-revision-response-audit.md 中未闭环的审稿任务回应。"])
    elif status == "pass" and str(response.get("status") or "") == "review_required":
        status = "warn"
        if revised_gate_clean:
            actions.extend(
                str(item)
                for item in (
                    _list(response.get("manual_tasks"))[:3]
                    or ["修订稿最终 gate 已通过；人工确认 09-revision-response-audit.md 中旧 review_required 任务已由当前正文覆盖。"]
                )
            )
        else:
            actions.extend(str(item) for item in _list(response.get("manual_tasks"))[:3] or ["人工关闭 09-revision-response-audit.md 中的待补证或待核对任务。"])
    return _check(
        "paper_review_loop",
        "论文阶段必须完成草稿、审稿式复核、校准、修订和主张证据审计闭环。",
        ["AI-Scientist", "PaperQA2"],
        status,
        [
            f"review={'yes' if review else 'no'}",
            f"calibration={calibration.get('status') or '-'}",
            f"revision_tasks={len(_list(revision_plan.get('tasks')))}",
            f"revision_response={response.get('status') or '-'}:{_float(response.get('response_score')):.2f}",
            f"revised_review={revised_review.get('decision') or revised_review.get('status') or '-'}",
            f"traceability={trace.get('status') or '-'}",
            f"citation_grounding={grounding.get('status') or '-'}",
            f"citation_coverage={coverage.get('status') or '-'}:{_float(coverage.get('coverage_score')):.2f}",
            f"claim_consistency={consistency.get('status') or '-'}",
        ],
        actions,
    )


def _release_contract(data: dict[str, Any]) -> dict[str, Any]:
    availability = _dict(data["availability"])
    submission = _dict(data["submission"])
    final = _dict(data["final"])
    package = _dict(data["package"])
    repair = _dict(data["repair_queue"])
    repair_resolution = _dict(data["repair_resolution"])
    repair_summary = repair.get("summary") if isinstance(repair.get("summary"), dict) else {}
    repair_block = _int(repair_summary.get("block"))
    repair_total = _int(repair_summary.get("total"))
    status = "pass"
    actions: list[str] = []
    if str(availability.get("status") or "") == "blocked":
        status = "block"
        actions.append("修复代码/数据可用性阻断项。")
    if _list(submission.get("blocking_issues")) or str(submission.get("status") or "") == "block":
        status = "block"
        actions.append("修复 10-submission-check.md 中投稿格式阻断项。")
    if _list(final.get("blocking_issues")):
        status = "block"
        actions.append("修复 10-final-readiness.md 中最终 gate 阻断项。")
    package_blocking = _list(package.get("blocking_issues"))
    if package_blocking and not _package_blocking_only_stale_repair_queue(package_blocking, repair):
        status = "block"
        actions.append("修复 11-submission-package.md 中缺失必需包文件。")
    elif package_blocking and status == "pass":
        status = "warn"
        actions.append("重新生成 11-submission-package，清除旧 repair queue 状态造成的投稿包待办。")
    repair_status = str(repair.get("status") or "")
    if repair_status == "blocked_repair_required" and repair_block:
        status = "block"
        actions.append("先处理 12-repair-queue.md 中仍阻断下游或投稿的修复项。")
    elif repair_status == "blocked_repair_required" and status == "pass":
        status = "warn"
        actions.append("12-repair-queue 状态仍是 blocked_repair_required 但没有 block 任务；重新生成 repair queue 和 submission package。")
    elif repair_status == "needs_repair" and status == "pass":
        status = "warn"
        actions.append("人工确认 12-repair-queue.md 中 high/medium 修复项是否已处理或接受风险。")
    if str(repair_resolution.get("status") or "") == "block":
        status = "block"
        actions.append("先处理 12-repair-resolution-audit.md 中未闭环的原修复项。")
    elif status == "pass" and str(repair_resolution.get("status") or "") == "review_required":
        status = "warn"
        actions.append("人工确认 12-repair-resolution-audit.md 中剩余 high/medium 修复项。")
    if status == "pass" and (_list(availability.get("manual_tasks")) or _list(submission.get("manual_tasks")) or _list(package.get("manual_tasks"))):
        status = "warn"
        actions.append("完成 code/data、投稿格式和 ZIP 上传前的人工待办。")
    return _check(
        "release_reproducibility",
        "归档前必须完成代码/数据可用性、投稿检查、最终 gate、投稿包和 repair queue 收敛。",
        ["Agent Laboratory", "MLAgentBench"],
        status,
        [
            f"availability={availability.get('status') or '-'}",
            f"submission={submission.get('status') or '-'}",
            f"final={final.get('status') or '-'}",
            f"package={package.get('status') or '-'}",
            f"repair_queue={repair.get('status') or '-'}:{repair_total}/{repair_block}",
            f"repair_resolution={repair_resolution.get('status') or '-'}",
        ],
        actions,
    )


def _observability_contract(data: dict[str, Any]) -> dict[str, Any]:
    manifest = _dict(data["manifest"])
    ledger = _dict(data["ledger"])
    iteration = _dict(data["iteration"])
    runtime_contract = _dict(data["llm_runtime_contract"])
    run_economics = _dict(data["run_economics"])
    observability = _dict(data["observability"])
    failed_calls = _int(ledger.get("failed_calls"))
    budget_exceeded_calls = _int(ledger.get("budget_exceeded_calls"))
    failure_recovery = summarize_llm_failure_recovery(ledger)
    artifacts = _list(manifest.get("artifacts"))
    events = _list(manifest.get("events"))
    observability_status = str(observability.get("status") or "")
    runtime_status = str(runtime_contract.get("status") or "")
    economics_status = str(run_economics.get("status") or "")
    status = "pass"
    actions: list[str] = []
    if not manifest or len(events) < 5:
        status = "missing"
        actions.append("补齐 run-manifest 事件，保证阶段轨迹可审计。")
    if not ledger:
        status = "missing"
        actions.append("补齐 run-llm-ledger，记录 LLM 调用。")
    if failed_calls:
        unrecovered_failed = _int(failure_recovery.get("unrecovered_failed_calls"))
        if unrecovered_failed:
            status = "block"
            actions.append("处理 run-llm-ledger 中未恢复的 LLM 失败调用。")
        elif status == "pass":
            status = "warn"
            actions.append("人工核对 run-llm-ledger 中已由后续同阶段 success 恢复的失败调用。")
    if budget_exceeded_calls:
        unrecovered_budget = _int(failure_recovery.get("unrecovered_budget_exceeded_calls"))
        if unrecovered_budget:
            status = "block"
            actions.append("处理 run-llm-ledger 中未恢复的 LLM 预算拦截调用。")
        elif status == "pass":
            status = "warn"
            actions.append("人工核对 run-llm-ledger 中已由后续同阶段 success 恢复的预算拦截调用。")
    if not runtime_contract:
        status = "missing" if status == "pass" else status
        actions.append("生成 13-llm-runtime-contract.md/json，证明模型配置、预算、密钥落盘和 ledger 元数据一致。")
    elif runtime_status == "block":
        status = "block"
        actions.extend(str(item) for item in _list(runtime_contract.get("blocking_issues"))[:3] or ["修复 13-llm-runtime-contract.md 中的 LLM 运行契约阻断项。"])
    elif status == "pass" and runtime_status == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(runtime_contract.get("manual_tasks"))[:3] or ["人工核对 13-llm-runtime-contract.md。"])
    if not run_economics:
        status = "missing" if status == "pass" else status
        actions.append("生成 13-run-economics-audit.md/json，补齐运行成本和耗时审计。")
    elif economics_status == "block":
        status = "block"
        actions.extend(str(item) for item in _list(run_economics.get("blocking_issues"))[:3] or ["修复 13-run-economics-audit.md 中的运行成本阻断项。"])
    elif status == "pass" and economics_status == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(run_economics.get("manual_tasks"))[:3] or ["人工核对 13-run-economics-audit.md。"])
    if not iteration:
        status = "warn" if status == "pass" else status
        actions.append("生成 12-next-iteration-plan，明确下一轮动作。")
    if not observability:
        status = "missing" if status == "pass" else status
        actions.append("生成 13-agent-observability-audit.md/json，补齐运行可观测性审计。")
    elif observability_status == "block":
        status = "block"
        actions.extend(str(item) for item in _list(observability.get("blocking_issues"))[:3] or ["修复 13-agent-observability-audit.md 中的可观测性阻断项。"])
    elif status == "pass" and observability_status == "review_required":
        status = "warn"
        actions.extend(str(item) for item in _list(observability.get("manual_tasks"))[:3] or ["人工核对 13-agent-observability-audit.md。"])
    return _check(
        "observability_resume",
        "平台必须留下 manifest、LLM ledger、LLM runtime contract、运行成本审计、artifact 清单、运行可观测性审计和下一轮计划，支持恢复与审计。",
        ["Agent Laboratory", "AI-Scientist", "MLAgentBench"],
        status,
        [f"events={len(events)}", f"artifacts={len(artifacts)}", f"llm_failed={failed_calls}", f"llm_budget={budget_exceeded_calls}", f"iteration={iteration.get('status') or '-'}", f"llm_runtime={runtime_status or '-'}", f"run_economics={economics_status or '-'}", f"observability={observability_status or '-'}"],
        actions,
    )


def _open_source_contract(data: dict[str, Any]) -> dict[str, Any]:
    lessons_report = _dict(data["open_source"])
    compliance = _dict(data["open_source_compliance"])
    lessons = _list(lessons_report.get("lessons"))
    project_evidence = _list(lessons_report.get("project_evidence"))
    contract = _dict(compliance.get("contract_summary"))
    compliance_status = str(compliance.get("status") or "")
    status = "pass"
    actions: list[str] = []
    if not lessons_report:
        status = "missing"
        actions.append("生成 00-open-source-lessons.md/json，记录 AI-Scientist、PaperQA2/OpenScholar、AgentLaboratory 和 MLAgentBench 的外部项目约束。")
    elif not lessons:
        status = "block"
        actions.append("补齐 00-open-source-lessons.json 中的 lessons，不能只保留空的开源项目参考。")
    if lessons_report and not project_evidence:
        status = "block"
        actions.append("为 00-open-source-lessons.json 补充 project_evidence，记录仓库 URL、验证方式和证据目标。")
    if not compliance:
        status = "missing" if status == "pass" else status
        actions.append("生成 13-open-source-compliance.md/json，逐条证明外部项目约束已落实。")
    elif compliance_status == "block":
        status = "block"
        actions.extend(str(item) for item in _list(compliance.get("blocking_issues"))[:3] or ["修复 13-open-source-compliance.md 中的外部项目约束阻断项。"])
    elif status == "pass" and compliance_status == "needs_human_review":
        status = "warn"
        actions.extend(str(item) for item in _list(compliance.get("manual_tasks"))[:3] or ["人工核对 13-open-source-compliance.md 中的外部项目约束待办。"])
    return _check(
        "open_source_lesson_contract",
        "参考开源项目必须转化为每个 run 可审计的 lesson、来源证据和合规报告。",
        ["SakanaAI/AI-Scientist-v2", "Future-House/PaperQA2", "OpenScholar", "SamuelSchmidgall/AgentLaboratory", "MLAgentBench"],
        status,
        [
            f"lessons={len(lessons)}",
            f"project_evidence={len(project_evidence)}",
            f"compliance={compliance_status or '-'}",
            f"score={_float(compliance.get('score')):.2f}",
            f"checked={_int(compliance.get('checked_lessons'))}",
            f"contract={contract.get('status') or '-'}:{_int(contract.get('checked_lessons'))}/{_int(contract.get('required_lessons'))}",
        ],
        actions,
    )


def _check(stage: str, expectation: str, source_projects: list[str], status: str, evidence: list[str], actions: list[str]) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "source_projects": source_projects,
        "expectation": expectation,
        "evidence": evidence,
        "required_actions": _unique(actions),
    }


def _open_source_patterns(open_source: Any) -> list[str]:
    report = _dict(open_source)
    lessons = _list(report.get("lessons"))
    patterns: list[str] = []
    for item in lessons[:8]:
        if isinstance(item, dict):
            lesson_id = str(item.get("lesson_id") or "lesson")
            requirement = str(item.get("requirement") or "")
            if requirement:
                patterns.append(f"{lesson_id}: {requirement}")
    return patterns


def _paper_grade_literature_allows_residual_review(
    *,
    selected: int,
    citations: int,
    blocked_citations: int,
    metadata: dict[str, Any],
    coverage: dict[str, Any],
    evidence_mix: dict[str, Any],
    literature_gate: dict[str, Any],
    paper_grade_status: str,
    query_status: str,
) -> bool:
    if paper_grade_status != "pass":
        return False
    if selected < 3 or citations < 3 or blocked_citations:
        return False
    if str(metadata.get("status") or "") == "block" or _int(metadata.get("blocked")):
        return False
    if str(coverage.get("status") or "") in {"needs_literature", "block"}:
        return False
    if str(evidence_mix.get("status") or "") == "block":
        return False
    if str(literature_gate.get("status") or "") == "block":
        return False
    if query_status == "needs_source_repair":
        return False
    return True


def _clean_revised_paper_gate(final: dict[str, Any], revised_review: dict[str, Any], trace: dict[str, Any]) -> bool:
    decision = str(revised_review.get("decision") or revised_review.get("status") or "")
    blocking_decisions = {"reject", "major_revision", "requires_revision", "block"}
    return (
        str(final.get("status") or "") == "ready_for_submission_check"
        and _int(final.get("unsupported_after")) == 0
        and _int(final.get("weak_after")) == 0
        and not _list(final.get("blocking_issues"))
        and str(trace.get("status") or "") == "pass"
        and decision not in blocking_decisions
        and not _list(revised_review.get("unsupported_claims"))
    )


def _package_blocking_only_stale_repair_queue(blocking: list[Any], repair: dict[str, Any]) -> bool:
    if not blocking:
        return False
    repair_summary = repair.get("summary") if isinstance(repair.get("summary"), dict) else {}
    if str(repair.get("status") or "") not in {"pass", "needs_repair", "blocked_repair_required"}:
        return False
    if _int(repair_summary.get("block")):
        return False
    return all("修复队列" in str(item) or "repair" in str(item).lower() for item in blocking)


def _recommended_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "pass":
        return ["人工抽查 13-agent-stage-contract.md、13-research-scorecard.md 和 14-run-integrity-audit.md 后再对外发布。"]
    if blocking:
        return ["先处理阻断问题，再运行 repair-resume 或 checkpoint resume 重新生成受影响阶段。", *blocking[:4]]
    return ["完成人工待办后重新生成 13-agent-stage-contract 和 submission package。", *manual[:4]]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


