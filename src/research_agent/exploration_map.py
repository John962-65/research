from __future__ import annotations

from pathlib import Path
import html

from .artifacts import write_json, write_text, cell as _cell
from .idea_audit import idea_audit_item_for_title, idea_audit_penalty
from .models import ExplorationBranch, ExplorationMap, ResearchIdea
from .novelty_audit import duplicate_penalty, novelty_item_for_title


EXPLORATION_MAP_JSON = "02-exploration-map.json"
EXPLORATION_MAP_MD = "02-exploration-map.md"
EXPLORATION_MAP_SVG = "02-exploration-map.svg"


def write_exploration_map_artifacts(
    topic: str,
    ideas: list[ResearchIdea],
    run_dir: Path,
    novelty_audit: dict | None = None,
    idea_audit: dict | None = None,
) -> ExplorationMap:
    report = build_exploration_map(topic, ideas, novelty_audit, idea_audit)
    write_json(run_dir / EXPLORATION_MAP_JSON, report)
    write_text(run_dir / EXPLORATION_MAP_MD, render_exploration_map_markdown(report))
    write_text(run_dir / EXPLORATION_MAP_SVG, render_exploration_map_svg(report))
    return report


def build_exploration_map(topic: str, ideas: list[ResearchIdea], novelty_audit: dict | None = None, idea_audit: dict | None = None) -> ExplorationMap:
    branches = [_branch(index, idea, novelty_audit, idea_audit) for index, idea in enumerate(ideas, start=1)]
    ranked = sorted(branches, key=lambda item: item.score, reverse=True)
    selected_id = ranked[0].branch_id if ranked else ""
    branches = [
        _replace_branch_status(branch, "selected" if branch.branch_id == selected_id else "pruned")
        for branch in branches
    ]
    selected = next((branch for branch in branches if branch.branch_id == selected_id), None)
    warnings: list[str] = []
    if not ideas:
        warnings.append("没有可用 idea，无法生成探索图。")
    if selected and selected.evidence_count == 0:
        warnings.append("选中分支缺少显式文献证据，实验前需要人工补证。")
    if selected and selected.risk >= 4:
        warnings.append("选中分支风险较高，建议先做低成本 smoke benchmark。")
    if selected and "novelty=likely_duplicate" in selected.rationale:
        warnings.append("选中分支存在高重复风险，建议人工复核 novelty 后再进入实验。")
    if selected and "idea_audit=block" in selected.rationale:
        warnings.append("选中分支包含不可核对证据，建议修正 citation/chunk 后再进入实验。")
    if selected and "idea_audit=review" in selected.rationale:
        warnings.append("选中分支需要补齐证据、baseline、实验草案或人工约束响应。")
    decision = (
        f"选择 {selected.branch_id}：{selected.title}，因为综合分最高（{selected.score:.2f}）。"
        if selected
        else "没有可选分支。"
    )
    return ExplorationMap(
        topic=topic,
        selected_branch_id=selected_id,
        selected_idea_title=selected.title if selected else "",
        branches=branches,
        decision=decision,
        warnings=warnings,
    )


def selected_idea(report: ExplorationMap, ideas: list[ResearchIdea]) -> ResearchIdea:
    if not ideas:
        raise RuntimeError("No research ideas available for experiment planning")
    for branch, idea in zip(report.branches, ideas):
        if branch.branch_id == report.selected_branch_id:
            return idea
    return ideas[0]


