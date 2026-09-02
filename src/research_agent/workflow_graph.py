from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
import hashlib
import json
import os
import secrets
import shutil
import time
from fnmatch import fnmatch

from .artifacts import write_json, sha256_file as _sha256_file, utc_now as _utc_now, read_json_dict as _read_json
from .provenance import RunManifestRecorder
from .run_lease import acquire_run_lease


WORKFLOW_STATUS_JSON = "workflow-status.json"
ROLLBACK_ARCHIVE_DIR = ".research-agent-archives"
CHECKPOINT_CONTRACT_JSON = "run-checkpoint-contract.json"
MAX_WORKFLOW_EVENTS = 40
ROLLBACK_PREVIEW_TTL_SECONDS = 600
MAX_ROLLBACK_FILES = 10_000
MAX_ROLLBACK_BYTES = 20 * 1024 * 1024 * 1024
# The archive copy plus a safety margin must fit on the same filesystem (ART-03).
MIN_ROLLBACK_FREE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class WorkflowNode:
    node_id: str
    title: str
    role: str
    task: str
    rollback_allowed: bool = True


WORKFLOW_NODES = [
    WorkflowNode("research_planning", "研究规划", "gap_analyst", "界定问题、假设与检索计划"),
    WorkflowNode("literature_review", "文献检索", "literature_scout", "检索并筛选可追溯文献"),
    WorkflowNode("literature_context", "证据整理", "evidence_curator", "构建引用上下文并执行证据门禁"),
    WorkflowNode("review_gate", "研究审核", "skeptical_reviewer", "人工确认文献与研究边界", False),
    WorkflowNode("ideation", "方案探索", "method_architect", "提出可检验候选方案与消融"),
    WorkflowNode("experiment_plan", "实验设计", "benchmark_engineer", "生成安全、可复现的实验计划"),
    WorkflowNode("execution_gate", "执行审核", "benchmark_engineer", "人工确认本地或 Benchmark 执行", False),
    WorkflowNode("experiments", "实验执行", "benchmark_engineer", "运行重复实验并固定产物"),
    WorkflowNode("analysis", "统计分析", "statistician", "配对统计、效应量与结果边界"),
    WorkflowNode("paper_writing", "论文写作", "manuscript_editor", "按证据边界生成论文初稿"),
    WorkflowNode("paper_review", "独立复核", "skeptical_reviewer", "独立检查论断、引用与局限"),
    WorkflowNode("paper_revision", "论文修订", "manuscript_editor", "按复核意见修订并闭环"),
    WorkflowNode("finalization", "审计交付", "evidence_curator", "完成可追溯审计与交付包"),
    WorkflowNode("completed", "完成", "manuscript_editor", "交付最终研究产物", False),
]

ROLLBACK_TARGETS = [node.node_id for node in WORKFLOW_NODES if node.rollback_allowed]

WORKFLOW_EDGES = [
    {"from": "research_planning", "to": "literature_review", "condition": "plan_ready"},
    {"from": "literature_review", "to": "literature_context", "condition": "sources_collected"},
    {"from": "literature_context", "to": "review_gate", "condition": "evidence_gate_ready"},
    {"from": "review_gate", "to": "ideation", "condition": "approved"},
    {"from": "review_gate", "to": "literature_review", "condition": "revision_requested"},
    {"from": "ideation", "to": "experiment_plan", "condition": "idea_selected"},
    {"from": "experiment_plan", "to": "execution_gate", "condition": "execution_requires_approval"},
    {"from": "experiment_plan", "to": "experiments", "condition": "simulated_or_approved"},
    {"from": "execution_gate", "to": "experiments", "condition": "approved"},
    {"from": "experiments", "to": "analysis", "condition": "results_valid"},
    {"from": "experiments", "to": "experiment_plan", "condition": "repair_required"},
    {"from": "analysis", "to": "paper_writing", "condition": "downstream_writing_allowed"},
    {"from": "analysis", "to": "finalization", "condition": "writing_blocked"},
    {"from": "paper_writing", "to": "paper_review", "condition": "draft_ready"},
    {"from": "paper_review", "to": "paper_revision", "condition": "revision_required"},
    {"from": "paper_review", "to": "finalization", "condition": "accepted"},
    {"from": "paper_revision", "to": "paper_review", "condition": "recheck"},
    {"from": "paper_revision", "to": "finalization", "condition": "revision_closed"},
    {"from": "finalization", "to": "completed", "condition": "handoff_ready"},
]

_STAGE_TO_NODE = {
    "queued": "research_planning",
    "started": "research_planning",
    "research_plan_completed": "literature_review",
    "literature_review_completed": "literature_context",
    "literature_context_completed": "review_gate",
    "awaiting_review_approval": "review_gate",
    "review_revision_requested": "review_gate",
    "review_approved": "ideation",
    "ideation_completed": "ideation",
    "exploration_map_completed": "ideation",
    "experiment_manager_completed": "experiment_plan",
    "experiment_manager_blocked": "experiment_plan",
    "experiment_plan_completed": "execution_gate",
    "awaiting_execution_approval": "execution_gate",
    "execution_approved": "experiments",
    "experiments_completed": "analysis",
    "awaiting_experiment_repair": "experiment_plan",
    "analysis_completed": "paper_writing",
    "paper_review_completed": "paper_review",
    "revision_plan_completed": "paper_revision",
    "paper_revision_completed": "paper_review",
    "revision_response_audit_completed": "finalization",
    "final_readiness_completed": "finalization",
    "submission_package_completed": "finalization",
    "iteration_plan_completed": "finalization",
    "llm_trace_audit_completed": "finalization",
    "run_economics_audit_completed": "finalization",
    "llm_runtime_contract_completed": "finalization",
    "agent_observability_audit_completed": "finalization",
    "llm_observability_summary_completed": "finalization",
    "open_source_compliance_completed": "finalization",
    "human_gate_audit_completed": "finalization",
    "repair_queue_completed": "finalization",
    "repair_resolution_audit_completed": "finalization",
    "agent_stage_contract_completed": "finalization",
    "agent_trajectory_completed": "finalization",
    "scorecard_completed": "finalization",
    "run_integrity_audit_completed": "finalization",
    "final_handoff_completed": "finalization",
    "completed": "completed",
    "repair_resume_applied": "research_planning",
    "rollback_applied": "research_planning",
}

