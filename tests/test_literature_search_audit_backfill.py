from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_search_audit_backfill import (
    LITERATURE_SEARCH_STRATEGY_JSON,
    LITERATURE_SEARCH_STRATEGY_MD,
    LITERATURE_SOURCE_HEALTH_JSON,
    LITERATURE_SOURCE_HEALTH_MD,
    backfill_literature_search_audits,
    render_literature_search_audit_backfill_markdown,
)
from research_agent.query_execution_audit import QUERY_EXECUTION_AUDIT_JSON, QUERY_EXECUTION_AUDIT_MD


class LiteratureSearchAuditBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_search_audits(runs_dir, dry_run=True)
            rendered = render_literature_search_audit_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write_runs"], 1)
            self.assertEqual(report["reconstructed_search_strategy"], 1)
            self.assertEqual(report["reconstructed_source_health"], 1)
            self.assertFalse((run_dir / LITERATURE_SEARCH_STRATEGY_JSON).exists())
            self.assertFalse((run_dir / LITERATURE_SOURCE_HEALTH_JSON).exists())
            self.assertFalse((run_dir / QUERY_EXECUTION_AUDIT_JSON).exists())
            self.assertIn("Literature Search Audit Backfill", rendered)
            self.assertIn("不会批准 gate", rendered)

    def test_write_creates_search_strategy_source_health_and_query_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_search_audits(runs_dir)
            strategy = json.loads((run_dir / LITERATURE_SEARCH_STRATEGY_JSON).read_text(encoding="utf-8"))
            source_health = json.loads((run_dir / LITERATURE_SOURCE_HEALTH_JSON).read_text(encoding="utf-8"))
            query_execution = json.loads((run_dir / QUERY_EXECUTION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written_runs"], 1)
            self.assertEqual(report["written_search_strategy"], 1)
            self.assertEqual(report["written_source_health"], 1)
            self.assertEqual(report["written_query_execution"], 1)
            self.assertTrue((run_dir / LITERATURE_SEARCH_STRATEGY_MD).exists())
            self.assertTrue((run_dir / LITERATURE_SOURCE_HEALTH_MD).exists())
            self.assertTrue((run_dir / QUERY_EXECUTION_AUDIT_MD).exists())
            self.assertEqual(strategy["status"], "legacy_summary")
            self.assertEqual(strategy["selected_queries"], ["robot manipulator motion planning", "OMPL benchmark robot manipulator"])
            self.assertEqual(source_health["total_sources"], 2)
            self.assertEqual(source_health["rate_limited_sources"], 1)
            self.assertEqual(query_execution["status"], "needs_query_repair")
            self.assertEqual(query_execution["selected_query_count"], 2)

    def test_existing_bundle_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_legacy_literature_run(run_dir)
            write_json(run_dir / LITERATURE_SEARCH_STRATEGY_JSON, {"status": "sentinel"})
            (run_dir / LITERATURE_SEARCH_STRATEGY_MD).write_text("# sentinel\n", encoding="utf-8")
            write_json(run_dir / LITERATURE_SOURCE_HEALTH_JSON, {"total_sources": 1})
            (run_dir / LITERATURE_SOURCE_HEALTH_MD).write_text("# sentinel\n", encoding="utf-8")
            write_json(run_dir / QUERY_EXECUTION_AUDIT_JSON, {"status": "sentinel"})
            (run_dir / QUERY_EXECUTION_AUDIT_MD).write_text("# sentinel\n", encoding="utf-8")

            skipped = backfill_literature_search_audits(runs_dir)
            forced = backfill_literature_search_audits(runs_dir, force=True)
            query_execution = json.loads((run_dir / QUERY_EXECUTION_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(skipped["written_runs"], 0)
            self.assertEqual(forced["written_runs"], 1)
            self.assertEqual(forced["items"][0]["action"], "overwrite")
            self.assertNotEqual(query_execution["status"], "sentinel")

    def test_missing_literature_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "missing-lit"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = backfill_literature_search_audits(runs_dir)

            self.assertEqual(report["skipped_no_literature"], 1)
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
                    "title": "Robot manipulator motion planning with OMPL benchmark",
                    "authors": ["Ada"],
                    "year": 2024,
                    "venue": "ICRA",
                    "url": "https://example.test/robot",
                    "abstract": "Robot manipulator motion planning with OMPL benchmark and RRT star baseline evaluation.",
                    "relevance": 0.88,
                    "source": "crossref",
                    "sources": ["crossref"],
                    "doi": "10.1000/robot",
                }
            ],
            "themes": ["motion planning"],
            "gaps": [],
            "summary": "legacy literature review",
            "source_diagnostics": [
                "检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",
                "semantic_scholar: 检索失败：HTTP 429: Too Many Requests",
                "crossref: 2 个检索式返回 20 条，用时 1.4s",
            ],
        },
    )


if __name__ == "__main__":
    unittest.main()
