from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.code_data_availability import build_code_data_availability_report, render_code_data_availability_markdown
from research_agent.config import ExecutionConfig, ReleaseConfig
from research_agent.experiments import run_experiments
from research_agent.final_readiness import build_final_readiness_report
from research_agent.models import ExperimentCommand, ExperimentPlan, PaperClaimAudit, PaperReview, PaperRewriteReport
from research_agent.release_metadata import write_release_metadata_artifacts


class CodeDataAvailabilityTest(unittest.TestCase):
    def test_availability_report_audits_runbook_hashes_and_statements(self) -> None:
        plan = _plan()
        paper_md = "## 代码和数据可用性\n代码可用性和数据可用性将在正式发布前补充公开仓库、许可证和数据仓库。"
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            results = run_experiments(plan, ExecutionConfig(mode="simulated", repeats=2), run_dir)
            write_json(run_dir / "04-results.json", results)
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo benchmark"]})
            write_text(run_dir / "04-statistics.json", "{}")
            write_text(run_dir / "01-references.bib", "@article{demo,title={Demo}}")
            write_text(run_dir / "01-references.ris", "TY  - JOUR\nTI  - Demo\nER  -")

            report = build_code_data_availability_report("可用性审计", run_dir, paper_md)
            rendered = render_code_data_availability_markdown(report)

            self.assertEqual(report.status, "needs_human_release_metadata")
            self.assertTrue(report.ready_for_internal_release)
            self.assertFalse(report.ready_for_submission_check)
            self.assertFalse(report.blocking_issues)
            self.assertTrue(any(item.item == "实验产物哈希" and item.status == "pass" for item in report.checks))
            self.assertTrue(any("许可证" in task for task in report.manual_tasks))
            self.assertIn("Code Availability", rendered)
            runbook = json.loads((run_dir / "04-experiment-runbook.json").read_text(encoding="utf-8"))
            self.assertTrue(runbook["artifacts"])

    def test_structured_release_metadata_satisfies_release_checks(self) -> None:
        paper_md = "## 代码和数据可用性\n代码可用性和数据可用性已经通过结构化 release metadata 记录。"
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_availability_inputs(run_dir)
            write_release_metadata_artifacts("可用性审计", run_dir, _complete_release_config())

            report = build_code_data_availability_report("可用性审计", run_dir, paper_md)

            self.assertEqual(report.status, "ready_for_internal_release")
            self.assertFalse(report.blocking_issues)
            self.assertFalse(any("Release metadata" in task for task in report.manual_tasks))
            self.assertTrue(any(item.item == "Release metadata" and item.status == "pass" for item in report.checks))
            self.assertTrue(any(item.item == "公开仓库或归档 DOI" and item.status == "pass" for item in report.checks))
            self.assertTrue(any(item.item == "许可证" and item.status == "pass" and "release metadata" in item.evidence for item in report.checks))
            self.assertIn("https://github.com/example/research-agent", report.code_statement)
            self.assertIn("10.5281/zenodo.7654321", report.data_statement)

    def test_final_readiness_includes_availability_manual_tasks(self) -> None:
        original = _review(score=8.0, support_level="supported")
        revised = _review(score=8.2, support_level="supported")
        rewrite = PaperRewriteReport(
            topic="可用性审计",
            source_paper="06-paper.md",
            revised_paper="09-revised-paper.md",
            revision_plan="08-revision-plan.json",
            summary="已修订。",
            task_results=[],
            deferred_tasks=[],
            next_checks=[],
        )
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            results = run_experiments(_plan(), ExecutionConfig(mode="simulated", repeats=1), run_dir)
            write_json(run_dir / "04-results.json", results)
            write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo benchmark"]})
            write_text(run_dir / "04-statistics.json", "{}")
            write_text(run_dir / "01-references.bib", "@article{demo,title={Demo}}")
            write_text(run_dir / "01-references.ris", "TY  - JOUR\nTI  - Demo\nER  -")
            availability = build_code_data_availability_report(
                "可用性审计",
                run_dir,
                "## 代码和数据可用性\n代码可用性和数据可用性待公开发布。",
            )

            readiness = build_final_readiness_report("可用性审计", original, revised, rewrite, availability)

            self.assertEqual(readiness.availability_status, "needs_human_release_metadata")
            self.assertEqual(readiness.status, "ready_for_submission_check")
            self.assertTrue(readiness.availability_manual_tasks)
            self.assertFalse(readiness.blocking_issues)


def _plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="可用性审计",
        objective="验证审计产物是否完整。",
        variables=["mode"],
        metrics=["success_rate", "runtime_cost"],
        protocol=["运行候选命令", "记录产物"],
        commands=[
            ExperimentCommand(name="simulate_artifact_pipeline", command=["python3", "simulate.py", "--mode", "artifact"]),
            ExperimentCommand(name="simulate_baseline_pipeline", command=["python3", "simulate.py", "--mode", "baseline"]),
        ],
    )


def _review(score: float, support_level: str) -> PaperReview:
    return PaperReview(
        decision="accept",
        score=score,
        novelty=4,
        soundness=4,
        evidence_quality=4,
        reproducibility=4,
        summary="通过。",
        strengths=[],
        weaknesses=[],
        required_revisions=[],
        claim_audit=[
            PaperClaimAudit(
                claim="当前实验支持该结论。",
                support_level=support_level,
                evidence_keys=["demo2024"],
                result_refs=["04-results.json"],
                risk="low",
            )
        ],
    )


def _write_complete_availability_inputs(run_dir: Path) -> None:
    experiment_dir = run_dir / "experiments"
    experiment_dir.mkdir(parents=True)
    write_text(experiment_dir / "metrics.txt", "success=1.0")
    write_json(
        run_dir / "04-experiment-runbook.json",
        {
            "execution": {"mode": "local", "repeats": 2, "timeout_seconds": 60},
            "runs": [{"name": "candidate", "seed": "seed-a"}, {"name": "baseline", "seed": "seed-b"}],
            "artifacts": [{"path": "experiments/metrics.txt", "sha256": "placeholder"}],
        },
    )
    write_json(run_dir / "04-results.json", [{"name": "candidate", "status": "passed"}])
    write_text(run_dir / "04-results.csv", "name,status\ncandidate,passed\n")
    write_json(run_dir / "04-statistics.json", {"comparisons": []})
    write_json(run_dir / "03-benchmark-plan.json", {"selected_names": ["demo benchmark"]})
    write_text(run_dir / "01-references.bib", "@article{demo,title={Demo}}")
    write_text(run_dir / "01-references.ris", "TY  - JOUR\nTI  - Demo\nER  -")


def _complete_release_config() -> ReleaseConfig:
    return ReleaseConfig(
        code_repository_url="https://github.com/example/research-agent",
        code_archive_doi="10.5281/zenodo.1234567",
        code_license="Apache-2.0",
        code_version="v0.1.0",
        data_repository_url="https://zenodo.org/records/7654321",
        data_archive_doi="10.5281/zenodo.7654321",
        data_access_statement="All benchmark data are available from the archived public record.",
        environment_url="https://github.com/example/research-agent/releases/tag/v0.1.0",
        release_notes="First reproducibility release for audit testing.",
    )


if __name__ == "__main__":
    unittest.main()
