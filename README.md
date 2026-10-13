# Research Copilot

**面向真实科研项目的自主实验探索与决策系统**：从真实科研数据与材料出发，发现问题、生成带证据的科学发现、管理竞争性假设、规划可证伪的下一步实验——以「可被客观验证的科研能力」为唯一目标。

这是一个**独立项目**，与旧仓库 `research`（科研流水线自动化原型）互不依赖：本仓库核心零第三方依赖，不 import 旧包；旧系统仅通过只读适配器（`integrations/legacy_research.py`）导入历史 run 产物。

**当前能力边界（2026-10-13）**：已实现材料诊断、证据检查、竞争假设和实验候选规划；
候选实验尚不执行，也尚未证明提高科研分析得分。历史评测的口径修正见
[`docs/reanalysis/20261013/local-runs/index.json`](docs/reanalysis/20261013/local-runs/index.json)，
本轮修复与验证见 [`docs/repair-20261013.md`](docs/repair-20261013.md)。

## 核心理念

1. **科研过程完成 ≠ 科研获得进展。** 系统的产出不是"格式正确的报告"，而是：识别证据缺口 → 提出可验证假设 → 规划能区分竞争解释的实验 → 根据新证据更新研究状态。
2. **证据约束高于生成能力。** LLM 产出的每条发现必须通过三层校验：
   - **L1 引用有效性**：引用的证据存在、材料可访问且哈希一致；
   - **L2 数值一致性**：可程序验证的结论（数值/方向/统计表述）一律由确定性代码复核，不用另一个 LLM 判断；
   - **L3 解释有效性**：因果/机制主张自动降级为假设，除非存在受控实验证据。
   - `lookup` 必须绑定精确字段路径 `value_path`；不可验证、缺结构化依据或缺有效显著性依据
     的主张进入人工审核。已证实结果只显示确定性观测或通过检查的结构化事实生成的陈述，
     原始自由文本保存在 `validation.draft_statement`，不自动认证其中的解释。
3. **主张五级分类**：Observation / Statistical Finding / Hypothesis / Causal Claim / Unverified Conjecture，只有前两级可升级为已证实结果，且必须注明适用条件。
4. **每新增一个核心 Agent，必须配套一项对照实验**证明其改善科研任务表现；没有改善就回退该模块，不堆功能。
5. **两层能力区分**：科研分析能力（DiscoveryBench 验证）≠ 科研推进能力（Science-Gym / ResearchGym 验证，最终目标）。禁止把 benchmark 分数当唯一优化目标刷分。

## 阶段路线（详见 docs/roadmap.md）

| 阶段 | 内容 | 客观验证 |
|---|---|---|
| P0 | 独立仓库、核心数据模型、凭据安全（env-only） | 单元/安全测试 |
| P1-A | 科研诊断闭环（导入→观测→发现→假设→校验→待研究问题） | DiscoveryBench A/B/C 对照 + 8 个对抗场景 |
| P1-B | 竞争假设管理 + 主动实验规划（六维透明评分，不执行） | 合成反例 + 人工评估 |
| P2 | 实验环境交互与真实实验迭代 | Science-Gym / ResearchGym |
| P3 | 完整科研流程 | AstaBench E2E |

## 快速开始

```bash
pip install -e ".[dev]"

# 凭据只走环境变量，永不落盘
export RESEARCH_COPILOT_LLM_BASE_URL="http://your-endpoint:8080/v1"
export RESEARCH_COPILOT_LLM_MODEL="your-model"
export RESEARCH_COPILOT_LLM_API_KEY="sk-..."   # 仅进程环境；无 LLM 时系统以离线统计模式运行

research-copilot project create --name "PACO 多机械臂规划" --goal "识别规划长尾来源"
research-copilot material import --project <id> --kind results --path experiments/results.csv
research-copilot diagnose  --project <id>          # 无 LLM 时输出纯统计观察（明确标注）
research-copilot hypothesize --project <id>        # 竞争假设
research-copilot plan-experiment --project <id>    # 实验候选（不执行）
research-copilot state --project <id>              # 研究状态报告
```

离线验收与历史重算（不会调用模型）：

```bash
PYTHONPATH=src python -m pytest -q --junitxml=test-results/junit.xml
python scripts/write_test_evidence.py --junit test-results/junit.xml
PYTHONPATH=src python scripts/reanalyze_archived_runs.py --source eval-runs --out docs/reanalysis/latest
```

沙箱执行依赖 Linux `bwrap`（Ubuntu/Debian 包名 `bubblewrap`）；仅检测到可执行文件并不足以
证明命名空间可用。不可用时默认拒绝模型代码执行，集成测试明确跳过。要求隔离集成必须
实际通过时设置 `RC_REQUIRE_SANDBOX=1`；显式开发降级不构成正式评测证据。
工具工作目录按任务保留，跨步输出文件在 `close()` 前可复用，任务结束清理。

离线说明：没有 LLM 时，诊断仅输出确定性统计观察与规则式待研究问题，并明确标注 `offline`；LLM 生成的发现未通过证据校验会被降级为 `unverified_conjecture`，不会被写成研究发现。

## 安全约定

- API Key 只经环境变量传入进程，任何代码路径不得把凭据写入项目目录或数据目录。
- `data/`、`eval-runs/`、benchmark 数据本体默认 gitignore。
- 历史遗留问题（旧仓库 run-config 明文密钥）见 `docs/security-advisory.md`。

## 许可

Apache-2.0
