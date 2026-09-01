from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Any
import re

from .artifacts import write_json, write_text, cell as _cell
from .config import ReleaseConfig
from .models import ReleaseMetadataCheck, ReleaseMetadataReport


RELEASE_METADATA_JSON = "10-release-metadata.json"
RELEASE_METADATA_MD = "10-release-metadata.md"
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def write_release_metadata_artifacts(topic: str, run_dir: Path, config: ReleaseConfig) -> ReleaseMetadataReport:
    report = build_release_metadata_report(topic, run_dir, config)
    write_json(run_dir / RELEASE_METADATA_JSON, report)
    write_text(run_dir / RELEASE_METADATA_MD, render_release_metadata_markdown(report))
    return report


def build_release_metadata_report(topic: str, run_dir: Path, config: ReleaseConfig) -> ReleaseMetadataReport:
    metadata = _metadata_dict(config)
    checks = [
        _url_check("code", "代码仓库 URL", metadata["code_repository_url"], "填写公开代码仓库 URL。"),
        _doi_or_url_check("code", "代码归档 DOI", metadata["code_archive_doi"], "在 Zenodo/OSF/Figshare 等创建代码归档 DOI。"),
        _license_check(run_dir, metadata["code_license"]),
        _text_check("code", "代码版本或 commit", metadata["code_version"], "填写 release tag、commit SHA 或版本号。"),
        _data_access_check(metadata),
        _doi_or_url_check("data", "数据归档 DOI", metadata["data_archive_doi"], "如使用真实数据，填写数据仓库 DOI 或稳定 accession。", required=False),
        _environment_check(run_dir, metadata["environment_url"]),
        _text_check("release", "发布备注", metadata["release_notes"], "记录本次发布范围、限制和人工核验结果。", required=False),
    ]
    blocking = [f"{item.item}: {item.action}" for item in checks if item.status == "block"]
    manual = [f"{item.item}: {item.action}" for item in checks if item.status == "manual_required"]
    status = _status(checks)
    recommended_config = _recommended_config(metadata, checks)
    return ReleaseMetadataReport(
        topic=topic,
        status=status,
        metadata=metadata,
        checks=checks,
        recommended_config=recommended_config,
        blocking_issues=blocking,
        manual_tasks=manual,
        code_statement=_code_statement(metadata, status),
        data_statement=_data_statement(metadata),
        release_statement=_release_statement(metadata, status),
    )


def render_release_metadata_markdown(report: ReleaseMetadataReport) -> str:
    lines = [
        f"# Release Metadata：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 阻断问题：{len(report.blocking_issues)}",
        f"- 人工待办：{len(report.manual_tasks)}",
        "",
        "## 元数据",
        "| 字段 | 值 |",
        "| --- | --- |",
    ]
    for key, value in report.metadata.items():
        lines.append(f"| {_cell(key)} | {_cell(value or '-')} |")
    lines.extend(["", "## 检查项", "| 类别 | 项目 | 状态 | 证据 | 动作 |", "| --- | --- | --- | --- | --- |"])
    for item in report.checks:
        lines.append(
            "| "
            + " | ".join([_cell(item.category), _cell(item.item), item.status, _cell(item.evidence), _cell(item.action or "-")])
            + " |"
        )
    lines.extend(["", "## 阻断问题"])
    lines.extend(f"- {item}" for item in report.blocking_issues) if report.blocking_issues else lines.append("- 无")
    lines.extend(["", "## 人工待办"])
    lines.extend(f"- [ ] {item}" for item in report.manual_tasks) if report.manual_tasks else lines.append("- 无")
    lines.extend(_recommended_config_markdown(report.recommended_config))
    lines.extend(
        [
            "",
            "## 建议声明",
            "### Code Availability",
            report.code_statement,
            "",
            "### Data Availability",
            report.data_statement,
            "",
            "### Release Record",
            report.release_statement,
        ]
    )
    return "\n".join(lines)


def _metadata_dict(config: ReleaseConfig) -> dict[str, str]:
    return {
        "code_repository_url": config.code_repository_url.strip(),
        "code_archive_doi": _normalize_doi(config.code_archive_doi.strip()),
        "code_license": config.code_license.strip(),
        "code_version": config.code_version.strip(),
        "data_repository_url": config.data_repository_url.strip(),
        "data_archive_doi": _normalize_doi(config.data_archive_doi.strip()),
        "data_access_statement": config.data_access_statement.strip(),
        "environment_url": config.environment_url.strip(),
        "release_notes": config.release_notes.strip(),
    }


