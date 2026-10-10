# 示例：PACO 多机械臂规划长尾诊断（离线演示）

演示 Research Copilot 的完整 P1 闭环（**全程离线，无需 LLM**；输出会明确标注离线模式）。

```bash
bash run_demo.sh
```

场景（虚构演示数据，公式化生成、可复现）：
- `paco`（候选）与 `baseline` 两组，相同 200 个查询、相同种子（可配对）；
- paco 总体更快（×0.85），但 3% 查询存在 2 倍长尾（均值优势仍在，尾部风险真实）；
- paco 组测试时 `arm_count` 系统性偏高（**混杂因素**，诊断会暴露）；
- 少量 timeout 行（诊断会报告而非忽略）。

演示流程与你会看到的关键输出：

1. `generate_demo_data.py` 生成 `results.csv` + `manifest.json`（声明指标方向）；
2. `project create` → 项目 ID；
3. `material import` → 材料登记（sha256 固定 + 方向声明自动提取）；
4. `diagnose --no-llm` → 确定性观测 + 经三层校验的发现：
   - 组间比较（配对、方向已声明）→ `statistical_finding`；
   - paco 组长尾被检出并定位到查询；
   - 混杂因素（arm_count 组间不均衡）被暴露；
   - timeout 计数被报告（不隐藏）；
5. `question confirm` → 人工确认证据缺口（diagnosis 只能提出 proposed 问题）；
6. `hypothesis generate --no-llm` → 从发现的竞争性解释生成竞争假设（互链 + 证伪条件）；
7. `experiment plan --no-llm` → 实验候选（六维透明评分；离线草稿明确标注
   `needs_revision` 与缺失字段——不假装完整）；
8. `state` → 研究状态报告（已证实 / 待验证 / 证据不足 / 待研究问题）；
9. `decision record` → 科研决策留痕。

`data/` 为运行产物（gitignore），可随时删除重跑。

接入真实 LLM 后，重跑 `diagnose`（去掉 `--no-llm`）：LLM 发现会经过三层证据校验，
引用不存在、数字不符、或含无依据因果机制的发现会被降级为 `unverified_conjecture`，
不会写成研究发现。
