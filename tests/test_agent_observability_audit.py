from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.agent_observability_audit import (
    AGENT_OBSERVABILITY_AUDIT_JSON,
    AGENT_OBSERVABILITY_AUDIT_MD,
    build_agent_observability_audit_report,
    render_agent_observability_audit_markdown,
    write_agent_observability_audit_artifacts,
)
from research_agent.agent_observability_backfill import backfill_agent_observability_audits, render_agent_observability_backfill_markdown
from research_agent.artifacts import write_json


class AgentObservabilityAuditTest(unittest.TestCase):
    def test_passes_complete_observable_run(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_observable_run(run_dir)

            report = write_agent_observability_audit_artifacts("机械臂路径规划", run_dir)
            rendered = render_agent_observability_audit_markdown(report)
            saved = json.loads((run_dir / AGENT_OBSERVABILITY_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["blocking_issues"])
            self.assertTrue((run_dir / AGENT_OBSERVABILITY_AUDIT_MD).exists())
            self.assertEqual(saved["status"], "pass")
            self.assertIn("Agent Observability Audit", rendered)

    def test_blocks_missing_core_trace_files_and_human_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = build_agent_observability_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("run-manifest.json" in item for item in report["blocking_issues"]))
            self.assertTrue(any("run-llm-ledger.json" in item for item in report["blocking_issues"]))
            self.assertTrue(any("approval.json" in item for item in report["blocking_issues"]))

    def test_requires_review_when_llm_budget_pressure_is_high(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_observable_run(run_dir)
            write_json(
                run_dir / "run-config.json",
                {"llm": {"max_calls": 4, "max_prompt_chars": 200, "api_key": ""}},
            )

            report = build_agent_observability_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertTrue(any("预算压力" in item for item in report["warnings"]))
            self.assertTrue(any(item["name"] == "llm_budget_telemetry" and item["status"] == "review_required" for item in report["checks"]))

    def test_requires_review_when_llm_failures_are_recovered(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_observable_run(run_dir)
            write_json(
                run_dir / "run-llm-ledger.json",
                {
                    "total_calls": 2,
                    "successful_calls": 1,
                    "failed_calls": 1,
                    "budget_exceeded_calls": 0,
                    "total_prompt_chars": 180,
                    "entries": [
                        {"stage": "paper_writing", "purpose": "paper writing", "status": "failed", "duration_seconds": 0.1},
                        {"stage": "paper_writing", "purpose": "paper writing", "status": "success", "duration_seconds": 0.2},
                    ],
                },
            )

            report = build_agent_observability_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertFalse(report["blocking_issues"])
            self.assertTrue(any("同阶段 success 恢复" in item for item in report["warnings"]))

    def test_requires_review_when_runbook_artifact_trace_is_incomplete(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_observable_run(run_dir)
            runbook = json.loads((run_dir / "04-experiment-runbook.json").read_text(encoding="utf-8"))
            for run in runbook["runs"]:
                run["produced_artifacts"] = []
            write_json(run_dir / "04-experiment-runbook.json", runbook)

            report = build_agent_observability_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertTrue(any("produced_artifacts" in item for item in report["manual_tasks"]))
            self.assertTrue(any(item["name"] == "experiment_runtime_trace" and item["status"] == "review_required" for item in report["checks"]))

    def test_backfill_writes_observability_audit_for_existing_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            _write_complete_observable_run(run_dir)

            dry = backfill_agent_observability_audits(runs_dir, dry_run=True)
            rendered_dry = render_agent_observability_backfill_markdown(dry)

            self.assertEqual(dry["would_write"], 1)
            self.assertIn("Agent Observability Backfill", rendered_dry)
            self.assertFalse((run_dir / AGENT_OBSERVABILITY_AUDIT_JSON).exists())

            written = backfill_agent_observability_audits(runs_dir)
            rendered = render_agent_observability_backfill_markdown(written)

            self.assertEqual(written["written"], 1)
            self.assertEqual(written["items"][0]["status"], "pass")
            self.assertIn("legacy-run", rendered)
            self.assertTrue((run_dir / AGENT_OBSERVABILITY_AUDIT_JSON).exists())
            self.assertTrue((run_dir / AGENT_OBSERVABILITY_AUDIT_MD).exists())

            skipped = backfill_agent_observability_audits(runs_dir)
            self.assertEqual(skipped["skipped_existing"], 1)


def _write_complete_observable_run(run_dir: Path) -> None:
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(
        run_dir / "run-llm-ledger.json",
        {
            "total_calls": 4,
            "successful_calls": 4,
            "failed_calls": 0,
            "budget_exceeded_calls": 0,
            "total_prompt_chars": 180,
            "entries": [
                {"status": "success", "duration_seconds": 0.1},
                {"status": "success", "duration_seconds": 0.2},
            ],
        },
    )
    write_json(run_dir / "run-config.json", {"llm": {"max_calls": 10, "max_prompt_chars": 1000, "api_key": ""}})
    write_json(
        run_dir / "approval.json",
        {
            "approved": True,
            "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
        },
    )
    write_json(
        run_dir / "04-experiment-runbook.json",
        {
            "execution": {"mode": "simulated"},
            "runs": [
                {
                    "name": "candidate",
                    "seed": "seed-a",
                    "status": "simulated",
                    "duration_seconds": 0.01,
                    "produced_artifacts": [{"path": "experiments/candidate.txt", "bytes": 10, "sha256": "a" * 64}],
                },
                {
                    "name": "baseline",
                    "seed": "seed-b",
                    "status": "simulated",
                    "duration_seconds": 0.01,
                    "produced_artifacts": [{"path": "experiments/baseline.txt", "bytes": 10, "sha256": "b" * 64}],
                },
            ],
        },
    )
    write_json(
        run_dir / "12-repair-queue.json",
        {"status": "pass", "summary": {"total": 0, "block": 0, "high": 0, "medium": 0}, "items": []},
    )
    write_json(
        run_dir / "run-manifest.json",
        {
            "status": "completed",
            "events": [
                {"stage": f"stage-{index}", "status": "completed", "started_at": f"2026-01-01T00:00:{index:02d}Z", "completed_at": f"2026-01-01T00:00:{index:02d}Z"}
                for index in range(15)
            ],
            "artifacts": [
                {"path": "state.json", "bytes": 10, "sha256": "1" * 64},
                {"path": "run-manifest.json", "bytes": 10, "sha256": "2" * 64},
                {"path": "run-llm-ledger.json", "bytes": 10, "sha256": "3" * 64},
                {"path": "04-experiment-runbook.json", "bytes": 10, "sha256": "4" * 64},
            ],
        },
    )


if __name__ == "__main__":
    unittest.main()
