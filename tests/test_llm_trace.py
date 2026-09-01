from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest

from research_agent.config import LLMConfig
from research_agent.llm_trace import complete_with_purpose, trace_llm


class LLMTraceTest(unittest.TestCase):
    def test_traced_llm_records_success_without_prompt_text(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            llm = trace_llm(_FakeLLM("OK"), run_dir, LLMConfig(base_url="https://api.example.test/v1", model="fake-model"))

            result = llm.complete("System prompt", "User prompt")

            self.assertEqual(result, "OK")
            data = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            rendered = (run_dir / "run-llm-ledger.md").read_text(encoding="utf-8")
            self.assertEqual(data["total_calls"], 1)
            self.assertEqual(data["successful_calls"], 1)
            self.assertEqual(data["entries"][0]["model"], "fake-model")
            self.assertEqual(data["entries"][0]["status"], "success")
            self.assertEqual(data["entries"][0]["stage"], "")
            self.assertEqual(len(data["entries"][0]["user_sha256"]), 64)
            self.assertNotIn("User prompt", json.dumps(data, ensure_ascii=False))
            self.assertIn("LLM 调用账本", rendered)

    def test_traced_llm_records_explicit_stage_and_purpose_without_prompt_text(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            llm = trace_llm(_FakeLLM("OK"), run_dir, LLMConfig(base_url="https://api.example.test/v1", model="fake-model"))

            result = complete_with_purpose(
                llm,
                "Private system prompt",
                "Private user prompt",
                stage="paper_writing",
                purpose="paper writing",
            )

            self.assertEqual(result, "OK")
            data = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            rendered = (run_dir / "run-llm-ledger.md").read_text(encoding="utf-8")
            encoded = json.dumps(data, ensure_ascii=False)
            self.assertEqual(data["entries"][0]["stage"], "paper_writing")
            self.assertEqual(data["entries"][0]["purpose"], "paper writing")
            self.assertNotIn("Private user prompt", encoded)
            self.assertNotIn("Private system prompt", encoded)
            self.assertIn("paper_writing", rendered)

    def test_traced_llm_records_runtime_model_and_base_url_from_inner_llm(self) -> None:
        old_model = os.environ.get("OPENAI_MODEL")
        old_base = os.environ.get("OPENAI_BASE_URL")
        os.environ["OPENAI_MODEL"] = "env-model"
        os.environ["OPENAI_BASE_URL"] = "https://env.example.test/v1"
        try:
            with TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                llm = trace_llm(_RuntimeLLM("OK"), run_dir, LLMConfig())

                llm.complete("System prompt", "User prompt")

                data = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
        finally:
            if old_model is None:
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = old_model
            if old_base is None:
                os.environ.pop("OPENAI_BASE_URL", None)
            else:
                os.environ["OPENAI_BASE_URL"] = old_base

        self.assertEqual(data["entries"][0]["model"], "runtime-model")
        self.assertEqual(data["entries"][0]["base_url"], "https://runtime.example.test/v1")

    def test_traced_llm_records_failure_and_reraises(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            llm = trace_llm(_FailingLLM(), run_dir, LLMConfig(model="fake-model"))

            with self.assertRaises(RuntimeError):
                llm.complete("System", "User")

            data = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(data["failed_calls"], 1)
            self.assertEqual(data["entries"][0]["status"], "failed")
            self.assertIn("boom", data["entries"][0]["error"])

    def test_traced_llm_blocks_when_max_calls_is_exhausted(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            inner = _FakeLLM("OK")
            llm = trace_llm(inner, run_dir, LLMConfig(model="fake-model", max_calls=1))

            self.assertEqual(llm.complete("System", "User"), "OK")
            with self.assertRaisesRegex(RuntimeError, "max_calls=1"):
                llm.complete("System 2", "User 2")

            data = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(inner.calls, 1)
            self.assertEqual(data["total_calls"], 2)
            self.assertEqual(data["successful_calls"], 1)
            self.assertEqual(data["failed_calls"], 0)
            self.assertEqual(data["budget_exceeded_calls"], 1)
            self.assertEqual(data["entries"][1]["status"], "budget_exceeded")
            self.assertIn("max_calls=1", data["entries"][1]["error"])

    def test_traced_llm_blocks_prompt_budget_before_calling_inner_llm(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            inner = _FakeLLM("OK")
            llm = trace_llm(inner, run_dir, LLMConfig(model="fake-model", max_prompt_chars=10))

            with self.assertRaisesRegex(RuntimeError, "max_prompt_chars=10"):
                llm.complete("Budget guard", "abcde")

            data = json.loads((run_dir / "run-llm-ledger.json").read_text(encoding="utf-8"))
            encoded = json.dumps(data, ensure_ascii=False)
            self.assertEqual(inner.calls, 0)
            self.assertEqual(data["budget_exceeded_calls"], 1)
            self.assertEqual(data["entries"][0]["status"], "budget_exceeded")
            self.assertNotIn("abcde", encoded)


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.response


class _FailingLLM:
    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("boom")


class _RuntimeLLM(_FakeLLM):
    model = "runtime-model"
    base_url = "https://runtime.example.test/v1"


if __name__ == "__main__":
    unittest.main()
