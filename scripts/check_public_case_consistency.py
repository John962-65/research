#!/usr/bin/env python3
"""公开案例一致性检查（T16/T20）：CASE-REPORT.md 与 replay-summary.json 的
计数、状态必须与目录内产物一致；发现漂移即失败（供 CI 调用）。

用法：python3 scripts/check_public_case_consistency.py runs/public-iris-case-replay
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_json_safe(path: Path) -> dict:
    try:
        return _read_json(path)
    except (OSError, ValueError):
        return {}


def check_case_dir(case_dir: Path) -> list[str]:
    problems: list[str] = []
    report_path = case_dir / "CASE-REPORT.md"
    summary_path = case_dir / "replay-summary.json"
    if not report_path.exists():
        return [f"缺少 {report_path}"]
    report = report_path.read_text(encoding="utf-8")
    attempts = _read_json(case_dir / "04-experiment-attempts.json").get("attempts") or []
    decision = _read_json(case_dir / "04-experiment-decision.json")
    integrity = _read_json(case_dir / "04-evidence-integrity.json")
    contract = _read_json(case_dir / "03-idea-experiment-contract.json")

    total = len(attempts)
    interrupted = sum(1 for a in attempts if a.get("status") == "interrupted")
    states = decision.get("decision_states") or {}

    # 报告中的尝试总数与中断数必须与账本一致。
    m = re.search(r"执行尝试总数：\*\*(\d+)\*\*（passed=(\d+)，interrupted=(\d+)", report)
    if not m:
        problems.append("CASE-REPORT 缺少标准化的尝试总数行")
    else:
        total_r, passed_r, interrupted_r = (int(g) for g in m.groups())
        if total_r != total:
            problems.append(f"报告尝试总数 {total_r} != 账本 {total}")
        if interrupted_r != interrupted:
            problems.append(f"报告 interrupted {interrupted_r} != 账本 {interrupted}")
        if passed_r != sum(1 for a in attempts if a.get("status") == "passed"):
            problems.append(f"报告 passed {passed_r} != 账本")

    # 状态行必须与决策/证据产物一致。
    for label, actual in (
        (f"execution={states.get('execution_status')}", states.get("execution_status")),
        (f"evidence={integrity.get('experiment_evidence_status')}", integrity.get("experiment_evidence_status")),
        (f"outcome={states.get('research_outcome')}", states.get("research_outcome")),
    ):
        if label not in report:
            problems.append(f"CASE-REPORT 缺少与产物一致的状态：{label}")
    for forbidden in ("not_assessed/not_supported", f"尝试总数：**{total + 1}**", f"尝试总数：**{total - 1}**"):
        if forbidden in report:
            problems.append(f"CASE-REPORT 出现漂移内容：{forbidden}")

    # 决策主指标必须来自契约。
    primary = ((contract.get("contract") or {}).get("evaluation") or {}).get("primary_metrics") or []
    if decision.get("primary_metrics") != primary:
        problems.append(f"决策主指标 {decision.get('primary_metrics')} != 契约 {primary}")

    # replay summary（若存在）必须与产物一致。
    if summary_path.exists():
        summary = _read_json(summary_path)
        if summary.get("attempts_total") != total:
            problems.append(f"summary.attempts_total {summary.get('attempts_total')} != {total}")
        if summary.get("interrupted_count") != interrupted:
            problems.append(f"summary.interrupted_count {summary.get('interrupted_count')} != {interrupted}")
        if summary.get("decision") != decision.get("decision"):
            problems.append("summary.decision 与决策产物不一致")
        if summary.get("contract_digest") != contract.get("contract_digest"):
            problems.append("summary.contract_digest 与契约产物不一致")
        # 契约摘要必须重算一致（防"改内容留旧 digest"）。
        from research_agent.idea_experiment_contract import compute_contract_digest  # type: ignore

        recomputed = compute_contract_digest(contract.get("contract") or {})
        if (contract.get("contract") or {}).get("digest") != recomputed:
            problems.append("契约 digest 字段与内容重算不一致")
        # 复审第 9 轮第 5 项：执行绑定摘要必须与当前契约一致，且不存在
        # 未处理的重跑要求（执行前冻结 → 执行时绑定 → 执行后校验）。
        runbook = _read_json_safe(case_dir / "04-experiment-runbook.json")
        binding = (runbook.get("contract_binding") or {}).get("contract_digest") if isinstance(runbook.get("contract_binding"), dict) else ""
        if not binding:
            problems.append("04-experiment-runbook 缺少契约绑定（契约未在执行前冻结）")
        elif binding != recomputed:
            problems.append(f"执行绑定摘要 {binding[:12]} 与当前契约 {recomputed[:12]} 不一致")
        history = _read_json_safe(case_dir / "03-experiment-contract-history.json").get("entries") or []
        unhandled = [e for e in history if e.get("rerun_required") and not e.get("resolved")]
        if unhandled:
            problems.append(f"契约历史存在 {len(unhandled)} 条未处理的重跑要求（rerun_required=true）")
    return problems


def main() -> int:
    case_dirs = [Path(arg) for arg in sys.argv[1:]] or [Path("runs/public-iris-case-replay")]
    failures = 0
    for case_dir in case_dirs:
        problems = check_case_dir(case_dir)
        status = "PASS" if not problems else "FAIL"
        print(f"[{status}] {case_dir}")
        for problem in problems:
            print(f"  - {problem}")
        failures += len(problems)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
