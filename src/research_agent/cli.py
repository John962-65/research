from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import argparse
import json
import shlex
import sys

from .artifacts import write_json, write_text
from .agent_trajectory_backfill import backfill_agent_trajectories, render_agent_trajectory_backfill_markdown
from .agent_observability_backfill import backfill_agent_observability_audits, render_agent_observability_backfill_markdown
from .benchmark_manifest_builder import build_benchmark_manifest_set, render_benchmark_manifest_build_markdown
from .benchmark_pack_runner import run_benchmark_pack, render_benchmark_pack_run_markdown
from .citation_grounding_backfill import backfill_citation_grounding, render_citation_grounding_backfill_markdown
from .config import load_config, load_config_snapshot
from .fulltext_grounding_runner import run_fulltext_grounding, render_fulltext_grounding_run_markdown
from .gold_run_doctor import build_gold_run_doctor, render_gold_run_doctor_markdown, write_gold_run_doctor_artifacts
from .gold_run_doctor import GOLD_RUN_VERIFICATION_JSON, build_gold_run_verification_report, render_gold_run_verification_markdown, write_gold_run_verification_artifacts
from .human_gate_audit_backfill import backfill_human_gate_audits, render_human_gate_audit_backfill_markdown
from .literature_audit_backfill import backfill_literature_audits, render_literature_audit_backfill_markdown
from .manifest_backfill import backfill_run_manifests, render_manifest_backfill_markdown
from .literature_context_backfill import backfill_literature_context_artifacts, render_literature_context_backfill_markdown
from .literature_gate_backfill import backfill_literature_gate_decisions, render_literature_gate_backfill_markdown
from .literature_quality_backfill import backfill_literature_quality_artifacts, render_literature_quality_backfill_markdown
from .literature_rerank_backfill import backfill_literature_rerank_artifacts, render_literature_rerank_backfill_markdown
from .literature_rescue_backfill import backfill_literature_rescue_plans, render_literature_rescue_backfill_markdown
from .literature_search_audit_backfill import backfill_literature_search_audits, render_literature_search_audit_backfill_markdown
from .llm_observability_backfill import backfill_llm_observability, render_llm_observability_backfill_markdown
from .open_source_compliance_backfill import backfill_open_source_compliance, render_open_source_compliance_backfill_markdown
from .paper_grade_benchmark_probe import build_paper_grade_benchmark_probe, render_paper_grade_benchmark_probe_markdown, write_paper_grade_benchmark_probe_artifacts
from .paper_grade_probe import build_paper_grade_online_probe, render_paper_grade_online_probe_markdown, write_paper_grade_online_probe_artifacts
from .perfect_agent_readiness import PERFECT_AGENT_READINESS_MD, build_perfect_agent_readiness, render_perfect_agent_readiness_markdown, write_perfect_agent_readiness_artifacts
from .pipeline import approve_execution_gate, approve_review_gate, default_out_dir, request_cancel, request_review_revision, resume_pipeline_from_checkpoint, resume_pipeline_from_repair_queue, run_pipeline
from .workflow_graph import apply_rollback, build_rollback_preview, issue_rollback_preview, prune_rollback_archives, rollback_options
from .platform_audit import build_platform_audit, render_platform_audit_markdown, write_platform_audit
from .preflight import render_preflight_markdown, run_preflight
from .repair_queue_backfill import backfill_repair_queues, render_repair_queue_backfill_markdown
from .repair_resolution_backfill import backfill_repair_resolution_audits, render_repair_resolution_backfill_markdown
from .repair_resume import render_repair_resume_plan_markdown, write_repair_resume_plan_artifacts
from .repair_resume_backlog import build_repair_resume_backlog, render_repair_resume_backlog_markdown
from .repair_resume_backfill import backfill_repair_resume_plans, render_repair_resume_backfill_markdown
from .run_library import build_run_library, render_run_library_markdown, search_run_library, write_run_library
from .run_memory import build_run_memory, render_run_memory_markdown, write_run_memory
from .run_summary import build_run_dashboard, render_run_dashboard_markdown, write_run_dashboard
from .seed_paper_intake_backfill import backfill_seed_paper_intake_artifacts, render_seed_paper_intake_backfill_markdown
from .open_source_lessons import build_open_source_lessons, github_project_evidence_verifier, render_open_source_lessons_markdown, write_open_source_lessons_artifacts
from .web_server import (
    GOLD_LAUNCH_BUNDLE_JSON,
    GOLD_LAUNCH_BUNDLE_MD,
    build_gold_env_launch_kit,
    build_gold_defaults_smoke_report,
    build_gold_launch_bundle_report,
    render_gold_env_launch_kit_markdown,
    render_gold_defaults_smoke_markdown,
    render_gold_launch_bundle_markdown,
)


_GOLD_DEFAULT_CONFIG = Path("examples/uci-iris-paper-grade-config.toml")
_GOLD_DEFAULT_BENCHMARK_PACK_RUN = Path("runs/uci-iris-expanded-baseline-pack-run")
_GOLD_DEFAULT_FULLTEXT_GROUNDING_RUN = Path("runs/uci-iris-fulltext-grounding")


def _research_agent_cli_command(args: list[str]) -> str:
    return "PYTHONPATH=src " + shlex.join(["python3", "-m", "research_agent", *args])


def _print_gold_launch_human_gate_commands(out_dir: Path) -> None:
    quoted_out = str(out_dir)
    print("Check current stage:")
    print(_research_agent_cli_command(["status", quoted_out]))
    print("When state.json shows awaiting_review_approval:")
    print(
        _research_agent_cli_command(
            [
                "approve",
                quoted_out,
                "--reviewer",
                "human",
                "--notes",
                "Literature gate inspected; DOI/URL seed coverage, source health, and claim boundaries accepted for this gold run.",
            ]
        )
    )
    print("When state.json shows awaiting_execution_approval:")
    print(
        _research_agent_cli_command(
            [
                "approve-execution",
                quoted_out,
                "--reviewer",
                "human",
                "--notes",
                "Benchmark manifests, allowed commands, frozen split, and grader hash inspected.",
            ]
        )
    )


def _print_gold_launch_runtime_guidance(out_dir: Path) -> None:
    print()
    print("Gold run directory created. Keep this launch process running while human gates are approved from another terminal.")
    _print_gold_launch_human_gate_commands(out_dir)


def _print_status_next_action(run_dir: Path, state_text: str) -> None:
    try:
        state = json.loads(state_text)
    except json.JSONDecodeError:
        return
    if not isinstance(state, dict):
        return
    stage = str(state.get("stage") or "")
    quoted_out = str(run_dir)
    if stage == "awaiting_review_approval":
        print()
        print("Next action: approve the literature review gate from another terminal:")
        print(
            _research_agent_cli_command(
                [
                    "approve",
                    quoted_out,
                    "--reviewer",
                    "human",
                    "--notes",
                    "Literature gate inspected; DOI/URL seed coverage, source health, and claim boundaries accepted for this gold run.",
                ]
            )
        )
        return
    if stage == "awaiting_execution_approval":
        print()
        print("Next action: approve benchmark/local execution from another terminal:")
        print(
            _research_agent_cli_command(
                [
                    "approve-execution",
                    quoted_out,
                    "--reviewer",
                    "human",
                    "--notes",
                    "Benchmark manifests, allowed commands, frozen split, and grader hash inspected.",
                ]
            )
        )
        return
    if stage == "repair_resume_applied":
        print()
        print("Next action: rerun repair-resume with the same reviewed configuration to continue from the cleaned checkpoint:")
        print(_research_agent_cli_command(["repair-resume", quoted_out, "--apply"]))


def _print_gold_verification_repair_resume_plan(run_dir: Path, verification_json_path: Path) -> None:
    repair_report = write_repair_resume_plan_artifacts(
        run_dir,
        apply=False,
        gold_verification_report_path=verification_json_path,
    )
    print()
    print(f"Repair resume plan: {run_dir / '12-repair-resume-plan.md'}")
    print(render_repair_resume_plan_markdown(repair_report))


def _print_gold_launch_perfect_readiness(project_dir: Path, runs_dir: Path) -> None:
    report = write_perfect_agent_readiness_artifacts(project_dir, runs_dir, project_dir)
    print()
    print(f"Perfect readiness: {project_dir / PERFECT_AGENT_READINESS_MD}")
    print(
        "Perfect readiness status: "
        f"{report.status} score={report.score:.3f} "
        f"ready/review/block={report.ready_capabilities}/{report.review_capabilities}/{report.blocked_capabilities}"
    )


def _gold_run_launch_start_command(args, out_dir: Path) -> str:
    command_args: list[str] = ["gold-run-launch", "--topic", args.topic]

    def add(flag: str, value) -> None:
        if value is not None:
            command_args.extend([flag, str(value)])

    def add_each(flag: str, values) -> None:
        for value in values or []:
            text = str(value).strip()
            if text:
                command_args.extend([flag, text])

    add("--project-dir", getattr(args, "project_dir", Path(".")))
    if getattr(args, "gold_defaults", False):
        command_args.append("--gold-defaults")
    add("--config", getattr(args, "config", None))
    add("--benchmark-pack-run-dir", getattr(args, "benchmark_pack_run_dir", None))
    add("--fulltext-grounding-run-dir", getattr(args, "fulltext_grounding_run_dir", None))
    add("--llm-base-url", getattr(args, "llm_base_url", None))
    add("--llm-model", getattr(args, "llm_model", None))
    add("--literature-provider", getattr(args, "literature_provider", None))
    add("--literature-sources", getattr(args, "literature_sources", None))
    add_each("--seed-paper", getattr(args, "seed_paper", []))
    add("--seed-papers-file", getattr(args, "seed_papers_file", None))
    add_each("--fulltext-path", getattr(args, "fulltext_path", []))
    add("--max-papers", getattr(args, "max_papers", None))
    add("--max-search-queries", getattr(args, "max_search_queries", None))
    add_each("--extra-search-query", getattr(args, "extra_search_query", []))
    add("--extra-search-queries-file", getattr(args, "extra_search_queries_file", None))
    add("--execution-mode", getattr(args, "execution_mode", None))
    add("--execution-repeats", getattr(args, "execution_repeats", None))
    add_each("--benchmark-manifest", getattr(args, "benchmark_manifest", []))
    add("--release-code-repository-url", getattr(args, "release_code_repository_url", None))
    add("--release-code-archive-doi", getattr(args, "release_code_archive_doi", None))
    add("--release-code-license", getattr(args, "release_code_license", None))
    add("--release-code-version", getattr(args, "release_code_version", None))
    add("--release-data-repository-url", getattr(args, "release_data_repository_url", None))
    add("--release-data-archive-doi", getattr(args, "release_data_archive_doi", None))
    add("--release-data-access-statement", getattr(args, "release_data_access_statement", None))
    add("--release-environment-url", getattr(args, "release_environment_url", None))
    add("--release-notes", getattr(args, "release_notes", None))
    add("--out", out_dir)
    return _research_agent_cli_command(command_args)


def _fresh_gold_launch_out_hint(out_dir: Path) -> Path:
    if not out_dir.exists():
        return out_dir
    for suffix in range(2, 100):
        candidate = out_dir.with_name(f"{out_dir.name}-{suffix}")
        if not candidate.exists():
            return candidate
    return out_dir.with_name(f"{out_dir.name}-fresh")


