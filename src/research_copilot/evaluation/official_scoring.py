"""DiscoveryBench 官方评分协议实现。

官方实现在 eval/new_eval.py（依赖 openai/numpy/pandas/IPython，无法直接 import）。
本模块**逐字镜像**其三个维度的 judge prompt、温度/长度参数与解析规则，按其
单子假设路径计算：accuracy = context(0/1) × var_F1 × rel(1.0/0.5/0.0)。
官方多子假设切分路径（recall_context × mean(...)）暂未实现，报告中如实标注。

溯源：OFFICIAL_EVAL_SHA256 为被镜像的官方文件哈希；judge 使用与被测无关的
LLM，temperature=0（与官方一致）。
"""
from __future__ import annotations

import json
import re
from typing import Any

OFFICIAL_EVAL_SHA256 = "83406ddbe6894429cc5012b17cb82a209d5397aa7863b0aba1bb51edf1dd6c65"
OFFICIAL_EVAL_SOURCE = "eval/new_eval.py @ allenai/discoverybench"

JUDGE_SYSTEM = (
    "You are an AI assistant that helps evaluate a data-driven hypothesis. "
    "You are a helpful assistant who is not talkative. "
    "You only respond with the exact answer to a query without additional conversation."
)

# ---- 官方 prompt 逐字镜像（new_eval.py: ask_dimension_question）----
_DIMENSION_QUESTIONS = {
    "context": """\
        Question: Is HypoB defined in the same context as HypoA?
        (Context refers to assumptions/stratification under which the hypotheses are defined.)
        Options: A) same   B) different
        What is your answer?""",
    "var": """\
        Question: For both HypoA and HypoB, what are the different variables found in the hypotheses? \
        Return your answer as a JSON object in the following format:
        ```json
        {{
        "sizeA": num of variables used in HypoA
        "sizeB": num of variables used in HypoB
        "intersection": num of variables common in HypoA and HypoB. Use *fuzzy matching* to determine intersection, accounting for paraphrases or slightly different surface forms
        "explanation": a short text explanation about the variables
        }}```
        Answer:""",
    "rel": """\
        Question: Does HypoB exhibit the same relation as HypoA?
        Compare using following example hierarchy of relationships (based on specificity): \
        "there exists a relationship" > "positive relationship" > "positive AND (linear OR quadratic)" > "positive AND linear".
        Options: A) very similar B) similar but general than HypoA C) different
        Return your answer as a JSON object in the following format:
        ```json
        {{
        "answer": one of the options from A) very similar B) similar but general than HypoA C) different
        "explanation": a short text explanation about the relationship comparison
        }}```
        Answer:""",
}

# ---- 官方解析规则（new_eval.py: get_score_from_answer）逐字语义 ----
def parse_context_answer(answer: str) -> float:
    answer = str(answer).replace("Answer:", "").strip()
    if answer.startswith("A)"):
        return 1.0
    if answer.startswith("B)"):
        return 0.0
    return -1.0


def parse_var_answer(answer: str) -> dict[str, Any]:
    try:
        var_json = json.loads(answer)
        p = r = f1 = 0.0
        if var_json.get("sizeB"):
            p = var_json["intersection"] / var_json["sizeB"]
        if var_json.get("sizeA"):
            r = var_json["intersection"] / var_json["sizeA"]
        if p > 0.0 and r > 0.0:
            f1 = (2 * p * r) / (p + r)
        return {"p": p, "r": r, "f1": f1, "sizeA": var_json.get("sizeA"), "sizeB": var_json.get("sizeB"),
                "intersection": var_json.get("intersection"), "explanation": var_json.get("explanation", "")}
    except Exception:
        return {"p": -1.0, "r": -1.0, "f1": -1.0}


def parse_rel_answer(answer: str) -> float:
    try:
        rel_json = json.loads(answer)
        answer_str = str(rel_json.get("answer", "")).strip()
    except Exception:
        return -1.0
    if answer_str.startswith("A") or "very similar" in answer_str:
        return 1.0
    if answer_str.startswith("B") or "similar but general than HypoA" in answer_str:
        return 0.5
    if answer_str.startswith("C") or "different" in answer_str:
        return 0.0
    return -1.0


