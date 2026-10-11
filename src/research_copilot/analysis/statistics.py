"""统计分析（自研、零依赖）。

设计约定（对齐项目三原则）：
- 指标方向以声明（metric_directions）为准，名称启发式仅作缺省；输出带 ``direction_declared``。
- CI 优先、不给 p 值；效应量 = delta / 配对差值标准差。
- 极端分位数（P95/P99）在样本不足时输出告警并降级表述，不假装精确。
- 区分「独立查询数」与「同查询重复测量数」：重复测量先按查询聚合再比较。
- 成功/超时/失败混合数据不得只分析成功样本：非成功行被排除时必须计数并上报。
"""
from __future__ import annotations

import math
from typing import Any, Iterable

LOWER_TOKENS = ("time", "cost", "latency", "duration", "iteration", "collision", "failure", "error", "risk", "耗时", "成本", "延迟", "迭代", "碰撞", "失败", "误差", "风险")
HIGHER_TOKENS = ("success", "accuracy", "score", "rate", "coverage", "reward", "成功率", "准确", "得分", "覆盖率")

SUCCESS_STATUSES = {"success", "passed", "ok", "done", "true", "1"}
# P95 需要约 20 个独立样本、P99 需要约 100 个，才能给出有意义的估计
PERCENTILE_MIN_N = {90: 10, 95: 20, 99: 100}


