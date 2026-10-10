"""材料导入与旧系统适配测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_copilot.core.storage import ProjectStore
from research_copilot.integrations.legacy_research import import_legacy_run, normalize_legacy_results
from research_copilot.integrations.material_importer import (
    extract_metric_directions,
    import_material,
    read_rows,
    summarize_rows,
)

from tests.conftest import latency_rows, manifest, write_csv


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "data")


def test_read_rows_csv_json_jsonl(tmp_path: Path):
    write_csv(tmp_path / "a.csv", [{"x": 1, "y": "a"}, {"x": 2, "y": "b"}])
    assert read_rows(tmp_path / "a.csv") == [{"x": 1.0, "y": "a"}, {"x": 2.0, "y": "b"}]
    (tmp_path / "b.json").write_text(json.dumps({"rows": [{"x": 3}]}), encoding="utf-8")
    assert read_rows(tmp_path / "b.json") == [{"x": 3}]
    (tmp_path / "c.jsonl").write_text('{"x": 4}\n{"x": 5}\n', encoding="utf-8")
    assert len(read_rows(tmp_path / "c.jsonl")) == 2


def test_manifest_direction_extraction(tmp_path: Path):
    manifest(tmp_path / "manifest.json", {"planning_time_s": "lower_is_better", "success_rate": "higher_is_better"})
    directions = extract_metric_directions(tmp_path / "results.csv")
    assert directions == {"planning_time_s": "lower_is_better", "success_rate": "higher_is_better"}


def test_explicit_direction_wins_over_manifest(tmp_path: Path):
    manifest(tmp_path / "manifest.json", {"m": "higher_is_better"})
    directions = extract_metric_directions(tmp_path / "results.csv", {"m": "lower_is_better"})
    assert directions == {"m": "lower_is_better"}


def test_import_material_summarizes(store: ProjectStore, tmp_path: Path):
    rows = latency_rows("paco", n_queries=30)
    data_file = write_csv(tmp_path / "results.csv", rows)
    material = import_material(store, store.create_project("导入").id, "results", data_file)
    table = material.meta["table"]
    assert table["n_rows"] == 30
    assert "planning_time_s" in table["numeric_columns"]
    assert table["query_field"] == "query_id"
    assert table["group_field"] == "comparison_group"
    assert material.sha256 and material.id == "MAT-001"


def test_import_second_material_gets_new_id(store: ProjectStore, tmp_path: Path):
    project_id = store.create_project("导入2").id
    first = import_material(store, project_id, "note", write_csv(tmp_path / "a.csv", [{"x": 1}]))
    second = import_material(store, project_id, "note", write_csv(tmp_path / "b.csv", [{"x": 2}]))
    assert (first.id, second.id) == ("MAT-001", "MAT-002")


def test_import_missing_file_raises(store: ProjectStore):
    with pytest.raises(FileNotFoundError):
        import_material(store, store.create_project("缺失").id, "results", "/nonexistent.csv")


def test_legacy_results_normalization(tmp_path: Path):
    run_dir = tmp_path / "old-run"
    run_dir.mkdir()
    payload = {
        "results": [
            {
                "name": "candidate-repeat-0",
                "status": "passed",
                "seed": "abc123",
                "repeat_index": 0,
                "comparison_group": "candidate",
                "metrics": {"success_rate": 0.97, "mean_iterations": 107.65},
            },
            {"name": "baseline-repeat-0", "status": "passed", "seed": "abc124", "repeat_index": 0, "comparison_group": "baseline", "metrics": {"success_rate": 0.95, "mean_iterations": 267.55}},
        ]
    }
    (run_dir / "04-results.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "03-benchmark-adapters.json").write_text(
        json.dumps({"adapters": [{"metric_schema": {"mean_iterations": {"direction": "lower_is_better"}, "success_rate": {"direction": "higher_is_better"}}}]}),
        encoding="utf-8",
    )
    rows, directions, notes = normalize_legacy_results(run_dir)
    assert len(rows) == 4  # 每个 metric 一行
    assert directions["mean_iterations"] == "lower_is_better"
    assert any("近似键" in note for note in notes)
    iteration_values = {r["value"] for r in rows if r["metric"] == "mean_iterations"}
    assert iteration_values == {107.65, 267.55}


def test_legacy_import_registers_materials_readonly(tmp_path: Path, store: ProjectStore):
    run_dir = tmp_path / "old-run"
    run_dir.mkdir()
    (run_dir / "04-results.json").write_text(
        json.dumps({"results": [{"name": "r0", "status": "passed", "metrics": {"m": 1.0}, "comparison_group": "candidate"}]}),
        encoding="utf-8",
    )
    (run_dir / "03-benchmark-adapters.json").write_text(json.dumps({"adapters": []}), encoding="utf-8")
    original = (run_dir / "04-results.json").read_text(encoding="utf-8")
    project_id = store.create_project("旧导入").id
    materials = import_legacy_run(store, project_id, run_dir)
    assert materials
    assert all(m.kind == "legacy_run" for m in materials)
    # 旧目录未被修改（只读适配）
    assert (run_dir / "04-results.json").read_text(encoding="utf-8") == original
    assert store.load_materials(project_id)
