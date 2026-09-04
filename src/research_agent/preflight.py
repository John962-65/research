from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import json
import os
import re
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from .agent_verdict import ROLE_EVIDENCE_VIEWS
from .artifacts import write_json, write_text, cell as _cell
from .benchmark_adapter import audit_benchmark_adapter_config, formal_benchmark_provenance_issues
from .config import AgentConfig
from .credential_validation import placeholder_secret as _placeholder_secret
from .credential_validation import valid_contact_email as _valid_contact_email
from .llm_trace_audit import REQUIRED_STAGE_SPECS


# A complete run needs one successful call per required stage, plus one
# independent verdict per role when the independent deliberation layer is on.
# Derived from the specs that define those sets so the floor tracks them instead
# of drifting.
_MIN_RUN_CALLS_SINGLE_AGENT = len(REQUIRED_STAGE_SPECS)
_MIN_RUN_CALLS_MULTI_AGENT = len(REQUIRED_STAGE_SPECS) + len(ROLE_EVIDENCE_VIEWS)

# The first and smallest stage (research planning) sends about 5.3k characters --
# system 922 + user 4418, measured on a real run -- and prompts only grow from
# there as prior-run lessons and literature context are added. A positive cap
# below this floor cannot admit a single call, so it disables the LLM entirely
# while still looking like a configured budget.
_MIN_USABLE_PROMPT_CHARS = 8192

# Literature synthesis, paper writing and revision carry the largest prompts;
# this is the floor the cross-run memory checks already recommend.
_RECOMMENDED_PROMPT_CHARS = 20000


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: str
    summary: str
    detail: str = ""
    action: str = ""


@dataclass(frozen=True)
class PreflightReport:
    topic: str
    status: str
    checks: list[PreflightCheck]


KNOWN_LITERATURE_SOURCES = {"semantic_scholar", "openalex", "arxiv", "crossref", "pubmed"}
PREFLIGHT_JSON = "00-preflight.json"
PREFLIGHT_MD = "00-preflight.md"


def run_preflight(
    topic: str,
    config: AgentConfig,
    ping_llm: bool = True,
    llm_timeout_seconds: float = 8.0,
    run_memory: Any | None = None,
) -> PreflightReport:
    checks: list[PreflightCheck] = []
    topic_value = topic.strip()
    if topic_value:
        checks.append(PreflightCheck("topic", "pass", "研究课题已填写", f"{len(topic_value)} characters"))
    else:
        checks.append(PreflightCheck("topic", "fail", "研究课题为空", action="填写明确研究课题后再启动。"))

    checks.extend(_llm_static_checks(config))
    checks.extend(_literature_checks(config))
    checks.extend(_execution_checks(config))
    checks.extend(_paper_grade_checks(config))
    checks.extend(_multi_agent_credential_checks(config))
    checks.extend(_llm_route_checks(config))
    checks.extend(_release_checks(config))
    checks.extend(_run_memory_checks(config, run_memory))
    if ping_llm:
        checks.append(_llm_ping_check(config, llm_timeout_seconds))
    else:
        checks.append(PreflightCheck("llm_ping", "skipped", "未执行 LLM 连通性测试"))
    return PreflightReport(topic=topic_value, status=_overall_status(checks), checks=checks)


