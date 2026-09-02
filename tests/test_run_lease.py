from __future__ import annotations

from pathlib import Path
from subprocess import Popen
from tempfile import TemporaryDirectory
import json
import sys
import time
import unittest

from research_agent.run_lease import (
    RunLeaseConflict,
    acquire_run_lease,
    lease_path,
    read_lease_holder,
)

LEASE_HOLDER_SCRIPT = """
import json, sys, time
from pathlib import Path
sys.path.insert(0, {src!r})
from research_agent.run_lease import acquire_run_lease
with acquire_run_lease(Path(sys.argv[1]), "long-operation", owner="other-process"):
    print("held", flush=True)
    time.sleep(6)
"""


class RunLeaseTest(unittest.TestCase):
    def test_cross_process_conflict_then_success_after_release(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            src = str(Path(__file__).resolve().parents[1] / "src")
            proc = Popen([sys.executable, "-c", LEASE_HOLDER_SCRIPT.format(src=src), str(run_dir)])
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    holder = read_lease_holder(run_dir)
                    if holder.get("owner") == "other-process":
                        break
                    time.sleep(0.05)
                else:
                    self.fail("subprocess never acquired the lease")

                with self.assertRaises(RunLeaseConflict) as caught:
                    with acquire_run_lease(run_dir, "rollback", owner="main"):
                        pass
                self.assertIn("other-process", str(caught.exception))
                self.assertEqual(caught.exception.holder.get("operation"), "long-operation")
            finally:
                proc.wait(timeout=15)

            with acquire_run_lease(run_dir, "rollback", owner="main"):
                holder = read_lease_holder(run_dir)
                self.assertEqual(holder.get("owner"), "main")
                self.assertEqual(holder.get("operation"), "rollback")
            # Released: metadata cleared.
            self.assertEqual(read_lease_holder(run_dir), {})

    def test_reentrant_within_same_process(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            with acquire_run_lease(run_dir, "outer", owner="same"):
                with acquire_run_lease(run_dir, "inner", owner="same"):
                    holder = read_lease_holder(run_dir)
                    self.assertEqual(holder.get("operation"), "outer")
                self.assertEqual(read_lease_holder(run_dir).get("operation"), "outer")
            self.assertEqual(read_lease_holder(run_dir), {})

    def test_lease_file_written_and_cleared(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            with acquire_run_lease(run_dir, "op"):
                payload = json.loads(lease_path(run_dir).read_text(encoding="utf-8"))
                self.assertEqual(payload["operation"], "op")
                self.assertEqual(payload["pid"], __import__("os").getpid())
            self.assertFalse(lease_path(run_dir).exists() and lease_path(run_dir).stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
