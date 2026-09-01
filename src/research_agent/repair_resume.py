from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import shutil

from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json
from .config import AgentConfig
from .seed_paper_intake import build_seed_paper_suggestion_report, seed_role_repair_queries


REPAIR_RESUME_PLAN_JSON = "12-repair-resume-plan.json"
REPAIR_RESUME_PLAN_MD = "12-repair-resume-plan.md"


RERUN_ORDER = [
    "literature_review",
    "literature_context",
    "ideation",
    "experiment_plan",
    "experiments",
    "analysis",
    "paper_revision_plan",
    "paper_rewrite",
    "final_readiness",
    "submission_package",
    "checkpoint",
]

BENCHMARK_REPAIR_CATEGORIES = {
    "benchmark_readiness",
    "benchmark_result_schema",
    "benchmark_evidence",
}

EXECUTION_REPAIR_CATEGORIES = {
    *BENCHMARK_REPAIR_CATEGORIES,
    "execution_safety",
}

DOCTOR_REPAIR_CATEGORY_BY_ID = {
    "paper_grade_literature": "paper_grade_literature",
    "benchmark_evidence": "benchmark_evidence",
    "benchmark_evidence_metadata": "benchmark_evidence",
    "benchmark_adapter": "benchmark_readiness",
    "negative_or_neutral_boundary": "claim_boundary",
    "claim_consistency": "claim_consistency",
    "submission_package": "submission_package",
    "research_scorecard": "research_scorecard",
    "run_integrity": "run_integrity",
    "final_handoff": "final_handoff",
    "repair_queue_blockers": "repair_queue",
    "missing_candidate_artifacts": "missing_candidate_artifacts",
    "gold_contract": "gold_contract",
}

PAPER_GRADE_CONFIG_INT_FIELDS = [
    "min_literature_sources",
    "min_successful_literature_sources",
    "min_seed_papers",
    "min_doi_url_seed_papers",
    "min_curated_seed_roles",
    "min_benchmark_roles",
    "min_execution_repeats",
]

