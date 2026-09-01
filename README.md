# Research Agent

一个可审计的科研自动化流水线原型，覆盖：

1. 文献调研
2. 研究 idea 生成与排序
3. 实验计划
4. 实验执行
5. 结果分析
6. 论文草稿生成
7. 审稿式复核
8. 修订计划
9. 修订稿生成
10. 最终就绪审计
11. 投稿/归档包生成
12. 下一轮迭代计划

第一版的原则是“全流程自动、每步留痕、默认安全”。LLM 只支持 OpenAI-compatible 在线接口，未配置模型会直接失败；可选配置 LLM 调用预算，超额会在真实请求前拦截。文献默认可用离线种子库，实验默认使用模拟执行器。配置 `execution.mode = "local"` 且设置命令白名单后，才会执行本地实验命令。

## Quick Start

```bash
cd /path/to/research-agent
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
read -rsp "OPENAI_API_KEY: " OPENAI_API_KEY && export OPENAI_API_KEY && echo
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=...
PYTHONPATH=src .venv/bin/python -m research_agent run \
  --topic "自动科研 agent 如何减少机器学习实验迭代成本" \
  --llm-model "$OPENAI_MODEL" \
  --out runs/demo
```

流水线会在 `01-review-gate.md` 生成后等待人工确认。用另一个终端批准后才会继续进入 idea、实验和论文草稿阶段：

```bash
PYTHONPATH=src .venv/bin/python -m research_agent approve runs/demo
```

如果 `01-review-gate.md` 的状态不是 `pass`，批准时必须填写审核意见；CLI 使用 `--notes`，Web UI 使用“审核意见/修复说明”。意见应说明人工判断依据、已完成的文献/引用修复，或为什么接受剩余风险。系统会同时生成 `01-review-feedback.md/json` 和 `01-review-constraints.md/json`，后者会把人工意见解析为 baseline、literature、metric、reproducibility、scope 或 safety 等约束，并把结构化约束文本传给后续 idea 和实验计划阶段。

已完成但 `12-repair-queue.json` 仍为 `blocked_repair_required` 或 `needs_repair` 的 run，可以先预览修复恢复计划：

```bash
PYTHONPATH=src python3 -m research_agent repair-resume runs/<run-id> --dry-run
```

确认后再执行：

```bash
PYTHONPATH=src python3 -m research_agent repair-resume runs/<run-id> \
  --apply \
  --llm-model "$OPENAI_MODEL" \
  --max-papers 12 --max-search-queries 6 \
  --extra-search-query "robot manipulator OMPL benchmark RRT* CHOMP TrajOpt"
```

CLI 不加 `--apply` 时只会预览并写出 `12-repair-resume-plan.md/json`，不会清理旧产物或启动 pipeline。若计划要求 release 元数据，`--apply` 前必须先通过 `--release-*` 参数或 `10-release-metadata.json` 提供真实必填值。Web UI 会在这类 run 上显示“预览修复”和“修复恢复”。预览只生成 `12-repair-resume-plan.md/json`，不会清理旧产物或启动后台 worker；确认后再点“修复恢复”。实际恢复会按 repair queue 中最早的 `rerun_from` 清理受影响的旧产物，并把来源审计中的 blockers、manual tasks、required actions 和失败 checks 汇总为 `repair_context` 注入下一轮 planning prompt，再进入 checkpoint resume；如果清理到了文献 context，会重新等待人工 review approval；如果清理到了实验执行，会重新等待 local/benchmark execution approval。

历史 run 可以生成本地成果库，供下一轮研究前检索已经产出的论文、摘要、证据量和修复状态：

```bash
PYTHONPATH=src python3 -m research_agent library \
  --runs-dir runs \
  --query "robot manipulator OMPL benchmark"
```

该命令会写出 `runs/runs-library.md` 和 `runs/runs-library.json`。Web UI 的“成果库”搜索框调用同一个索引，用于快速找到可复用的历史论文、失败案例或仍需修复的 run。

运行后会生成：

- `run-manifest.json` / `run-manifest.md`
- `run-llm-ledger.json` / `run-llm-ledger.md`
- `00-question.md`
- `00-human-brief.json` / `00-human-brief.md`
- `00-prior-run-lessons.json` / `00-prior-run-lessons.md`
- `00-prior-run-library.json` / `00-prior-run-library.md`
- `00-open-source-lessons.json` / `00-open-source-lessons.md`
- `00-research-plan.json` / `00-research-plan.md`
- `01-literature.json` / `01-literature.md`
- `01-literature-rerank.json` / `01-literature-rerank.md`
- `01-literature-search-strategy.json` / `01-literature-search-strategy.md`
- `01-literature-source-health.json` / `01-literature-source-health.md`
- `01-query-execution-audit.json` / `01-query-execution-audit.md`
- `01-literature-snowball.json` / `01-literature-snowball.md`
- `01-literature-coverage.json` / `01-literature-coverage.md`
- `01-literature-evidence-mix.json` / `01-literature-evidence-mix.md`
- `01-literature-rescue-plan.json` / `01-literature-rescue-plan.md`
- `01-literature-rescue-execution.json` / `01-literature-rescue-execution.md`
- `01-literature-search-feedback.json` / `01-literature-search-feedback.md`
- `01-seed-paper-intake.json` / `01-seed-paper-intake.md`
- `01-literature-quality.json` / `01-literature-quality.md`
- `01-literature-curated.json` / `01-literature-curated.md`
- `01-literature-metadata-audit.json` / `01-literature-metadata-audit.md`
- `01-fulltext-corpus.json` / `01-fulltext-corpus.md`
- `01-context.json` / `01-context.md`
- `01-review-gate.md`
- `01-citation-audit.json` / `01-citation-audit.md`
- `approval.json`
- `01-review-feedback.json` / `01-review-feedback.md`
- `01-review-revision-plan.json` / `01-review-revision-plan.md`
- `01-review-constraints.json` / `01-review-constraints.md`
- `01-references.bib` / `01-references.ris`
- `02-research-gap-map.json` / `02-research-gap-map.md`
- `02-agent-team.json` / `02-agent-team.md`
- `02-ideas.json` / `02-ideas.md`
- `02-novelty-audit.json` / `02-novelty-audit.md`
- `02-idea-audit.json` / `02-idea-audit.md`
- `02-exploration-map.json` / `02-exploration-map.md` / `02-exploration-map.svg`
- `02-experiment-manager.json` / `02-experiment-manager.md`
- `03-experiment-plan.json` / `03-experiment-plan.md`
- `03-agent-handoff-audit.json` / `03-agent-handoff-audit.md`
- `03-review-constraint-compliance.json` / `03-review-constraint-compliance.md`
- `03-experiment-audit.json` / `03-experiment-audit.md`
- `03-idea-experiment-contract.json` / `03-idea-experiment-contract.md`
- `03-execution-safety-audit.json` / `03-execution-safety-audit.md`
- `03-execution-approval.json` / `03-execution-approval.md`（`execution.mode = "local"` 或 `"benchmark"` 时生成）
- `03-ablation-plan.json` / `03-ablation-plan.md`
- `03-preregistration.json` / `03-preregistration.md`
- `03-benchmark-plan.json` / `03-benchmark-plan.md`
- `03-benchmark-readiness.json` / `03-benchmark-readiness.md`
- `03-benchmark-adapters.json` / `03-benchmark-adapters.md`（`execution.mode = "benchmark"` 时生成）
- `04-results.json` / `04-results.csv`
- `04-statistics-figure.svg` / `04-statistics-figure.json`
- `04-statistics.json` / `04-statistics.md`
- `04-result-validation.json` / `04-result-validation.md`
- `04-failure-analysis.json` / `04-failure-analysis.md`
- `04-benchmark-result-schema-audit.json` / `04-benchmark-result-schema-audit.md`
- `04-benchmark-evidence-audit.json` / `04-benchmark-evidence-audit.md`
- `04-experiment-decision.json` / `04-experiment-decision.md`
- `04-hypothesis-outcome.json` / `04-hypothesis-outcome.md`
- `04-claim-boundary-preflight.json` / `04-claim-boundary-preflight.md`
- `05-analysis.md`
- `06-paper.md` / `06-paper.tex`
- `07-paper-review.md` / `07-paper-review.json`
- `07-paper-review-calibration.md` / `07-paper-review-calibration.json`
- `08-revision-plan.md` / `08-revision-plan.json`
- `09-revised-paper.md` / `09-revised-paper.tex`
- `09-revision-report.md` / `09-revision-report.json`
- `09-revision-response-audit.md` / `09-revision-response-audit.json`
- `10-revised-paper-review.md` / `10-revised-paper-review.json`
- `10-claim-traceability.md` / `10-claim-traceability.json`
- `10-citation-grounding.md` / `10-citation-grounding.json`
- `10-citation-coverage.md` / `10-citation-coverage.json`
- `10-results-presentation.md` / `10-results-presentation.json`
- `10-claim-consistency.md` / `10-claim-consistency.json`
- `10-release-metadata.md` / `10-release-metadata.json`
- `10-code-data-availability.md` / `10-code-data-availability.json`
- `10-submission-check.md` / `10-submission-check.json`
- `10-final-readiness.md` / `10-final-readiness.json`
- `11-submission-package.md` / `11-submission-package.json` / `11-submission-package.zip`
- `12-next-iteration-plan.md` / `12-next-iteration-plan.json`
- `12-repair-queue.md` / `12-repair-queue.json`
- `12-repair-resolution-audit.md` / `12-repair-resolution-audit.json`
- `12-repair-resume-plan.md` / `12-repair-resume-plan.json`（触发修复恢复时生成）
- `13-agent-stage-contract.md` / `13-agent-stage-contract.json`
- `13-agent-trajectory.md` / `13-agent-trajectory.json`
- `13-llm-trace-audit.md` / `13-llm-trace-audit.json`
- `13-run-economics-audit.md` / `13-run-economics-audit.json`
- `13-agent-observability-audit.md` / `13-agent-observability-audit.json`
- `13-open-source-compliance.md` / `13-open-source-compliance.json`
- `13-research-scorecard.md` / `13-research-scorecard.json`
- `14-run-integrity-audit.md` / `14-run-integrity-audit.json`
- `run-diagnostics.md` / `run-diagnostics.json`（失败时生成）
- `state.json`


跨 run 汇总会额外在 `runs/` 根目录生成：

- `runs-summary.json` / `runs-summary.md`
- `runs-memory.json` / `runs-memory.md`
- `runs-library.json` / `runs-library.md`

## Phase 0: Research Plan and Domain Profile

第零阶段在文献检索前先读取人工 brief、历史 run 复盘和外部开源科研 agent 项目经验，再生成领域研究计划：

- `00-human-brief.md` / `00-human-brief.json`：把用户在 Web/CLI/config 中提供的研究偏好、人工约束、成功标准、资源限制和已知风险固化为可审计输入，并在 `00-research-plan` 之前注入 planning context。
- `00-prior-run-lessons.md` / `00-prior-run-lessons.json`：从 `runs/` 历史记录中提取文献薄弱、LLM 配置失败、实验管理阻断、人工约束未落实、smoke-first 分支、模拟证据、benchmark 缺口、citation grounding、投稿/发布阻断等可继承经验，并转成当前 run 的 agent 约束文本。
- `00-prior-run-library.md` / `00-prior-run-library.json`：按当前课题检索 `runs-library` 中的相关历史论文、失败案例和待修复 run，给 `00-research-plan` 提供可复用 benchmark/baseline/失败经验提示；它只作为 planning context，不会被当成本轮 citation 或论文证据。
- `00-open-source-lessons.md` / `00-open-source-lessons.json`：把 AI-Scientist-v2、PaperQA2 等开源科研 agent 项目的关键做法固化成本平台约束，例如结构化 idea->experiment 闭环、生成代码 sandbox、chunk-level citation grounding、多源 metadata/rate-limit 诊断、历史记忆/cache 复用和 AI 使用披露；同时记录每个参考项目的仓库 URL、证据目标文件和 provenance 状态。默认 run 不联网抓取 GitHub，使用内置编目保证离线可运行；如果要把外部项目版本当作强证据，需要人工或后续工具刷新 branch/commit/关键文件核对记录。
- `00-research-plan.md`：领域画像、英文 scholarly search queries、benchmark/数据集/任务、baseline、指标、约束、风险和成功标准。
- `00-research-plan.json`：结构化研究计划，供后续检索和实验计划复用。

