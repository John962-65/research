from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, cell as _cell, read_json_dict as _read_json
from .seed_paper_intake import build_seed_paper_suggestion_report


OPEN_SOURCE_COMPLIANCE_JSON = "13-open-source-compliance.json"
OPEN_SOURCE_COMPLIANCE_MD = "13-open-source-compliance.md"


def write_open_source_compliance_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_open_source_compliance_report(topic, run_dir)
    write_json(run_dir / OPEN_SOURCE_COMPLIANCE_JSON, report)
    write_text(run_dir / OPEN_SOURCE_COMPLIANCE_MD, render_open_source_compliance_markdown(report))
    return report


def build_open_source_compliance_report(topic: str, run_dir: Path) -> dict[str, Any]:
    lessons_report = _read_json(run_dir / "00-open-source-lessons.json")
    lessons = [item for item in _list(lessons_report.get("lessons")) if isinstance(item, dict)]
    results = [_evaluate_lesson(lesson, run_dir, topic) for lesson in lessons]
    project_summary = _source_project_summary(lessons_report, results)
    contract = _lesson_contract_summary(lessons_report, results)
    blocking = list(contract.get("blocking_issues") or [])
    blocking.extend(action for item in results if item.get("status") == "block" for action in _list(item.get("required_actions")))
    manual = [action for item in results if item.get("status") == "warn" for action in _list(item.get("required_actions"))]
    passed = sum(1 for item in results if item.get("status") == "pass")
    score = 0.0 if contract.get("status") == "block" and not results else round(passed / max(1, len(results)), 3)
    status = "block" if blocking else "needs_human_review" if manual else "pass"
    if not lessons:
        status = "block"
    return {
        "schema_version": 3,
        "topic": topic,
        "status": status,
        "score": score,
        "checked_lessons": len(results),
        "contract_summary": contract,
        "source_project_summary": project_summary,
        "lesson_results": results,
        "blocking_issues": _dedupe(blocking),
        "manual_tasks": _dedupe(manual),
        "recommended_actions": _recommended_actions(status, blocking, manual),
    }


