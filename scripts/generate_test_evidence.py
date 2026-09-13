#!/usr/bin/env python3
"""从 pytest 输出生成 docs/test-evidence.json（T20）。

用法：
  python3 scripts/generate_test_evidence.py --from-log <pytest 日志文件>
  python3 scripts/generate_test_evidence.py --summary "1435 passed, 1 skipped, 120 subtests passed in 291.32s"

README 与投递材料只引用本文件中带日期的记录，不手写数字（T20）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SUMMARY_PATTERN = re.compile(
    r"(?P<failed>\d+)? failed.*?(?P<passed>\d+) passed(?:, (?P<skipped>\d+) skipped)?(?:, (?P<subtests>\d+) subtests passed)?(?: in (?P<duration>[\d.]+)s)?"
)
SIMPLE_PATTERN = re.compile(r"(?P<passed>\d+) passed(?:, (?P<skipped>\d+) skipped)?(?:, (?P<subtests>\d+) subtests passed)?")


def parse_summary_line(line: str) -> dict | None:
    match = SIMPLE_PATTERN.search(line) or SUMMARY_PATTERN.search(line)
    if not match:
        return None
    groups = match.groupdict()
    if not groups.get("passed"):
        return None
    return {
        "passed": int(groups["passed"]),
        "failed": int(groups.get("failed") or 0) if "failed" in line and groups.get("failed") else 0,
        "skipped": int(groups.get("skipped") or 0),
        "subtests": int(groups.get("subtests") or 0),
        "duration_seconds": float(groups["duration"]) if groups.get("duration") else None,
    }


def find_summary_line(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        if " passed" in line and (" skipped" in line or " failed" in line or " subtests" in line or line.strip().endswith("passed")):
            return line
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-log", type=Path, help="pytest 日志文件")
    parser.add_argument("--summary", type=str, help="直接传入 pytest 汇总行")
    parser.add_argument("--command", default="bash scripts/run_tests.sh")
    parser.add_argument("--out", type=Path, default=Path("docs/test-evidence.json"))
    args = parser.parse_args()

    if args.summary:
        line = args.summary
    elif args.from_log:
        line = find_summary_line(args.from_log.read_text(encoding="utf-8", errors="replace"))
    else:
        proc = subprocess.run(args.command, shell=True, capture_output=True, text=True)
        combined = proc.stdout + proc.stderr
        line = find_summary_line(combined)
        if line is None:
            print("错误：无法从测试输出解析汇总行", file=sys.stderr)
            print(combined[-2000:], file=sys.stderr)
            return 1
    if line is None:
        print("错误：未找到 pytest 汇总行", file=sys.stderr)
        return 1
    parsed = parse_summary_line(line)
    if not parsed:
        print(f"错误：无法解析汇总行：{line}", file=sys.stderr)
        return 1
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": args.command,
        "summary_line": line.strip(),
        **parsed,
        "excluded_tests": [],
        "note": "完整套件，未排除 tests/test_cli.py；数字由 pytest 实际输出解析，不手写。",
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写入 {args.out}: {payload['summary_line']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
