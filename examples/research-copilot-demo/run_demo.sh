#!/usr/bin/env bash
# 端到端离线演示：建项目 → 导材料 → 诊断 → 确认问题 → 假设 → 实验规划 → 状态 → 决策
# 无需 LLM：全程离线统计模式（输出会明确标注）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

# 未安装包时直接用源码路径（pip install -e . 后可去掉）
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export RESEARCH_COPILOT_DATA_DIR="$SCRIPT_DIR/data"

echo "== 1. 生成示例数据 =="
python3 generate_demo_data.py

echo "== 2. 创建项目 =="
python3 -m research_copilot.cli project create --name "PACO 多机械臂规划（演示）" \
  --goal "识别规划长尾来源" --goal "界定相对强基线的优势边界"

PROJECT_ID=$(ls "$(pwd)/data/projects" | head -1)
echo "项目 ID: $PROJECT_ID"

echo "== 3. 导入实验结果（方向声明随 manifest 自动提取） =="
python3 -m research_copilot.cli material import --project "$PROJECT_ID" \
  --kind results --path "$(pwd)/results.csv"

echo "== 4. 科研诊断（离线统计模式） =="
python3 -m research_copilot.cli diagnose --project "$PROJECT_ID" --no-llm

echo "== 5. 查看并确认待研究问题 =="
python3 -m research_copilot.cli question list --project "$PROJECT_ID"
FIRST_QUESTION=$(python3 -m research_copilot.cli question list --project "$PROJECT_ID" | head -1 | cut -f1)
python3 -m research_copilot.cli question confirm --project "$PROJECT_ID" --id "$FIRST_QUESTION" \
  --rationale "演示：人工确认该证据缺口值得研究"

echo "== 6. 生成竞争假设（离线：来自发现的竞争性解释） =="
python3 -m research_copilot.cli hypothesis generate --project "$PROJECT_ID" --no-llm || true

echo "== 7. 实验候选规划（不执行；离线草稿需人工补齐） =="
python3 -m research_copilot.cli experiment plan --project "$PROJECT_ID" --no-llm || true

echo "== 8. 研究状态报告 =="
python3 -m research_copilot.cli state --project "$PROJECT_ID"

echo "== 9. 记录科研决策 =="
python3 -m research_copilot.cli decision record --project "$PROJECT_ID" \
  --action investigate --rationale "长尾来源尚未定位，先做分模块计时" || true

echo "演示完成。数据目录: $(pwd)/data（gitignore，可随时删除）"
