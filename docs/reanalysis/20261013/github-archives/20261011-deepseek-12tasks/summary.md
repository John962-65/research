# A/B/C 对照评测汇总

- 模型: deepseek-flash；judge: session-agent；dry_run: False
- 任务: subset=main, n=12, groups=['A', 'B', 'C1', 'C2']
- 沙箱: env 白名单 + rlimits；网络隔离: True（容器级隔离（bwrap）：网络+挂载空间全隔离，系统目录只读，仅数据目录与工作目录可写——生成代码无法读取绑定集之外的宿主文件）
- 历史归档离线重算；不是修复后的新模型评测。任务子集小且已用于开发，不外推能力收益。

| 组 | 完成率 | 已评分任务acc | **全任务得分** | 全任务95% CI（数据集聚类） | context | var_F1 | rel | 无依据(可评) | 不可评 | LLM调用 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 42% | 0.5714 | 0.2381 | [0.0, 0.4796] | 1.0 | 0.9714 | 0.6 | 0.0 | 7 | 59 |
| B | 17% | 0.0 | 0.0 | [0.0, 0.0] | 1.0 | 0.5 | 0.0 | 0.0 | 10 | 60 |
| C1 | 42% | 0.5 | 0.2083 | [0.0, 0.4583] | 1.0 | 0.8 | 0.5 | 0.0167 | 7 | 66 |
| C2 | 33% | 0.575 | 0.1917 | [0.0, 0.4] | 1.0 | 0.95 | 0.625 | 0.0 | 8 | 64 |

证据验证仅覆盖显式声明的断言；未声明断言不代表结论无风险。

- A：已复核断言 39；验证通过/矛盾/不可验证比例 = 0.0256/0.0/0.9744；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- B：已复核断言 3；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C1：已复核断言 41；验证通过/矛盾/不可验证比例 = 0.0488/0.0244/0.9268；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C2：已复核断言 27；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}

- **C1_vs_A**：全任务 n=12（未完成记 0），delta=-0.0298，CI (-0.3571, 0.3766)
- **C1_vs_B**：全任务 n=12（未完成记 0），delta=0.2083，CI (0.0, 0.4583)
- **C2_vs_C1**：全任务 n=12（未完成记 0），delta=-0.0167，CI (-0.3636, 0.2727)

仅重算汇总、置信区间与已保存轨迹异常；原始答案和官方评分未改，未重新运行模型或judge。
