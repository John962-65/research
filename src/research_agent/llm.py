from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from typing import Any, Protocol
import ipaddress
import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import LLMConfig


LLM_MAX_CONCURRENCY_ENV = "RESEARCH_AGENT_LLM_MAX_CONCURRENCY"
LLM_MAX_REQUEST_BYTES_ENV = "RESEARCH_AGENT_LLM_MAX_REQUEST_BYTES"
LLM_MAX_RESPONSE_BYTES_ENV = "RESEARCH_AGENT_LLM_MAX_RESPONSE_BYTES"
DEFAULT_LLM_MAX_CONCURRENCY = 1
DEFAULT_LLM_MAX_REQUEST_BYTES = 4 * 1024 * 1024
DEFAULT_LLM_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LLM_ATTEMPTS = 10
_LLM_SEMAPHORE_LOCK = Lock()
_LLM_SEMAPHORES: dict[int, BoundedSemaphore] = {}
_SECRET_QUERY_NAMES = {
    "api-key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
    "access-token",
    "access_token",
}


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str:
        ...


@dataclass
class OpenAICompatibleLLM:
    base_url: str
    api_key: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None

    def complete(self, system: str, user: str) -> str:
        base_url = validate_llm_base_url(self.base_url)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_limit = _llm_max_request_bytes()
        if len(body) > request_limit:
            raise ValueError(f"LLM completion request exceeds {request_limit} bytes")
        last_error: Exception | None = None
        attempts = _max_attempts()
        deadline = request_deadline(_request_timeout_seconds(), "LLM completion")
        try:
            with llm_request_slot(
                timeout_seconds=remaining_deadline_seconds(deadline, "LLM completion")
            ):
                for url in _candidate_chat_urls(base_url):
                    for attempt in range(attempts):
                        request = urllib.request.Request(
                            url,
                            data=body,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        add_bearer_auth(request, self.api_key)
                        try:
                            with _open_url(
                                request,
                                timeout=remaining_deadline_seconds(deadline, "LLM completion"),
                            ) as response:
                                response_body = read_limited_response(response, context="LLM completion")
                            data = json.loads(response_body.decode("utf-8"))
                            return data["choices"][0]["message"]["content"]
                        except urllib.error.HTTPError as exc:
                            detail = _http_error_detail(exc, secrets=[self.api_key])
                            safe_url = redact_url(url)
                            last_error = RuntimeError(f"{safe_url} returned HTTP {exc.code}: {detail}")
                            if exc.code in {404, 405}:
                                break
                            if exc.code in {429, 502, 503, 504} and attempt < attempts - 1:
                                delay = _retry_delay_seconds(exc, attempt)
                                if delay is not None:
                                    _sleep_within_deadline(delay, deadline, "LLM completion")
                                    continue
                            raise last_error
                        except (urllib.error.URLError, TimeoutError) as exc:
                            last_error = exc
                            if attempt < attempts - 1:
                                _sleep_within_deadline(1.5 * (attempt + 1), deadline, "LLM completion")
                                continue
                            safe_error = redact_sensitive_text(str(exc), secrets=[self.api_key])
                            raise RuntimeError(
                                f"{redact_url(url)} failed after {attempts} attempt(s): {safe_error}"
                            ) from exc
        except TimeoutError as exc:
            safe_error = redact_sensitive_text(str(exc), secrets=[self.api_key])
            raise RuntimeError(f"LLM completion failed: {safe_error}") from exc
        safe_last_error = redact_sensitive_text(str(last_error or "unknown error"), secrets=[self.api_key])
        raise RuntimeError(f"OpenAI-compatible endpoint failed: {safe_last_error}")

    def _candidate_chat_urls(self) -> list[str]:
        return _candidate_chat_urls(validate_llm_base_url(self.base_url))


def _positive_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _llm_max_concurrency() -> int:
    return _positive_env_int(LLM_MAX_CONCURRENCY_ENV, DEFAULT_LLM_MAX_CONCURRENCY)


def _llm_max_request_bytes() -> int:
    return _positive_env_int(LLM_MAX_REQUEST_BYTES_ENV, DEFAULT_LLM_MAX_REQUEST_BYTES)


def _llm_max_response_bytes() -> int:
    return _positive_env_int(LLM_MAX_RESPONSE_BYTES_ENV, DEFAULT_LLM_MAX_RESPONSE_BYTES)


@contextmanager
def llm_request_slot(timeout_seconds: float | None = None):
    limit = _llm_max_concurrency()
    with _LLM_SEMAPHORE_LOCK:
        semaphore = _LLM_SEMAPHORES.setdefault(limit, BoundedSemaphore(limit))
    if timeout_seconds is None:
        acquired = semaphore.acquire()
    else:
        timeout = _positive_timeout(timeout_seconds, "LLM concurrency wait timeout")
        acquired = semaphore.acquire(timeout=timeout)
    if not acquired:
        raise TimeoutError("timed out waiting for an LLM concurrency slot")
    try:
        yield
    finally:
        semaphore.release()


def request_deadline(timeout_seconds: float, context: str) -> float:
    return time.monotonic() + _positive_timeout(timeout_seconds, f"{context} timeout")


def remaining_deadline_seconds(deadline: float, context: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"{context} exceeded its total timeout budget")
    return remaining


def _sleep_within_deadline(delay_seconds: float, deadline: float, context: str) -> None:
    remaining = remaining_deadline_seconds(deadline, context)
    if delay_seconds >= remaining:
        raise TimeoutError(f"{context} retry delay exceeds the remaining timeout budget")
    time.sleep(delay_seconds)


def _positive_timeout(value: float, name: str) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return timeout


def add_bearer_auth(request: urllib.request.Request, api_key: str) -> None:
    if api_key:
        # urllib copies regular headers to redirected requests. Unredirected headers
        # authenticate the configured endpoint without leaking the key cross-origin.
        request.add_unredirected_header("Authorization", f"Bearer {api_key}")


def read_limited_response(response: Any, *, context: str, max_bytes: int | None = None) -> bytes:
    limit = max_bytes if max_bytes is not None else _llm_max_response_bytes()
    if limit <= 0:
        raise ValueError("response byte limit must be positive")
    headers = getattr(response, "headers", None) or {}
    content_length = str(headers.get("Content-Length") or "").strip()
    if content_length:
        try:
            if int(content_length) > limit:
                raise RuntimeError(f"{context} response exceeds {limit} bytes")
        except ValueError:
            pass
    body = response.read(limit + 1)
    if len(body) > limit:
        raise RuntimeError(f"{context} response exceeds {limit} bytes")
    return body


def validate_llm_base_url(base_url: str) -> str:
    value = str(base_url or "").strip()
    if not value:
        raise ValueError("LLM Base URL is required")
    if any(char.isspace() for char in value):
        raise ValueError("LLM Base URL contains invalid control characters")
    try:
        parsed = urllib.parse.urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise ValueError("LLM Base URL is invalid") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("LLM Base URL must use http or https")
    if not parsed.hostname:
        raise ValueError("LLM Base URL must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("LLM Base URL must not include user credentials")
    if parsed.fragment:
        raise ValueError("LLM Base URL must not include a fragment")
    for name, query_value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
        normalized_name = name.strip().lower()
        normalized_value = query_value.strip().lower()
        if normalized_name in _SECRET_QUERY_NAMES or normalized_value.startswith(("bearer ", "sk-")):
            raise ValueError("LLM Base URL must not contain credentials in its query string")
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None and not (
        (scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)
    ):
        host += f":{parsed.port}"
    normalized = urllib.parse.urlunsplit((scheme, host, parsed.path.rstrip("/"), parsed.query, ""))
    return normalized


def redact_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
        hostname = parsed.hostname or ""
        if not hostname:
            return "<invalid-url>"
        host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
        if parsed.port is not None:
            host += f":{parsed.port}"
        query = urllib.parse.urlencode([(name, "<redacted>") for name, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)])
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, query, ""))
    except (TypeError, ValueError):
        return "<invalid-url>"