RELEASE_FIELD_TO_CONFIG_KEY = {
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

RELEASE_FIELD_BY_CHECK_ITEM = {
    "代码仓库 URL": "release_code_repository_url",
    "代码归档 DOI": "release_code_archive_doi",
    "许可证": "release_code_license",
    "代码版本或 commit": "release_code_version",
    "数据访问说明": "release_data_access_statement",
    "数据归档 DOI": "release_data_archive_doi",
    "环境归档": "release_environment_url",
    "发布备注": "release_notes",
}

DEFAULT_RELEASE_REQUIRED_FIELDS = [
    "release_code_repository_url",
    "release_code_archive_doi",
    "release_code_license",
    "release_code_version",
    "release_data_access_statement",
    "release_environment_url",
]

DEFAULT_RELEASE_RECOMMENDED_FIELDS = [
    "release_data_archive_doi",
    "release_notes",
]

ARTIFACT_PATTERNS_BY_RERUN_FROM: dict[str, list[str]] = {
    "literature_review": [
        "01-literature*",
        "01-seed-paper-intake.*",
        "01-fulltext-corpus.*",
        "01-context.*",
        "01-review-gate.md",
        "01-citation-audit.*",
        "01-review-feedback.*",
        "01-review-revision-plan.*",
        "01-review-constraints.*",
        "01-references.*",
        "approval.json",
    ],
    "literature_context": [
        "01-context.*",
        "01-review-gate.md",
        "01-citation-audit.*",
        "01-review-feedback.*",
        "01-review-revision-plan.*",
        "01-review-constraints.*",
        "01-references.*",
        "approval.json",
    ],
    "ideation": ["02-*"],
    "experiment_plan": ["03-*"],
    "experiments": [
        "03-execution-approval.*",
        "04-*",
    ],
    "analysis": ["04-claim-boundary-preflight.*", "05-*", "06-*", "07-paper-review.*"],
    "paper_revision_plan": [
        "07-paper-review-calibration.*",
        "08-*",
    ],
    "paper_rewrite": ["09-*"],
    "final_readiness": ["10-*"],
    "submission_package": [
        "11-*",
        "12-next-iteration-plan.*",
        "12-repair-queue.*",
        "13-*",
        "14-*",
    ],
    "checkpoint": [
        "12-repair-queue.*",
        "12-repair-resolution-audit.*",
        "13-llm-trace-audit.*",
        "13-run-economics-audit.*",
        "13-agent-observability-audit.*",
        "13-open-source-compliance.*",
        "13-agent-stage-contract.*",
        "13-agent-trajectory.*",
        "13-research-scorecard.*",
        "14-run-integrity-audit.*",
        "14-final-handoff.*",
    ],
}

DIRS_BY_RERUN_FROM: dict[str, list[str]] = {
    "experiment_plan": ["experiments", "submission-package"],
    "experiments": ["experiments", "submission-package"],
    "analysis": ["submission-package"],
    "paper_revision_plan": ["submission-package"],
    "paper_rewrite": ["submission-package"],
    "final_readiness": ["submission-package"],
    "submission_package": ["submission-package"],
}


def write_repair_resume_plan_artifacts(
    run_dir: Path,
    apply: bool = False,
    doctor_report_path: Path | None = None,
    gold_verification_report_path: Path | None = None,
) -> dict[str, Any]:
    report = prepare_repair_resume(run_dir, apply=apply, doctor_report_path=doctor_report_path, gold_verification_report_path=gold_verification_report_path)
    write_json(run_dir / REPAIR_RESUME_PLAN_JSON, report)
    write_text(run_dir / REPAIR_RESUME_PLAN_MD, render_repair_resume_plan_markdown(report))
    return report


def prepare_repair_resume(
    run_dir: Path,
    apply: bool = False,
    doctor_report_path: Path | None = None,
    gold_verification_report_path: Path | None = None,
) -> dict[str, Any]:
    report = build_repair_resume_plan(run_dir, doctor_report_path=doctor_report_path, gold_verification_report_path=gold_verification_report_path)
    if apply and report.get("can_resume") is True:
        removed_files, removed_dirs = _remove_selected(run_dir, report)
        report = {
            **report,
            "applied": True,
            "applied_at": _utc_now(),
            "removed_artifacts": removed_files,
            "removed_directories": removed_dirs,
        }
    else:
        report = {**report, "applied": False, "removed_artifacts": [], "removed_directories": []}
    write_json(run_dir / REPAIR_RESUME_PLAN_JSON, report)
    write_text(run_dir / REPAIR_RESUME_PLAN_MD, render_repair_resume_plan_markdown(report))
    return report


def build_repair_resume_plan(
    run_dir: Path,
    doctor_report_path: Path | None = None,
    gold_verification_report_path: Path | None = None,
) -> dict[str, Any]:
    queue = _read_json(run_dir / "12-repair-queue.json")
    state = _read_json(run_dir / "state.json")
    topic = str(queue.get("topic") or state.get("topic") or run_dir.name)
    items = [item for item in queue.get("items", []) if isinstance(item, dict)]
    active_items = [item for item in items if str(item.get("status") or "open") == "open" and str(item.get("severity") or "") in {"block", "high", "medium"}]
    doctor_repair_items = _doctor_repair_items_from_path(doctor_report_path)
    gold_verification_repair_items = _gold_verification_repair_items_from_path(gold_verification_report_path)
    repair_items = [*active_items, *doctor_repair_items, *gold_verification_repair_items]
    if not queue and not doctor_repair_items and not gold_verification_repair_items:
        return _report(topic, "missing_queue", False, "", [], [], [], "12-repair-queue.json 缺失，无法自动选择修复 checkpoint。")
    if not repair_items:
        return _report(topic, "nothing_to_repair", False, "", [], [], [], "修复队列没有 open 的 block/high/medium 任务。")
    rerun_from = _earliest_rerun_from(repair_items)
    patterns = _patterns_from(rerun_from)
    dirs = _dirs_from(rerun_from)
    existing_files = _matching_files(run_dir, patterns)
    existing_dirs = [name for name in dirs if (run_dir / name).exists() and (run_dir / name).is_dir()]
    retrieval_repair_tasks = _retrieval_repair_tasks(run_dir, topic) if rerun_from == "literature_review" else []
    recommended_seed_papers = _recommended_seed_papers(run_dir, topic) if rerun_from == "literature_review" else []
    recommended_config = _recommended_literature_config(run_dir) if rerun_from == "literature_review" else {}
    if rerun_from == "literature_review" and not retrieval_repair_tasks and not recommended_seed_papers and not recommended_config:
        retrieval_repair_tasks = _fallback_literature_repair_tasks(topic, repair_items)
    if (retrieval_repair_tasks or recommended_seed_papers) and not recommended_config:
        recommended_config = _default_repair_literature_config()
    recommended_execution_config = _recommended_execution_config(run_dir, repair_items, rerun_from)
    recommended_paper_grade_config = _recommended_paper_grade_config(run_dir, repair_items, recommended_config, recommended_execution_config)
    recommended_release_config = _recommended_release_config(run_dir, repair_items)
    manager_actions = _experiment_manager_resume_actions(run_dir)
    repair_context = _repair_context(run_dir, repair_items)
    plan_sources = _repair_plan_sources(queue, doctor_repair_items, gold_verification_repair_items)
    doctor_report_arg = f" --gold-run-doctor-report {doctor_report_path}" if doctor_report_path is not None else ""
    gold_verification_report_arg = f" --gold-run-verification-report {gold_verification_report_path}" if gold_verification_report_path is not None else ""
    report_args = f"{doctor_report_arg}{gold_verification_report_arg}"
    apply_command = f"PYTHONPATH=src python3 -m research_agent repair-resume {run_dir} --apply{report_args}"
    preview_command = f"PYTHONPATH=src python3 -m research_agent repair-resume {run_dir} --dry-run{report_args}"
    return {
        "schema_version": 1,
        "topic": topic,
        "status": "ready_to_resume_repair",
        "can_resume": True,
        "queue_status": str(queue.get("status") or "missing_queue"),
        "repair_plan_sources": plan_sources,
        "doctor_report_path": str(doctor_report_path) if doctor_report_path is not None else "",
        "gold_verification_report_path": str(gold_verification_report_path) if gold_verification_report_path is not None else "",
        "rerun_from": rerun_from,
        "repair_items": [
            {
                "task_id": str(item.get("task_id") or ""),
                "severity": str(item.get("severity") or ""),
                "category": str(item.get("category") or ""),
                "source_artifact": str(item.get("source_artifact") or ""),
                "action": str(item.get("action") or ""),
            }
            for item in repair_items
        ],
        "candidate_patterns": patterns,
        "candidate_directories": dirs,
        "artifacts_to_remove": existing_files,
        "directories_to_remove": existing_dirs,
        "retrieval_repair_tasks": retrieval_repair_tasks,
        "recommended_config": recommended_config,
        "recommended_execution_config": recommended_execution_config,
        "recommended_paper_grade_config": recommended_paper_grade_config,
        "recommended_release_config": recommended_release_config,
        "experiment_manager_resume_actions": manager_actions,
        "recommended_seed_papers": recommended_seed_papers,
        "repair_context": repair_context,
        "review_reapproval_required": rerun_from in {"literature_review", "literature_context"},
        "execution_reapproval_required": _rerun_index(rerun_from) <= _rerun_index("experiments"),
        "recommended_actions": _recommended_actions(rerun_from, manager_actions),
        "commands": [
            apply_command,
            preview_command,
            f"PYTHONPATH=src python3 -m research_agent resume {run_dir}",
        ],
        "stop_conditions": [
            "12-repair-queue.json 重新生成为 pass 或只剩已接受的 high/medium 待办。",
            "13-research-scorecard.md 不再因 repair queue 进入 blocked。",
            "14-run-integrity-audit.md 无 required artifact 阻断。",
        ],
        "applied": False,
        "applied_at": None,
        "removed_artifacts": [],
        "removed_directories": [],
    }


def render_repair_resume_plan_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 修复恢复计划：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 可恢复：{'是' if report.get('can_resume') else '否'}",
        f"- 队列状态：{report.get('queue_status') or '-'}",
        f"- 计划来源：{', '.join(_string_list(report.get('repair_plan_sources'))) or '-'}",
        f"- 重跑入口：{report.get('rerun_from') or '-'}",
        f"- 已应用：{'是' if report.get('applied') else '否'}",
        f"- 文献重新批准：{'需要' if report.get('review_reapproval_required') else '不需要'}",
        f"- 执行重新批准：{'需要' if report.get('execution_reapproval_required') else '不需要'}",
        "",
    ]
    if report.get("reason"):
        lines.extend(["## 原因", f"- {report.get('reason')}", ""])
    lines.extend(["## 修复任务", "| ID | 严重级别 | 类别 | 来源 | 动作 |", "| --- | --- | --- | --- | --- |"])
    items = report.get("repair_items") if isinstance(report.get("repair_items"), list) else []
    if items:
        for item in items:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("task_id") or "")),
                            _cell(str(item.get("severity") or "")),
                            _cell(str(item.get("category") or "")),
                            _cell(str(item.get("source_artifact") or "")),
                            _cell(str(item.get("action") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | - | - | - | - |")
    retrieval_tasks = report.get("retrieval_repair_tasks") if isinstance(report.get("retrieval_repair_tasks"), list) else []
    lines.extend(["", "## 文献检索修复任务", "| ID | 优先级 | Owner | Query | 动作 |", "| --- | ---: | --- | --- | --- |"])
    if retrieval_tasks:
        for item in retrieval_tasks:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("task_id") or "")),
                            str(item.get("priority") or ""),
                            _cell(str(item.get("owner") or "")),
                            "`" + _cell(str(item.get("query") or "")) + "`",
                            _cell(str(item.get("action") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | - | - | - | - |")
    recommended_config = report.get("recommended_config") if isinstance(report.get("recommended_config"), dict) else {}
    if recommended_config:
        lines.extend(
            [
                "",
                "## 推荐下次文献配置",
                f"- literature_provider：`{recommended_config.get('literature_provider') or '-'}`",
                f"- sources：`{', '.join(recommended_config.get('sources') or []) or '-'}`",
                f"- max_papers：`{recommended_config.get('max_papers') or '-'}`",
                f"- max_search_queries：`{recommended_config.get('max_search_queries') or '-'}`",
                f"- seed_papers_min：`{recommended_config.get('seed_papers_min') or '-'}`",
            ]
        )
    recommended_paper_grade_config = report.get("recommended_paper_grade_config") if isinstance(report.get("recommended_paper_grade_config"), dict) else {}
    if recommended_paper_grade_config:
        thresholds = [
            f"{key}={recommended_paper_grade_config.get(key)}"
            for key in PAPER_GRADE_CONFIG_INT_FIELDS
            if _safe_int(recommended_paper_grade_config.get(key))
        ]
        reasons = _string_list(recommended_paper_grade_config.get("reasons"))
        lines.extend(
            [
                "",
                "## 推荐下次论文级门槛",
                f"- enabled：`{recommended_paper_grade_config.get('enabled') is True}`",
                f"- thresholds：`{', '.join(thresholds) or '-'}`",
                f"- reasons：`{', '.join(reasons) or '-'}`",
            ]
        )
    recommended_seed_papers = _string_list(report.get("recommended_seed_papers"))
    if recommended_seed_papers:
        lines.extend(["", "## 推荐下次人工 Seed Papers"])
        lines.extend(f"- `{item}`" for item in recommended_seed_papers)
    recommended_release_config = report.get("recommended_release_config") if isinstance(report.get("recommended_release_config"), dict) else {}
    if recommended_release_config:
        required = _string_list(recommended_release_config.get("required_fields"))
        recommended = _string_list(recommended_release_config.get("recommended_fields"))
        cli_args = _string_list(recommended_release_config.get("cli_args"))
        lines.extend(
            [
                "",
                "## 推荐下次发布配置",
                f"- required_fields：`{', '.join(required) or '-'}`",
                f"- recommended_fields：`{', '.join(recommended) or '-'}`",
                f"- cli_args：`{', '.join(cli_args) or '-'}`",
            ]
        )
    recommended_execution_config = report.get("recommended_execution_config") if isinstance(report.get("recommended_execution_config"), dict) else {}
    if recommended_execution_config:
        manifests = _string_list(recommended_execution_config.get("benchmark_manifest_paths"))
        paper_grade_status = str(recommended_execution_config.get("benchmark_paper_grade_status") or "")
        paper_grade_issues = _string_list(recommended_execution_config.get("benchmark_paper_grade_issues"))
        repair_suggestions = recommended_execution_config.get("benchmark_manifest_repair_suggestions") if isinstance(recommended_execution_config.get("benchmark_manifest_repair_suggestions"), list) else []
        scaffolds = recommended_execution_config.get("benchmark_manifest_scaffolds") if isinstance(recommended_execution_config.get("benchmark_manifest_scaffolds"), list) else []
        lines.extend(
            [
                "",
                "## 推荐下次执行配置",
                f"- execution_mode：`{recommended_execution_config.get('execution_mode') or '-'}`",
                f"- allowed_commands：`{', '.join(_string_list(recommended_execution_config.get('allowed_commands'))) or '-'}`",
                f"- execution_repeats：`{recommended_execution_config.get('execution_repeats') or '-'}`",
                f"- timeout_seconds：`{recommended_execution_config.get('timeout_seconds') or '-'}`",
                f"- benchmark_manifest_paths：`{', '.join(manifests) or '-'}`",
                f"- benchmark_paper_grade：`{paper_grade_status or '-'}`，issues={len(paper_grade_issues)}，repair_suggestions={len(repair_suggestions)}",
                f"- benchmark_manifest_scaffolds：`{len(scaffolds)}`",
            ]
        )
        if repair_suggestions:
            lines.extend(["", "### Benchmark Manifest 修复建议", "| 类型 | 目标 | 动作 |", "| --- | --- | --- |"])
            for item in repair_suggestions:
                if isinstance(item, dict):
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _cell(str(item.get("kind") or "")),
                                _cell(str(item.get("target") or item.get("role") or item.get("manifest_path") or "-")),
                                _cell(str(item.get("action") or "")),
                            ]
                        )
                        + " |"
                    )
        if scaffolds:
            lines.extend(["", "### Benchmark Manifest Scaffold"])
            for item in scaffolds:
                if not isinstance(item, dict):
                    continue
                manifest = item.get("manifest") if isinstance(item.get("manifest"), dict) else {}
                lines.extend(
                    [
                        f"- `{item.get('path_hint') or item.get('role') or 'benchmark-manifest.json'}`",
                        "```json",
                        json.dumps(manifest, ensure_ascii=False, indent=2),
                        "```",
                    ]
                )
    manager_actions = report.get("experiment_manager_resume_actions") if isinstance(report.get("experiment_manager_resume_actions"), list) else []
    if manager_actions:
        lines.extend(["", "## Experiment Manager 恢复动作", "| 分支 | 队列状态 | 动作 | 恢复入口 |", "| --- | --- | --- | --- |"])
        for item in manager_actions:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(f"{item.get('branch_id') or ''} {item.get('title') or ''}"),
                        _cell(str(item.get("queue_state") or "")),
                        _cell(str(item.get("action") or "")),
                        _cell(str(item.get("resume_from") or "")),
                    ]
                )
                + " |"
            )
    repair_context = report.get("repair_context") if isinstance(report.get("repair_context"), dict) else {}
    constraints = repair_context.get("constraints") if isinstance(repair_context.get("constraints"), list) else []
    lines.extend(["", "## 供 Agent 重新规划的修复约束"])
    lines.extend(f"- {item}" for item in constraints) if constraints else lines.append("- 无")
    for key, title in [
        ("artifacts_to_remove", "将清理的产物"),
        ("directories_to_remove", "将清理的目录"),
        ("removed_artifacts", "已清理的产物"),
        ("removed_directories", "已清理的目录"),
        ("recommended_actions", "推荐动作"),
        ("commands", "可执行命令"),
        ("stop_conditions", "停止条件"),
    ]:
        values = report.get(key) if isinstance(report.get(key), list) else []
        lines.extend(["", f"## {title}"])
        if values:
            prefix = "- [ ] " if key == "stop_conditions" else "- "
            if key == "commands":
                lines.extend(f"- `{item}`" for item in values)
            else:
                lines.extend(prefix + str(item) for item in values)
        else:
            lines.append("- 无")
    return "\n".join(lines)


