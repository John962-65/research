from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest
import zipfile

from research_agent.artifacts import write_json, write_text
from research_agent.run_integrity_audit import (
    COMPLETED_REQUIRED_ARTIFACTS,
    RUN_INTEGRITY_AUDIT_JSON,
    RUN_INTEGRITY_AUDIT_MD,
    build_run_integrity_audit,
    render_run_integrity_audit_markdown,
    write_run_integrity_audit_artifacts,
)


class RunIntegrityAuditTest(unittest.TestCase):
    def test_completed_run_with_valid_gate_manifest_package_and_ledger_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)

            report = write_run_integrity_audit_artifacts("机械臂路径规划", run_dir)
            rendered = render_run_integrity_audit_markdown(report)

            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["blocking_issues"])
            self.assertFalse(report["warnings"])
            self.assertTrue((run_dir / RUN_INTEGRITY_AUDIT_JSON).exists())
            self.assertTrue((run_dir / RUN_INTEGRITY_AUDIT_MD).exists())
            self.assertIn("Run Integrity Audit", rendered)
            self.assertTrue(any(item["category"] == "human_gate" and item["status"] == "pass" for item in report["items"]))
            self.assertTrue(any(item["name"] == "runtime_contract" and item["status"] == "pass" for item in report["items"]))
            self.assertTrue(any(item["name"] == "run_config_secret" and item["status"] == "pass" for item in report["items"]))
            self.assertTrue(any(item["name"] == "zip_valid" and item["status"] == "pass" for item in report["items"]))

    def test_blocks_unapproved_downstream_invalid_json_and_persisted_secret(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(run_dir / "approval.json", {"approved": False, "revision_requested": False})
            write_json(run_dir / "02-ideas.json", [{"title": "idea before approval"}])
            write_text(run_dir / "broken.json", "{not valid json")
            write_json(run_dir / "run-config.json", {"llm": {"api_key": "secret"}})

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("approval_before_downstream" in item for item in report["blocking_issues"]))
            self.assertTrue(any("top_level_json_validity" in item for item in report["blocking_issues"]))
            self.assertTrue(any("run_config_secret" in item for item in report["blocking_issues"]))

    def test_blocks_persisted_literature_source_credentials(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
            write_json(
                run_dir / "run-config.json",
                {
                    "llm": {"api_key": ""},
                    "literature": {
                        "semantic_scholar_api_key": "s2-secret",
                        "openalex_api_key": "",
                        "contact_email": "lab@example.com",
                    },
                },
            )

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("run_config_secret" in item for item in report["blocking_issues"]))
        self.assertTrue(any("semantic_scholar_api_key" in item.get("evidence", "") for item in report["items"]))

    def test_blocks_non_pass_gate_approval_without_notes(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            write_json(
                run_dir / "approval.json",
                {
                    "approved": True,
                    "revision_requested": False,
                    "gate_status": "literature_repair_required",
                    "warnings": ["核心文献不足"],
                    "notes": "",
                    "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
                },
            )

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("approval_notes" in item for item in report["blocking_issues"]))

    def test_blocks_downstream_artifacts_stale_after_review_revision_repair(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
            manifest["events"] = [
                {"stage": "review_approval", "status": "completed"},
                {"stage": "ideation", "status": "completed"},
                {"stage": "experiment_plan", "status": "completed"},
                {"stage": "review_revision_literature_repair", "status": "completed"},
                {"stage": "review_approval_checkpoint", "status": "completed"},
            ]
            write_json(run_dir / "run-manifest.json", manifest)

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("grounding_before_downstream" in item for item in report["blocking_issues"]))

    def test_blocks_local_results_without_execution_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            write_json(run_dir / "04-experiment-runbook.json", {"execution": {"mode": "local"}})

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("approval_before_execution" in item for item in report["blocking_issues"]))

    def test_warns_when_existing_integrity_audit_is_not_bundled_in_submission_package(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            write_json(run_dir / "14-run-integrity-audit.json", {"status": "pass", "summary": {"checks": 12}})

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "warn")
            self.assertTrue(any("run-integrity-audit.json" in item for item in report["warnings"]))

    def test_blocks_missing_llm_runtime_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            (run_dir / "13-llm-runtime-contract.json").unlink()

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("runtime_contract" in item for item in report["blocking_issues"]))

    def test_blocks_corrupt_submission_package_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            write_text(run_dir / "11-submission-package.zip", "not a zip archive")
            _write_manifest(run_dir)

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

        zip_check = next(item for item in report["items"] if item["name"] == "zip_valid")
        self.assertEqual(report["status"], "block")
        self.assertEqual(zip_check["status"], "block")
        self.assertIn("不是可读 ZIP", zip_check["evidence"])

    def test_blocks_unsafe_submission_package_zip_metadata_path(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_complete_run_fixture(run_dir)
            package = json.loads((run_dir / "11-submission-package.json").read_text(encoding="utf-8"))
            package["package_zip"] = "../11-submission-package.zip"
            write_json(run_dir / "11-submission-package.json", package)
            _write_manifest(run_dir)

            report = build_run_integrity_audit("机械臂路径规划", run_dir)

        zip_check = next(item for item in report["items"] if item["name"] == "zip_valid")
        self.assertEqual(report["status"], "block")
        self.assertEqual(zip_check["status"], "block")
        self.assertIn("路径不安全", zip_check["evidence"])


def _write_complete_run_fixture(run_dir: Path) -> None:
    for name in COMPLETED_REQUIRED_ARTIFACTS:
        path = run_dir / name
        if name.endswith(".json"):
            write_json(path, {"status": "pass"})
        elif name.endswith(".zip"):
            _write_submission_zip(path)
        elif name.endswith(".svg"):
            write_text(path, "<svg></svg>")
        elif name.endswith(".csv"):
            write_text(path, "metric,value\nscore,1\n")
        else:
            write_text(path, f"# {name}")

    write_json(
        run_dir / "approval.json",
        {
            "approved": True,
            "revision_requested": False,
            "gate_status": "pass",
            "warnings": [],
            "blocks": ["idea_generation", "experiment_planning", "experiment_execution"],
        },
    )
    write_json(run_dir / "state.json", {"topic": "机械臂路径规划", "stage": "completed"})
    write_json(run_dir / "run-llm-ledger.json", {"total_calls": 4, "failed_calls": 0})
    write_json(run_dir / "run-config.json", {"llm": {"api_key": ""}})
    package_paths = [
        "submission-package/audits/final-readiness.json",
        "submission-package/audits/citation-grounding.json",
        "submission-package/audits/citation-coverage.json",
        "submission-package/audits/results-presentation.json",
        "submission-package/audits/revision-response-audit.json",
        "submission-package/audits/code-data-availability.json",
        "submission-package/audits/submission-check.json",
        "submission-package/audits/repair-queue.json",
        "submission-package/audits/repair-resolution-audit.json",
        "submission-package/audits/query-execution-audit.json",
        "submission-package/audits/llm-trace-audit.json",
        "submission-package/audits/llm-runtime-contract.json",
        "submission-package/audits/run-economics-audit.json",
        "submission-package/audits/agent-observability-audit.json",
        "submission-package/results/benchmark-result-schema-audit.json",
        "submission-package/provenance/run-manifest.json",
        "submission-package/reproducibility/experiment-runbook.json",
        "submission-package/references/references.bib",
    ]
    write_json(
        run_dir / "11-submission-package.json",
        {
            "status": "ready_for_human_submission_upload",
            "package_zip": "11-submission-package.zip",
            "blocking_issues": [],
            "files": [{"package_path": item, "source_path": item, "status": "pass", "required": True} for item in package_paths],
        },
    )
    _write_manifest(run_dir)


def _write_submission_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
        archive.writestr(
            "submission-package/package-manifest.json",
            json.dumps({"status": "ready_for_human_submission_upload", "files": [{"package_path": "submission-package/CHECKLIST.md"}]}),
        )


def _write_manifest(run_dir: Path) -> None:
    artifact_paths = [*COMPLETED_REQUIRED_ARTIFACTS, "run-config.json"]
    artifacts = []
    for name in artifact_paths:
        path = run_dir / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
        artifacts.append({"path": name, "bytes": path.stat().st_size if path.exists() else 0, "sha256": digest})
    write_json(
        run_dir / "run-manifest.json",
        {
            "topic": "机械臂路径规划",
            "status": "completed",
            "events": [
                {"stage": "literature_context", "status": "completed"},
                {"stage": "review_approval", "status": "completed"},
                {"stage": "review_feedback", "status": "completed"},
                {"stage": "review_constraints", "status": "completed"},
                {"stage": "ideation", "status": "completed"},
                {"stage": "experiment_plan", "status": "completed"},
                {"stage": "experiments", "status": "completed"},
                {"stage": "analysis", "status": "completed"},
                {"stage": "claim_boundary_preflight", "status": "completed"},
                {"stage": "paper_and_review", "status": "completed"},
                {"stage": "paper_rewrite", "status": "completed"},
                {"stage": "revision_response_audit", "status": "completed"},
                {"stage": "final_readiness", "status": "completed"},
                {"stage": "submission_package", "status": "completed"},
                {"stage": "iteration_plan", "status": "completed"},
                {"stage": "repair_queue", "status": "completed"},
                {"stage": "research_scorecard", "status": "completed"},
            ],
            "artifacts": artifacts,
        },
    )


if __name__ == "__main__":
    unittest.main()
