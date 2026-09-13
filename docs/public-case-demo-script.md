# 公开案例演示脚本（3–5 分钟）

面向面试/评审场景：演示"研究者提交实验材料后，系统基于冻结标准和当前证据
给出可解释、可复查、可纠错的下一步决定"。

## 准备（30 秒，可提前完成）

```bash
cd research-fixed
bash scripts/replay_public_case.sh   # 离线重放，生成 runs/public-iris-case-replay
```

## 演示流程

### 1. 冻结的标准（45 秒）

打开 `runs/public-iris-case/03-idea-experiment-contract.json`：
指出八字段组（假设/方法/数据/评估/判据/验证/执行）与内容 digest；
再看 `03-preregistration.json`（status=locked，timing=before_results）——
标准在结果产生之前被锁定，结果出来后改指标会产生新版本而不是沿用旧批准。

### 2. 真实执行与中断恢复（60 秒）

- `04-experiment-attempts.json`：真实进程执行记录（数量由实际账本决定；基线归档为 15 条，干净重放通常为 10 条，含 1 次中断和 9 次最终成功）
  PID/起止时间/退出码）。指着编号 a1–a3 与 a4–a6 讲中断故事：
  第一次执行在 candidate/baseline 完成后被真实 SIGINT 终止，
  `--resume` 原地恢复，旧尝试保留、新尝试顺延编号。
- `experiments/logs/`：每次执行的真实 stdout/stderr 落盘。
- 强调守卫：恢复前核对 `/proc/<pid>/cmdline` 身份，活任务不重复启动
  （单元验证 `tests/test_experiment_attempts.py`）。

### 3. 结果与诚实判定（45 秒）

`04-benchmark-pack-run.json`：accuracy/macro_f1/error_rate 全部 Δ=0、CI 零宽 →
`statistical_outcome=neutral_no_observed_difference`、
`publishable_negative_or_neutral_result=True`。
要点：这是一个**合格的中性/负结果**——系统不把它包装成优势结论，
也不阻断它完成；边界语言来自系统而不是模型。

### 4. 纠错：故障注入被阻断（60 秒）

`runs/public-iris-case/fault-injection/FAULT-INJECTION.json`（明确标记为
受控故障注入）：把冻结 split 删 3 个样本再跑同一流水线——
`04-benchmark-result-schema-audit.json` 判 block：
"split_sha256 与 split_path 实际 SHA256 不一致"，pack 状态 block、退出码 2。
一句话：执行通过 ≠ 证据通过；篡改数据被 provenance 审计抓住。

### 5. 页面与决定（45 秒，可选）

启动 `research-agent-web`，在评审决策面板看四类状态分离显示
（执行状态/证据状态/研究结论/下一步动作）、阻断原因、预算与"本次修改影响"；
审批理由框不预填"已核对"文字，审批者身份如实标注单用户原型。

### 6. 边界声明（收尾 15 秒）

本案例无任何模型调用：LLM 证据=unknown，相关步骤 not_verified；
`publishable` 只表示通过系统约定的发布前检查，不代表期刊发表。
