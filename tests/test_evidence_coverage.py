"""证据验证覆盖率：显式保留通过、矛盾与不可验证声明的分母。"""
from __future__ import annotations

from research_copilot.analysis.evidence_validator import evidence_verification_coverage
from research_copilot.core.models import Finding, NumericAssertion, RelationClaim
from research_copilot.evaluation.metrics import aggregate_group, evidence_rates
from research_copilot.evaluation.runner import render_summary_markdown


def _finding(*, numeric_statuses=(), relation_statuses=(), l1_status="pass"):
    numeric = [NumericAssertion(metric=f"m{i}", value=float(i)) for i, _ in enumerate(numeric_statuses)]
    relations = [RelationClaim(variable_a=f"x{i}", variable_b="y", relation="positive") for i, _ in enumerate(relation_statuses)]
    return Finding(
        id="F-1",
        statement="structured finding",
        numeric_assertions=numeric,
        claims=relations,
        validation={
            "l1": {"status": l1_status},
            "l2": {
                "checks": [{"status": status} for status in numeric_statuses],
                "relation_checks": [{"status": status} for status in relation_statuses],
            },
        },
    )


def test_diagnosis_coverage_reports_pass_fail_and_unverifiable_separately():
    coverage = evidence_verification_coverage(
        [_finding(numeric_statuses=("pass", "fail", "unverifiable"))]
    )["numeric_assertions"]

    assert coverage["n_claims"] == 3
    assert coverage["n_programmatically_checked"] == 2
    assert coverage["coverage_rate"] == 0.6667
    assert coverage["verified_rate"] == 0.3333
    assert coverage["contradicted_rate"] == 0.3333
    assert coverage["unverifiable_rate"] == 0.3333


def test_diagnosis_coverage_all_passes():
    coverage = evidence_verification_coverage(
        [_finding(numeric_statuses=("pass",), relation_statuses=("pass",))]
    )

    assert coverage["numeric_assertions"]["coverage_rate"] == 1.0
    assert coverage["relation_claims"]["verified_rate"] == 1.0
    assert coverage["relation_claims"]["unverifiable_rate"] == 0.0


def test_diagnosis_coverage_all_unverifiable():
    coverage = evidence_verification_coverage(
        [_finding(numeric_statuses=("unverifiable",))]
    )["numeric_assertions"]

    assert coverage["coverage_rate"] == 0.0
    assert coverage["verified_rate"] == 0.0
    assert coverage["contradicted_rate"] == 0.0
    assert coverage["unverifiable_rate"] == 1.0


def test_l1_rejection_counts_claims_as_unverifiable():
    finding = Finding(
        id="F-1",
        statement="rejected finding",
        numeric_assertions=[NumericAssertion(metric="m", value=1.0)],
        claims=[RelationClaim(variable_a="x", variable_b="y", relation="positive")],
        validation={"l1": {"status": "fail"}, "l2": {"status": "not_applicable"}},
    )

    coverage = evidence_verification_coverage([finding])
    for kind in ("numeric_assertions", "relation_claims"):
        assert coverage[kind]["n_claims"] == 1
        assert coverage[kind]["coverage_rate"] == 0.0
        assert coverage[kind]["unverifiable_rate"] == 1.0


def test_empty_diagnosis_claims_have_no_rates():
    coverage = evidence_verification_coverage([])

    for kind in ("numeric_assertions", "relation_claims"):
        assert coverage[kind]["n_claims"] == 0
        assert coverage[kind]["coverage_rate"] is None
        assert coverage[kind]["verified_rate"] is None
        assert coverage[kind]["contradicted_rate"] is None
        assert coverage[kind]["unverifiable_rate"] is None


def test_benchmark_coverage_is_aggregated_and_rendered():
    checks = [{"status": "pass"}, {"status": "fail"}, {"status": "unverifiable"}]
    record = {
        "task_id": "real/test/dataset/metadata_0",
        "answer": {"hypothesis": "h"},
        "official": {"accuracy": 1.0},
        "unsupported": {
            "evaluable": True,
            "unsupported_conclusion_rate": 0.0,
            "numeric_checks": checks,
        },
    }

    evidence = evidence_rates([record])
    assert evidence["n_programmatically_checked"] == 2
    assert evidence["coverage_rate"] == 0.6667
    assert evidence["unverifiable_rate"] == 0.3333

    empty = evidence_rates([])
    assert empty["n_assertions"] == 0
    assert empty["coverage_rate"] is None

    aggregate = aggregate_group([record])
    summary = {
        "model": "test-model",
        "judge_model": "test-judge",
        "dry_run": False,
        "subset": "test",
        "task_ids": [record["task_id"]],
        "groups": ["A"],
        "honesty_note": "fixture",
        "group_summaries": {"A": aggregate},
        "comparisons": {},
    }
    rendered = render_summary_markdown(summary)
    assert aggregate["evidence"]["coverage_rate"] == 0.6667
    assert "程序复核覆盖率 0.6667" in rendered
    assert "此指标与诊断报告中的结构化主张覆盖率使用不同输入" in rendered
