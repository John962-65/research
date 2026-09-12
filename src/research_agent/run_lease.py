"""Cross-process run lease (LOCK-01).

Every mutating entry point (pipeline run/resume/repair-resume in the pipeline
module, rollback apply in workflow_graph) holds an exclusive lease on the run
directory for the duration of the write path, no matter whether the caller is
the Web worker, the CLI, or a second server process. Gate-signal writes
(approval.json, cancel.json) are deliberately exempt: the pipeline consumes
them while holding the lease.

The lock is an OS-level ``flock`` on ``<run_dir>/.lease`` so it is released
automatically when a process dies; the file also carries JSON metadata
(owner, pid, operation) for diagnostics and conflict messages. The lease is
reentrant only in the owning thread (pipeline resume paths call each other).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, get_ident
from typing import Any, Iterator
import fcntl
import json
import os

from .artifacts import write_json


LEASE_FILENAME = ".lease"


class RunLeaseConflict(RuntimeError):
    """Another process holds the lease for this run directory."""

    def __init__(self, run_dir: Path, operation: str, holder: dict[str, Any]) -> None:
        holder_desc = ", ".join(
            f"{key}={holder[key]}" for key in ("owner", "pid", "operation") if holder.get(key)
        ) or "unknown holder"
        super().__init__(
            f"run lease conflict on {run_dir.name}: another process holds the lease "
            f"({holder_desc}); stop that operation before starting '{operation}'"
        )
        self.run_dir = run_dir
        self.operation = operation
        self.holder = holder


@dataclass(frozen=True)
class RunLease:
    run_dir: Path
    operation: str
    owner: str
    acquired_at: str


_PROCESS_LOCKS_GUARD = Lock()
_PROCESS_LEASE_DEPTH: dict[str, int] = {}
_PROCESS_LEASE_OWNER: dict[str, tuple[int, int]] = {}


def lease_path(run_dir: Path) -> Path:
    return run_dir / LEASE_FILENAME


def read_lease_holder(run_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads(lease_path(run_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@contextmanager
def acquire_run_lease(
    run_dir: Path,
    operation: str,
    owner: str = "",
    *,
    conflict_note: str = "",
) -> Iterator[RunLease]:
    """Hold an exclusive, reentrant, crash-safe lease on ``run_dir``."""
    resolved = Path(run_dir).resolve()
    key = str(resolved)
    identity = (os.getpid(), get_ident())
    with _PROCESS_LOCKS_GUARD:
        depth = _PROCESS_LEASE_DEPTH.get(key, 0)
        if depth and _PROCESS_LEASE_OWNER.get(key) != identity:
            raise RunLeaseConflict(resolved, operation, read_lease_holder(resolved))
        _PROCESS_LEASE_OWNER[key] = identity
        _PROCESS_LEASE_DEPTH[key] = depth + 1
    fd: int | None = None
    try:
        if depth > 0:
            # Only the owning thread may reenter; other threads fail fast.
            yield RunLease(run_dir=resolved, operation=operation, owner=owner, acquired_at="")
            return
        resolved.mkdir(parents=True, exist_ok=True)
        path = lease_path(resolved)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            holder = read_lease_holder(resolved)
            raise RunLeaseConflict(resolved, operation, holder) from exc
        acquired_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "owner": owner or f"pid:{os.getpid()}",
            "pid": os.getpid(),
            "operation": operation,
            "acquired_at": acquired_at,
            "note": str(conflict_note or "")[:200],
        }
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, (json.dumps(metadata, ensure_ascii=False) + "\n").encode("utf-8"))
        os.fsync(fd)
        try:
            yield RunLease(run_dir=resolved, operation=operation, owner=metadata["owner"], acquired_at=acquired_at)
        finally:
            # Clear the diagnostics payload before releasing so a leftover file
            # never describes an active holder.
            os.ftruncate(fd, 0)
            os.fsync(fd)
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        if fd is not None:
            os.close(fd)
        with _PROCESS_LOCKS_GUARD:
            remaining = _PROCESS_LEASE_DEPTH.get(key, 1) - 1
            if remaining <= 0:
                _PROCESS_LEASE_DEPTH.pop(key, None)
                _PROCESS_LEASE_OWNER.pop(key, None)
            else:
                _PROCESS_LEASE_DEPTH[key] = remaining


def write_lease_snapshot(run_dir: Path, snapshot: dict[str, Any]) -> None:
    """Persist a diagnostic snapshot into the lease file (holder-only helper)."""
    write_json(lease_path(Path(run_dir).resolve()), snapshot)
