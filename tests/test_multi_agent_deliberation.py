from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.multi_agent_deliberation import (
    build_multi_agent_deliberation,
    render_multi_agent_deliberation_markdown,
    write_multi_agent_deliberation_artifacts,
)


class MultiAgentDeliberationTest(unittest.TestCase):
    def test_all_agents_approve_when_upstream_audits_pass(self) -> None:
        report = build_multi_agent_deliberation(
            "Iris classification benchmark smoke",
            _assignment(),
            _agent_claim_audit(),
            _claim_traceability(),
            _citation_grounding(),
            _citation_coverage(),
            _results_presentation(),
            _claim_consistency(),
        )
        rendered = render_multi_agent_deliberation_markdown(report)

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["rules_status"], "pass")
        self.assertEqual(report["assessment_kind"], "deterministic_role_projection")
        self.assertFalse(report["independent_agent_execution"])
        self.assertEqual(report["consensus"]["decision"], "approve")
        self.assertEqual(len(report["agent_verdicts"]), 8)
        self.assertTrue(all(item["verdict"] == "approve" for item in report["agent_verdicts"]))
        self.assertIn("Agent Verdicts", rendered)

    def test_blocks_when_benchmark_evidence_lacks_runbook_or_results(self) -> None:
        traceability = _claim_traceability(evidence_inventory={"has_runbook": False, "has_results": False})

        report = build_multi_agent_deliberation(
            "Iris classification benchmark smoke",
            _assignment(),
            _agent_claim_audit(),
            traceability,
            _citation_grounding(),
            _citation_coverage(),
            _results_presentation(),
            _claim_consistency(),
        )

        self.assertEqual(report["status"], "block")
        benchmark = next(item for item in report["agent_verdicts"] if item["agent_id"] == "benchmark_engineer")
        self.assertEqual(benchmark["verdict"], "block")
        self.assertTrue(any("runbook/results" in issue for issue in report["blocking_issues"]))

    def test_review_required_when_source_and_evidence_agents_disagree(self) -> None:
        report = build_multi_agent_deliberation(
            "Iris classification benchmark smoke",
            _assignment(),
            _agent_claim_audit(),
            _claim_traceability(status="review_required", manual_tasks=["补 claim result refs"]),
            _citation_grounding(),
            _citation_coverage(),
            _results_presentation(),
            _claim_consistency(),
        )

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["consensus"]["decision"], "revise")
        self.assertTrue(any(conflict["type"] == "source_vs_evidence" for conflict in report["conflicts"]))

    def test_uses_paper_deliberation_route_when_present(self) -> None:
        assignment = _assignment()
        assignment["task_routes"] = [
            {
                "task_type": "paper_deliberation",
                "status": "active",
                "primary_agents": ["skeptical_reviewer", "manuscript_editor"],
                "support_agents": ["evidence_curator", "method_architect", "statistician"],
                "all_agents": ["skeptical_reviewer", "manuscript_editor", "evidence_curator", "method_architect", "statistician"],
            }
        ]

        report = build_multi_agent_deliberation(
            "Iris classification benchmark smoke",
            assignment,
            _agent_claim_audit(),
            _claim_traceability(),
            _citation_grounding(),
            _citation_coverage(),
            _results_presentation(),
            _claim_consistency(),
        )

        self.assertEqual(report["active_agents"], ["evidence_curator", "method_architect", "statistician", "skeptical_reviewer", "manuscript_editor"])
        self.assertEqual(len(report["agent_verdicts"]), 5)
        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["rules_status"], "pass")
        self.assertEqual(report["assessment_kind"], "deterministic_role_projection")
        self.assertFalse(report["independent_agent_execution"])

    def test_write_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            report = write_multi_agent_deliberation_artifacts(
                "Iris classification benchmark smoke",
                _assignment(),
                _agent_claim_audit(),
                _claim_traceability(),
                _citation_grounding(),
                _citation_coverage(),
                _results_presentation(),
                _claim_consistency(),
                run_dir,
            )

            self.assertEqual(report["status"], "review_required")
            self.assertEqual(report["rules_status"], "pass")
            self.assertEqual(report["assessment_kind"], "deterministic_role_projection")
            self.assertFalse(report["independent_agent_execution"])
            self.assertTrue((run_dir / "10-agent-deliberation.json").exists())
            self.assertIn("角色规则审计（非独立 Agent）", (run_dir / "10-agent-deliberation.md").read_text(encoding="utf-8"))


def _assignment() -> dict[str, object]:
    active = [
        "literature_scout",
        "evidence_curator",
        "gap_analyst",
        "method_architect",
        "benchmark_engineer",
        "statistician",
        "skeptical_reviewer",
        "manuscript_editor",
    ]
    return {"active_agents": active, "tasks": [{"agent_id": agent, "status": "active"} for agent in active]}


def _agent_claim_audit(status: str = "pass") -> dict[str, object]:
    return {
        "status": status,
        "active_agents": _assignment()["active_agents"],
        "claim_owner_summary": {"total_claims": 1, "mapped_claims": 1, "orphaned_claims": 0},
        "blocking_issues": [],
        "manual_tasks": [],
    }


def _claim_traceability(
    status: str = "pass",
    *,
    evidence_inventory: dict[str, object] | None = None,
    manual_tasks: list[str] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "total_claims": 1,
        "blocked_claims": 0,
        "review_claims": 0,
        "traceability_score": 1.0,
        "blocking_issues": [],
        "manual_tasks": manual_tasks or [],
        "evidence_inventory": evidence_inventory if evidence_inventory is not None else {"has_runbook": True, "has_results": True},
    }


def _citation_grounding(status: str = "pass") -> dict[str, object]:
    return {"status": status, "blocked_citations": 0, "grounding_score": 1.0, "blocking_issues": [], "manual_tasks": []}


def _citation_coverage(status: str = "pass") -> dict[str, object]:
    return {"status": status, "coverage_score": 1.0, "blocking_issues": [], "manual_tasks": []}


def _results_presentation(status: str = "pass") -> dict[str, object]:
    return {"status": status, "presentation_score": 1.0, "blocking_issues": [], "manual_tasks": []}


def _claim_consistency(status: str = "pass") -> dict[str, object]:
    return {"status": status, "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []}


if __name__ == "__main__":
    unittest.main()
