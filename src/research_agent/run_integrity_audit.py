from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, read_json_dict as _read_json
from .provenance import active_revision, filter_active_events
from .submission_package_zip import submission_package_zip_blocking_issue


RUN_INTEGRITY_AUDIT_JSON = "14-run-integrity-audit.json"
RUN_INTEGRITY_AUDIT_MD = "14-run-integrity-audit.md"

COMPLETED_REQUIRED_ARTIFACTS = [
    "run-manifest.json",
    "run-manifest.md",
    "run-llm-ledger.json",
    "run-llm-ledger.md",
    "00-preflight.json",
    "00-preflight.md",
    "00-question.md",
    "00-prior-run-lessons.json",
    "00-prior-run-lessons.md",
    "00-open-source-lessons.json",
    "00-open-source-lessons.md",
    "00-research-plan.json",
    "00-research-plan.md",
    "01-literature.json",
    "01-literature.md",
    "01-literature-rerank.json",
    "01-literature-rerank.md",
    "01-literature-search-strategy.json",
    "01-literature-search-strategy.md",
    "01-literature-source-health.json",
    "01-literature-source-health.md",
    "01-query-execution-audit.json",
    "01-query-execution-audit.md",
    "01-literature-snowball.json",
    "01-literature-snowball.md",
    "01-literature-coverage.json",
    "01-literature-coverage.md",
    "01-literature-evidence-mix.json",
    "01-literature-evidence-mix.md",
    "01-literature-evidence-contract.json",
    "01-literature-evidence-contract.md",
    "01-literature-rescue-plan.json",
    "01-literature-rescue-plan.md",
    "01-literature-rescue-execution.json",
    "01-literature-rescue-execution.md",
    "01-literature-search-feedback.json",
    "01-literature-search-feedback.md",
    "01-seed-paper-intake.json",
    "01-seed-paper-intake.md",
    "01-literature-quality.json",
    "01-literature-quality.md",
    "01-literature-curated.json",
    "01-literature-curated.md",
    "01-literature-metadata-audit.json",
    "01-literature-metadata-audit.md",
    "01-fulltext-corpus.json",
    "01-fulltext-corpus.md",
    "01-context.json",
    "01-context.md",
    "01-review-gate.md",
    "01-citation-audit.json",
    "01-citation-audit.md",
    "approval.json",
    "01-review-feedback.json",
    "01-review-feedback.md",
    "01-review-constraints.json",
    "01-review-constraints.md",
    "01-references.bib",
    "01-references.ris",
    "02-ideas.json",
    "02-ideas.md",
    "02-novelty-audit.json",
    "02-novelty-audit.md",
    "02-idea-audit.json",
    "02-idea-audit.md",
    "02-exploration-map.json",
    "02-exploration-map.md",
    "02-exploration-map.svg",
    "02-experiment-manager.json",
    "02-experiment-manager.md",
    "03-experiment-plan.json",
    "03-experiment-plan.md",
    "03-review-constraint-compliance.json",
    "03-review-constraint-compliance.md",
    "03-experiment-audit.json",
    "03-experiment-audit.md",
    "03-idea-experiment-contract.json",
    "03-idea-experiment-contract.md",
    "03-execution-safety-audit.json",
    "03-execution-safety-audit.md",
    "03-ablation-plan.json",
    "03-ablation-plan.md",
    "03-preregistration.json",
    "03-preregistration.md",
    "03-benchmark-plan.json",
    "03-benchmark-plan.md",
    "03-benchmark-readiness.json",
    "03-benchmark-readiness.md",
    "04-results.json",
    "04-results.csv",
    "04-experiment-runbook.json",
    "04-experiment-runbook.md",
    "04-environment-snapshot.json",
    "04-environment-snapshot.md",
    "04-statistics.json",
    "04-statistics.md",
    "04-result-validation.json",
    "04-result-validation.md",
    "04-failure-analysis.json",
    "04-failure-analysis.md",
    "04-benchmark-result-schema-audit.json",
    "04-benchmark-result-schema-audit.md",
    "04-benchmark-evidence-audit.json",
    "04-benchmark-evidence-audit.md",
    "04-experiment-decision.json",
    "04-experiment-decision.md",
    "04-hypothesis-outcome.json",
    "04-hypothesis-outcome.md",
    "04-claim-boundary-preflight.json",
    "04-claim-boundary-preflight.md",
    "04-statistics-figure.json",
    "04-statistics-figure.svg",
    "05-analysis.json",
    "05-analysis.md",
    "06-paper.md",
    "06-paper.tex",
    "07-paper-review.json",
    "07-paper-review.md",
    "07-paper-review-calibration.json",
    "07-paper-review-calibration.md",
    "08-revision-plan.json",
    "08-revision-plan.md",
    "09-revised-paper.md",
    "09-revised-paper.tex",
    "09-revision-report.json",
    "09-revision-report.md",
    "09-revision-response-audit.json",
    "09-revision-response-audit.md",
    "10-revised-paper-review.json",
    "10-revised-paper-review.md",
    "10-claim-traceability.json",
    "10-claim-traceability.md",
    "10-citation-grounding.json",
    "10-citation-grounding.md",
    "10-citation-coverage.json",
    "10-citation-coverage.md",
    "10-results-presentation.json",
    "10-results-presentation.md",
    "10-claim-consistency.json",
    "10-claim-consistency.md",
    "10-release-metadata.json",
    "10-release-metadata.md",
    "10-code-data-availability.json",
    "10-code-data-availability.md",
    "10-ai-disclosure.json",
    "10-ai-disclosure.md",
    "10-submission-check.json",
    "10-submission-check.md",
    "10-final-readiness.json",
    "10-final-readiness.md",
    "11-submission-package.json",
    "11-submission-package.md",
    "11-submission-package.zip",
    "12-next-iteration-plan.json",
    "12-next-iteration-plan.md",
    "12-repair-queue.json",
    "12-repair-queue.md",
    "12-repair-resolution-audit.json",
    "12-repair-resolution-audit.md",
    "13-human-gate-audit.json",
    "13-human-gate-audit.md",
    "13-agent-stage-contract.json",
    "13-agent-stage-contract.md",
    "13-agent-trajectory.json",
    "13-agent-trajectory.md",
    "13-llm-trace-audit.json",
    "13-llm-trace-audit.md",
    "13-llm-runtime-contract.json",
    "13-llm-runtime-contract.md",
    "13-run-economics-audit.json",
    "13-run-economics-audit.md",
    "13-agent-observability-audit.json",
    "13-agent-observability-audit.md",
    "13-llm-observability-summary.json",
    "13-llm-observability-summary.md",
    "13-research-scorecard.json",
    "13-research-scorecard.md",
    "state.json",
]

