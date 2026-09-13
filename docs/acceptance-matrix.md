# 集中验收矩阵（acceptance-matrix）v1.0

冻结日期：2026-09-13（任务书 T00）。编号稳定：A01–A22 与任务书 §6 一一对应，
实现任务必须在"测试载体"列登记实际测试（文件::用例），验收时逐项核对
"必须观察到的行为"，不允许只断言生成文件或函数无异常。

状态标记：`planned`（未实现）→ `tested`（已登记测试且通过）→ `verified`
（阶段出口复核通过）。

| 编号 | 输入变化或故障 | 必须观察到的行为 | 所属任务 | 测试载体 | 状态 |
|---|---|---|---|---|---|
| A01 | 模型调用全失败（total>0，success=0） | 不计为成功模型产物 | T01/T04 | tests/test_evidence_integrity.py::test_all_failed_llm_calls_are_not_real_evidence | verified |
| A02 | 只有 failed/cancelled/timed_out 结果 | 无可用于主张的已验证实验结果 | T01 | tests/test_evidence_integrity.py::test_failed_only_results_are_attempts_not_verified_results | verified |
| A03 | 成功标签但无指标/NaN/Inf/来源缺失 | incomplete 或 invalid，给出原因 | T01 | tests/test_evidence_integrity.py::test_result_without_finite_metrics_is_not_verified | verified |
| A04 | 人工报告 + 完整真实实验 | 来源分开显示，不因无模型调用而判模拟 | T01 | tests/test_evidence_integrity.py::test_manual_report_with_real_experiment_is_not_simulated | verified |
| A05 | 审计状态不变，证据正文变 | 最终摘要变化，旧批准失效 | T02 | tests/test_gate_aggregator.py::test_override_rejects_invalid_semantics_and_changed_evidence | verified |
| A06 | 稿件变化后恢复 | 相关评审重新执行（不按 revision 复用旧 deliberation） | T02 | tests/test_gate_aggregator.py::test_stale_deliberation_is_rerun_on_resume + tests/test_evidence_snapshot.py::test_pipeline_reuse_gate_honors_snapshot | verified |
| A07 | 无效或旧人工覆盖（缺字段/"true"/旧摘要） | 拒绝覆盖，保留原决定 | T02 | tests/test_gate_aggregator.py::test_human_override_requires_full_provenance、::test_override_rejects_invalid_semantics_and_changed_evidence、::test_non_overridable_reasons_reject_override | verified |
| A08 | 校验与提交之间材料变动 | 不提交基于旧输入的决定 | T02 | tests/test_evidence_snapshot.py::test_build_digest_and_verify_roundtrip + tests/test_gate_aggregator.py::test_pipeline_rechecks_override_file_against_current_evidence | verified |
| A09 | 伪造/失败 call_id 或无引用 pass | 不计作有效独立评审票 | T03 | tests/test_gate_aggregator.py::test_verdict_must_match_ledger_records、::test_minimal_verdict_without_refs_or_summary_rejected、::test_independent_verdicts_are_bound_to_real_calls | verified |
| A10 | 明确启用模板降级 | 保留失败和来源，必需评审仍待完成 | T04 | tests/test_ai_integration.py::ExplicitTemplateFallbackTest（4 用例）+ 既有 test_llm_call_failures_are_not_replaced_by_rule_fallbacks 恢复通过 | verified |
| A11 | 契约完整、idea 未重复执行细节 | 不因文案关键词缺失误拦 | T05 | tests/test_idea_experiment_contract.py::test_complete_contract_passes_without_keyword_echo、::test_execution_contract_has_eight_field_groups | verified |
| A12 | 结果出来后改指标或划分 | 新版本/新分析身份，旧批准不沿用 | T05 | tests/test_idea_experiment_contract.py::test_contract_history_versions_after_results + tests/test_preregistration.py::test_posthoc_metric_change_creates_new_version + tests/test_result_validation.py::test_posthoc_contract_change_blocks_with_binding_mismatch | verified |
| A13 | 即刻崩溃或任务重启 | 及时报错，不重复启动活任务 | T06 | tests/test_experiment_attempts.py（ProcessMatchTest 3 用例 + RunExperimentsResumeGuardTest 3 用例，含 PID 复用与中断保留） | verified |
| A14 | 同 Run 线程/进程竞争 | 互斥成立，同线程嵌套仍正常 | T06 | tests/test_run_lease.py（既有回归，4 用例保留） | verified |
| A15 | 正确完成但假设不成立 | 允许准确负结果报告，停止无意义循环 | T07 | tests/test_experiment_decision.py::test_negative_result_maps_to_not_supported_with_stop_after_report、::test_blocked_validation_maps_to_repair_and_not_assessed、::test_simulated_mode_maps_to_simulated_evidence | verified |
| A16 | 超出总预算/最大轮次 | 停止并保留已有证据 | T07 | tests/test_run_budget.py（3 用例，含恢复不绕过） | verified |
| A17 | 引用否定方向/数字/条件相反 | 不得自动宣称已支持 | T08 | tests/test_claim_evidence_polarity.py（6 用例）+ tests/test_claim_traceability.py::test_contradicted_direction_blocks_claim_with_claim_id | verified |
| A18 | 正确主张且证据完整 | 可通过并定位证据 | T08 | tests/test_claim_traceability.py::test_supported_claim_with_complete_evidence_passes + citation_grounding evidence_locator（chunk/字符跨度/页码） | verified |
| A19 | 页面提交旧版本批准 | 后端拒绝，提示材料变化 | T09 | tests/test_web_decision_state.py::StaleApprovalRejectionTest::test_stale_binding_approval_is_rejected_with_material_change_message | verified |
| A20 | 正常真实案例 | 可重算关键结果并解释最终决策 | T10 | runs/public-iris-case（CASE-REPORT.md）+ scripts/replay_public_case.sh 实测：grader 复算 accuracy=0.966667 与案例一致；故障注入副本被 schema 审计阻断（status=block，exit 2）；基线归档 15 条，干净重放按实际事件为 interrupted=1、passed=9、总数=10 | verified |
| A21 | 无试用数据 | 保持 not_measured，不生成效率比例 | T11 | tests/test_review_evaluation.py（16 子测试通过；docs/review-evaluation.md 维持 not_measured 声明） | verified |
| A22 | 同输入走 CLI/Web/恢复 | 决策、原因、证据版本一致 | T12 | 三入口共享同一决策实现（experiment_decision/gate_aggregator/evidence_snapshot 由 pipeline 单点调用，Web 仅做输入输出）；tests/test_web_resume.py 恢复等价性 + examples/review-evaluation-cases.json 直连真实决策函数 | verified |