该阶段借鉴 PaperQA/OpenScholar/STORM 类项目对检索计划和引用 grounding 的重视，以及 AI Scientist/Agent Laboratory/AgentRxiv 类项目对人工 notes、迭代研究记忆、实验模板和 benchmark 的重视。系统会优先用 LLM 生成计划；如果 LLM 调用失败或超时，本次 run 会失败并写入诊断，而不会切到离线 LLM 兜底。只有在模型已成功返回但 JSON 结构不合格时，系统才会用规则画像补齐常见领域信息，例如机械臂路径规划、轴承故障诊断和科研 agent 的 benchmark、baseline 和指标。后续在线文献检索会优先使用研究计划中的英文检索式，实验计划也会吸收其中的 benchmark、baseline 和 metric。

`00-human-brief`、`00-prior-run-lessons`、`00-prior-run-library` 和 `00-open-source-lessons` 不会静默修改配置；它们会把人工约束、历史风险、历史成果库参考和外部项目约束写入 `constraints`、`risks`、`success_criteria`，并作为后续 idea 阶段的上下文。这样可以复用用户给定边界、上一轮人工 gate、失败实验、弱文献、citation grounding 和已生成论文的 benchmark/baseline 经验，同时保留可审计记录。

可以单独生成或刷新开源项目 provenance：

```bash
PYTHONPATH=src python3 -m research_agent open-source-lessons \
  --topic "机械臂路径规划" \
  --out runs/open-source-provenance-check

# 可选：联网核对 GitHub 默认分支、HEAD commit 和关键文件；失败会写成 unverified，不阻断正式 run
GITHUB_TOKEN=... PYTHONPATH=src python3 -m research_agent open-source-lessons \
  --topic "机械臂路径规划" \
  --out runs/open-source-provenance-check \
  --refresh-github
```

如果历史 run 的 `03-review-constraint-compliance` 因人工 brief 或 review 约束未落实而阻断，下一轮 preflight 会要求当前表单补 `human_constraints`、`human_resource_limits` 或相关 human brief 字段；补齐后会显示该历史风险已被当前配置承接。

## Phase 1: Online Literature Search

第一阶段已经接入真实文献检索源，默认仍使用离线种子库以保证无网络环境可运行。启用在线检索：

```bash
cd /path/to/research-agent
PYTHONPATH=src python3 -m research_agent run \
  --topic "自动科研 agent 如何减少机器学习实验迭代成本" \
  --literature-provider online \
  --literature-sources semantic_scholar,openalex,arxiv,crossref \
  --max-papers 10 \
  --max-search-queries 6 \
  --extra-search-query "agent laboratory autonomous science benchmark" \
  --out runs/online-literature-demo
```

如果目标是真正论文级 run，可先用 `--paper-grade` 做启动前硬门槛检查。该模式要求 online/auto 文献、多源检索、至少 3 条 DOI/URL seed、benchmark 执行模式、`repeats>=3`，并且 benchmark manifest 至少覆盖 candidate/baseline/ablation。三类 manifest 还必须指向公开外部 benchmark/data 来源：`dataset_url` 需要是非占位的 http(s) URL，不能是 `procedural://`、本地路径或仓库 fixture。它只检查配置和真实 manifest，不会自动伪造 DOI、URL 或 benchmark：

```bash
PYTHONPATH=src python3 -m research_agent preflight \
  --topic "机械臂路径规划" \
  --paper-grade \
  --literature-provider online \
  --literature-sources semantic_scholar,openalex,arxiv,crossref \
  --seed-paper "10.xxxx/review ..." \
  --seed-paper "10.xxxx/benchmark ..." \
  --seed-paper "https://doi.org/10.xxxx/baseline ..." \
  --execution-mode benchmark \
  --execution-repeats 3 \
  --benchmark-manifest benchmarks/candidate.json \
  --benchmark-manifest benchmarks/baseline.json \
  --benchmark-manifest benchmarks/ablation.json \
  --no-llm-ping
```

仓库内提供了一个可直接预检的结构性示例：

```bash
PYTHONPATH=src python3 -m research_agent preflight \
  --topic "机械臂路径规划" \
  --config examples/paper-grade-config.toml \
  --no-llm-ping
```

这个示例会启用 online 文献、多源配置、3 条 DOI/URL seed，以及 `examples/rrt-2d-benchmark/manifest-candidate.json`、`manifest-baseline.json`、`manifest-ablation.json` 三角色 benchmark manifest。它用于证明 agent 的论文级门槛链路可预检、可审计、可修复；其中 RRT 2D benchmark 是仓库内可复现 fixture，不是正式投稿的领域公开基准。因此这个示例的 `paper_grade_benchmark_manifests` 会失败，提示把 fixture 替换成公开外部 benchmark manifest。正式 paper run 应把 seed、manifest、release URL 和 LLM 配置替换成真实课题资产。
如果本机没有配置 Semantic Scholar key、contact email 或历史 `runs-memory` 里仍有继承风险，整体 preflight 也可能出现其他 `warn`；此时应先确认 online/seed 检查达标，再补齐外部 benchmark provenance。

如果要在正式 run 前验证在线源和 DOI seed 真的可用，可运行轻量探针：

```bash
PYTHONPATH=src python3 -m research_agent paper-grade-probe \
  --topic "机械臂路径规划" \
  --config examples/paper-grade-config.toml \
  --query "robot manipulator motion planning benchmark" \
  --out runs/paper-grade-probe
```

该命令会写入 `00-paper-grade-online-probe.md/json`，检查至少 2 个在线来源返回候选、至少 3 条 DOI/URL seed 能解析到 Crossref/在线/离线题录元数据，以及 probe 候选不为空。它不会生成论文、不会批准 review gate，也不会运行实验；失败时应先修复在线来源、contact email/API key、检索式或 seed DOI/URL。paper-grade probe、gold doctor、gold bundle 和 `run --paper-grade` 的正式链路都要求 secret 走环境变量；不要把 LLM 或文献源 API key 放进 CLI 参数。

外部 benchmark manifest 也有独立在线探针：

```bash
PYTHONPATH=src python3 -m research_agent paper-grade-benchmark-probe \
  --config path/to/formal-paper-grade-config.toml \
  --benchmark-manifest benchmarks/candidate/manifest.json \
  --benchmark-manifest benchmarks/baseline/manifest.json \
  --benchmark-manifest benchmarks/ablation/manifest.json \
  --execution-repeats 3 \
  --allowed-command python3 \
  --out runs/paper-grade-benchmark-probe
```

该命令会写入 `00-paper-grade-benchmark-probe.md/json`，先复用 benchmark adapter audit，确认 candidate/baseline/ablation、共享指标、`repeats/min_repeats>=3` 和 external provenance；再对 `dataset_url`、`benchmark_url` 以及 citation 中的 DOI/URL 做 bounded HTTP probe。仓库内 `examples/rrt-2d-benchmark` 这类 `benchmark_kind: fixture` 会在这里失败，这是预期行为。

如果要在不启动 LLM、不生成论文的情况下真实执行三角色 benchmark pack，可运行 standalone benchmark pack runner：

```bash
PYTHONPATH=src python3 -m research_agent benchmark-pack-run \
  --topic "formal benchmark pack execution" \
  --benchmark-manifest benchmarks/candidate/manifest.json \
  --benchmark-manifest benchmarks/baseline/manifest.json \
  --benchmark-manifest benchmarks/ablation/manifest.json \
  --execution-repeats 3 \
  --allowed-command python3 \
  --out runs/formal-benchmark-pack-run
```

该命令会写入标准实验产物：`04-results.json/csv`、`04-experiment-runbook.json`、`04-statistics.json`、`04-statistics-figure.svg`、`04-result-validation.json`、`04-benchmark-result-schema-audit.json`、`04-benchmark-evidence-audit.json` 和 `04-benchmark-pack-run.json`。`04-statistics.json` 会同时记录均值差、95% CI、effect size、多重比较策略和功效/敏感性摘要；`04-benchmark-evidence-audit.json` 会显式给出 `statistical_outcome`、`claim_boundary_severity`、`claim_policy` 和 `publishable_negative_or_neutral_result`。如果真实 benchmark 显示 candidate 不优于 baseline 或没有观察到差异，run 不会被伪装成正结果，而是要求按负/中性结果可发表地报告，并禁止 superiority/stability claim。它适合在正式 gold run 前验证真实 benchmark、统计比较和 artifact trace；但它不会做 online 文献综述、全文 citation grounding、人工 review gate、论文写作或最终 handoff，因此不能替代端到端 paper-grade gold run。

如果要单独验证本地全文 chunk 与正文 citation marker 的支撑关系，可运行 standalone fulltext grounding runner：

```bash
PYTHONPATH=src python3 -m research_agent fulltext-grounding-run \
  --topic "formal fulltext grounding validation" \
  --fulltext-path path/to/local-paper-or-dataset-description.txt \
  --claim "A concise claim that should be supported by the local fulltext." \
  --out runs/formal-fulltext-grounding
```

该命令会写入 `01-fulltext-corpus.*`、`01-context.*`、`09-revised-paper.md`、`10-citation-grounding.*` 和 `10-fulltext-grounding-run.*`。它适合验证全文 grounding 能力；但它不会做在线检索、完整论文写作、人工 gate 或 final handoff，也不能替代 gold run。

如果要从平台层面检查“完美科研 agent”还差哪些能力，可运行总控 readiness：

```bash
PYTHONPATH=src python3 -m research_agent perfect-readiness \
  --project-dir . \
  --runs-dir runs \
  --out .
```

该命令会写入 `perfect-agent-readiness.md/json`，按 12 个能力项审计：真实外部 benchmark pack、端到端 gold run、candidate/baseline/ablation 真实实现、可复现实验环境、全文 citation grounding、统计设计、claim traceability、领域模板库、Web 人工协作、成本/修复队列/并发、外部归档/引用管理集成、执行安全隔离。它只读当前项目和历史 runs，不联网、不执行实验；默认扫描全部历史 run，并在报告里写出扫描数量与 `limit`，如需快速抽样可显式传 `--limit N`。如果没有正式 `benchmarks/<domain>/` 外部三角色 manifest 或 gold run，会明确保持 `block`，不会把 `examples/` fixture 当作投稿级证据。若 UCI Iris 的正式 benchmark pack、standalone benchmark run 和 fulltext grounding run 已就绪但还没有完整 gold run，`gold_end_to_end_run` 证据会额外显示 `gold_launch_prereq`、`gold_launch_focus`、`gold_launch_gateway_socket` 和 `gold_launch_kit=scripts/start_gold_web_env.sh, scripts/run_gold_cli_env.sh`；该摘要只报告环境字段计数、socket 是否可达和下一步，不输出 API key 或环境变量值。

正式 gold run 启动前可以先运行只读 doctor，检查真实 LLM/contact 环境、paper-grade 配置和 standalone benchmark/fulltext 预验证产物是否齐全。该命令不会打印 API key，也不会启动实验：

```bash
PYTHONPATH=src python3 -m research_agent gold-run-doctor \
  --topic "Iris classification benchmark smoke" \
  --config examples/uci-iris-paper-grade-config.toml \
  --benchmark-pack-run-dir runs/uci-iris-expanded-baseline-pack-run \
  --fulltext-grounding-run-dir runs/uci-iris-fulltext-grounding \
  --out runs/uci-iris-gold-run-doctor
```

