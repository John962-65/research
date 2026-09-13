from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import math

from .artifacts import write_json, write_text, safe_int as _safe_int


EVIDENCE_INTEGRITY_JSON = "04-evidence-integrity.json"
EVIDENCE_INTEGRITY_MD = "04-evidence-integrity.md"

# decision-contract §1：四类证据状态 verified/incomplete/invalid/simulated/unknown。
# 实验结果状态白名单（冻结）：只有这些 status 表示真实执行完成；失败/超时/阻断
# 是"真实执行尝试"，保留记录但不能进入结论；simulated 族来自模拟器。
_COMPLETED_RESULT_STATUSES = {"passed", "completed"}
_ATTEMPT_RESULT_STATUSES = {"failed", "timeout", "timed_out", "blocked", "cancelled"}
_SIMULATED_RESULT_STATUSES = {"simulated", "mock", "synthetic", "smoke", "placeholder", "dry_run", "skipped"}

# 成功调用只有落到本 run 实际存在的阶段产物上，才算"被产物引用"。
_STAGE_ARTIFACTS = {
    "research_planning": "00-research-plan.json",
    "literature_synthesis": "01-literature.json",
    "idea_generation": "02-ideas.json",
    "experiment_planning": "03-experiment-plan.json",
    "paper_writing": "06-paper.md",
    "paper_review_loop": "07-paper-review.json",
    "paper_revision": "09-revised-paper.md",
    "paper_deliberation": "10-independent-deliberation.json",
}


@dataclass(frozen=True)
class EvidenceIntegrity:
    """本次 run 的证据真实性信号（schema_version=2）。

    LLM 证据与实验证据是两个独立维度：有真实模型调用不等于有真实实验；
    有真实实验也不要求报告必须由模型生成（decision-contract §1.2）。
    real_llm/real_experiment/status 为兼容字段：real_experiment 只在实验
    证据维度 verified 时为真；status=real_evidence 仅表示两个维度同时
    verified，不代表任何具体指标或论文主张已被核验。
    """

    real_llm: bool
    real_experiment: bool
    llm_calls: int
    real_result_count: int
    simulated_result_count: int
    experiment_statuses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    schema_version: int = 2
    llm_attempted_calls: int = 0
    llm_successful_calls: int = 0
    llm_valid_responses: int = 0
    llm_referenced_calls: int = 0
    llm_evidence_status: str = "unknown"
    experiment_evidence_status: str = "unknown"
    real_attempt_count: int = 0
    unusable_result_reasons: list[str] = field(default_factory=list)

    @property
    def publishable_evidence(self) -> bool:
        """兼容字段：两个证据维度同时 verified；不等于论文达到发表标准。"""
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
    run_dir = Path(run_dir)
    llm = _assess_llm_evidence(run_dir)
    experiment = _assess_experiment_evidence(run_dir)

    real_llm = llm["status"] == "verified"
    real_experiment = experiment["status"] == "verified"
    notes: list[str] = [*llm["notes"], *experiment["notes"]]

    return EvidenceIntegrity(
        real_llm=real_llm,
        real_experiment=real_experiment,
        llm_calls=llm["successful"],
        real_result_count=experiment["verified_count"],
        simulated_result_count=experiment["simulated_count"],
        experiment_statuses=experiment["statuses"],
        notes=notes,
        llm_attempted_calls=llm["attempted"],
        llm_successful_calls=llm["successful"],
        llm_valid_responses=llm["valid"],
        llm_referenced_calls=llm["referenced"],
        llm_evidence_status=llm["status"],
        experiment_evidence_status=experiment["status"],
        real_attempt_count=experiment["attempt_count"],
        unusable_result_reasons=experiment["reasons"],
    )


