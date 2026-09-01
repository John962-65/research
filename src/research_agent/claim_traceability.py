from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text
from .models import ClaimTraceabilityItem, ClaimTraceabilityReport, LiteratureContext, PaperClaimAudit, PaperReview


CLAIM_TRACEABILITY_JSON = "10-claim-traceability.json"
CLAIM_TRACEABILITY_MD = "10-claim-traceability.md"


def write_claim_traceability_artifacts(
    topic: str,
    run_dir: Path,
    revised_review: PaperReview,
    context: LiteratureContext,
) -> ClaimTraceabilityReport:
    report = build_claim_traceability_report(topic, run_dir, revised_review, context)
    write_json(run_dir / CLAIM_TRACEABILITY_JSON, report)
    write_text(run_dir / CLAIM_TRACEABILITY_MD, render_claim_traceability_markdown(report))
    return report


def build_claim_traceability_report(
    topic: str,
    run_dir: Path,
    revised_review: PaperReview,
    context: LiteratureContext,
) -> ClaimTraceabilityReport:
    inventory = _evidence_inventory(run_dir, context)
    items = [_trace_claim(item, inventory) for item in revised_review.claim_audit]
    total = len(items)
    passed = sum(1 for item in items if item.decision == "pass")
    review = sum(1 for item in items if item.decision == "review")
    blocked = sum(1 for item in items if item.decision == "block")
    score = round((passed + review * 0.45) / total, 3) if total else 0.0
    status = "block" if blocked or not total else "review_required" if review or score < 0.85 else "pass"
    blocking = _blocking_issues(items, total)
    manual = _manual_tasks(items, status)
    return ClaimTraceabilityReport(
        topic=topic,
        status=status,
        traceability_score=score,
        total_claims=total,
        passed_claims=passed,
        review_claims=review,
        blocked_claims=blocked,
        items=items,
        blocking_issues=blocking,
        manual_tasks=manual,
        evidence_inventory={
            "citations": len(inventory["citation_keys"]),
            "result_refs": len(inventory["result_refs"]),
            "has_results": bool(inventory["has_results"]),
            "has_statistics": bool(inventory["has_statistics"]),
            "has_runbook": bool(inventory["has_runbook"]),
            "execution_mode": str(inventory["execution_mode"]),
        },
    )