_LLM_STAGE_TO_NODE = {
    "research_planning": "research_planning",
    "online_search_query_planning": "literature_review",
    "literature_synthesis": "literature_context",
    "idea_generation": "ideation",
    "experiment_planning": "experiment_plan",
    "paper_writing": "paper_writing",
    "paper_review_loop": "paper_review",
    "paper_revision": "paper_revision",
    "paper_deliberation": "paper_review",
}

_NODE_PATTERNS = {
    # ART-01: nodes own the artifacts they produce. A file that matches no
    # node's ownership is reported by rollback previews as unowned and is
    # never archived automatically.
    "research_planning": [
        "00-question.md",
        "00-human-brief.*",
        "00-prior-run-lessons.*",
        "00-prior-run-library.*",
        "00-open-source-lessons.*",
        "00-research-plan.*",
        "00-preflight.*",
    ],
    "literature_review": ["01-*", "approval.json"],
    "literature_context": [
        "01-context.*",
        "01-review-gate.*",
        "01-citation-audit.*",
        "01-review-feedback.*",
        "01-review-revision-plan.*",
        "01-review-constraints.*",
        "01-references.*",
        "approval.json",
    ],
    "ideation": ["02-*"],
    "experiment_plan": ["03-*"],
    # Rolling back to a gate must invalidate the approval granted at it, so the
    # rerun re-arms the human gate instead of silently reusing the old approval
    # (which request_execution_approval/request_review_approval would otherwise
    # keep honoring while plan/safety/binding hashes look unchanged).
    "review_gate": ["approval.json"],
    "execution_gate": ["03-execution-approval.json", "03-execution-approval.md"],
    "experiments": ["04-*"],
    "analysis": ["05-*"],
    "paper_writing": ["06-*"],
    "paper_review": ["07-*"],
    "paper_revision": ["08-*", "09-*"],
    "finalization": ["10-*", "11-*", "12-*", "13-*", "14-*", "15-*"],
}

_NODE_DIRECTORIES = {
    "experiment_plan": ["experiments", "submission-package"],
    "experiments": ["experiments", "submission-package"],
    "analysis": ["submission-package"],
    "paper_writing": ["submission-package"],
    "paper_review": ["submission-package"],
    "paper_revision": ["submission-package"],
    "finalization": ["submission-package"],
}

# Run-level files belong to the run, not to any workflow node; they are never
# part of a rollback archive and never reported as unowned.
RUN_LEVEL_FILES = (
    ".lease",
    "state.json",
    "workflow-status.json",
    "run-manifest.json",
    "run-manifest.md",
    "run-llm-ledger.json",
    "run-llm-ledger.md",
    "run-config.json",
    "run-checkpoint-contract.json",
    "run-tool-receipts.json",
    "cancel.json",
)


def node_artifact_registry() -> dict[str, Any]:
    """The declared artifact ownership per workflow node (ART-01)."""
    return {
        "schema_version": 1,
        "nodes": [
            {
                "node_id": node.node_id,
                "patterns": list(_NODE_PATTERNS.get(node.node_id, [])),
                "directories": list(_NODE_DIRECTORIES.get(node.node_id, [])),
            }
            for node in WORKFLOW_NODES
        ],
        "run_level_files": list(RUN_LEVEL_FILES),
    }


def owning_nodes_for_artifact(relative: str) -> list[str]:
    """Which nodes claim an artifact path; empty means unowned."""
    owners = [
        node.node_id
        for node in WORKFLOW_NODES
        if any(fnmatch(relative, pattern) for pattern in _NODE_PATTERNS.get(node.node_id, []))
        or any(relative == directory or relative.startswith(f"{directory}/") for directory in _NODE_DIRECTORIES.get(node.node_id, []))
    ]
    return owners

_LOCKS_GUARD = Lock()
_STATUS_LOCKS: dict[str, Lock] = {}


def workflow_definition() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "nodes": [asdict(node) for node in WORKFLOW_NODES],
        "edges": list(WORKFLOW_EDGES),
        "rollback_targets": list(ROLLBACK_TARGETS),
    }


def rollback_options(run_dir: Path) -> list[dict[str, Any]]:
    status = read_workflow_status(run_dir)
    current_node = str(status.get("current_node") or "research_planning")
    current_index = _node_index(current_node)
    return [
        {
            "target": node.node_id,
            "title": node.title,
            "role": node.role,
            "task": node.task,
        }
        for index, node in enumerate(WORKFLOW_NODES)
        if node.rollback_allowed and index <= current_index
    ]


