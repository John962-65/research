from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
import re
import urllib.error
import urllib.request

from .artifacts import write_json, write_text
from .benchmark_adapter import audit_benchmark_adapter_config
from .config import AgentConfig


PAPER_GRADE_BENCHMARK_PROBE_JSON = "00-paper-grade-benchmark-probe.json"
PAPER_GRADE_BENCHMARK_PROBE_MD = "00-paper-grade-benchmark-probe.md"
_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


def write_paper_grade_benchmark_probe_artifacts(
    config: AgentConfig,
    out_dir: Path,
    *,
    timeout_seconds: float = 8.0,
    fetcher: Callable[[str, float], dict[str, Any]] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    report = build_paper_grade_benchmark_probe(config, timeout_seconds=timeout_seconds, fetcher=fetcher, base_dir=base_dir)
    write_json(out_dir / PAPER_GRADE_BENCHMARK_PROBE_JSON, report)
    write_text(out_dir / PAPER_GRADE_BENCHMARK_PROBE_MD, render_paper_grade_benchmark_probe_markdown(report))
    return report


def build_paper_grade_benchmark_probe(
    config: AgentConfig,
    *,
    timeout_seconds: float = 8.0,
    fetcher: Callable[[str, float], dict[str, Any]] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    adapter_report = audit_benchmark_adapter_config(config.execution, base_dir=base_dir, paper_grade=config.paper_grade)
    min_execution_repeats = max(1, int(config.paper_grade.min_execution_repeats or 0))
    ready_records = [record for record in adapter_report.adapters if record.status == "ready"]
    paper_roles = [record for record in ready_records if record.role in {"candidate", "baseline", "ablation"}]
    data_contract_checks = _data_contract_checks(ready_records)
    metric_contract_checks = _metric_contract_checks(ready_records)
    role_command_checks = _role_command_checks(paper_roles)
    url_checks = _url_checks(ready_records, fetcher or _fetch_url, timeout_seconds)
    citation_checks = _citation_checks(ready_records, fetcher or _fetch_url, timeout_seconds)
    checks = [
        _check(
            "benchmark_adapter_audit",
            "pass" if adapter_report.status == "ready" else "fail",
            f"adapter_status={adapter_report.status}; ready={len(ready_records)}",
            "Fix benchmark_manifest_paths, commands, source_files, metrics_path, expected_artifacts, or allowed_commands.",
        ),
        _check(
            "paper_grade_manifest_set",
            "pass" if adapter_report.paper_grade_status == "ready" else "fail",
            f"paper_grade_status={adapter_report.paper_grade_status}; issues={len(adapter_report.paper_grade_issues)}",
            f"Use candidate/baseline/ablation manifests with shared metrics, repeats/min_repeats>={min_execution_repeats}, and external provenance.",
        ),
        _check(
            "data_contract",
            "pass" if data_contract_checks and all(item["status"] == "pass" for item in data_contract_checks) else "fail",
            f"checked={len(data_contract_checks)}; failed={sum(1 for item in data_contract_checks if item['status'] != 'pass')}",
            "Fill dataset_version, split_name, and 64-hex split_sha256 for every paper-grade manifest role.",
        ),
        _check(
            "metric_contract",
            "pass" if metric_contract_checks and all(item["status"] == "pass" for item in metric_contract_checks) else "fail",
            f"checked={len(metric_contract_checks)}; failed={sum(1 for item in metric_contract_checks if item['status'] != 'pass')}",
            "Fill metric_schema, grader_version, and 64-hex grader_sha256 for every paper-grade manifest role.",
        ),
        _check(
            "role_command_contract",
            "pass" if role_command_checks and all(item["status"] == "pass" for item in role_command_checks) else "fail",
            f"checked={len(role_command_checks)}; failed={sum(1 for item in role_command_checks if item['status'] != 'pass')}",
            "Make candidate/baseline/ablation commands differ by method, variant, or config, not only output path.",
        ),
        _check(
            "external_url_reachability",
            "pass" if url_checks and all(item["status"] == "pass" for item in url_checks) else "fail",
            f"checked={len(url_checks)}; failed={sum(1 for item in url_checks if item['status'] != 'pass')}",
            "Replace broken/private/procedural URLs with public official benchmark/data URLs.",
        ),
        _check(
            "citation_resolution",
            "pass" if citation_checks and all(item["status"] == "pass" for item in citation_checks) else "fail",
            f"checked={len(citation_checks)}; failed={sum(1 for item in citation_checks if item['status'] != 'pass')}",
            "Add DOI or public URL citations for benchmark/data/baseline provenance.",
        ),
    ]
    status = "pass" if all(item["status"] == "pass" for item in checks) else "review_required"
    return {
        "schema_version": 1,
        "status": status,
        "manifest_paths": list(adapter_report.manifest_paths),
        "checks": checks,
        "adapter_status": adapter_report.status,
        "adapter_paper_grade_status": adapter_report.paper_grade_status,
        "adapter_paper_grade_issues": list(adapter_report.paper_grade_issues),
        "adapters": [asdict(record) for record in adapter_report.adapters],
        "data_contract_checks": data_contract_checks,
        "metric_contract_checks": metric_contract_checks,
        "role_command_checks": role_command_checks,
        "url_checks": url_checks,
        "citation_checks": citation_checks,
    }


def render_paper_grade_benchmark_probe_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper-grade Benchmark Probe",
        "",
        f"- 状态：{report.get('status') or '-'}",
        f"- Manifest 数：{len(report.get('manifest_paths', []) if isinstance(report.get('manifest_paths'), list) else [])}",
        f"- Adapter：{report.get('adapter_status') or '-'}",
        f"- Adapter paper-grade：{report.get('adapter_paper_grade_status') or '-'}",
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
    lines.extend(["", "## Data Contract Checks", "| Adapter | Status | Detail |", "| --- | --- | --- |"])
    data_checks = report.get("data_contract_checks") if isinstance(report.get("data_contract_checks"), list) else []
    if data_checks:
        for item in data_checks:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("adapter") or "")),
                            _cell(str(item.get("status") or "")),
                            _cell(str(item.get("detail") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | fail | no candidate/baseline/ablation data contract checks |")
    lines.extend(["", "## Metric Contract Checks", "| Adapter | Status | Detail |", "| --- | --- | --- |"])
    metric_checks = report.get("metric_contract_checks") if isinstance(report.get("metric_contract_checks"), list) else []
    if metric_checks:
        for item in metric_checks:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("adapter") or "")),
                            _cell(str(item.get("status") or "")),
                            _cell(str(item.get("detail") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | fail | no candidate/baseline/ablation metric contract checks |")
    lines.extend(["", "## Role Command Checks", "| Adapter | Status | Detail |", "| --- | --- | --- |"])
    role_checks = report.get("role_command_checks") if isinstance(report.get("role_command_checks"), list) else []
    if role_checks:
        for item in role_checks:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("adapter") or "")),
                            _cell(str(item.get("status") or "")),
                            _cell(str(item.get("detail") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | fail | no candidate/baseline/ablation role command checks |")
    lines.extend(["", "## URL Checks", "| Adapter | Field | Status | URL | Detail |", "| --- | --- | --- | --- | --- |"])
    url_checks = report.get("url_checks") if isinstance(report.get("url_checks"), list) else []
    if url_checks:
        for item in url_checks:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("adapter") or "")),
                            _cell(str(item.get("field") or "")),
                            _cell(str(item.get("status") or "")),
                            _cell(str(item.get("url") or "")),
                            _cell(str(item.get("detail") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | - | fail | - | no candidate/baseline/ablation URL checks |")
    lines.extend(["", "## Citation Checks", "| Adapter | Status | Target | Detail |", "| --- | --- | --- | --- |"])
    citation_checks = report.get("citation_checks") if isinstance(report.get("citation_checks"), list) else []
    if citation_checks:
        for item in citation_checks:
            if isinstance(item, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _cell(str(item.get("adapter") or "")),
                            _cell(str(item.get("status") or "")),
                            _cell(str(item.get("target") or "")),
                            _cell(str(item.get("detail") or "")),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | fail | - | no candidate/baseline/ablation citation checks |")
    issues = report.get("adapter_paper_grade_issues") if isinstance(report.get("adapter_paper_grade_issues"), list) else []
    if issues:
        lines.extend(["", "## Adapter Paper-grade Issues"])
        lines.extend(f"- {item}" for item in issues[:20])
    return "\n".join(lines)


def _data_contract_checks(records: list[Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for record in records:
        missing: list[str] = []
        if not str(getattr(record, "dataset_version", "") or "").strip():
            missing.append("dataset_version")
        if not str(getattr(record, "split_name", "") or "").strip():
            missing.append("split_name")
        split_sha256 = str(getattr(record, "split_sha256", "") or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F]{64}", split_sha256):
            missing.append("split_sha256")
        checks.append(
            {
                "adapter": str(getattr(record, "name", "") or ""),
                "status": "fail" if missing else "pass",
                "detail": "missing_or_invalid=" + ",".join(missing) if missing else "dataset_version/split_name/split_sha256 present",
            }
        )
    return checks


def _url_checks(records: list[Any], fetcher: Callable[[str, float], dict[str, Any]], timeout_seconds: float) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for record in records:
        for field in ["dataset_url", "benchmark_url"]:
            url = str(getattr(record, field, "") or "").strip()
            if not url:
                checks.append(_probe_row(record.name, field, "fail", url, "missing URL"))
                continue
            if not _is_http_url(url):
                checks.append(_probe_row(record.name, field, "fail", url, "not a public http(s) URL"))
                continue
            result = fetcher(url, timeout_seconds)
            checks.append(_probe_row(record.name, field, _fetch_status(result), url, _fetch_detail(result)))
    return checks


def _metric_contract_checks(records: list[Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for record in records:
        issues = [str(item) for item in getattr(record, "metric_contract_issues", []) if str(item).strip()]
        checks.append(
            {
                "adapter": str(getattr(record, "name", "") or ""),
                "status": "fail" if issues else "pass",
                "detail": "; ".join(issues[:3]) if issues else "metric_schema/grader_version/grader_sha256 present",
            }
        )
    return checks


def _role_command_checks(records: list[Any]) -> list[dict[str, str]]:
    by_signature: dict[str, list[str]] = {}
    for record in records:
        signature = str(getattr(record, "role_command_signature", "") or "")
        role = str(getattr(record, "role", "") or "")
        if signature:
            by_signature.setdefault(signature, []).append(role)
    duplicate_roles = {role for roles in by_signature.values() if len(set(roles)) > 1 for role in roles}
    checks: list[dict[str, str]] = []
    for record in records:
        signature = str(getattr(record, "role_command_signature", "") or "")
        role = str(getattr(record, "role", "") or "")
        if not signature:
            status = "fail"
            detail = "missing role_command_signature"
        elif role in duplicate_roles:
            status = "fail"
            detail = "command duplicates another paper-grade role after ignoring output paths"
        else:
            status = "pass"
            detail = "role command differs by method/variant/config"
        checks.append({"adapter": str(getattr(record, "name", "") or ""), "status": status, "detail": detail})
    return checks


def _citation_checks(records: list[Any], fetcher: Callable[[str, float], dict[str, Any]], timeout_seconds: float) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for record in records:
        citation = str(getattr(record, "citation", "") or "").strip()
        target = _citation_target(citation)
        if not target:
            checks.append(
                {
                    "adapter": record.name,
                    "status": "fail",
                    "citation": citation,
                    "target": "",
                    "detail": "citation does not contain a DOI or public URL for live resolution",
                }
            )
            continue
        result = fetcher(target, timeout_seconds)
        checks.append(
            {
                "adapter": record.name,
                "status": _fetch_status(result),
                "citation": citation,
                "target": target,
                "detail": _fetch_detail(result),
            }
        )
    return checks


def _citation_target(value: str) -> str:
    text = str(value or "").strip()
    doi_match = _DOI_PATTERN.search(text)
    if doi_match:
        return "https://doi.org/" + doi_match.group(0).rstrip(".,;)")
    for token in text.split():
        cleaned = token.strip(".,;()[]{}")
        if _is_http_url(cleaned):
            return cleaned
    return ""


def _fetch_url(url: str, timeout_seconds: float) -> dict[str, Any]:
    headers = {"User-Agent": "research-agent-paper-grade-probe/1.0"}
    for method in ["HEAD", "GET"]:
        request = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                status_code = int(getattr(response, "status", 0) or response.getcode() or 0)
                return {"ok": 200 <= status_code < 400, "status_code": status_code, "method": method}
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405, 501}:
                continue
            return {"ok": 200 <= int(exc.code) < 400, "status_code": int(exc.code), "method": method, "error": str(exc)}
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if method == "HEAD":
                continue
            return {"ok": False, "status_code": 0, "method": method, "error": str(exc)}
    return {"ok": False, "status_code": 0, "method": "GET", "error": "unreachable"}


def _probe_row(adapter: str, field: str, status: str, url: str, detail: str) -> dict[str, str]:
    return {"adapter": adapter, "field": field, "status": status, "url": url, "detail": detail}


def _fetch_status(result: dict[str, Any]) -> str:
    return "pass" if result.get("ok") is True else "fail"


def _fetch_detail(result: dict[str, Any]) -> str:
    status_code = result.get("status_code")
    method = result.get("method") or "-"
    error = str(result.get("error") or "").strip()
    detail = f"{method} status={status_code}"
    return f"{detail}; {error}" if error else detail


def _is_http_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _check(name: str, status: str, detail: str, action: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "action": action}


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
