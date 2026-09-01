from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import json
import os

from .artifacts import write_json, write_text


OPEN_SOURCE_LESSONS_JSON = "00-open-source-lessons.json"
OPEN_SOURCE_LESSONS_MD = "00-open-source-lessons.md"


@dataclass(frozen=True)
class OpenSourceProjectProfile:
    name: str
    url: str
    focus: str
    observed_patterns: list[str]
    risk_notes: list[str] = field(default_factory=list)
    evidence_targets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OpenSourceProjectEvidence:
    project_name: str
    repository_url: str
    status: str
    verification_mode: str
    evidence_targets: list[str]
    verified_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    default_branch: str = ""
    head_commit: str = ""
    checked_at: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OpenSourceLesson:
    lesson_id: str
    source_projects: list[str]
    pipeline_targets: list[str]
    requirement: str
    rationale: str
    status_policy: str = "required"


@dataclass(frozen=True)
class OpenSourceLessonsReport:
    topic: str
    status: str
    profiles: list[OpenSourceProjectProfile]
    project_evidence: list[OpenSourceProjectEvidence]
    lessons: list[OpenSourceLesson]
    manual_checklist: list[str]
    agent_prompt_text: str
    contract_summary: dict[str, Any] = field(default_factory=dict)


OpenSourceEvidenceVerifier = Callable[[OpenSourceProjectProfile], dict[str, Any] | OpenSourceProjectEvidence | None]
GithubJsonFetcher = Callable[[str, float, dict[str, str]], dict[str, Any]]


def write_open_source_lessons_artifacts(topic: str, out_dir: Path, verifier: OpenSourceEvidenceVerifier | None = None) -> OpenSourceLessonsReport:
    report = build_open_source_lessons(topic, verifier=verifier)
    write_json(out_dir / OPEN_SOURCE_LESSONS_JSON, report)
    write_text(out_dir / OPEN_SOURCE_LESSONS_MD, render_open_source_lessons_markdown(report))
    return report


def github_project_evidence_verifier(timeout_seconds: float = 5.0, token: str | None = None, fetch_json: GithubJsonFetcher | None = None) -> OpenSourceEvidenceVerifier:
    return lambda profile: refresh_github_project_evidence(profile, timeout_seconds=timeout_seconds, token=token, fetch_json=fetch_json)


def refresh_github_project_evidence(
    profile: OpenSourceProjectProfile,
    *,
    timeout_seconds: float = 5.0,
    token: str | None = None,
    fetch_json: GithubJsonFetcher | None = None,
) -> OpenSourceProjectEvidence:
    owner_repo = _github_owner_repo(profile.url)
    if owner_repo is None:
        return OpenSourceProjectEvidence(
            project_name=profile.name,
            repository_url=profile.url,
            status="unverified",
            verification_mode="github_api",
            evidence_targets=list(profile.evidence_targets),
            checked_at=_utc_now(),
            notes=["项目 URL 不是可识别的 GitHub 仓库地址。"],
        )
    owner, repo = owner_repo
    fetch = fetch_json or _fetch_github_json
    headers = _github_headers(token)
    repo_api = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        repo_data = fetch(repo_api, timeout_seconds, headers)
    except Exception as exc:
        return OpenSourceProjectEvidence(
            project_name=profile.name,
            repository_url=profile.url,
            status="unverified",
            verification_mode="github_api",
            evidence_targets=list(profile.evidence_targets),
            checked_at=_utc_now(),
            notes=[f"GitHub 元数据刷新失败：{_safe_error(exc, token)}"],
        )

    default_branch = str(repo_data.get("default_branch") or "").strip()
    head_commit = _github_head_commit(owner, repo, default_branch, timeout_seconds, headers, fetch)
    verified: list[str] = []
    missing: list[str] = []
    for target in profile.evidence_targets:
        if _github_content_exists(owner, repo, target, default_branch, timeout_seconds, headers, fetch):
            verified.append(target)
        else:
            missing.append(target)
    if verified and not missing:
        status = "verified"
    elif verified:
        status = "partial"
    else:
        status = "unverified"
    notes = [] if verified else ["未能核对到关键文件；可能是 API 限流、路径变更或仓库结构变化。"]
    return OpenSourceProjectEvidence(
        project_name=profile.name,
        repository_url=profile.url,
        status=status,
        verification_mode="github_api",
        evidence_targets=list(profile.evidence_targets),
        verified_files=verified,
        missing_files=missing,
        default_branch=default_branch,
        head_commit=head_commit,
        checked_at=_utc_now(),
        notes=notes,
    )


