from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.artifacts import write_json, write_text
from research_agent.llm_trace_audit import build_llm_trace_audit_report, render_llm_trace_audit_markdown, write_llm_trace_audit_artifacts


class LLMTraceAuditTest(unittest.TestCase):
    def test_passes_when_required_stage_purposes_are_covered_for_legacy_ledgers(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            _write_ledger(run_dir, _successful_entries())
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": True, "total_llm_calls": 8})

            report = write_llm_trace_audit_artifacts("机械臂路径规划", run_dir)
            rendered = render_llm_trace_audit_markdown(report)

            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["blocking_issues"])
            self.assertFalse(report["manual_tasks"])
            self.assertEqual(report["coverage"]["passed_required"], report["coverage"]["required_stages"])
            self.assertTrue((run_dir / "13-llm-trace-audit.json").exists())
            self.assertIn("LLM Trace Audit", rendered)

    def test_passes_when_explicit_stage_ids_are_covered(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            _write_ledger(run_dir, _successful_stage_entries())
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": True, "total_llm_calls": 8})

            report = build_llm_trace_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["coverage"]["passed_required"], report["coverage"]["required_stages"])
            research_check = next(item for item in report["stage_checks"] if item["stage"] == "research_planning")
            self.assertEqual(research_check["observed_successes"], 1)
            self.assertIn("research_planning:research planning", research_check["matched_entries"])

    def test_blocks_missing_ledger_entries_for_existing_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            write_json(run_dir / "run-llm-ledger.json", {"total_calls": 8, "successful_calls": 8, "failed_calls": 0, "entries": []})
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": True, "total_llm_calls": 8})

            report = build_llm_trace_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("缺少 entries" in item for item in report["blocking_issues"]))
            self.assertTrue(any(item["stage"] == "research_planning" and item["status"] == "block" for item in report["stage_checks"]))
            self.assertEqual(report["stage_gap_summary"]["missing_required_stage_count"], report["coverage"]["required_stages"])
            self.assertIn("research_planning", report["stage_gap_summary"]["missing_required_stages"])

    def test_blocks_failed_or_budget_exceeded_calls(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            entries = [
                *_successful_entries(),
                {"purpose": "Paper writing. You write concise Chinese academic Markdown.", "status": "failed"},
                {"purpose": "Paper revision. You revise Chinese academic Markdown without inventing evidence.", "status": "budget_exceeded"},
            ]
            _write_ledger(run_dir, entries)
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": True, "total_llm_calls": len(entries)})

            report = build_llm_trace_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("failed_calls=1" in item for item in report["blocking_issues"]))
            self.assertTrue(any("budget_exceeded_calls=1" in item for item in report["blocking_issues"]))

    def test_warns_when_failed_calls_are_recovered_by_later_stage_success(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            entries = [
                {"stage": "paper_writing", "purpose": "paper writing", "status": "failed"},
                {"stage": "paper_revision", "purpose": "paper revision", "status": "budget_exceeded"},
                *_successful_stage_entries(),
            ]
            _write_ledger(run_dir, entries)
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": True, "total_llm_calls": len(entries)})

            report = build_llm_trace_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "warn")
            self.assertFalse(report["blocking_issues"])
            self.assertEqual(report["ledger_summary"]["recovered_failed_calls"], 1)
            self.assertEqual(report["ledger_summary"]["recovered_budget_exceeded_calls"], 1)
            self.assertEqual(report["coverage"]["passed_required"], report["coverage"]["required_stages"])

    def test_blocks_ai_disclosure_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            _write_ledger(run_dir, _successful_entries())
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": False, "total_llm_calls": 0})

            report = build_llm_trace_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "block")
            self.assertTrue(any("used_ai=false" in item for item in report["blocking_issues"]))

    def test_warns_when_online_mode_lacks_llm_query_planning(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_stage_artifacts(run_dir)
            write_json(run_dir / "run-config.json", {"literature": {"provider": "online"}})
            _write_ledger(run_dir, _successful_entries())
            write_json(run_dir / "10-ai-disclosure.json", {"used_ai": True, "total_llm_calls": 8})

            report = build_llm_trace_audit_report("机械臂路径规划", run_dir)

            self.assertEqual(report["status"], "warn")
            self.assertTrue(any(item["stage"] == "online_search_query_planning" and item["status"] == "warn" for item in report["stage_checks"]))
            self.assertEqual(report["stage_gap_summary"]["warned_optional_stage_count"], 1)
            self.assertIn("online_search_query_planning", report["stage_gap_summary"]["warned_optional_stages"])


def _write_stage_artifacts(run_dir: Path) -> None:
    for name in [
        "00-research-plan.json",
        "01-literature.json",
        "01-literature-search-strategy.json",
        "02-ideas.json",
        "03-experiment-plan.json",
        "07-paper-review.json",
        "10-revised-paper-review.json",
    ]:
        write_json(run_dir / name, {"status": "pass"})
    for name in ["06-paper.md", "09-revised-paper.md"]:
        write_text(run_dir / name, "# Paper")


def _successful_entries() -> list[dict[str, str]]:
    return [
        {"purpose": "Research planning. You create domain profiles for scientific agents. Return only valid JSON in Chinese.", "status": "success"},
        {"purpose": "Literature synthesis. You are a scientific research assistant. Return only valid JSON in Chinese.", "status": "success"},
        {"purpose": "Research ideas. You generate testable scientific ideas. Return only valid JSON in Chinese.", "status": "success"},
        {"purpose": "Experiment planning. You design safe, reproducible scientific experiments. Return only valid JSON in Chinese.", "status": "success"},
        {"purpose": "Paper writing. You write concise Chinese academic Markdown. Use only provided evidence and experimental results.", "status": "success"},
        {"purpose": "Scientific peer review. You are a rigorous reviewer. Return only valid JSON in Chinese.", "status": "success"},
        {"purpose": "Paper revision. You revise Chinese academic Markdown without inventing evidence.", "status": "success"},
        {"purpose": "Scientific peer review. You are a rigorous reviewer. Return only valid JSON in Chinese.", "status": "success"},
    ]


def _successful_stage_entries() -> list[dict[str, str]]:
    return [
        {"stage": "research_planning", "purpose": "research planning", "status": "success"},
        {"stage": "literature_synthesis", "purpose": "literature synthesis", "status": "success"},
        {"stage": "idea_generation", "purpose": "research ideas", "status": "success"},
        {"stage": "experiment_planning", "purpose": "experiment planning", "status": "success"},
        {"stage": "paper_writing", "purpose": "paper writing", "status": "success"},
        {"stage": "paper_review_loop", "purpose": "scientific peer review", "status": "success"},
        {"stage": "paper_revision", "purpose": "paper revision", "status": "success"},
        {"stage": "paper_review_loop", "purpose": "scientific peer review", "status": "success"},
    ]


def _write_ledger(run_dir: Path, entries: list[dict[str, str]]) -> None:
    write_json(
        run_dir / "run-llm-ledger.json",
        {
            "total_calls": len(entries),
            "successful_calls": sum(1 for item in entries if item["status"] == "success"),
            "failed_calls": sum(1 for item in entries if item["status"] == "failed"),
            "budget_exceeded_calls": sum(1 for item in entries if item["status"] == "budget_exceeded"),
            "entries": entries,
        },
    )


if __name__ == "__main__":
    unittest.main()
