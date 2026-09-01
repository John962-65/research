from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json
from research_agent.llm_observability_summary import build_llm_observability_summary_report, render_llm_observability_summary_markdown, write_llm_observability_summary_artifacts


class LLMObservabilitySummaryTest(unittest.TestCase):
    def test_summary_passes_when_trace_economics_and_observability_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_pass_inputs(run_dir)

            report = write_llm_observability_summary_artifacts("机械臂路径规划", run_dir)
            rendered = render_llm_observability_summary_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["llm_calls"]["total"], 4)
        self.assertEqual(report["statuses"]["runtime_contract"], "pass")
        self.assertTrue(report["runtime_contract"]["model_configured"])
        self.assertEqual(report["stage_coverage"]["passed_required"], 7)
        self.assertEqual(report["stage_coverage"]["missing_required_stage_count"], 0)
        self.assertEqual(report["stage_coverage"]["missing_required_stages"], [])
        self.assertEqual(report["token_and_cost"]["input_tokens_estimated"], 120)
        self.assertIn("LLM Observability Summary", rendered)
        self.assertIn("AI-Scientist-v2", rendered)

    def test_summary_blocks_missing_ledger_or_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_json(run_dir / "13-llm-trace-audit.json", {"status": "block", "blocking_issues": ["ledger 缺失"]})

            report = build_llm_observability_summary_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("run-llm-ledger.json" in item for item in report["blocking_issues"]))
        self.assertTrue(any("13-llm-runtime-contract.json" in item for item in report["blocking_issues"]))
        self.assertTrue(any("13-run-economics-audit.json" in item for item in report["blocking_issues"]))


def _write_pass_inputs(run_dir: Path) -> None:
    write_json(
        run_dir / "run-llm-ledger.json",
        {"total_calls": 4, "successful_calls": 4, "failed_calls": 0, "budget_exceeded_calls": 0, "entries": [{"status": "success"} for _ in range(4)]},
    )
    write_json(
        run_dir / "13-llm-trace-audit.json",
        {
            "status": "pass",
            "ledger_summary": {"total_calls": 4, "successful_calls": 4, "failed_calls": 0, "budget_exceeded_calls": 0, "entries": 4},
            "coverage": {"required_stages": 7, "passed_required": 7, "coverage_ratio": 1.0},
            "stage_gap_summary": {"missing_required_stage_count": 0, "missing_required_stages": [], "warned_optional_stage_count": 0, "warned_optional_stages": []},
            "blocking_issues": [],
            "manual_tasks": [],
            "warnings": [],
        },
    )
    write_json(
        run_dir / "13-llm-runtime-contract.json",
        {
            "status": "pass",
            "summary": {
                "provider": "openai-compatible",
                "model_configured": True,
                "api_key_persisted": False,
                "call_budget_configured": True,
                "prompt_budget_configured": True,
                "pricing_configured": True,
            },
            "blocking_issues": [],
            "manual_tasks": [],
            "warnings": [],
        },
    )
    write_json(
        run_dir / "13-run-economics-audit.json",
        {
            "status": "pass",
            "summary": {"total_calls": 4, "successful_calls": 4, "failed_calls": 0, "budget_exceeded_calls": 0, "input_tokens_estimated": 120, "output_tokens_estimated": 60, "total_duration_seconds": 1.2, "estimated_cost_usd": 0.001},
            "budget": {"used_calls": 4, "max_calls": 10, "call_utilization": 0.4, "used_prompt_chars": 480, "max_prompt_chars": 4000, "prompt_utilization": 0.12},
            "blocking_issues": [],
            "manual_tasks": [],
            "warnings": [],
        },
    )
    write_json(
        run_dir / "13-agent-observability-audit.json",
        {
            "status": "pass",
            "summary": {"manifest_events": 30, "manifest_artifacts": 100, "llm_total_calls": 4, "llm_successful_calls": 4, "experiment_runs": 2, "repair_queue_status": "pass"},
            "blocking_issues": [],
            "manual_tasks": [],
            "warnings": [],
        },
    )


if __name__ == "__main__":
    unittest.main()