def _report(topic: str, status: str, can_resume: bool, rerun_from: str, items: list[dict[str, Any]], patterns: list[str], dirs: list[str], reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "can_resume": can_resume,
        "queue_status": "",
        "repair_plan_sources": [],
        "doctor_report_path": "",
        "gold_verification_report_path": "",
        "rerun_from": rerun_from,
        "repair_items": items,
        "candidate_patterns": patterns,
        "candidate_directories": dirs,
        "artifacts_to_remove": [],
        "directories_to_remove": [],
        "retrieval_repair_tasks": [],
        "recommended_config": {},
        "recommended_execution_config": {},
        "recommended_paper_grade_config": {},
        "recommended_release_config": {},
        "experiment_manager_resume_actions": [],
        "recommended_seed_papers": [],
        "repair_context": {"constraints": [], "prompt_text": ""},
        "review_reapproval_required": False,
        "execution_reapproval_required": False,
        "recommended_actions": [],
        "commands": [],
        "stop_conditions": [],
        "reason": reason,
        "applied": False,
        "applied_at": None,
        "removed_artifacts": [],
        "removed_directories": [],
    }


def _doctor_repair_items_from_path(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    report = _read_json(path)
    return _doctor_repair_items(report)


def _gold_verification_repair_items_from_path(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    report = _read_json(path)
    return _gold_verification_repair_items(report)


def _doctor_repair_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    repair_plan: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict) or check.get("name") != "candidate_gold_run":
            continue
        items = check.get("repair_plan") if isinstance(check.get("repair_plan"), list) else []
        repair_plan = [item for item in items if isinstance(item, dict)]
        break
    converted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in repair_plan:
        item_id = str(item.get("id") or "").strip()
        task_id = f"gold-doctor:{item_id}" if item_id else "gold-doctor:candidate_gold_run"
        if task_id in seen:
            continue
        seen.add(task_id)
        category = DOCTOR_REPAIR_CATEGORY_BY_ID.get(item_id, item_id or "candidate_gold_run")
        converted.append(
            {
                "task_id": task_id,
                "severity": "block",
                "category": category,
                "source_artifact": str(item.get("source_artifact") or "00-gold-run-doctor.json"),
                "action": str(item.get("action") or ""),
                "rerun_from": str(item.get("rerun_from") or "checkpoint"),
                "status": "open",
                "doctor_priority": _safe_int(item.get("priority")),
                "target_artifacts": _string_list(item.get("target_artifacts")),
            }
        )
    converted.sort(key=lambda item: (_rerun_index(str(item.get("rerun_from") or "")), _safe_int(item.get("doctor_priority"))))
    return converted


def _gold_verification_repair_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    repair_plan = report.get("repair_plan") if isinstance(report.get("repair_plan"), list) else []
    converted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in repair_plan:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        task_id = f"gold-verification:{item_id}" if item_id else "gold-verification:gold_contract"
        if task_id in seen:
            continue
        seen.add(task_id)
        category = DOCTOR_REPAIR_CATEGORY_BY_ID.get(item_id, item_id or "gold_contract")
        converted.append(
            {
                "task_id": task_id,
                "severity": "block",
                "category": category,
                "source_artifact": str(item.get("source_artifact") or "15-gold-run-verification.json"),
                "action": str(item.get("action") or ""),
                "rerun_from": str(item.get("rerun_from") or "checkpoint"),
                "status": "open",
                "doctor_priority": _safe_int(item.get("priority")),
                "target_artifacts": _string_list(item.get("target_artifacts")),
            }
        )
    converted.sort(key=lambda item: (_rerun_index(str(item.get("rerun_from") or "")), _safe_int(item.get("doctor_priority"))))
    return converted


def _repair_plan_sources(queue: dict[str, Any], doctor_repair_items: list[dict[str, Any]], gold_verification_repair_items: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    if queue:
        sources.append("12-repair-queue")
    if doctor_repair_items:
        sources.append("gold-run-doctor")
    if gold_verification_repair_items:
        sources.append("gold-run-verification")
    return sources


def _retrieval_repair_tasks(run_dir: Path, topic: str) -> list[dict[str, Any]]:
    feedback = _read_json(run_dir / "01-literature-search-feedback.json")
    tasks = feedback.get("retrieval_repair_tasks") if isinstance(feedback.get("retrieval_repair_tasks"), list) else []
    selected: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("owner") or "")
        query = str(item.get("query") or "").strip()
        if owner not in {"agent", "agent+human"} or not query:
            continue
        selected.append(
            {
                "task_id": str(item.get("task_id") or ""),
                "category": str(item.get("category") or ""),
                "priority": _safe_int(item.get("priority")),
                "owner": owner,
                "action": str(item.get("action") or ""),
                "query": query,
                "source": str(item.get("source") or "01-literature-search-feedback.json"),
                "rationale": str(item.get("rationale") or ""),
            }
        )
    selected.extend(_seed_role_repair_tasks(run_dir, topic))
    selected = _dedupe_tasks(selected)
    selected.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return selected[:6]


def _fallback_literature_repair_tasks(topic: str, active_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries = _fallback_literature_queries(topic)
    if not queries:
        return []
    categories = _dedupe(
        [
            str(item.get("category") or "").strip()
            for item in active_items
            if isinstance(item, dict) and str(item.get("category") or "").strip()
        ]
    )
    category_text = f" active repair categories: {', '.join(categories[:4])}." if categories else ""
    rows: list[dict[str, Any]] = []
    for index, query in enumerate(queries[:6], start=1):
        rows.append(
            {
                "task_id": f"fallback-literature-review-{index:02d}",
                "category": "bounded_rescue_query",
                "priority": 91 - index,
                "owner": "agent+human",
                "action": "执行有边界的补救检索；候选论文必须由人工核验 DOI/URL/来源后才可重新批准文献门。",
                "query": query,
                "source": "repair-resume-fallback",
                "rationale": "历史 run 缺少 search feedback、seed intake 或 seed suggestion，无法复用已有检索修复证据。"
                + category_text,
            }
        )
    return rows


def _fallback_literature_queries(topic: str) -> list[str]:
    clean_topic = " ".join(str(topic or "").replace("_", " ").split())
    if not clean_topic:
        return []
    lower = clean_topic.lower()
    robotics_markers = [
        "机械臂",
        "机械手",
        "机器人",
        "路径规划",
        "运动规划",
        "robot manipulator",
        "manipulator",
        "robot arm",
        "motion planning",
        "path planning",
        "ompl",
    ]
    if any(marker in lower for marker in robotics_markers):
        return [
            "robot manipulator motion planning survey review",
            "OMPL motion planning benchmark robot manipulator",
            "sampling-based motion planning RRT RRT* PRM robot manipulator",
            "recent robot manipulator motion planning learning-based 2024 2025",
        ]
    return [
        f"{clean_topic} survey review",
        f"{clean_topic} benchmark dataset evaluation protocol",
        f"{clean_topic} baseline method comparison",
        f"{clean_topic} recent advances 2024 2025",
    ]


def _recommended_release_config(run_dir: Path, repair_items: list[dict[str, Any]]) -> dict[str, Any]:
    release = _read_json(run_dir / "10-release-metadata.json")
    categories = {str(item.get("category") or "") for item in repair_items if isinstance(item, dict)}
    if not release:
        if categories & {"release", "release_metadata", "code_data_availability"}:
            return _release_config_from_fields(DEFAULT_RELEASE_REQUIRED_FIELDS, DEFAULT_RELEASE_RECOMMENDED_FIELDS)
        return {}
    recommended = release.get("recommended_config") if isinstance(release.get("recommended_config"), dict) else {}
    if recommended and recommended.get("status") != "complete":
        required = _string_list(recommended.get("required_fields"))
        optional = _string_list(recommended.get("recommended_fields"))
        actions = recommended.get("field_actions") if isinstance(recommended.get("field_actions"), dict) else {}
        result = _release_config_from_fields(required, optional)
        result["field_actions"] = _public_release_field_actions(actions, required, optional)
        config_fields = recommended.get("config_fields") if isinstance(recommended.get("config_fields"), dict) else {}
        result["config_fields"] = {
            str(key): str(value or "")
            for key, value in config_fields.items()
            if str(key) in RELEASE_FIELD_TO_CONFIG_KEY.values()
        }
        return result
    required, optional = _release_fields_from_checks(release.get("checks"))
    if required or optional:
        return _release_config_from_fields(required, optional)
    if str(release.get("status") or "") in {"blocked", "needs_release_metadata"}:
        return _release_config_from_fields(DEFAULT_RELEASE_REQUIRED_FIELDS, DEFAULT_RELEASE_RECOMMENDED_FIELDS)
    return {}


def _release_config_from_fields(required_fields: list[str], recommended_fields: list[str]) -> dict[str, Any]:
    required = _dedupe([field for field in required_fields if field in RELEASE_FIELD_TO_CONFIG_KEY])
    optional = _dedupe([field for field in recommended_fields if field in RELEASE_FIELD_TO_CONFIG_KEY and field not in required])
    fields = [*required, *optional]
    if not fields:
        return {}
    return {
        "status": "needs_input",
        "required_fields": required,
        "recommended_fields": optional,
        "cli_args": ["--" + field.replace("_", "-") for field in fields],
        "config_fields": {RELEASE_FIELD_TO_CONFIG_KEY[field]: "" for field in fields},
        "field_actions": {
            field: {
                "metadata_key": RELEASE_FIELD_TO_CONFIG_KEY[field],
                "config_key": f"release.{RELEASE_FIELD_TO_CONFIG_KEY[field]}",
                "cli_arg": "--" + field.replace("_", "-"),
                "recommended_value": "",
                "required": field in required,
            }
            for field in fields
        },
    }


def _public_release_field_actions(actions: dict[str, Any], required_fields: list[str], recommended_fields: list[str]) -> dict[str, dict[str, Any]]:
    allowed = set(required_fields) | set(recommended_fields)
    public: dict[str, dict[str, Any]] = {}
    for field, action in actions.items():
        field_name = str(field)
        if field_name not in allowed or field_name not in RELEASE_FIELD_TO_CONFIG_KEY or not isinstance(action, dict):
            continue
        metadata_key = str(action.get("metadata_key") or RELEASE_FIELD_TO_CONFIG_KEY[field_name])
        if metadata_key not in RELEASE_FIELD_TO_CONFIG_KEY.values():
            metadata_key = RELEASE_FIELD_TO_CONFIG_KEY[field_name]
        public[field_name] = {
            "metadata_key": metadata_key,
            "config_key": f"release.{metadata_key}",
            "cli_arg": str(action.get("cli_arg") or "--" + field_name.replace("_", "-")),
            "recommended_value": str(action.get("recommended_value") or ""),
            "required": field_name in required_fields,
            "action": str(action.get("action") or ""),
        }
    return public


def _release_fields_from_checks(checks: Any) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "")
        if status == "pass":
            continue
        field = RELEASE_FIELD_BY_CHECK_ITEM.get(str(check.get("item") or ""))
        if not field:
            continue
        if status in {"block", "manual_required"}:
            required.append(field)
        else:
            optional.append(field)
    return _dedupe(required), _dedupe(optional)


def apply_repair_resume_recommendations(config: AgentConfig, report: dict[str, Any]) -> AgentConfig:
    if report.get("applied") is not True:
        return config
    rerun_from = str(report.get("rerun_from") or "")
    if rerun_from == "literature_review":
        config = _apply_literature_recommendations(config, report)
    config = _apply_execution_recommendations(config, report)
    config = _apply_release_recommendations(config, report)
    return _apply_paper_grade_recommendations(config, report)


def missing_repair_resume_required_release_values(config: AgentConfig, report: dict[str, Any]) -> list[str]:
    recommended = report.get("recommended_release_config") if isinstance(report.get("recommended_release_config"), dict) else {}
    required = [field for field in _string_list(recommended.get("required_fields")) if field in RELEASE_FIELD_TO_CONFIG_KEY]
    if not required:
        return []
    config_fields = recommended.get("config_fields") if isinstance(recommended.get("config_fields"), dict) else {}
    field_actions = recommended.get("field_actions") if isinstance(recommended.get("field_actions"), dict) else {}
    missing: list[str] = []
    for field in required:
        metadata_key = RELEASE_FIELD_TO_CONFIG_KEY[field]
        action = field_actions.get(field) if isinstance(field_actions.get(field), dict) else {}
        values = [
            getattr(config.release, metadata_key, ""),
            config_fields.get(metadata_key),
            config_fields.get(field),
            action.get("recommended_value"),
        ]
        if not any(str(value or "").strip() for value in values):
            missing.append(field)
    return missing


def _apply_literature_recommendations(config: AgentConfig, report: dict[str, Any]) -> AgentConfig:
    recommended = report.get("recommended_config") if isinstance(report.get("recommended_config"), dict) else {}
    literature = config.literature
    provider = str(recommended.get("literature_provider") or "").strip()
    if literature.provider == "offline" and provider in {"online", "auto"}:
        literature = replace(literature, provider=provider)
    sources = _string_list(recommended.get("sources"))
    if sources:
        literature = replace(literature, sources=_dedupe([*literature.sources, *sources]))
    max_papers = _safe_int(recommended.get("max_papers"))
    if max_papers > literature.max_papers:
        literature = replace(literature, max_papers=max_papers)
    max_search_queries = _safe_int(recommended.get("max_search_queries"))
    if max_search_queries > literature.max_search_queries:
        literature = replace(literature, max_search_queries=max_search_queries)
    repair_queries = [
        str(item.get("query") or "").strip()
        for item in report.get("retrieval_repair_tasks", [])
        if isinstance(item, dict)
        and str(item.get("owner") or "") in {"agent", "agent+human"}
        and str(item.get("query") or "").strip()
    ]
    if repair_queries:
        literature = replace(literature, extra_search_queries=_dedupe([*literature.extra_search_queries, *repair_queries]))
    seed_papers = _string_list(report.get("recommended_seed_papers"))
    if seed_papers:
        literature = replace(literature, seed_papers=_dedupe([*literature.seed_papers, *seed_papers]))
    return replace(config, literature=literature) if literature is not config.literature else config


def _apply_execution_recommendations(config: AgentConfig, report: dict[str, Any]) -> AgentConfig:
    recommended = report.get("recommended_execution_config") if isinstance(report.get("recommended_execution_config"), dict) else {}
    if not recommended:
        return config
    execution = config.execution
    mode = str(recommended.get("execution_mode") or "").strip()
    if mode in {"local", "benchmark"} and (execution.mode == "simulated" or mode == "benchmark" and execution.mode != "benchmark"):
        execution = replace(execution, mode=mode)
    allowed_commands = _safe_command_names(recommended.get("allowed_commands"))
    if allowed_commands:
        execution = replace(execution, allowed_commands=_dedupe([*execution.allowed_commands, *allowed_commands]))
    repeats = _safe_int(recommended.get("execution_repeats"))
    if repeats > execution.repeats:
        execution = replace(execution, repeats=repeats)
    timeout_seconds = _safe_int(recommended.get("timeout_seconds"))
    if timeout_seconds > execution.timeout_seconds:
        execution = replace(execution, timeout_seconds=timeout_seconds)
    manifests = _string_list(recommended.get("benchmark_manifest_paths"))
    if manifests:
        execution = replace(execution, benchmark_manifest_paths=_dedupe([*execution.benchmark_manifest_paths, *manifests]))
    return replace(config, execution=execution) if execution is not config.execution else config


def _apply_paper_grade_recommendations(config: AgentConfig, report: dict[str, Any]) -> AgentConfig:
    recommended = report.get("recommended_paper_grade_config") if isinstance(report.get("recommended_paper_grade_config"), dict) else {}
    if recommended.get("enabled") is not True:
        return config
    paper_grade = replace(config.paper_grade, enabled=True) if not config.paper_grade.enabled else config.paper_grade
    for key in PAPER_GRADE_CONFIG_INT_FIELDS:
        value = _safe_int(recommended.get(key))
        current = _safe_int(getattr(paper_grade, key, 0))
        if value > current:
            paper_grade = replace(paper_grade, **{key: value})
    return replace(config, paper_grade=paper_grade) if paper_grade is not config.paper_grade else config


def _apply_release_recommendations(config: AgentConfig, report: dict[str, Any]) -> AgentConfig:
    recommended = report.get("recommended_release_config") if isinstance(report.get("recommended_release_config"), dict) else {}
    config_fields = recommended.get("config_fields") if isinstance(recommended.get("config_fields"), dict) else {}
    field_actions = recommended.get("field_actions") if isinstance(recommended.get("field_actions"), dict) else {}
    updates: dict[str, str] = {}
    for key, raw_value in config_fields.items():
        metadata_key = str(key)
        value = str(raw_value or "").strip()
        if metadata_key in RELEASE_FIELD_TO_CONFIG_KEY.values() and value:
            updates[metadata_key] = value
    for action in field_actions.values():
        if not isinstance(action, dict):
            continue
        metadata_key = str(action.get("metadata_key") or "")
        value = str(action.get("recommended_value") or "").strip()
        if metadata_key in RELEASE_FIELD_TO_CONFIG_KEY.values() and value:
            updates[metadata_key] = value
    if not updates:
        return config
    release = config.release
    applied: dict[str, str] = {}
    for key, value in updates.items():
        current = str(getattr(release, key, "") or "").strip()
        if not current:
            applied[key] = value
    if not applied:
        return config
    return replace(config, release=replace(release, **applied))


def _seed_role_repair_tasks(run_dir: Path, topic: str) -> list[dict[str, Any]]:
    seed = _read_json(run_dir / "01-seed-paper-intake.json")
    source = "01-seed-paper-intake.json"
    rationale_prefix = "curated seed"
    if str(seed.get("role_coverage_status") or "") == "review_required":
        missing_roles = _string_list(seed.get("missing_curated_seed_roles"))
    else:
        suggestion = build_seed_paper_suggestion_report(topic, run_dir, seed if seed else None)
        if not suggestion.get("suggested_seed_count"):
            return []
        missing_roles = _string_list(suggestion.get("missing_roles"))
        rationale_prefix = f"候选 seed 已补 {suggestion.get('suggested_seed_count', 0)} 条后仍"
    if not missing_roles:
        return []
    rows: list[dict[str, Any]] = []
    for role in missing_roles:
        queries = seed_role_repair_queries(topic, [role])
        if not queries:
            continue
        rows.append(
            {
                "task_id": f"seed-role-{role.replace('_', '-')}",
                "category": "seed_role_coverage",
                "priority": 93,
                "owner": "agent+human",
                "action": "执行角色补检索；找到真实核心论文后由人工把 DOI/URL 补入 seed_papers。",
                "query": queries[0],
                "source": source,
                "rationale": f"{rationale_prefix}缺少 {role} 角色覆盖。",
            }
        )
    return rows


def _dedupe_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    seen_ids: set[str] = set()
    for item in tasks:
        query = str(item.get("query") or "").strip()
        task_id = str(item.get("task_id") or "").strip()
        query_key = query.lower()
        id_key = task_id.lower()
        if (query_key and query_key in seen_queries) or (id_key and id_key in seen_ids):
            continue
        if query_key:
            seen_queries.add(query_key)
        if id_key:
            seen_ids.add(id_key)
        result.append(item)
    return result


def _recommended_seed_papers(run_dir: Path, topic: str) -> list[str]:
    suggestion = build_seed_paper_suggestion_report(topic, run_dir)
    entries = _string_list(suggestion.get("suggested_seed_entries")) if suggestion.get("suggested_seed_count") else []
    if entries:
        return entries
    gate = _read_json(run_dir / "01-literature-gate-decision.json")
    return _dedupe(
        [
            entry
            for item in _paper_grade_literature_repair_suggestions(gate)
            for entry in _string_list(item.get("suggested_seed_entries"))[:6]
        ]
    )


def _default_repair_literature_config() -> dict[str, Any]:
    return {
        "literature_provider": "online",
        "sources": ["semantic_scholar", "openalex", "arxiv", "crossref"],
        "max_papers": 12,
        "max_search_queries": 6,
    }


def _recommended_literature_config(run_dir: Path) -> dict[str, Any]:
    feedback = _read_json(run_dir / "01-literature-search-feedback.json")
    config = feedback.get("next_run_config") if isinstance(feedback.get("next_run_config"), dict) else {}
    result: dict[str, Any] = {}
    provider = str(config.get("literature_provider") or "").strip()
    if provider in {"offline", "online", "auto"}:
        result["literature_provider"] = provider
    sources = _string_list(config.get("sources"))
    if sources:
        result["sources"] = sources
    max_papers = _safe_int(config.get("max_papers"))
    if max_papers:
        result["max_papers"] = max_papers
    max_search_queries = _safe_int(config.get("max_search_queries"))
    if max_search_queries:
        result["max_search_queries"] = max_search_queries
    gate = _read_json(run_dir / "01-literature-gate-decision.json")
    for suggestion in _paper_grade_literature_repair_suggestions(gate):
        repair_config = suggestion.get("recommended_config") if isinstance(suggestion.get("recommended_config"), dict) else {}
        result = _merge_literature_repair_config(result, repair_config)
    return result


def _paper_grade_literature_repair_suggestions(gate: dict[str, Any]) -> list[dict[str, Any]]:
    paper_grade = gate.get("paper_grade_literature") if isinstance(gate.get("paper_grade_literature"), dict) else {}
    suggestions = paper_grade.get("repair_suggestions") if isinstance(paper_grade.get("repair_suggestions"), list) else []
    return [item for item in suggestions if isinstance(item, dict)]


def _merge_literature_repair_config(current: dict[str, Any], repair: dict[str, Any]) -> dict[str, Any]:
    result = dict(current)
    provider = str(repair.get("literature_provider") or "").strip()
    if provider in {"online", "auto"} and result.get("literature_provider") not in {"online", "auto"}:
        result["literature_provider"] = provider
    sources = _string_list(repair.get("sources"))
    if sources:
        result["sources"] = _dedupe([*_string_list(result.get("sources")), *sources])
    for key in ["max_papers", "max_search_queries", "seed_papers_min"]:
        value = _safe_int(repair.get(key))
        if value > _safe_int(result.get(key)):
            result[key] = value
    return result


def _recommended_execution_config(run_dir: Path, items: list[dict[str, Any]], rerun_from: str) -> dict[str, Any]:
    if not _has_execution_repair(items):
        return {}
    if _rerun_index(rerun_from) > _rerun_index("experiments"):
        return {}
    benchmark_repair = _has_benchmark_repair(items)
    run_config = _read_json(run_dir / "run-config.json")
    execution = run_config.get("execution") if isinstance(run_config.get("execution"), dict) else {}
    paper_grade = run_config.get("paper_grade") if isinstance(run_config.get("paper_grade"), dict) else {}
    min_execution_repeats = max(3, _safe_int(paper_grade.get("min_execution_repeats"))) if _safe_bool(paper_grade.get("enabled")) else 3
    safety = _read_json(run_dir / "03-execution-safety-audit.json")
    adapters = _read_json(run_dir / "03-benchmark-adapters.json")
    readiness = _read_json(run_dir / "03-benchmark-readiness.json")

    mode = "benchmark" if benchmark_repair else _first_string(
        safety.get("execution_mode"),
        execution.get("mode"),
    )
    result: dict[str, Any] = {}
    if mode in {"local", "benchmark"}:
        result["execution_mode"] = mode

    allowed_commands = _dedupe(
        [
            *_safe_command_names(execution.get("allowed_commands")),
            *_safe_command_names(safety.get("allowed_commands")),
        ]
    )
    if allowed_commands:
        result["allowed_commands"] = allowed_commands

    repeats = max(_safe_int(execution.get("repeats")), _safe_int(safety.get("repeats")))
    if benchmark_repair:
        repeats = max(repeats, min_execution_repeats)
    if repeats:
        result["execution_repeats"] = repeats

    timeout_seconds = max(_safe_int(execution.get("timeout_seconds")), _safe_int(safety.get("timeout_seconds")))
    if timeout_seconds:
        result["timeout_seconds"] = timeout_seconds

    manifests = _dedupe(
        [
            *_string_list(execution.get("benchmark_manifest_paths")),
            *_string_list(adapters.get("manifest_paths")),
            *_string_list(_nested_dict(readiness, "adapter_report").get("manifest_paths")),
            *_string_list(_nested_dict(safety, "benchmark_adapter_audit").get("manifest_paths")),
        ]
    )
    if manifests:
        result["benchmark_manifest_paths"] = manifests
    if benchmark_repair:
        adapter_reports = [adapters, _nested_dict(readiness, "adapter_report"), _nested_dict(safety, "benchmark_adapter_audit")]
        paper_grade_status = _first_string(*(item.get("paper_grade_status") for item in adapter_reports if item))
        paper_grade_issues = _first_list(*(item.get("paper_grade_issues") for item in adapter_reports if item))
        repair_suggestions = _first_list(*(item.get("paper_grade_repair_suggestions") for item in adapter_reports if item))
        if paper_grade_status:
            result["benchmark_paper_grade_status"] = paper_grade_status
        if paper_grade_issues:
            result["benchmark_paper_grade_issues"] = paper_grade_issues
        if repair_suggestions:
            result["benchmark_manifest_repair_suggestions"] = repair_suggestions
            scaffolds = _benchmark_manifest_scaffolds(repair_suggestions, min_execution_repeats=min_execution_repeats)
            if scaffolds:
                result["benchmark_manifest_scaffolds"] = scaffolds
    return result


def _recommended_paper_grade_config(
    run_dir: Path,
    items: list[dict[str, Any]],
    recommended_literature: dict[str, Any],
    recommended_execution: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    reasons: list[str] = []
    run_config = _read_json(run_dir / "run-config.json")
    existing = run_config.get("paper_grade") if isinstance(run_config.get("paper_grade"), dict) else {}
    if _safe_bool(existing.get("enabled")):
        reasons.append("run_config.paper_grade.enabled")
        result["enabled"] = True
        for key in PAPER_GRADE_CONFIG_INT_FIELDS:
            value = _safe_int(existing.get(key))
            if value:
                result[key] = value
    gate = _read_json(run_dir / "01-literature-gate-decision.json")
    paper_grade_literature = gate.get("paper_grade_literature") if isinstance(gate.get("paper_grade_literature"), dict) else {}
    if _paper_grade_literature_repair_suggestions(gate) or _paper_grade_status_requires_repair(paper_grade_literature.get("status")):
        reasons.append("paper_grade_literature_gate")
        result["enabled"] = True
    if _safe_int(recommended_literature.get("seed_papers_min")):
        reasons.append("paper_grade_seed_repair")
        result["enabled"] = True
        seed_min = _safe_int(recommended_literature.get("seed_papers_min"))
        if seed_min:
            result["min_seed_papers"] = max(_safe_int(result.get("min_seed_papers")), seed_min)
            result["min_doi_url_seed_papers"] = max(_safe_int(result.get("min_doi_url_seed_papers")), seed_min)
    if _benchmark_paper_grade_repair_required(run_dir, recommended_execution):
        reasons.append("paper_grade_benchmark_gate")
        result["enabled"] = True
    repeats = _safe_int(recommended_execution.get("execution_repeats"))
    if repeats:
        result["min_execution_repeats"] = max(_safe_int(result.get("min_execution_repeats")), min(repeats, 3) if repeats < 3 else repeats)
    if _repair_items_explicitly_reference_paper_grade(items):
        reasons.append("repair_queue.paper_grade")
        result["enabled"] = True
    if result.get("enabled") is not True:
        return {}
    result["reasons"] = _dedupe(reasons)
    result["trigger_count"] = len(result["reasons"])
    return result


def _paper_grade_status_requires_repair(value: Any) -> bool:
    status = str(value or "").strip()
    return bool(status and status not in {"pass", "ready"})


def _benchmark_paper_grade_repair_required(run_dir: Path, recommended_execution: dict[str, Any]) -> bool:
    if _paper_grade_status_requires_repair(recommended_execution.get("benchmark_paper_grade_status")):
        return True
    if _string_list(recommended_execution.get("benchmark_paper_grade_issues")):
        return True
    if isinstance(recommended_execution.get("benchmark_manifest_repair_suggestions"), list) and recommended_execution.get("benchmark_manifest_repair_suggestions"):
        return True
    for path, container_key in [
        ("03-benchmark-adapters.json", ""),
        ("03-benchmark-readiness.json", "adapter_report"),
        ("03-execution-safety-audit.json", "benchmark_adapter_audit"),
        ("04-benchmark-evidence-audit.json", ""),
    ]:
        data = _read_json(run_dir / path)
        report = _nested_dict(data, container_key) if container_key else data
        if _paper_grade_status_requires_repair(report.get("paper_grade_status")):
            return True
        if _paper_grade_status_requires_repair(report.get("adapter_paper_grade_status")):
            return True
        if _string_list(report.get("paper_grade_issues")) or _string_list(report.get("adapter_paper_grade_issues")):
            return True
    return False


def _repair_items_explicitly_reference_paper_grade(items: list[dict[str, Any]]) -> bool:
    for item in items:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            [
                str(item.get("task_id") or ""),
                str(item.get("category") or ""),
                str(item.get("source_artifact") or ""),
                str(item.get("action") or ""),
            ]
        ).lower()
        if "paper-grade" in text or "paper_grade" in text or "论文级" in text:
            return True
    return False


def _benchmark_manifest_scaffolds(repair_suggestions: list[Any], *, min_execution_repeats: int = 3) -> list[dict[str, Any]]:
    scaffolds: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item in repair_suggestions:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind != "missing_manifest_role":
            continue
        role = str(item.get("role") or "").strip()
        if role not in {"candidate", "baseline", "ablation"}:
            continue
        path_hint = str(item.get("target_path_hint") or f"benchmarks/{role}-manifest.json").strip()
        if path_hint in seen_paths:
            continue
        seen_paths.add(path_hint)
        template = item.get("manifest_template") if isinstance(item.get("manifest_template"), dict) else {}
        scaffolds.append(
            {
                "role": role,
                "path_hint": path_hint,
                "source": kind,
                "manifest": _manifest_scaffold(role, template, min_execution_repeats=min_execution_repeats),
            }
        )
    return scaffolds


def _manifest_scaffold(role: str, template: dict[str, Any], *, min_execution_repeats: int = 3) -> dict[str, Any]:
    result = dict(template)
    result["role"] = role
    min_repeats_default = max(1, min_execution_repeats)
    defaults: dict[str, Any] = {
        "name": f"TODO {role} benchmark adapter",
        "command": ["python3", f"run_{role}_benchmark.py", "--metrics", f"{role}_metrics.json"],
        "metrics_path": f"{role}_metrics.json",
        "source_files": [f"run_{role}_benchmark.py"],
        "expected_artifacts": [f"{role}_metrics.json"],
        "benchmark_kind": "external",
        "benchmark_url": "TODO official benchmark URL",
        "dataset_url": "TODO official dataset/task URL",
        "dataset_version": "TODO dataset/benchmark version",
        "split_name": "TODO official split/task set",
        "split_path": "TODO frozen split/task manifest path",
        "split_sha256": "TODO 64-hex SHA256 of frozen split/task manifest",
        "license": "TODO benchmark/data license",
        "baseline": "TODO matched baseline/control",
        "baseline_version": "TODO implementation version/commit",
        "citation": "TODO DOI/BibTeX key",
        "expected_metrics": ["TODO_metric"],
        "metric_schema": {
            "TODO_metric": {
                "direction": "TODO higher_is_better|lower_is_better|target|descriptive",
                "unit": "TODO unit",
                "description": "TODO metric definition",
            }
        },
        "grader": f"run_{role}_benchmark.py",
        "grader_path": f"run_{role}_benchmark.py",
        "grader_version": "TODO grader/evaluator version",
        "grader_sha256": "TODO 64-hex SHA256 of grader or official evaluation wrapper",
        "submission_path": f"{role}_submission.csv",
        "seed_policy": "RESEARCH_AGENT_SEED fixes split/task sampling and stochastic state",
        "min_repeats": min_repeats_default,
    }
    for key, value in defaults.items():
        current = result.get(key)
        if key not in result or current is None or current == "" or current == []:
            result[key] = value
    min_repeats = _safe_int(result.get("min_repeats"))
    if min_repeats < min_repeats_default:
        result["min_repeats"] = min_repeats_default
    return result


def _has_execution_repair(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("category") or "") in EXECUTION_REPAIR_CATEGORIES for item in items if isinstance(item, dict))