| A23 | 三条阻断同时存在，人工只批准第一条 | 其余阻断（含缺角色/不可核验）继续阻止放行 | 复审1 | tests/test_gate_aggregator.py::test_partial_override_only_dissolves_approved_blockers | verified |
| A24 | 修改角色证据文件（如 04-statistics）后恢复 | 快照摘要变化，独立评审重跑（调用次数>0） | 复审2 | tests/test_gate_aggregator.py::test_statistics_change_invalidates_deliberation_on_resume + ::test_verdict_must_match_ledger_records（版本/响应/输入过期核验） | verified |
| A25 | 导入声明已执行但无产物文件 | 实验证据 incomplete（声明不等于核验）；人工报告+已核验实验 → 来源说明而非演示横幅 | 复审3 | tests/test_import_existing.py::test_imported_results_without_artifacts_are_incomplete + tests/test_evidence_integrity.py::test_manual_report_with_real_experiment_is_not_simulated | verified |
| A26 | 改契约内容保留旧 digest 字段；主降次升 | 摘要重算不一致 → block；主指标决定结论（不出现 supported+pivot 并存） | 复审4 | tests/test_result_validation.py::test_tampered_contract_digest_is_blocked_even_if_field_kept + tests/test_experiment_decision.py::test_primary_metric_governs_when_secondary_improves | verified |
| A27 | 目标数值缺失/无方向证据/同句正反混合 | 数值冲突判矛盾；无方向证据 → 待核验；按指标归因 → 不误拦 | 复审5 | tests/test_claim_evidence_polarity.py::ReviewerRegressionTest | verified |
| A28 | 干净检出重放；预算中途异常；进程脚本不同 | 重放断言中断生效+期望数值+具体阻断原因；预算启动前预留；argv 全长比较 | 复审6–8 | scripts/replay_public_case.sh 实测 + tests/test_run_budget.py::test_event_history_survives_reload + tests/test_experiment_attempts.py::test_same_interpreter_different_script_is_rejected | verified |

