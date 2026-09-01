from __future__ import annotations

from typing import Any


_RECOVERABLE_STATUSES = {"failed", "budget_exceeded"}

_STAGE_RULES = [
    ("research_planning", ["research planning"]),
    ("online_search_query_planning", ["online search query planning", "academic search query planning"]),
    ("literature_synthesis", ["literature synthesis"]),
    ("idea_generation", ["research ideas"]),
    ("experiment_planning", ["experiment planning"]),
    ("paper_writing", ["paper writing"]),
    ("paper_review_loop", ["scientific peer review"]),
    ("paper_revision", ["paper revision"]),
]


def summarize_llm_failure_recovery(ledger: Any) -> dict[str, Any]:
    if not isinstance(ledger, dict):
        return _empty_summary()
    entries = _dicts(ledger.get("entries"))
    failed_total = _safe_int(ledger.get("failed_calls"))
    budget_total = _safe_int(ledger.get("budget_exceeded_calls"))
    if not entries:
        return {
            "failed_total": failed_total,
            "budget_exceeded_total": budget_total,
            "recovered_failed_calls": 0,
            "unrecovered_failed_calls": failed_total,
            "recovered_budget_exceeded_calls": 0,
            "unrecovered_budget_exceeded_calls": budget_total,
            "recovered_entries": [],
            "unrecovered_entries": [],
        }

    later_successes: list[set[str]] = [set() for _ in entries]
    seen_successes: set[str] = set()
    for index in range(len(entries) - 1, -1, -1):
        later_successes[index] = set(seen_successes)
        if str(entries[index].get("status") or "") == "success":
            seen_successes.add(_stage_key(entries[index]))

    recovered: list[str] = []
    unrecovered: list[str] = []
    recovered_failed = 0
    recovered_budget = 0
    unrecovered_failed = 0
    unrecovered_budget = 0
    entry_failed = 0
    entry_budget = 0
    for index, entry in enumerate(entries):
        status = str(entry.get("status") or "")
        if status not in _RECOVERABLE_STATUSES:
            continue
        key = _stage_key(entry)
        label = f"{key}:{status}#{index + 1}"
        is_recovered = key in later_successes[index]
        if status == "failed":
            entry_failed += 1
            if is_recovered:
                recovered_failed += 1
                recovered.append(label)
            else:
                unrecovered_failed += 1
                unrecovered.append(label)
        elif status == "budget_exceeded":
            entry_budget += 1
            if is_recovered:
                recovered_budget += 1
                recovered.append(label)
            else:
                unrecovered_budget += 1
                unrecovered.append(label)

    missing_failed = max(0, failed_total - entry_failed)
    missing_budget = max(0, budget_total - entry_budget)
    return {
        "failed_total": failed_total,
        "budget_exceeded_total": budget_total,
        "recovered_failed_calls": recovered_failed,
        "unrecovered_failed_calls": unrecovered_failed + missing_failed,
        "recovered_budget_exceeded_calls": recovered_budget,
        "unrecovered_budget_exceeded_calls": unrecovered_budget + missing_budget,
        "recovered_entries": recovered[:8],
        "unrecovered_entries": unrecovered[:8],
    }


def all_llm_failures_recovered(ledger: Any) -> bool:
    summary = summarize_llm_failure_recovery(ledger)
    return not summary["unrecovered_failed_calls"] and not summary["unrecovered_budget_exceeded_calls"]


def _stage_key(entry: dict[str, Any]) -> str:
    stage = str(entry.get("stage") or "").strip().lower()
    if stage:
        return stage
    purpose = str(entry.get("purpose") or "").strip()
    lowered = purpose.lower()
    for stage_id, needles in _STAGE_RULES:
        if any(needle in lowered for needle in needles):
            return stage_id
    return "other:" + " ".join(lowered.split())[:80]


def _empty_summary() -> dict[str, Any]:
    return {
        "failed_total": 0,
        "budget_exceeded_total": 0,
        "recovered_failed_calls": 0,
        "unrecovered_failed_calls": 0,
        "recovered_budget_exceeded_calls": 0,
        "unrecovered_budget_exceeded_calls": 0,
        "recovered_entries": [],
        "unrecovered_entries": [],
    }


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
