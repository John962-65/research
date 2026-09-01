from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Any
import hashlib
import json
import os
import re
import zipfile

from .artifacts import read_json, write_json, write_text
from .config import AgentConfig
from .credential_validation import placeholder_secret as _placeholder_secret
from .credential_validation import valid_contact_email
from .preflight import PreflightReport, run_preflight
from .repair_resume import REPAIR_RESUME_PLAN_JSON, REPAIR_RESUME_PLAN_MD, write_repair_resume_plan_artifacts
from .submission_package_zip import submission_package_zip_ready


GOLD_RUN_DOCTOR_JSON = "00-gold-run-doctor.json"
GOLD_RUN_DOCTOR_MD = "00-gold-run-doctor.md"
GOLD_LAUNCH_MANIFEST_JSON = "00-gold-launch-manifest.json"
GOLD_LAUNCH_MANIFEST_MD = "00-gold-launch-manifest.md"
GOLD_RUN_VERIFICATION_JSON = "15-gold-run-verification.json"
GOLD_RUN_VERIFICATION_MD = "15-gold-run-verification.md"
DEFAULT_LOCAL_GATEWAY_BASE_URL = "http://127.0.0.1:8317"
DEFAULT_LOCAL_GATEWAY_MODEL = "gpt-5.5"
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_PLACEHOLDER_RELEASE_TOKENS = ("<", ">", "example", "placeholder", "replace", "scaffold", "fixture", "todo", "your-")
_GOLD_RUN_REQUIRED_ARTIFACTS = [
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
_SECRET_SCAN_TEXT_SUFFIXES = {
    ".bib",
    ".csv",
    ".css",
    ".html",
    ".json",
    ".js",
    ".log",
    ".md",
    ".py",
    ".ris",
    ".sh",
    ".tex",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}
_SECRET_SCAN_RULES = {
    "openai_style_token": re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    "json_api_key_field": re.compile(r'(?i)"(?:api_key|llm_api_key|semantic_scholar_api_key|openalex_api_key)"\s*:\s*"([^"]+)"'),
    "env_api_key_assignment": re.compile(r"(?i)\b(?:OPENAI_API_KEY|SEMANTIC_SCHOLAR_API_KEY|OPENALEX_API_KEY)\s*=\s*['\"]?([^\s'\"]+)"),
    "auth_header_token": re.compile(r"(?i)\b(?:authorization\s*:\s*(?:bearer|token)|x-api-key\s*:)\s*([^\s]+)"),
    "query_api_key_token": re.compile(r"(?i)\b(?:api_key|apikey|x-api-key|bearer|token)=([^\s&]+)"),
}

_NONBLOCKING_STARTUP_WARN_CHECKS = {"semantic_scholar_key", "openalex_key"}
_HUMAN_HANDOFF_AUDIT_STATUSES = {"pass", "warn", "review_required", "needs_human_review"}


def write_gold_run_doctor_artifacts(
    *,
    topic: str,
    config: AgentConfig,
    out_dir: Path,
    config_path: Path | None = None,
    benchmark_pack_run_dir: Path | None = None,
    fulltext_grounding_run_dir: Path | None = None,
    candidate_run_dir: Path | None = None,
    ping_llm: bool = False,
    llm_timeout_seconds: float = 8.0,
    write_candidate_repair_resume_plan: bool = False,
) -> dict[str, Any]:
    report = build_gold_run_doctor(
        topic=topic,
        config=config,
        config_path=config_path,
        benchmark_pack_run_dir=benchmark_pack_run_dir,
        fulltext_grounding_run_dir=fulltext_grounding_run_dir,
        candidate_run_dir=candidate_run_dir,
        ping_llm=ping_llm,
        llm_timeout_seconds=llm_timeout_seconds,
    )
    doctor_json_path = out_dir / GOLD_RUN_DOCTOR_JSON
    write_json(doctor_json_path, report)
    if write_candidate_repair_resume_plan:
        report = {
            **report,
            "candidate_repair_resume_plan": _write_candidate_repair_resume_plan(
                report,
                candidate_run_dir=candidate_run_dir,
                doctor_report_path=doctor_json_path,
            ),
        }
    launch_manifest = report.get("launch_manifest") if isinstance(report.get("launch_manifest"), dict) else {}
    if launch_manifest:
        write_json(out_dir / GOLD_LAUNCH_MANIFEST_JSON, launch_manifest)
        write_text(out_dir / GOLD_LAUNCH_MANIFEST_MD, render_gold_launch_manifest_markdown(launch_manifest))
    write_json(doctor_json_path, report)
    write_text(out_dir / GOLD_RUN_DOCTOR_MD, render_gold_run_doctor_markdown(report))
    return report


def write_gold_run_verification_artifacts(run_dir: Path, out_dir: Path | None = None) -> dict[str, Any]:
    report = build_gold_run_verification_report(run_dir)
    destination = out_dir or run_dir
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / GOLD_RUN_VERIFICATION_JSON, report)
    write_text(destination / GOLD_RUN_VERIFICATION_MD, render_gold_run_verification_markdown(report))
    return report


def build_gold_run_verification_report(run_dir: Path) -> dict[str, Any]:
    check = _candidate_run_check(run_dir)
    contract_evidence = check.get("contract_evidence") if isinstance(check.get("contract_evidence"), dict) else {}
    repair_plan = check.get("repair_plan") if isinstance(check.get("repair_plan"), list) else []
    missing = _missing_gold_required_artifacts(run_dir)
    unsafe_artifacts = _gold_unsafe_required_artifacts(run_dir)
    artifact_safety = _gold_artifact_safety_report(unsafe_artifacts)
    secret_scan = _gold_run_secret_scan(run_dir)
    artifact_hashes = _gold_required_artifact_hashes(run_dir)
    manifest_inventory = _gold_manifest_inventory_check(run_dir, artifact_hashes)
    if unsafe_artifacts:
        repair_plan = [*repair_plan, _gold_required_artifact_safety_repair_item(unsafe_artifacts)]
    if manifest_inventory.get("status") != "pass":
        repair_plan = [*repair_plan, _gold_manifest_inventory_repair_item(manifest_inventory)]
    ready = (
        check.get("status") == "pass"
        and _verification_contract_evidence_ready(contract_evidence)
        and not missing
        and artifact_safety.get("status") == "pass"
        and _gold_required_artifact_hashes_ready(artifact_hashes)
        and manifest_inventory.get("status") == "pass"
        and secret_scan.get("status") == "pass"
    )
    return {
        "schema_version": 2,
        "status": "ready" if ready else "blocked",
        "gold_contract_ready": ready,
        "run_dir": str(run_dir),
        "required_artifacts": list(_GOLD_RUN_REQUIRED_ARTIFACTS),
        "missing_artifacts": missing,
        "unsafe_artifacts": unsafe_artifacts,
        "artifact_safety": artifact_safety,
        "artifact_hashes": artifact_hashes,
        "manifest_inventory": manifest_inventory,
        "secret_scan": secret_scan,
        "check": check,
        "contract_evidence": contract_evidence,
        "repair_plan": repair_plan,
        "read_only": True,
    }


def _missing_gold_required_artifacts(run_dir: Path) -> list[str]:
    return [name for name in _GOLD_RUN_REQUIRED_ARTIFACTS if not _gold_required_artifact_present(run_dir / name)]


def _gold_required_artifact_present(path: Path) -> bool:
    if not path.exists():
        return False
    if path.name == "11-submission-package.zip":
        return submission_package_zip_ready(path)
    return True


def _gold_required_artifact_hashes(run_dir: Path) -> dict[str, dict[str, Any]]:
    hashes: dict[str, dict[str, Any]] = {}
    for name in _GOLD_RUN_REQUIRED_ARTIFACTS:
        path = run_dir / name
        if _gold_required_artifact_path_issue(path, run_dir):
            continue
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            hashes[name] = {"sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}
        except OSError:
            continue
    return hashes


def _gold_required_artifact_hashes_ready(hashes: dict[str, dict[str, Any]]) -> bool:
    return all(_gold_required_artifact_hash_ready(hashes.get(name)) for name in _GOLD_RUN_REQUIRED_ARTIFACTS)


def _gold_required_artifact_hash_ready(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    value = item.get("sha256")
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value)) and _positive_int(item.get("size_bytes"))


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _gold_unsafe_required_artifacts(run_dir: Path) -> list[dict[str, str]]:
    unsafe: list[dict[str, str]] = []
    for name in _GOLD_RUN_REQUIRED_ARTIFACTS:
        issue = _gold_required_artifact_path_issue(run_dir / name, run_dir)
        if issue:
            unsafe.append({"path": name, "issue": issue})
    return unsafe


def _gold_required_artifact_path_issue(path: Path, run_dir: Path) -> str:
    try:
        if path.is_symlink():
            return "symlink"
        if not path.exists():
            return ""
        if not path.is_file():
            return "not_file"
        try:
            path.resolve().relative_to(run_dir.resolve())
        except ValueError:
            return "path_escape"
    except OSError:
        return "unreadable"
    return ""


def _gold_artifact_safety_report(unsafe_artifacts: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "blocked" if unsafe_artifacts else "pass",
        "checked_artifacts": len(_GOLD_RUN_REQUIRED_ARTIFACTS),
        "unsafe_artifacts": unsafe_artifacts,
        "safe_to_render": True,
    }


def _gold_required_artifact_safety_repair_item(unsafe_artifacts: list[dict[str, str]]) -> dict[str, Any]:
    targets = _unique_strings([str(item.get("path") or "") for item in unsafe_artifacts])[:12]
    return _candidate_repair_item(
        "required_artifact_safety",
        16,
        "checkpoint",
        "candidate_run",
        targets,
        "重新生成 unsafe required artifacts，确保 gold required artifacts 是 run 目录内的普通文件，不是 symlink、目录或目录逃逸路径。",
    )


