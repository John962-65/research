from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.workflow_graph import (
    RUN_LEVEL_FILES,
    build_rollback_preview,
    node_artifact_registry,
    owning_nodes_for_artifact,
    update_workflow_stage,
)


class NodeArtifactRegistryTest(unittest.TestCase):
    """ART-01: nodes declare their artifact ownership explicitly."""

    def test_registry_covers_every_node_with_run_level_files(self) -> None:
        registry = node_artifact_registry()
        node_ids = {node["node_id"] for node in registry["nodes"]}
        self.assertIn("research_planning", node_ids)
        self.assertIn("finalization", node_ids)
        self.assertIn("state.json", registry["run_level_files"])
        self.assertIn("run-manifest.json", registry["run_level_files"])

    def test_key_artifacts_have_owners(self) -> None:
        self.assertIn("execution_gate", owning_nodes_for_artifact("03-execution-approval.json"))
        self.assertIn("ideation", owning_nodes_for_artifact("02-ideas.json"))
        self.assertIn("review_gate", owning_nodes_for_artifact("approval.json"))
        self.assertIn("literature_review", owning_nodes_for_artifact("01-literature.json"))

    def test_run_level_files_have_no_owner(self) -> None:
        for name in RUN_LEVEL_FILES:
            self.assertEqual(owning_nodes_for_artifact(name), [], name)

    def test_planning_node_owns_the_full_planning_artifact_set(self) -> None:
        for name in ["00-question.md", "00-human-brief.json", "00-preflight.json", "00-research-plan.json"]:
            self.assertIn("research_planning", owning_nodes_for_artifact(name), name)


class UnownedFileReportTest(unittest.TestCase):
    def test_preview_reports_unowned_files_without_archiving_them(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "02-ideas.json").write_text("[]", encoding="utf-8")
            (run_dir / "00-question.md").write_text("# 问题\n", encoding="utf-8")
            (run_dir / "stray-notes.txt").write_text("operator scratch", encoding="utf-8")
            (run_dir / "state.json").write_text("{}", encoding="utf-8")
            update_workflow_stage(run_dir, "归属测试", "ideation_completed")

            preview = build_rollback_preview(run_dir, "ideation")
            self.assertIn("stray-notes.txt", preview["unowned_files"])
            self.assertNotIn("00-question.md", preview["unowned_files"])
            self.assertNotIn("state.json", preview["unowned_files"])
            # Unowned files are informational only: not in the archive plan.
            self.assertNotIn("stray-notes.txt", preview["artifacts_to_archive"])


if __name__ == "__main__":
    unittest.main()
