<!-- 拆分自原 README.md；总览见根 README -->

# 平台能力：诊断、溯源、Web UI 与执行

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

## 部署拓扑（DEPLOY-01）

Web 服务自身**不提供 TLS**。默认拓扑是仅回环监听（`127.0.0.1`）+ SSH 隧道访问；
如果必须远程访问，必须把服务置于 TLS reverse proxy（nginx/Caddy 等）之后，
由代理终结 TLS、校验来源并转发，且仍不应向不可信用户开放——当前版本的授权
模型（单用户 Basic Auth 可选、无会话隔离）只适合单机、可信用户场景。

SSE 活动流：`GET /api/runs/{id}/activity?cursor=N` 以 `text/event-stream`
返回 `run-node-events.json` 中 cursor 之后的事件（`id` 为序号、`event: node`、
`data` 含 node_id/type/revision），随后发送 `event: done` 并关闭。客户端可以
携带上次收到的最大 id 作为 cursor 重新请求，实现不丢不重的活动增量；前端
当前仍使用低频摘要轮询 + ETag 条件请求作为降级路径（WEB-03）。