GROUNDING_STAGES = {
    "literature_context",
    "literature_context_checkpoint",
    "review_revision_literature_repair",
    "review_approval",
    "review_approval_checkpoint",
    "resume_after_review_approval",
    "review_feedback",
    "review_constraints",
}

DOWNSTREAM_STAGES = {
    "ideation",
    "ideation_checkpoint",
    "novelty_audit",
    "novelty_audit_checkpoint",
    "idea_audit",
    "idea_audit_checkpoint",
    "exploration_map",
    "exploration_map_checkpoint",
    "experiment_plan",
    "experiment_plan_checkpoint",
    "review_constraint_compliance",
    "ablation_plan",
    "ablation_plan_checkpoint",
    "preregistration",
    "preregistration_checkpoint",
    "experiment_audit",
    "idea_experiment_contract",
    "execution_safety_audit",
    "benchmark_plan",
    "benchmark_plan_checkpoint",
    "experiments",
    "experiments_checkpoint",
    "analysis",
    "analysis_checkpoint",
    "claim_boundary_preflight",
    "claim_boundary_preflight_checkpoint",
    "paper_and_review",
    "paper_and_review_checkpoint",
    "paper_revision_plan",
    "paper_revision_plan_checkpoint",
    "paper_rewrite",
    "paper_rewrite_checkpoint",
    "revision_response_audit",
    "revision_response_audit_checkpoint",
    "final_readiness",
    "final_readiness_checkpoint",
    "submission_package",
    "iteration_plan",
    "repair_queue",
    "repair_resolution_audit",
    "research_scorecard",
}

DOWNSTREAM_FRESHNESS_GROUPS = [
    {
        "name": "ideas",
        "stages": {"ideation", "ideation_checkpoint"},
        "artifacts": ["02-ideas.json", "02-ideas.md"],
    },
        {
            "name": "experiment_plan",
            "stages": {"experiment_manager", "experiment_manager_checkpoint", "experiment_plan", "experiment_plan_checkpoint", "review_constraint_compliance", "idea_experiment_contract"},
            "artifacts": ["02-experiment-manager.json", "03-experiment-plan.json", "03-experiment-plan.md", "03-review-constraint-compliance.json", "03-idea-experiment-contract.json"],
        },
    {
        "name": "experiments",
        "stages": {"experiments", "experiments_checkpoint"},
        "artifacts": ["04-results.json", "04-results.csv"],
    },
    {
        "name": "analysis",
        "stages": {"analysis", "analysis_checkpoint"},
        "artifacts": ["05-analysis.json", "05-analysis.md"],
    },
    {
        "name": "claim_boundary_preflight",
        "stages": {"claim_boundary_preflight", "claim_boundary_preflight_checkpoint"},
        "artifacts": ["04-claim-boundary-preflight.json", "04-claim-boundary-preflight.md"],
    },
    {
        "name": "paper",
        "stages": {"paper_and_review", "paper_and_review_checkpoint"},
        "artifacts": ["06-paper.md", "07-paper-review.json"],
    },
    {
        "name": "paper_rewrite",
        "stages": {"paper_rewrite", "paper_rewrite_checkpoint", "revision_response_audit", "revision_response_audit_checkpoint"},
        "artifacts": ["09-revised-paper.md", "09-revision-report.json", "09-revision-response-audit.json"],
    },
    {
        "name": "final_audits",
        "stages": {"final_readiness", "final_readiness_checkpoint"},
        "artifacts": ["10-final-readiness.json", "10-submission-check.json", "10-citation-coverage.json"],
    },
    {
        "name": "submission_package",
        "stages": {"submission_package"},
        "artifacts": ["11-submission-package.json"],
    },
]


