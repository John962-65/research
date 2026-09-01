# UCI Iris Classification Benchmark Pack

This is a lightweight external benchmark pack for validating the research-agent paper-grade benchmark path.

- Official dataset: https://archive.ics.uci.edu/dataset/53/iris
- DOI: 10.24432/C56C76
- License: CC BY 4.0 as reported by the UCI Machine Learning Repository.
- Frozen local data: `data/iris.data`
- Local dataset description/fulltext: `fulltext/iris.names.txt`
- Frozen split: `split/iris-stratified-test-v1.json`
- Grader: `grade_iris.py`

The benchmark compares a primary executable candidate/baseline/ablation trio over the same frozen split, plus broader `role=other` reference baselines:

- `candidate`: nearest centroid classifier using all four Iris features.
- `baseline`: deterministic k=3 nearest-neighbor classifier on all four Iris features.
- `ablation`: nearest centroid classifier using only sepal length and sepal width.
- `other` reference: deterministic majority-class classifier.
- `other` reference: deterministic stratified dummy classifier using feature hashing and training-set class proportions.
- `other` reference: dependency-free Gaussian Naive Bayes classifier.
- `other` reference: dependency-free depth-limited Gini decision tree classifier.
- `other` reference: dependency-free multinomial linear logistic classifier.

The reference methods are benchmark-pack implementations rather than scikit-learn wrappers; this keeps the smoke path reproducible in environments without third-party scientific Python packages.
They broaden baseline evidence without changing the primary candidate-vs-knn3 statistical comparison.
This pack is intentionally small so that paper-grade manifest, provenance, metric schema, grader hash, role-command differentiation, and repeated execution gates can be exercised without external package dependencies.
Each metrics artifact also records a confusion matrix plus data/split/prediction SHA256 values for artifact-level audit; the standard `04-results.json` table only imports numeric metrics.

## Primary Role Parameter Mapping

The primary candidate/baseline/ablation manifests intentionally differ only in the `--method` flag and metrics artifact name. They share the same frozen dataset, stratified split, grader, metric schema, repeat policy, and provenance fields so that the benchmark contract isolates the method comparison rather than changing data or evaluation conditions.

| Role | Manifest | Method flag | Feature policy | Metrics artifact | Interpretation |
| --- | --- | --- | --- | --- | --- |
| `candidate` | `manifest-candidate.json` | `--method nearest_centroid` | all four numeric Iris features | `candidate_metrics.json` | primary candidate; compared directly with the matched `knn3` baseline |
| `baseline` | `manifest-baseline.json` | `--method knn3` | all four numeric Iris features | `baseline_metrics.json` | matched deterministic k=3 nearest-neighbor baseline |
| `ablation` | `manifest-ablation.json` | `--method sepal_centroid` | sepal length and sepal width only | `ablation_metrics.json` | feature-removal ablation for the nearest-centroid candidate |

Shared primary metrics are `accuracy`, `macro_f1`, and `error_rate`. The standalone pack runner treats `accuracy` and `macro_f1` as preregistered primary metrics, applies the same repeated execution count to all three roles, and records neutral/no-superiority claim boundaries when the candidate and matched baseline are statistically indistinguishable.

Run the pack without a full LLM paper workflow:

```bash
PYTHONPATH=src python3 -m research_agent benchmark-pack-run \
  --topic "Iris classification benchmark pack execution" \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-candidate.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-baseline.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-ablation.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-majority.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-dummy-stratified.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-gaussian-nb.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-decision-tree.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-reference-linear-logistic.json \
  --execution-repeats 3 \
  --allowed-command python3 \
  --out runs/uci-iris-expanded-baseline-pack-run
```

Verify the local dataset-description fulltext grounding path:

```bash
PYTHONPATH=src python3 -m research_agent fulltext-grounding-run \
  --topic "UCI Iris fulltext citation grounding" \
  --fulltext-path benchmarks/uci-iris-classification/fulltext/iris.names.txt \
  --claim "The UCI Iris description states that the data set contains three classes of 50 instances each and four numeric predictive attributes plus the class label." \
  --out runs/uci-iris-fulltext-grounding
```
