from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.literature_audit_backfill import (
    backfill_literature_audits,
    render_literature_audit_backfill_markdown,
)
from research_agent.literature_coverage import LITERATURE_COVERAGE_JSON, LITERATURE_COVERAGE_MD
from research_agent.literature_evidence_mix import LITERATURE_EVIDENCE_MIX_JSON, LITERATURE_EVIDENCE_MIX_MD
from research_agent.literature_metadata_audit import LITERATURE_METADATA_AUDIT_JSON, LITERATURE_METADATA_AUDIT_MD


class LiteratureAuditBackfillTest(unittest.TestCase):
    def test_dry_run_reports_without_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "run-a"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_audits(runs_dir, dry_run=True)
            rendered = render_literature_audit_backfill_markdown(report)

            self.assertEqual(report["scanned_runs"], 1)
            self.assertEqual(report["would_write_runs"], 1)
            self.assertEqual(report["fallback_research_plan"], 1)
            self.assertEqual(report["fallback_quality"], 1)
            self.assertEqual(report["generated_curated"], 1)
            self.assertEqual(report["reconstructed_source_health"], 1)
            self.assertFalse((run_dir / LITERATURE_METADATA_AUDIT_JSON).exists())
            self.assertFalse((run_dir / LITERATURE_COVERAGE_JSON).exists())
            self.assertFalse((run_dir / LITERATURE_EVIDENCE_MIX_JSON).exists())
            self.assertIn("Literature Audit Backfill", rendered)
            self.assertIn("不会伪造 seed 配置", rendered)

    def test_write_creates_audit_bundle_from_legacy_literature(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            _write_legacy_literature_run(run_dir)

            report = backfill_literature_audits(runs_dir)
            metadata = json.loads((run_dir / LITERATURE_METADATA_AUDIT_JSON).read_text(encoding="utf-8"))
            coverage = json.loads((run_dir / LITERATURE_COVERAGE_JSON).read_text(encoding="utf-8"))
            evidence_mix = json.loads((run_dir / LITERATURE_EVIDENCE_MIX_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["written_runs"], 1)
            self.assertEqual(report["written_metadata"], 1)
            self.assertEqual(report["written_coverage"], 1)
            self.assertEqual(report["written_evidence_mix"], 1)
            self.assertTrue((run_dir / LITERATURE_METADATA_AUDIT_MD).exists())
            self.assertTrue((run_dir / LITERATURE_COVERAGE_MD).exists())
            self.assertTrue((run_dir / LITERATURE_EVIDENCE_MIX_MD).exists())
            self.assertEqual(metadata["status"], "literature_repair_required")
            self.assertEqual(metadata["raw_papers"], 6)
            self.assertEqual(metadata["curated_papers"], 5)
            self.assertEqual(metadata["review_required"], 5)
            self.assertEqual(coverage["status"], "pass")
            self.assertEqual(coverage["curated_papers"], 5)
            self.assertEqual(evidence_mix["status"], "pass")
            self.assertEqual(evidence_mix["summary"]["curated_papers"], 5)

    def test_existing_bundle_is_skipped_unless_force_is_set(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "existing-run"
            _write_legacy_literature_run(run_dir)
            write_json(run_dir / LITERATURE_METADATA_AUDIT_JSON, {"status": "sentinel"})
            (run_dir / LITERATURE_METADATA_AUDIT_MD).write_text("# sentinel\n", encoding="utf-8")
            write_json(run_dir / LITERATURE_COVERAGE_JSON, {"status": "sentinel"})
            (run_dir / LITERATURE_COVERAGE_MD).write_text("# sentinel\n", encoding="utf-8")
            write_json(run_dir / LITERATURE_EVIDENCE_MIX_JSON, {"status": "sentinel"})
            (run_dir / LITERATURE_EVIDENCE_MIX_MD).write_text("# sentinel\n", encoding="utf-8")

            skipped = backfill_literature_audits(runs_dir)
            forced = backfill_literature_audits(runs_dir, force=True)
            metadata = json.loads((run_dir / LITERATURE_METADATA_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(skipped["skipped_existing"], 1)
            self.assertEqual(forced["written_runs"], 1)
            self.assertEqual(forced["items"][0]["action"], "overwrite")
            self.assertNotEqual(metadata["status"], "sentinel")

    def test_missing_literature_is_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "missing-lit"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})

            report = backfill_literature_audits(runs_dir)

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
                    "title": "Robot Manipulator Motion Planning Survey",
                    "authors": ["Ada Lovelace"],
                    "year": 2024,
                    "venue": "Robotics Review",
                    "url": "https://example.test/survey",
                    "abstract": "A review of robot manipulator motion planning with survey coverage of RRT star, PRM, CHOMP, STOMP, TrajOpt, OMPL benchmark, evaluation protocol, path length, collision rate, and reproducible baseline comparisons.",
                    "relevance": 0.92,
                    "source": "openalex",
                    "sources": ["openalex", "semantic_scholar"],
                    "doi": "10.1234/robot.survey",
                    "citation_count": 300,
                },
                {
                    "title": "The Open Motion Planning Library",
                    "authors": ["Bob Example"],
                    "year": 2023,
                    "venue": "Robotics Systems",
                    "url": "https://example.test/ompl",
                    "abstract": "OMPL benchmark and MoveIt benchmarking for robot arm manipulation tasks, dataset style evaluation suites, planning time, and success rate comparisons.",
                    "relevance": 0.9,
                    "source": "openalex",
                    "sources": ["openalex", "crossref"],
                    "doi": "10.1234/robot.ompl",
                    "citation_count": 500,
                },
                {
                    "title": "Sampling-based Optimal Motion Planning for Robot Manipulators",
                    "authors": ["Carol Example"],
                    "year": 2022,
                    "venue": "Motion Planning Journal",
                    "url": "https://example.test/rrt",
                    "abstract": "RRT star and PRM baseline methods for collision-free robot manipulator path planning with benchmark comparison and evaluation metrics.",
                    "relevance": 0.88,
                    "source": "semantic_scholar",
                    "sources": ["semantic_scholar", "openalex"],
                    "doi": "10.1234/robot.rrt",
                    "citation_count": 220,
                },
                {
                    "title": "Trajectory Optimization for Robot Arms with CHOMP STOMP and TrajOpt",
                    "authors": ["Dana Example"],
                    "year": 2021,
                    "venue": "Trajectory Optimization Letters",
                    "url": "https://example.test/trajopt",
                    "abstract": "Trajectory optimization baselines include CHOMP, STOMP, and TrajOpt for robot arm planning with obstacle avoidance and benchmark evaluation.",
                    "relevance": 0.87,
                    "source": "arxiv",
                    "sources": ["arxiv", "openalex"],
                    "doi": "10.1234/robot.trajopt",
                    "citation_count": 140,
                },
                {
                    "title": "Recent Benchmarking of Robot Arm Planning in Cluttered Scenes",
                    "authors": ["Eve Example"],
                    "year": 2025,
                    "venue": "Robotics Benchmarking",
                    "url": "https://example.test/recent",
                    "abstract": "Recent benchmark evaluation dataset for robot arm planning in cluttered scenes with planning time, path length, collision rate, and robust manipulation tasks.",
                    "relevance": 0.86,
                    "source": "crossref",
                    "sources": ["crossref", "openalex"],
                    "doi": "10.1234/robot.recent",
                    "citation_count": 50,
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


if __name__ == "__main__":
    unittest.main()