def node_for_stage(stage: str) -> WorkflowNode:
    normalized = str(stage or "").strip()
    node_id = _LLM_STAGE_TO_NODE.get(normalized) or _STAGE_TO_NODE.get(normalized) or "research_planning"
    return next(node for node in WORKFLOW_NODES if node.node_id == node_id)


def update_workflow_stage(out_dir: Path, topic: str, stage: str) -> dict[str, Any]:
    node = node_for_stage(stage)
    return _update_status(
        out_dir,
        topic=topic,
        pipeline_stage=stage,
        node_id=node.node_id,
        agent_id=node.role,
        task=node.task,
        activity_status=_activity_status(stage),
        event_kind="stage",
    )


def begin_workflow_node(out_dir: Path, topic: str, node_id: str) -> dict[str, Any]:
    """Mark a workflow node as actively running.

    Completion boundaries already advance the graph; this covers the long
    stretch of work inside a node (literature retrieval, experiment execution)
    so the UI shows fresh progress instead of the previous stage's name.
    """
    node = next((item for item in WORKFLOW_NODES if item.node_id == node_id), None)
    if node is None:
        raise ValueError(f"unknown workflow node: {node_id}")
    status = _update_status(
        out_dir,
        topic=topic,
        pipeline_stage=node_id,
        node_id=node.node_id,
        agent_id=node.role,
        task=node.task,
        activity_status="running",
        event_kind="stage",
        detail=f"阶段开始：{node.title}",
    )
    with _status_lock(out_dir):
        state_path = out_dir / "state.json"
        state = _read_json(state_path)
        state.update(
            {
                "topic": str(state.get("topic") or topic),
                "current_stage": node.node_id,
                "stage_status": "running",
                "updated_at": _utc_now(),
            }
        )
        write_json(state_path, state)
    return status


def update_agent_activity(
    out_dir: Path,
    *,
    stage: str,
    agent_id: str,
    task: str,
    model: str,
    status: str,
    detail: str = "",
) -> dict[str, Any]:
    node = node_for_stage(stage)
    topic = str(_read_json(out_dir / "state.json").get("topic") or "")
    return _update_status(
        out_dir,
        topic=topic,
        pipeline_stage=stage,
        node_id=node.node_id,
        agent_id=agent_id or node.role,
        task=task or node.task,
        model=model,
        activity_status=status,
        event_kind="agent",
        detail=detail,
    )


def read_workflow_status(out_dir: Path) -> dict[str, Any]:
    data = _read_json(out_dir / WORKFLOW_STATUS_JSON)
    if not data:
        state = _read_json(out_dir / "state.json")
        if state:
            return update_workflow_stage(out_dir, str(state.get("topic") or ""), str(state.get("stage") or "started"))
    return _public_status(data)


def build_rollback_preview(run_dir: Path, target: str) -> dict[str, Any]:
    target_id = str(target or "").strip()
    if target_id not in ROLLBACK_TARGETS:
        raise ValueError(f"invalid rollback target: {target_id}")
    status = _read_json(run_dir / WORKFLOW_STATUS_JSON)
    revision = _safe_int(status.get("revision"), 0)
    checkpoint = _read_json(run_dir / CHECKPOINT_CONTRACT_JSON)
    patterns, directory_names = _rollback_patterns_and_directories(target_id)
    files = _matching_files(run_dir, patterns)
    directories = [name for name in directory_names if _safe_directory(run_dir, name).is_dir()]
    unowned_files = _unowned_files(run_dir)
    artifact_index = [_file_record(run_dir, name) for name in files]
    directory_index = [_directory_record(run_dir, name) for name in directories]
    file_count = len(artifact_index) + sum(int(item["files"]) for item in directory_index)
    total_bytes = sum(int(item["bytes"]) for item in artifact_index) + sum(int(item["bytes"]) for item in directory_index)
    blockers: list[str] = []
    if file_count > MAX_ROLLBACK_FILES:
        blockers.append(f"rollback contains {file_count} files; limit is {MAX_ROLLBACK_FILES}")
    if total_bytes > MAX_ROLLBACK_BYTES:
        blockers.append(f"rollback contains {total_bytes} bytes; limit is {MAX_ROLLBACK_BYTES}")
    review_reapproval = _node_index(target_id) <= _node_index("review_gate")
    execution_reapproval = _node_index(target_id) <= _node_index("experiments")
    # GATE-01 invariant: a promised reapproval must correspond to an approval
    # file that the archive plan actually invalidates; otherwise the rerun
    # could silently reuse the old approval (request_execution_approval honors
    # an existing approval while plan/safety/binding hashes look unchanged).
    # A missing approval file has nothing to invalidate and is not a blocker.
    if review_reapproval and (run_dir / "approval.json").is_file() and "approval.json" not in files:
        blockers.append(
            "review reapproval is required but approval.json is not in the archive plan; "
            "refusing to roll back without invalidating the review gate"
        )
    if (
        execution_reapproval
        and (run_dir / "03-execution-approval.json").is_file()
        and "03-execution-approval.json" not in files
    ):
        blockers.append(
            "execution reapproval is required but 03-execution-approval.json is not in the archive plan; "
            "refusing to roll back without invalidating the execution gate"
        )
    payload = {
        "schema_version": 1,
        "target": target_id,
        "current_revision": revision,
        "next_revision": revision + 1,
        "checkpoint_fingerprint": str(checkpoint.get("fingerprint") or ""),
        "artifacts_to_archive": files,
        "directories_to_archive": directories,
        "artifact_index": artifact_index,
        "directory_index": directory_index,
        "unowned_files": unowned_files,
        "file_count": file_count,
        "total_bytes": total_bytes,
        "review_reapproval_required": review_reapproval,
        "execution_reapproval_required": execution_reapproval,
        "external_side_effects_not_reverted": [
            "已完成的远程 MCP 调用、网络请求和外部 Benchmark 副作用不会被本地回退撤销。"
        ],
        "blockers": blockers,
        "next_action": f"从 {target_id} 节点重新执行",
    }
    return {**payload, "plan_digest": _digest(payload)}