如果要实际验证本地 OpenAI-compatible 网关，把 `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY` 和真实 `RESEARCH_AGENT_CONTACT_EMAIL` 放在环境变量中，再给 doctor 加 `--ping-llm`。当前本地网关示例为 `OPENAI_BASE_URL=http://127.0.0.1:8317`、`OPENAI_MODEL=gpt-5.5`；API key 只放环境变量，不写入配置文件、命令参数或文档。ping 结果会进入 `preflight:overall`，失败时 doctor 保持 blocked；输出仍只显示 key 已配置，不会打印 key。paper-grade 模式下，即使是本地兼容网关，缺少 API key 也会在预检阶段直接 fail，避免正式 run 启动后才在 LLM 调用处失败。
`gold-run-doctor` 还会执行更严格的 `gold_release_metadata` 检查：正式 gold run 必须提供真实代码仓库 URL、代码归档 DOI/URL、许可证、版本、数据访问说明和环境归档 URL；`example`、`scaffold`、`placeholder` 这类占位值会被阻断。示例 `examples/uci-iris-paper-grade-config.toml` 仍是 scaffold，因此正式运行前需要复制为本地配置并补齐 `[release]`，或在 doctor/run 命令中传入对应 `--release-*` 参数。

doctor 输出还包含 `launch_manifest`，并单独写出 `00-gold-launch-manifest.md/json`：把 doctor/preflight 状态、secret 来源（只记 env/config/missing，不记录值）、online/auto 文献配置、DOI/URL seed 数量、benchmark manifest 数量、standalone benchmark/fulltext 预验证、release 必填字段和最终 gold run 必需证据汇总成启动前 checklist。`launch_manifest.status=ready_to_start` 只在 doctor 完全 ready 时出现；`blocked` 或 `needs_review` 时不要启动正式 gold run。

Web UI 的 “Gold Doctor” 按钮会用当前左侧表单的 LLM、online/auto 文献、seed papers、benchmark manifest 和 release 元数据执行同一套只读检查；默认不 ping LLM、不写 run 目录、不启动 pipeline。若当前选中了历史 run，Web doctor 会把该 run 作为候选 end-to-end run 一并检查，并且只显示公开摘要，不暴露 API key、邮箱、内部 detail/action 或绝对路径。

正式启动 gold run 时优先使用严格入口，而不是普通 `run`：

```bash
PYTHONPATH=src python3 -m research_agent gold-run-launch \
  --topic "your paper topic" \
  --literature-provider online \
  --literature-sources semantic_scholar,openalex,arxiv,crossref \
  --seed-paper 10.xxxx/example.review \
  --seed-paper https://doi.org/10.xxxx/example.benchmark \
  --seed-paper https://arxiv.org/abs/xxxx.xxxxx \
  --execution-mode benchmark \
  --execution-repeats 3 \
  --benchmark-manifest benchmarks/<domain>/manifest-candidate.json \
  --benchmark-manifest benchmarks/<domain>/manifest-baseline.json \
  --benchmark-manifest benchmarks/<domain>/manifest-ablation.json \
  --release-code-repository-url https://github.com/org/repo \
  --release-code-archive-doi 10.xxxx/zenodo.xxxxx \
  --release-code-license MIT \
  --release-code-version v1.0.0 \
  --release-data-access-statement "Public benchmark data are available from ..." \
  --release-environment-url https://... \
  --out runs/<gold-run>
```

对当前仓库内置的 UCI Iris gold 路径，可以用两种安全入口注入本地网关环境。Web 路径适合人工点选和观察；它会先检查端口、本地 LLM gateway socket、真实 contact email，并运行只读 `gold-defaults-smoke`，最后才用隐藏输入读取 `OPENAI_API_KEY`，或从 `RESEARCH_AGENT_OPENAI_API_KEY_FIFO` 指向的 600 权限 FIFO 读取一次 key；读取 key 后还会先执行 `gold-run-doctor --ping-llm --no-write` 和 `gold-launch-bundle --no-write`，确认 key/gate 可用后才启动 Web 服务：

```bash
RESEARCH_AGENT_WEB_REPLACE=1 scripts/start_gold_web_env.sh
```

默认路径仍是隐藏输入读取 API key；`RESEARCH_AGENT_OPENAI_API_KEY_FIFO` 只用于非交互自动化或需要由另一个安全终端传递 key 的场景。

纯 CLI 路径同样会先检查本地 LLM gateway socket，再校验真实 `RESEARCH_AGENT_CONTACT_EMAIL`，随后先运行只读 `gold-defaults-smoke`，最后才用隐藏输入或 `RESEARCH_AGENT_OPENAI_API_KEY_FIFO` 读取 `OPENAI_API_KEY`；contact email 缺失、使用 `example.org/example.com` 等占位域名、gateway 不可达，或默认论文级输入 blocked 时，脚本都会在读取 API key 之前退出。读取 key 后它会跑 `gold-run-doctor --ping-llm` 和 bundle gate，bundle ready 后再请求确认启动；正式 launch 返回后，只要 run 目录已经创建，脚本都会自动重跑 `gold-run-verify` 并写出最新 `perfect-readiness` 报告；如果 gold verification blocked，还会用 `15-gold-run-verification.json` 生成只读 `12-repair-resume-plan` 预案，同时保留原始 launch 失败码，避免 blocked run 漏掉最后的诊断闭环。可用 `RESEARCH_AGENT_GOLD_DRY_RUN=1` 只验证 gate，不启动 run：

```bash
scripts/run_gold_cli_env.sh
```

非交互自动化测试时不要把 key 写入命令行。可以用一次性 FIFO：

```bash
fifo_dir="$(mktemp -d /tmp/research-agent-key.XXXXXX)"
fifo="$fifo_dir/openai_key.fifo"
mkfifo -m 600 "$fifo"
RESEARCH_AGENT_OPENAI_API_KEY_FIFO="$fifo" RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh &
read -rsp "OPENAI_API_KEY: " k; printf '\n'; printf '%s\n' "$k" > "$fifo"; unset k
rm -f "$fifo"; rmdir "$fifo_dir"
```

如果已经在当前 shell 安全设置了环境变量，也可以直接用简化入口，避免手工复制 config、standalone benchmark/fulltext run 和 release 元数据：

```bash
PYTHONPATH=src python3 -m research_agent gold-defaults-smoke

PYTHONPATH=src python3 -m research_agent gold-launch-bundle \
  --topic "Iris classification benchmark smoke" \
  --gold-defaults \
  --no-write

PYTHONPATH=src python3 -m research_agent gold-run-launch \
  --topic "Iris classification benchmark smoke" \
  --gold-defaults \
  --out runs/iris-classification-benchmark-smoke-gold-run
```

`gold-defaults-smoke` 是只读聚合检查：它自动套用 UCI Iris DOI/URL seeds、全文路径、三角色 benchmark manifests、standalone support runs 和 release 覆盖项；若输出 `ready_except_server_environment`，说明本地论文级输入已通过，当前只需要用 `scripts/start_gold_web_env.sh` 或 `scripts/run_gold_cli_env.sh` 交互注入服务端 LLM/contact 环境。

两个脚本都会在读取 API key 前检查 `OPENAI_BASE_URL` 对应的 socket；若你的网关由其他方式按需启动，先人工确认风险后可设置 `RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK=1` 跳过该预检。
Web/CLI 的 Gold Env Kit 也会返回只读的服务端环境摘要：必填环境变量已配置数量、缺失变量名、可选文献 API key 数量，以及 gateway socket 是否可达；它只报告变量名和 socket target，不返回或保存任何 secret 值。

`gold-run-launch` 会强制启用 paper-grade，先执行 Gold Launch Bundle，只有 `ready_to_start` 且 `can_start_gold_run=true` 才会创建 run 并启动 pipeline；blocked 时退出 `2` 且不创建 `--out` 目录。非 dry-run 正式启动还会拒绝已有 `--out` 目录，避免把新 gold 证据混写进旧 run。启动后它会把 `00-gold-launch-bundle.md/json` 写入 run 目录；pipeline 完成后再自动写入 `15-gold-run-verification.md/json`，若最终 verification blocked，会同时生成只读 `12-repair-resume-plan` 预案；随后还会刷新项目根目录的 `perfect-agent-readiness.md/json` 并打印状态摘要。Web UI 的 “Gold Launch” 按钮执行同一 gate，只提交非 secret 表单字段，API key 仍必须来自服务端环境变量；Web 后台 worker 在 gold run 完成后也会自动写入同一套 `15-gold-run-verification` 验收产物，blocked 时写出 `12-repair-resume-plan`，并刷新项目级 readiness。

如果已经有一条完整候选 run，可以额外传 `--candidate-run-dir runs/<candidate-run>`，doctor 会只读检查该 run 是否同时满足 online paper-grade literature、真实 benchmark/adapter、claim traceability、claim consistency、`10-release-metadata.json` 的 `ready_for_release` 状态、submission package、`13-run-economics-audit.json` 的 `pass` 状态、scorecard、run integrity、repair queue 和 final handoff；负/中性结果必须闭合 `negative_or_neutral_no_superiority` 边界，否则 `candidate_gold_run` 会 fail。

正式 run 跑完后，也可以不重新执行 doctor/env/preflight，直接验收 run 目录里的最终 gold 合同：

```bash
PYTHONPATH=src python3 -m research_agent gold-run-verify \
  --run-dir runs/<candidate-run>
```

该命令会写入 `15-gold-run-verification.md/json`，只读检查 `state.json`、`run-config.json`、`run-manifest.json`、`run-llm-ledger.json`、`01-literature-gate-decision.json`、`04-benchmark-evidence-audit.json`、`10-claim-traceability.json`、`10-claim-consistency.json`、`10-release-metadata.json`、`11-submission-package.json`、`12-repair-queue.json`、`13-llm-trace-audit.json`、`13-llm-runtime-contract.json`、`13-run-economics-audit.json`、`13-agent-observability-audit.json`、`13-llm-observability-summary.json`、`13-agent-stage-contract.json`、`13-agent-trajectory.json`、`13-research-scorecard.json`、`14-run-integrity-audit.json` 和 `14-final-handoff.json` 是否共同满足 gold-run 合同；其中 LLM/provenance/observability/stage/trajectory 审计必须 `status=pass` 且没有 blocking/manual tasks。验收还会要求这些 required artifacts 是 run 目录内的普通文件，拒绝 symlink、目录和路径逃逸；并比对 `run-manifest.json` artifact inventory 是否只使用安全相对路径、是否唯一记录这些必需产物，且 SHA256/bytes 与磁盘一致；`15-gold-run-verification.json` 自身必须是当前 `schema_version=2` 的只读报告，`required_artifacts` 必须正好覆盖当前 23 项且无 extra/duplicate，顶层 `contract_evidence` 必须明确记录 final ZIP 和 audit contract 证据，`artifact_safety`、`manifest_inventory` 和 `secret_scan` 子报告也必须带当前 schema，artifact hash key 必须正好对应当前 required artifacts，且每条记录必须含有效 SHA256 和正数 size。它同时额外扫描 run 目录文本产物中是否出现 secret-like API key/token，并会阻断但不读取 symlink 或路径逃逸引用的外部目标。blocked 时会输出结构化 repair plan、unsafe artifact 计数和 secret scan 计数/相对路径；加 `--write-repair-resume-plan` 可在 blocked 时用刚写出的 `15-gold-run-verification.json` 生成只读 `12-repair-resume-plan`。它不调用 LLM、不联网、不读取或打印 API key 值。

`perfect-readiness` 判定 gold run 时还会重新读取当前磁盘上的 `run-manifest.json`，用当前 required artifact hash/bytes 复核 manifest inventory 的缺失、重复、hash/size mismatch 和 unsafe path；同时重新读取当前 7 个 audit artifact，确认 LLM trace/runtime、run economics、agent/LLM observability、stage contract 和 trajectory 都仍是 `status=pass` 且无 blocking/manual tasks，并要求 `15-gold-run-verification.json` 的 `status`、`gold_contract_ready`、`check.status`、`missing_artifacts` 和 `repair_plan` 顶层结论一致，顶层 audit summary 计数与 `audit_contracts` 字典计算结果一致，顶层 `unsafe_artifacts` 与 `artifact_safety.unsafe_artifacts` 明细一致，`manifest_inventory` 的 checked/recorded/safe-to-render summary 与必需产物合同一致，`secret_scan` 的 scanned/skipped/finding/truncated/safe-to-render summary 与 findings 明细一致且 rules 完整覆盖 secret-like token、API key 字段、环境变量、认证 header、URL query token 和 unsafe file reference。即使历史 `15-gold-run-verification.json` 中的 `manifest_inventory`、`audit_contracts`、artifact safety 或 secret scan 摘要写着 pass，当前 manifest、audit JSON 或 verification summary 被篡改、过期也会阻断。
Web UI 的 “Gold Verify” 按钮对当前选中的 run 执行同一套验收逻辑；它只提交 `candidate_run_id`，不调用 LLM、不读取表单 secret，并会把公开的 `15-gold-run-verification.md/json` 写回 run 目录。若验收 blocked，Web 会同时写出 dry-run `12-repair-resume-plan.md/json` 并刷新项目级 `perfect-agent-readiness.md/json`，返回的 API 摘要仍会过滤本地绝对路径、内部 detail/action 和私有 markdown。

