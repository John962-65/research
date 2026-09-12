"""Node-level execution state for the workflow graph (STATE-01 / ENGINE-01).

Node status is reduced from an append-only event log (``run-node-events.json``)
instead of being derived from a linear index, so skipped/failed/cancelled/
rolled_back nodes are representable and every revision keeps its own attempt
list. Pipeline stage transitions are adapted into node events at the existing
``_write_state``/``_stage_begin`` boundaries; the WorkflowEngine turns the
declared edges into testable predicates over the reduced state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import json
import uuid

from .artifacts import read_json, write_json, utc_now as _utc_now


NODE_EVENT_JSON = "run-node-events.json"

NODE_EVENT_TYPES = frozenset(
    {"started", "completed", "waiting", "failed", "skipped", "cancelled", "rolled_back", "stale"}
)
NODE_STATUSES = frozenset({"pending", "running", *NODE_EVENT_TYPES})

# Pipeline state transitions that complete one or more nodes. Compound cases
# are explicit: paper_review_completed finishes both the writing and the
# review node; the 13-* audit chain finishes finalization piecewise.
STAGE_COMPLETIONS: dict[str, tuple[str, ...]] = {
    "research_plan_completed": ("research_planning",),
    "literature_review_completed": ("literature_review",),
    "literature_context_completed": ("literature_context",),
    "review_approved": ("review_gate",),
    "ideation_completed": ("ideation",),
    "exploration_map_completed": ("ideation",),
    "experiment_manager_completed": ("ideation",),
    "experiment_plan_completed": ("experiment_plan",),
    "execution_approved": ("execution_gate",),
    "experiments_completed": ("experiments",),
    "analysis_completed": ("analysis",),
    "paper_review_completed": ("paper_writing", "paper_review"),
    "revision_response_audit_completed": ("paper_revision",),
    "final_readiness_completed": ("finalization",),
    "submission_package_completed": ("finalization",),
    "iteration_plan_completed": ("finalization",),
    "llm_trace_audit_completed": ("finalization",),
    "run_economics_audit_completed": ("finalization",),
    "llm_runtime_contract_completed": ("finalization",),
    "agent_observability_audit_completed": ("finalization",),
    "llm_observability_summary_completed": ("finalization",),
    "open_source_compliance_completed": ("finalization",),
    "human_gate_audit_completed": ("finalization",),
    "repair_queue_completed": ("finalization",),
    "repair_resolution_audit_completed": ("finalization",),
    "agent_stage_contract_completed": ("finalization",),
    "agent_trajectory_completed": ("finalization",),
    "scorecard_completed": ("finalization",),
    "run_integrity_audit_completed": ("finalization",),
    "completed": ("completed",),
}

# Pipeline state transitions that put a node (back) into waiting for a human.
STAGE_WAITING: dict[str, str] = {
    "awaiting_review_approval": "review_gate",
    "review_revision_requested": "review_gate",
    "awaiting_execution_approval": "execution_gate",
    "awaiting_experiment_repair": "experiment_plan",
    "experiment_manager_blocked": "experiment_plan",
}


def stage_to_node_events(stage: str) -> list[tuple[str, str]]:
    """Adapt a pipeline state transition into ``(node_id, event_type)`` pairs."""
    normalized = str(stage or "").strip()
    events: list[tuple[str, str]] = []
    if normalized == "started":
        events.append(("research_planning", "started"))
        return events
    for node_id in STAGE_COMPLETIONS.get(normalized, ()):
        events.append((node_id, "completed"))
    waiting_node = STAGE_WAITING.get(normalized)
    if waiting_node:
        events.append((waiting_node, "waiting"))
    return events


def append_node_event(
    run_dir: Path,
    *,
    node_id: str,
    event_type: str,
    revision: int | None = None,
    detail: str = "",
) -> dict[str, Any]:
    """Append one node event; the log is append-only and never rewritten."""
    if event_type not in NODE_EVENT_TYPES:
        raise ValueError(f"unknown node event type: {event_type}")
    if revision is None:
        from .provenance import active_revision

        revision = active_revision(run_dir)
    path = Path(run_dir) / NODE_EVENT_JSON
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        data = {}
    events = data.get("events") if isinstance(data.get("events"), list) else []
    event = {
        "event_id": uuid.uuid4().hex,
        "at": _utc_now(),
        "kind": "node",
        "node_id": str(node_id),
        "type": event_type,
        "revision": int(revision),
        "detail": str(detail or "")[:400],
    }
    events.append(event)
    write_json(path, {"schema_version": 1, "events": events})
    return event


def append_node_events(run_dir: Path, pairs: list[tuple[str, str]], *, detail: str = "") -> list[dict[str, Any]]:
    return [append_node_event(run_dir, node_id=node_id, event_type=event_type, detail=detail) for node_id, event_type in pairs]


def read_node_events(run_dir: Path) -> list[dict[str, Any]]:
    try:
        data = read_json(Path(run_dir) / NODE_EVENT_JSON)
    except (OSError, json.JSONDecodeError):
        return []
    events = data.get("events") if isinstance(data.get("events"), list) else []
    return [event for event in events if isinstance(event, dict)]


def reduce_node_states(events: list[dict[str, Any]], active_revision: int, node_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Reduce the append-only event log into per-node state (STATE-01).

    Only events up to ``active_revision`` count. A node completed at an older
    revision stays completed (its artifacts survived the rollback); nodes the
    rollback invalidated carry a ``rolled_back`` event at the new revision.
    """
    states: dict[str, dict[str, Any]] = {}
    for node_id in node_ids:
        node_events = [
            event
            for event in events
            if str(event.get("node_id") or "") == node_id and _safe_int(event.get("revision"), 0) <= _safe_int(active_revision, 0)
        ]
        node_events.sort(key=lambda event: ( _safe_int(event.get("revision"), 0), str(event.get("at") or "")))
        attempts = _reduce_attempts(node_events)
        status = "pending"
        if node_events:
            last_type = str(node_events[-1].get("type") or "")
            if last_type in NODE_STATUSES:
                status = "running" if last_type == "started" else last_type
        states[node_id] = {
            "node_id": node_id,
            "status": status,
            "attempts": attempts,
            "current_attempt": attempts[-1]["attempt"] if attempts else 0,
        }
    return states


