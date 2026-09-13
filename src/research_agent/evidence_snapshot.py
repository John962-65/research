"""Evidence snapshots (decision-contract §4).

一次判断实际使用的输入清单：文件标识（项目相对路径）、内容 SHA-256、
角色、版本。哈希只用于内容一致性检测，不证明内容真实，也不防篡改。

两类快照（契约 §3.2）：
- 评审输入快照（review_input）：参与最终裁决的全部输入内容，不含评审输出。
- 最终裁决快照：10-gate-decision.json 本身，引用评审输入快照 digest 并
  包含已生成的评审输出；人工覆盖绑定最终裁决快照。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json

from .artifacts import write_json, utc_now as _utc_now


REVIEW_INPUT_SNAPSHOT_JSON = "10-review-input-snapshot.json"

SNAPSHOT_SCHEMA_VERSION = 1


class SnapshotError(ValueError):
    """输入无法规范化（如含 NaN/Inf）时抛出；调用方应判 invalid 并阻断覆盖。"""


def canonical_json_bytes(payload: Any) -> bytes:
    """契约冻结的 JSON 规范化：sort_keys、紧凑分隔符、禁 NaN/Inf。"""
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"payload cannot be canonicalized: {exc}") from exc


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def file_sha256(path: Path) -> str | None:
    """文件内容 SHA-256；文件缺失/不可读返回 None（与"内容为空"区分）。"""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def build_review_input_snapshot(
    run_dir: Path,
    *,
    revision: int,
    file_inputs: dict[str, str],
    inline_inputs: dict[str, Any],
    rule_versions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """构建评审输入快照。

    ``file_inputs``: 相对/绝对路径 → 角色（如 manuscript、results）。
    ``inline_inputs``: 名称 → 内存中的报告对象（JSON 可序列化），
    如 citation_grounding 全量报告、复审全量内容。
    含 NaN/Inf 的 inline 输入抛出 SnapshotError，由调用方判 invalid。
    """
    items: list[dict[str, Any]] = []
    for name, role in file_inputs.items():
        digest = file_sha256(Path(run_dir) / name)
        items.append(
            {
                "name": name,
                "role": role,
                "source": "file",
                "sha256": digest,
                "missing": digest is None,
            }
        )
    for name, payload in inline_inputs.items():
        try:
            digest = payload_sha256(payload)
        except SnapshotError:
            items.append({"name": name, "role": "inline", "source": "inline", "sha256": None, "missing": False, "invalid": True})
            continue
        items.append({"name": name, "role": "inline", "source": "inline", "sha256": digest, "missing": False})
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": "review_input",
        "revision": int(revision),
        "created_at": _utc_now(),
        "rule_versions": dict(rule_versions or {}),
        "items": items,
    }
    snapshot["digest"] = _digest_of_items(snapshot)
    return snapshot


def _digest_of_items(snapshot: dict[str, Any]) -> str:
    payload = {
        "schema_version": snapshot.get("schema_version"),
        "kind": snapshot.get("kind"),
        "revision": snapshot.get("revision"),
        "rule_versions": snapshot.get("rule_versions"),
        "items": snapshot.get("items"),
    }
    return payload_sha256(payload)


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    """快照摘要；兼容手写/旧结构快照（无 digest 字段时现算）。"""
    if not isinstance(snapshot, dict) or not snapshot.get("items"):
        return ""
    stored = str(snapshot.get("digest") or "")
    if stored:
        return stored
    return _digest_of_items(snapshot)


def verify_snapshot(run_dir: Path, snapshot: dict[str, Any]) -> list[str]:
    """核对快照中的文件条目是否仍然一致；返回已变化/缺失的条目名。

    只核对 file 来源条目（inline 内容在构建后不落盘、不参与 TOCTOU 复核）。
    """
    changed: list[str] = []
    if not isinstance(snapshot, dict):
        return ["<snapshot not a dict>"]
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict) or item.get("source") != "file":
            continue
        name = str(item.get("name") or "")
        if item.get("invalid"):
            changed.append(f"{name}:invalid")
            continue
        current = file_sha256(Path(run_dir) / name)
        if current != item.get("sha256"):
            changed.append(name)
    return changed


def write_review_input_snapshot(run_dir: Path, snapshot: dict[str, Any]) -> Path:
    path = Path(run_dir) / REVIEW_INPUT_SNAPSHOT_JSON
    write_json(path, snapshot)
    return path


def load_review_input_snapshot(run_dir: Path) -> dict[str, Any] | None:
    path = Path(run_dir) / REVIEW_INPUT_SNAPSHOT_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and snapshot_digest(data) else None
