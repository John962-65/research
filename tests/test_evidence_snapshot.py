from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.evidence_snapshot import (
    SnapshotError,
    build_review_input_snapshot,
    canonical_json_bytes,
    load_review_input_snapshot,
    payload_sha256,
    snapshot_digest,
    verify_snapshot,
    write_review_input_snapshot,
)


class CanonicalJsonTest(unittest.TestCase):
    def test_canonical_form_is_stable(self) -> None:
        payload = {"b": 1, "a": ["中文", {"k": "v"}]}
        self.assertEqual(
            canonical_json_bytes(payload),
            canonical_json_bytes({"a": ["中文", {"k": "v"}], "b": 1}),
        )
        self.assertEqual(payload_sha256(payload), payload_sha256({"b": 1, "a": ["中文", {"k": "v"}]}))

    def test_nan_and_inf_are_rejected(self) -> None:
        # 契约冻结：NaN/Inf 不得静默序列化，直接判 invalid。
        for bad in (float("nan"), float("inf"), {"m": float("nan")}, [{"x": float("-inf")}]):
            with self.subTest(bad=bad):
                with self.assertRaises(SnapshotError):
                    canonical_json_bytes(bad)


class SnapshotRoundtripTest(unittest.TestCase):
    def test_build_digest_and_verify_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "09-revised-paper.md").write_text("# 修订稿", encoding="utf-8")
            snapshot = build_review_input_snapshot(
                run_dir,
                revision=2,
                file_inputs={"09-revised-paper.md": "manuscript", "missing-file.json": "results"},
                inline_inputs={"claim_consistency": {"status": "pass", "detail": "a"}},
                rule_versions={"gate_rule": "2"},
            )
            self.assertEqual(snapshot["revision"], 2)
            self.assertEqual(snapshot["digest"], snapshot_digest(snapshot))
            names = {item["name"] for item in snapshot["items"]}
            self.assertIn("09-revised-paper.md", names)
            self.assertIn("missing-file.json", names)
            missing = next(item for item in snapshot["items"] if item["name"] == "missing-file.json")
            self.assertTrue(missing["missing"])
            # 未变化 → verify 无报告。
            self.assertEqual(verify_snapshot(run_dir, snapshot), [])
            # 文件内容变化 → verify 报告该文件（A08 机制）。
            (run_dir / "09-revised-paper.md").write_text("# 修订稿（改动）", encoding="utf-8")
            self.assertEqual(verify_snapshot(run_dir, snapshot), ["09-revised-paper.md"])

    def test_inline_invalid_input_is_marked_not_fatal(self) -> None:
        with TemporaryDirectory() as tmp:
            snapshot = build_review_input_snapshot(
                Path(tmp), revision=0, file_inputs={}, inline_inputs={"report": {"status": float("nan")}}
            )
            item = snapshot["items"][0]
            self.assertTrue(item["invalid"])
            self.assertIsNone(item["sha256"])
            # 不同的 invalid 名称产生不同快照摘要（名称参与哈希）。
            other = build_review_input_snapshot(
                Path(tmp), revision=0, file_inputs={}, inline_inputs={"other": {"status": float("nan")}}
            )
            self.assertNotEqual(snapshot["digest"], other["digest"])

    def test_write_and_load_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = build_review_input_snapshot(run_dir, revision=1, file_inputs={}, inline_inputs={"a": {"b": 1}})
            write_review_input_snapshot(run_dir, snapshot)
            loaded = load_review_input_snapshot(run_dir)
            self.assertIsNotNone(loaded)
            self.assertEqual(snapshot_digest(loaded), snapshot["digest"])

    def test_pipeline_reuse_gate_honors_snapshot(self) -> None:
        # A06（后半）：终局复用门在快照不一致时拒绝复用。
        from research_agent.pipeline import _final_readiness_checkpoint_reusable

        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "09-revised-paper.md").write_text("# 修订稿\n内容A", encoding="utf-8")
            for name in (
                "10-revised-paper-review.json",
                "10-claim-traceability.json",
                "10-citation-grounding.json",
                "10-citation-coverage.json",
                "10-results-presentation.json",
                "10-claim-consistency.json",
                "10-submission-check.json",
                "10-final-readiness.json",
            ):
                (out / name).write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            snapshot = build_review_input_snapshot(
                out, revision=0, file_inputs={"09-revised-paper.md": "manuscript"}, inline_inputs={}
            )
            write_review_input_snapshot(out, snapshot)
            self.assertTrue(_final_readiness_checkpoint_reusable(out, {}, "local"))
            (out / "09-revised-paper.md").write_text("# 修订稿\n内容B（已改动）", encoding="utf-8")
            self.assertFalse(_final_readiness_checkpoint_reusable(out, {}, "local"))


if __name__ == "__main__":
    unittest.main()
