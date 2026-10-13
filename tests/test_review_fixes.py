"""2026-10-13 真实审查反例：升级门禁、负区间、解析、持久工作区、证据计数。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from research_copilot.analysis.evidence_validator import validate_finding
from research_copilot.core.evidence import sha256_file
from research_copilot.core.models import EvidenceRef, Finding, Material, NumericAssertion, Observation, RelationClaim
from research_copilot.evaluation.baselines import GroupBudget, _parse_answer, _react_loop, classify_failure, trace_diagnostics
from research_copilot.evaluation.metrics import aggregate_group, check_numeric_assertions, paired_delta
from research_copilot.evaluation.runner import render_summary_markdown
from research_copilot.evaluation.sandbox import ToolSandbox, _run_process
from research_copilot.integrations.llm import StubLLM


@pytest.fixture
def evidence(tmp_path):
    data = tmp_path / "data.csv"
    data.write_text("x\n8\n")
    material = Material("M", "results", str(data), sha256_file(data), "t")
    obs = Observation("O", "均值为8", {"mean": 8.0, "n": 100}, [EvidenceRef("M", material.sha256)])
    def validate(statement, assertions=None, **kw):
        finding = Finding(id="F", statement=statement, claim_type="statistical_finding", observation_ids=["O"], numeric_assertions=assertions or [], **kw)
        return validate_finding(finding, {"O": obs}, {"M": material})
    return obs, material, validate


def test_lookup_cannot_match_sample_count_as_mean(evidence):
    _, _, validate = evidence
    bad = NumericAssertion("mean", 100, check="lookup")
    assert validate("均值为100", [bad])["final_claim_type"] == "unverified_conjecture"
    bad.value_path = "n"
    assert validate("均值为100", [bad])["status"] != "verified"
    good = NumericAssertion("mean", 8, check="lookup", value_path="mean")
    assert validate("均值为8", [good])["status"] == "verified"


def test_missing_inputs_never_upgrade(evidence):
    _, _, validate = evidence
    result = validate("改善百分比待核对", [NumericAssertion("time", 999, check="percent_change_from_baseline")])
    assert result["l2"]["checks"][0]["status"] == "unverifiable"
    assert result["status"] == "needs_human_review"
    assert validate("改善999%", [NumericAssertion("time", 999, check="percent_change_from_baseline")])["status"] != "verified"


def test_unstructured_significance_never_upgrade(evidence):
    _, _, validate = evidence
    assert validate("候选显著优于基线")["status"] == "needs_human_review"
    assert validate("完全不相关")["status"] == "needs_human_review"
    assert validate("均值为8")["status"] == "verified"  # 精确照录确定性观测。


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_assertions_rejected(evidence, bad):
    _, _, validate = evidence
    assert validate("均值待核对", [NumericAssertion("mean", bad, check="mean")])["status"] != "verified"
    assert check_numeric_assertions({"numeric_assertions": [{"metric": "x", "value": bad, "check": "mean"}]}, [{"x": 8}])[0]["status"] == "fail"


def test_invalid_relation_basis_not_substituted(evidence):
    obs, _, validate = evidence
    obs.value["relations"] = [{"a": "x", "b": "y", "sign": "positive"}]
    claims = [RelationClaim("x", "y", "positive", "missing")]
    assert validate("x与y正相关", claims=claims)["status"] == "needs_human_review"
    claims[0].basis_observation = "O"
    assert validate("x与y正相关", claims=claims)["status"] == "verified"


def test_causal_metadata_without_intervention_does_not_pass(evidence):
    obs, material, validate = evidence
    material.meta["experiment_kind"] = "controlled"
    obs.value["relations"] = [{"a": "x", "b": "y", "sign": "positive"}]
    claims = [RelationClaim("x", "y", "positive", "O")]
    assert validate("x导致y变化", claims=claims)["final_claim_type"] == "hypothesis"


def _record(task, score):
    return {"task_id": task, "answer": {"hypothesis": "h"} if score is not None else {},
            "official": {"accuracy": score}, "unsupported": {"evaluable": False}}


def test_negative_paired_ci_and_full_denominator():
    a = [_record("test/d1/m1", 1), _record("test/d2/m1", None)]
    c = [_record("test/d1/m1", 0), _record("test/d2/m1", None)]
    diff = paired_delta(c, a)
    assert diff["delta_mean"] == -0.5
    assert diff["delta_ci95"] == (-1.0, 0.0)
    assert aggregate_group(a)["full_task_score_ci95"] == (0.0, 1.0)


def test_judge_missing_is_not_a_model_failure():
    records = [_record("test/d1/m1", 1), _record("test/d2/m1", None)]
    records[1]["answer"] = {"hypothesis": "h"}
    agg = aggregate_group(records)
    assert agg["completion_rate"] == 1
    assert agg["n_score_missing"] == 1
    assert agg["full_task_score_mean"] is None
    assert paired_delta(records, records)["delta_mean"] is None


def test_report_displays_the_full_task_interval():
    records = [_record("test/d1/m1", 1), _record("test/d2/m1", None)]
    agg = aggregate_group(records)
    agg["official_accuracy_ci95"] = (-9, 9)
    summary = {"model": "stub", "judge_model": "stub", "dry_run": True, "subset": "main",
               "task_ids": [r["task_id"] for r in records], "groups": ["A"], "honesty_note": "test", "group_summaries": {"A": agg}}
    text = render_summary_markdown(summary)
    assert "[0.0, 1.0]" in text and "[-9, 9]" not in text


def test_multitable_assertions_require_a_table():
    rows = [{"__dataset_file": "a.csv", "x": 8}, {"__dataset_file": "b.csv", "x": 100}]
    answer = {"numeric_assertions": [{"metric": "x", "value": 8, "check": "mean"}]}
    assert check_numeric_assertions(answer, rows)[0]["status"] == "unverifiable"
    answer["numeric_assertions"][0]["table"] = "a.csv"
    assert check_numeric_assertions(answer, rows)[0]["status"] == "pass"


def test_nested_tables_with_same_basename_have_distinct_sources(tmp_path):
    from research_copilot.evaluation.discoverybench_adapter import DiscoveryTask, load_task_tables
    for directory, value in (("a", 8), ("b", 100)):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "data.csv").write_text(f"x\n{value}\n")
    task = DiscoveryTask(task_id="t", query="q", gold_hypothesis="g", dataset_dir=str(tmp_path))
    tables = load_task_tables(task)
    assert [t["file"] for t in tables] == ["a/data.csv", "b/data.csv"]
    rows = [r for table in tables for r in table["rows"]]
    answer = {"numeric_assertions": [{"metric": "x", "value": 8, "check": "mean", "table": "a/data.csv"}]}
    assert check_numeric_assertions(answer, rows)[0]["status"] == "pass"


def test_parser_handles_wrappers_and_refuses_multiple_actions():
    action = {"tool": "python", "code": "print({'x': '}'})"}
    encoded = json.dumps(action)
    assert _parse_answer("```json\n" + encoded + "\n```") == action
    assert _parse_answer(encoded + '\n{"tool":"diagnose"}') == {}
    assert _parse_answer('{"bad": {"hypothesis":"nested"},') == {}


def test_dsml_parameter_is_scoped_to_one_invocation():
    raw = '<｜DSML｜invoke name="python"><｜DSML｜parameter name="code" string="true">print(1)</｜DSML｜parameter></｜DSML｜invoke>'
    assert _parse_answer(raw) == {"tool": "python", "code": "print(1)"}
    assert _parse_answer(raw + raw) == {}


class FakeSandbox:
    def run_python(self, code):
        return {"ok": False, "stdout": "", "stderr": "fixture error"}


def test_react_records_responses_and_feedback_and_failure_causes():
    action = json.dumps({"tool": "python", "code": "print(1)"})
    llm = StubLLM(responses={"react_a_step_0": action + action, "react_a_step_1": action})
    answer, raw, calls, tools, trace = _react_loop(llm, "context", FakeSandbox(), GroupBudget(max_steps=2), "A", "task", "react_a")
    responses = [t for t in trace if t["kind"] == "model_response"]
    assert responses[0]["raw"] == action + action
    assert "协议错误" in responses[1]["request"]
    assert trace_diagnostics(trace)["parse_failures"] == 1
    assert trace_diagnostics(trace)["tool_execution_failures"] == 1
    assert classify_failure("", answer, trace, calls, 2) == "tool_execution_failure"


def test_react_transport_failure_retains_partial_trace():
    class BrokenLLM:
        def complete(self, *args, **kw):
            raise ConnectionError("fixture disconnected")
    answer, _, calls, _, trace = _react_loop(BrokenLLM(), "context", FakeSandbox(), GroupBudget(), "A", "t", "react_a")
    assert calls == 1 and trace[0]["kind"] == "llm_error"
    assert classify_failure("", answer, trace, calls, 6) == "transport_failure"


def test_task_workdir_persists_and_is_deleted_on_close(tmp_path, monkeypatch):
    import research_copilot.evaluation.sandbox as sb
    monkeypatch.setattr(sb, "check_bwrap_available", lambda: False)
    (tmp_path / "data.csv").write_text("x\n8\n")
    with ToolSandbox(tmp_path, allow_unsafe_fallback=True, network_isolation=False) as sandbox:
        # 显式开发降级仅执行固定测试代码；不把该结果当作隔离集成测试。
        first = sandbox.run_python("from pathlib import Path\nPath('output.txt').write_text('persisted')\nprint(Path.cwd())")
        assert first["ok"], first
        cwd = Path(first["stdout"].strip())
        second = sandbox.run_python("print(open('output.txt').read())\nprint(open('data.csv').read())")
        assert second["ok"] and "persisted" in second["stdout"]
        assert sandbox.isolation_record["data_readonly"] is False
    assert not cwd.exists()
    assert sandbox.snapshot_manifest


def test_timeout_is_bounded_with_background_child():
    result = _run_process([sys.executable, "-c", "import subprocess,time; subprocess.Popen(['sleep','30']); time.sleep(30)"], 0.15)
    assert result["timed_out"] and result["ok"] is False


def test_test_evidence_excludes_skipped_from_passed(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("test_evidence_writer", root / "scripts/write_test_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    junit = tmp_path / "results.xml"
    junit.write_text('<testsuites><testsuite><testcase name="pass"/><testcase name="skip"><skipped message="no runtime"/></testcase><testcase name="fail"><failure/></testcase></testsuite></testsuites>')
    evidence = module.build_evidence(junit, root)
    assert evidence["totals"] == {"tests": 3, "passed": 1, "failed": 1, "errors": 0, "skipped": 1}
    assert len(evidence["source_sha256"]) == 64


def test_sandbox_nested_data_readonly_and_session_persistence(tmp_path, require_sandbox):
    (tmp_path / "nested").mkdir()
    data = tmp_path / "nested/data.csv"
    data.write_text("x\n8\n")
    with ToolSandbox(tmp_path, timeout_s=5) as sandbox:
        result = sandbox.run_python("open('out.txt','w').write('persistent'); print(open('nested/data.csv').read())")
        assert result["ok"] and "8" in result["stdout"]
        assert sandbox.run_python("print(open('out.txt').read())")["stdout"].strip() == "persistent"
        assert sandbox.run_python("open('nested/data.csv','w').write('changed')")["ok"] is False
    assert data.read_text() == "x\n8\n"