def issue_rollback_preview(run_dir: Path, target: str) -> dict[str, Any]:
    cleanup_expired_previews(run_dir)
    if target not in {item["target"] for item in rollback_options(run_dir)}:
        raise ValueError("rollback target is later than the current workflow node")
    preview = build_rollback_preview(run_dir, target)
    preview_id = secrets.token_hex(16)
    token = secrets.token_urlsafe(32)
    issued_at_epoch = int(time.time())
    record = {
        "schema_version": 1,
        "preview_id": preview_id,
        "run_id": run_dir.name,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "issued_at_epoch": issued_at_epoch,
        "expires_at_epoch": issued_at_epoch + ROLLBACK_PREVIEW_TTL_SECONDS,
        "plan_digest": preview["plan_digest"],
        "target": preview["target"],
        "current_revision": preview["current_revision"],
        "status": "issued",
    }
    control_path = _preview_record_path(run_dir, preview_id)
    write_json(control_path, record)
    try:
        os.chmod(control_path, 0o600)
    except OSError:
        pass
    return {
        **preview,
        "preview_id": preview_id,
        "preview_token": token,
        "issued_at_epoch": record["issued_at_epoch"],
        "expires_at_epoch": record["expires_at_epoch"],
    }


def apply_rollback(
    run_dir: Path,
    target: str,
    preview_id: str,
    preview_token: str,
    *,
    reason: str = "",
    actor: str = "",
) -> dict[str, Any]:
    """Archive the rerun set and commit the rollback as a crash-safe transaction.

    Holds the cross-process run lease for the whole apply (LOCK-01), journals
    every step (TX-01), persists reason/actor into the archive report and the
    manifest (ART-02), and refuses to run when disk space cannot hold the
    archive copy (ART-03).
    """
    with acquire_run_lease(run_dir, "rollback", owner=actor or "rollback"):
        return _apply_rollback_locked(
            run_dir,
            target,
            preview_id,
            preview_token,
            reason=reason,
            actor=actor,
        )


def _apply_rollback_locked(
    run_dir: Path,
    target: str,
    preview_id: str,
    preview_token: str,
    *,
    reason: str = "",
    actor: str = "",
) -> dict[str, Any]:
    reconciled = reconcile_rollback_journals(run_dir)
    record_path = _preview_record_path(run_dir, preview_id)
    record = _read_json(record_path)
    if not record or record.get("run_id") != run_dir.name or record.get("status") != "issued":
        raise RuntimeError("rollback preview is missing, consumed, or invalid")
    if int(record.get("expires_at_epoch") or 0) < int(time.time()):
        record["status"] = "expired"
        write_json(record_path, record)
        raise RuntimeError("rollback preview expired; preview the target again")
    supplied_hash = hashlib.sha256(str(preview_token or "").encode("utf-8")).hexdigest()
    if not _constant_time_equal(supplied_hash, str(record.get("token_sha256") or "")):
        raise RuntimeError("rollback preview token is invalid")
    preview = build_rollback_preview(run_dir, target)
    if (
        str(record.get("target") or "") != target
        or _safe_int(record.get("current_revision"), -1) != int(preview["current_revision"])
        or not _constant_time_equal(str(record.get("plan_digest") or ""), str(preview["plan_digest"]))
    ):
        raise RuntimeError("rollback preview is stale; preview the target again before applying")
    if preview["blockers"]:
        raise RuntimeError("rollback is blocked: " + "; ".join(preview["blockers"]))
    free_bytes = shutil.disk_usage(str(run_dir)).free
    if free_bytes < preview["total_bytes"] + MIN_ROLLBACK_FREE_BYTES:
        raise RuntimeError(
            f"rollback refused: only {free_bytes} bytes free, "
            f"archive copy needs {preview['total_bytes']} bytes plus a {MIN_ROLLBACK_FREE_BYTES} byte margin"
        )
    record["status"] = "applying"
    write_json(record_path, record)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive_id = f"{timestamp}-r{preview['next_revision']}-{preview['target']}"
    applied_at = _utc_now()
    archive_root = _archive_run_root(run_dir) / archive_id
    journal: dict[str, Any] = {
        "schema_version": 1,
        "state": "prepared",
        "archive_id": archive_id,
        "target": target,
        "revision": preview["next_revision"],
        "previous_revision": preview["current_revision"],
        "applied_at": applied_at,
        "reason": str(reason or "").strip()[:500],
        "actor": str(actor or "").strip()[:120],
        "artifact_index": preview["artifact_index"],
        "directory_index": preview["directory_index"],
        "moved_files": [],
        "moved_directories": [],
        "metadata_committed": False,
        "error": "",
        "updated_at": _utc_now(),
    }
    journal_path = _journal_path(run_dir, archive_id)
    write_json(journal_path, journal)
    archive_root.mkdir(parents=True, exist_ok=True)
    moved_files: list[str] = []
    moved_directories: list[str] = []
    try:
        for item in preview["artifact_index"]:
            relative = str(item["path"])
            source = _safe_file(run_dir, relative)
            if _sha256_file(source) != item["sha256"]:
                raise RuntimeError(f"rollback artifact changed after preview: {relative}")
            destination = archive_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            moved_files.append(relative)
            journal["state"] = "moving"
            journal["moved_files"] = moved_files
            journal["updated_at"] = _utc_now()
            write_json(journal_path, journal)
        for item in preview["directory_index"]:
            relative = str(item["path"])
            source = _safe_directory(run_dir, relative)
            if _directory_digest(source) != item["sha256"]:
                raise RuntimeError(f"rollback directory changed after preview: {relative}")
            destination = archive_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved_directories.append(relative)
            journal["state"] = "moving"
            journal["moved_directories"] = moved_directories
            journal["updated_at"] = _utc_now()
            write_json(journal_path, journal)
    except BaseException as exc:
        # In-process failure: restore the archived files so the run stays on
        # the old revision. The journal is marked failed (not reconciled
        # forward) because the operator's intent was to abort.
        _restore_partial_archive(run_dir, archive_root, moved_files, moved_directories)
        journal["state"] = "failed"
        journal["error"] = str(exc)[:400]
        journal["updated_at"] = _utc_now()
        write_json(journal_path, journal)
        record["status"] = "failed"
        write_json(record_path, record)
        raise

    journal["state"] = "moves_done"
    journal["moved_files"] = moved_files
    journal["moved_directories"] = moved_directories
    journal["updated_at"] = _utc_now()
    write_json(journal_path, journal)
    report = _commit_rollback_metadata(
        run_dir,
        journal,
        archive_root=archive_root,
        preview=preview,
        moved_files=moved_files,
        moved_directories=moved_directories,
    )
    # STATE-01: nodes from the target onward were invalidated by this rollback.
    try:
        from .workflow_state import append_node_event

        target_index = _node_index(target)
        for node in WORKFLOW_NODES[target_index:]:
            if node.node_id == "completed":
                continue
            append_node_event(
                run_dir,
                node_id=node.node_id,
                event_type="rolled_back",
                revision=_safe_int(journal.get("revision"), 0),
                detail=f"rollback archive {archive_id}",
            )
    except Exception:
        pass
    journal["state"] = "completed"
    journal["metadata_committed"] = True
    journal["updated_at"] = _utc_now()
    write_json(journal_path, journal)
    record["status"] = "consumed"
    record["consumed_at"] = applied_at
    record["archive_ref"] = archive_id
    write_json(record_path, record)
    report["reconciled_journals"] = reconciled
    return report