def render_exploration_map_markdown(report: ExplorationMap) -> str:
    lines = [
        f"# 研究分支探索图：{report.topic}",
        "",
        f"- 选中分支：{report.selected_branch_id or '无'}",
        f"- 选中 idea：{report.selected_idea_title or '无'}",
        f"- 决策：{report.decision}",
        "",
        "## 分支评分",
        "| 分支 | 状态 | 综合分 | 原始分 | 证据数 | 风险 | Baseline | 动作 | 理由 |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for branch in report.branches:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(f"{branch.branch_id} {branch.title}"),
                    branch.status,
                    f"{branch.score:.2f}",
                    str(branch.idea_score),
                    str(branch.evidence_count),
                    str(branch.risk),
                    _cell(branch.baseline or "-"),
                    _cell(branch.action),
                    _cell(branch.rationale),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 警告"])
    lines.extend(f"- {item}" for item in report.warnings) if report.warnings else lines.append("- 无")
    lines.extend(
        [
            "",
            "## 使用方式",
            "- 后续实验计划只沿 selected 分支继续；pruned 分支保留为下一轮迭代候选。",
            "- 如果人工不同意 selected 分支，可修改 `02-ideas.json` 排序或从 checkpoint resume。",
        ]
    )
    return "\n".join(lines)


def render_exploration_map_svg(report: ExplorationMap) -> str:
    width = 980
    row_height = 76
    header_height = 96
    height = max(220, header_height + max(1, len(report.branches)) * row_height + 40)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Research exploration map">',
        "<style>",
        ".title{font:700 24px Arial,sans-serif;fill:#111827}.meta{font:14px Arial,sans-serif;fill:#4b5563}.node{stroke:#d1d5db;stroke-width:1.5}.selected{fill:#ecfdf5;stroke:#059669}.pruned{fill:#f9fafb}.label{font:600 14px Arial,sans-serif;fill:#111827}.small{font:12px Arial,sans-serif;fill:#4b5563}.score{font:700 18px Arial,sans-serif;fill:#111827}.link{stroke:#9ca3af;stroke-width:1.4;fill:none}",
        "</style>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="28" y="38" class="title">{_svg_text("Research Exploration Map")}</text>',
        f'<text x="28" y="64" class="meta">{_svg_text(report.topic)}</text>',
        f'<text x="28" y="86" class="meta">{_svg_text(report.decision)}</text>',
    ]
    root_x = 36
    root_y = 122
    root_w = 180
    root_h = 54
    lines.extend(
        [
            f'<rect x="{root_x}" y="{root_y}" width="{root_w}" height="{root_h}" rx="6" class="node selected"/>',
            f'<text x="{root_x + 16}" y="{root_y + 24}" class="label">{_svg_text("approved context")}</text>',
            f'<text x="{root_x + 16}" y="{root_y + 42}" class="small">{_svg_text("branch selection")}</text>',
        ]
    )
    for index, branch in enumerate(report.branches):
        y = header_height + index * row_height + 24
        x = 282
        w = 660
        h = 56
        css = "selected" if branch.status == "selected" else "pruned"
        lines.append(f'<path d="M {root_x + root_w} {root_y + root_h / 2:.0f} C 240 {root_y + root_h / 2:.0f}, 240 {y + h / 2:.0f}, {x} {y + h / 2:.0f}" class="link"/>')
        lines.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="node {css}"/>')
        title = f"{branch.branch_id} {branch.title}"
        detail = f"{branch.status} | evidence {branch.evidence_count} | risk {branch.risk} | {branch.action}"
        lines.append(f'<text x="{x + 16}" y="{y + 22}" class="label">{_svg_text(_short(title, 72))}</text>')
        lines.append(f'<text x="{x + 16}" y="{y + 42}" class="small">{_svg_text(_short(detail, 94))}</text>')
        lines.append(f'<text x="{x + w - 78}" y="{y + 35}" class="score">{branch.score:.2f}</text>')
    lines.append("</svg>")
    return "\n".join(lines)


def _branch(index: int, idea: ResearchIdea, novelty_audit: dict | None = None, idea_audit: dict | None = None) -> ExplorationBranch:
    evidence_count = len(set(idea.evidence_keys + idea.evidence_chunks))
    evidence_bonus = min(2.0, evidence_count * 0.35)
    baseline_bonus = 0.5 if idea.baseline else 0.0
    experiment_bonus = min(1.0, len(idea.experiment_sketch) * 0.2)
    risk_penalty = max(0.0, (idea.risk - 3) * 0.35)
    novelty_item = novelty_item_for_title(novelty_audit, idea.title)
    novelty_penalty = duplicate_penalty(novelty_item)
    audit_item = idea_audit_item_for_title(idea_audit, idea.title)
    audit_penalty = idea_audit_penalty(audit_item)
    score = idea.score + evidence_bonus + baseline_bonus + experiment_bonus - risk_penalty - novelty_penalty - audit_penalty
    strengths = []
    if evidence_count:
        strengths.append(f"{evidence_count} 条证据")
    if idea.baseline:
        strengths.append("baseline 明确")
    if idea.experiment_sketch:
        strengths.append("实验草案可展开")
    if novelty_item:
        strengths.append(f"novelty={novelty_item.get('decision')}")
    if audit_item:
        strengths.append(f"idea_audit={audit_item.get('decision')}")
    if not strengths:
        strengths.append("仍需人工补证")
    return ExplorationBranch(
        branch_id=f"B{index}",
        title=idea.title,
        status="candidate",
        score=round(score, 3),
        idea_score=idea.score,
        evidence_count=evidence_count,
        risk=idea.risk,
        rationale="；".join(strengths),
        action="进入实验计划" if index == 1 else "保留为候选",
        evidence_keys=idea.evidence_keys[:5],
        baseline=idea.baseline,
    )


def _replace_branch_status(branch: ExplorationBranch, status: str) -> ExplorationBranch:
    action = "进入实验计划" if status == "selected" else "下一轮或人工改选时再展开"
    return ExplorationBranch(
        branch_id=branch.branch_id,
        title=branch.title,
        status=status,
        score=branch.score,
        idea_score=branch.idea_score,
        evidence_count=branch.evidence_count,
        risk=branch.risk,
        rationale=branch.rationale,
        action=action,
        evidence_keys=branch.evidence_keys,
        baseline=branch.baseline,
    )


def _svg_text(value: str) -> str:
    return html.escape(value, quote=False)


def _short(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."
