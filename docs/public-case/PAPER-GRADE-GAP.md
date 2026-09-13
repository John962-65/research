# T15：公开案例定位与 paper-grade 补齐清单（状态：benchmark-only）

复核版本：v1.1（T15）。真实调用/执行/用户是否发生：真实本地 benchmark 执行
已发生（见 CASE-REPORT.md）；**LLM 相关步骤未发生**。

## 1. 案例定位（如实声明）

`runs/public-iris-case` 当前是 **benchmark-only 案例**：

- 已证明：冻结契约与预注册 → 真实 CPU 执行（candidate/baseline/ablation）
  → 中断恢复 → 证据核验（来源绑定/哈希）→ 统计比较 → 实验后决策
  （契约主指标判据）→ 中性/负结果报告 → 受控故障注入被阻断。
- 未证明（T15 的完整目标）：`06-paper`、`07-paper-review`、
  `08-revision-plan`、`09-revised-paper`、`10-claim-traceability`、
  `10-citation-grounding`、`10-gate-decision`、`11-submission-package`、
  `14-final-handoff`——这些步骤需要真实 LLM 端点，当前状态 **not_verified**。
  不存在"空白签名栏冒充人工批准"：人工批准栏保持待签署。

## 2. 补齐为完整 paper-grade 案例的步骤（需要凭据）

前置：按 `docs/gold-canary-runbook.md` §2 提供环境变量凭据（密钥不入库）。

| 步骤 | 命令/产物 | 依赖 |
|---|---|---|
| 1. gold 预检 | `gold-run-doctor`（benchmark-pack-run-dir 指向本案例） | 凭据 |
| 2. 文献与全文语料 | `fulltext-grounding-run`（离线可先行） | 无 |
| 3. 论文生成 | pipeline `paper_writing`（模型） | 1 |
| 4. 独立评审 | 六角色 deliberation（模型） | 1–3 |
| 5. 修订与复审 | `08/09/10-revised-paper-review`（模型） | 4 |
| 6. 主张追溯 | `10-claim-traceability` + `10-citation-grounding`（规则+模型） | 3 |
| 7. 最终 gate | `10-gate-decision`（全部满足才 publishable） | 4–6 |
| 8. 投稿包 | `11-submission-package`、`14-final-handoff` | 7 |

可先行（无需凭据）的仅第 2 步；其余每一步都依赖真实端点。

## 3. 完成后必须满足的验收（任务书 T15）

- 第三方干净环境可重算主要数值（已具备：`scripts/replay_public_case.sh`）。
- 删除或篡改一条结果/引用 → gate 阻断（结果 provenance 已验证；
  引用篡改由 claim 极性/grounding 规则拦截）。
- 负结果可正常形成报告（已具备：`publishable_negative_or_neutral_result=True`）。
- 人工批准记录含 actor、时间、理由、版本（签署栏待研究者签署，
  见 CASE-REPORT §1；不得由自动化填写）。
