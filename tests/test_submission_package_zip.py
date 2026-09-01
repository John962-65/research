from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import zipfile

from research_agent.submission_package_zip import (
    safe_submission_package_zip_filename,
    submission_package_zip_blocking_issue,
    submission_package_zip_ready,
)


class SubmissionPackageZipTest(unittest.TestCase):
    def test_valid_submission_package_zip_is_ready(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "11-submission-package.zip"
            _write_zip(path, files=[{"package_path": "submission-package/CHECKLIST.md"}])

            self.assertTrue(submission_package_zip_ready(path))
            self.assertEqual(submission_package_zip_blocking_issue(path), "")

    def test_blocks_manifest_listed_file_missing_from_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "11-submission-package.zip"
            _write_zip(path, files=[{"package_path": "submission-package/paper/revised-paper.md", "status": "pass"}])

            issue = submission_package_zip_blocking_issue(path)

        self.assertIn("package-manifest.json", issue)
        self.assertIn("submission-package/paper/revised-paper.md", issue)

    def test_allows_manifest_record_for_missing_optional_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "11-submission-package.zip"
            _write_zip(path, files=[{"package_path": "submission-package/optional/missing.txt", "status": "optional_missing"}])

            self.assertTrue(submission_package_zip_ready(path))

    def test_blocks_unsafe_manifest_package_path(self) -> None:
        unsafe_paths = ["", "../outside.txt", "/submission-package/private.txt", "C:/submission-package/private.txt", "submission-package\\private.txt"]
        for package_path in unsafe_paths:
            with self.subTest(package_path=package_path), TemporaryDirectory() as tmp:
                path = Path(tmp) / "11-submission-package.zip"
                _write_zip(path, files=[{"package_path": package_path, "status": "pass"}])

                issue = submission_package_zip_blocking_issue(path)

            self.assertIn("package-manifest.json", issue)
            self.assertFalse(submission_package_zip_ready(path))

    def test_blocks_duplicate_zip_entries(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "11-submission-package.zip"
            _write_zip(path, files=[{"package_path": "submission-package/CHECKLIST.md"}])
            with zipfile.ZipFile(path, "a") as archive:
                with self.assertWarns(UserWarning):
                    archive.writestr("submission-package/CHECKLIST.md", "# Duplicate")

            issue = submission_package_zip_blocking_issue(path)

        self.assertIn("重复", issue)
        self.assertFalse(submission_package_zip_ready(path))

    def test_blocks_duplicate_manifest_package_paths(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "11-submission-package.zip"
            _write_zip(
                path,
                files=[
                    {"package_path": "submission-package/CHECKLIST.md", "status": "pass"},
                    {"package_path": "submission-package/CHECKLIST.md", "status": "optional_missing"},
                ],
            )

            issue = submission_package_zip_blocking_issue(path)

        self.assertIn("package-manifest.json", issue)
        self.assertIn("重复", issue)
        self.assertFalse(submission_package_zip_ready(path))

    def test_blocks_malformed_manifest_file_metadata(self) -> None:
        cases = [
            {"package_path": "submission-package/CHECKLIST.md", "status": "ready"},
            {"package_path": "submission-package/CHECKLIST.md", "required": "true"},
            {"package_path": "submission-package/CHECKLIST.md", "bytes": True},
            {"package_path": "submission-package/CHECKLIST.md", "bytes": -1},
            {"package_path": "submission-package/CHECKLIST.md", "sha256": "ABC"},
        ]
        for file_record in cases:
            with self.subTest(file_record=file_record), TemporaryDirectory() as tmp:
                path = Path(tmp) / "11-submission-package.zip"
                _write_zip(path, files=[file_record])

                issue = submission_package_zip_blocking_issue(path)

            self.assertIn("package-manifest.json", issue)
            self.assertFalse(submission_package_zip_ready(path))

    def test_safe_submission_package_zip_filename_rejects_paths(self) -> None:
        self.assertTrue(safe_submission_package_zip_filename("11-submission-package.zip"))
        for name in ["", "../11-submission-package.zip", "/tmp/11-submission-package.zip", "C:/11-submission-package.zip", "package.txt"]:
            with self.subTest(name=name):
                self.assertFalse(safe_submission_package_zip_filename(name))


def _write_zip(path: Path, *, files: list[dict[str, object]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("submission-package/CHECKLIST.md", "# Checklist")
        archive.writestr(
            "submission-package/package-manifest.json",
            json.dumps({"status": "ready_for_human_submission_upload", "files": files}),
        )


if __name__ == "__main__":
    unittest.main()
