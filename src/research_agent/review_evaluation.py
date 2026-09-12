"""Reproducible rule evaluation and paired human review measurements.

Synthetic cases test decisions over already-structured evidence. They do not
measure extraction accuracy, LLM quality, real-user speed, or production value.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from .experiment_decision import build_experiment_decision_report
from .gate_aggregator import aggregate_final_decision
from .models import ExperimentPlan, StatisticsReport

RELEASE_DECISIONS = {"publishable", "proceed_to_paper"}


def evaluate_case(case: dict[str, Any]) -> str:
    inputs = dict(case["inputs"])
    if case["kind"] == "gate":
        override = inputs.pop("human_override", None)
        if override is not None:
            override = dict(override)
            if override.get("verdict_sha256") == "$current_evidence":
                override["verdict_sha256"] = aggregate_final_decision(**inputs).inputs["verdict_sha256"]
        return aggregate_final_decision(**inputs, human_override=override).status
    if case["kind"] == "experiment":
        plan = ExperimentPlan(case["id"], "Review supplied experiment evidence", [], [], [], [])
        statistics = StatisticsReport(case["id"], 3, "candidate", "baseline", [], [])
        return build_experiment_decision_report(plan, statistics, **inputs)["decision"]
    raise ValueError(f"unknown case kind: {case['kind']}")


def summarize_sessions(rows: list[dict[str, str]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Accept only complete, nonduplicated pairs; never silently drop bad data."""
    if not rows:
        return {"status": "not_measured", "participants": 0, "pairs": 0}
    expected = {case["id"]: case["expected"] for case in cases}
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        participant, pair = row["participant_id"].strip(), row["pair_id"].strip()
        condition, case_id = row["condition"], row["case_id"]
        seconds = float(row["seconds"])
        if not participant or not pair or condition not in {"manual", "assisted"} or case_id not in expected:
            raise ValueError("invalid participant, pair, condition, or case id")
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("seconds must be finite and positive")
        if not row["decision"].strip():
            raise ValueError("decision is required")
        group = pairs.setdefault((participant, pair), {})
        if condition in group:
            raise ValueError("duplicate participant/pair/condition")
        group[condition] = dict(row, seconds=seconds, expected=expected[case_id])
    savings = []
    for pair in pairs.values():
        if set(pair) != {"manual", "assisted"}:
            raise ValueError("each pair must include manual and assisted observations")
        if pair["manual"]["expected"] != pair["assisted"]["expected"]:
            raise ValueError("paired cases must have the same expected decision")
        savings.append(pair["manual"]["seconds"] - pair["assisted"]["seconds"])
    by_condition = {}
    for condition in ("manual", "assisted"):
        observations = [pair[condition] for pair in pairs.values()]
        blocked = [row for row in observations if row["expected"] not in RELEASE_DECISIONS]
        false_releases = sum(row["decision"] in RELEASE_DECISIONS for row in blocked)
        by_condition[condition] = {
            "observations": len(observations),
            "median_seconds": median(row["seconds"] for row in observations),
            "exact_decision_accuracy": sum(row["decision"] == row["expected"] for row in observations) / len(observations),
            "false_releases": false_releases,
            "nonrelease_cases": len(blocked),
            "false_release_rate": false_releases / len(blocked) if blocked else None,
        }
    return {
        "status": "user_supplied_observations",
        "participants": len({participant for participant, _ in pairs}),
        "pairs": len(pairs), "conditions": by_condition,
        "median_paired_seconds_saved": median(savings),
        "interpretation": "Descriptive only; observations are user supplied and not independently verified. Repeated cases and participant clustering limit inference.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--sessions", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.cases.read_bytes()
    cases = json.loads(raw)["cases"]
    if not cases or any(not str(case["id"]).strip() for case in cases) or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("case ids must be nonempty and unique")
    results = []
    for case in cases:
        start = perf_counter()
        actual = evaluate_case(case)
        results.append({"id": case["id"], "expected": case["expected"], "actual": actual,
                        "passed": actual == case["expected"], "rule_seconds": perf_counter() - start})
    rows = []
    if args.sessions:
        with args.sessions.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    report = {
        "schema_version": 1, "evidence_type": "synthetic_structured_rule_cases",
        "cases_sha256": hashlib.sha256(raw).hexdigest(),
        "decision_sources_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("gate_aggregator.py", "experiment_decision.py", "review_evaluation.py")
        },
        "sessions_sha256": hashlib.sha256(args.sessions.read_bytes()).hexdigest() if args.sessions else None,
        "total": len(results), "passed": sum(item["passed"] for item in results),
        "results": results, "business_measurements": summarize_sessions(rows, cases),
        "limitations": ["No online LLM calls or real-user evaluation in the synthetic suite.",
                        "Rule execution time is not human review time.",
                        "Expected labels are repository-authored, not an independent expert benchmark."],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['total']} synthetic cases passed; business measurements: {report['business_measurements']['status']}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
