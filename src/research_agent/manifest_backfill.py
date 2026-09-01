from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import write_json, write_text
from .provenance import ArtifactRecord, MANIFEST_JSON, MANIFEST_MD, RunEvent, RunManifest, render_manifest_markdown


EVENT_SPECS: list[tuple[str, list[str], list[str]]] = [
    ("question", [], ["00-question.md"]),
    ("human_brief", [], ["00-human-brief.json", "00-human-brief.md"]),
    ("prior_run_lessons", [], ["00-prior-run-lessons.json", "00-prior-run-lessons.md"]),
    ("prior_run_library", [], ["00-prior-run-library.json", "00-prior-run-library.md"]),
    ("open_source_lessons", [], ["00-open-source-lessons.json", "00-open-source-lessons.md"]),
    ("research_plan", [], ["00-research-plan.json", "00-research-plan.md"]),
    ("literature_review", ["00-research-plan.json"], ["01-literature.json", "01-literature.md"]),
    ("literature_context", ["01-literature.json"], ["01-context.json", "01-context.md", "01-review-gate.md"]),
    ("query_execution_audit", ["01-literature.json"], ["01-query-execution-audit.json", "01-query-execution-audit.md"]),
    ("literature_snowball", ["01-literature.json"], ["01-literature-snowball.json", "01-literature-snowball.md"]),
    ("literature_coverage", ["01-literature.json"], ["01-literature-coverage.json", "01-literature-coverage.md"]),
    ("literature_evidence_mix", ["01-literature.json"], ["01-literature-evidence-mix.json", "01-literature-evidence-mix.md"]),
    ("literature_evidence_contract", ["01-context.json", "01-citation-audit.json"], ["01-literature-evidence-contract.json", "01-literature-evidence-contract.md"]),
    ("literature_rescue_plan", ["01-literature-evidence-mix.json"], ["01-literature-rescue-plan.json", "01-literature-rescue-plan.md"]),
    ("literature_rescue_execution", ["01-literature-rescue-plan.json"], ["01-literature-rescue-execution.json", "01-literature-rescue-execution.md"]),
    ("seed_paper_intake", [], ["01-seed-paper-intake.json", "01-seed-paper-intake.md"]),
    ("fulltext_corpus", [], ["01-fulltext-corpus.json", "01-fulltext-corpus.md"]),
    ("literature_metadata_audit", ["01-literature.json"], ["01-literature-metadata-audit.json", "01-literature-metadata-audit.md"]),
    ("citation_audit", ["01-context.json"], ["01-citation-audit.json", "01-citation-audit.md"]),
    ("review_approval", ["01-review-gate.md"], ["approval.json"]),
    ("review_feedback", ["approval.json"], ["01-review-feedback.json", "01-review-feedback.md"]),
    ("review_constraints", ["approval.json"], ["01-review-constraints.json", "01-review-constraints.md"]),
    ("ideation", ["approval.json", "01-context.json"], ["02-ideas.json", "02-ideas.md"]),
    ("novelty_audit", ["02-ideas.json"], ["02-novelty-audit.json", "02-novelty-audit.md"]),
    ("idea_audit", ["02-ideas.json"], ["02-idea-audit.json", "02-idea-audit.md"]),
    ("exploration_map", ["02-ideas.json"], ["02-exploration-map.json", "02-exploration-map.md", "02-exploration-map.svg"]),
    ("experiment_manager", ["02-ideas.json"], ["02-experiment-manager.json", "02-experiment-manager.md"]),
    ("experiment_plan", ["02-ideas.json"], ["03-experiment-plan.json", "03-experiment-plan.md"]),
    ("review_constraint_compliance", ["03-experiment-plan.json"], ["03-review-constraint-compliance.json", "03-review-constraint-compliance.md"]),
    ("experiment_audit", ["03-experiment-plan.json"], ["03-experiment-audit.json", "03-experiment-audit.md"]),
    ("idea_experiment_contract", ["03-experiment-plan.json"], ["03-idea-experiment-contract.json", "03-idea-experiment-contract.md"]),
    ("execution_safety", ["03-experiment-plan.json"], ["03-execution-safety-audit.json", "03-execution-safety-audit.md"]),
    ("benchmark_plan", ["03-experiment-plan.json"], ["03-benchmark-plan.json", "03-benchmark-plan.md"]),
    ("benchmark_readiness", ["03-benchmark-plan.json"], ["03-benchmark-readiness.json", "03-benchmark-readiness.md"]),
    ("execution_approval", ["03-execution-safety-audit.json"], ["03-execution-approval.json", "03-execution-approval.md"]),
    ("experiments", ["03-experiment-plan.json"], ["04-results.json", "04-results.csv", "04-experiment-runbook.json", "04-experiment-runbook.md"]),
    ("statistics", ["04-results.json"], ["04-statistics.json", "04-statistics.md", "04-statistics.svg"]),
    ("analysis", ["04-results.json", "04-statistics.json"], ["05-analysis.json", "05-analysis.md"]),
    ("result_validation", ["04-statistics.json"], ["04-result-validation.json", "04-result-validation.md"]),
    ("failure_analysis", ["04-statistics.json"], ["04-failure-analysis.json", "04-failure-analysis.md"]),
    ("benchmark_result_schema", ["04-experiment-runbook.json"], ["04-benchmark-result-schema-audit.json", "04-benchmark-result-schema-audit.md"]),
    ("benchmark_evidence", ["04-experiment-runbook.json"], ["04-benchmark-evidence-audit.json", "04-benchmark-evidence-audit.md"]),
    ("environment_snapshot", ["04-experiment-runbook.json"], ["04-environment-snapshot.json", "04-environment-snapshot.md"]),
    ("experiment_decision", ["04-statistics.json"], ["04-experiment-decision.json", "04-experiment-decision.md"]),
    ("hypothesis_outcome", ["04-statistics.json"], ["04-hypothesis-outcome.json", "04-hypothesis-outcome.md"]),
    ("claim_boundary_preflight", ["04-statistics.json"], ["04-claim-boundary-preflight.json", "04-claim-boundary-preflight.md"]),
    ("paper", ["04-statistics.json", "01-context.json"], ["06-paper.md"]),
    ("paper_review", ["06-paper.md"], ["07-paper-review.json", "07-paper-review.md", "07-paper-review-calibration.json", "07-paper-review-calibration.md"]),
    ("paper_and_review", ["06-paper.md", "01-context.json"], ["06-paper.md", "07-paper-review.json", "07-paper-review.md", "07-paper-review-calibration.json", "07-paper-review-calibration.md"]),
    ("revision_plan", ["07-paper-review.json"], ["08-revision-plan.json", "08-revision-plan.md"]),
    ("paper_revision", ["08-revision-plan.json", "06-paper.md"], ["09-revised-paper.md", "09-revised-paper.tex", "09-revision-report.json", "09-revision-report.md"]),
    ("revision_response_audit", ["09-revised-paper.md"], ["09-revision-response-audit.json", "09-revision-response-audit.md"]),
    ("claim_traceability", ["09-revised-paper.md"], ["10-claim-traceability.json", "10-claim-traceability.md"]),
    ("agent_claim_audit", ["10-claim-traceability.json"], ["10-agent-claim-audit.json", "10-agent-claim-audit.md"]),
    ("citation_grounding", ["09-revised-paper.md"], ["10-citation-grounding.json", "10-citation-grounding.md"]),
    ("citation_coverage", ["09-revised-paper.md"], ["10-citation-coverage.json", "10-citation-coverage.md"]),
    ("results_presentation", ["09-revised-paper.md"], ["10-results-presentation.json", "10-results-presentation.md"]),
    ("claim_consistency", ["09-revised-paper.md"], ["10-claim-consistency.json", "10-claim-consistency.md"]),
    ("agent_deliberation", ["10-agent-claim-audit.json", "10-claim-consistency.json"], ["10-agent-deliberation.json", "10-agent-deliberation.md"]),
    ("final_readiness", ["09-revised-paper.md"], ["10-final-readiness.json", "10-final-readiness.md"]),
    ("code_data_availability", ["09-revised-paper.md"], ["10-code-data-availability.json", "10-code-data-availability.md"]),
    ("submission_check", ["09-revised-paper.md"], ["10-submission-check.json", "10-submission-check.md"]),
    ("submission_package", ["10-final-readiness.json"], ["11-submission-package.json", "11-submission-package.md", "11-submission-package.zip"]),
    ("iteration_plan", ["10-final-readiness.json"], ["12-next-iteration-plan.json", "12-next-iteration-plan.md"]),
    ("repair_queue", ["12-next-iteration-plan.json"], ["12-repair-queue.json", "12-repair-queue.md"]),
    ("repair_resume", ["12-repair-queue.json"], ["12-repair-resume-plan.json", "12-repair-resume-plan.md"]),
    ("repair_resolution_audit", ["12-repair-queue.json"], ["12-repair-resolution-audit.json", "12-repair-resolution-audit.md"]),
    ("llm_trace_audit", ["run-llm-ledger.json"], ["13-llm-trace-audit.json", "13-llm-trace-audit.md"]),
    ("llm_runtime_contract", ["run-llm-ledger.json", "run-config.json"], ["13-llm-runtime-contract.json", "13-llm-runtime-contract.md"]),
    ("run_economics_audit", ["run-llm-ledger.json"], ["13-run-economics-audit.json", "13-run-economics-audit.md"]),
    ("agent_observability_audit", ["run-manifest.json"], ["13-agent-observability-audit.json", "13-agent-observability-audit.md"]),
    ("open_source_compliance", ["00-open-source-lessons.json"], ["13-open-source-compliance.json", "13-open-source-compliance.md"]),
    ("agent_stage_contract", ["13-agent-observability-audit.json"], ["13-agent-stage-contract.json", "13-agent-stage-contract.md"]),
    ("agent_trajectory", ["run-manifest.json"], ["13-agent-trajectory.json", "13-agent-trajectory.md"]),
    ("research_scorecard", ["13-agent-stage-contract.json"], ["13-research-scorecard.json", "13-research-scorecard.md"]),
    ("run_integrity_audit", ["run-manifest.json"], ["14-run-integrity-audit.json", "14-run-integrity-audit.md"]),
    ("final_handoff", ["14-run-integrity-audit.json"], ["14-final-handoff.json", "14-final-handoff.md"]),
]


