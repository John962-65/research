"""第三轮修复验证：regress 布尔编码 + bwrap 容器沙箱。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from research_copilot.analysis.statistics import regress
from research_copilot.evaluation.sandbox import ToolSandbox, build_bwrap_command

from tests.conftest import write_csv


def test_regress_accepts_boolean_strings(tmp_path: Path):
    """修复验证：BA 列为 'True'/'False' 字符串时回归可解（上轮 unverifiable 缺陷）。"""
    rows = []
    for i in range(200):
        ses = float(i % 50) / 10
        ba = "True" if (ses + (i % 3) * 0.1) > 2.5 else "False"
        rows.append({"SES": str(ses), "BA DEGREE COMPLETED": ba})
    result = regress(rows, "BA DEGREE COMPLETED", ["SES"])
    assert result is not None
    assert result["betas"]["SES"] > 0, "构造的正向关系必须可复算"
    assert result["n"] == 200


def test_regress_filters_and_missing_values(tmp_path: Path):
    rows = [
        {"g": "A", "x": 1.0, "y": 2.0},
        {"g": "A", "x": 2.0, "y": 4.0},
        {"g": "A", "x": 3.0, "y": 6.0},
        {"g": "B", "x": 1.0, "y": 9.0},
        {"g": "B", "x": "", "y": 5.0},  # 缺失值行应被跳过
    ]
    result = regress(rows, "y", ["x"], filters={"g": "A"})
    assert result is not None and abs(result["betas"]["x"] - 2.0) < 1e-9 and result["n"] == 3
    # B 组有效样本 1 < 参数 2 → 正确返回 None（样本不足）
    assert regress(rows, "y", ["x"], filters={"g": "B"}) is None


def test_bwrap_blocks_host_file_read(tmp_path: Path):
    """容器级隔离实测：绑定集之外的宿主文件不可读（bwrap 可用时）。"""
    if not shutil.which("bwrap"):
        pytest.skip("bwrap 不可用")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")  # tmp_path 不在绑定集
    sandbox = ToolSandbox(tmp_path / "data", timeout_s=60)
    outcome = sandbox.run_python(f"print(open({str(secret)!r}).read())")
    assert not outcome["ok"], "越权读取必须失败"
    assert "TOP-SECRET" not in outcome["stdout"]


def test_bwrap_data_readonly_output_writable(tmp_path: Path):
    """v3 语义：数据只读（写同名被拒）+ 输出可写 + 隔离记录。"""
    if not shutil.which("bwrap"):
        pytest.skip("bwrap 不可用")
    (tmp_path / "data").mkdir()
    write_csv(tmp_path / "data" / "d.csv", [{"x": 1}])
    sandbox = ToolSandbox(tmp_path / "data", timeout_s=60)
    ro = sandbox.run_python("open('d.csv','w').write('x')")
    assert not ro["ok"], "写数据文件必须被只读绑定拒绝"
    rw = sandbox.run_python("open('out_result.txt','w').write('x'); print('written')")
    assert rw["ok"] and "written" in rw["stdout"]
    record = sandbox.isolation_record
    assert record["fs_isolated"] is True and record["data_readonly"] is True
    assert record["network_isolated"] is True


def test_build_bwrap_command_data_files_readonly(tmp_path: Path):
    if not shutil.which("bwrap"):
        pytest.skip("bwrap 不可用")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "d.csv").write_text("x\n", encoding="utf-8")
    command = build_bwrap_command(tmp_path / "s.py", [(tmp_path / "data" / "d.csv", "d.csv")], tmp_path)
    assert command is not None
    assert "--ro-bind" in command and "d.csv" in " ".join(command), "数据文件必须以 ro-bind 进入 cwd"
