from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import uuid

from .artifacts import read_json, write_json, write_text, cell as _cell, utc_now as _utc_now


MANIFEST_JSON = "run-manifest.json"
MANIFEST_MD = "run-manifest.md"
WORKFLOW_STATUS_JSON = "workflow-status.json"
LEGACY_BRANCH_ID = "legacy"
ACTIVE_BRANCH_ID = "main"


@dataclass(frozen=True)
class RunEvent:
    stage: str
    status: str
    started_at: str
    completed_at: str
    inputs: list[str]
    outputs: list[str]
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    # Revision-aware fields (REV-01). Records written before schema v2 load
    # with revision=0 / branch_id="legacy": they cannot back a gate decision
    # once the run has rolled back to a newer revision.
    revision: int = 0
    branch_id: str = LEGACY_BRANCH_ID
    node_id: str = ""
    attempt_id: str = ""
    event_id: str = ""


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    bytes: int
    sha256: str
    revision: int = 0
    branch_id: str = LEGACY_BRANCH_ID


@dataclass(frozen=True)
class RunManifest:
    topic: str
    status: str
    started_at: str
    updated_at: str
    events: list[RunEvent]
    artifacts: list[ArtifactRecord]
    schema_version: int = 1


class RunManifestRecorder:
    def __init__(self, out_dir: Path, topic: str) -> None:
        self.out_dir = out_dir
        self.topic = topic
        existing = _load_existing(out_dir)
        self.started_at = existing.started_at if existing else _utc_now()
        self.events = list(existing.events) if existing else []

    def record(
        self,
        stage: str,
        status: str = "completed",
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        notes: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now()
        revision = active_revision(self.out_dir)
        node_id = _node_id_for_stage(stage)
        self.events.append(
            RunEvent(
                stage=stage,
                status=status,
                started_at=now,
                completed_at=now,
                inputs=inputs or [],
                outputs=outputs or [],
                notes=notes or [],
                metrics=metrics or {},
                revision=revision,
                branch_id=ACTIVE_BRANCH_ID,
                node_id=node_id,
                attempt_id=f"{node_id}-r{revision}" if node_id else f"stage-r{revision}",
                event_id=uuid.uuid4().hex,
            )
        )
        self.write(status=status)

    def write(self, status: str = "running") -> RunManifest:
        manifest = RunManifest(
            topic=self.topic,
            status=status,
            started_at=self.started_at,
            updated_at=_utc_now(),
            events=self.events,
            artifacts=_artifact_inventory(self.out_dir),
            schema_version=2,
        )
        write_json(self.out_dir / MANIFEST_JSON, manifest)
        write_text(self.out_dir / MANIFEST_MD, render_manifest_markdown(manifest))
        return manifest


def active_revision(out_dir: Path) -> int:
    """Current workflow revision of the run (0 until the first rollback)."""
    try:
        data = json.loads((Path(out_dir) / WORKFLOW_STATUS_JSON).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("revision") or 0)
    except (TypeError, ValueError):
        return 0


def event_in_active_branch(event: Any, active_rev: int) -> bool:
    """Whether a manifest event may back current-revision evidence (REV-01).

    v1 events (no revision stamp) are legacy: they only count while the run
    has never rolled back, and never once a newer revision is active.
    """
    if isinstance(event, dict):
        revision = event.get("revision", 0)
        branch = str(event.get("branch_id") or LEGACY_BRANCH_ID)
    else:
        revision = event.revision
        branch = event.branch_id
    try:
        revision = int(revision)
    except (TypeError, ValueError):
        revision = 0
    if branch == ACTIVE_BRANCH_ID:
        return revision == active_rev
    return active_rev == 0


def filter_active_events(events: list[Any], active_rev: int) -> list[Any]:
    return [event for event in events if event_in_active_branch(event, active_rev)]


def render_manifest_markdown(manifest: RunManifest) -> str:
    lines = [
        f"# Run Manifest：{manifest.topic}",
        "",
        f"- 状态：{manifest.status}",
        f"- 开始：{manifest.started_at}",
        f"- 更新：{manifest.updated_at}",
        f"- 阶段事件：{len(manifest.events)}",
        f"- 产物数量：{len(manifest.artifacts)}",
        f"- Schema 版本：{manifest.schema_version}",
        "",
        "## Timeline",
        "| 阶段 | 状态 | revision | 输入 | 输出 | 指标/备注 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for event in manifest.events:
        inputs = _cell(", ".join(event.inputs) or "-")
        outputs = _cell(", ".join(event.outputs) or "-")
        detail = _event_detail(event)
        lines.append(f"| {event.stage} | {event.status} | {event.revision} | {inputs} | {outputs} | {_cell(detail)} |")
    lines.extend(["", "## Artifact Inventory", "| 文件 | 大小 | SHA256 |", "| --- | ---: | --- |"])
    for artifact in manifest.artifacts:
        lines.append(f"| {_cell(artifact.path)} | {artifact.bytes} | `{artifact.sha256}` |")
    return "\n".join(lines)


def _load_existing(out_dir: Path) -> RunManifest | None:
    path = out_dir / MANIFEST_JSON
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    events = [
        RunEvent(
            stage=str(item.get("stage") or ""),
            status=str(item.get("status") or ""),
            started_at=str(item.get("started_at") or ""),
            completed_at=str(item.get("completed_at") or ""),
            inputs=[str(value) for value in item.get("inputs", [])],
            outputs=[str(value) for value in item.get("outputs", [])],
            notes=[str(value) for value in item.get("notes", [])],
            metrics=dict(item.get("metrics") or {}),
            revision=_safe_int(item.get("revision"), 0),
            branch_id=str(item.get("branch_id") or LEGACY_BRANCH_ID),
            node_id=str(item.get("node_id") or ""),
            attempt_id=str(item.get("attempt_id") or ""),
            event_id=str(item.get("event_id") or ""),
        )
        for item in data.get("events", [])
        if isinstance(item, dict)
    ]
    artifacts = [
        ArtifactRecord(
            path=str(item.get("path") or ""),
            bytes=int(item.get("bytes") or 0),
            sha256=str(item.get("sha256") or ""),
            revision=_safe_int(item.get("revision"), 0),
            branch_id=str(item.get("branch_id") or LEGACY_BRANCH_ID),
        )
        for item in data.get("artifacts", [])
        if isinstance(item, dict)
    ]
    return RunManifest(
        topic=str(data.get("topic") or ""),
        status=str(data.get("status") or "running"),
        started_at=str(data.get("started_at") or _utc_now()),
        updated_at=str(data.get("updated_at") or ""),
        events=events,
        artifacts=artifacts,
        schema_version=_safe_int(data.get("schema_version"), 1),
    )


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _node_id_for_stage(stage: str) -> str:
    try:
        from .workflow_graph import node_for_stage

        return node_for_stage(stage).node_id
    except Exception:
        return ""


def _artifact_inventory(out_dir: Path) -> list[ArtifactRecord]:
    revision = active_revision(out_dir)
    records: list[ArtifactRecord] = []
    if not out_dir.exists():
        return records
    for path in sorted(item for item in out_dir.rglob("*") if item.is_file()):
        rel = str(path.relative_to(out_dir))
        try:
            data = path.read_bytes()
        except OSError:
            continue
        records.append(
            ArtifactRecord(
                path=rel,
                bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                revision=revision,
                branch_id=ACTIVE_BRANCH_ID,
            )
        )
    return records


def _event_detail(event: RunEvent) -> str:
    details: list[str] = []
    if event.metrics:
        details.extend(f"{key}={value}" for key, value in event.metrics.items())
    details.extend(event.notes)
    return "; ".join(details) or "-"
