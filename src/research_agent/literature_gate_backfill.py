from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .citation_audit import audit_citations
from .literature_gate_decision import (
    LITERATURE_GATE_DECISION_JSON,
    LITERATURE_GATE_DECISION_MD,
    LITERATURE_GATE_DECISION_SCHEMA_VERSION,
    build_literature_context_gate_report,
    build_literature_gate_decision,
    render_literature_gate_decision_markdown,
)
from .literature_evidence_contract import build_literature_evidence_contract
from .literature_evidence_contract import (
    LITERATURE_EVIDENCE_CONTRACT_JSON,
    LITERATURE_EVIDENCE_CONTRACT_MD,
    render_literature_evidence_contract_markdown,
)
from .models import CitationEntry, ClaimSupport, EvidenceChunk, LiteratureContext, ReviewGate
from .artifacts import write_json, write_text, cell as _cell, safe_int as _safe_int, utc_now as _utc_now, read_json_dict as _read_json


def backfill_literature_gate_decisions(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
    run_dirs = [path for path in sorted(runs_dir.iterdir()) if path.is_dir()] if runs_dir.exists() else []
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "runs_dir": str(runs_dir),
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "scanned_runs": 0,
        "written": 0,
        "would_write": 0,
        "skipped_existing": 0,
        "skipped_no_state": 0,
        "skipped_no_literature": 0,
        "refreshed_outdated": 0,
        "errors": [],
        "items": [],
    }
    candidates = 0
    for run_dir in run_dirs:
        if not (run_dir / "state.json").exists():
            report["skipped_no_state"] += 1
            continue
        if limit > 0 and candidates >= limit:
            break
        candidates += 1
        report["scanned_runs"] += 1
        exists = (run_dir / LITERATURE_GATE_DECISION_JSON).exists() and (run_dir / LITERATURE_GATE_DECISION_MD).exists()
        if exists and not force:
            existing = _read_json(run_dir / LITERATURE_GATE_DECISION_JSON)
            if _is_current_gate(existing):
                report["skipped_existing"] += 1
                report["items"].append(_item(run_dir, "skipped_existing", existing))
                continue
        try:
            gate = build_literature_gate_decision_for_run(run_dir)
        except ValueError as exc:
            report["skipped_no_literature"] += 1
            report["items"].append(_item(run_dir, "skipped_no_literature", {}, error=str(exc)))
            continue
        except Exception as exc:  # pragma: no cover - defensive CLI/Web boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", {}, error=str(exc)))
            continue
        action = "overwrite" if exists else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", gate))
            continue
        if exists and not force:
            report["refreshed_outdated"] += 1
        evidence_contract = gate.pop("_evidence_contract", {})
        if isinstance(evidence_contract, dict) and evidence_contract:
            write_json(run_dir / LITERATURE_EVIDENCE_CONTRACT_JSON, evidence_contract)
            write_text(run_dir / LITERATURE_EVIDENCE_CONTRACT_MD, render_literature_evidence_contract_markdown(evidence_contract))
        write_json(run_dir / LITERATURE_GATE_DECISION_JSON, gate)
        write_text(run_dir / LITERATURE_GATE_DECISION_MD, render_literature_gate_decision_markdown(gate))
        report["written"] += 1
        report["items"].append(_item(run_dir, action, gate))
    return report


def build_literature_gate_decision_for_run(run_dir: Path) -> dict[str, Any]:
    quality = _read_json(run_dir / "01-literature-quality.json")
    context = _read_context(run_dir / "01-context.json")
    citation = _read_json(run_dir / "01-citation-audit.json")
    source_health = _read_json(run_dir / "01-literature-source-health.json")
    query_execution = _read_json(run_dir / "01-query-execution-audit.json")
    rerank = _read_json(run_dir / "01-literature-rerank.json")
    if not citation and context is not None:
        citation = _report_dict(audit_citations(context))
    raw_literature = _read_json(run_dir / "01-literature.json")
    if not quality and raw_literature:
        papers = raw_literature.get("papers") if isinstance(raw_literature.get("papers"), list) else []
        quality = {
            "total_papers": len(papers),
            "selected_papers": len(papers),
            "confidence_status": "review_required" if papers else "block",
            "confidence_score": 0.0,
        }
    if not any([quality, raw_literature, context, citation]):
        raise ValueError("missing literature/context artifacts")
    topic = _topic(run_dir, raw_literature, context)
    evidence_contract = {}
    if context is not None:
        evidence_contract = build_literature_evidence_contract(
            context=context,
            quality_report=quality,
            source_health_report=source_health,
            query_execution_report=query_execution,
            rerank_report=rerank,
            citation_audit_report=citation,
        )
    gate = build_literature_gate_decision(
        topic=topic,
        quality_report=quality,
        source_health_report=source_health,
        query_execution_report=query_execution,
        rerank_report=rerank,
        coverage_report=_read_json(run_dir / "01-literature-coverage.json"),
        evidence_mix_report=_read_json(run_dir / "01-literature-evidence-mix.json"),
        rescue_report=_read_json(run_dir / "01-literature-rescue-plan.json"),
        rescue_execution_report=_read_json(run_dir / "01-literature-rescue-execution.json"),
        seed_intake_report=_read_json(run_dir / "01-seed-paper-intake.json"),
        evidence_contract_report=evidence_contract,
        citation_audit_report=citation,
        context_report=build_literature_context_gate_report(context),
        citation_grounding_report=_read_json(run_dir / "10-citation-grounding.json"),
    )
    if evidence_contract:
        gate["_evidence_contract"] = evidence_contract
    return gate


