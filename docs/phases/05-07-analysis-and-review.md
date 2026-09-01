<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 05-07：结果分析、论文与独立复核

## Phase 4: Paper Review and Claim Audit

第四阶段在论文草稿之后自动生成审稿式复核：

- `07-paper-review.md`：模拟审稿决定、总分、分项评分、优点、问题、必须修改项和 Claim-Grounding 审计表。
- `07-paper-review.json`：结构化保存审稿分数、revision 清单和每条关键 claim 的支撑状态。
- `07-paper-review-calibration.md/json`：把审稿分数和决定与 unsupported/weak claims、实验后决策、假设结果和执行模式对齐，标记过宽自评并把校准任务传入修订计划。

复核阶段参考 AI Scientist 类项目的 simulated review 思路，并结合文献/实验产物做 claim-grounding 检查。LLM 可用时会生成结构化审稿 JSON；如果 LLM 调用失败或超时，本次 run 会失败并写入诊断。只有在模型已成功返回但格式不合格时，系统才会使用规则审计草稿中的关键主张，标记 supported、weak 或 unsupported，避免没有复核就直接把草稿当成最终论文。

论文写作阶段会把 `01-context` 的 citation key 和 `agent_roles` 注入写作提示；AI 草稿如果没有使用可追踪 `[citation_key]`，会被视为格式不合格并改用规则草稿。规则草稿会在正文和“参考证据”小节写入稳定 key，并保留多智能体责任边界，方便后续 claim traceability、agent owner audit 和参考文献核对。

复核之后系统会继续生成：

- `08-revision-plan.md`：把必须修改项和 weak/unsupported claims 转成可执行修订任务、验收检查和下一轮修改提示。
- `08-revision-plan.json`：结构化保存任务 ID、严重性、章节、动作、证据引用和 readiness 状态。

这一步借鉴 Agent Laboratory 类项目的人类反馈闭环：复核不是终点，而是下一轮写作和实验补强的输入。