def resolve_direction(metric: str, metric_directions: dict[str, str] | None = None) -> tuple[bool, bool]:
    """返回 (lower_is_better, declared)。声明优先，启发式只作缺省。"""
    declared = (metric_directions or {}).get(metric)
    if declared == "lower_is_better":
        return True, True
    if declared == "higher_is_better":
        return False, True
    lowered = metric.lower()
    if any(token in lowered for token in LOWER_TOKENS):
        return True, False
    if any(token in lowered for token in HIGHER_TOKENS):
        return False, False
    return True, False


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def std(values: Iterable[float]) -> float:
    """样本标准差（n-1）。"""
    values = list(values)
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def percentile(values: list[float], q: float) -> float:
    """线性插值分位数，q ∈ [0, 100]。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (q / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    frac = rank - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def numeric(rows: list[dict[str, Any]], field: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row.get(field))
        except (TypeError, ValueError):
            continue
        if not math.isnan(value) and not math.isinf(value):
            values.append(value)
    return values


def split_by_status(rows: list[dict[str, Any]], status_field: str = "status") -> tuple[list[dict[str, Any]], dict[str, int]]:
    """把行按状态分桶。返回 (成功行, 状态计数)。状态字段缺失时全部视为成功。"""
    counts: dict[str, int] = {}
    success_rows = []
    for row in rows:
        status = str(row.get(status_field) or "success").lower()
        counts[status] = counts.get(status, 0) + 1
        if status in SUCCESS_STATUSES:
            success_rows.append(row)
    return success_rows, counts


def aggregate_per_query(
    rows: list[dict[str, Any]], value_field: str, query_field: str = "query_id"
) -> tuple[list[float], int, int, list[str]]:
    """重复测量处理：有 query_id 时先按查询求均值。

    返回 (聚合值列表, 独立查询数, 原始重复测量数, 告警)。
    无 query_id 字段时把每行视为独立样本并说明。
    """
    mapping, n_rows, warnings = per_query_means(rows, value_field, query_field)
    return list(mapping.values()), len(mapping), n_rows, warnings


def per_query_means(
    rows: list[dict[str, Any]], value_field: str, query_field: str = "query_id"
) -> tuple[dict[str, float], int, list[str]]:
    """按查询键聚合（重复测量求均值）。返回 (键→均值, 原始行数, 告警)。

    无 query_id 字段时每行独立成键（"row:i"），不聚合。
    """
    if not rows:
        return {}, 0, []
    has_query_field = query_field in rows[0]
    if not has_query_field:
        values = {}
        for index, row in enumerate(rows):
            try:
                values[f"row:{index}"] = float(row.get(value_field))
            except (TypeError, ValueError):
                continue
        return values, len(rows), ["数据无 query_id 字段：每行按独立样本处理"]
    groups: dict[str, list[float]] = {}
    for row in rows:
        key = str(row.get(query_field))
        try:
            groups.setdefault(key, []).append(float(row.get(value_field)))
        except (TypeError, ValueError):
            continue
    warnings = []
    repeats = {k: len(v) for k, v in groups.items() if len(v) > 1}
    if repeats:
        warnings.append(
            f"存在同查询重复测量（{len(repeats)} 个查询重复 >1 次）：统计前已按查询聚合，重复测量未计入独立样本"
        )
    return {k: mean(v) for k, v in groups.items()}, len(rows), warnings


def two_mean_ci(candidate: list[float], baseline: list[float]) -> tuple[float, float] | None:
    """两组均值差的正态近似 95% CI（非配对回退）。"""
    if len(candidate) < 2 or len(baseline) < 2:
        return None
    delta = mean(candidate) - mean(baseline)
    se = math.sqrt(std(candidate) ** 2 / len(candidate) + std(baseline) ** 2 / len(baseline))
    return (delta - 1.96 * se, delta + 1.96 * se)


def paired_by_key(
    candidate_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    value_field: str,
    key_fields: tuple[str, ...] = ("seed", "repeat_index"),
) -> tuple[list[tuple[float, float]], list[str]]:
    """按 key_fields 配对（仅用于无 query_id 的独立 run 数据：同种子同索引）。"""
    def key_of(row: dict[str, Any]) -> tuple:
        return tuple(str(row.get(f) or "") for f in key_fields)

    cand = {key_of(r): r for r in candidate_rows}
    base = {key_of(r): r for r in baseline_rows}
    pairs: list[tuple[float, float]] = []
    unmatched: list[str] = []
    for key, crow in cand.items():
        brow = base.get(key)
        if brow is None:
            unmatched.append(f"candidate 无配对: {key}")
            continue
        try:
            pairs.append((float(crow.get(value_field)), float(brow.get(value_field))))
        except (TypeError, ValueError):
            unmatched.append(f"配对 {key} 数值不可解析")
    for key in base:
        if key not in cand:
            unmatched.append(f"baseline 无配对: {key}")
    return pairs, unmatched


def describe(values: list[float], label: str = "") -> dict[str, Any]:
    """描述统计 + 分位数小样本告警。"""
    result: dict[str, Any] = {
        "label": label,
        "n": len(values),
        "mean": mean(values) if values else None,
        "median": percentile(values, 50) if values else None,
        "std": std(values) if len(values) > 1 else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "percentiles": {},
        "warnings": [],
    }
    if values:
        for q in (90, 95, 99):
            min_n = PERCENTILE_MIN_N[q]
            if len(values) >= min_n:
                result["percentiles"][f"p{q}"] = percentile(values, q)
            else:
                result["percentiles"][f"p{q}"] = None
                result["warnings"].append(
                    f"p{q} 样本不足（n={len(values)} < {min_n}）：不给出精确值，仅报告 p90 及以下"
                )
    return result


def ci95(values: list[float]) -> tuple[float, float] | None:
    """正态近似 95% CI；样本 <2 返回 None。"""
    if len(values) < 2:
        return None
    m = mean(values)
    half = 1.96 * std(values) / math.sqrt(len(values))
    return (m - half, m + half)


def paired_by_key(
    candidate_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    value_field: str,
    key_fields: tuple[str, ...] = ("seed", "repeat_index"),
) -> tuple[list[tuple[float, float]], list[str]]:
    """按 key_fields 配对（同种子同索引），仅保留两侧都存在的配对。"""
    def key_of(row: dict[str, Any]) -> tuple:
        return tuple(str(row.get(f) or "") for f in key_fields)

    cand = {key_of(r): r for r in candidate_rows}
    base = {key_of(r): r for r in baseline_rows}
    pairs: list[tuple[float, float]] = []
    unmatched: list[str] = []
    for key, crow in cand.items():
        brow = base.get(key)
        if brow is None:
            unmatched.append(f"candidate 无配对: {key}")
            continue
        try:
            pairs.append((float(crow.get(value_field)), float(brow.get(value_field))))
        except (TypeError, ValueError):
            unmatched.append(f"配对 {key} 数值不可解析")
    for key in base:
        if key not in cand:
            unmatched.append(f"baseline 无配对: {key}")
    return pairs, unmatched


def compare_metric(
    rows: list[dict[str, Any]],
    metric: str,
    candidate_group: str,
    baseline_group: str,
    metric_directions: dict[str, str] | None = None,
    group_field: str = "comparison_group",
    query_field: str = "query_id",
) -> dict[str, Any]:
    """方向感知的组间比较。行需含 group_field 列与 metric 数值列；可选 status/query_id 列。

    返回结构包含：方向及是否声明、排除的状态计数、独立查询数 vs 重复测量数、
    配对/非配对 delta、95% CI、效应量、方向化解读（candidate_better / baseline_better_or_equal）。
    """
    lower_is_better, declared = resolve_direction(metric, metric_directions)
    buckets: dict[str, list[dict[str, Any]]] = {candidate_group: [], baseline_group: []}
    for row in rows:
        bucket = str(row.get(group_field) or "default")
        buckets.setdefault(bucket, []).append(row)
    for name in (candidate_group, baseline_group):
        buckets.setdefault(name, [])

    excluded_counts: dict[str, dict[str, int]] = {}
    usable: dict[str, list[dict[str, Any]]] = {}
    success_rows_by_group: dict[str, list[dict[str, Any]]] = {}
    for name in (candidate_group, baseline_group):
        success_rows, status_counts = split_by_status(buckets[name])
        excluded = {k: v for k, v in status_counts.items() if k not in SUCCESS_STATUSES}
        excluded_counts[name] = {"total": len(buckets[name]), "success": len(success_rows), "excluded": excluded}
        aggregated, n_queries, n_repeats, agg_warnings = aggregate_per_query(success_rows, metric, query_field)
        usable[name] = aggregated
        excluded_counts[name]["n_queries"] = n_queries
        excluded_counts[name]["n_repeats"] = n_repeats
        excluded_counts[name]["aggregation_warnings"] = agg_warnings
        success_rows_by_group[name] = success_rows

    cand_values = usable[candidate_group]
    base_values = usable[baseline_group]
    has_query_field = bool(success_rows_by_group[candidate_group]) and query_field in success_rows_by_group[candidate_group][0]

    if has_query_field:
        # 逐查询数据：按查询键配对（聚合后），这是唯一正确的配对方式；
        # 允许两侧成功查询集不完全一致，取公共查询配对并报告未匹配数
        cand_map, _, _ = per_query_means(success_rows_by_group[candidate_group], metric, query_field)
        base_map, _, _ = per_query_means(success_rows_by_group[baseline_group], metric, query_field)
        common = sorted(set(cand_map) & set(base_map))
        only_c = set(cand_map) - set(base_map)
        only_b = set(base_map) - set(cand_map)
        unmatched = [f"仅 candidate 有: {k}" for k in sorted(only_c)[:10]] + [f"仅 baseline 有: {k}" for k in sorted(only_b)[:10]]
        min_side = min(len(cand_map), len(base_map)) or 0
        coverage_ok = bool(common) and len(common) >= max(2, 0.8 * min_side)
        paired = coverage_ok
        pairs = [(cand_map[q], base_map[q]) for q in common]
        if common and len(common) < min_side:
            unmatched.insert(0, f"公共查询 {len(common)}/{min_side}（不足 80% 时回退非配对）")
            paired = coverage_ok
    else:
        # 独立 run 数据：按 (seed, repeat_index) 配对
        pairs, unmatched = paired_by_key(success_rows_by_group[candidate_group], success_rows_by_group[baseline_group], metric)
        paired = bool(pairs) and len(pairs) == len(cand_values) == len(base_values)

    comparison: dict[str, Any] = {
        "metric": metric,
        "lower_is_better": lower_is_better,
        "direction_declared": declared,
        "candidate_group": candidate_group,
        "baseline_group": baseline_group,
        "candidate": describe(cand_values, candidate_group),
        "baseline": describe(base_values, baseline_group),
        "excluded_rows": excluded_counts,
        "paired": False,
        "n_pairs": len(pairs) if pairs else 0,
        "unmatched_keys": unmatched[:20],
    }
    if paired and pairs:
        deltas = [c - b for c, b in pairs]
        comparison["paired"] = True
        comparison["delta_mean"] = mean(deltas)
        comparison["delta_std"] = std(deltas)
        comparison["delta_ci95"] = ci95(deltas)
        comparison["effect_size"] = (mean(deltas) / std(deltas)) if std(deltas) > 0 else None
        delta_for_interpretation = mean(deltas)
    elif cand_values and base_values:
        comparison["paired"] = False
        delta_for_interpretation = mean(cand_values) - mean(base_values)
        comparison["delta_mean"] = delta_for_interpretation
        comparison["delta_std"] = None
        comparison["delta_ci95"] = two_mean_ci(cand_values, base_values)
        pooled = math.sqrt((std(cand_values) ** 2 + std(base_values) ** 2) / 2) if len(cand_values) > 1 and len(base_values) > 1 else 0.0
        comparison["effect_size"] = (delta_for_interpretation / pooled) if pooled > 0 else None
    else:
        delta_for_interpretation = None
        comparison["delta_mean"] = None
        comparison["delta_ci95"] = None
        comparison["effect_size"] = None

    if delta_for_interpretation is None:
        comparison["interpretation"] = "insufficient_data"
        comparison["warnings"] = []
    else:
        warnings = []
        n_effective = comparison.get("n_pairs") or min(len(cand_values), len(base_values))
        if n_effective < 10:
            warnings.append(f"有效样本少（n={n_effective} < 10）：差异解读脆弱，应视为待验证信号而非结论")
        if not declared:
            warnings.append(
                "指标方向未经声明，由名称启发式推断；正式结论前请在 manifest/配置中声明 metric_schema.direction"
            )
        comparison["warnings"] = warnings
        better = delta_for_interpretation < 0 if lower_is_better else delta_for_interpretation > 0
        significant = False
        if comparison.get("delta_ci95"):
            lo, hi = comparison["delta_ci95"]
            significant = not (lo <= 0 <= hi)
        comparison["interpretation"] = (
            (
                "candidate_better" if better else "baseline_better_or_equal"
            )
            if significant
            else "no_clear_difference"
        )
    return comparison


def group_report(
    rows: list[dict[str, Any]],
    metric: str,
    group_field: str = "scenario",
    query_field: str = "query_id",
) -> dict[str, Any]:
    """按分组字段（如场景类型/机械臂数）分解指标。仅统计成功行并报告状态计数。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(group_field) or "unspecified"), []).append(row)
    report: dict[str, Any] = {"metric": metric, "group_field": group_field, "groups": {}}
    for name, group_rows in sorted(groups.items()):
        success_rows, status_counts = split_by_status(group_rows)
        aggregated, n_queries, n_repeats, _ = aggregate_per_query(success_rows, metric, query_field)
        report["groups"][name] = {
            "describe": describe(aggregated, name),
            "status_counts": status_counts,
            "n_rows": len(group_rows),
        }
    return report