若 doctor 给出 `candidate_gold_run.repair_plan`，可把该报告显式并入修复恢复预案：`PYTHONPATH=src python3 -m research_agent repair-resume runs/<candidate-run> --dry-run --gold-run-doctor-report runs/<doctor-run>/00-gold-run-doctor.json`。如果已经有 blocked 的 `15-gold-run-verification.json`，也可以用 `--gold-run-verification-report runs/<candidate-run>/15-gold-run-verification.json` 把顶层 `repair_plan` 转成 `gold-verification:*` 修复任务。也可以在 doctor 阶段直接加 `--write-candidate-repair-resume-plan`，让 doctor 把 dry-run 版 `12-repair-resume-plan.*` 写回 `--candidate-run-dir`。这会把 doctor/gold verification 的 gold-run 阻断项转成 `12-repair-resume-plan` 修复任务，并与现有 `12-repair-queue` 共同决定最早重跑入口；dry-run 不删除产物、不恢复 pipeline。

只有 `gold-run-doctor` 为 `ready`，且随后完整 pipeline 通过 review gate、execution gate、claim traceability、claim consistency，并达到 `ready_for_human_handoff` 或更强的 `ready_for_submission_upload`，`perfect-readiness` 才会把 `gold_end_to_end_run` 标为 ready。若 benchmark 是负/中性结果，claim consistency 必须证明正文保留了“不优于/未观察到优势”的边界，不能写成 superiority claim；`final-handoff` 也会把 `publishable_negative_or_neutral_result=true` 但缺少 `negative_or_neutral_no_superiority` 边界的 run 标为 blocked。
`perfect-readiness` 的 gold-run 判定还会复核 `11-submission-package.json`、`13-run-economics-audit.json`、`13-research-scorecard.json` 和 `14-run-integrity-audit.json` 的源状态；即使 `14-final-handoff.json` 被误标 ready，只要 package/run economics/scorecard/integrity 源 artifact 仍 blocked，也不会算作 gold end-to-end run。若最终状态是 `ready_for_submission_upload`，package 和 scorecard 必须都是 `ready_for_human_submission_upload`，run economics 必须为 `pass`，且 run integrity 必须为 `pass`；若只是 `ready_for_human_handoff`，允许仍有非阻断人工核验项。

仓库内还提供了一个轻量正式外部 benchmark pack：`benchmarks/uci-iris-classification/`。它使用 UCI Machine Learning Repository 的 Iris 数据集（DOI `10.24432/C56C76`，CC BY 4.0），包含冻结本地数据、固定 stratified split、无第三方依赖的 grader、candidate/baseline/ablation 三角色 manifest，以及 majority、dummy-stratified、Gaussian NB、decision tree、linear logistic 等 `role=other` reference baselines。可用下面的命令验证该 pack 的 paper-grade benchmark contract：

```bash
PYTHONPATH=src python3 -m research_agent paper-grade-benchmark-probe \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-candidate.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-baseline.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-ablation.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-majority.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-dummy-stratified.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-gaussian-nb.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-decision-tree.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-linear-logistic.json \
  --execution-repeats 3 \
  --allowed-command python3 \
  --out runs/uci-iris-benchmark-probe
```

也可以直接执行该 pack，生成正式 04 系列 benchmark/statistics/audit 产物：

```bash
PYTHONPATH=src python3 -m research_agent benchmark-pack-run \
  --topic "Iris classification benchmark pack execution" \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-candidate.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-baseline.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-ablation.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-majority.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-dummy-stratified.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-gaussian-nb.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-decision-tree.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-linear-logistic.json \
  --execution-repeats 3 \
  --allowed-command python3 \
  --out runs/uci-iris-expanded-baseline-pack-run
```

这个 standalone run 会把 `statistical_design` 的真实 benchmark 统计证据补齐；当前样板 pack 中 candidate 与主 baseline 在 3 个指标上没有观察到差异，因此 `04-benchmark-evidence-audit.json` 会标记 `statistical_outcome=neutral_no_observed_difference`、`claim_boundary_severity=negative_or_neutral_no_superiority`、`publishable_negative_or_neutral_result=true`，表示可作为负/中性结果报告，但不得声称 candidate 优于 baseline。如果没有完整 LLM run、人工 gate、全文 grounding 和 final handoff，`perfect-readiness` 仍会保留 `gold_end_to_end_run` 阻断。

UCI pack 还带有官方数据描述的本地全文副本，可用它验证 fulltext citation grounding：

```bash
PYTHONPATH=src python3 -m research_agent fulltext-grounding-run \
  --topic "UCI Iris fulltext citation grounding" \
  --fulltext-path benchmarks/uci-iris-classification/fulltext/iris.names.txt \
  --claim "The UCI Iris description states that the data set contains three classes of 50 instances each and four numeric predictive attributes plus the class label." \
  --out runs/uci-iris-fulltext-grounding
```

该 run 会补齐 `fulltext_citation_grounding` 的真实本地全文证据；没有完整 LLM run 和 final handoff 时，`perfect-readiness` 仍只剩 `gold_end_to_end_run` 阻断。

如果已经有官方 benchmark/data URL、本地冻结 split/task manifest 和本地 grader/evaluator wrapper，可先生成三角色 manifest 草稿。该命令只复制用户提供的本地文件、计算 SHA256 并写 manifest，不下载外部代码、不执行 benchmark：

```bash
PYTHONPATH=src python3 -m research_agent benchmark-manifest-build \
  --out-dir benchmarks/ompl-paper-run \
  --name "ompl motion planning" \
  --benchmark-url "https://ompl.kavrakilab.org/benchmark.html" \
  --dataset-url "https://ompl.kavrakilab.org/benchmark.html" \
  --dataset-version "ompl-1.6.0" \
  --split-name "official task manifest v1" \
  --split-file path/to/split-manifest.json \
  --grader-file path/to/official-evaluator-wrapper.py \
  --grader-version "ompl-wrapper-v1" \
  --license "BSD-3-Clause" \
  --baseline "RRT*" \
  --baseline-version "ompl-1.6.0" \
  --citation "10.1109/MRA.2012.2205651" \
  --metric "success_rate:higher_is_better:ratio:Fraction of tasks solved" \
  --metric "planning_time:lower_is_better:seconds:Planner wall-clock time" \
  --role-command "candidate=python3 {grader} --method ours --metrics {metrics_path}" \
  --role-command "baseline=python3 {grader} --method rrtstar --metrics {metrics_path}" \
  --role-command "ablation=python3 {grader} --method ours_no_component --metrics {metrics_path}"
```

输出目录会包含 `candidate/manifest.json`、`baseline/manifest.json`、`ablation/manifest.json`，以及 `benchmark-manifest-build-report.md/json`。生成后仍需人工核对三类 role 的命令是否真的运行对应方法，再运行 `paper-grade-benchmark-probe` 和 `preflight --paper-grade`。正式 paper-grade gate 会检查三类 role 的命令不能只改变 metrics 输出路径；命令中应显式包含 method、variant 或 config 差异。

支持的轻量级来源：

- `semantic_scholar`：论文元数据、摘要、引用数、DOI/外部 ID。
- `openalex`：跨学科 Works 元数据、摘要、引用数、DOI/外部 ID，适合作为 Semantic Scholar 限流时的补充来源。
- `crossref`：跨学科 DOI 元数据和出版信息。
- `arxiv`：预印本元数据和摘要。
- `pubmed`：PubMed 题录元数据，适合生物医学课题。

可选环境变量：

```bash
export SEMANTIC_SCHOLAR_API_KEY=...
export OPENALEX_API_KEY=...
export RESEARCH_AGENT_CONTACT_EMAIL="<your-real-contact-email>"
```

运行产物 `01-literature.md` 会包含检索诊断、实际检索式、候选证据表、去重后的相关文献和摘要；`01-literature.json` 保留结构化字段，方便后续接 RAG、引用管理或人工审核 gate。

如果 sources 中启用了 `crossref`，系统还会对带 DOI 但作者、年份、venue 或摘要过薄的 OpenAlex/Semantic Scholar/arXiv/PubMed 题录做一轮有上限的 Crossref DOI 元数据补强；补强结果会写入检索诊断中的 `crossref_enrichment`，并在去重合并时保留更可靠的主来源，避免单源 Crossref 薄题录挤掉语义更完整的候选。

检索后会先生成 `01-literature-rerank.md/json`：按 topic overlap、标题特异性、选中检索式覆盖、baseline/benchmark 命中、venue/source 可靠性、DOI/URL/作者/年份/摘要完整性、多来源可信度、引用数和人工 seed 信号重排候选。单源 Crossref、无摘要/短摘要、无 DOI/URL、弱主题匹配、标题过泛、venue/source 信号弱或不覆盖检索式的题录会被降权；该分数会写回 `01-literature` 的 relevance，再进入质量筛选和 context。

每次检索还会生成 `01-literature-search-strategy.md/json`：记录候选检索式的来源、用途、优先级、风险、最终选中的检索式、策略状态和人工改进建议。系统会先检查 selected queries 是否覆盖 method/baseline/benchmark 等必需 intent、是否包含过宽查询、在线来源是否过少；`review_required` 或 `needs_query_repair` 会进入 scorecard/repair queue。系统会优先加入领域规则检索式，例如机械臂路径规划会覆盖 RRT/PRM、CHOMP/STOMP/TrajOpt 和 OMPL benchmark，减少过宽查询带来的弱相关论文。Web 表单中的“补充检索式”会作为高优先级 human query 进入策略选择，可直接承接上一轮 `01-literature-search-feedback` 推荐的 query。

在线检索会默认启用本地 HTTP 缓存，减少重复请求和 Semantic Scholar 429 限流风险。缓存配置在 `[literature]` 中：

```toml
cache_enabled = true
cache_dir = ".cache/research-agent/literature"
cache_ttl_seconds = 604800
```

每次检索都会生成 `01-literature-source-health.md/json`，记录每个来源的状态、返回条数、错误数、限流情况、用时、cache hit/miss/stale 计数，以及每个 selected query 在每个 source 上的执行状态。若网络失败或 429 但存在过期缓存，系统会优先使用 stale cache 并在源健康表里记录。

`01-query-execution-audit.md/json` 会把 `01-literature-search-strategy`、`01-literature-source-health` 和 `01-literature-rerank` 串起来，审计 selected query 是否覆盖 method/baseline/benchmark 等必需意图、每条 query 是否有 source 返回、是否进入候选池、是否有高质量命中，以及 Top rerank 候选是否真正覆盖检索式。状态为 `needs_source_repair` 会进入 repair queue 并阻断下游；`needs_query_repair` 或 `review_required` 会要求补 query/seed 后重新生成文献 gate。未闭环的 selected query 也会进入 `01-literature-search-feedback`，生成结构化 `query_execution_repair` 任务，供 `repair-resume` 作为下一轮 bounded rescue search 的额外检索式执行。

质量筛选后还会生成 `01-literature-snowball.md/json`：从高质量 seed papers 生成 DOI、精确标题、related-work/cited-by 和 benchmark/baseline 扩展检索式，同时列出 Semantic Scholar 429、来源失败、DOI 覆盖不足、候选过少等修复动作。它用于下一轮检索补强，避免只靠一次宽泛在线搜索决定文献池。

筛选文献还会生成 `01-literature-coverage.md/json`：对照 `00-research-plan` 中的 benchmark、baseline、metric 和领域必需 facet，审计当前 curated 文献是否覆盖关键方法族、数据集和评价入口；缺失时会给出带 `terms` 和 `suggested_queries` 的补检索动作，防止后续 idea/实验建立在不完整文献池上。