def render_preflight_markdown(report: PreflightReport) -> str:
    lines = [
        f"# 预检报告：{report.topic or '未填写课题'}",
        "",
        f"- 状态：{report.status}",
        f"- 检查项：{len(report.checks)}",
        "",
        "| 检查项 | 状态 | 结果 | 建议 |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        result = check.summary
        if check.detail:
            result += f"；{check.detail}"
        lines.append(f"| {_cell(check.name)} | {check.status} | {_cell(result)} | {_cell(check.action or '-')} |")
    return "\n".join(lines)


def write_preflight_artifacts(report: PreflightReport, out_dir: Path) -> tuple[Path, Path]:
    json_path = out_dir / PREFLIGHT_JSON
    md_path = out_dir / PREFLIGHT_MD
    write_json(json_path, report)
    write_text(md_path, render_preflight_markdown(report))
    return json_path, md_path


def _llm_route_checks(config: AgentConfig) -> list[PreflightCheck]:
    """ROUTE-01: enumerate every (provider, endpoint, model, credential) route."""
    from .llm import enumerate_llm_routes

    checks: list[PreflightCheck] = []
    try:
        routes = enumerate_llm_routes(config)
    except Exception as exc:
        checks.append(PreflightCheck("llm_routes", "fail", f"无法枚举 LLM 路由：{exc}", action="检查 llm 与 multi_agent 配置。"))
        return checks
    problems: list[str] = []
    for route in routes:
        route_id = str(route.get("route_id") or "")
        if not route.get("base_url"):
            problems.append(f"{route_id}: endpoint 未解析")
        if not route.get("model"):
            problems.append(f"{route_id}: model 未配置")
    if problems:
        checks.append(
            PreflightCheck(
                "llm_routes",
                "fail",
                "；".join(problems[:4]),
                detail=f"routes={len(routes)}",
                action="为每个角色/任务路由补齐 model 与可证明的凭据来源。",
            )
        )
    else:
        summary = "；".join(f"{route['route_id']}→{route['model'] or '-'}" for route in routes[:4])
        checks.append(PreflightCheck("llm_routes", "pass", f"{len(routes)} 条路由全部可解析", summary))
    return checks


def _multi_agent_credential_checks(config: AgentConfig) -> list[PreflightCheck]:
    """SEC-01: every role endpoint must bind to a provably same-origin credential."""
    from .llm import resolve_role_llm_config

    checks: list[PreflightCheck] = []
    multi_agent = config.multi_agent
    if not multi_agent.enabled or not multi_agent.roles:
        return checks
    for role in multi_agent.roles:
        if not role.enabled:
            continue
        try:
            resolve_role_llm_config(
                config.llm,
                model=role.model,
                base_url=role.base_url,
                base_url_env=role.base_url_env,
                api_key_env=role.api_key_env,
            )
        except ValueError as exc:
            checks.append(
                PreflightCheck(
                    "multi_agent_credential_origin",
                    "fail",
                    f"角色 {role.agent_id}: {exc}",
                    action="为该角色声明成对的 base_url_env/api_key_env；或去掉独立 endpoint，改用全局 endpoint 与凭据。",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "multi_agent_credential_origin",
                    "pass",
                    f"角色 {role.agent_id} 的 endpoint/凭据绑定同源可证",
                )
            )
    return checks


def _llm_static_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    checks: list[PreflightCheck] = []
    from .llm import redact_url, resolve_llm_api_key, resolve_llm_base_url, validate_llm_provider
    try:
        provider = validate_llm_provider(llm.provider)
    except ValueError as exc:
        checks.append(PreflightCheck("llm_provider", "fail", str(exc), action="使用 OpenAI Chat Completions 兼容协议。"))
        checks.extend(_llm_budget_checks(config))
        return checks
    checks.append(PreflightCheck("llm_provider", "pass", "LLM provider 可用", provider))
    env_base_url = os.environ.get(llm.base_url_env, "").strip() if llm.base_url_env else ""
    base_url_configured = bool(str(llm.base_url or "").strip() or env_base_url)
    try:
        base_url = resolve_llm_base_url(provider, llm.base_url, llm.base_url_env)
        base_url_error = ""
    except ValueError as exc:
        base_url = ""
        base_url_error = str(exc)
    model = _resolved(llm.model, llm.model_env, "")
    api_key = resolve_llm_api_key(llm, base_url) if base_url else llm.api_key
    if config.paper_grade.enabled and not base_url_configured:
        checks.append(
            PreflightCheck(
                "llm_base_url",
                "fail",
                "paper-grade run 缺少显式 Base URL",
                action=f"设置环境变量 {llm.base_url_env} 或在配置中填写 llm.base_url。",
            )
        )
    elif base_url_error:
        checks.append(PreflightCheck("llm_base_url", "fail", base_url_error, action="填写仅含 http/https scheme 与主机名的 Base URL。"))
    else:
        checks.append(PreflightCheck("llm_base_url", "pass", "Base URL 已解析", redact_url(base_url)))
    if model:
        checks.append(PreflightCheck("llm_model", "pass", "模型名已配置", model))
    else:
        checks.append(PreflightCheck("llm_model", "fail", "模型名缺失", action=f"填写模型名，或设置环境变量 {llm.model_env}。"))
    official_openai = urllib.parse.urlsplit(base_url).hostname == "api.openai.com" if base_url else False
    if not api_key and (official_openai or config.paper_grade.enabled):
        summary = "OpenAI 官方接口缺少 API key" if official_openai else "paper-grade run 缺少 API key"
        key_action = (
            f"设置环境变量 {llm.api_key_env}，不要把密钥写入配置文件或命令行参数。"
            if llm.api_key_env
            else "为该 Web 请求同时填写 Base URL 和对应 API Key；不会使用服务器环境中的其他 key。"
        )
        checks.append(
            PreflightCheck(
                "llm_api_key",
                "fail",
                summary,
                action=key_action,
            )
        )
    elif api_key and config.paper_grade.enabled and _placeholder_secret(api_key):
        checks.append(
            PreflightCheck(
                "llm_api_key",
                "fail",
                "paper-grade run 的 API key 是占位值",
                "已隐藏",
                f"设置真实环境变量 {llm.api_key_env}；不要把占位 key 留在正式配置里。",
            )
        )
    elif api_key:
        checks.append(PreflightCheck("llm_api_key", "pass", "API key 已配置", "已隐藏"))
    else:
        checks.append(PreflightCheck("llm_api_key", "warn", "API key 未配置", action="如果本地兼容接口不需要 key 可忽略；否则填写 API Key。"))
    checks.extend(_llm_budget_checks(config))
    return checks


def _llm_budget_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    checks: list[PreflightCheck] = []
    multi_agent = config.multi_agent.enabled
    min_calls = _MIN_RUN_CALLS_MULTI_AGENT if multi_agent else _MIN_RUN_CALLS_SINGLE_AGENT
    if llm.max_calls < 0:
        checks.append(PreflightCheck("llm_max_calls", "fail", "LLM 调用上限不能为负数", action="设置 max_calls >= 0；0 表示不限制。"))
    elif llm.max_calls == 0:
        checks.append(PreflightCheck("llm_max_calls", "pass", "LLM 调用数不限制"))
    elif llm.max_calls < min_calls:
        checks.append(
            PreflightCheck(
                "llm_max_calls",
                "warn",
                f"LLM 调用上限 {llm.max_calls} 不足以完成一次端到端 run",
                str(llm.max_calls),
                action=(
                    f"当前配置下一次完整 run 至少需要 {min_calls} 次成功调用"
                    + (
                        f"（{len(REQUIRED_STAGE_SPECS)} 个必需阶段 + {len(ROLE_EVIDENCE_VIEWS)} 个独立角色 verdict，multi_agent 已启用）"
                        if multi_agent
                        else f"（{len(REQUIRED_STAGE_SPECS)} 个必需阶段；启用 multi_agent 后还需 {len(ROLE_EVIDENCE_VIEWS)} 次独立角色 verdict）"
                    )
                    + "；设为 0 表示不限制。单阶段探针可保留较小值。"
                ),
            )
        )
    else:
        checks.append(PreflightCheck("llm_max_calls", "pass", "LLM 调用上限已配置", str(llm.max_calls)))
    if llm.max_prompt_chars < 0:
        checks.append(
            PreflightCheck("llm_max_prompt_chars", "fail", "LLM prompt 字符上限不能为负数", action="设置 max_prompt_chars >= 0；0 表示不限制。")
        )
    elif llm.max_prompt_chars == 0:
        checks.append(PreflightCheck("llm_max_prompt_chars", "pass", "LLM prompt 字符数不限制"))
    elif llm.max_prompt_chars < _MIN_USABLE_PROMPT_CHARS:
        # Any positive cap this small rejects every stage, so the run cannot make
        # a single LLM call: llm_trace raises the budget error before the request
        # is built. Reporting it as configured is what let a doomed run start.
        checks.append(
            PreflightCheck(
                "llm_max_prompt_chars",
                "fail",
                f"LLM prompt 字符上限 {llm.max_prompt_chars} 低于任何阶段的最小 prompt，等价于禁用 LLM",
                str(llm.max_prompt_chars),
                action=(
                    f"设为 0（不限制）或 >= {_RECOMMENDED_PROMPT_CHARS}。首个研究计划阶段的 prompt 实测约 5340 字符，"
                    "当前上限会在构造请求之前拦截每一次调用（llm_trace 抛 LLM budget exceeded）。"
                ),
            )
        )
    elif llm.max_prompt_chars < _RECOMMENDED_PROMPT_CHARS:
        checks.append(
            PreflightCheck(
                "llm_max_prompt_chars",
                "warn",
                f"LLM prompt 字符上限 {llm.max_prompt_chars} 偏低，较大阶段会被拦截",
                str(llm.max_prompt_chars),
                action=(
                    f"研究计划阶段可以通过，但文献综合、论文写作与修订的 prompt 更大；"
                    f"建议 >= {_RECOMMENDED_PROMPT_CHARS}，或设为 0 表示不限制。"
                ),
            )
        )
    else:
        checks.append(PreflightCheck("llm_max_prompt_chars", "pass", "LLM prompt 字符上限已配置", str(llm.max_prompt_chars)))
    if llm.input_cost_per_million_tokens < 0 or llm.output_cost_per_million_tokens < 0:
        checks.append(PreflightCheck("llm_token_cost", "fail", "LLM token 单价不能为负数", action="设置 input/output cost >= 0；0 表示不估算美元成本。"))
    elif llm.input_cost_per_million_tokens > 0 and llm.output_cost_per_million_tokens > 0:
        checks.append(
            PreflightCheck(
                "llm_token_cost",
                "pass",
                "LLM token 单价已配置",
                f"input={llm.input_cost_per_million_tokens}/M output={llm.output_cost_per_million_tokens}/M",
            )
        )
    else:
        checks.append(PreflightCheck("llm_token_cost", "skipped", "未配置美元成本估算", action="如需成本审计，填写 input/output 每百万 token 单价。"))
    return checks


def _literature_checks(config: AgentConfig) -> list[PreflightCheck]:
    literature = config.literature
    checks: list[PreflightCheck] = []
    if literature.provider not in {"offline", "online", "auto"}:
        checks.append(PreflightCheck("literature_provider", "fail", f"不支持的文献模式: {literature.provider}", action="使用 offline、online 或 auto。"))
    else:
        checks.append(PreflightCheck("literature_provider", "pass", "文献模式可用", literature.provider))
    if literature.max_papers < 1:
        checks.append(PreflightCheck("max_papers", "fail", "文献数必须大于 0", action="设置 max_papers >= 1。"))
    else:
        checks.append(PreflightCheck("max_papers", "pass", "文献数配置有效", str(literature.max_papers)))
    if literature.max_search_queries < 1:
        checks.append(PreflightCheck("max_search_queries", "fail", "检索式数量必须大于 0", action="设置 max_search_queries >= 1。"))
    else:
        checks.append(PreflightCheck("max_search_queries", "pass", "检索式数量配置有效", str(literature.max_search_queries)))
    if literature.seed_papers:
        checks.append(PreflightCheck("seed_papers", "pass", "人工种子文献已配置", f"{len(literature.seed_papers)} entries"))
        strong_seed_count = _strong_seed_count(literature.seed_papers)
        if strong_seed_count and literature.provider in {"online", "auto"}:
            checks.append(PreflightCheck("seed_metadata", "pass", "将尝试解析 seed 元数据", f"{strong_seed_count} DOI/URL entries"))
        elif strong_seed_count:
            checks.append(PreflightCheck("seed_metadata", "skipped", "离线模式不联网解析 seed 元数据", action="如需自动补全题录，使用 online 或 auto 文献模式。"))
        if strong_seed_count < len(literature.seed_papers):
            checks.append(
                PreflightCheck(
                    "seed_papers_quality",
                    "warn",
                    "部分人工 seed 缺少 DOI/URL，元数据和去重可能不稳定",
                    f"{strong_seed_count}/{len(literature.seed_papers)} strong entries",
                    "正式 run 优先填写 DOI 或 URL；标题 seed 建议只作为补充线索。",
                )
            )
        if len(literature.seed_papers) >= 3:
            checks.append(_seed_role_coverage_check(literature.seed_papers))
        if len(literature.seed_papers) > literature.max_papers:
            checks.append(PreflightCheck("seed_papers_limit", "warn", "人工种子文献数量超过文献数上限", action="增大 max_papers，避免部分种子文献被截断。"))
    else:
        checks.append(PreflightCheck("seed_papers", "skipped", "未配置人工种子文献"))
    if literature.fulltext_paths:
        from .fulltext_corpus import fulltext_collection_issues, inspect_fulltext_path

        invalid = fulltext_collection_issues(literature.fulltext_paths, Path.cwd()) + [
            warning
            for value in literature.fulltext_paths
            for _path, status, warning in [inspect_fulltext_path(value, Path.cwd())]
            if status != "ok"
        ]
        if invalid:
            checks.append(
                PreflightCheck(
                    "fulltext_paths",
                    "fail",
                    "存在越界、不可读取或超限的本地全文路径",
                    "; ".join(invalid),
                    "将文件放入项目 fulltext/ 或 benchmarks/，或通过 RESEARCH_AGENT_FULLTEXT_ROOTS 显式加入目录，并移除符号链接/非普通文件。",
                )
            )
        else:
            checks.append(PreflightCheck("fulltext_paths", "pass", "本地全文路径可读取", f"{len(literature.fulltext_paths)} files"))
    else:
        checks.append(PreflightCheck("fulltext_paths", "skipped", "未配置本地全文语料"))
    unknown_sources = [source for source in literature.sources if source.strip().lower() not in KNOWN_LITERATURE_SOURCES]
    if unknown_sources:
        checks.append(PreflightCheck("literature_sources", "warn", "存在未知文献源", ", ".join(unknown_sources), "未知源会被跳过。"))
    else:
        checks.append(PreflightCheck("literature_sources", "pass", "在线文献源可识别", ", ".join(literature.sources) or "none"))
    if literature.provider in {"online", "auto"}:
        source_values = {source.lower() for source in literature.sources}
        semantic_key = _resolved(literature.semantic_scholar_api_key, literature.semantic_scholar_api_key_env, "")
        openalex_key = _resolved(literature.openalex_api_key, literature.openalex_api_key_env, "")
        contact_email = _resolved(literature.contact_email, literature.contact_email_env, "")
        if "semantic_scholar" in source_values:
            if semantic_key and _placeholder_secret(semantic_key):
                status = "fail" if config.paper_grade.enabled else "warn"
                checks.append(
                    PreflightCheck(
                        "semantic_scholar_key",
                        status,
                        "paper-grade run 的 Semantic Scholar API key 是占位值" if config.paper_grade.enabled else "Semantic Scholar API key 是占位值，将不会发送给文献源",
                        "已隐藏",
                        f"设置真实 {literature.semantic_scholar_api_key_env}；不要把占位 key 留在正式配置里。",
                    )
                )
            elif semantic_key:
                checks.append(PreflightCheck("semantic_scholar_key", "pass", "Semantic Scholar API key 已配置", "已隐藏"))
            else:
                checks.append(
                    PreflightCheck(
                        "semantic_scholar_key",
                        "warn",
                        "Semantic Scholar API key 未配置",
                        action=f"高频检索建议设置 {literature.semantic_scholar_api_key_env} 或在 Web 表单填写，否则容易 429。",
                    )
                )
        if "openalex" in source_values:
            if openalex_key and _placeholder_secret(openalex_key):
                status = "fail" if config.paper_grade.enabled else "warn"
                checks.append(
                    PreflightCheck(
                        "openalex_key",
                        status,
                        "paper-grade run 的 OpenAlex API key 是占位值" if config.paper_grade.enabled else "OpenAlex API key 是占位值，将不会发送给文献源",
                        "已隐藏",
                        f"设置真实 {literature.openalex_api_key_env}；不要把占位 key 留在正式配置里。",
                    )
                )
            elif openalex_key:
                checks.append(PreflightCheck("openalex_key", "pass", "OpenAlex API key 已配置", "已隐藏"))
            else:
                checks.append(PreflightCheck("openalex_key", "skipped", "OpenAlex API key 未配置", action=f"如有付费/高频配额，可设置 {literature.openalex_api_key_env} 或在 Web 表单填写。"))
        if source_values & {"openalex", "crossref", "pubmed"}:
            if contact_email and not _valid_contact_email(contact_email):
                status = "fail" if config.paper_grade.enabled else "warn"
                checks.append(
                    PreflightCheck(
                        "contact_email",
                        status,
                        "paper-grade run 的联系邮箱是占位值或格式不合法" if config.paper_grade.enabled else "联系邮箱是占位值或格式不合法，将不会发送给文献源",
                        "已隐藏",
                        f"设置真实 {literature.contact_email_env}；不要使用 example.org、example.com 或 <contact-email> 占位符。",
                    )
                )
            elif contact_email:
                checks.append(PreflightCheck("contact_email", "pass", "文献源联系邮箱已配置", _redact_email(contact_email)))
            elif config.paper_grade.enabled:
                checks.append(
                    PreflightCheck(
                        "contact_email",
                        "fail",
                        "paper-grade run 缺少文献源联系邮箱",
                        action=f"设置真实 {literature.contact_email_env} 或在 Web 表单填写，OpenAlex/Crossref/PubMed 请求更稳定。",
                    )
                )
            else:
                checks.append(
                    PreflightCheck(
                        "contact_email",
                        "warn",
                        "联系邮箱未配置",
                        action=f"建议设置 {literature.contact_email_env} 或在 Web 表单填写，OpenAlex/Crossref/PubMed 更稳定。",
                    )
                )
    return checks


def _execution_checks(config: AgentConfig) -> list[PreflightCheck]:
    execution = config.execution
    checks: list[PreflightCheck] = []
    if execution.mode not in {"simulated", "local", "benchmark"}:
        checks.append(PreflightCheck("execution_mode", "fail", f"不支持的执行模式: {execution.mode}", action="使用 simulated、local 或 benchmark。"))
    else:
        checks.append(PreflightCheck("execution_mode", "pass", "执行模式可用", execution.mode))
    if execution.repeats < 1:
        checks.append(PreflightCheck("execution_repeats", "fail", "重复次数必须大于 0", action="设置 repeats >= 1。"))
    else:
        checks.append(PreflightCheck("execution_repeats", "pass", "重复次数有效", str(execution.repeats)))
    if execution.mode in {"local", "benchmark"} and not execution.allowed_commands:
        checks.append(PreflightCheck("allowed_commands", "fail", "本地执行缺少命令白名单", action="至少允许 python3 或明确的实验命令。"))
    elif execution.mode in {"local", "benchmark"}:
        checks.append(PreflightCheck("allowed_commands", "pass", "命令白名单已配置", ", ".join(execution.allowed_commands)))
    if execution.mode == "benchmark":
        if not execution.benchmark_manifest_paths:
            checks.append(PreflightCheck("benchmark_manifests", "fail", "benchmark 模式缺少 manifest", action="配置 benchmark_manifest_paths 或在 Web 表单填写 Benchmark Manifest。"))
        else:
            missing = [value for value in execution.benchmark_manifest_paths if not Path(value).expanduser().exists()]
            if missing:
                checks.append(PreflightCheck("benchmark_manifests", "fail", "存在不可读取的 benchmark manifest", ", ".join(missing), "修正路径或删除无效项。"))
            else:
                checks.append(PreflightCheck("benchmark_manifests", "pass", "benchmark manifest 可读取", f"{len(execution.benchmark_manifest_paths)} files"))
                checks.extend(_benchmark_manifest_content_checks(config))
    return checks


def _release_checks(config: AgentConfig) -> list[PreflightCheck]:
    release = config.release
    configured = [
        release.code_repository_url,
        release.code_archive_doi,
        release.code_license,
        release.code_version,
        release.data_repository_url,
        release.data_archive_doi,
        release.data_access_statement,
        release.environment_url,
        release.release_notes,
    ]
    count = sum(1 for item in configured if str(item).strip())
    if count == 0:
        return [PreflightCheck("release_metadata", "warn", "未配置发布元数据", action="投稿前建议填写代码仓库、许可证、归档 DOI 和数据访问说明。")]
    checks = [PreflightCheck("release_metadata", "pass", "已配置发布元数据字段", f"{count} fields")]
    for name, value in [
        ("release_code_repository_url", release.code_repository_url),
        ("release_data_repository_url", release.data_repository_url),
        ("release_environment_url", release.environment_url),
    ]:
        if value and not _looks_like_url(value):
            checks.append(PreflightCheck(name, "fail", "URL 格式不合法", value, "使用 http(s) URL。"))
    for name, value in [
        ("release_code_archive_doi", release.code_archive_doi),
        ("release_data_archive_doi", release.data_archive_doi),
    ]:
        if value and not (_looks_like_doi(value) or _looks_like_url(value)):
            checks.append(PreflightCheck(name, "fail", "DOI/URL 格式不合法", value, "使用 DOI（10.xxxx/xxx）或 http(s) 稳定链接。"))
    return checks


def _paper_grade_checks(config: AgentConfig) -> list[PreflightCheck]:
    paper_grade = config.paper_grade
    if not paper_grade.enabled:
        return [PreflightCheck("paper_grade_mode", "skipped", "未启用 paper-grade 启动门槛")]
    literature = config.literature
    execution = config.execution
    checks = [PreflightCheck("paper_grade_mode", "pass", "已启用 paper-grade 启动门槛")]
    if literature.provider in {"online", "auto"}:
        checks.append(PreflightCheck("paper_grade_literature_provider", "pass", "paper-grade 文献使用 online/auto", literature.provider))
    else:
        checks.append(
            PreflightCheck(
                "paper_grade_literature_provider",
                "fail",
                "paper-grade 文献必须使用 online/auto",
                literature.provider,
                "设置 literature.provider=online 或 auto。",
            )
        )
    known_sources = _known_configured_sources(literature.sources)
    if len(known_sources) >= paper_grade.min_literature_sources:
        checks.append(
            PreflightCheck(
                "paper_grade_literature_sources",
                "pass",
                "paper-grade 文献源数量达标",
                f"{len(known_sources)}/{paper_grade.min_literature_sources} sources",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "paper_grade_literature_sources",
                "fail",
                f"paper-grade 至少需要 {paper_grade.min_literature_sources} 个可识别在线来源",
                f"{len(known_sources)}/{paper_grade.min_literature_sources}: {', '.join(known_sources) or 'none'}",
                f"配置 semantic_scholar、openalex、arxiv、crossref、pubmed 中至少 {paper_grade.min_literature_sources} 个来源。",
            )
        )
    strong_seed_count = _strong_seed_count(literature.seed_papers)
    if len(literature.seed_papers) >= paper_grade.min_seed_papers and strong_seed_count >= paper_grade.min_doi_url_seed_papers:
        checks.append(
            PreflightCheck(
                "paper_grade_seed_papers",
                "pass",
                "paper-grade DOI/URL seed 数量达标",
                f"strong={strong_seed_count}/{paper_grade.min_doi_url_seed_papers}; total={len(literature.seed_papers)}/{paper_grade.min_seed_papers}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "paper_grade_seed_papers",
                "fail",
                f"paper-grade 至少需要 {paper_grade.min_seed_papers} 条 seed 且其中 {paper_grade.min_doi_url_seed_papers} 条为 DOI/URL",
                f"strong={strong_seed_count}/{paper_grade.min_doi_url_seed_papers}; total={len(literature.seed_papers)}/{paper_grade.min_seed_papers}",
                f"补齐至少 {paper_grade.min_doi_url_seed_papers} 条 DOI 或 URL seed；标题-only seed 只能作为补充线索。",
            )
        )
    seed_roles = _covered_seed_roles(literature.seed_papers)
    if len(seed_roles) >= paper_grade.min_curated_seed_roles:
        checks.append(PreflightCheck("paper_grade_seed_roles", "pass", "paper-grade seed 角色覆盖达标", ", ".join(seed_roles)))
    else:
        checks.append(
            PreflightCheck(
                "paper_grade_seed_roles",
                "fail",
                f"paper-grade seed 至少覆盖 {paper_grade.min_curated_seed_roles} 类文献角色",
                ", ".join(seed_roles) or "none",
                f"seed 简短题名/备注至少覆盖 review/survey、benchmark/dataset、baseline/method、recent work 中 {paper_grade.min_curated_seed_roles} 类。",
            )
        )
    if execution.mode == "benchmark":
        checks.append(PreflightCheck("paper_grade_execution_mode", "pass", "paper-grade 使用 benchmark 执行模式"))
    else:
        checks.append(
            PreflightCheck(
                "paper_grade_execution_mode",
                "fail",
                "paper-grade 必须使用 benchmark 执行模式",
                execution.mode,
                "设置 execution.mode=benchmark，并配置真实 benchmark manifest。",
            )
        )
    if execution.repeats >= paper_grade.min_execution_repeats:
        checks.append(PreflightCheck("paper_grade_execution_repeats", "pass", "paper-grade 重复次数达标", str(execution.repeats)))
    else:
        checks.append(
            PreflightCheck(
                "paper_grade_execution_repeats",
                "fail",
                f"paper-grade 至少需要 repeats >= {paper_grade.min_execution_repeats}",
                str(execution.repeats),
                f"设置 execution.repeats >= {paper_grade.min_execution_repeats}。",
            )
        )
    checks.extend(_paper_grade_manifest_checks(config, paper_grade.min_benchmark_roles, paper_grade.min_execution_repeats))
    return checks


def _paper_grade_manifest_checks(config: AgentConfig, min_roles: int, min_repeats: int) -> list[PreflightCheck]:
    execution = config.execution
    required_repeats = max(1, int(min_repeats or 0))
    if execution.mode != "benchmark" or not execution.benchmark_manifest_paths:
        return [
            PreflightCheck(
                "paper_grade_benchmark_manifests",
                "fail",
                "paper-grade 需要 candidate/baseline/ablation benchmark manifest",
                "none",
                "配置真实 benchmark_manifest_paths，至少覆盖 candidate、baseline、ablation。",
            )
        ]
    report = audit_benchmark_adapter_config(execution, paper_grade=config.paper_grade)
    roles = {str(record.role or "") for record in report.adapters if record.status == "ready"}
    missing_roles = [role for role in ["candidate", "baseline", "ablation"] if role not in roles]
    provenance_issues = _paper_grade_manifest_provenance_issues(report.adapters)
    if not missing_roles and len(roles & {"candidate", "baseline", "ablation"}) >= min_roles and report.paper_grade_status == "ready" and not provenance_issues:
        return [PreflightCheck("paper_grade_benchmark_manifests", "pass", "paper-grade benchmark manifest 集合达标", f"roles={','.join(sorted(roles))}")]
    issues = [*report.paper_grade_issues[:4], *provenance_issues[:4]]
    if missing_roles:
        issues.append("missing_roles=" + ",".join(missing_roles))
    return [
        PreflightCheck(
            "paper_grade_benchmark_manifests",
            "fail",
            "paper-grade benchmark manifest 集合未达标",
            "；".join(issues) or f"status={report.paper_grade_status or '-'}",
            f"补齐 candidate/baseline/ablation 三类 ready manifest、共享 expected_metrics、min_repeats/repeats>={required_repeats}，并填写公开 http(s) dataset_url/benchmark_url、license、baseline_version 和 citation。",
        )
    ]


def _paper_grade_manifest_provenance_issues(records: list[Any]) -> list[str]:
    issues: list[str] = []
    for record in records:
        if str(getattr(record, "status", "") or "") != "ready":
            continue
        role = str(getattr(record, "role", "") or "")
        if role not in {"candidate", "baseline", "ablation"}:
            continue
        name = str(getattr(record, "name", "") or role)
        record_issues = getattr(record, "provenance_issues", None)
        if isinstance(record_issues, list):
            issues.extend(str(item) for item in record_issues if str(item).strip())
            continue
        issues.extend(
            formal_benchmark_provenance_issues(
                name=name,
                benchmark_kind=str(getattr(record, "benchmark_kind", "") or ""),
                benchmark_url=str(getattr(record, "benchmark_url", "") or ""),
                dataset_url=str(getattr(record, "dataset_url", "") or ""),
                dataset_version=str(getattr(record, "dataset_version", "") or ""),
                split_name=str(getattr(record, "split_name", "") or ""),
                split_sha256=str(getattr(record, "split_sha256", "") or ""),
                split_sha256_actual=str(getattr(record, "split_sha256_actual", "") or ""),
                license_value=str(getattr(record, "license", "") or ""),
                baseline_version=str(getattr(record, "baseline_version", "") or ""),
                citation=str(getattr(record, "citation", "") or ""),
            )
        )
    return issues


def _benchmark_manifest_content_checks(config: AgentConfig) -> list[PreflightCheck]:
    report = audit_benchmark_adapter_config(config.execution, paper_grade=config.paper_grade)
    checks: list[PreflightCheck] = []
    if report.status == "ready":
        checks.append(PreflightCheck("benchmark_adapter_audit", "pass", "benchmark manifest 内容可执行", f"{len(report.commands)} commands"))
    else:
        detail = "；".join(report.blocking_issues[:4])
        checks.append(
            PreflightCheck(
                "benchmark_adapter_audit",
                "fail",
                "benchmark manifest 内容审计未通过",
                detail,
                "修复 manifest 命令、source_files、metrics_path、expected_artifacts 或 allowed_commands。",
            )
        )
    for record in report.adapters[:6]:
        checks.append(
            PreflightCheck(
                f"benchmark_adapter:{record.name}",
                "pass" if record.status == "ready" else "fail",
                f"adapter {record.status}",
                " ".join(record.command) or record.manifest_path,
                "；".join(record.issues[:3]) if record.issues else "-",
            )
        )
    return checks


def _run_memory_checks(config: AgentConfig, run_memory: Any | None) -> list[PreflightCheck]:
    if run_memory is None:
        return []
    status = str(getattr(run_memory, "status", "") or "")
    signals = getattr(run_memory, "recurring_signals", [])
    if not isinstance(signals, list):
        return []
    checks: list[PreflightCheck] = []
    categories = {str(getattr(signal, "category", "") or "") for signal in signals}
    if status in {"needs_process_repair", "has_carry_forward_work"}:
        checks.append(
            PreflightCheck(
                "run_memory_status",
                "warn",
                "历史 run 存在可继承风险",
                f"{status}; signals={len(signals)}",
                "启动前查看 runs-memory.md，把高频问题转成当前表单配置或人工 seed。",
            )
        )
    elif status == "stable":
        checks.append(PreflightCheck("run_memory_status", "pass", "历史 run 暂无明显可继承风险"))
    elif status == "empty":
        checks.append(PreflightCheck("run_memory_status", "skipped", "暂无历史 run 可用于复盘"))

    if categories & {"literature_repair", "thin_evidence_pool"}:
        checks.extend(_memory_literature_checks(config))
    feedback_signal = next((signal for signal in signals if str(getattr(signal, "category", "") or "") == "literature_search_feedback"), None)
    if feedback_signal is not None:
        checks.extend(_memory_literature_search_feedback_checks(config, feedback_signal))
    rescue_execution_signal = next((signal for signal in signals if str(getattr(signal, "category", "") or "") == "literature_rescue_execution"), None)
    if rescue_execution_signal is not None:
        checks.extend(_memory_literature_rescue_execution_checks(config, rescue_execution_signal))
    source_health_signal = next((signal for signal in signals if str(getattr(signal, "category", "") or "") == "literature_source_health"), None)
    if source_health_signal is not None:
        checks.extend(_memory_literature_source_health_checks(config, source_health_signal))
    if "llm_configuration" in categories:
        checks.extend(_memory_llm_checks(config))
    if "llm_trace_audit" in categories:
        checks.extend(_memory_llm_trace_checks(config))
    if "run_economics" in categories:
        checks.extend(_memory_run_economics_checks(config))
    if "agent_observability" in categories:
        checks.extend(_memory_observability_checks(config))
    open_source_signal = next((signal for signal in signals if str(getattr(signal, "category", "") or "") == "open_source_compliance"), None)
    if open_source_signal is not None:
        checks.extend(_memory_open_source_compliance_checks(config, open_source_signal))
    if "agent_stage_contract" in categories:
        checks.extend(_memory_stage_contract_checks(config))
    if "research_scorecard" in categories:
        checks.extend(_memory_scorecard_checks(config))
    if "run_integrity_audit" in categories:
        checks.extend(_memory_integrity_checks(config))
    if "repair_resolution_audit" in categories:
        checks.extend(_memory_repair_resolution_checks(config))
    if categories & {"result_validation", "failure_or_negative_results"}:
        checks.extend(_memory_experiment_checks(config))
    if categories & {"experiment_manager", "experiment_manager_smoke_first", "experiment_branch_backlog"}:
        checks.extend(_memory_experiment_manager_checks(config, categories))
    if categories & {"review_constraints", "human_brief_constraints"}:
        checks.extend(_memory_human_constraints_checks(config))
    if categories & {"simulated_evidence", "benchmark_gap"}:
        checks.extend(_memory_benchmark_checks(config))
    if "benchmark_result_schema" in categories:
        checks.extend(_memory_benchmark_schema_checks(config))
    if "environment_snapshot" in categories:
        checks.extend(_memory_environment_checks(config))
    if "release_metadata" in categories:
        checks.extend(_memory_release_checks(config))
    return checks


def _memory_literature_checks(config: AgentConfig) -> list[PreflightCheck]:
    literature = config.literature
    checks: list[PreflightCheck] = []
    if literature.provider == "offline":
        checks.append(
            PreflightCheck(
                "memory_literature_provider",
                "warn",
                "历史 run 反复出现文献证据薄弱，当前仍是离线模式",
                action="下一次正式 run 建议使用 online/auto，并补人工 seed_papers。",
            )
        )
    elif literature.provider in {"online", "auto"}:
        checks.append(PreflightCheck("memory_literature_provider", "pass", "当前文献模式已响应历史复盘", literature.provider))
    if literature.max_papers < 12:
        checks.append(
            PreflightCheck(
                "memory_max_papers",
                "warn",
                "历史 run 文献池偏薄，当前 max_papers 仍偏小",
                str(literature.max_papers),
                "建议设置 max_papers >= 12，或至少加入高相关人工种子文献。",
            )
        )
    if not literature.seed_papers:
        checks.append(
            PreflightCheck(
                "memory_seed_papers",
                "warn",
                "历史 run 提示需要人工 seed，但当前未填写",
                action="至少提供 3 篇高相关 DOI/URL seed，避免检索结果漂移。",
            )
        )
    elif _strong_seed_count(literature.seed_papers) < 3:
        strong_seed_count = _strong_seed_count(literature.seed_papers)
        checks.append(
            PreflightCheck(
                "memory_seed_papers",
                "warn",
                "历史 run 提示需要至少 3 篇强 seed，当前 DOI/URL seed 不足",
                f"{strong_seed_count}/3 strong entries; total={len(literature.seed_papers)}",
                "补 3 篇以上高相关 DOI/URL，至少覆盖综述、benchmark/dataset 和 baseline/method。",
            )
        )
    else:
        checks.append(PreflightCheck("memory_seed_papers", "pass", "已配置足够强 seed_papers", f"{_strong_seed_count(literature.seed_papers)} DOI/URL entries"))
        checks.append(_memory_seed_role_coverage_check(literature.seed_papers))
    return checks


def _memory_literature_search_feedback_checks(config: AgentConfig, signal: Any) -> list[PreflightCheck]:
    literature = config.literature
    evidence = "; ".join(str(item) for item in (getattr(signal, "evidence", []) or [])[:1])
    checks: list[PreflightCheck] = []
    if literature.provider in {"online", "auto"}:
        checks.append(PreflightCheck("memory_search_feedback_provider", "pass", "当前文献模式可执行历史检索反馈", literature.provider))
    else:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_provider",
                "warn",
                "历史 search feedback 要求补检索，当前仍是离线模式",
                evidence,
                "切换为 online/auto，或在 approval notes 中说明为何用人工 seed/fulltext 替代在线补检索。",
            )
        )
    if literature.extra_search_queries:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_queries",
                "pass",
                "当前已填写补充检索式，可承接历史 search feedback",
                f"{len(literature.extra_search_queries)} queries",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_queries",
                "warn",
                "历史 search feedback 含推荐检索式，当前未填写补充检索式",
                evidence,
                "打开上一轮 01-literature-search-feedback.md，把推荐 query 粘到“补充检索式”后再预检。",
            )
        )
    if literature.max_papers >= 12 and literature.max_search_queries >= 6:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_capacity",
                "pass",
                "当前文献容量已响应历史 next_run_config",
                f"max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_capacity",
                "warn",
                "历史 search feedback 建议扩大候选池，当前容量偏小",
                f"max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}",
                "建议 max_papers >= 12 且 max_search_queries >= 6，避免仍由少量弱题录决定排序。",
            )
        )
    known_sources = [source for source in literature.sources if source in KNOWN_LITERATURE_SOURCES]
    if len(set(known_sources)) >= 3:
        checks.append(PreflightCheck("memory_search_feedback_sources", "pass", "当前文献源保留多源兜底", ", ".join(known_sources)))
    else:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_sources",
                "warn",
                "历史 search feedback 提示 source/query 修复，当前文献源过少",
                ", ".join(literature.sources) or "-",
                "至少保留 openalex、arxiv、crossref；Semantic Scholar 有 key 时再加入 semantic_scholar。",
            )
        )
    if len(literature.seed_papers) >= 3:
        checks.append(PreflightCheck("memory_search_feedback_seed_targets", "pass", "当前 seed_papers 数量可响应历史 seed 目标", f"{len(literature.seed_papers)} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_search_feedback_seed_targets",
                "warn",
                "历史 search feedback 要求补 seed 目标，当前 seed_papers 不足",
                f"{len(literature.seed_papers)} entries",
                "补 3 篇以上高相关 DOI/URL，至少覆盖综述、benchmark/dataset 和 baseline/method。",
            )
        )
    return checks


