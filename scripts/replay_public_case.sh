#!/usr/bin/env bash
# 一键重放公开真实闭环案例（离线、CPU、无需任何凭据/在线服务）。
# 干净检出即可运行：与入库的 docs/public-case/EXPECTED-RESULTS.json 比对，
# 不依赖 gitignore 的原始 runs/ 目录（复审第 6 项）。
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${RESEARCH_AGENT_PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN=python3
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

CASE_DIR="${1:-$ROOT_DIR/runs/public-iris-case-replay}"
BENCH="$ROOT_DIR/benchmarks/uci-iris-classification"
EXPECTED="$ROOT_DIR/docs/public-case/EXPECTED-RESULTS.json"

echo "== 1/5 重放公开案例（含一次真实中断 + 原地恢复） =="
if [ -f "$CASE_DIR/04-results.json" ] && [ -f "$CASE_DIR/04-experiment-decision.json" ]; then
  echo "目录已存在且已完成：$CASE_DIR（如需全新重放请先删除）"
else
  rm -rf "$CASE_DIR"
  # 中断注入：轮询尝试账本出现真实执行记录后立即 SIGINT（复审第 6 项：
  # 中断必须被验证生效，而不是打印一句"已中断"）。
  rm -rf "$CASE_DIR"
  "$PYTHON_BIN" -m research_agent.cli benchmark-pack-run \
    --topic "UCI Iris 最近质心候选 vs knn3 基线（公开案例重放）" \
    --benchmark-manifest "$BENCH/manifest-candidate.json" \
    --benchmark-manifest "$BENCH/manifest-baseline.json" \
    --benchmark-manifest "$BENCH/manifest-ablation.json" \
    --execution-repeats 3 --out "$CASE_DIR" > /tmp/replay-int.log 2>&1 &
  pid=$!
  interrupted=0
  for _ in $(seq 1 400); do
    if ! kill -0 "$pid" 2>/dev/null; then
      break  # 进程已自行结束（环境过慢/过快），稍后由结果存在性判定
    fi
    if [ -f "$CASE_DIR/04-experiment-attempts.json" ] && \
       [ ! -f "$CASE_DIR/04-results.json" ] && \
       "$PYTHON_BIN" -c "
import json,sys
d=json.load(open('$CASE_DIR/04-experiment-attempts.json'))
sys.exit(0 if len(d.get('attempts') or []) >= 1 else 1)
" 2>/dev/null; then
      # 崩溃式中断（与 A13"即刻崩溃或任务重启"同型）：检测到真实执行记录后
      # 强制终止父进程；尝试账本保留中断现场，恢复入口负责核对与标记。
      kill -STOP "$pid" 2>/dev/null || true
      kill -KILL "$pid" 2>/dev/null || true
      interrupted=1
      break
    fi
    sleep 0.02
  done
  wait "$pid" 2>/dev/null || true
  # 验证中断确实生效：结果文件必须不存在且尝试账本非空。
  if [ "$interrupted" = "1" ] && [ ! -f "$CASE_DIR/04-results.json" ] && \
     [ -f "$CASE_DIR/04-experiment-attempts.json" ]; then
    echo "已注入并验证真实中断（进度与尝试记录见 $CASE_DIR/04-experiment-attempts.json）"
  else
    rm -rf "$CASE_DIR"
    echo "错误：未能产生真实中断现场（中断标记=$interrupted）"
    exit 1
  fi
  # 等待被中断 run 的残留子进程清场（T06 活任务守卫要求：恢复前无活任务）。
  "$PYTHON_BIN" - "$CASE_DIR" <<'PY2'
import sys, time
sys.path.insert(0, "src")
from pathlib import Path
from research_agent import experiment_attempts
deadline = time.time() + 30
while time.time() < deadline:
    live = experiment_attempts.find_live_attempt(Path(sys.argv[1]))
    if live is None:
        print("无活任务（中断尝试将由恢复入口标记为 interrupted）")
        break
    time.sleep(0.2)
else:
    print("错误：中断尝试的进程仍存活，无法安全恢复")
    sys.exit(1)
PY2
  # 原地恢复：尝试账本保留中断前记录，重跑并完成
  "$PYTHON_BIN" -m research_agent.cli benchmark-pack-run \
    --topic "UCI Iris 最近质心候选 vs knn3 基线（公开案例重放）" \
    --benchmark-manifest "$BENCH/manifest-candidate.json" \
    --benchmark-manifest "$BENCH/manifest-baseline.json" \
    --benchmark-manifest "$BENCH/manifest-ablation.json" \
    --execution-repeats 3 --out "$CASE_DIR" --resume > /tmp/replay-resume.log 2>&1
  echo "恢复完成：$(cat "$CASE_DIR/state.json" | tr -d '\n')"
fi

echo
echo "== 2/5 生成评审工件（契约/证据/决策/假设结论） =="
"$PYTHON_BIN" "$ROOT_DIR/scripts/finalize_public_case.py" "$CASE_DIR"

echo
echo "== 3/5 比对关键数值（与入库期望值 docs/public-case/EXPECTED-RESULTS.json） =="
"$PYTHON_BIN" - "$CASE_DIR" "$EXPECTED" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1] + "/04-results.json"))
passed = [r for r in rows if r["status"] == "passed"]
cand = next(r for r in passed if r["name"].endswith("candidate"))
actual = {
    "accuracy": cand["metrics"]["accuracy"],
    "macro_f1": cand["metrics"]["macro_f1"],
    "error_rate": cand["metrics"]["error_rate"],
    "passed_rows": len(passed),
}
expected = json.load(open(sys.argv[2]))
for key, want in expected.items():
    got = actual[key]
    ok = abs(got - want) < 1e-9 if isinstance(want, float) else got == want
    print(f"[{'OK ' if ok else 'DIFF'}] {key}: expected={want} replay={got}")
    if not ok:
        raise SystemExit(f"关键数值不一致：{key}")
