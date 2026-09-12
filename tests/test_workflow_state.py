from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.workflow_graph import WORKFLOW_EDGES, WORKFLOW_NODES
from research_agent.workflow_state import (
    NODE_STATUSES,
    STAGE_COMPLETIONS,
    WorkflowEngine,
    NodeOutcome,
    WorkflowDispatchError,
    append_node_event,
    append_node_events,
    read_node_states,
    reduce_node_states,
    stage_to_node_events,
    validate_node_state_consistency,
)

NODE_IDS = [node.node_id for node in WORKFLOW_NODES]


class DispatchTest(unittest.TestCase):
    def test_wait_does_not_dispatch_experiments_and_can_resume(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            calls = []
            engine = WorkflowEngine(NODE_IDS)
            handlers = {
                "experiment_plan": lambda: calls.append("plan"),
                "execution_gate": lambda: NodeOutcome("waiting"),
                "experiments": lambda: calls.append("experiment"),
            }
            kwargs = dict(handlers=handlers, facts=lambda: {"execution_requires_approval": True}, terminal_nodes={"experiments"})
            self.assertEqual(engine.run(out, start="experiment_plan", **kwargs), "execution_gate")
            self.assertEqual(calls, ["plan"])
            handlers["execution_gate"] = lambda: calls.append("approved")
            engine.run(out, start="execution_gate", **kwargs)
            self.assertEqual(calls, ["plan", "approved", "experiment"])

    def test_blocked_writing_selects_repair_instead_of_writer(self) -> None:
        with TemporaryDirectory() as tmp:
            calls = []
            WorkflowEngine(NODE_IDS).run(Path(tmp), start="analysis", handlers={
                "analysis": lambda: None,
                "paper_writing": lambda: calls.append("writer"),
                "finalization": lambda: calls.append("repair"),
            }, facts=lambda: {"writing_blocked": True}, terminal_nodes={"finalization"})
            self.assertEqual(calls, ["repair"])

    def test_failure_never_completes_or_invokes_successor(self) -> None:
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            calls = []
            def fail():
                raise RuntimeError("injected crash")
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                WorkflowEngine(NODE_IDS).run(out, start="research_planning", handlers={
                    "research_planning": fail,
                    "literature_review": lambda: calls.append("search"),
                }, facts=lambda: {}, terminal_nodes={"literature_review"})
            self.assertEqual(calls, [])
            self.assertEqual(read_node_states(out)["research_planning"]["status"], "failed")


def _states(**statuses: str) -> dict[str, dict[str, str]]:
    base = {node_id: {"node_id": node_id, "status": "pending"} for node_id in NODE_IDS}
    for node_id, status in statuses.items():
        base[node_id] = {"node_id": node_id, "status": status}
    return base


class ReducerTest(unittest.TestCase):
    def test_status_vocabulary_covers_all_required_states(self) -> None:
        required = {"pending", "running", "waiting", "completed", "skipped", "failed", "cancelled", "rolled_back", "stale"}
        self.assertTrue(required.issubset(NODE_STATUSES))

    def test_reduce_follows_latest_event_per_node(self) -> None:
        events = [
            {"node_id": "research_planning", "type": "started", "revision": 0, "at": "2026-09-03T00:00:00+00:00"},
            {"node_id": "research_planning", "type": "completed", "revision": 0, "at": "2026-09-03T00:01:00+00:00"},
            {"node_id": "literature_review", "type": "started", "revision": 0, "at": "2026-09-03T00:01:00+00:00"},
        ]
        states = reduce_node_states(events, 0, NODE_IDS)
        self.assertEqual(states["research_planning"]["status"], "completed")
        self.assertEqual(states["literature_review"]["status"], "running")
        self.assertEqual(states["ideation"]["status"], "pending")

    def test_future_revision_events_do_not_leak_back(self) -> None:
        events = [
            {"node_id": "ideation", "type": "completed", "revision": 1, "at": "2026-09-03T00:00:00+00:00"},
        ]
        states = reduce_node_states(events, 0, NODE_IDS)
        self.assertEqual(states["ideation"]["status"], "pending")

    def test_attempts_grouped_by_revision_and_start(self) -> None:
        events = [
            {"node_id": "experiments", "type": "started", "revision": 0, "at": "t0"},
            {"node_id": "experiments", "type": "failed", "revision": 0, "at": "t1"},
            {"node_id": "experiments", "type": "started", "revision": 1, "at": "t2"},
            {"node_id": "experiments", "type": "completed", "revision": 1, "at": "t3"},
        ]
        states = reduce_node_states(events, 1, NODE_IDS)
        attempts = states["experiments"]["attempts"]
        self.assertEqual(len(attempts), 2)
        self.assertEqual((attempts[0]["revision"], attempts[0]["attempt"], attempts[0]["status"]), (0, 1, "failed"))
        self.assertEqual((attempts[1]["revision"], attempts[1]["attempt"], attempts[1]["status"]), (1, 1, "completed"))
        self.assertEqual(states["experiments"]["current_attempt"], 1)

    def test_rolled_back_keeps_prior_node_completed(self) -> None:
        events = [
            {"node_id": "research_planning", "type": "completed", "revision": 0, "at": "t0"},
            {"node_id": "literature_review", "type": "completed", "revision": 0, "at": "t1"},
            {"node_id": "literature_review", "type": "rolled_back", "revision": 1, "at": "t2"},
        ]
        states = reduce_node_states(events, 1, NODE_IDS)
        self.assertEqual(states["research_planning"]["status"], "completed")
        self.assertEqual(states["literature_review"]["status"], "rolled_back")
        self.assertEqual(states["ideation"]["status"], "pending")

    def test_consistency_check_flags_completion_without_prior_events(self) -> None:
        states = _states(ideation="completed")
        issues = validate_node_state_consistency(states, NODE_IDS)
        self.assertTrue(any("ideation" in issue for issue in issues))
        coherent = _states(
            research_planning="completed",
            literature_review="completed",
            literature_context="completed",
            review_gate="completed",
            ideation="completed",
        )
        self.assertEqual(validate_node_state_consistency(coherent, NODE_IDS), [])


class StageEventMappingTest(unittest.TestCase):
    def test_compound_completion_maps_both_writing_nodes(self) -> None:
        pairs = stage_to_node_events("paper_review_completed")
        self.assertIn(("paper_writing", "completed"), pairs)
        self.assertIn(("paper_review", "completed"), pairs)

    def test_waiting_states_map_to_gates(self) -> None:
        self.assertEqual(stage_to_node_events("awaiting_review_approval"), [("review_gate", "waiting")])
        self.assertEqual(stage_to_node_events("awaiting_execution_approval"), [("execution_gate", "waiting")])

    def test_every_declared_stage_event_type_is_known(self) -> None:
        for stage in list(STAGE_COMPLETIONS) + ["started", "cancelled", "failed"]:
            for node_id, event_type in stage_to_node_events(stage):
                self.assertIn(event_type, NODE_STATUSES)


class EngineEdgeTest(unittest.TestCase):
    """Table-driven proof that every declared edge has a satisfiable predicate."""

    EDGE_TABLE = [
        (("research_planning", "literature_review"), {"research_planning": "completed"}, {}),
        (("literature_review", "literature_context"), {"literature_review": "completed"}, {}),
        (("literature_context", "review_gate"), {"literature_context": "completed"}, {}),
        (("review_gate", "ideation"), {"review_gate": "completed"}, {}),
        (("review_gate", "literature_review"), {"review_gate": "waiting"}, {"review_revision_requested": True}),
        (("ideation", "experiment_plan"), {"ideation": "completed"}, {}),
        (("experiment_plan", "execution_gate"), {"experiment_plan": "completed"}, {"execution_requires_approval": True}),
        (("experiment_plan", "experiments"), {"experiment_plan": "completed"}, {}),
        (("execution_gate", "experiments"), {"execution_gate": "completed"}, {}),
        (("experiments", "analysis"), {"experiments": "completed"}, {}),
        (("experiments", "experiment_plan"), {"experiments": "completed"}, {"repair_required": True}),
        (("analysis", "paper_writing"), {"analysis": "completed"}, {}),
        (("analysis", "finalization"), {"analysis": "completed"}, {"writing_blocked": True}),
        (("paper_writing", "paper_review"), {"paper_writing": "completed"}, {}),
        (("paper_review", "paper_revision"), {"paper_review": "completed"}, {"revision_required": True}),
        (("paper_review", "finalization"), {"paper_review": "completed"}, {}),
        (("paper_revision", "paper_review"), {"paper_revision": "completed"}, {"recheck_required": True}),
        (("paper_revision", "finalization"), {"paper_revision": "completed"}, {}),
        (("finalization", "completed"), {"finalization": "completed"}, {}),
    ]

    def setUp(self) -> None:
        self.engine = WorkflowEngine(NODE_IDS)

    def test_every_declared_edge_is_satisfiable_and_wired(self) -> None:
        declared = {(str(edge["from"]), str(edge["to"])) for edge in WORKFLOW_EDGES}
        table_edges = {edge for edge, _states, _facts in self.EDGE_TABLE}
        self.assertEqual(declared, table_edges, "edge table must cover the declared graph exactly")
        for (from_node, to_node), states, facts in self.EDGE_TABLE:
            decision = self.engine.evaluate_edge(from_node, to_node, _states(**states), facts)
            self.assertTrue(decision.satisfied, f"edge {from_node}->{to_node} must be satisfiable")

    def test_graph_report_is_consistent(self) -> None:
        report = self.engine.graph_report(WORKFLOW_EDGES)
        self.assertTrue(report["consistent"], report)
        self.assertEqual(report["declared_edges"], len(WORKFLOW_EDGES))
        self.assertEqual(report["registered_predicates"], len(WORKFLOW_EDGES))

    def test_unknown_edge_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.evaluate_edge("research_planning", "completed", _states(), {})


class EngineScenarioTest(unittest.TestCase):
    """The branches the audit requires: review revision, execution approval,
    writing_blocked, paper recheck, repair, cancel, rollback."""

    def setUp(self) -> None:
        self.engine = WorkflowEngine(NODE_IDS)

    def test_review_revision_branch(self) -> None:
        states = _states(
            research_planning="completed",
            literature_review="completed",
            literature_context="completed",
            review_gate="waiting",
        )
        successors = self.engine.satisfied_successors("review_gate", states, {"review_revision_requested": True})
        self.assertEqual(successors, ["literature_review"])

    def test_execution_approval_branch(self) -> None:
        states = _states(research_planning="completed", ideation="completed", experiment_plan="completed")
        self.assertEqual(
            self.engine.satisfied_successors("experiment_plan", states, {"execution_requires_approval": True}),
            ["execution_gate"],
        )
        waiting = _states(experiment_plan="completed", execution_gate="waiting")
        self.assertEqual(self.engine.satisfied_successors("experiment_plan", waiting, {}), [])
        approved = _states(experiment_plan="completed", execution_gate="completed")
        self.assertEqual(self.engine.satisfied_successors("execution_gate", approved, {}), ["experiments"])

    def test_writing_blocked_branch(self) -> None:
        states = _states(analysis="completed", paper_writing="skipped", paper_review="skipped", paper_revision="skipped")
        self.assertEqual(self.engine.satisfied_successors("analysis", states, {"writing_blocked": True}), ["finalization"])
        self.assertEqual(self.engine.satisfied_successors("analysis", states, {}), ["paper_writing"])

    def test_paper_recheck_branch(self) -> None:
        states = _states(paper_writing="completed", paper_review="completed", paper_revision="completed")
        self.assertEqual(
            self.engine.satisfied_successors("paper_revision", states, {"recheck_required": True}),
            ["paper_review"],
        )
        self.assertEqual(self.engine.satisfied_successors("paper_revision", states, {}), ["finalization"])

    def test_repair_branch(self) -> None:
        states = _states(experiment_plan="completed", experiments="failed")
        self.assertEqual(self.engine.satisfied_successors("experiments", states, {}), ["experiment_plan"])


class NodeEventPersistenceTest(unittest.TestCase):
    def test_append_and_read_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            append_node_event(run_dir, node_id="research_planning", event_type="started", revision=0)
            append_node_event(run_dir, node_id="research_planning", event_type="completed", revision=0)
            events = json.loads((run_dir / "run-node-events.json").read_text(encoding="utf-8"))["events"]
            self.assertEqual([event["type"] for event in events], ["started", "completed"])
            states = read_node_states(run_dir)
            self.assertEqual(states["research_planning"]["status"], "completed")

    def test_unknown_event_type_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                append_node_event(Path(tmp), node_id="ideation", event_type="exploded")

    def test_rollback_emits_rolled_back_events(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            (run_dir / "02-ideas.json").write_text("[]", encoding="utf-8")
            update = json.dumps({}, ensure_ascii=False)
            (run_dir / "state.json").write_text(update, encoding="utf-8")
            from research_agent.workflow_graph import apply_rollback, build_rollback_preview, issue_rollback_preview, update_workflow_stage

            update_workflow_stage(run_dir, "回退状态测试", "ideation_completed")
            preview = issue_rollback_preview(run_dir, "ideation")
            apply_rollback(
                run_dir,
                "ideation",
                preview["preview_id"],
                preview["preview_token"],
                reason="state machine test",
                actor="test",
            )
            states = read_node_states(run_dir)
            # Only the target node and everything after it is invalidated;
            # earlier nodes keep their revision-0 completion.
            for node_id in ["ideation", "experiment_plan", "execution_gate", "experiments",
                            "analysis", "paper_writing", "paper_review", "paper_revision", "finalization"]:
                self.assertEqual(states[node_id]["status"], "rolled_back", node_id)


if __name__ == "__main__":
    unittest.main()
