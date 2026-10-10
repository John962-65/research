# 安全公告与凭据约定

## 历史事件（旧仓库 `research`，本项目不修改它）

旧仓库在提交 `009372b`（"run-config 支持保存 LLM 凭据"）中**有意**将 LLM API Key
明文写入 `runs/*/run-config.json`，并停用了"密钥落盘即阻断"的完整性审计。本地
`runs/灵巧手重定向-20260914-044523/run-config.json` 中确认存在真实明文密钥。

**该密钥必须视为已泄露。** 清洗文件或设置 0600 权限**不能**使已泄露的密钥重新安全。

### 需要人工执行的动作（代码无法替代）

1. **立即轮换（作废重发）该密钥**；
2. 排查泄露面：旧仓库 git 历史（`git log -p -- '**/run-config.json'`）、
   本地备份、共享网盘、CI 日志；
3. 若密钥曾推送到任何远端，按已公开泄露处理并检查用量账单。

本项目（research-copilot）**不会**修复旧仓库——按约定旧仓库冻结、零功能性改动。

## 本项目的凭据约定

- API Key **只经环境变量**传入进程：
  `RESEARCH_COPILOT_LLM_BASE_URL / RESEARCH_COPILOT_LLM_MODEL / RESEARCH_COPILOT_LLM_API_KEY`；
- 任何代码路径不得把凭据写入项目目录、数据目录（`data/`）或评测产物（`eval-runs/`）；
- 调用台账（`LLMCallRecord`）只记录模型名、用量、耗时，不含密钥与请求内容；
- `.gitignore` 排除 `credentials*.json`、`.env`、`data/`、`eval-runs/`；
- 关于"0600 权限的本地凭据文件"：它**仍是明文存储，不等于加密保护**。本项目默认
  不提供凭据文件机制；如未来引入，必须与系统凭据管理器（keyring）配合并明确标注其局限。

## 数据与证据完整性

- 导入材料即固定 sha256；引用（EvidenceRef）绑定内容哈希，材料更新后引用自动
  失效（stale），基于旧引用的结论升级被阻断（tests/test_adversarial_scenarios.py 场景 8）。
- `data/` 与 benchmark 数据本体默认不入 git，防止科研数据与密钥意外公开。