def _recommended_config(metadata: dict[str, str], checks: list[ReleaseMetadataCheck]) -> dict[str, Any]:
    check_by_item = {check.item: check for check in checks}
    actions: dict[str, dict[str, Any]] = {}

    def add_field(
        field: str,
        metadata_key: str,
        check: ReleaseMetadataCheck,
        *,
        required: bool,
        action: str | None = None,
    ) -> None:
        if check.status == "pass":
            return
        actions[field] = {
            "metadata_key": metadata_key,
            "config_key": f"release.{metadata_key}",
            "cli_arg": "--" + field.replace("_", "-"),
            "current_value": metadata.get(metadata_key, ""),
            "recommended_value": "",
            "status": check.status,
            "required": required,
            "action": action or check.action,
        }

    add_field("release_code_repository_url", "code_repository_url", check_by_item["代码仓库 URL"], required=True)
    add_field("release_code_archive_doi", "code_archive_doi", check_by_item["代码归档 DOI"], required=True)
    add_field("release_code_license", "code_license", check_by_item["许可证"], required=True)
    add_field("release_code_version", "code_version", check_by_item["代码版本或 commit"], required=True)

    data_check = check_by_item["数据访问说明"]
    if data_check.status != "pass":
        data_field_required = data_check.status in {"block", "manual_required"}
        if metadata["data_repository_url"] and not _is_url(metadata["data_repository_url"]):
            add_field("release_data_repository_url", "data_repository_url", data_check, required=True)
        else:
            add_field(
                "release_data_access_statement",
                "data_access_statement",
                data_check,
                required=data_field_required,
            )

    add_field("release_data_archive_doi", "data_archive_doi", check_by_item["数据归档 DOI"], required=False)
    env_check = check_by_item["环境归档"]
    add_field(
        "release_environment_url",
        "environment_url",
        env_check,
        required=env_check.status in {"block", "manual_required"},
    )
    add_field("release_notes", "release_notes", check_by_item["发布备注"], required=False)

    required_fields = [field for field, item in actions.items() if item["required"]]
    recommended_fields = [field for field, item in actions.items() if not item["required"]]
    return {
        "status": "complete" if not actions else "needs_input",
        "required_fields": required_fields,
        "recommended_fields": recommended_fields,
        "manual_fields": list(actions),
        "cli_args": [item["cli_arg"] for item in actions.values()],
        "config_fields": {item["metadata_key"]: item["recommended_value"] for item in actions.values()},
        "field_actions": actions,
    }


