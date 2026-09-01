from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.human_gate_audit import HUMAN_GATE_AUDIT_JSON, HUMAN_GATE_AUDIT_MD
from research_agent.human_gate_audit_backfill import backfill_human_gate_audits, render_human_gate_audit_backfill_markdown


class HumanGateAuditBackfillTest(unittest.TestCase):
    def test_backfill_writes_without_approving_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / "approval.json", {"approved": False, "blocks": []})
            write_json(run_dir / "02-ideas.json", [{"title": "idea"}])

            report = backfill_human_gate_audits(runs_dir)
            rendered = render_human_gate_audit_backfill_markdown(report)

            self.assertEqual(report["written"], 1)
            self.assertTrue((run_dir / HUMAN_GATE_AUDIT_JSON).exists())
            self.assertTrue((run_dir / HUMAN_GATE_AUDIT_MD).exists())
            self.assertIn("不会补写 approval", rendered)
            saved_approval = (run_dir / "approval.json").read_text(encoding="utf-8")
            self.assertIn('"approved": false', saved_approval)

    def test_existing_skips_unless_forced(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})

            backfill_human_gate_audits(runs_dir)
            skipped = backfill_human_gate_audits(runs_dir)
            forced = backfill_human_gate_audits(runs_dir, force=True)

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written"], 1)


if __name__ == "__main__":
    unittest.main()