def _assess_llm_evidence(run_dir: Path) -> dict[str, Any]:
    """分开统计调用尝试数、成功响应数、结构有效响应数、被产物引用数。

    只信逐条 entries；缺失 entries 的旧/汇总账本按 incomplete 处理，
    不能用 total_calls 冒充成功调用数（A01）。
    """
    ledger = _read_json(run_dir / "run-llm-ledger.json")
    entries = ledger.get("entries") if isinstance(ledger, dict) else None
    notes: list[str] = []
    if not isinstance(entries, list):
        attempted = _safe_int((ledger or {}).get("total_calls")) if isinstance(ledger, dict) else 0
        if attempted <= 0:
            notes.append(
                "未检测到成功的真实 LLM 调用（run-llm-ledger.json 缺失或调用数为 0）；"
                "本 run 的文本可能来自离线兜底，不能作为模型推理证据。"
            )
            return {"status": "unknown", "attempted": 0, "successful": 0, "valid": 0, "referenced": 0, "notes": notes}
        notes.append(
            "run-llm-ledger.json 只有汇总计数、缺少逐条调用记录，无法核验每次调用；"
            "按 incomplete 处理。补充动作：用当前版本重跑以生成完整账本。"
        )
        return {"status": "incomplete", "attempted": attempted, "successful": 0, "valid": 0, "referenced": 0, "notes": notes}

    attempted = len(entries)
    successful = 0
    invalid_responses = 0
    referenced = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "").strip().lower()
        if status == "success":
            successful += 1
            artifact = _STAGE_ARTIFACTS.get(str(entry.get("stage") or ""))
            if artifact and (run_dir / artifact).exists():
                referenced += 1
        elif status == "invalid_response":
            invalid_responses += 1
    if attempted == 0:
        notes.append("调用账本为空：本 run 没有任何模型调用记录。")
        status_value = "unknown"
    elif successful > 0:
        status_value = "verified"
        if invalid_responses:
            notes.append(
                f"存在 {invalid_responses} 条结构无效的模型响应，已与成功响应分开计数；"
                "无效响应不得作为任何产物来源。"
            )
        if successful > referenced:
            notes.append(
                f"成功调用 {successful} 次中仅 {referenced} 次能定位到本 run 现存产物；"
                "未定位部分保留记录但需人工确认其用途。"
            )
    elif invalid_responses and invalid_responses == attempted:
        status_value = "invalid"
        notes.append(
            "全部模型响应均为结构无效，不能作为任何产物的来源。"
            "补充动作：检查模型端点返回格式与解析逻辑后重跑。"
        )
    else:
        status_value = "incomplete"
        notes.append(
            f"模型调用尝试 {attempted} 次、成功 0 次（失败/预算/其他 {attempted} 次）；"
            "不存在可用的模型产物。补充动作：检查凭据、预算与端点后重跑。"
        )
    return {
        "status": status_value,
        "attempted": attempted,
        "successful": successful,
        "valid": successful,
        "referenced": referenced,
        "notes": notes,
    }


def _assess_experiment_evidence(run_dir: Path) -> dict[str, Any]:
    """按白名单分辨实验结果：verified 需完成状态 + 有限指标 + 来源绑定。"""
    results = _read_json(run_dir / "04-results.json")
    rows = results if isinstance(results, list) else []
    notes: list[str] = []
    reasons: list[str] = []
    statuses: list[str] = []
    verified_count = 0
    simulated_count = 0
    attempt_count = 0
    completed_rows = 0
    if not rows:
        notes.append("未发现任何实验结果（04-results.json 缺失或为空）。")
        return {
            "status": "unknown",
            "verified_count": 0,
            "simulated_count": 0,
            "attempt_count": 0,
            "statuses": [],
            "reasons": [],
            "notes": notes,
        }
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status:
            statuses.append(status)
        if status in _COMPLETED_RESULT_STATUSES:
            completed_rows += 1
            problems = _result_row_problems(row, run_dir)
            if problems:
                reasons.extend(problems)
            else:
                verified_count += 1
        elif status in _ATTEMPT_RESULT_STATUSES:
            attempt_count += 1
        elif status in _SIMULATED_RESULT_STATUSES:
            simulated_count += 1

    if verified_count > 0:
        status_value = "verified"
        if simulated_count:
            notes.append(
                f"结果混合真实与模拟：真实可用 {verified_count} 条、模拟 {simulated_count} 条；"
                "模拟行已逐条分开计数，不得进入真实效果结论的汇总。"
            )
        if attempt_count:
            notes.append(
                f"另有 {attempt_count} 条失败/超时/阻断的真实执行尝试，仅保留记录，不参与结论。"
            )
        if reasons:
            status_value = "incomplete"
            notes.append("部分完成结果缺少可用指标或来源绑定，已降级为 incomplete。")
    elif completed_rows > 0:
        status_value = "invalid" if any("非有限" in reason or "NaN" in reason for reason in reasons) else "incomplete"
        notes.append(
            "存在完成状态的结果行，但全部缺少可用指标或来源绑定，不能判 verified。"
            "补充动作：" + "；".join(reasons[:3])
        )
    elif attempt_count > 0:
        status_value = "incomplete"
        notes.append(
            f"仅有 {attempt_count} 条失败/超时/阻断的真实执行尝试，没有任何可用实验结果；"
            "这些记录保留为执行证据，但不能支撑任何研究结论。"
            "补充动作：修复执行问题后重跑。"
        )
        if simulated_count:
            notes.append(f"同 run 另有 {simulated_count} 条模拟结果，已与真实尝试分开计数。")
    elif simulated_count > 0:
        status_value = "simulated"
        notes.append("实验结果全部为模拟/占位状态；任何性能数字都不能作为科学结论。")
    else:
        status_value = "unknown"
        notes.append(
            "04-results.json 存在，但状态取值不在已知的白名单/尝试/模拟集合内；"
            "按 unknown 处理。补充动作：核对结果文件来源与结构。"
        )
    return {
        "status": status_value,
        "verified_count": verified_count,
        "simulated_count": simulated_count,
        "attempt_count": attempt_count,
        "statuses": sorted({status for status in statuses if status}),
        "reasons": reasons,
        "notes": notes,
    }


