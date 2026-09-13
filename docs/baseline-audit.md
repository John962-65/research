# 基线审计（T00）

> 历史快照说明（T20）：本文记录的是 **2026-09-13 T00 时点的历史快照**——
> 当时的本地目录为无 `.git` 的导出副本、与远端 `e64af3c` 零差异、测试基线
> 3 failed/1372 passed。这些是当时的事实，不随当前仓库演化更新；当前
> 数字以 [`docs/test-evidence.json`](test-evidence.json) 为准。

审计日期：2026-09-13（历史快照时点）。任务书：`research_modification_taskbook_v1.md`，
基线 `e64af3c11ce7c1cdf7124bd1999d8cccc4cfcdd6`。

## 1. 版本核对结论

- 本地目录无 `.git`；目录名中的 `36f6340` 是导出工具生成的快照哈希，
  远端仓库历史中不存在该提交。
- 已克隆 `https://github.com/John962-65/research` 核对：`e64af3c` 即
  远端当前最新提交（2026-09-12，"fix: enhance runtime robustness,
  execution safety, and paper writing error handling"）。
- 本地工作副本 `src/`、`tests/`、`web/`、`docs/`、`scripts/`、`README.md`
  与 `e64af3c` 逐文件对比**零差异**（仅 `__pycache__`、`egg-info` 等构建产物不同）。
- 结论：没有"已修复但未同步"或"无法复现"的问题需要登记；任务书描述的
  缺陷在本地副本中全部原样存在。
- 特别确认：`e64af3c` 正是引入 writing/paper_review/paper_rewrite 三处
  `try-except → 模板兜底` 的提交（提交说明："Safeguard paper generation,
  review, and rewrite with try-except fallback"），与任务书 T04 所述
  "新增通用异常捕获后与既有测试约定冲突"一致。

## 2. 基线测试记录

命令：`bash scripts/run_tests.sh`（完整套件，**未排除** `tests/test_cli.py`；
gold 支撑运行已由 `scripts/prepare_gold_support_runs.sh` 生成）。

- 环境：Python 3.12.13（仓库 `.venv`），Linux x64。
- 结果：**3 failed, 1372 passed, 1 skipped, 103 subtests passed**，耗时 5:31。
- 3 个失败均为 `tests/test_ai_integration.py::
  AIIntegrationTest::test_llm_call_failures_are_not_replaced_by_rule_fallbacks`
  的子用例 `paper` / `paper_review` / `paper_rewrite`：断言模型失败必须抛出
  `TimeoutError`，实际被 `writing.py:126`、`paper_review.py:88`、
  `paper_rewrite.py:81` 的宽泛 `except Exception` 吞掉并回退模板。
  与任务书记录的"3 个失败子用例"一致（通过数差异源于任务书审查时点更早）。
- 该 3 个失败在 T04 修复；其余 1372 项为回归基线。

## 3. 任务书缺陷现状核对（本地逐条确认）

| 任务书问题 | 现状 | 证据 |
|---|---|---|
| T01：全失败调用被判真实模型调用 | 存在 | `evidence_integrity.py:56` `successful_calls or total_calls` |
| T01：failed 结果算作真实实验 | 存在 | `evidence_integrity.py:15,64` 黑名单不含 `failed` |
| T01：无指标有限性/来源校验 | 存在 | `evidence_integrity.py:61-66`；`result_validation.py` 仅查键存在 |
| T02：citation_grounding/复审仅绑状态 | 存在 | `pipeline.py:385-388` |
| T02：恢复按 revision 复用旧 deliberation | 存在 | `pipeline.py:367-368`（无 prompt/快照校验） |
| T02：覆盖缺原因码/范围/不可覆盖约束 | 存在 | `gate_aggregator.py:98-131`（机械校验已达标） |
| T02：最终就绪复用按状态不按哈希 | 存在 | `pipeline.py:2676,4894-4913` |
| T03：最小 `{verdict, confidence}` 可通过 | 存在 | `agent_verdict.py:243-260` |
| T03：verdict 不与调用账本交叉核验 | 存在 | `gate_aggregator.py` 全文无 ledger 读取 |
| T04：三处静默模板降级 | 存在 | `writing.py:126`、`paper_review.py:88`、`paper_rewrite.py:81` |
| T05：契约非权威结构、预注册就地覆盖 | 存在 | `idea_experiment_contract.py`、`preregistration.py:26-29` |
| T06：无任务标识/PID/起止时间持久化，恢复不查存活 | 存在 | `experiments.py:343-429`、`pipeline.py:2166-2254` |
| T07：revision_required 硬编码、无轮次/预算上限 | 存在 | `pipeline.py:3288-3290`；仅 `max_steps=128` |
| T08：主张判定纯词面重合、无 contradicted/位置定位 | 存在 | `literature_context.py:401-426`、`citation_grounding.py:130-254` |
| T09：无"已有代码和结果"入口 | 存在 | web/CLI 均无导入路由 |
| T09：执行/证据/结论状态未分离展示 | 存在 | 工作台仅有阶段轨道与状态胶囊 |

已达标项（保留回归，不回退）：run 租约线程重入与跨进程互斥
（`run_lease.py`）、人工覆盖机械校验（真布尔/整型 revision/HMAC 摘要，
`gate_aggregator.py:108-118`）、TRACE-01 按 call_id 绑定校验结果、
审批绑定 `approval_binding_sha256`、WorkflowEngine 阻断路由
（`awaiting_experiment_repair`）。

## 4. 环境与材料

- 测试与运行：`.venv`（Python 3.12.13），零第三方运行时依赖。
- gold 支撑运行已存在：`runs/uci-iris-expanded-baseline-pack-run`、
  `runs/uci-iris-fulltext-grounding`。
- `runs/` 下含 2026-09-09/10 两次真实用户运行与若干验证运行，本轮全部保留不动。
- 离线 CPU 基准：`benchmarks/uci-iris-classification`（冻结数据/split/grader），
  `examples/rrt-2d-benchmark`（第二套）。

## 5. 验收矩阵状态

见 `docs/acceptance-matrix.md`（A01–A22 初始全部 `planned`；
A21 维持 `not_measured` 口径）。
