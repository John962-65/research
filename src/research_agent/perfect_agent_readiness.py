from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import hashlib
import json
import os
import re
import socket
import tomllib

from .artifacts import write_json, write_text, cell as _cell, read_json_dict as _read_json
from .benchmark_plan import _domain_candidates
from .config import PaperGradeConfig, load_config
from .gold_run_doctor import (
    _gold_manifest_inventory_check,
    _gold_required_artifact_hashes,
    _gold_run_secret_scan,
    _gold_unsafe_required_artifacts,
    build_gold_environment_lint,
)
from .run_summary import RunSummary, build_run_dashboard
from .submission_package_zip import submission_package_zip_blocking_issue


PERFECT_AGENT_READINESS_JSON = "perfect-agent-readiness.json"
PERFECT_AGENT_READINESS_MD = "perfect-agent-readiness.md"
_ROLES = {"candidate", "baseline", "ablation"}
_DEFAULT_GOLD_GATEWAY_BASE_URL = "http://127.0.0.1:8317"
_GOLD_VERIFICATION_REQUIRED_ARTIFACTS = [
    "state.json",
    "run-config.json",
    "run-manifest.json",
    "run-llm-ledger.json",
    "01-literature-gate-decision.json",
    "04-benchmark-evidence-audit.json",
    "10-claim-traceability.json",
    "10-claim-consistency.json",
    "10-final-readiness.json",
    "10-release-metadata.json",
    "11-submission-package.json",
    "11-submission-package.zip",
    "12-repair-queue.json",
    "13-llm-trace-audit.json",
    "13-llm-runtime-contract.json",
    "13-run-economics-audit.json",
    "13-agent-observability-audit.json",
    "13-llm-observability-summary.json",
    "13-agent-stage-contract.json",
    "13-agent-trajectory.json",
    "13-research-scorecard.json",
    "14-run-integrity-audit.json",
    "14-final-handoff.json",
]
_GOLD_VERIFICATION_AUDIT_CONTRACTS = [
    "llm_trace",
    "llm_runtime",
    "run_economics",
    "agent_observability",
    "llm_observability",
    "stage_contract",
    "trajectory",
]
_GOLD_VERIFICATION_AUDIT_CONTRACT_ARTIFACTS = {
    "llm_trace": "13-llm-trace-audit.json",
    "llm_runtime": "13-llm-runtime-contract.json",
    "run_economics": "13-run-economics-audit.json",
    "agent_observability": "13-agent-observability-audit.json",
    "llm_observability": "13-llm-observability-summary.json",
    "stage_contract": "13-agent-stage-contract.json",
    "trajectory": "13-agent-trajectory.json",
}
_GOLD_HUMAN_HANDOFF_AUDIT_STATUSES = {"pass", "warn", "review_required", "needs_human_review"}
_GOLD_VERIFICATION_SECRET_SCAN_RULES = [
    "auth_header_token",
    "env_api_key_assignment",
    "json_api_key_field",
    "openai_style_token",
    "query_api_key_token",
    "unsafe_file_reference",
]


@dataclass(frozen=True)
class PerfectAgentCapability:
    capability_id: str
    category: str
    status: str
    score: float
    requirement: str
    evidence: list[str]
    gaps: list[str]
    next_actions: list[str]
    target_artifacts: list[str]


@dataclass(frozen=True)
class PerfectAgentReadinessReport:
    generated_at: str
    project_dir: str
    runs_dir: str
    dashboard_limit: int
    scanned_runs: int
    status: str
    score: float
    ready_capabilities: int
    review_capabilities: int
    blocked_capabilities: int
    capabilities: list[PerfectAgentCapability]


@dataclass(frozen=True)
class _ManifestRecord:
    path: Path
    group: str
    role: str
    benchmark_kind: str
    benchmark_url: str
    dataset_url: str
    citation: str
    command_signature: str
    method_flag: str
    metrics_path: str
    has_source_files: bool
    has_grader: bool


def build_perfect_agent_readiness(project_dir: Path, runs_dir: Path, limit: int = 0) -> PerfectAgentReadinessReport:
    project = project_dir.resolve()
    runs_root = runs_dir.resolve()
    dashboard = build_run_dashboard(runs_root, limit=limit)
    run_dirs = {run.id: runs_root / run.id for run in dashboard.runs}
    manifest_groups = _discover_manifest_groups(project)
    paper_grade = _gold_paper_grade_config(project / "examples" / "uci-iris-paper-grade-config.toml")
    capabilities = [
        _real_benchmark_pack_check(manifest_groups),
        _gold_run_check(dashboard.runs, project=project, runs_root=runs_root, manifest_groups=manifest_groups),
        _method_baseline_check(manifest_groups),
        _reproducible_environment_check(project, dashboard.runs, run_dirs),
        _fulltext_grounding_check(dashboard.runs, run_dirs),
        _statistics_design_check(dashboard.runs, run_dirs, paper_grade),
        _claim_traceability_check(dashboard.runs, run_dirs),
        _agent_claim_ownership_check(dashboard.runs, run_dirs),
        _agent_deliberation_check(dashboard.runs, run_dirs),
        _task_specific_agent_routing_check(dashboard.runs, run_dirs),
        _domain_template_check(),
        _human_ui_check(project),
        _cost_queue_check(project, dashboard.runs),
        _external_integration_check(project, dashboard.runs, run_dirs),
        _execution_isolation_check(project, dashboard.runs, run_dirs),
    ]
    ready = sum(1 for item in capabilities if item.status == "ready")
    review = sum(1 for item in capabilities if item.status == "review_required")
    blocked = sum(1 for item in capabilities if item.status == "block")
    status = "block" if blocked else "review_required" if review else "ready"
    score = round(sum(item.score for item in capabilities) / len(capabilities), 3) if capabilities else 0.0
    return PerfectAgentReadinessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        project_dir=str(project),
        runs_dir=str(runs_root),
        dashboard_limit=limit,
        scanned_runs=dashboard.total_runs,
        status=status,
        score=score,
        ready_capabilities=ready,
        review_capabilities=review,
        blocked_capabilities=blocked,
        capabilities=capabilities,
    )


def write_perfect_agent_readiness_artifacts(project_dir: Path, runs_dir: Path, out_dir: Path, limit: int = 0) -> PerfectAgentReadinessReport:
    report = build_perfect_agent_readiness(project_dir, runs_dir, limit=limit)
    write_json(out_dir / PERFECT_AGENT_READINESS_JSON, report)
    write_text(out_dir / PERFECT_AGENT_READINESS_MD, render_perfect_agent_readiness_markdown(report))
    return report


