from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import time
import unittest

from research_agent.config import ExecutionConfig
from research_agent.experiments import (
    ENVIRONMENT_SNAPSHOT_JSON,
    EXPERIMENT_RUNBOOK_JSON,
    MAX_EXECUTION_REPEATS,
    MAX_EXECUTION_TIMEOUT_SECONDS,
    MAX_OUTPUT_BYTES,
    build_experiment_runbook,
    plan_experiment,
    render_experiment_plan_markdown,
    run_experiments,
)
from research_agent.models import ExperimentCommand, ExperimentPlan, ExperimentResult, ResearchIdea
from research_agent.research_plan import build_research_plan


class ExperimentTemplateTest(unittest.TestCase):
    def test_robotics_plan_uses_motion_planning_template(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        idea = _idea()

        plan = plan_experiment(idea, research_plan=research_plan)
        rendered = render_experiment_plan_markdown(plan)

        self.assertEqual(plan.template_profile, "robotics_motion_planning")
        self.assertTrue(any("robotics_candidate" in command.name for command in plan.commands))
        self.assertTrue(any("ablation" in command.name for command in plan.commands))
        self.assertTrue(any("--profile" in command.command for command in plan.commands))
        self.assertIn("robotics_motion_planning", rendered)

    def test_manager_constraints_are_carried_into_fallback_plan(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        plan = plan_experiment(
            _idea(),
            research_plan=research_plan,
            manager_constraints="Experiment manager constraints:\n- 先规划低成本 smoke-first 实验。\n- 实验必须包含直接 baseline：RRT*。",
        )

        rendered = render_experiment_plan_markdown(plan)

        self.assertTrue(any("experiment manager" in step.lower() for step in plan.protocol))
        self.assertIn("experiment manager", plan.rationale.lower())
        self.assertIn("smoke-first", rendered)

    def test_local_robotics_template_outputs_domain_metrics(self) -> None:
        research_plan = build_research_plan("机械臂路径规划")
        plan = plan_experiment(_idea(), research_plan=research_plan)

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            results = run_experiments(
                plan,
                ExecutionConfig(mode="local", allowed_commands=["python3"], repeats=1),
                run_dir,
            )

            metrics = {key for result in results for key in result.metrics}
            manifest = json.loads((run_dir / "experiments" / "experiment-template.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["template_profile"], "robotics_motion_planning")
            self.assertIn("planning_success_rate", metrics)
            self.assertIn("collision_rate", metrics)
            self.assertTrue((run_dir / "experiments" / "candidate_metrics.json").exists())
            self.assertTrue((run_dir / "experiments" / "baseline_metrics.json").exists())
            self.assertTrue((run_dir / "experiments" / "ablation_metrics.json").exists())
            runbook = json.loads((run_dir / EXPERIMENT_RUNBOOK_JSON).read_text(encoding="utf-8"))
            environment = json.loads((run_dir / ENVIRONMENT_SNAPSHOT_JSON).read_text(encoding="utf-8"))
            self.assertEqual(runbook["execution"]["mode"], "local")
            self.assertEqual(runbook["execution"]["environment_snapshot"], ENVIRONMENT_SNAPSHOT_JSON)
            self.assertEqual(runbook["environment"]["source_tree"]["aggregate_sha256"], environment["source_tree"]["aggregate_sha256"])
            self.assertTrue(environment["python"]["executable"])
            self.assertTrue(environment["source_tree"]["file_count"])
            self.assertTrue(any(item["path"] == "src/research_agent/experiments.py" and len(item["sha256"]) == 64 for item in environment["source_tree"]["files"]))
            self.assertTrue((run_dir / "04-environment-snapshot.md").exists())
            self.assertIn("实验环境快照", (run_dir / "04-environment-snapshot.md").read_text(encoding="utf-8"))
            self.assertTrue(runbook["commands"][0]["allowed"])
            self.assertTrue(any(item["path"] == "experiments/candidate_metrics.json" and len(item["sha256"]) == 64 for item in runbook["artifacts"]))
            self.assertTrue(any(item["path"] == "experiments/ablation_metrics.json" and len(item["sha256"]) == 64 for item in runbook["artifacts"]))
            self.assertTrue(all(run["seed"] for run in runbook["runs"]))

    def test_local_timeout_is_recorded_as_result_status(self) -> None:
        plan = ExperimentPlan(
            idea_title="timeout audit",
            objective="确认本地命令超时会被结构化记录。",
            variables=["runtime"],
            metrics=["success_rate"],
            protocol=["run slow command"],
            commands=[ExperimentCommand(name="slow_command", command=["python3", "slow.py"])],
        )
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            experiment_dir = run_dir / "experiments"
            experiment_dir.mkdir(parents=True)
            (experiment_dir / "slow.py").write_text("import time\ntime.sleep(2)\n", encoding="utf-8")

            results = run_experiments(
                plan,
                ExecutionConfig(mode="local", allowed_commands=["python3"], timeout_seconds=1, repeats=1),
                run_dir,
            )
            runbook = json.loads((run_dir / EXPERIMENT_RUNBOOK_JSON).read_text(encoding="utf-8"))

            self.assertEqual(results[0].status, "timeout")
            self.assertIn("超时", results[0].stderr)
            self.assertEqual(runbook["runs"][0]["status"], "timeout")
            self.assertTrue(any("timeout" in warning for warning in runbook["warnings"]))

    def test_timeout_terminates_spawned_process_group(self) -> None:
        plan = ExperimentPlan(
            idea_title="process group timeout",
            objective="terminate descendants",
            variables=["runtime"],
            metrics=["success_rate"],
            protocol=["spawn child"],
            commands=[ExperimentCommand(name="spawner", command=["python3", "parent.py"])],
        )
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            experiment_dir = run_dir / "experiments"
            experiment_dir.mkdir(parents=True)
            (experiment_dir / "child.py").write_text(
                "import pathlib, time\ntime.sleep(2)\npathlib.Path('child-survived.txt').write_text('alive')\n",
                encoding="utf-8",
            )
            (experiment_dir / "parent.py").write_text(
                "import subprocess, sys, time\nsubprocess.Popen([sys.executable, 'child.py'])\ntime.sleep(30)\n",
                encoding="utf-8",
            )

            result = run_experiments(
                plan,
                ExecutionConfig(mode="local", allowed_commands=["python3"], timeout_seconds=1, repeats=1),
                run_dir,
            )[0]
            time.sleep(1.5)

            self.assertEqual(result.status, "timeout")
            self.assertFalse((experiment_dir / "child-survived.txt").exists())

    def test_local_output_capture_keeps_only_bounded_tail(self) -> None:
        plan = ExperimentPlan(
            idea_title="bounded output",
            objective="bound output memory",
            variables=["bytes"],
            metrics=["success_rate"],
            protocol=["write output"],
            commands=[ExperimentCommand(name="noisy", command=["python3", "noisy.py"])],
        )
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            experiment_dir = run_dir / "experiments"
            experiment_dir.mkdir(parents=True)
            (experiment_dir / "noisy.py").write_text(
                "import sys\nsys.stdout.write('START-' + 'x' * 200000 + '-STDOUT-END')\n"
                "sys.stderr.write('START-' + 'y' * 200000 + '-STDERR-END')\n",
                encoding="utf-8",
            )

            result = run_experiments(
                plan,
                ExecutionConfig(mode="local", allowed_commands=["python3"], repeats=1, max_output_bytes=1024),
                run_dir,
            )[0]

            self.assertEqual(result.status, "passed")
            self.assertLessEqual(len(result.stdout.encode("utf-8")), 1024)
            self.assertLessEqual(len(result.stderr.encode("utf-8")), 1024)
            self.assertTrue(result.stdout.endswith("-STDOUT-END"))
            self.assertTrue(result.stderr.endswith("-STDERR-END"))
            self.assertNotIn("START-", result.stdout)
            self.assertNotIn("START-", result.stderr)

    def test_direct_execution_rejects_resource_limit_bypass(self) -> None:
        plan = ExperimentPlan("limits", "reject", ["limit"], ["score"], ["run"], [])
        cases = [
            (ExecutionConfig(timeout_seconds=MAX_EXECUTION_TIMEOUT_SECONDS + 1), "timeout_seconds"),
            (ExecutionConfig(repeats=MAX_EXECUTION_REPEATS + 1), "repeats"),
            (ExecutionConfig(max_output_bytes=MAX_OUTPUT_BYTES + 1), "max_output_bytes"),
        ]
        with TemporaryDirectory() as tmp:
            for config, field in cases:
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError, field):
                        run_experiments(plan, config, Path(tmp))

    def test_local_blocked_command_is_recorded_in_runbook(self) -> None:
        plan = ExperimentPlan(
            idea_title="blocked audit",
            objective="确认非白名单命令被阻断。",
            variables=["command"],
            metrics=["success_rate"],
            protocol=["run blocked command"],
            commands=[ExperimentCommand(name="blocked_command", command=["bash", "run.sh"])],
        )
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            results = run_experiments(
                plan,
                ExecutionConfig(mode="local", allowed_commands=["python3"], repeats=1),
                run_dir,
            )
            runbook = json.loads((run_dir / EXPERIMENT_RUNBOOK_JSON).read_text(encoding="utf-8"))

            self.assertEqual(results[0].status, "blocked")
            self.assertIn("allowed_commands", results[0].stderr)
            self.assertFalse(runbook["commands"][0]["allowed"])
            self.assertEqual(runbook["runs"][0]["validation_issues"], results[0].validation_issues)

    def test_runbook_artifacts_handle_relative_run_dir(self) -> None:
        plan = ExperimentPlan(
            idea_title="relative runbook",
            objective="确认相对 run_dir 可以记录绝对解析后的产物。",
            variables=["artifact_path"],
            metrics=["accuracy"],
            protocol=["record artifact"],
            commands=[ExperimentCommand(name="candidate", command=["python3", "run.py"], expected_artifacts=["metrics.json"])],
        )
        with TemporaryDirectory(dir=".") as tmp:
            raw_run_dir = Path(tmp)
            run_dir = raw_run_dir if not raw_run_dir.is_absolute() else raw_run_dir.relative_to(Path.cwd())
            experiment_dir = run_dir / "experiments"
            experiment_dir.mkdir(parents=True)
            (experiment_dir / "metrics.json").write_text('{"accuracy": 1.0}\n', encoding="utf-8")
            result = ExperimentResult("candidate", "passed", {"accuracy": 1.0}, ["metrics.json"], repeat_index=0)

            runbook = build_experiment_runbook(
                plan,
                ExecutionConfig(mode="local", allowed_commands=["python3"], repeats=1),
                run_dir,
                [result],
            )

            self.assertEqual(runbook["runs"][0]["produced_artifacts"][0]["path"], "experiments/metrics.json")


def _idea() -> ResearchIdea:
    return ResearchIdea(
        title="可复现路径规划验证",
        hypothesis="候选方法应在公开任务上优于经典规划器。",
        mechanism="对相同障碍布局和随机种子运行候选方法与 baseline。",
        expected_contribution="给出可复现的机械臂路径规划评估协议。",
        novelty=4,
        feasibility=4,
        risk=2,
        evaluation=["任务成功率"],
        baseline="文献中最高相关的传统 baseline 或消融版本",
    )


if __name__ == "__main__":
    unittest.main()