def pearson(x: list[float], y: list[float]) -> float | None:
    """Pearson 相关系数；方差为 0 或样本 <3 返回 None。"""
    n = len(x)
    if n < 3 or n != len(y):
        return None
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    denom = math.sqrt(sxx * syy)
    if denom <= 0:
        return None
    return sxy / denom


RELATION_SIGN_THRESHOLD = 0.05  # |r| 低于该值视为无单调方向


def relation_sign(r: float | None) -> str:
    if r is None:
        return "unverifiable"
    if r >= RELATION_SIGN_THRESHOLD:
        return "positive"
    if r <= -RELATION_SIGN_THRESHOLD:
        return "negative"
    return "none"


def relation_signs(
    rows: list[dict[str, Any]], columns: list[str] | None = None, max_columns: int = 16, max_pairs: int = 40
) -> list[dict[str, Any]]:
    """数值列两两 Pearson 方向（供关系主张的程序化核对）。

    返回按 |r| 降序的 pair 列表（仅保留 |r|>0.05 有方向或 |r| 最大的前 max_pairs 对），
    保证关系图观测在上下文预算内携带信息量最大的对。
    """
    if columns is None:
        seen: list[str] = []
        for row in rows[:50]:
            for key in row:
                if key not in seen:
                    seen.append(key)
        columns = seen
    numeric_cols = [c for c in columns if numeric(rows, c)][:max_columns]
    out: list[dict[str, Any]] = []
    for i in range(len(numeric_cols)):
        for j in range(i + 1, len(numeric_cols)):
            a, b = numeric_cols[i], numeric_cols[j]
            xs = [float(r.get(a)) for r in rows if _is_num(r.get(a)) and _is_num(r.get(b))]
            ys = [float(r.get(b)) for r in rows if _is_num(r.get(a)) and _is_num(r.get(b))]
            r = pearson(xs, ys)
            if r is None:
                continue
            out.append({"a": a, "b": b, "pearson_r": round(r, 4), "sign": relation_sign(r), "n": len(xs)})
    out.sort(key=lambda item: -abs(item["pearson_r"]))
    return out[:max_pairs]


