from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

from .artifacts import write_json, write_text
from .models import ClaimConsistencyCheck, ClaimConsistencyReport


CLAIM_CONSISTENCY_JSON = "10-claim-consistency.json"
CLAIM_CONSISTENCY_MD = "10-claim-consistency.md"


_STRONG_POSITIVE_PATTERNS = [
    "证明",
    "证实",
    "验证了",
    "支持假设",
    "显著优于",
    "明显优于",
    "优于 baseline",
    "优于基线",
    "显著提升",
    "稳定提升",
    "全面提升",
    "方法有效",
    "有效性得到",
    "可靠地提升",
    "outperform",
    "outperforms",
    "significantly improves",
    "significant improvement",
    "supports the hypothesis",
    "validates",
    "validated",
    "proves",
    "confirms",
    "demonstrates superiority",
    "superior to baseline",
]

_BOUNDARY_PATTERNS = [
    "结果边界",
    "结论边界",
    "局限",
    "仅",
    "初步",
    "不确定",
    "证据不足",
    "不能",
    "不得",
    "部分支持",
    "负结果",
    "未检验",
    "置信区间",
    "95% ci",
    "ci",
    "跨 0",
    "smoke",
    "simulated",
    "模拟",
    "preliminary",
    "limited",
    "partial",
    "inconclusive",
    "uncertain",
]

_OUTCOME_BOUNDARY_PATTERNS = {
    "partially_supported": ["部分支持", "不确定", "未检验", "混合", "partial", "mixed", "uncertain"],
    "refuted_or_negative": ["负结果", "不支持", "不优于", "未显示优势", "反驳", "negative", "not support", "no advantage"],
    "inconclusive": ["不确定", "证据不足", "无法判断", "inconclusive", "uncertain", "insufficient"],
    "smoke_only": ["smoke", "simulated", "模拟", "烟测", "初步", "preliminary"],
    "untested": ["未检验", "尚未检验", "不得", "不能", "untested"],
    "blocked_unverified": ["阻断", "未验证", "不得", "不能", "blocked", "unverified"],
}

_NEGATION_PATTERNS = ["不能", "不得", "不足以", "无法", "未", "不", "not ", "cannot", "can't", "no "]

_CLAIM_NEGATION_PATTERNS = [
    "不声称",
    "不得声称",
    "不能声称",
    "不应声称",
    "未声称",
    "没有声称",
    "不证明",
    "不能证明",
    "无法证明",
    "不支持",
    "do not claim",
    "does not claim",
    "does not prove",
    "not claim",
    "must not claim",
    "cannot claim",
]

_PROHIBITION_CONTEXT_PATTERNS = [
    "禁止表述",
    "禁用表述",
    "禁止 claim",
    "禁止：",
    "不得声称",
    "不能声称",
    "不应声称",
    "不得写成",
    "不能写成",
    "prohibited claim",
    "prohibited claims",
    "prohibited pattern",
    "prohibited patterns",
    "do not claim",
    "must not claim",
    "weak claim",
    "unsupported claim",
    "问题：weak claim",
    "问题：unsupported claim",
    "问题: weak claim",
    "问题: unsupported claim",
]

_FORMAL_BENCHMARK_CLAIM_PATTERNS = [
    "正式 benchmark",
    "公开 benchmark",
    "标准 benchmark",
    "real benchmark",
    "public benchmark",
    "official benchmark",
    "standard benchmark",
    "benchmark 支持",
    "benchmark support",
    "可泛化",
    "泛化到",
    "广泛任务",
    "generalize",
    "generalizes",
    "generalized",
    "state-of-the-art",
    "sota",
]


def write_claim_consistency_artifacts(topic: str, run_dir: Path) -> ClaimConsistencyReport:
    report = build_claim_consistency_report(topic, run_dir)
    write_json(run_dir / CLAIM_CONSISTENCY_JSON, report)
    write_text(run_dir / CLAIM_CONSISTENCY_MD, render_claim_consistency_markdown(report))
    return report


