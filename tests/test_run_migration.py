from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from types import SimpleNamespace

from research_agent.run_migration import MIGRATION_RECORD_JSON, apply_migration, plan_migration
from research_agent.artifacts import write_json
from research_agent.config import AgentConfig


class MigrationTest(unittest.TestCase):
    def _legacy_run(self, run_dir: Path) -> None:
        """v1 结构 fixture：旧 evidence schema、旧 gate、无绑定批准、无尝试账本。"""
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(run_dir / "04-evidence-integrity.json", {"schema_version": 1, "status": "no_real_evidence"})
        write_json(run_dir / "10-gate-decision.json", {"status": "publishable", "inputs": {}})
        write_json(run_dir / "10-independent-deliberation.json", {"verdicts": [{"verdict": "pass"}]})
        write_json(run_dir / "approval.json", {
            "approved": True, "reviewer": "legacy-user", "stage": "review_approved",
            "notes": "旧批准", "history": [],
        })
        (run_dir / "state.json").write_text(json.dumps({"topic": "legacy", "stage": "completed"}), encoding="utf-8")

    def test_dry_run_lists_findings_without_modifying(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self._legacy_run(run_dir)
            before = sorted(p.name for p in run_dir.iterdir())
            plan = plan_migration(run_dir)
            self.assertTrue(plan["findings"])
            self.assertTrue(any("schema_version=1" in f for f in plan["findings"]))
            self.assertTrue(any("approval_binding_sha256" in f for f in plan["findings"]))
            self.assertTrue(any("不伪造尝试记录" in f for f in plan["findings"]))
            self.assertTrue(any("旧批准将在 apply 时失效" in a for a in plan["actions"]))
            after = sorted(p.name for p in run_dir.iterdir())
            self.assertEqual(before, after, "dry-run 不得修改 run 目录")

    def test_apply_creates_backup_invalidates_approval_and_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self._legacy_run(run_dir)
            result = apply_migration(run_dir)
            # 不可变备份存在且含哈希清单。
            backup = Path(result["backup_dir"])
            self.assertTrue((backup / "BACKUP-MANIFEST.json").exists())
            manifest = json.loads((backup / "BACKUP-MANIFEST.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item["path"] == "approval.json" for item in manifest["files"]))
            # 旧批准失效但内容保留（追加历史，不伪造批准）。
            approval = json.loads((run_dir / "approval.json").read_text(encoding="utf-8"))
            self.assertFalse(approval["approved"])
            self.assertTrue(approval["stale_previous_approval"])
            self.assertTrue(any(h["action"] == "invalidated_by_schema_migration" for h in approval["history"]))
            self.assertEqual(approval["reviewer"], "legacy-user", "原批准内容保留供审计")
            # legacy 标记与迁移记录。
            self.assertEqual(result["migration_status"] if "migration_status" in result else None, None)
            record = json.loads((run_dir / MIGRATION_RECORD_JSON).read_text(encoding="utf-8"))
            self.assertEqual(record["migration_status"], "legacy_unscoped")
            self.assertTrue(record["old_approval_invalidated"])
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["migration"]["status"], "legacy_unscoped")
            # 幂等：重复 apply 不再改动（already-migrated）。
            before = (run_dir / MIGRATION_RECORD_JSON).read_text(encoding="utf-8")
            again = apply_migration(run_dir)
            self.assertTrue(again["already_migrated"])
            self.assertEqual((run_dir / MIGRATION_RECORD_JSON).read_text(encoding="utf-8"), before)

    def test_migrated_run_is_blocked_by_publishable_gate(self) -> None:
        """A36: migration metadata must affect the runtime gate, not only docs."""
        from research_agent.pipeline import _finalize_gate_decision

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self._legacy_run(run_dir)
            apply_migration(run_dir)
            decision, _ = _finalize_gate_decision(
                "legacy",
                run_dir,
                AgentConfig(),
                None,
                agent_deliberation={"status": "pass"},
                claim_consistency={"status": "pass"},
                citation_grounding=SimpleNamespace(status="pass"),
                revised_review=SimpleNamespace(decision="accept"),
                resume=False,
            )
            self.assertEqual(decision["status"], "blocked")
            self.assertIn("deterministic:schema_migration", decision["blocking_sources"])
            self.assertFalse(decision["overridden"])


if __name__ == "__main__":
    unittest.main()
