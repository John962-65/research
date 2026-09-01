from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text
from .submission_package_zip import safe_submission_package_zip_filename, submission_package_zip_blocking_issue


FINAL_HANDOFF_JSON = "14-final-handoff.json"
FINAL_HANDOFF_MD = "14-final-handoff.md"


def write_final_handoff_artifacts(topic: str, run_dir: Path) -> dict[str, Any]:
    report = build_final_handoff_report(topic, run_dir)
    write_json(run_dir / FINAL_HANDOFF_JSON, report)
    write_text(run_dir / FINAL_HANDOFF_MD, render_final_handoff_markdown(report))
    return report


def build_final_handoff_report(topic: str, run_dir: Path) -> dict[str, Any]:
    package = _read_json(run_dir / "11-submission-package.json")
    scorecard = _read_json(run_dir / "13-research-scorecard.json")
    integrity = _read_json(run_dir / "14-run-integrity-audit.json")
    paper_grade = _paper_grade_summary(run_dir)
    package_zip = str(package.get("package_zip") or "11-submission-package.zip")
    package_files = package.get("files") if isinstance(package.get("files"), list) else []
    package_paths = {str(item.get("package_path") or "") for item in package_files if isinstance(item, dict)}
    package_has_integrity_audit = "submission-package/audits/run-integrity-audit.json" in package_paths
    blocking: list[str] = []
    manual: list[str] = []

    package_status = _status_field(package)
    scorecard_status = _status_field(scorecard)
    integrity_status = _status_field(integrity)
    package_zip_blocking_issue = submission_package_zip_blocking_issue(run_dir / package_zip, package_zip_name=package_zip, require_safe_filename=True)
    package_zip_exists = safe_submission_package_zip_filename(package_zip) and _nonempty_file(run_dir / package_zip)
    if not package:
        blocking.append("11-submission-package.json 缺失，无法交付 ZIP。")
    elif package_status == "blocked":
        blocking.extend(_prefixed_items("submission_package", package.get("blocking_issues")))
    elif package_status == "needs_human_submission_review":
        manual.append("投稿包仍需人工上传前核验。")
    if package_zip_blocking_issue:
        blocking.append(package_zip_blocking_issue)

    if not scorecard:
        blocking.append("13-research-scorecard.json 缺失，无法判断研究就绪度。")
    elif scorecard_status == "blocked":
        blocking.extend(_prefixed_items("scorecard", scorecard.get("blocking_issues")))
    elif scorecard_status != "ready_for_human_submission_upload":
        manual.append(f"研究分数卡状态为 {scorecard_status or '-'}，需人工确认是否进入投稿/归档。")

    if not integrity:
        blocking.append("14-run-integrity-audit.json 缺失，无法完成最终完整性 handoff。")
    elif integrity_status == "block":
        blocking.extend(_prefixed_items("run_integrity", integrity.get("blocking_issues")))
    elif integrity_status == "warn":
        manual.extend(_prefixed_items("run_integrity", integrity.get("warnings")))

    if integrity and not package_has_integrity_audit:
        manual.append("submission package 未包含 run-integrity-audit.json；若要离线交付最终审计快照，请重新生成投稿包或附上 14-run-integrity-audit.*。")
    blocking.extend(_prefixed_items("paper_grade", paper_grade.get("blocking_issues")))
    manual.extend(_prefixed_items("paper_grade", paper_grade.get("manual_tasks")))

    status = "blocked" if blocking else "ready_for_human_handoff" if manual else "ready_for_submission_upload"
    return {
        "topic": topic or _topic_from(package, scorecard, integrity, run_dir),
        "status": status,
        "package_zip": package_zip,
        "package_zip_exists": package_zip_exists,
        "package_zip_valid": not package_zip_blocking_issue,
        "package_status": package_status,
        "scorecard_status": scorecard_status,
        "scorecard_overall_score": scorecard.get("overall_score", 0.0) if isinstance(scorecard, dict) else 0.0,
        "run_integrity_status": integrity_status,
        "run_integrity_summary": integrity.get("summary", {}) if isinstance(integrity.get("summary"), dict) else {},
        "paper_grade_summary": paper_grade,
        "package_has_integrity_audit": package_has_integrity_audit,
        "blocking_issues": _dedupe(blocking),
        "manual_tasks": _dedupe(manual),
        "recommended_actions": _recommended_actions(status),
    }


