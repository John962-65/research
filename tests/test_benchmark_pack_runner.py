from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.benchmark_pack_runner import run_benchmark_pack


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "benchmarks" / "uci-iris-classification"


class BenchmarkPackRunnerTest(unittest.TestCase):
    def test_runs_uci_iris_pack_and_writes_standard_artifacts(self) -> None:
        manifests = [
            BENCHMARK_DIR / "manifest-candidate.json",
            BENCHMARK_DIR / "manifest-baseline.json",
            BENCHMARK_DIR / "manifest-ablation.json",
            BENCHMARK_DIR / "manifest-reference-majority.json",
            BENCHMARK_DIR / "manifest-reference-dummy-stratified.json",
            BENCHMARK_DIR / "manifest-reference-gaussian-nb.json",
            BENCHMARK_DIR / "manifest-reference-decision-tree.json",
            BENCHMARK_DIR / "manifest-reference-linear-logistic.json",
        ]
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "uci-iris-run"

            report = run_benchmark_pack(
                topic="Iris classification benchmark pack execution",
                manifest_paths=[str(path) for path in manifests],
                out_dir=out_dir,
                repeats=3,
                allowed_commands=["python3"],
            )

            self.assertEqual(report["status"], "warn")
            self.assertEqual(report["execution_mode"], "benchmark")
            self.assertEqual(report["results"], 24)
            self.assertEqual(report["comparisons"], 3)
            self.assertEqual(report["benchmark_evidence_grade"], "real_benchmark")
            self.assertEqual(report["statistical_outcome"], "neutral_no_observed_difference")
            self.assertEqual(report["claim_boundary_severity"], "negative_or_neutral_no_superiority")
            self.assertTrue(report["publishable_negative_or_neutral_result"])
            self.assertEqual(report["claim_policy"], "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims")
            self.assertEqual(report["statistical_design"]["status"], "pass")
            self.assertEqual(report["statistical_design"]["multiplicity_status"], "pass")
            self.assertEqual(report["statistical_design"]["power_status"], "profile_ready")
            self.assertEqual(report["statistical_design"]["family_size"], 3)
            self.assertIn("minimum_detectable_standardized_effect", report["statistical_design"])
            for name in [
                "03-benchmark-adapters.json",
                "03-execution-safety-audit.json",
                "03-benchmark-plan.json",
                "03-benchmark-plan.md",
                "03-preregistration.json",
                "03-preregistration.md",
                "04-results.json",
                "04-results.csv",
                "04-experiment-runbook.json",
                "04-environment-snapshot.json",
                "04-statistics.json",
                "04-statistics-figure.svg",
                "04-result-validation.json",
                "04-benchmark-result-schema-audit.json",
                "04-benchmark-evidence-audit.json",
                "04-benchmark-pack-run.json",
            ]:
                self.assertTrue((out_dir / name).exists(), name)

            statistics = json.loads((out_dir / "04-statistics.json").read_text(encoding="utf-8"))
            self.assertEqual(statistics["repeats"], 3)
            self.assertFalse(statistics["warnings"])
            self.assertEqual(statistics["multiplicity"]["family_size"], 3)
            self.assertEqual(statistics["power_analysis"]["status"], "profile_ready")
            self.assertEqual(statistics["baseline_name"], "baseline-uci-iris-3-nearest-neighbor-baseline")
            self.assertEqual({item["metric"] for item in statistics["comparisons"]}, {"accuracy", "macro_f1", "error_rate"})
            accuracy = next(item for item in statistics["comparisons"] if item["metric"] == "accuracy")
            self.assertEqual(accuracy["candidate_mean"], accuracy["baseline_mean"])
            preregistration = json.loads((out_dir / "03-preregistration.json").read_text(encoding="utf-8"))
            self.assertEqual(preregistration["status"], "locked")
            self.assertEqual(preregistration["timing"], "before_results")
            self.assertEqual(set(preregistration["primary_metrics"]), {"accuracy", "macro_f1"})
            validation = json.loads((out_dir / "04-result-validation.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["preregistration_status"], "locked")
            preregistration_item = next(item for item in validation["items"] if item["name"] == "preregistration")
            self.assertEqual(preregistration_item["status"], "pass")
            self.assertFalse(any("缺少 03-preregistration" in item for item in validation["warnings"]))
            benchmark_plan = json.loads((out_dir / "03-benchmark-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(benchmark_plan["selected_names"], ["UCI Iris dataset manifest pack"])
            self.assertEqual(benchmark_plan["required_actions"], [])
            evidence = json.loads((out_dir / "04-benchmark-evidence-audit.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["benchmark_plan_selected"], ["UCI Iris dataset manifest pack"])
            self.assertEqual(evidence["statistical_outcome"], "neutral_no_observed_difference")
            self.assertTrue(evidence["publishable_negative_or_neutral_result"])
            self.assertFalse(any("03-benchmark-plan 未选择" in item for item in evidence["manual_tasks"]))
            rendered = (out_dir / "04-benchmark-pack-run.md").read_text(encoding="utf-8")
            self.assertIn("Statistical Design", rendered)
            self.assertIn("Power/sensitivity", rendered)

            results = json.loads((out_dir / "04-results.json").read_text(encoding="utf-8"))
            self.assertEqual({item["status"] for item in results}, {"passed"})
            self.assertEqual({item["repeat_index"] for item in results}, {0, 1, 2})
            self.assertTrue(any(item["name"] == "baseline-uci-iris-3-nearest-neighbor-baseline" for item in results))
            self.assertTrue(any(item["name"] == "uci-iris-majority-class-reference-baseline" for item in results))
            self.assertTrue(any(item["name"] == "uci-iris-dummy-stratified-reference-baseline" for item in results))
            self.assertTrue(any(item["name"] == "uci-iris-gaussian-naive-bayes-reference-baseline" for item in results))
            self.assertTrue(any(item["name"] == "uci-iris-decision-tree-reference-baseline" for item in results))
            self.assertTrue(any(item["name"] == "uci-iris-linear-logistic-reference-baseline" for item in results))
            ablation = next(item for item in results if item["name"] == "ablation-uci-iris-sepal-centroid-ablation")
            self.assertLess(ablation["metrics"]["accuracy"], accuracy["candidate_mean"])
            majority = next(item for item in results if item["name"] == "uci-iris-majority-class-reference-baseline")
            self.assertLess(majority["metrics"]["accuracy"], accuracy["candidate_mean"])
            gaussian_nb = next(item for item in results if item["name"] == "uci-iris-gaussian-naive-bayes-reference-baseline")
            self.assertLess(gaussian_nb["metrics"]["accuracy"], accuracy["candidate_mean"])

            baseline_metrics = json.loads((out_dir / "experiments" / "benchmark-adapters" / "baseline-uci-iris-3-nearest-neighbor-baseline" / "baseline_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(baseline_metrics["method"], "knn3")
            self.assertIn("confusion_matrix", baseline_metrics)
            self.assertIn("prediction_sha256", baseline_metrics)
            self.assertIn("precision_setosa", baseline_metrics)
            self.assertIn("train_class_count_setosa", baseline_metrics)
            self.assertIn("cm_setosa_setosa", baseline_metrics)
            self.assertIn("cm_setosa_setosa", next(item for item in results if item["name"] == "baseline-uci-iris-3-nearest-neighbor-baseline")["metrics"])
            majority_metrics = json.loads((out_dir / "experiments" / "benchmark-adapters" / "uci-iris-majority-class-reference-baseline" / "majority_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(majority_metrics["method"], "majority_class")
            dummy_metrics = json.loads((out_dir / "experiments" / "benchmark-adapters" / "uci-iris-dummy-stratified-reference-baseline" / "dummy_stratified_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(dummy_metrics["method"], "dummy_stratified")
            tree_metrics = json.loads((out_dir / "experiments" / "benchmark-adapters" / "uci-iris-decision-tree-reference-baseline" / "decision_tree_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(tree_metrics["method"], "decision_tree")
            logistic_metrics = json.loads((out_dir / "experiments" / "benchmark-adapters" / "uci-iris-linear-logistic-reference-baseline" / "linear_logistic_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(logistic_metrics["method"], "linear_logistic")


if __name__ == "__main__":
    unittest.main()
