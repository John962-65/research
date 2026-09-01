from __future__ import annotations

from typing import Any, Callable
import json
import re

from .config import LiteratureConfig
from .literature_sources import OnlineLiteratureClient, annotate_evidence, build_evidence_table, deduplicate_papers, rank_papers
from .literature_search_strategy import build_literature_search_strategy, strategy_to_dict
from .llm import LLM
from .llm_trace import complete_with_purpose, record_validation_result
from .models import LiteratureReview, Paper


OFFLINE_CORPUS = [
    Paper(
        title="Autonomous Agents for Scientific Discovery",
        authors=["King", "Whelan", "Jones"],
        year=2009,
        venue="Science",
        url="https://doi.org/10.1126/science.1165620",
        abstract="该工作展示了一个机器人科学家系统，能够在酵母功能基因组学中生成假设、选择实验并解释结果，是自动科学发现的早期代表。",
        relevance=0.92,
    ),
    Paper(
        title="The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery",
        authors=["Lu", "Lu", "Lange"],
        year=2024,
        venue="arXiv",
        url="https://arxiv.org/abs/2408.06292",
        abstract="该系统尝试自动完成机器学习研究中的 idea 生成、代码执行、论文写作和模拟评审，直接对应端到端科研 agent 的目标。",
        relevance=0.9,
    ),
    Paper(
        title="ChemCrow: Augmenting Large-Language Models with Chemistry Tools",
        authors=["Bran", "Cox", "Schilter"],
        year=2024,
        venue="Nature Machine Intelligence",
        url="https://doi.org/10.1038/s42256-024-00832-8",
        abstract="该研究说明工具增强的大语言模型可以规划并执行化学相关任务，强调外部工具对科研 agent 的必要性。",
        relevance=0.78,
    ),
    Paper(
        title="Coscientist: An AI System for Autonomous Chemical Research",
        authors=["Boiko", "MacKnight", "Kline", "Gomes"],
        year=2023,
        venue="Nature",
        url="https://doi.org/10.1038/s41586-023-06792-0",
        abstract="该系统结合文献推理、代码生成和实验自动化控制，展示了 AI 系统参与自主化学研究的完整链路。",
        relevance=0.82,
    ),
    Paper(
        title="Language Agents as Optimizers",
        authors=["Yang", "Ma", "Wang"],
        year=2024,
        venue="arXiv",
        url="https://arxiv.org/abs/2309.03409",
        abstract="该工作把语言 agent 看作迭代优化器，说明模型可以通过提出、评估和改进候选方案来推动研究循环。",
        relevance=0.74,
    ),
    Paper(
        title="SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering",
        authors=["Yang", "Jimenez", "Wettig"],
        year=2024,
        venue="NeurIPS",
        url="https://arxiv.org/abs/2405.15793",
        abstract="该研究表明，良好的 agent-computer interface 和结构化轨迹能提升自动软件工程任务表现，对实验执行层有借鉴意义。",
        relevance=0.68,
    ),
    Paper(
        title="Self-Refine: Iterative Refinement with Self-Feedback",
        authors=["Madaan", "Tandon", "Gupta"],
        year=2023,
        venue="NeurIPS",
        url="https://arxiv.org/abs/2303.17651",
        abstract="该框架让语言模型生成自我反馈并多轮改进输出，适合用于 idea、实验计划和论文草稿的迭代修正。",
        relevance=0.66,
    ),
    Paper(
        title="Reflexion: Language Agents with Verbal Reinforcement Learning",
        authors=["Shinn", "Cassano", "Gopinath"],
        year=2023,
        venue="NeurIPS",
        url="https://arxiv.org/abs/2303.11366",
        abstract="该方法让 agent 把试错后的反思写入记忆，并在后续任务中复用，为科研 agent 的经验积累提供思路。",
        relevance=0.64,
    ),
    Paper(
        title="Sampling-based Algorithms for Optimal Motion Planning",
        authors=["Karaman", "Frazzoli"],
        year=2011,
        venue="The International Journal of Robotics Research",
        url="https://doi.org/10.1177/0278364911406761",
        abstract="该工作提出 RRT* 等渐近最优 sampling-based motion planning 方法，是机械臂路径规划、避障规划和最优路径质量比较中的经典 baseline。",
        relevance=0.88,
        source="offline",
        sources=["offline"],
        doi="10.1177/0278364911406761",
    ),
    Paper(
        title="The Open Motion Planning Library",
        authors=["Sucan", "Moll", "Kavraki"],
        year=2012,
        venue="IEEE Robotics & Automation Magazine",
        url="https://doi.org/10.1109/MRA.2012.2205651",
        abstract="OMPL 提供机械臂和移动机器人运动规划算法库与 benchmark 基础设施，常用于比较 RRT、PRM、RRT* 等路径规划方法的成功率、耗时和路径质量。",
        relevance=0.86,
        source="offline",
        sources=["offline"],
        doi="10.1109/MRA.2012.2205651",
    ),
    Paper(
        title="CHOMP: Gradient Optimization Techniques for Efficient Motion Planning",
        authors=["Ratliff", "Zucker", "Bagnell", "Srinivasa"],
        year=2009,
        venue="IEEE International Conference on Robotics and Automation",
        url="https://doi.org/10.1109/ICRA.2009.5152817",
        abstract="CHOMP 将机械臂 motion planning 表述为轨迹优化问题，关注避障、平滑性和约束满足，是 trajectory optimization 类 baseline。",
        relevance=0.84,
        source="offline",
        sources=["offline"],
        doi="10.1109/ICRA.2009.5152817",
    ),
    Paper(
        title="STOMP: Stochastic Trajectory Optimization for Motion Planning",
        authors=["Kalakrishnan", "Chitta", "Theodorou", "Pastor", "Schaal"],
        year=2011,
        venue="IEEE International Conference on Robotics and Automation",
        url="https://doi.org/10.1109/ICRA.2011.5980280",
        abstract="STOMP 用随机轨迹优化处理机器人和机械臂运动规划，可作为 CHOMP、RRT* 等方法之外的优化类 baseline。",
        relevance=0.83,
        source="offline",
        sources=["offline"],
        doi="10.1109/ICRA.2011.5980280",
    ),
    Paper(
        title="Motion Planning with Sequential Convex Optimization and Convex Collision Checking",
        authors=["Schulman", "Ho", "Lee", "Awwal", "Bradlow", "Abbeel"],
        year=2014,
        venue="The International Journal of Robotics Research",
        url="https://doi.org/10.1177/0278364914528132",
        abstract="TrajOpt 使用序列凸优化和凸碰撞检查生成机器人轨迹，是机械臂路径规划中常见的轨迹优化 baseline。",
        relevance=0.83,
        source="offline",
        sources=["offline"],
        doi="10.1177/0278364914528132",
    ),
    Paper(
        title="Case Western Reserve University Bearing Data Center",
        authors=["Case Western Reserve University"],
        year=1999,
        venue="Dataset",
        url="https://engineering.case.edu/bearingdatacenter",
        abstract="CWRU bearing dataset 是轴承故障诊断常用公开数据源，适合验证 vibration signal classification、故障类型识别和跨负载泛化。",
        relevance=0.84,
        source="offline",
        sources=["offline"],
    ),
    Paper(
        title="Condition Monitoring of Bearing Damage in Electromechanical Drive Systems by Using Motor Current Signals of Electric Motors",
        authors=["Lessmeier", "Kimotho", "Zimmer", "Sextro"],
        year=2016,
        venue="PHM Society European Conference",
        url="https://doi.org/10.36001/phme.2016.v3i1.1577",
        abstract="该工作对应 Paderborn bearing dataset，提供真实和人工损伤轴承数据，可用于跨工况轴承故障诊断、domain adaptation 和鲁棒性测试。",
        relevance=0.82,
        source="offline",
        sources=["offline"],
        doi="10.36001/phme.2016.v3i1.1577",
    ),
    Paper(
        title="XJTU-SY Bearing Datasets: A Tutorial",
        authors=["Wang", "Tsui"],
        year=2018,
        venue="Dataset",
        url="https://biaowang.tech/xjtu-sy-bearing-datasets/",
        abstract="XJTU-SY bearing datasets 常用于轴承退化、剩余寿命预测和故障诊断任务，适合评估跨工况稳定性和重复实验统计。",
        relevance=0.80,
        source="offline",
        sources=["offline"],
    ),
]