def _print_gold_launch_dry_run_guidance(args, out_dir: Path) -> None:
    start_out_dir = _fresh_gold_launch_out_hint(out_dir)
    print()
    print("Gold launch gate ready; dry run requested, pipeline not started.")
    if start_out_dir != out_dir:
        print("Selected --out already exists; non-dry-run gold launches require a fresh output directory.")
        print(f"Suggested fresh --out: {start_out_dir}")
    print("Start this gold run with:")
    print(_gold_run_launch_start_command(args, start_out_dir))
    print()
    print("After the launch starts, approve human gates from another terminal:")
    _print_gold_launch_human_gate_commands(start_out_dir)
    print("After completion, verify:")
    print(_research_agent_cli_command(["gold-run-verify", "--run-dir", str(start_out_dir)]))
    print(_research_agent_cli_command(["perfect-readiness", "--project-dir", ".", "--runs-dir", "runs", "--no-write"]))


def _run_evaluate(run_dir):
    from .existing_results import evaluate_imported_results

    return evaluate_imported_results(run_dir)


def _print_evaluate_summary(report) -> None:
    print(f"评估报告：{report['run_dir'] / '00-import-report.json'} 与 04-experiment-decision")
    for step in report.get("steps", []):
        print(f"- {step}")
    states = report.get("decision_states") or {}
    print(f"- 决策：{report.get('decision')}")
    print(
        "- 四类状态："
        f"execution={states.get('execution_status')} evidence={states.get('evidence_status')} "
        f"outcome={states.get('research_outcome')} next={states.get('next_action')}"
    )
    print(f"- 证据（独立维度）：LLM={report.get('evidence', {}).get('llm')} 实验={report.get('evidence', {}).get('experiment')}")
    for blocker in report.get("blockers", [])[:5]:
        print(f"- 阻断：{blocker}")
    for action in report.get("next_actions", [])[:5]:
        print(f"- 下一步：{action}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="research-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_existing_parser = subparsers.add_parser(
        "import-existing",
        help="导入已有实验结果/契约/预注册（已有代码和结果入口），生成字段映射与缺失项报告",
    )
    import_existing_parser.add_argument("--run-dir", type=Path, required=True, help="目标 run 目录（不存在则创建）")
    import_existing_parser.add_argument("--results", type=Path, required=True, help="已有 04-results 格式的 JSON 文件路径")
    import_existing_parser.add_argument("--contract", type=Path, default=None, help="已有 03-idea-experiment-contract JSON（可选）")
    import_existing_parser.add_argument("--preregistration", type=Path, default=None, help="已有 03-preregistration JSON（可选）")
    import_existing_parser.add_argument("--replace", action="store_true", help="覆盖 run 目录中已有的 04-results.json")
    import_existing_parser.add_argument("--notes", default="", help="导入备注（来源、授权等）")
    import_existing_parser.add_argument("--evaluate", action="store_true", help="导入后立即生成统计比较与实验后决策（完整评审路径）")
    evaluate_imported_parser = subparsers.add_parser(
        "evaluate-imported",
        help="对已导入的已有结果生成统计比较、结果验证与实验后决策（不重新执行、不调用模型）",
    )
    evaluate_imported_parser.add_argument("--run-dir", type=Path, required=True, help="已导入结果的 run 目录")
    migrate_parser = subparsers.add_parser(
        "migrate-run",
        help="旧 Run 迁移：默认 dry-run 盘点 schema 差异；--apply 备份后标记 legacy 并使旧批准失效",
    )
    migrate_parser.add_argument("--run-dir", type=Path, required=True, help="目标 run 目录")
    migrate_parser.add_argument("--apply", action="store_true", help="显式执行迁移（默认仅 dry-run 盘点）")

    run_parser = subparsers.add_parser("run", help="Run the full research pipeline")
    run_parser.add_argument("--topic", required=True, help="Research topic or question")
    run_parser.add_argument("--out", type=Path, default=None, help="Output directory for run artifacts")
    run_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    run_parser.add_argument("--llm-provider", choices=["openai-compatible"], default=None, help="LLM provider")
    run_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:3000/v1")
    run_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name")
    run_parser.add_argument("--llm-api-key", default=None, help="OpenAI-compatible API key; prefer OPENAI_API_KEY env var so secrets are not exposed in process args")
    run_parser.add_argument("--llm-max-calls", type=int, default=None, help="Maximum LLM calls for this run; 0 means unlimited")
    run_parser.add_argument("--llm-max-prompt-chars", type=int, default=None, help="Maximum accumulated prompt characters for this run; 0 means unlimited")
    run_parser.add_argument("--llm-input-cost-per-million-tokens", type=float, default=None, help="Input token price used by run economics audit; 0 disables cost estimate")
    run_parser.add_argument("--llm-output-cost-per-million-tokens", type=float, default=None, help="Output token price used by run economics audit; 0 disables cost estimate")
    run_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode")
    run_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources: semantic_scholar,openalex,arxiv,crossref,pubmed")
    run_parser.add_argument("--semantic-scholar-api-key", default=None, help="Semantic Scholar API key for this run; not persisted in run-config")
    run_parser.add_argument("--openalex-api-key", default=None, help="OpenAlex API key for this run; not persisted in run-config")
    run_parser.add_argument("--literature-contact-email", default=None, help="Contact email sent to OpenAlex/Crossref/PubMed; not persisted in run-config")
    run_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    run_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    run_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    run_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep after deduplication")
    run_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    run_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    run_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    run_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    run_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    run_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    run_parser.add_argument("--paper-grade", action="store_true", help="Require paper-grade startup checks: online literature, DOI/URL seeds, and benchmark manifest set")
    _add_human_args(run_parser)
    _add_release_args(run_parser)

    preflight_parser = subparsers.add_parser("preflight", help="Validate configuration before starting a run")
    preflight_parser.add_argument("--topic", required=True, help="Research topic or question")
    preflight_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    preflight_parser.add_argument("--llm-provider", choices=["openai-compatible"], default=None, help="LLM provider")
    preflight_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL")
    preflight_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name")
    preflight_parser.add_argument("--llm-api-key", default=None, help="OpenAI-compatible API key; prefer OPENAI_API_KEY env var")
    preflight_parser.add_argument("--llm-max-calls", type=int, default=None, help="Maximum LLM calls for this run; 0 means unlimited")
    preflight_parser.add_argument("--llm-max-prompt-chars", type=int, default=None, help="Maximum accumulated prompt characters for this run; 0 means unlimited")
    preflight_parser.add_argument("--llm-input-cost-per-million-tokens", type=float, default=None, help="Input token price used by run economics audit; 0 disables cost estimate")
    preflight_parser.add_argument("--llm-output-cost-per-million-tokens", type=float, default=None, help="Output token price used by run economics audit; 0 disables cost estimate")
    preflight_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode")
    preflight_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    preflight_parser.add_argument("--semantic-scholar-api-key", default=None, help="Semantic Scholar API key for this preflight/run")
    preflight_parser.add_argument("--openalex-api-key", default=None, help="OpenAlex API key for this preflight/run")
    preflight_parser.add_argument("--literature-contact-email", default=None, help="Contact email sent to OpenAlex/Crossref/PubMed")
    preflight_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    preflight_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    preflight_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    preflight_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep after deduplication")
    preflight_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    preflight_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    preflight_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    preflight_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    preflight_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    preflight_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    preflight_parser.add_argument("--paper-grade", action="store_true", help="Require paper-grade startup checks: online literature, DOI/URL seeds, and benchmark manifest set")
    preflight_parser.add_argument("--no-llm-ping", action="store_true", help="Skip live LLM connectivity check")
    preflight_parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Runs directory for historical memory checks")
    preflight_parser.add_argument("--no-memory", action="store_true", help="Skip historical run memory checks")
    _add_human_args(preflight_parser)
    _add_release_args(preflight_parser)

    paper_grade_probe_parser = subparsers.add_parser("paper-grade-probe", help="Run a bounded online literature/seed metadata probe before a paper-grade run")
    paper_grade_probe_parser.add_argument("--topic", required=True, help="Research topic or question")
    paper_grade_probe_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    paper_grade_probe_parser.add_argument("--query", action="append", default=[], help="Probe search query; can be repeated")
    paper_grade_probe_parser.add_argument("--out", type=Path, default=None, help="Directory to write 00-paper-grade-online-probe artifacts")
    paper_grade_probe_parser.add_argument("--no-write", action="store_true", help="Print only; do not write probe artifacts")
    paper_grade_probe_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode")
    paper_grade_probe_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    paper_grade_probe_parser.add_argument("--literature-contact-email", default=None, help="Contact email sent to OpenAlex/Crossref/PubMed")
    paper_grade_probe_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    paper_grade_probe_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    paper_grade_probe_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep after deduplication")
    paper_grade_probe_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    _add_forbidden_cli_secret_args(paper_grade_probe_parser)

    paper_grade_benchmark_probe_parser = subparsers.add_parser("paper-grade-benchmark-probe", help="Probe benchmark manifest URLs and citation DOI/URLs before a paper-grade run")
    paper_grade_benchmark_probe_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    paper_grade_benchmark_probe_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    paper_grade_benchmark_probe_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    paper_grade_benchmark_probe_parser.add_argument("--allowed-command", action="append", default=[], help="Allowed command executable; can be repeated")
    paper_grade_benchmark_probe_parser.add_argument("--timeout-seconds", type=float, default=8.0, help="Per-URL probe timeout in seconds")
    paper_grade_benchmark_probe_parser.add_argument("--out", type=Path, default=None, help="Directory to write 00-paper-grade-benchmark-probe artifacts")
    paper_grade_benchmark_probe_parser.add_argument("--no-write", action="store_true", help="Print only; do not write probe artifacts")

    benchmark_manifest_build_parser = subparsers.add_parser("benchmark-manifest-build", help="Build candidate/baseline/ablation benchmark manifest drafts with split/grader hashes")
    benchmark_manifest_build_parser.add_argument("--out-dir", type=Path, required=True, help="Directory to write role manifest folders")
    benchmark_manifest_build_parser.add_argument("--name", required=True, help="Benchmark set name")
    benchmark_manifest_build_parser.add_argument("--benchmark-url", required=True, help="Official benchmark or task suite URL")
    benchmark_manifest_build_parser.add_argument("--dataset-url", required=True, help="Official dataset/task URL")
    benchmark_manifest_build_parser.add_argument("--dataset-version", required=True, help="Dataset or benchmark version")
    benchmark_manifest_build_parser.add_argument("--split-name", required=True, help="Frozen split/task set name")
    benchmark_manifest_build_parser.add_argument("--split-file", type=Path, required=True, help="Local frozen split/task manifest file")
    benchmark_manifest_build_parser.add_argument("--grader-file", type=Path, required=True, help="Local frozen grader/evaluation wrapper file")
    benchmark_manifest_build_parser.add_argument("--grader-version", required=True, help="Grader/evaluation protocol version")
    benchmark_manifest_build_parser.add_argument("--license", dest="license_value", required=True, help="Benchmark/data license")
    benchmark_manifest_build_parser.add_argument("--baseline", required=True, help="Primary baseline/control")
    benchmark_manifest_build_parser.add_argument("--baseline-version", required=True, help="Baseline implementation version")
    benchmark_manifest_build_parser.add_argument("--citation", required=True, help="Benchmark/data/baseline DOI, URL, or citation")
    benchmark_manifest_build_parser.add_argument("--metric", action="append", default=[], required=True, help="Metric spec name:direction:unit:description; can be repeated")
    benchmark_manifest_build_parser.add_argument("--command-template", default="python3 {grader} --role {role} --metrics {metrics_path}", help="Command template using {role}, {grader}, and {metrics_path}")
    benchmark_manifest_build_parser.add_argument("--role-command", action="append", default=[], help="Per-role command override, e.g. candidate='python3 {grader} --method ours --metrics {metrics_path}'")
    benchmark_manifest_build_parser.add_argument("--seed-policy", default="RESEARCH_AGENT_SEED fixes split/task sampling and stochastic state; RESEARCH_AGENT_REPEAT_INDEX selects repeat.", help="Seed/repeat reproducibility policy")
    benchmark_manifest_build_parser.add_argument("--min-repeats", type=int, default=3, help="Minimum repeats required by generated manifests")
    benchmark_manifest_build_parser.add_argument("--benchmark-kind", default="external", help="Benchmark kind, normally external/official/public/formal")
    benchmark_manifest_build_parser.add_argument("--note", action="append", default=[], help="Human note to include in each manifest")
    benchmark_manifest_build_parser.add_argument("--force", action="store_true", help="Overwrite existing generated files")
    benchmark_manifest_build_parser.add_argument("--no-write", action="store_true", help="Print only; do not write manifests")

    benchmark_pack_run_parser = subparsers.add_parser("benchmark-pack-run", help="Execute a candidate/baseline/ablation benchmark manifest set without a full LLM paper run")
    benchmark_pack_run_parser.add_argument("--topic", required=True, help="Benchmark run topic or label")
    benchmark_pack_run_parser.add_argument("--benchmark-manifest", action="append", default=[], required=True, help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    benchmark_pack_run_parser.add_argument("--out", type=Path, required=True, help="Output directory for benchmark run artifacts")
    benchmark_pack_run_parser.add_argument("--execution-repeats", type=int, default=3, help="Number of repeated benchmark executions per role")
    benchmark_pack_run_parser.add_argument("--allowed-command", action="append", default=[], help="Allowed command executable; can be repeated")
    benchmark_pack_run_parser.add_argument("--timeout-seconds", type=int, default=300, help="Per-command timeout in seconds")
    benchmark_pack_run_parser.add_argument("--force", action="store_true", help="Overwrite a non-empty output directory")
    benchmark_pack_run_parser.add_argument("--resume", action="store_true", help="Resume an interrupted pack run in place: keep the attempt ledger, mark dead attempts interrupted, and re-execute")

    fulltext_grounding_run_parser = subparsers.add_parser("fulltext-grounding-run", help="Build local fulltext corpus/context and verify citation grounding without a full LLM paper run")
    fulltext_grounding_run_parser.add_argument("--topic", required=True, help="Grounding run topic or label")
    fulltext_grounding_run_parser.add_argument("--fulltext-path", action="append", default=[], required=True, help="Local fulltext path (.txt/.md/.pdf); can be repeated")
    fulltext_grounding_run_parser.add_argument("--claim", default="", help="Optional claim text to ground; citation marker is appended when omitted")
    fulltext_grounding_run_parser.add_argument("--out", type=Path, required=True, help="Output directory for fulltext grounding artifacts")
    fulltext_grounding_run_parser.add_argument("--force", action="store_true", help="Overwrite a non-empty output directory")

    gold_env_launch_kit_parser = subparsers.add_parser("gold-env-launch-kit", help="Print a secret-safe local environment launch kit for Web gold runs")
    gold_env_launch_kit_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    gold_env_launch_kit_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL to place in the launch kit")
    gold_env_launch_kit_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name to place in the launch kit")
    gold_env_launch_kit_parser.add_argument("--literature-contact-email", default=None, help="Contact email field to check locally; rendered output still uses a placeholder")
    _add_forbidden_cli_secret_args(gold_env_launch_kit_parser)

    gold_defaults_smoke_parser = subparsers.add_parser("gold-defaults-smoke", help="Read-only UCI Iris gold defaults smoke check; succeeds when only server env is missing")
    gold_defaults_smoke_parser.add_argument("--topic", default="Iris classification benchmark smoke", help="Gold defaults smoke topic or label")
    gold_defaults_smoke_parser.add_argument("--project-dir", type=Path, default=Path("."), help="Project directory used to resolve benchmark manifest paths")
    _add_forbidden_cli_secret_args(gold_defaults_smoke_parser)

    gold_run_doctor_parser = subparsers.add_parser("gold-run-doctor", help="Check whether a real paper-grade gold run can be started without leaking secrets")
    gold_run_doctor_parser.add_argument("--topic", required=True, help="Gold run topic or label")
    gold_run_doctor_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    gold_run_doctor_parser.add_argument("--gold-defaults", action="store_true", help="Use this repository's UCI Iris gold config, support runs, and release defaults")
    gold_run_doctor_parser.add_argument("--benchmark-pack-run-dir", type=Path, default=None, help="Optional standalone benchmark-pack-run output directory")
    gold_run_doctor_parser.add_argument("--fulltext-grounding-run-dir", type=Path, default=None, help="Optional standalone fulltext-grounding-run output directory")
    gold_run_doctor_parser.add_argument("--candidate-run-dir", type=Path, default=None, help="Optional completed end-to-end candidate run directory to check against the gold-run contract")
    gold_run_doctor_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL for this doctor check")
    gold_run_doctor_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name for this doctor check")
    gold_run_doctor_parser.add_argument("--llm-max-calls", type=int, default=None, help="Maximum LLM calls for the generated gold run command; 0 means unlimited")
    gold_run_doctor_parser.add_argument("--llm-max-prompt-chars", type=int, default=None, help="Maximum accumulated prompt characters for the generated gold run command; 0 means unlimited")
    gold_run_doctor_parser.add_argument("--llm-input-cost-per-million-tokens", type=float, default=None, help="Input token price used by run economics audit; 0 disables cost estimate")
    gold_run_doctor_parser.add_argument("--llm-output-cost-per-million-tokens", type=float, default=None, help="Output token price used by run economics audit; 0 disables cost estimate")
    gold_run_doctor_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode for this doctor check")
    gold_run_doctor_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    gold_run_doctor_parser.add_argument("--literature-contact-email", default=None, help="Contact email for this doctor check; not persisted in doctor artifacts")
    gold_run_doctor_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    gold_run_doctor_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    gold_run_doctor_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    gold_run_doctor_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep after deduplication")
    gold_run_doctor_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    gold_run_doctor_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    gold_run_doctor_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    gold_run_doctor_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    gold_run_doctor_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    gold_run_doctor_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    gold_run_doctor_parser.add_argument("--paper-grade", action="store_true", help="Require paper-grade startup checks: online literature, DOI/URL seeds, and benchmark manifest set")
    _add_release_args(gold_run_doctor_parser)
    _add_forbidden_cli_secret_args(gold_run_doctor_parser)
    gold_run_doctor_parser.add_argument("--ping-llm", action="store_true", help="Actually call the configured OpenAI-compatible chat endpoint during doctor checks")
    gold_run_doctor_parser.add_argument("--llm-timeout-seconds", type=float, default=8.0, help="Timeout for --ping-llm connectivity check")
    gold_run_doctor_parser.add_argument("--out", type=Path, default=None, help="Directory to write 00-gold-run-doctor artifacts")
    gold_run_doctor_parser.add_argument("--no-write", action="store_true", help="Print only; do not write doctor artifacts")
    gold_run_doctor_parser.add_argument("--write-candidate-repair-resume-plan", action="store_true", help="Also write a dry-run 12-repair-resume-plan to --candidate-run-dir from candidate_gold_run.repair_plan")

    gold_launch_bundle_parser = subparsers.add_parser("gold-launch-bundle", help="Run a read-only aggregate launch check before a paper-grade gold run")
    gold_launch_bundle_parser.add_argument("--topic", required=True, help="Gold run topic or label")
    gold_launch_bundle_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    gold_launch_bundle_parser.add_argument("--gold-defaults", action="store_true", help="Use this repository's UCI Iris gold config, support runs, and release defaults")
    gold_launch_bundle_parser.add_argument("--project-dir", type=Path, default=Path("."), help="Project directory used to resolve benchmark manifest paths")
    gold_launch_bundle_parser.add_argument("--benchmark-pack-run-dir", type=Path, default=None, help="Optional standalone benchmark-pack-run output directory")
    gold_launch_bundle_parser.add_argument("--fulltext-grounding-run-dir", type=Path, default=None, help="Optional standalone fulltext-grounding-run output directory")
    gold_launch_bundle_parser.add_argument("--candidate-run-dir", type=Path, default=None, help="Optional completed end-to-end candidate run directory to check against the gold-run contract")
    gold_launch_bundle_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL override; prefer server env for real launch")
    gold_launch_bundle_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name override")
    gold_launch_bundle_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode for this bundle check")
    gold_launch_bundle_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    gold_launch_bundle_parser.add_argument("--literature-contact-email", default=None, help="Contact email for this bundle check; prefer environment for repeatable gold launches")
    gold_launch_bundle_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    gold_launch_bundle_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    gold_launch_bundle_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    gold_launch_bundle_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep after deduplication")
    gold_launch_bundle_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    gold_launch_bundle_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    gold_launch_bundle_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    gold_launch_bundle_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    gold_launch_bundle_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    gold_launch_bundle_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    gold_launch_bundle_parser.add_argument("--paper-grade", action="store_true", help="Require paper-grade startup checks: online literature, DOI/URL seeds, and benchmark manifest set")
    _add_release_args(gold_launch_bundle_parser)
    _add_forbidden_cli_secret_args(gold_launch_bundle_parser)
    gold_launch_bundle_parser.add_argument("--out", type=Path, default=None, help="Directory to write 00-gold-launch-bundle artifacts")
    gold_launch_bundle_parser.add_argument("--no-write", action="store_true", help="Print only; do not write bundle artifacts")

    gold_run_launch_parser = subparsers.add_parser("gold-run-launch", help="Strictly launch a paper-grade gold run only after the Gold Launch Bundle is ready")
    gold_run_launch_parser.add_argument("--topic", required=True, help="Gold run topic or label")
    gold_run_launch_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    gold_run_launch_parser.add_argument("--gold-defaults", action="store_true", help="Use this repository's UCI Iris gold config, support runs, and release defaults")
    gold_run_launch_parser.add_argument("--project-dir", type=Path, default=Path("."), help="Project directory used to resolve benchmark manifest paths")
    gold_run_launch_parser.add_argument("--benchmark-pack-run-dir", type=Path, default=None, help="Optional standalone benchmark-pack-run output directory")
    gold_run_launch_parser.add_argument("--fulltext-grounding-run-dir", type=Path, default=None, help="Optional standalone fulltext-grounding-run output directory")
    gold_run_launch_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL override; prefer server env for real launch")
    gold_run_launch_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name override")
    gold_run_launch_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode for this launch")
    gold_run_launch_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    gold_run_launch_parser.add_argument("--literature-contact-email", default=None, help="Contact email for this launch; prefer environment for repeatable gold launches")
    gold_run_launch_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    gold_run_launch_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    gold_run_launch_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    gold_run_launch_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep after deduplication")
    gold_run_launch_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    gold_run_launch_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    gold_run_launch_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    gold_run_launch_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    gold_run_launch_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    gold_run_launch_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    _add_release_args(gold_run_launch_parser)
    _add_forbidden_cli_secret_args(gold_run_launch_parser)
    gold_run_launch_parser.add_argument("--out", type=Path, default=None, help="Output directory for the launched gold run")
    gold_run_launch_parser.add_argument("--dry-run", action="store_true", help="Run the strict launch gate only; do not start the pipeline")

    gold_run_verify_parser = subparsers.add_parser("gold-run-verify", help="Verify a completed run directory against the paper-grade gold-run contract")
    gold_run_verify_parser.add_argument("--run-dir", type=Path, required=True, help="Completed candidate run directory")
    gold_run_verify_parser.add_argument("--out", type=Path, default=None, help="Directory to write 15-gold-run-verification artifacts; defaults to --run-dir")
    gold_run_verify_parser.add_argument("--no-write", action="store_true", help="Print only; do not write verification artifacts")
    gold_run_verify_parser.add_argument("--write-repair-resume-plan", action="store_true", help="When verification is blocked, also write a dry-run 12-repair-resume-plan from 15-gold-run-verification.json")

    status_parser = subparsers.add_parser("status", help="Print run state")
    status_parser.add_argument("run_dir", type=Path)

    summary_parser = subparsers.add_parser("summary", help="Build a cross-run summary dashboard")
    summary_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    summary_parser.add_argument("--out", type=Path, default=None, help="Directory to write runs-summary.md/json")
    summary_parser.add_argument("--limit", type=int, default=50)
    summary_parser.add_argument("--no-write", action="store_true", help="Print only; do not write summary artifacts")

    memory_parser = subparsers.add_parser("memory", help="Build cross-run memory without rebuilding the dashboard")
    memory_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    memory_parser.add_argument("--out", type=Path, default=None, help="Directory to write runs-memory.md/json")
    memory_parser.add_argument("--limit", type=int, default=50)
    memory_parser.add_argument("--no-write", action="store_true", help="Print only; do not write memory artifacts")

    library_parser = subparsers.add_parser("library", help="Build or search the local run paper library")
    library_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    library_parser.add_argument("--out", type=Path, default=None, help="Directory to write runs-library.md/json")
    library_parser.add_argument("--limit", type=int, default=50)
    library_parser.add_argument("--query", default="", help="Search query over prior run topics, papers, abstracts, and keywords")
    library_parser.add_argument("--no-write", action="store_true", help="Print only; do not write library artifacts")

    platform_audit_parser = subparsers.add_parser("platform-audit", help="Audit platform capability gaps across historical runs")
    platform_audit_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    platform_audit_parser.add_argument("--out", type=Path, default=None, help="Directory to write runs-platform-audit.md/json")
    platform_audit_parser.add_argument("--limit", type=int, default=100)
    platform_audit_parser.add_argument("--no-write", action="store_true", help="Print only; do not write platform audit artifacts")

    perfect_readiness_parser = subparsers.add_parser("perfect-readiness", help="Audit the project against the full paper-grade research-agent capability contract")
    perfect_readiness_parser.add_argument("--project-dir", type=Path, default=Path("."))
    perfect_readiness_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    perfect_readiness_parser.add_argument("--out", type=Path, default=None, help="Directory to write perfect-agent-readiness.md/json")
    perfect_readiness_parser.add_argument("--limit", type=int, default=0, help="Maximum historical runs to scan; 0 means all")
    perfect_readiness_parser.add_argument("--no-write", action="store_true", help="Print only; do not write perfect readiness artifacts")

    trajectory_backfill_parser = subparsers.add_parser("trajectory-backfill", help="Backfill 13-agent-trajectory artifacts for existing runs")
    trajectory_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    trajectory_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    trajectory_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 13-agent-trajectory artifacts")
    trajectory_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    manifest_backfill_parser = subparsers.add_parser("manifest-backfill", help="Backfill run-manifest artifacts for existing runs from artifact inventory")
    manifest_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    manifest_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    manifest_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing run-manifest artifacts")
    manifest_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    observability_backfill_parser = subparsers.add_parser("observability-backfill", help="Backfill 13-agent-observability-audit artifacts for existing runs")
    observability_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    observability_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    observability_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 13-agent-observability-audit artifacts")
    observability_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    llm_observability_backfill_parser = subparsers.add_parser("llm-observability-backfill", help="Backfill LLM trace, economics, and observability audit artifacts for existing runs")
    llm_observability_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    llm_observability_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    llm_observability_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing LLM audit artifacts")
    llm_observability_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_gate_backfill_parser = subparsers.add_parser("literature-gate-backfill", help="Backfill 01-literature-gate-decision artifacts for existing runs")
    literature_gate_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_gate_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_gate_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 01-literature-gate-decision artifacts")
    literature_gate_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_context_backfill_parser = subparsers.add_parser("literature-context-backfill", help="Backfill 01-context and related citation/gate artifacts for existing runs")
    literature_context_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_context_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_context_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing literature context artifacts")
    literature_context_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_audit_backfill_parser = subparsers.add_parser("literature-audit-backfill", help="Backfill literature metadata, coverage, and evidence-mix audits for existing runs")
    literature_audit_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_audit_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_audit_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing literature audit artifacts")
    literature_audit_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_quality_backfill_parser = subparsers.add_parser("literature-quality-backfill", help="Backfill 01-literature-quality and 01-literature-curated artifacts for existing runs")
    literature_quality_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_quality_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_quality_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing literature quality artifacts")
    literature_quality_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_rerank_backfill_parser = subparsers.add_parser("literature-rerank-backfill", help="Backfill 01-literature-rerank artifacts for existing runs")
    literature_rerank_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_rerank_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_rerank_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 01-literature-rerank artifacts")
    literature_rerank_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_rescue_backfill_parser = subparsers.add_parser("literature-rescue-backfill", help="Backfill 01-literature-rescue-plan artifacts for existing runs")
    literature_rescue_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_rescue_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_rescue_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 01-literature-rescue-plan artifacts")
    literature_rescue_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    literature_search_audit_backfill_parser = subparsers.add_parser("literature-search-audit-backfill", help="Backfill literature search strategy, source health, and query execution artifacts for existing runs")
    literature_search_audit_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    literature_search_audit_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    literature_search_audit_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing literature search audit artifacts")
    literature_search_audit_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    seed_paper_intake_backfill_parser = subparsers.add_parser("seed-paper-intake-backfill", help="Backfill conservative 01-seed-paper-intake artifacts for existing runs")
    seed_paper_intake_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    seed_paper_intake_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    seed_paper_intake_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing seed paper intake artifacts")
    seed_paper_intake_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    citation_grounding_backfill_parser = subparsers.add_parser("citation-grounding-backfill", help="Backfill 10-citation-grounding artifacts from context and revised paper")
    citation_grounding_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    citation_grounding_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    citation_grounding_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 10-citation-grounding artifacts")
    citation_grounding_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    human_gate_audit_backfill_parser = subparsers.add_parser("human-gate-audit-backfill", help="Backfill 13-human-gate-audit artifacts for existing runs")
    human_gate_audit_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    human_gate_audit_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    human_gate_audit_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 13-human-gate-audit artifacts")
    human_gate_audit_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    repair_queue_backfill_parser = subparsers.add_parser("repair-queue-backfill", help="Backfill 12-repair-queue artifacts for existing runs")
    repair_queue_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    repair_queue_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    repair_queue_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 12-repair-queue artifacts")
    repair_queue_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    repair_resume_backfill_parser = subparsers.add_parser("repair-resume-backfill", help="Backfill 12-repair-resume-plan artifacts for runs with active repair queues")
    repair_resume_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    repair_resume_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would get a repair-resume plan without changing files")
    repair_resume_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 12-repair-resume-plan artifacts")
    repair_resume_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    repair_resume_backlog_parser = subparsers.add_parser("repair-resume-backlog", help="List runs with active repair queues and pending repair-resume plans")
    repair_resume_backlog_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    repair_resume_backlog_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    repair_resolution_backfill_parser = subparsers.add_parser("repair-resolution-backfill", help="Backfill 12-repair-resolution-audit artifacts for existing repair runs")
    repair_resolution_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    repair_resolution_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    repair_resolution_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing 12-repair-resolution-audit artifacts")
    repair_resolution_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    open_source_parser = subparsers.add_parser("open-source-lessons", help="Build or refresh open-source project lesson provenance")
    open_source_parser.add_argument("--topic", required=True, help="Research topic or question")
    open_source_parser.add_argument("--out", type=Path, default=Path("."), help="Directory to write 00-open-source-lessons.md/json")
    open_source_parser.add_argument("--refresh-github", action="store_true", help="Try to refresh GitHub branch/commit/file provenance; failures are recorded as unverified")
    open_source_parser.add_argument("--github-token", default=None, help="GitHub token for higher rate limits; defaults to GITHUB_TOKEN")
    open_source_parser.add_argument("--timeout", type=float, default=5.0, help="Per-request GitHub timeout in seconds")
    open_source_parser.add_argument("--no-write", action="store_true", help="Print only; do not write artifacts")

    open_source_backfill_parser = subparsers.add_parser("open-source-compliance-backfill", help="Backfill open-source lesson and compliance artifacts for existing runs")
    open_source_backfill_parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    open_source_backfill_parser.add_argument("--dry-run", action="store_true", help="Report runs that would be written without changing files")
    open_source_backfill_parser.add_argument("--force", action="store_true", help="Rewrite existing open-source lesson and compliance artifacts")
    open_source_backfill_parser.add_argument("--limit", type=int, default=0, help="Maximum run directories with state.json to inspect; 0 means all")

    approve_parser = subparsers.add_parser("approve", help="Approve a run that is waiting at the review gate")
    approve_parser.add_argument("run_dir", type=Path)
    approve_parser.add_argument("--reviewer", default="cli")
    approve_parser.add_argument("--notes", default="")

    approve_execution_parser = subparsers.add_parser("approve-execution", help="Approve a run that is waiting before local/benchmark execution")
    approve_execution_parser.add_argument("run_dir", type=Path)
    approve_execution_parser.add_argument("--reviewer", default="cli")
    approve_execution_parser.add_argument("--notes", required=True)

    revision_parser = subparsers.add_parser("request-revision", help="Request literature review revision at the review gate")
    revision_parser.add_argument("run_dir", type=Path)
    revision_parser.add_argument("--reviewer", default="cli")
    revision_parser.add_argument("--notes", required=True)

    resume_parser = subparsers.add_parser("resume", help="Resume a run from existing checkpoint artifacts")
    resume_parser.add_argument("run_dir", type=Path)
    resume_parser.add_argument("--topic", default=None, help="Topic override; defaults to state.json topic")
    resume_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    resume_parser.add_argument("--llm-provider", choices=["openai-compatible"], default=None, help="LLM provider")
    resume_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL")
    resume_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name")
    resume_parser.add_argument("--llm-api-key", default=None, help="OpenAI-compatible API key; prefer OPENAI_API_KEY env var")
    resume_parser.add_argument("--llm-max-calls", type=int, default=None, help="Maximum LLM calls for this run; 0 means unlimited")
    resume_parser.add_argument("--llm-max-prompt-chars", type=int, default=None, help="Maximum accumulated prompt characters for this run; 0 means unlimited")
    resume_parser.add_argument("--llm-input-cost-per-million-tokens", type=float, default=None, help="Input token price used by run economics audit; 0 disables cost estimate")
    resume_parser.add_argument("--llm-output-cost-per-million-tokens", type=float, default=None, help="Output token price used by run economics audit; 0 disables cost estimate")
    resume_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode")
    resume_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    resume_parser.add_argument("--semantic-scholar-api-key", default=None, help="Semantic Scholar API key for this resumed run; not persisted in run-config")
    resume_parser.add_argument("--openalex-api-key", default=None, help="OpenAlex API key for this resumed run; not persisted in run-config")
    resume_parser.add_argument("--literature-contact-email", default=None, help="Contact email sent to OpenAlex/Crossref/PubMed; not persisted in run-config")
    resume_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    resume_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    resume_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    resume_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep")
    resume_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    resume_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    resume_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    resume_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    resume_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    resume_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    _add_human_args(resume_parser)
    _add_release_args(resume_parser)

    repair_resume_parser = subparsers.add_parser("repair-resume", help="Preview or apply 12-repair-queue.json cleanup and resume")
    repair_resume_parser.add_argument("run_dir", type=Path)
    repair_resume_parser.add_argument("--topic", default=None, help="Topic override; defaults to state.json topic")
    repair_resume_parser.add_argument("--config", type=Path, default=None, help="TOML config path")
    repair_resume_parser.add_argument("--dry-run", action="store_true", help="Preview only; kept for compatibility because preview is now the default")
    repair_resume_parser.add_argument("--apply", action="store_true", help="Delete affected artifacts and resume from the repair checkpoint")
    repair_resume_parser.add_argument("--gold-run-doctor-report", type=Path, default=None, help="Optional 00-gold-run-doctor.json to merge candidate_gold_run repair_plan into repair-resume")
    repair_resume_parser.add_argument("--gold-run-verification-report", type=Path, default=None, help="Optional 15-gold-run-verification.json to merge blocked gold verification repair_plan into repair-resume")
    repair_resume_parser.add_argument("--llm-provider", choices=["openai-compatible"], default=None, help="LLM provider")
    repair_resume_parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL")
    repair_resume_parser.add_argument("--llm-model", default=None, help="OpenAI-compatible model name")
    repair_resume_parser.add_argument("--llm-api-key", default=None, help="OpenAI-compatible API key; prefer OPENAI_API_KEY env var")
    repair_resume_parser.add_argument("--llm-max-calls", type=int, default=None, help="Maximum LLM calls for this run; 0 means unlimited")
    repair_resume_parser.add_argument("--llm-max-prompt-chars", type=int, default=None, help="Maximum accumulated prompt characters for this run; 0 means unlimited")
    repair_resume_parser.add_argument("--llm-input-cost-per-million-tokens", type=float, default=None, help="Input token price used by run economics audit; 0 disables cost estimate")
    repair_resume_parser.add_argument("--llm-output-cost-per-million-tokens", type=float, default=None, help="Output token price used by run economics audit; 0 disables cost estimate")
    repair_resume_parser.add_argument("--literature-provider", choices=["offline", "online", "auto"], default=None, help="Literature source mode")
    repair_resume_parser.add_argument("--literature-sources", default=None, help="Comma-separated online sources")
    repair_resume_parser.add_argument("--semantic-scholar-api-key", default=None, help="Semantic Scholar API key for this repair-resume run; not persisted in run-config")
    repair_resume_parser.add_argument("--openalex-api-key", default=None, help="OpenAlex API key for this repair-resume run; not persisted in run-config")
    repair_resume_parser.add_argument("--literature-contact-email", default=None, help="Contact email sent to OpenAlex/Crossref/PubMed; not persisted in run-config")
    repair_resume_parser.add_argument("--seed-paper", action="append", default=[], help="Manual seed paper DOI/URL/title; can be repeated")
    repair_resume_parser.add_argument("--seed-papers-file", type=Path, default=None, help="Text file with one seed paper DOI/URL/title per line")
    repair_resume_parser.add_argument("--fulltext-path", action="append", default=[], help="Local paper fulltext path (.txt/.md/.pdf); can be repeated")
    repair_resume_parser.add_argument("--max-papers", type=int, default=None, help="Maximum papers to keep")
    repair_resume_parser.add_argument("--max-search-queries", type=int, default=None, help="Maximum literature search queries to execute")
    repair_resume_parser.add_argument("--extra-search-query", action="append", default=[], help="Manual literature search query; can be repeated")
    repair_resume_parser.add_argument("--extra-search-queries-file", type=Path, default=None, help="Text file with one manual literature search query per line")
    repair_resume_parser.add_argument("--execution-mode", choices=["simulated", "local", "benchmark"], default=None, help="Experiment execution mode")
    repair_resume_parser.add_argument("--execution-repeats", type=int, default=None, help="Number of repeated experiment runs per command")
    repair_resume_parser.add_argument("--benchmark-manifest", action="append", default=[], help="Benchmark adapter manifest path (.json/.toml); can be repeated")
    _add_human_args(repair_resume_parser)
    _add_release_args(repair_resume_parser)

    cancel_parser = subparsers.add_parser("cancel", help="Request cancellation for a run")
    cancel_parser.add_argument("run_dir", type=Path)
    cancel_parser.add_argument("--reason", default="cli_requested")

    rollback_prune_parser = subparsers.add_parser("rollback-prune", help="Preview or apply rollback archive cleanup (ART-03)")
    rollback_prune_parser.add_argument("run_dir", type=Path)
    rollback_prune_parser.add_argument("--keep", type=int, default=3, help="Number of newest rollback archives to keep (default: 3)")
    rollback_prune_parser.add_argument("--apply", action="store_true", help="Delete the older archives; without it the command only previews")

    rollback_parser = subparsers.add_parser("rollback", help="Archive artifacts from a workflow node onward and rerun from there")
    rollback_parser.add_argument("run_dir", type=Path)
    rollback_parser.add_argument("--target", default=None, help="Workflow node to rerun from; omit to list available targets")
    rollback_parser.add_argument("--apply", action="store_true", help="Apply the rollback (archive + checkpoint resume) after previewing")
    rollback_parser.add_argument("--reason", default="", help="Why the rollback is needed; required with --apply (>= 4 chars)")
    rollback_parser.add_argument("--config", type=Path, default=None, help="TOML config path used for the resumed run")

    args = parser.parse_args(argv)
    _reject_forbidden_cli_secret_args(args)
    _apply_gold_defaults_to_args(args)
    if args.command == "import-existing":
        from .existing_results import import_existing_results

        report = import_existing_results(
            args.run_dir,
            args.results,
            contract_source=args.contract,
            preregistration_source=args.preregistration,
            replace=args.replace,
            notes=args.notes,
        )
        print(f"导入报告：{args.run_dir / '00-import-report.json'}")
        print(f"- 导入文件：{len(report.get('imported_files', []))}")
        print(f"- 缺失项：{len(report.get('missing_fields', []))}")
        for item in report.get("missing_fields", [])[:6]:
            print(f"  - {item}")
        print(f"- 警告：{len(report.get('warnings', []))}")
        evidence = report.get("evidence_assessment") or {}
        if evidence:
            print(f"- LLM 证据：{evidence.get('llm_evidence_status')}")
            print(f"- 实验证据：{evidence.get('experiment_evidence_status')}")
        print(f"- 下一步：{evidence.get('next_step') or '见导入报告'}")
        if args.evaluate:
            _print_evaluate_summary(import_existing_results.__module__ and _run_evaluate(args.run_dir))
        return

    if args.command == "evaluate-imported":
        _print_evaluate_summary(_run_evaluate(args.run_dir))
        return

    if args.command == "migrate-run":
        from .run_migration import apply_migration, plan_migration

        report = apply_migration(args.run_dir) if args.apply else plan_migration(args.run_dir)
        print(f"迁移报告（{report['mode']}）：{args.run_dir}")
        print(f"- 已迁移：{report.get('already_migrated')}")
        for finding in report.get("findings", [])[:8]:
            print(f"- 发现：{finding}")
        for action in report.get("actions", [])[:6]:
            print(f"- 动作：{action}")
        if args.apply and report.get("backup_dir"):
            print(f"- 备份：{report['backup_dir']}")
        print(f"- 说明：{report.get('note')}")
        return

    if args.command == "run":
        base_config = load_config(args.config)
        _reject_paper_grade_direct_secret_args(args, base_config)
        config = _apply_run_overrides(base_config, args)
        out_dir = args.out or default_out_dir(args.topic)
        result_dir = run_pipeline(args.topic, out_dir, config)
        print(f"Research run completed: {result_dir}")
        print(f"Paper draft: {result_dir / '06-paper.md'}")
        return
    if args.command == "preflight":
        base_config = load_config(args.config)
        _reject_paper_grade_direct_secret_args(args, base_config)
        config = _apply_run_overrides(base_config, args)
        memory = None if args.no_memory else build_run_memory(args.runs_dir, limit=100)
        report = run_preflight(args.topic, config, ping_llm=not args.no_llm_ping, run_memory=memory)
        print(render_preflight_markdown(report))
        if report.status == "fail":
            raise SystemExit(2)
        return
    if args.command == "paper-grade-probe":
        config = _apply_literature_probe_overrides(load_config(args.config), args)
        out_dir = args.out or Path("runs")
        if args.no_write:
            report = build_paper_grade_online_probe(args.topic, config, queries=args.query)
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            report = write_paper_grade_online_probe_artifacts(args.topic, config, out_dir, queries=args.query)
        print(render_paper_grade_online_probe_markdown(report))
        if report.get("status") != "pass":
            raise SystemExit(2)
        return
    if args.command == "paper-grade-benchmark-probe":
        config = _apply_benchmark_probe_overrides(load_config(args.config), args)
        out_dir = args.out or Path("runs")
        if args.no_write:
            report = build_paper_grade_benchmark_probe(config, timeout_seconds=args.timeout_seconds)
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            report = write_paper_grade_benchmark_probe_artifacts(config, out_dir, timeout_seconds=args.timeout_seconds)
        print(render_paper_grade_benchmark_probe_markdown(report))
        if report.get("status") != "pass":
            raise SystemExit(2)
        return
    if args.command == "benchmark-manifest-build":
        report = build_benchmark_manifest_set(
            out_dir=args.out_dir,
            name=args.name,
            benchmark_url=args.benchmark_url,
            dataset_url=args.dataset_url,
            dataset_version=args.dataset_version,
            split_name=args.split_name,
            split_file=args.split_file,
            grader_file=args.grader_file,
            grader_version=args.grader_version,
            license_value=args.license_value,
            baseline=args.baseline,
            baseline_version=args.baseline_version,
            citation=args.citation,
            metrics=args.metric,
            command_template=args.command_template,
            role_commands=_parse_role_commands(args.role_command),
            seed_policy=args.seed_policy,
            min_repeats=args.min_repeats,
            benchmark_kind=args.benchmark_kind,
            notes=args.note,
            write=not args.no_write,
            force=args.force,
        )
        print(render_benchmark_manifest_build_markdown(report))
        if report.get("status") != "ready":
            raise SystemExit(2)
        return
    if args.command == "benchmark-pack-run":
        report = run_benchmark_pack(
            topic=args.topic,
            manifest_paths=args.benchmark_manifest,
            out_dir=args.out,
            repeats=args.execution_repeats,
            allowed_commands=[str(item).strip() for item in args.allowed_command if str(item).strip()] or None,
            timeout_seconds=args.timeout_seconds,
            force=args.force,
            resume=args.resume,
        )
        print(render_benchmark_pack_run_markdown(report))
        if report.get("status") == "block":
            raise SystemExit(2)
        return
    if args.command == "fulltext-grounding-run":
        report = run_fulltext_grounding(
            topic=args.topic,
            fulltext_paths=args.fulltext_path,
            out_dir=args.out,
            claim=args.claim,
            force=args.force,
        )
        print(render_fulltext_grounding_run_markdown(report))
        if report.get("status") != "pass":
            raise SystemExit(2)
        return
    if args.command == "gold-env-launch-kit":
        config = _apply_gold_env_launch_kit_overrides(load_config(args.config), args)
        report = build_gold_env_launch_kit(config)
        print(render_gold_env_launch_kit_markdown(report))
        return
    if args.command == "gold-defaults-smoke":
        report = build_gold_defaults_smoke_report(args.topic, base_dir=args.project_dir)
        print(render_gold_defaults_smoke_markdown(report))
        if report.get("status") not in {"ready_to_start", "ready_except_server_environment"}:
            raise SystemExit(2)
        return
    if args.command == "gold-run-doctor":
        if args.write_candidate_repair_resume_plan and args.candidate_run_dir is None:
            raise SystemExit("--write-candidate-repair-resume-plan requires --candidate-run-dir")
        if args.write_candidate_repair_resume_plan and args.no_write:
            raise SystemExit("--write-candidate-repair-resume-plan cannot be used with --no-write")
        config = _apply_gold_run_doctor_overrides(load_config(args.config), args)
        if args.no_write:
            report = build_gold_run_doctor(
                topic=args.topic,
                config=config,
                config_path=args.config,
                benchmark_pack_run_dir=args.benchmark_pack_run_dir,
                fulltext_grounding_run_dir=args.fulltext_grounding_run_dir,
                candidate_run_dir=args.candidate_run_dir,
                ping_llm=args.ping_llm,
                llm_timeout_seconds=args.llm_timeout_seconds,
            )
        else:
            out_dir = args.out or Path("runs")
            out_dir.mkdir(parents=True, exist_ok=True)
            report = write_gold_run_doctor_artifacts(
                topic=args.topic,
                config=config,
                config_path=args.config,
                out_dir=out_dir,
                benchmark_pack_run_dir=args.benchmark_pack_run_dir,
                fulltext_grounding_run_dir=args.fulltext_grounding_run_dir,
                candidate_run_dir=args.candidate_run_dir,
                ping_llm=args.ping_llm,
                llm_timeout_seconds=args.llm_timeout_seconds,
                write_candidate_repair_resume_plan=args.write_candidate_repair_resume_plan,
            )
        print(render_gold_run_doctor_markdown(report))
        if report.get("status") == "blocked":
            raise SystemExit(2)
        return
    if args.command == "gold-launch-bundle":
        config = _apply_gold_run_doctor_overrides(load_config(args.config), args)
        report = build_gold_launch_bundle_report(
            args.topic,
            config,
            benchmark_pack_run_dir=args.benchmark_pack_run_dir,
            fulltext_grounding_run_dir=args.fulltext_grounding_run_dir,
            candidate_run_dir=args.candidate_run_dir,
            base_dir=args.project_dir,
        )
        markdown = render_gold_launch_bundle_markdown(report)
        if not args.no_write:
            out_dir = args.out or Path("runs")
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(out_dir / "00-gold-launch-bundle.json", report)
            write_text(out_dir / "00-gold-launch-bundle.md", markdown)
        print(markdown)
        if report.get("status") != "ready_to_start" or report.get("can_start_gold_run") is not True:
            raise SystemExit(2)
        return
    if args.command == "gold-run-launch":
        config = _apply_gold_run_doctor_overrides(load_config(args.config), args)
        config = replace(config, paper_grade=replace(config.paper_grade, enabled=True))
        launch_out_dir = args.out or default_out_dir(args.topic)
        if not args.dry_run and launch_out_dir.exists():
            print(f"Output path already exists: {launch_out_dir}", file=sys.stderr)
            print(
                "Pick a fresh --out directory or archive/remove the previous run before launching a paper-grade gold run.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        report = build_gold_launch_bundle_report(
            args.topic,
            config,
            benchmark_pack_run_dir=args.benchmark_pack_run_dir,
            fulltext_grounding_run_dir=args.fulltext_grounding_run_dir,
            candidate_run_dir=None,
            base_dir=args.project_dir,
        )
        markdown = render_gold_launch_bundle_markdown(report)
        print(markdown)
        if report.get("status") != "ready_to_start" or report.get("can_start_gold_run") is not True:
            raise SystemExit(2)
        if args.dry_run:
            _print_gold_launch_dry_run_guidance(args, launch_out_dir)
            return
        out_dir = launch_out_dir
        try:
            out_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            print(f"Output path already exists: {out_dir}", file=sys.stderr)
            print(
                "Pick a fresh --out directory or archive/remove the previous run before launching a paper-grade gold run.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        write_json(out_dir / GOLD_LAUNCH_BUNDLE_JSON, report)
        write_text(out_dir / GOLD_LAUNCH_BUNDLE_MD, markdown)
        _print_gold_launch_runtime_guidance(out_dir)
        result_dir = run_pipeline(args.topic, out_dir, config)
        verification = write_gold_run_verification_artifacts(result_dir)
        print()
        print(f"Gold research run completed: {result_dir}")
        print(f"Gold verification: {result_dir / '15-gold-run-verification.md'}")
        print()
        print(render_gold_run_verification_markdown(verification))
        if verification.get("status") == "blocked":
            _print_gold_verification_repair_resume_plan(result_dir, result_dir / GOLD_RUN_VERIFICATION_JSON)
        _print_gold_launch_perfect_readiness(args.project_dir, result_dir.parent)
        if verification.get("status") == "blocked":
            raise SystemExit(2)
        return
    if args.command == "gold-run-verify":
        if args.no_write and args.write_repair_resume_plan:
            print("--write-repair-resume-plan requires writing 15-gold-run-verification.json; remove --no-write.", file=sys.stderr)
            raise SystemExit(2)
        if args.no_write:
            report = build_gold_run_verification_report(args.run_dir)
            verification_json_path = None
        else:
            report = write_gold_run_verification_artifacts(args.run_dir, out_dir=args.out)
            verification_json_path = (args.out or args.run_dir) / GOLD_RUN_VERIFICATION_JSON
        print(render_gold_run_verification_markdown(report))
        if args.write_repair_resume_plan and report.get("status") == "blocked" and verification_json_path is not None:
            _print_gold_verification_repair_resume_plan(args.run_dir, verification_json_path)
        if report.get("status") == "blocked":
            raise SystemExit(2)
        return
    if args.command == "status":
        state_path = args.run_dir / "state.json"
        if not state_path.exists():
            print(f"No state.json found in {args.run_dir}", file=sys.stderr)
            raise SystemExit(1)
        state_text = state_path.read_text(encoding="utf-8").strip()
        print(state_text)
        _print_status_next_action(args.run_dir, state_text)
        return
    if args.command == "summary":
        dashboard = build_run_dashboard(args.runs_dir, limit=args.limit)
        memory = build_run_memory(args.runs_dir, limit=args.limit)
        if not args.no_write:
            out_dir = args.out or args.runs_dir
            write_run_dashboard(dashboard, out_dir)
            write_run_memory(memory, out_dir)
        print(render_run_dashboard_markdown(dashboard))
        print()
        print(render_run_memory_markdown(memory))
        return
    if args.command == "memory":
        memory = build_run_memory(args.runs_dir, limit=args.limit)
        if not args.no_write:
            out_dir = args.out or args.runs_dir
            write_run_memory(memory, out_dir)
        print(render_run_memory_markdown(memory))
        return
    if args.command == "library":
        library = build_run_library(args.runs_dir, limit=args.limit)
        results = search_run_library(library, args.query, limit=args.limit) if args.query else None
        if not args.no_write:
            out_dir = args.out or args.runs_dir
            write_run_library(library, out_dir)
        print(render_run_library_markdown(library, query=args.query, results=results))
        return
    if args.command == "platform-audit":
        report = build_platform_audit(args.runs_dir, limit=args.limit)
        if not args.no_write:
            out_dir = args.out or args.runs_dir
            write_platform_audit(report, out_dir)
        print(render_platform_audit_markdown(report))
        return
    if args.command == "perfect-readiness":
        if args.no_write:
            report = build_perfect_agent_readiness(args.project_dir, args.runs_dir, limit=args.limit)
        else:
            out_dir = args.out or args.project_dir
            report = write_perfect_agent_readiness_artifacts(args.project_dir, args.runs_dir, out_dir, limit=args.limit)
        print(render_perfect_agent_readiness_markdown(report))
        return
    if args.command == "trajectory-backfill":
        report = backfill_agent_trajectories(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_agent_trajectory_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "manifest-backfill":
        report = backfill_run_manifests(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_manifest_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "observability-backfill":
        report = backfill_agent_observability_audits(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_agent_observability_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "llm-observability-backfill":
        report = backfill_llm_observability(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_llm_observability_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-gate-backfill":
        report = backfill_literature_gate_decisions(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_gate_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-context-backfill":
        report = backfill_literature_context_artifacts(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_context_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-audit-backfill":
        report = backfill_literature_audits(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_audit_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-quality-backfill":
        report = backfill_literature_quality_artifacts(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_quality_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-rerank-backfill":
        report = backfill_literature_rerank_artifacts(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_rerank_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-rescue-backfill":
        report = backfill_literature_rescue_plans(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_rescue_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "literature-search-audit-backfill":
        report = backfill_literature_search_audits(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_literature_search_audit_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "seed-paper-intake-backfill":
        report = backfill_seed_paper_intake_artifacts(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_seed_paper_intake_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "citation-grounding-backfill":
        report = backfill_citation_grounding(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_citation_grounding_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "human-gate-audit-backfill":
        report = backfill_human_gate_audits(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_human_gate_audit_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "repair-queue-backfill":
        report = backfill_repair_queues(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_repair_queue_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "repair-resume-backfill":
        report = backfill_repair_resume_plans(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_repair_resume_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "repair-resume-backlog":
        report = build_repair_resume_backlog(args.runs_dir, limit=args.limit)
        print(render_repair_resume_backlog_markdown(report))
        return
    if args.command == "repair-resolution-backfill":
        report = backfill_repair_resolution_audits(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_repair_resolution_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "open-source-lessons":
        verifier = github_project_evidence_verifier(timeout_seconds=args.timeout, token=args.github_token) if args.refresh_github else None
        report = build_open_source_lessons(args.topic, verifier=verifier) if args.no_write else write_open_source_lessons_artifacts(args.topic, args.out, verifier=verifier)
        print(render_open_source_lessons_markdown(report))
        return
    if args.command == "open-source-compliance-backfill":
        report = backfill_open_source_compliance(args.runs_dir, dry_run=args.dry_run, force=args.force, limit=args.limit)
        print(render_open_source_compliance_backfill_markdown(report))
        if report.get("errors"):
            raise SystemExit(1)
        return
    if args.command == "approve":
        try:
            approval = approve_review_gate(args.run_dir, reviewer=args.reviewer, notes=args.notes)
        except (FileNotFoundError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Approved: {args.run_dir}")
        print(f"approved_at: {approval.get('approved_at')}")
        return
    if args.command == "approve-execution":
        try:
            approval = approve_execution_gate(args.run_dir, reviewer=args.reviewer, notes=args.notes)
        except (FileNotFoundError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Execution approved: {args.run_dir}")
        print(f"approved_at: {approval.get('approved_at')}")
        return
    if args.command == "request-revision":
        try:
            approval = request_review_revision(args.run_dir, reviewer=args.reviewer, notes=args.notes)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Revision requested: {args.run_dir}")
        print(f"revision_requested_at: {approval.get('revision_requested_at')}")
        return
    if args.command == "resume":
        config = _apply_run_overrides(_load_resume_base_config(args.run_dir, args.config), args)
        topic = args.topic or _topic_from_state(args.run_dir)
        result_dir = resume_pipeline_from_checkpoint(topic, args.run_dir, config)
        print(f"Research run resumed: {result_dir}")
        print(f"Paper draft: {result_dir / '06-paper.md'}")
        return
    if args.command == "repair-resume":
        if args.apply and args.dry_run:
            print("--apply cannot be used with --dry-run", file=sys.stderr)
            raise SystemExit(2)
        if not args.apply:
            report = write_repair_resume_plan_artifacts(
                args.run_dir,
                apply=False,
                doctor_report_path=args.gold_run_doctor_report,
                gold_verification_report_path=args.gold_run_verification_report,
            )
            print(render_repair_resume_plan_markdown(report))
            if report.get("can_resume") is not True:
                raise SystemExit(1)
            print("Preview only: add --apply after reviewing 12-repair-resume-plan.md to delete artifacts and resume.")
            return
        config = _apply_run_overrides(_load_resume_base_config(args.run_dir, args.config), args)
        topic = args.topic or _topic_from_state(args.run_dir)
        result_dir = resume_pipeline_from_repair_queue(
            topic,
            args.run_dir,
            config,
            doctor_report_path=args.gold_run_doctor_report,
            gold_verification_report_path=args.gold_run_verification_report,
        )
        print(f"Research run repair-resumed: {result_dir}")
        print(f"Repair resume plan: {result_dir / '12-repair-resume-plan.md'}")
        return
    if args.command == "cancel":
        cancel = request_cancel(args.run_dir, requester="cli", reason=args.reason)
        print(f"Cancel requested: {args.run_dir}")
        print(f"requested_at: {cancel.get('requested_at')}")
        return
    if args.command == "rollback-prune":
        report = prune_rollback_archives(args.run_dir, keep=args.keep, apply=args.apply)
        print(f"归档总数：{len(report['archives'])}；将保留：{len(report['kept'])}")
        for item in report["archives"]:
            marker = "（已删除）" if item["archive_ref"] in report["removed"] else "（保留）"
            print(f"- {item['archive_ref']}  {item['bytes']} 字节  {marker}")
        if not args.apply:
            print("Preview only: add --apply to delete the marked archives.")
        return
    if args.command == "rollback":
        if not args.target:
            options = rollback_options(args.run_dir)
            if not options:
                print(f"No rollback targets: {args.run_dir}", file=sys.stderr)
                raise SystemExit(1)
            print("可回退目标（--target）：")
            for option in options:
                print(f"- {option['target']}  {option['title']}（{option['role']}）")
            return
        if args.apply and len(str(args.reason).strip()) < 4:
            print("--apply requires --reason with at least 4 characters", file=sys.stderr)
            raise SystemExit(2)
        if not args.apply:
            preview = build_rollback_preview(args.run_dir, args.target)
            print(f"回退目标：{preview['target']}（revision {preview['current_revision']} -> {preview['next_revision']}）")
            print(f"将归档文件：{preview['file_count']} 个 / {preview['total_bytes']} 字节")
            if preview["review_reapproval_required"]:
                print("注意：回退到文献链之前，恢复后会重新等待人工 review 审批。")
            if preview["execution_reapproval_required"]:
                print("注意：回退到实验执行之前，恢复后会重新等待执行审批。")
            for blocker in preview["blockers"]:
                print(f"阻断：{blocker}")
            if preview["blockers"]:
                raise SystemExit(1)
            print("Preview only: add --apply --reason '...' to archive these artifacts and resume.")
            return
        preview = issue_rollback_preview(args.run_dir, args.target)
        report = apply_rollback(args.run_dir, args.target, preview["preview_id"], preview["preview_token"], reason=str(args.reason).strip(), actor="cli")
        print(f"Rollback applied: {report['archive_ref']}")
        config = _apply_run_overrides(_load_resume_base_config(args.run_dir, args.config), args)
        topic = _topic_from_state(args.run_dir)
        result_dir = resume_pipeline_from_checkpoint(topic, args.run_dir, config)
        print(f"Research run resumed after rollback: {result_dir}")
        return
    raise SystemExit(f"Unknown command: {args.command}")


def _apply_run_overrides(config, args):
    llm = config.llm
    if args.llm_provider is not None:
        llm = replace(llm, provider=args.llm_provider)
    if args.llm_base_url is not None:
        llm = replace(llm, base_url=args.llm_base_url)
    if args.llm_model is not None:
        llm = replace(llm, model=args.llm_model)
    if args.llm_api_key is not None:
        llm = replace(llm, api_key=args.llm_api_key)
    if args.llm_max_calls is not None:
        llm = replace(llm, max_calls=args.llm_max_calls)
    if args.llm_max_prompt_chars is not None:
        llm = replace(llm, max_prompt_chars=args.llm_max_prompt_chars)
    if getattr(args, "llm_input_cost_per_million_tokens", None) is not None:
        llm = replace(llm, input_cost_per_million_tokens=args.llm_input_cost_per_million_tokens)
    if getattr(args, "llm_output_cost_per_million_tokens", None) is not None:
        llm = replace(llm, output_cost_per_million_tokens=args.llm_output_cost_per_million_tokens)
    if llm is not config.llm:
        config = replace(config, llm=llm)

    literature = config.literature
    if args.literature_provider is not None:
        literature = replace(literature, provider=args.literature_provider)
    if args.literature_sources:
        literature = replace(literature, sources=_parse_csv(args.literature_sources))
    if getattr(args, "semantic_scholar_api_key", None) is not None:
        literature = replace(literature, semantic_scholar_api_key=args.semantic_scholar_api_key)
    if getattr(args, "openalex_api_key", None) is not None:
        literature = replace(literature, openalex_api_key=args.openalex_api_key)
    if getattr(args, "literature_contact_email", None) is not None:
        literature = replace(literature, contact_email=args.literature_contact_email)
    seed_papers = _seed_entries_from_args(args)
    if seed_papers:
        literature = replace(literature, seed_papers=[*literature.seed_papers, *seed_papers])
    fulltext_paths = [str(item).strip() for item in getattr(args, "fulltext_path", []) if str(item).strip()]
    if fulltext_paths:
        literature = replace(literature, fulltext_paths=[*literature.fulltext_paths, *fulltext_paths])
    if args.max_papers is not None:
        literature = replace(literature, max_papers=args.max_papers)
    if getattr(args, "max_search_queries", None) is not None:
        literature = replace(literature, max_search_queries=args.max_search_queries)
    extra_search_queries = _extra_search_queries_from_args(args)
    if extra_search_queries:
        literature = replace(literature, extra_search_queries=[*literature.extra_search_queries, *extra_search_queries])
    if literature is not config.literature:
        config = replace(config, literature=literature)
    execution = config.execution
    if args.execution_mode is not None:
        execution = replace(execution, mode=args.execution_mode)
    if args.execution_repeats is not None:
        execution = replace(execution, repeats=args.execution_repeats)
    benchmark_manifests = [str(item).strip() for item in getattr(args, "benchmark_manifest", []) if str(item).strip()]
    if benchmark_manifests:
        execution = replace(execution, benchmark_manifest_paths=[*execution.benchmark_manifest_paths, *benchmark_manifests])
    if execution is not config.execution:
        config = replace(config, execution=execution)
    if getattr(args, "paper_grade", False):
        config = replace(config, paper_grade=replace(config.paper_grade, enabled=True))
    release = config.release
    release_overrides = {
        "release_code_repository_url": "code_repository_url",
        "release_code_archive_doi": "code_archive_doi",
        "release_code_license": "code_license",
        "release_code_version": "code_version",
        "release_data_repository_url": "data_repository_url",
        "release_data_archive_doi": "data_archive_doi",
        "release_data_access_statement": "data_access_statement",
        "release_environment_url": "environment_url",
        "release_notes": "release_notes",
    }
    updates = {field: str(getattr(args, arg_name)).strip() for arg_name, field in release_overrides.items() if getattr(args, arg_name, None)}
    if updates:
        release = replace(release, **updates)
    if release is not config.release:
        config = replace(config, release=release)
    human = config.human
    if getattr(args, "human_note", []):
        human = replace(human, notes=[*human.notes, *_arg_list(args, "human_note")])
    if getattr(args, "human_constraint", []):
        human = replace(human, constraints=[*human.constraints, *_arg_list(args, "human_constraint")])
    if getattr(args, "human_success_criterion", []):
        human = replace(human, success_criteria=[*human.success_criteria, *_arg_list(args, "human_success_criterion")])
    if getattr(args, "human_resource_limit", []):
        human = replace(human, resource_limits=[*human.resource_limits, *_arg_list(args, "human_resource_limit")])
    if getattr(args, "human_risk", []):
        human = replace(human, risks=[*human.risks, *_arg_list(args, "human_risk")])
    if human is not config.human:
        config = replace(config, human=human)
    return config


def _load_resume_base_config(run_dir: Path, config_path: Path | None):
    if config_path is not None:
        return load_config(config_path)
    snapshot = run_dir / "run-config.json"
    if snapshot.exists():
        return load_config_snapshot(snapshot)
    return load_config(None)


def _apply_benchmark_probe_overrides(config, args):
    execution = config.execution
    manifests = [str(item).strip() for item in getattr(args, "benchmark_manifest", []) if str(item).strip()]
    if manifests:
        execution = replace(execution, mode="benchmark", benchmark_manifest_paths=[*execution.benchmark_manifest_paths, *manifests])
    elif execution.benchmark_manifest_paths:
        execution = replace(execution, mode="benchmark")
    if getattr(args, "execution_repeats", None) is not None:
        execution = replace(execution, repeats=args.execution_repeats)
    allowed = [str(item).strip() for item in getattr(args, "allowed_command", []) if str(item).strip()]
    if allowed:
        execution = replace(execution, allowed_commands=allowed)
    if execution is not config.execution:
        config = replace(config, execution=execution)
    return config


def _apply_gold_env_launch_kit_overrides(config, args):
    llm = config.llm
    if getattr(args, "llm_base_url", None) is not None:
        llm = replace(llm, base_url=args.llm_base_url)
    if getattr(args, "llm_model", None) is not None:
        llm = replace(llm, model=args.llm_model)
    if llm is not config.llm:
        config = replace(config, llm=llm)
    if getattr(args, "literature_contact_email", None) is not None:
        literature = replace(config.literature, contact_email=args.literature_contact_email)
        config = replace(config, literature=literature)
    return config


def _apply_gold_defaults_to_args(args) -> None:
    if not getattr(args, "gold_defaults", False):
        return
    project_dir = Path(getattr(args, "project_dir", Path(".")) or Path("."))
    config_path = project_dir / _GOLD_DEFAULT_CONFIG
    benchmark_run = project_dir / _GOLD_DEFAULT_BENCHMARK_PACK_RUN
    fulltext_run = project_dir / _GOLD_DEFAULT_FULLTEXT_GROUNDING_RUN
    missing = [path for path in [config_path, benchmark_run, fulltext_run] if not path.exists()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise SystemExit(f"--gold-defaults missing required local inputs: {joined}")
    if getattr(args, "config", None) is None:
        args.config = config_path
    if getattr(args, "benchmark_pack_run_dir", None) is None:
        args.benchmark_pack_run_dir = benchmark_run
    if getattr(args, "fulltext_grounding_run_dir", None) is None:
        args.fulltext_grounding_run_dir = fulltext_run
    if hasattr(args, "paper_grade"):
        args.paper_grade = True
    release_overrides = build_gold_env_launch_kit(load_config(config_path))["release_overrides"]
    for name, value in release_overrides.items():
        if getattr(args, name, None) is None:
            setattr(args, name, value)


def _apply_gold_run_doctor_overrides(config, args):
    llm = config.llm
    if getattr(args, "llm_base_url", None) is not None:
        llm = replace(llm, base_url=args.llm_base_url)
    if getattr(args, "llm_model", None) is not None:
        llm = replace(llm, model=args.llm_model)
    if getattr(args, "llm_api_key", None) is not None:
        llm = replace(llm, api_key=args.llm_api_key)
    if getattr(args, "llm_max_calls", None) is not None:
        llm = replace(llm, max_calls=args.llm_max_calls)
    if getattr(args, "llm_max_prompt_chars", None) is not None:
        llm = replace(llm, max_prompt_chars=args.llm_max_prompt_chars)
    if getattr(args, "llm_input_cost_per_million_tokens", None) is not None:
        llm = replace(llm, input_cost_per_million_tokens=args.llm_input_cost_per_million_tokens)
    if getattr(args, "llm_output_cost_per_million_tokens", None) is not None:
        llm = replace(llm, output_cost_per_million_tokens=args.llm_output_cost_per_million_tokens)
    if llm is not config.llm:
        config = replace(config, llm=llm)

    literature = config.literature
    if getattr(args, "literature_provider", None) is not None:
        literature = replace(literature, provider=args.literature_provider)
    if getattr(args, "literature_sources", None):
        literature = replace(literature, sources=_parse_csv(args.literature_sources))
    if getattr(args, "literature_contact_email", None) is not None:
        literature = replace(literature, contact_email=args.literature_contact_email)
    if getattr(args, "semantic_scholar_api_key", None) is not None:
        literature = replace(literature, semantic_scholar_api_key=args.semantic_scholar_api_key)
    if getattr(args, "openalex_api_key", None) is not None:
        literature = replace(literature, openalex_api_key=args.openalex_api_key)
    seed_papers = _seed_entries_from_args(args)
    if seed_papers:
        literature = replace(literature, seed_papers=[*literature.seed_papers, *seed_papers])
    fulltext_paths = [str(item).strip() for item in getattr(args, "fulltext_path", []) if str(item).strip()]
    if fulltext_paths:
        literature = replace(literature, fulltext_paths=[*literature.fulltext_paths, *fulltext_paths])
    if getattr(args, "max_papers", None) is not None:
        literature = replace(literature, max_papers=args.max_papers)
    if getattr(args, "max_search_queries", None) is not None:
        literature = replace(literature, max_search_queries=args.max_search_queries)
    extra_search_queries = _extra_search_queries_from_args(args)
    if extra_search_queries:
        literature = replace(literature, extra_search_queries=[*literature.extra_search_queries, *extra_search_queries])
    if literature is not config.literature:
        config = replace(config, literature=literature)
    execution = config.execution
    if getattr(args, "execution_mode", None) is not None:
        execution = replace(execution, mode=args.execution_mode)
    if getattr(args, "execution_repeats", None) is not None:
        execution = replace(execution, repeats=args.execution_repeats)
    benchmark_manifests = [str(item).strip() for item in getattr(args, "benchmark_manifest", []) if str(item).strip()]
    if benchmark_manifests:
        execution = replace(execution, benchmark_manifest_paths=[*execution.benchmark_manifest_paths, *benchmark_manifests])
    if execution is not config.execution:
        config = replace(config, execution=execution)
    if getattr(args, "paper_grade", False):
        config = replace(config, paper_grade=replace(config.paper_grade, enabled=True))
    config = _apply_release_overrides(config, args)
    return config


def _apply_release_overrides(config, args):
    release = config.release
    release_overrides = {
        "release_code_repository_url": "code_repository_url",
        "release_code_archive_doi": "code_archive_doi",
        "release_code_license": "code_license",
        "release_code_version": "code_version",
        "release_data_repository_url": "data_repository_url",
        "release_data_archive_doi": "data_archive_doi",
        "release_data_access_statement": "data_access_statement",
        "release_environment_url": "environment_url",
        "release_notes": "release_notes",
    }
    updates = {field: str(getattr(args, arg_name)).strip() for arg_name, field in release_overrides.items() if getattr(args, arg_name, None)}
    if updates:
        release = replace(release, **updates)
    return replace(config, release=release) if release is not config.release else config


def _apply_literature_probe_overrides(config, args):
    literature = config.literature
    if args.literature_provider is not None:
        literature = replace(literature, provider=args.literature_provider)
    if args.literature_sources:
        literature = replace(literature, sources=_parse_csv(args.literature_sources))
    if getattr(args, "semantic_scholar_api_key", None) is not None:
        literature = replace(literature, semantic_scholar_api_key=args.semantic_scholar_api_key)
    if getattr(args, "openalex_api_key", None) is not None:
        literature = replace(literature, openalex_api_key=args.openalex_api_key)
    if getattr(args, "literature_contact_email", None) is not None:
        literature = replace(literature, contact_email=args.literature_contact_email)
    seed_papers = _seed_entries_from_args(args)
    if seed_papers:
        literature = replace(literature, seed_papers=[*literature.seed_papers, *seed_papers])
    if args.max_papers is not None:
        literature = replace(literature, max_papers=args.max_papers)
    if args.max_search_queries is not None:
        literature = replace(literature, max_search_queries=args.max_search_queries)
    return replace(config, literature=literature) if literature is not config.literature else config


def _add_human_args(parser) -> None:
    parser.add_argument("--human-note", action="append", default=[], help="Human research note or preference; can be repeated")
    parser.add_argument("--human-constraint", action="append", default=[], help="Human constraint that planning/ideas/experiments must respect; can be repeated")
    parser.add_argument("--human-success-criterion", action="append", default=[], help="Human-defined success criterion; can be repeated")
    parser.add_argument("--human-resource-limit", action="append", default=[], help="Compute, budget, data, or timing limit; can be repeated")
    parser.add_argument("--human-risk", action="append", default=[], help="Known risk or negative direction to watch; can be repeated")


def _add_release_args(parser) -> None:
    parser.add_argument("--release-code-repository-url", default=None, help="Public code repository URL")
    parser.add_argument("--release-code-archive-doi", default=None, help="Code archive DOI or stable URL")
    parser.add_argument("--release-code-license", default=None, help="Code license, e.g. MIT")
    parser.add_argument("--release-code-version", default=None, help="Release tag, version, or commit SHA")
    parser.add_argument("--release-data-repository-url", default=None, help="Public data repository URL")
    parser.add_argument("--release-data-archive-doi", default=None, help="Data archive DOI or accession")
    parser.add_argument("--release-data-access-statement", default=None, help="Data access conditions or no-external-data statement")
    parser.add_argument("--release-environment-url", default=None, help="Docker/Conda/environment archive URL")
    parser.add_argument("--release-notes", default=None, help="Release scope, limitations, and manual verification notes")


def _add_forbidden_cli_secret_args(parser) -> None:
    parser.add_argument("--llm-api-key", dest="_forbidden_llm_api_key", nargs="?", const=True, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--semantic-scholar-api-key",
        dest="_forbidden_semantic_scholar_api_key",
        nargs="?",
        const=True,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--openalex-api-key", dest="_forbidden_openalex_api_key", nargs="?", const=True, default=None, help=argparse.SUPPRESS)


def _reject_forbidden_cli_secret_args(args) -> None:
    forbidden = {
        "--llm-api-key": "_forbidden_llm_api_key",
        "--semantic-scholar-api-key": "_forbidden_semantic_scholar_api_key",
        "--openalex-api-key": "_forbidden_openalex_api_key",
    }
    used = [flag for flag, name in forbidden.items() if getattr(args, name, None) is not None]
    if used:
        flags = ", ".join(used)
        print(f"{args.command}: do not pass secret values via CLI arguments ({flags}); set the corresponding environment variables instead.", file=sys.stderr)
        raise SystemExit(2)


def _reject_paper_grade_direct_secret_args(args, config) -> None:
    if not (getattr(args, "paper_grade", False) or getattr(getattr(config, "paper_grade", None), "enabled", False)):
        return
    used = _direct_cli_secret_flags(args)
    if used:
        flags = ", ".join(used)
        print(f"{args.command}: paper-grade runs require env-only secret handling; remove CLI secret arguments ({flags}).", file=sys.stderr)
        raise SystemExit(2)


def _direct_cli_secret_flags(args) -> list[str]:
    secret_args = {
        "--llm-api-key": "llm_api_key",
        "--semantic-scholar-api-key": "semantic_scholar_api_key",
        "--openalex-api-key": "openalex_api_key",
    }
    return [flag for flag, name in secret_args.items() if getattr(args, name, None) is not None]


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _seed_entries_from_args(args) -> list[str]:
    entries = [str(item).strip() for item in getattr(args, "seed_paper", []) if str(item).strip()]
    path = getattr(args, "seed_papers_file", None)
    if path is not None:
        entries.extend(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return entries


def _extra_search_queries_from_args(args) -> list[str]:
    entries = [str(item).strip() for item in getattr(args, "extra_search_query", []) if str(item).strip()]
    path = getattr(args, "extra_search_queries_file", None)
    if path is not None:
        entries.extend(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return entries


def _parse_role_commands(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        role, sep, command = str(raw).partition("=")
        role = role.strip().lower()
        command = command.strip()
        if sep and role and command:
            result[role] = command
    return result


def _arg_list(args, name: str) -> list[str]:
    return [str(item).strip() for item in getattr(args, name, []) if str(item).strip()]


def _topic_from_state(run_dir: Path) -> str:
    state_path = run_dir / "state.json"
    if not state_path.exists():
        return run_dir.name
    try:
        import json

        data = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return run_dir.name
    if not isinstance(data, dict):
        return run_dir.name
    return str(data.get("topic") or run_dir.name)


if __name__ == "__main__":
    main()
