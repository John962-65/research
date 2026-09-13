# 决策契约（decision-contract）v1.0

冻结日期：2026-09-13（任务书 T00）。本文件冻结四类决策状态的业务语义、
取值、与现有字段的映射、允许操作与人工覆盖边界。实现必须按本契约执行；
修改本契约必须升 schema_version 并记录原因。

来源任务书：`research_modification_taskbook_v1.md` §3.1/§3.2/§3.3。
基线核对结论见 `docs/baseline-audit.md`。

## 1. 四类决策状态

四类状态分别保存、互不推导。任何界面与报告都必须能同时呈现四类状态；
只显示其中一个（如只显示"完成"）视为缺陷。

| 维度 | 冻结取值 | 回答的问题 |
|---|---|---|
| execution_status | pending / running / completed / failed / cancelled / timed_out / blocked / simulated | 程序有没有正确执行结束？ |
| evidence_status | verified / incomplete / invalid / simulated / unknown | 产物来源与内容是否足够可信？ |
| research_outcome | supported / not_supported / inconclusive / not_assessed | 预先提出的假设是否被支持？ |
| next_action | proceed / request_material / repair / rerun / stop / human_review | 接下来允许做什么？ |

`blocked` 表示因安全/配置/预算原因未能启动或中途终止执行；`simulated`
表示由模拟器生成、从未真实执行。二者都不算 completed。

### 1.1 execution_status 映射（现有 → 冻结）

来源：`04-results.json` 中 `ExperimentResult.status`
（`experiments.py` 实际写入值：passed / failed / timeout / blocked / simulated）。

| 现有值 | execution_status | 可作为结论证据 |
|---|---|---|
| passed | completed | 待 evidence_status=verified |
| failed | failed | 否（保留为真实执行尝试记录） |
| timeout | timed_out | 否（同上） |
| blocked | blocked | 否（未能执行） |
| simulated | simulated | 否 |
| （缺失/未知值） | unknown 语义，按 blocked+incomplete 处理 | 否 |

### 1.2 evidence_status 语义（T01 实现）

evidence_status 按"LLM 证据"与"实验证据"两个独立维度分别给出；
一个维度的状态不得推断另一个维度（有真实模型调用≠有真实实验；
有真实实验也不要求报告必须由模型生成）。

- verified：来源可核验、内容通过结构与数值校验、可定位到产物/记录。
- incomplete：缺少必需部分（如指标缺失、记录数不足、来源绑定缺失）。
- invalid：存在但校验失败（NaN/Inf、状态不在允许集、摘要不匹配）。
- simulated：由模拟器/模板/占位生成。
- unknown：旧结构或无法判定；展示补充动作，不得默认通过。

兼容映射：旧 `EvidenceIntegrity.status` 中 `real_evidence` 仅表示
"本 run 存在成功的真实 LLM 调用且存在通过状态白名单的实验结果"，
不表示任何具体数字、指标或论文主张已被核验；`partial_real_evidence` /
`no_real_evidence` 按维度拆分后废弃。T01 起 `04-evidence-integrity.json`
schema_version=2，读取 v1 文件时按 unknown/incomplete 处理并给出迁移提示。

### 1.3 research_outcome 映射

来源：`04-hypothesis-outcome.json` 的 `outcome`（七值）。冻结四值映射如下，
原七值保留在 `outcome_detail` 字段中，论文措辞分级仍按原值与 claim_boundaries。

| 现有 outcome | research_outcome | 说明 |
|---|---|---|
| supported | supported | 限定范围内支持 |
| partially_supported | inconclusive | 整体假设未被完全支持；不得写成 supported |
| refuted_or_negative | not_supported | 准确的负结果 |
| inconclusive | inconclusive | 证据不足以判断 |
| smoke_only | not_assessed | 证据等级不足以评估假设 |
| untested | not_assessed | 计划比较未执行 |
| blocked_unverified | not_assessed | 执行/证据未通过，不得评估 |

特别约定：not_supported 允许形成准确的负结果报告，不自动触发无限改写
或搜索正结果；不支持≠失败。

### 1.4 next_action 映射

来源：`04-experiment-decision.json` 的 `decision`（五值）。

| 现有 decision | next_action | 说明 |
|---|---|---|
| proceed_to_paper | proceed | 进入保守写作与评审 |
| pivot_or_refine | proceed（附 stop_after_report=true） | 负结果报告完成后终止本轮，不自动开新实验轮 |
| refine_experiment | request_material | 列出缺口（重复数/指标/任务规模），人工确认后可 rerun |
| benchmark_upgrade | request_material | 需要真实 benchmark 环境/数据，属人工材料 |
| repair_before_writing | repair | 进入修复分支，修复后重跑验证 |
| （新增）证据不足且需人工 | human_review | 无法自动判定时 |
| （新增）预算/轮次耗尽 | stop | 保留已有证据并终止 |

