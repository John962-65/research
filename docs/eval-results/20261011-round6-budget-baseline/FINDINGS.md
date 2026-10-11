# 第五轮验收修复 + 第六轮预算基线（2026-10-11，4 新鲜任务 × A/B/C1/C2）

## 验收修复（全部落地，127→本轮后 127 测试）

1. **CI 修复**：沙箱测试拆分——单元测试 mock which（不依赖宿主），bwrap 集成
   测试 skipif 明确跳过原因；CI 自动生成 test-evidence.json（GITHUB_SHA +
   自动 commit）——SHA 滞后问题根治。
2. **沙箱 v3**：数据快照文件级 **ro-bind**（保留相对结构——agent 旧代码
   glob('*.csv') 兼容；写同名文件被内核拒绝，实测 Read-only file system）；
   输出目录独立可写；site-packages 精确挂载（~/.local 整目录不再进入沙箱）；
   快照哈希清单（snapshot_manifest）；bwrap 绑定顺序修复。
3. **runner 异常按来源分类**（transport_failure 仅限连接/超时，其余
   executor_error）；全任务/配对 bootstrap 按真实数据集 ID（失败记 0 保留
   组内；配对差同为数据集分层 bootstrap、钳位 [-1,1]）。
4. **FINDINGS-4 措辞修正**（17/13 为失败现象分类，非已证根因）。

## 第六轮基线运行（新代码 + trace 全归档）

4 新鲜任务（archaeology PCA / intro_pathways 交互 / meta_regression 职称×2），
DeepSeek-flash 被测 + session-agent 盲判 judge。**16/16 trace.json 首次全量归档**。

| 组 | 完成率 | 成功任务acc | **全任务得分** | 失败分类 | LLM调用 |
|---|---|---|---|---|---|
| A | 25% | 1.0 | **0.25** | tool_loop_exhausted ×3 | 23 |
| B | 50% | 0.0 | **0.0** | tool_loop_exhausted ×2 | 14 |
| C1 | **75%** | 0.111 | **0.0833** | tool_loop_exhausted ×1 | 12 |
| C2 | 25% | 0.0 | **0.0** | tool_loop_exhausted ×3 | 19 |

配对差（全任务口径）：C1_vs_A = -0.167（CI [0, 0.17]）；C1_vs_B = +0.083。

## 如实解读（样本仅 4 任务，全部为方向信号）

1. **这批任务是 DeepSeek 的硬骨头**：4 组全部由 tool_loop_exhausted 主导（9/16
   组次），无 output_parse_failure（DSML 修复生效）——失败集中在 PCA/职称比例
   等列语义不明确的任务。
2. **完成率与精度反向**：C1 完成率最高（75%）但成功任务 acc 低（0.111）——
   C1 产出了更多"答案"但答对的少；A 完成率低但答对的 1 个是满分。全任务得分
   A 0.25 > C1 0.083。**按审查重算口径，本批 Copilot 仍无优势**。
3. **失败分类工作正常**：全部落入 tool_loop_exhausted，无 parse/transport——
   新执行器稳定，瓶颈回到"模型在难题上的探索预算"——正是审查建议的
   6 步 vs 12 步预算对照要回答的问题。
4. **trace 全量归档验证通过**：16/16 轨迹可审计（工具调用次数/代码/输出可核）。

## 结论

- 审查四项验收门槛全部完成（CI 绿、快照只读、分类有据、口径统一）；
- 本批 4 任务上 Copilot 无优势（全任务得分 A 最高）——如实报告；
- 下一步（审查建议的第六轮研究）：同模型同任务比较 6 步 vs 12 步预算 × A/B/C1/C2，
  回答"限制是科研分析能力还是执行预算"。
