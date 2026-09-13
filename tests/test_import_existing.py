from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.existing_results import import_existing_results


RESULTS = [
    {
        "name": "candidate",
        "status": "passed",
        "metrics": {"accuracy": 0.966},
        "command": ["python3", "run_candidate.py"],
        "returncode": 0,
        "seed": "abc",
        "repeat_index": 0,
        "artifact_records": [{"path": "experiments/candidate_metrics.json", "bytes": 10, "sha256": "a" * 64}],
    },
    {
        "name": "baseline",
        "status": "failed",
        "metrics": {},
        "command": ["python3", "run_baseline.py"],
        "returncode": 2,
        "repeat_index": 0,
    },
]


class ImportExistingTest(unittest.TestCase):
    def test_import_creates_report_with_mapping_and_missing_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            report = import_existing_results(run_dir, RESULTS, notes="本地 UCI 实验")
            paths = [item["path"] for item in report["imported_files"]]
            self.assertIn("04-results.json", paths)
            self.assertTrue((run_dir / "04-results.json").exists())
            mapping = {item["name"]: item for item in report["field_mapping"]}
            self.assertEqual(mapping["candidate"]["execution_status"], "completed")
            self.assertTrue(mapping["candidate"]["usable_as_evidence"])
            self.assertEqual(mapping["baseline"]["execution_status"], "failed")
            self.assertFalse(mapping["baseline"]["usable_as_evidence"])
            # 缺失项如实列出，不补成已验证。
            self.assertTrue(any("metrics" in item for item in report["missing_fields"]))
            self.assertEqual(report["result_summary"]["status_counts"], {"passed": 1, "failed": 1})
            # candidate 行指标与来源绑定齐全 → 实验证据 verified；
            # baseline 失败行保留为执行尝试，不影响 verified 判定。
            self.assertEqual(report["evidence_assessment"]["experiment_evidence_status"], "verified")
            self.assertIn("unknown", report["evidence_assessment"]["llm_evidence_status"])

    def test_import_writes_file_source_and_does_not_overwrite_without_flag(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            source = Path(tmp) / "my-results.json"
            source.write_text(json.dumps(RESULTS), encoding="utf-8")
            first = import_existing_results(run_dir, source)
            self.assertTrue((run_dir / "04-results.json").exists())
            second = import_existing_results(run_dir, source)
            self.assertTrue(any("未写入新结果" in w for w in second["warnings"]))
            forced = import_existing_results(run_dir, source, replace=True)
            replaced = [item for item in forced["imported_files"] if item["path"] == "04-results.json"]
            self.assertEqual(replaced[0]["action"], "replaced")
            self.assertEqual(replaced[0]["source_sha256"], first["imported_files"][0]["source_sha256"])

    def test_inline_contract_import_and_missing_contract_notice(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            report = import_existing_results(
                run_dir, RESULTS,
                contract_source={"schema_version": 2, "contract_id": "contract-x"},
            )
            paths = [item["path"] for item in report["imported_files"]]
            self.assertIn("03-idea-experiment-contract.json", paths)
            self.assertTrue(any("preregistration: 未提供" in item for item in report["missing_fields"]))
            self.assertTrue((run_dir / "03-idea-experiment-contract.json").exists())


if __name__ == "__main__":
    unittest.main()