def run_literature_review(
    topic: str,
    config: LiteratureConfig,
    llm: LLM,
    seed_queries: list[str] | None = None,
) -> LiteratureReview:
    diagnostics: list[str] = []
    online_client = OnlineLiteratureClient(config) if config.provider in {"online", "auto"} else None
    online_source_health: list[dict[str, Any]] = []
    manual_papers, manual_diagnostics = parse_manual_seed_papers(
        config.seed_papers,
        resolver=_seed_resolver(online_client) if online_client is not None else None,
    )
    diagnostics.extend(manual_diagnostics)
    strategy = None
    if config.provider in {"online", "auto"}:
        llm_queries, query_diagnostics = _llm_search_queries(topic, llm, config.max_search_queries)
        strategy = build_literature_search_strategy(topic, config, seed_queries=seed_queries or [], extra_queries=config.extra_search_queries, llm_queries=llm_queries)
        queries = strategy.selected_queries
        if seed_queries:
            query_diagnostics.insert(0, "研究计划检索式: " + " | ".join((seed_queries or [])[: config.max_search_queries]))
        if config.extra_search_queries:
            query_diagnostics.insert(0, "补充检索式: " + " | ".join(config.extra_search_queries[: config.max_search_queries]))
        query_diagnostics.insert(0, "检索策略已选: " + " | ".join(queries))
        papers, diagnostics = (online_client or OnlineLiteratureClient(config)).search(topic, queries)
        online_source_health = list((online_client or OnlineLiteratureClient(config)).source_health)
        diagnostics = manual_diagnostics + query_diagnostics + diagnostics
        if papers:
            papers = _merge_manual_and_rank(manual_papers, papers, topic, queries, config.max_papers)
            papers = annotate_evidence(papers, topic)
            return _build_review(topic, papers, llm, diagnostics, source_health=online_source_health, search_strategy=strategy_to_dict(strategy))
        diagnostics.append("在线检索没有可用结果，已回退到离线种子文献库。")
    elif config.provider != "offline":
        raise ValueError(f"Unsupported literature provider: {config.provider}")

    if strategy is None:
        strategy = build_literature_search_strategy(topic, config, seed_queries=seed_queries or [], extra_queries=config.extra_search_queries, llm_queries=[])
    papers = _merge_manual_and_rank(manual_papers, _rank_offline(topic, strategy.selected_queries), topic, strategy.selected_queries, config.max_papers)
    papers = annotate_evidence(papers, topic)
    if config.provider == "offline":
        diagnostics.append("offline: 使用内置种子文献库。")
    source_health = [
        *online_source_health,
        {
            "source": "offline",
            "status": "ok",
            "queries": len(strategy.selected_queries),
            "returned": len(papers),
            "errors": 0,
            "rate_limited": False,
            "elapsed_seconds": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_writes": 0,
            "stale_cache_uses": 0,
            "query_results": [
                {
                    "source": "offline",
                    "query": query,
                    "status": "offline_ranked",
                    "returned": len(papers),
                    "error": "",
                    "rate_limited": False,
                    "elapsed_seconds": 0.0,
                    "cache_hits": 0,
                    "cache_misses": 0,
                    "cache_writes": 0,
                    "stale_cache_uses": 0,
                }
                for query in strategy.selected_queries
            ],
        }
    ]
    return _build_review(topic, papers, llm, diagnostics, source_health=source_health, search_strategy=strategy_to_dict(strategy))