def write_run_integrity_audit_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_run_integrity_audit(topic, run_dir)
    write_json(run_dir / RUN_INTEGRITY_AUDIT_JSON, report)
    write_text(run_dir / RUN_INTEGRITY_AUDIT_MD, render_run_integrity_audit_markdown(report))
    return report


def build_run_integrity_audit(topic: str, run_dir: Path) -> dict[str, Any]:
    state = _read_json(run_dir / "state.json")
    approval = _read_json(run_dir / "approval.json")
    execution_approval = _read_json(run_dir / "03-execution-approval.json")
    manifest = _read_json(run_dir / "run-manifest.json")
    package = _read_json(run_dir / "11-submission-package.json")
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    llm_trace_audit = _read_json(run_dir / "13-llm-trace-audit.json")
    llm_runtime_contract = _read_json(run_dir / "13-llm-runtime-contract.json")
    run_config = _read_json(run_dir / "run-config.json")
    runbook = _read_json(run_dir / "04-experiment-runbook.json")
    items = [
        _artifact_inventory_check(run_dir),
        _json_validity_check(run_dir),
        _state_check(state),
        *_human_gate_checks(run_dir, approval, manifest),
        *_execution_gate_checks(run_dir, execution_approval, runbook, manifest),
        *_freshness_checks(run_dir, manifest),
        *_manifest_checks(run_dir, manifest),
        *_package_checks(run_dir, package),
        _llm_ledger_check(ledger),
        _llm_trace_audit_check(llm_trace_audit),
        _llm_runtime_contract_check(llm_runtime_contract),
        _secret_persistence_check(run_config),
    ]
    status = _overall_status(items)
    return {
        "topic": topic or str(state.get("topic") or run_dir.name),
        "status": status,
        "summary": {
            "checks": len(items),
            "pass": sum(1 for item in items if item["status"] == "pass"),
            "warn": sum(1 for item in items if item["status"] == "warn"),
            "block": sum(1 for item in items if item["status"] == "block"),
            "required_artifacts": len(COMPLETED_REQUIRED_ARTIFACTS),
        },
        "items": items,
        "blocking_issues": [f"{item['category']}/{item['name']}: {item['evidence']}" for item in items if item["status"] == "block"],
        "warnings": [f"{item['category']}/{item['name']}: {item['evidence']}" for item in items if item["status"] == "warn"],
        "recommended_actions": _recommended_actions(items),
    }