print("与入库期望值一致。")
PY

echo
echo "== 4/5 复算主要数值（直接运行冻结 grader）并核对决策工件 =="
"$PYTHON_BIN" "$BENCH/grade_iris.py" --method nearest_centroid --data "$BENCH/data/iris.data" \
  --split "$BENCH/split/iris-stratified-test-v1.json" --metrics /tmp/replay-check-metrics.json
"$PYTHON_BIN" - "$CASE_DIR" <<'PY'
import json, sys
m = json.load(open("/tmp/replay-check-metrics.json"))
print("grader accuracy =", m["accuracy"])
assert abs(m["accuracy"] - 0.966667) < 1e-6, "grader 复算与冻结划分不符"
decision = json.load(open(sys.argv[1] + "/04-experiment-decision.json"))
states = decision["decision_states"]
assert decision["primary_metrics"], "决策必须绑定契约主指标"
assert states["execution_status"] == "completed"
assert states["research_outcome"] in {"not_supported", "inconclusive"}, "中性/负结果不得判 supported"
assert states["stop_after_report"] is True
integrity = json.load(open(sys.argv[1] + "/04-evidence-integrity.json"))
assert integrity["experiment_evidence_status"] == "verified"
assert integrity["llm_evidence_status"] == "unknown", "本案例无模型调用，必须如实记录"
contract = json.load(open(sys.argv[1] + "/03-idea-experiment-contract.json"))
assert contract["contract_digest"] == contract["contract"]["digest"]
attempts = json.load(open(sys.argv[1] + "/04-experiment-attempts.json"))["attempts"]
assert len(attempts) > 9, "中断恢复后的尝试总数应多于一次完整执行（9）"
print(f"决策工件核验通过：research_outcome={states['research_outcome']}，尝试总数={len(attempts)}（含中断保留）")
PY

echo
echo "== 5/5 故障注入演示（受控、独立副本；断言具体审计原因） =="
"$PYTHON_BIN" "$ROOT_DIR/scripts/fault_injection_demo.py"

echo
echo "重放完成。公开证据包：$ROOT_DIR/runs/public-iris-case（干净检出重放目录：$CASE_DIR）"
echo "依赖在线模型的步骤在本重放中保持 not_verified（无 LLM 调用，属预期）。"