def build_open_source_lessons(topic: str, verifier: OpenSourceEvidenceVerifier | None = None) -> OpenSourceLessonsReport:
    profiles = _profiles()
    project_evidence = _project_evidence(profiles, verifier)
    lessons = _lessons(topic)
    return OpenSourceLessonsReport(
        topic=topic,
        status="constraints_ready" if lessons else "no_external_constraints",
        profiles=profiles,
        project_evidence=project_evidence,
        lessons=lessons,
        manual_checklist=_manual_checklist(lessons),
        agent_prompt_text=_agent_prompt_text(lessons, project_evidence),
        contract_summary=_contract_summary(profiles, project_evidence, lessons),
    )


def render_open_source_lessons_markdown(report: OpenSourceLessonsReport) -> str:
    lines = [
        f"# Open-Source Project Lessons：{report.topic}",
        "",
        f"- 状态：{report.status}",
        f"- 参考项目：{len(report.profiles)}",
        f"- 约束数：{len(report.lessons)}",
        f"- Contract：{_contract_text(report.contract_summary)}",
        "",
        "## 参考项目",
        "| 项目 | 重点 | 来源 | 观察到的模式 | 风险提示 | 证据目标 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for profile in report.profiles:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(profile.name),
                    _cell(profile.focus),
                    _cell(profile.url),
                    _cell("；".join(profile.observed_patterns)),
                    _cell("；".join(profile.risk_notes) or "-"),
                    _cell("；".join(profile.evidence_targets) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 项目来源证据",
            "| 项目 | 状态 | 验证方式 | Branch/Commit | 已核对文件 | 缺失文件 | 说明 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in report.project_evidence:
        branch_commit = "/".join(value for value in [item.default_branch, item.head_commit[:12]] if value) or "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.project_name),
                    _cell(item.status),
                    _cell(item.verification_mode),
                    _cell(branch_commit),
                    _cell("；".join(item.verified_files) or "-"),
                    _cell("；".join(item.missing_files) or "-"),
                    _cell("；".join(item.notes) or "-"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 固化到本平台的约束",
            "| 约束 | 来源项目 | 目标阶段 | 策略 | 要求 | 理由 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for lesson in report.lessons:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(lesson.lesson_id),
                    _cell(", ".join(lesson.source_projects)),
                    _cell(", ".join(lesson.pipeline_targets)),
                    _cell(lesson.status_policy),
                    _cell(lesson.requirement),
                    _cell(lesson.rationale),
                ]
            )
            + " |"
        )
    lines.extend(["", "## 启动前人工检查"])
    lines.extend(f"- [ ] {item}" for item in report.manual_checklist) if report.manual_checklist else lines.append("- 暂无")
    lines.extend(["", "## 给 Agent 的外部项目约束"])
    lines.append(report.agent_prompt_text or "无外部项目约束。")
    return "\n".join(lines)


