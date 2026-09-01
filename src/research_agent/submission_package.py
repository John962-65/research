from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil
import zipfile

from .artifacts import write_json, write_text
from .models import SubmissionPackageFile, SubmissionPackageReport


SUBMISSION_PACKAGE_DIR = "submission-package"
SUBMISSION_PACKAGE_JSON = "11-submission-package.json"
SUBMISSION_PACKAGE_MD = "11-submission-package.md"
SUBMISSION_PACKAGE_ZIP = "11-submission-package.zip"


def write_submission_package_artifacts(topic: str, run_dir: Path) -> SubmissionPackageReport:
    package_dir = run_dir / SUBMISSION_PACKAGE_DIR
    package_dir.mkdir(parents=True, exist_ok=True)

    copied_files = [_copy_into_package(run_dir, package_dir, spec) for spec in _package_specs()]
    final_readiness = _read_json(run_dir / "10-final-readiness.json")
    availability = _read_json(run_dir / "10-code-data-availability.json")
    submission = _read_json(run_dir / "10-submission-check.json")
    ai_disclosure = _read_json(run_dir / "10-ai-disclosure.json")
    repair_queue = _read_json(run_dir / "12-repair-queue.json")
    blocking, manual = _audit_tasks(copied_files, final_readiness, availability, submission, ai_disclosure, repair_queue)
    status = _status(blocking, manual)
    generated = _write_generated_package_files(topic, run_dir, package_dir, copied_files, status, blocking, manual, final_readiness, availability, submission, ai_disclosure, repair_queue)
    files = [*copied_files, *generated]
    package_manifest = _write_package_manifest(topic, package_dir, files, status, blocking, manual)
    files.append(package_manifest)
    zip_record = _write_zip(run_dir, package_dir, files)
    files.append(zip_record)

    if zip_record.status != "pass":
        blocking = [*blocking, f"ZIP package: {zip_record.note or 'failed to create zip archive'}"]
        status = _status(blocking, manual)

    report = SubmissionPackageReport(
        topic=topic,
        status=status,
        package_dir=SUBMISSION_PACKAGE_DIR,
        package_zip=SUBMISSION_PACKAGE_ZIP,
        final_readiness_status=_status_field(final_readiness),
        availability_status=_status_field(availability),
        submission_status=_status_field(submission),
        files=files,
        blocking_issues=blocking,
        manual_tasks=manual,
        recommended_actions=_recommended_actions(status),
    )
    write_json(run_dir / SUBMISSION_PACKAGE_JSON, report)
    write_text(run_dir / SUBMISSION_PACKAGE_MD, render_submission_package_markdown(report))
    return report


