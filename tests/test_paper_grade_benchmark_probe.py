from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.config import AgentConfig, ExecutionConfig, PaperGradeConfig
from research_agent.paper_grade_benchmark_probe import (
    PAPER_GRADE_BENCHMARK_PROBE_JSON,
    PAPER_GRADE_BENCHMARK_PROBE_MD,
    build_paper_grade_benchmark_probe,
    render_paper_grade_benchmark_probe_markdown,
    write_paper_grade_benchmark_probe_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]


class PaperGradeBenchmarkProbeTest(unittest.TestCase):
    def test_benchmark_probe_passes_external_manifest_set_with_resolved_urls(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = _write_manifest_set(root, "https://ompl.kavrakilab.org/benchmark.html")
            config = AgentConfig(
                execution=ExecutionConfig(
                    mode="benchmark",
                    allowed_commands=["python3"],
                    repeats=3,
                    benchmark_manifest_paths=manifests,
                )
            )

            report = build_paper_grade_benchmark_probe(config, fetcher=passing_fetcher, base_dir=root)
            rendered = render_paper_grade_benchmark_probe_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["adapter_paper_grade_status"], "ready")
        self.assertTrue(all(item["status"] == "pass" for item in report["checks"]))
        self.assertEqual(len(report["url_checks"]), 6)
        self.assertEqual(len(report["citation_checks"]), 3)
        self.assertIn("Paper-grade Benchmark Probe", rendered)
        self.assertIn("URL Checks", rendered)

    def test_benchmark_probe_rejects_repo_fixture_even_if_citation_url_resolves(self) -> None:
        manifests = [
            ROOT / "examples" / "rrt-2d-benchmark" / "manifest-candidate.json",
            ROOT / "examples" / "rrt-2d-benchmark" / "manifest-baseline.json",
            ROOT / "examples" / "rrt-2d-benchmark" / "manifest-ablation.json",
        ]
        config = AgentConfig(
            execution=ExecutionConfig(
                mode="benchmark",
                allowed_commands=["python3"],
                repeats=3,
                benchmark_manifest_paths=[str(path) for path in manifests],
            )
        )

        report = build_paper_grade_benchmark_probe(config, fetcher=passing_fetcher, base_dir=ROOT)
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(checks["paper_grade_manifest_set"]["status"], "fail")
        self.assertEqual(checks["external_url_reachability"]["status"], "fail")
        self.assertTrue(any("benchmark_kind=fixture" in item for item in report["adapter_paper_grade_issues"]))
        self.assertTrue(any(item["field"] == "dataset_url" and item["status"] == "fail" for item in report["url_checks"]))

    def test_benchmark_probe_rejects_private_http_dataset_url(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = _write_manifest_set(root, "http://127.0.0.1:9/benchmark")
            config = AgentConfig(
                execution=ExecutionConfig(
                    mode="benchmark",
                    allowed_commands=["python3"],
                    repeats=3,
                    benchmark_manifest_paths=manifests,
                )
            )

            report = build_paper_grade_benchmark_probe(config, fetcher=passing_fetcher, base_dir=root)
            checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(checks["paper_grade_manifest_set"]["status"], "fail")
        self.assertTrue(any("dataset_url" in item for item in report["adapter_paper_grade_issues"]))

    def test_benchmark_probe_rejects_role_commands_that_only_change_outputs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = _write_shared_command_manifest_set(root, "https://ompl.kavrakilab.org/benchmark.html")
            config = AgentConfig(
                execution=ExecutionConfig(
                    mode="benchmark",
                    allowed_commands=["python3"],
                    repeats=3,
                    benchmark_manifest_paths=manifests,
                )
            )

            report = build_paper_grade_benchmark_probe(config, fetcher=passing_fetcher, base_dir=root)
            checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(checks["paper_grade_manifest_set"]["status"], "fail")
        self.assertEqual(checks["role_command_contract"]["status"], "fail")
        self.assertTrue(all(item["status"] == "fail" for item in report["role_command_checks"]))
        self.assertTrue(any("重复 role command" in item for item in report["adapter_paper_grade_issues"]))

    def test_benchmark_probe_uses_configured_execution_repeat_threshold(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = _write_manifest_set(root, "https://ompl.kavrakilab.org/benchmark.html")
            config = AgentConfig(
                execution=ExecutionConfig(
                    mode="benchmark",
                    allowed_commands=["python3"],
                    repeats=3,
                    benchmark_manifest_paths=manifests,
                ),
                paper_grade=PaperGradeConfig(enabled=True, min_execution_repeats=5),
            )

            report = build_paper_grade_benchmark_probe(config, fetcher=passing_fetcher, base_dir=root)
            checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(report["adapter_paper_grade_status"], "review_required")
        self.assertEqual(checks["paper_grade_manifest_set"]["status"], "fail")
        self.assertIn("repeats/min_repeats>=5", checks["paper_grade_manifest_set"]["action"])
        issues = "\n".join(report["adapter_paper_grade_issues"])
        self.assertIn("repeats >= 5", issues)
        self.assertIn("min_repeats 至少需要 5", issues)

    def test_write_benchmark_probe_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = _write_manifest_set(root, "https://ompl.kavrakilab.org/benchmark.html")
            config = AgentConfig(
                execution=ExecutionConfig(
                    mode="benchmark",
                    allowed_commands=["python3"],
                    repeats=3,
                    benchmark_manifest_paths=manifests,
                )
            )
            out_dir = root / "out"
            report = write_paper_grade_benchmark_probe_artifacts(
                config,
                out_dir,
                fetcher=passing_fetcher,
                base_dir=root,
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue((out_dir / PAPER_GRADE_BENCHMARK_PROBE_JSON).exists())
            self.assertTrue((out_dir / PAPER_GRADE_BENCHMARK_PROBE_MD).exists())


def _write_manifest_set(root: Path, dataset_url: str) -> list[str]:
    manifests: list[str] = []
    for role in ["candidate", "baseline", "ablation"]:
        script = root / f"run_{role}.py"
        script.write_text("print('ok')\n", encoding="utf-8")
        manifest = root / f"{role}.json"
        manifest.write_text(
            json.dumps(
                {
                    "name": f"{role} external adapter",
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
                    "benchmark_url": dataset_url,
                    "dataset_url": dataset_url,
                    "dataset_version": "ompl-1.6.0",
                    "split_name": f"official-{role}-split",
                    "split_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                    "license": "BSD-3-Clause",
                    "baseline": "RRT*",
                    "baseline_version": f"ompl-1.6.0-{role}",
                    "citation": "10.1109/MRA.2012.2205651",
                    "grader": script.name,
                    "grader_version": f"grader-{role}-v1",
                    "grader_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                    "submission_path": f"{role}_submission.csv",
                    "seed_policy": "RESEARCH_AGENT_SEED fixes task sampling and repeat index.",
                    "min_repeats": 3,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        manifests.append(str(manifest))
    return manifests


def _write_shared_command_manifest_set(root: Path, dataset_url: str) -> list[str]:
    script = root / "run_benchmark.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    manifests: list[str] = []
    for role in ["candidate", "baseline", "ablation"]:
        manifest = root / f"{role}.json"
        manifest.write_text(
            json.dumps(
                {
                    "name": f"{role} external adapter",
                    "role": role,
                    "command": ["python3", script.name, "--metrics", f"{role}_metrics.json"],
                    "source_files": [script.name],
                    "metrics_path": f"{role}_metrics.json",
                    "expected_artifacts": [f"{role}_metrics.json"],
                    "expected_metrics": ["success_rate", "planning_time"],
                    "metric_schema": {
                        "success_rate": {"direction": "higher_is_better", "unit": "ratio", "description": "Fraction solved."},
                        "planning_time": {"direction": "lower_is_better", "unit": "seconds", "description": "Planning time."},
                    },
                    "benchmark_kind": "external",
                    "benchmark_url": dataset_url,
                    "dataset_url": dataset_url,
                    "dataset_version": "ompl-1.6.0",
                    "split_name": f"official-{role}-split",
                    "split_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                    "license": "BSD-3-Clause",
                    "baseline": "RRT*",
                    "baseline_version": f"ompl-1.6.0-{role}",
                    "citation": "10.1109/MRA.2012.2205651",
                    "grader": script.name,
                    "grader_version": f"grader-{role}-v1",
                    "grader_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                    "submission_path": f"{role}_submission.csv",
                    "seed_policy": "RESEARCH_AGENT_SEED fixes task sampling and repeat index.",
                    "min_repeats": 3,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        manifests.append(str(manifest))
    return manifests


def passing_fetcher(url: str, timeout_seconds: float) -> dict[str, object]:
    return {"ok": True, "status_code": 200, "method": "HEAD"}


if __name__ == "__main__":
    unittest.main()
