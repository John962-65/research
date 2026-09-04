#!/usr/bin/env bash
# CI-02: create the two gold support runs the gold-path tests require.
#
# The gold smoke/launch tests assert on
# runs/uci-iris-expanded-baseline-pack-run and runs/uci-iris-fulltext-grounding.
# Both directories are gitignored local artifacts, so a fresh clone has neither
# and those tests fail even though nothing is wrong with the code. Both runs are
# deterministic and offline: they consume only the tracked UCI Iris benchmark
# pack and its frozen fulltext, and execute the pack's graders through the
# allowlisted `python3` command.
#
# CI calls this before the suite; contributors can call it to get a green suite
# from a clean checkout.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN="${RESEARCH_AGENT_PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

PACK_DIR="runs/uci-iris-expanded-baseline-pack-run"
GROUND_DIR="runs/uci-iris-fulltext-grounding"

if [[ -f "$PACK_DIR/04-benchmark-evidence-audit.json" && -f "$GROUND_DIR/10-citation-grounding.json" ]]; then
  echo "gold support runs already present; skipping"
  exit 0
fi

echo "using python: $PYTHON_BIN"

"$PYTHON_BIN" -m research_agent benchmark-pack-run \
  --topic "UCI Iris expanded baseline pack" \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-candidate.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-baseline.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-ablation.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-majority.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-dummy-stratified.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-gaussian-nb.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-linear-logistic.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-decision-tree.json \
  --out "$PACK_DIR"

"$PYTHON_BIN" -m research_agent fulltext-grounding-run \
  --topic "UCI Iris fulltext grounding" \
  --fulltext-path benchmarks/uci-iris-classification/fulltext/iris.names.txt \
  --out "$GROUND_DIR"

echo "gold support runs ready: $PACK_DIR, $GROUND_DIR"
