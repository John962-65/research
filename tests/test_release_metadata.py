from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research_agent.config import ReleaseConfig
from research_agent.release_metadata import (
    build_release_metadata_report,
    render_release_metadata_markdown,
    write_release_metadata_artifacts,
)


class ReleaseMetadataTest(unittest.TestCase):
    def test_complete_metadata_is_ready_and_writes_statements(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = write_release_metadata_artifacts("发布元数据测试", run_dir, _complete_release_config())
            rendered = render_release_metadata_markdown(report)
            saved = json.loads((run_dir / "10-release-metadata.json").read_text(encoding="utf-8"))

            self.assertEqual(report.status, "ready_for_release")
            self.assertFalse(report.blocking_issues)
            self.assertFalse(report.manual_tasks)
            self.assertIn("https://github.com/example/research-agent", report.code_statement)
            self.assertIn("10.5281/zenodo.1234567", report.code_statement)
            self.assertIn("Apache-2.0", report.code_statement)
            self.assertIn("Release Metadata", rendered)
            self.assertEqual(report.recommended_config["status"], "complete")
            self.assertFalse(report.recommended_config["field_actions"])
            self.assertEqual(saved["status"], "ready_for_release")
            self.assertEqual(saved["recommended_config"]["status"], "complete")

    def test_malformed_url_and_doi_block_release(self) -> None:
        with TemporaryDirectory() as tmp:
            report = build_release_metadata_report(
                "发布元数据测试",
                Path(tmp),
                ReleaseConfig(
                    code_repository_url="github.com/example/repo",
                    code_archive_doi="zenodo pending",
                    code_license="MIT",
                    code_version="v0.1.0",
                    data_access_statement="本研究未使用受限外部数据。",
                    environment_url="docker-image",
                    release_notes="测试。",
                ),
            )

            self.assertEqual(report.status, "blocked")
            self.assertTrue(any("代码仓库 URL" in item for item in report.blocking_issues))
            self.assertTrue(any("代码归档 DOI" in item for item in report.blocking_issues))
            self.assertTrue(any("环境归档" in item for item in report.blocking_issues))
            field_actions = report.recommended_config["field_actions"]
            self.assertEqual(field_actions["release_code_repository_url"]["current_value"], "github.com/example/repo")
            self.assertEqual(field_actions["release_code_repository_url"]["recommended_value"], "")
            self.assertIn("release_code_archive_doi", report.recommended_config["required_fields"])
            self.assertIn("release_environment_url", report.recommended_config["required_fields"])

    def test_missing_metadata_recommends_cli_fields_without_fabricating_values(self) -> None:
        with TemporaryDirectory() as tmp:
            report = build_release_metadata_report("发布元数据测试", Path(tmp), ReleaseConfig())
            rendered = render_release_metadata_markdown(report)

            self.assertEqual(report.status, "needs_release_metadata")
            self.assertEqual(report.recommended_config["status"], "needs_input")
            self.assertIn("release_code_repository_url", report.recommended_config["required_fields"])
            self.assertIn("release_data_access_statement", report.recommended_config["required_fields"])
            self.assertIn("release_data_archive_doi", report.recommended_config["recommended_fields"])
            self.assertIn("--release-code-repository-url", report.recommended_config["cli_args"])
            self.assertIn("`--release-code-repository-url`", rendered)

            for action in report.recommended_config["field_actions"].values():
                self.assertEqual(action["recommended_value"], "")
                self.assertNotIn("https://", action["recommended_value"])
                self.assertFalse(action["recommended_value"].startswith("10."))


def _complete_release_config() -> ReleaseConfig:
    return ReleaseConfig(
        code_repository_url="https://github.com/example/research-agent",
        code_archive_doi="10.5281/zenodo.1234567",
        code_license="Apache-2.0",
        code_version="v0.1.0",
        data_repository_url="https://zenodo.org/records/7654321",
        data_archive_doi="10.5281/zenodo.7654321",
        data_access_statement="All benchmark data are available from the archived public record.",
        environment_url="https://github.com/example/research-agent/releases/tag/v0.1.0",
        release_notes="First reproducibility release for audit testing.",
    )


if __name__ == "__main__":
    unittest.main()