def parse_manual_seed_papers(
    seed_entries: list[str],
    resolver: Callable[[str], Paper | None] | None = None,
) -> tuple[list[Paper], list[str]]:
    papers: list[Paper] = []
    diagnostics: list[str] = []
    for index, raw in enumerate(seed_entries, start=1):
        entry = re.sub(r"\s+", " ", str(raw)).strip()
        if not entry:
            continue
        paper = _manual_seed_paper(entry, index)
        if resolver is not None and paper.doi:
            try:
                resolved = resolver(paper.doi)
            except Exception as exc:
                diagnostics.append(f"manual_seed: DOI {paper.doi} 元数据解析失败：{exc}")
                resolved = None
            if resolved is not None:
                paper = _merge_resolved_manual_seed(paper, resolved)
                diagnostics.append(f"manual_seed: DOI {paper.doi} 已解析元数据。")
        papers.append(paper)
    if papers:
        diagnostics.append(f"manual_seed: 纳入 {len(papers)} 条人工种子文献。")
    return papers, diagnostics


def _seed_resolver(client: Any) -> Callable[[str], Paper | None]:
    resolver = getattr(client, "resolve_doi_metadata", None)
    if callable(resolver):
        return resolver
    return client.resolve_crossref_doi


def _manual_seed_paper(entry: str, index: int) -> Paper:
    doi = _extract_doi(entry)
    url = _extract_url(entry) or (f"https://doi.org/{doi}" if doi else "")
    title = _manual_title(entry, doi, url, index)
    year = _extract_year(entry)
    return Paper(
        title=title,
        authors=["Manual seed"],
        year=year,
        venue="Manual seed",
        url=url,
        abstract=f"人工种子文献：{entry}",
        relevance=0.96,
        source="manual_seed",
        sources=["manual_seed"],
        doi=doi,
        external_ids={"DOI": doi} if doi else {},
        evidence_note="用户提供的人工种子文献，优先作为可信候选进入文献池并等待人工核对。",
    )


