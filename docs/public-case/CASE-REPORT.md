# 公开真实闭环案例报告：UCI Iris 最近质心候选 vs knn3 基线（公开案例重放）

> 本报告由 `scripts/finalize_public_case.py` 从案例产物自动渲染（T16）：
> 全部计数与状态来自 04-experiment-attempts / 04-experiment-decision /
> 04-evidence-integrity / 03-experiment-contract-history，不手写。

- 案例目录：`/home/johb/下载/research-fixed-36f6340/research-fixed/runs/public-iris-case-replay`
- 生成时间：2026-09-13T17:32:31.570031+00:00
- 案例定位：benchmark-only（LLM/论文/独立评审/gate 步骤 not_verified，见 `docs/public-case/PAPER-GRADE-GAP.md`）

## 1. 冻结契约与预注册

- 契约 digest：`4d0df11f22147930…`（revision 1，历史版本 1 条）
- 预注册：status=locked，timing=before_results，revision=1
- 主指标：accuracy, macro_f1
- 判据：支持=至少一个 primary metric 的均值差 95% CI 不跨 0 且方向为 candidate_better，且结果验证无阻断。

## 2. 真实执行与中断恢复（实际事件计数）

- 执行尝试总数：**10**（passed=9，interrupted=1，其余=0）
- 中断证据（两种形态，均为真实事件）：1 条尝试带 interrupted 标记（process_no_longer_alive_at_resume）；若单任务尝试编号超过契约 repeats（如 candidate a1–a6 vs repeats=3），说明存在多次执行——第一次执行进程在中途死亡（未产出 04-results.json），恢复入口核对存活后重跑并顺延编号。
- 全部尝试的进程身份/起止时间/退出码见 `04-experiment-attempts.json`；日志在 `experiments/logs/`。

## 3. 结果与决策（产物原文）

- evidence：llm=unknown，experiment=verified
- decision=pivot_or_refine；四态：execution=completed，evidence=verified，outcome=not_supported，next=proceed；stop_after_report=True

| 指标 | Candidate | Baseline | Δ | 95% CI | 方向 |
| --- | ---: | ---: | ---: | --- | --- |
| accuracy | 0.966667 | 0.966667 | 0.000000 | [0.000000, 0.000000] | baseline_better_or_equal |
| error_rate | 0.033333 | 0.033333 | 0.000000 | [0.000000, 0.000000] | baseline_better_or_equal |
| macro_f1 | 0.966583 | 0.966583 | 0.000000 | [0.000000, 0.000000] | baseline_better_or_equal |

- 统计结论：无附加警告

## 4. 受控故障注入

- 本目录未包含故障注入副本。

## 5. 复核与限制

- 依赖在线模型的步骤 not_verified（无凭据）；`publishable` 仅表示通过系统发布前检查。
- 第三方复核：`bash scripts/replay_public_case.sh`；重放生成独立目录与 `replay-summary.json`。
- 人工批准签署栏（actor/时间/理由/版本）待研究者签署，不得由自动化填写。
