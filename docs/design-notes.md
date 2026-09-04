# 设计笔记：与同类开源项目的对照

本平台保持零第三方运行时依赖（纯 Python 标准库），但流程设计借鉴了多个成熟开源项目的模式。本文记录借鉴关系与有意的差异，供后续演进时对照。

## 1. LangGraph：checkpoint 与 time-travel 回退

- **LangGraph 的做法**：每个节点执行后持久化状态快照；可以"时间旅行"到任意历史 checkpoint，检查点之前不重执行、之后全部重放。
- **本项目的对应实现**：`workflow_graph.py` 把流程声明为 14 个 `WORKFLOW_NODES`，`run-checkpoint-contract.json` 记录 topic/config 指纹与 revision；`resume_pipeline_from_checkpoint` 按"产物存在即复用、缺失即重生成"恢复；`issue_rollback_preview`/`apply_rollback` 实现两阶段回退（preview token + plan digest + TTL，产物移入 `.research-agent-archives/`，哈希校验失败自动恢复）。
- **有意的差异**：LangGraph 在内存/序列化层保存整个图状态；本项目把"状态"落在人类可读的产物文件上，回退以归档文件而非状态快照为准——牺牲原子性换取每一步的审计可见性。

## 2. CrewAI / AutoGen：按角色配置模型与角色任务

- **CrewAI 的做法**：每个 Agent 声明 role/goal/backstory 与独立的 `llm`；Task 绑定 agent。
- **AutoGen 的做法**：每个 agent 携带自己的 `model_client` 配置，可在同一个对话中混合不同厂商的模型。
- **本项目的对应实现**：`multi_agent_assignment.py` 定义 8 个角色画像（agent_id/name/role/responsibility）；`agent_runtime.py` 的 `AGENT_TASKS` 把 10 个流水线任务（T01-T10）绑定到角色，其中 T10 是为 statistician 增加的独立统计审查任务；`RoleModelRouter` 按优先级路由模型：`task_models[stage]`（按任务） > `roles[id].model`（按角色） > 全局默认；`AgentRoleConfig` 还可为单个角色指定独立 `base_url`（凭据仍只能来自环境变量）。`AgentRoutedLLM` 在每次调用前注入角色 system prompt，账本按 agent/task/model/base_url 记录。
- **有意的差异**：不做自由的多 agent 对话（AutoGen 的 group chat）。角色协作是两层结构化审计：`multi_agent_deliberation` 用确定性规则按角色视角重算既有产物（不发起调用），`agent_verdict` 再让 6 个角色各自拿最小证据视图独立发起一次 LLM 调用并返回强类型 verdict。两层分开保存、互不冒充，最终由 `gate_aggregator` 汇成唯一裁决。这保证了每条审计结论都能追溯到确定性规则或单次可记账的 LLM 调用。

## 3. MCP（Model Context Protocol）：只读工具通道

- **MCP 的做法**：标准 JSON-RPC 协议，stdio 与 Streamable HTTP 两种传输，`tools/list`、`tools/call`。
- **本项目的对应实现**：`tool_runtime.py` 只支持 streamable-http 客户端（官方 `mcp` Python SDK 作为可选依赖 `pip install -e '.[mcp]'`）；`MCPServerConfig` 强制 `read_only`、`allowed_tools` 白名单、默认仅 localhost、auth env 限定 `RESEARCH_AGENT_MCP_*` 命名空间；工具调用循环由 `AgentRoutedLLM.complete_prepared` 驱动（模型输出 `{"__mcp_call__":...}` 约定，最多 `max_tool_rounds` 轮），每次调用写 `run-tool-receipts.json` 审计回执；工具结果以"不可信数据"身份拼回 prompt。
- **有意的差异**：不支持 function calling 原生协议（`OpenAICompatibleLLM` 的 payload 保持最小），也不支持 stdio 本地传输（拉起子进程会扩大攻击面，需要先接入执行安全审计）。选择"文本 JSON 约定 + 白名单 + 回执"是为保持与既有命令白名单同级的安全姿态。

## 4. 其余借鉴点

- **预算与账本**：LLM 预算在真实请求前拦截（`llm_trace.TracedLLM`），账本只记长度/哈希/用途——与 AI-Scientist 系列项目暴露的"成本失控"教训对应，规则固化在 `00-open-source-lessons`。
- **chunk-level citation grounding**：`fulltext_corpus` + `citation_grounding` 的做法与 PaperQA2 一致：引用必须能落到本地全文切块。
- **多源文献与限流诊断**：`literature_sources.py` 同时打 Semantic Scholar/OpenAlex/Crossref/arXiv/PubMed，并记录 source health 与查询执行审计，来源失败只降级、不伪造。
- **非线性的流程控制**：repair-resume（按修复队列清理受影响产物后从 checkpoint 续跑）与 workflow rollback（归档 + 任意节点续跑）互补：前者面向"审计发现问题"，后者面向"人工判断需要换方向"。

## 5. 为什么保持零依赖

除可选的 `mcp` extra 外，运行时只用标准库：LLM 客户端是手写 urllib、Web 服务器是 `ThreadingHTTPServer`、前端无框架无构建。这是有意的约束——科研自动化工具的可信度部分来自"每一行处理你 API key 和数据的代码都可以直接读完"。代价是部分代码更长（如 `llm.py` 的重试/超时/脱敏），在设计上用更强的测试与审计模块补偿。