def _merge_manual_and_rank(
    manual_papers: list[Paper],
    candidate_papers: list[Paper],
    topic: str,
    seed_queries: list[str] | None,
    max_papers: int,
) -> list[Paper]:
    if not manual_papers:
        return rank_papers(candidate_papers, topic, seed_queries or [])[:max_papers]
    deduped = deduplicate_papers([*manual_papers, *candidate_papers])
    ranked = rank_papers(deduped, topic, seed_queries or [])
    manual_titles = {paper.title for paper in manual_papers}
    manual_dois = {paper.doi.lower() for paper in manual_papers if paper.doi}
    manual_ranked = [paper for paper in ranked if paper.title in manual_titles or (paper.doi and paper.doi.lower() in manual_dois)]
    other_ranked = [paper for paper in ranked if paper not in manual_ranked]
    return [*manual_ranked, *other_ranked][:max_papers]


def _merge_resolved_manual_seed(manual: Paper, resolved: Paper) -> Paper:
    sources = sorted(set((resolved.sources or [resolved.source]) + ["manual_seed"]))
    return Paper(
        title=resolved.title or manual.title,
        authors=resolved.authors or manual.authors,
        year=resolved.year or manual.year,
        venue=resolved.venue or manual.venue,
        url=resolved.url or manual.url,
        abstract=resolved.abstract or manual.abstract,
        relevance=max(manual.relevance, resolved.relevance),
        source="manual_seed",
        sources=sources,
        doi=manual.doi or resolved.doi,
        external_ids={**resolved.external_ids, **manual.external_ids},
        citation_count=resolved.citation_count,
        evidence_note="用户提供 DOI，系统已尝试解析题录元数据；正式引用前仍需人工核对。",
    )


def _extract_doi(entry: str) -> str:
    match = re.search(r"(10\.\d{4,9}/[^\s,;]+)", entry, flags=re.I)
    return match.group(1).rstrip(").]") if match else ""


def _extract_url(entry: str) -> str:
    match = re.search(r"https?://[^\s,;]+", entry)
    return match.group(0).rstrip(").]") if match else ""


def _extract_year(entry: str) -> int:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", entry)
    return int(match.group(1)) if match else 0


