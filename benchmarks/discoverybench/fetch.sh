#!/usr/bin/env bash
# 获取 DiscoveryBench 官方数据（allenai/discoverybench）。
# 数据本体不入库（.gitignore 已排除 discoverybench/discoverybench/）。
set -euo pipefail
cd "$(dirname "$0")"

if [ -d discoverybench/.git ]; then
  echo "已存在：$(pwd)/discoverybench"
  exit 0
fi

echo "浅克隆 allenai/discoverybench（仅元数据与数据集，可能较大）…"
git clone --depth 1 https://github.com/allenai/discoverybench.git
echo "完成。运行评测："
echo "  research-copilot evaluate --bench-root $(pwd)/discoverybench --subset main --limit 20"
