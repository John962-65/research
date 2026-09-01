from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.config import AgentConfig, LiteratureConfig, PaperGradeConfig
from research_agent.models import Paper
from research_agent.paper_grade_probe import (
    PAPER_GRADE_ONLINE_PROBE_JSON,
    PAPER_GRADE_ONLINE_PROBE_MD,
    build_paper_grade_online_probe,
    render_paper_grade_online_probe_markdown,
    write_paper_grade_online_probe_artifacts,
)


class PaperGradeProbeTest(unittest.TestCase):
    def test_online_probe_passes_with_two_sources_and_resolved_seed_metadata(self) -> None:
        config = AgentConfig(
            literature=LiteratureConfig(
                provider="online",
                sources=["semantic_scholar", "openalex", "crossref"],
                max_papers=6,
                max_search_queries=2,
                seed_papers=[
                    "10.1000/review robot motion planning review",
                    "10.1000/benchmark robot planning benchmark",
                    "10.1000/baseline RRT baseline planner",
                ],
            )
        )

        report = build_paper_grade_online_probe("robot motion planning", config, queries=["robot benchmark"], client_factory=PassingClient)
        rendered = render_paper_grade_online_probe_markdown(report)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["source_summary"]["successful_sources"], 2)
        self.assertEqual(report["seed_summary"]["metadata_resolved_seed_papers"], 3)
        self.assertEqual(report["candidate_count"], 1)
        self.assertIn("Paper-grade Online Probe", rendered)
        self.assertIn("doi_seed_metadata_resolution", rendered)

    def test_online_probe_requires_source_success_and_seed_metadata(self) -> None:
        config = AgentConfig(
            literature=LiteratureConfig(
                provider="online",
                sources=["semantic_scholar", "openalex", "crossref"],
                seed_papers=["10.1000/missing one", "10.1000/missing two", "10.1000/missing three"],
            )
        )

        report = build_paper_grade_online_probe("robot motion planning", config, client_factory=FailingClient)
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(checks["online_source_success"]["status"], "fail")
        self.assertEqual(checks["doi_seed_metadata_resolution"]["status"], "fail")
        self.assertEqual(report["seed_summary"]["metadata_unresolved_doi_url_seed_papers"], 3)

    def test_online_probe_uses_configured_paper_grade_thresholds(self) -> None:
        config = AgentConfig(
            literature=LiteratureConfig(
                provider="online",
                sources=["semantic_scholar", "openalex", "crossref"],
                seed_papers=[
                    "10.1000/review robot motion planning review",
                    "10.1000/benchmark robot planning benchmark",
                    "10.1000/baseline RRT baseline planner",
                ],
            ),
            paper_grade=PaperGradeConfig(
                min_literature_sources=4,
                min_successful_literature_sources=3,
                min_seed_papers=4,
                min_doi_url_seed_papers=4,
            ),
        )

        report = build_paper_grade_online_probe("robot motion planning", config, client_factory=PassingClient)
        checks = {item["name"]: item for item in report["checks"]}

        self.assertEqual(report["status"], "review_required")
        self.assertEqual(checks["online_source_count"]["status"], "fail")
        self.assertEqual(checks["online_source_count"]["detail"], "configured_sources=3/4")
        self.assertEqual(checks["online_source_success"]["status"], "fail")
        self.assertEqual(checks["online_source_success"]["detail"], "successful_sources=2/3")
        self.assertEqual(checks["doi_url_seed_count"]["status"], "fail")
        self.assertEqual(checks["doi_url_seed_count"]["detail"], "strong_seed_papers=3/4")
        self.assertEqual(checks["doi_seed_metadata_resolution"]["status"], "fail")
        self.assertEqual(checks["doi_seed_metadata_resolution"]["detail"], "metadata_resolved_seed_papers=3/4")

    def test_write_probe_artifacts(self) -> None:
        config = AgentConfig(
            literature=LiteratureConfig(
                provider="online",
                sources=["semantic_scholar", "openalex", "crossref"],
                seed_papers=[
                    "10.1000/review robot motion planning review",
                    "10.1000/benchmark robot planning benchmark",
                    "10.1000/baseline RRT baseline planner",
                ],
            )
        )
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            report = write_paper_grade_online_probe_artifacts("robot motion planning", config, out_dir, client_factory=PassingClient)

            self.assertEqual(report["status"], "pass")
            self.assertTrue((out_dir / PAPER_GRADE_ONLINE_PROBE_JSON).exists())
            self.assertTrue((out_dir / PAPER_GRADE_ONLINE_PROBE_MD).exists())

    def test_online_probe_redacts_diagnostic_secrets(self) -> None:
        config = AgentConfig(
            literature=LiteratureConfig(
                provider="online",
                sources=["semantic_scholar", "openalex", "crossref"],
                semantic_scholar_api_key="s2-secret",
                openalex_api_key="oa-secret",
                contact_email="lab@university.edu",
                seed_papers=["10.1000/leaky robot paper"],
            )
        )

        report = build_paper_grade_online_probe("robot motion planning", config, client_factory=LeakyClient)
        rendered = render_paper_grade_online_probe_markdown(report)
        encoded = f"{report}\n{rendered}"
        short_gateway_token = "sk-" + "LOCAL12345"

        self.assertNotIn("s2-secret", encoded)
        self.assertNotIn("oa-secret", encoded)
        self.assertNotIn("lab@university.edu", encoded)
        self.assertNotIn(short_gateway_token, encoded)
        self.assertIn("sk-***", encoded)
        self.assertIn("api_key=***", encoded)
        self.assertIn("mailto=***", encoded)
        self.assertIn("email=***", encoded)
        self.assertIn("x-api-key: ***", encoded)


