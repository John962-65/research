from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .models import IterationPlanItem, IterationPlanReport


ITERATION_PLAN_JSON = "12-next-iteration-plan.json"
ITERATION_PLAN_MD = "12-next-iteration-plan.md"


def write_iteration_plan_artifacts(topic: str, run_dir: Path) -> IterationPlanReport:
    report = build_iteration_plan_report(topic, run_dir)
    write_json(run_dir / ITERATION_PLAN_JSON, report)
    write_text(run_dir / ITERATION_PLAN_MD, render_iteration_plan_markdown(report))
    return report


def build_iteration_plan_report(topic: str, run_dir: Path) -> IterationPlanReport:
    final_readiness = _read_json(run_dir / "10-final-readiness.json")
    availability = _read_json(run_dir / "10-code-data-availability.json")
    release = _read_json(run_dir / "10-release-metadata.json")
    submission = _read_json(run_dir / "10-submission-check.json")
    package = _read_json(run_dir / "11-submission-package.json")
    final_handoff = _read_json(run_dir / "14-final-handoff.json")
    runbook = _read_json(run_dir / "04-experiment-runbook.json")
    benchmark = _read_json(run_dir / "03-benchmark-plan.json")
    adapter = _read_json(run_dir / "03-benchmark-adapters.json")
    result_validation = _read_json(run_dir / "04-result-validation.json")
    failure_analysis = _read_json(run_dir / "04-failure-analysis.json")
    experiment_decision = _read_json(run_dir / "04-experiment-decision.json")
    experiment_manager = _read_json(run_dir / "02-experiment-manager.json")
    hypothesis_outcome = _read_json(run_dir / "04-hypothesis-outcome.json")
    claim_preflight = _read_json(run_dir / "04-claim-boundary-preflight.json")
    revision_response = _read_json(run_dir / "09-revision-response-audit.json")
    citation_coverage = _read_json(run_dir / "10-citation-coverage.json")
    claim_consistency = _read_json(run_dir / "10-claim-consistency.json")
    literature_rescue = _read_json(run_dir / "01-literature-rescue-plan.json")
    seed_intake = _read_json(run_dir / "01-seed-paper-intake.json")
    items = _build_items(final_readiness, availability, release, submission, package, final_handoff, runbook, benchmark, adapter, result_validation, failure_analysis, experiment_decision, experiment_manager, hypothesis_outcome, claim_preflight, revision_response, citation_coverage, claim_consistency, literature_rescue, seed_intake)
    status = _status(items, final_readiness, package, final_handoff)
    decision = _decision(status, items)
    return IterationPlanReport(
        topic=topic,
        status=status,
        decision=decision,
        final_readiness_status=_field(final_readiness, "status"),
        availability_status=_field(availability, "status"),
        submission_status=_field(submission, "status"),
        package_status=_field(package, "status"),
        execution_mode=_execution_mode(runbook),
        benchmark_status=_benchmark_status(benchmark, adapter),
        items=items,
        rerun_commands=_rerun_commands(status),
        stop_conditions=_stop_conditions(status),
        carry_forward_notes=_carry_forward_notes(final_readiness, availability, release, submission, package, final_handoff, runbook, benchmark, adapter, result_validation, failure_analysis, experiment_decision, experiment_manager, hypothesis_outcome, claim_preflight, revision_response, citation_coverage, claim_consistency, literature_rescue, seed_intake),
    )


