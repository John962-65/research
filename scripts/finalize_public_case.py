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


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/public-iris-case")
    summary = finalize_case(target)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