def build_claim_consistency_report(topic: str, run_dir: Path) -> ClaimConsistencyReport:
    paper_md = _read_text(run_dir / "09-revised-paper.md")
    hypothesis_outcome = _read_json(run_dir / "04-hypothesis-outcome.json")
    benchmark_evidence = _read_json(run_dir / "04-benchmark-evidence-audit.json")
    claim_preflight = _read_json(run_dir / "04-claim-boundary-preflight.json")
    outcome = str(hypothesis_outcome.get("outcome") or "")
    outcome_status = str(hypothesis_outcome.get("status") or "")
    support_score = _safe_float(hypothesis_outcome.get("support_score"))
    benchmark_grade = str(benchmark_evidence.get("evidence_grade") or "")
    benchmark_status = str(benchmark_evidence.get("status") or "")
    claim_preflight_status = str(claim_preflight.get("status") or "")
    strong_claims = _strong_positive_claims(paper_md)
    formal_benchmark_claims = _matching_claims(paper_md, _FORMAL_BENCHMARK_CLAIM_PATTERNS)
    preflight_violations = _preflight_violations(paper_md, claim_preflight)
    checks = [
        _paper_check(paper_md),
        _outcome_check(hypothesis_outcome, outcome, outcome_status, paper_md),
        _overclaim_check(outcome, outcome_status, support_score, strong_claims),
        _benchmark_evidence_check(benchmark_evidence, benchmark_grade, benchmark_status, formal_benchmark_claims, strong_claims, paper_md),
        _claim_preflight_check(claim_preflight, claim_preflight_status, preflight_violations, paper_md),
        _boundary_check(paper_md, outcome, outcome_status),
        _negative_reporting_check(paper_md, outcome),
    ]
    total = len(checks)
    passed = sum(1 for item in checks if item.status == "pass")
    review = sum(1 for item in checks if item.status == "review")
    score = round((passed + review * 0.45) / total, 3) if total else 0.0
    status = _status(checks)
    return ClaimConsistencyReport(
        topic=topic,
        status=status,
        consistency_score=score,
        checks=checks,
        blocking_issues=[f"{item.item}: {item.action}" for item in checks if item.status == "block"],
        manual_tasks=[f"{item.item}: {item.action}" for item in checks if item.status == "review"],
        evidence_inventory={
            "paper_chars": len(paper_md),
            "outcome": outcome,
            "hypothesis_status": outcome_status,
            "benchmark_grade": benchmark_grade,
            "benchmark_status": benchmark_status,
            "claim_preflight_status": claim_preflight_status,
            "support_score": f"{support_score:.3f}",
            "strong_positive_claims": len(strong_claims),
            "formal_benchmark_claims": len(formal_benchmark_claims),
            "claim_preflight_violations": len(preflight_violations),
            "has_boundary_language": _has_boundary_language(paper_md),
            "has_outcome_specific_boundary": _has_outcome_boundary(paper_md, outcome),
        },
    )


