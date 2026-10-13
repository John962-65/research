# A/B/C 对照评测汇总

- 模型: session-agent；judge: session-agent；dry_run: False
- 任务: subset=main, n=12, groups=['A', 'B', 'C1', 'C2']
- 沙箱: env 白名单 + rlimits；网络隔离: True（网络已通过 user+net namespace 隔离；文件系统未隔离（用户权限内可读）；容器运行时可用但尚未接入）
- 历史归档离线重算；不是修复后的新模型评测。任务子集小且已用于开发，不外推能力收益。

| 组 | 完成率 | 已评分任务acc | **全任务得分** | 全任务95% CI（数据集聚类） | context | var_F1 | rel | 无依据(可评) | 不可评 | LLM调用 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 100% | 0.4153 | 0.4153 | [0.1944, 0.6653] | 0.8333 | 0.7046 | 0.4583 | 0.0278 | 0 | 32 |
| B | 100% | 0.4236 | 0.4236 | [0.2, 0.675] | 0.8333 | 0.7212 | 0.4583 | 0.0 | 0 | 25 |
| C1 | 100% | 0.4153 | 0.4153 | [0.1944, 0.6653] | 0.8333 | 0.6907 | 0.4583 | 0.0 | 0 | 21 |
| C2 | 100% | 0.4236 | 0.4236 | [0.2, 0.675] | 0.8333 | 0.7212 | 0.4583 | 0.0 | 0 | 26 |

证据验证仅覆盖显式声明的断言；未声明断言不代表结论无风险。

- A：已复核断言 20；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- B：已复核断言 13；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C1：已复核断言 12；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}
- C2：已复核断言 11；验证通过/矛盾/不可验证比例 = 0.0/0.0/1.0；评分缺失 0；逐步异常计数 {'parse_failures': 0, 'tool_execution_failures': 0, 'tool_budget_exhaustions': 0, 'transport_failures': 0}

- **C1_vs_A**：全任务 n=12（未完成记 0），delta=0.0，CI (0.0, 0.0)
- **C1_vs_B**：全任务 n=12（未完成记 0），delta=-0.0083，CI (-0.0273, 0.0)
- **C2_vs_C1**：全任务 n=12（未完成记 0），delta=0.0083，CI (0.0, 0.0273)

仅重算汇总、置信区间与已保存轨迹异常；原始答案和官方评分未改，未重新运行模型或judge。