def _commit_rollback_metadata(
    run_dir: Path,
    journal: dict[str, Any],
    *,
    archive_root: Path,
    preview: dict[str, Any],
    moved_files: list[str],
    moved_directories: list[str],
) -> dict[str, Any]:
    """Write the rollback report, index, checkpoint revision, state, and manifest.

    Every step is idempotent so a crashed run can be reconciled without
    duplicating index entries, workflow events, or manifest events.
    """
    archive_id = str(journal["archive_id"])
    target = str(journal["target"])
    applied_at = str(journal["applied_at"])
    report = {
        **preview,
        "status": "applied",
        "applied_at": applied_at,
        "archive_ref": archive_id,
        "archived_artifacts": moved_files,
        "archived_directories": moved_directories,
        "reason": str(journal.get("reason") or ""),
        "actor": str(journal.get("actor") or ""),
    }
    write_json(archive_root / "rollback.json", report)
    _update_rollback_index(run_dir, report)
    _mark_checkpoint_revision(run_dir, report)
    _set_rollback_status(run_dir, report)
    topic = str(_read_json(run_dir / "state.json").get("topic") or run_dir.name)
    events = _read_json(run_dir / "run-manifest.json").get("events")
    already_recorded = any(
        isinstance(event, dict)
        and event.get("stage") == "workflow_rollback"
        and _safe_int((event.get("metrics") or {}).get("revision"), -1) == _safe_int(journal.get("revision"), -1)
        for event in (events if isinstance(events, list) else [])
    )
    if not already_recorded:
        RunManifestRecorder(run_dir, topic).record(
            "workflow_rollback",
            status="completed",
            inputs=[f"archive:{archive_id}/rollback.json"],
            outputs=["state.json", WORKFLOW_STATUS_JSON],
            notes=[
                f"archived immutable revision before rerunning {target}",
                *( [f"reason: {journal.get('reason')}" if journal.get("reason") else "reason: (not provided)"] ),
            ],
            metrics={
                "target": target,
                "revision": _safe_int(journal.get("revision"), 0),
                "files": len(moved_files),
                "directories": len(moved_directories),
            },
        )
    return report