def _manual_title(entry: str, doi: str, url: str, index: int) -> str:
    title = entry
    if url:
        title = title.replace(url, " ")
    if doi:
        title = title.replace(doi, " ")
    title = re.sub(r"\b(19\d{2}|20\d{2})\b", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -:;,")
    if title:
        return title[:180]
    if doi:
        return f"Manual seed DOI {doi}"
    return f"Manual seed paper {index}"


def _merge_queries(seed_queries: list[str], llm_queries: list[str], max_queries: int) -> list[str]:
    merged: list[str] = []
    for query in [*seed_queries, *llm_queries]:
        query = query.strip()
        if query and query not in merged:
            merged.append(query)
    return merged[:max_queries]


def render_literature_markdown(review: LiteratureReview) -> str:
    lines = [f"# 文献调研：{review.topic}", ""]
    if review.source_diagnostics:
        lines.extend(["## 检索诊断"])
        lines.extend(f"- {item}" for item in review.source_diagnostics)
        lines.append("")
    lines.extend(["## 总结", review.summary, "", "## 主要主题"])
    lines.extend(f"- {theme}" for theme in review.themes)
    lines.extend(["", "## 研究空白"])
    lines.extend(f"- {gap}" for gap in review.gaps)
    if review.evidence_table:
        lines.extend(["", "## 证据表", "| 文献 | 年份 | 来源 | 相关性 | 证据说明 |", "| --- | ---: | --- | ---: | --- |"])
        for row in review.evidence_table:
            title = _table_cell(str(row.get("title") or ""))
            year = row.get("year") or ""
            sources = _table_cell(str(row.get("sources") or ""))
            relevance = row.get("relevance") or ""
            note = _table_cell(str(row.get("evidence_note") or ""))
            lines.append(f"| {title} | {year} | {sources} | {relevance} | {note} |")
    lines.extend(["", "## 相关文献"])
    for paper in review.papers:
        authors = ", ".join(paper.authors) if paper.authors else "Unknown authors"
        sources = ", ".join(paper.sources or [paper.source])
        doi = f" DOI: {paper.doi}." if paper.doi else ""
        citations = f" Citations: {paper.citation_count}." if paper.citation_count is not None else ""
        lines.append(f"- **{paper.title}**（{paper.year or 'n.d.'}，{paper.venue}）- {authors}。{paper.url}")
        lines.append(f"  来源：{sources}.{doi}{citations}")
        if paper.evidence_note:
            lines.append(f"  证据说明：{paper.evidence_note}")
        if paper.abstract:
            lines.append(f"  摘要：{paper.abstract}")
    return "\n".join(lines)


def literature_source_health_report(review: LiteratureReview) -> dict[str, Any]:
    sources = review.source_health or []
    query_results = _query_results(sources)
    strategy = review.search_strategy if isinstance(review.search_strategy, dict) else {}
    configured_sources = [str(source).strip().lower() for source in strategy.get("sources", []) if str(source).strip()] if isinstance(strategy.get("sources"), list) else []
    successful_sources = {
        str(item.get("source") or "").strip()
        for item in query_results
        if item.get("status") in {"ok", "offline_ranked"} and _safe_int(item.get("returned")) > 0
    }
    if not successful_sources:
        successful_sources = {
            str(item.get("source") or "").strip()
            for item in sources
            if isinstance(item, dict) and item.get("status") in {"ok", "partial"} and _safe_int(item.get("returned")) > 0
        }
    return {
        "topic": review.topic,
        "provider": str(strategy.get("provider") or ""),
        "configured_sources": configured_sources,
        "configured_source_count": len(configured_sources),
        "sources_with_success": len([source for source in successful_sources if source]),
        "sources": sources,
        "query_results": query_results,
        "total_sources": len(sources),
        "rate_limited_sources": sum(1 for item in sources if item.get("rate_limited") is True),
        "failed_sources": sum(1 for item in sources if item.get("status") == "failed"),
        "cache_hits": sum(_safe_int(item.get("cache_hits")) for item in sources),
        "cache_misses": sum(_safe_int(item.get("cache_misses")) for item in sources),
        "stale_cache_uses": sum(_safe_int(item.get("stale_cache_uses")) for item in sources),
        "query_attempts": len(query_results),
        "query_successes": sum(1 for item in query_results if item.get("status") in {"ok", "offline_ranked"} and _safe_int(item.get("returned")) > 0),
        "query_failures": sum(1 for item in query_results if item.get("status") == "failed"),
        "query_rate_limits": sum(1 for item in query_results if item.get("rate_limited") is True or item.get("status") == "rate_limited"),
        "diagnostics": review.source_diagnostics,
    }


def render_literature_source_health_markdown(review: LiteratureReview) -> str:
    report = literature_source_health_report(review)
    lines = [
        f"# 文献源健康：{review.topic}",
        "",
        f"- 来源数：{report['total_sources']}",
        f"- 限流来源：{report['rate_limited_sources']}",
        f"- 失败来源：{report['failed_sources']}",
        f"- 缓存命中：{report['cache_hits']}",
        f"- 缓存未命中：{report['cache_misses']}",
        f"- 使用过期缓存：{report['stale_cache_uses']}",
        f"- Query 尝试/成功/失败/限流：{report['query_attempts']}/{report['query_successes']}/{report['query_failures']}/{report['query_rate_limits']}",
        "",
        "## 来源表",
        "| 来源 | 状态 | 查询数 | 返回 | 错误 | 限流 | 用时 | Cache hit/miss/stale |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for item in review.source_health or []:
        cache = f"{item.get('cache_hits', 0)}/{item.get('cache_misses', 0)}/{item.get('stale_cache_uses', 0)}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _table_cell(str(item.get("source") or "")),
                    _table_cell(str(item.get("status") or "")),
                    str(item.get("queries") or 0),
                    str(item.get("returned") or 0),
                    str(item.get("errors") or 0),
                    "yes" if item.get("rate_limited") is True else "no",
                    str(item.get("elapsed_seconds") or 0),
                    cache,
                ]
            )
            + " |"
        )
    query_results = report.get("query_results") if isinstance(report.get("query_results"), list) else []
    if query_results:
        lines.extend(
            [
                "",
                "## Query 执行表",
                "| 来源 | 状态 | 返回 | 限流 | Cache hit/miss/stale | 检索式 | 错误 |",
                "| --- | --- | ---: | --- | --- | --- | --- |",
            ]
        )
        for item in query_results:
            if not isinstance(item, dict):
                continue
            cache = f"{item.get('cache_hits', 0)}/{item.get('cache_misses', 0)}/{item.get('stale_cache_uses', 0)}"
            lines.append(
                "| "
                + " | ".join(
                    [
                        _table_cell(str(item.get("source") or "")),
                        _table_cell(str(item.get("status") or "")),
                        str(item.get("returned") or 0),
                        "yes" if item.get("rate_limited") is True else "no",
                        cache,
                        "`" + _table_cell(str(item.get("query") or "")) + "`",
                        _table_cell(str(item.get("error") or "-")),
                    ]
                )
                + " |"
            )
    if review.source_diagnostics:
        lines.extend(["", "## 原始诊断"])
        lines.extend(f"- {item}" for item in review.source_diagnostics)
    return "\n".join(lines)


