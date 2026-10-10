"""A/B/C 三组基线（同一模型、同一工具集、同一预算——对照评测的关键）。

- A  plain_llm      ：普通 LLM + 相同数据分析工具（python 执行沙箱），ReAct 循环；
- B  copilot_no_diag：Copilot 框架但关闭诊断与证据约束（只给表格头/摘要，直接作答）；
- C  copilot_full   ：完整 Copilot：确定性画像 + 诊断观测 + 证据校验后再作答。

统一作答 schema（对齐 HMS 结构化抽取字段）：
    {"hypothesis": str, "variables": [...], "relationships": [...],
     "mechanism": str, "numeric_assertions": [...]}
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ANSWER_SCHEMA = {
    "hypothesis": "一句话主假设陈述",
    "variables": ["涉及变量"],
    "relationships": ["变量间关系（相关或因果，如实标注）"],
    "mechanism": "机制解释（若数据不足以支持机制，写 '数据不足以支持机制解释'）",
    "numeric_assertions": [
        {
            "metric": "列名",
            "value": 0.0,
            "check": "mean|median|percentile_p95|percent_change_from_baseline",
            "group": "组名（mean/median/p95 时）",
            "candidate_group": "（percent_change 时）",
            "baseline_group": "（percent_change 时）",
            "basis": "数据依据说明",
        }
    ],
}

ANSWER_SYSTEM_PROMPT = f"""你是数据分析驱动的科研发现助手。基于给定数据回答研究问题，只输出 JSON（不要其他文字）：
{json.dumps(ANSWER_SCHEMA, ensure_ascii=False, indent=1)}
规则：数字必须放入 numeric_assertions 并说明依据；数据不足以支持因果/机制时必须如实写
"数据不足以支持机制解释"，不得编造机制；不得引入数据之外的知识作为发现依据。"""


class ToolSandbox:
    """python 代码执行沙箱：任务数据集目录为 cwd，禁网络靠不提供（公平地同样用于所有组）。

    记录每次执行的代码与输出（轨迹可复现）。零依赖：LLM 生成代码可用 stdlib csv；
    环境若装有 pandas 也可用（版本记录进成本台账）。
    """

    def __init__(self, dataset_dir: str | Path, timeout_s: float = 60.0) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else None
        self.timeout_s = timeout_s
        self.executions: list[dict[str, Any]] = []

    def run_python(self, code: str) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "snippet.py"
            script.write_text(code, encoding="utf-8")
            try:
                completed = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(self.dataset_dir) if self.dataset_dir else str(tmp),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
                result = {
                    "ok": completed.returncode == 0,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-2000:],
                }
            except subprocess.TimeoutExpired:
                result = {"ok": False, "stdout": "", "stderr": f"timeout after {self.timeout_s}s"}
        self.executions.append({"code": code, **result})
        return result


class AnswerLLM(Protocol):
    def complete(self, system: str, user: str, purpose: str = "") -> str: ...


@dataclass
class GroupResult:
    group: str
    task_id: str
    answer: dict[str, Any]
    raw_answer: str
    llm_calls: int
    tool_calls: int
    ok: bool
    error: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)


def _parse_answer(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _dataset_brief(rows: list[dict[str, Any]], head_n: int = 8) -> str:
    if not rows:
        return "（无数据集文件）"
    columns: list[str] = []
    for row in rows[:20]:
        for key in row:
            if key not in columns:
                columns.append(key)
    head = rows[:head_n]
    brief = {
        "n_rows": len(rows),
        "columns": columns,
        "head": head,
    }
    return json.dumps(brief, ensure_ascii=False, default=str)


def _data_profile_for_copilot(rows: list[dict[str, Any]]) -> str:
    """B/C 组共享的数据画像：列 + 每数值列 describe（不含 LLM）。

    B 组拿到同样的画像但跳过诊断观测与证据校验 —— 差异只在 Copilot 模块本身。
    """
    from ..analysis.statistics import describe, numeric

    if not rows:
        return "（无数据集文件）"
    columns: list[str] = []
    for row in rows[:50]:
        for key in row:
            if key not in columns:
                columns.append(key)
    profile: dict[str, Any] = {"n_rows": len(rows), "columns": columns, "column_stats": {}}
    for column in columns:
        values = numeric(rows, column)
        if values and len(values) >= max(2, int(0.3 * len(rows))):
            stats = describe(values, column)
            profile["column_stats"][column] = {
                "n": stats["n"],
                "mean": stats["mean"],
                "median": stats["median"],
                "min": stats["min"],
                "max": stats["max"],
                "p90": stats["percentiles"].get("p90"),
            }
    return json.dumps(profile, ensure_ascii=False, default=str)


def run_group_a(llm: AnswerLLM, task, max_steps: int = 6, sandbox: ToolSandbox | None = None) -> GroupResult:
    """A：普通 LLM + python 工具的 ReAct 循环。"""
    sandbox = sandbox or ToolSandbox(task.dataset_dir)
    from ..integrations.material_importer import read_rows
    from pathlib import Path as _Path

    rows: list[dict[str, Any]] = []
    if task.dataset_dir and _Path(task.dataset_dir).exists():
        for csv_path in sorted(_Path(task.dataset_dir).rglob("*.csv")):
            try:
                rows.extend(read_rows(csv_path))
            except ValueError:
                continue
    tool_desc = (
        "你可以调用工具 python：给我一段 python 代码（操作 cwd 下的数据集文件），我会返回 stdout/stderr。"
        "需要分析时输出 JSON：{\"tool\": \"python\", \"code\": \"...\"}；"
        "最终答案输出 JSON：{\"hypothesis\": ..., \"variables\": [...], \"relationships\": [...], "
        "\"mechanism\": ..., \"numeric_assertions\": [...]}"
    )
    context = f"研究问题：{task.query}\n\n数据集概要：{_dataset_brief(rows)}\n\n{tool_desc}"
    trace: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    raw = ""
    llm_calls = 0
    for step in range(max_steps):
        raw = llm.complete(ANSWER_SYSTEM_PROMPT, context, purpose=f"react_step_{step}")
        llm_calls += 1
        parsed = _parse_answer(raw) or {}
        if parsed.get("tool") == "python" and isinstance(parsed.get("code"), str):
            outcome = sandbox.run_python(parsed["code"])
            trace.append({"step": step, "kind": "tool", "code": parsed["code"], "outcome": outcome})
            context += f"\n\n工具结果（第 {step + 1} 步）：{json.dumps(outcome, ensure_ascii=False)[:4000]}"
            continue
        if parsed:
            answer = parsed
            trace.append({"step": step, "kind": "answer", "answer": answer})
            break
        trace.append({"step": step, "kind": "unparseable", "raw": raw[:500]})
    return GroupResult(
        group="A",
        task_id=task.task_id,
        answer=answer,
        raw_answer=raw,
        llm_calls=llm_calls,
        tool_calls=len(sandbox.executions),
        ok=bool(answer.get("hypothesis")),
        error="" if answer.get("hypothesis") else "未在步数预算内产出有效答案",
        trace=trace,
    )


def run_group_b(llm: AnswerLLM, task, sandbox: ToolSandbox | None = None) -> GroupResult:
    """B：Copilot 框架但关闭诊断与证据约束。"""
    from ..integrations.material_importer import read_rows
    from pathlib import Path as _Path

    rows: list[dict[str, Any]] = []
    if task.dataset_dir and _Path(task.dataset_dir).exists():
        for csv_path in sorted(_Path(task.dataset_dir).rglob("*.csv")):
            try:
                rows.extend(read_rows(csv_path))
            except ValueError:
                continue
    context = (
        f"研究问题：{task.query}\n\n数据画像（无诊断/证据模块）：{_data_profile_for_copilot(rows)}"
    )
    raw = llm.complete(ANSWER_SYSTEM_PROMPT, context, purpose="group_b_answer")
    answer = _parse_answer(raw)
    return GroupResult(
        group="B",
        task_id=task.task_id,
        answer=answer,
        raw_answer=raw,
        llm_calls=1,
        tool_calls=0,
        ok=bool(answer.get("hypothesis")),
        error="" if answer.get("hypothesis") else "答案解析失败",
    )


def run_group_c(llm: AnswerLLM, task, project_store: Any | None = None) -> GroupResult:
    """C：完整 Copilot——确定性画像 + 诊断观测（含异常/长尾/混杂）→ LLM 作答。

    注意：与 A/B 同一 LLM、同一作答 schema；C 的额外信息全部来自确定性分析模块，
    且作答提示同样禁止编造机制 —— 差异即 Copilot 诊断与证据层本身的贡献。
    """
    from ..analysis.anomaly_detection import detect_anomalies
    from ..analysis.statistics import compare_metric
    from pathlib import Path as _Path
    from ..integrations.material_importer import read_rows, summarize_rows

    rows: list[dict[str, Any]] = []
    if task.dataset_dir and _Path(task.dataset_dir).exists():
        for csv_path in sorted(_Path(task.dataset_dir).rglob("*.csv")):
            try:
                rows.extend(read_rows(csv_path))
            except ValueError:
                continue
    summary = summarize_rows(rows) if rows else {}
    metric_columns = summary.get("numeric_columns") or []
    metric_directions = summary.get("metric_directions") or {}
    query_field = summary.get("query_field") or "query_id"
    group_field = summary.get("group_field") or "comparison_group"

    observations: list[dict[str, Any]] = []
    for metric in metric_columns:
        for candidate in detect_anomalies(rows, metric, metric_directions, query_field):
            observations.append({"kind": candidate["kind"], "statement": candidate["statement"], "value": candidate["value"]})
    if summary.get("group_field"):
        groups = sorted({str(row.get(group_field)) for row in rows if row.get(group_field) is not None})
        if len(groups) >= 2:
            for metric in metric_columns:
                comparison = compare_metric(rows, metric, groups[-1], groups[0], metric_directions, group_field, query_field)
                observations.append(
                    {
                        "kind": "group_comparison",
                        "statement": f"{metric}: {groups[-1]} vs {groups[0]} → {comparison['interpretation']}",
                        "value": {
                            "candidate_mean": comparison["candidate"]["mean"],
                            "baseline_mean": comparison["baseline"]["mean"],
                            "delta_mean": comparison.get("delta_mean"),
                            "delta_ci95": list(comparison["delta_ci95"]) if comparison.get("delta_ci95") else None,
                            "interpretation": comparison["interpretation"],
                            "direction_declared": comparison["direction_declared"],
                        },
                    }
                )
    context = (
        f"研究问题：{task.query}\n\n数据画像：{_data_profile_for_copilot(rows)}\n\n"
        f"诊断观测（确定性分析，含异常/长尾/混杂提示）：\n{json.dumps(observations, ensure_ascii=False, default=str)[:8000]}"
    )
    raw = llm.complete(ANSWER_SYSTEM_PROMPT, context, purpose="group_c_answer")
    answer = _parse_answer(raw)
    return GroupResult(
        group="C",
        task_id=task.task_id,
        answer=answer,
        raw_answer=raw,
        llm_calls=1,
        tool_calls=0,
        ok=bool(answer.get("hypothesis")),
        error="" if answer.get("hypothesis") else "答案解析失败",
    )


GROUP_RUNNERS = {"A": run_group_a, "B": run_group_b, "C": run_group_c}