def render_literature_gate_backfill_markdown(report: dict[str, Any]) -> str:
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    lines = [
        "# Literature Gate Decision Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入门禁：{report.get('written', 0)}",
        f"- 将写入门禁：{report.get('would_write', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 旧 schema 刷新：{report.get('refreshed_outdated', 0)}",
        f"- 缺少文献跳过：{report.get('skipped_no_literature', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(errors)}",
        "",
        "说明：该回填只根据历史文献/引用审计生成 01-literature-gate-decision.*；不会批准 review gate、不会恢复 pipeline、不会进入 idea 或实验。",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""])
        for item in errors[:20]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('run_id') or '-'}: {item.get('error') or '-'}")
        lines.append("")
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if items:
        lines.extend(
            [
                "## Runs",
                "",
                "| Run | Action | Gate | Decision | Raw | Selected | Blocking | Review | Required |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("run_id") or "")),
                        _cell(str(item.get("action") or "")),
                        _cell(str(item.get("status") or "-")),
                        _cell(str(item.get("decision") or "-")),
                        str(item.get("raw_papers") or 0),
                        str(item.get("selected_papers") or 0),
                        str(item.get("blocking_reasons") or 0),
                        str(item.get("review_reasons") or 0),
                        str(item.get("required_actions") or 0),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _item(run_dir: Path, action: str, gate: dict[str, Any], **extra: Any) -> dict[str, Any]:
    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    return {
        "run_id": run_dir.name,
        "action": action,
        "status": gate.get("status", ""),
        "decision": gate.get("decision", ""),
        "raw_papers": _safe_int(summary.get("raw_papers")),
        "selected_papers": _safe_int(summary.get("selected_papers")),
        "blocking_reasons": len(gate.get("blocking_reasons", [])) if isinstance(gate.get("blocking_reasons"), list) else 0,
        "review_reasons": len(gate.get("review_reasons", [])) if isinstance(gate.get("review_reasons"), list) else 0,
        "required_actions": len(gate.get("required_actions", [])) if isinstance(gate.get("required_actions"), list) else 0,
        **extra,
    }


def _read_context(path: Path) -> LiteratureContext | None:
    data = _read_json(path)
    if not data:
        return None
    citations = [_citation(item) for item in data.get("citations", []) if isinstance(item, dict)]
    chunks = [_chunk(item) for item in data.get("chunks", []) if isinstance(item, dict)]
    claim_support = [_claim_support(item) for item in data.get("claim_support", []) if isinstance(item, dict)]
    gate_data = data.get("review_gate") if isinstance(data.get("review_gate"), dict) else {}
    return LiteratureContext(
        topic=str(data.get("topic") or ""),
        citations=citations,
        chunks=chunks,
        claim_support=claim_support,
        review_gate=ReviewGate(
            status=str(gate_data.get("status") or ""),
            warnings=[str(item) for item in gate_data.get("warnings", [])] if isinstance(gate_data.get("warnings"), list) else [],
            required_actions=[str(item) for item in gate_data.get("required_actions", [])] if isinstance(gate_data.get("required_actions"), list) else [],
        ),
    )


def _is_current_gate(gate: dict[str, Any]) -> bool:
    if _safe_int(gate.get("schema_version")) < LITERATURE_GATE_DECISION_SCHEMA_VERSION:
        return False
    summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    return (
        "context_chunks" in summary
        and "citation_grounding_status" in summary
        and "evidence_contract_status" in summary
        and "evidence_contract_substantive_chunk_coverage" in summary
    )


def _citation(data: dict[str, Any]) -> CitationEntry:
    return CitationEntry(
        key=str(data.get("key") or ""),
        title=str(data.get("title") or ""),
        authors=[str(item) for item in data.get("authors", [])] if isinstance(data.get("authors"), list) else [],
        year=_safe_int(data.get("year")),
        venue=str(data.get("venue") or ""),
        url=str(data.get("url") or ""),
        doi=str(data.get("doi") or ""),
        source=str(data.get("source") or ""),
    )


def _chunk(data: dict[str, Any]) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=str(data.get("chunk_id") or ""),
        citation_key=str(data.get("citation_key") or ""),
        title=str(data.get("title") or ""),
        text=str(data.get("text") or ""),
        source=str(data.get("source") or ""),
        url=str(data.get("url") or ""),
        relevance=float(data.get("relevance") or 0.0),
    )


def _claim_support(data: dict[str, Any]) -> ClaimSupport:
    return ClaimSupport(
        claim=str(data.get("claim") or ""),
        claim_type=str(data.get("claim_type") or ""),
        support_level=str(data.get("support_level") or ""),
        citation_keys=[str(item) for item in data.get("citation_keys", [])] if isinstance(data.get("citation_keys"), list) else [],
        evidence_notes=[str(item) for item in data.get("evidence_notes", [])] if isinstance(data.get("evidence_notes"), list) else [],
    )


def _topic(run_dir: Path, literature: dict[str, Any], context: LiteratureContext | None) -> str:
    state = _read_json(run_dir / "state.json")
    return str(state.get("topic") or literature.get("topic") or (context.topic if context else "") or run_dir.name)


def _report_dict(report: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in dir(report):
        if key.startswith("_"):
            continue
        value = getattr(report, key, None)
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
            result[key] = value
    return result