如果 `01-literature-rescue-plan.md/json` 判断文献池薄弱，在线或 auto 模式会自动执行一轮 bounded rescue search，并写入 `01-literature-rescue-execution.md/json`：只运行 priority >= 94 的补检索式，最多 6 条；新候选会和第一轮结果去重、候选重排、过滤，并重新生成质量筛选、覆盖审计和检索反馈。补检索计划现在也会读取 `01-literature-quality` 的缺失 evidence role，自动生成 `missing_evidence_role` query，补齐 review/survey、benchmark/dataset、baseline/method 或 recent work anchor。执行报告还会按 query / repair task 记录 `query_outcomes`，说明补检索是否命中候选、带来新增去重文献并进入最终候选池；未闭环时会进入 `12-repair-queue`。离线模式会记录 `not_applicable`，不会伪装成在线补检索。

系统还会生成 `01-literature-search-feedback.md/json`：把质量筛选、候选重排、覆盖审计、证据组合、滚雪球、补检索计划和文献源健康合并为下一轮检索反馈策略，列出推荐检索式、人工 seed paper 目标、source 修复动作、结构化 `retrieval_repair_tasks` 和建议的 `literature_provider/max_papers/max_search_queries`。如果文献池薄弱，批准前应先按该反馈策略补检索或补 seed；这些任务也会进入 `12-repair-queue`。

人工填写 `seed_papers` 后会生成 `01-seed-paper-intake.md/json`：逐条检查 seed 是 DOI、URL 还是标题-only，是否进入原始文献池、是否进入 `01-literature-curated`、是否被质量筛选保留，以及和课题关键词/领域同义词是否有重叠。如果用户给的核心 seed 没有进入 curated context，人工审核 gate 会提示先修复 DOI/URL、质量筛选或写明豁免理由，再允许进入 idea/实验。

历史 run 即使没有 `01-seed-paper-intake.json`，系统也会从已筛选/curated 文献中提取候选 DOI/URL seed，显示建议覆盖的 review/benchmark/baseline/recent 角色，并把仍缺角色转成可应用到表单的补检索 query；同一份建议会进入 open-source compliance、research scorecard 和 repair queue，避免只停留在 Web 提示层。

### 文献质量筛选

在线检索和离线回退之后，系统会在进入 RAG/idea 前生成一个文献质量筛选层：

- `01-literature-rerank.md/json`：逐篇记录候选重排分数、topic/query 覆盖、标题特异性、venue/source 分、baseline/benchmark 命中、metadata/source 分数、降权原因和建议动作。
- `01-query-execution-audit.md/json`：逐条记录 selected query 的 source 返回、候选命中、高质量命中、intent 覆盖和 Top rerank 覆盖；用于定位文献差是 API/source 问题、检索式问题还是重排候选污染。
- `01-literature-quality.md/json`：逐篇给出质量分、`keep/review/exclude` 决策、是否进入上下文、evidence role（review/survey、benchmark/dataset、baseline/method、recent work）和原因；整批证据还会计算角色覆盖，避免只有泛泛相关或单一 recent work 的候选直接进入 idea/实验。
- `01-literature-curated.md/json`：筛选后的文献集合，后续 `01-context`、人工审核 gate、idea、实验计划和论文草稿都使用该版本。
- 质量筛选宁可保留更少文献，也不会用 `exclude` 候选凑满 `min_keep`；无 DOI/URL 且摘要过薄的高相关假象题录会被硬降级并阻止进入上下文。
- `01-literature-metadata-audit.md/json`：对保留文献检查 DOI、URL、作者、年份、摘要长度、来源交叉验证和题目/摘要主题匹配；`block` 或 `literature_repair_required` 会进入人工审核 gate，阻止低可核验文献池直接进入 idea/实验。
- `01-literature-evidence-mix.md/json`：检查筛选文献整体是否覆盖综述/高引用入口、benchmark/dataset、baseline/method、近期研究和可核验 metadata；缺 anchor、单源 Crossref 薄摘要或 locator 不足会进入 gate、repair queue 和 scorecard。

评分会综合 topic 匹配、摘要可用性、DOI/URL/作者/年份、来源数量、引用数和原始相关性。原始检索结果不会被覆盖，方便人工回看被排除的候选。

### 检索质量与限流

在线模式会先用 LLM 生成英文 scholarly search queries，再多源检索、去重、排序和相关性过滤。默认源包含 Semantic Scholar、OpenAlex、arXiv 和 Crossref；Semantic Scholar 无 API key 时容易返回 429，设置 `SEMANTIC_SCHOLAR_API_KEY` 可显著减少限流。OpenAlex 可通过 `OPENALEX_API_KEY` 配置授权。LLM 超时可设置：

`01-literature-evidence-mix` 用来解决“搜到的论文看起来都很差”的组合级问题：单篇质量分通过还不够，系统还会要求文献包至少有综述/高引用锚点、benchmark/dataset、baseline/method 和近期研究。状态为 `block` 或 `needs_evidence_upgrade` 时，`01-review-gate` 会要求先补检索或补 seed paper，再由人工决定是否继续。

```bash
export OPENAI_TIMEOUT_SECONDS=120
export OPENAI_MAX_ATTEMPTS=3
```

## Phase 2: Literature Context, Citations, and Review Gate

第二阶段在文献调研后自动生成一个可审核的文献上下文包：

- `01-fulltext-corpus.md` / `01-fulltext-corpus.json`：读取配置中的本地 `.txt/.md/.pdf` 论文全文路径，记录文件 hash、抽取状态、chunk 数和警告。
- `01-context.json`：结构化 RAG chunks、引用条目、claim-support 表和 gate 状态。
- `01-context.md`：人工可读的文献上下文包。
- `01-review-gate.md`：进入 idea 生成前的人工审核清单。
- `01-citation-audit.md` / `01-citation-audit.json`：逐条审计 citation key、DOI、URL、年份、作者、来源和人工种子引用，标记 `usable/review/block`。
- `01-references.bib` / `01-references.ris`：可导入 Zotero、EndNote 或其他引用管理器。

当前 gate 是 blocking：生成 `01-review-gate.md` 和 `approval.json` 后，状态进入 `awaiting_review_approval`，必须由人工在 Web UI 点击“批准继续”或运行 `research-agent approve <run_dir>`，才会进入 idea 生成、实验计划和实验执行阶段。gate 状态为 `review_required`、`literature_repair_required`、`block` 等非 `pass` 值时，批准必须带审核意见或修复说明，否则 Web/CLI 不会继续；直接把 `approval.json` 改成 `approved: true` 也不会让流水线通过等待检查。

如果人工选择退回，系统会写入 `01-review-revision-plan.md/json`，把退回意见、文献覆盖、质量筛选、引用完整性和文献源健康问题整理成修复项、resume 命令、停止条件和再次批准 checklist。修复前 run 会停在 `review_revision_requested`，不会进入 idea 或实验；退回后再次点击批准会先用最新配置和 seed papers 重新生成 `01-literature*`、`01-seed-paper-intake*`、`01-context*` 和 `01-review-gate.md`，只有新 gate 的批准策略满足后才会继续。

本地全文语料可通过 Web 表单“本地全文文件”填写，或 CLI 使用 `--fulltext-path path/to/paper.txt`。`.txt/.md` 会直接抽取文本；`.pdf` 会优先尝试 `pypdf`，缺少依赖时使用轻量 fallback 并在 `01-fulltext-corpus.md` 标记人工核对警告。

如只想验证本地全文和 citation grounding 链路，而不启动完整 LLM run，可使用 `fulltext-grounding-run`。它会从本地全文构建 `01-fulltext-corpus` 与 `01-context`，生成一段带稳定 citation key 的 grounding note，再运行 `10-citation-grounding` 审计；这只证明全文 grounding 能力，不代表完成论文写作或人工 review gate。

引用审计参考 PaperQA/OpenScholar/STORM 这类 citation-grounded 系统的要求：进入 idea 前先把不可核对或元数据不完整的引用暴露出来，避免后续论文草稿建立在不可引用候选上。

## Agent Stage Contract Audit

`13-agent-stage-contract.md/json` 会把 AI Scientist、Agent Laboratory、PaperQA2 和 MLAgentBench 这类开源科研 agent 项目的关键模式转成阶段契约：研究计划、grounded 文献、人类 gate、idea 探索、实验设计、执行证据、论文复核闭环、代码/数据归档和可恢复观测性。它不同于 `13-research-scorecard` 的综合打分，也不同于 `14-run-integrity-audit` 的文件完整性检查；它回答的是“这个 run 是否满足一个科研 agent 平台应有的阶段职责”。

如果状态为 `block`，优先处理 `blocking_issues`，再使用 `repair-resume` 或 checkpoint resume 重新生成受影响阶段。状态为 `needs_human_review` 时，说明自动产物完整但仍存在人工待办，例如真实 benchmark、投稿格式或代码/数据归档信息。

`13-agent-trajectory.md/json` 会把 `run-manifest` 的底层事件和关键 gate/audit 状态聚合成面向人工检查的阶段轨迹：planning、literature grounding、human gate、ideation、experiment design、execution/analysis、writing/review 和 release/observability。它借鉴 AI-Scientist-v2/MLGym 这类项目保留实验树或 trajectory 以便复盘的做法，用来快速定位“当前 run 走到哪、哪段 warning/block、下一步该看哪个产物”。

## LLM Trace Audit

`13-llm-trace-audit.md/json` 会检查 `run-llm-ledger` 是否覆盖关键科研阶段：research planning、literature synthesis、idea generation、experiment planning、paper writing、paper review loop 和 paper revision。若已生成这些阶段产物但 ledger 中没有对应 `success` 调用，或存在 `failed` / `budget_exceeded` 调用，状态会变为 `block`，并进入 `12-repair-queue`、`13-research-scorecard`、投稿包和 `14-run-integrity-audit`。

该审计不保存或读取完整 prompt/response，只使用 purpose、状态、长度和 hash。模型成功返回后再做结构化 JSON 修复不算离线 LLM 兜底；但模型完全缺席、失败或预算拦截不能被当作完成的自动科研 run。

## Run Economics Audit

`13-run-economics-audit.md/json` 会把 `run-llm-ledger` 按科研阶段汇总为调用数、成功/失败/预算拦截、输入/输出字符数、估算 token、阶段耗时和可选美元成本。Token 估算使用 `ceil(chars / 4)`，只用于 run 级趋势和预算诊断，不替代供应商账单。

默认只报告 token 和耗时。如果在配置中填写 `llm.input_cost_per_million_tokens` 与 `llm.output_cost_per_million_tokens`，审计会同时估算总成本和阶段成本；缺失 ledger、失败调用或预算拦截会进入 `12-repair-queue`。

## Agent Observability Audit

`13-agent-observability-audit.md/json` 会把 `state.json`、`run-manifest`、`run-llm-ledger`、`run-config`、人工 approval、执行 approval、`04-experiment-runbook`、诊断/恢复计划和 repair queue 串成运行可观测性审计。它重点回答“这个 run 失败、卡住、预算耗尽或需要恢复时，是否有足够轨迹让人和 agent 继续处理”，而不是评价论文质量。

状态为 `block` 时会进入 `12-repair-queue`，通常表示 manifest/ledger/human gate/runbook/诊断恢复断链。状态为 `review_required` 时多半是 LLM 预算接近上限、旧 run 缺少 run-config、artifact trace 不完整或 repair queue 仍需人工处理。

## Open-Source Lesson Compliance

`13-open-source-compliance.md/json` 会逐条检查 `00-open-source-lessons` 中从 AI-Scientist-v2、Agent Laboratory、PaperQA2/OpenScholar 和 MLAgentBench/MLE-bench 类项目吸收的约束是否真的落到本次 run 的产物里。`00-open-source-lessons.json` 同时保存 `contract_summary`，记录本轮必须覆盖的参考项目、project evidence 和 lesson id；`13-open-source-compliance` 会先校验这个 contract 完整性，再检查各阶段产物，防止通过删减 lesson 绕过外部项目约束。它会核对开源项目 provenance、结构化 idea->experiment 链路、query/source 覆盖审计、citation grounding、human feedback compliance、execution safety、benchmark result schema、LLM trace/run economics、observability、AI disclosure 和领域 benchmark 约束。缺少 `contract_summary`、`project_evidence`、仓库 URL 或证据目标文件时会阻断；只有内置编目而没有实时 commit 核对时不会阻断，但报告会保留 provenance 状态，避免把未刷新版本误当成强证据。

