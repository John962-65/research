"""Old-run migration (T17).

旧 Run（schema v1 及更早）可以浏览，但不能直接进入 publishable gate；
`migrate-run --dry-run` 盘点文件/哈希/schema 差异并列出迁移项，显式
`--apply` 才执行：先做不可变备份（含哈希清单），再标记 legacy 状态并使
旧批准失效。迁移不伪造 attempt、来源或人工批准；重复执行幂等。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import shutil

from .artifacts import read_json, utc_now as _utc_now, write_json


MIGRATION_RECORD_JSON = "00-migration.json"

# 旧 schema 检查项：路径 → 判定函数（返回 (needs_migration, finding)）。
_SCHEMA_CHECKS = {
    "04-evidence-integrity.json": lambda d: (
        int(d.get("schema_version") or 1) < 2,
        f"evidence-integrity schema_version={d.get('schema_version') or 1} < 2（缺四计数与维度拆分）",
    ),
    "03-preregistration.json": lambda d: (
        "revision" not in d,
        "preregistration 缺 revision 字段（版本化之前的结构）",
    ),
    "10-gate-decision.json": lambda d: (
        str((d.get("inputs") or {}).get("rule_version") or "") != "2",
        "gate decision 缺 rule_version=2（旧摘要规则）",
    ),
    "10-independent-deliberation.json": lambda d: (
        "review_input_sha256" not in d,
        "deliberation 缺 review_input_sha256（旧缓存键）",
    ),
}


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def plan_migration(run_dir: Path) -> dict[str, Any]:
    """盘点（dry-run）：文件清单+哈希、schema 差异、迁移项；不做任何修改。"""
    run_dir = Path(run_dir)
    files: list[dict[str, Any]] = []
    findings: list[str] = []
    actions: list[str] = []
    for name in sorted(_SCHEMA_CHECKS):
        path = run_dir / name
        if not path.exists():
            findings.append(f"{name}: 缺失（按 unknown 处理，不补造）")
            continue
        try:
            data = read_json(path)
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        needs, finding = _SCHEMA_CHECKS[name](data)
        files.append({"path": name, "sha256": _sha256_file(path)})
        if needs:
            findings.append(f"{name}: {finding}")
    approval_path = run_dir / "approval.json"
    approval_stale = False
    if approval_path.exists():
        files.append({"path": "approval.json", "sha256": _sha256_file(approval_path)})
        try:
            approval = read_json(approval_path)
        except (OSError, ValueError):
            approval = {}
        approval = approval if isinstance(approval, dict) else {}
        if not approval.get("approval_binding_sha256"):
            approval_stale = True
            findings.append("approval.json 缺 approval_binding_sha256（旧批准无法核验绑定）")
            actions.append("旧批准将在 apply 时失效（approved=False + stale 标记，追加历史记录，不删除原批准内容）")
    if not (run_dir / "04-experiment-attempts.json").exists():
        findings.append("04-experiment-attempts.json 缺失：无执行尝试账本（不伪造尝试记录）")
    record = _read_record(run_dir)
    already = bool(record)
    actions.insert(0, "写入 00-migration.json 迁移记录并标记 run 为 legacy_unscoped")
    return {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "mode": "dry-run",
        "already_migrated": already,
        "files": files,
        "findings": findings,
        "actions": [] if already else actions,
        "legacy_unscoped": True,
        "note": (
            "旧 Run 可浏览；进入 publishable gate 前必须迁移。"
            "迁移使旧批准失效并要求按当前 schema 重新核验。"
            if not already
            else "该 run 已迁移；重复执行幂等。"
        ),
    }


def apply_migration(run_dir: Path) -> dict[str, Any]:
    """显式迁移：不可变备份 → 写迁移记录 → 旧批准失效 → 标记 legacy_unscoped。"""
    run_dir = Path(run_dir)
    plan = plan_migration(run_dir)
    if plan["already_migrated"]:
        plan["mode"] = "apply(already-migrated)"
        return plan
    # 1) 不可变备份：迁移前的文件与哈希清单一起保存。
    backup_dir = run_dir / "migration-backup"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(parents=True)
    backup_manifest = []
    for item in plan["files"]:
        source = run_dir / item["path"]
        if item["sha256"] and source.exists():
            shutil.copy2(source, backup_dir / item["path"])
            backup_manifest.append(item)
    write_json(backup_dir / "BACKUP-MANIFEST.json", {
        "schema_version": 1,
        "created_at": _utc_now(),
        "files": backup_manifest,
        "note": "迁移前不可变备份；哈希见各条目。迁移不伪造 attempt、来源或人工批准。",
    })
    # 2) 旧批准失效（追加历史，不删除原内容）。
    invalidated = False
    approval_path = run_dir / "approval.json"
    if approval_path.exists():
        try:
            approval = read_json(approval_path)
        except (OSError, ValueError):
            approval = {}
        if isinstance(approval, dict) and approval:
            history = approval.get("history") if isinstance(approval.get("history"), list) else []
            history.append({
                "action": "invalidated_by_schema_migration",
                "at": _utc_now(),
                "reason": "旧批准缺少可核验绑定（approval_binding_sha256）；迁移后必须按当前 schema 重新审批。",
            })
            approval["history"] = history
            approval["approved"] = False
            approval["approved_at"] = None
            approval["stale_previous_approval"] = True
            write_json(approval_path, approval)
            invalidated = True
    # 3) 迁移记录与 legacy 标记。
    record = {
        "schema_version": 1,
        "applied_at": _utc_now(),
        "mode": "apply",
        "migration_status": "legacy_unscoped",
        "backup_dir": str(backup_dir),
        "findings": plan["findings"],
        "old_approval_invalidated": invalidated,
        "note": "迁移不伪造 attempt、来源或人工批准；补齐缺失材料后按当前 schema 重新核验。",
    }
    write_json(run_dir / MIGRATION_RECORD_JSON, record)
    state_path = run_dir / "state.json"
    try:
        state = read_json(state_path)
    except (OSError, ValueError):
        state = {}
    if isinstance(state, dict) and state:
        state["migration"] = {"status": "legacy_unscoped", "at": record["applied_at"]}
        write_json(state_path, state)
    result = plan_migration(run_dir)
    result["mode"] = "apply"
    result["backup_dir"] = str(backup_dir)
    result["old_approval_invalidated"] = invalidated
    return result


def _read_record(run_dir: Path) -> dict[str, Any] | None:
    path = Path(run_dir) / MIGRATION_RECORD_JSON
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("migration_status") else None