def render_claim_consistency_markdown(report: ClaimConsistencyReport) -> str:
    inventory = report.evidence_inventory
    lines = [
        f"# Claim Consistency Audit：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 分数：{report.consistency_score:.3f}",
        f"- 假设结果：{inventory.get('outcome') or '-'} / {inventory.get('hypothesis_status') or '-'}",
        f"- Benchmark 证据：{inventory.get('benchmark_status') or '-'} / {inventory.get('benchmark_grade') or '-'}",
        f"- Claim 预检：{inventory.get('claim_preflight_status') or '-'}",
        f"- 支撑分数：{inventory.get('support_score') or '0.000'}",
        f"- 强正向结论：{inventory.get('strong_positive_claims', 0)}",
        f"- 正式 benchmark 外推表述：{inventory.get('formal_benchmark_claims', 0)}",
        f"- Claim 预检禁用表述：{inventory.get('claim_preflight_violations', 0)}",
        "",
        "## 阻断问题",
    ]
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(
        [
            "",
            "## Consistency Checks",
            "| 类别 | 项目 | 状态 | 证据 | 动作 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.checks:
        lines.append(
            "| "
            + " | ".join([_cell(item.category), _cell(item.item), item.status, _cell(item.evidence), _cell(item.action or "-")])
            + " |"
        )
    return "\n".join(lines)


def _paper_check(paper_md: str) -> ClaimConsistencyCheck:
    if not paper_md.strip():
        return ClaimConsistencyCheck("paper", "修订稿文本", "block", "09-revised-paper.md 缺失或为空", "重新生成修订稿后再做 claim consistency 审计。")
    return ClaimConsistencyCheck("paper", "修订稿文本", "pass", f"{len(paper_md)} chars")


def _outcome_check(data: Any, outcome: str, outcome_status: str, paper_md: str) -> ClaimConsistencyCheck:
    if not isinstance(data, dict) or not data:
        return ClaimConsistencyCheck("hypothesis", "假设结果输入", "block", "缺少 04-hypothesis-outcome.json", "先运行假设结果审计。")
    if outcome_status == "block" or outcome in {"blocked_unverified", "untested"}:
        return ClaimConsistencyCheck(
            "hypothesis",
            "假设结果输入",
            "block",
            f"outcome={outcome or '-'}; status={outcome_status or '-'}",
            "先修复未检验或被阻断的 hypothesis outcome，再允许论文主张效果。",
        )
    if outcome == "refuted_or_negative" and _has_outcome_boundary(paper_md, outcome):
        return ClaimConsistencyCheck("hypothesis", "假设结果输入", "pass", f"outcome={outcome}; status={outcome_status or '-'}; negative boundary present")
    if outcome in {"partially_supported", "refuted_or_negative", "inconclusive", "smoke_only"} or outcome_status == "review_required":
        return ClaimConsistencyCheck("hypothesis", "假设结果输入", "review", f"outcome={outcome or '-'}; status={outcome_status or '-'}", "论文必须使用保守表述并写明结果边界。")
    return ClaimConsistencyCheck("hypothesis", "假设结果输入", "pass", f"outcome={outcome or 'supported'}; status={outcome_status or 'pass'}")


def _overclaim_check(outcome: str, outcome_status: str, support_score: float, strong_claims: list[str]) -> ClaimConsistencyCheck:
    if not strong_claims:
        return ClaimConsistencyCheck("claims", "过强正向结论", "pass", "未检测到证明/显著优于/支持假设等强正向表述")
    sample = "；".join(strong_claims[:3])
    if outcome in {"smoke_only", "refuted_or_negative", "inconclusive", "untested", "blocked_unverified"} or outcome_status == "block":
        return ClaimConsistencyCheck(
            "claims",
            "过强正向结论",
            "block",
            f"outcome={outcome or '-'}; strong_claims={len(strong_claims)}; examples={sample}",
            "删除或降级强正向结论，把结论改成 smoke/负结果/不确定/未检验对应边界。",
        )
    if outcome == "partially_supported" or outcome_status == "review_required" or support_score < 0.7:
        return ClaimConsistencyCheck(
            "claims",
            "过强正向结论",
            "review",
            f"outcome={outcome or '-'}; score={support_score:.2f}; strong_claims={len(strong_claims)}; examples={sample}",
            "人工核对这些强正向句是否逐项限定到已支持指标，避免概括为整体支持。",
        )
    return ClaimConsistencyCheck("claims", "过强正向结论", "pass", f"supported outcome with {len(strong_claims)} strong positive claim(s)")


def _benchmark_evidence_check(
    benchmark_evidence: Any,
    benchmark_grade: str,
    benchmark_status: str,
    formal_benchmark_claims: list[str],
    strong_claims: list[str],
    paper_md: str,
) -> ClaimConsistencyCheck:
    if not isinstance(benchmark_evidence, dict) or not benchmark_evidence:
        return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "pass", "缺少 04-benchmark-evidence-audit.json；由 submission check/scorecard 处理缺失审计")
    if benchmark_status == "block" or benchmark_grade == "blocked":
        return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "block", f"benchmark_grade={benchmark_grade or '-'}; status={benchmark_status or '-'}", "先修复 benchmark evidence audit 阻断项，不得保留效果主张。")
    if benchmark_grade == "real_benchmark":
        return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "pass", f"benchmark_grade={benchmark_grade}; formal_benchmark_claims={len(formal_benchmark_claims)}")
    if benchmark_grade == "smoke_only":
        if strong_claims or formal_benchmark_claims:
            examples = "；".join([*formal_benchmark_claims, *strong_claims][:3])
            return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "block", f"benchmark_grade=smoke_only; examples={examples}", "smoke_only 证据只能写流程验证或初步趋势，删除正式 benchmark/强效果结论。")
        if not _has_boundary_language(paper_md):
            return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "review", "benchmark_grade=smoke_only; 正文缺少 smoke/preliminary 边界", "补写结果边界，明确当前仅为 smoke/preliminary evidence。")
        return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "pass", "smoke_only evidence with boundary language")
    if benchmark_grade == "local_experiment":
        if formal_benchmark_claims:
            examples = "；".join(formal_benchmark_claims[:3])
            return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "block", f"benchmark_grade=local_experiment; formal_benchmark_claims={len(formal_benchmark_claims)}; examples={examples}", "local_experiment 不得写成公开/正式 benchmark 或泛化任务族结论。")
        if strong_claims and not _has_boundary_language(paper_md):
            examples = "；".join(strong_claims[:3])
            return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "block", f"benchmark_grade=local_experiment; strong_claims={len(strong_claims)}; examples={examples}", "保留强效果句前必须明确 local evidence 和结果边界；否则删除或降级。")
        if not _has_boundary_language(paper_md):
            return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "review", "benchmark_grade=local_experiment; 正文缺少 local evidence 边界", "补写结果边界，说明证据限于本地任务、seed、baseline 和运行环境。")
        return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "pass", "local_experiment evidence with boundary language")
    return ClaimConsistencyCheck("claims", "Benchmark 证据等级", "review", f"benchmark_grade={benchmark_grade or '-'}; status={benchmark_status or '-'}", "人工确认正文 claim 与 benchmark evidence grade 一致。")