def redact_sensitive_text(value: str, *, secrets: list[str] | tuple[str, ...] = ()) -> str:
    text = str(value or "")
    for secret in sorted({str(item) for item in secrets if len(str(item)) >= 4}, key=len, reverse=True):
        text = text.replace(secret, "***")
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", text)
    text = re.sub(
        r'(?i)(["\']?(?:api[_-]?key|token|authorization|password|secret)["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+',
        r"\1***",
        text,
    )
    return text


def _candidate_chat_urls(base_url: str) -> list[str]:
    parsed = urllib.parse.urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        paths = [path]
    elif path.endswith("/v1"):
        paths = [path + "/chat/completions"]
    else:
        paths = [path + "/v1/chat/completions", path + "/chat/completions"]
    return [urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, item, parsed.query, "")) for item in paths]


def _candidate_model_urls(base_url: str, provider: str) -> list[str]:
    parsed = urllib.parse.urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if provider == "ollama" or parsed.port == 11434:
        root_path = path[:-3] if path.endswith("/v1") else path
        paths = [root_path + "/api/tags", path + "/models"]
    elif path.endswith("/v1"):
        paths = [path + "/models"]
    else:
        paths = [path + "/models", path + "/v1/models"]
    return [urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, item, parsed.query, "")) for item in paths]


