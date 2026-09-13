#!/usr/bin/env python3
"""公开案例收尾生成器（T10/复审第 6 项）。

从 benchmark pack 运行产物（03-experiment-plan/03-preregistration/04-results）
确定性生成案例的其余评审工件：
- 03-idea-experiment-contract.json（+ 版本历史）
- 04-evidence-integrity.json/.md
- 04-statistics.json（与 pack 运行一致，重算用于决策输入）
- 04-experiment-decision.json/.md（读取契约主指标）
- 04-hypothesis-outcome.json/.md

供 `runs/public-iris-case` 与重放（`scripts/replay_public_case.sh`）共同使用，
保证原始案例与干净检出重放的工件集合一致。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent.artifacts import read_json, write_json, write_text  # noqa: E402
from research_agent.config import ExecutionConfig  # noqa: E402
from research_agent.evidence_integrity import write_evidence_integrity_artifacts  # noqa: E402
from research_agent.experiment_decision import write_experiment_decision_artifacts  # noqa: E402
from research_agent.hypothesis_outcome import write_hypothesis_outcome_artifacts  # noqa: E402
from research_agent.idea_experiment_contract import (  # noqa: E402
    append_contract_history,
    build_execution_contract,
)
from research_agent.models import (  # noqa: E402
    ExperimentCommand,
    ExperimentPlan,
    ResearchIdea,
    ResearchPlan,
    StatisticsReport,
)
from research_agent.statistics import build_statistics_report  # noqa: E402


def _experiment_plan(data: dict) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title=str(data.get("idea_title") or ""),
        objective=str(data.get("objective") or ""),
        variables=[str(v) for v in (data.get("variables") or [])],
        metrics=[str(m) for m in (data.get("metrics") or [])],
        protocol=[str(p) for p in (data.get("protocol") or [])],
        commands=[ExperimentCommand(**c) for c in (data.get("commands") or []) if isinstance(c, dict)],
        rationale=str(data.get("rationale") or ""),
        baseline=str(data.get("baseline") or ""),
        evidence_keys=[str(k) for k in (data.get("evidence_keys") or [])],
        template_profile=str(data.get("template_profile") or "generic"),
    )


def finalize_case(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    plan_data = read_json(run_dir / "03-experiment-plan.json")
    prereg = read_json(run_dir / "03-preregistration.json")
    results_payload = read_json(run_dir / "04-results.json")
    from research_agent.models import ExperimentResult

    plan = _experiment_plan(plan_data if isinstance(plan_data, dict) else {})
    results = [
        ExperimentResult(**row) for row in (results_payload if isinstance(results_payload, list) else []) if isinstance(row, dict)
    ]
    idea = ResearchIdea(
        title=plan.idea_title,
        hypothesis=str(prereg.get("primary_hypothesis") or "候选方法在冻结划分上不劣于基线。"),
        mechanism="由锁定实验计划与预注册生成（公开案例，无模型参与）。",
        expected_contribution="可复现的 CPU 端公开基准闭环案例。",
        novelty=2,
        feasibility=5,
        risk=1,
        evaluation=plan.metrics,
        evidence_keys=["10.24432/C56C76"],
        baseline=plan.baseline,
    )
    research_plan = ResearchPlan(
        topic=str(prereg.get("topic") or plan.idea_title),
        domain="machine-learning",
        objective=plan.objective,
        search_queries=[],
        benchmarks=["UCI Iris"],
        baselines=[plan.baseline],
        metrics=plan.metrics,
        constraints=["离线 CPU 可复现", "使用冻结 split"],
        risks=["结果可能为中性/负结果"],
        success_criteria=["完成 candidate/baseline 统计比较并如实报告"],
    )
    config = ExecutionConfig(mode="benchmark", repeats=3, timeout_seconds=300, allowed_commands=["python3"])

    contract = build_execution_contract(research_plan, idea, plan, config, preregistration=prereg)
    history = append_contract_history(run_dir, contract, results_exist=True)
    contract_report = {
        "topic": prereg.get("topic"),
        "status": "pass",
        "contract": contract,
        "contract_digest": contract.get("digest"),
        "note": "本契约由锁定计划与预注册生成（任务书 T10 冻结）；执行器与结果验证读取同一 digest。",
    }
    write_json(run_dir / "03-idea-experiment-contract.json", contract_report)

    integrity = write_evidence_integrity_artifacts(str(prereg.get("topic") or plan.idea_title), run_dir)

    statistics: StatisticsReport = build_statistics_report(plan, results)
    write_json(run_dir / "04-statistics.json", statistics)
    write_text(run_dir / "04-statistics.md", _statistics_markdown(statistics))

    result_validation = read_json(run_dir / "04-result-validation.json")
    # pack 运行不产出 04-failure-analysis；由统计比较推导等价输入
    # （negative/uncertain 行与 write_failure_analysis 的口径一致）。
    try:
        stored_failure = read_json(run_dir / "04-failure-analysis.json")
    except (OSError, ValueError):
        stored_failure = None
    if isinstance(stored_failure, dict) and stored_failure:
        failure_analysis = stored_failure
    else:
        failure_analysis = {
            "status": "pass" if result_validation.get("status") != "block" else "block",
            "summary": {"failed_runs": 0, "simulated_runs": 0},
            "failed_runs": [],
            "negative_metrics": [
                {"metric": item.metric, "delta": item.delta, "direction": item.direction}
                for item in statistics.comparisons
                if item.direction == "baseline_better_or_equal"
            ],
            "uncertain_metrics": [
                {"metric": item.metric, "delta": item.delta, "direction": item.direction}
                for item in statistics.comparisons
                if item.ci_low <= 0 <= item.ci_high
            ],
            "claim_boundaries": [],
        }
    decision = write_experiment_decision_artifacts(
        plan,
        statistics,
        result_validation if isinstance(result_validation, dict) else {},
        failure_analysis if isinstance(failure_analysis, dict) else {},
        run_dir,
        execution_mode="benchmark",
        contract=contract,
        experiment_evidence_status=integrity.experiment_evidence_status,
    )
    write_hypothesis_outcome_artifacts(
        idea,
        plan,
        statistics,
        result_validation if isinstance(result_validation, dict) else {},
        failure_analysis if isinstance(failure_analysis, dict) else {},
        decision,
        run_dir,
        execution_mode="benchmark",
    )
    return {
        "contract_digest": contract.get("digest"),
        "contract_revision": contract.get("revision"),
        "history_revisions": len(history.get("entries", [])),
        "decision": decision.get("decision"),
        "decision_states": decision.get("decision_states"),
        "research_outcome": decision.get("decision_states", {}).get("research_outcome"),
    }


def _statistics_markdown(statistics: StatisticsReport) -> str:
    lines = ["# 统计比较（重算）", ""]
    for item in statistics.comparisons:
        lines.append(
            f"- {item.metric}: candidate={item.candidate_mean:.6f} baseline={item.baseline_mean:.6f} "
            f"delta={item.delta:.6f} CI=[{item.ci_low:.6f}, {item.ci_high:.6f}] direction={item.direction}"
        )
    return "\n".join(lines)


NEWLINE = chr(10)


def render_case_report(run_dir: Path) -> str:
    """T16：CASE-REPORT.md 完全由产物渲染——不手写尝试计数或状态，
    消除报告与重放产物之间的 15/10、not_assessed/not_supported 漂移。"""
    run_dir = Path(run_dir)
    contract_report = _opt_json(run_dir / "03-idea-experiment-contract.json")
    contract = contract_report.get("contract") or {}
    history = _opt_json(run_dir / "03-experiment-contract-history.json")
    prereg = _opt_json(run_dir / "03-preregistration.json")
    integrity = _opt_json(run_dir / "04-evidence-integrity.json")
    decision = _opt_json(run_dir / "04-experiment-decision.json")
    states = decision.get("decision_states") or {}
    statistics = _opt_json(run_dir / "04-statistics.json")
    attempts_payload = _opt_json(run_dir / "04-experiment-attempts.json")
    attempts = attempts_payload.get("attempts") or []
    interrupted = [a for a in attempts if str(a.get("status")) == "interrupted"]
    passed = [a for a in attempts if str(a.get("status")) == "passed"]
    fault = _opt_json(run_dir / "fault-injection" / "FAULT-INJECTION.json")

    lines = [
        f"# 公开真实闭环案例报告：{prereg.get('topic') or contract.get('hypothesis', {}).get('question', '')}",
        "",
        "> 本报告由 `scripts/finalize_public_case.py` 从案例产物自动渲染（T16）：",
        "> 全部计数与状态来自 04-experiment-attempts / 04-experiment-decision /",
        "> 04-evidence-integrity / 03-experiment-contract-history，不手写。",
        "",
        f"- 案例目录：`{run_dir}`",
        f"- 生成时间：{_utc_now_local()}",
        f"- 案例定位：benchmark-only（LLM/论文/独立评审/gate 步骤 not_verified，见 `docs/public-case/PAPER-GRADE-GAP.md`）",
        "",
        "## 1. 冻结契约与预注册",
        "",
        f"- 契约 digest：`{contract.get('digest', '')[:16]}…`（revision {contract.get('revision')}，历史版本 {len(history.get('entries', []))} 条）",
        f"- 预注册：status={prereg.get('status')}，timing={prereg.get('timing')}，revision={prereg.get('revision')}",
        f"- 主指标：{', '.join((contract.get('evaluation') or {}).get('primary_metrics', []))}",
        f"- 判据：支持={contract.get('criteria', {}).get('supported', '')}",
        "",
        "## 2. 真实执行与中断恢复（实际事件计数）",
        "",
        f"- 执行尝试总数：**{len(attempts)}**（passed={len(passed)}，interrupted={len(interrupted)}，其余={len(attempts) - len(passed) - len(interrupted)}）",
        f"- 中断证据（两种形态，均为真实事件）："
        f"{len(interrupted)} 条尝试带 interrupted 标记（{interrupted[0].get('interrupted_reason') if interrupted else '无'}）；"
        "若单任务尝试编号超过契约 repeats（如 candidate a1–a6 vs repeats=3），说明存在多次执行——"
        "第一次执行进程在中途死亡（未产出 04-results.json），恢复入口核对存活后重跑并顺延编号。",
        f"- 全部尝试的进程身份/起止时间/退出码见 `04-experiment-attempts.json`；日志在 `experiments/logs/`。",
        "",
        "## 3. 结果与决策（产物原文）",
        "",
        f"- evidence：llm={integrity.get('llm_evidence_status')}，experiment={integrity.get('experiment_evidence_status')}",
        f"- decision={decision.get('decision')}；四态：execution={states.get('execution_status')}，evidence={states.get('evidence_status')}，outcome={states.get('research_outcome')}，next={states.get('next_action')}；stop_after_report={states.get('stop_after_report')}",
        "",
        "| 指标 | Candidate | Baseline | Δ | 95% CI | 方向 |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in statistics.get("comparisons", []):
        lines.append(
            f"| {item.get('metric')} | {item.get('candidate_mean'):.6f} | {item.get('baseline_mean'):.6f} "
            f"| {item.get('delta'):.6f} | [{item.get('ci_low'):.6f}, {item.get('ci_high'):.6f}] | {item.get('direction')} |"
        )
    lines += [
        "",
        f"- 统计结论：{statistics.get('warnings') or '无附加警告'}",
        "",
        "## 4. 受控故障注入",
        "",
    ]
    if fault:
        lines += [
            f"- 标记：{fault.get('marked_as')}",
            f"- 注入方式：{fault.get('injection', {}).get('method')}",
            f"- 观察结果：{fault.get('observed', {}).get('benchmark_result_schema_audit_status')}（原因：split_sha256 provenance 不一致），pack 状态 {fault.get('observed', {}).get('benchmark_pack_run_status')}，CLI 退出码 {fault.get('observed', {}).get('cli_exit_code')}",
            f"- 结论：{fault.get('conclusion')}",
        ]
    else:
        lines.append("- 本目录未包含故障注入副本。")
    lines += [
        "",
        "## 5. 复核与限制",
        "",
        "- 依赖在线模型的步骤 not_verified（无凭据）；`publishable` 仅表示通过系统发布前检查。",
        "- 第三方复核：`bash scripts/replay_public_case.sh`；重放生成独立目录与 `replay-summary.json`。",
        "- 人工批准签署栏（actor/时间/理由/版本）待研究者签署，不得由自动化填写。",
        "",
    ]
    return NEWLINE.join(lines)


def _opt_json(path: Path) -> dict:
    try:
        data = read_json(Path(path))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _utc_now_local():
    from research_agent.artifacts import utc_now

    return utc_now()


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/public-iris-case")
    summary = finalize_case(target)
    report_path = target / "CASE-REPORT.md"
    report_path.write_text(render_case_report(target), encoding="utf-8")
    summary["case_report"] = str(report_path)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
