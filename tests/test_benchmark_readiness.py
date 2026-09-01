from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.benchmark_plan import build_benchmark_plan
from research_agent.benchmark_readiness import (
    BENCHMARK_READINESS_JSON,
    BENCHMARK_READINESS_MD,
    build_benchmark_readiness_report,
    render_benchmark_readiness_markdown,
    write_benchmark_readiness_artifacts,
)
from research_agent.config import ExecutionConfig
from research_agent.models import ExperimentCommand, ExperimentPlan, ResearchPlan


class BenchmarkReadinessTest(unittest.TestCase):
    def test_benchmark_readiness_passes_with_ready_manifest_adapter(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            report = build_benchmark_readiness_report(
                _research_plan(),
                _experiment_plan(),
                build_benchmark_plan(_research_plan(), _experiment_plan()),
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]),
                base_dir=root,
            )
            rendered = render_benchmark_readiness_markdown(report)

            self.assertEqual(report["status"], "ready_for_benchmark")
            self.assertEqual(report["adapter_report"]["status"], "ready")
            self.assertFalse(report["blocking_issues"])
            self.assertIn("Benchmark Readiness Audit", rendered)
            self.assertIn("Adapter Dry Run", rendered)

    def test_benchmark_readiness_blocks_missing_benchmark_manifest(self) -> None:
        report = build_benchmark_readiness_report(
            _research_plan(),
            _experiment_plan(),
            build_benchmark_plan(_research_plan(), _experiment_plan()),
            ExecutionConfig(mode="benchmark", allowed_commands=["python3"]),
        )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("manifest" in issue for issue in report["blocking_issues"]))
        self.assertTrue(any(check["name"] == "execution_mode" and check["status"] == "block" for check in report["checks"]))

    def test_benchmark_readiness_blocks_missing_manifest_provenance(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root, include_provenance=False)
            report = build_benchmark_readiness_report(
                _research_plan(),
                _experiment_plan(),
                build_benchmark_plan(_research_plan(), _experiment_plan()),
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]),
                base_dir=root,
            )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any(check["name"] == "manifest_provenance" and check["status"] == "block" for check in report["checks"]))
        self.assertTrue(any("baseline_version" in issue for issue in report["blocking_issues"]))

    def test_benchmark_readiness_blocks_role_commands_that_only_change_outputs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = _write_manifest_role_set(root, include_variant=False)
            report = build_benchmark_readiness_report(
                _research_plan(),
                _experiment_plan(),
                build_benchmark_plan(_research_plan(), _experiment_plan()),
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], repeats=3, benchmark_manifest_paths=manifests),
                base_dir=root,
            )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any(check["name"] == "manifest_role_commands" and check["status"] == "block" for check in report["checks"]))
        self.assertTrue(any("重复 role command" in issue for issue in report["blocking_issues"]))

    def test_benchmark_readiness_warns_when_simulated_cannot_support_benchmark_claims(self) -> None:
        report = build_benchmark_readiness_report(
            _research_plan(),
            _experiment_plan(),
            build_benchmark_plan(_research_plan(), _experiment_plan()),
            ExecutionConfig(mode="simulated"),
        )

        self.assertEqual(report["status"], "needs_benchmark_upgrade")
        self.assertTrue(any("simulated" in action for action in report["manual_tasks"]))

    def test_write_benchmark_readiness_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            out = root / "run"
            report = write_benchmark_readiness_artifacts(
                _research_plan(),
                _experiment_plan(),
                build_benchmark_plan(_research_plan(), _experiment_plan()),
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]),
                out,
                base_dir=root,
            )

            self.assertEqual(report["status"], "ready_for_benchmark")
            self.assertTrue((out / BENCHMARK_READINESS_JSON).exists())
            self.assertTrue((out / BENCHMARK_READINESS_MD).exists())


def _research_plan() -> ResearchPlan:
    return ResearchPlan(
        topic="机械臂路径规划",
        domain="robotics_motion_planning",
        objective="提高机械臂路径规划成功率",
        search_queries=["robot manipulator motion planning OMPL RRT"],
        benchmarks=["OMPL Benchmark"],
        baselines=["RRT", "RRT*"],
        metrics=["planning_success_rate", "planning_time", "path_length"],
        constraints=[],
        risks=[],
        success_criteria=[],
    )


