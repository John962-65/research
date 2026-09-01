<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 02-03：Idea 生成与实验计划

## Phase 3: Evidence-Grounded Ideas and Experiment Plans

第三阶段把人工批准后的 idea/实验阶段改成文献证据约束：

- `02-research-gap-map.md/json`：把 review.gaps、文献 coverage 缺失、人工审核约束和 RAG chunk 合成研究空白矩阵；每个 gap 都标注 evidence strength、testability、baseline、benchmark/data、指标、检索补救建议和实验提示。Idea 生成会优先围绕 `ready` gap。
- `02-agent-team.md/json`：根据研究计划、文献覆盖、gap map、人工约束和执行模式分配多智能体任务；内置 literature scout、evidence curator、gap analyst、method architect、benchmark engineer、statistician、skeptical reviewer 和 manuscript editor，记录每个 agent 的任务、优先级、输入/输出产物和 handoff。它还写入 `task_routes`，把 literature repair、gap-to-idea、benchmark execution、claim boundary review、paper deliberation 和 release reproducibility 路由到不同 primary/support agent 小队。Idea 生成会读取该分配并写入 `agent_roles`。
- `02-ideas.md`：每个 idea 都包含文献依据 citation key、证据 chunk、对齐的研究空白、baseline 和实验草案。
- `02-ideas.json`：结构化保存 `evidence_keys`、`evidence_chunks`、`gap_alignment`、`baseline`、`agent_roles` 和 `experiment_sketch`。
- `02-novelty-audit.md/json`：把每个 idea 与已纳入文献标题/摘要做相似度审计，标记 `likely_novel`、`review_required` 或 `likely_duplicate`；高重复风险会降低探索图分支得分。
- `02-idea-audit.md/json`：检查每个 idea 的 citation key、evidence chunk、baseline、评估指标、实验草案和人工审核约束覆盖；不可核对证据会被标记为 `block` 并在探索图中强力降权。
- `02-exploration-map.md/json/svg`：把候选 idea 转成研究分支探索图，记录综合评分、选中分支、淘汰分支、警告和可视化路径。
- `02-experiment-manager.md/json`：把探索图、idea audit 和 novelty audit 汇总成实验管理决策，记录本轮只扩展哪个分支、是否必须 smoke-first、下一轮候选分支和注入 `03-experiment-plan` 的约束。
- `03-experiment-plan.md`：根据选中 idea 生成领域相关实验目标、变量、指标、协议和 baseline。
- `03-experiment-plan.json`：结构化实验计划，保留安全模拟命令入口，并继承选中 idea 的 `agent_roles`。
- `03-agent-handoff-audit.md/json`：执行前检查 `02-agent-team`、选中 idea 和 `03-experiment-plan` 的多智能体 handoff 是否连通；完全缺失 assignment、idea roles 或 plan roles 会阻断，角色族覆盖不足则要求人工复核并降级 claim。
- `03-review-constraint-compliance.md/json`：把人工审核 notes 和 `00-human-brief` 中的约束、成功标准、资源限制、风险映射到选中 idea 和实验计划；高优先级约束缺失会进入 `block`，并由实验审计阻止继续执行。
- `03-experiment-audit.md/json`：在执行实验前审计 baseline 公平性、metric 对齐、命令结构、文献覆盖、人工约束落实、消融计划和预注册；`block` 状态会阻止进入实验执行。
- `03-idea-experiment-contract.md/json`：在 benchmark readiness 之后、执行批准之前，把 `02-exploration-map` 选中的 idea、证据 key、baseline、metric、candidate/baseline/ablation 命令、预注册、消融和人工约束串成跨阶段契约；标题断链、无证据、占位 baseline、缺 candidate/baseline 命令或 readiness/preregistration/constraint block 会阻止进入实验执行。
- `03-execution-approval.md/json`：当执行模式为 `local` 或 `benchmark` 时，在真正运行本地命令前列出待执行命令、预期产物和 execution safety 结果，必须人工批准后才会生成 `04-results*`。
- `03-ablation-plan.md/json`：检查 candidate、baseline、ablation 命令覆盖，给出领域相关消融变体和必要动作。
- `03-preregistration.md/json`：在实验执行前锁定 primary hypothesis、primary metrics、planned comparisons、排除/停止规则和计划指纹；恢复旧 run 且已有结果时会标记为 `posthoc_checkpoint`。
- `03-benchmark-plan.md/json`：列出推荐真实 benchmark/数据集、来源 URL、许可核对、接入步骤、风险和替换模拟器的人工任务。
- `03-benchmark-readiness.md/json`：在执行批准前检查 execution mode、benchmark manifest adapter、metric/baseline 对齐和 expected artifacts；`simulated`/`local` 会提示只能支撑 smoke/local 证据，`benchmark` 模式缺 manifest 或 adapter blocked 会标记为 `block`。

LLM 返回缺少证据字段时，系统会从 `01-context.json`、`02-research-gap-map.json` 和 `02-agent-team.json` 自动检索并补齐最相关 citation/chunk、baseline、gap alignment、agent roles 和实验提示；如果 LLM 调用失败或超时，本次 run 会失败并写入诊断。只有在模型已成功返回但没有可用 idea 时，系统才会优先用研究空白矩阵和多智能体任务分配生成领域相关结构化候选，其次才退回到文献主题和 review.gaps。探索图和 experiment manager 参考 AI Scientist-v2 式多方向探索与 experiment manager 思路，但当前实现是轻量分支评分、选择记录和 smoke-first 约束，不伪装成完整树搜索；`02-idea-audit` 会在分支选择前把无效证据、弱实验轮廓和未响应人工约束的 idea 暴露出来。`03-review-constraint-compliance` 参考 Agent Laboratory 对人工 notes/参与度的强调，把 human brief 和批准意见变成可审计约束，而不是只把文本塞进 prompt。`03-idea-experiment-contract` 参考 PaperQA/OpenScholar 的 evidence-before-synthesis 思路，把 idea 证据链是否真正落到实验计划里作为执行前 gate。实验执行命令仍由系统提供，避免让模型生成任意 shell 命令。Benchmark 接入计划用于把当前模拟模板迁移到真实公开任务集；代码/数据可用性审计会检查该计划是否存在。
