from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
import hashlib
import json
import os
import time

from .artifacts import write_json, write_text, cell as _cell, sha256_text as _sha256_text, utc_now as _utc_now
from .config import LLMConfig
from .llm import LLM


LLM_TRACE_JSON = "run-llm-ledger.json"
LLM_TRACE_MD = "run-llm-ledger.md"


@dataclass(frozen=True)
class LLMTraceEntry:
    call_id: int
    stage: str
    purpose: str
    provider: str
    model: str
    base_url: str
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    system_chars: int
    user_chars: int
    response_chars: int
    system_sha256: str
    user_sha256: str
    response_sha256: str = ""
    error: str = ""
    validation_status: str = "not_required"
    validation_error: str = ""
    agent_id: str = ""
    task_id: str = ""
    task_type: str = ""
    route_id: str = ""
    skills: list[str] = field(default_factory=list)
    skill_hashes: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    usage_input_tokens: int = 0
    usage_output_tokens: int = 0
    usage_source: str = ""
    workflow_revision: int = 0


@dataclass(frozen=True)
class LLMTraceReport:
    total_calls: int
    successful_calls: int
    failed_calls: int
    budget_exceeded_calls: int
    total_prompt_chars: int
    total_response_chars: int
    entries: list[LLMTraceEntry] = field(default_factory=list)
    invalid_response_calls: int = 0
    validation_pending_calls: int = 0


