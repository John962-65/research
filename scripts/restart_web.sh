#!/usr/bin/env bash
set -euo pipefail
systemctl --user restart research-agent-fixed.service
echo "Research Agent (Fixed) Web Server restarted: http://127.0.0.1:8766"