def _memory_literature_rescue_execution_checks(config: AgentConfig, signal: Any) -> list[PreflightCheck]:
    literature = config.literature
    evidence = "; ".join(str(item) for item in (getattr(signal, "evidence", []) or [])[:1])
    checks: list[PreflightCheck] = []
    if literature.provider in {"online", "auto"}:
        checks.append(PreflightCheck("memory_rescue_execution_provider", "pass", "当前文献模式可重跑未闭环补检索", literature.provider))
    else:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_provider",
                "warn",
                "历史补检索执行未改善候选池，当前仍是离线模式",
                evidence,
                "切换为 online/auto；若必须离线，需要补 DOI/URL seed 和 fulltext_paths 替代在线补检索。",
            )
        )
    if literature.extra_search_queries:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_queries",
                "pass",
                "当前已填写新补充检索式，可替换历史低收益 query",
                f"{len(literature.extra_search_queries)} queries",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_queries",
                "warn",
                "历史补检索 query 未闭环，当前未填写替代检索式",
                evidence,
                "从 01-literature-coverage 的 suggested_queries 或人工 seed 生成更具体英文 query，填入“补充检索式”。",
            )
        )
    known_sources = [source for source in literature.sources if source in KNOWN_LITERATURE_SOURCES]
    if len(set(known_sources)) >= 3:
        checks.append(PreflightCheck("memory_rescue_execution_sources", "pass", "当前文献源足以重试补检索", ", ".join(known_sources)))
    else:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_sources",
                "warn",
                "历史补检索执行未改善候选池，当前文献源过少",
                ", ".join(literature.sources) or "-",
                "至少保留 openalex、arxiv、crossref；Semantic Scholar 有 key 时再加入。",
            )
        )
    if literature.max_papers >= 12 and literature.max_search_queries >= 6:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_capacity",
                "pass",
                "当前文献容量可重新评估未闭环补检索",
                f"max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_capacity",
                "warn",
                "历史补检索未带来新增候选，当前检索容量仍偏小",
                f"max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}",
                "建议 max_papers >= 12 且 max_search_queries >= 6，避免新 query 没有足够候选空间。",
            )
        )
    if len(literature.seed_papers) >= 3:
        checks.append(PreflightCheck("memory_rescue_execution_seed_papers", "pass", "当前 seed_papers 可辅助修复未闭环 query", f"{len(literature.seed_papers)} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_rescue_execution_seed_papers",
                "warn",
                "历史补检索未闭环，当前缺少人工 DOI/URL seed",
                f"{len(literature.seed_papers)} entries",
                "补 3 篇以上强相关 DOI/URL，覆盖 benchmark/dataset、baseline/method 和近期研究。",
            )
        )
    return checks