class TracedLLM:
    def __init__(self, inner: LLM, run_dir: Path, config: LLMConfig) -> None:
        self.inner = inner
        self.run_dir = run_dir
        self.config = config

    def complete(self, system: str, user: str) -> str:
        return self.complete_with_purpose(system, user, stage="", purpose="")

    def complete_with_purpose(
        self,
        system: str,
        user: str,
        *,
        stage: str = "",
        purpose: str = "",
        requires_validation: bool = False,
        agent_id: str = "",
    ) -> str:
        response, _call_id = self.complete_validatable(
            system,
            user,
            stage=stage,
            purpose=purpose,
            requires_validation=requires_validation,
            agent_id=agent_id,
        )
        return response

    def complete_validatable(
        self,
        system: str,
        user: str,
        *,
        stage: str = "",
        purpose: str = "",
        requires_validation: bool = False,
        agent_id: str = "",
    ) -> tuple[str, int]:
        """Run one traced call and return ``(response, call_id)`` (TRACE-01).

        The call id is the only safe key for attaching a validation result to
        the exact ledger entry it belongs to; matching by stage alone can hit
        the wrong pending entry when a stage calls the model more than once.
        """
        with _ledger_lock(self.run_dir):
            prepared = _prepare_request(self.inner, system, user, stage=stage, purpose=purpose, agent_id=agent_id)
            conversation = getattr(self.inner, "complete_prepared_with_trace", None)
            if prepared is not None and callable(conversation):
                final_call_id = 0

                def complete_request(request: Any) -> str:
                    nonlocal final_call_id
                    response, final_call_id = self._complete_request(
                        request, system, user, stage=stage, purpose=purpose,
                        requires_validation=False, agent_id=agent_id,
                        complete=self.inner.complete_request,
                    )
                    return response

                try:
                    response = conversation(prepared, complete_request)
                except Exception as exc:
                    metadata = _route_metadata(getattr(prepared, "route", None), stage=stage, agent_id=agent_id)
                    _publish_activity(self.run_dir, metadata, status="failed", detail=str(exc))
                    raise
                if requires_validation:
                    # Intermediate tool requests succeeded; only the final answer needs schema validation.
                    entries = _read_entries(self.run_dir / LLM_TRACE_JSON)
                    entries = [
                        replace(entry, status="validation_pending") if entry.call_id == final_call_id else entry
                        for entry in entries
                    ]
                    report = _report(entries)
                    write_json(self.run_dir / LLM_TRACE_JSON, report)
                    write_text(self.run_dir / LLM_TRACE_MD, render_llm_trace_markdown(report))
                return response, final_call_id
            return self._complete_request(
                prepared, system, user, stage=stage, purpose=purpose,
                requires_validation=requires_validation, agent_id=agent_id,
            )

    def _complete_request(
        self,
        prepared: Any,
        system: str,
        user: str,
        *,
        stage: str,
        purpose: str,
        requires_validation: bool,
        agent_id: str,
        complete: Callable[[Any], str] | None = None,
    ) -> tuple[str, int]:
        traced_system = str(getattr(prepared, "system", system))
        traced_user = str(getattr(prepared, "user", user))
        route = getattr(prepared, "route", None)
        metadata = _route_metadata(route, stage=stage, agent_id=agent_id)
        started_at = _utc_now()
        started = time.monotonic()
        _publish_activity(self.run_dir, metadata, status="running")
        budget_error, budget_status = self._budget_error(traced_system, traced_user)
        if budget_error:
            call_id = self._append(
                traced_system,
                traced_user,
                "",
                started_at,
                started,
                budget_status,
                budget_error,
                stage=stage,
                purpose=purpose,
                route=route,
                skill_records=_prepared_skill_records(prepared),
            )
            _publish_activity(self.run_dir, metadata, status="failed", detail=budget_error)
            raise RuntimeError(budget_error)
        try:
            response = complete(prepared) if complete is not None else _complete_prepared(self.inner, prepared, traced_system, traced_user)
        except Exception as exc:
            self._append(
                traced_system,
                traced_user,
                "",
                started_at,
                started,
                "failed",
                str(exc),
                stage=stage,
                purpose=purpose,
                route=route,
                skill_records=_prepared_skill_records(prepared),
            )
            _publish_activity(self.run_dir, metadata, status="failed", detail=str(exc))
            raise
        status = "validation_pending" if requires_validation else "success"
        call_id = self._append(
            traced_system,
            traced_user,
            response,
            started_at,
            started,
            status,
            "",
            stage=stage,
            purpose=purpose,
            route=route,
            skill_records=_prepared_skill_records(prepared),
            route_usage=getattr(self.inner, "last_usage", None),
        )
        _publish_activity(self.run_dir, metadata, status="completed")
        return response, call_id

    def complete_as_agent(
        self,
        system: str,
        user: str,
        *,
        stage: str,
        purpose: str,
        agent_id: str,
        requires_validation: bool = False,
    ) -> str:
        return self.complete_with_purpose(
            system,
            user,
            stage=stage,
            purpose=purpose,
            requires_validation=requires_validation,
            agent_id=agent_id,
        )

    def record_validation_result(self, *, stage: str, valid: bool, error: str = "", call_id: int = 0) -> None:
        with _ledger_lock(self.run_dir):
            entries = _read_entries(self.run_dir / LLM_TRACE_JSON)
            normalized_stage = _stage(stage)
            if call_id > 0:
                # TRACE-01: attach to the exact call, never to a later pending
                # entry that happens to share the stage.
                index = next(
                    (
                        index
                        for index in range(len(entries) - 1, -1, -1)
                        if entries[index].call_id == call_id
                        and entries[index].stage == normalized_stage
                        and entries[index].status == "validation_pending"
                    ),
                    None,
                )
            else:
                index = next(
                    (
                        index
                        for index in range(len(entries) - 1, -1, -1)
                        if entries[index].stage == normalized_stage and entries[index].status == "validation_pending"
                    ),
                    None,
                )
            if index is None:
                return
            entries[index] = replace(
                entries[index],
                status="success" if valid else "invalid_response",
                error="" if valid else _short_error(error or "response failed semantic validation"),
                validation_status="accepted" if valid else "rejected",
                validation_error="" if valid else _short_error(error or "response failed semantic validation"),
            )
            report = _report(entries)
            write_json(self.run_dir / LLM_TRACE_JSON, report)
            write_text(self.run_dir / LLM_TRACE_MD, render_llm_trace_markdown(report))

    def _budget_error(self, system: str, user: str) -> tuple[str, str]:
        if self.config.max_calls < 0:
            return "LLM budget invalid: max_calls must be >= 0", "failed"
        if self.config.max_prompt_chars < 0:
            return "LLM budget invalid: max_prompt_chars must be >= 0", "failed"
        entries = _read_entries(self.run_dir / LLM_TRACE_JSON)
        used_calls = _actual_call_count(entries)
        next_prompt_chars = len(system) + len(user)
        used_prompt_chars = _actual_prompt_chars(entries)
        if self.config.max_calls > 0 and used_calls >= self.config.max_calls:
            return f"LLM budget exceeded: max_calls={self.config.max_calls}, used_calls={used_calls}", "budget_exceeded"
        if self.config.max_prompt_chars > 0 and used_prompt_chars + next_prompt_chars > self.config.max_prompt_chars:
            return (
                "LLM budget exceeded: "
                f"max_prompt_chars={self.config.max_prompt_chars}, "
                f"used_prompt_chars={used_prompt_chars}, "
                f"next_prompt_chars={next_prompt_chars}"
            ), "budget_exceeded"
        return "", ""

    def _append(
        self,
        system: str,
        user: str,
        response: str,
        started_at: str,
        started: float,
        status: str,
        error: str,
        *,
        stage: str,
        purpose: str,
        route: Any = None,
        skill_records: tuple[dict[str, Any], ...] = (),
        route_usage: dict[str, Any] | None = None,
    ) -> int:
        entries = _read_entries(self.run_dir / LLM_TRACE_JSON)
        entry = LLMTraceEntry(
            call_id=len(entries) + 1,
            stage=_stage(stage),
            purpose=_purpose(system, purpose),
            provider=self.config.provider,
            model=_route_value(route, "model") or _runtime_model(self.inner, self.config),
            status=status,
            started_at=started_at,
            completed_at=_utc_now(),
            duration_seconds=round(time.monotonic() - started, 3),
            system_chars=len(system),
            user_chars=len(user),
            response_chars=len(response),
            system_sha256=_sha256_text(system),
            user_sha256=_sha256_text(user),
            response_sha256=_sha256_text(response) if response else "",
            error=_short_error(error),
            agent_id=_route_value(route, "agent_id"),
            task_id=_route_value(route, "task_id"),
            task_type=_route_value(route, "stage") or _stage(stage),
            route_id=_route_value(route, "route_id"),
            skills=_route_list(route, "skills"),
            skill_hashes=[
                f"{record.get('skill_id', '')}:{str(record.get('sha256', ''))[:16]}"
                for record in skill_records
                if isinstance(record, dict)
            ],
            mcp_servers=_route_list(route, "mcp_servers"),
            usage_input_tokens=_safe_usage_value((route_usage or {}).get("input_tokens")),
            usage_output_tokens=_safe_usage_value((route_usage or {}).get("output_tokens")),
            usage_source="provider" if route_usage else "",
            workflow_revision=_workflow_revision(self.run_dir),
            base_url=_redact_url(_entry_base_url(route, self.inner, self.config)),
        )
        report = _report([*entries, entry])
        write_json(self.run_dir / LLM_TRACE_JSON, report)
        write_text(self.run_dir / LLM_TRACE_MD, render_llm_trace_markdown(report))
        return entry.call_id