状态为 `block` 或 `needs_human_review` 时会进入 `12-repair-queue` 和 `13-research-scorecard`。这样外部项目经验不只是 prompt 里的建议，而是会成为可修复、可复查的阶段契约。

## Phase 3: Evidence-Grounded Ideas and Experiment Plans

第三阶段把人工批准后的 idea/实验阶段改成文献证据约束：

- `02-research-gap-map.md/json`：把 review.gaps、文献 coverage 缺失、人工审核约束和 RAG chunk 合成研究空白矩阵；每个 gap 都标注 evidence strength、testability、baseline、benchmark/data、指标、检索补救建议和实验提示。Idea 生成会优先围绕 `ready` gap。
- `02-agent-team.md/json`：根据研究计划、文献覆盖、gap map、人工约束和执行模式分配多智能体任务；内置 literature scout、evidence curator、gap analyst、method architect、benchmark engineer、statistician、skeptical reviewer 和 manuscript editor，记录每个 agent 的任务、优先级、输入/输出产物和 handoff。它还写入 `task_routes`，把 literature repair、gap-to-idea、benchmark execution、claim boundary review、paper deliberation 和 release reproducibility 路由到不同 primary/support agent 小队。Idea 生成会读取该分配并写入 `agent_roles`。
- `02-ideas.md`：每个 idea 都包含文献依据 citation key、证据 chunk、对齐的研究空白、baseline 和实验草案。
- `02-ideas.json`：结构化保存 `evidence_keys`、`evidence_chunks`、`gap_alignment`、`baseline`、`agent_roles` 和 `experiment_sketch`。
- `02-novelty-audit.md/json`：把每个 idea 与已纳入文献标题/摘要做相似度审计，标记 `likely_novel`、`review_required` 或 `likely_duplicate`；高重复风险会降低探索图分支得分。
- `02-idea-audit.md/json`：检查每个 idea 的 citation key、evidence chunk、baseline、评估指标、实验草案和人工审核约束覆盖；不可核对证据会被标记为 `block` 并在探索图中强力降权。
- `02-exploration-map.md/json/svg`：把候选 idea 转成研究分支探索图，记录综合评分、选中分支、淘汰分支、警告和可视化路径。
- `02-experiment-manager.md/json`：把探索图、idea audit 和 novelty audit 汇总成实验管理决策，记录本轮只扩展哪个分支、是否必须 smoke-first、下一轮候选分支和注入 `03-experiment-plan` 的约束。
- `03-experiment-plan.md`：根据选中 idea 生成领域相关实验目标、变量、指标、协议和 baseline。
- `03-experiment-plan.json`：结构化实验计划，保留安全模拟命令入口，并继承选中 idea 的 `agent_roles`。
- `03-agent-handoff-audit.md/json`：执行前检查 `02-agent-team`、选中 idea 和 `03-experiment-plan` 的多智能体 handoff 是否连通；完全缺失 assignment、idea roles 或 plan roles 会阻断，角色族覆盖不足则要求人工复核并降级 claim。
- `03-review-constraint-compliance.md/json`：把人工审核 notes 和 `00-human-brief` 中的约束、成功标准、资源限制、风险映射到选中 idea 和实验计划；高优先级约束缺失会进入 `block`，并由实验审计阻止继续执行。
- `03-experiment-audit.md/json`：在执行实验前审计 baseline 公平性、metric 对齐、命令结构、文献覆盖、人工约束落实、消融计划和预注册；`block` 状态会阻止进入实验执行。
- `03-idea-experiment-contract.md/json`：在 benchmark readiness 之后、执行批准之前，把 `02-exploration-map` 选中的 idea、证据 key、baseline、metric、candidate/baseline/ablation 命令、预注册、消融和人工约束串成跨阶段契约；标题断链、无证据、占位 baseline、缺 candidate/baseline 命令或 readiness/preregistration/constraint block 会阻止进入实验执行。
- `03-execution-approval.md/json`：当执行模式为 `local` 或 `benchmark` 时，在真正运行本地命令前列出待执行命令、预期产物和 execution safety 结果，必须人工批准后才会生成 `04-results*`。
- `03-ablation-plan.md/json`：检查 candidate、baseline、ablation 命令覆盖，给出领域相关消融变体和必要动作。
- `03-preregistration.md/json`：在实验执行前锁定 primary hypothesis、primary metrics、planned comparisons、排除/停止规则和计划指纹；恢复旧 run 且已有结果时会标记为 `posthoc_checkpoint`。
- `03-benchmark-plan.md/json`：列出推荐真实 benchmark/数据集、来源 URL、许可核对、接入步骤、风险和替换模拟器的人工任务。
- `03-benchmark-readiness.md/json`：在执行批准前检查 execution mode、benchmark manifest adapter、metric/baseline 对齐和 expected artifacts；`simulated`/`local` 会提示只能支撑 smoke/local 证据，`benchmark` 模式缺 manifest 或 adapter blocked 会标记为 `block`。

LLM 返回缺少证据字段时，系统会从 `01-context.json`、`02-research-gap-map.json` 和 `02-agent-team.json` 自动检索并补齐最相关 citation/chunk、baseline、gap alignment、agent roles 和实验提示；如果 LLM 调用失败或超时，本次 run 会失败并写入诊断。只有在模型已成功返回但没有可用 idea 时，系统才会优先用研究空白矩阵和多智能体任务分配生成领域相关结构化候选，其次才退回到文献主题和 review.gaps。探索图和 experiment manager 参考 AI Scientist-v2 式多方向探索与 experiment manager 思路，但当前实现是轻量分支评分、选择记录和 smoke-first 约束，不伪装成完整树搜索；`02-idea-audit` 会在分支选择前把无效证据、弱实验轮廓和未响应人工约束的 idea 暴露出来。`03-review-constraint-compliance` 参考 Agent Laboratory 对人工 notes/参与度的强调，把 human brief 和批准意见变成可审计约束，而不是只把文本塞进 prompt。`03-idea-experiment-contract` 参考 PaperQA/OpenScholar 的 evidence-before-synthesis 思路，把 idea 证据链是否真正落到实验计划里作为执行前 gate。实验执行命令仍由系统提供，避免让模型生成任意 shell 命令。Benchmark 接入计划用于把当前模拟模板迁移到真实公开任务集；代码/数据可用性审计会检查该计划是否存在。

## Phase 4: Paper Review and Claim Audit

第四阶段在论文草稿之后自动生成审稿式复核：

- `07-paper-review.md`：模拟审稿决定、总分、分项评分、优点、问题、必须修改项和 Claim-Grounding 审计表。
- `07-paper-review.json`：结构化保存审稿分数、revision 清单和每条关键 claim 的支撑状态。
- `07-paper-review-calibration.md/json`：把审稿分数和决定与 unsupported/weak claims、实验后决策、假设结果和执行模式对齐，标记过宽自评并把校准任务传入修订计划。

复核阶段参考 AI Scientist 类项目的 simulated review 思路，并结合文献/实验产物做 claim-grounding 检查。LLM 可用时会生成结构化审稿 JSON；如果 LLM 调用失败或超时，本次 run 会失败并写入诊断。只有在模型已成功返回但格式不合格时，系统才会使用规则审计草稿中的关键主张，标记 supported、weak 或 unsupported，避免没有复核就直接把草稿当成最终论文。

论文写作阶段会把 `01-context` 的 citation key 和 `agent_roles` 注入写作提示；AI 草稿如果没有使用可追踪 `[citation_key]`，会被视为格式不合格并改用规则草稿。规则草稿会在正文和“参考证据”小节写入稳定 key，并保留多智能体责任边界，方便后续 claim traceability、agent owner audit 和参考文献核对。

复核之后系统会继续生成：

- `08-revision-plan.md`：把必须修改项和 weak/unsupported claims 转成可执行修订任务、验收检查和下一轮修改提示。
- `08-revision-plan.json`：结构化保存任务 ID、严重性、章节、动作、证据引用和 readiness 状态。

这一步借鉴 Agent Laboratory 类项目的人类反馈闭环：复核不是终点，而是下一轮写作和实验补强的输入。

## Phase 9: Revised Paper Draft

第九阶段把 `08-revision-plan` 应用回论文草稿：

- `09-revised-paper.md` / `09-revised-paper.tex`：基于修订计划生成的下一版论文草稿。自动修订会降级过强 claim、补充修订执行记录，并明确哪些任务不能自动完成。
- `09-revision-report.md` / `09-revision-report.json`：逐条记录修订任务的处理状态，例如 `applied_in_draft`、`draft_adjusted`、`needs_human_evidence` 或 `needs_human_verification`。
- `09-revision-response-audit.md` / `09-revision-response-audit.json`：检查 `08-revision-plan` 中每条任务是否在 `09-revision-report` 有结果、是否在修订稿“修订执行记录”中留下任务 ID 或待补证/人工核对痕迹；高优先级任务静默消失会进入 block。

这一步参考 AI Scientist 类项目的 review/improve 循环和 PaperQA2 式证据边界：自动评审不只是打分，而是反馈到下一版稿件，并留下逐条回应证据。系统不会自动编造新文献或真实实验；缺证据的任务会保留为人工补证项，并由修订响应审计传入投稿检查、repair queue、scorecard、stage contract 和投稿包。

## Phase 10: Post-Revision Audit and Readiness

第十阶段对 `09-revised-paper.md` 再做一次 claim-grounding 复核，并生成最终就绪报告：

- `10-revised-paper-review.md` / `10-revised-paper-review.json`：修订稿的第二轮审稿式复核。
- `10-claim-traceability.md` / `10-claim-traceability.json`：把修订稿关键 claim 映射到 citation key、结果指标、统计审计和实验 runbook，标记 `pass/review/block`。
- `10-agent-claim-audit.md` / `10-agent-claim-audit.json`：把每条修订稿 claim 映射到 `manuscript_editor`、`skeptical_reviewer`、`evidence_curator`/`literature_scout`、`benchmark_engineer`/`statistician` 等 owner，检查写作、复核、证据和统计/benchmark 角色是否贯穿到最终 claim。
- `10-agent-deliberation.md` / `10-agent-deliberation.json`：当前实现是基于 claim traceability、citation grounding/coverage、结果呈现和 claim consistency 的确定性角色规则审计，不是独立 Agent 执行。产物会明确写入 `assessment_kind=deterministic_role_projection` 和 `independent_agent_execution=false`；即使规则全部通过也保持 `review_required`，不能冒充独立多智能体共识。
- `10-citation-grounding.md` / `10-citation-grounding.json`：逐个检查正文 `[citation_key]` / `\cite{key}` 附近 claim 是否能和 `01-context` 中对应文献 chunk 形成可见支撑；未知 key、无 chunk 或弱重叠会进入投稿检查和分数卡。
- `10-citation-coverage.md` / `10-citation-coverage.json`：反向检查 `01-context` 中的高相关、近年、baseline/benchmark 文献是否真正进入修订稿正文，并标记未知 citation key、覆盖过低或 citation 过度集中问题。
- `10-results-presentation.md` / `10-results-presentation.json`：检查修订稿是否有明确结果章节、是否报告结构化统计指标、是否引用统计图/表、是否呈现 95% CI 或不确定性，并阻断没有统计比较却写出比较性结论的稿件。
- `10-claim-consistency.md` / `10-claim-consistency.json`：把修订稿中的强正向结论和 `04-hypothesis-outcome` 对齐；当结果是 `smoke_only`、`refuted_or_negative`、`inconclusive`、`untested` 或 `blocked_unverified` 时，阻断“证明/显著优于/支持假设”等越界表述。
- `10-release-metadata.md` / `10-release-metadata.json`：结构化记录代码仓库、许可证、版本、归档 DOI、数据访问说明和环境归档 URL。
- `10-code-data-availability.md` / `10-code-data-availability.json`：审计代码仓库、许可证、实验 runbook、结果产物、引用导出、数据/代码可用性声明和公开归档人工待办。
- `10-submission-check.md` / `10-submission-check.json`：静态检查修订稿 Markdown、TeX 基本结构、BibTeX、正文 citation key、结果呈现审计、统计图、代码/数据可用性和目标 venue 模板待办。
- `10-final-readiness.md` / `10-final-readiness.json`：比较修订前后分数、weak/unsupported claim 数量和延后任务，给出 `requires_human_evidence`、`requires_revision`、`ready_for_human_polish` 或 `ready_for_submission_check` 状态。

