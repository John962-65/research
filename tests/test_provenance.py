from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.provenance import RunManifestRecorder, render_manifest_markdown


class ProvenanceTest(unittest.TestCase):
    def test_manifest_records_events_and_artifact_hashes(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "artifact.txt").write_text("hello\n", encoding="utf-8")
            recorder = RunManifestRecorder(out, "测试课题")
            recorder.record(
                "stage_one",
                inputs=["input.json"],
                outputs=["artifact.txt"],
                metrics={"count": 1},
            )

            data = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
            rendered = (out / "run-manifest.md").read_text(encoding="utf-8")

            self.assertEqual(data["topic"], "测试课题")
            self.assertEqual(data["events"][0]["stage"], "stage_one")
            self.assertIn("artifact.txt", rendered)
            self.assertTrue(any(item["path"] == "artifact.txt" and len(item["sha256"]) == 64 for item in data["artifacts"]))
            self.assertIn("Timeline", render_manifest_markdown(recorder.write()))


if __name__ == "__main__":
    unittest.main()
