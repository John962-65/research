#!/usr/bin/env python3
"""Verify that every relative Markdown link in README/docs resolves (Phase H)."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")


def check_file(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for match in LINK_PATTERN.finditer(text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        if not resolved.exists():
            problems.append(f"{path.relative_to(ROOT)}: broken link -> {target}")
    return problems


def main() -> int:
    files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    problems: list[str] = []
    for path in files:
        if path.is_file():
            problems.extend(check_file(path))
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"checked {len(files)} markdown files; {len(problems)} broken link(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