def _profiles() -> list[OpenSourceProjectProfile]:
    return [
        OpenSourceProjectProfile(
            name="SakanaAI/AI-Scientist-v2",
            url="https://github.com/SakanaAI/AI-Scientist-v2",
            focus="端到端科研自动化：idea、实验、分析、写作和评审式闭环。",
            observed_patterns=[
                "用结构化 idea 文件驱动后续实验",
                "用 agentic tree search 扩展和调试实验路径",
                "把写作、引用和 review 明确拆成阶段",
            ],
            risk_notes=[
                "会执行 LLM 生成代码，必须放在受控 sandbox 或严格 allowlist 内",
                "Semantic Scholar rate limit 会影响 novelty/citation 阶段",
                "AI 生成论文需要披露",
            ],
            evidence_targets=["README.md", "docs/", "ai_scientist/"],
        ),
        OpenSourceProjectProfile(
            name="Future-House/PaperQA2",
            url="https://github.com/Future-House/paper-qa",
            focus="面向科研文献的高准确率 agentic RAG 和带 citation 的 grounded answers。",
            observed_patterns=[
                "先构建本地全文检索索引，再从 chunks 收集 evidence",
                "回答必须包含正文内 citation 和可追踪 context",
                "组合多源 metadata、重排、缓存和可复用索引",
            ],
            risk_notes=[
                "大规模文献 metadata 需要 Crossref/Semantic Scholar 等 API key 避免限流",
                "模型和 embedding 配置会影响检索质量",
            ],
            evidence_targets=["README.md", "paperqa/", "paperqa/agents/"],
        ),
        OpenSourceProjectProfile(
            name="OpenScholar",
            url="https://github.com/AkariAsai/OpenScholar",
            focus="面向科学文献的检索增强综述生成：先检索/重排高相关论文，再生成带引用答案。",
            observed_patterns=[
                "把检索、重排和 citation 生成拆成可复查步骤",
                "用高质量候选池约束生成，而不是让 LLM 凭泛化知识写综述",
                "强调答案中的引用覆盖和可追溯证据",
            ],
            risk_notes=[
                "如果初始检索池质量差，后续生成和引用覆盖都会被污染",
                "需要显式记录候选排序理由，便于人工修复 seed/query",
            ],
            evidence_targets=["README.md", "retriever", "rerank"],
        ),
        OpenSourceProjectProfile(
            name="SamuelSchmidgall/AgentLaboratory",
            url="https://github.com/SamuelSchmidgall/AgentLaboratory",
            focus="端到端科研助手：文献综述、实验和报告写作，并强调人的研究意图和反馈。",
            observed_patterns=[
                "把科研流程拆成 literature review、experimentation 和 report writing 阶段",
                "允许不同计算资源和人工参与程度",
                "用户 notes 会影响实验、图表、API key 和写作偏好",
            ],
            risk_notes=[
                "人工 notes 如果只进入 prompt 而没有审计，后续 agent 可能忽略关键约束",
                "端到端流程需要明确每阶段哪些结果可自动继续、哪些必须人工确认",
            ],
            evidence_targets=["README.md", "ai_lab_repo/", "research_dir/"],
        ),
        OpenSourceProjectProfile(
            name="MLAgentBench / MLE-bench-style tasks",
            url="https://github.com/snap-stanford/MLAgentBench",
            focus="用标准任务、运行轨迹、指标文件和最终产物评估科研/机器学习 agent 的真实执行能力。",
            observed_patterns=[
                "把 benchmark 任务、baseline、metric schema 和输出文件格式作为显式 contract",
                "要求每次运行保留命令、日志、指标、产物和可复查执行轨迹",
                "评估时区分真实任务完成、局部实验和 smoke run",
            ],
            risk_notes=[
                "如果只检查是否有结果文件，无法发现 candidate/baseline/ablation schema 不可比较",
                "benchmark adapter 输出路径和 metrics_path 断链会让统计和论文结果不可复现",
            ],
            evidence_targets=["README.md", "MLAgentBench/", "benchmarks/"],
        ),
    ]


def _project_evidence(profiles: list[OpenSourceProjectProfile], verifier: OpenSourceEvidenceVerifier | None) -> list[OpenSourceProjectEvidence]:
    evidence: list[OpenSourceProjectEvidence] = []
    for profile in profiles:
        item = verifier(profile) if verifier is not None else None
        if isinstance(item, OpenSourceProjectEvidence):
            evidence.append(item)
            continue
        if isinstance(item, dict):
            evidence.append(
                OpenSourceProjectEvidence(
                    project_name=str(item.get("project_name") or profile.name),
                    repository_url=str(item.get("repository_url") or profile.url),
                    status=str(item.get("status") or "catalogued"),
                    verification_mode=str(item.get("verification_mode") or "external_verifier"),
                    evidence_targets=_string_list(item.get("evidence_targets")) or list(profile.evidence_targets),
                    verified_files=_string_list(item.get("verified_files")),
                    missing_files=_string_list(item.get("missing_files")),
                    default_branch=str(item.get("default_branch") or ""),
                    head_commit=str(item.get("head_commit") or ""),
                    checked_at=str(item.get("checked_at") or ""),
                    notes=_string_list(item.get("notes")),
                )
            )
            continue
        evidence.append(
            OpenSourceProjectEvidence(
                project_name=profile.name,
                repository_url=profile.url,
                status="catalogued",
                verification_mode="built_in_catalog",
                evidence_targets=list(profile.evidence_targets),
                notes=["默认运行不联网抓取 GitHub；如要更新外部项目版本，请人工刷新项目来源证据。"],
            )
        )
    return evidence


