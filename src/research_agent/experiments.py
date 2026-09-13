from __future__ import annotations

from pathlib import Path
from typing import Any
import csv
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import platform
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import tomllib

from .artifacts import write_json, write_text, cell as _cell, utc_now as _utc_now
from .benchmark_adapter import prepare_benchmark_adapter_plan
from .command_safety import interpreter_execution_issues
from .config import ExecutionConfig, PaperGradeConfig
from .llm import LLM
from .llm_trace import complete_with_purpose_detail, record_validation_result
from .literature_context import retrieve_chunks
from .models import ExperimentCommand, ExperimentPlan, ExperimentResult, LiteratureContext, ResearchIdea, ResearchPlan


EXPERIMENT_RUNBOOK_JSON = "04-experiment-runbook.json"
EXPERIMENT_RUNBOOK_MD = "04-experiment-runbook.md"
ENVIRONMENT_SNAPSHOT_JSON = "04-environment-snapshot.json"
ENVIRONMENT_SNAPSHOT_MD = "04-environment-snapshot.md"
_SHELL_META_PATTERN = re.compile(r"[;&|<>`$]|\r|\n")
_PACKAGE_VERSION_NAMES = ["research-agent", "pip", "setuptools", "wheel", "pytest", "requests", "numpy", "pandas", "scipy", "matplotlib"]
MAX_EXECUTION_TIMEOUT_SECONDS = 3600
MAX_EXECUTION_REPEATS = 100
MAX_OUTPUT_BYTES = 10 * 1024 * 1024


def plan_experiment(
    idea: ResearchIdea,
    context: LiteratureContext | None = None,
    llm: LLM | None = None,
    research_plan: ResearchPlan | None = None,
    review_feedback: str = "",
    manager_constraints: str = "",
) -> ExperimentPlan:
    if llm is not None:
        ai_plan = _try_ai_plan(idea, context, llm, research_plan, review_feedback, manager_constraints)
        if ai_plan is not None:
            return ai_plan
    return _fallback_plan(idea, context, research_plan, review_feedback, manager_constraints)


def render_experiment_plan_markdown(plan: ExperimentPlan) -> str:
    lines = [
        f"# 实验计划：{plan.idea_title}",
        "",
        f"**实验模板：** {plan.template_profile}",
        "",
        f"**目标：** {plan.objective}",
        "",
        f"**Baseline：** {plan.baseline or '待人工确认'}",
        "",
        f"**文献依据：** {', '.join(plan.evidence_keys) if plan.evidence_keys else '待人工补充'}",
        "",
        f"**Agent Roles：** {', '.join(plan.agent_roles) if plan.agent_roles else '待任务分配'}",
        "",
    ]
    if plan.rationale:
        lines.extend(["## 设计理由", plan.rationale, ""])
    lines.extend(["## 变量"])
    lines.extend(f"- {item}" for item in plan.variables)
    lines.extend(["", "## 指标"])
    lines.extend(f"- {item}" for item in plan.metrics)
    lines.extend(["", "## 协议"])
    lines.extend(f"{index}. {item}" for index, item in enumerate(plan.protocol, start=1))
    lines.extend(["", "## 执行命令"])
    for command in plan.commands:
        lines.append(f"- `{command.name}`: `{' '.join(command.command)}`")
    return "\n".join(lines)


def _fallback_plan(
    idea: ResearchIdea,
    context: LiteratureContext | None,
    research_plan: ResearchPlan | None = None,
    review_feedback: str = "",
    manager_constraints: str = "",
) -> ExperimentPlan:
    metrics = _metric_candidates(idea, research_plan)
    evidence_keys = list(idea.evidence_keys)
    if not evidence_keys and context is not None:
        evidence_keys = [chunk.citation_key for chunk in retrieve_chunks(context, idea.title + " " + idea.hypothesis, top_k=3)]
    baseline = _select_baseline(idea.baseline, research_plan)
    benchmark = "；".join(research_plan.benchmarks[:3]) if research_plan and research_plan.benchmarks else "代表性任务集"
    template_profile = _template_profile(research_plan)
    protocol = idea.experiment_sketch or [
        "构建覆盖典型成功、失败和边界条件的任务集。",
        "分别运行候选方案、baseline 和关键消融版本。",
        "记录核心指标、失败案例和运行成本。",
        "对每个设置进行重复试验并报告均值、方差和异常样本。",
    ]
    if review_feedback.strip():
        protocol = [*protocol, f"落实人工审核意见：{_short_text(review_feedback, 220)}"]
    if manager_constraints.strip():
        protocol = [*protocol, f"落实 experiment manager 约束：{_short_text(manager_constraints, 260)}"]
    rationale = "实验计划由文献约束 idea 自动生成；真实研究时应替换为领域脚本和公开 benchmark。"
    if review_feedback.strip():
        rationale += " 已纳入人工审核反馈作为额外约束。"
    if manager_constraints.strip():
        rationale += " 已纳入 experiment manager 的分支管理与执行策略约束。"
    return ExperimentPlan(
        idea_title=idea.title,
        objective=f"在 {benchmark} 上评估“{idea.hypothesis}”是否成立。",
        variables=[
            f"方法条件：候选方案 vs {baseline}",
            "任务难度或场景复杂度",
            "关键消融：移除候选方案的核心机制",
        ],
        metrics=metrics,
        protocol=protocol,
        commands=_safe_simulation_commands(template_profile),
        rationale=rationale,
        baseline=baseline,
        evidence_keys=evidence_keys[:5],
        template_profile=template_profile,
        agent_roles=idea.agent_roles[:5],
    )


def _try_ai_plan(
    idea: ResearchIdea,
    context: LiteratureContext | None,
    llm: LLM,
    research_plan: ResearchPlan | None,
    review_feedback: str,
    manager_constraints: str,
) -> ExperimentPlan | None:
    raw, call_id = complete_with_purpose_detail(
        llm,
        "Experiment planning. You design safe, reproducible scientific experiments. Return only valid JSON in Chinese.",
        _plan_prompt(idea, context, research_plan, review_feedback, manager_constraints),
        stage="experiment_planning",
        purpose="experiment planning",
        requires_validation=True,
    )
    data = _parse_json(raw)
    if not isinstance(data, dict):
        record_validation_result(llm, stage="experiment_planning", valid=False, error="response is not a JSON object", call_id=call_id)
        return None
    objective = str(data.get("objective") or "").strip()
    variables = _as_str_list(data.get("variables"))
    metrics = _as_str_list(data.get("metrics"))
    protocol = _as_str_list(data.get("protocol"))
    if not objective or len(variables) < 2 or len(metrics) < 2 or len(protocol) < 3:
        record_validation_result(llm, stage="experiment_planning", valid=False, error="experiment plan schema is incomplete", call_id=call_id)
        return None
    record_validation_result(llm, stage="experiment_planning", valid=True, call_id=call_id)
    template_profile = _template_profile(research_plan)
    return ExperimentPlan(
        idea_title=idea.title,
        objective=objective,
        variables=variables[:8],
        metrics=metrics[:8],
        protocol=protocol[:8],
        commands=_safe_simulation_commands(template_profile),
        rationale=str(data.get("rationale") or "").strip(),
        baseline=_select_baseline(str(data.get("baseline") or idea.baseline or "").strip(), research_plan),
        evidence_keys=_as_str_list(data.get("evidence_keys"))[:5] or idea.evidence_keys[:5],
        template_profile=template_profile,
        agent_roles=_agent_roles(data, idea),
    )


