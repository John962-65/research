from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import sys
from types import SimpleNamespace
import unittest

from research_agent.fulltext_corpus import build_fulltext_corpus, render_fulltext_corpus_markdown
from research_agent.literature_context import build_literature_context, retrieve_chunks
from research_agent.models import LiteratureReview, Paper


class FullTextCorpusTest(unittest.TestCase):
    def test_text_file_is_chunked_and_merged_into_context(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "fulltext" / "robot-planning-paper.txt"
            path.parent.mkdir()
            path.write_text(
                "Robot manipulator motion planning needs obstacle avoidance and repeatable benchmark scenes.\n\n"
                "The experiment compares RRT star, PRM, and trajectory optimization baselines with fixed random seeds.",
                encoding="utf-8",
            )
            corpus = build_fulltext_corpus("机械臂路径规划", [str(path)], base_dir=base)
            rendered = render_fulltext_corpus_markdown(corpus)
            review = LiteratureReview(
                topic="机械臂路径规划",
                papers=[
                    Paper(
                        title="Short metadata paper",
                        authors=["Ada Lovelace"],
                        year=2024,
                        venue="arXiv",
                        url="https://example.test",
                        abstract="Short abstract.",
                        relevance=0.5,
                    )
                ],
                themes=["机械臂路径规划需要避障。"],
                gaps=["需要可复现 benchmark。"],
                summary="测试综述",
            )

            context = build_literature_context(review, corpus)
            chunks = retrieve_chunks(context, "fixed random seeds trajectory optimization", top_k=2)

            self.assertEqual(corpus.total_chunks, 1)
            self.assertEqual(corpus.documents[0].status, "ok")
            self.assertIn("robot planning paper", rendered)
            self.assertTrue(any(citation.source == "local_fulltext" for citation in context.citations))
            self.assertTrue(any(chunk.source == "local_fulltext" for chunk in context.chunks))
            self.assertEqual(chunks[0].source, "local_fulltext")
            self.assertIn("sha256=", chunks[0].text)

    def test_path_outside_default_roots_requires_explicit_configuration(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "paper.txt"
            path.write_text("local text", encoding="utf-8")

            blocked = build_fulltext_corpus("topic", [str(path)], base_dir=base)
            with patch.dict(os.environ, {"RESEARCH_AGENT_FULLTEXT_ROOTS": str(base)}):
                allowed = build_fulltext_corpus("topic", [str(path)], base_dir=base)

            self.assertEqual(blocked.documents[0].status, "blocked")
            self.assertEqual(allowed.documents[0].status, "ok")

    def test_symlink_and_oversized_file_are_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            fulltext = base / "fulltext"
            fulltext.mkdir()
            outside = base / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            link = fulltext / "link.txt"
            link.symlink_to(outside)
            large = fulltext / "large.txt"
            large.write_text("x" * 20, encoding="utf-8")

            linked = build_fulltext_corpus("topic", [str(link)], base_dir=base)
            with patch.dict(os.environ, {"RESEARCH_AGENT_FULLTEXT_MAX_BYTES": "10"}):
                oversized = build_fulltext_corpus("topic", [str(large)], base_dir=base)

            self.assertEqual(linked.documents[0].status, "blocked")
            self.assertEqual(oversized.documents[0].status, "too_large")

    def test_pdf_page_and_extracted_character_limits_are_enforced(self) -> None:
        class FakePage:
            def extract_text(self):
                return "x" * 20

        class FakeReader:
            def __init__(self, stream):
                self.pages = [FakePage(), FakePage()]

        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "fulltext" / "paper.pdf"
            path.parent.mkdir()
            path.write_bytes(b"%PDF fake")
            fake_module = SimpleNamespace(PdfReader=FakeReader)
            with patch.dict(sys.modules, {"pypdf": fake_module}), patch.dict(
                os.environ,
                {"RESEARCH_AGENT_FULLTEXT_MAX_PDF_PAGES": "1"},
            ):
                pages = build_fulltext_corpus("topic", [str(path)], base_dir=base)
            with patch.dict(sys.modules, {"pypdf": fake_module}), patch.dict(
                os.environ,
                {"RESEARCH_AGENT_FULLTEXT_MAX_PDF_PAGES": "2", "RESEARCH_AGENT_FULLTEXT_MAX_PDF_CHARS": "30"},
            ):
                chars = build_fulltext_corpus("topic", [str(path)], base_dir=base)

            self.assertEqual(pages.documents[0].status, "too_large")
            self.assertEqual(chars.documents[0].status, "too_large")


if __name__ == "__main__":
    unittest.main()
