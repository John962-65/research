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

## 三组对照（统一条件）

| 组 | 配置 | 目的 |
|---|---|---|
| A | 普通 LLM + 相同数据分析工具（python 沙箱），ReAct 循环 | 基础模型能做到什么 |
| B | Copilot 框架，关闭诊断与证据约束（只给列/统计画像） | 框架本身是否产生收益 |
| C | 完整 Copilot（确定性画像 + 诊断观测 + 证据校验） | 诊断与证据层是否有效 |

统一约束：同一被测模型、同一推理预算（max_steps / max LLM calls）、同一工具集、
同一任务输入、同一时限、同一作答 schema（hypothesis/variables/relationships/
mechanism/numeric_assertions，对齐 HMS 结构化抽取字段）。

## 指标

1. **HMS（Hypothesis Matching Score）**：官方两步协议（结构化摘要 → 0/1/2 匹配分），
   优先使用官方评分实现；本仓库内置协议实现（`metrics.hms_score`）作备选。
   **judge 模型与被测模型无关，单独记录**；judge 不可用时 HMS=None，绝不伪造。
2. **无依据结论比例**：数值断言确定性重算失败数 + 无因果依据的机制表述数，
   除以总检查数。全程序判定，不用 LLM 判断数值。
3. **任务完成率**：产出符合 schema 的非空答案比例。
4. **单任务成本**：LLM 调用次数、工具调用次数、token 用量、时延。

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