def render_iteration_plan_markdown(report: IterationPlanReport) -> str:
    lines = [
        f"# 下一轮迭代计划：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 决策：{report.decision}",
        f"- 最终 Gate：{report.final_readiness_status or '未审计'}",
        f"- 代码/数据：{report.availability_status or '未审计'}",
        f"- 投稿格式：{report.submission_status or '未审计'}",
        f"- 投稿包：{report.package_status or '未审计'}",
        f"- 实验模式：{report.execution_mode or '未知'}",
        f"- Benchmark：{report.benchmark_status or '未知'}",
        "",
        "## 优先任务",
        "| 优先级 | 类别 | 负责人 | 自动化 | 目标产物 | 动作 | 理由 |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
    ]
    if report.items:
        for item in sorted(report.items, key=lambda value: value.priority):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.priority),
                        _cell(item.category),
                        _cell(item.owner),
                        _cell(item.automation),
                        _cell(", ".join(item.target_artifacts) or "-"),
                        _cell(item.action),
                        _cell(item.rationale),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | 暂无自动生成任务 | - |")
    lines.extend(["", "## 建议重跑命令"])
    lines.extend(f"- `{item}`" for item in report.rerun_commands) if report.rerun_commands else lines.append("- 暂无")
    lines.extend(["", "## 停止条件"])
    lines.extend(f"- {item}" for item in report.stop_conditions)
    lines.extend(["", "## 继承说明"])
    lines.extend(f"- {item}" for item in report.carry_forward_notes) if report.carry_forward_notes else lines.append("- 无")
    return "\n".join(lines)


