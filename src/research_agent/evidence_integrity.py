from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from .artifacts import write_json, write_text, safe_int as _safe_int


EVIDENCE_INTEGRITY_JSON = "04-evidence-integrity.json"
EVIDENCE_INTEGRITY_MD = "04-evidence-integrity.md"

# 这些实验 status 表示结果不是真实执行得来的（模拟器/占位/冒烟），不能作为科学证据。
_NON_REAL_STATUSES = {"", "simulated", "mock", "synthetic", "smoke", "placeholder", "dry_run", "skipped"}


@dataclass(frozen=True)
class EvidenceIntegrity:
    """本次 run 的证据真实性信号：是否真接了 LLM、实验是否真实执行。

    这是防止"严谨包装的假数据被当成科学结论投出去"的核心闸门。论文写作和
    最终就绪判定都消费这个信号；证据不足时强制声明、禁止断言、阻断投稿。
    """

    real_llm: bool
    real_experiment: bool
    llm_calls: int
    real_result_count: int
    simulated_result_count: int
    experiment_statuses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def publishable_evidence(self) -> bool:
        """是否具备支撑正式科学结论的证据：必须既有真实 LLM 又有真实实验。"""
        return self.real_llm and self.real_experiment

    @property
    def simulated_only(self) -> bool:
        """有实验结果但无一为真实执行。"""
        return self.simulated_result_count > 0 and not self.real_experiment

    @property
    def status(self) -> str:
        if self.publishable_evidence:
            return "real_evidence"
        if not self.real_llm and not self.real_experiment:
            return "no_real_evidence"
        return "partial_real_evidence"


def assess_evidence_integrity(run_dir: Path) -> EvidenceIntegrity:
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    if isinstance(ledger, dict):
        llm_calls = _safe_int(ledger.get("successful_calls")) or _safe_int(ledger.get("total_calls"))
    else:
        llm_calls = 0
    real_llm = llm_calls > 0

    results = _read_json(run_dir / "04-results.json")
    rows = results if isinstance(results, list) else []
    statuses = [str(row.get("status") or "").strip().lower() for row in rows if isinstance(row, dict)]
    real_result_count = sum(1 for status in statuses if status and status not in _NON_REAL_STATUSES)
    simulated_result_count = sum(1 for status in statuses if status in _NON_REAL_STATUSES)
    real_experiment = real_result_count > 0

    notes: list[str] = []
    if not real_llm:
        notes.append(
            "未检测到成功的真实 LLM 调用（run-llm-ledger.json 缺失或调用数为 0）；"
            "本 run 的文本可能来自离线兜底，不能作为模型推理证据。"
        )
    if not real_experiment:
        if statuses:
            notes.append("实验结果全部为模拟/占位状态；任何性能数字都不能作为科学结论。")
        else:
            notes.append("未发现任何实验结果（04-results.json 缺失或为空）。")

    return EvidenceIntegrity(
        real_llm=real_llm,
        real_experiment=real_experiment,
        llm_calls=llm_calls,
        real_result_count=real_result_count,
        simulated_result_count=simulated_result_count,
        experiment_statuses=sorted({status for status in statuses if status}),
        notes=notes,
    )


def evidence_integrity_banner(integrity: EvidenceIntegrity | None) -> str:
    """论文顶部的不可忽略横幅；证据充分时返回空串。"""
    if integrity is None or integrity.publishable_evidence:
        return ""
    reasons: list[str] = []
    if not integrity.real_llm:
        reasons.append("未接入真实 LLM（文本可能来自离线兜底）")
    if not integrity.real_experiment:
        reasons.append("实验结果为模拟/占位数据")
    return (
        "> ⚠️ **诚实性声明：本稿为流水线演示，不能作为科学结论或投稿稿。**\n"
        f">\n> 原因：{'；'.join(reasons)}。"
        "正文中关于方法有效性、性能数字和与 baseline 的比较结论均**不被真实证据支持**，"
        "仅用于展示流水线结构与可复现骨架。正式研究须接入真实 LLM 与真实 benchmark 后重跑。"
    )


def evidence_integrity_prompt_constraint(integrity: EvidenceIntegrity | None) -> str:
    """注入论文 LLM 写作 prompt 的强制诚实性约束；证据充分时返回空串。"""
    if integrity is None or integrity.publishable_evidence:
        return ""
    gaps: list[str] = []
    if not integrity.real_experiment:
        gaps.append("实验结果为模拟/占位数据")
    if not integrity.real_llm:
        gaps.append("未接入真实 LLM")
    return (
        "【强制诚实性约束（最高优先级，覆盖其他写作目标）】"
        f"本 run 的证据不足以支持正式科学结论：{'；'.join(gaps)}。因此你必须："
        "(1) 标题结尾追加“（模拟原型）”；"
        "(2) 摘要第一句声明结果基于模拟/占位数据、不能支持正式科学结论；"
        "(3) 禁止任何关于方法有效性、优越于 baseline、因果或可泛化的断言，所有性能数字必须显式标注“（模拟）”；"
        "(4) 结论小节必须明确说明正式结论需替换为真实数据与真实实验后重跑。"
        "违反以上任一条都视为不合格输出。"
    )


def write_evidence_integrity_artifacts(topic: str, run_dir: Path) -> EvidenceIntegrity:
    integrity = assess_evidence_integrity(run_dir)
    write_json(run_dir / EVIDENCE_INTEGRITY_JSON, _to_dict(topic, integrity))
    write_text(run_dir / EVIDENCE_INTEGRITY_MD, render_evidence_integrity_markdown(topic, integrity))
    return integrity


def render_evidence_integrity_markdown(topic: str, integrity: EvidenceIntegrity) -> str:
    lines = [
        f"# 证据真实性审计：{topic}",
        "",
        f"- 状态：{integrity.status}",
        f"- 可支撑正式结论：{'yes' if integrity.publishable_evidence else 'no'}",
        f"- 真实 LLM 调用：{'yes' if integrity.real_llm else 'no'}（成功调用 {integrity.llm_calls}）",
        f"- 真实实验结果：{'yes' if integrity.real_experiment else 'no'}"
        f"（真实 {integrity.real_result_count} / 模拟 {integrity.simulated_result_count}）",
        f"- 实验状态取值：{', '.join(integrity.experiment_statuses) if integrity.experiment_statuses else '无'}",
        "",
        "## 说明",
    ]
    lines.extend(f"- {note}" for note in integrity.notes) if integrity.notes else lines.append(
        "- 证据真实，未发现真实性阻断。"
    )
    return "\n".join(lines)


def _to_dict(topic: str, integrity: EvidenceIntegrity) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "topic": topic,
        "status": integrity.status,
        "publishable_evidence": integrity.publishable_evidence,
        "real_llm": integrity.real_llm,
        "real_experiment": integrity.real_experiment,
        "simulated_only": integrity.simulated_only,
        "llm_calls": integrity.llm_calls,
        "real_result_count": integrity.real_result_count,
        "simulated_result_count": integrity.simulated_result_count,
        "experiment_statuses": integrity.experiment_statuses,
        "notes": integrity.notes,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


