# 决策与工作流完整性修复

## 人工覆盖

最终裁决的 `inputs.verdict_sha256` 是以下规范 JSON 的 SHA-256：schema 版本、当前 revision、确定性审计完整内容、独立审查完整内容、排序去重后的必需角色集合。
使用 UTF-8、按键排序、紧凑分隔符，禁止 NaN。哈希不包含裁决生成时间及人工覆盖自身，避免循环依赖；输入证据内的时间字段仍属于输入内容。

`10-gate-override.json` 必须同时满足：

- `approved` 必须是 JSON 布尔值 `true`，数字和字符串都不接受。
- `revision` 必须是整数且等于当前裁决版本。
- `verdict_sha256` 必须与本次重新计算的证据哈希完全一致。
- reviewer/reason 必须为非空文本，分别不超过 120/500 字符。

先检查 `10-gate-decision.json` 中的完整阻断依据，再把当前 `inputs.verdict_sha256` 写入覆盖文件。任何输入审计或角色结果改变后都需要重新审核；即使 revision 没变，旧哈希也会被拒绝。
有效覆盖保留 `blocking_sources`、覆盖者、理由、原状态和证据哈希。哈希绑定提供完整性检查，不是用户身份认证或数字签名；当前仍面向可信本地用户。

缺失必需角色报告、未知裁决值、未知审计状态按阻断处理；`review_required` 按需要修复处理。

## Run 租约

同一 Run 只有持锁线程可以嵌套进入。其他线程立即得到 `RunLeaseConflict`；同一线程退出最外层后，其他线程可获取租约。`flock` 继续负责跨进程互斥。持有者身份包含进程和线程 ID，预留身份先于打开/锁定文件，关闭了首次获取过程中的线程竞争窗口。

## 实际调度

新建任务和检查点恢复的研究规划、文献、证据整理、人工审核阶段已注册为可执行处理函数；审核后的方案、实验计划、执行审批、实验、分析、写作、审稿、修订、最终审计与完成阶段也由 `WorkflowEngine.run` 调度。
引擎调用处理函数后归约节点事件，根据谓词选择唯一后继；缺少处理函数、无后继或多个后继均失败。`workflow_dispatch` manifest 事件记录实际选边。

- 处理函数负责加载与校验其检查点；文件存在不决定下一个执行阶段。
- local/benchmark 恢复也重新校验执行审批。内容和绑定未变的有效批准可沿用；失效批准必须重新等待。
- 写作阻断时仅生成修复材料并停止，不调用写作、审稿或投稿打包。
- 模拟执行跳过执行审批节点，留下 skipped 事件。
- 当前产品策略仍让每个初审稿经过修订；修订后的复核包含在最终审计处理函数内。引擎支持条件分支，但不宣称已引入自由循环 Agent 调度。
- 人工退回文献仍沿用既有刷新与重新审批适配器；主动修复由现有 repair-resume 入口重新进入检查点调度，不自动无限重试。

原阶段实现保留在命名处理函数内，以维持产物和调用接口兼容。`pipeline.py` 与 Web 模块的进一步物理拆分仍属后续维护工作。

## 验证边界

回归测试包括拒绝/过期/错哈希覆盖、线程竞争、跨进程竞争、同线程重入、等待后恢复、写作阻断、失败不调度后继，以及禁用真实流水线边后不再生成方案或实验。

业务价值证据与下一步试用方式见 [评审测量协议](review-evaluation.md)。真实线上模型与使用者试用尚不能由这些离线测试代替。

## 本次验证记录（Python 3.12，2026-09-09）

- `bash scripts/run_tests.sh --ignore=tests/test_cli.py`：1270 passed、1 skipped、90 subtests passed。
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_cli.py -k 'not gold'`：57 passed、35 deselected、8 subtests passed。
- 补充主流水线覆盖文件校验后，`test_gate_aggregator.py` 与 `test_review_evaluation.py`：24 passed、26 subtests passed。
- 12/12 合成结构化规则案例通过；真实使用者数据仍为 `not_measured`。
- 文档链接检查：16 个 Markdown 文件，0 个坏链接。

以上不是完整线上验收。Gold CLI 包含真实外部文献探测，环境中未配置模型 API Key；完整在线 multi-agent canary 未执行。案例标签及测试桩都不能替代真实专家与使用者证据。