def _plan_prompt(
    idea: ResearchIdea,
    context: LiteratureContext | None,
    research_plan: ResearchPlan | None,
    review_feedback: str = "",
    manager_constraints: str = "",
) -> str:
    schema = {
        "objective": "一个可检验实验目标",
        "variables": ["自变量/控制变量，至少2项"],
        "metrics": ["可量化指标，至少2项，建议英文 snake_case 或清晰中文短语"],
        "protocol": ["实验步骤，至少3步"],
        "baseline": "最直接可比较 baseline",
        "rationale": "为什么这个实验能验证 hypothesis",
        "evidence_keys": ["来自 idea 或上下文的 citation key"],
        "agent_roles": ["负责实验设计/执行复核的 agent_id"],
    }
    lines = [
        f"Idea 标题：{idea.title}",
        f"假设：{idea.hypothesis}",
        f"机制：{idea.mechanism}",
        f"预期贡献：{idea.expected_contribution}",
        f"文献依据：{json.dumps(idea.evidence_keys, ensure_ascii=False)}",
        f"证据 chunks：{json.dumps(idea.evidence_chunks, ensure_ascii=False)}",
        f"对齐空白：{idea.gap_alignment}",
        f"建议 baseline：{idea.baseline}",
        f"负责智能体：{json.dumps(idea.agent_roles, ensure_ascii=False)}",
        "请生成领域相关、可复现、可量化的实验计划。不要生成真实 shell 命令，执行命令由系统安全模拟器统一提供。",
    ]
    if review_feedback.strip():
        lines.extend(
            [
                "人工审核反馈/额外约束：",
                review_feedback.strip(),
                "实验计划必须响应该反馈，尤其是补充 baseline、公平比较、排除弱文献或收窄实验范围的要求。",
            ]
        )
    if manager_constraints.strip():
        lines.extend(
            [
                "Experiment manager 分支/执行策略约束：",
                manager_constraints.strip(),
                "实验计划必须落实这些约束；如果要求 smoke-first、保守 claim 或特定 baseline，必须体现在 objective、metrics、protocol 和 rationale 中。",
            ]
        )
    if research_plan is not None:
        lines.extend(
            [
                "前置研究计划：",
                json.dumps(
                    {
                        "domain": research_plan.domain,
                        "objective": research_plan.objective,
                        "benchmarks": research_plan.benchmarks,
                        "baselines": research_plan.baselines,
                        "metrics": research_plan.metrics,
                        "constraints": research_plan.constraints,
                        "success_criteria": research_plan.success_criteria,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    if context is not None:
        chunks = retrieve_chunks(context, idea.title + " " + idea.hypothesis + " " + idea.mechanism, top_k=5)
        lines.extend(
            [
                "相关文献 chunks：",
                json.dumps(
                    [
                        {
                            "chunk_id": chunk.chunk_id,
                            "citation_key": chunk.citation_key,
                            "title": chunk.title,
                            "text": _short_text(chunk.text, 360),
                        }
                        for chunk in chunks
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
            ]
        )
    lines.extend(["输出严格 JSON，不要 Markdown，不要代码块。Schema：", json.dumps(schema, ensure_ascii=False, indent=2)])
    return "\n".join(lines)


def validate_execution_config(config: ExecutionConfig) -> None:
    if config.timeout_seconds < 1 or config.timeout_seconds > MAX_EXECUTION_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_EXECUTION_TIMEOUT_SECONDS}")
    if config.repeats < 1 or config.repeats > MAX_EXECUTION_REPEATS:
        raise ValueError(f"repeats must be between 1 and {MAX_EXECUTION_REPEATS}")
    if config.max_output_bytes < 1 or config.max_output_bytes > MAX_OUTPUT_BYTES:
        raise ValueError(f"max_output_bytes must be between 1 and {MAX_OUTPUT_BYTES}")


def run_experiments(
    plan: ExperimentPlan,
    config: ExecutionConfig,
    run_dir: Path,
    paper_grade: PaperGradeConfig | None = None,
    base_dir: Path | None = None,
    contract_digest: str = "",
) -> list[ExperimentResult]:
    validate_execution_config(config)
    experiment_dir = run_dir / "experiments"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    _write_template_manifest(plan, experiment_dir)
    execution_plan = plan
    if config.mode == "benchmark":
        execution_plan, adapter_report = prepare_benchmark_adapter_plan(plan, config, run_dir, base_dir=base_dir or Path.cwd(), paper_grade=paper_grade)
        if adapter_report.blocking_issues:
            raise ValueError("Benchmark adapter configuration is blocked: " + "；".join(adapter_report.blocking_issues))
    repeats = max(1, int(config.repeats))
    if config.mode == "simulated":
        results = [
            _simulate_result(execution_plan, command, experiment_dir, repeat_index, simulated_offsets=config.simulated_offsets)
            for command in execution_plan.commands
            for repeat_index in range(repeats)
        ]
    elif config.mode in {"local", "benchmark"}:
        _ensure_local_simulator(experiment_dir, plan.template_profile)
        results = [
            _run_local(command, config, experiment_dir, repeat_index, seed_namespace=execution_plan.idea_title)
            for command in execution_plan.commands
            for repeat_index in range(repeats)
        ]
    else:
        raise ValueError(f"Unsupported execution mode: {config.mode}")
    _write_results_csv(run_dir / "04-results.csv", results)
    write_experiment_runbook(execution_plan, config, run_dir, results, contract_digest=contract_digest)
    return results


def _simulate_result(
    plan: ExperimentPlan,
    command: ExperimentCommand,
    experiment_dir: Path,
    repeat_index: int,
    simulated_offsets: dict[str, float] | None = None,
) -> ExperimentResult:
    started = time.monotonic()
    seed = _repeat_seed(plan.idea_title, repeat_index)
    command_entropy = hashlib.sha256(f"{command.name}:{seed}".encode("utf-8")).hexdigest()
    base = int(command_entropy[:8], 16) / 0xFFFFFFFF
    mode = _command_mode(command.name)
    metrics = _simulated_metrics(plan.metrics, base, mode, plan.template_profile, simulated_offsets)
    artifact_path = experiment_dir / f"{command.name}_repeat_{repeat_index + 1:02d}_metrics.txt"
    artifact_path.write_text(str(metrics) + "\n", encoding="utf-8")
    return ExperimentResult(
        name=command.name,
        status="simulated",
        metrics=metrics,
        artifacts=[str(artifact_path.relative_to(experiment_dir.parent))],
        stdout="模拟实验已完成",
        repeat_index=repeat_index,
        seed=seed[:12],
        command=command.command,
        returncode=0,
        duration_seconds=round(time.monotonic() - started, 3),
        comparison_group=command.comparison_group or "default",
        adapter_id=command.adapter_id or command.name,
        artifact_records=[_artifact_record(artifact_path, experiment_dir.parent)],
    )


def _run_local(
    command: ExperimentCommand,
    config: ExecutionConfig,
    experiment_dir: Path,
    repeat_index: int,
    *,
    seed_namespace: str = "",
) -> ExperimentResult:
    if not command.command:
        raise ValueError(f"Experiment command '{command.name}' is empty")
    seed = _repeat_seed(seed_namespace, repeat_index)
    validation_issues = _validate_local_command(command, config, experiment_dir)
    if validation_issues:
        return ExperimentResult(
            name=command.name,
            status="blocked",
            metrics={},
            artifacts=[],
            stderr="；".join(validation_issues),
            repeat_index=repeat_index,
            seed=seed,
            command=command.command,
            validation_issues=validation_issues,
            comparison_group=command.comparison_group or "default",
            adapter_id=command.adapter_id or command.name,
        )
    started = time.monotonic()
    _remove_expected_outputs(command, experiment_dir)
    max_output_bytes = max(1, min(int(config.max_output_bytes), MAX_OUTPUT_BYTES))
    process = subprocess.Popen(
        command.command,
        cwd=experiment_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
        env=_minimal_subprocess_env(seed, repeat_index),
    )
    stdout_buffer, stdout_thread = _start_bounded_drain(process.stdout, max_output_bytes)
    stderr_buffer, stderr_thread = _start_bounded_drain(process.stderr, max_output_bytes)
    try:
        returncode = process.wait(timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        stdout = _finish_bounded_drain(process.stdout, stdout_thread, stdout_buffer)
        stderr = _finish_bounded_drain(process.stderr, stderr_thread, stderr_buffer)
        duration = round(time.monotonic() - started, 3)
        artifacts, artifact_records = _snapshot_command_artifacts(command, experiment_dir, repeat_index)
        timeout_message = f"命令超过 {config.timeout_seconds}s 超时限制，已终止整个进程组。"
        return ExperimentResult(
            name=command.name,
            status="timeout",
            metrics={},
            artifacts=artifacts,
            stdout=stdout,
            stderr=(stderr + "\n" + timeout_message).strip(),
            repeat_index=repeat_index,
            seed=seed,
            command=command.command,
            returncode=None,
            duration_seconds=duration,
            comparison_group=command.comparison_group or "default",
            adapter_id=command.adapter_id or command.name,
            artifact_records=artifact_records,
        )
    _terminate_remaining_process_group(process.pid)
    stdout = _finish_bounded_drain(process.stdout, stdout_thread, stdout_buffer)
    stderr = _finish_bounded_drain(process.stderr, stderr_thread, stderr_buffer)
    duration = round(time.monotonic() - started, 3)
    status = "passed" if returncode == 0 else "failed"
    metrics = _read_expected_metrics(command, experiment_dir)
    artifacts, artifact_records = _snapshot_command_artifacts(command, experiment_dir, repeat_index)
    return ExperimentResult(
        name=command.name,
        status=status,
        metrics=metrics,
        artifacts=artifacts,
        stdout=stdout,
        stderr=stderr,
        repeat_index=repeat_index,
        seed=seed,
        command=command.command,
        returncode=returncode,
        duration_seconds=duration,
        comparison_group=command.comparison_group or "default",
        adapter_id=command.adapter_id or command.name,
        artifact_records=artifact_records,
    )


def write_experiment_runbook(
    plan: ExperimentPlan,
    config: ExecutionConfig,
    run_dir: Path,
    results: list[ExperimentResult],
    contract_digest: str = "",
) -> dict[str, Any]:
    experiment_dir = run_dir / "experiments"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    runbook = build_experiment_runbook(plan, config, run_dir, results)
    if contract_digest:
        # T05：执行启动时绑定契约内容摘要；事后改契约产生新版本，旧摘要失效。
        runbook["contract_binding"] = {"contract_digest": str(contract_digest), "bound_at": _utc_now()}
    environment = runbook.get("environment", {}) if isinstance(runbook.get("environment"), dict) else {}
    write_json(run_dir / EXPERIMENT_RUNBOOK_JSON, runbook)
    write_text(run_dir / EXPERIMENT_RUNBOOK_MD, render_experiment_runbook_markdown(runbook))
    write_json(run_dir / ENVIRONMENT_SNAPSHOT_JSON, environment)
    write_text(run_dir / ENVIRONMENT_SNAPSHOT_MD, render_environment_snapshot_markdown(environment))
    return runbook


def build_experiment_runbook(
    plan: ExperimentPlan,
    config: ExecutionConfig,
    run_dir: Path,
    results: list[ExperimentResult],
) -> dict[str, Any]:
    experiment_dir = run_dir / "experiments"
    environment = _environment_snapshot(config, run_dir)
    command_lookup = {command.name: command for command in plan.commands}
    command_records = [
        {
            "name": command.name,
            "role": command.role,
            "comparison_group": command.comparison_group or "default",
            "adapter_id": command.adapter_id or command.name,
            "command": command.command,
            "expected_artifacts": command.expected_artifacts,
            "validation_issues": _validate_local_command(command, config, experiment_dir) if config.mode in {"local", "benchmark"} else [],
        }
        for command in plan.commands
    ]
    runs: list[dict[str, Any]] = []
    result_counts = {name: sum(1 for item in results if item.name == name) for name in {item.name for item in results}}
    for result in results:
        command = command_lookup.get(result.name)
        expected_artifacts = command.expected_artifacts if command is not None else []
        artifact_inputs = _unique([*result.artifacts, *expected_artifacts])
        produced_artifacts = list(result.artifact_records or _artifact_records(run_dir, experiment_dir, artifact_inputs))
        if result_counts.get(result.name) == 1 and result.artifact_records:
            existing_paths = {str(item.get("path") or "") for item in produced_artifacts if isinstance(item, dict)}
            produced_artifacts.extend(
                item for item in _artifact_records(run_dir, experiment_dir, artifact_inputs) if str(item.get("path") or "") not in existing_paths
            )
        runs.append(
            {
                "name": result.name,
                "role": command.role if command is not None else "",
                "comparison_group": result.comparison_group or (command.comparison_group if command is not None else "") or "default",
                "adapter_id": result.adapter_id or (command.adapter_id if command is not None else "") or result.name,
                "repeat_index": result.repeat_index,
                "seed": result.seed,
                "status": result.status,
                "command": result.command or (command.command if command is not None else []),
                "returncode": result.returncode,
                "duration_seconds": result.duration_seconds,
                "metrics": result.metrics,
                "expected_artifacts": expected_artifacts,
                "produced_artifacts": produced_artifacts,
                "stdout_tail": result.stdout,
                "stderr_tail": result.stderr,
                "validation_issues": result.validation_issues,
            }
        )
    runbook = {
        "schema_version": 1,
        "plan": {
            "idea_title": plan.idea_title,
            "objective": plan.objective,
            "baseline": plan.baseline,
            "template_profile": plan.template_profile,
            "metrics": plan.metrics,
            "evidence_keys": plan.evidence_keys,
        },
        "execution": {
            "mode": config.mode,
            "timeout_seconds": config.timeout_seconds,
            "allowed_commands": config.allowed_commands,
            "repeats": max(1, int(config.repeats)),
            "max_output_bytes": config.max_output_bytes,
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "working_directory": "experiments/",
            "env_policy": "minimal",
            "process_isolation": "new_session_process_group",
            "network_isolation": False,
            "env_keys": ["PATH", "PYTHONHASHSEED", "PYTHONIOENCODING", "LC_ALL", "LANG", "RESEARCH_AGENT_SEED", "RESEARCH_AGENT_REPEAT_INDEX"],
            "environment_snapshot": ENVIRONMENT_SNAPSHOT_JSON,
        },
        "environment": environment,
        "commands": command_records,
        "runs": runs,
        "artifacts": _experiment_artifact_inventory(run_dir, experiment_dir),
        "warnings": _runbook_warnings(config, command_lookup, experiment_dir, results),
    }
    for command in command_records:
        command["allowed"] = not command["validation_issues"]
    return runbook


def render_experiment_runbook_markdown(runbook: dict[str, Any]) -> str:
    execution = runbook.get("execution", {})
    plan = runbook.get("plan", {})
    environment = runbook.get("environment", {}) if isinstance(runbook.get("environment"), dict) else {}
    source_tree = environment.get("source_tree", {}) if isinstance(environment.get("source_tree"), dict) else {}
    lines = [
        "# 实验运行手册",
        "",
        f"- Idea：{plan.get('idea_title') or '-'}",
        f"- 执行模式：{execution.get('mode') or '-'}",
        f"- 工作目录：{execution.get('working_directory') or '-'}",
        f"- 重复次数：{execution.get('repeats') or '-'}",
        f"- 超时限制：{execution.get('timeout_seconds') or '-'}s",
        f"- Python：{execution.get('python_version') or '-'}",
        f"- Python executable：{execution.get('python_executable') or '-'}",
        f"- 平台：{execution.get('platform') or '-'}",
        f"- 环境快照：{execution.get('environment_snapshot') or '-'}",
        f"- 代码快照：{source_tree.get('aggregate_sha256') or '-'}",
        f"- 代码文件数：{source_tree.get('file_count') or 0}",
        "",
        "## 命令矩阵",
        "| 名称 | 命令 | 预期产物 | 校验 |",
        "| --- | --- | --- | --- |",
    ]
    for command in runbook.get("commands", []):
        issues = command.get("validation_issues") or []
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(command.get("name") or "")),
                    _cell(" ".join(command.get("command") or [])),
                    _cell(", ".join(command.get("expected_artifacts") or []) or "-"),
                    _cell("通过" if not issues else "阻断：" + "；".join(str(item) for item in issues)),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Repeat 记录", "| 名称 | repeat | seed | 状态 | returncode | 耗时 | 指标 |", "| --- | ---: | --- | --- | ---: | ---: | --- |"])
    for run in runbook.get("runs", []):
        metrics = run.get("metrics") or {}
        metric_text = ", ".join(f"{key}={value}" for key, value in metrics.items()) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(run.get("name") or "")),
                    str(run.get("repeat_index", "")),
                    _cell(str(run.get("seed") or "")),
                    _cell(str(run.get("status") or "")),
                    _cell(str(run.get("returncode")) if run.get("returncode") is not None else "-"),
                    str(run.get("duration_seconds") or 0),
                    _cell(metric_text),
                ]
            )
            + " |"
        )
    warnings = runbook.get("warnings") or []
    if warnings:
        lines.extend(["", "## 警告"])
        lines.extend(f"- {item}" for item in warnings)
    lines.extend(["", "## 产物清单", "| 文件 | 大小 | SHA256 |", "| --- | ---: | --- |"])
    for artifact in runbook.get("artifacts", []):
        lines.append(f"| {_cell(str(artifact.get('path') or ''))} | {artifact.get('bytes') or 0} | `{artifact.get('sha256') or ''}` |")
    lines.extend(
        [
            "",
            "## 复现入口",
            "1. 使用相同代码快照、Python executable、平台和环境快照。",
            "2. 进入本 run 的 `experiments/` 工作目录。",
            "3. 按命令矩阵逐条执行命令，并使用 Repeat 记录中的 seed 对照产物。",
        ]
    )
    return "\n".join(lines)


def render_environment_snapshot_markdown(snapshot: dict[str, Any]) -> str:
    python_info = snapshot.get("python", {}) if isinstance(snapshot.get("python"), dict) else {}
    system_info = snapshot.get("system", {}) if isinstance(snapshot.get("system"), dict) else {}
    execution_policy = snapshot.get("execution_policy", {}) if isinstance(snapshot.get("execution_policy"), dict) else {}
    project = snapshot.get("project", {}) if isinstance(snapshot.get("project"), dict) else {}
    source_tree = snapshot.get("source_tree", {}) if isinstance(snapshot.get("source_tree"), dict) else {}
    packages = snapshot.get("package_versions", []) if isinstance(snapshot.get("package_versions"), list) else []
    tools = snapshot.get("tool_versions", []) if isinstance(snapshot.get("tool_versions"), list) else []
    lines = [
        "# 实验环境快照",
        "",
        f"- 状态：{snapshot.get('status') or '-'}",
        f"- Python：{python_info.get('version') or '-'} ({python_info.get('implementation') or '-'})",
        f"- Python executable：{python_info.get('executable') or '-'}",
        f"- 平台：{system_info.get('platform') or '-'}",
        f"- 工作目录：{system_info.get('working_directory') or '-'}",
        f"- Run 目录：{system_info.get('run_directory') or '-'}",
        f"- 执行模式：{execution_policy.get('mode') or '-'}",
        f"- 子进程环境策略：{execution_policy.get('env_policy') or '-'}",
        "",
        "## 项目元数据",
        f"- 名称：{project.get('name') or '-'}",
        f"- 版本：{project.get('version') or '-'}",
        f"- Python 要求：{project.get('requires_python') or '-'}",
        f"- 依赖：{', '.join(project.get('dependencies') or []) or '-'}",
        "",
        "## 包版本",
        "| 包 | 版本 |",
        "| --- | --- |",
    ]
    if packages:
        for item in packages:
            if not isinstance(item, dict):
                continue
            lines.append(f"| {_cell(str(item.get('name') or ''))} | {_cell(str(item.get('version') or ''))} |")
    else:
        lines.append("| - | - |")
    lines.extend(["", "## 工具路径", "| 命令 | 可用 | 路径 |", "| --- | --- | --- |"])
    if tools:
        for item in tools:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("command") or "")),
                        "是" if item.get("available") else "否",
                        _cell(str(item.get("path") or "-")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - |")
    lines.extend(
        [
            "",
            "## 代码快照",
            f"- 根目录：{source_tree.get('root') or '-'}",
            f"- 文件数：{source_tree.get('file_count') or 0}",
            f"- 聚合 SHA256：`{source_tree.get('aggregate_sha256') or ''}`",
            "",
            "| 文件 | 大小 | SHA256 |",
            "| --- | ---: | --- |",
        ]
    )
    files = source_tree.get("files", []) if isinstance(source_tree.get("files"), list) else []
    if files:
        for item in files:
            if not isinstance(item, dict):
                continue
            lines.append(f"| {_cell(str(item.get('path') or ''))} | {item.get('bytes') or 0} | `{item.get('sha256') or ''}` |")
    else:
        lines.append("| - | 0 | - |")
    warnings = snapshot.get("warnings") or []
    if warnings:
        lines.extend(["", "## 警告"])
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines)


