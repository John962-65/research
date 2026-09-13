#!/usr/bin/env python3
"""文档状态漂移检查（T20）：README/案例报告/契约枚举必须与机器产物一致。

- README 不得手写测试通过数：必须引用 docs/test-evidence.json（带日期）。
- 公开案例目录（存在时）走 scripts/check_public_case_consistency.py。
- decision-contract 冻结的状态枚举必须与代码常量一致（防枚举漂移）。

任一检查失败即退出 1（CI 中阻断合并）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_agent.experiment_decision import _NEXT_ACTION_MAP  # noqa: E402


def check_readme() -> list[str]:
    problems: list[str] = []
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    evidence_path = ROOT / "docs" / "test-evidence.json"
    if not evidence_path.exists():
        return ["docs/test-evidence.json 缺失：请先运行 scripts/generate_test_evidence.py"]
    evidence = evidence_path.read_text(encoding="utf-8")
    # README 不得出现硬编码的 "N passed" 数字表述（引用 evidence 文件即可）。
    import re

    hardcoded = re.findall(r"\d{3,} passed", readme)
    if hardcoded:
        problems.append(f"README 硬编码测试数字 {hardcoded}：改为引用 docs/test-evidence.json")
    if "docs/test-evidence.json" not in readme:
        problems.append("README 未引用 docs/test-evidence.json")
    if "generated_at" not in evidence:
        problems.append("test-evidence.json 缺 generated_at（必须带日期）")
    return problems


def check_contract_enums() -> list[str]:
    problems: list[str] = []
    contract = (ROOT / "docs" / "decision-contract.md").read_text(encoding="utf-8")
    # 冻结枚举（decision-contract §1）。
    frozen_next_actions = {"proceed", "request_material", "repair", "rerun", "stop", "human_review"}
    frozen_evidence = {"verified", "incomplete", "invalid", "simulated", "unknown"}
    for value in set(_NEXT_ACTION_MAP.values()):
        if value not in frozen_next_actions:
            problems.append(f"experiment_decision next_action '{value}' 不在冻结枚举中")
    for token in frozen_next_actions:
        if token not in contract:
            problems.append(f"decision-contract 缺少 next_action 枚举 '{token}'")
    for token in frozen_evidence:
        if token not in contract:
            problems.append(f"decision-contract 缺少 evidence_status 枚举 '{token}'")
    return problems


def check_case_dirs() -> list[str]:
    from check_public_case_consistency import check_case_dir  # type: ignore

    problems: list[str] = []
    for case_dir in sorted((ROOT / "runs").glob("*-case")) if (ROOT / "runs").exists() else []:
        problems.extend(f"{case_dir.name}: {p}" for p in check_case_dir(case_dir))
    return problems


def main() -> int:
    problems = [*check_readme(), *check_contract_enums(), *check_case_dirs()]
    for problem in problems:
        print(f"[DRIFT] {problem}")
    print("文档状态漂移检查：", "PASS" if not problems else f"FAIL（{len(problems)} 项）")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
