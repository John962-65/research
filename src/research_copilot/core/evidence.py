"""证据引用与台账：哈希固定、失效检测、引用有效性校验（L1 层的基础）。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .models import EvidenceRef, Material


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def material_ref(material: Material, locator: str = "", data_range: str = "") -> EvidenceRef:
    """从材料登记项构造证据引用（固定当时的 sha256）。"""
    return EvidenceRef(
        material_id=material.id,
        sha256=material.sha256,
        locator=locator,
        data_range=data_range,
        analysis_code_version=material.meta.get("analysis_code_version", ""),
    )


def check_ref(
    ref: EvidenceRef, materials_by_id: dict[str, Material], project_dir: Path | None = None
) -> dict[str, Any]:
    """L1 引用有效性检查。

    返回 {"status": valid | stale | missing | broken, "detail": str}
    - valid   材料存在且当前文件 sha256 与引用一致
    - stale   材料仍登记但文件内容已变化（引用过期，阻断结论升级）
    - missing 引用的材料 ID 不在登记表中
    - broken  文件路径不可读
    """
    material = materials_by_id.get(ref.material_id)
    if material is None:
        return {"status": "missing", "detail": f"材料 {ref.material_id} 不在登记表中"}
    path = Path(material.path)
    if not path.is_absolute() and project_dir is not None:
        path = project_dir / path
    if not path.exists():
        return {"status": "broken", "detail": f"材料文件不可读: {material.path}"}
    try:
        current = sha256_file(path)
    except OSError as exc:
        return {"status": "broken", "detail": f"读取失败: {exc}"}
    if current != ref.sha256:
        return {"status": "stale", "detail": f"材料 {ref.material_id} 内容已更新，引用指向旧哈希"}
    return {"status": "valid", "detail": "ok"}