def _is_num(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(parsed) or math.isinf(parsed))


def regress(
    rows: list[dict[str, Any]], y: str, xs: list[str], filters: dict[str, str] | None = None
) -> dict[str, Any] | None:
    """多元 OLS（正规方程 + 高斯消元，零依赖）。用于回归断言的程序化验证。

    filters: {列: 字符串值}——行按 str(row[col]) == str(value) 过滤（子样本回归）。
    返回 {"betas": {列名: 系数}, "n": 样本数}；样本不足或奇异矩阵返回 None。
    """
    if filters:
        rows = [
            row for row in rows
            if all(str(row.get(col)) == str(val) for col, val in filters.items())
        ]
    columns = ["_intercept"] + list(xs)
    data = []
    for row in rows:
        try:
            data.append([1.0] + [float(row.get(x)) for x in xs] + [float(row.get(y))])
        except (TypeError, ValueError):
            continue
    n = len(data)
    k = len(columns)
    if n <= k:
        return None
    XtX = [[sum(row[i] * row[j] for row in data) for j in range(k)] for i in range(k)]
    Xty = [sum(row[i] * row[k] for row in data) for i in range(k)]
    A = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for col in range(k):
        pivot = max(range(col, k), key=lambda r: abs(A[r][col]))
        if abs(A[pivot][col]) < 1e-12:
            return None
        A[col], A[pivot] = A[pivot], A[col]
        for r in range(k):
            if r != col and A[r][col] != 0:
                factor = A[r][col] / A[col][col]
                for cc in range(col, k + 1):
                    A[r][cc] -= factor * A[col][cc]
    betas = {columns[i]: A[i][k] / A[i][i] for i in range(k)}
    return {"betas": betas, "n": n}


