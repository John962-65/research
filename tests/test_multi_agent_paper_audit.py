from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.models import ClaimTraceabilityItem, ClaimTraceabilityReport, ExperimentPlan, PaperClaimAudit, PaperReview, ResearchIdea
from research_agent.multi_agent_paper_audit import (
    build_multi_agent_paper_audit,
    render_multi_agent_paper_audit_markdown,
    write_multi_agent_paper_audit_artifacts,
)


class MultiAgentPaperAuditTest(unittest.TestCase):
    def test_passes_when_claim_owners_are_active(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _run_dir(tmp)

            report = build_multi_agent_paper_audit(
                "Iris classification benchmark smoke",
                _idea(),
                _plan(),
                _review(),
                _review(),
                _traceability(),
                _assignment(),
                run_dir,
            )
            rendered = render_multi_agent_paper_audit_markdown(report)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["claim_owner_summary"]["orphaned_claims"], 0)
            self.assertIn("Claim Role Matrix", rendered)
            self.assertTrue(any(check["name"] == "paper_role_family_coverage" and check["status"] == "pass" for check in report["checks"]))

    def test_blocks_missing_assignment_or_handoff_roles(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _run_dir(tmp)
            report = build_multi_agent_paper_audit(
                "Iris classification benchmark smoke",
                _idea(agent_roles=[]),
                _plan(agent_roles=[]),
                _review(),
                _review(),
                _traceability(),
                None,
                run_dir,
            )

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("02-agent-team" in issue for issue in report["blocking_issues"]))
            self.assertTrue(any("agent_roles" in issue for issue in report["blocking_issues"]))

    def test_review_required_when_writer_or_reviewer_owner_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _run_dir(tmp)
            assignment = _assignment(active_agents=["evidence_curator", "literature_scout", "benchmark_engineer", "statistician", "method_architect"])

            report = build_multi_agent_paper_audit(
                "Iris classification benchmark smoke",
                _idea(agent_roles=["method_architect", "evidence_curator"]),
                _plan(agent_roles=["method_architect", "evidence_curator", "benchmark_engineer", "statistician"]),
                _review(),
                _review(),
                _traceability(),
                assignment,
                run_dir,
            )

            self.assertEqual(report["status"], "review_required")
            self.assertGreater(report["claim_owner_summary"]["orphaned_claims"], 0)
            self.assertTrue(any("manuscript_editor" in task or "skeptical_reviewer" in task for task in report["manual_tasks"]))

    def test_write_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = _run_dir(tmp)

            report = write_multi_agent_paper_audit_artifacts(
                "Iris classification benchmark smoke",
                _idea(),
                _plan(),
                _review(),
                _review(),
                _traceability(),
                _assignment(),
                run_dir,
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue((run_dir / "10-agent-claim-audit.json").exists())
            self.assertIn("多智能体 Claim 审计", (run_dir / "10-agent-claim-audit.md").read_text(encoding="utf-8"))


def _run_dir(root: str) -> Path:
    run_dir = Path(root)
    for name in ["07-paper-review.json", "09-revised-paper.md", "10-revised-paper-review.json", "10-claim-traceability.json"]:
        (run_dir / name).write_text("{}", encoding="utf-8")
    return run_dir


def _assignment(active_agents: list[str] | None = None) -> dict[str, object]:
    active = active_agents or [
        "literature_scout",
        "evidence_curator",
        "method_architect",
        "benchmark_engineer",
        "statistician",
        "skeptical_reviewer",
        "manuscript_editor",
    ]
    return {
        "active_agents": active,
        "tasks": [{"agent_id": agent, "task": f"{agent} task", "status": "active"} for agent in active],
    }


def _idea(agent_roles: list[str] | None = None) -> ResearchIdea:
    return ResearchIdea(
        title="Nearest centroid smoke benchmark",
        hypothesis="candidate and baseline can be compared on frozen Iris split.",
        mechanism="Use fixed split and metric table.",
        expected_contribution="A reproducible smoke benchmark boundary.",
        novelty=3,
        feasibility=4,
        risk=1,
        evaluation=["accuracy", "macro_f1"],
        evidence_keys=["fisher1936iris"],
        baseline="majority baseline",
        agent_roles=agent_roles if agent_roles is not None else ["method_architect", "evidence_curator", "skeptical_reviewer"],
    )


def _plan(agent_roles: list[str] | None = None) -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="Nearest centroid smoke benchmark",
        objective="Run candidate, baseline and ablation on Iris.",
        variables=["model"],
        metrics=["accuracy", "macro_f1"],
        protocol=["Use frozen split.", "Repeat three times."],
        commands=[],
        baseline="majority baseline",
        evidence_keys=["fisher1936iris"],
        agent_roles=agent_roles if agent_roles is not None else ["method_architect", "evidence_curator", "benchmark_engineer", "statistician", "skeptical_reviewer"],
    )


def _review() -> PaperReview:
    return PaperReview(
        decision="revise",
        score=7.0,
        novelty=3,
        soundness=4,
        evidence_quality=4,
        reproducibility=4,
        summary="Claims are scoped to the run artifacts.",
        strengths=["Traceable run artifacts."],
        weaknesses=["Needs conservative claim boundary."],
        required_revisions=["Keep superiority claims out."],
        claim_audit=[_claim()],
    )


def _claim() -> PaperClaimAudit:
    return PaperClaimAudit(
        claim="candidate accuracy is reported from 04-results.json and bounded to the frozen split.",
        support_level="supported",
        evidence_keys=["fisher1936iris"],
        result_refs=["04-results.json", "04-statistics.json"],
        risk="low",
    )


def _traceability() -> ClaimTraceabilityReport:
    return ClaimTraceabilityReport(
        topic="Iris classification benchmark smoke",
        status="pass",
        traceability_score=1.0,
        total_claims=1,
        passed_claims=1,
        review_claims=0,
        blocked_claims=0,
        items=[
            ClaimTraceabilityItem(
                claim="candidate accuracy is reported from 04-results.json and bounded to the frozen split.",
                support_level="supported",
                decision="pass",
                citation_status="pass",
                result_status="pass",
                runbook_status="pass",
                evidence_keys=["fisher1936iris"],
                missing_evidence_keys=[],
                result_refs=["04-results.json", "04-statistics.json"],
                matched_result_refs=["04-results.json", "04-statistics.json"],
                issues=[],
            )
        ],
        blocking_issues=[],
        manual_tasks=[],
        evidence_inventory={"citations": 1, "result_refs": 2, "has_results": True, "has_statistics": True, "has_runbook": True, "execution_mode": "benchmark"},
    )


if __name__ == "__main__":
    unittest.main()
