# Test authority and optional upstream diagnostics

Historical initial-implementation record. This preserves planning and review context, including the implementation status at its original checkpoints. Use the [maintained documentation](../../README.md) for current behavior. Detailed execution reports and earlier versions are archived privately; milestone summaries retain substantive findings and outcomes.

Required tests establish conformance to the documented upstream automation procedures, pinned criteria YAML and English locale, and explicitly agreed MCP contracts. They do not require execution of BadgeApp's Ruby implementation. This policy governs future milestones and corrections as well as the current CI gates.

## Required coverage

| Authority and agreed boundary | Required verification |
| --- | --- |
| Criteria YAML and English locale; approved flag entailments, level-bounded details inheritance and Baseline aliases | `tests/test_criteria.py` independently reads all 209 definitions with standard PyYAML and checks public records; `make catalog-check` checks reproducible generation |
| Upstream `automation-approach.md` decision matrix and `automation-proposals.md` URL procedures; the accepted v1 limits in the transfer-rules document | `tests/test_transfer_contract.py` and `tests/test_proposals.py` check retention, forcing, status/justification coupling, standalone justification, exact overrides, raw encoding and approved whitespace handling |
| Specification §4 advisory validation, including minimum length, exact comment prefix and URL-pattern rules | `tests/test_validation.py` checks explicit agreed examples and operational boundaries; successful validation does not establish website acceptance |
| [Specification §6, Form-fill scripts](badgeapp-mcp-spec.md#form-fill-scripts): guarded console fallback, an approved project feature rather than an upstream-supported API | `tests/test_scripts.py` executes generated JavaScript against controlled synthetic forms, checking guards, preflight and value preservation |
| Pinned source provenance and controlled-form provenance | `tests/test_upstream_sources.py` and catalog integrity checks verify hashes and recorded revision; hashing a Ruby source file does not execute it or make all its behavior normative |
| Nine-tool MCP contract, bounded reads, local documents/storage and reference host | Existing protocol, network, document, storage, host and package tests remain required |

The retained upstream documents are under `vendor/badgeapp-m3/docs/`. The [transfer rules](badgeapp-mcp-transfer-rules.md) record approved compatibility details and the documented disagreement about unknown-status URL resets. These tests concern artifact preparation and edit-form effects. Save/Submit acceptance, persisted-value transformations, importer behavior and automated assessment remain outside this contract.

## Commands and gates

After `make setup` and `make setup-dom` with Node 24.22.3 or newer within 24.x, run:

```sh
make check
make test-catalog
make test-upstream
make test-coverage
make test-package
```

Default pytest collection, including `python -m pytest tests`, excludes `tests/optional/`. Required GitHub Actions jobs retain the six Python 3.11/3.12 combinations across Linux, macOS and Windows, coverage and fresh wheel/sdist installation. They do not invoke Ruby. M5 QA uses `test-upstream` in place of the former required `oracle-check`. Existing reports retain their historical execution evidence; the [M5 milestone summary](milestones/M5.md) records this change separately.

## Optional maintainer investigation

```sh
make oracle-check
```

This explicitly requires Ruby, re-executes the selected pinned transfer/predicate methods with `m3_oracle.rb --check`, and runs the supplementary Python comparisons in `tests/optional/`. Those comparisons use historical Ruby-generated catalog, transfer and predicate fixtures. The catalog comparison reads its committed fixture; this command does not regenerate it. Maintainers can regenerate that fixture deliberately with `ruby tests/fixtures/upstream/generate_oracle.rb` and review the resulting diff.

These checks provide additional implementation evidence, not milestone or publication gates. A mismatch prompts investigation against the documented contract and accepted compatibility decisions; it does not authorize changing server behavior to copy an internal upstream detail. Changing the public contract requires an explicit decision and corresponding documentation and required tests.

Vendored Ruby files and generation scripts remain available for this investigation and provenance. Source distributions retain these development materials; installed wheels and server execution do not depend on Ruby. No runtime behavior, tool, permission or browser operation is added by this policy change.

Consulting these sources during development does not turn BadgeApp's internal Ruby behavior into the public contract. In particular, these diagnostics do not predict submission acceptance or persisted results. The [design decisions](../../reference/design.md#follow-documented-procedures-not-internal-save-behavior) explain this boundary and distinguish the MCP's no-save behavior from a user's separate decision to authorize a host agent to operate the browser and save.
