# 评审规则验证与业务试用

此入口把两类证据分开：结构化规则反例验证，以及真实使用者的评审记录。
没有使用者数据时，报告必须为 `business_measurements.status=not_measured`。

## 离线规则案例

```bash
PYTHONPATH=src python3 -m research_agent.review_evaluation \
  --cases examples/review-evaluation-cases.json \
  --out runs/review-rule-evaluation.json
```

[案例集](../examples/review-evaluation-cases.json) 包括：正常比较、比较校验失败、执行失败、负结果、不确定结果、模拟证据、无覆盖、明确拒绝、旧版本覆盖、错误哈希、有效覆盖、必需角色缺失。
它直接调用实际 `build_experiment_decision_report` 与 `aggregate_final_decision`，并比较预先写好的期望结论。

[本次运行报告](evidence/review-rule-evaluation.json) 记录案例哈希、每例的实际与期望决策。
这些是作者编写的合成结构化输入；不验证从原始材料自动提取问题的准确率，也不代表独立专家基准、LLM 质量或企业收益。
`rule_seconds` 仅为本机规则执行耗时，不能用来计算人工效率提升。

## 可展示的案例顺序

1. 展示 `invalid_comparison` 的结构化校验失败，结果为 `repair_before_writing`。
2. 展示修复后 `valid_comparison` 的材料状态与结果 `proceed_to_paper`。
3. 展示 `explicit_rejection`、`stale_override`、`wrong_evidence_hash` 都不能放行。
4. 展示有效覆盖与原始阻断原因同时保留，说明机器建议、人工例外及其责任边界。

这只是可重放演示，不是实际用户研究。实际演示原始材料提取时，必须同时展示原文位置及人工核验结果。

## 真实试用协议

试用前冻结案例、规则版本、期望决策、计时起止点以及主要指标。请有相关经验的评审者独立标注期望结论，分歧先仲裁，再开始计时；不要看到系统输出后修改标准答案。

- 使用真实且已获授权、脱敏的实验材料，包括可接受与不可接受的比较。
- 同一参与者完成无辅助和有系统辅助两种条件；随机或交错安排顺序，优先使用难度相近的平行材料，避免直接重复记忆答案。
- 从打开材料计时，到提交最终决定结束。系统等待、修复与人工纠正的时间都计入，不删除失败任务。
- 同时记录错误放行、错误阻断与最终判断是否正确。速度提升不能抵消错误放行的增加。
- 参与者使用匿名 ID。保留规则版本、材料哈希、原始意见和录屏/时间记录供复查。

复制 [空白记录模板](../examples/review-session-template.csv)，填入真实观测：

| 字段 | 含义 |
| --- | --- |
| participant_id | 匿名参与者 ID |
| pair_id | 同一参与者的一对评审任务 ID |
| condition | `manual` 或 `assisted` |
| case_id | 案例文件中已标注的 ID |
| seconds | 实际总耗时，必须为正且有限 |
| decision | 使用者提交的实际决策代码 |

每对任务必须包含两种条件，且期望决策一致。导入器拒绝缺失配对、重复记录、未知案例、无效耗时，不会悄悄丢弃异常记录。

```bash
PYTHONPATH=src python3 -m research_agent.review_evaluation \
  --cases examples/review-evaluation-cases.json \
  --sessions /path/to/real-review-sessions.csv \
  --out runs/review-business-evaluation.json
```

报告提供各条件决策准确率、错误放行率、耗时中位数、配对节省时间中位数、参与者数和任务对数。
数据由使用者提供，系统无法独立验证真实性。当前仅输出描述性统计，不对重复任务作独立样本显著性检验。若要报告泛化效果，需要增加不同参与者与任务，并按参与者和任务聚类分析。

## 尚需真实环境完成

- 使用实际模型凭据跑一次完整 multi-agent canary，并检查六个独立角色的调用账本、证据引用、版本和最终裁决。
- 完成上述真实用户试用。离线规则案例和自动化测试不能替代这一步。
- 在此之前，简历可以写“建立规则反例验证及试用测量入口”，不能写未测得的效率提升比例或企业落地效果。