def render_final_handoff_markdown(report: dict[str, Any]) -> str:
    summary = report.get("run_integrity_summary") if isinstance(report.get("run_integrity_summary"), dict) else {}
    paper_grade = report.get("paper_grade_summary") if isinstance(report.get("paper_grade_summary"), dict) else {}
    lines = [
        f"# 最终交付清单：{report.get('topic') or '未命名课题'}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- ZIP：{report.get('package_zip') or '-'}（{_zip_state_cell(report)}）",
        f"- 投稿包：{report.get('package_status') or '-'}",
        f"- 分数卡：{report.get('scorecard_status') or '-'}（{report.get('scorecard_overall_score', 0.0)}）",
        f"- 完整性：{report.get('run_integrity_status') or '-'}（P{summary.get('pass', 0)} W{summary.get('warn', 0)} B{summary.get('block', 0)}）",
        f"- 论文级：{_paper_grade_cell(paper_grade)}",
        f"- 包含完整性审计快照：{'是' if report.get('package_has_integrity_audit') else '否'}",
        "",
        "## 阻断问题",
    ]
    blockers = report.get("blocking_issues", []) if isinstance(report.get("blocking_issues"), list) else []
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- 无")
    lines.extend(["", "## 人工交付待办"])
    manual = report.get("manual_tasks", []) if isinstance(report.get("manual_tasks"), list) else []
    lines.extend(f"- [ ] {item}" for item in manual) if manual else lines.append("- 无")
    lines.extend(["", "## 论文级审计"])
    if paper_grade:
        for key, label in [
            ("literature", "文献"),
            ("benchmark", "Benchmark"),
            ("adapter", "Adapter"),
            ("claim_preflight", "Claim 预检"),
            ("claim_consistency", "Claim 一致性"),
            ("negative_or_neutral_boundary", "负/中性边界"),
        ]:
            value = paper_grade.get(key) if isinstance(paper_grade.get(key), dict) else {}
            lines.append(f"- {label}：{_paper_grade_detail(value)}")
    else:
        lines.append("- 未发现论文级审计摘要")
    lines.extend(["", "## 推荐动作"])
    actions = report.get("recommended_actions", []) if isinstance(report.get("recommended_actions"), list) else []
    lines.extend(f"- [ ] {item}" for item in actions) if actions else lines.append("- 无")
    return "\n".join(lines)


def _paper_grade_summary(run_dir: Path) -> dict[str, Any]:
    literature_gate = _read_json(run_dir / "01-literature-gate-decision.json")
    benchmark = _read_json(run_dir / "04-benchmark-evidence-audit.json")
    claim_preflight = _read_json(run_dir / "04-claim-boundary-preflight.json")
    claim_consistency = _read_json(run_dir / "10-claim-consistency.json")
    blocking: list[str] = []
    manual: list[str] = []
    missing: list[str] = []

    literature = _literature_paper_grade(literature_gate, missing, blocking, manual)
    benchmark_summary, adapter = _benchmark_paper_grade(benchmark, missing, blocking, manual)
    claim_preflight_summary = _claim_preflight_grade(claim_preflight, missing, blocking, manual)
    claim_consistency_summary = _claim_consistency_grade(claim_consistency, missing, blocking, manual)
    negative_or_neutral_boundary = _negative_or_neutral_boundary_grade(benchmark, claim_preflight, claim_consistency, blocking, manual)
    return {
        "literature": literature,
        "benchmark": benchmark_summary,
        "adapter": adapter,
        "claim_preflight": claim_preflight_summary,
        "claim_consistency": claim_consistency_summary,
        "negative_or_neutral_boundary": negative_or_neutral_boundary,
        "missing_artifacts": missing,
        "blocking_issues": _dedupe(blocking),
        "manual_tasks": _dedupe(manual),
    }


def _literature_paper_grade(data: dict[str, Any], missing: list[str], blocking: list[str], manual: list[str]) -> dict[str, Any]:
    if not data:
        missing.append("01-literature-gate-decision.json")
        manual.append("01-literature-gate-decision.json 缺失，无法确认 online/auto 文献、多源来源与 DOI/URL seed。")
        return {"status": "", "issues": 0}
    paper_grade = data.get("paper_grade_literature") if isinstance(data.get("paper_grade_literature"), dict) else {}
    status = str(paper_grade.get("status") or "")
    issues = _count_list(paper_grade.get("issues"))
    if status == "block":
        blocking.append(f"paper-grade literature 为 block，issues={issues}。")
    elif status and status != "pass":
        manual.append(f"paper-grade literature 为 {status}，需补齐 online/auto、多源成功检索、DOI/URL seed 和 curated seed。")
    elif not status:
        manual.append("paper-grade literature 状态缺失，需重新生成 01-literature-gate-decision.json。")
    return {"status": status, "issues": issues}