def _memory_literature_source_health_checks(config: AgentConfig, signal: Any) -> list[PreflightCheck]:
    literature = config.literature
    evidence = "; ".join(str(item) for item in (getattr(signal, "evidence", []) or [])[:1])
    evidence_lower = evidence.lower()
    source_values = {source.strip().lower() for source in literature.sources if source.strip()}
    known_sources = sorted(source for source in source_values if source in KNOWN_LITERATURE_SOURCES)
    semantic_key = _resolved(literature.semantic_scholar_api_key, literature.semantic_scholar_api_key_env, "")
    contact_email = _resolved(literature.contact_email, literature.contact_email_env, "")
    checks: list[PreflightCheck] = []
    if literature.provider in {"online", "auto"}:
        checks.append(PreflightCheck("memory_source_health_provider", "pass", "当前文献模式可重跑历史文献源健康检查", literature.provider))
    else:
        checks.append(
            PreflightCheck(
                "memory_source_health_provider",
                "warn",
                "历史文献源存在限流/失败，当前仍是离线模式",
                evidence,
                "切换为 online/auto，并在批准 idea/实验前重跑文献源健康检查。",
            )
        )
    if len(known_sources) >= 3:
        checks.append(PreflightCheck("memory_source_health_sources", "pass", "当前保留多源文献兜底", ", ".join(known_sources)))
    else:
        checks.append(
            PreflightCheck(
                "memory_source_health_sources",
                "warn",
                "历史文献源健康不稳定，当前可用文献源过少",
                ", ".join(literature.sources) or "-",
                "至少保留 openalex、arxiv、crossref；Semantic Scholar 有 key 时再加入。",
            )
        )
    if literature.max_papers >= 12 and literature.max_search_queries >= 6:
        checks.append(
            PreflightCheck(
                "memory_source_health_capacity",
                "pass",
                "当前文献检索容量可覆盖历史 source health 修复",
                f"max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_source_health_capacity",
                "warn",
                "历史文献源健康不稳定，当前候选池/检索式容量偏小",
                f"max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}",
                "建议 max_papers >= 12 且 max_search_queries >= 6，避免少量失败 query 决定整轮结果。",
            )
        )
    if "semantic_scholar" in source_values:
        if semantic_key and _placeholder_secret(semantic_key):
            checks.append(
                PreflightCheck(
                    "memory_source_health_semantic_scholar_key",
                    "warn",
                    "历史文献源健康提示 Semantic Scholar 风险，但当前 API key 是占位值",
                    "已隐藏",
                    f"设置真实 {literature.semantic_scholar_api_key_env}；占位 key 不会发送给文献源。",
                )
            )
        elif semantic_key:
            checks.append(PreflightCheck("memory_source_health_semantic_scholar_key", "pass", "Semantic Scholar API key 已配置，可缓解历史 429", "已隐藏"))
        else:
            checks.append(
                PreflightCheck(
                    "memory_source_health_semantic_scholar_key",
                    "warn",
                    "历史文献源健康提示 Semantic Scholar 风险，当前未配置 API key",
                    evidence,
                    f"设置 {literature.semantic_scholar_api_key_env} 或在 Web 表单填写；否则暂时移除 semantic_scholar 并保留其他来源。",
                )
            )
    elif "semantic_scholar" in evidence_lower:
        checks.append(
            PreflightCheck(
                "memory_source_health_semantic_scholar_key",
                "skipped",
                "历史 Semantic Scholar 出现限流，本轮未启用该源",
                action="有 API key 后再加入 semantic_scholar；否则保持 OpenAlex/arXiv/Crossref 兜底。",
            )
            )
    if source_values & {"openalex", "crossref", "pubmed"}:
        if contact_email and not _valid_contact_email(contact_email):
            checks.append(
                PreflightCheck(
                    "memory_source_health_contact_email",
                    "warn",
                    "历史文献源健康不稳定，但当前联系邮箱是占位值或格式不合法",
                    "已隐藏",
                    f"设置真实 {literature.contact_email_env}；占位邮箱不会发送给文献源。",
                )
            )
        elif contact_email:
            checks.append(PreflightCheck("memory_source_health_contact_email", "pass", "文献源联系邮箱已配置，可提升历史故障源稳定性", _redact_email(contact_email)))
        else:
            checks.append(
                PreflightCheck(
                    "memory_source_health_contact_email",
                    "warn",
                    "历史文献源健康不稳定，当前未配置联系邮箱",
                    evidence,
                    f"设置 {literature.contact_email_env} 或在 Web 表单填写，OpenAlex/Crossref/PubMed 请求更稳定。",
                )
            )
    return checks


