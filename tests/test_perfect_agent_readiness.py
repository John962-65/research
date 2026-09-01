from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import hashlib
import json
import os
import unittest
import zipfile

from research_agent.artifacts import write_json
from research_agent.perfect_agent_readiness import (
    _agent_deliberation_check,
    _external_integration_check,
    _gold_candidate_evidence,
    _human_ui_check,
    _reproducible_environment_check,
    _statistics_design_check,
    build_perfect_agent_readiness,
    render_perfect_agent_readiness_markdown,
    write_perfect_agent_readiness_artifacts,
)


class PerfectAgentReadinessTest(unittest.TestCase):
    def test_deterministic_role_projection_is_not_independent_agent_readiness(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            write_json(
                run_dir / "10-agent-deliberation.json",
                {
                    "status": "pass",
                    "assessment_kind": "deterministic_role_projection",
                    "independent_agent_execution": False,
                    "independent_verdict_count": 0,
                    "consensus": {"decision": "approve"},
                    "agent_verdicts": [{"verdict": "approve"}] * 6,
                },
            )

            capability = _agent_deliberation_check(
                [SimpleNamespace(id="run")],
                {"run": run_dir},
            )

        self.assertEqual(capability.status, "review_required")
        self.assertIn("independent=False", " ".join(capability.evidence))

    def test_blocks_empty_project_without_gold_assets(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = build_perfect_agent_readiness(root, root / "runs")
            rendered = render_perfect_agent_readiness_markdown(report)

        self.assertEqual(report.status, "block")
        self.assertEqual(len(report.capabilities), 15)
        self.assertTrue(any(item.capability_id == "real_benchmark_packs" and item.status == "block" for item in report.capabilities))
        self.assertIn("Perfect Research Agent Readiness", rendered)
        self.assertIn("real_benchmark_packs", rendered)

    def test_reports_ready_when_all_contract_evidence_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run")

            report = build_perfect_agent_readiness(root, runs_dir)
            out_dir = root / "out"
            written = write_perfect_agent_readiness_artifacts(root, runs_dir, out_dir)

            statuses = {item.capability_id: item.status for item in report.capabilities}
            self.assertEqual(report.status, "ready")
            self.assertEqual(report.ready_capabilities, 15)
            self.assertEqual(statuses["gold_end_to_end_run"], "ready")
            self.assertEqual(statuses["agent_claim_ownership"], "ready")
            self.assertEqual(statuses["agent_deliberation_consensus"], "ready")
            self.assertEqual(statuses["task_specific_agent_routing"], "ready")
            gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
            self.assertTrue(any("verification=ready" in item for item in gold.evidence))
            self.assertEqual(statuses["candidate_baseline_ablation_implementations"], "ready")
            statistical = next(item for item in report.capabilities if item.capability_id == "statistical_design")
            self.assertTrue(any("multiplicity=pass" in item and "power=profile_ready" in item for item in statistical.evidence))
            self.assertEqual(written.status, "ready")
            self.assertTrue((out_dir / "perfect-agent-readiness.json").exists())
            self.assertTrue((out_dir / "perfect-agent-readiness.md").exists())

    def test_default_scan_does_not_hide_gold_run_below_top_100_readiness_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run")
            for index in range(101):
                _write_high_readiness_non_gold_run(runs_dir / f"decoy-{index:03d}")

            report = build_perfect_agent_readiness(root, runs_dir)
            rendered = render_perfect_agent_readiness_markdown(report)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        self.assertEqual(report.dashboard_limit, 0)
        self.assertEqual(report.scanned_runs, 102)
        self.assertEqual(statuses["gold_end_to_end_run"], "ready")
        self.assertIn("Run 扫描：102（limit=all）", rendered)

    def test_gold_run_requires_claim_consistency_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", claim_consistency=False)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertIn("claim consistency pass", " ".join(gold.gaps))
        self.assertTrue(any("closest_run=gold-run" in item for item in gold.evidence))
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("claim=block" in item for item in gold.evidence))

    def test_gold_run_requires_claim_traceability_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", claim_traceability=False)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertIn("claim traceability pass", " ".join(gold.gaps))
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("trace=block" in item for item in gold.evidence))

    def test_gold_run_accepts_submission_upload_handoff(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", final_handoff_status="ready_for_submission_upload")

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        self.assertEqual(report.status, "ready")
        self.assertEqual(statuses["gold_end_to_end_run"], "ready")

    def test_gold_run_requires_handoff_source_artifacts_not_blocked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", package_status="blocked")

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("sources=package=blocked:1" in item for item in gold.evidence))
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))

    def test_gold_run_requires_valid_final_handoff_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", package_zip_valid=False)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("sources=package=ready_for_human_submission_upload:0" in item and "zip=invalid" in item for item in gold.evidence))
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))

    def test_gold_run_requires_explicit_final_handoff_zip_valid_marker(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", package_zip_valid=None)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("sources=package=ready_for_human_submission_upload:0" in item and "zip=unknown" in item for item in gold.evidence))
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))

    def test_gold_run_revalidates_current_submission_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            (run_dir / "11-submission-package.zip").write_text("not a zip archive", encoding="utf-8")

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "zip_current=invalid" in item for item in gold.evidence))

    def test_gold_run_rejects_upload_ready_handoff_when_package_still_needs_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(
                runs_dir / "gold-run",
                final_handoff_status="ready_for_submission_upload",
                package_status="needs_human_submission_review",
            )

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("sources=package=needs_human_submission_review:0" in item for item in gold.evidence))

    def test_gold_run_allows_human_handoff_when_package_review_remains(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(
                runs_dir / "gold-run",
                final_handoff_status="ready_for_human_handoff",
                package_status="needs_human_submission_review",
            )

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        self.assertEqual(report.status, "ready")
        self.assertEqual(statuses["gold_end_to_end_run"], "ready")

    def test_gold_run_requires_run_economics_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", economics_status="block")

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=7/9" in item for item in gold.evidence))
        self.assertTrue(any("economics=block:1" in item for item in gold.evidence))
        self.assertTrue(any("current_audit_contracts=6/7; blocking=1; manual=0; missing=0" in item for item in gold.evidence))

    def test_gold_run_requires_final_verification_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(runs_dir / "gold-run", gold_verification=False)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=missing" in item for item in gold.evidence))
        self.assertIn("15-gold-run-verification ready", " ".join(gold.gaps))

    def test_gold_run_requires_structured_final_verification_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            write_json(
                run_dir / "15-gold-run-verification.json",
                {
                    "status": "ready",
                    "gold_contract_ready": True,
                    "secret_scan": {"status": "pass", "finding_count": 0},
                },
            )

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "required=0/23" in item for item in gold.evidence))
        self.assertTrue(any("check=-" in item and "repairs=unknown" in item for item in gold.evidence))

    def test_gold_run_requires_current_final_verification_schema_version(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["schema_version"] = 1
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "schema=1:read_only" in item for item in gold.evidence))

    def test_gold_run_requires_final_verification_top_level_summary_consistency(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["check"]["status"] = "fail"
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "contract=ready" in item
                and "verification_summary=mismatch=1" in item
                and "check=fail" in item
                and "repairs=0" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rejects_malformed_final_verification_top_level_summary_items(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["missing_artifacts"] = [""]
            verification["repair_plan"] = [{"id": "", "target_artifacts": [""], "action": ""}]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "verification_summary=mismatch=3" in item
                and "missing=1" in item
                and "missing_malformed=1" in item
                and "repairs=1" in item
                and "repair_malformed=3" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_exact_final_verification_required_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["required_artifacts"] = [*verification["required_artifacts"], "private-extra-artifact.json"]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "required=23/23; missing=0; extra=1; duplicate=0" in item for item in gold.evidence))

    def test_gold_run_rejects_duplicate_final_verification_required_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["required_artifacts"] = [*verification["required_artifacts"], "10-claim-consistency.json"]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "required=23/23; missing=0; extra=0; duplicate=1" in item for item in gold.evidence))

    def test_gold_run_rejects_malformed_final_verification_required_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["required_artifacts"] = [*verification["required_artifacts"], ""]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "required=23/23; missing=0; extra=0; duplicate=0; malformed=1" in item for item in gold.evidence))

    def test_gold_run_rejects_whitespace_final_verification_required_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["required_artifacts"] = [
                " state.json " if item == "state.json" else item for item in verification["required_artifacts"]
            ]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "required=22/23; missing=1; extra=0; duplicate=0; malformed=1" in item for item in gold.evidence))

    def test_gold_run_requires_final_verification_subschemas(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["manifest_inventory"].pop("schema_version", None)
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "subschemas=artifact_safety=1,manifest_inventory=missing,secret_scan=1" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_contract_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification.pop("contract_evidence", None)
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "final_zip=unknown" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "contract_evidence=missing" in item for item in gold.evidence))

    def test_gold_run_rejects_nested_only_final_verification_contract_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            nested_evidence = verification.pop("contract_evidence")
            verification["check"]["contract_evidence"] = nested_evidence
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "contract_evidence=missing" in item and "final_zip=unknown" in item for item in gold.evidence))

    def test_gold_run_requires_final_zip_evidence_summary_consistency(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["contract_evidence"]["final_zip_state"] = "valid"
            verification["contract_evidence"]["final_handoff_package_zip_valid"] = False
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "contract_evidence=top_level" in item
                and "final_zip=valid" in item
                and "final_zip_summary=mismatch=1" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_audit_contracts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            evidence = verification["contract_evidence"]
            evidence["audit_contracts_ready"] = False
            evidence["audit_contract_ready_count"] = 6
            evidence["audit_contract_manual_tasks"] = 1
            evidence["audit_contracts"]["llm_trace"] = {"status": "pass", "blocking_issues": 0, "manual_tasks": 1, "ready": False}
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "audit_contracts=6/7; blocking=0; manual=1; missing=0" in item for item in gold.evidence))

    def test_gold_run_rejects_boolean_final_verification_audit_contract_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            evidence = verification["contract_evidence"]
            evidence["audit_contracts"]["llm_trace"]["blocking_issues"] = False
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "audit_contracts=6/7; blocking=1; manual=0; missing=0" in item
                and "audit_summary=mismatch=3" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rejects_extra_final_verification_audit_contracts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["contract_evidence"]["audit_contracts"]["private_extra"] = {
                "status": "pass",
                "blocking_issues": 0,
                "manual_tasks": 0,
                "ready": True,
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "audit_contracts=7/7; blocking=0; manual=0; missing=0; extra=1" in item
                and "audit_summary=mismatch=2" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rejects_malformed_final_verification_audit_contract_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["contract_evidence"]["audit_contracts"][""] = {
                "status": "pass",
                "blocking_issues": 0,
                "manual_tasks": 0,
                "ready": True,
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "audit_contracts=7/7; blocking=0; manual=0; missing=0; extra=0; malformed=1" in item
                and "audit_summary=mismatch=2" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_audit_summary_consistency(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            evidence = verification["contract_evidence"]
            evidence["audit_contract_ready_count"] = 6
            evidence["audit_contract_blocking_issues"] = 1
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "audit_contracts=7/7; blocking=0; manual=0; missing=0" in item
                and "audit_summary=mismatch=2" in item
                and "current_audit_contracts=7/7; blocking=0; manual=0; missing=0" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rechecks_current_audit_contracts_after_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            audit_name = "13-llm-trace-audit.json"
            audit_path = run_dir / audit_name
            write_json(audit_path, {"status": "warn", "blocking_issues": [], "manual_tasks": ["review trace"]})
            audit_bytes = audit_path.read_bytes()
            manifest_path = run_dir / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
            for item in artifacts:
                if isinstance(item, dict) and item.get("path") == audit_name:
                    item["bytes"] = len(audit_bytes)
                    item["sha256"] = hashlib.sha256(audit_bytes).hexdigest()
                    break
            write_json(manifest_path, manifest)
            manifest_bytes = manifest_path.read_bytes()
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"][audit_name] = {"sha256": hashlib.sha256(audit_bytes).hexdigest(), "size_bytes": len(audit_bytes)}
            verification["artifact_hashes"]["run-manifest.json"] = {
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "size_bytes": len(manifest_bytes),
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "audit_contracts=7/7; blocking=0; manual=0; missing=0" in item
                and "current_audit_contracts=6/7; blocking=0; manual=1; missing=0" in item
                and "artifact_hashes=match" in item
                and "current_manifest_inventory=pass:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=0" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rechecks_current_audit_contracts_reject_boolean_counts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            audit_name = "13-llm-trace-audit.json"
            audit_path = run_dir / audit_name
            write_json(audit_path, {"status": "pass", "blocking_issues": False, "manual_tasks": []})
            audit_bytes = audit_path.read_bytes()
            manifest_path = run_dir / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
            for item in artifacts:
                if isinstance(item, dict) and item.get("path") == audit_name:
                    item["bytes"] = len(audit_bytes)
                    item["sha256"] = hashlib.sha256(audit_bytes).hexdigest()
                    break
            write_json(manifest_path, manifest)
            manifest_bytes = manifest_path.read_bytes()
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"][audit_name] = {"sha256": hashlib.sha256(audit_bytes).hexdigest(), "size_bytes": len(audit_bytes)}
            verification["artifact_hashes"]["run-manifest.json"] = {
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "size_bytes": len(manifest_bytes),
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "audit_contracts=7/7; blocking=0; manual=0; missing=0" in item
                and "current_audit_contracts=6/7; blocking=1; manual=0; missing=0" in item
                and "artifact_hashes=match" in item
                and "current_manifest_inventory=pass:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=0" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_artifact_hashes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification.pop("artifact_hashes", None)
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=missing" in item for item in gold.evidence))

    def test_gold_run_requires_positive_final_verification_artifact_hash_sizes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"]["10-claim-consistency.json"]["size_bytes"] = 0
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=missing" in item for item in gold.evidence))

    def test_gold_run_rejects_boolean_final_verification_artifact_hash_sizes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"]["10-claim-consistency.json"]["size_bytes"] = True
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=missing" in item for item in gold.evidence))

    def test_gold_run_rejects_extra_final_verification_artifact_hashes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"]["private-extra-artifact.json"] = {"sha256": "0" * 64, "size_bytes": 1}
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=extra=1" in item for item in gold.evidence))

    def test_gold_run_rejects_malformed_final_verification_artifact_hash_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"][""] = {"sha256": "0" * 64, "size_bytes": 1}
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=malformed=1" in item for item in gold.evidence))

    def test_gold_run_rejects_whitespace_final_verification_artifact_hash_names(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"][" state.json "] = {"sha256": "0" * 64, "size_bytes": 1}
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=malformed=1" in item for item in gold.evidence))

    def test_gold_run_requires_final_verification_manifest_inventory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification.pop("manifest_inventory", None)
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "manifest_inventory=missing" in item for item in gold.evidence))

    def test_gold_run_requires_unique_final_verification_manifest_inventory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["manifest_inventory"]["status"] = "blocked"
            verification["manifest_inventory"]["duplicate_required_artifacts"] = ["10-claim-consistency.json"]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "manifest_inventory=blocked:missing=0,mismatch=0,size_mismatch=0,duplicate=1,unsafe=0" in item for item in gold.evidence))

    def test_gold_run_requires_manifest_inventory_size_match(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["manifest_inventory"]["status"] = "blocked"
            verification["manifest_inventory"]["size_mismatches"] = ["10-claim-consistency.json"]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "manifest_inventory=blocked:missing=0,mismatch=0,size_mismatch=1,duplicate=0,unsafe=0" in item for item in gold.evidence))

    def test_gold_run_requires_safe_final_verification_manifest_inventory_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["manifest_inventory"]["status"] = "blocked"
            verification["manifest_inventory"]["unsafe_artifact_paths"] = [{"path": "outside/private-result.json", "issue": "parent_reference"}]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "manifest_inventory=blocked:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=1" in item for item in gold.evidence))

    def test_gold_run_rejects_malformed_final_verification_manifest_inventory_items(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["manifest_inventory"]["status"] = "blocked"
            verification["manifest_inventory"]["missing_required_artifacts"] = [""]
            verification["manifest_inventory"]["unsafe_artifact_paths"] = [{"path": "", "issue": "parent_reference"}]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "manifest_inventory=blocked:missing=1,mismatch=0,size_mismatch=0,duplicate=0,unsafe=1,malformed=2" in item
                and "manifest_inventory_summary=mismatch=1" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_manifest_inventory_summary_consistency(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["manifest_inventory"]["checked_artifacts"] = 0
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "manifest_inventory=pass:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=0" in item
                and "manifest_inventory_summary=mismatch=1" in item
                and "current_manifest_inventory=pass:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=0" in item
                and "artifact_hashes=match" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rechecks_current_manifest_inventory_after_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            manifest_path = run_dir / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
            duplicate = next(item for item in artifacts if isinstance(item, dict) and item.get("path") == "10-claim-consistency.json")
            artifacts.append(dict(duplicate))
            write_json(manifest_path, manifest)
            manifest_bytes = manifest_path.read_bytes()
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"]["run-manifest.json"] = {
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "size_bytes": len(manifest_bytes),
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "artifact_hashes=match" in item
                and "manifest_inventory=pass:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=0" in item
                and "current_manifest_inventory=blocked:missing=0,mismatch=0,size_mismatch=0,duplicate=1,unsafe=0" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rechecks_current_manifest_inventory_requires_integer_bytes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            manifest_path = run_dir / "run-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
            for item in artifacts:
                if isinstance(item, dict) and item.get("path") == "10-claim-consistency.json":
                    item["bytes"] = str(item.get("bytes"))
            write_json(manifest_path, manifest)
            manifest_bytes = manifest_path.read_bytes()
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_hashes"]["run-manifest.json"] = {
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "size_bytes": len(manifest_bytes),
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "artifact_hashes=match" in item
                and "manifest_inventory=pass:missing=0,mismatch=0,size_mismatch=0,duplicate=0,unsafe=0" in item
                and "current_manifest_inventory=blocked:missing=0,mismatch=0,size_mismatch=1,duplicate=0,unsafe=0" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rehashes_current_required_artifacts_after_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            artifact_path = run_dir / "10-claim-consistency.json"
            verification_mtime = verification_path.stat().st_mtime_ns
            write_json(artifact_path, {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": [], "late_change": True})
            os.utime(artifact_path, ns=(verification_mtime - 1_000_000_000, verification_mtime - 1_000_000_000))

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_hashes=mismatch" in item and "freshness=fresh" in item for item in gold.evidence))

    def test_gold_run_requires_zero_secret_scan_findings_in_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["secret_scan"] = {
                "status": "pass",
                "finding_count": 1,
                "findings": [{"path": "leaky-log.txt", "rule": "openai_style_token", "count": 1}],
            }
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "secret_findings=1" in item for item in gold.evidence))

    def test_gold_run_requires_final_verification_secret_scan_summary_consistency(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["secret_scan"]["safe_to_render"] = False
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "secret_scan=pass" in item
                and "secret_findings=0" in item
                and "secret_scan_summary=mismatch=1" in item
                and "current_secret_scan=pass:0" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_secret_scan_rules_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["secret_scan"]["rules"] = ["openai_style_token"]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "secret_scan=pass" in item
                and "secret_findings=0" in item
                and "secret_scan_summary=mismatch=1" in item
                and "current_secret_scan=pass:0" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rejects_malformed_final_verification_secret_scan_rules(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["secret_scan"]["rules"] = [*verification["secret_scan"]["rules"], ""]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "secret_scan=pass" in item
                and "secret_findings=0" in item
                and "secret_scan_summary=mismatch=1" in item
                and "current_secret_scan=pass:0" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rejects_malformed_final_verification_secret_scan_findings(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["secret_scan"]["status"] = "blocked"
            verification["secret_scan"]["finding_count"] = 1
            verification["secret_scan"]["findings"] = [{"path": "", "rule": "openai_style_token", "count": 1}]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "secret_scan=blocked" in item
                and "secret_findings=1" in item
                and "secret_malformed_findings=1" in item
                and "secret_scan_summary=mismatch=1" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_run_dir_match(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["run_dir"] = str(runs_dir / "other-run")
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "run_dir=mismatch" in item for item in gold.evidence))

    def test_gold_run_rechecks_current_run_for_secrets_after_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            (run_dir / "late-secret.log").write_text("leak " + "sk" + "-late-secret-token", encoding="utf-8")

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "current_secret_scan=blocked:1" in item for item in gold.evidence))

    def test_gold_run_rechecks_current_required_artifact_safety_after_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_mtime = (run_dir / "15-gold-run-verification.json").stat().st_mtime_ns
            artifact = run_dir / "10-claim-consistency.json"
            external = root / "outside-claim-consistency.json"
            external.write_bytes(artifact.read_bytes())
            os.utime(external, ns=(verification_mtime - 1_000_000_000, verification_mtime - 1_000_000_000))
            artifact.unlink()
            artifact.symlink_to(external)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "artifact_safety=blocked:1" in item for item in gold.evidence))

    def test_gold_run_requires_final_verification_artifact_safety_summary_consistency(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            verification["artifact_safety"]["unsafe_artifacts"] = [{"path": "10-claim-consistency.json", "issue": "symlink"}]
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "artifact_safety=pass:0" in item
                and "artifact_safety_summary=mismatch=1" in item
                and "artifact_hashes=match" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_rejects_malformed_final_verification_artifact_safety_items(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            verification = json.loads(verification_path.read_text(encoding="utf-8"))
            malformed = [{"path": "", "issue": "symlink"}]
            verification["unsafe_artifacts"] = malformed
            verification["artifact_safety"]["status"] = "blocked"
            verification["artifact_safety"]["unsafe_artifacts"] = malformed
            write_json(verification_path, verification)

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(
            any(
                "verification=ready" in item
                and "artifact_safety=blocked:1" in item
                and "artifact_safety_summary=missing" in item
                and "artifact_hashes=match" in item
                and "freshness=fresh" in item
                for item in gold.evidence
            )
        )

    def test_gold_run_requires_final_verification_newer_than_required_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "gold-run"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_run(run_dir)
            verification_path = run_dir / "15-gold-run-verification.json"
            artifact_path = run_dir / "10-claim-consistency.json"
            verification_mtime = verification_path.stat().st_mtime_ns
            write_json(artifact_path, {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})
            os.utime(artifact_path, ns=(verification_mtime + 1_000_000_000, verification_mtime + 1_000_000_000))

            report = build_perfect_agent_readiness(root, runs_dir)

        statuses = {item.capability_id: item.status for item in report.capabilities}
        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(report.status, "block")
        self.assertEqual(statuses["gold_end_to_end_run"], "block")
        self.assertTrue(any("gold_criteria=8/9" in item for item in gold.evidence))
        self.assertTrue(any("verification=ready" in item and "freshness=stale" in item for item in gold.evidence))

    def test_gold_candidate_evidence_prefers_end_to_end_over_standalone_pack_on_tie(self) -> None:
        standalone = _summary_stub(
            id="benchmark-pack",
            readiness_score=4.5,
            benchmark_evidence_status="warn",
            benchmark_evidence_grade="real_benchmark",
            adapter_paper_grade_status="ready",
            repair_queue_block=0,
            artifact_count=15,
        )
        end_to_end = _summary_stub(
            id="blocked-gold-run",
            readiness_score=0.0,
            paper_grade_literature_status="pass",
            benchmark_evidence_status="warn",
            benchmark_evidence_grade="real_benchmark",
            adapter_paper_grade_status="ready",
            claim_preflight_status="review_required",
            claim_consistency_status="review_required",
            final_readiness_status="requires_revision",
            package_status="blocked",
            final_handoff_status="blocked",
            repair_queue_block=2,
            artifact_count=80,
        )

        evidence = _gold_candidate_evidence([standalone, end_to_end], standalone)

        self.assertTrue(any("closest_run=blocked-gold-run" in item for item in evidence))

    def test_method_capability_detects_benchmark_readme_parameter_mapping(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_formal_manifest_set(root)
            _write_formal_manifest_readme_mapping(root)

            report = build_perfect_agent_readiness(root, root / "runs")
            rendered = render_perfect_agent_readiness_markdown(report)

        method = next(item for item in report.capabilities if item.capability_id == "candidate_baseline_ablation_implementations")
        self.assertEqual(method.status, "ready")
        self.assertTrue(any("parameter_mapping_readme=ready" in item for item in method.evidence))
        self.assertFalse(any("参数映射写入 benchmark pack README" in item for item in method.next_actions))
        self.assertTrue(any("保持 README/manifest 参数映射同步" in item for item in method.next_actions))
        self.assertIn("parameter_mapping_readme=ready", rendered)

    def test_statistical_design_prioritizes_multiplicity_power_evidence(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = [_summary_stub(id="older-statistics"), _summary_stub(id="complete-design")]
            run_dirs = {run.id: root / run.id for run in runs}
            _write_statistics_run(run_dirs["older-statistics"], design=False)
            _write_statistics_run(run_dirs["complete-design"], design=True)

            capability = _statistics_design_check(runs, run_dirs)

        self.assertEqual(capability.status, "ready")
        self.assertIn("complete-design", capability.evidence[0])
        self.assertIn("multiplicity=pass", capability.evidence[0])
        self.assertIn("power=profile_ready", capability.evidence[0])
        self.assertTrue(any("older-statistics" in item and "multiplicity/power=missing" in item for item in capability.evidence[1:]))
        self.assertTrue(any("继续用 statistical_design.multiplicity/power_analysis" in item for item in capability.next_actions))

    def test_statistical_design_uses_configured_repeat_threshold(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            _write_formal_manifest_set(root)
            _write_project_scaffold(root)
            _write_gold_launch_config(root, paper_grade_lines=["min_execution_repeats = 5"])
            _write_gold_run(runs_dir / "gold-run")

            report = build_perfect_agent_readiness(root, runs_dir)

        statistical = next(item for item in report.capabilities if item.capability_id == "statistical_design")
        self.assertEqual(statistical.status, "review_required")
        self.assertTrue(any("repeats=3" in item for item in statistical.evidence))
        self.assertTrue(any("repeats>=5" in item for item in statistical.gaps))
        self.assertTrue(any("至少 5 次" in item for item in statistical.next_actions))

    def test_reproducible_environment_reports_release_environment_url(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
            run = _summary_stub(id="release-env-run")
            run_dir = root / "runs" / run.id
            run_dir.mkdir(parents=True)
            write_json(run_dir / "04-environment-snapshot.json", {"source_tree": {"aggregate_sha256": "a" * 64}})
            write_json(
                run_dir / "10-release-metadata.json",
                {"metadata": {"environment_url": "https://example.test/research-agent/environment"}},
            )

            capability = _reproducible_environment_check(root, [run], {run.id: run_dir})

        self.assertEqual(capability.status, "ready")
        self.assertTrue(any("release_environment_urls=1" in item for item in capability.evidence))
        self.assertTrue(any("保持环境文件" in item for item in capability.next_actions))
        self.assertFalse(any("归档 Docker/Conda/requirements 环境 URL" in item for item in capability.next_actions))

    def test_external_integrations_report_release_archive_field_coverage(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Zotero EndNote Zenodo OSF GitHub integration notes\n", encoding="utf-8")
            run = _summary_stub(id="release-ready-run")
            run_dir = root / "runs" / run.id
            run_dir.mkdir(parents=True)
            write_json(
                run_dir / "10-release-metadata.json",
                {
                    "status": "ready_for_release",
                    "metadata": {
                        "code_repository_url": "https://github.com/research-lab/agent",
                        "code_archive_doi": "10.5281/zenodo.1234567",
                        "data_archive_doi": "10.24432/C56C76",
                        "environment_url": "https://zenodo.org/records/1234567",
                    },
                },
            )

            capability = _external_integration_check(root, [run], {run.id: run_dir})

        self.assertEqual(capability.status, "ready")
        self.assertTrue(any("release_archive_fields=complete:1/1" in item for item in capability.evidence))
        self.assertTrue(any("code_archive:1/1" in item and "data_archive:1/1" in item for item in capability.evidence))
        self.assertTrue(any("带入 gold run" in item for item in capability.next_actions))
        self.assertFalse(any("为 gold run 填写 release metadata" in item for item in capability.next_actions))

    def test_external_integrations_review_when_ready_release_metadata_lacks_archives(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("Zotero EndNote Zenodo OSF GitHub integration notes\n", encoding="utf-8")
            run = _summary_stub(id="release-ready-run")
            run_dir = root / "runs" / run.id
            run_dir.mkdir(parents=True)
            write_json(run_dir / "10-release-metadata.json", {"status": "ready_for_release"})

            capability = _external_integration_check(root, [run], {run.id: run_dir})

        self.assertEqual(capability.status, "review_required")
        self.assertTrue(any("release_archive_fields=complete:0/1" in item for item in capability.evidence))
        self.assertTrue(any("字段不完整" in item for item in capability.gaps))

    def test_human_ui_reports_perfect_readiness_and_benchmark_manifest_guide(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            web = root / "web"
            web.mkdir()
            (web / "index.html").write_text(
                "\n".join(
                    [
                        '<button id="perfect-readiness"></button>',
                        '<button id="benchmark-template"></button>',
                        '<button id="benchmark-manifest-lint"></button>',
                        '<button id="benchmark-manifest-save"></button>',
                        '<textarea id="benchmark-manifest-draft"></textarea>',
                    ]
                ),
                encoding="utf-8",
            )
            (web / "app.js").write_text(
                "approve approve_execution repair worker_active "
                "/api/perfect-readiness /api/benchmark-template /api/benchmark-manifest-lint /api/benchmark-manifest-save",
                encoding="utf-8",
            )
            (web / "styles.css").write_text("body { color: #111; }\n", encoding="utf-8")
            src = root / "src" / "research_agent"
            src.mkdir(parents=True)
            (src / "web_server.py").write_text(
                'ThreadingHTTPServer worker_active approve approve_execution repair '
                '/api/perfect-readiness '
                'parsed.path == "/api/benchmark-template" '
                'parsed.path == "/api/benchmark-manifest-lint" '
                'parsed.path == "/api/benchmark-manifest-save"',
                encoding="utf-8",
            )

            capability = _human_ui_check(root)

        self.assertEqual(capability.status, "ready")
        self.assertTrue(any("perfect_readiness_panel=True" in item for item in capability.evidence))
        self.assertTrue(any("benchmark_manifest_guide=True" in item for item in capability.evidence))
        self.assertTrue(any("继续保持 perfect-readiness 面板" in item for item in capability.next_actions))
        self.assertFalse(any("继续增加 perfect-readiness 面板" in item for item in capability.next_actions))

    def test_gold_blocker_reports_server_env_focus_when_local_launch_inputs_are_ready(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir)

                report = build_perfect_agent_readiness(root, runs_dir)
                rendered = render_perfect_agent_readiness_markdown(report)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("gold_config_benchmark_manifests=pass" in item for item in gold.evidence))
        self.assertTrue(any("roles=ablation,baseline,candidate" in item for item in gold.evidence))
        self.assertTrue(any("paper_grade_literature_probe=pass" in item for item in gold.evidence))
        self.assertTrue(any("online_sources=2/3" in item and "doi_url_seeds=3/3" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_output=available" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_secret_flow=pass" in item for item in gold.evidence))
        self.assertTrue(any("hidden_key_prompt=2/2" in item and "model_default=2/2" in item for item in gold.evidence))
        self.assertTrue(any("gold_post_launch_verifier=pass" in item for item in gold.evidence))
        self.assertTrue(any("required_artifacts=23/23" in item and "web_auto_write=True" in item for item in gold.evidence))
        self.assertTrue(any("schema_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("required_list_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("artifact_hash_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("contract_evidence_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("verification_summary_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("secret_scan_summary_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("artifact_safety=True" in item for item in gold.evidence))
        self.assertTrue(any("artifact_safety_summary_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("manifest_inventory_summary_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("current_manifest_inventory_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("audit_contracts=True" in item and "current_audit_contract=True" in item and "audit_names=7/7" in item for item in gold.evidence))
        self.assertTrue(any("audit_summary_contract=True" in item for item in gold.evidence))
        self.assertTrue(any("cli_env_final_audit=True" in item for item in gold.evidence))
        self.assertTrue(any("cli_env_resilient_audit=True" in item for item in gold.evidence))
        self.assertTrue(any("gold_verification_repair_resume=True" in item for item in gold.evidence))
        self.assertTrue(any("direct_launch_repair_resume=True" in item for item in gold.evidence))
        self.assertTrue(any("direct_launch_perfect_readiness=True" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=server_environment" in item for item in gold.evidence))
        self.assertTrue(any("server_env_present=0/4" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_gateway_socket=" in item for item in gold.evidence))
        self.assertFalse(any("@" in item and "gold_launch_gateway_socket=" in item for item in gold.evidence))
        self.assertTrue(any("scripts/start_gold_web_env.sh" in item for item in gold.evidence))
        self.assertTrue(any("scripts/run_gold_cli_env.sh" in item for item in gold.evidence))
        self.assertTrue(any("scripts/start_gold_web_env.sh" in item for item in gold.next_actions))
        self.assertTrue(any("RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh" in item for item in gold.next_actions))
        self.assertIn("gold_launch_prereq", rendered)
        self.assertIn("scripts/run_gold_cli_env.sh", rendered)
        self.assertNotIn("sk-", rendered)
        self.assertNotIn("OPENAI_API_KEY", rendered)

    def test_gold_blocker_rejects_placeholder_contact_email_without_echoing_it(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:8317"
            os.environ["OPENAI_MODEL"] = "gpt-5.5"
            os.environ["OPENAI_API_KEY"] = "unit-test-api-token"
            os.environ["RESEARCH_AGENT_CONTACT_EMAIL"] = "agent@example.org"
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir)

                report = build_perfect_agent_readiness(root, runs_dir)
                rendered = render_perfect_agent_readiness_markdown(report)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        evidence = "\n".join(gold.evidence)
        self.assertEqual(gold.status, "block")
        self.assertIn("gold_launch_focus=server_environment", evidence)
        self.assertIn("server_env_present=3/4", evidence)
        self.assertIn("invalid_env=1", evidence)
        self.assertNotIn("agent@example.org", rendered)
        self.assertNotIn("OPENAI_API_KEY", rendered)
        self.assertNotIn("sk-", rendered)

    def test_gold_blocker_focuses_literature_probe_before_server_env(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir, literature_probe=False)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("paper_grade_literature_probe=missing" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=paper_grade_literature_probe" in item for item in gold.evidence))
        self.assertTrue(any("paper-grade-probe" in item for item in gold.next_actions))

    def test_gold_blocker_uses_configured_literature_probe_thresholds(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root)
                config_path = root / "examples" / "uci-iris-paper-grade-config.toml"
                config_path.write_text(
                    config_path.read_text(encoding="utf-8")
                    + "\n\n[paper_grade]\n"
                    + "min_literature_sources = 4\n"
                    + "min_successful_literature_sources = 3\n"
                    + "min_seed_papers = 4\n"
                    + "min_doi_url_seed_papers = 4\n",
                    encoding="utf-8",
                )
                _write_gold_launch_support_runs(runs_dir)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        evidence = "\n".join(gold.evidence)
        self.assertIn("paper_grade_literature_probe=pass", evidence)
        self.assertIn("configured_sources=3/4", evidence)
        self.assertIn("successful_sources=2/3", evidence)
        self.assertIn("strong_seeds=3/4", evidence)
        self.assertIn("resolved_seeds=3/4", evidence)
        self.assertIn("gold_launch_focus=paper_grade_literature_probe", evidence)
        self.assertTrue(any("至少 4 个来源" in item and "至少 3 个来源返回候选" in item for item in gold.next_actions))

    def test_gold_blocker_focuses_config_benchmark_manifests_before_literature_probe(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root, benchmark_manifests=False)
                _write_gold_launch_support_runs(runs_dir, literature_probe=True)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("gold_config_benchmark_manifests=block" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=benchmark_manifest" in item for item in gold.evidence))
        self.assertTrue(any("benchmark_manifest_paths" in item for item in gold.next_actions))

    def test_gold_blocker_uses_configured_benchmark_role_threshold(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root)
                config_path = root / "examples" / "uci-iris-paper-grade-config.toml"
                config_path.write_text(
                    config_path.read_text(encoding="utf-8")
                    + "\n\n[paper_grade]\n"
                    + "min_benchmark_roles = 4\n",
                    encoding="utf-8",
                )
                _write_gold_launch_support_runs(runs_dir, literature_probe=True)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        evidence = "\n".join(gold.evidence)
        self.assertEqual(gold.status, "block")
        self.assertIn("gold_config_benchmark_manifests=block", evidence)
        self.assertIn("formal_roles=3/4", evidence)
        self.assertIn("required_roles=4", evidence)
        self.assertIn("gold_launch_focus=benchmark_manifest", evidence)

    def test_gold_blocker_focuses_existing_output_directory_before_server_env(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL", "RESEARCH_AGENT_GOLD_OUT"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir)
                (root / "runs" / "iris-classification-benchmark-smoke-gold-run").mkdir(parents=True)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("gold_launch_output=exists" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=output_directory" in item for item in gold.evidence))
        self.assertTrue(any("RESEARCH_AGENT_GOLD_OUT" in item for item in gold.next_actions))

    def test_gold_blocker_focuses_launch_secret_flow_before_server_env(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL", "RESEARCH_AGENT_GOLD_OUT"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root, safe_gold_scripts=False)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("gold_launch_secret_flow=block" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=launch_secret_flow" in item for item in gold.evidence))
        self.assertTrue(any("OPENAI_API_KEY" in item for item in gold.next_actions))

    def test_gold_blocker_focuses_post_launch_verifier_before_server_env(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL", "RESEARCH_AGENT_GOLD_OUT"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root, verifier=False)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("gold_post_launch_verifier=block" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=post_launch_verification" in item for item in gold.evidence))
        self.assertTrue(any("gold-run-verify" in item for item in gold.next_actions))

    def test_gold_blocker_rejects_verifier_without_audit_contract_summary(self) -> None:
        env_keys = ["OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL", "RESEARCH_AGENT_GOLD_OUT"]
        previous_env = {key: os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:
                os.environ.pop(key, None)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                runs_dir = root / "runs"
                _write_formal_manifest_set(root)
                _write_project_scaffold(root, verifier=True, verifier_audit_contracts=False)
                _write_gold_launch_config(root)
                _write_gold_launch_support_runs(runs_dir)

                report = build_perfect_agent_readiness(root, runs_dir)
        finally:
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        gold = next(item for item in report.capabilities if item.capability_id == "gold_end_to_end_run")
        self.assertEqual(gold.status, "block")
        self.assertTrue(any("gold_post_launch_verifier=block" in item and "audit_contracts=False" in item for item in gold.evidence))
        self.assertTrue(any("required_artifacts=23/23" in item for item in gold.evidence))
        self.assertTrue(any("gold_launch_focus=post_launch_verification" in item for item in gold.evidence))


def _write_formal_manifest_set(root: Path) -> None:
    base = root / "benchmarks" / "formal-motion"
    for role, method in [("candidate", "ours"), ("baseline", "rrtstar"), ("ablation", "ours_no_map")]:
        manifest_dir = base / role
        manifest_dir.mkdir(parents=True)
        data = {
            "name": f"{role} formal adapter",
            "role": role,
            "command": ["python3", "grade.py", "--method", method, "--metrics", "metrics.json"],
            "source_files": ["grade.py", f"{method}.py"],
            "metrics_path": "metrics.json",
            "expected_artifacts": ["metrics.json"],
            "benchmark_kind": "external",
            "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
            "citation": "10.1109/MRA.2012.2205651",
            "grader": "grade.py",
        }
        (manifest_dir / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


def _write_formal_manifest_readme_mapping(root: Path) -> None:
    readme = root / "benchmarks" / "formal-motion" / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Formal Motion Benchmark Pack",
                "",
                "## Primary Role Parameter Mapping",
                "",
                "| Role | Manifest | Method flag | Metrics artifact |",
                "| --- | --- | --- | --- |",
                "| `candidate` | `manifest.json` | `--method ours` | `metrics.json` |",
                "| `baseline` | `manifest.json` | `--method rrtstar` | `metrics.json` |",
                "| `ablation` | `manifest.json` | `--method ours_no_map` | `metrics.json` |",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_project_scaffold(root: Path, *, safe_gold_scripts: bool = True, verifier: bool = True, verifier_audit_contracts: bool = True) -> None:
    (root / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
    (root / "README.md").write_text("Zotero EndNote Zenodo OSF GitHub integration notes\n", encoding="utf-8")
    (root / "web").mkdir()
    (root / "web" / "index.html").write_text("<button>approve</button>\n", encoding="utf-8")
    (root / "web" / "app.js").write_text("approve approve_execution repair worker_active\n", encoding="utf-8")
    (root / "web" / "styles.css").write_text("body { color: #111; }\n", encoding="utf-8")
    src = root / "src" / "research_agent"
    src.mkdir(parents=True)
    web_source = "ThreadingHTTPServer worker_active approve approve_execution repair\n"
    if verifier:
        web_source += "_write_gold_verification_if_gold_launch write_gold_run_verification_artifacts(out_dir) _write_gold_verification_followups(out_dir, report) write_repair_resume_plan_artifacts( gold_verification_report_path=verification_json write_perfect_agent_readiness_artifacts(ROOT, RUNS_DIR, ROOT, limit=0) gold-run-verify perfect-readiness\n"
        web_source += "_public_gold_unsafe_artifacts unsafe_artifact_count manifest_inventory_unsafe_path_count\n"
        if verifier_audit_contracts:
            web_source += "_public_gold_audit_contracts audit_contract_ready_count\n"
    (src / "web_server.py").write_text(web_source, encoding="utf-8")
    (src / "run_economics_audit.py").write_text("", encoding="utf-8")
    (src / "repair_queue.py").write_text("", encoding="utf-8")
    (src / "repair_resume.py").write_text("", encoding="utf-8")
    (src / "execution_safety.py").write_text("allowed_commands timeout experiments\n", encoding="utf-8")
    (src / "experiments.py").write_text("allowed_commands timeout experiments\n", encoding="utf-8")
    if verifier:
        (src / "cli.py").write_text(
            "gold-run-verify write_gold_run_verification_artifacts build_gold_run_verification_report "
            "--gold-run-verification-report --write-repair-resume-plan write_repair_resume_plan_artifacts "
            "_print_gold_verification_repair_resume_plan(result_dir, result_dir / GOLD_RUN_VERIFICATION_JSON) "
            "_print_gold_launch_perfect_readiness(args.project_dir, result_dir.parent) "
            "write_perfect_agent_readiness_artifacts(project_dir, runs_dir, project_dir) Perfect readiness status:\n",
            encoding="utf-8",
        )
        (src / "repair_resume.py").write_text("gold_verification_report_path _gold_verification_repair_items gold-run-verification\n", encoding="utf-8")
        doctor_lines = [
            'GOLD_RUN_VERIFICATION_JSON = "15-gold-run-verification.json"',
            "write_gold_run_verification_artifacts build_gold_run_verification_report",
            "schema_version read_only",
            "contract_evidence",
            "_gold_run_secret_scan _SECRET_SCAN_RULES _secret_scan_file_reference_issue unsafe_file_reference secret_scan",
            "auth_header_token env_api_key_assignment json_api_key_field openai_style_token query_api_key_token unsafe_file_reference",
            "_gold_unsafe_required_artifacts required_artifact_safety",
            "_gold_manifest_inventory_unsafe_paths unsafe_artifact_paths",
            "state.json",
            "run-config.json",
            "run-manifest.json",
            "run-llm-ledger.json",
            "01-literature-gate-decision.json",
            "04-benchmark-evidence-audit.json",
            "10-claim-traceability.json",
            "10-claim-consistency.json",
            "10-final-readiness.json",
            "10-release-metadata.json",
            "11-submission-package.json",
            "11-submission-package.zip",
            "12-repair-queue.json",
            "13-llm-trace-audit.json",
            "13-llm-runtime-contract.json",
            "13-run-economics-audit.json",
            "13-agent-observability-audit.json",
            "13-llm-observability-summary.json",
            "13-agent-stage-contract.json",
            "13-agent-trajectory.json",
            "13-research-scorecard.json",
            "14-run-integrity-audit.json",
            "14-final-handoff.json",
        ]
        if verifier_audit_contracts:
            doctor_lines.extend(
                [
                    "_candidate_audit_contracts_evidence audit_contracts_ready",
                    "llm_trace llm_runtime run_economics agent_observability llm_observability stage_contract trajectory",
                ]
            )
            (src / "perfect_agent_readiness.py").write_text(
                "_gold_verification_audit_contracts_ready audit_contracts= malformed_audit_names\n"
                "_gold_verification_schema_ready _gold_verification_subschemas_ready schema= subschemas=\n"
                "_gold_verification_required_artifacts_ready extra= duplicate= malformed=\n"
                "_gold_verification_artifact_hash_state extra_names malformed_names artifact_hashes=\n"
                "_gold_verification_contract_evidence_state _gold_verification_final_zip_summary_ready contract_evidence= final_zip_summary= top_level\n"
                "_gold_verification_summary_ready missing_malformed= repair_malformed= verification_summary=\n"
                "_gold_verification_secret_scan_summary_ready _GOLD_VERIFICATION_SECRET_SCAN_RULES malformed_findings malformed_rules secret_malformed_findings= secret_scan_summary=\n"
                "_gold_verification_artifact_safety_ready artifact_safety= unsafe=\n"
                "_gold_verification_artifact_safety_summary_ready artifact_safety_summary=\n"
                "_gold_verification_manifest_inventory_summary_ready malformed_manifest_inventory_items manifest_inventory_summary=\n"
                "_gold_manifest_inventory_check _gold_required_artifact_hashes _gold_current_manifest_inventory_ready current_manifest_inventory=\n"
                "_gold_verification_audit_summary_ready audit_summary=\n"
                "_GOLD_VERIFICATION_AUDIT_CONTRACT_ARTIFACTS _gold_current_audit_contracts_ready current_audit_contracts=\n",
                encoding="utf-8",
            )
        else:
            (src / "perfect_agent_readiness.py").write_text(
                "_gold_verification_schema_ready _gold_verification_subschemas_ready schema= subschemas=\n"
                "_gold_verification_required_artifacts_ready extra= duplicate= malformed=\n"
                "_gold_verification_artifact_hash_state extra_names malformed_names artifact_hashes=\n"
                "_gold_verification_contract_evidence_state _gold_verification_final_zip_summary_ready contract_evidence= final_zip_summary= top_level\n"
                "_gold_verification_summary_ready missing_malformed= repair_malformed= verification_summary=\n"
                "_gold_verification_secret_scan_summary_ready _GOLD_VERIFICATION_SECRET_SCAN_RULES malformed_findings malformed_rules secret_malformed_findings= secret_scan_summary=\n"
                "_gold_verification_artifact_safety_ready artifact_safety= unsafe=\n"
                "_gold_verification_artifact_safety_summary_ready artifact_safety_summary=\n"
                "_gold_verification_manifest_inventory_summary_ready malformed_manifest_inventory_items manifest_inventory_summary=\n"
                "_gold_manifest_inventory_check _gold_required_artifact_hashes _gold_current_manifest_inventory_ready current_manifest_inventory=\n"
                "_gold_verification_audit_summary_ready audit_summary=\n"
                "_GOLD_VERIFICATION_AUDIT_CONTRACT_ARTIFACTS _gold_current_audit_contracts_ready current_audit_contracts=\n",
                encoding="utf-8",
            )
        (src / "gold_run_doctor.py").write_text("\n".join(doctor_lines), encoding="utf-8")
    else:
        (src / "cli.py").write_text("", encoding="utf-8")
        (src / "gold_run_doctor.py").write_text("", encoding="utf-8")
        (src / "perfect_agent_readiness.py").write_text("", encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    script_text = (
        'export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:8317}"\n'
        'export OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.5}"\n'
        "ensure_llm_gateway_reachable\n"
        "prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL\n"
        "prompt_required_secret OPENAI_API_KEY\n"
        'python3 -m research_agent gold-run-launch --topic "$TOPIC" --gold-defaults --out "$OUT_DIR"\n'
        'python3 -m research_agent gold-run-verify --run-dir "$OUT_DIR"\n'
        'python3 -m research_agent perfect-readiness --project-dir . --runs-dir "$readiness_runs_dir" --out .\n'
        'python3 -m research_agent repair-resume "$OUT_DIR" --dry-run --gold-run-verification-report "$OUT_DIR/15-gold-run-verification.json"\n'
        "launch_status=$?\n"
        "audit_status=$?\n"
        'if [[ -d "$OUT_DIR" ]]; then\n'
        'return "$launch_status"\n'
        "run_gold_launch_with_final_audit\n"
        "run_final_gold_audits\n"
        "read -rsp \"$name: \" value\n"
    )
    if not safe_gold_scripts:
        script_text = "prompt_required_secret OPENAI_API_KEY\nread -rp \"$name: \" value\n"
    (scripts / "start_gold_web_env.sh").write_text(script_text, encoding="utf-8")
    (scripts / "run_gold_cli_env.sh").write_text(script_text, encoding="utf-8")


def _write_gold_launch_config(root: Path, *, benchmark_manifests: bool = True, paper_grade_lines: list[str] | None = None) -> None:
    examples = root / "examples"
    examples.mkdir()
    lines = [
        "[llm]",
        'base_url_env = "OPENAI_BASE_URL"',
        'model_env = "OPENAI_MODEL"',
        'api_key_env = "OPENAI_API_KEY"',
        "",
        "[literature]",
        'contact_email_env = "RESEARCH_AGENT_CONTACT_EMAIL"',
    ]
    if benchmark_manifests:
        lines.extend(
            [
                "",
                "[execution]",
                "benchmark_manifest_paths = [",
                '  "benchmarks/formal-motion/candidate/manifest.json",',
                '  "benchmarks/formal-motion/baseline/manifest.json",',
                '  "benchmarks/formal-motion/ablation/manifest.json",',
                "]",
            ]
        )
    if paper_grade_lines:
        lines.extend(["", "[paper_grade]", *paper_grade_lines])
    (examples / "uci-iris-paper-grade-config.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_gold_launch_support_runs(runs_dir: Path, *, literature_probe: bool = True) -> None:
    benchmark = runs_dir / "uci-iris-expanded-baseline-pack-run"
    benchmark.mkdir(parents=True)
    write_json(
        benchmark / "04-benchmark-evidence-audit.json",
        {"evidence_grade": "real_benchmark", "adapter_paper_grade_status": "ready"},
    )
    fulltext = runs_dir / "uci-iris-fulltext-grounding"
    fulltext.mkdir(parents=True)
    write_json(fulltext / "01-fulltext-corpus.json", {"total_chunks": 3})
    write_json(fulltext / "10-citation-grounding.json", {"status": "pass"})
    if literature_probe:
        probe = runs_dir / "uci-iris-paper-grade-probe"
        probe.mkdir(parents=True)
        write_json(
            probe / "00-paper-grade-online-probe.json",
            {
                "status": "pass",
                "source_summary": {
                    "provider": "online",
                    "configured_sources": 3,
                    "successful_sources": 2,
                },
                "seed_summary": {
                    "strong_seed_papers": 3,
                    "metadata_resolved_seed_papers": 3,
                },
                "candidate_count": 8,
            },
        )


def _write_statistics_run(run_dir: Path, *, design: bool) -> None:
    run_dir.mkdir(parents=True)
    report = {
        "repeats": 3,
        "comparisons": [{"metric": "accuracy", "ci_low": -0.1, "ci_high": 0.1, "effect_size": 0.0}],
        "warnings": [],
    }
    if design:
        report["multiplicity"] = {"status": "pass", "family_size": 1, "primary_metrics": ["accuracy"]}
        report["power_analysis"] = {"status": "profile_ready", "per_group_repeats": 3}
    write_json(run_dir / "04-statistics.json", report)


def _write_gold_run(
    run_dir: Path,
    *,
    claim_traceability: bool = True,
    claim_consistency: bool = True,
    final_handoff_status: str = "ready_for_human_handoff",
    package_status: str = "ready_for_human_submission_upload",
    scorecard_status: str = "ready_for_human_submission_upload",
    integrity_status: str = "pass",
    economics_status: str = "pass",
    gold_verification: bool = True,
    package_zip_valid: bool | None = True,
) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "gold", "stage": "completed", "updated_at": "2026-07-05T00:00:00+08:00"})
    write_json(run_dir / "run-config.json", {"llm": {"api_key": ""}, "literature": {"semantic_scholar_api_key": "", "openalex_api_key": "", "contact_email": ""}})
    write_json(run_dir / "run-manifest.json", {"events": [{"stage": "completed"}], "artifacts": [{"path": "state.json"}, {"path": "run-manifest.json"}, {"path": "run-llm-ledger.json"}]})
    write_json(run_dir / "run-llm-ledger.json", {"summary": {"total_calls": 3, "successful_calls": 3}, "calls": [{"stage": "paper_revision", "status": "success"}]})
    write_json(
        run_dir / "02-agent-team.json",
        {
            "status": "active",
            "active_agents": ["literature_scout", "evidence_curator", "method_architect", "benchmark_engineer", "statistician", "skeptical_reviewer", "manuscript_editor"],
            "task_routes": [
                {"task_type": "literature_repair", "status": "active", "all_agents": ["literature_scout", "evidence_curator", "gap_analyst"]},
                {"task_type": "gap_to_idea", "status": "active", "all_agents": ["gap_analyst", "method_architect", "evidence_curator"]},
                {"task_type": "benchmark_execution", "status": "active", "all_agents": ["benchmark_engineer", "statistician", "method_architect", "skeptical_reviewer"]},
                {"task_type": "paper_deliberation", "status": "active", "all_agents": ["evidence_curator", "method_architect", "statistician", "skeptical_reviewer", "manuscript_editor"]},
            ],
        },
    )
    write_json(run_dir / "01-literature-gate-decision.json", {"paper_grade_literature": {"status": "pass", "issues": []}})
    write_json(run_dir / "04-benchmark-evidence-audit.json", {"status": "pass", "evidence_grade": "real_benchmark", "adapter_paper_grade_status": "ready", "adapter_paper_grade_issues": []})
    if claim_consistency:
        write_json(run_dir / "10-claim-consistency.json", {"status": "pass", "consistency_score": 1.0, "blocking_issues": [], "manual_tasks": []})
    else:
        write_json(run_dir / "10-claim-consistency.json", {"status": "block", "consistency_score": 0.0, "blocking_issues": ["claim blocked"], "manual_tasks": []})
    write_json(run_dir / "11-submission-package.json", {"status": package_status, "blocking_issues": ["package blocked"] if package_status == "blocked" else [], "manual_tasks": []})
    final_handoff = {"status": final_handoff_status, "blocking_issues": [], "manual_tasks": []}
    if package_zip_valid is not None:
        final_handoff["package_zip_valid"] = package_zip_valid
    write_json(run_dir / "14-final-handoff.json", final_handoff)
    write_json(run_dir / "12-repair-queue.json", {"status": "pass", "summary": {"total": 0, "block": 0, "high": 0, "medium": 0}})
    write_json(run_dir / "13-research-scorecard.json", {"status": scorecard_status, "overall_score": 95, "blocking_issues": ["scorecard blocked"] if scorecard_status == "blocked" else [], "manual_tasks": []})
    write_json(run_dir / "14-run-integrity-audit.json", {"status": integrity_status, "summary": {"pass": 12, "warn": 0, "block": 0}, "blocking_issues": ["integrity blocked"] if integrity_status == "block" else [], "warnings": []})
    write_json(run_dir / "04-environment-snapshot.json", {"source_tree": {"aggregate_sha256": "a" * 64}})
    write_json(run_dir / "01-fulltext-corpus.json", {"total_chunks": 8})
    write_json(run_dir / "10-citation-grounding.json", {"status": "pass"})
    write_json(
        run_dir / "04-statistics.json",
        {
            "repeats": 3,
            "comparisons": [{"metric": "success_rate", "ci_low": 0.05, "ci_high": 0.2, "effect_size": 1.2, "direction": "candidate_better"}],
            "warnings": [],
            "multiplicity": {"status": "pass", "family_size": 1, "primary_metrics": ["success_rate"]},
            "power_analysis": {"status": "profile_ready", "per_group_repeats": 3, "minimum_detectable_standardized_effect": 2.286},
        },
    )
    if claim_traceability:
        write_json(run_dir / "10-claim-traceability.json", {"status": "pass", "total_claims": 3, "traceability_score": 1.0, "blocked_claims": 0, "blocking_issues": []})
        write_json(run_dir / "10-agent-claim-audit.json", {"status": "pass", "claim_owner_summary": {"total_claims": 3, "mapped_claims": 3, "orphaned_claims": 0}, "blocking_issues": [], "manual_tasks": []})
        write_json(run_dir / "10-agent-deliberation.json", {"status": "pass", "assessment_kind": "independent_agent_deliberation", "independent_agent_execution": True, "independent_verdict_count": 6, "consensus": {"decision": "approve", "approve": 6, "revise": 0, "block": 0}, "agent_verdicts": [{"agent_id": f"agent-{index}", "verdict": "approve"} for index in range(6)], "blocking_issues": [], "manual_tasks": []})
    else:
        write_json(run_dir / "10-claim-traceability.json", {"status": "block", "total_claims": 3, "traceability_score": 0.0, "blocked_claims": 1, "blocking_issues": ["trace blocked"]})
        write_json(run_dir / "10-agent-claim-audit.json", {"status": "review_required", "claim_owner_summary": {"total_claims": 3, "mapped_claims": 2, "orphaned_claims": 1}, "blocking_issues": [], "manual_tasks": ["repair claim owner"]})
        write_json(run_dir / "10-agent-deliberation.json", {"status": "review_required", "consensus": {"decision": "revise", "approve": 3, "revise": 2, "block": 0}, "agent_verdicts": [{"agent_id": f"agent-{index}", "verdict": "revise"} for index in range(5)], "blocking_issues": [], "manual_tasks": ["repair verdict"]})
    write_json(
        run_dir / "13-run-economics-audit.json",
        {
            "status": economics_status,
            "summary": {"total_calls": 3, "failed_calls": 0},
            "blocking_issues": ["economics blocked"] if economics_status == "block" else [],
            "manual_tasks": [],
        },
    )
    write_json(
        run_dir / "10-release-metadata.json",
        {
            "status": "ready_for_release",
            "metadata": {
                "code_repository_url": "https://github.com/research-lab/research-agent",
                "code_archive_doi": "10.5281/zenodo.1234567",
                "data_archive_doi": "10.24432/C56C76",
                "environment_url": "https://zenodo.org/records/1234567",
            },
        },
    )
    write_json(run_dir / "03-execution-safety-audit.json", {"status": "pass"})
    write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "unsupported_after": 0, "blocking_issues": []})
    write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-runtime-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-observability-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-llm-observability-summary.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-stage-contract.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    write_json(run_dir / "13-agent-trajectory.json", {"status": "pass", "blocking_issues": [], "manual_tasks": []})
    with zipfile.ZipFile(run_dir / "11-submission-package.zip", "w") as archive:
        archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
        archive.writestr(
            "submission-package/package-manifest.json",
            json.dumps({"status": "ready_for_human_submission_upload", "files": [{"package_path": "submission-package/CHECKLIST.md"}]}),
        )
    if gold_verification:
        _write_test_run_manifest(run_dir)
        required_artifacts = [
            "state.json",
            "run-config.json",
            "run-manifest.json",
            "run-llm-ledger.json",
            "01-literature-gate-decision.json",
            "04-benchmark-evidence-audit.json",
            "10-claim-traceability.json",
            "10-claim-consistency.json",
            "10-final-readiness.json",
            "10-release-metadata.json",
            "11-submission-package.json",
            "11-submission-package.zip",
            "12-repair-queue.json",
            "13-llm-trace-audit.json",
            "13-llm-runtime-contract.json",
            "13-run-economics-audit.json",
            "13-agent-observability-audit.json",
            "13-llm-observability-summary.json",
            "13-agent-stage-contract.json",
            "13-agent-trajectory.json",
            "13-research-scorecard.json",
            "14-run-integrity-audit.json",
            "14-final-handoff.json",
        ]
        write_json(
            run_dir / "15-gold-run-verification.json",
            {
                "schema_version": 2,
                "status": "ready",
                "gold_contract_ready": True,
                "read_only": True,
                "run_dir": str(run_dir),
                "required_artifacts": required_artifacts,
                "missing_artifacts": [],
                "unsafe_artifacts": [],
                "artifact_safety": {
                    "schema_version": 1,
                    "status": "pass",
                    "checked_artifacts": len(required_artifacts),
                    "unsafe_artifacts": [],
                    "safe_to_render": True,
                },
                "artifact_hashes": _gold_artifact_hashes(run_dir, required_artifacts),
                "manifest_inventory": _gold_manifest_inventory(run_dir, required_artifacts),
                "secret_scan": {
                    "schema_version": 1,
                    "status": "pass",
                    "scanned_files": 12,
                    "skipped_files": 0,
                    "finding_count": 0,
                    "findings": [],
                    "truncated_findings": 0,
                    "rules": [
                        "auth_header_token",
                        "env_api_key_assignment",
                        "json_api_key_field",
                        "openai_style_token",
                        "query_api_key_token",
                        "unsafe_file_reference",
                    ],
                    "safe_to_render": True,
                },
                "check": {"status": "pass"},
                "contract_evidence": {
                    "final_zip_state": "valid",
                    "final_handoff_package_zip_exists": True,
                    "final_handoff_package_zip_valid": True,
                    "audit_contracts_ready": True,
                    "audit_contract_ready_count": 7,
                    "audit_contract_total": 7,
                    "audit_contract_blocking_issues": 0,
                    "audit_contract_manual_tasks": 0,
                    "audit_contracts": _gold_audit_contracts(),
                },
                "repair_plan": [],
            },
        )


def _write_test_run_manifest(run_dir: Path) -> None:
    artifacts = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        data = path.read_bytes()
        artifacts.append({"path": str(path.relative_to(run_dir)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    write_json(run_dir / "run-manifest.json", {"events": [{"stage": "completed"}], "artifacts": artifacts})


def _gold_artifact_hashes(run_dir: Path, required_artifacts: list[str]) -> dict[str, dict[str, int | str]]:
    hashes: dict[str, dict[str, int | str]] = {}
    for name in required_artifacts:
        path = run_dir / name
        hashes[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size}
    return hashes


def _gold_audit_contracts() -> dict[str, dict[str, object]]:
    return {
        name: {"status": "pass", "blocking_issues": 0, "manual_tasks": 0, "ready": True}
        for name in [
            "llm_trace",
            "llm_runtime",
            "run_economics",
            "agent_observability",
            "llm_observability",
            "stage_contract",
            "trajectory",
        ]
    }


def _gold_manifest_inventory(run_dir: Path, required_artifacts: list[str]) -> dict[str, object]:
    manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    by_path = {str(item.get("path") or ""): item for item in artifacts if isinstance(item, dict)}
    current = _gold_artifact_hashes(run_dir, required_artifacts)
    required = [name for name in required_artifacts if name != "run-manifest.json"]
    missing = [name for name in required if name not in by_path]
    duplicates = sorted(name for name in required if sum(int(isinstance(item, dict) and str(item.get("path") or "") == name) for item in artifacts) > 1)
    size_mismatches = [
        name
        for name in required
        if name in by_path and int(by_path[name].get("bytes") or 0) != int(current.get(name, {}).get("size_bytes") or 0)
    ]
    mismatches = [
        name
        for name in required
        if name in by_path and str(by_path[name].get("sha256") or "") != str(current.get(name, {}).get("sha256") or "")
    ]
    return {
        "schema_version": 1,
        "status": "pass" if not missing and not mismatches and not size_mismatches and not duplicates else "blocked",
        "checked_artifacts": len(required),
        "recorded_artifacts": len(by_path),
        "missing_required_artifacts": missing,
        "hash_mismatches": mismatches,
        "size_mismatches": size_mismatches,
        "duplicate_required_artifacts": duplicates,
        "unsafe_artifact_paths": [],
        "safe_to_render": True,
    }


def _write_high_readiness_non_gold_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(run_dir / "state.json", {"topic": "decoy", "stage": "completed", "updated_at": "2026-07-05T01:00:00+08:00"})
    write_json(run_dir / "01-literature-quality.json", {"selected_papers": 10, "total_papers": 10})
    write_json(run_dir / "02-ideas.json", [{"score": 15}])
    write_json(
        run_dir / "04-statistics.json",
        {
            "repeats": 3,
            "comparisons": [{"metric": "score", "ci_low": 0.1, "ci_high": 0.2, "effect_size": 1.0, "direction": "candidate_better"}],
            "warnings": [],
        },
    )
    write_json(run_dir / "10-final-readiness.json", {"status": "ready_for_submission_check", "score_after": 10})


def _summary_stub(**overrides):
    defaults = {
        "id": "run",
        "readiness_score": 0.0,
        "updated_at": "",
        "paper_grade_literature_status": "",
        "benchmark_evidence_status": "",
        "benchmark_evidence_grade": "",
        "adapter_paper_grade_status": "",
        "claim_preflight_status": "",
        "claim_traceability_status": "",
        "claim_traceability_blocked_claims": 0,
        "claim_traceability_blocking_issues": 0,
        "claim_consistency_status": "",
        "claim_consistency_blocking_issues": 0,
        "benchmark_publishable_negative_or_neutral": False,
        "benchmark_claim_boundary_severity": "",
        "final_readiness_status": "",
        "package_status": "",
        "package_blocking_issues": 0,
        "scorecard_status": "",
        "scorecard_blocking_issues": 0,
        "run_integrity_status": "",
        "run_integrity_blocking_issues": 0,
        "run_economics_status": "",
        "run_economics_blocking_issues": 0,
        "final_handoff_status": "",
        "final_handoff_blocking_issues": 0,
        "final_handoff_package_zip_valid": None,
        "repair_queue_block": 0,
        "artifact_count": 0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


if __name__ == "__main__":
    unittest.main()