def _has_benchmark_repair(items: list[dict[str, Any]]) -> bool:
    return any(str(item.get("category") or "") in BENCHMARK_REPAIR_CATEGORIES for item in items if isinstance(item, dict))


def _nested_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list) and value:
            return value
    return []


def _first_string(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _safe_command_names(value: Any) -> list[str]:
    names = _string_list(value)
    unsafe = set("/\\;&|<>`$\r\n")
    return [name for name in names if name and not any(char in unsafe for char in name)]


def _repair_context(run_dir: Path, items: list[dict[str, Any]]) -> dict[str, Any]:
    constraints: list[str] = _experiment_manager_constraints(run_dir)
    source_artifacts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "").strip()
        severity = str(item.get("severity") or "").strip()
        category = str(item.get("category") or "").strip()
        source = str(item.get("source_artifact") or "").strip()
        action = str(item.get("action") or "").strip()
        if source:
            source_artifacts.append(source)
        label = " ".join(value for value in [task_id, severity, category, source] if value)
        if action:
            constraints.append(f"{label}: {action}" if label else action)
        if source:
            constraints.extend(_source_repair_constraints(run_dir / source, task_id or source))
    constraints = _dedupe([_short_constraint(item) for item in constraints if str(item).strip()])[:18]
    return {
        "constraints": constraints,
        "source_artifacts": _dedupe(source_artifacts),
        "prompt_text": _repair_prompt_text(constraints),
    }


