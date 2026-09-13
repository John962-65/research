from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import read_json, write_json, write_text, cell as _cell
from .models import ExperimentPlan, ExperimentResult, StatisticsReport
from .preregistration import plan_fingerprint


RESULT_VALIDATION_JSON = "04-result-validation.json"
RESULT_VALIDATION_MD = "04-result-validation.md"


def write_result_validation_artifacts(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    run_dir: Path,
    expected_repeats: int,
    preregistration: dict[str, Any] | None = None,
    execution_mode: str = "",
) -> dict[str, Any]:
    contract_report = _read_local_dict(run_dir / "03-idea-experiment-contract.json")
    contract = contract_report.get("contract") if isinstance(contract_report.get("contract"), dict) else {}
    runbook = _read_local_dict(run_dir / "04-experiment-runbook.json")
    binding = runbook.get("contract_binding") if isinstance(runbook.get("contract_binding"), dict) else None
    report = build_result_validation_report(
        plan,
        results,
        statistics,
        expected_repeats,
        preregistration=preregistration,
        execution_mode=execution_mode,
        contract=contract,
        contract_binding=binding,
        contract_check_expected=(run_dir / "04-experiment-runbook.json").exists(),
    )
    write_json(run_dir / RESULT_VALIDATION_JSON, report)
    write_text(run_dir / RESULT_VALIDATION_MD, render_result_validation_markdown(report))
    return report


def build_result_validation_report(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    statistics: StatisticsReport,
    expected_repeats: int,
    preregistration: dict[str, Any] | None = None,
    execution_mode: str = "",
    contract: dict[str, Any] | None = None,
    contract_binding: dict[str, Any] | None = None,
    contract_check_expected: bool = False,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    blocking: list[str] = []
    warnings: list[str] = []
    expected = max(1, int(expected_repeats))
    _check_result_presence(results, items, blocking)
    _check_command_coverage(plan, results, expected, items, blocking)
    _check_ablation_coverage(plan, results, expected, items, blocking, warnings, execution_mode)
    _check_preregistration(plan, statistics, preregistration, items, blocking, warnings, execution_mode)
    _check_contract_binding(contract, contract_binding, items, blocking, warnings, contract_check_expected)
    _check_run_status(results, items, blocking)
    _check_metrics(plan, results, items, blocking, warnings)
    _check_statistics(statistics, items, blocking, warnings, execution_mode)
    status = "block" if blocking else "warn" if warnings else "pass"
    return {
        "idea_title": plan.idea_title,
        "status": status,
        "execution_mode": execution_mode,
        "expected_repeats": expected,
        "total_results": len(results),
        "preregistration_status": str((preregistration or {}).get("status") or ""),
        "blocking_issues": blocking,
        "warnings": warnings,
        "items": items,
    }


def render_result_validation_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 实验结果有效性验证：{report.get('idea_title') or ''}",
        "",
        f"- 状态：{report.get('status') or 'unknown'}",
        f"- 期望重复次数：{report.get('expected_repeats', 0)}",
        f"- 结果数：{report.get('total_results', 0)}",
        f"- 阻断问题：{len(report.get('blocking_issues', []) if isinstance(report.get('blocking_issues'), list) else [])}",
        f"- 警告：{len(report.get('warnings', []) if isinstance(report.get('warnings'), list) else [])}",
        "",
    ]
    blocking = report.get("blocking_issues") if isinstance(report.get("blocking_issues"), list) else []
    if blocking:
        lines.extend(["## 阻断问题"])
        lines.extend(f"- {item}" for item in blocking)
        lines.append("")
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    if warnings:
        lines.extend(["## 警告"])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    lines.extend(
        [
            "## 检查项",
            "| 检查 | 状态 | 详情 |",
            "| --- | --- | --- |",
        ]
    )
    for item in report.get("items", []):
        if isinstance(item, dict):
            lines.append(f"| {_cell(str(item.get('name') or ''))} | {_cell(str(item.get('status') or ''))} | {_cell(str(item.get('detail') or ''))} |")
    lines.extend(
        [
            "",
            "## 使用方式",
            "- `block` 表示结果不足以支撑论文分析，应先修复实验执行或指标产物。",
            "- `warn` 表示可进入草稿，但论文中必须保留局限性和人工复核说明。",
        ]
    )
    return "\n".join(lines)


def _check_result_presence(results: list[ExperimentResult], items: list[dict[str, Any]], blocking: list[str]) -> None:
    if results:
        items.append({"name": "result_presence", "status": "pass", "detail": f"{len(results)} results"})
        return
    detail = "没有实验结果。"
    items.append({"name": "result_presence", "status": "block", "detail": detail})
    blocking.append(detail)