def backfill_run_manifests(runs_dir: Path, *, dry_run: bool = False, force: bool = False, limit: int = 0) -> dict[str, Any]:
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
        "errors": [],
        "items": [],
    }
    candidates = 0
    for run_dir in run_dirs:
        state_path = run_dir / "state.json"
        if not state_path.exists():
            report["skipped_no_state"] += 1
            continue
        if limit > 0 and candidates >= limit:
            break
        candidates += 1
        report["scanned_runs"] += 1
        manifest_path = run_dir / MANIFEST_JSON
        if manifest_path.exists() and not force:
            report["skipped_existing"] += 1
            report["items"].append(_item(run_dir, "skipped_existing"))
            continue
        manifest = build_backfilled_manifest(run_dir)
        action = "overwrite" if manifest_path.exists() else "write"
        if dry_run:
            report["would_write"] += 1
            report["items"].append(_item(run_dir, f"would_{action}", events=len(manifest.events), artifacts=len(manifest.artifacts), last_event=_last_event(manifest)))
            continue
        try:
            manifest = write_backfilled_manifest(run_dir, manifest)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            report["errors"].append({"run_id": run_dir.name, "error": str(exc)})
            report["items"].append(_item(run_dir, "error", error=str(exc)))
            continue
        report["written"] += 1
        report["items"].append(_item(run_dir, action, events=len(manifest.events), artifacts=len(manifest.artifacts), last_event=_last_event(manifest)))
    return report