def _source_repair_constraints(path: Path, label: str) -> list[str]:
    data = _read_json(path)
    if not data:
        return []
    constraints: list[str] = []
    status = str(data.get("status") or "").strip()
    if status:
        constraints.append(f"{label} source_status={status}")
    for field in ["blocking_issues", "manual_tasks", "required_actions", "warnings"]:
        for value in _list_values(data.get(field))[:5]:
            constraints.append(f"{label} {field}: {value}")
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    for check in checks:
        if not isinstance(check, dict):
            continue
        check_status = str(check.get("status") or "").strip()
        if check_status not in {"block", "review_required", "warn"}:
            continue
        name = str(check.get("name") or "").strip() or "check"
        actions = _list_values(check.get("required_actions"))
        evidence = _list_values(check.get("evidence"))
        if actions:
            constraints.append(f"{label} {name}/{check_status}: {'; '.join(actions[:3])}")
        elif evidence:
            constraints.append(f"{label} {name}/{check_status}: evidence {'; '.join(evidence[:3])}")
    return constraints


def _experiment_manager_resume_actions(run_dir: Path) -> list[dict[str, Any]]:
    manager = _read_json(run_dir / "02-experiment-manager.json")
    queue = manager.get("manager_queue") if isinstance(manager.get("manager_queue"), list) else []
    actions: list[dict[str, Any]] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        queue_state = str(item.get("queue_state") or "").strip()
        if queue_state not in {"blocked_human_repair", "needs_human_repair", "active_smoke_first", "deferred_novelty_check"}:
            continue
        actions.append(
            {
                "branch_id": str(item.get("branch_id") or ""),
                "title": str(item.get("title") or ""),
                "queue_state": queue_state,
                "selected": item.get("selected") is True,
                "requires_human": item.get("requires_human") is True,
                "blocks_current_experiment": item.get("blocks_current_experiment") is True,
                "resume_from": str(item.get("resume_from") or ""),
                "action": _manager_resume_action(item),
            }
        )
    return actions[:6]


