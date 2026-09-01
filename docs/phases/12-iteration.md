<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 12：下一轮迭代与修复队列

## Phase 12: Next Iteration Plan

第十二阶段把最终审计结果转成下一轮可执行计划：

- `12-next-iteration-plan.md` / `12-next-iteration-plan.json`：读取最终 gate、代码/数据审计、投稿格式检查、投稿包、实验 runbook、experiment manager 和 benchmark plan，输出下一轮状态、优先任务、建议重跑命令、停止条件和继承说明；`02-experiment-manager` 的 smoke-first 策略、实验计划约束和下一轮候选分支会进入 carry-forward notes。
- `12-repair-queue.md` / `12-repair-queue.json`：把 query execution、文献 metadata、补检索、seed intake、idea audit、人工约束落实、实验审计、安全审计、环境快照、结果验证、benchmark result schema、benchmark 证据、hypothesis outcome、论文 grounding、claim consistency、agent observability、release 和投稿包等审计汇总成结构化修复队列，标出 `severity`、来源产物、目标产物、重跑入口、自动化/人工职责，以及是否阻断投稿或下游阶段。
- `12-repair-resolution-audit.md` / `12-repair-resolution-audit.json`：如果本轮来自 `repair-resume`，把原修复项与新生成的 `12-repair-queue` 对比，确认原来源/类别是否仍然阻断；未闭环会进入 scorecard 和 stage contract。
- `12-repair-resume-plan.md` / `12-repair-resume-plan.json`：触发 `repair-resume` 时生成，记录最早重跑入口、将清理/已清理的产物、供下一轮 agent 使用的 `repair_context`、是否需要重新人工批准 review gate 或执行 gate，以及恢复后的停止条件。

典型状态包括：

- `needs_human_evidence`：必须先补文献、真实实验或删除 unsupported claim。
- `needs_real_benchmark_iteration`：当前证据仍偏模拟或 benchmark 未接入，下一轮应优先接真实任务集。
- `needs_targeted_iteration`：需要处理代码/数据、投稿格式或打包阻断项后从 checkpoint resume。
- `ready_for_submission_upload`：可以进入人工投稿系统上传，但仍需完成 `submission-package/CHECKLIST.md`。
- `ready_for_next_research_question`：当前 run 可归档，适合开启新课题。

这一步让 Agent Laboratory 式人工反馈、AI Scientist 式 review/improve 循环和 MLAgentBench 式实验可复现要求连接起来：系统不会只给一个“完成”状态，而会明确下一轮该补什么、谁处理、重跑哪些命令、满足什么停止条件。

`12-repair-queue` 更偏机器可执行：`blocked_repair_required` 表示至少一个 block 任务未清零，不能把当前 run 当作最终投稿版本；`needs_repair` 表示没有 block，但还有 high/medium 修复或人工确认项；`pass` 表示当前审计队列没有自动识别的修复项。

`12-repair-resolution-audit` 是 repair-resume 的闭环检查：没有应用 repair-resume 时为 `not_applicable`；原修复项已从新队列消失时为 `pass`；原来源/类别仍以 block/high/medium 出现时会标记为 `block` 或 `review_required`。

`repair-resume` 借鉴 AI Scientist 的 review/improve 循环和 Agent Laboratory 的人工 checkpoint 思路，但不会直接跳过 gate。它会清理旧产物、把修复队列和来源审计的失败原因注入下一轮 ideation/experiment planning 上下文，再恢复流水线；文献 gate 与执行 gate 仍按原规则等待人工确认。

`repair-resume-backlog` 是只读 triage，不会删除产物、批准 gate、恢复 pipeline 或执行实验。它会把活跃 repair queue 按优先级列出，并区分 `ready_to_apply` 和 `needs_preconditions`：前者已有可用恢复计划，后者还缺文献修复 query/seed、benchmark manifest、allowed command 或 gate 重批标记等恢复前置条件。Web 端只展示枚举化状态、计数和安全命令，不暴露 repair_context、manager queue、绝对路径或内部 action 文本。

当修复队列来自 `01-literature-search-feedback.json` 时，`repair-resume` 会先把其中 owner 为 `agent` / `agent+human` 且带 query 的 `retrieval_repair_tasks` 复制进 `12-repair-resume-plan.json`，同时保留 `next_run_config` 中推荐的 `literature_provider`、sources、`max_papers` 和 `max_search_queries`。其中 `query_execution_repair` 会直接承接 `01-query-execution-audit` 中 no source、no candidate 或 weak hit 的 selected query，避免只给泛化补检索建议。如果 `01-seed-paper-intake.json` 显示 curated seed 角色覆盖不足，`repair-resume` 也会把缺失的 review/benchmark/baseline/recent 角色转成检索修复 query，并合并进下一次 `extra_search_queries`；历史 run 即使没有 `01-seed-paper-intake.json`，也会从 `01-literature-quality`/`01-literature-curated` 提取候选 DOI/URL seed，写入 `12-repair-resume-plan.json` 的推荐 seed，并在应用 repair-resume 建议时合并进下一轮 `seed_papers`。清理旧 `01-literature*` 产物后，下一次文献阶段会采用这些推荐配置做安全升级，并把 agent 检索修复任务作为 bounded rescue search 的额外检索式执行；Web 的“应用检索建议”会把推荐配置、Search feedback Top queries、`01-literature-rescue-plan` 的 evidence-role 补检索式、未闭环补检索 query、seed 角色补检索式，以及从 `01-literature-quality`/`01-literature-curated` 提取的候选 DOI/URL seed 写回左侧表单。候选 seed 会优先补齐缺失的 review/survey、benchmark/dataset、baseline/method 和 recent 角色，然后再按质量分补足数量。CLI 也可用 `--max-search-queries`、重复的 `--extra-search-query`、`--extra-search-queries-file`、`--seed-paper` 或 `--seed-papers-file` 承接这些检索式和种子文献，供新 run、checkpoint resume 或人工修复后重跑使用。人工 seed/source 修复任务仍由人工处理；候选 seed 写入表单后仍需人工核对题名、年份和相关性，且新的 `01-review-gate.md` 仍必须重新批准后才能进入 idea/实验。

当修复队列来自 `03-benchmark-readiness.json`、`04-benchmark-result-schema-audit.json`、`04-benchmark-evidence-audit.json` 或 `03-execution-safety-audit.json` 时，`repair-resume` 会额外生成 `recommended_execution_config`：从旧 `run-config.json`、`03-benchmark-adapters.json`、`03-benchmark-readiness.json` 或 execution safety 审计中继承 `execution_mode`、`allowed_commands`、`execution_repeats`、`timeout_seconds` 和已有 `benchmark_manifest_paths`。如果是 benchmark 修复但旧 run 没有 manifest，建议会切到 `benchmark` 模式并让 preflight/execution safety 明确阻断缺失 manifest；如果 paper-grade benchmark 缺 candidate/baseline/ablation role，则 `12-repair-resume-plan` 会给出带 TODO 的 manifest scaffold，供人工补真实 benchmark URL、dataset、citation、license、命令和 metrics 后再加入配置。Web 的“预览修复”会只读生成 `12-repair-resume-plan`；确认后可点“应用修复建议”把推荐文献配置、补检索式、seed papers、执行模式、白名单、重复次数、超时和 benchmark manifest 回填到左侧表单。这个按钮只更新表单，不会启动 run、批准 review gate 或批准执行 gate；旧 `03-execution-approval.*` 会被清理，local/benchmark 命令仍必须重新人工批准后才会运行。
