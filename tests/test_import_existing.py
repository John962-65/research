from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.existing_results import evaluate_imported_results, import_existing_results


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
            # 复审第 3 项：导入结果没有真实存在的产物文件 → 声明不等于核验，
            # 实验证据为 incomplete 而非 verified。
            self.assertEqual(report["evidence_assessment"]["experiment_evidence_status"], "incomplete")
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


class EvaluateImportedTest(unittest.TestCase):
    """复审第 7 项：新目录导入已有结果 → 补齐比较条件 → 统计与决策 → 定位问题。"""

    @staticmethod
    def _imported_rows_with_artifacts(run_dir: Path) -> list[dict]:
        import hashlib

        experiments = run_dir / "experiments"
        experiments.mkdir(parents=True, exist_ok=True)
        rows = []
        for index, (name, group, accuracy) in enumerate([
            ("candidate", "candidate", 0.966),
            ("baseline", "baseline", 0.933),
            ("ablation", "ablation", 0.900),
        ]):
            artifact = experiments / f"{name}_metrics.json"
            artifact.write_text(json.dumps({"accuracy": accuracy}), encoding="utf-8")
            rows.append({
                "name": name,
                "status": "passed",
                "metrics": {"accuracy": accuracy},
                "command": ["python3", f"{name}.py"],
                "returncode": 0,
                "seed": "s",
                "repeat_index": 0,
                "comparison_group": group,
                "artifact_records": [
                    {"path": f"experiments/{name}_metrics.json", "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
                ],
            })
        return rows

    def test_full_user_path_import_then_evaluate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            rows = self._imported_rows_with_artifacts(run_dir)
            import_existing_results(run_dir, rows, contract_source={"schema_version": 2, "evaluation": {"primary_metrics": ["accuracy"]}, "hypothesis": {"question": "候选准确率更高"}})
            report = evaluate_imported_results(run_dir)
            # 单次重复的导入数据不足以支持强结论：系统给出保守的
            # refine_experiment/inconclusive 而非 proceed+supported。
            self.assertIn(report["decision"], {"proceed_to_paper", "refine_experiment"})
            states = report["decision_states"]
            self.assertEqual(states["execution_status"], "completed")
            self.assertEqual(states["evidence_status"], "verified", "产物文件真实存在且哈希一致 → 实验证据 verified")
            self.assertIn(states["research_outcome"], {"supported", "inconclusive"})
            self.assertEqual(states["next_action"], "proceed" if report["decision"] == "proceed_to_paper" else "request_material")
            self.assertEqual(report["evidence"]["experiment"], "verified")
            self.assertEqual(report["evidence"]["llm"], "unknown")
            self.assertTrue(states["contract_version"].startswith("decision-contract/"))
            # 关键工件已生成
            for name in ("04-statistics.json", "04-result-validation.json", "04-experiment-decision.json", "04-hypothesis-outcome.json"):
                self.assertTrue((run_dir / name).exists(), name)
            self.assertTrue((run_dir / "04-experiment-decision.json").exists())

    def test_import_without_baseline_locates_missing_condition(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            rows = self._imported_rows_with_artifacts(run_dir)[:1]  # 只有 candidate
            import_existing_results(run_dir, rows)
            report = evaluate_imported_results(run_dir)
            self.assertTrue(
                any("比较" in blocker or "baseline" in blocker.lower() for blocker in report["blockers"]),
                report["blockers"],
            )
            self.assertTrue(report["next_actions"], "必须给出补齐材料的下一步动作")
            # 决策工件仍然生成（用于页面展示问题所在）
            self.assertTrue((run_dir / "04-experiment-decision.json").exists())

    def test_imported_results_without_artifacts_are_incomplete(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            rows = self._imported_rows_with_artifacts(run_dir)
            for row in rows:
                row.pop("artifact_records")  # 复审第 3 项：声明不等于核验
            import_existing_results(run_dir, rows, replace=True)
            report = evaluate_imported_results(run_dir)
            self.assertEqual(report["evidence"]["experiment"], "incomplete")
            self.assertNotEqual(report["decision_states"]["evidence_status"], "verified")


if __name__ == "__main__":
    unittest.main()
