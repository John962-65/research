from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.run_library import build_run_library, render_run_library_markdown, search_run_library, write_run_library


class RunLibraryTest(unittest.TestCase):
    def test_library_indexes_completed_papers_and_searches_prior_results(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            robot = runs_dir / "robot-run"
            bearing = runs_dir / "bearing-run"
            robot.mkdir(parents=True)
            bearing.mkdir(parents=True)
            write_json(robot / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(robot / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(robot / "01-context.json", {"citations": [{"key": "ompl2012"}, {"key": "rrtstar"}]})
            write_json(robot / "02-ideas.json", [{"title": "OMPL 窄通道规划验证", "hypothesis": "RRT* baseline 对照"}])
            write_json(
                robot / "00-research-plan.json",
                {
                    "domain": "robotics_motion_planning",
                    "benchmarks": ["OMPL benchmark"],
                    "baselines": ["RRT*", "CHOMP"],
                    "metrics": ["planning_success_rate"],
                },
            )
            write_text(
                robot / "06-paper.md",
                "\n".join(
                    [
                        "# 可复现机械臂路径规划验证",
                        "",
                        "## Abstract",
                        "We evaluate robot manipulator motion planning with OMPL benchmark tasks and RRT* baselines.",
                    ]
                ),
            )
            write_text(robot / "05-analysis.md", "# Analysis")
            write_text(robot / "12-next-iteration-plan.md", "# 下一轮")

            write_json(bearing / "state.json", {"topic": "轴承故障诊断", "stage": "completed", "updated_at": "2026-06-08T09:00:00+00:00"})
            write_json(bearing / "01-literature-quality.json", {"selected_papers": 5, "total_papers": 7})
            write_text(bearing / "06-paper.md", "# 轴承故障诊断实验\n\nCWRU benchmark fault diagnosis.")

            library = build_run_library(runs_dir)
            results = search_run_library(library, "OMPL RRT robot", limit=5)
            rendered = render_run_library_markdown(library, query="OMPL RRT robot", results=results)

            self.assertEqual(library.indexed_runs, 2)
            self.assertEqual(results[0].entry.id, "robot-run")
            self.assertGreater(results[0].score, 0)
            self.assertTrue({"abstract", "keywords"} & set(results[0].matched_fields))
            self.assertEqual(results[0].entry.reusable_status, "ready_reference")
            self.assertIn("OMPL benchmark", results[0].entry.keywords)
            self.assertIn("Runs 本地成果库", rendered)
            self.assertIn("robot-run", rendered)

    def test_write_library_outputs_json_and_markdown(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "one-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "科研 agent", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 4, "total_papers": 5})
            write_text(run_dir / "06-paper.md", "# 科研 agent 论文\n\n可审计 workflow。")
            library = build_run_library(runs_dir)

            json_path, md_path = write_run_library(library, root)

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["indexed_runs"], 1)
            self.assertIn("Runs 本地成果库", md_path.read_text(encoding="utf-8"))

    def test_library_marks_invalid_final_handoff_zip_as_needs_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "invalid-zip-reference"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "坏 ZIP 参考", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(run_dir / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_text(run_dir / "06-paper.md", "# 坏 ZIP 论文\n\nThis completed paper should not be reusable while the final package is invalid.")
            write_json(
                run_dir / "14-final-handoff.json",
                {
                    "status": "ready_for_submission_upload",
                    "package_zip_exists": True,
                    "package_zip_valid": False,
                    "blocking_issues": [],
                    "manual_tasks": [],
                },
            )

            library = build_run_library(runs_dir)
            rendered = render_run_library_markdown(library)

            self.assertEqual(library.entries[0].reusable_status, "needs_repair")
            self.assertIn("needs_repair", rendered)


if __name__ == "__main__":
    unittest.main()
