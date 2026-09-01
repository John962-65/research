from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest

from research_agent.benchmark_adapter import audit_benchmark_adapter_config
from research_agent.benchmark_manifest_builder import build_benchmark_manifest_set
from research_agent.config import ExecutionConfig


class BenchmarkManifestBuilderTest(unittest.TestCase):
    def test_builder_writes_three_role_manifests_with_verified_hashes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "official-split.json"
            split.write_text('{"tasks":["task-001","task-002"]}\n', encoding="utf-8")
            grader = root / "grade.py"
            grader.write_text("print('grade')\n", encoding="utf-8")
            out_dir = root / "benchmarks" / "ompl"

            report = build_benchmark_manifest_set(
                out_dir=out_dir,
                name="ompl motion planning",
                benchmark_url="https://ompl.kavrakilab.org/benchmark.html",
                dataset_url="https://ompl.kavrakilab.org/benchmark.html",
                dataset_version="ompl-1.6.0",
                split_name="official split",
                split_file=split,
                grader_file=grader,
                grader_version="ompl-wrapper-v1",
                license_value="BSD-3-Clause",
                baseline="RRT*",
                baseline_version="ompl-1.6.0",
                citation="10.1109/MRA.2012.2205651",
                metrics=[
                    "success_rate:higher_is_better:ratio:Fraction solved.",
                    "planning_time:lower_is_better:seconds:Planning time.",
                ],
            )

            manifests = [out_dir / role / "manifest.json" for role in ["candidate", "baseline", "ablation"]]
            audit = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=[str(path) for path in manifests]),
                base_dir=root,
            )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(len(report["manifest_paths"]), 3)
        self.assertEqual(audit.status, "ready")
        self.assertEqual(audit.paper_grade_status, "ready")
        self.assertTrue(all(record.split_sha256_actual == record.split_sha256 for record in audit.adapters))
        self.assertTrue(all(record.grader_sha256_actual == record.grader_sha256 for record in audit.adapters))

    def test_builder_no_write_reports_manifest_preview_without_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.json"
            split.write_text("[]\n", encoding="utf-8")
            grader = root / "grade.py"
            grader.write_text("print('grade')\n", encoding="utf-8")
            out_dir = root / "drafts"

            report = build_benchmark_manifest_set(
                out_dir=out_dir,
                name="draft benchmark",
                benchmark_url="https://ompl.kavrakilab.org/benchmark.html",
                dataset_url="https://ompl.kavrakilab.org/benchmark.html",
                dataset_version="v1",
                split_name="split",
                split_file=split,
                grader_file=grader,
                grader_version="grader-v1",
                license_value="BSD-3-Clause",
                baseline="baseline",
                baseline_version="v1",
                citation="10.1109/MRA.2012.2205651",
                metrics=["score:higher_is_better:points:Primary score."],
                write=False,
            )

        self.assertEqual(report["status"], "ready")
        self.assertFalse(out_dir.exists())
        self.assertEqual({item["role"] for item in report["manifests"]}, {"candidate", "baseline", "ablation"})

    def test_builder_accepts_role_specific_command_overrides(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.json"
            split.write_text("[]\n", encoding="utf-8")
            grader = root / "grade.py"
            grader.write_text("print('grade')\n", encoding="utf-8")

            report = build_benchmark_manifest_set(
                out_dir=root / "drafts",
                name="role benchmark",
                benchmark_url="https://ompl.kavrakilab.org/benchmark.html",
                dataset_url="https://ompl.kavrakilab.org/benchmark.html",
                dataset_version="v1",
                split_name="split",
                split_file=split,
                grader_file=grader,
                grader_version="grader-v1",
                license_value="BSD-3-Clause",
                baseline="baseline",
                baseline_version="v1",
                citation="10.1109/MRA.2012.2205651",
                metrics=["score:higher_is_better:points:Primary score."],
                role_commands={
                    "candidate": "python3 {grader} --method ours --metrics {metrics_path}",
                    "baseline": "python3 {grader} --method baseline --metrics {metrics_path}",
                    "ablation": "python3 {grader} --method ablation --metrics {metrics_path}",
                },
                write=False,
            )

        commands = {item["role"]: item["manifest"]["command"] for item in report["manifests"]}
        self.assertEqual(report["status"], "ready")
        self.assertIn("ours", commands["candidate"])
        self.assertIn("baseline", commands["baseline"])
        self.assertIn("ablation", commands["ablation"])

    def test_cli_build_command_writes_report_and_manifests(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            split = root / "split.json"
            split.write_text('{"tasks":["a"]}\n', encoding="utf-8")
            grader = root / "grade.py"
            grader.write_text("print('grade')\n", encoding="utf-8")
            out_dir = root / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "benchmark-manifest-build",
                    "--out-dir",
                    str(out_dir),
                    "--name",
                    "ompl benchmark",
                    "--benchmark-url",
                    "https://ompl.kavrakilab.org/benchmark.html",
                    "--dataset-url",
                    "https://ompl.kavrakilab.org/benchmark.html",
                    "--dataset-version",
                    "ompl-1.6.0",
                    "--split-name",
                    "official split",
                    "--split-file",
                    str(split),
                    "--grader-file",
                    str(grader),
                    "--grader-version",
                    "grader-v1",
                    "--license",
                    "BSD-3-Clause",
                    "--baseline",
                    "RRT*",
                    "--baseline-version",
                    "ompl-1.6.0",
                    "--citation",
                    "10.1109/MRA.2012.2205651",
                    "--metric",
                    "success_rate:higher_is_better:ratio:Fraction solved.",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            candidate = json.loads((out_dir / "candidate" / "manifest.json").read_text(encoding="utf-8"))
            report_exists = (out_dir / "benchmark-manifest-build-report.json").exists()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Benchmark Manifest Builder", completed.stdout)
        self.assertTrue(report_exists)
        self.assertEqual(candidate["role"], "candidate")
        self.assertEqual(len(candidate["split_sha256"]), 64)
        self.assertEqual(len(candidate["grader_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