class PassingClient:
    def __init__(self, config: LiteratureConfig) -> None:
        self.config = config
        self.source_health: list[dict[str, object]] = []

    def resolve_crossref_doi(self, doi: str) -> Paper:
        return Paper(
            title=f"Resolved {doi}",
            authors=["Ada"],
            year=2024,
            venue="Resolved Journal",
            url=f"https://doi.org/{doi}",
            abstract="Resolved robot motion planning benchmark metadata.",
            relevance=0.9,
            source="crossref",
            sources=["crossref"],
            doi=doi,
        )

    def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
        self.source_health = [
            {"source": "semantic_scholar", "status": "ok", "returned": 3, "rate_limited": False},
            {"source": "openalex", "status": "ok", "returned": 2, "rate_limited": False},
            {"source": "crossref", "status": "failed", "returned": 0, "rate_limited": False},
        ]
        return [
            Paper(
                title="Robot Motion Planning Benchmark",
                authors=["Ada"],
                year=2024,
                venue="Robotics",
                url="https://doi.org/10.1000/robot",
                abstract="Robot motion planning benchmark result.",
                relevance=0.9,
                source="semantic_scholar",
                sources=["semantic_scholar", "openalex"],
                doi="10.1000/robot",
            )
        ], ["fake online search"]


class FailingClient:
    def __init__(self, config: LiteratureConfig) -> None:
        self.config = config
        self.source_health: list[dict[str, object]] = []

    def resolve_crossref_doi(self, doi: str) -> None:
        return None

    def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
        self.source_health = [
            {"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "rate_limited": True},
            {"source": "openalex", "status": "failed", "returned": 0, "rate_limited": False},
            {"source": "crossref", "status": "ok", "returned": 0, "rate_limited": False},
        ]
        return [], ["fake empty search"]


class LeakyClient:
    def __init__(self, config: LiteratureConfig) -> None:
        self.config = config
        self.source_health: list[dict[str, object]] = []

    def resolve_crossref_doi(self, doi: str) -> Paper:
        short_gateway_token = "sk-" + "LOCAL12345"
        raise RuntimeError(f"metadata failed api_key=oa-secret bearer={short_gateway_token} email=lab@university.edu")

    def search(self, topic: str, queries: list[str]) -> tuple[list[Paper], list[str]]:
        self.source_health = [
            {
                "source": "openalex",
                "status": "failed",
                "returned": 0,
                "rate_limited": False,
                "query_results": [
                    {
                        "source": "openalex",
                        "status": "failed",
                        "error": "x-api-key: s2-secret mailto=lab@university.edu",
                    }
                ],
            }
        ]
        short_gateway_token = "sk-" + "LOCAL12345"
        return [], [f"online failed api_key=oa-secret token={short_gateway_token} mailto=lab@university.edu"]


if __name__ == "__main__":
    unittest.main()
