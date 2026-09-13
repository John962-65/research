# 集中验收矩阵（acceptance-matrix）v1.0

冻结日期：2026-09-13（任务书 T00）。编号稳定：A01–A22 与任务书 §6 一一对应，
实现任务必须在"测试载体"列登记实际测试（文件::用例），验收时逐项核对
"必须观察到的行为"，不允许只断言生成文件或函数无异常。

状态标记：`planned`（未实现）→ `tested`（已登记测试且通过）→ `verified`
（阶段出口复核通过）。

| 编号 | 输入变化或故障 | 必须观察到的行为 | 所属任务 | 测试载体 | 状态 |
|---|---|---|---|---|---|
| A01 | 模型调用全失败（total>0，success=0） | 不计为成功模型产物 | T01/T04 | tests/test_evidence_integrity.py::test_all_failed_llm_calls_are_not_real_evidence | tested |
| A02 | 只有 failed/cancelled/timed_out 结果 | 无可用于主张的已验证实验结果 | T01 | tests/test_evidence_integrity.py::test_failed_only_results_are_attempts_not_verified_results | tested |
| A03 | 成功标签但无指标/NaN/Inf/来源缺失 | incomplete 或 invalid，给出原因 | T01 | tests/test_evidence_integrity.py::test_result_without_finite_metrics_is_not_verified | tested |
| A04 | 人工报告 + 完整真实实验 | 来源分开显示，不因无模型调用而判模拟 | T01 | tests/test_evidence_integrity.py::test_manual_report_with_real_experiment_is_not_simulated | tested |
| A05 | 审计状态不变，证据正文变 | 最终摘要变化，旧批准失效 | T02 | tests/test_gate_aggregator.py::test_override_rejects_invalid_semantics_and_changed_evidence | tested |
| A06 | 稿件变化后恢复 | 相关评审重新执行（不按 revision 复用旧 deliberation） | T02 | tests/test_gate_aggregator.py::test_stale_deliberation_is_rerun_on_resume + tests/test_evidence_snapshot.py::test_pipeline_reuse_gate_honors_snapshot | tested |
| A07 | 无效或旧人工覆盖（缺字段/"true"/旧摘要） | 拒绝覆盖，保留原决定 | T02 | tests/test_gate_aggregator.py::test_human_override_requires_full_provenance、::test_override_rejects_invalid_semantics_and_changed_evidence、::test_non_overridable_reasons_reject_override | tested |
| A08 | 校验与提交之间材料变动 | 不提交基于旧输入的决定 | T02 | tests/test_evidence_snapshot.py::test_build_digest_and_verify_roundtrip + tests/test_gate_aggregator.py::test_pipeline_rechecks_override_file_against_current_evidence | tested |
| A09 | 伪造/失败 call_id 或无引用 pass | 不计作有效独立评审票 | T03 | tests/test_gate_aggregator.py::test_verdict_must_match_ledger_records、::test_minimal_verdict_without_refs_or_summary_rejected、::test_independent_verdicts_are_bound_to_real_calls | tested |
| A10 | 明确启用模板降级 | 保留失败和来源，必需评审仍待完成 | T04 | tests/test_ai_integration.py::ExplicitTemplateFallbackTest（4 用例）+ 既有 test_llm_call_failures_are_not_replaced_by_rule_fallbacks 恢复通过 | tested |
| A11 | 契约完整、idea 未重复执行细节 | 不因文案关键词缺失误拦 | T05 | tests/test_idea_experiment_contract.py::test_complete_contract_passes_without_keyword_echo、::test_execution_contract_has_eight_field_groups | tested |
| A12 | 结果出来后改指标或划分 | 新版本/新分析身份，旧批准不沿用 | T05 | tests/test_idea_experiment_contract.py::test_contract_history_versions_after_results + tests/test_preregistration.py::test_posthoc_metric_change_creates_new_version + tests/test_result_validation.py::test_posthoc_contract_change_blocks_with_binding_mismatch | tested |
| A13 | 即刻崩溃或任务重启 | 及时报错，不重复启动活任务 | T06 | tests/test_experiment_attempts.py（ProcessMatchTest 3 用例 + RunExperimentsResumeGuardTest 3 用例，含 PID 复用与中断保留） | tested |
| A14 | 同 Run 线程/进程竞争 | 互斥成立，同线程嵌套仍正常 | T06 | tests/test_run_lease.py（既有回归，4 用例保留） | tested |
| A15 | 正确完成但假设不成立 | 允许准确负结果报告，停止无意义循环 | T07 | tests/test_experiment_decision.py::test_negative_result_maps_to_not_supported_with_stop_after_report、::test_blocked_validation_maps_to_repair_and_not_assessed、::test_simulated_mode_maps_to_simulated_evidence | tested |
| A16 | 超出总预算/最大轮次 | 停止并保留已有证据 | T07 | tests/test_run_budget.py（3 用例，含恢复不绕过） | tested |
| A17 | 引用否定方向/数字/条件相反 | 不得自动宣称已支持 | T08 | tests/test_claim_evidence_polarity.py（6 用例）+ tests/test_claim_traceability.py::test_contradicted_direction_blocks_claim_with_claim_id | tested |
| A18 | 正确主张且证据完整 | 可通过并定位证据 | T08 | tests/test_claim_traceability.py::test_supported_claim_with_complete_evidence_passes + citation_grounding evidence_locator（chunk/字符跨度/页码） | tested |
| A19 | 页面提交旧版本批准 | 后端拒绝，提示材料变化 | T09 | tests/test_web_server.py::test_stale_approval_rejected | planned |
| A20 | 正常真实案例 | 可重算关键结果并解释最终决策 | T10 | runs 公开案例 + scripts/replay_public_case.sh（人工核对记录） | planned |
| A21 | 无试用数据 | 保持 not_measured，不生成效率比例 | T11 | tests/test_review_evaluation.py（既有；docs/review-evaluation.md 声明） | planned |
| A22 | 同输入走 CLI/Web/恢复 | 决策、原因、证据版本一致 | T12 | tests/test_cli.py 决策一致性用例 | planned |

## 使用规则

1. 每个任务实现完成时把对应行的"测试载体"改为实际 `文件::用例名`，
   状态改 `tested`；阶段出口全量复核后改 `verified`。
2. 编号不得复用或重排；若某反例确认在当前架构下不适用，必须在
   `docs/baseline-audit.md` 记录原因，状态标 `n/a`，不允许静默删除。
3. 新增关键反例沿用 A23 起编号并补充输入/行为两列。
