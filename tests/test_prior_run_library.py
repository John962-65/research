from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.prior_run_library import render_prior_run_library_markdown, write_prior_run_library_artifacts


class PriorRunLibraryTest(unittest.TestCase):
    def test_prior_run_library_exports_relevant_ready_references_for_agent_context(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            prior = runs_dir / "robot-run"
            out_dir = runs_dir / "new-run"
            prior.mkdir(parents=True)
            out_dir.mkdir()
            write_json(prior / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(prior / "01-literature-quality.json", {"selected_papers": 6, "total_papers": 8})
            write_json(prior / "01-context.json", {"citations": [{"key": "ompl2012"}, {"key": "rrtstar"}]})
            write_json(prior / "02-ideas.json", [{"title": "OMPL 窄通道规划验证", "hypothesis": "RRT* baseline 对照"}])
            write_json(
                prior / "00-research-plan.json",
                {
                    "domain": "robotics_motion_planning",
                    "benchmarks": ["OMPL benchmark"],
                    "baselines": ["RRT*"],
                    "metrics": ["planning_success_rate"],
                },
            )
            write_text(
                prior / "06-paper.md",
                "\n".join(
                    [
                        "# 可复现机械臂路径规划验证",
                        "",
                        "## Abstract",
                        "We evaluate robot manipulator motion planning with OMPL benchmark tasks and RRT* baselines.",
                    ]
                ),
            )

            report = write_prior_run_library_artifacts("机械臂路径规划", runs_dir, out_dir)
            rendered = render_prior_run_library_markdown(report)
            data = json.loads((out_dir / "00-prior-run-library.json").read_text(encoding="utf-8"))

            self.assertEqual(report.status, "prior_references_ready")
            self.assertEqual(report.references[0].run_id, "robot-run")
            self.assertEqual(report.references[0].reusable_status, "ready_reference")
            self.assertIn("OMPL", report.agent_prompt_text)
            self.assertIn("不是本轮文献证据", report.agent_prompt_text)
            self.assertTrue((out_dir / "00-prior-run-library.md").exists())
            self.assertIn("Prior Run Library", rendered)
            self.assertEqual(data["references"][0]["artifact_path"], "robot-run/06-paper.md")

    def test_prior_run_library_excludes_current_run(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            out_dir = runs_dir / "current-run"
            out_dir.mkdir(parents=True)
            write_json(out_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed", "updated_at": "2026-06-08T10:00:00+00:00"})
            write_json(out_dir / "01-literature-quality.json", {"selected_papers": 5, "total_papers": 6})
            write_text(out_dir / "06-paper.md", "# 当前 run\n\nOMPL benchmark RRT*")

            report = write_prior_run_library_artifacts("机械臂路径规划", runs_dir, out_dir)

            self.assertEqual(report.status, "no_relevant_prior_runs")
            self.assertFalse(report.references)


if __name__ == "__main__":
    unittest.main()
