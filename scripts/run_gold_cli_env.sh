#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

TOPIC="${RESEARCH_AGENT_GOLD_TOPIC:-Iris classification benchmark smoke}"
OUT_DIR="${RESEARCH_AGENT_GOLD_OUT:-runs/iris-classification-benchmark-smoke-gold-run}"
DRY_RUN="${RESEARCH_AGENT_GOLD_DRY_RUN:-0}"
LLM_TIMEOUT_SECONDS="${RESEARCH_AGENT_GOLD_LLM_TIMEOUT_SECONDS:-8}"

resolve_python_bin() {
  local candidate="${RESEARCH_AGENT_PYTHON_BIN:-}"
  if [[ -z "$candidate" && -x "$ROOT_DIR/.venv/bin/python" ]]; then
    candidate="$ROOT_DIR/.venv/bin/python"
  fi
  if [[ -z "$candidate" ]]; then
    candidate="$(command -v python3 || true)"
  elif [[ "$candidate" != */* ]]; then
    candidate="$(command -v "$candidate" || true)"
  fi
  if [[ -z "$candidate" || ! -x "$candidate" ]]; then
    printf 'Python interpreter not found. Set RESEARCH_AGENT_PYTHON_BIN to Python 3.11 or newer.\n' >&2
    exit 2
  fi
  if ! "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    printf 'Research Agent requires Python 3.11 or newer; selected interpreter is %s.\n' "$candidate" >&2
    printf 'Set RESEARCH_AGENT_PYTHON_BIN or create .venv with a supported Python.\n' >&2
    exit 2
  fi
  printf '%s\n' "$candidate"
}

PYTHON_BIN="$(resolve_python_bin)"

fresh_out_hint() {
  local base="$1"
  local suffix
  local candidate
  if [[ ! -e "$base" ]]; then
    printf '%s\n' "$base"
    return 0
  fi
  for suffix in {2..99}; do
    candidate="${base}-${suffix}"
    if [[ ! -e "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  printf '%s-fresh\n' "$base"
}

prompt_required_secret() {
  local name="$1" fifo fifo_var
  local value="${!name:-}"
  fifo_var="RESEARCH_AGENT_OPENAI_API_KEY_FIFO"
  fifo="${!fifo_var:-}"
  if [[ -z "$value" && -n "$fifo" ]]; then
    read_secret_from_fifo "$name" "$fifo"
    return 0
  fi
  if [[ -z "$value" && ! -t 0 ]]; then
    printf '%s is required but stdin is not interactive.\n' "$name" >&2
    printf 'Aborted before reading %s. Export %s, set %s to a 600-permission FIFO, or run this script from an interactive terminal.\n' "$name" "$name" "$fifo_var" >&2
    exit 2
  fi
  while [[ -z "$value" ]]; do
    if ! read -rsp "$name: " value; then
      printf '\n%s input was not received.\n' "$name" >&2
      exit 2
    fi
    printf '\n'
    if [[ -z "$value" ]]; then
      printf '%s is required.\n' "$name" >&2
    fi
  done
  export "$name=$value"
}

read_secret_from_fifo() {
  local name="$1" fifo="$2" value
  if [[ ! -p "$fifo" ]]; then
    printf '%s must point to a FIFO, not a regular file: %s\n' "RESEARCH_AGENT_OPENAI_API_KEY_FIFO" "$fifo" >&2
    exit 2
  fi
  if ! fifo_group_other_private "$fifo"; then
    printf '%s FIFO must not be accessible by group/other; create it with mkfifo -m 600.\n' "RESEARCH_AGENT_OPENAI_API_KEY_FIFO" >&2
    exit 2
  fi
  printf 'Reading %s from FIFO specified by %s.\n' "$name" "RESEARCH_AGENT_OPENAI_API_KEY_FIFO" >&2
  if ! IFS= read -r value < "$fifo"; then
    printf '%s input was not received from FIFO.\n' "$name" >&2
    exit 2
  fi
  if [[ -z "$value" ]]; then
    printf '%s is required.\n' "$name" >&2
    exit 2
  fi
  export "$name=$value"
}

fifo_group_other_private() {
  local fifo="$1" perms group other
  perms="$(stat -c '%a' "$fifo" 2>/dev/null || true)"
  [[ "$perms" =~ ^[0-7]+$ ]] || return 1
  group="${perms: -2:1}"
  other="${perms: -1}"
  [[ -n "$group" && -n "$other" ]] || return 1
  (( (10#$group) == 0 && (10#$other) == 0 ))
}

status() {
  printf '%s\n' "$*" >&2
}

valid_contact_email_value() {
  "$PYTHON_BIN" - "$1" <<'PY'
import sys
sys.path.insert(0, "src")
from research_agent.credential_validation import valid_contact_email

sys.exit(0 if valid_contact_email(sys.argv[1]) else 1)
PY
}

prompt_required_contact_email() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" && ! -t 0 ]]; then
    printf '%s is required but stdin is not interactive.\n' "$name" >&2
    printf 'Aborted before reading OPENAI_API_KEY. Export %s in your shell or run this script from an interactive terminal.\n' "$name" >&2
    exit 2
  fi
  while true; do
    while [[ -z "$value" ]]; do
      if ! read -rp "$name: " value; then
        printf '\n%s input was not received.\n' "$name" >&2
        exit 2
      fi
      if [[ -z "$value" ]]; then
        printf '%s is required.\n' "$name" >&2
      fi
    done
    if valid_contact_email_value "$value"; then
      export "$name=$value"
      return 0
    fi
    printf '%s must be a real contact email; do not use example.org/example.com or placeholders.\n' "$name" >&2
    if [[ ! -t 0 ]]; then
      printf 'Aborted before reading OPENAI_API_KEY. Export a real %s before launching.\n' "$name" >&2
      exit 2
    fi
    value=""
  done
}

confirm_launch() {
  local reply
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  if [[ "${RESEARCH_AGENT_GOLD_CONFIRM:-}" == "1" ]]; then
    return 0
  fi
  printf 'Gold Bundle is ready. Start the strict gold run at %s? [y/N] ' "$OUT_DIR" >&2
  read -r reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

run_final_gold_audits() {
  local readiness_runs_dir verify_status readiness_status repair_resume_status
  readiness_runs_dir="$(dirname "$OUT_DIR")"
  printf 'Gold run finished. Re-running final verifier and perfect-readiness audit.\n' >&2
  set +e
  "$PYTHON_BIN" -m research_agent gold-run-verify --run-dir "$OUT_DIR"
  verify_status=$?
  "$PYTHON_BIN" -m research_agent perfect-readiness --project-dir . --runs-dir "$readiness_runs_dir" --out .
  readiness_status=$?
  repair_resume_status=0
  if ((verify_status != 0)) && [[ -f "$OUT_DIR/15-gold-run-verification.json" ]]; then
    "$PYTHON_BIN" -m research_agent repair-resume "$OUT_DIR" --dry-run --gold-run-verification-report "$OUT_DIR/15-gold-run-verification.json"
    repair_resume_status=$?
    if ((repair_resume_status != 0)); then
      printf 'Gold repair-resume preview could not be generated; inspect 15-gold-run-verification.json manually.\n' >&2
    fi
  fi
  set -e
  if ((verify_status != 0)); then
    return "$verify_status"
  fi
  return "$readiness_status"
}

run_gold_launch_with_final_audit() {
  local launch_status audit_status
  set +e
  "$PYTHON_BIN" -m research_agent gold-run-launch --topic "$TOPIC" --gold-defaults --out "$OUT_DIR"
  launch_status=$?
  set -e
  audit_status=0
  if [[ -d "$OUT_DIR" ]]; then
    set +e
    run_final_gold_audits
    audit_status=$?
    set -e
  fi
  if ((launch_status != 0)); then
    return "$launch_status"
  fi
  return "$audit_status"
}

ensure_llm_gateway_reachable() {
  if [[ "${RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK:-}" == "1" ]]; then
    return 0
  fi
  "$PYTHON_BIN" - "$OPENAI_BASE_URL" <<'PY'
import socket
import sys
from urllib.parse import urlparse

raw = sys.argv[1]
parsed = urlparse(raw if "://" in raw else f"http://{raw}")
host = parsed.hostname
if not host:
    print("OPENAI_BASE_URL is invalid; aborting before reading OPENAI_API_KEY.", file=sys.stderr)
    sys.exit(2)
port = parsed.port
if port is None:
    port = 443 if parsed.scheme == "https" else 80
try:
    with socket.create_connection((host, port), timeout=2.0):
        pass
except OSError as exc:
    print(f"LLM gateway {host}:{port} is not reachable before reading OPENAI_API_KEY - {exc}", file=sys.stderr)
    print("Start the local gateway or set RESEARCH_AGENT_GOLD_SKIP_GATEWAY_CHECK=1 after reviewing the risk.", file=sys.stderr)
    sys.exit(2)
PY
}

if [[ "$DRY_RUN" != "1" && -e "$OUT_DIR" ]]; then
  suggested_out="$(fresh_out_hint "$OUT_DIR")"
  printf 'Output path already exists: %s\n' "$OUT_DIR" >&2
  printf 'Aborted before reading OPENAI_API_KEY. Pick a fresh RESEARCH_AGENT_GOLD_OUT; non-dry-run gold launches never reuse an existing run directory.\n' >&2
  printf 'Suggested fresh RESEARCH_AGENT_GOLD_OUT: %s\n' "$suggested_out" >&2
  printf 'Run with: RESEARCH_AGENT_GOLD_OUT=%q scripts/run_gold_cli_env.sh\n' "$suggested_out" >&2
  exit 2
fi

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:8317}"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.5}"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

ensure_llm_gateway_reachable
prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL

status "Running read-only Gold Defaults Smoke..."
"$PYTHON_BIN" -m research_agent gold-defaults-smoke --topic "$TOPIC"

prompt_required_secret OPENAI_API_KEY

status "Running Gold Doctor with LLM ping; this may take a few seconds..."
"$PYTHON_BIN" -m research_agent gold-run-doctor --topic "$TOPIC" --gold-defaults --ping-llm --llm-timeout-seconds "$LLM_TIMEOUT_SECONDS" --no-write
status "Running Gold Launch Bundle; online literature probe can take 30-60 seconds..."
"$PYTHON_BIN" -m research_agent gold-launch-bundle --topic "$TOPIC" --gold-defaults --no-write

if [[ "$DRY_RUN" == "1" ]]; then
  status "Running dry-run gold launch validation..."
  "$PYTHON_BIN" -m research_agent gold-run-launch --topic "$TOPIC" --gold-defaults --out "$OUT_DIR" --dry-run
  exit 0
fi

if ! confirm_launch; then
  printf 'Gold run launch cancelled after read-only checks. No run was started.\n' >&2
  exit 2
fi

run_gold_launch_with_final_audit
