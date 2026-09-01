<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 13-14：平台审计与完整性交付

## Phase 13: Agent Contract, LLM Trace, Run Economics and Scorecard

第十三阶段先做平台阶段契约、LLM 调用覆盖和运行成本/耗时审计，再把一个 run 的关键证据汇总为统一分数卡：

- `13-agent-stage-contract.md` / `13-agent-stage-contract.json`：按开源科研 agent 模式检查 planning、literature grounding、human gate、idea exploration、experiment design、execution evidence、paper review loop、release reproducibility 和 observability/resume 九个阶段契约。
- `13-agent-trajectory.md` / `13-agent-trajectory.json`：按阶段聚合 run-manifest 事件、关键 gate 状态、缺失产物、阻断和人工待办，方便像实验 trajectory 一样复盘 run。
- `13-llm-trace-audit.md` / `13-llm-trace-audit.json`：检查关键阶段是否都有成功 LLM 调用，失败/预算拦截和 AI disclosure 不一致会阻断。
- `13-run-economics-audit.md` / `13-run-economics-audit.json`：按阶段汇总 LLM 调用、估算 token、耗时、预算压力和可选美元成本，用于判断一次 run 的资源消耗是否可解释。
- `13-agent-observability-audit.md` / `13-agent-observability-audit.json`：检查 manifest/state 一致性、artifact inventory、LLM budget pressure、human gate、实验 runtime trace、诊断恢复和 repair queue 可追踪性。
- `13-research-scorecard.md` / `13-research-scorecard.json`：按文献证据、idea 探索、实验/benchmark、论文质量、复现/release、投稿就绪六个维度给出 0-100 分、状态、证据和下一步动作；若 `12-repair-queue` 仍有 block，投稿就绪维度会保持 blocked。

这一步借鉴 MLAgentBench/AIRS-Bench 式可比较评估与 Agent Laboratory 的人工闭环思路。阶段契约用于发现平台流程缺口，分数卡用于定位证据强弱；二者都不是科学结论，也不会替代人工审稿。

## Phase 14: Run Integrity Audit

第十四阶段检查 run 本身是否可信：

- `14-run-integrity-audit.md` / `14-run-integrity-audit.json`：最终检查必需产物、顶层 JSON 可读性、人工 gate 顺序、上游文献/gate 修复是否早于下游 idea/实验/论文产物、manifest 产物 hash、投稿包、LLM ledger 和 `run-config.json` 是否保存 API key。

这一步把“流水线跑完了”和“这个 run 可采信”分开：如果完整性审计为 `block`，说明需要先修复流程或产物问题，再采信后续论文、分数卡或投稿包。

## Agent Stage Contract Audit

`13-agent-stage-contract.md/json` 会把 AI Scientist、Agent Laboratory、PaperQA2 和 MLAgentBench 这类开源科研 agent 项目的关键模式转成阶段契约：研究计划、grounded 文献、人类 gate、idea 探索、实验设计、执行证据、论文复核闭环、代码/数据归档和可恢复观测性。它不同于 `13-research-scorecard` 的综合打分，也不同于 `14-run-integrity-audit` 的文件完整性检查；它回答的是“这个 run 是否满足一个科研 agent 平台应有的阶段职责”。

如果状态为 `block`，优先处理 `blocking_issues`，再使用 `repair-resume` 或 checkpoint resume 重新生成受影响阶段。状态为 `needs_human_review` 时，说明自动产物完整但仍存在人工待办，例如真实 benchmark、投稿格式或代码/数据归档信息。

`13-agent-trajectory.md/json` 会把 `run-manifest` 的底层事件和关键 gate/audit 状态聚合成面向人工检查的阶段轨迹：planning、literature grounding、human gate、ideation、experiment design、execution/analysis、writing/review 和 release/observability。它借鉴 AI-Scientist-v2/MLGym 这类项目保留实验树或 trajectory 以便复盘的做法，用来快速定位“当前 run 走到哪、哪段 warning/block、下一步该看哪个产物”。

## LLM Trace Audit

`13-llm-trace-audit.md/json` 会检查 `run-llm-ledger` 是否覆盖关键科研阶段：research planning、literature synthesis、idea generation、experiment planning、paper writing、paper review loop 和 paper revision。若已生成这些阶段产物但 ledger 中没有对应 `success` 调用，或存在 `failed` / `budget_exceeded` 调用，状态会变为 `block`，并进入 `12-repair-queue`、`13-research-scorecard`、投稿包和 `14-run-integrity-audit`。

该审计不保存或读取完整 prompt/response，只使用 purpose、状态、长度和 hash。模型成功返回后再做结构化 JSON 修复不算离线 LLM 兜底；但模型完全缺席、失败或预算拦截不能被当作完成的自动科研 run。

## Run Economics Audit

`13-run-economics-audit.md/json` 会把 `run-llm-ledger` 按科研阶段汇总为调用数、成功/失败/预算拦截、输入/输出字符数、估算 token、阶段耗时和可选美元成本。Token 估算使用 `ceil(chars / 4)`，只用于 run 级趋势和预算诊断，不替代供应商账单。

默认只报告 token 和耗时。如果在配置中填写 `llm.input_cost_per_million_tokens` 与 `llm.output_cost_per_million_tokens`，审计会同时估算总成本和阶段成本；缺失 ledger、失败调用或预算拦截会进入 `12-repair-queue`。

## Agent Observability Audit

`13-agent-observability-audit.md/json` 会把 `state.json`、`run-manifest`、`run-llm-ledger`、`run-config`、人工 approval、执行 approval、`04-experiment-runbook`、诊断/恢复计划和 repair queue 串成运行可观测性审计。它重点回答“这个 run 失败、卡住、预算耗尽或需要恢复时，是否有足够轨迹让人和 agent 继续处理”，而不是评价论文质量。

状态为 `block` 时会进入 `12-repair-queue`，通常表示 manifest/ledger/human gate/runbook/诊断恢复断链。状态为 `review_required` 时多半是 LLM 预算接近上限、旧 run 缺少 run-config、artifact trace 不完整或 repair queue 仍需人工处理。

## Open-Source Lesson Compliance

`13-open-source-compliance.md/json` 会逐条检查 `00-open-source-lessons` 中从 AI-Scientist-v2、Agent Laboratory、PaperQA2/OpenScholar 和 MLAgentBench/MLE-bench 类项目吸收的约束是否真的落到本次 run 的产物里。`00-open-source-lessons.json` 同时保存 `contract_summary`，记录本轮必须覆盖的参考项目、project evidence 和 lesson id；`13-open-source-compliance` 会先校验这个 contract 完整性，再检查各阶段产物，防止通过删减 lesson 绕过外部项目约束。它会核对开源项目 provenance、结构化 idea->experiment 链路、query/source 覆盖审计、citation grounding、human feedback compliance、execution safety、benchmark result schema、LLM trace/run economics、observability、AI disclosure 和领域 benchmark 约束。缺少 `contract_summary`、`project_evidence`、仓库 URL 或证据目标文件时会阻断；只有内置编目而没有实时 commit 核对时不会阻断，但报告会保留 provenance 状态，避免把未刷新版本误当成强证据。

状态为 `block` 或 `needs_human_review` 时会进入 `12-repair-queue` 和 `13-research-scorecard`。这样外部项目经验不只是 prompt 里的建议，而是会成为可修复、可复查的阶段契约。