def _prepared_skill_records(prepared: Any) -> tuple[dict[str, Any], ...]:
    records = getattr(prepared, "skill_records", ())
    return tuple(record for record in records if isinstance(record, dict))


def _safe_usage_value(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
    records = getattr(prepared, "skill_records", ())
    return tuple(record for record in records if isinstance(record, dict))


def trace_llm(llm: LLM, run_dir: Path, config: LLMConfig) -> LLM:
    return TracedLLM(llm, run_dir, config)


def complete_with_purpose(
    llm: LLM,
    system: str,
    user: str,
    *,
    stage: str,
    purpose: str,
    requires_validation: bool = False,
    agent_id: str = "",
) -> str:
    complete = getattr(llm, "complete_with_purpose", None)
    if callable(complete):
        return complete(
            system,
            user,
            stage=stage,
            purpose=purpose,
            requires_validation=requires_validation,
            agent_id=agent_id,
        )
    return llm.complete(system, user)


def complete_as_agent(
    llm: LLM,
    system: str,
    user: str,
    *,
    stage: str,
    purpose: str,
    agent_id: str,
    requires_validation: bool = False,
) -> str:
    complete = getattr(llm, "complete_as_agent", None)
    if callable(complete):
        return complete(
            system,
            user,
            stage=stage,
            purpose=purpose,
            agent_id=agent_id,
            requires_validation=requires_validation,
        )
    return complete_with_purpose(
        llm,
        system,
        user,
        stage=stage,
        purpose=purpose,
        requires_validation=requires_validation,
    )


def complete_with_purpose_detail(
    llm: LLM,
    system: str,
    user: str,
    *,
    stage: str,
    purpose: str,
    requires_validation: bool = False,
    agent_id: str = "",
) -> tuple[str, int]:
    """Run one (traced) call and return ``(response, call_id)`` (TRACE-01)."""
    validatable = getattr(llm, "complete_validatable", None)
    if callable(validatable):
        return validatable(
            system,
            user,
            stage=stage,
            purpose=purpose,
            requires_validation=requires_validation,
            agent_id=agent_id,
        )
    complete = getattr(llm, "complete_with_purpose", None)
    if callable(complete):
        response = complete(
            system,
            user,
            stage=stage,
            purpose=purpose,
            requires_validation=requires_validation,
        )
        return response, 0
    return llm.complete(system, user), 0


def record_validation_result(
    llm: LLM,
    *,
    stage: str,
    valid: bool,
    error: str = "",
    call_id: int = 0,
) -> None:
    record = getattr(llm, "record_validation_result", None)
    if callable(record):
        record(stage=stage, valid=valid, error=error, call_id=call_id)


def render_llm_trace_markdown(report: LLMTraceReport) -> str:
    lines = [
        "# LLM 调用账本",
        "",
        f"- 总调用：{report.total_calls}",
        f"- 成功：{report.successful_calls}",
        f"- 失败：{report.failed_calls}",
        f"- 预算拦截：{report.budget_exceeded_calls}",
        f"- 结构无效：{report.invalid_response_calls}",
        f"- 待结构验证：{report.validation_pending_calls}",
        f"- Prompt 字符：{report.total_prompt_chars}",
        f"- Response 字符：{report.total_response_chars}",
        "",
        "## 调用明细",
        "| ID | 状态 | 阶段 | Agent | 用途 | 模型 | 耗时 | Prompt 字符 | Response 字符 | Prompt Hash | Response Hash | 错误 |",
        "| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for item in report.entries:
        prompt_chars = item.system_chars + item.user_chars
        prompt_hash = f"{item.system_sha256[:10]}/{item.user_sha256[:10]}"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.call_id),
                    item.status,
                    _cell(item.stage or "-"),
                    _cell(item.agent_id or "-"),
                    _cell(item.purpose),
                    _cell(item.model),
                    f"{item.duration_seconds:.3f}",
                    str(prompt_chars),
                    str(item.response_chars),
                    f"`{prompt_hash}`",
                    f"`{item.response_sha256[:10]}`" if item.response_sha256 else "-",
                    _cell(item.error or "-"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 说明",
            "- 账本只记录 prompt/response 的长度和 SHA256，不保存完整内容或 API key。",
            "- 失败调用也会落账，便于定位 LLM 超时、HTTP 错误或格式错误的阶段。",
            "- 预算拦截会在真实模型请求前发生，状态记录为 budget_exceeded。",
        ]
    )
    return "\n".join(lines)