def build_backfilled_manifest(run_dir: Path) -> RunManifest:
    state = _read_json(run_dir / "state.json")
    topic = str(state.get("topic") or run_dir.name)
    status = _manifest_status(str(state.get("stage") or ""))
    started_at = _oldest_mtime(run_dir) or _utc_now()
    events = _backfilled_events(run_dir, state)
    return RunManifest(topic=topic, status=status, started_at=started_at, updated_at=_utc_now(), events=events, artifacts=_artifact_inventory(run_dir))


def write_backfilled_manifest(run_dir: Path, manifest: RunManifest) -> RunManifest:
    write_json(run_dir / MANIFEST_JSON, manifest)
    write_text(run_dir / MANIFEST_MD, render_manifest_markdown(manifest))
    manifest = RunManifest(
        topic=manifest.topic,
        status=manifest.status,
        started_at=manifest.started_at,
        updated_at=_utc_now(),
        events=manifest.events,
        artifacts=_artifact_inventory(run_dir),
    )
    write_json(run_dir / MANIFEST_JSON, manifest)
    write_text(run_dir / MANIFEST_MD, render_manifest_markdown(manifest))
    return manifest


def render_manifest_backfill_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Run Manifest Backfill",
        "",
        f"- Runs 目录：{report.get('runs_dir') or '-'}",
        f"- 模式：{'dry-run' if report.get('dry_run') else 'write'} / force={bool(report.get('force'))}",
        f"- 扫描 run：{report.get('scanned_runs', 0)}",
        f"- 写入：{report.get('written', 0)}",
        f"- 将写入：{report.get('would_write', 0)}",
        f"- 已存在跳过：{report.get('skipped_existing', 0)}",
        f"- 非 run 目录跳过：{report.get('skipped_no_state', 0)}",
        f"- 错误：{len(report.get('errors', [])) if isinstance(report.get('errors'), list) else 0}",
        "",
    ]
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    if errors:
        lines.extend(["## Errors", ""])
        for item in errors[:20]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('run_id') or '-'}: {item.get('error') or '-'}")
        lines.append("")
    items = report.get("items") if isinstance(report.get("items"), list) else []
    if items:
        lines.extend(["## Runs", "", "| Run | Action | Events | Artifacts | Last Event |", "| --- | --- | ---: | ---: | --- |"])
        for item in items[:100]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(str(item.get("run_id") or "")),
                        _cell(str(item.get("action") or "")),
                        str(item.get("events") or 0),
                        str(item.get("artifacts") or 0),
                        _cell(str(item.get("last_event") or "-")),
                    ]
                )
                + " |"
            )
    return "\n".join(lines)