def _experiment_manager_constraints(run_dir: Path) -> list[str]:
    manager = _read_json(run_dir / "02-experiment-manager.json")
    if not manager:
        return []
    constraints: list[str] = []
    selected = str(manager.get("selected_branch_id") or "").strip()
    decision = str(manager.get("manager_decision") or "").strip()
    policy = str(manager.get("execution_policy") or "").strip()
    if selected or decision or policy:
        constraints.append(f"experiment_manager selected={selected or '-'} decision={decision or '-'} policy={policy or '-'}")
    for value in _list_values(manager.get("required_actions"))[:4]:
        constraints.append(f"experiment_manager required_action: {value}")
    for value in _list_values(manager.get("planning_constraints"))[:4]:
        constraints.append(f"experiment_manager planning_constraint: {value}")
    for action in _experiment_manager_resume_actions(run_dir):
        branch = str(action.get("branch_id") or "-")
        state = str(action.get("queue_state") or "-")
        text = str(action.get("action") or "")
        if text:
            constraints.append(f"experiment_manager queue {branch}/{state}: {text}")
    return constraints


def _manager_resume_action(item: dict[str, Any]) -> str:
    queue_state = str(item.get("queue_state") or "").strip()
    next_action = str(item.get("next_action") or "").strip()
    issues = _string_list(item.get("issues"))
    issue_text = f"；问题：{'; '.join(issues[:3])}" if issues else ""
    if queue_state == "blocked_human_repair":
        return f"必须人工改选分支或补证修复后再从 ideation 恢复；未修复前禁止生成实验计划。{issue_text}"
    if queue_state == "needs_human_repair":
        return f"补齐该候选分支的证据、citation/chunk、baseline 或 novelty 复核后再放入下一轮。{issue_text}"
    if queue_state == "active_smoke_first":
        return f"只允许先做 smoke-first 实验计划，并把 claim 限制为可行性或诊断结论。{issue_text}"
    if queue_state == "deferred_novelty_check":
        return f"先人工复核 novelty；疑似重复未澄清前不得声称新颖贡献。{issue_text}"
    return next_action or "按 experiment manager 队列处理后再恢复。"