def _memory_llm_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    model = _resolved(llm.model, llm.model_env, "")
    base_url = _resolved(llm.base_url, llm.base_url_env, "https://api.openai.com/v1")
    if model and base_url:
        return [PreflightCheck("memory_llm_config", "pass", "当前 LLM 配置已响应历史失败", f"{_redact_url(base_url)} / {model}")]
    return [
        PreflightCheck(
            "memory_llm_config",
            "warn",
            "历史 run 出现 LLM 配置失败，当前配置仍需确认",
            action="启动前固定可用的 model/base_url/api_key 组合，并先运行预检。",
        )
    ]


def _memory_open_source_compliance_checks(config: AgentConfig, signal: Any | None = None) -> list[PreflightCheck]:
    llm = config.llm
    literature = config.literature
    human = config.human
    execution = config.execution
    release = config.release
    model = _resolved(llm.model, llm.model_env, "")
    base_url = _resolved(llm.base_url, llm.base_url_env, "https://api.openai.com/v1")
    lesson_ids = _open_source_lesson_ids(signal)
    lesson_id_list = sorted(lesson_ids)
    checks: list[PreflightCheck] = []
    if lesson_ids:
        checks.append(
            PreflightCheck(
                "memory_open_source_contract_lessons",
                "pass",
                "历史 open-source lessons 已前置为本次启动检查",
                ", ".join(lesson_id_list[:8]),
            )
        )
    if model and base_url and (llm.max_calls == 0 or llm.max_calls >= 8):
        detail = "unlimited" if llm.max_calls == 0 else str(llm.max_calls)
        checks.append(PreflightCheck("memory_open_source_compliance_llm", "pass", "当前 LLM 配置可响应外部项目 trace/成本约束", f"{_redact_url(base_url)} / {model}; calls={detail}"))
    else:
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_llm",
                "warn",
                "历史 open-source compliance 提示 LLM trace/预算约束未闭环",
                f"model={'set' if model else 'missing'}; max_calls={llm.max_calls}",
                "固定可用 model/base_url/api_key；端到端正式 run 建议 llm_max_calls 为 0 或 >= 8。",
            )
        )
    if not lesson_ids or lesson_ids & {"runtime_cost_observability", "ai_use_disclosure"}:
        trace_ready = bool(model and base_url and (llm.max_calls == 0 or llm.max_calls >= 8) and (llm.max_prompt_chars == 0 or llm.max_prompt_chars >= 20000))
        cost_ready = llm.input_cost_per_million_tokens > 0 and llm.output_cost_per_million_tokens > 0
        if trace_ready and cost_ready:
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_runtime_trace",
                    "pass",
                    "当前配置可响应 AgentLaboratory/MLAgentBench 式运行轨迹与成本契约",
                    f"calls={'unlimited' if llm.max_calls == 0 else llm.max_calls}; prompt={'unlimited' if llm.max_prompt_chars == 0 else llm.max_prompt_chars}; cost=on",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_runtime_trace",
                    "warn",
                    "历史 open-source lesson 指向 LLM ledger/成本/披露缺口",
                    f"trace_ready={trace_ready}; cost_ready={cost_ready}",
                    "正式 run 应固定 model/base_url/api_key，llm_max_calls 设为 0 或 >=8，并填写 input/output token 单价。",
                )
            )
    known_sources = [source for source in literature.sources if source in KNOWN_LITERATURE_SOURCES]
    if literature.provider in {"online", "auto"} and literature.max_papers >= 12 and literature.max_search_queries >= 6 and len(set(known_sources)) >= 3:
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_literature",
                "pass",
                "当前文献配置可响应 PaperQA/OpenScholar 式检索与重排约束",
                f"{literature.provider}; max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}; sources={len(set(known_sources))}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_literature",
                "warn",
                "历史 open-source compliance 提示文献 grounding/query coverage 约束未闭环",
                f"{literature.provider}; max_papers={literature.max_papers}; max_search_queries={literature.max_search_queries}; sources={len(set(known_sources))}",
                "使用 online/auto、max_papers>=12、max_search_queries>=6，并保留至少 3 个已知文献源。",
            )
        )
    if not lesson_ids or lesson_ids & {"query_execution_coverage_audit", "retrieval_rerank_before_synthesis", "citation_grounded_fulltext", "metadata_rate_limit_resilience"}:
        seed_role = _seed_role_coverage_check(literature.seed_papers) if literature.seed_papers else None
        strong_seed_count = _strong_seed_count(literature.seed_papers)
        grounding_ready = (
            literature.provider in {"online", "auto"}
            and literature.max_papers >= 12
            and literature.max_search_queries >= 6
            and len(set(known_sources)) >= 3
            and strong_seed_count >= 3
            and seed_role is not None
            and seed_role.status == "pass"
        )
        if grounding_ready:
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_literature_grounding",
                    "pass",
                    "当前文献配置可响应 PaperQA/OpenScholar 式 query/source、rerank 和 seed 角色契约",
                    f"{literature.provider}; papers={literature.max_papers}; queries={literature.max_search_queries}; strong_seeds={strong_seed_count}; {seed_role.detail if seed_role else ''}",
                )
            )
        else:
            role_detail = seed_role.detail if seed_role is not None else "seed_roles=missing"
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_literature_grounding",
                    "warn",
                    "历史 open-source lesson 指向文献 grounding/query/seed 契约缺口",
                    f"{literature.provider}; papers={literature.max_papers}; queries={literature.max_search_queries}; sources={len(set(known_sources))}; strong_seeds={strong_seed_count}; {role_detail}",
                    "正式 run 使用 online/auto、max_papers>=12、max_search_queries>=6、至少 3 个已知文献源，并填写覆盖 review/benchmark/baseline/recent 中至少 3 类的 DOI/URL seed。",
                )
            )
    human_count = sum(1 for item in [*human.notes, *human.constraints, *human.success_criteria, *human.resource_limits, *human.risks] if str(item).strip())
    if human_count:
        checks.append(PreflightCheck("memory_open_source_compliance_human", "pass", "当前 human brief 可响应 Agent Laboratory 式人工反馈约束", f"{human_count} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_human",
                "warn",
                "历史 open-source compliance 提示人工反馈/约束未落实",
                action="把本轮硬性要求写入 human_constraints、success_criteria 或 resource_limits，避免只靠 prompt 记忆。",
            )
        )
    if not lesson_ids or lesson_ids & {"human_feedback_compliance", "structured_idea_to_experiment_loop"}:
        if human_count:
            checks.append(PreflightCheck("memory_open_source_contract_human_gate", "pass", "当前 human brief 可前置 AgentLaboratory 式人工 gate 约束", f"{human_count} entries"))
        else:
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_human_gate",
                    "warn",
                    "历史 open-source lesson 指向人工 gate/idea->experiment 契约缺口",
                    action="把研究边界、必须比较的 baseline、成功标准和资源限制写入 human brief；review gate 批准前不得进入 idea/实验。",
                )
            )
    if (execution.mode == "benchmark" and execution.allowed_commands and execution.benchmark_manifest_paths) or (execution.mode == "local" and execution.allowed_commands):
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_execution",
                "pass",
                "当前执行配置可响应 AI-Scientist/MLAgentBench 式可复现实验证据约束",
                f"{execution.mode}; commands={len(execution.allowed_commands)}; manifests={len(execution.benchmark_manifest_paths)}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_execution",
                "warn",
                "历史 open-source compliance 提示实验执行/benchmark 约束未闭环",
                f"{execution.mode}; commands={len(execution.allowed_commands)}; manifests={len(execution.benchmark_manifest_paths)}",
                "正式 run 建议使用 local 或 benchmark；benchmark 模式需填写 manifest，并保留 execution approval/runbook/stdout/stderr。",
            )
        )
    if not lesson_ids or lesson_ids & {"benchmark_result_schema_contract", "domain_benchmark_before_claims", "sandbox_generated_code"}:
        benchmark_required = bool(lesson_ids & {"benchmark_result_schema_contract", "domain_benchmark_before_claims"})
        if benchmark_required:
            execution_ready = execution.mode == "benchmark" and bool(execution.allowed_commands) and bool(execution.benchmark_manifest_paths)
        else:
            execution_ready = (
                execution.mode == "benchmark"
                and bool(execution.allowed_commands)
                and bool(execution.benchmark_manifest_paths)
            ) or (execution.mode == "local" and bool(execution.allowed_commands) and execution.repeats >= 5)
        if execution_ready:
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_execution_evidence",
                    "pass",
                    "当前执行配置可响应 AI-Scientist/MLAgentBench 式可复现实验证据契约",
                    f"{execution.mode}; repeats={execution.repeats}; commands={len(execution.allowed_commands)}; manifests={len(execution.benchmark_manifest_paths)}",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "memory_open_source_contract_execution_evidence",
                    "warn",
                    "历史 open-source lesson 指向实验执行/benchmark/schema 契约缺口",
                    f"{execution.mode}; repeats={execution.repeats}; commands={len(execution.allowed_commands)}; manifests={len(execution.benchmark_manifest_paths)}",
                    "正式 run 使用 benchmark manifest；若只用 local，至少 repeats>=5、配置 allowed_commands，并保留 execution approval、runbook、stdout/stderr 和 metrics schema。",
                )
            )
    release_count = sum(
        1
        for item in [
            release.code_repository_url,
            release.code_archive_doi,
            release.code_license,
            release.code_version,
            release.data_repository_url,
            release.data_archive_doi,
            release.data_access_statement,
            release.environment_url,
            release.release_notes,
        ]
        if str(item).strip()
    )
    if release_count:
        checks.append(PreflightCheck("memory_open_source_compliance_release", "pass", "当前 release 元数据可响应 AI disclosure/submission package 约束", f"{release_count} fields"))
    else:
        checks.append(
            PreflightCheck(
                "memory_open_source_compliance_release",
                "warn",
                "历史 open-source compliance 提示投稿披露或归档约束未闭环",
                action="填写代码仓库、许可证、版本、数据访问、环境归档或 release notes，便于 AI disclosure 和投稿包审计。",
            )
        )
    return checks


