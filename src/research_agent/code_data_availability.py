from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import write_json, write_text, cell as _cell
from .models import CodeDataAvailabilityItem, CodeDataAvailabilityReport
from .release_metadata import RELEASE_METADATA_JSON


def build_code_data_availability_report(topic: str, run_dir: Path, paper_md: str = "") -> CodeDataAvailabilityReport:
    runbook = _read_json(run_dir / "04-experiment-runbook.json")
    results_json = run_dir / "04-results.json"
    results_csv = run_dir / "04-results.csv"
    statistics = run_dir / "04-statistics.json"
    benchmark_plan = run_dir / "03-benchmark-plan.json"
    bib = run_dir / "01-references.bib"
    ris = run_dir / "01-references.ris"
    experiment_dir = run_dir / "experiments"
    repo_root = Path(__file__).resolve().parents[2]
    release_metadata = _read_json(run_dir / RELEASE_METADATA_JSON)
    checks = [
        _file_check("experiments", "实验 runbook", run_dir / "04-experiment-runbook.json", "重新运行实验阶段，生成 04-experiment-runbook.json。"),
        _file_check("experiments", "结构化结果 JSON", results_json, "重新运行实验阶段，生成 04-results.json。"),
        _file_check("experiments", "结果 CSV", results_csv, "重新运行实验阶段，生成 04-results.csv。"),
        _file_check("experiments", "统计审计", statistics, "重新运行统计阶段，生成 04-statistics.json。"),
        _file_check("experiments", "真实 benchmark 接入计划", benchmark_plan, "重新运行实验计划阶段，生成 03-benchmark-plan.json。"),
        _artifact_hash_check(experiment_dir),
        _runbook_seed_check(runbook),
        _source_tree_check(repo_root),
        _license_check(repo_root, release_metadata),
        _file_check("citations", "BibTeX 导出", bib, "重新运行文献上下文阶段，生成 01-references.bib。"),
        _file_check("citations", "RIS 导出", ris, "重新运行文献上下文阶段，生成 01-references.ris。"),
        _paper_statement_check("paper", "代码可用性声明", paper_md, ["代码", "可用性"], "在论文中补充代码可用性声明，说明仓库、版本、许可和复现入口。"),
        _paper_statement_check("paper", "数据可用性声明", paper_md, ["数据", "可用性"], "在论文中补充数据可用性声明，说明数据来源、访问条件和限制。"),
        _release_metadata_check(release_metadata),
        _public_archive_check(release_metadata),
        _simulated_result_check(runbook),
    ]
    blocking = [f"{item.item}: {item.action}" for item in checks if item.status == "block"]
    manual = [f"{item.item}: {item.action}" for item in checks if item.status == "manual_required"]
    status = _status(checks)
    return CodeDataAvailabilityReport(
        topic=topic,
        status=status,
        ready_for_internal_release=not blocking,
        ready_for_submission_check=status == "ready_for_submission_check",
        checks=checks,
        blocking_issues=blocking,
        manual_tasks=manual,
        code_statement=_code_statement(checks, release_metadata),
        data_statement=_data_statement(checks, runbook, release_metadata),
        reproduction_statement=_reproduction_statement(runbook),
    )


def write_code_data_availability_artifacts(topic: str, run_dir: Path, paper_md: str = "") -> CodeDataAvailabilityReport:
    report = build_code_data_availability_report(topic, run_dir, paper_md)
    write_json(run_dir / "10-code-data-availability.json", report)
    write_text(run_dir / "10-code-data-availability.md", render_code_data_availability_markdown(report))
    return report


def render_code_data_availability_markdown(report: CodeDataAvailabilityReport) -> str:
    lines = [
        f"# 代码和数据可用性审计：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 内部可复查：{'是' if report.ready_for_internal_release else '否'}",
        f"- 投稿前可检查：{'是' if report.ready_for_submission_check else '否'}",
        "",
        "## 检查项",
        "| 类别 | 项目 | 状态 | 证据 | 动作 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in report.checks:
        lines.append(
            "| "
            + " | ".join([_cell(item.category), _cell(item.item), item.status, _cell(item.evidence), _cell(item.action or "-")])
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    if report.blocking_issues:
        lines.extend(f"- {item}" for item in report.blocking_issues)
    else:
        lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    if report.manual_tasks:
        lines.extend(f"- [ ] {item}" for item in report.manual_tasks)
    else:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 建议写入论文的声明",
            "### Code Availability",
            report.code_statement,
            "",
            "### Data Availability",
            report.data_statement,
            "",
            "### Reproducibility",
            report.reproduction_statement,
        ]
    )
    return "\n".join(lines)