def render_run_integrity_audit_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# Run Integrity Audit：{report.get('topic') or '未命名课题'}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 检查项：{summary.get('checks', 0)}",
        f"- 通过/警告/阻断：{summary.get('pass', 0)}/{summary.get('warn', 0)}/{summary.get('block', 0)}",
        f"- 必需产物：{summary.get('required_artifacts', 0)}",
        "",
        "## 检查明细",
        "| 类别 | 检查 | 状态 | 证据 | 动作 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.get("items", []) if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("category") or "")),
                    _cell(str(item.get("name") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("evidence") or "")),
                    _cell(str(item.get("action") or "")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    blockers = report.get("blocking_issues", []) if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- 无")
    lines.extend(["", "## 警告"])
    warnings = report.get("warnings", []) if isinstance(report.get("warnings"), list) else []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    actions = report.get("recommended_actions", []) if isinstance(report.get("recommended_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 无")
    return "\n".join(lines)


def _artifact_inventory_check(run_dir: Path) -> dict[str, Any]:
    missing = [name for name in COMPLETED_REQUIRED_ARTIFACTS if not _nonempty_file(run_dir / name)]
    if missing:
        return _item("artifact", "required_completed_artifacts", "block", f"缺失或为空 {len(missing)} 个：{', '.join(missing[:8])}", "补齐缺失产物后从 checkpoint resume。", missing[:8])
    return _item("artifact", "required_completed_artifacts", "pass", f"{len(COMPLETED_REQUIRED_ARTIFACTS)} 个必需产物存在且非空。", "无需处理。")


def _json_validity_check(run_dir: Path) -> dict[str, Any]:
    invalid: list[str] = []
    checked = 0
    for path in sorted(run_dir.glob("*.json")):
        checked += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            invalid.append(path.name)
    if invalid:
        return _item("json", "top_level_json_validity", "block", f"{len(invalid)} 个顶层 JSON 不可解析：{', '.join(invalid[:8])}", "修复损坏 JSON 后重新运行 resume 或重新生成对应阶段。", invalid[:8])
    return _item("json", "top_level_json_validity", "pass", f"{checked} 个顶层 JSON 可解析。", "无需处理。")


def _state_check(state: dict[str, Any]) -> dict[str, Any]:
    stage = str(state.get("stage") or "")
    if stage in {"scorecard_completed", "run_integrity_audit_completed", "completed"}:
        return _item("state", "terminal_stage", "pass", f"state.stage={stage}", "无需处理。")
    if not stage:
        return _item("state", "terminal_stage", "warn", "缺少 state.json 或 stage 字段。", "确认 run 状态并重新写入 state.json。")
    return _item("state", "terminal_stage", "warn", f"最终审计运行时 state.stage={stage}", "确认该 run 是否仍在执行或从 checkpoint resume。")


def _human_gate_checks(run_dir: Path, approval: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    downstream = [name for name in ["02-ideas.json", "03-experiment-plan.json", "04-results.json"] if (run_dir / name).exists()]
    items: list[dict[str, Any]] = []
    if not downstream:
        items.append(_item("human_gate", "approval_before_downstream", "warn", "未发现 idea/实验产物，无法验证 gate 后续顺序。", "确认 run 是否已经完成。"))
    elif not approval:
        items.append(_item("human_gate", "approval_before_downstream", "block", f"已有下游产物 {', '.join(downstream)}，但 approval.json 缺失或不可读。", "补齐人工批准记录；无法确认时不要采信下游产物。"))
    elif approval.get("approved") is not True or approval.get("revision_requested") is True:
        items.append(_item("human_gate", "approval_before_downstream", "block", f"已有下游产物 {', '.join(downstream)}，但 approved={approval.get('approved')} revision_requested={approval.get('revision_requested')}。", "先完成文献 gate 人工批准，再恢复 idea/实验。"))
    else:
        items.append(_item("human_gate", "approval_before_downstream", "pass", f"人工批准存在，下游产物：{', '.join(downstream)}。", "无需处理。"))

    blocks = approval.get("blocks") if isinstance(approval.get("blocks"), list) else []
    if approval and {"idea_generation", "experiment_planning", "experiment_execution"}.issubset(set(str(item) for item in blocks)):
        items.append(_item("human_gate", "blocked_actions_declared", "pass", "approval.json 声明阻断 idea_generation、experiment_planning 和 experiment_execution。", "无需处理。"))
    elif approval:
        items.append(_item("human_gate", "blocked_actions_declared", "warn", "approval.json 未完整声明人工 gate 阻断的下游动作。", "重新生成 approval gate 或人工核对该历史 run。"))

    if approval and approval.get("approved") is True:
        if _approval_notes_required(approval):
            notes = str(approval.get("notes") or "")
            if _substantive_approval_notes(notes):
                items.append(_item("human_gate", "approval_notes", "pass", "非 pass review gate 已记录人工批准意见。", "无需处理。"))
            else:
                items.append(
                    _item(
                        "human_gate",
                        "approval_notes",
                        "block",
                        "非 pass review gate 已批准，但 approval.json 缺少实质性审核意见。",
                        "补充人工审核理由、已完成的文献/引用修复或风险接受说明；无法确认时不要采信下游产物。",
                    )
                )
        else:
            items.append(_item("human_gate", "approval_notes", "pass", "review gate 为 pass 或历史状态未知，不强制要求批准意见。", "无需处理。"))

    events = _active_events(run_dir, manifest)
    if events and downstream:
        approval_index = _first_event_index(events, {"review_approval", "review_approval_checkpoint"})
        downstream_index = _first_event_index(events, {"ideation", "ideation_checkpoint", "experiment_plan", "experiment_plan_checkpoint", "experiments", "experiments_checkpoint"})
        if approval_index is None:
            items.append(_item("human_gate", "manifest_order", "block", "manifest 中没有 review_approval 事件，但已有 idea/实验事件。", "核对 run-manifest；无法确认时不要采信下游产物。"))
        elif downstream_index is not None and approval_index > downstream_index:
            items.append(_item("human_gate", "manifest_order", "block", f"manifest 顺序异常：approval_index={approval_index}, downstream_index={downstream_index}。", "检查是否有人手工篡改或错误恢复。"))
        else:
            items.append(_item("human_gate", "manifest_order", "pass", f"manifest 中人工批准发生在下游阶段之前。approval_index={approval_index}", "无需处理。"))
    elif downstream:
        items.append(_item("human_gate", "manifest_order", "warn", "manifest 缺失或没有事件，无法验证人工 gate 顺序。", "检查 run-manifest.json 是否损坏或重新生成。"))
    return items


def _execution_gate_checks(run_dir: Path, execution_approval: dict[str, Any], runbook: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    mode = _execution_mode(execution_approval, runbook)
    if mode not in {"local", "benchmark"}:
        return []
    if not (run_dir / "04-results.json").exists():
        return [
            _item(
                "execution_gate",
                "approval_before_execution",
                "warn",
                f"execution_mode={mode}，但未发现 04-results.json，无法验证执行确认顺序。",
                "确认 run 是否仍停在 awaiting_execution_approval 或尚未执行。",
            )
        ]
    items: list[dict[str, Any]] = []
    if not execution_approval:
        items.append(_item("execution_gate", "approval_before_execution", "block", f"execution_mode={mode} 且已有实验结果，但 03-execution-approval.json 缺失或不可读。", "补齐人工执行确认记录；无法确认时不要采信本地/benchmark 结果。"))
    elif execution_approval.get("approved") is not True:
        items.append(_item("execution_gate", "approval_before_execution", "block", f"execution_mode={mode} 且已有实验结果，但 execution approved={execution_approval.get('approved')}。", "先完成人工执行确认，再重新运行实验。"))
    elif not _substantive_approval_notes(str(execution_approval.get("notes") or "")):
        items.append(_item("execution_gate", "approval_before_execution", "block", f"execution_mode={mode} 的执行确认缺少实质性 notes。", "补充命令计划、安全审计和白名单确认说明。"))
    else:
        items.append(_item("execution_gate", "approval_before_execution", "pass", f"execution_mode={mode} 已记录人工执行确认。", "无需处理。"))

    blocks = execution_approval.get("blocks") if isinstance(execution_approval.get("blocks"), list) else []
    if execution_approval and "experiment_execution" in {str(item) for item in blocks}:
        items.append(_item("execution_gate", "blocked_actions_declared", "pass", "03-execution-approval.json 声明阻断 experiment_execution。", "无需处理。"))
    elif execution_approval:
        items.append(_item("execution_gate", "blocked_actions_declared", "warn", "03-execution-approval.json 未声明阻断 experiment_execution。", "重新生成 execution approval gate 或人工核对历史 run。"))

    events = _active_events(run_dir, manifest)
    if events:
        approval_index = _first_event_index(events, {"execution_approval"})
        experiments_index = _first_event_index(events, {"experiments", "experiments_checkpoint"})
        if experiments_index is not None and approval_index is None:
            items.append(_item("execution_gate", "manifest_order", "block", "manifest 中没有 execution_approval 事件，但已有 experiments 事件。", "核对 manifest；无法确认时不要采信本地/benchmark 结果。"))
        elif approval_index is not None and experiments_index is not None and approval_index > experiments_index:
            items.append(_item("execution_gate", "manifest_order", "block", f"manifest 顺序异常：execution_approval_index={approval_index}, experiments_index={experiments_index}。", "重新运行执行确认后的实验阶段。"))
        elif experiments_index is not None:
            items.append(_item("execution_gate", "manifest_order", "pass", f"manifest 中 execution_approval 发生在 experiments 之前。approval_index={approval_index}", "无需处理。"))
    return items


def _execution_mode(execution_approval: dict[str, Any], runbook: dict[str, Any]) -> str:
    mode = str(execution_approval.get("execution_mode") or "").strip()
    if mode:
        return mode
    execution = runbook.get("execution") if isinstance(runbook.get("execution"), dict) else {}
    return str(execution.get("mode") or "").strip()


def _freshness_checks(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if not manifest:
        return []
    events = _active_events(run_dir, manifest)
    if not events:
        return []
    grounding_index = _last_event_index(events, GROUNDING_STAGES)
    present_groups = [
        group
        for group in DOWNSTREAM_FRESHNESS_GROUPS
        if any((run_dir / str(artifact)).exists() for artifact in group["artifacts"])
    ]
    if not present_groups:
        return []
    if grounding_index is None:
        return [
            _item(
                "freshness",
                "grounding_before_downstream",
                "block",
                "run 有下游 idea/实验/论文产物，但 manifest 缺少文献 context 或 review approval 事件。",
                "不要采信下游产物；从文献 gate checkpoint 重新恢复，生成可追溯 manifest。",
            )
        ]
    grounding_stage = _event_stage(events[grounding_index])
    stale: list[str] = []
    fresh: list[str] = []
    for group in present_groups:
        group_index = _last_event_index(events, {str(stage) for stage in group["stages"]})
        name = str(group["name"])
        if group_index is None:
            stale.append(f"{name}: missing event")
            continue
        group_stage = _event_stage(events[group_index])
        if group_index < grounding_index:
            stale.append(f"{name}: {group_stage}@{group_index}")
        else:
            fresh.append(f"{name}: {group_stage}@{group_index}")
    if stale:
        return [
            _item(
                "freshness",
                "grounding_before_downstream",
                "block",
                f"最新 grounding/gate 事件 {grounding_stage}@{grounding_index} 之后，仍有 {len(stale)} 组下游产物缺少更新事件：{', '.join(stale[:6])}。",
                "删除或重生成旧下游产物；从最新 review gate 批准后重新生成 idea、实验和论文。",
                stale[:8],
            )
        ]
    return [
        _item(
            "freshness",
            "grounding_before_downstream",
            "pass",
            f"最新 grounding/gate 事件 {grounding_stage}@{grounding_index} 之后，{len(fresh)} 组下游产物都有生成或 checkpoint 事件。",
            "无需处理。",
        )
    ]


def _approval_notes_required(approval: dict[str, Any]) -> bool:
    stored_policy = approval.get("approval_policy")
    policy_status = ""
    stored_notes_required = False
    if isinstance(stored_policy, dict):
        policy_status = str(stored_policy.get("gate_status") or "").strip()
        stored_notes_required = stored_policy.get("notes_required") is True
    status = str(approval.get("gate_status") or "").strip()
    if status:
        return status not in {"pass", "unknown"}
    if policy_status:
        return policy_status not in {"pass", "unknown"}
    return stored_notes_required


def _substantive_approval_notes(notes: str) -> bool:
    normalized = " ".join(str(notes or "").split())
    return len(normalized) >= 8


def _manifest_checks(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if not manifest:
        return [_item("manifest", "presence", "block", "run-manifest.json 缺失或不可读。", "重新运行或从 checkpoint resume 以生成 provenance。")]
    events = manifest.get("events") if isinstance(manifest.get("events"), list) else []
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    items = [_item("manifest", "events", "pass" if events else "block", f"events={len(events)}", "无需处理。" if events else "重新生成 run-manifest.json。")]
    artifact_paths = {str(item.get("path") or "") for item in artifacts if isinstance(item, dict)}
    missing_from_manifest = [name for name in COMPLETED_REQUIRED_ARTIFACTS if (run_dir / name).exists() and name not in artifact_paths]
    stale = [name for name in artifact_paths if name and not (run_dir / name).exists()]
    if missing_from_manifest:
        items.append(_item("manifest", "artifact_inventory", "warn", f"manifest 未记录 {len(missing_from_manifest)} 个现存必需产物：{', '.join(missing_from_manifest[:8])}", "重新写入 manifest 或从 checkpoint resume。", missing_from_manifest[:8]))
    elif stale:
        items.append(_item("manifest", "artifact_inventory", "warn", f"manifest 记录了 {len(stale)} 个已不存在产物：{', '.join(stale[:8])}", "核对是否手工删除了产物。", stale[:8]))
    else:
        items.append(_item("manifest", "artifact_inventory", "pass", f"manifest 记录 {len(artifact_paths)} 个产物，核心产物覆盖完整。", "无需处理。"))
    hash_issues = _manifest_hash_issues(run_dir, artifacts)
    if hash_issues:
        items.append(_item("manifest", "artifact_hashes", "block", f"发现 {len(hash_issues)} 个 SHA256 不匹配：{', '.join(hash_issues[:6])}", "检查产物是否在 manifest 生成后被修改；必要时重新运行后续阶段。", hash_issues[:6]))
    else:
        items.append(_item("manifest", "artifact_hashes", "pass", "manifest 中现存产物 SHA256 与磁盘一致。", "无需处理。"))
    return items


def _package_checks(run_dir: Path, package: dict[str, Any]) -> list[dict[str, Any]]:
    if not package:
        return [_item("submission_package", "presence", "block", "11-submission-package.json 缺失或不可读。", "重新生成投稿/归档包。")]
    status = str(package.get("status") or "")
    blocking = package.get("blocking_issues") if isinstance(package.get("blocking_issues"), list) else []
    package_files = package.get("files") if isinstance(package.get("files"), list) else []
    required_bad = [
        str(item.get("source_path") or item.get("package_path") or "")
        for item in package_files
        if isinstance(item, dict) and item.get("required") is True and item.get("status") not in {"pass", "generated"}
    ]
    items: list[dict[str, Any]] = []
    if required_bad:
        items.append(_item("submission_package", "package_status", "block", f"status={status or '-'}; blocking={len(blocking)}; required_bad={len(required_bad)}", "补齐投稿包缺失的必需文件后重新生成 ZIP。", required_bad[:8]))
    elif status == "blocked" or blocking:
        items.append(_item("submission_package", "package_status", "warn", f"status={status or '-'}; blocking={len(blocking)}; required_bad={len(required_bad)}", "投稿包已记录研究/投稿就绪阻断项；按 final readiness、scorecard 和 package checklist 处理。"))
    elif status in {"needs_human_submission_review", "ready_for_human_submission_upload"}:
        items.append(_item("submission_package", "package_status", "pass", f"status={status}; files={len(package_files)}", "按 CHECKLIST 做最终人工核验。"))
    else:
        items.append(_item("submission_package", "package_status", "warn", f"status={status or '-'}; files={len(package_files)}", "人工确认投稿包状态。"))

    zip_name = str(package.get("package_zip") or "11-submission-package.zip")
    zip_issue = submission_package_zip_blocking_issue(run_dir / zip_name, package_zip_name=zip_name, require_safe_filename=True)
    if not zip_issue:
        items.append(_item("submission_package", "zip_valid", "pass", f"{zip_name} 是可读 ZIP，包含 checklist 和 package manifest。", "无需处理。"))
    else:
        items.append(_item("submission_package", "zip_valid", "block", zip_issue, "重新生成投稿/归档 ZIP。"))

    package_paths = {str(item.get("package_path") or "") for item in package_files if isinstance(item, dict)}
    expected = {
        "submission-package/audits/final-readiness.json",
        "submission-package/audits/citation-grounding.json",
        "submission-package/audits/citation-coverage.json",
        "submission-package/audits/results-presentation.json",
        "submission-package/audits/revision-response-audit.json",
        "submission-package/audits/code-data-availability.json",
        "submission-package/audits/submission-check.json",
        "submission-package/audits/repair-queue.json",
        "submission-package/audits/repair-resolution-audit.json",
        "submission-package/audits/query-execution-audit.json",
        "submission-package/audits/llm-trace-audit.json",
        "submission-package/audits/run-economics-audit.json",
        "submission-package/audits/agent-observability-audit.json",
        "submission-package/audits/run-integrity-audit.json",
        "submission-package/results/benchmark-result-schema-audit.json",
        "submission-package/provenance/run-manifest.json",
        "submission-package/reproducibility/experiment-runbook.json",
        "submission-package/references/references.bib",
    }
    if not (run_dir / RUN_INTEGRITY_AUDIT_JSON).exists():
        expected.remove("submission-package/audits/run-integrity-audit.json")
    missing_expected = sorted(expected - package_paths)
    if missing_expected:
        items.append(_item("submission_package", "audit_bundle_contents", "warn", f"包内缺少 {len(missing_expected)} 个关键路径：{', '.join(missing_expected)}", "重新生成投稿包或核对 package spec。", missing_expected))
    else:
        items.append(_item("submission_package", "audit_bundle_contents", "pass", "包内包含 final readiness、可用性、投稿检查、manifest、runbook 和 references。", "无需处理。"))
    return items


def _llm_ledger_check(ledger: dict[str, Any]) -> dict[str, Any]:
    if not ledger:
        return _item("llm", "ledger", "block", "run-llm-ledger.json 缺失或不可读。", "确认 LLM 已配置并重新运行；不要用无 LLM 的历史产物冒充自动研究结果。")
    total = _safe_int(ledger.get("total_calls"))
    failed = _safe_int(ledger.get("failed_calls"))
    if total <= 0:
        return _item("llm", "ledger", "block", f"total_calls={total}", "检查 LLM 配置，重新运行需要模型参与的阶段。")
    if failed:
        return _item("llm", "ledger", "warn", f"total_calls={total}; failed_calls={failed}", "核对失败调用是否影响了研究计划、文献综述或论文复核。")
    return _item("llm", "ledger", "pass", f"total_calls={total}; failed_calls={failed}", "无需处理。")


def _llm_trace_audit_check(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return _item("llm", "trace_audit", "block", "13-llm-trace-audit.json 缺失或不可读。", "重新生成 LLM trace audit，不要跳过模型参与覆盖检查。")
    status = str(report.get("status") or "")
    blocking = len(report.get("blocking_issues", [])) if isinstance(report.get("blocking_issues"), list) else 0
    warnings = len(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else 0
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    coverage_ratio = _safe_float(coverage.get("coverage_ratio"))
    evidence = f"status={status or '-'}; coverage={coverage_ratio:.3f}; blocking={blocking}; warnings={warnings}"
    if status == "block" or blocking:
        return _item("llm", "trace_audit", "block", evidence, "修复 13-llm-trace-audit.md 中缺失、失败或预算拦截的模型调用后重跑。")
    if status == "warn" or warnings:
        return _item("llm", "trace_audit", "warn", evidence, "人工核对 LLM ledger、online search query planning 或 AI disclosure 警告。")
    return _item("llm", "trace_audit", "pass", evidence, "无需处理。")


def _llm_runtime_contract_check(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return _item("llm", "runtime_contract", "block", "13-llm-runtime-contract.json 缺失或不可读。", "重新生成 LLM runtime contract，证明模型配置、预算、密钥和 ledger 元数据一致。")
    status = str(report.get("status") or "")
    blocking = len(report.get("blocking_issues", [])) if isinstance(report.get("blocking_issues"), list) else 0
    manual = len(report.get("manual_tasks", [])) if isinstance(report.get("manual_tasks"), list) else 0
    warnings = len(report.get("warnings", [])) if isinstance(report.get("warnings"), list) else 0
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    evidence = f"status={status or '-'}; calls={_safe_int(summary.get('total_calls'))}; blocking={blocking}; manual={manual}; warnings={warnings}"
    if status == "block" or blocking:
        return _item("llm", "runtime_contract", "block", evidence, "修复 13-llm-runtime-contract.md 中的模型配置、预算、密钥落盘或 ledger 元数据阻断项。")
    if status == "review_required" or manual or warnings:
        return _item("llm", "runtime_contract", "warn", evidence, "人工核对 LLM runtime contract 后重新生成完整性审计。")
    return _item("llm", "runtime_contract", "pass", evidence, "无需处理。")


def _secret_persistence_check(run_config: dict[str, Any]) -> dict[str, Any]:
    if not run_config:
        return _item("security", "run_config_secret", "warn", "run-config.json 缺失或不可读，无法确认 API key 是否落盘。", "确认 Web/CLI 恢复配置不保存 API key。")
    llm = run_config.get("llm") if isinstance(run_config.get("llm"), dict) else {}
    if str(llm.get("api_key") or ""):
        return _item("security", "run_config_secret", "block", "run-config.json 中 llm.api_key 非空。", "立即清除落盘 API key，并改用环境变量或一次性表单输入。")
    literature = run_config.get("literature") if isinstance(run_config.get("literature"), dict) else {}
    leaked = [
        key
        for key in ["semantic_scholar_api_key", "openalex_api_key", "contact_email"]
        if str(literature.get(key) or "").strip()
    ]
    if leaked:
        return _item("security", "run_config_secret", "block", f"run-config.json 中 literature 字段包含敏感值：{', '.join(leaked)}。", "立即清除落盘文献源凭据/邮箱，并改用环境变量或一次性表单输入。")
    return _item("security", "run_config_secret", "pass", "run-config.json 未保存 API key 或文献源凭据。", "无需处理。")


def _manifest_hash_issues(run_dir: Path, artifacts: list[Any]) -> list[str]:
    issues: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        expected = str(item.get("sha256") or "")
        if rel in {"run-manifest.json", "run-manifest.md"}:
            continue
        if not rel or not expected:
            continue
        path = run_dir / rel
        if not path.exists() or not path.is_file():
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        if digest != expected:
            issues.append(rel)
    return issues


def _active_events(run_dir: Path, manifest: dict[str, Any]) -> list[Any]:
    """Manifest events that may back current-revision evidence (REV-01).

    After a rollback, success events from older revisions must not satisfy
    gate-order or freshness checks for the active revision.
    """
    events = manifest.get("events") if isinstance(manifest.get("events"), list) else []
    return filter_active_events(events, active_revision(run_dir))


def _first_event_index(events: list[Any], stages: set[str]) -> int | None:
    for index, event in enumerate(events):
        if isinstance(event, dict) and str(event.get("stage") or "") in stages:
            return index
    return None


def _last_event_index(events: list[Any], stages: set[str]) -> int | None:
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if isinstance(event, dict) and str(event.get("stage") or "") in stages:
            return index
    return None


def _event_stage(event: Any) -> str:
    return str(event.get("stage") or "unknown") if isinstance(event, dict) else "unknown"


def _recommended_actions(items: list[dict[str, Any]]) -> list[str]:
    actions = [str(item.get("action") or "") for item in items if item.get("status") in {"block", "warn"} and item.get("action")]
    return _dedupe(actions) or ["归档该 run；开启新课题时继续保留人工文献 gate 和最终完整性审计。"]


def _overall_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "") for item in items}
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _item(category: str, name: str, status: str, evidence: str, action: str, artifacts: list[str] | None = None) -> dict[str, Any]:
    return {"category": category, "name": name, "status": status, "evidence": evidence, "action": action, "artifacts": artifacts or []}


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