def _memory_llm_trace_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    model = _resolved(llm.model, llm.model_env, "")
    base_url = _resolved(llm.base_url, llm.base_url_env, "https://api.openai.com/v1")
    checks: list[PreflightCheck] = []
    if model and base_url:
        checks.append(PreflightCheck("memory_llm_trace_config", "pass", "当前 LLM 配置可用于重建历史 trace 缺口", f"{_redact_url(base_url)} / {model}"))
    else:
        checks.append(
            PreflightCheck(
                "memory_llm_trace_config",
                "warn",
                "历史 run 的 LLM trace 审计不完整，当前模型配置仍需确认",
                action="固定可用 model/base_url/api_key，并保留 run-llm-ledger 与 13-llm-trace-audit。",
            )
        )
    if 0 < llm.max_calls < 8:
        checks.append(
            PreflightCheck(
                "memory_llm_trace_budget",
                "warn",
                "历史 run 的关键阶段 LLM trace 不完整，当前调用预算偏低",
                str(llm.max_calls),
                "端到端正式 run 建议 llm_max_calls >= 8，或设为 0 表示不限制；预算不足会造成 trace 缺口。",
            )
        )
    else:
        detail = "unlimited" if llm.max_calls == 0 else str(llm.max_calls)
        checks.append(PreflightCheck("memory_llm_trace_budget", "pass", "当前 LLM 调用预算可覆盖关键科研阶段 trace", detail))
    if 0 < llm.max_prompt_chars < 20000:
        checks.append(
            PreflightCheck(
                "memory_llm_trace_prompt_budget",
                "warn",
                "历史 run 的 LLM trace 审计不完整，当前 prompt 字符预算可能截断关键阶段",
                str(llm.max_prompt_chars),
                "正式 run 建议提高 llm_max_prompt_chars，避免计划、文献和写作阶段被预算拦截。",
            )
        )
    return checks


def _memory_run_economics_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    checks: list[PreflightCheck] = []
    if llm.max_calls == 0:
        checks.append(PreflightCheck("memory_run_economics_call_budget", "pass", "当前 LLM 调用预算不限制，可避免历史调用预算拦截", "unlimited"))
    elif llm.max_calls < 8:
        checks.append(
            PreflightCheck(
                "memory_run_economics_call_budget",
                "warn",
                "历史 run 出现 LLM 成本/预算压力，当前调用预算偏低",
                str(llm.max_calls),
                "端到端正式 run 建议 llm_max_calls >= 8，或设为 0 表示不限制。",
            )
        )
    else:
        checks.append(PreflightCheck("memory_run_economics_call_budget", "pass", "当前 LLM 调用预算可响应历史 economics 复盘", str(llm.max_calls)))
    if llm.max_prompt_chars == 0:
        checks.append(PreflightCheck("memory_run_economics_prompt_budget", "pass", "当前 LLM prompt 预算不限制，可避免历史 prompt 预算拦截", "unlimited"))
    elif llm.max_prompt_chars < 20000:
        checks.append(
            PreflightCheck(
                "memory_run_economics_prompt_budget",
                "warn",
                "历史 run 出现 LLM 成本/预算压力，当前 prompt 字符预算偏低",
                str(llm.max_prompt_chars),
                "正式 run 建议 llm_max_prompt_chars >= 20000，避免文献、计划或写作阶段被预算截断。",
            )
        )
    else:
        checks.append(PreflightCheck("memory_run_economics_prompt_budget", "pass", "当前 LLM prompt 预算可响应历史 economics 复盘", str(llm.max_prompt_chars)))
    if llm.input_cost_per_million_tokens > 0 and llm.output_cost_per_million_tokens > 0:
        checks.append(
            PreflightCheck(
                "memory_run_economics_token_cost",
                "pass",
                "当前 token 单价可用于美元成本估算",
                f"input={llm.input_cost_per_million_tokens}/M output={llm.output_cost_per_million_tokens}/M",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_run_economics_token_cost",
                "warn",
                "历史 run 需要 economics 复盘，当前 token 单价未完整配置",
                action="如需成本趋势，填写 llm.input_cost_per_million_tokens 和 llm.output_cost_per_million_tokens。",
            )
        )
    return checks


def _memory_observability_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    execution = config.execution
    release = config.release
    model = _resolved(llm.model, llm.model_env, "")
    base_url = _resolved(llm.base_url, llm.base_url_env, "https://api.openai.com/v1")
    checks: list[PreflightCheck] = []
    if model and base_url:
        checks.append(PreflightCheck("memory_observability_llm", "pass", "当前 LLM 配置可生成 ledger/trace", f"{_redact_url(base_url)} / {model}"))
    else:
        checks.append(
            PreflightCheck(
                "memory_observability_llm",
                "warn",
                "历史 run 可观测性断链，当前 LLM 配置仍需确认",
                action="固定可用 model/base_url/api_key，确保 run-llm-ledger 能覆盖关键阶段。",
            )
        )
    if execution.mode in {"local", "benchmark"} and not execution.allowed_commands:
        checks.append(
            PreflightCheck(
                "memory_observability_execution_trace",
                "warn",
                "历史 run 可观测性断链，当前本地/benchmark 执行缺少命令白名单",
                action="补 allowed_commands，确保 execution approval、runbook 和 artifact trace 可生成。",
            )
        )
    elif execution.mode == "benchmark" and not execution.benchmark_manifest_paths:
        checks.append(
            PreflightCheck(
                "memory_observability_execution_trace",
                "warn",
                "历史 run 可观测性断链，当前 benchmark 缺少 manifest",
                action="补 benchmark manifest，确保 adapter/runbook/recovery trace 可追踪。",
            )
        )
    else:
        checks.append(PreflightCheck("memory_observability_execution_trace", "pass", "当前执行配置可生成 approval/runbook trace", execution.mode))
    if release.release_notes or release.code_repository_url or release.environment_url:
        checks.append(PreflightCheck("memory_observability_release_trace", "pass", "当前 release 字段可承接归档说明", "configured"))
    else:
        checks.append(
            PreflightCheck(
                "memory_observability_release_trace",
                "warn",
                "历史 run 可观测性断链，当前缺少 release/归档说明",
                action="建议填写 release_notes、代码仓库或环境归档 URL，便于 submission package 解释轨迹和恢复状态。",
            )
        )
    return checks


def _memory_stage_contract_checks(config: AgentConfig) -> list[PreflightCheck]:
    literature = config.literature
    execution = config.execution
    release = config.release
    human = config.human
    checks: list[PreflightCheck] = []
    if literature.provider in {"online", "auto"} and literature.max_papers >= 12 and literature.seed_papers:
        checks.append(
            PreflightCheck(
                "memory_stage_contract_literature",
                "pass",
                "当前文献配置可响应历史 stage contract grounding 缺口",
                f"{literature.provider}; max_papers={literature.max_papers}; seeds={len(literature.seed_papers)}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_stage_contract_literature",
                "warn",
                "历史 stage contract 提示阶段契约缺口，当前文献配置仍偏弱",
                f"{literature.provider}; max_papers={literature.max_papers}; seeds={len(literature.seed_papers)}",
                "正式 run 建议 online/auto、max_papers>=12，并提供高相关 DOI/URL seed_papers。",
            )
        )
    human_count = sum(
        1
        for item in [*human.notes, *human.constraints, *human.success_criteria, *human.resource_limits, *human.risks]
        if str(item).strip()
    )
    if human_count:
        checks.append(PreflightCheck("memory_stage_contract_human_brief", "pass", "当前 human brief 可承接历史 stage contract 约束", f"{human_count} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_stage_contract_human_brief",
                "warn",
                "历史 stage contract 提示人工约束需要前移，当前未填写 human brief",
                action="把硬性限制、验收标准和审核意见写入 human_constraints/resource_limits/success_criteria。",
            )
        )
    if execution.mode == "simulated":
        checks.append(
            PreflightCheck(
                "memory_stage_contract_execution",
                "warn",
                "历史 stage contract 提示执行/证据契约缺口，当前仍是 simulated",
                action="正式 run 使用 local 或 benchmark，并保留 runbook、stdout/stderr、统计和 artifact trace。",
            )
        )
    elif execution.mode == "benchmark" and not execution.benchmark_manifest_paths:
        checks.append(
            PreflightCheck(
                "memory_stage_contract_execution",
                "warn",
                "历史 stage contract 提示 benchmark/执行契约缺口，当前 benchmark 缺少 manifest",
                action="填写 Benchmark Manifest，并先用 Benchmark preview 校验命令、metrics 和 provenance。",
            )
        )
    else:
        checks.append(PreflightCheck("memory_stage_contract_execution", "pass", "当前执行模式可承接历史 stage contract 执行契约", execution.mode))
    release_count = sum(
        1
        for item in [
            release.code_repository_url,
            release.code_archive_doi,
            release.code_license,
            release.code_version,
            release.data_repository_url,
            release.data_archive_doi,
            release.data_access_statement,
            release.environment_url,
            release.release_notes,
        ]
        if str(item).strip()
    )
    if release_count:
        checks.append(PreflightCheck("memory_stage_contract_release", "pass", "当前 release 字段可承接历史 stage contract 归档契约", f"{release_count} fields"))
    else:
        checks.append(
            PreflightCheck(
                "memory_stage_contract_release",
                "warn",
                "历史 stage contract 提示发布/复现契约缺口，当前未填写 release 元数据",
                action="建议提前填写代码仓库、许可证、版本、数据访问、环境归档或 release notes。",
            )
        )
    return checks


def _memory_scorecard_checks(config: AgentConfig) -> list[PreflightCheck]:
    literature = config.literature
    execution = config.execution
    release = config.release
    human = config.human
    checks: list[PreflightCheck] = []
    if literature.provider in {"online", "auto"} and literature.max_papers >= 12 and literature.seed_papers:
        checks.append(
            PreflightCheck(
                "memory_scorecard_evidence",
                "pass",
                "当前文献配置可响应历史 scorecard 低证据维度",
                f"{literature.provider}; max_papers={literature.max_papers}; seeds={len(literature.seed_papers)}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_scorecard_evidence",
                "warn",
                "历史 scorecard 存在低分维度，当前文献启动配置仍偏弱",
                f"{literature.provider}; max_papers={literature.max_papers}; seeds={len(literature.seed_papers)}",
                "下一轮建议 online/auto、max_papers>=12，并补高相关 DOI/URL seed_papers。",
            )
        )
    if execution.mode == "benchmark" and execution.benchmark_manifest_paths:
        checks.append(PreflightCheck("memory_scorecard_experiment", "pass", "当前 benchmark 配置可响应历史 scorecard 实验/benchmark 维度", f"{len(execution.benchmark_manifest_paths)} manifests"))
    elif execution.mode == "local" and execution.allowed_commands and execution.repeats >= 5:
        checks.append(PreflightCheck("memory_scorecard_experiment", "pass", "当前 local 配置可承接 targeted 实验迭代", f"repeats={execution.repeats}; commands={len(execution.allowed_commands)}"))
    else:
        checks.append(
            PreflightCheck(
                "memory_scorecard_experiment",
                "warn",
                "历史 scorecard 存在实验/benchmark 低分风险，当前执行配置仍偏弱",
                f"{execution.mode}; repeats={execution.repeats}; manifests={len(execution.benchmark_manifest_paths)}",
                "正式迭代建议使用 benchmark manifest，或 local 模式 repeats>=5 并保留命令白名单与 artifacts。",
            )
        )
    release_count = sum(
        1
        for item in [
            release.code_repository_url,
            release.code_archive_doi,
            release.code_license,
            release.code_version,
            release.data_repository_url,
            release.data_archive_doi,
            release.data_access_statement,
            release.environment_url,
            release.release_notes,
        ]
        if str(item).strip()
    )
    if release_count:
        checks.append(PreflightCheck("memory_scorecard_release", "pass", "当前 release 元数据可响应历史 scorecard 复现/投稿维度", f"{release_count} fields"))
    else:
        checks.append(
            PreflightCheck(
                "memory_scorecard_release",
                "warn",
                "历史 scorecard 存在复现/投稿低分风险，当前未填写 release 元数据",
                action="提前填写代码仓库、许可证、版本、数据访问、环境归档或 release notes。",
            )
        )
    human_count = sum(
        1
        for item in [*human.notes, *human.constraints, *human.success_criteria, *human.resource_limits, *human.risks]
        if str(item).strip()
    )
    if human_count:
        checks.append(PreflightCheck("memory_scorecard_human_work", "pass", "当前 human brief 可承接历史 scorecard 人工待办", f"{human_count} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_scorecard_human_work",
                "warn",
                "历史 scorecard 提示需要人工待办或 targeted iteration，当前未填写 human brief",
                action="把 scorecard 最低分维度、人工待办和验收标准写入 human_constraints/success_criteria。",
            )
        )
    return checks