def _build_items(
    final_readiness: dict[str, Any],
    availability: dict[str, Any],
    release: dict[str, Any],
    submission: dict[str, Any],
    package: dict[str, Any],
    final_handoff: dict[str, Any],
    runbook: dict[str, Any],
    benchmark: dict[str, Any],
    adapter: dict[str, Any],
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    experiment_decision: dict[str, Any],
    experiment_manager: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    claim_preflight: dict[str, Any],
    revision_response: dict[str, Any],
    citation_coverage: dict[str, Any],
    claim_consistency: dict[str, Any],
    literature_rescue: dict[str, Any],
    seed_intake: dict[str, Any],
) -> list[IterationPlanItem]:
    items: list[IterationPlanItem] = []
    rescue_status = _field(literature_rescue, "status")
    if rescue_status in {"block", "needs_source_repair", "needs_rescue_search", "needs_manual_seed"}:
        items.append(
            _item(
                8,
                "literature",
                "先修复弱文献：执行补检索、补 seed paper 或修复文献源后重新生成审核 gate。",
                f"01-literature-rescue-plan.json 状态为 {rescue_status}，继续写作会把弱证据带入 idea、实验和论文。",
                ["01-literature-rescue-plan.md", "01-review-gate.md"],
                "human+agent",
            )
        )
    seed_status = _field(seed_intake, "status")
    seed_role_status = _field(seed_intake, "role_coverage_status")
    if seed_status in {"block", "review_required"}:
        items.append(
            _item(
                9,
                "literature",
                "修复人工 seed 文献输入，确保核心 DOI/URL 进入 curated context。",
                f"01-seed-paper-intake.json 状态为 {seed_status}，说明人工 seed 尚未可靠约束文献上下文。",
                ["01-seed-paper-intake.md", "01-literature-quality.md", "01-literature-curated.md"],
                "human+agent",
            )
        )
    elif seed_role_status == "review_required":
        missing_roles = seed_intake.get("missing_curated_seed_roles") if isinstance(seed_intake.get("missing_curated_seed_roles"), list) else []
        items.append(
            _item(
                9,
                "literature",
                "补齐人工 seed 的角色覆盖，确保 curated context 至少覆盖 3 类核心文献角色。",
                f"01-seed-paper-intake.json role_coverage_status={seed_role_status}；缺失角色={', '.join(str(item) for item in missing_roles[:4]) or '-'}。",
                ["01-seed-paper-intake.md", "01-literature-quality.md", "01-literature-curated.md"],
                "human+agent",
            )
        )

    validation_status = _field(result_validation, "status")
    if validation_status == "block":
        items.append(
            _item(
                12,
                "experiment",
                "修复 04-result-validation 的阻断项并重跑实验统计。",
                "实验结果有效性验证未通过，当前结果不足以支撑论文分析。",
                ["04-result-validation.md", "04-results.json", "04-statistics.md"],
                "agent+human",
            )
        )
    elif validation_status == "warn":
        items.append(
            _item(
                44,
                "experiment",
                "处理 04-result-validation warning，并把剩余限制写入论文局限性。",
                "实验结果存在警告，下一轮需要补重复、补共同指标或人工核对统计解释。",
                ["04-result-validation.md", "05-analysis.md"],
                "agent+human",
            )
        )

    failure_status = _field(failure_analysis, "status")
    if failure_status == "block":
        items.append(
            _item(
                13,
                "experiment_failure",
                "修复失败/超时/阻断运行，重跑后再写分析和论文。",
                "04-failure-analysis.json 显示实验失败会阻断主张生成。",
                ["04-failure-analysis.md", "04-experiment-runbook.md"],
                "agent+human",
            )
        )
    elif failure_status == "warn":
        items.append(
            _item(
                43,
                "experiment_failure",
                "处理负结果和不确定指标，必要时增加重复或降级论文结论。",
                "04-failure-analysis.json 显示候选不优于基线、CI 不稳定或仍为模拟证据。",
                ["04-failure-analysis.md", "05-analysis.md", "09-revised-paper.md"],
                "agent+human",
            )
        )

    decision = _field(experiment_decision, "decision")
    if decision == "repair_before_writing":
        items.append(
            _item(
                11,
                "experiment_decision",
                "按实验后决策先修复验证/失败项，再重新进入分析和论文写作。",
                "04-experiment-decision.json 判定当前结果不应直接进入效果主张。",
                ["04-experiment-decision.md", "04-result-validation.md", "04-failure-analysis.md"],
                "agent+human",
            )
        )
    elif decision == "pivot_or_refine":
        items.append(
            _item(
                38,
                "experiment_decision",
                "围绕负向指标做方法 pivot 或实验 refine，并把负结果写入下一版论文。",
                "实验后决策显示候选不优于 baseline，继续只写正结果会失真。",
                ["04-experiment-decision.md", "02-ideas.md", "03-experiment-plan.md"],
                "human+agent",
            )
        )
    elif decision in {"refine_experiment", "benchmark_upgrade"}:
        items.append(
            _item(
                39,
                "experiment_decision",
                "按实验后决策补重复、补任务或升级 benchmark 后再收窄结论。",
                "当前实验仍是初步趋势或 smoke 证据。",
                ["04-experiment-decision.md", "03-benchmark-plan.md", "04-statistics.md"],
                "human+agent",
            )
        )

    manager_status = _field(experiment_manager, "status")
    if manager_status == "block":
        items.append(
            _item(
                11,
                "experiment_manager",
                "修复 experiment manager 阻断项：人工改选分支、修正 idea audit，或重新生成探索图和实验管理策略。",
                "02-experiment-manager.json 判定当前选中分支不能安全进入实验计划。",
                ["02-experiment-manager.md", "02-exploration-map.md", "03-experiment-plan.md"],
                "human+agent",
            )
        )

    hypothesis_status = _field(hypothesis_outcome, "status")
    hypothesis_decision = _field(hypothesis_outcome, "outcome")
    if hypothesis_status == "block" or hypothesis_decision in {"blocked_unverified", "untested"}:
        items.append(
            _item(
                14,
                "hypothesis",
                "先补齐 hypothesis outcome 所需实验和统计比较，再进入论文主结论写作。",
                "04-hypothesis-outcome.json 显示原始假设尚未被有效检验。",
                ["04-hypothesis-outcome.md", "04-result-validation.md", "04-statistics.md"],
                "agent+human",
            )
        )
    elif hypothesis_status == "review_required" or hypothesis_decision in {"partially_supported", "refuted_or_negative", "inconclusive", "smoke_only"}:
        items.append(
            _item(
                41,
                "hypothesis",
                "按假设结果审计收窄论文主张，并规划下一轮验证或 pivot。",
                f"当前 hypothesis outcome={hypothesis_decision or '-'}，不能直接写成完整支持假设。",
                ["04-hypothesis-outcome.md", "09-revised-paper.md", "12-next-iteration-plan.md"],
                "agent+human",
            )
        )

    preflight_status = _field(claim_preflight, "status")
    preflight_mode = _field(claim_preflight, "writing_mode")
    if preflight_status == "block":
        items.append(
            _item(
                15,
                "claim_boundary_preflight",
                "按写作前 claim 边界预检修复实验证据，或把论文改为诊断/修复报告。",
                "04-claim-boundary-preflight.json 在写作前已判定当前结果不能支撑正常效果论文。",
                ["04-claim-boundary-preflight.md", "04-result-validation.md", "06-paper.md"],
                "agent+human",
            )
        )
    elif preflight_status == "review_required":
        items.append(
            _item(
                42,
                "claim_boundary_preflight",
                "把 allowed/prohibited claim 和 required boundary statements 带入下一版论文。",
                f"写作前 claim 预检为 {preflight_mode or 'limited'}，需要人工确认结论强度。",
                ["04-claim-boundary-preflight.md", "06-paper.md", "09-revised-paper.md"],
                "agent+human",
            )
        )

    revision_response_status = _field(revision_response, "status")
    if revision_response_status == "block":
        items.append(
            _item(
                17,
                "revision",
                "修复审稿任务回应闭环：补齐缺失 result、正文任务痕迹或高优先级待补证说明。",
                "09-revision-response-audit.json 显示修订计划和修订稿之间存在阻断性断点。",
                ["09-revision-response-audit.md", "09-revision-report.md", "09-revised-paper.md"],
                "agent+human",
            )
        )
    elif revision_response_status == "review_required":
        items.append(
            _item(
                47,
                "revision",
                "人工关闭修订响应审计中的 needs_human_evidence / needs_human_verification 任务。",
                "09-revision-response-audit.json 仍有待补证或待人工核对的审稿任务回应。",
                ["09-revision-response-audit.md", "09-revised-paper.md"],
                "human",
            )
        )

    citation_coverage_status = _field(citation_coverage, "status")
    if citation_coverage_status == "block":
        items.append(
            _item(
                19,
                "citation_coverage",
                "修复正文 citation 覆盖阻断项：未知 key、缺失 citation marker 或 context 覆盖过低。",
                "10-citation-coverage.json 显示文献 context 没有可靠进入修订稿正文。",
                ["10-citation-coverage.md", "09-revised-paper.md", "01-context.md"],
                "agent+human",
            )
        )
    elif citation_coverage_status == "review_required":
        items.append(
            _item(
                48,
                "citation_coverage",
                "把高相关、近年或核心 baseline/benchmark 文献补入正文，降低 citation 过度集中。",
                "10-citation-coverage.json 需要人工复核 context 文献覆盖和引用分布。",
                ["10-citation-coverage.md", "09-revised-paper.md"],
                "agent+human",
            )
        )

    consistency_status = _field(claim_consistency, "status")
    if consistency_status == "block":
        items.append(
            _item(
                18,
                "revision",
                "删除或降级与 hypothesis outcome 不一致的过强结论。",
                "10-claim-consistency.json 显示论文结论强度超过了当前假设结果证据等级。",
                ["10-claim-consistency.md", "04-hypothesis-outcome.md", "09-revised-paper.md"],
                "agent+human",
            )
        )
    elif consistency_status == "review_required":
        items.append(
            _item(
                46,
                "revision",
                "人工复核 claim consistency 待办，确认负结果、smoke-only 或部分支持没有被写成正式支持。",
                "10-claim-consistency.json 需要人工核对结论边界。",
                ["10-claim-consistency.md", "09-revised-paper.md"],
                "human",
            )
        )

    final_status = _field(final_readiness, "status")
    if not final_status:
        items.append(_item(10, "final_gate", "重新生成最终就绪报告。", "缺少 10-final-readiness.json，无法判断研究闭环状态。", ["10-final-readiness.md"], "agent"))
    elif final_status == "requires_human_evidence":
        items.append(_item(10, "evidence", "补齐人工证据、真实实验或删除 unsupported claim。", "最终 gate 明确要求人工证据，继续自动写作会放大不可支撑结论。", ["09-revision-report.md", "10-final-readiness.md"], "human"))
    elif final_status == "requires_revision":
        items.append(_item(20, "revision", "执行下一轮 claim-grounding 修订并重新复核。", "修订稿仍有 weak claim、低分或审计阻断项。", ["08-revision-plan.md", "09-revised-paper.md", "10-revised-paper-review.md"], "agent+human"))
    elif final_status == "ready_for_human_polish":
        items.append(_item(50, "polish", "做语言、图表、引用和格式人工润色。", "自动复核未发现硬阻断，但仍未达到完全投稿状态。", ["09-revised-paper.md", "10-final-readiness.md"], "human"))

    if _field(availability, "status") == "blocked":
        items.append(_item(15, "release", "修复代码/数据可用性阻断项。", "没有可用性材料时无法形成可复现实验交付物。", ["10-code-data-availability.md"], "human"))
    elif _field(availability, "status") == "needs_human_release_metadata":
        items.append(_item(35, "release", "补齐仓库 URL、许可证、数据访问说明和归档 DOI。", "代码/数据发布元数据仍需人工确认。", ["10-code-data-availability.md", "submission-package/CHECKLIST.md"], "human"))
    if _field(release, "status") == "blocked":
        items.append(_item(16, "release", "修复 release metadata 中的 URL/DOI 格式阻断项。", "发布元数据格式错误会导致论文声明和归档包不可用。", ["10-release-metadata.md"], "human"))
    elif _field(release, "status") == "needs_release_metadata":
        items.append(_item(34, "release", "补齐结构化 release metadata。", "仓库、许可证、版本、归档 DOI 或数据访问说明仍缺失。", ["10-release-metadata.md"], "human"))

    if _field(submission, "status") == "blocked":
        items.append(_item(25, "format", "修复 TeX、参考文献或必需章节阻断项。", "投稿格式检查未通过，当前稿件无法作为正式上传材料。", ["10-submission-check.md"], "human"))
    elif _field(submission, "status") == "needs_human_format_check":
        items.append(_item(45, "format", "套用目标会议/期刊官方模板并核对匿名、页数和参考文献样式。", "当前 TeX 仍是通用骨架或需要目标 venue 人工核对。", ["10-submission-check.md", "09-revised-paper.tex"], "human"))

    if _field(package, "status") == "blocked":
        items.append(_item(30, "package", "补齐投稿包缺失文件后重新生成 ZIP。", "投稿/归档包仍有必需文件缺失或无法复制。", ["11-submission-package.md", "11-submission-package.zip"], "agent+human"))
    elif _field(package, "status") == "needs_human_submission_review":
        items.append(_item(60, "package", "按 CHECKLIST 完成人工上传前核验。", "ZIP 已生成，但仍有上传前人工待办。", ["submission-package/CHECKLIST.md", "11-submission-package.zip"], "human"))

    handoff_status = _field(final_handoff, "status")
    if handoff_status == "blocked" or _handoff_zip_invalid(final_handoff):
        items.append(
            _item(
                31,
                "package",
                "修复最终交付 ZIP 后重新生成 run integrity 和 final handoff。",
                _handoff_package_rationale(final_handoff),
                ["11-submission-package.zip", "14-run-integrity-audit.md", "14-final-handoff.md"],
                "agent+human",
            )
        )

    if _execution_mode(runbook) == "simulated":
        items.append(_item(40, "benchmark", "把模拟实验替换为真实 benchmark 或记录模拟证据边界。", "当前结果来自模拟执行器，不能支撑强科学结论。", ["03-benchmark-plan.md", "04-experiment-runbook.md"], "human+agent"))
    if _benchmark_status(benchmark, adapter) in {"missing", "manual_required", "adapter_blocked"}:
        items.append(_item(42, "benchmark", "确认真实 benchmark、许可、数据入口和 baseline 接入步骤。", "公开 benchmark 是下一轮实验可信度的关键证据。", ["03-benchmark-plan.md"], "human"))

    return _dedupe_items(items)


