<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 10：修订后审计与最终就绪

## Phase 10: Post-Revision Audit and Readiness

第十阶段对 `09-revised-paper.md` 再做一次 claim-grounding 复核，并生成最终就绪报告：

- `10-revised-paper-review.md` / `10-revised-paper-review.json`：修订稿的第二轮审稿式复核。
- `10-claim-traceability.md` / `10-claim-traceability.json`：把修订稿关键 claim 映射到 citation key、结果指标、统计审计和实验 runbook，标记 `pass/review/block`。
- `10-agent-claim-audit.md` / `10-agent-claim-audit.json`：把每条修订稿 claim 映射到 `manuscript_editor`、`skeptical_reviewer`、`evidence_curator`/`literature_scout`、`benchmark_engineer`/`statistician` 等 owner，检查写作、复核、证据和统计/benchmark 角色是否贯穿到最终 claim。
- `10-agent-deliberation.md` / `10-agent-deliberation.json`：当前实现是基于 claim traceability、citation grounding/coverage、结果呈现和 claim consistency 的确定性角色规则审计，不是独立 Agent 执行。产物会明确写入 `assessment_kind=deterministic_role_projection` 和 `independent_agent_execution=false`；即使规则全部通过也保持 `review_required`，不能冒充独立多智能体共识。
- `10-citation-grounding.md` / `10-citation-grounding.json`：逐个检查正文 `[citation_key]` / `\cite{key}` 附近 claim 是否能和 `01-context` 中对应文献 chunk 形成可见支撑；未知 key、无 chunk 或弱重叠会进入投稿检查和分数卡。
- `10-citation-coverage.md` / `10-citation-coverage.json`：反向检查 `01-context` 中的高相关、近年、baseline/benchmark 文献是否真正进入修订稿正文，并标记未知 citation key、覆盖过低或 citation 过度集中问题。
- `10-results-presentation.md` / `10-results-presentation.json`：检查修订稿是否有明确结果章节、是否报告结构化统计指标、是否引用统计图/表、是否呈现 95% CI 或不确定性，并阻断没有统计比较却写出比较性结论的稿件。
- `10-claim-consistency.md` / `10-claim-consistency.json`：把修订稿中的强正向结论和 `04-hypothesis-outcome` 对齐；当结果是 `smoke_only`、`refuted_or_negative`、`inconclusive`、`untested` 或 `blocked_unverified` 时，阻断“证明/显著优于/支持假设”等越界表述。
- `10-release-metadata.md` / `10-release-metadata.json`：结构化记录代码仓库、许可证、版本、归档 DOI、数据访问说明和环境归档 URL。
- `10-code-data-availability.md` / `10-code-data-availability.json`：审计代码仓库、许可证、实验 runbook、结果产物、引用导出、数据/代码可用性声明和公开归档人工待办。
- `10-submission-check.md` / `10-submission-check.json`：静态检查修订稿 Markdown、TeX 基本结构、BibTeX、正文 citation key、结果呈现审计、统计图、代码/数据可用性和目标 venue 模板待办。
- `10-final-readiness.md` / `10-final-readiness.json`：比较修订前后分数、weak/unsupported claim 数量和延后任务，给出 `requires_human_evidence`、`requires_revision`、`ready_for_human_polish` 或 `ready_for_submission_check` 状态。

这一步把 review/improve 循环变成可审计 gate：即使系统生成了修订稿，只要仍有 `needs_human_evidence`、unsupported claim、claim traceability/citation grounding/citation coverage 阻断项、结果呈现或 claim consistency 阻断项、代码/数据可用性阻断项或投稿格式阻断项，就不会把它标为投稿就绪。`10-agent-claim-audit` 负责论文阶段责任追踪；`10-agent-deliberation` 当前只是确定性角色规则汇总，不是独立多智能体共识。缺失 owner 或规则汇总未通过会进入人工复核和投稿包证据，而不是自动抹掉 claim traceability 的结论。

Release metadata 可通过配置文件、CLI 或 Web 表单填写。CLI 示例：

```bash
PYTHONPATH=src python3 -m research_agent run \
  --topic "机械臂路径规划" \
  --release-code-repository-url "https://github.com/org/repo" \
  --release-code-archive-doi "10.xxxx/zenodo.xxxxx" \
  --release-code-license "MIT" \
  --release-code-version "v0.1.0" \
  --release-data-access-statement "This run uses the benchmark data described in 03-benchmark-adapters.md." \
  --llm-model "$OPENAI_MODEL"
```

如果这些字段缺失，`10-code-data-availability` 会继续保留发布元数据人工待办；如果 URL/DOI 格式错误，会作为阻断项进入最终 gate。
