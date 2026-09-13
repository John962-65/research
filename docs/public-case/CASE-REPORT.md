# 公开真实闭环案例报告：UCI Iris 最近质心候选 vs knn3 基线

> 存档说明：本报告的权威版本随证据包生成于 `runs/public-iris-case/`（runs 为 gitignore 的本地产物，可用 `bash scripts/replay_public_case.sh` 确定性再生）；此副本入库供查阅，两者内容一致。

案例目录：`runs/public-iris-case`（本目录即公开证据包；`fault-injection/` 为受控故障注入副本，不是自然错误）。
生成日期：2026-09-13。重放：`bash scripts/replay_public_case.sh`（离线、CPU、无需任何凭据；干净检出即可运行——与入库的 `docs/public-case/EXPECTED-RESULTS.json` 比对，并断言中断生效与具体阻断原因）。

## 1. 研究问题与冻结契约

- 研究问题：在 UCI Iris 冻结测试划分上，最近质心候选分类器相对 knn3 基线的表现如何？
- 契约：`03-idea-experiment-contract.json`（digest `c8f926942e8c4c65…`，revision 1，八字段组：假设/方法/数据/评估/判据/验证/执行）。
- 判据（冻结）：至少一个 primary metric 均值差 95% CI 不跨 0 且方向 candidate_better → supported；明确偏负 → not_supported；CI 跨 0/零宽 → 不得宣称优势。
- 预注册：`03-preregistration.json`（status=locked，timing=before_results，revision 1，primary metrics=accuracy, macro_f1）。预注册在结果产生前由 pack 流程写入（pack runner 先写预注册再执行）。
- 数据：UCI Iris（DOI 10.24432/C56C76，CC BY 4.0），冻结 split `split/iris-stratified-test-v1.json`（sha256 `89b38bc0…`，见 manifest），grader `grade_iris.py`（sha256 `2c4da3e5…`）。
- 人工批准：本案例的比较方案、数据来源与执行方式由任务书 T10 冻结（本任务书即授权记录）。签名栏：

| 步骤 | 批准人 | 日期 | 备注 |
|---|---|---|---|
| 契约冻结（digest c8f926942e8c4c65） | ____________ | ____ | 研究者核对契约与判据后签署 |
| 执行与恢复 | （本案例由重放脚本以无人值守方式执行） | 2026-09-13 | 中断与恢复均为真实系统行为 |

## 2. 执行与环境（真实运行）

- 全部命令为真实本地 CPU 进程执行；simulated 模式未使用；无任何模型调用（依赖在线模型的步骤见 §6）。
- 命令：`research-agent benchmark-pack-run --topic … --benchmark-manifest …candidate/baseline/ablation… --execution-repeats 3 --out runs/public-iris-case [--resume]`
- 环境：Python 3.12.13（仓库 `.venv`）、Linux x64；环境快照见 `04-environment-snapshot.json`（含源码树 sha256）。
- 每次尝试的进程身份、起止时间、退出码、stdout/stderr 日志路径记录于 `04-experiment-attempts.json`；日志文件在 `experiments/logs/`。

## 3. 真实中断恢复记录

第一次执行在中途被真实终止（进程死亡式中断，进度：candidate×3 与 baseline×3 已完成、ablation 未开始，`04-results.json` 尚未生成；重放脚本以轮询尝试账本+强制终止的崩溃式中断注入，与 A13"即刻崩溃或任务重启"同型）。
随后使用 `benchmark-pack-run --resume` 原地恢复：

- 复用：03 契约/适配器/预注册工件（内容与摘要未变化，预注册保持 revision 1，未产生新分析身份）。
- 重跑：全部 9 次命令执行（`04-experiment-attempts.json` 中 candidate/baseline 的新尝试编号顺延为 a4–a6，中断前的 a1–a3 记录原样保留；ablation 为 a1–a3）。
- 活任务守卫：恢复入口核对 `/proc/<pid>/cmdline`，已消亡进程不会被误判为活任务；同名活任务存在时会拒绝重复启动（单元级验证见 `tests/test_experiment_attempts.py`）。
- 诚实说明：pack 级恢复不跨尝试复用部分执行结果（每次命令执行是原子单元），恢复的成本是重跑而非断点续跑；这一点如实记录，不夸大。