def render_open_source_compliance_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Open-Source Lesson Compliance：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 合规得分：{float(report.get('score') or 0.0):.3f}",
        f"- 检查约束：{report.get('checked_lessons') or 0}",
        f"- 阻断问题：{len(_list(report.get('blocking_issues')))}",
        f"- 人工待办：{len(_list(report.get('manual_tasks')))}",
        f"- Contract 完整性：{_contract_status_text(report.get('contract_summary'))}",
        f"- 来源项目：{_count_from_summary(report.get('source_project_summary'), 'project_count')}，阻断项目：{_count_from_summary(report.get('source_project_summary'), 'blocked_project_count')}，复核项目：{_count_from_summary(report.get('source_project_summary'), 'warn_project_count')}",
        "",
        "## Lesson Contract",
        "| 状态 | Required Lessons | Checked Lessons | Required Projects | Evidence Projects | Missing Lessons | Missing Projects |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    contract = report.get("contract_summary") if isinstance(report.get("contract_summary"), dict) else {}
    lines.append(
        "| "
        + " | ".join(
            [
                _cell(str(contract.get("status") or "missing")),
                str(contract.get("required_lessons") or 0),
                str(contract.get("checked_lessons") or 0),
                str(contract.get("required_projects") or 0),
                str(contract.get("project_evidence") or 0),
                _cell(", ".join(str(item) for item in _list(contract.get("missing_lesson_ids"))) or "-"),
                _cell(", ".join(str(item) for item in _list(contract.get("missing_project_names"))) or "-"),
            ]
        )
        + " |"
    )
    lines.extend(
        [
            "",
        "## 来源项目闭环",
        "| 项目 | 状态 | Lessons | Pass | Warn | Block | 证据状态 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in _list((report.get("source_project_summary") or {}).get("projects") if isinstance(report.get("source_project_summary"), dict) else []):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("project_name") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("lesson_count") or 0)),
                    _cell(str(item.get("pass") or 0)),
                    _cell(str(item.get("warn") or 0)),
                    _cell(str(item.get("block") or 0)),
                    _cell(str(item.get("evidence_status") or "-")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 逐条约束",
            "| Lesson | 状态 | 来源项目 | 目标阶段 | 证据 | 动作 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in _list(report.get("lesson_results")):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("lesson_id") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell(", ".join(str(value) for value in _list(item.get("source_projects")))),
                    _cell(", ".join(str(value) for value in _list(item.get("pipeline_targets")))),
                    _cell("；".join(str(value) for value in _list(item.get("evidence"))) or "-"),
                    _cell("；".join(str(value) for value in _list(item.get("required_actions"))) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    blocking = _list(report.get("blocking_issues"))
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    manual = _list(report.get("manual_tasks"))
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- 无")
    lines.extend(["", "## 推荐动作"])
    actions = _list(report.get("recommended_actions"))
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 暂无")
    return "\n".join(lines)


def _evaluate_lesson(lesson: dict[str, Any], run_dir: Path, topic: str) -> dict[str, Any]:
    lesson_id = str(lesson.get("lesson_id") or "").strip()
    checks = {
        "source_project_provenance": _source_project_provenance,
        "structured_idea_to_experiment_loop": _structured_idea_to_experiment,
        "sandbox_generated_code": _sandbox_generated_code,
        "citation_grounded_fulltext": _citation_grounded_fulltext,
        "retrieval_rerank_before_synthesis": _retrieval_rerank_before_synthesis,
        "query_execution_coverage_audit": _query_execution_coverage_audit,
        "human_feedback_compliance": _human_feedback_compliance,
        "repair_context_on_resume": _repair_context_on_resume,
        "benchmark_result_schema_contract": _benchmark_result_schema_contract,
        "runtime_cost_observability": _runtime_cost_observability,
        "metadata_rate_limit_resilience": _metadata_rate_limit_resilience,
        "cache_and_memory_reuse": _cache_and_memory_reuse,
        "ai_use_disclosure": _ai_use_disclosure,
        "domain_benchmark_before_claims": _domain_benchmark_before_claims,
    }
    check = checks.get(lesson_id)
    result = check(run_dir, topic) if check else _unknown_lesson(lesson_id)
    return {
        "lesson_id": lesson_id,
        "status": result["status"],
        "source_projects": _list(lesson.get("source_projects")),
        "pipeline_targets": _list(lesson.get("pipeline_targets")),
        "requirement": str(lesson.get("requirement") or ""),
        "evidence": result["evidence"],
        "required_actions": result["actions"],
    }


def _source_project_summary(lessons_report: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_by_key = {
        _project_key(str(item.get("project_name") or item.get("name") or "")): item
        for item in _list(lessons_report.get("project_evidence"))
        if isinstance(item, dict)
    }
    profile_names = [
        str(item.get("name") or "").strip()
        for item in _list(lessons_report.get("profiles"))
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    project_order = _dedupe_project_names(
        profile_names
        + [
            str(project).strip()
            for result in results
            for project in _list(result.get("source_projects"))
            if str(project).strip()
        ]
    )
    projects: list[dict[str, Any]] = []
    for project_name in project_order:
        key = _project_key(project_name)
        project_results = [
            item
            for item in results
            if key in {_project_key(str(project)) for project in _list(item.get("source_projects"))}
        ]
        if not project_results:
            continue
        counts: dict[str, int] = {"pass": 0, "warn": 0, "block": 0}
        for item in project_results:
            status = str(item.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        status = "block" if counts.get("block") else "warn" if counts.get("warn") else "pass"
        evidence = evidence_by_key.get(key, {})
        evidence_status = str(evidence.get("status") or "missing") if isinstance(evidence, dict) else "missing"
        projects.append(
            {
                "project_name": project_name,
                "status": status,
                "lesson_count": len(project_results),
                "pass": counts.get("pass", 0),
                "warn": counts.get("warn", 0),
                "block": counts.get("block", 0),
                "lesson_ids": [str(item.get("lesson_id") or "") for item in project_results if str(item.get("lesson_id") or "").strip()],
                "blocked_lessons": [str(item.get("lesson_id") or "") for item in project_results if item.get("status") == "block" and str(item.get("lesson_id") or "").strip()],
                "warn_lessons": [str(item.get("lesson_id") or "") for item in project_results if item.get("status") == "warn" and str(item.get("lesson_id") or "").strip()],
                "evidence_status": evidence_status,
                "verification_mode": str(evidence.get("verification_mode") or "") if isinstance(evidence, dict) else "",
                "version_verified": bool(isinstance(evidence, dict) and (_list(evidence.get("verified_files")) or str(evidence.get("head_commit") or "").strip())),
            }
        )
    blocked_projects = [str(item["project_name"]) for item in projects if item.get("status") == "block"]
    warn_projects = [str(item["project_name"]) for item in projects if item.get("status") == "warn"]
    evidence_statuses: dict[str, int] = {}
    for item in projects:
        status = str(item.get("evidence_status") or "missing")
        evidence_statuses[status] = evidence_statuses.get(status, 0) + 1
    return {
        "project_count": len(projects),
        "blocked_project_count": len(blocked_projects),
        "warn_project_count": len(warn_projects),
        "pass_project_count": sum(1 for item in projects if item.get("status") == "pass"),
        "blocked_projects": blocked_projects,
        "warn_projects": warn_projects,
        "evidence_statuses": evidence_statuses,
        "projects": projects,
    }


def _lesson_contract_summary(lessons_report: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    contract = lessons_report.get("contract_summary") if isinstance(lessons_report.get("contract_summary"), dict) else {}
    lessons = [item for item in _list(lessons_report.get("lessons")) if isinstance(item, dict)]
    profiles = [item for item in _list(lessons_report.get("profiles")) if isinstance(item, dict)]
    project_evidence = [item for item in _list(lessons_report.get("project_evidence")) if isinstance(item, dict)]
    required_lesson_ids = _strings(contract.get("required_lesson_ids")) or _strings(item.get("lesson_id") for item in lessons)
    checked_lesson_ids = _strings(item.get("lesson_id") for item in results)
    required_projects = _strings(contract.get("required_project_names")) or _strings(item.get("name") for item in profiles)
    evidence_projects = _strings(item.get("project_name") or item.get("name") for item in project_evidence)
    missing_lessons = [item for item in required_lesson_ids if item not in set(checked_lesson_ids)]
    extra_lessons = [item for item in checked_lesson_ids if item not in set(required_lesson_ids)]
    missing_projects = [item for item in required_projects if _project_key(item) not in {_project_key(project) for project in evidence_projects}]
    blocking: list[str] = []
    if not lessons_report:
        blocking.append("生成 00-open-source-lessons.json，记录开源项目 lesson contract。")
    if not contract:
        blocking.append("补齐 00-open-source-lessons.json 的 contract_summary，防止开源项目约束被静默删减。")
    if not required_lesson_ids:
        blocking.append("补齐 open-source lesson contract 的 required_lesson_ids。")
    if missing_lessons:
        blocking.append("补齐缺失的 open-source lessons：" + ", ".join(missing_lessons[:8]) + "。")
    if not required_projects:
        blocking.append("补齐 open-source lesson contract 的 required_project_names。")
    if missing_projects:
        blocking.append("补齐缺失的参考项目 provenance：" + ", ".join(missing_projects[:8]) + "。")
    if not project_evidence:
        blocking.append("为 open-source lessons 补充 project_evidence，不能只保留 lesson 文本。")
    return {
        "schema_version": 1,
        "status": "block" if blocking else "pass",
        "required_lessons": len(required_lesson_ids),
        "checked_lessons": len(checked_lesson_ids),
        "required_projects": len(required_projects),
        "project_evidence": len(project_evidence),
        "required_lesson_ids": required_lesson_ids,
        "checked_lesson_ids": checked_lesson_ids,
        "missing_lesson_ids": missing_lessons,
        "extra_lesson_ids": extra_lessons,
        "required_project_names": required_projects,
        "project_evidence_names": evidence_projects,
        "missing_project_names": missing_projects,
        "blocking_issues": blocking,
    }


def _structured_idea_to_experiment(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _present(run_dir, "02-ideas.json"),
        _present(run_dir, "02-exploration-map.json"),
        _status_artifact(run_dir, "02-experiment-manager.json"),
        _present(run_dir, "03-experiment-plan.json"),
        _status_artifact(run_dir, "03-idea-experiment-contract.json"),
    )


def _sandbox_generated_code(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _status_artifact(run_dir, "03-execution-safety-audit.json"),
        _present(run_dir, "04-experiment-runbook.json"),
        _status_artifact(run_dir, "04-environment-snapshot.json", pass_statuses={"complete", "pass"}, warn_statuses={"partial"}),
    )


def _citation_grounded_fulltext(run_dir: Path, topic: str) -> dict[str, Any]:
    context = _read_json(run_dir / "01-context.json")
    fulltext = _read_json(run_dir / "01-fulltext-corpus.json")
    citations = len(_list(context.get("citations")))
    chunks = len(_list(context.get("chunks")))
    fulltext_docs = _int(fulltext.get("documents_count")) or len(_list(fulltext.get("documents")))
    status = "pass"
    actions: list[str] = []
    if citations < 3 or chunks < 3:
        status = "block"
        actions.append("补齐 01-context 中可追踪 citation/chunk，避免只凭标题摘要进入写作。")
    elif fulltext and fulltext_docs == 0:
        status = "warn"
        actions.append("已声明 fulltext corpus 但没有可用全文文档；补全文路径或说明豁免。")
    grounding = _status_artifact(run_dir, "10-citation-grounding.json")
    combined = _combine({"status": status, "evidence": [f"context_citations={citations}", f"context_chunks={chunks}", f"fulltext_documents={fulltext_docs}"], "actions": actions}, grounding)
    return combined


def _retrieval_rerank_before_synthesis(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _status_artifact(run_dir, "01-literature-rerank.json"),
        _present(run_dir, "01-literature-quality.json"),
        _status_artifact(run_dir, "01-literature-metadata-audit.json"),
        _status_artifact(run_dir, "01-literature-evidence-mix.json"),
        _status_artifact(run_dir, "01-literature-evidence-contract.json"),
        _seed_intake_artifact(run_dir, topic),
    )


def _query_execution_coverage_audit(run_dir: Path, topic: str) -> dict[str, Any]:
    if _paper_grade_literature_pass(run_dir):
        return _combine(
            _status_artifact(run_dir, "01-literature-search-strategy.json", warn_statuses={"review_required", "needs_query_repair"}),
            _status_artifact(run_dir, "01-query-execution-audit.json", warn_statuses={"review_required", "needs_query_repair"}),
            _status_artifact(run_dir, "01-literature-source-health.json", warn_if_actions=False),
        )
    return _combine(
        _status_artifact(run_dir, "01-literature-search-strategy.json"),
        _status_artifact(run_dir, "01-query-execution-audit.json"),
        _status_artifact(run_dir, "01-literature-source-health.json", warn_if_actions=False),
    )


def _human_feedback_compliance(run_dir: Path, topic: str) -> dict[str, Any]:
    approval = _read_json(run_dir / "approval.json")
    blocks = {str(item) for item in _list(approval.get("blocks"))}
    notes = str(approval.get("notes") or "").strip()
    gate_status = str(approval.get("gate_status") or "")
    status = "pass"
    actions: list[str] = []
    if approval.get("approved") is not True:
        status = "block"
        actions.append("人工批准 review gate 后才允许进入 idea/实验。")
    if not {"idea_generation", "experiment_planning", "experiment_execution"}.issubset(blocks):
        status = "block"
        actions.append("approval.json 必须记录 idea、experiment planning 和 execution 阻断范围。")
    if gate_status and gate_status != "pass" and not notes:
        status = "block"
        actions.append("非 pass gate 的批准必须包含实质审核意见。")
    return _combine(
        {"status": status, "evidence": [f"approved={approval.get('approved') is True}", f"gate_status={gate_status or '-'}", f"blocks={len(blocks)}"], "actions": actions},
        _present(run_dir, "01-review-constraints.json"),
        _status_artifact(run_dir, "03-review-constraint-compliance.json"),
    )


def _repair_context_on_resume(run_dir: Path, topic: str) -> dict[str, Any]:
    if not (run_dir / "12-repair-resume-plan.json").exists():
        return {"status": "pass", "evidence": ["repair_resume_plan=not_applicable"], "actions": []}
    return _combine(
        _present(run_dir, "12-repair-resume-plan.json"),
        _status_artifact(run_dir, "12-repair-resolution-audit.json", pass_statuses={"pass", "not_applicable"}, warn_statuses={"review_required"}),
    )


def _benchmark_result_schema_contract(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _status_artifact(run_dir, "04-benchmark-result-schema-audit.json"),
        _status_artifact(run_dir, "04-benchmark-evidence-audit.json", warn_statuses={"smoke_only", "review_required"}),
    )


def _runtime_cost_observability(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _present(run_dir, "run-manifest.json"),
        _present(run_dir, "run-llm-ledger.json"),
        _status_artifact(run_dir, "13-llm-trace-audit.json"),
        _status_artifact(run_dir, "13-run-economics-audit.json", warn_statuses={"review_required"}),
        _status_artifact(run_dir, "13-agent-observability-audit.json", warn_statuses={"review_required"}),
    )


def _metadata_rate_limit_resilience(run_dir: Path, topic: str) -> dict[str, Any]:
    source_health = _read_json(run_dir / "01-literature-source-health.json")
    rate_limited = _int(source_health.get("rate_limited_sources"))
    failed = _int(source_health.get("failed_sources"))
    query_attempts = _int(source_health.get("query_attempts"))
    query_successes = _int(source_health.get("query_successes"))
    status = "pass"
    actions: list[str] = []
    if query_attempts and query_successes == 0:
        status = "block"
        actions.append("文献源 query 全部无成功返回；修复 API key/source 配置并重跑检索。")
    elif rate_limited or failed:
        status = "warn"
        actions.append("修复限流或失败的文献源，优先配置 Semantic Scholar key 和联系邮箱。")
    return _combine(
        {"status": status, "evidence": [f"rate_limited_sources={rate_limited}", f"failed_sources={failed}", f"query_successes={query_successes}/{query_attempts}"], "actions": actions},
        _status_artifact(run_dir, "01-literature-rescue-plan.json"),
        _status_artifact(run_dir, "01-literature-search-feedback.json", warn_if_actions=False),
    )


def _cache_and_memory_reuse(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _present(run_dir, "00-prior-run-lessons.json"),
        _present(run_dir, "00-open-source-lessons.json"),
    )


def _source_project_provenance(run_dir: Path, topic: str) -> dict[str, Any]:
    lessons = _read_json(run_dir / "00-open-source-lessons.json")
    evidence_items = [item for item in _list(lessons.get("project_evidence")) if isinstance(item, dict)]
    profiles = [item for item in _list(lessons.get("profiles")) if isinstance(item, dict)]
    if not lessons:
        return {"status": "block", "evidence": ["00-open-source-lessons.json=missing"], "actions": ["生成 00-open-source-lessons.json，记录参考开源项目来源证据。"]}
    if not evidence_items:
        return {"status": "block", "evidence": ["project_evidence=missing"], "actions": ["为 open-source lessons 补充 project_evidence，至少包含仓库 URL 和证据目标文件。"]}
    missing_url = [str(item.get("project_name") or "unknown") for item in evidence_items if not str(item.get("repository_url") or "").strip()]
    missing_targets = [str(item.get("project_name") or "unknown") for item in evidence_items if not _list(item.get("evidence_targets"))]
    failed = [str(item.get("project_name") or "unknown") for item in evidence_items if str(item.get("status") or "") in {"failed", "missing", "error"}]
    statuses = ",".join(str(item.get("status") or "-") for item in evidence_items)
    verified = sum(1 for item in evidence_items if _list(item.get("verified_files")) or str(item.get("head_commit") or "").strip())
    evidence = [f"project_evidence={len(evidence_items)}/{len(profiles) or len(evidence_items)}", f"statuses={statuses}", f"version_verified_projects={verified}"]
    if missing_url or missing_targets or failed:
        actions = []
        if missing_url:
            actions.append("补齐参考开源项目仓库 URL：" + ", ".join(missing_url[:4]) + "。")
        if missing_targets:
            actions.append("补齐参考开源项目证据目标文件：" + ", ".join(missing_targets[:4]) + "。")
        if failed:
            actions.append("刷新失败的开源项目 provenance 或记录人工豁免：" + ", ".join(failed[:4]) + "。")
        return {"status": "block", "evidence": evidence, "actions": actions}
    if verified == 0:
        evidence.append("version_mode=built_in_catalog")
    return {"status": "pass", "evidence": evidence, "actions": []}


def _ai_use_disclosure(run_dir: Path, topic: str) -> dict[str, Any]:
    return _combine(
        _status_artifact(run_dir, "10-ai-disclosure.json", warn_statuses={"needs_human_policy_check"}),
        _status_artifact(run_dir, "13-llm-trace-audit.json"),
    )


def _domain_benchmark_before_claims(run_dir: Path, topic: str) -> dict[str, Any]:
    if not _robotics_topic(topic):
        return {"status": "pass", "evidence": ["domain_benchmark=not_applicable"], "actions": []}
    benchmark = _status_artifact(run_dir, "03-benchmark-plan.json")
    readiness = _status_artifact(run_dir, "03-benchmark-readiness.json", warn_statuses={"needs_benchmark_upgrade"})
    evidence = _read_json(run_dir / "04-benchmark-evidence-audit.json")
    claim = _status_artifact(run_dir, "04-claim-boundary-preflight.json")
    grade = str(evidence.get("evidence_grade") or "")
    status = "pass"
    actions: list[str] = []
    if grade == "blocked" or str(evidence.get("status") or "") == "block":
        status = "block"
        actions.extend(str(item) for item in _list(evidence.get("blocking_issues"))[:3] or ["修复真实 benchmark 证据阻断项。"])
    elif grade in {"smoke_only", "local_experiment"}:
        status = "warn"
        actions.append("机械臂路径规划仍是 smoke/local 证据；升级 OMPL/MoveIt 等真实 benchmark，或在论文中明确降级。")
    return _combine({"status": status, "evidence": [f"benchmark_evidence={grade or '-'}"], "actions": actions}, benchmark, readiness, claim)


def _seed_intake_artifact(run_dir: Path, topic: str) -> dict[str, Any]:
    data = _read_json(run_dir / "01-seed-paper-intake.json")
    if not data:
        suggestion = build_seed_paper_suggestion_report(topic, run_dir)
        if suggestion.get("suggested_seed_count"):
            missing = _list(suggestion.get("missing_roles"))
            actions = _list(suggestion.get("role_repair_queries"))[:3]
            if missing:
                actions.append("人工核对候选 DOI/URL seed，并补齐缺失 seed 角色：" + ", ".join(str(item) for item in missing[:4]) + "。")
            else:
                actions.append("人工核对候选 DOI/URL seed，写入 seed_papers 后重新生成 01-seed-paper-intake.json。")
            return {
                "status": "warn",
                "evidence": [
                    "01-seed-paper-intake.json=missing",
                    f"suggested_seed_count={suggestion.get('suggested_seed_count') or 0}",
                    "suggested_roles=" + ",".join(f"{key}:{value}" for key, value in dict(suggestion.get("suggested_seed_role_counts") or {}).items()),
                ],
                "actions": actions,
            }
        return {"status": "block", "evidence": ["01-seed-paper-intake.json=missing"], "actions": ["生成 01-seed-paper-intake.json，记录人工 seed 是否进入 curated context。"]}
    status_value = str(data.get("status") or "")
    role_status = str(data.get("role_coverage_status") or "")
    evidence = [f"01-seed-paper-intake.json={status_value or 'present'}:{role_status or '-'}"]
    actions = _list(data.get("required_actions"))
    if status_value == "block":
        return {"status": "block", "evidence": evidence, "actions": [str(item) for item in actions[:3]] or ["修复人工 seed 文献输入，让核心 DOI/URL 进入 curated context。"]}
    if status_value in {"review_required", "not_configured"} or role_status == "review_required":
        return {"status": "warn", "evidence": evidence, "actions": [str(item) for item in actions[:3]] or ["人工复核 01-seed-paper-intake.md；补齐 seed 角色覆盖或写明豁免理由。"]}
    return {"status": "pass", "evidence": evidence, "actions": []}


def _paper_grade_literature_pass(run_dir: Path) -> bool:
    gate = _read_json(run_dir / "01-literature-gate-decision.json")
    paper_grade = gate.get("paper_grade_literature") if isinstance(gate.get("paper_grade_literature"), dict) else {}
    return str(paper_grade.get("status") or "") == "pass"


def _unknown_lesson(lesson_id: str) -> dict[str, Any]:
    return {
        "status": "warn",
        "evidence": [f"lesson_id={lesson_id or '-'}"],
        "actions": [f"为 open-source lesson {lesson_id or '-'} 补充合规检查映射。"],
    }


def _present(run_dir: Path, artifact: str) -> dict[str, Any]:
    if not (run_dir / artifact).exists():
        return {"status": "block", "evidence": [f"{artifact}=missing"], "actions": [f"生成 {artifact}。"]}
    return {"status": "pass", "evidence": [f"{artifact}=present"], "actions": []}


def _status_artifact(
    run_dir: Path,
    artifact: str,
    *,
    pass_statuses: set[str] | None = None,
    warn_statuses: set[str] | None = None,
    warn_if_actions: bool = True,
) -> dict[str, Any]:
    data = _read_json(run_dir / artifact)
    if not data:
        return {"status": "block", "evidence": [f"{artifact}=missing"], "actions": [f"生成 {artifact}。"]}
    status_value = str(data.get("status") or "").strip()
    pass_values = pass_statuses or {"pass", "ready", "ready_for_benchmark", "ready_for_submission_check", "ready_for_release", "complete", "completed", "not_applicable"}
    warn_values = warn_statuses or {"warn", "review_required", "needs_human_review", "needs_benchmark_upgrade", "needs_human_policy_check", "needs_human_format_check", "needs_human_submission_review", "needs_release_metadata", "needs_human_release_metadata", "ready_for_human_polish"}
    block_values = {"block", "blocked", "fail", "failed", "requires_human_evidence", "requires_revision", "blocked_repair_required", "needs_source_repair", "needs_query_repair"}
    blocking = _list(data.get("blocking_issues"))
    actions = _list(data.get("required_actions")) or _list(data.get("manual_tasks")) or _list(data.get("recommended_actions")) or _list(data.get("warnings"))
    evidence = [f"{artifact}={status_value or 'present'}"]
    if status_value in (warn_statuses or set()):
        return {"status": "warn", "evidence": evidence, "actions": [str(item) for item in actions[:3]] or [f"人工复核 {artifact}。"]}
    if status_value in block_values or blocking:
        return {"status": "block", "evidence": evidence, "actions": [str(item) for item in (blocking or actions)[:3]] or [f"修复 {artifact} 中的阻断项。"]}
    if status_value in warn_values or (warn_if_actions and actions and status_value not in pass_values):
        return {"status": "warn", "evidence": evidence, "actions": [str(item) for item in actions[:3]] or [f"人工复核 {artifact}。"]}
    return {"status": "pass", "evidence": evidence, "actions": []}


def _combine(*checks: dict[str, Any]) -> dict[str, Any]:
    evidence = [str(item) for check in checks for item in _list(check.get("evidence")) if str(item).strip()]
    block_actions = [str(item) for check in checks if check.get("status") == "block" for item in _list(check.get("actions")) if str(item).strip()]
    warn_actions = [str(item) for check in checks if check.get("status") == "warn" for item in _list(check.get("actions")) if str(item).strip()]
    status = "block" if block_actions else "warn" if warn_actions else "pass"
    return {"status": status, "evidence": evidence, "actions": _dedupe(block_actions or warn_actions)}


def _recommended_actions(status: str, blocking: list[str], manual: list[str]) -> list[str]:
    if status == "block":
        return _dedupe(blocking)[:8]
    if status == "needs_human_review":
        return _dedupe(manual)[:8]
    return ["外部项目约束已闭环；继续检查 repair queue、stage contract 和 scorecard。"]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        try:
            raw = list(value)
        except TypeError:
            raw = []
    return _dedupe([str(item).strip() for item in raw if str(item).strip()])


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count_from_summary(value: Any, key: str) -> int:
    if not isinstance(value, dict):
        return 0
    return _int(value.get(key))


def _contract_status_text(value: Any) -> str:
    if not isinstance(value, dict):
        return "missing"
    return (
        f"{value.get('status') or '-'} "
        f"lessons={_int(value.get('checked_lessons'))}/{_int(value.get('required_lessons'))} "
        f"projects={_int(value.get('project_evidence'))}/{_int(value.get('required_projects'))}"
    )


def _project_key(value: str) -> str:
    text = value.strip().lower()
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    if "mlagentbench" in compact or "mlebench" in compact:
        return "mlagentbench"
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text.replace("-style tasks", "").replace(" ", "").replace("-", "").replace("_", "")


def _dedupe_project_names(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = _project_key(text)
        if text and key and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _robotics_topic(topic: str) -> bool:
    lowered = topic.lower()
    return "机械臂" in topic or "manipulator" in lowered or ("robot" in lowered and ("path" in lowered or "motion" in lowered))