def reconcile_rollback_journals(run_dir: Path) -> list[str]:
    """Finish any rollback left half-done by a crashed process (TX-01).

    Only journals in ``prepared``/``moving``/``moves_done`` are reconciled
    forward; ``failed`` journals keep the run on the old revision and stay as
    an audit record. Returns the archive ids it completed.
    """
    completed: list[str] = []
    archive_run_root = _archive_run_root(run_dir)
    previews = archive_run_root / "previews"
    if not archive_run_root.is_dir():
        return completed
    for journal_path in sorted(archive_run_root.glob("journal-*.json")):
        journal = _read_json(journal_path)
        state = str(journal.get("state") or "")
        if state not in {"prepared", "moving", "moves_done"}:
            continue
        archive_id = str(journal.get("archive_id") or "")
        if not archive_id:
            continue
        try:
            archive_root = _archive_run_root(run_dir) / archive_id
            moved_files = [str(item) for item in journal.get("moved_files", [])]
            moved_directories = [str(item) for item in journal.get("moved_directories", [])]
            for item in journal.get("artifact_index", []):
                if not isinstance(item, dict):
                    continue
                relative = str(item["path"])
                if relative in moved_files:
                    continue
                source = run_dir / relative
                destination = archive_root / relative
                if source.is_file():
                    _safe_file(run_dir, relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
                    moved_files.append(relative)
                elif destination.is_file():
                    moved_files.append(relative)
                else:
                    raise RuntimeError(f"rollback journal {archive_id}: artifact is neither in the run nor archived: {relative}")
                journal["moved_files"] = moved_files
                journal["state"] = "moving"
                write_json(journal_path, journal)
            for item in journal.get("directory_index", []):
                if not isinstance(item, dict):
                    continue
                relative = str(item["path"])
                if relative in moved_directories:
                    continue
                source = run_dir / relative
                destination = archive_root / relative
                if source.is_dir() and not source.is_symlink():
                    shutil.move(str(source), str(destination))
                    moved_directories.append(relative)
                elif destination.is_dir():
                    moved_directories.append(relative)
                else:
                    raise RuntimeError(f"rollback journal {archive_id}: directory is neither in the run nor archived: {relative}")
                journal["moved_directories"] = moved_directories
                journal["state"] = "moving"
                write_json(journal_path, journal)
            journal["state"] = "moves_done"
            write_json(journal_path, journal)
            preview = build_rollback_preview(run_dir, str(journal.get("target") or ""))
            # The scan above ran on a half-moved run; the journal's own plan is
            # the committed truth for what was archived.
            preview["artifact_index"] = list(journal.get("artifact_index", []))
            preview["directory_index"] = list(journal.get("directory_index", []))
            preview["next_revision"] = _safe_int(journal.get("revision"), 0)
            preview["current_revision"] = _safe_int(journal.get("previous_revision"), 0)
            preview["blockers"] = [
                blocker
                for blocker in preview["blockers"]
                if "archive plan" not in blocker
            ]
            preview["file_count"] = len(moved_files) + sum(
                int(item.get("files") or 0) for item in preview["directory_index"] if isinstance(item, dict)
            )
            preview["total_bytes"] = sum(
                int(item.get("bytes") or 0) for item in preview["artifact_index"] if isinstance(item, dict)
            ) + sum(
                int(item.get("bytes") or 0) for item in preview["directory_index"] if isinstance(item, dict)
            )
            report = _commit_rollback_metadata(
                run_dir,
                journal,
                archive_root=archive_root,
                preview=preview,
                moved_files=moved_files,
                moved_directories=moved_directories,
            )
            journal["state"] = "completed"
            journal["metadata_committed"] = True
            journal["updated_at"] = _utc_now()
            write_json(journal_path, journal)
            # A stale preview record for this crashed apply may still say
            # "applying"; consume it so it cannot be applied twice.
            for record_path in previews.glob("*.json"):
                preview_record = _read_json(record_path)
                if (
                    preview_record.get("status") in {"issued", "applying"}
                    and preview_record.get("run_id") == run_dir.name
                    and str(preview_record.get("target") or "") == str(journal.get("target"))
                ):
                    preview_record["status"] = "consumed"
                    preview_record["archive_ref"] = archive_id
                    write_json(record_path, preview_record)
            completed.append(archive_id)
            report.setdefault("reconciled", True)
        except Exception as exc:
            journal["state"] = "failed"
            journal["error"] = str(exc)[:400]
            journal["updated_at"] = _utc_now()
            write_json(journal_path, journal)
    return completed


def cleanup_expired_previews(run_dir: Path) -> int:
    """Delete preview records that can no longer be applied (ART-03)."""
    now = int(time.time())
    removed = 0
    previews = _archive_run_root(run_dir) / "previews"
    if not previews.is_dir():
        return removed
    for record_path in sorted(previews.glob("*.json")):
        record = _read_json(record_path)
        if not record:
            removed += _unlink_if_expired_file(record_path, now)
            continue
        status = str(record.get("status") or "")
        expired = int(record.get("expires_at_epoch") or 0) < now
        if expired and status in {"issued", "expired", "failed"}:
            try:
                record_path.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def _unlink_if_expired_file(path: Path, now: int) -> int:
    try:
        if path.stat().st_mtime + ROLLBACK_PREVIEW_TTL_SECONDS < now:
            path.unlink()
            return 1
    except OSError:
        return 0
    return 0


def _journal_path(run_dir: Path, archive_id: str) -> Path:
    return _archive_run_root(run_dir) / f"journal-{archive_id}.json"


def _update_status(
    out_dir: Path,
    *,
    topic: str,
    pipeline_stage: str,
    node_id: str,
    agent_id: str,
    task: str,
    activity_status: str,
    event_kind: str,
    model: str = "",
    detail: str = "",
) -> dict[str, Any]:
    with _status_lock(out_dir):
        path = out_dir / WORKFLOW_STATUS_JSON
        previous = _read_json(path)
        now = _utc_now()
        previous_node = str(previous.get("current_node") or "")
        previous_status = str(previous.get("activity_status") or "")
        started_at = str(previous.get("activity_started_at") or now)
        if previous_node != node_id or activity_status == "running" and previous_status != "running":
            started_at = now
        events = previous.get("events") if isinstance(previous.get("events"), list) else []
        event = {
            "at": now,
            "kind": event_kind,
            "node_id": node_id,
            "stage": pipeline_stage,
            "status": activity_status,
            "agent_id": agent_id,
            "task": task,
            "model": model,
            "detail": str(detail or "")[:400],
        }
        last = events[-1] if events and isinstance(events[-1], dict) else {}
        if any(last.get(key) != event.get(key) for key in ["kind", "node_id", "stage", "status", "agent_id", "model", "detail"]):
            events = [*events, event][-MAX_WORKFLOW_EVENTS:]
        current_index = _node_index(node_id)
        nodes = []
        for index, node in enumerate(WORKFLOW_NODES):
            if node.node_id == "completed":
                node_status = "completed" if node_id == "completed" else "pending"
            elif index < current_index or node_id == "completed":
                node_status = "completed"
            elif index == current_index:
                node_status = "waiting" if activity_status == "waiting" else "running"
            else:
                node_status = "pending"
            nodes.append({**asdict(node), "status": node_status})
        completed = sum(1 for node in nodes if node["status"] == "completed")
        data = {
            "schema_version": 1,
            "topic": topic or previous.get("topic") or "",
            "revision": _safe_int(previous.get("revision"), 0),
            "pipeline_stage": pipeline_stage,
            "current_node": node_id,
            "current_node_title": next(node.title for node in WORKFLOW_NODES if node.node_id == node_id),
            "agent_id": agent_id,
            "task": task,
            "model": model or str(previous.get("model") or ""),
            "activity_status": activity_status,
            "activity_started_at": started_at,
            "updated_at": now,
            "completed_nodes": completed,
            "total_nodes": len(WORKFLOW_NODES),
            "nodes": nodes,
            "edges": list(WORKFLOW_EDGES),
            "events": events,
        }
        write_json(path, data)
        return _public_status(data)


def _set_rollback_status(run_dir: Path, report: dict[str, Any]) -> None:
    state = _read_json(run_dir / "state.json")
    topic = str(state.get("topic") or run_dir.name)
    # Idempotent for crash recovery: re-committing the same revision must not
    # append a duplicate workflow event or rewrite the original timestamp.
    already_applied = (
        str(state.get("stage") or "") == "rollback_applied"
        and _safe_int(state.get("workflow_revision"), -1) == _safe_int(report["next_revision"], -1)
    )
    if already_applied:
        return
    write_json(
        run_dir / "state.json",
        {
            "topic": topic,
            "stage": "rollback_applied",
            "workflow_revision": report["next_revision"],
            "rollback_target": report["target"],
            "updated_at": report["applied_at"],
        },
    )
    with _status_lock(run_dir):
        status = _read_json(run_dir / WORKFLOW_STATUS_JSON)
        status.update(
            {
                "revision": report["next_revision"],
                "pipeline_stage": "rollback_applied",
                "current_node": report["target"],
                "current_node_title": next(node.title for node in WORKFLOW_NODES if node.node_id == report["target"]),
                "activity_status": "waiting",
                "activity_started_at": report["applied_at"],
                "updated_at": report["applied_at"],
            }
        )
        events = status.get("events") if isinstance(status.get("events"), list) else []
        status["events"] = [
            *events,
            {
                "at": report["applied_at"],
                "kind": "rollback",
                "node_id": report["target"],
                "stage": "rollback_applied",
                "status": "completed",
                "agent_id": "human_operator",
                "task": f"归档 revision {report['current_revision']} 并回退",
                "model": "",
                "detail": report["archive_ref"],
            },
        ][-MAX_WORKFLOW_EVENTS:]
        write_json(run_dir / WORKFLOW_STATUS_JSON, status)


def _update_rollback_index(run_dir: Path, report: dict[str, Any]) -> None:
    path = _archive_run_root(run_dir) / "index.json"
    current = _read_json(path)
    entries = current.get("entries") if isinstance(current.get("entries"), list) else []
    # Idempotent for crash recovery: the same archive is never indexed twice.
    if any(entry.get("archive_ref") == report["archive_ref"] for entry in entries if isinstance(entry, dict)):
        return
    entries.append(
        {
            "revision": report["next_revision"],
            "target": report["target"],
            "applied_at": report["applied_at"],
            "archive_ref": report["archive_ref"],
            "plan_digest": report["plan_digest"],
            "reason": str(report.get("reason") or "")[:200],
            "actor": str(report.get("actor") or "")[:80],
        }
    )
    write_json(path, {"schema_version": 1, "entries": entries[-100:]})


def _mark_checkpoint_revision(run_dir: Path, report: dict[str, Any]) -> None:
    path = run_dir / CHECKPOINT_CONTRACT_JSON
    checkpoint = _read_json(path)
    if not checkpoint:
        return
    checkpoint["workflow_revision"] = report["next_revision"]
    checkpoint["rollback"] = {
        "target": report["target"],
        "applied_at": report["applied_at"],
        "archive_ref": report["archive_ref"],
        "previous_fingerprint": report["checkpoint_fingerprint"],
    }
    write_json(path, checkpoint)


def _rollback_patterns_and_directories(target: str) -> tuple[list[str], list[str]]:
    start = _node_index(target)
    patterns: list[str] = []
    directories: list[str] = []
    for node in WORKFLOW_NODES[start:]:
        patterns.extend(_NODE_PATTERNS.get(node.node_id, []))
        directories.extend(_NODE_DIRECTORIES.get(node.node_id, []))
    # Approval invalidation closure: whenever rolling back to `target` promises
    # a reapproval, the approval file authorizing the rerun set must be part of
    # the archive plan even when the gate node itself is not being rerun
    # (e.g. rolling back to `experiments` still invalidates the execution
    # approval granted at the preceding gate).
    if start <= _node_index("review_gate"):
        patterns.extend(_NODE_PATTERNS.get("review_gate", []))
    if start <= _node_index("experiments"):
        patterns.extend(_NODE_PATTERNS.get("execution_gate", []))
    patterns.extend(["run-diagnostics.*", "run-recovery-plan.*"])
    return _unique(patterns), _unique(directories)


def _matching_files(run_dir: Path, patterns: list[str]) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        for path in run_dir.glob(pattern):
            if path.is_file() and _is_relative_to(path, run_dir):
                values.append(str(path.relative_to(run_dir)))
    return sorted(_unique(values))


def _unowned_files(run_dir: Path, *, limit: int = 200) -> list[str]:
    """Files present in the run that no node claims (ART-01, informational).

    Unowned files are surfaced by rollback previews but never archived
    automatically.
    """
    all_patterns = [pattern for node in WORKFLOW_NODES for pattern in _NODE_PATTERNS.get(node.node_id, [])]
    owned_directories = [
        directory for node in WORKFLOW_NODES for directory in _NODE_DIRECTORIES.get(node.node_id, [])
    ]
    unowned: list[str] = []
    if not run_dir.is_dir():
        return unowned
    for path in sorted(run_dir.rglob("*")):
        if len(unowned) >= limit:
            break
        if not path.is_file() or path.is_symlink() or not _is_relative_to(path, run_dir):
            continue
        relative = str(path.relative_to(run_dir))
        if relative in RUN_LEVEL_FILES:
            continue
        if any(fnmatch(relative, pattern) for pattern in all_patterns):
            continue
        if any(relative == directory or relative.startswith(f"{directory}/") for directory in owned_directories):
            continue
        unowned.append(relative)
    return unowned


def _file_record(run_dir: Path, relative: str) -> dict[str, Any]:
    safe = _safe_file(run_dir, relative)
    return {"path": relative, "bytes": safe.stat().st_size, "sha256": _sha256_file(safe)}


def _directory_record(run_dir: Path, relative: str) -> dict[str, Any]:
    path = _safe_directory(run_dir, relative)
    files = _safe_directory_files(path)
    return {
        "path": relative,
        "sha256": _directory_digest(path, files),
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files),
    }


