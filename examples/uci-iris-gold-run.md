# UCI Iris Gold Run Checklist

This checklist is the shortest path from the included UCI Iris benchmark pack to a real end-to-end paper-grade run.

## Preconditions

Set real credentials and contact metadata before running without `--no-llm-ping`:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:8317"
export OPENAI_MODEL="gpt-5.5"
export OPENAI_API_KEY="<real-key>"
export RESEARCH_AGENT_CONTACT_EMAIL="<your-real-contact-email>"
```

Optional but recommended for fewer rate-limit warnings:

```bash
export SEMANTIC_SCHOLAR_API_KEY="..."
export OPENALEX_API_KEY="..."
```

Check whether the real gold run can start without exposing secret values:

```bash
PYTHONPATH=src python3 -m research_agent gold-run-doctor \
  --topic "Iris classification benchmark smoke" \
  --config examples/uci-iris-paper-grade-config.toml \
  --benchmark-pack-run-dir runs/uci-iris-benchmark-pack-run \
  --fulltext-grounding-run-dir runs/uci-iris-fulltext-grounding \
  --out runs/uci-iris-gold-run-doctor
```

The doctor should report `ready` before the full `run` command is started. `blocked` means a required credential, contact email, paper-grade config item, benchmark validation artifact, or fulltext grounding artifact is missing.
Add `--ping-llm` to the doctor command after exporting real gateway credentials if you want it to call the local OpenAI-compatible endpoint before the full run; secret values are not written to doctor artifacts.
The included config intentionally contains scaffold release metadata. Before a real gold run, copy the config and fill `[release]`, or pass real `--release-code-repository-url`, `--release-code-archive-doi`, `--release-code-license`, `--release-code-version`, `--release-data-access-statement`, and `--release-environment-url` values to both doctor and the final run command.
After an end-to-end candidate run completes, rerun the doctor with `--candidate-run-dir runs/uci-iris-gold-run` to check the actual gold-run contract, including submission package, scorecard, run integrity, final handoff, repair queue, claim consistency, and the no-superiority boundary required for negative/neutral benchmark outcomes.
If the final handoff is `ready_for_submission_upload`, the package and scorecard source artifacts must also be upload-ready and run integrity must be `pass`; use `ready_for_human_handoff` when non-blocking human submission review remains.

## Verify Inputs

```bash
PYTHONPATH=src python3 -m research_agent preflight \
  --topic "Iris classification benchmark smoke" \
  --config examples/uci-iris-paper-grade-config.toml

PYTHONPATH=src python3 -m research_agent paper-grade-probe \
  --topic "Iris classification benchmark smoke" \
  --config examples/uci-iris-paper-grade-config.toml \
  --query "UCI Iris classification benchmark Fisher discriminant analysis" \
  --out runs/uci-iris-online-probe

PYTHONPATH=src python3 -m research_agent paper-grade-benchmark-probe \
  --config examples/uci-iris-paper-grade-config.toml \
  --out runs/uci-iris-benchmark-probe
```

## Execute Benchmark Pack Only

This step runs the real UCI Iris candidate/baseline/ablation manifests and writes the standard `04-*` result, statistics, runbook, and benchmark audit artifacts. It does not call an LLM and does not count as the full gold run.

```bash
PYTHONPATH=src python3 -m research_agent benchmark-pack-run \
  --topic "Iris classification benchmark pack execution" \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-candidate.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-baseline.json \
  --benchmark-manifest benchmarks/uci-iris-classification/manifest-ablation.json \
  --execution-repeats 3 \
  --allowed-command python3 \
  --out runs/uci-iris-benchmark-pack-run
```

## Verify Fulltext Grounding Only

This step builds a local fulltext corpus from the UCI Iris dataset description and runs the same citation grounding audit used after paper revision. It does not call an LLM and does not count as the full gold run.

```bash
PYTHONPATH=src python3 -m research_agent fulltext-grounding-run \
  --topic "UCI Iris fulltext citation grounding" \
  --fulltext-path benchmarks/uci-iris-classification/fulltext/iris.names.txt \
  --claim "The UCI Iris description states that the data set contains three classes of 50 instances each and four numeric predictive attributes plus the class label." \
  --out runs/uci-iris-fulltext-grounding
```

## Run

```bash
PYTHONPATH=src python3 -m research_agent run \
  --topic "Iris classification benchmark smoke" \
  --config examples/uci-iris-paper-grade-config.toml \
  --out runs/uci-iris-gold-run
```

The pipeline must still stop at the review gate and the benchmark execution gate. Approve only after inspecting the generated artifacts:

```bash
PYTHONPATH=src python3 -m research_agent approve runs/uci-iris-gold-run \
  --reviewer "human" \
  --notes "Literature gate inspected; UCI Iris is acceptable as a benchmark-path smoke, not as a novelty claim."

PYTHONPATH=src python3 -m research_agent approve-execution runs/uci-iris-gold-run \
  --reviewer "human" \
  --notes "Benchmark manifests, allowed commands, frozen split, and grader hash inspected."
```

## Acceptance Criteria

After the run completes:

```bash
PYTHONPATH=src python3 -m research_agent perfect-readiness \
  --project-dir . \
  --runs-dir runs \
  --out .
```

Expected direction:

- `real_benchmark_packs`: ready.
- `candidate_baseline_ablation_implementations`: ready.
- `gold_end_to_end_run`: ready only if `runs/uci-iris-gold-run` reaches `ready_for_human_handoff` or `ready_for_submission_upload` with `benchmark_evidence_grade=real_benchmark` and `10-claim-consistency.json` pass; negative/neutral outcomes must keep a no-superiority claim boundary.
- `fulltext_citation_grounding`: ready only if the generated paper cites grounded context from `fulltext/iris.names.txt` or other curated fulltext.
- `statistical_design`: ready only if the benchmark execution produces `04-statistics.json` with repeats >= 3, CI, effect size, and no warnings.

Do not use this Iris run to claim broad scientific novelty. Its purpose is to prove the agent can complete an auditable paper-grade workflow over a real public benchmark.