def _build_review(
    topic: str,
    papers: list[Paper],
    llm: LLM,
    diagnostics: list[str],
    source_health: list[dict[str, Any]] | None = None,
    search_strategy: dict[str, Any] | None = None,
) -> LiteratureReview:
    synthesis = _llm_literature_synthesis(topic, papers, llm)
    themes = _as_str_list(synthesis.get("themes")) or _themes_from_papers(topic, papers)
    gaps = _as_str_list(synthesis.get("gaps")) or _gaps_from_papers(topic, papers)
    source_names = sorted({source for paper in papers for source in (paper.sources or [paper.source])})
    default_summary = (
        f"围绕“{topic}”，本阶段纳入 {len(papers)} 条候选文献，来源覆盖 {', '.join(source_names) or 'offline'}。"
        "这些结果用于建立研究背景、识别可执行空白，并为下一阶段 idea 生成提供可追溯证据。"
    )
    summary = str(synthesis.get("summary") or default_summary).strip()
    return LiteratureReview(
        topic=topic,
        papers=papers,
        themes=themes,
        gaps=gaps,
        summary=summary,
        source_diagnostics=diagnostics,
        evidence_table=build_evidence_table(papers),
        source_health=source_health or [],
        search_strategy=search_strategy or {},
    )


def build_literature_review_from_papers(
    topic: str,
    papers: list[Paper],
    llm: LLM,
    diagnostics: list[str],
    source_health: list[dict[str, Any]] | None = None,
    search_strategy: dict[str, Any] | None = None,
) -> LiteratureReview:
    papers = annotate_evidence(papers, topic)
    return _build_review(topic, papers, llm, diagnostics, source_health=source_health, search_strategy=search_strategy)


def _llm_search_queries(topic: str, llm: LLM, max_queries: int) -> tuple[list[str], list[str]]:
    raw = complete_with_purpose(
        llm,
        "Academic search query planning. Return only valid JSON.",
        _search_query_prompt(topic, max_queries),
        stage="online_search_query_planning",
        purpose="academic search query planning",
        requires_validation=True,
    )
    data = _parse_json_object(raw)
    queries = _as_str_list(data.get("queries")) if data else []
    if not queries:
        record_validation_result(llm, stage="online_search_query_planning", valid=False, error="response contains no usable search queries")
        return _rule_search_queries(topic, max_queries), ["LLM 未返回可用检索式，使用规则检索式。"]
    record_validation_result(llm, stage="online_search_query_planning", valid=True)
    return queries[:max_queries], ["LLM 检索式: " + " | ".join(queries[:max_queries])]