def _repair_prompt_text(constraints: list[str]) -> str:
    if not constraints:
        return ""
    lines = [
        "Repair-resume constraints from 12-repair-queue and source audits:",
        "The next generated plan must explicitly fix these issues and avoid repeating the stale artifacts.",
    ]
    lines.extend(f"- {item}" for item in constraints)
    return "\n".join(lines)


def _earliest_rerun_from(items: list[dict[str, Any]]) -> str:
    candidates = [str(item.get("rerun_from") or "").strip() for item in items]
    known = [candidate for candidate in candidates if candidate in RERUN_ORDER]
    if not known:
        return "submission_package"
    return min(known, key=_rerun_index)


def _patterns_from(rerun_from: str) -> list[str]:
    start = _rerun_index(rerun_from)
    patterns: list[str] = []
    for name in RERUN_ORDER[start:]:
        patterns.extend(ARTIFACT_PATTERNS_BY_RERUN_FROM.get(name, []))
    patterns.extend(["run-diagnostics.*", "run-recovery-plan.*"])
    return _dedupe(patterns)


def _dirs_from(rerun_from: str) -> list[str]:
    start = _rerun_index(rerun_from)
    dirs: list[str] = []
    for name in RERUN_ORDER[start:]:
        dirs.extend(DIRS_BY_RERUN_FROM.get(name, []))
    return _dedupe(dirs)


