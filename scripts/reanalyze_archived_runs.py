"""离线重算历史指标与轨迹异常；不调用模型、不改变原答案/评分/原始归档。"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from research_copilot.evaluation.baselines import trace_diagnostics
from research_copilot.evaluation.metrics import aggregate_group, paired_delta
from research_copilot.evaluation.runner import EVAL_CODE_VERSION, render_summary_markdown


def reanalyze(source: Path, out: Path) -> dict:
    old = json.loads((source / "summary.json").read_text())
    records_by_group = {}
    source_digest = hashlib.sha256()
    source_digest.update((source / "summary.json").read_bytes())
    missing_traces = []
    for group in old["groups"]:
        raw = source / "raw" / f"{group}.jsonl"
        if not raw.exists():
            raise FileNotFoundError(raw)
        source_digest.update(raw.read_bytes())
        records = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
        for record in records:
            trace_paths = [source / group / record["task_id"] / "trace.json",
                           source / "traces" / group / record["task_id"] / "trace.json"]
            trace_path = next((p for p in trace_paths if p.exists()), None)
            if trace_path is None:
                missing_traces.append(f"{group}:{record['task_id']}")
            else:
                source_digest.update(trace_path.read_bytes())
                record["diagnostics"] = trace_diagnostics(json.loads(trace_path.read_text()))
        records_by_group[group] = records
    comparisons = {}
    for x, y in (("C1", "A"), ("C1", "B"), ("C2", "C1"), ("C", "A"), ("C", "B")):
        if x in records_by_group and y in records_by_group:
            comparisons[f"{x}_vs_{y}"] = paired_delta(records_by_group[x], records_by_group[y])
    result = {
        **old,
        "group_summaries": {g: aggregate_group(rs) for g, rs in records_by_group.items()},
        "comparisons": comparisons,
        "reanalysis": {
            "source_directory": str(source), "source_sha256": source_digest.hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metric_code_version": EVAL_CODE_VERSION,
            "scope": "仅重算汇总、置信区间与已保存轨迹异常；原始答案和官方评分未改，未重新运行模型或judge。",
            "missing_traces": missing_traces,
            "execution_note": "旧运行使用原执行器，不能视为修复后能力评测；终态失败标签不是经实验确认的根因。",
        },
        "honesty_note": "历史归档离线重算；不是修复后的新模型评测。任务子集小且已用于开发，不外推能力收益。",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (out / "summary.md").write_text(render_summary_markdown(result) + "\n" + result["reanalysis"]["scope"] + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("eval-runs"))
    parser.add_argument("--out", type=Path, default=Path("docs/reanalysis/20261013"))
    args = parser.parse_args()
    runs = []
    for summary in sorted(args.source.rglob("summary.json")):
        source = summary.parent
        result = reanalyze(source, args.out / source.relative_to(args.source))
        runs.append({"source": str(source), "model": result["model"], "n_tasks": len(result["task_ids"]),
                     "scores": {g: s["full_task_score_mean"] for g, s in result["group_summaries"].items()},
                     "comparisons": result["comparisons"]})
    (args.out / "index.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(runs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
