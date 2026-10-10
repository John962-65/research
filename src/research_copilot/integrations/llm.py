"""LLM 集成：OpenAI 兼容协议，凭据只走环境变量，永不落盘。

环境变量：
    RESEARCH_COPILOT_LLM_BASE_URL  例 http://host:8080/v1
    RESEARCH_COPILOT_LLM_MODEL     模型名
    RESEARCH_COPILOT_LLM_API_KEY   API Key（仅进程环境；缺省时视为 LLM 不可用）
    RESEARCH_COPILOT_LLM_TIMEOUT   秒（默认 120）

安全说明：0600 权限的本地凭据文件仍属明文存储、不等于加密保护；本项目默认不提供
凭据文件，仅接受环境变量。调用台账只记录模型名/用量/耗时，不记录密钥。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class LLMUnavailable(RuntimeError):
    """未配置或无法访问 LLM。调用方必须退化为离线统计模式并明确标注。"""


@dataclass
class LLMCallRecord:
    """调用台账条目（用于成本核算；不含密钥）。"""

    ts: float
    model: str
    purpose: str
    prompt_chars: int
    completion_chars: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    duration_s: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "model": self.model,
            "purpose": self.purpose,
            "prompt_chars": self.prompt_chars,
            "completion_chars": self.completion_chars,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "duration_s": self.duration_s,
            "error": self.error,
        }


@dataclass
class LLMConfig:
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_s: float = 120.0
    temperature: float = 0.2
    max_tokens: int | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        return cls(
            base_url=os.environ.get("RESEARCH_COPILOT_LLM_BASE_URL", "").rstrip("/"),
            model=os.environ.get("RESEARCH_COPILOT_LLM_MODEL", ""),
            api_key=os.environ.get("RESEARCH_COPILOT_LLM_API_KEY", ""),
            timeout_s=float(os.environ.get("RESEARCH_COPILOT_LLM_TIMEOUT", "120") or 120),
        )

    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)


class OpenAICompatibleLLM:
    """最小 OpenAI /chat/completions 客户端（stdlib urllib，零依赖）。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self.calls: list[LLMCallRecord] = []
        if not self.config.is_configured():
            raise LLMUnavailable(
                "LLM 未配置：请设置 RESEARCH_COPILOT_LLM_BASE_URL / RESEARCH_COPILOT_LLM_MODEL"
                "（API Key 经 RESEARCH_COPILOT_LLM_API_KEY 传入，仅存进程环境）"
            )

    def complete(self, system: str, user: str, purpose: str = "complete", temperature: float | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
        }
        if self.config.max_tokens:
            payload["max_tokens"] = self.config.max_tokens
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.config.base_url}/chat/completions"
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}),
            },
            method="POST",
        )
        record = LLMCallRecord(
            ts=time.time(), model=self.config.model, purpose=purpose, prompt_chars=len(system) + len(user)
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            record.duration_s = time.time() - started
            record.error = str(exc)[:300]
            self.calls.append(record)
            raise LLMUnavailable(f"LLM 调用失败: {exc}") from exc
        record.duration_s = time.time() - started
        usage = data.get("usage") or {}
        record.prompt_tokens = usage.get("prompt_tokens")
        record.completion_tokens = usage.get("completion_tokens")
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            record.error = f"响应格式异常: {exc}"
            self.calls.append(record)
            raise LLMUnavailable(f"LLM 响应缺少 choices/message: {data}") from exc
        record.completion_chars = len(content)
        self.calls.append(record)
        return content

    def usage_summary(self) -> dict[str, Any]:
        ok_calls = [c for c in self.calls if not c.error]
        return {
            "model": self.config.model,
            "total_calls": len(self.calls),
            "failed_calls": len(self.calls) - len(ok_calls),
            "prompt_tokens": sum(c.prompt_tokens or 0 for c in ok_calls),
            "completion_tokens": sum(c.completion_tokens or 0 for c in ok_calls),
            "duration_s": round(sum(c.duration_s for c in self.calls), 3),
        }


class StubLLM:
    """测试用确定性 stub：按 purpose 返回脚本化响应。"""

    def __init__(self, responses: dict[str, str] | None = None, default: str = "{}") -> None:
        self.responses = responses or {}
        self.default = default
        self.calls: list[LLMCallRecord] = []
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, purpose: str = "complete", temperature: float | None = None) -> str:
        _ = temperature  # stub 不模拟温度；接受该参数以与真实客户端签名一致
        self.prompts.append((system, user))
        record = LLMCallRecord(
            ts=time.time(), model="stub", purpose=purpose, prompt_chars=len(system) + len(user), completion_chars=0
        )
        self.calls.append(record)
        return self.responses.get(purpose, self.default)

    def usage_summary(self) -> dict[str, Any]:
        return {"model": "stub", "total_calls": len(self.calls), "failed_calls": 0}
