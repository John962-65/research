# A/B/C 对照评测汇总

- 模型: deepseek-flash；judge: deepseek-flash；dry_run: False
- 任务: subset=main, n=12, groups=['A', 'B', 'C1', 'C2']
- 沙箱: env 白名单 + rlimits；网络隔离: True（容器级隔离（bwrap）：网络+挂载空间全隔离，系统目录只读，仅数据目录与工作目录可写——生成代码无法读取绑定集之外的宿主文件）
- 历史归档离线重算；不是修复后的新模型评测。任务子集小且已用于开发，不外推能力收益。

| 组 | 完成率 | 已评分任务acc | **全任务得分** | 全任务95% CI（数据集聚类） | context | var_F1 | rel | 无依据(可评) | 不可评 | LLM调用 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 17% | 0.0 | - | - | 0.5 | 0.875 | -0.5 | 0.5 | 10 | 62 |
| B | 25% | 0.0 | - | - | 0.3333 | 0.8 | -0.6667 | 0.1111 | 9 | 62 |
| C1 | 17% | 0.0 | - | - | 0.5 | 0.8 | -0.5 | 0.1666 | 10 | 65 |
| C2 | 17% | 0.0 | - | - | 0.0 | 0.9286 | -0.5 | 0.0 | 10 | 65 |

证据验证仅覆盖显式声明的断言；未声明断言不代表结论无风险。

- A：已复核断言 6；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 1；逐步异常计数 {'parse_failures': 52, 'tool_execution_failures': 1, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- B：已复核断言 21；验证通过/矛盾/不可验证比例 = 0.0952/0.0/0.9048；评分缺失 2；逐步异常计数 {'parse_failures': 49, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C1：已复核断言 9；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 1；逐步异常计数 {'parse_failures': 48, 'tool_execution_failures': 1, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C2：已复核断言 6；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 1；逐步异常计数 {'parse_failures': 46, 'tool_execution_failures': 2, 'tool_budget_exhaustions': 0, 'transport_failures': 0}

- **C1_vs_A**：全任务 n=12（未完成记 0），delta=None，CI None
- **C1_vs_B**：全任务 n=12（未完成记 0），delta=None，CI None
- **C2_vs_C1**：全任务 n=12（未完成记 0），delta=None，CI None

仅重算汇总、置信区间与已保存轨迹异常；原始答案和官方评分未改，未重新运行模型或judge。
