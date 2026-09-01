from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_gate_backfill import backfill_literature_gate_decisions, render_literature_gate_backfill_markdown
from research_agent.literature_gate_decision import LITERATURE_GATE_DECISION_JSON, LITERATURE_GATE_DECISION_MD, LITERATURE_GATE_DECISION_SCHEMA_VERSION
from research_agent.literature_evidence_contract import LITERATURE_EVIDENCE_CONTRACT_JSON, LITERATURE_EVIDENCE_CONTRACT_MD


class LiteratureGateBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_minimal_literature_run(run_dir)

            report = backfill_literature_gate_decisions(runs_dir, dry_run=True)
            rendered = render_literature_gate_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write"], 1)
            self.assertFalse((run_dir / LITERATURE_GATE_DECISION_JSON).exists())
            self.assertFalse((run_dir / LITERATURE_EVIDENCE_CONTRACT_JSON).exists())
            self.assertIn("不会批准 review gate", rendered)

    def test_write_creates_gate_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_minimal_literature_run(run_dir)

            report = backfill_literature_gate_decisions(runs_dir)
            saved = (run_dir / LITERATURE_GATE_DECISION_JSON).read_text(encoding="utf-8")

            self.assertEqual(report["written"], 1)
            self.assertTrue((run_dir / LITERATURE_GATE_DECISION_MD).exists())
            self.assertIn("review_required", saved)

    def test_backfill_reads_context_and_citation_grounding(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_minimal_literature_run(run_dir)
            write_json(
                run_dir / "01-context.json",
                {
                    "topic": "机械臂路径规划",
                    "citations": [{"key": "a"}, {"key": "b"}],
                    "chunks": [{"citation_key": "a"}, {"citation_key": "b"}],
                    "claim_support": [{"claim": "baseline"}],
                    "review_gate": {"status": "pass"},
                },
            )
            write_json(
                run_dir / "10-citation-grounding.json",
                {
                    "status": "block",
                    "grounding_score": 0.4,
                    "blocked_citations": 1,
                    "review_citations": 0,
                    "passed_citations": 1,
                    "total_citations": 2,
                    "blocking_issues": ["private grounding issue should stay local"],
                },
            )

            report = backfill_literature_gate_decisions(runs_dir)
            saved = (run_dir / LITERATURE_GATE_DECISION_JSON).read_text(encoding="utf-8")

            self.assertEqual(report["written"], 1)
            self.assertTrue((run_dir / LITERATURE_EVIDENCE_CONTRACT_JSON).exists())
            self.assertTrue((run_dir / LITERATURE_EVIDENCE_CONTRACT_MD).exists())
            self.assertIn('"citation_grounding_status": "block"', saved)
            self.assertIn('"context_chunks": 2', saved)
            self.assertNotIn("private grounding issue should stay local", report["items"][0])

    def test_existing_skips_unless_forced(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_minimal_literature_run(run_dir)
            backfill_literature_gate_decisions(runs_dir)

            skipped = backfill_literature_gate_decisions(runs_dir)
            forced = backfill_literature_gate_decisions(runs_dir, force=True)

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written"], 1)

    def test_existing_outdated_gate_is_refreshed_without_force(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_minimal_literature_run(run_dir)
            write_json(run_dir / LITERATURE_GATE_DECISION_JSON, {"schema_version": 1, "status": "review_required", "summary": {}})
            (run_dir / LITERATURE_GATE_DECISION_MD).write_text("# old\n", encoding="utf-8")

            report = backfill_literature_gate_decisions(runs_dir)
            saved = (run_dir / LITERATURE_GATE_DECISION_JSON).read_text(encoding="utf-8")

            self.assertEqual(report["refreshed_outdated"], 1)
            self.assertIn(f'"schema_version": {LITERATURE_GATE_DECISION_SCHEMA_VERSION}', saved)


def _write_minimal_literature_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "awaiting_review_approval"})
    write_json(
        run_dir / "01-literature-quality.json",
        {
            "total_papers": 2,
            "selected_papers": 2,
            "confidence_status": "review_required",
            "confidence_score": 0.61,
        },
    )
    write_json(
        run_dir / "01-citation-audit.json",
        {
            "integrity_status": "review_required",
            "integrity_score": 0.7,
            "blocked_citations": 0,
            "review_required": 1,
            "usable_citations": 1,
            "total_citations": 2,
            "required_actions": ["private action text should stay local"],
        },
    )


if __name__ == "__main__":
    unittest.main()
