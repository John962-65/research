"""评测运行器：A/B/C 三组 × N 任务的可复现对照（公平预算 + 官方协议评分）。

产物（eval-runs/<stamp>/，gitignore）：
    config.json          模型/预算/任务清单/评分器溯源/沙箱隔离级别（复现台账）
    <group>/<task_id>/answer.json + trace.json + cost.json
    summary.json/.md     组级汇总（官方 accuracy ± CI）+ 组间配对差
    raw/<group>.jsonl    原始记录

公平性：三组共用 GroupBudget（同一 max_steps / max_tool_calls / 时限）与同一
沙箱配置；差异仅在注入上下文（Copilot 模块输出）。
成本计量：每任务记录 usage 差值（调用前后 snapshot 相减），不累计重复计算。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from concurrent.futures import ThreadPoolExecutor

from .baselines import GROUP_RUNNERS, GroupBudget, ToolSandbox, trace_diagnostics, valid_final_answer
from .discoverybench_adapter import DiscoveryTask, load_tasks
from .metrics import (
    aggregate_group,
    hms_score,
    paired_delta,
    unsupported_conclusion_rate,
    var_precision_heuristic,
)
from .sandbox import check_bwrap_available

EVAL_CODE_VERSION = "eval/2.2"


def preflight_evaluation_sandbox(dry_run: bool = False) -> dict[str, Any]:
    """正式评测必须先验证 bwrap 命名空间可启动；stub dry-run 可离线执行。"""
    if dry_run:
        return {"required": False, "status": "bypassed_dry_run"}
    if not check_bwrap_available():
        raise RuntimeError(
            "正式评测已拒绝启动：bwrap 命名空间预检失败；未创建评测目录，也未调用模型。"
            "请使用支持 bwrap user/mount/network namespace 的 Runner；管道冒烟可使用 --dry-run。"
        )
    return {"required": True, "status": "passed", "runtime": "bwrap"}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    keys = ("total_calls", "prompt_tokens", "completion_tokens")
    return {key: int(after.get(key) or 0) - int(before.get(key) or 0) for key in keys}


def run_evaluation(
    bench_root: str | Path,
    out_dir: str | Path,
    groups: list[str] = ("A", "B", "C1", "C2"),
    subset: str = "main",
    limit: int = 20,
    task_ids: list[str] | None = None,
    llm: Any | None = None,
    judge_llm: Any | None = None,
    budget: GroupBudget | None = None,
    dry_run: bool = False,
    judge_hms_custom: bool = False,
) -> dict[str, Any]:
    sandbox_preflight = preflight_evaluation_sandbox(dry_run=dry_run)
    from ..integrations.llm import LLMUnavailable, OpenAICompatibleLLM
    from .official_scoring import OFFICIAL_EVAL_SHA256, OfficialProtocolScorer

    if llm is None:
        if dry_run:
            from ..integrations.llm import StubLLM

            llm = _dry_run_stub()
            judge_llm = judge_llm or _dry_run_judge_stub()
        else:
            llm = OpenAICompatibleLLM()  # 未配置会抛 LLMUnavailable
    judge_llm = judge_llm if judge_llm is not None else llm
    budget = budget or GroupBudget()

    if task_ids:
        tasks = load_tasks(bench_root, subset, task_ids=task_ids)
        selection: dict[str, Any] = {"rule": "显式 task_ids", "task_ids": list(task_ids), "note": ""}
    else:
        from .discoverybench_adapter import select_dev_tasks

        selection = select_dev_tasks(bench_root, subset, limit)
        tasks = load_tasks(bench_root, subset, task_ids=selection["task_ids"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(out_dir) / f"{stamp}-{'-'.join(groups)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    model = getattr(getattr(llm, "config", None), "model", "stub")
    judge_model = getattr(getattr(judge_llm, "config", None), "model", "stub")
    probe_sandbox = ToolSandbox(None, timeout_s=budget.timeout_s)
    config = {
        "eval_code_version": EVAL_CODE_VERSION,
        "schema_version": "rc/1.0",
        "bench_root": str(bench_root),
        "subset": subset,
        "selection": selection,
        "task_ids": [t.task_id for t in tasks],
        "groups": list(groups),
        "model": model,
        "judge_model": judge_model,
        "budget": {"max_steps": budget.max_steps, "max_tool_calls": budget.max_tool_calls, "timeout_s": budget.timeout_s},
        "fairness": "三组共用同一 ReAct 循环 / 同一工具沙箱配置 / 同一预算；差异仅在注入上下文（Copilot 模块输出）",
        "sandbox_isolation": probe_sandbox.isolation_record,
        "sandbox_preflight": sandbox_preflight,
        "scorer": {
            "kind": "official-protocol/single-subhypothesis",
            "official_eval_sha256": OFFICIAL_EVAL_SHA256,
            "judge_model": judge_model,
        },
        "dry_run": dry_run,
        "note": "judge 模型仅用于评分并单独计量；dry_run 为 stub 管道冒烟，不构成评测结论。",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_dir / "config.json", config)

    # 金标-数据分歧诊断（每任务一次，诊断性、不影响评分）
    divergence_checks: dict[str, Any] = {}
    if tasks:  # dry-run 也走 stub，保持管道覆盖
        from ..analysis.statistics import relation_signs

        def _divergence(task):
            try:
                tables = _task_tables(task)
                all_rows = [row for table in tables for row in table["rows"]]
                if len(all_rows) < 5:
                    return task.task_id, {"divergence": None, "note": "no rows"}
                columns: list[str] = []
                for row in all_rows[:50]:
                    for key in row:
                        if key not in columns and key != "__dataset_file":
                            columns.append(key)
                relations = relation_signs(all_rows, columns)
                top = [rel for rel in relations if rel["sign"] in ("positive", "negative")][:8]
                scorer_probe = OfficialProtocolScorer(judge_llm)
                return task.task_id, scorer_probe.divergence_check(
                    task.query,
                    task.gold_hypothesis,
                    json.dumps(top, ensure_ascii=False),
                )
            except Exception as exc:
                return task.task_id, {"divergence": None, "error": str(exc)[:200]}

        with ThreadPoolExecutor(max_workers=4) as pool:
            for task_id, check in pool.map(_divergence, tasks):
                divergence_checks[task_id] = check
        config["divergence_checks"] = divergence_checks
        config["divergence_note"] = "divergence=true 的任务：金标与数据实测方向矛盾，其官方分数应解读为分歧而非模型错误（诊断性标注，不参与评分）"
        _write_json(run_dir / "config.json", config)

    records_by_group: dict[str, list[dict[str, Any]]] = {group: [] for group in groups}
    for task in tasks:
        for group in groups:
            runner = GROUP_RUNNERS[group]
            sandbox = ToolSandbox(task.dataset_dir, timeout_s=budget.timeout_s)
            usage_before = llm.usage_summary()
            started = time.time()
            try:
                result = runner(llm, task, budget=budget, sandbox=sandbox)
            except Exception as exc:  # 单任务失败不拖垮整场评测
                # 审查 P1：按异常来源分类，不再统一 transport_failure
                failure_class = (
                    "transport_failure" if isinstance(exc, (ConnectionError, TimeoutError, LLMUnavailable)) else "executor_error"
                )
                error_record = {
                    "group": group,
                    "task_id": task.task_id,
                    "failure_class": failure_class,
                    "error": f"{type(exc).__name__}: {exc}",
                    "answer": {},
                    "unsupported": {"evaluable": False, "not_evaluable_reason": "task_error"},
                    "official": {},
                    "llm_calls": _usage_delta(usage_before, llm.usage_summary())["total_calls"],
                    "tool_calls": len(sandbox.executions),
                    "duration_s": round(time.time() - started, 3),
                    "sandbox_isolation": sandbox.isolation_record,
                    "prompt_tokens": _usage_delta(usage_before, llm.usage_summary())["prompt_tokens"],
                    "completion_tokens": _usage_delta(usage_before, llm.usage_summary())["completion_tokens"],
                }
                records_by_group[group].append(error_record)
                _write_json(run_dir / group / task.task_id / "error.json", error_record)
                _write_json(run_dir / group / task.task_id / "trace.json", [{"kind": "executor_error", "error": error_record["error"], "executions": sandbox.executions}])
                continue
            finally:
                sandbox.close()
            usage = _usage_delta(usage_before, llm.usage_summary())
            all_rows = _task_rows(task)
            unsupported = unsupported_conclusion_rate(result.answer, all_rows)
            record = {
                "group": result.group,
                "task_id": result.task_id,
                "failure_class": result.failure_class,
                "diagnostics": trace_diagnostics(result.trace),
                "sandbox_isolation": sandbox.isolation_record,
                "answer": result.answer,
                "raw_answer": result.raw_answer[:2000],
                "llm_calls": result.llm_calls,
                "tool_calls": result.tool_calls,
                "duration_s": round(time.time() - started, 3),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "error": result.error,
                "self_check": result.self_check,
                "unsupported": unsupported,
                "official": {},
                "official_accuracy": None,
                "hms_custom": None,
                "judge_calls": 0,
            }
            task_dir = run_dir / group / task.task_id
            _write_json(task_dir / "answer.json", {"answer": result.answer, "raw": result.raw_answer, "self_check": result.self_check})
            (task_dir / "trace.json").write_text(
                json.dumps(result.trace, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _write_json(
                task_dir / "cost.json",
                {k: record[k] for k in ("llm_calls", "tool_calls", "duration_s", "prompt_tokens", "completion_tokens")},
            )
            records_by_group[group].append(record)

    # 评分：官方协议（judge）为主。judge 请求管道化（线程池），组/被测标签不进入
    # judge 上下文（盲评）；var 维度另附确定性启发式交叉核对。
    hms_error = ""

    def _score_one(group: str, record: dict[str, Any]) -> None:
        nonlocal hms_error
        if not valid_final_answer(record.get("answer") or {}):
            return
        try:
            task = next(t for t in tasks if t.task_id == record["task_id"])
            scorer = OfficialProtocolScorer(judge_llm)
            official = scorer.score(task.query, task.gold_hypothesis, record["answer"].get("hypothesis") or "")
            record["official"] = official
            record["official_accuracy"] = official.get("accuracy")
            record["judge_calls"] = scorer.judge_calls
            record["var_precision_heuristic"] = var_precision_heuristic(record["answer"], task.gold_hypothesis)
            if judge_hms_custom:
                scored_custom = hms_score(record["answer"], task.gold_hypothesis, judge_llm)
                record["hms_custom"] = scored_custom["hms"]
        except Exception as exc:
            hms_error = f"{type(exc).__name__}: {exc}"
            record["official_accuracy"] = None
            record["scoring_error"] = hms_error

    scoring_pairs = [(group, record) for group in groups for record in records_by_group[group]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda pair: _score_one(*pair), scoring_pairs))
    for group in groups:
        raw_path = run_dir / "raw" / f"{group}.jsonl"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as handle:
            for record in records_by_group[group]:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    summaries = {group: aggregate_group(records_by_group[group]) for group in groups}
    actual_isolation = [r["sandbox_isolation"] for rs in records_by_group.values() for r in rs if r.get("sandbox_isolation", {}).get("execution_verified")]
    config["sandbox_execution_summary"] = {
        "n_tasks_executed_code": len(actual_isolation),
        "all_fs_isolated": all(r.get("fs_isolated") for r in actual_isolation) if actual_isolation else None,
        "all_network_isolated": all(r.get("network_isolated") for r in actual_isolation) if actual_isolation else None,
    }
    _write_json(run_dir / "config.json", config)
    comparisons = {}
    if "A" in records_by_group and "C1" in records_by_group:
        comparisons["C1_vs_A"] = paired_delta(records_by_group["C1"], records_by_group["A"])
    if "B" in records_by_group and "C1" in records_by_group:
        comparisons["C1_vs_B"] = paired_delta(records_by_group["C1"], records_by_group["B"])
    if "C1" in records_by_group and "C2" in records_by_group:
        comparisons["C2_vs_C1"] = paired_delta(records_by_group["C2"], records_by_group["C1"])

    summary = {
        **config,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "group_summaries": summaries,
        "comparisons": comparisons,
        "hms_error": hms_error,
        "divergent_tasks": sorted(
            [task_id for task_id, check in (config.get("divergence_checks") or {}).items() if check.get("divergence")]
        ),
        "honesty_note": (
            "dry_run 模式：stub LLM，仅验证管道连通性，不构成评测结论。"
            if dry_run
            else "正式评测：结果只描述本任务子集；test 划分任务已用于开发期评测（见 selection 污染注记）；未观察到收益时按原样报告并归因。"
        ),
    }
    _write_json(run_dir / "summary.json", summary)
    (run_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    return summary


def _task_rows(task: DiscoveryTask) -> list[dict[str, Any]]:
    # 用 load_task_tables（csv+dta）合并行——仅用于数值断言重算；表结构信息由 __dataset_file 保留
    from .discoverybench_adapter import load_task_tables

    rows: list[dict[str, Any]] = []
    for table in load_task_tables(task):
        rows.extend(table["rows"])
    return rows


def _task_tables(task: DiscoveryTask) -> list[dict[str, Any]]:
    from .discoverybench_adapter import load_task_tables

    return load_task_tables(task)


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = ["# A/B/C 对照评测汇总", ""]
    sandbox = summary.get("sandbox_isolation") or {}
    lines += [
        f"- 模型: {summary['model']}；judge: {summary['judge_model']}；dry_run: {summary['dry_run']}",
        f"- 任务: subset={summary['subset']}, n={len(summary['task_ids'])}, groups={summary['groups']}",
        f"- 沙箱: env 白名单 + rlimits；网络隔离: {sandbox.get('network_isolated')}（{sandbox.get('honesty_note', '')}）",
        f"- {summary['honesty_note']}",
        "",
        "| 组 | 完成率 | 已评分任务acc | **全任务得分** | 全任务95% CI（数据集聚类） | context | var_F1 | rel | 无依据(可评) | 不可评 | LLM调用 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for group, agg in summary["group_summaries"].items():
        ci = agg.get("full_task_score_ci95")
        lines.append(
            f"| {group} | {agg['completion_rate']:.0%} | {agg['official_accuracy_mean'] if agg['official_accuracy_mean'] is not None else '-'} "
        f"| {agg['full_task_score_mean'] if agg.get('full_task_score_mean') is not None else '-'} "
            f"| {f'[{ci[0]}, {ci[1]}]' if ci else '-'} | {agg.get('context_match_rate') if agg.get('context_match_rate') is not None else '-'} "
            f"| {agg.get('var_f1_mean') if agg.get('var_f1_mean') is not None else '-'} "
            f"| {agg.get('rel_score_mean') if agg.get('rel_score_mean') is not None else '-'} "
            f"| {agg.get('unsupported_rate_mean_evaluable') if agg.get('unsupported_rate_mean_evaluable') is not None else '-'} "
            f"| {agg.get('n_not_evaluable', 0)} | {agg['total_llm_calls']} |"
        )
    lines.append("")
    lines += [
        "Benchmark Evidence Verification Coverage 只统计答案中显式声明的数值断言；未声明的数字和自由文本结论不在分母中，也不代表已验证。",
        "此指标与诊断报告中的结构化主张覆盖率使用不同输入。",
        "",
    ]
    for group, agg in summary["group_summaries"].items():
        evidence = agg.get("evidence") or {}
        lines.append(f"- {group}：声明数值断言 {evidence.get('n_assertions', 0)}；程序复核覆盖率 {evidence.get('coverage_rate')}；"
                     f"通过/矛盾/不可验证比例 = "
                     f"{evidence.get('verified_rate')}/{evidence.get('contradicted_rate')}/{evidence.get('unverifiable_rate')}；"
                     f"评分缺失 {agg.get('n_score_missing', 0)}；逐步异常计数 {agg.get('diagnostics', {})}")
    lines.append("")
    for name, delta in summary.get("comparisons", {}).items():
        lines.append(
            f"- **{name}**：全任务 n={delta['n_tasks']}（未完成记 0），delta={delta['delta_mean']}，CI {delta['delta_ci95']}"
        )
    if summary.get("hms_error"):
        lines.append(f"- 评分异常: {summary['hms_error']}")
    lines.append("")
    return "\n".join(lines)


def _dry_run_stub():
    from ..integrations.llm import StubLLM

    answer = json.dumps(
        {
            "hypothesis": "变量 X 与 Y 呈正相关（dry-run 占位答案，不构成评测结论）",
            "variables": ["X", "Y"],
            "relationships": ["X 与 Y 正相关"],
            "mechanism": "数据不足以支持机制解释",
            "numeric_assertions": [],
        },
        ensure_ascii=False,
    )
    return StubLLM(responses={"react_a_step_0": answer, "react_b_step_0": answer, "react_c1_step_0": answer, "react_c2_step_0": answer})


def _dry_run_judge_stub():
    from ..integrations.llm import StubLLM

    return StubLLM(
        responses={
            "official_judge_context": "A) same",
            "official_judge_var": json.dumps({"sizeA": 2, "sizeB": 2, "intersection": 2, "explanation": "stub"}),
            "official_judge_rel": json.dumps({"answer": "A) very similar", "explanation": "stub"}),
            "divergence_check": json.dumps({"divergence": False, "reason": "stub"}, ensure_ascii=False),
        },
        default=json.dumps({"score": 1, "reason": "stub judge（dry-run）"}, ensure_ascii=False),
    )
