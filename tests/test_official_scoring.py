"""官方 DiscoveryBench 评分协议测试：解析语义与官方 new_eval.py 逐字一致。"""
from __future__ import annotations

import json

from research_copilot.evaluation.official_scoring import (
    OFFICIAL_EVAL_SHA256,
    OfficialProtocolScorer,
    build_judge_prompt,
    parse_context_answer,
    parse_rel_answer,
    parse_var_answer,
)
from research_copilot.integrations.llm import StubLLM


def test_parse_context_matches_official_semantics():
    assert parse_context_answer("A) same") == 1.0
    assert parse_context_answer("B) different") == 0.0
    assert parse_context_answer("Answer: A) same") == 1.0
    assert parse_context_answer("无法解析") == -1.0


def test_parse_var_f1_matches_official_formula():
    # 官方公式：p = intersection/sizeB, r = intersection/sizeA, f1 = 2pr/(p+r)
    result = parse_var_answer(json.dumps({"sizeA": 4, "sizeB": 2, "intersection": 2, "explanation": "x"}))
    assert abs(result["p"] - 1.0) < 1e-9
    assert abs(result["r"] - 0.5) < 1e-9
    assert abs(result["f1"] - 2 / 3) < 1e-9
    broken = parse_var_answer("不是 JSON")
    assert broken["f1"] == -1.0  # 官方语义：解析失败记 -1


def test_parse_rel_matches_official_hierarchy():
    assert parse_rel_answer(json.dumps({"answer": "A) very similar"})) == 1.0
    assert parse_rel_answer(json.dumps({"answer": "B) similar but general than HypoA"})) == 0.5
    assert parse_rel_answer(json.dumps({"answer": "C) different"})) == 0.0
    # 官方容错：答案文本中的关键词也参与判定
    assert parse_rel_answer(json.dumps({"answer": "It is very similar overall"})) == 1.0
    assert parse_rel_answer("垃圾输出") == -1.0


def test_prompts_are_verbatim_mirrors():
    prompt = build_judge_prompt("q?", "gold", "gen", {"datasets": []}, "rel")
    # 官方 prompt 的关键句必须原样出现
    assert "Does HypoB exhibit the same relation as HypoA?" in prompt
    assert "A) very similar B) similar but general than HypoA C) different" in prompt
    ctx_prompt = build_judge_prompt("q?", "gold", "gen", {}, "context")
    assert "Is HypoB defined in the same context as HypoA?" in ctx_prompt
    var_prompt = build_judge_prompt("q?", "gold", "gen", {}, "var")
    assert "Use *fuzzy matching* to determine intersection" in var_prompt


def test_scorer_accuracy_is_product_and_records_provenance():
    judge = StubLLM(
        responses={
            "official_judge_context": "A) same",
            "official_judge_var": json.dumps({"sizeA": 2, "sizeB": 2, "intersection": 1, "explanation": "部分"}),
            "official_judge_rel": json.dumps({"answer": "B) similar but general than HypoA", "explanation": "较泛"}),
        }
    )
    scorer = OfficialProtocolScorer(judge)
    result = scorer.score("q?", "gold hypo", "gen hypo", {"datasets": [{"name": "data.csv"}]})
    # accuracy = context(1) × var_F1(0.5) × rel(0.5) = 0.25
    assert abs(result["accuracy"] - 0.25) < 1e-9
    assert result["official_eval_sha256"] == OFFICIAL_EVAL_SHA256
    assert scorer.judge_calls == 3


def test_scorer_parse_failure_records_not_scores():
    judge = StubLLM(default="完全无法解析的输出")
    scorer = OfficialProtocolScorer(judge)
    result = scorer.score("q?", "gold", "gen")
    assert result["accuracy"] is None
    assert set(result["parse_errors"]) == {"context", "var_f1", "rel"}


def test_scorer_uses_temperature_zero():
    class TempRecorder(StubLLM):
        def __init__(self):
            super().__init__()
            self.temperatures = []

        def complete(self, system, user, purpose="", temperature=None):
            self.temperatures.append(temperature)
            return super().complete(system, user, purpose)

    judge = TempRecorder()
    judge.responses.update(
        {
            "official_judge_context": "A) same",
            "official_judge_var": json.dumps({"sizeA": 1, "sizeB": 1, "intersection": 1, "explanation": "x"}),
            "official_judge_rel": json.dumps({"answer": "A) very similar", "explanation": "x"}),
        }
    )
    OfficialProtocolScorer(judge).score("q?", "g", "p")
    assert judge.temperatures == [0.0, 0.0, 0.0]  # 官方协议要求 temperature=0
