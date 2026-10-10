# 评测协议（P1-A：DiscoveryBench A/B/C 对照）

## 目标

在公开科研任务上客观回答：Research Copilot 的诊断/证据模块是否改善了科研分析表现？
**不预设提升幅度**；若未观察到收益，保留失败结论并给出归因分析。

## 任务集

- 来源：[allenai/discoverybench](https://github.com/allenai/discoverybench)（官方仓库，
  `benchmarks/discoverybench/fetch.sh` 浅克隆；数据本体不入库）。
- **官方数据现实**（2024 版布局，适配器 `discoverybench_adapter.py` 已按此校准）：
  - 任务 = `discoverybench/{real,synth}/{train,dev,test}/<task>/metadata_N.json`，每文件一条查询；
  - **train 金标**在 metadata 内（real/train 共 14 个可用）；**test 金标**只在
    `eval/answer_key_{real,synth}.csv`（real/test 144 + synth/test 200，文件级命中 100%）；
    dev 划分无金标；
  - 因此开发期任务选择 = **train 优先、test 按序补足**（`select_dev_tasks`），
    并在 config.json 记录 composition 与**污染注记**：凡使用过 test 任务的评测，
    不得把该批任务再当留出集报告结论；正式结论性报告应注明或更换任务。
- 规模：先取 **20–30 个任务**作开发期评测（如 real/train 14 + real/test 前 6–16）。
- **AstaBench 中的 DiscoveryBench 子任务与本评测同源，不得重复计入。**

## 三组对照（统一条件，v2 公平性协议）

| 组 | 上下文注入 | 诊断观测 | 证据自检闭环 |
|---|---|---|---|
| A | 数据概要（表名/列/前几行） | 无 | 无 |
| B | 确定性统计画像 | 无 | 无 |
| C | 统计画像 + 诊断观测 | 有 | 有（数值断言程序复核失败→预算内重答） |

**公平性约定（修复 2026-10 审查 P0-1）**：三组共用**同一个** ReAct 循环、同一个
python 工具沙箱（相同限额/隔离级别）、同一 `GroupBudget`（max_steps /
max_tool_calls / 时限）、同一模型与作答 schema。组间唯一差异 = 注入的上下文，
即 Copilot 模块本身的输出。任何成绩差异都可归因于 Copilot 模块。

## 工具沙箱（P0 安全项）

- **环境变量白名单**：子进程只获得 PATH/LANG 等最小 env——API Key 等凭据不可能被
  生成代码读取（有测试断言）；
- **资源限额**：RLIMIT_CPU / AS(2GB) / FSIZE / NPROC / NOFILE；
- **网络隔离**：系统支持非特权 `unshare -Urn` 时启用 user+net namespace；不支持时
  执行记录如实标注 `network_isolated=false`（残余风险：生成代码可访问网络与用户
  文件，正式评测不可信代码应使用容器级隔离——见 roadmap P2 工作区安全路径）；
- 隔离级别写入每次运行的 config.json，评测报告必须展示。

## 评分（P0-2：官方协议对齐）

- **主指标 = 官方单子假设协议**（`evaluation/official_scoring.py`）：
  `accuracy = context(0/1) × var_F1 × rel(1.0/0.5/0.0)`；
  三个维度的 judge prompt、温度（0）与解析规则**逐字镜像**官方
  `eval/new_eval.py`（溯源 sha256 记录于 config.json 与每条评分记录）；
  自定义 0/1/2 评分降级为辅助指标 `hms_custom`。
- 已知偏差（如实声明）：官方完整流程含 LLM 子假设切分（recall_context × mean），
  本实现按单子假设计——与多数外部论文的单假设报告口径一致，但与官方脚本数值
  不保证完全一致；需要严格对齐时用官方脚本复核同一批答案。
- judge 模型与被测模型无关，单独计量（每任务 judge_calls）。

## 指标

1. **官方协议 accuracy**（主）：跨任务均值 ± 95% CI；分项 context 匹配率 / var_F1 / rel。
2. **无依据结论比例**：只对 **evaluable** 任务取均值；无有效答案或无数据的任务记
   `not_evaluable` 并单独报告 `n_not_evaluable`——失败任务不当作零风险。
3. **任务完成率**：与无依据比例分开报告。
4. **单任务成本**：每任务记录 usage **差值**（调用前后 snapshot 相减），不累计
   重复计算；含 LLM 调用、工具调用、token、时延、judge 调用。

## 多表数据

任务数据集按表加载（`load_task_tables`），保留每张表的独立 schema 与行集；
概要/画像/诊断观测均按表分别计算，禁止跨 schema 盲目合并
（`load_task_rows` 的合并行为仅供兼容，评测路径不使用）。

## 统计不确定性

- 任务级 HMS 均值 ± 95% CI（正态近似，任务数 ≥2 才给 CI）；
- 组间比较：按任务配对的 delta ± 95% CI（CI 优先，不给 p 值）；
- 结论只描述本任务子集，不外推。

## 产物（eval-runs/<stamp>-<groups>/，gitignore）

```
config.json            # 模型/judge/任务清单/选择规则/评测代码版本（复现台账）
<group>/<task>/answer.json + trace.json + cost.json
raw/<group>.jsonl      # 原始记录（含每任务的 unsupported 明细与 HMS 理由）
summary.json/.md       # 组级汇总 + 配对差
```

## 验收标准

> 完成 DiscoveryBench 的正式评测适配，能够在相同模型、工具和预算下，对普通 LLM 与
> Research Copilot 进行可复现对照；提供原始输出、官方评分、成本记录、错误分类和
> 统计不确定性。若未观察到明显收益，保留失败结论并分析原因。

**系统必须允许自己的研究假设被证伪**：若 C 组不如 A 组，这也是有价值的实验结果。

## 运行

```bash
benchmarks/discoverybench/fetch.sh
export RESEARCH_COPILOT_LLM_BASE_URL=... RESEARCH_COPILOT_LLM_MODEL=... RESEARCH_COPILOT_LLM_API_KEY=...
research-copilot evaluate --bench-root benchmarks/discoverybench/discoverybench \
  --subset main --limit 20 --out-dir eval-runs

# 管道冒烟（stub LLM，不构成评测结论）：
research-copilot evaluate --bench-root <fixture> --limit 1 --dry-run
```

## 防刷分原则

DiscoveryBench 分数是第一层能力的检查器，不是优化目标。禁止针对任务集反复调
prompt 刷 HMS；任何 prompt/模块变更都要重新走完整三组对照并记录版本。