def _report(entries: list[LLMTraceEntry]) -> LLMTraceReport:
    return LLMTraceReport(
        total_calls=len(entries),
        successful_calls=sum(1 for item in entries if item.status == "success"),
        failed_calls=sum(1 for item in entries if item.status == "failed"),
        budget_exceeded_calls=sum(1 for item in entries if item.status == "budget_exceeded"),
        total_prompt_chars=sum(item.system_chars + item.user_chars for item in entries),
        total_response_chars=sum(item.response_chars for item in entries),
        entries=entries,
        invalid_response_calls=sum(1 for item in entries if item.status == "invalid_response"),
        validation_pending_calls=sum(1 for item in entries if item.status == "validation_pending"),
    )


def _actual_call_count(entries: list[LLMTraceEntry]) -> int:
    return sum(1 for item in entries if item.status in {"success", "failed", "invalid_response", "validation_pending"})


def _actual_prompt_chars(entries: list[LLMTraceEntry]) -> int:
    return sum(
        item.system_chars + item.user_chars
        for item in entries
        if item.status in {"success", "failed", "invalid_response", "validation_pending"}
    )


def _read_entries(path: Path) -> list[LLMTraceEntry]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("entries", []) if isinstance(data, dict) else []
    entries: list[LLMTraceEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item = {
            "stage": "",
            "validation_status": "not_required",
            "validation_error": "",
            "agent_id": "",
            "task_id": "",
            "task_type": "",
            "route_id": "",
            "skills": [],
            "skill_hashes": [],
            "mcp_servers": [],
            "usage_input_tokens": 0,
            "usage_output_tokens": 0,
            "usage_source": "",
            "workflow_revision": 0,
            **item,
        }
        try:
            entries.append(LLMTraceEntry(**item))
        except TypeError:
            continue
    return entries


def _stage(stage: str) -> str:
    return stage.strip().lower().replace(" ", "_")[:96]


def _purpose(system: str, purpose: str = "") -> str:
    first_line = purpose.strip() or (system.strip().splitlines()[0] if system.strip() else "LLM call")
    return first_line[:96]


def _short_error(value: str) -> str:
    value = value.replace("\n", " ").strip()
    return value[:280]


def _runtime_model(inner: LLM, config: LLMConfig) -> str:
    model = getattr(inner, "model", "")
    if isinstance(model, str) and model.strip():
        return model.strip()
    if config.model:
        return config.model
    env_model = os.environ.get(config.model_env, "")
    return env_model or config.model_env


def _runtime_base_url(inner: LLM, config: LLMConfig) -> str:
    base_url = getattr(inner, "base_url", "")
    if isinstance(base_url, str) and base_url.strip():
        return base_url.strip()
    if config.base_url:
        return config.base_url
    env_base_url = os.environ.get(config.base_url_env, "")
    return env_base_url or config.base_url_env


def _entry_base_url(route: Any, inner: LLM, config: LLMConfig) -> str:
    routed = _route_value(route, "base_url")
    if routed:
        return routed
    return _runtime_base_url(inner, config)


_LEDGER_LOCKS_GUARD = Lock()
_LEDGER_LOCKS: dict[str, Lock] = {}


def _ledger_lock(run_dir: Path) -> Lock:
    key = str(run_dir.resolve())
    with _LEDGER_LOCKS_GUARD:
        return _LEDGER_LOCKS.setdefault(key, Lock())


def _prepare_request(inner: LLM, system: str, user: str, *, stage: str, purpose: str, agent_id: str) -> Any:
    prepare = getattr(inner, "prepare_request", None)
    if callable(prepare):
        return prepare(system, user, stage=stage, purpose=purpose, agent_id=agent_id)
    return None


def _complete_prepared(inner: LLM, prepared: Any, system: str, user: str) -> str:
    complete = getattr(inner, "complete_prepared", None)
    if prepared is not None and callable(complete):
        return complete(prepared)
    return inner.complete(system, user)


def _route_metadata(route: Any, *, stage: str, agent_id: str) -> dict[str, str]:
    return {
        "stage": _route_value(route, "stage") or _stage(stage),
        "agent_id": _route_value(route, "agent_id") or agent_id,
        "task": _route_value(route, "task"),
        "model": _route_value(route, "model"),
    }


def _route_value(route: Any, name: str) -> str:
    value = getattr(route, name, "") if route is not None else ""
    return str(value or "").strip()


def _route_list(route: Any, name: str) -> list[str]:
    value = getattr(route, name, []) if route is not None else []
    return [str(item) for item in value] if isinstance(value, list) else []


def _publish_activity(run_dir: Path, metadata: dict[str, str], *, status: str, detail: str = "") -> None:
    try:
        from .workflow_graph import update_agent_activity

        update_agent_activity(
            run_dir,
            stage=metadata["stage"],
            agent_id=metadata["agent_id"],
            task=metadata["task"],
            model=metadata["model"],
            status=status,
            detail=_short_error(detail),
        )
    except Exception:
        return


def _workflow_revision(run_dir: Path) -> int:
    try:
        data = json.loads((run_dir / "workflow-status.json").read_text(encoding="utf-8"))
        return int(data.get("revision") or 0) if isinstance(data, dict) else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def _redact_url(value: str) -> str:
    return value.replace("@", "@***")

