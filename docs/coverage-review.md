# Coverage gap review — 2026-11-12

## Scope and baseline

Reviewed the existing `build/coverage/coverage.json` and `summary.json`, generated on November 11, 2026 at 23:02 America/New_York for commit `66fa5fac1efa73559e007403404575f393d6c96a`. The report measures the server package, including MCP subprocesses; it does not measure development scripts, the reference host, or generated JavaScript. Their behavioral tests remain part of the suite.

The baseline contains 1,342 executable statements and 386 branch destinations: 29 missing statements and 16 missing branch destinations, for 97.40% combined coverage (97.84% statements, 95.85% branches). The associated test run had 692 passes and one native-Windows skip. Baseline evidence was copied to ignored `build/coverage-review-baseline/` before regenerating the reports.

## Plan and disposition of every reported gap

The initial review prioritized deterministic behavior through public entry points, then bounded failure injection for filesystem and transport boundaries. That test-only change did not modify production code, coverage exclusions, or percentage gates. Source line numbers below refer to the server files at that stage; the subsequent retry-loop refactor is recorded at the end of this document.

| Module | Original missing lines; branch destinations | Tests added and disposition |
| --- | --- | --- |
| `badgeapp.py` | 72, 86–87, 167–168, 227; 71→72, 221→227 | `test_badgeapp.py`: nondefault ports preserve URL identity distinctions; excessive numeric identifiers fail before fetching; excessive pagination integers preserve candidates but leave pagination uncertain; deeply nested public answers become upstream errors. All covered. |
| `documents.py` | 69–70 | `test_documents.py`: an integer exceeding Python's configured decimal-conversion limit becomes `invalid_document`; the previous process-wide limit is restored. All covered. |
| `drafts.py` | 84; 83→84 | `test_drafts.py`: invalid requested IDs fail regardless of whether document provenance is absent or valid. All covered. |
| `http.py` | 52, 190, 197, 202, 214–215, 219, 270, 280, 289, 306; 196→197, 200→202, 218→219, 269→270, 279→280, 297→306 | `test_http.py`: preexisting cookie suppression, explicit transport closure, expired or unreachable limiter starts, timezone-less Retry-After fallback, deadlines before dispatch and after response completion, and safe nonretryable transport failures. All covered except the two defensive paths described below. |
| `server.py` | 133, 158; 132→133, 157→158 | `test_document_tools.py`: direct calls to all four network-dependent tools without a lifespan context return schema-valid sanitized errors without creating storage or starting HTTP. All covered. |
| `storage.py` | 39, 132, 212, 225–226; 131→132, 201→205, 209→212 | `test_storage.py`: root resolution failures; rejection and closure of a descriptor whose type changes after layout inspection; failed cleanup preserves the old destination and reports an error; controlled Windows writable-destination and path-chmod fallback cases. All covered. |
| `transfer.py` | 41; 40→41 | `test_proposals.py`: non-list override inputs fail through the URL generator without mutating the draft. All covered. |
| `validation.py` | 123; 122→123 | `test_validation.py`: a missing level produces the documented operational error. All covered. |

## Defensive paths remaining after the initial review

### `http.py:214–215`: numeric Retry-After conversion exception

The preceding full match admits only a nonempty string of ASCII digits after whitespace trimming. Python's float conversion accepts these strings, producing a finite value or positive infinity for a sufficiently large number. Ordinary header values therefore cannot raise the caught `ValueError` or `OverflowError` here. Malformed headers take the separately tested date/fallback path.

Covering this handler would require replacing the builtin float conversion or violating the string-input assumption. Such a test would exercise an invented dependency failure rather than an HTTP response the adapter can receive. Leave this defense visible as uncovered. Revisit it if the accepted numeric syntax or conversion implementation changes; any simplification should be a separate production change.

### Original `http.py:306`, branch `297→306`: retry-loop fallthrough (subsequently removed)

The original retry count was a fixed positive value (`MAX_ATTEMPTS = 3`). Each attempt either returned a result, raised a terminal error, or invoked `_retry`; `_retry` always raised for a final failed attempt. Consequently, normal execution could not finish the loop and reach its final safety raise.