def render_submission_package_markdown(report: SubmissionPackageReport) -> str:
    lines = [
        f"# 投稿/归档包：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 包目录：{report.package_dir}",
        f"- ZIP：{report.package_zip}",
        f"- 最终 Gate：{report.final_readiness_status or '未审计'}",
        f"- 代码/数据：{report.availability_status or '未审计'}",
        f"- 投稿格式：{report.submission_status or '未审计'}",
        "",
        "## 文件清单",
        "| 源文件 | 包内路径 | 必需 | 状态 | 大小 | SHA256 | 说明 |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in report.files:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.source_path or "-"),
                    _cell(item.package_path),
                    "是" if item.required else "否",
                    item.status,
                    str(item.bytes),
                    f"`{item.sha256}`" if item.sha256 else "-",
                    _cell(item.note or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    if report.blocking_issues:
        lines.extend(f"- {item}" for item in report.blocking_issues)
    else:
        lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    if report.manual_tasks:
        lines.extend(f"- [ ] {item}" for item in report.manual_tasks)
    else:
        lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    lines.extend(f"- [ ] {item}" for item in report.recommended_actions)
    return "\n".join(lines)


def _package_specs() -> list[dict[str, Any]]:
    return [
        {"source": "09-revised-paper.md", "dest": "paper/revised-paper.md", "required": True, "note": "修订后的主文稿 Markdown。"},
        {"source": "09-revised-paper.tex", "dest": "paper/revised-paper.tex", "required": True, "note": "修订后的 LaTeX 源文件。"},
        {"source": "00-prior-run-lessons.md", "dest": "provenance/prior-run-lessons.md", "required": False, "note": "历史 run 经验继承约束。"},
        {"source": "00-prior-run-lessons.json", "dest": "provenance/prior-run-lessons.json", "required": False, "note": "结构化历史 run 经验继承约束。"},
        {"source": "00-open-source-lessons.md", "dest": "provenance/open-source-lessons.md", "required": False, "note": "外部开源科研 agent 项目经验和本轮平台约束。"},
        {"source": "00-open-source-lessons.json", "dest": "provenance/open-source-lessons.json", "required": False, "note": "结构化外部开源项目经验约束。"},
        {"source": "01-references.bib", "dest": "references/references.bib", "required": True, "note": "BibTeX 参考文献。"},
        {"source": "01-references.ris", "dest": "references/references.ris", "required": False, "note": "RIS 参考文献导出。"},
        {"source": "04-statistics-figure.svg", "dest": "figures/statistics-figure.svg", "required": False, "note": "统计图。"},
        {"source": "04-results.csv", "dest": "results/results.csv", "required": True, "note": "实验结果表。"},
        {"source": "04-results.json", "dest": "results/results.json", "required": True, "note": "结构化实验结果。"},
        {"source": "04-statistics.md", "dest": "results/statistics.md", "required": True, "note": "统计审计摘要。"},
        {"source": "04-statistics.json", "dest": "results/statistics.json", "required": True, "note": "结构化统计审计。"},
        {"source": "04-failure-analysis.md", "dest": "results/failure-analysis.md", "required": False, "note": "失败/负结果分析和论文结论边界。"},
        {"source": "04-failure-analysis.json", "dest": "results/failure-analysis.json", "required": False, "note": "结构化失败/负结果分析。"},
        {"source": "04-benchmark-result-schema-audit.md", "dest": "results/benchmark-result-schema-audit.md", "required": False, "note": "执行后 result schema、统计比较、角色矩阵和 benchmark artifact contract 审计。"},
        {"source": "04-benchmark-result-schema-audit.json", "dest": "results/benchmark-result-schema-audit.json", "required": False, "note": "结构化 benchmark result schema 审计。"},
        {"source": "04-benchmark-evidence-audit.md", "dest": "results/benchmark-evidence-audit.md", "required": False, "note": "区分真实 benchmark、local 实验和 smoke-only 证据的审计。"},
        {"source": "04-benchmark-evidence-audit.json", "dest": "results/benchmark-evidence-audit.json", "required": False, "note": "结构化 benchmark 证据等级审计。"},
        {"source": "04-experiment-decision.md", "dest": "results/experiment-decision.md", "required": False, "note": "实验后 proceed/refine/pivot/repair 决策。"},
        {"source": "04-experiment-decision.json", "dest": "results/experiment-decision.json", "required": False, "note": "结构化实验后决策。"},
        {"source": "04-hypothesis-outcome.md", "dest": "results/hypothesis-outcome.md", "required": False, "note": "假设是否被支持、部分支持、反驳、未检验或仅有 smoke 证据的审计。"},
        {"source": "04-hypothesis-outcome.json", "dest": "results/hypothesis-outcome.json", "required": False, "note": "结构化假设结果审计。"},
        {"source": "04-claim-boundary-preflight.md", "dest": "audits/claim-boundary-preflight.md", "required": False, "note": "写作前 allowed/prohibited claim、结果边界和越界风险预检。"},
        {"source": "04-claim-boundary-preflight.json", "dest": "audits/claim-boundary-preflight.json", "required": False, "note": "结构化写作前 claim 边界预检。"},
        {"source": "09-revision-response-audit.md", "dest": "audits/revision-response-audit.md", "required": False, "note": "审稿修订任务到修订稿回应的逐条闭环审计。"},
        {"source": "09-revision-response-audit.json", "dest": "audits/revision-response-audit.json", "required": False, "note": "结构化审稿修订回应闭环审计。"},
        {"source": "03-preregistration.md", "dest": "reproducibility/preregistration.md", "required": False, "note": "实验预注册和分析规则锁定。"},
        {"source": "03-preregistration.json", "dest": "reproducibility/preregistration.json", "required": False, "note": "结构化实验预注册。"},
        {"source": "03-ablation-plan.md", "dest": "reproducibility/ablation-plan.md", "required": False, "note": "消融计划。"},
        {"source": "03-review-constraint-compliance.md", "dest": "reproducibility/review-constraint-compliance.md", "required": False, "note": "人工审核约束是否落实到选中 idea 和实验计划的审计。"},
        {"source": "03-review-constraint-compliance.json", "dest": "reproducibility/review-constraint-compliance.json", "required": False, "note": "结构化人工审核约束落实审计。"},
        {"source": "03-experiment-audit.md", "dest": "reproducibility/experiment-audit.md", "required": False, "note": "实验计划执行前审计。"},
        {"source": "03-experiment-audit.json", "dest": "reproducibility/experiment-audit.json", "required": False, "note": "结构化实验计划审计。"},
        {"source": "03-idea-experiment-contract.md", "dest": "reproducibility/idea-experiment-contract.md", "required": False, "note": "选中 idea、证据、baseline、metric、命令和 benchmark readiness 到实验计划的跨阶段契约。"},
        {"source": "03-idea-experiment-contract.json", "dest": "reproducibility/idea-experiment-contract.json", "required": False, "note": "结构化 idea 到实验契约审计。"},
        {"source": "03-execution-safety-audit.md", "dest": "reproducibility/execution-safety-audit.md", "required": False, "note": "实验命令和执行配置安全审计。"},
        {"source": "03-execution-safety-audit.json", "dest": "reproducibility/execution-safety-audit.json", "required": False, "note": "结构化实验执行安全审计。"},
        {"source": "04-experiment-runbook.md", "dest": "reproducibility/experiment-runbook.md", "required": True, "note": "复现实验运行手册。"},
        {"source": "04-experiment-runbook.json", "dest": "reproducibility/experiment-runbook.json", "required": True, "note": "结构化复现实验记录。"},
        {"source": "04-environment-snapshot.md", "dest": "reproducibility/environment-snapshot.md", "required": False, "note": "本次实验 Python、平台、工具路径、包版本和源码哈希快照。"},
        {"source": "04-environment-snapshot.json", "dest": "reproducibility/environment-snapshot.json", "required": False, "note": "结构化实验环境快照。"},
        {"source": "10-code-data-availability.md", "dest": "audits/code-data-availability.md", "required": True, "note": "代码/数据可用性审计。"},
        {"source": "10-code-data-availability.json", "dest": "audits/code-data-availability.json", "required": True, "note": "结构化代码/数据可用性审计。"},
        {"source": "10-release-metadata.md", "dest": "audits/release-metadata.md", "required": False, "note": "发布/归档元数据。"},
        {"source": "10-release-metadata.json", "dest": "audits/release-metadata.json", "required": False, "note": "结构化发布/归档元数据。"},
        {"source": "10-submission-check.md", "dest": "audits/submission-check.md", "required": True, "note": "投稿格式检查。"},
        {"source": "10-submission-check.json", "dest": "audits/submission-check.json", "required": True, "note": "结构化投稿格式检查。"},
        {"source": "10-ai-disclosure.md", "dest": "audits/ai-disclosure.md", "required": True, "note": "AI 使用披露和人工政策核验说明。"},
        {"source": "10-ai-disclosure.json", "dest": "audits/ai-disclosure.json", "required": True, "note": "结构化 AI 使用披露审计。"},
        {"source": "10-claim-traceability.md", "dest": "audits/claim-traceability.md", "required": False, "note": "修订稿主张到文献、结果、统计和 runbook 的证据追踪矩阵。"},
        {"source": "10-claim-traceability.json", "dest": "audits/claim-traceability.json", "required": False, "note": "结构化 claim traceability 审计。"},
        {"source": "10-agent-claim-audit.md", "dest": "audits/agent-claim-audit.md", "required": False, "note": "修订稿 claim 到多智能体写作、复核、证据和统计/benchmark owner 的责任矩阵。"},
        {"source": "10-agent-claim-audit.json", "dest": "audits/agent-claim-audit.json", "required": False, "note": "结构化多智能体 claim owner 审计。"},
        {"source": "10-agent-deliberation.md", "dest": "audits/agent-deliberation.md", "required": False, "note": "确定性角色规则投影与人工复核记录；当前不代表独立 Agent verdict。"},
        {"source": "10-agent-deliberation.json", "dest": "audits/agent-deliberation.json", "required": False, "note": "结构化角色规则汇总，包含 independent_agent_execution 能力声明。"},
        {"source": "10-citation-grounding.md", "dest": "audits/citation-grounding.md", "required": False, "note": "修订稿正文 citation 附近 claim 与 01-context chunks 的支撑关系审计。"},
        {"source": "10-citation-grounding.json", "dest": "audits/citation-grounding.json", "required": False, "note": "结构化 citation grounding 审计。"},
        {"source": "10-citation-coverage.md", "dest": "audits/citation-coverage.md", "required": False, "note": "文献 context 到修订稿正文 citation 覆盖、近期文献和引用集中度审计。"},
        {"source": "10-citation-coverage.json", "dest": "audits/citation-coverage.json", "required": False, "note": "结构化 citation coverage 审计。"},
        {"source": "10-results-presentation.md", "dest": "audits/results-presentation.md", "required": False, "note": "修订稿结果章节、统计指标、图表引用和 CI/不确定性呈现审计。"},
        {"source": "10-results-presentation.json", "dest": "audits/results-presentation.json", "required": False, "note": "结构化 results presentation 审计。"},
        {"source": "10-claim-consistency.md", "dest": "audits/claim-consistency.md", "required": False, "note": "修订稿结论强度与 hypothesis outcome、负结果和 smoke-only 证据边界的一致性审计。"},
        {"source": "10-claim-consistency.json", "dest": "audits/claim-consistency.json", "required": False, "note": "结构化 claim consistency 审计。"},
        {"source": "10-final-readiness.md", "dest": "audits/final-readiness.md", "required": True, "note": "最终就绪报告。"},
        {"source": "10-final-readiness.json", "dest": "audits/final-readiness.json", "required": True, "note": "结构化最终就绪报告。"},
        {"source": "12-repair-queue.md", "dest": "audits/repair-queue.md", "required": False, "note": "汇总所有未通过审计的结构化修复队列。"},
        {"source": "12-repair-queue.json", "dest": "audits/repair-queue.json", "required": False, "note": "结构化修复队列、重跑入口和阻断关系。"},
        {"source": "12-repair-resolution-audit.md", "dest": "audits/repair-resolution-audit.md", "required": False, "note": "repair-resume 后原修复项是否闭环的审计。"},
        {"source": "12-repair-resolution-audit.json", "dest": "audits/repair-resolution-audit.json", "required": False, "note": "结构化修复闭环审计。"},
        {"source": "13-human-gate-audit.md", "dest": "audits/human-gate-audit.md", "required": False, "note": "review/execution 人工 gate 是否先于 idea、实验和执行结果的合规审计。"},
        {"source": "13-human-gate-audit.json", "dest": "audits/human-gate-audit.json", "required": False, "note": "结构化人工 gate 合规审计。"},
        {"source": "13-agent-stage-contract.md", "dest": "audits/agent-stage-contract.md", "required": False, "note": "开源科研 agent 模式映射到本 run 的阶段契约和平台缺口审计。"},
        {"source": "13-agent-stage-contract.json", "dest": "audits/agent-stage-contract.json", "required": False, "note": "结构化阶段契约审计。"},
        {"source": "13-agent-trajectory.md", "dest": "audits/agent-trajectory.md", "required": False, "note": "按科研流程聚合 run-manifest 和关键 gate 的阶段轨迹。"},
        {"source": "13-agent-trajectory.json", "dest": "audits/agent-trajectory.json", "required": False, "note": "结构化阶段轨迹、缺失产物、阻断和人工待办。"},
        {"source": "13-llm-trace-audit.md", "dest": "audits/llm-trace-audit.md", "required": False, "note": "关键科研阶段是否有成功 LLM 调用、失败调用和 AI 披露一致性的审计。"},
        {"source": "13-llm-trace-audit.json", "dest": "audits/llm-trace-audit.json", "required": False, "note": "结构化 LLM 阶段调用覆盖审计。"},
        {"source": "13-llm-runtime-contract.md", "dest": "audits/llm-runtime-contract.md", "required": False, "note": "模型配置、预算策略、密钥不落盘、ledger 元数据和 AI disclosure 一致性的运行契约。"},
        {"source": "13-llm-runtime-contract.json", "dest": "audits/llm-runtime-contract.json", "required": False, "note": "结构化 LLM runtime contract 审计。"},
        {"source": "13-run-economics-audit.md", "dest": "audits/run-economics-audit.md", "required": False, "note": "LLM 调用按阶段汇总的 token、耗时、预算压力和可选成本审计。"},
        {"source": "13-run-economics-audit.json", "dest": "audits/run-economics-audit.json", "required": False, "note": "结构化运行成本和耗时审计。"},
        {"source": "13-agent-observability-audit.md", "dest": "audits/agent-observability-audit.md", "required": False, "note": "run manifest、LLM budget、human gate、实验 runbook、诊断恢复和 repair trace 的可观测性审计。"},
        {"source": "13-agent-observability-audit.json", "dest": "audits/agent-observability-audit.json", "required": False, "note": "结构化 agent 可观测性审计。"},
        {"source": "14-run-integrity-audit.md", "dest": "audits/run-integrity-audit.md", "required": False, "note": "最终运行完整性、manifest/hash、人工 gate、LLM ledger、投稿包和密钥落盘审计。"},
        {"source": "14-run-integrity-audit.json", "dest": "audits/run-integrity-audit.json", "required": False, "note": "结构化最终运行完整性审计。"},
        {"source": "10-revised-paper-review.md", "dest": "audits/revised-paper-review.md", "required": False, "note": "修订稿复核。"},
        {"source": "07-paper-review-calibration.md", "dest": "audits/paper-review-calibration.md", "required": False, "note": "原始论文复核分数/决定是否过宽的校准审计。"},
        {"source": "07-paper-review-calibration.json", "dest": "audits/paper-review-calibration.json", "required": False, "note": "结构化论文复核校准审计。"},
        {"source": "09-revision-report.md", "dest": "audits/revision-report.md", "required": False, "note": "修订执行记录。"},
        {"source": "01-citation-audit.md", "dest": "audits/citation-audit.md", "required": False, "note": "引用审计。"},
        {"source": "01-literature-rerank.md", "dest": "audits/literature-rerank.md", "required": False, "note": "文献候选 topic/query/baseline/benchmark/metadata 重排和降权诊断。"},
        {"source": "01-literature-rerank.json", "dest": "audits/literature-rerank.json", "required": False, "note": "结构化文献候选重排报告。"},
        {"source": "01-query-execution-audit.md", "dest": "audits/query-execution-audit.md", "required": False, "note": "selected query 到 source 返回、候选命中和 top rerank 覆盖的审计。"},
        {"source": "01-query-execution-audit.json", "dest": "audits/query-execution-audit.json", "required": False, "note": "结构化 query execution 覆盖审计。"},
        {"source": "01-literature-snowball.md", "dest": "audits/literature-snowball.md", "required": False, "note": "文献滚雪球补强计划。"},
        {"source": "01-literature-snowball.json", "dest": "audits/literature-snowball.json", "required": False, "note": "结构化文献滚雪球计划。"},
        {"source": "01-literature-coverage.md", "dest": "audits/literature-coverage.md", "required": False, "note": "文献 benchmark/baseline 覆盖审计。"},
        {"source": "01-literature-coverage.json", "dest": "audits/literature-coverage.json", "required": False, "note": "结构化文献覆盖审计。"},
        {"source": "01-literature-evidence-mix.md", "dest": "audits/literature-evidence-mix.md", "required": False, "note": "筛选文献组合是否覆盖综述/高引用、benchmark/dataset、baseline/method 和近期研究 anchor 的审计。"},
        {"source": "01-literature-evidence-mix.json", "dest": "audits/literature-evidence-mix.json", "required": False, "note": "结构化文献证据组合审计。"},
        {"source": "01-literature-evidence-contract.md", "dest": "audits/literature-evidence-contract.md", "required": False, "note": "进入 RAG/context 的文献是否可定位、可支撑、可复核的证据契约。"},
        {"source": "01-literature-evidence-contract.json", "dest": "audits/literature-evidence-contract.json", "required": False, "note": "结构化文献证据契约。"},
        {"source": "01-literature-rescue-plan.md", "dest": "audits/literature-rescue-plan.md", "required": False, "note": "弱文献补检索和文献源修复计划。"},
        {"source": "01-literature-rescue-plan.json", "dest": "audits/literature-rescue-plan.json", "required": False, "note": "结构化弱文献补检索计划。"},
        {"source": "01-literature-rescue-execution.md", "dest": "audits/literature-rescue-execution.md", "required": False, "note": "自动补检索执行记录。"},
        {"source": "01-literature-rescue-execution.json", "dest": "audits/literature-rescue-execution.json", "required": False, "note": "结构化自动补检索执行记录。"},
        {"source": "01-literature-search-feedback.md", "dest": "audits/literature-search-feedback.md", "required": False, "note": "下一轮检索反馈策略。"},
        {"source": "01-literature-search-feedback.json", "dest": "audits/literature-search-feedback.json", "required": False, "note": "结构化下一轮检索反馈策略。"},
        {"source": "01-literature-metadata-audit.md", "dest": "audits/literature-metadata-audit.md", "required": False, "note": "保留文献 DOI/URL/年份/来源/摘要/主题匹配的 metadata 去噪审计。"},
        {"source": "01-literature-metadata-audit.json", "dest": "audits/literature-metadata-audit.json", "required": False, "note": "结构化文献 metadata 去噪审计。"},
        {"source": "01-seed-paper-intake.md", "dest": "audits/seed-paper-intake.md", "required": False, "note": "人工 seed 文献是否进入原始文献池、curated context 和质量筛选的审计。"},
        {"source": "01-seed-paper-intake.json", "dest": "audits/seed-paper-intake.json", "required": False, "note": "结构化 seed paper intake 审计。"},
        {"source": "02-idea-audit.md", "dest": "audits/idea-audit.md", "required": False, "note": "Idea 证据、baseline、实验草案和人工审核约束审计。"},
        {"source": "02-idea-audit.json", "dest": "audits/idea-audit.json", "required": False, "note": "结构化 idea 证据与约束审计。"},
        {"source": "03-benchmark-plan.md", "dest": "reproducibility/benchmark-plan.md", "required": False, "note": "真实 benchmark 接入计划。"},
        {"source": "03-benchmark-readiness.md", "dest": "reproducibility/benchmark-readiness.md", "required": False, "note": "执行前 benchmark 模式、adapter、metric/baseline 和 artifact contract 就绪审计。"},
        {"source": "03-benchmark-readiness.json", "dest": "reproducibility/benchmark-readiness.json", "required": False, "note": "结构化 benchmark readiness 审计。"},
        {"source": "03-benchmark-adapters.md", "dest": "reproducibility/benchmark-adapters.md", "required": False, "note": "Benchmark adapter 审计。"},
        {"source": "03-benchmark-adapters.json", "dest": "reproducibility/benchmark-adapters.json", "required": False, "note": "结构化 benchmark adapter 审计。"},
        {"source": "run-manifest.md", "dest": "provenance/run-manifest.md", "required": True, "note": "运行轨迹。"},
        {"source": "run-manifest.json", "dest": "provenance/run-manifest.json", "required": True, "note": "结构化运行轨迹。"},
        {"source": "run-llm-ledger.md", "dest": "provenance/llm-ledger.md", "required": False, "note": "LLM 调用审计账本。"},
        {"source": "run-llm-ledger.json", "dest": "provenance/llm-ledger.json", "required": False, "note": "结构化 LLM 调用审计账本。"},
    ]


def _copy_into_package(run_dir: Path, package_dir: Path, spec: dict[str, Any]) -> SubmissionPackageFile:
    source_rel = str(spec["source"])
    dest_rel = str(spec["dest"])
    required = bool(spec["required"])
    source = run_dir / source_rel
    package_path = f"{SUBMISSION_PACKAGE_DIR}/{dest_rel}"
    if not source.exists() or not source.is_file() or source.stat().st_size == 0:
        return SubmissionPackageFile(source_rel, package_path, "missing" if required else "optional_missing", 0, "", required, str(spec["note"]))
    dest = package_dir / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, dest)
    except OSError as exc:
        return SubmissionPackageFile(source_rel, package_path, "error", 0, "", required, str(exc))
    return _file_record(source_rel, package_path, dest, required, str(spec["note"]))


def _write_generated_package_files(
    topic: str,
    run_dir: Path,
    package_dir: Path,
    files: list[SubmissionPackageFile],
    status: str,
    blocking: list[str],
    manual: list[str],
    final_readiness: dict[str, Any],
    availability: dict[str, Any],
    submission: dict[str, Any],
    ai_disclosure: dict[str, Any],
    repair_queue: dict[str, Any],
) -> list[SubmissionPackageFile]:
    readme_path = package_dir / "README.md"
    checklist_path = package_dir / "CHECKLIST.md"
    write_text(readme_path, _render_package_readme(topic, run_dir, files, status, blocking, manual, final_readiness, availability, submission, ai_disclosure, repair_queue))
    write_text(checklist_path, _render_package_checklist(blocking, manual))
    return [
        _file_record("", f"{SUBMISSION_PACKAGE_DIR}/README.md", readme_path, True, "包说明。"),
        _file_record("", f"{SUBMISSION_PACKAGE_DIR}/CHECKLIST.md", checklist_path, True, "人工提交前清单。"),
    ]


def _write_package_manifest(
    topic: str,
    package_dir: Path,
    files: list[SubmissionPackageFile],
    status: str,
    blocking: list[str],
    manual: list[str],
) -> SubmissionPackageFile:
    manifest_path = package_dir / "package-manifest.json"
    payload = {
        "topic": topic,
        "status": status,
        "files": [asdict(item) for item in files],
        "blocking_issues": blocking,
        "manual_tasks": manual,
    }
    write_json(manifest_path, payload)
    return _file_record("", f"{SUBMISSION_PACKAGE_DIR}/package-manifest.json", manifest_path, True, "包内文件 manifest。")


def _write_zip(run_dir: Path, package_dir: Path, files: list[SubmissionPackageFile]) -> SubmissionPackageFile:
    zip_path = run_dir / SUBMISSION_PACKAGE_ZIP
    unsafe_paths = [item.package_path for item in files if item.status in {"pass", "generated"} and not _safe_package_arcname(item.package_path)]
    if unsafe_paths:
        return SubmissionPackageFile("", SUBMISSION_PACKAGE_ZIP, "error", 0, "", True, f"Unsafe package path: {unsafe_paths[0]}")
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            seen: set[str] = set()
            for item in files:
                arcname = _safe_package_arcname(item.package_path)
                if not arcname or item.status not in {"pass", "generated"}:
                    continue
                path = run_dir / arcname
                if not path.exists() or arcname in seen:
                    continue
                archive.write(path, arcname=arcname)
                seen.add(arcname)
    except OSError as exc:
        return SubmissionPackageFile("", SUBMISSION_PACKAGE_ZIP, "error", 0, "", True, str(exc))
    return _file_record("", SUBMISSION_PACKAGE_ZIP, zip_path, True, "可下载投稿/归档 ZIP。")


def _safe_package_arcname(package_path: str) -> str:
    if not package_path.startswith(f"{SUBMISSION_PACKAGE_DIR}/"):
        return ""
    if "\\" in package_path or package_path.startswith("/") or _windows_drive_absolute(package_path):
        return ""
    parts = package_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return ""
    return "/".join(parts)


def _windows_drive_absolute(path: str) -> bool:
    return len(path) >= 2 and path[0].isalpha() and path[1] == ":"


def _audit_tasks(
    files: list[SubmissionPackageFile],
    final_readiness: dict[str, Any],
    availability: dict[str, Any],
    submission: dict[str, Any],
    ai_disclosure: dict[str, Any],
    repair_queue: dict[str, Any],
) -> tuple[list[str], list[str]]:
    blocking = [f"{item.source_path}: 必需文件缺失或无法复制。" for item in files if item.required and item.status != "pass"]
    manual: list[str] = []

    final_status = _status_field(final_readiness)
    if not final_status:
        blocking.append("10-final-readiness.json 缺失，无法判断最终 gate。")
    elif final_status in {"requires_human_evidence", "requires_revision"}:
        blocking.append(f"最终 Gate 仍为 {final_status}，不应直接投稿或归档为最终版本。")
    elif final_status == "ready_for_human_polish":
        manual.append("最终 Gate 为 ready_for_human_polish，投稿前仍需人工语言、格式和图表润色。")

    availability_status = _status_field(availability)
    if not availability_status:
        blocking.append("10-code-data-availability.json 缺失，无法确认代码/数据可用性。")
    elif availability_status == "blocked":
        blocking.append("代码/数据可用性审计仍为 blocked。")
    elif availability_status == "needs_human_release_metadata":
        manual.append("代码/数据可用性仍需人工补齐仓库、许可证、数据访问或归档 DOI。")

    submission_status = _status_field(submission)
    if not submission_status:
        blocking.append("10-submission-check.json 缺失，无法确认投稿格式检查。")
    elif submission_status == "blocked":
        blocking.append("投稿格式检查仍为 blocked。")
    elif submission_status == "needs_human_format_check":
        manual.append("投稿格式检查仍需人工套用目标会议/期刊官方模板。")

    ai_status = _status_field(ai_disclosure)
    if not ai_status:
        blocking.append("10-ai-disclosure.json 缺失，无法确认 AI 使用披露。")
    elif ai_status == "needs_human_policy_check":
        manual.append("AI 使用披露仍需按目标 venue policy 人工确认措辞和放置位置。")

    repair_status = _status_field(repair_queue)
    repair_summary = repair_queue.get("summary") if isinstance(repair_queue.get("summary"), dict) else {}
    repair_block = _int_value(repair_summary.get("block"))
    repair_total = _int_value(repair_summary.get("total"))
    if repair_status == "blocked_repair_required" and repair_block:
        blocking.append(f"修复队列仍有 {repair_summary.get('block', 0)} 个 block 任务，不应把当前包标记为最终版本。")
    elif repair_status == "blocked_repair_required":
        manual.append("修复队列状态仍为 blocked_repair_required 但 block 计数为 0；投稿前重新生成 repair queue/package 或人工确认状态一致。")
    elif repair_status == "needs_repair":
        manual.append(f"修复队列仍有 {repair_total} 个 high/medium 任务，投稿前需人工确认是否已处理或接受风险。")

    manual.extend(_list_values(final_readiness, "next_actions", limit=4))
    manual.extend(_list_values(availability, "manual_tasks", limit=4))
    manual.extend(_list_values(submission, "manual_tasks", limit=4))
    manual.extend(_list_values(repair_queue, "manual_tasks", limit=4))
    return _dedupe(blocking), _dedupe(manual)


def _render_package_readme(
    topic: str,
    run_dir: Path,
    files: list[SubmissionPackageFile],
    status: str,
    blocking: list[str],
    manual: list[str],
    final_readiness: dict[str, Any],
    availability: dict[str, Any],
    submission: dict[str, Any],
    ai_disclosure: dict[str, Any],
    repair_queue: dict[str, Any],
) -> str:
    lines = [
        f"# Submission Package: {topic}",
        "",
        f"- Source run: `{run_dir.name}`",
        f"- Package status: `{status}`",
        f"- Final readiness: `{_status_field(final_readiness) or 'missing'}`",
        f"- Code/data availability: `{_status_field(availability) or 'missing'}`",
        f"- Submission format check: `{_status_field(submission) or 'missing'}`",
        f"- AI disclosure: `{_status_field(ai_disclosure) or 'missing'}`",
        f"- Repair queue: `{_status_field(repair_queue) or 'missing'}`",
        "",
        "## Contents",
        "| Path | Source | Status | Required |",
        "| --- | --- | --- | --- |",
    ]
    for item in files:
        lines.append(f"| {_cell(item.package_path)} | {_cell(item.source_path or 'generated')} | {item.status} | {'yes' if item.required else 'no'} |")
    lines.extend(["", "## Blocking Issues"])
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- None")
    lines.extend(["", "## Manual Tasks"])
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- None")
    return "\n".join(lines)


def _render_package_checklist(blocking: list[str], manual: list[str]) -> str:
    lines = [
        "# Human Submission Checklist",
        "",
        "## Must Resolve Before Upload",
    ]
    if blocking:
        lines.extend(f"- [ ] {item}" for item in blocking)
    else:
        lines.append("- [ ] Confirm there are no hidden unsupported claims or missing files.")
    lines.extend(
        [
            "",
            "## Manual Submission Checks",
            "- [ ] Replace the generic TeX skeleton with the official target venue template when required.",
            "- [ ] Confirm author list, acknowledgements, anonymity rules, page limits and supplementary material rules.",
            "- [ ] Verify DOI, year, author order, venue and citation keys in the reference manager.",
            "- [ ] Confirm code repository URL, license, data access notes and archive DOI.",
            "- [ ] Run the actual benchmark or document why the included results are still simulated/local smoke evidence.",
        ]
    )
    lines.extend(f"- [ ] {item}" for item in manual[:10])
    return "\n".join(lines)


def _recommended_actions(status: str) -> list[str]:
    if status == "blocked":
        return [
            "先处理 11-submission-package.md 中的阻断问题，再把 ZIP 作为投稿或归档材料。",
            "重新运行 resume 生成新的最终审计和投稿包。",
            "不要把当前包标记为最终可提交版本。",
        ]
    if status == "needs_human_submission_review":
        return [
            "打开 submission-package/CHECKLIST.md 逐项完成人工上传前检查。",
            "确认目标会议/期刊官方模板、匿名规则、页数限制和参考文献样式。",
            "补齐代码/数据发布元数据后，再更新 ZIP 包或重新运行流水线。",
        ]
    return [
        "人工下载并核验 11-submission-package.zip。",
        "在目标投稿系统中按官方要求上传 TeX、参考文献、图和补充材料。",
        "投稿后把系统回执、版本号或 DOI 写回项目记录。",
    ]


def _status(blocking: list[str], manual: list[str]) -> str:
    if blocking:
        return "blocked"
    if manual:
        return "needs_human_submission_review"
    return "ready_for_human_submission_upload"


def _file_record(source_path: str, package_path: str, path: Path, required: bool, note: str) -> SubmissionPackageFile:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return SubmissionPackageFile(source_path, package_path, "error", 0, "", required, str(exc))
    return SubmissionPackageFile(source_path, package_path, "pass", len(data), hashlib.sha256(data).hexdigest(), required, note)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _status_field(data: dict[str, Any]) -> str:
    return str(data.get("status") or "").strip()


def _list_values(data: dict[str, Any], key: str, limit: int) -> list[str]:
    values = data.get(key)
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values[:limit] if str(item).strip()]


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