def _item(priority: int, category: str, action: str, rationale: str, artifacts: list[str], owner: str, automation: str | None = None) -> IterationPlanItem:
    return IterationPlanItem(
        priority=priority,
        category=category,
        action=action,
        rationale=rationale,
        owner=owner,
        target_artifacts=artifacts,
        automation=automation or owner,
    )


def _status(items: list[IterationPlanItem], final_readiness: dict[str, Any], package: dict[str, Any], final_handoff: dict[str, Any]) -> str:
    categories = {item.category for item in items}
    if "literature" in categories:
        return "needs_literature_repair"
    if categories & {"experiment", "experiment_failure", "experiment_decision", "hypothesis"}:
        return "needs_experiment_repair"
    if "experiment_manager" in categories:
        return "needs_experiment_repair"
    if "evidence" in categories:
        return "needs_human_evidence"
    if "benchmark" in categories and _field(final_readiness, "status") in {"requires_human_evidence", "requires_revision", "ready_for_human_polish"}:
        return "needs_real_benchmark_iteration"
    if categories & {"revision", "citation_coverage", "release", "format", "package"}:
        return "needs_targeted_iteration"
    if _field(package, "status") == "ready_for_human_submission_upload" and not _handoff_zip_invalid(final_handoff) and _field(final_handoff, "status") != "blocked":
        return "ready_for_submission_upload"
    return "ready_for_next_research_question"


