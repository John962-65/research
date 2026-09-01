<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 00：研究计划与领域画像

## Phase 0: Research Plan and Domain Profile

第零阶段在文献检索前先读取人工 brief、历史 run 复盘和外部开源科研 agent 项目经验，再生成领域研究计划：

- `00-human-brief.md` / `00-human-brief.json`：把用户在 Web/CLI/config 中提供的研究偏好、人工约束、成功标准、资源限制和已知风险固化为可审计输入，并在 `00-research-plan` 之前注入 planning context。
- `00-prior-run-lessons.md` / `00-prior-run-lessons.json`：从 `runs/` 历史记录中提取文献薄弱、LLM 配置失败、实验管理阻断、人工约束未落实、smoke-first 分支、模拟证据、benchmark 缺口、citation grounding、投稿/发布阻断等可继承经验，并转成当前 run 的 agent 约束文本。
- `00-prior-run-library.md` / `00-prior-run-library.json`：按当前课题检索 `runs-library` 中的相关历史论文、失败案例和待修复 run，给 `00-research-plan` 提供可复用 benchmark/baseline/失败经验提示；它只作为 planning context，不会被当成本轮 citation 或论文证据。
- `00-open-source-lessons.md` / `00-open-source-lessons.json`：把 AI-Scientist-v2、PaperQA2 等开源科研 agent 项目的关键做法固化成本平台约束，例如结构化 idea->experiment 闭环、生成代码 sandbox、chunk-level citation grounding、多源 metadata/rate-limit 诊断、历史记忆/cache 复用和 AI 使用披露；同时记录每个参考项目的仓库 URL、证据目标文件和 provenance 状态。默认 run 不联网抓取 GitHub，使用内置编目保证离线可运行；如果要把外部项目版本当作强证据，需要人工或后续工具刷新 branch/commit/关键文件核对记录。
- `00-research-plan.md`：领域画像、英文 scholarly search queries、benchmark/数据集/任务、baseline、指标、约束、风险和成功标准。
- `00-research-plan.json`：结构化研究计划，供后续检索和实验计划复用。

该阶段借鉴 PaperQA/OpenScholar/STORM 类项目对检索计划和引用 grounding 的重视，以及 AI Scientist/Agent Laboratory/AgentRxiv 类项目对人工 notes、迭代研究记忆、实验模板和 benchmark 的重视。系统会优先用 LLM 生成计划；如果 LLM 调用失败或超时，本次 run 会失败并写入诊断，而不会切到离线 LLM 兜底。只有在模型已成功返回但 JSON 结构不合格时，系统才会用规则画像补齐常见领域信息，例如机械臂路径规划、轴承故障诊断和科研 agent 的 benchmark、baseline 和指标。后续在线文献检索会优先使用研究计划中的英文检索式，实验计划也会吸收其中的 benchmark、baseline 和 metric。

`00-human-brief`、`00-prior-run-lessons`、`00-prior-run-library` 和 `00-open-source-lessons` 不会静默修改配置；它们会把人工约束、历史风险、历史成果库参考和外部项目约束写入 `constraints`、`risks`、`success_criteria`，并作为后续 idea 阶段的上下文。这样可以复用用户给定边界、上一轮人工 gate、失败实验、弱文献、citation grounding 和已生成论文的 benchmark/baseline 经验，同时保留可审计记录。

可以单独生成或刷新开源项目 provenance：

```bash
PYTHONPATH=src python3 -m research_agent open-source-lessons \
  --topic "机械臂路径规划" \
  --out runs/open-source-provenance-check

# 可选：联网核对 GitHub 默认分支、HEAD commit 和关键文件；失败会写成 unverified，不阻断正式 run
GITHUB_TOKEN=... PYTHONPATH=src python3 -m research_agent open-source-lessons \
  --topic "机械臂路径规划" \
  --out runs/open-source-provenance-check \
  --refresh-github
```

如果历史 run 的 `03-review-constraint-compliance` 因人工 brief 或 review 约束未落实而阻断，下一轮 preflight 会要求当前表单补 `human_constraints`、`human_resource_limits` 或相关 human brief 字段；补齐后会显示该历史风险已被当前配置承接。