def _reduce_attempts(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_key: tuple[int, int] | None = None
    counter: dict[int, int] = {}
    for event in node_events:
        revision = _safe_int(event.get("revision"), 0)
        if str(event.get("type") or "") == "started":
            counter[revision] = counter.get(revision, 0) + 1
        attempt_no = counter.get(revision, 0) or 1
        key = (revision, attempt_no)
        if current is None or key != current_key:
            if current is not None:
                attempts.append(current)
            current = {
                "revision": revision,
                "attempt": attempt_no,
                "status": str(event.get("type") or ""),
                "started_at": str(event.get("at") or ""),
                "ended_at": str(event.get("at") or ""),
                "events": 1,
            }
            current_key = key
        else:
            current["status"] = str(event.get("type") or "")
            current["ended_at"] = str(event.get("at") or "")
            current["events"] = int(current.get("events") or 0) + 1
    if current is not None:
        attempts.append(current)
    return attempts


def read_node_states(run_dir: Path) -> dict[str, dict[str, Any]]:
    from .provenance import active_revision
    from .workflow_graph import WORKFLOW_NODES

    node_ids = [node.node_id for node in WORKFLOW_NODES]
    return reduce_node_states(read_node_events(run_dir), active_revision(run_dir), node_ids)


def validate_node_state_consistency(states: dict[str, dict[str, Any]], node_order: list[str]) -> list[str]:
    """Graph-order invariants over reduced states (used by the integrity audit).

    A node may not be completed (or otherwise advanced) while an earlier node
    has never produced execution events — that means artifacts exist without
    the execution that produced them.
    """
    issues: list[str] = []
    for index, node_id in enumerate(node_order):
        status = str(states.get(node_id, {}).get("status") or "pending")
        if status == "pending":
            continue
        earlier_pending = [
            earlier
            for earlier in node_order[:index]
            if str(states.get(earlier, {}).get("status") or "pending") == "pending"
        ]
        if earlier_pending:
            issues.append(
                f"node {node_id} is {status} but earlier nodes never started: {', '.join(earlier_pending)}"
            )
    return issues


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class EdgeDecision:
    from_node: str
    to_node: str
    condition: str
    satisfied: bool


@dataclass(frozen=True)
class NodeOutcome:
    status: str = "completed"


class WorkflowDispatchError(RuntimeError):
    """The graph cannot select a unique, registered continuation."""


class WorkflowEngine:
    """Executable handler dispatch over reduced node state (ENGINE-01).

    The pipeline registers executable handlers with ``run``. Every edge has a
    predicate over
    ``(node_states, facts)``; ``facts`` carries the artifact-level decisions
    (mode requires approval, writing blocked, revisions required) that the
    pipeline and audits supply. Table-driven tests prove each predicate is
    satisfiable, so no declared edge is dead.
    """

    def __init__(self, node_ids: list[str]) -> None:
        self.node_ids = list(node_ids)
        self._predicates = self._build_predicates()

    def run(
        self, run_dir: Path, *, start: str,
        handlers: dict[str, Callable[[], NodeOutcome | None]],
        facts: Callable[[], dict[str, bool]],
        terminal_nodes: set[str],
        before_node: Callable[[str], None] | None = None,
        on_edge: Callable[[str, str], None] | None = None,
        max_steps: int = 128,
        from_node: str | None = None,
    ) -> str:
        """Execute registered handlers; predicates, not file presence, select edges.

        A handler owns loading/validating its checkpoint and its actual work.
        Completion is committed only after it returns. Waiting stops dispatch;
        exceptions propagate to the existing CLI/Web recovery boundary.
        """
        current = start
        if from_node is not None:
            successors = self.satisfied_successors(from_node, read_node_states(run_dir), facts())
            if successors != [start]:
                raise WorkflowDispatchError(f"cannot resume {from_node}->{start}: enabled successors {successors}")
            if on_edge:
                on_edge(from_node, start)
        for _ in range(max_steps):
            if current not in self.node_ids or current not in handlers:
                raise WorkflowDispatchError(f"no executable handler for {current}")
            if before_node:
                before_node(current)
            append_node_event(run_dir, node_id=current, event_type="started", detail="engine dispatch")
            try:
                outcome = handlers[current]() or NodeOutcome()
            except BaseException as exc:
                status = "cancelled" if type(exc).__name__ == "PipelineCancelled" else (
                    "waiting" if type(exc).__name__ == "PipelineReviewRevisionRequested" else "failed")
                append_node_event(run_dir, node_id=current, event_type=status, detail=type(exc).__name__)
                raise
            if outcome.status not in {"completed", "waiting", "skipped"}:
                raise WorkflowDispatchError(f"invalid handler outcome: {outcome.status}")
            append_node_event(run_dir, node_id=current, event_type=outcome.status, detail="engine handler returned")
            if outcome.status == "waiting" or current in terminal_nodes:
                return current
            successors = self.satisfied_successors(current, read_node_states(run_dir), facts())
            if len(successors) != 1:
                raise WorkflowDispatchError(f"expected one successor for {current}, got {successors}")
            target = successors[0]
            if target not in handlers:
                raise WorkflowDispatchError(f"no executable handler for {target}")
            if on_edge:
                on_edge(current, target)
            if (current, target) == ("experiment_plan", "experiments"):
                append_node_event(run_dir, node_id="execution_gate", event_type="skipped", detail="execution does not require approval")
            current = target
        raise WorkflowDispatchError(f"workflow exceeded {max_steps} transitions")

    def _status(self, states: dict[str, dict[str, Any]], node_id: str) -> str:
        return str(states.get(node_id, {}).get("status") or "pending")

    def _build_predicates(self) -> dict[tuple[str, str], Any]:
        def status_is(node_id: str, *statuses: str):
            def predicate(states: dict, facts: dict) -> bool:
                return self._status(states, node_id) in statuses
            return predicate

        return {
            ("research_planning", "literature_review"): status_is("research_planning", "completed"),
            ("literature_review", "literature_context"): status_is("literature_review", "completed"),
            ("literature_context", "review_gate"): status_is("literature_context", "completed"),
            ("review_gate", "ideation"): status_is("review_gate", "completed"),
            ("review_gate", "literature_review"): lambda states, facts: self._status(
                states, "review_gate"
            ) in {"waiting", "failed"} and bool(facts.get("review_revision_requested")),
            ("ideation", "experiment_plan"): status_is("ideation", "completed"),
            ("experiment_plan", "execution_gate"): lambda states, facts: self._status(
                states, "experiment_plan"
            ) == "completed" and bool(facts.get("execution_requires_approval")),
            ("experiment_plan", "experiments"): lambda states, facts: self._status(
                states, "experiment_plan"
            ) == "completed"
            and not bool(facts.get("execution_requires_approval"))
            and self._status(states, "execution_gate") != "waiting",
            ("execution_gate", "experiments"): status_is("execution_gate", "completed"),
            ("experiments", "analysis"): lambda states, facts: self._status(states, "experiments") == "completed" and not bool(facts.get("repair_required")),
            ("experiments", "experiment_plan"): lambda states, facts: self._status(
                states, "experiments"
            ) in {"failed", "cancelled"} or bool(facts.get("repair_required")),
            ("analysis", "paper_writing"): lambda states, facts: self._status(
                states, "analysis"
            ) == "completed" and not bool(facts.get("writing_blocked")),
            ("analysis", "finalization"): lambda states, facts: self._status(
                states, "analysis"
            ) == "completed" and bool(facts.get("writing_blocked")),
            ("paper_writing", "paper_review"): status_is("paper_writing", "completed"),
            ("paper_review", "paper_revision"): lambda states, facts: self._status(
                states, "paper_review"
            ) == "completed" and bool(facts.get("revision_required")),
            ("paper_review", "finalization"): lambda states, facts: self._status(
                states, "paper_review"
            ) == "completed" and not bool(facts.get("revision_required")),
            ("paper_revision", "paper_review"): lambda states, facts: self._status(
                states, "paper_revision"
            ) == "completed" and bool(facts.get("recheck_required")),
            ("paper_revision", "finalization"): lambda states, facts: self._status(
                states, "paper_revision"
            ) == "completed" and not bool(facts.get("recheck_required")),
            ("finalization", "completed"): status_is("finalization", "completed"),
        }

    def evaluate_edge(self, from_node: str, to_node: str, states: dict[str, dict[str, Any]], facts: dict[str, bool] | None = None) -> EdgeDecision:
        predicate = self._predicates.get((from_node, to_node))
        if predicate is None:
            raise ValueError(f"no condition registered for edge {from_node}->{to_node}")
        return EdgeDecision(
            from_node=from_node,
            to_node=to_node,
            condition=f"{from_node}->{to_node}",
            satisfied=bool(predicate(states or {}, facts or {})),
        )

    def satisfied_successors(self, from_node: str, states: dict[str, dict[str, Any]], facts: dict[str, bool] | None = None) -> list[str]:
        return [
            decision.to_node
            for (source, _target), _predicate in sorted(self._predicates.items())
            if source == from_node
            for decision in [self.evaluate_edge(source, _target, states, facts)]
            if decision.satisfied
        ]

    def graph_report(self, declared_edges: list[dict[str, Any]]) -> dict[str, Any]:
        declared = {(str(edge.get("from") or ""), str(edge.get("to") or "")) for edge in declared_edges}
        registered = set(self._predicates)
        unknown_edges = sorted(declared - registered)
        undeclared_predicates = sorted(registered - declared)
        # A declared edge is dead when its predicate can never be satisfied by
        # any status vocabulary the reducer emits; the per-edge satisfiability
        # is proven by the table-driven tests, this report only checks wiring.
        return {
            "declared_edges": len(declared),
            "registered_predicates": len(registered),
            "unknown_edges": [f"{from_node}->{to_node}" for from_node, to_node in unknown_edges],
            "undeclared_predicates": [f"{from_node}->{to_node}" for from_node, to_node in undeclared_predicates],
            "consistent": not unknown_edges and not undeclared_predicates,
        }