def _decision(status: str, items: list[IterationPlanItem]) -> str:
    if status == "needs_literature_repair":
        return "暂停自动推进，先补检索或修复文献源，再重新生成审核 gate。"
    if status == "needs_experiment_repair":
        return "下一轮优先修复实验失败、结果验证或负结果边界，再重新分析和修订论文。"
    if status == "needs_human_evidence":
        return "暂停自动推进，先补证据或删除无法支撑的 claim。"
    if status == "needs_real_benchmark_iteration":
        return "下一轮优先接入真实 benchmark，再重跑实验、修订和最终审计。"
    if status == "needs_targeted_iteration":
        return "按优先级处理阻断项，然后从 checkpoint resume 重跑后半段流水线。"
    if status == "ready_for_submission_upload":
        return "可以进入人工投稿系统上传，但仍需完成最终人工核验。"
    return "当前课题闭环已足够稳定，可以保留产物并开启新研究问题。"


def _rerun_commands(status: str) -> list[str]:
    if status in {"needs_literature_repair", "needs_experiment_repair", "needs_human_evidence", "needs_real_benchmark_iteration", "needs_targeted_iteration"}:
        return [
            "PYTHONPATH=src python3 -m research_agent resume <run_dir> --llm-model \"$OPENAI_MODEL\"",
            "PYTHONPATH=src python3 -m research_agent summary --runs-dir runs --limit 20",
        ]
    if status == "ready_for_submission_upload":
        return ["下载 11-submission-package.zip 并按目标 venue 官方系统上传。"]
    return ["PYTHONPATH=src python3 -m research_agent run --topic \"<next topic>\" --llm-model \"$OPENAI_MODEL\""]


