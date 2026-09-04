from __future__ import annotations

from io import BytesIO
from unittest.mock import Mock, patch
import json
import os
import unittest
import urllib.error
import urllib.request

from research_agent.config import LLMConfig
from research_agent.llm import (
    USER_AGENT,
    OpenAICompatibleLLM,
    _open_url,
    fetch_provider_models,
    resolve_llm_api_key,
    validate_llm_base_url,
    validate_llm_provider,
)


class OpenAICompatibleLLMTest(unittest.TestCase):
    def test_retries_socket_timeout(self) -> None:
        calls = {"count": 0}

        def fake_urlopen(request, timeout):
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimeoutError("timed out")
            return _Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        old_attempts = os.environ.get("OPENAI_MAX_ATTEMPTS")
        old_timeout = os.environ.get("OPENAI_TIMEOUT_SECONDS")
        os.environ["OPENAI_MAX_ATTEMPTS"] = "2"
        os.environ["OPENAI_TIMEOUT_SECONDS"] = "5"
        try:
            with patch("research_agent.llm._open_url", side_effect=fake_urlopen), patch("research_agent.llm.time.sleep"):
                result = OpenAICompatibleLLM(base_url="http://local.test/v1", api_key="secret", model="model").complete("s", "u")
        finally:
            if old_attempts is None:
                os.environ.pop("OPENAI_MAX_ATTEMPTS", None)
            else:
                os.environ["OPENAI_MAX_ATTEMPTS"] = old_attempts
            if old_timeout is None:
                os.environ.pop("OPENAI_TIMEOUT_SECONDS", None)
            else:
                os.environ["OPENAI_TIMEOUT_SECONDS"] = old_timeout

        self.assertEqual(result, "OK")
        self.assertEqual(calls["count"], 2)

    def test_timeout_does_not_try_fallback_chat_url(self) -> None:
        urls: list[str] = []

        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            raise TimeoutError("timed out")

        old_attempts = os.environ.get("OPENAI_MAX_ATTEMPTS")
        os.environ["OPENAI_MAX_ATTEMPTS"] = "1"
        try:
            with patch("research_agent.llm._open_url", side_effect=fake_urlopen):
                with self.assertRaises(RuntimeError):
                    OpenAICompatibleLLM(base_url="http://local.test", api_key="secret", model="model").complete("s", "u")
        finally:
            if old_attempts is None:
                os.environ.pop("OPENAI_MAX_ATTEMPTS", None)
            else:
                os.environ["OPENAI_MAX_ATTEMPTS"] = old_attempts

        self.assertEqual(urls, ["http://local.test/v1/chat/completions"])

    def test_tries_fallback_chat_url_after_404(self) -> None:
        urls: list[str] = []

        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            if len(urls) == 1:
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)
            return _Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        with patch("research_agent.llm._open_url", side_effect=fake_urlopen):
            result = OpenAICompatibleLLM(base_url="http://local.test", api_key="secret", model="model").complete("s", "u")

        self.assertEqual(result, "OK")
        self.assertEqual(urls, ["http://local.test/v1/chat/completions", "http://local.test/chat/completions"])

    def test_completion_uses_only_required_request_fields(self) -> None:
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return _Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        with patch("research_agent.llm._open_url", side_effect=fake_urlopen):
            result = OpenAICompatibleLLM(
                base_url="http://local.test/v1", api_key="secret", model="model"
            ).complete("system instruction", "user request")

        self.assertEqual(result, "OK")
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(set(payload), {"model", "messages"})
        self.assertEqual(payload["messages"][0]["role"], "system")

    def test_completion_sends_project_user_agent_not_urllib_default(self) -> None:
        """Cloudflare-fronted gateways answer urllib's default signature with
        HTTP 403 error code 1010 before the origin sees the request."""
        captured: list[str] = []

        def fake_urlopen(request, timeout):
            captured.append(request.get_header("User-agent") or "")
            return _Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        with patch("research_agent.llm._open_url", side_effect=fake_urlopen):
            OpenAICompatibleLLM(
                base_url="http://local.test/v1", api_key="secret", model="model"
            ).complete("system instruction", "user request")

        self.assertEqual(captured, [USER_AGENT])
        self.assertNotIn("Python-urllib", captured[0])

    def test_model_discovery_sends_project_user_agent(self) -> None:
        captured: list[str] = []

        def fake_urlopen(request, timeout):
            captured.append(request.get_header("User-agent") or "")
            return _Response(b'{"data":[{"id":"model-a"}]}')

        with patch("research_agent.llm._open_url", side_effect=fake_urlopen):
            result = fetch_provider_models("openai-compatible", "http://local.test/v1", "secret")

        self.assertTrue(result["success"])
        self.assertEqual(captured, [USER_AGENT])
        self.assertNotIn("Python-urllib", captured[0])

    def test_retries_429_after_retry_after_delay(self) -> None:
        rate_limit_error = urllib.error.HTTPError(
            "http://local.test/v1/chat/completions",
            429,
            "Too Many Requests",
            hdrs={"Retry-After": "2"},
            fp=BytesIO(b'{"error":{"message":"busy"}}'),
        )
        response = _Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        with patch.dict(
            os.environ,
            {"OPENAI_MAX_ATTEMPTS": "2", "OPENAI_MAX_RETRY_DELAY_SECONDS": "60"},
        ), patch("research_agent.llm._open_url", side_effect=[rate_limit_error, response]), patch(
            "research_agent.llm.random.uniform", return_value=0.25
        ), patch("research_agent.llm.time.sleep") as sleep:
            result = OpenAICompatibleLLM(
                base_url="http://local.test/v1", api_key="secret", model="model"
            ).complete("system instruction", "user request")

        self.assertEqual(result, "OK")
        sleep.assert_called_once_with(2.25)

    def test_fetch_provider_models_marks_live_results_as_success(self) -> None:
        response = _Response(b'{"data":[{"id":"model-a"},{"id":"model-a"},{"id":"model-b"}]}')

        with patch("research_agent.llm._open_url", return_value=response):
            result = fetch_provider_models("openai-compatible", "http://local.test/v1", "secret")

        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "live_api")
        self.assertEqual(result["live_api_status"], "pass")
        self.assertEqual(result["models"], ["model-a", "model-b"])

    def test_fetch_provider_models_reports_preset_fallback_as_failure(self) -> None:
        error = urllib.error.HTTPError("http://local.test/v1/models", 401, "Unauthorized", hdrs=None, fp=None)

        with patch("research_agent.llm._open_url", side_effect=error):
            result = fetch_provider_models("openai-compatible", "http://local.test/v1", "secret")

        self.assertFalse(result["success"])
        self.assertEqual(result["source"], "preset_fallback")
        self.assertEqual(result["live_api_status"], "fail")
        self.assertIn("HTTP 401", result["error"])
        self.assertTrue(result["models"])
        self.assertNotIn("secret", str(result))

    def test_explicit_untrusted_url_does_not_receive_environment_key(self) -> None:
        config = LLMConfig(
            base_url="http://untrusted.test/v1",
            base_url_env="OPENAI_BASE_URL",
            api_key_env="OPENAI_API_KEY",
        )
        with patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "http://trusted.test/v1", "OPENAI_API_KEY": "environment-secret"},
        ):
            self.assertEqual(resolve_llm_api_key(config), "")

    def test_canonically_matching_url_can_receive_environment_key(self) -> None:
        config = LLMConfig(
            base_url="HTTP://TRUSTED.TEST:80/v1/",
            base_url_env="OPENAI_BASE_URL",
            api_key_env="OPENAI_API_KEY",
        )
        with patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "http://trusted.test/v1", "OPENAI_API_KEY": "environment-secret"},
        ):
            self.assertEqual(resolve_llm_api_key(config), "environment-secret")

    def test_non_openai_provider_default_does_not_receive_openai_environment_key(self) -> None:
        config = LLMConfig(
            provider="deepseek",
            api_key_env="OPENAI_API_KEY",
            base_url_env="OPENAI_BASE_URL",
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}, clear=True):
            self.assertEqual(resolve_llm_api_key(config), "")

    def test_explicit_matching_custom_http_environment_url_can_receive_environment_key(self) -> None:
        config = LLMConfig(
            provider="custom-http",
            base_url="http://192.0.2.1:8080/v1",
            api_key_env="OPENAI_API_KEY",
            base_url_env="OPENAI_BASE_URL",
        )
        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "http://192.0.2.1:8080/v1/",
                "OPENAI_API_KEY": "environment-secret",
            },
            clear=True,
        ):
            self.assertEqual(resolve_llm_api_key(config), "environment-secret")

    def test_rejects_invalid_base_urls_and_native_providers(self) -> None:
        for value in ["file:///tmp/socket", "http:///v1", "http://user:pass@host/v1", "http://host/v1?api_key=secret"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_llm_base_url(value)
        for provider in ["anthropic", "anthropic-compatible", "azure-openai"]:
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                validate_llm_provider(provider)

    def test_completion_rejects_oversized_request_before_network(self) -> None:
        with patch.dict(os.environ, {"RESEARCH_AGENT_LLM_MAX_REQUEST_BYTES": "64"}), patch(
            "research_agent.llm._open_url"
        ) as open_url:
            with self.assertRaisesRegex(ValueError, "request exceeds"):
                OpenAICompatibleLLM(
                    base_url="http://local.test/v1", api_key="secret", model="model"
                ).complete("system", "x" * 1000)
        open_url.assert_not_called()

    def test_bearer_header_is_not_forwarded_by_redirects(self) -> None:
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return _Response(b'{"choices":[{"message":{"content":"OK"}}]}')

        with patch("research_agent.llm._open_url", side_effect=fake_urlopen):
            OpenAICompatibleLLM(
                base_url="http://local.test/v1", api_key="secret", model="model"
            ).complete("s", "u")

        self.assertNotIn("Authorization", requests[0].headers)
        self.assertEqual(requests[0].unredirected_hdrs["Authorization"], "Bearer secret")

    def test_no_proxy_cidr_uses_direct_connection(self) -> None:
        request = urllib.request.Request("http://192.0.2.1:8080/v1/models")
        opener = Mock()
        response = _Response(b"{}")
        opener.open.return_value = response

        with patch.dict(os.environ, {"no_proxy": "localhost,192.0.2.0/24"}), patch(
            "research_agent.llm.urllib.request.proxy_bypass", return_value=False
        ), patch("research_agent.llm.urllib.request.build_opener", return_value=opener) as build_opener, patch(
            "research_agent.llm.urllib.request.urlopen"
        ) as urlopen:
            actual = _open_url(request, timeout=3.0)

        self.assertIs(actual, response)
        build_opener.assert_called_once()
        opener.open.assert_called_once_with(request, timeout=3.0)
        urlopen.assert_not_called()

    def test_non_matching_no_proxy_cidr_keeps_configured_proxy_handling(self) -> None:
        request = urllib.request.Request("http://203.0.113.10/v1/models")
        response = _Response(b"{}")

        with patch.dict(os.environ, {"no_proxy": "192.0.2.0/24"}), patch(
            "research_agent.llm.urllib.request.proxy_bypass", return_value=False
        ), patch("research_agent.llm.urllib.request.build_opener") as build_opener, patch(
            "research_agent.llm.urllib.request.urlopen", return_value=response
        ) as urlopen:
            actual = _open_url(request, timeout=3.0)

        self.assertIs(actual, response)
        build_opener.assert_not_called()
        urlopen.assert_called_once_with(request, timeout=3.0)


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


if __name__ == "__main__":
    unittest.main()
