from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.agent_trajectory import (
    AGENT_TRAJECTORY_JSON,
    AGENT_TRAJECTORY_MD,
    build_agent_trajectory_report,
    render_agent_trajectory_markdown,
    write_agent_trajectory_artifacts,
)
from research_agent.agent_trajectory_backfill import backfill_agent_trajectories, render_agent_trajectory_backfill_markdown
from research_agent.artifacts import write_json
from research_agent.manifest_backfill import backfill_run_manifests, build_backfilled_manifest, render_manifest_backfill_markdown


class AgentTrajectoryTest(unittest.TestCase):
    def test_trajectory_groups_manifest_events_and_gate_statuses(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_minimal_run(run_dir)

            report = write_agent_trajectory_artifacts("机械臂路径规划", run_dir)
            rendered = render_agent_trajectory_markdown(report)
            saved = json.loads((run_dir / AGENT_TRAJECTORY_JSON).read_text(encoding="utf-8"))
            md_exists = (run_dir / AGENT_TRAJECTORY_MD).exists()

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["event_count"], 9)
        self.assertEqual(saved["status"], "pass")
        self.assertTrue(any(phase["phase_id"] == "literature_grounding" and phase["status"] == "pass" for phase in report["phases"]))
        self.assertTrue(any(event["stage"] == "agent_stage_contract" for event in report["timeline"]))
        self.assertIn("Agent Trajectory", rendered)
        self.assertTrue(md_exists)

    def test_trajectory_blocks_unapproved_human_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_minimal_run(run_dir)
            write_json(run_dir / "approval.json", {"approved": False, "blocks": []})

            report = build_agent_trajectory_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        phase = next(item for item in report["phases"] if item["phase_id"] == "human_gate")
        self.assertEqual(phase["status"], "block")
        self.assertTrue(any("review gate" in item for item in report["blocking_issues"]))

    def test_trajectory_warns_on_started_phase_missing_required_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_minimal_run(run_dir)
            (run_dir / "04-statistics.json").unlink()

            report = build_agent_trajectory_report("机械臂路径规划", run_dir)

        phase = next(item for item in report["phases"] if item["phase_id"] == "execution_analysis")
        self.assertEqual(phase["status"], "warn")
        self.assertIn("04-statistics.json", phase["missing_artifacts"])

    def test_trajectory_counts_backfilled_manifest_events(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_minimal_run(run_dir)
            manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
            manifest["events"][0]["status"] = "backfilled"
            manifest["events"][1]["metrics"]["backfilled"] = True
            write_json(run_dir / "run-manifest.json", manifest)

            report = build_agent_trajectory_report("机械臂路径规划", run_dir)
            rendered = render_agent_trajectory_markdown(report)

        self.assertEqual(report["summary"]["backfilled_events"], 2)
        self.assertIn("backfilled=2", rendered)

    def test_backfill_writes_missing_trajectory_artifacts_and_skips_existing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            noise_dir = runs_dir / "not-a-run"
            run_dir.mkdir(parents=True)
            noise_dir.mkdir()
            _write_minimal_run(run_dir)

            dry = backfill_agent_trajectories(runs_dir, dry_run=True)
            self.assertFalse((run_dir / AGENT_TRAJECTORY_JSON).exists())

            written = backfill_agent_trajectories(runs_dir)
            rendered = render_agent_trajectory_backfill_markdown(written)
            skipped = backfill_agent_trajectories(runs_dir)
            json_exists = (run_dir / AGENT_TRAJECTORY_JSON).exists()
            md_exists = (run_dir / AGENT_TRAJECTORY_MD).exists()

        self.assertEqual(dry["would_write"], 1)
        self.assertEqual(dry["skipped_no_state"], 1)
        self.assertEqual(written["written"], 1)
        self.assertEqual(written["items"][0]["status"], "pass")
        self.assertEqual(skipped["skipped_existing"], 1)
        self.assertIn("Agent Trajectory Backfill", rendered)
        self.assertTrue(json_exists)
        self.assertTrue(md_exists)

    def test_backfill_force_rewrites_existing_trajectory_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "stale-run"
            run_dir.mkdir(parents=True)
            _write_minimal_run(run_dir)
            write_json(run_dir / AGENT_TRAJECTORY_JSON, {"status": "stale"})
            (run_dir / AGENT_TRAJECTORY_MD).write_text("stale", encoding="utf-8")

            report = backfill_agent_trajectories(runs_dir, force=True)
            saved = json.loads((run_dir / AGENT_TRAJECTORY_JSON).read_text(encoding="utf-8"))

        self.assertEqual(report["written"], 1)
        self.assertEqual(report["items"][0]["action"], "overwrite")
        self.assertEqual(saved["status"], "pass")

    def test_manifest_backfill_builds_backfilled_events_and_artifact_inventory(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "legacy-run"
            run_dir.mkdir()
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / "00-research-plan.json", {"topic": "机械臂路径规划"})
            write_json(run_dir / "01-context.json", {"citations": []})
            (run_dir / "01-review-gate.md").write_text("gate", encoding="utf-8")
            write_json(run_dir / "approval.json", {"approved": True})
            write_json(run_dir / "02-ideas.json", [{"title": "idea"}])

            manifest = build_backfilled_manifest(run_dir)

        stages = [event.stage for event in manifest.events]
        self.assertIn("research_plan", stages)
        self.assertIn("literature_context", stages)
        self.assertIn("review_approval", stages)
        self.assertIn("ideation", stages)
        self.assertEqual(manifest.events[-1].stage, "completed")
        self.assertTrue(all(event.status == "backfilled" for event in manifest.events))
        self.assertTrue(any(item.path == "state.json" and item.sha256 for item in manifest.artifacts))

    def test_manifest_backfill_writes_and_skips_existing_manifests(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            noise_dir = runs_dir / "not-a-run"
            run_dir.mkdir(parents=True)
            noise_dir.mkdir()
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / "00-research-plan.json", {"topic": "机械臂路径规划"})

            dry = backfill_run_manifests(runs_dir, dry_run=True)
            self.assertFalse((run_dir / "run-manifest.json").exists())
            written = backfill_run_manifests(runs_dir)
            rendered = render_manifest_backfill_markdown(written)
            skipped = backfill_run_manifests(runs_dir)
            saved = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(dry["would_write"], 1)
        self.assertEqual(dry["skipped_no_state"], 1)
        self.assertEqual(written["written"], 1)
        self.assertEqual(skipped["skipped_existing"], 1)
        self.assertIn("Run Manifest Backfill", rendered)
        self.assertTrue(saved["events"])
        self.assertTrue(saved["artifacts"])


def _write_minimal_run(run_dir: Path) -> None:
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(
        run_dir / "run-manifest.json",
        {
            "status": "completed",
            "events": [
                {"stage": "research_plan", "status": "completed", "outputs": ["00-research-plan.json"], "metrics": {"status": "ok"}},
                {"stage": "literature_review", "status": "completed", "outputs": ["01-context.json"], "metrics": {"papers": 8}},
                {"stage": "review_approval", "status": "completed", "outputs": ["approval.json"], "metrics": {"approved": True}},
                {"stage": "ideation", "status": "completed", "outputs": ["02-ideas.json"], "metrics": {"ideas": 4}},
                {"stage": "experiment_plan", "status": "completed", "outputs": ["03-experiment-plan.json"], "metrics": {"status": "pass"}},
                {"stage": "experiments", "status": "completed", "outputs": ["04-statistics.json"], "metrics": {"runs": 2}},
                {"stage": "paper_revision", "status": "completed", "outputs": ["09-revised-paper.md"], "metrics": {"tasks": 1}},
                {"stage": "llm_observability_summary", "status": "completed", "outputs": ["13-llm-observability-summary.json"], "metrics": {"status": "pass"}},
                {"stage": "agent_stage_contract", "status": "completed", "outputs": ["13-agent-stage-contract.json"], "metrics": {"status": "pass"}},
            ],
            "artifacts": [{"path": "state.json"}, {"path": "run-manifest.json"}],
        },
    )
    for path, payload in [
        ("00-preflight.json", {"status": "pass"}),
        ("00-research-plan.json", {"topic": "机械臂路径规划"}),
        ("01-context.json", {"citations": [{"key": "a"}]}),
        ("01-query-execution-audit.json", {"status": "pass"}),
        ("01-literature-evidence-mix.json", {"status": "pass"}),
        ("01-literature-rescue-plan.json", {"status": "pass"}),
        ("01-literature-metadata-audit.json", {"status": "pass", "blocked": 0}),
        ("01-citation-audit.json", {"status": "pass", "blocked_citations": 0}),
        ("approval.json", {"approved": True, "blocks": ["idea_generation", "experiment_planning", "experiment_execution"]}),
        ("01-review-constraints.json", {"status": "pass", "constraints": []}),
        ("02-ideas.json", {"ideas": [{"title": "A"}]}),
        ("02-exploration-map.json", {"selected_branch_id": "B1"}),
        ("02-experiment-manager.json", {"status": "pass"}),
        ("02-idea-audit.json", {"status": "pass", "blocked": 0}),
        ("03-experiment-plan.json", {"commands": [{"name": "run"}]}),
        ("03-review-constraint-compliance.json", {"status": "pass", "blocked": 0, "review_required": 0}),
        ("03-experiment-audit.json", {"status": "pass"}),
        ("03-idea-experiment-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("03-execution-safety-audit.json", {"status": "pass"}),
        ("03-benchmark-readiness.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("04-experiment-runbook.json", {"runs": [{"name": "candidate"}]}),
        ("04-statistics.json", {"comparisons": [{"metric": "success"}]}),
        ("04-result-validation.json", {"status": "pass"}),
        ("04-benchmark-result-schema-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("04-failure-analysis.json", {"status": "pass"}),
        ("04-benchmark-evidence-audit.json", {"status": "pass", "evidence_grade": "real_benchmark"}),
        ("04-hypothesis-outcome.json", {"status": "pass", "outcome": "supported"}),
        ("04-claim-boundary-preflight.json", {"status": "pass", "blocking_issues": [], "warnings": []}),
        ("07-paper-review-calibration.json", {"status": "pass"}),
        ("09-revision-response-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("10-claim-traceability.json", {"status": "pass"}),
        ("10-agent-claim-audit.json", {"status": "pass"}),
        ("10-agent-deliberation.json", {"status": "pass"}),
        ("10-citation-grounding.json", {"status": "pass"}),
        ("10-citation-coverage.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("10-results-presentation.json", {"status": "pass"}),
        ("10-claim-consistency.json", {"status": "pass"}),
        ("10-code-data-availability.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("10-submission-check.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("10-final-readiness.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("11-submission-package.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("12-repair-queue.json", {"status": "pass", "summary": {"total": 0}, "blocking_issues": [], "manual_tasks": []}),
        ("12-repair-resolution-audit.json", {"status": "not_applicable", "blocking_issues": [], "manual_tasks": []}),
        ("13-agent-stage-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []}),
        ("13-llm-observability-summary.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []}),
        ("13-research-scorecard.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []}),
        ("14-run-integrity-audit.json", {"status": "pass", "blocking_issues": [], "warnings": []}),
    ]:
        write_json(run_dir / path, payload)
    for path in ["01-review-gate.md", "06-paper.md", "09-revised-paper.md"]:
        (run_dir / path).write_text(path, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
