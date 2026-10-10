"""沙箱隔离测试：环境变量清洗、资源限额、隔离记录诚实标注。"""
from __future__ import annotations

from pathlib import Path

from research_copilot.evaluation.sandbox import ToolSandbox, build_clean_env, check_network_isolation_available


def test_env_scrubbed_no_secrets():
    import os

    os.environ["RESEARCH_COPILOT_LLM_API_KEY"] = "sk-test-secret-value"
    os.environ["SOME_OTHER_SECRET_TOKEN"] = "secret-token"
    try:
        env = build_clean_env()
        assert "RESEARCH_COPILOT_LLM_API_KEY" not in env
        assert "SOME_OTHER_SECRET_TOKEN" not in env
        assert "PATH" in env
        assert env.get("RESEARCH_COPILOT_SANDBOXED") == "1"
    finally:
        os.environ.pop("RESEARCH_COPILOT_LLM_API_KEY", None)
        os.environ.pop("SOME_OTHER_SECRET_TOKEN", None)


def test_sandboxed_code_cannot_read_env_secrets(tmp_path: Path):
    import os

    os.environ["RESEARCH_COPILOT_LLM_API_KEY"] = "sk-test-secret-value"
    try:
        sandbox = ToolSandbox(tmp_path, timeout_s=30)
        code = (
            "import os, json\n"
            "print(json.dumps({k: (v[:6] + '...') for k, v in os.environ.items() if 'KEY' in k or 'TOKEN' in k or 'SECRET' in k}))\n"
        )
        outcome = sandbox.run_python(code)
        assert outcome["ok"], outcome["stderr"]
        assert outcome["stdout"].strip() in ("{}", "[]")
        assert "sk-tes" not in outcome["stdout"]
    finally:
        os.environ.pop("RESEARCH_COPILOT_LLM_API_KEY", None)


def test_sandbox_rlimits_block_big_memory(tmp_path: Path):
    sandbox = ToolSandbox(tmp_path, timeout_s=30, limits={"address_space_bytes": 128 * 1024 * 1024})
    outcome = sandbox.run_python("x = bytearray(512 * 1024 * 1024)\nprint('allocated')\n")
    assert not outcome["ok"], "超出地址空间限额的分配必须失败"


def test_sandbox_can_read_dataset_dir(tmp_path: Path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    sandbox = ToolSandbox(tmp_path, timeout_s=30)
    outcome = sandbox.run_python("print(open('data.csv').read().strip())")
    assert outcome["ok"] and "1,2" in outcome["stdout"]


def test_isolation_record_is_honest():
    sandbox = ToolSandbox(None, network_isolation=False)
    record = sandbox.isolation_record
    assert record["network_isolated"] is False
    assert "残余风险" in record["honesty_note"]
    sandbox2 = ToolSandbox(None, network_isolation=True)
    assert sandbox2.isolation_record["network_isolated"] is True


def test_network_probe_returns_bool():
    result = check_network_isolation_available()
    assert isinstance(result, bool)
