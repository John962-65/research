from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import shutil

from .artifacts import read_json, write_json, write_text, cell as _cell
from .benchmark_adapter import prepare_benchmark_adapter_plan
from .benchmark_evidence_audit import write_benchmark_evidence_audit_artifacts
from .benchmark_plan import BENCHMARK_PLAN_JSON, BENCHMARK_PLAN_MD, render_benchmark_plan_markdown
from .benchmark_result_schema_audit import write_benchmark_result_schema_audit_artifacts
from .config import ExecutionConfig
from .execution_safety import write_execution_safety_audit_artifacts
from .experiments import render_experiment_plan_markdown, run_experiments
from .models import BenchmarkCandidate, BenchmarkPlan, ExperimentCommand, ExperimentPlan, ExperimentResult, ResearchIdea
from .preregistration import PREREGISTRATION_JSON, PREREGISTRATION_MD, write_preregistration_artifacts
from .result_validation import write_result_validation_artifacts
from .statistics import build_statistics_report, render_statistics_markdown, write_statistics_figure_artifacts


BENCHMARK_PACK_RUN_JSON = "04-benchmark-pack-run.json"
BENCHMARK_PACK_RUN_MD = "04-benchmark-pack-run.md"


def run_benchmark_pack(
    *,
    topic: str,
    manifest_paths: list[str],
    out_dir: Path,
    repeats: int = 3,
    allowed_commands: list[str] | None = None,
    timeout_seconds: int = 300,
    force: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not resume:
        if not force:
            raise FileExistsError(f"Output directory is not empty: {out_dir}")
        shutil.rmtree(out_dir)
    if resume and not out_dir.exists():
        raise FileNotFoundError(f"Cannot resume: run directory does not exist: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_state(out_dir, topic, "started")
    config = ExecutionConfig(
        mode="benchmark",
        timeout_seconds=timeout_seconds,
        allowed_commands=allowed_commands or ["python3"],
        repeats=max(1, int(repeats)),
        benchmark_manifest_paths=[str(item) for item in manifest_paths if str(item).strip()],
    )
    plan = _base_plan(topic)
    _, prepared_adapter_report = prepare_benchmark_adapter_plan(plan, config, out_dir, base_dir=Path.cwd())
    if prepared_adapter_report.blocking_issues:
        raise ValueError("Benchmark adapter configuration is blocked: " + "；".join(prepared_adapter_report.blocking_issues))
    prepared_adapter_report_dict = _read_dict(out_dir / "03-benchmark-adapters.json")
    locked_plan = _execution_audit_plan(plan, {"commands": prepared_adapter_report_dict.get("commands", [])}, prepared_adapter_report_dict)
    write_json(out_dir / "03-experiment-plan.json", locked_plan)
    write_text(out_dir / "03-experiment-plan.md", render_experiment_plan_markdown(locked_plan))
    benchmark_plan = _benchmark_plan_from_adapter_report(topic, locked_plan, prepared_adapter_report_dict)
    write_json(out_dir / BENCHMARK_PLAN_JSON, benchmark_plan)
    write_text(out_dir / BENCHMARK_PLAN_MD, render_benchmark_plan_markdown(benchmark_plan))
    benchmark_plan_report = _read_dict(out_dir / BENCHMARK_PLAN_JSON)
    write_execution_safety_audit_artifacts(locked_plan, config, out_dir)
    preregistration = write_preregistration_artifacts(topic, _benchmark_pack_idea(topic, locked_plan), locked_plan, out_dir, results_exist=False)

    # T10/T06：resume 时 run_experiments 会核对尝试账本——活任务不重复启动，
    # 已消亡的中断尝试标记为 interrupted 并保留；随后重跑全部命令。
    results = run_experiments(plan, config, out_dir)
    write_json(out_dir / "04-results.json", results)
    runbook = _read_dict(out_dir / "04-experiment-runbook.json")
    adapter_report = _read_dict(out_dir / "03-benchmark-adapters.json")
    audit_plan = _execution_audit_plan(plan, runbook, adapter_report)
    write_json(out_dir / "03-experiment-plan.json", audit_plan)
    write_text(out_dir / "03-experiment-plan.md", render_experiment_plan_markdown(audit_plan))

    statistics = build_statistics_report(audit_plan, results)
    write_json(out_dir / "04-statistics.json", statistics)
    write_text(out_dir / "04-statistics.md", render_statistics_markdown(statistics))
    write_statistics_figure_artifacts(out_dir, statistics)

    result_validation = write_result_validation_artifacts(audit_plan, results, statistics, out_dir, config.repeats, preregistration=preregistration, execution_mode=config.mode)
    benchmark_schema = write_benchmark_result_schema_audit_artifacts(
        audit_plan,
        results,
        statistics,
        runbook,
        out_dir,
        benchmark_plan=benchmark_plan_report,
        adapter_report=adapter_report,
        result_validation=result_validation,
    )
    benchmark_evidence = write_benchmark_evidence_audit_artifacts(
        audit_plan,
        results,
        statistics,
        result_validation,
        runbook,
        out_dir,
        execution_mode=config.mode,
        benchmark_plan=benchmark_plan_report,
        adapter_report=adapter_report,
    )
    report = _report(topic, config, results, statistics, result_validation, benchmark_schema, benchmark_evidence)
    write_json(out_dir / BENCHMARK_PACK_RUN_JSON, report)
    write_text(out_dir / BENCHMARK_PACK_RUN_MD, render_benchmark_pack_run_markdown(report))
    _write_state(out_dir, topic, "completed")
    return report


def render_benchmark_pack_run_markdown(report: dict[str, Any]) -> str:
    design = report.get("statistical_design") if isinstance(report.get("statistical_design"), dict) else {}
    lines = [
        f"# Benchmark Pack Run：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 执行模式：{report.get('execution_mode') or '-'}",
        f"- 重复次数：{report.get('repeats') or 0}",
        f"- 结果数：{report.get('results') or 0}",
        f"- 统计比较：{report.get('comparisons') or 0}",
        f"- Result validation：{report.get('result_validation_status') or '-'}",
        f"- Benchmark schema：{report.get('benchmark_schema_status') or '-'}",
        f"- Benchmark evidence：{report.get('benchmark_evidence_status') or '-'} / {report.get('benchmark_evidence_grade') or '-'}",
        f"- 统计结果：{report.get('statistical_outcome') or '-'}",
        f"- Claim 边界严重性：{report.get('claim_boundary_severity') or '-'}",
        f"- 可发表负/中性结果：{'是' if report.get('publishable_negative_or_neutral_result') else '否'}",
        f"- 多重比较策略：{design.get('multiplicity_status') or '-'}",
        f"- 功效/敏感性分析：{design.get('power_status') or '-'}",
        "",
        "## Metrics",
        "| Metric | Candidate | Baseline | Delta | 95% CI | Effect size | Direction |",
        "| --- | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for item in report.get("statistics", []) if isinstance(report.get("statistics"), list) else []:
        effect = item.get("effect_size")
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("metric") or "")),
                    _fmt(item.get("candidate_mean")),
                    _fmt(item.get("baseline_mean")),
                    _fmt(item.get("delta")),
                    f"[{_fmt(item.get('ci_low'))}, {_fmt(item.get('ci_high'))}]",
                    "-" if effect is None else _fmt(effect),
                    _cell(str(item.get("direction") or "")),
                ]
            )
            + " |"
        )
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {item}" for item in warnings)
    if design:
        lines.extend(
            [
                "",
                "## Statistical Design",
                f"- Multiplicity：{design.get('multiplicity_status') or '-'}；family size={design.get('family_size') or 0}",
                f"- Power/sensitivity：{design.get('power_status') or '-'}；per-group repeats={design.get('per_group_repeats') or 0}；MDE={design.get('minimum_detectable_standardized_effect') or '-'}",
                f"- Claim boundary：{design.get('claim_boundary') or '-'}",
            ]
        )
    lines.extend(["", "## Artifacts"])
    for artifact in report.get("artifacts", []) if isinstance(report.get("artifacts"), list) else []:
        lines.append(f"- `{artifact}`")
    return "\n".join(lines)


