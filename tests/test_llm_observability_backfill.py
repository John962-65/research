from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.llm_observability_backfill import backfill_llm_observability, render_llm_observability_backfill_markdown


class LlmObservabilityBackfillTest(unittest.TestCase):
    def test_backfill_writes_missing_audits_without_creating_ledger(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            dry = backfill_llm_observability(runs_dir, dry_run=True)
            report = backfill_llm_observability(runs_dir)
            rendered = render_llm_observability_backfill_markdown(report)
            trace = json.loads((run_dir / "13-llm-trace-audit.json").read_text(encoding="utf-8"))
            runtime = json.loads((run_dir / "13-llm-runtime-contract.json").read_text(encoding="utf-8"))
            economics = json.loads((run_dir / "13-run-economics-audit.json").read_text(encoding="utf-8"))
            observability = json.loads((run_dir / "13-agent-observability-audit.json").read_text(encoding="utf-8"))
            summary = json.loads((run_dir / "13-llm-observability-summary.json").read_text(encoding="utf-8"))
            ledger_exists = (run_dir / "run-llm-ledger.json").exists()

        self.assertEqual(dry["would_write_trace"], 1)
        self.assertEqual(dry["would_write_runtime"], 1)
        self.assertEqual(dry["would_write_economics"], 1)
        self.assertEqual(dry["would_write_observability"], 1)
        self.assertEqual(dry["would_write_summary"], 1)
        self.assertEqual(report["trace_written"], 1)
        self.assertEqual(report["runtime_written"], 1)
        self.assertEqual(report["economics_written"], 1)
        self.assertEqual(report["observability_written"], 1)
        self.assertEqual(report["summary_written"], 1)
        self.assertEqual(trace["status"], "block")
        self.assertEqual(runtime["status"], "block")
        self.assertEqual(economics["status"], "block")
        self.assertEqual(observability["status"], "block")
        self.assertEqual(summary["status"], "block")
        self.assertFalse(ledger_exists)
        self.assertIn("LLM Observability Backfill", rendered)
        self.assertIn("legacy-run", rendered)
        self.assertIn("Summary 写入", rendered)
        self.assertIn("Runtime Contract 写入", rendered)
        self.assertIn("不创建或修改 run-llm-ledger.json", rendered)

    def test_backfill_skips_existing_without_force(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "已有产物", "stage": "completed"})
            backfill_llm_observability(runs_dir)

            skipped = backfill_llm_observability(runs_dir)

        self.assertEqual(skipped["skipped_existing"], 1)
        self.assertEqual(skipped["trace_written"], 0)
        self.assertEqual(skipped["runtime_written"], 0)
        self.assertEqual(skipped["economics_written"], 0)
        self.assertEqual(skipped["observability_written"], 0)
        self.assertEqual(skipped["summary_written"], 0)


if __name__ == "__main__":
    unittest.main()