def _claim_preflight_check(claim_preflight: Any, status: str, violations: list[str], paper_md: str) -> ClaimConsistencyCheck:
    if not isinstance(claim_preflight, dict) or not claim_preflight:
        return ClaimConsistencyCheck("claims", "Claim 预检禁用表述", "pass", "缺少 04-claim-boundary-preflight.json；由 submission check/scorecard 处理缺失审计")
    if violations:
        examples = "；".join(violations[:3])
        return ClaimConsistencyCheck("claims", "Claim 预检禁用表述", "block", f"status={status or '-'}; violations={len(violations)}; examples={examples}", "删除或改写 04-claim-boundary-preflight 禁止的 claim 表述。")
    if status == "block":
        return ClaimConsistencyCheck("claims", "Claim 预检禁用表述", "block", "claim preflight status=block", "先处理 claim boundary preflight 阻断项，再重新生成修订稿。")
    if status == "review_required" and not _has_boundary_language(paper_md):
        return ClaimConsistencyCheck("claims", "Claim 预检禁用表述", "review", "claim preflight review_required; 正文缺少边界语言", "补写结果边界并响应 allowed/prohibited claim。")
    return ClaimConsistencyCheck("claims", "Claim 预检禁用表述", "pass", f"status={status or 'pass'}; violations=0")


