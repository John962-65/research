from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re


@dataclass(frozen=True)
class RunDiagnostic:
    category: str
    severity: str
    summary: str
    likely_cause: str
    recommended_actions: list[str]
    topic: str = ""
    stage: str = ""
    details: str = ""
    traceback: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def diagnose_exception(exc: BaseException, topic: str = "", stage: str = "", traceback_text: str = "") -> RunDiagnostic:
    text = f"{exc}\n{traceback_text}".strip()
    lowered = text.lower()
    if "missing model" in lowered or "openai_model" in text:
        return RunDiagnostic(
            category="llm_configuration",
            severity="blocking",
            summary="模型名未配置，流水线无法启动 LLM。",
            likely_cause="未填写 Web 表单里的模型名，也没有设置 OPENAI_MODEL 环境变量。",
            recommended_actions=[
                "在 Web 表单“模型名”填写可用模型，例如 gpt-4o-mini、qwen-plus 或本地兼容服务的模型名。",
                "或在启动服务前设置 OPENAI_MODEL。",
                "重新启动 run；如果是审核门恢复，填写模型名后点击“批准并恢复”。",
            ],
            topic=topic,
            stage=stage,
            details=str(exc),
            traceback=traceback_text,
        )
    if "missing api key" in lowered or "openai_api_key" in text:
        return RunDiagnostic(
            category="llm_configuration",
            severity="blocking",
            summary="API key 未配置，无法访问 OpenAI 官方接口。",
            likely_cause="Base URL 指向 api.openai.com，但 Web 表单和 OPENAI_API_KEY 都没有提供 key。",
            recommended_actions=[
                "在 Web 表单“API Key”填入 key，或在启动服务前设置 OPENAI_API_KEY。",
                "如果使用本地 OpenAI-compatible 服务，把 Base URL 改成本地地址。",
                "恢复旧 run 时，key 不会写入 run-config.json，需要重新填写或设置环境变量。",
            ],
            topic=topic,
            stage=stage,
            details=str(exc),
            traceback=traceback_text,
        )
    if "openai-compatible endpoint failed" in lowered or "urlerror" in lowered or "timed out" in lowered or "timeout" in lowered:
        return RunDiagnostic(
            category="llm_connection",
            severity="blocking",
            summary="LLM 接口连接失败或超时。",
            likely_cause="Base URL、网络、模型服务状态或超时时间配置不正确。",
            recommended_actions=[
                "检查 Base URL 是否能访问，路径通常应类似 https://api.openai.com/v1 或 http://127.0.0.1:port/v1。",
                "确认模型服务正在运行，模型名与服务端一致。",
                "大模型响应慢时设置 OPENAI_TIMEOUT_SECONDS=120 或更高后重启服务。",
            ],
            topic=topic,
            stage=stage,
            details=_short_details(str(exc)),
            traceback=traceback_text,
        )
    if "llm budget exceeded" in lowered or "llm budget invalid" in lowered:
        return RunDiagnostic(
            category="llm_budget",
            severity="blocking",
            summary="LLM 调用预算已耗尽或配置不合法。",
            likely_cause="本次 run 配置的 llm.max_calls 或 llm.max_prompt_chars 已达到上限，或预算字段为负数。",
            recommended_actions=[
                "如果需要继续当前 run，调大 Web 表单或配置文件中的 LLM 调用上限。",
                "把 llm.max_calls 或 llm.max_prompt_chars 设为 0 可取消对应限制。",
                "打开 run-llm-ledger.md 查看已发生的 LLM 调用和被预算拦截的阶段。",
            ],
            topic=topic,
            stage=stage,
            details=_short_details(str(exc)),
            traceback=traceback_text,
        )
    if "http 429" in lowered and ("semantic" in lowered or "too many requests" in lowered):
        return RunDiagnostic(
            category="literature_rate_limit",
            severity="recoverable",
            summary="文献源触发限流。",
            likely_cause="Semantic Scholar 等文献源请求频率受限，未配置 API key 时更容易出现。",
            recommended_actions=[
                "设置 SEMANTIC_SCHOLAR_API_KEY 后重跑。",
                "保留 openalex、arxiv、crossref 作为备用源。",
                "降低 max_search_queries 或 max_papers，稍后再试。",
            ],
            topic=topic,
            stage=stage,
            details=_short_details(str(exc)),
            traceback=traceback_text,
        )
    if "not approved" in lowered or "approval.json" in lowered or "invalid research plan json" in lowered or "invalid literature" in lowered:
        return RunDiagnostic(
            category="resume_artifact",
            severity="blocking",
            summary="审核门恢复所需产物缺失、未批准或损坏。",
            likely_cause="run 停在恢复点，但 approval、研究计划、文献综述或上下文 JSON 不完整。",
            recommended_actions=[
                "先查看 approval.json 和 01-review-gate.md，确认该 run 是否确实等待人工批准。",
                "如果 JSON 产物损坏，重新启动一个 run 更可靠。",
                "如果只缺批准记录，在 Web 中重新提交同一课题生成新的审核包。",
            ],
            topic=topic,
            stage=stage,
            details=_short_details(str(exc)),
            traceback=traceback_text,
        )
    if "unsupported execution mode" in lowered or "不在 allowed_commands" in text:
        return RunDiagnostic(
            category="execution_configuration",
            severity="blocking",
            summary="实验执行配置不合法。",
            likely_cause="execution.mode 或 allowed_commands 与实验命令不匹配。",
            recommended_actions=[
                "模拟阶段使用 execution.mode=simulated。",
                "本地执行时确认命令首项在 allowed_commands 白名单内。",
                "不要把任意 shell 命令交给模型生成，实验命令应由系统模板或人工确认。",
            ],
            topic=topic,
            stage=stage,
            details=_short_details(str(exc)),
            traceback=traceback_text,
        )
    return RunDiagnostic(
        category="runtime_error",
        severity="blocking",
        summary="流水线运行时失败。",
        likely_cause="当前错误不属于已知配置或文献源问题，需要查看 traceback 定位。",
        recommended_actions=[
            "打开 run-diagnostics.md 查看错误摘要和 traceback。",
            "检查最近阶段对应产物是否完整。",
            "修复后重新启动 run；若停在审核门，可尝试“批准并恢复”。",
        ],
        topic=topic,
        stage=stage,
        details=_short_details(str(exc)),
        traceback=traceback_text,
    )


def render_diagnostic_markdown(diagnostic: RunDiagnostic) -> str:
    lines = [
        "# Run 诊断",
        "",
        f"- 类型：{diagnostic.category}",
        f"- 严重性：{diagnostic.severity}",
        f"- 阶段：{diagnostic.stage or 'unknown'}",
        f"- 课题：{diagnostic.topic or 'unknown'}",
        f"- 时间：{diagnostic.created_at}",
        "",
        "## 摘要",
        diagnostic.summary,
        "",
        "## 可能原因",
        diagnostic.likely_cause,
        "",
        "## 建议动作",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(diagnostic.recommended_actions, start=1))
    if diagnostic.details:
        lines.extend(["", "## 错误详情", diagnostic.details])
    if diagnostic.traceback:
        lines.extend(["", "## Traceback", "```text", diagnostic.traceback.strip(), "```"])
    return "\n".join(lines)


def _short_details(text: str, max_chars: int = 1200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."