工作流必须依据 next_action 路由（T07）；`revision_required` 不得再无条件
为真（当前 `pipeline.py:3288-3290` 硬编码，T07 修正）。

## 2. 允许操作矩阵（冻结）

| 当前组合 | 允许的动作 |
|---|---|
| completed + verified + supported | proceed（写作/评审/报告） |
| completed + verified + not_supported | proceed（负结果报告）→ stop_after_report |
| completed + verified + inconclusive | proceed（保守表述）或 request_material |
| completed + incomplete/invalid | request_material 或 repair（不得 proceed） |
| completed + simulated | request_material（升级真实执行） |
| failed/timed_out/blocked（任意 evidence） | repair / rerun / stop（不得 proceed） |
| 任意状态 + next_action=stop | 仅允许导出报告与归档 |

禁止组合（必须阻断）：任何 execution_status 非 completed 的结果进入
research_outcome=supported；simulated 证据支撑正式科学主张；
next_action=stop 后继续自动实验轮。

## 3. 人工覆盖边界（冻结，T02 实现）

覆盖只能把"可人工接受的已知风险"降级，不能改变事实状态。

### 3.1 可覆盖原因码（override_reason_code 允许值）

| 码 | 含义 |
|---|---|
| scope_limitation | 阻断源于范围限制，人工接受在此范围外使用 |
| advisory_only | 仅警告级问题，人工确认不构成阻断 |
| documented_exception | 有书面记录的例外，绑定具体材料 |
| known_deferral | 已知延后项，明确后续补齐计划 |
| resource_constraint | 资源限制导致的降级，人工接受 |

### 3.2 不可覆盖原因码（出现即拒绝覆盖）

| 码 | 含义 |
|---|---|
| corrupted_input | 参与决策的输入损坏（JSON 解析失败、哈希不匹配） |
| unverifiable_source | 来源无法核验（无 artifact 绑定、来源哈希缺失） |
| invalid_approval | 既有审批失效/被伪造/摘要不匹配 |
| missing_required_evidence | 必需证据缺失（如必需角色 verdict、必需指标） |
| contract_violation | 违反冻结契约（如结果出来后改主指标且未建新版本） |

### 3.3 覆盖字段要求（在现有 gate_aggregator 校验之上新增）

- `approved` 必须布尔真、`revision` 必须整型且等于当前 revision、
  `verdict_sha256` 必须 HMAC 匹配（现有校验保留）。
- 新增：`reason_code` ∈ §3.1 词表；`scope`（覆盖影响的产物/阶段清单）；
  `approval_object`（被覆盖对象，如 "10-gate-decision:blocking_sources:deterministic:citation_grounding"）。
- 覆盖后的决定必须同时保留：原机器决定（status/blocking_sources）、
  覆盖者、理由、原因码、所绑定证据摘要。批准不能消除原始阻断记录，
  不能把缺失数据改成已验证证据。
- §3.2 码出现时覆盖不生效，提示补齐材料后重新检查。

## 4. 证据快照约定（冻结，T02 实现）

- 评审输入快照（review-input snapshot）：一次判断实际使用的输入清单——
  文件标识（项目相对路径）、内容 SHA-256、角色、规则/提示词版本；
  不含评审输出。
- 最终裁决快照（final decision snapshot）：引用评审输入快照摘要 +
  已生成的评审输出（deliberation、verdicts）；人工覆盖绑定本快照，
  不把覆盖文件自身纳入它所签认的摘要。
- JSON 规范化：`sort_keys=True, ensure_ascii=False, separators=(",",":")`，
  `allow_nan=False`；含 NaN/Inf 的输入直接判 invalid，不得静默序列化。
- 哈希只用于内容一致性检测，不防篡改；路径一律项目相对路径。

## 5. 版本登记

| 结构 | 版本 | 变更 |
|---|---|---|
| 本契约 | 1.0 | T00 冻结 |
| 04-evidence-integrity.json | 2（T01 起） | 四计数分离、状态白名单、维度拆分；v1 兼容读为 unknown/incomplete |
| 10-gate-decision.json inputs | 2（T02 起） | 增加评审输入快照 id 与内容绑定 |
| 03-preregistration.json | 2（T05 起） | 版本化，不再就地覆盖 |
| 03-idea-experiment-contract | 2（T05 起） | 增加机器可读契约结构（八字段组） |

旧 Run 规则：缺少新字段的记录按 unknown/incomplete 处理并给出迁移建议，
不自动补成"已批准/已验证"；不静默假定旧 Run 具备新能力（如独立评审）。

## 6. publishable 语义声明

`publishable`（gate decision status）仅表示"通过本系统约定的发布前检查
（门禁/评审/覆盖流程）"，不表示论文达到期刊发表标准或必然被录用。
界面与导出报告必须使用具体中文说明，不得使用"可发表"作为唯一表述。