def _backfilled_events(run_dir: Path, state: dict[str, Any]) -> list[RunEvent]:
    events: list[RunEvent] = []
    for stage, inputs, outputs in EVENT_SPECS:
        present_outputs = [path for path in outputs if (run_dir / path).exists()]
        if not present_outputs:
            continue
        timestamp = _latest_mtime(run_dir, present_outputs) or _utc_now()
        events.append(
            RunEvent(
                stage=stage,
                status="backfilled",
                started_at=timestamp,
                completed_at=timestamp,
                inputs=[path for path in inputs if (run_dir / path).exists()],
                outputs=present_outputs,
                notes=["Backfilled from artifacts already present on disk; event timing is inferred from file mtimes."],
                metrics={"backfilled": True, "present_outputs": len(present_outputs)},
            )
        )
    state_stage = str(state.get("stage") or "").strip()
    if state_stage and (not events or events[-1].stage != state_stage):
        timestamp = _file_mtime(run_dir / "state.json") or _utc_now()
        events.append(
            RunEvent(
                stage=state_stage,
                status="backfilled",
                started_at=timestamp,
                completed_at=timestamp,
                inputs=[],
                outputs=["state.json"],
                notes=["Backfilled terminal/current state from state.json."],
                metrics={"backfilled": True},
            )
        )
    return events


def _artifact_inventory(run_dir: Path) -> list[ArtifactRecord]:
    records: list[ArtifactRecord] = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        records.append(ArtifactRecord(path=str(path.relative_to(run_dir)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return records


def _manifest_status(stage: str) -> str:
    if stage == "completed":
        return "completed"
    if stage == "failed":
        return "failed"
    if stage == "cancelled":
        return "cancelled"
    return "backfilled"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _latest_mtime(run_dir: Path, paths: list[str]) -> str:
    values = [_file_mtime(run_dir / path) for path in paths]
    values = [value for value in values if value]
    return max(values) if values else ""


def _oldest_mtime(run_dir: Path) -> str:
    values = [_file_mtime(path) for path in run_dir.rglob("*") if path.is_file()]
    values = [value for value in values if value]
    return min(values) if values else ""


def _file_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return ""


def _last_event(manifest: RunManifest) -> str:
    return manifest.events[-1].stage if manifest.events else ""


def _item(run_dir: Path, action: str, **extra: Any) -> dict[str, Any]:
    return {"run_id": run_dir.name, "action": action, **extra}


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