def _file_check(category: str, item: str, path: Path, action: str) -> CodeDataAvailabilityItem:
    if not path.exists():
        return CodeDataAvailabilityItem(category=category, item=item, status="block", evidence=f"缺失：{path.name}", action=action)
    return CodeDataAvailabilityItem(category=category, item=item, status="pass", evidence=f"{path.name} 存在，sha256={_sha256(path)[:12]}")


def _artifact_hash_check(experiment_dir: Path) -> CodeDataAvailabilityItem:
    if not experiment_dir.exists():
        return CodeDataAvailabilityItem("experiments", "实验产物哈希", "block", "experiments/ 目录缺失", "重新运行实验阶段。")
    files = [path for path in experiment_dir.rglob("*") if path.is_file()]
    if not files:
        return CodeDataAvailabilityItem("experiments", "实验产物哈希", "block", "experiments/ 内无文件", "补充实验脚本或重新运行实验阶段。")
    hashed = [f"{path.name}:{_sha256(path)[:12]}" for path in files[:6]]
    return CodeDataAvailabilityItem("experiments", "实验产物哈希", "pass", f"{len(files)} 个文件；" + ", ".join(hashed))


def _runbook_seed_check(runbook: Any) -> CodeDataAvailabilityItem:
    runs = runbook.get("runs", []) if isinstance(runbook, dict) else []
    if not runs:
        return CodeDataAvailabilityItem("experiments", "随机种子和 repeat 记录", "block", "runbook 缺少 runs", "重新运行实验阶段。")
    missing = [run for run in runs if not isinstance(run, dict) or not run.get("seed")]
    if missing:
        return CodeDataAvailabilityItem("experiments", "随机种子和 repeat 记录", "block", f"{len(missing)} 条 run 缺少 seed", "重新运行实验阶段或补齐 seed。")
    return CodeDataAvailabilityItem("experiments", "随机种子和 repeat 记录", "pass", f"{len(runs)} 条 repeat 均有 seed")


def _source_tree_check(repo_root: Path) -> CodeDataAvailabilityItem:
    source_files = list((repo_root / "src" / "research_agent").glob("*.py"))
    if not source_files:
        return CodeDataAvailabilityItem("code", "源码树", "block", "未找到 src/research_agent/*.py", "确认项目源码已纳入发布包。")
    return CodeDataAvailabilityItem("code", "源码树", "pass", f"找到 {len(source_files)} 个核心 Python 文件")


def _license_check(repo_root: Path, release_metadata: Any) -> CodeDataAvailabilityItem:
    metadata = release_metadata.get("metadata", {}) if isinstance(release_metadata, dict) else {}
    code_license = str(metadata.get("code_license") or "").strip() if isinstance(metadata, dict) else ""
    if code_license:
        return CodeDataAvailabilityItem("code", "许可证", "pass", f"release metadata: {code_license}")
    candidates = ["LICENSE", "LICENSE.md", "COPYING"]
    for name in candidates:
        path = repo_root / name
        if path.exists():
            return CodeDataAvailabilityItem("code", "许可证", "pass", f"{name} 存在")
    return CodeDataAvailabilityItem("code", "许可证", "manual_required", "未找到 LICENSE 文件", "发布前补充代码许可证。")


def _paper_statement_check(category: str, item: str, paper_md: str, required_terms: list[str], action: str) -> CodeDataAvailabilityItem:
    text = paper_md.lower()
    ok = all(term.lower() in text for term in required_terms)
    if ok:
        return CodeDataAvailabilityItem(category, item, "pass", "修订稿包含相关声明关键词")
    return CodeDataAvailabilityItem(category, item, "manual_required", "修订稿未包含完整声明关键词", action)


def _release_metadata_check(release_metadata: Any) -> CodeDataAvailabilityItem:
    if not isinstance(release_metadata, dict) or not release_metadata:
        return CodeDataAvailabilityItem(
            "release",
            "Release metadata",
            "manual_required",
            f"缺少 {RELEASE_METADATA_JSON}",
            "填写 release 元数据后重新运行，生成代码仓库、许可证、归档 DOI 和数据访问记录。",
        )
    status = str(release_metadata.get("status") or "")
    if status == "blocked":
        return CodeDataAvailabilityItem("release", "Release metadata", "block", status, "修复 10-release-metadata.md 中的阻断项。")
    if status == "needs_release_metadata":
        return CodeDataAvailabilityItem("release", "Release metadata", "manual_required", status, "补齐 10-release-metadata.md 中的发布元数据。")
    if status == "ready_with_warnings":
        return CodeDataAvailabilityItem("release", "Release metadata", "warn", status, "投稿前核对 warning 项。")
    if status == "ready_for_release":
        return CodeDataAvailabilityItem("release", "Release metadata", "pass", status)
    return CodeDataAvailabilityItem("release", "Release metadata", "manual_required", status or "unknown", "人工核对 release 元数据状态。")