def _memory_integrity_checks(config: AgentConfig) -> list[PreflightCheck]:
    llm = config.llm
    literature = config.literature
    execution = config.execution
    release = config.release
    human = config.human
    checks: list[PreflightCheck] = []
    model = _resolved(llm.model, llm.model_env, "")
    base_url = _resolved(llm.base_url, llm.base_url_env, "https://api.openai.com/v1")
    if model and base_url:
        checks.append(PreflightCheck("memory_integrity_llm_trace", "pass", "当前 LLM 配置可生成 ledger 和 trace 审计", f"{_redact_url(base_url)} / {model}"))
    else:
        checks.append(
            PreflightCheck(
                "memory_integrity_llm_trace",
                "warn",
                "历史 run integrity 提示 LLM/ledger 轨迹缺口，当前模型配置仍需确认",
                action="固定可用 model/base_url/api_key；run-config 只保存脱敏配置，API key 不得落盘。",
            )
        )
    human_count = sum(
        1
        for item in [*human.notes, *human.constraints, *human.success_criteria, *human.resource_limits, *human.risks]
        if str(item).strip()
    )
    if human_count:
        checks.append(PreflightCheck("memory_integrity_human_gate", "pass", "当前 human brief 可支撑 human gate 记录", f"{human_count} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_integrity_human_gate",
                "warn",
                "历史 run integrity 提示 gate/manifest 风险，当前未填写 human brief",
                action="填写 human_constraints/success_criteria/review_notes，使人工 gate 和 manifest 轨迹可审计。",
            )
        )
    if execution.mode in {"local", "benchmark"} and execution.allowed_commands:
        checks.append(PreflightCheck("memory_integrity_execution_trace", "pass", "当前执行配置可生成 execution gate/runbook trace", f"{execution.mode}; commands={len(execution.allowed_commands)}"))
    else:
        checks.append(
            PreflightCheck(
                "memory_integrity_execution_trace",
                "warn",
                "历史 run integrity 提示 execution/runbook 轨迹风险，当前执行配置偏弱",
                f"{execution.mode}; commands={len(execution.allowed_commands)}",
                "正式 run 使用 local/benchmark，并保留 allowed_commands、execution approval、runbook、stdout/stderr 和 artifacts。",
            )
        )
    release_count = sum(
        1
        for item in [
            release.code_repository_url,
            release.code_archive_doi,
            release.code_license,
            release.code_version,
            release.data_repository_url,
            release.data_archive_doi,
            release.data_access_statement,
            release.environment_url,
            release.release_notes,
        ]
        if str(item).strip()
    )
    if release_count:
        checks.append(PreflightCheck("memory_integrity_release_package", "pass", "当前 release 字段可支撑 package/integrity 审计", f"{release_count} fields"))
    else:
        checks.append(
            PreflightCheck(
                "memory_integrity_release_package",
                "warn",
                "历史 run integrity 提示 package/release 轨迹风险，当前未填写 release 元数据",
                action="提前填写代码仓库、许可证、版本、数据访问、环境归档或 release notes。",
            )
        )
    if literature.provider in {"online", "auto"} or literature.seed_papers or literature.fulltext_paths:
        checks.append(
            PreflightCheck(
                "memory_integrity_literature_inputs",
                "pass",
                "当前文献输入可支撑 artifact inventory 和 citation trace",
                f"{literature.provider}; seeds={len(literature.seed_papers)}; fulltexts={len(literature.fulltext_paths)}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_integrity_literature_inputs",
                "warn",
                "历史 run integrity 提示完整 artifact/citation 轨迹风险，当前文献输入偏弱",
                f"{literature.provider}; seeds=0; fulltexts=0",
                "正式 run 建议 online/auto，或至少提供 seed_papers/fulltext_paths，保证文献和引用产物可追踪。",
            )
        )
    return checks


def _memory_repair_resolution_checks(config: AgentConfig) -> list[PreflightCheck]:
    human = config.human
    execution = config.execution
    release = config.release
    checks: list[PreflightCheck] = [
        PreflightCheck(
            "memory_repair_resolution_resume_mode",
            "skipped",
            "历史 repair-resume 仍有未闭环项",
            action="优先对原 run 使用 repair-resume，并查看 12-repair-resolution-audit.md；不要直接新开低上下文 run 覆盖问题。",
        )
    ]
    human_count = sum(
        1
        for item in [*human.notes, *human.constraints, *human.success_criteria, *human.resource_limits, *human.risks]
        if str(item).strip()
    )
    if human_count:
        checks.append(PreflightCheck("memory_repair_resolution_human_brief", "pass", "当前 human brief 可承接历史修复闭环要求", f"{human_count} entries"))
    else:
        checks.append(
            PreflightCheck(
                "memory_repair_resolution_human_brief",
                "warn",
                "历史 repair-resume 未完全闭环，当前未填写 human brief",
                action="把未闭环修复项、人工验收标准和允许/禁止的修复范围写入 human_constraints/success_criteria。",
            )
        )
    if execution.mode in {"local", "benchmark"} and execution.allowed_commands:
        checks.append(
            PreflightCheck(
                "memory_repair_resolution_execution",
                "pass",
                "当前执行配置可支撑修复后重跑验证",
                f"{execution.mode}; commands={len(execution.allowed_commands)}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_repair_resolution_execution",
                "warn",
                "历史 repair-resume 未完全闭环，当前执行配置难以验证修复",
                f"{execution.mode}; commands={len(execution.allowed_commands)}",
                "修复闭环建议使用 local/benchmark，并保留 allowed_commands、runbook、stdout/stderr 和 artifacts。",
            )
        )
    release_count = sum(
        1
        for item in [
            release.code_repository_url,
            release.code_archive_doi,
            release.code_license,
            release.code_version,
            release.data_repository_url,
            release.data_archive_doi,
            release.data_access_statement,
            release.environment_url,
            release.release_notes,
        ]
        if str(item).strip()
    )
    if release_count:
        checks.append(PreflightCheck("memory_repair_resolution_release", "pass", "当前 release 字段可记录修复闭环说明", f"{release_count} fields"))
    else:
        checks.append(
            PreflightCheck(
                "memory_repair_resolution_release",
                "warn",
                "历史 repair-resume 未完全闭环，当前缺少 release/修复说明字段",
                action="建议填写 release_notes、代码仓库或环境归档 URL，说明修复范围和重跑依据。",
            )
        )
    return checks


def _memory_experiment_checks(config: AgentConfig) -> list[PreflightCheck]:
    repeats = config.execution.repeats
    if repeats < 5:
        return [
            PreflightCheck(
                "memory_execution_repeats",
                "warn",
                "历史 run 出现实验验证或负结果风险，当前重复次数偏低",
                str(repeats),
                "建议 execution_repeats >= 5，并保留失败/负结果进入分析边界。",
            )
        ]
    return [PreflightCheck("memory_execution_repeats", "pass", "当前重复次数已响应历史实验复盘", str(repeats))]


def _memory_experiment_manager_checks(config: AgentConfig, categories: set[str]) -> list[PreflightCheck]:
    execution = config.execution
    checks: list[PreflightCheck] = []
    if "experiment_manager" in categories:
        checks.append(
            PreflightCheck(
                "memory_experiment_manager",
                "warn",
                "历史 run 存在实验管理阻断",
                action="启动前查看 runs-memory.md 和 00-prior-run-lessons.md；block 分支必须人工改选或修复 idea audit。",
            )
        )
    if "experiment_manager_smoke_first" in categories:
        if execution.mode == "simulated":
            checks.append(
                PreflightCheck(
                    "memory_experiment_manager_smoke_first",
                    "warn",
                    "历史实验管理要求 smoke-first，当前仍是 simulated",
                    action="正式推进前使用 local 或 benchmark 模式执行可复核 smoke，并保留 stdout/stderr。",
                )
            )
        elif execution.mode == "benchmark" and not execution.benchmark_manifest_paths:
            checks.append(
                PreflightCheck(
                    "memory_experiment_manager_smoke_first",
                    "warn",
                    "历史实验管理要求 smoke-first，但当前 benchmark 缺少 manifest",
                    action="补 benchmark manifest，或先用 local 白名单命令做可复核 smoke。",
                )
            )
        else:
            checks.append(
                PreflightCheck(
                    "memory_experiment_manager_smoke_first",
                    "pass",
                    "当前执行模式可承接历史 smoke-first 要求",
                    execution.mode,
                )
            )
    if "experiment_branch_backlog" in categories:
        checks.append(
            PreflightCheck(
                "memory_experiment_branch_backlog",
                "skipped",
                "历史实验管理留有下一轮候选分支",
                action="启动后优先读取 02-experiment-manager 的 next_expansion_candidates，避免从零发散。",
            )
        )
    return checks


def _memory_human_constraints_checks(config: AgentConfig) -> list[PreflightCheck]:
    human = config.human
    fields = [
        *human.notes,
        *human.constraints,
        *human.success_criteria,
        *human.resource_limits,
        *human.risks,
    ]
    count = sum(1 for item in fields if str(item).strip())
    if count == 0:
        return [
            PreflightCheck(
                "memory_human_constraints",
                "warn",
                "历史 run 存在未落实的人工/review 约束，当前未填写 human brief",
                action="把硬性要求写入 human_constraints 或 human_resource_limits；背景和验收口径写入 human_notes/success_criteria。",
            )
        ]
    return [
        PreflightCheck(
            "memory_human_constraints",
            "pass",
            "当前 human brief 已响应历史人工约束复盘",
            f"{count} entries",
            "启动后仍需检查 00-human-brief.md 和 03-review-constraint-compliance.md。",
        )
    ]


def _memory_benchmark_checks(config: AgentConfig) -> list[PreflightCheck]:
    execution = config.execution
    if execution.mode == "simulated":
        return [
            PreflightCheck(
                "memory_execution_mode",
                "warn",
                "历史 run 提示模拟证据或 benchmark 缺口，当前仍是 simulated",
                action="正式 run 使用 local 或 benchmark，并准备 benchmark manifest。",
            )
        ]
    if execution.mode == "benchmark" and not execution.benchmark_manifest_paths:
        return [
            PreflightCheck(
                "memory_benchmark_manifest",
                "warn",
                "历史 run 提示 benchmark 缺口，但当前未填写 manifest",
                action="补 benchmark manifest、数据入口、baseline 和许可说明。",
            )
        ]
    return [PreflightCheck("memory_execution_mode", "pass", "当前执行模式已响应历史 benchmark 复盘", execution.mode)]


def _memory_benchmark_schema_checks(config: AgentConfig) -> list[PreflightCheck]:
    execution = config.execution
    if execution.mode != "benchmark":
        return [
            PreflightCheck(
                "memory_benchmark_result_schema",
                "warn",
                "历史 run 存在 benchmark result schema/provenance 断链，当前不是 benchmark 模式",
                action="切换 benchmark 模式，并准备含 dataset_url/license/baseline_version/citation 的 manifest。",
            )
        ]
    if not execution.benchmark_manifest_paths:
        return [
            PreflightCheck(
                "memory_benchmark_result_schema",
                "warn",
                "历史 run 存在 benchmark result schema/provenance 断链，当前缺少 manifest",
                action="填写 Benchmark Manifest，并先点“校验 Benchmark”确认来源、许可、baseline 和 citation。",
            )
        ]
    return [
        PreflightCheck(
            "memory_benchmark_result_schema",
            "pass",
            "当前 benchmark manifest 配置可用于修复历史 schema/provenance 断链",
            f"{len(execution.benchmark_manifest_paths)} manifests",
            "启动前仍需运行 Benchmark preview，确认 metrics_path/expected_artifacts 和 provenance 字段齐全。",
        )
    ]