def _stop_conditions(status: str) -> list[str]:
    if status == "needs_literature_repair":
        return [
            "01-literature-rescue-plan.json 状态为 pass，或 approval.json 中记录了明确人工豁免理由。",
            "01-seed-paper-intake.json 的 role_coverage_status 不再是 review_required，或 approval.json 中记录了明确人工豁免理由。",
            "01-review-gate.md 不再列出必须补检索或文献源修复动作。",
        ]
    if status == "needs_experiment_repair":
        return [
            "04-result-validation.json 不再是 block。",
            "04-failure-analysis.json 不再是 block，且 warn 项已进入论文局限性或下一轮实验设计。",
        ]
    if status == "needs_human_evidence":
        return [
            "所有 unsupported claim 已删除或有可核验证据支撑。",
            "真实实验或引用补充后，10-final-readiness.json 不再是 requires_human_evidence。",
        ]
    if status == "needs_real_benchmark_iteration":
        return [
            "04-experiment-runbook.json 显示执行模式或产物已能代表真实 benchmark，而不是仅 simulated smoke。",
            "10-revised-paper-review.json 中 unsupported claim 为 0。",
        ]
    if status == "needs_targeted_iteration":
        return [
            "10-code-data-availability.json 无 blocking issues。",
            "10-submission-check.json 无 block 项。",
            "11-submission-package.json 无 blocking issues。",
            "14-final-handoff.json 未报告 ZIP 缺失或无效。",
        ]
    if status == "ready_for_submission_upload":
        return [
            "submission-package/CHECKLIST.md 已人工勾选完成。",
            "投稿系统回执、版本号或归档 DOI 已记录。",
        ]
    return ["当前 run 的核心产物已归档，下一轮研究问题应重新走人工文献审核 gate。"]