def _gold_manifest_inventory_check(run_dir: Path, artifact_hashes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest = _read_dict(run_dir / "run-manifest.json")
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    by_path = {
        str(item.get("path") or ""): item
        for item in artifacts
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    }
    unsafe_paths = _gold_manifest_inventory_unsafe_paths(artifacts)
    required = [name for name in _GOLD_RUN_REQUIRED_ARTIFACTS if name != "run-manifest.json"]
    missing = [name for name in required if name not in by_path]
    duplicates = sorted(name for name in required if sum(int(isinstance(item, dict) and str(item.get("path") or "") == name) for item in artifacts) > 1)
    mismatched: list[str] = []
    size_mismatched: list[str] = []
    for name in required:
        item = by_path.get(name)
        current = artifact_hashes.get(name)
        if not isinstance(item, dict) or not isinstance(current, dict):
            continue
        expected_sha = str(item.get("sha256") or "")
        actual_sha = str(current.get("sha256") or "")
        if expected_sha != actual_sha:
            mismatched.append(name)
        expected_size = item.get("bytes")
        actual_size = current.get("size_bytes")
        if not _positive_int(expected_size) or not _positive_int(actual_size) or expected_size != actual_size:
            size_mismatched.append(name)
    status = "pass" if manifest and not missing and not mismatched and not size_mismatched and not duplicates and not unsafe_paths else "blocked"
    return {
        "schema_version": 1,
        "status": status,
        "checked_artifacts": len(required),
        "recorded_artifacts": len(by_path),
        "missing_required_artifacts": missing,
        "hash_mismatches": mismatched,
        "size_mismatches": size_mismatched,
        "duplicate_required_artifacts": duplicates,
        "unsafe_artifact_paths": unsafe_paths,
        "safe_to_render": True,
    }


def _gold_manifest_inventory_unsafe_paths(artifacts: list[Any]) -> list[dict[str, str]]:
    unsafe: list[dict[str, str]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        value = str(item.get("path") or "").strip()
        if not value:
            continue
        issue = _gold_manifest_artifact_path_issue(value)
        if issue:
            unsafe.append({"path": _manifest_artifact_path_label(value), "issue": issue})
    return unsafe


def _gold_manifest_artifact_path_issue(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "empty"
    if "\\" in text:
        return "backslash"
    if re.match(r"^[A-Za-z]:", text):
        return "drive_path"
    path = Path(text)
    if path.is_absolute():
        return "absolute"
    if any(part == ".." for part in path.parts):
        return "parent_reference"
    return ""


def _manifest_artifact_path_label(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return "<empty>"
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    if not parts:
        return "<unsafe>"
    return "/".join(parts[-2:])


def _gold_manifest_inventory_repair_item(report: dict[str, Any]) -> dict[str, Any]:
    missing = _string_list(report.get("missing_required_artifacts"))
    mismatched = _string_list(report.get("hash_mismatches"))
    size_mismatched = _string_list(report.get("size_mismatches"))
    duplicates = _string_list(report.get("duplicate_required_artifacts"))
    unsafe = [
        str(item.get("path") or "")
        for item in (report.get("unsafe_artifact_paths") if isinstance(report.get("unsafe_artifact_paths"), list) else [])
        if isinstance(item, dict)
    ]
    targets = _unique_strings(["run-manifest.json", *missing[:8], *mismatched[:8], *size_mismatched[:8], *duplicates[:8], *unsafe[:8]])
    return _candidate_repair_item(
        "manifest_inventory",
        18,
        "checkpoint",
        "run-manifest.json",
        targets,
        "重新生成 run-manifest.json，确保 artifact inventory 只使用 run 目录内安全相对路径，gold required artifacts 唯一记录，且 SHA256/bytes 与磁盘一致。",
    )


def render_gold_run_verification_markdown(report: dict[str, Any]) -> str:
    check = report.get("check") if isinstance(report.get("check"), dict) else {}
    evidence = report.get("contract_evidence") if isinstance(report.get("contract_evidence"), dict) else {}
    lines = [
        "# Gold Run Verification",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Gold contract ready：{'是' if report.get('gold_contract_ready') else '否'}",
        f"- 只读：{'是' if report.get('read_only') else '否'}",
        "",
        "## Contract Check",
        f"- candidate_gold_run：`{check.get('status') or '-'}`",
        f"- detail：{check.get('detail') or '-'}",
        f"- final_zip：{_verification_final_zip_state(report)}",
        f"- audit_contracts：{evidence.get('audit_contract_ready_count') or 0}/{evidence.get('audit_contract_total') or 0} ready; blocking={evidence.get('audit_contract_blocking_issues') or 0}; manual={evidence.get('audit_contract_manual_tasks') or 0}",
    ]
    secret_scan = report.get("secret_scan") if isinstance(report.get("secret_scan"), dict) else {}
    lines.extend(
        [
            "",
            "## Secret Scan",
            f"- 状态：{secret_scan.get('status') or '-'}",
            f"- 扫描文件：{secret_scan.get('scanned_files') or 0}",
            f"- 命中：{secret_scan.get('finding_count') or 0}",
        ]
    )
    findings = [item for item in (secret_scan.get("findings") if isinstance(secret_scan.get("findings"), list) else []) if isinstance(item, dict)]
    if findings:
        lines.extend(["| Path | Rule | Count |", "| --- | --- | ---: |"])
        for item in findings:
            lines.append(f"| {_cell(str(item.get('path') or ''))} | {_cell(str(item.get('rule') or ''))} | {_cell(str(item.get('count') or 0))} |")
    missing = _string_list(report.get("missing_artifacts"))
    lines.extend(["", "## Missing Artifacts"])
    lines.extend(f"- {item}" for item in missing) if missing else lines.append("- 无")
    artifact_safety = report.get("artifact_safety") if isinstance(report.get("artifact_safety"), dict) else {}
    unsafe_artifacts = [item for item in (report.get("unsafe_artifacts") if isinstance(report.get("unsafe_artifacts"), list) else []) if isinstance(item, dict)]
    lines.extend(
        [
            "",
            "## Required Artifact Safety",
            f"- 状态：{artifact_safety.get('status') or '-'}",
            f"- Unsafe：{len(unsafe_artifacts)}",
        ]
    )
    if unsafe_artifacts:
        lines.extend(["| Path | Issue |", "| --- | --- |"])
        for item in unsafe_artifacts:
            lines.append(f"| {_cell(str(item.get('path') or ''))} | {_cell(str(item.get('issue') or ''))} |")
    artifact_hashes = report.get("artifact_hashes") if isinstance(report.get("artifact_hashes"), dict) else {}
    lines.extend(["", "## Artifact Hashes", f"- 记录：{_gold_artifact_hash_count(artifact_hashes)}/{len(_GOLD_RUN_REQUIRED_ARTIFACTS)}"])
    manifest_inventory = report.get("manifest_inventory") if isinstance(report.get("manifest_inventory"), dict) else {}
    lines.extend(
        [
            "",
            "## Manifest Inventory",
            f"- 状态：{manifest_inventory.get('status') or '-'}",
            f"- 检查：{manifest_inventory.get('checked_artifacts') or 0}",
            f"- 缺失记录：{len(_string_list(manifest_inventory.get('missing_required_artifacts')))}",
            f"- Hash 不一致：{len(_string_list(manifest_inventory.get('hash_mismatches')))}",
            f"- Size 不一致：{len(_string_list(manifest_inventory.get('size_mismatches')))}",
            f"- 重复记录：{len(_string_list(manifest_inventory.get('duplicate_required_artifacts')))}",
            f"- Unsafe path：{len(manifest_inventory.get('unsafe_artifact_paths') if isinstance(manifest_inventory.get('unsafe_artifact_paths'), list) else [])}",
        ]
    )
    repair_plan = report.get("repair_plan") if isinstance(report.get("repair_plan"), list) else []
    lines.extend(["", "## Repair Plan"])
    if repair_plan:
        lines.extend(["| ID | Priority | Rerun from | Target artifacts | Action |", "| --- | ---: | --- | --- | --- |"])
        for item in repair_plan:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("id") or "")),
                            _cell(str(item.get("priority") or "")),
                            _cell(str(item.get("rerun_from") or "")),
                            _cell(", ".join(_string_list(item.get("target_artifacts")))),
                            _cell(str(item.get("action") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("该检查只读取 run 目录中的公开证据产物；不会读取、记录或返回任何 secret。")
    return "\n".join(lines)


def _gold_artifact_hash_count(hashes: dict[str, Any]) -> int:
    return sum(int(_gold_required_artifact_hash_ready(hashes.get(name))) for name in _GOLD_RUN_REQUIRED_ARTIFACTS)


def _gold_run_secret_scan(run_dir: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned = 0
    skipped = 0
    if not run_dir.exists():
        return {
            "schema_version": 1,
            "status": "blocked",
            "scanned_files": 0,
            "skipped_files": 0,
            "finding_count": 1,
            "findings": [{"path": ".", "rule": "run_dir_missing", "count": 1}],
            "safe_to_render": True,
        }
    for path in sorted(run_dir.rglob("*")):
        reference_issue = _secret_scan_file_reference_issue(path, run_dir)
        if reference_issue:
            findings.append({"path": _safe_relative_to(path, run_dir), "rule": "unsafe_file_reference", "count": 1})
            continue
        if not path.is_file():
            continue
        if path.name == "11-submission-package.zip":
            scanned_zip, skipped_zip = _scan_secret_zip_entries(path, run_dir, findings)
            scanned += scanned_zip
            skipped += skipped_zip
            continue
        if not _secret_scan_should_read(path):
            skipped += 1
            continue
        try:
            if path.stat().st_size > 2_000_000:
                skipped += 1
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            skipped += 1
            continue
        scanned += 1
        relative = _safe_relative_to(path, run_dir)
        _append_secret_scan_findings(findings, relative, text)
    return {
        "schema_version": 1,
        "status": "pass" if not findings else "blocked",
        "scanned_files": scanned,
        "skipped_files": skipped,
        "finding_count": sum(_safe_int(item.get("count")) for item in findings),
        "findings": findings[:50],
        "truncated_findings": max(0, len(findings) - 50),
        "rules": sorted([*_SECRET_SCAN_RULES, "unsafe_file_reference"]),
        "safe_to_render": True,
    }


def _secret_scan_file_reference_issue(path: Path, run_dir: Path) -> str:
    try:
        if path.is_symlink():
            return "symlink"
        if not path.exists():
            return ""
        if not path.is_file():
            return ""
        try:
            path.resolve().relative_to(run_dir.resolve())
        except ValueError:
            return "path_escape"
    except OSError:
        return "unreadable"
    return ""


def _scan_secret_zip_entries(path: Path, run_dir: Path, findings: list[dict[str, Any]]) -> tuple[int, int]:
    scanned = 0
    skipped = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not _secret_scan_name_should_read(info.filename):
                    skipped += 1
                    continue
                if info.file_size > 2_000_000:
                    skipped += 1
                    continue
                try:
                    text = archive.read(info).decode("utf-8", errors="ignore")
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    skipped += 1
                    continue
                scanned += 1
                _append_secret_scan_findings(findings, f"{_safe_relative_to(path, run_dir)}!{info.filename}", text)
    except (OSError, zipfile.BadZipFile):
        skipped += 1
    return scanned, skipped


def _append_secret_scan_findings(findings: list[dict[str, Any]], path: str, text: str) -> None:
    for rule, pattern in _SECRET_SCAN_RULES.items():
        count = _secret_scan_match_count(rule, pattern, text)
        if count:
            findings.append({"path": path, "rule": rule, "count": count})


def _secret_scan_should_read(path: Path) -> bool:
    if any(part in {".cache", "__pycache__", "node_modules"} for part in path.parts):
        return False
    return _secret_scan_name_should_read(path.name)


def _secret_scan_name_should_read(name: str) -> bool:
    path = Path(name)
    filename = path.name.lower()
    return path.suffix.lower() in _SECRET_SCAN_TEXT_SUFFIXES or filename == ".env" or filename.startswith(".env.") or filename.endswith(".env")


def _secret_scan_match_count(rule: str, pattern: re.Pattern[str], text: str) -> int:
    count = 0
    for match in pattern.finditer(text):
        if rule == "openai_style_token":
            count += 1
            continue
        value = match.group(1) if match.groups() else match.group(0)
        if _secret_scan_value_is_sensitive(value):
            count += 1
    return count


def _secret_scan_value_is_sensitive(value: str) -> bool:
    text = str(value or "").strip().strip("'\"")
    lowered = text.lower()
    if not text:
        return False
    if text.startswith("<") and text.endswith(">"):
        return False
    if lowered in {"***", "<redacted>", "redacted", "none", "null", "false", "true"}:
        return False
    if any(token in lowered for token in ["placeholder", "replace", "real-key", "your-", "example"]):
        return False
    return True


def _safe_relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def build_gold_run_doctor(
    *,
    topic: str,
    config: AgentConfig,
    config_path: Path | None = None,
    benchmark_pack_run_dir: Path | None = None,
    fulltext_grounding_run_dir: Path | None = None,
    candidate_run_dir: Path | None = None,
    ping_llm: bool = False,
    llm_timeout_seconds: float = 8.0,
) -> dict[str, Any]:
    preflight = run_preflight(topic, config, ping_llm=ping_llm, llm_timeout_seconds=llm_timeout_seconds, run_memory=None)
    checks = [
        *_credential_checks(config),
        _credential_transport_check(config),
        _gold_release_metadata_check(config),
        _preflight_status_check(preflight),
        *_preflight_contract_checks(preflight),
        _benchmark_pack_run_check(benchmark_pack_run_dir),
        _fulltext_grounding_run_check(fulltext_grounding_run_dir),
        *([_candidate_run_check(candidate_run_dir)] if candidate_run_dir is not None else []),
    ]
    status = "blocked" if any(item["status"] == "fail" for item in checks) else "warn" if any(item["status"] == "warn" for item in checks) else "ready"
    report = {
        "schema_version": 1,
        "topic": topic,
        "status": status,
        "checks": checks,
        "preflight_status": preflight.status,
        "preflight": _preflight_summary(preflight),
        "commands": _gold_run_commands(topic, config, config_path=config_path),
    }
    report["launch_manifest"] = _build_launch_manifest(
        report,
        config=config,
        benchmark_pack_run_dir=benchmark_pack_run_dir,
        fulltext_grounding_run_dir=fulltext_grounding_run_dir,
        candidate_run_dir=candidate_run_dir,
    )
    return report


def render_gold_run_doctor_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Gold Run Doctor：{report.get('topic') or ''}",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Preflight：{report.get('preflight_status') or '-'}",
        "",
        "## Checks",
        "| Check | Status | Detail | Action |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.get("checks", []) if isinstance(report.get("checks"), list) else []:
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("name") or "")),
                        _cell(str(item.get("status") or "")),
                        _cell(str(item.get("detail") or "")),
                        _cell(str(item.get("action") or "-")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Commands"])
    commands = report.get("commands") if isinstance(report.get("commands"), list) else []
    if commands:
        lines.append("```bash")
        lines.extend(str(item) for item in commands)
        lines.append("```")
    else:
        lines.append("- 无")
    launch_manifest = report.get("launch_manifest") if isinstance(report.get("launch_manifest"), dict) else {}
    if launch_manifest:
        lines.extend(_render_launch_manifest_section(launch_manifest))
    repair_plan = _candidate_repair_plan_from_report(report)
    if repair_plan:
        lines.extend(
            [
                "",
                "## Candidate Repair Plan",
                "| Priority | Rerun From | Source | Target Artifacts | Action |",
                "| ---: | --- | --- | --- | --- |",
            ]
        )
        for item in repair_plan:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(item.get("priority") or ""),
                            _cell(str(item.get("rerun_from") or "")),
                            _cell(str(item.get("source_artifact") or "")),
                            _cell(", ".join(_string_list(item.get("target_artifacts")))),
                            _cell(str(item.get("action") or "")),
                        ]
                    )
                    + " |"
                )
    resume_plan = report.get("candidate_repair_resume_plan") if isinstance(report.get("candidate_repair_resume_plan"), dict) else {}
    if resume_plan:
        lines.extend(
            [
                "",
                "## Candidate Repair Resume Plan",
                f"- 状态：{resume_plan.get('status') or '-'}",
                f"- 候选 run：`{resume_plan.get('candidate_run_dir') or '-'}`",
                f"- 可恢复：{'是' if resume_plan.get('can_resume') else '否'}",
                f"- 重跑入口：`{resume_plan.get('rerun_from') or '-'}`",
                f"- 修复任务：`{resume_plan.get('repair_items') or 0}`",
                f"- 预案：`{resume_plan.get('plan_json') or '-'}`",
            ]
        )
    return "\n".join(lines)


def render_gold_launch_manifest_markdown(manifest: dict[str, Any]) -> str:
    lines = _render_launch_manifest_section(manifest)
    if lines and lines[0] == "":
        lines = lines[1:]
    if lines and lines[0] == "## Gold Launch Manifest":
        lines[0] = f"# Gold Launch Manifest：{manifest.get('topic') or ''}"
    return "\n".join(lines)


def build_gold_release_metadata_lint(config: AgentConfig) -> dict[str, Any]:
    summary = _launch_release_summary(config)
    field_statuses = _release_field_statuses(config)
    optional_statuses = _optional_release_field_statuses(config)
    check = _gold_release_metadata_check(config)
    blocking_fields = [
        *summary.get("missing_required_fields", []),
        *summary.get("invalid_required_fields", []),
        *summary.get("placeholder_required_fields", []),
        *[field for field, item in optional_statuses.items() if item.get("status") in {"invalid", "placeholder"}],
    ]
    recommended_fields = [field for field in summary.get("required_fields", []) if field in blocking_fields]
    return {
        "schema_version": 1,
        "status": "ready" if check["status"] == "pass" else "blocked",
        "check": check["name"],
        "check_status": check["status"],
        "detail": check["detail"],
        "action": check.get("action", ""),
        "required_ready": summary.get("required_ready") is True and check["status"] == "pass",
        "required_fields": summary.get("required_fields", []),
        "present_required_fields": summary.get("present_required_fields", []),
        "missing_required_fields": summary.get("missing_required_fields", []),
        "invalid_required_fields": summary.get("invalid_required_fields", []),
        "placeholder_required_fields": summary.get("placeholder_required_fields", []),
        "field_statuses": field_statuses,
        "optional_field_statuses": optional_statuses,
        "blocking_fields": _unique_strings(blocking_fields),
        "recommended_fields": _unique_strings(recommended_fields),
        "next_steps": _gold_release_metadata_next_steps(blocking_fields),
    }


def render_gold_release_metadata_lint_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Gold Release Metadata Lint",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Gold check：{report.get('check_status') or '-'}",
        f"- 必填 ready：{'是' if report.get('required_ready') else '否'}",
        f"- 阻断字段：{', '.join(_string_list(report.get('blocking_fields'))) or '-'}",
        "",
        "## Required Fields",
        "| Field | Status | Kind |",
        "| --- | --- | --- |",
    ]
    field_statuses = report.get("field_statuses") if isinstance(report.get("field_statuses"), dict) else {}
    if not field_statuses:
        field_statuses = {}
        for field in _string_list(report.get("required_fields")):
            if field in _string_list(report.get("missing_required_fields")):
                status = "missing"
            elif field in _string_list(report.get("invalid_required_fields")):
                status = "invalid"
            elif field in _string_list(report.get("placeholder_required_fields")):
                status = "placeholder"
            else:
                status = "pass"
            field_statuses[field] = {"status": status, "kind": "-"}
    for field, item in field_statuses.items():
        if isinstance(item, dict):
            lines.append(f"| {_cell(field)} | {_cell(str(item.get('status') or '-'))} | {_cell(str(item.get('kind') or '-'))} |")
    optional = report.get("optional_field_statuses") if isinstance(report.get("optional_field_statuses"), dict) else {}
    if optional:
        lines.extend(["", "## Optional Fields", "| Field | Status | Kind |", "| --- | --- | --- |"])
        for field, item in optional.items():
            if isinstance(item, dict):
                lines.append(f"| {_cell(field)} | {_cell(str(item.get('status') or '-'))} | {_cell(str(item.get('kind') or '-'))} |")
    lines.extend(["", "## Next Steps"])
    steps = _string_list(report.get("next_steps"))
    lines.extend(f"- {item}" for item in steps) if steps else lines.append("- 无")
    return "\n".join(lines)


