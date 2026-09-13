from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.run_budget import (
    RUN_BUDGET_JSON,
    RunBudgetExhausted,
    budget_summary,
    ensure_budget,
    load_budget,
    record_execution,
)


class RunBudgetTest(unittest.TestCase):
    def test_record_and_ensure_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            ensure_budget(run_dir, "experiment_runs")  # 0/3 → 通过
            record_execution(run_dir, "experiment_runs", note="first")
            record_execution(run_dir, "experiment_runs", note="second")
            summary = budget_summary(run_dir)
            self.assertEqual(summary["experiment_runs"], {"consumed": 2, "limit": 3})
            ensure_budget(run_dir, "experiment_runs")

    def test_exhaustion_stops_and_persists_across_resume(self) -> None:
        # A16：耗尽 → 停止；恢复（新进程语义，重新加载文件）不能绕过。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for index in range(3):
                ensure_budget(run_dir, "repair_resumes")
                record_execution(run_dir, "repair_resumes", note=f"resume-{index}")
            with self.assertRaises(RunBudgetExhausted) as ctx:
                ensure_budget(run_dir, "repair_resumes")
            self.assertIn("预算已耗尽", str(ctx.exception))
            self.assertIn("保留", str(ctx.exception))
            # 预算文件持久化，模拟"新进程恢复"再次检查仍被拦。
            self.assertTrue((run_dir / RUN_BUDGET_JSON).exists())
            with self.assertRaises(RunBudgetExhausted):
                ensure_budget(run_dir, "repair_resumes")

    def test_kinds_are_independent(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for _ in range(3):
                record_execution(run_dir, "paper_revisions")
            with self.assertRaises(RunBudgetExhausted):
                ensure_budget(run_dir, "paper_revisions")
            ensure_budget(run_dir, "experiment_runs")


    def test_event_history_survives_reload(self) -> None:
        # 复审第 8 项：连续记录三次，事件历史必须保留全部 3 条而不是只剩最后一条。
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            for index in range(3):
                record_execution(run_dir, "experiment_runs", note=f"run-{index}")
            budget = load_budget(run_dir)
            self.assertEqual(budget["consumed"]["experiment_runs"], 3)
            self.assertEqual(len(budget["events"]), 3)
            self.assertEqual([item["note"] for item in budget["events"]], ["run-0", "run-1", "run-2"])


if __name__ == "__main__":
    unittest.main()
