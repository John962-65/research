#!/usr/bin/env bash
# TEST-01: isolated test entry.
#
# The host machine may auto-load pytest plugins (e.g. ROS test tooling) that
# break collection before any project test runs. This entry point disables
# plugin autoload, pins the project venv when present, and runs the full
# suite. CI should call this script in a fresh checkout with the project's
# dev extra installed:  pip install -e '.[dev]'
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

PYTHON_BIN=""
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [[ -n "${RESEARCH_AGENT_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$RESEARCH_AGENT_PYTHON_BIN"
else
  PYTHON_BIN="$(command -v python3)"
fi

echo "using python: $PYTHON_BIN"
exec "$PYTHON_BIN" -m pytest tests/ -q "$@"
