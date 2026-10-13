"""从实际 JUnit 结果生成证据，绑定被测源文件指纹（不修改或提交 Git 分支）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def source_digest(root: Path) -> str:
    files = [p for folder in ("src", "tests", "scripts") for p in (root / folder).rglob("*.py")]
    files += [root / "pyproject.toml", root / ".github/workflows/copilot-ci.yml"]
    digest = hashlib.sha256()
    for path in sorted(files):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def build_evidence(junit: Path, root: Path) -> dict:
    tree = ET.parse(junit).getroot()
    cases = list(tree.iter("testcase"))
    failures = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unavailable", None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": os.environ.get("GITHUB_SHA", commit),
        "working_tree_dirty": dirty, "source_sha256": source_digest(root),
        "python": platform.python_version(), "ci": os.environ.get("CI") == "true",
        "runner": "pytest (offline; actual sandbox integration when available)",
        "totals": {"tests": len(cases), "passed": len(cases) - failures - errors - skipped,
                   "failed": failures, "errors": errors, "skipped": skipped},
        "skips": [{"name": case.get("name"), "reason": case.find("skipped").get("message", "")}
                  for case in cases if case.find("skipped") is not None],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/test-evidence.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = build_evidence(args.junit, root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence["totals"]))


if __name__ == "__main__":
    main()
