"""Model failure classification and degradation constraints (T04).

decision-contract / 任务书 T04：
- 默认必需模型阶段失败时停在可恢复状态（异常向上传播，由工作流引擎记录
  失败节点）；只有显式配置（allow_template_fallback）且失败类别属于
  FALLBACK_ALLOWED_KINDS 时，才允许模板降级。
- 临时网络错误可有限重试；凭据、预算、策略问题不得以重试循环或换路径规避；
  响应结构错误不自动重试（单次尝试，记 invalid，修复次数上限=1）。
- 每个模型产物通过 04-model-stage-sources.json 保存来源
  model/template/paused 与关联失败记录；模板草稿可以保存，但不能冒充
  已完成的模型评审。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import json

from .artifacts import read_json, write_json


ModelSourceRecorder = Callable[[dict[str, Any]], None]


MODEL_STAGE_SOURCES_JSON = "04-model-stage-sources.json"

TRANSIENT_NETWORK = "transient_network"
CREDENTIAL_ERROR = "credential_error"
BUDGET_EXHAUSTED = "budget_exhausted"
POLICY_REJECTED = "policy_rejected"
INVALID_RESPONSE = "invalid_response"
PROGRAM_ERROR = "program_error"

# 只有这两类允许显式降级为模板；其余类别必须停机人工处理。
FALLBACK_ALLOWED_KINDS = frozenset({TRANSIENT_NETWORK, INVALID_RESPONSE})
MAX_TRANSIENT_RETRIES = 2

_CREDENTIAL_MARKERS = ("401", "403", "unauthorized", "invalid api key", "invalid_api_key", "api key", "credential", "认证", "凭据", "鉴权")
_BUDGET_MARKERS = ("budget", "quota", "余额", "预算", "额度")
_POLICY_MARKERS = ("content policy", "content_policy", "moderation", "flagged", "内容政策", "内容审核", "政策拒绝")
_STRUCTURE_MARKERS = ("json", "parse", "schema", "结构", "解析")


@dataclass(frozen=True)
class ModelFailure:
    kind: str
    message: str
    retryable: bool

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message[:280], "retryable": self.retryable}


def classify_model_failure(exc: BaseException) -> ModelFailure:
    """把模型阶段异常分为六类；未知异常按程序错误处理（不降级）。"""
    message = f"{type(exc).__name__}: {exc}"
    lowered = str(exc).lower()
    if any(marker in lowered for marker in _BUDGET_MARKERS):
        return ModelFailure(BUDGET_EXHAUSTED, message, retryable=False)
    if any(marker in lowered for marker in _CREDENTIAL_MARKERS):
        return ModelFailure(CREDENTIAL_ERROR, message, retryable=False)
    if any(marker in lowered for marker in _POLICY_MARKERS):
        return ModelFailure(POLICY_REJECTED, message, retryable=False)
    if isinstance(exc, TimeoutError) or "timeout" in lowered or "timed out" in lowered or isinstance(exc, ConnectionError):
        return ModelFailure(TRANSIENT_NETWORK, message, retryable=True)
    if any(marker in lowered for marker in _STRUCTURE_MARKERS):
        return ModelFailure(INVALID_RESPONSE, message, retryable=False)
    return ModelFailure(PROGRAM_ERROR, message, retryable=False)


def call_with_bounded_retry(call: Callable[[], Any], *, max_retries: int = MAX_TRANSIENT_RETRIES) -> Any:
    """执行模型调用；仅临时网络错误有限重试，其余类别直接抛出。"""
    attempts = 0
    while True:
        try:
            return call()
        except Exception as exc:
            attempts += 1
            failure = classify_model_failure(exc)
            if failure.kind == TRANSIENT_NETWORK and attempts <= max_retries:
                continue
            raise


def record_model_stage_source(
    run_dir: Path | None,
    stage: str,
    source: str,
    *,
    call_id: int = 0,
    failure: "ModelFailure | dict[str, Any] | None" = None,
    independent_completed: bool | None = None,
) -> None:
    """把阶段来源与失败记录写入 04-model-stage-sources.json（run_dir 为空时忽略）。"""
    if run_dir is None:
        return
    path = Path(run_dir) / MODEL_STAGE_SOURCES_JSON
    payload = read_json(path) if path.exists() else {}
    stages = payload.get("stages") if isinstance(payload, dict) else None
    if not isinstance(stages, dict):
        stages = {}
    entry: dict[str, Any] = {"source": source, "call_id": int(call_id or 0)}
    if isinstance(failure, ModelFailure):
        entry["failure"] = failure.to_dict()
    elif isinstance(failure, dict) and failure:
        entry["failure"] = failure
    if independent_completed is not None:
        entry["independent_review_completed"] = bool(independent_completed)
    stages[stage] = entry
    write_json(path, {"schema_version": 1, "stages": stages})


def fallback_permitted(config: Any, failure: ModelFailure) -> bool:
    """模板降级判据：显式开启 + 失败类别在允许集合内。"""
    return bool(getattr(config, "allow_template_fallback", False)) and failure.kind in FALLBACK_ALLOWED_KINDS
