from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.config import ExecutionConfig, PaperGradeConfig
from research_agent.execution_safety import build_execution_safety_audit_report, render_execution_safety_audit_markdown, write_execution_safety_audit_artifacts
from research_agent.experiments import MAX_EXECUTION_REPEATS, MAX_EXECUTION_TIMEOUT_SECONDS, MAX_OUTPUT_BYTES
from research_agent.models import ExperimentCommand, ExperimentPlan


class ExecutionSafetyTest(unittest.TestCase):
    def test_local_unsafe_command_blocks_execution_safety(self) -> None:
        plan = ExperimentPlan(
            idea_title="unsafe local",
            objective="audit unsafe command",
            variables=["command"],
            metrics=["success_rate"],
            protocol=["run"],
            commands=[ExperimentCommand(name="unsafe", command=["bash", "run.sh"], expected_artifacts=[])],
        )
        with TemporaryDirectory() as tmp:
            report = build_execution_safety_audit_report(plan, ExecutionConfig(mode="local", allowed_commands=["python3"], repeats=1), Path(tmp))
            rendered = render_execution_safety_audit_markdown(report)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("allowed_commands" in item for item in report["blocking_issues"]))
        self.assertIn("实验执行安全审计", rendered)

    def test_simulated_mode_warns_but_writes_artifacts(self) -> None:
        plan = ExperimentPlan(
            idea_title="simulated smoke",
            objective="audit simulated mode",
            variables=["mode"],
            metrics=["success_rate"],
            protocol=["run"],
            commands=[ExperimentCommand(name="simulate_baseline", command=["python3", "simulate.py"], expected_artifacts=["metrics.json"])],
        )
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_execution_safety_audit_artifacts(plan, ExecutionConfig(mode="simulated", repeats=1), run_dir)

            self.assertEqual(report["status"], "warn")
            self.assertTrue((run_dir / "03-execution-safety-audit.json").exists())
            self.assertTrue((run_dir / "03-execution-safety-audit.md").exists())

    def test_benchmark_mode_includes_adapter_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter_dir = root / "adapter"
            adapter_dir.mkdir()
            (adapter_dir / "run_benchmark.py").write_text("print('ok')\n", encoding="utf-8")
            manifest = adapter_dir / "manifest.json"
            manifest.write_text(
                '{"name":"Toy","command":["python3","run_benchmark.py"],"metrics_path":"metrics.json","expected_artifacts":["metrics.json"]}',
                encoding="utf-8",
            )
            plan = ExperimentPlan(
                idea_title="benchmark",
                objective="audit benchmark",
                variables=["adapter"],
                metrics=["success_rate"],
                protocol=["run"],
                commands=[],
            )

            report = build_execution_safety_audit_report(
                plan,
                ExecutionConfig(mode="benchmark", allowed_commands=["python3"], benchmark_manifest_paths=[str(manifest)]),
                root / "run",
                base_dir=root,
            )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["benchmark_adapter_audit"]["status"], "ready")

    def test_execution_resource_hard_limits_block_safety_audit(self) -> None:
        plan = ExperimentPlan(
            idea_title="resource limits",
            objective="reject unbounded execution",
            variables=["limits"],
            metrics=["success_rate"],
            protocol=["run"],
            commands=[ExperimentCommand(name="candidate", command=["python3", "run.py"], expected_artifacts=["metrics.json"])],
        )
        cases = [
            (ExecutionConfig(timeout_seconds=MAX_EXECUTION_TIMEOUT_SECONDS + 1), "timeout_seconds"),
            (ExecutionConfig(repeats=MAX_EXECUTION_REPEATS + 1), "repeats"),
            (ExecutionConfig(max_output_bytes=MAX_OUTPUT_BYTES + 1), "max_output_bytes"),
        ]

        with TemporaryDirectory() as tmp:
            for config, field in cases:
                with self.subTest(field=field):
                    report = build_execution_safety_audit_report(plan, config, Path(tmp))
                    self.assertEqual(report["status"], "block")
                    self.assertTrue(any(field in issue for issue in report["blocking_issues"]))

    def test_paper_grade_benchmark_requires_controlled_external_runner(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "run.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                '{"name":"Toy","command":["python3","run.py"],"metrics_path":"metrics.json","expected_artifacts":["metrics.json"]}',
                encoding="utf-8",
            )
            plan = ExperimentPlan("benchmark", "audit", ["adapter"], ["score"], ["run"], [])
            report = build_execution_safety_audit_report(
                plan,
                ExecutionConfig(mode="benchmark", benchmark_manifest_paths=[str(manifest)]),
                root / "run",
                paper_grade=PaperGradeConfig(enabled=True),
                base_dir=root,
            )

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("external_runner_controlled=true" in issue for issue in report["blocking_issues"]))


if __name__ == "__main__":
    unittest.main()