def _matching_files(run_dir: Path, patterns: list[str]) -> list[str]:
    files: list[str] = []
    for pattern in patterns:
        for path in run_dir.glob(pattern):
            if not path.is_file():
                continue
            rel = str(path.relative_to(run_dir))
            if rel in {REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD}:
                continue
            files.append(rel)
    return _dedupe(sorted(files))


def _remove_selected(run_dir: Path, report: dict[str, Any]) -> tuple[list[str], list[str]]:
    removed_files: list[str] = []
    removed_dirs: list[str] = []
    for name in report.get("artifacts_to_remove", []) if isinstance(report.get("artifacts_to_remove"), list) else []:
        path = (run_dir / str(name)).resolve()
        if not _is_relative_to(path, run_dir) or not path.is_file():
            continue
        path.unlink()
        removed_files.append(str(name))
    for name in report.get("directories_to_remove", []) if isinstance(report.get("directories_to_remove"), list) else []:
        path = (run_dir / str(name)).resolve()
        if not _is_relative_to(path, run_dir) or not path.is_dir():
            continue
        shutil.rmtree(path)
        removed_dirs.append(str(name))
    return removed_files, removed_dirs


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _recommended_actions(rerun_from: str, manager_actions: list[dict[str, Any]] | None = None) -> list[str]:
    actions = [f"从 `{rerun_from}` 清理旧产物后执行 checkpoint resume。"]
    if manager_actions:
        if any(item.get("blocks_current_experiment") for item in manager_actions if isinstance(item, dict)):
            actions.append("Experiment manager 阻断当前选中分支：先人工改选或补证修复，再允许生成 03-experiment-plan。")
        if any(str(item.get("queue_state") or "") == "active_smoke_first" for item in manager_actions if isinstance(item, dict)):
            actions.append("Experiment manager 要求 smoke-first：下一次实验计划必须保持低成本验证和保守 claim。")
    if rerun_from in {"literature_review", "literature_context"}:
        actions.append("重新查看 01-review-gate.md；未人工批准前不要进入 idea/实验。")
    if _rerun_index(rerun_from) <= _rerun_index("experiments"):
        actions.append("local/benchmark 模式会重新请求执行确认；未批准前不要运行实验命令。")
    actions.append("修复后检查 12-repair-queue.md、13-research-scorecard.md 和 14-run-integrity-audit.md。")
    return actions


def _rerun_index(rerun_from: str) -> int:
    try:
        return RERUN_ORDER.index(rerun_from)
    except ValueError:
        return len(RERUN_ORDER) - 1


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    item = str(value or "").strip()
    return [item] if item else []


def _short_constraint(value: str, limit: int = 260) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


