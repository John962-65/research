<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 04：重复实验与统计审计

## Phase 5: Repeated Experiments and Statistics Audit

第五阶段把实验结果从单点指标升级为重复实验和统计审计：

- `04-results.csv`：保存每次重复的原始指标、`repeat_index` 和确定性 `seed`。
- `04-results.json`：结构化保存所有重复结果。
- `04-experiment-runbook.md/json`：记录执行环境、命令白名单校验、每次 repeat 的 seed/status、超时结果、预期产物、实际产物和 SHA256。
- `04-environment-snapshot.md/json`：记录 Python、平台、工具路径、包版本和源码聚合 SHA256；`partial` 或包含 warnings 时会进入 Web artifact、repair queue、scorecard 和投稿包。
- `04-statistics.md`：candidate 与 baseline 的均值、差值、近似 95% CI、标准化效应量、多重比较策略、功效/敏感性摘要和解释。
- `04-statistics.json`：结构化统计报告，包含 `multiplicity` 和 `power_analysis` 字段；小样本 run 会明确标注近似 MDE 和保守解释边界。
- `04-statistics-figure.svg/json`：把每个指标的 candidate-baseline 差值和 95% CI 可视化，便于人工快速识别不确定或反向指标。
- `04-result-validation.md/json`：验证实验结果是否覆盖所有命令、ablation 命令和 repeats，是否存在 failed/blocked/timeout，计划指标是否完整，candidate/baseline 是否有共同可比较指标，以及实验计划是否匹配 `03-preregistration` 的 plan fingerprint。
- `04-failure-analysis.md/json`：把失败、超时、负向指标、CI 跨 0 的不确定指标和模拟证据边界转成必须处理动作，并给论文写作阶段提供 claim boundaries。
- `04-benchmark-result-schema-audit.md/json`：把 `04-results`、`04-statistics`、`04-experiment-runbook`、benchmark adapter `metrics_path` 和 `expected_artifacts` 串成执行后 schema contract；candidate/baseline/ablation 不可比较、repeat metrics 不一致或 benchmark 产物断链会进入 repair queue。
- `04-benchmark-evidence-audit.md/json`：区分 `real_benchmark`、`local_experiment`、`smoke_only` 和 `blocked` 证据等级，检查 benchmark adapter、runbook、artifact trace、统计比较和执行模式是否足以支撑正式结论。
- `04-experiment-decision.md/json`：读取结果验证、失败分析、benchmark 证据审计、统计比较、执行模式和 benchmark 待办，做出 `proceed_to_paper`、`refine_experiment`、`pivot_or_refine`、`benchmark_upgrade` 或 `repair_before_writing` 决策，并把对应结论边界传入论文写作。
- `04-hypothesis-outcome.md/json`：把选中 idea 的 hypothesis、baseline、计划指标、统计比较、失败分析和实验后决策合并为 `supported`、`partially_supported`、`refuted_or_negative`、`inconclusive`、`smoke_only`、`untested` 或 `blocked_unverified`，并把假设层面的结论边界传入论文写作和下一轮计划。
- `04-claim-boundary-preflight.md/json`：在 `06-paper` 写作前汇总结果验证、失败分析、benchmark 证据、实验后决策和假设结果，生成 allowed/prohibited claim、必须写入的结果边界和写作模式；`block` 或 `review_required` 会进入 repair queue、scorecard、stage contract 和投稿包。
- `09-revision-response-audit.md/json`：在修订稿后、最终审计前验证每条审稿修订任务是否有结构化 result 和正文回应痕迹；`block` 或 `review_required` 会进入投稿检查、repair queue、scorecard、stage contract、下一轮计划和投稿包。
- `05-analysis.md`：优先基于统计审计写结论，而不是只比较单次结果。

Web UI 的“重复次数”控制每条实验命令的重复运行次数；CLI 可使用：

```bash
PYTHONPATH=src python3 -m research_agent run \
  --topic "your topic" \
  --llm-model "$OPENAI_MODEL" \
  --execution-repeats 5 \
  --out runs/statistics-demo
```

当前统计审计使用轻量近似方法，适合原型和 smoke test；正式科研仍应替换为领域 benchmark、更多随机种子、合适的统计检验和可视化。

### Benchmark Manifest 模式

除了 `simulated` 和 `local`，执行器还支持 `benchmark` 模式。该模式读取人工提供的 benchmark manifest，把脚本复制到 `experiments/benchmark-adapters/<name>/`，然后按本地白名单、相对路径和超时策略执行。运行时会生成：

- `03-benchmark-readiness.md/json`：执行批准前 dry-run 审计 manifest、adapter 命令、metric/baseline 对齐和 expected artifacts。
- `03-idea-experiment-contract.md/json`：readiness 之后、执行批准之前确认选中 idea 的证据链、baseline、metric 和命令已经落到实验计划。
- `03-benchmark-adapters.md/json`：manifest 解析、复制文件、改写命令、安全校验和人工待办。
- `04-experiment-runbook.md/json`：真实 adapter 的执行命令、seed、状态、metrics 和 artifact hash。
- `04-benchmark-result-schema-audit.md/json`：执行后确认 adapter `metrics_path`、预期产物、实际产物 hash、统计比较、candidate/baseline/ablation schema，以及 benchmark/data 来源、license、baseline version 和 citation provenance 仍然一致。