def _search_query_prompt(topic: str, max_queries: int) -> str:
    schema = {"queries": ["English scholarly query, no broad single-word query"]}
    return "\n".join(
        [
            f"Research topic: {topic}",
            f"Generate {max_queries} high-precision English academic search queries.",
            "Prefer domain terms, methods, synonyms, and benchmark names. Avoid broad single words.",
            "For Chinese topics, translate and expand them into English scholarly terminology.",
            "Return strict JSON only. Schema:",
            json.dumps(schema, ensure_ascii=False),
        ]
    )


def _rule_search_queries(topic: str, max_queries: int) -> list[str]:
    lower = topic.lower()
    if "机械臂" in topic or "robot" in lower or "manipulator" in lower:
        queries = [
            "robot manipulator motion planning",
            "robot arm path planning obstacle avoidance",
            "manipulator trajectory planning sampling-based planning",
            "robot manipulator path planning RRT optimization",
        ]
    else:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", topic)
        queries = [topic, " ".join(tokens[:6])]
    deduped: list[str] = []
    for query in queries:
        if query and query not in deduped:
            deduped.append(query)
    return deduped[:max_queries]


def _literature_prompt(topic: str, papers: list[Paper]) -> str:
    snippets = []
    for paper in papers[:8]:
        snippets.append(
            f"- {paper.title} ({paper.year}, {paper.venue}; sources={paper.sources or [paper.source]}): {paper.abstract[:500]}"
        )
    return f"课题：{topic}\n候选文献：\n" + "\n".join(snippets) + "\n请用一句中文总结这些文献对该课题的启发。"


def _llm_literature_synthesis(topic: str, papers: list[Paper], llm: LLM) -> dict[str, Any]:
    raw = complete_with_purpose(
        llm,
        "Literature synthesis. You are a scientific research assistant. Return only valid JSON in Chinese.",
        _literature_json_prompt(topic, papers),
        stage="literature_synthesis",
        purpose="literature synthesis",
        requires_validation=True,
    )
    parsed = _parse_json_object(raw)
    if not parsed:
        record_validation_result(llm, stage="literature_synthesis", valid=False, error="response is not a valid literature synthesis object")
        return {"summary": raw.strip()}
    valid = bool(str(parsed.get("summary") or "").strip())
    record_validation_result(llm, stage="literature_synthesis", valid=valid, error="literature synthesis is missing summary")
    return parsed


def _literature_json_prompt(topic: str, papers: list[Paper]) -> str:
    rows = []
    for index, paper in enumerate(papers[:10], start=1):
        rows.append(
            {
                "index": index,
                "title": paper.title,
                "year": paper.year,
                "venue": paper.venue,
                "sources": paper.sources or [paper.source],
                "abstract": paper.abstract[:900],
                "evidence_note": paper.evidence_note,
            }
        )
    schema = {
        "summary": "150-250字中文综述，必须引用候选文献的总体证据，不要编造不存在的论文",
        "themes": ["3-5条中文主题，每条一句话"],
        "gaps": ["3-5条中文研究空白，每条必须可转化为后续实验或系统设计任务"],
    }
    return "\n".join(
        [
            f"课题：{topic}",
            "候选文献 JSON：",
            json.dumps(rows, ensure_ascii=False, indent=2),
            "输出必须是严格 JSON，不要 Markdown，不要代码块。Schema：",
            json.dumps(schema, ensure_ascii=False, indent=2),
        ]
    )


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _themes_from_papers(topic: str, papers: list[Paper]) -> list[str]:
    domain_themes = _domain_themes(topic)
    if domain_themes:
        return domain_themes
    text = " ".join(f"{paper.title} {paper.abstract}" for paper in papers).lower()
    themes = [
        "多源检索、去重和结构化证据表是科研 agent 第一阶段的基础设施，后续结论应能追溯到具体文献。",
        "闭环科研系统必须保留文献、idea、实验计划、结果和论文草稿等中间产物，才能支持复现、审计和人工接管。",
    ]
    if any(term in text for term in ["agent", "autonomous", "automated", "tool"]):
        themes.append("工具增强和明确的执行边界是科研 agent 从文本生成走向可执行研究流程的关键。")
    if any(term in text for term in ["benchmark", "evaluation", "experiment", "dataset"]):
        themes.append("可度量 benchmark、重复实验和统计分析应优先接入，因为它们能给自动科研闭环提供清晰反馈信号。")
    return themes[:4]


