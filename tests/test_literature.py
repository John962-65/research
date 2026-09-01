from __future__ import annotations

from io import BytesIO
from tempfile import TemporaryDirectory
import urllib.error
import unittest

from research_agent.config import LiteratureConfig
from research_agent.literature import literature_source_health_report, parse_manual_seed_papers, render_literature_source_health_markdown, run_literature_review
from research_agent.literature_search_strategy import build_literature_search_strategy, render_literature_search_strategy_markdown
from research_agent.literature_sources import OnlineLiteratureClient, build_evidence_table, deduplicate_papers
from research_agent.literature_quality import assess_literature_quality
from research_agent.models import Paper


class LiteratureSourceTest(unittest.TestCase):
    def test_openalex_search_parses_work_metadata(self) -> None:
        class FakeOpenAlexClient(OnlineLiteratureClient):
            def _json(self, url, headers):
                return {
                    "results": [
                        {
                            "id": "https://openalex.org/W123",
                            "doi": "https://doi.org/10.1234/robot",
                            "display_name": "Robot manipulator motion planning with RRT",
                            "publication_year": 2024,
                            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
                            "primary_location": {
                                "landing_page_url": "https://example.test/paper",
                                "source": {"display_name": "Robotics Journal"},
                            },
                            "abstract_inverted_index": {
                                "Robot": [0],
                                "manipulator": [1],
                                "motion": [2],
                                "planning": [3],
                            },
                            "cited_by_count": 42,
                        }
                    ]
                }

        papers = FakeOpenAlexClient(LiteratureConfig()).search_openalex("robot manipulator motion planning", 5)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].source, "openalex")
        self.assertEqual(papers[0].doi, "10.1234/robot")
        self.assertEqual(papers[0].venue, "Robotics Journal")
        self.assertEqual(papers[0].citation_count, 42)
        self.assertEqual(papers[0].abstract, "Robot manipulator motion planning")

    def test_doi_metadata_falls_back_to_doi_org_csl(self) -> None:
        class FakeDoiClient(OnlineLiteratureClient):
            def _json(self, url, headers):
                if "crossref.org/works/" in url:
                    raise RuntimeError("crossref missing")
                return {
                    "title": "Iris",
                    "author": [{"literal": "R. A. Fisher"}],
                    "issued": {"date-parts": [[1936]]},
                    "DOI": "10.24432/C56C76",
                    "publisher": "UCI Machine Learning Repository",
                    "type": "dataset",
                    "URL": "https://archive.ics.uci.edu/dataset/53/iris",
                }

        paper = FakeDoiClient(LiteratureConfig()).resolve_doi_metadata("10.24432/C56C76")

        self.assertIsNotNone(paper)
        assert paper is not None
        self.assertEqual(paper.source, "doi")
        self.assertEqual(paper.doi, "10.24432/C56C76")
        self.assertEqual(paper.title, "Iris")
        self.assertIn("UCI", paper.venue)

    def test_online_sources_use_configured_credentials(self) -> None:
        class CaptureClient(OnlineLiteratureClient):
            def __init__(self, config):
                super().__init__(config)
                self.calls = []

            def _json(self, url, headers):
                self.calls.append((url, dict(headers)))
                if "semanticscholar" in url:
                    return {"data": []}
                return {"results": []}

        client = CaptureClient(
            LiteratureConfig(
                semantic_scholar_api_key="s2-secret",
                openalex_api_key="oa-secret",
                contact_email="lab@university.edu",
            )
        )

        client.search_semantic_scholar("robot manipulator motion planning", 1)
        client.search_openalex("robot manipulator motion planning", 1)

        semantic_url, semantic_headers = client.calls[0]
        openalex_url, _ = client.calls[1]
        self.assertIn("semanticscholar", semantic_url)
        self.assertEqual(semantic_headers["x-api-key"], "s2-secret")
        self.assertIn("mailto=lab%40university.edu", openalex_url)
        self.assertIn("api_key=oa-secret", openalex_url)

    def test_online_sources_ignore_placeholder_credentials(self) -> None:
        class CaptureClient(OnlineLiteratureClient):
            def __init__(self, config):
                super().__init__(config)
                self.calls = []

            def _json(self, url, headers):
                self.calls.append((url, dict(headers)))
                if "semanticscholar" in url:
                    return {"data": []}
                if "crossref.org" in url:
                    return {"message": {"items": []}}
                if "eutils.ncbi.nlm.nih.gov" in url:
                    return {"esearchresult": {"idlist": []}}
                return {"results": []}

        client = CaptureClient(
            LiteratureConfig(
                semantic_scholar_api_key="<api-key>",
                openalex_api_key="replace-me",
                contact_email="agent@example.org",
            )
        )

        client.search_semantic_scholar("robot manipulator motion planning", 1)
        client.search_openalex("robot manipulator motion planning", 1)
        client.search_crossref("robot manipulator motion planning", 1)
        client.search_pubmed("robot manipulator motion planning", 1)

        rendered_calls = "\n".join(f"{url} {headers}" for url, headers in client.calls)
        self.assertNotIn("x-api-key", rendered_calls)
        self.assertNotIn("api_key=", rendered_calls)
        self.assertNotIn("mailto=", rendered_calls)
        self.assertNotIn("email=", rendered_calls)
        self.assertNotIn("<api-key>", rendered_calls)
        self.assertNotIn("replace-me", rendered_calls)
        self.assertNotIn("agent%40example.org", rendered_calls)

    def test_online_search_diagnostics_redact_credentials(self) -> None:
        class FailingClient(OnlineLiteratureClient):
            def search_openalex(self, topic: str, limit: int) -> list[Paper]:
                raise RuntimeError("api_key=oa-secret x-api-key: s2-secret mailto=lab@university.edu")

        client = FailingClient(
            LiteratureConfig(
                provider="online",
                sources=["openalex"],
                max_search_queries=1,
                openalex_api_key="oa-secret",
                semantic_scholar_api_key="s2-secret",
                contact_email="lab@university.edu",
            )
        )

        _, diagnostics = client.search("robot manipulator motion planning", ["robot planner"])
        encoded = "\n".join([*diagnostics, str(client.source_health)])

        self.assertIn("api_key=***", encoded)
        self.assertIn("x-api-key: ***", encoded)
        self.assertIn("mailto=***", encoded)
        self.assertNotIn("oa-secret", encoded)
        self.assertNotIn("s2-secret", encoded)
        self.assertNotIn("lab@university.edu", encoded)

    def test_http_error_details_redact_credentials(self) -> None:
        class HttpErrorClient(OnlineLiteratureClient):
            def _network_bytes(self, url, headers):
                raise urllib.error.HTTPError(
                    url,
                    500,
                    "server error",
                    {},
                    BytesIO(b"api_key=oa-secret x-api-key: s2-secret email=lab@university.edu"),
                )

        client = HttpErrorClient(
            LiteratureConfig(
                openalex_api_key="oa-secret",
                semantic_scholar_api_key="s2-secret",
                contact_email="lab@university.edu",
                cache_enabled=False,
            )
        )

        with self.assertRaises(RuntimeError) as ctx:
            client._bytes("https://example.test/api?api_key=oa-secret", {})

        message = str(ctx.exception)
        self.assertIn("api_key=***", message)
        self.assertIn("x-api-key: ***", message)
        self.assertIn("email=***", message)
        self.assertNotIn("oa-secret", message)
        self.assertNotIn("s2-secret", message)
        self.assertNotIn("lab@university.edu", message)

    def test_http_cache_reuses_cached_response(self) -> None:
        with TemporaryDirectory() as tmp:
            class CacheClient(OnlineLiteratureClient):
                def __init__(self, config):
                    super().__init__(config)
                    self.calls = 0

                def _network_bytes(self, url, headers):
                    self.calls += 1
                    return b'{"ok": true}'

            client = CacheClient(LiteratureConfig(cache_dir=f"{tmp}/cache", cache_enabled=True, cache_ttl_seconds=3600))

            first = client._bytes("https://example.test/api?q=robot", {})
            second = client._bytes("https://example.test/api?q=robot", {})

            self.assertEqual(first, second)
            self.assertEqual(client.calls, 1)
            self.assertEqual(client._cache_stats["hits"], 1)
            self.assertEqual(client._cache_stats["misses"], 1)
            self.assertEqual(client._cache_stats["writes"], 1)

    def test_crossref_doi_resolution_parses_work_metadata(self) -> None:
        class FakeCrossrefClient(OnlineLiteratureClient):
            def _json(self, url, headers):
                return {
                    "message": {
                        "DOI": "10.1234/robot",
                        "title": ["Resolved robot planner"],
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "issued": {"date-parts": [[2024]]},
                        "container-title": ["Robotics Journal"],
                        "URL": "https://doi.org/10.1234/robot",
                        "abstract": "<jats:p>Resolved abstract.</jats:p>",
                        "is-referenced-by-count": 12,
                    }
                }

        paper = FakeCrossrefClient(LiteratureConfig()).resolve_crossref_doi("10.1234/robot")

        self.assertIsNotNone(paper)
        self.assertEqual(paper.title, "Resolved robot planner")
        self.assertEqual(paper.authors, ["Ada Lovelace"])
        self.assertEqual(paper.year, 2024)
        self.assertEqual(paper.venue, "Robotics Journal")
        self.assertEqual(paper.citation_count, 12)

    def test_online_search_enriches_thin_doi_records_with_crossref_metadata(self) -> None:
        class EnrichingClient(OnlineLiteratureClient):
            def __init__(self, config):
                super().__init__(config)
                self.resolved_dois = []

            def search_openalex(self, topic: str, limit: int) -> list[Paper]:
                return [
                    Paper(
                        title="Robot Manipulator Motion Planning Benchmark",
                        authors=[],
                        year=0,
                        venue="OpenAlex",
                        url="https://example.test/openalex",
                        abstract="Robot manipulator motion planning benchmark.",
                        relevance=0.82,
                        source="openalex",
                        sources=["openalex"],
                        doi="10.1234/robot.benchmark",
                    )
                ]

            def search_crossref(self, topic: str, limit: int) -> list[Paper]:
                return []

            def resolve_crossref_doi(self, doi: str) -> Paper | None:
                self.resolved_dois.append(doi)
                return Paper(
                    title="Robot Manipulator Motion Planning Benchmark",
                    authors=["Ada Lovelace"],
                    year=2024,
                    venue="Robotics Journal",
                    url=f"https://doi.org/{doi}",
                    abstract=(
                        "Robot manipulator motion planning benchmark with RRT star, CHOMP, "
                        "OMPL, path length, planning time, and collision avoidance evaluation."
                    ),
                    relevance=0.58,
                    source="crossref",
                    sources=["crossref"],
                    doi=doi,
                    citation_count=33,
                )

        client = EnrichingClient(LiteratureConfig(provider="online", sources=["openalex", "crossref"], max_papers=5, max_search_queries=1))
        papers, diagnostics = client.search("robot manipulator motion planning", ["robot manipulator OMPL benchmark"])

        self.assertEqual(client.resolved_dois, ["10.1234/robot.benchmark"])
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].source, "openalex")
        self.assertEqual(papers[0].sources, ["crossref", "openalex"])
        self.assertEqual(papers[0].authors, ["Ada Lovelace"])
        self.assertEqual(papers[0].year, 2024)
        self.assertEqual(papers[0].venue, "Robotics Journal")
        self.assertEqual(papers[0].citation_count, 33)
        self.assertIn("OMPL", papers[0].abstract)
        self.assertTrue(any("crossref_enrichment" in item and "补强 1 条" in item for item in diagnostics))

    def test_deduplicate_merges_doi_sources_and_best_metadata(self) -> None:
        crossref = Paper(
            title="Auditable Autonomous Research Agents",
            authors=["A. Author"],
            year=2025,
            venue="Crossref Journal",
            url="https://doi.org/10.1234/example",
            abstract="Short abstract.",
            relevance=0.6,
            source="crossref",
            sources=["crossref"],
            doi="10.1234/example",
            citation_count=3,
        )
        semantic = Paper(
            title="Auditable Autonomous Research Agents",
            authors=["A. Author", "B. Author"],
            year=2025,
            venue="Semantic Scholar",
            url="https://example.test/paper",
            abstract="Longer abstract with benchmark and evaluation details.",
            relevance=0.8,
            source="semantic_scholar",
            sources=["semantic_scholar"],
            doi="10.1234/example",
            citation_count=11,
        )

        merged = deduplicate_papers([crossref, semantic])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].doi, "10.1234/example")
        self.assertEqual(merged[0].citation_count, 11)
        self.assertEqual(merged[0].sources, ["crossref", "semantic_scholar"])
        self.assertEqual(merged[0].source, "semantic_scholar")
        self.assertIn("benchmark", merged[0].abstract)

    def test_deduplicate_merges_title_match_when_crossref_adds_missing_doi(self) -> None:
        openalex = Paper(
            title="Robot Manipulator Motion Planning Benchmark",
            authors=["Ada Lovelace", "B. Author"],
            year=2024,
            venue="Robotics Journal",
            url="https://example.test/robot-planner",
            abstract="Robot manipulator motion planning benchmark with RRT star, CHOMP, OMPL, path length, planning time, and collision checks.",
            relevance=0.84,
            source="openalex",
            sources=["openalex"],
            doi="",
            citation_count=25,
        )
        crossref = Paper(
            title="Robot Manipulator Motion Planning Benchmark",
            authors=["Ada Lovelace"],
            year=2024,
            venue="Crossref",
            url="https://doi.org/10.1234/robot.benchmark",
            abstract="Short record.",
            relevance=0.56,
            source="crossref",
            sources=["crossref"],
            doi="10.1234/robot.benchmark",
            citation_count=5,
        )

        merged = deduplicate_papers([openalex, crossref])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].doi, "10.1234/robot.benchmark")
        self.assertEqual(merged[0].source, "openalex")
        self.assertEqual(merged[0].sources, ["crossref", "openalex"])
        self.assertEqual(merged[0].venue, "Robotics Journal")
        self.assertEqual(merged[0].url, "https://example.test/robot-planner")
        self.assertIn("OMPL", merged[0].abstract)

    def test_evidence_table_uses_structured_fields(self) -> None:
        paper = Paper(
            title="Tool-augmented research agents",
            authors=[],
            year=2024,
            venue="arXiv",
            url="https://arxiv.org/abs/0000.00000",
            abstract="Tool use enables automated experiment planning.",
            relevance=0.72,
            source="arxiv",
            sources=["arxiv"],
            external_ids={"arXiv": "0000.00000"},
        )

        table = build_evidence_table([paper])

        self.assertEqual(table[0]["title"], "Tool-augmented research agents")
        self.assertEqual(table[0]["sources"], "arxiv")
        self.assertIn("agent", table[0]["evidence_note"])

    def test_online_mode_falls_back_when_sources_are_empty(self) -> None:
        config = LiteratureConfig(provider="online", max_papers=2, sources=["unknown_source"])
        review = run_literature_review("auditable autonomous research agents", config, type("NoopLLM", (), {"complete": lambda self, system, user: "测试 LLM 输出"})())

        self.assertEqual(len(review.papers), 2)
        self.assertTrue(any("未知文献源" in item for item in review.source_diagnostics))
        self.assertTrue(any("回退" in item for item in review.source_diagnostics))
        self.assertTrue(review.evidence_table)
        self.assertTrue(review.source_health)
        rendered = render_literature_source_health_markdown(review)
        report = literature_source_health_report(review)
        self.assertIn("文献源健康", rendered)
        self.assertIn("Query 执行表", rendered)
        self.assertGreaterEqual(report["total_sources"], 1)
        self.assertGreaterEqual(report["query_attempts"], 1)
        self.assertTrue(report["query_results"])
        self.assertTrue(any(item.get("source") == "unknown_source" for item in review.source_health))

    def test_offline_robotics_topic_uses_motion_planning_corpus_and_gaps(self) -> None:
        config = LiteratureConfig(provider="offline", max_papers=4)
        review = run_literature_review("机械臂路径规划", config, type("NoopLLM", (), {"complete": lambda self, system, user: "测试 LLM 输出"})())

        titles = " ".join(paper.title for paper in review.papers)

        self.assertIn("Motion Planning", titles)
        self.assertTrue(any("RRT" in gap or "TrajOpt" in gap for gap in review.gaps))
        self.assertTrue(any("规划成功率" in theme or "OMPL" in theme for theme in review.themes))
        self.assertTrue(review.search_strategy.get("selected_queries"))
        self.assertTrue(any("robot manipulator" in query for query in review.search_strategy.get("selected_queries", [])))

    def test_search_strategy_prefers_domain_queries_and_renders_risks(self) -> None:
        strategy = build_literature_search_strategy(
            "机械臂路径规划",
            LiteratureConfig(provider="online", max_search_queries=5, sources=["semantic_scholar", "crossref"]),
            seed_queries=["robot"],
            llm_queries=["robot manipulator motion planning survey"],
        )
        rendered = render_literature_search_strategy_markdown(strategy)

        self.assertEqual(len(strategy.selected_queries), 5)
        self.assertEqual(strategy.status, "pass")
        self.assertGreaterEqual(strategy.quality_score, 0.78)
        self.assertIn("survey", strategy.selected_intents)
        self.assertIn("baseline", strategy.selected_intents)
        self.assertIn("benchmark", strategy.selected_intents)
        self.assertIn("recent", strategy.selected_intents)
        self.assertFalse(strategy.missing_required_intents)
        self.assertTrue(any("CHOMP" in query or "RRT" in query for query in strategy.selected_queries))
        self.assertTrue(any("survey" in query.lower() or "review" in query.lower() for query in strategy.selected_queries))
        self.assertTrue(any("recent" in query.lower() or "2024" in query for query in strategy.selected_queries))
        self.assertTrue(any(item.query == "robot" and item.risk == "too_broad" for item in strategy.candidates))
        self.assertIn("文献检索策略", rendered)
        self.assertIn("策略质量分", rendered)
        self.assertIn("too_broad", rendered)

    def test_search_strategy_requires_survey_and_recent_for_domain_topics_when_capacity_allows(self) -> None:
        strategy = build_literature_search_strategy(
            "机械臂路径规划",
            LiteratureConfig(provider="online", max_search_queries=4, sources=["semantic_scholar", "crossref"]),
            seed_queries=["robot manipulator motion planning"],
            llm_queries=[],
        )

        self.assertEqual(strategy.status, "pass")
        self.assertFalse(strategy.missing_required_intents)
        self.assertIn("survey", strategy.selected_intents)
        self.assertIn("baseline", strategy.selected_intents)
        self.assertIn("benchmark", strategy.selected_intents)
        self.assertIn("recent", strategy.selected_intents)
        self.assertTrue(any("recent" in query.lower() or "2024" in query for query in strategy.selected_queries))

    def test_search_strategy_flags_missing_intents_before_online_search(self) -> None:
        strategy = build_literature_search_strategy(
            "robot manipulator motion planning",
            LiteratureConfig(provider="online", max_search_queries=2, sources=["crossref"]),
            seed_queries=["robot"],
            llm_queries=[],
        )
        rendered = render_literature_search_strategy_markdown(strategy)

        self.assertEqual(strategy.status, "pass")
        self.assertFalse(strategy.missing_required_intents)
        self.assertIn("survey", strategy.selected_intents)
        self.assertIn("baseline", strategy.selected_intents)
        self.assertNotIn("robot", strategy.selected_queries)
        self.assertTrue(any(item.query == "robot" and item.risk == "too_broad" and not item.selected for item in strategy.candidates))
        self.assertTrue(any("benchmark" in item.lower() or "近期工作" in item for item in strategy.recommendations))
        self.assertIn("缺失必需意图", rendered)

    def test_extra_search_queries_are_prioritized_in_strategy(self) -> None:
        config = LiteratureConfig(
            provider="offline",
            max_search_queries=5,
            extra_search_queries=["robot manipulator OMPL benchmark RRT* CHOMP"],
        )
        review = run_literature_review("机械臂路径规划", config, type("NoopLLM", (), {"complete": lambda self, system, user: "测试 LLM 输出"})())

        self.assertIn("robot manipulator OMPL benchmark RRT* CHOMP", review.search_strategy.get("selected_queries", []))
        human_candidates = [item for item in review.search_strategy.get("candidates", []) if item.get("origin") == "human"]
        self.assertTrue(human_candidates)

    def test_manual_seed_papers_are_included_and_quality_marked(self) -> None:
        config = LiteratureConfig(
            provider="offline",
            max_papers=3,
            seed_papers=[
                "10.1177/0278364911406761 Sampling-based Algorithms for Optimal Motion Planning",
                "Custom manipulator benchmark paper 2025",
            ],
        )
        review = run_literature_review("机械臂路径规划", config, type("NoopLLM", (), {"complete": lambda self, system, user: "测试 LLM 输出"})())
        quality = assess_literature_quality(review)

        manual = [paper for paper in review.papers if "manual_seed" in paper.sources]

        self.assertEqual(len(manual), 2)
        self.assertTrue(any(paper.doi == "10.1177/0278364911406761" for paper in manual))
        self.assertTrue(any("manual_seed" in row.get("sources", "") for row in review.evidence_table))
        self.assertTrue(any("manual seed" in item.reasons for item in quality.items))

    def test_manual_seed_doi_can_be_resolved_by_injected_resolver(self) -> None:
        def resolver(doi: str) -> Paper:
            return Paper(
                title="Resolved Robot Motion Planning Paper",
                authors=["Ada Lovelace"],
                year=2024,
                venue="Resolved Journal",
                url=f"https://doi.org/{doi}",
                abstract="Resolved metadata for robot motion planning and benchmark evaluation.",
                relevance=0.72,
                source="crossref",
                sources=["crossref"],
                doi=doi,
                citation_count=7,
            )

        papers, diagnostics = parse_manual_seed_papers(["10.1234/resolved"], resolver=resolver)

        self.assertEqual(papers[0].title, "Resolved Robot Motion Planning Paper")
        self.assertEqual(papers[0].authors, ["Ada Lovelace"])
        self.assertEqual(papers[0].venue, "Resolved Journal")
        self.assertEqual(papers[0].sources, ["crossref", "manual_seed"])
        self.assertTrue(any("已解析元数据" in item for item in diagnostics))

    def test_manual_seed_doi_merges_with_offline_metadata(self) -> None:
        config = LiteratureConfig(
            provider="offline",
            max_papers=2,
            seed_papers=["10.1177/0278364911406761"],
        )

        review = run_literature_review("机械臂路径规划", config, type("NoopLLM", (), {"complete": lambda self, system, user: "测试 LLM 输出"})())
        paper = next(item for item in review.papers if item.doi == "10.1177/0278364911406761")

        self.assertEqual(paper.title, "Sampling-based Algorithms for Optimal Motion Planning")
        self.assertIn("Karaman", paper.authors)
        self.assertEqual(paper.venue, "The International Journal of Robotics Research")
        self.assertIn("manual_seed", paper.sources)
        self.assertIn("offline", paper.sources)


if __name__ == "__main__":
    unittest.main()