Covering that path would have required setting the retry count to zero or replacing `_retry` so that it violated its final-attempt contract. Existing tests exercised actual retry exhaustion. The initial review left this defense visible as uncovered; the follow-up refactor below removes it by making exhaustion explicit in the loop.

These are invariant-constrained paths, not gaps requiring a larger test harness. All reachable gaps in the supplied report have tests; no additional coverage exclusions were introduced to hide the residual paths.

## Initial review verification

`make test-coverage` passed on macOS with Python 3.12.4: **732 passed, one native-Windows skip**, adding 40 passing test cases over the original report. All report-generation stages passed, and the source fingerprint remained unchanged during collection. The run emitted one pytest assertion-rewrite warning because the coverage subprocess hook imports AnyIO before pytest; no test failed.

| Metric | Existing report | After this review |
| --- | --- | --- |
| Combined statement/branch coverage | 97.40% | **99.77%** |
| Statement coverage | 1,313/1,342 (97.84%) | **1,339/1,342 (99.78%)** |
| Branch coverage | 370/386 (95.85%) | **385/386 (99.74%)** |
| Missing statements / branch destinations | 29 / 16 | **3 / 1** |

At the end of the initial review, every server module except `http.py` had 100% statement and branch coverage. The residual gaps were exactly lines 214–215 and 306, and branch 297→306, discussed above. HTML, XML, JSON, test results, and execution evidence under ignored `build/coverage/` are regenerated by each subsequent run; open `build/coverage/html/index.html` for the latest detailed report.

Focused suites and repository-wide Ruff formatting/lint, dependency consistency, and whitespace checks pass. An independent read-only review found no actionable issues in test isolation, failure cleanup, or Python 3.11 compatibility.

Windows fallback tests use controlled platform and filesystem seams on macOS. They do not replace the existing native Windows CI jobs or the native-Windows junction test, which remains skipped locally. This review does not claim new live-site or cross-platform execution evidence.

## Follow-up: explicit retry exhaustion

The retry loop now counts failed attempts and raises its final error directly, without an unreachable trailing fallback. `_update_cooldown` records and checks the shared Retry-After delay; `_wait_for_retry` applies backoff only when another attempt is allowed. The fixed three-attempt limit is unchanged.

Cooldown handling still precedes exhaustion: a final 503 response with an out-of-budget Retry-After yields `rate_limited`, while a final 503 with an in-budget delay yields `upstream_unavailable`. A final 429 retains its remaining cooldown in the error. Both cases preserve the shared cooldown for subsequent calls, and neither sleeps after the final failure.

The existing behavior tests remain in place; the test that directly exercised the old private `_retry` helper now calls `_update_cooldown`. Five additional regression cases verify final-response error precedence, cooldown persistence into a later call, and exhaustion after transient transport errors without a final sleep.

Validation: `make test-network` passed all 68 HTTP cases; `make test-coverage` passed 737 tests with the existing native-Windows skip and AnyIO assertion-rewrite warning. Formatting, lint, and whitespace checks passed, and an independent complexity/behavior review found no actionable issues. Coverage report generation passed with no source changes during collection.

The latest server coverage is **99.88% combined**, with **1,344/1,346 statements (99.85%)** and **384/384 branch destinations (100%)** covered. Only the numeric conversion exception handler at `http.py:214–215` remains uncovered. No coverage exclusions were added.

## Deferred: coverage startup warning

The `PytestAssertRewriteWarning` for AnyIO originates in `scripts/check_coverage.py`: its temporary startup hook imports the MCP SDK, and therefore AnyIO, before pytest installs assertion rewriting. Potential remediation is to defer SDK setup in the pytest process to `pytest_configure`, retaining startup forwarding for measured descendants; a disposable macOS prototype passed 56 read-tool and host tests with the warning treated as an error and subprocess coverage preserved. Defer this change until the planned reference-host deprecation and possible replacement by the MCP Inspector, when the testing infrastructure should be reassessed together. Removing the host may allow explicit coverage-environment forwarding in a shared test helper instead of the startup hook, although direct SDK subprocess tests still need forwarding. The current warning affects assertion diagnostics in already-imported AnyIO code, not whether assertions execute.
