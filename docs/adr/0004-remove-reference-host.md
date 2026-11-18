# ADR 0004: Remove the reference terminal host

Status: Accepted. Date: 2026-11-15.

## Context

The product is a stdio MCP server. `examples/host.py` is a separate interactive terminal application with project-selection state, document imports and exports, field-subset prompts, cached artifacts, and a stored-draft mode. It does not integrate with an agent. Its 647 lines and 718 lines of dedicated tests maintain a second application whose value is largely demonstrating calls to the server.

The MCP project's [Inspector](https://github.com/modelcontextprotocol/inspector/tree/4d3464cb3a6dde609d7b5ac24c440b947eb40f23) already provides an independent client for discovery and tool invocation. This repository already documents Inspector 2.14.0, tests real MCP subprocesses, and checks freshly installed wheels and source distributions directly through the SDK. Keeping a custom interactive host adds little value relative to these facilities.

[ADR 0003](0003-remove-console-script-tool.md) deliberately preserved the host and its coverage during removal of the console-script tool. This decision addresses the deferred slice. The [surface and coverage audit](../archive/reference-host-removal-audit.md) records the affected files, surviving guarantees, and implementation checks against `252b16e` on main. No new release is required to make this decision.

## Decision

Remove the reference host completely, including its dedicated tests, Make entry points, source-distribution inclusion, and separate package-qualification discovery subprocess. Do not retain a deprecated command, compatibility wrapper, replacement executable example, or new client framework. This supersedes the roadmap's earlier suggestion of a smaller SDK example and ADR 0003's temporary requirement to retain the host. The ten server tools, installed `bestpractices-mcp` entry point, schemas, storage format, and caller-owned document contract remain unchanged.

Preserve server behavior through the existing automated tests and installed-package probes. Before deleting the host tests, move two narrowly scoped assertions into the existing direct-MCP suites: exact long Unicode URL generation without a preceding validation call, and generation from an explicit subset of a stored snapshot without modifying the stored draft. Do not reproduce terminal interaction, file export, overwrite refusal, or cached-artifact lifecycle tests: those features are retiring. Do not add permanent tests asserting that the host no longer exists.

Use Inspector for independent-client qualification and exploratory tool use. Use the existing live browser runbook for actual BadgeApp proposal application and restoration. Neither substitutes for deterministic regression tests. Inspector's [CLI guidance](https://github.com/modelcontextprotocol/inspector/blob/4d3464cb3a6dde609d7b5ac24c440b947eb40f23/docs/cli-smoke-testing.md) distinguishes smoke tests from conformance testing; strict discovery is not a test of tool execution or BadgeApp behavior.

## Coverage boundaries

| Layer | Required evidence after removal |
| --- | --- |
| Automated Python suite | Discovery, schemas, typed/text results and errors, public-read bounds and identity, document semantics, exact URL encoding, explicit/stored precedence, persistence, isolation, budgets, cancellation and atomic-write behavior. Extend existing tests only for the two identified migrations. |
| Installed-package checks | Continue offline wheel checks and fresh wheel/sdist installations, installed entry-point discovery, catalog access, storage/restart, and synthetic public workflows. Run the probe and shared fixture from the exact candidate sdist; remove only the extra host launch and its report field. |
| Inspector | Against the exact installed candidate: discovery and schema findings; readable successes/errors; explicit document and stored-draft calls; reconnect/read persistence; extraction of the latest exact proposal URL. Record the Inspector and server versions and installation identity. |
| Authenticated browser | Both proposal delivery routes and all six existing cases: blocked pair, status override, blank pair, retained wording, clearing wording, and matching values; exact encoded versus displayed text; untouched neighbors; discard and baseline restoration. No Save/Submit operation. |

Inspector does not implement this project's selection policy or guarantee automatic clearing of stale results. Instructions must require an explicit choice of an existing project after lookup, use of the latest successful result for that project/document, and `read_draft` before deciding whether to retry an uncertain write. Construct subsets as explicit documents, retaining relevant identity fields. Do not describe these caller obligations as server session enforcement or Inspector features.

The browser runbook must identify its deliberately URL-shaped QA text before execution. Capture the actual baseline, preview, and restored controls for each selected case; retain exact tool inputs/results and URLs. A post-preview public read is supplementary evidence, not a substitute for checking the restored form. Hidden values that were not inspected must be identified as unverified. This prevents an intentional preview change from being confused with baseline corruption.

## CI, packaging, and dependencies

Keep the current compatibility matrix, pre-commit offline suite, release qualification, security scans, report retention, and publication/verification jobs. They already exercise the surviving automated paths. Remove obsolete Make/Ruff paths and source-distribution requirements, and stop emitting `reference_host_discovery`; no checked-in consumer requires that field. Preserve archive identity and license checks. No historical report needs rewriting and no compatibility field is necessary.

No Python dependency exists solely for the host: it uses the standard library and the MCP SDK, which the server and tests still require. Keep `pyproject.toml`, `uv.lock`, OSV policy, SBOM scope, attestations, and release-manifest logic unless implementation uncovers a concrete additional dependency. Preserve catalog package data and the shared synthetic read-server fixture.

Inspector remains an externally installed, exactly versioned maintainer tool, optional for ordinary contributors. It becomes the documented manual independent-client qualification route before promotion to stable and for relevant release candidates. This slice does not add Node/npm to standard setup, pre-commit, CI, package dependencies, or release inventories. A future mandatory Inspector CI job would require its own dependency/inventory and failure-policy decision. Manual Inspector results must not be represented as covered by this project's OSV scans or release attestations merely because Inspector was used.

The deferred coverage-instrumentation question in [the coverage review](../archive/coverage-review.md) must be reassessed, but removing the host does not remove the SDK's filtered subprocess environment. Retain working subprocess coverage instrumentation for this slice; do not fold an unrelated warning fix into the removal or silently reduce measured server coverage.

## Implementation acceptance

Follow the file inventory and test mapping in the audit. Update current contributor, architecture, testing, release, and browser-QA instructions, including Windows executable paths and disposable absolute storage roots. Preserve historical milestones and ADRs with a retirement note rather than rewriting past behavior. Generic references to a user's MCP host remain valid.

Run `make validate`, `make test-coverage`, `make test-package`, and `make check-fresh-package`; run the existing release artifact/qualification regression checks and verify both archive contents without adding absence-only tests. The existing CI matrix must remain green. Review surviving behavioral assertions and subprocess coverage rather than preserving test count or relying on an aggregate percentage. Record Inspector qualification and repeat the unsaved live browser matrix against the candidate before declaring this slice qualified. No release, production save, new browser automation framework, or broad refactor is part of this decision.

## Consequences

Users lose the guided terminal workflow and its import/export safeguards. Inspector requires Node/npm and manual composition of some tool arguments, but it exercises the server through an independently maintained client. The project keeps responsibility for its MCP contract and documents the remaining caller responsibilities. The expected implementation is a substantial net deletion with two small additions to existing integration tests.
