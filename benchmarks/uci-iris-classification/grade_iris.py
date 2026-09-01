from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--method",
        choices=[
            "nearest_centroid",
            "knn3",
            "majority_class",
            "dummy_stratified",
            "gaussian_nb",
            "decision_tree",
            "linear_logistic",
            "sepal_centroid",
        ],
        required=True,
    )
    parser.add_argument("--data", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--metrics", required=True)
    args = parser.parse_args()

    data_path = Path(args.data)
    split_path = Path(args.split)
    rows = _load_rows(data_path)
    split = json.loads(split_path.read_text(encoding="utf-8"))
    test_indices = {int(item) for item in split.get("test_indices", [])}
    train = [row for index, row in enumerate(rows) if index not in test_indices]
    test = [row for index, row in enumerate(rows) if index in test_indices]
    if not train or not test:
        raise SystemExit("split must produce non-empty train and test partitions")

    predictions = _predict_all(args.method, train, [row[0] for row in test])
    labels = [row[1] for row in test]
    metrics = _metrics(labels, predictions, data_path, split_path)
    metrics.update(_class_counts("train", [label for _, label in train]))
    metrics.update(_class_counts("test", labels))
    metrics.update(
        {
            "method": args.method,
            "train_cases": len(train),
            "test_cases": len(test),
            "split_name": split.get("name", ""),
            "dataset_doi": split.get("dataset_doi", ""),
        }
    )
    Path(args.metrics).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_rows(path: Path) -> list[tuple[list[float], str]]:
    rows: list[tuple[list[float], str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            raise SystemExit(f"invalid iris row: {line}")
        rows.append(([float(value) for value in parts[:4]], parts[4]))
    return rows


def _predict_all(method: str, train: list[tuple[list[float], str]], feature_rows: list[list[float]]) -> list[str]:
    if method == "gaussian_nb":
        model = _fit_gaussian_nb(train)
        return [_gaussian_nb_predict(model, features) for features in feature_rows]
    if method == "decision_tree":
        tree = _fit_tree(train, max_depth=3)
        return [_tree_predict(tree, features) for features in feature_rows]
    if method == "linear_logistic":
        model = _fit_linear_logistic(train)
        return [_linear_logistic_predict(model, features) for features in feature_rows]
    return [_predict(method, train, features) for features in feature_rows]


def _predict(method: str, train: list[tuple[list[float], str]], features: list[float]) -> str:
    if method == "majority_class":
        return Counter(label for _, label in train).most_common(1)[0][0]
    if method == "dummy_stratified":
        return _dummy_stratified_predict(train, features)
    if method == "knn3":
        return _knn_predict(train, features, k=3)
    feature_indices = [0, 1] if method == "sepal_centroid" else [0, 1, 2, 3]
    centroids = _centroids(train, feature_indices)
    projected = [features[index] for index in feature_indices]
    return min(centroids, key=lambda label: _squared_distance(projected, centroids[label]))


def _dummy_stratified_predict(train: list[tuple[list[float], str]], features: list[float]) -> str:
    counts = Counter(label for _, label in train)
    labels = sorted(counts)
    total = sum(counts.values())
    key = ",".join(f"{value:.6f}" for value in features)
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16) % total
    cumulative = 0
    for label in labels:
        cumulative += counts[label]
        if bucket < cumulative:
            return label
    return labels[-1]


def _knn_predict(train: list[tuple[list[float], str]], features: list[float], k: int) -> str:
    neighbors = sorted((_squared_distance(features, train_features), label) for train_features, label in train)[:k]
    counts = Counter(label for _, label in neighbors)
    top_count = max(counts.values())
    tied = [label for label, count in counts.items() if count == top_count]
    if len(tied) == 1:
        return tied[0]
    return min(tied, key=lambda label: (sum(distance for distance, item in neighbors if item == label), label))


def _centroids(rows: list[tuple[list[float], str]], feature_indices: list[int]) -> dict[str, list[float]]:
    totals: dict[str, list[float]] = defaultdict(lambda: [0.0 for _ in feature_indices])
    counts: Counter[str] = Counter()
    for features, label in rows:
        counts[label] += 1
        for out_index, feature_index in enumerate(feature_indices):
            totals[label][out_index] += features[feature_index]
    return {label: [value / counts[label] for value in totals[label]] for label in totals}


def _fit_gaussian_nb(rows: list[tuple[list[float], str]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[list[float]]] = defaultdict(list)
    for features, label in rows:
        grouped[label].append(features)
    total = len(rows)
    model: dict[str, dict[str, object]] = {}
    for label, values in grouped.items():
        means = [sum(row[index] for row in values) / len(values) for index in range(len(values[0]))]
        variances = []
        for index, mean in enumerate(means):
            variance = sum(math.pow(row[index] - mean, 2) for row in values) / len(values)
            variances.append(max(variance, 1e-9))
        model[label] = {"prior": len(values) / total, "means": means, "variances": variances}
    return model


def _gaussian_nb_predict(model: dict[str, dict[str, object]], features: list[float]) -> str:
    scores: dict[str, float] = {}
    for label, params in model.items():
        means = params["means"]
        variances = params["variances"]
        assert isinstance(means, list) and isinstance(variances, list)
        score = math.log(float(params["prior"]))
        for value, mean, variance in zip(features, means, variances):
            score += -0.5 * (math.log(2.0 * math.pi * variance) + math.pow(value - mean, 2) / variance)
        scores[label] = score
    return max(sorted(scores), key=lambda label: scores[label])


def _fit_tree(rows: list[tuple[list[float], str]], max_depth: int) -> dict[str, object]:
    return _build_tree(rows, depth=0, max_depth=max_depth)


def _build_tree(rows: list[tuple[list[float], str]], depth: int, max_depth: int) -> dict[str, object]:
    labels = [label for _, label in rows]
    majority = _majority_label(labels)
    if depth >= max_depth or len(set(labels)) == 1 or len(rows) < 4:
        return {"type": "leaf", "label": majority}
    split = _best_split(rows)
    if split is None:
        return {"type": "leaf", "label": majority}
    feature_index, threshold = split
    left = [row for row in rows if row[0][feature_index] <= threshold]
    right = [row for row in rows if row[0][feature_index] > threshold]
    if not left or not right:
        return {"type": "leaf", "label": majority}
    return {
        "type": "node",
        "feature_index": feature_index,
        "threshold": threshold,
        "left": _build_tree(left, depth + 1, max_depth),
        "right": _build_tree(right, depth + 1, max_depth),
        "label": majority,
    }


def _best_split(rows: list[tuple[list[float], str]]) -> tuple[int, float] | None:
    parent = _gini([label for _, label in rows])
    best_gain = 0.0
    best: tuple[int, float] | None = None
    feature_count = len(rows[0][0])
    for feature_index in range(feature_count):
        values = sorted({features[feature_index] for features, _ in rows})
        thresholds = [(left + right) / 2.0 for left, right in zip(values, values[1:])]
        for threshold in thresholds:
            left_labels = [label for features, label in rows if features[feature_index] <= threshold]
            right_labels = [label for features, label in rows if features[feature_index] > threshold]
            if not left_labels or not right_labels:
                continue
            weighted = (len(left_labels) / len(rows)) * _gini(left_labels) + (len(right_labels) / len(rows)) * _gini(right_labels)
            gain = parent - weighted
            candidate = (feature_index, threshold)
            if gain > best_gain + 1e-12 or (abs(gain - best_gain) <= 1e-12 and best is not None and candidate < best):
                best_gain = gain
                best = candidate
    return best


def _tree_predict(tree: dict[str, object], features: list[float]) -> str:
    node = tree
    while node.get("type") == "node":
        feature_index = int(node["feature_index"])
        threshold = float(node["threshold"])
        node = node["left"] if features[feature_index] <= threshold else node["right"]
        assert isinstance(node, dict)
    return str(node.get("label"))


def _gini(labels: list[str]) -> float:
    counts = Counter(labels)
    total = len(labels)
    return 1.0 - sum(math.pow(count / total, 2) for count in counts.values())


def _majority_label(labels: list[str]) -> str:
    counts = Counter(labels)
    return min(counts, key=lambda label: (-counts[label], label))


def _fit_linear_logistic(rows: list[tuple[list[float], str]]) -> dict[str, object]:
    labels = sorted({label for _, label in rows})
    means = [sum(features[index] for features, _ in rows) / len(rows) for index in range(len(rows[0][0]))]
    scales = []
    for index, mean in enumerate(means):
        variance = sum(math.pow(features[index] - mean, 2) for features, _ in rows) / len(rows)
        scales.append(math.sqrt(variance) or 1.0)
    xs = [[1.0, *[(features[index] - means[index]) / scales[index] for index in range(len(features))]] for features, _ in rows]
    label_index = {label: index for index, label in enumerate(labels)}
    weights = [[0.0 for _ in xs[0]] for _ in labels]
    lr = 0.08
    l2 = 1e-4
    for _ in range(900):
        grads = [[0.0 for _ in xs[0]] for _ in labels]
        for x, (_, label) in zip(xs, rows):
            probs = _softmax([sum(weight * value for weight, value in zip(class_weights, x)) for class_weights in weights])
            target = label_index[label]
            for class_index, prob in enumerate(probs):
                diff = prob - (1.0 if class_index == target else 0.0)
                for feature_index, value in enumerate(x):
                    grads[class_index][feature_index] += diff * value / len(rows)
        for class_index in range(len(labels)):
            for feature_index in range(len(xs[0])):
                penalty = 0.0 if feature_index == 0 else l2 * weights[class_index][feature_index]
                weights[class_index][feature_index] -= lr * (grads[class_index][feature_index] + penalty)
    return {"labels": labels, "means": means, "scales": scales, "weights": weights}


def _linear_logistic_predict(model: dict[str, object], features: list[float]) -> str:
    labels = model["labels"]
    means = model["means"]
    scales = model["scales"]
    weights = model["weights"]
    assert isinstance(labels, list) and isinstance(means, list) and isinstance(scales, list) and isinstance(weights, list)
    x = [1.0, *[(features[index] - means[index]) / scales[index] for index in range(len(features))]]
    scores = [sum(weight * value for weight, value in zip(class_weights, x)) for class_weights in weights]
    best = max(range(len(scores)), key=lambda index: (scores[index], str(labels[index])))
    return str(labels[best])


def _softmax(scores: list[float]) -> list[float]:
    offset = max(scores)
    exps = [math.exp(score - offset) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]


def _metrics(labels: list[str], predictions: list[str], data_path: Path, split_path: Path) -> dict[str, object]:
    correct = sum(1 for expected, predicted in zip(labels, predictions) if expected == predicted)
    accuracy = correct / len(labels)
    classes = sorted(set(labels) | set(predictions))
    f1_values = []
    matrix = _confusion_matrix(labels, predictions, classes)
    for label in classes:
        tp = sum(1 for expected, predicted in zip(labels, predictions) if expected == label and predicted == label)
        fp = sum(1 for expected, predicted in zip(labels, predictions) if expected != label and predicted == label)
        fn = sum(1 for expected, predicted in zip(labels, predictions) if expected == label and predicted != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_values.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    metrics: dict[str, object] = {
        "accuracy": round(accuracy, 6),
        "macro_f1": round(sum(f1_values) / len(f1_values), 6) if f1_values else 0.0,
        "error_rate": round(1.0 - accuracy, 6),
        "label_order": classes,
        "confusion_matrix": matrix,
        "prediction_sha256": _sha256_text("\n".join(predictions) + "\n"),
        "data_sha256": _sha256_file(data_path),
        "split_sha256_actual": _sha256_file(split_path),
    }
    for index, label in enumerate(classes):
        slug = _label_slug(label)
        tp = matrix[index][index]
        fp = sum(row[index] for row in matrix) - tp
        fn = sum(matrix[index]) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        metrics[f"precision_{slug}"] = round(precision, 6)
        metrics[f"recall_{slug}"] = round(recall, 6)
        metrics[f"f1_{slug}"] = round(2 * precision * recall / (precision + recall), 6) if precision + recall else 0.0
    for expected_index, expected in enumerate(classes):
        for predicted_index, predicted in enumerate(classes):
            metrics[f"cm_{_label_slug(expected)}_{_label_slug(predicted)}"] = matrix[expected_index][predicted_index]
    return metrics


def _class_counts(prefix: str, labels: list[str]) -> dict[str, int]:
    counts = Counter(labels)
    return {f"{prefix}_class_count_{_label_slug(label)}": counts[label] for label in sorted(counts)}


def _squared_distance(left: list[float], right: list[float]) -> float:
    return sum(math.pow(a - b, 2) for a, b in zip(left, right))


def _confusion_matrix(labels: list[str], predictions: list[str], classes: list[str]) -> list[list[int]]:
    index = {label: position for position, label in enumerate(classes)}
    matrix = [[0 for _ in classes] for _ in classes]
    for expected, predicted in zip(labels, predictions):
        matrix[index[expected]][index[predicted]] += 1
    return matrix


def _label_slug(label: str) -> str:
    return label.replace("Iris-", "").replace("-", "_").lower()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
