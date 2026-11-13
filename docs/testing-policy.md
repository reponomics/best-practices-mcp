# Test authority and live compatibility

Required tests establish conformance to the documented upstream automation procedures, pinned criteria YAML and English locale, and explicitly agreed MCP contracts. They do not execute BadgeApp's Ruby implementation or reproduce Save/Submit processing. The same contracts govern local tests, CI and release qualification.

## Required coverage

| Authority and agreed boundary | Required verification |
| --- | --- |
| Criteria YAML and English locale; approved flag entailments, level-bounded details inheritance and Baseline aliases | `tests/test_criteria.py` independently reads all 209 definitions with standard PyYAML and checks public records; `make catalog-check` checks reproducible generation |
| Upstream `automation-proposals.md` URL format and explicit override parameters; the artifact limits in the transfer-rules document | `tests/test_transfer_contract.py` and `tests/test_proposals.py` check exact encoding, explicit overrides, standalone justification, unchanged-value inclusion, and independence from observed answers |
| Specification §4 advisory validation, including minimum length, exact comment prefix and URL-pattern rules | `tests/test_validation.py` checks explicit agreed examples and operational boundaries; successful validation does not establish website acceptance |
| [Specification §6, Form-fill scripts](specification.md#form-fill-scripts): guarded console fallback, an approved project feature rather than an upstream-supported API | `tests/test_scripts.py` executes generated JavaScript against controlled synthetic forms, checking routes, control preflight, assignments, event dispatch, value preservation and partial-failure reporting |
| Pinned source provenance and controlled-form derivation | Catalog integrity and `tests/test_upstream_sources.py` verify retained input hashes. The form derivation record preserves source references as explanatory context; it is not a checked copy of those sources or evidence of the deployed site |
| Nine-tool MCP contract, bounded reads, local documents/storage and reference host | Protocol, network, document, storage, host and package tests remain required |
| Actual BadgeApp edit-form integration | The [local browser runbook](live-browser-qa.md) exercises generated URLs and a script against an authenticated live form, with the exact server version and observations recorded |

The retained upstream documents are under `vendor/badgeapp/docs/`. The [transfer rules](transfer-rules.md) record approved compatibility details and the documented disagreement about unknown-status URL resets. Deterministic artifact tests verify included/excluded fields and exact supplied values. They do not compare saved answers or simulate BadgeApp's decision matrix. Live browser checks observe the actual edit-form effects. Save/Submit acceptance, persisted-value transformations, importer behavior and automated assessment remain outside this contract.

## Synthetic forms and live checks answer different questions

Synthetic forms are deliberately small test inputs, not a BadgeApp replica. They allow controlled tests of missing, ambiguous, disabled or wrong-type controls and runtime failures without altering a live application. Those tests establish how the generated script behaves under the supplied DOM conditions. They cannot establish that the real website still has the assumed field names, types or values: an incorrect assumption shared by code and fixture could pass both.

A locally supervised browser check supplies that integration evidence. It checks the actual controls and upstream URL handling without requiring production saves. Record unexpected form automation or a changed baseline explicitly; neither the public JSON observation nor an earlier screenshot guarantees the next rendered form's state. Limited tested levels and cases should be reported as such, without claiming exhaustive live coverage.

The first browser run is deferred until after publication of the first beta and must pass before stable promotion. Subsequent release candidates repeat the runbook. This manual gate remains separate from deterministic CI and is never marked passed because CI is green.

## Commands and gates

After `make setup` and `make setup-dom` with Node 24, run:

```sh
make check
make test-catalog
make test-upstream
make test-coverage
make test-package
```

Required GitHub Actions jobs retain the six Python 3.11/3.12 combinations across Linux, macOS and Windows, coverage and fresh wheel/sdist installation. The [release procedure](releasing.md) identifies the remaining package, remote CI and publication gates.

The [November 2026 coverage gap review](coverage-review.md) records the measured baseline, added regression cases, and the remaining defensive paths that are unreachable under current invariants.

Upstream implementation details do not define the public contract. The [design decisions](design.md#follow-documented-procedures-not-internal-save-behavior) explain the boundary between artifact preparation and a user's separate decision to authorize a host agent to operate the browser and save.
