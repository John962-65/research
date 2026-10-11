"""A/B/C 三组对照（评测公平性协议，v2）。

公平性约定（修复 2026-10 审查的 P0-1）：
- 三组共用**同一个** ReAct 循环、同一个 python 工具沙箱（相同限额/隔离）、
  相同的模型调用与工具调用预算、相同的时限与作答 schema；
- 组间唯一差异 = 注入的上下文（Copilot 模块的输出）：
  * A  plain_llm      ：仅数据概要（表名/列/前几行）；
  * B  copilot_no_diag：确定性统计画像（无诊断观测、无证据校验）；
  * C  copilot_full   ：统计画像 + 诊断观测（异常/长尾/混杂/关系方向），
    且答案经过**确定性自检闭环**：numeric_assertions 程序复核失败时，
    在预算内带错误信息重答一次，最终答案附自检结果。
- 任何组的成绩差异都可归因于 Copilot 模块本身，而不是工具/预算差异。

作答 schema（对齐 HMS 结构化抽取字段）：
    {"hypothesis": str, "variables": [...], "relationships": [...],
     "mechanism": str, "numeric_assertions": [...]}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sandbox import ToolSandbox

ANSWER_SCHEMA = {
    "hypothesis": "一句话主假设陈述",
    "variables": ["涉及变量"],
    "relationships": ["变量间关系（相关或因果，如实标注）"],
    "mechanism": "机制解释（若数据不足以支持机制，写 '数据不足以支持机制解释'）",
    "numeric_assertions": [
        {
            "metric": "断言名",
            "value": 0.0,
            "check": "mean|median|percentile_p95|percent_change_from_baseline|ols_beta",
            "group": "组名（mean/median/p95 时）",
            "candidate_group": "（percent_change 时）",
            "baseline_group": "（percent_change 时）",
            "regression": {"y": "因变量列", "x": ["自变量列"], "controls": ["控制列"], "filter": {"列": "值"}, "report": "要核对的系数对应列"},
            "basis": "数据依据说明（回归须给模型设定，验证器才能复算）",
        }
    ],
}

ANSWER_SYSTEM_PROMPT = f"""你是数据分析驱动的科研发现助手。基于给定数据回答研究问题，只输出 JSON（不要其他文字）：
{json.dumps(ANSWER_SCHEMA, ensure_ascii=False, indent=1)}
规则：数字必须放入 numeric_assertions 并说明依据；数据不足以支持因果/机制时必须如实写
"数据不足以支持机制解释"，不得编造机制；不得引入数据之外的知识作为发现依据。"""

TOOL_INSTRUCTION = (
    '你可以调用工具 python：输出 JSON {"tool": "python", "code": "..."}，'
    "代码将在数据集目录内的隔离沙箱执行并返回 stdout/stderr。"
    "分析完成后输出最终 JSON 答案（不再调用工具）。"
)


@dataclass
class GroupBudget:
    """三组共享的资源预算（公平性关键）。"""

    max_steps: int = 6
    max_tool_calls: int = 8
    timeout_s: float = 60.0


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
    self_check: dict[str, Any] = field(default_factory=dict)
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


# ---------- 共享上下文构建 ----------
def _dataset_brief(tables: list[dict[str, Any]], head_n: int = 5) -> str:
    if not tables:
        return "（无数据集文件）"
    brief = [
        {
            "table": table["name"],
            "n_rows": len(table["rows"]),
            "columns": _columns(table["rows"]),
            "head": table["rows"][:head_n],
        }
        for table in tables
    ]
    return json.dumps({"tables": brief}, ensure_ascii=False, default=str)


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows[:50]:
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def _data_profile(tables: list[dict[str, Any]]) -> str:
    """确定性统计画像（B/C 共享；无 LLM 参与）。"""
    from ..analysis.statistics import describe, numeric

    if not tables:
        return "（无数据集文件）"
    out = {"tables": []}
    for table in tables:
        rows = table["rows"]
        profile: dict[str, Any] = {"table": table["name"], "n_rows": len(rows), "column_stats": {}}
        for column in _columns(rows):
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
        out["tables"].append(profile)
    return json.dumps(out, ensure_ascii=False, default=str)


# 观测优先级（修复 2026-10 评测发现：噪声观测挤占有用观测）。
# C 组上下文按此排序并在超预算时从尾部丢弃——高信息量观测（组间比较/关系图）优先保留。
OBSERVATION_PRIORITY = {"group_comparison": 0, "relation_map": 1, "tail_latency": 2, "mixed_status": 3}
DEFAULT_OBSERVATION_PRIORITY = 5
C_CONTEXT_BUDGET_CHARS = 9000


def pack_observations(observations: list[dict[str, Any]], budget_chars: int = C_CONTEXT_BUDGET_CHARS) -> str:
    """按信息量优先级排序观测并序列化；超预算从尾部丢弃并注明。"""
    ordered = sorted(
        observations,
        key=lambda o: OBSERVATION_PRIORITY.get(str(o.get("kind")), DEFAULT_OBSERVATION_PRIORITY),
    )
    note = ""
    while True:
        payload = json.dumps(ordered, ensure_ascii=False, default=str)
        if len(payload) <= budget_chars or not ordered:
            break
        ordered = ordered[:-1]
        note = "（观测已按信息量优先级截断：低优先级观测被省略）"
    if note:
        payload = json.dumps(ordered, ensure_ascii=False, default=str) + note
    return payload


def compute_task_observations(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """C 组的诊断观测（确定性）：异常/长尾/混杂/组间比较/关系方向，按表分别计算。"""
    from ..analysis.anomaly_detection import compact_direction_noise, detect_anomalies
    from ..analysis.statistics import compare_metric, relation_signs
    from ..integrations.material_importer import summarize_rows

    observations: list[dict[str, Any]] = []
    for table in tables:
        rows = table["rows"]
        if not rows:
            continue
        summary = summarize_rows(rows)
        metric_columns = summary.get("numeric_columns") or []
        directions = summary.get("metric_directions") or {}
        query_field = summary.get("query_field") or "query_id"
        group_field = summary.get("group_field") or "comparison_group"
        for metric in metric_columns:
            for candidate in compact_direction_noise(
                detect_anomalies(rows, metric, directions, query_field)
            ):
                observations.append(
                    {"table": table["name"], "kind": candidate["kind"], "statement": candidate["statement"], "value": candidate["value"]}
                )
        group_values = sorted({str(row.get(group_field)) for row in rows if row.get(group_field) is not None})
        if summary.get("group_field") and len(group_values) >= 2:
            for metric in metric_columns:
                comparison = compare_metric(rows, metric, group_values[-1], group_values[0], directions, group_field, query_field)
                observations.append(
                    {
                        "table": table["name"],
                        "kind": "group_comparison",
                        "statement": f"{metric}: {group_values[-1]} vs {group_values[0]} → {comparison['interpretation']}",
                        "value": {
                            "candidate_mean": comparison["candidate"]["mean"],
                            "baseline_mean": comparison["baseline"]["mean"],
                            "delta_mean": comparison.get("delta_mean"),
                            "delta_ci95": list(comparison["delta_ci95"]) if comparison.get("delta_ci95") else None,
                            "interpretation": comparison["interpretation"],
                            "direction_declared": comparison["direction_declared"],
                            "lower_is_better": comparison["lower_is_better"],
                        },
                    }
                )
        if metric_columns and len(rows) >= 5:
            relations = relation_signs(rows, metric_columns)
            top = [rel for rel in relations if rel["sign"] in ("positive", "negative")][:5]
            statement = (
                "数值列相关方向（按 |r| 降序）："
                + "；".join(f"{rel['a']}~{rel['b']}={rel['sign']}(r={rel['pearson_r']})" for rel in top)
                if top
                else "数值列两两相关均无明确方向"
            )
            observations.append(
                {
                    "table": table["name"],
                    "kind": "relation_map",
                    "statement": statement,
                    "value": {"relations": relations},
                }
            )
    return observations


# ---------- 共享 ReAct 循环（各组唯一执行路径） ----------
def _react_loop(
    llm: Any,
    context: str,
    sandbox: ToolSandbox,
    budget: GroupBudget,
    group: str,
    task_id: str,
    purpose_prefix: str,
    diagnose_fn: Any | None = None,
) -> tuple[dict[str, Any], str, int, int, list[dict[str, Any]]]:
    trace: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    raw = ""
    llm_calls = 0
    tool_calls = 0
    for step in range(budget.max_steps):
        raw = llm.complete(ANSWER_SYSTEM_PROMPT, context, purpose=f"{purpose_prefix}_step_{step}")
        llm_calls += 1
        parsed = _parse_answer(raw) or {}
        if parsed.get("tool") == "python" and isinstance(parsed.get("code"), str):
            if tool_calls >= budget.max_tool_calls:
                trace.append({"step": step, "kind": "tool_budget_exhausted"})
                continue
            outcome = sandbox.run_python(parsed["code"])
            tool_calls += 1
            trace.append({"step": step, "kind": "tool", "code": parsed["code"], "outcome": {k: outcome.get(k) for k in ("ok", "stdout", "stderr")}})
            context += f"\n\n工具结果（第 {step + 1} 步）：{json.dumps({'ok': outcome.get('ok'), 'stdout': outcome.get('stdout', '')[:3000], 'stderr': outcome.get('stderr', '')[:800]}, ensure_ascii=False)}"
            continue
        if parsed.get("tool") == "diagnose" and diagnose_fn is not None:
            if tool_calls >= budget.max_tool_calls:
                trace.append({"step": step, "kind": "tool_budget_exhausted"})
                continue
            observations = diagnose_fn()
            tool_calls += 1
            trace.append({"step": step, "kind": "diagnose", "n_observations": len(observations)})
            context += (
                f"\n\n诊断工具结果（第 {step + 1} 步，确定性分析，按信息量优先级排序）：\n"
                f"{pack_observations(observations)}\n\n（可继续用 python 或直接给最终 JSON 答案）"
            )
            continue
        if parsed:
            answer = parsed
            trace.append({"step": step, "kind": "answer"})
            break
        trace.append({"step": step, "kind": "unparseable", "raw": raw[:400]})
    return answer, raw, llm_calls, tool_calls, trace


def run_group_a(llm: Any, task, budget: GroupBudget | None = None, sandbox: ToolSandbox | None = None) -> GroupResult:
    """A：普通 LLM + 同一工具沙箱。上下文只有数据概要。"""
    budget = budget or GroupBudget()
    sandbox = sandbox or ToolSandbox(task.dataset_dir, timeout_s=budget.timeout_s)
    from .discoverybench_adapter import load_task_tables

    tables = load_task_tables(task)
    context = f"研究问题：{task.query}\n\n数据集概要：{_dataset_brief(tables)}\n\n{TOOL_INSTRUCTION}"
    answer, raw, llm_calls, tool_calls, trace = _react_loop(llm, context, sandbox, budget, "A", task.task_id, "react_a")
    return GroupResult("A", task.task_id, answer, raw, llm_calls, tool_calls, bool(answer.get("hypothesis")),
                       error="" if answer.get("hypothesis") else "未在步数预算内产出有效答案", trace=trace)


def run_group_b(llm: Any, task, budget: GroupBudget | None = None, sandbox: ToolSandbox | None = None) -> GroupResult:
    """B：Copilot 框架但关闭诊断与证据约束。上下文 = 确定性统计画像。"""
    budget = budget or GroupBudget()
    sandbox = sandbox or ToolSandbox(task.dataset_dir, timeout_s=budget.timeout_s)
    from .discoverybench_adapter import load_task_tables

    tables = load_task_tables(task)
    context = f"研究问题：{task.query}\n\n数据画像（无诊断/证据模块）：{_data_profile(tables)}\n\n{TOOL_INSTRUCTION}"
    answer, raw, llm_calls, tool_calls, trace = _react_loop(llm, context, sandbox, budget, "B", task.task_id, "react_b")
    return GroupResult("B", task.task_id, answer, raw, llm_calls, tool_calls, bool(answer.get("hypothesis")),
                       error="" if answer.get("hypothesis") else "未在步数预算内产出有效答案", trace=trace)


def run_group_c1(llm: Any, task, budget: GroupBudget | None = None, sandbox: ToolSandbox | None = None) -> GroupResult:
    """C1：完整 Copilot——画像 + 预注入诊断观测 + 答案确定性自检闭环。

    自检 = 对答案的 numeric_assertions 程序重算（与 research-copilot 的 L2 校验同一套
    确定性检查）；复核失败时在预算内带错误重答一次；最终答案附 self_check 结果。
    """
    budget = budget or GroupBudget()
    sandbox = sandbox or ToolSandbox(task.dataset_dir, timeout_s=budget.timeout_s)
    from .discoverybench_adapter import load_task_tables
    from .metrics import check_numeric_assertions, causal_claims_without_basis

    tables = load_task_tables(task)
    observations = compute_task_observations(tables)
    context = (
        f"研究问题：{task.query}\n\n数据画像：{_data_profile(tables)}\n\n"
        f"诊断观测（确定性分析，含异常/长尾/混杂/关系方向，按信息量优先级排序）：\n"
        f"{pack_observations(observations)}\n\n{TOOL_INSTRUCTION}"
    )
    answer, raw, llm_calls, tool_calls, trace = _react_loop(llm, context, sandbox, budget, "C1", task.task_id, "react_c1")

    all_rows = [row for table in tables for row in table["rows"]]
    checks = check_numeric_assertions(answer, all_rows) if answer else []
    failed = [c for c in checks if c.get("status") == "fail"]
    causal = causal_claims_without_basis(answer) if answer else []
    self_check: dict[str, Any] = {
        "checks": checks,
        "n_fail": len(failed),
        "causal_without_basis": causal,
        "corrective_round": False,
    }
    # 预算内自检重答（C 组专属能力：证据约束闭环）
    if failed and llm_calls < budget.max_steps:
        error_report = json.dumps({"numeric_assertion_failures": failed}, ensure_ascii=False)
        context += (
            f"\n\n[证据自检未通过——数值断言与数据重算不一致，请修正后重新输出最终 JSON 答案]\n{error_report}"
        )
        raw2 = llm.complete(ANSWER_SYSTEM_PROMPT, context, purpose="react_c1_selfcheck")
        llm_calls += 1
        parsed = _parse_answer(raw2) or {}
        if parsed.get("hypothesis"):
            answer = parsed
            raw = raw2
            trace.append({"step": llm_calls - 1, "kind": "selfcheck_answer"})
            rechecks = check_numeric_assertions(answer, all_rows)
            self_check["checks"] = rechecks
            self_check["n_fail"] = len([c for c in rechecks if c.get("status") == "fail"])
            self_check["causal_without_basis"] = causal_claims_without_basis(answer)
            self_check["corrective_round"] = True
    return GroupResult("C", task.task_id, answer, raw, llm_calls, tool_calls, bool(answer.get("hypothesis")),
                       error="" if answer.get("hypothesis") else "未在步数预算内产出有效答案",
                       self_check=self_check, trace=trace)


def run_group_c2(llm: Any, task, budget: GroupBudget | None = None, sandbox: ToolSandbox | None = None) -> GroupResult:
    """C2：按需诊断消融组（审查建议的 C2 实验）。

    与 C1 唯一差异：诊断观测不预注入，而是作为工具按需调用（tool="diagnose"，
    确定性输出与 C1 相同）。比较两种诊断策略的准确度/成本/行为差异。
    """
    budget = budget or GroupBudget()
    sandbox = sandbox or ToolSandbox(task.dataset_dir, timeout_s=budget.timeout_s)
    from .discoverybench_adapter import load_task_tables
    from .metrics import check_numeric_assertions, causal_claims_without_basis

    tables = load_task_tables(task)
    context = (
        f"研究问题：{task.query}\n\n数据画像：{_data_profile(tables)}\n\n"
        f"{TOOL_INSTRUCTION}\n另外可用诊断工具：输出 JSON {{\"tool\": \"diagnose\"}}，"
        "将返回确定性诊断观测（异常/长尾/混杂/组间比较/关系方向，与 python 工具共享调用预算）。"
    )
    answer, raw, llm_calls, tool_calls, trace = _react_loop(
        llm, context, sandbox, budget, "C2", task.task_id, "react_c2",
        diagnose_fn=lambda: compute_task_observations(tables),
    )

    all_rows = [row for table in tables for row in table["rows"]]
    checks = check_numeric_assertions(answer, all_rows) if answer else []
    failed = [c for c in checks if c.get("status") == "fail"]
    causal = causal_claims_without_basis(answer) if answer else []
    self_check: dict[str, Any] = {
        "checks": checks,
        "n_fail": len(failed),
        "causal_without_basis": causal,
        "corrective_round": False,
    }
    if failed and llm_calls < budget.max_steps:
        error_report = json.dumps({"numeric_assertion_failures": failed}, ensure_ascii=False)
        context += (
            f"\n\n[证据自检未通过——数值断言与数据重算不一致，请修正后重新输出最终 JSON 答案]\n{error_report}"
        )
        raw2 = llm.complete(ANSWER_SYSTEM_PROMPT, context, purpose="react_c2_selfcheck")
        llm_calls += 1
        parsed = _parse_answer(raw2) or {}
        if parsed.get("hypothesis"):
            answer = parsed
            raw = raw2
            trace.append({"step": llm_calls - 1, "kind": "selfcheck_answer"})
            rechecks = check_numeric_assertions(answer, all_rows)
            self_check["checks"] = rechecks
            self_check["n_fail"] = len([c for c in rechecks if c.get("status") == "fail"])
            self_check["causal_without_basis"] = causal_claims_without_basis(answer)
            self_check["corrective_round"] = True
    return GroupResult("C2", task.task_id, answer, raw, llm_calls, tool_calls, bool(answer.get("hypothesis")),
                       error="" if answer.get("hypothesis") else "未在步数预算内产出有效答案",
                       self_check=self_check, trace=trace)


GROUP_RUNNERS = {"A": run_group_a, "B": run_group_b, "C1": run_group_c1, "C2": run_group_c2}