def group_profile(
    rows: list[dict[str, Any]], covariate_fields: list[str], group_field: str = "comparison_group"
) -> dict[str, Any]:
    """组间协变量画像：暴露潜在混杂因素（组定义之外的变量若分布不齐，需提示）。"""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(str(row.get(group_field) or "default"), []).append(row)
    profile: dict[str, Any] = {"covariates": {}, "imbalance_warnings": []}
    for field in covariate_fields:
        per_group = {}
        for name, group_rows in buckets.items():
            values = numeric(group_rows, field)
            per_group[name] = {"mean": mean(values) if values else None, "n": len(values)}
        profile["covariates"][field] = per_group
        group_names = list(per_group)
        for i in range(len(group_names)):
            for j in range(i + 1, len(group_names)):
                a = per_group[group_names[i]]["mean"]
                b = per_group[group_names[j]]["mean"]
                if a is None or b is None:
                    continue
                denom = max(abs(a), abs(b), 1e-9)
                if abs(a - b) / denom > 0.3:
                    profile["imbalance_warnings"].append(
                        f"协变量 {field} 在 {group_names[i]}({a:.3g}) 与 {group_names[j]}({b:.3g}) 之间差异 >30%："
                        "比较前请检查是否构成混杂因素"
                    )
    return profile