def _recommended_config_markdown(recommended_config: dict[str, Any]) -> list[str]:
    lines = ["", "## 推荐配置"]
    actions = recommended_config.get("field_actions")
    if not isinstance(actions, dict) or not actions:
        lines.append("- 当前 release metadata 已完整，无需额外配置。")
        return lines
    required = recommended_config.get("required_fields") if isinstance(recommended_config.get("required_fields"), list) else []
    recommended = recommended_config.get("recommended_fields") if isinstance(recommended_config.get("recommended_fields"), list) else []
    lines.append("- 必填字段：" + (", ".join(f"`{item}`" for item in required) if required else "无"))
    lines.append("- 建议字段：" + (", ".join(f"`{item}`" for item in recommended) if recommended else "无"))
    lines.extend(["", "| 字段 | CLI 参数 | 配置键 | 状态 | 动作 |", "| --- | --- | --- | --- | --- |"])
    for field, item in actions.items():
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(str(field))}`",
                    f"`{_cell(str(item.get('cli_arg', '-')))}`",
                    f"`{_cell(str(item.get('config_key', '-')))}`",
                    _cell(str(item.get("status", "-"))),
                    _cell(str(item.get("action", "-")) or "-"),
                ]
            )
            + " |"
        )
    return lines


def _url_check(category: str, item: str, value: str, action: str, required: bool = True) -> ReleaseMetadataCheck:
    if not value:
        return ReleaseMetadataCheck(category, item, "manual_required" if required else "warn", "未配置", action)
    if _is_url(value):
        return ReleaseMetadataCheck(category, item, "pass", value)
    return ReleaseMetadataCheck(category, item, "block", value, "必须填写 http(s) URL。")


def _doi_or_url_check(category: str, item: str, value: str, action: str, required: bool = True) -> ReleaseMetadataCheck:
    if not value:
        return ReleaseMetadataCheck(category, item, "manual_required" if required else "warn", "未配置", action)
    if _is_doi(value) or _is_url(value):
        return ReleaseMetadataCheck(category, item, "pass", value)
    return ReleaseMetadataCheck(category, item, "block", value, "必须填写 DOI（10.xxxx/xxx）或 http(s) 稳定链接。")


def _license_check(run_dir: Path, configured_license: str) -> ReleaseMetadataCheck:
    if configured_license:
        return ReleaseMetadataCheck("code", "许可证", "pass", configured_license)
    repo_root = Path(__file__).resolve().parents[2]
    for name in ["LICENSE", "LICENSE.md", "COPYING"]:
        if (repo_root / name).exists():
            return ReleaseMetadataCheck("code", "许可证", "pass", f"本地检测到 {name}")
    return ReleaseMetadataCheck("code", "许可证", "manual_required", "未配置，也未检测到 LICENSE", "发布前补充代码许可证。")


def _text_check(category: str, item: str, value: str, action: str, required: bool = True) -> ReleaseMetadataCheck:
    if value:
        return ReleaseMetadataCheck(category, item, "pass", value)
    return ReleaseMetadataCheck(category, item, "manual_required" if required else "warn", "未配置", action)


def _data_access_check(metadata: dict[str, str]) -> ReleaseMetadataCheck:
    data_url = metadata["data_repository_url"]
    statement = metadata["data_access_statement"]
    if data_url and not _is_url(data_url):
        return ReleaseMetadataCheck("data", "数据访问说明", "block", data_url, "数据仓库必须是 http(s) URL，或只填写文字访问说明。")
    if data_url and statement:
        return ReleaseMetadataCheck("data", "数据访问说明", "pass", f"{data_url}; {statement[:120]}")
    if statement:
        return ReleaseMetadataCheck("data", "数据访问说明", "pass", statement[:180])
    if data_url:
        return ReleaseMetadataCheck("data", "数据访问说明", "warn", data_url, "建议补充访问条件、使用限制和预处理说明。")
    return ReleaseMetadataCheck("data", "数据访问说明", "manual_required", "未配置", "填写数据来源、访问条件、限制或说明本研究不使用外部数据。")


def _environment_check(run_dir: Path, value: str) -> ReleaseMetadataCheck:
    if value:
        if _is_url(value):
            return ReleaseMetadataCheck("reproducibility", "环境归档", "pass", value)
        return ReleaseMetadataCheck("reproducibility", "环境归档", "block", value, "环境归档必须是 http(s) URL。")
    if (run_dir / "04-environment-snapshot.json").exists():
        return ReleaseMetadataCheck(
            "reproducibility",
            "环境归档",
            "warn",
            "已生成 04-environment-snapshot.json，但未提供可公开访问的环境归档 URL",
            "建议补充 Docker/Conda/requirements 归档链接。",
        )
    if (run_dir / "04-experiment-runbook.json").exists():
        return ReleaseMetadataCheck("reproducibility", "环境归档", "warn", "runbook 记录了 Python/平台/命令，但未提供环境归档 URL", "建议补充 Docker/Conda/requirements 归档链接。")
    return ReleaseMetadataCheck("reproducibility", "环境归档", "manual_required", "未配置", "补充可复现环境说明或归档。")


def _status(checks: list[ReleaseMetadataCheck]) -> str:
    if any(item.status == "block" for item in checks):
        return "blocked"
    if any(item.status == "manual_required" for item in checks):
        return "needs_release_metadata"
    if any(item.status == "warn" for item in checks):
        return "ready_with_warnings"
    return "ready_for_release"


def _code_statement(metadata: dict[str, str], status: str) -> str:
    repo = metadata["code_repository_url"] or "待补公开代码仓库 URL"
    archive = metadata["code_archive_doi"] or "待补代码归档 DOI"
    license_value = metadata["code_license"] or "待补许可证"
    version = metadata["code_version"] or "待补版本或 commit"
    return f"Code is available at {repo} under {license_value}; the archived release is {archive}, version/commit {version}. Release metadata status: {status}."


def _data_statement(metadata: dict[str, str]) -> str:
    url = metadata["data_repository_url"]
    doi = metadata["data_archive_doi"]
    statement = metadata["data_access_statement"]
    parts = []
    if url:
        parts.append(f"Data repository: {url}.")
    if doi:
        parts.append(f"Archived data DOI/accession: {doi}.")
    if statement:
        parts.append(statement)
    return " ".join(parts) if parts else "Data availability metadata is not yet complete; data source, access conditions and restrictions must be provided before submission."


def _release_statement(metadata: dict[str, str], status: str) -> str:
    notes = metadata["release_notes"] or "No additional release notes recorded."
    env = metadata["environment_url"] or "environment archive pending"
    return f"Release metadata status is {status}; environment: {env}. {notes}"


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_doi(value: str) -> bool:
    return bool(_DOI_PATTERN.match(value))


def _normalize_doi(value: str) -> str:
    if value.lower().startswith("doi:"):
        return value[4:].strip()
    if "doi.org/" in value.lower():
        return value.rsplit("doi.org/", 1)[-1].strip()
    return value


