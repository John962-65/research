<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 11：投稿与归档包

## Phase 11: Submission and Archive Package

第十一阶段把最终稿、引用、图、实验结果、复现手册和审计报告汇总成一个可下载的投稿/归档包：

- `11-submission-package.md` / `11-submission-package.json`：列出包内文件、缺失项、阻断问题、人工上传前待办和推荐动作。
- `11-submission-package.zip`：可下载 ZIP，包含 `submission-package/README.md`、`CHECKLIST.md`、主文稿、TeX、BibTeX、结果、统计审计、实验 runbook、修订响应审计、citation grounding/coverage 审计、最终 gate、修复队列、代码/数据审计、投稿格式检查和 run manifest。
- `submission-package/README.md`：包说明和状态摘要。
- `submission-package/CHECKLIST.md`：人工投稿前清单。

该阶段参考 AI Scientist/Agent Laboratory 的端到端论文产出思路，以及 MLAgentBench/DeployBench 类 benchmark 对可复现交付物的要求。系统会打包已有证据，但不会把仍有阻断项的 run 伪装成可投；若最终 gate、代码/数据审计或投稿格式检查仍需人工处理，`11-submission-package.md` 会继续显示 `blocked` 或 `needs_human_submission_review`。