def _result_row_problems(row: dict[str, Any], run_dir: Path) -> list[str]:
    """单条完成结果行的校验：指标非空、全部有限数值、来源可核验。

    复审第 3 项："有产物路径/退出码为零/有命令"只是导入者声明，不等于
    系统核验过执行产物。verified 要求产物文件真实存在于 run 目录且
    （声明了 sha256 时）内容哈希一致；否则按 incomplete 处理。
    """
    name = str(row.get("name") or f"row#{row.get('repeat_index', '?')}")
    problems: list[str] = []
    metrics = row.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        problems.append(f"{name}: 无任何指标")
        return problems
    for key, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            problems.append(f"{name}: 指标 {key} 非有限数值（NaN/Inf/非数值）")
    records = row.get("artifact_records")
    record_list = [item for item in (records if isinstance(records, list) else []) if isinstance(item, dict)]
    if not record_list:
        problems.append(f"{name}: 来源不可核验（无任何产物记录；声明字段不构成核验）")
        return problems
    # 复审第 9 轮第 3 项：文件身份（存在+哈希）只证明文件完整，不证明
    # 报告的指标数值来自该文件。必须从产物重新提取并核对每个指标。
    any_verifiable = False
    any_content_checked = False
    for record in record_list:
        rel = str(record.get("path") or "").strip()
        if not rel:
            continue
        artifact = Path(run_dir) / rel
        if not artifact.is_file():
            problems.append(f"{name}: 产物文件不存在（声明 {rel}）；来源待核验")
            continue
        declared_hash = str(record.get("sha256") or "").strip()
        if declared_hash:
            try:
                import hashlib as _hashlib

                actual = _hashlib.sha256(artifact.read_bytes()).hexdigest()
            except OSError:
                problems.append(f"{name}: 产物文件不可读（{rel}）")
                continue
            if actual != declared_hash:
                problems.append(f"{name}: 产物哈希与声明不一致（{rel}）")
                continue
        any_verifiable = True
        content_problems = _verify_metrics_from_artifact(name, row.get("metrics") or {}, artifact, rel)
        if content_problems:
            problems.extend(content_problems)
        elif _artifact_contains_any_metric(artifact):
            any_content_checked = True
    if not any_verifiable:
        problems.append(f"{name}: 没有任何可核验的产物文件（声明不等于核验）")
        return problems
    if not any_content_checked:
        # 复审第 9 轮第 3 项：区分"文件完整性已验证"与"指标来源已验证"。
        problems.append(f"{name}: 文件完整性已验证，但指标来源未验证（产物不含可比对的指标值）")
    return problems


def _artifact_contains_any_metric(artifact: Path) -> bool:
    try:
        data = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and bool(data)