def _benchmark_paper_grade(data: dict[str, Any], missing: list[str], blocking: list[str], manual: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not data:
        missing.append("04-benchmark-evidence-audit.json")
        manual.append("04-benchmark-evidence-audit.json 缺失，无法确认真实 benchmark 与 candidate/baseline/ablation manifest。")
        return {"status": "", "grade": "", "issues": 0}, {"status": "", "issues": 0}
    status = str(data.get("status") or "")
    grade = str(data.get("evidence_grade") or "")
    issues = _count_list(data.get("blocking_issues")) + _count_list(data.get("manual_tasks"))
    adapter_status = str(data.get("adapter_paper_grade_status") or "")
    adapter_issues = _count_list(data.get("adapter_paper_grade_issues"))
    if status == "block" or grade == "blocked":
        blocking.append(f"benchmark evidence 为 {status or '-'} / {grade or '-'}，不能作为最终论文级证据。")
    elif status in {"smoke_only", "review_required"} or grade in {"smoke_only", "local_experiment"}:
        manual.append(f"benchmark evidence 为 {status or '-'} / {grade or '-'}，正式上传前需真实 benchmark 复核。")
    if adapter_status == "review_required":
        manual.append(f"adapter paper-grade 为 review_required，需补齐 candidate/baseline/ablation、共享指标和 repeat policy，issues={adapter_issues}。")
    elif not adapter_status:
        manual.append("adapter paper-grade 状态缺失，需重新生成 benchmark evidence audit。")
    return {"status": status, "grade": grade, "issues": issues}, {"status": adapter_status, "issues": adapter_issues}


def _claim_preflight_grade(data: dict[str, Any], missing: list[str], blocking: list[str], manual: list[str]) -> dict[str, Any]:
    if not data:
        missing.append("04-claim-boundary-preflight.json")
        manual.append("04-claim-boundary-preflight.json 缺失，无法确认结果写作边界。")
        return {"status": "", "mode": "", "issues": 0}
    status = str(data.get("status") or "")
    mode = str(data.get("writing_mode") or "")
    issues = _count_list(data.get("blocking_issues")) + _count_list(data.get("warnings"))
    if status == "block" or _count_list(data.get("blocking_issues")):
        blocking.append(f"claim boundary preflight 为 {status or '-'}，写作边界仍有阻断项。")
    elif status and status != "pass":
        manual.append(f"claim boundary preflight 为 {status} / {mode or '-'}，需人工确认结果表述边界。")
    elif not status:
        manual.append("claim boundary preflight 状态缺失，需重新生成 04-claim-boundary-preflight.json。")
    return {"status": status, "mode": mode, "issues": issues}


def _claim_consistency_grade(data: dict[str, Any], missing: list[str], blocking: list[str], manual: list[str]) -> dict[str, Any]:
    if not data:
        missing.append("10-claim-consistency.json")
        manual.append("10-claim-consistency.json 缺失，无法确认最终论文 claim 与证据边界一致。")
        return {"status": "", "score": None, "issues": 0}
    status = str(data.get("status") or "")
    score = _safe_float_or_none(data.get("consistency_score"))
    issues = _count_list(data.get("blocking_issues")) + _count_list(data.get("manual_tasks"))
    if status == "block" or _count_list(data.get("blocking_issues")):
        blocking.append(f"claim consistency 为 {status or '-'}，最终论文仍有越界 claim。")
    elif status and status != "pass":
        manual.append(f"claim consistency 为 {status}，需人工处理 {issues} 个 claim 一致性待办。")
    elif not status:
        manual.append("claim consistency 状态缺失，需重新生成 10-claim-consistency.json。")
    return {"status": status, "score": score, "issues": issues}


def _negative_or_neutral_boundary_grade(
    benchmark: dict[str, Any],
    claim_preflight: dict[str, Any],
    claim_consistency: dict[str, Any],
    blocking: list[str],
    manual: list[str],
) -> dict[str, Any]:
    publishable = benchmark.get("publishable_negative_or_neutral_result") is True
    outcome = str(benchmark.get("statistical_outcome") or "")
    severity = str(benchmark.get("claim_boundary_severity") or "")
    if not publishable:
        return {"status": "not_applicable", "publishable": False, "statistical_outcome": outcome, "claim_boundary_severity": severity}
    consistency_status = str(claim_consistency.get("status") or "")
    consistency_blockers = _count_list(claim_consistency.get("blocking_issues"))
    preflight_status = str(claim_preflight.get("status") or "")
    preflight_blockers = _count_list(claim_preflight.get("blocking_issues"))
    bounded = severity == "negative_or_neutral_no_superiority" and consistency_status == "pass" and consistency_blockers == 0
    if not bounded:
        blocking.append(
            "negative/neutral benchmark result 缺少 no-superiority claim boundary 或 claim consistency pass，不能最终交付。"
        )
    elif preflight_status != "pass" or preflight_blockers:
        manual.append("negative/neutral benchmark result 已保留 no-superiority boundary，但 claim preflight 仍需人工确认。")
    return {
        "status": "bounded_negative_or_neutral" if bounded else "unbounded_negative_or_neutral",
        "publishable": True,
        "statistical_outcome": outcome,
        "claim_boundary_severity": severity,
        "claim_consistency_status": consistency_status,
        "claim_consistency_blocking_issues": consistency_blockers,
        "claim_preflight_status": preflight_status,
        "claim_preflight_blocking_issues": preflight_blockers,
    }


def _zip_state_cell(report: dict[str, Any]) -> str:
    exists = report.get("package_zip_exists")
    valid = report.get("package_zip_valid")
    exists_label = "存在" if exists is True else "缺失" if exists is False else "未知"
    valid_label = "有效" if valid is True else "无效" if valid is False else "有效性未知"
    return f"{exists_label}，{valid_label}"


def _paper_grade_cell(summary: dict[str, Any]) -> str:
    if not summary:
        return "-"
    literature = summary.get("literature") if isinstance(summary.get("literature"), dict) else {}
    benchmark = summary.get("benchmark") if isinstance(summary.get("benchmark"), dict) else {}
    adapter = summary.get("adapter") if isinstance(summary.get("adapter"), dict) else {}
    claim = summary.get("claim_preflight") if isinstance(summary.get("claim_preflight"), dict) else {}
    consistency = summary.get("claim_consistency") if isinstance(summary.get("claim_consistency"), dict) else {}
    boundary = summary.get("negative_or_neutral_boundary") if isinstance(summary.get("negative_or_neutral_boundary"), dict) else {}
    parts = [
        _summary_part("lit", str(literature.get("status") or ""), "", _safe_int(literature.get("issues"))),
        _summary_part("bench", str(benchmark.get("status") or ""), str(benchmark.get("grade") or ""), _safe_int(benchmark.get("issues"))),
        _summary_part("adapter", str(adapter.get("status") or ""), "", _safe_int(adapter.get("issues"))),
        _summary_part("claim", str(claim.get("status") or ""), str(claim.get("mode") or ""), _safe_int(claim.get("issues"))),
        _summary_part("cc", str(consistency.get("status") or ""), "", _safe_int(consistency.get("issues"))),
        _summary_part("negneutral", str(boundary.get("status") or ""), str(boundary.get("claim_boundary_severity") or ""), 0)
        if boundary.get("publishable") is True
        else "",
    ]
    return " ".join(item for item in parts if item) or "-"


def _summary_part(name: str, status: str, detail: str, issues: int) -> str:
    if not status and not detail:
        return ""
    suffix = f"/{detail}" if detail else ""
    issue_suffix = f":{issues}" if issues else ""
    return f"{name}={status or '-'}{suffix}{issue_suffix}"


def _paper_grade_detail(value: dict[str, Any]) -> str:
    if not value:
        return "-"
    parts = []
    for key in ["status", "grade", "mode"]:
        text = str(value.get(key) or "").strip()
        if text:
            parts.append(text)
    if value.get("score") is not None:
        parts.append(f"score={float(value.get('score') or 0.0):.3f}")
    parts.append(f"issues={_safe_int(value.get('issues'))}")
    return " / ".join(parts)


def _recommended_actions(status: str) -> list[str]:
    if status == "blocked":
        return [
            "先处理阻断项，不要把当前 ZIP 标记为最终可提交版本。",
            "从对应 checkpoint 或 repair queue 恢复后重新生成最终审计与 handoff。",
        ]
    if status == "ready_for_human_handoff":
        return [
            "人工核对 ZIP、scorecard、完整性审计、paper-grade 摘要和 submission checklist。",
            "如需离线包内包含最终完整性审计快照，重新生成投稿包或附上 14-run-integrity-audit.*。",
        ]
    return [
        "人工下载并核验 ZIP。",
        "按目标 venue 官方要求上传正文、参考文献、图、补充材料和代码/数据链接。",
    ]


def _topic_from(package: dict[str, Any], scorecard: dict[str, Any], integrity: dict[str, Any], run_dir: Path) -> str:
    return str(package.get("topic") or scorecard.get("topic") or integrity.get("topic") or run_dir.name)


def _status_field(data: dict[str, Any]) -> str:
    return str(data.get("status") or "").strip()


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prefixed_items(prefix: str, values: Any, limit: int = 6) -> list[str]:
    if not isinstance(values, list):
        return []
    return [f"{prefix}: {str(item).strip()}" for item in values[:limit] if str(item).strip()]


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
