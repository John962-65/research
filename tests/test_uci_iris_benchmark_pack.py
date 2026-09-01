from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

from research_agent.benchmark_adapter import audit_benchmark_adapter_config
from research_agent.config import ExecutionConfig


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "benchmarks" / "uci-iris-classification"
PRIMARY_MANIFESTS = [
    BENCHMARK_DIR / "manifest-candidate.json",
    BENCHMARK_DIR / "manifest-baseline.json",
    BENCHMARK_DIR / "manifest-ablation.json",
]
REFERENCE_MANIFESTS = [
    BENCHMARK_DIR / "manifest-reference-majority.json",
    BENCHMARK_DIR / "manifest-reference-dummy-stratified.json",
    BENCHMARK_DIR / "manifest-reference-gaussian-nb.json",
    BENCHMARK_DIR / "manifest-reference-decision-tree.json",
    BENCHMARK_DIR / "manifest-reference-linear-logistic.json",
]


class UciIrisBenchmarkPackTest(unittest.TestCase):
    def test_readme_documents_primary_role_parameter_mapping(self) -> None:
        readme = (BENCHMARK_DIR / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Primary Role Parameter Mapping", readme)
        for manifest_path in PRIMARY_MANIFESTS:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            command = manifest["command"]
            method = command[command.index("--method") + 1]
            role = manifest["role"]
            metrics_path = manifest["metrics_path"]

            self.assertIn(f"| `{role}` | `{manifest_path.name}` | `--method {method}` |", readme)
            self.assertIn(f"`{metrics_path}`", readme)

        self.assertIn("same frozen dataset, stratified split, grader, metric schema", readme)
        self.assertIn("neutral/no-superiority claim boundaries", readme)

    def test_uci_iris_manifest_set_is_paper_grade_ready(self) -> None:
        report = audit_benchmark_adapter_config(
            ExecutionConfig(
                mode="benchmark",
                allowed_commands=["python3"],
                repeats=3,
                benchmark_manifest_paths=[str(path) for path in PRIMARY_MANIFESTS],
            ),
            base_dir=ROOT,
        )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "ready")
        self.assertEqual({record.role for record in report.adapters}, {"candidate", "baseline", "ablation"})
        self.assertFalse(report.paper_grade_issues)

    def test_uci_iris_reference_manifest_set_is_paper_grade_ready(self) -> None:
        report = audit_benchmark_adapter_config(
            ExecutionConfig(
                mode="benchmark",
                allowed_commands=["python3"],
                repeats=3,
                benchmark_manifest_paths=[str(path) for path in [*PRIMARY_MANIFESTS, *REFERENCE_MANIFESTS]],
            ),
            base_dir=ROOT,
        )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "ready")
        self.assertEqual(len(report.adapters), 8)
        self.assertEqual({record.role for record in report.adapters}, {"candidate", "baseline", "ablation", "other"})
        self.assertFalse(report.paper_grade_issues)

    def test_uci_iris_grader_methods_produce_distinct_metrics(self) -> None:
        data_path = BENCHMARK_DIR / "data" / "iris.data"
        split_path = BENCHMARK_DIR / "split" / "iris-stratified-test-v1.json"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics: dict[str, dict[str, object]] = {}
            methods = [
                "nearest_centroid",
                "knn3",
                "majority_class",
                "dummy_stratified",
                "gaussian_nb",
                "decision_tree",
                "linear_logistic",
                "sepal_centroid",
            ]
            for method in methods:
                out = root / f"{method}.json"
                subprocess.run(
                    [
                        sys.executable,
                        str(BENCHMARK_DIR / "grade_iris.py"),
                        "--method",
                        method,
                        "--data",
                        str(data_path),
                        "--split",
                        str(split_path),
                        "--metrics",
                        str(out),
                    ],
                    check=True,
                )
                metrics[method] = json.loads(out.read_text(encoding="utf-8"))

        self.assertTrue(all(item["test_cases"] == 30 for item in metrics.values()))
        self.assertTrue(all(item["train_cases"] == 120 for item in metrics.values()))
        self.assertEqual(metrics["dummy_stratified"]["method"], "dummy_stratified")
        self.assertEqual(metrics["gaussian_nb"]["method"], "gaussian_nb")
        self.assertEqual(metrics["decision_tree"]["method"], "decision_tree")
        self.assertEqual(metrics["linear_logistic"]["method"], "linear_logistic")
        self.assertAlmostEqual(float(metrics["nearest_centroid"]["accuracy"]), float(metrics["knn3"]["accuracy"]))
        self.assertAlmostEqual(float(metrics["gaussian_nb"]["accuracy"]), float(metrics["linear_logistic"]["accuracy"]))
        self.assertGreater(metrics["nearest_centroid"]["accuracy"], metrics["sepal_centroid"]["accuracy"])
        self.assertGreater(metrics["gaussian_nb"]["accuracy"], metrics["decision_tree"]["accuracy"])
        self.assertGreater(metrics["sepal_centroid"]["accuracy"], metrics["majority_class"]["accuracy"])
        self.assertGreater(metrics["dummy_stratified"]["accuracy"], metrics["majority_class"]["accuracy"])


if __name__ == "__main__":
    unittest.main()
