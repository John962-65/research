"""CLI 端到端测试：create → import → diagnose → confirm → hypothesize → plan → state → decision → evaluate dry-run。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.cli import main

from tests.conftest import latency_rows, write_csv


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture()
def results_csv(tmp_path: Path) -> Path:
    rows = latency_rows("baseline", n_queries=120, scale=1.0, tail_ratio=0.0) + latency_rows(
        "paco", n_queries=120, scale=0.8, tail_ratio=0.05, tail_multiplier=25.0
    )
    return write_csv(tmp_path / "results.csv", rows)


def _run(args: list[str], data_dir: Path) -> int:
    return main(["--data-dir", str(data_dir)] + args)


def test_full_loop_offline(data_dir: Path, results_csv: Path, capsys):
    import re as _re

    assert _run(["project", "create", "--name", "PACO 长尾", "--goal", "识别长尾来源", "--goal", "验证协调器假设"], data_dir) == 0
    project_id = _re.search(r"已创建项目 (\S+?)（", capsys.readouterr().out).group(1)

    assert _run(["material", "import", "--project", project_id, "--kind", "results", "--path", str(results_csv), "--direction", "planning_time_s=lower_is_better", "--direction", "success_rate=higher_is_better"], data_dir) == 0
    capsys.readouterr()

    assert _run(["diagnose", "--project", project_id, "--no-llm"], data_dir) == 0
    diagnose_out = capsys.readouterr().out
    assert "离线" in diagnose_out or "offline" in diagnose_out

    assert _run(["question", "list", "--project", project_id], data_dir) == 0
    question_id = capsys.readouterr().out.split("\t")[0]
    assert question_id.startswith("Q-")

    assert _run(["question", "confirm", "--project", project_id, "--id", question_id, "--rationale", "关键缺口"], data_dir) == 0
    capsys.readouterr()

    assert _run(["hypothesis", "generate", "--project", project_id, "--no-llm"], data_dir) == 0
    hyp_out = capsys.readouterr().out
    assert "H-001" in hyp_out

    assert _run(["hypothesis", "record-evidence", "--project", project_id, "--hypothesis", "H-001", "--verdict", "supports", "--rationale", "复现支持", "--ref", "F-001"], data_dir) == 0
    assert _run(["hypothesis", "status", "--project", project_id, "--id", "H-001", "--status", "active", "--rationale", "进入验证"], data_dir) == 0
    capsys.readouterr()

    assert _run(["experiment", "plan", "--project", project_id, "--no-llm"], data_dir) == 0
    plan_out = capsys.readouterr().out
    assert "EXP-001" in plan_out
    assert "needs_revision" in plan_out or "proposed" in plan_out
    assert "启发式" in plan_out  # 必须明确标注评分性质

    # 形式检查不过的草稿不能批准
    assert _run(["experiment", "approve", "--project", project_id, "--id", "EXP-001"], data_dir) == 1

    assert _run(["state", "--project", project_id], data_dir) == 0
    state_out = capsys.readouterr().out
    assert "待研究问题" in state_out
    assert question_id in state_out

    assert _run(["decision", "record", "--project", project_id, "--action", "investigate", "--rationale", "长尾证据需分模块计时", "--evidence", "F-001"], data_dir) == 0
    assert _run(["decision", "list", "--project", project_id], data_dir) == 0
    assert "investigate" in capsys.readouterr().out


def test_error_exit_code(data_dir: Path):
    assert _run(["state", "--project", "missing-project"], data_dir) == 1


def test_evaluate_dry_run(tmp_path: Path, capsys):
    # 构造最小 bench fixture
    dataset_dir = tmp_path / "bench" / "datasets" / "task-0001"
    write_csv(dataset_dir / "data.csv", latency_rows("baseline", n_queries=40, tail_ratio=0.0))
    meta_path = tmp_path / "bench" / "metadata" / "main" / "task-0001.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps({"domain": "x", "query": "q?", "hypothesis": "h", "dataset_dir": "datasets/task-0001"}), encoding="utf-8")

    code = main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "evaluate",
            "--bench-root",
            str(tmp_path / "bench"),
            "--out-dir",
            str(tmp_path / "eval-runs"),
            "--groups",
            "A,B,C",
            "--limit",
            "1",
            "--dry-run",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "A" in out and "dry_run=True" in out