def _base_plan(topic: str) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title=topic,
        objective="Execute a paper-grade benchmark manifest set and produce standard research-agent result artifacts.",
        variables=["method_role", "repeat_index"],
        metrics=["accuracy", "macro_f1", "error_rate"],
        protocol=[
            "Load candidate, baseline, and ablation benchmark manifests.",
            "Execute every role for the configured repeat count under the benchmark command allowlist.",
            "Write 04-results, 04-statistics, runbook, result validation, and benchmark evidence audits.",
        ],
        commands=[],
        rationale="This standalone run validates benchmark pack execution without claiming an end-to-end autonomous paper run.",
        baseline="manifest baseline role",
        template_profile="benchmark_pack",
    )


def _execution_audit_plan(plan: ExperimentPlan, runbook: dict[str, Any], adapter_report: dict[str, Any]) -> ExperimentPlan:
    commands = _runbook_experiment_commands(runbook) or plan.commands
    metrics = _adapter_expected_metrics(adapter_report) or _runbook_plan_metrics(runbook) or plan.metrics
    return ExperimentPlan(
        idea_title=plan.idea_title,
        objective=plan.objective,
        variables=plan.variables,
        metrics=metrics,
        protocol=[*plan.protocol, "Statistics and audits use the adapter commands and metrics executed from the benchmark runbook."],
        commands=commands,
        rationale=plan.rationale,
        baseline=plan.baseline,
        evidence_keys=plan.evidence_keys,
        template_profile=plan.template_profile,
    )