def _extract_json_block(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return fenced.group(1) if fenced else text


def build_judge_prompt(
    query: str,
    gold_hypo: str,
    gen_hypo: str,
    dataset_meta: dict[str, Any],
    dimension: str,
) -> str:
    """官方 dimension_question_str 结构（new_eval.py:143-166），datasets 描述可传入。"""
    dimension_question = _DIMENSION_QUESTIONS[dimension]
    datasets_json = json.dumps(dataset_meta.get("datasets") or [], ensure_ascii=False, default=str)
    return f"""\
        You are going to compare two natural-language hypotheses HypoA and HypoB accompanied with optional workflows: WorkflowA for HypoA and WorkflowB for HypoB. \
        Both the hypotheses answer the natural language query "QUERY" over the dataset(s) described by dataset description(s) and column description(s) below. \
        Compare HypoA and HypoB in terms of three aspects: Contexts, Variables, and Relations. \
        E.g., for the hypothesis "From 1995 to 2009, the number of sandhill cranes around the tundra (Indigilka River) surged by an astounding ~10X":
        * Contexts refer to stratification of the data under which the given hypothesis is True. E.g., "For all women", "From 1995 to 2009".
        * Variables refer to the set of variables (either dependent or independent) that are mentioned in the hypothesis. E.g., number of sandhill cranes, location.
        * Relations refer to the form of relation between the variables. E.g., "surged by ~10x".

        Answer following questions for a given pair of hypotheses, HypoA and HypoB, along with an explanation grounded on the QUERY and the DATASET(S).

        Here is the metadata for the task:
        ```json
        {{
        "datasets": {datasets_json},
        "query": {query},
        "HypoA": {gold_hypo},
        "WorkflowA": {dataset_meta.get("gold_workflow") or "N/A"},
        "HypoB": {gen_hypo},
        "WorkflowB": {dataset_meta.get("gen_workflow") or "N/A"}
        }}
        ```

        {dimension_question}"""


class OfficialProtocolScorer:
    """官方单子假设路径评分器：accuracy = context × var_F1 × rel；另含金标-数据分歧诊断。"""

    def __init__(self, judge_llm: Any, gold_workflow: str = "", gen_workflow: str = "") -> None:
        self.judge = judge_llm
        self.gold_workflow = gold_workflow
        self.gen_workflow = gen_workflow
        self.judge_calls = 0

    def _ask(self, dimension: str, prompt: str, max_tokens: int, json_response: bool) -> str:
        self.judge_calls += 1
        _ = json_response, max_tokens  # 参数与官方一致；json 由 prompt 约定
        return self.judge.complete(JUDGE_SYSTEM, prompt, purpose=f"official_judge_{dimension}", temperature=0.0)

    def score(
        self,
        query: str,
        gold_hypo: str,
        gen_hypo: str,
        dataset_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        dataset_meta = dict(dataset_meta or {})
        if self.gold_workflow:
            dataset_meta.setdefault("gold_workflow", self.gold_workflow)
        if self.gen_workflow:
            dataset_meta.setdefault("gen_workflow", self.gen_workflow)
        result: dict[str, Any] = {
            "scorer": "official-protocol/single-subhypothesis",
            "official_eval_sha256": OFFICIAL_EVAL_SHA256,
            "official_eval_source": OFFICIAL_EVAL_SOURCE,
            "note": (
                "镜像官方 prompt 与解析（new_eval.py get_score_from_answer）；"
                "未实现多子假设切分路径（recall_context），按单子假设 accuracy=context×var_F1×rel 计。"
            ),
        }
        parse_errors = []
        context_answer = self._ask("context", build_judge_prompt(query, gold_hypo, gen_hypo, dataset_meta, "context"), 256, False)
        context = parse_context_answer(context_answer)
        var_answer = self._ask("var", build_judge_prompt(query, gold_hypo, gen_hypo, dataset_meta, "var"), 512, True)
        var = parse_var_answer(_extract_json_block(var_answer))
        rel_answer = self._ask("rel", build_judge_prompt(query, gold_hypo, gen_hypo, dataset_meta, "rel"), 512, True)
        rel = parse_rel_answer(_extract_json_block(rel_answer))
        for name, value in (("context", context), ("var_f1", var.get("f1")), ("rel", rel)):
            if value is None or not 0 <= value <= 1:
                parse_errors.append(name)
        result["context"] = {"answer": str(context_answer)[:500], "score": context}
        result["var"] = {"answer": str(var_answer)[:500], "score": var}
        result["rel"] = {"answer": str(rel_answer)[:500], "score": rel}
        if parse_errors:
            result["accuracy"] = None
            result["parse_errors"] = parse_errors
        else:
            result["accuracy"] = context * float(var["f1"]) * rel
        return result

    def divergence_check(self, query: str, gold_hypo: str, relations_summary: str) -> dict[str, Any]:
        """金标-数据分歧诊断（修复 2026-10 评测发现：任务 3 金标与数据实测相反）。

        只做诊断、**不参与评分**：当金标假设与数据导出的相关方向矛盾时，
        该任务的官方分数应被解读为"金标与数据分歧"，而非"被测模型错误"。
        relations_summary：来自确定性 relation_signs 的 JSON 文本。
        """
        prompt = (
            "You are given a GOLD hypothesis and data-derived pairwise correlation directions "
            "(Pearson r with sign) computed directly from the task dataset. "
            "Determine whether the GOLD hypothesis CONTRADICTS the data-derived relations "
            "(e.g., gold claims no association or the opposite sign for a relation the data shows clearly).\n\n"
            f"QUERY: {query}\n\nGOLD HYPOTHESIS: {gold_hypo}\n\n"
            f"DATA-DERIVED RELATIONS (top by |r|):\n{relations_summary}\n\n"
            'Output JSON only: {"divergence": true|false, "reason": "one sentence"}'
        )
        self.judge_calls += 1
        response = self.judge.complete(JUDGE_SYSTEM, prompt, purpose="divergence_check", temperature=0.0)
        match = re.search(r"\{.*\}", response, re.DOTALL)
        try:
            parsed = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            parsed = {}
        divergence = parsed.get("divergence")
        return {
            "divergence": bool(divergence) if divergence is not None else None,
            "reason": str(parsed.get("reason") or "")[:300],
            "raw": response[:200],
            "diagnostic_only": "不参与评分；仅标注该任务的金标-数据可信度",
        }
