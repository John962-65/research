"""DiscoveryBench 任务适配器（官方仓库 allenai/discoverybench，按真实布局校准）。

官方布局（v2024）：
    <bench_root>/discoverybench/discoverybench/{real,synth}/{train,dev,test}/<task_dir>/metadata_N.json
    <bench_root>/eval/answer_key_{real,synth}.csv   # 官方金标（dataset, metadataid, query_id, gold_hypo）
每个 metadata_N.json 是一条查询；test 划分的金标只存在于 answer key（官方设计）。
task_id = "<subset_dir>/<split>/<task_dir>/metadata_N"（稳定、可复现）。

注意：AstaBench 内含 DiscoveryBench 子任务，与独立 DiscoveryBench 样本重叠；
同一批任务不得当作两份独立评测证据（见 docs/evaluation-protocol.md）。
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 评测子集 → 官方目录名
SUBSET_DIRS = {"main": "real", "real": "real", "synthetic": "synth", "gen": "synth", "synth": "synth"}
VALID_SPLITS = ("train", "dev", "test")


@dataclass
class DiscoveryTask:
    task_id: str
    query: str
    gold_hypothesis: str
    domain: str = ""
    dataset_dir: str = ""
    source_path: str = ""
    gold_source: str = ""  # answer_key（官方）| metadata
    meta: dict[str, Any] = field(default_factory=dict)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_answer_key(bench_root: Path, subset_dir: str) -> dict[tuple[str, str], str]:
    """官方金标：eval/answer_key_{real,synth}.csv → {(dataset, metadata_id): gold_hypo}。"""
    key_path = bench_root / "eval" / f"answer_key_{subset_dir}.csv"
    if not key_path.exists():
        return {}
    keys: dict[tuple[str, str], str] = {}
    with key_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            dataset = str(row.get("dataset") or "").strip()
            metadata_id = str(row.get("metadataid") or "").strip()
            gold = str(row.get("gold_hypo") or "").strip()
            if dataset and metadata_id and gold:
                keys.setdefault((dataset, metadata_id), gold)
    return keys


def _find_task_files(bench_root: Path, subset: str, split: str | None) -> tuple[list[Path], str | None]:
    """定位官方布局的 metadata_*.json；官方布局不存在时才做宽容回退（fixture/旧布局）。"""
    subset_dir = SUBSET_DIRS.get(subset)
    if subset_dir:
        # 官方克隆布局：<clone>/discoverybench/{real,synth}/...（个别版本多嵌套一层，向后兼容）
        base = bench_root / "discoverybench" / subset_dir
        if not base.is_dir():
            base = bench_root / "discoverybench" / "discoverybench" / subset_dir
        if base.is_dir():
            if split:
                split_base = base / split
                if split_base.is_dir():
                    return sorted(split_base.rglob("metadata_*.json")), subset_dir
                return [], subset_dir  # 显式指定 split 却不存在：宁缺毋滥，不跨子集回退
            return sorted(base.rglob("metadata_*.json")), subset_dir
    # 宽容回退：递归找含 metadata 的 JSON（适配 fixture/旧布局）
    candidates = []
    for path in sorted(bench_root.rglob("*.json")):
        parts = [p.lower() for p in path.parts]
        if "metadata" in parts or path.name.startswith("metadata"):
            if split and split not in parts:
                continue
            candidates.append(path)
    return candidates, None


def _extract_questions(entry: dict[str, Any]) -> str:
    queries = entry.get("queries")
    questions: list[str] = []
    if isinstance(queries, list):
        for group in queries:
            items = group if isinstance(group, list) else [group]
            for item in items:
                if isinstance(item, dict) and str(item.get("question") or "").strip():
                    questions.append(str(item["question"]).strip())
    if questions:
        return " ".join(f"({i + 1}) {q}" for i, q in enumerate(questions))
    for key in ("query", "question", "problem"):
        if isinstance(entry.get(key), str) and entry[key].strip():
            return entry[key].strip()
    return ""


def _extract_gold_hypothesis(entry: dict[str, Any]) -> str:
    hypotheses = entry.get("hypotheses")
    if isinstance(hypotheses, dict):
        for group_key in ("main", "hypothesis", "gold"):
            group = hypotheses.get(group_key)
            if isinstance(group, list):
                for item in group:
                    if isinstance(item, dict):
                        for field_key in ("text", "hypothesis", "statement"):
                            if isinstance(item.get(field_key), str) and item[field_key].strip():
                                return item[field_key].strip()
                    elif isinstance(item, str) and item.strip():
                        return item.strip()
    for key in ("hypothesis", "gold_hypothesis", "reference_hypothesis"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = value.get("text") or value.get("hypothesis")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _extract_dataset_dir(entry: dict[str, Any], source: Path, bench_root: Path) -> str:
    # 官方布局：数据文件（csv/dta）与 metadata 同目录
    if any(source.parent.glob("*.csv")) or any(source.parent.glob("*.dta")):
        return str(source.parent)
    candidates = []
    for key in ("dataset_dir", "datasets_dir", "data_dir"):
        if isinstance(entry.get(key), str):
            candidates.append(entry[key])
    datasets = entry.get("datasets")
    if isinstance(datasets, list) and datasets and isinstance(datasets[0], dict):
        for key in ("dataset_dir", "dir", "path"):
            if isinstance(datasets[0].get(key), str):
                candidates.append(datasets[0][key])
                break
    for candidate in candidates:
        for base in (source.parent, bench_root):
            path = (base / candidate).resolve()
            if path.is_dir():
                return str(path)
    return ""


def _task_id_for(source: Path, bench_root: Path, subset_dir: str | None) -> str:
    try:
        relative = source.relative_to(bench_root).with_suffix("")
        return "/".join(relative.parts)
    except ValueError:
        return source.stem


def load_tasks(
    bench_root: str | Path,
    subset: str = "main",
    split: str | None = None,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> list[DiscoveryTask]:
    bench_root = Path(bench_root)
    if not bench_root.exists():
        raise FileNotFoundError(
            f"DiscoveryBench 数据根目录不存在: {bench_root}。请先运行 benchmarks/discoverybench/fetch.sh"
        )
    if split is not None and split not in VALID_SPLITS:
        raise ValueError(f"非法 split: {split}（可选 {VALID_SPLITS}）")
    files, subset_dir = _find_task_files(bench_root, subset, split)
    if not files:
        raise FileNotFoundError(
            f"在 {bench_root} 中未找到 subset={subset} split={split} 的任务元数据；"
            f"官方布局为 discoverybench/discoverybench/{{real,synth}}/{{train,dev,test}}/<task>/metadata_N.json"
        )
    tasks: list[DiscoveryTask] = []
    wanted = set(task_ids or [])
    answer_key = _load_answer_key(bench_root, subset_dir) if subset_dir else {}
    for path in files:
        entry = _read_json(path)
        if not isinstance(entry, dict):
            continue
        query = _extract_questions(entry)
        gold = _extract_gold_hypothesis(entry)
        gold_source = "metadata" if gold else ""
        # 官方 answer key 优先（test 划分的金标只在这里）
        if subset_dir:
            key = (path.parent.name, path.stem.replace("metadata_", ""))
            if key in answer_key:
                gold = answer_key[key]
                gold_source = "answer_key"
        if not query or not gold:
            continue
        task_id = _task_id_for(path, bench_root, subset_dir)
        if wanted and task_id not in wanted:
            continue
        tasks.append(
            DiscoveryTask(
                task_id=task_id,
                query=query,
                gold_hypothesis=gold,
                domain=str(entry.get("domain") or ""),
                dataset_dir=_extract_dataset_dir(entry, path, bench_root),
                source_path=str(path),
                gold_source=gold_source,
                meta={k: v for k, v in entry.items() if k not in ("queries", "hypotheses")},
            )
        )
        if limit and len(tasks) >= limit and not wanted:
            break
    if not tasks:
        raise FileNotFoundError(
            "元数据存在但没有可用任务（需同时含 question 与 gold hypothesis text）；"
            "部分官方任务的金标假设为空，会被自动跳过"
        )
    return tasks


def select_dev_tasks(bench_root: str | Path, subset: str, n: int, split: str | None = None) -> dict[str, Any]:
    """确定性 dev 任务选择。

    官方数据现实：train 金标在 metadata 里（real/train 14 个），test 金标只在
    eval/answer_key_*.csv，dev 划分无金标。因此默认选择 = train 全部 + test 按序补足，
    并写明污染注记：test 任务已用于开发期评测，不得再作为留出集报告结论。
    """
    tasks = load_tasks(bench_root, subset, split=split)
    train = sorted((t for t in tasks if "/train/" in f"/{t.task_id}/"), key=lambda t: t.task_id)
    non_train = sorted((t for t in tasks if "/train/" not in f"/{t.task_id}/"), key=lambda t: t.task_id)
    selected = (train + non_train)[:n]
    return {
        "rule": f"train 优先、其余按 task_id 排序补足，取前 {n}（subset={subset}，确定性可复现）",
        "subset": subset,
        "task_ids": [t.task_id for t in selected],
        "composition": {
            "from_train": sum(1 for t in selected if "/train/" in f"/{t.task_id}/"),
            "from_test_or_dev": sum(1 for t in selected if "/train/" not in f"/{t.task_id}/"),
        },
        "gold_source": sorted({t.gold_source for t in selected}),
        "note": (
            "若包含 test 划分任务：其金标来自公开 answer key，已用于开发期评测，"
            "不得再作为留出集报告结论。main(real) 与 synth(gen) 同源样本不得重复计入。"
        ),
    }


def load_task_tables(task: DiscoveryTask) -> list[dict[str, Any]]:
    """按表加载任务数据集，**保留表结构**（禁止盲目合并）。

    支持 .csv 与 .dta（.dta 需 pandas，见 pyproject [eval] extra）。
    返回 [{"name": 表名(file stem), "path": str, "rows": [行字典]}]。
    每行附 __dataset_file 标记来源（不合并不同 schema 的表）。
    """
    from ..integrations.material_importer import read_rows

    if not task.dataset_dir:
        return []
    tables: list[dict[str, Any]] = []
    dataset_dir = Path(task.dataset_dir)
    paths = sorted(dataset_dir.rglob("*.csv")) + sorted(dataset_dir.rglob("*.dta"))
    for data_path in paths:
        try:
            rows = read_rows(data_path)
        except (ValueError, OSError):
            continue
        for row in rows:
            row["__dataset_file"] = data_path.name
        tables.append({"name": data_path.stem, "path": str(data_path), "rows": rows})
    return tables


def load_task_rows(task: DiscoveryTask) -> list[dict[str, Any]]:
    """读取任务数据集（全部 CSV 合并行，带来源文件名列）。

    注意：多表任务使用本函数会丢失表结构——评测路径请用 load_task_tables。
    """
    from ..integrations.material_importer import read_rows

    if not task.dataset_dir:
        return []
    rows: list[dict[str, Any]] = []
    dataset_dir = Path(task.dataset_dir)
    for csv_path in sorted(dataset_dir.rglob("*.csv")):
        try:
            for row in read_rows(csv_path):
                row["__dataset_file"] = csv_path.name
                rows.append(row)
        except (ValueError, OSError):
            continue
    return rows
