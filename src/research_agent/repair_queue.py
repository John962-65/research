from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .models import RepairQueueItem, RepairQueueReport
from .seed_paper_intake import build_seed_paper_suggestion_report


REPAIR_QUEUE_JSON = "12-repair-queue.json"
REPAIR_QUEUE_MD = "12-repair-queue.md"


AUDIT_SPECS: list[dict[str, Any]] = [
    {
        "source": "01-literature-metadata-audit.json",
        "category": "literature_metadata",
        "block_statuses": {"block"},
        "high_statuses": {"literature_repair_required", "review_required"},
        "block_count_fields": ["blocked"],
        "high_count_fields": ["review_required"],
        "action": "替换低可信题录或补齐 DOI/URL/作者/年份/摘要后重新生成 context。",
        "target_artifacts": ["01-literature-curated.md", "01-context.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-rescue-plan.json",
        "category": "literature_rescue",
        "block_statuses": {"block", "needs_source_repair"},
        "high_statuses": {"needs_rescue_search", "needs_manual_seed"},
        "action": "执行补检索、补 seed paper 或修复文献源后重新跑文献 gate。",
        "target_artifacts": ["01-literature-rescue-plan.md", "01-literature-rescue-execution.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-rescue-execution.json",
        "category": "literature_rescue_execution",
        "high_statuses": {"no_new_papers"},
        "action": "补检索执行未改善候选池；调整 query、修复 source 或补 DOI/URL seed 后重新跑文献 gate。",
        "target_artifacts": ["01-literature-rescue-execution.md", "01-literature-search-feedback.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-search-feedback.json",
        "category": "literature_search_feedback",
        "block_statuses": {"needs_source_repair"},
        "high_statuses": {"needs_search_revision", "needs_manual_seed"},
        "action": "关闭检索修复任务：修复 source、执行补检索式、补 DOI/URL seed 后重新生成文献 gate。",
        "target_artifacts": ["01-literature-search-feedback.md", "01-literature-rerank.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-search-strategy.json",
        "category": "literature_search_strategy",
        "block_statuses": {"needs_query_repair"},
        "high_statuses": {"review_required"},
        "action": "修复 selected query 的必需 intent 覆盖、过宽查询和来源配置后重新检索。",
        "target_artifacts": ["01-literature-search-strategy.md", "01-query-execution-audit.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-query-execution-audit.json",
        "category": "query_execution",
        "block_statuses": {"needs_source_repair"},
        "high_statuses": {"needs_query_repair", "review_required"},
        "action": "修复 selected query 的 source 返回、intent 覆盖和 top rerank 覆盖后重新生成文献 gate。",
        "target_artifacts": ["01-query-execution-audit.md", "01-literature-source-health.md", "01-literature-rerank.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-evidence-mix.json",
        "category": "literature_evidence_mix",
        "block_statuses": {"block"},
        "high_statuses": {"needs_evidence_upgrade", "review_required"},
        "action": "补齐综述/高引用、benchmark/dataset、baseline/method 和近期研究 anchor 后重新生成 review gate。",
        "target_artifacts": ["01-literature-evidence-mix.md", "01-literature-curated.md", "01-review-gate.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-seed-paper-intake.json",
        "category": "seed_papers",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "extra_status_fields": ["role_coverage_status"],
        "action": "修复人工 seed 文献输入，让核心 DOI/URL 进入 curated context。",
        "target_artifacts": ["01-seed-paper-intake.md", "01-literature-quality.md", "01-context.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-citation-audit.json",
        "category": "citation_integrity",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocked_citations"],
        "high_count_fields": ["review_citations"],
        "extra_status_fields": ["integrity_status"],
        "action": "修复不可核对或不可引用的 citation，再重新生成 context 和后续论文。",
        "target_artifacts": ["01-citation-audit.md", "01-context.md", "09-revised-paper.md"],
        "rerun_from": "literature_context",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-gate-decision.json",
        "category": "literature_rag_gate",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_reasons"],
        "high_count_fields": ["review_reasons", "required_actions"],
        "action": "修复文献总门禁中的检索、RAG context、seed 或 citation grounding 问题；未通过前不要进入 idea/实验。",
        "target_artifacts": ["01-literature-gate-decision.md", "01-context.md", "10-citation-grounding.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "01-literature-evidence-contract.json",
        "category": "literature_evidence_contract",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["review_reasons", "required_actions"],
        "action": "修复进入 context 的文献证据契约：补 DOI/URL seed、降低单源 Crossref、补全文 chunk 或补齐证据角色后重跑文献 gate。",
        "target_artifacts": ["01-literature-evidence-contract.md", "01-context.md", "01-literature-gate-decision.md"],
        "rerun_from": "literature_review",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "02-idea-audit.json",
        "category": "idea_evidence",
        "block_statuses": {"block"},
        "high_statuses": {"review", "review_required"},
        "block_count_fields": ["blocked"],
        "high_count_fields": ["review_required"],
        "action": "补齐选中 idea 的证据、baseline、metric 或实验草案。",
        "target_artifacts": ["02-idea-audit.md", "02-exploration-map.md", "02-experiment-manager.md", "03-experiment-plan.md"],
        "rerun_from": "ideation",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "02-experiment-manager.json",
        "category": "experiment_manager",
        "block_statuses": {"block"},
        "action": "修复选中分支阻断、人工改选或重新生成实验管理策略。",
        "target_artifacts": ["02-experiment-manager.md", "02-exploration-map.md", "03-experiment-plan.md"],
        "rerun_from": "ideation",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "03-review-constraint-compliance.json",
        "category": "review_constraints",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocked"],
        "high_count_fields": ["review_required"],
        "action": "把人工审核约束落实到选中 idea 和实验计划。",
        "target_artifacts": ["03-review-constraint-compliance.md", "02-ideas.md", "03-experiment-plan.md"],
        "rerun_from": "experiment_plan",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "03-experiment-audit.json",
        "category": "experiment_plan",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "action": "修复实验计划审计中的阻断项或警告，再允许执行。",
        "target_artifacts": ["03-experiment-audit.md", "03-experiment-plan.md"],
        "rerun_from": "experiment_plan",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "03-idea-experiment-contract.json",
        "category": "idea_experiment_contract",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks"],
        "action": "修复选中 idea 到实验计划的证据、baseline、metric、命令和 benchmark 契约后再执行。",
        "target_artifacts": ["03-idea-experiment-contract.md", "02-exploration-map.md", "02-experiment-manager.md", "03-experiment-plan.md"],
        "rerun_from": "experiment_plan",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "03-benchmark-readiness.json",
        "category": "benchmark_readiness",
        "block_statuses": {"block"},
        "high_statuses": {"needs_benchmark_upgrade"},
        "action": "修复 benchmark manifest/adapter、metric/baseline 对齐或切换真实 benchmark 模式。",
        "target_artifacts": ["03-benchmark-readiness.md", "03-benchmark-plan.md", "03-execution-approval.md"],
        "rerun_from": "experiment_plan",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "03-execution-safety-audit.json",
        "category": "execution_safety",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "action": "修复命令白名单、安全风险或执行配置后再申请执行确认。",
        "target_artifacts": ["03-execution-safety-audit.md", "03-execution-approval.md"],
        "rerun_from": "experiment_plan",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "04-result-validation.json",
        "category": "result_validation",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "action": "修复实验结果有效性问题并重跑统计。",
        "target_artifacts": ["04-result-validation.md", "04-results.json", "04-statistics.md"],
        "rerun_from": "experiments",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "04-benchmark-result-schema-audit.json",
        "category": "benchmark_result_schema",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks", "warnings"],
        "action": "修复 result schema、candidate/baseline/ablation 角色、统计比较、benchmark artifact contract 或 manifest provenance 后重跑实验。",
        "target_artifacts": ["04-benchmark-result-schema-audit.md", "04-results.json", "04-experiment-runbook.md", "04-statistics.md"],
        "rerun_from": "experiments",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "04-failure-analysis.json",
        "category": "experiment_failure",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "action": "修复失败、超时或负结果解释，必要时重跑实验。",
        "target_artifacts": ["04-failure-analysis.md", "04-experiment-runbook.md", "05-analysis.md"],
        "rerun_from": "experiments",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "04-environment-snapshot.json",
        "category": "environment_snapshot",
        "block_statuses": {"block"},
        "high_statuses": {"partial"},
        "high_count_fields": ["warnings"],
        "action": "补齐实验环境快照中的 Python、工具路径、包版本或源码哈希，再重新生成 runbook 和投稿包。",
        "target_artifacts": ["04-environment-snapshot.md", "04-experiment-runbook.md", "11-submission-package.md"],
        "rerun_from": "experiments",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "04-benchmark-evidence-audit.json",
        "category": "benchmark_evidence",
        "block_statuses": {"block"},
        "high_statuses": {"smoke_only", "review_required"},
        "block_values": {"evidence_grade": {"blocked"}},
        "high_values": {"evidence_grade": {"smoke_only", "local_experiment"}},
        "action": "把 smoke/local 证据升级为真实 benchmark，或在论文中降级结论。",
        "target_artifacts": ["03-benchmark-plan.md", "04-benchmark-evidence-audit.md", "04-experiment-decision.md"],
        "rerun_from": "experiments",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "04-experiment-decision.json",
        "category": "experiment_decision",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "block_values": {"decision": {"repair_before_writing"}},
        "high_values": {"decision": {"pivot_or_refine", "refine_experiment", "benchmark_upgrade"}},
        "action": "按实验后决策 repair/refine/pivot，再重写分析和论文结论。",
        "target_artifacts": ["04-experiment-decision.md", "05-analysis.md", "09-revised-paper.md"],
        "rerun_from": "analysis",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "04-hypothesis-outcome.json",
        "category": "hypothesis_outcome",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_values": {"outcome": {"blocked_unverified", "untested"}},
        "high_values": {"outcome": {"partially_supported", "refuted_or_negative", "inconclusive", "smoke_only"}},
        "action": "补齐假设检验、收窄主张或把负结果/pivot 写入下一轮计划。",
        "target_artifacts": ["04-hypothesis-outcome.md", "05-analysis.md", "09-revised-paper.md"],
        "rerun_from": "analysis",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "04-claim-boundary-preflight.json",
        "category": "claim_boundary_preflight",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["warnings"],
        "action": "按写作前 claim 边界预检修复实验证据或降级论文表述。",
        "target_artifacts": ["04-claim-boundary-preflight.md", "06-paper.md", "09-revised-paper.md"],
        "rerun_from": "analysis",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "07-paper-review-calibration.json",
        "category": "review_calibration",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "action": "校正过宽复核结论，补写修订任务或降低论文 ready 判定。",
        "target_artifacts": ["07-paper-review-calibration.md", "08-revision-plan.md", "09-revised-paper.md"],
        "rerun_from": "paper_revision_plan",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "09-revision-response-audit.json",
        "category": "revision_response",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks"],
        "action": "逐条关闭审稿任务回应：补 result、补正文任务痕迹或显式保留待补证/人工核对项。",
        "target_artifacts": ["09-revision-response-audit.md", "09-revision-report.md", "09-revised-paper.md"],
        "rerun_from": "paper_rewrite",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "13-llm-trace-audit.json",
        "category": "llm_trace_audit",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "action": "修复 LLM 配置、预算、缺失阶段调用或 AI disclosure 不一致后从 checkpoint 重跑。",
        "target_artifacts": ["run-llm-ledger.md", "13-llm-trace-audit.md", "10-ai-disclosure.md"],
        "rerun_from": "checkpoint",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "13-llm-runtime-contract.json",
        "category": "llm_runtime_contract",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks", "warnings"],
        "action": "修复模型配置、预算策略、密钥落盘、ledger 元数据或 AI disclosure 一致性后重新生成 LLM runtime contract。",
        "target_artifacts": ["13-llm-runtime-contract.md", "run-config.json", "run-llm-ledger.md", "10-ai-disclosure.md"],
        "rerun_from": "checkpoint",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "13-run-economics-audit.json",
        "category": "run_economics",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks", "warnings"],
        "action": "修复 LLM ledger、预算压力或 token 单价配置后重新生成运行成本审计。",
        "target_artifacts": ["13-run-economics-audit.md", "run-llm-ledger.md", "run-config.json"],
        "rerun_from": "checkpoint",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "13-agent-observability-audit.json",
        "category": "agent_observability",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks", "warnings"],
        "action": "修复 run manifest、LLM budget、human gate、实验 runbook、诊断恢复或 artifact trace 的可观测性缺口。",
        "target_artifacts": ["13-agent-observability-audit.md", "run-manifest.md", "run-llm-ledger.md", "04-experiment-runbook.md"],
        "rerun_from": "analysis",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "13-human-gate-audit.json",
        "category": "human_gate",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks"],
        "action": "修复未批准 review/execution gate 却进入下游的流程违规；从人工 gate 前重新批准并重跑受影响阶段。",
        "target_artifacts": ["13-human-gate-audit.md", "approval.json", "03-execution-approval.md", "12-repair-resume-plan.md"],
        "rerun_from": "literature_context",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
    {
        "source": "10-claim-traceability.json",
        "category": "claim_traceability",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocked_claims"],
        "high_count_fields": ["review_claims"],
        "action": "补齐 claim 到文献、结果、统计和 runbook 的证据链。",
        "target_artifacts": ["10-claim-traceability.md", "09-revised-paper.md"],
        "rerun_from": "paper_rewrite",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-citation-grounding.json",
        "category": "citation_grounding",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocked_citations"],
        "high_count_fields": ["review_citations"],
        "action": "修复正文 citation 附近 claim 与 context chunk 的支撑关系。",
        "target_artifacts": ["10-citation-grounding.md", "09-revised-paper.md", "01-context.md"],
        "rerun_from": "paper_rewrite",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-citation-coverage.json",
        "category": "citation_coverage",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks"],
        "action": "补齐 context 核心文献到正文的覆盖，修复未知 citation key 或 citation 过度集中问题。",
        "target_artifacts": ["10-citation-coverage.md", "09-revised-paper.md", "01-context.md"],
        "rerun_from": "paper_rewrite",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-results-presentation.json",
        "category": "results_presentation",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "action": "补齐结果章节、统计指标、图表引用和 CI/不确定性呈现。",
        "target_artifacts": ["10-results-presentation.md", "09-revised-paper.md", "04-statistics.md"],
        "rerun_from": "paper_rewrite",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-claim-consistency.json",
        "category": "claim_consistency",
        "block_statuses": {"block"},
        "high_statuses": {"review_required"},
        "action": "删除或降级与 hypothesis outcome、负结果或 smoke 证据不一致的过强结论。",
        "target_artifacts": ["10-claim-consistency.md", "09-revised-paper.md"],
        "rerun_from": "paper_rewrite",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-code-data-availability.json",
        "category": "code_data_availability",
        "block_statuses": {"blocked"},
        "high_statuses": {"needs_human_release_metadata"},
        "action": "补齐代码仓库、许可证、数据访问、环境或归档 DOI。",
        "target_artifacts": ["10-code-data-availability.md", "10-release-metadata.md", "submission-package/CHECKLIST.md"],
        "rerun_from": "final_readiness",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-release-metadata.json",
        "category": "release_metadata",
        "block_statuses": {"blocked"},
        "high_statuses": {"needs_release_metadata"},
        "action": "补齐 release metadata、版本、许可证和归档目标。",
        "target_artifacts": ["10-release-metadata.md", "10-code-data-availability.md"],
        "rerun_from": "final_readiness",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-submission-check.json",
        "category": "submission_format",
        "block_statuses": {"blocked"},
        "high_statuses": {"needs_human_format_check"},
        "action": "按目标 venue 官方模板、引用格式、页数和图表要求修复投稿检查。",
        "target_artifacts": ["10-submission-check.md", "09-revised-paper.tex", "submission-package/CHECKLIST.md"],
        "rerun_from": "final_readiness",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "10-final-readiness.json",
        "category": "final_readiness",
        "block_statuses": {"requires_human_evidence", "requires_revision"},
        "high_statuses": {"ready_for_human_polish"},
        "block_count_fields": ["unsupported_after", "deferred_tasks"],
        "high_count_fields": ["weak_after"],
        "action": "处理最终 gate 的 unsupported/weak claim 和延后任务。",
        "target_artifacts": ["10-final-readiness.md", "09-revised-paper.md", "10-revised-paper-review.md"],
        "rerun_from": "paper_rewrite",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "11-submission-package.json",
        "category": "submission_package",
        "block_statuses": {"blocked"},
        "high_statuses": {"needs_human_submission_review"},
        "action": "补齐投稿包缺失文件或完成 CHECKLIST 人工核验后重新生成 ZIP。",
        "target_artifacts": ["11-submission-package.md", "11-submission-package.zip", "submission-package/CHECKLIST.md"],
        "rerun_from": "submission_package",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "14-run-integrity-audit.json",
        "category": "run_integrity",
        "block_statuses": {"block"},
        "medium_statuses": {"warn"},
        "block_count_fields": ["blocking_issues"],
        "action": "修复最终完整性审计中的 artifact、manifest、hash、secret 或投稿包问题后重新生成完整性审计。",
        "target_artifacts": ["14-run-integrity-audit.md", "run-manifest.json", "11-submission-package.zip"],
        "rerun_from": "submission_package",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "14-final-handoff.json",
        "category": "final_handoff",
        "block_statuses": {"blocked"},
        "high_statuses": {"ready_for_human_handoff"},
        "block_values": {"package_zip_valid": {False}, "package_zip_exists": {False}},
        "extra_status_fields": ["package_zip_valid", "package_zip_exists", "package_status", "run_integrity_status"],
        "action": "修复最终 handoff 的 ZIP、scorecard、完整性审计或人工交付问题后重新生成最终交付清单。",
        "target_artifacts": ["14-final-handoff.md", "11-submission-package.zip", "11-submission-package.md", "14-run-integrity-audit.md"],
        "rerun_from": "submission_package",
        "automation": "human+agent",
        "blocks_submission": True,
        "blocks_downstream": False,
    },
    {
        "source": "13-open-source-compliance.json",
        "category": "open_source_compliance",
        "block_statuses": {"block"},
        "high_statuses": {"needs_human_review"},
        "block_count_fields": ["blocking_issues"],
        "high_count_fields": ["manual_tasks"],
        "action": "关闭 open-source lesson compliance 中未满足的外部项目约束后，再进入最终打包或下一轮。",
        "target_artifacts": ["13-open-source-compliance.md", "00-open-source-lessons.md", "13-agent-stage-contract.md"],
        "rerun_from": "checkpoint",
        "automation": "agent+human",
        "blocks_submission": True,
        "blocks_downstream": True,
    },
]


def write_repair_queue_artifacts(topic: str, run_dir: Path) -> RepairQueueReport:
    report = build_repair_queue_report(topic, run_dir)
    write_json(run_dir / REPAIR_QUEUE_JSON, report)
    write_text(run_dir / REPAIR_QUEUE_MD, render_repair_queue_markdown(report))
    return report


def build_repair_queue_report(topic: str, run_dir: Path) -> RepairQueueReport:
    candidates: list[RepairQueueItem] = []
    for spec in AUDIT_SPECS:
        data = _read_json(run_dir / str(spec["source"]))
        if not data:
            continue
        severity = _severity(data, spec, run_dir)
        if not severity:
            continue
        candidates.append(_candidate_item(len(candidates) + 1, data, spec, severity))
    seed_item = _seed_suggestion_item(topic, run_dir, len(candidates) + 1)
    if seed_item:
        candidates.append(seed_item)
    items = _dedupe_items(candidates)
    status = _status(items)
    summary = {
        "total": len(items),
        "block": sum(1 for item in items if item.severity == "block"),
        "high": sum(1 for item in items if item.severity == "high"),
        "medium": sum(1 for item in items if item.severity == "medium"),
        "blocks_submission": sum(1 for item in items if item.blocks_submission),
        "blocks_downstream": sum(1 for item in items if item.blocks_downstream),
        "human_tasks": sum(1 for item in items if "human" in item.automation),
        "agent_tasks": sum(1 for item in items if "agent" in item.automation),
    }
    blocking = [f"{item.task_id} {item.source_artifact}: {item.action}" for item in items if item.severity == "block"]
    manual = [f"{item.task_id} {item.source_artifact}: {item.action}" for item in items if "human" in item.automation and item.severity != "block"]
    return RepairQueueReport(
        topic=topic,
        status=status,
        summary=summary,
        items=items,
        blocking_issues=blocking,
        manual_tasks=manual,
        recommended_actions=_recommended_actions(status, items),
    )


def _seed_suggestion_item(topic: str, run_dir: Path, index: int) -> RepairQueueItem | None:
    if (run_dir / "01-seed-paper-intake.json").exists():
        return None
    suggestion = build_seed_paper_suggestion_report(topic, run_dir)
    missing = _values(suggestion, "missing_roles")
    if not suggestion.get("suggested_seed_count") or not missing:
        return None
    missing_text = ", ".join(str(item) for item in missing[:4]) or "-"
    queries = _values(suggestion, "role_repair_queries")
    return RepairQueueItem(
        task_id=f"RQ-{index:03d}",
        category="seed_papers",
        severity="high",
        source_artifact="01-seed-paper-intake.json",
        trigger_status=f"status=missing; suggested_seed_count={suggestion.get('suggested_seed_count')}; missing_roles={missing_text}",
        evidence="；".join(queries[:2]) or f"候选 seed 仍缺角色：{missing_text}",
        action="人工核对候选 DOI/URL seed，并补齐缺失 seed 角色：" + missing_text + "。",
        target_artifacts=["01-seed-paper-intake.md", "01-literature-quality.md", "01-context.md"],
        rerun_from="literature_review",
        automation="human+agent",
        blocks_submission=True,
        blocks_downstream=True,
    )


def render_repair_queue_markdown(report: RepairQueueReport) -> str:
    lines = [
        f"# 修复队列：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 总任务：{report.summary.get('total', 0)}",
        f"- block/high/medium：{report.summary.get('block', 0)}/{report.summary.get('high', 0)}/{report.summary.get('medium', 0)}",
        f"- 阻断投稿/下游：{report.summary.get('blocks_submission', 0)}/{report.summary.get('blocks_downstream', 0)}",
        "",
        "## 队列",
        "| ID | 严重级别 | 类别 | 来源 | 触发 | 自动化 | 阻断投稿 | 阻断下游 | 重跑入口 | 目标产物 | 动作 | 证据 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if report.items:
        for item in report.items:
            lines.append(
                "| "
                + " | ".join(
                    [
                        item.task_id,
                        item.severity,
                        _cell(item.category),
                        _cell(item.source_artifact),
                        _cell(item.trigger_status),
                        _cell(item.automation),
                        "是" if item.blocks_submission else "否",
                        "是" if item.blocks_downstream else "否",
                        _cell(item.rerun_from),
                        _cell(", ".join(item.target_artifacts) or "-"),
                        _cell(item.action),
                        _cell(item.evidence),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | - | 暂无修复任务 | - |")
    lines.extend(["", "## 阻断问题"])
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    lines.extend(f"- [ ] {item}" for item in report.recommended_actions) if report.recommended_actions else lines.append("- 无")
    return "\n".join(lines)


def _candidate_item(index: int, data: dict[str, Any], spec: dict[str, Any], severity: str) -> RepairQueueItem:
    return RepairQueueItem(
        task_id=f"RQ-{index:03d}",
        category=str(spec["category"]),
        severity=severity,
        source_artifact=str(spec["source"]),
        trigger_status=_trigger_status(data, spec),
        evidence=_evidence(data, spec),
        action=_action(data, spec, severity),
        target_artifacts=[str(item) for item in spec.get("target_artifacts", []) if str(item).strip()],
        rerun_from=str(spec.get("rerun_from") or ""),
        automation=str(spec.get("automation") or "agent"),
        blocks_submission=bool(spec.get("blocks_submission")) or severity == "block",
        blocks_downstream=bool(spec.get("blocks_downstream")) and severity in {"block", "high"},
    )


def _severity(data: dict[str, Any], spec: dict[str, Any], run_dir: Path | None = None) -> str:
    source = str(spec.get("source") or "")
    category = str(spec.get("category") or "")
    if source == "10-final-readiness.json" and _clean_final_gate(data, run_dir):
        return ""
    if source == "07-paper-review-calibration.json" and run_dir and _clean_revised_gate_for_run(run_dir):
        return ""
    if source == "11-submission-package.json" and _package_only_repair_queue_block(data):
        return ""
    statuses = _statuses(data, spec)
    pass_statuses = {"pass", "ready", "ready_for_benchmark", "ready_for_submission_check", "ready_for_release", "complete", "completed", "not_applicable"}
    if statuses and statuses <= pass_statuses:
        if _values(data, "manual_tasks") or _values(data, "warnings"):
            return "medium"
        return ""
    if statuses & set(spec.get("block_statuses", set())):
        if source == "14-final-handoff.json" and _final_handoff_only_upstream_block(data):
            return ""
        if _paper_grade_literature_pass(run_dir) and category in {"literature_search_strategy", "literature_rescue", "literature_rescue_execution"}:
            return "high"
        return "block"
    if _field_values_match(data, spec.get("block_values", {})):
        return "block"
    if any(_count_value(data.get(field)) > 0 for field in spec.get("block_count_fields", [])):
        if _paper_grade_literature_pass(run_dir) and category in {"literature_search_strategy", "literature_rescue", "literature_rescue_execution"}:
            return "high"
        return "block"
    if _values(data, "blocking_issues"):
        if _paper_grade_literature_pass(run_dir) and category in {"literature_search_strategy", "literature_rescue", "literature_rescue_execution"}:
            return "high"
        return "block"
    if statuses & set(spec.get("high_statuses", set())):
        return "high"
    if _field_values_match(data, spec.get("high_values", {})):
        return "high"
    if any(_count_value(data.get(field)) > 0 for field in spec.get("high_count_fields", [])):
        return "high"
    if _values(data, "manual_tasks") or _values(data, "required_actions"):
        return "high"
    if statuses & set(spec.get("medium_statuses", set())):
        return "medium"
    return ""


def _statuses(data: dict[str, Any], spec: dict[str, Any]) -> set[str]:
    fields = ["status", *[str(field) for field in spec.get("extra_status_fields", [])]]
    return {str(data.get(field) or "").strip() for field in fields if str(data.get(field) or "").strip()}


def _field_values_match(data: dict[str, Any], expected: Any) -> bool:
    if not isinstance(expected, dict):
        return False
    for field, values in expected.items():
        key = str(field)
        if key not in data or data.get(key) is None:
            continue
        if str(data.get(key)).strip() in {str(value) for value in values}:
            return True
    return False


def _trigger_status(data: dict[str, Any], spec: dict[str, Any]) -> str:
    parts = [f"status={data.get('status') or '-'}"]
    for field in ["integrity_status", "evidence_grade", "decision", "outcome", *[str(value) for value in spec.get("extra_status_fields", [])]]:
        if field in data and data.get(field) is not None and str(data.get(field)).strip():
            parts.append(f"{field}={data.get(field)}")
    for field in [*spec.get("block_count_fields", []), *spec.get("high_count_fields", [])]:
        count = _count_value(data.get(field))
        if count:
            parts.append(f"{field}={count}")
    return "; ".join(parts)


def _evidence(data: dict[str, Any], spec: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ["blocking_issues", "required_actions", "manual_tasks", "warnings", "next_actions"]:
        values.extend(_values(data, key))
        if len(values) >= 2:
            break
    if not values:
        values.append(_trigger_status(data, spec))
    return "；".join(values[:2])


def _action(data: dict[str, Any], spec: dict[str, Any], severity: str) -> str:
    keys = ["blocking_issues", "required_actions", "manual_tasks", "next_actions", "warnings"]
    if severity == "medium":
        keys = ["required_actions", "manual_tasks", "warnings", "next_actions"]
    for key in keys:
        values = _values(data, key)
        if values:
            return values[0]
    return str(spec.get("action") or "按来源审计报告修复后重跑。")


def _status(items: list[RepairQueueItem]) -> str:
    if any(item.severity == "block" for item in items):
        return "blocked_repair_required"
    if items:
        return "needs_repair"
    return "pass"


def _recommended_actions(status: str, items: list[RepairQueueItem]) -> list[str]:
    if status == "pass":
        return ["当前审计队列没有自动识别的修复项；继续人工最终核验。"]
    earliest = _earliest_rerun_from(items)
    actions = [
        "先处理 severity=block 的任务；未清零前不要把当前 run 当作最终投稿版本。",
        f"从 `{earliest}` 或其前一个人工 gate 恢复，重新生成受影响产物。",
        "修复后重新运行 resume，并检查 12-repair-queue.md、13-research-scorecard.md 和 14-run-integrity-audit.md。",
    ]
    if status == "needs_repair":
        actions[0] = "按 high/medium 优先级处理修复项；涉及人工审核、benchmark 或投稿模板的任务需要人工确认。"
    return actions


def _earliest_rerun_from(items: list[RepairQueueItem]) -> str:
    order = [
        "literature_review",
        "literature_context",
        "ideation",
        "experiment_plan",
        "experiments",
        "analysis",
        "paper_revision_plan",
        "paper_rewrite",
        "final_readiness",
        "submission_package",
    ]
    positions = {name: index for index, name in enumerate(order)}
    best = min((positions.get(item.rerun_from, len(order)), item.rerun_from) for item in items)
    return best[1] or "resume"


def _dedupe_items(items: list[RepairQueueItem]) -> list[RepairQueueItem]:
    seen: set[tuple[str, str]] = set()
    result: list[RepairQueueItem] = []
    for item in items:
        key = (item.source_artifact, item.category)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return [
        RepairQueueItem(
            task_id=f"RQ-{index:03d}",
            category=item.category,
            severity=item.severity,
            source_artifact=item.source_artifact,
            trigger_status=item.trigger_status,
            evidence=item.evidence,
            action=item.action,
            target_artifacts=item.target_artifacts,
            rerun_from=item.rerun_from,
            automation=item.automation,
            blocks_submission=item.blocks_submission,
            blocks_downstream=item.blocks_downstream,
            status=item.status,
        )
        for index, item in enumerate(result, start=1)
    ]


def _values(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _count_value(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _paper_grade_literature_pass(run_dir: Path | None) -> bool:
    if run_dir is None:
        return False
    gate = _read_json(run_dir / "01-literature-gate-decision.json")
    paper_grade = gate.get("paper_grade_literature") if isinstance(gate.get("paper_grade_literature"), dict) else {}
    return str(paper_grade.get("status") or "") == "pass"


def _clean_revised_gate_for_run(run_dir: Path) -> bool:
    return _clean_final_gate(_read_json(run_dir / "10-final-readiness.json"), run_dir)


def _clean_final_gate(final: dict[str, Any], run_dir: Path | None) -> bool:
    if str(final.get("status") or "") != "ready_for_submission_check":
        return False
    if _count_value(final.get("unsupported_after")) or _count_value(final.get("weak_after")):
        return False
    if _values(final, "blocking_issues"):
        return False
    if run_dir is None:
        return True
    trace = _read_json(run_dir / "10-claim-traceability.json")
    if trace and str(trace.get("status") or "") != "pass":
        return False
    revised_review = _read_json(run_dir / "10-revised-paper-review.json")
    decision = str(revised_review.get("decision") or revised_review.get("status") or "")
    if decision in {"reject", "major_revision", "requires_revision", "block"}:
        return False
    if _values(revised_review, "unsupported_claims"):
        return False
    return True


def _package_only_repair_queue_block(data: dict[str, Any]) -> bool:
    blocking = _values(data, "blocking_issues")
    if not blocking:
        return False
    return all("修复队列" in item or "repair queue" in item.lower() for item in blocking)


def _final_handoff_only_upstream_block(data: dict[str, Any]) -> bool:
    if data.get("package_zip_exists") is False or data.get("package_zip_valid") is False:
        return False
    blocking = _values(data, "blocking_issues")
    if not blocking:
        return False
    prefixes = ("submission_package:", "scorecard:", "run_integrity:", "paper_grade:")
    return all(str(item).strip().startswith(prefixes) for item in blocking)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
