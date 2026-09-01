from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_context_backfill import (
    CITATION_AUDIT_JSON,
    LITERATURE_CONTEXT_JSON,
    LITERATURE_CONTEXT_MD,
    REVIEW_GATE_MD,
    REFERENCES_BIB,
    REFERENCES_RIS,
    backfill_literature_context_artifacts,
    render_literature_context_backfill_markdown,
)
from research_agent.literature_evidence_contract import LITERATURE_EVIDENCE_CONTRACT_JSON
from research_agent.literature_gate_decision import LITERATURE_GATE_DECISION_JSON


class LiteratureContextBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_context_artifacts(runs_dir, dry_run=True)
            rendered = render_literature_context_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write_runs"], 1)
            self.assertEqual(report["built_from_curated"], 1)
            self.assertEqual(report["reconstructed_source_health"], 1)
            self.assertFalse((run_dir / LITERATURE_CONTEXT_JSON).exists())
            self.assertFalse((run_dir / CITATION_AUDIT_JSON).exists())
            self.assertIn("Literature Context Backfill", rendered)
            self.assertIn("不会批准 gate", rendered)

    def test_write_creates_context_bundle_from_curated_review(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_context_artifacts(runs_dir)
            context = json.loads((run_dir / LITERATURE_CONTEXT_JSON).read_text(encoding="utf-8"))
            citation_audit = json.loads((run_dir / CITATION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written_runs"], 1)
            self.assertTrue((run_dir / LITERATURE_CONTEXT_MD).exists())
            self.assertTrue((run_dir / REVIEW_GATE_MD).exists())
            self.assertTrue((run_dir / REFERENCES_BIB).exists())
            self.assertTrue((run_dir / REFERENCES_RIS).exists())
            self.assertTrue((run_dir / LITERATURE_EVIDENCE_CONTRACT_JSON).exists())
            self.assertTrue((run_dir / LITERATURE_GATE_DECISION_JSON).exists())
            self.assertEqual(len(context["citations"]), 1)
            self.assertEqual(len(context["chunks"]), 1)
            self.assertEqual(citation_audit["blocked_citations"], 0)
            self.assertEqual(citation_audit["review_required"], 1)

    def test_existing_context_can_refresh_without_literature_inputs(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "context-only"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / LITERATURE_CONTEXT_JSON, _context_payload())

            report = backfill_literature_context_artifacts(runs_dir)
            citation_audit = json.loads((run_dir / CITATION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written_runs"], 1)
            self.assertEqual(report["reused_existing_context"], 1)
            self.assertEqual(report["items"][0]["context_source"], "existing_context")
            self.assertEqual(citation_audit["integrity_status"], "pass")

    def test_existing_bundle_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_legacy_literature_run(run_dir)
            backfill_literature_context_artifacts(runs_dir)

            skipped = backfill_literature_context_artifacts(runs_dir)
            forced = backfill_literature_context_artifacts(runs_dir, force=True)

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written_runs"], 1)
            self.assertEqual(forced["items"][0]["action"], "overwrite_existing_context")

    def test_missing_context_source_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "missing-source"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = backfill_literature_context_artifacts(runs_dir)

            self.assertEqual(report["skipped_no_context_source"], 1)
            self.assertEqual(report["written_runs"], 0)


def _write_legacy_literature_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(
        run_dir / "01-literature.json",
        {
            "topic": "机械臂路径规划",
            "papers": [
                {
                    "title": "A generic education survey",
                    "authors": [],
                    "year": 2025,
                    "venue": "Crossref",
                    "url": "",
                    "abstract": "Short note.",
                    "relevance": 0.95,
                    "source": "crossref",
                    "sources": ["crossref"],
                },
                {
                    "title": "Robot manipulator motion planning with RRT star and OMPL benchmarks",
                    "authors": ["Ada Lovelace"],
                    "year": 2024,
                    "venue": "Robotics Journal",
                    "url": "https://example.test/robot",
                    "abstract": "Robot manipulator motion planning with obstacle avoidance, RRT star, CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, collision rate, and reproducible baseline evaluation.",
                    "relevance": 0.35,
                    "source": "openalex",
                    "sources": ["openalex", "semantic_scholar"],
                    "doi": "10.1234/robot.motion",
                    "citation_count": 120,
                },
            ],
            "themes": [],
            "gaps": [],
            "summary": "legacy literature review",
            "source_diagnostics": [
                "检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",
                "semantic_scholar: 检索失败：HTTP 429: Too Many Requests",
                "crossref: 2 个检索式返回 20 条，用时 1.4s",
            ],
        },
    )


def _context_payload() -> dict[str, object]:
    return {
        "topic": "机械臂路径规划",
        "citations": [
            {
                "key": "lovelace2024robot1",
                "title": "Robot manipulator motion planning benchmark",
                "authors": ["Ada Lovelace"],
                "year": 2024,
                "venue": "Robotics",
                "url": "https://example.test",
                "doi": "10.1234/example",
                "source": "openalex",
            }
        ],
        "chunks": [
            {
                "chunk_id": "chunk-001",
                "citation_key": "lovelace2024robot1",
                "title": "Robot manipulator motion planning benchmark",
                "text": "Robot manipulator motion planning benchmark evaluates collision-free path quality and planning success.",
                "source": "openalex",
                "url": "https://example.test",
                "relevance": 0.9,
            }
        ],
        "claim_support": [
            {
                "claim": "Robot manipulator motion planning needs benchmark evaluation.",
                "claim_type": "benchmark",
                "support_level": "supported",
                "citation_keys": ["lovelace2024robot1"],
                "evidence_notes": ["benchmark evidence"],
            }
        ],
        "review_gate": {"status": "pass", "warnings": [], "required_actions": []},
    }


if __name__ == "__main__":
    unittest.main()