这一步把 review/improve 循环变成可审计 gate：即使系统生成了修订稿，只要仍有 `needs_human_evidence`、unsupported claim、claim traceability/citation grounding/citation coverage 阻断项、结果呈现或 claim consistency 阻断项、代码/数据可用性阻断项或投稿格式阻断项，就不会把它标为投稿就绪。`10-agent-claim-audit` 负责论文阶段责任追踪；`10-agent-deliberation` 当前只是确定性角色规则汇总，不是独立多智能体共识。缺失 owner 或规则汇总未通过会进入人工复核和投稿包证据，而不是自动抹掉 claim traceability 的结论。

Release metadata 可通过配置文件、CLI 或 Web 表单填写。CLI 示例：

```bash
PYTHONPATH=src python3 -m research_agent run \
  --topic "机械臂路径规划" \
  --release-code-repository-url "https://github.com/org/repo" \
  --release-code-archive-doi "10.xxxx/zenodo.xxxxx" \
  --release-code-license "MIT" \
  --release-code-version "v0.1.0" \
  --release-data-access-statement "This run uses the benchmark data described in 03-benchmark-adapters.md." \
  --llm-model "$OPENAI_MODEL"
```

如果这些字段缺失，`10-code-data-availability` 会继续保留发布元数据人工待办；如果 URL/DOI 格式错误，会作为阻断项进入最终 gate。

## Phase 11: Submission and Archive Package

第十一阶段把最终稿、引用、图、实验结果、复现手册和审计报告汇总成一个可下载的投稿/归档包：

- `11-submission-package.md` / `11-submission-package.json`：列出包内文件、缺失项、阻断问题、人工上传前待办和推荐动作。
- `11-submission-package.zip`：可下载 ZIP，包含 `submission-package/README.md`、`CHECKLIST.md`、主文稿、TeX、BibTeX、结果、统计审计、实验 runbook、修订响应审计、citation grounding/coverage 审计、最终 gate、修复队列、代码/数据审计、投稿格式检查和 run manifest。
- `submission-package/README.md`：包说明和状态摘要。
- `submission-package/CHECKLIST.md`：人工投稿前清单。

该阶段参考 AI Scientist/Agent Laboratory 的端到端论文产出思路，以及 MLAgentBench/DeployBench 类 benchmark 对可复现交付物的要求。系统会打包已有证据，但不会把仍有阻断项的 run 伪装成可投；若最终 gate、代码/数据审计或投稿格式检查仍需人工处理，`11-submission-package.md` 会继续显示 `blocked` 或 `needs_human_submission_review`。

## Phase 12: Next Iteration Plan

第十二阶段把最终审计结果转成下一轮可执行计划：

- `12-next-iteration-plan.md` / `12-next-iteration-plan.json`：读取最终 gate、代码/数据审计、投稿格式检查、投稿包、实验 runbook、experiment manager 和 benchmark plan，输出下一轮状态、优先任务、建议重跑命令、停止条件和继承说明；`02-experiment-manager` 的 smoke-first 策略、实验计划约束和下一轮候选分支会进入 carry-forward notes。
- `12-repair-queue.md` / `12-repair-queue.json`：把 query execution、文献 metadata、补检索、seed intake、idea audit、人工约束落实、实验审计、安全审计、环境快照、结果验证、benchmark result schema、benchmark 证据、hypothesis outcome、论文 grounding、claim consistency、agent observability、release 和投稿包等审计汇总成结构化修复队列，标出 `severity`、来源产物、目标产物、重跑入口、自动化/人工职责，以及是否阻断投稿或下游阶段。
- `12-repair-resolution-audit.md` / `12-repair-resolution-audit.json`：如果本轮来自 `repair-resume`，把原修复项与新生成的 `12-repair-queue` 对比，确认原来源/类别是否仍然阻断；未闭环会进入 scorecard 和 stage contract。
- `12-repair-resume-plan.md` / `12-repair-resume-plan.json`：触发 `repair-resume` 时生成，记录最早重跑入口、将清理/已清理的产物、供下一轮 agent 使用的 `repair_context`、是否需要重新人工批准 review gate 或执行 gate，以及恢复后的停止条件。

典型状态包括：

- `needs_human_evidence`：必须先补文献、真实实验或删除 unsupported claim。
- `needs_real_benchmark_iteration`：当前证据仍偏模拟或 benchmark 未接入，下一轮应优先接真实任务集。
- `needs_targeted_iteration`：需要处理代码/数据、投稿格式或打包阻断项后从 checkpoint resume。
- `ready_for_submission_upload`：可以进入人工投稿系统上传，但仍需完成 `submission-package/CHECKLIST.md`。
- `ready_for_next_research_question`：当前 run 可归档，适合开启新课题。

这一步让 Agent Laboratory 式人工反馈、AI Scientist 式 review/improve 循环和 MLAgentBench 式实验可复现要求连接起来：系统不会只给一个“完成”状态，而会明确下一轮该补什么、谁处理、重跑哪些命令、满足什么停止条件。

`12-repair-queue` 更偏机器可执行：`blocked_repair_required` 表示至少一个 block 任务未清零，不能把当前 run 当作最终投稿版本；`needs_repair` 表示没有 block，但还有 high/medium 修复或人工确认项；`pass` 表示当前审计队列没有自动识别的修复项。

`12-repair-resolution-audit` 是 repair-resume 的闭环检查：没有应用 repair-resume 时为 `not_applicable`；原修复项已从新队列消失时为 `pass`；原来源/类别仍以 block/high/medium 出现时会标记为 `block` 或 `review_required`。

`repair-resume` 借鉴 AI Scientist 的 review/improve 循环和 Agent Laboratory 的人工 checkpoint 思路，但不会直接跳过 gate。它会清理旧产物、把修复队列和来源审计的失败原因注入下一轮 ideation/experiment planning 上下文，再恢复流水线；文献 gate 与执行 gate 仍按原规则等待人工确认。

`repair-resume-backlog` 是只读 triage，不会删除产物、批准 gate、恢复 pipeline 或执行实验。它会把活跃 repair queue 按优先级列出，并区分 `ready_to_apply` 和 `needs_preconditions`：前者已有可用恢复计划，后者还缺文献修复 query/seed、benchmark manifest、allowed command 或 gate 重批标记等恢复前置条件。Web 端只展示枚举化状态、计数和安全命令，不暴露 repair_context、manager queue、绝对路径或内部 action 文本。

当修复队列来自 `01-literature-search-feedback.json` 时，`repair-resume` 会先把其中 owner 为 `agent` / `agent+human` 且带 query 的 `retrieval_repair_tasks` 复制进 `12-repair-resume-plan.json`，同时保留 `next_run_config` 中推荐的 `literature_provider`、sources、`max_papers` 和 `max_search_queries`。其中 `query_execution_repair` 会直接承接 `01-query-execution-audit` 中 no source、no candidate 或 weak hit 的 selected query，避免只给泛化补检索建议。如果 `01-seed-paper-intake.json` 显示 curated seed 角色覆盖不足，`repair-resume` 也会把缺失的 review/benchmark/baseline/recent 角色转成检索修复 query，并合并进下一次 `extra_search_queries`；历史 run 即使没有 `01-seed-paper-intake.json`，也会从 `01-literature-quality`/`01-literature-curated` 提取候选 DOI/URL seed，写入 `12-repair-resume-plan.json` 的推荐 seed，并在应用 repair-resume 建议时合并进下一轮 `seed_papers`。清理旧 `01-literature*` 产物后，下一次文献阶段会采用这些推荐配置做安全升级，并把 agent 检索修复任务作为 bounded rescue search 的额外检索式执行；Web 的“应用检索建议”会把推荐配置、Search feedback Top queries、`01-literature-rescue-plan` 的 evidence-role 补检索式、未闭环补检索 query、seed 角色补检索式，以及从 `01-literature-quality`/`01-literature-curated` 提取的候选 DOI/URL seed 写回左侧表单。候选 seed 会优先补齐缺失的 review/survey、benchmark/dataset、baseline/method 和 recent 角色，然后再按质量分补足数量。CLI 也可用 `--max-search-queries`、重复的 `--extra-search-query`、`--extra-search-queries-file`、`--seed-paper` 或 `--seed-papers-file` 承接这些检索式和种子文献，供新 run、checkpoint resume 或人工修复后重跑使用。人工 seed/source 修复任务仍由人工处理；候选 seed 写入表单后仍需人工核对题名、年份和相关性，且新的 `01-review-gate.md` 仍必须重新批准后才能进入 idea/实验。

当修复队列来自 `03-benchmark-readiness.json`、`04-benchmark-result-schema-audit.json`、`04-benchmark-evidence-audit.json` 或 `03-execution-safety-audit.json` 时，`repair-resume` 会额外生成 `recommended_execution_config`：从旧 `run-config.json`、`03-benchmark-adapters.json`、`03-benchmark-readiness.json` 或 execution safety 审计中继承 `execution_mode`、`allowed_commands`、`execution_repeats`、`timeout_seconds` 和已有 `benchmark_manifest_paths`。如果是 benchmark 修复但旧 run 没有 manifest，建议会切到 `benchmark` 模式并让 preflight/execution safety 明确阻断缺失 manifest；如果 paper-grade benchmark 缺 candidate/baseline/ablation role，则 `12-repair-resume-plan` 会给出带 TODO 的 manifest scaffold，供人工补真实 benchmark URL、dataset、citation、license、命令和 metrics 后再加入配置。Web 的“预览修复”会只读生成 `12-repair-resume-plan`；确认后可点“应用修复建议”把推荐文献配置、补检索式、seed papers、执行模式、白名单、重复次数、超时和 benchmark manifest 回填到左侧表单。这个按钮只更新表单，不会启动 run、批准 review gate 或批准执行 gate；旧 `03-execution-approval.*` 会被清理，local/benchmark 命令仍必须重新人工批准后才会运行。

## Phase 13: Agent Contract, LLM Trace, Run Economics and Scorecard

第十三阶段先做平台阶段契约、LLM 调用覆盖和运行成本/耗时审计，再把一个 run 的关键证据汇总为统一分数卡：

- `13-agent-stage-contract.md` / `13-agent-stage-contract.json`：按开源科研 agent 模式检查 planning、literature grounding、human gate、idea exploration、experiment design、execution evidence、paper review loop、release reproducibility 和 observability/resume 九个阶段契约。
- `13-agent-trajectory.md` / `13-agent-trajectory.json`：按阶段聚合 run-manifest 事件、关键 gate 状态、缺失产物、阻断和人工待办，方便像实验 trajectory 一样复盘 run。
- `13-llm-trace-audit.md` / `13-llm-trace-audit.json`：检查关键阶段是否都有成功 LLM 调用，失败/预算拦截和 AI disclosure 不一致会阻断。
- `13-run-economics-audit.md` / `13-run-economics-audit.json`：按阶段汇总 LLM 调用、估算 token、耗时、预算压力和可选美元成本，用于判断一次 run 的资源消耗是否可解释。
- `13-agent-observability-audit.md` / `13-agent-observability-audit.json`：检查 manifest/state 一致性、artifact inventory、LLM budget pressure、human gate、实验 runtime trace、诊断恢复和 repair queue 可追踪性。
- `13-research-scorecard.md` / `13-research-scorecard.json`：按文献证据、idea 探索、实验/benchmark、论文质量、复现/release、投稿就绪六个维度给出 0-100 分、状态、证据和下一步动作；若 `12-repair-queue` 仍有 block，投稿就绪维度会保持 blocked。

这一步借鉴 MLAgentBench/AIRS-Bench 式可比较评估与 Agent Laboratory 的人工闭环思路。阶段契约用于发现平台流程缺口，分数卡用于定位证据强弱；二者都不是科学结论，也不会替代人工审稿。