def _environment_snapshot(config: ExecutionConfig, run_dir: Path) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    source_tree = _source_tree_snapshot(repo_root)
    packages = _package_versions()
    tool_versions = _tool_versions(config.allowed_commands)
    warnings = _environment_warnings(source_tree, packages, tool_versions)
    return {
        "schema_version": 1,
        "status": "complete" if not warnings else "partial",
        "python": {
            "version": sys.version.split()[0],
            "full_version": sys.version,
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "working_directory": str(Path.cwd()),
            "run_directory": str(run_dir.resolve()),
        },
        "execution_policy": {
            "mode": config.mode,
            "timeout_seconds": config.timeout_seconds,
            "allowed_commands": list(config.allowed_commands),
            "repeats": max(1, int(config.repeats)),
            "env_policy": "minimal",
            "env_keys": ["PATH", "PYTHONHASHSEED", "PYTHONIOENCODING", "LC_ALL", "LANG", "RESEARCH_AGENT_SEED", "RESEARCH_AGENT_REPEAT_INDEX"],
            "tracked_env": {
                "PYTHONIOENCODING": "utf-8",
                "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                "PYTHONHASHSEED": "per-repeat deterministic hash",
            },
        },
        "project": _project_metadata(repo_root),
        "package_versions": packages,
        "tool_versions": tool_versions,
        "source_tree": source_tree,
        "warnings": warnings,
    }


