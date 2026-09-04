# Research Agent

[![CI](https://github.com/John962-65/research/actions/workflows/ci.yml/badge.svg)](https://github.com/John962-65/research/actions/workflows/ci.yml)

一个可审计的科研自动化流水线原型：输入一个研究主题，自动完成文献调研、idea 生成、实验计划、实验执行、统计分析、论文草稿、审稿式复核、修订、投稿/归档包生成与下一轮迭代计划。每一步都落盘为带编号的产物文件，全程留痕、默认安全。

第一版的原则是“全流程自动、每步留痕、默认安全”。LLM 只支持 OpenAI-compatible 在线接口，未配置模型会直接失败；可选配置 LLM 调用预算，超额会在真实请求前拦截。文献默认可用离线种子库，实验默认使用模拟执行器。配置 `execution.mode = "local"` 且设置命令白名单后，才会执行本地实验命令。

> 本 README 是总览。各阶段的产物清单、审计语义和配置细节见 [`docs/`](docs) 目录。

## 流程阶段总览（00-15）

| 前缀 | 阶段 | 核心产物 |
| --- | --- | --- |
| 00 | 研究规划 | `00-question.md`、`00-human-brief`、`00-research-plan`、`00-preflight` |
| 01 | 文献与证据门禁 | `01-literature`（检索/重排/质量/滚雪球/覆盖率/补检索/元数据审计）、`01-fulltext-corpus`、`01-context`、`01-review-gate.md`、`01-references.bib/.ris` |
| — | 人工 review gate | `approval.json`（批准前不进入 idea/实验/论文） |
| 02 | 方案探索 | `02-research-gap-map`、`02-agent-team`、`02-ideas`、`02-novelty-audit`、`02-idea-audit`、`02-exploration-map`、`02-experiment-manager` |
| 03 | 实验设计 | `03-experiment-plan`、`03-ablation-plan`、`03-preregistration`、`03-benchmark-plan/-readiness/-adapters`、`03-execution-safety-audit` |
| — | 人工执行门 | `03-execution-approval.json`（仅 local/benchmark 模式） |
| 04 | 实验执行与统计 | `04-results`、`04-statistics`、`04-result-validation`、`04-failure-analysis`、`04-experiment-decision`、`04-hypothesis-outcome` |
| 05 | 结果分析 | `05-analysis` |
| 06 | 论文写作 | `06-paper.md/.tex` |
| 07 | 独立复核 | `07-paper-review`、`07-paper-review-calibration` |
| 08 | 修订计划 | `08-revision-plan` |
| 09 | 修订稿 | `09-revised-paper`、`09-revision-report`、`09-revision-response-audit` |
| 10 | 修订后审计 | `10-revised-paper-review`、`10-claim-traceability`、`10-citation-grounding/-coverage`、`10-claim-consistency`、`10-agent-deliberation`（确定性角色投影）、`10-independent-deliberation`（独立角色 verdict，仅 multi_agent 启用时）、`10-gate-decision`（最终门禁裁决）、`10-release-metadata`、`10-code-data-availability`、`10-submission-check`、`10-final-readiness` |
| 11 | 投稿/归档包 | `11-submission-package.zip` |
| 12 | 迭代与修复 | `12-next-iteration-plan`、`12-repair-queue`、`12-repair-resolution-audit`、`12-repair-resume-plan` |
| 13 | 平台审计 | `13-agent-stage-contract`、`13-agent-trajectory`、`13-llm-trace-audit`、`13-run-economics-audit`、`13-agent-observability-audit`、`13-open-source-compliance`、`13-research-scorecard` |
| 14 | 完整性与交付 | `14-run-integrity-audit`、`14-final-handoff` |
| 15 | Gold 校验 | `15-gold-run-verification` |

每个 run 还有 `run-manifest.json`（事件 + 产物哈希清单）、`run-llm-ledger.json`（LLM 调用账本：只记长度/哈希/用途，不记正文）、`state.json` 与 `workflow-status.json`（阶段状态）。零 LLM 调用且到达 completed 的 run 会在跨 run 汇总与 Web UI 中标注「模板空转」。

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

如果 `01-review-gate.md` 的状态不是 `pass`，批准时必须填写审核意见；CLI 使用 `--notes`，Web UI 使用“审核意见/修复说明”。系统会同时生成 `01-review-feedback` 和 `01-review-constraints`，后者会把人工意见解析为 baseline、literature、metric、reproducibility、scope 或 safety 等结构化约束，并传给后续 idea 和实验计划阶段。

Web UI（可选）。`pip install -e .` 后可直接用 console script：

```bash
research-agent-web --host 127.0.0.1 --port 8765
```

未安装 console script 时用模块入口（注意是 `research_agent.web_server`，不是 `research_agent_web`）：

```bash
PYTHONPATH=src .venv/bin/python -m research_agent.web_server --host 127.0.0.1 --port 8765
```

默认只监听回环地址，此时不需要 token。绑定任何非回环地址都必须先设置至少 16 字符的 `RESEARCH_AGENT_WEB_TOKEN`，且服务自身不提供 TLS——受支持拓扑见 [`docs/platform.md`](docs/platform.md) 的「部署拓扑（DEPLOY-01）」。

## 回退到任意阶段重跑

流程不是单向流水线。任何已到达的节点都可以回退：目标节点及之后的产物会先归档到 `.research-agent-archives/`（带哈希校验、失败自动恢复），然后从该节点的 checkpoint 自动续跑。

```bash
# 列出可回退节点
PYTHONPATH=src python3 -m research_agent rollback runs/<run-id>
# 预览将归档的产物
PYTHONPATH=src python3 -m research_agent rollback runs/<run-id> --target ideation
# 应用回退并自动续跑（回退到文献链之前会重新等待人工 review 审批）
PYTHONPATH=src python3 -m research_agent rollback runs/<run-id> --target ideation --apply --reason "文献证据不足，需要重新检索"
```

Web UI 的 run 详情页有同样的「回退重跑」按钮：选择目标 → 预览归档范围与重新审批提示 → 填写原因 → 确认回退。回退是两阶段提交（preview token 10 分钟有效），已发生的远程 MCP 调用、网络请求和外部 benchmark 副作用不会被本地回退撤销。

## 多智能体：角色、模型路由、skill 与 MCP

流水线的 10 个 LLM 任务（T01-T10）绑定到 8 个固定角色画像（literature_scout、evidence_curator、gap_analyst、method_architect、benchmark_engineer、statistician、skeptical_reviewer、manuscript_editor）。`multi_agent.enabled = true` 时，每次 LLM 调用都会注入角色系统提示（你是谁、职责、当前任务），并在账本中记录 agent/task/model。T10 是 statistician 的独立统计审查任务，审查统计设计、效应量、多重比较与结果边界。

角色审计分两层，彼此独立保存、互不冒充：

- **确定性角色投影**（`10-agent-deliberation`）：用纯规则从既有审计产物重算各角色 verdict，不发起 LLM 调用，`independent_agent_execution` 恒为 `false`，状态只会是 `review_required` 或 `block`。它是第一层安全检查，不能当作多智能体共识。
- **独立执行层**（`10-independent-deliberation`）：6 个角色（evidence_curator、method_architect、benchmark_engineer、statistician、skeptical_reviewer、manuscript_editor）各自只拿到职责范围内的最小证据视图，串行发起一次角色化 LLM 调用并返回强类型 verdict；每条 verdict 绑定 ledger call id、model、revision 与 prompt/response 哈希，无效或调用失败的角色按 `block` 处理。

两层结果连同确定性审计、缺失角色和人工 override 汇入唯一的最终门禁裁决 `10-gate-decision`：任一来源 block 即为 `blocked`，此时不允许生成 publishable 交付；人工 override 必须记录 reviewer、reason、revision 与被覆盖 verdict 的哈希。

模型路由优先级：`multi_agent.task_models[stage]`（按任务/阶段） > `roles[agent_id].model`（按智能体类型） > `[llm].model`（全局默认）。

```toml
[multi_agent]
enabled = true
task_models = { research_planning = "model-a", paper_review_loop = "model-b" }

# 角色是数组（array-of-tables）；agent_id 必须是内置角色之一。
# 角色凭据只能来自环境变量：跨 origin 的 endpoint 必须成对声明
# base_url_env / api_key_env，且两者解析出的 origin 一致，
# 否则 preflight 直接拒绝（全局字面 API Key 不会发给其他域名）。
[[multi_agent.roles]]
agent_id = "gap_analyst"
model = "model-a"
base_url_env = "DEEPSEEK_BASE_URL"   # 例如 https://api.deepseek.com/v1
api_key_env = "DEEPSEEK_API_KEY"

[[multi_agent.roles]]
agent_id = "skeptical_reviewer"
model = "model-b"
skills = ["skeptical-review"]        # 不配置时使用内置默认绑定
mcp_servers = ["local-docs"]

[[multi_agent.mcp_servers]]
server_id = "local-docs"
transport = "streamable-http"
url = "http://127.0.0.1:8000/mcp"
allowed_tools = ["search_docs"]
auth_env = "RESEARCH_AGENT_MCP_LOCAL_DOCS_TOKEN"
enabled = false
```

- **skill**：`skills/<skill_id>/SKILL.md` 全文注入对应角色的 system prompt。内置四个 skill（experiment-design、manuscript-editing、evidence-grounding、skeptical-review），角色未显式配置时按内置默认绑定（如 skeptical_reviewer → skeptical-review、benchmark_engineer → experiment-design）。
- **MCP**：仅支持 streamable-http 传输（`pip install -e '.[mcp]'` 安装依赖），默认仅限 localhost、强制只读、工具白名单非空、auth env 限定 `RESEARCH_AGENT_MCP_*` 命名空间；每次调用写 `run-tool-receipts.json` 审计回执。工具结果以「不可信数据」注入，最多 `max_tool_rounds` 轮。
- 完整字段说明见 `examples/config.toml` 与 `docs/platform.md`。

## 修复恢复与跨 run 记忆

已完成但 `12-repair-queue.json` 仍为 `blocked_repair_required` 或 `needs_repair` 的 run，可以先预览修复恢复计划，确认后 `--apply` 清理受影响产物并从 checkpoint 续跑；来源审计中的 blockers/manual tasks 会汇总为 `repair_context` 注入下一轮 planning prompt。

```bash
PYTHONPATH=src python3 -m research_agent repair-resume runs/<run-id>            # 预览
PYTHONPATH=src python3 -m research_agent repair-resume runs/<run-id> --apply --llm-model "$OPENAI_MODEL"
```

跨 run 汇总写在 `runs/` 根目录：`runs-summary`（排行榜与状态分布）、`runs-memory`（失败模式与下一轮推荐配置，回灌给 `00-prior-run-lessons`）、`runs-library`（历史论文成果检索库）、`runs-platform-audit`（平台能力缺口）。CLI 示例：

```bash
PYTHONPATH=src python3 -m research_agent library --runs-dir runs --query "robot manipulator OMPL benchmark"
```

## 安全模型

- **两个人工 gate**：文献证据门（`approval.json`）与 local/benchmark 执行门（`03-execution-approval.json`），都有主题绑定哈希与实质性意见校验；退回意见会解析为结构化约束注入后续阶段。
- **受限本地执行**（SANDBOX-01：这不是容器级 sandbox）：`execution.allowed_commands` 二进制白名单（默认 `python3`/`pytest`）+ `command_safety` 禁止解释器动态代码执行（`python -c`、`node --eval` 等）+ 子进程环境变量剥离密钥 + 超时与输出上限。不可信代码的正式强隔离需要容器或独立 worker，当前版本不宣称具备。模拟执行器结果恒标记 `status=simulated`，下游审计强制 `smoke_only/review_required` 降级，不因模拟结果宣称科学结论。
- **密钥安全**：run-config 快照脱敏；LLM 账本只记长度/哈希；MCP 凭据限定专用 env 命名空间；env API key 只发给与其声明来源一致的 base URL。
- **Web 安全**：默认仅回环监听、Host/Origin 校验、body/response 大小上限、回退等危险操作需要预览 token 与原因。

## 外部集成

- `01-references.bib` / `01-references.ris` 可导入 Zotero、EndNote 或其他引用管理器。
- release metadata（`10-release-metadata.json`）承接 GitHub 代码仓库、Zenodo 代码/数据归档 DOI、OSF 补充材料与环境快照 URL，作为投稿包的归档证据。
- 文献在线检索支持 Semantic Scholar、OpenAlex、Crossref、arXiv、PubMed（`literature.provider = "online"` 或 `"auto"`）。
- 通过 MCP（streamable-http）可接入本地/远程只读工具服务。

## Gold Run 安全启动

对当前仓库内置的 UCI Iris gold 路径，可以用两种安全入口注入本地网关环境。Web 路径适合人工点选和观察；它会先检查端口、本地 LLM gateway socket、真实 contact email，并运行只读 `gold-defaults-smoke`，最后才用隐藏输入读取 `OPENAI_API_KEY`，或从 `RESEARCH_AGENT_OPENAI_API_KEY_FIFO` 指向的 600 权限 FIFO 读取一次 key；读取 key 后还会先执行 `gold-run-doctor --ping-llm --no-write` 和 `gold-launch-bundle --no-write`，确认 key/gate 可用后才启动 Web 服务：

```bash
RESEARCH_AGENT_WEB_REPLACE=1 scripts/start_gold_web_env.sh
```

默认路径仍是隐藏输入读取 API key；`RESEARCH_AGENT_OPENAI_API_KEY_FIFO` 只用于非交互自动化或需要由另一个安全终端传递 key 的场景。

纯 CLI 路径同样会先检查本地 LLM gateway socket，先校验真实 contact email（`RESEARCH_AGENT_CONTACT_EMAIL`），随后先运行只读 `gold-defaults-smoke`，最后才用隐藏输入或 `RESEARCH_AGENT_OPENAI_API_KEY_FIFO` 读取 `OPENAI_API_KEY`；contact email 缺失、使用 `example.org/example.com` 等占位域名、gateway 不可达，或默认论文级输入 blocked 时，脚本都会在读取 API key 之前退出：

```bash
scripts/run_gold_cli_env.sh
```

非交互自动化测试时不要把 key 写入命令行，用一次性 FIFO：

```bash
fifo_dir="$(mktemp -d /tmp/research-agent-key.XXXXXX)"
fifo="$fifo_dir/openai_key.fifo"
mkfifo -m 600 "$fifo"
RESEARCH_AGENT_OPENAI_API_KEY_FIFO="$fifo" RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh &
read -rsp "OPENAI_API_KEY: " k; printf '\n'; printf '%s\n' "$k" > "$fifo"; unset k
rm -f "$fifo"; rmdir "$fifo_dir"
```

## 测试与 CI

本地跑全量测试必须走隔离入口。宿主机可能自动加载 pytest 插件（例如 ROS 测试工具链）并因缺失依赖在收集阶段就中断——那时还没进入项目测试，报错看起来却像业务失败：

```bash
bash scripts/run_tests.sh      # PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 + 优先使用项目 venv
python scripts/check_docs.py   # Markdown 相对链接检查
```

gold 路径的测试会断言 `runs/uci-iris-expanded-baseline-pack-run` 与 `runs/uci-iris-fulltext-grounding` 两个目录，而它们属于 gitignore 的本地产物——**全新克隆里不存在，相关测试会失败，尽管代码没有问题**。先跑一次离线且确定性的生成步骤（只消费仓库内的 UCI Iris benchmark pack 与冻结全文）：

```bash
bash scripts/prepare_gold_support_runs.sh
```

`.github/workflows/ci.yml` 在每次 push 与 PR 上跑三个 job：

| Job | 内容 |
| --- | --- |
| `tests` | Python 3.11 / 3.12 矩阵，只装 dev extra（对应文档化的开发流程）；先跑 `prepare_gold_support_runs.sh` 生成 gold 测试所需的两个 support run，再跑全量测试与文档链接检查。`RESEARCH_AGENT_PYTHON_BIN` 固定解释器，避免脚本回退到与安装包不同的 `python3` |
| `tests-with-mcp` | 装上可选 mcp extra，同样先生成 support run 再跑全量，让 streamable-http 客户端路径跑在真实 SDK 上，而不是只覆盖 `tool_runtime` 的 ImportError 回退 |
| `zero-runtime-deps` | 不装任何 extra，逐个导入 `src/research_agent` 下 143 个模块。零第三方运行时依赖是本项目的可信度论据之一（见 [`docs/design-notes.md`](docs/design-notes.md) §5），这个 job 防止后续某次 import 悄悄破坏它 |

当前基线：Python 3.12 + dev extra 为 1352 passed, 1 skipped, 72 subtests（UA-01 合入后实测）；Python 3.11 + dev 与 3.12 + dev,mcp 最近一次实测为 1345 passed（BUDGET-01 之前）。三种配置由 CI 矩阵在每次 push 上覆盖，以 CI 结果为准。

## 文档索引

- [`docs/phases/00-planning.md`](docs/phases/00-planning.md) — 研究规划与领域画像
- [`docs/phases/01-literature.md`](docs/phases/01-literature.md) — 文献检索、证据门禁与审核门
- [`docs/phases/02-03-ideas-and-plans.md`](docs/phases/02-03-ideas-and-plans.md) — idea 生成与实验计划
- [`docs/phases/04-experiments.md`](docs/phases/04-experiments.md) — 重复实验与统计审计
- [`docs/phases/05-07-analysis-and-review.md`](docs/phases/05-07-analysis-and-review.md) — 分析、论文与独立复核
- [`docs/phases/08-09-revision.md`](docs/phases/08-09-revision.md) — 修订计划与修订稿
- [`docs/phases/10-audits.md`](docs/phases/10-audits.md) — 修订后审计与最终就绪
- [`docs/phases/11-package.md`](docs/phases/11-package.md) — 投稿与归档包
- [`docs/phases/12-iteration.md`](docs/phases/12-iteration.md) — 下一轮迭代与修复队列
- [`docs/phases/13-14-platform-audits.md`](docs/phases/13-14-platform-audits.md) — 平台审计与完整性交付
- [`docs/platform.md`](docs/platform.md) — 诊断、溯源、Web UI、LLM 与本地执行
- [`docs/design-notes.md`](docs/design-notes.md) — 设计借鉴与开源项目对照
- [`docs/improvement-plan.md`](docs/improvement-plan.md) — 分级 gap register（P0/P1/P2，带 file:line 证据）、阶段 A-H 实施进度，以及 §0.2 明确列出的**尚未闭合项**

## Scope

本平台是科研自动化原型：它保证流程可审计、证据可溯源、边界诚实呈现，但不替代研究者的科学判断；所有最终 gate 都保留人工确认，论文级产出默认标注为需要人工润色与投稿前检查。

## 许可证

Apache License 2.0，全文见 [`LICENSE`](LICENSE)。

例外：`benchmarks/uci-iris-classification/` 下的冻结数据（`data/iris.data`）与数据集描述（`fulltext/iris.names.txt`）来自 UCI Machine Learning Repository 的 Iris 数据集（官方页 https://archive.ics.uci.edu/dataset/53/iris ，DOI `10.24432/C56C76`），按 UCI 报告的 **CC BY 4.0** 许可保留，版权归原数据集作者所有，不在本项目许可证范围内。其余文件均为 Apache-2.0。
