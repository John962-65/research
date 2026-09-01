from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research_agent.open_source_lessons import build_open_source_lessons, refresh_github_project_evidence, render_open_source_lessons_markdown, write_open_source_lessons_artifacts


class OpenSourceLessonsTest(unittest.TestCase):
    def test_open_source_lessons_capture_project_constraints(self) -> None:
        report = build_open_source_lessons("机械臂路径规划")
        rendered = render_open_source_lessons_markdown(report)

        self.assertEqual(report.status, "constraints_ready")
        self.assertTrue(any(profile.name == "SakanaAI/AI-Scientist-v2" for profile in report.profiles))
        self.assertTrue(any(profile.evidence_targets for profile in report.profiles))
        self.assertEqual(len(report.project_evidence), len(report.profiles))
        self.assertTrue(all(item.repository_url.startswith("https://github.com/") for item in report.project_evidence))
        self.assertTrue(all(item.evidence_targets for item in report.project_evidence))
        self.assertTrue(any(profile.name == "Future-House/PaperQA2" for profile in report.profiles))
        self.assertTrue(any(profile.name == "OpenScholar" for profile in report.profiles))
        self.assertTrue(any("MLAgentBench" in profile.name for profile in report.profiles))
        self.assertTrue(any(item.lesson_id == "sandbox_generated_code" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "retrieval_rerank_before_synthesis" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "query_execution_coverage_audit" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "repair_context_on_resume" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "benchmark_result_schema_contract" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "runtime_cost_observability" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "runtime_cost_observability" and "run_economics" in item.pipeline_targets for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "source_project_provenance" for item in report.lessons))
        self.assertTrue(any(item.lesson_id == "domain_benchmark_before_claims" for item in report.lessons))
        self.assertIn("Open-Source Project Lessons", rendered)
        self.assertIn("项目来源证据", rendered)
        self.assertIn("built_in_catalog", rendered)
        self.assertIn("AI-Scientist-v2", report.agent_prompt_text)
        self.assertIn("provenance", report.agent_prompt_text)

    def test_open_source_lessons_accept_external_project_evidence(self) -> None:
        def verifier(profile):
            return {
                "project_name": profile.name,
                "repository_url": profile.url,
                "status": "verified",
                "verification_mode": "test_fixture",
                "evidence_targets": profile.evidence_targets,
                "verified_files": ["README.md"],
                "default_branch": "main",
                "head_commit": "0123456789abcdef",
                "checked_at": "2026-06-10T00:00:00+00:00",
            }

        report = build_open_source_lessons("科研 agent", verifier=verifier)

        self.assertTrue(all(item.status == "verified" for item in report.project_evidence))
        self.assertTrue(all(item.head_commit for item in report.project_evidence))
        self.assertIn("verified", render_open_source_lessons_markdown(report))

    def test_refresh_github_project_evidence_records_branch_commit_and_files(self) -> None:
        profile = build_open_source_lessons("科研 agent").profiles[0]

        def fetch(url, timeout, headers):
            if url.endswith("/repos/SakanaAI/AI-Scientist-v2"):
                return {"default_branch": "main"}
            if url.endswith("/branches/main"):
                return {"commit": {"sha": "abcdef1234567890"}}
            if "/contents/README.md" in url or "/contents/docs" in url or "/contents/ai_scientist" in url:
                return {"path": url.rsplit("/contents/", 1)[-1]}
            raise AssertionError(url)

        evidence = refresh_github_project_evidence(profile, fetch_json=fetch, token="token-value")

        self.assertEqual(evidence.status, "verified")
        self.assertEqual(evidence.default_branch, "main")
        self.assertEqual(evidence.head_commit, "abcdef1234567890")
        self.assertIn("README.md", evidence.verified_files)
        self.assertFalse(evidence.missing_files)

    def test_refresh_github_project_evidence_degrades_to_unverified_on_api_failure(self) -> None:
        profile = build_open_source_lessons("科研 agent").profiles[0]

        def fetch(url, timeout, headers):
            raise RuntimeError("HTTP 403 rate limited token-value")

        evidence = refresh_github_project_evidence(profile, fetch_json=fetch, token="token-value")

        self.assertEqual(evidence.status, "unverified")
        self.assertEqual(evidence.verification_mode, "github_api")
        self.assertTrue(any("HTTP 403" in item for item in evidence.notes))
        self.assertFalse(any("token-value" in item for item in evidence.notes))

    def test_write_open_source_lessons_artifacts(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            report = write_open_source_lessons_artifacts("科研 agent", run_dir)

            self.assertTrue((run_dir / "00-open-source-lessons.json").exists())
            self.assertTrue((run_dir / "00-open-source-lessons.md").exists())
            self.assertTrue(report.manual_checklist)


if __name__ == "__main__":
    unittest.main()