def _project_metadata(repo_root: Path) -> dict[str, Any]:
    pyproject = repo_root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"name": "", "version": "", "requires_python": "", "dependencies": []}
    project = data.get("project", {}) if isinstance(data.get("project"), dict) else {}
    dependencies = project.get("dependencies") if isinstance(project.get("dependencies"), list) else []
    return {
        "name": str(project.get("name") or ""),
        "version": str(project.get("version") or ""),
        "requires_python": str(project.get("requires-python") or ""),
        "dependencies": [str(item) for item in dependencies],
    }


def _package_versions() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for name in _PACKAGE_VERSION_NAMES:
        try:
            version = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            continue
        records.append({"name": name, "version": version})
    return records


def _tool_versions(allowed_commands: list[str]) -> list[dict[str, Any]]:
    commands = _unique(["python3", sys.executable, *allowed_commands])
    records: list[dict[str, Any]] = []
    for command in commands:
        if not command:
            continue
        path = command if Path(command).exists() else shutil.which(command)
        records.append({"command": command, "available": bool(path), "path": path or ""})
    return records


def _source_tree_snapshot(repo_root: Path) -> dict[str, Any]:
    paths: list[Path] = []
    for rel in ["pyproject.toml", "README.md"]:
        path = repo_root / rel
        if path.is_file():
            paths.append(path)
    package_dir = repo_root / "src" / "research_agent"
    if package_dir.exists():
        paths.extend(sorted(package_dir.glob("*.py")))
    files: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for path in sorted(set(paths)):
        try:
            data = path.read_bytes()
            rel = str(path.relative_to(repo_root))
        except OSError:
            continue
        digest = hashlib.sha256(data).hexdigest()
        files.append({"path": rel, "bytes": len(data), "sha256": digest})
        aggregate.update(rel.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\0")
    return {
        "root": str(repo_root),
        "file_count": len(files),
        "aggregate_sha256": aggregate.hexdigest() if files else "",
        "files": files,
    }


def _environment_warnings(source_tree: dict[str, Any], packages: list[dict[str, str]], tools: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if not source_tree.get("files"):
        warnings.append("未能记录源码快照，复现时无法核对代码版本。")
    if not packages:
        warnings.append("未检测到 Python 包版本记录，建议归档 requirements/lockfile。")
    missing_tools = [str(item.get("command")) for item in tools if isinstance(item, dict) and not item.get("available")]
    if missing_tools:
        warnings.append("部分白名单命令当前不可定位：" + "、".join(missing_tools[:5]))
    return warnings


def validate_experiment_command(command: ExperimentCommand, config: ExecutionConfig, experiment_dir: Path) -> list[str]:
    return _validate_local_command(command, config, experiment_dir)


def _validate_local_command(command: ExperimentCommand, config: ExecutionConfig, experiment_dir: Path) -> list[str]:
    if not command.command:
        return [f"命令 '{command.name}' 为空"]
    issues: list[str] = []
    executable = str(command.command[0]).strip()
    if executable not in config.allowed_commands:
        issues.append(f"命令 '{executable}' 不在 allowed_commands 白名单中")
    issues.extend(interpreter_execution_issues(command.command))
    for index, part in enumerate(command.command):
        token = str(part)
        if not token.strip():
            issues.append(f"命令参数 #{index} 为空")
            continue
        if _SHELL_META_PATTERN.search(token):
            issues.append(f"命令参数 #{index} 含 shell 元字符：{token}")
        if _is_path_like_token(token) and not _is_safe_relative_path(token, experiment_dir):
            issues.append(f"命令路径参数必须是 experiments/ 内的相对路径：{token}")
    return issues


def _is_path_like_token(token: str) -> bool:
    if token.startswith("-"):
        return False
    return "/" in token or "\\" in token or Path(token).suffix in {".py", ".json", ".csv", ".txt", ".sh", ".yaml", ".yml"}


def _is_safe_relative_path(token: str, experiment_dir: Path) -> bool:
    path = Path(token)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        return False
    try:
        resolved = (experiment_dir / path).resolve()
        resolved.relative_to(experiment_dir.resolve())
    except (OSError, ValueError):
        return False
    return True


def _minimal_subprocess_env(seed: str, repeat_index: int) -> dict[str, str]:
    hash_seed = str(int(seed[:8], 16))
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONHASHSEED": hash_seed,
        "PYTHONIOENCODING": "utf-8",
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "RESEARCH_AGENT_SEED": seed,
        "RESEARCH_AGENT_REPEAT_INDEX": str(repeat_index),
    }


def _repeat_seed(namespace: str, repeat_index: int) -> str:
    return hashlib.sha256(f"{namespace.strip()}:{repeat_index}".encode("utf-8")).hexdigest()[:12]


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


def _start_bounded_drain(stream: Any, limit: int) -> tuple[bytearray, threading.Thread]:
    buffer = bytearray()

    def drain() -> None:
        try:
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    return
                if len(chunk) >= limit:
                    buffer[:] = chunk[-limit:]
                else:
                    buffer.extend(chunk)
                    overflow = len(buffer) - limit
                    if overflow > 0:
                        del buffer[:overflow]
        except (OSError, ValueError):
            return

    thread = threading.Thread(target=drain, name="research-agent-output-drain", daemon=True)
    thread.start()
    return buffer, thread


def _finish_bounded_drain(stream: Any, thread: threading.Thread, buffer: bytearray) -> str:
    thread.join(timeout=2)
    if stream is not None:
        try:
            stream.close()
        except (OSError, ValueError):
            pass
    if thread.is_alive():
        thread.join(timeout=1)
    return bytes(buffer).decode("utf-8", errors="replace")


def _terminate_remaining_process_group(pid: int) -> None:
    if os.name != "posix":
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _remove_expected_outputs(command: ExperimentCommand, experiment_dir: Path) -> None:
    for value in command.expected_artifacts:
        path = _resolve_artifact_reference(experiment_dir.parent, experiment_dir, value)
        if path is None:
            continue
        if path.is_file() or path.is_symlink():
            path.unlink()


def _snapshot_command_artifacts(
    command: ExperimentCommand,
    experiment_dir: Path,
    repeat_index: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", command.name).strip("-.") or "command"
    snapshot_root = experiment_dir / "repeat-artifacts" / safe_name / f"repeat-{repeat_index + 1:03d}"
    if snapshot_root.exists():
        shutil.rmtree(snapshot_root)
    artifacts: list[str] = []
    records: list[dict[str, Any]] = []
    for value in command.expected_artifacts:
        source = _resolve_artifact_reference(experiment_dir.parent, experiment_dir, value)
        if source is None or not source.is_file():
            continue
        relative_source = source.resolve().relative_to(experiment_dir.resolve())
        destination = snapshot_root / relative_source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        record = _artifact_record(destination, experiment_dir.parent)
        artifacts.append(record["path"])
        records.append(record)
    return artifacts, records


def _artifact_records(run_dir: Path, experiment_dir: Path, paths: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in paths:
        path = _resolve_artifact_reference(run_dir, experiment_dir, value)
        if path is None or not path.is_file():
            continue
        rel = str(path.resolve().relative_to(run_dir.resolve()))
        if rel in seen:
            continue
        seen.add(rel)
        records.append(_artifact_record(path, run_dir))
    return records


def _experiment_artifact_paths(experiment_dir: Path) -> list[str]:
    if not experiment_dir.exists():
        return []
    return [
        str(path.relative_to(experiment_dir))
        for path in sorted(item for item in experiment_dir.rglob("*") if item.is_file())
    ]


def _command_artifact_paths(command: ExperimentCommand, experiment_dir: Path) -> list[str]:
    paths = [*command.expected_artifacts]
    for token in command.command:
        if _is_path_like_token(str(token)):
            paths.append(str(token))
    artifacts: list[str] = []
    seen: set[str] = set()
    for value in paths:
        path = _resolve_artifact_reference(experiment_dir.parent, experiment_dir, value)
        if path is None or not path.is_file():
            continue
        rel = str(path.resolve().relative_to(experiment_dir.resolve()))
        if rel in seen:
            continue
        seen.add(rel)
        artifacts.append(rel)
    return artifacts


def _experiment_artifact_inventory(run_dir: Path, experiment_dir: Path) -> list[dict[str, Any]]:
    if not experiment_dir.exists():
        return []
    return [_artifact_record(path, run_dir) for path in sorted(item for item in experiment_dir.rglob("*") if item.is_file())]


def _artifact_record(path: Path, run_dir: Path) -> dict[str, Any]:
    resolved = path.resolve()
    data = resolved.read_bytes()
    return {
        "path": str(resolved.relative_to(run_dir.resolve())),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _resolve_artifact_reference(run_dir: Path, experiment_dir: Path, value: str) -> Path | None:
    try:
        ref = Path(str(value))
    except TypeError:
        return None
    if ref.is_absolute() or any(part == ".." for part in ref.parts):
        return None
    path = run_dir / ref if ref.parts and ref.parts[0] == "experiments" else experiment_dir / ref
    try:
        resolved = path.resolve()
        resolved.relative_to(experiment_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _runbook_warnings(
    config: ExecutionConfig,
    command_lookup: dict[str, ExperimentCommand],
    experiment_dir: Path,
    results: list[ExperimentResult],
) -> list[str]:
    warnings: list[str] = []
    if config.mode == "simulated":
        warnings.append("当前为模拟执行器结果，不能替代真实 benchmark 或真实数据集实验。")
    for result in results:
        if result.status in {"blocked", "timeout", "failed"}:
            warnings.append(f"{result.name} repeat {result.repeat_index} 状态为 {result.status}。")
        command = command_lookup.get(result.name)
        if command is None:
            continue
        if command.expected_artifacts and not result.artifact_records:
            warnings.append(f"{result.name} repeat {result.repeat_index} 没有可追踪的 per-repeat 产物快照。")
        for artifact in command.expected_artifacts:
            if not (experiment_dir / artifact).exists():
                warnings.append(f"{result.name} 缺少预期产物：{artifact}")
    return _unique(warnings)


def _tail_text(value: str | bytes | None, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text[-limit:]


def _write_results_csv(path: Path, results: list[ExperimentResult]) -> None:
    metric_names = sorted({metric for result in results for metric in result.metrics})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "status", "repeat_index", "seed", "comparison_group", "adapter_id", *metric_names])
        writer.writeheader()
        for result in results:
            row = {
                "name": result.name,
                "status": result.status,
                "repeat_index": result.repeat_index,
                "seed": result.seed,
                "comparison_group": result.comparison_group,
                "adapter_id": result.adapter_id,
            }
            row.update(result.metrics)
            writer.writerow(row)


def _read_expected_metrics(command: ExperimentCommand, experiment_dir: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for artifact in command.expected_artifacts:
        path = experiment_dir / artifact
        if path.suffix != ".json" or not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if isinstance(value, int | float):
                metrics[key] = float(value)
    return metrics


def _safe_simulation_commands(template_profile: str = "generic") -> list[ExperimentCommand]:
    if template_profile == "robotics_motion_planning":
        return [
            ExperimentCommand(
                name="robotics_candidate_planner",
                command=["python3", "simulate.py", "--profile", "robotics_motion_planning", "--mode", "candidate"],
                expected_artifacts=["candidate_metrics.json"],
            ),
            ExperimentCommand(
                name="robotics_baseline_planner",
                command=["python3", "simulate.py", "--profile", "robotics_motion_planning", "--mode", "baseline"],
                expected_artifacts=["baseline_metrics.json"],
            ),
            ExperimentCommand(
                name="robotics_ablation_planner",
                command=["python3", "simulate.py", "--profile", "robotics_motion_planning", "--mode", "ablation"],
                expected_artifacts=["ablation_metrics.json"],
            ),
        ]
    if template_profile == "bearing_fault_diagnosis":
        return [
            ExperimentCommand(
                name="bearing_candidate_classifier",
                command=["python3", "simulate.py", "--profile", "bearing_fault_diagnosis", "--mode", "candidate"],
                expected_artifacts=["candidate_metrics.json"],
            ),
            ExperimentCommand(
                name="bearing_baseline_classifier",
                command=["python3", "simulate.py", "--profile", "bearing_fault_diagnosis", "--mode", "baseline"],
                expected_artifacts=["baseline_metrics.json"],
            ),
            ExperimentCommand(
                name="bearing_ablation_classifier",
                command=["python3", "simulate.py", "--profile", "bearing_fault_diagnosis", "--mode", "ablation"],
                expected_artifacts=["ablation_metrics.json"],
            ),
        ]
    return [
        ExperimentCommand(
            name="simulate_artifact_pipeline",
            command=["python3", "simulate.py", "--mode", "artifact"],
            expected_artifacts=["artifact_metrics.json"],
        ),
        ExperimentCommand(
            name="simulate_baseline_pipeline",
            command=["python3", "simulate.py", "--mode", "baseline"],
            expected_artifacts=["baseline_metrics.json"],
        ),
        ExperimentCommand(
            name="simulate_ablation_pipeline",
            command=["python3", "simulate.py", "--mode", "ablation"],
            expected_artifacts=["ablation_metrics.json"],
        ),
    ]


def _template_profile(research_plan: ResearchPlan | None) -> str:
    if research_plan is None:
        return "generic"
    if research_plan.domain in {"robotics_motion_planning", "bearing_fault_diagnosis", "ai_research_agents"}:
        return research_plan.domain
    return "generic"


def _write_template_manifest(plan: ExperimentPlan, experiment_dir: Path) -> None:
    manifest = {
        "template_profile": plan.template_profile,
        "idea_title": plan.idea_title,
        "baseline": plan.baseline,
        "metrics": plan.metrics,
        "commands": [
            {"name": command.name, "command": command.command, "expected_artifacts": command.expected_artifacts}
            for command in plan.commands
        ],
    }
    (experiment_dir / "experiment-template.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _select_baseline(candidate: str, research_plan: ResearchPlan | None) -> str:
    value = candidate.strip()
    if value and not _is_generic_baseline(value):
        return value
    if research_plan is not None and research_plan.baselines:
        return " / ".join(research_plan.baselines[:3])
    return value or "最相关 baseline"


def _is_generic_baseline(value: str) -> bool:
    normalized = value.lower()
    generic_markers = [
        "待人工",
        "最相关",
        "传统 baseline",
        "消融版本",
        "现有方法",
        "strong baseline",
        "relevant baseline",
    ]
    return any(marker in normalized for marker in generic_markers)


def _metric_candidates(idea: ResearchIdea, research_plan: ResearchPlan | None = None) -> list[str]:
    metrics = [_metric_name(item) for item in idea.evaluation]
    if research_plan is not None:
        metrics.extend(_metric_name(item) for item in research_plan.metrics)
    metrics = [metric for metric in metrics if metric]
    if len(metrics) >= 2:
        return _unique(metrics[:6])
    return ["success_rate", "quality_score", "runtime_cost", "failure_cases"]


def _metric_name(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_ -]{1,60}", text):
        return re.sub(r"[\s-]+", "_", text.lower())
    return _short_text(text, 24)


def _simulated_metrics(
    metric_names: list[str],
    base: float,
    mode: str,
    template_profile: str = "generic",
    offsets: dict[str, float] | None = None,
) -> dict[str, float]:
    names = _domain_metric_names(metric_names, template_profile)
    # Neutral by default: the deterministic jitter alone decides which command
    # wins. Configured offsets express a per-mode "advantage" applied in the
    # favorable direction for both metric polarities.
    mode_offsets = offsets or {}
    advantage = float(mode_offsets.get(mode, 0.0))
    metrics: dict[str, float] = {}
    for index, metric in enumerate(names):
        local = (base + index * 0.173) % 1.0
        lower_is_better = _lower_is_better(metric)
        if lower_is_better:
            value = (34 - local * 8) - advantage
        else:
            value = (0.68 + local * 0.16) + advantage
        metrics[metric] = round(max(0.0, value), 3)
    return metrics


def _command_mode(name: str) -> str:
    lower = name.lower()
    if "ablation" in lower or "without" in lower or "ablated" in lower:
        return "ablation"
    if "artifact" in lower or "candidate" in lower or "proposed" in lower:
        return "candidate"
    return "baseline"


def _domain_metric_names(metric_names: list[str], template_profile: str) -> list[str]:
    names = list(metric_names)
    defaults = {
        "robotics_motion_planning": [
            "planning_success_rate",
            "planning_time",
            "path_length",
            "collision_rate",
            "trajectory_smoothness",
            "minimum_clearance",
        ],
        "bearing_fault_diagnosis": [
            "accuracy",
            "macro_f1",
            "cross_domain_accuracy",
            "noise_robustness",
            "inference_latency",
        ],
        "ai_research_agents": [
            "citation_precision",
            "unsupported_claims",
            "artifact_completeness",
            "reproduction_success_rate",
            "review_revision_count",
        ],
    }.get(template_profile, ["success_rate", "quality_score", "runtime_cost", "failure_cases"])
    for metric in defaults:
        if metric not in names:
            names.append(metric)
    return names[:8]


def _lower_is_better(metric: str) -> bool:
    lowered = metric.lower()
    tokens = ["time", "cost", "latency", "collision", "failure", "error", "risk", "耗时", "成本", "碰撞", "失败", "误差", "风险"]
    return any(token in lowered for token in tokens)


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\})", text, flags=re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _agent_roles(data: dict[str, Any], idea: ResearchIdea) -> list[str]:
    roles = _as_str_list(data.get("agent_roles") or data.get("assigned_agents")) or list(idea.agent_roles)
    if roles and "method_architect" not in roles:
        roles.insert(0, "method_architect")
    return _unique([role for role in roles if role])[:5]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _short_text(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _ensure_local_simulator(experiment_dir: Path, template_profile: str = "generic") -> None:
    script = experiment_dir / "simulate.py"
    if script.exists():
        return
    script.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import argparse",
                "import json",
                "",
                "",
                "def main() -> None:",
                "    parser = argparse.ArgumentParser()",
                "    parser.add_argument('--profile', default='generic', choices=['generic', 'robotics_motion_planning', 'bearing_fault_diagnosis', 'ai_research_agents'])",
                "    parser.add_argument('--mode', choices=['artifact', 'candidate', 'baseline', 'ablation'], required=True)",
                "    args = parser.parse_args()",
                "    metrics = metrics_for(args.profile, args.mode)",
                "    if args.mode == 'artifact':",
                "        out = 'artifact_metrics.json'",
                "    elif args.mode == 'candidate':",
                "        out = 'candidate_metrics.json'",
                "    elif args.mode == 'ablation':",
                "        out = 'ablation_metrics.json'",
                "    else:",
                "        out = 'baseline_metrics.json'",
                "    with open(out, 'w', encoding='utf-8') as handle:",
                "        json.dump(metrics, handle, indent=2)",
                "        handle.write('\\n')",
                "    print(json.dumps({'profile': args.profile, 'mode': args.mode, 'metrics': metrics}, ensure_ascii=False))",
                "",
                "",
                "def metrics_for(profile: str, mode: str) -> dict[str, float]:",
                "    is_candidate = mode in {'artifact', 'candidate'}",
                "    is_ablation = mode == 'ablation'",
                "    if profile == 'robotics_motion_planning':",
                "        if is_candidate:",
                "            return {",
                "                'planning_success_rate': 0.87,",
                "                'planning_time': 18.4,",
                "                'path_length': 5.8,",
                "                'collision_rate': 0.03,",
                "                'trajectory_smoothness': 0.82,",
                "                'minimum_clearance': 0.18,",
                "            }",
                "        if is_ablation:",
                "            return {",
                "                'planning_success_rate': 0.81,",
                "                'planning_time': 22.3,",
                "                'path_length': 6.2,",
                "                'collision_rate': 0.06,",
                "                'trajectory_smoothness': 0.75,",
                "                'minimum_clearance': 0.14,",
                "            }",
                "        return {",
                "            'planning_success_rate': 0.76,",
                "            'planning_time': 27.6,",
                "            'path_length': 6.7,",
                "            'collision_rate': 0.09,",
                "            'trajectory_smoothness': 0.69,",
                "            'minimum_clearance': 0.11,",
                "        }",
                "    if profile == 'bearing_fault_diagnosis':",
                "        if is_candidate:",
                "            return {",
                "                'accuracy': 0.91,",
                "                'macro_f1': 0.88,",
                "                'cross_domain_accuracy': 0.79,",
                "                'noise_robustness': 0.74,",
                "                'inference_latency': 12.5,",
                "            }",
                "        if is_ablation:",
                "            return {",
                "                'accuracy': 0.87,",
                "                'macro_f1': 0.82,",
                "                'cross_domain_accuracy': 0.71,",
                "                'noise_robustness': 0.64,",
                "                'inference_latency': 15.6,",
                "            }",
                "        return {",
                "            'accuracy': 0.84,",
                "            'macro_f1': 0.78,",
                "            'cross_domain_accuracy': 0.65,",
                "            'noise_robustness': 0.58,",
                "            'inference_latency': 18.2,",
                "        }",
                "    if profile == 'ai_research_agents':",
                "        if is_candidate:",
                "            return {",
                "                'citation_precision': 0.82,",
                "                'unsupported_claims': 2.8,",
                "                'artifact_completeness': 0.9,",
                "                'reproduction_success_rate': 0.84,",
                "                'review_revision_count': 2.0,",
                "            }",
                "        if is_ablation:",
                "            return {",
                "                'citation_precision': 0.72,",
                "                'unsupported_claims': 3.8,",
                "                'artifact_completeness': 0.76,",
                "                'reproduction_success_rate': 0.79,",
                "                'review_revision_count': 3.0,",
                "            }",
                "        return {",
                "            'citation_precision': 0.63,",
                "            'unsupported_claims': 5.2,",
                "            'artifact_completeness': 0.62,",
                "            'reproduction_success_rate': 0.73,",
                "            'review_revision_count': 4.0,",
                "        }",
                "    if is_candidate:",
                "        metrics = {",
                "            'reproduction_success_rate': 0.84,",
                "            'artifact_completeness': 0.9,",
                "            'audit_minutes': 31.5,",
                "            'unsupported_claims': 2.8,",
                "        }",
                "    elif is_ablation:",
                "        metrics = {",
                "            'reproduction_success_rate': 0.79,",
                "            'artifact_completeness': 0.76,",
                "            'audit_minutes': 37.0,",
                "            'unsupported_claims': 3.8,",
                "        }",
                "    else:",
                "        metrics = {",
                "            'reproduction_success_rate': 0.73,",
                "            'artifact_completeness': 0.62,",
                "            'audit_minutes': 44.0,",
                "            'unsupported_claims': 5.2,",
                "        }",
                "    return metrics",
                "",
                "",
                "if __name__ == '__main__':",
                "    main()",
                "",
            ]
        ),
        encoding="utf-8",
    )