def _carry_forward_notes(
    final_readiness: dict[str, Any],
    availability: dict[str, Any],
    release: dict[str, Any],
    submission: dict[str, Any],
    package: dict[str, Any],
    final_handoff: dict[str, Any],
    runbook: dict[str, Any],
    benchmark: dict[str, Any],
    adapter: dict[str, Any],
    result_validation: dict[str, Any],
    failure_analysis: dict[str, Any],
    experiment_decision: dict[str, Any],
    experiment_manager: dict[str, Any],
    hypothesis_outcome: dict[str, Any],
    claim_preflight: dict[str, Any],
    revision_response: dict[str, Any],
    citation_coverage: dict[str, Any],
    claim_consistency: dict[str, Any],
    literature_rescue: dict[str, Any],
    seed_intake: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    notes.extend(_prefixed_list("文献补检索", literature_rescue.get("required_actions"), 4))
    notes.extend(_prefixed_list("Seed intake", seed_intake.get("required_actions"), 4))
    if _field(seed_intake, "role_coverage_status") == "review_required":
        missing_roles = seed_intake.get("missing_curated_seed_roles") if isinstance(seed_intake.get("missing_curated_seed_roles"), list) else []
        notes.append(f"Seed intake: 角色覆盖不足，缺失 {', '.join(str(item) for item in missing_roles[:4]) or '-'}")
    notes.extend(_prefixed_list("结果验证", result_validation.get("blocking_issues"), 4))
    notes.extend(_prefixed_list("结果验证", result_validation.get("warnings"), 4))
    notes.extend(_prefixed_list("失败分析", failure_analysis.get("required_actions"), 4))
    notes.extend(_prefixed_list("实验后决策", experiment_decision.get("next_actions"), 4))
    notes.extend(_experiment_manager_notes(experiment_manager))
    notes.extend(_prefixed_list("假设结果", hypothesis_outcome.get("next_actions"), 4))
    notes.extend(_prefixed_list("Claim preflight", claim_preflight.get("required_actions"), 4))
    notes.extend(_prefixed_list("Claim preflight", claim_preflight.get("blocking_issues"), 4))
    notes.extend(_prefixed_list("Claim preflight", claim_preflight.get("warnings"), 4))
    notes.extend(_prefixed_list("Revision response", revision_response.get("blocking_issues"), 4))
    notes.extend(_prefixed_list("Revision response", revision_response.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("Citation coverage", citation_coverage.get("blocking_issues"), 4))
    notes.extend(_prefixed_list("Citation coverage", citation_coverage.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("Claim consistency", claim_consistency.get("blocking_issues"), 4))
    notes.extend(_prefixed_list("Claim consistency", claim_consistency.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("最终 Gate", final_readiness.get("next_actions"), 4))
    notes.extend(_prefixed_list("代码/数据", availability.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("Release metadata", release.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("投稿格式", submission.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("投稿包", package.get("manual_tasks"), 4))
    notes.extend(_prefixed_list("最终交付", final_handoff.get("blocking_issues"), 4))
    notes.extend(_prefixed_list("最终交付", final_handoff.get("manual_tasks"), 4))
    warnings = runbook.get("warnings") if isinstance(runbook, dict) else []
    notes.extend(_prefixed_list("实验 runbook", warnings, 3))
    required = benchmark.get("required_actions") if isinstance(benchmark, dict) else []
    notes.extend(_prefixed_list("Benchmark", required, 3))
    notes.extend(_prefixed_list("Benchmark adapter", adapter.get("blocking_issues"), 3))
    notes.extend(_prefixed_list("Benchmark adapter", adapter.get("manual_tasks"), 3))
    return _dedupe(notes)


def _execution_mode(runbook: dict[str, Any]) -> str:
    execution = runbook.get("execution") if isinstance(runbook, dict) else {}
    return str(execution.get("mode") or "").strip() if isinstance(execution, dict) else ""


def _benchmark_status(benchmark: dict[str, Any], adapter: dict[str, Any] | None = None) -> str:
    if isinstance(adapter, dict) and adapter:
        adapter_status = _field(adapter, "status")
        if adapter_status == "ready":
            return "adapter_ready"
        if adapter_status == "blocked":
            return "adapter_blocked"
    if not benchmark:
        return "missing"
    selected = benchmark.get("selected_names")
    required = benchmark.get("required_actions")
    if isinstance(selected, list) and selected and isinstance(required, list) and not required:
        return "selected"
    return "manual_required"


def _experiment_manager_notes(manager: dict[str, Any]) -> list[str]:
    if not isinstance(manager, dict) or not manager:
        return []
    notes: list[str] = []
    selected = str(manager.get("selected_idea_title") or "").strip()
    policy = str(manager.get("execution_policy") or "").strip()
    decision = str(manager.get("manager_decision") or "").strip()
    if selected or policy:
        notes.append(f"Experiment manager: selected={selected or '-'}; decision={decision or '-'}; policy={policy or '-'}")
    constraints = manager.get("planning_constraints")
    if isinstance(constraints, list):
        notes.extend(f"Experiment manager constraint: {str(item).strip()}" for item in constraints[:4] if str(item).strip())
    candidates = manager.get("next_expansion_candidates")
    if isinstance(candidates, list):
        for item in candidates[:3]:
            if not isinstance(item, dict):
                continue
            branch = str(item.get("branch_id") or "").strip()
            title = str(item.get("title") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if title:
                notes.append(f"下一轮候选分支: {branch or '-'} {title}；{reason or '保留为候选'}")
    return notes


def _handoff_zip_invalid(handoff: dict[str, Any]) -> bool:
    if not isinstance(handoff, dict) or not handoff:
        return False
    return handoff.get("package_zip_valid") is False or handoff.get("package_zip_exists") is False


def _handoff_package_rationale(handoff: dict[str, Any]) -> str:
    if handoff.get("package_zip_valid") is False:
        return "14-final-handoff.json 明确报告 package_zip_valid=false，当前 ZIP 不能作为最终上传材料。"
    if handoff.get("package_zip_exists") is False:
        return "14-final-handoff.json 明确报告 package_zip_exists=false，最终交付 ZIP 缺失。"
    blockers = handoff.get("blocking_issues") if isinstance(handoff.get("blocking_issues"), list) else []
    if blockers:
        return str(blockers[0])
    return "14-final-handoff.json 为 blocked，最终交付尚未闭环。"


def _field(data: dict[str, Any], key: str) -> str:
    return str(data.get(key) or "").strip() if isinstance(data, dict) else ""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _prefixed_list(prefix: str, values: Any, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    return [f"{prefix}: {str(item).strip()}" for item in values[:limit] if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_items(items: list[IterationPlanItem]) -> list[IterationPlanItem]:
    seen: set[tuple[str, str]] = set()
    result: list[IterationPlanItem] = []
    for item in sorted(items, key=lambda value: value.priority):
        key = (item.category, item.action)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