def _directory_digest(path: Path, files: list[Path] | None = None) -> str:
    digest = hashlib.sha256()
    for item in files if files is not None else _safe_directory_files(path):
        relative = str(item.relative_to(path)).encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(_sha256_file(item)))
    return digest.hexdigest()


def _restore_partial_archive(run_dir: Path, archive_root: Path, files: list[str], directories: list[str]) -> None:
    for relative in reversed(directories):
        archived = archive_root / relative
        destination = run_dir / relative
        if archived.exists() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(archived), str(destination))
    for relative in reversed(files):
        archived = archive_root / relative
        destination = run_dir / relative
        if archived.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(archived, destination)


def _safe_file(run_dir: Path, relative: str) -> Path:
    path = run_dir / relative
    if not path.is_file() or path.is_symlink() or not _is_relative_to(path, run_dir):
        raise RuntimeError(f"unsafe or missing rollback artifact: {relative}")
    return path


def _safe_directory(run_dir: Path, relative: str) -> Path:
    path = run_dir / relative
    if path.is_symlink() or not _is_relative_to(path, run_dir):
        raise RuntimeError(f"unsafe rollback directory: {relative}")
    return path


def _safe_directory_files(path: Path) -> list[Path]:
    files: list[Path] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise RuntimeError(f"rollback directory contains a symlink: {item.relative_to(path)}")
        if item.is_dir():
            continue
        if not item.is_file():
            raise RuntimeError(f"rollback directory contains a non-regular file: {item.relative_to(path)}")
        files.append(item)
    return files


