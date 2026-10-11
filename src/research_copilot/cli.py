"""Research Copilot CLI（P1 仅有 CLI，无 Web）。"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .agents.diagnosis_agent import run_diagnosis
from .agents.experiment_planner import ExperimentPlanner
from .agents.hypothesis_agent import HypothesisManager
from .core.research_state import confirm_question, render_markdown, set_question_status
from .core.storage import ProjectStore
from .integrations.llm import LLMUnavailable, OpenAICompatibleLLM
from .integrations.material_importer import import_material
from .integrations.legacy_research import import_legacy_run


def _store(args: Any) -> ProjectStore:
    return ProjectStore(getattr(args, "data_dir", None))


def _maybe_llm(args: Any):
    if getattr(args, "no_llm", False):
        return None
    try:
        return OpenAICompatibleLLM()
    except LLMUnavailable as exc:
        print(f"[提示] {exc}")
        print("[提示] 本次运行将以离线统计模式执行（仅确定性观测与规则式发现）。")
        return None


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# ---------- project ----------
def cmd_project_create(args: Any) -> int:
    project = _store(args).create_project(args.name, args.desc or "", args.goal or [])
    print(f"已创建项目 {project.id}（{project.name}）")
    return 0


def cmd_project_list(args: Any) -> int:
    store = _store(args)
    for project in store.list_projects():
        print(f"{project.id}\t{project.name}\t目标: {'; '.join(project.goals) or '-'}")
    return 0


# ---------- material ----------
def cmd_material_import(args: Any) -> int:
    store = _store(args)
    directions = {}
    for item in args.direction or []:
        if "=" not in item:
            print(f"[错误] --direction 格式应为 metric=lower_is_better|higher_is_better: {item}", file=sys.stderr)
            return 2
        metric, direction = item.split("=", 1)
        directions[metric.strip()] = direction.strip()
    material = import_material(
        store,
        args.project,
        args.kind,
        args.path,
        summary=args.summary or "",
        meta={"metric_directions": directions} if directions else None,
    )
    print(f"已导入材料 {material.id}（{material.kind}）sha256={material.sha256[:12]}…")
    table = material.meta.get("table")
    if table:
        print(f"  {table['n_rows']} 行；数值列: {table['numeric_columns']}")
        print(f"  指标方向声明: {table['metric_directions'] or '无（将回退名称启发式并在输出中标注）'}")
    return 0


def cmd_material_list(args: Any) -> int:
    store = _store(args)
    for material in store.load_materials(args.project):
        print(f"{material.id}\t{material.kind}\t{material.summary[:60]}\t{material.path}")
    return 0


def cmd_legacy_import(args: Any) -> int:
    store = _store(args)
    materials = import_legacy_run(store, args.project, args.run_dir)
    for material in materials:
        print(f"已导入 {material.id}\t{material.summary}")
    return 0


# ---------- diagnose ----------
def cmd_diagnose(args: Any) -> int:
    store = _store(args)
    llm = _maybe_llm(args)
    report = run_diagnosis(store, args.project, llm=llm, material_ids=args.material)
    print(f"诊断完成（模式 {report['llm_mode']}）：观测 {report['n_observations']} 条，发现 {report['n_findings']} 条")
    for finding in report["findings"]:
        validation = finding.get("validation") or {}
        print(f"  {finding['id']} [{finding['claim_type']}] {finding['statement'][:100]}")
        for downgrade in validation.get("downgrades") or []:
            print(f"    ↳ 降级: {downgrade}")
    print(f"建议待研究问题 {report['n_questions_proposed']} 个（proposed，需人工确认）")
    if report.get("skipped_materials"):
        for item in report["skipped_materials"]:
            print(f"  [跳过] {item['material_id']}: {item['reason']}")
    for path in report.get("report_files") or []:
        print(f"  报告: {path}")
    return 0


# ---------- question ----------
def cmd_question_list(args: Any) -> int:
    state = _store(args).load_state(args.project)
    for question in state.open_questions:
        print(f"{question.id}\t[{question.status}]\t{question.statement[:100]}")
    return 0


def cmd_question_confirm(args: Any) -> int:
    store = _store(args)
    state = store.load_state(args.project)
    question = confirm_question(state, args.id, rationale=args.rationale or "", actor="human")
    store.save_state(args.project, state)
    store.log_event(args.project, "question_confirmed", target=question.id, actor="human")
    print(f"{question.id} 已确认为研究目标问题")
    return 0


def cmd_question_status(args: Any) -> int:
    store = _store(args)
    state = store.load_state(args.project)
    question = set_question_status(state, args.id, args.status, rationale=args.rationale or "")
    store.save_state(args.project, state)
    print(f"{question.id} → {question.status}")
    return 0


# ---------- hypothesis ----------
def cmd_hypothesize(args: Any) -> int:
    store = _store(args)
    llm = _maybe_llm(args)
    manager = HypothesisManager(store, args.project)
    result = manager.generate(llm=llm, question_ids=args.question)
    for item in result["generated"]:
        print(f"{item['id']}\t[{item['status']}]\t{item['statement'][:100]}")
        print(f"    证伪条件: {item['falsification_criteria'][:100] or '未定义'}")
        print(f"    竞争假设: {', '.join(item['competing_with']) or '-'}")
    if result.get("note"):
        print(f"[提示] {result['note']}")
    if result.get("llm_error"):
        print(f"[提示] LLM 失败已回退离线规则: {result['llm_error']}")
    return 0


def cmd_hypothesis_list(args: Any) -> int:
    for hypothesis in _store(args).load_hypotheses(args.project):
        print(f"{hypothesis.id}\t[{hypothesis.status}]\t{hypothesis.statement[:100]}")
        print(f"    证据: {', '.join(hypothesis.evidence_links) or '-'}\t竞争: {', '.join(hypothesis.competing_with) or '-'}")
    return 0


def cmd_hypothesis_status(args: Any) -> int:
    manager = HypothesisManager(_store(args), args.project)
    hypothesis = manager.set_status(args.id, args.status, rationale=args.rationale or "", evidence_links=args.evidence, actor="human")
    print(f"{hypothesis.id} → {hypothesis.status}")
    return 0


def cmd_hypothesis_add(args: Any) -> int:
    manager = HypothesisManager(_store(args), args.project)
    hypothesis = manager.add_manual(args.question, args.statement, args.falsification or "")
    print(f"已人工添加 {hypothesis.id}: {hypothesis.statement}")
    return 0


def cmd_evidence_record(args: Any) -> int:
    manager = HypothesisManager(_store(args), args.project)
    entry = manager.record_evidence(
        args.hypothesis,
        args.verdict,
        rationale=args.rationale,
        ref_id=args.ref or "",
        kind=args.kind,
        actor="human",
    )
    print(f"证据 {entry.id} 已记录（{args.verdict} → {args.hypothesis}）")
    return 0


# ---------- experiment ----------
def cmd_plan_experiment(args: Any) -> int:
    store = _store(args)
    llm = _maybe_llm(args)
    planner = ExperimentPlanner(store, args.project)
    result = planner.plan(llm=llm, question_ids=args.question)
    for item in result["created"]:
        print(f"{item['id']}\t[{item['status']}]\t优先级 {item['priority_score']}\t{item['research_question'][:80]}")
        for score in item["scores"]:
            print(f"    {score['name']}: {score['score']} — {score['rationale'][:80]}")
        if not item["form_check"]["form_complete"]:
            missing = [k for k, v in item["form_check"].items() if v is False and k != "form_complete"]
            print(f"    [需人工补齐] 缺少: {', '.join(missing)}")
    print(f"[说明] {result['scoring_note']}")
    if result.get("note"):
        print(f"[提示] {result['note']}")
    return 0


def cmd_experiment_list(args: Any) -> int:
    for candidate in _store(args).load_candidates(args.project):
        print(f"{candidate.id}\t[{candidate.status}]\t优先级 {candidate.priority_score}\t{candidate.research_question[:80]}")
    return 0


def cmd_experiment_approve(args: Any) -> int:
    planner = ExperimentPlanner(_store(args), args.project)
    candidate = planner.set_status(args.id, "approved", actor="human")
    print(f"{candidate.id} 已批准（P1 仅作标记，不执行实验）")
    return 0


# ---------- state / decision ----------
def cmd_state(args: Any) -> int:
    store = _store(args)
    project = store.load_project(args.project)
    state = store.load_state(args.project)
    print(render_markdown(state, project.name))
    return 0


def cmd_decision_record(args: Any) -> int:
    from .core.models import DecisionRecord

    store = _store(args)
    decision = store.append_decision(
        args.project,
        DecisionRecord(
            id="",
            action=args.action,
            rationale=args.rationale or "",
            evidence_refs=args.evidence or [],
            question_id=args.question or "",
            human_override=True,
            actor="human",
        ),
    )
    print(f"决策 {decision.id} 已记录：{decision.action}")
    return 0


def cmd_decision_list(args: Any) -> int:
    for decision in _store(args).load_decisions(args.project):
        print(f"{decision.id}\t{decision.action}\t{decision.rationale[:80]}")
    return 0


# ---------- evaluation ----------
def cmd_evaluate(args: Any) -> int:
    from .evaluation.runner import run_evaluation

    groups = [g.strip().upper() for g in (args.groups or "A,B,C1,C2").split(",") if g.strip()]
    task_ids = args.task_ids if args.task_ids else None
    from .evaluation.baselines import GroupBudget

    summary = run_evaluation(
        bench_root=args.bench_root,
        out_dir=args.out_dir,
        groups=groups,
        subset=args.subset,
        limit=args.limit,
        task_ids=task_ids,
        budget=GroupBudget(max_steps=args.max_steps),
        dry_run=args.dry_run,
    )
    print(f"评测完成 → {summary['task_ids'][:3]}…（n={len(summary['task_ids'])}, dry_run={summary['dry_run']}）")
    for group, agg in summary["group_summaries"].items():
        print(
            f"  {group}: 完成率 {agg['completion_rate']:.0%}, 官方accuracy {agg['official_accuracy_mean']}, "
            f"CI {agg['official_accuracy_ci95']}, 无依据比例(可评) {agg['unsupported_rate_mean_evaluable']}, "
            f"不可评任务 {agg['n_not_evaluable']}"
        )
    print("汇总: summary.json / summary.md（见 out_dir）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-copilot", description="科研诊断 / 假设 / 实验规划 Copilot")
    parser.add_argument("--data-dir", default=None, help="数据根目录（默认 ./data 或 $RESEARCH_COPILOT_DATA_DIR）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_project = sub.add_parser("project", help="项目管理")
    project_sub = p_project.add_subparsers(dest="subcommand", required=True)
    p_create = project_sub.add_parser("create")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--desc", default="")
    p_create.add_argument("--goal", action="append")
    p_create.set_defaults(func=cmd_project_create)
    p_list = project_sub.add_parser("list")
    p_list.set_defaults(func=cmd_project_list)

    p_material = sub.add_parser("material", help="材料导入")
    material_sub = p_material.add_subparsers(dest="subcommand", required=True)
    p_import = material_sub.add_parser("import")
    p_import.add_argument("--project", required=True)
    p_import.add_argument("--kind", required=True, choices=["results", "dataset", "code_repo", "paper_draft", "config", "review", "note"])
    p_import.add_argument("--path", required=True)
    p_import.add_argument("--summary", default="")
    p_import.add_argument("--direction", action="append", help="metric=lower_is_better|higher_is_better（可多次）")
    p_import.set_defaults(func=cmd_material_import)
    p_mlist = material_sub.add_parser("list")
    p_mlist.add_argument("--project", required=True)
    p_mlist.set_defaults(func=cmd_material_list)

    p_legacy = sub.add_parser("legacy", help="旧 research 仓库 run 导入（只读）")
    legacy_sub = p_legacy.add_subparsers(dest="subcommand", required=True)
    p_limport = legacy_sub.add_parser("import")
    p_limport.add_argument("--project", required=True)
    p_limport.add_argument("--run-dir", required=True)
    p_limport.set_defaults(func=cmd_legacy_import)

    p_diag = sub.add_parser("diagnose", help="科研诊断（无 LLM 时离线统计模式）")
    p_diag.add_argument("--project", required=True)
    p_diag.add_argument("--material", action="append", help="限定材料 ID（可多次）")
    p_diag.add_argument("--no-llm", action="store_true")
    p_diag.set_defaults(func=cmd_diagnose)

    p_question = sub.add_parser("question", help="待研究问题管理")
    question_sub = p_question.add_subparsers(dest="subcommand", required=True)
    p_qlist = question_sub.add_parser("list")
    p_qlist.add_argument("--project", required=True)
    p_qlist.set_defaults(func=cmd_question_list)
    p_qconfirm = question_sub.add_parser("confirm")
    p_qconfirm.add_argument("--project", required=True)
    p_qconfirm.add_argument("--id", required=True)
    p_qconfirm.add_argument("--rationale", default="")
    p_qconfirm.set_defaults(func=cmd_question_confirm)
    p_qstatus = question_sub.add_parser("status")
    p_qstatus.add_argument("--project", required=True)
    p_qstatus.add_argument("--id", required=True)
    p_qstatus.add_argument("--status", required=True, choices=["proposed", "confirmed", "resolved", "retired"])
    p_qstatus.add_argument("--rationale", default="")
    p_qstatus.set_defaults(func=cmd_question_status)

    p_hyp = sub.add_parser("hypothesis", help="竞争假设管理")
    hyp_sub = p_hyp.add_subparsers(dest="subcommand", required=True)
    p_gen = hyp_sub.add_parser("generate", aliases=["hypothesize"])
    p_gen.add_argument("--project", required=True)
    p_gen.add_argument("--question", action="append")
    p_gen.add_argument("--no-llm", action="store_true")
    p_gen.set_defaults(func=cmd_hypothesize)
    p_hlist = hyp_sub.add_parser("list")
    p_hlist.add_argument("--project", required=True)
    p_hlist.set_defaults(func=cmd_hypothesis_list)
    p_hstatus = hyp_sub.add_parser("status")
    p_hstatus.add_argument("--project", required=True)
    p_hstatus.add_argument("--id", required=True)
    p_hstatus.add_argument("--status", required=True, choices=["candidate", "active", "supported", "refuted", "uncertain", "retired"])
    p_hstatus.add_argument("--rationale", default="")
    p_hstatus.add_argument("--evidence", action="append")
    p_hstatus.set_defaults(func=cmd_hypothesis_status)
    p_hadd = hyp_sub.add_parser("add")
    p_hadd.add_argument("--project", required=True)
    p_hadd.add_argument("--question", required=True)
    p_hadd.add_argument("--statement", required=True)
    p_hadd.add_argument("--falsification", default="")
    p_hadd.set_defaults(func=cmd_hypothesis_add)
    p_ev = hyp_sub.add_parser("record-evidence")
    p_ev.add_argument("--project", required=True)
    p_ev.add_argument("--hypothesis", required=True)
    p_ev.add_argument("--verdict", required=True, choices=["supports", "contradicts", "inconclusive"])
    p_ev.add_argument("--rationale", required=True)
    p_ev.add_argument("--ref", default="")
    p_ev.add_argument("--kind", default="observation")
    p_ev.set_defaults(func=cmd_evidence_record)

    p_exp = sub.add_parser("experiment", help="主动实验规划（不执行）")
    exp_sub = p_exp.add_subparsers(dest="subcommand", required=True)
    p_plan = exp_sub.add_parser("plan", aliases=["plan-experiment"])
    p_plan.add_argument("--project", required=True)
    p_plan.add_argument("--question", action="append")
    p_plan.add_argument("--no-llm", action="store_true")
    p_plan.set_defaults(func=cmd_plan_experiment)
    p_elist = exp_sub.add_parser("list")
    p_elist.add_argument("--project", required=True)
    p_elist.set_defaults(func=cmd_experiment_list)
    p_eapprove = exp_sub.add_parser("approve")
    p_eapprove.add_argument("--project", required=True)
    p_eapprove.add_argument("--id", required=True)
    p_eapprove.set_defaults(func=cmd_experiment_approve)

    p_state = sub.add_parser("state", help="研究状态报告")
    p_state.add_argument("--project", required=True)
    p_state.set_defaults(func=cmd_state)

    p_decision = sub.add_parser("decision", help="科研决策记录")
    decision_sub = p_decision.add_subparsers(dest="subcommand", required=True)
    p_drecord = decision_sub.add_parser("record")
    p_drecord.add_argument("--project", required=True)
    p_drecord.add_argument("--action", required=True, choices=["continue", "refine", "investigate", "replicate", "pivot", "stop", "report"])
    p_drecord.add_argument("--rationale", default="")
    p_drecord.add_argument("--evidence", action="append")
    p_drecord.add_argument("--question", default="")
    p_drecord.set_defaults(func=cmd_decision_record)
    p_dlist = decision_sub.add_parser("list")
    p_dlist.add_argument("--project", required=True)
    p_dlist.set_defaults(func=cmd_decision_list)

    p_eval = sub.add_parser("evaluate", help="DiscoveryBench A/B/C 对照评测")
    p_eval.add_argument("--bench-root", required=True, help="DiscoveryBench 数据根目录（fetch.sh 克隆产物）")
    p_eval.add_argument("--out-dir", default="eval-runs")
    p_eval.add_argument("--groups", default="A,B,C1,C2")
    p_eval.add_argument("--subset", default="main", choices=["main", "synthetic"])
    p_eval.add_argument("--limit", type=int, default=20)
    p_eval.add_argument("--task-ids", action="append", help="显式任务 ID（可多次，覆盖 --limit 选择）")
    p_eval.add_argument("--max-steps", type=int, default=6)
    p_eval.add_argument("--dry-run", action="store_true", help="stub LLM 管道冒烟（不构成评测结论）")
    p_eval.set_defaults(func=cmd_evaluate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
