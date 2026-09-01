from __future__ import annotations

from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
import base64
import json
import os
import unittest
import urllib.error
import urllib.request

from research_agent.artifacts import write_json
import research_agent.web_server as web_server


@contextmanager
def _running_server(*, token: str = "", max_body_bytes: int = 1024):
    server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
    server.research_agent_bind_host = "127.0.0.1"
    server.research_agent_allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    server.research_agent_web_token = token
    server.research_agent_max_body_bytes = max_body_bytes
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _basic_header(token: str) -> str:
    credentials = f"{web_server.WEB_AUTH_USERNAME}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(credentials).decode("ascii")


class WebSecurityTests(unittest.TestCase):
    def test_loopback_without_token_and_security_headers(self) -> None:
        with _running_server() as server:
            url = f"http://127.0.0.1:{server.server_port}/api/benchmark-examples"
            with urllib.request.urlopen(url, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
                csp = response.headers["Content-Security-Policy"]
                self.assertIn("default-src 'self'", csp)
                self.assertIn("frame-ancestors 'none'", csp)

    def test_basic_auth_protects_static_and_api(self) -> None:
        token = "test-web-token-123456"
        with _running_server(token=token) as server:
            base = f"http://127.0.0.1:{server.server_port}"
            for path in ["/", "/api/benchmark-examples"]:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base + path, timeout=2)
                self.assertEqual(caught.exception.code, 401)
                self.assertIn("Basic", caught.exception.headers["WWW-Authenticate"])

            request = urllib.request.Request(
                base + "/api/benchmark-examples",
                headers={"Authorization": _basic_header(token)},
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)

    def test_host_origin_content_type_and_body_size_are_checked(self) -> None:
        with _running_server(max_body_bytes=4) as server:
            base = f"http://127.0.0.1:{server.server_port}"
            wrong_host = urllib.request.Request(
                base + "/api/benchmark-examples",
                headers={"Host": f"example.invalid:{server.server_port}"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(wrong_host, timeout=2)
            self.assertEqual(caught.exception.code, 400)

            cross_origin = urllib.request.Request(
                base + "/api/benchmark-examples",
                headers={"Origin": "http://example.invalid"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(cross_origin, timeout=2)
            self.assertEqual(caught.exception.code, 403)

            same_origin = urllib.request.Request(
                base + "/api/benchmark-examples",
                headers={"Origin": base},
            )
            with urllib.request.urlopen(same_origin, timeout=2) as response:
                self.assertEqual(response.status, 200)

            wrong_type = urllib.request.Request(base + "/api/not-found", data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(wrong_type, timeout=2)
            self.assertEqual(caught.exception.code, 415)

            oversized = urllib.request.Request(
                base + "/api/not-found",
                data=b'{"x":1}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(oversized, timeout=2)
            self.assertEqual(caught.exception.code, 413)

    def test_non_loopback_configuration_requires_strong_token(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.ResearchAgentHandler)
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(web_server.WEB_TOKEN_ENV, None)
                with self.assertRaisesRegex(ValueError, "required"):
                    web_server._configure_web_server(server, "0.0.0.0")
            with patch.dict(os.environ, {web_server.WEB_TOKEN_ENV: "too-short"}, clear=False):
                with self.assertRaisesRegex(ValueError, "at least 16"):
                    web_server._configure_web_server(server, "0.0.0.0")
            token = "sixteen-characters"
            with patch.dict(os.environ, {web_server.WEB_TOKEN_ENV: token}, clear=False):
                web_server._configure_web_server(server, "0.0.0.0")
            self.assertEqual(server.research_agent_web_token, token)
        finally:
            server.server_close()

    def test_artifacts_use_sandboxed_navigation_headers_and_safe_mime_types(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_store = web_server.STORE
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "malicious-artifact-run"
            run_dir.mkdir(parents=True)
            write_json(run_dir / "state.json", {"topic": "artifact boundary", "stage": "completed"})
            malicious_svg = (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<script>fetch("/api/runs/malicious-artifact-run/stop",{method:"POST"})</script>'
                '<text x="4" y="16">preview remains visible</text></svg>'
            )
            (run_dir / web_server.STATISTICS_FIGURE_SVG).write_text(malicious_svg, encoding="utf-8")
            (run_dir / "06-paper.md").write_text('<script>alert(document.domain)</script>', encoding="utf-8")
            try:
                web_server.ROOT = root
                web_server.RUNS_DIR = runs_dir
                web_server.STORE = web_server.RunStore()
                with _running_server() as server:
                    base = f"http://127.0.0.1:{server.server_port}/api/runs/malicious-artifact-run/artifact?file="
                    with urllib.request.urlopen(base + web_server.STATISTICS_FIGURE_SVG, timeout=2) as response:
                        svg_body = response.read().decode("utf-8")
                        svg_headers = response.headers
                    with urllib.request.urlopen(base + "06-paper.md", timeout=2) as response:
                        markdown_body = response.read().decode("utf-8")
                        markdown_headers = response.headers
            finally:
                web_server.STORE = original_store
                web_server.RUNS_DIR = original_runs
                web_server.ROOT = original_root

        for headers in [svg_headers, markdown_headers]:
            self.assertIn("sandbox", headers["Content-Security-Policy"])
            self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
            self.assertIn("form-action 'none'", headers["Content-Security-Policy"])
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(svg_headers.get_content_type(), "image/svg+xml")
        self.assertEqual(svg_headers["Content-Disposition"], f'inline; filename="{web_server.STATISTICS_FIGURE_SVG}"')
        self.assertEqual(svg_body, malicious_svg)
        self.assertEqual(markdown_headers.get_content_type(), "text/plain")
        self.assertEqual(markdown_headers["Content-Disposition"], 'attachment; filename="06-paper.md"')
        self.assertIn("<script>", markdown_body)


class RunSummaryTests(unittest.TestCase):
    def test_summary_view_reads_only_card_and_control_state(self) -> None:
        original_root = web_server.ROOT
        original_runs = web_server.RUNS_DIR
        original_reader = web_server._read_public_availability
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            run_dir = runs_dir / "summary-run-20260831-120000"
            run_dir.mkdir(parents=True)
            write_json(
                run_dir / "state.json",
                {"topic": "summary topic", "stage": "awaiting_review_approval", "updated_at": "2026-08-31T12:01:00+00:00"},
            )
            write_json(run_dir / web_server.APPROVAL_FILENAME, {"approved": False, "stage": "awaiting_review_approval"})
            write_json(run_dir / web_server.REPAIR_QUEUE_JSON, {"status": "needs_repair", "summary": {"total": 1}})
            write_json(run_dir / web_server.FINAL_HANDOFF_JSON, {"status": "blocked", "blocking_issues": ["test"]})
            try:
                web_server.ROOT = root
                web_server.RUNS_DIR = runs_dir
                web_server._read_public_availability = lambda _path: (_ for _ in ()).throw(AssertionError("full reader called"))
                summary = web_server.RunStore().list_summary()[0]
            finally:
                web_server._read_public_availability = original_reader
                web_server.ROOT = original_root
                web_server.RUNS_DIR = original_runs

        self.assertEqual(set(summary), set(web_server.RUN_SUMMARY_FIELDS))
        self.assertEqual(summary["topic"], "summary topic")
        self.assertEqual(summary["status"], "waiting")
        self.assertEqual(summary["created_at"], "2026-08-31T12:00:00+00:00")
        self.assertEqual(summary["repair_queue"]["status"], "needs_repair")
        self.assertEqual(summary["final_handoff"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