def render_perfect_agent_readiness_markdown(report: PerfectAgentReadinessReport) -> str:
    lines = [
        "# Perfect Research Agent Readiness",
        "",
        f"- 状态：{report.status}",
        f"- 分数：{report.score:.3f}",
        f"- 项目：{report.project_dir}",
        f"- Runs：{report.runs_dir}",
        f"- Run 扫描：{report.scanned_runs}（limit={_limit_label(report.dashboard_limit)}）",
        f"- Ready/Review/Block：{report.ready_capabilities}/{report.review_capabilities}/{report.blocked_capabilities}",
        "",
        "## Capability Matrix",
        "| 能力 | 类别 | 状态 | 分数 | 证据 | 缺口 | 下一步 | 目标产物 |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in report.capabilities:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.capability_id),
                    _cell(item.category),
                    item.status,
                    f"{item.score:.2f}",
                    _cell("；".join(item.evidence) or "-"),
                    _cell("；".join(item.gaps) or "-"),
                    _cell("；".join(item.next_actions) or "-"),
                    _cell(", ".join(item.target_artifacts) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blockers"])
    blockers = [item for item in report.capabilities if item.status == "block"]
    if blockers:
        for item in blockers:
            lines.append(f"- `{item.capability_id}`：{'; '.join(item.gaps) or item.requirement}")
    else:
        lines.append("- 无")
    lines.extend(["", "## Review Required"])
    review = [item for item in report.capabilities if item.status == "review_required"]
    if review:
        for item in review:
            lines.append(f"- `{item.capability_id}`：{'; '.join(item.next_actions) or item.requirement}")
    else:
        lines.append("- 无")
    return "\n".join(lines)


def _real_benchmark_pack_check(groups: dict[str, list[_ManifestRecord]]) -> PerfectAgentCapability:
    complete = _complete_external_groups(groups)
    evidence = _manifest_evidence(groups)
    if complete:
        return _capability(
            "real_benchmark_packs",
            "P0",
            "ready",
            "至少一个正式 benchmark pack 覆盖 candidate/baseline/ablation，且指向公开外部 benchmark/data。",
            [f"formal_external_sets={len(complete)}", *evidence[:3]],
            [],
            ["为每个目标领域继续沉淀 benchmarks/<domain>/ 三角色 manifest。"],
            ["benchmarks/<domain>/{candidate,baseline,ablation}/manifest.json", "00-paper-grade-benchmark-probe.json"],
        )
    gaps = ["缺少非 examples 的公开外部 candidate/baseline/ablation benchmark manifest 集合。"]
    return _capability(
        "real_benchmark_packs",
        "P0",
        "block",
        "正式论文级 run 必须有真实外部 benchmark pack。",
        evidence or ["formal_external_sets=0"],
        gaps,
        ["用 benchmark-manifest-build 在 benchmarks/<domain>/ 下生成三角色 manifest，并运行 paper-grade-benchmark-probe。"],
        ["benchmarks/<domain>/{candidate,baseline,ablation}/manifest.json", "perfect-agent-readiness.json"],
    )


def _gold_run_check(
    runs: list[RunSummary],
    *,
    project: Path | None = None,
    runs_root: Path | None = None,
    manifest_groups: dict[str, list[_ManifestRecord]] | None = None,
) -> PerfectAgentCapability:
    run_dirs = {run.id: runs_root / run.id for run in runs} if runs_root is not None else {}
    gold = [run for run in runs if _is_gold_run(run, run_dirs.get(run.id))]
    best = runs[0] if runs else None
    if gold:
        return _capability(
            "gold_end_to_end_run",
            "P0",
            "ready",
            "存在一个完整公开证据链 gold run。",
            [f"gold_run={gold[0].id}", f"readiness={gold[0].readiness_score:.3f}", f"verification={_gold_verification_state(run_dirs.get(gold[0].id))}"],
            [],
            ["把该 run 固化为 README 和回归样板。"],
            ["runs/<gold-run>/13-run-economics-audit.json", "runs/<gold-run>/14-final-handoff.json", "runs/<gold-run>/15-gold-run-verification.json", "runs/<gold-run>/11-submission-package.zip"],
        )
    evidence = _gold_candidate_evidence(runs, best, run_dirs)
    preflight = _gold_launch_preflight_status(project, runs_root, manifest_groups or {})
    if preflight:
        evidence.extend(preflight["evidence"])
        next_actions = preflight["next_actions"]
    else:
        next_actions = ["先补正式 benchmark pack，再跑一条 paper-grade gold run；若结果为负/中性，必须保留无优势 claim 边界、claim traceability pass 和 claim-consistency pass 证据。"]
    return _capability(
        "gold_end_to_end_run",
        "P0",
        "block",
        "需要一个 online 文献、真实 benchmark、论文、归档包全通过的 gold run。",
        evidence,
        ["没有检测到 benchmark_evidence=real_benchmark、claim traceability pass、claim consistency pass、run economics pass、15-gold-run-verification ready 且最终 handoff ready/upload-ready 的完整 run。"],
        next_actions,
        [
            "runs/<gold-run>/run-manifest.json",
            "runs/<gold-run>/10-claim-traceability.json",
            "runs/<gold-run>/10-claim-consistency.json",
            "runs/<gold-run>/10-final-readiness.json",
            "runs/<gold-run>/13-run-economics-audit.json",
            "runs/<gold-run>/14-final-handoff.json",
            "runs/<gold-run>/15-gold-run-verification.json",
        ],
    )


def _gold_launch_preflight_status(project: Path | None, runs_root: Path | None, manifest_groups: dict[str, list[_ManifestRecord]]) -> dict[str, list[str]] | None:
    if project is None or runs_root is None:
        return None
    config_path = project / "examples" / "uci-iris-paper-grade-config.toml"
    benchmark_run = runs_root / "uci-iris-expanded-baseline-pack-run"
    fulltext_run = runs_root / "uci-iris-fulltext-grounding"
    if not config_path.exists():
        return None
    benchmark = _read_json(benchmark_run / "04-benchmark-evidence-audit.json")
    fulltext_corpus = _read_json(fulltext_run / "01-fulltext-corpus.json")
    citation_grounding = _read_json(fulltext_run / "10-citation-grounding.json")
    benchmark_ready = benchmark.get("evidence_grade") == "real_benchmark" and benchmark.get("adapter_paper_grade_status") == "ready"
    fulltext_ready = _int(fulltext_corpus.get("total_chunks")) > 0 and citation_grounding.get("status") == "pass"
    paper_grade = _gold_paper_grade_config(config_path)
    literature_probe = _paper_grade_literature_probe_summary(runs_root, paper_grade)
    formal_sets = len(_complete_external_groups(manifest_groups))
    if not (benchmark_ready and fulltext_ready and formal_sets):
        return None
    config_benchmark = _gold_config_benchmark_manifest_summary(config_path, project, manifest_groups)
    environment = _gold_launch_environment_summary(config_path)
    output = _gold_launch_output_summary(project)
    secret_flow = _gold_launch_secret_flow_summary(project)
    verifier = _gold_post_launch_verifier_summary(project)
    config_benchmark_ready = config_benchmark.get("ready") is True
    literature_ready = literature_probe.get("ready") is True
    output_ready = output.get("ready") is True
    secret_flow_ready = secret_flow.get("ready") is True
    verifier_ready = verifier.get("ready") is True
    environment_ready = environment.get("ready") is True
    focus = "benchmark_manifest" if not config_benchmark_ready else "paper_grade_literature_probe" if not literature_ready else "output_directory" if not output_ready else "launch_secret_flow" if not secret_flow_ready else "post_launch_verification" if not verifier_ready else "server_environment" if not environment_ready else "ready_to_bundle"
    launch_kits = _gold_launch_kit_paths(project)
    gateway_socket = _gold_launch_gateway_socket_status(config_path)
    evidence = [
        (
            "gold_launch_prereq="
            f"config=yes; formal_external_sets={formal_sets}; "
            f"benchmark_pack=real_benchmark/ready; fulltext_grounding=pass"
        ),
        str(config_benchmark["evidence"]),
        str(literature_probe["evidence"]),
        str(output["evidence"]),
        str(secret_flow["evidence"]),
        str(verifier["evidence"]),
        f"gold_launch_focus={focus}; {environment.get('evidence')}",
        gateway_socket,
        f"gold_launch_kit={', '.join(launch_kits) or '-'}",
    ]
    if not config_benchmark_ready:
        next_actions = [
            "先修复 examples/uci-iris-paper-grade-config.toml 中的 benchmark_manifest_paths，确保当前 gold 配置直接引用 candidate/baseline/ablation 三角色正式 manifest。",
            "Benchmark Preview 通过后再处理文献 Probe、服务端环境字段和 gold-run-launch。",
        ]
    elif not literature_ready:
        min_sources = max(1, int(paper_grade.min_literature_sources or 0))
        min_successful = max(1, int(paper_grade.min_successful_literature_sources or 0))
        min_seed = max(1, int(paper_grade.min_seed_papers or 0))
        min_resolved = max(1, int(paper_grade.min_doi_url_seed_papers or 0))
        next_actions = [
            f"先运行 paper-grade-probe，确认 literature.provider=online/auto、至少 {min_sources} 个来源、至少 {min_successful} 个来源返回候选、{min_seed} 条 DOI/URL seed 且 {min_resolved} 条元数据解析通过。",
            "文献 Probe 通过后再打开 Gold Bundle；随后处理服务端环境字段并执行 gold-run-launch。",
        ]
    elif not output_ready:
        next_actions = [
            "默认 gold 输出目录已存在；设置新的 RESEARCH_AGENT_GOLD_OUT，或归档旧 run 后再启动正式 gold run。",
            "输出目录可用后再处理服务端环境字段并执行 gold-run-launch。",
        ]
    elif not secret_flow_ready:
        next_actions = [
            "先修复 gold launch 脚本的密钥流：必须先检查 gateway 和真实联系邮箱，再隐藏读取 OPENAI_API_KEY。",
            "密钥流通过后再处理服务端环境字段并执行 gold-run-launch。",
        ]
    elif not verifier_ready:
        next_actions = [
            "先修复 gold-run-verify 和 Web worker 的 post-launch 验收闭环，确保 run 完成后写入 15-gold-run-verification 并扫描 secret。",
            "post-launch verifier 通过后再处理服务端环境字段并执行 gold-run-launch。",
        ]
    elif not environment_ready:
        next_actions = [
            "运行 scripts/start_gold_web_env.sh 或 scripts/run_gold_cli_env.sh，用交互输入注入本地 gateway key 和联系邮箱。",
            "CLI 只验证 gate 可用：RESEARCH_AGENT_GOLD_DRY_RUN=1 scripts/run_gold_cli_env.sh。",
            "Gold Bundle 显示 ready_to_start 后再执行 gold-run-launch；完成后运行 gold-run-verify 和 perfect-readiness。",
        ]
    else:
        next_actions = [
            "服务端环境字段已存在；先执行 Gold Bundle 只读核验，ready_to_start 后执行 gold-run-launch 或 scripts/run_gold_cli_env.sh。",
            "Gold Launch 完成后运行 gold-run-verify 和 perfect-readiness；负/中性结果必须保留 no-superiority claim 边界。",
        ]
    return {"evidence": evidence, "next_actions": next_actions}


def _gold_launch_environment_summary(config_path: Path) -> dict[str, Any]:
    try:
        config = load_config(config_path)
        report = build_gold_environment_lint(config)
    except Exception:
        env_names = _gold_launch_env_names(config_path)
        present = sum(1 for name in env_names if os.environ.get(name))
        total = len(env_names)
        missing = max(0, total - present)
        return {
            "ready": missing == 0,
            "present": present,
            "total": total,
            "missing": missing,
            "invalid": 0,
            "evidence": f"server_env_present={present}/{total}; missing_env={missing}; invalid_env=0",
        }
    required = report.get("required_fields") if isinstance(report.get("required_fields"), dict) else {}
    total = len(required) or len(_gold_launch_env_names(config_path))
    missing = len(_string_list(report.get("missing_required_fields")))
    invalid = len(_string_list(report.get("invalid_required_fields")))
    present = max(0, total - missing - invalid)
    return {
        "ready": report.get("required_ready") is True,
        "present": present,
        "total": total,
        "missing": missing,
        "invalid": invalid,
        "evidence": f"server_env_present={present}/{total}; missing_env={missing}; invalid_env={invalid}",
    }


def _gold_launch_output_summary(project: Path) -> dict[str, Any]:
    default_value = "runs/iris-classification-benchmark-smoke-gold-run"
    raw = os.environ.get("RESEARCH_AGENT_GOLD_OUT", "").strip() or default_value
    source = "env" if os.environ.get("RESEARCH_AGENT_GOLD_OUT", "").strip() else "default"
    path = Path(raw)
    resolved = path if path.is_absolute() else project / path
    exists = resolved.exists()
    label = _project_relative_label(project, resolved)
    return {
        "ready": not exists,
        "evidence": f"gold_launch_output={'available' if not exists else 'exists'}; source={source}; path={label}",
    }


def _gold_launch_secret_flow_summary(project: Path) -> dict[str, Any]:
    names = ["scripts/start_gold_web_env.sh", "scripts/run_gold_cli_env.sh"]
    sources: list[str] = []
    existing = 0
    for name in names:
        path = project / name
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            source = ""
        if source:
            existing += 1
        sources.append(source)
    total = len(names)
    hidden = sum(int("prompt_required_secret OPENAI_API_KEY" in source and "read -rsp" in source) for source in sources)
    contact = sum(int(_ordered(source, "prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL", "prompt_required_secret OPENAI_API_KEY")) for source in sources)
    gateway = sum(int(_ordered(source, "ensure_llm_gateway_reachable", "prompt_required_secret OPENAI_API_KEY")) for source in sources)
    base_url = sum(int("OPENAI_BASE_URL:-http://127.0.0.1:8317" in source) for source in sources)
    model = sum(int("OPENAI_MODEL:-gpt-5.5" in source) for source in sources)
    ready = existing == total and hidden == total and contact == total and gateway == total and base_url == total and model == total
    return {
        "ready": ready,
        "evidence": (
            f"gold_launch_secret_flow={'pass' if ready else 'block'}; "
            f"scripts={existing}/{total}; hidden_key_prompt={hidden}/{total}; "
            f"contact_before_key={contact}/{total}; gateway_before_key={gateway}/{total}; "
            f"base_url_default={base_url}/{total}; model_default={model}/{total}"
        ),
    }


def _gold_post_launch_verifier_summary(project: Path) -> dict[str, Any]:
    cli = _read_text(project / "src" / "research_agent" / "cli.py")
    cli_env = _read_text(project / "scripts" / "run_gold_cli_env.sh")
    doctor = _read_text(project / "src" / "research_agent" / "gold_run_doctor.py")
    readiness = _read_text(project / "src" / "research_agent" / "perfect_agent_readiness.py")
    repair_resume = _read_text(project / "src" / "research_agent" / "repair_resume.py")
    web = _read_text(project / "src" / "research_agent" / "web_server.py")
    cli_verify = "gold-run-verify" in cli and "write_gold_run_verification_artifacts" in cli and "build_gold_run_verification_report" in cli
    writes_artifacts = (
        'GOLD_RUN_VERIFICATION_JSON = "15-gold-run-verification.json"' in doctor
        and "write_gold_run_verification_artifacts" in doctor
        and "build_gold_run_verification_report" in doctor
    )
    required = sum(int(name in doctor) for name in _GOLD_VERIFICATION_REQUIRED_ARTIFACTS)
    schema_contract = (
        "schema_version" in doctor
        and "read_only" in doctor
        and "_gold_verification_schema_ready" in readiness
        and "_gold_verification_subschemas_ready" in readiness
        and "schema=" in readiness
        and "subschemas=" in readiness
    )
    required_list_contract = "_gold_verification_required_artifacts_ready" in readiness and "extra=" in readiness and "duplicate=" in readiness and "malformed=" in readiness
    artifact_hash_contract = "_gold_verification_artifact_hash_state" in readiness and "extra_names" in readiness and "malformed_names" in readiness and "artifact_hashes=" in readiness
    contract_evidence_contract = (
        "contract_evidence" in doctor
        and "_gold_verification_contract_evidence_state" in readiness
        and "_gold_verification_final_zip_summary_ready" in readiness
        and "contract_evidence=" in readiness
        and "final_zip_summary=" in readiness
        and "top_level" in readiness
    )
    verification_summary_contract = (
        "_gold_verification_summary_ready" in readiness
        and "missing_malformed=" in readiness
        and "repair_malformed=" in readiness
        and "verification_summary=" in readiness
    )
    secret_scan = (
        "_gold_run_secret_scan" in doctor
        and "_SECRET_SCAN_RULES" in doctor
        and "_secret_scan_file_reference_issue" in doctor
        and "unsafe_file_reference" in doctor
        and "secret_scan" in doctor
    )
    secret_scan_summary_contract = (
        "_gold_verification_secret_scan_summary_ready" in readiness
        and "_GOLD_VERIFICATION_SECRET_SCAN_RULES" in readiness
        and "malformed_findings" in readiness
        and "malformed_rules" in readiness
        and "secret_malformed_findings=" in readiness
        and "secret_scan_summary=" in readiness
        and all(name in doctor for name in _GOLD_VERIFICATION_SECRET_SCAN_RULES)
    )
    artifact_safety = (
        "_gold_unsafe_required_artifacts" in doctor
        and "required_artifact_safety" in doctor
        and "_gold_verification_artifact_safety_ready" in readiness
        and "artifact_safety=" in readiness
        and "_public_gold_unsafe_artifacts" in web
        and "unsafe_artifact_count" in web
    )
    artifact_safety_summary_contract = "_gold_verification_artifact_safety_summary_ready" in readiness and "artifact_safety_summary=" in readiness
    manifest_path_safety = (
        "_gold_manifest_inventory_unsafe_paths" in doctor
        and "unsafe_artifact_paths" in doctor
        and "unsafe=" in readiness
        and "manifest_inventory_unsafe_path_count" in web
    )
    manifest_inventory_summary_contract = (
        "_gold_verification_manifest_inventory_summary_ready" in readiness
        and "malformed_manifest_inventory_items" in readiness
        and "manifest_inventory_summary=" in readiness
    )
    current_manifest_inventory_contract = (
        "_gold_manifest_inventory_check" in readiness
        and "_gold_required_artifact_hashes" in readiness
        and "_gold_current_manifest_inventory_ready" in readiness
        and "current_manifest_inventory=" in readiness
    )
    audit_names = sum(int(name in doctor) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    audit_contracts = (
        audit_names == len(_GOLD_VERIFICATION_AUDIT_CONTRACTS)
        and "_candidate_audit_contracts_evidence" in doctor
        and "audit_contracts_ready" in doctor
        and "_gold_verification_audit_contracts_ready" in readiness
        and "audit_contracts=" in readiness
        and "malformed_audit_names" in readiness
        and "_public_gold_audit_contracts" in web
        and "audit_contract_ready_count" in web
    )
    audit_summary_contract = "_gold_verification_audit_summary_ready" in readiness and "audit_summary=" in readiness
    current_audit_contract = (
        "_GOLD_VERIFICATION_AUDIT_CONTRACT_ARTIFACTS" in readiness
        and "_gold_current_audit_contracts_ready" in readiness
        and "current_audit_contracts=" in readiness
    )
    web_auto = (
        "_write_gold_verification_if_gold_launch" in web
        and "write_gold_run_verification_artifacts(out_dir)" in web
        and "_write_gold_verification_followups(out_dir, report)" in web
        and "write_repair_resume_plan_artifacts(" in web
        and "gold_verification_report_path=verification_json" in web
        and "write_perfect_agent_readiness_artifacts(ROOT, RUNS_DIR, ROOT, limit=0)" in web
    )
    post_commands = "gold-run-verify" in web and "perfect-readiness" in web
    cli_env_launch = 'python3 -m research_agent gold-run-launch --topic "$TOPIC" --gold-defaults --out "$OUT_DIR"'
    cli_env_launch_index = cli_env.find(cli_env_launch)
    cli_env_final_audit_call_index = cli_env.find("run_final_gold_audits", cli_env_launch_index)
    cli_env_final_audit = (
        'gold-run-verify --run-dir "$OUT_DIR"' in cli_env
        and "perfect-readiness --project-dir . --runs-dir" in cli_env
        and "--out ." in cli_env
        and cli_env_launch_index >= 0
        and cli_env_final_audit_call_index > cli_env_launch_index
    )
    cli_env_resilient_audit = (
        "run_gold_launch_with_final_audit" in cli_env
        and "launch_status=$?" in cli_env
        and "audit_status=$?" in cli_env
        and 'if [[ -d "$OUT_DIR" ]]; then' in cli_env
        and "return \"$launch_status\"" in cli_env
    )
    gold_verification_repair_resume = (
        "--gold-run-verification-report" in cli
        and "--write-repair-resume-plan" in cli
        and "write_repair_resume_plan_artifacts" in cli
        and "gold_verification_report_path" in repair_resume
        and "_gold_verification_repair_items" in repair_resume
        and "gold-run-verification" in repair_resume
        and 'repair-resume "$OUT_DIR" --dry-run --gold-run-verification-report "$OUT_DIR/15-gold-run-verification.json"' in cli_env
    )
    direct_launch_repair_resume = "_print_gold_verification_repair_resume_plan(result_dir, result_dir / GOLD_RUN_VERIFICATION_JSON)" in cli
    direct_launch_perfect_readiness = (
        "_print_gold_launch_perfect_readiness(args.project_dir, result_dir.parent)" in cli
        and "write_perfect_agent_readiness_artifacts(project_dir, runs_dir, project_dir)" in cli
        and "Perfect readiness status:" in cli
    )
    ready = (
        cli_verify
        and writes_artifacts
        and required == len(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)
        and schema_contract
        and required_list_contract
        and artifact_hash_contract
        and contract_evidence_contract
        and verification_summary_contract
        and secret_scan
        and secret_scan_summary_contract
        and artifact_safety
        and artifact_safety_summary_contract
        and manifest_path_safety
        and manifest_inventory_summary_contract
        and current_manifest_inventory_contract
        and audit_contracts
        and audit_summary_contract
        and current_audit_contract
        and web_auto
        and post_commands
        and cli_env_final_audit
        and cli_env_resilient_audit
        and gold_verification_repair_resume
        and direct_launch_repair_resume
        and direct_launch_perfect_readiness
    )
    return {
        "ready": ready,
        "evidence": (
            f"gold_post_launch_verifier={'pass' if ready else 'block'}; "
            f"cli_verify={cli_verify}; writes_15_artifacts={writes_artifacts}; "
            f"required_artifacts={required}/{len(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)}; "
            f"schema_contract={schema_contract}; required_list_contract={required_list_contract}; "
            f"artifact_hash_contract={artifact_hash_contract}; contract_evidence_contract={contract_evidence_contract}; "
            f"verification_summary_contract={verification_summary_contract}; "
            f"secret_scan={secret_scan}; secret_scan_summary_contract={secret_scan_summary_contract}; "
            f"artifact_safety={artifact_safety}; "
            f"artifact_safety_summary_contract={artifact_safety_summary_contract}; "
            f"manifest_path_safety={manifest_path_safety}; manifest_inventory_summary_contract={manifest_inventory_summary_contract}; "
            f"current_manifest_inventory_contract={current_manifest_inventory_contract}; "
            f"audit_contracts={audit_contracts}; audit_summary_contract={audit_summary_contract}; current_audit_contract={current_audit_contract}; "
            f"audit_names={audit_names}/{len(_GOLD_VERIFICATION_AUDIT_CONTRACTS)}; "
            f"web_auto_write={web_auto}; post_commands={post_commands}; cli_env_final_audit={cli_env_final_audit}; "
            f"cli_env_resilient_audit={cli_env_resilient_audit}; gold_verification_repair_resume={gold_verification_repair_resume}; "
            f"direct_launch_repair_resume={direct_launch_repair_resume}; direct_launch_perfect_readiness={direct_launch_perfect_readiness}"
        ),
    }


def _gold_config_benchmark_manifest_summary(config_path: Path, project: Path, manifest_groups: dict[str, list[_ManifestRecord]]) -> dict[str, Any]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    paper_grade = _gold_paper_grade_config(config_path)
    required_roles = max(len(_ROLES), int(paper_grade.min_benchmark_roles or 0))
    execution = data.get("execution") if isinstance(data.get("execution"), dict) else {}
    raw_paths = execution.get("benchmark_manifest_paths") if isinstance(execution, dict) else []
    listed = [str(item).strip() for item in raw_paths if str(item).strip()] if isinstance(raw_paths, list) else []
    records_by_path = {
        record.path.resolve(): record
        for records in manifest_groups.values()
        for record in records
    }
    config_records: list[_ManifestRecord] = []
    existing = 0
    for value in listed:
        path = Path(value)
        if not path.is_absolute():
            path = project / path
        resolved = path.resolve()
        if resolved.exists():
            existing += 1
        record = records_by_path.get(resolved)
        if record is not None:
            config_records.append(record)
    role_records = [item for item in config_records if item.role in _ROLES]
    roles = {item.role for item in role_records}
    formal_roles = {item.role for item in role_records if _is_formal_external_manifest(item)}
    method_ready = _role_commands_ready(role_records)
    ready = (
        bool(listed)
        and existing == len(listed)
        and roles >= _ROLES
        and formal_roles >= _ROLES
        and len(roles) >= required_roles
        and len(formal_roles) >= required_roles
        and method_ready
    )
    return {
        "ready": ready,
        "evidence": (
            f"gold_config_benchmark_manifests={'pass' if ready else 'block'}; "
            f"paths={existing}/{len(listed)}; roles={','.join(sorted(roles)) or '-'}; "
            f"formal_roles={len(formal_roles)}/{required_roles}; required_roles={required_roles}; "
            f"method_roles={'ready' if method_ready else 'missing'}"
        ),
    }


def _gold_paper_grade_config(config_path: Path) -> PaperGradeConfig:
    try:
        return load_config(config_path).paper_grade
    except Exception:
        return PaperGradeConfig()


def _paper_grade_literature_probe_summary(runs_root: Path, paper_grade: PaperGradeConfig | None = None) -> dict[str, Any]:
    config = paper_grade or PaperGradeConfig()
    min_configured = max(1, int(config.min_literature_sources or 0))
    min_successful = max(1, int(config.min_successful_literature_sources or 0))
    min_strong = max(1, int(config.min_seed_papers or 0))
    min_resolved = max(1, int(config.min_doi_url_seed_papers or 0))
    reports = []
    try:
        paths = sorted(runs_root.glob("*/00-paper-grade-online-probe.json"))
    except OSError:
        paths = []
    for path in paths:
        report = _read_json(path)
        if report:
            reports.append((path, report))
    if not reports:
        return {"ready": False, "evidence": "paper_grade_literature_probe=missing"}
    path, report = max(reports, key=lambda item: _paper_grade_literature_probe_rank(item[1]))
    source = report.get("source_summary") if isinstance(report.get("source_summary"), dict) else {}
    seed = report.get("seed_summary") if isinstance(report.get("seed_summary"), dict) else {}
    configured = _int(source.get("configured_sources"))
    successful = _int(source.get("successful_sources"))
    strong = _int(seed.get("strong_seed_papers"))
    resolved = _int(seed.get("metadata_resolved_seed_papers"))
    candidates = _int(report.get("candidate_count"))
    provider = str(source.get("provider") or "").strip() or "-"
    status = str(report.get("status") or "").strip() or "-"
    ready = (
        status == "pass"
        and provider in {"online", "auto"}
        and configured >= min_configured
        and successful >= min_successful
        and strong >= min_strong
        and resolved >= min_resolved
        and candidates > 0
    )
    return {
        "ready": ready,
        "evidence": (
            f"paper_grade_literature_probe={status}; provider={provider}; "
            f"online_sources={successful}/{configured}; doi_url_seeds={resolved}/{strong}; "
            f"configured_sources={configured}/{min_configured}; successful_sources={successful}/{min_successful}; "
            f"strong_seeds={strong}/{min_strong}; resolved_seeds={resolved}/{min_resolved}; "
            f"candidates={candidates}; run={path.parent.name}"
        ),
    }


def _paper_grade_literature_probe_rank(report: dict[str, Any]) -> tuple[int, int, int, int, int]:
    source = report.get("source_summary") if isinstance(report.get("source_summary"), dict) else {}
    seed = report.get("seed_summary") if isinstance(report.get("seed_summary"), dict) else {}
    return (
        int(str(report.get("status") or "") == "pass"),
        _int(source.get("successful_sources")),
        _int(seed.get("metadata_resolved_seed_papers")),
        _int(seed.get("strong_seed_papers")),
        _int(report.get("candidate_count")),
    )


def _gold_launch_kit_paths(project: Path) -> list[str]:
    candidates = ["scripts/start_gold_web_env.sh", "scripts/run_gold_cli_env.sh"]
    existing = [item for item in candidates if (project / item).exists()]
    return existing or candidates


def _gold_launch_env_names(config_path: Path) -> list[str]:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    literature = data.get("literature") if isinstance(data.get("literature"), dict) else {}
    return [
        str(llm.get("base_url_env") or "OPENAI_BASE_URL"),
        str(llm.get("model_env") or "OPENAI_MODEL"),
        str(llm.get("api_key_env") or "OPENAI_API_KEY"),
        str(literature.get("contact_email_env") or "RESEARCH_AGENT_CONTACT_EMAIL"),
    ]


def _gold_launch_gateway_socket_status(config_path: Path) -> str:
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    base_url_env = str(llm.get("base_url_env") or "OPENAI_BASE_URL")
    raw = os.environ.get(base_url_env, "").strip() or str(llm.get("base_url") or _DEFAULT_GOLD_GATEWAY_BASE_URL)
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname
    if not host:
        return "gold_launch_gateway_socket=invalid"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = parsed.scheme or "http"
    target = f"{scheme}://{host}:{port}"
    try:
        with socket.create_connection((host, port), timeout=0.25):
            pass
    except OSError:
        return f"gold_launch_gateway_socket=unreachable; target={target}"
    return f"gold_launch_gateway_socket=reachable; target={target}"


def _method_baseline_check(groups: dict[str, list[_ManifestRecord]]) -> PerfectAgentCapability:
    complete = _complete_external_groups(groups)
    method_ready = [group for group in complete if _role_commands_ready(group)]
    if method_ready:
        mapping_ready = [group for group in method_ready if _role_mapping_readme_ready(group)]
        mapping_evidence = _role_mapping_readme_evidence(mapping_ready[0] if mapping_ready else method_ready[0])
        next_actions = (
            ["继续为新增 benchmark pack 保持 README/manifest 参数映射同步。"]
            if mapping_ready
            else ["把 candidate/baseline/ablation 的参数映射写入 benchmark pack README。"]
        )
        return _capability(
            "candidate_baseline_ablation_implementations",
            "P0",
            "ready",
            "三角色 manifest 显式绑定不同 method/variant/config，并声明 source/grader。",
            [f"method_ready_sets={len(method_ready)}", _group_summary(method_ready[0]), mapping_evidence],
            [],
            next_actions,
            ["benchmarks/<domain>/README.md", "benchmarks/<domain>/benchmark-manifest-build-report.json", "03-benchmark-adapters.json"],
        )
    return _capability(
        "candidate_baseline_ablation_implementations",
        "P0",
        "block",
        "候选方法、baseline 和 ablation 必须是真实可执行实现，而不只是输出路径不同。",
        _manifest_evidence(groups) or ["method_ready_sets=0"],
        ["缺少外部三角色 manifest，或三角色命令/source/grader 证据不足。"],
        ["为每个 role 的 command 加入真实 method/variant/config 参数，并提供 source_files 与 grader。"],
        ["benchmarks/<domain>/*/manifest.json", "03-benchmark-readiness.json"],
    )


def _reproducible_environment_check(project: Path, runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    env_files = [name for name in ["Dockerfile", "environment.yml", "conda-lock.yml", "requirements.txt", "uv.lock", "poetry.lock", "pyproject.toml"] if (project / name).exists()]
    snapshots = [run.id for run in runs if (run_dirs[run.id] / "04-environment-snapshot.json").exists()]
    release_environment_runs = [
        run.id
        for run in runs
        if _release_environment_url(_read_json(run_dirs[run.id] / "10-release-metadata.json"))
    ]
    container_or_lock = any(name in env_files for name in ["Dockerfile", "environment.yml", "conda-lock.yml", "requirements.txt", "uv.lock", "poetry.lock"])
    if container_or_lock and snapshots:
        status = "ready"
        gaps: list[str] = []
        actions = (
            ["继续保持环境文件、04-environment-snapshot 和 release metadata environment_url 同步。"]
            if release_environment_runs
            else ["归档 Docker/Conda/requirements 环境 URL，并写入 release metadata。"]
        )
    elif env_files or snapshots:
        status = "review_required"
        gaps = ["检测到部分环境证据，但还缺容器/lockfile 或正式 run 环境快照。"]
        actions = ["补 Dockerfile 或 lockfile，并确保 gold run 生成 04-environment-snapshot。"]
    else:
        status = "block"
        gaps = ["缺少可复现实验环境文件和 run 环境快照。"]
        actions = ["添加 Dockerfile/Conda/requirements/lockfile，并在真实实验 run 中生成环境快照。"]
    return _capability(
        "reproducible_environment",
        "P0",
        status,
        "论文级实验必须能用锁定环境复现。",
        [
            f"env_files={', '.join(env_files) or '-'}",
            f"environment_snapshots={len(snapshots)}",
            f"release_environment_urls={len(release_environment_runs)}",
        ],
        gaps,
        actions,
        ["Dockerfile", "environment.yml", "04-environment-snapshot.json", "10-release-metadata.json"],
    )


def _release_environment_url(release_metadata: dict[str, Any]) -> str:
    metadata = release_metadata.get("metadata") if isinstance(release_metadata.get("metadata"), dict) else {}
    value = str(metadata.get("environment_url") or "").strip()
    return value if _public_url(value) else ""


def _fulltext_grounding_check(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    candidates: list[str] = []
    partial: list[str] = []
    for run in runs:
        run_dir = run_dirs[run.id]
        corpus = _read_json(run_dir / "01-fulltext-corpus.json")
        grounding = _read_json(run_dir / "10-citation-grounding.json")
        chunks = _int(corpus.get("total_chunks"))
        status = str(grounding.get("status") or "")
        if chunks and status == "pass":
            candidates.append(f"{run.id}: chunks={chunks}, grounding=pass")
        elif chunks or status:
            partial.append(f"{run.id}: chunks={chunks}, grounding={status or '-'}")
    if candidates:
        return _capability("fulltext_citation_grounding", "P1", "ready", "全文 chunk 与正文 citation grounding 可追踪。", candidates[:3], [], ["继续扩大全文覆盖到核心 seed/review/benchmark 文献。"], ["01-fulltext-corpus.json", "01-context.json", "10-citation-grounding.json"])
    status = "review_required" if partial else "block"
    gaps = ["没有检测到全文 chunk + citation grounding pass 的 run。"]
    return _capability("fulltext_citation_grounding", "P1", status, "论文 claim 需要全文级证据定位，而不只依赖题录摘要。", partial[:4] or ["fulltext_grounded_runs=0"], gaps, ["为核心 DOI/URL seed 提供 PDF/txt/md 全文，并重新生成 context 与 citation grounding。"], ["01-fulltext-corpus.json", "01-context.json", "10-citation-grounding.json"])


def _statistics_design_check(runs: list[RunSummary], run_dirs: dict[str, Path], paper_grade: PaperGradeConfig | None = None) -> PerfectAgentCapability:
    min_repeats = max(1, int((paper_grade or PaperGradeConfig()).min_execution_repeats or 0))
    ready: list[str] = []
    ready_with_design: list[str] = []
    partial: list[str] = []
    for run in runs:
        stats = _read_json(run_dirs[run.id] / "04-statistics.json")
        comparisons = stats.get("comparisons") if isinstance(stats.get("comparisons"), list) else []
        repeats = _int(stats.get("repeats"))
        has_ci = any(isinstance(item, dict) and "ci_low" in item and "ci_high" in item and "effect_size" in item for item in comparisons)
        multiplicity = stats.get("multiplicity") if isinstance(stats.get("multiplicity"), dict) else {}
        power = stats.get("power_analysis") if isinstance(stats.get("power_analysis"), dict) else {}
        has_design = multiplicity.get("status") == "pass" and bool(power.get("status"))
        warnings = stats.get("warnings") if isinstance(stats.get("warnings"), list) else []
        if comparisons and repeats >= min_repeats and has_ci and not warnings:
            evidence = f"{run.id}: comparisons={len(comparisons)}, repeats={repeats}, ci/effect_size=yes"
            if has_design:
                evidence += f", multiplicity={multiplicity.get('status')}, power={power.get('status')}"
                ready_with_design.append(evidence)
            else:
                evidence += ", multiplicity/power=missing"
            ready.append(evidence)
        elif comparisons:
            partial.append(f"{run.id}: comparisons={len(comparisons)}, repeats={repeats}, warnings={len(warnings)}")
    if ready:
        evidence = [*ready_with_design, *[item for item in ready if item not in ready_with_design]][:3]
        next_actions = (
            ["继续用 statistical_design.multiplicity/power_analysis 约束结果呈现和 claim consistency。"]
            if ready_with_design
            else ["重新运行 benchmark-pack-run 或 gold run，刷新 04-statistics.json 的 multiplicity/power_analysis 字段。"]
        )
        return _capability("statistical_design", "P1", "ready", "统计报告包含重复、CI、effect size，并支持多重比较/功效敏感性审计。", evidence, [], next_actions, ["04-statistics.json", "04-results-presentation.json"])
    return _capability(
        "statistical_design",
        "P1",
        "review_required" if partial else "block",
        "真实论文结果需要 CI、effect size 和足够 repeats。",
        partial[:4] or ["statistics_runs=0"],
        [f"没有检测到 repeats>={min_repeats} 且 CI/effect size 完整的统计 run。"],
        [f"在真实 benchmark 上运行至少 {min_repeats} 次，并保留 04-statistics 与结果呈现审计。"],
        ["04-statistics.json", "04-results-presentation.json"],
    )


def _claim_traceability_check(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    pass_runs: list[str] = []
    review_runs: list[str] = []
    for run in runs:
        trace = _read_json(run_dirs[run.id] / "10-claim-traceability.json")
        status = str(trace.get("status") or "")
        if status == "pass":
            pass_runs.append(f"{run.id}: claims={_int(trace.get('total_claims'))}, score={trace.get('traceability_score')}")
        elif status:
            review_runs.append(f"{run.id}: status={status}, blocked={_int(trace.get('blocked_claims'))}")
    if pass_runs:
        return _capability("sentence_claim_traceability", "P1", "ready", "修订稿 claim 可追踪到 citation/result/runbook。", pass_runs[:3], [], ["继续用 gold-run-verify 强制验收 traceability，并扩展到更多领域模板。"], ["10-claim-traceability.json", "10-citation-grounding.json"])
    return _capability("sentence_claim_traceability", "P1", "review_required" if review_runs else "block", "每个强 claim 都要有文献、实验或人工证据。", review_runs[:4] or ["claim_traceability_runs=0"], ["没有检测到 claim traceability pass 的 run。"], ["重跑 paper review/revision 后生成 10-claim-traceability，并降级 unsupported claim。"], ["10-claim-traceability.json", "09-revised-paper.md"])


def _agent_claim_ownership_check(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    pass_runs: list[str] = []
    review_runs: list[str] = []
    for run in runs:
        audit = _read_json(run_dirs[run.id] / "10-agent-claim-audit.json")
        status = str(audit.get("status") or "")
        summary = audit.get("claim_owner_summary") if isinstance(audit.get("claim_owner_summary"), dict) else {}
        orphaned = _int(summary.get("orphaned_claims"))
        total = _int(summary.get("total_claims"))
        if status == "pass" and orphaned == 0:
            pass_runs.append(f"{run.id}: claims={total}, orphaned=0")
        elif status:
            review_runs.append(f"{run.id}: status={status}, orphaned={orphaned}")
    if pass_runs:
        return _capability(
            "agent_claim_ownership",
            "P1",
            "ready",
            "论文阶段 claim 需要映射到写作、复核、文献证据和统计/benchmark owner。",
            pass_runs[:3],
            [],
            ["继续把 10-agent-claim-audit 扩展到更多领域模板和 gold runs。"],
            ["10-agent-claim-audit.json", "02-agent-team.json", "03-agent-handoff-audit.json"],
        )
    return _capability(
        "agent_claim_ownership",
        "P1",
        "review_required" if review_runs else "block",
        "多智能体科研系统必须能说明每条论文 claim 由哪个 agent 负责。",
        review_runs[:4] or ["agent_claim_audit_runs=0"],
        ["没有检测到通过的 10-agent-claim-audit run。"],
        ["重跑最终论文审计，生成 10-agent-claim-audit，并补齐 manuscript/reviewer/evidence/stat owner。"],
        ["10-agent-claim-audit.json", "10-claim-traceability.json"],
    )


def _agent_deliberation_check(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    pass_runs: list[str] = []
    review_runs: list[str] = []
    for run in runs:
        audit = _read_json(run_dirs[run.id] / "10-agent-deliberation.json")
        status = str(audit.get("status") or "")
        consensus = audit.get("consensus") if isinstance(audit.get("consensus"), dict) else {}
        decision = str(consensus.get("decision") or "")
        agent_count = len(audit.get("agent_verdicts", [])) if isinstance(audit.get("agent_verdicts"), list) else 0
        independent = audit.get("independent_agent_execution") is True
        independent_count = int(audit.get("independent_verdict_count") or 0)
        if status == "pass" and decision == "approve" and independent and independent_count >= 4:
            pass_runs.append(f"{run.id}: agents={agent_count}, consensus={decision}")
        elif status:
            review_runs.append(
                f"{run.id}: status={status}, decision={decision or '-'}, "
                f"independent={independent}, independent_verdicts={independent_count}"
            )
    if pass_runs:
        return _capability(
            "agent_deliberation_consensus",
            "P1",
            "ready",
            "多智能体科研系统需要可验证的独立 Agent 上下文、verdict、分歧记录和最终共识。",
            pass_runs[:3],
            [],
            ["继续把独立 Agent deliberation 接入更多 gold runs 和人工审阅界面。"],
            ["10-agent-deliberation.json", "10-agent-claim-audit.json"],
        )
    return _capability(
        "agent_deliberation_consensus",
        "P1",
        "review_required" if review_runs else "block",
        "确定性角色规则投影不能替代独立 Agent verdict；需要留下独立上下文与执行证据。",
        review_runs[:4] or ["agent_deliberation_runs=0"],
        ["没有检测到带独立 Agent 执行证据的 10-agent-deliberation run。"],
        ["接入独立 Agent 上下文与调用轨迹后再生成 deliberation；当前规则投影仅供人工复核。"],
        ["10-agent-deliberation.json", "10-agent-claim-audit.json"],
    )


def _task_specific_agent_routing_check(runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    pass_runs: list[str] = []
    review_runs: list[str] = []
    for run in runs:
        assignment = _read_json(run_dirs[run.id] / "02-agent-team.json")
        routes = assignment.get("task_routes") if isinstance(assignment.get("task_routes"), list) else []
        route_teams = [
            tuple(str(agent) for agent in route.get("all_agents", []) if str(agent).strip())
            for route in routes
            if isinstance(route, dict) and isinstance(route.get("all_agents"), list)
        ]
        distinct_teams = {team for team in route_teams if team}
        active_routes = [route for route in routes if isinstance(route, dict) and str(route.get("status") or "") in {"active", "repair"}]
        if len(routes) >= 4 and len(distinct_teams) >= 3 and active_routes:
            pass_runs.append(f"{run.id}: routes={len(routes)}, distinct_teams={len(distinct_teams)}, active={len(active_routes)}")
        elif routes:
            review_runs.append(f"{run.id}: routes={len(routes)}, distinct_teams={len(distinct_teams)}, active={len(active_routes)}")
    if pass_runs:
        return _capability(
            "task_specific_agent_routing",
            "P1",
            "ready",
            "不同科研任务需要路由到不同 primary/support agent 小队，而不是固定一组角色。",
            pass_runs[:3],
            [],
            ["继续把 task_routes 暴露到 Web UI，并记录人工改派。"],
            ["02-agent-team.json", "10-agent-deliberation.json"],
        )
    return _capability(
        "task_specific_agent_routing",
        "P1",
        "review_required" if review_runs else "block",
        "多智能体能力需要可审计的 task_type -> agent team 路由矩阵。",
        review_runs[:4] or ["task_route_runs=0"],
        ["没有检测到带 task_routes 且不同任务队伍有差异的 run。"],
        ["重新生成 02-agent-team，确保包含 literature/gap/benchmark/claim/paper/release 等不同 task routes。"],
        ["02-agent-team.json"],
    )


def _domain_template_check() -> PerfectAgentCapability:
    domains = ["robotics_motion_planning", "bearing_fault_diagnosis", "ai_research_agents"]
    covered = [domain for domain in domains if _domain_candidates(domain)]
    status = "ready" if len(covered) >= 3 else "review_required" if covered else "block"
    gaps = [] if status == "ready" else ["领域模板覆盖不足，benchmark/baseline/metric 推荐会退化为通用规则。"]
    return _capability("domain_template_library", "P1", status, "核心领域需要 benchmark、metric、baseline 和风险模板。", [f"covered_domains={', '.join(covered) or '-'}"], gaps, ["为新增目标领域补 _domain_candidates 模板和对应测试。"], ["benchmark_plan.py", "tests/test_benchmark_plan.py"])


def _human_ui_check(project: Path) -> PerfectAgentCapability:
    files = [path for path in [project / "web" / "index.html", project / "web" / "app.js", project / "web" / "styles.css", project / "src" / "research_agent" / "web_server.py"] if path.exists()]
    index = (project / "web" / "index.html").read_text(encoding="utf-8") if (project / "web" / "index.html").exists() else ""
    app = (project / "web" / "app.js").read_text(encoding="utf-8") if (project / "web" / "app.js").exists() else ""
    server = (project / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8") if (project / "src" / "research_agent" / "web_server.py").exists() else ""
    has_gate_controls = all(term in app + server for term in ["approve", "approve_execution", "repair", "worker_active"])
    has_perfect_readiness_panel = 'id="perfect-readiness"' in index and "/api/perfect-readiness" in app + server
    has_benchmark_manifest_guide = (
        all(term in index for term in ['id="benchmark-template"', 'id="benchmark-manifest-lint"', 'id="benchmark-manifest-save"', 'id="benchmark-manifest-draft"'])
        and all(term in app for term in ["/api/benchmark-template", "/api/benchmark-manifest-lint", "/api/benchmark-manifest-save"])
        and all(term in server for term in ['parsed.path == "/api/benchmark-template"', 'parsed.path == "/api/benchmark-manifest-lint"', 'parsed.path == "/api/benchmark-manifest-save"'])
    )
    status = "ready" if len(files) == 4 and has_gate_controls else "review_required" if files else "block"
    gaps = [] if status == "ready" else ["Web UI 尚未完整覆盖 review/execution/repair gate。"]
    actions = (
        ["继续保持 perfect-readiness 面板、benchmark manifest 向导和人工 gate 与 Gold Bundle/Gold Smoke 状态同步。"]
        if has_perfect_readiness_panel and has_benchmark_manifest_guide
        else ["继续增加 perfect-readiness 面板和 benchmark pack 向导。"]
    )
    return _capability(
        "human_collaboration_ui",
        "P2",
        status,
        "用户应能在 UI 中补 seed、manifest、批准 gate、恢复修复。",
        [
            f"web_files={len(files)}/4",
            f"gate_controls={has_gate_controls}",
            f"perfect_readiness_panel={has_perfect_readiness_panel}",
            f"benchmark_manifest_guide={has_benchmark_manifest_guide}",
        ],
        gaps,
        actions,
        ["web/index.html", "web/app.js", "web/styles.css", "web_server.py"],
    )


def _cost_queue_check(project: Path, runs: list[RunSummary]) -> PerfectAgentCapability:
    files = [project / "src" / "research_agent" / "run_economics_audit.py", project / "src" / "research_agent" / "repair_queue.py", project / "src" / "research_agent" / "repair_resume.py", project / "src" / "research_agent" / "web_server.py"]
    existing = [path.name for path in files if path.exists()]
    economics_runs = [run.id for run in runs if run.run_economics_status in {"pass", "review_required"}]
    active_queue_runs = [run.id for run in runs if run.repair_queue_items]
    source = (project / "src" / "research_agent" / "web_server.py").read_text(encoding="utf-8") if (project / "src" / "research_agent" / "web_server.py").exists() else ""
    has_worker_guard = "worker_active" in source and "ThreadingHTTPServer" in source
    if len(existing) == 4 and has_worker_guard and economics_runs:
        status = "ready"
        gaps: list[str] = []
    elif len(existing) == 4 and has_worker_guard:
        status = "review_required"
        gaps = ["平台有成本/队列模块，但历史 run 尚缺通过的 economics 证据。"]
    else:
        status = "block"
        gaps = ["缺少成本审计、修复队列或后台 worker 防重入能力。"]
    return _capability("cost_queue_concurrency", "P2", status, "多 run 平台需要预算、修复队列、worker 状态和恢复控制。", [f"modules={', '.join(existing) or '-'}", f"economics_runs={len(economics_runs)}", f"repair_queue_runs={len(active_queue_runs)}", f"worker_guard={has_worker_guard}"], gaps, ["补 run economics gold-run 证据；后续可增加持久化任务队列。"], ["13-run-economics-audit.json", "12-repair-queue.json", "web_server.py"])


def _external_integration_check(project: Path, runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    readme = (project / "README.md").read_text(encoding="utf-8") if (project / "README.md").exists() else ""
    refs = [term for term in ["Zotero", "EndNote", "Zenodo", "OSF", "GitHub"] if term.lower() in readme.lower()]
    release_ready = [run for run in runs if _read_json(run_dirs[run.id] / "10-release-metadata.json").get("status") in {"ready_for_release", "ready_with_warnings"}]
    release_archive_evidence, archive_complete = _release_archive_evidence(release_ready, run_dirs)
    if len(refs) >= 4 and release_ready and archive_complete:
        status = "ready"
        gaps: list[str] = []
        next_actions = ["将已通过的 release metadata 字段带入 gold run，并在正式提交前核对代码/数据/环境 DOI 或稳定 URL。"]
    elif len(refs) >= 4 and release_ready:
        status = "review_required"
        gaps = ["已有 ready release metadata run，但代码、数据或环境归档字段不完整。"]
        next_actions = ["补齐 code repository/archive、data archive/repository 和 environment_url 后重跑 release metadata lint。"]
    elif refs:
        status = "review_required"
        gaps = ["已有引用/归档集成说明，但缺少 ready release metadata 的真实 run。"]
        next_actions = ["为 gold run 填写 release metadata，并归档代码/数据/环境 DOI 或稳定 URL。"]
    else:
        status = "block"
        gaps = ["缺少 Zotero/EndNote、GitHub、Zenodo/OSF 等外部系统集成证据。"]
        next_actions = ["补 Zotero/EndNote、GitHub、Zenodo/OSF 等外部系统集成说明和 release metadata。"]
    evidence = [f"documented_integrations={', '.join(refs) or '-'}", f"release_ready_runs={len(release_ready)}"]
    evidence.extend(release_archive_evidence)
    return _capability("external_research_integrations", "P2", status, "科研闭环需要引用管理、代码仓库、数据/环境归档和投稿包接口。", evidence, gaps, next_actions, ["01-references.bib", "01-references.ris", "10-release-metadata.json", "11-submission-package.zip"])


def _release_archive_evidence(runs: list[RunSummary], run_dirs: dict[str, Path]) -> tuple[list[str], bool]:
    if not runs:
        return ["release_archive_fields=0/0"], False
    counts = {"code_repository": 0, "code_archive": 0, "data_archive": 0, "environment_url": 0}
    complete = 0
    for run in runs:
        report = _read_json(run_dirs[run.id] / "10-release-metadata.json")
        metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        code_repository = _public_url(str(metadata.get("code_repository_url") or "").strip())
        code_archive = _doi_or_public_url(str(metadata.get("code_archive_doi") or "").strip())
        data_archive = _doi_or_public_url(str(metadata.get("data_archive_doi") or "").strip()) or _public_url(str(metadata.get("data_repository_url") or "").strip())
        environment_url = _public_url(str(metadata.get("environment_url") or "").strip())
        values = {
            "code_repository": code_repository,
            "code_archive": code_archive,
            "data_archive": data_archive,
            "environment_url": environment_url,
        }
        for key, ready in values.items():
            counts[key] += int(ready)
        complete += int(all(values.values()))
    total = len(runs)
    evidence = [
        (
            "release_archive_fields="
            f"complete:{complete}/{total}, "
            f"code_repository:{counts['code_repository']}/{total}, "
            f"code_archive:{counts['code_archive']}/{total}, "
            f"data_archive:{counts['data_archive']}/{total}, "
            f"environment_url:{counts['environment_url']}/{total}"
        )
    ]
    return evidence, complete == total


def _execution_isolation_check(project: Path, runs: list[RunSummary], run_dirs: dict[str, Path]) -> PerfectAgentCapability:
    safety = (project / "src" / "research_agent" / "execution_safety.py").read_text(encoding="utf-8") if (project / "src" / "research_agent" / "execution_safety.py").exists() else ""
    experiments = (project / "src" / "research_agent" / "experiments.py").read_text(encoding="utf-8") if (project / "src" / "research_agent" / "experiments.py").exists() else ""
    has_allowlist = "allowed_commands" in safety + experiments
    has_timeout = "timeout" in safety + experiments
    has_experiment_dir = "experiments" in safety + experiments
    pass_runs = [run.id for run in runs if _read_json(run_dirs[run.id] / "03-execution-safety-audit.json").get("status") == "pass"]
    if has_allowlist and has_timeout and has_experiment_dir and pass_runs:
        status = "ready"
        gaps: list[str] = []
    elif has_allowlist and has_timeout and has_experiment_dir:
        status = "review_required"
        gaps = ["已有 allowlist/timeout/workdir 控制，但缺少真实 run safety pass 证据；容器级隔离仍可加强。"]
    else:
        status = "block"
        gaps = ["执行器缺少命令白名单、超时或工作目录隔离证据。"]
    return _capability("execution_safety_isolation", "P2", status, "真实 benchmark 执行需要命令白名单、最小环境、超时、工作目录隔离，最好有容器 sandbox。", [f"allowlist={has_allowlist}", f"timeout={has_timeout}", f"workdir={has_experiment_dir}", f"safety_pass_runs={len(pass_runs)}"], gaps, ["为 gold benchmark run 保留 03-execution-safety-audit pass；后续接入容器 sandbox。"], ["03-execution-safety-audit.json", "04-experiment-runbook.json", "Dockerfile"])


def _discover_manifest_groups(project: Path) -> dict[str, list[_ManifestRecord]]:
    roots = [project / "benchmarks", project / "examples"]
    records: list[_ManifestRecord] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted([*root.rglob("*.json"), *root.rglob("*.toml"), *root.rglob("*.tml")]):
            if "manifest" not in path.name or path.name.endswith(".schema.json"):
                continue
            data = _read_manifest(path)
            if not data or not isinstance(data.get("command"), list):
                continue
            role = _manifest_role(path, data)
            group = _manifest_group(path, role)
            records.append(
                _ManifestRecord(
                    path=path,
                    group=group,
                    role=role,
                    benchmark_kind=str(data.get("benchmark_kind") or "").strip().lower(),
                    benchmark_url=str(data.get("benchmark_url") or "").strip(),
                    dataset_url=str(data.get("dataset_url") or "").strip(),
                    citation=str(data.get("citation") or "").strip(),
                    command_signature=_command_signature(data),
                    method_flag=_command_option(data, "--method"),
                    metrics_path=str(data.get("metrics_path") or "").strip(),
                    has_source_files=bool(data.get("source_files")),
                    has_grader=bool(str(data.get("grader") or "").strip() or str(data.get("grader_path") or "").strip()),
                )
            )
    groups: dict[str, list[_ManifestRecord]] = {}
    for record in records:
        groups.setdefault(record.group, []).append(record)
    return groups


def _complete_external_groups(groups: dict[str, list[_ManifestRecord]]) -> list[list[_ManifestRecord]]:
    result: list[list[_ManifestRecord]] = []
    for records in groups.values():
        role_records = [item for item in records if item.role in _ROLES]
        roles = {item.role for item in role_records}
        if roles >= _ROLES and all(_is_formal_external_manifest(item) for item in role_records if item.role in _ROLES):
            result.append(role_records)
    return result


def _role_commands_ready(records: list[_ManifestRecord]) -> bool:
    role_records = [item for item in records if item.role in _ROLES]
    signatures = {item.command_signature for item in role_records if item.command_signature}
    return len({item.role for item in role_records}) >= 3 and len(signatures) >= 3 and all(item.has_source_files and item.has_grader for item in role_records)


def _role_mapping_readme_ready(records: list[_ManifestRecord]) -> bool:
    readme = _role_mapping_readme_text(records)
    if not readme:
        return False
    for record in _primary_role_records(records):
        if not all(
            needle in readme
            for needle in [
                f"`{record.role}`",
                f"`{record.path.name}`",
                f"`--method {record.method_flag}`",
                f"`{record.metrics_path}`",
            ]
        ):
            return False
    return True


def _role_mapping_readme_evidence(records: list[_ManifestRecord]) -> str:
    readme_path = _role_mapping_readme_path(records)
    status = "ready" if _role_mapping_readme_ready(records) else "missing"
    return f"parameter_mapping_readme={status}; path={readme_path if readme_path else '-'}"


def _role_mapping_readme_text(records: list[_ManifestRecord]) -> str:
    path = _role_mapping_readme_path(records)
    if path is None or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _role_mapping_readme_path(records: list[_ManifestRecord]) -> Path | None:
    if not records:
        return None
    return Path(records[0].group) / "README.md"


def _primary_role_records(records: list[_ManifestRecord]) -> list[_ManifestRecord]:
    by_role: dict[str, _ManifestRecord] = {}
    for record in sorted(records, key=lambda item: str(item.path)):
        if record.role in _ROLES:
            by_role.setdefault(record.role, record)
    return [by_role[role] for role in ["candidate", "baseline", "ablation"] if role in by_role]


def _is_formal_external_manifest(record: _ManifestRecord) -> bool:
    if "examples" in record.path.parts:
        return False
    if record.benchmark_kind in {"fixture", "procedural", "local", "private", "placeholder"}:
        return False
    return _public_url(record.dataset_url) and _public_url(record.benchmark_url) and bool(_citation_locator(record.citation))


def _manifest_evidence(groups: dict[str, list[_ManifestRecord]]) -> list[str]:
    if not groups:
        return ["manifest_groups=0"]
    return [_group_summary(records) for records in list(groups.values())[:5]]


def _group_summary(records: list[_ManifestRecord]) -> str:
    roles = sorted({item.role for item in records if item.role})
    external = sum(1 for item in records if _is_formal_external_manifest(item))
    return f"{records[0].group}: roles={','.join(roles) or '-'}, formal_external={external}/{len(records)}"


def _is_gold_run(run: RunSummary, run_dir: Path | None = None) -> bool:
    return (
        run.benchmark_evidence_grade == "real_benchmark"
        and run.adapter_paper_grade_status == "ready"
        and run.paper_grade_literature_status == "pass"
        and _gold_claim_traceability_pass(run)
        and _gold_claim_boundary_closed(run)
        and _gold_run_economics_pass(run)
        and _gold_handoff_sources_ready(run)
        and _gold_verification_ready(run_dir)
        and run.final_handoff_status in {"ready_for_human_handoff", "ready_for_submission_upload"}
        and run.final_handoff_blocking_issues == 0
        and run.repair_queue_block == 0
    )


def _gold_claim_boundary_closed(run: RunSummary) -> bool:
    if run.claim_consistency_status != "pass" or run.claim_consistency_blocking_issues:
        return False
    if run.benchmark_publishable_negative_or_neutral:
        return run.benchmark_claim_boundary_severity == "negative_or_neutral_no_superiority"
    return True


def _gold_claim_traceability_pass(run: RunSummary) -> bool:
    return (
        run.claim_traceability_status == "pass"
        and run.claim_traceability_blocked_claims == 0
        and run.claim_traceability_blocking_issues == 0
    )


def _gold_run_economics_pass(run: RunSummary) -> bool:
    return run.run_economics_status == "pass" and run.run_economics_blocking_issues == 0


def _gold_handoff_sources_ready(run: RunSummary) -> bool:
    if run.final_handoff_package_zip_valid is not True:
        return False
    if run.final_handoff_status == "ready_for_submission_upload":
        return (
            run.package_status == "ready_for_human_submission_upload"
            and run.package_blocking_issues == 0
            and run.scorecard_status == "ready_for_human_submission_upload"
            and run.scorecard_blocking_issues == 0
            and run.run_integrity_status == "pass"
            and run.run_integrity_blocking_issues == 0
        )
    return (
        bool(run.package_status)
        and run.package_status != "blocked"
        and run.package_blocking_issues == 0
        and bool(run.scorecard_status)
        and run.scorecard_status != "blocked"
        and run.scorecard_blocking_issues == 0
        and bool(run.run_integrity_status)
        and run.run_integrity_status != "block"
        and run.run_integrity_blocking_issues == 0
    )


def _gold_verification_ready(run_dir: Path | None) -> bool:
    if run_dir is None:
        return False
    report = _read_json(run_dir / "15-gold-run-verification.json")
    secret_scan = report.get("secret_scan") if isinstance(report.get("secret_scan"), dict) else {}
    missing = report.get("missing_artifacts")
    repair_plan = report.get("repair_plan")
    return (
        report.get("status") == "ready"
        and report.get("gold_contract_ready") is True
        and _gold_verification_summary_ready(report)
        and _gold_verification_schema_ready(report)
        and _gold_verification_subschemas_ready(report)
        and _gold_verification_secret_scan_ready(secret_scan)
        and _gold_verification_secret_scan_summary_ready(secret_scan)
        and _gold_verification_required_artifacts_ready(report)
        and _gold_verification_contract_evidence_ready(report)
        and _gold_verification_final_zip_summary_ready(report)
        and _gold_verification_artifact_safety_ready(report)
        and _gold_verification_artifact_safety_summary_ready(report)
        and _gold_verification_artifact_hashes_match(run_dir, report)
        and _gold_verification_manifest_inventory_ready(report)
        and _gold_verification_manifest_inventory_summary_ready(report)
        and _gold_current_manifest_inventory_ready(run_dir)
        and _gold_verification_audit_contracts_ready(report)
        and _gold_verification_audit_summary_ready(report)
        and _gold_current_audit_contracts_ready(run_dir, report)
        and isinstance(missing, list)
        and not missing
        and _gold_verification_check_status(report) == "pass"
        and _gold_verification_run_dir_matches(report, run_dir)
        and _gold_verification_fresh_for_required_artifacts(run_dir)
        and isinstance(repair_plan, list)
        and not repair_plan
        and not _gold_current_package_zip_issue(run_dir)
        and _gold_current_artifact_safety_ready(run_dir)
        and _gold_current_secret_scan_ready(run_dir)
    )


def _gold_verification_state(run_dir: Path | None) -> str:
    if run_dir is None:
        return "missing"
    report = _read_json(run_dir / "15-gold-run-verification.json")
    if not report:
        return "missing"
    secret_scan = report.get("secret_scan") if isinstance(report.get("secret_scan"), dict) else {}
    state = str(report.get("status") or "-")
    if report.get("gold_contract_ready") is True:
        state += "; contract=ready"
    state += f"; verification_summary={_gold_verification_summary_state(report)}"
    state += f"; schema={_gold_verification_schema_state(report)}"
    state += f"; subschemas={_gold_verification_subschema_state(report)}"
    if secret_scan.get("status"):
        state += f"; secret_scan={secret_scan.get('status')}"
    state += f"; secret_findings={_gold_verification_secret_finding_count(secret_scan)}"
    state += f"; secret_malformed_findings={_gold_secret_scan_malformed_finding_count(secret_scan)}"
    state += f"; secret_scan_summary={_gold_verification_secret_scan_summary_state(secret_scan)}"
    state += f"; required={_gold_verification_required_artifact_state(report)}"
    missing = report.get("missing_artifacts")
    state += f"; missing={len(missing) if isinstance(missing, list) else 'unknown'}"
    state += f"; missing_malformed={_gold_verification_missing_artifacts_malformed_count(report)}"
    state += f"; check={_gold_verification_check_status(report) or '-'}"
    state += f"; run_dir={_gold_verification_run_dir_state(report, run_dir)}"
    state += f"; contract_evidence={_gold_verification_contract_evidence_state(report)}"
    state += f"; final_zip={_gold_verification_final_zip_state(report)}"
    state += f"; final_zip_summary={_gold_verification_final_zip_summary_state(report)}"
    state += f"; audit_contracts={_gold_verification_audit_contract_state(report)}"
    state += f"; audit_summary={_gold_verification_audit_summary_state(report)}"
    state += f"; current_audit_contracts={_gold_current_audit_contract_state(run_dir, report)}"
    state += f"; artifact_safety={_gold_verification_artifact_safety_state(run_dir, report)}"
    state += f"; artifact_safety_summary={_gold_verification_artifact_safety_summary_state(report)}"
    state += f"; artifact_hashes={_gold_verification_artifact_hash_state(run_dir, report)}"
    state += f"; manifest_inventory={_gold_verification_manifest_inventory_state(report)}"
    state += f"; manifest_inventory_summary={_gold_verification_manifest_inventory_summary_state(report)}"
    state += f"; current_manifest_inventory={_gold_current_manifest_inventory_state(run_dir)}"
    state += f"; freshness={_gold_verification_freshness_state(run_dir)}"
    repair_plan = report.get("repair_plan")
    state += f"; repairs={len(repair_plan) if isinstance(repair_plan, list) else 'unknown'}"
    state += f"; repair_malformed={_gold_verification_repair_plan_malformed_count(report)}"
    state += f"; zip_current={'invalid' if _gold_current_package_zip_issue(run_dir) else 'valid'}"
    state += f"; current_secret_scan={_gold_current_secret_scan_state(run_dir)}"
    return state


def _gold_current_package_zip_issue(run_dir: Path) -> str:
    package = _read_json(run_dir / "11-submission-package.json")
    zip_name = str(package.get("package_zip") or "11-submission-package.zip")
    return submission_package_zip_blocking_issue(run_dir / zip_name, package_zip_name=zip_name, require_safe_filename=True)


def _gold_current_secret_scan_ready(run_dir: Path) -> bool:
    return _secret_scan_report_ready(_gold_run_secret_scan(run_dir))


def _gold_current_secret_scan_state(run_dir: Path) -> str:
    report = _gold_run_secret_scan(run_dir)
    return f"{report.get('status') or '-'}:{_gold_verification_secret_finding_count(report)}"


def _gold_verification_fresh_for_required_artifacts(run_dir: Path) -> bool:
    return _gold_verification_freshness_state(run_dir) == "fresh"


def _gold_verification_freshness_state(run_dir: Path) -> str:
    verification_path = run_dir / "15-gold-run-verification.json"
    try:
        verification_mtime = verification_path.stat().st_mtime_ns
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unknown"
    for name in _GOLD_VERIFICATION_REQUIRED_ARTIFACTS:
        try:
            if (run_dir / name).stat().st_mtime_ns > verification_mtime:
                return "stale"
        except FileNotFoundError:
            return "stale"
        except OSError:
            return "unknown"
    return "fresh"


def _gold_verification_required_artifacts_ready(report: dict[str, Any]) -> bool:
    return (
        _gold_verification_required_artifact_state(report)
        == f"{len(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)}/{len(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)}; missing=0; extra=0; duplicate=0; malformed=0"
    )


def _gold_verification_required_artifact_state(report: dict[str, Any]) -> str:
    required = report.get("required_artifacts")
    if not isinstance(required, list):
        return f"0/{len(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)}; missing=unknown; extra=unknown; duplicate=unknown; malformed=unknown"
    malformed = sum(int(not _exact_nonempty_string(item)) for item in required)
    names = [item for item in required if _exact_nonempty_string(item)]
    expected = list(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)
    expected_set = set(expected)
    names_set = set(names)
    missing = [name for name in expected if name not in names_set]
    extra = [name for name in names if name not in expected_set]
    duplicate = len(names) - len(names_set)
    present = sum(int(name in names_set) for name in expected)
    return f"{present}/{len(expected)}; missing={len(missing)}; extra={len(extra)}; duplicate={duplicate}; malformed={malformed}"


def _gold_verification_summary_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_summary_state(report) == "match"


def _gold_verification_summary_state(report: dict[str, Any]) -> str:
    missing = report.get("missing_artifacts")
    repair_plan = report.get("repair_plan")
    if not isinstance(missing, list) or not isinstance(repair_plan, list):
        return "missing"
    missing_malformed = _gold_verification_missing_artifacts_malformed_count(report)
    repair_malformed = _gold_verification_repair_plan_malformed_count(report)
    if missing_malformed is None or repair_malformed is None:
        return "missing"
    check_ready = _gold_verification_check_status(report) == "pass"
    ready_flag = report.get("gold_contract_ready") is True
    expected_ready = ready_flag and check_ready and not missing and not repair_plan and missing_malformed == 0 and repair_malformed == 0
    expected_status = "ready" if expected_ready else "blocked"
    mismatches = 0
    mismatches += int(str(report.get("status") or "") != expected_status)
    mismatches += int(ready_flag != (str(report.get("status") or "") == "ready"))
    mismatches += int(missing_malformed != 0)
    mismatches += int(repair_malformed != 0)
    return "match" if not mismatches else f"mismatch={mismatches}"


def _gold_verification_missing_artifacts_malformed_count(report: dict[str, Any]) -> int | None:
    missing = report.get("missing_artifacts")
    if not isinstance(missing, list):
        return None
    expected = set(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)
    return sum(int(not _exact_nonempty_string(item) or item not in expected) for item in missing)


def _gold_verification_repair_plan_malformed_count(report: dict[str, Any]) -> int | None:
    repair_plan = report.get("repair_plan")
    if not isinstance(repair_plan, list):
        return None
    malformed = 0
    for item in repair_plan:
        if not isinstance(item, dict):
            malformed += 1
            continue
        malformed += int(not _exact_nonempty_string(item.get("id")))
        malformed += int(not _exact_nonempty_string(item.get("action")))
        targets = item.get("target_artifacts")
        if not isinstance(targets, list):
            malformed += 1
            continue
        malformed += sum(int(not _exact_nonempty_string(target)) for target in targets)
    return malformed


def _gold_verification_schema_ready(report: dict[str, Any]) -> bool:
    return report.get("schema_version") == 2 and report.get("read_only") is True


def _gold_verification_schema_state(report: dict[str, Any]) -> str:
    version = report.get("schema_version")
    version_text = str(version) if isinstance(version, int) and not isinstance(version, bool) else "missing"
    mode = "read_only" if report.get("read_only") is True else "mutable"
    return f"{version_text}:{mode}"


def _gold_verification_subschemas_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_subschema_state(report) == "artifact_safety=1,manifest_inventory=1,secret_scan=1"


def _gold_verification_subschema_state(report: dict[str, Any]) -> str:
    artifact_safety = report.get("artifact_safety") if isinstance(report.get("artifact_safety"), dict) else {}
    manifest_inventory = report.get("manifest_inventory") if isinstance(report.get("manifest_inventory"), dict) else {}
    secret_scan = report.get("secret_scan") if isinstance(report.get("secret_scan"), dict) else {}
    return (
        f"artifact_safety={_schema_version_label(artifact_safety.get('schema_version'))},"
        f"manifest_inventory={_schema_version_label(manifest_inventory.get('schema_version'))},"
        f"secret_scan={_schema_version_label(secret_scan.get('schema_version'))}"
    )


def _schema_version_label(value: Any) -> str:
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else "missing"


def _gold_verification_artifact_safety_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_report_artifact_safety_state(report) == "pass:0"


def _gold_verification_artifact_safety_summary_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_artifact_safety_summary_state(report) == "match"


def _gold_verification_artifact_safety_state(run_dir: Path, report: dict[str, Any]) -> str:
    current_state = _gold_current_artifact_safety_state(run_dir)
    if current_state != "pass:0":
        return current_state
    return _gold_verification_report_artifact_safety_state(report)


def _gold_verification_report_artifact_safety_state(report: dict[str, Any]) -> str:
    safety = report.get("artifact_safety") if isinstance(report.get("artifact_safety"), dict) else {}
    unsafe = report.get("unsafe_artifacts")
    if not isinstance(unsafe, list):
        return "missing"
    status = str(safety.get("status") or "-")
    return f"{status}:{len(unsafe)}"


def _gold_verification_artifact_safety_summary_state(report: dict[str, Any]) -> str:
    safety = report.get("artifact_safety") if isinstance(report.get("artifact_safety"), dict) else {}
    unsafe = _gold_artifact_safety_items(report.get("unsafe_artifacts"))
    nested = _gold_artifact_safety_items(safety.get("unsafe_artifacts"))
    if unsafe is None or nested is None:
        return "missing"
    expected_status = "blocked" if unsafe else "pass"
    mismatches = 0
    mismatches += int(str(safety.get("status") or "") != expected_status)
    mismatches += int(not _gold_verification_int_field_matches(safety, "checked_artifacts", len(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)))
    mismatches += int(safety.get("safe_to_render") is not True)
    mismatches += int(nested != unsafe)
    return "match" if not mismatches else f"mismatch={mismatches}"


def _gold_artifact_safety_items(value: Any) -> list[tuple[str, str]] | None:
    if not isinstance(value, list):
        return None
    items: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        issue = item.get("issue")
        if not _exact_nonempty_string(path) or not _exact_nonempty_string(issue):
            return None
        items.append((path, issue))
    return sorted(items)


def _gold_current_artifact_safety_ready(run_dir: Path) -> bool:
    return not _gold_unsafe_required_artifacts(run_dir)


def _gold_current_artifact_safety_state(run_dir: Path) -> str:
    unsafe = _gold_unsafe_required_artifacts(run_dir)
    return f"{'blocked' if unsafe else 'pass'}:{len(unsafe)}"


def _gold_verification_artifact_hashes_match(run_dir: Path, report: dict[str, Any]) -> bool:
    return _gold_verification_artifact_hash_state(run_dir, report) == "match"


def _gold_verification_manifest_inventory_ready(report: dict[str, Any]) -> bool:
    inventory = report.get("manifest_inventory")
    return (
        isinstance(inventory, dict)
        and inventory.get("status") == "pass"
        and inventory.get("missing_required_artifacts") == []
        and inventory.get("hash_mismatches") == []
        and inventory.get("size_mismatches") == []
        and inventory.get("duplicate_required_artifacts") == []
        and inventory.get("unsafe_artifact_paths") == []
    )


def _gold_verification_manifest_inventory_summary_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_manifest_inventory_summary_state(report) == "match"


def _gold_current_manifest_inventory_ready(run_dir: Path) -> bool:
    return _gold_current_manifest_inventory_state(run_dir).startswith("pass:")


def _gold_current_manifest_inventory_state(run_dir: Path) -> str:
    return _gold_manifest_inventory_report_state(_gold_manifest_inventory_check(run_dir, _gold_required_artifact_hashes(run_dir)))


def _gold_verification_manifest_inventory_state(report: dict[str, Any]) -> str:
    inventory = report.get("manifest_inventory")
    if not isinstance(inventory, dict):
        return "missing"
    return _gold_manifest_inventory_report_state(inventory)


def _gold_verification_manifest_inventory_summary_state(report: dict[str, Any]) -> str:
    inventory = report.get("manifest_inventory")
    if not isinstance(inventory, dict):
        return "missing"
    missing = inventory.get("missing_required_artifacts")
    mismatches = inventory.get("hash_mismatches")
    size_mismatches = inventory.get("size_mismatches")
    duplicates = inventory.get("duplicate_required_artifacts")
    unsafe = inventory.get("unsafe_artifact_paths")
    if not all(isinstance(value, list) for value in [missing, mismatches, size_mismatches, duplicates, unsafe]):
        return "missing"
    malformed = _gold_manifest_inventory_malformed_item_count(inventory)
    if malformed is None:
        return "missing"
    expected_checked = len([name for name in _GOLD_VERIFICATION_REQUIRED_ARTIFACTS if name != "run-manifest.json"])
    expected_status = "blocked" if missing or mismatches or size_mismatches or duplicates or unsafe or malformed else "pass"
    recorded = inventory.get("recorded_artifacts")
    recorded_ok = isinstance(recorded, int) and not isinstance(recorded, bool) and recorded >= expected_checked
    mismatched = 0
    mismatched += int(str(inventory.get("status") or "") != expected_status)
    mismatched += int(not _gold_verification_int_field_matches(inventory, "checked_artifacts", expected_checked))
    mismatched += int(not recorded_ok)
    mismatched += int(inventory.get("safe_to_render") is not True)
    mismatched += int(malformed != 0)
    return "match" if not mismatched else f"mismatch={mismatched}"


def _gold_manifest_inventory_report_state(inventory: dict[str, Any]) -> str:
    missing = inventory.get("missing_required_artifacts")
    mismatches = inventory.get("hash_mismatches")
    size_mismatches = inventory.get("size_mismatches")
    duplicates = inventory.get("duplicate_required_artifacts")
    unsafe = inventory.get("unsafe_artifact_paths")
    malformed = _gold_manifest_inventory_malformed_item_count(inventory)
    return (
        f"{inventory.get('status') or '-'}:"
        f"missing={len(missing) if isinstance(missing, list) else 'unknown'},"
        f"mismatch={len(mismatches) if isinstance(mismatches, list) else 'unknown'},"
        f"size_mismatch={len(size_mismatches) if isinstance(size_mismatches, list) else 'unknown'},"
        f"duplicate={len(duplicates) if isinstance(duplicates, list) else 'unknown'},"
        f"unsafe={len(unsafe) if isinstance(unsafe, list) else 'unknown'},"
        f"malformed={malformed if malformed is not None else 'unknown'}"
    )


def _gold_manifest_inventory_malformed_item_count(inventory: dict[str, Any]) -> int | None:
    malformed_manifest_inventory_items = 0
    for key in ["missing_required_artifacts", "hash_mismatches", "size_mismatches", "duplicate_required_artifacts"]:
        value = inventory.get(key)
        if not isinstance(value, list):
            return None
        malformed_manifest_inventory_items += sum(int(not _exact_nonempty_string(item)) for item in value)
    unsafe = inventory.get("unsafe_artifact_paths")
    if not isinstance(unsafe, list):
        return None
    for item in unsafe:
        if not isinstance(item, dict):
            malformed_manifest_inventory_items += 1
            continue
        malformed_manifest_inventory_items += int(not _exact_nonempty_string(item.get("path")))
        malformed_manifest_inventory_items += int(not _exact_nonempty_string(item.get("issue")))
    return malformed_manifest_inventory_items


def _gold_verification_audit_contracts_ready(report: dict[str, Any]) -> bool:
    contracts = _gold_verification_audit_contracts(report)
    contract_names = set(contracts)
    expected_names = set(_GOLD_VERIFICATION_AUDIT_CONTRACTS)
    policy = _gold_verification_audit_policy(report)
    return (
        contract_names == expected_names
        and all(_gold_verification_audit_contract_ready(contracts.get(name), policy) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    )


def _gold_verification_audit_summary_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_audit_summary_state(report) == "match"


def _gold_verification_audit_policy(report: dict[str, Any]) -> str:
    evidence = _gold_verification_contract_evidence(report)
    if evidence.get("audit_contract_policy") == "human_handoff":
        return "human_handoff"
    return "submission_upload"


def _gold_current_audit_policy(run_dir: Path) -> str:
    handoff = _read_json(run_dir / "14-final-handoff.json")
    if str(handoff.get("status") or "") == "ready_for_human_handoff":
        return "human_handoff"
    return "submission_upload"


def _gold_current_audit_contracts_ready(run_dir: Path, report: dict[str, Any] | None = None) -> bool:
    contracts = _gold_current_audit_contracts(run_dir)
    policy = _gold_verification_audit_policy(report) if report is not None else _gold_current_audit_policy(run_dir)
    return all(_gold_current_audit_contract_ready(contracts.get(name), policy) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)


def _gold_verification_audit_contract_ready(value: Any, policy: str = "submission_upload") -> bool:
    if not isinstance(value, dict):
        return False
    if policy == "human_handoff":
        return (
            value.get("ready") is True
            and str(value.get("status") or "") in _GOLD_HUMAN_HANDOFF_AUDIT_STATUSES
            and _zero_int(value.get("blocking_issues"))
            and _nonnegative_int(value.get("manual_tasks"))
        )
    return (
        value.get("ready") is True
        and str(value.get("status") or "") == "pass"
        and _zero_int(value.get("blocking_issues"))
        and _zero_int(value.get("manual_tasks"))
    )


def _gold_current_audit_contract_ready(value: Any, policy: str = "submission_upload") -> bool:
    if not isinstance(value, dict):
        return False
    if policy == "human_handoff":
        return str(value.get("status") or "") in _GOLD_HUMAN_HANDOFF_AUDIT_STATUSES and _zero_int(value.get("blocking_issues")) and _nonnegative_int(value.get("manual_tasks"))
    return str(value.get("status") or "") == "pass" and _zero_int(value.get("blocking_issues")) and _zero_int(value.get("manual_tasks"))


def _gold_verification_audit_contract_state(report: dict[str, Any]) -> str:
    contracts = _gold_verification_audit_contracts(report)
    if not contracts:
        return "missing"
    policy = _gold_verification_audit_policy(report)
    ready, blocking, manual, missing, extra, malformed = _gold_verification_audit_contract_counts(contracts, policy)
    return f"{ready}/{len(_GOLD_VERIFICATION_AUDIT_CONTRACTS)}; blocking={blocking}; manual={manual}; missing={missing}; extra={extra}; malformed={malformed}; policy={policy}"


def _gold_verification_audit_summary_state(report: dict[str, Any]) -> str:
    evidence = _gold_verification_contract_evidence(report)
    contracts = _gold_verification_audit_contracts(report)
    if not contracts:
        return "missing"
    policy = _gold_verification_audit_policy(report)
    ready, blocking, manual, missing, extra, malformed = _gold_verification_audit_contract_counts(contracts, policy)
    expected_ready = (
        ready == len(_GOLD_VERIFICATION_AUDIT_CONTRACTS)
        and blocking == 0
        and (manual == 0 or policy == "human_handoff")
        and missing == 0
        and extra == 0
        and malformed == 0
    )
    mismatches = 0
    mismatches += int(evidence.get("audit_contracts_ready") is not expected_ready)
    mismatches += int(not _gold_verification_int_field_matches(evidence, "audit_contract_ready_count", ready))
    mismatches += int(not _gold_verification_int_field_matches(evidence, "audit_contract_total", len(_GOLD_VERIFICATION_AUDIT_CONTRACTS)))
    mismatches += int(not _gold_verification_int_field_matches(evidence, "audit_contract_blocking_issues", blocking))
    mismatches += int(not _gold_verification_int_field_matches(evidence, "audit_contract_manual_tasks", manual))
    mismatches += int(extra != 0)
    mismatches += int(malformed != 0)
    return "match" if not mismatches else f"mismatch={mismatches}"


def _gold_verification_audit_contract_counts(contracts: dict[str, Any], policy: str = "submission_upload") -> tuple[int, int, int, int, int, int]:
    ready = sum(int(_gold_verification_audit_contract_ready(contracts.get(name), policy)) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    blocking = sum(_gold_verification_audit_issue_count(contracts.get(name), "blocking_issues") for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    manual = sum(_gold_verification_audit_issue_count(contracts.get(name), "manual_tasks") for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    missing = sum(int(name not in contracts) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    expected = set(_GOLD_VERIFICATION_AUDIT_CONTRACTS)
    malformed_audit_names = sum(int(not _exact_nonempty_string(name)) for name in contracts)
    extra = sum(int(_exact_nonempty_string(name) and name not in expected) for name in contracts)
    return ready, blocking, manual, missing, extra, malformed_audit_names


def _gold_verification_int_field_matches(evidence: dict[str, Any], key: str, expected: int) -> bool:
    value = evidence.get(key)
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _gold_current_audit_contract_state(run_dir: Path, report: dict[str, Any] | None = None) -> str:
    contracts = _gold_current_audit_contracts(run_dir)
    policy = _gold_verification_audit_policy(report) if report is not None else _gold_current_audit_policy(run_dir)
    ready = sum(int(_gold_current_audit_contract_ready(contracts.get(name), policy)) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    blocking = sum(_gold_audit_issue_count(contracts.get(name, {}).get("blocking_issues")) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    manual = sum(_gold_audit_issue_count(contracts.get(name, {}).get("manual_tasks")) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    missing = sum(int(not str(contracts.get(name, {}).get("status") or "")) for name in _GOLD_VERIFICATION_AUDIT_CONTRACTS)
    return f"{ready}/{len(_GOLD_VERIFICATION_AUDIT_CONTRACTS)}; blocking={blocking}; manual={manual}; missing={missing}; policy={policy}"


def _gold_verification_audit_contracts(report: dict[str, Any]) -> dict[str, Any]:
    evidence = _gold_verification_contract_evidence(report)
    contracts = evidence.get("audit_contracts")
    return contracts if isinstance(contracts, dict) else {}


def _gold_current_audit_contracts(run_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        name: _gold_current_audit_contract(_read_json(run_dir / artifact))
        for name, artifact in _GOLD_VERIFICATION_AUDIT_CONTRACT_ARTIFACTS.items()
    }


def _gold_current_audit_contract(report: dict[str, Any]) -> dict[str, Any]:
    has_status = bool(str(report.get("status") or "").strip())
    return {
        "status": str(report.get("status") or ""),
        "blocking_issues": _gold_audit_issue_count(report.get("blocking_issues"), invalid_count=1 if has_status else 0),
        "manual_tasks": _gold_audit_issue_count(report.get("manual_tasks"), invalid_count=1 if has_status else 0),
    }


def _gold_audit_issue_count(value: Any, *, invalid_count: int = 1) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return invalid_count


def _gold_verification_audit_issue_count(contract: Any, key: str) -> int:
    if not isinstance(contract, dict):
        return 0
    return _gold_audit_issue_count(contract.get(key))


def _zero_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _gold_verification_artifact_hash_state(run_dir: Path, report: dict[str, Any]) -> str:
    artifact_hashes = report.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        return "missing"
    expected_names = set(_GOLD_VERIFICATION_REQUIRED_ARTIFACTS)
    malformed_names = sum(int(not _exact_nonempty_string(name)) for name in artifact_hashes)
    if malformed_names:
        return f"malformed={malformed_names}"
    recorded_names = set(artifact_hashes)
    extra_names = recorded_names - expected_names
    if extra_names:
        return f"extra={len(extra_names)}"
    for name in _GOLD_VERIFICATION_REQUIRED_ARTIFACTS:
        entry = artifact_hashes.get(name)
        if not isinstance(entry, dict):
            return "missing"
        expected_sha = entry.get("sha256")
        expected_size = entry.get("size_bytes")
        if not (isinstance(expected_sha, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha) and _positive_int(expected_size)):
            return "missing"
        path = run_dir / name
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            return "missing"
        except OSError:
            return "unknown"
        if current_size != expected_size:
            return "mismatch"
        current_sha = _gold_file_sha256(path)
        if current_sha is None:
            return "unknown"
        if current_sha != expected_sha:
            return "mismatch"
    return "match"


def _gold_file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _gold_verification_secret_scan_ready(secret_scan: dict[str, Any]) -> bool:
    return _secret_scan_report_ready(secret_scan)


def _gold_verification_secret_scan_summary_ready(secret_scan: dict[str, Any]) -> bool:
    return _gold_verification_secret_scan_summary_state(secret_scan) == "match"


def _secret_scan_report_ready(secret_scan: dict[str, Any]) -> bool:
    findings = secret_scan.get("findings")
    return secret_scan.get("status") == "pass" and secret_scan.get("finding_count") == 0 and isinstance(findings, list) and not findings


def _gold_verification_secret_scan_summary_state(secret_scan: dict[str, Any]) -> str:
    findings = secret_scan.get("findings")
    if not isinstance(findings, list):
        return "missing"
    counts: list[int] = []
    for item in findings:
        if not isinstance(item, dict):
            return "missing"
        count = item.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            return "missing"
        counts.append(count)
    malformed_findings = _gold_secret_scan_malformed_finding_count(secret_scan)
    if malformed_findings is None:
        return "missing"
    finding_count = secret_scan.get("finding_count")
    truncated = secret_scan.get("truncated_findings", 0)
    scanned = secret_scan.get("scanned_files")
    skipped = secret_scan.get("skipped_files")
    rules = secret_scan.get("rules")
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in [finding_count, truncated, scanned, skipped]):
        return "missing"
    if not isinstance(rules, list):
        return "missing"
    malformed_rules = sum(int(not _exact_nonempty_string(item)) for item in rules)
    rule_names = sorted(item for item in rules if _exact_nonempty_string(item))
    visible_count = sum(counts)
    expected_status = "blocked" if finding_count else "pass"
    mismatched = 0
    mismatched += int(str(secret_scan.get("status") or "") != expected_status)
    mismatched += int(finding_count < visible_count)
    mismatched += int(truncated == 0 and finding_count != visible_count)
    mismatched += int(finding_count == 0 and bool(findings))
    mismatched += int(secret_scan.get("safe_to_render") is not True)
    mismatched += int(rule_names != _GOLD_VERIFICATION_SECRET_SCAN_RULES)
    mismatched += int(malformed_findings != 0)
    mismatched += int(malformed_rules != 0)
    return "match" if not mismatched else f"mismatch={mismatched}"


def _gold_secret_scan_malformed_finding_count(secret_scan: dict[str, Any]) -> int | None:
    findings = secret_scan.get("findings")
    if not isinstance(findings, list):
        return None
    allowed_rules = {*_GOLD_VERIFICATION_SECRET_SCAN_RULES, "run_dir_missing"}
    malformed_findings = 0
    for item in findings:
        if not isinstance(item, dict):
            malformed_findings += 1
            continue
        malformed_findings += int(not _exact_nonempty_string(item.get("path")))
        rule = item.get("rule")
        malformed_findings += int(not _exact_nonempty_string(rule) or rule not in allowed_rules)
    return malformed_findings


def _gold_verification_secret_finding_count(secret_scan: dict[str, Any]) -> str:
    value = secret_scan.get("finding_count")
    return str(value) if isinstance(value, int) else "unknown"


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _gold_verification_contract_evidence_ready(report: dict[str, Any]) -> bool:
    evidence = _gold_verification_contract_evidence(report)
    return (
        _gold_verification_contract_evidence_state(report) == "top_level"
        and evidence.get("final_zip_state") == "valid"
        and evidence.get("final_handoff_package_zip_exists") is True
        and evidence.get("final_handoff_package_zip_valid") is True
    )


def _gold_verification_final_zip_summary_ready(report: dict[str, Any]) -> bool:
    return _gold_verification_final_zip_summary_state(report) == "match"


def _gold_verification_final_zip_state(report: dict[str, Any]) -> str:
    evidence = _gold_verification_contract_evidence(report)
    return str(evidence.get("final_zip_state") or "unknown")


def _gold_verification_final_zip_summary_state(report: dict[str, Any]) -> str:
    evidence = _gold_verification_contract_evidence(report)
    if not evidence:
        return "missing"
    state = evidence.get("final_zip_state")
    exists = evidence.get("final_handoff_package_zip_exists")
    valid = evidence.get("final_handoff_package_zip_valid")
    if not _exact_nonempty_string(state) or not isinstance(exists, bool) or not isinstance(valid, bool):
        return "missing"
    expected_state = _gold_zip_state(exists, valid)
    mismatches = int(state != expected_state)
    return "match" if not mismatches else f"mismatch={mismatches}"


def _gold_zip_state(exists: bool, valid: bool) -> str:
    if exists is False:
        return "missing"
    if valid is False:
        return "invalid"
    return "valid"


def _gold_verification_contract_evidence(report: dict[str, Any]) -> dict[str, Any]:
    evidence = report.get("contract_evidence") if isinstance(report.get("contract_evidence"), dict) else {}
    return evidence


def _gold_verification_contract_evidence_state(report: dict[str, Any]) -> str:
    evidence = report.get("contract_evidence")
    return "top_level" if isinstance(evidence, dict) and evidence else "missing"


def _gold_verification_run_dir_matches(report: dict[str, Any], run_dir: Path) -> bool:
    return _gold_verification_run_dir_state(report, run_dir) == "current"


def _gold_verification_run_dir_state(report: dict[str, Any], run_dir: Path) -> str:
    value = str(report.get("run_dir") or "").strip()
    if not value:
        return "missing"
    try:
        recorded = Path(value)
        if not recorded.is_absolute():
            recorded = Path.cwd() / recorded
        return "current" if recorded.resolve() == run_dir.resolve() else "mismatch"
    except OSError:
        return "mismatch"


def _gold_verification_check_status(report: dict[str, Any]) -> str:
    check = report.get("check")
    if not isinstance(check, dict):
        return ""
    return str(check.get("status") or "")


def _gold_candidate_evidence(runs: list[RunSummary], fallback: RunSummary | None, run_dirs: dict[str, Path] | None = None) -> list[str]:
    if not runs:
        return ["runs=0"]
    run_dirs = run_dirs or {}
    candidate = max(runs, key=lambda run: _gold_candidate_rank(run, run_dirs), default=fallback)
    if candidate is None:
        return ["runs=0"]
    met = _gold_candidate_score(candidate, run_dirs.get(candidate.id))
    evidence = [
        f"closest_run={candidate.id}, gold_criteria={met}/9, readiness={candidate.readiness_score:.3f}",
        (
            f"lit={candidate.paper_grade_literature_status or '-'}; "
            f"bench={candidate.benchmark_evidence_status or '-'}/{candidate.benchmark_evidence_grade or '-'}; "
            f"adapter={candidate.adapter_paper_grade_status or '-'}; "
            f"trace={_gold_traceability_state(candidate)}; "
            f"claim={_gold_claim_state(candidate)}; "
            f"economics={_gold_run_economics_state(candidate)}; "
            f"sources={_gold_handoff_source_state(candidate)}; "
            f"verification={_gold_verification_state(run_dirs.get(candidate.id))}; "
            f"final={candidate.final_handoff_status or '-'}; "
            f"repair_block={candidate.repair_queue_block}"
        ),
    ]
    if fallback is not None and fallback.id != candidate.id:
        evidence.append(f"top_readiness_run={fallback.id}, readiness={fallback.readiness_score:.3f}, final={fallback.final_handoff_status or '-'}")
    return evidence


def _gold_candidate_score(run: RunSummary, run_dir: Path | None = None) -> int:
    return sum(
        [
            run.benchmark_evidence_grade == "real_benchmark",
            run.adapter_paper_grade_status == "ready",
            run.paper_grade_literature_status == "pass",
            _gold_claim_traceability_pass(run),
            _gold_claim_boundary_closed(run),
            _gold_run_economics_pass(run),
            _gold_handoff_sources_ready(run)
            and run.final_handoff_status in {"ready_for_human_handoff", "ready_for_submission_upload"}
            and run.final_handoff_blocking_issues == 0,
            _gold_verification_ready(run_dir),
            run.repair_queue_block == 0,
        ]
    )


def _gold_candidate_rank(run: RunSummary, run_dirs: dict[str, Path] | None = None) -> tuple[int, int, float, str, str]:
    run_dirs = run_dirs or {}
    return (
        _gold_candidate_score(run, run_dirs.get(run.id)),
        _end_to_end_signal_score(run),
        run.readiness_score,
        run.updated_at,
        run.id,
    )


def _end_to_end_signal_score(run: RunSummary) -> int:
    return sum(
        [
            bool(run.paper_grade_literature_status),
            bool(run.claim_preflight_status),
            bool(run.claim_traceability_status),
            bool(run.claim_consistency_status),
            bool(run.final_readiness_status),
            bool(run.package_status),
            bool(run.final_handoff_status),
            run.artifact_count >= 25,
        ]
    )


def _gold_claim_state(run: RunSummary) -> str:
    state = run.claim_consistency_status or "-"
    if run.benchmark_publishable_negative_or_neutral:
        state += f"; boundary={run.benchmark_claim_boundary_severity or '-'}"
    if run.claim_consistency_blocking_issues:
        state += f"; blockers={run.claim_consistency_blocking_issues}"
    return state


def _gold_traceability_state(run: RunSummary) -> str:
    state = run.claim_traceability_status or "-"
    if run.claim_traceability_blocked_claims:
        state += f"; blocked_claims={run.claim_traceability_blocked_claims}"
    if run.claim_traceability_blocking_issues:
        state += f"; blockers={run.claim_traceability_blocking_issues}"
    return state


def _gold_run_economics_state(run: RunSummary) -> str:
    return f"{run.run_economics_status or '-'}:{run.run_economics_blocking_issues}"


def _gold_handoff_source_state(run: RunSummary) -> str:
    zip_state = (
        "valid"
        if run.final_handoff_package_zip_valid is True
        else "invalid"
        if run.final_handoff_package_zip_valid is False
        else "unknown"
    )
    return (
        f"package={run.package_status or '-'}:{run.package_blocking_issues}; "
        f"scorecard={run.scorecard_status or '-'}:{run.scorecard_blocking_issues}; "
        f"integrity={run.run_integrity_status or '-'}:{run.run_integrity_blocking_issues}; "
        f"zip={zip_state}"
    )


def _capability(
    capability_id: str,
    category: str,
    status: str,
    requirement: str,
    evidence: list[str],
    gaps: list[str],
    next_actions: list[str],
    target_artifacts: list[str],
) -> PerfectAgentCapability:
    return PerfectAgentCapability(
        capability_id=capability_id,
        category=category,
        status=status,
        score={"ready": 1.0, "review_required": 0.5, "block": 0.0}.get(status, 0.0),
        requirement=requirement,
        evidence=evidence,
        gaps=gaps,
        next_actions=next_actions,
        target_artifacts=target_artifacts,
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix.lower() in {".toml", ".tml"}:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        else:
            return {}
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _manifest_role(path: Path, data: dict[str, Any]) -> str:
    role = str(data.get("role") or "").strip().lower()
    if role:
        return role
    for value in [path.parent.name, path.stem]:
        lowered = value.lower()
        for candidate in _ROLES:
            if candidate in lowered:
                return candidate
    return ""


def _manifest_group(path: Path, role: str) -> str:
    if role in _ROLES and path.parent.name.lower() == role:
        return str(path.parent.parent)
    return str(path.parent)


def _command_signature(data: dict[str, Any]) -> str:
    output_values = {str(data.get("metrics_path") or "").strip(), str(data.get("submission_path") or "").strip()}
    expected = data.get("expected_artifacts")
    if isinstance(expected, list):
        output_values.update(str(item).strip() for item in expected if str(item).strip())
    output_values.discard("")
    normalized: list[str] = []
    for token in data.get("command", []) if isinstance(data.get("command"), list) else []:
        value = str(token).strip()
        normalized.append("<output>" if value in output_values else value)
    return " ".join(normalized)


def _command_option(data: dict[str, Any], name: str) -> str:
    command = data.get("command") if isinstance(data.get("command"), list) else []
    values = [str(item).strip() for item in command]
    try:
        index = values.index(name)
    except ValueError:
        return ""
    return values[index + 1] if index + 1 < len(values) else ""


def _public_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org"}:
        return False
    if host.endswith(".local"):
        return False
    return True


def _doi_or_public_url(value: str) -> bool:
    return bool(_citation_locator(value))


def _project_relative_label(project: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project.resolve()))
    except (OSError, ValueError):
        return "<external>"


def _ordered(source: str, before: str, after: str) -> bool:
    before_index = source.find(before)
    after_index = source.find(after)
    return before_index >= 0 and after_index >= 0 and before_index < after_index


def _citation_locator(value: str) -> str:
    stripped = value.strip()
    if _public_url(stripped):
        return stripped
    match = re.search(r"\b10\.\d{4,9}/\S+", stripped, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _limit_label(limit: int) -> str:
    return "all" if limit <= 0 else str(limit)