def _request_timeout_seconds() -> float:
    return _positive_timeout(os.environ.get("OPENAI_TIMEOUT_SECONDS", "90"), "OPENAI_TIMEOUT_SECONDS")


def _max_attempts() -> int:
    return min(MAX_LLM_ATTEMPTS, _positive_env_int("OPENAI_MAX_ATTEMPTS", 3))


def _ping_max_attempts() -> int:
    return min(MAX_LLM_ATTEMPTS, _positive_env_int("OPENAI_PING_MAX_ATTEMPTS", 2))


def _retry_delay_seconds(exc: urllib.error.HTTPError, attempt: int) -> float | None:
    raw_max_delay = os.environ.get("OPENAI_MAX_RETRY_DELAY_SECONDS", "60")
    try:
        max_delay = float(raw_max_delay)
    except ValueError as exc_value:
        raise ValueError("OPENAI_MAX_RETRY_DELAY_SECONDS must be a non-negative finite number") from exc_value
    if not math.isfinite(max_delay) or max_delay < 0:
        raise ValueError("OPENAI_MAX_RETRY_DELAY_SECONDS must be a non-negative finite number")
    if max_delay == 0:
        return None
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        if retry_after > max_delay:
            return None
        delay = retry_after
    else:
        delay = min(1.5 * (2**attempt), max_delay)
    jitter_limit = min(0.5, max(0.0, max_delay - delay))
    return delay + (random.uniform(0.0, jitter_limit) if jitter_limit else 0.0)


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    raw = str((exc.headers or {}).get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _http_error_detail(exc: urllib.error.HTTPError, *, secrets: list[str] | tuple[str, ...] = ()) -> str:
    try:
        body = read_limited_response(
            exc,
            context="LLM error",
            max_bytes=min(_llm_max_response_bytes(), 64 * 1024),
        ).decode("utf-8", errors="replace")
    except Exception:
        body = ""
    body = redact_sensitive_text(body.strip(), secrets=secrets)
    if len(body) > 1200:
        body = body[:1200] + "..."
    return body or redact_sensitive_text(str(exc.reason), secrets=secrets)


def _open_url(request: urllib.request.Request, timeout: float) -> Any:
    if _should_bypass_proxy(request.full_url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(request, timeout=timeout)
    return urllib.request.urlopen(request, timeout=timeout)


def _should_bypass_proxy(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        return False
    if urllib.request.proxy_bypass(host):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    no_proxy = os.environ.get("no_proxy") if "no_proxy" in os.environ else os.environ.get("NO_PROXY", "")
    for item in str(no_proxy or "").split(","):
        candidate = item.strip()
        if "/" not in candidate:
            continue
        try:
            network = ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            continue
        if address in network:
            return True
    return False



KNOWN_LLM_PROVIDERS = {
    "openai-compatible",
    "openai",
    "deepseek",
    "dashscope",
    "qwen",
    "zhipu",
    "bigmodel",
    "moonshot",
    "kimi",
    "siliconflow",
    "openrouter",
    "google-gemini",
    "gemini",
    "anthropic-compatible",
    "anthropic",
    "ollama",
    "vllm",
    "azure-openai",
    "custom-http",
}

UNSUPPORTED_NATIVE_LLM_PROVIDERS = {
    "anthropic-compatible": "Anthropic Messages API is not OpenAI Chat Completions compatible; use an OpenAI-compatible gateway and provider=openai-compatible",
    "anthropic": "Anthropic Messages API is not supported by this client; use an OpenAI-compatible gateway and provider=openai-compatible",
    "azure-openai": "native Azure OpenAI authentication and deployment URLs are not supported; use an OpenAI-compatible gateway and provider=openai-compatible",
}

PROVIDER_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openai-compatible": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "bigmodel": "https://open.bigmodel.cn/api/paas/v4",
    "moonshot": "https://api.moonshot.cn/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "google-gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic-compatible": "https://api.anthropic.com/v1",
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
    "azure-openai": "",
    "custom-http": "",
}

PROVIDER_PRESET_MODELS = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "openai": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "openai-compatible": ["gpt-4o", "gpt-4o-mini", "deepseek-chat", "deepseek-reasoner", "qwen-plus"],
    "dashscope": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen2.5-72b-instruct", "qwen-long"],
    "qwen": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen2.5-72b-instruct", "qwen-long"],
    "zhipu": ["glm-4-plus", "glm-4-air", "glm-4-flash", "glm-4-long"],
    "bigmodel": ["glm-4-plus", "glm-4-air", "glm-4-flash", "glm-4-long"],
    "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "kimi": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    "siliconflow": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct", "Pro/deepseek-ai/DeepSeek-V3"],
    "openrouter": ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "deepseek/deepseek-r1", "google/gemini-2.0-flash-exp:free"],
    "google-gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "anthropic-compatible": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
    "ollama": ["llama3.2", "qwen2.5:7b", "deepseek-r1:8b", "mistral", "gemma2"],
    "vllm": ["default-model"],
}


