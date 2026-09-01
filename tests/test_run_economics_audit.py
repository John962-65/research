from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.run_economics_audit import (
    RUN_ECONOMICS_AUDIT_JSON,
    RUN_ECONOMICS_AUDIT_MD,
    build_run_economics_audit_report,
    render_run_economics_audit_markdown,
    write_run_economics_audit_artifacts,
)


class RunEconomicsAuditTest(unittest.TestCase):
    def test_writes_stage_level_token_duration_and_cost_report(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ledger(run_dir, _successful_entries())
            write_json(
                run_dir / "run-config.json",
                {
                    "llm": {
                        "max_calls": 10,
                        "max_prompt_chars": 2000,
                        "input_cost_per_million_tokens": 2.0,
                        "output_cost_per_million_tokens": 10.0,
                    }
                },
            )

            report = write_run_economics_audit_artifacts("机械臂路径规划", run_dir)
            rendered = render_run_economics_audit_markdown(report)
            saved = json.loads((run_dir / RUN_ECONOMICS_AUDIT_JSON).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "pass")
            self.assertTrue(report["summary"]["estimated_cost_usd"] > 0)
            self.assertTrue(any(item["stage"] == "research_planning" for item in report["stages"]))
            self.assertTrue(any(item["stage"] == "paper_review" for item in report["stages"]))
            self.assertTrue((run_dir / RUN_ECONOMICS_AUDIT_MD).exists())
            self.assertEqual(saved["status"], "pass")
            self.assertIn("Run Economics Audit", rendered)

    def test_blocks_missing_ledger(self) -> None:
        with TemporaryDirectory() as tmp:
            report = build_run_economics_audit_report("机械臂路径规划", Path(tmp))

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("run-llm-ledger.json" in item for item in report["blocking_issues"]))

    def test_blocks_failed_or_budget_exceeded_calls(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ledger(
                run_dir,
                [
                    {"purpose": "Research planning. You create domain profiles.", "status": "success", "system_chars": 100, "user_chars": 100, "response_chars": 80, "duration_seconds": 0.1},
                    {"purpose": "Paper writing. You write concise Chinese academic Markdown.", "status": "failed", "system_chars": 100, "user_chars": 100, "response_chars": 0, "duration_seconds": 0.1},
                    {"purpose": "Paper revision. You revise Chinese academic Markdown.", "status": "budget_exceeded", "system_chars": 100, "user_chars": 100, "response_chars": 0, "duration_seconds": 0.0},
                ],
            )

            report = build_run_economics_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("failed=1" in item for item in report["blocking_issues"]))
            self.assertTrue(any("budget_exceeded=1" in item for item in report["blocking_issues"]))

    def test_reviews_recovered_failed_or_budget_exceeded_calls(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ledger(
                run_dir,
                [
                    {"stage": "paper_writing", "purpose": "paper writing", "status": "failed", "system_chars": 100, "user_chars": 100, "response_chars": 0, "duration_seconds": 0.1},
                    {"stage": "paper_revision", "purpose": "paper revision", "status": "budget_exceeded", "system_chars": 100, "user_chars": 100, "response_chars": 0, "duration_seconds": 0.0},
                    {"stage": "paper_writing", "purpose": "paper writing", "status": "success", "system_chars": 100, "user_chars": 100, "response_chars": 80, "duration_seconds": 0.2},
                    {"stage": "paper_revision", "purpose": "paper revision", "status": "success", "system_chars": 100, "user_chars": 100, "response_chars": 80, "duration_seconds": 0.2},
                ],
            )

            report = build_run_economics_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertFalse(report["blocking_issues"])
            self.assertTrue(any("均已由后续同阶段 success 恢复" in item for item in report["warnings"]))

    def test_stage_summary_prefers_explicit_stage_over_legacy_purpose(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ledger(
                run_dir,
                [
                    {
                        "stage": "paper_writing",
                        "purpose": "Research planning. legacy text should not drive grouping.",
                        "status": "success",
                        "system_chars": 100,
                        "user_chars": 100,
                        "response_chars": 80,
                        "duration_seconds": 0.1,
                    }
                ],
            )

            report = build_run_economics_audit_report("机械臂路径规划", run_dir)

            self.assertEqual([item["stage"] for item in report["stages"]], ["paper_writing"])

    def test_requires_review_for_high_budget_pressure_or_partial_pricing(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_ledger(run_dir, _successful_entries())
            write_json(
                run_dir / "run-config.json",
                {
                    "llm": {
                        "max_calls": 3,
                        "max_prompt_chars": 500,
                        "input_cost_per_million_tokens": 2.0,
                        "output_cost_per_million_tokens": 0.0,
                    }
                },
            )

            report = build_run_economics_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "review_required")
            self.assertTrue(any("预算" in item for item in report["warnings"]))
            self.assertTrue(any("部分 token 单价" in item for item in report["manual_tasks"]))


def _successful_entries() -> list[dict[str, object]]:
    return [
        {"purpose": "Research planning. You create domain profiles.", "status": "success", "system_chars": 120, "user_chars": 280, "response_chars": 160, "duration_seconds": 0.2},
        {"purpose": "Literature synthesis. You are a scientific research assistant.", "status": "success", "system_chars": 150, "user_chars": 350, "response_chars": 200, "duration_seconds": 0.3},
        {"purpose": "Scientific peer review. You are a rigorous reviewer.", "status": "success", "system_chars": 110, "user_chars": 240, "response_chars": 180, "duration_seconds": 0.4},
    ]


def _write_ledger(run_dir: Path, entries: list[dict[str, object]]) -> None:
    write_json(
        run_dir / "run-llm-ledger.json",
        {
            "total_calls": len(entries),
            "successful_calls": sum(1 for item in entries if item["status"] == "success"),
            "failed_calls": sum(1 for item in entries if item["status"] == "failed"),
            "budget_exceeded_calls": sum(1 for item in entries if item["status"] == "budget_exceeded"),
            "total_prompt_chars": sum(int(item.get("system_chars", 0)) + int(item.get("user_chars", 0)) for item in entries),
            "total_response_chars": sum(int(item.get("response_chars", 0)) for item in entries),
            "entries": entries,
        },
    )


if __name__ == "__main__":
    unittest.main()