最小 manifest：

```json
{
  "name": "toy benchmark",
  "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
  "metrics_path": "metrics.json",
  "expected_artifacts": ["metrics.json"],
  "source_files": ["run_benchmark.py"],
  "role": "candidate",
  "benchmark_kind": "external",
  "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
  "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
  "dataset_version": "ompl-1.6.0",
  "split_name": "official-ompl-benchmark-suite",
  "split_path": "split-manifest.json",
  "split_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "license": "BSD-3-Clause",
  "baseline": "RRT*",
  "baseline_version": "ompl-1.6.0",
  "citation": "10.1109/MRA.2012.2205651",
  "expected_metrics": ["success_rate", "planning_time"],
  "metric_schema": {
    "success_rate": {
      "direction": "higher_is_better",
      "unit": "ratio",
      "description": "Fraction of benchmark tasks solved within the configured budget."
    },
    "planning_time": {
      "direction": "lower_is_better",
      "unit": "seconds",
      "description": "Planner wall-clock time measured by the frozen benchmark grader."
    }
  },
  "grader": "official-evaluator-or-wrapper.py",
  "grader_path": "official-evaluator-or-wrapper.py",
  "grader_version": "ompl-1.6.0-wrapper-v1",
  "grader_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
  "seed_policy": "RESEARCH_AGENT_SEED fixes task sampling and repeat index.",
  "min_repeats": 3,
  "notes": ["确认数据许可、baseline 版本、split_sha256 和 grader_sha256 都来自冻结文件。"]
}
```

`split_path` 和 `grader_path` 是可选但推荐的本地核验文件：填写后，adapter audit 会实际读取文件并比对 `split_sha256` / `grader_sha256`。正式 run 前可用 `sha256sum split-manifest.json official-evaluator-or-wrapper.py` 生成这两个值；hash 不一致会进入 paper-grade/readiness/result-schema/probe 阻断项。

CLI 示例：

```bash
PYTHONPATH=src python3 -m research_agent run \
  --topic "机械臂路径规划" \
  --execution-mode benchmark \
  --benchmark-manifest path/to/manifest.json \
  --llm-model "$OPENAI_MODEL"
```

仓库内提供了一个 smoke 示例：`examples/benchmark-adapter/manifest.json`，对应 schema 在 `examples/benchmark-adapter/manifest.schema.json`；另有一组三角色 fixture：`examples/rrt-2d-benchmark/manifest-candidate.json`、`manifest-baseline.json`、`manifest-ablation.json`。这些示例显式标记为 `benchmark_kind: fixture`，adapter audit 可以通过并执行，但 formal paper-grade 会返回 `review_required`。Web UI 可点击“生成 Manifest 模板”查看一个按当前课题生成的可编辑 JSON 起点；该模板接口只读，不会写文件、创建 run 或执行命令。生成后可以在“Manifest 草稿 JSON”中编辑，点击“校验草稿”检查 JSON、必填字段、命令白名单、相对路径和 `metrics_path`/`expected_artifacts` 一致性；点击“保存草稿”只允许写入仓库内 `benchmarks/**/manifest.json`，保存成功后会把路径写入 Benchmark Manifest 输入框。也可以点击“填入示例 Manifest”把 smoke 示例路径写入表单，并自动运行只读 preview；该操作不会创建 run、复制 adapter 或执行命令。正式 benchmark run 的 readiness 会强制审计公开 http(s) `dataset_url`/`benchmark_url`、`dataset_version`、`split_name`、`split_sha256`、`license`、`baseline_version`、`citation`、`metric_schema`、`grader_version` 和 `grader_sha256`，如果提供 `split_path`/`grader_path` 还会比对实际文件 hash；缺失、仍是 fixture/procedural/local/placeholder、hash 不匹配，或 `expected_metrics` 没有逐项指标定义时，会阻止进入正式 benchmark 证据链；`--paper-grade` 预检也会拒绝 candidate/baseline/ablation manifest 中缺失这些 provenance/metric/grader 字段或仍带 TODO/placeholder 的配置。

如果执行后的 `04-benchmark-result-schema-audit` 发现 metrics schema、artifact trace、provenance 或 metric/grader contract 断链，该问题会进入 `12-repair-queue`，并沉淀到 `runs-memory` / `00-prior-run-lessons`。下一轮 preflight 会提示切换 benchmark 模式、填写 manifest，并先用“校验 Benchmark”确认 `metrics_path`、`expected_artifacts`、来源 URL、license、baseline version、citation、metric schema 和 grader fingerprint。

这不是自动下载任意外部代码的执行器；manifest 仍需人工准备，并受 `allowed_commands` 白名单约束。
