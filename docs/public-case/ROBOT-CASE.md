# 公开真实闭环案例报告：2D RRT 贪婪采样 vs 保守采样（机器人规划基准案例）

> 本报告由 `scripts/finalize_public_case.py` 从案例产物自动渲染（T16）：
> 全部计数与状态来自 04-experiment-attempts / 04-experiment-decision /
> 04-evidence-integrity / 03-experiment-contract-history，不手写。

- 案例目录：`runs/robot-rrt2d-case`
- 生成时间：2026-09-13T17:31:31.520444+00:00
- 案例定位：benchmark-only（LLM/论文/独立评审/gate 步骤 not_verified，见 `docs/public-case/PAPER-GRADE-GAP.md`）

## 1. 冻结契约与预注册

- 契约 digest：`6d4627f451cf55de…`（revision 1，历史版本 1 条）
- 预注册：status=locked，timing=before_results，revision=1
- 主指标：success_rate, mean_iterations
- 判据：支持=至少一个 primary metric 的均值差 95% CI 不跨 0 且方向为 candidate_better，且结果验证无阻断。

## 2. 真实执行与中断恢复（实际事件计数）

- 执行尝试总数：**9**（passed=9，interrupted=0，其余=0）
- 中断证据（两种形态，均为真实事件）：0 条尝试带 interrupted 标记（无）；若单任务尝试编号超过契约 repeats（如 candidate a1–a6 vs repeats=3），说明存在多次执行——第一次执行进程在中途死亡（未产出 04-results.json），恢复入口核对存活后重跑并顺延编号。
- 全部尝试的进程身份/起止时间/退出码见 `04-experiment-attempts.json`；日志在 `experiments/logs/`。

## 3. 结果与决策（产物原文）

- evidence：llm=unknown，experiment=verified
- decision=pivot_or_refine；四态：execution=completed，evidence=verified，outcome=not_supported，next=proceed；stop_after_report=True

| 指标 | Candidate | Baseline | Δ | 95% CI | 方向 |
| --- | ---: | ---: | ---: | --- | --- |
| mean_iterations | 107.650000 | 267.550000 | -159.900000 | [-169.043633, -150.756367] | baseline_better_or_equal |
| mean_path_length_solved | 15.775867 | 16.310833 | -0.534967 | [-0.628848, -0.441085] | baseline_better_or_equal |
| success_rate | 1.000000 | 1.000000 | 0.000000 | [0.000000, 0.000000] | baseline_better_or_equal |

- 统计结论：无附加警告

## 4. 受控故障注入

- 本目录未包含故障注入副本。

## 5. 复核与限制

- 依赖在线模型的步骤 not_verified（无凭据）；`publishable` 仅表示通过系统发布前检查。
- 第三方复核：`bash scripts/replay_public_case.sh`；重放生成独立目录与 `replay-summary.json`。
- 人工批准签署栏（actor/时间/理由/版本）待研究者签署，不得由自动化填写。
