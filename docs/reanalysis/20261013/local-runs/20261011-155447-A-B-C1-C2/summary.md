# A/B/C 对照评测汇总

- 模型: deepseek-flash；judge: session-agent；dry_run: False
- 任务: subset=main, n=4, groups=['A', 'B', 'C1', 'C2']
- 沙箱: env 白名单 + rlimits；网络隔离: True（容器级隔离（bwrap v3）：网络+挂载空间全隔离；数据快照文件级只读绑定（agent 写数据文件被内核拒绝）；仅工作目录可写；site-packages 精确挂载）
- 历史归档离线重算；不是修复后的新模型评测。任务子集小且已用于开发，不外推能力收益。

| 组 | 完成率 | 已评分任务acc | **全任务得分** | 全任务95% CI（数据集聚类） | context | var_F1 | rel | 无依据(可评) | 不可评 | LLM调用 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 25% | 1.0 | 0.25 | [0.0, 0.75] | 1.0 | 1.0 | 1.0 | 0.0 | 3 | 23 |
| B | 50% | 0.0 | 0.0 | [0.0, 0.0] | 1.0 | 0.0 | 0.0 | 0.0 | 2 | 14 |
| C1 | 75% | 0.1111 | 0.0833 | [0.0, 0.25] | 1.0 | 0.2222 | 0.1667 | 0.0 | 1 | 12 |
| C2 | 25% | 0.0 | 0.0 | [0.0, 0.0] | 1.0 | 0.0 | 0.0 | 0.0 | 3 | 19 |

证据验证仅覆盖显式声明的断言；未声明断言不代表结论无风险。

- A：已复核断言 3；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 6, 'tool_execution_failures': 2, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- B：已复核断言 0；验证通过/矛盾/不可验证比例 = None/None/None；评分缺失 0；逐步异常计数 {'parse_failures': 7, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C1：已复核断言 19；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 2, 'tool_execution_failures': 1, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C2：已复核断言 5；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 9, 'tool_execution_failures': 2, 'tool_budget_exhaustions': 0, 'transport_failures': 0}

- **C1_vs_A**：全任务 n=4（未完成记 0），delta=-0.1667，CI (-0.75, 0.1667)
- **C1_vs_B**：全任务 n=4（未完成记 0），delta=0.0833，CI (0.0, 0.25)
- **C2_vs_C1**：全任务 n=4（未完成记 0），delta=-0.0833，CI (-0.25, 0.0)

仅重算汇总、置信区间与已保存轨迹异常；原始答案和官方评分未改，未重新运行模型或judge。
