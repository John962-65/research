#!/usr/bin/env python3
"""受控故障注入演示（T10）：篡改冻结 split 后运行同一流水线，验证系统阻断。

该脚本生成独立副本并标记为 fault_injection；预期结果是 benchmark pack
以 status=block 结束（split_sha256 provenance 校验失败），CLI 退出码 2。
这是演示性质的受控故障注入，不是自然发生的用户错误。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_SRC = ROOT / "benchmarks" / "uci-iris-classification"
TAMPER_ROOT = ROOT / "runs" / "fault-injection-benchmarks"
TAMPERED = TAMPER_ROOT / "uci-iris-tampered"
OUT = ROOT / "runs" / "public-iris-case-fault-injection-replay"


def main() -> int:
    TAMPER_ROOT.mkdir(parents=True, exist_ok=True)
    if TAMPERED.exists():
        shutil.rmtree(TAMPERED)
    shutil.copytree(BENCH_SRC, TAMPERED)

    split_path = TAMPERED / "split" / "iris-stratified-test-v1.json"
    data = json.loads(split_path.read_text(encoding="utf-8"))
    removed = data["test_indices"][:3]
    data["test_indices"] = data["test_indices"][3:]
    data["fault_injection"] = {
        "description": "受控故障注入：测试划分被人为缩减 3 个样本",
        "removed_indices": removed,
    }
    split_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"[fault-injection] 已篡改 split：测试样本 {30}→{len(data['test_indices'])}")

    if OUT.exists():
        shutil.rmtree(OUT)
    cmd = [
        sys.executable, "-m", "research_agent.cli", "benchmark-pack-run",
        "--topic", "故障注入副本（受控）：篡改 split 后必须被阻断",
        "--benchmark-manifest", str(TAMPERED / "manifest-candidate.json"),
        "--benchmark-manifest", str(TAMPERED / "manifest-baseline.json"),
        "--benchmark-manifest", str(TAMPERED / "manifest-ablation.json"),
        "--execution-repeats", "3", "--out", str(OUT),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=None)
    schema_path = OUT / "04-benchmark-result-schema-audit.json"
    pack_path = OUT / "04-benchmark-pack-run.json"
    print(f"[fault-injection] pack 退出码：{proc.returncode}（预期非 0）")
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        print(f"[fault-injection] schema 审计状态：{schema.get('status')}（预期 block）")
        for issue in schema.get("blocking_issues", [])[:2]:
            print(f"  阻断：{issue[:160]}")
    if pack_path.exists():
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        print(f"[fault-injection] pack 状态：{pack.get('status')}（预期 block）")
    blocked = proc.returncode != 0
    print("[fault-injection] 结果：", "系统按预期阻断 ✓" if blocked else "未阻断——系统出现漏判，需要排查 ✗")
    return 0 if blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