| A29 | 模拟执行 | 四态一致：execution=simulated（非 completed）、evidence=simulated、outcome=not_assessed、next=request_material | T13 | tests/test_workflow_facts.py::SimulatedStatesTest + ::test_simulated_result_maps_all_four_states | verified |
| A30 | 合格负结果且复核无必须修改项 | 不进入无界修订，直达终局 | T13 | tests/test_workflow_facts.py::NegativeResultRoutingTest::test_negative_result_without_review_tasks_skips_revision | verified |
| A31 | 负结果但有复核任务；修订后审计阻断；三入口 | 进入一次修订（受 paper_revisions 上限）；recheck 按审计实际结果；facts 由共享构造函数生成 | T13 | tests/test_workflow_facts.py::NegativeResultRoutingTest（3 用例） | verified |

| A32 | T14 离线预检、无真实端点/凭据 | 预检链路可运行但 gold canary 保持 not_verified，不生成 publishable | T14 | docs/public-case/t14-canary-offline-doctor.txt + docs/gold-canary-runbook.md | verified |
| A33 | T14 六角色真实账本缺失 | 缺少真实 call_id、角色输入摘要或证据定位时 gate 保持 blocked；当前真实 canary 未执行 | T14 | docs/gold-canary-runbook.md（验收条件，待真实端点） | planned |
| A34 | T15 仅有 benchmark-only 产物 | 未生成论文/独立评审/最终 gate 时保持 benchmark-only 与 not_verified，不得宣称 paper-grade | T15 | docs/public-case/PAPER-GRADE-GAP.md + runs/public-iris-case/CASE-REPORT.md | verified |
| A35 | T16 重放事件数量变化 | replay summary、CASE-REPORT 与 attempts 账本按实际事件一致；允许 interrupted=1、passed=9、总数=10 | T16 | scripts/replay_public_case.sh + scripts/check_public_case_consistency.py（三案例通过） | verified |
| A36 | T17 旧 Run 迁移后进入发布门禁 | 迁移保留 legacy/unknown 标记并使旧批准失效；缺字段 Run 不得直接 publishable | T17 | tests/test_run_migration.py::test_migrated_run_is_blocked_by_publishable_gate + 迁移/幂等测试 | verified |
| A37 | T18 仓库内置机器人 fixture | 真实 RRT 执行可复核但 fixture provenance 的 schema audit 保持 block，不得称外部正式 benchmark | T18 | docs/public-case/ROBOT-CASE.md + runs/robot-rrt2d-case/04-benchmark-result-schema-audit.json | verified |
| A38 | T19/T20 无用户数据与文档漂移 | participants=0 时保持 not_measured；文档漂移检查通过，测试数字来自机器产物 | T19/T20 | docs/trial-kit.md + scripts/check_docs_drift.py + docs/test-evidence.json | verified |

## 使用规则

1. 每个任务实现完成时把对应行的"测试载体"改为实际 `文件::用例名`，
   状态改 `tested`；阶段出口全量复核后改 `verified`。
2. 编号不得复用或重排；若某反例确认在当前架构下不适用，必须在
   `docs/baseline-audit.md` 记录原因，状态标 `n/a`，不允许静默删除。
3. 新增关键反例沿用 A23 起编号并补充输入/行为两列。
