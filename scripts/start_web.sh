#!/usr/bin/env bash
set -euo pipefail
systemctl --user start research-agent-fixed.service
echo "Research Agent (Fixed) Web Server started: http://127.0.0.1:8766"