def _check_command_coverage(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    expected_repeats: int,
    items: list[dict[str, Any]],
    blocking: list[str],
) -> None:
    missing: list[str] = []
    by_name: dict[str, int] = {}
    for result in results:
        by_name[result.name] = by_name.get(result.name, 0) + 1
    for command in plan.commands:
        count = by_name.get(command.name, 0)
        if count < expected_repeats:
            missing.append(f"{command.name}: {count}/{expected_repeats}")
    if missing:
        detail = "命令重复结果不足：" + "；".join(missing)
        items.append({"name": "command_coverage", "status": "block", "detail": detail})
        blocking.append(detail)
    else:
        items.append({"name": "command_coverage", "status": "pass", "detail": f"{len(plan.commands)} commands covered"})


def _check_ablation_coverage(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    expected_repeats: int,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
    execution_mode: str,
) -> None:
    ablation_names = [command.name for command in plan.commands if _is_ablation_name(command.name)]
    if not ablation_names:
        detail = "实验计划缺少 ablation 命令，无法验证核心机制贡献。"
        if execution_mode == "benchmark":
            detail += " 当前 benchmark adapter 未暴露 ablation 角色，只能作为非消融 benchmark/smoke 证据。"
            items.append({"name": "ablation_coverage", "status": "warn", "detail": detail})
            warnings.append(detail)
        else:
            items.append({"name": "ablation_coverage", "status": "block", "detail": detail})
            blocking.append(detail)
        return
    by_name: dict[str, int] = {}
    for result in results:
        by_name[result.name] = by_name.get(result.name, 0) + 1
    missing = [f"{name}: {by_name.get(name, 0)}/{expected_repeats}" for name in ablation_names if by_name.get(name, 0) < expected_repeats]
    if missing:
        detail = "ablation 重复结果不足：" + "；".join(missing)
        items.append({"name": "ablation_coverage", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    items.append({"name": "ablation_coverage", "status": "pass", "detail": f"{len(ablation_names)} ablation commands covered"})


def _check_preregistration(
    plan: ExperimentPlan,
    statistics: StatisticsReport,
    preregistration: dict[str, Any] | None,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
    execution_mode: str,
) -> None:
    if not preregistration:
        detail = "缺少 03-preregistration，无法证明 primary metrics 和分析规则在实验前锁定。"
        items.append({"name": "preregistration", "status": "warn", "detail": detail})
        warnings.append(detail)
        return
    status = str(preregistration.get("status") or "")
    if status == "block":
        detail = "预注册存在阻断问题：" + "；".join(str(item) for item in _as_list(preregistration.get("blocking_issues"))[:4])
        items.append({"name": "preregistration", "status": "block", "detail": detail})
        blocking.append(detail)
        return
    expected_fingerprint = str(preregistration.get("plan_fingerprint") or "")
    actual_fingerprint = plan_fingerprint(plan)
    if expected_fingerprint and expected_fingerprint != actual_fingerprint:
        detail = "实验计划与预注册 plan_fingerprint 不一致，可能存在事后改计划。"
        if execution_mode == "benchmark":
            detail += " 当前 benchmark 执行计划来自预先配置的 manifest adapter，需人工确认 manifest 在执行审批前已锁定。"
            items.append({"name": "preregistration", "status": "warn", "detail": detail})
            warnings.append(detail)
        else:
            items.append({"name": "preregistration", "status": "block", "detail": detail})
            blocking.append(detail)
        return
    primary = {str(item) for item in _as_list(preregistration.get("primary_metrics")) if str(item).strip()}
    compared = {item.metric for item in statistics.comparisons}
    missing_primary = sorted(primary - compared)
    if missing_primary:
        detail = "预注册 primary metrics 未进入统计比较：" + ",".join(missing_primary[:6])
        if execution_mode == "benchmark":
            detail += "；benchmark adapter 结果可继续审计，但不得据此写强比较结论。"
            items.append({"name": "preregistration", "status": "warn", "detail": detail})
            warnings.append(detail)
        else:
            items.append({"name": "preregistration", "status": "block", "detail": detail})
            blocking.append(detail)
        return
    if status == "posthoc":
        detail = "03-preregistration 是已有结果后的 posthoc_checkpoint，只能作为事后审计。"
        items.append({"name": "preregistration", "status": "warn", "detail": detail})
        warnings.append(detail)
        return
    items.append({"name": "preregistration", "status": "pass", "detail": f"{len(primary)} primary metrics locked"})


def _check_contract_binding(
    contract: dict[str, Any] | None,
    binding: dict[str, Any] | None,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
    check_expected: bool = False,
) -> None:
    """A12：结果出来后改契约 → 执行绑定摘要失效，旧批准与分析身份不再沿用。"""
    if not contract:
        if not check_expected:
            return
        detail = "缺少 03-idea-experiment-contract 的结构化契约（旧结构）；建议迁移后重跑关键比较。"
        items.append({"name": "contract_binding", "status": "warn", "detail": detail})
        warnings.append(detail)
        return
    bound = str((binding or {}).get("contract_digest") or "")
    current = str(contract.get("digest") or "")
    if bound and bound != current:
        detail = (
            "执行绑定的契约摘要与当前契约不一致：已有结果可能基于旧契约版本；"
            "旧批准与分析身份不再沿用，必须生成新契约版本并人工确认后重跑比较（A12）。"
        )
        items.append({
            "name": "contract_binding", "status": "block", "detail": detail,
            "overridable": False, "block_reason_code": "contract_violation",
        })
        blocking.append(detail)
        return
    if bound:
        items.append({"name": "contract_binding", "status": "pass", "detail": f"执行绑定摘要一致（{current[:12]}）"})
    else:
        detail = "04-experiment-runbook 缺少契约绑定记录（旧结构）；结果与契约的对应关系待人工确认。"
        items.append({"name": "contract_binding", "status": "warn", "detail": detail})
        warnings.append(detail)


def _check_run_status(results: list[ExperimentResult], items: list[dict[str, Any]], blocking: list[str]) -> None:
    bad = [result for result in results if result.status in {"failed", "blocked", "timeout"}]
    if bad:
        detail = "存在失败/阻断/超时结果：" + "；".join(f"{item.name}:{item.status}" for item in bad[:8])
        items.append({"name": "run_status", "status": "block", "detail": detail})
        blocking.append(detail)
    else:
        items.append({"name": "run_status", "status": "pass", "detail": "没有 failed/blocked/timeout 结果"})


def _check_metrics(
    plan: ExperimentPlan,
    results: list[ExperimentResult],
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
) -> None:
    expected_metrics = {metric for metric in plan.metrics if metric}
    if not expected_metrics:
        warnings.append("实验计划没有声明 metrics。")
        items.append({"name": "metric_schema", "status": "warn", "detail": "实验计划没有声明 metrics"})
        return
    missing: list[str] = []
    for result in results:
        if result.status in {"failed", "blocked", "timeout"}:
            continue
        keys = set(result.metrics)
        if not keys:
            missing.append(f"{result.name}#{result.repeat_index}: no metrics")
            continue
        missing_metrics = sorted(expected_metrics - keys)
        if missing_metrics:
            missing.append(f"{result.name}#{result.repeat_index}: missing {','.join(missing_metrics[:4])}")
    if missing:
        detail = "指标缺失：" + "；".join(missing[:8])
        items.append({"name": "metric_schema", "status": "block", "detail": detail})
        blocking.append(detail)
    else:
        items.append({"name": "metric_schema", "status": "pass", "detail": f"{len(expected_metrics)} planned metrics present"})


def _check_statistics(
    statistics: StatisticsReport,
    items: list[dict[str, Any]],
    blocking: list[str],
    warnings: list[str],
    execution_mode: str,
) -> None:
    if not statistics.comparisons:
        detail = "candidate 与 baseline 没有可比较的共同指标。"
        if execution_mode == "benchmark":
            detail += " 当前 benchmark adapter 只能证明执行闭环，不能支撑 candidate-baseline 优劣比较。"
            items.append({"name": "statistical_comparability", "status": "warn", "detail": detail})
            warnings.append(detail)
        else:
            items.append({"name": "statistical_comparability", "status": "block", "detail": detail})
            blocking.append(detail)
        return
    uncertain = [item for item in statistics.comparisons if item.ci_low <= 0 <= item.ci_high]
    if len(uncertain) == len(statistics.comparisons):
        if all(abs(item.delta) < 1e-12 and abs(item.ci_low) < 1e-12 and abs(item.ci_high) < 1e-12 for item in uncertain):
            detail = "所有比较指标的 candidate-baseline 差值为 0 且 CI 零宽；当前 repeat 未观察到差异，不能据此声明优势或稳定性。"
        else:
            detail = "所有比较指标的 95% CI 都跨过 0，结论不稳定。"
        items.append({"name": "statistical_comparability", "status": "warn", "detail": detail})
        warnings.append(detail)
    else:
        items.append(
            {
                "name": "statistical_comparability",
                "status": "pass",
                "detail": f"{len(statistics.comparisons)} comparisons, {len(uncertain)} uncertain",
            }
        )
    if statistics.warnings:
        warnings.extend(str(item) for item in statistics.warnings)


def _read_local_dict(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_ablation_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ("ablation", "without", "ablated"))
