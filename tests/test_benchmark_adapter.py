from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import subprocess
import sys
import unittest

from research_agent.benchmark_adapter import BENCHMARK_ADAPTER_JSON, BENCHMARK_ADAPTER_MD, audit_benchmark_adapter_config
from research_agent.config import ExecutionConfig, PaperGradeConfig
from research_agent.experiments import run_experiments
from research_agent.models import ExperimentCommand, ExperimentPlan
from research_agent.statistics import build_statistics_report


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_formal_adapter_manifest(
    root: Path,
    role: str,
    *,
    benchmark_kind: str = "external",
    dataset_url: str = "https://ompl.kavrakilab.org/benchmark.html",
    min_repeats: int = 3,
) -> str:
    script = root / f"run_{role}.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    split = root / f"{role}_split.json"
    split.write_text(json.dumps({"role": role, "tasks": ["task-001", "task-002"]}, sort_keys=True), encoding="utf-8")
    manifest = root / f"{role}.json"
    manifest.write_text(
        json.dumps(
            {
                "name": f"{role} adapter",
                "role": role,
                "command": ["python3", script.name],
                "source_files": [script.name],
                "metrics_path": f"{role}_metrics.json",
                "expected_artifacts": [f"{role}_metrics.json"],
                "expected_metrics": ["success_rate", "planning_time"],
                "metric_schema": {
                    "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                    "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
                },
                "benchmark_kind": benchmark_kind,
                "benchmark_url": dataset_url,
                "dataset_url": dataset_url,
                "dataset_version": "ompl-1.6.0",
                "split_name": f"official-{role}-split",
                "split_path": split.name,
                "split_sha256": _sha256(split),
                "license": "BSD-3-Clause",
                "baseline": "RRT*",
                "baseline_version": f"ompl-1.6.0-{role}",
                "citation": "10.1109/MRA.2012.2205651",
                "grader": script.name,
                "grader_path": script.name,
                "grader_version": f"grader-{role}-v1",
                "grader_sha256": _sha256(script),
                "submission_path": f"{role}_submission.csv",
                "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat index.",
                "min_repeats": min_repeats,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(manifest)


class BenchmarkAdapterTest(unittest.TestCase):
    def test_rrt_2d_example_manifest_set_is_structural_fixture_not_formal_paper_grade(self) -> None:
        manifests = [
            ROOT / "examples" / "rrt-2d-benchmark" / "manifest-candidate.json",
            ROOT / "examples" / "rrt-2d-benchmark" / "manifest-baseline.json",
            ROOT / "examples" / "rrt-2d-benchmark" / "manifest-ablation.json",
        ]

        report = audit_benchmark_adapter_config(
            ExecutionConfig(
                mode="benchmark",
                allowed_commands=["python3"],
                repeats=3,
                benchmark_manifest_paths=[str(path) for path in manifests],
            ),
            base_dir=ROOT,
        )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "review_required")
        self.assertTrue(any("benchmark_kind=fixture" in issue for issue in report.paper_grade_issues))
        self.assertTrue(any("dataset_url" in issue and "procedural://" in issue for issue in report.paper_grade_issues))
        self.assertTrue(any(item.get("kind") == "external_benchmark_provenance" for item in report.paper_grade_repair_suggestions))
        self.assertEqual({record.role for record in report.adapters}, {"candidate", "baseline", "ablation"})
        self.assertTrue(all(record.min_repeats >= 3 for record in report.adapters))
        common = set.intersection(*(set(record.expected_metrics) for record in report.adapters))
        self.assertGreaterEqual(common, {"success_rate", "mean_iterations", "mean_path_length_solved"})

    def test_external_manifest_set_is_formal_paper_grade_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests: list[str] = []
            for role in ["candidate", "baseline", "ablation"]:
                script = root / f"run_{role}.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                split = root / f"{role}_split.json"
                split.write_text(json.dumps({"role": role, "tasks": ["task-001", "task-002"]}, sort_keys=True), encoding="utf-8")
                manifest = root / f"{role}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": f"{role} adapter",
                            "role": role,
                            "command": ["python3", script.name],
                            "source_files": [script.name],
                            "metrics_path": f"{role}_metrics.json",
                            "expected_artifacts": [f"{role}_metrics.json"],
                            "expected_metrics": ["success_rate", "planning_time"],
                            "metric_schema": {
                                "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                                "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
                            },
                            "benchmark_kind": "external",
                            "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_version": "ompl-1.6.0",
                            "split_name": f"official-{role}-split",
                            "split_path": split.name,
                            "split_sha256": _sha256(split),
                            "license": "BSD-3-Clause",
                            "baseline": "RRT*",
                            "baseline_version": f"ompl-1.6.0-{role}",
                            "citation": "10.1109/MRA.2012.2205651",
                            "grader": script.name,
                            "grader_path": script.name,
                            "grader_version": f"grader-{role}-v1",
                            "grader_sha256": _sha256(script),
                            "submission_path": f"{role}_submission.csv",
                            "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat index.",
                            "min_repeats": 3,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))

            report = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=manifests),
                base_dir=root,
            )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "ready")
        self.assertEqual(report.paper_grade_issues, [])
        self.assertTrue(all(record.provenance_status == "external" for record in report.adapters))
        self.assertTrue(all(record.split_sha256_actual == record.split_sha256 for record in report.adapters))
        self.assertTrue(all(record.grader_sha256_actual == record.grader_sha256 for record in report.adapters))

    def test_adapter_audit_uses_configured_paper_grade_repeats(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests: list[str] = []
            for role in ["candidate", "baseline", "ablation"]:
                script = root / f"run_{role}.py"
                script.write_text("print('ok')\n", encoding="utf-8")
                split = root / f"{role}_split.json"
                split.write_text(json.dumps({"role": role, "tasks": ["task-001", "task-002"]}, sort_keys=True), encoding="utf-8")
                manifest = root / f"{role}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": f"{role} adapter",
                            "role": role,
                            "command": ["python3", script.name],
                            "source_files": [script.name],
                            "metrics_path": f"{role}_metrics.json",
                            "expected_artifacts": [f"{role}_metrics.json"],
                            "expected_metrics": ["success_rate", "planning_time"],
                            "metric_schema": {
                                "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                                "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
                            },
                            "benchmark_kind": "external",
                            "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_version": "ompl-1.6.0",
                            "split_name": f"official-{role}-split",
                            "split_path": split.name,
                            "split_sha256": _sha256(split),
                            "license": "BSD-3-Clause",
                            "baseline": "RRT*",
                            "baseline_version": f"ompl-1.6.0-{role}",
                            "citation": "10.1109/MRA.2012.2205651",
                            "grader": script.name,
                            "grader_path": script.name,
                            "grader_version": f"grader-{role}-v1",
                            "grader_sha256": _sha256(script),
                            "submission_path": f"{role}_submission.csv",
                            "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat index.",
                            "min_repeats": 3,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))

            report = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=manifests),
                base_dir=root,
                paper_grade=PaperGradeConfig(enabled=True, min_execution_repeats=5),
            )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "review_required")
        issues = "\n".join(report.paper_grade_issues)
        self.assertIn("repeats >= 5", issues)
        self.assertIn("min_repeats 至少需要 5", issues)
        suggestion = next(item for item in report.paper_grade_repair_suggestions if item["kind"] == "increase_execution_repeats")
        self.assertEqual(suggestion["recommended_execution_config"]["execution_repeats"], 5)
        patches = [item for item in report.paper_grade_repair_suggestions if item["kind"] == "manifest_field_patch"]
        self.assertTrue(patches)
        self.assertTrue(all(item["field_patch"]["min_repeats"] == 5 for item in patches))

    def test_adapter_audit_checks_extra_ready_adapters_when_threshold_requires_them(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = [_write_formal_adapter_manifest(root, role) for role in ["candidate", "baseline", "ablation"]]
            manifests.append(
                _write_formal_adapter_manifest(
                    root,
                    "other",
                    benchmark_kind="fixture",
                    dataset_url="procedural://toy-extra",
                )
            )

            report = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=manifests),
                base_dir=root,
                paper_grade=PaperGradeConfig(enabled=True, min_benchmark_roles=4),
            )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "review_required")
        self.assertTrue(any("benchmark_kind=fixture" in issue for issue in report.paper_grade_issues))
        self.assertTrue(any(item.get("kind") == "external_benchmark_provenance" and item.get("role") == "other" for item in report.paper_grade_repair_suggestions))

    def test_manifest_local_hash_mismatch_blocks_formal_paper_grade(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "run_candidate.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            split = root / "split.json"
            split.write_text('{"tasks":["task-001"]}\n', encoding="utf-8")
            manifest = root / "candidate.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "candidate adapter",
                        "role": "candidate",
                        "command": ["python3", script.name],
                        "source_files": [script.name],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                        "expected_metrics": ["success_rate"],
                        "metric_schema": {
                            "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."}
                        },
                        "benchmark_kind": "external",
                        "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                        "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                        "dataset_version": "ompl-1.6.0",
                        "split_name": "official-candidate-split",
                        "split_path": split.name,
                        "split_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "license": "BSD-3-Clause",
                        "baseline": "RRT*",
                        "baseline_version": "ompl-1.6.0",
                        "citation": "10.1109/MRA.2012.2205651",
                        "grader": script.name,
                        "grader_path": script.name,
                        "grader_version": "grader-candidate-v1",
                        "grader_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "submission_path": "candidate_submission.csv",
                        "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat index.",
                        "min_repeats": 3,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=[str(manifest)]),
                base_dir=root,
            )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "review_required")
        self.assertTrue(any("split_sha256 与 split_path" in issue for issue in report.paper_grade_issues))
        self.assertTrue(any("grader_sha256 与 grader_path" in issue for issue in report.paper_grade_issues))

    def test_paper_grade_requires_role_commands_to_differ_beyond_output_path(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "grade.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            split = root / "split.json"
            split.write_text('{"tasks":["task-001"]}\n', encoding="utf-8")
            manifests: list[str] = []
            for role in ["candidate", "baseline", "ablation"]:
                manifest = root / f"{role}.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": f"{role} adapter",
                            "role": role,
                            "command": ["python3", script.name, "--metrics", f"{role}_metrics.json"],
                            "source_files": [script.name],
                            "metrics_path": f"{role}_metrics.json",
                            "expected_artifacts": [f"{role}_metrics.json"],
                            "expected_metrics": ["success_rate"],
                            "metric_schema": {
                                "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."}
                            },
                            "benchmark_kind": "external",
                            "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_version": "ompl-1.6.0",
                            "split_name": "official split",
                            "split_path": split.name,
                            "split_sha256": _sha256(split),
                            "license": "BSD-3-Clause",
                            "baseline": "RRT*",
                            "baseline_version": "ompl-1.6.0",
                            "citation": "10.1109/MRA.2012.2205651",
                            "grader": script.name,
                            "grader_path": script.name,
                            "grader_version": "grader-v1",
                            "grader_sha256": _sha256(script),
                            "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat index.",
                            "min_repeats": 3,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))

            report = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=manifests),
                base_dir=root,
            )

        self.assertEqual(report.status, "ready")
        self.assertEqual(report.paper_grade_status, "review_required")
        self.assertTrue(any("重复 role command" in issue for issue in report.paper_grade_issues))
        self.assertTrue(any(item.get("kind") == "differentiate_role_commands" for item in report.paper_grade_repair_suggestions))

    def test_rrt_2d_role_runner_emits_common_metrics(self) -> None:
        with TemporaryDirectory() as tmp:
            metrics = Path(tmp) / "metrics.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "examples" / "rrt-2d-benchmark" / "run_benchmark.py"),
                    "--variant",
                    "greedy",
                    "--metrics",
                    str(metrics),
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            data = json.loads(metrics.read_text(encoding="utf-8"))

        self.assertIn("success_rate", data)
        self.assertIn("mean_iterations", data)
        self.assertIn("mean_path_length_solved", data)

    def test_benchmark_mode_runs_manifest_adapter_and_reads_metrics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter_dir = root / "adapter"
            adapter_dir.mkdir()
            script = adapter_dir / "run_benchmark.py"
            script.write_text(
                "\n".join(
                    [
                        "import argparse, json",
                        "parser = argparse.ArgumentParser()",
                        "parser.add_argument('--metrics', required=True)",
                        "args = parser.parse_args()",
                        "with open(args.metrics, 'w', encoding='utf-8') as handle:",
                        "    json.dump({'success_rate': 0.91, 'runtime_cost': 1.7}, handle)",
                    ]
                ),
                encoding="utf-8",
            )
            manifest = adapter_dir / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "Toy Benchmark",
                        "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                        "benchmark_url": "https://example.org/toy-benchmark",
                        "dataset_url": "https://example.org/toy-data",
                        "license": "CC-BY-4.0",
                        "baseline": "toy-baseline",
                        "baseline_version": "v1",
                        "citation": "10.1000/toy",
                        "expected_metrics": ["success_rate", "runtime_cost"],
                        "grader": "run_benchmark.py",
                        "submission_path": "submission.csv",
                        "seed_policy": "RESEARCH_AGENT_SEED fixes toy task sampling",
                        "min_repeats": 1,
                        "notes": ["确认 toy benchmark 仅用于 adapter smoke。"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            run_dir = root / "run"
            plan = ExperimentPlan(
                idea_title="benchmark adapter",
                objective="验证 benchmark manifest 可以接入本地任务。",
                variables=["adapter"],
                metrics=["success_rate", "runtime_cost"],
                protocol=["运行 adapter"],
                commands=[],
            )

            results = run_experiments(
                plan,
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=1, benchmark_manifest_paths=[str(manifest)]),
                run_dir,
                base_dir=root,
            )
            report = json.loads((run_dir / BENCHMARK_ADAPTER_JSON).read_text(encoding="utf-8"))
            runbook = json.loads((run_dir / "04-experiment-runbook.json").read_text(encoding="utf-8"))

            self.assertEqual(results[0].status, "passed")
            self.assertEqual(results[0].metrics["success_rate"], 0.91)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["paper_grade_status"], "review_required")
            suggestions = report["paper_grade_repair_suggestions"]
            suggested_roles = {item.get("role") for item in suggestions if item.get("kind") == "missing_manifest_role"}
            self.assertEqual(suggested_roles, {"candidate", "baseline", "ablation"})
            self.assertTrue(any(item.get("kind") == "increase_execution_repeats" for item in suggestions))
            candidate_template = next(item["manifest_template"] for item in suggestions if item.get("role") == "candidate")
            self.assertEqual(candidate_template["role"], "candidate")
            self.assertEqual(candidate_template["min_repeats"], 3)
            self.assertEqual(report["adapters"][0]["dataset_url"], "https://example.org/toy-data")
            self.assertEqual(report["adapters"][0]["expected_metrics"], ["success_rate", "runtime_cost"])
            self.assertEqual(report["adapters"][0]["grader"], "benchmark-adapters/toy-benchmark/run_benchmark.py")
            self.assertEqual(report["adapters"][0]["submission_path"], "benchmark-adapters/toy-benchmark/submission.csv")
            self.assertEqual(report["adapters"][0]["seed_policy"], "RESEARCH_AGENT_SEED fixes toy task sampling")
            self.assertEqual(report["adapters"][0]["min_repeats"], 1)
            self.assertEqual(report["commands"][0]["baseline_version"], "v1")
            self.assertEqual(report["commands"][0]["expected_metrics"], ["success_rate", "runtime_cost"])
            self.assertTrue((run_dir / BENCHMARK_ADAPTER_MD).exists())
            self.assertTrue((run_dir / "experiments" / "benchmark-adapters" / "toy-benchmark" / "run_benchmark.py").exists())
            self.assertEqual(runbook["execution"]["mode"], "benchmark")
            self.assertTrue(any(item["path"].endswith("metrics.json") for item in runbook["artifacts"]))
            produced = runbook["runs"][0]["produced_artifacts"]
            metrics_record = next(
                item
                for item in produced
                if item["path"] == "experiments/benchmark-adapters/toy-benchmark/metrics.json"
            )
            self.assertEqual(metrics_record["bytes"], len('{"success_rate": 0.91, "runtime_cost": 1.7}'))
            self.assertEqual(len(metrics_record["sha256"]), 64)

    def test_manifest_roles_drive_paper_grade_statistics(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = []
            for role, value in [("candidate", 0.9), ("baseline", 0.7), ("ablation", 0.8)]:
                adapter_dir = root / role
                adapter_dir.mkdir()
                script = adapter_dir / "run_benchmark.py"
                script.write_text(
                    "\n".join(
                        [
                            "import argparse, json",
                            "parser = argparse.ArgumentParser()",
                            "parser.add_argument('--variant', required=True)",
                            "parser.add_argument('--metrics', required=True)",
                            "args = parser.parse_args()",
                            f"json.dump({{'success_rate': {value}, 'runtime_cost': 1.0}}, open(args.metrics, 'w', encoding='utf-8'))",
                        ]
                    ),
                    encoding="utf-8",
                )
                manifest = adapter_dir / "manifest.json"
                manifest.write_text(
                    json.dumps(
                        {
                            "name": "shared benchmark",
                            "role": role,
                            "command": ["python3", "run_benchmark.py", "--variant", role, "--metrics", "metrics.json"],
                            "metrics_path": "metrics.json",
                            "expected_artifacts": ["metrics.json"],
                            "benchmark_kind": "external",
                            "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                            "dataset_version": "ompl-1.6.0",
                            "split_name": "shared official split",
                            "split_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                            "license": "CC-BY-4.0",
                            "baseline": "control",
                            "baseline_version": "v1",
                            "citation": "10.1109/MRA.2012.2205651",
                            "expected_metrics": ["success_rate", "runtime_cost"],
                            "metric_schema": {
                                "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                                "runtime_cost": {"direction": "lower_is_better", "unit": "seconds", "description": "Runtime cost."},
                            },
                            "grader": "run_benchmark.py",
                            "grader_version": "shared-grader-v1",
                            "grader_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                            "submission_path": "submission.csv",
                            "seed_policy": "RESEARCH_AGENT_SEED fixes split",
                            "min_repeats": 3,
                        }
                    ),
                    encoding="utf-8",
                )
                manifests.append(str(manifest))

            plan = ExperimentPlan(
                idea_title="role benchmark",
                objective="role-based benchmark stats",
                variables=["role"],
                metrics=["success_rate", "runtime_cost"],
                protocol=["run adapters"],
                commands=[],
            )
            run_dir = root / "run"
            results = run_experiments(
                plan,
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=manifests),
                run_dir,
                base_dir=root,
            )
            report = json.loads((run_dir / BENCHMARK_ADAPTER_JSON).read_text(encoding="utf-8"))
            runbook = json.loads((run_dir / "04-experiment-runbook.json").read_text(encoding="utf-8"))
            statistics = build_statistics_report(
                ExperimentPlan(
                    idea_title=plan.idea_title,
                    objective=plan.objective,
                    variables=plan.variables,
                    metrics=plan.metrics,
                    protocol=plan.protocol,
                    commands=[
                        # Rehydrate from runbook to prove role survives persisted artifacts.
                        ExperimentCommand(
                            name=item["name"],
                            command=item["command"],
                            expected_artifacts=item["expected_artifacts"],
                            role=item["role"],
                        )
                        for item in runbook["commands"]
                    ],
                ),
                results,
            )

            self.assertEqual(report["paper_grade_status"], "ready")
            self.assertEqual(report["paper_grade_repair_suggestions"], [])
            self.assertEqual({item["role"] for item in report["commands"]}, {"candidate", "baseline", "ablation"})
            self.assertTrue(all(item["name"].startswith(item["role"]) for item in report["commands"]))
            self.assertEqual({item["role"] for item in runbook["commands"]}, {"candidate", "baseline", "ablation"})
            self.assertEqual(statistics.candidate_name, "candidate-shared-benchmark")
            self.assertEqual(statistics.baseline_name, "baseline-shared-benchmark")
            self.assertTrue(any(item.metric == "success_rate" for item in statistics.comparisons))

    def test_benchmark_mode_requires_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            plan = ExperimentPlan(
                idea_title="missing manifest",
                objective="验证缺失 manifest 会失败。",
                variables=["adapter"],
                metrics=["success_rate"],
                protocol=["运行 adapter"],
                commands=[],
            )

            with self.assertRaises(ValueError):
                run_experiments(plan, ExecutionConfig(mode="benchmark", allowed_commands=["python3"]), run_dir)
            self.assertTrue((run_dir / BENCHMARK_ADAPTER_JSON).exists())

    def test_benchmark_adapter_audit_has_no_side_effects_and_checks_whitelist(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter_dir = root / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "run_benchmark.py").write_text("print('ok')\n", encoding="utf-8")
            manifest = adapter_dir / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "Audit Benchmark",
                        "command": ["python3", "run_benchmark.py", "--metrics", "metrics.json"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                        "expected_metrics": ["success_rate"],
                        "grader": "run_benchmark.py",
                        "submission_path": "submission.csv",
                        "seed_policy": "RESEARCH_AGENT_SEED fixed",
                        "min_repeats": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            ready = audit_benchmark_adapter_config(ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]), base_dir=root)
            blocked = audit_benchmark_adapter_config(ExecutionConfig(mode="benchmark", allowed_commands=["pytest"], benchmark_manifest_paths=[str(manifest)]), base_dir=root)

            self.assertEqual(ready.status, "ready")
            self.assertEqual(blocked.status, "blocked")
            self.assertTrue(any("allowed_commands" in issue for issue in blocked.blocking_issues))
            self.assertFalse((Path.cwd() / "experiments" / "benchmark-adapters" / "audit-benchmark").exists())

    def test_benchmark_adapter_audit_detects_missing_source_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "Missing Source",
                        "command": ["python3", "missing.py"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = audit_benchmark_adapter_config(ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]), base_dir=root)

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("source file 缺失" in issue for issue in report.blocking_issues))

    def test_manifest_outside_config_root_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            outer = Path(tmp)
            root = outer / "configured-root"
            root.mkdir()
            script = outer / "outside.py"
            script.write_text("print('outside')\n", encoding="utf-8")
            manifest = outer / "manifest.json"
            manifest.write_text(
                json.dumps({"name": "outside", "command": ["python3", script.name], "metrics_path": "metrics.json"}),
                encoding="utf-8",
            )

            report = audit_benchmark_adapter_config(
                ExecutionConfig(mode="benchmark", benchmark_manifest_paths=[str(manifest)]),
                base_dir=root,
            )

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("路径不安全" in issue for issue in report.blocking_issues))

    def test_symlinked_source_is_rejected_and_not_copied(self) -> None:
        with TemporaryDirectory() as tmp:
            outer = Path(tmp)
            root = outer / "configured-root"
            root.mkdir()
            outside = outer / "outside.py"
            outside.write_text("print('outside')\n", encoding="utf-8")
            (root / "linked.py").symlink_to(outside)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "symlink escape",
                        "command": ["python3", "linked.py"],
                        "source_files": ["linked.py"],
                        "metrics_path": "metrics.json",
                        "expected_artifacts": ["metrics.json"],
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "run"
            plan = ExperimentPlan("symlink", "reject", ["path"], ["score"], ["run"], [])

            with self.assertRaisesRegex(ValueError, "路径不安全"):
                run_experiments(
                    plan,
                    ExecutionConfig(mode="benchmark", benchmark_manifest_paths=[manifest.name]),
                    run_dir,
                    base_dir=root,
                )

            self.assertFalse((run_dir / "experiments" / "benchmark-adapters" / "symlink-escape" / "linked.py").exists())


if __name__ == "__main__":
    unittest.main()