def _boundary_check(paper_md: str, outcome: str, outcome_status: str) -> ClaimConsistencyCheck:
    if outcome in {"", "supported"} and outcome_status not in {"review_required", "block"}:
        return ClaimConsistencyCheck("claims", "结果边界一致性", "pass", "假设结果为 supported，未强制要求额外边界语言")
    if _has_outcome_boundary(paper_md, outcome):
        return ClaimConsistencyCheck("claims", "结果边界一致性", "pass", f"正文包含与 {outcome or 'review'} 对应的边界语言")
    if _has_boundary_language(paper_md):
        return ClaimConsistencyCheck(
            "claims",
            "结果边界一致性",
            "review",
            "正文有一般边界语言，但没有明确响应该 outcome",
            f"在结果边界或结论中点名写出 {outcome or 'review_required'} 的证据等级。",
        )
    return ClaimConsistencyCheck(
        "claims",
        "结果边界一致性",
        "review",
        "正文缺少结果边界/局限/不确定性等保守表述",
        f"为 {outcome or 'review_required'} outcome 补写结果边界，避免读者误解为正式支持。",
    )


def _negative_reporting_check(paper_md: str, outcome: str) -> ClaimConsistencyCheck:
    if outcome != "refuted_or_negative":
        return ClaimConsistencyCheck("claims", "负结果报告", "pass", "非 refuted_or_negative outcome")
    if _contains_any(paper_md, _OUTCOME_BOUNDARY_PATTERNS["refuted_or_negative"]):
        return ClaimConsistencyCheck("claims", "负结果报告", "pass", "正文检测到负结果/不支持/不优于等表述")
    return ClaimConsistencyCheck(
        "claims",
        "负结果报告",
        "review",
        "hypothesis outcome 为 refuted_or_negative，但正文没有显式负结果语言",
        "在结果和结论中报告负结果，不要只写方法潜力。",
    )


def _strong_positive_claims(text: str) -> list[str]:
    return _matching_claims(text, _STRONG_POSITIVE_PATTERNS)


def _matching_claims(text: str, patterns: list[str]) -> list[str]:
    claims: list[str] = []
    for sentence in _sentences(text):
        if _is_prohibition_context(sentence):
            continue
        lowered = sentence.lower()
        for pattern in patterns:
            index = lowered.find(pattern.lower())
            if index < 0 or _is_negated(sentence, index):
                continue
            claims.append(sentence.strip())
            break
    return _unique(claims)


def _preflight_violations(text: str, claim_preflight: Any) -> list[str]:
    if not isinstance(claim_preflight, dict):
        return []
    patterns = [str(item).strip() for item in claim_preflight.get("prohibited_patterns", []) if str(item).strip()] if isinstance(claim_preflight.get("prohibited_patterns"), list) else []
    if not patterns:
        return []
    return _matching_claims(text, patterns)


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    return [item.strip() for item in raw if item.strip() and not item.lstrip().startswith("#")]


def _is_negated(sentence: str, index: int) -> bool:
    limited_window = sentence[max(0, index - 4) : index + 32].lower()
    if "仅" in limited_window[:4] and _contains_any(sentence[index:], ["不证明", "不能证明", "不支持", "不构成", "不能推断"]):
        return True
    local_window = sentence[max(0, index - 14) : index].lower()
    if any(pattern in local_window for pattern in _NEGATION_PATTERNS):
        return True
    claim_window = sentence[max(0, index - 48) : index].lower()
    return any(pattern in claim_window for pattern in _CLAIM_NEGATION_PATTERNS)


def _is_prohibition_context(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(pattern in lowered for pattern in _PROHIBITION_CONTEXT_PATTERNS)


def _has_boundary_language(text: str) -> bool:
    return _contains_any(text, _BOUNDARY_PATTERNS)


def _has_outcome_boundary(text: str, outcome: str) -> bool:
    patterns = _OUTCOME_BOUNDARY_PATTERNS.get(outcome, [])
    return _contains_any(text, patterns) if patterns else False


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def _status(checks: list[ClaimConsistencyCheck]) -> str:
    if any(item.status == "block" for item in checks):
        return "block"
    if any(item.status == "review" for item in checks):
        return "review_required"
    return "pass"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