def build_gold_environment_lint(config: AgentConfig) -> dict[str, Any]:
    required = {
        "llm_base_url": _gold_env_field(os.environ.get(config.llm.base_url_env, ""), "url", required=True, secret=False, expected=config.llm.base_url),
        "llm_model": _gold_env_field(os.environ.get(config.llm.model_env, ""), "text", required=True, secret=False, expected=config.llm.model),
        "llm_api_key": _gold_env_field(os.environ.get(config.llm.api_key_env, ""), "secret", required=True, secret=True),
        "literature_contact_email": _gold_env_field(os.environ.get(config.literature.contact_email_env, ""), "email", required=True, secret=False),
    }
    optional = {
        "semantic_scholar_api_key": _gold_env_field(os.environ.get(config.literature.semantic_scholar_api_key_env, ""), "secret", required=False, secret=True),
        "openalex_api_key": _gold_env_field(os.environ.get(config.literature.openalex_api_key_env, ""), "secret", required=False, secret=True),
    }
    missing = [field for field, item in required.items() if item["status"] == "missing"]
    invalid = [field for field, item in required.items() if item["status"] in {"invalid", "placeholder", "mismatch"}]
    mismatched = [field for field, item in required.items() if item["status"] == "mismatch"]
    optional_missing = [field for field, item in optional.items() if item["status"] == "missing_optional"]
    return {
        "schema_version": 1,
        "status": "ready" if not (missing or invalid) else "blocked",
        "required_ready": not (missing or invalid),
        "required_fields": required,
        "optional_fields": optional,
        "missing_required_fields": missing,
        "invalid_required_fields": invalid,
        "expected_mismatch_fields": mismatched,
        "missing_optional_fields": optional_missing,
        "target_environment": _gold_environment_target_summary(required),
        "secret_policy": "env_only",
        "safe_to_render": True,
        "next_steps": _gold_environment_next_steps(missing, invalid, optional_missing),
    }


def render_gold_environment_lint_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Gold Environment Lint",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- 必填 ready：{'是' if report.get('required_ready') else '否'}",
        f"- Secret policy：`{report.get('secret_policy') or '-'}`",
        f"- 忽略的 payload secret 字段：{', '.join(_string_list(report.get('ignored_payload_secret_fields'))) or '-'}",
        "",
        "## Required Fields",
        "| Field | Status | Kind | Configured | Expected match |",
        "| --- | --- | --- | --- | --- |",
    ]
    required = report.get("required_fields") if isinstance(report.get("required_fields"), dict) else {}
    for field, item in required.items():
        if isinstance(item, dict):
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(field)),
                        _cell(str(item.get("status") or "-")),
                        _cell(str(item.get("kind") or "-")),
                        "yes" if item.get("configured") else "no",
                        _expected_match_cell(item),
                    ]
                )
                + " |"
            )
    optional = report.get("optional_fields") if isinstance(report.get("optional_fields"), dict) else {}
    if optional:
        lines.extend(["", "## Optional Fields", "| Field | Status | Kind | Configured |", "| --- | --- | --- | --- |"])
        for field, item in optional.items():
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(field)),
                            _cell(str(item.get("status") or "-")),
                            _cell(str(item.get("kind") or "-")),
                            "yes" if item.get("configured") else "no",
                        ]
                    )
                    + " |"
                )
    lines.extend(["", "## Next Steps"])
    steps = _string_list(report.get("next_steps"))
    lines.extend(f"- {item}" for item in steps) if steps else lines.append("- 无")
    lines.append("")
    target = report.get("target_environment") if isinstance(report.get("target_environment"), dict) else {}
    if target:
        lines.append("")
        lines.append(
            "目标环境一致性："
            + (
                "已匹配"
                if target.get("status") == "matched"
                else "未设置目标"
                if target.get("status") == "not_configured"
                else "不匹配"
            )
        )
    lines.append("该检查只读取服务端环境变量是否已配置、格式是否有效以及是否匹配配置目标；不会读取、记录或返回任何 secret 值。")
    return "\n".join(lines)


def _gold_env_field(value: str, kind: str, *, required: bool, secret: bool, expected: str = "") -> dict[str, Any]:
    text = str(value or "").strip()
    expected_text = str(expected or "").strip()
    expected_configured = bool(expected_text and not secret)
    base = {"required": required, "secret": secret, "configured": bool(text), "kind": kind, "expected_configured": expected_configured, "matches_expected": None}
    if not text:
        return {**base, "valid": False, "status": "missing" if required else "missing_optional", "matches_expected": False if expected_configured else None}
    if secret and _placeholder_secret(text):
        return {**base, "valid": False, "status": "placeholder"}
    if kind == "url" and not _looks_like_url(text):
        return {**base, "valid": False, "status": "invalid", "matches_expected": False if expected_configured else None}
    if kind == "email" and not valid_contact_email(text):
        return {**base, "valid": False, "status": "invalid", "matches_expected": False if expected_configured else None}
    if expected_configured and not _gold_env_matches_expected(text, expected_text, kind):
        return {**base, "valid": False, "status": "mismatch", "matches_expected": False}
    return {**base, "valid": True, "status": "pass", "matches_expected": True if expected_configured else None}


def _gold_env_matches_expected(value: str, expected: str, kind: str) -> bool:
    if kind == "url":
        return value.rstrip("/") == expected.rstrip("/")
    return value == expected


def _gold_environment_target_summary(required: dict[str, dict[str, Any]]) -> dict[str, Any]:
    expected_fields = [field for field, item in required.items() if item.get("expected_configured")]
    mismatched = [field for field, item in required.items() if item.get("expected_configured") and item.get("matches_expected") is False]
    if not expected_fields:
        status = "not_configured"
    elif mismatched:
        status = "mismatch"
    else:
        status = "matched"
    return {
        "status": status,
        "expected_fields": expected_fields,
        "mismatched_fields": mismatched,
        "safe_to_render": True,
    }


def _expected_match_cell(item: dict[str, Any]) -> str:
    if not item.get("expected_configured"):
        return "n/a"
    return "yes" if item.get("matches_expected") is True else "no"


def _gold_environment_next_steps(missing: list[str], invalid: list[str], optional_missing: list[str]) -> list[str]:
    if not missing and not invalid:
        steps = ["服务端环境已满足 gold run 的必填启动凭据。"]
        if optional_missing:
            steps.append("可选文献 API key 未全部配置；公共源仍可运行，但正式 online probe 可能更容易限流。")
        return steps
    labels = {
        "llm_base_url": "设置服务端 LLM base URL 环境变量，指向配置的 OpenAI-compatible gateway。",
        "llm_model": "设置服务端 LLM model 环境变量为配置的目标模型名。",
        "llm_api_key": "设置服务端 LLM API key 环境变量；不要通过 Web 表单或 CLI 参数传 secret。",
        "literature_contact_email": "设置真实文献检索 contact email 环境变量，用于 OpenAlex/Crossref/PubMed 联系信息。",
    }
    return [labels.get(field, f"修复 {field}。") for field in _unique_strings([*missing, *invalid])]


def _build_launch_manifest(
    report: dict[str, Any],
    *,
    config: AgentConfig,
    benchmark_pack_run_dir: Path | None,
    fulltext_grounding_run_dir: Path | None,
    candidate_run_dir: Path | None,
) -> dict[str, Any]:
    checks = [item for item in report.get("checks", []) if isinstance(item, dict)]
    status = str(report.get("status") or "")
    failed = _launch_blocking_check_names(checks)
    warnings = _check_names_by_status(checks, "warn")
    launch_review = _launch_review_check_names(checks)
    can_start = not failed and not launch_review
    direct_secret_fields = _direct_secret_fields(config)
    launch_status = "ready_to_start" if can_start else "blocked" if failed else "needs_review"
    manifest = {
        "schema_version": 1,
        "topic": str(report.get("topic") or ""),
        "status": launch_status,
        "can_start_gold_run": can_start,
        "doctor_status": status,
        "preflight_status": str(report.get("preflight_status") or ""),
        "check_status_counts": _check_status_counts(checks),
        "failed_checks": failed,
        "warn_checks": warnings,
        "launch_review_checks": launch_review,
        "nonblocking_warn_checks": [name for name in warnings if name not in launch_review],
        "credential_sources": _credential_sources(config),
        "secret_handling": {
            "required_env_vars": [config.llm.base_url_env, config.llm.model_env, config.llm.api_key_env, config.literature.contact_email_env],
            "optional_env_vars": [config.literature.semantic_scholar_api_key_env, config.literature.openalex_api_key_env],
            "direct_secret_fields": direct_secret_fields,
            "secrets_in_config": bool(direct_secret_fields),
            "safe_to_render": True,
        },
        "literature": _launch_literature_summary(config),
        "benchmark": _launch_benchmark_summary(config, benchmark_pack_run_dir=benchmark_pack_run_dir),
        "fulltext_grounding": {
            "standalone_run_provided": fulltext_grounding_run_dir is not None,
            "standalone_run_id": _path_name(fulltext_grounding_run_dir),
        },
        "candidate_run": {
            "provided": candidate_run_dir is not None,
            "run_id": _path_name(candidate_run_dir),
        },
        "release_metadata": _launch_release_summary(config),
        "required_human_gates": ["01-review-gate approval", "03-execution-approval for local/benchmark execution"],
        "required_final_evidence": [
            "01-literature-gate-decision.json paper_grade_literature=pass",
            "04-benchmark-evidence-audit.json evidence_grade=real_benchmark and adapter_paper_grade_status=ready",
            "10-claim-traceability.json status=pass and blocked_claims=0",
            "10-claim-consistency.json status=pass",
            "10-final-readiness.json ready_for_submission_check for upload-ready or ready_for_human_polish+",
            "10-release-metadata.json status=ready_for_release",
            "11-submission-package.json non-blocked",
            "11-submission-package.zip is readable and contains package-manifest/checklist entries",
            "13-run-economics-audit.json status=pass",
            "13-research-scorecard.json non-blocked",
            "14-run-integrity-audit.json pass/non-blocked",
            "14-final-handoff.json ready_for_human_handoff or ready_for_submission_upload",
        ],
        "safe_commands": [str(item) for item in report.get("commands", []) if str(item).strip()],
    }
    manifest["launch_checklist"] = _launch_checklist(manifest)
    manifest["launch_readiness"] = _launch_readiness(manifest)
    return manifest


