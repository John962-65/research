<!-- 拆分自原 README.md；总览见根 README -->

# 阶段 01：在线文献检索与审核门

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

仓库内提供了一个结构性预检示例。它**按设计以非 0 退出码结束**（下面说明哪两项必然 fail），用途是展示论文级门槛链路如何逐项判定，不是一条应当通过的命令：

```bash
PYTHONPATH=src python3 -m research_agent preflight \
  --topic "机械臂路径规划" \
  --config examples/paper-grade-config.toml \
  --no-llm-ping
```

这个示例会启用 online 文献、多源配置、3 条 DOI/URL seed，以及 `examples/rrt-2d-benchmark/manifest-candidate.json`、`manifest-baseline.json`、`manifest-ablation.json` 三角色 benchmark manifest。它用于证明 agent 的论文级门槛链路可预检、可审计、可修复。有两项**无条件** `fail`：

- `paper_grade_benchmark_manifests`：RRT 2D benchmark 是仓库内可复现 fixture（`benchmark_kind=fixture`、`procedural://` dataset_url），不是正式投稿的领域公开基准，检查会提示把 fixture 替换成公开外部 benchmark manifest。
- `llm_api_key`：示例配置故意不声明任何凭据，且 `base_url` 指向 discard 端口（`127.0.0.1:9`）。SEC-01 下环境变量里的 key 只在 effective endpoint 与可信来源同源时才释放，所以即使设置了 `OPENAI_API_KEY` 也不会被解析出来——这是预期行为，不是配置错误。

另有一项取决于本机环境：未设置 `RESEARCH_AGENT_CONTACT_EMAIL` 时 `contact_email` 也会 `fail`。

正式 paper run 应把 seed、manifest、release URL 和 LLM 配置替换成真实课题资产，LLM 段改用成对的 `base_url_env` / `api_key_env` 形式，参照 `examples/uci-iris-paper-grade-config.toml`。
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