def _public_archive_check(release_metadata: Any) -> CodeDataAvailabilityItem:
    metadata = release_metadata.get("metadata", {}) if isinstance(release_metadata, dict) else {}
    if isinstance(metadata, dict):
        code_repo = str(metadata.get("code_repository_url") or "").strip()
        code_archive = str(metadata.get("code_archive_doi") or "").strip()
        data_repo = str(metadata.get("data_repository_url") or "").strip()
        data_archive = str(metadata.get("data_archive_doi") or "").strip()
        if code_repo and code_archive and (data_repo or data_archive or str(metadata.get("data_access_statement") or "").strip()):
            return CodeDataAvailabilityItem(
                "release",
                "公开仓库或归档 DOI",
                "pass",
                f"code={code_repo}; archive={code_archive}; data={data_archive or data_repo or 'statement'}",
            )
    return CodeDataAvailabilityItem(
        "release",
        "公开仓库或归档 DOI",
        "manual_required",
        "未检测到公开仓库 URL、Zenodo/OSF DOI 或数据仓库 accession",
        "正式投稿前创建公开代码/数据归档，并在论文中写入稳定链接或 DOI。",
    )


def _simulated_result_check(runbook: Any) -> CodeDataAvailabilityItem:
    mode = ""
    if isinstance(runbook, dict) and isinstance(runbook.get("execution"), dict):
        mode = str(runbook["execution"].get("mode") or "")
    if mode == "simulated":
        return CodeDataAvailabilityItem(
            "data",
            "真实数据或 benchmark",
            "manual_required",
            "当前实验模式为 simulated",
            "按 03-benchmark-plan.md 选择并接入真实公开数据集、领域 benchmark，或人工说明模拟实验范围。",
        )
    if mode == "local":
        return CodeDataAvailabilityItem("data", "真实数据或 benchmark", "warn", "当前为本地脚本执行；仍需人工确认数据来源和访问条件")
    return CodeDataAvailabilityItem("data", "真实数据或 benchmark", "manual_required", "无法确认实验模式", "人工确认数据来源。")


def _status(checks: list[CodeDataAvailabilityItem]) -> str:
    if any(item.status == "block" for item in checks):
        return "blocked"
    if any(item.status == "manual_required" for item in checks):
        return "needs_human_release_metadata"
    if any(item.status == "warn" for item in checks):
        return "ready_for_internal_release"
    return "ready_for_submission_check"


def _code_statement(checks: list[CodeDataAvailabilityItem], release_metadata: Any) -> str:
    if isinstance(release_metadata, dict) and str(release_metadata.get("code_statement") or "").strip():
        return str(release_metadata["code_statement"])
    license_status = next((item.status for item in checks if item.item == "许可证"), "manual_required")
    if license_status == "pass":
        return "本项目代码保存在当前研究 agent 源码树中；复现实验入口、命令、随机种子和产物哈希记录在 `04-experiment-runbook.json`。正式发布时应提供公开仓库 URL、版本标签和归档 DOI。"
    return "本项目代码当前保存在本地源码树中，复现实验入口记录在 `04-experiment-runbook.json`。正式发布前必须补充许可证、公开仓库 URL、版本标签和归档 DOI。"


def _data_statement(checks: list[CodeDataAvailabilityItem], runbook: Any, release_metadata: Any) -> str:
    if isinstance(release_metadata, dict) and str(release_metadata.get("data_statement") or "").strip():
        return str(release_metadata["data_statement"])
    mode = ""
    if isinstance(runbook, dict) and isinstance(runbook.get("execution"), dict):
        mode = str(runbook["execution"].get("mode") or "")
    if mode == "simulated":
        return "当前结果来自系统内置模拟执行器，不包含可替代真实科学结论的公开数据集。正式研究需按 `03-benchmark-plan.md` 声明真实数据集、访问条件、预处理脚本和任何使用限制。"
    return "实验数据和中间产物保存在本次 run 的 `experiments/` 与结果文件中；正式投稿前需补充公开数据集或数据仓库链接、访问条件和限制说明。"


def _reproduction_statement(runbook: Any) -> str:
    if not isinstance(runbook, dict):
        return "复现信息缺失；请重新运行实验阶段生成 `04-experiment-runbook.json`。"
    execution = runbook.get("execution", {}) if isinstance(runbook.get("execution"), dict) else {}
    mode = execution.get("mode") or "-"
    repeats = execution.get("repeats") or "-"
    timeout = execution.get("timeout_seconds") or "-"
    return f"复现实验使用 `{mode}` 模式，重复次数为 {repeats}，超时限制为 {timeout}s；完整命令、环境、随机种子和产物 SHA256 见 `04-experiment-runbook.md/json`。"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


