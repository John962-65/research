from __future__ import annotations

import unittest

from research_agent.literature_quality import assess_literature_quality, filter_review_by_quality, render_literature_quality_markdown
from research_agent.models import LiteratureReview, Paper


class LiteratureQualityTest(unittest.TestCase):
    def test_quality_filter_excludes_weak_metadata_and_unrelated_candidate(self) -> None:
        strong = Paper(
            title="Robot manipulator motion planning with RRT star benchmark",
            authors=["Ada Lovelace"],
            year=2024,
            venue="Robotics Journal",
            url="https://example.test/robot",
            abstract="Robot manipulator motion planning benchmark with obstacle avoidance, RRT star baseline, planning time, path length, and collision rate.",
            relevance=0.9,
            source="openalex",
            sources=["openalex", "semantic_scholar"],
            doi="10.1234/robot",
            citation_count=120,
        )
        weak = Paper(
            title="A generic education survey",
            authors=[],
            year=0,
            venue="Crossref",
            url="",
            abstract="Short note.",
            relevance=0.1,
            source="crossref",
            sources=["crossref"],
        )
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[weak, strong],
            themes=["机械臂路径规划需要可复现 benchmark。"],
            gaps=["需要比较 RRT* baseline。"],
            summary="测试",
        )

        report = assess_literature_quality(review, min_keep=1)
        curated = filter_review_by_quality(review, report)
        rendered = render_literature_quality_markdown(report)

        self.assertEqual(curated.papers[0].title, strong.title)
        self.assertEqual(len(curated.papers), 1)
        self.assertTrue(any(item.decision == "exclude" for item in report.items))
        self.assertIn("质量筛选", rendered)
        self.assertIn("Robot manipulator", rendered)

    def test_quality_filter_does_not_select_excluded_candidates_to_fill_min_keep(self) -> None:
        strong = Paper(
            title="Robot manipulator motion planning with RRT star benchmark",
            authors=["Ada Lovelace"],
            year=2024,
            venue="IEEE Robotics and Automation Letters",
            url="https://example.test/robot",
            abstract="Robot manipulator motion planning benchmark with obstacle avoidance, RRT star baseline, planning time, path length, and collision rate.",
            relevance=0.9,
            source="openalex",
            sources=["openalex", "semantic_scholar"],
            doi="10.1234/robot",
            citation_count=120,
        )
        weak = [
            Paper(
                title=f"Unrelated education note {index}",
                authors=[],
                year=2024,
                venue="Crossref",
                url="",
                abstract="Short note.",
                relevance=0.95,
                source="crossref",
                sources=["crossref"],
            )
            for index in range(4)
        ]
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[strong, *weak],
            themes=[],
            gaps=[],
            summary="测试",
        )

        report = assess_literature_quality(review, min_keep=5)
        curated = filter_review_by_quality(review, report)

        self.assertEqual(report.selected_papers, 1)
        self.assertEqual([paper.title for paper in curated.papers], [strong.title])
        self.assertTrue(all(item.decision == "exclude" for item in report.items if item.title != strong.title))
        self.assertTrue(any("拒绝用 exclude 文献填充上下文" in item for item in report.warnings))

    def test_quality_demotes_high_relevance_unverifiable_thin_crossref_record(self) -> None:
        weak = Paper(
            title="Robot manipulator motion planning benchmark",
            authors=[],
            year=2025,
            venue="Crossref",
            url="",
            abstract="Short note.",
            relevance=0.99,
            source="crossref",
            sources=["crossref"],
        )
        review = LiteratureReview(
            topic="robot manipulator motion planning benchmark",
            papers=[weak],
            themes=[],
            gaps=[],
            summary="测试",
        )

        report = assess_literature_quality(review, min_keep=1)
        curated = filter_review_by_quality(review, report)

        item = report.items[0]
        self.assertEqual(item.decision, "exclude")
        self.assertFalse(item.selected)
        self.assertLessEqual(item.quality_score, 0.40)
        self.assertIn("unverifiable thin record", item.reasons)
        self.assertEqual(curated.papers, [])

    def test_quality_report_scores_evidence_confidence_for_multi_source_grounding(self) -> None:
        papers = [
            Paper(
                title=f"Robot manipulator motion planning benchmark paper {index}",
                authors=["Ada Lovelace"],
                year=2021 + index,
                venue="Robotics Journal",
                url=f"https://example.test/robot/{index}",
                abstract=(
                    "Robot manipulator motion planning benchmark with obstacle avoidance, "
                    "RRT star, CHOMP, STOMP, TrajOpt, OMPL, planning time, path length, "
                    "collision rate, and reproducible baseline evaluation."
                ),
                relevance=0.92,
                source="openalex",
                sources=["openalex", "semantic_scholar", "crossref"],
                doi=f"10.1234/robot.{index}",
                citation_count=100 + index,
            )
            for index in range(5)
        ]
        review = LiteratureReview(
            topic="robot manipulator motion planning benchmark",
            papers=papers,
            themes=["Robotics motion planning needs benchmark grounding."],
            gaps=["Compare sampling-based and trajectory optimization baselines."],
            summary="测试",
            source_health=[
                {"source": "openalex", "status": "ok", "returned": 5, "errors": 0, "rate_limited": False},
                {"source": "semantic_scholar", "status": "ok", "returned": 5, "errors": 0, "rate_limited": False},
                {"source": "crossref", "status": "ok", "returned": 5, "errors": 0, "rate_limited": False},
            ],
        )

        report = assess_literature_quality(review, min_keep=5)
        rendered = render_literature_quality_markdown(report)

        self.assertEqual(report.selected_papers, 5)
        self.assertEqual(report.confidence_status, "pass")
        self.assertGreaterEqual(report.confidence_score, 0.74)
        self.assertEqual(report.confidence_factors["source_diversity"], 3)
        self.assertGreaterEqual(report.confidence_factors["evidence_role_count"], 2)
        self.assertGreater(report.role_coverage["benchmark_dataset"], 0)
        self.assertGreater(report.role_coverage["baseline_method"], 0)
        self.assertIn("证据置信度：pass", rendered)
        self.assertIn("证据角色覆盖", rendered)
        self.assertIn("人工打开核心 URL/DOI", rendered)

    def test_quality_report_blocks_generic_high_metadata_pool_without_core_evidence_roles(self) -> None:
        papers = [
            Paper(
                title=f"Recent path planning applications overview {index}",
                authors=["Ada Lovelace"],
                year=2024,
                venue="IEEE Access",
                url=f"https://example.test/generic/{index}",
                abstract=(
                    "This recent article discusses path planning applications, engineering context, "
                    "and general deployment considerations, but does not name concrete public tasks, "
                    "comparator approaches, or reusable robot manipulator evaluation anchors."
                ),
                relevance=0.86,
                source="openalex",
                sources=["openalex", "semantic_scholar", "crossref"],
                doi=f"10.1234/generic.{index}",
                citation_count=50 + index,
            )
            for index in range(5)
        ]
        review = LiteratureReview(
            topic="robot manipulator motion planning benchmark",
            papers=papers,
            themes=[],
            gaps=[],
            summary="测试",
            source_health=[
                {"source": "openalex", "status": "ok", "returned": 5, "errors": 0, "rate_limited": False},
                {"source": "semantic_scholar", "status": "ok", "returned": 5, "errors": 0, "rate_limited": False},
                {"source": "crossref", "status": "ok", "returned": 5, "errors": 0, "rate_limited": False},
            ],
        )

        report = assess_literature_quality(review, min_keep=5)
        rendered = render_literature_quality_markdown(report)

        self.assertEqual(report.selected_papers, 5)
        self.assertNotEqual(report.confidence_status, "pass")
        self.assertLessEqual(report.confidence_score, 0.66)
        self.assertEqual(report.confidence_factors["evidence_role_count"], 1)
        self.assertIn("review_survey", report.missing_evidence_roles)
        self.assertIn("证据角色覆盖不足", " ".join(report.warnings))
        self.assertTrue(any("evidence roles" in item for item in report.recommended_actions))
        self.assertIn("recent_work", rendered)

    def test_quality_selection_adds_review_role_anchors_to_homogeneous_keep_pool(self) -> None:
        papers = [
            Paper(
                title=f"Recent robot path planning application note {index}",
                authors=["Ada Lovelace"],
                year=2024,
                venue="IEEE Access",
                url=f"https://example.test/generic/{index}",
                abstract=(
                    "This recent article discusses robot path planning applications, "
                    "engineering deployment, and general planning context for manipulators."
                ),
                relevance=0.88,
                source="openalex",
                sources=["openalex", "semantic_scholar"],
                doi=f"10.1234/generic.{index}",
                citation_count=60 + index,
            )
            for index in range(5)
        ]
        benchmark = Paper(
            title="OMPL benchmark dataset for robot manipulator motion planning",
            authors=["Ada Lovelace"],
            year=2020,
            venue="Robotics Benchmark Workshop",
            url="https://example.test/ompl",
            abstract=(
                "OMPL benchmark dataset and testbed with planning time, path length, "
                "collision rate, and repeatable robot arm evaluation tasks."
            ),
            relevance=0.55,
            source="openalex",
            sources=["openalex"],
            doi="10.1234/ompl",
            citation_count=10,
        )
        baseline = Paper(
            title="RRT CHOMP STOMP baseline methods for robot manipulator planning",
            authors=["Ada Lovelace"],
            year=2020,
            venue="Robotics Methods Workshop",
            url="https://example.test/baseline",
            abstract="RRT, CHOMP, STOMP, and TrajOpt baseline method comparison for robot manipulator planning.",
            relevance=0.55,
            source="openalex",
            sources=["openalex"],
            doi="10.1234/baseline",
            citation_count=10,
        )
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=[*papers, benchmark, baseline],
            themes=[],
            gaps=[],
            summary="测试",
        )

        report = assess_literature_quality(review, min_keep=5)
        selected = {item.title: item for item in report.items if item.selected}

        self.assertIn(benchmark.title, selected)
        self.assertIn(baseline.title, selected)
        self.assertEqual(selected[benchmark.title].decision, "review")
        self.assertEqual(selected[baseline.title].decision, "review")
        self.assertGreater(report.role_coverage["benchmark_dataset"], 0)
        self.assertGreater(report.role_coverage["baseline_method"], 0)

    def test_quality_selection_keeps_manual_url_seed_review_anchor(self) -> None:
        strong = [
            Paper(
                title=f"Iris benchmark paper {index}",
                authors=["Ada Lovelace"],
                year=2024,
                venue="Machine Learning",
                url=f"https://example.test/iris/{index}",
                abstract="UCI Iris classification benchmark provenance with accuracy and macro F1 evaluation.",
                relevance=0.9,
                source="openalex",
                sources=["openalex"],
                doi=f"10.1234/iris.{index}",
            )
            for index in range(5)
        ]
        manual = Paper(
            title="scikit-learn Decision Tree classifier interpretable nonlinear baseline",
            authors=["Manual seed"],
            year=0,
            venue="Manual seed",
            url="https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeClassifier.html",
            abstract=(
                "人工种子文献：https://scikit-learn.org/stable/modules/generated/"
                "sklearn.tree.DecisionTreeClassifier.html scikit-learn Decision Tree classifier "
                "interpretable nonlinear baseline"
            ),
            relevance=0.2,
            source="manual_seed",
            sources=["manual_seed"],
        )
        review = LiteratureReview("Iris classification benchmark smoke", [*strong, manual], themes=[], gaps=[], summary="测试")

        report = assess_literature_quality(review, min_keep=5)
        curated = filter_review_by_quality(review, report)
        manual_item = next(item for item in report.items if item.title == manual.title)

        self.assertEqual(manual_item.decision, "review")
        self.assertTrue(manual_item.selected)
        self.assertIn(manual.title, [paper.title for paper in curated.papers])

    def test_quality_roles_treat_open_motion_planning_library_as_benchmark_anchor(self) -> None:
        paper = Paper(
            title="The Open Motion Planning Library",
            authors=["Ioan Sucan", "Mark Moll", "Lydia Kavraki"],
            year=2012,
            venue="IEEE Robotics and Automation Magazine",
            url="https://doi.org/10.1109/MRA.2012.2205651",
            abstract=(
                "A software library for sampling based motion planning that implements "
                "RRT, PRM, and robot manipulation planners."
            ),
            relevance=0.86,
            source="openalex",
            sources=["openalex", "crossref"],
            doi="10.1109/MRA.2012.2205651",
            citation_count=900,
        )
        review = LiteratureReview("机械臂路径规划", [paper], themes=[], gaps=[], summary="测试")

        report = assess_literature_quality(review, min_keep=1)

        self.assertIn("benchmark_dataset", report.items[0].evidence_roles)
        self.assertIn("baseline_method", report.items[0].evidence_roles)
        self.assertEqual(report.role_coverage["benchmark_dataset"], 1)

    def test_quality_report_flags_low_confidence_when_sources_are_thin_and_limited(self) -> None:
        papers = [
            Paper(
                title=f"Generic path planning note {index}",
                authors=[],
                year=2020,
                venue="Crossref",
                url="",
                abstract="Short path planning note.",
                relevance=0.45,
                source="semantic_scholar",
                sources=["semantic_scholar"],
            )
            for index in range(3)
        ]
        review = LiteratureReview(
            topic="机械臂路径规划",
            papers=papers,
            themes=[],
            gaps=[],
            summary="测试",
            source_health=[
                {"source": "semantic_scholar", "status": "rate_limited", "returned": 0, "errors": 1, "rate_limited": True},
            ],
        )

        report = assess_literature_quality(review, min_keep=3)
        rendered = render_literature_quality_markdown(report)

        self.assertIn(report.confidence_status, {"weak", "block"})
        self.assertLess(report.confidence_score, 0.60)
        self.assertTrue(any("限流" in item for item in report.warnings))
        self.assertTrue(any("不要批准进入 idea/实验" in item for item in report.recommended_actions))
        self.assertIn("SEMANTIC_SCHOLAR_API_KEY", rendered)


if __name__ == "__main__":
    unittest.main()
