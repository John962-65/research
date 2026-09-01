#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

HOST="${RESEARCH_AGENT_WEB_HOST:-127.0.0.1}"
PORT="${RESEARCH_AGENT_WEB_PORT:-8766}"
TOPIC="${RESEARCH_AGENT_GOLD_TOPIC:-Iris classification benchmark smoke}"
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

existing_web_pids() {
  local pid cmd process_cwd
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    cmd="$(ps -o args= -p "$pid" 2>/dev/null || true)"
    process_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [[ "$process_cwd" == "$ROOT_DIR" ]] || continue
    [[ " $cmd " == *" -m research_agent.web_server "* ]] || continue
    if [[ " $cmd " == *" --port $PORT "* || " $cmd " == *" --port=$PORT "* || ( "$PORT" == "8766" && " $cmd " != *" --port "* && " $cmd " != *" --port="* ) ]]; then
      printf '%s\n' "$pid"
    fi
  done < <(pgrep -f "[r]esearch_agent\.web_server" 2>/dev/null || true)
}

ensure_web_port_available() {
  local pids reply
  mapfile -t pids < <(existing_web_pids)
  if ((${#pids[@]})); then
    printf 'Existing research_agent.web_server on port %s: %s\n' "$PORT" "${pids[*]}" >&2
    if [[ "${RESEARCH_AGENT_WEB_REPLACE:-}" == "1" ]]; then
      kill "${pids[@]}"
    else
      if [[ ! -t 0 ]]; then
        printf 'Cannot confirm replacement without an interactive terminal. Set RESEARCH_AGENT_WEB_REPLACE=1 after verifying the listed process.\n' >&2
        exit 2
      fi
      if ! read -rp "Stop and replace it now? [y/N] " reply; then
        printf '\nReplacement confirmation was not received; existing Web service was left running.\n' >&2
        exit 2
      fi
      if [[ ! "$reply" =~ ^[Yy]$ ]]; then
        printf 'Aborted before reading OPENAI_API_KEY. Stop the old server or set RESEARCH_AGENT_WEB_REPLACE=1.\n' >&2
        exit 2
      fi
      kill "${pids[@]}"
    fi
    sleep 0.5
  fi
  "$PYTHON_BIN" - "$HOST" "$PORT" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind((host, port))
    except OSError:
        print(f"Port {host}:{port} is still in use; aborting before reading OPENAI_API_KEY.", file=sys.stderr)
        sys.exit(2)
PY
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

host_is_loopback() {
  "$PYTHON_BIN" - "$HOST" <<'PY'
import ipaddress
import socket
import sys

host = sys.argv[1].strip().strip("[]")
if host.lower() == "localhost":
    raise SystemExit(0)
try:
    addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
except OSError:
    raise SystemExit(1)
raise SystemExit(0 if addresses and all(ipaddress.ip_address(item).is_loopback for item in addresses) else 1)
PY
}

ensure_web_auth() {
  local value="${RESEARCH_AGENT_WEB_TOKEN:-}"
  if host_is_loopback; then
    return 0
  fi
  if [[ -z "$value" && ! -t 0 ]]; then
    printf 'RESEARCH_AGENT_WEB_TOKEN is required when RESEARCH_AGENT_WEB_HOST is not loopback.\n' >&2
    printf 'Set a strong token before exposing the Web UI to a LAN address.\n' >&2
    exit 2
  fi
  while [[ -z "$value" ]]; do
    if ! read -rsp "RESEARCH_AGENT_WEB_TOKEN: " value; then
      printf '\nRESEARCH_AGENT_WEB_TOKEN input was not received.\n' >&2
      exit 2
    fi
    printf '\n'
    if [[ -z "$value" ]]; then
      printf 'RESEARCH_AGENT_WEB_TOKEN is required for non-loopback hosts.\n' >&2
    fi
  done
  if ((${#value} < 16)); then
    printf 'RESEARCH_AGENT_WEB_TOKEN must contain at least 16 characters.\n' >&2
    exit 2
  fi
  export RESEARCH_AGENT_WEB_TOKEN="$value"
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

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:8317}"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.5}"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

ensure_web_auth
ensure_web_port_available
ensure_llm_gateway_reachable
prompt_required_contact_email RESEARCH_AGENT_CONTACT_EMAIL

status "Running read-only Gold Defaults Smoke..."
"$PYTHON_BIN" -m research_agent gold-defaults-smoke --topic "$TOPIC"

prompt_required_secret OPENAI_API_KEY

status "Running Gold Doctor with LLM ping; this may take a few seconds..."
"$PYTHON_BIN" -m research_agent gold-run-doctor --topic "$TOPIC" --gold-defaults --ping-llm --llm-timeout-seconds "$LLM_TIMEOUT_SECONDS" --no-write
status "Running Gold Launch Bundle; online literature probe can take 30-60 seconds..."
"$PYTHON_BIN" -m research_agent gold-launch-bundle --topic "$TOPIC" --gold-defaults --no-write

status "Starting Research Agent Web UI in the foreground at http://$HOST:$PORT"
status "Keep this terminal open; press Ctrl-C to stop the Web server."
exec "$PYTHON_BIN" -m research_agent.web_server --host "$HOST" --port "$PORT"