## Phase 14: Run Integrity Audit

第十四阶段检查 run 本身是否可信：

- `14-run-integrity-audit.md` / `14-run-integrity-audit.json`：最终检查必需产物、顶层 JSON 可读性、人工 gate 顺序、上游文献/gate 修复是否早于下游 idea/实验/论文产物、manifest 产物 hash、投稿包、LLM ledger 和 `run-config.json` 是否保存 API key。

这一步把“流水线跑完了”和“这个 run 可采信”分开：如果完整性审计为 `block`，说明需要先修复流程或产物问题，再采信后续论文、分数卡或投稿包。

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

## Run Diagnostics

如果流水线失败，系统会生成：

- `run-diagnostics.md`：人工可读的失败类型、阶段、可能原因、建议动作和 traceback。
- `run-diagnostics.json`：结构化诊断，Web API 会把摘要挂到 run record 的 `diagnostic` 字段。

当前会识别常见问题：

- `llm_configuration`：模型名或 API key 未配置。
- `llm_connection`：OpenAI-compatible endpoint 连接失败或超时。
- `llm_budget`：LLM 调用数或累计 prompt 字符数达到预算上限。
- `literature_rate_limit`：Semantic Scholar 等文献源 429 限流。
- `resume_artifact`：审核门恢复所需 JSON/approval 产物缺失或损坏。
- `execution_configuration`：执行模式或命令白名单配置不合法。
- `runtime_error`：其他运行时错误。

Web UI 失败时会优先提示诊断摘要，并可打开“诊断”标签查看完整信息。

## Run Manifest and Provenance

每次 run 都会持续写入：

- `run-manifest.md`：阶段 timeline、每阶段输入/输出文件、关键数量指标和 artifact inventory。
- `run-manifest.json`：结构化运行轨迹，包含每个产物的大小和 SHA256，方便复盘、审计和比较不同 run。
- `run-llm-ledger.md/json`：记录每次 LLM 调用的用途、模型、耗时、输入/输出字符数、SHA256、失败错误和预算拦截；不保存 API key，也不保存完整 prompt/response。
- `13-llm-trace-audit.md/json`：把 ledger 映射回关键科研阶段，确认“有产物”与“模型成功参与”一致。
- `13-run-economics-audit.md/json`：把 ledger 汇总为阶段级 token/耗时/成本估算，帮助比较不同 run 的资源消耗。

该 manifest 会在服务重启后的审核门恢复场景中继续追加事件，而不是重建一个新的 run 轨迹。

## Web UI

启动本地网页版控制台：

```bash
cd /path/to/research-agent
PYTHONPATH=src .venv/bin/python -m research_agent.web_server --host 127.0.0.1 --port 8766
```

如果要启动正式 paper-grade / gold run，推荐使用环境启动脚本。它会设置本地 OpenAI-compatible gateway 默认值，先校验真实 contact email，再用隐藏输入或 600 权限 FIFO 读取 API key，避免 key 出现在 shell history、Web 表单、命令参数或仓库文件中：

```bash
cd /path/to/research-agent
scripts/start_gold_web_env.sh
```

脚本优先使用项目的 `.venv/bin/python`，也可以通过 `RESEARCH_AGENT_PYTHON_BIN` 指定解释器；选中的 Python 低于 3.11 时会在读取任何密钥前退出。如果 `8766` 端口已有同项目的 `research_agent.web_server`，脚本会在读取 API key 之前提示是否停止并替换，包括通过 `.venv/bin/python` 启动的进程；也可以显式使用 `RESEARCH_AGENT_WEB_REPLACE=1 scripts/start_gold_web_env.sh` 自动替换。若端口仍被其他进程占用，脚本会在读取 key 前退出。读取 key 后的 Web 启动前 doctor ping 和 bundle gate 失败时也会直接退出，不会启动一个注定无法完成 gold run 的 Web 服务。

Web 服务默认只监听回环地址，并校验 Host、同源 Origin 和 JSON 写请求。若把 `RESEARCH_AGENT_WEB_HOST` 设置为 `0.0.0.0`、局域网 IP 或其他非回环地址，必须同时设置至少 16 字符的 `RESEARCH_AGENT_WEB_TOKEN`；启动脚本会在交互终端隐藏读取该值，非交互启动则要求预先导出。浏览器访问时使用 HTTP Basic Auth，用户名固定为 `research-agent`，密码为该 token。不要把 token 放入 URL、仓库文件或命令参数。

然后打开：

```text
http://127.0.0.1:8766
```

Web UI 支持提交研究课题、填写人工 brief、选择离线/在线文献模式、选择模拟或本地白名单执行模式、查看阶段进度、浏览历史 runs，并预览论文、分析、ideas、文献、实验结果、实验 runbook 和代码/数据可用性审计产物。进入 `awaiting_review_approval` 后，页面会显示“批准继续”按钮；点击后后台 run 才继续。

人工 brief 可填写研究偏好、人工约束、成功标准、资源限制和已知风险；这些内容会写入 `00-human-brief.md/json` 并进入 `00-research-plan`。CLI 对应参数包括 `--human-note`、`--human-constraint`、`--human-success-criterion`、`--human-resource-limit` 和 `--human-risk`，均可重复传入。

选择 `Benchmark Manifest` 执行模式时，可以先点“校验 Benchmark”预览 manifest 审计结果；该操作只解析和校验 manifest、命令白名单、source files、metrics_path 和 expected_artifacts，不会创建 run、复制 adapter 文件或执行 benchmark 命令。正式进入 local/benchmark 执行前仍需要 `03-execution-approval` 人工批准。

如果服务在 `awaiting_review_approval` 阶段被重启，历史 run 会重新加载为可恢复等待状态。页面会显示“批准并恢复”，点击后系统会复用已有的 `00-research-plan`、`01-literature`、`01-context` 和 `approval.json`，从 idea 生成继续往后跑。若该 run 曾被退回到 `review_revision_requested`，批准恢复时会先按当前表单配置刷新文献、seed intake、context 和 review gate，再继续。系统会保存不含 API key 的 `run-config.json` 用于恢复；如果模型 key 只填在 Web 表单里而没有环境变量，恢复前需要重新填入 API key。

历史 runs 的“对比”按钮会生成跨 run dashboard。排行榜现在会优先读取 `02-experiment-manager.json`、`04-benchmark-result-schema-audit.json`、`10-final-readiness.json`、`10-code-data-availability.json` 和 `13-run-economics-audit.json`，把实验管理策略、benchmark schema/provenance 闭环、最终 gate 状态、修订后分数、LLM 调用数、估算 token、耗时、可选美元成本、预算压力、代码/数据可用性状态和发布元数据人工待办纳入排序；历史列表也会显示检索修复、实验管理、Benchmark schema 和最终 gate 的简短状态。`runs-memory.md/json` 会进一步沉淀实验管理阻断、smoke-first、benchmark schema/provenance 缺口和下一轮候选分支，后续 preflight 和 `00-prior-run-lessons` 会把这些历史信号带回新 run；`runs-library.md/json` 会按课题被 `00-prior-run-library` 自动检索，用于快速定位可复用论文、失败案例、benchmark/baseline 经验或仍需修复的 run。

## OpenAI-Compatible LLM

LLM 只支持 `openai-compatible`。必须提供 Base URL、模型名和 API key；未配置模型时 run 会失败。推荐把 API key 放在环境变量里，CLI 只传非 secret 参数；paper-grade 模式会拒绝 CLI secret 参数，避免正式 gold run 的 key 出现在 shell history 或 process list。Web 开启 Paper-Grade 后会禁用表单密钥输入，“测试模型”会改为检查 Web 服务进程继承的 `OPENAI_BASE_URL`、`OPENAI_MODEL` 和 `OPENAI_API_KEY`。模型列表实时查询失败时，页面只把内置列表显示为“推荐预设”，不会再把它当作接口授权成功：

```bash
export OPENAI_API_KEY=...
PYTHONPATH=src .venv/bin/python -m research_agent run \
  --topic "自动科研 agent 如何减少机器学习实验迭代成本" \
  --llm-provider openai-compatible \
  --llm-base-url https://api.openai.com/v1 \
  --llm-model gpt-4o-mini \
  --llm-max-calls 20 \
  --llm-max-prompt-chars 200000 \
  --literature-provider online \
  --literature-sources semantic_scholar,openalex,arxiv,crossref \
  --max-search-queries 6 \
  --extra-search-query "autonomous research agent benchmark reproducibility" \
  --fulltext-path path/to/local-paper.txt \
  --out runs/ai-online-demo
```

也可以把 Base URL 和模型名一并放在环境变量中，让命令更短：

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=http://127.0.0.1:8317
export OPENAI_MODEL=gpt-5.5
PYTHONPATH=src python3 -m research_agent run \
  --topic "your topic" \
  --llm-provider openai-compatible \
  --out runs/ai-demo
```

AI 会参与 `00-research-plan`、`01-literature` 的检索式/综述、`02-ideas`、`03-experiment-plan`、`06-paper.md`、`07-paper-review` 和 `09-revised-paper` 等阶段。模型调用失败、超时或预算耗尽时，当前 run 会失败并生成 `run-diagnostics.md/json`；系统不会使用离线 LLM 兜底。模型已成功返回但 JSON 结构不合格时，对应阶段仍可使用确定性规则修复或结构化补齐。

可选预算字段：

- `llm.max_calls` / `--llm-max-calls`：本次 run 最多允许多少次真实 LLM 调用，`0` 表示不限制。
- `llm.max_prompt_chars` / `--llm-max-prompt-chars`：本次 run 累计 prompt 字符上限，`0` 表示不限制。
- 超额时会写入 `run-llm-ledger.md/json`，状态为 `budget_exceeded`，并停止当前 run。

## Local Experiment Execution

本地执行是显式启用的：

```toml
[execution]
mode = "local"
timeout_seconds = 600
allowed_commands = ["python3", "pytest"]
```

执行器只允许命令首项在 `allowed_commands` 中的命令，且会把工作目录限制在本次 run 的 `experiments/` 目录中。本地命令会额外拒绝 shell 元字符和逃出 `experiments/` 的路径参数；子进程使用最小环境变量，并把超时记录为 `status = "timeout"` 而不是让流水线卡死。`local` 和 `benchmark` 模式在通过 `03-execution-safety-audit` 后会停在 `awaiting_execution_approval`，需要在 Web 点击“批准执行”或运行：

```bash
PYTHONPATH=src python3 -m research_agent approve-execution runs/<run-id> \
  --notes "已检查实验命令、白名单和安全审计，允许执行"
```

批准后再 resume 或等待后台线程继续，才会真正运行本地/benchmark 命令。

实验计划会携带 `template_profile`，并在 `experiments/experiment-template.json` 记录本次实验模板、命令和指标。内置安全模板会同时包含 candidate、baseline 和 ablation 命令；实验执行前会生成 `03-preregistration.md/json` 锁定分析计划，防止跑完结果后倒推 primary metrics；每次运行还会生成 `04-experiment-runbook.md/json`，用于人工复查命令、随机种子、执行状态和产物哈希。当前内置模板：

- `robotics_motion_planning`：机械臂路径规划，包含 `planning_success_rate`、`planning_time`、`path_length`、`collision_rate`、`trajectory_smoothness`、`minimum_clearance`。
- `bearing_fault_diagnosis`：轴承故障诊断，包含 `accuracy`、`macro_f1`、`cross_domain_accuracy`、`noise_robustness`、`inference_latency`。
- `ai_research_agents` / `generic`：科研 agent 或通用任务，保留引用质量、产物完整度、复现成功率等指标。

这仍然是可复现原型模板，不等同于真实 benchmark；正式研究应把模板中的模拟器替换为领域公开数据集和真实实验脚本。

## Scope

这个项目先解决“端到端可运行和可审计”。真实科研质量还需要继续接入：

- 更深的 RAG 摘要、PDF 正文解析和引用格式导出
- 领域特定实验模板
- 真实 benchmark 数据集
- 统计检验与可视化
- LaTeX 会议模板
- 人类审核 gate 与复现实验
