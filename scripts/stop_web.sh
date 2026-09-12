#!/usr/bin/env bash
set -euo pipefail
systemctl --user stop research-agent-fixed.service
echo "Research Agent (Fixed) Web Server stopped."