def _runbook_experiment_commands(runbook: dict[str, Any]) -> list[ExperimentCommand]:
    commands: list[ExperimentCommand] = []
    for item in runbook.get("commands", []) if isinstance(runbook.get("commands"), list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        command = [str(value) for value in item.get("command", [])] if isinstance(item.get("command"), list) else []
        expected = [str(value) for value in item.get("expected_artifacts", [])] if isinstance(item.get("expected_artifacts"), list) else []
        role = str(item.get("role") or "").strip()
        commands.append(ExperimentCommand(name=name, command=command, expected_artifacts=expected, role=role))
    return commands


def _adapter_expected_metrics(adapter_report: dict[str, Any]) -> list[str]:
    metrics: list[str] = []
    for item in adapter_report.get("adapters", []) if isinstance(adapter_report.get("adapters"), list) else []:
        if not isinstance(item, dict) or str(item.get("status") or "") != "ready":
            continue
        metrics.extend(str(value) for value in item.get("expected_metrics", []) if str(value).strip())
    return _unique(metrics)


def _runbook_plan_metrics(runbook: dict[str, Any]) -> list[str]:
    plan = runbook.get("plan") if isinstance(runbook.get("plan"), dict) else {}
    return [str(value) for value in plan.get("metrics", [])] if isinstance(plan.get("metrics"), list) else []


def _report(
    topic: str,
    config: ExecutionConfig,
    results: list[ExperimentResult],
    statistics,
    result_validation: dict[str, Any],
    benchmark_schema: dict[str, Any],
    benchmark_evidence: dict[str, Any],
) -> dict[str, Any]:
    statuses = [
        str(result_validation.get("status") or ""),
        str(benchmark_schema.get("status") or ""),
        str(benchmark_evidence.get("status") or ""),
    ]
    blocking_statuses = {"block", "blocked", "smoke_only"}
    status = "block" if any(item in blocking_statuses for item in statuses) else "warn" if any(item in {"warn", "review_required"} for item in statuses) else "pass"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "execution_mode": config.mode,
        "repeats": config.repeats,
        "results": len(results),
        "comparisons": len(statistics.comparisons),
        "result_validation_status": str(result_validation.get("status") or ""),
        "benchmark_schema_status": str(benchmark_schema.get("status") or ""),
        "benchmark_evidence_status": str(benchmark_evidence.get("status") or ""),
        "benchmark_evidence_grade": str(benchmark_evidence.get("evidence_grade") or ""),
        "statistical_outcome": str(benchmark_evidence.get("statistical_outcome") or ""),
        "claim_boundary_severity": str(benchmark_evidence.get("claim_boundary_severity") or ""),
        "publishable_negative_or_neutral_result": benchmark_evidence.get("publishable_negative_or_neutral_result") is True,
        "claim_policy": str(benchmark_evidence.get("claim_policy") or ""),
        "statistical_design": _statistical_design_summary(statistics),
        "statistics": [
            {
                "metric": item.metric,
                "candidate_mean": item.candidate_mean,
                "baseline_mean": item.baseline_mean,
                "delta": item.delta,
                "ci_low": item.ci_low,
                "ci_high": item.ci_high,
                "effect_size": item.effect_size,
                "direction": item.direction,
            }
            for item in statistics.comparisons
        ],
        "warnings": [*statistics.warnings, *result_validation.get("warnings", []), *benchmark_schema.get("warnings", []), *benchmark_evidence.get("warnings", [])],
        "artifacts": [
            "03-benchmark-adapters.json",
            "03-execution-safety-audit.json",
            "03-benchmark-plan.json",
            "03-benchmark-plan.md",
            "03-preregistration.json",
            "03-preregistration.md",
            "04-results.json",
            "04-results.csv",
            "04-experiment-runbook.json",
            "04-environment-snapshot.json",
            "04-statistics.json",
            "04-statistics-figure.svg",
            "04-result-validation.json",
            "04-benchmark-result-schema-audit.json",
            "04-benchmark-evidence-audit.json",
        ],
    }


