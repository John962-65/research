# Research Copilot 路线图（P2 / P3 设计）

> 本轮交付为 P0 + P1-A + P1-B（见 README）。本文档是 P2/P3 的设计基线，
> 供下一轮实现时遵循；设计变更需先更新本文档再动代码。

## 阶段总览

| 阶段 | 开发目标 | 测试方法 | 完成标志 |
|---|---|---|---|
| P0 | 独立仓库、核心数据模型、凭据与证据安全 | 单元 + 安全测试 | 不依赖旧系统运行 ✅ |
| P1-A | 科研数据分析、问题诊断、假设生成 | DiscoveryBench A/B/C | 评测框架已实现；历史运行无稳定能力收益，执行器修复后须用新任务验证 |
| P1-B | 竞争假设管理、主动实验规划 | 合成反例 + 人工评估 | 可证伪的实验建议 ✅ |
| P2-A | 实验环境交互、结果反馈 | Science-Gym | 根据实验结果更新假设与下一步行动 |
| P2-B | 代码修改与自主科研实验 | ResearchGym | 真实实验迭代，客观衡量性能变化 |
| P3 | 完整科研流程与跨任务验证 | AstaBench E2E | 完整科研任务公开评测结果 |

## 两层能力（不可混淆）

- **第一层：科研分析能力** —— 输入已有数据，能否发现可信的科学关系？（DiscoveryBench 验证）
- **第二层：科研推进能力** —— 面对不确定的问题，能否选择值得做的实验、根据真实反馈更新假设、取得可量化的研究进展？（Science-Gym / ResearchGym 验证，**最终目标**）

第一层成绩好不代表第二层成立。任何阶段都不得只优化第一层分数。

## 硬性规则：每个核心 Agent 必须有对照实验

新增任何核心 Agent（诊断/假设/规划/决策……）时，必须在同一批任务上运行
`research-copilot evaluate` 风格的三组对照（A 普通 LLM+工具 / B 关闭该模块 / C 开启），
并报告：任务完成率、无依据结论比例、任务级指标（HMS 或后续环境指标）±95% CI、成本。
**若该模块未带来可测收益，回退或重设计该模块，而不是继续堆功能。**

## P2-A：实验环境交互（Science-Gym）

1. **研究循环调度器（自建，不复用任何旧系统 WorkflowEngine）**：
   `diagnose → hypothesize → plan → (human approve) → execute → ingest → decide → 循环`
   - 状态机复用 P1 的 ResearchState / Hypothesis / EvidenceEntry 模型；
   - 每轮循环写 decisions.jsonl（continue/refine/investigate/replicate/pivot/stop/report），
     人工覆盖永远可用；
   - 预算上限：每项目最大轮数、每轮最大 LLM 调用、最大执行时长。
2. **Experiment Workspace 渐进安全路径**（禁止从空实现直接跳到任意命令执行）：
   - 阶段 1：代码版本隔离（git worktree per experiment，记录 commit sha）；
   - 阶段 2：命令许可清单（白名单 + 无 shell 元字符 + 相对路径）；
   - 阶段 3：资源限制（超时、CPU/内存上限、输出截断）；
   - 阶段 4：人工批准门（diff 预览 → 人工批准 → 执行 → 证据留存 sha256）。
3. **结果回注**：执行产物（指标 JSON/CSV + 日志 + 环境/种子/commit）
   经 evidence 核验后入台账，逐假设判定 supports/contradicts/inconclusive；
   研究状态随之更新；"不确定"是合法结局，不得强行收敛。
4. 验证：Science-Gym 交互式任务（主动选择实验、发现科学规律）。

## P2-B：代码修改与自主实验（ResearchGym）

- 在 P2-A 基础上允许 Agent 提出代码修改（patch → 检查 → 人工批准 → worktree 内执行）；
- 客观衡量：相对官方基线的性能变化、修改的可复现性、失败实验的证据留存；
- ResearchGym 要求"超越已有基线"——此处必须报告全部失败尝试，不得只报成功。

## P3：AstaBench E2E

- 接入 [AstaBench](https://github.com/allenai/asta-bench)（Inspect AI 生态）统一任务与评分；
- **样本重叠警告**：AstaBench 内含 DiscoveryBench 子任务，与独立 DiscoveryBench
  同源样本不得当作两份独立证据；汇总报告必须标注任务来源与重叠关系。

## 每阶段复现台账（强制）

每次评测/运行保存：模型版本与配置、任务输入（含数据集哈希）、工具调用轨迹、
原始输出、评测代码版本（eval_code_version）、成本台账。缺任何一项视为不可复现，
不得写入结论性文档。

## 已知边界（如实声明）

- P1 的实验规划分数是 **Experiment Readiness Score（实验准备度）**：衡量方案形式
  完备性/可执行性/可复算性，不衡量科学信息价值。判断"不同假设对实验结果的预测
  是否真的不同"需要未来独立的 **Discrimination Score**（对每个竞争假设分别预测
  实验结果并度量预测差异）；两者都不是信息论信息增益（需概率模型，属后续研究）。
- P1 无实验执行：approved 只是人工标记，下一阶段才接入真实执行。
- 官方 DiscoveryBench 评分采用单子假设协议（无子假设切分）；与官方脚本数值
  不保证完全一致，需要严格对齐时用官方脚本复核同一批答案。
- 评测工具沙箱已使用 bwrap 命名空间、只读数据快照和任务级持久工作区；实际隔离记录
  随执行归档。P2 的任意实验命令执行工作区仍未实现。命名空间不可用时默认拒绝执行。
- P2 的实验优先级不变：先完成真实 LLM 的 A/B/C 正式对照并归档成绩，再进入
  实验执行开发。