def validate_llm_provider(provider: str) -> str:
    normalized = str(provider or "openai-compatible").strip().lower()
    if normalized in UNSUPPORTED_NATIVE_LLM_PROVIDERS:
        raise ValueError(UNSUPPORTED_NATIVE_LLM_PROVIDERS[normalized])
    if normalized not in KNOWN_LLM_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return normalized


def resolve_llm_base_url(provider: str, configured: str = "", env_name: str = "") -> str:
    provider_norm = validate_llm_provider(provider)
    env_value = os.environ.get(env_name, "").strip() if env_name else ""
    base_url = str(configured or "").strip() or env_value or PROVIDER_DEFAULT_BASE_URLS.get(provider_norm, "")
    if not base_url:
        raise ValueError(f"LLM provider {provider_norm} requires an explicit Base URL")
    return validate_llm_base_url(base_url)


def resolve_llm_api_key(config: LLMConfig, resolved_base_url: str | None = None) -> str:
    if config.api_key:
        return config.api_key
    if not config.api_key_env:
        return ""
    env_key = os.environ.get(config.api_key_env, "")
    if not env_key:
        return ""
    provider = validate_llm_provider(config.provider)
    configured_base = str(config.base_url or "").strip()
    try:
        actual_url = resolved_base_url or resolve_llm_base_url(
            provider,
            configured_base,
            config.base_url_env,
        )
    except ValueError:
        return ""
    env_base = os.environ.get(config.base_url_env, "").strip() if config.base_url_env else ""
    trusted_base = env_base
    if not trusted_base and provider in {"openai", "openai-compatible"}:
        trusted_base = PROVIDER_DEFAULT_BASE_URLS[provider]
    if not trusted_base:
        return ""
    try:
        trusted_url = validate_llm_base_url(trusted_base)
    except ValueError:
        return ""
    return env_key if actual_url == trusted_url else ""


