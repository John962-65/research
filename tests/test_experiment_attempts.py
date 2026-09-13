from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import time
import unittest

from research_agent import experiment_attempts
from research_agent.config import ExecutionConfig
from research_agent.experiments import run_experiments
from research_agent.models import ExperimentCommand, ExperimentPlan


class ProcessMatchTest(unittest.TestCase):
    def test_alive_process_with_matching_cmdline(self) -> None:
        process = subprocess.Popen(["/bin/sleep", "30"])
        try:
            # fork 后 exec 前的短暂窗口内 /proc cmdline 可能仍是父进程的，轮询等待。
            matched = False
            for _ in range(40):
                if experiment_attempts.process_matches(process.pid, ["/bin/sleep", "30"]):
                    matched = True
                    break
                time.sleep(0.05)
            self.assertTrue(matched)
        finally:
            process.terminate()
            process.wait()

    def test_dead_process_reported_dead(self) -> None:
        process = subprocess.Popen(["/bin/sleep", "30"])
        process.terminate()
        process.wait()
        self.assertFalse(experiment_attempts.process_matches(process.pid, ["/bin/sleep", "30"]))

    def test_same_interpreter_different_script_is_rejected(self) -> None:
        # 复审第 8 项：解释器和末尾参数相同、中间执行脚本不同 → 必须视为不同任务。
        process = subprocess.Popen(["/bin/sleep", "30"])
        try:
            matched = False
            for _ in range(40):
                if experiment_attempts.process_matches(process.pid, ["/bin/sleep", "30"]):
                    matched = True
                    break
                time.sleep(0.05)
            self.assertTrue(matched)
            # 相同解释器位置特征、不同中间参数 → 不匹配。
            self.assertFalse(experiment_attempts.process_matches(process.pid, ["/bin/sleep", "other-script.py", "30"]))
            self.assertFalse(experiment_attempts.process_matches(process.pid, ["/bin/sleep"]))
        finally:
            process.terminate()
            process.wait()

    def test_pid_reuse_with_different_cmdline_is_rejected(self) -> None:
        # 只凭 PID 存在不能判断存活：命令行不匹配 → 不算活任务（A13）。
        process = subprocess.Popen(["/bin/sleep", "30"])
        try:
            self.assertFalse(experiment_attempts.process_matches(process.pid, ["/bin/echo", "30"]))
        finally:
            process.terminate()
            process.wait()


class AttemptRecordsTest(unittest.TestCase):
    def test_start_end_roundtrip_and_interrupt_marking(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            experiment_attempts.record_attempt_start(
                run_dir,
                task_id="task-a#r0",
                attempt_number=1,
                pid=999999,  # 不存在的 PID
                command=["/bin/sleep", "30"],
                timeout_seconds=30,
                stdout_log="experiments/logs/a.log",
            )
            live = experiment_attempts.find_live_attempt(run_dir)
            self.assertIsNone(live, "不存在的 PID 不应判为活任务")
            marked = experiment_attempts.mark_interrupted_attempts(run_dir)
            self.assertEqual(len(marked), 1)
            self.assertEqual(marked[0]["status"], "interrupted")
            # 记录终态后完整历史保留。
            experiment_attempts.record_attempt_end(
                run_dir,
                task_id="task-a#r0",
                attempt_number=1,
                pid=999999,
                status="failed",
                exit_code=1,
                duration_seconds=0.2,
            )
            history = experiment_attempts.load_attempt_history(run_dir)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["status"], "interrupted")


class RunExperimentsResumeGuardTest(unittest.TestCase):
    def _plan(self, tmp: Path) -> ExperimentPlan:
        script = tmp / "experiments" / "tiny_ok.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("print('ok')\n", encoding="utf-8")
        return ExperimentPlan(
            idea_title="guard 测试",
            objective="验证活任务守卫。",
            variables=["method"],
            metrics=["success_rate"],
            protocol=["run candidate", "run baseline"],
            commands=[
                ExperimentCommand(name="candidate", command=["python3", "tiny_ok.py"]),
                ExperimentCommand(name="baseline", command=["python3", "tiny_ok.py"]),
            ],
        )

    def test_run_refuses_to_start_when_live_attempt_exists(self) -> None:
        # A13：存在存活同命令尝试时，run_experiments 立即报错，不重复启动。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            plan = self._plan(run_dir)
            blocker = subprocess.Popen(["/bin/sleep", "30"])
            try:
                experiment_attempts.record_attempt_start(
                    run_dir,
                    task_id="candidate#r0",
                    attempt_number=1,
                    pid=blocker.pid,
                    command=["/bin/sleep", "30"],
                    timeout_seconds=30,
                )
                config = ExecutionConfig(mode="local", repeats=1, timeout_seconds=30, allowed_commands=["python3"])
                with self.assertRaises(RuntimeError) as ctx:
                    run_experiments(plan, config, run_dir)
                self.assertIn("仍在运行", str(ctx.exception))
                # 守卫触发后，真任务没有被执行（无结果文件）。
                self.assertFalse((run_dir / "04-results.json").exists())
            finally:
                blocker.terminate()
                blocker.wait()
            # 进程结束后（守卫解除）同一 run 可正常执行。
            config = ExecutionConfig(mode="local", repeats=1, timeout_seconds=30, allowed_commands=["python3"])
            results = run_experiments(plan, config, run_dir)
            self.assertTrue(results)

    def test_local_run_writes_attempt_records_and_logs(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            plan = self._plan(run_dir)
            config = ExecutionConfig(mode="local", repeats=1, timeout_seconds=30, allowed_commands=["python3"])
            results = run_experiments(plan, config, run_dir)
            self.assertEqual({row.status for row in results}, {"passed"})
            history = experiment_attempts.load_attempt_history(run_dir)
            self.assertEqual(len(history), 2)
            for entry in history:
                self.assertEqual(entry["status"], "passed")
                self.assertEqual(entry["exit_code"], 0)
                self.assertGreater(entry["pid"], 0)
                self.assertIn("started_at", entry)
                self.assertIn("ended_at", entry)
                self.assertIn("timeout_seconds", entry)
                self.assertTrue(entry["stdout_log"])
            # stdout/stderr 落盘且路径有效。
            log = run_dir / history[0]["stdout_log"]
            self.assertTrue(log.exists())
            self.assertIn("ok", log.read_text(encoding="utf-8"))

    def test_interrupted_attempt_is_recorded_before_fresh_run(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            plan = self._plan(run_dir)
            experiment_attempts.record_attempt_start(
                run_dir,
                task_id="candidate#r0",
                attempt_number=1,
                pid=999999,
                command=["python3", "tiny_ok.py"],
                timeout_seconds=30,
            )
            config = ExecutionConfig(mode="local", repeats=1, timeout_seconds=30, allowed_commands=["python3"])
            run_experiments(plan, config, run_dir)
            history = experiment_attempts.load_attempt_history(run_dir)
            statuses = [entry["status"] for entry in history]
            self.assertEqual(statuses.count("interrupted"), 1, "旧的中断尝试保留为 interrupted")
            self.assertEqual(statuses.count("passed"), 2)
            # 尝试编号按任务递增，不覆盖历史。
            candidate_attempts = [entry for entry in history if entry["task_id"].startswith("candidate#")]
            self.assertEqual([entry["attempt_number"] for entry in candidate_attempts], [1, 2])


if __name__ == "__main__":
    unittest.main()
