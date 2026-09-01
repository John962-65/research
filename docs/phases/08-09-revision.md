<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 08-09：修订计划与修订稿

## Phase 9: Revised Paper Draft

第九阶段把 `08-revision-plan` 应用回论文草稿：

- `09-revised-paper.md` / `09-revised-paper.tex`：基于修订计划生成的下一版论文草稿。自动修订会降级过强 claim、补充修订执行记录，并明确哪些任务不能自动完成。
- `09-revision-report.md` / `09-revision-report.json`：逐条记录修订任务的处理状态，例如 `applied_in_draft`、`draft_adjusted`、`needs_human_evidence` 或 `needs_human_verification`。
- `09-revision-response-audit.md` / `09-revision-response-audit.json`：检查 `08-revision-plan` 中每条任务是否在 `09-revision-report` 有结果、是否在修订稿“修订执行记录”中留下任务 ID 或待补证/人工核对痕迹；高优先级任务静默消失会进入 block。

这一步参考 AI Scientist 类项目的 review/improve 循环和 PaperQA2 式证据边界：自动评审不只是打分，而是反馈到下一版稿件，并留下逐条回应证据。系统不会自动编造新文献或真实实验；缺证据的任务会保留为人工补证项，并由修订响应审计传入投稿检查、repair queue、scorecard、stage contract 和投稿包。