def _archive_root(run_dir: Path) -> Path:
    return run_dir.parent / ROLLBACK_ARCHIVE_DIR


def _archive_run_root(run_dir: Path) -> Path:
    root = _archive_root(run_dir) / run_dir.name
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _preview_record_path(run_dir: Path, preview_id: str) -> Path:
    normalized = str(preview_id or "").strip()
    if not normalized or len(normalized) > 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise RuntimeError("invalid rollback preview id")
    path = _archive_run_root(run_dir) / "previews" / f"{normalized}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _public_status(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: data.get(key)
        for key in [
            "schema_version",
            "topic",
            "revision",
            "pipeline_stage",
            "current_node",
            "current_node_title",
            "agent_id",
            "task",
            "model",
            "activity_status",
            "activity_started_at",
            "updated_at",
            "completed_nodes",
            "total_nodes",
            "nodes",
            "edges",
            "events",
        ]
    }


def _activity_status(stage: str) -> str:
    if stage.startswith("awaiting_") or stage in {"review_revision_requested", "experiment_manager_blocked"}:
        return "waiting"
    if stage == "completed":
        return "completed"
    if stage in {"failed", "cancelled"}:
        return stage
    return "running"


def _status_lock(out_dir: Path) -> Lock:
    key = str(out_dir.resolve())
    with _LOCKS_GUARD:
        return _STATUS_LOCKS.setdefault(key, Lock())


def _node_index(node_id: str) -> int:
    return next(index for index, node in enumerate(WORKFLOW_NODES) if node.node_id == node_id)


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


