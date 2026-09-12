# Runtime Fixes and Verification

Verified on 2026-09-09 with Python 3.12.

## Changes

- Implicit enabled agent roles now receive their default skills, including the
  skill content and hashes in the prepared request and LLM ledger.
- Each model request after an MCP result passes through the same call-count and
  cumulative prompt-character budget checks as the initial request.
- Each request records its own prompt hashes and provider token usage. Output
  validation attaches to the final response's call ID. Tool failures do not
  create fictional model calls, and failed continuations do not reuse old usage.
- Unauthorized MCP server requests reach the existing denial-receipt path.
- The optional MCP dependency is constrained to `>=1.2,<2`. MCP 2.2.0 changed
  the client API and rejects the existing `Client(..., headers=...)` call.
  Actual HTTP tool verification used MCP 1.30.0.

## Automated Coverage

The runtime tests cover implicit and disabled roles, skill hashes, call-count
and cumulative prompt budgets, multiple tool rounds, exact validation call IDs,
usage on failures, denied tool receipts, and the tool-round limit.

Use `bash scripts/run_tests.sh` with the documented Gold support runs prepared.
The online checks below are separate from the automated suite and use real
provider requests.

Final verification used the isolated test entry with MCP 1.30.0 installed:

- Suite excluding `tests/test_cli.py`: 1280 passed, 1 skipped, 98 subtests passed.
- Non-Gold CLI tests, run separately: 57 passed, 8 subtests passed.
- Total covered tests: 1337 passed and 1 skipped; 35 Gold CLI tests were not run.
- Markdown links: 17 files checked, no broken links.
- All application modules imported with Python's `-S` option and no third-party
  runtime packages on the import path.

## Online Results

Endpoint: `https://kuaipao.ai/v1`. Model: `glm-5.3-flash`.
Credentials were entered through hidden terminal input and kept in process
memory/environment; no credential was added to project files.

| Check | Observed Result |
| --- | --- |
| Authentication and model discovery | Passed; the selected model was listed. |
| Implicit reviewer role | Passed; default skill and hash recorded, valid response rejected an unsupported superiority claim. |
| Real local HTTP MCP, `max_calls=2` | Passed; two model requests and one tool call; the final response reproduced a value available only from the tool. |
| Per-request provider usage | First request: 357 input / 69 output tokens. Continuation: 463 input / 182 output tokens. |
| Real local HTTP MCP, `max_calls=1` | Passed; one model request and one tool call; the continuation was blocked before a second model request. |

Local evidence is under `runs/kuaipao-runtime-verification-v2/` and
`runs/kuaipao-mcp-verification-v2/verification.json`. These generated run
directories are not source files. The first MCP attempt encountered the host's
unsupported `socks://` proxy setting; the successful local test cleared
`ALL_PROXY` and set loopback `NO_PROXY` in its own process.

## Full Pipeline Boundary

`runs/kuaipao-iris-integration/` attempted the real online literature workflow
with the repository's frozen Iris benchmark manifests and multi-agent mode.
Crossref and OpenAlex returned literature. A test-only review approval retained
the metadata and coverage warnings and explicitly excluded publication claims.

The initial idea-generation request timed out after 90 seconds. Resuming with
a 180-second request timeout reused the existing checkpoints. The next idea
response failed the expected schema; the existing fallback continued to
experiment planning. The experiment audit then blocked execution because the
selected fallback idea did not satisfy the fixed candidate/baseline/ablation
and deterministic-repeat constraints. The generated experiment plan included
those constraints, but the audit requires them in both the idea and the plan.

This is a failed full-pipeline integration attempt, not a completed scientific
run. It did not execute that run's benchmark, produce a paper, or reach final
independent deliberation. No final gate override was written.