## 4. 结果（如实报告：中性/负结果）

9/9 次执行 passed。candidate 与 baseline 在冻结划分上表现完全相同：

| 指标 | Candidate（最近质心） | Baseline（knn3） | Δ | 95% CI | 方向 |
| --- | ---: | ---: | ---: | --- | --- |
| accuracy | 0.966667 | 0.966667 | 0.0 | [0.0, 0.0] | baseline_better_or_equal |
| macro_f1 | 0.966583 | 0.966583 | 0.0 | [0.0, 0.0] | baseline_better_or_equal |
| error_rate | 0.033333 | 0.033333 | 0.0 | [0.0, 0.0] | baseline_better_or_equal |

- 系统判定：`statistical_outcome=neutral_no_observed_difference`；`claim_boundary_severity=negative_or_neutral_no_superiority`；`publishable_negative_or_neutral_result=True`。
- 决策四类状态（decision-contract §1）：execution_status=completed；evidence_status=verified（实验维度，来源绑定与指标校验通过）；research_outcome=not_assessed→按契约映射中性结果不得写成 supported（`04-experiment-decision`/`04-hypothesis-outcome` 未由 pack 流程生成，重放脚本给出按 04-statistics 的忠实摘要；见 §6 未验证项）。
- 结论边界（`04-result-validation.json` warnings）："所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽；当前 repeat 未观察到差异，不能据此声明优势或稳定性。"
- 允许的表述：在该冻结划分与两类确定性方法上未观察到差异；不允许的表述：候选方法更优/更简单因此更稳等外推。

## 5. 受控故障注入（独立副本，标记为故障注入）

`fault-injection/FAULT-INJECTION.json`：把冻结测试划分删去 3 个样本（30→27）后运行同一流水线。

- 观察到：适配器允许执行（执行通过≠证据通过），但 `04-benchmark-result-schema-audit` 判 **block**——"split_sha256 与 split_path 实际 SHA256 不一致"（三个角色全部命中）；pack 最终状态 **block**，CLI 退出码 2。
- 指标漂移被审计发现：accuracy 0.966667→0.962963（test_cases 30→27）。
- 结论：被篡改副本的结果被系统拒绝，不能进入任何结论。副本目录 `runs/fault-injection-benchmarks/` 保留原始篡改现场。

## 6. 未验证项与依赖在线模型的步骤

- 本案例未调用任何 LLM：无模型生成的论文文本、无独立模型评审。相应步骤在本案例中状态为 **not_verified**（依赖真实模型端点与凭据，见 README 的凭据要求）。如需补齐模型评审证据，用 `examples/uci-iris-paper-grade-config.toml` 配置真实端点后按 gold 流程重跑。
- `04-evidence-integrity.json` 显示 LLM 证据=unknown、实验证据=verified——与本案例"真实执行、无模型"的事实一致。

## 7. 第三方复核指引

1. 干净环境重放：`bash scripts/replay_public_case.sh`（生成 `runs/public-iris-case-replay`，与 `runs/public-iris-case` 逐字节可比的关键数值：accuracy/macro_f1/error_rate 与尝试计数）。
2. 核对关键证据：`03-preregistration.json`（锁定时间在执行前）、`04-experiment-attempts.json`（15 条尝试含中断）、`experiments/logs/`（每次执行的原始输出）、`04-experiment-runbook.json`（命令/种子/退出码）。
3. 复算主要数值：`python3 benchmarks/uci-iris-classification/grade_iris.py --method nearest_centroid --data data/iris.data --split split/iris-stratified-test-v1.json --metrics /tmp/check.json` → accuracy 应为 0.966667。
4. 检查故障注入：`runs/public-iris-case/fault-injection/FAULT-INJECTION.json` 与其引用的审计工件。