def _statistical_design_summary(statistics) -> dict[str, Any]:
    multiplicity = statistics.multiplicity if isinstance(getattr(statistics, "multiplicity", None), dict) else {}
    power = statistics.power_analysis if isinstance(getattr(statistics, "power_analysis", None), dict) else {}
    return {
        "schema_version": 1,
        "status": "pass" if multiplicity.get("status") == "pass" and power.get("status") in {"profile_ready", "pass"} else "review_required",
        "multiplicity_status": str(multiplicity.get("status") or ""),
        "power_status": str(power.get("status") or ""),
        "family_size": int(multiplicity.get("family_size") or 0),
        "primary_metrics": [str(item) for item in multiplicity.get("primary_metrics", [])] if isinstance(multiplicity.get("primary_metrics"), list) else [],
        "ci_crosses_zero": int(multiplicity.get("ci_crosses_zero") or 0),
        "stable_candidate_better": int(multiplicity.get("stable_candidate_better") or 0),
        "per_group_repeats": int(power.get("per_group_repeats") or 0),
        "minimum_detectable_standardized_effect": power.get("minimum_detectable_standardized_effect"),
        "claim_boundary": str(multiplicity.get("claim_boundary") or ""),
        "interpretation": str(power.get("interpretation") or ""),
    }


def _read_dict(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _benchmark_pack_idea(topic: str, plan: ExperimentPlan) -> ResearchIdea:
    return ResearchIdea(
        title=topic,
        hypothesis="The configured candidate, baseline, ablation, and reference benchmark roles can be executed reproducibly under the declared manifest contracts.",
        mechanism="Benchmark manifest adapters lock commands, expected metrics, source files, split hashes, grader hashes, and role metadata before execution.",
        expected_contribution="A standalone benchmark-pack run that validates real benchmark provenance and produces auditable statistics before an end-to-end paper-grade gold run.",
        novelty=1,
        feasibility=5,
        risk=2,
        evaluation=[*plan.metrics],
        evidence_keys=["benchmark_manifest_pack"],
        baseline=plan.baseline,
        experiment_sketch=[*plan.protocol],
    )


def _benchmark_plan_from_adapter_report(topic: str, plan: ExperimentPlan, adapter_report: dict[str, Any]) -> BenchmarkPlan:
    adapters = [item for item in adapter_report.get("adapters", []) if isinstance(item, dict) and str(item.get("status") or "") == "ready"]
    expected_metrics = _unique([str(metric) for item in adapters for metric in item.get("expected_metrics", []) if str(metric).strip()])
    baselines = _unique([str(item.get("baseline") or "") for item in adapters if str(item.get("baseline") or "").strip()])
    first = adapters[0] if adapters else {}
    dataset_url = str(first.get("dataset_url") or first.get("benchmark_url") or "").strip()
    dataset_version = str(first.get("dataset_version") or "").strip()
    license_notes = str(first.get("license") or "需人工核对 benchmark/data 许可证。").strip()
    candidate = BenchmarkCandidate(
        name=_benchmark_candidate_name(first, topic),
        domain="benchmark_pack",
        benchmark_type="external benchmark manifest pack",
        url=dataset_url,
        access=dataset_version or "Manifest-provided dataset and benchmark provenance.",
        license_notes=license_notes,
        expected_metrics=expected_metrics or plan.metrics,
        baselines=baselines or [plan.baseline],
        integration_steps=[
            "Use the locked benchmark manifests listed in 03-benchmark-adapters.",
            "Execute candidate, baseline, ablation, and reference roles under the command allowlist.",
            "Keep grader, split, data, and result artifact SHA256 values in the runbook.",
        ],
        risks=[
            "Standalone benchmark-pack evidence validates execution and provenance but does not replace an end-to-end paper-grade gold run.",
        ],
        status="selected",
    )
    return BenchmarkPlan(
        topic=topic,
        domain="benchmark_pack",
        template_profile=plan.template_profile,
        candidates=[candidate],
        selected_names=[candidate.name],
        required_actions=[],
        warnings=[],
    )


def _benchmark_candidate_name(adapter: dict[str, Any], topic: str) -> str:
    citation = str(adapter.get("citation") or "").strip()
    dataset_url = str(adapter.get("dataset_url") or adapter.get("benchmark_url") or "").strip()
    if "10.24432/C56C76" in citation or "iris" in dataset_url.lower():
        return "UCI Iris dataset manifest pack"
    return f"{topic} manifest pack"


def _write_state(out_dir: Path, topic: str, stage: str) -> None:
    write_json(out_dir / "state.json", {"topic": topic, "stage": stage, "updated_at": datetime.now(timezone.utc).isoformat()})


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _fmt(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.6g}"
    return str(value)