def _github_owner_repo(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return parts[0], repo


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "research-agent-open-source-provenance",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    value = (token if token is not None else os.environ.get("GITHUB_TOKEN", "")).strip()
    if value:
        headers["Authorization"] = f"Bearer {value}"
    return headers


def _fetch_github_json(url: str, timeout_seconds: float, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=max(float(timeout_seconds), 0.1)) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _github_head_commit(owner: str, repo: str, branch: str, timeout_seconds: float, headers: dict[str, str], fetch: GithubJsonFetcher) -> str:
    if not branch:
        return ""
    try:
        data = fetch(f"https://api.github.com/repos/{owner}/{repo}/branches/{quote(branch, safe='')}", timeout_seconds, headers)
    except Exception:
        return ""
    commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
    return str(commit.get("sha") or "").strip()


def _github_content_exists(owner: str, repo: str, target: str, branch: str, timeout_seconds: float, headers: dict[str, str], fetch: GithubJsonFetcher) -> bool:
    target = target.strip().strip("/")
    if not target:
        return False
    ref = f"?ref={quote(branch, safe='')}" if branch else ""
    try:
        fetch(f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(target, safe='/')}{ref}", timeout_seconds, headers)
    except Exception:
        return False
    return True


def _safe_error(exc: Exception, *secrets: str | None) -> str:
    text = str(exc)
    for secret in [*secrets, os.environ.get("GITHUB_TOKEN", "")]:
        value = str(secret or "").strip()
        if value:
            text = text.replace(value, "***")
    return text[:240]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lessons(topic: str) -> list[OpenSourceLesson]:
    base = [
        OpenSourceLesson(
            lesson_id="source_project_provenance",
            source_projects=["AI-Scientist-v2", "PaperQA2", "OpenScholar", "AgentLaboratory", "MLAgentBench"],
            pipeline_targets=["open_source_lessons", "open_source_compliance", "run_integrity"],
            requirement="开源项目约束必须带仓库 URL、证据目标和可刷新 provenance；默认离线编目可以运行，但不能把未核对版本当作强证据。",
            rationale="平台长期演进不能只复制一次性文字总结；需要知道外部项目参考来自哪里、是否可刷新、是否缺关键证据文件。",
        ),
        OpenSourceLesson(
            lesson_id="structured_idea_to_experiment_loop",
            source_projects=["AI-Scientist-v2"],
            pipeline_targets=["ideation", "exploration_map", "experiment_plan", "experiment_decision"],
            requirement="idea 必须保留 hypothesis、baseline、metric、evidence keys 和实验草案；进入实验前必须经过探索图和人工 gate。",
            rationale="端到端科研 agent 不能从单次头脑风暴直接跳到实验；需要可审计的 idea -> experiment 链路。",
        ),
        OpenSourceLesson(
            lesson_id="sandbox_generated_code",
            source_projects=["AI-Scientist-v2"],
            pipeline_targets=["experiment_audit", "execution_safety", "experiment_execution"],
            requirement="任何自动实验命令必须经过 allowlist、路径边界、环境快照和 artifact hash；高风险命令只能人工接管。",
            rationale="自动科研系统会运行模型生成或用户提供的实验命令，安全边界是平台级硬约束。",
        ),
        OpenSourceLesson(
            lesson_id="citation_grounded_fulltext",
            source_projects=["PaperQA2"],
            pipeline_targets=["literature_context", "fulltext_corpus", "writing", "citation_grounding"],
            requirement="写作前必须优先使用可追踪 citation key、fulltext chunk 和 chunk-level evidence；不得只凭标题/摘要生成强结论。",
            rationale="科研 RAG 的核心质量来自带引用的 evidence gathering，而不是宽泛摘要。",
        ),
        OpenSourceLesson(
            lesson_id="retrieval_rerank_before_synthesis",
            source_projects=["PaperQA2", "OpenScholar"],
            pipeline_targets=["literature_rerank", "literature_quality", "literature_context", "citation_coverage"],
            requirement="进入综述、idea 或写作前，候选文献必须先按标题特异性、query 覆盖、来源/venue 可靠性、metadata 和 citation 信号重排，并把降权原因写入 artifact。",
            rationale="文献池质量决定后续 RAG、idea 和引用质量；LLM 不能用生成能力掩盖弱检索结果。",
        ),
        OpenSourceLesson(
            lesson_id="query_execution_coverage_audit",
            source_projects=["PaperQA2", "OpenScholar"],
            pipeline_targets=["literature_search", "literature_rerank", "repair_queue"],
            requirement="文献阶段必须记录 selected queries 到各 source 的执行结果，并审计 query intent、source 返回和 top rerank 覆盖；覆盖不足时进入 repair queue。",
            rationale="只看总返回数无法解释文献质量差的原因；query/source 级审计能区分 API 限流、检索式偏题和候选重排污染。",
        ),
        OpenSourceLesson(
            lesson_id="human_feedback_compliance",
            source_projects=["AgentLaboratory"],
            pipeline_targets=["review_constraints", "ideation", "experiment_plan", "experiment_audit"],
            requirement="人工审核 notes 必须被结构化为约束，并在选中 idea 与实验计划中进行 compliance 审计；高优先级约束缺失时不得继续执行实验。",
            rationale="人类研究者的反馈是科研 agent 的核心输入；只把反馈放进 prompt，无法证明后续阶段真的遵守。",
        ),
        OpenSourceLesson(
            lesson_id="repair_context_on_resume",
            source_projects=["AI-Scientist-v2", "AgentLaboratory"],
            pipeline_targets=["repair_queue", "repair_resume", "repair_resolution_audit", "ideation", "experiment_plan"],
            requirement="从 repair queue 恢复时，必须把失败审计中的 blockers、manual tasks、required actions 和失败 checks 注入下一轮 agent 规划上下文，并在重跑后审计原修复项是否闭环。",
            rationale="迭代式科研 agent 不能只删除旧产物后重跑；下一轮必须显式知道上次为什么失败，并证明原问题已经消失，才能形成有效 debug/repair loop。",
        ),
        OpenSourceLesson(
            lesson_id="benchmark_result_schema_contract",
            source_projects=["MLAgentBench", "MLE-bench-style tasks"],
            pipeline_targets=["experiment_execution", "result_validation", "benchmark_evidence", "repair_queue"],
            requirement="实验完成后必须审计 04-results、04-statistics、04-experiment-runbook、benchmark adapter metrics_path 和 expected_artifacts 是否共享同一 result schema；candidate/baseline/ablation 不可比较时必须进入修复队列。",
            rationale="真实 benchmark 的可信度来自可复查的指标 schema 和产物 trace，而不是只看到某个脚本返回 0 或生成了一个结果文件。",
        ),
        OpenSourceLesson(
            lesson_id="runtime_cost_observability",
            source_projects=["AgentLaboratory", "MLAgentBench"],
            pipeline_targets=["run_manifest", "llm_trace", "run_economics", "agent_observability", "repair_queue"],
            requirement="每个 run 必须保留阶段事件、artifact inventory、LLM 调用预算/耗时/成本估算、human gate、实验 runtime trace、诊断恢复和 repair queue 状态；可观测性或成本归因断链必须进入修复队列。",
            rationale="科研 agent 平台如果不能解释一次 run 为什么失败、卡住、耗尽预算或需要恢复，就无法形成可靠的人机协作和 benchmark 评估。",
        ),
        OpenSourceLesson(
            lesson_id="metadata_rate_limit_resilience",
            source_projects=["AI-Scientist-v2", "PaperQA2"],
            pipeline_targets=["literature_search", "literature_rescue", "preflight"],
            requirement="文献检索必须保留多源诊断、API key 提示、补检索计划和弱文献 rescue；Semantic Scholar 限流不能静默降级为低质量文献。",
            rationale="外部项目都依赖 Semantic Scholar/Crossref 等 metadata；限流会直接损害 novelty 和 citation 质量。",
        ),
        OpenSourceLesson(
            lesson_id="cache_and_memory_reuse",
            source_projects=["PaperQA2"],
            pipeline_targets=["prior_run_lessons", "run_memory", "research_plan"],
            requirement="每次 run 必须读取历史失败、弱文献、citation grounding、结果呈现和发布阻断项，并把它们注入下一轮规划。",
            rationale="可复用索引和历史记忆可以减少重复错误，提升后续 run 的检索和写作质量。",
        ),
        OpenSourceLesson(
            lesson_id="ai_use_disclosure",
            source_projects=["AI-Scientist-v2"],
            pipeline_targets=["ai_disclosure", "submission_check", "submission_package"],
            requirement="投稿包必须包含 AI 使用披露、LLM ledger 和人工 policy check；不能把 AI 参与隐藏在最终稿之外。",
            rationale="自治科研写作需要透明披露模型参与、调用痕迹和人工核验边界。",
        ),
    ]
    if _robotics_topic(topic):
        base.append(
            OpenSourceLesson(
                lesson_id="domain_benchmark_before_claims",
                source_projects=["AI-Scientist-v2", "PaperQA2"],
                pipeline_targets=["benchmark_plan", "experiment_decision", "results_presentation"],
                requirement="机械臂路径规划类课题必须优先声明 OMPL/MoveIt 或同等公开任务、baseline 和重复 seed；没有真实 benchmark 时只能写 smoke-test 结果。",
                rationale="领域任务必须先固定 benchmark/baseline，结果章节不能把模拟烟测写成正式科学结论。",
            )
        )
    return base


def _manual_checklist(lessons: list[OpenSourceLesson]) -> list[str]:
    return [
        "确认本轮文献源 API key、LLM 配置和检索 provider 已能支持高质量 evidence gathering。",
        "确认实验模式是否为 local/benchmark；若仍是 simulated，结果必须被写成烟测而不是科学结论。",
        "确认投稿包中保留 AI disclosure、LLM ledger、run manifest 和完整审计产物。",
        "确认 open-source lessons 中的 required 约束已经在 research plan 的 constraints/risks 中可见。",
    ][: 2 + min(2, len(lessons))]


def _agent_prompt_text(lessons: list[OpenSourceLesson], project_evidence: list[OpenSourceProjectEvidence]) -> str:
    if not lessons:
        return ""
    lines = [
        "外部开源科研 agent 项目经验必须作为本轮平台约束处理：",
    ]
    if project_evidence:
        status_text = ", ".join(f"{item.project_name}:{item.status}" for item in project_evidence[:5])
        lines.append(f"参考项目 provenance：{status_text}。")
    for lesson in lessons[:8]:
        lines.append(f"- [{lesson.status_policy}] {lesson.lesson_id} ({', '.join(lesson.source_projects)}) -> {', '.join(lesson.pipeline_targets)}: {lesson.requirement}")
    return "\n".join(lines)


def _contract_summary(
    profiles: list[OpenSourceProjectProfile],
    project_evidence: list[OpenSourceProjectEvidence],
    lessons: list[OpenSourceLesson],
) -> dict[str, Any]:
    lesson_ids = [lesson.lesson_id for lesson in lessons if lesson.lesson_id]
    project_names = [profile.name for profile in profiles if profile.name]
    evidence_projects = [item.project_name for item in project_evidence if item.project_name]
    return {
        "schema_version": 1,
        "profile_count": len(project_names),
        "project_evidence_count": len(evidence_projects),
        "lesson_count": len(lesson_ids),
        "required_project_names": project_names,
        "project_evidence_names": evidence_projects,
        "required_lesson_ids": lesson_ids,
        "required_pipeline_targets": _dedupe(
            [
                target
                for lesson in lessons
                for target in lesson.pipeline_targets
                if str(target).strip()
            ]
        ),
        "required_source_projects": _dedupe(
            [
                project
                for lesson in lessons
                for project in lesson.source_projects
                if str(project).strip()
            ]
        ),
    }


def _contract_text(value: dict[str, Any]) -> str:
    if not isinstance(value, dict) or not value:
        return "missing"
    return (
        f"projects={int(value.get('profile_count') or 0)}, "
        f"evidence={int(value.get('project_evidence_count') or 0)}, "
        f"lessons={int(value.get('lesson_count') or 0)}"
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _robotics_topic(topic: str) -> bool:
    lowered = topic.lower()
    return "机械臂" in topic or "manipulator" in lowered or ("robot" in lowered and ("path" in lowered or "motion" in lowered))


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