def render_claim_traceability_markdown(report: ClaimTraceabilityReport) -> str:
    lines = [
        f"# Claim Traceability：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 分数：{report.traceability_score:.3f}",
        f"- Claims：{report.total_claims}",
        f"- 通过/复核/阻断：{report.passed_claims}/{report.review_claims}/{report.blocked_claims}",
        f"- 引用数：{report.evidence_inventory.get('citations', 0)}",
        f"- 结果引用数：{report.evidence_inventory.get('result_refs', 0)}",
        f"- 实验模式：{report.evidence_inventory.get('execution_mode') or '-'}",
        "",
        "## 阻断问题",
    ]
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(
        [
            "",
            "## Traceability Matrix",
            "| 决策 | 支撑 | Citation | Result | Runbook | Claim | 文献 | 结果 | 问题 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.items:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.decision,
                    item.support_level,
                    item.citation_status,
                    item.result_status,
                    item.runbook_status,
                    _cell(item.claim),
                    _cell(", ".join(item.evidence_keys) or "-"),
                    _cell(", ".join(item.result_refs) or "-"),
                    _cell("；".join(item.issues) or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _trace_claim(claim: PaperClaimAudit, inventory: dict[str, Any]) -> ClaimTraceabilityItem:
    paper_text = str(inventory.get("paper_text") or "")
    if claim.support_level == "unsupported" and paper_text and not _claim_asserted_in_paper(claim.claim, paper_text):
        return ClaimTraceabilityItem(
            claim=claim.claim,
            support_level=claim.support_level,
            decision="pass",
            citation_status="not_required",
            result_status="not_required",
            runbook_status="not_required",
            evidence_keys=claim.evidence_keys,
            missing_evidence_keys=[],
            result_refs=claim.result_refs,
            matched_result_refs=[],
            issues=["reviewer unsupported claim is not asserted in revised paper"],
        )
    if _is_evidence_gap_or_boundary_claim(claim.claim):
        return ClaimTraceabilityItem(
            claim=claim.claim,
            support_level=claim.support_level,
            decision="pass",
            citation_status="not_required",
            result_status="not_required",
            runbook_status="not_required",
            evidence_keys=claim.evidence_keys,
            missing_evidence_keys=[],
            result_refs=claim.result_refs,
            matched_result_refs=[],
            issues=["evidence-gap or boundary statement does not assert empirical performance"],
        )
    citation_keys = set(inventory["citation_keys"])
    result_refs = set(inventory["result_refs"])
    missing_keys = [key for key in claim.evidence_keys if key not in citation_keys]
    empirical = _is_empirical_claim(claim.claim, claim.result_refs)
    matched_refs = _matched_result_refs(claim.result_refs, inventory)
    if empirical and not matched_refs and not claim.result_refs:
        implicit_ref = _implicit_result_ref(claim.claim, inventory)
        if implicit_ref:
            matched_refs = [implicit_ref]
    citation_status = _citation_status(claim, missing_keys, empirical)
    result_status = _result_status(claim, matched_refs, empirical)
    runbook_status = _runbook_status(inventory, empirical)
    issues: list[str] = []
    if claim.support_level == "unsupported":
        issues.append("paper review marked claim as unsupported")
    if missing_keys:
        issues.append("missing citation keys: " + ", ".join(missing_keys[:5]))
    if citation_status == "missing":
        issues.append("claim has no citation evidence")
    if result_status == "missing":
        issues.append("empirical claim has no matched result/statistics reference")
    elif result_status == "weak":
        issues.append("result references are not fully matched to result/statistics artifacts")
    if runbook_status == "missing":
        issues.append("empirical claim lacks experiment runbook evidence")
    elif runbook_status == "simulated":
        issues.append("empirical claim is backed only by simulated experiment evidence")
    decision_support_level = claim.support_level
    if (
        claim.support_level == "weak"
        and (_is_internal_artifact_audit_claim(claim.claim) or _is_internal_scope_or_artifact_claim(claim.claim))
        and result_status == "pass"
        and runbook_status == "pass"
    ):
        decision_support_level = "supported"
    decision = _decision(decision_support_level, citation_status, result_status, runbook_status, issues)
    return ClaimTraceabilityItem(
        claim=claim.claim,
        support_level=claim.support_level,
        decision=decision,
        citation_status=citation_status,
        result_status=result_status,
        runbook_status=runbook_status,
        evidence_keys=claim.evidence_keys,
        missing_evidence_keys=missing_keys,
        result_refs=claim.result_refs,
        matched_result_refs=matched_refs,
        issues=issues,
    )


def _evidence_inventory(run_dir: Path, context: LiteratureContext) -> dict[str, Any]:
    experiment_plan = _read_json(run_dir / "03-experiment-plan.json")
    results = _read_json(run_dir / "04-results.json")
    statistics = _read_json(run_dir / "04-statistics.json")
    analysis = _read_json(run_dir / "05-analysis.json")
    benchmark_evidence = _read_json(run_dir / "04-benchmark-evidence-audit.json")
    benchmark_evidence_markdown = _read_text(run_dir / "04-benchmark-evidence-audit.md")
    runbook = _read_json(run_dir / "04-experiment-runbook.json")
    runbook_markdown = _read_text(run_dir / "04-experiment-runbook.md")
    environment = _read_json(run_dir / "04-environment-snapshot.json")
    environment_markdown = _read_text(run_dir / "04-environment-snapshot.md")
    split_artifact_text = _selected_runbook_artifact_text(run_dir, runbook)
    paper_text = _read_text(run_dir / "09-revised-paper.md")
    result_refs: set[str] = set()
    if isinstance(experiment_plan, dict) and experiment_plan:
        result_refs.add("03-experiment-plan.json")
    if isinstance(results, list):
        result_refs.add("04-results.json")
        for result in results:
            if not isinstance(result, dict):
                continue
            if result.get("name"):
                result_refs.add(str(result["name"]))
            metrics = result.get("metrics")
            if isinstance(metrics, dict):
                result_refs.update(str(key) for key in metrics)
            for artifact in result.get("artifacts", []) if isinstance(result.get("artifacts"), list) else []:
                result_refs.add(str(artifact))
    if isinstance(statistics, dict):
        result_refs.add("04-statistics.json")
        for comparison in statistics.get("comparisons", []) if isinstance(statistics.get("comparisons"), list) else []:
            if isinstance(comparison, dict) and comparison.get("metric"):
                result_refs.add(str(comparison["metric"]))
    if isinstance(runbook, dict) and runbook:
        result_refs.update({"04-experiment-runbook.json", "04-experiment-runbook.md", "04-experiment-runbook.md/json"})
    if isinstance(analysis, dict):
        result_refs.update({"05-analysis.json", "analysis.headline"})
        for row in analysis.get("metric_table", []) if isinstance(analysis.get("metric_table"), list) else []:
            if isinstance(row, dict):
                result_refs.update(str(key) for key in row if key not in {"name", "status"})
    if isinstance(benchmark_evidence, dict):
        result_refs.add("04-benchmark-evidence-audit.json")
        for key in ["status", "evidence_grade", "claim_policy", "results", "comparisons", "repeats"]:
            if key in benchmark_evidence:
                result_refs.add(str(key))
    execution = runbook.get("execution", {}) if isinstance(runbook, dict) and isinstance(runbook.get("execution"), dict) else {}
    evidence_text = "\n".join(
        _json_text(value)
        for value in [experiment_plan, results, statistics, analysis, benchmark_evidence, benchmark_evidence_markdown, runbook, environment, runbook_markdown, environment_markdown, split_artifact_text]
        if value not in ({}, [], "")
    )
    return {
        "citation_keys": {item.key for item in context.citations},
        "result_refs": result_refs,
        "result_ref_norms": {_normalize_result_text(ref) for ref in result_refs},
        "evidence_text_norm": _normalize_result_text(evidence_text),
        "evidence_numbers": _numbers(evidence_text),
        "has_results": isinstance(results, list) and bool(results),
        "has_statistics": isinstance(statistics, dict) and bool(statistics),
        "has_analysis": isinstance(analysis, dict) and bool(analysis),
        "has_runbook": isinstance(runbook, dict) and bool(runbook),
        "execution_mode": str(execution.get("mode") or ""),
        "paper_text": paper_text,
    }


def _matched_result_refs(refs: list[str], inventory: dict[str, Any]) -> list[str]:
    result_refs = set(inventory["result_refs"])
    matched: list[str] = []
    for ref in refs:
        if ref in result_refs or (ref in {"analysis.headline", "05-analysis.json"} and inventory["has_analysis"]):
            matched.append(ref)
        elif _result_ref_supported_by_artifacts(ref, inventory):
            matched.append(ref)
    return matched


def _implicit_result_ref(claim: str, inventory: dict[str, Any]) -> str:
    if not _has_implicit_result_anchor(claim):
        return ""
    if _result_ref_supported_by_artifacts(claim, inventory):
        return "implicit:claim_text_artifact_match"
    return ""


def _has_implicit_result_anchor(claim: str) -> bool:
    lowered = claim.lower()
    if _numbers(claim):
        return True
    anchors = [
        "04-results",
        "04-statistics",
        "04-experiment-runbook",
        "04-benchmark-evidence-audit",
        "evidence_grade",
        "runbook/results/statistics",
        "results/statistics",
        "accuracy=",
        "macro_f1=",
        "error_rate=",
        "repeat=",
        "train/test",
        "sha256",
    ]
    if any(anchor in lowered for anchor in anchors):
        return True
    return bool(re.search(r"\b(candidate|baseline|ablation|reference)\s*=", lowered))


def _result_ref_supported_by_artifacts(ref: str, inventory: dict[str, Any]) -> bool:
    norm = _normalize_result_text(ref)
    if not norm:
        return False
    evidence_norm = str(inventory.get("evidence_text_norm") or "")
    if (len(norm) >= 12 or (_contains_cjk(norm) and len(norm) >= 6)) and norm in evidence_norm:
        return True
    if norm in inventory.get("result_ref_norms", set()):
        return True
    terms = _result_terms(ref)
    matched_terms = [term for term in terms if term in evidence_norm]
    ref_numbers = _numbers(ref)
    evidence_numbers = inventory.get("evidence_numbers", [])
    matched_numbers = [number for number in ref_numbers if _number_present(number, evidence_numbers)]
    if ref_numbers:
        needed_numbers = min(2, len(ref_numbers))
        return len(matched_terms) >= 1 and len(matched_numbers) >= needed_numbers
    return len(matched_terms) >= 2


def _result_terms(text: str) -> set[str]:
    lowered = text.lower().replace("-", "_")
    terms: set[str] = set()
    variants = {
        "candidate": ["candidate", "候选"],
        "baseline": ["baseline", "基线"],
        "ablation": ["ablation", "消融", "退化"],
        "accuracy": ["accuracy", "准确"],
        "macro_f1": ["macro_f1", "macro f1", "macro-f1"],
        "error_rate": ["error_rate", "error rate", "error=", "错误率"],
        "train_cases": ["train_cases", "train case", "train/", "train ", "训练"],
        "test_cases": ["test_cases", "test case", "/test", "test/", "test ", "测试"],
        "class_count": ["class_count", "class count", "setosa", "versicolor", "virginica", "类别", "均衡"],
        "split": ["split", "划分"],
        "split_policy": ["split_policy", "policy", "生成规则"],
        "repeat": ["repeat", "重复", "三次"],
        "ci": ["ci", "confidence interval", "置信区间", "零宽", "区间"],
        "delta": ["delta", "差值", "差异", "没有观测到差异"],
        "runbook": ["runbook"],
        "results": ["results", "04-results", "结果"],
        "statistics": ["statistics", "04-statistics", "统计"],
        "benchmark": ["benchmark"],
        "artifact": ["artifact", "artifacts", "produced_artifacts", "产物"],
        "sha256": ["sha256", "hash"],
        "source_tree": ["source_tree", "aggregate_sha256", "代码快照"],
        "metrics_artifact": ["metrics artifact", "metrics_artifact", "metrics.json", "metrics_path"],
        "data_artifact": ["data/", "data artifact", "iris.data", "数据文件"],
        "grader": ["grader", "grade_iris.py", "评分脚本"],
        "mode": ["mode=", "mode", "模式"],
        "environment": ["environment", "执行环境", "单环境"],
        "python": ["python"],
        "linux": ["linux"],
        "sepal": ["sepal", "sepal_only"],
        "centroid": ["centroid"],
        "knn3": ["knn3", "nearest_neighbor", "nearest neighbor"],
        "smoke": ["smoke"],
        "fixed": ["fixed", "frozen", "固定", "同一"],
    }
    for canonical, needles in variants.items():
        matched_needles = [needle for needle in needles if needle in lowered]
        if matched_needles:
            terms.add(canonical)
            terms.update(_normalize_result_text(needle) for needle in matched_needles if _normalize_result_text(needle))
    return terms


def _number_present(number: float, evidence_numbers: Any) -> bool:
    if not isinstance(evidence_numbers, list):
        return False
    tolerance = max(1e-6, abs(number) * 1e-3)
    return any(abs(number - candidate) <= tolerance for candidate in evidence_numbers)


def _numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(?<![A-Za-z0-9])-?\d+(?:\.\d+)?(?![A-Za-z0-9])", text):
        try:
            values.append(float(match.group(0)))
        except ValueError:
            continue
    return values


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _selected_runbook_artifact_text(run_dir: Path, runbook: Any) -> str:
    if not isinstance(runbook, dict):
        return ""
    artifacts = runbook.get("artifacts") if isinstance(runbook.get("artifacts"), list) else []
    chunks: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        lowered = rel.lower()
        if "split" not in lowered or not lowered.endswith((".json", ".txt")):
            continue
        path = run_dir / rel
        text = _read_text(path)
        if text:
            chunks.append(rel)
            chunks.append(text[:20000])
    return "\n".join(chunks)


def _normalize_result_text(text: str) -> str:
    return re.sub(r"[\s，,。.;；:：!！?？、（）()【】\[\]\"'`/=-]+", "", str(text).lower().replace("-", "_"))


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _citation_status(claim: PaperClaimAudit, missing_keys: list[str], empirical: bool) -> str:
    if missing_keys:
        return "missing"
    if claim.evidence_keys:
        return "pass"
    if claim.result_refs or empirical:
        return "not_required"
    return "missing" if claim.support_level in {"supported", "weak"} else "not_provided"


def _result_status(claim: PaperClaimAudit, matched_refs: list[str], empirical: bool) -> str:
    if not empirical:
        return "not_required"
    if not claim.result_refs and matched_refs:
        return "pass"
    if matched_refs and len(matched_refs) == len(claim.result_refs):
        return "pass"
    if matched_refs:
        return "weak"
    return "missing"


def _runbook_status(inventory: dict[str, Any], empirical: bool) -> str:
    if not empirical:
        return "not_required"
    if not inventory["has_runbook"]:
        return "missing"
    if inventory["execution_mode"] == "simulated":
        return "simulated"
    return "pass"


def _decision(support_level: str, citation_status: str, result_status: str, runbook_status: str, issues: list[str]) -> str:
    if support_level == "unsupported" or citation_status == "missing" or result_status == "missing" or runbook_status == "missing":
        return "block"
    if issues or support_level == "weak" or result_status == "weak" or runbook_status == "simulated":
        return "review"
    return "pass"


def _is_empirical_claim(claim: str, result_refs: list[str]) -> bool:
    lowered = claim.lower()
    if _is_literature_scope_claim(claim):
        return False
    if result_refs:
        return True
    tokens = [
        "result",
        "metric",
        "baseline",
        "success_rate",
        "accuracy",
        "f1",
        "latency",
        "runtime",
        "collision",
        "improve",
        "outperform",
        "结果",
        "显示",
        "优于",
        "高于",
        "低于",
        "提高",
        "降低",
        "实验",
        "指标",
    ]
    return any(token in lowered for token in tokens)


def _is_literature_scope_claim(claim: str) -> bool:
    lowered = claim.lower()
    scope_markers = [
        "文献引用",
        "本文将文献",
        "citation",
        "literature",
        "参考文献",
        "相关文献",
    ]
    background_markers = ["api", "baseline", "背景", "数据来源", "provenance", "来源"]
    non_evidence_markers = ["不用于", "仅用于", "只用于", "限定为", "not used", "not intended"]
    return (
        any(marker in lowered for marker in scope_markers)
        and any(marker in lowered for marker in background_markers)
        and any(marker in lowered for marker in non_evidence_markers)
    )


def _is_evidence_gap_or_boundary_claim(claim: str) -> bool:
    lowered = claim.lower()
    gap_markers = [
        "未提供",
        "没有提供",
        "缺少",
        "不足以",
        "无法证明",
        "不能证明",
        "不构成",
        "does not provide",
        "does not prove",
        "cannot prove",
        "insufficient evidence",
        "not enough evidence",
        "no evidence",
        "missing evidence",
    ]
    evidence_markers = [
        "材料",
        "证据",
        "指标",
        "baseline",
        "sanity baseline",
        "reference check",
        "claim",
        "evidence",
        "metric",
        "result",
    ]
    return any(marker in lowered for marker in gap_markers) and any(marker in lowered for marker in evidence_markers)


def _is_internal_artifact_audit_claim(claim: str) -> bool:
    lowered = claim.lower()
    audit_markers = ["evidence_grade=real_benchmark", "real_benchmark", "产物标记", "内部产物审计", "adapter"]
    evidence_markers = ["runbook", "results", "statistics", "04-results", "04-statistics", "实际执行", "命令实际执行"]
    return any(marker in lowered for marker in audit_markers) and any(marker in lowered for marker in evidence_markers)


def _is_internal_scope_or_artifact_claim(claim: str) -> bool:
    lowered = claim.lower()
    scope_markers = ["单环境", "frozen split", "三次执行", "一致性检查", "内部运行", "内部执行"]
    chain_markers = ["数据加载", "固定划分", "adapter variant", "结果落盘", "统计审计", "可复核链条"]
    artifact_markers = ["代码", "manifest", "实验计划", "结果", "runbook", "statistics", "统计审计", "内部运行产物"]
    return (
        any(marker in lowered for marker in scope_markers)
        or sum(1 for marker in chain_markers if marker in lowered) >= 2
        or ("保存" in lowered and sum(1 for marker in artifact_markers if marker in lowered) >= 3)
    )


def _claim_asserted_in_paper(claim: str, paper_text: str) -> bool:
    claim_norm = _normalize_claim(claim)
    claim_core = _claim_core(claim_norm)
    if not claim_norm:
        return False
    for sentence in _sentences(paper_text):
        if _is_nonassertive_context(sentence):
            continue
        sentence_norm = _normalize_claim(sentence)
        if claim_norm in sentence_norm or (len(sentence_norm) >= 12 and sentence_norm in claim_norm):
            return True
        if len(claim_core) >= 8 and claim_core in sentence_norm:
            return True
    return False


def _claim_core(claim_norm: str) -> str:
    core = claim_norm
    for prefix in ["本文已经证明", "本文证明", "结果显示", "实验显示", "结果表明", "实验表明", "我们证明", "我们发现"]:
        if core.startswith(prefix):
            core = core[len(prefix) :]
            break
    return core


def _is_nonassertive_context(sentence: str) -> bool:
    lowered = sentence.lower()
    markers = [
        "禁止表述",
        "禁用表述",
        "不得声称",
        "不能声称",
        "不应声称",
        "不再声称",
        "未声称",
        "没有声称",
        "未检验",
        "未完成验证",
        "不是本次已检验结果",
        "不构成",
        "不作为",
        "不用于",
        "不能自动外推",
        "尚需",
        "后续扩展",
        "后续工作",
        "下一轮",
        "禁止：",
        "prohibited claim",
        "do not claim",
        "must not claim",
    ]
    return any(marker in lowered for marker in markers)


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？.!?；;])\s*|\n+", text)
    return [item.strip() for item in raw if item.strip() and not item.lstrip().startswith("#")]


def _normalize_claim(text: str) -> str:
    return re.sub(r"[\s，,。.;；:：!！?？、（）()【】\\[\\]\"'`]+", "", text.lower())


def _blocking_issues(items: list[ClaimTraceabilityItem], total: int) -> list[str]:
    if not total:
        return ["修订稿没有可追踪 claim audit，无法确认论文主张是否有证据支撑。"]
    return [f"{item.claim}: {'；'.join(item.issues)}" for item in items if item.decision == "block"]


def _manual_tasks(items: list[ClaimTraceabilityItem], status: str) -> list[str]:
    tasks: list[str] = []
    for item in items:
        if item.decision == "review":
            tasks.append(f"人工复核 claim：{item.claim}")
    if status == "block":
        tasks.append("删除、降级或补证所有 traceability=block 的 claim 后重新运行 resume。")
    elif status == "review_required":
        tasks.append("逐条核对 review claim 的 citation key、结果指标和实验模式边界。")
    return _dedupe(tasks)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip()