def _render_launch_manifest_section(manifest: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Gold Launch Manifest",
        f"- 状态：{manifest.get('status') or '-'}",
        f"- 可启动 gold run：{'是' if manifest.get('can_start_gold_run') else '否'}",
        f"- Doctor：{manifest.get('doctor_status') or '-'}；Preflight：{manifest.get('preflight_status') or '-'}",
        f"- 失败检查：{', '.join(_string_list(manifest.get('failed_checks'))) or '-'}",
        f"- 警告检查：{', '.join(_string_list(manifest.get('warn_checks'))) or '-'}",
        "",
        "### Secret Handling",
    ]
    secret = manifest.get("secret_handling") if isinstance(manifest.get("secret_handling"), dict) else {}
    lines.append(f"- secret 仅记录来源和值是否存在：{'是' if secret.get('safe_to_render') else '否'}")
    lines.append(f"- 通过配置直接传入的 secret 字段：{', '.join(_string_list(secret.get('direct_secret_fields'))) or '-'}")
    literature = manifest.get("literature") if isinstance(manifest.get("literature"), dict) else {}
    benchmark = manifest.get("benchmark") if isinstance(manifest.get("benchmark"), dict) else {}
    release = manifest.get("release_metadata") if isinstance(manifest.get("release_metadata"), dict) else {}
    readiness = manifest.get("launch_readiness") if isinstance(manifest.get("launch_readiness"), dict) else {}
    lines.extend(
        [
            "",
            "### Launch Inputs",
            f"- literature_provider：`{literature.get('provider') or '-'}`；sources：`{', '.join(_string_list(literature.get('sources'))) or '-'}`",
            f"- seed papers：`{literature.get('seed_papers') or 0}`；DOI/URL seed：`{literature.get('doi_url_seed_papers') or 0}`；fulltext paths：`{literature.get('fulltext_paths') or 0}`",
            f"- execution_mode：`{benchmark.get('execution_mode') or '-'}`；repeats：`{benchmark.get('execution_repeats') or 0}`；manifests：`{benchmark.get('benchmark_manifest_paths') or 0}`",
            f"- benchmark pack run：`{benchmark.get('standalone_pack_run_id') or '-'}`",
            f"- release required ready：{'是' if release.get('required_ready') else '否'}；missing：`{', '.join(_string_list(release.get('missing_required_fields'))) or '-'}`；invalid：`{', '.join(_string_list(release.get('invalid_required_fields'))) or '-'}`",
            "",
            "### Launch Readiness",
            f"- 状态：`{readiness.get('status') or '-'}`；可启动：{'是' if readiness.get('can_start_gold_run') else '否'}",
            f"- 阻断项：`{', '.join(_string_list(readiness.get('blocking_items'))) or '-'}`；需复核：`{', '.join(_string_list(readiness.get('review_items'))) or '-'}`",
            f"- Secret policy：`{readiness.get('secret_policy') or '-'}`；safe command count：`{readiness.get('safe_launch_command_count') or 0}`",
            "",
            "### Checklist",
            "| Item | Status | Evidence | Form fields | Next step |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in manifest.get("launch_checklist", []) if isinstance(manifest.get("launch_checklist"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(str(item.get("item") or "")),
                    _cell(str(item.get("status") or "")),
                    _cell(str(item.get("evidence") or "")),
                    _cell(", ".join(_string_list(item.get("form_fields")))),
                    _cell(str(item.get("next_step") or "")),
                ]
            )
            + " |"
        )
    return lines


def _launch_readiness(manifest: dict[str, Any]) -> dict[str, Any]:
    checklist = [item for item in manifest.get("launch_checklist", []) if isinstance(item, dict)]
    blocking_items = [
        str(item.get("item") or "")
        for item in checklist
        if str(item.get("status") or "") in {"block", "fail"} and str(item.get("item") or "")
    ]
    review_items = [
        str(item.get("item") or "")
        for item in checklist
        if str(item.get("status") or "") == "warn" and str(item.get("item") or "")
    ]
    secret = manifest.get("secret_handling") if isinstance(manifest.get("secret_handling"), dict) else {}
    literature = manifest.get("literature") if isinstance(manifest.get("literature"), dict) else {}
    benchmark = manifest.get("benchmark") if isinstance(manifest.get("benchmark"), dict) else {}
    release = manifest.get("release_metadata") if isinstance(manifest.get("release_metadata"), dict) else {}
    can_start = manifest.get("can_start_gold_run") is True
    status = "ready_to_start" if can_start else "blocked" if blocking_items else "needs_review"
    return {
        "schema_version": 1,
        "status": status,
        "can_start_gold_run": can_start,
        "blocking_items": blocking_items,
        "review_items": review_items,
        "required_before_start": [_launch_next_step_for_item(checklist, item) for item in blocking_items],
        "review_before_start": [_launch_next_step_for_item(checklist, item) for item in review_items],
        "secret_policy": "env_only" if not secret.get("direct_secret_fields") else "move_secrets_to_env",
        "paper_grade_contract": {
            "literature": literature.get("paper_grade_ready") is True,
            "benchmark": benchmark.get("benchmark_ready") is True,
            "release_metadata": release.get("required_ready") is True,
        },
        "safe_launch_command_count": len(manifest.get("safe_commands", [])) if isinstance(manifest.get("safe_commands"), list) else 0,
    }


def _launch_next_step_for_item(checklist: list[dict[str, Any]], item_name: str) -> str:
    for item in checklist:
        if str(item.get("item") or "") == item_name:
            return str(item.get("next_step") or "").strip()
    return ""


