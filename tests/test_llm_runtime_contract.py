from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.artifacts import write_json
from research_agent.llm_runtime_contract import build_llm_runtime_contract_report, render_llm_runtime_contract_markdown, write_llm_runtime_contract_artifacts


class LlmRuntimeContractTest(unittest.TestCase):
    def test_passes_when_runtime_config_ledger_and_audits_are_consistent(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_good_runtime(run_dir)

            report = write_llm_runtime_contract_artifacts("机械臂路径规划", run_dir)
            rendered = render_llm_runtime_contract_markdown(report)

            self.assertTrue((run_dir / "13-llm-runtime-contract.json").exists())
            self.assertTrue((run_dir / "13-llm-runtime-contract.md").exists())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["total_calls"], 2)
        self.assertFalse(report["summary"]["api_key_persisted"])
        self.assertIn("LLM Runtime Contract", rendered)

    def test_blocks_missing_ledger(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_good_runtime(run_dir)
            (run_dir / "run-llm-ledger.json").unlink()

            report = build_llm_runtime_contract_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("run-llm-ledger.json" in item for item in report["blocking_issues"]))

    def test_blocks_api_key_persisted_in_run_config(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_good_runtime(run_dir)
            config = json.loads((run_dir / "run-config.json").read_text(encoding="utf-8"))
            config["llm"]["api_key"] = "sk-private"
            write_json(run_dir / "run-config.json", config)

            report = build_llm_runtime_contract_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("api_key" in item for item in report["blocking_issues"]))

    def test_blocks_full_prompt_or_response_text_in_ledger(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_good_runtime(run_dir)
            ledger = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            ledger["entries"][0]["raw_prompt"] = "private full prompt"
            write_json(run_dir / "run-llm-ledger.json", ledger)

            report = build_llm_runtime_contract_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "block")
        self.assertTrue(any("prompt/response" in item for item in report["blocking_issues"]))

    def test_treats_zero_budget_values_as_unlimited(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_good_runtime(run_dir)
            config = json.loads((run_dir / "run-config.json").read_text(encoding="utf-8"))
            config["llm"]["max_calls"] = 0
            config["llm"]["max_prompt_chars"] = 0
            write_json(run_dir / "run-config.json", config)

            report = build_llm_runtime_contract_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["summary"]["call_budget_configured"])
        self.assertTrue(report["summary"]["prompt_budget_configured"])
        self.assertFalse(report["manual_tasks"])
        self.assertFalse(report["warnings"])

    def test_requires_review_for_recovered_failed_ledger_calls(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_good_runtime(run_dir)
            ledger = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            ledger["entries"] = [
                {
                    "call_id": 1,
                    "stage": "paper_writing",
                    "purpose": "paper writing",
                    "provider": "openai-compatible",
                    "model": "good-model",
                    "base_url": "https://api.example.test/v1",
                    "status": "failed",
                    "system_chars": 100,
                    "user_chars": 100,
                    "response_chars": 0,
                    "duration_seconds": 0.1,
                },
                {
                    "call_id": 2,
                    "stage": "paper_writing",
                    "purpose": "paper writing",
                    "provider": "openai-compatible",
                    "model": "good-model",
                    "base_url": "https://api.example.test/v1",
                    "status": "success",
                    "system_chars": 100,
                    "user_chars": 100,
                    "response_chars": 100,
                    "duration_seconds": 0.5,
                    "system_sha256": "a" * 64,
                    "user_sha256": "b" * 64,
                    "response_sha256": "c" * 64,
                },
            ]
            ledger["total_calls"] = 2
            ledger["successful_calls"] = 1
            ledger["failed_calls"] = 1
            write_json(run_dir / "run-llm-ledger.json", ledger)

            report = build_llm_runtime_contract_report("机械臂路径规划", run_dir)

        self.assertEqual(report["status"], "review_required")
        self.assertFalse(report["blocking_issues"])
        self.assertTrue(any("同阶段 success 恢复" in item for item in report["warnings"]))


def _write_good_runtime(run_dir: Path) -> None:
    write_json(
        run_dir / "run-config.json",
        {
            "llm": {
                "provider": "openai-compatible",
                "base_url_env": "OPENAI_BASE_URL",
                "api_key_env": "OPENAI_API_KEY",
                "model_env": "OPENAI_MODEL",
                "base_url": "https://api.example.test/v1",
                "api_key": "",
                "model": "good-model",
                "max_calls": 10,
                "max_prompt_chars": 4000,
                "input_cost_per_million_tokens": 1.0,
                "output_cost_per_million_tokens": 2.0,
            }
        },
    )
    write_json(
        run_dir / "run-llm-ledger.json",
        {
            "total_calls": 2,
            "successful_calls": 2,
            "failed_calls": 0,
            "budget_exceeded_calls": 0,
            "total_prompt_chars": 400,
            "total_response_chars": 200,
            "entries": [
                {
                    "call_id": 1,
                    "purpose": "Research planning. You produce JSON.",
                    "provider": "openai-compatible",
                    "model": "good-model",
                    "base_url": "https://api.example.test/v1",
                    "status": "success",
                    "system_chars": 100,
                    "user_chars": 100,
                    "response_chars": 100,
                    "duration_seconds": 0.5,
                    "system_sha256": "a" * 64,
                    "user_sha256": "b" * 64,
                    "response_sha256": "c" * 64,
                },
                {
                    "call_id": 2,
                    "purpose": "Literature synthesis. You produce JSON.",
                    "provider": "openai-compatible",
                    "model": "good-model",
                    "base_url": "https://api.example.test/v1",
                    "status": "success",
                    "system_chars": 100,
                    "user_chars": 100,
                    "response_chars": 100,
                    "duration_seconds": 0.5,
                    "system_sha256": "d" * 64,
                    "user_sha256": "e" * 64,
                    "response_sha256": "f" * 64,
                },
            ],
        },
    )
    write_json(run_dir / "13-llm-trace-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "13-run-economics-audit.json", {"status": "pass", "blocking_issues": [], "manual_tasks": [], "warnings": []})
    write_json(run_dir / "10-ai-disclosure.json", {"status": "needs_human_policy_check", "used_ai": True, "total_llm_calls": 2})


if __name__ == "__main__":
    unittest.main()