@dataclass(frozen=True)
class CredentialBinding:
    """Provenance of the credential for one route: which env it comes from and where it goes."""

    origin_base_url: str
    source: str  # "literal" | "env" | "none"
    env_name: str
    same_origin_as_global: bool


def _url_origin(url: str) -> tuple[str, str, int | None]:
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme.lower(), (parts.hostname or "").lower().rstrip("."), parts.port)


def resolve_role_llm_config(
    global_config: LLMConfig,
    *,
    model: str = "",
    base_url: str = "",
    base_url_env: str = "",
    api_key_env: str = "",
) -> LLMConfig:
    """Bind one role/task route to an endpoint and a provably matching credential.

    This is the single credential-origin enforcement point shared by runtime,
    preflight, Web, and CLI. A global literal API key must never be sent to an
    endpoint whose origin differs from the global one: a cross-origin route
    must declare a paired ``base_url_env``/``api_key_env``, and the endpoint
    named by ``base_url_env`` must match the effective origin.
    """
    overrides: dict[str, Any] = {}
    model_value = str(model or "").strip()
    if model_value:
        overrides["model"] = model_value
    base_url_value = str(base_url or "").strip()
    base_url_env_value = str(base_url_env or "").strip()
    api_key_env_value = str(api_key_env or "").strip()
    if base_url_value:
        overrides["base_url"] = base_url_value
    if base_url_env_value:
        overrides["base_url_env"] = base_url_env_value
    if api_key_env_value:
        overrides["api_key_env"] = api_key_env_value
    if not overrides:
        return global_config
    if not base_url_value and not base_url_env_value and not api_key_env_value:
        # Model-only override keeps the global endpoint and its credential.
        return replace(global_config, **overrides)

    try:
        global_base_url = resolve_llm_base_url(
            global_config.provider, global_config.base_url, global_config.base_url_env
        )
    except ValueError:
        global_base_url = ""
    effective_base_url = resolve_llm_base_url(
        global_config.provider,
        base_url_value,
        base_url_env_value,
    )
    same_origin = bool(global_base_url) and _url_origin(global_base_url) == _url_origin(effective_base_url)
    if same_origin:
        return replace(global_config, **overrides)

    if not api_key_env_value:
        raise ValueError(
            "LLM credential binding rejected: role endpoint "
            f"{redact_url(effective_base_url)} does not share the global endpoint origin; "
            "declare api_key_env for this role instead of reusing the global literal key"
        )
    if not base_url_env_value:
        raise ValueError(
            "LLM credential binding rejected: role endpoint "
            f"{redact_url(effective_base_url)} does not share the global endpoint origin; "
            "declare the matching base_url_env so the credential origin can be proven"
        )
    env_base = os.environ.get(base_url_env_value, "").strip()
    if not env_base:
        raise ValueError(
            "LLM credential binding rejected: environment variable "
            f"{base_url_env_value} is not set, so the credential origin for "
            f"{redact_url(effective_base_url)} cannot be proven"
        )
    try:
        env_base_url = validate_llm_base_url(env_base)
    except ValueError as exc:
        raise ValueError(
            f"LLM credential binding rejected: {base_url_env_value} is not a valid base URL"
        ) from exc
    if _url_origin(env_base_url) != _url_origin(effective_base_url):
        raise ValueError(
            "LLM credential binding rejected: "
            f"{base_url_env_value} resolves to {redact_url(env_base_url)} which does not match "
            f"the role endpoint {redact_url(effective_base_url)}"
        )
    # Cross-origin route: drop the global literal key entirely and pin the
    # role's endpoint fields (base_url="" clears a global literal so the env
    # var stays authoritative).
    return replace(
        global_config,
        model=overrides.get("model", global_config.model),
        base_url=base_url_value,
        base_url_env=base_url_env_value,
        api_key="",
        api_key_env=api_key_env_value,
    )