def _launch_checklist(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    literature = manifest.get("literature") if isinstance(manifest.get("literature"), dict) else {}
    benchmark = manifest.get("benchmark") if isinstance(manifest.get("benchmark"), dict) else {}
    release = manifest.get("release_metadata") if isinstance(manifest.get("release_metadata"), dict) else {}
    secret = manifest.get("secret_handling") if isinstance(manifest.get("secret_handling"), dict) else {}
    candidate = manifest.get("candidate_run") if isinstance(manifest.get("candidate_run"), dict) else {}
    launch_blocking = _string_list(manifest.get("failed_checks"))
    launch_review = _string_list(manifest.get("launch_review_checks"))
    return [
        _launch_item(
            "doctor_ready",
            "block" if launch_blocking else "warn" if launch_review else "pass",
            f"doctor_status={manifest.get('doctor_status') or '-'}",
            [],
            "Resolve failed Gold Doctor checks, then rerun Gold Doctor.",
        ),
        _launch_item(
            "preflight_pass",
            "pass" if _launch_preflight_ready(manifest) else "block",
            f"preflight_status={manifest.get('preflight_status') or '-'}",
            [],
            "Run Preflight and fix failed preflight checks before launch.",
        ),
        _launch_item(
            "secrets_via_environment",
            "pass" if not secret.get("direct_secret_fields") else "warn",
            f"direct_secret_fields={','.join(_string_list(secret.get('direct_secret_fields'))) or '-'}",
            ["llm_api_key", "semantic_scholar_api_key", "openalex_api_key"],
            "Move secret values to environment variables before a real run; leave Web/config secret fields empty.",
        ),
        _launch_item(
            "paper_grade_literature",
            "pass" if literature.get("paper_grade_ready") else "block",
            (
                f"provider={literature.get('provider') or '-'}; "
                f"sources={literature.get('source_count') or 0}/{literature.get('min_literature_sources') or 0}; "
                f"seeds={literature.get('seed_papers') or 0}/{literature.get('min_seed_papers') or 0}; "
                f"doi_url={literature.get('doi_url_seed_papers') or 0}/{literature.get('min_doi_url_seed_papers') or 0}"
            ),
            ["literature_provider", "literature_sources", "seed_papers", "fulltext_paths", "max_papers", "max_search_queries", "extra_search_queries"],
            "Use online/auto literature with configured source and DOI/URL seed counts meeting paper_grade thresholds; run Literature Preview.",
        ),
        _launch_item(
            "benchmark_manifest",
            "pass" if benchmark.get("benchmark_ready") else "block",
            (
                f"mode={benchmark.get('execution_mode') or '-'}; "
                f"manifests={benchmark.get('benchmark_manifest_paths') or 0}/{benchmark.get('min_benchmark_roles') or 0}; "
                f"repeats={benchmark.get('execution_repeats') or 0}/{benchmark.get('min_execution_repeats') or 0}"
            ),
            ["execution_mode", "execution_repeats", "benchmark_manifests"],
            (
                f"Use benchmark execution with repeats >= {benchmark.get('min_execution_repeats') or 0} "
                f"and at least {benchmark.get('min_benchmark_roles') or 0} candidate/baseline/ablation manifests; run Benchmark Preview."
            ),
        ),
        _launch_item(
            "release_metadata",
            "pass" if release.get("required_ready") else "block",
            f"missing={','.join(_string_list(release.get('missing_required_fields'))) or '-'}; invalid={','.join(_string_list(release.get('invalid_required_fields'))) or '-'}",
            [
                "release_code_repository_url",
                "release_code_archive_doi",
                "release_code_license",
                "release_code_version",
                "release_data_access_statement",
                "release_environment_url",
            ],
            "Fill real release metadata: code repository/archive, license, version, data access statement, and environment URL.",
        ),
        _launch_item(
            "candidate_run_optional",
            "pass" if candidate.get("provided") else "warn",
            "candidate_run_dir provided" if candidate.get("provided") else "no candidate run supplied; startup doctor only",
            ["candidate_run_id"],
            "Optional before launch; after a candidate run finishes, rerun Gold Doctor against that run for final gold evidence.",
        ),
    ]


def _launch_item(item: str, status: str, evidence: str, form_fields: list[str], next_step: str) -> dict[str, Any]:
    return {"item": item, "status": status, "evidence": evidence, "form_fields": form_fields, "next_step": next_step}


def _launch_literature_summary(config: AgentConfig) -> dict[str, Any]:
    seeds = [str(item).strip() for item in config.literature.seed_papers if str(item).strip()]
    doi_url_seeds = [item for item in seeds if _looks_like_doi(item) or _looks_like_url(item)]
    provider = str(config.literature.provider or "").strip()
    sources = [str(item).strip() for item in config.literature.sources if str(item).strip()]
    min_literature_sources = max(1, int(config.paper_grade.min_literature_sources or 0))
    min_seed_papers = max(1, int(config.paper_grade.min_seed_papers or 0))
    min_doi_url_seed_papers = max(1, int(config.paper_grade.min_doi_url_seed_papers or 0))
    return {
        "provider": provider,
        "sources": sources,
        "source_count": len(sources),
        "min_literature_sources": min_literature_sources,
        "max_papers": int(config.literature.max_papers or 0),
        "max_search_queries": int(config.literature.max_search_queries or 0),
        "seed_papers": len(seeds),
        "min_seed_papers": min_seed_papers,
        "doi_url_seed_papers": len(doi_url_seeds),
        "min_doi_url_seed_papers": min_doi_url_seed_papers,
        "fulltext_paths": len([item for item in config.literature.fulltext_paths if str(item).strip()]),
        "paper_grade_ready": (
            provider in {"online", "auto"}
            and len(sources) >= min_literature_sources
            and len(seeds) >= min_seed_papers
            and len(doi_url_seeds) >= min_doi_url_seed_papers
        ),
    }


def _launch_benchmark_summary(config: AgentConfig, *, benchmark_pack_run_dir: Path | None) -> dict[str, Any]:
    manifests = [str(item).strip() for item in config.execution.benchmark_manifest_paths if str(item).strip()]
    min_benchmark_roles = max(1, int(config.paper_grade.min_benchmark_roles or 0))
    min_execution_repeats = max(1, int(config.paper_grade.min_execution_repeats or 0))
    return {
        "execution_mode": str(config.execution.mode or ""),
        "execution_repeats": int(config.execution.repeats or 0),
        "min_execution_repeats": min_execution_repeats,
        "timeout_seconds": int(config.execution.timeout_seconds or 0),
        "allowed_commands": [str(item).strip() for item in config.execution.allowed_commands if str(item).strip()],
        "benchmark_manifest_paths": len(manifests),
        "min_benchmark_roles": min_benchmark_roles,
        "benchmark_manifest_names": [_path_name(item) for item in manifests[:12]],
        "standalone_pack_run_provided": benchmark_pack_run_dir is not None,
        "standalone_pack_run_id": _path_name(benchmark_pack_run_dir),
        "benchmark_ready": str(config.execution.mode or "") == "benchmark" and len(manifests) >= min_benchmark_roles and int(config.execution.repeats or 0) >= min_execution_repeats,
    }


def _launch_release_summary(config: AgentConfig) -> dict[str, Any]:
    field_status = _release_field_statuses(config)
    missing = [field for field, item in field_status.items() if item["status"] == "missing"]
    invalid = [field for field, item in field_status.items() if item["status"] == "invalid"]
    placeholders = [field for field, item in field_status.items() if item["status"] == "placeholder"]
    present = [field for field, item in field_status.items() if item["present"]]
    return {
        "required_fields": list(field_status),
        "present_required_fields": present,
        "missing_required_fields": missing,
        "invalid_required_fields": invalid,
        "placeholder_required_fields": placeholders,
        "required_ready": not (missing or invalid or placeholders),
    }


def _release_field_statuses(config: AgentConfig) -> dict[str, dict[str, Any]]:
    release = config.release
    required = {
        "release_code_repository_url": (release.code_repository_url, "url"),
        "release_code_archive_doi": (release.code_archive_doi, "doi_or_url"),
        "release_code_license": (release.code_license, "text"),
        "release_code_version": (release.code_version, "text"),
        "release_data_access_statement": (release.data_access_statement, "text"),
        "release_environment_url": (release.environment_url, "url"),
    }
    return {field: _release_field_status(value, kind) for field, (value, kind) in required.items()}


def _optional_release_field_statuses(config: AgentConfig) -> dict[str, dict[str, Any]]:
    release = config.release
    optional = {
        "release_data_repository_url": (release.data_repository_url, "url"),
        "release_data_archive_doi": (release.data_archive_doi, "doi_or_url"),
        "release_notes": (release.release_notes, "text"),
    }
    result: dict[str, dict[str, Any]] = {}
    for field, (value, kind) in optional.items():
        text = str(value or "").strip()
        if not text:
            result[field] = {"present": False, "status": "missing_optional", "kind": kind}
        else:
            result[field] = _release_field_status(text, kind)
    return result


def _release_field_status(value: str, kind: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {"present": False, "status": "missing", "kind": kind}
    if _placeholder_release_value(text):
        return {"present": True, "status": "placeholder", "kind": kind}
    if kind == "url" and not _looks_like_url(text):
        return {"present": True, "status": "invalid", "kind": kind}
    if kind == "doi_or_url" and not (_looks_like_doi(text) or _looks_like_url(text)):
        return {"present": True, "status": "invalid", "kind": kind}
    return {"present": True, "status": "pass", "kind": kind}


def _gold_release_metadata_next_steps(blocking_fields: list[str]) -> list[str]:
    if not blocking_fields:
        return ["Release metadata meets the stricter Gold Doctor startup contract."]
    labels = {
        "release_code_repository_url": "填写公开代码仓库 URL。",
        "release_code_archive_doi": "填写代码归档 DOI 或稳定 URL。",
        "release_code_license": "填写代码许可证。",
        "release_code_version": "填写 release tag、commit SHA 或版本号。",
        "release_data_access_statement": "填写数据来源、访问条件、限制，或说明未使用外部数据。",
        "release_environment_url": "填写 Docker/Conda/requirements 等环境归档 URL。",
        "release_data_repository_url": "数据仓库 URL 必须是公开 http(s) URL，且不能是占位值。",
        "release_data_archive_doi": "数据归档 DOI 必须是 DOI 或稳定 URL。",
    }
    return [labels.get(field, f"修复 {field}。") for field in _unique_strings(blocking_fields)]


def _credential_sources(config: AgentConfig) -> dict[str, dict[str, Any]]:
    return {
        "llm_base_url": _credential_source(config.llm.base_url, config.llm.base_url_env, secret=False),
        "llm_model": _credential_source(config.llm.model, config.llm.model_env, secret=False),
        "llm_api_key": _credential_source(config.llm.api_key, config.llm.api_key_env, secret=True),
        "literature_contact_email": _credential_source(config.literature.contact_email, config.literature.contact_email_env, secret=False),
        "semantic_scholar_api_key": _credential_source(config.literature.semantic_scholar_api_key, config.literature.semantic_scholar_api_key_env, secret=True),
        "openalex_api_key": _credential_source(config.literature.openalex_api_key, config.literature.openalex_api_key_env, secret=True),
    }


def _credential_source(value: str, env_name: str, *, secret: bool) -> dict[str, Any]:
    source = "env" if os.environ.get(env_name, "").strip() else "config" if str(value or "").strip() else "missing"
    return {"env": env_name, "source": source, "configured": source != "missing", "secret": secret}


def _direct_secret_fields(config: AgentConfig) -> list[str]:
    fields: list[str] = []
    if str(config.llm.api_key or "").strip() and not os.environ.get(config.llm.api_key_env, "").strip():
        fields.append("llm_api_key")
    if str(config.literature.semantic_scholar_api_key or "").strip() and not os.environ.get(config.literature.semantic_scholar_api_key_env, "").strip():
        fields.append("semantic_scholar_api_key")
    if str(config.literature.openalex_api_key or "").strip() and not os.environ.get(config.literature.openalex_api_key_env, "").strip():
        fields.append("openalex_api_key")
    return fields


def _check_status_counts(checks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in checks:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _check_names_by_status(checks: list[dict[str, Any]], status: str) -> list[str]:
    return [str(item.get("name") or "") for item in checks if str(item.get("status") or "") == status and str(item.get("name") or "")]


def _launch_blocking_check_names(checks: list[dict[str, Any]]) -> list[str]:
    return _check_names_by_status(checks, "fail")


def _launch_review_check_names(checks: list[dict[str, Any]]) -> list[str]:
    preflight_contract_nonpass = _preflight_contract_nonpass_check_names(checks)
    ignored = set(_NONBLOCKING_STARTUP_WARN_CHECKS)
    if not preflight_contract_nonpass:
        ignored.add("preflight:overall")
    return [name for name in _check_names_by_status(checks, "warn") if name not in ignored]


def _preflight_contract_nonpass_check_names(checks: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for item in checks:
        name = str(item.get("name") or "")
        if not name.startswith("preflight:") or name == "preflight:overall":
            continue
        if str(item.get("status") or "") != "pass":
            result.append(name)
    return result


def _launch_preflight_ready(manifest: dict[str, Any]) -> bool:
    blocking = [item for item in _string_list(manifest.get("failed_checks")) if item.startswith("preflight:")]
    review = [item for item in _string_list(manifest.get("launch_review_checks")) if item.startswith("preflight:")]
    return not blocking and not review


def _write_candidate_repair_resume_plan(
    report: dict[str, Any],
    *,
    candidate_run_dir: Path | None,
    doctor_report_path: Path,
) -> dict[str, Any]:
    if candidate_run_dir is None:
        return {"status": "skipped_missing_candidate_run_dir", "can_resume": False}
    if not _candidate_repair_plan_from_report(report):
        return {
            "status": "skipped_no_candidate_repair_plan",
            "candidate_run_dir": str(candidate_run_dir),
            "can_resume": False,
        }
    plan = write_repair_resume_plan_artifacts(candidate_run_dir, apply=False, doctor_report_path=doctor_report_path)
    return {
        "status": "written",
        "candidate_run_dir": str(candidate_run_dir),
        "doctor_report_path": str(doctor_report_path),
        "plan_json": str(candidate_run_dir / REPAIR_RESUME_PLAN_JSON),
        "plan_md": str(candidate_run_dir / REPAIR_RESUME_PLAN_MD),
        "can_resume": plan.get("can_resume") is True,
        "rerun_from": str(plan.get("rerun_from") or ""),
        "repair_items": len(plan.get("repair_items", [])) if isinstance(plan.get("repair_items"), list) else 0,
    }


def _credential_checks(config: AgentConfig) -> list[dict[str, str]]:
    llm = config.llm
    literature = config.literature
    base_url_ok = _configured(llm.base_url, llm.base_url_env)
    model_ok = _configured(llm.model, llm.model_env)
    api_key_ok = _configured_secret(llm.api_key, llm.api_key_env)
    email_ok = _configured_contact_email(literature.contact_email, literature.contact_email_env)
    return [
        _check(
            "llm_base_url_explicit",
            "pass" if base_url_ok else "fail",
            _credential_detail(llm.base_url, llm.base_url_env),
            "" if base_url_ok else f"设置 {llm.base_url_env}，例如 {DEFAULT_LOCAL_GATEWAY_BASE_URL} 或 https://api.openai.com/v1。",
        ),
        _check(
            "llm_model",
            "pass" if model_ok else "fail",
            _credential_detail(llm.model, llm.model_env),
            "" if model_ok else f"设置 {llm.model_env} 为真实模型名。",
        ),
        _check(
            "llm_api_key",
            "pass" if api_key_ok else "fail",
            _credential_detail(llm.api_key, llm.api_key_env, valid=api_key_ok),
            "" if api_key_ok else f"设置 {llm.api_key_env}；doctor 不会记录密钥值。",
        ),
        _check(
            "literature_contact_email",
            "pass" if email_ok else "fail",
            _credential_detail(literature.contact_email, literature.contact_email_env, valid=email_ok),
            "" if email_ok else f"设置真实 {literature.contact_email_env}，用于 OpenAlex/Crossref/PubMed 联系信息；不要使用 example.org 或 <contact-email> 占位符。",
        ),
        _check(
            "semantic_scholar_key",
            "pass" if _configured_secret(literature.semantic_scholar_api_key, literature.semantic_scholar_api_key_env) else "warn",
            _credential_detail(
                literature.semantic_scholar_api_key,
                literature.semantic_scholar_api_key_env,
                valid=_configured_secret(literature.semantic_scholar_api_key, literature.semantic_scholar_api_key_env),
            ),
            "可选；缺失时 online probe 可能更容易遇到限流。",
        ),
        _check(
            "openalex_key",
            "pass" if _configured_secret(literature.openalex_api_key, literature.openalex_api_key_env) else "warn",
            _credential_detail(
                literature.openalex_api_key,
                literature.openalex_api_key_env,
                valid=_configured_secret(literature.openalex_api_key, literature.openalex_api_key_env),
            ),
            "可选；有 key 时 online probe 更稳定。",
        ),
    ]


def _preflight_contract_checks(preflight: PreflightReport) -> list[dict[str, str]]:
    by_name = {item.name: item for item in preflight.checks}
    required = [
        "paper_grade_mode",
        "paper_grade_literature_provider",
        "paper_grade_literature_sources",
        "paper_grade_seed_papers",
        "paper_grade_seed_roles",
        "fulltext_paths",
        "paper_grade_execution_mode",
        "paper_grade_execution_repeats",
        "paper_grade_benchmark_manifests",
        "benchmark_adapter_audit",
        "release_metadata",
    ]
    checks: list[dict[str, str]] = []
    for name in required:
        item = by_name.get(name)
        status = "fail" if item is None or item.status == "fail" else "pass" if item.status == "pass" else "warn"
        detail = "missing" if item is None else f"{item.status}: {item.summary}" + (f"; {item.detail}" if item.detail else "")
        action = "修复 preflight 对应检查项后再启动 gold run。" if status == "fail" else ""
        checks.append(_check(f"preflight:{name}", status, detail, action))
    return checks


def _credential_transport_check(config: AgentConfig) -> dict[str, str]:
    direct_secret_fields: list[str] = []
    if str(config.llm.api_key or "").strip() and not os.environ.get(config.llm.api_key_env, "").strip():
        direct_secret_fields.append("llm_api_key")
    if str(config.literature.semantic_scholar_api_key or "").strip() and not os.environ.get(config.literature.semantic_scholar_api_key_env, "").strip():
        direct_secret_fields.append("semantic_scholar_api_key")
    if str(config.literature.openalex_api_key or "").strip() and not os.environ.get(config.literature.openalex_api_key_env, "").strip():
        direct_secret_fields.append("openalex_api_key")
    if not direct_secret_fields:
        return _check("credential_transport", "pass", "secrets=env_or_missing")
    return _check(
        "credential_transport",
        "warn",
        "direct_secret_fields=" + ",".join(direct_secret_fields),
        "建议把 API key 放入环境变量，不要通过 CLI 参数或配置文件传入 secret。",
    )


def _gold_release_metadata_check(config: AgentConfig) -> dict[str, str]:
    release = config.release
    required = {
        "release_code_repository_url": ("code_repository_url", release.code_repository_url, "url"),
        "release_code_archive_doi": ("code_archive_doi", release.code_archive_doi, "doi_or_url"),
        "release_code_license": ("code_license", release.code_license, "text"),
        "release_code_version": ("code_version", release.code_version, "text"),
        "release_data_access_statement": ("data_access_statement", release.data_access_statement, "text"),
        "release_environment_url": ("environment_url", release.environment_url, "url"),
    }
    missing: list[str] = []
    invalid: list[str] = []
    placeholders: list[str] = []
    for field, (_metadata_key, value, kind) in required.items():
        text = str(value or "").strip()
        if not text:
            missing.append(field)
            continue
        if _placeholder_release_value(text):
            placeholders.append(field)
            continue
        if kind == "url" and not _looks_like_url(text):
            invalid.append(field)
        if kind == "doi_or_url" and not (_looks_like_doi(text) or _looks_like_url(text)):
            invalid.append(field)
    optional_invalid: list[str] = []
    if release.data_repository_url and (not _looks_like_url(release.data_repository_url) or _placeholder_release_value(release.data_repository_url)):
        optional_invalid.append("release_data_repository_url")
    if release.data_archive_doi and not (_looks_like_doi(release.data_archive_doi) or _looks_like_url(release.data_archive_doi)):
        optional_invalid.append("release_data_archive_doi")
    problems = [*missing, *invalid, *placeholders, *optional_invalid]
    detail_parts = [
        f"required={len(required) - len(set(missing) | set(invalid) | set(placeholders))}/{len(required)}",
    ]
    if missing:
        detail_parts.append("missing=" + ",".join(missing))
    if invalid:
        detail_parts.append("invalid=" + ",".join(invalid))
    if placeholders:
        detail_parts.append("placeholder=" + ",".join(placeholders))
    if optional_invalid:
        detail_parts.append("optional_invalid=" + ",".join(optional_invalid))
    action = "" if not problems else "补齐真实 release metadata：代码仓库、代码归档 DOI/URL、许可证、版本、数据访问说明和环境归档 URL；不得使用 example/scaffold/placeholder。"
    return _check("gold_release_metadata", "fail" if problems else "pass", "; ".join(detail_parts), action)


def _preflight_status_check(preflight: PreflightReport) -> dict[str, str]:
    status = "fail" if preflight.status == "fail" else "warn" if preflight.status == "warn" else "pass"
    failing = [item.name for item in preflight.checks if item.status == "fail"]
    warnings = [item.name for item in preflight.checks if item.status == "warn"]
    detail = f"{preflight.status}; fail={len(failing)}; warn={len(warnings)}"
    if failing:
        detail += "; failing=" + ",".join(failing[:5])
    action = "修复 preflight fail 项后再启动 gold run。" if status == "fail" else ""
    return _check("preflight:overall", status, detail, action)


def _benchmark_pack_run_check(run_dir: Path | None) -> dict[str, str]:
    if run_dir is None:
        return _check("benchmark_pack_run", "warn", "未提供 standalone benchmark pack run 目录", "可先运行 benchmark-pack-run 预验证真实 benchmark。")
    data = _read_dict(run_dir / "04-benchmark-pack-run.json")
    status = str(data.get("status") or "")
    grade = str(data.get("benchmark_evidence_grade") or "")
    results = int(data.get("results") or 0)
    comparisons = int(data.get("comparisons") or 0)
    outcome = str(data.get("statistical_outcome") or "")
    boundary = str(data.get("claim_boundary_severity") or "")
    claim_policy = str(data.get("claim_policy") or "")
    publishable_negative_or_neutral = data.get("publishable_negative_or_neutral_result") is True
    bounded_negative_or_neutral = (
        publishable_negative_or_neutral
        and boundary == "negative_or_neutral_no_superiority"
        and claim_policy == "negative_or_neutral_benchmark_claims_allowed_no_superiority_claims"
    )
    core_ok = grade == "real_benchmark" and results > 0 and comparisons > 0
    ok = core_ok and (status == "pass" or (status == "warn" and bounded_negative_or_neutral))
    review = core_ok and status == "warn" and not bounded_negative_or_neutral
    detail = (
        f"status={status or '-'}; grade={grade or '-'}; results={results}; comparisons={comparisons}; "
        f"outcome={outcome or '-'}; boundary={boundary or '-'}; "
        f"publishable_negative_or_neutral={publishable_negative_or_neutral}; claim_policy={claim_policy or '-'}"
    )
    if ok:
        action = "" if status == "pass" else "可继续 gold run，但论文必须按负/中性结果边界写作，禁止 superiority/stability claim。"
    elif review:
        action = "人工核对 benchmark-pack-run warning；若为负/中性真实结果，需要 04-benchmark-pack-run.json 标明 publishable_negative_or_neutral_result 和无优势 claim policy。"
    else:
        action = "运行 benchmark-pack-run 并确认 04-benchmark-pack-run.json 为 real_benchmark，且有结果、比较和闭合的 claim 边界。"
    return _check(
        "benchmark_pack_run",
        "pass" if ok else "warn" if review else "fail",
        detail,
        action,
    )


def _fulltext_grounding_run_check(run_dir: Path | None) -> dict[str, str]:
    if run_dir is None:
        return _check("fulltext_grounding_run", "warn", "未提供 standalone fulltext grounding run 目录", "可先运行 fulltext-grounding-run 预验证全文 grounding。")
    data = _read_dict(run_dir / "10-fulltext-grounding-run.json")
    status = str(data.get("status") or "")
    grounding = str(data.get("grounding_status") or "")
    chunks = int(data.get("fulltext_chunks") or 0)
    ok = status == "pass" and grounding == "pass" and chunks > 0
    return _check(
        "fulltext_grounding_run",
        "pass" if ok else "fail",
        f"status={status or '-'}; grounding={grounding or '-'}; chunks={chunks}",
        "" if ok else "运行 fulltext-grounding-run 并确认 10-citation-grounding.json pass。",
    )


def _candidate_run_check(run_dir: Path) -> dict[str, str]:
    state = _read_dict(run_dir / "state.json")
    run_config = _read_dict(run_dir / "run-config.json")
    run_manifest = _read_dict(run_dir / "run-manifest.json")
    llm_ledger = _read_dict(run_dir / "run-llm-ledger.json")
    literature = _read_dict(run_dir / "01-literature-gate-decision.json")
    benchmark = _read_dict(run_dir / "04-benchmark-evidence-audit.json")
    claim_traceability = _read_dict(run_dir / "10-claim-traceability.json")
    claim_consistency = _read_dict(run_dir / "10-claim-consistency.json")
    final_readiness = _read_dict(run_dir / "10-final-readiness.json")
    release_metadata = _read_dict(run_dir / "10-release-metadata.json")
    package = _read_dict(run_dir / "11-submission-package.json")
    repair_queue = _read_dict(run_dir / "12-repair-queue.json")
    llm_trace = _read_dict(run_dir / "13-llm-trace-audit.json")
    llm_runtime = _read_dict(run_dir / "13-llm-runtime-contract.json")
    run_economics = _read_dict(run_dir / "13-run-economics-audit.json")
    observability = _read_dict(run_dir / "13-agent-observability-audit.json")
    llm_observability = _read_dict(run_dir / "13-llm-observability-summary.json")
    stage_contract = _read_dict(run_dir / "13-agent-stage-contract.json")
    trajectory = _read_dict(run_dir / "13-agent-trajectory.json")
    scorecard = _read_dict(run_dir / "13-research-scorecard.json")
    integrity = _read_dict(run_dir / "14-run-integrity-audit.json")
    final_handoff = _read_dict(run_dir / "14-final-handoff.json")
    literature_grade = literature.get("paper_grade_literature") if isinstance(literature.get("paper_grade_literature"), dict) else {}
    lit_status = str(literature_grade.get("status") or "")
    bench_status = str(benchmark.get("status") or "")
    bench_grade = str(benchmark.get("evidence_grade") or "")
    adapter_status = str(benchmark.get("adapter_paper_grade_status") or "")
    publishable_negative_or_neutral = benchmark.get("publishable_negative_or_neutral_result") is True
    boundary = str(benchmark.get("claim_boundary_severity") or "")
    trace_status = str(claim_traceability.get("status") or "")
    trace_blockers = _count_list(claim_traceability.get("blocking_issues"))
    trace_blocked_claims = _safe_int(claim_traceability.get("blocked_claims"))
    claim_status = str(claim_consistency.get("status") or "")
    claim_blockers = _count_list(claim_consistency.get("blocking_issues"))
    final_readiness_status = str(final_readiness.get("status") or "")
    final_readiness_blockers = _count_list(final_readiness.get("blocking_issues"))
    final_readiness_unsupported = _safe_int(final_readiness.get("unsupported_after"))
    release_status = str(release_metadata.get("status") or "")
    release_blockers = _count_list(release_metadata.get("blocking_issues"))
    release_manual = _count_list(release_metadata.get("manual_tasks"))
    package_status = str(package.get("status") or "")
    package_blockers = _count_list(package.get("blocking_issues"))
    audit_contracts = {
        "llm_trace": _candidate_audit_contract(llm_trace),
        "llm_runtime": _candidate_audit_contract(llm_runtime),
        "run_economics": _candidate_audit_contract(run_economics),
        "agent_observability": _candidate_audit_contract(observability),
        "llm_observability": _candidate_audit_contract(llm_observability),
        "stage_contract": _candidate_audit_contract(stage_contract),
        "trajectory": _candidate_audit_contract(trajectory),
    }
    scorecard_status = str(scorecard.get("status") or "")
    scorecard_blockers = _count_list(scorecard.get("blocking_issues"))
    integrity_status = str(integrity.get("status") or "")
    integrity_blockers = _count_list(integrity.get("blocking_issues"))
    final_status = str(final_handoff.get("status") or "")
    final_blockers = _count_list(final_handoff.get("blocking_issues"))
    final_zip_exists = final_handoff.get("package_zip_exists") if isinstance(final_handoff.get("package_zip_exists"), bool) else None
    final_zip_valid = final_handoff.get("package_zip_valid") if isinstance(final_handoff.get("package_zip_valid"), bool) else None
    final_zip_ok = final_zip_exists is True and final_zip_valid is True
    repair_summary = repair_queue.get("summary") if isinstance(repair_queue.get("summary"), dict) else {}
    repair_block = _safe_int(repair_summary.get("block"))
    missing = [
        name
        for name, data in [
            ("state.json", state),
            ("run-config.json", run_config),
            ("run-manifest.json", run_manifest),
            ("run-llm-ledger.json", llm_ledger),
            ("01-literature-gate-decision.json", literature),
            ("04-benchmark-evidence-audit.json", benchmark),
            ("10-claim-traceability.json", claim_traceability),
            ("10-claim-consistency.json", claim_consistency),
            ("10-final-readiness.json", final_readiness),
            ("10-release-metadata.json", release_metadata),
            ("11-submission-package.json", package),
            ("12-repair-queue.json", repair_queue),
            ("13-llm-trace-audit.json", llm_trace),
            ("13-llm-runtime-contract.json", llm_runtime),
            ("13-run-economics-audit.json", run_economics),
            ("13-agent-observability-audit.json", observability),
            ("13-llm-observability-summary.json", llm_observability),
            ("13-agent-stage-contract.json", stage_contract),
            ("13-agent-trajectory.json", trajectory),
            ("13-research-scorecard.json", scorecard),
            ("14-run-integrity-audit.json", integrity),
            ("14-final-handoff.json", final_handoff),
        ]
        if not data
    ]
    if not _gold_required_artifact_present(run_dir / "11-submission-package.zip"):
        missing.append("11-submission-package.zip")
    negative_boundary_ok = (not publishable_negative_or_neutral) or boundary == "negative_or_neutral_no_superiority"
    benchmark_boundary_metadata_ok = _benchmark_boundary_metadata_ok(benchmark)
    ok = (
        not missing
        and lit_status == "pass"
        and bench_grade == "real_benchmark"
        and bench_status in {"pass", "warn"}
        and _count_list(benchmark.get("blocking_issues")) == 0
        and adapter_status == "ready"
        and benchmark_boundary_metadata_ok
        and negative_boundary_ok
        and trace_status == "pass"
        and trace_blockers == 0
        and trace_blocked_claims == 0
        and claim_status == "pass"
        and claim_blockers == 0
        and _final_readiness_ready(final_readiness_status, final_readiness_blockers, final_readiness_unsupported, final_status)
        and release_status == "ready_for_release"
        and release_blockers == 0
        and release_manual == 0
        and _candidate_audit_contracts_ready(audit_contracts, final_status)
        and final_status in {"ready_for_human_handoff", "ready_for_submission_upload"}
        and _candidate_handoff_sources_ready(final_status, package_status, package_blockers, scorecard_status, scorecard_blockers, integrity_status, integrity_blockers)
        and final_blockers == 0
        and final_zip_ok
        and repair_block == 0
    )
    detail = (
        f"run={run_dir}; lit={lit_status or '-'}; bench={bench_status or '-'}/{bench_grade or '-'}; "
        f"adapter={adapter_status or '-'}; publishable_negative_or_neutral={publishable_negative_or_neutral}; "
        f"boundary={boundary or '-'}; traceability={trace_status or '-'}:{trace_blockers}/{trace_blocked_claims}; "
        f"claim={claim_status or '-'}:{claim_blockers}; "
        f"final_readiness={final_readiness_status or '-'}:{final_readiness_blockers}/{final_readiness_unsupported}; "
        f"release={release_status or '-'}:{release_blockers}/{release_manual}; "
        f"package={package_status or '-'}:{package_blockers}; "
        f"llm_trace={_candidate_audit_contract_detail(audit_contracts['llm_trace'])}; "
        f"llm_runtime={_candidate_audit_contract_detail(audit_contracts['llm_runtime'])}; "
        f"economics={_candidate_audit_contract_detail(audit_contracts['run_economics'])}; "
        f"agent_observability={_candidate_audit_contract_detail(audit_contracts['agent_observability'])}; "
        f"llm_observability={_candidate_audit_contract_detail(audit_contracts['llm_observability'])}; "
        f"stage_contract={_candidate_audit_contract_detail(audit_contracts['stage_contract'])}; "
        f"trajectory={_candidate_audit_contract_detail(audit_contracts['trajectory'])}; "
        f"scorecard={scorecard_status or '-'}:{scorecard_blockers}; "
        f"integrity={integrity_status or '-'}:{integrity_blockers}; "
        f"final={final_status or '-'}:{final_blockers}; final_zip={_zip_state(final_zip_exists, final_zip_valid)}; repair_block={repair_block}"
    )
    if missing:
        detail += "; missing=" + ",".join(missing)
    repair_plan = [] if ok else _candidate_gold_run_repair_plan(
        missing=missing,
        lit_status=lit_status,
        bench_status=bench_status,
        bench_grade=bench_grade,
        benchmark_blockers=_count_list(benchmark.get("blocking_issues")),
        benchmark_boundary_metadata_ok=benchmark_boundary_metadata_ok,
        adapter_status=adapter_status,
        publishable_negative_or_neutral=publishable_negative_or_neutral,
        negative_boundary_ok=negative_boundary_ok,
        trace_status=trace_status,
        trace_blockers=trace_blockers,
        trace_blocked_claims=trace_blocked_claims,
        claim_status=claim_status,
        claim_blockers=claim_blockers,
        final_readiness_status=final_readiness_status,
        final_readiness_blockers=final_readiness_blockers,
        final_readiness_unsupported=final_readiness_unsupported,
        release_status=release_status,
        release_blockers=release_blockers,
        release_manual=release_manual,
        package_status=package_status,
        package_blockers=package_blockers,
        audit_contracts=audit_contracts,
        scorecard_status=scorecard_status,
        scorecard_blockers=scorecard_blockers,
        integrity_status=integrity_status,
        integrity_blockers=integrity_blockers,
        final_status=final_status,
        final_blockers=final_blockers,
        final_zip_exists=final_zip_exists,
        final_zip_valid=final_zip_valid,
        repair_block=repair_block,
    )
    check = _check("candidate_gold_run", "pass" if ok else "fail", detail, _candidate_gold_run_action(repair_plan))
    audit_contract_policy = _candidate_audit_contract_policy(final_status)
    check["contract_evidence"] = {
        "final_zip_state": _zip_state(final_zip_exists, final_zip_valid),
        "final_handoff_package_zip_exists": final_zip_exists,
        "final_handoff_package_zip_valid": final_zip_valid,
        "final_handoff_status": final_status,
        "audit_contract_policy": audit_contract_policy,
        "audit_contracts_ready": _candidate_audit_contracts_ready(audit_contracts, final_status),
        "audit_contract_ready_count": sum(int(_candidate_audit_contract_ready(item, final_status)) for item in audit_contracts.values()),
        "audit_contract_total": len(audit_contracts),
        "audit_contract_blocking_issues": sum(_candidate_audit_issue_count(item.get("blocking_issues")) for item in audit_contracts.values()),
        "audit_contract_manual_tasks": sum(_candidate_audit_issue_count(item.get("manual_tasks")) for item in audit_contracts.values()),
        "audit_contracts": _candidate_audit_contracts_evidence(audit_contracts, final_status),
    }
    if repair_plan:
        check["repair_plan"] = repair_plan
    return check


def _candidate_audit_contract(report: dict[str, Any]) -> dict[str, Any]:
    has_status = bool(str(report.get("status") or "").strip())
    return {
        "status": str(report.get("status") or ""),
        "blocking_issues": _candidate_audit_issue_count(report.get("blocking_issues"), invalid_count=1 if has_status else 0),
        "manual_tasks": _candidate_audit_issue_count(report.get("manual_tasks"), invalid_count=1 if has_status else 0),
    }


def _candidate_audit_contract_ready(report: dict[str, Any], final_status: str = "") -> bool:
    status = str(report.get("status") or "")
    if _candidate_audit_contract_policy(final_status) == "human_handoff":
        return status in _HUMAN_HANDOFF_AUDIT_STATUSES and _zero_int(report.get("blocking_issues")) and _nonnegative_int(report.get("manual_tasks"))
    return status == "pass" and _zero_int(report.get("blocking_issues")) and _zero_int(report.get("manual_tasks"))


def _candidate_audit_contracts_ready(reports: dict[str, dict[str, Any]], final_status: str = "") -> bool:
    return all(_candidate_audit_contract_ready(report, final_status) for report in reports.values())


def _candidate_audit_contract_detail(report: dict[str, Any]) -> str:
    status = str(report.get("status") or "-")
    return f"{status}:{_candidate_audit_issue_count(report.get('blocking_issues'))}/{_candidate_audit_issue_count(report.get('manual_tasks'))}"


def _candidate_audit_contracts_evidence(reports: dict[str, dict[str, Any]], final_status: str = "") -> dict[str, dict[str, Any]]:
    return {
        key: {
            "status": str(item.get("status") or ""),
            "blocking_issues": _candidate_audit_issue_count(item.get("blocking_issues")),
            "manual_tasks": _candidate_audit_issue_count(item.get("manual_tasks")),
            "ready": _candidate_audit_contract_ready(item, final_status),
            "strict_ready": _candidate_audit_contract_ready(item, "ready_for_submission_upload"),
        }
        for key, item in reports.items()
    }


def _candidate_audit_contract_policy(final_status: str) -> str:
    if final_status == "ready_for_human_handoff":
        return "human_handoff"
    return "submission_upload"


def _candidate_audit_issue_count(value: Any, *, invalid_count: int = 1) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return invalid_count


def _zero_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _verification_final_zip_state(report: dict[str, Any]) -> str:
    evidence = report.get("contract_evidence") if isinstance(report.get("contract_evidence"), dict) else {}
    return str(evidence.get("final_zip_state") or "-")


def _verification_contract_evidence_ready(evidence: dict[str, Any]) -> bool:
    return (
        evidence.get("final_zip_state") == "valid"
        and evidence.get("final_handoff_package_zip_exists") is True
        and evidence.get("final_handoff_package_zip_valid") is True
    )


def _final_readiness_ready(status: str, blockers: int, unsupported: int, final_status: str) -> bool:
    if blockers or unsupported:
        return False
    if final_status == "ready_for_submission_upload":
        return status == "ready_for_submission_check"
    return status in {"ready_for_human_polish", "ready_for_submission_check"}


def _candidate_handoff_sources_ready(
    final_status: str,
    package_status: str,
    package_blockers: int,
    scorecard_status: str,
    scorecard_blockers: int,
    integrity_status: str,
    integrity_blockers: int,
) -> bool:
    if final_status == "ready_for_submission_upload":
        return (
            package_status == "ready_for_human_submission_upload"
            and package_blockers == 0
            and scorecard_status == "ready_for_human_submission_upload"
            and scorecard_blockers == 0
            and integrity_status == "pass"
            and integrity_blockers == 0
        )
    return (
        bool(package_status)
        and package_status != "blocked"
        and package_blockers == 0
        and bool(scorecard_status)
        and scorecard_status != "blocked"
        and scorecard_blockers == 0
        and bool(integrity_status)
        and integrity_status != "block"
        and integrity_blockers == 0
    )


def _benchmark_boundary_metadata_ok(benchmark: dict[str, Any]) -> bool:
    if not benchmark:
        return False
    if str(benchmark.get("evidence_grade") or "") != "real_benchmark":
        return True
    required = ["statistical_outcome", "claim_boundary_severity", "publishable_negative_or_neutral_result", "claim_policy"]
    return all(key in benchmark for key in required)


def _candidate_gold_run_repair_plan(
    *,
    missing: list[str],
    lit_status: str,
    bench_status: str,
    bench_grade: str,
    benchmark_blockers: int,
    benchmark_boundary_metadata_ok: bool,
    adapter_status: str,
    publishable_negative_or_neutral: bool,
    negative_boundary_ok: bool,
    trace_status: str,
    trace_blockers: int,
    trace_blocked_claims: int,
    claim_status: str,
    claim_blockers: int,
    final_readiness_status: str,
    final_readiness_blockers: int,
    final_readiness_unsupported: int,
    release_status: str,
    release_blockers: int,
    release_manual: int,
    package_status: str,
    package_blockers: int,
    audit_contracts: dict[str, dict[str, Any]],
    scorecard_status: str,
    scorecard_blockers: int,
    integrity_status: str,
    integrity_blockers: int,
    final_status: str,
    final_blockers: int,
    final_zip_exists: bool | None,
    final_zip_valid: bool | None,
    repair_block: int,
) -> list[dict[str, Any]]:
    upload_ready = final_status == "ready_for_submission_upload"
    plan: list[dict[str, Any]] = []
    if missing:
        plan.append(
            _candidate_repair_item(
                "missing_candidate_artifacts",
                10,
                "checkpoint",
                "candidate_run",
                missing,
                "重新生成缺失候选产物: " + ",".join(missing) + "。",
            )
        )
    if lit_status != "pass":
        plan.append(
            _candidate_repair_item(
                "paper_grade_literature",
                20,
                "literature_review",
                "01-literature-gate-decision.json",
                ["01-literature-gate-decision.json", "01-seed-paper-intake.json", "01-literature-source-health.json"],
                "修复 01-literature-gate-decision.json：online/auto、多源检索、DOI/URL seed 和 curated seed 必须 pass。",
            )
        )
    if bench_grade != "real_benchmark" or bench_status not in {"pass", "warn"} or benchmark_blockers:
        plan.append(
            _candidate_repair_item(
                "benchmark_evidence",
                30,
                "experiments",
                "04-benchmark-evidence-audit.json",
                ["03-benchmark-adapters.json", "04-benchmark-evidence-audit.json", "04-results.json"],
                "修复 04-benchmark-evidence-audit.json：必须是 real_benchmark、无 blocking issues，并保留真实 candidate/baseline/ablation adapter 证据。",
            )
        )
    elif not benchmark_boundary_metadata_ok:
        plan.append(
            _candidate_repair_item(
                "benchmark_evidence_metadata",
                35,
                "experiments",
                "04-benchmark-evidence-audit.json",
                ["04-benchmark-evidence-audit.json", "04-claim-boundary-preflight.json", "10-claim-consistency.json"],
                "重新生成 04-benchmark-evidence-audit.json：real_benchmark 必须包含 statistical_outcome、claim_boundary_severity、publishable_negative_or_neutral_result 和 claim_policy。",
            )
        )
    if adapter_status != "ready":
        plan.append(
            _candidate_repair_item(
                "benchmark_adapter",
                40,
                "experiment_plan",
                "03-benchmark-adapters.json",
                ["03-benchmark-adapters.json", "03-benchmark-readiness.json", "04-benchmark-evidence-audit.json"],
                "修复 benchmark adapter：candidate/baseline/ablation manifest、共享指标和 repeat policy 必须 ready。",
            )
        )
    if publishable_negative_or_neutral and not negative_boundary_ok:
        plan.append(
            _candidate_repair_item(
                "negative_or_neutral_boundary",
                50,
                "analysis",
                "04-claim-boundary-preflight.json",
                ["04-claim-boundary-preflight.json", "06-paper.md", "09-revised-paper.md", "10-claim-consistency.json"],
                "负/中性结果必须补 no-superiority boundary，即 negative_or_neutral_no_superiority；不能写 superiority claim。",
            )
        )
    if trace_status != "pass" or trace_blockers or trace_blocked_claims:
        plan.append(
            _candidate_repair_item(
                "claim_traceability",
                55,
                "final_readiness",
                "10-claim-traceability.json",
                ["10-claim-traceability.json", "10-citation-grounding.json", "10-citation-coverage.json", "09-revised-paper.md"],
                "修复 10-claim-traceability.json：每个关键 claim 必须可追踪到 citation、结果或 runbook，且 blocked_claims=0。",
            )
        )
    if claim_status != "pass" or claim_blockers:
        plan.append(
            _candidate_repair_item(
                "claim_consistency",
                60,
                "final_readiness",
                "10-claim-consistency.json",
                ["10-claim-consistency.json", "10-final-readiness.json"],
                "修复 10-claim-consistency.json：最终论文 claim 必须与 benchmark、负/中性边界和 citation grounding 一致。",
            )
        )
    if not _final_readiness_ready(final_readiness_status, final_readiness_blockers, final_readiness_unsupported, final_status):
        plan.append(
            _candidate_repair_item(
                "final_readiness",
                62,
                "final_readiness",
                "10-final-readiness.json",
                ["10-final-readiness.json", "10-final-readiness.md", "09-revised-paper.md", "10-claim-traceability.json"],
                "修复 10-final-readiness.json：upload-ready 必须 ready_for_submission_check；human handoff 至少 ready_for_human_polish，且无 blocking/unsupported claims。",
            )
        )
    if release_status != "ready_for_release" or release_blockers or release_manual:
        plan.append(
            _candidate_repair_item(
                "release_metadata",
                65,
                "final_readiness",
                "10-release-metadata.json",
                ["10-release-metadata.json", "10-release-metadata.md", "10-code-data-availability.json", "10-final-readiness.json", "11-submission-package.json"],
                "修复 10-release-metadata.json：候选 gold run 必须达到 ready_for_release，且没有 release blocking/manual tasks。",
            )
        )
    if not package_status or package_status == "blocked" or package_blockers or (upload_ready and package_status != "ready_for_human_submission_upload"):
        plan.append(
            _candidate_repair_item(
                "submission_package",
                70,
                "submission_package",
                "11-submission-package.json",
                ["11-submission-package.json", "11-submission-package.zip"],
                "修复 submission package / 11-submission-package.json：blocked 或仍需 review 的包不能支撑 ready_for_submission_upload。",
            )
        )
    if not _candidate_audit_contract_ready(audit_contracts.get("run_economics", {}), final_status):
        plan.append(
            _candidate_repair_item(
                "run_economics",
                75,
                "checkpoint",
                "13-run-economics-audit.json",
                ["13-run-economics-audit.json", "run-llm-ledger.json", "run-config.json"],
                "修复 13-run-economics-audit.json：gold run 要求 run economics status=pass、无 blocking issues，并保留可复核的 LLM ledger/run config。",
            )
        )
    for spec in _candidate_audit_repair_specs():
        if _candidate_audit_contract_ready(audit_contracts.get(spec["key"], {}), final_status):
            continue
        plan.append(
            _candidate_repair_item(
                str(spec["id"]),
                int(spec["priority"]),
                str(spec["rerun_from"]),
                str(spec["source_artifact"]),
                list(spec["target_artifacts"]),
                str(spec["action"]),
            )
        )
    if not scorecard_status or scorecard_status == "blocked" or scorecard_blockers or (upload_ready and scorecard_status != "ready_for_human_submission_upload"):
        plan.append(
            _candidate_repair_item(
                "research_scorecard",
                80,
                "checkpoint",
                "13-research-scorecard.json",
                ["13-research-scorecard.json", "13-agent-stage-contract.json", "14-run-integrity-audit.json"],
                "修复 13-research-scorecard.json：处理最低分维度、blocking issues 和人工待办后重新生成 scorecard。",
            )
        )
    if not integrity_status or integrity_status == "block" or integrity_blockers or (upload_ready and integrity_status != "pass"):
        plan.append(
            _candidate_repair_item(
                "run_integrity",
                90,
                "checkpoint",
                "14-run-integrity-audit.json",
                ["14-run-integrity-audit.json", "run-manifest.json", "run-config.json"],
                "修复 14-run-integrity-audit.json：ready_for_submission_upload 要求 integrity=pass 且无 blocking issues。",
            )
        )
    if final_status not in {"ready_for_human_handoff", "ready_for_submission_upload"} or final_blockers:
        plan.append(
            _candidate_repair_item(
                "final_handoff",
                100,
                "checkpoint",
                "14-final-handoff.json",
                ["14-final-handoff.json"],
                "重新生成 14-final-handoff.json：只有源产物非阻断后才能进入 handoff/upload-ready。",
            )
        )
    if final_status and (final_zip_exists is not True or final_zip_valid is not True):
        plan.append(
            _candidate_repair_item(
                "final_handoff_zip",
                105,
                "submission_package",
                "14-final-handoff.json",
                ["11-submission-package.zip", "14-final-handoff.json"],
                "重新生成 submission package 和 14-final-handoff.json：final handoff 必须明确报告 ZIP 存在且有效。",
            )
        )
    if repair_block:
        plan.append(
            _candidate_repair_item(
                "repair_queue_blockers",
                110,
                "submission_package",
                "12-repair-queue.json",
                ["12-repair-queue.json", "13-research-scorecard.json", "14-final-handoff.json"],
                "先关闭 12-repair-queue.json 的 block 级修复项，再重新跑 final readiness/handoff。",
            )
        )
    if not plan:
        plan.append(
            _candidate_repair_item(
                "gold_contract",
                999,
                "checkpoint",
                "candidate_run",
                [
                    "01-literature-gate-decision.json",
                    "04-benchmark-evidence-audit.json",
                    "10-claim-traceability.json",
                    "10-claim-consistency.json",
                    "10-final-readiness.json",
                    "10-release-metadata.json",
                    "11-submission-package.json",
                    "11-submission-package.zip",
                    "13-run-economics-audit.json",
                    "13-research-scorecard.json",
                    "14-final-handoff.json",
                ],
                "候选 run 必须通过 online paper-grade literature、real_benchmark adapter、claim traceability、claim consistency、submission package、run economics、scorecard、run integrity、repair queue 和 final handoff。",
            )
        )
    return plan


def _candidate_audit_repair_specs() -> list[dict[str, Any]]:
    return [
        {
            "key": "llm_trace",
            "id": "llm_trace_audit",
            "priority": 72,
            "rerun_from": "checkpoint",
            "source_artifact": "13-llm-trace-audit.json",
            "target_artifacts": ["13-llm-trace-audit.json", "run-llm-ledger.json", "10-ai-disclosure.json"],
            "action": "修复 13-llm-trace-audit.json：gold run 要求 LLM trace status=pass，且无 blocking/manual tasks。",
        },
        {
            "key": "llm_runtime",
            "id": "llm_runtime_contract",
            "priority": 73,
            "rerun_from": "checkpoint",
            "source_artifact": "13-llm-runtime-contract.json",
            "target_artifacts": ["13-llm-runtime-contract.json", "run-config.json", "run-llm-ledger.json", "13-llm-trace-audit.json", "13-run-economics-audit.json"],
            "action": "修复 13-llm-runtime-contract.json：gold run 要求 runtime contract status=pass，且无 blocking/manual tasks。",
        },
        {
            "key": "agent_observability",
            "id": "agent_observability",
            "priority": 76,
            "rerun_from": "checkpoint",
            "source_artifact": "13-agent-observability-audit.json",
            "target_artifacts": ["13-agent-observability-audit.json", "state.json", "run-manifest.json", "run-llm-ledger.json", "12-repair-queue.json"],
            "action": "修复 13-agent-observability-audit.json：gold run 要求 agent observability status=pass，且无 blocking/manual tasks。",
        },
        {
            "key": "llm_observability",
            "id": "llm_observability_summary",
            "priority": 77,
            "rerun_from": "checkpoint",
            "source_artifact": "13-llm-observability-summary.json",
            "target_artifacts": ["13-llm-observability-summary.json", "13-llm-runtime-contract.json", "13-llm-trace-audit.json", "13-run-economics-audit.json", "13-agent-observability-audit.json"],
            "action": "修复 13-llm-observability-summary.json：gold run 要求 LLM observability summary status=pass，且无 blocking/manual tasks。",
        },
        {
            "key": "stage_contract",
            "id": "agent_stage_contract",
            "priority": 78,
            "rerun_from": "checkpoint",
            "source_artifact": "13-agent-stage-contract.json",
            "target_artifacts": ["13-agent-stage-contract.json", "13-agent-observability-audit.json", "13-run-economics-audit.json", "14-run-integrity-audit.json"],
            "action": "修复 13-agent-stage-contract.json：gold run 要求 stage contract status=pass，且无 blocking/manual tasks。",
        },
        {
            "key": "trajectory",
            "id": "agent_trajectory",
            "priority": 79,
            "rerun_from": "checkpoint",
            "source_artifact": "13-agent-trajectory.json",
            "target_artifacts": ["13-agent-trajectory.json", "run-manifest.json", "state.json"],
            "action": "修复 13-agent-trajectory.json：gold run 要求 trajectory status=pass，且无 blocking/manual tasks。",
        },
    ]


def _zip_state(exists: bool | None, valid: bool | None) -> str:
    if exists is False:
        return "missing"
    if valid is False:
        return "invalid"
    if exists is True and valid is True:
        return "valid"
    return "unknown"


def _candidate_repair_item(
    item_id: str,
    priority: int,
    rerun_from: str,
    source_artifact: str,
    target_artifacts: list[str],
    action: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "priority": priority,
        "rerun_from": rerun_from,
        "source_artifact": source_artifact,
        "target_artifacts": target_artifacts,
        "action": action,
    }


def _candidate_gold_run_action(repair_plan: list[dict[str, Any]]) -> str:
    return " ".join(str(item.get("action") or "") for item in repair_plan if isinstance(item, dict) and str(item.get("action") or "").strip())


def _candidate_repair_plan_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    for item in checks:
        if isinstance(item, dict) and item.get("name") == "candidate_gold_run" and isinstance(item.get("repair_plan"), list):
            return [entry for entry in item["repair_plan"] if isinstance(entry, dict)]
    return []


def _preflight_summary(preflight: PreflightReport) -> list[dict[str, str]]:
    return [
        {"name": item.name, "status": item.status, "summary": item.summary, "detail": item.detail, "action": item.action}
        for item in preflight.checks
    ]


def _gold_run_commands(topic: str, config: AgentConfig, *, config_path: Path | None = None) -> list[str]:
    safe_topic = _shell_double(topic)
    base_url = _resolved_setting(config.llm.base_url, config.llm.base_url_env, DEFAULT_LOCAL_GATEWAY_BASE_URL)
    model = _resolved_setting(config.llm.model, config.llm.model_env, DEFAULT_LOCAL_GATEWAY_MODEL)
    config_args = _gold_run_config_args(config, config_path=config_path)
    out_dir = _gold_run_out_dir(topic)
    return [
        f"export {config.llm.base_url_env}={_shell_double(base_url)}",
        f"export {config.llm.model_env}={_shell_double(model)}",
        f'export {config.llm.api_key_env}="<real-key>"',
        f'export {config.literature.contact_email_env}="<contact-email>"',
        f"PYTHONPATH=src python3 -m research_agent run --topic {safe_topic}{config_args} --out {_shell_double(out_dir)}",
        f"PYTHONPATH=src python3 -m research_agent status {_shell_double(out_dir)}",
        f'PYTHONPATH=src python3 -m research_agent approve {_shell_double(out_dir)} --reviewer "human" --notes "Literature gate inspected; DOI/URL seed coverage, source health, and claim boundaries accepted for this gold run."',
        f'PYTHONPATH=src python3 -m research_agent approve-execution {_shell_double(out_dir)} --reviewer "human" --notes "Benchmark manifests, allowed commands, frozen split, and grader hash inspected."',
    ]


def _gold_run_config_args(config: AgentConfig, *, config_path: Path | None = None) -> str:
    if config_path is not None:
        return f" --config {_shell_double(str(config_path))}{_release_command_args(config)}"
    args: list[str] = []
    _append_cli_arg(args, "--llm-max-calls", config.llm.max_calls)
    _append_cli_arg(args, "--llm-max-prompt-chars", config.llm.max_prompt_chars)
    _append_cli_arg(args, "--llm-input-cost-per-million-tokens", config.llm.input_cost_per_million_tokens)
    _append_cli_arg(args, "--llm-output-cost-per-million-tokens", config.llm.output_cost_per_million_tokens)
    _append_cli_arg(args, "--literature-provider", config.literature.provider)
    if config.literature.sources:
        _append_cli_arg(args, "--literature-sources", ",".join(str(item).strip() for item in config.literature.sources if str(item).strip()))
    for seed in config.literature.seed_papers:
        _append_cli_arg(args, "--seed-paper", seed)
    for fulltext_path in config.literature.fulltext_paths:
        _append_cli_arg(args, "--fulltext-path", fulltext_path)
    _append_cli_arg(args, "--max-papers", config.literature.max_papers)
    _append_cli_arg(args, "--max-search-queries", config.literature.max_search_queries)
    for query in config.literature.extra_search_queries:
        _append_cli_arg(args, "--extra-search-query", query)
    _append_cli_arg(args, "--execution-mode", config.execution.mode)
    _append_cli_arg(args, "--execution-repeats", config.execution.repeats)
    for manifest_path in config.execution.benchmark_manifest_paths:
        _append_cli_arg(args, "--benchmark-manifest", manifest_path)
    if config.paper_grade.enabled:
        args.append("--paper-grade")
    release_args = _release_command_args(config).strip()
    if release_args:
        args.append(release_args)
    return (" " + " ".join(args)) if args else ""


def _append_cli_arg(args: list[str], name: str, value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in {"0", "0.0"}:
        args.extend([name, _shell_double(text)])


def _release_command_args(config: AgentConfig) -> str:
    fields = [
        ("--release-code-repository-url", config.release.code_repository_url),
        ("--release-code-archive-doi", config.release.code_archive_doi),
        ("--release-code-license", config.release.code_license),
        ("--release-code-version", config.release.code_version),
        ("--release-data-repository-url", config.release.data_repository_url),
        ("--release-data-archive-doi", config.release.data_archive_doi),
        ("--release-data-access-statement", config.release.data_access_statement),
        ("--release-environment-url", config.release.environment_url),
        ("--release-notes", config.release.release_notes),
    ]
    args = [f"{name} {_shell_double(str(value).strip())}" for name, value in fields if str(value or "").strip()]
    return (" " + " ".join(args)) if args else ""


def _gold_run_out_dir(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(topic or "").lower()).strip("-")
    if not slug:
        slug = "gold-run"
    return f"runs/{slug[:72]}-gold-run"


def _configured(value: str, env_name: str) -> bool:
    return bool(str(value or "").strip() or os.environ.get(env_name, "").strip())


def _configured_secret(value: str, env_name: str) -> bool:
    resolved = os.environ.get(env_name, "").strip() or str(value or "").strip()
    return bool(resolved and not _placeholder_secret(resolved))


def _configured_contact_email(value: str, env_name: str) -> bool:
    resolved = os.environ.get(env_name, "").strip() or str(value or "").strip()
    return bool(resolved and valid_contact_email(resolved))


def _credential_detail(value: str, env_name: str, *, valid: bool | None = None) -> str:
    if os.environ.get(env_name, "").strip():
        suffix = "" if valid is not False else "; invalid_or_placeholder"
        return f"{env_name}=set{suffix}"
    if str(value or "").strip():
        suffix = "" if valid is not False else "; invalid_or_placeholder"
        return f"config=set{suffix}"
    return f"{env_name}=missing"


def _resolved_setting(value: str, env_name: str, default: str) -> str:
    return str(value or "").strip() or os.environ.get(env_name, "").strip() or default


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _looks_like_doi(value: str) -> bool:
    return bool(_DOI_PATTERN.match(str(value or "").strip()))


def _placeholder_release_value(value: str) -> bool:
    text = str(value or "").strip().lower()
    return any(token in text for token in _PLACEHOLDER_RELEASE_TOKENS)


def _read_dict(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _path_name(value: Any) -> str:
    text = str(value or "").strip()
    return Path(text).name if text else ""


def _check(name: str, status: str, detail: str, action: str = "") -> dict[str, Any]:
    return {"id": name, "name": name, "status": status, "detail": detail, "action": action}


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _shell_double(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'