def _gaps_from_papers(topic: str, papers: list[Paper]) -> list[str]:
    domain_gaps = _domain_gaps(topic)
    if domain_gaps:
        return domain_gaps
    has_benchmark = any("benchmark" in f"{paper.title} {paper.abstract}".lower() for paper in papers)
    gaps = [
        "现有自动科研系统常展示端到端 demo，但对失败案例、消融实验、可复现环境和成本边界报告不足。",
        "idea 的新颖性缺少可操作评估标准，通常没有和文献空白、baseline、实验预算绑定。",
        "自主执行实验的安全边界仍不清晰，尤其是命令权限、资源限制、数据访问和结果可信度。",
    ]
    if not has_benchmark:
        gaps.append("当前候选文献中 benchmark 线索不足，下一步需要主动寻找可重复、低成本、指标清楚的评测任务。")
    return gaps


def _domain_themes(topic: str) -> list[str]:
    lower = topic.lower()
    if "机械臂" in topic or "manipulator" in lower or ("robot" in lower and ("path" in lower or "motion" in lower)):
        return [
            "机械臂路径规划通常需要同时比较采样规划、轨迹优化和混合方法，不能只看单一算法输出。",
            "OMPL、MoveIt benchmark、狭窄通道和杂乱抓取场景可以作为可复现实验任务来源。",
            "评价指标应覆盖规划成功率、规划耗时、路径长度、碰撞率、轨迹平滑性和最小安全距离。",
            "RRT/RRT*/PRM 与 CHOMP/STOMP/TrajOpt 是后续 idea 和实验计划必须显式比较的 baseline。"
        ]
    if "轴承" in topic or "bearing" in lower or "fault" in lower:
        return [
            "轴承故障诊断需要区分同工况随机划分、跨负载泛化和跨数据集迁移，避免数据泄漏导致虚高结果。",
            "CWRU、Paderborn、XJTU-SY 和 IMS 等公开数据集可作为可复现实验入口。",
            "指标应至少包含 accuracy、macro_f1、混淆矩阵、跨工况准确率、噪声鲁棒性和推理延迟。",
            "传统手工特征+SVM、1D-CNN、ResNet/LSTM/Transformer 和 domain adaptation 方法应作为 baseline。"
        ]
    return []


def _domain_gaps(topic: str) -> list[str]:
    lower = topic.lower()
    if "机械臂" in topic or "manipulator" in lower or ("robot" in lower and ("path" in lower or "motion" in lower)):
        return [
            "很多路径规划结果只在少量简单障碍场景展示，缺少狭窄通道、杂乱场景和不可达任务上的失败分类。",
            "候选方法需要与 RRT*、PRM、CHOMP、STOMP 或 TrajOpt 在相同起终位姿、障碍布局和随机种子下公平比较。",
            "仅报告成功路径不足以支撑改进结论，必须同时报告规划时间、路径长度、碰撞率、平滑性和最小安全距离。",
            "仿真结果与真实机械臂约束之间可能存在差距，需要显式记录关节限位、碰撞模型和控制可执行性。"
        ]
    if "轴承" in topic or "bearing" in lower or "fault" in lower:
        return [
            "同一工况随机划分容易产生数据泄漏，后续实验必须设置跨负载或跨数据集划分。",
            "很多模型只报告 accuracy，缺少 macro_f1、混淆矩阵和少数类故障表现。",
            "噪声、转速变化和样本不足条件下的鲁棒性仍需系统评估。",
            "候选方法需要与手工特征+SVM、1D-CNN、ResNet 或 Transformer baseline 在固定划分和重复种子下比较。"
        ]
    return []


def _rank_offline(topic: str, seed_queries: list[str] | None = None) -> list[Paper]:
    return rank_papers(OFFLINE_CORPUS, topic, seed_queries or [])


def _table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _query_results(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        results = source.get("query_results") if isinstance(source.get("query_results"), list) else []
        for item in results:
            if isinstance(item, dict):
                rows.append(dict(item))
    return rows


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