def _memory_environment_checks(config: AgentConfig) -> list[PreflightCheck]:
    execution = config.execution
    release = config.release
    checks: list[PreflightCheck] = []
    if execution.mode == "simulated":
        checks.append(
            PreflightCheck(
                "memory_environment_execution",
                "warn",
                "历史 run 环境快照不完整，当前仍是 simulated",
                action="正式或可复现 run 使用 local/benchmark，并确认命令白名单可定位。",
            )
        )
    elif execution.mode in {"local", "benchmark"} and execution.allowed_commands:
        checks.append(
            PreflightCheck(
                "memory_environment_execution",
                "pass",
                "当前执行配置可重新生成环境快照",
                f"{execution.mode}; commands={', '.join(execution.allowed_commands)}",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                "memory_environment_execution",
                "warn",
                "历史 run 环境快照不完整，当前执行配置仍需确认",
                f"{execution.mode}; commands={len(execution.allowed_commands)}",
                "使用 local/benchmark，并至少保留 python3 或明确实验命令白名单。",
            )
        )
    if release.environment_url:
        checks.append(PreflightCheck("memory_environment_archive", "pass", "环境归档字段已配置", release.environment_url))
    else:
        checks.append(
            PreflightCheck(
                "memory_environment_archive",
                "warn",
                "历史环境快照不完整，当前未填写环境归档 URL",
                action="建议补充 Docker/Conda/requirements/lockfile 的公开归档链接。",
            )
        )
    return checks


def _memory_release_checks(config: AgentConfig) -> list[PreflightCheck]:
    release = config.release
    configured = [
        release.code_repository_url,
        release.code_archive_doi,
        release.code_license,
        release.code_version,
        release.data_repository_url,
        release.data_archive_doi,
        release.data_access_statement,
        release.environment_url,
        release.release_notes,
    ]
    count = sum(1 for item in configured if str(item).strip())
    if count == 0:
        return [
            PreflightCheck(
                "memory_release_metadata",
                "warn",
                "历史 run 提示发布元数据缺口，当前仍未填写",
                action="启动时同步填写代码仓库、许可证、版本、数据访问和环境归档字段。",
            )
        ]
    return [PreflightCheck("memory_release_metadata", "pass", "当前发布元数据已响应历史复盘", f"{count} fields")]


def _llm_ping_check(config: AgentConfig, timeout_seconds: float) -> PreflightCheck:
    llm = config.llm
    from .llm import (
        _candidate_chat_urls,
        add_bearer_auth,
        _http_error_detail,
        _open_url,
        _ping_max_attempts,
        _retry_delay_seconds,
        llm_request_slot,
        read_limited_response,
        redact_sensitive_text,
        redact_url,
        remaining_deadline_seconds,
        request_deadline,
        resolve_llm_api_key,
        resolve_llm_base_url,
        USER_AGENT,
        validate_llm_provider,
    )
    try:
        provider = validate_llm_provider(llm.provider)
    except ValueError as exc:
        return PreflightCheck("llm_ping", "fail", "LLM provider 不支持 ping", str(exc), "使用 OpenAI Chat Completions 兼容协议。")
    env_base_url = os.environ.get(llm.base_url_env, "").strip() if llm.base_url_env else ""
    base_url_configured = bool(str(llm.base_url or "").strip() or env_base_url)
    try:
        base_url = resolve_llm_base_url(provider, llm.base_url, llm.base_url_env)
    except ValueError as exc:
        return PreflightCheck("llm_ping", "fail", "LLM Base URL 无效", str(exc), "检查 Base URL 的 scheme、主机名和凭据位置。")
    model = _resolved(llm.model, llm.model_env, "")
    api_key = resolve_llm_api_key(llm, base_url)
    if config.paper_grade.enabled and not base_url_configured:
        return PreflightCheck("llm_ping", "skipped", "缺少显式 Base URL，未执行 LLM ping")
    if not model:
        return PreflightCheck("llm_ping", "skipped", "缺少模型名，未执行 LLM ping")
    if not api_key and (urllib.parse.urlsplit(base_url).hostname == "api.openai.com" or config.paper_grade.enabled):
        return PreflightCheck("llm_ping", "skipped", "缺少 API key，未执行 LLM ping")
    if api_key and config.paper_grade.enabled and _placeholder_secret(api_key):
        return PreflightCheck("llm_ping", "skipped", "API key 是占位值，未执行 LLM ping")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly OK."}],
    }
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    last_error = ""
    last_status: int | None = None
    try:
        deadline = request_deadline(timeout_seconds, "LLM ping")
        with llm_request_slot(timeout_seconds=remaining_deadline_seconds(deadline, "LLM ping")):
            for url in _candidate_chat_urls(base_url):
                for attempt in range(_ping_max_attempts()):
                    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                    add_bearer_auth(request, api_key)
                    try:
                        with _open_url(
                            request,
                            timeout=remaining_deadline_seconds(deadline, "LLM ping"),
                        ) as response:
                            response_body = read_limited_response(response, context="LLM ping")
                        data = json.loads(response_body.decode("utf-8"))
                        content = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
                        if content:
                            return PreflightCheck("llm_ping", "pass", "LLM 连通性正常", f"{redact_url(url)} -> {content[:60]}")
                        return PreflightCheck("llm_ping", "warn", "LLM 有响应但内容为空", redact_url(url))
                    except urllib.error.HTTPError as exc:
                        last_status = exc.code
                        detail = _http_error_detail(exc, secrets=[api_key])
                        last_error = f"{redact_url(url)} HTTP {exc.code}: {detail}"
                        if exc.code == 429 and attempt < _ping_max_attempts() - 1:
                            delay = _retry_delay_seconds(exc, attempt)
                            if delay is not None:
                                remaining = remaining_deadline_seconds(deadline, "LLM ping")
                                if delay >= remaining:
                                    last_error += "; retry delay exceeds the remaining timeout budget"
                                    break
                                time.sleep(delay)
                                continue
                        if exc.code in {404, 405}:
                            break
                        action = (
                            "网关并发槽已满；等待现有请求结束后重试，或提高网关用户并发上限。"
                            if exc.code == 429
                            else "检查 Base URL、模型名、API Key 和服务状态。"
                        )
                        return PreflightCheck("llm_ping", "fail", "LLM 连通性失败", last_error, action)
                    except Exception as exc:
                        last_error = f"{redact_url(url)}: {redact_sensitive_text(str(exc), secrets=[api_key])}"
                        break
    except (TimeoutError, ValueError) as exc:
        last_error = redact_sensitive_text(str(exc), secrets=[api_key])
    action = (
        "网关并发槽已满；等待现有请求结束后重试，或提高网关用户并发上限。"
        if last_status == 429
        else "检查 Base URL、模型名、API Key 和服务状态。"
    )
    return PreflightCheck("llm_ping", "fail", "LLM 连通性失败", last_error, action)


def _redact_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def _candidate_chat_urls(base_url: str) -> list[str]:
    from .llm import _candidate_chat_urls as candidate_chat_urls

    return candidate_chat_urls(base_url)


def _overall_status(checks: list[PreflightCheck]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _resolved(value: str, env_name: str, default: str) -> str:
    return value or (os.environ.get(env_name, default) if env_name else default)


def _redact_url(value: str) -> str:
    from .llm import redact_url

    return redact_url(value)


def _redact_email(value: str) -> str:
    if "@" not in value:
        return "已隐藏"
    name, domain = value.split("@", 1)
    prefix = name[:2] if len(name) > 2 else name[:1]
    return f"{prefix}***@{domain}"


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _looks_like_doi(value: str) -> bool:
    value = value.removeprefix("doi:").strip()
    if "doi.org/" in value.lower():
        value = value.rsplit("doi.org/", 1)[-1].strip()
    return value.lower().startswith("10.") and "/" in value


def _strong_seed_count(values: list[str]) -> int:
    return sum(1 for value in values if _looks_like_doi(value.strip()) or _looks_like_url(value.strip()))


def _known_configured_sources(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        source = str(value or "").strip().lower()
        if source in KNOWN_LITERATURE_SOURCES and source not in seen:
            seen.add(source)
            result.append(source)
    return result


def _covered_seed_roles(values: list[str]) -> list[str]:
    counts = _seed_role_counts(values)
    return [role for role in ["review", "benchmark_dataset", "baseline_method", "recent"] if counts.get(role, 0) > 0]


def _open_source_lesson_ids(signal: Any | None) -> set[str]:
    texts: list[str] = []
    for attr in ["evidence", "recommended_action", "next_run_hint"]:
        value = getattr(signal, attr, None)
        if isinstance(value, list):
            texts.extend(str(item) for item in value)
        elif value is not None:
            texts.append(str(value))
    known = {
        "source_project_provenance",
        "structured_idea_to_experiment_loop",
        "sandbox_generated_code",
        "citation_grounded_fulltext",
        "retrieval_rerank_before_synthesis",
        "query_execution_coverage_audit",
        "human_feedback_compliance",
        "repair_context_on_resume",
        "benchmark_result_schema_contract",
        "runtime_cost_observability",
        "metadata_rate_limit_resilience",
        "cache_and_memory_reuse",
        "ai_use_disclosure",
        "domain_benchmark_before_claims",
    }
    found: set[str] = set()
    for text in texts:
        found.update(lesson_id for lesson_id in known if lesson_id in text)
    return found


def _seed_role_coverage_check(values: list[str]) -> PreflightCheck:
    counts = _seed_role_counts(values)
    covered = [role for role in ["review", "benchmark_dataset", "baseline_method", "recent"] if counts.get(role, 0) > 0]
    detail = _seed_role_detail(counts)
    if len(covered) >= 3:
        return PreflightCheck("seed_role_coverage", "pass", "人工 seed 覆盖了多个文献角色", detail)
    return PreflightCheck(
        "seed_role_coverage",
        "warn",
        "人工 seed 角色覆盖不足，可能仍会形成偏窄证据池",
        detail,
        "为 seed 条目补 DOI/URL 后追加简短角色或题名，至少覆盖 review/survey、benchmark/dataset、baseline/method、recent work 中的 3 类。",
    )


def _memory_seed_role_coverage_check(values: list[str]) -> PreflightCheck:
    check = _seed_role_coverage_check(values)
    if check.status == "pass":
        return PreflightCheck("memory_seed_role_coverage", "pass", "当前 seed 角色覆盖可响应历史薄证据池", check.detail)
    return PreflightCheck(
        "memory_seed_role_coverage",
        "warn",
        "历史 run 证据池偏薄，当前 seed 角色覆盖仍不足",
        check.detail,
        "至少补齐 review/survey、benchmark/dataset、baseline/method、recent work 中的 3 类 seed；每条建议含 DOI/URL 和简短题名。",
    )


def _seed_role_counts(values: list[str]) -> dict[str, int]:
    counts = {"review": 0, "benchmark_dataset": 0, "baseline_method": 0, "recent": 0}
    for value in values:
        text = str(value).lower()
        if any(token in text for token in ["review", "survey", "tutorial", "overview", "综述"]):
            counts["review"] += 1
        if any(token in text for token in ["benchmark", "dataset", "evaluation", "corpus", "suite", "leaderboard", "基准", "数据集", "评测"]):
            counts["benchmark_dataset"] += 1
        if any(
            token in text
            for token in [
                "baseline",
                "method",
                "algorithm",
                "planner",
                "planning",
                "approach",
                "framework",
                "model",
                "rrt",
                "prm",
                "chomp",
                "stomp",
                "trajopt",
                "ompl",
                "方法",
                "算法",
                "规划",
            ]
        ):
            counts["baseline_method"] += 1
        if any(year >= _recent_seed_year_cutoff() for year in _seed_years(text)):
            counts["recent"] += 1
    return counts


def _seed_role_detail(counts: dict[str, int]) -> str:
    return (
        f"review={counts.get('review', 0)}, benchmark_dataset={counts.get('benchmark_dataset', 0)}, "
        f"baseline_method={counts.get('baseline_method', 0)}, recent={counts.get('recent', 0)}"
    )


def _seed_years(value: str) -> list[int]:
    result: list[int] = []
    for match in re.findall(r"\b(20\d{2})\b", value):
        try:
            result.append(int(match))
        except ValueError:
            continue
    return result


def _recent_seed_year_cutoff() -> int:
    return datetime.now(timezone.utc).year - 5


