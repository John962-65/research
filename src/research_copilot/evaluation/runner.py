"""评测运行器：A/B/C 三组 × N 任务的可复现对照。

产物（eval-runs/<stamp>/，gitignore）：
    config.json          模型/预算/任务清单/评测代码版本（复现台账）
    <group>/<task_id>/answer.json + trace.json + cost.json
    summary.json/.md     组级汇总 + 组间配对差
    raw/<group>.jsonl    原始记录

dry_run=True 时用 StubLLM 跑通管道（工程冒烟），正式评测必须用真实 LLM 并记录。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .baselines import GROUP_RUNNERS, ToolSandbox
from .discoverybench_adapter import DiscoveryTask, load_tasks
from .metrics import aggregate_group, hms_score, paired_delta, unsupported_conclusion_rate

EVAL_CODE_VERSION = "eval/1.0"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_evaluation(
    bench_root: str | Path,
    out_dir: str | Path,
    groups: list[str] = ("A", "B", "C"),
    subset: str = "main",
    limit: int = 20,
    task_ids: list[str] | None = None,
    llm: Any | None = None,
    judge_llm: Any | None = None,
    max_steps: int = 6,
    dry_run: bool = False,
) -> dict[str, Any]:
    from ..integrations.llm import LLMUnavailable, OpenAICompatibleLLM

    if llm is None:
        if dry_run:
            from ..integrations.llm import StubLLM

            llm = _dry_run_stub()
            judge_llm = judge_llm or _dry_run_judge_stub()
        else:
            llm = OpenAICompatibleLLM()  # 未配置会抛 LLMUnavailable
    judge_llm = judge_llm if judge_llm is not None else llm

    if task_ids:
        tasks = load_tasks(bench_root, subset, task_ids=task_ids)
        selection = {"rule": "显式 task_ids", "task_ids": list(task_ids), "note": ""}
    else:
        from .discoverybench_adapter import select_dev_tasks

        selection = select_dev_tasks(bench_root, subset, limit)
        tasks = load_tasks(bench_root, subset, task_ids=selection["task_ids"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(out_dir) / f"{stamp}-{'-'.join(groups)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    model = getattr(getattr(llm, "config", None), "model", "stub")
    judge_model = getattr(getattr(judge_llm, "config", None), "model", "stub")
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
        "max_steps": max_steps,
        "dry_run": dry_run,
        "note": "同一被测模型/工具集/步数预算用于所有组；judge 模型仅用于 HMS 评分并单独记录。",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(run_dir / "config.json", config)

    records_by_group: dict[str, list[dict[str, Any]]] = {group: [] for group in groups}
    for task in tasks:
        rows = _task_rows(task)
        for group in groups:
            runner = GROUP_RUNNERS[group]
            started = time.time()
            try:
                result = runner(llm, task, max_steps=max_steps) if group == "A" else runner(llm, task)
            except Exception as exc:  # 单任务失败不拖垮整场评测
                result_records = {
                    "group": group,
                    "task_id": task.task_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "answer": {},
                    "llm_calls": 0,
                    "tool_calls": 0,
                }
                records_by_group[group].append(result_records)
                _write_json(run_dir / group / task.task_id / "error.json", result_records)
                continue
            usage = getattr(llm, "usage_summary", lambda: {})()
            unsupported = unsupported_conclusion_rate(result.answer, rows)
            record = {
                "group": result.group,
                "task_id": result.task_id,
                "answer": result.answer,
                "raw_answer": result.raw_answer[:2000],
                "llm_calls": result.llm_calls,
                "tool_calls": result.tool_calls,
                "duration_s": round(time.time() - started, 3),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "error": result.error,
                "unsupported": unsupported,
                "hms": None,
                "hms_reason": "",
            }
            task_dir = run_dir / group / task.task_id
            _write_json(task_dir / "answer.json", {"answer": result.answer, "raw": result.raw_answer})
            (task_dir / "trace.json").write_text(
                json.dumps(result.trace if hasattr(result, "trace") else [], ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _write_json(task_dir / "cost.json", {k: record[k] for k in ("llm_calls", "tool_calls", "duration_s", "prompt_tokens", "completion_tokens")})
            records_by_group[group].append(record)

    # HMS 评分（judge 可用才评；不可用保留 None 并如实标注）
    hms_error = ""
    for group in groups:
        for record in records_by_group[group]:
            try:
                task = next(t for t in tasks if t.task_id == record["task_id"])
                scored = hms_score(record["answer"], task.gold_hypothesis, judge_llm)
                record["hms"] = scored["hms"]
                record["hms_reason"] = scored.get("reason", "")
            except Exception as exc:
                hms_error = f"{type(exc).__name__}: {exc}"
                record["hms"] = None
            # 保存 raw 记录
        raw_path = run_dir / "raw" / f"{group}.jsonl"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        with raw_path.open("w", encoding="utf-8") as handle:
            for record in records_by_group[group]:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    summaries = {group: aggregate_group(records_by_group[group]) for group in groups}
    comparisons = {}
    if "A" in records_by_group and "C" in records_by_group:
        comparisons["C_vs_A"] = paired_delta(records_by_group["C"], records_by_group["A"])
    if "B" in records_by_group and "C" in records_by_group:
        comparisons["C_vs_B"] = paired_delta(records_by_group["C"], records_by_group["B"])

    summary = {
        **config,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "group_summaries": summaries,
        "comparisons": comparisons,
        "hms_error": hms_error,
        "honesty_note": (
            "dry_run 模式：stub LLM，仅验证管道连通性，不构成评测结论。"
            if dry_run
            else "正式评测：结果只描述本任务子集；未观察到收益时按原样报告并归因。"
        ),
    }
    _write_json(run_dir / "summary.json", summary)
    (run_dir / "summary.md").write_text(render_summary_markdown(summary), encoding="utf-8")
    return summary


def _task_rows(task: DiscoveryTask) -> list[dict[str, Any]]:
    from .discoverybench_adapter import load_task_rows

    return load_task_rows(task)


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = ["# A/B/C 对照评测汇总", ""]
    lines += [
        f"- 模型: {summary['model']}；judge: {summary['judge_model']}；dry_run: {summary['dry_run']}",
        f"- 任务: subset={summary['subset']}, n={len(summary['task_ids'])}",
        f"- {summary['honesty_note']}",
        "",
        "| 组 | 完成率 | HMS 均值 | HMS 95% CI | 无依据结论比例 | LLM 调用 |",
        "|---|---|---|---|---|---|",
    ]
    for group, agg in summary["group_summaries"].items():
        ci = agg.get("hms_ci95")
        lines.append(
            f"| {group} | {agg['completion_rate']:.0%} | {agg['hms_mean'] if agg['hms_mean'] is not None else '-'} "
            f"| {f'[{ci[0]}, {ci[1]}]' if ci else '-'} | {agg.get('unsupported_rate_mean') if agg.get('unsupported_rate_mean') is not None else '-'} "
            f"| {agg['total_llm_calls']} |"
        )
    lines.append("")
    for name, delta in summary.get("comparisons", {}).items():
        lines.append(
            f"- **{name}**：配对 n={delta['n_paired']}，delta={delta['delta_mean']}，CI {delta['delta_ci95']}"
        )
    if summary.get("hms_error"):
        lines.append(f"- HMS 评分异常: {summary['hms_error']}")
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
    return StubLLM(responses={"react_step_0": answer, "group_b_answer": answer, "group_c_answer": answer})


def _dry_run_judge_stub():
    from ..integrations.llm import StubLLM

    return StubLLM(default=json.dumps({"score": 1, "reason": "stub judge（dry-run）"}, ensure_ascii=False))
