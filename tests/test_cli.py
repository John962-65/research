from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import contextlib
import io
import os
import subprocess
import sys
import unittest

import research_agent.cli as cli_module
from research_agent.cli import _apply_gold_defaults_to_args, _apply_run_overrides, _load_resume_base_config
from research_agent.config import AgentConfig, HumanConfig, LiteratureConfig


_GOLD_SERVER_ENV_KEYS = {
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_API_KEY",
    "RESEARCH_AGENT_CONTACT_EMAIL",
    "SEMANTIC_SCHOLAR_API_KEY",
    "OPENALEX_API_KEY",
}


def _env_without_gold_server_values() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in _GOLD_SERVER_ENV_KEYS}


class CliTest(unittest.TestCase):
    def test_resume_without_explicit_config_loads_run_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            snapshot = (
                '{"literature":{"provider":"online","max_papers":17},'
                '"execution":{"mode":"benchmark","repeats":9},'
                '"paper_grade":{"enabled":true}}'
            )
            (run_dir / "run-config.json").write_text(snapshot, encoding="utf-8")

            config = _load_resume_base_config(run_dir, None)

        self.assertEqual(config.literature.provider, "online")
        self.assertEqual(config.literature.max_papers, 17)
        self.assertEqual(config.execution.mode, "benchmark")
        self.assertEqual(config.execution.repeats, 9)
        self.assertTrue(config.paper_grade.enabled)

    def test_resume_rejects_corrupt_run_snapshot(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "run-config.json").write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid run config snapshot"):
                _load_resume_base_config(run_dir, None)

    def test_literature_search_overrides_append_manual_queries(self) -> None:
        with TemporaryDirectory() as tmp:
            query_file = Path(tmp) / "queries.txt"
            query_file.write_text("RRT* CHOMP robot arm\n\nTrajOpt manipulation planning\n", encoding="utf-8")
            config = AgentConfig(literature=LiteratureConfig(extra_search_queries=["configured query"], max_search_queries=4))

            updated = _apply_run_overrides(
                config,
                _run_args(
                    max_search_queries=7,
                    extra_search_query=["robot manipulator OMPL benchmark", " "],
                    extra_search_queries_file=query_file,
                ),
            )

        self.assertEqual(updated.literature.max_search_queries, 7)
        self.assertEqual(
            updated.literature.extra_search_queries,
            [
                "configured query",
                "robot manipulator OMPL benchmark",
                "RRT* CHOMP robot arm",
                "TrajOpt manipulation planning",
            ],
        )

    def test_literature_search_flags_are_available_on_run_commands(self) -> None:
        for command in ["run", "preflight", "resume", "repair-resume"]:
            with self.subTest(command=command):
                completed = subprocess.run(
                    [sys.executable, "-m", "research_agent.cli", command, "--help"],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(completed.returncode, 0)
                self.assertIn("--max-search-queries", completed.stdout)
                self.assertIn("--extra-search-query", completed.stdout)
                self.assertIn("--extra-search-queries-file", completed.stdout)
                if command == "repair-resume":
                    self.assertIn("--apply", completed.stdout)

    def test_status_awaiting_review_approval_prints_approve_next_action_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "gate-run"
            run_dir.mkdir()
            state_text = '{"topic":"Iris","stage":"awaiting_review_approval"}'
            (run_dir / "state.json").write_text(state_text, encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                cli_module.main(["status", str(run_dir)])

            output = stdout.getvalue()

        self.assertIn(state_text, output)
        self.assertIn("Next action: approve the literature review gate", output)
        self.assertIn("research_agent approve ", output)
        self.assertIn(str(run_dir), output)
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)

    def test_status_awaiting_execution_approval_prints_execution_next_action_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "execution-run"
            run_dir.mkdir()
            state_text = '{"topic":"Iris","stage":"awaiting_execution_approval"}'
            (run_dir / "state.json").write_text(state_text, encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                cli_module.main(["status", str(run_dir)])

            output = stdout.getvalue()

        self.assertIn(state_text, output)
        self.assertIn("Next action: approve benchmark/local execution", output)
        self.assertIn("research_agent approve-execution", output)
        self.assertIn(str(run_dir), output)
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)

    def test_status_repair_resume_applied_prints_repair_resume_next_action_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "repair-run"
            run_dir.mkdir()
            state_text = '{"topic":"Iris","stage":"repair_resume_applied"}'
            (run_dir / "state.json").write_text(state_text, encoding="utf-8")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                cli_module.main(["status", str(run_dir)])

            output = stdout.getvalue()

        self.assertIn(state_text, output)
        self.assertIn("Next action: rerun repair-resume", output)
        self.assertIn("research_agent repair-resume", output)
        self.assertIn("--apply", output)
        self.assertIn(str(run_dir), output)
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)

    def test_paper_grade_probe_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "paper-grade-probe", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--query", completed.stdout)
        self.assertIn("--seed-paper", completed.stdout)
        self.assertIn("--literature-sources", completed.stdout)
        self.assertNotIn("--semantic-scholar-api-key", completed.stdout)
        self.assertNotIn("--openalex-api-key", completed.stdout)

    def test_paper_grade_probe_rejects_cli_secret_arguments_without_echoing_values(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "paper-grade-probe",
                "--topic",
                "secret probe smoke",
                "--openalex-api-key",
                "unit-test-openalex-secret",
                "--no-write",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("do not pass secret values via CLI arguments", completed.stderr)
        self.assertIn("--openalex-api-key", completed.stderr)
        self.assertNotIn("unit-test-openalex-secret", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_paper_grade_run_rejects_cli_secret_arguments_without_echoing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "run",
                    "--topic",
                    "secret run smoke",
                    "--out",
                    str(Path(tmp) / "run"),
                    "--paper-grade",
                    "--llm-api-key",
                    "unit-test-run-secret",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("paper-grade runs require env-only secret handling", completed.stderr)
        self.assertIn("--llm-api-key", completed.stderr)
        self.assertNotIn("unit-test-run-secret", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_paper_grade_preflight_config_rejects_cli_secret_arguments_without_echoing_values(self) -> None:
        with TemporaryDirectory() as tmp:
            config = Path(tmp) / "paper-grade.toml"
            config.write_text("[paper_grade]\nenabled = true\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "preflight",
                    "--topic",
                    "secret preflight smoke",
                    "--config",
                    str(config),
                    "--no-llm-ping",
                    "--semantic-scholar-api-key",
                    "unit-test-preflight-secret",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("paper-grade runs require env-only secret handling", completed.stderr)
        self.assertIn("--semantic-scholar-api-key", completed.stderr)
        self.assertNotIn("unit-test-preflight-secret", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_benchmark_manifest_build_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "benchmark-manifest-build", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--split-file", completed.stdout)
        self.assertIn("--grader-file", completed.stdout)
        self.assertIn("--metric", completed.stdout)
        self.assertIn("--role-command", completed.stdout)

    def test_benchmark_pack_run_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "benchmark-pack-run", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--benchmark-manifest", completed.stdout)
        self.assertIn("--execution-repeats", completed.stdout)
        self.assertIn("--allowed-command", completed.stdout)

    def test_fulltext_grounding_run_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "fulltext-grounding-run", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--fulltext-path", completed.stdout)
        self.assertIn("--claim", completed.stdout)
        self.assertIn("--out", completed.stdout)

    def test_gold_env_launch_kit_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "gold-env-launch-kit", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--config", completed.stdout)
        self.assertIn("--llm-base-url", completed.stdout)
        self.assertIn("--llm-model", completed.stdout)
        self.assertIn("--literature-contact-email", completed.stdout)
        self.assertNotIn("--llm-api-key", completed.stdout)
        self.assertNotIn("--semantic-scholar-api-key", completed.stdout)
        self.assertNotIn("--openalex-api-key", completed.stdout)

    def test_gold_env_launch_kit_cli_prints_safe_placeholder_commands(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-env-launch-kit",
                "--llm-base-url",
                "http://127.0.0.1:8317",
                "--llm-model",
                "gpt-5.5",
                "--literature-contact-email",
                "lab@university.edu",
            ],
            text=True,
            capture_output=True,
            check=False,
            env=_env_without_gold_server_values(),
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Gold Env Launch Kit", completed.stdout)
        self.assertIn("scripts/start_gold_web_env.sh", completed.stdout)
        self.assertIn("scripts/run_gold_cli_env.sh", completed.stdout)
        self.assertIn("RESEARCH_AGENT_GOLD_DRY_RUN=1", completed.stdout)
        self.assertIn("socket_before_secret", completed.stdout)
        self.assertIn("RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK=1", completed.stdout)
        self.assertIn("read -rsp", completed.stdout)
        self.assertLess(
            completed.stdout.index("export RESEARCH_AGENT_CONTACT_EMAIL='<your-real-contact-email>'"),
            completed.stdout.index("read -rsp 'OPENAI_API_KEY: ' OPENAI_API_KEY; export OPENAI_API_KEY; echo"),
        )
        self.assertIn("RESEARCH_AGENT_WEB_REPLACE=1", completed.stdout)
        self.assertIn("prompt_before_secret", completed.stdout)
        self.assertIn("http://127.0.0.1:8317", completed.stdout)
        self.assertIn("gpt-5.5", completed.stdout)
        self.assertIn("服务端环境：`needs_server_environment`；必填 0/4", completed.stdout)
        self.assertIn("缺失必填环境：OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_API_KEY, RESEARCH_AGENT_CONTACT_EMAIL", completed.stdout)
        self.assertIn("Gateway socket：", completed.stdout)
        self.assertIn("target=`http://127.0.0.1:8317`", completed.stdout)
        self.assertIn("Post-Launch Human Gates", completed.stdout)
        self.assertIn("research_agent status runs/iris-classification-benchmark-smoke-gold-run", completed.stdout)
        self.assertIn("research_agent approve runs/iris-classification-benchmark-smoke-gold-run", completed.stdout)
        self.assertIn("research_agent approve-execution runs/iris-classification-benchmark-smoke-gold-run", completed.stdout)
        self.assertIn("--release-code-repository-url", completed.stdout)
        self.assertIn("--release-code-archive-doi", completed.stdout)
        self.assertIn("research-agent-lab/research-agent", completed.stdout)
        self.assertNotIn("paper-grade-scaffold", completed.stdout)
        self.assertNotIn("lab@university.edu", completed.stdout)
        self.assertNotIn("sk-", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_gold_env_launch_kit_rejects_cli_secret_arguments_without_echoing_values(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-env-launch-kit",
                "--llm-api-key",
                "unit-test-launch-kit-secret",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("do not pass secret values via CLI arguments", completed.stderr)
        self.assertIn("--llm-api-key", completed.stderr)
        self.assertNotIn("unit-test-launch-kit-secret", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_gold_defaults_smoke_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "gold-defaults-smoke", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--topic", completed.stdout)
        self.assertIn("--project-dir", completed.stdout)
        self.assertNotIn("--llm-api-key", completed.stdout)
        self.assertNotIn("--semantic-scholar-api-key", completed.stdout)
        self.assertNotIn("--openalex-api-key", completed.stdout)

    def test_gold_defaults_smoke_cli_reports_server_env_and_gateway_summary_without_secrets(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-defaults-smoke",
                "--topic",
                "Iris classification benchmark smoke",
                "--project-dir",
                str(Path.cwd()),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=_env_without_gold_server_values(),
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Gold Defaults Smoke", completed.stdout)
        self.assertIn("状态：ready_except_server_environment", completed.stdout)
        self.assertIn("主要阻断：server_environment", completed.stdout)
        self.assertIn("服务端环境：`needs_server_environment`；必填 0/4", completed.stdout)
        self.assertIn("缺失必填环境：OPENAI_BASE_URL, OPENAI_MODEL, RESEARCH_AGENT_CONTACT_EMAIL, <secret-env>", completed.stdout)
        self.assertIn("Gateway socket：", completed.stdout)
        self.assertIn("target=`http://127.0.0.1:8317`", completed.stdout)
        self.assertIn("server_env=0/4", completed.stdout)
        self.assertIn("Gold run output：`runs/iris-classification-benchmark-smoke-gold-run`", completed.stdout)
        self.assertIn("RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh", completed.stdout)
        self.assertIn("scripts/run_gold_cli_env.sh", completed.stdout)
        self.assertIn("Post-Launch Human Gates", completed.stdout)
        self.assertIn("research_agent status runs/iris-classification-benchmark-smoke-gold-run", completed.stdout)
        self.assertIn("research_agent approve-execution runs/iris-classification-benchmark-smoke-gold-run", completed.stdout)
        self.assertIn("Final Verification", completed.stdout)
        self.assertIn("research_agent gold-run-verify --run-dir runs/iris-classification-benchmark-smoke-gold-run", completed.stdout)
        self.assertIn("research_agent perfect-readiness --project-dir . --runs-dir runs --no-write", completed.stdout)
        self.assertNotIn("sk-", completed.stdout)
        self.assertNotIn("researcher@university.edu", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_gold_cli_env_script_aborts_before_secret_when_output_exists(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "existing"
            out_dir.mkdir()
            suggested_out = Path(f"{out_dir}-2")
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"}
            }
            env["RESEARCH_AGENT_GOLD_OUT"] = str(out_dir)
            env["RESEARCH_AGENT_GOLD_REUSE_OUT"] = "1"
            completed = subprocess.run(
                ["scripts/run_gold_cli_env.sh"],
                cwd=root,
                text=True,
                input="",
                capture_output=True,
                check=False,
                env=env,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Aborted before reading OPENAI_API_KEY", completed.stderr)
        self.assertIn("never reuse an existing run directory", completed.stderr)
        self.assertIn(f"Suggested fresh RESEARCH_AGENT_GOLD_OUT: {suggested_out}", completed.stderr)
        self.assertIn(f"RESEARCH_AGENT_GOLD_OUT={suggested_out}", completed.stderr)
        self.assertNotIn("OPENAI_API_KEY:", completed.stderr)
        self.assertNotIn("sk-", completed.stdout + completed.stderr)

    def test_gold_cli_env_script_aborts_before_secret_when_gateway_is_unreachable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"OPENAI_API_KEY", "RESEARCH_AGENT_CONTACT_EMAIL"}
            }
            env["OPENAI_BASE_URL"] = "http://127.0.0.1:1"
            env["RESEARCH_AGENT_GOLD_OUT"] = str(Path(tmp) / "new-run")
            completed = subprocess.run(
                ["scripts/run_gold_cli_env.sh"],
                cwd=root,
                text=True,
                input="",
                capture_output=True,
                check=False,
                env=env,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("not reachable before reading OPENAI_API_KEY", completed.stderr)
        self.assertIn("RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK=1", completed.stderr)
        self.assertNotIn("OPENAI_API_KEY:", completed.stderr)
        self.assertNotIn("sk-", completed.stdout + completed.stderr)

    def test_gold_cli_env_script_runs_final_audits_when_launch_returns_blocked(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out_dir = tmp_path / "blocked-run"
            log_path = tmp_path / "python-calls.log"
            mock_bin = tmp_path / "bin"
            mock_bin.mkdir()
            mock_python = mock_bin / "python3"
            mock_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$RESEARCH_AGENT_TEST_PYTHON_LOG"
if [[ "${1:-}" == "-" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "research_agent" ]]; then
  cmd="${3:-}"
  case "$cmd" in
    gold-run-launch)
      for ((i = 1; i <= $#; i++)); do
        if [[ "${!i}" == "--out" ]]; then
          next=$((i + 1))
          mkdir -p "${!next}"
        fi
      done
      exit 2
      ;;
    gold-run-verify)
      mkdir -p "$RESEARCH_AGENT_TEST_GOLD_OUT"
      printf '{"status":"blocked","repair_plan":[{"id":"submission_package","rerun_from":"submission_package","target_artifacts":["11-submission-package.json"],"action":"repair package"}]}' > "$RESEARCH_AGENT_TEST_GOLD_OUT/15-gold-run-verification.json"
      exit 2
      ;;
    perfect-readiness)
      exit 0
      ;;
    *)
      exit 0
      ;;
  esac
fi
exit 0
""",
                encoding="utf-8",
            )
            mock_python.chmod(0o755)
            env = _env_without_gold_server_values()
            env.update(
                {
                    "PATH": f"{mock_bin}{os.pathsep}{env.get('PATH', '')}",
                    "RESEARCH_AGENT_PYTHON_BIN": str(mock_python),
                    "RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK": "1",
                    "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
                    "OPENAI_API_KEY": "unit-test-token",
                    "RESEARCH_AGENT_GOLD_CONFIRM": "1",
                    "RESEARCH_AGENT_GOLD_OUT": str(out_dir),
                    "RESEARCH_AGENT_TEST_GOLD_OUT": str(out_dir),
                    "RESEARCH_AGENT_TEST_PYTHON_LOG": str(log_path),
                }
            )
            completed = subprocess.run(
                ["scripts/run_gold_cli_env.sh"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            calls = log_path.read_text(encoding="utf-8")
            out_dir_exists = out_dir.is_dir()

        self.assertEqual(completed.returncode, 2)
        self.assertTrue(out_dir_exists)
        self.assertIn("research_agent gold-run-launch", calls)
        self.assertIn("research_agent gold-run-verify --run-dir", calls)
        self.assertIn("research_agent perfect-readiness --project-dir . --runs-dir", calls)
        self.assertIn("research_agent repair-resume", calls)
        self.assertIn("--gold-run-verification-report", calls)
        self.assertLess(calls.index("research_agent gold-run-launch"), calls.index("research_agent gold-run-verify --run-dir"))
        self.assertLess(calls.index("research_agent gold-run-verify --run-dir"), calls.index("research_agent perfect-readiness --project-dir . --runs-dir"))
        self.assertLess(calls.index("research_agent perfect-readiness --project-dir . --runs-dir"), calls.index("research_agent repair-resume"))
        self.assertNotIn("sk-", completed.stdout + completed.stderr + calls)

    def test_gold_cli_env_script_reads_openai_key_from_fifo(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fifo = tmp_path / "openai-key.fifo"
            os.mkfifo(fifo, 0o600)
            fifo.chmod(0o600)
            log_path = tmp_path / "python-calls.log"
            mock_bin = tmp_path / "bin"
            mock_bin.mkdir()
            mock_python = mock_bin / "python3"
            mock_python.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-" ]]; then
  exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "research_agent" ]]; then
  printf '%s key=%s\\n' "$*" "${OPENAI_API_KEY:+set}" >> "$RESEARCH_AGENT_TEST_PYTHON_LOG"
fi
exit 0
""",
                encoding="utf-8",
            )
            mock_python.chmod(0o755)
            env = _env_without_gold_server_values()
            env.update(
                {
                    "PATH": f"{mock_bin}{os.pathsep}{env.get('PATH', '')}",
                    "RESEARCH_AGENT_PYTHON_BIN": str(mock_python),
                    "RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK": "1",
                    "RESEARCH_AGENT_GOLD_DRY_RUN": "1",
                    "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
                    "RESEARCH_AGENT_OPENAI_API_KEY_FIFO": str(fifo),
                    "RESEARCH_AGENT_TEST_PYTHON_LOG": str(log_path),
                }
            )
            completed = subprocess.run(
                [
                    "bash",
                    "-lc",
                    'printf "%s\\n" unit-test-token > "$RESEARCH_AGENT_OPENAI_API_KEY_FIFO" & scripts/run_gold_cli_env.sh',
                ],
                cwd=root,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                check=False,
                env=env,
                timeout=10,
            )
            calls = log_path.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Reading OPENAI_API_KEY from FIFO specified by RESEARCH_AGENT_OPENAI_API_KEY_FIFO", completed.stderr)
        self.assertIn("research_agent gold-run-doctor", calls)
        self.assertIn("research_agent gold-launch-bundle", calls)
        self.assertIn("research_agent gold-run-launch", calls)
        self.assertIn("key=set", calls)
        self.assertNotIn("unit-test-token", completed.stdout + completed.stderr + calls)
        self.assertNotIn("OPENAI_API_KEY:", completed.stderr)
        self.assertNotIn("sk-", completed.stdout + completed.stderr + calls)

    def test_gold_run_doctor_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "gold-run-doctor", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--benchmark-pack-run-dir", completed.stdout)
        self.assertIn("--fulltext-grounding-run-dir", completed.stdout)
        self.assertIn("--candidate-run-dir", completed.stdout)
        self.assertIn("--llm-base-url", completed.stdout)
        self.assertIn("--literature-contact-email", completed.stdout)
        self.assertIn("--literature-provider", completed.stdout)
        self.assertIn("--seed-paper", completed.stdout)
        self.assertIn("--benchmark-manifest", completed.stdout)
        self.assertIn("--paper-grade", completed.stdout)
        self.assertIn("--release-code-archive-doi", completed.stdout)
        self.assertIn("--gold-defaults", completed.stdout)
        self.assertIn("--ping-llm", completed.stdout)
        self.assertIn("--no-write", completed.stdout)
        self.assertIn("--write-candidate-repair-resume-plan", completed.stdout)
        self.assertNotIn("--llm-api-key", completed.stdout)
        self.assertNotIn("--semantic-scholar-api-key", completed.stdout)
        self.assertNotIn("--openalex-api-key", completed.stdout)

    def test_gold_run_doctor_rejects_cli_secret_arguments(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-run-doctor",
                "--topic",
                "secret argument smoke",
                "--llm-api-key",
                "unit-test-api-token",
                "--no-write",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("do not pass secret values via CLI arguments", completed.stderr)
        self.assertIn("--llm-api-key", completed.stderr)
        self.assertNotIn("unit-test-api-token", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_gold_launch_bundle_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "gold-launch-bundle", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--project-dir", completed.stdout)
        self.assertIn("--benchmark-pack-run-dir", completed.stdout)
        self.assertIn("--fulltext-grounding-run-dir", completed.stdout)
        self.assertIn("--candidate-run-dir", completed.stdout)
        self.assertIn("--literature-provider", completed.stdout)
        self.assertIn("--seed-paper", completed.stdout)
        self.assertIn("--benchmark-manifest", completed.stdout)
        self.assertIn("--paper-grade", completed.stdout)
        self.assertIn("--release-code-archive-doi", completed.stdout)
        self.assertIn("--gold-defaults", completed.stdout)
        self.assertIn("--no-write", completed.stdout)
        self.assertNotIn("--llm-api-key", completed.stdout)
        self.assertNotIn("--semantic-scholar-api-key", completed.stdout)
        self.assertNotIn("--openalex-api-key", completed.stdout)

    def test_gold_launch_bundle_rejects_cli_secret_arguments_without_echoing_values(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-launch-bundle",
                "--topic",
                "secret bundle smoke",
                "--semantic-scholar-api-key",
                "unit-test-semantic-secret",
                "--no-write",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("do not pass secret values via CLI arguments", completed.stderr)
        self.assertIn("--semantic-scholar-api-key", completed.stderr)
        self.assertNotIn("unit-test-semantic-secret", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_gold_launch_bundle_cli_exits_nonzero_when_not_ready_to_start(self) -> None:
        bundle = {
            "schema_version": 1,
            "topic": "needs review bundle",
            "status": "needs_review",
            "can_start_gold_run": False,
            "components": [],
            "launch_plan": {"status": "blocked", "ready_to_execute_commands": False},
            "read_only": True,
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(cli_module, "build_gold_launch_bundle_report", return_value=bundle),
            patch.object(cli_module, "render_gold_launch_bundle_markdown", return_value="# Gold Launch Bundle\n\nneeds review"),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            cli_module.main(["gold-launch-bundle", "--topic", "needs review bundle", "--no-write"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("needs review", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_gold_launch_bundle_cli_allows_ready_to_start(self) -> None:
        bundle = {
            "schema_version": 1,
            "topic": "ready bundle",
            "status": "ready_to_start",
            "can_start_gold_run": True,
            "components": [],
            "launch_plan": {"status": "ready_to_start", "ready_to_execute_commands": True},
            "read_only": True,
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(cli_module, "build_gold_launch_bundle_report", return_value=bundle),
            patch.object(cli_module, "render_gold_launch_bundle_markdown", return_value="# Gold Launch Bundle\n\nready"),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            cli_module.main(["gold-launch-bundle", "--topic", "ready bundle", "--no-write"])

        self.assertIn("ready", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_gold_run_launch_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "gold-run-launch", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--project-dir", completed.stdout)
        self.assertIn("--benchmark-pack-run-dir", completed.stdout)
        self.assertIn("--fulltext-grounding-run-dir", completed.stdout)
        self.assertIn("--literature-provider", completed.stdout)
        self.assertIn("--seed-paper", completed.stdout)
        self.assertIn("--benchmark-manifest", completed.stdout)
        self.assertIn("--release-code-archive-doi", completed.stdout)
        self.assertIn("--gold-defaults", completed.stdout)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--out", completed.stdout)
        self.assertNotIn("--llm-api-key", completed.stdout)
        self.assertNotIn("--semantic-scholar-api-key", completed.stdout)
        self.assertNotIn("--openalex-api-key", completed.stdout)
        self.assertNotIn("--paper-grade", completed.stdout)

    def test_gold_defaults_populate_local_gold_launch_inputs_without_secrets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        args = SimpleNamespace(
            command="gold-run-launch",
            gold_defaults=True,
            project_dir=root,
            config=None,
            benchmark_pack_run_dir=None,
            fulltext_grounding_run_dir=None,
            paper_grade=False,
            release_code_repository_url=None,
            release_code_archive_doi=None,
            release_code_license=None,
            release_code_version=None,
            release_data_repository_url=None,
            release_data_archive_doi=None,
            release_data_access_statement=None,
            release_environment_url=None,
            release_notes=None,
        )

        _apply_gold_defaults_to_args(args)
        encoded = repr(args)

        self.assertEqual(args.config, root / "examples" / "uci-iris-paper-grade-config.toml")
        self.assertEqual(args.benchmark_pack_run_dir, root / "runs" / "uci-iris-expanded-baseline-pack-run")
        self.assertEqual(args.fulltext_grounding_run_dir, root / "runs" / "uci-iris-fulltext-grounding")
        self.assertTrue(args.paper_grade)
        self.assertEqual(args.release_code_license, "MIT")
        self.assertIn("research-agent-lab/research-agent", args.release_code_repository_url)
        self.assertIn("UCI Machine Learning Repository", args.release_data_access_statement)
        self.assertNotIn("sk-", encoded)
        self.assertNotIn("api_key", encoded.lower())

    def test_gold_run_launch_rejects_cli_secret_arguments_without_echoing_values(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-run-launch",
                "--topic",
                "secret launch smoke",
                "--llm-api-key",
                "unit-test-launch-secret",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("do not pass secret values via CLI arguments", completed.stderr)
        self.assertIn("--llm-api-key", completed.stderr)
        self.assertNotIn("unit-test-launch-secret", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_gold_run_launch_rejects_existing_output_directory_before_bundle_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "existing-gold-run"
            out_dir.mkdir()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-launch",
                    "--topic",
                    "existing output smoke",
                    "--gold-defaults",
                    "--out",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=_env_without_gold_server_values(),
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Output path already exists", completed.stderr)
        self.assertIn("fresh --out directory", completed.stderr)
        self.assertNotIn("OPENAI_API_KEY", completed.stderr)
        self.assertNotIn("sk-", completed.stderr)

    def test_gold_run_launch_blocks_before_creating_output_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "gold-run"
            env = {
                **os.environ,
                "OPENAI_BASE_URL": "http://127.0.0.1:8317",
                "OPENAI_MODEL": "gpt-5.5",
                "OPENAI_API_KEY": "unit-test-api-token",
                "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
            }
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-launch",
                    "--topic",
                    "blocked gold launch smoke",
                    "--project-dir",
                    str(Path.cwd()),
                    "--literature-provider",
                    "offline",
                    "--out",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            exists = out_dir.exists()

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Gold Launch Bundle", completed.stdout)
        self.assertIn("可启动 gold run：否", completed.stdout)
        self.assertFalse(exists)
        self.assertNotIn("unit-test-api-token", completed.stdout)
        self.assertNotIn("researcher@university.edu", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_gold_run_launch_dry_run_gold_defaults_reports_env_summary_without_output_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "gold-dry-run"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-launch",
                    "--topic",
                    "Iris classification benchmark smoke",
                    "--project-dir",
                    str(Path.cwd()),
                    "--gold-defaults",
                    "--dry-run",
                    "--out",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=_env_without_gold_server_values(),
            )

            exists = out_dir.exists()

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Gold Launch Bundle", completed.stdout)
        self.assertIn("可启动 gold run：否", completed.stdout)
        self.assertIn("主要阻断：server_environment", completed.stdout)
        self.assertIn("服务端环境：`needs_server_environment`；必填 0/4", completed.stdout)
        self.assertIn("Gateway socket：", completed.stdout)
        self.assertIn("target=`http://127.0.0.1:8317`", completed.stdout)
        self.assertIn("server_env=0/4", completed.stdout)
        self.assertNotIn("Gold launch gate ready", completed.stdout)
        self.assertFalse(exists)
        self.assertNotIn("sk-", completed.stdout)
        self.assertNotIn("OPENAI_API_KEY", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_gold_run_launch_ready_dry_run_prints_start_gate_and_verify_guidance_without_output_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "ready-gold-dry-run"
            ready_bundle = {
                "schema_version": 1,
                "topic": "ready dry run",
                "status": "ready_to_start",
                "can_start_gold_run": True,
                "components": [],
                "launch_plan": {"status": "ready_to_start", "ready_to_execute_commands": True},
                "read_only": True,
            }
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(cli_module, "build_gold_launch_bundle_report", return_value=ready_bundle),
                patch.object(cli_module, "render_gold_launch_bundle_markdown", return_value="# Gold Launch Bundle\n\nready"),
                patch.object(cli_module, "run_pipeline") as run_pipeline,
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                cli_module.main(
                    [
                        "gold-run-launch",
                        "--topic",
                        "ready dry run",
                        "--project-dir",
                        str(Path.cwd()),
                        "--seed-paper",
                        "https://doi.org/10.1234/example",
                        "--dry-run",
                        "--out",
                        str(out_dir),
                    ]
                )

            output = stdout.getvalue()
            exists = out_dir.exists()

        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Gold launch gate ready; dry run requested, pipeline not started.", output)
        self.assertIn("Start this gold run with:", output)
        self.assertIn("research_agent gold-run-launch", output)
        self.assertIn("--seed-paper https://doi.org/10.1234/example", output)
        self.assertIn(f"--out {out_dir}", output)
        self.assertIn("research_agent status", output)
        self.assertIn("research_agent approve ", output)
        self.assertIn("research_agent approve-execution", output)
        self.assertIn("research_agent gold-run-verify", output)
        self.assertIn("research_agent perfect-readiness", output)
        self.assertNotIn("--dry-run", output)
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)
        self.assertFalse(exists)
        run_pipeline.assert_not_called()

    def test_gold_run_launch_ready_dry_run_suggests_fresh_output_when_selected_output_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "existing-ready-gold-dry-run"
            out_dir.mkdir()
            suggested_out = Path(f"{out_dir}-2")
            ready_bundle = {
                "schema_version": 1,
                "topic": "ready dry run existing out",
                "status": "ready_to_start",
                "can_start_gold_run": True,
                "components": [],
                "launch_plan": {"status": "ready_to_start", "ready_to_execute_commands": True},
                "read_only": True,
            }
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(cli_module, "build_gold_launch_bundle_report", return_value=ready_bundle),
                patch.object(cli_module, "render_gold_launch_bundle_markdown", return_value="# Gold Launch Bundle\n\nready"),
                patch.object(cli_module, "run_pipeline") as run_pipeline,
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                cli_module.main(
                    [
                        "gold-run-launch",
                        "--topic",
                        "ready dry run existing out",
                        "--dry-run",
                        "--out",
                        str(out_dir),
                    ]
                )

            output = stdout.getvalue()
            selected_out_still_exists = out_dir.exists()
            suggested_out_exists = suggested_out.exists()

        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Selected --out already exists", output)
        self.assertIn("non-dry-run gold launches require a fresh output directory", output)
        self.assertIn(f"Suggested fresh --out: {suggested_out}", output)
        self.assertIn(f"--out {suggested_out}", output)
        self.assertIn(f"research_agent status {suggested_out}", output)
        self.assertIn(f"research_agent gold-run-verify --run-dir {suggested_out}", output)
        self.assertTrue(selected_out_still_exists)
        self.assertFalse(suggested_out_exists)
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)
        run_pipeline.assert_not_called()

    def test_gold_run_launch_ready_path_prints_human_gate_runtime_guidance(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "ready-gold-run"
            ready_bundle = {
                "schema_version": 1,
                "topic": "ready gold",
                "status": "ready_to_start",
                "can_start_gold_run": True,
                "components": [],
                "launch_plan": {"status": "ready_to_start", "ready_to_execute_commands": True},
                "read_only": True,
            }
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(cli_module, "build_gold_launch_bundle_report", return_value=ready_bundle),
                patch.object(cli_module, "render_gold_launch_bundle_markdown", return_value="# Gold Launch Bundle\n\nready"),
                patch.object(cli_module, "run_pipeline", return_value=out_dir),
                patch.object(cli_module, "write_gold_run_verification_artifacts", return_value={"status": "ready"}),
                patch.object(cli_module, "render_gold_run_verification_markdown", return_value="# Gold Run Verification\n\nready"),
                patch.object(
                    cli_module,
                    "write_perfect_agent_readiness_artifacts",
                    return_value=SimpleNamespace(status="block", score=0.917, ready_capabilities=11, review_capabilities=0, blocked_capabilities=1),
                ) as write_readiness,
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                cli_module.main(
                    [
                        "gold-run-launch",
                        "--topic",
                        "ready gold",
                        "--out",
                        str(out_dir),
                    ]
                )

            output = stdout.getvalue()
            bundle_written = (out_dir / "00-gold-launch-bundle.json").exists()
            readiness_args = write_readiness.call_args.args

        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Gold run directory created", output)
        self.assertIn("Keep this launch process running", output)
        self.assertIn("research_agent status", output)
        self.assertIn("awaiting_review_approval", output)
        self.assertIn("research_agent approve ", output)
        self.assertIn("awaiting_execution_approval", output)
        self.assertIn("research_agent approve-execution", output)
        self.assertIn("Gold research run completed", output)
        self.assertIn("Perfect readiness:", output)
        self.assertIn("ready/review/block=11/0/1", output)
        self.assertEqual(readiness_args, (Path("."), out_dir.parent, Path(".")))
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)
        self.assertTrue(bundle_written)

    def test_gold_run_launch_blocked_verification_writes_repair_resume_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "blocked-gold-run"
            ready_bundle = {
                "schema_version": 1,
                "topic": "blocked gold",
                "status": "ready_to_start",
                "can_start_gold_run": True,
                "components": [],
                "launch_plan": {"status": "ready_to_start", "ready_to_execute_commands": True},
                "read_only": True,
            }
            repair_report = {
                "status": "ready_to_resume_repair",
                "can_resume": True,
                "repair_plan_sources": ["gold-run-verification"],
            }
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                patch.object(cli_module, "build_gold_launch_bundle_report", return_value=ready_bundle),
                patch.object(cli_module, "render_gold_launch_bundle_markdown", return_value="# Gold Launch Bundle\n\nready"),
                patch.object(cli_module, "run_pipeline", return_value=out_dir),
                patch.object(cli_module, "write_gold_run_verification_artifacts", return_value={"status": "blocked"}),
                patch.object(cli_module, "render_gold_run_verification_markdown", return_value="# Gold Run Verification\n\nblocked"),
                patch.object(cli_module, "write_repair_resume_plan_artifacts", return_value=repair_report) as write_repair,
                patch.object(cli_module, "render_repair_resume_plan_markdown", return_value="# 修复恢复计划\n"),
                patch.object(
                    cli_module,
                    "write_perfect_agent_readiness_artifacts",
                    return_value=SimpleNamespace(status="block", score=0.917, ready_capabilities=11, review_capabilities=0, blocked_capabilities=1),
                ) as write_readiness,
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                with self.assertRaises(SystemExit) as caught:
                    cli_module.main(
                        [
                            "gold-run-launch",
                            "--topic",
                            "blocked gold",
                            "--out",
                            str(out_dir),
                        ]
                    )

            output = stdout.getvalue()
            kwargs = write_repair.call_args.kwargs
            readiness_args = write_readiness.call_args.args

        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Gold research run completed", output)
        self.assertIn("Repair resume plan:", output)
        self.assertIn("Perfect readiness:", output)
        self.assertEqual(kwargs["gold_verification_report_path"], out_dir / "15-gold-run-verification.json")
        self.assertFalse(kwargs["apply"])
        self.assertEqual(readiness_args, (Path("."), out_dir.parent, Path(".")))
        self.assertNotIn("sk-", output)
        self.assertNotIn("OPENAI_API_KEY", output)

    def test_gold_run_verify_command_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "gold-run-verify", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--run-dir", completed.stdout)
        self.assertIn("--out", completed.stdout)
        self.assertIn("--no-write", completed.stdout)
        self.assertIn("--write-repair-resume-plan", completed.stdout)
        self.assertNotIn("--llm-api-key", completed.stdout)

    def test_gold_run_verify_can_write_repair_resume_plan_from_blocked_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "candidate"
            run_dir.mkdir()
            (run_dir / "01-literature-gate-decision.json").write_text('{"paper_grade_literature":{"status":"pass"}}', encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-verify",
                    "--run-dir",
                    str(run_dir),
                    "--write-repair-resume-plan",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            verification_exists = (run_dir / "15-gold-run-verification.json").exists()
            plan_text = (run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 2)
        self.assertTrue(verification_exists)
        self.assertIn("Repair resume plan:", completed.stdout)
        self.assertIn("gold-verification:", plan_text)
        self.assertIn('"gold-run-verification"', plan_text)
        self.assertNotIn("sk-", completed.stdout + completed.stderr + plan_text)

    def test_gold_run_verify_repair_resume_plan_requires_write_mode(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-run-verify",
                "--run-dir",
                ".",
                "--no-write",
                "--write-repair-resume-plan",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("--write-repair-resume-plan requires writing", completed.stderr)

    def test_gold_run_verify_cli_reports_blocked_contract_without_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "candidate"
            run_dir.mkdir()
            (run_dir / "01-literature-gate-decision.json").write_text('{"paper_grade_literature":{"status":"pass"}}', encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-verify",
                    "--run-dir",
                    str(run_dir),
                    "--no-write",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Gold Run Verification", completed.stdout)
        self.assertIn("Gold contract ready：否", completed.stdout)
        self.assertIn("04-benchmark-evidence-audit.json", completed.stdout)
        self.assertNotIn("api-key", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_gold_launch_bundle_cli_prints_safe_blocking_summary(self) -> None:
        env = {
            **os.environ,
            "OPENAI_BASE_URL": "http://127.0.0.1:8317",
            "OPENAI_MODEL": "gpt-5.5",
            "OPENAI_API_KEY": "unit-test-api-token",
            "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
        }
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent.cli",
                "gold-launch-bundle",
                "--topic",
                "CLI bundle smoke",
                "--project-dir",
                str(Path.cwd()),
                "--literature-provider",
                "offline",
                "--literature-sources",
                "openalex,arxiv,crossref",
                "--seed-paper",
                "10.1234/example.review",
                "--seed-paper",
                "10.1234/example.benchmark",
                "--seed-paper",
                "10.1234/example.baseline",
                "--execution-mode",
                "benchmark",
                "--execution-repeats",
                "3",
                "--benchmark-manifest",
                "benchmarks/uci-iris-classification/manifest-candidate.json",
                "--benchmark-manifest",
                "benchmarks/uci-iris-classification/manifest-baseline.json",
                "--benchmark-manifest",
                "benchmarks/uci-iris-classification/manifest-ablation.json",
                "--release-code-repository-url",
                "https://github.com/research-agent-lab/research-agent",
                "--release-code-archive-doi",
                "10.5281/zenodo.7654321",
                "--release-code-license",
                "MIT",
                "--release-code-version",
                "v1.0.0",
                "--release-data-access-statement",
                "The Iris data are available from the UCI Machine Learning Repository.",
                "--release-environment-url",
                "https://github.com/research-agent-lab/research-agent/blob/v1.0.0/Dockerfile",
                "--paper-grade",
                "--no-write",
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Gold Launch Bundle", completed.stdout)
        self.assertIn("Safe Launch Plan", completed.stdout)
        self.assertIn("Repair Plan", completed.stdout)
        self.assertIn("paper_grade_literature_probe", completed.stdout)
        self.assertIn("benchmark_preview", completed.stdout)
        self.assertIn("seed_papers", completed.stdout)
        self.assertIn("research_agent run", completed.stdout)
        self.assertIn("research_agent status", completed.stdout)
        self.assertIn("research_agent approve-execution", completed.stdout)
        self.assertNotIn("export ", completed.stdout)
        self.assertNotIn("unit-test-api-token", completed.stdout)
        self.assertNotIn("researcher@university.edu", completed.stdout)
        self.assertNotIn("OPENAI_API_KEY", completed.stdout)

    def test_gold_run_doctor_cli_accepts_configless_paper_grade_inputs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir = root / "benchmark"
            fulltext_dir = root / "fulltext"
            benchmark_dir.mkdir()
            fulltext_dir.mkdir()
            (benchmark_dir / "04-benchmark-pack-run.json").write_text(
                '{"status":"warn","benchmark_evidence_grade":"real_benchmark","results":9,"comparisons":3,'
                '"statistical_outcome":"neutral_no_observed_difference",'
                '"claim_boundary_severity":"negative_or_neutral_no_superiority",'
                '"publishable_negative_or_neutral_result":true,'
                '"claim_policy":"negative_or_neutral_benchmark_claims_allowed_no_superiority_claims"}',
                encoding="utf-8",
            )
            (fulltext_dir / "10-fulltext-grounding-run.json").write_text('{"status":"pass","grounding_status":"pass","fulltext_chunks":3}', encoding="utf-8")
            env = {
                **os.environ,
                "OPENAI_BASE_URL": "http://127.0.0.1:8317",
                "OPENAI_MODEL": "gpt-5.5",
                "OPENAI_API_KEY": "unit-test-api-token",
                "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
                "SEMANTIC_SCHOLAR_API_KEY": "semantic-secret",
                "OPENALEX_API_KEY": "openalex-secret",
            }

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-doctor",
                    "--topic",
                    "Iris classification benchmark smoke",
                    "--benchmark-pack-run-dir",
                    str(benchmark_dir),
                    "--fulltext-grounding-run-dir",
                    str(fulltext_dir),
                    "--literature-provider",
                    "online",
                    "--literature-sources",
                    "semantic_scholar,openalex,arxiv,crossref",
                    "--seed-paper",
                    "10.24432/C56C76 benchmark dataset UCI Iris 2024 official dataset",
                    "--seed-paper",
                    "10.1111/j.1469-1809.1936.tb02137.x Fisher Iris discriminant analysis baseline method",
                    "--seed-paper",
                    "https://archive.ics.uci.edu/dataset/53/iris official UCI repository page",
                    "--fulltext-path",
                    "benchmarks/uci-iris-classification/fulltext/iris.names.txt",
                    "--max-papers",
                    "12",
                    "--max-search-queries",
                    "6",
                    "--extra-search-query",
                    "UCI Iris classification benchmark baseline",
                    "--execution-mode",
                    "benchmark",
                    "--execution-repeats",
                    "3",
                    "--benchmark-manifest",
                    "benchmarks/uci-iris-classification/manifest-candidate.json",
                    "--benchmark-manifest",
                    "benchmarks/uci-iris-classification/manifest-baseline.json",
                    "--benchmark-manifest",
                    "benchmarks/uci-iris-classification/manifest-ablation.json",
                    "--paper-grade",
                    "--release-code-repository-url",
                    "https://github.com/research-agent-lab/research-agent",
                    "--release-code-archive-doi",
                    "10.5281/zenodo.7654321",
                    "--release-code-license",
                    "MIT",
                    "--release-code-version",
                    "v1.0.0",
                    "--release-data-access-statement",
                    "The Iris data are available from the UCI Machine Learning Repository.",
                    "--release-environment-url",
                    "https://github.com/research-agent-lab/research-agent/blob/v1.0.0/Dockerfile",
                    "--no-write",
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--paper-grade", completed.stdout)
        self.assertIn("--seed-paper", completed.stdout)
        self.assertIn("--benchmark-manifest", completed.stdout)
        self.assertIn('--execution-mode "benchmark"', completed.stdout)
        self.assertIn("--release-code-archive-doi", completed.stdout)
        self.assertNotIn("--config examples/uci-iris-paper-grade-config.toml", completed.stdout)
        self.assertNotIn("unit-test-api-token", completed.stdout)
        self.assertNotIn("researcher@university.edu", completed.stdout)
        self.assertNotIn("semantic-secret", completed.stdout)
        self.assertNotIn("openalex-secret", completed.stdout)

    def test_gold_run_doctor_cli_accepts_release_overrides(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir = root / "benchmark"
            fulltext_dir = root / "fulltext"
            benchmark_dir.mkdir()
            fulltext_dir.mkdir()
            (benchmark_dir / "04-benchmark-pack-run.json").write_text(
                '{"status":"warn","benchmark_evidence_grade":"real_benchmark","results":9,"comparisons":3,'
                '"statistical_outcome":"neutral_no_observed_difference",'
                '"claim_boundary_severity":"negative_or_neutral_no_superiority",'
                '"publishable_negative_or_neutral_result":true,'
                '"claim_policy":"negative_or_neutral_benchmark_claims_allowed_no_superiority_claims"}',
                encoding="utf-8",
            )
            (fulltext_dir / "10-fulltext-grounding-run.json").write_text('{"status":"pass","grounding_status":"pass","fulltext_chunks":3}', encoding="utf-8")
            env = {
                **os.environ,
                "OPENAI_BASE_URL": "http://127.0.0.1:8317",
                "OPENAI_MODEL": "gpt-5.5",
                "OPENAI_API_KEY": "unit-test-api-token",
                "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
                "SEMANTIC_SCHOLAR_API_KEY": "semantic-secret",
                "OPENALEX_API_KEY": "openalex-secret",
            }

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-doctor",
                    "--topic",
                    "Iris classification benchmark smoke",
                    "--config",
                    str(Path(__file__).resolve().parents[1] / "examples" / "uci-iris-paper-grade-config.toml"),
                    "--benchmark-pack-run-dir",
                    str(benchmark_dir),
                    "--fulltext-grounding-run-dir",
                    str(fulltext_dir),
                    "--release-code-repository-url",
                    "https://github.com/research-agent-lab/research-agent",
                    "--release-code-archive-doi",
                    "10.5281/zenodo.7654321",
                    "--release-code-license",
                    "MIT",
                    "--release-code-version",
                    "v1.0.0",
                    "--release-data-access-statement",
                    "The Iris data are available from the UCI Machine Learning Repository.",
                    "--release-environment-url",
                    "https://github.com/research-agent-lab/research-agent/blob/v1.0.0/Dockerfile",
                    "--no-write",
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("gold_release_metadata", completed.stdout)
        self.assertIn("ready", completed.stdout)
        self.assertNotIn("unit-test-api-token", completed.stdout)

    def test_gold_run_doctor_cli_writes_candidate_repair_resume_plan(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_dir = root / "benchmark"
            fulltext_dir = root / "fulltext"
            candidate_dir = root / "candidate"
            doctor_dir = root / "doctor"
            benchmark_dir.mkdir()
            fulltext_dir.mkdir()
            candidate_dir.mkdir()
            (benchmark_dir / "04-benchmark-pack-run.json").write_text(
                '{"status":"warn","benchmark_evidence_grade":"real_benchmark","results":9,"comparisons":3,'
                '"statistical_outcome":"neutral_no_observed_difference",'
                '"claim_boundary_severity":"negative_or_neutral_no_superiority",'
                '"publishable_negative_or_neutral_result":true,'
                '"claim_policy":"negative_or_neutral_benchmark_claims_allowed_no_superiority_claims"}',
                encoding="utf-8",
            )
            (fulltext_dir / "10-fulltext-grounding-run.json").write_text('{"status":"pass","grounding_status":"pass","fulltext_chunks":3}', encoding="utf-8")
            (candidate_dir / "01-literature-gate-decision.json").write_text('{"paper_grade_literature":{"status":"pass","issues":[]}}', encoding="utf-8")
            (candidate_dir / "04-benchmark-evidence-audit.json").write_text(
                '{"status":"warn","evidence_grade":"real_benchmark","adapter_paper_grade_status":"ready",'
                '"adapter_paper_grade_issues":[],"claim_boundary_severity":"negative_or_neutral_no_superiority",'
                '"statistical_outcome":"neutral_no_observed_difference","publishable_negative_or_neutral_result":true,'
                '"claim_policy":"negative_or_neutral_benchmark_claims_allowed_no_superiority_claims",'
                '"blocking_issues":[],"manual_tasks":[]}',
                encoding="utf-8",
            )
            (candidate_dir / "10-claim-consistency.json").write_text('{"status":"pass","blocking_issues":[],"manual_tasks":[]}', encoding="utf-8")
            (candidate_dir / "10-claim-traceability.json").write_text(
                '{"status":"pass","traceability_score":1.0,"blocked_claims":0,"review_claims":0,"blocking_issues":[],"manual_tasks":[]}',
                encoding="utf-8",
            )
            (candidate_dir / "11-submission-package.json").write_text('{"status":"blocked","blocking_issues":[],"manual_tasks":[]}', encoding="utf-8")
            (candidate_dir / "12-repair-queue.json").write_text('{"status":"pass","summary":{"total":0,"block":0,"high":0,"medium":0}}', encoding="utf-8")
            (candidate_dir / "13-run-economics-audit.json").write_text(
                '{"status":"pass","summary":{"input_tokens_estimated":100,"output_tokens_estimated":50,"total_tokens_estimated":150},'
                '"blocking_issues":[],"manual_tasks":[],"warnings":[]}',
                encoding="utf-8",
            )
            (candidate_dir / "13-research-scorecard.json").write_text('{"status":"ready_for_human_submission_upload","blocking_issues":[],"manual_tasks":[]}', encoding="utf-8")
            (candidate_dir / "14-run-integrity-audit.json").write_text(
                '{"status":"pass","summary":{"pass":12,"warn":0,"block":0},"blocking_issues":[],"warnings":[]}',
                encoding="utf-8",
            )
            (candidate_dir / "14-final-handoff.json").write_text('{"status":"ready_for_submission_upload","blocking_issues":[],"manual_tasks":[]}', encoding="utf-8")

            env = {
                **os.environ,
                "OPENAI_BASE_URL": "http://127.0.0.1:8317",
                "OPENAI_MODEL": "gpt-5.5",
                "OPENAI_API_KEY": "unit-test-api-token",
                "RESEARCH_AGENT_CONTACT_EMAIL": "researcher@university.edu",
                "SEMANTIC_SCHOLAR_API_KEY": "semantic-secret",
                "OPENALEX_API_KEY": "openalex-secret",
            }
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "gold-run-doctor",
                    "--topic",
                    "Iris classification benchmark smoke",
                    "--config",
                    str(Path(__file__).resolve().parents[1] / "examples" / "uci-iris-paper-grade-config.toml"),
                    "--benchmark-pack-run-dir",
                    str(benchmark_dir),
                    "--fulltext-grounding-run-dir",
                    str(fulltext_dir),
                    "--candidate-run-dir",
                    str(candidate_dir),
                    "--out",
                    str(doctor_dir),
                    "--write-candidate-repair-resume-plan",
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertIn("Candidate Repair Resume Plan", completed.stdout)
            self.assertTrue((doctor_dir / "00-gold-launch-manifest.json").exists())
            self.assertTrue((doctor_dir / "00-gold-launch-manifest.md").exists())
            self.assertTrue((candidate_dir / "12-repair-resume-plan.json").exists())
            self.assertIn("gold-doctor:submission_package", (candidate_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8"))
            self.assertNotIn("unit-test-api-token", completed.stdout)
            self.assertNotIn("researcher@university.edu", completed.stdout)

    def test_repair_resume_defaults_to_preview_without_cleanup(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "state.json").write_text('{"topic":"Iris","stage":"completed"}', encoding="utf-8")
            (run_dir / "12-repair-queue.json").write_text(
                '{"topic":"Iris","status":"blocked_repair_required",'
                '"items":[{"task_id":"RQ-001","severity":"block","category":"result_validation",'
                '"source_artifact":"04-result-validation.json","action":"重跑实验",'
                '"rerun_from":"experiments","status":"open"}]}',
                encoding="utf-8",
            )
            (run_dir / "04-results.json").write_text('{"status":"stale"}', encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "repair-resume", str(run_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Preview only", completed.stdout)
            self.assertTrue((run_dir / "04-results.json").exists())
            plan_text = (run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8")
            self.assertIn('"applied": false', plan_text)
            self.assertIn("--apply", plan_text)

    def test_repair_resume_rejects_apply_and_dry_run_together(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "repair-resume", ".", "--apply", "--dry-run"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("--apply cannot be used with --dry-run", completed.stderr)

    def test_human_brief_overrides_append_to_config(self) -> None:
        config = AgentConfig(human=HumanConfig(constraints=["配置约束"]))

        updated = _apply_run_overrides(
            config,
            _run_args(
                human_note=["优先验证窄通道"],
                human_constraint=["必须比较 RRT*"],
                human_success_criterion=["成功率提升"],
                human_resource_limit=["只运行 smoke-first"],
                human_risk=["避免玩具场景"],
            ),
        )

        self.assertEqual(updated.human.notes, ["优先验证窄通道"])
        self.assertEqual(updated.human.constraints, ["配置约束", "必须比较 RRT*"])
        self.assertEqual(updated.human.success_criteria, ["成功率提升"])
        self.assertEqual(updated.human.resource_limits, ["只运行 smoke-first"])
        self.assertEqual(updated.human.risks, ["避免玩具场景"])

    def test_human_brief_flags_are_available_on_run_commands(self) -> None:
        for command in ["run", "preflight", "resume", "repair-resume"]:
            with self.subTest(command=command):
                completed = subprocess.run(
                    [sys.executable, "-m", "research_agent.cli", command, "--help"],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(completed.returncode, 0)
                self.assertIn("--human-note", completed.stdout)
                self.assertIn("--human-constraint", completed.stdout)
                self.assertIn("--human-resource-limit", completed.stdout)

    def test_memory_command_writes_run_memory_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            out_dir = root / "out"
            run_dir = runs_dir / "handoff-blocked"
            run_dir.mkdir(parents=True)
            out_dir.mkdir()
            (run_dir / "state.json").write_text('{"topic":"交付阻断","stage":"completed","updated_at":"2026-06-08T10:00:00+00:00"}', encoding="utf-8")
            (run_dir / "01-literature-quality.json").write_text('{"selected_papers":6,"total_papers":8}', encoding="utf-8")
            (run_dir / "14-final-handoff.json").write_text(
                '{"status":"blocked","package_zip_exists":false,"package_status":"blocked",'
                '"scorecard_status":"blocked","run_integrity_status":"block",'
                '"package_has_integrity_audit":false,'
                '"blocking_issues":["ZIP 缺失"],"manual_tasks":[],"recommended_actions":[]}',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "memory",
                    "--runs-dir",
                    str(runs_dir),
                    "--out",
                    str(out_dir),
                    "--limit",
                    "10",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Runs 复盘记忆", completed.stdout)
            self.assertIn("final_handoff", completed.stdout)
            self.assertTrue((out_dir / "runs-memory.json").exists())
            self.assertTrue((out_dir / "runs-memory.md").exists())

    def test_library_command_writes_searchable_run_library_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            out_dir = root / "out"
            run_dir = runs_dir / "robot-run"
            run_dir.mkdir(parents=True)
            out_dir.mkdir()
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed","updated_at":"2026-06-08T10:00:00+00:00"}', encoding="utf-8")
            (run_dir / "01-literature-quality.json").write_text('{"selected_papers":6,"total_papers":8}', encoding="utf-8")
            (run_dir / "01-context.json").write_text('{"citations":[{"key":"ompl2012"}]}', encoding="utf-8")
            (run_dir / "06-paper.md").write_text("# 机械臂路径规划\n\nOMPL benchmark with RRT* baseline.", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "library",
                    "--runs-dir",
                    str(runs_dir),
                    "--out",
                    str(out_dir),
                    "--query",
                    "OMPL RRT",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Runs 本地成果库", completed.stdout)
            self.assertIn("robot-run", completed.stdout)
            self.assertTrue((out_dir / "runs-library.json").exists())
            self.assertTrue((out_dir / "runs-library.md").exists())

    def test_platform_audit_command_writes_cross_run_audit_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            out_dir = root / "out"
            run_dir = runs_dir / "weak-run"
            run_dir.mkdir(parents=True)
            out_dir.mkdir()
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed","updated_at":"2026-06-10T10:00:00+00:00"}', encoding="utf-8")
            (run_dir / "01-literature-quality.json").write_text('{"selected_papers":1,"total_papers":2,"confidence_status":"warn"}', encoding="utf-8")
            (run_dir / "approval.json").write_text('{"approved":false,"blocks":[]}', encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "platform-audit",
                    "--runs-dir",
                    str(runs_dir),
                    "--out",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("平台能力审计", completed.stdout)
            self.assertIn("literature_rag_quality", completed.stdout)
            self.assertTrue((out_dir / "runs-platform-audit.json").exists())
            self.assertTrue((out_dir / "runs-platform-audit.md").exists())

    def test_platform_audit_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "platform-audit", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--runs-dir", completed.stdout)
        self.assertIn("--no-write", completed.stdout)

    def test_perfect_readiness_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "perfect-readiness", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--project-dir", completed.stdout)
        self.assertIn("--runs-dir", completed.stdout)
        self.assertIn("--no-write", completed.stdout)

    def test_open_source_lessons_command_writes_project_provenance_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "open-source-lessons",
                    "--topic",
                    "机械臂路径规划",
                    "--out",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("项目来源证据", completed.stdout)
            self.assertIn("built_in_catalog", completed.stdout)
            self.assertTrue((out_dir / "00-open-source-lessons.json").exists())
            self.assertTrue((out_dir / "00-open-source-lessons.md").exists())

    def test_open_source_lessons_help_exposes_github_refresh(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "open-source-lessons", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--refresh-github", completed.stdout)
        self.assertIn("--github-token", completed.stdout)
        self.assertIn("--timeout", completed.stdout)

    def test_open_source_compliance_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "open-source-compliance-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Open-Source Compliance Backfill", dry.stdout)
            self.assertIn("将写入 Lessons：1", dry.stdout)
            self.assertFalse((run_dir / "00-open-source-lessons.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "open-source-compliance-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "00-open-source-lessons.json").exists())
            self.assertTrue((run_dir / "13-open-source-compliance.json").exists())

    def test_open_source_compliance_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "open-source-compliance-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_trajectory_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "run-manifest.json").write_text(
                '{"status":"completed","events":[{"stage":"completed","status":"completed"}],"artifacts":[]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "trajectory-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Agent Trajectory Backfill", dry.stdout)
            self.assertIn("would_write", dry.stdout)
            self.assertFalse((run_dir / "13-agent-trajectory.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "trajectory-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "13-agent-trajectory.json").exists())
            self.assertTrue((run_dir / "13-agent-trajectory.md").exists())

    def test_trajectory_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "trajectory-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_manifest_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "00-research-plan.json").write_text('{"topic":"机械臂路径规划"}', encoding="utf-8")

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "manifest-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Run Manifest Backfill", dry.stdout)
            self.assertIn("would_write", dry.stdout)
            self.assertFalse((run_dir / "run-manifest.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "manifest-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "run-manifest.json").exists())
            self.assertTrue((run_dir / "run-manifest.md").exists())

    def test_manifest_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "manifest-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_observability_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "run-manifest.json").write_text(
                '{"status":"completed","events":[{"stage":"completed","status":"completed"}],"artifacts":[]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "observability-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Agent Observability Backfill", dry.stdout)
            self.assertIn("would_write", dry.stdout)
            self.assertFalse((run_dir / "13-agent-observability-audit.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "observability-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "13-agent-observability-audit.json").exists())
            self.assertTrue((run_dir / "13-agent-observability-audit.md").exists())

    def test_observability_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "observability-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_llm_observability_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "llm-observability-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("LLM Observability Backfill", dry.stdout)
            self.assertIn("将写入 Trace 审计：1", dry.stdout)
            self.assertFalse((run_dir / "13-llm-trace-audit.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "llm-observability-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "13-llm-trace-audit.json").exists())
            self.assertTrue((run_dir / "13-run-economics-audit.json").exists())
            self.assertTrue((run_dir / "13-agent-observability-audit.json").exists())
            self.assertFalse((run_dir / "run-llm-ledger.json").exists())

    def test_llm_observability_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "llm-observability-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_gate_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"awaiting_review_approval"}', encoding="utf-8")
            (run_dir / "01-literature-quality.json").write_text(
                '{"total_papers":2,"selected_papers":1,"confidence_status":"weak","confidence_score":0.42}',
                encoding="utf-8",
            )
            (run_dir / "01-citation-audit.json").write_text(
                '{"integrity_status":"block","integrity_score":0.3,"blocked_citations":1,"review_required":0,"usable_citations":0,"total_citations":1}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-gate-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Gate Decision Backfill", dry.stdout)
            self.assertIn("将写入门禁：1", dry.stdout)
            self.assertFalse((run_dir / "01-literature-gate-decision.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-gate-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-literature-gate-decision.json").exists())
            self.assertTrue((run_dir / "01-literature-gate-decision.md").exists())

    def test_literature_gate_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-gate-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_rescue_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature.json").write_text(
                '{"topic":"机械臂路径规划","papers":[{"title":"A generic neural planner","authors":["A"],'
                '"year":2024,"venue":"arXiv","url":"https://example.test/a","abstract":"Generic path planning article.",'
                '"relevance":0.9,"source":"openalex","sources":["openalex"],"doi":"10.1000/a"}],"themes":[],"gaps":[],"summary":"legacy"}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-rescue-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Rescue Backfill", dry.stdout)
            self.assertIn("将写入 rescue plan：1", dry.stdout)
            self.assertFalse((run_dir / "01-literature-rescue-plan.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-rescue-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-literature-rescue-plan.json").exists())
            self.assertTrue((run_dir / "01-literature-rescue-plan.md").exists())

    def test_literature_rescue_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-rescue-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_search_audit_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature.json").write_text(
                '{"topic":"机械臂路径规划","papers":[{"title":"Robot manipulator motion planning with OMPL benchmark",'
                '"authors":["Ada"],"year":2024,"venue":"ICRA","url":"https://example.test/robot",'
                '"abstract":"Robot manipulator motion planning with OMPL benchmark and RRT star baseline evaluation.",'
                '"relevance":0.88,"source":"crossref","sources":["crossref"],"doi":"10.1000/robot"}],'
                '"themes":[],"gaps":[],"summary":"legacy","source_diagnostics":["检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",'
                '"semantic_scholar: 检索失败：HTTP 429: Too Many Requests","crossref: 2 个检索式返回 20 条，用时 1.4s"]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-search-audit-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Search Audit Backfill", dry.stdout)
            self.assertIn("将写入 run：1", dry.stdout)
            self.assertFalse((run_dir / "01-query-execution-audit.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-search-audit-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-literature-search-strategy.json").exists())
            self.assertTrue((run_dir / "01-literature-source-health.json").exists())
            self.assertTrue((run_dir / "01-query-execution-audit.json").exists())

    def test_literature_search_audit_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-search-audit-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_seed_paper_intake_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature-quality.json").write_text(
                '{"items":[{"title":"The Open Motion Planning Library",'
                '"doi":"10.1109/MRA.2012.2205651","url":"https://doi.org/10.1109/MRA.2012.2205651",'
                '"selected":true,"quality_score":0.94,"evidence_roles":["benchmark_dataset","baseline_method"]}]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "seed-paper-intake-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Seed Paper Intake Backfill", dry.stdout)
            self.assertIn("将写入 run：1", dry.stdout)
            self.assertFalse((run_dir / "01-seed-paper-intake.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "seed-paper-intake-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-seed-paper-intake.json").exists())
            self.assertTrue((run_dir / "01-seed-paper-intake.md").exists())

    def test_seed_paper_intake_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "seed-paper-intake-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_context_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature.json").write_text(
                '{"topic":"机械臂路径规划","papers":[{"title":"A generic education survey","authors":[],"year":2025,'
                '"venue":"Crossref","url":"","abstract":"Short note.","relevance":0.95,"source":"crossref","sources":["crossref"]},'
                '{"title":"Robot manipulator motion planning with RRT star and OMPL benchmarks","authors":["Ada Lovelace"],'
                '"year":2024,"venue":"Robotics Journal","url":"https://example.test/robot",'
                '"abstract":"Robot manipulator motion planning with obstacle avoidance, RRT star, CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, collision rate, and reproducible baseline evaluation.",'
                '"relevance":0.35,"source":"openalex","sources":["openalex","semantic_scholar"],"doi":"10.1234/robot.motion","citation_count":120}],'
                '"themes":[],"gaps":[],"summary":"legacy","source_diagnostics":["检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",'
                '"semantic_scholar: 检索失败：HTTP 429: Too Many Requests","crossref: 2 个检索式返回 20 条，用时 1.4s"]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-context-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Context Backfill", dry.stdout)
            self.assertIn("将写入 run：1", dry.stdout)
            self.assertFalse((run_dir / "01-context.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-context-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-context.json").exists())
            self.assertTrue((run_dir / "01-citation-audit.json").exists())

    def test_literature_context_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-context-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_audit_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature.json").write_text(
                '{"topic":"机械臂路径规划","papers":[{"title":"A generic education survey","authors":[],"year":2025,'
                '"venue":"Crossref","url":"","abstract":"Short note.","relevance":0.95,"source":"crossref","sources":["crossref"]},'
                '{"title":"Robot manipulator motion planning with RRT star and OMPL benchmarks","authors":["Ada Lovelace"],'
                '"year":2024,"venue":"Robotics Journal","url":"https://example.test/robot",'
                '"abstract":"Robot manipulator motion planning with obstacle avoidance, RRT star, CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, collision rate, and reproducible baseline evaluation.",'
                '"relevance":0.35,"source":"openalex","sources":["openalex","semantic_scholar"],"doi":"10.1234/robot.motion","citation_count":120}],'
                '"themes":[],"gaps":[],"summary":"legacy","source_diagnostics":["检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",'
                '"semantic_scholar: 检索失败：HTTP 429: Too Many Requests","crossref: 2 个检索式返回 20 条，用时 1.4s"]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-audit-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Audit Backfill", dry.stdout)
            self.assertIn("将写入 run：1", dry.stdout)
            self.assertFalse((run_dir / "01-literature-metadata-audit.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-audit-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-literature-metadata-audit.json").exists())
            self.assertTrue((run_dir / "01-literature-coverage.json").exists())
            self.assertTrue((run_dir / "01-literature-evidence-mix.json").exists())

    def test_literature_audit_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-audit-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_quality_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature.json").write_text(
                '{"topic":"机械臂路径规划","papers":[{"title":"A generic education survey","authors":[],"year":2025,'
                '"venue":"Crossref","url":"","abstract":"Short note.","relevance":0.95,"source":"crossref","sources":["crossref"]},'
                '{"title":"Robot manipulator motion planning with RRT star and OMPL benchmarks","authors":["Ada Lovelace"],'
                '"year":2024,"venue":"Robotics Journal","url":"https://example.test/robot",'
                '"abstract":"Robot manipulator motion planning with obstacle avoidance, RRT star, CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, collision rate, and reproducible baseline evaluation.",'
                '"relevance":0.35,"source":"openalex","sources":["openalex","semantic_scholar"],"doi":"10.1234/robot.motion","citation_count":120}],'
                '"themes":[],"gaps":[],"summary":"legacy","source_diagnostics":["检索式: robot manipulator motion planning | OMPL benchmark robot manipulator",'
                '"semantic_scholar: 检索失败：HTTP 429: Too Many Requests","crossref: 2 个检索式返回 20 条，用时 1.4s"]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-quality-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Quality Backfill", dry.stdout)
            self.assertIn("将写入 run：1", dry.stdout)
            self.assertFalse((run_dir / "01-literature-quality.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-quality-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-literature-quality.json").exists())
            self.assertTrue((run_dir / "01-literature-curated.json").exists())

    def test_literature_quality_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-quality-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_literature_rerank_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "01-literature.json").write_text(
                '{"topic":"机械臂路径规划","papers":[{"title":"A generic education survey","authors":[],"year":2025,'
                '"venue":"Crossref","url":"","abstract":"Short note.","relevance":0.95,"source":"crossref","sources":["crossref"]},'
                '{"title":"Robot manipulator motion planning with RRT star and OMPL benchmarks","authors":["Ada Lovelace"],'
                '"year":2024,"venue":"Robotics Journal","url":"https://example.test/robot",'
                '"abstract":"Robot manipulator motion planning with obstacle avoidance, RRT star, CHOMP, STOMP, TrajOpt, OMPL benchmark, planning time, path length, collision rate, and reproducible baseline evaluation.",'
                '"relevance":0.35,"source":"openalex","sources":["openalex","semantic_scholar"],"doi":"10.1234/robot.motion","citation_count":120}],'
                '"themes":[],"gaps":[],"summary":"legacy"}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-rerank-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Literature Rerank Backfill", dry.stdout)
            self.assertIn("将写入 rerank：1", dry.stdout)
            self.assertFalse((run_dir / "01-literature-rerank.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "literature-rerank-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "01-literature-rerank.json").exists())
            self.assertTrue((run_dir / "01-literature-rerank.md").exists())

    def test_literature_rerank_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "literature-rerank-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_repair_resume_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "12-repair-queue.json").write_text(
                '{"topic":"机械臂路径规划","status":"blocked_repair_required",'
                '"items":[{"task_id":"RQ-001","severity":"block","category":"result_validation",'
                '"source_artifact":"04-result-validation.json","action":"重跑修复项",'
                '"rerun_from":"experiments","status":"open"}]}',
                encoding="utf-8",
            )
            (run_dir / "04-results.json").write_text('[{"status":"stale"}]', encoding="utf-8")

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "repair-resume-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Repair Resume Backfill", dry.stdout)
            self.assertIn("将写入预案：1", dry.stdout)
            self.assertFalse((run_dir / "12-repair-resume-plan.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "repair-resume-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertTrue((run_dir / "12-repair-resume-plan.json").exists())
            self.assertTrue((run_dir / "12-repair-resume-plan.md").exists())
            self.assertTrue((run_dir / "04-results.json").exists())

    def test_repair_resume_dry_run_accepts_gold_run_doctor_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "candidate"
            run_dir.mkdir()
            (run_dir / "12-repair-queue.json").write_text('{"topic":"Iris","status":"pass","items":[]}', encoding="utf-8")
            (run_dir / "04-benchmark-evidence-audit.json").write_text('{"status":"warn"}', encoding="utf-8")
            doctor_report = root / "00-gold-run-doctor.json"
            doctor_report.write_text(
                '{"checks":[{"name":"candidate_gold_run","status":"fail","repair_plan":['
                '{"id":"benchmark_evidence_metadata","priority":35,"rerun_from":"experiments",'
                '"source_artifact":"04-benchmark-evidence-audit.json",'
                '"target_artifacts":["04-benchmark-evidence-audit.json","10-claim-consistency.json"],'
                '"action":"重新生成 benchmark evidence metadata。"}]}]}',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "repair-resume",
                    str(run_dir),
                    "--dry-run",
                    "--gold-run-doctor-report",
                    str(doctor_report),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("计划来源：12-repair-queue, gold-run-doctor", completed.stdout)
            plan_text = (run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8")
            self.assertIn('"gold-doctor:benchmark_evidence_metadata"', plan_text)
            self.assertIn('"rerun_from": "experiments"', plan_text)

    def test_repair_resume_accepts_gold_run_verification_report(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "candidate"
            run_dir.mkdir()
            (run_dir / "12-repair-queue.json").write_text('{"topic":"Iris","status":"pass","items":[]}', encoding="utf-8")
            (run_dir / "11-submission-package.json").write_text('{"status":"blocked"}', encoding="utf-8")
            verification_report = run_dir / "15-gold-run-verification.json"
            verification_report.write_text(
                '{"status":"blocked","repair_plan":['
                '{"id":"submission_package","priority":70,"rerun_from":"submission_package",'
                '"source_artifact":"11-submission-package.json",'
                '"target_artifacts":["11-submission-package.json","11-submission-package.zip"],'
                '"action":"重新生成 submission package。"}]}',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "research_agent.cli",
                    "repair-resume",
                    str(run_dir),
                    "--dry-run",
                    "--gold-run-verification-report",
                    str(verification_report),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("计划来源：12-repair-queue, gold-run-verification", completed.stdout)
            plan_text = (run_dir / "12-repair-resume-plan.json").read_text(encoding="utf-8")
            self.assertIn('"gold-verification:submission_package"', plan_text)
            self.assertIn('"rerun_from": "submission_package"', plan_text)

    def test_repair_resume_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "repair-resume-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_repair_resume_backlog_command_reports_pending_runs(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "12-repair-queue.json").write_text(
                '{"topic":"机械臂路径规划","status":"blocked_repair_required",'
                '"items":[{"task_id":"RQ-001","severity":"block","category":"result_validation",'
                '"source_artifact":"04-result-validation.json","action":"重跑修复项",'
                '"rerun_from":"experiments","status":"open"}]}',
                encoding="utf-8",
            )

            completed = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "repair-resume-backlog", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Repair Resume Backlog", completed.stdout)
            self.assertIn("legacy-run", completed.stdout)
            self.assertIn("不删除产物、不批准 gate、不恢复 pipeline、不执行实验", completed.stdout)
            self.assertFalse((run_dir / "12-repair-resume-plan.json").exists())

    def test_repair_resume_backlog_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "repair-resume-backlog", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--runs-dir", completed.stdout)
        self.assertIn("--limit", completed.stdout)

    def test_repair_queue_backfill_command_supports_dry_run_and_write(self) -> None:
        with TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            run_dir = runs_dir / "legacy-run"
            run_dir.mkdir(parents=True)
            (run_dir / "state.json").write_text('{"topic":"机械臂路径规划","stage":"completed"}', encoding="utf-8")
            (run_dir / "13-agent-observability-audit.json").write_text(
                '{"status":"block","blocking_issues":["run manifest 缺少 artifact trace"],"manual_tasks":[],"warnings":[]}',
                encoding="utf-8",
            )

            dry = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "repair-queue-backfill", "--runs-dir", str(runs_dir), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("Repair Queue Backfill", dry.stdout)
            self.assertIn("would_write", dry.stdout)
            self.assertFalse((run_dir / "12-repair-queue.json").exists())

            written = subprocess.run(
                [sys.executable, "-m", "research_agent.cli", "repair-queue-backfill", "--runs-dir", str(runs_dir)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("legacy-run", written.stdout)
            self.assertIn("blocked_repair_required", written.stdout)
            self.assertTrue((run_dir / "12-repair-queue.json").exists())
            self.assertTrue((run_dir / "12-repair-queue.md").exists())

    def test_repair_queue_backfill_help_is_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_agent.cli", "repair-queue-backfill", "--help"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--dry-run", completed.stdout)
        self.assertIn("--force", completed.stdout)
        self.assertIn("--limit", completed.stdout)


def _run_args(**overrides):
    values = {
        "llm_provider": None,
        "llm_base_url": None,
        "llm_model": None,
        "llm_api_key": None,
        "llm_max_calls": None,
        "llm_max_prompt_chars": None,
        "llm_input_cost_per_million_tokens": None,
        "llm_output_cost_per_million_tokens": None,
        "literature_provider": None,
        "literature_sources": None,
        "seed_paper": [],
        "seed_papers_file": None,
        "fulltext_path": [],
        "max_papers": None,
        "max_search_queries": None,
        "extra_search_query": [],
        "extra_search_queries_file": None,
        "execution_mode": None,
        "execution_repeats": None,
        "benchmark_manifest": [],
        "human_note": [],
        "human_constraint": [],
        "human_success_criterion": [],
        "human_resource_limit": [],
        "human_risk": [],
        "release_code_repository_url": None,
        "release_code_archive_doi": None,
        "release_code_license": None,
        "release_code_version": None,
        "release_data_repository_url": None,
        "release_data_archive_doi": None,
        "release_data_access_statement": None,
        "release_environment_url": None,
        "release_notes": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


if __name__ == "__main__":
    unittest.main()
