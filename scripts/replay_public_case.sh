#!/usr/bin/env bash
# 一键重放公开真实闭环案例（离线、CPU、无需任何凭据/在线服务）。
# 生成 runs/public-iris-case-replay 并与 runs/public-iris-case 比对关键数值（A20）。
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${RESEARCH_AGENT_PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN=python3
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

CASE_DIR="${1:-$ROOT_DIR/runs/public-iris-case-replay}"
BENCH="$ROOT_DIR/benchmarks/uci-iris-classification"

echo "== 1/4 重放公开案例（含一次真实中断 + 原地恢复） =="
if [ -d "$CASE_DIR" ]; then
  echo "目录已存在：$CASE_DIR（如需全新重放请先删除）"
else
  # 1a. 启动后在约 0.6s 处 SIGINT 中断（真实中断，与公开案例同一方式）
  "$PYTHON_BIN" -m research_agent.cli benchmark-pack-run \
    --topic "UCI Iris 最近质心候选 vs knn3 基线（公开案例重放）" \
    --benchmark-manifest "$BENCH/manifest-candidate.json" \
    --benchmark-manifest "$BENCH/manifest-baseline.json" \
    --benchmark-manifest "$BENCH/manifest-ablation.json" \
    --execution-repeats 3 --out "$CASE_DIR" > /tmp/replay-int.log 2>&1 &
  pid=$!
  sleep 0.6
  kill -INT "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  echo "已注入真实中断（进度见 /tmp/replay-int.log 与尝试账本）"
  # 1b. 原地恢复：尝试账本保留中断前记录，重跑并完成
  "$PYTHON_BIN" -m research_agent.cli benchmark-pack-run \
    --topic "UCI Iris 最近质心候选 vs knn3 基线（公开案例重放）" \
    --benchmark-manifest "$BENCH/manifest-candidate.json" \
    --benchmark-manifest "$BENCH/manifest-baseline.json" \
    --benchmark-manifest "$BENCH/manifest-ablation.json" \
    --execution-repeats 3 --out "$CASE_DIR" --resume > /tmp/replay-resume.log 2>&1
  echo "恢复完成：$(cat "$CASE_DIR/state.json" | tr -d '\n')"
fi

echo
echo "== 2/4 比对关键数值（冻结划分下的主要结果） =="
"$PYTHON_BIN" - "$ROOT_DIR/runs/public-iris-case" "$CASE_DIR" <<'PY'
import json, sys
def metrics(path):
    rows = json.load(open(path + "/04-results.json"))
    first = [r for r in rows if r["status"] == "passed"]
    base = {}
    for name in ("accuracy", "macro_f1", "error_rate"):
        base[name] = round(next(r["metrics"][name] for r in first if r["name"].endswith("candidate")), 6)
    base["passed_rows"] = len(first)
    base["attempts"] = len(json.load(open(path + "/04-experiment-attempts.json"))["attempts"])
    return base
a, b = metrics(sys.argv[1]), metrics(sys.argv[2])
for key in sorted(a):
    mark = "OK " if a[key] == b[key] else "DIFF"
    print(f"[{mark}] {key}: case={a[key]} replay={b[key]}")
if any(a[k] != b[k] for k in a if k != "attempts"):
    raise SystemExit("关键数值不一致：请检查环境与数据完整性")
print("关键结果数值一致（尝试总数允许因中断时点不同而不同）。")
PY

echo
echo "== 3/4 复算主要数值（直接运行冻结 grader） =="
"$PYTHON_BIN" "$BENCH/grade_iris.py" --method nearest_centroid --data "$BENCH/data/iris.data" \
  --split "$BENCH/split/iris-stratified-test-v1.json" --metrics /tmp/replay-check-metrics.json
"$PYTHON_BIN" -c "import json; m=json.load(open('/tmp/replay-check-metrics.json')); print('grader accuracy =', m['accuracy']); assert abs(m['accuracy']-0.966667)<1e-6"

echo
echo "== 4/4 故障注入演示（受控、独立副本；预期被阻断） =="
"$PYTHON_BIN" "$ROOT_DIR/scripts/fault_injection_demo.py" || true

echo
echo "重放完成。公开证据包：$ROOT_DIR/runs/public-iris-case（CASE-REPORT.md）"
echo "依赖在线模型的步骤在本重放中保持 not_verified（无 LLM 调用，属预期）。"
