# T14：真实 multi-agent gold canary 操作手册（状态：not_verified）

复核版本：v1.1（T14）。本文件是**离线准备**产物：当前环境没有已授权的
OpenAI-compatible 端点与凭据，真实 canary 尚未执行。真实调用是否发生：**否**。
凭据到位后按本手册执行，完成后以实际产物更新本文件状态。

## 1. 目标与验收（任务书 T14）

用已授权、预算受限的端点运行一次真实多智能体 canary，证明独立评审不是
测试夹具或确定性投影。验收要点：

- 六个角色（evidence_curator、method_architect、benchmark_engineer、
  statistician、skeptical_reviewer、manuscript_editor）各产出真实 verdict；
- 每条 verdict 有真实 `call_id`、角色、输入摘要、规则版本和可定位的证据引用；
- 任一调用失败、结构无效或证据不足 → 最终 gate 保持 **blocked**；
- 只有全部条件满足才可写 `publishable`；
- 无论通过或阻断，发布脱敏证据摘要（账本计数、角色 verdict 表、
  gate 决定、费用），不能只报告"调用成功"。

## 2. 前置条件（安全约定）

- `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`、
  `RESEARCH_AGENT_CONTACT_EMAIL` **只通过环境变量或受控 FIFO** 提供；
  不得写入 TOML、命令行、网页表单或日志（`secrets_via_environment` 检查）。
- 预算上限：`--llm-max-calls` 与 `--llm-max-prompt-chars` 显式设定；
  run-economics 审计核对实际费用。

## 3. 执行步骤（凭据到位后）

```bash
# 1) 离线预检（无需凭据，应复现 docs/public-case/t14-canary-offline-doctor.txt）
PYTHONPATH=src python3 -m research_agent.cli gold-run-doctor \
  --topic "multi-agent gold canary" \
  --config examples/uci-iris-paper-grade-config.toml \
  --benchmark-pack-run-dir runs/public-iris-case --gold-defaults

# 2) 配置真实端点后：preflight 必须通过（含 llm_routes 与连通性）
export OPENAI_BASE_URL=... OPENAI_MODEL=... OPENAI_API_KEY=...
export RESEARCH_AGENT_CONTACT_EMAIL=...
PYTHONPATH=src python3 -m research_agent.cli gold-run-launch-bundle ...   # 按 doctor 输出补参

# 3) 启动 gold run（严格模式；人工 gate 用 approve/approve-execution）
PYTHONPATH=src python3 -m research_agent.cli gold-run-launch ...

# 4) 完成后核验（本手册 §4 的判定清单）
PYTHONPATH=src python3 -m research_agent.cli gold-run-verify ...
```

## 4. 判定清单（完成后逐项勾选，引用产物字段）

| 检查 | 产物/字段 | 通过条件 |
|---|---|---|
| 六角色独立调用 | `run-llm-ledger.json` | 每角色 ≥1 条 status=success、stage=paper_deliberation、agent_id 匹配 |
| verdict 绑定 | `10-independent-deliberation.json` | 每条 verdict 有非空 call_id/response_sha256/rule_version/review_input_sha256；evidence_refs 可定位 |
| 账本交叉核验 | `10-gate-decision.json` | 无 `verdict:*:unverified_call` 阻断 |
| 失败即阻断 | 同上 | 任一 invalid/失败角色 → status=blocked 且保留原始响应 |
| 发布检查语义 | `10-gate-decision.md` | publishable 附"非发表保证"说明 |
| 费用与披露 | `13-run-economics-audit.json`、`13-ai-disclosure.json` | token 用量与费用来自 provider；披露完整 |
| 脱敏证据摘要 | `docs/public-case/` | 无任何密钥/联系人原文；含账本计数、verdict 表、gate 决定 |

## 5. 当前离线证据（2026-09-13）

`docs/public-case/t14-canary-offline-doctor.txt`：`gold-run-doctor --gold-defaults`
在无凭据环境下的输出——Launch Readiness=**blocked**（doctor_ready/preflight_pass
阻断，原因即无可用端点），secret policy=env_only 通过，benchmark/文献/发布元数据
检查通过。该输出证明预检链路本身工作正常，但不构成 T14 的完成证据。

**结论：T14 = not_verified。** 需要的条件：已授权端点、API 凭据（环境变量）、
真实联系邮箱、预算审批。