def _experiment_plan() -> ExperimentPlan:
    return ExperimentPlan(
        idea_title="benchmark readiness",
        objective="在 OMPL Benchmark 上比较候选规划器和 RRT baseline。",
        variables=["planner"],
        metrics=["planning_success_rate", "planning_time", "path_length"],
        protocol=["运行 benchmark"],
        commands=[ExperimentCommand(name="baseline", command=["python3", "simulate.py"])],
        baseline="RRT",
        template_profile="robotics_motion_planning",
    )


def _write_manifest(root: Path, include_provenance: bool = True) -> Path:
    adapter = root / "adapter"
    adapter.mkdir()
    (adapter / "run_benchmark.py").write_text(
        "import json\nwith open('metrics.json', 'w', encoding='utf-8') as handle:\n    json.dump({'planning_success_rate': 0.9}, handle)\n",
        encoding="utf-8",
    )
    manifest = adapter / "manifest.json"
    data = {
        "name": "OMPL Toy",
        "command": ["python3", "run_benchmark.py"],
        "metrics_path": "metrics.json",
        "expected_artifacts": ["metrics.json"],
    }
    if include_provenance:
        data.update(
            {
                "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                "dataset_version": "ompl-1.6.0",
                "split_name": "official readiness split",
                "split_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                "expected_metrics": ["planning_success_rate", "planning_time"],
                "metric_schema": {
                    "planning_success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                    "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
                },
                "license": "BSD-3-Clause",
                "baseline": "RRT",
                "baseline_version": "ompl-1.6.0",
                "citation": "10.1109/MRA.2012.2205651",
                "grader_version": "readiness-grader-v1",
                "grader_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            }
        )
    manifest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return manifest


def _write_manifest_role_set(root: Path, *, include_variant: bool) -> list[str]:
    adapter = root / "adapter-roles"
    adapter.mkdir()
    runner = adapter / "run_benchmark.py"
    runner.write_text(
        "\n".join(
            [
                "import argparse, json",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--metrics', required=True)",
                "parser.add_argument('--variant', default='same')",
                "args = parser.parse_args()",
                "with open(args.metrics, 'w', encoding='utf-8') as handle:",
                "    json.dump({'success_rate': 0.9, 'planning_time': 1.0, 'variant': args.variant}, handle)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifests: list[str] = []
    for role in ["candidate", "baseline", "ablation"]:
        command = ["python3", runner.name, "--metrics", f"{role}_metrics.json"]
        if include_variant:
            command.extend(["--variant", role])
        manifest = adapter / f"{role}.json"
        manifest.write_text(
            json.dumps(
                {
                    "name": f"{role} adapter",
                    "role": role,
                    "command": command,
                    "source_files": [runner.name],
                    "metrics_path": f"{role}_metrics.json",
                    "expected_artifacts": [f"{role}_metrics.json"],
                    "benchmark_kind": "external",
                    "benchmark_url": "https://ompl.kavrakilab.org/benchmark.html",
                    "dataset_url": "https://ompl.kavrakilab.org/benchmark.html",
                    "dataset_version": "ompl-1.6.0",
                    "split_name": "official role split",
                    "split_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                    "expected_metrics": ["success_rate", "planning_time"],
                    "metric_schema": {
                        "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                        "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
                    },
                    "license": "BSD-3-Clause",
                    "baseline": "RRT*",
                    "baseline_version": f"ompl-1.6.0-{role}",
                    "citation": "10.1109/MRA.2012.2205651",
                    "grader": runner.name,
                    "grader_version": "readiness-grader-v1",
                    "grader_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                    "submission_path": f"{role}_submission.csv",
                    "seed_policy": "RESEARCH_AGENT_SEED fixes planner seed and repeat index.",
                    "min_repeats": 3,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        manifests.append(str(manifest))
    return manifests


if __name__ == "__main__":
    unittest.main()