def _verify_metrics_from_artifact(name: str, metrics: dict[str, Any], artifact: Path, rel: str) -> list[str]:
    """从产物 JSON 重新提取指标并核对数值；返回问题列表（空 = 来源已核验）。"""
    import json as _json

    try:
        data = _json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return [f"{name}: 产物 {rel} 非 JSON/不可解析，指标来源未验证（文件完整性已验证）"]
    if not isinstance(data, dict):
        return [f"{name}: 产物 {rel} 不是指标对象，指标来源未验证（文件完整性已验证）"]
    problems: list[str] = []
    for key, declared in metrics.items():
        if key not in data:
            continue  # 产物只包含部分指标：不强制全含，由来源定位标注覆盖范围
        try:
            actual_value = float(data[key])
        except (TypeError, ValueError):
            problems.append(f"{name}: 产物 {rel} 的 {key} 非数值，指标来源未验证")
            continue
        try:
            declared_value = float(declared)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(actual_value) or abs(actual_value - declared_value) > 1e-6:
            problems.append(
                f"{name}: 指标 {key} 与产物内容不一致（声明 {declared_value}，产物 {actual_value}，来源 {rel}）"
            )
    return problems


def evidence_integrity_banner(integrity: EvidenceIntegrity | None) -> str:
    """论文顶部横幅；按两个独立维度分别措辞（复审第 3 项）。

    - 实验证据未通过 → 完整的"流水线演示"警示横幅；
    - 实验证据已核验、仅缺模型调用 → 只做来源说明（人工/模板撰写），
      不得宣称"不能作为科学结论"——实验真实性与报告撰写来源互相独立。
    """
    if integrity is None or integrity.publishable_evidence:
        return ""
    if integrity.real_experiment:
        return (
            "> ℹ️ **来源说明：本报告文本非模型生成（人工撰写或模板来源）。**\n"
            ">\n> 实验结果已通过真实性核验（见 04-evidence-integrity）；"
            "未使用的模型生成/独立评审步骤如需补齐，接入真实端点后重跑对应阶段。"
        )
    reasons: list[str] = []
    if not integrity.real_experiment:
        reasons.append("实验结果缺少可用真实数据（模拟、失败或未通过校验）")
    if not integrity.real_llm:
        reasons.append("未检测到成功的真实 LLM 调用（文本可能来自模板或人工撰写）")
    return (
        "> ⚠️ **诚实性声明：本稿为流水线演示，不能作为科学结论或投稿稿。**\n"
        f">\n> 原因：{'；'.join(reasons)}。"
        "正文中关于方法有效性、性能数字和与 baseline 的比较结论均**不被真实证据支持**，"
        "仅用于展示流水线结构与可复现骨架。正式研究须接入真实 LLM 与真实 benchmark 后重跑。"
    )


def evidence_integrity_prompt_constraint(integrity: EvidenceIntegrity | None) -> str:
    """注入论文 LLM 写作 prompt 的强制诚实性约束；两个维度都 verified 时返回空串。"""
    if integrity is None or integrity.publishable_evidence:
        return ""
    if integrity.real_experiment:
        # 实验证据已核验、仅缺模型：不注入"模拟原型"诚实性约束。
        return ""
    gaps: list[str] = []
    if not integrity.real_experiment:
        gaps.append("实验结果缺少可用真实数据")
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
        f"- LLM 证据：{integrity.llm_evidence_status}"
        f"（尝试 {integrity.llm_attempted_calls} / 成功 {integrity.llm_successful_calls}"
        f" / 结构有效 {integrity.llm_valid_responses} / 被产物引用 {integrity.llm_referenced_calls}）",
        f"- 实验证据：{integrity.experiment_evidence_status}"
        f"（真实可用 {integrity.real_result_count} / 真实执行尝试 {integrity.real_attempt_count}"
        f" / 模拟 {integrity.simulated_result_count}）",
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
        "schema_version": 2,
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
        "llm_evidence_status": integrity.llm_evidence_status,
        "experiment_evidence_status": integrity.experiment_evidence_status,
        "llm_attempted_calls": integrity.llm_attempted_calls,
        "llm_successful_calls": integrity.llm_successful_calls,
        "llm_valid_responses": integrity.llm_valid_responses,
        "llm_referenced_calls": integrity.llm_referenced_calls,
        "real_attempt_count": integrity.real_attempt_count,
        "unusable_result_reasons": integrity.unusable_result_reasons,
        "notes": integrity.notes,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