def describe_credential_binding(config: LLMConfig, resolved_base_url: str | None = None) -> CredentialBinding:
    """Describe where the credential for ``config`` comes from (no secret values)."""
    try:
        origin = resolved_base_url or resolve_llm_base_url(
            config.provider, config.base_url, config.base_url_env
        )
    except ValueError:
        origin = ""
    if config.api_key:
        return CredentialBinding(origin_base_url=origin, source="literal", env_name="", same_origin_as_global=True)
    if config.api_key_env:
        return CredentialBinding(
            origin_base_url=origin,
            source="env",
            env_name=config.api_key_env,
            same_origin_as_global=True,
        )
    return CredentialBinding(origin_base_url=origin, source="none", env_name="", same_origin_as_global=True)

def fetch_provider_models(provider: str, base_url: str, api_key: str, timeout_seconds: float = 8.0) -> dict[str, Any]:
    provider_norm = validate_llm_provider(provider)
    resolved_base_url = resolve_llm_base_url(provider_norm, base_url)
    candidate_urls = _candidate_model_urls(resolved_base_url, provider_norm)
    deadline = request_deadline(timeout_seconds, "LLM model discovery")
    
    headers = {"Content-Type": "application/json"}
    
    models = []
    error_msg = ""
    try:
        with llm_request_slot(
            timeout_seconds=remaining_deadline_seconds(deadline, "LLM model discovery")
        ):
            for url in candidate_urls:
                try:
                    req = urllib.request.Request(url, headers=headers, method="GET")
                    add_bearer_auth(req, api_key)
                    with _open_url(
                        req,
                        timeout=remaining_deadline_seconds(deadline, "LLM model discovery"),
                    ) as resp:
                        response_body = read_limited_response(resp, context="LLM model discovery")
                    data = json.loads(response_body.decode("utf-8"))
                    if isinstance(data, dict):
                        if "data" in data and isinstance(data["data"], list):
                            for item in data["data"]:
                                if isinstance(item, dict) and "id" in item:
                                    models.append(str(item["id"]))
                        elif "models" in data and isinstance(data["models"], list):
                            for item in data["models"]:
                                if isinstance(item, dict) and "name" in item:
                                    models.append(str(item["name"]))
                    if models:
                        break
                except urllib.error.HTTPError as exc:
                    error_msg = f"{redact_url(url)} HTTP {exc.code}: {_http_error_detail(exc, secrets=[api_key])}"
                except Exception as exc:
                    error_msg = redact_sensitive_text(str(exc), secrets=[api_key])
    except (TimeoutError, ValueError) as exc:
        error_msg = redact_sensitive_text(str(exc), secrets=[api_key])
            
    if models:
        seen = set()
        unique_models = []
        for m in models:
            if m not in seen:
                seen.add(m)
                unique_models.append(m)
        return {
            "success": True,
            "models": unique_models,
            "source": "live_api",
            "live_api_status": "pass",
            "provider": provider_norm,
            "base_url": redact_url(resolved_base_url),
            "count": len(unique_models)
        }
    
    fallback = PROVIDER_PRESET_MODELS.get(provider_norm, PROVIDER_PRESET_MODELS["openai-compatible"])
    return {
        "success": False,
        "models": fallback,
        "source": "preset_fallback",
        "live_api_status": "fail",
        "error": error_msg or "无法直接从接口获取模型列表，已回退至推荐预设列表",
        "provider": provider_norm,
        "base_url": redact_url(resolved_base_url),
        "count": len(fallback)
    }


def build_llm(config: LLMConfig) -> LLM:
    provider = validate_llm_provider(config.provider)
    base_url = resolve_llm_base_url(provider, config.base_url, config.base_url_env)
    api_key = resolve_llm_api_key(config, base_url)
    model = config.model or (os.environ.get(config.model_env, "") if config.model_env else "")
    if not model:
        raise RuntimeError(f"Missing model. Set llm.model or env var: {config.model_env}")
    if urllib.parse.urlsplit(base_url).hostname == "api.openai.com" and not api_key:
        raise RuntimeError(f"Missing API key. Set llm.api_key or env var: {config.api_key_env}")
    return OpenAICompatibleLLM(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
